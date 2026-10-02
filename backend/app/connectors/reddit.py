from __future__ import annotations

import asyncio
import secrets
import time
import threading
from datetime import datetime, timezone

import praw

from ..security import SecretStore, safe_error, strip_html


class RedditNotConnected(RuntimeError):
    pass


class RedditConnector:
    def __init__(self, secrets_store: SecretStore):
        self.secrets = secrets_store
        self.lock = threading.RLock()
        self.generation = self.secrets.get("reddit_oauth_generation", 0)

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
        options = dict(
            client_id=client_id,
            client_secret=self.secrets.get("reddit_client_secret") or None,
            redirect_uri=self.secrets.get("reddit_redirect_uri"),
            user_agent="desktop:market-radar:0.1 (personal local reader)",
            check_for_async=False,
            check_for_updates=False,
            requestor_kwargs={"timeout": 12},
        )
        if refresh_token:
            options["refresh_token"] = refresh_token
        return praw.Reddit(**options)

    def status(self):
        return {
            "status": "connected" if self.secrets.get("reddit_refresh_token") else "disconnected",
            "state": "connected" if self.secrets.get("reddit_refresh_token") else "disconnected",
            "configured": bool(self.secrets.get("reddit_client_id")),
            "username": self.secrets.get("reddit_username", ""),
            "message": "本人 OAuth 账号已连接" if self.secrets.get("reddit_refresh_token") else "使用 Reddit OAuth 授权本人账号",
            "redirect_uri": self.secrets.get("reddit_redirect_uri", "http://localhost:8787/api/connections/reddit/callback"),
        }

    def authorize(self):
        with self.lock:
            state = secrets.token_urlsafe(32)
            self.secrets.set("reddit_oauth_state", {"state": state, "expires_at": time.time() + 600, "generation": self.generation})
            client = self._client(False)
            try:
                return client.auth.url(scopes=["identity", "read", "mysubreddits", "history"], state=state, duration="permanent")
            finally:
                self._close(client)

    @staticmethod
    def _close(client):
        # Sync PRAW exposes closure through prawcore, unlike asyncpraw's Reddit.close().
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

        def exchange():
            client = self._client(False)
            try:
                token = client.auth.authorize(code)
                if not token:
                    raise RuntimeError("No refresh token")
                username = str(client.user.me())
                with self.lock:
                    if generation != self.generation:
                        raise ValueError("该 Reddit 授权已取消，请重新连接")
                    self.secrets.set("reddit_refresh_token", token)
                    self.secrets.set("reddit_username", username)
            finally:
                self._close(client)

        await asyncio.to_thread(exchange)

    def disconnect(self):
        with self.lock:
            self.generation += 1
            self.secrets.set("reddit_oauth_generation", self.generation)
            for name in ["reddit_refresh_token", "reddit_username", "reddit_oauth_state"]:
                self.secrets.delete(name)

    async def following_accounts(self):
        def collect():
            client = self._client()
            try:
                names = [sub.display_name for sub in client.user.subreddits(limit=300)]
                return {"authors": [name[2:] for name in names if name.startswith("u_")], "subreddits": [name for name in names if not name.startswith("u_")]}
            finally:
                self._close(client)
        return await asyncio.to_thread(collect)

    async def collect(self, channel: str, query: str, authors: list[str], subreddits: list[str], limit=75):
        def read():
            client = self._client()
            try:
                submissions, errors = [], []
                if channel == "search":
                    submissions.extend(client.subreddit("all").search(query, sort="new", time_filter="week", limit=limit))
                elif channel == "recommended":
                    # Reddit's authenticated best listing; not the web app's experimental Home recommendations.
                    submissions.extend(client.front.best(limit=limit))
                else:
                    submissions.extend(client.front.new(limit=limit))
                    for author in authors[:25]:
                        try:
                            submissions.extend(client.redditor(author).submissions.new(limit=40))
                        except Exception as error:
                            errors.append({"source": "reddit", "message": f"u/{author}: {safe_error(error, 'Reddit')}"})
                    if subreddits:
                        try:
                            submissions.extend(client.subreddit("+".join(subreddits[:50])).new(limit=limit))
                        except Exception as error:
                            errors.append({"source": "reddit", "message": safe_error(error, "Reddit 订阅社区")})
                unique = {post.id: post for post in submissions}
                posts = [{
                    "external_id": post.id, "source": "reddit", "source_name": f"r/{post.subreddit.display_name}",
                    "author": str(post.author) if post.author else "[deleted]", "title": post.title,
                    "content": strip_html(post.selftext or ""),
                    "url": "https://www.reddit.com" + post.permalink,
                    "published_at": datetime.fromtimestamp(post.created_utc, timezone.utc).isoformat(),
                    "score": post.score,
                    "metrics": {"score": post.score, "comments": post.num_comments, "upvote_ratio": post.upvote_ratio},
                } for post in unique.values()]
                return posts, errors
            finally:
                self._close(client)
        return await asyncio.to_thread(read)
