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
