import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Activity, AlertTriangle, ArrowUpRight, Check, ChevronDown, CircleHelp, ExternalLink, LoaderCircle, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { api, json } from "../api";
import type { Post } from "../types";
import { localizeMessage, t, useLocale } from "../i18n";
import { sameOriginal, translatedPost, translationReady } from "../useChineseTranslation";
import Chart from "./Chart";
import { adjustmentLabel, evidenceRows, formatNumber, formatTime, isRunning, instrumentName, jobSummary, latestCandle, MARKET_NAMES, messageOf, PROVIDER_NAMES, qualityNotes, ruleDescription, ruleName, signalSummary, statusLabel, volumeLabel, webUrl } from "./helpers";
import type { Market, MarketInstrument, MarketJob, MarketOverview, MarketPreset, MarketRule, MarketSnapshot } from "./types";
import "./market.css";

interface Props {
  active?: boolean;
  onOpenNews?: (query: string) => void;
  onRelatedNews?: (posts: Post[]) => void;
  chinese?: boolean;
  translationModel?: string;
  translatedNews?: Post[];
  translationIssue?: string;
  translationRunning?: boolean;
  onTranslationRetry?: () => void;
  onSetChinese?: (value: boolean) => void;
  onConfigureTranslation?: () => void;
}
const BASE = "/market";
type DetailTab = "signals" | "news" | "data";
function ruleParameterLabels(): Record<string, string> { return {
  lookback: t("回看期数", "Lookback periods"), window: t("窗口期数", "Window periods"), period: t("计算期数", "Calculation periods"), fast: t("短均线期数", "Fast MA periods"), slow: t("长均线期数", "Slow MA periods"),
  fast_period: t("短均线期数", "Fast MA periods"), slow_period: t("长均线期数", "Slow MA periods"), fast_window: t("短均线期数", "Fast MA periods"), slow_window: t("长均线期数", "Slow MA periods"),
  volume_window: t("成交量窗口", "Volume window"), ratio: t("成交量倍数", "Volume multiplier"), multiplier: t("成交量倍数", "Volume multiplier"), threshold: t("阈值", "Threshold"), thresholds: t("RSI 阈值", "RSI thresholds"),
  low: t("低位阈值", "Lower threshold"), high: t("高位阈值", "Upper threshold"), lower: t("低位阈值", "Lower threshold"), upper: t("高位阈值", "Upper threshold"), lower_threshold: t("低位阈值", "Lower threshold"), upper_threshold: t("高位阈值", "Upper threshold"),
}; }

function RuleNotes({ rules }: { rules: MarketRule[] }) {
  useLocale();
  const parameterLabels = ruleParameterLabels();
  return <details className="market-rules" open>
    <summary><CircleHelp size={16} />{t("计算规则与数据范围", "Rules and data coverage")}<ChevronDown size={15} /></summary>
    <div className="market-rules-body">
      <p>{t("信号描述已发生的价格或成交量变化，用于核对行情。每条信号保留触发时间、观测值和来源。", "Signals describe observed price or volume changes. Each record retains its trigger time, evidence and source.")}</p>
      {rules.map((rule) => <div className="market-rule" key={rule.id}>
        <h4>{ruleName(rule)}{!rule.enabled_by_default && <span className="market-small">{t(" · 当前未开启", " · Disabled")}</span>}</h4><p>{ruleDescription(rule)}</p>
        <p className="market-small">{t(`至少需要 ${rule.min_bars} 根已收盘 K 线`, `Requires at least ${rule.min_bars} closed candles`)}{Object.entries(rule.parameters || {}).filter(([key]) => parameterLabels[key]).map(([key, value]) => ` · ${parameterLabels[key]} ${String(value)}`).join("")}</p>
      </div>)}
      <p className="market-small">{t("首版查看加密货币 1 小时线和股票日线，图表最多展示最近 180 根。股票另读取 60 根指标预热数据；这个窗口不代表完整历史，来源可能有延迟或缺口。尚未收盘的数据仅供查看。", "This version supports hourly crypto candles and daily equity candles, showing up to 180 recent bars. Equities also fetch 60 warmup bars. This is a limited history window; sources may have delays or gaps. Open candles are for viewing only.")}</p>
    </div>
  </details>;
}

