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
    assert reddit.status()["status"] == "connecting"
    assert reddit.status()["last_verified_at"] is None
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
        user=SimpleNamespace(me=lambda: "owner"),
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


def post(number, **overrides):
    values = dict(id=str(number), subreddit=SimpleNamespace(display_name="books"), author="writer",
        title="An ordinary day", selftext="No market keywords", permalink=f"/r/books/comments/{number}",
        url="https://publisher.example/article", created_utc=1700000000, score=2,
        num_comments=3, upvote_ratio=0.9)
    values.update(overrides)
    return SimpleNamespace(**values)


class MemoryStore:
    def __init__(self):
        self.values = {}
    def get_checkpoint(self, key):
        return dict(self.values.get(key, {}))
    def save_checkpoint(self, key, value):
        self.values[key] = dict(value)


def fake_client(**overrides):
    values = dict(user=SimpleNamespace(me=lambda: "owner"), _core=SimpleNamespace(close=lambda: None),
        front=SimpleNamespace(new=lambda **kw: [], best=lambda **kw: []),
        redditor=lambda name: SimpleNamespace(submissions=SimpleNamespace(new=lambda **kw: [])),
        subreddit=lambda name: SimpleNamespace(new=lambda **kw: []))
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_verify_status_requires_identity_and_throttles_polling(monkeypatch, tmp_path):
    secrets = SecretStore(tmp_path)
    secrets.set("reddit_refresh_token", "PRIVATE")
    reddit = RedditConnector(secrets)
    calls = []
    client = fake_client(user=SimpleNamespace(me=lambda: calls.append("identity") or "owner"))
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    assert reddit.status()["state"] == "connecting"
    result = await reddit.verify_status()
    assert result["state"] == "connected" and result["last_verified_at"]
    await reddit.verify_status()
    assert calls == ["identity"]
    Unauthorized = type("Unauthorized", (Exception,), {})
    def rejected():
        raise Unauthorized("PRIVATE")
    client.user.me = rejected
    reddit._verification_attempt = 0
    result = await reddit.verify_status()
    assert result["state"] == "error" and "PRIVATE" not in str(result)


@pytest.mark.asyncio
async def test_following_global_budget_rotation_and_external_reference(monkeypatch, tmp_path):
    store = MemoryStore()
    reddit = RedditConnector(SecretStore(tmp_path), store)
    seen = []
    def author(name):
        seen.append(name)
        return SimpleNamespace(submissions=SimpleNamespace(new=lambda **kw: [post("a" + name)]))
    client = fake_client(front=SimpleNamespace(new=lambda **kw: [post(i) for i in range(100)]), redditor=author)
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    handles = [f"writer{i}" for i in range(60)]
    first, warnings = await reddit.collect("following", "crypto", handles, [], limit=10)
    assert len(first) <= 10 and len(seen) == 4
    assert any(w["code"] == "truncated" for w in warnings)
    assert first[0]["external_url"] == "https://publisher.example/article"
    assert first[0]["content"] == "No market keywords"
    first_authors = seen[:]
    seen.clear()
    restored = RedditConnector(reddit.secrets, store)
    monkeypatch.setattr(restored, "_client", lambda authenticated=True: client)
    await restored.collect("following", "", handles, [], limit=10)
    assert not set(first_authors) & set(seen)
    assert all("watermark" not in value and "since_id" not in value for value in store.values.values())
    crosspost = post("x", crosspost_parent_list=[{"id": "parent", "author": "original", "title": "Original", "permalink": "/r/news/comments/parent", "selftext": "Source"}])
    mapped = reddit._post(crosspost, "following")
    assert mapped["references"][0]["type"] == "crosspost"
    assert mapped["references"][0]["url"] == "https://www.reddit.com/r/news/comments/parent"


