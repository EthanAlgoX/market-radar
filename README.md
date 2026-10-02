[English](README.md) · [简体中文](README.zh-CN.md)

# Market Radar

A local workspace for market research. Search public news and social posts, organize your own X or Reddit feeds, and inspect price and volume signals alongside related news. Every collected item keeps its original source link.

The interface starts in **English** and can switch to **简体中文**. Source text stays in its original language by default; Chinese reading uses your configured LLM API and keeps the originals intact.

Current release: **0.4**. See the [release notes](docs/UPGRADE_0_4.md) for bilingual reading and personal translation APIs, and [0.3](docs/UPGRADE_0_3.md) for the market-data implementation.

## Run locally

Requirements: macOS or Linux, **Node.js 22.12+** with npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Setup creates a Python 3.12 environment, installs the locked dependencies and the isolated browser used for X login, and builds the frontend.

```bash
git clone https://github.com/EthanAlgoX/market-radar.git
cd market-radar
./setup.sh
./start.sh
```

Open **[http://localhost:8787](http://localhost:8787)**. After the first setup, use `./start.sh` or `npm start` for subsequent runs. On macOS, you can also double-click `start.command`. Press `Ctrl+C` in the terminal to stop the service.

The service binds to `127.0.0.1`. Use `localhost` or `127.0.0.1` so that account callbacks and browser-origin checks work correctly.

## Start researching

1. **Search news.** Enter a keyword or choose a market topic: macro, crypto, US stocks, Hong Kong stocks, China A-shares, finance or gold. Queries support phrases, parentheses, `OR`, `AND` and `NOT`, with English/Chinese financial aliases.
2. **Build a watchlist.** Open the market workspace, add a symbol such as `BTC/USDT`, `AAPL`, `0700.HK` or `600519.SS`, then refresh to fetch candles.
3. **Connect your feeds.** Open Settings to connect your own X or Reddit account, manage followed authors, and add public RSS feeds.
4. **Choose a language.** Switch the interface to Chinese without an API. Configure a translation provider in Settings to read collected articles and posts in Chinese.

## News and social feeds

| Channel | What it collects |
| --- | --- |
| Keyword research | Google News RSS search, financial RSS, and connected X/Reddit sources; Hacker News and an external RSSHub instance are also supported |
| Following | Followed-account content and enabled subscriptions, without requiring a keyword match |
| Recommendations | Your connected X For You feed or Reddit's OAuth `best` homepage |

These channels remain independent: an item can belong to more than one channel. Collection coverage is bounded by each provider's API, pagination, request and time limits; the app shows failures and partial results.

- Read titles, source text, excerpts, publication times, matched terms and collection provenance. Open the original link at any time.
- Filter and sort saved items, mark them read, bookmark them, and export JSON or CSV.
- Fetch accessible article text on demand, or load a limited set of Reddit/Hacker News comments in the reading panel.
- Deduplicate by platform IDs, feed IDs and conservative URL normalization. Similar headlines are not automatically merged into a single news event.
- Keep durable collection jobs and cached RSS responses. Failed sources do not discard successful results; interrupted jobs resume after a restart.

New installations include feeds from the Federal Reserve, ECB, CoinDesk, Yahoo Finance, CNBC Finance and HKEX. Existing subscriptions are preserved. Optional scheduled news refresh runs only while the local service is running; market refresh remains manual. AI summaries are optional and are configured separately from content translation.

## Market data and signals

The watchlist starts empty, supports up to **20 symbols**, and fetches data only when you request a refresh. The chart shows up to **180 candles**, volume, MA20/MA60, and historical rule events.

| Market | Provider and supported scope | Data convention |
| --- | --- | --- |
| Crypto | Binance public REST; USDT spot pairs, 1-hour candles | Source close time and server clock; base and quote volume preserved |
| US / Hong Kong | yfinance / Yahoo; stocks and ETFs, daily regular-session candles | Provider prices retained with `auto_adjust=False` and `repair=False`; dividends, splits and null values preserved |
| China A-shares | AKShare / Eastmoney; Shanghai and Shenzhen stocks, daily candles | No requested price adjustment; volume reported in lots of 100 shares |

US and Hong Kong instruments are checked against the provider's asset type, currency and timezone. This implementation accepts USD-priced US equities/ETFs and HKD-priced Hong Kong equities/ETFs.

Default events cover 20-bar range breakouts, MA20/MA60 crossovers and volume expansion. Each event includes its rule parameters, numerical evidence, source and timestamps. RSI14 is available in the calculation layer, but its threshold rule is disabled by default and has no configuration control in the current interface.

Events require enough valid, closed candles. Missing values, unfinished candles, gaps and corporate actions stay visible; the app does not fill missing prices with zero or substitute an insufficient moving average. Exchange calendars, timezones and a post-close buffer determine stock closure and freshness; crypto uses the source server clock. Data receipt time is recorded separately from the candle's market time.

The analysis can use up to 240 saved candles for warmup. Stock refreshes fetch the warmup and visible window together, reducing the risk of mixing revised prices with an older cache. Data revisions are audited, and affected events are reconfirmed, withdrawn or marked for revalidation. Source failures retain saved charts and show their historical status.

Up to eight related items are matched from the existing local news library within a stated time window. This association is a research aid, not evidence that a news item caused a price move. The current scope is finite public-data snapshots and rule events; it does not include full historical backfill, streaming prices, backtesting or trade execution. Public providers can be unavailable or return incomplete data; inspect the displayed quality and freshness status before using a window.

## Language and translation

Interface language and source-content translation have different requirements:

- **English / 简体中文 interface:** local UI text switches without contacting an LLM. English is the default; the browser remembers your choice.
- **Chinese source content:** configure an API base URL, API key and model in **Settings → Translation**. The default is DeepSeek Flash (`deepseek-flash`); a custom OpenAI-compatible Chat Completions provider and model can also be used. If no provider is configured, the app points you to Settings and retains the original text.

Translation covers collected titles, summaries and bodies, including related market news. It does not translate your query, source URLs or identifiers. Translations are cached locally by original-text revision, provider and model, so unchanged content can reuse its result. Errors retain the original and offer a retry; incomplete outputs are not saved as completed translations. Text being translated is sent to the API provider you configure.

Saved API settings take effect immediately. When Chinese reading is enabled, pending items translate automatically. Removing a local override restores any available environment configuration. Changing the provider URL requires that provider's API key.

API keys entered in Settings are encrypted locally and are not returned to the browser. Environment configuration remains available as a fallback. For a new installation, create a project-root `.env` from [.env.example](.env.example); if `.env` already exists, edit it rather than replacing it.

```dotenv
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_FLASH_MODEL=deepseek-flash
```

`DEEPSEEK_BASE_URL` is also accepted as a base-URL alias. Existing terminal environment variables take precedence over `.env`. Restart the local service after changing environment configuration. Keep `.env` private; it is excluded from Git.

## Connect your accounts

### X

Use the browser-login action in Settings. It opens an isolated browser window where you sign in directly to X; Market Radar does not receive your password or reuse your normal browser profile. The connection is marked ready only after account identity verification.

The connector supports keyword search, Following, For You, author timelines and following-list synchronization. You can also enter specific authors, whose posts are collected without a keyword requirement. If browser login is unavailable, import your own Cookie JSON containing `auth_token` and `ct0`. Disconnecting clears the locally saved session.

X access uses Twikit's unofficial session interface. Platform changes, expired sessions and provider restrictions can affect availability. Real personal-account coverage and recommendation parity are not guaranteed; the project's account paths have been validated with offline responses rather than a developer's personal account.

### Reddit

You need an application that has Reddit API access. In [Reddit application settings](https://www.reddit.com/prefs/apps), set this callback:

```text
http://localhost:8787/api/connections/reddit/callback
```

Enter the Client ID and Client Secret in Settings; installed apps may leave the secret empty. Sign in and authorize read access. The refresh token is encrypted locally.

The connector supports search, subscribed communities, specified authors and the API homepage. Synchronization retrieves subscriptions exposed by the API and may not reproduce the full website following list. Recommendations use OAuth `best`, which can differ from the website's personalized feed. Logging in to Reddit does not itself grant developer API access.

An external RSSHub instance is optional. Add its full feed URLs as RSS subscriptions. Routes that need account cookies must be configured on that instance; use an isolated personal instance for account timelines.

## Development and local data

```bash
npm run dev      # frontend :5173, backend :8787, both reload on changes
npm run check    # TypeScript
npm run build    # production frontend
npm test         # backend and frontend regression tests
```

API documentation: [http://localhost:8787/docs](http://localhost:8787/docs). Health check: `/health`. Market API: `/api/market`. Export: `/api/export?format=json` or `format=csv`.

```text
frontend/           React, TypeScript, Vite, Lightweight Charts
backend/app/        FastAPI, news/social collectors, credential storage
backend/app/market/ Market adapters, queue, quality checks, rules and API
backend/tests/      Backend regression tests
backend/data/       Local databases and encrypted credentials; excluded from Git
scripts/run.mjs     Local service lifecycle and .env loading
docs/               Release notes, research, references and validation records
```

News uses `market-radar.sqlite3`; market data uses `market-radar-market.sqlite3`. Set `RADAR_DATA_DIR` before startup to choose another data directory. Stop the service before backing up the entire data directory, including any WAL files and the credential-encryption key. Keep that key with encrypted credentials when migrating to another machine. The app assumes one local user and one backend process.

## References and implementation notes

Market Radar is an independent application using installed libraries, rather than a deployment of every reference platform. The runtime includes PRAW, Twikit, yfinance, AKShare, exchange_calendars, NumPy, TA-Lib and Lightweight Charts; exact package versions are recorded in the lockfiles. CCXT and the larger aggregation/trading platforms are research references, not runtime services.

- [Reference projects and actual reuse](docs/REFERENCES.md)
- [Market-data research](docs/MARKET_DATA_RESEARCH.md) and [source research](docs/SOURCE_RESEARCH.md)
- [0.3 release notes](docs/UPGRADE_0_3.md), [0.2 release notes](docs/UPGRADE_0_2.md), and [validation record](docs/TESTING.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

Reference source checkouts are kept separately in the development workspace and are not needed to run this repository. The chart retains the required TradingView attribution, links and license notices. Historical research and test records describe their own validation dates and may be written in Chinese.
