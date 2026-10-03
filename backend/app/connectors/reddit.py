from __future__ import annotations

import asyncio
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any

import praw
from prawcore import Requestor

from ..security import SecretStore, safe_error, strip_html
from ..deployment import LOCAL_CALLBACK


def _now():
    return datetime.now(timezone.utc).isoformat()


class RedditNotConnected(RuntimeError):
    pass


class RedditCancelled(ValueError):
    pass


class RedditBudgetExceeded(RuntimeError):
    pass


class _Budget:
    """Guards every HTTP request and every listing item, including worker threads."""
    def __init__(self, connector, seconds, requests):
        self.connector, self.generation = connector, connector.generation
        self.cancelled = threading.Event()
        self.deadline = time.monotonic() + seconds
        self.maximum, self.requests = requests, 0
        try:
            self.task = asyncio.current_task()
        except RuntimeError:
            self.task = None

    def check(self):
        if self.cancelled.is_set() or self.generation != self.connector.generation or (self.task and self.task.cancelling()):
            raise RedditCancelled("该 Reddit 操作已取消，未继续读取或保存结果")
        if time.monotonic() >= self.deadline:
            raise RedditBudgetExceeded("Reddit 单轮时间预算已用完，保留已取得的内容")

    def before_request(self):
        self.check()
        if self.requests >= self.maximum:
            raise RedditBudgetExceeded("Reddit 单轮请求预算已用完，保留已取得的内容")
        self.requests += 1

    def wait(self, seconds):
        until = time.monotonic() + max(0, seconds)
        while time.monotonic() < until:
            self.check()
            self.cancelled.wait(min(0.1, until - time.monotonic()))
        self.check()


