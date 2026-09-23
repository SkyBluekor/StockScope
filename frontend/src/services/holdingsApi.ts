export type HoldingAnalysis = {
  market_date: string;
  revision_id: string;
  revision_no: number;
  strategy_key: string;
  action_state: string;
  risk_state: string;
  reference_price: string | null;
  stop_price: string | null;
  target1_price: string | null;
  target2_price: string | null;
  scanner_version?: string | null;
  analysis_engine_version?: string | null;
  policy_version?: string | null;
  revision_reason?: string | null;
  computed_at?: string | null;
};

export type HoldingPosition = {
  position_id: string;
  account_id: string;
  provider: string;
  account_kind: "BROKER" | "MANUAL" | "VIRTUAL" | string;
  broker_environment: string | null;
  account_name: string | null;
  status: string;
  opened_at: string | null;
  closed_at: string | null;
  quantity: string;
  average_price: string;
  cost_basis: string;
  opened_reason: string | null;
  last_observed_at: string | null;
};

export type HoldingConditionDetail = {
  label: string;
  detail: string | null;
  current_value: string | null;
  required_value: string | null;
  raw: string | null;
};

export type HoldingDecisionEntry = {
  state: "READY" | "WATCH" | "NOT_READY" | "BLOCKED" | "CAUTION" | "NO_TRADE" | "UNKNOWN" | string;
  label: string;
  summary: string | null;
  decision_reason: string | null;
  passed: number | null;
  missing: number | null;
  total: number | null;
  warnings: string[];
  missing_details: HoldingConditionDetail[];
};

export type HoldingStrategyContext = {
  state: "INITIAL" | "UNCHANGED" | "CHANGED" | string;
  current: string | null;
  previous: string | null;
  previous_market_date: string | null;
};

export type HoldingPreviousPlanContext = {
  state: "FIRST_PLAN" | "PREVIOUS_PLAN_UNAVAILABLE" | "WITHIN_PLAN" | "STOP_BREACHED" | "TARGET1_REACHED" | "TARGET2_REACHED" | string;
  label: string;
  previous_market_date: string | null;
  previous_reference_price: string | null;
  previous_stop_price: string | null;
  previous_target1_price: string | null;
  previous_target2_price: string | null;
  current_close: string | null;
};

export type HoldingDecisionContext = {
  entry: HoldingDecisionEntry;
  strategy: HoldingStrategyContext;
  previous_plan: HoldingPreviousPlanContext;
};

export type HoldingStock = {
  stock_id: string;
  market: "KOSPI" | "KOSDAQ" | string;
  ticker: string;
  name: string;
  watch_enabled: boolean;
  is_held: boolean;
  positions: HoldingPosition[];
  current_analysis: HoldingAnalysis | null;
  decision_context: HoldingDecisionContext | null;
  latest_position_event?: HoldingPositionEvent | null;
};

export type HoldingAccount = {
  id: string;
  provider: string;
  account_kind: "BROKER" | "MANUAL" | "VIRTUAL" | string;
  broker_environment: string | null;
  display_name: string | null;
  status: string;
};

export type HoldingPositionEvent = {
  event_id: string;
  position_id: string;
  event_type: string;
  quantity_delta: string | null;
  unit_price: string | null;
  before_quantity: string | null;
  after_quantity: string | null;
  before_average_price: string | null;
  after_average_price: string | null;
  observed_at: string | null;
  effective_at: string | null;
  analysis_revision_id: string | null;
  account_sync_run_id: string | null;
  note: string | null;
  created_at: string | null;
};

export type HoldingTimelineItem = {
  kind: "ANALYSIS" | "POSITION_EVENT" | string;
  occurred_at: string;
  market_date: string | null;
  analysis_revision_id: string | null;
  position_id: string | null;
  event_type: string | null;
  payload: Record<string, unknown>;
};

export type CurrentAnalysisResponse = {
  available: boolean;
  analysis: HoldingAnalysis | null;
};

export type KisSyncResponse = {
  status: string;
  sync_run_id: string;
  account_id: string;
  observed_at: string;
  page_count: number;
  holding_count: number;
  created: number;
  reconciled: number;
  closed: number;
  unchanged: number;
};

export type HoldingChartRange = "1m" | "3m" | "6m" | "1y";

export type HoldingChartBar = {
  date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
};

