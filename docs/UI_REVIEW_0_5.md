# 0.5 workspace review and verification

[English README](../README.md) · [中文 README](../README.zh-CN.md) · [Workflow guide](WORKFLOWS.md)

Reviewed on 2026-10-03 using the running local site and its real saved content. The change preserves the existing Market Radar visual identity and reorganizes the research workflow. No sample news, simulated quotes or account connections were added for presentation.

## Initial walkthrough

The audit first captured these ten states from the existing site. Screenshots are local verification artifacts under `output/playwright/v05-audit/`, excluded from the repository.

| Step | Screen | Finding |
| --- | --- | --- |
| 1 | News on a narrow viewport | Collection, filtering and reading language competed for space |
| 2 | Following | Prior topic/source filters could hide independently collected posts |
| 3 | For you | The next action needed to reflect disconnected accounts |
| 4 | Accounts on desktop | Source diagnostics pushed the sign-in task down the page |
| 5 | Research settings | One shared draft could accidentally save another section |
| 6 | RSS settings | Presets appeared before the user's own subscriptions |
| 7 | Translation API | Configuration and reading mode needed clearer separation |
| 8 | Markets | Chart, signals, related news and lengthy data details shared one long view |
| 9 | Desktop news | Unselected context occupied useful reading space |
| 10 | Desktop reader | The fixed narrow pane made long titles and source text difficult to read |

The existing site already preserved original links, source identity and real data-quality states. Those behaviors remain part of the revised design.

## Resolved logic and interface issues

| Priority | Issue | Result |
| --- | --- | --- |
| P1 | Local source selection changed collection targets | Collection now resolves the active channel's supported sources independently |
| P1 | Channel changes carried unrelated filters | Switching channel clears local topic, source and query filters |
| P1 | Shared settings saves crossed section boundaries | Research, RSS, RSSHub and Translation API submit their own fields |
| P1 | Account synchronization discarded edited settings | Incoming settings update untouched fields and preserve dirty drafts |
| P2 | Library semantics excluded personal channels | News library searches all saved channels; personal views retain channel filters |
| P2 | Chinese reading was coupled to interface language | The two persisted preferences are independent; interface changes make no translation request |
| P2 | Reader labels overstated available translation/full text | Labels distinguish returned text, extracted text and completed translation |
| P2 | Search results did not reflect the requested query | Completed collection applies its query to the local library with removable filters |
| P2 | URL normalization and typing polluted browser history | Startup/restored URLs use replacement; typing coalesces within a local query |
| P2 | API configuration interrupted market reading context | The market view retains its selected instrument and tab; Settings returns to that workspace |
| P2 | Dense chart labels obscured candles | Signal markers default to hidden and can be enabled without rebuilding the chart |
| P2 | Mobile reader close icon was unclear | Overlay reading uses a conventional close icon |
| P3 | Errors used a success-looking toast | General feedback uses a neutral icon; form errors appear inline |

## Implemented structure

Six destinations share one navigation: News library, Following, For you, Saved, Markets and Settings. Collection appears above the saved library; local search, topic, source and sort controls sit with the list. With no selection, the list uses the workspace width. Selecting an item opens a wider desktop reader; tablet and mobile reading use an overlay.

Settings prioritizes account connection and separates source diagnostics, research, subscriptions and translation. Own subscriptions appear before optional presets. Pending edits have section indicators and discard controls. Drafts survive navigation in the running page and are discarded by browser reload or close.

Markets prioritizes the price/volume chart. Signals, Related news and Data & rules have their own tabs. Freshness and quality warnings remain near the quote. Mobile uses a compact instrument selector with expandable management.

## Verification

- **Automated:** 256 backend tests and 28 frontend tests passed. Production TypeScript/Vite build and `git diff --check` passed.
- **Runtime:** restarted production service; `/health` reports `0.5.0`.
- **Data:** both SQLite databases passed integrity checks. All rows in the 8 news tables and 7 market tables matched the pre-upgrade backups, including settings and credentials.
- **Desktop:** news library, reader, personal empty states, accounts, research draft, RSS, API configuration and market workspace inspected at 1440 × 1000.
- **Mobile:** original and Chinese interfaces, reading, accounts, API fields and market selector inspected at 390 × 844; final API/reader confirmation also at 375 × 812. No horizontal page overflow in checked views; mobile inputs use 16px text.
- **Navigation:** local-query typing followed by Back returns to the unfiltered library in one step. Reload restores the route. News channel changes clear prior conditions.
- **Drafts:** an unsaved research edit survived tab changes and leaving/reopening Settings. Discard restored the saved keywords; the test draft was not persisted.
- **Market continuity:** AAPL → Related news → Translation API → Back to markets preserved AAPL and the Related news tab.
- **Chart:** markers toggle between shown/hidden, with accurate visible and accessible state labels. Existing closed-candle filtering remains intact.
- **Keyboard:** mobile navigation wraps focus, and navigation/reading close with Escape. The reader returns focus on close. Form labels and tab semantics were inspected.
- **Appearance:** light/Chinese mobile and dark/English mobile screenshots reviewed. Independent screenshot review identified the close-icon and chart-label issues; final confirmation shows both resolved.
- **Browser:** no console errors in final confirmation. Temporary viewport overrides were reset.

Final screenshots are in `output/playwright/v05-qa/`: `final-news-desktop.jpg`, `final-reader-desktop.jpg`, `final-market-desktop.jpg`, `final-api-mobile.jpg` and `final-reader-mobile.jpg`.

## Verification limits

This is a targeted interface and functional review, not a complete screen-reader or WCAG conformance audit. Real X/Reddit account login and live personal-feed coverage require the user's authorization and provider access; those account integrations retain offline regression coverage. This review did not change credentials, issue new upstream collection/market refreshes or make paid translation calls.
