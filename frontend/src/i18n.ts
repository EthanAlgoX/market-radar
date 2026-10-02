import { useSyncExternalStore } from "react";
import { UI_MESSAGES } from "./messages.ts";
import { localizeDiagnostic } from "./diagnostics.ts";

export type Locale = "en" | "zh";
const storageKey = "radar-interface-language";
const listeners = new Set<() => void>();
function savedLocale(): Locale {
  try { return typeof localStorage !== "undefined" && localStorage.getItem(storageKey) === "zh" ? "zh" : "en"; }
  catch { return "en"; }
}
let currentLocale: Locale = savedLocale();
export const getLocale = () => currentLocale;
export const localeCode = () => currentLocale === "zh" ? "zh-CN" : "en-US";
export function setLocale(locale: Locale) {
  currentLocale = locale;
  try { if (typeof localStorage !== "undefined") localStorage.setItem(storageKey, locale); } catch { /* Language selection also works without persistent storage. */ }
  if (typeof document !== "undefined") {
    document.documentElement.lang = localeCode();
    document.title = locale === "zh" ? "交易雷达 · Market Radar" : "Market Radar · Trading research";
  }
  listeners.forEach(listener => listener());
}
export function useLocale() {
  const locale = useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener); }; }, getLocale, () => "en" as Locale);
  return { locale, setLocale };
}
export function t(chinese: string, english: string): string { return currentLocale === "zh" ? chinese : english; }

const reverseMessages = Object.fromEntries(Object.entries(UI_MESSAGES).map(([chinese, english]) => [english, chinese]));
/** Localize application-owned labels and diagnostics; never pass source article text here. */
export function localizeMessage(message: string): string {
  if (!message) return message;
  if (currentLocale === "zh") return reverseMessages[message] || localizeDiagnostic(message, "zh") || message;
  const exact = UI_MESSAGES[message];
  if (exact) return exact;
  const diagnostic = localizeDiagnostic(message, "en");
  if (diagnostic !== undefined) return diagnostic;
  const patterns: [RegExp, (...values: string[]) => string][] = [
    [/^请求失败（(\d+)）$/, code => `Request failed (HTTP ${code})`],
    [/^翻译服务返回 HTTP (\d+)，原文已保留$/, code => `Translation service returned HTTP ${code}. Original text is retained.`],
    [/^末根连续合格闭合样本 (\d+) 根，需要至少 (\d+) 根才能确认全部默认规则。$/, (count, required) => `${count} consecutive valid closed bars; at least ${required} are required for all default rules.`],
    [/^当前连续合格闭合样本 (\d+) 根，至少需要 (\d+) 根。$/, (count, required) => `${count} consecutive valid closed bars; at least ${required} are required.`],
    [/^当前闭合窗口存在质量问题：(.*)$/, reason => `The closed window has data quality issues: ${localizeMessage(reason)}`],
    [/^当前连续有效闭合 K 线 (\d+) 根，至少需 (\d+) 根才能计算所选规则。$/, (count, minimum) => `${count} consecutive valid closed candles; at least ${minimum} are needed for the selected rules.`],
    [/^末根 K 线(.*)，该窗口停止计算并重新预热。$/, reason => `The latest candle failed validation (${reason.split("、").map(localizeMessage).join(", ")}). Calculation pauses and warmup restarts.`],
    [/^已按闭合 K 线计算。以下规则仍需预热：(.*)。$/, names => `Calculated from closed candles. These rules still need warmup: ${names.split("、").map(localizeMessage).join(", ")}.`],
    [/^Value error, (.*)$/, reason => `Value error, ${localizeMessage(reason)}`],
  ];
  for (const [pattern, render] of patterns) {
    const match = message.match(pattern);
    if (match) return render(...match.slice(1));
  }
  return message;
}
