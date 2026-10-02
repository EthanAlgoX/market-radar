import { localizeMessage, localeCode, t } from "../i18n.ts";
import type { Market, MarketCandle, MarketJob, MarketQuality, MarketRule, MarketSignal } from "./types";

// Getters resolve labels at render time so a locale change never leaves cached labels behind.
export const MARKET_NAMES: Record<Market, string> = {
  get crypto() { return t("加密货币", "Crypto"); },
  get us() { return t("美股", "US equities"); },
  get hk() { return t("港股", "Hong Kong"); },
  get cn() { return t("A 股", "China A shares"); },
};
export const PROVIDER_NAMES: Record<string, string> = {
  binance: "Binance", yahoo: "Yahoo Finance", get eastmoney() { return t("东方财富", "Eastmoney"); },
};
export function instrumentName(name?: string, fallback = ""): string {
  const names: Record<string, string> = {
    "比特币": "Bitcoin", "以太坊": "Ethereum", "苹果": "Apple", "英伟达": "NVIDIA", "微软": "Microsoft",
    "腾讯": "Tencent", "阿里巴巴": "Alibaba", "贵州茅台": "Kweichow Moutai", "平安银行": "Ping An Bank",
  };
  return name ? t(name, names[name] || name) : fallback;
}
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
  return new Intl.NumberFormat(localeCode(), {
    maximumFractionDigits: Math.abs(value) > 0 && Math.abs(value) < 0.01 ? 8 : digits,
  }).format(value);
}

export function formatTime(value?: string | null, timezone?: string): string {
  if (!value) return t("尚无记录", "No record yet");
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return t("时间未知", "Unknown time");
  try {
    return new Intl.DateTimeFormat(localeCode(), {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      hour12: false, ...(timezone ? { timeZone: timezone } : {}),
    }).format(date);
  } catch { return date.toLocaleString(localeCode(), { hour12: false }); }
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
  if (quality.open_rows > 0) notes.push(t(`${quality.open_rows} 根 K 线尚未收盘，正式信号仅使用已收盘数据。`, `${quality.open_rows} candles are still open. Confirmed signals use closed candles only.`));
  if (quality.gaps > 0) notes.push(t(`窗口中有 ${quality.gaps} 处时间缺口，均线与信号需结合数据连续性核对。`, `The window contains ${quality.gaps} time gaps. Check data continuity when reviewing moving averages and signals.`));
  if (quality.missing_rows > 0) notes.push(t(`${quality.missing_rows} 根 K 线的价格或成交量数据缺失，相关规则暂停计算。`, `${quality.missing_rows} candles have missing price or volume data. Affected rules pause calculation.`));
  const labels: Record<string, string> = {
    stale: t("最新行情可能有延迟。", "The latest market data may be delayed."), stale_data: t("最新行情可能有延迟。", "The latest market data may be delayed."),
    missing_volume: t("部分成交量未提供，成交量规则暂不适用。", "Some volume data is unavailable. Volume rules cannot apply to those rows."),
    volume_missing: t("部分成交量未提供，成交量规则暂不适用。", "Some volume data is unavailable. Volume rules cannot apply to those rows."),
    calendar_unverified: t("交易日连续性尚未核验。", "Trading-session continuity has not been verified."),
    unverified_calendar: t("交易日连续性尚未核验。", "Trading-session continuity has not been verified."),
    invalid_ohlc: t("部分价格数据未通过校验。", "Some price data failed validation."),
    missing_ohlcv: t("部分价格或成交量数据缺失，相关规则暂停计算。", "Some price or volume data is missing. Affected rules pause calculation."),
    calendar_unconfirmed: t("交易日连续性尚未核验。", "Trading-session continuity has not been verified."),
    corporate_action: t("窗口包含除权、拆股等公司行动，相关价格变化需要核对。", "The window contains corporate actions such as dividends or splits. Review the related price changes."),
    large_price_change_unverified: t("部分价格变化较大，来源口径需要进一步核对。", "Some price changes are unusually large. Verify the source's pricing conventions."),
    invalid_interval: t("部分 K 线周期与所选周期不一致。", "Some candle intervals do not match the selected interval."),
    non_trading_session: t("来源包含非正常交易时段记录。", "The source includes records outside regular trading sessions."),
    partial: t("本次仅取得部分数据。", "Only part of the requested data was retrieved."), truncated: t("本次数据范围受到来源限制。", "The source limits the available data window."),
  };
  for (const flag of quality.flags || []) {
    if (/open|unclosed|missing_rows|gap/.test(flag)) continue;
    if (flag === "missing_ohlcv" && quality.missing_rows > 0) continue;
    const text = labels[flag] || (/[㐀-鿿]/.test(flag) ? localizeMessage(flag) : t("来源数据需要进一步核对。", "Source data needs further verification."));
    if (!notes.includes(text)) notes.push(text);
  }
  if (quality.status === "warning" && !notes.length) notes.push(t("来源数据需要进一步核对。", "Source data needs further verification."));
  return notes;
}

export function statusLabel(status?: string): string {
  const labels: Record<string, string> = {
    idle: t("待刷新", "Not refreshed"), empty: t("暂无数据", "No data"), queued: t("等待刷新", "Queued"), pending: t("等待刷新", "Pending"),
    running: t("刷新中", "Refreshing"), completed: t("已更新", "Updated"), available: t("可用", "Available"), ready: t("可用", "Ready"),
    ok: t("已核验", "Verified"), warning: t("需要核对", "Review needed"), partial: t("部分更新", "Partial update"), failed: t("刷新失败", "Refresh failed"),
    error: t("获取失败", "Fetch failed"), skipped: t("已跳过", "Skipped"), insufficient_history: t("历史不足", "Insufficient history"),
    waiting_close: t("等待收盘", "Waiting for close"), quality_blocked: t("暂停计算", "Calculation paused"), dependency_unavailable: t("计算暂不可用", "Calculation unavailable"), stale: t("历史记录", "Historical"),
  };
  return labels[status || ""] || t("待核对", "Unverified");
}

