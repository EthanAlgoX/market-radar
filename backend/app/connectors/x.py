"""Read-only X capture using the user's explicitly supplied, local session.

Twikit's web API can change or be rate limited. Connection status is confirmed
with ``client.user()``; possessing cookies alone never means connected. Browser
login uses a new profile owned by this app, never an existing Chrome profile.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable

try:
    from twikit import Client
except ImportError:  # Other sources still work before optional X setup.
    Client = None  # type: ignore[assignment]


class MissingCredentials(RuntimeError):
    """The user has not connected their X account."""


class XConnectorError(RuntimeError):
    """Safe provider error; deliberately excludes upstream request/response text."""


def parse_cookies(value: str | dict | list) -> dict[str, str]:
    """Accept Twikit dictionaries and browser-exported lists, with no logging."""
    if isinstance(value, str):
        if len(value) > 256_000:
            raise ValueError("Cookie JSON 过大，请仅提供 X 会话 Cookie。")
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("请提供有效的 Cookie JSON（对象或浏览器导出的列表）。") from None
    if isinstance(value, dict) and isinstance(value.get("cookies"), list):
        value = value["cookies"]
    cookies: dict[str, str] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("Cookie 列表中的每一项都需要 name 和 value。")
            domain = str(item.get("domain", "")).lstrip(".").lower()
            # Do not import unrelated website cookies from a browser export.
            if domain and not (
                domain == "x.com" or domain.endswith(".x.com")
                or domain == "twitter.com" or domain.endswith(".twitter.com")
            ):
                continue
            name, content = item.get("name"), item.get("value")
            if isinstance(name, str) and isinstance(content, str):
                cookies[name] = content
    elif isinstance(value, dict):
        for name, content in value.items():
            if isinstance(content, dict):
                content = content.get("value")
            if isinstance(name, str) and isinstance(content, str):
                cookies[name] = content
    else:
        raise ValueError("Cookie JSON 必须是对象或列表。")
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise ValueError("Cookie 中必须包含非空的 auth_token 和 ct0。")
    if any("\n" in v or "\r" in v for v in cookies.values()):
        raise ValueError("Cookie 值不能包含换行符。")
    return cookies


def _safe_error(exc: Exception, operation: str) -> str:
    """Never interpolate exceptions: they may contain URLs, headers or tokens."""
    kind = type(exc).__name__
    code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if code is None and response is not None:
        code = getattr(response, "status_code", None)
    if kind == "TooManyRequests" or code == 429:
        return f"{operation}失败：X 请求过于频繁（429），请稍后再试。"
    if kind in {"Unauthorized", "AccountLocked", "AccountSuspended"} or code == 401:
        return f"{operation}失败：X 会话已失效或账号需要验证，请重新登录。"
    if kind == "Forbidden" or code == 403:
        return f"{operation}失败：X 拒绝访问（403），请在 X 检查登录或安全验证。"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or kind in {
        "TimeoutException", "ConnectTimeout", "ReadTimeout", "RequestTimeout"
    }:
        return f"{operation}超时，请检查网络或代理后重试；会话尚未确认可用。"
    if kind in {"ConnectError", "NetworkError", "ProxyError", "RemoteProtocolError"}:
        return f"{operation}失败：无法连接 X，请检查本机网络或代理。"
    if kind in {"NotFound", "UserNotFound", "UserUnavailable"} or code == 404:
        return f"{operation}失败：目标不可用，或 X 接口已经变更。"
    return f"{operation}失败：X 接口返回异常，可能需要重新登录或更新采集器。"


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return getattr(obj, key, default)
    except (KeyError, TypeError, ValueError, AttributeError):
        return default


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _post_time(tweet: Any) -> str:
    date = _get(tweet, "created_at_datetime")
    if not isinstance(date, datetime):
        raw = _get(tweet, "created_at", "")
        try:
            date = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        except (TypeError, ValueError):
            try:
                date = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                try:
                    milliseconds = (int(_get(tweet, "id")) >> 22) + 1288834974657
                    date = datetime.fromtimestamp(milliseconds / 1000, timezone.utc)
                except (TypeError, ValueError, OverflowError, OSError):
                    raise XConnectorError("X 帖子缺少有效发布时间，未将采集时间充当发布时间。") from None
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).isoformat()


def _handle(tweet: Any) -> str:
    return str(_get(_get(tweet, "user"), "screen_name", "") or "").lstrip("@")


def _url(tweet: Any) -> str:
    handle = _handle(tweet)
    tweet_id = str(_get(tweet, "id", ""))
    return f"https://x.com/{handle}/status/{tweet_id}" if handle else f"https://x.com/i/web/status/{tweet_id}"


def _text(tweet: Any) -> str:
    text = str(_get(tweet, "full_text") or _get(tweet, "text") or "")
    for link in _get(tweet, "urls", []) or []:
        if isinstance(link, dict) and link.get("url") and link.get("expanded_url"):
            text = text.replace(str(link["url"]), str(link["expanded_url"]))
    return text


def tweet_to_post(tweet: Any, channel: str) -> dict[str, Any]:
    tweet_id = str(_get(tweet, "id", ""))
    if not tweet_id:
        raise XConnectorError("X 返回了没有帖子 ID 的数据，未保存该条目。")
    text = _text(tweet)
    references = []
    for attribute, label in (("retweeted_tweet", "转发"), ("quote", "引用")):
        referenced = _get(tweet, attribute)
        if referenced is None:
            continue
        reference = {
            "type": "repost" if attribute == "retweeted_tweet" else "quote",
            "external_id": str(_get(referenced, "id", "")),
            "author": "@" + _handle(referenced) if _handle(referenced) else "X 用户",
            "url": _url(referenced),
            "content": _text(referenced),
        }
        references.append(reference)
        text += f"\n\n{label} {reference['author']}：\n{reference['content']}\n{reference['url']}"
    text = text.strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "X 帖子")
    return {
        "external_id": tweet_id,
        "source": "x",
        "source_name": "X",
        "author": "@" + _handle(tweet) if _handle(tweet) else "X 用户",
        "title": first_line[:160],
        "content": text,
        "url": _url(tweet),
        "published_at": _post_time(tweet),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "likes": _count(_get(tweet, "favorite_count")),
            "comments": _count(_get(tweet, "reply_count")),
            "reposts": _count(_get(tweet, "retweet_count")),
        },
        "channels": [channel],
        "references": references,
    }


class XConnector:
    REQUEST_TIMEOUT = 25.0
    LOGIN_TIMEOUT = 600.0
    MAX_PAGES = 20
    MAX_POSTS = 400
    STATUS_RETRY_INTERVAL = 60.0

    def __init__(self, secrets: Any, data_dir: Path):
        self.secrets = secrets
        self.data_dir = Path(data_dir)
        self._client: Any = None
        self._user: Any = None
        self._login_task: asyncio.Task | None = None
        self._client_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._generation = 0
        self._last_validation_attempt = 0.0
        self._state = "disconnected"
        self._message = "尚未连接 X 账号。"
        self._username: str | None = None

    def _snapshot(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "username": self._username,
            "message": self._message,
            "configured": bool(self.secrets.get("x.cookies")),
        }

    def _assert_generation(self, generation: int) -> None:
        if self._generation != generation:
            raise XConnectorError("X 连接操作已取消，请重新发起。")

    async def _close_client(self, client: Any) -> None:
        if client is not None:
            http = getattr(client, "http", None)
            if http is not None and callable(getattr(http, "aclose", None)):
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(http.aclose(), timeout=5)

    async def _drop_client(self) -> None:
        client, self._client = self._client, None
        self._user = None
        await self._close_client(client)

    def _make_client(self, cookies: dict[str, str]) -> Any:
        if Client is None:
            raise XConnectorError("X 采集依赖尚未安装，请先完成后端依赖安装。")
        client = Client("en-US", timeout=self.REQUEST_TIMEOUT)
        client.set_cookies(cookies, clear_cookies=True)
        return client

    async def _validate(self, cookies: dict[str, str], generation: int) -> Any:
        self._last_validation_attempt = time.monotonic()
        client = self._make_client(cookies)
        try:
            user = await asyncio.wait_for(client.user(), timeout=self.REQUEST_TIMEOUT)
            self._assert_generation(generation)
            username = str(_get(user, "screen_name", "") or "")
            user_id = str(_get(user, "id", "") or "")
            if not username or not user_id:
                raise XConnectorError("X 未返回有效账号身份，会话尚未确认可用。")
        except BaseException:
            await self._close_client(client)
            raise
        await self._drop_client()
        try:
            self._assert_generation(generation)
        except XConnectorError:
            await self._close_client(client)
            raise
        self._client, self._user = client, user
        self._username = username
        self.secrets.set("x.account", {"username": username, "user_id": user_id})
        self._state = "connected"
        self._message = f"已验证 @{username} 的 X 会话。"
        return client

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is not None:
                return self._client
            cookies = self.secrets.get("x.cookies")
            if not cookies:
                raise MissingCredentials("请先连接自己的 X 账号。")
            generation = self._generation
            try:
                return await self._validate(parse_cookies(cookies), generation)
            except XConnectorError as exc:
                if generation == self._generation:
                    self._state, self._message = "error", str(exc)
                raise
            except Exception as exc:
                if generation == self._generation:
                    self._state = "error"
                    self._message = _safe_error(exc, "验证 X 会话")
                raise XConnectorError(_safe_error(exc, "验证 X 会话")) from None

    async def status(self) -> dict[str, Any]:
        if self._login_task and not self._login_task.done():
            return self._snapshot()
        if not self.secrets.get("x.cookies"):
            return self._snapshot()
        if self._client is None and (
            self._last_validation_attempt == 0
            or time.monotonic() - self._last_validation_attempt >= self.STATUS_RETRY_INTERVAL
        ):
            generation = self._generation
            try:
                await self._ensure_client()
            except (XConnectorError, ValueError, MissingCredentials) as exc:
                if generation == self._generation:
                    self._state = "error"
                    self._message = str(exc)
        return self._snapshot()

    async def _cancel_login(self) -> None:
        task, self._login_task = self._login_task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def start_login(self) -> dict[str, Any]:
        if self._login_task and not self._login_task.done():
            return self._snapshot()
        self._generation += 1
        self._state = "connecting"
        self._message = "正在打开独立浏览器窗口，请在该窗口登录自己的 X 账号。"
        self._login_task = asyncio.create_task(self._browser_login(self._generation))
        return self._snapshot()

    async def _store_and_validate(self, cookies: dict[str, str], generation: int) -> dict[str, Any]:
        self._assert_generation(generation)
        self.secrets.set("x.cookies", cookies)
        self.secrets.delete("x.account")
        self._username = None
        await self._drop_client()
        try:
            async with self._client_lock:
                self._assert_generation(generation)
                await self._validate(cookies, generation)
        except Exception as exc:
            if generation == self._generation:
                self._state = "error"
                detail = str(exc) if isinstance(exc, XConnectorError) else _safe_error(exc, "验证 X 会话")
                self._message = "会话已保存，但尚未验证：" + detail
        return self._snapshot()

    async def save_cookies(self, cookies: str | dict | list) -> dict[str, Any]:
        parsed = parse_cookies(cookies)
        await self._cancel_login()
        self._generation += 1
        self._state = "connecting"
        self._message = "正在验证 X 会话。"
        return await self._store_and_validate(parsed, self._generation)

    async def _browser_login(self, generation: int) -> None:
        profile = self.data_dir / "x-browser" / uuid.uuid4().hex
        context = None
        try:
            from playwright.async_api import async_playwright

            profile.mkdir(parents=True, mode=0o700, exist_ok=False)
            profile.parent.chmod(0o700)
            async with async_playwright() as playwright:
                options = {"user_data_dir": str(profile), "headless": False, "viewport": {"width": 1280, "height": 850}}
                try:
                    context = await playwright.chromium.launch_persistent_context(channel="chrome", **options)
                except Exception:
                    context = await playwright.chromium.launch_persistent_context(**options)
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=45_000)
                deadline = time.monotonic() + self.LOGIN_TIMEOUT
                self._message = "请在独立浏览器中完成 X 登录；完成后将自动验证并关闭窗口。"
                while time.monotonic() < deadline:
                    self._assert_generation(generation)
                    cookies = await context.cookies(["https://x.com", "https://twitter.com"])
                    try:
                        parsed = parse_cookies(cookies)
                    except ValueError:
                        await asyncio.sleep(1)
                        continue
                    await self._store_and_validate(parsed, generation)
                    return
                self._state = "error"
                self._message = "X 登录等待已超时，窗口已关闭。请重新连接或手动导入会话 Cookie。"
        except asyncio.CancelledError:
            raise
        except ImportError:
            if generation == self._generation:
                self._state = "error"
                self._message = "浏览器登录依赖尚未安装，请安装 Playwright 或手动导入会话 Cookie。"
        except Exception:
            if generation == self._generation:
                self._state = "error"
                self._message = "X 登录窗口无法继续，可能被关闭、浏览器未安装或 X 拒绝自动化登录。请重试或手动导入会话 Cookie。"
        finally:
            if context is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(context.close(), timeout=5)
            if profile.exists():
                await asyncio.to_thread(shutil.rmtree, profile, True)

    async def disconnect(self) -> dict[str, Any]:
        self._generation += 1
        await self._cancel_login()
        await self._drop_client()
        self.secrets.delete("x.cookies")
        self.secrets.delete("x.account")
        profile_root = self.data_dir / "x-browser"
        if profile_root.is_dir() and not profile_root.is_symlink():
            await asyncio.to_thread(shutil.rmtree, profile_root, True)
        self._username = None
        self._state = "disconnected"
        self._message = "已断开 X 账号并清除本地会话。"
        self._last_validation_attempt = 0
        return self._snapshot()

    async def shutdown(self) -> None:
        self._generation += 1
        await self._cancel_login()
        await self._drop_client()

    async def _call(self, request: Awaitable, operation: str, generation: int) -> Any:
        try:
            result = await asyncio.wait_for(request, timeout=self.REQUEST_TIMEOUT)
            self._assert_generation(generation)
            return result
        except XConnectorError:
            raise
        except Exception as exc:
            message = _safe_error(exc, operation)
            if generation == self._generation:
                self._state, self._message = "error", message
                if type(exc).__name__ in {"Unauthorized", "AccountLocked", "AccountSuspended"}:
                    await self._drop_client()
            raise XConnectorError(message) from None

    async def _pages(self, first: Awaitable, limit: int, operation: str, generation: int) -> list[Any]:
        result = await self._call(first, operation, generation)
        items: list[Any] = []
        seen: set[str] = set()
        cursors: set[str] = set()
        for page_number in range(self.MAX_PAGES):
            page = list(result)
            for item in page:
                key = str(_get(item, "id", ""))
                if key and key not in seen:
                    seen.add(key)
                    items.append(item)
                if len(items) >= limit:
                    return items
            cursor = _get(result, "next_cursor")
            if not page or not cursor or str(cursor) in cursors or page_number + 1 >= self.MAX_PAGES:
                break
            cursors.add(str(cursor))
            if not callable(getattr(result, "next", None)):
                break
            result = await self._call(result.next(), operation, generation)
        return items

    async def collect(
        self, channel: str, query: str = "", authors: list[str] | None = None, limit: int = 40
    ) -> list[dict[str, Any]]:
        if channel not in {"search", "following", "recommended"}:
            raise ValueError("不支持的 X 采集频道。")
        if channel == "search" and not query.strip():
            raise ValueError("X 关键词采集需要提供搜索词。")
        limit = max(1, min(int(limit), self.MAX_POSTS))
        async with self._request_lock:
            client = await self._ensure_client()
            generation = self._generation
            if channel == "search":
                first = client.search_tweet(query.strip(), "Latest", count=min(limit, 20))
                tweets = await self._pages(first, limit, "搜索 X 帖子", generation)
            elif channel == "recommended":
                tweets = await self._pages(client.get_timeline(count=min(limit, 40)), limit, "采集 X 推荐流", generation)
            else:
                handles = list(dict.fromkeys(handle.strip().lstrip("@") for handle in (authors or []) if handle.strip()))
                if any(not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) for handle in handles):
                    raise ValueError("X 作者需填写有效用户名，例如 naval。")
                # Reserve 60% for the personal Following timeline, including
                # reposts. Imported authors supplement it; they never replace it.
                timeline_budget = max(1, limit * 3 // 5) if handles else limit
                timeline = await self._pages(
                    client.get_latest_timeline(count=min(timeline_budget, 40)),
                    timeline_budget, "采集 X 关注流", generation,
                )
                merged = {str(_get(tweet, "id")): tweet for tweet in timeline}
                selected_handles = handles[:50]
                for index, handle in enumerate(selected_handles):
                    remaining = limit - len(merged)
                    if remaining <= 0:
                        break
                    authors_left = len(selected_handles) - index
                    quota = max(1, (remaining + authors_left - 1) // authors_left)
                    try:
                        user = await self._call(client.get_user_by_screen_name(handle), "查询 X 作者", generation)
                        batch = await self._pages(
                            client.get_user_tweets(str(_get(user, "id")), "Tweets", count=min(quota, 40)),
                            quota, "采集 X 作者帖子", generation,
                        )
                    except XConnectorError as exc:
                        # The caller receives an explicit failed collection,
                        # rather than silently accepting a partial author import.
                        raise XConnectorError("本人关注流已读取，但作者补充未完成：" + str(exc)) from None
                    for tweet in batch:
                        merged.setdefault(str(_get(tweet, "id")), tweet)
                        if len(merged) >= limit:
                            break
                tweets = list(merged.values())
            posts: dict[str, dict] = {}
            for tweet in tweets:
                post = tweet_to_post(tweet, channel)
                posts.setdefault(post["external_id"], post)
                if len(posts) >= limit:
                    break
            self._assert_generation(generation)
            self._state = "connected"
            self._message = f"已采集 {len(posts)} 条 X 信息。"
            return list(posts.values())

    async def following_accounts(self, limit: int = 200) -> list[str]:
        limit = max(1, min(int(limit), 1000))
        async with self._request_lock:
            client = await self._ensure_client()
            generation = self._generation
            users = await self._pages(
                client.get_user_following(str(_get(self._user, "id")), count=min(limit, 40)),
                limit, "读取 X 关注列表", generation,
            )
            handles = [str(_get(user, "screen_name", "")).lstrip("@") for user in users]
            names = list(dict.fromkeys(handle for handle in handles if handle))
            self._state = "connected"
            self._message = f"已读取 {len(names)} 个 X 关注账号。"
            return names
