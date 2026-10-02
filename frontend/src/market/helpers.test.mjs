import assert from "node:assert/strict";
import test from "node:test";
import { setLocale } from "../i18n.ts";
import { evidenceRows, formatTime, instrumentName, jobSummary, latestCandle, MARKET_NAMES, qualityNotes, ruleName, signalSummary, statusLabel, volumeLabel } from "./helpers.ts";

test.beforeEach(() => setLocale("en"));
test.afterEach(() => setLocale("en"));

test("refresh progress counts instruments while total counts candles", () => {
  const job = { status: "running", total: 720, progress: [{ status: "completed" }, { status: "running" }], added: 0, updated: 0 };
  assert.equal(jobSummary(job), "Refreshing · 1/2 instruments");
});

test("latest quote preserves auction OHLC conventions and rejects missing prices", () => {
  const old = { time: "2026-10-01T00:00:00Z", open: 10, high: 12, low: 9, close: 11 };
  const auction = { time: "2026-10-02T00:00:00Z", open: 13, high: 12, low: 10, close: 11 };
  assert.equal(latestCandle([old, auction]), auction);
  assert.equal(latestCandle([old, { ...auction, close: null }]), old);
  assert.equal(latestCandle([{ ...auction, close: Number.NaN }]), undefined);
});

test("missing OHLCV rows are not described as missing time intervals", () => {
  const notes = qualityNotes({ flags: ["missing_ohlcv"], missing_rows: 1, open_rows: 0, gaps: 0, status: "warning" });
  assert.equal(notes.length, 1);
  assert.ok(notes[0].includes("missing price or volume data"));
  assert.ok(!notes[0].includes("time gaps"));
});

test("stock lots and crypto base quantity retain their source units", () => {
  assert.equal(volumeLabel("lots_100_shares"), "lots (100 shares)");
  assert.equal(volumeLabel("base_asset", "BTC/USDT"), "BTC (base asset)");
});

test("market labels, evidence and quality notes react to locale changes without reloading", () => {
  const quality = { flags: ["missing_ohlcv"], missing_rows: 1, open_rows: 0, gaps: 0, status: "warning" };
  const signal = { evidence: { close: 123.5, volume_ratio20: 2.5 } };
  assert.equal(MARKET_NAMES.crypto, "Crypto");
  assert.equal(statusLabel("quality_blocked"), "Calculation paused");
  assert.equal(evidenceRows(signal)[1].value, "2.5×");
  assert.equal(formatTime(undefined), "No record yet");
  setLocale("zh");
  assert.equal(MARKET_NAMES.crypto, "加密货币");
  assert.equal(statusLabel("quality_blocked"), "暂停计算");
  assert.equal(evidenceRows(signal)[0].label, "收盘价");
  assert.equal(evidenceRows(signal)[1].value, "2.5 倍");
  assert.ok(qualityNotes(quality)[0].includes("价格或成交量数据缺失"));
  assert.equal(volumeLabel("lots_100_shares"), "手（100 股）");
  assert.equal(formatTime(undefined), "尚无记录");
  setLocale("en");
  assert.equal(MARKET_NAMES.crypto, "Crypto");
  assert.equal(evidenceRows(signal)[0].label, "Close");
});

test("known instrument labels localize while unknown identities and signal evidence are retained", () => {
  assert.equal(instrumentName("腾讯", "0700.HK"), "Tencent");
  assert.equal(instrumentName("自定义公司", "CUSTOM"), "自定义公司");
  assert.equal(instrumentName(undefined, "CUSTOM"), "CUSTOM");
  const signal = { id: "event-123", rule_name: "RSI14 阈值穿越", rule_id: "rsi14_cross", direction: "down", evidence: { threshold: 30 }, parameters: {}, summary: "RSI14 下穿 30。" };
  assert.equal(signalSummary(signal), "RSI14 crossed below 30.");
  assert.equal(ruleName(signal), "RSI14 threshold crossover");
  setLocale("zh");
  assert.equal(instrumentName("腾讯", "0700.HK"), "腾讯");
  assert.equal(signalSummary(signal), "RSI14 下穿 30。");
});
