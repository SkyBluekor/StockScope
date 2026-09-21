export type RecommendationPerformance = {
  recommendation_id: string;
  market_date: string | null;
  latest_date: string | null;
  latest_close: string | null;
  price_status: "FRESH" | "STALE" | "WAITING" | string;
  trading_days: number;
  current_return_pct: string | null;
  mfe_pct: string | null;
  mae_pct: string | null;
  highest_price: string | null;
  highest_date: string | null;
  lowest_price: string | null;
  lowest_date: string | null;
  return_5d: string | null;
  return_10d: string | null;
  return_20d: string | null;
  entry_touched: boolean;
  entry_touch_date: string | null;
  stop_touched: boolean;
  stop_touch_date: string | null;
  target1_touched: boolean;
  target1_touch_date: string | null;
  target2_touched: boolean;
  target2_touch_date: string | null;
  updated_at: string;
};

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
  performance: RecommendationPerformance | null;
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

export type TrackingRefreshSummary = {
  updated: number;
  unchanged: number;
  failed: number;
  latest_market_date: string | null;
  errors: Array<{ id: string; ticker: string; message: string }>;
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

export function refreshTrackedRecommendation(id: string) {
  return apiJson<TrackedRecommendation>(`/api/tracking/recommendations/${encodeURIComponent(id)}/refresh`, { method: "POST" });
}

export function refreshActiveTrackedRecommendations() {
  return apiJson<TrackingRefreshSummary>("/api/tracking/recommendations/refresh", { method: "POST" });
}
