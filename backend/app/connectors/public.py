from __future__ import annotations

import asyncio
import calendar
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import feedparser

from ..query import compile_query, expand_query, matches_query
from ..security import fetch_response, fetch_url, is_url_under_base, safe_error, strip_html


class UnsupportedChannel(RuntimeError):
    pass


def canonical_url(url: str) -> str:
    """Remove only known tracking fields; retain the untouched source URL separately."""
    parts = urlsplit(url)
    parameters = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                  if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}]
    fragment = parts.fragment if parts.fragment.startswith(("/", "!")) else ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(parameters), fragment))


def _valid_link(value: str) -> str:
    try:
        parts = urlsplit(value or "")
        return value if parts.scheme in {"http", "https"} and parts.hostname and not parts.username else ""
    except ValueError:
        return ""


def _timestamp(value) -> str | None:
    return datetime.fromtimestamp(calendar.timegm(value), timezone.utc).isoformat() if value else None


def parse_feed(raw: bytes, source: str, source_name: str, *, feed_id: str | None = None,
               feed_url: str = "", max_items: int = 150) -> list[dict]:
    feed = feedparser.parse(raw)
    if not feed.entries and feed.bozo:
        raise RuntimeError("来源返回的内容不是有效 RSS / Atom")
    identity = str(feed_id or feed_url or source_name)
    result = []
    for entry in feed.entries[:max_items]:
        link = _valid_link(entry.get("link", ""))
        if not link:
            continue
        guid = str(entry.get("id") or entry.get("guid") or "")
        summary = strip_html(entry.get("summary", ""), preserve_paragraphs=True)
        parts = entry.get("content", [])
        full_content = max((strip_html(part.get("value", ""), preserve_paragraphs=True) for part in parts), key=len, default="")
        content = full_content or summary
        language = entry.get("language") or next((part.get("language") for part in parts if part.get("language")), None) or feed.feed.get("language")
        external = _valid_link(entry.get("feedburner_origlink") or entry.get("origlink") or link)
        stable_link = canonical_url(external or link)
        result.append({
            "external_id": hashlib.sha256(f"{identity}:{guid or stable_link}".encode()).hexdigest()[:32],
            "feed_id": identity, "guid": guid, "feed_url": feed_url, "feed_name": source_name,
            "source": source, "source_name": (entry.get("source") or {}).get("title", source_name),
            "author": entry.get("author", ""), "title": strip_html(entry.get("title", "")),
            "content": content[:20000], "summary": (summary or content)[:280],
            "content_kind": "feed_content" if full_content else "feed_summary" if summary else "title_only",
            "url": link, "source_url": link, "external_url": external, "canonical_url": stable_link,
            "published_at": _timestamp(entry.get("published_parsed") or entry.get("updated_parsed")),
            "updated_at": _timestamp(dict.get(entry, "updated_parsed")), "language": language,
            "truncated": len(content) > 20000 or len(feed.entries) > max_items,
            "score": 0, "metrics": {}, "summary_kind": "extractive",
        })
    return result


def query_matches(post: dict, query: str) -> bool:
    return matches_query(f"{post.get('title', '')} {post.get('content', '')}", query)


