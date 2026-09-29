import type { StockDataContract } from "./api";
import type { WatchPositionStatus } from "./watchApi";

export type HoldingHorizonContext = {
  intent: "SHORT" | "MEDIUM" | "LONG" | "LEGACY_UNSPECIFIED" | string;
  policy_version: string | null;
  support_status: "SUPPORTED" | "EVALUATION_PENDING" | "UNSUPPORTED" | "LEGACY_UNSPECIFIED" | string;
  reason_code: string | null;
  review_cycle_trading_days: number | null;
  time_stop_trading_days: number | null;
  strategy_support: Record<string, string> | null;
  required_inputs: string[] | null;
  confirmation_policy: string | null;
};

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
  horizon_context: HoldingHorizonContext;
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

export type HoldingChartPrepareProgress = {
  type: "progress" | "complete" | "error" | string;
  stage: string;
  message: string;
  current: number;
  required: number;
  status?: string;
};

export type HoldingChartPrepareResult = {
  status: "READY" | "PARTIAL_MAX_AVAILABLE" | string;
  market: string;
  ticker: string;
  range: HoldingChartRange;
  latest_confirmed_date: string;
  existing_rows: number;
  prepared_rows: number;
  final_rows: number;
  required_rows: number;
  network_requests: number;
  message: string;
};

