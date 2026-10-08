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


test("SC-UX4 READY says as-of entry conditions satisfied, not buy-now", () => {
  const ready = candidate({
    current_price: 89_400,
    entry_risk_guide: { price_rule: { kind: "ABOVE", trigger_price: 88_200, executable_entry_range: true } },
  });
  const view = beginnerCandidatePresentation(ready);
  assert.match(view.headline, /분석일 기준 진입 조건을 모두 충족/);
  assert.equal(view.why, "전체 투자 조건 6개 중 6개를 충족했어요.");
  assert.equal(view.asOfPrice.state, "IN_RANGE");
  assert.match(view.next, /새 시세/);
  assert.equal(view.nextActionLabel, "새 시세·전략 확인");
  assert.doesNotMatch(view.headline, /지금 매수|매수하세요/);
});

test("SC-UX4 missing condition uses stored label and current/required values", () => {
  const view = beginnerCandidatePresentation(candidate({
    priority: { tier: "NEAR_READY" },
    conditions: {
      passed: 8, total: 9, missing: 1,
      top_missing: [{ label: "거래량 회복", detail: "평균 거래량 대비 거래량이 부족합니다.", current_value: "80%", required_value: "120%" }],
    },
  }));
  assert.equal(view.why, "전체 투자 조건 9개 중 8개를 충족했어요.");
  assert.match(view.headline, /1개 부족/);
  assert.equal(view.missingConditions.length, 1);
  assert.deepEqual(view.missingConditions[0], {
    label: "거래량 회복", detail: "평균 거래량 대비 거래량이 부족합니다.", current: "80%", required: "120%",
  });
  assert.equal(view.nextActionLabel, "부족: 거래량 회복");
  assert.match(view.nextActionContext, /현재 80%.*필요 120%/);
});

test("SC-UX4 missing count survives absent or partial top_missing; no invented values", () => {
  const view = beginnerCandidatePresentation(candidate({
    priority: { tier: "NEAR_READY" },
    conditions: { passed: 8, total: 9, missing: 1, top_missing: [] },
  }));
  assert.equal(view.missingCount, 1);
  assert.equal(view.missingConditions.length, 0);
  assert.match(view.nextActionLabel, /상세 없음/);
  assert.doesNotMatch(view.nextActionContext, /현재.*필요/);
});

test("SC-UX4 risk block takes priority over missing conditions and price", () => {
  const view = beginnerCandidatePresentation(candidate({
    current_price: 89_400,
    conditions: {
      passed: 8, total: 9, missing: 1,
      top_missing: [{ label: "실제 미충족 조건", detail: "위험과 별개", current_value: "5", required_value: "10" }],
    },
    priority: { tier: "RISK_HOLD" },
    risk: { warning: true, warnings: ["변동성 경고"] },
  }));
  assert.match(view.headline, /위험 신호/);
  assert.match(view.caution, /변동성 경고/);
  assert.equal(view.nextActionLabel, "위험 차단 이유 확인");
  assert.equal(view.missingConditions[0].label, "실제 미충족 조건");
});

test("SC-UX4 missing/invalid condition counts must not turn into a ready recommendation", () => {
  const view = beginnerCandidatePresentation(candidate({
    conditions: { passed: 0, total: 0, missing: 0 },
  }));
  assert.match(view.headline, /자료가 부족/);
  assert.doesNotMatch(view.headline, /모두 충족/);
});

test("SC-UX4-S2 rephrases only verified negative market condition", () => {
  const view = beginnerCandidatePresentation(candidate({
    priority: { tier: "NEAR_READY" },
    conditions: {
      passed: 8, total: 9, missing: 1,
      top_missing: [{
        label: "시장 환경이 급격한 하락 상태가 아님",
        detail: "시장 상태가 조건에 맞지 않습니다.",
        current_value: "하락장", required_value: "상승장 또는 횡보장",
      }],
    },
  }));
  assert.equal(view.missingConditions[0].label, "현재 하락장이라 진입 조건 미충족");
  assert.equal(view.missingConditions[0].current, "하락장");
  assert.equal(view.missingConditions[0].required, "상승장 또는 횡보장");
  assert.match(view.nextActionLabel, /하락장/);
});

test("SC-UX4-S2 does not invent cause when market evidence differs", () => {
  const view = beginnerCandidatePresentation(candidate({
    priority: { tier: "NEAR_READY" },
    conditions: {
      passed: 8, total: 9, missing: 1,
      top_missing: [{
        label: "시장 환경이 급격한 하락 상태가 아님",
        current_value: "불명", required_value: "상승장 또는 횡보장",
      }],
    },
  }));
  assert.equal(view.missingConditions[0].label, "시장 환경이 급격한 하락 상태가 아님");
});
