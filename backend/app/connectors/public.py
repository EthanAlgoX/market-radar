from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlsplit

import feedparser

from ..security import fetch_url, safe_error, strip_html


class UnsupportedChannel(RuntimeError):
    pass


def parse_feed(raw: bytes, source: str, source_name: str) -> list[dict]:
    feed = feedparser.parse(raw)
    if not feed.entries and feed.bozo:
        raise RuntimeError("来源返回的内容不是有效 RSS / Atom")
    result = []
    for entry in feed.entries[:150]:
        link = entry.get("link", "")
        if urlsplit(link).scheme not in {"http", "https"}:
            continue
        timestamp = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = datetime.fromtimestamp(calendar.timegm(timestamp), timezone.utc).isoformat() if timestamp else None
        content = strip_html(entry.get("summary") or " ".join(part.get("value", "") for part in entry.get("content", [])))
        result.append({
            "external_id": hashlib.sha256(link.encode()).hexdigest()[:24],
            "source": source, "source_name": (entry.get("source") or {}).get("title", source_name),
            "author": entry.get("author", ""), "title": strip_html(entry.get("title", "")),
            "content": content[:20000], "url": link, "published_at": published_at,
            "score": 0, "metrics": {}, "summary_kind": "extractive",
        })
    return result


def query_matches(post: dict, query: str) -> bool:
    if not query.strip():
        return True
    text = f"{post.get('title', '')} {post.get('content', '')}".casefold()
    # RSS has no provider search API. Treat explicit OR terms as independent phrases.
    terms = [term.strip().strip('"').casefold() for term in re.split(r"\s+OR\s+|[,，]", query, flags=re.I)]
    return any(term and term in text for term in terms)


class PublicConnector:
    async def collect(self, source: str, channel: str, query: str, settings: dict):
        if channel == "recommended":
            raise UnsupportedChannel("该公开来源没有本人个性化推荐流")
        if source == "news":
            if channel != "search":
                raise UnsupportedChannel("Google News 在此接入仅提供关键词搜索")
            params = urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
            raw = await fetch_url("https://news.google.com/rss/search?" + params)
            return parse_feed(raw, "news", "Google News"), []
        if source == "hackernews":
            if channel != "search":
                raise UnsupportedChannel("Hacker News 在此接入仅提供关键词搜索")
            url = "https://hn.algolia.com/api/v1/search_by_date?" + urlencode({"query": query, "tags": "story", "hitsPerPage": 50})
            data = json.loads(await fetch_url(url))
            items = [{
                "external_id": str(hit["objectID"]), "source": "hackernews", "source_name": "Hacker News",
                "author": hit.get("author", ""), "title": strip_html(hit.get("title", "")),
                "content": strip_html(hit.get("story_text") or ""),
                "url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "published_at": hit.get("created_at"), "score": hit.get("points") or 0,
                "metrics": {"points": hit.get("points") or 0, "comments": hit.get("num_comments") or 0},
            } for hit in data.get("hits", [])]
            return items, []
        if source != "rss":
            raise ValueError("Unknown source")

        async def read(feed):
            try:
                raw = await fetch_url(feed["url"])
                posts = parse_feed(raw, "rss", feed["name"])
                if channel == "search":
                    posts = [post for post in posts if query_matches(post, query)]
                return posts, None
            except Exception as error:
                return [], {"source": "rss", "message": f"{feed['name']}: {safe_error(error, 'RSS')}"}

        feeds = [feed for feed in settings["rss_feeds"] if feed.get("enabled")]
        if not feeds:
            raise UnsupportedChannel("请先在设置中启用 RSS 订阅")
        results = await asyncio.gather(*(read(feed) for feed in feeds))
        return [post for posts, _ in results for post in posts], [error for _, error in results if error]

    async def x_rsshub(self, channel: str, query: str, authors: list[str], base_url: str):
        if channel == "search":
            routes = ["/twitter/keyword/" + quote(query, safe="")]
        elif channel == "following":
            routes = ["/twitter/home_latest"]
            # Authenticated home route is the actual personal Following feed.
            # Explicit author subscriptions are additional independent streams.
            routes.extend("/twitter/user/" + quote(author.lstrip("@"), safe="") for author in authors[:30])
        else:
            routes = ["/twitter/home"]
        posts, errors = [], []
        for route in routes:
            try:
                raw = await fetch_url(base_url.rstrip("/") + route, allow_loopback=True)
                entries = parse_feed(raw, "x", "X · RSSHub")
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
