import test from "node:test";
import assert from "node:assert/strict";
import {
  scannerJevCapturedHorizonLabel as horizon,
  scannerJevDiagnosticStageLabel as stage,
} from "../src/components/scannerJevHorizonCopy.ts";

test("legacy capture is explicitly unstated, not a fake SHORT classification", () => {
  assert.match(horizon("LEGACY_UNSPECIFIED"), /기간 미지정/);
  assert.doesNotMatch(horizon("LEGACY_UNSPECIFIED"), /단기/);
});
test("LONG remains a separate unsupported category, never downcast to MEDIUM", () => {
  assert.match(horizon("LONG"), /장기/);
  assert.match(horizon("LONG"), /대상 아님/);
  assert.notEqual(horizon("LONG"), horizon("MEDIUM"));
});
test("SHORT and MEDIUM record intent but do not imply active provider", () => {
  assert.equal(horizon("SHORT"), "단기 (SHORT)");
  assert.equal(horizon("MEDIUM"), "중기 (MEDIUM)");
});
test("missing or unknown period cannot be guessed", () => {
  assert.match(horizon(null), /확인 불가/);
  assert.match(horizon("HACKED"), /확인 불가/);
});
test("horizon failures are not misreported as strategy semantic deficiency", () => {
  assert.equal(stage("HORIZON_SCOPE"), "캡처 투자 기간 검사");
  assert.equal(stage("SEMANTIC_INPUT"), "전략·조건 의미 근거 검사");
  assert.notEqual(stage("HORIZON_SCOPE"), stage("SEMANTIC_INPUT"));
});
test("capture hash error and completed local check are distinctly labeled", () => {
  assert.match(stage("CAPTURE_INTEGRITY"), /해시/);
  assert.match(stage("COMPLETE"), /완료/);
});

test("S31-R legacy-only evidence has a distinct UI stage from in-scope V4", () => {
  assert.equal(stage("LOCAL_EVIDENCE_COMPLETE"), "기간과 무관한 전략 관계 검사 완료");
  assert.notEqual(stage("LOCAL_EVIDENCE_COMPLETE"), stage("COMPLETE"));
  assert.notEqual(stage("LOCAL_EVIDENCE_COMPLETE"), stage("HORIZON_SCOPE"));
  assert.equal(horizon("LEGACY_UNSPECIFIED"), "기간 미지정 (LEGACY_UNSPECIFIED)");
});
