from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import threading
from pathlib import Path
from urllib.parse import urljoin, urlsplit

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


async def fetch_url(
    url: str,
    *,
    allow_loopback: bool = False,
    method: str = "GET",
    json_body=None,
    headers: dict | None = None,
    timeout: float = 18,
    max_bytes: int = 4_000_000,
) -> bytes:
    """Resolve and pin a safe destination on every hop, avoiding DNS rebinding."""
    current = url
    original_host = urlsplit(url).hostname
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for hop in range(5):
            # A configured local RSSHub may remain local; a public source must never redirect local.
            loopback_allowed = allow_loopback and urlsplit(current).hostname == original_host
            parsed, address = await resolve_public_url(current, loopback_allowed)
            request_headers = {"User-Agent": "MarketRadar/0.1 (+local news reader)", **(headers or {})}
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
                    current = urljoin(current, target)
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise RuntimeError("来源响应超过大小上限")
                    chunks.append(chunk)
                return b"".join(chunks)
        raise RuntimeError("来源重定向次数过多")


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


def strip_html(value: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()