export default function MarketWorkspace({ active = true, onOpenNews, onRelatedNews, chinese = false, translationModel = "", translatedNews = [], translationIssue = "", translationRunning = false, onTranslationRetry, onSetChinese, onConfigureTranslation }: Props) {
  useLocale();
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [overviewError, setOverviewError] = useState("");
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [selectedId, setSelectedId] = useState("");
  const [snapshots, setSnapshots] = useState<Record<string, MarketSnapshot>>({});
  const [detailError, setDetailError] = useState("");
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [reload, setReload] = useState(0);
  const [job, setJob] = useState<MarketJob | null>(null);
  const [pollError, setPollError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState<{ kind: "added" | "removed"; name: string; symbol: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState("");
  const [startingRefresh, setStartingRefresh] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showWatchlist, setShowWatchlist] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("signals");
  const [market, setMarket] = useState<Market>("crypto");
  const [symbol, setSymbol] = useState("");
  const alive = useRef(true);
  const overviewRequest = useRef<AbortController | null>(null);
  const selectedRef = useRef("");
  const detailPanels = useRef<HTMLDivElement>(null);
  const relatedCallback = useRef(onRelatedNews);
  relatedCallback.current = onRelatedNews;
  selectedRef.current = selectedId;

  const loadOverview = useCallback(async () => {
    overviewRequest.current?.abort();
    const controller = new AbortController();
    overviewRequest.current = controller;
    try {
      const result = await api<MarketOverview>(`${BASE}/overview`, { signal: controller.signal });
      if (controller.signal.aborted || !alive.current) return;
      setOverview(result);
      setOverviewError("");
      setSelectedId((previous) => result.watchlist.some((item) => item.id === previous) ? previous : result.watchlist[0]?.id || "");
      if (result.active_job) setJob(result.active_job);
    } catch (error) {
      if (!controller.signal.aborted && alive.current) setOverviewError(messageOf(error));
    } finally {
      if (!controller.signal.aborted && alive.current) setLoadingOverview(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void loadOverview();
    return () => { alive.current = false; overviewRequest.current?.abort(); };
  }, [loadOverview]);

  useEffect(() => {
    if (!selectedId) { setLoadingDetail(false); setDetailError(""); relatedCallback.current?.([]); return; }
    const controller = new AbortController();
    setLoadingDetail(true);
    setDetailError("");
    void api<MarketSnapshot>(`${BASE}/instruments/${encodeURIComponent(selectedId)}?limit=180`, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted || !alive.current || selectedRef.current !== selectedId) return;
        if (result.instrument.id !== selectedId) throw new Error("返回的标的与当前选择不一致，请重新读取。");
        setSnapshots((previous) => ({ ...previous, [selectedId]: result }));
      })
      .catch((error: unknown) => { if (!controller.signal.aborted && alive.current && selectedRef.current === selectedId) setDetailError(messageOf(error)); })
      .finally(() => { if (!controller.signal.aborted && alive.current && selectedRef.current === selectedId) setLoadingDetail(false); });
    return () => controller.abort();
  }, [selectedId, reload]);

  useEffect(() => {
    if (!job || !isRunning(job)) return;
    const id = job.id;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    async function poll() {
      try {
        const next = await api<MarketJob>(`${BASE}/jobs/${encodeURIComponent(id)}`, { signal: controller.signal });
        if (stopped || !alive.current) return;
        setJob((current) => current?.id === id ? next : current);
        setPollError("");
        if (isRunning(next)) timer = setTimeout(poll, 1500);
        else {
          // The terminal setJob above will clean up this polling effect.
          // Request the saved snapshot before awaiting the separate overview read.
          setReload((value) => value + 1);
          await loadOverview();
        }
      } catch (error) {
        if (stopped || controller.signal.aborted || !alive.current) return;
        setPollError(messageOf(error));
        timer = setTimeout(poll, 5000);
      }
    }
    timer = setTimeout(poll, 500);
    return () => { stopped = true; controller.abort(); if (timer) clearTimeout(timer); };
  }, [job?.id, job?.status, loadOverview]);

  const busy = isRunning(job) || startingRefresh;
  const watchlist = overview?.watchlist || [];
  const selected = watchlist.find((item) => item.id === selectedId);
  const snapshot = selected ? snapshots[selected.id] : undefined;
  const instrument = snapshot && selected?.last_attempt_at && selected.last_attempt_at > (snapshot.instrument.last_attempt_at || "")
    ? { ...snapshot.instrument, ...selected }
    : snapshot?.instrument || selected;
  const latest = snapshot ? latestCandle(snapshot.candles) : undefined;
  const latestMatchesBar = !!latest && Date.parse(latest.time) === Date.parse(snapshot?.coverage.last_bar_at || "");
  const quality = instrument?.quality || snapshot?.quality;
  const notes = qualityNotes(quality);
  const currentProgress = job?.progress.find((item) => item.instrument_id === selectedId);
  const sourceUrl = webUrl(snapshot?.source_url || instrument?.source_url || snapshot?.signals[0]?.source_url);
  const relatedNews = (snapshot?.related_news || []).map((item) => translatedNews.find((candidate) => sameOriginal(candidate, item)) || item);
  const untranslatedCount = chinese ? relatedNews.filter((item) => !translationReady(item, translationModel)).length : 0;
  const dataStatus = instrument?.status || snapshot?.status;
  const dataMessage = instrument?.message || snapshot?.message;
  const hasDataWarning = !!snapshot && (["failed", "error", "partial"].includes(dataStatus || "") || notes.length > 0 || snapshot.coverage.stale);
  const quoteLabel = latest && snapshot ? latest.closed
    ? snapshot.coverage.stale ? t("历史收盘价", "Historical close") : latestMatchesBar ? t("最新收盘价", "Latest close") : t("最近有效收盘价", "Latest valid close")
    : snapshot.coverage.stale ? t("历史盘中价 · 尚未收盘", "Historical intraday quote · Candle open") : latestMatchesBar ? t("最新盘中价 · 尚未收盘", "Latest intraday quote · Candle open") : t("最近有效盘中价 · 尚未收盘", "Latest valid intraday quote · Candle open") : "";

  useEffect(() => {
    relatedCallback.current?.(active && detailTab === "news" ? snapshot?.related_news || [] : []);
    return () => { relatedCallback.current?.([]); };
  }, [active, detailTab, snapshot]);

  function navigateDetailTabs(event: KeyboardEvent<HTMLButtonElement>) {
    const tabs: DetailTab[] = ["signals", "news", "data"];
    const current = tabs.indexOf(detailTab);
    const next = event.key === "ArrowRight" ? (current + 1) % tabs.length
      : event.key === "ArrowLeft" ? (current + tabs.length - 1) % tabs.length
        : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
    if (next < 0) return;
    event.preventDefault();
    setDetailTab(tabs[next]);
    event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
  }

  function openDataDetails() {
    setDetailTab("data");
    requestAnimationFrame(() => {
      const panel = detailPanels.current?.querySelector<HTMLDivElement>("#market-panel-data");
      panel?.focus({ preventScroll: true });
      panel?.scrollIntoView({ block: "start" });
    });
  }

  async function addInstrument(value: Market, ticker: string) {
    if (adding || !ticker.trim()) return;
    setAdding(true); setActionError(""); setNotice(null);
    try {
      const result = await api<MarketInstrument>(`${BASE}/watchlist`, json("POST", { market: value, symbol: ticker.trim() }));
      if (!alive.current) return;
      setOverview((previous) => previous ? { ...previous, watchlist: [...previous.watchlist.filter((item) => item.id !== result.id), result] } : previous);
      setSelectedId(result.id); setSymbol(""); setShowAdd(false);
      setNotice({ kind: "added", name: result.name || result.symbol, symbol: result.symbol });
    } catch (error) { if (alive.current) setActionError(messageOf(error)); }
    finally { if (alive.current) setAdding(false); }
  }
  function submitAdd(event: FormEvent) { event.preventDefault(); void addInstrument(market, symbol); }

  async function removeInstrument(item: MarketInstrument) {
    if (deleting || busy) return;
    setDeleting(item.id); setActionError(""); setNotice(null);
    try {
      await api(`${BASE}/watchlist/${encodeURIComponent(item.id)}`, json("DELETE"));
      if (!alive.current) return;
      const remaining = watchlist.filter((entry) => entry.id !== item.id);
      setOverview((previous) => previous ? { ...previous, watchlist: remaining } : previous);
      setSnapshots((previous) => { const next = { ...previous }; delete next[item.id]; return next; });
      if (selectedRef.current === item.id) setSelectedId(remaining[0]?.id || "");
      setNotice({ kind: "removed", name: item.name || item.symbol, symbol: item.symbol });
    } catch (error) { if (alive.current) setActionError(messageOf(error)); }
    finally { if (alive.current) setDeleting(""); }
  }

  async function refresh(ids?: string[]) {
    if (busy || !watchlist.length) return;
    setStartingRefresh(true); setActionError(""); setNotice(null); setPollError("");
    try {
      const next = await api<MarketJob>(`${BASE}/refresh`, json("POST", { ...(ids ? { ids } : {}) }));
      if (!alive.current) return;
      setJob(next);
      if (!isRunning(next)) { await loadOverview(); if (alive.current) setReload((value) => value + 1); }
    } catch (error) { if (alive.current) setActionError(messageOf(error)); }
    finally { if (alive.current) setStartingRefresh(false); }
  }

  function presetButton(preset: MarketPreset) {
    const exists = watchlist.some((item) => item.market === preset.market && item.symbol.toUpperCase() === preset.symbol.toUpperCase());
    return <button type="button" className="market-preset" key={`${preset.market}:${preset.symbol}`} disabled={adding || exists || watchlist.length >= (overview?.limits.max_instruments || 20)} onClick={() => void addInstrument(preset.market, preset.symbol)} aria-label={exists ? t(`${instrumentName(preset.name, preset.symbol)} 已在自选`, `${instrumentName(preset.name, preset.symbol)} is already in your watchlist`) : t(`添加${instrumentName(preset.name, preset.symbol)} ${preset.symbol}`, `Add ${instrumentName(preset.name, preset.symbol)} ${preset.symbol}`)}>
      <span><strong>{preset.symbol}</strong><small>{instrumentName(preset.name, preset.symbol)} · {MARKET_NAMES[preset.market]}</small></span>
      {exists ? <Check size={16} /> : <Plus size={16} />}
    </button>;
  }

  const addForm = <div className="market-add">
    <div className="market-add-heading"><strong>{t("添加标的", "Add instrument")}</strong>{watchlist.length > 0 && <button className="market-icon-button" type="button" aria-label={t("收起添加标的", "Close add instrument")} onClick={() => setShowAdd(false)}><X size={17} /></button>}</div>
    <form onSubmit={submitAdd} className="market-add-form">
      <label>{t("市场", "Market")}<select value={market} onChange={(event) => setMarket(event.target.value as Market)} disabled={adding}>{Object.entries(MARKET_NAMES).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
      <label>{t("标的代码", "Symbol")}<input value={symbol} onChange={(event) => setSymbol(event.target.value)} autoCapitalize="characters" spellCheck={false} maxLength={40} placeholder={market === "crypto" ? "BTC/USDT" : market === "hk" ? "0700.HK" : market === "cn" ? "600519" : "AAPL"} disabled={adding} /></label>
      <button type="submit" className="primary-button market-button" disabled={adding || !symbol.trim() || watchlist.length >= (overview?.limits.max_instruments || 20)}>{adding ? <LoaderCircle size={16} className="market-spin" /> : <Plus size={16} />}{t("加入自选", "Add to watchlist")}</button>
    </form>
    <p className="market-small">{t("加入自选后，点击刷新获取真实行情。", "Add an instrument, then refresh to fetch market data.")}</p>
    {watchlist.length >= (overview?.limits.max_instruments || 20) && <p className="market-small">{t(`已达到 ${overview?.limits.max_instruments || 20} 个标的上限，移除一个后可继续添加。`, `The ${overview?.limits.max_instruments || 20}-instrument limit has been reached. Remove one to add another.`)}</p>}
    <details className="market-examples" open={!watchlist.length}><summary>{t("常用标的示例", "Instrument examples")}<ChevronDown size={14} /></summary><div className="market-presets">{overview?.presets.map(presetButton)}</div></details>
  </div>;

  return <section className="market-workspace" aria-label={t("行情与信号工作区", "Market and signals workspace")}>
    <header className="market-heading">
      <div><h1>{t("行情与信号", "Market & signals")}</h1><p>{t("查看价格与成交量，核对规则信号，再阅读相关资讯。", "Review price and volume, inspect rule signals, then read related news.")}</p></div>
      <button type="button" className="secondary-button market-button" disabled={busy || !watchlist.length || loadingOverview} onClick={() => void refresh()}>{busy ? <LoaderCircle size={16} className="market-spin" /> : <RefreshCw size={16} />} {busy ? t("正在刷新", "Refreshing") : t("刷新全部自选", "Refresh watchlist")}</button>
    </header>

    {(overviewError || actionError) && <div className="market-feedback market-feedback-error" role="alert"><div><strong>{overviewError ? t("暂时无法读取自选", "Unable to load watchlist") : t("操作未完成", "Action incomplete")}</strong><p>{localizeMessage(overviewError || actionError)}</p></div>{overviewError && <button className="secondary-button market-button" type="button" onClick={() => { setLoadingOverview(true); void loadOverview(); }}>{t("重新读取", "Reload")}</button>}</div>}
    {notice && <div className="market-feedback" role="status"><p>{notice.kind === "added" ? t(`${instrumentName(notice.name, notice.symbol)} 已加入自选，点击刷新获取行情。`, `${instrumentName(notice.name, notice.symbol)} was added. Refresh to fetch market data.`) : t(`${instrumentName(notice.name, notice.symbol)} 已移出自选。`, `${instrumentName(notice.name, notice.symbol)} was removed from your watchlist.`)}</p><button type="button" className="market-icon-button" onClick={() => setNotice(null)} aria-label={t("关闭操作提示", "Dismiss notification")}><X size={16} /></button></div>}
    {job && <div className={`market-job ${job.status === "failed" || job.status === "partial" ? "market-job-warning" : ""}`} role="status" aria-live="polite">
      <div className="market-job-heading">{isRunning(job) ? <LoaderCircle size={16} className="market-spin" /> : job.status === "failed" ? <X size={16} /> : job.status === "partial" ? <AlertTriangle size={16} /> : <Check size={16} />}<strong>{jobSummary(job)}</strong>{!isRunning(job) && <button type="button" className="market-icon-button" onClick={() => setJob(null)} aria-label={t("关闭刷新结果", "Dismiss refresh result")}><X size={16} /></button>}</div>
      {pollError && <p className="market-small">{t(`暂时无法读取刷新进度：${localizeMessage(pollError)}。正在重新连接。`, `Unable to read refresh progress: ${localizeMessage(pollError)} Reconnecting.`)}</p>}
      {job.recovered && <p className="market-small">{t("上次中断的刷新任务已恢复，以下为当前进度。", "The interrupted refresh was recovered. Current progress is shown below.")}</p>}
      {(job.progress.length > 0 || job.errors.length > 0) && <details className="market-job-details"><summary>{t("查看逐个标的进度", "View instrument progress")}{job.errors.length ? t(`与 ${job.errors.length} 项失败说明`, ` and ${job.errors.length} failure details`) : ""}</summary><ul>{job.progress.map((entry) => <li key={entry.instrument_id}><strong>{entry.symbol}</strong><span>{statusLabel(entry.status)}</span>{entry.message && <p>{localizeMessage(entry.message)}</p>}</li>)}{job.errors.map((error, index) => <li key={`${error.instrument_id}:${index}`} className="market-job-error"><strong>{error.symbol}</strong><span>{t("获取失败", "Fetch failed")}</span><p>{localizeMessage(error.message)}</p></li>)}</ul></details>}
    </div>}

    {loadingOverview && !overview ? <div className="market-initial-state" role="status"><div className="market-skeleton" aria-hidden="true"><i /><i /><i /></div><h2>{t("正在读取自选列表", "Loading watchlist")}</h2><p>{t("读取已保存的行情记录。", "Reading saved market data.")}</p></div> : !overview ? null : !watchlist.length ? <div className="market-first-use">
      <div className="market-first-intro"><h2>{t("从一个标的开始", "Start with one instrument")}</h2><p>{t("添加关注的标的，再刷新行情。K 线和信号会保存在本地，方便回看同一时期的资讯。", "Add an instrument, then refresh its market data. Candles and signals are saved locally to compare with news from the same period.")}</p><ul><li>{t("加密货币查看 1 小时 K 线，股票查看日线。", "Hourly candles for crypto; daily candles for equities.")}</li><li>{t("规则信号只使用已收盘数据，保留来源、缺口和修订记录。", "Rule signals use closed candles, with source, gap and revision records preserved.")}</li></ul></div>
      {addForm}
    </div> : <div className="market-layout">
      <aside className={`market-watchlist ${showWatchlist ? "is-expanded" : ""}`} aria-label={t("自选标的", "Watchlist instruments")}>
        <div className="market-panel-heading"><h2>{t("自选列表", "Watchlist")}<span>{watchlist.length}</span></h2><div className="market-watch-actions"><button type="button" className="market-manage-button" aria-expanded={showWatchlist} aria-controls="market-watch-rows" onClick={() => setShowWatchlist((value) => !value)}>{showWatchlist ? t("收起列表", "Hide list") : t("管理", "Manage")}</button><button type="button" className="market-icon-button" aria-label={t("添加自选标的", "Add watchlist instrument")} aria-expanded={showAdd} aria-controls="market-watch-add" onClick={() => setShowAdd((value) => !value)} disabled={adding}><Plus size={18} /></button></div></div>
        <label className="market-mobile-select">{t("当前标的", "Instrument")}<select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{watchlist.map((item) => <option key={item.id} value={item.id}>{item.symbol} · {instrumentName(item.name, item.symbol)} · {MARKET_NAMES[item.market]}</option>)}</select></label>
        <div className="market-watch-rows" id="market-watch-rows">{watchlist.map((item) => {
          const progress = isRunning(job) ? job?.progress.find((entry) => entry.instrument_id === item.id) : undefined;
          const itemLatest = snapshots[item.id] ? latestCandle(snapshots[item.id].candles) : undefined;
          return <div key={item.id} className={`market-watch-row ${item.id === selectedId ? "is-selected" : ""}`}>
            <button type="button" className="market-watch-select" onClick={() => setSelectedId(item.id)} aria-pressed={item.id === selectedId} aria-label={t(`查看 ${instrumentName(item.name, item.symbol)} 行情`, `View ${instrumentName(item.name, item.symbol)} market data`)}><span className="market-watch-top"><strong>{item.symbol}</strong><span>{MARKET_NAMES[item.market]}</span></span><span className="market-watch-name">{item.name && item.name !== item.symbol ? instrumentName(item.name, item.symbol) : PROVIDER_NAMES[item.provider] || item.provider}</span><span className="market-watch-bottom"><span className={`market-status ${["failed", "error", "partial"].includes(progress?.status || item.status) ? "has-warning" : ""}`}>{statusLabel(progress?.status || item.status)}</span>{itemLatest ? <span>{formatNumber(itemLatest.close)} <small>{item.currency}</small></span> : <span className="market-small">{item.count > 0 ? t(`${item.count} 根 K 线`, `${item.count} candles`) : t("等待首次刷新", "Awaiting first refresh")}</span>}</span></button>
            <button type="button" className="market-icon-button market-remove" aria-label={t(`移除 ${item.symbol}`, `Remove ${item.symbol}`)} disabled={busy || !!deleting} onClick={() => void removeInstrument(item)}>{deleting === item.id ? <LoaderCircle size={15} className="market-spin" /> : <Trash2 size={15} />}</button>
          </div>;
        })}</div>
        {showAdd && <div id="market-watch-add">{addForm}</div>}
        <div className="market-watch-footer"><span>{t(`最多 ${overview.limits.max_instruments} 个自选 · 手动刷新行情`, `Up to ${overview.limits.max_instruments} instruments · Refresh manually`)}</span></div>
      </aside>

      <div className="market-detail" aria-busy={loadingDetail}>
        {instrument && <>
          <header className="market-instrument-heading"><div><div className="market-instrument-identity"><h2>{instrument.symbol}</h2><span>{MARKET_NAMES[instrument.market]} · {instrument.interval === "1h" ? t("1 小时线", "Hourly") : t("日线", "Daily")}</span></div><p>{instrument.name && instrument.name !== instrument.symbol ? `${instrumentName(instrument.name, instrument.symbol)} · ` : ""}{PROVIDER_NAMES[instrument.provider] || instrument.provider}</p></div><button type="button" className="primary-button market-button" onClick={() => void refresh([instrument.id])} disabled={busy}>{busy && currentProgress?.status === "running" ? <LoaderCircle size={16} className="market-spin" /> : <RefreshCw size={16} />}{t("刷新此标的", "Refresh instrument")}</button></header>
          {detailError && <div className="market-feedback market-feedback-error" role="alert"><div><strong>{snapshot?.candles.length ? t("暂时无法读取图表，已有图表仍保留", "Unable to reload. The saved chart is retained.") : t("暂时无法读取图表", "Unable to load chart")}</strong><p>{localizeMessage(detailError)}</p></div><button className="secondary-button market-button" type="button" onClick={() => setReload((value) => value + 1)}>{t("重新读取", "Reload")}</button></div>}
          {snapshot ? <>
            <div className="market-quote"><div className="market-price-line">{latest ? <><strong>{formatNumber(latest.close)} <span>{instrument.currency}</span></strong><span>{quoteLabel}</span></> : <span>{t("尚无可展示的报价", "No quote available yet")}</span>}{loadingDetail && <span className="market-detail-loading"><LoaderCircle size={14} className="market-spin" />{t("读取最新记录", "Loading latest records")}</span>}</div><p className="market-quote-time">{latest ? <><span>{latest.closed ? t("K 线收盘", "Candle close") : t("K 线开始", "Candle start")}</span>{formatTime(latest.closed ? latest.end_time : latest.time, instrument.timezone)} <span>{instrument.timezone}</span></> : t("刷新后显示报价与时间", "Refresh to load a quote and its time")}{sourceUrl && <a href={sourceUrl} target="_blank" rel="noopener noreferrer">{t("原始来源", "Source")}<ExternalLink size={12} /></a>}</p></div>
            {(hasDataWarning || !!dataMessage) && <div className={`market-data-note ${hasDataWarning ? "has-warning" : ""}`}>
              <div className="market-data-note-heading">{hasDataWarning ? <AlertTriangle size={16} /> : <CircleHelp size={16} />}<strong>{dataStatus === "failed" || dataStatus === "error" ? snapshot.candles.length ? t("刷新失败 · 当前显示已有行情", "Refresh failed · Saved data shown") : t("刷新失败 · 暂无已保存行情", "Refresh failed · No saved data") : !snapshot.candles.length ? t("等待首次获取行情", "Awaiting first market data") : snapshot.coverage.stale ? t("历史行情 · 新鲜度未确认", "Historical data · Freshness unconfirmed") : dataStatus === "partial" || quality?.status === "warning" ? t("数据需要核对", "Data needs review") : (quality?.open_rows || 0) > 0 ? t("含未收盘 K 线", "Includes open candles") : t("数据说明", "Data notes")}</strong><button type="button" onClick={openDataDetails}>{t("查看详情", "View details")}</button></div>
              {dataMessage && <p>{localizeMessage(dataMessage)}</p>}
              <div className="market-quality-summary">{(quality?.gaps || 0) > 0 && <span>{t(`${quality!.gaps} 处时间缺口`, `${quality!.gaps} time gaps`)}</span>}{(quality?.missing_rows || 0) > 0 && <span>{t(`${quality!.missing_rows} 根数据缺失`, `${quality!.missing_rows} incomplete candles`)}</span>}{(quality?.open_rows || 0) > 0 && <span>{t(`${quality!.open_rows} 根尚未收盘`, `${quality!.open_rows} open candles`)}</span>}{snapshot.coverage.stale && <span>{t("信号属于历史记录", "Signals are historical records")}</span>}{quality?.flags.some((flag) => flag === "corporate_action") && <span>{t("包含公司行动", "Includes corporate actions")}</span>}</div>
            </div>}
            {snapshot.candles.length > 0 ? <Chart key={instrument.id} candles={snapshot.candles} signals={snapshot.signals} indicators={snapshot.indicators} currency={instrument.currency} volumeUnit={volumeLabel(instrument.volume_unit, instrument.symbol)} /> : <div className="market-chart-empty"><h3>{t("还没有行情记录", "No market data yet")}</h3><p>{t("点击“刷新此标的”，获取来源提供的最近 K 线。", "Click “Refresh instrument” to retrieve recent candles from the source.")}</p></div>}

            <div className="market-detail-tabs" role="tablist" aria-label={t("行情分析视图", "Market analysis views")}>
              {(["signals", "news", "data"] as DetailTab[]).map((tab) => <button type="button" role="tab" key={tab} id={`market-tab-${tab}`} aria-controls={`market-panel-${tab}`} aria-selected={detailTab === tab} tabIndex={detailTab === tab ? 0 : -1} onClick={() => setDetailTab(tab)} onKeyDown={navigateDetailTabs}>{tab === "signals" ? t("信号", "Signals") : tab === "news" ? t("相关资讯", "Related news") : t("数据与规则", "Data & rules")}{tab !== "data" && <span>{tab === "signals" ? snapshot.signals.length : relatedNews.length}</span>}</button>)}
            </div>
            <div className="market-tab-panels" ref={detailPanels}>
              <div className="market-tab-panel" role="tabpanel" id="market-panel-signals" aria-labelledby="market-tab-signals" tabIndex={0} hidden={detailTab !== "signals"}>
              {detailTab === "signals" && <section className="market-signals" aria-label={t("信号记录", "Signal records")}>
                <div className="market-section-heading"><h3>{t("已收盘规则信号", "Closed-candle rule signals")}</h3><span>{statusLabel(snapshot.signal_analysis?.status || "empty")}</span></div>
                {snapshot.signal_analysis?.message && <p className="market-signal-note">{localizeMessage(snapshot.signal_analysis.message)}</p>}
                {snapshot.signals.length ? <div className="market-signal-list">{snapshot.signals.map((signal) => <details className="market-signal" key={signal.id}>
                  <summary>
                    <span className="market-signal-direction" aria-hidden="true">{signal.direction === "up" || signal.direction === "down" ? <ArrowUpRight size={17} style={signal.direction === "down" ? { transform: "rotate(90deg)" } : undefined} /> : <Activity size={17} />}</span>
                    <span className="market-signal-copy"><strong>{ruleName(signal)}{signal.pending_revalidation && <em className="market-signal-pending">{t("待重新核验", "Pending revalidation")}</em>}</strong><small>{signal.is_stale && !signal.pending_revalidation ? t("历史记录 · ", "Historical · ") : ""}{signalSummary(signal)}</small><time dateTime={signal.bar_close}>{formatTime(signal.bar_close, instrument.timezone)} · {instrument.timezone}</time></span><ChevronDown size={15} />
                  </summary>
                  <div className="market-signal-evidence">
                    {signal.pending_revalidation && <p className="market-signal-revalidation">{t("来源已修订历史数据，目前样本不足以重新核验这条旧记录。图表不将其标为已确认触发。", "The source revised historical data. There is not enough history to revalidate this record, so the chart does not mark it as a confirmed trigger.")}</p>}
                    <dl>{evidenceRows(signal).map((entry) => <div key={entry.key}><dt>{entry.label}</dt><dd>{entry.value}</dd></div>)}</dl>
                    <p>{signal.pending_revalidation ? t("原确认时间", "Original confirmation") : t("确认时间", "Confirmed at")}{t("：", ": ")}{formatTime(signal.confirmed_at)} · {t("本地时间", "Local time")} · {t(`数据修订 ${signal.data_revision}`, `Data revision ${signal.data_revision}`)}</p>
                    {webUrl(signal.source_url) && <a href={webUrl(signal.source_url)} target="_blank" rel="noopener noreferrer">{t("核对信号来源", "Verify signal source")}<ExternalLink size={12} /></a>}
                  </div>
                </details>)}</div> : <div className="market-panel-empty"><h4>{snapshot.candles.length ? t("当前窗口内没有已确认的信号", "No confirmed signals in this window") : t("取得行情后才能计算信号", "Fetch market data to calculate signals")}</h4><p>{snapshot.candles.length ? t("信号需要足够且连续的已收盘数据。数据与规则页可查看计算条件及暂停原因。", "Signals require enough continuous, closed-candle data. Check Data & rules for conditions and calculation limits.") : t("刷新此标的后，这里会展示规则触发和实际观测值。", "Refresh this instrument to see rule triggers and their observed values here.")}</p><button type="button" className="market-text-button" onClick={openDataDetails}>{t("查看数据与规则", "View data & rules")}</button></div>}
              </section>}
              </div>
              <div className="market-tab-panel" role="tabpanel" id="market-panel-news" aria-labelledby="market-tab-news" tabIndex={0} hidden={detailTab !== "news"}>
              {detailTab === "news" && <section className="market-news-bridge" aria-label={t("相关资讯", "Related news")}>
                <div className="market-news-heading"><div><h3>{t("相关的本地资讯", "Related saved news")}</h3><p>{t("按标的名称与时间窗口匹配已收录的资讯，可在资讯页进一步筛选。", "Locally saved news matched by instrument and time window. Continue filtering in the news feed.")}</p></div>{onOpenNews && <button type="button" className="secondary-button market-button" onClick={() => onOpenNews(instrument.news_query || instrument.symbol)}><Search size={16} />{t("到资讯页查看", "View in news feed")}</button>}</div>
                {(onSetChinese || onConfigureTranslation) && <div className="market-reading-toolbar">{onSetChinese && <label>{t("资讯阅读语言", "News reading language")}<select value={chinese ? "zh" : "original"} onChange={(event) => onSetChinese(event.target.value === "zh")}><option value="original">{t("原文", "Original text")}</option><option value="zh">{t("中文译文", "Chinese translation")}</option></select></label>}{onConfigureTranslation && <button type="button" className="market-text-button" onClick={onConfigureTranslation}>{t("翻译 API 设置", "Translation API settings")}</button>}</div>}
                {untranslatedCount > 0 && <div className="market-news-translation" role={translationIssue ? "alert" : "status"}>
                  <p>{translationIssue ? localizeMessage(translationIssue) : translationRunning ? t(`正在翻译相关资讯，${untranslatedCount} 条暂显示原文。`, `Translating related news. ${untranslatedCount} items still show their original text.`) : t(`${untranslatedCount} 条相关资讯尚无当前中文译文，暂显示原文。`, `${untranslatedCount} related news items have no current Chinese translation and show their original text.`)}</p>
                  {onTranslationRetry && !translationRunning && <button type="button" className="secondary-button market-button" onClick={onTranslationRetry}>{t("重试翻译", "Retry translation")}</button>}
                </div>}
                {relatedNews.length > 0 ? <ul>{relatedNews.map((item) => {
                  const url = webUrl(item.url);
                  if (!url) return null;
                  const display = translatedPost(item, chinese, translationModel);
                  const translated = chinese && translationReady(item, translationModel);
                  return <li key={item.id}>
                    <a href={url} target="_blank" rel="noopener noreferrer">{display.title}<ExternalLink size={12} /></a>
                    <span>{item.source_name} · {formatTime(item.published_at)}{chinese ? translated ? t(" · 中文译文", " · Chinese translation") : t(" · 原文", " · Original") : ""}</span>
                    {translated && display.title !== item.title && <details className="market-news-original"><summary>{t("查看原标题", "View original title")}</summary><p>{item.title}</p></details>}
                  </li>;
                })}</ul> : <div className="market-panel-empty"><h4>{t("还没有匹配的本地资讯", "No matching saved news yet")}</h4><p>{t("前往资讯页搜索与该标的相关的内容。这里仅关联已收录的资讯。", "Search for this instrument in the news feed. This view only includes locally saved news.")}</p></div>}
                <p className="market-small market-news-disclaimer">{t("关联时间：最新 K 线收盘前 3 日至后 1 日。同期报道与价格变化不代表因果关系。", "Window: 3 days before to 1 day after the latest candle close. Timing does not establish causation between news and price changes.")}</p>
              </section>}
              </div>
              <div className="market-tab-panel" role="tabpanel" id="market-panel-data" aria-labelledby="market-tab-data" tabIndex={0} hidden={detailTab !== "data"}>
              {detailTab === "data" && <section className="market-data-detail" aria-label={t("数据质量与计算规则", "Data quality and calculation rules")}>
                <div className="market-quality-detail"><h3>{t("数据质量", "Data quality")}</h3>{notes.length ? <ul>{notes.map((note) => <li key={note}>{note}</li>)}</ul> : <p>{snapshot.candles.length ? t("当前记录未报告额外的质量问题，仍需结合来源与获取时间查看。", "No additional quality issues are reported in these records. Review the source and retrieval time alongside the data.") : t("尚未获取行情，当前无法核对数据质量。", "Market data has not been fetched, so its quality cannot be reviewed yet.")}</p>}{snapshot.coverage.freshness_message && <p>{localizeMessage(snapshot.coverage.freshness_message)}</p>}</div>
                <dl className="market-data-facts"><div><dt>{t("最新 K 线时间", "Latest candle time")}</dt><dd>{formatTime(snapshot.coverage.last_bar_at || latest?.time, instrument.timezone)}<small>{instrument.timezone}</small></dd></div><div><dt>{t("行情获取时间", "Data received at")}</dt><dd>{formatTime(snapshot.coverage.received_at || instrument.last_success_at)}<small>{t("本地时间", "Local time")}</small></dd></div><div><dt>{t("计价与成交量", "Currency & volume")}</dt><dd>{instrument.currency || t("来源未说明", "Not specified by source")} · {volumeLabel(instrument.volume_unit, instrument.symbol)}</dd></div><div><dt>{t("价格调整", "Price adjustment")}</dt><dd>{adjustmentLabel(instrument.adjustment)}</dd></div><div><dt>{t("当前数据范围", "Data coverage")}</dt><dd>{t(`${snapshot.coverage.count} 根`, `${snapshot.coverage.count} candles`)} · {snapshot.coverage.history_complete ? t("来源标记完整", "Source marks history complete") : t("最近窗口", "Recent window")}</dd></div><div><dt>{t("交易时段", "Trading session")}</dt><dd>{instrument.session === "24x7" ? t("全天交易", "24 / 7") : instrument.session === "regular" ? t("常规交易时段", "Regular session") : t("来源未说明", "Not specified by source")}</dd></div><div><dt>{t("最近有效 K 线修订", "Latest valid candle revision")}</dt><dd>{latest?.revision || t("尚无记录", "No record yet")}</dd></div><div><dt>{t("来源入口", "Original source")}</dt><dd>{sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer">{t("查看原始来源", "Open original source")}<ExternalLink size={12} /></a> : <span>{t("来源未提供链接", "No source link provided")}</span>}</dd></div></dl>
                <RuleNotes rules={overview.rules} />
                <details className="market-provider-notes"><summary>{t("行情来源与延迟说明", "Market sources and delays")}<ChevronDown size={15} /></summary><div>{overview.providers.map((provider) => <p key={provider.id}><strong>{localizeMessage(provider.name)}</strong><span>{statusLabel(provider.status)}</span>{provider.message && <span>{localizeMessage(provider.message)}</span>}{provider.delay_note && <span>{localizeMessage(provider.delay_note)}</span>}</p>)}</div></details>
              </section>}
              </div>
            </div>
          </> : <div className="market-chart-empty" role="status">{loadingDetail ? <><div className="market-skeleton" aria-hidden="true"><i /><i /><i /></div><h3>{t(`正在读取 ${instrument.symbol}`, `Loading ${instrument.symbol}`)}</h3><p>{t("读取已保存的 K 线和信号。", "Reading saved candles and signals.")}</p></> : <><h3>{t(`暂时无法显示 ${instrument.symbol} 的图表`, `Unable to display the ${instrument.symbol} chart`)}</h3><p>{t("请点击上方“重新读取”再次获取本地记录。", "Click “Reload” above to read local records again.")}</p></>}</div>}
        </>}
      </div>
    </div>}
  </section>;
}
