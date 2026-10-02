import type { Post } from "../types";

export type Market = "crypto" | "us" | "hk" | "cn";
export type MarketJobStatus = "queued" | "running" | "completed" | "partial" | "failed";

export interface MarketQuality {
  status: "ok" | "warning" | "empty";
  flags: string[];
  missing_rows: number;
  open_rows: number;
  gaps: number;
  calendar_verified: boolean;
}

export interface MarketInstrument {
  id: string;
  market: Market;
  symbol: string;
  name?: string;
  news_query?: string;
  source_url?: string;
  provider: string;
  interval: "1h" | "1d";
  currency: string;
  timezone: string;
  volume_unit: string;
  adjustment: string;
  session: string;
  status: string;
  message?: string;
  count: number;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  last_bar_at?: string | null;
  quality: MarketQuality;
}

export interface MarketCandle {
  time: string;
  end_time: string;
  trading_date?: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  closed: boolean;
  quality: string[];
  provider: string;
  symbol?: string;
  interval?: string;
  currency?: string;
  timezone?: string;
  volume_unit: string;
  adjustment: string;
  session?: string;
  received_at: string;
  source_hash?: string;
  revision: number;
}

export interface MarketIndicator {
  time: string;
  ma20: number | null;
  ma60: number | null;
  rsi14: number | null;
  volume_ratio20: number | null;
}
export type MarketIndicators = MarketIndicator[];

export interface MarketSignal {
  id: string;
  rule_id: string;
  rule_name: string;
  rule_version: string;
  direction: string;
  symbol: string;
  provider: string;
  interval: string;
  bar_time: string;
  bar_start: string;
  bar_close: string;
  confirmed_at: string;
  emitted_at: string;
  parameters: Record<string, number | number[] | string | boolean | null>;
  evidence: Record<string, number | null>;
  source_hash: string;
  source_url: string;
  data_revision: number;
  summary: string;
  is_stale?: boolean;
  historical?: boolean;
  pending_revalidation?: boolean;
}

export interface MarketRule {
  id: string;
  name: string;
  description: string;
  parameters: Record<string, number | number[] | string | boolean | null>;
  min_bars: number;
  enabled_by_default: boolean;
}

export interface MarketCoverage {
  count: number;
  first_bar_at?: string | null;
  last_bar_at?: string | null;
  last_closed_bar_at?: string | null;
  received_at?: string | null;
  interval: string;
  window: number;
  history_complete: boolean;
  stale?: boolean;
  freshness_message?: string;
  freshness_status?: string;
  expected_last_closed_date?: string | null;
}

export interface SignalAnalysis {
  status: string;
  message: string;
  warmup?: Record<string, unknown> | number;
  latest_bar_time?: string | null;
  latest?: (MarketIndicator & { close?: number | null }) | null;
}

export interface MarketSnapshot {
  instrument: MarketInstrument;
  candles: MarketCandle[];
  quality: MarketQuality;
  signals: MarketSignal[];
  indicators: MarketIndicators;
  coverage: MarketCoverage;
  status: string;
  message?: string;
  signal_analysis?: SignalAnalysis;
  source_url?: string;
  related_news?: Post[];
}

export interface MarketProvider {
  id: string;
  name: string;
  markets: string[];
  intervals: string[];
  status: string;
  message?: string;
  delay_note?: string;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
}

export interface MarketPreset {
  market: Market;
  symbol: string;
  name: string;
}

export interface MarketJob {
  id: string;
  status: MarketJobStatus;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  request?: { ids: string[] };
  progress: {
    instrument_id: string;
    symbol: string;
    status: string;
    count?: number;
    new?: number;
    updated?: number;
    message?: string;
  }[];
  errors: { instrument_id: string; symbol: string; provider: string; message: string }[];
  added: number;
  updated: number;
  total: number;
  recovered?: boolean;
}

export interface MarketOverview {
  watchlist: MarketInstrument[];
  providers: MarketProvider[];
  rules: MarketRule[];
  presets: MarketPreset[];
  limits: { max_instruments: number; window: number };
  active_job: MarketJob | null;
}
