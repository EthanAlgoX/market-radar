import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Activity,
  ArrowDownToLine,
  Bitcoin,
  Bookmark,
  BookOpen,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  CircleX,
  Clock3,
  ExternalLink,
  FileText,
  Gem,
  Globe2,
  Layers3,
  Languages,
  LoaderCircle,
  Menu,
  MessageSquare,
  Moon,
  PanelRightClose,
  Plug,
  Plus,
  Radar,
  RefreshCw,
  Rss,
  Search,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Trash2,
  UserRound,
  UsersRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { api, json } from "./api";
import {
  sameOriginal,
  translatedPost,
  translationReady,
  useChineseTranslation,
} from "./useChineseTranslation";
import type {
  Channel,
  Connection,
  Job,
  Overview,
  Post,
  Settings,
  SourceKey,
  View,
} from "./types";

const TOPICS: { id: string; name: string; icon: LucideIcon; query: string }[] =
  [
    {
      id: "all",
      name: "全部资讯",
      icon: Layers3,
      query: "金融市场 OR 加密货币 OR 美股 OR 黄金",
    },
    {
      id: "macro",
      name: "宏观与政策",
      icon: Globe2,
      query: "Federal Reserve OR inflation OR 央行 OR 利率",
    },
    {
      id: "crypto",
      name: "加密货币",
      icon: Bitcoin,
      query: "Bitcoin OR Ethereum OR 加密货币",
    },
    {
      id: "us",
      name: "美股",
      icon: Activity,
      query: "S&P 500 OR Nasdaq OR 美股",
    },
    {
      id: "hk",
      name: "港股",
      icon: Building2,
      query: "Hang Seng OR 港股 OR 恒生指数",
    },
    {
      id: "cn",
      name: "A 股",
      icon: Activity,
      query: "A股 OR 上证指数 OR 沪深300",
    },
    {
      id: "finance",
      name: "财经与市场",
      icon: FileText,
      query: "财经 OR 金融市场 OR financial markets",
    },
    {
      id: "gold",
      name: "黄金与商品",
      icon: Gem,
      query: "gold price OR 黄金 OR commodities",
    },
  ];
const SOURCES: Record<SourceKey, string> = {
  x: "X",
  reddit: "Reddit",
  news: "新闻搜索",
  rss: "RSS",
  hackernews: "Hacker News",
};
const CHANNELS: { id: View; label: string; icon: LucideIcon }[] = [
  { id: "search", label: "关键词资讯", icon: Search },
  { id: "following", label: "我的关注", icon: UsersRound },
  { id: "recommended", label: "为我推荐", icon: Sparkles },
  { id: "bookmarked", label: "已收藏", icon: Bookmark },
];
const TOPIC_NAMES = Object.fromEntries(TOPICS.map((t) => [t.id, t.name]));
const splitList = (s: string) => [
  ...new Set(
    s
      .split(/[\n,，;；]/)
      .map((v) => v.trim())
      .filter(Boolean),
  ),
];
const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "暂时无法完成，请重试。";

function previewText(item: Post) {
  const text = item.summary || item.content.slice(0, 240);
  if (item.summary_kind === "llm") return text;
  const normalize = (value: string) =>
    value.replace(/\s+/g, " ").trim().toLowerCase();
  const title = normalize(item.title);
  const preview = normalize(text);
  if (
    title &&
    preview.startsWith(title) &&
    preview.length <= title.length + item.source_name.length + 12
  )
    return "";
  return text;
}

function timeLabel(value: string | null, full = false) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "时间未知";
  if (full)
    return date.toLocaleString("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour12: false,
    });
  const minutes = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (minutes >= 0 && minutes < 1) return "刚刚";
  if (minutes >= 1 && minutes < 60) return `${minutes} 分钟前`;
  if (minutes >= 60 && minutes < 1440)
    return `${Math.floor(minutes / 60)} 小时前`;
  return date.toLocaleDateString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "short",
    day: "numeric",
  });
}

function SourceMark({ source }: { source: string }) {
  return (
    <span className={`source-mark source-${source}`} aria-hidden="true">
      {source === "x" ? (
        "𝕏"
      ) : source === "reddit" ? (
        "r"
      ) : source === "hackernews" ? (
        "Y"
      ) : (
        <Rss size={13} />
      )}
    </span>
  );
}

