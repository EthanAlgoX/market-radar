"""Offline regressions: market boundaries, missingness, revisions and durable tasks."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.market.models import instrument_spec
from app.market.providers import FetchResult, ProviderError, finish_candle, normalize_binance, normalize_daily, freshness
from app.market.service import MarketService
from app.market.store import MarketStore


def crypto_bars(count=70, close=100, received_at="2026-10-02T12:00:00+00:00", symbol="BTC/USDT"):
    start = int(datetime(2026, 9, 28, tzinfo=timezone.utc).timestamp() * 1000)
    raw = [[start + i * 3_600_000, close, close + 2, close - 2, close, 10,
            start + (i + 1) * 3_600_000 - 1, 1000, 10, 5, 500, 0] for i in range(count)]
    return normalize_binance(raw, instrument_spec("crypto", symbol),
                             server_time=start + count * 3_600_000 + 1000, received_at=received_at)


def test_symbol_identity_and_units_prevent_cross_market_mix():
    assert instrument_spec("hk", "700")["symbol"] == "0700.HK"
    assert instrument_spec("cn", "000001")["symbol"] == "000001.SZ"
    assert instrument_spec("cn", "600519")["volume_unit"] == "lots_100_shares"
    assert instrument_spec("us", "AAPL")["volume_unit"] == "shares"
    assert instrument_spec("cn", "000001")["news_query"] == '平安银行 OR "Ping An Bank"'
    for market, symbol in [("us", "https://127.0.0.1"), ("crypto", "../BTC"), ("cn", "600519.SZ"), ("hk", "0"), ("cn", "430001")]:
        with pytest.raises(ValueError):
            instrument_spec(market, symbol)


def test_binance_closed_boundary_missing_and_duplicate_rejection():
    spec = instrument_spec("crypto", "BTC")
    raw = [[0, "1", "2", "1", "2", "4", 3_599_999, "6", 2, "3", "5", 0],
           [3_600_000, "2", "3", "2", "3", None, 7_199_999, "7", 3, "4", "6", 0]]
    bars = normalize_binance(raw, spec, server_time=3_601_000, received_at="2026-10-02T00:00:00+00:00")
    assert bars[0]["closed"] and not bars[1]["closed"]
    assert bars[0]["end_time"] == bars[1]["time"]
    assert bars[0]["provider_close_time"] == 3_599_999 and bars[0]["quote_volume"] == 6
    assert bars[1]["volume"] is None and "missing_ohlcv" in bars[1]["quality"]
    with pytest.raises(ProviderError, match="重复"):
        normalize_binance([raw[0], raw[0]], spec, server_time=9_000_000, received_at="now")


def test_stock_calendar_uses_early_close_and_detects_missing_session():
    spec = instrument_spec("us", "AAPL")
    rows = [{"date": date, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 50}
            for date in ("2025-11-26", "2025-11-28", "2025-12-02")]
    candles = normalize_daily(rows, spec, received_at="2025-12-03T00:00:00+00:00",
                              observed_at=datetime(2025, 12, 3, tzinfo=timezone.utc))
    assert all(bar["closed"] for bar in candles)
    # Thanksgiving closed; Black Friday session closes 13:00 EST, not normal 16:00.
    assert candles[1]["end_time"] == "2025-11-28T18:00:00+00:00"
    assert "gap_before" not in candles[1]["quality"]
    assert "gap_before" in candles[2]["quality"]  # Missing Dec 1 trading session.


def test_missing_price_and_corporate_action_are_retained_without_repair():
    rows = [{"date": "2026-09-30", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 4},
            {"date": "2026-10-01", "open": None, "high": None, "low": None, "close": None, "volume": None},
            {"date": "2026-10-02", "open": 25, "high": 26, "low": 24, "close": 25, "volume": 16, "stock_splits": 4}]
    bars = normalize_daily(rows, instrument_spec("us", "AAPL"), received_at="2026-10-03T00:00:00+00:00",
                           observed_at=datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert len(bars) == 3 and bars[1]["close"] is None
    assert "missing_ohlcv" in bars[1]["quality"]
    assert bars[2]["corporate_action"]["split_ratio"] == 4
    assert "corporate_action" in bars[2]["quality"]
    assert bars[2]["adjustment"] == "none"


def test_http_received_time_is_not_market_freshness():
    bars = crypto_bars(received_at="2026-10-03T00:00:00+00:00")
    state = freshness(instrument_spec("crypto", "BTC"), bars,
                      observed_at=datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert state["stale"]


def test_ingest_keeps_history_revises_only_market_values_and_refuses_mixing(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    instrument = store.add("crypto", "BTC")
    bars = crypto_bars(2)
    assert store.ingest(instrument["id"], bars)["new"] == 2
    replay = crypto_bars(2, received_at="2026-10-03T00:00:00+00:00")
    assert store.ingest(instrument["id"], replay)["updated"] == 0
    assert all(bar["revision"] == 1 for bar in store.candles(instrument["id"]))
    changed = crypto_bars(2, close=101)
    assert store.ingest(instrument["id"], changed)["updated"] == 2
    assert all(bar["revision"] == 2 for bar in store.candles(instrument["id"]))
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM candle_revisions").fetchone()[0] == 2
    incompatible = [{**changed[0], "provider": "other"}]
    with pytest.raises(ValueError, match="拼入"):
        store.ingest(instrument["id"], incompatible)
    with pytest.raises(ValueError, match="重复"):
        store.ingest(instrument["id"], [bars[0], bars[0]])


def test_signal_retraction_preserves_revision_record(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    instrument = store.add("crypto", "BTC")
    bars = crypto_bars(2)
    signal = {"id": "signal-one", "bar_time": bars[-1]["time"], "source_hash": "first", "summary": "fixture"}
    store.save_analysis(instrument["id"], {"signals": [signal]}, bars)
    store.save_analysis(instrument["id"], {"signals": []}, bars)
    assert store.analysis(instrument["id"])["signals"] == []
    assert store.analysis(instrument["id"])["invalidated_signal_count"] == 1
    with store.connect() as db:
        revised = db.execute("SELECT value FROM signals").fetchone()[0]
        assert '"active": false' in revised
        assert db.execute("SELECT COUNT(*) FROM signal_revisions").fetchone()[0] == 1


def test_sliding_window_does_not_retract_history_when_warmup_was_truncated(tmp_path):
    from app.market.signals import compute_signals
    store = MarketStore(tmp_path / "market.sqlite3")
    instrument = store.add("crypto", "BTC")
    bars = crypto_bars(70)
    bars[20] = finish_candle(instrument, {**bars[20], "volume": 30})
    initial = compute_signals(bars, emitted_at="2026-10-03T00:00:00+00:00", limit=1000)
    assert any(signal["rule_id"] == "volume2x" for signal in initial["signals"])
    store.save_analysis(instrument["id"], initial, bars)
    previous = store.analysis(instrument["id"])["signals"]
    shifted = bars[10:]
    rechecked = compute_signals(shifted, emitted_at="2026-10-03T00:00:00+00:00", limit=1000)
    assert not any(signal["rule_id"] == "volume2x" for signal in rechecked["signals"])
    store.save_analysis(instrument["id"], rechecked, shifted)
    assert {signal["id"] for signal in store.analysis(instrument["id"])["signals"]} == {signal["id"] for signal in previous}
    assert store.analysis(instrument["id"])["invalidated_signal_count"] == 0
    store.save_analysis(instrument["id"], rechecked, shifted, changed_times=[bars[15]["time"]])
    assert store.analysis(instrument["id"])["signals"][0]["pending_revalidation"]


def test_quality_revision_is_audited_but_server_clock_is_not(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    instrument = store.add("crypto", "BTC")
    original = crypto_bars(2)
    store.ingest(instrument["id"], original)
    clock_update = [{**bar, "provider_server_time": bar["provider_server_time"] + 1000} for bar in original]
    assert store.ingest(instrument["id"], clock_update)["updated"] == 0
    revised = finish_candle(instrument, {**original[-1], "quality": ["invalid_ohlcv"]})
    assert store.ingest(instrument["id"], [revised])["updated"] == 1
    assert store.candles(instrument["id"])[-1]["revision"] == 2
    mismatch = {**original[0], "volume_unit": "quote_asset"}
    with pytest.raises(ValueError, match="口径"):
        store.ingest(instrument["id"], [mismatch])


def test_related_news_keeps_reader_fields_and_avoids_numeric_symbol_match(tmp_path):
    item = {"id": "article", "title": "平安银行业绩", "content": "完整原文", "summary": "完整摘要",
            "source_hash": "existing-hash", "translation": {"title": "translated"}, "published_at": "2026-09-30T00:00:00+00:00"}

    class News:
        def items(self, **kwargs):
            assert "000001" not in kwargs["q"]
            return {"items": [item, {**item, "id": "irrelevant", "title": "000001 unrelated", "content": "irrelevant"}]}

    service = MarketService(tmp_path, news_store=News())
    instrument = service.add_watchlist("cn", "000001")
    candles = [{"end_time": "2026-09-30T07:00:00+00:00"}]
    related = service.related_news(instrument, candles)
    assert len(related) == 1 and related[0]["content"] == "完整原文"
    assert related[0]["source_hash"] == "existing-hash" and related[0]["translation"]
    assert "因果" in related[0]["relation"]


def test_concurrent_queue_reuse_recovery_and_delete_cascade(tmp_path):
    path = tmp_path / "market.sqlite3"
    store = MarketStore(path)
    instrument = store.add("crypto", "BTC")
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: store.enqueue([instrument["id"]]), range(4)))
    assert len({job["id"] for job in jobs}) == 1
    claimed = store.claim()
    claimed["progress"][0]["status"] = "running"
    store.save_job(claimed)
    recovered = MarketStore(path).get_job(claimed["id"])
    assert recovered["status"] == "queued" and recovered["recovered"]
    assert recovered["progress"][0]["status"] == "pending"
    store.ingest(instrument["id"], crypto_bars(2))
    store.delete(instrument["id"])
    assert not store.candles(instrument["id"])


async def test_one_provider_failure_preserves_old_data_and_other_source_success(tmp_path):
    class FakeProviders:
        fail = False

        async def fetch(self, instrument):
            if self.fail and instrument["symbol"] == "BTC/USDT":
                raise ProviderError("公开来源暂不可用")
            return FetchResult(crypto_bars(symbol=instrument["symbol"]))

    providers = FakeProviders()
    service = MarketService(tmp_path, providers=providers)
    instrument = service.add_watchlist("crypto", "BTC")
    job = service.new_job()
    await service.run_job(service.store.claim())
    assert service.get_job(job["id"])["status"] == "completed"
    previous_success = service.store.get_instrument(instrument["id"])["last_success_at"]
    providers.fail = True
    other = service.add_watchlist("crypto", "ETH")
    failed = service.new_job()
    await service.run_job(service.store.claim())
    snapshot = service.snapshot(instrument["id"])
    assert service.get_job(failed["id"])["status"] == "partial"
    assert service.store.get_instrument(other["id"])["status"] == "available"
    assert len(snapshot["candles"]) == 70 and snapshot["status"] == "error"
    assert snapshot["coverage"]["stale"]
    assert snapshot["instrument"]["last_success_at"] == previous_success
    assert snapshot["signal_analysis"]["status"] == "stale"


async def test_worker_restart_skips_completed_instruments(tmp_path):
    store = MarketStore(tmp_path / "market-radar-market.sqlite3")
    first = store.add("crypto", "BTC")
    second = store.add("crypto", "ETH")
    queued = store.enqueue([first["id"], second["id"]])
    job = store.claim()
    next(row for row in job["progress"] if row["instrument_id"] == first["id"]).update(status="completed", count=70, new=70)
    store.save_job(job)
    calls = []

    class Fake:
        async def fetch(self, instrument):
            calls.append(instrument["symbol"])
            return FetchResult(crypto_bars(symbol=instrument["symbol"]))

    service = MarketService(tmp_path, providers=Fake())
    assert service.get_job(queued["id"])["recovered"]
    await service.run_job(service.store.claim())
    assert calls == ["ETH/USDT"]
    assert service.get_job(queued["id"])["status"] == "completed"


async def test_source_budget_cancels_slow_fetch_and_retains_previous_data(tmp_path):
    cancelled = asyncio.Event()

    class Slow:
        async def fetch(self, instrument):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

    service = MarketService(tmp_path, providers=Slow())
    instrument = service.add_watchlist("crypto", "BTC")
    service.store.ingest(instrument["id"], crypto_bars(2))
    service.instrument_budget = .01
    job = service.new_job()
    await service.run_job(service.store.claim())
    assert cancelled.is_set()
    assert service.get_job(job["id"])["status"] == "failed"
    assert len(service.store.candles(instrument["id"])) == 2


async def test_deleted_queued_instrument_is_skipped_without_fetch(tmp_path):
    class NoFetch:
        async def fetch(self, instrument):
            pytest.fail("Deleted instrument must never fetch")

    service = MarketService(tmp_path, providers=NoFetch())
    instrument = service.add_watchlist("crypto", "BTC")
    job = service.new_job()
    service.delete_watchlist(instrument["id"])
    await service.run_job(service.store.claim())
    assert service.get_job(job["id"])["progress"][0]["status"] == "skipped"
