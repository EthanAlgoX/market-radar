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

from app.security import fetch_response, is_url_under_base, strip_html


def mock_public_transport(monkeypatch, handler):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.asyncio
async def test_response_metadata_304_and_body_compatibility(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(304, headers={"ETag": '"one"', "Last-Modified": "Fri, 02 Oct 2026 04:00:00 GMT"})

    mock_public_transport(monkeypatch, handler)
    response = await fetch_response("https://publisher.example/feed", headers={"If-None-Match": '"one"'})
    assert response.status_code == 304 and response.body == b""
    assert response.final_url == "https://publisher.example/feed"
    assert response.headers["etag"] == '"one"'
    assert seen[0].headers["If-None-Match"] == '"one"'
    assert await fetch_url("https://publisher.example/feed") == b""


@pytest.mark.asyncio
async def test_get_retries_5xx_at_most_three_times_and_resolves_each_attempt(monkeypatch):
    requests, delays = [], []

    def handler(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) < 3 else 200, content=b"ok")

    async def sleep(seconds):
        delays.append(seconds)

    mock_public_transport(monkeypatch, handler)
    monkeypatch.setattr("app.security.asyncio.sleep", sleep)
    response = await fetch_response("https://publisher.example/feed", max_attempts=99)
    assert response.body == b"ok" and len(requests) == 3
    assert delays == [0.35, 0.7]
    assert all(request.url.host == "8.8.8.8" and request.headers["Host"] == "publisher.example" for request in requests)


@pytest.mark.asyncio
async def test_long_retry_after_stops_run_without_premature_retry(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    mock_public_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_response("https://publisher.example/feed")
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method,status", [("GET", 403), ("POST", 503)])
async def test_permissions_and_non_idempotent_requests_are_not_retried(monkeypatch, method, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status)

    mock_public_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_response("https://publisher.example/api", method=method)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_byte_limit_is_enforced_without_retry(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b"oversized")

    mock_public_transport(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="大小上限"):
        await fetch_response("https://publisher.example/feed", max_bytes=3)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_cross_origin_redirect_drops_credentials_and_conditional_headers(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/feed"}) if len(requests) == 1 else httpx.Response(200, content=b"ok")

    mock_public_transport(monkeypatch, handler)
    response = await fetch_response("https://publisher.example/feed", headers={"Authorization": "Bearer fake", "Cookie": "fake=1", "If-None-Match": "old"})
    assert response.final_url == "https://other.example/feed"
    assert "authorization" not in requests[1].headers and "cookie" not in requests[1].headers
    assert "if-none-match" not in requests[1].headers


@pytest.mark.parametrize("url", [
    "http://localhost:1200/rss-evil/feed", "http://localhost:9999/rss/feed",
    "https://localhost:1200/rss/feed", "http://localhost.evil:1200/rss/feed",
    "http://user@localhost:1200/rss/feed", "http://localhost:1200/rss/%2e%2e/private",
    "http://localhost:1200/rss/%252e%252e/private",
])
def test_trusted_hub_scope_rejects_prefix_origin_credentials_and_traversal(url):
    assert not is_url_under_base(url, "http://localhost:1200/rss")
    assert is_url_under_base("http://localhost:1200/rss/cls/telegraph?limit=5", "http://localhost:1200/rss")


@pytest.mark.asyncio
async def test_trusted_loopback_cannot_redirect_outside_base_or_to_another_port(monkeypatch):
    seen = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 1200))])
    original = httpx.AsyncClient

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "http://localhost:1200/private"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(UnsafeURL):
        await fetch_response("http://localhost:1200/rss/cls", allow_loopback=True, trusted_base_url="http://localhost:1200/rss")
    assert len(seen) == 1
    seen.clear()
    # The older explicit exception is restricted to the same origin too.
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(lambda req: httpx.Response(302, headers={"Location": "http://localhost:9999/feed"})), **kwargs))
    with pytest.raises(UnsafeURL):
        await fetch_response("http://localhost:1200/feed", allow_loopback=True)


def test_paragraph_extraction_omits_scripts_preserves_breaks_and_plain_comparisons():
    assert strip_html("<p>One &amp; two</p><script>leak()</script><p>Three<br>Four</p>", preserve_paragraphs=True) == "One & two\n\nThree\nFour"
    assert strip_html("Market < 5 and earnings > 2") == "Market < 5 and earnings > 2"
