import assert from "node:assert/strict";
import test from "node:test";
import { setLocale } from "./i18n.ts";
import { initialReadingChinese, parseWorkspaceHash, resolveCollectionSources, workspaceHash, workspaceHistoryMode } from "./workspaceLogic.ts";

test("collection sources follow ingestion capabilities, independently of library filters", () => {
  const connections = { x: { state: "connected" }, reddit: { state: "connected" } };
  assert.deepEqual(resolveCollectionSources("search", connections, true), ["news", "hackernews", "rss", "x", "reddit"]);
  assert.deepEqual(resolveCollectionSources("following", connections, true), ["x", "reddit", "rss"]);
  assert.deepEqual(resolveCollectionSources("recommended", connections, true), ["x", "reddit"]);
  const filteredRoute = parseWorkspaceHash("#/news?channel=following&topic=gold&q=Fed&source=news&sort=relevance");
  assert.equal(filteredRoute.view, "following");
  assert.deepEqual(resolveCollectionSources(filteredRoute.view, connections, true), ["x", "reddit", "rss"]);
});

test("RSS supports following without an account and unavailable accounts cannot supply recommendations", () => {
  const connections = { x: { state: "error", status: "connected" }, reddit: { state: "connecting" } };
  assert.deepEqual(resolveCollectionSources("following", connections, true), ["rss"]);
  assert.deepEqual(resolveCollectionSources("recommended", connections, true), []);
  assert.deepEqual(resolveCollectionSources("search", {}, false), ["news", "hackernews"]);
  assert.deepEqual(resolveCollectionSources("following", {}, false), []);
});

test("valid news routes restore channel, topic and an encoded local filter", () => {
  const route = { page: "feed", view: "bookmarked", topic: "crypto", settingsTab: "accounts", q: "黄金 & BTC/USDT + Fed? #宏观", source: "reddit", sort: "relevance" };
  const hash = workspaceHash(route);
  assert.ok(hash.startsWith("#/news?channel=bookmarked&topic=crypto&q="));
  assert.ok(!hash.includes("#宏观"));
  assert.deepEqual(parseWorkspaceHash(hash), route);
});

test("settings and market deep links restore their own workspace without leaking news filters", () => {
  assert.equal(workspaceHash({ page: "settings", settingsTab: "translation", q: "BTC" }), "#/settings?tab=translation");
  assert.equal(parseWorkspaceHash("#/settings?tab=health&channel=following&q=BTC").settingsTab, "health");
  assert.equal(parseWorkspaceHash("#/settings?tab=health&channel=following&q=BTC").q, "");
  assert.equal(workspaceHash({ page: "market", view: "following", q: "BTC" }), "#/markets");
  assert.equal(parseWorkspaceHash("#/markets").page, "market");
});

test("invalid routes and enums safely fall back; unknown parameters are removed from generated links", () => {
  const defaults = { page: "feed", view: "search", topic: "all", settingsTab: "accounts", q: "", source: "all", sort: "latest" };
  assert.deepEqual(parseWorkspaceHash("#https://example.org/settings?tab=translation"), defaults);
  assert.deepEqual(parseWorkspaceHash("#/unknown?channel=following"), defaults);
  assert.deepEqual(parseWorkspaceHash("#/news?channel=invalid&topic=invalid&source=invalid&sort=invalid&tab=translation"), defaults);
  assert.equal(workspaceHash(parseWorkspaceHash("#/news?unexpected=secret")), "#/news");
  assert.equal(parseWorkspaceHash("#/settings?tab=unknown").settingsTab, "accounts");
  assert.equal(workspaceHash({ page: "unknown", topic: "invalid", settingsTab: "unknown" }), "#/news");
});

test("route filters retain literal percent and plus characters and respect the query limit", () => {
  const q = "growth 5% + jobs & inflation";
  assert.equal(parseWorkspaceHash(workspaceHash({ q })).q, q);
  assert.equal(parseWorkspaceHash(workspaceHash({ q: "a".repeat(700) })).q.length, 500);
  assert.equal(parseWorkspaceHash("#/news?q=" + "b".repeat(700)).q.length, 500);
});

test("the Chinese content preference restores under either interface language", () => {
  for (const locale of ["en", "zh"]) {
    setLocale(locale);
    assert.equal(initialReadingChinese("zh"), true);
    assert.equal(initialReadingChinese("original"), false);
    assert.equal(initialReadingChinese(null), false);
    assert.equal(initialReadingChinese("invalid"), false);
  }
  setLocale("en");
});

test("startup canonicalization replaces an empty URL rather than adding a Back step", () => {
  assert.equal(workspaceHistoryMode("", parseWorkspaceHash(""), true), "replace");
});

test("query edits still coalesce after returning from a non-default settings section", () => {
  const next = { ...parseWorkspaceHash("#/news?q=Bitcoin"), q: "Bitcoin ETF", settingsTab: "translation" };
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", next, false), "replace");
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", { ...next, settingsTab: "preferences" }, false), "replace");
});

test("channel, filter context and workspace changes create useful navigation history", () => {
  const next = parseWorkspaceHash("#/news?q=Bitcoin");
  assert.equal(workspaceHistoryMode("#/news", next, false), "push");
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", { ...next, view: "following" }, false), "push");
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", { ...next, source: "reddit" }, false), "push");
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", { ...next, q: "" }, false), "push");
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", { ...next, page: "settings", settingsTab: "translation" }, false), "push");
});

test("an already matching hash does not alter history, even with retained settings state", () => {
  const next = { ...parseWorkspaceHash("#/news?q=Bitcoin"), settingsTab: "translation" };
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", next, false), null);
  assert.equal(workspaceHistoryMode("#/news?q=Bitcoin", next, true), null);
});
