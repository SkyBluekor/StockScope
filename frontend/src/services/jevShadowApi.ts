import { SimulationApiError } from "./simulationApi";

type ApiErrorPayload = {
  detail?: string | { code?: string; message?: string };
};

async function jevShadowJson<T>(
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
      payload && typeof payload === "object"
        ? payload
        : {}
    ) as ApiErrorPayload;
    const detail = body.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.message ?? "JEV Shadow API 오류 (" + response.status + ")";
    const code = typeof detail === "object" && detail
      ? detail.code ?? null
      : null;
    throw new SimulationApiError(
      message,
      response.status,
      code,
    );
  }

  return payload as T;
}

export type JevShadowStatus = {
  available: boolean;
  enabled: boolean;
  ready_for_activation: boolean;
  trial_status: string | null;
  protocol_status: string | null;
  network_enabled: boolean;
  status_counts: Record<string, number>;
  decision_counts: Record<string, number>;
  code?: string;
};

export type JevShadowMonitorItem = {
  capture_id: string;
  sample_index: number;
  market: string;
  ticker: string;
  name: string;
  status:
    | "PENDING"
    | "VALID"
    | "ERROR"
    | "LATE"
    | "SKIPPED"
    | "INTERRUPTED"
    | string;
  decision:
    | "PASS_THROUGH"
    | "REVIEW_REQUIRED"
    | "ABSTAIN"
    | null
    | string;
  failure_code: string | null;
  completed_at: string | null;
  latency_ms: number | null;
  reason_codes: string[];
};

export type JevShadowReviewSummary = {
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

export type JevShadowReviewResponse = {
  available: boolean;
  capture_id: string;
  summary: JevShadowReviewSummary;
  items: JevShadowMonitorItem[];
  code?: string;
};

export function getJevShadowStatus() {
  return jevShadowJson<JevShadowStatus>(
    "/api/simulation/jev-shadow/status",
  );
}

export function getJevShadowReviews(captureId: string) {
  const params = new URLSearchParams({
    capture_id: captureId,
  });
  return jevShadowJson<JevShadowReviewResponse>(
    "/api/simulation/jev-shadow/reviews?" + params.toString(),
  );
}
