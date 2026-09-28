import { SimulationApiError } from "./simulationApi";

type ApiErrorPayload = { detail?: string | { code?: string; message?: string } };

async function feedbackJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) {
    const body = (payload && typeof payload === "object" ? payload : {}) as ApiErrorPayload;
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? `Feedback API 오류 (${response.status})`;
    const code = typeof detail === "object" && detail ? detail.code ?? null : null;
    throw new SimulationApiError(message, response.status, code);
  }
  return payload as T;
}

function post(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export type FeedbackSourceType = "TRACKING" | "VALIDATION" | "EXECUTION" | "BACKTEST";

export type FeedbackSelector = {
  source_type: FeedbackSourceType;
  source_id: string;
  date_from?: string | null;
  date_to?: string | null;
  market?: "KOSPI" | "KOSDAQ" | null;
  strategy?: string | null;
};

export type FeedbackSourceState = {
  source_order: number;
  source_type: FeedbackSourceType;
  source_id: string;
  selector: FeedbackSelector;
  status: "READY" | "EMPTY" | "ERROR" | string;
  error_code: string | null;
  error_message: string | null;
  evidence_count: number;
};

export type FeedbackEvidenceSnapshot = {
  source_type: FeedbackSourceType;
  source_id: string;
  source_item_id: string;
  source_hash: string;
  durability: "DURABLE" | "EPHEMERAL" | string;
  origin_kind: string;
  market: string | null;
  ticker: string | null;
  name: string | null;
  signal_date: string | null;
  strategy: string | null;
  decision_status: string | null;
  horizon_intent: string;
  maturity_status: string;
  inclusion_status: string;
  exclusion_reason: string | null;
  metrics: Record<string, unknown>;
  metadata: Record<string, unknown>;
  comparison_key: string;
  comparison_dimensions: Record<string, unknown>;
};

export type FeedbackCohortMember = {
  id: string;
  adapter_version: string;
  source_type: FeedbackSourceType;
  source_owner: string;
  source_id: string;
  source_item_id: string;
  source_hash: string;
  durability: string;
  origin_kind: string;
  comparison_key: string;
  comparison_dimensions: Record<string, unknown>;
  evidence: FeedbackEvidenceSnapshot;
  source_observed_at: string | null;
  created_at: string;
  inclusion_status: string;
  exclusion_reason: string | null;
};

export type FeedbackCohort = {
  id: string;
  client_request_id: string;
  name: string;
  cohort_version: string;
  filters: Record<string, unknown>;
  status: string;
  created_at: string;
  sources: FeedbackSourceState[];
  members: FeedbackCohortMember[];
  source_verification?: {
    status: string;
    counts: Record<string, number>;
  };
  reports?: FeedbackReport[];
};

export type FeedbackCohortListItem = {
  id: string;
  client_request_id: string;
  name: string;
  cohort_version: string;
  filters: Record<string, unknown>;
  status: string;
  member_count: number;
  included_count: number;
  created_at: string;
};

export type FeedbackMetric = {
  sample_count: number;
  average_pct: number | null;
  median_pct: number | null;
};

export type FeedbackComparisonGroup = {
  comparison_key: string;
  comparison_dimensions: Record<string, unknown>;
  member_count: number;
  source_types: Record<string, number>;
  maturity: Record<string, number>;
  metrics: {
    return_5d: FeedbackMetric;
    return_10d: FeedbackMetric;
    return_20d: FeedbackMetric;
    mfe: FeedbackMetric;
    mae: FeedbackMetric;
    realized_net_return: FeedbackMetric;
    realized_gross_return: FeedbackMetric;
    censored_mark_return: FeedbackMetric;
  };
  metric_sample_count: number;
  censored_is_realized_return: false;
};

export type FeedbackReport = {
  id: string;
  cohort_id: string;
  client_request_id: string;
  report_version: string;
  report_sequence: number;
  source_set_hash: string;
  status: string;
  effective_status?: string;
  source_changed_or_missing?: boolean;
  summary: {
    cohort_id: string;
    cohort_version: string;
    counts: {
      source_selector_count: number;
      source_error_count: number;
      member_count: number;
      included_count: number;
      excluded_count: number;
      comparison_group_count: number;
      metric_sample_count: number;
    };
    source_types: Record<string, number>;
    maturity: Record<string, number>;
    exclusion_reasons: Record<string, number>;
    source_errors: FeedbackSourceState[];
    comparison: {
      groups: FeedbackComparisonGroup[];
      cross_group_aggregation_allowed: false;
      different_comparison_keys_are_not_merged: true;
    };
    evidence_state: "INSUFFICIENT_EVIDENCE" | "SAMPLE_SIZE_POLICY_UNDEFINED" | string;
    minimum_sample_policy_defined: false;
    performance_conclusion_allowed: false;
    notes: string[];
  };
  created_at: string;
};

export function listFeedbackCohorts() {
  return feedbackJson<FeedbackCohortListItem[]>("/api/simulation/feedback/cohorts");
}

export function getFeedbackCohort(cohortId: string) {
  return feedbackJson<FeedbackCohort>(`/api/simulation/feedback/cohorts/${encodeURIComponent(cohortId)}`);
}

export function createFeedbackCohort(input: {
  client_request_id: string;
  name: string;
  sources: FeedbackSelector[];
  filters?: Record<string, unknown>;
}) {
  return feedbackJson<FeedbackCohort>("/api/simulation/feedback/cohorts", post(input));
}

export function createFeedbackReport(cohortId: string) {
  return feedbackJson<FeedbackReport>(
    `/api/simulation/feedback/cohorts/${encodeURIComponent(cohortId)}/reports`,
    post({ client_request_id: crypto.randomUUID() }),
  );
}

export function getFeedbackReport(reportId: string) {
  return feedbackJson<FeedbackReport>(`/api/simulation/feedback/reports/${encodeURIComponent(reportId)}`);
}
