"""Offline request-order regressions; no real SDK or HTTP requests."""

import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.market import providers
from app.market.models import instrument_spec
from app.market.signals import compute_signals
from app.market.store import MarketStore
from app.market.service import MarketService


END = int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp() * 1000)
AS_OF = "2026-10-01T12:00:03+00:00"


def raw_window(last_close):
    start = END - 21 * 3_600_000
    return [[start + index * 3_600_000, close, close + 1, close - .5, close, 100,
             start + (index + 1) * 3_600_000 - 1, 10_000, 10, 50, 5_000, 0]
            for index, close in enumerate([100.0] * 20 + [last_close])]


async def test_clock_is_captured_before_candles_so_cross_boundary_payload_stays_open(monkeypatch):
    calls = []
    phase = 0

    async def fake_response(url, **kwargs):
        calls.append(url)
        if url.endswith("/time"):
            # The first response crosses the hour after the live kline payload
            # was prepared. Capturing a later clock would falsely confirm it.
            first_in_round = len(calls) % 2 == 1
            clock = END - 250 if phase == 0 and first_in_round else END + 1500
            payload = {"serverTime": clock}
        else:
            payload = raw_window(120.0 if phase == 0 else 99.0)
        return SimpleNamespace(body=json.dumps(payload).encode())

    monkeypatch.setattr(providers, "fetch_response", fake_response)
    monkeypatch.setattr(providers, "now_iso", lambda: AS_OF)
    client = providers.PublicMarketProviders()
    instrument = instrument_spec("crypto", "BTC")
    live = await client.fetch(instrument)
    assert calls[0].endswith("/time") and "/klines?" in calls[1]
    assert live.candles[-1]["close"] == 120.0 and not live.candles[-1]["closed"]
    initial = compute_signals(live.candles, rule_ids=["breakout20"], emitted_at=AS_OF)
    assert initial["status"] == "waiting_close" and initial["signals"] == []

    # The next refresh reads the finished bar; the earlier partial price is
    # replaced before it becomes eligible for a formal rule.
    phase = 1
    final = await client.fetch(instrument)
    assert final.candles[-1]["closed"] and final.candles[-1]["close"] == 99.0
    assert compute_signals(final.candles, rule_ids=["breakout20"], emitted_at=AS_OF)["signals"] == []


async def test_preceding_server_clock_can_confirm_already_closed_payload(monkeypatch):
    calls = []

    async def fake_response(url, **kwargs):
        calls.append(url)
        payload = {"serverTime": END + 1500} if url.endswith("/time") else raw_window(120.0)
        return SimpleNamespace(body=json.dumps(payload).encode())

    monkeypatch.setattr(providers, "fetch_response", fake_response)
    monkeypatch.setattr(providers, "now_iso", lambda: AS_OF)
    result = await providers.PublicMarketProviders().fetch(instrument_spec("crypto", "BTC"))
    assert calls[0].endswith("/time") and result.candles[-1]["closed"]
    event, = compute_signals(result.candles, rule_ids=["breakout20"], emitted_at=AS_OF)["signals"]
    assert event["evidence"]["close"] == 120.0


def daily_rows(dates, close):
    return [{"date": date, "open": close, "high": close + 1, "low": close - .5,
             "close": close, "volume": 100.0} for date in dates]


def daily_windows(instrument):
    import exchange_calendars as xcals

    calendar = xcals.get_calendar("XNYS", start="2023-10-01", end="2025-10-01")
    old_dates = [session.date().isoformat() for session in calendar.sessions
                 if session.date().isoformat() <= "2024-01-31"][-60:]
    new_dates = [session.date().isoformat() for session in calendar.sessions
                 if session.date().isoformat() >= "2025-01-02"][:180]
    assert len(old_dates) == 60 and len(new_dates) == 180
    observed = datetime(2026, 10, 3, tzinfo=UTC)
    old = providers.normalize_daily(daily_rows(old_dates, 100.0), instrument,
                                    received_at=observed.isoformat(), observed_at=observed)
    incoming = providers.normalize_daily(daily_rows(new_dates, 120.0), instrument,
                                         received_at=observed.isoformat(), observed_at=observed)
    return old, incoming, observed


