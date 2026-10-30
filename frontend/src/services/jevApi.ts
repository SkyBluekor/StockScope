import { SimulationApiError } from "./simulationApi";

type ApiErrorPayload = {
  detail?: string | { code?: string; message?: string };
};

async function jevJson<T>(
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
      : detail?.message ?? "TypeSafe Jev API 오류 (" + response.status + ")";
    const code = typeof detail === "object" && detail
      ? detail.code ?? null
      : null;
    throw new SimulationApiError(message, response.status, code);
  }
  return payload as T;
}

export type JevStatus = {
  available: boolean;
  engine: "TYPESAFE_V2" | string;
  core_status: string;
  trial_status: string;
  enabled: boolean;
  network_enabled: boolean;
  protocol_id: string | null;
  protocol_status: string | null;
  recruitment: {
    total: number;
    callable: number;
    skipped: number;
  };
  review_status: {
    pending: number;
    valid: number;
    error: number;
    late: number;
    interrupted: number;
  };
  disposition: {
    pass_through: number;
    review_required: number;
    abstain: number;
  };
  cost: {
    known_cost_usd: number;
    unknown_cost_count: number;
    reserved_exposure_usd: number;
  };
  code?: string;
};

export type JevMonitorItem = {
  capture_id: string;
  sample_index: number;
  market: string;
  ticker: string;
  name: string;
  recruitment_id: string;
  review_id: string | null;
  callable: boolean;
  skip_reason: string | null;
  operational_status:
    | "PENDING"
    | "VALID"
    | "ERROR"
    | "LATE"
    | "SKIPPED"
    | "INTERRUPTED"
    | string;
  disposition:
    | "PASS_THROUGH"
    | "REVIEW_REQUIRED"
    | "ABSTAIN"
    | null
    | string;
  uncertainty_reason: string | null;
  failure_code: string | null;
  integrity_status: string;
  model_identity_status: string | null;
  completed_at: string | null;
  latency_ms: number | null;
  reason_codes: string[];
};

export type JevReviewSummary = {
  total: number;
  pending: number;
  complete: number;
  review_required: number;
  abstain: number;
  error: number;
  late: number;
  skipped: number;
  interrupted: number;
};

export type JevReviewResponse = {
  available: boolean;
  engine: "TYPESAFE_V2" | string;
  capture_id: string;
  summary: JevReviewSummary;
  items: JevMonitorItem[];
  code?: string;
};

export function getJevStatus() {
  return jevJson<JevStatus>("/api/simulation/jev/status");
}

export function getJevReviews(captureId: string) {
  const params = new URLSearchParams({ capture_id: captureId });
  return jevJson<JevReviewResponse>(
    "/api/simulation/jev/reviews?" + params.toString(),
  );
}


export type JevReviewFeature = {
  execution_mode: "BASELINE_WITH_JEV" | string;
  feature_status: "DISABLED_VALIDATION_PENDING" | "ACTIVE" | string;
  available: boolean;
  reason: string;
};

export type JevManualReviewRequest = {
  capture_id: string;
  sample_index: number;
  review_epoch?: number;
};

export type JevManualReviewResult = {
  status:
    | "NOT_REQUESTED"
    | "UNAVAILABLE"
    | "NOT_READY"
    | "QUEUED"
    | "RUNNING"
    | "PASS_THROUGH"
    | "REVIEW_REQUIRED"
    | "ABSTAIN"
    | "SKIPPED"
    | "ERROR"
    | string;
  reason: string;
  reused: boolean;
  baseline_reference: {
    requested_capture_id: string;
    capture_id: string | null;
    sample_index: number;
    snapshot_hash: string | null;
  };
  review_id: string | null;
  review_identity: string | null;
  execution_mode: "BASELINE_WITH_JEV" | string;
  feature_status: string;
  reason_codes: string[];
};

export function getJevReviewFeature() {
  return jevJson<JevReviewFeature>("/api/simulation/jev/review-feature");
}

export function requestJevReview(payload: JevManualReviewRequest) {
  return jevJson<JevManualReviewResult>("/api/simulation/jev/reviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      capture_id: payload.capture_id,
      sample_index: payload.sample_index,
      review_epoch: payload.review_epoch ?? 0,
    }),
  });
}