type HoldingChartPrepareStreamEvent = HoldingChartPrepareProgress & {
  code?: string;
  current_rows?: number;
  required_rows?: number;
  result?: HoldingChartPrepareResult;
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

export type HoldingHistoryPrepare = {
  status: "READY" | "UPDATED" | string;
  market: string;
  ticker: string;
  market_date: string;
  existing_rows: number;
  prepared_rows: number;
  final_rows: number;
  required_rows: number;
  network_requests: number;
  message: string;
};

export type HoldingAnalysisInputProof = {
  revision_id: string;
  market: string;
  ticker: string;
  market_date: string;
  verification_result: "MATCH" | "MISMATCH";
  stored_fingerprint: string;
  current_fingerprint: string;
  generation: Record<string, unknown>;
  verified_at: string;
};

export type HoldingAnalysisRefreshResponse = HoldingAnalysis & {
  created_revision: boolean;
  promoted_current: boolean;
  previous_analysis_date: string | null;
  data_freshness: HoldingDataFreshness;
  history_prepare?: HoldingHistoryPrepare;
};

export type HoldingAnalysisPrepareProgress = {
  type: "progress" | "complete" | "error" | string;
  stage: string;
  message: string;
  stock_current?: number;
  stock_required?: number;
  index_current?: number;
  index_required?: number;
};

type HoldingAnalysisStreamEvent = HoldingAnalysisPrepareProgress & {
  code?: string;
  source_code?: string;
  current_rows?: number;
  required_rows?: number;
  result?: HoldingAnalysisRefreshResponse;
};

type ApiErrorDetail = {
  code?: string;
  message?: string;
  source_code?: string;
  current_rows?: number;
  required_rows?: number;
};

export type HoldingManagementPlan = {
  plan_id: string;
  position_id: string;
  version: number;
  status: string;
  source_type: string;
  source_analysis_revision_id: string;
  reference_price: string | null;
  stop_price: string;
  target1_price: string | null;
  target2_price: string | null;
  confirmation_policy: string;
  applied_at: string;
  change_reason: string | null;
  previous_plan_id: string | null;
  superseded_at: string | null;
  closed_at: string | null;
  horizon_context?: HoldingHorizonContext;
};

export type HoldingDecisionAction =
  | "HOLD"
  | "ADD"
  | "REDUCE"
  | "TAKE_PROFIT"
  | "STOP"
  | "EXIT"
  | string;

export type HoldingDecisionOption = {
  action: HoldingDecisionAction;
  state: "AVAILABLE" | "REVIEW" | "MANUAL_REVIEW" | "BLOCKED" | "NOT_TRIGGERED" | "DEFERRED" | string;
  reason: string;
};

export type HoldingDecisionRecord = {
  decision_id: string;
  position_id: string;
  decision_policy_version: string;
  status: "ACTIONABLE" | "REVIEW_REQUIRED" | "DEFERRED" | "INSUFFICIENT_DATA" | "CONFLICT" | string;
  effective_status?: "STALE" | string;
  primary_action: HoldingDecisionAction | null;
  source_analysis_revision_id: string | null;
  source_active_plan_id: string | null;
  source_active_plan_version: number | null;
  source_position_status: string;
  source_position_quantity: string;
  source_position_average_price: string | null;
  valuation_market_date: string | null;
  valuation_price: string | null;
  valuation_source: string | null;
  horizon_intent: string | null;
  horizon_policy_version: string | null;
  input_fingerprint: string;
  evidence: {
    plan_state?: string;
    proposal_conflict?: string | null;
    latest_analysis_differs_from_active_plan?: boolean;
    new_plan_horizon_activatable?: boolean;
    source?: Record<string, unknown>;
  };
  alternatives: HoldingDecisionOption[];
  limitations: Array<{ code: string; message: string }>;
  created_at: string;
  stale?: boolean;
  stale_reasons?: string[];
  reused?: boolean;
  resolutions?: Array<{
    resolution_id: string;
    selected_action: HoldingDecisionAction | null;
    resolution_type: string;
    note: string | null;
    resulting_plan_id: string | null;
    created_at: string;
  }>;
};

export type HoldingDecisionSupportResponse = {
  stock_id: string;
  market: string;
  ticker: string;
  positions: Array<{
    position_id: string;
    decision: HoldingDecisionRecord | null;
  }>;
};

export type HoldingManagementResponse = {
  stock_id: string;
  market: string;
  ticker: string;
  valuation: { available: boolean; market_date: string | null; price: string | null; source: string | null; message: string | null };
  positions: Array<{
    position_id: string;
    account_id: string;
    account_name: string | null;
    provider: string | null;
    management_state: string;
    active_plan: HoldingManagementPlan | null;
    distances: {
      stop: { amount: string | null; pct: string | null };
      target1: { amount: string | null; pct: string | null };
      target2: { amount: string | null; pct: string | null };
    };
    proposal: {
      state: string;
      can_apply: boolean;
      reason: string | null;
      analysis_revision_id: string | null;
      market_date?: string | null;
      action_state?: string | null;
      reference_price?: string | null;
      stop_price?: string | null;
      target1_price?: string | null;
      target2_price?: string | null;
    };
  }>;
};

export type LiveHoldingManagementProximityResponse = {
  stock_id: string;
  market: string;
  ticker: string;
  available: boolean;
  state: "FRESH" | "STALE" | "UNAVAILABLE";
  reason_code: string | null;
  quote: {
    provider: string;
    mode: string;
    venue: string;
    price: string;
    provider_timestamp: string | null;
    received_at: string;
    age_ms: number;
    freshness_seconds: number;
  } | null;
  positions: Array<{
    position_id: string;
    active_plan_id: string | null;
    plan_version: number | null;
    distances: {
      stop: { level: string | null; amount: string | null; pct: string | null };
      target1: { level: string | null; amount: string | null; pct: string | null };
      target2: { level: string | null; amount: string | null; pct: string | null };
    };
  }>;
};

export type HoldingPerformanceValuation = {
  available: boolean;
  market_date: string | null;
  price: string | null;
  source: string | null;
  message: string | null;
};

export type HoldingPositionPerformance = {
  position_id: string;
  account_id: string;
  provider: string;
  account_kind: "BROKER" | "MANUAL" | "VIRTUAL" | string;
  account_name: string | null;
  quantity: string;
  average_price: string | null;
  cost_basis: string | null;
  market_value: string | null;
  unrealized_pnl: string | null;
  unrealized_return_pct: string | null;
  confirmed_realized_pnl: string | null;
  recorded_sell_count: number;
  calculable_sell_count: number;
  tracked_pnl: string | null;
  calculation_status:
    | "COMPLETE_SINCE_TRACKING_START"
    | "PARTIAL"
    | "VALUATION_ONLY"
    | "UNAVAILABLE"
    | string;
  calculation_message: string;
  warnings: string[];
};

export type HoldingPerformanceResponse = {
  stock_id: string;
  market: string;
  ticker: string;
  valuation: HoldingPerformanceValuation;
  positions: HoldingPositionPerformance[];
  aggregate: {
    available: boolean;
    mode: string;
    position_count: number;
    potential_overlap: boolean;
    quantity?: string | null;
    cost_basis?: string | null;
    market_value?: string | null;
    unrealized_pnl?: string | null;
    unrealized_return_pct?: string | null;
    confirmed_realized_pnl?: string | null;
    tracked_pnl?: string | null;
  };
  calculation_status: string;
  warnings: string[];
};

export type HoldingRecoveryThesisState = "INTACT" | "WEAKENED" | "BROKEN" | "UNKNOWN";
export type HoldingRecoveryAction = "UNDECIDED" | "HOLD" | "REDUCE" | "EXIT" | "ADD_REVIEW";

export type HoldingRecoveryReview = {
  review_id: string;
  position_id: string;
  status: "OPEN" | "CLOSED";
  opened_at: string;
  opened_note: string | null;
  closed_at: string | null;
  close_reason: string | null;
  close_note: string | null;
  created_at: string;
  updated_at: string;
};

export type HoldingRecoveryAssessment = {
  assessment_id: string;
  review_id: string;
  position_id: string;
  thesis_state: HoldingRecoveryThesisState;
  review_action: HoldingRecoveryAction;
  reason_note: string | null;
  source_analysis_revision_id: string | null;
  source_active_plan_id: string | null;
  source_active_plan_version: number | null;
  source_position_status: string;
  source_position_quantity: string;
  source_position_average_price: string | null;
  valuation_market_date: string | null;
  valuation_price: string | null;
  unrealized_pnl: string | null;
  unrealized_return_pct: string | null;
  linked_decision_id: string | null;
  limitations: string[];
  evidence: Record<string, unknown>;
  created_at: string;
};

export type HoldingRecoveryContext = {
  position_id: string;
  open_review: HoldingRecoveryReview | null;
  latest_open_assessment: HoldingRecoveryAssessment | null;
  reviews: HoldingRecoveryReview[];
  review_history: Array<{
    review: HoldingRecoveryReview;
    assessments: HoldingRecoveryAssessment[];
  }>;
  current: {
    evidence_version: string;
    stock: { stock_id: string; market: string; ticker: string; name: string };
    position: {
      position_id: string;
      status: string;
      quantity: string;
      average_price: string | null;
      cost_basis: string | null;
      opened_at: string;
      closed_at: string | null;
    };
    valuation: HoldingPerformanceValuation;
    performance: HoldingPositionPerformance | null;
    analysis: {
      market_date: string;
      revision_id: string;
      revision_no: number;
      strategy_key: string | null;
      action_state: string | null;
      risk_state: string | null;
      reference_price: string | null;
      stop_price: string | null;
      target1_price: string | null;
      target2_price: string | null;
      policy_version: string | null;
      computed_at: string;
    } | null;
    active_plan: HoldingManagementPlan | null;
    latest_decision: HoldingDecisionRecord | null;
    limitations: string[];
  };
};

export type HoldingWorkspaceSourceStatus = {
  status: string;
  reason_code: string | null;
};

export type HoldingWorkspacePositionContext = {
  position: HoldingPosition;
  performance: HoldingPositionPerformance | null;
  management: HoldingManagementResponse["positions"][number] | null;
  decision: HoldingDecisionRecord | null;
  user_choice: NonNullable<HoldingDecisionRecord["resolutions"]>[number] | null;
  recovery: HoldingRecoveryContext | null;
  recovery_status: HoldingWorkspaceSourceStatus;
  watch: WatchPositionStatus;
  review_conditions: string[];
};

export type HoldingWorkspaceContext = {
  context_version: "HOLDINGS_WORKSPACE_CONTEXT_V1" | string;
  checked_at: string;
  stock: HoldingStock;
  context_identity: {
    stock_id: string;
    market: string;
    ticker: string;
    market_confirmed_date: string | null;
    analysis_revision_id: string | null;
    analysis_market_date: string | null;
    analysis_input_fingerprint: string | null;
    fingerprint_contract_version: string | null;
    selection_policy_id: string | null;
    selection_policy_hash: string | null;
    selection_policy_contract_version: string | null;
    strategy_version_id: string | null;
    strategy_definition_hash: string | null;
    positions: Array<{
      position_id: string;
      active_plan_id: string | null;
      active_plan_version: number | null;
      decision_id: string | null;
      recovery_review_id: string | null;
      watch_setting_id: string | null;
    }>;
  };
  source_status: Record<string, HoldingWorkspaceSourceStatus>;
  current_state: {
    held: boolean;
    analysis_status: string;
    analysis_current_use_allowed: boolean;
    analysis_reason_code: string | null;
    valuation: HoldingPerformanceValuation | null;
    attention_required: boolean;
    review_conditions: string[];
  };
  data_contract: StockDataContract;
  performance: HoldingPerformanceResponse | null;
  management: HoldingManagementResponse | null;
  positions: HoldingWorkspacePositionContext[];
};

export type LiveHoldingPerformanceResponse = {
  stock_id: string;
  market: string;
  ticker: string;
  available: boolean;
  state: "FRESH" | "STALE" | "UNAVAILABLE";
  reason_code: string | null;
  quote: {
    provider: string;
    mode: string;
    venue: string;
    price: string;
    provider_timestamp: string | null;
    received_at: string;
    age_ms: number;
    freshness_seconds: number;
  } | null;
  performance: HoldingPerformanceResponse | null;
};

type ApiErrorBody = {
  detail?: string | ApiErrorDetail;
};

export class HoldingsApiError extends Error {
  code: string | null;
  status: number;
  detail: ApiErrorDetail | null;

  constructor(message: string, code: string | null, status: number, detail: ApiErrorDetail | null) {
    super(message);
    this.name = "HoldingsApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (response.ok) return response.json() as Promise<T>;

  let message = `요청 실패 (${response.status})`;
  let code: string | null = null;
  let detail: ApiErrorDetail | null = null;
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (body.detail) {
      detail = body.detail;
      code = body.detail.code ?? null;
      if (body.detail.message) message = body.detail.message;
    }
  } catch {
    // Keep the safe fallback message.
  }
  throw new HoldingsApiError(message, code, response.status, detail);
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

export function getHoldingWorkspaceContext(
  stockId: string,
  options: { signal?: AbortSignal } = {},
): Promise<HoldingWorkspaceContext> {
  return requestJson<HoldingWorkspaceContext>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/workspace-context`,
    { signal: options.signal },
  );
}

export function getHoldingStock(
  stockId: string,
  options: { signal?: AbortSignal } = {},
): Promise<HoldingStock> {
  return requestJson<HoldingStock>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}`,
    { signal: options.signal },
  );
}

export function addWatchStock(input: {
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  name: string;
}): Promise<{ created: boolean; stock: HoldingStock }> {
  return requestJson<{ created: boolean; stock: HoldingStock }>("/api/holdings/watch", jsonInit("POST", input));
}


export function registerHeldStock(input: {
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  name: string;
  quantity: string;
  average_price: string;
  effective_at: string;
  account_id?: string | null;
}): Promise<{ created: boolean; stock: HoldingStock; position: unknown; event: HoldingPositionEvent }> {
  return requestJson(
    "/api/holdings/held",
    jsonInit("POST", input),
  );
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

export function getHoldingDecisionSupport(
  stockId: string,
  options: { signal?: AbortSignal } = {},
): Promise<HoldingDecisionSupportResponse> {
  return requestJson<HoldingDecisionSupportResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/decision-support`,
    { signal: options.signal },
  );
}

export function evaluateHoldingDecision(
  positionId: string,
): Promise<{ decision: HoldingDecisionRecord }> {
  return requestJson<{ decision: HoldingDecisionRecord }>(
    `/api/holdings/positions/${encodeURIComponent(positionId)}/decisions/evaluate`,
    jsonInit("POST"),
  );
}

export function resolveHoldingDecision(
  decisionId: string,
  input: {
    resolution_type: "KEEP_CURRENT_PLAN" | "ACKNOWLEDGED" | "DEFERRED";
    selected_action?: HoldingDecisionAction | null;
    note?: string | null;
  },
): Promise<{ decision: HoldingDecisionRecord }> {
  return requestJson<{ decision: HoldingDecisionRecord }>(
    `/api/holdings/decisions/${encodeURIComponent(decisionId)}/resolve`,
    jsonInit("POST", input),
  );
}

export function applyHoldingDecisionPlan(
  decisionId: string,
  input: {
    selected_action?: HoldingDecisionAction | null;
    note?: string | null;
  } = {},
): Promise<{
  decision: HoldingDecisionRecord;
  plan: HoldingManagementPlan;
  plan_context: {
    context_version: string;
    source_decision_id: string;
    selected_action: HoldingDecisionAction | null;
    review_cycle_trading_days: number | null;
    time_stop_trading_days: number | null;
  };
}> {
  return requestJson(
    `/api/holdings/decisions/${encodeURIComponent(decisionId)}/apply-plan`,
    jsonInit("POST", input),
  );
}

export function getHoldingRecovery(
  positionId: string,
  options: { signal?: AbortSignal } = {},
): Promise<HoldingRecoveryContext> {
  return requestJson<HoldingRecoveryContext>(
    `/api/holdings/positions/${encodeURIComponent(positionId)}/recovery`,
    { signal: options.signal },
  );
}

export function startHoldingRecovery(
  positionId: string,
  note?: string | null,
): Promise<{ created: boolean; review: HoldingRecoveryReview; context: HoldingRecoveryContext }> {
  return requestJson(
    `/api/holdings/positions/${encodeURIComponent(positionId)}/recovery/start`,
    jsonInit("POST", { note: note ?? null }),
  );
}

export function recordHoldingRecoveryAssessment(
  reviewId: string,
  input: {
    thesis_state: HoldingRecoveryThesisState;
    review_action: HoldingRecoveryAction;
    reason_note?: string | null;
    linked_decision_id?: string | null;
  },
): Promise<{ assessment: HoldingRecoveryAssessment; context: HoldingRecoveryContext }> {
  return requestJson(
    `/api/holdings/recovery/${encodeURIComponent(reviewId)}/assessments`,
    jsonInit("POST", input),
  );
}

export function closeHoldingRecovery(
  reviewId: string,
  input: { reason?: string | null; note?: string | null } = {},
): Promise<{ closed: boolean; review: HoldingRecoveryReview; context: HoldingRecoveryContext }> {
  return requestJson(
    `/api/holdings/recovery/${encodeURIComponent(reviewId)}/close`,
    jsonInit("POST", input),
  );
}

export function getHoldingManagement(
  stockId: string,
  options: { signal?: AbortSignal } = {},
): Promise<HoldingManagementResponse> {
  return requestJson<HoldingManagementResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/management`,
    { signal: options.signal },
  );
}

export function getLiveHoldingManagementProximity(
  stockId: string,
  options: { signal?: AbortSignal } = {},
): Promise<LiveHoldingManagementProximityResponse> {
  return requestJson<LiveHoldingManagementProximityResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/management/live-proximity`,
    { signal: options.signal },
  );
}

export function applyHoldingManagementPlan(
  positionId: string,
  analysisRevisionId: string,
): Promise<{ plan: HoldingManagementPlan }> {
  return requestJson<{ plan: HoldingManagementPlan }>(
    `/api/holdings/positions/${encodeURIComponent(positionId)}/plans/apply`,
    jsonInit("POST", { analysis_revision_id: analysisRevisionId, change_reason: null }),
  );
}

export function getHoldingPerformance(
  stockId: string,
  options: { signal?: AbortSignal } = {},
): Promise<HoldingPerformanceResponse> {
  return requestJson<HoldingPerformanceResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/performance`,
    { signal: options.signal },
  );
}

