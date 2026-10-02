import type { Market, MarketCandle, MarketJob, MarketQuality, MarketSignal } from "./types";

export const MARKET_NAMES: Record<Market, string> = {
  crypto: "加密货币", us: "美股", hk: "港股", cn: "A 股",
};
export const PROVIDER_NAMES: Record<string, string> = {
  binance: "Binance", yahoo: "Yahoo Finance", eastmoney: "东方财富",
};
export const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
export const isRunning = (job?: MarketJob | null) =>
  job?.status === "queued" || job?.status === "running";
export const messageOf = (error: unknown) =>
  error instanceof Error ? error.message : "暂时无法完成，请重试。";

export function webUrl(value?: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch { return undefined; }
}

export function formatNumber(value: unknown, digits = 4): string {
  if (!finite(value)) return "—";
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: Math.abs(value) > 0 && Math.abs(value) < 0.01 ? 8 : digits,
  }).format(value);
}

export function formatTime(value?: string | null, timezone?: string): string {
  if (!value) return "尚无记录";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "时间未知";
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      hour12: false, ...(timezone ? { timeZone: timezone } : {}),
    }).format(date);
  } catch { return date.toLocaleString("zh-CN", { hour12: false }); }
}

export function latestCandle(candles: MarketCandle[]): MarketCandle | undefined {
  return candles.filter((c) => finite(c.open) && finite(c.high) && finite(c.low) && finite(c.close)
    && c.open > 0 && c.close > 0 && c.low > 0 && c.high > 0 && c.low <= c.high
    && Number.isFinite(Date.parse(c.time)))
    .reduce<MarketCandle | undefined>((latest, candle) =>
      !latest || Date.parse(candle.time) > Date.parse(latest.time) ? candle : latest, undefined);
}

export function qualityNotes(quality?: MarketQuality): string[] {
  if (!quality) return [];
  const notes: string[] = [];
  if (quality.open_rows > 0) notes.push(`${quality.open_rows} 根 K 线尚未收盘，正式信号仅使用已收盘数据。`);
  if (quality.gaps > 0) notes.push(`窗口中有 ${quality.gaps} 处时间缺口，均线与信号需结合数据连续性核对。`);
  if (quality.missing_rows > 0) notes.push(`${quality.missing_rows} 根 K 线的价格或成交量数据缺失，相关规则暂停计算。`);
  const labels: Record<string, string> = {
    stale: "最新行情可能有延迟。", stale_data: "最新行情可能有延迟。",
    missing_volume: "部分成交量未提供，成交量规则暂不适用。",
    volume_missing: "部分成交量未提供，成交量规则暂不适用。",
    calendar_unverified: "交易日连续性尚未核验。",
    unverified_calendar: "交易日连续性尚未核验。",
    invalid_ohlc: "部分价格数据未通过校验。",
    missing_ohlcv: "部分价格或成交量数据缺失，相关规则暂停计算。",
    calendar_unconfirmed: "交易日连续性尚未核验。",
    corporate_action: "窗口包含除权、拆股等公司行动，相关价格变化需要核对。",
    large_price_change_unverified: "部分价格变化较大，来源口径需要进一步核对。",
    invalid_interval: "部分 K 线周期与所选周期不一致。",
    non_trading_session: "来源包含非正常交易时段记录。",
    partial: "本次仅取得部分数据。", truncated: "本次数据范围受到来源限制。",
  };
  for (const flag of quality.flags || []) {
    if (/open|unclosed|missing_rows|gap/.test(flag)) continue;
    if (flag === "missing_ohlcv" && quality.missing_rows > 0) continue;
    const text = labels[flag] || (/[\u3400-\u9fff]/.test(flag) ? flag : "来源数据需要进一步核对。");
    if (!notes.includes(text)) notes.push(text);
  }
  if (quality.status === "warning" && !notes.length) notes.push("来源数据需要进一步核对。");
  return notes;
}

export function statusLabel(status?: string): string {
  const labels: Record<string, string> = {
    idle: "待刷新", empty: "暂无数据", queued: "等待刷新", pending: "等待刷新",
    running: "刷新中", completed: "已更新", available: "可用", ready: "可用",
    ok: "已核验", warning: "需要核对", partial: "部分更新", failed: "刷新失败",
    error: "获取失败", skipped: "已跳过", insufficient_history: "历史不足",
    waiting_close: "等待收盘", quality_blocked: "暂停计算", dependency_unavailable: "计算暂不可用", stale: "历史记录",
  };
  return labels[status || ""] || "待核对";
}

export function volumeLabel(value?: string, symbol?: string): string {
  if (value === "base_asset") return `${symbol?.split("/")[0] || "基础资产"}（基础资产）`;
  if (value === "shares") return "股";
  if (value === "lots_100_shares") return "手（100 股）";
  return value && /[\u3400-\u9fff]/.test(value) ? value : "来源未说明单位";
}

export function adjustmentLabel(value?: string): string {
  const labels: Record<string, string> = {
    none: "不复权", unadjusted: "不复权", raw: "不复权",
    qfq: "前复权", forward: "前复权", hfq: "后复权", backward: "后复权",
    adjusted: "复权价格", split: "拆股调整", split_adjusted: "拆股调整",
    auto_adjust: "自动复权", not_applicable: "不适用", "": "来源未说明",
  };
  return labels[value || ""] || (/[\u3400-\u9fff]/.test(value || "") ? value! : "来源调整口径待核对");
}

export const EVIDENCE_LABELS: Record<string, string> = {
  close: "收盘价", reference_high: "此前区间最高价", reference_low: "此前区间最低价",
  ma20: "20期均线", ma60: "60期均线", previous_ma20: "上一期20期均线", previous_ma60: "上一期60期均线",
  volume: "本期成交量", mean_volume20: "此前20期平均量", volume_ratio20: "成交量倍数",
  rsi14: "14期 RSI", previous_rsi14: "上一期 RSI", threshold: "触发阈值",
};
export function evidenceRows(signal: MarketSignal) {
  return Object.entries(signal.evidence || {}).map(([key, value]) => ({
    key, label: EVIDENCE_LABELS[key] || "观测值",
    value: finite(value) ? `${formatNumber(value)}${key === "volume_ratio20" ? " 倍" : ""}` : "未提供",
  }));
}

export function jobSummary(job: MarketJob): string {
  if (isRunning(job)) {
    const done = job.progress.filter((p) => !["pending", "running"].includes(p.status)).length;
    return `${job.status === "queued" ? "准备刷新" : "正在刷新"} · ${done}/${job.progress.length} 个标的`;
  }
  if (job.status === "failed") return "本次刷新失败，已有行情仍保留。";
  if (job.status === "partial") return `部分刷新完成 · 新收录 ${job.added} 根，更新 ${job.updated} 根 K 线`;
  return `刷新完成 · 新收录 ${job.added} 根，更新 ${job.updated} 根 K 线`;
}
