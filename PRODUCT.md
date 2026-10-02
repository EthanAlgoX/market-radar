# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A single user researching trading information on their own computer. The user wants public news, followed authors, account feeds and market-data signals in one local workspace, with enough provenance to inspect the original evidence.

## Product Purpose

Market Radar is a locally runnable website that collects public information by keyword and through the user's authorized X or Reddit account, stores it locally and presents it with original source links. A separate watchlist collects public candles and explains price and volume events alongside relevant local news.

## Operating Context

Research topics include macroeconomics, cryptocurrency, US stocks, Hong Kong stocks, mainland China stocks, financial news and gold. Reference open-source projects are stored separately in `../reference`. The site starts in English, supports a persistent Chinese interface and offers optional API-based Chinese reading of source content.

## Capabilities and Constraints

### Six task entry points

- **News library:** all locally collected information across ingestion channels. Search & collect fetches external content; the library's search, topic, source and sort controls operate on saved content. Collecting a query then applies that query to the library.
- **Following:** content from followed/configured authors and supported personal subscriptions. Posts must not be discarded merely because they lack a research keyword.
- **For you:** the supported X recommendation feed and Reddit API homepage. The Reddit API result is not guaranteed to reproduce the website's recommendation algorithm.
- **Saved:** bookmarked local information. Refresh reloads saved content rather than initiating collection.
- **Markets & signals:** a manual-refresh watchlist, inspectable candles, closed-data rule signals and related local news.
- **Settings:** Accounts, Research, RSS feeds, Translation API and Source status.

Keyword, following and recommendation collection remain independent ingestion channels even though the News library can display all of them. Local source filters do not change the collection scope. Changing a news channel resets local filters. Workspace routes and filters are represented in the URL for refresh and browser navigation.

### Personal sources and processing

Personal access requires the user's own authorization. Unconnected, failed or rate-limited sources show their actual state. Partial collection retains successful results and exposes source-specific errors. Preserve original text, URLs, publication time and collection provenance before producing optional AI summaries.

Research and RSS save only their own configuration fields. Unsaved drafts survive section and workspace changes while the app remains open. Credential drafts stay in memory rather than local browser persistence. Saving one section must not submit unconfirmed edits from another section. The already-open market workspace also stays mounted so returning from Settings preserves its instrument and detail tab; Back to news/markets follows the entry workspace.

### Languages and translation

English is the default interface. The top-bar Chinese/English switch changes built-in UI copy locally and needs no API. Source-content Original/中文 is a separate persistent reading preference; changing the interface language must not request translation or upstream market data.

Chinese source-content translation requires the user's own LLM API, configured in Settings → Translation API or provided through local environment settings. Missing configuration explains the requirement and links to the form. Custom OpenAI-compatible providers and models are supported independently of optional AI summaries. Keep UI-entered keys encrypted locally, never return saved credentials to the browser, preserve original text, and identify untranslated, excerpt-only or failed content truthfully. Hidden market tabs/workspaces do not register related news for translation.

### Market data

Market data has its own local database and manual refresh queue. Supported initial sources are Binance USDT spot pairs at one hour, US/HK stocks and ETFs through Yahoo daily data, and mainland Shanghai/Shenzhen stocks through Eastmoney daily data. The watchlist supports at most 20 instruments; the chart displays a bounded candle window, not complete historical backfill.

Preserve currency, volume units, timezone, source, adjustment, session, closed-state and revisions. Confirm signals only from sufficient closed data. Missing values, open candles, gaps, corporate actions, freshness uncertainty and failed updates remain visible. A failed refresh retains previous historical evidence. Signal markers are optional and hidden by default; Signals, Related news and Data & rules provide separate inspection views.

The app does not execute trades, guarantee live prices or claim causal relationships between news and price changes.

## Evidence on Hand

The workspace contains real public RSS and Hacker News content and public Binance/Yahoo/Eastmoney candle observations, including a visible failed stock-source update. Do not add synthetic posts or fabricated market prices as current results.

v0.5 layout evidence includes real desktop and 375px / 390px mobile screenshots in light/dark and English/Chinese modes. Account-disconnected states, existing API configuration, source text, research drafts and historical market-data warnings have been visually inspected. Personal X/Reddit adapters also have offline-response tests; real login and account-feed behavior still require the user's own session and have not been demonstrated by those screenshots. Final screenshots confirm the mobile close action, API field sizes and optional chart markers. Browser checks also verified return-navigation continuity, marker toggling and a 375px viewport without horizontal overflow or console errors. Full accessibility conformance is not established by this visual review.

## Product Principles

- Start with search and reading, with original evidence one click away.
- Give collecting, filtering, reading and configuring distinct controls.
- Persist collected information before summarizing or translating it.
- Keep partial failures and data-quality limits visible and recoverable.
- Preserve user drafts and keep credentials out of browser responses.

## Open Decisions

Market Radar / 交易雷达 remains the working product name. The user has not specified an external brand identity. Current scope assumes one local user; additional permitted stock-data sources, longer history and offline backtesting remain future work.
