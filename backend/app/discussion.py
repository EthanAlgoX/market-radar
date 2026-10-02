"""Lazy, bounded public discussion retrieval; no background recursive crawling."""
import json
import re

from .security import fetch_url, strip_html


async def hackernews_comments(identity: str, limit: int = 20):
    if not re.fullmatch(r"[0-9]{1,20}", identity):
        raise ValueError("无效的 Hacker News 帖子 ID")
    limit = min(40, max(1, limit))
    data = json.loads(await fetch_url(f"https://hn.algolia.com/api/v1/items/{identity}"))
    result = []
    # Algolia returns an item tree in one bounded HTTP response. Keep reply relationships.
    pending = [(node, identity, 1) for node in reversed(data.get("children", []))]
    while pending and len(result) < limit:
        node, parent, depth = pending.pop()
        node_id = str(node.get("id", ""))
        if not re.fullmatch(r"[0-9]{1,20}", node_id):
            continue
        text = strip_html(node.get("text") or "")
        if text:
            result.append({"external_id": node_id, "parent_id": str(parent), "root_id": identity,
                           "depth": depth, "author": node.get("author") or "[deleted]", "content": text[:16000],
                           "url": f"https://news.ycombinator.com/item?id={node_id}",
                           "published_at": node.get("created_at"), "score": node.get("points") or 0})
        if depth < 5:
            pending.extend((child, node_id, depth + 1) for child in reversed(node.get("children", [])))
    return result
