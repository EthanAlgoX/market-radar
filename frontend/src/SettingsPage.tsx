import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, Check, CheckCircle2, ExternalLink, LoaderCircle, Plus, Rss, Trash2, UsersRound } from "lucide-react";
import { api, getSourcePresets, json } from "./api";
import { localeCode, localizeMessage, t, useLocale } from "./i18n";
import TranslationSettings from "./TranslationSettings";
import { editorFromSettings, mergeSettingsEditor, scopeDirty, settingsPayload, type SettingsEditor, type SaveScope } from "./settingsDraft";
import type { Connection, FeedSource, Settings, SourcePresets, SourceState } from "./types";
import "./settings.css";
const errorMessage = (error: unknown) => error instanceof Error ? localizeMessage(error.message) : t("暂时无法完成，请重试。", "Unable to complete this action. Please retry.");
const webUrl = (value?: string | null) => { if (!value) return undefined; try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : undefined; } catch { return undefined; } };
function sourceRequirements(requirements: string[]) {
  const labels: Record<string, string> = {
    browser_runtime: localizeMessage("RSSHub 实例需能运行浏览器"),
    XUEQIU_COOKIES: localizeMessage("在实例中配置本人的雪球登录 Cookie"),
    isolated_personal_instance: localizeMessage("使用仅本人访问的独立 RSSHub 实例"),
    declared_contact_user_agent: localizeMessage("请求中需声明可联系的身份信息"),
    access_validation: localizeMessage("启用前需验证访问是否可用"),
  };
  return requirements.map((requirement) => labels[requirement] || requirement).join("；");
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

function SourceHealth({ sources }: { sources: SourceState[] }) {
  return <div className="source-health-list">
    {sources.map((s) => <div className="source-health" key={s.source}>
      <div className="source-status-row">
        <SourceMark source={s.source} />
        <span>{localizeMessage(s.name)}</span>
        <span className={`source-status ${s.status}`}>
          {s.status === "connected" ? localizeMessage("已连接") : s.status === "available" ? localizeMessage("可用") :
            s.status === "partial" ? localizeMessage("部分可用") : s.status === "rate_limited" ? localizeMessage("限流中") :
            ["error", "failed"].includes(s.status) ? localizeMessage("需检查") : s.status === "connecting" ? localizeMessage("连接中") :
              s.status === "disabled" ? localizeMessage("未启用") : ["disconnected", "unconfigured", "not_configured"].includes(s.status) ? localizeMessage("未连接") : localizeMessage("待检查")}
        </span>
      </div>
      <div className="source-health-meta">
        <span>{localizeMessage("最近成功：")}{s.last_success_at ? timeLabel(s.last_success_at, true) : localizeMessage("尚无成功记录")}</span>
        {s.last_attempt_at && <span>{localizeMessage("最近尝试：")}{timeLabel(s.last_attempt_at, true)}</span>}
        {s.message && <p>{localizeMessage(s.message)}</p>}
      </div>
    </div>)}
    {!sources.length && <p className="text-note">{localizeMessage("来源状态尚未加载。")}</p>}
  </div>;
}

export type SettingsTab = "accounts" | "preferences" | "feeds" | "translation" | "health";
export default function SettingsPage({
  settings,
  connections,
  sources,
  tab,
  setTab,
  save,
  reloadConnections,
  reloadSettings,
  tell,
  onAuth,
  onTranslationSaved,
  returnPage = "feed",
  back,
}: {
  settings: Settings | null;
  connections: Record<string, Connection>;
  sources: SourceState[];
  tab: SettingsTab;
  setTab: (tab: SettingsTab) => void;
  save: (value: unknown) => Promise<void>;
  reloadConnections: () => Promise<unknown>;
  reloadSettings: () => Promise<void>;
  tell: (message: string) => void;
  onAuth: () => void;
  onTranslationSaved: () => Promise<void>;
  returnPage?: "feed" | "market";
  back: () => void;
}) {
  useLocale();
  const [editor, setEditor] = useState<SettingsEditor | null>(null);
  const previousSettings = useRef<Settings | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [translationDirty, setTranslationDirty] = useState(false);
  const draft = editor && settings ? { ...settings, rss_feeds: editor.feeds, rsshub_url: editor.rsshubUrl, auto_refresh_minutes: editor.refreshMinutes, llm: editor.llm } : null;
  const keywords = editor?.keywords || "";
  const xAuthors = editor?.xAuthors || "";
  const redditAuthors = editor?.redditAuthors || "";
  const llmKey = editor?.llmKey || "";
  function updateEditor<K extends keyof SettingsEditor>(field: K, value: SettingsEditor[K]) { setEditor(previous => previous ? { ...previous, [field]: value } : previous); setNotice(""); }
  const setKeywords = (value: string) => updateEditor("keywords", value);
  const setXAuthors = (value: string) => updateEditor("xAuthors", value);
  const setRedditAuthors = (value: string) => updateEditor("redditAuthors", value);
  const setLlmKey = (value: string) => updateEditor("llmKey", value);
  const [cookies, setCookies] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [newFeedName, setNewFeedName] = useState("");
  const [newFeedUrl, setNewFeedUrl] = useState("");
  const [busy, setBusy] = useState("");
  const [presets, setPresets] = useState<SourcePresets | null>(null);
  const [presetsLoading, setPresetsLoading] = useState(false);
  const [presetsError, setPresetsError] = useState("");
  const presetRequest = useRef<AbortController | null>(null);
  const loadPresets = useCallback(async () => {
    presetRequest.current?.abort();
    const controller = new AbortController();
    presetRequest.current = controller;
    setPresetsLoading(true);
    setPresetsError("");
    try {
      const result = await getSourcePresets(controller.signal);
      if (!controller.signal.aborted) setPresets(result);
    } catch (error) {
      if (!controller.signal.aborted) setPresetsError(errorMessage(error));
    } finally {
      if (!controller.signal.aborted) setPresetsLoading(false);
    }
  }, []);
  useEffect(() => {
    if (tab === "feeds" && !presets && !presetsLoading && !presetsError) void loadPresets();
  }, [tab, presets, presetsLoading, presetsError, loadPresets]);
  useEffect(() => () => presetRequest.current?.abort(), []);
  useEffect(() => {
    if (!settings) return;
    const previous = previousSettings.current;
    setEditor(current => current && previous ? mergeSettingsEditor(current, previous, settings) : editorFromSettings(settings));
    previousSettings.current = settings;
  }, [settings]);
  const dirty = (scope: SaveScope) => !!(editor && settings && scopeDirty(editor, settings, scope));
  const pending = (["preferences", "feeds", "rsshub"] as const).filter(dirty);
  async function perform(key: string, action: () => Promise<void>) {
    setBusy(key); setError(""); setNotice("");
    try { await action(); if (!key.startsWith("save-")) await reloadConnections(); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }
  async function saveSection(scope: SaveScope) {
    if (!editor) return;
    if (scope === "preferences") {
      if (editor.llm.enabled && (!editor.llm.base_url.trim() || !editor.llm.model.trim())) throw new Error(t("启用 AI 摘要前，请填写摘要 API 地址和模型。", "Add the summary API URL and model before enabling AI summaries."));
      if (configuredLlm && editor.llm.base_url.trim().replace(/\/+$/, "") !== (settings?.llm.base_url || "").trim().replace(/\/+$/, "") && !editor.llmKey.trim()) throw new Error(t("更换摘要 API 地址时，请填写该服务的 API key。", "Enter the new provider's API key when changing the summary API URL."));
    }
    await save(settingsPayload(editor, scope));
    if (scope === "preferences") setLlmKey("");
    setNotice(scope === "feeds" ? t("RSS 来源已保存。", "RSS feeds saved.") : scope === "rsshub" ? t("RSSHub 地址已保存。", "RSSHub URL saved.") : t("研究设置已保存。", "Research settings saved."));
  }
  function resetSection(scope: SaveScope) {
    if (!settings) return;
    const saved = editorFromSettings(settings);
    setEditor(current => !current ? saved : scope === "feeds" ? { ...current, feeds: saved.feeds } : scope === "rsshub" ? { ...current, rsshubUrl: saved.rsshubUrl } : { ...current, keywords: saved.keywords, xAuthors: saved.xAuthors, redditAuthors: saved.redditAuthors, refreshMinutes: saved.refreshMinutes, llm: saved.llm, llmKey: "" });
    setError(""); setNotice("");
  }
  function saveBar(scope: SaveScope, label: string) {
    return <div className="settings-save-row">
      <span className={dirty(scope) ? "settings-dirty" : "settings-clean"}>{dirty(scope) ? t("有未保存的修改", "Unsaved changes") : t("当前设置已保存", "All changes saved")}</span>
      <div className="settings-save-actions">
        {dirty(scope) && <button className="quiet-button" disabled={!!busy} onClick={() => resetSection(scope)}>{t("放弃修改", "Discard changes")}</button>}
        <button className="primary-button" disabled={!!busy || !dirty(scope)} onClick={() => void perform(`save-${scope}`, () => saveSection(scope))}>{busy === `save-${scope}` ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{label}</button>
      </div>
    </div>;
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
      tell(localizeMessage("请在 Reddit 授权页面完成登录。"));
    } catch (error) {
      popup?.close();
      throw error;
    }
  }
  function updateDraft(field: keyof Settings, value: unknown) {
    if (field === "rss_feeds") updateEditor("feeds", value as Settings["rss_feeds"]);
    else if (field === "rsshub_url") updateEditor("rsshubUrl", String(value));
    else if (field === "auto_refresh_minutes") updateEditor("refreshMinutes", Number(value));
    else if (field === "llm") updateEditor("llm", value as SettingsEditor["llm"]);
  }
  function addPresets(feeds: FeedSource[]) {
    if (!draft) return;
    const known = new Set(draft.rss_feeds.map((feed) => webUrl(feed.url) || feed.url));
    const knownIds = new Set(draft.rss_feeds.map((feed) => feed.id));
    const additions = feeds.filter((feed) => {
      const url = webUrl(feed.url);
      if (!url || known.has(url)) return false;
      known.add(url);
      return true;
    }).map((feed) => {
      const id = knownIds.has(feed.id) ? crypto.randomUUID() : feed.id;
      knownIds.add(id);
      return { ...feed, id, enabled: feed.enabled ?? true };
    });
    if (!additions.length) {
      tell(localizeMessage("这些来源已在订阅列表中；可在列表中启用，不会改写已有配置。"));
      return;
    }
    updateDraft("rss_feeds", [...draft.rss_feeds, ...additions]);
    tell(t(`已加入 ${additions.length} 个待保存来源，请点击“保存来源”。`, `${additions.length} feeds added to the draft. Click Save feeds.`));
  }
  const xState = connections.x?.state || "disconnected";
  const redditState = connections.reddit?.state || "disconnected";
  const configuredLlm =
    typeof settings?.llm.api_key === "object" &&
    settings.llm.api_key.configured;
  const changedSummaryUrl = draft && draft.llm.base_url.trim().replace(/\/+$/, "") !== (settings?.llm.base_url || "").trim().replace(/\/+$/, "");

  return (
    <section className="settings-page" data-section={tab}>
      <div className="page-heading">
        <div><h1>{t("设置", "Settings")}</h1><p className="settings-intro">{t("连接账号，管理研究来源，配置自己的翻译服务。", "Connect accounts, manage research sources and configure your translation service.")}</p></div>
        <button className="secondary-button" onClick={back}><BookOpen size={16} />{returnPage === "market" ? t("返回行情", "Back to markets") : t("返回资讯", "Back to news")}</button>
      </div>
      <div className="settings-tabs" role="tablist" aria-label={t("设置分类", "Settings sections")} onKeyDown={event => {
        const tabs = ["accounts", "preferences", "feeds", "translation", "health"] as const;
        const index = tabs.indexOf(tab);
        const next = event.key === "ArrowRight" ? tabs[(index + 1) % tabs.length] : event.key === "ArrowLeft" ? tabs[(index + tabs.length - 1) % tabs.length] : event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[tabs.length - 1] : null;
        if (next) { event.preventDefault(); setTab(next); document.getElementById(`settings-tab-${next}`)?.focus(); }
      }}>
        {([
          ["accounts", t("账号", "Accounts")], ["preferences", t("研究设置", "Research")],
          ["feeds", t("RSS 来源", "RSS feeds")], ["translation", t("翻译 API", "Translation API")],
          ["health", t("来源状态", "Source status")],
        ] as [SettingsTab, string][]).map(([id, label]) => <button key={id} id={`settings-tab-${id}`} role="tab" aria-selected={tab === id} aria-controls={`settings-panel-${id}`} tabIndex={tab === id ? 0 : -1} className={tab === id ? "active" : ""} onClick={() => { setTab(id); setError(""); setNotice(""); }}>
          {label}{((id === "preferences" && dirty("preferences")) || (id === "feeds" && (dirty("feeds") || dirty("rsshub"))) || (id === "translation" && translationDirty)) && <span className="unsaved-dot" aria-label={t("有未保存的修改", "Unsaved changes")} />}
        </button>)}
      </div>
      {(!!pending.length || translationDirty) && <div className="settings-pending" role="status">{t("未保存：", "Unsaved:")}{pending.map(scope => <button className="text-button" key={scope} onClick={() => setTab(scope === "preferences" ? "preferences" : "feeds")}>{scope === "preferences" ? t("研究设置", "Research") : scope === "feeds" ? t("RSS 来源", "RSS feeds") : "RSSHub"}</button>)}{translationDirty && <button className="text-button" onClick={() => setTab("translation")}>{t("翻译 API", "Translation API")}</button>}</div>}
      {error && <div className="settings-feedback inline-error" role="alert"><strong>{t("操作未完成", "Action could not complete")}</strong><p>{error}</p></div>}
      {notice && <p className="settings-feedback settings-notice" role="status"><CheckCircle2 size={16} />{notice}</p>}
      <div id={`settings-panel-${tab}`} role="tabpanel" aria-labelledby={`settings-tab-${tab}`}>
      <div hidden={tab !== "translation"}><TranslationSettings onSaved={onTranslationSaved} onDirtyChange={setTranslationDirty} /></div>
      {tab === "accounts" ? (
        <div className="settings-content">
          <fieldset className="settings-editor-fields" disabled={!!busy}>
          <section className="connection-panel">
            <div className="connection-heading">
              <div className="connection-title">
                <SourceMark source="x" />
                <div>
                  <h2>X</h2>
                  <p>{localizeMessage("关键词、关注博主、Following 和 For You")}</p>
                </div>
              </div>
              <ConnectionBadge
                state={xState}
                username={connections.x?.username}
              />
            </div>
            <div className="connection-body">
              <p>{localizeMessage("在独立浏览器窗口中登录自己的账号，本站不接收你的 X 密码。")}</p>
              {connections.x?.message && (
                <div
                  className={`connection-message ${xState === "error" ? "error" : ""}`}
                >
                  {localizeMessage(connections.x.message)}
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
                          localizeMessage("已打开登录窗口，请在浏览器中完成登录。"),
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
                    ? localizeMessage("等待浏览器登录")
                    : xState === "connected"
                      ? localizeMessage("重新登录 X")
                      : localizeMessage("在浏览器登录 X")}
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
                        tell(t(`已同步 ${result.count} 个关注账号。`, `${result.count} followed accounts synced.`));
                      })
                    }
                  >
                    <UsersRound size={16} />{localizeMessage("同步关注名单")}</button>
                )}
                {xState !== "disconnected" && (
                  <button
                    className="quiet-button danger-text"
                    disabled={!!busy}
                    onClick={() =>
                      void perform("x-disconnect", async () => {
                        await api("/connections/x", json("DELETE"));
                        tell(localizeMessage("X 连接已移除。"));
                      })
                    }
                  >{localizeMessage("断开连接")}</button>
                )}
              </div>
              <details className="advanced-settings">
                <summary>{localizeMessage("使用已有登录会话")}</summary>
                <p className="text-note">{localizeMessage("如果浏览器登录不可用，可以导入你自己导出的 Cookie JSON。会话只保存到本机。")}</p>
                <label className="field">
                  <span>Cookie JSON</span>
                  <textarea
                    rows={4}
                    value={cookies}
                    onChange={(event) => setCookies(event.target.value)}
                    placeholder={localizeMessage("粘贴 Cookie JSON（需要 auth_token 与 ct0）")}
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
                      tell(result.message || localizeMessage("登录会话已保存。"));
                    })
                  }
                >{localizeMessage("保存并验证会话")}</button>
              </details>
            </div>
          </section>
          <section className="connection-panel">
            <div className="connection-heading">
              <div className="connection-title">
                <SourceMark source="reddit" />
                <div>
                  <h2>Reddit</h2>
                  <p>{localizeMessage("关键词、订阅社区、指定作者和账号 API 首页")}</p>
                </div>
              </div>
              <ConnectionBadge
                state={redditState}
                username={connections.reddit?.username}
              />
            </div>
            <div className="connection-body">
              <p>{localizeMessage("通过 Reddit 授权连接账号。首次使用需要填写已获 API 访问权限的应用信息。")}</p>
              {connections.reddit?.message && (
                <div
                  className={`connection-message ${redditState === "error" ? "error" : ""}`}
                >
                  {localizeMessage(connections.reddit.message)}
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
                        ? localizeMessage("已配置，留空沿用")
                        : localizeMessage("填写 Reddit 应用 Client ID")
                    }
                    autoComplete="off"
                  />
                </label>
                <label className="field">
                  <span>
                    Client Secret <small>{localizeMessage("Installed app 可留空")}</small>
                  </span>
                  <input
                    type="password"
                    value={clientSecret}
                    onChange={(event) => setClientSecret(event.target.value)}
                    placeholder={localizeMessage("填写应用密钥")}
                    autoComplete="new-password"
                  />
                </label>
              </div>
              <div className="callback-note">{localizeMessage("应用回调地址：")}<code>
                  http://localhost:8787/api/connections/reddit/callback
                </code>
                <button
                  className="text-button"
                  onClick={() => {
                    void navigator.clipboard
                      .writeText(
                        "http://localhost:8787/api/connections/reddit/callback",
                      )
                      .then(() => tell(localizeMessage("回调地址已复制。")))
                      .catch(() => setError(t("无法复制回调地址，请手动选择上方地址。", "Could not copy the callback URL. Select the address above to copy it manually.")));
                  }}
                >{localizeMessage("复制")}</button>
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
                  )}{localizeMessage("登录并授权 Reddit")}</button>
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
                        tell(t(`已同步 ${result.count} 项订阅。`, `${result.count} subscriptions synced.`));
                      })
                    }
                  >{localizeMessage("同步订阅")}</button>
                )}
                {redditState === "connected" && (
                  <button
                    className="quiet-button danger-text"
                    disabled={!!busy}
                    onClick={() =>
                      void perform("reddit-disconnect", async () => {
                        await api("/connections/reddit", json("DELETE"));
                        tell(localizeMessage("Reddit 连接已移除。"));
                      })
                    }
                  >{localizeMessage("断开连接")}</button>
                )}
              </div>
              <p className="text-note">{localizeMessage("Reddit 的 API Best 首页与网页上的个性化推荐可能不同。读取作者投稿时，不要求含有关键词。")}</p>
              <a
                className="subtle-link"
                href="https://www.reddit.com/prefs/apps"
                target="_blank"
                rel="noopener noreferrer"
              >{localizeMessage("查看 Reddit 应用设置")}<ExternalLink size={12} />
              </a>
            </div>
          </section>

          </fieldset>
        </div>
      ) : tab === "health" ? (
        <div className="settings-content settings-health">
          <div className="settings-section-intro"><h2>{t("采集来源状态", "Collection source status")}</h2><p>{t("分别记录最近尝试与成功采集。已有资讯在来源暂时不可用时仍可阅读。", "Last attempts and successful collections are recorded separately. Collected news remains readable when a source is temporarily unavailable.")}</p></div>
          <SourceHealth sources={sources} />
        </div>
      ) : tab === "translation" ? null : !draft ? (
        <div className="empty-state">
          <LoaderCircle className="spin" size={25} />
          <p>{localizeMessage("正在读取工作区配置…")}</p>
          <button
            className="secondary-button"
            onClick={() =>
              void reloadSettings().catch((error) => tell(errorMessage(error)))
            }
          >{localizeMessage("重新读取")}</button>
        </div>
      ) : tab === "preferences" ? (
        <div className="settings-content">
          {saveBar("preferences", t("保存研究设置", "Save research"))}
          <fieldset className="settings-editor-fields" disabled={!!busy}>
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>{localizeMessage("研究关键词")}</h2>
                <p>{localizeMessage("保存你的研究方向；搜索时仍可输入任何关键词。")}</p>
              </div>
            </div>
            <div className="connection-body">
              <label className="field">
                <span>{localizeMessage("关键词，每行一个")}</span>
                <textarea
                  value={keywords}
                  onChange={(event) => setKeywords(event.target.value)}
                  rows={6}
                  placeholder={localizeMessage("宏观\n加密货币\n美股\n港股\nA股\n黄金")}
                />
              </label>
            </div>
          </section>
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>{localizeMessage("关注博主")}</h2>
                <p>{localizeMessage("这里的作者内容会独立收录，不强制匹配关键词。")}</p>
              </div>
            </div>
            <div className="connection-body form-grid">
              <label className="field">
                <span>{localizeMessage("X 用户名，每行一个")}</span>
                <textarea
                  rows={5}
                  value={xAuthors}
                  onChange={(event) => setXAuthors(event.target.value)}
                  placeholder={localizeMessage("用户名，不需要 @")}
                />
              </label>
              <label className="field">
                <span>{localizeMessage("Reddit 用户名，每行一个")}</span>
                <textarea
                  rows={5}
                  value={redditAuthors}
                  onChange={(event) => setRedditAuthors(event.target.value)}
                  placeholder={localizeMessage("用户名，不需要 u/")}
                />
              </label>
            </div>
          </section>
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>{localizeMessage("自动更新")}</h2>
                <p>{localizeMessage("网站服务运行期间，按设定间隔更新关键词、关注订阅和已连接账号推荐。")}</p>
              </div>
            </div>
            <div className="connection-body">
              <label className="field compact-field">
                <span>{localizeMessage("更新间隔")}</span>
                <select
                  value={draft.auto_refresh_minutes}
                  onChange={(event) =>
                    updateDraft(
                      "auto_refresh_minutes",
                      Number(event.target.value),
                    )
                  }
                >
                  <option value={0}>{localizeMessage("手动更新")}</option>
                  <option value={15}>{localizeMessage("每 15 分钟")}</option>
                  <option value={30}>{localizeMessage("每 30 分钟")}</option>
                  <option value={60}>{localizeMessage("每 1 小时")}</option>
                  <option value={240}>{localizeMessage("每 4 小时")}</option>
                </select>
              </label>
            </div>
          </section>
          <details className="settings-disclosure summary-settings" open={draft.llm.enabled || undefined}>
            <summary><span>{t("AI 摘要", "AI summaries")}</span><small>{t("可选 · 与翻译 API 分别配置", "Optional · configured separately from translation")}</small></summary>
            <section>
            <div className="connection-heading">
              <div>
                <h2>{localizeMessage("AI 整理")}<span className="optional-label">{localizeMessage("可选")}</span>
                </h2>
                <p>{localizeMessage("不启用时展示原文摘录；启用后可生成中文摘要。")}</p>
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
                <span>{localizeMessage("启用")}</span>
              </label>
            </div>
            <div className="connection-body">
              <div className="form-grid">
                <label className="field">
                  <span>{localizeMessage("兼容 API 地址")}</span>
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
                  <span>{localizeMessage("模型名称")}</span>
                  <input
                    value={draft.llm.model || ""}
                    onChange={(event) =>
                      updateDraft("llm", {
                        ...draft.llm,
                        model: event.target.value,
                      })
                    }
                    placeholder={localizeMessage("填写你使用的模型名称")}
                  />
                </label>
              </div>
              <label className="field">
                <span>
                  API Key{" "}
                  <small>
                    {changedSummaryUrl && configuredLlm ? t("地址已更换，需要新服务的密钥", "New URL: enter this provider's key") : configuredLlm ? localizeMessage("已保存，留空沿用") : localizeMessage("本地模型服务可留空")}
                  </small>
                </span>
                <input
                  type="password"
                  value={llmKey}
                  onChange={(event) => setLlmKey(event.target.value)}
                  placeholder={configuredLlm ? localizeMessage("已保存") : localizeMessage("输入 API Key")}
                  autoComplete="new-password"
                />
              </label>
              <p className="text-note">{localizeMessage("启用后，生成摘要会将对应帖子的文本发送到你配置的服务。")}</p>
            </div>
            </section>
          </details>

          </fieldset>
        </div>
      ) : (
        <div className="settings-content">
          {saveBar("feeds", t("保存 RSS 来源", "Save feeds"))}
          <fieldset className="settings-editor-fields" disabled={!!busy}>
          <section className="connection-panel">
            <div className="connection-heading">
              <div>
                <h2>{localizeMessage("订阅来源")}</h2>
                <p>{localizeMessage("公开新闻、机构公告和博客。加入、启停或移除后，点击“保存来源”。")}</p>
              </div>
            </div>
            <div className="feed-settings-list">
              {!draft.rss_feeds.length && <p className="settings-empty-feeds">{t("还没有 RSS 来源。可在下方添加地址，或展开「发现财经来源」选择预设。", "No RSS feeds yet. Add a URL below, or open Discover financial feeds to choose a preset.")}</p>}
              {draft.rss_feeds.map((feed) => (
                <div className="feed-setting" key={feed.id}>
                  <label className="feed-enabled">
                    <input
                      type="checkbox"
                      checked={feed.enabled}
                      disabled={!!busy}
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
                    disabled={!!busy}
                    aria-label={t(`移除 ${feed.name}`, `Remove ${feed.name}`)}
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
                  <span>{localizeMessage("来源名称")}</span>
                  <input
                    value={newFeedName}
                    onChange={(event) => setNewFeedName(event.target.value)}
                    placeholder={localizeMessage("例如：研究博客")}
                  />
                </label>
                <label className="field">
                  <span>{localizeMessage("RSS / Atom 地址")}</span>
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
                    if (draft.rss_feeds.some((feed) => (webUrl(feed.url) || feed.url) === url.href)) {
                      setError(localizeMessage("这个 RSS 地址已在列表中；请直接启用现有来源。"));
                      return;
                    }
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
                    setError("");
                  } catch {
                    setError(localizeMessage("请输入有效的 http 或 https RSS 地址。"));
                  }
                }}
              >
                <Plus size={16} />{localizeMessage("添加来源")}</button>
            </div>
          </section>
          <details className="settings-disclosure preset-panel">
            <summary><span>{t("发现财经来源", "Discover financial feeds")}</span><small>{t("公开来源预设与 RSSHub 路由", "Public presets and RSSHub routes")}</small></summary>
            <section>
            <div className="connection-heading">
              <div><h2>{localizeMessage("财经来源预设")}</h2><p>{localizeMessage("加入公开财经 RSS；已有来源的名称、地址和启停状态会保留。")}</p></div>
              {presets?.feeds?.length ? <button className="secondary-button" disabled={!!busy} onClick={() => addPresets(presets.feeds)}><Plus size={15} />{localizeMessage("加入全部")}</button> : null}
            </div>
            <div className="connection-body">
              {presetsLoading && <p className="text-note" role="status"><LoaderCircle size={14} className="spin" />{localizeMessage("正在读取财经来源…")}</p>}
              {presetsError && <div className="inline-error" role="alert"><p>{localizeMessage("财经预设未能加载：")}{localizeMessage(presetsError)}</p><button className="text-button" onClick={() => void loadPresets()}>{localizeMessage("重试读取")}</button></div>}
              {!presetsLoading && !presetsError && !presets?.feeds?.length && <p className="text-note">{localizeMessage("暂无预设来源；可以在下方手动添加 RSS。")}</p>}
              <div className="preset-list">
                {(presets?.feeds || []).map((feed) => {
                  const existing = draft.rss_feeds.some((current) => (webUrl(current.url) || current.url) === (webUrl(feed.url) || feed.url));
                  return <div className="preset-row" key={feed.id}>
                    <div><strong>{feed.name}</strong>{feed.category && <span className="preset-category">{feed.category}</span>}{!feed.enabled && <span className="preset-category">{localizeMessage("默认未启用")}</span>}<small>{feed.url}</small>
                      {feed.description && <p className="text-note">{localizeMessage(feed.description)}</p>}
                      {!!feed.requires?.length && <p className="text-note">{localizeMessage("使用要求：")}{sourceRequirements(feed.requires)}</p>}
                    </div>
                    <button className="text-button" disabled={existing || !!busy} onClick={() => addPresets([feed])}>{existing ? localizeMessage("已添加") : localizeMessage("加入订阅")}</button>
                  </div>;
                })}
              </div>
              {!!presets?.rsshub_routes?.length && <details className="rsshub-route-notes"><summary>{localizeMessage("RSSHub 财经路由参考")}</summary><p className="text-note">{localizeMessage("需要自行运行实例并验证具体路由；本人首页与登录会话尚未验证。")}</p>
                <ul>{presets.rsshub_routes.map((route, index) => <li key={route.id || index}>
                  <strong>{localizeMessage(route.name)}</strong>
                  {(route.path || route.route || route.url) && <code>{route.path || route.route || route.url}</code>}
                  {route.description && <p>{localizeMessage(route.description)}</p>}
                  <p>{localizeMessage("使用要求：")}{route.requires?.length ? sourceRequirements(route.requires) : localizeMessage("预设无额外配置要求")}</p>
                </li>)}</ul>
              </details>}
            </div>
            </section>
          </details>
          <details className="settings-disclosure rsshub-settings">
            <summary><span>RSSHub</span><small>{t("高级接入 · 可选", "Advanced connection · optional")}</small></summary>
            <section>
              <div className="connection-heading">
                <div className="connection-title">
                  <Rss size={23} />
                  <div>
                    <h2>
                      RSSHub <span className="optional-label">{localizeMessage("可选")}</span>
                    </h2>
                    <p>{localizeMessage("接入已经运行的 RSSHub 实例")}</p>
                  </div>
                </div>
              </div>
              <div className="connection-body">
                <label className="field">
                  <span>{localizeMessage("RSSHub 地址")}</span>
                  <input
                    type="url"
                    value={draft.rsshub_url || ""}
                    onChange={(event) =>
                      updateDraft("rsshub_url", event.target.value)
                    }
                    placeholder="http://127.0.0.1:1200"
                  />
                </label>
                <p className="text-note">{localizeMessage("保存地址仅表示已配置实例。本人首页仍需配置自己的会话并实际验证；当前尚未验证 RSSHub 本人首页。 普通公开路由可作为 RSS 订阅加入，账号推荐流请使用上方的账号连接。")}</p>
                {saveBar("rsshub", t("保存 RSSHub 地址", "Save RSSHub URL"))}
              </div>
            </section>
          </details>
          </fieldset>
        </div>
      )}
      </div>
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
        ? username || localizeMessage("已连接")
        : state === "connecting"
          ? localizeMessage("连接中")
          : state === "error"
            ? localizeMessage("需要检查")
            : localizeMessage("未连接")}
    </span>
  );
}
