import json
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store


def post(identity="abc", content="A post with no trading keywords"):
    return {"external_id": identity, "source": "x", "source_name": "X", "author": "writer", "title": "Personal note", "content": content, "url": "https://x.com/writer/status/" + identity, "published_at": "2026-10-02T00:00:00+00:00"}


def test_following_is_preserved_and_duplicate_channels_merge(tmp_path):
    store = Store(tmp_path / "data.sqlite3")
    assert store.ingest(post(), "following", query="Bitcoin", topic="crypto")
    identity = store.items()["items"][0]["id"]
    store.update_item(identity, {"bookmarked": True, "is_read": True})
    assert not store.ingest(post(), "recommended")
    result = store.items()["items"][0]
    assert result["channels"] == ["following", "recommended"]
    assert result["bookmarked"] and result["is_read"]
    assert store.items(channel="following", q="Bitcoin")["total"] == 0
    assert store.items(channel="following")["total"] == 1
    # Re-opening the database keeps personal annotation and channel history.
    reopened = Store(tmp_path / "data.sqlite3")
    assert reopened.get_item(identity)["bookmarked"]


def test_api_shapes_bookmarks_and_secret_redaction(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        service = client.app.state.service
        service.store.ingest(post(), "following")
        response = client.get("/api/items?channel=following")
        assert response.status_code == 200
        result = response.json()
        assert result["total"] == 1 and result["limit"] == 40
        identity = result["items"][0]["id"]
        assert client.patch("/api/items/" + identity, json={"bookmarked": True}).json()["bookmarked"]
        settings = client.put("/api/settings", json={"llm": {"enabled": True, "model": "test", "api_key": "TOP_SECRET_123"}}).json()
        assert settings["llm"]["api_key"] == {"configured": True}
        assert "TOP_SECRET_123" not in client.get("/api/settings").text
        assert "TOP_SECRET_123" not in (tmp_path / "secrets.enc").read_text()
        assert "TOP_SECRET_123" not in service.store.settings().__str__()
        overview = client.get("/api/overview").json()
        assert overview["counts"]["following"] == 1
        assert overview["counts"]["bookmarked"] == 1
        assert {topic["id"] for topic in overview["topics"]} == {"all", "macro", "crypto", "us", "hk", "cn", "finance", "gold"}
        assert "TOP_SECRET_123" not in client.get("/api/export").text


def test_browser_origins_host_and_validation_do_not_leak_cookies(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/connections/x/login", headers={"Origin": "https://malicious.example"}).status_code == 403
        assert client.get("/api/settings", headers={"Host": "evil.example"}).status_code == 403
        result = client.post("/api/connections/x/cookies", json={"cookies": "SECRET_COOKIE_MARKER" * 20000})
        assert result.status_code == 422
        assert "SECRET_COOKIE_MARKER" not in result.text
        assert client.post("/api/connections/reddit/config", json={"client_id": "abc", "redirect_uri": "https://evil.example/callback"}).status_code == 422


def test_items_escape_sql_like_wildcards_and_handle_missing_dates(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    item = post(content="100% information")
    item["published_at"] = None
    store.ingest(item, "following")
    assert store.items(q="%")["total"] == 1
    assert store.items(q="_")["total"] == 0
    assert store.items()["items"][0]["published_at"] is None


def test_interrupted_jobs_are_marked_failed_on_restart(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    store.save_job({"id": "interrupted", "status": "running", "errors": []})
    restarted = Store(tmp_path / "db.sqlite3")
    assert restarted.get_job("interrupted")["status"] == "failed"


def test_collection_job_partial_failure_keeps_real_results(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        async def collect(source, channel, query, settings):
            if source == "rss":
                raise RuntimeError("raw token must not leak: TOP_SECRET")
            value = post()
            value["source"] = source
            return [value], []
        client.app.state.service.public.collect = collect
        result = client.post("/api/collect", json={"query": "Bitcoin", "sources": ["news", "rss"]})
        assert result.status_code == 202
        identity = result.json()["id"]
        for _ in range(40):
            job = client.get("/api/jobs/" + identity).json()
            if job["status"] not in {"queued", "running"}:
                break
            time.sleep(0.02)
        assert job["status"] == "partial" and job["added"] == 1
        assert job["errors"][0]["source"] == "rss"
        assert "TOP_SECRET" not in json.dumps(job)


def test_following_collection_does_not_force_selected_search_topic(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        async def collect(source, channel, query, settings):
            value = post()
            value["source"] = "rss"
            return [value], []
        client.app.state.service.public.collect = collect
        job = client.post("/api/collect", json={"channel": "following", "topic": "crypto", "query": "Bitcoin", "sources": ["rss"]}).json()
        for _ in range(30):
            if client.get("/api/jobs/" + job["id"]).json()["status"] not in {"queued", "running"}:
                break
            time.sleep(0.02)
        item = client.get("/api/items?channel=following").json()["items"][0]
        assert item["content"] == "A post with no trading keywords"
        assert "crypto" not in item["topics"]
        assert client.get("/api/connections/reddit/callback?state=invalid&code=secret_code").status_code == 400


def test_invalid_settings_never_modify_credentials_or_preferences(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        service = client.app.state.service
        service.secrets.set("llm_api_key", "old-key")
        before = service.store.settings()
        response = client.put("/api/settings", json={"keywords": ["changed"], "llm": {"api_key": "new-secret-key", "enabled": "invalid"}})
        assert response.status_code == 422
        assert "new-secret-key" not in response.text
        assert service.secrets.get("llm_api_key") == "old-key"
        assert service.store.settings() == before


def test_settings_transaction_restores_key_when_database_commit_fails(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path)) as client:
        service = client.app.state.service
        service.secrets.set("llm_api_key", "old-key")
        original_connect = service.store.connect
        previous = service.store.settings()
        changes = {**previous, "keywords": ["new-keyword"]}
        class FailedCommit:
            def __init__(self):
                self.db = original_connect()
            def execute(self, *args):
                return self.db.execute(*args)
            def commit(self):
                raise RuntimeError("simulated persistence failure")
            def rollback(self):
                self.db.rollback()
            def close(self):
                self.db.close()
        monkeypatch.setattr(service.store, "connect", FailedCommit)
        import pytest
        with pytest.raises(RuntimeError):
            service.commit_settings(changes, "new-key")
        assert service.secrets.get("llm_api_key") == "old-key"
        monkeypatch.setattr(service.store, "connect", original_connect)
        assert service.store.settings() == previous


def test_updated_original_url_remains_deduplicated_across_sources(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    old = post()
    store.ingest(old, "following")
    updated = {**old, "url": "https://x.com/newwriter/status/abc"}
    assert not store.ingest(updated, "recommended")
    duplicate = {**updated, "source": "news", "external_id": "other-source-id"}
    assert not store.ingest(duplicate, "search")
    items = store.items()["items"]
    assert len(items) == 1 and items[0]["url"] == updated["url"]
    assert set(items[0]["channels"]) == {"following", "recommended", "search"}


def test_relevance_sort_uses_keyword_matches_before_score(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    unrelated = {**post("unrelated"), "score": 10000}
    relevant = {**post("relevant", "Bitcoin and Federal Reserve"), "score": 1}
    store.ingest(unrelated, "following")
    store.ingest(relevant, "following")
    assert store.items(sort="relevance")["items"][0]["external_id"] == "relevant"


def test_production_favicon_has_svg_mime_and_is_not_spa_html(tmp_path, monkeypatch):
    import app.main as main
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend" / "dist"
    frontend.mkdir(parents=True)
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="2"/></svg>'
    (frontend / "favicon.svg").write_text(svg)
    (frontend / "index.html").write_text("<!doctype html><title>SPA</title>")
    monkeypatch.setattr(main, "ROOT", backend)
    with TestClient(main.create_app(tmp_path / "data")) as client:
        response = client.get("/favicon.svg")
        assert response.status_code == 200
        assert response.headers["content-type"].split(";")[0] == "image/svg+xml"
        assert response.text == svg
        assert client.get("/reader").text.startswith("<!doctype html>")