export function volumeLabel(value?: string, symbol?: string): string {
  if (value === "base_asset") return t(`${symbol?.split("/")[0] || "基础资产"}（基础资产）`, `${symbol?.split("/")[0] || "Base asset"} (base asset)`);
  if (value === "shares") return t("股", "shares");
  if (value === "lots_100_shares") return t("手（100 股）", "lots (100 shares)");
  return value && /[㐀-鿿]/.test(value) ? localizeMessage(value) : t("来源未说明单位", "Unit not specified by source");
}

export function adjustmentLabel(value?: string): string {
  const labels: Record<string, string> = {
    none: t("不复权", "Unadjusted"), unadjusted: t("不复权", "Unadjusted"), raw: t("不复权", "Unadjusted"),
    qfq: t("前复权", "Forward adjusted"), forward: t("前复权", "Forward adjusted"), hfq: t("后复权", "Backward adjusted"), backward: t("后复权", "Backward adjusted"),
    adjusted: t("复权价格", "Adjusted prices"), split: t("拆股调整", "Split adjusted"), split_adjusted: t("拆股调整", "Split adjusted"),
    auto_adjust: t("自动复权", "Automatically adjusted"), not_applicable: t("不适用", "Not applicable"), "": t("来源未说明", "Not specified by source"),
  };
  return labels[value || ""] || (/[㐀-鿿]/.test(value || "") ? localizeMessage(value!) : t("来源调整口径待核对", "Source adjustment needs verification"));
}

const EVIDENCE_LABELS: Record<string, [string, string]> = {
  close: ["收盘价", "Close"], reference_high: ["此前区间最高价", "Previous range high"], reference_low: ["此前区间最低价", "Previous range low"],
  ma20: ["20期均线", "20-period SMA"], ma60: ["60期均线", "60-period SMA"], previous_ma20: ["上一期20期均线", "Previous 20-period SMA"], previous_ma60: ["上一期60期均线", "Previous 60-period SMA"],
  volume: ["本期成交量", "Current volume"], mean_volume20: ["此前20期平均量", "Previous 20-period average volume"], volume_ratio20: ["成交量倍数", "Volume ratio"],
  rsi14: ["14期 RSI", "14-period RSI"], previous_rsi14: ["上一期 RSI", "Previous RSI"], threshold: ["触发阈值", "Trigger threshold"],
};
export function evidenceRows(signal: MarketSignal) {
  return Object.entries(signal.evidence || {}).map(([key, value]) => ({
    key, label: EVIDENCE_LABELS[key] ? t(...EVIDENCE_LABELS[key]) : t("观测值", "Observed value"),
    value: finite(value) ? `${formatNumber(value)}${key === "volume_ratio20" ? t(" 倍", "×") : ""}` : t("未提供", "Not provided"),
  }));
}

export function ruleName(rule: Pick<MarketRule, "id" | "name"> | Pick<MarketSignal, "rule_id" | "rule_name">): string {
  const id = "rule_id" in rule ? rule.rule_id : rule.id;
  const original = "rule_name" in rule ? rule.rule_name : rule.name;
  const names: Record<string, string> = { breakout20: "20-candle range breakout", sma20_60: "MA20 / MA60 crossover", volume2x: "Volume expansion", rsi14_cross: "RSI14 threshold crossover" };
  return t(original, names[id] || localizeMessage(original));
}
export function ruleDescription(rule: MarketRule): string {
  const descriptions: Record<string, string> = {
    breakout20: "A closed candle's close exceeds the highest high of the previous 20 candles.",
    sma20_60: "The 20-period simple moving average crosses above or below the 60-period average.",
    volume2x: "Volume reaches at least twice the average volume of the previous 20 candles.",
    rsi14_cross: "RSI14 crosses above or below the 30 or 70 threshold.",
  };
  return t(rule.description, descriptions[rule.id] || localizeMessage(rule.description));
}
export function signalSummary(signal: MarketSignal): string {
  const summaries: Record<string, string> = {
    breakout20: "The closed price exceeded the previous 20-candle high.",
    sma20_60: signal.direction === "up" ? "MA20 crossed above MA60." : "MA20 crossed below MA60.",
    volume2x: "Volume reached at least twice the previous 20-candle average.",
    rsi14_cross: `RSI14 crossed ${signal.direction === "up" ? "above" : "below"} ${formatNumber(signal.evidence.threshold ?? signal.parameters.threshold)}.`,
  };
  return t(signal.summary, summaries[signal.rule_id] || localizeMessage(signal.summary));
}

export function jobSummary(job: MarketJob): string {
  if (isRunning(job)) {
    const done = job.progress.filter((p) => !["pending", "running"].includes(p.status)).length;
    return t(`${job.status === "queued" ? "准备刷新" : "正在刷新"} · ${done}/${job.progress.length} 个标的`, `${job.status === "queued" ? "Queued for refresh" : "Refreshing"} · ${done}/${job.progress.length} instruments`);
  }
  if (job.status === "failed") return t("本次刷新失败，已有行情仍保留。", "This refresh failed. Previously saved market data is retained.");
  if (job.status === "partial") return t(`部分刷新完成 · 新收录 ${job.added} 根，更新 ${job.updated} 根 K 线`, `Partial refresh · ${job.added} candles added, ${job.updated} updated`);
  return t(`刷新完成 · 新收录 ${job.added} 根，更新 ${job.updated} 根 K 线`, `Refresh complete · ${job.added} candles added, ${job.updated} updated`);
}
