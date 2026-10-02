import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight, Check, ChevronDown, CircleHelp, ExternalLink, LoaderCircle, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { api, json } from "../api";
import type { Post } from "../types";
import { sameOriginal, translatedPost, translationReady } from "../useChineseTranslation";
import Chart from "./Chart";
import { adjustmentLabel, evidenceRows, formatNumber, formatTime, isRunning, jobSummary, latestCandle, MARKET_NAMES, messageOf, PROVIDER_NAMES, qualityNotes, statusLabel, volumeLabel, webUrl } from "./helpers";
import type { Market, MarketInstrument, MarketJob, MarketOverview, MarketPreset, MarketRule, MarketSnapshot } from "./types";
import "./market.css";

interface Props {
  onOpenNews?: (query: string) => void;
  onRelatedNews?: (posts: Post[]) => void;
  chinese?: boolean;
  translationModel?: string;
  translatedNews?: Post[];
  translationIssue?: string;
  translationRunning?: boolean;
  onTranslationRetry?: () => void;
}
const BASE = "/market";
const ruleParameterLabels: Record<string, string> = {
  lookback: "回看期数", window: "窗口期数", period: "计算期数", fast: "短均线期数", slow: "长均线期数",
  fast_period: "短均线期数", slow_period: "长均线期数", fast_window: "短均线期数", slow_window: "长均线期数",
  volume_window: "成交量窗口", ratio: "成交量倍数", multiplier: "成交量倍数", threshold: "阈值", thresholds: "RSI 阈值",
  low: "低位阈值", high: "高位阈值", lower: "低位阈值", upper: "高位阈值", lower_threshold: "低位阈值", upper_threshold: "高位阈值",
};

function RuleNotes({ rules }: { rules: MarketRule[] }) {
  return <details className="market-rules">
    <summary><CircleHelp size={16} />计算规则与数据范围<ChevronDown size={15} /></summary>
    <div className="market-rules-body">
      <p>信号描述已发生的价格或成交量变化，用于核对行情。每条信号保留触发时间、观测值和来源。</p>
      {rules.map((rule) => <div className="market-rule" key={rule.id}>
        <h4>{rule.name}{!rule.enabled_by_default && <span className="market-small"> · 当前未开启</span>}</h4><p>{rule.description}</p>
        <p className="market-small">至少需要 {rule.min_bars} 根已收盘 K 线{Object.entries(rule.parameters || {}).filter(([key]) => ruleParameterLabels[key]).map(([key, value]) => ` · ${ruleParameterLabels[key]} ${String(value)}`).join("")}</p>
      </div>)}
      <p className="market-small">首版查看加密货币 1 小时线和股票日线，图表最多展示最近 180 根。股票另读取 60 根指标预热数据；这个窗口不代表完整历史，来源可能有延迟或缺口。尚未收盘的数据仅供查看。</p>
    </div>
  </details>;
}

