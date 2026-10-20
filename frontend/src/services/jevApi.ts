import { SimulationApiError } from "./simulationApi.ts";

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


/** S31-P: local semantic router output is never an external JEV model result. */
export type JevCandidateLocalCheck = {
  version: string;
  capture_id: string;
  sample_index: number;
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  status: "LOCAL_CHECK_COMPLETE" | "LOCAL_EVIDENCE_COMPLETE" | "HOLD";
  reason_code: string | null;
  local_semantic_status: string | null;
  /** Provenance from the immutable Prospective capture, after its hash check. */
  capture_horizon_intent: "SHORT" | "MEDIUM" | "LONG" | "LEGACY_UNSPECIFIED" | "UNKNOWN" | null;
  capture_horizon_policy_version: string | null;
  local_v4_horizon_supported: boolean;
  local_evidence_scope: "NOT_CHECKED" | "V4_SUPPORTED_HORIZON" | "HORIZON_INDEPENDENT_ONLY";
  horizon_diagnostic_status: "NOT_CHECKED" | "LOCAL_V4_IN_SCOPE"
    | "LEGACY_HORIZON_UNSPECIFIED" | "LONG_OUTSIDE_LOCAL_V4" | "CAPTURE_HORIZON_UNKNOWN";
  check_stage: "REQUEST_VALIDATION" | "CAPTURE_LOOKUP" | "CAPTURE_INTEGRITY"
    | "HORIZON_SCOPE" | "ACTION_SCOPE" | "SEMANTIC_INPUT" | "COMPLETE"
    | "LOCAL_EVIDENCE_COMPLETE";
  next_action: string;
  headline: string;
  explanation: string;
  snapshot_hash: string | null;
  provider_review_suggested_by_local_state: boolean;
  provider_call_authorized: false;
  rights_for_real_market_transmission_verified: false;
  model_result_available: false;
  baseline_candidate_changed: false;
  review_kind: "LOCAL_SEMANTIC_CHECK_NOT_JEV_MODEL";
  jev_model_calls: 0;
  external_requests: 0;
  orders: 0;
  db_writes: 0;
};

export function getJevCandidateLocalCheck(params: {
  captureId: string;
  sampleIndex: number;
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
}): Promise<JevCandidateLocalCheck> {
  const query = new URLSearchParams({
    capture_id: params.captureId,
    sample_index: String(params.sampleIndex),
    market: params.market,
    ticker: params.ticker,
  });
  return jevJson<JevCandidateLocalCheck>(
    "/api/simulation/jev/candidate-local-check?" + query.toString(),
  );
}
