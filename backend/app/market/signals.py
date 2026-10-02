"""Causal, explanatory events from verified, closed OHLCV bars.

The adapters retain missing rows and flag missing sessions with ``gap_before``.
We do not sort away defects, compress missing rows, fill prices, or interpret
these events as orders.  Stock high/low conventions may exclude auctions, so
this module does not require open/close to lie inside the reported high/low.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence


RULE_VERSION = "1"
RULES = [
    {"id": "breakout20", "name": "20 根区间突破", "description": "闭合收盘价超过此前 20 根 K 线最高价。",
     "parameters": {"period": 20}, "min_bars": 21, "enabled_by_default": True},
    {"id": "sma20_60", "name": "MA20 / MA60 穿越", "description": "简单均线 MA20 上穿或下穿 MA60。",
     "parameters": {"fast_period": 20, "slow_period": 60}, "min_bars": 61, "enabled_by_default": True},
    {"id": "volume2x", "name": "成交量放大", "description": "成交量达到此前 20 根均量的 2 倍。",
     "parameters": {"period": 20, "ratio": 2.0}, "min_bars": 21, "enabled_by_default": True},
    {"id": "rsi14_cross", "name": "RSI14 阈值穿越", "description": "RSI14 上穿或下穿 30、70 阈值。",
     "parameters": {"period": 14, "thresholds": [30.0, 70.0]}, "min_bars": 16, "enabled_by_default": False},
]
_RULE_BY_ID = {rule["id"]: rule for rule in RULES}
_INDICATORS = ("ma20", "ma60", "rsi14", "volume_ratio20")
_IDENTITY_FIELDS = ("provider", "symbol", "interval", "currency", "timezone", "volume_unit", "adjustment", "session")
_EXTRA_IDENTITY_FIELDS = ("exchange", "instrument_id", "market_type", "price_type")
_BOUNDARY_FLAGS = {"gap_before", "corporate_action"}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, (bool, str, bytes)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _time(value: Any) -> datetime | None:
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _iso(value: datetime) -> str:
    return value.isoformat()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class _Bar:
    index: int
    raw: Mapping[str, Any]
    start: datetime
    end: datetime
    received: datetime
    identity: tuple[str, ...]
    high: float
    close: float
    volume: float
    source_hash: str


def _decode(raw: Mapping[str, Any], index: int, as_of: datetime) -> tuple[_Bar | None, str | None]:
    start, end = _time(raw.get("time")), _time(raw.get("end_time"))
    if start is None or end is None or end <= start:
        return None, "invalid_time"
    if raw.get("closed") is not True or end > as_of:
        return None, "waiting_close"
    received = _time(raw.get("received_at")) if raw.get("received_at") is not None else end
    if received is None or received > as_of:
        return None, "invalid_received_at"
    quality = raw.get("quality", [])
    if not isinstance(quality, (list, tuple)) or any(not isinstance(flag, str) or flag not in _BOUNDARY_FLAGS
                                                  for flag in quality):
        return None, "invalid_quality"
    if any(not isinstance(raw.get(key), str) or not raw[key] for key in _IDENTITY_FIELDS):
        return None, "missing_provenance"
    if raw["interval"] not in ("1h", "1d"):
        return None, "unsupported_interval"
    values = {key: _number(raw.get(key)) for key in ("open", "high", "low", "close", "volume")}
    if any(value is None for value in values.values()):
        return None, "missing_ohlcv"
    if (values["volume"] < 0 or values["high"] < values["low"]
            or any(values[key] <= 0 for key in ("open", "high", "low", "close"))):
        return None, "invalid_ohlcv"
    identity = tuple(str(raw.get(key, "")) for key in (*_IDENTITY_FIELDS, *_EXTRA_IDENTITY_FIELDS))
    source_hash = raw.get("source_hash")
    if not isinstance(source_hash, str) or not source_hash:
        source_hash = _hash({"identity": identity, "time": _iso(start), "end_time": _iso(end),
                             "closed": True, **values})
    return _Bar(index, raw, start, end, received, identity, values["high"], values["close"],
                values["volume"], source_hash), None


def _segments(candles: Sequence[Mapping[str, Any]], as_of: datetime):
    segments: list[list[_Bar]] = []
    current: list[_Bar] = []
    reasons: list[str | None] = []
    previous_input_time: datetime | None = None
    for index, raw in enumerate(candles):
        bar, reason = _decode(raw, index, as_of)
        input_time = _time(raw.get("time"))
        if input_time is not None:
            if previous_input_time is not None and input_time <= previous_input_time:
                bar, reason = None, "non_increasing_time"
            previous_input_time = max(previous_input_time, input_time) if previous_input_time else input_time
        if bar is None:
            current = []
            reasons.append(reason)
            continue
        gap = raw.get("gap_before") is True or bool(_BOUNDARY_FLAGS.intersection(raw.get("quality", [])))
        if current:
            previous = current[-1]
            gap = gap or previous.identity != bar.identity or previous.end > bar.start
            # Only continuous markets have a universal wall-clock cadence.
            # Stock missing sessions must be flagged by the exchange calendar.
            if raw["session"] == "24x7" and raw["interval"] == "1h":
                gap = gap or bar.start - previous.start != timedelta(hours=1) or previous.end != bar.start
        if gap:
            current = []
        if not current:
            current = []
            segments.append(current)
        current.append(bar)
        reasons.append(None)
    return segments, reasons


def _event(rule_id: str, direction: str, bar: _Bar, dependencies: Sequence[_Bar], emitted: datetime,
           evidence: dict[str, float], summary: str) -> dict[str, Any]:
    rule = _RULE_BY_ID[rule_id]
    evidence = {key: _number(value) for key, value in evidence.items()}
    identity = [rule_id, RULE_VERSION, direction, bar.identity, _iso(bar.start)]
    # Dependencies stop at the triggering bar; appending future bars cannot
    # change either this evidence or its provenance hash.
    source_hash = _hash([item.source_hash for item in dependencies])
    revisions = [item.raw.get("revision", 1) for item in dependencies]
    revisions = [value for value in revisions if isinstance(value, int) and not isinstance(value, bool)]
    return {
        "id": _hash(identity)[:32], "rule_id": rule_id, "rule_name": rule["name"],
        "rule_version": RULE_VERSION, "direction": direction,
        "symbol": bar.raw["symbol"], "provider": bar.raw["provider"], "interval": bar.raw["interval"],
        "bar_time": _iso(bar.start), "bar_start": _iso(bar.start), "bar_close": _iso(bar.end),
        "confirmed_at": _iso(max(max(item.end, item.received) for item in dependencies)),
        "emitted_at": _iso(emitted), "parameters": copy.deepcopy(rule["parameters"]), "evidence": evidence,
        "source_hash": source_hash, "source_url": next((bar.raw[key] for key in ("source_url", "url")
                                                        if isinstance(bar.raw.get(key), str) and bar.raw[key]), None),
        "data_revision": max(revisions, default=1), "summary": summary,
        **{key: bar.raw.get(key) for key in (*_IDENTITY_FIELDS, *_EXTRA_IDENTITY_FIELDS)
           if isinstance(bar.raw.get(key), str)},
    }


def compute_signals(candles: Sequence[Mapping[str, Any]], *, rule_ids: Iterable[str] | None = None,
                    emitted_at: str | datetime | None = None, limit: int = 20) -> dict[str, Any]:
    """Return finite/null chart values and the most recent closed-bar events.

    Missing/invalid rows, explicit calendar gaps, non-increasing timestamps,
    continuous-market gaps, and changes in price/volume provenance break the
    warmup segment.  A later valid row starts a new segment; rows stay in the
    chart output.  RSI is optional and uses TA-Lib's actual current lookback.
    """
    selected = set(rule_ids) if rule_ids is not None else {
        rule["id"] for rule in RULES if rule["enabled_by_default"]
    }
    unknown = selected - _RULE_BY_ID.keys()
    if unknown:
        raise ValueError("Unknown market rule: " + ", ".join(sorted(unknown)))
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 1000:
        raise ValueError("Signal limit must be between 0 and 1000")
    as_of = datetime.now(UTC) if emitted_at is None else _time(emitted_at)
    if as_of is None:
        raise ValueError("emitted_at must include a timezone")
    candles = list(candles)
    points = [{"time": _iso(dt) if (dt := _time(raw.get("time"))) else (
               raw.get("time") if isinstance(raw.get("time"), str) else None),
               **{key: None for key in _INDICATORS}} for raw in candles]
    required = {rule["id"]: rule["min_bars"] for rule in RULES}
    result = {"status": "empty", "message": "暂无 K 线。", "latest_bar_time": points[-1]["time"] if points else None,
              "warmup": {"available_bars": 0, "required_bars": required, "rules_ready": []},
              "indicators": points, "latest": None, "signals": []}
    if not candles:
        return result
    try:
        import numpy as np
        import talib
        from talib import abstract
    except ImportError:
        result.update(status="dependency_unavailable", message="指标计算依赖尚未安装。")
        return result
    lookback20 = abstract.Function("SMA", timeperiod=20).lookback
    lookback60 = abstract.Function("SMA", timeperiod=60).lookback
    rsi_lookback = abstract.Function("RSI", timeperiod=14).lookback
    required["sma20_60"] = max(lookback20, lookback60) + 2
    required["rsi14_cross"] = rsi_lookback + 2
    segments, reasons = _segments(candles, as_of)
    events: list[dict[str, Any]] = []
    for segment in segments:
        close = np.asarray([bar.close for bar in segment], dtype=np.float64)
        ma20, ma60 = talib.SMA(close, timeperiod=20), talib.SMA(close, timeperiod=60)
        rsi = talib.RSI(close, timeperiod=14)
        for index, bar in enumerate(segment):
            point = points[bar.index]
            point.update(ma20=_number(ma20[index]), ma60=_number(ma60[index]), rsi14=_number(rsi[index]))
            if index >= 20:
                previous20 = segment[index - 20:index]
                # math.fsum avoids silent overflow in a sum of finite inputs.
                mean_volume = math.fsum(item.volume / 20 for item in previous20)
                ratio = _number(bar.volume / mean_volume) if mean_volume > 0 else None
                point["volume_ratio20"] = ratio
                reference_high = max(item.high for item in previous20)
                if "breakout20" in selected and bar.close > reference_high:
                    events.append(_event("breakout20", "above", bar, segment[index - 20:index + 1], as_of,
                                         {"close": bar.close, "reference_high": reference_high},
                                         "闭合收盘价超过此前 20 根 K 线最高价。"))
                if "volume2x" in selected and ratio is not None and ratio >= 2.0:
                    events.append(_event("volume2x", "above", bar, segment[index - 20:index + 1], as_of,
                                         {"volume": bar.volume, "mean_volume20": mean_volume, "volume_ratio20": ratio},
                                         "成交量达到此前 20 根均量的 2 倍。"))
            if "sma20_60" in selected and index + 1 >= required["sma20_60"]:
                previous_fast, previous_slow = _number(ma20[index - 1]), _number(ma60[index - 1])
                fast, slow = point["ma20"], point["ma60"]
                if all(value is not None for value in (previous_fast, previous_slow, fast, slow)):
                    direction = "up" if previous_fast <= previous_slow and fast > slow else (
                        "down" if previous_fast >= previous_slow and fast < slow else None)
                    if direction:
                        events.append(_event("sma20_60", direction, bar,
                                             segment[index - required["sma20_60"] + 1:index + 1], as_of,
                                             {"ma20": fast, "ma60": slow, "previous_ma20": previous_fast,
                                              "previous_ma60": previous_slow},
                                             "MA20 上穿 MA60。" if direction == "up" else "MA20 下穿 MA60。"))
            if "rsi14_cross" in selected and index + 1 >= required["rsi14_cross"]:
                previous_rsi, current_rsi = _number(rsi[index - 1]), point["rsi14"]
                if previous_rsi is not None and current_rsi is not None:
                    for threshold in (30.0, 70.0):
                        direction = "up" if previous_rsi <= threshold and current_rsi > threshold else (
                            "down" if previous_rsi >= threshold and current_rsi < threshold else None)
                        if direction:
                            event = _event("rsi14_cross", direction, bar, segment[:index + 1], as_of,
                                           {"rsi14": current_rsi, "previous_rsi14": previous_rsi, "threshold": threshold},
                                           f"RSI14 {'上穿' if direction == 'up' else '下穿'} {threshold:g}。")
                            # One bar can cross both thresholds; each event has its own identity.
                            event["id"] = _hash([event["id"], threshold])[:32]
                            events.append(event)
    available = len(segments[-1]) if segments and segments[-1][-1].index == len(candles) - 1 else 0
    if reasons[-1] == "waiting_close" and segments and segments[-1][-1].index == len(candles) - 2:
        available = len(segments[-1])
    result["warmup"].update(available_bars=available,
                            rules_ready=sorted(rule for rule in selected if available >= required[rule]))
    if segments:
        latest_closed = segments[-1][-1]
        result["latest"] = {**points[latest_closed.index], "close": latest_closed.close}
    result["signals"] = sorted(events, key=lambda event: (event["bar_time"], event["rule_id"], event["id"]),
                               reverse=True)[:limit]
    if reasons[-1] == "waiting_close":
        result.update(status="waiting_close", message="末根 K 线尚未确认闭合，正式信号仅来自此前闭合数据。")
    elif reasons[-1] is not None:
        reason = reasons[-1]
        descriptions = {"invalid_time": "时间边界无效", "invalid_received_at": "采集时间无效",
                        "invalid_quality": "来源质量标记未通过", "missing_provenance": "来源或价格口径缺失",
                        "unsupported_interval": "周期暂不支持", "missing_ohlcv": "OHLCV 缺失或非有限",
                        "invalid_ohlcv": "价格或成交量无效", "non_increasing_time": "K 线时间重复或倒序"}
        description = descriptions.get(reason, "质量未通过")
        if reason == "invalid_quality":
            flags = candles[-1].get("quality")
            flag_descriptions = {"missing_ohlcv": "OHLCV 缺失", "calendar_unconfirmed": "交易日历未确认",
                                 "large_price_change_unverified": "单根价格变化尚未通过来源核验"}
            if isinstance(flags, (list, tuple)):
                details = [flag_descriptions[flag] for flag in flags
                           if isinstance(flag, str) and flag in flag_descriptions]
                if details:
                    description = "、".join(details)
        result.update(status="quality_blocked", quality_reason=reason,
                      message=f"末根 K 线{description}，该窗口停止计算并重新预热。")
    elif available < min((required[rule] for rule in selected), default=1):
        minimum = min((required[rule] for rule in selected), default=1)
        result.update(status="insufficient_history",
                      message=f"当前连续有效闭合 K 线 {available} 根，至少需 {minimum} 根才能计算所选规则。")
    else:
        pending = [_RULE_BY_ID[rule]["name"] for rule in sorted(selected) if available < required[rule]]
        message = "已按闭合 K 线计算。"
        if pending:
            message += "以下规则仍需预热：" + "、".join(pending) + "。"
        result.update(status="ready", message=message)
    return result
