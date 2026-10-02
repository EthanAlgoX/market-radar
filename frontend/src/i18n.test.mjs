import assert from "node:assert/strict";
import test from "node:test";
import { getLocale, localizeMessage, setLocale, t } from "./i18n.ts";
import { sameOriginal, translatedPost, translationReady } from "./useChineseTranslation.ts";

test("English is the fresh default; interface switching is local and reversible", () => {
  assert.equal(getLocale(), "en");
  assert.equal(localizeMessage("关键词资讯"), "Keyword feed");
  setLocale("zh");
  assert.equal(t("资讯翻译 API", "Content translation API"), "资讯翻译 API");
  assert.equal(localizeMessage("Configure your own LLM API in Settings to translate content into Chinese."), "请在设置中配置自己的 LLM API，再翻译资讯内容。");
  setLocale("en");
});

test("dynamic quality diagnostics retain counts in English", () => {
  setLocale("en");
  assert.equal(localizeMessage("当前连续有效闭合 K 线 21 根，至少需 61 根才能计算所选规则。"), "21 consecutive valid closed candles; at least 61 are needed for the selected rules.");
  assert.ok(localizeMessage("末根 K 线OHLCV 缺失，该窗口停止计算并重新预热。").includes("missing OHLCV"));
});

test("source diagnostics keep counts and account identities across language switches", () => {
  setLocale("en");
  const original = "收到 17 条 · 新增 2 · 更新 1 · 重复 14";
  const english = localizeMessage(original);
  assert.ok(!/[\u3400-\u9fff]/.test(english));
  for (const count of ["17", "2", "1", "14"]) assert.ok(english.includes(count));
  assert.ok(localizeMessage("已验证 @researcher_1 的 X 会话。").includes("@researcher_1"));
  setLocale("zh");
  assert.equal(localizeMessage(english), original);
  setLocale("en");
  assert.equal(localizeMessage("Unknown diagnostic: source-id-123"), "Unknown diagnostic: source-id-123");
});

test("same model on another provider cannot reuse the page's previous translation", () => {
  const item = { id: "post", title: "Source", content: "Text", summary: "", url: "https://example.org/post", translation: { language: "zh", model: "model", cache_key: "model@provider-a", title: "来源", content: "文本", summary: "" } };
  assert.equal(translationReady(item, "model@provider-b"), false);
  assert.equal(translatedPost(item, true, "model@provider-b"), item);
  assert.equal(translationReady(item, "model@provider-a"), true);
  const result = translatedPost(item, true, "model@provider-a");
  assert.equal(result.title, "来源");
  assert.equal(result.url, item.url);
  assert.equal(item.title, "Source");
});

test("legacy DeepSeek translations remain readable without a provider cache field", () => {
  const item = { id: "post", title: "Source", content: "Text", summary: "", translation: { language: "zh", model: "deepseek-flash", title: "来源", content: "文本", summary: "" } };
  assert.equal(translationReady(item, "deepseek-flash"), true);
  assert.equal(sameOriginal(item, { ...item, bookmarked: true }), true);
  assert.equal(sameOriginal(item, { ...item, content: "Revised text" }), false);
});
