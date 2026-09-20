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
