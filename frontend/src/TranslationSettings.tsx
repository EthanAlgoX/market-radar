import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Check, CheckCircle2, Languages, LoaderCircle, Trash2 } from "lucide-react";
import { api, json } from "./api";
import { localizeMessage, t, useLocale } from "./i18n";
import type { TranslationConfig } from "./types";

export default function TranslationSettings({ onSaved }: { onSaved: () => Promise<void> }) {
  useLocale();
  const [config, setConfig] = useState<TranslationConfig | null>(null);
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com");
  const [model, setModel] = useState("deepseek-flash");
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<"saved" | "removed" | null>(null);
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
      accept(result); await onSaved(); setNotice("saved");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to save API settings."); }
    finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError(""); setNotice(null);
    try { accept(await api<TranslationConfig>("/translation/config", json("DELETE"))); await onSaved(); setNotice("removed"); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to remove API settings."); }
    finally { setBusy(false); }
  }
  return <div className="settings-content translation-settings">
    <section className="connection-panel">
      <div className="connection-heading">
        <div className="connection-title"><Languages size={24} /><div>
          <h2>{t("资讯翻译 API", "Content translation API")}</h2>
          <p>{t("使用你自己的 LLM API，将资讯标题、摘要和正文翻译为中文。", "Use your own LLM API to translate collected titles, summaries and article text into Chinese.")}</p>
        </div></div>
        {config && <span className={`connection-badge ${config.configured ? "connected" : "disconnected"}`}>
          {config.configured ? <CheckCircle2 size={14} /> : <span className="status-dot" />}
          {config.configured ? t("已配置", "Configured") : t("未配置", "Not configured")}
        </span>}
      </div>
      <div className="connection-body">
        {loading ? <p className="text-note" role="status"><LoaderCircle className="spin" size={15} /> {t("正在读取 API 配置…", "Loading API settings…")}</p> : <>
          {config && <p className="translation-config-source">{config.source === "environment"
            ? t("当前使用本机环境配置。你可以保存自己的 API 来覆盖它，移除本地配置后会恢复环境配置。", "Using this machine's environment configuration. Save your own API to override it; removing the local override restores the environment configuration.")
            : config.source === "local" ? t("当前使用你保存的本地 API 配置，修改后立即生效。", "Using your saved local API settings. Changes take effect immediately.")
            : t("尚未配置翻译服务。请填写 API 地址、模型和密钥，原文会始终保留。", "No translation service is configured. Add an API URL, model and key; original text is always retained.")}</p>}
          {config && <form onSubmit={event => void save(event)}>
            <fieldset disabled={busy} className="translation-fields">
              <div className="form-grid">
                <label className="field"><span>{t("API 地址", "API base URL")}</span><input type="url" required value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="https://api.deepseek.com" spellCheck={false} autoComplete="off" /></label>
                <label className="field"><span>{t("模型名称", "Model name")}</span><input required value={model} onChange={event => setModel(event.target.value)} placeholder="deepseek-flash" spellCheck={false} autoComplete="off" /></label>
              </div>
              <label className="field"><span>API key <small>{config.api_key_set ? t("已配置；同一地址留空沿用", "Configured; leave blank to keep for the same URL") : t("需要你自己的密钥", "Your own key is required")}</small></span>
                <input type="password" required={!config.api_key_set} value={key} onChange={event => setKey(event.target.value)} placeholder={config.api_key_set ? t("不显示已有密钥", "Existing key is not displayed") : t("输入 API key", "Enter your API key")} autoComplete="new-password" spellCheck={false} />
              </label>
              <p className="text-note">{t("默认使用 DeepSeek Flash，也支持兼容 OpenAI Chat Completions 的服务。更换 API 地址时请填写该服务的密钥。保存后立即生效；中文阅读模式已启用时，会自动翻译待处理资讯。", "DeepSeek Flash is the default. Other OpenAI-compatible Chat Completions providers are supported. Enter that provider's key when changing the URL. Settings take effect immediately; pending posts translate automatically when Chinese reading mode is enabled.")}</p>
              <p className="text-note">{t("密钥在本机加密保存，不会在页面回显。翻译时，相关资讯文本会发送到你配置的服务。", "Keys are encrypted on this computer and are never shown back in the page. Translation sends the selected source text to your configured provider.")}</p>
              <div className="connection-actions">
                <button className="primary-button" type="submit">{busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}{t("保存 API", "Save API")}</button>
                {config.source === "local" && <button className="quiet-button danger-text" type="button" onClick={() => void remove()}><Trash2 size={16} />{config.environment_available ? t("恢复环境配置", "Use environment settings") : t("移除 API 配置", "Remove API settings")}</button>}
              </div>
            </fieldset>
          </form>}
        </>}
        {error && <div className="inline-error" role="alert"><p>{localizeMessage(error)}</p>{!config && <button className="text-button" onClick={() => void load()}>{t("重试读取", "Retry loading")}</button>}</div>}
        {notice && <p className="translation-save-notice" role="status"><CheckCircle2 size={15} />{notice === "saved" ? t("API 已保存并立即生效，可以返回资讯切换中文。", "API saved and active. Return to the feed to translate posts.") : t("本地 API 配置已移除。", "Local API settings removed.")}</p>}
      </div>
    </section>
    <p className="text-note">{t("界面的 English / 中文 切换使用内置文案，无需 API。资讯内容的中文翻译需要可用的 LLM API；AI 摘要在「关键词与加工」中单独配置。", "The English / 中文 interface switch uses built-in text and needs no API. Chinese content translation needs an LLM API. AI summaries are configured separately in Research.")}</p>
  </div>;
}
