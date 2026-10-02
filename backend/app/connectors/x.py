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
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    from twikit import Client
except ImportError:  # Other sources still work before optional X setup.
    Client = None  # type: ignore[assignment]


class MissingCredentials(RuntimeError):
    """The user has not connected their X account."""


class XConnectorError(RuntimeError):
    """Safe provider error; deliberately excludes upstream request/response text."""


class XAuthenticationError(XConnectorError):
    """Authentication failures cannot be downgraded to partial author results."""


class XCancelledError(XConnectorError):
    """A disconnect invalidated an in-flight operation."""


class XRateLimitError(XConnectorError):
    """An endpoint is cooling down; no automatic sleep or retry is performed."""


def _status_code(exc: Exception) -> Any:
    return getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)


def _is_authentication_error(exc: Exception) -> bool:
    return isinstance(exc, XAuthenticationError) or type(exc).__name__ in {
        "Unauthorized", "Forbidden", "AccountLocked", "AccountSuspended"
    } or _status_code(exc) in {401, 403}


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
    SESSION_VERIFY_INTERVAL = 900.0
    USER_ID_CACHE_TTL = 86400.0
    DEFAULT_COOLDOWN = 60.0
    MAX_COOLDOWN = 86400.0
    MAX_AUTHORS = 50
    MAX_AUTHOR_PAGES = 3
    CHECKPOINT_KEY = "x.capture"

    def __init__(self, secrets: Any, data_dir: Path, store: Any = None):
        self.secrets = secrets
        self.data_dir = Path(data_dir)
        self.store = store
        self._client: Any = None
        self._user: Any = None
        self._login_task: asyncio.Task | None = None
        self._client_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._generation = 0
        self._last_validation_attempt = 0.0
        self._verified_monotonic = 0.0
        self._last_verified_at: str | None = None
        self._last_success: str | None = None
        self._last_error: str | None = None
        self._truncated = False
        self._warnings: list[dict[str, str]] = []
        saved = self.store.get_checkpoint(self.CHECKPOINT_KEY) if self.store is not None else None
        saved = saved if isinstance(saved, dict) else {}
        self._author_offset = _count(saved.get("author_offset"))
        self._user_ids = saved.get("user_ids", {}) if isinstance(saved.get("user_ids"), dict) else {}
        self._cooldowns: dict[str, float] = {}
        cooldowns = saved.get("cooldowns", {})
        for endpoint, until in (cooldowns if isinstance(cooldowns, dict) else {}).items():
            if isinstance(endpoint, str) and isinstance(until, (int, float)) and time.time() < until <= time.time() + self.MAX_COOLDOWN:
                self._cooldowns[endpoint] = float(until)
        self._state = "disconnected"
        self._message = "尚未连接 X 账号。"
        self._username: str | None = None

    def _snapshot(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "username": self._username,
            "message": self._message,
            "configured": bool(self.secrets.get("x.cookies")),
            "last_verified_at": self._last_verified_at,
            "last_success": self._last_success,
            "last_error": self._last_error,
            "truncated": self._truncated,
            "warnings": list(self._warnings),
            "cooldowns": dict(self._cooldowns),
        }

    def _assert_generation(self, generation: int) -> None:
        if self._generation != generation:
            raise XCancelledError("X 连接操作已取消，请重新发起。")

    def _persist_capture_state(self) -> None:
        if self.store is not None:
            self.store.save_checkpoint(self.CHECKPOINT_KEY, {
                "author_offset": self._author_offset,
                "user_ids": dict(self._user_ids),
                "cooldowns": dict(self._cooldowns),
            })

    def _verified(self) -> None:
        self._verified_monotonic = time.monotonic()
        self._last_verified_at = datetime.now(timezone.utc).isoformat()

    def _cooldown_until(self, exc: Exception) -> float:
        now = time.time()
        headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
        reset = getattr(exc, "rate_limit_reset", None) or headers.get("x-rate-limit-reset")
        retry = getattr(exc, "retry_after", None) or headers.get("retry-after") or headers.get("Retry-After")
        until = now + self.DEFAULT_COOLDOWN
        try:
            if reset is not None and float(reset) > now:
                until = float(reset)
            elif retry is not None:
                try:
                    until = now + max(1.0, float(retry))
                except (TypeError, ValueError):
                    until = parsedate_to_datetime(str(retry)).timestamp()
        except (TypeError, ValueError, OverflowError):
            pass
        return max(now + 1, min(until, now + self.MAX_COOLDOWN))

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
            user = await self._call(lambda: client.user(), "验证 X 会话", generation, "identity")
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
        self._last_error = None
        self._verified()
        return client

    async def _ensure_client(self) -> Any:
        if self._client is not None and time.monotonic() - self._verified_monotonic < self.SESSION_VERIFY_INTERVAL:
            return self._client
        async with self._client_lock:
            if self._client is not None:
                if time.monotonic() - self._verified_monotonic >= self.SESSION_VERIFY_INTERVAL:
                    self._last_validation_attempt = time.monotonic()
                    user = await self._call(lambda: self._client.user(), "重新验证 X 会话", self._generation, "identity")
                    if not _get(user, "id") or not _get(user, "screen_name"):
                        self._state = "error"
                        self._last_error = self._message = "X 未返回有效账号身份，会话尚未确认可用。"
                        await self._drop_client()
                        raise XAuthenticationError(self._message)
                    self._user = user
                    self._username = str(_get(user, "screen_name"))
                    self._verified()
                    self._state = "connected"
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
                    self._last_error = str(exc)
                raise
            except Exception as exc:
                if generation == self._generation:
                    self._state = "error"
                    self._message = _safe_error(exc, "验证 X 会话")
                    self._last_error = self._message
                raise XConnectorError(_safe_error(exc, "验证 X 会话")) from None

    async def status(self) -> dict[str, Any]:
        if self._login_task and not self._login_task.done():
            return self._snapshot()
        if not self.secrets.get("x.cookies"):
            return self._snapshot()
        if (self._client is None or time.monotonic() - self._verified_monotonic >= self.SESSION_VERIFY_INTERVAL) and (
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
                    self._last_error = self._message
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
        self._cooldowns.clear()
        self._author_offset = 0
        self._user_ids.clear()
        self._persist_capture_state()
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
                self._last_error = self._message
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
        self._verified_monotonic = 0
        self._last_verified_at = self._last_success = self._last_error = None
        self._truncated = False
        self._warnings = []
        self._cooldowns.clear()
        self._user_ids.clear()
        self._author_offset = 0
        self._persist_capture_state()
        return self._snapshot()

    async def shutdown(self) -> None:
        self._generation += 1
        await self._cancel_login()
        await self._drop_client()

    async def _call(
        self, request: Callable[[], Awaitable] | Awaitable, operation: str,
        generation: int, endpoint: str,
    ) -> Any:
        self._assert_generation(generation)
        until = self._cooldowns.get(endpoint, 0)
        if until > time.time():
            # Call sites use factories, so skipped requests create no coroutine.
            if not callable(request) and callable(getattr(request, "close", None)):
                request.close()
            seconds = max(1, int(until - time.time()) + 1)
            raise XRateLimitError(f"{operation}暂缓：X 端点处于 429 冷却期，请约 {seconds} 秒后再试。")
        try:
            result = await asyncio.wait_for(request() if callable(request) else request, timeout=self.REQUEST_TIMEOUT)
            self._assert_generation(generation)
            if endpoint in self._cooldowns:
                self._cooldowns.pop(endpoint, None)
                self._persist_capture_state()
            return result
        except XConnectorError:
            raise
        except Exception as exc:
            message = _safe_error(exc, operation)
            if generation == self._generation:
                self._state, self._message = "error", message
                self._last_error = message
                if type(exc).__name__ == "TooManyRequests" or _status_code(exc) == 429:
                    self._cooldowns[endpoint] = self._cooldown_until(exc)
                    self._persist_capture_state()
                if _is_authentication_error(exc):
                    self._state, self._message = "error", message
                    await self._drop_client()
                    raise XAuthenticationError(message) from None
            if type(exc).__name__ == "TooManyRequests" or _status_code(exc) == 429:
                raise XRateLimitError(message) from None
            raise XConnectorError(message) from None

    @staticmethod
    def _warning(message: str, code: str = "partial") -> dict[str, str]:
        return {"source": "x", "message": message, "code": code}

    async def _pages(
        self, first: Callable[[], Awaitable], limit: int, operation: str,
        generation: int, endpoint: str, exclude: set[str] | None = None,
        max_pages: int | None = None,
    ) -> tuple[list[Any], list[dict[str, str]]]:
        result = await self._call(first, operation, generation, endpoint)
        items: list[Any] = []
        seen = set(exclude or ())
        cursors: set[str] = set()
        warnings: list[dict[str, str]] = []
        page_limit = min(self.MAX_PAGES, max_pages or self.MAX_PAGES)
        for page_number in range(page_limit):
            page = list(result)
            cursor = _get(result, "next_cursor")
            for index, item in enumerate(page):
                key = str(_get(item, "id", ""))
                if key and key not in seen:
                    seen.add(key)
                    items.append(item)
                if len(items) >= limit:
                    if cursor or any(str(_get(rest, "id", "")) not in seen for rest in page[index + 1:]):
                        warnings.append(self._warning(f"{operation}达到本次数量上限，仅保存有限采样。", "truncated"))
                    return items, warnings
            if not cursor:
                break
            if not page or str(cursor) in cursors or page_number + 1 >= page_limit:
                warnings.append(self._warning(f"{operation}分页已停止（空页、重复游标或页数上限），结果可能不完整。", "truncated"))
                break
            cursors.add(str(cursor))
            if not callable(getattr(result, "next", None)):
                warnings.append(self._warning(f"{operation}有下一页游标但无法翻页，结果可能不完整。", "truncated"))
                break
            try:
                result = await self._call(result.next, operation, generation, endpoint)
            except (XAuthenticationError, XCancelledError):
                raise
            except XConnectorError as exc:
                warnings.append(self._warning(f"{operation}后续页未完成：{exc}"))
                break
        return items, warnings

    async def _author_id(self, client: Any, handle: str, generation: int) -> str:
        cached = self._user_ids.get(handle.lower(), {})
        if isinstance(cached, dict) and cached.get("user_id") and isinstance(cached.get("cached_at"), (int, float)) and 0 <= time.time() - cached["cached_at"] < self.USER_ID_CACHE_TTL:
            return str(cached["user_id"])
        user = await self._call(lambda: client.get_user_by_screen_name(handle), "查询 X 作者", generation, "user_by_screen_name")
        user_id = str(_get(user, "id", "") or "")
        if not user_id:
            raise XConnectorError("X 作者查询未返回有效 ID。")
        self._user_ids[handle.lower()] = {"user_id": user_id, "cached_at": time.time()}
        if len(self._user_ids) > 1000:
            oldest = next(iter(self._user_ids))
            self._user_ids.pop(oldest, None)
        self._persist_capture_state()
        return user_id

    async def collect(
        self, channel: str, query: str = "", authors: list[str] | None = None, limit: int = 40
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        if channel not in {"search", "following", "recommended"}:
            raise ValueError("不支持的 X 采集频道。")
        if channel == "search" and not query.strip():
            raise ValueError("X 关键词采集需要提供搜索词。")
        limit = max(1, min(int(limit), self.MAX_POSTS))
        async with self._request_lock:
            client = await self._ensure_client()
            generation = self._generation
            warnings: list[dict[str, str]] = []
            if channel == "search":
                tweets, warnings = await self._pages(
                    lambda: client.search_tweet(query.strip(), "Latest", count=min(limit, 20)),
                    limit, "搜索 X 帖子", generation, "search",
                )
            elif channel == "recommended":
                tweets, warnings = await self._pages(
                    lambda: client.get_timeline(count=min(limit, 40)), limit,
                    "采集 X 推荐流", generation, "home_timeline",
                )
            else:
                handles = list(dict.fromkeys(handle.strip().lstrip("@").lower() for handle in (authors or []) if handle.strip()))
                if any(not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) for handle in handles):
                    raise ValueError("X 作者需填写有效用户名，例如 naval。")
                # Reserve 60% for the personal Following timeline, including
                # reposts. Imported authors supplement it; they never replace it.
                timeline_budget = max(1, limit * 3 // 5) if handles else limit
                timeline, warnings = await self._pages(
                    lambda: client.get_latest_timeline(count=min(timeline_budget, 40)),
                    timeline_budget, "采集 X 关注流", generation, "home_latest_timeline",
                )
                merged = {str(_get(tweet, "id")): tweet for tweet in timeline}
                start = self._author_offset % len(handles) if handles else 0
                rotated = handles[start:] + handles[:start]
                selected_handles = rotated[:min(self.MAX_AUTHORS, max(0, limit - len(merged)))]
                attempted = 0
                for index, handle in enumerate(selected_handles):
                    remaining = limit - len(merged)
                    if remaining <= 0:
                        break
                    authors_left = len(selected_handles) - index
                    quota = max(1, (remaining + authors_left - 1) // authors_left)
                    attempted += 1
                    self._author_offset = (start + attempted) % len(handles)
                    self._persist_capture_state()
                    try:
                        if self._cooldowns.get("user_tweets", 0) > time.time():
                            raise XRateLimitError("X 作者帖子端点仍处于 429 冷却期，请稍后再试。")
                        user_id = await self._author_id(client, handle, generation)
                        batch, author_warnings = await self._pages(
                            lambda: client.get_user_tweets(user_id, "Tweets", count=min(quota, 40)),
                            quota, f"采集 X 作者 @{handle} 帖子", generation, "user_tweets", set(merged),
                            max_pages=self.MAX_AUTHOR_PAGES,
                        )
                        warnings.extend(author_warnings)
                    except (XAuthenticationError, XCancelledError):
                        raise
                    except XConnectorError as exc:
                        warnings.append(self._warning(f"作者 @{handle} 补充未完成：{exc}"))
                        continue
                    for tweet in batch:
                        merged.setdefault(str(_get(tweet, "id")), tweet)
                        if len(merged) >= limit:
                            break
                if attempted < len(handles):
                    warnings.append(self._warning(f"本轮仅处理 {attempted}/{len(handles)} 个指定作者，其余将在后续采集轮转。", "truncated"))
                tweets = list(merged.values())
            posts: dict[str, dict] = {}
            for tweet in tweets:
                try:
                    post = tweet_to_post(tweet, channel)
                except XConnectorError as exc:
                    warnings.append(self._warning(str(exc)))
                    continue
                posts.setdefault(post["external_id"], post)
                if len(posts) >= limit:
                    break
            self._assert_generation(generation)
            # Bind results to the identity validated for this collection, with
            # no await between the generation guard and returning the payload.
            for post in posts.values():
                post["account_id"] = self._username or ""
            self._state = "connected"
            self._warnings = warnings
            self._truncated = any(warning["code"] == "truncated" for warning in warnings)
            self._last_success = datetime.now(timezone.utc).isoformat()
            partial = next((warning["message"] for warning in warnings if warning["code"] == "partial"), None)
            self._last_error = partial
            self._message = f"已采集 {len(posts)} 条 X 信息。" + ("存在部分失败或采样截断，详情见采集警告。" if warnings else "")
            return list(posts.values()), warnings

    async def following_accounts(self, limit: int = 200) -> list[str]:
        limit = max(1, min(int(limit), 1000))
        async with self._request_lock:
            client = await self._ensure_client()
            generation = self._generation
            users, warnings = await self._pages(
                lambda: client.get_user_following(str(_get(self._user, "id")), count=min(limit, 40)),
                limit, "读取 X 关注列表", generation, "following",
            )
            handles = [str(_get(user, "screen_name", "")).lstrip("@") for user in users]
            names = list(dict.fromkeys(handle for handle in handles if handle))
            self._state = "connected"
            self._message = f"已读取 {len(names)} 个 X 关注账号。"
            self._warnings = warnings
            self._truncated = any(w["code"] == "truncated" for w in warnings)
            self._last_success = datetime.now(timezone.utc).isoformat()
            self._last_error = next((w["message"] for w in warnings if w["code"] == "partial"), None)
            return names
