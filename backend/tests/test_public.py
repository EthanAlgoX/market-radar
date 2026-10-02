from app.connectors.public import parse_feed, query_matches


FEED = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title><item><guid>real-guid</guid><title>Central bank raises rates</title><link>https://example.org/press/1</link><description><![CDATA[<p>Policy update &amp; statement</p>]]></description><pubDate>Fri, 02 Oct 2026 04:00:00 GMT</pubDate></item><item><title>No date item</title><link>https://example.org/press/2</link></item><item><title>Unsafe link</title><link>javascript:alert(1)</link></item></channel></rss>'''


def test_rss_parser_keeps_original_links_dates_and_strips_html():
    posts = parse_feed(FEED, "rss", "Central Bank")
    assert len(posts) == 2
    assert posts[0]["url"] == "https://example.org/press/1"
    assert posts[0]["content"] == "Policy update & statement"
    assert posts[0]["published_at"] == "2026-10-02T04:00:00+00:00"
    assert posts[0]["updated_at"] is None
    assert posts[1]["published_at"] is None
    assert query_matches(posts[0], "Bitcoin OR Central bank")
    assert not query_matches(posts[0], "Bitcoin")

import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.connectors.public import PublicConnector
from app.security import FetchResponse


FULL_FEED = b'''<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><language>en-US</language><item><guid isPermaLink="false">same-article</guid><title>Gold outlook</title><link>https://example.org/a?utm_source=rss</link><description>Short summary</description><content:encoded><![CDATA[<p>First paragraph.</p><p>Second <b>paragraph</b>.</p>]]></content:encoded></item></channel></rss>'''


def test_guid_identity_survives_link_and_name_change_and_is_scoped_to_feed():
    one = parse_feed(FULL_FEED, "rss", "Old name", feed_id="publisher")[0]
    changed = FULL_FEED.replace(b"a?utm_source=rss", b"different-permalink")
    two = parse_feed(changed, "rss", "Renamed", feed_id="publisher")[0]
    other = parse_feed(changed, "rss", "Renamed", feed_id="other-publisher")[0]
    assert one["external_id"] == two["external_id"]
    assert other["external_id"] != one["external_id"]
    assert one["guid"] == "same-article"
    assert one["url"].endswith("?utm_source=rss")
    assert one["canonical_url"] == "https://example.org/a"


def test_full_content_summary_language_and_paragraphs_are_separate():
    post = parse_feed(FULL_FEED, "rss", "Publisher", feed_id="publisher")[0]
    assert post["content"] == "First paragraph.\n\nSecond paragraph."
    assert post["summary"] == "Short summary"
    assert post["language"] == "en-US"
    assert post["content_kind"] == "feed_content"
    assert post["truncated"] is False


