import type { Channel, Connection, SourceKey, View } from "./types.ts";

export type WorkspacePage = "feed" | "market" | "settings";
export type WorkspaceTopic = "all" | "macro" | "crypto" | "us" | "hk" | "cn" | "finance" | "gold";
export type WorkspaceSettingsTab = "accounts" | "preferences" | "feeds" | "translation" | "health";
export interface WorkspaceRoute {
  page: WorkspacePage;
  view: View;
  topic: WorkspaceTopic;
  settingsTab: WorkspaceSettingsTab;
  q: string;
  source: SourceKey | "all";
  sort: "latest" | "relevance";
}

const DEFAULT_ROUTE: WorkspaceRoute = {
  page: "feed", view: "search", topic: "all", settingsTab: "accounts", q: "", source: "all", sort: "latest",
};
const VIEWS: readonly View[] = ["search", "following", "recommended", "bookmarked"];
const TOPICS: readonly WorkspaceTopic[] = ["all", "macro", "crypto", "us", "hk", "cn", "finance", "gold"];
const SETTINGS_TABS: readonly WorkspaceSettingsTab[] = ["accounts", "preferences", "feeds", "translation", "health"];
const SOURCES: readonly WorkspaceRoute["source"][] = ["all", "news", "rss", "x", "reddit", "hackernews"];
const SORTS: readonly WorkspaceRoute["sort"][] = ["latest", "relevance"];

function validValue<T extends string>(value: string | null | undefined, values: readonly T[], fallback: T): T {
  return values.includes(value as T) ? value as T : fallback;
}

/** Collection uses channel capabilities; filtering the local library cannot change them. */
export function resolveCollectionSources(
  channel: Channel,
  connections: Partial<Record<"x" | "reddit", Pick<Connection, "state">>>,
  rssEnabled: boolean,
): SourceKey[] {
  const personal: SourceKey[] = [];
  if (connections.x?.state === "connected") personal.push("x");
  if (connections.reddit?.state === "connected") personal.push("reddit");
  const rss: SourceKey[] = rssEnabled ? ["rss"] : [];
  if (channel === "search") return ["news", "hackernews", ...rss, ...personal];
  if (channel === "following") return [...personal, ...rss];
  return personal;
}

/** Restore only recognized routes and parameters, without interpreting URLs or HTML. */
export function parseWorkspaceHash(hash: string): WorkspaceRoute {
  const route = { ...DEFAULT_ROUTE };
  const fragment = hash.startsWith("#") ? hash.slice(1) : hash;
  const separator = fragment.indexOf("?");
  const path = separator < 0 ? fragment : fragment.slice(0, separator);
  const query = separator < 0 ? "" : fragment.slice(separator + 1);
  if (path === "/markets") route.page = "market";
  else if (path === "/settings") route.page = "settings";
  else if (path !== "/news") return route;
  const parameters = new URLSearchParams(query);
  if (route.page === "feed") {
    route.view = validValue(parameters.get("channel"), VIEWS, DEFAULT_ROUTE.view);
    route.topic = validValue(parameters.get("topic"), TOPICS, DEFAULT_ROUTE.topic);
    route.q = (parameters.get("q") || "").slice(0, 500);
    route.source = validValue(parameters.get("source"), SOURCES, DEFAULT_ROUTE.source);
    route.sort = validValue(parameters.get("sort"), SORTS, DEFAULT_ROUTE.sort);
  } else if (route.page === "settings") {
    route.settingsTab = validValue(parameters.get("tab"), SETTINGS_TABS, DEFAULT_ROUTE.settingsTab);
  }
  return route;
}

/** Create a canonical, encoded deep link for the currently visible workspace. */
export function workspaceHash(state: Partial<WorkspaceRoute>): string {
  const page = validValue(state.page, ["feed", "market", "settings"] as const, DEFAULT_ROUTE.page);
  if (page === "market") return "#/markets";
  const parameters = new URLSearchParams();
  if (page === "settings") {
    const tab = validValue(state.settingsTab, SETTINGS_TABS, DEFAULT_ROUTE.settingsTab);
    if (tab !== DEFAULT_ROUTE.settingsTab) parameters.set("tab", tab);
  } else {
    const view = validValue(state.view, VIEWS, DEFAULT_ROUTE.view);
    const topic = validValue(state.topic, TOPICS, DEFAULT_ROUTE.topic);
    const source = validValue(state.source, SOURCES, DEFAULT_ROUTE.source);
    const sort = validValue(state.sort, SORTS, DEFAULT_ROUTE.sort);
    if (view !== DEFAULT_ROUTE.view) parameters.set("channel", view);
    if (topic !== DEFAULT_ROUTE.topic) parameters.set("topic", topic);
    if (state.q) parameters.set("q", state.q.slice(0, 500));
    if (source !== DEFAULT_ROUTE.source) parameters.set("source", source);
    if (sort !== DEFAULT_ROUTE.sort) parameters.set("sort", sort);
  }
  const query = parameters.toString();
  return `#/${page === "settings" ? "settings" : "news"}${query ? `?${query}` : ""}`;
}

/** Canonicalize startup without adding history; coalesce edits to the same local query. */
export function workspaceHistoryMode(
  currentHash: string,
  next: WorkspaceRoute,
  initial: boolean,
): "replace" | "push" | null {
  if (currentHash === workspaceHash(next)) return null;
  if (initial) return "replace";
  const current = parseWorkspaceHash(currentHash);
  const sameFeed = current.page === "feed" && next.page === "feed" &&
    current.view === next.view && current.topic === next.topic &&
    current.source === next.source && current.sort === next.sort;
  // Settings state is retained in memory but is not a parameter of a news route.
  if (sameFeed && current.q && next.q) return "replace";
  return "push";
}

/** Content reading preference is independent of the interface language. */
export function initialReadingChinese(stored: string | null | undefined): boolean {
  return stored === "zh";
}
