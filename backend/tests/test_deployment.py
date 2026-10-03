import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.deployment import DeploymentURL
from app.main import create_app


PUBLIC_URL = "https://myaistock.top/market-radar/"
CALLBACK = PUBLIC_URL + "api/connections/reddit/callback"


@pytest.mark.parametrize("value", [
    "https://myaistock.top/market-radar", "https://MYAISTOCK.TOP:443/market-radar/",
])
def test_public_url_normalizes_one_explicit_https_origin_and_path(value):
    parsed = DeploymentURL.parse(value)
    assert parsed.base_url == PUBLIC_URL
    assert parsed.origin == "https://myaistock.top"
    assert parsed.authority == "myaistock.top"
    assert parsed.base_path == "/market-radar"
    assert parsed.reddit_callback == CALLBACK


@pytest.mark.parametrize("value", [
    "//myaistock.top/market-radar", "http://myaistock.top/market-radar/",
    "https://user:private@example.com/market-radar/", "https://example.com/?token=private",
    "https://example.com/?", "https://example.com/#", "https://example.com/path#fragment",
    "https://*.example.com/", "https://example.com:/", "https://example.com:0/",
    "https://example.com:99999/", "https://example.com/../private", "https://example.com/./private",
    "https://example.com/%2e%2e/private", "https://example.com/path%2fprivate",
    "https://example.com//private", "https://example.com/private//", "https://example.com\\private",
    "https://example.com/ private", "https://example.com/\nprivate", " https://example.com/",
])
def test_invalid_public_url_fails_before_application_startup_without_echoing_url(value, tmp_path):
    with pytest.raises(ValueError, match="RADAR_PUBLIC_URL") as error:
        create_app(tmp_path, public_url=value)
    assert value not in str(error.value)
    assert "token=private" not in str(error.value)


def test_public_url_environment_applies_root_path_and_exact_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("RADAR_PUBLIC_URL", PUBLIC_URL)
    app = create_app(tmp_path)
    assert app.root_path == "/market-radar"
    with TestClient(app, base_url="https://myaistock.top") as client:
        response = client.get("/api/settings", headers={"Origin": "https://myaistock.top", "Sec-Fetch-Site": "same-origin"})
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://myaistock.top"
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/market-radar/api/health").json()["status"] == "ok"
        assert client.get("/market-radar/api/health").headers["Cache-Control"] == "no-store"
        assert "/market-radar/openapi.json" in client.get("/docs").text
        assert client.get("/openapi.json").json()["servers"] == [{"url": "/market-radar"}]


@pytest.mark.parametrize("header,value", [
    ("Origin", "https://malicious.example"), ("Origin", "https://myaistock.top.evil.example"),
    ("Origin", "http://myaistock.top"), ("Origin", "https://myaistock.top/market-radar/"),
    ("Origin", "null"), ("Origin", ""), ("Host", "evil.example"),
    ("Host", "myaistock.top.evil.example"), ("Host", "myaistock.top:1234"),
    ("Host", "evil.example@myaistock.top"), ("Host", "myaistock.top/"),
    ("Host", "myaistock.top?private"), ("Host", "myaistock.top:"), ("Host", "myaistock.top,evil.example"),
    ("Sec-Fetch-Site", "cross-site"),
])
def test_hosted_requests_reject_unconfigured_authorities_origins_and_cross_site(header, value, tmp_path):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        assert client.get("/api/settings", headers={header: value}).status_code == 403


