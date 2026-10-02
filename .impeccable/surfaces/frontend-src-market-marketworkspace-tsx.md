---
version: 1
slug: "frontend-src-market-marketworkspace-tsx"
primary_target: "frontend/src/market/MarketWorkspace.tsx"
related_targets: ["frontend/src/market/Chart.tsx","frontend/src/market/market.css"]
---

# 行情与信号工作区

Scope: extend the existing local research workbench in Operate mode. The user adds a market symbol, refreshes public candles, checks an observed price or volume event, then opens related news or the original source.

THESIS: a watchlist beside an inspectable candle chart makes the evidence behind each event visible. Keep the market workspace separate from keyword and personal information feeds.

OWN-WORLD: retain the existing gray workspace, white panels, blue actions and Chinese system type. Use the established light/dark tokens; color on candles explains direction, while text states data quality.

STORY: add → refresh → inspect timeframe, units and freshness → expand signal evidence → review source links and relevant local news. An empty watchlist explains the first action. A failed refresh preserves prior evidence and labels it historical.

FIRST VIEWPORT: show the workspace title and refresh action, a compact watchlist on the left, and the selected symbol plus chart on the right. Mobile places the selectable watchlist before the chart. The first empty view puts adding a symbol in reach.

FORM: ordinary extension of the incumbent workbench. The watchlist/detail arrangement supports repeated comparison. No new-world seed or staging was selected.

Proof: actual public OHLCV, closed-state and quality flags; numerical rule parameters, event times and provenance; related news association is not a causal claim. Keep model-generated prose out of numerical signals. Translation uses the existing global reading mode for news text.

Constraints: at most 20 symbols and 180 visible bars; crypto 1h, stocks 1d; no synthetic current quotes, automatic trading or automatic network request on add. Preserve missing data and revision history. Unresolved: future permitted intraday stock sources and offline backtesting.
