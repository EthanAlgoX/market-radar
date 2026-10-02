import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
import talib

from app.market.signals import RULES, compute_signals


AS_OF = "2026-10-03T00:00:00+00:00"
START = datetime(2026, 9, 1, tzinfo=UTC)


def bars(closes, volumes=None, *, offset=0):
    result = []
    for index, close in enumerate(closes):
        start = START + timedelta(hours=index + offset)
        end = start + timedelta(hours=1)
        result.append({
            "time": start.isoformat(), "end_time": end.isoformat(), "trading_date": start.date().isoformat(),
            "open": close, "high": close + 1, "low": close - 0.5, "close": close,
            "volume": volumes[index] if volumes is not None else 100.0,
            "provider": "test-public", "symbol": "BTC/USDT", "interval": "1h", "currency": "USDT",
            "timezone": "UTC", "volume_unit": "BTC", "adjustment": "none", "session": "24x7",
            "closed": True, "received_at": (end + timedelta(seconds=5)).isoformat(), "quality": [],
            "revision": 1, "source_url": "https://example.org/public/BTC-USDT",
        })
    return result


def evaluate(data, rules=None, **kwargs):
    return compute_signals(data, rule_ids=rules, emitted_at=AS_OF, limit=1000, **kwargs)


def test_breakout_warmup_and_previous_window_excludes_current_bar():
    data = bars([100.0] * 20 + [102.0])
    assert evaluate(data[:20], ["breakout20"])["status"] == "insufficient_history"
    assert evaluate(data[:20], ["breakout20"])["signals"] == []
    result = evaluate(data, ["breakout20"])
    assert result["status"] == "ready"
    event, = result["signals"]
    assert event["evidence"] == {"close": 102.0, "reference_high": 101.0}
    assert event["bar_time"] == data[-1]["time"]
    assert event["bar_close"] == data[-1]["end_time"]
    assert event["confirmed_at"] == data[-1]["received_at"]
    assert event["emitted_at"] == AS_OF
    equal_high = bars([100.0] * 20 + [101.0])
    assert evaluate(equal_high, ["breakout20"])["signals"] == []


@pytest.mark.parametrize(("last_close", "direction"), [(120.0, "up"), (80.0, "down")])
def test_sma_cross_needs_two_valid_slow_averages(last_close, direction):
    too_short = evaluate(bars([100.0] * 59 + [last_close]), ["sma20_60"])
    assert too_short["status"] == "insufficient_history"
    assert too_short["signals"] == []
    result = evaluate(bars([100.0] * 60 + [last_close]), ["sma20_60"])
    event, = result["signals"]
    assert event["direction"] == direction
    assert event["evidence"]["previous_ma20"] == event["evidence"]["previous_ma60"] == 100.0
    assert event["evidence"]["ma20"] == pytest.approx((100.0 * 19 + last_close) / 20)
    assert event["evidence"]["ma60"] == pytest.approx((100.0 * 59 + last_close) / 60)
    assert result["warmup"]["required_bars"]["sma20_60"] == 61


def test_no_repeat_sma_cross_when_fast_average_stays_above_slow():
    result = evaluate(bars([100.0] * 60 + [120.0] * 4), ["sma20_60"])
    assert len(result["signals"]) == 1
    assert result["signals"][0]["bar_time"] == bars([100.0] * 61)[-1]["time"]


def test_volume_ratio_uses_prior_twenty_and_zero_baseline_is_not_an_event():
    data = bars([100.0] * 21, [100.0] * 20 + [200.0])
    event, = evaluate(data, ["volume2x"])["signals"]
    assert event["evidence"] == {"volume": 200.0, "mean_volume20": 100.0, "volume_ratio20": 2.0}
    assert evaluate(data[:20], ["volume2x"])["signals"] == []
    zeros = evaluate(bars([100.0] * 21, [0.0] * 20 + [200.0]), ["volume2x"])
    assert zeros["signals"] == [] and zeros["latest"]["volume_ratio20"] is None


@pytest.mark.parametrize(("closes", "direction"), [
    ([float(value) for value in range(100, 115)] + [1.0], "down"),
    ([float(value) for value in range(100, 85, -1)] + [200.0], "up"),
])
def test_rsi_cross_requires_two_valid_values_and_distinguishes_thresholds(closes, direction):
    data = bars(closes)
    short = evaluate(data[:15], ["rsi14_cross"])
    assert short["signals"] == [] and short["status"] == "insufficient_history"
    assert short["latest"]["rsi14"] is not None
    result = evaluate(data, ["rsi14_cross"])
    assert {event["evidence"]["threshold"] for event in result["signals"]} == {30.0, 70.0}
    assert {event["direction"] for event in result["signals"]} == {direction}
    assert len({event["id"] for event in result["signals"]}) == 2
    assert result["warmup"]["required_bars"]["rsi14_cross"] == 16


