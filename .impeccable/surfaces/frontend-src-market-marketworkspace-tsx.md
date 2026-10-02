---
version: 1
slug: "frontend-src-market-marketworkspace-tsx"
primary_target: "frontend/src/market/MarketWorkspace.tsx"
related_targets: ["frontend/src/market/Chart.tsx","frontend/src/market/market.css","frontend/src/market/helpers.ts"]
---

# Markets & signals v0.5

Mode: Operate. Extend the established local research workbench; retain its gray workspace, white panels, system type and blue actions. English is the default interface, with independently selectable Chinese source-content reading for related news.

THESIS: let the user inspect price and volume first, then verify rule evidence and related information. Keep market refresh separate from news collection and local filtering.

STORY: add → refresh → inspect currency, timeframe, candle status and freshness → inspect Signals → read Related news → check Data & rules. Failed updates preserve prior historical evidence and explain the failure. Associated news is context, not a causal claim.

FIRST VIEWPORT: desktop shows a compact watchlist beside the selected instrument's identity, quote, quality note and chart. At 760px or below, a native current-instrument select replaces the long watchlist; Manage expands rows and removal controls. Empty watchlists expose adding an instrument directly.

FORM: the chart is persistent above three detail tabs: Signals, Related news, Data & rules. Signal evidence and full metadata are available without flooding the default view. Show signal markers is off by default so labels do not obscure candles; toggling markers does not rebuild the chart. Keyboard arrows/Home/End navigate detail tabs.

PROOF: real OHLCV, source, currency, volume units, timezone, adjustment, closed-state, quality flags, numerical rule parameters and revision evidence. Hollow candles identify open intraday data. Missing values, bounded history and freshness uncertainty remain explicit. Model-generated prose must not replace numerical signal evidence.

Related news provides its own Original/中文 control and Translation API link. It participates in translation only while its tab and market workspace are visible; opening the news library applies the instrument's research keyword to local content. Interface language changes must not refresh upstream candles or translate hidden news. The opened workspace remains mounted while hidden, and returning from Settings preserves the selected instrument and detail tab.

Constraints: at most 20 instruments; a bounded visible candle window; crypto 1h and stock 1d; manual upstream refresh; no synthetic quotes or trading execution. Preserve the viewed chart range across ordinary language/layout changes. Future permitted intraday stock sources and offline backtesting remain open work.

Evidence: real desktop and 390px Chinese mobile screenshots show watchlist selection, historical quote labeling, freshness warnings, chart layout and a failed mainland-stock update. The final desktop screenshot confirms optional markers hidden by default, keeping candles unobscured. Root browser checks verified marker toggling and AAPL / Related news → Translation API → Back to markets preserving the selection. Live price guarantees, connected-account behavior and complete accessibility conformance are not established by these images.
