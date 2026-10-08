import assert from "node:assert/strict";
import test from "node:test";
import {
  assessPriceRule,
  beginnerCandidatePresentation,
  priceReferenceText,
  simpleConditionStatus,
} from "../src/components/scannerDecisionPresentation.ts";

function candidate(overrides = {}) {
  const base = {
    code: "003930", name: "예시종목", market: "KOSPI",
    action: "ENTRY_CANDIDATE", current_price: 89_400,
    data_date: "2026-10-07", candidate_state: "READY",
    conditions: { passed: 6, total: 6, missing: 0, top_missing: [] },
    risk: { status: "READY", warning: false, warnings: [] },
    priority: { tier: "READY", label: "현재 진입 후보" },
    entry_risk_guide: {
      price_rule: {
        kind: "AT_OR_BELOW", trigger_price: 88_300,
        range_low: null, range_high: null, reference_price: 88_300,
        executable_entry_range: true,
      },
      action: { status: "WAIT" },
    },
  };
  return {
    ...base, ...overrides,
    conditions: { ...base.conditions, ...overrides.conditions },
    risk: { ...base.risk, ...overrides.risk },
    priority: { ...base.priority, ...overrides.priority },
    entry_risk_guide: {
      ...base.entry_risk_guide, ...overrides.entry_risk_guide,
      price_rule: {
        ...base.entry_risk_guide.price_rule,
        ...overrides.entry_risk_guide?.price_rule,
      },
      action: {
        ...base.entry_risk_guide.action,
        ...overrides.entry_risk_guide?.action,
      },
    },
  };
}

test("READY is an investment-conditions state, never a buy-now signal", () => {
  const result = beginnerCandidatePresentation(candidate());
  assert.equal(result.status, "투자 조건을 충족했어요");
  assert.equal(result.asOfPrice.state, "OUT_OF_RANGE");
  assert.match(result.headline, /분석 당시 가격/);
  assert.doesNotMatch(result.headline, /매수하세요|지금 사세요/);
  assert.match(result.next, /다시/);
});

test("NEAR_READY cannot become a buy signal merely because price is in range", () => {
  const example = candidate({
    current_price: 87_000, priority: { tier: "NEAR_READY" },
    conditions: { passed: 5, missing: 1 },
  });
  const view = beginnerCandidatePresentation(example);
  assert.match(view.headline, /기다려야/);
  assert.match(view.caution, /1개/);
  assert.equal(view.asOfPrice.state, "IN_RANGE");
  assert.doesNotMatch(view.headline, /매수하세요/);
});

test("risk warning takes precedence over price and conditions", () => {
  const view = beginnerCandidatePresentation(candidate({
    current_price: 87_000, risk: { warning: true, status: "WARNING" },
  }));
  assert.match(view.headline, /위험 신호/);
  assert.match(view.caution, /위험 경고/);
});

test("price comparison respects threshold direction and range edges", () => {
  const below = { kind: "AT_OR_BELOW", trigger_price: 88_300, executable_entry_range: true };
  const above = { kind: "ABOVE", trigger_price: 88_300, executable_entry_range: true };
  const range = { kind: "RANGE", range_low: 86_000, range_high: 88_300 };
  assert.equal(assessPriceRule(below, 88_300).state, "IN_RANGE");
  assert.equal(assessPriceRule(below, 89_400).state, "OUT_OF_RANGE");
  assert.equal(assessPriceRule(above, 89_400).state, "IN_RANGE");
  assert.equal(assessPriceRule(above, 88_000).state, "OUT_OF_RANGE");
  assert.equal(assessPriceRule(range, 86_000).state, "IN_RANGE");
  assert.equal(assessPriceRule(range, 88_300).state, "IN_RANGE");
  assert.equal(assessPriceRule(range, 88_301).state, "OUT_OF_RANGE");
});

test("reference-only and unavailable data fail closed instead of guessing", () => {
  const reference = { kind: "REFERENCE", reference_price: 88_300 };
  assert.equal(assessPriceRule(reference, 88_300).state, "UNKNOWN");
  assert.match(priceReferenceText(reference), /참고 가격/);
  assert.equal(assessPriceRule(null, 89_400).state, "UNKNOWN");
  assert.equal(assessPriceRule({ kind: "ABOVE", trigger_price: null }, 89_400).state, "UNKNOWN");
  assert.equal(assessPriceRule({ kind: "RANGE", range_low: 90_000, range_high: 80_000 }, 85_000).state, "UNKNOWN");
  assert.equal(assessPriceRule({ kind: "AT_OR_BELOW", trigger_price: 88_300 }, null).state, "UNKNOWN");
  assert.equal(assessPriceRule({ kind: "AT_OR_BELOW", trigger_price: 88_300 }, -1).state, "UNKNOWN");
});

test("NO_TRADE / RISK_HOLD wording is never READY", () => {
  assert.match(simpleConditionStatus(candidate({ action: "NO_TRADE", priority: { tier: "LOW_PRIORITY" } })), /아니에요/);
  assert.match(simpleConditionStatus(candidate({ priority: { tier: "RISK_HOLD" } })), /위험/);
});
