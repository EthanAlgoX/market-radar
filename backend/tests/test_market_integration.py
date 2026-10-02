"""Verify the new market surface retains the local app's isolation boundaries."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_market_api_uses_the_same_local_access_boundary(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/api/market/overview")
        assert response.status_code == 200
        assert response.json()["watchlist"] == []
        assert client.get("/api/market/overview", headers={"Host": "evil.example"}).status_code == 403
        assert client.post(
            "/api/market/watchlist", json={"market": "crypto", "symbol": "BTC/USDT"},
            headers={"Origin": "https://evil.example"},
        ).status_code == 403
        assert client.post(
            "/api/market/refresh", json={}, headers={"Sec-Fetch-Site": "cross-site"},
        ).status_code == 403
        assert client.get("/api/market/overview").json()["watchlist"] == []


def test_new_watchlist_is_persistent_without_changing_news_or_fetching_prices(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        service = client.app.state.service
        service.store.ingest({
            "external_id": "independent-personal-post", "source": "x", "source_name": "X",
            "author": "writer", "title": "Personal note", "content": "A followed author's unrelated note",
            "url": "https://x.com/writer/status/independent-personal-post", "published_at": None,
        }, "following")
        item = service.store.items()["items"][0]
        service.store.update_item(item["id"], {"bookmarked": True, "is_read": True})
        before = service.store.get_item(item["id"])
        added = client.post("/api/market/watchlist", json={"market": "crypto", "symbol": "BTC/USDT"})
        assert added.status_code in {200, 201}
        watchlist = client.get("/api/market/overview").json()["watchlist"]
        assert len(watchlist) == 1
        snapshot = client.get("/api/market/instruments/" + watchlist[0]["id"]).json()
        assert snapshot["candles"] == [] and snapshot["signals"] == []
        assert service.store.get_item(item["id"]) == before
        assert service.store.items(channel="following")["total"] == 1

    with TestClient(create_app(tmp_path)) as client:
        watchlist = client.get("/api/market/overview").json()["watchlist"]
        assert len(watchlist) == 1 and watchlist[0]["symbol"] == "BTC/USDT"
        existing = client.get("/api/items?channel=following").json()["items"][0]
        assert existing["id"] == item["id"] and existing["bookmarked"] and existing["is_read"]


def test_market_symbol_validation_cannot_configure_an_arbitrary_data_url(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        for body in [
            {"market": "us", "symbol": "http://127.0.0.1/secret"},
            {"market": "crypto", "symbol": "BTC/USDT", "url": "http://127.0.0.1/secret"},
            {"market": "cn", "symbol": "600519.SZ"},
        ]:
            assert client.post("/api/market/watchlist", json=body).status_code in {400, 422}
        assert client.get("/api/market/overview").json()["watchlist"] == []
        response = client.post("/api/market/watchlist", json={"market": "invalid", "symbol": "PRIVATE_INPUT_MARKER"})
        assert response.status_code == 422 and "PRIVATE_INPUT_MARKER" not in response.text
