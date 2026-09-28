import { SimulationApiError } from "./simulationApi";

type ApiErrorPayload = { detail?: string | { code?: string; message?: string } };

async function prospectiveJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) {
    const body = (payload && typeof payload === "object" ? payload : {}) as ApiErrorPayload;
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? `평가 API 오류 (${response.status})`;
    const code = typeof detail === "object" && detail ? detail.code ?? null : null;
    throw new SimulationApiError(message, response.status, code);
  }
  return payload as T;
}

function post(body?: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  };
}

export type ProspectiveStatus = {
  schema_version: string;
  capture_counts: Record<string, number>;
  sample_count: number;
  first_signal_date: string | null;
  latest_signal_date: string | null;
  protocol_count: number;
  evaluation_run_count: number;
  minimum_sample_policy_defined: false;
  strategy_promotion_allowed: false;
  adaptive_rotation_enabled: false;
};

export type ProspectiveCapture = {
  id: string;
  source_job_id: string;
  status: string;
  scanner_version: string | null;
  market_scope: string;
  actual_data_date: string | null;
  actionable_candidate_count: number;
  returned_candidate_count: number;
  created_at: string;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
};

export type ProspectiveProtocol = {
  id: string;
  protocol_version: string;
  name: string;
  status: string;
  spec: {
    market_scope: string;
    strategy: string | null;
    development_start: string;
    development_end: string;
    holdout_start: string;
    holdout_end: string;
    observation_windows: number[];
    purge_trading_days: number;
    execution_mode: string;
    max_holding_days: number;
    round_trip_cost_pct: number;
    fee_pct: number;
    tax_pct: number;
    slippage_pct: number;
  };
  spec_hash: string;
  created_at: string;
};

export type ProspectiveRun = {
  id: string;
  protocol_id: string;
  status: string;
  source_capture_count: number;
  source_sample_count: number;
  development_count: number;
  holdout_count: number;
  purged_count: number;
  mature_count: number;
  immature_count: number;
  excluded_count: number;
  failed_count: number;
  processed_count: number;
  cancel_requested: boolean;
  restart_count: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type ProspectiveReport = {
  id: string;
  evaluation_run_id: string;
  report_version: string;
  source_set_hash: string;
  summary: {
    evidence_state: string;
    counts: {
      source_capture_count: number;
      source_sample_count: number;
      development_count: number;
      holdout_count: number;
      purged_count: number;
      mature_count: number;
      immature_count: number;
      excluded_count: number;
      failed_count: number;
    };
    candidate_observation: Record<string, {
      sample_count: number;
      average_pct: number | null;
      median_pct: number | null;
    }>;
    virtual_execution: {
      realized_net_return: { sample_count: number; average_pct: number | null; median_pct: number | null };
      censored_mark_return: { sample_count: number; average_pct: number | null; median_pct: number | null };
      censored_is_realized_return: false;
    };
    strategy_breakdown: Array<{
      strategy: string;
      sample_count: number;
      mature_count: number;
      return_20d: { sample_count: number; average_pct: number | null; median_pct: number | null };
      realized_net_return: { sample_count: number; average_pct: number | null; median_pct: number | null };
      execution_status: Record<string, number>;
    }>;
    minimum_sample_policy_defined: false;
    performance_conclusion_allowed: false;
    strategy_promotion_allowed: false;
    adaptive_rotation_enabled: false;
    notes: string[];
  };
  created_at: string;
};

export type ProspectiveEvaluationDetail = {
  run: ProspectiveRun;
  protocol: ProspectiveProtocol | null;
  report: ProspectiveReport | null;
  units: unknown[];
};

export function getProspectiveStatus() {
  return prospectiveJson<ProspectiveStatus>("/api/simulation/prospective/status");
}

export function listProspectiveCaptures(limit = 20) {
  return prospectiveJson<ProspectiveCapture[]>(`/api/simulation/prospective/captures?limit=${limit}`);
}

export function listProspectiveProtocols() {
  return prospectiveJson<ProspectiveProtocol[]>("/api/simulation/prospective/protocols");
}

export function createProspectiveProtocol(input: {
  client_request_id: string;
  name: string;
  market_scope: "ALL" | "KOSPI" | "KOSDAQ";
  strategy?: string | null;
  development_start: string;
  development_end: string;
  holdout_start: string;
  holdout_end: string;
  purge_trading_days?: number;
  max_holding_days?: number;
  round_trip_cost_pct?: number;
  fee_pct?: number;
  tax_pct?: number;
  slippage_pct?: number;
  execution_mode?: "PRODUCTION_POLICY" | "OBSERVATION_ONLY";
}) {
  return prospectiveJson<ProspectiveProtocol>(
    "/api/simulation/prospective/protocols",
    post(input),
  );
}

export function listProspectiveRuns(limit = 20) {
  return prospectiveJson<ProspectiveRun[]>(`/api/simulation/prospective/evaluation-runs?limit=${limit}`);
}

export function createProspectiveRun(protocolId: string) {
  return prospectiveJson<ProspectiveRun>(
    "/api/simulation/prospective/evaluation-runs",
    post({ protocol_id: protocolId, client_request_id: crypto.randomUUID() }),
  );
}

export function executeProspectiveRun(runId: string) {
  return prospectiveJson<ProspectiveEvaluationDetail>(
    `/api/simulation/prospective/evaluation-runs/${encodeURIComponent(runId)}/execute`,
    post(),
  );
}

export function getProspectiveRun(runId: string) {
  return prospectiveJson<ProspectiveEvaluationDetail>(
    `/api/simulation/prospective/evaluation-runs/${encodeURIComponent(runId)}`,
  );
}

export function cancelProspectiveRun(runId: string) {
  return prospectiveJson<ProspectiveRun>(
    `/api/simulation/prospective/evaluation-runs/${encodeURIComponent(runId)}/cancel`,
    post(),
  );
}
