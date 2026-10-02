from __future__ import annotations

import asyncio
import json
import math
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ..security import fetch_response, safe_error
from .models import WINDOW, fingerprint, instrument_spec, now_iso

PROVIDERS = [
    {"id": "binance", "name": "Binance 公开现货", "markets": ["crypto"], "intervals": ["1h"],
     "delay_note": "公开 REST 快照；以服务器时间确认闭合，不是交易流"},
    {"id": "yahoo", "name": "Yahoo · yfinance", "markets": ["us", "hk"], "intervals": ["1d"],
     "delay_note": "公开日线，港股报价有延迟；可用性与数据权限由 Yahoo 决定"},
    {"id": "eastmoney", "name": "东方财富 · AKShare", "markets": ["cn"], "intervals": ["1d"],
     "delay_note": "公开沪深日线；网站接口可能限流或变更，不保证实时"},
]


@dataclass
class FetchResult:
    candles: list[dict]
    message: str = "已取得有限行情窗口；未回补完整历史"


class ProviderError(RuntimeError):
    pass


_YAHOO_IDENTITY_ERRORS = {
    "missing": "Yahoo 行情身份信息缺失，无法确认资产类型、币种和交易时区，未保存数据",
    "type": "Yahoo 返回的资产类型不是股票或 ETF，未保存所选股票市场的数据",
    "market": "Yahoo 行情币种或交易时区与所选市场不一致，未保存数据",
}


def _validate_yahoo_metadata(metadata, market: str) -> None:
    # yfinance 1.7 returns a lazy Mapping, not necessarily a dict. Read only
    # base keys; converting/iterating it may lazily request tradingPeriods.
    if not isinstance(metadata, Mapping):
        raise ProviderError(_YAHOO_IDENTITY_ERRORS["missing"])
    fields = [metadata.get(key) for key in ("currency", "exchangeTimezoneName", "instrumentType")]
    if any(not isinstance(value, str) or not value for value in fields):
        raise ProviderError(_YAHOO_IDENTITY_ERRORS["missing"])
    currency, zone, kind = fields
    if kind not in {"EQUITY", "ETF"}:
        raise ProviderError(_YAHOO_IDENTITY_ERRORS["type"])
    expected = {"us": ("USD", "America/New_York"), "hk": ("HKD", "Asia/Hong_Kong")}
    if (currency, zone) != expected[market]:
        raise ProviderError(_YAHOO_IDENTITY_ERRORS["market"])


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def finish_candle(spec: dict, candle: dict) -> dict:
    for key in ("provider", "symbol", "interval", "currency", "timezone", "volume_unit", "adjustment", "session"):
        candle[key] = spec[key]
    candle.setdefault("quality", [])
    for field in ("open", "high", "low", "close", "volume"):
        candle[field] = number(candle.get(field))
    if any(candle[field] is None for field in ("open", "high", "low", "close", "volume")):
        candle["quality"].append("missing_ohlcv")
    elif (min(candle[field] for field in ("open", "high", "low", "close")) <= 0
          or candle["volume"] < 0 or candle["high"] < candle["low"]):
        candle["quality"].append("invalid_ohlcv")
    # Open/close may lie outside the reported high/low when auctions are
    # excluded from that range; the high itself must still be >= the low.
    candle["quality"] = sorted(set(candle["quality"]))
    candle["source_hash"] = fingerprint({key: candle.get(key) for key in (
        "provider", "symbol", "interval", "currency", "timezone", "volume_unit", "adjustment", "session",
        "time", "end_time", "trading_date", "open", "high", "low", "close", "volume", "closed", "quality",
        "corporate_action", "dividends", "stock_splits", "quote_volume", "trade_count",
        "taker_buy_base_volume", "taker_buy_quote_volume", "provider_close_time")})
    return candle


