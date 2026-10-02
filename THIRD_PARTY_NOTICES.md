# Third-party notices

Market Radar installs libraries through its dependency files; reference platforms are kept outside this repository. Market adapters, persistence, event rules and the application interface are independently implemented. Exact installed versions are recorded in `backend/uv.lock` and `frontend/package-lock.json`.

## TradingView Lightweight Charts

TradingView Lightweight Charts™
Copyright (с) 2025 TradingView, Inc. https://www.tradingview.com/

Lightweight Charts is used for market charts under Apache-2.0. The application preserves its attribution logo and an explicit TradingView link. The build includes the complete [license](frontend/public/licenses/lightweight-charts-LICENSE.txt) and [notice](frontend/public/licenses/lightweight-charts-NOTICE.txt). Charts consume our configured providers' data; this library does not supply TradingView market data.

## Market libraries

| Library | Upstream code license | Application use |
| --- | --- | --- |
| [AKShare](https://github.com/akfamily/akshare) | MIT | Public stock-history adapter |
| [yfinance](https://github.com/ranaroussi/yfinance) | Apache-2.0 | Yahoo stock-history adapter |
| [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) | Apache-2.0 | Stock sessions, holidays and close times |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause | Numerical arrays |
| [TA-Lib Python](https://github.com/TA-Lib/ta-lib-python) | BSD-2-Clause; underlying C library BSD-3-Clause | Technical indicator calculations |

These code licenses do not grant rights to redistribute upstream market data. Public endpoints' coverage, availability and data-use conditions remain separate. CCXT, daily_stock_analysis, QuantDinger and Freqtrade informed the research and design; their platform code is not vendored or imported by this application. QuantDinger's frontend, vectorbt and GPL/AGPL reference engines are not production dependencies.

Existing social/news dependencies and reference snapshots are documented in [docs/REFERENCES.md](docs/REFERENCES.md).