/** LIVE-02: read-only local Scanner candidate diagnosis, never a model request. */
export type JevLocalReadiness = {
  version: string;
  capture_id: string;
  sample_index: number;
  identity: {
    snapshot_hash: string;
    signal_date: string | null;
    market: string;
    ticker: string;
    rank: number | null;
    strategy: string;
    action: string;
  };
  status: "LOCAL_READY" | "LOCAL_ONLY" | "NEEDS_EVIDENCE" | "SOURCE_RIGHTS_HOLD" | "NOT_ENTRY_CANDIDATE";
  local_readiness: string;
  local_v4_status: string;
  v4_semantic_status: string | null;
  input_contract: {
    horizon_intent: string | null;
    horizon_policy_version: string | null;
    horizon_support_status: string;
    horizon_reason_code: string | null;
    strategy_identity_status: string;
    original_strategy_identity: "CAPTURED_ORIGINAL" | "LEGACY_DERIVED_NOT_ORIGINAL" | "NOT_VERIFIED";
    capture_created_at: string | null;
    capture_started_at: string | null;
    capture_completed_at: string | null;
    source_first_published_at: null;
    source_publication_evidence: "UNVERIFIED";
  };
  integrity_reason_codes: string[];
  baseline_checks: Record<"rank" | "strategy" | "policy" | "engine" | "risk" | "dates", {
    status: string;
    code: string | null;
  }>;
  lineage_analysis_status: string;
  v4_outbound_lineage_status: string;
  source_origin_status: string;
  source_revision_status: string;
  publication_time_status: string;
  rights_status: string;
  transmission_decision: "NO_GO" | "NOT_REQUIRED" | "NOT_APPLICABLE";
  reason_codes: string[];
  model_review_executed: false;
  provider_eligible: false;
  actual_provider_calls: 0;
  db_writes: 0;
};

/** P5 local-only summary: these are NOT TypeSafe model results or permission. */
export type JevEntryRouting = {
  version: string;
  read_only: true;
  capture_id: string;
  canonical_capture_id: string | null;
  status: "COMPLETE" | "NO_ENTRY_CANDIDATE";
  entry_count: number;
  counts: Record<
    "LOCAL_MATCH" | "LOCAL_CONFLICT" | "LOCAL_INCOMPLETE" |
    "LOCAL_AMBIGUOUS" | "RESIDUAL_READY" | "RESIDUAL_BLOCKED" |
    "BLOCKED_EVIDENCE", number
  >;
  rows: Array<{
    sample_index: number;
    market: string;
    ticker: string;
    rank: number | null;
    snapshot_hash: string;
    routing: string;
    semantic_status: string | null;
    local_v4_status: string;
    v4_state_hash: string | null;
    strategy_identity: string;
    source_v2_valid: boolean;
    provider_decision: "HOLD";
    reason_codes: string[];
  }>;
  review_eligible_count: number;
  external_model_call_allowed: false;
  actual_provider_calls: 0;
  db_writes: 0;
};

/** P6-A local EventEvidence reference. Not a model response or event verdict. */
export type JevIndependentEventReference = {
  version: string;
  read_only: true;
  capture_id: string;
  sample_index: number;
  snapshot_hash: string;
  market: string;
  ticker: string;
  status: "NO_INDEPENDENT_EVIDENCE" | "EVIDENCE_UNCERTAIN" | "EVIDENCE_NOT_USABLE";
  reason_codes: string[];
  decision_cutoff: string | null;
  cutoff_source: string;
  event_reference_status: string;
  projection_hash: string | null;
  reference_count: number;
  source_kinds: string[];
  ai_input_rights: "NOT_APPROVED";
  independent_conflict_proven: false;
  review_needed: false;
  model_review_executed: false;
  external_model_call_allowed: false;
  actual_provider_calls: 0;
  db_writes: 0;
};

export function getJevIndependentEventReference(captureId: string, sampleIndex: number) {
  const params = new URLSearchParams({
    capture_id: captureId, sample_index: String(sampleIndex),
  });
  return jevJson<JevIndependentEventReference>(
    "/api/simulation/jev/independent-event-reference?" + params.toString(),
  );
}


