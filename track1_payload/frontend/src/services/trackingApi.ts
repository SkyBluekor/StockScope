export type TrackedRecommendation = {
  id: string;
  ticker: string;
  name: string;
  market: string;
  source: "SCANNER" | "MANUAL" | string;
  recommendation_date: string;
  reference_price: string;
  scanner_version: string | null;
  scanner_baseline: string | null;
  strategy: string | null;
  decision_status: string | null;
  rank: number | null;
  entry_price: string | null;
  stop_price: string | null;
  target1_price: string | null;
  target2_price: string | null;
  snapshot: Record<string, unknown>;
  status: "ACTIVE" | "CLOSED" | string;
  created_at: string;
  closed_at: string | null;
};

export type TrackRecommendationInput = {
  ticker: string;
  name: string;
  market: string;
  recommendation_date: string;
  source?: "SCANNER" | "MANUAL";
  scanner_version?: string | null;
  scanner_baseline?: string | null;
  strategy?: string | null;
  decision_status?: string | null;
  rank?: number | null;
  entry_price?: string | number | null;
  stop_price?: string | number | null;
  target1_price?: string | number | null;
  target2_price?: string | number | null;
  snapshot?: Record<string, unknown>;
};

type ErrorBody = { detail?: string | { code?: string; message?: string } };

export class TrackingApiError extends Error {
  constructor(message: string, public status: number, public code: string | null = null) {
    super(message);
    this.name = "TrackingApiError";
  }
}

async function apiJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) {
    const body = (payload && typeof payload === "object" ? payload : {}) as ErrorBody;
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? `추천 추적 API 오류 (${response.status})`;
    const code = typeof detail === "object" && detail ? detail.code ?? null : null;
    throw new TrackingApiError(message, response.status, code);
  }
  return payload as T;
}

export function listTrackedRecommendations(status?: "ACTIVE" | "CLOSED") {
  const query = status ? `?status=${status}` : "";
  return apiJson<TrackedRecommendation[]>(`/api/tracking/recommendations${query}`);
}

export function addTrackedRecommendation(input: TrackRecommendationInput) {
  return apiJson<{ created: boolean; item: TrackedRecommendation }>("/api/tracking/recommendations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function closeTrackedRecommendation(id: string) {
  return apiJson<TrackedRecommendation>(`/api/tracking/recommendations/${encodeURIComponent(id)}/close`, { method: "POST" });
}
