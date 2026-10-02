from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from cryptography.fernet import Fernet


class SecretStore:
    """Encrypted local credential storage. The key and ciphertext stay on this machine."""

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "secrets.enc"
        key_path = data_dir / ".secrets.key"
        if not key_path.exists():
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(Fernet.generate_key())
        os.chmod(key_path, 0o600)
        self.fernet = Fernet(key_path.read_bytes())
        self.lock = threading.RLock()

    def _read(self):
        if not self.path.exists():
            return {}
        return json.loads(self.fernet.decrypt(self.path.read_bytes()))

    def get(self, name: str, default=None):
        with self.lock:
            return self._read().get(name, default)

    def set(self, name: str, value):
        with self.lock:
            data = self._read()
            data[name] = value
            self._write(data)

    def delete(self, name: str):
        with self.lock:
            data = self._read()
            data.pop(name, None)
            self._write(data)

    def _write(self, data):
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(self.fernet.encrypt(json.dumps(data).encode()))
        os.replace(temporary, self.path)


class UnsafeURL(ValueError):
    pass


async def resolve_public_url(url: str, allow_loopback: bool = False) -> tuple[httpx.URL, str]:
    try:
        parsed = httpx.URL(url)
        if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.userinfo:
            raise UnsafeURL("仅支持不含登录凭据的 HTTP / HTTPS 地址")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        result = await asyncio.to_thread(socket.getaddrinfo, parsed.host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(row[4][0] for row in result))
        if not addresses:
            raise UnsafeURL("无法解析来源地址")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified) and not (allow_loopback and ip.is_loopback):
                raise UnsafeURL("来源地址指向私有、保留或元数据网络，已阻止请求")
        return parsed, addresses[0]
    except UnsafeURL:
        raise
    except (ValueError, OSError, httpx.InvalidURL) as exc:
        raise UnsafeURL("来源地址无效或无法解析") from exc


@dataclass(frozen=True)
class FetchResponse:
    status_code: int
    body: bytes
    headers: dict[str, str]
    final_url: str

    @property
    def not_modified(self) -> bool:
        return self.status_code == 304


def _origin(url: httpx.URL) -> tuple[str, str, int]:
    return url.scheme, url.host, url.port or (443 if url.scheme == "https" else 80)


def is_url_under_base(url: str, base_url: str) -> bool:
    """Match the configured RSSHub origin and path without prefix/traversal tricks."""
    try:
        target, base = httpx.URL(url), httpx.URL(base_url)
        if base.scheme not in {"http", "https"} or not base.host or base.userinfo or base.query or base.fragment:
            return False
        if target.userinfo or _origin(target) != _origin(base):
            return False
        path, base_path = target.path, base.path
        for _ in range(3):
            path, base_path = unquote(path), unquote(base_path)
        if "\\" in path or any(part in {"..", "."} for part in path.split("/")):
            return False
        prefix = base_path.rstrip("/")
        return not prefix or path == prefix or path.startswith(prefix + "/")
    except (ValueError, httpx.InvalidURL):
        return False


def _retry_delay(response: httpx.Response, attempt: int, retry_base: float, max_delay: float) -> float | None:
    value = response.headers.get("retry-after", "").strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = retry_base * (2 ** attempt)
    # A long Retry-After means stop this bounded run, not retry before the provider permits.
    return None if seconds > max_delay else max(0.0, seconds)


