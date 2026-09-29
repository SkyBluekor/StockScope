export type StrategyRegistryVersion = {
  strategy_version_id: string;
  strategy_key: string;
  definition_version: string;
  definition_hash: string;
  fingerprint_contract_version: string;
  implementation_key: string;
  operational_status: "CANDIDATE" | "OPERATING" | "ON_HOLD" | "DEMOTED" | string;
  validation_status: "UNVERIFIED" | "EVALUATING" | "VALIDATED" | "INSUFFICIENT_EVIDENCE" | "BLOCKED" | string;
  source: string;
  created_at: string;
  retired_at: string | null;
  evidence_count: number;
};

export type StrategyGovernanceOverview = {
  schema_version: string;
  schema_ready: boolean;
  registry: {
    total_version_count: number;
    operating_count: number;
    candidate_count: number;
    on_hold_count: number;
    demoted_count: number;
    validation_states: Record<string, number>;
  };
  evidence: {
    artifact_count: number;
    current_count: number;
    stale_or_missing_count: number;
    verification_error: { code: string; message: string } | null;
  };
  proposal: {
    latest_id: string | null;
    gate_state: string | null;
    verification_status: string | null;
  };
  approval: {
    latest_id: string | null;
    production_approval_available: boolean;
    blocked_reason: string | null;
    protocol_version: string;
  };
  production_policy: ProductionSelectionPolicyStatus;
  scanner_baseline: {
    scanner_version: string;
    baseline_id: string;
    production_fingerprint: string;
    production_policy_fingerprint: string;
  };
};

export type ProductionSelectionPolicyStatus = {
  policy_id: string;
  policy_hash: string;
  policy_contract_version: string;
  policy_source: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  active_reference_valid: boolean;
  policy_hash_valid: boolean;
  operating_strategy_count: number;
  operating_strategies: Array<{
    strategy_version_id: string | null;
    strategy_key: string;
    definition_hash: string | null;
  }>;
  rollback_available: boolean;
  generation: number | null;
  activation_source: string | null;
  reference_reason: string | null;
  scanner_baseline: StrategyGovernanceOverview["scanner_baseline"];
};

export type StrategyEvidenceArtifact = Record<string, unknown> & {
  id: string;
  strategy_version_id: string;
  strategy_key: string;
  evidence_state: string;
  artifact_hash: string;
  created_at: string;
  artifact_integrity?: string;
  current_source_status?: string;
};

export type StrategyEvidenceEligibilityRow = {
  strategy_key: string;
  sample_count: number;
  mature_count: number;
  evidence_state: string;
  identity_status: string;
  block_reason: string | null;
  creation_allowed: boolean;
  strategy_version_id: string | null;
  definition_hash: string | null;
  observed_sample_count: number;
  existing_artifact_id: string | null;
};

export type StrategyEvidenceEligibility = {
  source_kind: "PROSPECTIVE_REPORT" | string;
  source_report_id: string;
  source_status: string;
  report_version: string;
  evidence_state: string;
  restrictions: {
    minimum_sample_policy_defined: boolean;
    performance_conclusion_allowed: boolean;
    strategy_promotion_allowed: boolean;
    adaptive_rotation_enabled: boolean;
  };
  strategies: StrategyEvidenceEligibilityRow[];
};

export type StrategyChangeProposal = Record<string, unknown> & {
  id: string;
  approval_gate_state: string;
  proposal_hash: string;
  created_at: string;
};

export type StrategyApprovalArtifact = Record<string, unknown> & {
  id: string;
  proposal_id: string;
  approval_hash: string;
  approved_at: string;
};

type ApiErrorPayload = {
  detail?: string | { code?: string; message?: string };
};

export class StrategyGovernanceApiError extends Error {
  code: string | null;
  status: number;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "StrategyGovernanceApiError";
    this.code = code;
    this.status = status;
  }
}

async function apiJson<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const body = (
      payload && typeof payload === "object" ? payload : {}
    ) as ApiErrorPayload;
    const detail = body.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.message ?? "Strategy Governance API 오류 (" + response.status + ")";
    const code = typeof detail === "object" && detail
      ? detail.code ?? null
      : null;
    throw new StrategyGovernanceApiError(message, response.status, code);
  }
  return payload as T;
}

function postJson(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function getStrategyGovernanceOverview() {
  return apiJson<StrategyGovernanceOverview>(
    "/api/simulation/strategy-governance/overview",
  );
}

export function listStrategyRegistry() {
  return apiJson<StrategyRegistryVersion[]>(
    "/api/simulation/strategy-governance/registry",
  );
}

export function listStrategyEvidence(
  strategyVersionId?: string,
  verifySource = false,
) {
  const query = new URLSearchParams();
  if (strategyVersionId) {
    query.set("strategy_version_id", strategyVersionId);
  }
  query.set("verify_source", String(verifySource));
  return apiJson<StrategyEvidenceArtifact[]>(
    "/api/simulation/strategy-governance/evidence?" + query.toString(),
  );
}

export function getStrategyEvidenceEligibility(
  sourceReportId: string,
) {
  const query = new URLSearchParams({
    source_kind: "PROSPECTIVE_REPORT",
    source_report_id: sourceReportId,
  });
  return apiJson<StrategyEvidenceEligibility>(
    "/api/simulation/strategy-governance/evidence/eligibility?" + query.toString(),
  );
}

export function createStrategyEvidenceArtifact(input: {
  source_kind: "PROSPECTIVE_REPORT";
  source_report_id: string;
  strategy_version_id: string;
}) {
  return apiJson<StrategyEvidenceArtifact>(
    "/api/simulation/strategy-governance/evidence",
    postJson(input),
  );
}

export function listStrategyProposals(verify = false) {
  const query = new URLSearchParams({
    verify: String(verify),
  });
  return apiJson<StrategyChangeProposal[]>(
    "/api/simulation/strategy-governance/proposals?" + query.toString(),
  );
}

export function listStrategyApprovals() {
  return apiJson<StrategyApprovalArtifact[]>(
    "/api/simulation/strategy-governance/approvals",
  );
}

export function getProductionSelectionPolicy() {
  return apiJson<ProductionSelectionPolicyStatus>(
    "/api/simulation/strategy-governance/production-policy",
  );
}

export function createStrategyChangeProposal(input: {
  client_request_id: string;
  changes: Array<Record<string, unknown>>;
  evidence_artifact_ids: string[];
  affected_horizons: string[];
  affected_regimes: string[];
}) {
  return apiJson<StrategyChangeProposal>(
    "/api/simulation/strategy-governance/proposals",
    postJson(input),
  );
}

export function approveStrategyChangeProposal(
  proposalId: string,
  approvedBy = "LOCAL_USER",
) {
  return apiJson<StrategyApprovalArtifact>(
    "/api/simulation/strategy-governance/proposals/" +
      encodeURIComponent(proposalId) +
      "/approve",
    postJson({ approved_by: approvedBy }),
  );
}

export function activateProductionSelectionPolicy(input: {
  approval_artifact_id: string;
  expected_active_policy_id: string | null;
}) {
  return apiJson<Record<string, unknown>>(
    "/api/simulation/strategy-governance/production-policy/activate",
    postJson(input),
  );
}

export function rollbackProductionSelectionPolicy(
  expectedActivePolicyId: string,
) {
  return apiJson<Record<string, unknown>>(
    "/api/simulation/strategy-governance/production-policy/rollback",
    postJson({ expected_active_policy_id: expectedActivePolicyId }),
  );
}
