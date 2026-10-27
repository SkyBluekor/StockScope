import assert from "node:assert/strict";
import test from "node:test";
import { holdingPlanReview } from "../src/components/holdingPlanReview.ts";

function fixture() {
  const decision = {
    decision_id: "decision-1", position_id: "position-1", input_fingerprint: "fingerprint-1",
    source_analysis_revision_id: "revision-2", source_active_plan_id: "plan-1",
    source_active_plan_version: 1, stale: false,
    evidence: { new_plan_horizon_activatable: true, latest_analysis_differs_from_active_plan: true, proposal_conflict: null },
  };
  const management = {
    position_id: "position-1",
    active_plan: { plan_id: "plan-1", version: 1, stop_price: "90", target1_price: "120", target2_price: "130" },
    proposal: { can_apply: true, state: "NEW_REVISION", analysis_revision_id: "revision-2", market_date: "2026-10-21", reference_price: "105", stop_price: "95", target1_price: "125", target2_price: "135" },
  };
  return { decision, management };
}

test("matching decision and proposal show exact existing and proposed stops/targets", () => {
  const { decision, management } = fixture();
  const preview = holdingPlanReview(decision, management);
  assert.ok(preview);
  assert.deepEqual([preview.previousStop, preview.nextStop, preview.previousTarget1, preview.nextTarget1, preview.previousTarget2, preview.nextTarget2],
    ["90", "95", "120", "125", "130", "135"]);
});

test("first plan has no previous prices and still requires explicit confirmation", () => {
  const { decision, management } = fixture();
  decision.source_active_plan_id = null;
  decision.source_active_plan_version = null;
  management.active_plan = null;
  assert.equal(holdingPlanReview(decision, management)?.previousStop, null);
});

test("mismatched inputs, blocked proposal and stale decisions fail closed", () => {
  const cases = [
    ({ decision }) => { decision.stale = true; },
    ({ decision }) => { decision.effective_status = "STALE"; },
    ({ decision }) => { decision.evidence.proposal_conflict = "STOP_LOOSENING"; },
    ({ decision }) => { decision.evidence.new_plan_horizon_activatable = false; },
    ({ decision }) => { decision.source_active_plan_id = "different"; },
    ({ decision }) => { decision.source_analysis_revision_id = "old"; },
    ({ management }) => { management.position_id = "another-position"; },
    ({ management }) => { management.proposal.can_apply = false; },
    ({ management }) => { management.proposal.stop_price = "-2"; },
    ({ management }) => { management.proposal.stop_price = "89"; },
    ({ management }) => { management.proposal.state = "SAME_AS_ACTIVE"; },
  ];
  for (const mutate of cases) {
    const inputs = fixture();
    mutate(inputs);
    assert.equal(holdingPlanReview(inputs.decision, inputs.management), null);
  }
});

test("price or decision changes invalidate a pending confirmation key", () => {
  const { decision, management } = fixture();
  const first = holdingPlanReview(decision, management);
  management.proposal.stop_price = "96";
  assert.notEqual(first.key, holdingPlanReview(decision, management).key);
  management.proposal.stop_price = "95";
  decision.decision_id = "decision-2";
  assert.notEqual(first.key, holdingPlanReview(decision, management).key);
});
