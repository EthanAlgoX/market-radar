[English](WORKFLOWS.md) · [简体中文](WORKFLOWS.zh-CN.md) · [README](../README.md)

# Workspace workflows

Market Radar separates collecting new information, reading saved information, and inspecting market data. The interface starts in English. Its language preference and content-reading preference are independent.

## Navigation and links

| Area | Purpose |
| --- | --- |
| News library | Search and filter all locally collected channels, or collect more keyword research |
| Following | Read posts from followed authors, account subscriptions and enabled RSS feeds |
| For you | Read the connected X For You feed or Reddit API homepage |
| Saved | Revisit bookmarks from any channel |
| Market & signals | Manage a watchlist, refresh candles and inspect rule events |
| Settings | Accounts, Research, RSS feeds, Translation API and Source status |

Switching news channels clears the previous query, topic and source filters. Topic filtering is available in News library and Saved. Following and For you preserve content that has no research keyword match.

The URL hash records the page, channel and local filters. Browser back/forward restores them, and refreshing a valid link opens that workspace. Example links for a running local service:

- [Bitcoin keyword research](http://localhost:8787/#/news?topic=crypto&q=Bitcoin)
- [Following](http://localhost:8787/#/news?channel=following)
- [Saved Reddit items](http://localhost:8787/#/news?channel=bookmarked&source=reddit&sort=latest)
- [Market workspace](http://localhost:8787/#/markets)
- [Translation API](http://localhost:8787/#/settings?tab=translation)
- [Source status](http://localhost:8787/#/settings?tab=health)

Queries are URL encoded; unrecognized routes and enum values fall back to safe defaults. These links do not encode the selected reader item, market instrument or unsaved settings drafts.

The active market instrument and analysis tab stay in memory while navigating the running page, including a visit to Translation API settings. Browser reload resets that market selection. Local-query typing is combined into a single history step.

## Collect and filter keyword research

1. Open **News library**, enter a query in the collection box, and select **Collect news**. The source list below the box identifies the actual collection targets.
2. The job reports progress and source failures. Successful items remain saved when another source fails.
3. The local list filters by the submitted query. Use the visible filter chips or **Clear filters** to widen the results.
4. Use **Search your local library**, topic, source and sorting controls to inspect saved items. **Reload local list** rereads local records without collecting new posts.

Collection uses Google News, Hacker News, enabled RSS feeds and connected personal sources. A local source filter cannot restrict or redirect collection. RSS without a keyword match is independently available through Following. Queries support financial aliases, phrases, parentheses and `OR` / `AND` / `NOT`.

The sidebar's saved keywords filter the local library and prepare the collection query. Quick-search buttons inside the collection box only fill that box. Neither shortcut starts a network collection until you select **Collect news**. **Export all** exports the saved library rather than the visible filter result; JSON and CSV are available through the export API.

## Following and account feeds

In **Settings → Accounts**, authorize your own X or Reddit account. X login opens an isolated browser; Reddit requires an application with API access. You can synchronize the available following/subscription list and manage specified authors in **Research**.

Select **Collect following** to collect followed-person and subscription content without a keyword requirement. Enabled RSS subscriptions work here even without a personal account. Add or enable them in **Settings → RSS feeds**, then select **Save feeds** before collecting.

Select **Collect account feed** in For you to request connected personal feeds. RSS and public news do not supply this channel. X uses an unofficial Twikit session interface, so changes to the platform or expired sessions may interrupt access. Reddit uses OAuth `best`, which can differ from its website recommendations; its subscription synchronization may not reproduce the complete website following list. Platform, pagination and request limits bound both channels. A configured RSSHub URL alone does not establish access to your personal homepage.

Personal-account paths have offline regression coverage. Actual collection with your account still depends on your authorization, session and provider access.

## Read, save and translate

Open a title to read it and mark it read. The reader keeps the source, author, publication time and original link visible. **Overview** distinguishes a source excerpt from an optional AI summary. **Source text** displays what collection returned; **Load article text** attempts to extract an accessible article on demand. Sources may provide only a title or excerpt. Reddit and Hacker News discussions load a limited set of comments when requested.

Bookmark an item to make it available in Saved. Saved has local filtering and reload controls, with no collection action.

The top-bar **中文 / English** switch changes built-in interface text without an LLM call. **Read in → 中文** requests Chinese content translation; market-related news has the same reading preference. The browser remembers both choices separately. Switching only the interface language does not start translation.

Content translation requires your own API configured in **Settings → Translation API**, or an available environment fallback. DeepSeek Flash is the default; custom OpenAI-compatible Chat Completions services are supported. Without configuration, the page links to API settings and keeps the original. Translation sends the relevant text to your configured provider. Current results are cached by original-text revision, provider and model; errors retain the original and offer retry. The reader uses **Chinese translation** only when that item's translation is ready, and retains access to the source text.

AI summaries remain an optional, separately configured Research feature. They do not enable translation by themselves.

## Inspect candles and signals

Add a supported instrument, then refresh it or the watchlist. Adding alone does not fetch data. The watchlist allows 20 instruments, and charts show up to 180 candles: hourly Binance USDT spot pairs or daily US, Hong Kong and mainland China equities within the supported provider scope.

Below the chart:

| Tab | What to inspect |
| --- | --- |
| Signals | Closed-candle rule events; expand a record for observed values, rule evidence, confirmation time and source |
| Related news | Up to eight locally saved items matched by instrument and the stated time window; continue in News library to filter or collect more |
| Data & rules | Candle time, receipt time, currency, volume units, adjustment, coverage, quality notes and rule requirements |

Data warnings remain near the chart rather than disappearing behind a tab. Source errors retain existing data; stale events are historical, and pending revalidation is explicitly labeled. The app does not infer causation from coincident news or execute trades. See the [README market scope](../README.md#market-data-and-signals) for providers and finite-history limits.

## Configure and save

Research, RSS feeds, RSSHub URL and Translation API save independently. Saving one does not commit another section's pending edits. Unsaved dots and a pending-section list show where work remains; **Discard changes** resets only its section. Errors appear next to settings and preserve entered values. Account synchronization refreshes untouched fields while retaining locally edited fields.

Drafts remain in memory when moving between settings sections or returning to news and markets. Save before reloading or closing the browser: unsaved drafts do not survive either action. Stored translation keys are encrypted and never returned in configuration responses. Local API saves take effect immediately; environment changes require restarting the service.

**Source status** separates recent attempts from successful collection and shows partial failures or unavailable connections. It describes news collection sources; market data has its own quality, refresh and provider status.

## Workflow API map

All paths below use the local service; API schemas are available at [localhost:8787/docs](http://localhost:8787/docs).

| Workflow | API |
| --- | --- |
| Local list and filters | `GET /api/items` |
| Collection and progress | `POST /api/collect`, `GET /api/jobs/{id}` |
| Read state and bookmarks | `PATCH /api/items/{id}` |
| Article, discussion, optional summary | `POST /api/items/{id}/content`, `/discussion`, `/summarize` |
| Settings and RSS presets | `GET/PUT /api/settings`, `GET /api/source-presets` |
| Personal account authorization/sync | `/api/connections/x/*`, `/api/connections/reddit/*` |
| Translation settings and jobs | `/api/translation/config`, `/api/translation/status`, `POST /api/translate`, `GET /api/translation/jobs/{id}` |
| Watchlist, candles and signals | `/api/market/overview`, `/watchlist`, `/refresh`, `/jobs/{id}`, `/instruments/{id}` |
| Export all collected items | `GET /api/export?format=json` or `format=csv` |
