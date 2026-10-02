import assert from "node:assert/strict";
import test from "node:test";
import { editorFromSettings, mergeSettingsEditor, scopeDirty, settingsPayload } from "./settingsDraft.ts";

const saved = {
  keywords: ["gold"], authors: { x: ["alice"], reddit: ["bob"] },
  rss_feeds: [{ id: "feed", name: "News", url: "https://example.com/feed", enabled: true }],
  rsshub_url: "", auto_refresh_minutes: 30,
  llm: { enabled: false, base_url: "https://example.com/v1", model: "model", api_key: { configured: true } },
};

test("saving feeds cannot save research changes or credentials", () => {
  const editor = { ...editorFromSettings(saved), keywords: "bitcoin", llmKey: "private-draft-key", feeds: [] };
  assert.deepEqual(settingsPayload(editor, "feeds"), { rss_feeds: [] });
  assert.deepEqual(settingsPayload(editor, "rsshub"), { rsshub_url: "" });
  assert.equal(scopeDirty(editor, saved, "feeds"), true);
  assert.equal(scopeDirty(editor, saved, "preferences"), true);
});

test("research save normalizes lists and omits unchanged key", () => {
  const editor = { ...editorFromSettings(saved), keywords: "gold\ngold,bitcoin", xAuthors: "@alice\nalice", redditAuthors: "u/bob\n@bob" };
  const payload = settingsPayload(editor, "preferences");
  assert.deepEqual(payload.keywords, ["gold", "bitcoin"]);
  assert.deepEqual(payload.authors, { x: ["alice"], reddit: ["bob"] });
  assert.equal("api_key" in payload.llm, false);
  assert.equal("rss_feeds" in payload, false);
});

test("research payload never serializes returned secret metadata", () => {
  const editor = { ...editorFromSettings(saved), llm: { ...saved.llm } };
  const payload = settingsPayload(editor, "preferences");
  assert.equal("api_key" in payload.llm, false);
  assert.deepEqual(Object.keys(payload.llm).sort(), ["base_url", "enabled", "model"]);
});

test("account sync updates untouched author list without discarding other drafts", () => {
  const editor = { ...editorFromSettings(saved), keywords: "gold\nbitcoin", feeds: [], llmKey: "draft-only" };
  const incoming = { ...saved, authors: { x: ["alice", "carol"], reddit: ["bob"] }, auto_refresh_minutes: 60 };
  const result = mergeSettingsEditor(editor, saved, incoming);
  assert.equal(result.keywords, "gold\nbitcoin");
  assert.equal(result.xAuthors, "alice\ncarol");
  assert.equal(result.refreshMinutes, 60);
  assert.deepEqual(result.feeds, []);
  assert.equal(result.llmKey, "draft-only");
});

test("incoming settings preserve locally edited author and API fields", () => {
  const editor = { ...editorFromSettings(saved), xAuthors: "different", llm: { ...saved.llm, enabled: true } };
  const incoming = { ...saved, authors: { ...saved.authors, x: ["synced"] }, llm: { ...saved.llm, model: "new" } };
  const result = mergeSettingsEditor(editor, saved, incoming);
  assert.equal(result.xAuthors, "different");
  assert.equal(result.llm.enabled, true);
  assert.equal(result.llm.model, "model");
});

test("a successful scoped save clears only that scope's dirty state", () => {
  const editor = { ...editorFromSettings(saved), keywords: "bitcoin", feeds: [] };
  const incoming = { ...saved, rss_feeds: [] };
  const result = mergeSettingsEditor(editor, saved, incoming);
  assert.equal(scopeDirty(result, incoming, "feeds"), false);
  assert.equal(scopeDirty(result, incoming, "preferences"), true);
});