export function getLiveHoldingPerformance(
  stockId: string,
  options: { signal?: AbortSignal } = {},
): Promise<LiveHoldingPerformanceResponse> {
  return requestJson<LiveHoldingPerformanceResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/performance/live`,
    { signal: options.signal },
  );
}

export function getCurrentHoldingAnalysis(stockId: string): Promise<CurrentAnalysisResponse> {
  return requestJson<CurrentAnalysisResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis`,
  );
}

export function verifyHoldingAnalysisInput(
  stockId: string,
): Promise<{ proof: HoldingAnalysisInputProof }> {
  return requestJson<{ proof: HoldingAnalysisInputProof }>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis/verify-input`,
    jsonInit("POST"),
  );
}

export function refreshHoldingAnalysis(
  stockId: string,
  options: { prepareHistory?: boolean } = {},
): Promise<HoldingAnalysisRefreshResponse> {
  const query = new URLSearchParams({ prepare_latest: "true" });
  if (options.prepareHistory) query.set("prepare_history", "true");
  return requestJson<HoldingAnalysisRefreshResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis/refresh?${query.toString()}`,
    jsonInit("POST"),
  );
}


export async function prepareHoldingAnalysisWithProgress(
  stockId: string,
  onProgress: (progress: HoldingAnalysisPrepareProgress) => void,
): Promise<HoldingAnalysisRefreshResponse> {
  const response = await fetch(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis/prepare-stream`,
    jsonInit("POST"),
  );
  if (!response.ok) {
    throw new HoldingsApiError(`데이터 준비 요청 실패 (${response.status})`, null, response.status, null);
  }
  if (!response.body) {
    throw new HoldingsApiError("데이터 준비 진행상황을 읽을 수 없습니다.", null, response.status, null);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: HoldingAnalysisRefreshResponse | null = null;

  const consumeLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const event = JSON.parse(trimmed) as HoldingAnalysisStreamEvent;
    if (event.type === "progress") {
      onProgress(event);
      return;
    }
    if (event.type === "error") {
      const detail: ApiErrorDetail = {
        code: event.code,
        message: event.message,
        source_code: event.source_code,
        current_rows: event.current_rows,
        required_rows: event.required_rows,
      };
      throw new HoldingsApiError(
        event.message || "과거 가격 데이터를 준비하지 못했습니다.",
        event.code ?? null,
        400,
        detail,
      );
    }
    if (event.type === "complete" && event.result) {
      completed = event.result;
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) consumeLine(line);
    if (done) break;
  }
  if (buffer.trim()) consumeLine(buffer);
  if (!completed) {
    throw new HoldingsApiError("데이터 준비가 완료되기 전에 연결이 종료되었습니다.", null, 500, null);
  }
  return completed;
}

export function getHoldingTimeline(
  stockId: string,
  limit = 100,
  options: { signal?: AbortSignal } = {},
): Promise<HoldingTimelineItem[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  return requestJson<HoldingTimelineItem[]>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/timeline?${query.toString()}`,
    { signal: options.signal },
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


export async function prepareHoldingChartWithProgress(
  stockId: string,
  range: HoldingChartRange,
  onProgress: (progress: HoldingChartPrepareProgress) => void,
): Promise<HoldingChartPrepareResult> {
  const query = new URLSearchParams({ range });
  const response = await fetch(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/chart/prepare-stream?${query.toString()}`,
    jsonInit("POST"),
  );
  if (!response.ok) {
    throw new HoldingsApiError(`차트 데이터 준비 요청 실패 (${response.status})`, null, response.status, null);
  }
  if (!response.body) {
    throw new HoldingsApiError("차트 데이터 준비 진행상황을 읽을 수 없습니다.", null, response.status, null);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: HoldingChartPrepareResult | null = null;

  const consumeLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const event = JSON.parse(trimmed) as HoldingChartPrepareStreamEvent;
    if (event.type === "progress") {
      onProgress(event);
      return;
    }
    if (event.type === "error") {
      throw new HoldingsApiError(
        event.message || "차트 데이터를 준비하지 못했습니다.",
        event.code ?? null,
        400,
        { code: event.code, message: event.message, current_rows: event.current_rows, required_rows: event.required_rows },
      );
    }
    if (event.type === "complete" && event.result) completed = event.result;
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) consumeLine(line);
    if (done) break;
  }
  if (buffer.trim()) consumeLine(buffer);
  if (!completed) {
    throw new HoldingsApiError("차트 데이터 준비가 완료되기 전에 연결이 종료되었습니다.", null, 500, null);
  }
  return completed;
}

export function syncKisHoldings(): Promise<KisSyncResponse> {
  return requestJson<KisSyncResponse>("/api/holdings/kis/sync", jsonInit("POST"));
}
