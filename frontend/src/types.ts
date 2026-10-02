export type Channel = "search" | "following" | "recommended";
export type View = "search" | "following" | "recommended" | "bookmarked";
export type SourceKey = "x" | "reddit" | "news" | "rss" | "hackernews";
export interface Observation {
  source?: SourceKey | string;
  source_name?: string;
  author?: string;
  external_id?: string;
  url?: string;
  channel?: Channel;
  channels?: Channel[];
  query?: string;
  queries?: string[];
  provider_query?: string;
  collected_at?: string;
  observed_at?: string;
}
export interface Post {
  id: string;
  external_id: string;
  source: SourceKey;
  source_name: string;
  author: string;
  title: string;
  content: string;
  url: string;
  external_url?: string | null;
  canonical_url?: string | null;
  content_kind?: string;
  observations?: Observation[];
  published_at: string | null;
  collected_at: string;
  topics: string[];
  matched_keywords: string[];
  channels: Channel[];
  summary: string;
  summary_kind: string;
  language: string;
  score: number;
  metrics: Record<string, number>;
  bookmarked: boolean;
  is_read: boolean;
  translation?: {
    title: string;
    content: string;
    summary: string;
    language: "zh";
    model: string;
    translated_at: string;
    source_hash: string;
  } | null;
}
export interface TranslationStatus {
  configured: boolean;
  model: string;
  message: string;
}
export interface TranslationJob {
  id: string;
  status: "running" | "completed" | "failed";
  total: number;
  completed: number;
  failed: number;
  errors: { id: string; message: string }[];
  items?: Post[];
}
export interface Connection {
  state: string;
  status?: string;
  username?: string;
  message?: string;
  configured?: boolean;
  client_id_configured?: boolean;
}
export interface Settings {
  keywords: string[];
  authors: { x: string[]; reddit: string[] };
  rss_feeds: FeedSource[];
  rsshub_url: string;
  auto_refresh_minutes: number;
  llm: {
    enabled: boolean;
    base_url: string;
    model: string;
    api_key?: { configured: boolean } | string;
    configured?: boolean;
  };
}
export interface SourceState {
  source: SourceKey;
  name: string;
  status: string;
  message?: string;
  count: number;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
}
export interface FeedSource {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  category?: string;
  requires?: string[];
  description?: string;
}
export interface SourcePresets {
  feeds: FeedSource[];
  rsshub_routes: {
    id?: string;
    name: string;
    path?: string;
    route?: string;
    url?: string;
    description?: string;
    requires?: string[];
  }[];
}
export interface DiscussionComment {
  external_id: string;
  parent_id?: string | null;
  author: string;
  content: string;
  url: string;
  published_at: string | null;
  score?: number;
  depth?: number;
}
export interface Discussion {
  items: DiscussionComment[];
  status: string;
  message?: string;
}
export interface Overview {
  topics: { id: string; name: string; query: string; count: number }[];
  keywords: string[];
  counts: {
    total: number;
    unread: number;
    bookmarked: number;
    search: number;
    following: number;
    recommended: number;
  };
  sources: SourceState[];
}
export interface Job {
  id: string;
  status: string;
  added: number;
  total: number;
  started_at?: string;
  finished_at?: string;
  progress: {
    source: string;
    status: string;
    count?: number;
    new?: number;
    added?: number;
    updated?: number;
    duplicates?: number;
    retries?: number;
    query?: string;
    queries?: string[];
    coverage?: string | number | Record<string, unknown>;
    truncated?: boolean;
    message?: string;
  }[];
  errors: { source: string; message: string }[];
}
