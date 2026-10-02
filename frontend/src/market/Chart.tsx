import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";
import { localeCode, t, useLocale } from "../i18n";
import type { MarketCandle, MarketIndicators, MarketSignal } from "./types";

export interface ChartProps {
  candles: MarketCandle[];
  signals: MarketSignal[];
  indicators: MarketIndicators;
  currency?: string;
  volumeUnit?: string;
}

type ValidCandle = {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  source: MarketCandle;
};
type TimedCandle = { time: UTCTimestamp; source: MarketCandle };

type Palette = {
  surface: string;
  ink: string;
  muted: string;
  line: string;
  blue: string;
  up: string;
  down: string;
  ma60: string;
};

type ChartInstance = {
  chart: IChartApi;
  price: ISeriesApi<"Candlestick">;
  volume: ISeriesApi<"Histogram">;
  ma20: ISeriesApi<"Line">;
  ma60: ISeriesApi<"Line">;
  markers: ISeriesMarkersPluginApi<Time>;
  dataset: string | null;
};


function utcTime(value: string): UTCTimestamp | null {
  // Reject ambiguous local timestamps instead of shifting market bars by the viewer's timezone.
  if (!/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return null;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? Math.floor(milliseconds / 1000) as UTCTimestamp : null;
}

function finite(value: number | null): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function candleTimeline(candles: MarketCandle[]): TimedCandle[] {
  const unique = new Map<UTCTimestamp, MarketCandle>();
  for (const candle of candles) {
    const time = utcTime(candle.time);
    if (time === null) continue;
    const previous = unique.get(time);
    if (!previous || candle.revision >= previous.revision) unique.set(time, candle);
  }
  return [...unique].map(([time, source]) => ({ time, source })).sort((left, right) => left.time - right.time);
}

function validCandles(timeline: TimedCandle[]): ValidCandle[] {
  const result: ValidCandle[] = [];
  for (const { time, source: candle } of timeline) {
    const { open, high, low, close } = candle;
    if (!finite(open) || !finite(high) || !finite(low) || !finite(close)) continue;
    // Auction/session conventions can put open or close outside the reported
    // intraday high/low. Preserve those finite source prices rather than hiding them.
    if (open <= 0 || close <= 0 || low <= 0 || high <= 0 || low > high) continue;
    result.push({ time, open, high, low, close, source: candle });
  }
  return result;
}

function readPalette(container: HTMLElement): Palette {
  const style = getComputedStyle(container);
  const token = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  const dark = Boolean(container.closest('[data-theme="dark"]'));
  return {
    surface: token("--surface", "#fff"), ink: token("--ink", "#263248"),
    muted: token("--muted", "#627087"), line: token("--line", "#e6eaf0"),
    blue: token("--blue", "#2e5dde"), up: token("--success", "#27845e"),
    down: token("--error", "#bc4948"), ma60: dark ? "#e3ba70" : "#9b681a",
  };
}

function dateLabel(time: UTCTimestamp): string {
  return `${new Intl.DateTimeFormat(localeCode(), { timeZone: "UTC", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(time * 1000))} UTC`;
}

function candleStatus(candle: MarketCandle): string {
  return candle.closed ? t("已收盘", "Closed") : t("盘中 · 未收盘", "Intraday · Open");
}

export default function Chart({ candles, signals, indicators, currency, volumeUnit }: ChartProps) {
  const { locale } = useLocale();
  const priceFormatter = useMemo(() => new Intl.NumberFormat(localeCode(), { maximumSignificantDigits: 9 }), [locale]);
  const volumeFormatter = useMemo(() => new Intl.NumberFormat(localeCode(), { maximumSignificantDigits: 6 }), [locale]);
  const containerRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<ChartInstance | null>(null);
  const summaryId = useId();
  const timeline = useMemo(() => candleTimeline(candles), [candles]);
  const rows = useMemo(() => validCandles(timeline), [timeline]);
  const [palette, setPalette] = useState<Palette | null>(null);
  const [hoveredTime, setHoveredTime] = useState<UTCTimestamp | null>(null);
  const [chartError, setChartError] = useState(false);
  const [showSignalMarkers, setShowSignalMarkers] = useState(false);
  const hasRows = rows.length > 0;
  const latest = rows.at(-1);
  const selected = rows.find(row => row.time === hoveredTime) ?? latest;
  const hasOpen = rows.some(row => !row.source.closed);
  const missingVolume = timeline.filter(row => !finite(row.source.volume) || row.source.volume < 0).length;
  const priceUnit = currency || latest?.source.currency || "";
  const quantityUnit = volumeUnit || latest?.source.volume_unit || t("来源未注明单位", "Unit not specified by source");

  const confirmedSignals = useMemo(() => {
    const closedTimes = new Set(rows.filter(row => row.source.closed).map(row => row.time));
    return signals.flatMap(signal => {
      if (signal.pending_revalidation) return [];
      const time = utcTime(signal.bar_time);
      return time !== null && closedTimes.has(time) ? [{ signal, time }] : [];
    }).sort((left, right) => left.time - right.time);
  }, [signals, rows]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !hasRows) return;
    const colors = readPalette(container);
    setPalette(colors);
    setChartError(false);
    let instance: ChartInstance;
    let pendingChart: IChartApi | undefined;
    try {
      const chart = createChart(container, {
        width: Math.max(container.clientWidth, 1), height: Math.max(container.clientHeight, 340),
        layout: {
          background: { type: ColorType.Solid, color: colors.surface }, textColor: colors.muted,
          fontFamily: getComputedStyle(container).fontFamily, fontSize: 11,
          attributionLogo: true, panes: { separatorColor: colors.line, separatorHoverColor: colors.blue },
        },
        grid: { vertLines: { visible: false }, horzLines: { color: colors.line } },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: colors.line, minimumWidth: 70 },
        timeScale: { borderColor: colors.line, timeVisible: true, secondsVisible: false, rightOffset: 5 },
        localization: {
          locale: localeCode(), priceFormatter: (value: number) => priceFormatter.format(value),
          timeFormatter: (time: Time) => typeof time === "number" ? dateLabel(time as UTCTimestamp) : String(time),
        },
      });
      pendingChart = chart;
      const price = chart.addSeries(CandlestickSeries, {
        upColor: colors.up, downColor: colors.down, wickUpColor: colors.up, wickDownColor: colors.down,
        borderUpColor: colors.up, borderDownColor: colors.down,
        priceFormat: { type: "custom", formatter: (value: number) => priceFormatter.format(value) },
      });
      const lineOptions = { lineWidth: 1 as const, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
      const ma20 = chart.addSeries(LineSeries, { ...lineOptions, color: colors.blue });
      const ma60 = chart.addSeries(LineSeries, { ...lineOptions, color: colors.ma60 });
      const volume = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false,
      }, 1);
      chart.panes()[0]?.setStretchFactor(4);
      chart.panes()[1]?.setStretchFactor(1);
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.12, bottom: 0 } });
      instance = { chart, price, volume, ma20, ma60, markers: createSeriesMarkers(price, []), dataset: null };
      instanceRef.current = instance;
    } catch {
      pendingChart?.remove();
      setChartError(true);
      return;
    }

    let lastHover: UTCTimestamp | null = null;
    const onCrosshair: Parameters<IChartApi["subscribeCrosshairMove"]>[0] = event => {
      const next = event.point && typeof event.time === "number" ? event.time as UTCTimestamp : null;
      if (next !== lastHover) { lastHover = next; setHoveredTime(next); }
    };
    instance.chart.subscribeCrosshairMove(onCrosshair);
    const resize = new ResizeObserver(() => {
      if (container.clientWidth > 0 && container.clientHeight > 0) {
        const range = instance.chart.timeScale().getVisibleLogicalRange();
        instance.chart.resize(container.clientWidth, container.clientHeight);
        // Preserve the viewed candle window, rather than narrow-screen bar spacing.
        if (range) instance.chart.timeScale().setVisibleLogicalRange(range);
      }
    });
    resize.observe(container);
    const theme = new MutationObserver(() => setPalette(readPalette(container)));
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"], subtree: true });
    return () => {
      resize.disconnect();
      theme.disconnect();
      instance.chart.unsubscribeCrosshairMove(onCrosshair);
      instance.markers.detach();
      instance.chart.remove();
      if (instanceRef.current === instance) instanceRef.current = null;
    };
  }, [hasRows]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !palette) return;
    const { chart, price, volume, ma20, ma60 } = instance;
    chart.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: palette.surface }, textColor: palette.muted,
        panes: { separatorColor: palette.line, separatorHoverColor: palette.blue },
      },
      grid: { horzLines: { color: palette.line } },
      rightPriceScale: { borderColor: palette.line }, timeScale: { borderColor: palette.line },
      localization: { locale: localeCode(), priceFormatter: (value: number) => priceFormatter.format(value), timeFormatter: (time: Time) => typeof time === "number" ? dateLabel(time as UTCTimestamp) : String(time) },
    });
    price.applyOptions({
      upColor: palette.up, downColor: palette.down, wickUpColor: palette.up, wickDownColor: palette.down,
      borderUpColor: palette.up, borderDownColor: palette.down,
      priceFormat: { type: "custom", formatter: (value: number) => priceFormatter.format(value) },
    });
    ma20.applyOptions({ color: palette.blue });
    ma60.applyOptions({ color: palette.ma60 });
    const validByTime = new Map(rows.map(row => [row.time, row]));
    const candleData: (CandlestickData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] = timeline.map(({ time }) => {
      const row = validByTime.get(time);
      return row ? {
        time, open: row.open, high: row.high, low: row.low, close: row.close,
        ...(!row.source.closed ? { color: palette.surface, borderColor: palette.blue, wickColor: palette.blue } : {}),
      } : { time };
    });
    price.setData(candleData);
    const volumeData: (HistogramData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] = timeline.map(row => {
      const value = row.source.volume;
      const valid = validByTime.get(row.time);
      const color = !valid ? palette.muted : !row.source.closed ? palette.blue : valid.close >= valid.open ? palette.up : palette.down;
      return finite(value) && value >= 0
        ? { time: row.time, value, color }
        : { time: row.time };
    });
    volume.setData(volumeData);
    const indicatorByTime = new Map(indicators.flatMap(indicator => {
      const time = utcTime(indicator.time);
      return time === null ? [] : [[time, indicator] as const];
    }));
    const maData = (key: "ma20" | "ma60"): (LineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] => {
      const data: (LineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] = [];
      let previous: LineData<UTCTimestamp> | null = null;
      for (const row of timeline) {
        const value = indicatorByTime.get(row.time)?.[key];
        if (validByTime.has(row.time) && row.source.closed && typeof value === "number" && Number.isFinite(value) && value >= 0) {
          previous = { time: row.time, value, color: key === "ma20" ? palette.blue : palette.ma60 };
          data.push(previous);
        } else {
          // v5 preserves whitespace positions but connects adjacent value points.
          // A point's color owns its outgoing segment, so hide the bridge across a gap.
          if (previous) previous.color = "transparent";
          data.push({ time: row.time });
        }
      }
      return data;
    };
    ma20.setData(maData("ma20"));
    ma60.setData(maData("ma60"));
    const first = rows[0]?.source;
    const dataset = first ? `${first.provider}:${first.symbol ?? ""}:${first.interval ?? ""}` : "";
    if (instance.dataset !== dataset) {
      chart.timeScale().fitContent();
      instance.dataset = dataset;
      setHoveredTime(null);
    }
  }, [timeline, rows, indicators, palette, locale, priceFormatter]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !palette) return;
    // Marker visibility is independent of series data and the viewed candle window.
    const markerData: SeriesMarker<Time>[] = showSignalMarkers ? confirmedSignals.map(({ signal, time }) => ({
      time, id: signal.id,
      position: signal.direction === "up" ? "belowBar" : "aboveBar",
      shape: signal.direction === "up" ? "arrowUp" : signal.direction === "down" ? "arrowDown" : "circle",
      color: signal.direction === "up" ? palette.up : signal.direction === "down" ? palette.down : palette.blue,
      text: ({ breakout20: t("突", "B"), sma20_60: t("均", "MA"), volume2x: t("量", "V"), rsi14_cross: "RSI" } as Record<string, string>)[signal.rule_id] || t("信号", "Signal"),
    })) : [];
    instance.markers.setMarkers(markerData);
  }, [confirmedSignals, palette, locale, showSignalMarkers]);

  if (!hasRows) {
    return <div className="market-chart__empty" role="status">
      <strong>{t("还没有可展示的 K 线", "No candles to display yet")}</strong>
      <p>{candles.length ? t("当前数据缺少有效的开、高、低、收价格。请刷新行情或查看数据质量说明。", "The current data has no valid open, high, low and close prices. Refresh or review the data quality notes.") : t("刷新行情后，价格、成交量与已确认信号会在这里显示。", "Prices, volume and confirmed signals appear here after a refresh.")}</p>
    </div>;
  }

  return <figure className="market-chart" aria-describedby={summaryId} style={{ margin: 0, minWidth: 0 }}>
    <div className="market-chart__legend" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 16px" }}>
      <span>{t("价格", "Price")}{priceUnit ? ` · ${priceUnit}` : ""}</span>
      <span className="market-chart__key"><i aria-hidden="true" style={{ display: "inline-block", width: 16, height: 2, background: palette?.blue ?? "var(--blue)", marginRight: 6, verticalAlign: "middle" }} />MA20</span>
      <span className="market-chart__key"><i aria-hidden="true" style={{ display: "inline-block", width: 16, height: 2, background: palette?.ma60 ?? "#9b681a", marginRight: 6, verticalAlign: "middle" }} />MA60</span>
      <label className="market-chart__marker-toggle"><input type="checkbox" checked={showSignalMarkers} onChange={(event) => setShowSignalMarkers(event.target.checked)} />{t("显示信号标记", "Show signal markers")}</label>
      {confirmedSignals.some(({ signal }) => signal.is_stale) && <span className="market-chart__history">{t("包含历史信号记录", "Includes historical signal records")}</span>}
      {hasOpen && <span className="market-chart__note">{t("空心蓝柱：盘中未收盘", "Hollow blue candles: intraday, still open")}</span>}
    </div>
    {selected && <div className="market-chart__ohlc" style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", fontVariantNumeric: "tabular-nums" }}>
      <span>{dateLabel(selected.time)}</span>
      <span>{t("开 ", "O ")} {priceFormatter.format(selected.open)}</span>
      <span>{t("高 ", "H ")} {priceFormatter.format(selected.high)}</span>
      <span>{t("低 ", "L ")} {priceFormatter.format(selected.low)}</span>
      <span>{t("收 ", "C ")} {priceFormatter.format(selected.close)}</span>
      <span>{candleStatus(selected.source)}</span>
    </div>}
    {chartError && <p className="market-chart__note" role="alert">{t("图表暂时无法显示，请重新打开此标的。下方摘要保留最近一根 K 线。", "Unable to display the chart. Reopen this instrument. The summary retains the latest candle.")}</p>}
    <div ref={containerRef} className="market-chart__canvas" style={{ width: "100%", position: "relative" }} />
    <div className="market-chart__footer" style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "6px 16px" }}>
      <span>{t("下图：成交量", "Lower pane: volume")} · {quantityUnit}{missingVolume ? t(` · ${missingVolume} 根缺失值留空`, ` · ${missingVolume} missing values left blank`) : ""}</span>
      <span>{t("绿涨 · 红跌 · UTC", "Green up · Red down · UTC")}</span>
      <span>{t(`${confirmedSignals.length} 条可用的已收盘信号记录 · 标记${showSignalMarkers ? "已显示" : "已隐藏"}`, `${confirmedSignals.length} available closed-candle signal records · Markers ${showSignalMarkers ? "shown" : "hidden"}`)}</span>
      {showSignalMarkers && <span>{t("突：区间突破 · 均：均线穿越 · 量：放量，完整证据见下方", "B: breakout · MA: crossover · V: volume expansion. Full evidence below.")}</span>}
      {timeline.length > rows.length && <span>{t(`${timeline.length - rows.length} 根价格缺失或无效，保留空白位置`, `${timeline.length - rows.length} candles have missing or invalid prices; their positions remain blank`)}</span>}
      <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™ · Copyright (с) 2025 TradingView, Inc.</a>
    </div>
    <figcaption id={summaryId} className="sr-only">
      {latest && t(`最近 K 线：${dateLabel(latest.time)}，${candleStatus(latest.source)}。开盘 ${priceFormatter.format(latest.open)}，最高 ${priceFormatter.format(latest.high)}，最低 ${priceFormatter.format(latest.low)}，收盘 ${priceFormatter.format(latest.close)}${priceUnit ? ` ${priceUnit}` : ""}。成交量${finite(latest.source.volume) && latest.source.volume >= 0 ? `${volumeFormatter.format(latest.source.volume)} ${quantityUnit}` : "缺失"}。共有 ${rows.length} 根有效 K 线，${confirmedSignals.length} 条可用的已收盘信号记录。信号标记${showSignalMarkers ? "已显示" : "已隐藏"}。`, `Latest candle: ${dateLabel(latest.time)}, ${candleStatus(latest.source)}. Open ${priceFormatter.format(latest.open)}, high ${priceFormatter.format(latest.high)}, low ${priceFormatter.format(latest.low)}, close ${priceFormatter.format(latest.close)}${priceUnit ? ` ${priceUnit}` : ""}. Volume ${finite(latest.source.volume) && latest.source.volume >= 0 ? `${volumeFormatter.format(latest.source.volume)} ${quantityUnit}` : "missing"}. ${rows.length} valid candles and ${confirmedSignals.length} available closed-candle signal records. Signal markers ${showSignalMarkers ? "shown" : "hidden"}.`)}
    </figcaption>
  </figure>;
}