/** P6-B is an operator-local event-assertion assessment, NOT a JEV result. */
export type JevIndependentEventAssessment = {
  version: string;
  read_only: true;
  capture_id: string;
  sample_index: number;
  snapshot_hash: string;
  market: string;
  ticker: string;
  status: "NO_INDEPENDENT_EVIDENCE" | "EVIDENCE_CONFLICT" |
    "EVIDENCE_COMPATIBLE" | "EVIDENCE_UNCERTAIN" | "EVIDENCE_NOT_USABLE";
  reason_codes: string[];
  decision_cutoff: string | null;
  reference_count: number;
  assertion_status: string;
  approved_assertion_count: number;
  reviewed_event_count: number;
  reviewed_assertion_refs: Array<{event_id: string; event_version: number; quality_hash: string; source_ref_id: string; source_ref_hash: string; assertion_hash: string; claim_id: string; relation: string; approved_at: string}>;
  retrospective_assertion_count: number;
  local_review_required: boolean;
  independent_review_candidate: boolean;
  assessment_origin: "OPERATOR_AUTHORED_LOCAL_ONLY";
  ai_input_rights: "NOT_APPROVED";
  independent_conflict_proven: false;
  model_review_executed: false;
  external_model_call_allowed: false;
  actual_provider_calls: 0;
  db_writes: 0;
};

export function getJevIndependentEventAssessment(captureId: string, sampleIndex: number) {
  const params = new URLSearchParams({
    capture_id: captureId, sample_index: String(sampleIndex),
  });
  return jevJson<JevIndependentEventAssessment>(
    "/api/simulation/jev/independent-event-assessment?" + params.toString(),
  );
}


export function getJevEntryRouting(captureId: string) {
  const params = new URLSearchParams({ capture_id: captureId });
  return jevJson<JevEntryRouting>(
    "/api/simulation/jev/entry-routing?" + params.toString(),
  );
}


export function getJevLocalReadiness(captureId: string, sampleIndex: number) {
  const params = new URLSearchParams({
    capture_id: captureId,
    // ProspectiveCatalog persists sample_index as zero-based; UI rank is one-based.
    sample_index: String(sampleIndex),
  });
  return jevJson<JevLocalReadiness>(
    "/api/simulation/jev/local-readiness?" + params.toString(),
  );
}


/** LIVE-03 audit metadata only: NEVER a transport grant or real model result. */
export type JevOutboundPreflight = {
  version: string;
  capture_id: string;
  sample_index: number;
  snapshot_hash: string;
  market: string;
  ticker: string;
  decision: "HOLD" | "DENY" | "NOT_APPLICABLE" | string;
  data_eligibility: string;
  execution_status: "NOT_AUTHORIZED";
  evaluation_mode: string;
  v4_local_status: string;
  recipient: string;
  purpose: string;
  requested_model: string;
  wire_ready: boolean;
  wire_audit: null | {
    model_id: string;
    field_count: number;
    http_body_sha256: string;
    http_body_bytes: number;
    outbound_projection_hash: string;
    all_actual_parent_revisions_verified: false;
    body_was_transmitted: false;
    field_verdicts: Array<{path: string; expected_parents: string[]; origin_verified: false;
      rights_status: string; time_status: string;}>;
  };
  trusted_rights_resolver: string;
  time_authenticity: string;
  reason_codes: string[];
  provider_eligible: false;
  actual_provider_calls: 0;
  db_writes: 0;
};

export function getJevOutboundPreflight(captureId: string, sampleIndex: number) {
  const params = new URLSearchParams({
    capture_id: captureId,
    sample_index: String(sampleIndex),
  });
  return jevJson<JevOutboundPreflight>(
    "/api/simulation/jev/outbound-preflight?" + params.toString(),
  );
}


/** Localhost-only LIVE-04 demonstration. Fixed fake stock; never selected ticker. */
export type JevSyntheticDemoStatus = {
  enabled: boolean;
  synthetic_only: true;
  status: "DISABLED" | "NOT_REQUESTED" | "QUEUED" | "RUNNING" | "VALID" | "ERROR" | "INTERRUPTED";
  fixture?: string;
  job_id?: string;
  reused?: boolean;
  capture_id?: string;
  sample_index?: number;
  mock_provider_requests?: number;
  actual_provider_calls: 0;
  result?: {
    review_id?: string | null;
    disposition?: "PASS_THROUGH" | "REVIEW_REQUIRED" | "ABSTAIN" | null;
    model_returned?: string | null;
    model_identity_status?: string;
    cost_usd?: number | null;
    cost_unknown?: boolean;
    failure_code?: string | null;
    reason_codes?: string[];
    usage?: { input_tokens: number; output_tokens: number } | null;
  };
};

export function getJevSyntheticDemoStatus() {
  return jevJson<JevSyntheticDemoStatus>("/api/simulation/jev/synthetic-demo/status");
}

export function startJevSyntheticDemo() {
  return jevJson<JevSyntheticDemoStatus>(
    "/api/simulation/jev/synthetic-demo/start",
    {
      method: "POST",
      headers: { "X-StockScope-Synthetic-Demo": "confirmed" },
    },
  );
}
