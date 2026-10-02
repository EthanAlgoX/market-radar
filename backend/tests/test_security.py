import socket

import httpx
import pytest

from app.security import SecretStore, UnsafeURL, fetch_url, resolve_public_url


def test_secret_store_roundtrip_encryption_permissions(tmp_path):
    secrets = SecretStore(tmp_path)
    secrets.set("reddit_token", {"value": "sensitive-token"})
    assert SecretStore(tmp_path).get("reddit_token") == {"value": "sensitive-token"}
    assert "sensitive-token" not in (tmp_path / "secrets.enc").read_text()
    assert (tmp_path / ".secrets.key").stat().st_mode & 0o777 == 0o600
    secrets.delete("reddit_token")
    assert secrets.get("reddit_token") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.2", "224.0.0.1", "0.0.0.0"])
async def test_private_metadata_dns_are_blocked(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))])
    with pytest.raises(UnsafeURL):
        await resolve_public_url("http://public-looking.example/feed")


@pytest.mark.asyncio
async def test_only_explicit_loopback_exception_is_allowed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 1200))])
    _, address = await resolve_public_url("http://localhost:1200", allow_loopback=True)
    assert address == "127.0.0.1"
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.1", 80))])
    with pytest.raises(UnsafeURL):
        await resolve_public_url("http://private.example", allow_loopback=True)


@pytest.mark.asyncio
async def test_fetch_pins_dns_and_blocks_redirect_to_private(monkeypatch):
    seen = []
    def dns(host, *a, **kw):
        ip = "127.0.0.1" if host == "localhost" else "8.8.8.8"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    def response(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "http://localhost/private"})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(response), **kwargs))
    with pytest.raises(UnsafeURL):
        await fetch_url("https://news.example/feed")
    assert len(seen) == 1
    assert seen[0].url.host == "8.8.8.8"
    assert seen[0].headers["Host"] == "news.example"
    assert seen[0].extensions["sni_hostname"] == "news.example"
