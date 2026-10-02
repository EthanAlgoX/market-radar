from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_INSTRUMENTS = 20
WINDOW = 180


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class WatchlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Literal["crypto", "us", "hk", "cn"]
    symbol: str = Field(min_length=1, max_length=24)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] | None = Field(default=None, max_length=MAX_INSTRUMENTS)


PRESETS = [
    {"market": "crypto", "symbol": "BTC/USDT", "name": "比特币", "aliases": ["Bitcoin", "比特币", "BTC"]},
    {"market": "crypto", "symbol": "ETH/USDT", "name": "以太坊", "aliases": ["Ethereum", "以太坊", "ETH"]},
    {"market": "us", "symbol": "AAPL", "name": "苹果", "aliases": ["Apple", "苹果", "AAPL"]},
    {"market": "us", "symbol": "NVDA", "name": "英伟达", "aliases": ["NVIDIA", "英伟达", "NVDA"]},
    {"market": "us", "symbol": "MSFT", "name": "微软", "aliases": ["Microsoft", "微软", "MSFT"]},
    {"market": "hk", "symbol": "0700.HK", "name": "腾讯", "aliases": ["Tencent", "腾讯"]},
    {"market": "hk", "symbol": "9988.HK", "name": "阿里巴巴", "aliases": ["Alibaba", "阿里巴巴"]},
    {"market": "cn", "symbol": "600519.SS", "name": "贵州茅台", "aliases": ["贵州茅台", "Kweichow Moutai"]},
    {"market": "cn", "symbol": "000001.SZ", "name": "平安银行", "aliases": ["平安银行", "Ping An Bank"]},
]


def instrument_spec(market: str, symbol: str) -> dict:
    symbol = symbol.strip().upper()
    if market == "crypto":
        symbol = symbol.removesuffix("/USDT").removesuffix("USDT") + "/USDT"
        if not re.fullmatch(r"[A-Z0-9]{2,12}/USDT", symbol):
            raise ValueError("加密资产请输入 BTC/USDT 一类 Binance 现货 USDT 交易对")
        provider, interval, currency, zone, unit, session = "binance", "1h", "USDT", "UTC", "base_asset", "24x7"
    elif market == "us":
        if not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,3})?", symbol):
            raise ValueError("美股请输入 AAPL 一类股票或 ETF 代码")
        provider, interval, currency, zone, unit, session = "yahoo", "1d", "USD", "America/New_York", "shares", "regular"
    elif market == "hk":
        code = symbol.removesuffix(".HK")
        if not re.fullmatch(r"[0-9]{1,5}", code) or int(code) == 0:
            raise ValueError("港股请输入 0700.HK 一类股票代码")
        symbol = str(int(code)).zfill(4) + ".HK"
        provider, interval, currency, zone, unit, session = "yahoo", "1d", "HKD", "Asia/Hong_Kong", "shares", "regular"
    elif market == "cn":
        code = symbol.split(".")[0]
        if not re.fullmatch(r"[036][0-9]{5}", code):
            raise ValueError("首版 A 股仅支持沪深股票六位代码，如 600519 或 000001")
        suffix = ".SS" if code.startswith("6") else ".SZ"
        if "." in symbol and symbol != code + suffix:
            raise ValueError("A 股代码与交易所后缀不一致")
        symbol = code + suffix
        provider, interval, currency, zone, unit, session = "eastmoney", "1d", "CNY", "Asia/Shanghai", "lots_100_shares", "regular"
    else:
        raise ValueError("不支持的市场")
    preset = next((p for p in PRESETS if p["market"] == market and p["symbol"] == symbol), {})
    aliases = preset.get("aliases", [symbol] if market == "us" else [])
    source_url = ("https://www.binance.com/en/trade/" + symbol.replace("/", "_") + "?type=spot" if market == "crypto" else
                  "https://quote.eastmoney.com/" + ("sh" if symbol.endswith(".SS") else "sz") + symbol[:6] + ".html" if market == "cn" else
                  "https://finance.yahoo.com/quote/" + symbol + "/history/")
    return {
        "market": market, "symbol": symbol, "name": preset.get("name", symbol),
        "provider": provider, "interval": interval, "currency": currency, "timezone": zone,
        "volume_unit": unit, "adjustment": "none", "session": session,
        "source_url": source_url,
        "aliases": aliases, "news_query": " OR ".join(f'"{alias}"' if " " in alias else alias for alias in aliases),
    }


def quality_summary(candles: list[dict]) -> dict:
    flags = sorted({flag for candle in candles for flag in candle.get("quality", [])})
    return {
        "status": "empty" if not candles else "warning" if flags else "ok", "flags": flags,
        "missing_rows": sum("missing_ohlcv" in c.get("quality", []) for c in candles),
        "open_rows": sum(not c.get("closed", False) for c in candles),
        "gaps": sum("gap_before" in c.get("quality", []) for c in candles),
        "calendar_verified": bool(candles) and not any("calendar_unconfirmed" in c.get("quality", []) for c in candles),
    }
