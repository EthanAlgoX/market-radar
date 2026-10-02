import { localeCode, localizeMessage, t, useLocale } from "./i18n";
import SettingsPage, { type SettingsTab } from "./SettingsPage";
import { parseWorkspaceHash, workspaceHash, workspaceHistoryMode, resolveCollectionSources, type WorkspaceTopic, type WorkspaceRoute } from "./workspaceLogic";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  lazy,
  Suspense,
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
  Sparkles,
  Sun,
  UserRound,
  UsersRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { api, getArticleContent, getDiscussion, json } from "./api";
import {
  sameOriginal,
  translatedPost,
  translationReady,
  useChineseTranslation,
} from "./useChineseTranslation";
import type {
  Channel,
  Connection,
  Discussion,
  DiscussionComment,
  Job,
  Overview,
  Post,
  Settings,
  SourceKey,
  View,
} from "./types";

const MarketWorkspace = lazy(() => import("./market/MarketWorkspace"));

const TOPICS: { id: string; name: string; icon: LucideIcon; query: string }[] =
  [
    {
      id: "all",
      name: "全部资讯",
      icon: Layers3,
      query: "financial markets OR cryptocurrency OR US stocks OR gold",
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
const errorMessage = (error: unknown) =>
  error instanceof Error ? localizeMessage(error.message) : localizeMessage("暂时无法完成，请重试。");
const activeJob = (status?: string) => status === "queued" || status === "running";
const webUrl = (value?: string | null) => {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
};
const jobOutcome = (job: Job) =>
  job.status === "failed"
    ? localizeMessage("本次采集失败，已取得的内容仍保留。请查看来源说明。")
    : job.status === "partial"
      ? t(`部分采集完成，新增 ${job.added ?? 0} 条；请查看未完成来源。`, `Partly collected: ${job.added ?? 0} new items. Check unfinished sources.`)
      : t(`采集完成，新增 ${job.added ?? 0} 条信息。`, `Collection complete: ${job.added ?? 0} new items.`);

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
  if (!value) return localizeMessage("时间未知");
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return localizeMessage("时间未知");
  if (full)
    return date.toLocaleString(localeCode(), {
      timeZone: "Asia/Shanghai",
      hour12: false,
    });
  const minutes = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (minutes >= 0 && minutes < 1) return localizeMessage("刚刚");
  if (minutes >= 1 && minutes < 60) return t(`${minutes} 分钟前`, `${minutes} min ago`);
  if (minutes >= 60 && minutes < 1440)
    return t(`${Math.floor(minutes / 60)} 小时前`, `${Math.floor(minutes / 60)}h ago`);
  return date.toLocaleDateString(localeCode(), {
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
  const { locale, setLocale } = useLocale();
  const [initialRoute] = useState(() => parseWorkspaceHash(window.location.hash));
  const [page, setPage] = useState<"feed" | "market" | "settings">(initialRoute.page);
  const [marketOpened, setMarketOpened] = useState(initialRoute.page === "market");
  const currentPage = useRef(page);
  currentPage.current = page;
  const [settingsTab, setSettingsTab] = useState<SettingsTab>(initialRoute.settingsTab);
  const [topic, setTopic] = useState(initialRoute.topic);
  const [view, setView] = useState<View>(initialRoute.view);
  const [query, setQuery] = useState(initialRoute.q);
  const [source, setSource] = useState(initialRoute.source);
  const [filter, setFilter] = useState(initialRoute.q);
  const [sort, setSort] = useState(initialRoute.sort);
  const [configError, setConfigError] = useState("");
  const [configLoading, setConfigLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const routeInitialized = useRef(false);
  const settingsReturn = useRef<"feed" | "market">("feed");
  const [items, setItems] = useState<Post[]>([]);
  const [marketRelated, setMarketRelated] = useState<Post[]>([]);
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
  const [jobPollError, setJobPollError] = useState("");
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
    setMarketRelated((previous) => previous.map(merge));
    setSelected((previous) => (previous ? merge(previous) : previous));
  }, []);
  const chinese = useChineseTranslation(page === "market" ? marketRelated : page === "feed" ? items : [], applyTranslations);
  const translationUnconfigured = chinese.chinese && chinese.configuration?.configured === false;
  const openSettings = (tab: SettingsTab = "accounts") => {
    if (page !== "settings") settingsReturn.current = page;
    setPage("settings"); setSettingsTab(tab); setSelected(null); setMobileMenu(false);
  };
  const openTranslationSettings = () => openSettings("translation");
  const pickView = (next: View) => {
    setPage("feed"); setView(next); setTopic("all"); setSource("all");
    setFilter(""); setSelected(null); setMobileMenu(false);
  };
  useEffect(() => {
    const restore = () => {
      const route = parseWorkspaceHash(window.location.hash);
      const canonical = workspaceHash(route);
      if (window.location.hash !== canonical) window.history.replaceState({}, "", canonical);
      if (route.page === "settings" && currentPage.current !== "settings") settingsReturn.current = currentPage.current;
      setPage(route.page); setView(route.view); setTopic(route.topic);
      setSettingsTab(route.settingsTab); setFilter(route.q); setSource(route.source); setSort(route.sort);
      setSelected(null); setMobileMenu(false);
    };
    window.addEventListener("hashchange", restore);
    window.addEventListener("popstate", restore);
    return () => { window.removeEventListener("hashchange", restore); window.removeEventListener("popstate", restore); };
  }, []);
  useEffect(() => { if (page === "market") setMarketOpened(true); }, [page]);
  useEffect(() => {
    const route = { page, view, topic, settingsTab, q: filter, source, sort };
    const mode = workspaceHistoryMode(window.location.hash, route, !routeInitialized.current);
    routeInitialized.current = true;
    if (mode === "replace") window.history.replaceState({}, "", workspaceHash(route));
    else if (mode === "push") window.history.pushState({}, "", workspaceHash(route));
  }, [page, view, topic, settingsTab, filter, source, sort]);
  useEffect(() => {
    if (!mobileMenu) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebarRef.current?.querySelector<HTMLElement>("a[href],button")?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileMenu(false);
      if (event.key !== "Tab" || !sidebarRef.current) return;
      const controls = Array.from(sidebarRef.current.querySelectorAll<HTMLElement>("a[href],button:not(:disabled)"));
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !sidebarRef.current.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("keydown", close); document.body.style.overflow = previousOverflow; if (previousFocus?.isConnected) previousFocus.focus(); };
  }, [mobileMenu]);
  useEffect(() => {
    document.documentElement.lang = localeCode();
    document.title = t("交易雷达 · Market Radar", "Market Radar · Trading research");
  }, [locale]);
  const receiveMarketNews = useCallback((posts: Post[]) => {
    setMarketRelated((previous) => posts.map((post) => {
      const cached = previous.find((item) => sameOriginal(item, post));
      return cached?.translation && !post.translation ? { ...post, translation: cached.translation } : post;
    }));
  }, []);
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
      if (!append) setLoading(true); else setLoadingMore(true);
      const parameters = new URLSearchParams({
        limit: "60",
        offset: append ? String(itemCount.current) : "0",
        sort,
      });
      if (topic !== "all") parameters.set("topic", topic);
      if (source !== "all") parameters.set("source", source);
      if (view === "bookmarked") parameters.set("bookmarked", "true");
      else if (view !== "search") parameters.set("channel", view);
      if (filter.trim()) parameters.set("q", filter.trim());
      try {
        const result = await api<{ items: Post[]; total: number }>(
          `/items?${parameters}`,
        );
        if (sequence !== fetchSequence.current) return;
        setItems((previous) =>
          append ? [...previous, ...result.items.filter((item) => !previous.some((entry) => entry.id === item.id))] : result.items,
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
        if (sequence === fetchSequence.current) { setLoading(false); setLoadingMore(false); }
      }
    },
    [topic, source, view, filter, sort],
  );

  const loadWorkspace = useCallback(async () => {
    setConfigLoading(true);
    const results = await Promise.allSettled([loadOverview(), loadSettings(), loadConnections()]);
    const failures = results.filter((result) => result.status === "rejected");
    setConfigError(failures.length ? t("工作区配置未能完整读取，请重试。已收录资讯仍可查看。", "Workspace configuration could not be fully loaded. Retry; collected news remains available.") : "");
    setConfigLoading(false);
  }, [loadOverview, loadSettings, loadConnections]);
  useEffect(() => {
    void loadWorkspace();
    const params = new URLSearchParams(window.location.search);
    if (params.get("connection") === "reddit") {
      setPage("settings");
      tell(
        params.get("status") === "connected"
          ? localizeMessage("Reddit 已授权，可以拉取关注内容。")
          : params.get("status") === "cancelled"
            ? localizeMessage("Reddit 授权已取消。")
            : localizeMessage("Reddit 授权未完成，请检查应用信息后重试。"),
      );
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [loadWorkspace, tell]);
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
            tell(localizeMessage("Reddit 连接成功。"));
          }
        })
        .catch(() => {});
    }, 2500);
    return () => clearInterval(timer);
  }, [connections.x?.state, pendingAuth, loadConnections, tell]);
  useEffect(() => {
    if (!job || !activeJob(job.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      let keepPolling = true;
      try {
        const current = await api<Job>(`/jobs/${job.id}`);
        if (cancelled) return;
        setJob(current);
        setJobPollError("");
        keepPolling = activeJob(current.status);
        if (
          !activeJob(current.status) &&
          !completeJobs.current.has(current.id)
        ) {
          completeJobs.current.add(current.id);
          tell(jobOutcome(current));
          await Promise.allSettled([
            loadItems(),
            loadOverview(),
            loadConnections(),
          ]);
        }
      } catch (error) {
        if (!cancelled) setJobPollError(errorMessage(error));
      } finally {
        if (!cancelled && keepPolling) timer = setTimeout(() => void tick(), 1200);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [job?.id, job?.status, loadItems, loadOverview, loadConnections, tell]);

  async function collect(customQuery?: string, customChannel?: Channel) {
    const channel = customChannel || (view === "bookmarked" ? "search" : view);
    const text = customQuery ?? query;
    const personalSources = [
      ...(connections.x?.state === "connected"
        ? ["x"]
        : []),
      ...(connections.reddit?.state === "connected" ? ["reddit"] : []),
    ];
    const rssSources = settings?.rss_feeds.some((feed) => feed.enabled)
      ? ["rss"]
      : [];
    if (channel === "search" && !text.trim()) {
      tell(localizeMessage("请输入要搜集的关键词。"));
      return;
    }
    if (
      channel === "recommended" && !personalSources.length
    ) {
      setPage("settings");
      setSettingsTab("accounts");
      tell(localizeMessage("先连接 X 或 Reddit，再拉取账号推荐流。RSSHub 地址尚不能证明本人首页可用。"));
      return;
    }
    const sources = resolveCollectionSources(channel, connections, rssSources.length > 0);
    if (!sources.length) {
      openSettings("accounts");
      tell(t("请先连接账号或启用订阅。", "Connect an account or enable a subscription first."));
      return;
    }
    setStarting(true);
    setJobPollError("");
    if (customQuery) setQuery(customQuery);
    if (view === "bookmarked" || customChannel) setView(channel);
    setTopic("all"); setSource("all");
    setFilter(channel === "search" ? text.trim() : "");
    try {
      const current = await api<Job>(
        "/collect",
        json("POST", {
          query: channel === "search" ? text.trim() : "",
          channel,
          topic: undefined,
          sources,
        }),
      );
      setJob(current);
      if (!activeJob(current.status)) {
        await Promise.allSettled([loadItems(), loadOverview()]);
        completeJobs.current.add(current.id);
        tell(jobOutcome(current));
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
  function pickTopic(id: WorkspaceTopic) {
    setTopic(id);
    setPage("feed");
    setSelected(null);
    setFilter("");
    setMobileMenu(false);
    setView("search"); setSource("all");
  }
  const busy = starting || activeJob(job?.status);
  const counts = overview?.counts;
  const currentTopic = TOPICS.find((t) => t.id === topic) || TOPICS[0];
  const currentChannel = CHANNELS.find((c) => c.id === view)!;
  const availableSources =
    overview?.sources.filter((s) =>
      ["available", "connected"].includes(s.status),
    ).length || 0;
  const collectingSources = resolveCollectionSources(view === "bookmarked" ? "search" : view, connections, !!settings?.rss_feeds.some((feed) => feed.enabled));
  const hasFilters = !!filter.trim() || source !== "all" || topic !== "all";
  const channelTitle = view === "search" ? t("资讯库", "News library") : localizeMessage(currentChannel.label);
  const channelDescription = view === "following"
    ? t("关注的人与订阅，独立收录，不要求匹配关键词。", "Posts from followed people and subscriptions, collected independently of keywords.")
    : view === "recommended"
      ? t("来自已连接账号的信息流。Reddit API 首页可能与网站推荐不同。", "Feeds from connected accounts. Reddit's API homepage may differ from its website recommendations.")
      : view === "bookmarked"
        ? t("保存值得继续阅读的内容，原链接始终保留。", "Keep useful research for later, with original links intact.")
        : t("搜索公开来源，再在本机筛选、阅读和整理。", "Search public sources, then filter, read and organize them locally.");

  return (
    <div className="app-shell">
      {mobileMenu && (
        <button
          className="nav-backdrop"
          aria-label={localizeMessage("关闭导航")}
          onClick={() => setMobileMenu(false)}
        />
      )}
      <aside ref={sidebarRef} className={`sidebar ${mobileMenu ? "is-open" : ""}`} role={mobileMenu ? "dialog" : undefined} aria-modal={mobileMenu || undefined} aria-label={mobileMenu ? t("工作台导航", "Workspace navigation") : undefined}>
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
            <strong>{localizeMessage("交易雷达")}</strong>
            <small>{t("Market Radar", "Trading research")}</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="local-indicator" />{localizeMessage("个人工作区")}<span className="local-label">{localizeMessage("本地")}</span>
        </div>
        <div className="nav-caption">{t("工作台", "Workspace")}</div>
        <nav className="topic-nav primary-nav" aria-label={t("工作台导航", "Workspace navigation")}>
          {CHANNELS.map((channel) => {
            const Icon = channel.icon;
            const count = channel.id === "search" ? counts?.total : counts?.[channel.id];
            return <button key={channel.id} className={`nav-item ${page === "feed" && view === channel.id ? "active" : ""}`}
              aria-current={page === "feed" && view === channel.id ? "page" : undefined} onClick={() => pickView(channel.id)}>
              <Icon size={18} /><span>{channel.id === "search" ? t("资讯库", "News library") : localizeMessage(channel.label)}</span>
              {!!count && <span className="nav-count">{count}</span>}
            </button>;
          })}
          <button className={`nav-item market-nav ${page === "market" ? "active" : ""}`} aria-current={page === "market" ? "page" : undefined}
            onClick={() => { setPage("market"); setSelected(null); setMobileMenu(false); }}>
            <Activity size={18} /><span>{localizeMessage("行情与信号")}</span>
          </button>
        </nav>
        <div className="nav-caption nav-caption-spaced">{localizeMessage("我的关键词")}<button
            className="icon-button small"
            title={localizeMessage("编辑关键词")}
            aria-label={localizeMessage("编辑关键词")}
            onClick={() => openSettings("preferences")}
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
                  setFilter(keyword); setSource("all"); setSelected(null);
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
            onClick={() => openSettings("accounts")}
          >
            <Plug size={18} />
            <span>{t("设置", "Settings")}</span>
          </button>
          <div className="local-footer">
            <span>{localizeMessage("数据保存在这台电脑")}</span>
            <button
              className="icon-button small"
              aria-label={theme === "light" ? localizeMessage("切换深色模式") : localizeMessage("切换浅色模式")}
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? <Moon size={15} /> : <Sun size={15} />}
            </button>
          </div>
        </div>
      </aside>

      <main className="main-workspace" inert={mobileMenu}>
        <header className="topbar">
          <div className="topbar-start">
            <button
              className="icon-button mobile-nav-toggle"
              aria-label={localizeMessage("打开导航")}
              onClick={() => setMobileMenu(true)}
            >
              <Menu size={21} />
            </button>
            <span>{page === "feed" ? localizeMessage("资讯工作台") : page === "market" ? localizeMessage("行情与信号") : localizeMessage("工作区设置")}</span>
          </div>
          <div className="topbar-end">
            <button
              className="language-button interface-language-button"
              onClick={() => {
                const next = locale === "en" ? "zh" : "en";
                setLocale(next);
              }}
              aria-label={locale === "en" ? "Switch to Chinese" : "Switch to English"}
              title={t("切换界面语言", "Switch interface language")}
            >
              <Globe2 size={16} />{locale === "en" ? "中文" : "English"}
            </button>
            <button className="source-availability source-health-button" onClick={() => openSettings("health")}>
              <span className={`status-dot ${availableSources > 0 ? "success" : ""}`} />
              {t(`${availableSources} 个资讯来源可用`, `${availableSources} news sources available`)}<ChevronDown size={13} />
            </button>
          </div>
        </header>

        {configError && <div className="workspace-error" role="alert"><CircleX size={17} /><span>{configError}</span><button className="text-button" onClick={() => void loadWorkspace()}>{t("重试", "Retry")}</button></div>}
        {translationUnconfigured && page !== "settings" && <div className="translation-setup-banner" role="alert">
          <Languages size={17} />
          <span>{t("资讯的中文翻译需要配置你自己的 LLM API，当前保留原文。", "Configure your own LLM API to translate posts into Chinese. Original text is retained.")}</span>
          <button className="secondary-button" onClick={openTranslationSettings}>{t("配置 API", "Configure API")}</button>
        </div>}

        {marketOpened && <div hidden={page !== "market"}>
          <Suspense fallback={<div className="search-section" role="status">{localizeMessage("正在打开行情工作台…")}</div>}>
            <MarketWorkspace
              active={page === "market"}
              chinese={chinese.chinese}
              translationModel={chinese.model}
              translatedNews={marketRelated}
              onRelatedNews={receiveMarketNews}
              translationIssue={chinese.issue || Object.values(chinese.failures)[0] || ""}
              translationRunning={chinese.running}
              onTranslationRetry={chinese.retry}
              onSetChinese={chinese.setChinese}
              onConfigureTranslation={openTranslationSettings}
              onOpenNews={(keyword) => {
                setPage("feed");
                setTopic("all");
                setView("search");
                setSource("all");
                setFilter(keyword); setQuery(keyword); setSelected(null);
              }}
            />
          </Suspense>
        </div>}
        {page === "feed" ? (
          <>
            <section className="search-section news-heading">
              <div className="page-heading">
                <div><h1>{channelTitle}</h1><p className="page-description">{channelDescription}</p></div>
                <button className="quiet-button export-button" onClick={() => window.open("/api/export?format=json", "_blank", "noopener")}>
                  <ArrowDownToLine size={16} />{t("导出全部", "Export all")}
                </button>
              </div>
              {view === "search" && <div className="collection-panel">
                <div className="collection-heading"><strong>{t("搜索并搜集", "Search & collect")}</strong><span>{t("获取外部新内容", "Get new content from your sources")}</span></div>
                <form className="search-form" onSubmit={(event: FormEvent) => { event.preventDefault(); void collect(undefined, "search"); }}>
                  <Search className="search-leading" size={19} />
                  <input ref={searchInput} aria-label={localizeMessage("搜索关键词")} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={localizeMessage("输入关键词，如：美联储、Bitcoin、黄金…")} maxLength={500} />
                  <button className="primary-button" disabled={busy || configLoading || !!configError || !query.trim()} type="submit">
                    {busy ? <LoaderCircle size={16} className="spin" /> : <Search size={16} />}{busy ? localizeMessage("正在采集") : t("搜集资讯", "Collect news")}
                  </button>
                </form>
                <div className="collection-footer">
                  <span>{t("采集来源：", "Collect from: ")}{collectingSources.map((key) => localizeMessage(SOURCES[key])).join(" · ")}</span>
                  <button className="text-button" onClick={() => openSettings("accounts")}>{t("管理来源", "Manage sources")}<ExternalLink size={12} /></button>
                </div>
                <div className="query-shortcuts"><span>{t("快速搜索", "Quick search")}</span>{(overview?.keywords || ["Federal Reserve", "Bitcoin", "gold"]).slice(0,6).map((keyword) =>
                  <button key={keyword} onClick={() => { setQuery(keyword); searchInput.current?.focus(); }}>{keyword}</button>)}</div>
              </div>}
              {(view === "following" || view === "recommended") && <div className="personal-collection">
                <div><strong>{view === "following" ? t("同步关注来源", "Sync followed sources") : t("同步账号信息流", "Sync account feeds")}</strong>
                  <span>{collectingSources.length ? collectingSources.map((key) => localizeMessage(SOURCES[key])).join(" · ") : t("尚未连接账号", "No account connected")}</span></div>
                <button className="primary-button" disabled={busy || configLoading || !!configError} onClick={() => collectingSources.length ? void collect() : openSettings("accounts")}>
                  {busy ? <LoaderCircle size={16} className="spin" /> : collectingSources.length ? <RefreshCw size={16} /> : <Plug size={16} />}
                  {collectingSources.length ? view === "following" ? t("拉取关注", "Collect following") : t("拉取推荐", "Collect account feed") : t("连接账号", "Connect account")}
                </button>
              </div>}
            </section>
            <div className="channel-row mobile-channels"><div className="channel-tabs" role="tablist" aria-label={localizeMessage("信息类型")}>
              {CHANNELS.map((channel) => <button key={channel.id} role="tab" aria-selected={view === channel.id} className={view === channel.id ? "active" : ""} onClick={() => pickView(channel.id)}>
                {channel.id === "search" ? t("资讯库", "Library") : localizeMessage(channel.label)}
              </button>)}
            </div></div>
            {job && <JobNotice job={job} pollError={jobPollError} close={() => setJob(null)} />}
            <div
              className={`reading-workspace ${selected ? "has-selection" : ""}`}
            >
              <section className="feed-section" aria-label={localizeMessage("资讯列表")}>
                <div className="feed-toolbar">
                  <div className="library-tools">
                    <label className="filter-input"><Search size={16} /><input aria-label={localizeMessage("筛选已收录内容")} placeholder={t("搜索本地资讯库…", "Search your local library…")} value={filter} onChange={(event) => setFilter(event.target.value)} maxLength={500} />
                      {filter && <button className="icon-button small" aria-label={localizeMessage("清空筛选")} onClick={() => setFilter("")}><X size={14} /></button>}
                    </label>
                    <div className="reading-language"><span>{t("资讯语言", "Read in")}</span><button className={!chinese.chinese ? "active" : ""} aria-pressed={!chinese.chinese} onClick={() => chinese.setChinese(false)}>{t("原文", "Original")}</button><button className={chinese.chinese ? "active" : ""} aria-pressed={chinese.chinese} onClick={() => chinese.setChinese(true)}>中文</button></div>
                  </div>
                  <div className="library-filter-row">
                    <div className="feed-total"><strong>{loading ? "…" : total}</strong>{t("条已收录", "collected items")}</div>
                    <div className="feed-controls">
                      {(view === "search" || view === "bookmarked") && <label className="select-wrap"><span className="sr-only">{t("主题筛选", "Filter by topic")}</span><select value={topic} onChange={(event) => { setTopic(event.target.value as WorkspaceTopic); setSelected(null); }}>
                        {TOPICS.map((item) => <option key={item.id} value={item.id}>{item.id === "all" ? t("所有主题", "All topics") : localizeMessage(item.name)}</option>)}
                      </select><ChevronDown size={13} /></label>}
                      <label className="select-wrap"><span className="sr-only">{localizeMessage("数据来源")}</span><select value={source} onChange={(event) => { setSource(event.target.value as WorkspaceRoute["source"]); setSelected(null); }}>
                        <option value="all">{localizeMessage("所有来源")}</option>{Object.entries(SOURCES).filter(([key]) => view === "recommended" ? ["x", "reddit"].includes(key) : view === "following" ? ["x", "reddit", "rss"].includes(key) : true).map(([key,name]) => <option key={key} value={key}>{localizeMessage(name)}</option>)}
                      </select><ChevronDown size={13} /></label>
                      <label className="select-wrap sort-select"><span className="sr-only">{localizeMessage("排列方式")}</span><select value={sort} onChange={(event) => setSort(event.target.value as WorkspaceRoute["sort"])}><option value="latest">{localizeMessage("最新优先")}</option><option value="relevance">{localizeMessage("相关度")}</option></select><ChevronDown size={13} /></label>
                      <button className="icon-button small" aria-label={t("刷新本地列表", "Reload local list")} disabled={loading} onClick={() => void loadItems()}><RefreshCw size={15} className={loading ? "spin" : ""} /></button>
                    </div>
                  </div>
                  {hasFilters && <div className="active-filters"><span>{t("本地筛选", "Filtering library")}</span>{filter.trim() && <button onClick={() => setFilter("")} title={filter}>{filter}<X size={12} /></button>}{topic !== "all" && <button onClick={() => setTopic("all")}>{localizeMessage(currentTopic.name)}<X size={12} /></button>}{source !== "all" && <button onClick={() => setSource("all")}>{localizeMessage(SOURCES[source as SourceKey])}<X size={12} /></button>}<button className="clear-all" onClick={() => { setFilter(""); setSource("all"); setTopic("all"); }}>{localizeMessage("清除筛选")}</button></div>}
                  {chinese.chinese && !translationUnconfigured && <div className={`translation-notice ${chinese.issue || Object.keys(chinese.failures).length ? "has-error" : ""}`} role="status"><Languages size={14} /><span>{chinese.issue ? localizeMessage(chinese.issue) : chinese.running ? t(`正在翻译 ${chinese.completed}/${items.length}`, `Translating ${chinese.completed}/${items.length}`) : t(`中文译文 ${chinese.ready}/${items.length} 条就绪`, `Chinese translations ${chinese.ready}/${items.length} ready`)}</span>{!chinese.running && (chinese.issue || Object.keys(chinese.failures).length > 0) && <button className="text-button" onClick={chinese.retry}>{localizeMessage("重试翻译")}</button>}<button className="text-button" onClick={openTranslationSettings}>{t("API 设置", "API settings")}</button></div>}
                </div>
                {loadError ? (
                  <div className="empty-state error-state">
                    <CircleX size={29} />
                    <h2>{localizeMessage("暂时无法读取资讯")}</h2>
                    <p>{localizeMessage(loadError)}</p>
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
                    >{localizeMessage("重新连接")}</button>
                  </div>
                ) : loading ? (
                  <div className="loading-list" aria-label={localizeMessage("正在读取资讯")}>
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
                      {hasFilters
                        ? localizeMessage("没有符合筛选条件的内容")
                        : view === "following"
                          ? localizeMessage("把你关注的信息带到这里")
                          : view === "recommended"
                            ? localizeMessage("阅读为你推荐的内容")
                            : view === "bookmarked"
                              ? localizeMessage("值得留下的信息，都在这里")
                              : localizeMessage("开始收集你的交易信息")}
                    </h2>
                    <p>
                      {hasFilters
                        ? localizeMessage("调整关键词或数据来源，查看已收录的信息。")
                        : view === "following"
                          ? localizeMessage("启用 RSS 订阅或连接 X、Reddit 后拉取关注内容；即使没有关键词，也会收录。")
                          : view === "recommended"
                            ? localizeMessage("连接账号后可以拉取 X 推荐流和 Reddit API 首页。")
                            : view === "bookmarked"
                              ? localizeMessage("点击资讯旁的收藏按钮，稍后可以在这里继续阅读。")
                              : localizeMessage("从宏观、加密货币、股票和黄金开始，搜索会获取真实公开来源的最新内容。")}
                    </p>
                    {!hasFilters && view !== "bookmarked" && (
                      <button
                        className="primary-button"
                        disabled={busy}
                        onClick={() => collectingSources.length ? void collect() : openSettings("accounts")}
                      >
                        {busy ? (
                          <LoaderCircle className="spin" size={17} />
                        ) : !collectingSources.length ? (
                          <Plug size={17} />
                        ) : (
                          <Search size={17} />
                        )}
                        {!collectingSources.length
                          ? localizeMessage("连接账号")
                          : view === "following"
                          ? localizeMessage("拉取关注内容")
                          : view === "recommended"
                            ? localizeMessage("拉取推荐内容")
                            : localizeMessage("搜索最新信息")}
                      </button>
                    )}
                    {(hasFilters) && (
                      <button
                        className="quiet-button"
                        onClick={() => {
                          setFilter("");
                          setSource("all"); setTopic("all");
                        }}
                      >{localizeMessage("清除筛选")}</button>
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
                              item.bookmarked ? localizeMessage("取消收藏") : localizeMessage("收藏资讯")
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
                              <span className="unread-dot" aria-label={localizeMessage("未读")} />
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
                                  ? localizeMessage("中文译文")
                                  : chinese.failures[item.id]
                                    ? localizeMessage("翻译失败 · 原文")
                                    : chinese.running
                                      ? localizeMessage("翻译中 · 原文")
                                      : localizeMessage("暂显示原文")}
                              </span>
                            )}
                            {(item.topics || []).slice(0, 3).map((t) => (
                              <span key={t}>{localizeMessage(TOPIC_NAMES[t] || t)}</span>
                            ))}
                            {item.summary_kind === "llm" && (
                              <span className="ai-tag">
                                <Sparkles size={11} />{localizeMessage("AI 摘要")}</span>
                            )}
                          </div>
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="original-link"
                          >{localizeMessage("原文")}<ExternalLink size={12} />
                          </a>
                        </div>
                      </article>
                    ))}
                    {items.length < total && (
                      <button
                        className="load-more"
                        disabled={loadingMore}
                        onClick={() => void loadItems(true)}
                      >{loadingMore ? t("正在读取…", "Loading…") : localizeMessage("加载更多")}<ChevronDown size={16} />
                      </button>
                    )}
                  </div>
                )}
              </section>
              {selected ? (
                <ReadPane
                  key={selected.id}
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
              ) : null}
            </div>
          </>
        ) : null}
        <div hidden={page !== "settings"}>
          <SettingsPage
            settings={settings}
            connections={connections}
            sources={overview?.sources || []}
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
            onTranslationSaved={chinese.configurationChanged}
            returnPage={settingsReturn.current}
            back={() => setPage(settingsReturn.current)}
          />
        </div>
      </main>
      {toast && (
        <div className="toast" role="status">
          <CircleHelp size={18} />
          <span>{localizeMessage(toast)}</span>
          <button
            className="icon-button small"
            aria-label={localizeMessage("关闭通知")}
            onClick={() => setToast("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function coverageLabel(value: Job["progress"][number]["coverage"]) {
  if (value === "window") return localizeMessage("本次采集窗口");
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (value && typeof value === "object") {
    return Object.entries(value).map(([key, entry]) => {
      const labels: Record<string, string> = { pages: localizeMessage("页数"), items: localizeMessage("取得条数"), limit: localizeMessage("上限"), truncated: localizeMessage("是否截断"), complete: localizeMessage("是否完整") };
      return t(`${labels[key] || key}：${typeof entry === "boolean" ? (entry ? "是" : "否") : String(entry)}`, `${labels[key] || key}: ${typeof entry === "boolean" ? (entry ? "Yes" : "No") : String(entry)}`);
    }).join(" · ");
  }
  return "";
}

function JobNotice({ job, close, pollError }: { job: Job; close: () => void; pollError: string }) {
  const running = activeJob(job.status);
  return (
    <div
      className={`job-notice ${["failed", "partial"].includes(job.status) ? "has-error" : ""}`}
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
          {job.status === "queued"
            ? localizeMessage("采集任务已排队")
            : running
              ? localizeMessage("正在从各个来源收集信息")
            : job.status === "failed"
              ? localizeMessage("本次采集失败 · 已取得内容仍保留")
              : t(`${job.status === "partial" ? "部分采集完成" : "收录完成"} · 新增 ${job.added ?? 0} 条`, `${job.status === "partial" ? "Partly collected" : "Collection complete"} · ${job.added ?? 0} new items`)}
        </strong>
        {!running && (
          <button
            className="icon-button small"
            aria-label={localizeMessage("收起采集结果")}
            onClick={close}
          >
            <X size={15} />
          </button>
        )}
      </div>
      {pollError && <p className="job-poll-error">{localizeMessage("暂时无法读取进度：")}{localizeMessage(pollError)}{localizeMessage("。正在自动重试，任务结果尚未确认。")}</p>}
      {(job.progress || []).length > 0 && (
        <div className="job-sources">
          {(job.progress || []).map((p, i) => (
            <details key={`${p.source}-${i}`} className="job-source-detail">
            <summary className={`job-source ${p.status}`}>
              {p.status === "running" ? (
                <LoaderCircle size={12} className="spin" />
              ) : ["success", "completed"].includes(p.status) ? (
                <Check size={12} />
              ) : ["error", "failed"].includes(p.status) ? (
                <CircleX size={12} />
              ) : (
                <Clock3 size={12} />
              )}
              {localizeMessage(SOURCES[p.source as SourceKey] || p.source)}
              <span>{p.status === "running" ? localizeMessage("采集中") : p.status === "queued" || p.status === "pending" ? localizeMessage("待采集") :
                p.status === "retry_wait" ? localizeMessage("等待重试") : ["success", "completed"].includes(p.status) ? localizeMessage("完成") : p.status === "partial" ? localizeMessage("部分完成") :
                  ["error", "failed"].includes(p.status) ? localizeMessage("失败") : p.status === "skipped" ? localizeMessage("未采集") : p.status}</span>
              {p.count !== undefined ? t(` · ${p.count} 条`, ` · ${p.count} items`) : ""}
              <ChevronDown size={12} />
            </summary>
            <div className="job-source-body">
              <p>{localizeMessage("新增")}{p.new ?? p.added ?? "—"}{localizeMessage("· 更新")}{p.updated ?? "—"}{localizeMessage("· 重复")}{p.duplicates ?? "—"}{localizeMessage("· 重试")}{p.retries ?? "—"}</p>
              {(p.query || p.queries?.length) && <p>{localizeMessage("实际查询：")}{p.queries?.join(" / ") || p.query}</p>}
              {coverageLabel(p.coverage) && <p>{localizeMessage("采集覆盖：")}{coverageLabel(p.coverage)}</p>}
              {p.truncated && <p>{localizeMessage("达到本次采集上限，尚未覆盖全部内容。")}</p>}
              {p.message && <p>{localizeMessage(p.message)}</p>}
            </div>
            </details>
          ))}
        </div>
      )}
      {(job.errors || []).length > 0 && (
        <details className="job-errors">
          <summary>{job.errors.length}{localizeMessage("个来源需要检查")}</summary>
          {(job.errors || []).map((e, i) => (
            <p key={i}>
              <strong>{localizeMessage(SOURCES[e.source as SourceKey] || e.source)}：</strong>
              {localizeMessage(e.message)}
            </p>
          ))}
        </details>
      )}
    </div>
  );
}

function TextParagraphs({ text }: { text: string }) {
  return <>{text.split(/\n\s*\n/).filter((paragraph) => paragraph.trim()).map((paragraph, index) =>
    <p key={index} dir="auto">{paragraph}</p>)}</>;
}

function commentDepth(comment: DiscussionComment, comments: DiscussionComment[]) {
  if (typeof comment.depth === "number") return Math.min(3, Math.max(0, comment.depth));
  let parent = comment.parent_id;
  let depth = 0;
  const seen = new Set([comment.external_id]);
  while (parent && depth < 3 && !seen.has(parent)) {
    seen.add(parent);
    const ancestor = comments.find((entry) => entry.external_id === parent);
    if (!ancestor) break;
    depth += 1;
    parent = ancestor.parent_id;
  }
  return depth;
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
  const paneRef = useRef<HTMLElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  const [overlay, setOverlay] = useState(() => window.matchMedia("(max-width: 1250px)").matches);
  const [tab, setTab] = useState<"summary" | "original">("original");
  const [summarizing, setSummarizing] = useState(false);
  const [discussion, setDiscussion] = useState<Discussion | null>(null);
  const [discussionLoading, setDiscussionLoading] = useState(false);
  const [discussionError, setDiscussionError] = useState("");
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState("");
  const discussionRequest = useRef<AbortController | null>(null);
  const contentRequest = useRef<AbortController | null>(null);
  useEffect(() => () => {
    discussionRequest.current?.abort();
    contentRequest.current?.abort();
  }, []);
  useEffect(() => setTab("original"), [item.id]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1250px)");
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const change = () => { setOverlay(media.matches); document.body.style.overflow = media.matches ? "hidden" : previousOverflow; };
    change(); media.addEventListener("change", change);
    if (media.matches) paneRef.current?.querySelector<HTMLButtonElement>(".reader-close")?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (event.key === "Tab" && media.matches && paneRef.current) {
        const controls = Array.from(paneRef.current.querySelectorAll<HTMLElement>("button:not(:disabled),a[href],input,select,textarea,[tabindex='0']")).filter((element) => element.getClientRects().length > 0);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && (document.activeElement === first || !paneRef.current.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => { document.removeEventListener("keydown", handleKey); media.removeEventListener("change", change); document.body.style.overflow = previousOverflow; if (previousFocus?.isConnected) previousFocus.focus(); };
  }, []);
  async function summarize() {
    setSummarizing(true);
    try {
      update(await api<Post>(`/items/${item.id}/summarize`, json("POST")));
      tell(localizeMessage("摘要已更新。"));
    } catch (error) {
      tell(errorMessage(error));
    } finally {
      setSummarizing(false);
    }
  }
  async function loadDiscussion() {
    if (discussionLoading) return;
    const controller = new AbortController();
    discussionRequest.current = controller;
    setDiscussionLoading(true);
    setDiscussionError("");
    try {
      const result = await getDiscussion(item.id, controller.signal);
      if (!controller.signal.aborted) setDiscussion(result);
    } catch (error) {
      if (!controller.signal.aborted) setDiscussionError(errorMessage(error));
    } finally {
      if (!controller.signal.aborted) setDiscussionLoading(false);
    }
  }
  async function loadArticleContent() {
    if (contentLoading) return;
    const controller = new AbortController();
    contentRequest.current = controller;
    setContentLoading(true);
    setContentError("");
    try {
      const result = await getArticleContent(item.id, controller.signal);
      if (!controller.signal.aborted) {
        update(result);
        setTab("original");
        tell(localizeMessage("文章正文已读取，原链接已保留。"));
      }
    } catch (error) {
      if (!controller.signal.aborted) setContentError(errorMessage(error));
    } finally {
      if (!controller.signal.aborted) setContentLoading(false);
    }
  }
  const originalUrl = webUrl(item.url);
  const externalUrl = webUrl(item.external_url);
  return (
    <aside ref={paneRef} className="read-pane" role={overlay ? "dialog" : undefined} aria-modal={overlay || undefined} aria-label={localizeMessage("阅读详情")}>
      <div className="read-pane-toolbar">
        <span>{localizeMessage("阅读详情")}</span>
        <div>
          <button
            className={`icon-button ${item.bookmarked ? "is-saved" : ""}`}
            aria-label={item.bookmarked ? localizeMessage("取消收藏") : localizeMessage("收藏资讯")}
            onClick={() => patch({ bookmarked: !item.bookmarked })}
          >
            <Bookmark
              size={17}
              fill={item.bookmarked ? "currentColor" : "none"}
            />
          </button>
          <button
            className="icon-button reader-close"
            aria-label={localizeMessage("关闭阅读详情")}
            onClick={close}
          >
            {overlay ? <X size={19} /> : <PanelRightClose size={19} />}
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
        <div className="detail-link-actions">
        {originalUrl && <a
          className="secondary-button original-button"
          href={originalUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink size={15} />
          {["x", "reddit", "hackernews"].includes(item.source) ? localizeMessage("打开原始帖子") : localizeMessage("打开来源原文")}
        </a>}
        {externalUrl && externalUrl !== originalUrl && <a
          className="secondary-button original-button"
          href={externalUrl}
          target="_blank"
          rel="noopener noreferrer"
        ><ExternalLink size={15} />{localizeMessage("打开外链文章")}</a>}
        </div>
        {["rss", "news"].includes(item.source) && item.content_kind !== "extracted_html" &&
          <div className="article-content-action">
            <button className="quiet-button" disabled={contentLoading} onClick={() => void loadArticleContent()}>
              {contentLoading ? <LoaderCircle size={14} className="spin" /> : <BookOpen size={14} />}
              {contentLoading ? localizeMessage("正在读取正文") : contentError ? localizeMessage("重试读取正文") : localizeMessage("读取文章正文")}
            </button>
            {contentError && <p className="inline-error" role="alert">{localizeMessage("正文未能读取：")}{contentError}{localizeMessage("。现有摘录与原链接已保留。")}</p>}
          </div>}
        <div className="detail-tabs" role="tablist" aria-label={t("阅读方式", "Reading view")}>
          <button
            role="tab" aria-selected={tab === "summary"}
            className={tab === "summary" ? "active" : ""}
            onClick={() => setTab("summary")}
          >{localizeMessage("整理内容")}</button>
          <button
            role="tab" aria-selected={tab === "original"}
            className={tab === "original" ? "active" : ""}
            onClick={() => setTab("original")}
          >
            {chinese && translationReady(item, translationModel) ? t("中文译文", "Chinese translation") : localizeMessage("原始文本")}
          </button>
        </div>
        {chinese && !translationReady(item, translationModel) && <p className="reader-translation-state" role="status">{t("此条译文尚未就绪，当前显示原文。", "Translation is not ready for this item. Showing the original text.")}</p>}
        {item.content_kind === "extracted_html" && <p className="reader-content-kind">{t("已提取文章正文", "Extracted article text")}</p>}
        {tab === "summary" ? (
          <>
            <div className="summary-label">
              {item.summary_kind === "llm" ? (
                <>
                  <Sparkles size={14} />{localizeMessage("AI 摘要")}</>
              ) : (
                <>
                  <FileText size={14} />{localizeMessage("原文摘录")}</>
              )}
            </div>
            <div className="detail-body">
              <TextParagraphs text={previewText(display) ||
                localizeMessage("此来源只提供标题或简短文本，请打开原文阅读完整内容。")} />
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
                {summarizing ? localizeMessage("正在整理") : localizeMessage("生成 AI 摘要")}
              </button>
            )}
            <div className="detail-section">
              <h3>{localizeMessage("研究主题")}</h3>
              <div className="detail-topics">
                {item.topics.length ? (
                  item.topics.map((t) => (
                    <span key={t}>{localizeMessage(TOPIC_NAMES[t] || t)}</span>
                  ))
                ) : (
                  <span>{localizeMessage("未分类")}</span>
                )}
              </div>
            </div>
            {item.matched_keywords.length > 0 && (
              <div className="detail-section">
                <h3>{localizeMessage("命中关键词")}</h3>
                <div className="detail-keywords">
                  {item.matched_keywords.map((k) => (
                    <span key={k}>#{k}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="detail-body original-text">
              <TextParagraphs text={display.content || localizeMessage("此来源只提供标题和链接。")} />
            </div>
            <p className="text-note">
              {chinese && translationReady(item, translationModel)
                ? localizeMessage("这里是来源文本的中文译文；完整文章或讨论请查看原文。")
                : localizeMessage("这里保留的是采集时来源返回的文本，完整文章或讨论请查看原文。")}
            </p>
            {chinese && (
              <details className="original-disclosure">
                <summary>{localizeMessage("查看原始文本")}</summary>
                <div className="detail-body">
                  <TextParagraphs text={item.content || localizeMessage("此来源只提供标题和链接。")} />
                </div>
              </details>
            )}
          </>
        )}
        <details className="detail-section provenance-section">
          <summary>{localizeMessage("收录与来源")}</summary>
          <p className="detail-secondary">
            {item.channels.map((c) => localizeMessage(CHANNELS.find((v) => v.id === c)?.label || c)).join(" · ")}
            <br />{timeLabel(item.collected_at, true)}
          </p>
          {!!item.observations?.length && <ul className="observation-list">
            {item.observations.map((observation, index) => <li key={`${observation.source}-${observation.external_id}-${index}`}>
              <strong>{observation.source_name || SOURCES[observation.source as SourceKey] || observation.source || localizeMessage("来源记录")}</strong>
              {observation.author && <span>{observation.author}</span>}
              {(observation.channels?.length || observation.channel) && <span>{(observation.channels?.length ? observation.channels : [observation.channel]).map((value) => localizeMessage(CHANNELS.find((channel) => channel.id === value)?.label || value || "")).join(" · ")}</span>}
              {(observation.queries?.length || observation.query) && <p>{localizeMessage("研究查询：")}{observation.queries?.join(" / ") || observation.query}</p>}
              {observation.provider_query && observation.provider_query !== observation.query && <p>{localizeMessage("来源查询：")}{observation.provider_query}</p>}
              {(observation.collected_at || observation.observed_at) && <time>{timeLabel(observation.collected_at || observation.observed_at || null, true)}</time>}
              {webUrl(observation.url) && <a href={webUrl(observation.url)} target="_blank" rel="noopener noreferrer">{localizeMessage("查看此来源")}<ExternalLink size={12} /></a>}
            </li>)}
          </ul>}
        </details>
        {["reddit", "hackernews"].includes(item.source) && <div className="detail-section discussion-section">
          <div className="discussion-heading">
            <h3>{localizeMessage("评论讨论")}</h3>
            <button className="text-button" disabled={discussionLoading} onClick={() => void loadDiscussion()}>
              {discussionLoading ? <LoaderCircle size={13} className="spin" /> : <MessageSquare size={13} />}
              {discussionLoading ? localizeMessage("正在加载") : discussionError ? localizeMessage("重试评论") : discussion ? localizeMessage("刷新评论") : localizeMessage("加载评论")}
            </button>
          </div>
          {!discussion && !discussionError && !discussionLoading && <p className="text-note">{localizeMessage("点击后从来源读取部分评论；完整讨论可打开原始帖子查看。")}</p>}
          {discussionError && <p className="inline-error" role="alert">{localizeMessage("评论未能加载：")}{localizeMessage(discussionError)}{localizeMessage("。可重试或打开原始帖子。")}</p>}
          {discussionLoading && <p className="text-note" role="status">{localizeMessage("正在读取来源评论…")}</p>}
          {discussion && <>
            {discussion.message && <p className="text-note">{discussion.message}</p>}
            {!discussion.items.length && <p className="text-note">{localizeMessage("本次没有取得可显示的评论。请查看原始帖子。")}</p>}
            <ol className="discussion-list">
              {discussion.items.map((comment) => <li key={comment.external_id} style={{ marginInlineStart: `${commentDepth(comment, discussion.items) * 10}px` }}>
                <div className="comment-meta"><strong>{comment.author || localizeMessage("匿名作者")}</strong><time>{timeLabel(comment.published_at)}</time></div>
                <div className="comment-content"><TextParagraphs text={comment.content || localizeMessage("此评论没有可用文本。")} /></div>
                <div className="comment-footer">{comment.score !== undefined && <span>{comment.score.toLocaleString()}{localizeMessage("分")}</span>}
                  {webUrl(comment.url) && <a href={webUrl(comment.url)} target="_blank" rel="noopener noreferrer">{localizeMessage("原评论")}<ExternalLink size={11} /></a>}
                </div>
              </li>)}
            </ol>
          </>}
        </div>}
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
                    ? localizeMessage("讨论")
                    : k === "likes"
                      ? localizeMessage("赞")
                      : k === "reposts"
                        ? localizeMessage("转发")
                        : k}
                </span>
              ))}
          </div>
        )}
      </div>
    </aside>
  );
}
