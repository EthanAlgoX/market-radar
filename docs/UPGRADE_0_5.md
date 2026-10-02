# 0.5 — Clear collection and reading workflows

[English README](../README.md) · [中文 README](../README.zh-CN.md) · [Workflow guide](WORKFLOWS.md) · [工作流程](WORKFLOWS.zh-CN.md)

The workspace now places News library, Following, For you, Saved and Market & signals in a consistent navigation structure. Collection, local filtering and reading have distinct controls. The list uses more of the available width, with a reader that opens when an item is selected; mobile navigation and reading retain their own focused views.

## Behavior changes

- **Collection and filtering are separate.** News library searches across all collected channels. Local source selection no longer changes collection targets. Keyword collection resets unrelated filters and applies its query to the local library. Visible filter chips can be removed individually or cleared together.
- **Personal channels are independent.** Channel changes clear prior topic, source and query filters. Following retains posts without keyword matches and includes enabled RSS feeds; For you uses connected personal sources. Saved reads bookmarks and has no collection action.
- **Reading language is independent.** The interface switch changes local UI copy. Chinese content reading is a separate persisted preference requiring a configured API. English UI with Chinese posts now restores correctly. The reader identifies available source text, extracted text and completed translations accurately.
- **Settings save by section.** Research, RSS feeds, RSSHub and Translation API have independent saves and visible pending edits. Account synchronization preserves locally edited fields. Drafts remain available during navigation in the running page; browser reload or close discards unsaved drafts.
- **Source diagnostics have a dedicated home.** Accounts focuses on connecting X and Reddit; Source status records collection attempts, successes and partial failures. Configuration-load failures provide retry instead of an indefinite loading state.
- **Market details use three views.** Signals, Related news and Data & rules sit below the chart. Data warnings remain visible, while numerical evidence, source conventions and rule requirements are available on demand.
- **Market reading keeps its place.** Opening Translation API and returning preserves the selected instrument and analysis tab. Chart signal markers default to hidden and can be enabled without resetting the viewed candle window.
- **Workspace links restore context.** Valid hash links and browser history restore the page, channel, topic, local query, source and sorting. Settings sections can be linked directly. Reader selection and market instrument selection are not encoded.

## Data and API boundaries

This release reorganizes the local frontend and its interactions; it retains the existing news and market storage, credential handling and collection APIs. The app continues to preserve original links and text, partial collection results, candle quality and revision history. Collection coverage remains bounded by each source. X uses an unofficial session interface, and Reddit's OAuth `best` homepage may differ from the website recommendation feed.

The market implementation remains finite public-data snapshots and closed-candle rule events, as described in [0.3](UPGRADE_0_3.md). It does not add streaming, backtesting or trade execution. Personal-account paths use offline regression fixtures; this release does not claim a live personal-account integration test.

## Regression coverage

Frontend tests cover channel-supported collection independently of local filters, encoded route restoration and invalid-route fallbacks, separate reading-language preferences, section-only settings payloads and draft retention during synchronization. Existing backend regression tests continue to cover collection, market data and translation behavior.

The local verification run passed 256 backend and 28 frontend tests, the production build, and diff checks. Desktop and mobile confirmation covered draft preservation, navigation/history, API return to the market view and signal-marker visibility. See the [review and verification record](UI_REVIEW_0_5.md) for evidence and limits.

This document records the implemented behavior and test scope. Provider access, supplied API connectivity and personal-account coverage still depend on the local user's configuration.