async def fetch_response(
    url: str,
    *,
    allow_loopback: bool = False,
    trusted_base_url: str | None = None,
    method: str = "GET",
    json_body=None,
    headers: dict | None = None,
    timeout: float = 18,
    max_bytes: int = 4_000_000,
    max_attempts: int = 3,
    retry_base: float = 0.35,
    max_retry_delay: float = 3,
) -> FetchResponse:
    """Bounded GET retries; resolve and pin the destination on every attempt and hop."""
    method = method.upper()
    attempts = min(max(1, max_attempts), 3) if method == "GET" else 1
    original = httpx.URL(url)
    if trusted_base_url and not is_url_under_base(url, trusted_base_url):
        raise UnsafeURL("来源地址超出可信 RSSHub 配置范围")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for attempt in range(attempts):
            current = url
            current_headers = {"User-Agent": "MarketRadar/0.1 (+local news reader)", **(headers or {})}
            try:
                for _ in range(5):
                    parsed_current = httpx.URL(current)
                    if trusted_base_url and not is_url_under_base(current, trusted_base_url):
                        raise UnsafeURL("RSSHub 跳转超出可信地址范围")
                    loopback_allowed = allow_loopback and _origin(parsed_current) == _origin(original)
                    parsed, address = await resolve_public_url(current, loopback_allowed)
                    request_headers = dict(current_headers)
                    request_headers["Host"] = parsed.netloc.decode()
                    pinned = parsed.copy_with(host=address)
                    async with client.stream(
                        method, pinned, headers=request_headers, json=json_body,
                        extensions={"sni_hostname": parsed.host},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            target = response.headers.get("location")
                            if not target:
                                raise RuntimeError("来源返回了无目标的跳转")
                            if method != "GET":
                                raise RuntimeError("该 API 不允许自动跳转，请填写最终地址")
                            destination = urljoin(current, target)
                            if _origin(httpx.URL(destination)) != _origin(parsed):
                                current_headers = {k: v for k, v in current_headers.items() if k.lower() not in {
                                    "authorization", "cookie", "proxy-authorization", "if-none-match", "if-modified-since",
                                }}
                            current = destination
                            continue
                        if response.status_code == 304:
                            return FetchResponse(304, b"", dict(response.headers), str(parsed))
                        if response.status_code in {429, 500, 502, 503, 504} and attempt + 1 < attempts:
                            delay = _retry_delay(response, attempt, retry_base, max_retry_delay)
                            if delay is not None:
                                await asyncio.sleep(delay)
                                break
                        response.raise_for_status()
                        chunks, size = [], 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise RuntimeError("来源响应超过大小上限")
                            chunks.append(chunk)
                        return FetchResponse(response.status_code, b"".join(chunks), dict(response.headers), str(parsed))
                else:
                    raise RuntimeError("来源重定向次数过多")
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt + 1 >= attempts:
                    raise
                await asyncio.sleep(min(max_retry_delay, retry_base * (2 ** attempt)))
    raise RuntimeError("来源请求未完成")


async def fetch_url(url: str, **kwargs) -> bytes:
    """Backward-compatible body-only interface for existing API adapters."""
    return (await fetch_response(url, **kwargs)).body


def safe_error(error: Exception, source: str = "") -> str:
    # Avoid exposing provider exceptions: they can contain authorization headers and request URLs.
    if isinstance(error, UnsafeURL):
        return str(error)
    if isinstance(error, (httpx.TimeoutException, TimeoutError, asyncio.TimeoutError)):
        return "来源请求超时，可稍后重试"
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        return f"来源返回 HTTP {code}，请检查连接、权限或访问频率"
    if isinstance(error, httpx.TransportError):
        return "无法连接来源，请检查网络或代理配置"
    if type(error).__name__ in {"MissingCredentials", "XConnectorError", "RedditNotConnected"}:
        return str(error)[:240]
    return f"{source or '来源'}采集未完成，请检查配置后重试"


class _TextParser(HTMLParser):
    BLOCKS = {"p", "div", "section", "article", "li", "ul", "ol", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1
        elif not self.suppressed:
            if tag == "br":
                self.parts.append("\n")
            elif tag in self.BLOCKS:
                self.parts.append("\n\n")
            elif tag in {"td", "th"}:
                self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.suppressed = max(0, self.suppressed - 1)
        elif not self.suppressed and tag in self.BLOCKS:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def strip_html(value: str, *, preserve_paragraphs: bool = False) -> str:
    parser = _TextParser()
    parser.feed(value or "")
    text = "".join(parser.parts).replace("\xa0", " ")
    if not preserve_paragraphs:
        return re.sub(r"\s+", " ", text).strip()
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
