import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Check, CheckCircle2, Languages, LoaderCircle, Trash2 } from "lucide-react";
import { api, json } from "./api";
import { localizeMessage, t, useLocale } from "./i18n";
import type { TranslationConfig } from "./types";

export default function TranslationSettings({ onSaved, onDirtyChange }: { onSaved: () => Promise<void>; onDirtyChange?: (dirty: boolean) => void }) {
  useLocale();
  const [config, setConfig] = useState<TranslationConfig | null>(null);
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com");
  const [model, setModel] = useState("deepseek-flash");
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<"saved" | "removed" | null>(null);
  const normalizeUrl = (value: string) => value.trim().replace(/\/+$/, "");
  const changedUrl = !!config && normalizeUrl(baseUrl) !== normalizeUrl(config.base_url);
  const dirty = !!config && (changedUrl || model.trim() !== config.model || !!key.trim());
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  const accept = useCallback((value: TranslationConfig) => {
    setConfig(value); setBaseUrl(value.base_url); setModel(value.model || "deepseek-flash"); setKey("");
  }, []);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try { const value = await api<TranslationConfig>("/translation/config", { signal }); if (!signal?.aborted) accept(value); }
    catch (failure) { if (!signal?.aborted) setError(failure instanceof Error ? failure.message : "Unable to load API settings."); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [accept]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice(null);
    try {
      const result = await api<TranslationConfig>("/translation/config", json("PATCH", { base_url: baseUrl.trim(), model: model.trim(), api_key: key.trim() }));
      accept(result); setNotice("saved");
      try { await onSaved(); } catch { setError(t("API 已保存，但资讯状态刷新失败。返回资讯后可重新加载。", "API saved, but the feed status could not refresh. Reload the feed to continue.")); }
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to save API settings."); }
    finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError(""); setNotice(null);
    try {
      accept(await api<TranslationConfig>("/translation/config", json("DELETE"))); setNotice("removed");
      try { await onSaved(); } catch { setError(t("本地配置已移除，但资讯状态刷新失败。返回资讯后可重新加载。", "Local settings removed, but the feed status could not refresh. Reload the feed to continue.")); }
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to remove API settings."); }
    finally { setBusy(false); }
  }
  return <div className="settings-content translation-settings">
    <section className="connection-panel">
      <div className="connection-heading">
        <div className="connection-title"><Languages size={24} /><div>
          <h2>{t("资讯翻译 API", "Content translation API")}</h2>
          <p>{t("中文阅读模式会使用此服务翻译标题、摘要和正文。", "Chinese reading mode uses this service to translate titles, summaries and source text.")}</p>
        </div></div>
        {config && <span className={`connection-badge ${config.configured ? "connected" : "disconnected"}`}>
          {config.configured ? <CheckCircle2 size={14} /> : <span className="status-dot" />}
          {config.configured ? t("已配置", "Configured") : t("未配置", "Not configured")}
        </span>}
      </div>
      <div className="connection-body">
        {loading ? <p className="text-note" role="status"><LoaderCircle className="spin" size={15} /> {t("正在读取 API 配置…", "Loading API settings…")}</p> : <>
          {config && <p className="translation-config-source">{config.source === "environment"
            ? t("正在使用本机环境配置。保存自己的 API 可覆盖它。", "Using this machine's environment settings. Save your own API to override them.")
            : config.source === "local" ? t("正在使用已保存的本地 API，修改后立即生效。", "Using your saved local API. Changes take effect immediately.")
            : t("先配置自己的 LLM API，才能启用中文阅读。", "Configure your own LLM API to enable Chinese reading.")}</p>}
          {config?.configured && <div className="translation-provider-status"><span>{t("当前模型", "Active model")}</span><strong>{config.model}</strong><span>{config.source === "environment" ? t("来自环境变量", "From environment") : t("本地配置", "Local settings")}</span></div>}
          {config && <form onSubmit={event => void save(event)}>
            <fieldset disabled={busy} className="translation-fields">
              <div className="form-grid">
                <label className="field"><span>{t("API 地址", "API base URL")}</span><input type="url" required value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="https://api.deepseek.com" spellCheck={false} autoComplete="off" /></label>
                <label className="field"><span>{t("模型名称", "Model name")}</span><input required value={model} onChange={event => setModel(event.target.value)} placeholder="deepseek-flash" spellCheck={false} autoComplete="off" /></label>
              </div>
              <label className="field"><span>API key <small>{changedUrl ? t("已更换地址，需要此服务的密钥", "New URL: enter this provider's key") : config.api_key_set ? t("已配置；留空沿用", "Configured; leave blank to keep") : t("需要你自己的密钥", "Your own key is required")}</small></span>
                <input type="password" required={!config.api_key_set || changedUrl} value={key} onChange={event => setKey(event.target.value)} placeholder={config.api_key_set && !changedUrl ? t("不显示已有密钥", "Existing key is not displayed") : t("输入 API key", "Enter your API key")} autoComplete="new-password" spellCheck={false} />
              </label>
              <p className="text-note">{t("密钥在本机加密保存。翻译内容会发送到你选择的 API 服务。", "Keys are encrypted on this computer. Source text is sent to the API provider you choose.")}</p>
              <div className="translation-api-actions">
                <span className={dirty ? "settings-dirty" : "settings-clean"}>{dirty ? t("有未保存的修改", "Unsaved changes") : config.configured ? t("当前配置已生效", "Current settings are active") : t("等待配置 API", "Waiting for API configuration")}</span>
                <div className="connection-actions">
                  {dirty && <button className="quiet-button" type="button" onClick={() => { accept(config); setError(""); setNotice(null); }}>{t("放弃修改", "Discard changes")}</button>}
                  <button className="primary-button" type="submit" disabled={!dirty}>{busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}{t("保存 API", "Save API")}</button>
                </div>
              </div>
              <details className="translation-help"><summary>{t("支持的服务与翻译方式", "Supported providers and translation behavior")}</summary><p className="text-note">{t("默认使用 DeepSeek Flash，也支持兼容 OpenAI Chat Completions 的服务。更换 API 地址时需要填写对应密钥。原文会保留；保存后，中文阅读模式会继续翻译待处理资讯。", "DeepSeek Flash is the default. Other OpenAI-compatible Chat Completions providers are supported. Changing providers requires that provider's key. Originals are retained; Chinese reading mode resumes translating pending posts after saving.")}</p></details>
              {config.source === "local" && <div className="connection-actions"><button className="quiet-button danger-text" type="button" onClick={() => void remove()}><Trash2 size={16} />{config.environment_available ? t("恢复环境配置", "Use environment settings") : t("移除 API 配置", "Remove API settings")}</button></div>}
            </fieldset>
          </form>}
        </>}
        {error && <div className="inline-error" role="alert"><p>{localizeMessage(error)}</p>{!config && <button className="text-button" onClick={() => void load()}>{t("重试读取", "Retry loading")}</button>}</div>}
        {notice && <p className="translation-save-notice" role="status"><CheckCircle2 size={15} />{notice === "saved" ? t("API 已保存并立即生效，可以返回资讯切换中文。", "API saved and active. Return to the feed to translate posts.") : t("本地 API 配置已移除。", "Local API settings removed.")}</p>}
      </div>
    </section>
    <p className="text-note">{t("界面语言使用内置文案，无需 API。资讯翻译需要 LLM API；AI 摘要在「研究设置」中单独配置。", "Interface language needs no API. Content translation needs an LLM API; AI summaries have separate settings in Research.")}</p>
  </div>;
}