export default function MarketWorkspace({ onOpenNews, onRelatedNews, chinese = false, translationModel = "", translatedNews = [], translationIssue = "", translationRunning = false, onTranslationRetry }: Props) {
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
  const [notice, setNotice] = useState("");
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState("");
  const [startingRefresh, setStartingRefresh] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [market, setMarket] = useState<Market>("crypto");
  const [symbol, setSymbol] = useState("");
  const alive = useRef(true);
  const overviewRequest = useRef<AbortController | null>(null);
  const selectedRef = useRef("");
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
        relatedCallback.current?.(result.related_news || []);
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
        setPollError(`暂时无法读取刷新进度：${messageOf(error)}。正在重新连接。`);
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
  const notes = qualityNotes(snapshot?.quality || selected?.quality);
  const currentProgress = job?.progress.find((item) => item.instrument_id === selectedId);
  const sourceUrl = webUrl(snapshot?.source_url || instrument?.source_url || snapshot?.signals[0]?.source_url);
  const relatedNews = (snapshot?.related_news || []).map((item) => translatedNews.find((candidate) => sameOriginal(candidate, item)) || item);
  const untranslatedCount = chinese ? relatedNews.filter((item) => !translationReady(item, translationModel)).length : 0;
  const dataStatus = instrument?.status || snapshot?.status;
  const dataMessage = instrument?.message || snapshot?.message;

  async function addInstrument(value: Market, ticker: string) {
    if (adding || !ticker.trim()) return;
    setAdding(true); setActionError(""); setNotice("");
    try {
      const result = await api<MarketInstrument>(`${BASE}/watchlist`, json("POST", { market: value, symbol: ticker.trim() }));
      if (!alive.current) return;
      setOverview((previous) => previous ? { ...previous, watchlist: [...previous.watchlist.filter((item) => item.id !== result.id), result] } : previous);
      setSelectedId(result.id); setSymbol(""); setShowAdd(false);
      setNotice(`${result.name || result.symbol} 已加入自选，点击刷新获取行情。`);
    } catch (error) { if (alive.current) setActionError(messageOf(error)); }
    finally { if (alive.current) setAdding(false); }
  }
  function submitAdd(event: FormEvent) { event.preventDefault(); void addInstrument(market, symbol); }

  async function removeInstrument(item: MarketInstrument) {
    if (deleting || busy) return;
    setDeleting(item.id); setActionError(""); setNotice("");
    try {
      await api(`${BASE}/watchlist/${encodeURIComponent(item.id)}`, json("DELETE"));
      if (!alive.current) return;
      const remaining = watchlist.filter((entry) => entry.id !== item.id);
      setOverview((previous) => previous ? { ...previous, watchlist: remaining } : previous);
      setSnapshots((previous) => { const next = { ...previous }; delete next[item.id]; return next; });
      if (selectedRef.current === item.id) setSelectedId(remaining[0]?.id || "");
      setNotice(`${item.name || item.symbol} 已移出自选。`);
    } catch (error) { if (alive.current) setActionError(messageOf(error)); }
    finally { if (alive.current) setDeleting(""); }
  }

  async function refresh(ids?: string[]) {
    if (busy || !watchlist.length) return;
    setStartingRefresh(true); setActionError(""); setNotice(""); setPollError("");
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
    return <button type="button" className="market-preset" key={`${preset.market}:${preset.symbol}`} disabled={adding || exists || watchlist.length >= (overview?.limits.max_instruments || 20)} onClick={() => void addInstrument(preset.market, preset.symbol)} aria-label={exists ? `${preset.name} 已在自选` : `添加${preset.name} ${preset.symbol}`}>
      <span><strong>{preset.symbol}</strong><small>{preset.name} · {MARKET_NAMES[preset.market]}</small></span>
      {exists ? <Check size={16} /> : <Plus size={16} />}
    </button>;
  }

  const addForm = <div className="market-add">
    <div className="market-add-heading"><strong>添加标的</strong>{watchlist.length > 0 && <button className="market-icon-button" type="button" aria-label="收起添加标的" onClick={() => setShowAdd(false)}><X size={17} /></button>}</div>
    <p className="market-small">加入自选后，点击刷新获取真实行情。</p>
    <div className="market-presets">{overview?.presets.map(presetButton)}</div>
    <form onSubmit={submitAdd} className="market-add-form">
      <label>市场<select value={market} onChange={(event) => setMarket(event.target.value as Market)} disabled={adding}>{Object.entries(MARKET_NAMES).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
      <label>标的代码<input value={symbol} onChange={(event) => setSymbol(event.target.value)} autoCapitalize="characters" spellCheck={false} maxLength={40} placeholder={market === "crypto" ? "BTC/USDT" : market === "hk" ? "0700.HK" : market === "cn" ? "600519" : "AAPL"} disabled={adding} /></label>
      <button type="submit" className="secondary-button market-button" disabled={adding || !symbol.trim() || watchlist.length >= (overview?.limits.max_instruments || 20)}>{adding ? <LoaderCircle size={16} className="market-spin" /> : <Plus size={16} />}加入自选</button>
    </form>
    {watchlist.length >= (overview?.limits.max_instruments || 20) && <p className="market-small">已达到 {overview?.limits.max_instruments || 20} 个标的上限，移除一个后可继续添加。</p>}
  </div>;

  return <section className="market-workspace" aria-label="行情与信号工作区">
    <header className="market-heading">
      <div><h1>行情与信号</h1><p>扫描自选行情，核对已收盘信号，再继续查看相关资讯。</p></div>
      <button type="button" className="primary-button market-button" disabled={busy || !watchlist.length || loadingOverview} onClick={() => void refresh()}>{busy ? <LoaderCircle size={16} className="market-spin" /> : <RefreshCw size={16} />} {busy ? "正在刷新" : "刷新全部自选"}</button>
    </header>

    {(overviewError || actionError) && <div className="market-feedback market-feedback-error" role="alert"><div><strong>{overviewError ? "暂时无法读取自选" : "操作未完成"}</strong><p>{overviewError || actionError}</p></div>{overviewError && <button className="secondary-button market-button" type="button" onClick={() => { setLoadingOverview(true); void loadOverview(); }}>重新读取</button>}</div>}
    {notice && <div className="market-feedback" role="status"><p>{notice}</p><button type="button" className="market-icon-button" onClick={() => setNotice("")} aria-label="关闭操作提示"><X size={16} /></button></div>}
    {job && <div className={`market-job ${job.status === "failed" || job.status === "partial" ? "market-job-warning" : ""}`} role="status" aria-live="polite">
      <div className="market-job-heading">{isRunning(job) ? <LoaderCircle size={16} className="market-spin" /> : job.status === "failed" ? <X size={16} /> : job.status === "partial" ? <CircleHelp size={16} /> : <Check size={16} />}<strong>{jobSummary(job)}</strong></div>
      {pollError && <p className="market-small">{pollError}</p>}
      {job.recovered && <p className="market-small">上次中断的刷新任务已恢复，以下为当前进度。</p>}
      {(job.progress.length > 0 || job.errors.length > 0) && <details className="market-job-details"><summary>查看逐个标的进度{job.errors.length ? `与 ${job.errors.length} 项失败说明` : ""}</summary><ul>{job.progress.map((entry) => <li key={entry.instrument_id}><strong>{entry.symbol}</strong><span>{statusLabel(entry.status)}</span>{entry.message && <p>{entry.message}</p>}</li>)}{job.errors.map((error, index) => <li key={`${error.instrument_id}:${index}`} className="market-job-error"><strong>{error.symbol}</strong><span>获取失败</span><p>{error.message}</p></li>)}</ul></details>}
    </div>}

    {loadingOverview && !overview ? <div className="market-initial-state" role="status"><LoaderCircle size={24} className="market-spin" /><h2>正在读取自选列表</h2><p>读取已保存的行情记录。</p></div> : !overview ? null : !watchlist.length ? <div className="market-first-use">
      <div className="market-first-intro"><span className="market-section-label">从一个标的开始</span><h2>建立你的行情观察列表</h2><p>先添加关注的标的，再主动刷新。K 线、成交量和信号会保存在本地，方便回看同一时期的资讯。</p><ul><li>加密货币查看 1 小时 K 线，股票查看日线。</li><li>标注未收盘、缺口和来源延迟，保留原始来源入口。</li><li>规则触发后展示实际观测值和计算条件。</li></ul></div>
      {addForm}
    </div> : <div className="market-layout">
      <aside className="market-watchlist" aria-label="自选标的">
        <div className="market-panel-heading"><h2>我的自选 <span>{watchlist.length}</span></h2><button type="button" className="market-icon-button" aria-label="添加自选标的" aria-expanded={showAdd} onClick={() => setShowAdd((value) => !value)} disabled={adding}><Plus size={18} /></button></div>
        <div className="market-watch-rows">{watchlist.map((item) => {
          const progress = isRunning(job) ? job?.progress.find((entry) => entry.instrument_id === item.id) : undefined;
          const itemLatest = snapshots[item.id] ? latestCandle(snapshots[item.id].candles) : undefined;
          return <div key={item.id} className={`market-watch-row ${item.id === selectedId ? "is-selected" : ""}`}>
            <button type="button" className="market-watch-select" onClick={() => setSelectedId(item.id)} aria-pressed={item.id === selectedId} aria-label={`查看 ${item.name || item.symbol} 行情`}><span className="market-watch-top"><strong>{item.symbol}</strong><span>{MARKET_NAMES[item.market]}</span></span><span className="market-watch-name">{item.name && item.name !== item.symbol ? item.name : PROVIDER_NAMES[item.provider] || item.provider}</span><span className="market-watch-bottom"><span className={`market-status ${["failed", "error", "partial"].includes(progress?.status || item.status) ? "has-warning" : ""}`}>{statusLabel(progress?.status || item.status)}</span>{itemLatest ? <span>{formatNumber(itemLatest.close)} <small>{item.currency}</small></span> : <span className="market-small">{item.count > 0 ? `${item.count} 根 K 线` : "等待首次刷新"}</span>}</span></button>
            <button type="button" className="market-icon-button market-remove" aria-label={`移除 ${item.symbol}`} disabled={busy || !!deleting} onClick={() => void removeInstrument(item)}>{deleting === item.id ? <LoaderCircle size={15} className="market-spin" /> : <Trash2 size={15} />}</button>
          </div>;
        })}</div>
        {showAdd && addForm}
        <div className="market-watch-footer"><p>选择标的查看图表。添加候选不会自动获取行情。</p><span>最多 {overview.limits.max_instruments} 个自选</span></div>
      </aside>

      <div className="market-detail" aria-busy={loadingDetail}>
        {instrument && <>
          <header className="market-instrument-heading"><div><div className="market-instrument-identity"><h2>{instrument.symbol}</h2><span>{MARKET_NAMES[instrument.market]} · {instrument.interval === "1h" ? "1 小时线" : "日线"}</span></div><p>{instrument.name && instrument.name !== instrument.symbol ? `${instrument.name} · ` : ""}{PROVIDER_NAMES[instrument.provider] || instrument.provider}</p></div><button type="button" className="secondary-button market-button" onClick={() => void refresh([instrument.id])} disabled={busy}>{busy && currentProgress?.status === "running" ? <LoaderCircle size={16} className="market-spin" /> : <RefreshCw size={16} />}刷新此标的</button></header>
          {detailError && <div className="market-feedback market-feedback-error" role="alert"><div><strong>暂时无法读取图表{snapshot?.candles.length ? "，已有图表仍保留" : ""}</strong><p>{detailError}</p></div><button className="secondary-button market-button" type="button" onClick={() => setReload((value) => value + 1)}>重新读取</button></div>}
          {snapshot ? <>
            <div className="market-price-line">{latest ? <><strong>{formatNumber(latest.close)} <span>{instrument.currency}</span></strong><span>{snapshot.coverage.stale ? "历史" : latestMatchesBar ? "最新" : "最近有效"}{latest.closed ? "收盘价" : "盘中价 · 尚未收盘"}{!latestMatchesBar && ` · ${formatTime(latest.time, instrument.timezone)}`}</span></> : <span>尚无可展示的报价</span>}{loadingDetail && <span className="market-detail-loading"><LoaderCircle size={14} className="market-spin" />读取最新记录</span>}</div>
            {(dataStatus === "failed" || dataStatus === "error" || dataStatus === "partial" || dataMessage || notes.length > 0 || snapshot.coverage.stale) && <div className="market-data-note"><strong>{dataStatus === "failed" || dataStatus === "error" ? (snapshot.candles.length ? "本次刷新失败，以下为已有行情" : "本次刷新失败，暂无已保存行情") : !snapshot.candles.length ? "等待首次获取行情" : dataStatus === "partial" ? "本次行情需要核对" : snapshot.coverage.stale ? "已有行情需要更新" : snapshot.quality.status === "warning" ? "数据需要核对" : snapshot.quality.open_rows > 0 ? "含未收盘 K 线" : "数据说明"}</strong>{dataMessage && <p>{dataMessage}</p>}{snapshot.coverage.stale && snapshot.candles.length > 0 && <p>当前数据未确认新鲜，保留的信号属于历史记录。</p>}{notes.map((note) => <p key={note}>{note}</p>)}</div>}
            {snapshot.candles.length > 0 ? <Chart key={instrument.id} candles={snapshot.candles} signals={snapshot.signals} indicators={snapshot.indicators} currency={instrument.currency} volumeUnit={volumeLabel(instrument.volume_unit, instrument.symbol)} /> : <div className="market-chart-empty"><h3>还没有行情记录</h3><p>点击“刷新此标的”，获取来源提供的最近 K 线。</p></div>}
            <dl className="market-data-facts"><div><dt>最新 K 线时间</dt><dd>{formatTime(snapshot.coverage.last_bar_at || latest?.time, instrument.timezone)}<small>{instrument.timezone}</small></dd></div><div><dt>行情获取时间</dt><dd>{formatTime(snapshot.coverage.received_at || instrument.last_success_at)}<small>本地时间</small></dd></div><div><dt>计价与成交量</dt><dd>{instrument.currency || "来源未说明"} · {volumeLabel(instrument.volume_unit, instrument.symbol)}</dd></div><div><dt>价格调整</dt><dd>{adjustmentLabel(instrument.adjustment)}</dd></div><div><dt>当前数据范围</dt><dd>{snapshot.coverage.count} 根 · {snapshot.coverage.history_complete ? "来源标记完整" : "最近窗口"}</dd></div><div><dt>来源入口</dt><dd>{sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer">查看原始来源<ExternalLink size={12} /></a> : <span>来源未提供链接</span>}</dd></div></dl>
            <section className="market-signals" aria-label="信号记录">
              <div className="market-section-heading"><h3>信号记录</h3><span>{snapshot.signals.length ? `最近 ${snapshot.signals.length} 条` : statusLabel(snapshot.signal_analysis?.status || "empty")}</span></div>
              {snapshot.signal_analysis?.message && <p className="market-signal-note">{snapshot.signal_analysis.message}</p>}
              {snapshot.signals.length ? <div className="market-signal-list">{snapshot.signals.map((signal) => <details className="market-signal" key={signal.id}>
                <summary>
                  <span className="market-signal-direction" aria-hidden="true"><ArrowUpRight size={17} style={signal.direction === "down" ? { transform: "rotate(90deg)" } : undefined} /></span>
                  <span><strong>{signal.rule_name}{signal.pending_revalidation && <em className="market-signal-pending">待重新核验</em>}</strong><small>{signal.is_stale && !signal.pending_revalidation ? "历史记录 · " : ""}{signal.summary}</small></span>
                  <time dateTime={signal.bar_close}>{formatTime(signal.bar_close, instrument.timezone)}</time><ChevronDown size={15} />
                </summary>
                <div className="market-signal-evidence">
                  {signal.pending_revalidation && <p className="market-signal-revalidation">来源已修订历史数据，目前样本不足以重新核验这条旧记录。图表不将其标为已确认触发。</p>}
                  <dl>{evidenceRows(signal).map((entry) => <div key={entry.key}><dt>{entry.label}</dt><dd>{entry.value}</dd></div>)}</dl>
                  <p>收盘时间：{formatTime(signal.bar_close, instrument.timezone)} · {signal.pending_revalidation ? "原确认时间" : "确认时间"}：{formatTime(signal.confirmed_at)}</p>
                  {webUrl(signal.source_url) && <a href={webUrl(signal.source_url)} target="_blank" rel="noopener noreferrer">核对信号来源<ExternalLink size={12} /></a>}
                </div>
              </details>)}</div> : <p className="market-no-signals">{snapshot.candles.length ? "当前窗口内还没有已确认的规则触发。可展开计算规则查看所需数据与条件。" : "取得行情后，这里会展示已确认的规则触发和观测值。"}</p>}
            </section>
            <section className="market-news-bridge" aria-label="相关资讯">
              <div><h3>把行情放回资讯上下文</h3><p>继续搜索 {instrument.name || instrument.symbol} 的相关报道，结合发布时间自行核对。</p></div>
              {onOpenNews && <button type="button" className="secondary-button market-button" onClick={() => onOpenNews(instrument.news_query || instrument.symbol)}><Search size={16} />搜索相关资讯</button>}
              {untranslatedCount > 0 && <div className="market-news-translation" role={translationIssue ? "alert" : "status"}>
                <p>{translationIssue || (translationRunning ? `正在翻译相关资讯，${untranslatedCount} 条暂显示原文。` : `${untranslatedCount} 条相关资讯尚无当前中文译文，暂显示原文。`)}</p>
                {onTranslationRetry && !translationRunning && <button type="button" className="secondary-button market-button" onClick={onTranslationRetry}>重试翻译</button>}
              </div>}
              {relatedNews.length > 0 ? <ul>{relatedNews.map((item) => {
                const url = webUrl(item.url);
                if (!url) return null;
                const display = translatedPost(item, chinese, translationModel);
                const translated = chinese && translationReady(item, translationModel);
                return <li key={item.id}>
                  <a href={url} target="_blank" rel="noopener noreferrer">{display.title}<ExternalLink size={12} /></a>
                  <span>{item.source_name} · {formatTime(item.published_at)}{chinese ? translated ? " · 中文译文" : " · 原文" : ""}</span>
                  {translated && display.title !== item.title && <details className="market-news-original"><summary>查看原标题</summary><p>{item.title}</p></details>}
                </li>;
              })}</ul> : <p className="market-small market-news-disclaimer">本地暂无匹配的同期资讯，可继续搜索。</p>}
              <p className="market-small market-news-disclaimer">同期报道与价格变化不代表因果关系。</p>
              <p className="market-small market-news-disclaimer">关联范围：最新 K 线结束时间前 3 日至后 1 日；仅关联本地已收录资讯。</p>
            </section>
          </> : <div className="market-chart-empty" role="status">{loadingDetail ? <><LoaderCircle size={22} className="market-spin" /><h3>正在读取 {instrument.symbol}</h3><p>读取已保存的 K 线和信号。</p></> : <><h3>暂时无法显示 {instrument.symbol} 的图表</h3><p>请点击上方“重新读取”再次获取本地记录。</p></>}</div>}
        </>}
        <RuleNotes rules={overview.rules} />
      </div>
    </div>}

    {overview && <details className="market-provider-notes"><summary>行情来源与延迟说明<ChevronDown size={15} /></summary><div>{overview.providers.map((provider) => <p key={provider.id}><strong>{provider.name}</strong><span>{statusLabel(provider.status)}</span>{provider.message && <span>{provider.message}</span>}{provider.delay_note && <span>{provider.delay_note}</span>}</p>)}</div></details>}
  </section>;
}
