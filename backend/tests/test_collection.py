"""Offline regressions for collection admission, recovery and source outcomes."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import pytest

from app.main import CollectRequest, Service
from app.store import Store, canonical_url


def sample_post(source, identity="one"):
    return {
        "source": source, "external_id": identity, "source_name": source,
        "author": "fixture-author", "title": "Bitcoin source fixture",
        "content": "Offline collector text.",
        "url": f"https://example.org/{source}/{identity}",
        "published_at": "2026-10-02T00:00:00+00:00",
    }


def queued_job(identity="first", sources=("news", "rss")):
    return {
        "id": identity, "status": "queued", "fingerprint": "same-request",
        "created_at": "2026-10-02T00:00:00+00:00",
        "request": {"query": "Bitcoin", "channel": "search", "sources": list(sources)},
        "query": "Bitcoin", "channel": "search", "added": 0, "total": 0,
        "progress": [{"source": source, "status": "pending", "count": 0,
                      "new": 0, "updated": 0, "duplicates": 0, "retries": 0}
                     for source in sources],
        "errors": [],
    }


@asynccontextmanager
async def isolated_service(path, monkeypatch):
    # No account data or live model credentials participate in these tests.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    service = Service(path)
    try:
        yield service
    finally:
        tasks = list(service.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await service.translation.shutdown()
        await service.x.shutdown()


async def wait_for_job(service, identity, timeout=3):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        job = service.store.get_job(identity)
        # A newly persisted job can remain queued before either worker claims it.
        if job["status"] not in {"queued", "running"}:
            return job
        await asyncio.sleep(0.01)
    pytest.fail(f"Collection job {identity} did not reach a terminal state")


def test_queue_coalesces_concurrent_admission_and_claims_once(tmp_path):
    store = Store(tmp_path / "market-radar.sqlite3")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda index: store.enqueue_job(queued_job(str(index))), range(4)))
    assert len({job["id"] for job in results}) == 1
    assert len(store.active_jobs()) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda index: store.claim_job(f"owner-{index}"), range(4)))
    assert sum(claim is not None for claim in claims) == 1
    assert store.enqueue_job(queued_job("another"))["id"] == results[0]["id"]


def test_canonical_identity_preserves_repeated_parameter_value_order():
    # HTTP services can choose either the first or last same-name query value.
    first_article = "https://example.org/article?id=one&id=two&utm_source=rss"
    other_article = "https://example.org/article?id=two&id=one&utm_source=news"
    assert canonical_url(first_article) != canonical_url(other_article)


async def test_slow_rss_does_not_block_news_delivery(tmp_path, monkeypatch):
    async with isolated_service(tmp_path, monkeypatch) as service:
        release_rss = asyncio.Event()

        async def collect(source, channel, query, settings):
            if source == "rss":
                await release_rss.wait()
            return [sample_post(source)], []

        service.public.collect = collect
        job = service.new_job(CollectRequest(query="Bitcoin", sources=["rss", "news"]))
        deadline = asyncio.get_running_loop().time() + 2
        while not service.store.items(source="news")["total"]:
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.01)
        pending = service.store.get_job(job["id"])
        assert pending["status"] == "running"
        assert next(entry for entry in pending["progress"] if entry["source"] == "news")["status"] == "completed"
        release_rss.set()
        assert (await wait_for_job(service, job["id"]))["status"] == "completed"


async def test_partial_failure_keeps_items_and_previous_success_time(tmp_path, monkeypatch):
    async with isolated_service(tmp_path, monkeypatch) as service:
        previous_success = "2026-10-01T01:02:03+00:00"
        service.store.status("rss", {"status": "available", "last_success_at": previous_success})

        async def collect(source, channel, query, settings):
            if source == "rss":
                raise RuntimeError("offline fixture failure")
            return [sample_post(source)], []

        service.public.collect = collect
        job = service.new_job(CollectRequest(query="Bitcoin", sources=["news", "rss"]))
        result = await wait_for_job(service, job["id"])
        assert result["status"] == "partial" and result["added"] == 1
        assert service.store.items(source="news")["total"] == 1
        health = service.store.status("rss")
        assert health["status"] == "error"
        assert health["last_success_at"] == previous_success
        assert health["last_attempt_at"]


async def test_restart_resumes_pending_source_without_refetching_completed_source(tmp_path, monkeypatch):
    store = Store(tmp_path / "market-radar.sqlite3")
    store.ingest(sample_post("news"), "search")
    job = queued_job()
    job.update(added=1, total=1)
    job["progress"][0].update(status="completed", count=1, new=1)
    job["progress"][1]["status"] = "running"
    store.enqueue_job(job)
    store.claim_job("interrupted-process")
    async with isolated_service(tmp_path, monkeypatch) as service:
        calls = []

        async def collect(source, channel, query, settings):
            calls.append(source)
            return [sample_post(source)], []

        service.public.collect = collect
        recovered = service.store.get_job(job["id"])
        assert recovered["status"] == "queued" and recovered["recovered"]
        assert "lease_owner" not in recovered
        service.start_workers()
        result = await wait_for_job(service, job["id"])
        assert calls == ["rss"]
        assert result["status"] == "completed" and result["added"] == 2
        assert service.store.items()["total"] == 2


async def test_recovered_success_does_not_keep_previous_failed_source_error(tmp_path, monkeypatch):
    store = Store(tmp_path / "market-radar.sqlite3")
    job = queued_job()
    job["progress"][0]["status"] = "failed"
    job["progress"][1]["status"] = "running"
    job["errors"] = [{"source": "news", "message": "previous attempt failed"}]
    store.enqueue_job(job)
    store.claim_job("interrupted-process")
    async with isolated_service(tmp_path, monkeypatch) as service:
        async def collect(source, channel, query, settings):
            return [sample_post(source)], []

        service.public.collect = collect
        service.start_workers()
        result = await wait_for_job(service, job["id"])
        assert all(entry["status"] == "completed" for entry in result["progress"])
        assert result["status"] == "completed"
        assert not result["errors"]


@pytest.mark.parametrize("has_items", [True, False])
async def test_budget_warning_is_partial_coverage_not_source_failure(tmp_path, monkeypatch, has_items):
    async with isolated_service(tmp_path, monkeypatch) as service:
        async def collect(source, channel, query, settings):
            posts = [sample_post(source)] if has_items else []
            return posts, [{"source": source, "truncated": True, "message": "Only six query groups fit this run"}]

        service.public.collect = collect
        job = service.new_job(CollectRequest(query="Bitcoin", sources=["hackernews"]))
        result = await wait_for_job(service, job["id"])
        assert result["status"] == "partial"
        assert result["progress"][0]["status"] == "partial"
        assert result["progress"][0]["truncated"] is True
        assert service.store.items()["total"] == int(has_items)
