import type { Settings } from "./types";

export type SaveScope = "preferences" | "feeds" | "rsshub";
export interface SettingsEditor {
  keywords: string;
  xAuthors: string;
  redditAuthors: string;
  feeds: Settings["rss_feeds"];
  rsshubUrl: string;
  refreshMinutes: number;
  llm: Pick<Settings["llm"], "enabled" | "base_url" | "model">;
  llmKey: string;
}
export const splitList = (text: string) => [...new Set(text.split(/[\n,，;；]/).map(value => value.trim()).filter(Boolean))];
const authors = (text: string, platform: "x" | "reddit") => [...new Set(splitList(text).map(value => value.replace(platform === "x" ? /^@/ : /^(?:u\/|@)/, "")).filter(Boolean))];
const equal = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

export function editorFromSettings(settings: Settings): SettingsEditor {
  return {
    keywords: settings.keywords.join("\n"), xAuthors: settings.authors.x.join("\n"), redditAuthors: settings.authors.reddit.join("\n"),
    feeds: settings.rss_feeds, rsshubUrl: settings.rsshub_url, refreshMinutes: settings.auto_refresh_minutes,
    llm: { enabled: settings.llm.enabled, base_url: settings.llm.base_url, model: settings.llm.model }, llmKey: "",
  };
}

export function settingsPayload(editor: SettingsEditor, scope: SaveScope) {
  if (scope === "feeds") return { rss_feeds: editor.feeds };
  if (scope === "rsshub") return { rsshub_url: editor.rsshubUrl.trim() };
  return {
    keywords: splitList(editor.keywords), authors: { x: authors(editor.xAuthors, "x"), reddit: authors(editor.redditAuthors, "reddit") },
    auto_refresh_minutes: editor.refreshMinutes,
    llm: { enabled: editor.llm.enabled, base_url: editor.llm.base_url.trim(), model: editor.llm.model.trim(), ...(editor.llmKey.trim() ? { api_key: editor.llmKey.trim() } : {}) },
  };
}

export function scopeDirty(editor: SettingsEditor, settings: Settings, scope: SaveScope) {
  return !equal(settingsPayload(editor, scope), settingsPayload(editorFromSettings(settings), scope));
}

/** Refresh untouched fields while preserving local edits, including during account sync. */
export function mergeSettingsEditor(editor: SettingsEditor, previous: Settings, incoming: Settings): SettingsEditor {
  const before = editorFromSettings(previous), next = editorFromSettings(incoming);
  return {
    keywords: equal(splitList(editor.keywords), previous.keywords) ? next.keywords : editor.keywords,
    xAuthors: equal(authors(editor.xAuthors, "x"), previous.authors.x) ? next.xAuthors : editor.xAuthors,
    redditAuthors: equal(authors(editor.redditAuthors, "reddit"), previous.authors.reddit) ? next.redditAuthors : editor.redditAuthors,
    feeds: equal(editor.feeds, before.feeds) ? next.feeds : editor.feeds,
    rsshubUrl: editor.rsshubUrl === before.rsshubUrl ? next.rsshubUrl : editor.rsshubUrl,
    refreshMinutes: editor.refreshMinutes === before.refreshMinutes ? next.refreshMinutes : editor.refreshMinutes,
    llm: equal(editor.llm, before.llm) ? next.llm : editor.llm,
    llmKey: editor.llmKey,
  };
}
