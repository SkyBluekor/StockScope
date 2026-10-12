import assert from "node:assert/strict";
import test from "node:test";
import { scannerMotionSteps } from "../src/components/scannerProgress.ts";

const states = (status, stage, details = {}) =>
  scannerMotionSteps(status, stage, details).map((item) => item.status);

test("queued and data confirmation only animate the real data phase", () => {
  assert.deepEqual(states("queued", "queued"), ["active", "waiting", "waiting"]);
  assert.deepEqual(states("running", "scanner_prepare_probe"), ["active", "waiting", "waiting"]);
  assert.deepEqual(states("running", "scanner_prepare_store"), ["active", "waiting", "waiting"]);
});

test("strategy analysis and final ranking use distinct user phases", () => {
  assert.deepEqual(states("running", "scanner_quick_filter"), ["done", "active", "waiting"]);
  assert.deepEqual(states("running", "scanner_deep_analysis"), ["done", "active", "waiting"]);
  assert.deepEqual(states("running", "scanner_priority_rank"), ["done", "done", "active"]);
});

test("finished or cached Scanner is not a Jev result", () => {
  for (const stage of ["scanner_complete", "scanner_cache", "scanner_priority_rank"]) {
    const steps = scannerMotionSteps("completed", stage, {});
    assert.deepEqual(steps.map((step) => step.status), ["done", "done", "done"]);
    assert.deepEqual(steps.map((step) => step.id), ["data", "analysis", "result"]);
    assert.equal(steps.some((step) => /AI|Jev|모델/.test(step.label)), false);
  }
});

test("cancelled and failed jobs never animate later unfinished phases", () => {
  assert.deepEqual(states("cancelled", "scanner_deep_analysis"), ["done", "cancelled", "waiting"]);
  assert.deepEqual(states("failed", "scanner_prepare_failed", { failed_stage: "scanner_prepare_probe" }), ["failed", "waiting", "waiting"]);
  // The server can replace stage with 'failed'; never guess an invisible phase.
  assert.deepEqual(states("failed", "failed"), ["waiting", "waiting", "waiting"]);
});

test("scope-specific background progress stays as one stable customer rail", () => {
  for (const market_scope of ["ALL", "KOSPI", "KOSDAQ"]) {
    const steps = scannerMotionSteps("running", "scanner_prepare_kospi_stock", { market_scope });
    assert.equal(steps.length, 3);
    assert.equal(steps[0].status, "active");
  }
});
