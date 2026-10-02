---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/TranslationSettings.tsx","frontend/src/i18n.ts","frontend/src/styles.css"]
---

# English-first research and personal translation

Mode: Operate. Extend the existing local trading research workbench; preserve its gray workspace, white panels, system type and blue actions.

The user starts in English, searches or reads real source content, switches to Chinese, and configures a personal LLM API when source-content translation needs it. UI copy switches locally. Source text and user keywords are not mechanically relabeled.

The header exposes interface language and source reading mode as separate actions. Settings → Translation contains base URL, model and a blank password field; source and key presence explain the current state without exposing secrets. Missing configuration links directly to this form. Save errors retain entered values and allow retry; saved credentials are never sent back to the browser. English and Chinese READMEs link to one another.

Use flexible labels, local date/number formatting, mobile touch areas and wrapped explanatory copy. Keep language changes independent of upstream market requests. Resize candle charts while preserving the viewed candle range.

Validation: English desktop/feed, English and Chinese mobile/API, persistent language after refresh, empty API setup, failed save and retry, save/removal, existing cached news, and source links. Verify with browser-local API responses rather than altering the user's credentials.
