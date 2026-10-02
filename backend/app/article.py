"""On-demand extraction of accessible HTML using the existing safe HTTP client."""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from .security import fetch_response


class ArticleUnavailable(ValueError):
    pass


async def extract_article(url: str) -> dict:
    response = await fetch_response(url, timeout=20, max_attempts=2)
    if urlsplit(response.final_url).hostname in {"news.google.com", "www.google.com"}:
        raise ArticleUnavailable("该链接仍为新闻聚合页，请通过原文链接进入发布网站；已有摘要已保留")
    kind = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if kind and kind not in {"text/html", "application/xhtml+xml"}:
        raise ArticleUnavailable("该来源不是可解析的 HTML 文章，请打开原文查看；已有内容已保留")

    def extract():
        from trafilatura import extract
        return extract(response.body, url=response.final_url, include_comments=False, include_tables=True, favor_precision=True)

    text = await asyncio.to_thread(extract)
    if not text or len(text.strip()) < 120:
        raise ArticleUnavailable("未取得足够的公开正文，请打开原文查看；已有摘要已保留")
    if len(text) > 120000:
        raise ArticleUnavailable("正文超过本次读取上限，已有内容已保留，请打开原文查看")
    return {"content": text.strip(), "content_kind": "extracted_html", "external_url": response.final_url, "truncated": False}
