import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import FetchResponse
from app.article import ArticleUnavailable, extract_article
from app.discussion import hackernews_comments
from app.translation import source_hash


@pytest.mark.asyncio
async def test_html_article_extraction_excludes_navigation(monkeypatch):
    text = "The Federal Reserve announced a policy decision. Markets assessed interest rates and inflation expectations. "
    html = ("<html><body><nav>Navigation</nav><article><h1>Policy decision</h1>" + "".join(f"<p>{text}</p>" for _ in range(8)) + "</article></body></html>").encode()
    async def fetch(*args, **kwargs):
        return FetchResponse(200, html, {"content-type": "text/html"}, "https://example.org/article")
    monkeypatch.setattr("app.article.fetch_response", fetch)
    result = await extract_article("https://example.org/article")
    assert "interest rates" in result["content"] and "Navigation" not in result["content"]
    assert result["content_kind"] == "extracted_html"


@pytest.mark.asyncio
async def test_non_html_keeps_existing_excerpt(monkeypatch):
    async def fetch(*args, **kwargs):
        return FetchResponse(200, b"PDF", {"content-type": "application/pdf"}, "https://example.org/article.pdf")
    monkeypatch.setattr("app.article.fetch_response", fetch)
    with pytest.raises(ArticleUnavailable):
        await extract_article("https://example.org/article.pdf")


@pytest.mark.asyncio
async def test_hn_comments_are_bounded_and_keep_parent_links(monkeypatch):
    tree = {"children": [{"id": 2, "author": "a", "text": "<p>Root reply</p>", "children": [{"id": 3, "text": "Nested reply", "children": []}]}, {"id": 4, "text": "Another reply"}]}
    async def fetch(*args, **kwargs):
        return json.dumps(tree).encode()
    monkeypatch.setattr("app.discussion.fetch_url", fetch)
    items = await hackernews_comments("1", limit=2)
    assert len(items) == 2 and items[1]["parent_id"] == "2"
    assert items[0]["url"] == "https://news.ycombinator.com/item?id=2"
    assert "<p>" not in items[0]["content"]
    with pytest.raises(ValueError):
        await hackernews_comments("../../private")


def test_article_endpoint_preserves_annotations_and_invalidates_translation(tmp_path, monkeypatch):
    async def extract(*args, **kwargs):
        return {"content": "New complete article body " * 20, "content_kind": "extracted_html", "external_url": "https://example.org/article"}
    monkeypatch.setattr("app.article.extract_article", extract)
    with TestClient(create_app(tmp_path)) as client:
        store = client.app.state.service.store
        store.ingest({"external_id": "a", "source": "rss", "url": "https://example.org/article", "title": "Article", "content": "Excerpt"}, "following")
        item = store.items()["items"][0]
        store.update_item(item["id"], {"bookmarked": True})
        store.save_translation(item["id"], source_hash(item), "test-flash", {"title": "标题", "content": "旧摘要译文", "summary": "旧摘要"})
        response = client.post(f"/api/items/{item['id']}/content")
        assert response.status_code == 200
        updated = response.json()
        assert updated["bookmarked"] and updated["url"] == item["url"]
        assert updated["content_kind"] == "extracted_html" and updated["content"].startswith("New complete")
        assert updated["translation"] is None


def test_discussion_endpoint_caches_bounded_results(tmp_path, monkeypatch):
    calls = []
    async def comments(identity, limit=20):
        calls.append(identity)
        return [{"external_id": "2", "parent_id": identity, "author": "reader", "content": "Comment", "url": "https://news.ycombinator.com/item?id=2"}]
    monkeypatch.setattr("app.discussion.hackernews_comments", comments)
    with TestClient(create_app(tmp_path)) as client:
        store = client.app.state.service.store
        store.ingest({"external_id": "1", "source": "hackernews", "url": "https://news.ycombinator.com/item?id=1", "title": "Discussion"}, "search")
        identity = store.items()["items"][0]["id"]
        assert client.post(f"/api/items/{identity}/discussion").json()["items"][0]["content"] == "Comment"
        assert client.post(f"/api/items/{identity}/discussion").json()["cached"]
        assert calls == ["1"]


@pytest.mark.parametrize("revision", ["text", "url"])
def test_delayed_article_does_not_overwrite_changed_source(tmp_path, monkeypatch, revision):
    with TestClient(create_app(tmp_path)) as client:
        store = client.app.state.service.store
        original = {"external_id": "a", "source": "rss", "url": "https://example.org/v1", "title": "Version ONE", "content": "Excerpt ONE"}
        store.ingest(original, "following")
        identity = store.items()["items"][0]["id"]
        store.update_item(identity, {"bookmarked": True})

        async def extract(*args, **kwargs):
            revised = {**original, "url": "https://example.org/v2"} if revision == "url" else {**original, "title": "Version TWO", "content": "Excerpt TWO"}
            store.ingest(revised, "following")
            return {"content": "OLD extracted body " * 20, "content_kind": "extracted_html", "external_url": original["url"]}

        monkeypatch.setattr("app.article.extract_article", extract)
        response = client.post(f"/api/items/{identity}/content")
        assert response.status_code == 409
        current = store.get_item(identity)
        assert current["bookmarked"] and current["content"] == ("Excerpt ONE" if revision == "url" else "Excerpt TWO")
        assert current["url"] == ("https://example.org/v2" if revision == "url" else original["url"])


def test_delayed_article_preserves_annotations_changed_during_fetch(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path)) as client:
        store = client.app.state.service.store
        store.ingest({"external_id": "a", "source": "rss", "url": "https://example.org/article", "title": "Article", "content": "Excerpt"}, "following")
        identity = store.items()["items"][0]["id"]

        async def extract(*args, **kwargs):
            store.update_item(identity, {"bookmarked": True, "is_read": True})
            return {"content": "Complete article " * 20, "content_kind": "extracted_html", "external_url": "https://example.org/article"}

        monkeypatch.setattr("app.article.extract_article", extract)
        response = client.post(f"/api/items/{identity}/content")
        assert response.status_code == 200
        assert response.json()["bookmarked"] and response.json()["is_read"]