class PublicConnector:
    def __init__(self, store=None, *, concurrency: int = 4, domain_interval: float = 0.25):
        self.store = store
        self._cache: dict[str, dict] = {}
        self._semaphore = asyncio.Semaphore(max(1, min(concurrency, 8)))
        self._domain_limits: dict[str, asyncio.Semaphore] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self.domain_interval = max(0.0, domain_interval)

    async def _request(self, url: str, **kwargs):
        domain = urlsplit(url).hostname or ""
        limit = self._domain_limits.setdefault(domain, asyncio.Semaphore(2))
        lock = self._domain_locks.setdefault(domain, asyncio.Lock())
        async with self._semaphore, limit:
            async with lock:
                now = asyncio.get_running_loop().time()
                delay = self.domain_interval - (now - self._last_request.get(domain, 0))
                if delay > 0:
                    await asyncio.sleep(delay)
                self._last_request[domain] = asyncio.get_running_loop().time()
            return await fetch_response(url, **kwargs)

    def _load_cache(self, key: str) -> dict:
        if key not in self._cache:
            saved = self.store.get_checkpoint(key) if self.store is not None else None
            self._cache[key] = dict(saved or {})
        return self._cache[key]

    def _save_cache(self, key: str, value: dict):
        if self.store is not None:
            self.store.save_checkpoint(key, value)
        self._cache[key] = value

    async def _read_feed(self, feed: dict, source: str, settings: dict):
        url, name = feed["url"], feed.get("name") or feed["url"]
        identity = str(feed.get("id") or hashlib.sha256(url.encode()).hexdigest()[:24])
        key = "rss:" + hashlib.sha256(f"{identity}:{url}".encode()).hexdigest()
        cached = self._load_cache(key)
        headers = {}
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
        trusted_base = settings.get("rsshub_url", "")
        trusted = bool(trusted_base and is_url_under_base(url, trusted_base))
        options = {"allow_loopback": trusted, "trusted_base_url": trusted_base if trusted else None}
        response = await self._request(url, headers=headers, **options)
        if response.not_modified and "items" not in cached:
            # Metadata-only or migrated caches need a body before a 304 can be replayed.
            response = await self._request(url, **options)
        if response.not_modified:
            posts = copy.deepcopy(cached["items"])
        else:
            posts = parse_feed(response.body, source, name, feed_id=identity, feed_url=url)
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "etag": response.headers.get("etag", cached.get("etag", "")) if response.not_modified else response.headers.get("etag", ""),
            "last_modified": response.headers.get("last-modified", cached.get("last_modified", "")) if response.not_modified else response.headers.get("last-modified", ""),
            "final_url": response.final_url, "last_success_at": now, "last_checked_at": now,
            "status": response.status_code, "item_count": len(posts), "items": posts,
        }
        self._save_cache(key, state)
        return copy.deepcopy(posts)

    async def collect(self, source: str, channel: str, query: str, settings: dict):
        if channel == "recommended":
            raise UnsupportedChannel("该公开来源没有本人个性化推荐流")
        if source == "news":
            if channel != "search":
                raise UnsupportedChannel("Google News 在此接入仅提供关键词搜索")
            provider_query = compile_query(query, "news")
            region = settings.get("google_news") or {}
            params = urlencode({"q": provider_query, "hl": region.get("hl", "en-US"),
                                "gl": region.get("gl", "US"), "ceid": region.get("ceid", "US:en")})
            url = "https://news.google.com/rss/search?" + params
            feed = {"id": "google-news:" + hashlib.sha256(params.encode()).hexdigest()[:24], "name": "Google News", "url": url}
            posts = await self._read_feed(feed, "news", settings)
            for post in posts:
                post["provider_query"] = provider_query
                # A Google aggregate link is not proof of the publisher's direct article URL.
                if urlsplit(post["external_url"]).hostname == "news.google.com":
                    post["external_url"] = ""
            return posts, []
        if source == "hackernews":
            if channel != "search":
                raise UnsupportedChannel("Hacker News 在此接入仅提供关键词搜索")
            all_queries = list(dict.fromkeys(compile_query(term, "hackernews") for term in expand_query(query))) or [query]
            queries = all_queries[:6]

            async def search(term):
                url = "https://hn.algolia.com/api/v1/search_by_date?" + urlencode({"query": term, "tags": "story", "hitsPerPage": 50})
                response = await self._request(url)
                data = json.loads(response.body)
                return [{
                    "external_id": str(hit["objectID"]), "source": "hackernews", "source_name": "Hacker News",
                    "author": hit.get("author", ""), "title": strip_html(hit.get("title", "")),
                    "content": strip_html(hit.get("story_text") or "", preserve_paragraphs=True),
                    "url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    "source_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    "external_url": _valid_link(hit.get("url", "")),
                    "canonical_url": canonical_url(_valid_link(hit.get("url", "")) or f"https://news.ycombinator.com/item?id={hit['objectID']}"),
                    "published_at": hit.get("created_at"), "score": hit.get("points") or 0,
                    "provider_query": term, "content_kind": "discussion", "truncated": False,
                    "metrics": {"points": hit.get("points") or 0, "comments": hit.get("num_comments") or 0},
                } for hit in data.get("hits", [])]

            results = await asyncio.gather(*(search(term) for term in queries), return_exceptions=True)
            unique, errors = {}, []
            if len(all_queries) > len(queries):
                errors.append({"source": source, "truncated": True, "message": "Hacker News 本轮最多检索6个词组，剩余词组尚未查询"})
            for value in results:
                if isinstance(value, Exception):
                    errors.append({"source": source, "message": safe_error(value, "Hacker News")})
                else:
                    for post in value:
                        if query_matches(post, query):
                            unique.setdefault(post["external_id"], post)
            return list(unique.values())[:150], errors
        if source != "rss":
            raise ValueError("Unknown source")

        async def read(feed):
            try:
                posts = await self._read_feed(feed, "rss", settings)
                if channel == "search":
                    posts = [post for post in posts if query_matches(post, query)]
                return posts, None
            except Exception as error:
                return [], {"source": "rss", "feed_id": feed.get("id", ""),
                            "message": f"{feed.get('name', 'RSS')}: {safe_error(error, 'RSS')}"}

        feeds = [feed for feed in settings.get("rss_feeds", []) if feed.get("enabled")]
        if not feeds:
            raise UnsupportedChannel("请先在设置中启用 RSS 订阅")
        results = await asyncio.gather(*(read(feed) for feed in feeds))
        return [post for posts, _ in results for post in posts], [error for _, error in results if error]

    async def x_rsshub(self, channel: str, query: str, authors: list[str], base_url: str):
        if channel == "search":
            routes = ["/twitter/keyword/" + quote(query, safe="")]
        elif channel == "following":
            routes = ["/twitter/home_latest"]
            routes.extend("/twitter/user/" + quote(author.lstrip("@"), safe="") for author in authors[:30])
        else:
            routes = ["/twitter/home"]
        posts, errors = [], []
        for route in routes:
            try:
                url = base_url.rstrip("/") + route
                raw = await fetch_url(url, allow_loopback=True, trusted_base_url=base_url)
                entries = parse_feed(raw, "x", "X · RSSHub", feed_id="x-rsshub:" + route, feed_url=url)
                for post in entries:
                    match = re.search(r"/(?:status|statuses)/(\d+)", post["url"])
                    if match:
                        post["external_id"] = match.group(1)
                    if not post["author"]:
                        parts = urlsplit(post["url"]).path.strip("/").split("/")
                        post["author"] = parts[0] if parts else ""
                posts.extend(entries)
            except Exception as error:
                errors.append({"source": "x", "message": f"RSSHub {route.split('/')[2]}: {safe_error(error, 'RSSHub')}"})
        return posts, errors