@pytest.mark.asyncio
async def test_author_failure_keeps_following_posts_with_warning(monkeypatch, tmp_path):
    reddit = RedditConnector(SecretStore(tmp_path))
    def failing_author(name):
        raise RuntimeError("not available")
    client = fake_client(front=SimpleNamespace(new=lambda **kw: [post("front")]), redditor=failing_author)
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    posts, warnings = await reddit.collect("following", "irrelevant", ["writer"], [], limit=5)
    assert [p["external_id"] for p in posts] == ["front"]
    assert warnings[0]["code"] == "partial"


@pytest.mark.asyncio
async def test_request_budget_counts_actual_requestor_calls(monkeypatch, tmp_path):
    from app.connectors.reddit import _Budget, RedditBudgetExceeded
    from prawcore import Requestor
    reddit = RedditConnector(SecretStore(tmp_path))
    reddit.secrets.set("reddit_client_id", "test-id")
    reddit.secrets.set("reddit_refresh_token", "test-refresh")
    calls = []
    monkeypatch.setattr(Requestor, "request", lambda *args, **kw: calls.append(kw["timeout"]) or SimpleNamespace(headers={}))
    def make(**kw):
        requestor = kw["requestor_class"].__new__(kw["requestor_class"])
        return SimpleNamespace(requestor=requestor)
    monkeypatch.setattr("app.connectors.reddit.praw.Reddit", make)
    budget = _Budget(reddit, 20, 2)
    def work():
        requestor = reddit._client().requestor
        requestor.request("GET", "https://oauth.reddit.com/test")
        requestor.request("GET", "https://oauth.reddit.com/test")
        requestor.request("GET", "https://oauth.reddit.com/test")
    with pytest.raises(RedditBudgetExceeded):
        await reddit._thread(work, budget)
    assert len(calls) == 2 and all(0 < t <= 12 for t in calls)


@pytest.mark.asyncio
async def test_time_budget_preserves_received_posts(monkeypatch, tmp_path):
    reddit = RedditConnector(SecretStore(tmp_path))
    reddit.RUN_TIMEOUT = 0.02
    def slow(**kwargs):
        yield post("first")
        time.sleep(0.04)
        yield post("late")
    client = fake_client(front=SimpleNamespace(new=slow))
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    posts, warnings = await reddit.collect("following", "", [], [])
    assert [p["external_id"] for p in posts] == ["first"]
    assert warnings[0]["code"] == "truncated"


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect", [False, True])
async def test_cancelled_or_disconnected_worker_stops_before_next_source(monkeypatch, tmp_path, disconnect):
    from app.connectors.reddit import RedditCancelled
    reddit = RedditConnector(SecretStore(tmp_path))
    started, release, closed = threading.Event(), threading.Event(), threading.Event()
    authors = []
    def slow(**kwargs):
        started.set()
        assert release.wait(3)
        yield post("late")
    client = fake_client(front=SimpleNamespace(new=slow),
        redditor=lambda name: authors.append(name), _core=SimpleNamespace(close=closed.set))
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    task = asyncio.create_task(reddit.collect("following", "", ["writer"], []))
    assert await asyncio.to_thread(started.wait, 2)
    if disconnect:
        reddit.disconnect()
    else:
        task.cancel()
    release.set()
    with pytest.raises(RedditCancelled if disconnect else asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(closed.wait, 2)
    assert not authors and reddit.last_success is None


@pytest.mark.asyncio
async def test_comments_are_bounded_and_preserve_parent_and_original_link(monkeypatch, tmp_path):
    reddit = RedditConnector(SecretStore(tmp_path))
    replaced = []
    comments = [SimpleNamespace(id=str(i), parent_id="t3_abc", author=None if i == 0 else "writer",
        body="A discussion", permalink=f"/r/books/comments/abc/_/{i}", created_utc=1700000000, score=3) for i in range(70)]
    forest = SimpleNamespace(replace_more=lambda **kw: replaced.append(kw), list=lambda: comments)
    submission = SimpleNamespace(comments=forest)
    client = fake_client(submission=lambda **kw: submission)
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    result = await reddit.comments("t3_abc", limit=20)
    assert len(result) == 20 and submission.comment_limit == 20
    assert replaced == [{"limit": 0}]
    assert result[0]["parent_id"] == "t3_abc" and result[0]["author"] == "[deleted]"
    assert result[0]["url"] == "https://www.reddit.com/r/books/comments/abc/_/0"
    with pytest.raises(ValueError):
        await reddit.comments("https://bad.example/")


@pytest.mark.asyncio
async def test_rate_limit_reset_wait_obeys_total_time_budget(monkeypatch, tmp_path):
    from app.connectors.reddit import _Budget, RedditBudgetExceeded
    from prawcore import Requestor
    reddit = RedditConnector(SecretStore(tmp_path))
    reddit.secrets.set("reddit_client_id", "test-id")
    reddit.secrets.set("reddit_refresh_token", "test-refresh")
    calls = []
    def response(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "600"})
    monkeypatch.setattr(Requestor, "request", response)
    def make(**kw):
        cls = kw["requestor_class"]
        return SimpleNamespace(requestor=cls.__new__(cls))
    monkeypatch.setattr("app.connectors.reddit.praw.Reddit", make)
    budget = _Budget(reddit, 0.03, 5)
    started = time.monotonic()
    def work():
        requestor = reddit._client().requestor
        requestor.request("GET", "https://oauth.reddit.com/test")
        requestor.request("GET", "https://oauth.reddit.com/test")
    with pytest.raises(RedditBudgetExceeded):
        await reddit._thread(work, budget)
    assert len(calls) == 1 and time.monotonic() - started < 1