def test_actual_talib_unstable_lookback_is_used_and_restored():
    original = talib.get_unstable_period("RSI")
    try:
        talib.set_unstable_period("RSI", 3)
        result = evaluate(bars([100.0] * 15 + [200.0]), ["rsi14_cross"])
        assert result["warmup"]["required_bars"]["rsi14_cross"] == 19
        assert result["status"] == "insufficient_history" and result["signals"] == []
    finally:
        talib.set_unstable_period("RSI", original)


def test_future_append_or_change_cannot_change_past_confirmed_events_or_values():
    prefix = bars([100.0] * 60 + [120.0, 80.0, 125.0], [100.0] * 60 + [200.0, 250.0, 200.0])
    earlier = evaluate(prefix, [rule["id"] for rule in RULES])
    future = bars([180.0, 50.0, 200.0, 100.0], offset=len(prefix))
    extended = evaluate(prefix + future, [rule["id"] for rule in RULES])
    assert [event for event in extended["signals"] if event["bar_time"] <= prefix[-1]["time"]] == earlier["signals"]
    assert extended["indicators"][:len(prefix)] == earlier["indicators"]
    changed = bars([500.0, 3.0, 400.0, 2.0], offset=len(prefix))
    alternative = evaluate(prefix + changed, [rule["id"] for rule in RULES])
    assert [event for event in alternative["signals"] if event["bar_time"] <= prefix[-1]["time"]] == earlier["signals"]
    assert alternative["indicators"][:len(prefix)] == earlier["indicators"]


def test_open_tail_does_not_block_prior_events_and_becomes_eligible_after_close():
    closed = bars([100.0] * 60 + [120.0])
    baseline = evaluate(closed)
    tail = bars([150.0], [500.0], offset=len(closed))[0]
    tail["closed"] = False
    pending = evaluate(closed + [tail])
    assert pending["status"] == "waiting_close"
    assert pending["signals"] == baseline["signals"]
    assert pending["latest"] == baseline["latest"]
    assert pending["latest_bar_time"] == tail["time"]
    assert all(pending["indicators"][-1][key] is None for key in ("ma20", "ma60", "rsi14", "volume_ratio20"))
    tail["closed"] = True
    confirmed = evaluate(closed + [tail])
    assert confirmed["status"] == "ready"
    assert any(event["bar_time"] == tail["time"] for event in confirmed["signals"])
    assert confirmed["latest"]["time"] == tail["time"]


def test_even_a_closed_flag_cannot_confirm_a_future_bar():
    data = bars([100.0] * 20 + [120.0])
    result = compute_signals(data, rule_ids=["breakout20"], emitted_at=data[-1]["time"])
    assert result["status"] == "waiting_close" and result["signals"] == []


