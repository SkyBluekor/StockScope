export type SimulationPortfolio = {
  id: string;
  name: string;
  mode: "HISTORICAL" | "MANUAL_TRACKING" | "PAPER" | string;
  status: string;
  initial_cash: string;
  cash_balance: string;
  realized_pnl: string;
  positions_market_value: string;
  unrealized_pnl: string;
  total_equity: string;
  total_return_pct: string;
  open_position_count: number;
  default_scanner_baseline_id: string | null;
};

export type SimulationPosition = {
  id: string;
  portfolio_id: string;
  stock_code: string;
  stock_name: string;
  market: string;
  source: string;
  status: "OPEN" | "CLOSED" | string;
  quantity: number;
  average_entry_price: string;
  current_price: string;
  cost_basis: string;
  market_value: string;
  unrealized_pnl: string;
  unrealized_pnl_pct: string;
  realized_pnl: string;
  scanner_baseline_id: string | null;
  opened_at: string;
  closed_at: string | null;
};

export type SimulationSession = {
  session_id: string;
  portfolio_id: string;
  start_date: string;
  end_date: string | null;
  current_date: string;
  status: string;
};

export type PositionMark = {
  position_id: string;
  price_status: "FRESH" | "STALE" | "MISSING" | null;
  valuation_stale: boolean;
  mark_date: string | null;
  source_bar_date: string | null;
};


export type SimulationQuote = {
  stock_code: string;
  market: string;
  trading_date: string;
  close: string;
};
export type PlaybackResult = {
  session_id: string;
  previous_date: string;
  current_date: string;
  updated_positions: number;
  missing_positions: number;
  cash_balance: string;
  positions_market_value: string;
  total_equity: string;
  unrealized_pnl: string;
  realized_pnl: string;
};

type ApiErrorPayload = { detail?: string | { code?: string; message?: string } };

export class SimulationApiError extends Error {
  code: string | null;
  status: number;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "SimulationApiError";
    this.code = code;
    this.status = status;
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
    const body = (payload && typeof payload === "object" ? payload : {}) as ApiErrorPayload;
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? `Simulation API 오류 (${response.status})`;
    const code = typeof detail === "object" && detail ? detail.code ?? null : null;
    throw new SimulationApiError(message, response.status, code);
  }
  return payload as T;
}

function json(body: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function createSimulationPortfolio(name: string, initialCash: string) {
  return apiJson<SimulationPortfolio>("/api/simulation/portfolios", json({ name, initial_cash: initialCash, mode: "HISTORICAL" }));
}

export function getSimulationPortfolio(portfolioId: string) {
  return apiJson<SimulationPortfolio>(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}`);
}

export function getSimulationPositions(portfolioId: string) {
  return apiJson<SimulationPosition[]>(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/positions?status=OPEN`);
}

export function getSimulationMarks(portfolioId: string) {
  return apiJson<PositionMark[]>(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/position-marks`);
}

export function buySimulationPosition(portfolioId: string, input: {
  stock_code: string; stock_name: string; market: string; quantity: number; execution_price: string;
}) {
  return apiJson(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/buy`, json({
    ...input, source: "MANUAL", order_type: "MARKET", client_request_id: crypto.randomUUID(),
  }));
}

export function sellSimulationPosition(portfolioId: string, input: {
  position_id: string; quantity: number; execution_price: string;
}) {
  return apiJson(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/sell`, json({
    ...input, order_type: "MARKET", client_request_id: crypto.randomUUID(),
  }));
}

export function createSimulationSession(portfolioId: string, startDate: string, endDate?: string) {
  return apiJson<SimulationSession>(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/sessions`, json({
    start_date: startDate, end_date: endDate || null,
  }));
}

