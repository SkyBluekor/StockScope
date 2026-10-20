import test from "node:test";
import assert from "node:assert/strict";
import { getJevSyntheticActualReceipts } from "../src/services/jevApi.ts";

test("S31-S only GETs local research history, never posts candidate payload", async () => {
  const before = globalThis.fetch;
  const urls = [];
  globalThis.fetch = async (path, init) => {
    urls.push(path);
    assert.equal(init, undefined);
    return { ok: true, status: 200, text: async () => JSON.stringify({
      status: "ACTUAL_RECEIPTS_FOUND", scope: "SYNTHETIC_ONLY",
      actual_provider_attempts_recorded: 1, actual_valid_receipts: 1,
      correct_against_synthetic_gold: 1, incorrect_against_synthetic_gold: 0,
      unverified_receipt_rows: 0, mock_rows_excluded: 3,
      real_stock_models_reviewed: 0, scanner_uplift_proven: false,
      model_calls_on_request: 0, external_requests_on_request: 0,
      db_writes_on_request: 0,
      provider_provenance: "LOCAL_JOURNAL_ORIGIN_CLAIM_NOT_CRYPTOGRAPHICALLY_ATTESTED",
      cost_basis: "PUBLIC_STANDARD_ESTIMATE_NOT_ACCOUNT_BILLING",
      results: [{ case_id: "s5-condition-contradiction", case_title: "전략 조건 충돌",
        state: "VALID", expected: "REVIEW_REQUIRED", observed: "REVIEW_REQUIRED",
        model: "jev-1.13.0", matches_expected: true, receipt_status: "JOURNAL_CONSISTENCY_CHECK_PASSED" }],
    }) };
  };
  try {
    const r = await getJevSyntheticActualReceipts();
    assert.deepEqual(urls, ["/api/simulation/jev/synthetic-actual-receipts"]);
    assert.equal(r.real_stock_models_reviewed, 0);
    assert.equal(r.model_calls_on_request, 0);
    assert.equal(r.results[0].matches_expected, true);
  } finally { globalThis.fetch = before; }
});
