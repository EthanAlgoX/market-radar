import json

import pytest

from app.store import Store
from app.translation import source_hash


def article(source="rss", external_id="guid-1", **changes):
    return {"source": source, "external_id": external_id, "source_name": "Publisher A", "author": "Author A",
            "url": "https://example.org/story?utm_source=feed&id=1", "title": "Federal Reserve policy",
            "content": "Original publication", "feed_id": "feed-a", "content_kind": "feed_summary", **changes}


def test_cross_source_observations_preserve_identity_and_translation(tmp_path):
    store = Store(tmp_path / "store.sqlite3")
    store.ingest(article(), "following")
    first = store.items()["items"][0]
    store.update_item(first["id"], {"bookmarked": True, "is_read": True})
    assert store.save_translation(first["id"], source_hash(first), "test-flash", {"title": "中文标题", "content": "中文正文", "summary": "摘要"})
    result = store.ingest_detailed(article("news", "news-1", source_name="Search B", author="Author B", content="Different source excerpt", url="https://example.org/story?id=1&fbclid=tracking", feed_id="news"), "search", "美联储")
    assert result["duplicate"] and not result["updated"]
    item = store.get_item(first["id"])
    assert (item["source"], item["source_name"], item["author"], item["content"]) == ("rss", "Publisher A", "Author A", "Original publication")
    assert item["bookmarked"] and item["is_read"] and item["translation"]["title"] == "中文标题"
    assert len(item["observations"]) == 2
    assert {obs["source"] for obs in item["observations"]} == {"rss", "news"}
    assert store.items(source="news")["total"] == 1
    assert store.items(q="美联储")["total"] == 1


def test_same_feed_updates_and_extracted_content_survives_summary_refresh(tmp_path):
    store = Store(tmp_path / "store.sqlite3")
    store.ingest(article(), "following")
    identity = store.items()["items"][0]["id"]
    store.update_item(identity, {"content": "Full article text " * 100, "summary": "Full article summary", "content_kind": "extracted_html", "content_extracted_at": "now"})
    result = store.ingest_detailed(article(), "following")
    assert result["duplicate"]
    assert store.get_item(identity)["content"].startswith("Full article text")
    result = store.ingest_detailed(article(title="New decision", content="Revised article summary"), "following")
    assert result["updated"]
    assert store.get_item(identity)["content"] == "Revised article summary"


def test_legacy_rss_id_adopts_guid_without_losing_annotations(tmp_path):
    store = Store(tmp_path / "store.sqlite3")
    old = article(external_id="old-url-hash")
    old.pop("feed_id")
    store.ingest(old, "following")
    identity = store.items()["items"][0]["id"]
    store.update_item(identity, {"bookmarked": True})
    store.ingest(article(external_id="new-guid-hash", content="New body"), "following")
    store.ingest(article(external_id="new-guid-hash", content="Second body"), "following")
    item = store.get_item(identity)
    assert store.items()["total"] == 1 and item["bookmarked"]
    assert item["external_id"] == "new-guid-hash" and item["content"] == "Second body"


def test_provenance_migration_and_checkpoint_survive_restart(tmp_path):
    store = Store(tmp_path / "store.sqlite3")
    store.ingest(article(), "following")
    identity = store.items()["items"][0]["id"]
    with store.connect() as db:
        db.execute("DELETE FROM observations")
    store.save_checkpoint("feed:test", {"etag": "version-1", "items": []})
    reopened = Store(tmp_path / "store.sqlite3")
    assert reopened.get_checkpoint("feed:test")["etag"] == "version-1"
    assert len(reopened.get_item(identity)["observations"]) == 1


def test_word_boundaries_and_bilingual_queries_keep_personal_posts(tmp_path):
    store = Store(tmp_path / "store.sqlite3")
    store.ingest(article(title="Goldman Sachs and riverbank", content="A personal note"), "following", "gold", "gold")
    item = store.items()["items"][0]
    assert "gold" not in item["topics"] and "finance" not in item["topics"]
    assert store.items(q="黄金")["total"] == 0
    store.ingest(article(external_id="gold", title="Gold price rises", url="https://example.org/gold"), "following")
    assert store.items(q="黄金")["total"] == 1
    assert store.items(q="gold AND NOT Goldman")["total"] == 1


@pytest.mark.parametrize("route_prefix", ["#/", "#!"])
def test_hash_routes_remain_distinct_items(tmp_path, route_prefix):
    from app.store import canonical_url
    from app.connectors.public import canonical_url as feed_canonical_url

    first = f"https://example.org/{route_prefix}news/one"
    second = f"https://example.org/{route_prefix}news/two"
    assert canonical_url(first) != canonical_url(second)
    assert feed_canonical_url(first) != feed_canonical_url(second)
    store = Store(tmp_path / "store.sqlite3")
    store.ingest(article(external_id="route-one", url=first), "following")
    store.ingest(article(external_id="route-two", url=second), "following")
    items = store.items()
    assert items["total"] == 2
    assert {item["url"] for item in items["items"]} == {first, second}


def test_same_title_new_url_discards_old_extracted_body_and_translation(tmp_path):
    store = Store(tmp_path / "store.sqlite3")
    store.ingest(article(), "following")
    original = store.items()["items"][0]
    extracted = store.update_item(original["id"], {
        "content": "Old full article body " * 100, "summary": "Old full article summary",
        "content_kind": "extracted_html", "external_url": original["url"],
        "content_extracted_at": "2026-10-02T00:00:00+00:00", "bookmarked": True,
    })
    assert store.save_translation(extracted["id"], source_hash(extracted), "test-flash", {
        "title": "旧标题", "content": "旧全文译文", "summary": "旧摘要译文",
    })
    revised_url = "https://example.org/revised-story?id=2"
    outcome = store.ingest_detailed(article(url=revised_url, external_url=revised_url,
        content="Current feed body", summary="Current feed summary"), "following")
    current = store.get_item(original["id"])
    assert outcome["updated"] and not outcome["added"]
    assert current["title"] == original["title"] and current["url"] == revised_url
    assert current["content"] == "Current feed body" and current["summary"] == "Current feed summary"
    assert current["content_kind"] == "feed_summary" and "content_extracted_at" not in current
    assert current["external_url"] == revised_url and current["bookmarked"]
    assert current["translation"] is None
