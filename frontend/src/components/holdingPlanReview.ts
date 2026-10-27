import type { HoldingDecisionRecord, HoldingManagementResponse } from "../services/holdingsApi";

type PositionManagement = HoldingManagementResponse["positions"][number];

export type HoldingPlanReview = {
  key: string;
  previousVersion: number | null;
  previousStop: string | null;
  previousTarget1: string | null;
  previousTarget2: string | null;
  nextStop: string;
  nextTarget1: string | null;
  nextTarget2: string | null;
  proposalDate: string | null;
};

// Both the saved decision and the management proposal must describe the same
// position, analysis revision and active plan before offering a write action.
export function holdingPlanReview(
  decision: HoldingDecisionRecord | null,
  positionManagement: PositionManagement | null,
): HoldingPlanReview | null {
  if (!decision || !positionManagement || positionManagement.position_id !== decision.position_id) return null;
  if (decision.stale || decision.effective_status === "STALE") return null;
  if (!decision.source_analysis_revision_id || !decision.evidence.new_plan_horizon_activatable) return null;
  if (decision.evidence.proposal_conflict) return null;
  if (decision.source_active_plan_id !== null && !decision.evidence.latest_analysis_differs_from_active_plan) return null;

  const active = positionManagement.active_plan;
  const proposal = positionManagement.proposal;
  if (!proposal.can_apply || proposal.state !== "NEW_REVISION") return null;
  if (proposal.analysis_revision_id !== decision.source_analysis_revision_id) return null;
  if ((active?.plan_id ?? null) !== decision.source_active_plan_id) return null;
  if ((active?.version ?? null) !== decision.source_active_plan_version) return null;

  const stop = Number(proposal.stop_price);
  if (!proposal.stop_price || !Number.isFinite(stop) || stop <= 0) return null;
  if (active && stop < Number(active.stop_price)) return null;

  const key = JSON.stringify([
    decision.decision_id,
    decision.input_fingerprint,
    decision.source_analysis_revision_id,
    decision.source_active_plan_id,
    decision.source_active_plan_version,
    proposal.market_date ?? null,
    proposal.reference_price ?? null,
    proposal.stop_price,
    proposal.target1_price ?? null,
    proposal.target2_price ?? null,
  ]);
  return {
    key,
    previousVersion: active?.version ?? null,
    previousStop: active?.stop_price ?? null,
    previousTarget1: active?.target1_price ?? null,
    previousTarget2: active?.target2_price ?? null,
    nextStop: proposal.stop_price,
    nextTarget1: proposal.target1_price ?? null,
    nextTarget2: proposal.target2_price ?? null,
    proposalDate: proposal.market_date ?? null,
  };
}
