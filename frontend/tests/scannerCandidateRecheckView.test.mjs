import test from "node:test";
import assert from "node:assert/strict";
import {
  scannerRecheckFilterDescription as filter,
  scannerRecheckHeadline as headline,
  scannerSelectionAfterRecheck as selection,
  scannerRecheckCaptureDescription as capture,
} from "../src/components/scannerCandidateRecheckView.ts";

const candidates = [
  { market: "KOSDAQ", code: "005930", data_date: "2026-10-21" },
  { market: "KOSPI", code: "000660", data_date: "2026-10-21" },
];
const recheck = {
  market: "KOSPI", code: "145720", new_data_date: "2026-10-21",
  status: "TARGET_OUTSIDE_SCANNER_FILTER",
};

test("specific filter reason is explained without inventing NO_TRADE", () => {
  assert.match(headline(recheck), /필터 제외/);
  assert.match(filter("LOW_LIQUIDITY"), /거래대금/);
  assert.doesNotMatch(filter("LOW_LIQUIDITY"), /NO_TRADE/);
  assert.match(filter("거래정지 또는 거래 없음"), /확정한 것은 아닙니다/);
  assert.match(filter(undefined), /확인하지 못했습니다/);
  assert.match(filter("CUSTOM_FILTER"), /CUSTOM_FILTER/);
});

test("removed prior stock never silently selects unrelated #1", () => {
  const next = { candidates, more_candidates: [], candidate_recheck: recheck };
  assert.equal(selection(next, "KOSPI-145720"), null);
  assert.equal(selection(next, "KOSDAQ-005930"), null);
});

test("matched candidate selects exact market/code/date only", () => {
  const target = { market: "KOSPI", code: "145720", data_date: "2026-10-21" };
  const next = {
    candidates, more_candidates: [target],
    candidate_recheck: { ...recheck, status: "MATCHED_RETURNED_CANDIDATE" },
  };
  assert.equal(selection(next, null), "KOSPI-145720");
  next.candidate_recheck = { ...next.candidate_recheck, new_data_date: "2026-10-20" };
  assert.equal(selection(next, null), null);
});

test("normal Scanner still retains selection then falls back to first", () => {
  const next = { candidates, more_candidates: [], candidate_recheck: undefined };
  assert.equal(selection(next, "KOSPI-000660"), "KOSPI-000660");
  assert.equal(selection(next, "KOSPI-145720"), "KOSDAQ-005930");
});

test("failed and absent captures must not appear persisted", () => {
  assert.match(capture({ baseline_scanner_capture_status: "FAILED", baseline_scanner_capture_id: null }), /저장 완료 확인 불가/);
  assert.match(capture({ baseline_scanner_capture_status: "COMPLETE", baseline_scanner_capture_id: "abc" }), /abc/);
});