def test_atom_id_language_updated_time_and_tracking_fallback():
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="ja"><title>JP</title><entry><id>urn:news:1</id><title>News</title><link href="https://example.org/jp"/><updated>2026-10-02T08:00:00Z</updated><content type="html">&lt;p&gt;One&lt;/p&gt;&lt;p&gt;Two&lt;/p&gt;</content></entry></feed>'''
    item = parse_feed(atom, "rss", "JP", feed_id="jp")[0]
    assert item["guid"] == "urn:news:1"
    assert item["language"] == "ja"
    assert item["updated_at"] == "2026-10-02T08:00:00+00:00"
    assert item["content"] == "One\n\nTwo"
    no_guid = FULL_FEED.replace(b'<guid isPermaLink="false">same-article</guid>', b"")
    assert parse_feed(no_guid, "rss", "P", feed_id="p")[0]["external_id"] == parse_feed(no_guid.replace(b"utm_source=rss", b"utm_source=other"), "rss", "P", feed_id="p")[0]["external_id"]


class CacheStore:
    def __init__(self):
        self.values = {}

    def get_checkpoint(self, key):
        return self.values.get(key)

    def save_checkpoint(self, key, value):
        self.values[key] = value


@pytest.mark.asyncio
async def test_persistent_304_cache_replays_all_items_for_changed_query(monkeypatch):
    calls = []

    async def fetch(url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return FetchResponse(200, FEED, {"etag": '"v1"', "last-modified": "Fri, 02 Oct 2026 04:00:00 GMT"}, url)
        return FetchResponse(304, b"", {"etag": '"v1"'}, url)

    monkeypatch.setattr("app.connectors.public.fetch_response", fetch)
    store = CacheStore()
    settings = {"rss_feeds": [{"id": "central", "name": "Central", "url": "https://example.org/feed", "enabled": True}]}
    first, errors = await PublicConnector(store, domain_interval=0).collect("rss", "search", "Bitcoin", settings)
    assert first == [] and errors == []
    posts, errors = await PublicConnector(store, domain_interval=0).collect("rss", "search", "央行", settings)
    assert len(posts) == 1 and errors == []
    assert calls[1]["headers"]["If-None-Match"] == '"v1"'
    assert "If-Modified-Since" in calls[1]["headers"]
    assert next(iter(store.values.values()))["status"] == 304
    assert len(next(iter(store.values.values()))["items"]) == 2


@pytest.mark.asyncio
async def test_304_metadata_without_cached_items_gets_an_unconditional_body(monkeypatch):
    store = CacheStore()
    store.get_checkpoint = lambda key: {"etag": '"old"'}
    calls = []

    async def fetch(url, **kwargs):
        calls.append(kwargs)
        return FetchResponse(304, b"", {}, url) if len(calls) == 1 else FetchResponse(200, FEED, {}, url)

    monkeypatch.setattr("app.connectors.public.fetch_response", fetch)
    settings = {"rss_feeds": [{"id": "a", "name": "A", "url": "https://example.org/feed", "enabled": True}]}
    posts, errors = await PublicConnector(store, domain_interval=0).collect("rss", "following", "Bitcoin", settings)
    assert len(posts) == 2 and errors == []  # Following ignores keyword filtering.
    assert "headers" not in calls[1]


@pytest.mark.asyncio
async def test_failure_does_not_replace_good_cache_or_advance_success(monkeypatch):
    async def fetch(url, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr("app.connectors.public.fetch_response", fetch)
    store = CacheStore()
    saved = {"etag": "old", "last_success_at": "2020", "items": [{"title": "saved"}]}
    store.get_checkpoint = lambda key: saved
    settings = {"rss_feeds": [{"id": "a", "name": "A", "url": "https://example.org/feed", "enabled": True}]}
    posts, errors = await PublicConnector(store, domain_interval=0).collect("rss", "following", "", settings)
    assert posts == [] and len(errors) == 1
    assert saved["last_success_at"] == "2020" and store.values == {}


@pytest.mark.asyncio
async def test_feed_concurrency_is_bounded_and_bad_source_is_isolated(monkeypatch):
    active = maximum = 0

    async def fetch(url, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.005)
            if "bad" in url:
                raise TimeoutError()
            return FetchResponse(200, FEED, {}, url)
        finally:
            active -= 1

    monkeypatch.setattr("app.connectors.public.fetch_response", fetch)
    feeds = [{"id": str(i), "name": str(i), "url": f"https://domain{i}.example/feed", "enabled": True} for i in range(8)]
    feeds.append({"id": "bad", "name": "bad", "url": "https://bad.example/feed", "enabled": True})
    posts, errors = await PublicConnector(concurrency=3, domain_interval=0).collect("rss", "following", "", {"rss_feeds": feeds})
    assert maximum <= 3
    assert len(posts) == 16 and len(errors) == 1 and errors[0]["feed_id"] == "bad"


@pytest.mark.asyncio
async def test_only_feed_within_configured_hub_gets_loopback_exception(monkeypatch):
    calls = []

    async def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return FetchResponse(200, FEED, {}, url)

    monkeypatch.setattr("app.connectors.public.fetch_response", fetch)
    urls = ["http://localhost:1200/rss/cls/telegraph", "http://localhost:1200/rss-evil/feed", "http://localhost:9999/rss/feed"]
    feeds = [{"id": str(i), "name": str(i), "url": url, "enabled": True} for i, url in enumerate(urls)]
    await PublicConnector(domain_interval=0).collect("rss", "following", "", {"rsshub_url": "http://localhost:1200/rss", "rss_feeds": feeds})
    assert {url: options["allow_loopback"] for url, options in calls} == dict(zip(urls, [True, False, False]))


@pytest.mark.asyncio
async def test_google_region_and_financial_aliases_and_hn_external_article(monkeypatch):
    seen = []

    async def fetch(url, **kwargs):
        seen.append(url)
        if "algolia" in url:
            body = json.dumps({"hits": [{"objectID": "12", "title": "Bitcoin markets", "url": "https://publisher.org/a?utm_source=hn"}]}).encode()
            return FetchResponse(200, body, {}, url)
        return FetchResponse(200, FULL_FEED, {}, url)

    monkeypatch.setattr("app.connectors.public.fetch_response", fetch)
    connector = PublicConnector(domain_interval=0)
    posts, errors = await connector.collect("news", "search", "黄金", {"google_news": {"hl": "zh-CN", "gl": "HK", "ceid": "HK:zh-Hant"}})
    params = parse_qs(urlsplit(seen[0]).query)
    assert params["hl"] == ["zh-CN"] and "gold" in params["q"][0]
    assert posts[0]["provider_query"] == params["q"][0] and errors == []
    hn, errors = await connector.collect("hackernews", "search", "比特币", {})
    assert len(hn) == 1 and errors == []
    assert hn[0]["url"] == "https://news.ycombinator.com/item?id=12"
    assert hn[0]["external_url"] == "https://publisher.org/a?utm_source=hn"
    assert hn[0]["canonical_url"] == "https://publisher.org/a"