class RedditConnector:
    MAX_POSTS = 200
    MAX_REQUESTS = 32
    MAX_AUTHOR_STREAMS = 20
    RUN_TIMEOUT = 75.0
    VERIFY_INTERVAL = 60.0

    def __init__(self, secrets_store: SecretStore, store: Any = None, redirect_uri: str | None = None):
        self.secrets, self.store = secrets_store, store
        self.redirect_uri = redirect_uri
        self.lock, self._request_lock = threading.RLock(), threading.Lock()
        self._local = threading.local()
        self._checkpoints = {}
        self.generation = self.secrets.get("reddit_oauth_generation", 0)
        self._state = "connecting" if self.secrets.get("reddit_refresh_token") else "disconnected"
        self._message = "会话已保存，等待真实账号验证" if self._state == "connecting" else "使用 Reddit OAuth 授权本人账号"
        self._verified_monotonic = self._verification_attempt = 0.0
        self.last_verified_at = self.last_success = self.last_error = None
        self.truncated = False
        self._next_request_at = 0.0

    def _checkpoint(self, key):
        return (self.store.get_checkpoint(key) or {}) if self.store else self._checkpoints.get(key, {})

    def _save_checkpoint(self, key, value):
        if self.store:
            self.store.save_checkpoint(key, value)
        else:
            self._checkpoints[key] = value

    async def _thread(self, function, budget):
        def worker():
            acquired = False
            try:
                while not acquired:
                    budget.check()
                    acquired = self._request_lock.acquire(timeout=0.1)
                self._local.budget = budget
                budget.check()
                return function()
            finally:
                self._local.budget = None
                if acquired:
                    self._request_lock.release()
        try:
            return await asyncio.to_thread(worker)
        except asyncio.CancelledError:
            # An in-flight request finishes with its HTTP timeout; the event
            # prevents any following request/item or stale result commit.
            budget.cancelled.set()
            raise

    def config(self, client_id: str, client_secret: str | None, redirect_uri: str):
        with self.lock:
            self.disconnect()
            self.secrets.set("reddit_client_id", client_id)
            if client_secret is not None:
                self.secrets.set("reddit_client_secret", client_secret)
            self.secrets.set("reddit_redirect_uri", redirect_uri)

    def _client(self, authenticated=True):
        client_id = self.secrets.get("reddit_client_id")
        if not client_id:
            raise RedditNotConnected("请先配置 Reddit OAuth 应用")
        refresh_token = self.secrets.get("reddit_refresh_token") if authenticated else None
        if authenticated and not refresh_token:
            raise RedditNotConnected("请先连接本人 Reddit 账号")
        budget = getattr(self._local, "budget", None)

        class BudgetedRequestor(Requestor):
            def request(self, *args, **kwargs):
                if budget:
                    budget.wait(self_connector._next_request_at - time.time())
                    budget.before_request()
                    kwargs["timeout"] = max(0.1, min(12.0, budget.deadline - time.monotonic()))
                response = super().request(*args, **kwargs)
                try:
                    headers = response.headers
                    if float(headers.get("x-ratelimit-remaining", "1")) <= 0:
                        self_connector._next_request_at = time.time() + max(0, float(headers.get("x-ratelimit-reset", "60")))
                except (ValueError, TypeError):
                    pass
                if budget:
                    budget.check()
                return response

        self_connector = self
        contact = self.secrets.get("reddit_contact_username") or self.secrets.get("reddit_username")
        agent = f"desktop:market-radar:0.2 (by /u/{contact})" if contact else "desktop:market-radar:0.2 (local reader; contact username not configured)"
        options = dict(client_id=client_id, client_secret=self.secrets.get("reddit_client_secret") or None,
            redirect_uri=self.secrets.get("reddit_redirect_uri"), user_agent=agent,
            check_for_async=False, check_for_updates=False, requestor_class=BudgetedRequestor,
            requestor_kwargs={"timeout": 12})
        if refresh_token:
            options["refresh_token"] = refresh_token
        client = praw.Reddit(**options)
        if budget:
            # PRAW 7's limiter otherwise sleeps in one uninterruptible block.
            # Preserve its header/update policy, but bound and interrupt waiting.
            for core_name in ("_core", "_authorized_core", "_read_only_core"):
                limiter = getattr(getattr(client, core_name, None), "_rate_limiter", None)
                if limiter is not None:
                    def delay(limiter=limiter):
                        budget.wait((limiter.next_request_timestamp or time.time()) - time.time())
                    limiter.delay = delay
        return client

    def status(self):
        with self.lock:
            has_token = bool(self.secrets.get("reddit_refresh_token"))
            state = self._state if has_token else "disconnected"
            return {"status": state, "state": state,
                "configured": bool(self.secrets.get("reddit_client_id")),
                "username": self.secrets.get("reddit_username", ""),
                "message": self._message if has_token else "使用 Reddit OAuth 授权本人账号",
                "last_verified_at": self.last_verified_at, "last_success": self.last_success,
                "last_error": self.last_error, "truncated": self.truncated,
                "redirect_uri": self.redirect_uri or self.secrets.get("reddit_redirect_uri", LOCAL_CALLBACK)}

    def _validate_identity(self, client, budget):
        budget.check()
        username = str(client.user.me() or "")
        budget.check()
        if not username or username == "None":
            raise RedditNotConnected("Reddit 未返回有效本人账号，会话尚未验证")
        with self.lock:
            budget.check()
            self.secrets.set("reddit_username", username)
            self._state, self._message = "connected", f"已验证 u/{username} 的 Reddit OAuth 会话"
            self.last_verified_at = _now()
            self._verified_monotonic = time.monotonic()
            self._verification_attempt = self._verified_monotonic
            self.last_error = None
        return username

    def _failed(self, error, budget):
        with self.lock:
            if budget.generation == self.generation and not budget.cancelled.is_set():
                self.last_error = safe_error(error, "Reddit")
                self._state, self._message = "error", self.last_error

    async def verify_status(self):
        if not self.secrets.get("reddit_refresh_token"):
            return self.status()
        if self._verification_attempt and time.monotonic() - self._verification_attempt < self.VERIFY_INTERVAL:
            return self.status()
        self._verification_attempt = time.monotonic()
        budget = _Budget(self, 20, 4)
        def verify():
            client = self._client()
            try:
                self._validate_identity(client, budget)
            finally:
                self._close(client)
        try:
            await self._thread(verify, budget)
        except RedditCancelled:
            pass
        except Exception as error:
            self._failed(error, budget)
        return self.status()

    def authorize(self):
        with self.lock:
            if self.redirect_uri and self.secrets.get("reddit_redirect_uri") != self.redirect_uri:
                raise RedditNotConnected("The saved Reddit callback belongs to a different deployment. Configure your Reddit app using the callback URL shown in account settings.")
            state = secrets.token_urlsafe(32)
            self.secrets.set("reddit_oauth_state", {"state": state, "expires_at": time.time() + 600, "generation": self.generation})
            client = self._client(False)
            try:
                return client.auth.url(scopes=["identity", "read", "mysubreddits"], state=state, duration="permanent")
            finally:
                self._close(client)

    @staticmethod
    def _close(client):
        client._core.close()

    def consume_state(self, state: str):
        with self.lock:
            saved = self.secrets.get("reddit_oauth_state")
            if not saved or saved["expires_at"] < time.time() or saved.get("generation", 0) != self.generation or not secrets.compare_digest(saved["state"], state):
                raise ValueError("Reddit 授权状态无效或已过期，请重新发起连接")
            self.secrets.delete("reddit_oauth_state")
            return self.generation

    async def callback(self, code: str, state: str):
        generation = self.consume_state(state)
        budget = _Budget(self, 30, 5)
        budget.generation = generation
        def exchange():
            client = self._client(False)
            try:
                budget.check()
                token = client.auth.authorize(code)
                budget.check()
                if not token:
                    raise RuntimeError("Reddit 未返回长期授权，会话未保存")
                username = str(client.user.me() or "")
                if not username or username == "None":
                    raise RedditNotConnected("Reddit 未返回有效本人账号")
                with self.lock:
                    budget.check()
                    self.secrets.set("reddit_refresh_token", token)
                    self.secrets.set("reddit_username", username)
                    self._state, self._message = "connected", f"已验证 u/{username} 的 Reddit OAuth 会话"
                    self.last_verified_at = _now()
                    self._verified_monotonic = self._verification_attempt = time.monotonic()
                    self.last_error = None
            finally:
                self._close(client)
        await self._thread(exchange, budget)

    def disconnect(self):
        with self.lock:
            self.generation += 1
            self.secrets.set("reddit_oauth_generation", self.generation)
            for name in ["reddit_refresh_token", "reddit_username", "reddit_oauth_state"]:
                self.secrets.delete(name)
            self._state, self._message = "disconnected", "已断开 Reddit 账号"
            self.last_verified_at = self.last_success = self.last_error = None
            self._verified_monotonic = self._verification_attempt = 0.0
            self.truncated = False

    async def following_accounts(self):
        budget = _Budget(self, self.RUN_TIMEOUT, self.MAX_REQUESTS)
        def collect():
            client = self._client()
            try:
                self._validate_identity(client, budget)
                names = []
                for sub in client.user.subreddits(limit=301):
                    budget.check()
                    names.append(sub.display_name)
                    if len(names) >= 301:
                        break
                budget.check()
                with self.lock:
                    budget.check()
                    self.truncated = len(names) > 300
                return {"authors": [name[2:] for name in names[:300] if name.startswith("u_")],
                    "subreddits": [name for name in names[:300] if not name.startswith("u_")],
                    "truncated": len(names) > 300}
            finally:
                self._close(client)
        return await self._thread(collect, budget)

    @staticmethod
    def _post(post, channel):
        references = []
        # Missing optional attributes on a PRAW listing object trigger a lazy
        # detail fetch. Read the received payload only; comments stay on demand.
        payload = vars(post)
        for parent in payload.get("crosspost_parent_list", []) or []:
            if isinstance(parent, dict):
                permalink = parent.get("permalink", "")
                references.append({"type": "crosspost", "external_id": parent.get("id", ""),
                    "author": parent.get("author", "[deleted]"), "title": parent.get("title", ""),
                    "content": strip_html(parent.get("selftext", "")),
                    "url": "https://www.reddit.com" + permalink if permalink.startswith("/") else permalink})
        return {"external_id": post.id, "source": "reddit", "source_name": f"r/{post.subreddit.display_name}",
            "author": str(post.author) if post.author else "[deleted]", "title": post.title,
            "content": strip_html(post.selftext or ""), "url": "https://www.reddit.com" + post.permalink,
            "external_url": payload.get("url"), "references": references,
            "published_at": datetime.fromtimestamp(post.created_utc, timezone.utc).isoformat(),
            "collected_at": _now(), "score": post.score, "channels": [channel],
            "metrics": {"score": post.score, "comments": post.num_comments, "upvote_ratio": post.upvote_ratio}}

    async def collect(self, channel: str, query: str, authors: list[str], subreddits: list[str], limit=75):
        if channel not in {"search", "following", "recommended"}:
            raise ValueError("不支持的 Reddit 采集频道")
        if channel == "search" and not query.strip():
            raise ValueError("Reddit 关键词采集需要搜索词")
        limit = max(1, min(int(limit), self.MAX_POSTS))
        budget = _Budget(self, self.RUN_TIMEOUT, self.MAX_REQUESTS)
        def read():
            client = self._client()
            posts, errors, rotation = {}, [], {}
            truncated, attempted = False, 0
            rotation_key = "reddit.rotation." + self.secrets.get("reddit_username", "local")
            rotation = self._checkpoint(rotation_key)
            def take(factory, quota, label):
                nonlocal truncated
                if quota <= 0:
                    return
                taken = 0
                try:
                    budget.check()
                    # One lookahead reports truncation; no unbounded listing.
                    for post in factory(quota + 1):
                        budget.check()
                        if str(post.id) in posts:
                            continue
                        if taken >= quota or len(posts) >= limit:
                            truncated = True
                            break
                        posts[str(post.id)] = self._post(post, channel)
                        taken += 1
                except (RedditCancelled, RedditBudgetExceeded):
                    raise
                except Exception as error:
                    if type(error).__name__ in {"Unauthorized", "Forbidden", "InvalidToken", "OAuthException"}:
                        raise
                    errors.append({"source": "reddit", "code": "partial", "message": f"{label}: {safe_error(error, 'Reddit')}"})
            try:
                if not self._verified_monotonic or time.monotonic() - self._verified_monotonic >= self.VERIFY_INTERVAL:
                    self._validate_identity(client, budget)
                    rotation_key = "reddit.rotation." + self.secrets.get("reddit_username", "local")
                    rotation = self._checkpoint(rotation_key)
                if channel == "search":
                    take(lambda n: client.subreddit("all").search(query, sort="new", time_filter="week", limit=n), limit, "Reddit 搜索")
                elif channel == "recommended":
                    take(lambda n: client.front.best(limit=n), limit, "Reddit API Best")
                else:
                    handles = list(dict.fromkeys(a.strip().removeprefix("u/") for a in authors if a.strip()))
                    communities = list(dict.fromkeys(s.strip().removeprefix("r/") for s in subreddits if s.strip()))
                    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name) for name in handles + communities):
                        raise ValueError("Reddit 用户名或社区名无效")
                    front_budget = max(1, limit * 3 // 5) if handles or communities else limit
                    take(lambda n: client.front.new(limit=n), front_budget, "Reddit 关注首页")
                    community_budget = min(limit - len(posts), max(1, limit // 5)) if communities else 0
                    author_budget = max(0, limit - len(posts) - community_budget)
                    offset = int(rotation.get("author_offset", 0)) % len(handles) if handles else 0
                    selected = (handles[offset:] + handles[:offset])[:min(self.MAX_AUTHOR_STREAMS, author_budget)]
                    truncated = truncated or len(selected) < len(handles)
                    for index, author in enumerate(selected):
                        budget.check()
                        quota = max(1, (author_budget + len(selected) - index - 1) // (len(selected) - index))
                        before = len(posts)
                        attempted += 1
                        rotation["author_offset"] = (offset + attempted) % len(handles)
                        take(lambda n, a=author: client.redditor(a).submissions.new(limit=n), quota, f"u/{author}")
                        author_budget -= len(posts) - before
                    if communities and len(posts) < limit:
                        community_offset = int(rotation.get("community_offset", 0)) % len(communities)
                        group = (communities[community_offset:] + communities[:community_offset])[:50]
                        truncated = truncated or len(group) < len(communities)
                        take(lambda n: client.subreddit("+".join(group)).new(limit=n), limit - len(posts), "Reddit 订阅社区")
                        rotation["community_offset"] = (community_offset + len(group)) % len(communities)
                    rotation["author_offset"] = (offset + attempted) % len(handles) if handles else 0
                budget.check()
            except RedditBudgetExceeded as error:
                truncated = True
                errors.append({"source": "reddit", "code": "truncated", "message": str(error)})
            except RedditCancelled:
                raise
            except Exception as error:
                self._failed(error, budget)
                raise
            finally:
                self._close(client)
            if budget.cancelled.is_set() or budget.generation != self.generation or (budget.task and budget.task.cancelling()):
                raise RedditCancelled("该 Reddit 操作已取消，未交付旧账号结果")
            if truncated and not any(e["code"] == "truncated" for e in errors):
                errors.append({"source": "reddit", "code": "truncated", "message": "本轮按帖子和来源预算截断；未扫描的来源将在后续轮转采集"})
            with self.lock:
                if budget.generation != self.generation or budget.cancelled.is_set() or (budget.task and budget.task.cancelling()):
                    raise RedditCancelled("该 Reddit 操作已取消，未交付旧账号结果")
                if channel == "following":
                    self._save_checkpoint(rotation_key, rotation)
                self.truncated = truncated
                self.last_error = next((e["message"] for e in errors if e["code"] == "partial"), None)
                if posts or not errors:
                    self.last_success = _now()
                    self._state = "connected"
                elif self.last_error:
                    self._state = "error"
                self._message = f"已取得 {len(posts)} 条 Reddit 内容" + ("，本轮覆盖已截断" if truncated else "")
            return list(posts.values()), errors
        return await self._thread(read, budget)

    async def comments(self, post_id: str, limit: int = 20):
        post_id = post_id.removeprefix("t3_")
        if not re.fullmatch(r"[A-Za-z0-9]{1,12}", post_id):
            raise ValueError("Reddit 投稿 ID 无效")
        limit = max(1, min(int(limit), 50))
        budget = _Budget(self, 25, 6)
        def read():
            client = self._client()
            try:
                if not self._verified_monotonic or time.monotonic() - self._verified_monotonic >= self.VERIFY_INTERVAL:
                    self._validate_identity(client, budget)
                budget.check()
                submission = client.submission(id=post_id)
                submission.comment_sort, submission.comment_limit = "top", limit
                forest = submission.comments
                budget.check()
                forest.replace_more(limit=0)
                result = []
                for comment in forest.list():
                    budget.check()
                    if len(result) >= limit:
                        break
                    result.append({"external_id": str(comment.id), "parent_id": comment.parent_id,
                        "author": str(comment.author) if comment.author else "[deleted]",
                        "content": strip_html(comment.body), "url": "https://www.reddit.com" + comment.permalink,
                        "published_at": datetime.fromtimestamp(comment.created_utc, timezone.utc).isoformat(), "score": comment.score})
                budget.check()
                return result
            finally:
                self._close(client)
        return await self._thread(read, budget)
