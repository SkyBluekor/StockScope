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


/** Plan B — explicitly user-authored semantic review (no licensed market data). */
export type OwnedJevInput = {
  capture_id: string;
  sample_index: number;
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  required_condition: string;
  observed_meaning: string;
};
export type OwnedJevResult = {
  version: string;
  review_id: string;
  selected_stock: {
    capture_id: string;
    sample_index: number;
    snapshot_hash: string;
    market: string;
    ticker: string;
    stock_name: string;
  };
  wire_sha256: string;
  input_sha256: string;
  question_sha256: string;
  model_requested: string;
  status: "PENDING_OR_INTERRUPTED" | "PENDING" | "VALID" | "ERROR";
  started_at: string;
  completed_at?: string;
  disposition?: "PASS_THROUGH" | "REVIEW_REQUIRED" | "ABSTAIN";
  model_returned?: string;
  answer_noul?: number;
  response_sha256?: string;
  usage?: { input_tokens: number; output_tokens: number };
  cost_usd: number | null;
  cost_unknown: boolean;
  reused?: boolean;
  reason?: string;
};
export type OwnedJevPreview = {
  version: string;
  review_id: string;
  wire_sha256: string;
  input_sha256: string;
  question_sha256: string;
  model_requested: string;
  selected_stock: OwnedJevResult["selected_stock"];
  remote_input_scope: "USER_AUTHORED_TEXT_ONLY";
  market_data_sent: false;
  third_party_content_sent: false;
  estimated_cost_usd: null;
  cost_unknown: true;
  ready: boolean;
  reason: string;
  existing: OwnedJevResult | null;
};

export function previewOwnedJevReview(input: OwnedJevInput) {
  return jevJson<OwnedJevPreview>("/api/simulation/jev/manual-owned/preview", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(input),
  });
}
export function getOwnedJevLatest(input: Pick<OwnedJevInput, "capture_id" | "sample_index" | "market" | "ticker">) {
  const qs = new URLSearchParams({
    capture_id: input.capture_id,
    sample_index: String(input.sample_index),
    market: input.market,
    ticker: input.ticker,
  });
  return jevJson<{review: OwnedJevResult | null}>(
    "/api/simulation/jev/manual-owned/latest?" + qs.toString(),
  );
}
export function executeOwnedJevReview(input: OwnedJevInput, preview: OwnedJevPreview) {
  return jevJson<OwnedJevResult>("/api/simulation/jev/manual-owned/execute", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-StockScope-JEV-Approve": "paid-once-confirmed-v1",
    },
    body: JSON.stringify({
      ...input, preflight_sha256: preview.wire_sha256,
      confirm_paid_call: "유료 JEV 1회 실행",
      original_authored_attested: true,
    }),
  });
}
