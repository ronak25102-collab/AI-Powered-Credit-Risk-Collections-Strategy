import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { batchScorePortfolio, fetchPortfolio, predictRisk, setApiToken, setUserRole } from "../src/api.js";

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
const originalSetTimeout = globalThis.setTimeout;
const originalClearTimeout = globalThis.clearTimeout;

beforeEach(() => {
  const storage = () => {
    const values = new Map();
    return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  };
  globalThis.window = { localStorage: storage(), sessionStorage: storage() };
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.window = originalWindow;
  globalThis.setTimeout = originalSetTimeout;
  globalThis.clearTimeout = originalClearTimeout;
});

test("credentials and role are included without embedding secrets in the URL", async () => {
  setApiToken("  session-token  ");
  setUserRole("analyst");
  globalThis.fetch = async (url, options) => {
    assert.equal(options.headers.Authorization, "Bearer session-token");
    assert.equal(options.headers["X-User-Role"], "analyst");
    assert.ok(!url.includes("session-token"));
    return { ok: true, json: async () => ({ risk_score: 20 }) };
  };
  assert.deepEqual(await predictRisk({ income: 50000 }), { risk_score: 20 });
});

test("structured validation errors become readable messages", async () => {
  globalThis.fetch = async () => ({ ok: false, json: async () => ({ detail: [
    { loc: ["body", "income"], msg: "Input should be greater than 0" },
  ] }) });
  await assert.rejects(predictRisk({ income: -1 }), /income: Input should be greater than 0/);
});

test("uploads preserve the browser-generated multipart boundary", async () => {
  globalThis.fetch = async (_url, options) => {
    assert.ok(options.body instanceof FormData);
    assert.equal(options.headers["Content-Type"], undefined);
    return { ok: true, json: async () => ({ summary: {} }) };
  };
  await batchScorePortfolio(new Blob(["income\n50000"], { type: "text/csv" }));
});

test("portfolio filters and pagination are encoded", async () => {
  globalThis.fetch = async (url) => {
    const query = new URL(url).searchParams;
    assert.equal(query.get("search"), "Agent A & B");
    assert.equal(query.get("offset"), "20");
    assert.equal(query.get("summary_mode"), "light");
    return { ok: true, json: async () => ({ records: [] }) };
  };
  await fetchPortfolio({ search: "Agent A & B", offset: 20, summaryMode: "light" });
});

test("timeout also covers reading the response body", async () => {
  let expire;
  globalThis.setTimeout = (callback) => { expire = callback; return 1; };
  globalThis.clearTimeout = () => {};
  globalThis.fetch = async (_url, options) => ({ ok: true, json: () => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  }) });
  const pending = predictRisk({ income: 50000 });
  await Promise.resolve();
  expire();
  await assert.rejects(pending, /Request timed out/);
});