@pytest.mark.parametrize("missing", [None, float("nan"), float("inf")])
def test_missing_or_nonfinite_bar_keeps_its_row_and_resets_warmup(missing):
    data = bars([100.0] * 60 + [100.0] + [100.0] * 19 + [120.0])
    data[60]["close"] = missing
    result = evaluate(data, ["sma20_60"])
    assert result["status"] == "insufficient_history" and result["signals"] == []
    assert result["warmup"]["available_bars"] == 20
    assert len(result["indicators"]) == len(data)
    assert result["indicators"][60]["ma20"] is None
    assert result["latest"]["ma20"] is not None and result["latest"]["ma60"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("boundary", ["gap_before", "corporate_action"])
def test_explicit_boundaries_start_a_new_segment_without_losing_the_valid_row(boundary):
    data = bars([100.0] * 60 + [50.0] * 20 + [60.0])
    data[60]["quality"] = [boundary]
    result = evaluate(data, ["breakout20", "sma20_60"])
    assert result["warmup"]["available_bars"] == 21
    assert result["latest"]["ma60"] is None
    event, = result["signals"]
    assert event["rule_id"] == "breakout20" and event["evidence"]["reference_high"] == 51.0


def test_missing_crypto_hour_breaks_window_even_without_provider_flag():
    data = bars([100.0] * 60) + bars([100.0] * 19 + [120.0], offset=61)
    result = evaluate(data, ["sma20_60"])
    assert result["warmup"]["available_bars"] == 20
    assert result["latest"]["ma60"] is None and result["signals"] == []


def test_stock_weekends_are_not_treated_as_missing_trading_sessions():
    data = bars([100.0] * 60 + [120.0])
    for index, bar in enumerate(data):
        start = START + timedelta(days=index + index // 5 * 2)
        bar.update(time=start.isoformat(), end_time=(start + timedelta(hours=7)).isoformat(),
                   received_at=(start + timedelta(hours=7, seconds=5)).isoformat(),
                   interval="1d", session="regular", timezone="America/New_York", volume_unit="shares")
    result = compute_signals(data, rule_ids=["sma20_60"], emitted_at="2027-01-01T00:00:00+00:00")
    assert result["warmup"]["available_bars"] == 61 and len(result["signals"]) == 1


@pytest.mark.parametrize(("key", "value"), [("provider", "other-public"), ("adjustment", "forward"),
                                            ("volume_unit", "quote-USDT"), ("currency", "USD")])
def test_provenance_change_never_splices_an_existing_indicator_window(key, value):
    data = bars([100.0] * 60 + [120.0])
    data[-1][key] = value
    result = evaluate(data, ["sma20_60"])
    assert result["status"] == "insufficient_history"
    assert result["warmup"]["available_bars"] == 1 and result["signals"] == []


@pytest.mark.parametrize("quality", [["missing_ohlcv"], ["large_price_change_unverified"], ["calendar_unconfirmed"]])
def test_source_quality_flags_block_current_events(quality):
    data = bars([100.0] * 60 + [120.0])
    data[-1]["quality"] = quality
    result = evaluate(data)
    assert result["status"] == "quality_blocked" and result["quality_reason"] == "invalid_quality"
    assert all(event["bar_time"] != data[-1]["time"] for event in result["signals"])


def test_auction_price_convention_is_not_rejected_by_a_generic_ohlc_check():
    data = bars([100.0] * 20 + [102.0])
    data[-1].update(high=101.0, low=99.0, open=103.0)
    event, = evaluate(data, ["breakout20"])["signals"]
    assert event["evidence"]["close"] == 102.0


def test_revision_recomputes_evidence_hash_and_can_withdraw_an_event():
    data = bars([100.0] * 60 + [120.0])
    first, = evaluate(data, ["sma20_60"])["signals"]
    revised = copy.deepcopy(data)
    revised[-1].update(open=125.0, high=126.0, low=124.5, close=125.0, revision=2)
    second, = evaluate(revised, ["sma20_60"])["signals"]
    assert second["id"] == first["id"]
    assert second["source_hash"] != first["source_hash"] and second["data_revision"] == 2
    assert second["evidence"]["ma20"] != first["evidence"]["ma20"]
    revised[-1].update(open=100.0, high=101.0, low=99.5, close=100.0, revision=3)
    assert evaluate(revised, ["sma20_60"])["signals"] == []


def test_audit_timestamp_refresh_does_not_change_data_hash_or_event_id():
    data = bars([100.0] * 60 + [120.0])
    first, = evaluate(data, ["sma20_60"])["signals"]
    refreshed = copy.deepcopy(data)
    for bar in refreshed:
        bar["received_at"] = "2026-10-02T00:00:00+00:00"
    second, = evaluate(refreshed, ["sma20_60"])["signals"]
    assert second["id"] == first["id"] and second["source_hash"] == first["source_hash"]
    assert second["evidence"] == first["evidence"]


def test_duplicate_or_reversed_time_is_not_silently_sorted_or_deduplicated():
    data = bars([100.0] * 60 + [120.0])
    data[-1].update(time=data[-2]["time"], end_time=data[-2]["end_time"])
    result = evaluate(data)
    assert result["status"] == "quality_blocked" and result["quality_reason"] == "non_increasing_time"
    assert len(result["indicators"]) == len(data)
    assert result["signals"] == []


def test_outputs_are_json_safe_and_catalog_matches_supported_rules():
    data = bars([100.0] * 60 + [120.0])
    result = evaluate(data, [rule["id"] for rule in RULES])
    json.dumps(result, allow_nan=False)
    assert {rule["id"] for rule in RULES} == {"breakout20", "sma20_60", "volume2x", "rsi14_cross"}
    assert evaluate([])["status"] == "empty"
    with pytest.raises(ValueError, match="Unknown market rule"):
        evaluate(data, ["made-up"])