def test_forwarded_headers_neither_authorize_host_nor_change_callback(tmp_path):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        proxy_headers = {"Forwarded": 'host="evil.example";proto=http', "X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "http"}
        response = client.get("/api/connections", headers=proxy_headers)
        assert response.status_code == 200
        assert response.json()["reddit"]["redirect_uri"] == CALLBACK
        assert response.json()["x"]["browser_login_available"] is False
        assert client.get("/api/settings", headers={**proxy_headers, "Host": "evil.example", "X-Forwarded-Host": "myaistock.top"}).status_code == 403
        assert client.get("/api/settings", headers=[("Origin", "https://myaistock.top"), ("Origin", "https://evil.example")]).status_code == 403
        assert client.get("/api/settings", headers=[("Host", "myaistock.top"), ("Host", "evil.example")]).status_code == 403


def test_default_local_mode_does_not_trust_public_host_or_origin(tmp_path):
    with TestClient(create_app(tmp_path, public_url="")) as client:
        assert client.get("/api/settings", headers={"Host": "myaistock.top"}).status_code == 403
        assert client.get("/api/settings", headers={"Origin": "https://myaistock.top"}).status_code == 403
        assert client.get("/api/connections").json()["x"]["browser_login_available"] is True
        assert client.get("/api/connections").json()["reddit"]["redirect_uri"] == "http://localhost:8787/api/connections/reddit/callback"


def test_explicit_public_port_is_enforced(tmp_path):
    with TestClient(create_app(tmp_path, public_url="https://example.com:9443/radar/"), base_url="https://example.com:9443") as client:
        assert client.get("/api/health", headers={"Origin": "https://example.com:9443"}).status_code == 200
        assert client.get("/api/health", headers={"Host": "example.com"}).status_code == 403
        assert client.get("/api/health", headers={"Origin": "https://example.com"}).status_code == 403


@pytest.mark.parametrize("redirect_uri", [
    "http://localhost:8787/api/connections/reddit/callback", "https://evil.example/callback",
    "https://myaistock.top/api/connections/reddit/callback", CALLBACK + "?next=https://evil.example",
    CALLBACK + "#fragment", CALLBACK.replace("/api/", "/%2e%2e/api/"),
])
def test_hosted_reddit_config_rejects_wrong_callback_without_modifying_secrets(redirect_uri, tmp_path):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        response = client.post("/api/connections/reddit/config", json={"client_id": "new-client", "client_secret": "never-return", "redirect_uri": redirect_uri})
        assert response.status_code == 422
        assert "never-return" not in response.text
        assert client.app.state.service.secrets.get("reddit_client_id") is None


@pytest.mark.parametrize("include_callback", [False, True])
def test_hosted_reddit_config_defaults_to_public_callback_and_authorizes_it(include_callback, tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        payload = {"client_id": "new-client", "client_secret": "never-return"}
        if include_callback:
            payload["redirect_uri"] = CALLBACK
        response = client.post("/api/connections/reddit/config", json=payload)
        assert response.status_code == 200 and response.json()["redirect_uri"] == CALLBACK
        assert "never-return" not in response.text
        reddit = client.app.state.service.reddit
        assert reddit.secrets.get("reddit_redirect_uri") == CALLBACK
        fake_client = SimpleNamespace(auth=SimpleNamespace(url=lambda **kwargs: "https://www.reddit.com/api/v1/authorize?redirect_uri=" + reddit.secrets.get("reddit_redirect_uri")), _core=SimpleNamespace(close=lambda: None))
        monkeypatch.setattr(reddit, "_client", lambda authenticated=True: fake_client)
        assert CALLBACK in client.get("/api/connections/reddit/authorize").json()["url"]


def test_relocated_reddit_configuration_requires_new_callback_before_oauth(tmp_path):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        reddit = client.app.state.service.reddit
        reddit.config("old-client", None, "http://localhost:8787/api/connections/reddit/callback")
        assert client.get("/api/connections").json()["reddit"]["redirect_uri"] == CALLBACK
        response = client.get("/api/connections/reddit/authorize")
        assert response.status_code == 400
        assert reddit.secrets.get("reddit_oauth_state") is None


@pytest.mark.parametrize("prefixed", [False, True])
@pytest.mark.parametrize("outcome", ["connected", "cancelled", "error"])
def test_reddit_callback_redirects_to_public_subpath_and_keeps_cross_site_state_checks(outcome, prefixed, tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top", follow_redirects=False) as client:
        reddit = client.app.state.service.reddit
        reddit.secrets.set("reddit_oauth_state", {"state": "valid", "expires_at": time.time() + 100, "generation": reddit.generation})
        async def callback(code, state):
            assert code == "private-code"
            reddit.consume_state(state)
            if outcome == "error":
                raise RuntimeError("private-server-error")
        monkeypatch.setattr(reddit, "callback", callback)
        path = ("/market-radar" if prefixed else "") + "/api/connections/reddit/callback"
        params = {"state": "valid", "error": "access_denied"} if outcome == "cancelled" else {"state": "valid", "code": "private-code"}
        response = client.get(path, params=params, headers={"Sec-Fetch-Site": "cross-site", "X-Forwarded-Host": "evil.example"})
        assert response.status_code == 307
        assert response.headers["Location"] == PUBLIC_URL + f"?connection=reddit&status={outcome}"
        assert "private-code" not in response.text and "private-server-error" not in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get(path, params=params, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 400
        assert client.post(path, params=params, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_hosted_x_login_does_not_open_server_browser_but_cookie_import_remains_available(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        called = []
        async def start_login():
            called.append("browser")
        async def save_cookies(value):
            called.append("import")
            assert value == "private-session"
            return {"status": "connected", "state": "connected"}
        monkeypatch.setattr(client.app.state.service.x, "start_login", start_login)
        monkeypatch.setattr(client.app.state.service.x, "save_cookies", save_cookies)
        response = client.post("/api/connections/x/login")
        assert response.status_code == 400 and "Import" in response.json()["detail"]
        assert client.post("/api/connections/x/cookies", json={"cookies": "private-session"}).status_code == 200
        assert called == ["import"]


@pytest.mark.parametrize("prefixed", [False, True])
def test_reverse_proxy_modes_serve_asset_files_favicon_docs_and_api(tmp_path, monkeypatch, prefixed):
    import app.main as main
    frontend = tmp_path / "frontend" / "dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    html = '<!doctype html><script type="module" src="/market-radar/assets/entry.js"></script>'
    javascript = 'document.body.dataset.marketRadar = "ready";'
    stylesheet = 'body { color: rgb(21, 31, 49); }'
    icon = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="2"/></svg>'
    (frontend / "index.html").write_text(html)
    (assets / "entry.js").write_text(javascript)
    (assets / "entry.css").write_text(stylesheet)
    (frontend / "favicon.svg").write_text(icon)
    monkeypatch.setattr(main, "ROOT", tmp_path / "backend")
    prefix = "/market-radar" if prefixed else ""
    with TestClient(main.create_app(tmp_path / "data", public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        assert client.get(prefix + "/").text == html
        for name, content, mime in [("entry.js", javascript, "text/javascript"), ("entry.css", stylesheet, "text/css")]:
            response = client.get(prefix + "/assets/" + name)
            assert response.status_code == 200
            assert response.text == content
            assert response.headers["content-type"].split(";")[0] == mime
        assert client.get(prefix + "/assets/missing.js").status_code == 404
        favicon = client.get(prefix + "/favicon.svg")
        assert favicon.status_code == 200 and favicon.text == icon
        assert favicon.headers["content-type"].split(";")[0] == "image/svg+xml"
        assert client.get(prefix + "/api/health").json()["status"] == "ok"
        assert client.get(prefix + "/api/health").headers["Cache-Control"] == "no-store"
        assert "/market-radar/openapi.json" in client.get(prefix + "/docs").text
        assert client.get(prefix + "/openapi.json").json()["servers"] == [{"url": "/market-radar"}]


@pytest.mark.parametrize("prefixed", [False, True])
def test_production_frontend_bundle_is_served_in_both_proxy_modes(tmp_path, prefixed):
    import app.main as main
    frontend = Path(main.ROOT).parent / "frontend" / "dist"
    files = list((frontend / "assets").glob("*.js")) + list((frontend / "assets").glob("*.css"))
    if not files:
        pytest.skip("Build the frontend to smoke test its production bundles.")
    prefix = "/market-radar" if prefixed else ""
    with TestClient(main.create_app(tmp_path / "data", public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        for asset in files:
            response = client.get(prefix + "/assets/" + asset.name)
            assert response.status_code == 200
            assert response.content == asset.read_bytes()
            assert response.headers["content-type"].split(";")[0] == ("text/javascript" if asset.suffix == ".js" else "text/css")


ENTRY_HEADERS = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}


@pytest.mark.parametrize("prefixed", [False, True])
@pytest.mark.parametrize("entry", ["/", "/index.html"])
def test_hosted_homepage_accepts_top_level_navigation_from_external_links(tmp_path, monkeypatch, prefixed, entry):
    import app.main as main
    frontend = tmp_path / "frontend" / "dist"
    frontend.mkdir(parents=True)
    html = "<!doctype html><title>Market Radar</title><main>News workspace</main>"
    (frontend / "index.html").write_text(html)
    monkeypatch.setattr(main, "ROOT", tmp_path / "backend")
    prefix = "/market-radar" if prefixed else ""
    with TestClient(main.create_app(tmp_path / "data", public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        response = client.get(prefix + entry, headers=ENTRY_HEADERS)
        assert response.status_code == 200 and response.text == html
        assert response.headers["content-type"].split(";")[0] == "text/html"
        assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("prefixed", [False, True])
@pytest.mark.parametrize("method,path,changes", [
    ("GET", "/api/settings", {}), ("GET", "/api/health", {}),
    ("POST", "/api/collect", {}), ("PUT", "/api/settings", {}),
    ("POST", "/", {}), ("HEAD", "/index.html", {}),
    ("GET", "/docs", {}), ("GET", "/assets/entry.js", {}),
    ("GET", "/", {"Sec-Fetch-Mode": "cors"}),
    ("GET", "/", {"Sec-Fetch-Mode": "no-cors"}),
    ("GET", "/index.html", {"Sec-Fetch-Dest": "iframe"}),
    ("GET", "/index.html", {"Sec-Fetch-Dest": "empty"}),
])
def test_public_navigation_exception_does_not_allow_cross_site_api_mutations_fetches_or_embeds(tmp_path, prefixed, method, path, changes):
    prefix = "/market-radar" if prefixed else ""
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        assert client.request(method, prefix + path, headers={**ENTRY_HEADERS, **changes}).status_code == 403


@pytest.mark.parametrize("headers", [
    {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"},
    {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Dest": "document"},
    {**ENTRY_HEADERS, "Host": "evil.example", "X-Forwarded-Host": "myaistock.top"},
    {**ENTRY_HEADERS, "Origin": "https://github.com"},
])
def test_homepage_navigation_keeps_host_origin_and_fetch_metadata_validation(tmp_path, headers):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        assert client.get("/", headers=headers).status_code == 403


def test_homepage_navigation_rejects_duplicate_fetch_metadata(tmp_path):
    with TestClient(create_app(tmp_path, public_url=PUBLIC_URL), base_url="https://myaistock.top") as client:
        duplicated_mode = list(ENTRY_HEADERS.items()) + [("Sec-Fetch-Mode", "cors")]
        duplicated_dest = list(ENTRY_HEADERS.items()) + [("Sec-Fetch-Dest", "iframe")]
        assert client.get("/", headers=duplicated_mode).status_code == 403
        assert client.get("/", headers=duplicated_dest).status_code == 403


@pytest.mark.parametrize("entry", ["/", "/index.html"])
def test_local_default_keeps_cross_site_navigation_blocked(tmp_path, entry):
    with TestClient(create_app(tmp_path, public_url=""), base_url="http://localhost:8787") as client:
        assert client.get(entry, headers=ENTRY_HEADERS).status_code == 403
