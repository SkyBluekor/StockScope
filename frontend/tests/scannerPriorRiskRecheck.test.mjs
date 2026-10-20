import assert from "node:assert/strict";
import test from "node:test";
import { scannerPriorRiskRecheck } from "../src/components/scannerPriorRiskRecheck.ts";

function candidate(overrides = {}) {
  return {
    code: "001820", name: "가상 종목", market: "KOSPI",
    data_date: "2026-10-14", current_price: 142500,
    risk: { status: "READY", warning: false, warnings: [] },
    conditions: { passed: 9, total: 9, missing: 0 },
    candidate_state: "READY",
    priority: { tier: "READY" },
    entry_risk_guide: {
      price_rule: { kind: "RANGE", range_low: 140000, range_high: 145000,
                    executable_entry_range: false },
      risk: { status: "READY", available: true, reference_only: false,
              entry_reference_price: 142500, invalidation_price: 136960.99 },
    },
    ...overrides,
  };
}
function quote(overrides = {}) {
  return {
    provider: "KIS", mode: "SNAPSHOT", market: "KOSPI", ticker: "001820",
    current_price: "130000", environment: "real",
    provider_timestamp: "2026-10-15T09:00:00+09:00",
    received_at: "2026-10-15T09:01:00+09:00",
    delivery: { source: "UPSTREAM", cache_age_ms: 0 },
    ...overrides,
  };
}
function snapshot(q = quote(), changes = {}) {
  return { quote: q, loading: false, error: null, marketSession: { market_active: true }, ...changes };
}

test("unqueried previous READY is never promoted into a buy instruction", () => {
  const original = candidate();
  const before = structuredClone(original);
  const r = scannerPriorRiskRecheck(original, { quote: null, loading: false, error: null, marketSession: null });
  assert.equal(r.state, "NOT_CHECKED");
  assert.equal(r.executionPermission, false);
  assert.equal(r.riskRevalidated, false);
  assert.equal(r.scannerVerdictChanged, false);
  assert.deepEqual(original, before);
});
test("valid matching later KIS quote below original invalidation has explicit reference breach", () => {
  const r = scannerPriorRiskRecheck(candidate(), snapshot());
  assert.equal(r.state, "OLD_REFERENCE_BREACHED");
  assert.equal(r.quotePrice, 130000);
  assert.equal(r.originalInvalidationReference, 136960.99);
  assert.equal(r.oldReferenceComparison, "AT_OR_BELOW");
  assert.equal(r.riskRevalidated, false);
  assert.equal(r.executionPermission, false);
  assert.match(r.explanation, /분석 당시/);
});
test("exactly equal to old invalidation price also counts as touched", () => {
  assert.equal(scannerPriorRiskRecheck(candidate(),
    snapshot(quote({ current_price: "136960.99" }))).state, "OLD_REFERENCE_BREACHED");
});
test("above previous invalidation is NOT a renewed READY or risk clearance", () => {
  const original = candidate();
  const result = scannerPriorRiskRecheck(original, snapshot(quote({ current_price: "138000" })));
  assert.equal(result.state, "OLD_REFERENCE_NOT_BREACHED");
  assert.equal(result.oldReferenceComparison, "ABOVE");
  assert.match(result.explanation, /유효하다는 뜻은 아니에요/);
  assert.equal(result.executionPermission, false);
  assert.equal(original.candidate_state, "READY");
});
test("wrong stock or market/provider quote is hidden from any old-reference comparison", () => {
  for (const change of [{ ticker: "999999" }, {market:"KOSDAQ"}, {provider:"NOT_KIS"}, {mode:"LIVE"}]) {
    const result = scannerPriorRiskRecheck(candidate(), snapshot(quote(change)));
    assert.equal(result.state, "QUOTE_UNVERIFIED");
    assert.equal(result.quotePrice, null);
    assert.equal(result.oldReferenceComparison, "NOT_COMPARABLE");
  }
});
test("no timestamp, future timestamp relative to receive or invalid amount fails closed", () => {
  const changes = [
    { provider_timestamp: null },
    { received_at: "bad" },
    { provider_timestamp: "2026-10-16T09:00:00+09:00" },
    { current_price: "NaN" },
    { current_price: "0" },
    { current_price: "-3" },
  ];
  for (const change of changes) {
    assert.equal(scannerPriorRiskRecheck(candidate(), snapshot(quote(change))).state,
      "QUOTE_UNVERIFIED");
  }
});
test("quote on or before analysis day cannot revalidate prior READY", () => {
  for (const provider_timestamp of [
    "2026-10-14T15:31:00+09:00", "2026-10-13T10:00:00+09:00",
  ]) {
    const r = scannerPriorRiskRecheck(candidate(), snapshot(quote({
      provider_timestamp, received_at: "2026-10-15T09:00:00+09:00",
    })));
    assert.equal(r.state, "QUOTE_NOT_AFTER_ANALYSIS");
    assert.equal(r.oldReferenceComparison, "NOT_COMPARABLE");
  }
});
test("invalid analysis date and missing reference block comparisons", () => {
  const wrongDate = scannerPriorRiskRecheck(candidate({ data_date: "2026-15-40" }), snapshot());
  assert.equal(wrongDate.state, "QUOTE_UNVERIFIED");
  for (const invalidation_price of [null, 0, 150000, Number.NaN]) {
    const item = candidate({entry_risk_guide: {risk: {
      available: true, status: "READY", entry_reference_price: 142500, invalidation_price,
    }}});
    const result = scannerPriorRiskRecheck(item, snapshot());
    assert.equal(result.state, "REFERENCE_UNAVAILABLE");
    assert.equal(result.originalInvalidationReference, null);
    assert.equal(result.executionPermission, false);
  }
});
test("cached KIS quote and closed market are timestamped past observation only", () => {
  const r = scannerPriorRiskRecheck(candidate(), snapshot(quote({
    delivery: { source: "CACHE", cache_age_ms: 5_000_000 },
    current_price: "130000",
  }), { marketSession: { market_active: false } }));
  assert.equal(r.state, "OLD_REFERENCE_BREACHED");
  assert.match(r.quoteSourceLabel, /보관된/);
  assert.equal(r.riskRevalidated, false);
});
test("loading and failure must clear old matched quote and NEVER retain green signal", () => {
  const q = quote();
  assert.equal(scannerPriorRiskRecheck(candidate(), snapshot(q, { loading: true })).state, "CHECKING");
  assert.equal(scannerPriorRiskRecheck(candidate(), snapshot(q, { error: "offline" })).state, "QUOTE_ERROR");
});
test("no special 10/14 identifiers: any Scanner candidate has identical fail-closed checks", () => {
  const item = candidate({
    code: "123456", market: "KOSDAQ", data_date: "2026-09-01",
  });
  const r = scannerPriorRiskRecheck(item, snapshot(quote({
    ticker: "123456", market: "KOSDAQ",
    provider_timestamp: "2026-09-02T09:00:00+09:00",
    received_at: "2026-09-02T09:01:00+09:00",
    current_price: "144000",
  })));
  assert.equal(r.state, "OLD_REFERENCE_NOT_BREACHED");
  assert.equal(r.analysisDate, "2026-09-01");
});
