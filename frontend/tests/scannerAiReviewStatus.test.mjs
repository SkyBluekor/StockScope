import assert from "node:assert/strict";
import test from "node:test";
import {
  historicalReviewStatus, matchStoredJevReview, scannerAiReviewStatus,
} from "../src/components/scannerAiReviewStatus.ts";

const candidate = {
  code: "003930", market: "KOSPI", data_date: "2026-10-07",
  ai_review_presentation: {
    state: "LOCAL_COMPLETE", provider_status: "NOT_REQUESTED",
    summary: "로컬 의미 점검", strengths: ["조건 확인"], review_points: [],
  },
  historical_evidence: { verified: false, status: "DATA_UNAVAILABLE", unavailable_reason: "INSUFFICIENT_AVAILABLE_HISTORY" },
};
const result = {
  execution_mode: "BASELINE_ONLY",
  jev_review: { status: "NOT_REQUESTED" },
  prospective_capture: { canonical_capture_id: "capture-1" },
};
const args = { candidate, result, enabled: true, available: false, featureStatus: "DISABLED_VALIDATION_PENDING" };
const valid = {
  capture_id: "capture-1", sample_index: 0, market: "KOSPI", ticker: "003930",
  operational_status: "VALID", disposition: "PASS_THROUGH", review_id: "review-1",
  completed_at: "2026-10-08T05:00:00Z", integrity_status: "MATCHED",
  model_identity_status: "MATCHED", reason_codes: [],
};

test("base scan and local meaning checks are never Jev completion", () => {
  const state = scannerAiReviewStatus(args);
  assert.equal(state.state, "FEATURE_PENDING");
  assert.notEqual(state.state, "COMPLETE");
  assert.equal(state.source, "LOCAL");
});
test("disabled, pending, not-requested and input-missing are separate", () => {
  assert.equal(scannerAiReviewStatus({ ...args, enabled: false, available: true, featureStatus: "ACTIVE" }).state, "OFF");
  assert.equal(scannerAiReviewStatus({ ...args, available: true, featureStatus: "ACTIVE" }).state, "NOT_REQUESTED");
  assert.equal(scannerAiReviewStatus({
    ...args, available: true, featureStatus: "ACTIVE",
    candidate: { ...candidate, ai_review_presentation: { ...candidate.ai_review_presentation, state: "NOT_READY" } },
  }).state, "INPUT_MISSING");
});
test("valid identity and completed record are required before claiming Jev completion", () => {
  const base = { ...args, available: true, featureStatus: "ACTIVE" };
  assert.equal(scannerAiReviewStatus({ ...base, review: valid }).state, "COMPLETE");
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, disposition: "REVIEW_REQUIRED" } }).state, "NEEDS_REVIEW");
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, disposition: "ABSTAIN" } }).state, "ABSTAIN");
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, integrity_status: "MISMATCH" } }).state, "UNKNOWN");
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, model_identity_status: "ERROR" } }).state, "UNKNOWN");
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, review_id: null } }).state, "UNKNOWN");
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, completed_at: null } }).state, "UNKNOWN");
});
test("real queued and failed differ from never requested", () => {
  const base = { ...args, available: true, featureStatus: "ACTIVE" };
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, operational_status: "PENDING" } }).state, "QUEUED");
  assert.equal(scannerAiReviewStatus({ ...base, review: { ...valid, operational_status: "ERROR" } }).state, "FAILED");
  assert.equal(scannerAiReviewStatus({ ...base, review: null }).state, "NOT_REQUESTED");
});
test("capture, ticker, market and sample index must match", () => {
  assert.equal(matchStoredJevReview(valid, candidate, "capture-1", 0), true);
  assert.equal(matchStoredJevReview(valid, candidate, "capture-other", 0), false);
  assert.equal(matchStoredJevReview(valid, candidate, "capture-1", 1), false);
  assert.equal(matchStoredJevReview(valid, { ...candidate, code: "000001" }, "capture-1", 0), false);
  assert.equal(matchStoredJevReview(valid, { ...candidate, market: "KOSDAQ" }, "capture-1", 0), false);
});
test("historical evidence is independent of AI state", () => {
  assert.match(historicalReviewStatus(candidate), /데이터 부족/);
  assert.match(historicalReviewStatus({ ...candidate, historical_evidence: { verified: true } }), /완료/);
});


test("SC-UX4 disabled feature wins over saved preference OFF or ON", () => {
  for (const enabled of [true, false]) {
    const state = scannerAiReviewStatus({ ...args, enabled });
    assert.equal(state.state, "FEATURE_PENDING");
    assert.equal(state.label, "AI 검토 미제공");
  }
});
test("SC-UX4 server feature loading and failure never claim AI availability", () => {
  assert.equal(scannerAiReviewStatus({ ...args, featureStatus: "STATUS_LOADING" }).state, "FEATURE_LOADING");
  assert.equal(scannerAiReviewStatus({ ...args, featureStatus: "STATUS_ERROR" }).state, "FEATURE_ERROR");
  assert.equal(scannerAiReviewStatus({ ...args, featureStatus: null }).state, "FEATURE_ERROR");
});