def normalize_daily(rows: list[dict], spec: dict, *, received_at: str, observed_at: datetime | None = None, window: int = WINDOW) -> list[dict]:
    """Use real exchange sessions; unresolved calendars leave bars unconfirmed."""
    observed_at = observed_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    else:
        observed_at = observed_at.astimezone(timezone.utc)
    if len({str(row["date"])[:10] for row in rows}) != len(rows):
        raise ProviderError("来源返回重复交易日，未覆盖已有数据")
    rows = sorted(rows, key=lambda row: str(row["date"]))[-window:]
    calendar = None
    try:
        import exchange_calendars as xcals
        calendar_name = {"us": "XNYS", "hk": "XHKG", "cn": "XSHG"}[spec["market"]]
        if rows:
            calendar = xcals.get_calendar(calendar_name, start=rows[0]["date"],
                                          end=(datetime.fromisoformat(rows[-1]["date"]) + timedelta(days=7)).date().isoformat())
    except Exception:
        pass
    candles, previous_session, previous_close = [], None, None
    for row in rows:
        trade_date = str(row["date"])[:10]
        midnight = datetime.fromisoformat(trade_date).replace(tzinfo=ZoneInfo(spec["timezone"]))
        opening, ending, closed, quality = midnight, midnight + timedelta(days=1), False, []
        try:
            if calendar is None:
                raise ValueError("calendar unavailable")
            import pandas as pd
            session = pd.Timestamp(trade_date)
            if not calendar.is_session(session):
                quality.append("non_trading_session")
            else:
                opening = calendar.session_open(session).to_pydatetime()
                ending = calendar.session_close(session).to_pydatetime()
                closed = observed_at >= ending + timedelta(minutes=30)
                if previous_session is not None and calendar.next_session(previous_session) != session:
                    quality.append("gap_before")
                previous_session = session
        except Exception:
            quality.append("calendar_unconfirmed")
        dividend, split = number(row.get("dividends")), number(row.get("stock_splits"))
        action = {"dividend": dividend, "split_ratio": split} if (dividend and dividend > 0) or (split and split != 1) else None
        if action:
            quality.append("corporate_action")
        current_close = number(row.get("close"))
        if spec["provider"] == "eastmoney" and previous_close and current_close and abs(current_close / previous_close - 1) > .3:
            quality.append("large_price_change_unverified")
        previous_close = current_close
        candles.append(finish_candle(spec, {
            "time": opening.astimezone(timezone.utc).isoformat(), "end_time": ending.astimezone(timezone.utc).isoformat(),
            "trading_date": trade_date, "open": row.get("open"), "high": row.get("high"),
            "low": row.get("low"), "close": row.get("close"), "volume": row.get("volume"),
            "closed": closed, "received_at": received_at, "quality": quality,
            "source_url": row.get("source_url", ""),
            "dividends": number(row.get("dividends")), "stock_splits": number(row.get("stock_splits")),
            "corporate_action": action,
        }))
    return candles


def normalize_binance(rows: list[list], spec: dict, *, server_time: int, received_at: str) -> list[dict]:
    if len({row[0] for row in rows}) != len(rows):
        raise ProviderError("Binance 返回重复时间戳，未覆盖已有数据")
    candles, previous_time = [], None
    for row in sorted(rows, key=lambda value: value[0])[-WINDOW:]:
        if len(row) < 11:
            raise ProviderError("Binance 返回了不完整 K 线结构")
        start, close_time = int(row[0]), int(row[6])
        quality = []
        if close_time != start + 3_600_000 - 1 or start % 3_600_000:
            quality.append("invalid_interval")
        if previous_time is not None and start - previous_time != 3_600_000:
            quality.append("gap_before")
        previous_time = start
        moment = datetime.fromtimestamp(start / 1000, timezone.utc)
        candles.append(finish_candle(spec, {
            "time": moment.isoformat(), "end_time": datetime.fromtimestamp((close_time + 1) / 1000, timezone.utc).isoformat(),
            "trading_date": moment.date().isoformat(), "open": row[1], "high": row[2], "low": row[3],
            "close": row[4], "volume": row[5], "quote_volume": number(row[7]), "trade_count": int(row[8]),
            "taker_buy_base_volume": number(row[9]), "taker_buy_quote_volume": number(row[10]),
            "provider_close_time": close_time, "provider_server_time": server_time,
            "closed": server_time >= close_time + 1001, "received_at": received_at, "quality": quality,
            "source_url": "https://www.binance.com/en/trade/" + spec["symbol"].replace("/", "_") + "?type=spot",
        }))
    return candles


