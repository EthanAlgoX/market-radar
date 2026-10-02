from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.market.router import create_market_router
from app.market.service import MarketService


def test_market_api_is_lazy_bounded_and_validates_symbols(tmp_path):
    class NoFetch:
        async def fetch(self, instrument):
            raise AssertionError("Overview/add must not fetch")

    service = MarketService(tmp_path, providers=NoFetch())
    app = FastAPI()
    app.include_router(create_market_router(lambda request: service))
    with TestClient(app) as client:
        overview = client.get("/api/market/overview").json()
        assert overview["watchlist"] == [] and overview["active_job"] is None
        assert len(overview["providers"]) == 3 and overview["presets"]
        assert client.post("/api/market/watchlist", json={"market": "us", "symbol": "http://localhost"}).status_code == 400
        assert client.post("/api/market/watchlist", json={"market": "us", "symbol": "AAPL", "url": "http://localhost"}).status_code == 422
        instrument = client.post("/api/market/watchlist", json={"market": "hk", "symbol": "700"}).json()
        assert instrument["symbol"] == "0700.HK" and instrument["status"] == "idle"
        snapshot = client.get(f"/api/market/instruments/{instrument['id']}").json()
        assert snapshot["candles"] == [] and snapshot["signals"] == [] and snapshot["related_news"] == []
        assert snapshot["source_url"] == "https://finance.yahoo.com/quote/0700.HK/history/"
        assert client.get(f"/api/market/instruments/{instrument['id']}?limit=181").status_code == 422
        first = client.post("/api/market/refresh", json={}).json()
        assert client.post("/api/market/refresh", json={"ids": [instrument["id"]]}).json()["id"] == first["id"]
        assert client.get(f"/api/market/jobs/{first['id']}").json()["status"] == "queued"
        assert client.post("/api/market/refresh", json={"ids": ["not-existing"]}).status_code == 400
        assert client.delete(f"/api/market/watchlist/{instrument['id']}").status_code == 200
        assert client.get(f"/api/market/instruments/{instrument['id']}").status_code == 404


def test_market_watchlist_maximum_is_enforced_without_network(tmp_path):
    service = MarketService(tmp_path)
    for index in range(20):
        service.add_watchlist("us", "T" + str(index))
    app = FastAPI()
    app.include_router(create_market_router(lambda request: service))
    with TestClient(app) as client:
        assert client.post("/api/market/watchlist", json={"market": "us", "symbol": "MORE"}).status_code == 400
        # Re-adding an existing instrument is idempotent even at capacity.
        assert client.post("/api/market/watchlist", json={"market": "us", "symbol": "T0"}).status_code == 201