export default function App() {
  const [page, setPage] = useState<"feed" | "settings">("feed");
  const [settingsTab, setSettingsTab] = useState<
    "accounts" | "preferences" | "feeds"
  >("accounts");
  const [topic, setTopic] = useState("all");
  const [view, setView] = useState<View>("search");
  const [query, setQuery] = useState(TOPICS[0].query);
  const [source, setSource] = useState("all");
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState("latest");
  const [items, setItems] = useState<Post[]>([]);
  const [total, setTotal] = useState(0);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [connections, setConnections] = useState<Record<string, Connection>>(
    {},
  );
  const [selected, setSelected] = useState<Post | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [toast, setToast] = useState("");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [theme, setTheme] = useState(
    () => localStorage.getItem("radar-theme") || "light",
  );
  const [pendingAuth, setPendingAuth] = useState(false);
  const completeJobs = useRef(new Set<string>());
  const fetchSequence = useRef(0);
  const itemCount = useRef(0);
  const applyTranslations = useCallback((results: Post[]) => {
    const merge = (item: Post) => {
      const result = results.find((candidate) => sameOriginal(candidate, item));
      return result ? { ...item, translation: result.translation } : item;
    };
    setItems((previous) => previous.map(merge));
    setSelected((previous) => (previous ? merge(previous) : previous));
  }, []);
  const chinese = useChineseTranslation(items, applyTranslations);
  useEffect(() => {
    itemCount.current = items.length;
  }, [items.length]);

  const tell = useCallback((message: string) => setToast(message), []);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 6000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("radar-theme", theme);
  }, [theme]);

  const loadOverview = useCallback(async () => {
    const result = await api<Overview>("/overview");
    setOverview(result);
  }, []);
  const loadConnections = useCallback(async () => {
    const result = await api<Record<string, Connection>>("/connections");
    setConnections(result);
    return result;
  }, []);
  const loadSettings = useCallback(async () => {
    setSettings(await api<Settings>("/settings"));
  }, []);
  const loadItems = useCallback(
    async (append = false) => {
      const sequence = ++fetchSequence.current;
      if (!append) setLoading(true);
      const parameters = new URLSearchParams({
        limit: "60",
        offset: append ? String(itemCount.current) : "0",
        sort,
      });
      if (topic !== "all") parameters.set("topic", topic);
      if (source !== "all") parameters.set("source", source);
      if (view === "bookmarked") parameters.set("bookmarked", "true");
      else parameters.set("channel", view);
      if (filter.trim()) parameters.set("q", filter.trim());
      try {
        const result = await api<{ items: Post[]; total: number }>(
          `/items?${parameters}`,
        );
        if (sequence !== fetchSequence.current) return;
        setItems((previous) =>
          append ? [...previous, ...result.items] : result.items,
        );
        setTotal(result.total);
        setLoadError("");
        setSelected((previous) => {
          if (previous)
            return (
              result.items.find((p) => p.id === previous.id) ||
              (append ? previous : null)
            );
          return null;
        });
      } catch (error) {
        if (sequence === fetchSequence.current)
          setLoadError(errorMessage(error));
      } finally {
        if (sequence === fetchSequence.current) setLoading(false);
      }
    },
    [topic, source, view, filter, sort],
  );

  useEffect(() => {
    void Promise.allSettled([
      loadOverview(),
      loadSettings(),
      loadConnections(),
    ]);
    const params = new URLSearchParams(window.location.search);
    if (params.get("connection") === "reddit") {
      setPage("settings");
      tell(
        params.get("status") === "connected"
          ? "Reddit 已授权，可以拉取关注内容。"
          : params.get("status") === "cancelled"
            ? "Reddit 授权已取消。"
            : "Reddit 授权未完成，请检查应用信息后重试。",
      );
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [loadOverview, loadSettings, loadConnections, tell]);
  useEffect(() => {
    const timer = setTimeout(() => void loadItems(), filter ? 250 : 0);
    return () => clearTimeout(timer);
  }, [loadItems, filter]);
  useEffect(() => {
    const timer = setInterval(() => {
      void loadOverview().catch(() => {});
    }, 30000);
    return () => clearInterval(timer);
  }, [loadOverview]);
  useEffect(() => {
    const connecting = connections.x?.state === "connecting";
    if (!connecting && !pendingAuth) return;
    const timer = setInterval(() => {
      void loadConnections()
        .then((result) => {
          if (pendingAuth && result.reddit?.state === "connected") {
            setPendingAuth(false);
            tell("Reddit 连接成功。");
          }
        })
        .catch(() => {});
    }, 2500);
    return () => clearInterval(timer);
  }, [connections.x?.state, pendingAuth, loadConnections, tell]);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    let cancelled = false;
    const tick = async () => {
      try {
        const current = await api<Job>(`/jobs/${job.id}`);
        if (cancelled) return;
        setJob(current);
        if (
          current.status !== "running" &&
          !completeJobs.current.has(current.id)
        ) {
          completeJobs.current.add(current.id);
          await Promise.allSettled([
            loadItems(),
            loadOverview(),
            loadConnections(),
          ]);
          tell(
            current.status === "failed"
              ? "本次采集未完成，请查看来源状态。"
              : `采集完成，新增 ${current.added} 条信息。`,
          );
        }
      } catch (error) {
        if (!cancelled) tell(errorMessage(error));
      }
    };
    const timer = setInterval(() => void tick(), 1200);
    void tick();
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [job?.id, job?.status, loadItems, loadOverview, loadConnections, tell]);

  async function collect(customQuery?: string, customChannel?: Channel) {
    const channel = customChannel || (view === "bookmarked" ? "search" : view);
    const text = customQuery ?? query;
    const personalSources = [
      ...(connections.x?.state === "connected" || settings?.rsshub_url
        ? ["x"]
        : []),
      ...(connections.reddit?.state === "connected" ? ["reddit"] : []),
    ];
    const rssSources = settings?.rss_feeds.some((feed) => feed.enabled)
      ? ["rss"]
      : [];
    if (channel === "search" && !text.trim()) {
      tell("请输入要搜集的关键词。");
      return;
    }
    if (
      channel !== "search" &&
      !["x", "reddit"].some((s) => connections[s]?.state === "connected") &&
      !settings?.rsshub_url
    ) {
      setPage("settings");
      setSettingsTab("accounts");
      tell("先连接 X 或 Reddit，再拉取你的个人信息流。");
      return;
    }
    setStarting(true);
    if (customQuery) setQuery(customQuery);
    if (view === "bookmarked" || customChannel) setView(channel);
    setFilter("");
    try {
      const current = await api<Job>(
        "/collect",
        json("POST", {
          query: text.trim(),
          channel,
          topic: topic === "all" ? undefined : topic,
          sources:
            source !== "all"
              ? [source]
              : channel === "search"
                ? ["news", ...rssSources, ...personalSources]
                : channel === "following"
                  ? [...personalSources, ...rssSources]
                  : personalSources,
        }),
      );
      setJob(current);
      if (current.status !== "running") {
        await Promise.allSettled([loadItems(), loadOverview()]);
      }
    } catch (error) {
      tell(errorMessage(error));
    } finally {
      setStarting(false);
    }
  }
  async function patchItem(item: Post, changes: Partial<Post>) {
    try {
      const response = await api<Post>(
        `/items/${item.id}`,
        json("PATCH", changes),
      );
      const updated = { ...item, ...changes, ...response };
      setItems((previous) =>
        previous.map((p) => (p.id === item.id ? updated : p)),
      );
      setSelected((previous) =>
        previous?.id === item.id ? updated : previous,
      );
      void loadOverview();
      if (view === "bookmarked" && changes.bookmarked === false)
        void loadItems();
    } catch (error) {
      tell(errorMessage(error));
    }
  }
  function openItem(item: Post) {
    setSelected(item);
    if (!item.is_read) void patchItem(item, { is_read: true });
  }
  function pickTopic(id: string) {
    setTopic(id);
    setPage("feed");
    setSelected(null);
    setFilter("");
    setMobileMenu(false);
    setQuery(TOPICS.find((t) => t.id === id)?.query || TOPICS[0].query);
  }
  const busy = starting || job?.status === "running";
  const counts = overview?.counts;
  const currentTopic = TOPICS.find((t) => t.id === topic)!;
  const currentChannel = CHANNELS.find((c) => c.id === view)!;
  const availableSources =
    overview?.sources.filter((s) =>
      ["available", "connected"].includes(s.status),
    ).length || 0;
  const dateText = new Date().toLocaleDateString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  return (
    <div className="app-shell">
      {mobileMenu && (
        <button
          className="nav-backdrop"
          aria-label="关闭导航"
          onClick={() => setMobileMenu(false)}
        />
      )}
      <aside className={`sidebar ${mobileMenu ? "is-open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            pickTopic("all");
          }}
        >
          <span className="brand-symbol">
            <Radar size={23} strokeWidth={1.8} />
          </span>
          <span>
            <strong>交易雷达</strong>
            <small>Market Radar</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="local-indicator" />
          个人工作区<span className="local-label">本地</span>
        </div>
        <div className="nav-caption">交易主题</div>
        <nav className="topic-nav" aria-label="交易主题">
          {TOPICS.map((t) => {
            const Icon = t.icon;
            const count =
              t.id === "all"
                ? counts?.total
                : overview?.topics.find((v) => v.id === t.id)?.count;
            return (
              <button
                key={t.id}
                className={`nav-item ${page === "feed" && topic === t.id ? "active" : ""}`}
                onClick={() => pickTopic(t.id)}
              >
                <Icon size={18} strokeWidth={1.7} />
                <span>{t.name}</span>
                {count !== undefined && count > 0 && (
                  <span className="nav-count">{count}</span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="nav-caption nav-caption-spaced">
          我的关键词
          <button
            className="icon-button small"
            title="编辑关键词"
            aria-label="编辑关键词"
            onClick={() => {
              setPage("settings");
              setSettingsTab("preferences");
            }}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="keyword-list">
          {(
            overview?.keywords || [
              "宏观",
              "加密货币",
              "美股",
              "港股",
              "A股",
              "黄金",
            ]
          )
            .slice(0, 9)
            .map((keyword) => (
              <button
                key={keyword}
                onClick={() => {
                  setPage("feed");
                  setView("search");
                  setTopic("all");
                  setQuery(keyword);
                  setMobileMenu(false);
                }}
              >
                <span>#</span>
                {keyword}
              </button>
            ))}
        </div>
        <div className="sidebar-bottom">
          <button
            className={`nav-item ${page === "settings" ? "active" : ""}`}
            onClick={() => {
              setPage("settings");
              setSettingsTab("accounts");
              setMobileMenu(false);
            }}
          >
            <Plug size={18} />
            <span>来源与账号</span>
          </button>
          <div className="local-footer">
            <span>数据保存在这台电脑</span>
            <button
              className="icon-button small"
              aria-label={theme === "light" ? "切换深色模式" : "切换浅色模式"}
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? <Moon size={15} /> : <Sun size={15} />}
            </button>
          </div>
        </div>
      </aside>

      <main className="main-workspace">
        <header className="topbar">
          <div className="topbar-start">
            <button
              className="icon-button mobile-nav-toggle"
              aria-label="打开导航"
              onClick={() => setMobileMenu(true)}
            >
              <Menu size={21} />
            </button>
            <span>{page === "feed" ? "资讯工作台" : "工作区设置"}</span>
          </div>
          <div className="topbar-end">
            <button
              className={`language-button ${chinese.chinese ? "active" : ""}`}
              aria-pressed={chinese.chinese}
              onClick={chinese.toggle}
              title="使用 DeepSeek Flash 翻译资讯，原始内容会保留"
            >
              <Languages size={16} />
              {chinese.chinese ? "切回原文" : "一键切换中文"}
            </button>
            <time>{dateText}</time>
            <span className="topbar-divider" />
            <span className="source-availability">
              <span
                className={`status-dot ${availableSources > 0 ? "success" : ""}`}
              />
              {availableSources > 0
                ? `${availableSources} 个可用来源`
                : "检查来源连接"}
            </span>
          </div>
        </header>

        {page === "feed" ? (
          <>
            <section className="search-section">
              <div className="page-heading">
                <div>
                  <div className="page-kicker">
                    {currentTopic.id === "all" ? "跨源信息流" : "主题信息流"}
                  </div>
                  <h1>{currentTopic.name}</h1>
                </div>
                <div className="heading-actions">
                  <button
                    className="quiet-button"
                    onClick={() =>
                      window.open(
                        "/api/export?format=json",
                        "_blank",
                        "noopener",
                      )
                    }
                  >
                    <ArrowDownToLine size={16} />
                    导出
                  </button>
                  <button
                    className="icon-button"
                    aria-label="打开来源设置"
                    onClick={() => {
                      setPage("settings");
                      setSettingsTab("accounts");
                    }}
                  >
                    <SlidersHorizontal size={19} />
                  </button>
                </div>
              </div>
              <form
                className="search-form"
                onSubmit={(event: FormEvent) => {
                  event.preventDefault();
                  void collect(undefined, "search");
                }}
              >
                <Search className="search-leading" size={20} />
                <input
                  aria-label="搜索关键词"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="输入关键词，如：美联储、Bitcoin、黄金…"
                  maxLength={500}
                />
                <button
                  className="primary-button"
                  disabled={busy || !query.trim()}
                  type="submit"
                >
                  {busy ? (
                    <LoaderCircle size={17} className="spin" />
                  ) : (
                    <Search size={17} />
                  )}
                  {busy ? "正在采集" : "跨源搜索"}
                </button>
              </form>
              {chinese.chinese && (
                <div
                  className={`translation-notice ${chinese.issue || Object.keys(chinese.failures).length ? "has-error" : ""}`}
                  role="status"
                >
                  {chinese.running ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <Languages size={14} />
                  )}
                  <span>
                    {chinese.issue ||
                      (chinese.running
                        ? `DeepSeek Flash 正在翻译 · ${chinese.completed}/${items.length}`
                        : `中文阅读 · ${chinese.ready}/${items.length} 条已就绪`)}
                    {Object.keys(chinese.failures).length > 0 &&
                      ` · ${Object.keys(chinese.failures).length} 条翻译失败，已保留原文`}
                  </span>
                  {!chinese.running &&
                    (chinese.issue ||
                      Object.keys(chinese.failures).length > 0) && (
                      <button className="text-button" onClick={chinese.retry}>
                        重试翻译
                      </button>
                    )}
                </div>
              )}
              <div className="search-hint">
                {view === "following"
                  ? "关注内容独立收录，不受关键词筛选影响。"
                  : view === "recommended"
                    ? "整理已连接账号的推荐信息，并保留每条内容的来源。"
                    : "搜索会从可用来源获取新内容，收录后可继续筛选、整理和收藏。"}
              </div>
            </section>

            <div className="channel-row">
              <div
                className="channel-tabs"
                role="tablist"
                aria-label="信息类型"
              >
                {CHANNELS.map((c) => {
                  const Icon = c.icon;
                  const count = counts?.[c.id];
                  return (
                    <button
                      key={c.id}
                      role="tab"
                      aria-selected={view === c.id}
                      className={view === c.id ? "active" : ""}
                      onClick={() => {
                        setView(c.id);
                        setSelected(null);
                        setFilter("");
                      }}
                    >
                      <Icon size={16} />
                      {c.label}
                      {count !== undefined && count > 0 && <span>{count}</span>}
                    </button>
                  );
                })}
              </div>
              <button
                className="quiet-button collect-button"
                disabled={busy}
                onClick={() => void collect()}
              >
                <RefreshCw size={15} className={busy ? "spin" : ""} />
                {view === "following"
                  ? "拉取关注"
                  : view === "recommended"
                    ? "拉取推荐"
                    : "更新资讯"}
              </button>
            </div>

            {job && <JobNotice job={job} close={() => setJob(null)} />}
            <div
              className={`reading-workspace ${selected ? "has-selection" : ""}`}
            >
              <section className="feed-section" aria-label="资讯列表">
                <div className="feed-toolbar">
                  <div className="feed-total">
                    <strong>{loading ? "…" : total}</strong> 条信息
                    <span>{currentChannel.label}</span>
                  </div>
                  <div className="feed-controls">
                    <label className="filter-input">
                      <Search size={14} />
                      <input
                        aria-label="筛选已收录内容"
                        placeholder="筛选已收录内容"
                        value={filter}
                        onChange={(event) => setFilter(event.target.value)}
                      />
                      {filter && (
                        <button
                          className="icon-button small"
                          type="button"
                          aria-label="清空筛选"
                          onClick={() => setFilter("")}
                        >
                          <X size={13} />
                        </button>
                      )}
                    </label>
                    <label className="select-wrap">
                      <span className="sr-only">数据来源</span>
                      <select
                        value={source}
                        onChange={(event) => {
                          setSource(event.target.value);
                          setSelected(null);
                        }}
                      >
                        <option value="all">所有来源</option>
                        {Object.entries(SOURCES).map(([key, name]) => (
                          <option key={key} value={key}>
                            {name}
                          </option>
                        ))}
                      </select>
                      <ChevronDown size={13} />
                    </label>
                    <label className="select-wrap sort-select">
                      <span className="sr-only">排列方式</span>
                      <select
                        value={sort}
                        onChange={(event) => setSort(event.target.value)}
                      >
                        <option value="latest">最新优先</option>
                        <option value="relevance">相关度</option>
                      </select>
                      <ChevronDown size={13} />
                    </label>
                  </div>
                </div>
                {loadError ? (
                  <div className="empty-state error-state">
                    <CircleX size={29} />
                    <h2>暂时无法读取资讯</h2>
                    <p>{loadError}</p>
                    <button
                      className="secondary-button"
                      onClick={() =>
                        void Promise.allSettled([
                          loadItems(),
                          loadOverview(),
                          loadSettings(),
                          loadConnections(),
                        ])
                      }
                    >
                      重新连接
                    </button>
                  </div>
                ) : loading ? (
                  <div className="loading-list" aria-label="正在读取资讯">
                    {[1, 2, 3, 4].map((n) => (
                      <div className="skeleton-row" key={n}>
                        <div className="skeleton short" />
                        <div className="skeleton title" />
                        <div className="skeleton" />
                        <div className="skeleton medium" />
                      </div>
                    ))}
                  </div>
                ) : items.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-icon">
                      {view === "following" ? (
                        <UsersRound size={31} />
                      ) : view === "recommended" ? (
                        <Sparkles size={31} />
                      ) : view === "bookmarked" ? (
                        <Bookmark size={31} />
                      ) : (
                        <Radar size={34} strokeWidth={1.4} />
                      )}
                    </span>
                    <h2>
                      {filter || source !== "all"
                        ? "没有符合筛选条件的内容"
                        : view === "following"
                          ? "把你关注的信息带到这里"
                          : view === "recommended"
                            ? "阅读为你推荐的内容"
                            : view === "bookmarked"
                              ? "值得留下的信息，都在这里"
                              : "开始收集你的交易信息"}
                    </h2>
                    <p>
                      {filter || source !== "all"
                        ? "调整关键词或数据来源，查看已收录的信息。"
                        : view === "following"
                          ? "连接 X 或 Reddit 后，拉取关注信息；即使没有关键词，也会收录。"
                          : view === "recommended"
                            ? "连接账号后可以拉取 X 推荐流和 Reddit API 首页。"
                            : view === "bookmarked"
                              ? "点击资讯旁的收藏按钮，稍后可以在这里继续阅读。"
                              : "从宏观、加密货币、股票和黄金开始，搜索会获取真实公开来源的最新内容。"}
                    </p>
                    {view !== "bookmarked" && (
                      <button
                        className="primary-button"
                        disabled={busy}
                        onClick={() => void collect()}
                      >
                        {busy ? (
                          <LoaderCircle className="spin" size={17} />
                        ) : (
                          <Search size={17} />
                        )}
                        {view === "following"
                          ? "拉取关注内容"
                          : view === "recommended"
                            ? "拉取推荐内容"
                            : "搜索最新信息"}
                      </button>
                    )}
                    {(filter || source !== "all") && (
                      <button
                        className="quiet-button"
                        onClick={() => {
                          setFilter("");
                          setSource("all");
                        }}
                      >
                        清除筛选
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="post-list">
                    {items.map((item) => (
                      <article
                        className={`post-row ${selected?.id === item.id ? "selected" : ""} ${item.is_read ? "is-read" : ""}`}
                        key={item.id}
                      >
                        <div className="post-row-meta">
                          <SourceMark source={item.source} />
                          <span className="post-source">
                            {item.source_name || SOURCES[item.source]}
                          </span>
                          {item.author && (
                            <>
                              <span className="meta-separator">·</span>
                              <span className="post-author">{item.author}</span>
                            </>
                          )}
                          <time title={timeLabel(item.published_at, true)}>
                            {timeLabel(item.published_at)}
                          </time>
                          <button
                            className={`icon-button bookmark-button ${item.bookmarked ? "is-saved" : ""}`}
                            aria-label={
                              item.bookmarked ? "取消收藏" : "收藏资讯"
                            }
                            onClick={() =>
                              void patchItem(item, {
                                bookmarked: !item.bookmarked,
                              })
                            }
                          >
                            <Bookmark
                              size={17}
                              fill={item.bookmarked ? "currentColor" : "none"}
                            />
                          </button>
                        </div>
                        <button
                          className="post-content-button"
                          onClick={() => openItem(item)}
                        >
                          <h2>
                            {translatedPost(
                              item,
                              chinese.chinese,
                              chinese.model,
                            ).title ||
                              translatedPost(
                                item,
                                chinese.chinese,
                                chinese.model,
                              ).content.slice(0, 110)}
                            {!item.is_read && (
                              <span className="unread-dot" aria-label="未读" />
                            )}
                          </h2>
                          {previewText(
                            translatedPost(
                              item,
                              chinese.chinese,
                              chinese.model,
                            ),
                          ) && (
                            <p>
                              {previewText(
                                translatedPost(
                                  item,
                                  chinese.chinese,
                                  chinese.model,
                                ),
                              )}
                            </p>
                          )}
                        </button>
                        <div className="post-row-footer">
                          <div className="post-tags">
                            {chinese.chinese && (
                              <span
                                className={`translation-tag ${chinese.failures[item.id] ? "failed" : ""}`}
                              >
                                {translationReady(item, chinese.model)
                                  ? "中文译文"
                                  : chinese.failures[item.id]
                                    ? "翻译失败 · 原文"
                                    : chinese.running
                                      ? "翻译中 · 原文"
                                      : "暂显示原文"}
                              </span>
                            )}
                            {(item.topics || []).slice(0, 3).map((t) => (
                              <span key={t}>{TOPIC_NAMES[t] || t}</span>
                            ))}
                            {item.summary_kind === "llm" && (
                              <span className="ai-tag">
                                <Sparkles size={11} />
                                AI 摘要
                              </span>
                            )}
                          </div>
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="original-link"
                          >
                            原文
                            <ExternalLink size={12} />
                          </a>
                        </div>
                      </article>
                    ))}
                    {items.length < total && (
                      <button
                        className="load-more"
                        onClick={() => void loadItems(true)}
                      >
                        加载更多
                        <ChevronDown size={16} />
                      </button>
                    )}
                  </div>
                )}
              </section>
              {selected ? (
                <ReadPane
                  item={selected}
                  close={() => setSelected(null)}
                  patch={(changes) => void patchItem(selected, changes)}
                  update={(item) => {
                    setSelected((previous) =>
                      previous?.id === item.id ? item : previous,
                    );
                    setItems((previous) =>
                      previous.map((p) => (p.id === item.id ? item : p)),
                    );
                  }}
                  tell={tell}
                  llmEnabled={!!settings?.llm.enabled}
                  chinese={chinese.chinese}
                  translationModel={chinese.model}
                />
              ) : (
                <aside className="context-pane">
                  <div className="context-intro">
                    <BookOpen size={21} />
                    <h2>把信息变成脉络</h2>
                    <p>选中一条资讯，在这里阅读整理内容和原文。</p>
                  </div>
                  <div className="context-section">
                    <div className="context-title">
                      数据来源
                      <button
                        className="text-button"
                        onClick={() => {
                          setPage("settings");
                          setSettingsTab("accounts");
                        }}
                      >
                        管理
                      </button>
                    </div>
                    {(overview?.sources || []).map((s) => (
                      <div className="source-status-row" key={s.source}>
                        <SourceMark source={s.source} />
                        <span>{s.name}</span>
                        <span className={`source-status ${s.status}`}>
                          {s.status === "connected"
                            ? "已连接"
                            : s.status === "available"
                              ? "可用"
                              : s.status === "error"
                                ? "需检查"
                                : "未连接"}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="context-section">
                    <div className="context-title">收录方式</div>
                    <div className="channel-note">
                      <Search size={16} />
                      <div>
                        <strong>关键词资讯</strong>
                        <p>搜集与你的研究主题相关的信息。</p>
                      </div>
                    </div>
                    <div className="channel-note">
                      <UsersRound size={16} />
                      <div>
                        <strong>我的关注</strong>
                        <p>关注账号的内容独立保留。</p>
                      </div>
                    </div>
                    <div className="channel-note">
                      <Sparkles size={16} />
                      <div>
                        <strong>为我推荐</strong>
                        <p>整理账号信息流，保留来源。</p>
                      </div>
                    </div>
                  </div>
                  <div className="context-footnote">
                    <CircleHelp size={15} />
                    <span>
                      每条信息均可跳转原文。摘要供快速阅读，原文提供完整上下文。
                    </span>
                  </div>
                </aside>
              )}
            </div>
          </>
        ) : (
          <SettingsPage
            settings={settings}
            connections={connections}
            tab={settingsTab}
            setTab={setSettingsTab}
            save={async (value) => {
              const result = await api<Settings>(
                "/settings",
                json("PUT", value),
              );
              setSettings(result);
              await Promise.allSettled([loadOverview(), loadConnections()]);
            }}
            reloadConnections={loadConnections}
            reloadSettings={loadSettings}
            tell={tell}
            onAuth={() => setPendingAuth(true)}
            back={() => setPage("feed")}
          />
        )}
      </main>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          <span>{toast}</span>
          <button
            className="icon-button small"
            aria-label="关闭通知"
            onClick={() => setToast("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function JobNotice({ job, close }: { job: Job; close: () => void }) {
  const running = job.status === "running";
  return (
    <div
      className={`job-notice ${job.status === "failed" ? "has-error" : ""}`}
      role="status"
    >
      <div className="job-title">
        {running ? (
          <LoaderCircle size={17} className="spin" />
        ) : job.status === "failed" ? (
          <CircleX size={17} />
        ) : (
          <CheckCircle2 size={17} />
        )}
        <strong>
          {running
            ? "正在从各个来源收集信息"
            : job.status === "failed"
              ? "本次采集未完成"
              : `收录完成 · 新增 ${job.added} 条`}
        </strong>
        {!running && (
          <button
            className="icon-button small"
            aria-label="收起采集结果"
            onClick={close}
          >
            <X size={15} />
          </button>
        )}
      </div>
      {job.progress.length > 0 && (
        <div className="job-sources">
          {job.progress.map((p, i) => (
            <span key={`${p.source}-${i}`} className={`job-source ${p.status}`}>
              {p.status === "running" ? (
                <LoaderCircle size={12} className="spin" />
              ) : ["success", "completed"].includes(p.status) ? (
                <Check size={12} />
              ) : ["error", "failed"].includes(p.status) ? (
                <CircleX size={12} />
              ) : (
                <Clock3 size={12} />
              )}
              {SOURCES[p.source as SourceKey] || p.source}
              {p.count ? ` ${p.count} 条` : ""}
            </span>
          ))}
        </div>
      )}
      {job.errors.length > 0 && (
        <details className="job-errors">
          <summary>{job.errors.length} 个来源需要检查</summary>
          {job.errors.map((e, i) => (
            <p key={i}>
              <strong>{SOURCES[e.source as SourceKey] || e.source}：</strong>
              {e.message}
            </p>
          ))}
        </details>
      )}
    </div>
  );
}

function ReadPane({
  item,
  close,
  patch,
  update,
  tell,
  llmEnabled,
  chinese,
  translationModel,
}: {
  item: Post;
  close: () => void;
  patch: (changes: Partial<Post>) => void;
  update: (item: Post) => void;
  tell: (s: string) => void;
  llmEnabled: boolean;
  chinese: boolean;
  translationModel: string;
}) {
  const display = translatedPost(item, chinese, translationModel);
  const [tab, setTab] = useState<"summary" | "original">("summary");
  const [summarizing, setSummarizing] = useState(false);
  useEffect(() => setTab("summary"), [item.id]);
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", handleKey);
    const mobile = window.matchMedia("(max-width: 760px)").matches;
    const previous = document.body.style.overflow;
    if (mobile) document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previous;
    };
  }, [close]);
  async function summarize() {
    setSummarizing(true);
    try {
      update(await api<Post>(`/items/${item.id}/summarize`, json("POST")));
      tell("摘要已更新。");
    } catch (error) {
      tell(errorMessage(error));
    } finally {
      setSummarizing(false);
    }
  }
  return (
    <aside className="read-pane">
      <div className="read-pane-toolbar">
        <span>阅读详情</span>
        <div>
          <button
            className={`icon-button ${item.bookmarked ? "is-saved" : ""}`}
            aria-label={item.bookmarked ? "取消收藏" : "收藏资讯"}
            onClick={() => patch({ bookmarked: !item.bookmarked })}
          >
            <Bookmark
              size={17}
              fill={item.bookmarked ? "currentColor" : "none"}
            />
          </button>
          <button
            className="icon-button"
            aria-label="关闭阅读详情"
            onClick={close}
          >
            <PanelRightClose size={19} />
          </button>
        </div>
      </div>
      <div className="read-pane-content">
        <div className="detail-source">
          <SourceMark source={item.source} />
          <span>{item.source_name}</span>
        </div>
        <h2>{display.title || display.content.slice(0, 120)}</h2>
        <div className="detail-meta">
          {item.author && (
            <span>
              <UserRound size={13} />
              {item.author}
            </span>
          )}
          <time>
            <Clock3 size={13} />
            {timeLabel(item.published_at, true)}
          </time>
        </div>
        <a
          className="secondary-button original-button"
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink size={15} />
          打开原文
        </a>
        <div className="detail-tabs">
          <button
            className={tab === "summary" ? "active" : ""}
            onClick={() => setTab("summary")}
          >
            整理内容
          </button>
          <button
            className={tab === "original" ? "active" : ""}
            onClick={() => setTab("original")}
          >
            {chinese ? "中文全文" : "原始文本"}
          </button>
        </div>
        {tab === "summary" ? (
          <>
            <div className="summary-label">
              {item.summary_kind === "llm" ? (
                <>
                  <Sparkles size={14} />
                  AI 摘要
                </>
              ) : (
                <>
                  <FileText size={14} />
                  原文摘录
                </>
              )}
            </div>
            <div className="detail-body">
              {previewText(display) ||
                "此来源只提供标题或简短文本，请打开原文阅读完整内容。"}
            </div>
            {llmEnabled && (
              <button
                className="quiet-button ai-summary-button"
                disabled={summarizing}
                onClick={() => void summarize()}
              >
                {summarizing ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <Sparkles size={15} />
                )}
                {summarizing ? "正在整理" : "生成 AI 摘要"}
              </button>
            )}
            <div className="detail-section">
              <h3>研究主题</h3>
              <div className="detail-topics">
                {item.topics.length ? (
                  item.topics.map((t) => (
                    <span key={t}>{TOPIC_NAMES[t] || t}</span>
                  ))
                ) : (
                  <span>未分类</span>
                )}
              </div>
            </div>
            {item.matched_keywords.length > 0 && (
              <div className="detail-section">
                <h3>命中关键词</h3>
                <div className="detail-keywords">
                  {item.matched_keywords.map((k) => (
                    <span key={k}>#{k}</span>
                  ))}
                </div>
              </div>
            )}
            <div className="detail-section">
              <h3>收录来源</h3>
              <p className="detail-secondary">
                {item.channels
                  .map((c) => CHANNELS.find((v) => v.id === c)?.label || c)
                  .join(" · ")}
                <br />
                {timeLabel(item.collected_at, true)}
              </p>
            </div>
          </>
        ) : (
          <>
            <div className="detail-body original-text">
              {display.content || "此来源只提供标题和链接。"}
            </div>
            <p className="text-note">
              {chinese && translationReady(item, translationModel)
                ? "这里是来源文本的中文译文；完整文章或讨论请查看原文。"
                : "这里保留的是采集时来源返回的文本，完整文章或讨论请查看原文。"}
            </p>
            {chinese && (
              <details className="original-disclosure">
                <summary>查看原始文本</summary>
                <div className="detail-body">
                  {item.content || "此来源只提供标题和链接。"}
                </div>
              </details>
            )}
          </>
        )}
        {Object.values(item.metrics || {}).some((v) => v > 0) && (
          <div className="detail-metrics">
            {Object.entries(item.metrics)
              .filter(([, v]) => v > 0)
              .map(([k, v]) => (
                <span key={k}>
                  {k === "comments" ? (
                    <MessageSquare size={13} />
                  ) : (
                    <Activity size={13} />
                  )}
                  {v.toLocaleString()}{" "}
                  {k === "comments"
                    ? "讨论"
                    : k === "likes"
                      ? "赞"
                      : k === "reposts"
                        ? "转发"
                        : k}
                </span>
              ))}
          </div>
        )}
      </div>
    </aside>
  );
}

type SettingsTab = "accounts" | "preferences" | "feeds";
function SettingsPage({
  settings,
  connections,
  tab,
  setTab,
  save,
  reloadConnections,
  reloadSettings,
  tell,
  onAuth,
  back,
}: {
  settings: Settings | null;
  connections: Record<string, Connection>;
  tab: SettingsTab;
  setTab: (tab: SettingsTab) => void;
  save: (value: unknown) => Promise<void>;
  reloadConnections: () => Promise<unknown>;
  reloadSettings: () => Promise<void>;
  tell: (message: string) => void;
  onAuth: () => void;
  back: () => void;
}) {
  const [draft, setDraft] = useState<Settings | null>(null);
  const [keywords, setKeywords] = useState("");
  const [xAuthors, setXAuthors] = useState("");
  const [redditAuthors, setRedditAuthors] = useState("");
  const [cookies, setCookies] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [llmKey, setLlmKey] = useState("");
  const [newFeedName, setNewFeedName] = useState("");
  const [newFeedUrl, setNewFeedUrl] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => {
    if (!settings) return;
    setDraft(settings);
    setKeywords(settings.keywords.join("\n"));
    setXAuthors(settings.authors.x.join("\n"));
    setRedditAuthors(settings.authors.reddit.join("\n"));
  }, [settings]);
  async function perform(key: string, action: () => Promise<void>) {
    setBusy(key);
    try {
      await action();
      await reloadConnections();
    } catch (error) {
      tell(errorMessage(error));
    } finally {
      setBusy("");
    }
  }
  async function saveDraft() {
    if (!draft) return;
    await save({
      ...draft,
      keywords: splitList(keywords),
      authors: {
        x: splitList(xAuthors).map((v) => v.replace(/^@/, "")),
        reddit: splitList(redditAuthors).map((v) =>
          v.replace(/^(?:u\/|@)/, ""),
        ),
      },
      llm: { ...draft.llm, api_key: llmKey || undefined },
    });
    setLlmKey("");
    tell("工作区设置已保存。");
  }
  async function authorizeReddit() {
    const popup = window.open(
      "about:blank",
      "radar-reddit-login",
      "width=680,height=760",
    );
    try {
      if (clientId.trim())
        await api(
          "/connections/reddit/config",
          json("POST", {
            client_id: clientId.trim(),
            client_secret: clientSecret.trim(),
            redirect_uri:
              "http://localhost:8787/api/connections/reddit/callback",
          }),
        );
      const result = await api<{ url: string }>(
        "/connections/reddit/authorize",
      );
      if (popup) popup.location.href = result.url;
      else window.location.href = result.url;
      setClientSecret("");
      onAuth();
      tell("请在 Reddit 授权页面完成登录。");
    } catch (error) {
      popup?.close();
      throw error;
    }
  }
  function updateDraft(field: keyof Settings, value: unknown) {
    setDraft((previous) =>
      previous ? ({ ...previous, [field]: value } as Settings) : previous,
    );
  }
  const xState = connections.x?.state || "disconnected";
  const redditState = connections.reddit?.state || "disconnected";
  const configuredLlm =
    typeof settings?.llm.api_key === "object" &&
    settings.llm.api_key.configured;

  return (
    <section className="settings-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">个人工作区</div>
          <h1>来源与账号</h1>
        </div>
        <button className="secondary-button" onClick={back}>
          <BookOpen size={16} />
          返回资讯
        </button>
      </div>
      <div className="settings-tabs" role="tablist" aria-label="设置分类">
        <button
          role="tab"
          aria-selected={tab === "accounts"}
          className={tab === "accounts" ? "active" : ""}
          onClick={() => setTab("accounts")}
        >
          账号连接
        </button>
        <button
          role="tab"
          aria-selected={tab === "preferences"}
          className={tab === "preferences" ? "active" : ""}
          onClick={() => setTab("preferences")}
        >
          关键词与加工
        </button>
        <button
          role="tab"
          aria-selected={tab === "feeds"}
          className={tab === "feeds" ? "active" : ""}
          onClick={() => setTab("feeds")}
        >
          RSS 来源
        </button>
      </div>
      {tab === "accounts" ? (
        <div className="settings-content">
          <section className="connection-panel">
            <div className="connection-heading">
              <div className="connection-title">
                <SourceMark source="x" />
                <div>
                  <h2>X</h2>
                  <p>关键词、关注博主、Following 和 For You</p>
                </div>
              </div>
              <ConnectionBadge
                state={xState}
                username={connections.x?.username}
              />
            </div>
            <div className="connection-body">
              <p>在独立浏览器窗口中登录自己的账号，本站不接收你的 X 密码。</p>
              {connections.x?.message && (
                <div
                  className={`connection-message ${xState === "error" ? "error" : ""}`}
                >
                  {connections.x.message}
                </div>
              )}
              <div className="connection-actions">
                <button
                  className="primary-button"
                  disabled={!!busy || xState === "connecting"}
                  onClick={() =>
                    void perform("x-login", async () => {
                      const response = await api<Connection>(
                        "/connections/x/login",
                        json("POST"),
                      );
                      tell(
                        response.message ||
                          "已打开登录窗口，请在浏览器中完成登录。",
                      );
                    })
                  }
                >
                  {busy === "x-login" || xState === "connecting" ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <ExternalLink size={16} />
                  )}
                  {xState === "connecting"
                    ? "等待浏览器登录"
                    : xState === "connected"
                      ? "重新登录 X"
                      : "在浏览器登录 X"}
                </button>
                {xState === "connected" && (
                  <button
                    className="secondary-button"
                    disabled={!!busy}
                    onClick={() =>
                      void perform("x-sync", async () => {
                        const result = await api<{ count: number }>(
                          "/connections/x/following/sync",
                          json("POST"),
                        );
                        await reloadSettings();
                        tell(`已同步 ${result.count} 个关注账号。`);
                      })
                    }
                  >
                    <UsersRound size={16} />
                    同步关注名单
                  </button>
                )}
                {xState !== "disconnected" && (
                  <button
                    className="quiet-button danger-text"
                    disabled={!!busy}
                    onClick={() =>
                      void perform("x-disconnect", async () => {
                        await api("/connections/x", json("DELETE"));
                        tell("X 连接已移除。");
                      })
                    }
                  >
                    断开连接
                  </button>
                )}
              </div>
              <details className="advanced-settings">
                <summary>使用已有登录会话</summary>
                <p className="text-note">
                  如果浏览器登录不可用，可以导入你自己导出的 Cookie
                  JSON。会话只保存到本机。
                </p>
                <label className="field">
                  <span>Cookie JSON</span>
                  <textarea
                    rows={4}
                    value={cookies}
                    onChange={(event) => setCookies(event.target.value)}
                    placeholder="粘贴 Cookie JSON（需要 auth_token 与 ct0）"
                    autoComplete="off"
                    spellCheck={false}
                  />
                </label>
                <button
                  className="secondary-button"
                  disabled={!!busy || !cookies.trim()}
                  onClick={() =>
                    void perform("x-cookie", async () => {
                      const result = await api<Connection>(
                        "/connections/x/cookies",
                        json("POST", { cookies }),
                      );
                      setCookies("");
                      tell(result.message || "登录会话已保存。");
                    })
                  }
                >
                  保存并验证会话
                </button>
              </details>
            </div>
          </section>
          <section className="connection-panel">
            <div className="connection-heading">
              <div className="connection-title">
                <SourceMark source="reddit" />
                <div>
                  <h2>Reddit</h2>
                  <p>关键词、订阅社区、指定作者和账号 API 首页</p>
                </div>
              </div>
              <ConnectionBadge
                state={redditState}
                username={connections.reddit?.username}
              />
            </div>
            <div className="connection-body">
              <p>
                通过 Reddit 授权连接账号。首次使用需要填写已获 API
                访问权限的应用信息。
              </p>
              {connections.reddit?.message && (
                <div
                  className={`connection-message ${redditState === "error" ? "error" : ""}`}
                >
                  {connections.reddit.message}
                </div>
              )}
              <div className="form-grid">
                <label className="field">
                  <span>Client ID</span>
                  <input
                    value={clientId}
                    onChange={(event) => setClientId(event.target.value)}
                    placeholder={
                      connections.reddit?.configured ||
                      connections.reddit?.client_id_configured
                        ? "已配置，留空沿用"
                        : "填写 Reddit 应用 Client ID"
                    }
                    autoComplete="off"
                  />
                </label>
                <label className="field">
                  <span>
                    Client Secret <small>Installed app 可留空</small>
                  </span>
                  <input
                    type="password"
                    value={clientSecret}
                    onChange={(event) => setClientSecret(event.target.value)}
                    placeholder="填写应用密钥"
                    autoComplete="new-password"
                  />
                </label>
              </div>
              <div className="callback-note">
                应用回调地址：
                <code>
                  http://localhost:8787/api/connections/reddit/callback
                </code>
                <button
                  className="text-button"
                  onClick={() => {
                    void navigator.clipboard
                      .writeText(
                        "http://localhost:8787/api/connections/reddit/callback",
                      )
                      .then(() => tell("回调地址已复制。"));
                  }}
                >
                  复制
                </button>
              </div>
              <div className="connection-actions">
                <button
                  className="primary-button"
                  disabled={
                    !!busy ||
                    (!clientId.trim() &&
                      !connections.reddit?.configured &&
                      !connections.reddit?.client_id_configured &&
                      redditState !== "connected")
                  }
                  onClick={() => void perform("reddit-login", authorizeReddit)}
                >
                  {busy === "reddit-login" ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <ExternalLink size={16} />
                  )}
                  登录并授权 Reddit
                </button>
                {redditState === "connected" && (
                  <button
                    className="secondary-button"
                    disabled={!!busy}
                    onClick={() =>
                      void perform("reddit-sync", async () => {
                        const result = await api<{ count: number }>(
                          "/connections/reddit/following/sync",
                          json("POST"),
                        );
                        await reloadSettings();
                        tell(`已同步 ${result.count} 项订阅。`);
                      })
                    }
                  >
                    同步订阅
                  </button>
                )}
                {redditState === "connected" && (
                  <button
                    className="quiet-button danger-text"
                    disabled={!!busy}
                    onClick={() =>
                      void perform("reddit-disconnect", async () => {
                        await api("/connections/reddit", json("DELETE"));
                        tell("Reddit 连接已移除。");
                      })
                    }
                  >
                    断开连接
                  </button>
                )}
              </div>
              <p className="text-note">
                Reddit 的 API Best
                首页与网页上的个性化推荐可能不同。读取作者投稿时，不要求含有关键词。
              </p>
              <a
                className="subtle-link"
                href="https://www.reddit.com/prefs/apps"
                target="_blank"
                rel="noopener noreferrer"
              >
                查看 Reddit 应用设置
                <ExternalLink size={12} />
              </a>
            </div>
          </section>
          {draft && (
            <section className="connection-panel">
              <div className="connection-heading">
                <div className="connection-title">
                  <Rss size={23} />
                  <div>
                    <h2>
                      RSSHub <span className="optional-label">可选</span>
                    </h2>
                    <p>接入已经运行的 RSSHub 实例</p>
                  </div>
                </div>
              </div>
              <div className="connection-body">
                <label className="field">
                  <span>RSSHub 地址</span>
                  <input
                    type="url"
                    value={draft.rsshub_url || ""}
                    onChange={(event) =>
                      updateDraft("rsshub_url", event.target.value)
                    }
                    placeholder="http://127.0.0.1:1200"
                  />
                </label>
                <p className="text-note">
                  用于 X 等网站的 RSS 路由。个人首页需要在 RSSHub
                  中配置本人的登录会话；未配置时使用上方 X 连接。
                </p>
                <button
                  className="secondary-button"
                  disabled={!!busy}
                  onClick={() => void perform("save-rsshub", saveDraft)}
                >
                  保存地址
                </button>
              </div>
            </section>
          )}
        </div>
      ) : !draft ? (
        <div className="empty-state">
          <LoaderCircle className="spin" size={25} />
          <p>正在读取工作区配置…</p>
          <button
            className="secondary-button"
            onClick={() =>
              void reloadSettings().catch((error) => tell(errorMessage(error)))
            }
          >
            重新读取
          </button>
        </div>
      ) : tab === "preferences" ? (
        <div className="settings-content">
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>研究关键词</h2>
                <p>保存你的研究方向；搜索时仍可输入任何关键词。</p>
              </div>
            </div>
            <div className="connection-body">
              <label className="field">
                <span>关键词，每行一个</span>
                <textarea
                  value={keywords}
                  onChange={(event) => setKeywords(event.target.value)}
                  rows={6}
                  placeholder="宏观\n加密货币\n美股\n港股\nA股\n黄金"
                />
              </label>
            </div>
          </section>
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>关注博主</h2>
                <p>这里的作者内容会独立收录，不强制匹配关键词。</p>
              </div>
            </div>
            <div className="connection-body form-grid">
              <label className="field">
                <span>X 用户名，每行一个</span>
                <textarea
                  rows={5}
                  value={xAuthors}
                  onChange={(event) => setXAuthors(event.target.value)}
                  placeholder="用户名，不需要 @"
                />
              </label>
              <label className="field">
                <span>Reddit 用户名，每行一个</span>
                <textarea
                  rows={5}
                  value={redditAuthors}
                  onChange={(event) => setRedditAuthors(event.target.value)}
                  placeholder="用户名，不需要 u/"
                />
              </label>
            </div>
          </section>
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>自动更新</h2>
                <p>网站服务运行期间，按设定的间隔更新研究关键词。</p>
              </div>
            </div>
            <div className="connection-body">
              <label className="field compact-field">
                <span>更新间隔</span>
                <select
                  value={draft.auto_refresh_minutes}
                  onChange={(event) =>
                    updateDraft(
                      "auto_refresh_minutes",
                      Number(event.target.value),
                    )
                  }
                >
                  <option value={0}>手动更新</option>
                  <option value={15}>每 15 分钟</option>
                  <option value={30}>每 30 分钟</option>
                  <option value={60}>每 1 小时</option>
                  <option value={240}>每 4 小时</option>
                </select>
              </label>
            </div>
          </section>
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>
                  AI 整理 <span className="optional-label">可选</span>
                </h2>
                <p>不启用时展示原文摘录；启用后可生成中文摘要。</p>
              </div>
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={draft.llm.enabled}
                  onChange={(event) =>
                    updateDraft("llm", {
                      ...draft.llm,
                      enabled: event.target.checked,
                    })
                  }
                />
                <span>启用</span>
              </label>
            </div>
            <div className="connection-body">
              <div className="form-grid">
                <label className="field">
                  <span>兼容 API 地址</span>
                  <input
                    value={draft.llm.base_url || ""}
                    onChange={(event) =>
                      updateDraft("llm", {
                        ...draft.llm,
                        base_url: event.target.value,
                      })
                    }
                    placeholder="https://api.openai.com/v1"
                  />
                </label>
                <label className="field">
                  <span>模型名称</span>
                  <input
                    value={draft.llm.model || ""}
                    onChange={(event) =>
                      updateDraft("llm", {
                        ...draft.llm,
                        model: event.target.value,
                      })
                    }
                    placeholder="填写你使用的模型名称"
                  />
                </label>
              </div>
              <label className="field">
                <span>
                  API Key{" "}
                  <small>
                    {configuredLlm ? "已保存，留空沿用" : "本地模型服务可留空"}
                  </small>
                </span>
                <input
                  type="password"
                  value={llmKey}
                  onChange={(event) => setLlmKey(event.target.value)}
                  placeholder={configuredLlm ? "已保存" : "输入 API Key"}
                  autoComplete="new-password"
                />
              </label>
              <p className="text-note">
                启用后，生成摘要会将对应帖子的文本发送到你配置的服务。
              </p>
            </div>
          </section>
          <div className="settings-save-row">
            <button
              className="primary-button"
              disabled={!!busy}
              onClick={() => void perform("save-preferences", saveDraft)}
            >
              {busy === "save-preferences" ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Check size={16} />
              )}
              保存设置
            </button>
          </div>
        </div>
      ) : (
        <div className="settings-content">
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>订阅来源</h2>
                <p>公开新闻、机构公告和博客，与账号信息流一起整理。</p>
              </div>
            </div>
            <div className="feed-settings-list">
              {draft.rss_feeds.map((feed) => (
                <div className="feed-setting" key={feed.id}>
                  <label className="feed-enabled">
                    <input
                      type="checkbox"
                      checked={feed.enabled}
                      onChange={(event) =>
                        updateDraft(
                          "rss_feeds",
                          draft.rss_feeds.map((f) =>
                            f.id === feed.id
                              ? { ...f, enabled: event.target.checked }
                              : f,
                          ),
                        )
                      }
                    />
                    <span>
                      <strong>{feed.name}</strong>
                      <small>{feed.url}</small>
                    </span>
                  </label>
                  <button
                    className="icon-button"
                    aria-label={`移除 ${feed.name}`}
                    onClick={() =>
                      updateDraft(
                        "rss_feeds",
                        draft.rss_feeds.filter((f) => f.id !== feed.id),
                      )
                    }
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
            <div className="connection-body">
              <div className="form-grid">
                <label className="field">
                  <span>来源名称</span>
                  <input
                    value={newFeedName}
                    onChange={(event) => setNewFeedName(event.target.value)}
                    placeholder="例如：研究博客"
                  />
                </label>
                <label className="field">
                  <span>RSS / Atom 地址</span>
                  <input
                    type="url"
                    value={newFeedUrl}
                    onChange={(event) => setNewFeedUrl(event.target.value)}
                    placeholder="https://example.com/feed.xml"
                  />
                </label>
              </div>
              <button
                className="secondary-button"
                disabled={!newFeedName.trim() || !newFeedUrl.trim()}
                onClick={() => {
                  try {
                    const url = new URL(newFeedUrl);
                    if (!["https:", "http:"].includes(url.protocol))
                      throw new Error();
                    updateDraft("rss_feeds", [
                      ...draft.rss_feeds,
                      {
                        id: crypto.randomUUID(),
                        name: newFeedName.trim(),
                        url: url.href,
                        enabled: true,
                      },
                    ]);
                    setNewFeedName("");
                    setNewFeedUrl("");
                  } catch {
                    tell("请输入有效的 http 或 https RSS 地址。");
                  }
                }}
              >
                <Plus size={16} />
                添加来源
              </button>
            </div>
          </section>
          <div className="settings-save-row">
            <button
              className="primary-button"
              disabled={!!busy}
              onClick={() => void perform("save-feeds", saveDraft)}
            >
              <Check size={16} />
              保存来源
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function ConnectionBadge({
  state,
  username,
}: {
  state: string;
  username?: string;
}) {
  return (
    <span className={`connection-badge ${state}`}>
      {state === "connected" ? (
        <CheckCircle2 size={14} />
      ) : state === "connecting" ? (
        <LoaderCircle className="spin" size={14} />
      ) : (
        <span className="status-dot" />
      )}
      {state === "connected"
        ? username || "已连接"
        : state === "connecting"
          ? "连接中"
          : state === "error"
            ? "需要检查"
            : "未连接"}
    </span>
  );
}