export function getSimulationSession(portfolioId: string) {
  return apiJson<SimulationSession>(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/session`);
}

export function nextSimulationDay(portfolioId: string) {
  return apiJson<PlaybackResult>(`/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/next-day`, { method: "POST" });
}

export function getSimulationQuote(portfolioId: string, stockCode: string, market = "KRX") {
  const query = new URLSearchParams({ market });
  return apiJson<SimulationQuote>(
    `/api/simulation/portfolios/${encodeURIComponent(portfolioId)}/quote/${encodeURIComponent(stockCode)}?${query.toString()}`,
  );
}


export type ValidationPeriodPreview = {
  market_scope: "ALL" | "KOSPI" | "KOSDAQ" | string;
  preset: "6m" | "1y" | "2y" | null;
  requested_start_month: string;
  requested_end_month: string;
  resolved_start_date: string;
  resolved_end_date: string;
  trading_days: number;
  minimum_trading_days: number;
  valid: boolean;
  market_data_latest_date: string;
  partial_end_month: boolean;
};

export type LegacyValidation = {
  portfolio_id: string;
  name: string;
  legacy_status: "LEGACY_SAVED" | string;
  portfolio_status: string;
  session_status: string | null;
  start_date: string | null;
  end_date: string | null;
  current_date: string | null;
  initial_cash: string;
  position_count: number;
  trade_count: number;
  created_at: string;
  updated_at: string;
};

export function previewValidationPeriod(input: {
  preset?: "6m" | "1y" | "2y";
  start_month?: string;
  end_month?: string;
  market_scope?: "ALL" | "KOSPI" | "KOSDAQ";
}) {
  const query = new URLSearchParams();
  if (input.preset) query.set("preset", input.preset);
  if (input.start_month) query.set("start_month", input.start_month);
  if (input.end_month) query.set("end_month", input.end_month);
  query.set("market_scope", input.market_scope ?? "ALL");
  return apiJson<ValidationPeriodPreview>(`/api/simulation/validation-periods/preview?${query.toString()}`);
}

export function validateValidationPeriod(input: {
  preset?: "6m" | "1y" | "2y";
  start_month?: string;
  end_month?: string;
  market_scope?: "ALL" | "KOSPI" | "KOSDAQ";
}) {
  return apiJson<ValidationPeriodPreview>("/api/simulation/validation-periods/validate", json({
    ...input,
    market_scope: input.market_scope ?? "ALL",
  }));
}

export function listLegacyValidations() {
  return apiJson<LegacyValidation[]>("/api/simulation/legacy-validations");
}

export type HistoricalValidationDraft = {
  id: string;
  name: string;
  validation_target: "PRODUCTION_SCANNER" | string;
  market_scope: "ALL" | "KOSPI" | "KOSDAQ" | string;
  scanner_version: string;
  scanner_baseline: string | null;
  requested_period_type: "6m" | "1y" | "2y" | "custom" | string;
  requested_start_month: string;
  requested_end_month: string;
  resolved_start_date: string;
  resolved_end_date: string;
  trading_day_count: number;
  status: "DRAFT" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  processed_day_count: number;
  candidate_count: number;
  last_completed_date: string | null;
  error_code: string | null;
  error_message: string | null;
  cancel_requested: boolean;
  runtime_active?: boolean;
};

export type HistoricalValidationDay = {
  validation_id: string;
  trading_date: string;
  status: string;
  scanner_version: string;
  market_scope: string;
  candidate_count: number;
  scanner_cache_hit: boolean;
  partial_data: boolean;
  input_fingerprint: unknown;
  result_hash: string | null;
  duration_ms: number;
  market_summary: unknown;
  summary: unknown;
  methodology: unknown;
  diagnostics: unknown;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
};

export type ValidationReplayResponse = {
  accepted: boolean;
  id: string;
  status: string;
  cancel_requested?: boolean;
};

export function createValidationDraft(input: {
  name: string;
  preset?: "6m" | "1y" | "2y";
  start_month?: string;
  end_month?: string;
  market_scope?: "ALL" | "KOSPI" | "KOSDAQ";
}) {
  return apiJson<HistoricalValidationDraft>("/api/simulation/validations", json({
    ...input,
    market_scope: input.market_scope ?? "ALL",
  }));
}

export function listValidationDrafts() {
  return apiJson<HistoricalValidationDraft[]>("/api/simulation/validations");
}

export function getValidationDraft(id: string) {
  return apiJson<HistoricalValidationDraft>(`/api/simulation/validations/${encodeURIComponent(id)}`);
}

export function runValidationReplay(id: string) {
  return apiJson<ValidationReplayResponse>(
    `/api/simulation/validations/${encodeURIComponent(id)}/run`,
    { method: "POST" },
  );
}

export function cancelValidationReplay(id: string) {
  return apiJson<ValidationReplayResponse>(
    `/api/simulation/validations/${encodeURIComponent(id)}/cancel`,
    { method: "POST" },
  );
}

export function listValidationDays(id: string) {
  return apiJson<HistoricalValidationDay[]>(
    `/api/simulation/validations/${encodeURIComponent(id)}/days`,
  );
}

export function deleteValidationDraft(id: string) {
  return apiJson<{ deleted: boolean; id: string }>(`/api/simulation/validations/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function deleteLegacyValidation(portfolioId: string) {
  return apiJson<{ deleted: boolean; portfolio_id: string }>(`/api/simulation/legacy-validations/${encodeURIComponent(portfolioId)}`, { method: "DELETE" });
}
