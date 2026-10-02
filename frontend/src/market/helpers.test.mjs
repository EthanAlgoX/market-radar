import assert from "node:assert/strict";
import test from "node:test";
import { jobSummary, latestCandle, qualityNotes, volumeLabel } from "./helpers.ts";

test("refresh progress counts instruments while total counts candles", () => {
  const job = { status: "running", total: 720, progress: [{ status: "completed" }, { status: "running" }], added: 0, updated: 0 };
  assert.equal(jobSummary(job), "正在刷新 · 1/2 个标的");
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
  assert.ok(notes[0].includes("价格或成交量数据缺失"));
  assert.ok(!notes[0].includes("时间缺口"));
});

test("stock lots and crypto base quantity retain their source units", () => {
  assert.equal(volumeLabel("lots_100_shares"), "手（100 股）");
  assert.equal(volumeLabel("base_asset", "BTC/USDT"), "BTC（基础资产）");
});