def test_stored_stock_predecessor_cannot_supply_warmup_across_missing_sessions(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    instrument = store.add("us", "AAPL")
    old, incoming, observed = daily_windows(instrument)
    # Both finite responses are internally contiguous. Only storage can see
    # the missing sessions at their join.
    assert incoming[0]["quality"] == []
    store.ingest(instrument["id"], old)
    changes = store.ingest(instrument["id"], incoming)
    merged = store.candles(instrument["id"], 240)
    first_new = merged[60]
    assert "gap_before" in first_new["quality"]
    assert first_new["source_hash"] != incoming[0]["source_hash"]
    result = compute_signals(merged, rule_ids=["sma20_60"], emitted_at=observed.isoformat(), limit=1000)
    assert result["signals"] == []
    assert result["indicators"][60]["ma20"] is None and result["indicators"][60]["ma60"] is None
    store.save_analysis(instrument["id"], result, merged, changed_times=changes["changed_times"])
    assert store.analysis(instrument["id"])["signals"] == []


def test_filling_missing_stock_session_clears_successor_gap_and_audits_revision(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    instrument = store.add("us", "AAPL")
    observed = datetime(2026, 10, 3, tzinfo=UTC)
    existing = providers.normalize_daily(daily_rows(["2025-09-30", "2025-10-02"], 100.0), instrument,
                                         received_at=observed.isoformat(), observed_at=observed)
    assert "gap_before" in existing[-1]["quality"]
    store.ingest(instrument["id"], existing)
    before = store.candles(instrument["id"])[-1]
    missing = providers.normalize_daily(daily_rows(["2025-10-01"], 100.0), instrument,
                                        received_at=observed.isoformat(), observed_at=observed)
    changes = store.ingest(instrument["id"], missing)
    after = store.candles(instrument["id"])
    assert len(after) == 3 and all("gap_before" not in bar["quality"] for bar in after)
    assert changes["new"] == 1 and changes["updated"] == 1
    assert after[-1]["revision"] == 2 and after[-1]["source_hash"] != before["source_hash"]
    assert after[-1]["time"] in changes["changed_times"]
    with store.connect() as db:
        previous = json.loads(db.execute("SELECT value FROM candle_revisions WHERE time=?", (after[-1]["time"],)).fetchone()[0])
    assert "gap_before" in previous["quality"]


@pytest.mark.parametrize("flag", ["missing_ohlcv", "invalid_ohlcv", "calendar_unconfirmed",
                                  "non_trading_session", "invalid_interval", "large_price_change_unverified"])
def test_invalid_closed_quality_cannot_claim_current_market_freshness(flag):
    spec = instrument_spec("crypto", "BTC")
    candles = providers.normalize_binance(raw_window(120.0), spec, server_time=END + 1500, received_at=AS_OF)
    candles[-1] = providers.finish_candle(spec, {**candles[-1], "quality": [flag]})
    observed = datetime.fromisoformat(AS_OF)
    assert providers.usable_closed_candles(candles, observed_at=observed)[-1]["time"] == candles[-2]["time"]
    assert providers.freshness(spec, candles, observed_at=observed)["stale"]


@pytest.mark.parametrize("price", [None, float("nan"), float("inf")])
def test_nonfinite_or_missing_last_price_cannot_be_the_last_usable_closed_bar(price):
    spec = instrument_spec("crypto", "BTC")
    candles = providers.normalize_binance(raw_window(120.0), spec, server_time=END + 1500, received_at=AS_OF)
    candles[-1]["close"] = price  # Independent gate must work even before provider quality normalization.
    observed = datetime.fromisoformat(AS_OF)
    assert providers.usable_closed_candles(candles, observed_at=observed)[-1]["time"] == candles[-2]["time"]
    assert providers.freshness(spec, candles, observed_at=observed)["stale"]


@pytest.mark.parametrize("boundary", ["gap_before", "corporate_action"])
def test_boundary_only_quality_keeps_its_own_closed_quote_usable(boundary):
    spec = instrument_spec("crypto", "BTC")
    candles = providers.normalize_binance(raw_window(120.0), spec, server_time=END + 1500, received_at=AS_OF)
    candles[-1]["quality"] = [boundary]
    observed = datetime.fromisoformat(AS_OF)
    assert providers.usable_closed_candles(candles, observed_at=observed)[-1]["time"] == candles[-1]["time"]
    assert not providers.freshness(spec, candles, observed_at=observed)["stale"]


def test_snapshot_distinguishes_raw_closed_from_usable_closed_timestamp(tmp_path, monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(AS_OF).astimezone(tz or UTC)

    monkeypatch.setattr(providers, "datetime", FrozenDatetime)
    service = MarketService(tmp_path)
    instrument = service.add_watchlist("crypto", "BTC")
    candles = providers.normalize_binance(raw_window(120.0), instrument, server_time=END + 1500, received_at=AS_OF)
    candles[-1] = providers.finish_candle(instrument, {**candles[-1], "close": None})
    service.store.ingest(instrument["id"], candles)
    snapshot = service.snapshot(instrument["id"])
    assert snapshot["coverage"]["last_raw_closed_bar_at"] == candles[-1]["end_time"]
    assert snapshot["coverage"]["last_closed_bar_at"] == candles[-2]["end_time"]
    assert snapshot["coverage"]["stale"]


async def test_ingest_reconciled_gap_updates_instrument_overview_and_snapshot_quality(tmp_path, monkeypatch):
    from app.market import service as service_module

    class FakeProvider:
        async def fetch(self, instrument):
            return providers.FetchResult(incoming)

    service = MarketService(tmp_path, providers=FakeProvider())
    instrument = service.add_watchlist("us", "AAPL")
    old, incoming, observed = daily_windows(instrument)
    monkeypatch.setattr(service_module, "now_iso", lambda: observed.isoformat())
    service.store.ingest(instrument["id"], old)
    job = service.new_job()
    await service.run_job(service.store.claim())
    assert service.get_job(job["id"])["status"] == "partial"
    stored = service.store.get_instrument(instrument["id"])
    assert stored["status"] == "partial" and stored["quality"]["gaps"] == 1
    overview = service.overview()["watchlist"][0]
    snapshot = service.snapshot(instrument["id"])
    assert overview["quality"] == stored["quality"] == snapshot["quality"]
    assert snapshot["signals"] == []


@pytest.mark.parametrize("inverted", [True, False])
def test_high_low_order_is_gated_but_auction_open_and_close_may_be_outside_range(inverted):
    spec = instrument_spec("crypto", "BTC")
    candles = providers.normalize_binance(raw_window(102.0), spec, server_time=END + 1500, received_at=AS_OF)
    candles[-1].update(open=103.0, high=99.0 if inverted else 101.0, low=101.0 if inverted else 99.0)
    raw_gate = compute_signals(candles, rule_ids=["breakout20"], emitted_at=AS_OF)
    usable = providers.usable_closed_candles(candles, observed_at=datetime.fromisoformat(AS_OF))
    finished = providers.finish_candle(spec, dict(candles[-1]))
    if inverted:
        assert raw_gate["status"] == "quality_blocked" and raw_gate["signals"] == []
        assert "invalid_ohlcv" in finished["quality"]
        assert usable[-1]["time"] == candles[-2]["time"]
    else:
        assert len(raw_gate["signals"]) == 1 and "invalid_ohlcv" not in finished["quality"]
        assert usable[-1]["time"] == candles[-1]["time"]


def fake_yahoo(monkeypatch, metadata, market, *, metadata_error=False):
    import pandas as pd

    calls = []
    zone = "America/New_York" if market == "us" else "Asia/Hong_Kong"
    frame = pd.DataFrame({"Open": [100.0, 25.0], "High": [101.0, 26.0], "Low": [99.0, 24.0],
                          "Close": [100.0, 25.0], "Volume": [10.0, 40.0],
                          "Dividends": [.25, 0.0], "Stock Splits": [0.0, 4.0]},
                         index=pd.date_range("2026-09-30", periods=2, tz=zone))

    class FakeTicker:
        def __init__(self, symbol):
            calls.append(("ticker", symbol))

        def history(self, **kwargs):
            calls.append(("history", kwargs))
            return frame

        def get_history_metadata(self):
            calls.append(("metadata", None))
            if metadata_error:
                raise RuntimeError("PRIVATE_PROVIDER_METADATA_MARKER")
            return metadata

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=FakeTicker))
    return calls


@pytest.mark.parametrize(("market", "symbol", "metadata", "error_key"), [
    ("us", "BTC-USD", {"currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": "CRYPTOCURRENCY"}, "type"),
    ("hk", "2800.HK", {"currency": "USD", "exchangeTimezoneName": "Asia/Hong_Kong", "instrumentType": "ETF"}, "market"),
    ("hk", "2800.HK", {"currency": "CNY", "exchangeTimezoneName": "Asia/Hong_Kong", "instrumentType": "ETF"}, "market"),
    ("us", "AAPL", {"currency": "USD", "exchangeTimezoneName": "Asia/Hong_Kong", "instrumentType": "EQUITY"}, "market"),
    ("us", "AAPL", {"exchangeTimezoneName": "America/New_York", "instrumentType": "EQUITY"}, "missing"),
    ("us", "AAPL", {"currency": "USD", "instrumentType": "EQUITY"}, "missing"),
    ("hk", "0700.HK", {"currency": "HKD", "exchangeTimezoneName": "Asia/Hong_Kong"}, "missing"),
    ("hk", "0700.HK", None, "missing"),
])
def test_yahoo_mismatched_or_missing_asset_identity_is_rejected(monkeypatch, market, symbol, metadata, error_key):
    calls = fake_yahoo(monkeypatch, metadata, market)
    with pytest.raises(providers.ProviderError) as error:
        providers._sdk_rows(market, symbol)
    assert str(error.value) == providers._YAHOO_IDENTITY_ERRORS[error_key]
    assert symbol not in str(error.value) and "CRYPTOCURRENCY" not in str(error.value)
    assert [name for name, _ in calls] == ["ticker", "history", "metadata"]


@pytest.mark.parametrize(("market", "symbol", "currency", "zone", "kind"), [
    ("us", "AAPL", "USD", "America/New_York", "EQUITY"),
    ("us", "GLD", "USD", "America/New_York", "ETF"),
    ("hk", "0700.HK", "HKD", "Asia/Hong_Kong", "EQUITY"),
    ("hk", "2800.HK", "HKD", "Asia/Hong_Kong", "ETF"),
])
def test_yahoo_equity_and_etf_identity_keeps_original_prices_and_actions(monkeypatch, market, symbol, currency, zone, kind):
    metadata = {"currency": currency, "exchangeTimezoneName": zone, "instrumentType": kind}
    calls = fake_yahoo(monkeypatch, metadata, market)
    result = providers._sdk_rows(market, symbol)
    assert [name for name, _ in calls] == ["ticker", "history", "metadata"]
    requested = calls[1][1]
    assert requested["actions"] is True and requested["auto_adjust"] is False
    assert requested["repair"] is False and requested["keepna"] is True
    assert [row["close"] for row in result] == [100.0, 25.0]
    assert result[0]["dividends"] == .25 and result[1]["stock_splits"] == 4.0
    assert result[0]["source_url"] == "https://finance.yahoo.com/quote/" + symbol + "/history/"


def test_yahoo_cached_metadata_reads_only_basic_mapping_keys(monkeypatch):
    reads = []
    fields = {"currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": "EQUITY"}

    class CachedMetadata(Mapping):
        def __getitem__(self, key):
            reads.append(key)
            assert key != "tradingPeriods", "must not trigger an extra intraday metadata request"
            return fields[key]

        def __iter__(self):
            raise AssertionError("must not iterate a lazy history metadata mapping")

        def __len__(self):
            raise AssertionError("must not enumerate a lazy history metadata mapping")

    fake_yahoo(monkeypatch, CachedMetadata(), "us")
    assert len(providers._sdk_rows("us", "AAPL")) == 2
    assert reads == ["currency", "exchangeTimezoneName", "instrumentType"]


def test_yahoo_metadata_accessor_failure_is_a_static_public_error(monkeypatch):
    fake_yahoo(monkeypatch, None, "us", metadata_error=True)
    with pytest.raises(providers.ProviderError) as error:
        providers._sdk_rows("us", "AAPL")
    assert str(error.value) == providers._YAHOO_IDENTITY_ERRORS["missing"]
    assert "PRIVATE_PROVIDER_METADATA_MARKER" not in str(error.value)


async def test_stock_fetch_refreshes_warmup_prices_after_retroactive_vendor_revision(tmp_path, monkeypatch):
    import exchange_calendars as xcals
    from app.market.service import MarketService

    observed = datetime(2026, 10, 3, tzinfo=UTC)
    calendar = xcals.get_calendar('XNYS', start='2024-01-01', end='2026-10-03')
    dates = [session.date().isoformat() for session in calendar.sessions
             if session.date().isoformat() <= '2026-09-30'][-240:]
    assert len(dates) == 240
    service = MarketService(tmp_path)
    instrument = service.add_watchlist('us', 'AAPL')
    prior = providers.normalize_daily(daily_rows(dates[:60], 100.0), instrument,
                                      received_at=observed.isoformat(), observed_at=observed)
    service.store.ingest(instrument['id'], prior)
    revised = daily_rows(dates, 10.0)
    revised[220]['stock_splits'] = 10.0

    class Process:
        returncode = 0
        async def communicate(self):
            return json.dumps({'rows': revised}).encode(), b''

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(providers.asyncio, 'create_subprocess_exec', spawn)
    service.new_job([instrument['id']])
    await service.run_job(service.store.claim())
    stored = service.store.candles(instrument['id'], 240)
    assert len(stored) == 240 and all(bar['close'] == 10.0 for bar in stored)
    assert stored[0]['revision'] == 2
    snapshot = service.snapshot(instrument['id'])
    assert len(snapshot['candles']) == 180
    first_visible = snapshot['indicators'][0]
    assert first_visible['ma20'] == 10.0 and first_visible['ma60'] == 10.0
    assert not any(event['rule_id'] == 'sma20_60' for event in snapshot['signals'])
