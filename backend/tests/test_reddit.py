import time
import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.connectors.reddit import RedditConnector
from app.security import SecretStore


def test_oauth_state_is_secret_expiring_and_single_use(tmp_path):
    secrets = SecretStore(tmp_path)
    reddit = RedditConnector(secrets)
    secrets.set("reddit_oauth_state", {"state": "valid-state", "expires_at": time.time() + 100})
    with pytest.raises(ValueError):
        reddit.consume_state("attacker-state")
    reddit.consume_state("valid-state")
    with pytest.raises(ValueError):
        reddit.consume_state("valid-state")
    secrets.set("reddit_oauth_state", {"state": "expired", "expires_at": time.time() - 1})
    with pytest.raises(ValueError):
        reddit.consume_state("expired")


def test_reddit_status_does_not_expose_app_secret_or_refresh_token(tmp_path):
    secrets = SecretStore(tmp_path)
    secrets.set("reddit_client_secret", "NEVER_EXPOSE")
    secrets.set("reddit_refresh_token", "NEVER_EXPOSE_TOKEN")
    reddit = RedditConnector(secrets)
    assert "NEVER_EXPOSE" not in str(reddit.status())
    assert reddit.status()["status"] == "connected"
    reddit.disconnect()
    assert reddit.status()["status"] == "disconnected"


@pytest.mark.asyncio
async def test_reddit_following_keeps_nonmatching_posts_and_best_is_native(monkeypatch, tmp_path):
    record = SimpleNamespace(id="real-id", subreddit=SimpleNamespace(display_name="books"), author="writer", title="Novel review", selftext="No market keywords", permalink="/r/books/comments/real-id", created_utc=1700000000, score=2, num_comments=3, upvote_ratio=0.9)
    calls, closed = [], []
    def listing(kind):
        def read(**kwargs):
            calls.append(kind)
            return [record]
        return read
    client = SimpleNamespace(
        front=SimpleNamespace(new=listing("new"), best=listing("best")),
        _core=SimpleNamespace(close=lambda: closed.append(True)),
        redditor=lambda name: SimpleNamespace(submissions=SimpleNamespace(new=listing("author"))),
        subreddit=lambda name: SimpleNamespace(new=listing("subreddit")),
    )
    reddit = RedditConnector(SecretStore(tmp_path))
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    posts, errors = await reddit.collect("following", "Bitcoin", ["writer"], ["books"])
    assert len(posts) == 1 and posts[0]["title"] == "Novel review" and not errors
    assert calls == ["new", "author", "subreddit"]
    calls.clear()
    posts, errors = await reddit.collect("recommended", "", [], [])
    assert calls == ["best"] and posts
    assert len(closed) == 2


@pytest.mark.asyncio
async def test_oauth_exchange_verifies_account_and_closes_prawcore(monkeypatch, tmp_path):
    secrets = SecretStore(tmp_path)
    reddit = RedditConnector(secrets)
    secrets.set("reddit_oauth_state", {"state": "state", "expires_at": time.time() + 100})
    closed = []
    client = SimpleNamespace(auth=SimpleNamespace(authorize=lambda code: "SAFE_REFRESH_TOKEN"), user=SimpleNamespace(me=lambda: "real_user"), _core=SimpleNamespace(close=lambda: closed.append(True)))
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    await reddit.callback("one_time_code", "state")
    assert reddit.status()["username"] == "real_user"
    assert secrets.get("reddit_refresh_token") == "SAFE_REFRESH_TOKEN"
    assert closed == [True]


@pytest.mark.asyncio
async def test_disconnect_cancels_pending_oauth_commit(monkeypatch, tmp_path):
    secrets = SecretStore(tmp_path)
    reddit = RedditConnector(secrets)
    secrets.set("reddit_oauth_state", {"state": "pending", "expires_at": time.time() + 100, "generation": reddit.generation})
    started, proceed = threading.Event(), threading.Event()
    def authorize(code):
        started.set()
        assert proceed.wait(3)
        return "STALE_REFRESH_TOKEN"
    client = SimpleNamespace(auth=SimpleNamespace(authorize=authorize), user=SimpleNamespace(me=lambda: "old_user"), _core=SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    callback = asyncio.create_task(reddit.callback("code", "pending"))
    assert await asyncio.to_thread(started.wait, 2)
    reddit.disconnect()
    proceed.set()
    with pytest.raises(ValueError):
        await callback
    assert secrets.get("reddit_refresh_token") is None
    assert reddit.status()["status"] == "disconnected"
