import assert from "node:assert/strict";
import test from "node:test";
import {
  asOfPriorityLabel,
  EMPTY_SCANNER_QUOTE,
  quoteMatchesCandidate,
  quoteTimeText,
  scannerQuoteTruth,
} from "../src/components/scannerQuoteTruth.ts";

function candidate(overrides = {}) {
  return {
    code: "016360", market: "KOSPI", data_date: "2026-10-07",
    current_price: 89_400,
    priority: { tier: "READY", label: "현재 진입 후보" },
    risk: { warning: false, warnings: [] },
    conditions: { passed: 6, total: 6, missing: 0 },
    entry_risk_guide: {
      price_rule: {
        kind: "AT_OR_BELOW", trigger_price: 88_300,
        executable_entry_range: true,
      },
    },
    ...overrides,
  };
}

function quote(overrides = {}) {
  return {
    provider: "KIS", mode: "SNAPSHOT",
    ticker: "016360", market: "KOSPI", current_price: "86100",
    received_at: "2026-10-10T07:00:00+09:00",
    provider_timestamp: "2026-10-10T06:59:59+09:00",
    environment: "real",
    delivery: { source: "UPSTREAM", cache_age_ms: 0 },
    ...overrides,
  };
}

function withQuote(q = quote(), other = {}) {
  return {
    ...EMPTY_SCANNER_QUOTE,
    quote: q, marketSession: { market_active: true },
    ...other,
  };
}

test("READY is as-of only; manual quote remains unrequested", () => {
  const item = candidate();
  const view = scannerQuoteTruth(item, EMPTY_SCANNER_QUOTE);
  assert.equal(asOfPriorityLabel(item), "분석일 기준 진입 후보");
  assert.equal(view.state, "NOT_CHECKED");
  assert.equal(view.strategyRevalidated, false);
  assert.match(view.nextStep, /새 시세/);
  assert.equal(item.priority.tier, "READY");
});

test("out-of-range quote never downgrades original 6/6 priority, only annotates price", () => {
  const item = candidate({ entry_risk_guide: {
    price_rule: { kind: "ABOVE", trigger_price: 88_300, executable_entry_range: true },
  } });
  const before = structuredClone(item);
  const result = scannerQuoteTruth(item, withQuote());
  assert.equal(result.state, "OUT_OF_RANGE");
  assert.equal(result.strategyRevalidated, false);
  assert.match(result.stateLabel, /범위 밖/);
  assert.match(result.nextStep, /재검증/);
  assert.match(result.priceLabel, /86,100원/);
  assert.deepEqual(item, before);
});

test("in-range quote is NOT current strategy or Risk revalidation", () => {
  const result = scannerQuoteTruth(candidate(), withQuote());
  assert.equal(result.state, "IN_RANGE");
  assert.equal(result.strategyRevalidated, false);
  assert.match(result.nextStep, /여전히 재검증 전/);
});

test("missing condition and risk-block are not made READY by price", () => {
  const near = candidate({
    priority: { tier: "NEAR_READY", label: "근접" },
    conditions: { passed: 8, total: 9, missing: 1 },
  });
  const blocked = candidate({
    priority: { tier: "RISK_HOLD", label: "위험 차단" },
    risk: { warning: true, warnings: ["리스크"] },
  });
  const nearView = scannerQuoteTruth(near, withQuote());
  const riskView = scannerQuoteTruth(blocked, withQuote());
  assert.equal(nearView.state, "IN_RANGE");
  assert.equal(riskView.state, "IN_RANGE");
  assert.equal(asOfPriorityLabel(near), "분석일 기준 근접 후보");
  assert.equal(asOfPriorityLabel(blocked), "분석일 기준 위험 보류");
  assert.equal(near.conditions.missing, 1);
  assert.equal(blocked.risk.warning, true);
});

test("unknown price rules fail closed, no invented market decision", () => {
  const item = candidate({
    entry_risk_guide: {
      price_rule: { kind: "REFERENCE", reference_price: 88_300 },
    },
  });
  assert.equal(scannerQuoteTruth(item, withQuote()).state, "UNKNOWN");
  assert.equal(scannerQuoteTruth(item, withQuote(quote({ current_price: "0" }))).state, "UNKNOWN");
  assert.equal(scannerQuoteTruth(item, withQuote(quote({ current_price: "not-a-price" }))).state, "UNKNOWN");
  assert.equal(scannerQuoteTruth(item, withQuote(quote({ current_price: "NaN" }))).priceLabel, "가격 확인 불가");
});

test("a quote from the wrong ticker, market, or provider is rejected", () => {
  const item = candidate();
  for (const q of [
    quote({ ticker: "000000" }),
    quote({ market: "KOSDAQ" }),
    quote({ provider: "UNKNOWN" }),
    quote({ mode: "TICK" }),
  ]) {
    assert.equal(quoteMatchesCandidate(q, item), false);
    const view = scannerQuoteTruth(item, withQuote(q));
    assert.equal(view.state, "ERROR");
    assert.equal(view.priceLabel, "조회 가격 없음");
  }
});

test("quoted timestamp and cache/virtual environment are explicit, not realtime promises", () => {
  const item = candidate();
  const result = scannerQuoteTruth(item, withQuote(quote({
    delivery: { source: "CACHE", cache_age_ms: 7200000 },
    environment: "virtual",
    provider_timestamp: null,
  }), { marketSession: { market_active: false } }));
  assert.match(result.freshnessLabel, /보관된 시세/);
  assert.match(result.freshnessLabel, /모의투자/);
  assert.match(result.freshnessLabel, /제공 시각 확인 불가/);
  assert.match(result.marketLabel, /마지막 거래 가격/);
  assert.equal(quoteTimeText("invalid"), "시간 확인 불가");
});

test("loading and failed lookups hide earlier quotes rather than acting as fresh", () => {
  const item = candidate();
  const loading = scannerQuoteTruth(item, withQuote(quote(), { loading: true }));
  const failed = scannerQuoteTruth(item, withQuote(quote(), { error: "조회 실패" }));
  assert.equal(loading.state, "CHECKING");
  assert.equal(loading.priceLabel, "조회 가격 없음");
  assert.equal(failed.state, "ERROR");
  assert.equal(failed.priceLabel, "조회 가격 없음");
});
