import assert from "node:assert/strict";
import test from "node:test";
import { applicationApiUrl, applicationBaseUrl } from "./appUrls.ts";

test("local root deployment retains its API paths", () => {
  assert.equal(applicationBaseUrl("http://localhost:8787/#/news?q=BTC"), "http://localhost:8787/");
  assert.equal(applicationApiUrl("/items?limit=60", "http://localhost:8787/"), "http://localhost:8787/api/items?limit=60");
});

test("relative builds preserve the public prefix independently of query strings and SPA routes", () => {
  const page = "https://myaistock.top/market-radar/?connection=reddit&status=connected#/settings?tab=accounts";
  assert.equal(applicationBaseUrl(page, "./"), "https://myaistock.top/market-radar/");
  assert.equal(applicationApiUrl("/export?format=json", page, "./"), "https://myaistock.top/market-radar/api/export?format=json");
  assert.equal(applicationApiUrl("/connections/reddit/callback", page), "https://myaistock.top/market-radar/api/connections/reddit/callback");
});

test("the application prefix is a directory with a trailing slash, including direct HTML entry points", () => {
  assert.equal(applicationBaseUrl("https://myaistock.top/market-radar"), "https://myaistock.top/market-radar/");
  assert.equal(applicationApiUrl("/overview", "https://myaistock.top/market-radar"), "https://myaistock.top/market-radar/api/overview");
  assert.equal(applicationBaseUrl("https://myaistock.top/market-radar/index.html?unused=1"), "https://myaistock.top/market-radar/");
});

test("an explicit Vite base takes precedence and API identifiers remain encoded", () => {
  assert.equal(applicationBaseUrl("https://myaistock.top/", "/market-radar"), "https://myaistock.top/market-radar/");
  assert.equal(applicationApiUrl("/items/a%2Fb/discussion", "https://myaistock.top/market-radar/", "/market-radar/"), "https://myaistock.top/market-radar/api/items/a%2Fb/discussion");
  assert.equal(applicationApiUrl("/items", "http://localhost:5173/", "/"), "http://localhost:5173/api/items");
});
