# 0.4 — English-first reading and personal translation APIs

[English README](../README.md) · [中文 README](../README.zh-CN.md)

Market Radar now starts in English, with a persistent Chinese interface switch. The news workspace, reader, accounts, RSS settings, market charts, data quality explanations and signal evidence share the same language setting. Source articles and user-entered keywords retain their original text until Chinese content translation is requested.

## Configure translation in the website

Open **Settings → Translation** and enter an API base URL, model and your own key. DeepSeek Flash is the default; custom OpenAI-compatible Chat Completions providers are supported. Saving takes effect immediately. If Chinese reading is already enabled, pending items translate automatically.

With no configuration, requesting Chinese content displays an explanation and a **Configure API** action. Interface labels can still switch locally. The app never substitutes a fabricated translation or hides the original source link.

Keys entered in this form are encrypted in the local credential store. Configuration responses include presence flags rather than key values. Leaving the key field blank keeps it only for the same API URL; changing the URL requires an explicit key. Removing a local override restores the available environment configuration. Environment changes still require a service restart.

Translation jobs capture their provider and model configuration when they start. Cache entries are separated by source revision, provider and model, preventing reuse of another provider's identically named model. Existing DeepSeek translations remain compatible.

## Documentation and display

- `README.md` is the English entry point; `README.zh-CN.md` provides the corresponding Chinese guide with reciprocal links.
- Both guides explain setup, research channels, account authorization, market data scope and API settings.
- Language selection persists across reloads. Dates, chart legends, marker labels and data units follow the interface language.
- Chart resize preserves the visible candle window when moving between mobile and desktop widths.

## Validation

- 256 backend regression tests and 11 frontend tests passed.
- TypeScript checks and the production build passed.
- Browser checks covered English defaults, persistent Chinese switching, cached Chinese reading, desktop/mobile layouts, and API form values without exposing keys.
- Missing configuration, save failure, successful save and removal were checked with browser-local responses. Those checks did not alter the user's credentials or send paid translation requests.
- Backend tests cover encrypted persistence, environment fallback, validation, immutable in-flight jobs, cross-provider cache separation and secret-free error responses.

The existing market-data provider scope and finite-history limitations remain as described in the [0.3 release notes](UPGRADE_0_3.md). Custom provider connectivity depends on the supplied endpoint, model and credentials.