export type HoldingChartResponse = {
  market: string;
  ticker: string;
  range: HoldingChartRange;
  source: "MARKET_STORE_CONFIRMED_EOD" | string;
  from_date: string;
  to_date: string;
  requested_bars: number;
  count: number;
  bars: HoldingChartBar[];
};

export type HoldingDataFreshness = {
  status: "READY" | "UPDATED" | string;
  market: string;
  requested_date: string | null;
  latest_confirmed_date: string | null;
  resolved_as_of_date: string;
  known_data_date: string | null;
  market_data_updated: boolean;
  date_changed: boolean;
  network_requests: number;
  message: string;
};

export type HoldingAnalysisRefreshResponse = HoldingAnalysis & {
  created_revision: boolean;
  promoted_current: boolean;
  previous_analysis_date: string | null;
  data_freshness: HoldingDataFreshness;
};

type ApiErrorBody = {
  detail?: string | { code?: string; message?: string };
};

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (response.ok) return response.json() as Promise<T>;

  let message = `요청 실패 (${response.status})`;
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (body.detail?.message) {
      message = body.detail.message;
    }
  } catch {
    // Keep the safe fallback message.
  }
  throw new Error(message);
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: body == null ? undefined : { "Content-Type": "application/json" },
    body: body == null ? undefined : JSON.stringify(body),
  };
}

export function listHoldingStocks(): Promise<HoldingStock[]> {
  return requestJson<HoldingStock[]>("/api/holdings/stocks");
}

export function getHoldingStock(stockId: string): Promise<HoldingStock> {
  return requestJson<HoldingStock>(`/api/holdings/stocks/${encodeURIComponent(stockId)}`);
}

export function addWatchStock(input: {
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  name: string;
}): Promise<{ created: boolean; stock: HoldingStock }> {
  return requestJson<{ created: boolean; stock: HoldingStock }>("/api/holdings/watch", jsonInit("POST", input));
}

export function setWatchEnabled(
  stockId: string,
  enabled: boolean,
): Promise<{ stock: HoldingStock }> {
  return requestJson<{ stock: HoldingStock }>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/watch`,
    jsonInit("PATCH", { enabled }),
  );
}

export function listHoldingAccounts(): Promise<HoldingAccount[]> {
  return requestJson<HoldingAccount[]>("/api/holdings/accounts");
}

export function recordManualBuy(input: {
  stock_id: string;
  account_id?: string | null;
  quantity: string;
  unit_price: string;
  effective_at: string;
  analysis_revision_id?: string | null;
  note?: string | null;
}): Promise<unknown> {
  return requestJson("/api/holdings/manual/buy", jsonInit("POST", input));
}

export function recordManualSell(
  positionId: string,
  input: {
    quantity: string;
    unit_price: string;
    effective_at: string;
    note?: string | null;
  },
): Promise<unknown> {
  return requestJson(
    `/api/holdings/manual/${encodeURIComponent(positionId)}/sell`,
    jsonInit("POST", input),
  );
}

export function recordManualCorrection(
  positionId: string,
  input: {
    quantity: string;
    average_price: string;
    effective_at: string;
    note: string;
  },
): Promise<unknown> {
  return requestJson(
    `/api/holdings/manual/${encodeURIComponent(positionId)}/correction`,
    jsonInit("POST", input),
  );
}

export function getCurrentHoldingAnalysis(stockId: string): Promise<CurrentAnalysisResponse> {
  return requestJson<CurrentAnalysisResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis`,
  );
}

export function refreshHoldingAnalysis(
  stockId: string,
): Promise<HoldingAnalysisRefreshResponse> {
  return requestJson<HoldingAnalysisRefreshResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis/refresh?prepare_latest=true`,
    jsonInit("POST"),
  );
}

export function getHoldingTimeline(
  stockId: string,
  limit = 100,
): Promise<HoldingTimelineItem[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  return requestJson<HoldingTimelineItem[]>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/timeline?${query.toString()}`,
  );
}

export function getHoldingChart(
  stockId: string,
  range: HoldingChartRange,
): Promise<HoldingChartResponse> {
  const query = new URLSearchParams({ range });
  return requestJson<HoldingChartResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/chart?${query.toString()}`,
  );
}

export function syncKisHoldings(): Promise<KisSyncResponse> {
  return requestJson<KisSyncResponse>("/api/holdings/kis/sync", jsonInit("POST"));
}