@pytest.mark.asyncio
async def test_native_praw_limiter_wait_is_cancelable(monkeypatch, tmp_path):
    from app.connectors.reddit import _Budget
    reddit = RedditConnector(SecretStore(tmp_path))
    reddit.secrets.set("reddit_client_id", "test-id")
    reddit.secrets.set("reddit_refresh_token", "test-refresh")
    limiter = SimpleNamespace(next_request_timestamp=time.time() + 600)
    fake = SimpleNamespace(_core=SimpleNamespace(_rate_limiter=limiter))
    monkeypatch.setattr("app.connectors.reddit.praw.Reddit", lambda **kw: fake)
    started, finished = threading.Event(), threading.Event()
    budget = _Budget(reddit, 20, 5)
    def work():
        client = reddit._client()
        started.set()
        try:
            client._core._rate_limiter.delay()
        finally:
            finished.set()
    task = asyncio.create_task(reddit._thread(work, budget))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(finished.wait, 1)


@pytest.mark.asyncio
async def test_success_recovers_error_within_identity_cache_window(monkeypatch, tmp_path):
    reddit = RedditConnector(SecretStore(tmp_path))
    reddit.secrets.set("reddit_refresh_token", "test-refresh")
    client = fake_client(front=SimpleNamespace(new=lambda **kw: [post("healthy")]))
    monkeypatch.setattr(reddit, "_client", lambda authenticated=True: client)
    await reddit.verify_status()
    reddit._state, reddit.last_error = "error", "previous network failure"
    posts, errors = await reddit.collect("following", "", [], [])
    assert posts and not errors
    assert reddit.status()["state"] == "connected" and reddit.status()["last_error"] is None


def test_real_praw_listing_mapping_does_not_fetch_optional_details(monkeypatch):
    import praw
    client = praw.Reddit(client_id="offline-test", client_secret=None, user_agent="market-radar offline unit test", check_for_updates=False, check_for_async=False)
    payload = vars(post("abc"))
    payload["subreddit"] = "books"
    record = praw.models.Submission(client, _data=payload)
    def forbidden_fetch():
        raise AssertionError("post mapping must not lazily fetch details or comments")
    monkeypatch.setattr(record, "_fetch", forbidden_fetch)
    try:
        mapped = RedditConnector._post(record, "following")
        assert mapped["external_id"] == "abc" and mapped["references"] == []
        assert mapped["external_url"] == "https://publisher.example/article"
    finally:
        client._core.close()
