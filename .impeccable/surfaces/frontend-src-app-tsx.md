---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/SettingsPage.tsx","frontend/src/TranslationSettings.tsx","frontend/src/workspaceLogic.ts","frontend/src/i18n.ts","frontend/src/styles.css","frontend/src/workspace.css","frontend/src/settings.css"]
---

# Research workspace v0.5

Mode: Operate for collection, filtering and settings; Read for source text. Preserve the incumbent system font, gray workspace, white surfaces and blue actions.

The navigation exposes News library, Following, For you, Saved, Markets & signals and Settings. News library includes all locally collected channels. Personal channels still use their own ingestion semantics; switching channels clears local filters. Hash routes restore the workspace and filters on refresh or browser navigation.

Search & collect fetches external information and shows the participating sources. A separate local-library search, topic/source filters, sort and removable filter chips organize saved information. Local source choice never changes the personal collection scope. Saved refresh reloads bookmarks. Disconnected personal feeds direct the user to Accounts.

The full-width list is the default first view. Selecting an item creates a wider reading pane above 1250px; at 761–1250px it overlays the right side and at 760px or below it covers the screen. Source text is the default, with the original link near the title. Excerpts and pending translation remain honestly labeled. The overlay has a recognizable close action, Escape, focus handling and scroll locking.

Settings has Accounts, Research, RSS feeds, Translation API and Source status. Personal login appears before advanced import, and the user's RSS list appears before preset catalogues. Research and RSS save their own fields. Mounted editors retain dirty drafts across tabs and workspace changes, with section-specific save/discard actions and unsaved links. Returning from Settings follows the entry workspace; an already-open market workspace retains its instrument and detail tab while hidden.

The top-bar Chinese/English control changes built-in interface copy without an API. Original/中文 in the reading toolbar controls source-content translation independently. Missing LLM configuration links to Translation API. Existing keys are never displayed, changing providers requires a new key, and credentials are not persisted in browser storage.

Mobile keeps the four news channels visible, all six entry points in the drawer, wrapped filters including sort, 16px search/settings inputs and larger touch controls. Dark mode uses the same content hierarchy. Optional AI summaries remain separate from translation.

Evidence: actual v0.5 desktop and 375px / 390px mobile screenshots cover English/Chinese news, source reading, accounts, API settings, research drafts and a dark mobile news view. Final screenshots confirm the mobile X close action, 16px API fields and full-width desktop local search. Root browser checks verified browser-return behavior and market → API → return continuity, with no horizontal overflow at 375px or console errors. Real account login, all failure paths and full keyboard/screen-reader conformance remain unverified.