def usable_closed_candles(candles: list[dict], *, observed_at: datetime | None = None) -> list[dict]:
    """Same complete, usable closed-bar gate as the signal engine.

    A valid session boundary or corporate action starts a new warmup segment;
    it does not make that bar's own quote unusable. All other quality flags,
    missing/nonfinite values, and unconfirmed/future time boundaries block it.
    """
    observed_at = observed_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    else:
        observed_at = observed_at.astimezone(timezone.utc)
    result = []
    for bar in candles:
        quality = bar.get("quality", [])
        if bar.get("closed") is not True or not isinstance(quality, (list, tuple)):
            continue
        if any(flag not in ("gap_before", "corporate_action") for flag in quality):
            continue
        values = {key: number(bar.get(key)) for key in ("open", "high", "low", "close", "volume")}
        if any(value is None for value in values.values()):
            continue
        if (values["volume"] < 0 or values["high"] < values["low"]
                or any(values[key] <= 0 for key in ("open", "high", "low", "close"))):
            continue
        try:
            start = datetime.fromisoformat(bar["time"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(bar["end_time"].replace("Z", "+00:00"))
            received = datetime.fromisoformat(bar.get("received_at", bar["end_time"]).replace("Z", "+00:00"))
            if any(moment.tzinfo is None for moment in (start, end, received)):
                continue
            if not start < end <= observed_at or received > observed_at:
                continue
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        result.append(bar)
    return result


def freshness(spec: dict, candles: list[dict], *, observed_at: datetime | None = None) -> dict:
    """Compare the bar's market time with the last completed session, not HTTP receipt time."""
    observed_at = observed_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    else:
        observed_at = observed_at.astimezone(timezone.utc)
    closed = usable_closed_candles(candles, observed_at=observed_at)
    result = {"stale": True, "freshness_status": "empty", "freshness_message": "尚无可用的已确认闭合行情", "expected_last_closed_date": None}
    if not closed:
        return result
    if spec["market"] == "crypto":
        expected_end = observed_at.replace(minute=0, second=0, microsecond=0)
        ending = datetime.fromisoformat(closed[-1]["end_time"])
        result.update(stale=ending < expected_end, freshness_status="stale" if ending < expected_end else "current",
                      freshness_message="按最近已结束小时检查；接收时间不等于行情时间")
        return result
    try:
        import exchange_calendars as xcals
        local_day = observed_at.astimezone(ZoneInfo(spec["timezone"])).date()
        calendar = xcals.get_calendar({"us": "XNYS", "hk": "XHKG", "cn": "XSHG"}[spec["market"]],
                                      start=(local_day - timedelta(days=25)).isoformat(), end=(local_day + timedelta(days=5)).isoformat())
        eligible = [session for session in calendar.sessions if calendar.session_close(session).to_pydatetime() + timedelta(minutes=30) <= observed_at]
        if not eligible:
            raise ValueError("no completed sessions")
        expected = eligible[-1].date().isoformat()
        stale = closed[-1]["trading_date"] < expected
        result.update(stale=stale, freshness_status="stale" if stale else "current", expected_last_closed_date=expected,
                      freshness_message="按交易所日历最近已结束交易日检查；未证明实时报价")
    except Exception:
        result.update(freshness_status="unconfirmed", freshness_message="交易日历无法确认，保守标记为待验证")
    return result


class PublicMarketProviders:
    async def fetch(self, instrument: dict) -> FetchResult:
        spec = instrument_spec(instrument["market"], instrument["symbol"])
        if spec["market"] == "crypto":
            base = "https://data-api.binance.vision"
            params = urlencode({"symbol": spec["symbol"].replace("/", ""), "interval": "1h", "limit": WINDOW})
            try:
                # Fixed public domains and pinned DNS/redirect checks; no user-supplied URL or account.
                # A clock taken after the candle response cannot prove that its
                # previously returned live bar was final. Take the clock first;
                # a bar closing during these requests remains a preview until
                # the next refresh obtains a post-close candle snapshot.
                clock = await fetch_response(base + "/api/v3/time", trusted_base_url=base, timeout=8, max_attempts=2, max_bytes=10_000)
                response = await fetch_response(base + "/api/v3/klines?" + params, trusted_base_url=base, timeout=12, max_attempts=2, max_bytes=500_000)
                rows, server_time = json.loads(response.body), int(json.loads(clock.body)["serverTime"])
                if not isinstance(rows, list) or not rows:
                    raise ProviderError("Binance 未返回该现货交易对的行情")
                return FetchResult(normalize_binance(rows, spec, server_time=server_time, received_at=now_iso()))
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderError(safe_error(exc, "Binance")) from exc
        # Synchronous third-party SDK requests run in a killable process, never an unbounded worker thread.
        for attempt in range(2):
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "app.market.providers", "--fetch", spec["market"], spec["symbol"],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=35)
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            if len(stdout) > 1_000_000:
                raise ProviderError("行情响应超过有限窗口大小")
            try:
                payload = json.loads(stdout)
            except (ValueError, UnicodeError):
                payload = {"error": "行情 SDK 未返回有效结果，请检查依赖与网络"}
            if process.returncode == 0 and "rows" in payload:
                if not payload["rows"]:
                    raise ProviderError("来源返回空行情；可能是代码不可用、限流或无可用交易数据")
                # Yahoo may revise earlier OHLC after splits. Refresh the full
                # 60-bar warmup together with the 180-bar view; cached prices
                # must not become a different unit at their join.
                candles = normalize_daily(payload["rows"], spec, received_at=now_iso(), window=WINDOW + 60)
                return FetchResult(candles)
            if attempt == 0:
                await asyncio.sleep(0.6)
            else:
                raise ProviderError(payload.get("error", "行情来源不可用"))
        raise ProviderError("行情来源不可用")


def _sdk_rows(market: str, symbol: str) -> list[dict]:
    if market in {"us", "hk"}:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        frame = ticker.history(period="1y", interval="1d", auto_adjust=False,
                               actions=True, repair=False, keepna=True, prepost=False,
                               timeout=12, raise_errors=True)
        try:
            metadata = ticker.get_history_metadata()
        except Exception as exc:
            raise ProviderError(_YAHOO_IDENTITY_ERRORS["missing"]) from exc
        _validate_yahoo_metadata(metadata, market)
        return [{"date": index.date().isoformat(), **{key.lower(): number(row[key]) for key in ("Open", "High", "Low", "Close", "Volume")},
                 "dividends": number(row.get("Dividends")), "stock_splits": number(row.get("Stock Splits")),
                 "source_url": "https://finance.yahoo.com/quote/" + symbol + "/history/"}
                for index, row in frame.tail(WINDOW + 60).iterrows()]
    import akshare as ak
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    frame = ak.stock_zh_a_hist(symbol=symbol.split(".")[0], period="daily", adjust="",
                              start_date=(today - timedelta(days=400)).strftime("%Y%m%d"),
                              end_date=today.strftime("%Y%m%d"), timeout=12)
    return [{"date": str(row["日期"])[:10], **{key: number(row[field]) for key, field in
             {"open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量"}.items()},
             "source_url": "https://quote.eastmoney.com/" + ("sh" if symbol.endswith(".SS") else "sz") + symbol[:6] + ".html"}
            for _, row in frame.tail(WINDOW + 60).iterrows()]


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4 or sys.argv[1] != "--fetch":
            raise ValueError("invalid arguments")
        spec = instrument_spec(sys.argv[2], sys.argv[3])
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            rows = _sdk_rows(spec["market"], spec["symbol"])
        result = {"rows": rows}
    except Exception as exc:
        # Exceptions can contain upstream tokens/URLs; never copy them into API/log output.
        message = str(exc) if isinstance(exc, ProviderError) and str(exc) in _YAHOO_IDENTITY_ERRORS.values() else (
            "行情 SDK 未完成请求，请检查公开数据可用性、网络或限流")
        result = {"error": message}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
