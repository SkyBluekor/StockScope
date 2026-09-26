export type HealthResponse = { status: string };

export type ProviderStatus = {
  krx: { configured: boolean; role: string };
  dart: { configured: boolean; role: string };
  naver_news: { configured: boolean; provider_kind: string; role: string };
  kis: { enabled: boolean; role: string };
  real_trading: boolean;
};

export type DataContractResourceStatus = "ABSENT" | "UNVERIFIED" | "VALID" | "INVALID";
export type StockDataContractRange = "1m" | "3m" | "6m" | "1y";

export type DataContractAction = {
  id: "PREPARE_CHART" | "REFRESH_HOLDING_ANALYSIS" | "VIEW_ACTIVE_JOB";
  target: "chart" | "analysis_result" | "active_job";
  enabled: boolean;
  requires_user_initiation: true;
  reason_code: string | null;
};

export type StockDataContract = {
  contract_version: "DATA_CONTRACT_V1";
  resource_key: string;
  checked_at: string;
  request: {
    market: "KOSPI" | "KOSDAQ";
    ticker: string;
    range: StockDataContractRange | null;
    job_id: string | null;
  };
  resources: {
    eod: {
      status: DataContractResourceStatus;
      present: boolean;
      source: string;
      basis: "CONFIRMED_EOD";
      market_confirmed_date: string | null;
      stock_date: string | null;
      first_date: string | null;
      row_count: number;
      reason_code: string | null;
    };
    chart: {
      status: DataContractResourceStatus;
      present: boolean;
      source: string;
      range: StockDataContractRange | null;
      from_date: string | null;
      to_date: string | null;
      row_count: number;
      required_rows: number | null;
      market_confirmed_date: string | null;
      reason_code: string | null;
    };
    analysis_result: {
      status: DataContractResourceStatus;
      present: boolean;
      source: string;
      basis: "CONFIRMED_EOD" | null;
      basis_date: string | null;
      monitored_stock_id: string | null;
      revision_id: string | null;
      revision_no: number | null;
      computed_at: string | null;
      strategy_key: string | null;
      action_state: string | null;
      risk_state: string | null;
      identity: {
        input_fingerprint: string | null;
        scanner_version: string | null;
        analysis_engine_version: string | null;
        policy_version: string | null;
        source_versions: Record<string, unknown> | null;
      };
      displayable: boolean;
      current_use_allowed: boolean;
      reason_code: string | null;
    };
    realtime: {
      status: DataContractResourceStatus;
      present: boolean;
      source: string;
      reason_code: string | null;
    };
    ledger: {
      status: DataContractResourceStatus;
      present: boolean;
      source: string;
      monitored_stock_id: string | null;
      watch_enabled: boolean | null;
      archived_at: string | null;
      open_position_count: number;
      positions: Array<{
        position_id: string;
        account_id: string;
        provider: string;
        account_kind: string;
        broker_environment: string | null;
        current_quantity: string;
        current_average_price: string | null;
        current_cost_basis: string | null;
        opened_reason: string;
        opened_at: string;
        last_observed_at: string | null;
        last_sync_run_id: string | null;
      }>;
      reason_code: string | null;
    };
  };
  preparation: {
    required: boolean;
    targets: Array<"eod" | "chart">;
    supported: boolean;
    reason_codes: string[];
  };
  active_job: {
    state: "KNOWN" | "UNKNOWN";
    job_id: string;
    status: string | null;
    stage: string | null;
    message: string | null;
    current: number | null;
    total: number | null;
    details: Record<string, unknown> | null;
    error: string | null;
    created_at: string | null;
    updated_at: string | null;
    reason_code: string | null;
  } | null;
  actions: DataContractAction[];
};

export type KrxStockRow = {
  date: string | null;
  code: string | null;
  name: string | null;
  market: string | null;
  section: string | null;
  close: number | null;
  change: number | null;
  change_rate: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  trade_value: number | null;
  market_cap: number | null;
  listed_shares: number | null;
};

export type IndexPoint = {
  date: string | null;
  class: string | null;
  name: string | null;
  close: number | null;
  change: number | null;
  change_rate: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  trade_value: number | null;
  market_cap: number | null;
};

export type MarketDashboard = {
  real_trading: false;
  data_date: string;
  requested_date: string | null;
  fallback_used: boolean;
  data_freshness: {
    status: "CONFIRMED" | "FALLBACK";
    message: string;
    requested_date: string;
    data_date: string;
    kospi_data_date: string;
    kosdaq_data_date: string;
    retry_note: string;
  };
  market: {
    regime: string;
    volatility_proxy: string;
    volatility_note: string;
    breadth: {
      total: number;
      up: number;
      down: number;
      flat: number;
      up_ratio: number;
      avg_abs_change_rate: number;
    };
  };
  indices: {
    kospi: IndexPoint;
    kosdaq: IndexPoint;
  };
  history: {
    kospi: IndexPoint[];
    kosdaq: IndexPoint[];
  };
  strong_groups: Array<{
    name: string | null;
    change_rate: number | null;
    class: string | null;
    kind: string;
  }>;
  top_turnover: KrxStockRow[];
  summary: string;
  sources: Record<string, string>;
};

export type MarketHistory = {
  real_trading: false;
  kospi: IndexPoint[];
  kosdaq: IndexPoint[];
};

export type DartCompany = {
  provider: "OpenDART";
  corp_code: string | null;
  corp_name: string | null;
  corp_name_eng: string | null;
  stock_name: string | null;
  stock_code: string | null;
  ceo: string | null;
  corp_class: string | null;
  business_number: string | null;
  established_date: string | null;
  address: string | null;
  homepage: string | null;
  phone: string | null;
  industry_code: string | null;
  fiscal_month: string | null;
};

export type DartDisclosureResponse = {
  provider: "OpenDART";
  corp_code: string;
  begin_date: string;
  end_date: string;
  count: number;
  rows: Array<{
    receipt_no: string | null;
    corp_name: string | null;
    report_name: string | null;
    filer_name: string | null;
    receipt_date: string | null;
    remark: string | null;
  }>;
};

export type StockContext = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  real_trading: false;
  data_date: string;
  requested_date: string | null;
  fallback_used: boolean;
  stock: KrxStockRow;
  market_index: IndexPoint | null;
  company: DartCompany;
  disclosures: DartDisclosureResponse;
  sources: Record<string, string>;
};

export type StockNewsItem = {
  id: string;
  title: string;
  description: string;
  url: string;
  source_url: string;
  source_name: string | null;
  source_domain: string | null;
  provider: string;
  published_at: string | null;
  timestamp_kind: string;
  query: string;
  fetched_at: string;
};

export type StockNewsResponse = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  company_name: string;
  query: string;
  fetched_at: string;
  status: "ok" | string;
  items: StockNewsItem[];
  count: number;
  cache: { hit: boolean; stale: boolean };
  discarded_items: number;
};

export class ApiError extends Error {
  status: number;
  code: string | null;
  retryable: boolean;
  retryAfter: number | null;
  requestId: string | null;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string | null;
      retryable?: boolean;
      retryAfter?: number | null;
      requestId?: string | null;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.retryable = options.retryable ?? false;
    this.retryAfter = options.retryAfter ?? null;
    this.requestId = options.requestId ?? null;
  }
}

async function asJson<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let message = `요청 실패 (${response.status})`;
  let code: string | null = null;
  let retryable = false;
  let retryAfter: number | null = null;
  let requestId: string | null = null;
  try {
    const body = (await response.json()) as {
      detail?: string | { error?: { code?: string; message?: string; retryable?: boolean; retry_after?: number | null; request_id?: string } };
      error?: { code?: string; message?: string; retryable?: boolean; retry_after?: number | null; request_id?: string };
    };
    const structured = typeof body.detail === "object" ? body.detail?.error : body.error;
    if (typeof body.detail === "string") message = body.detail;
    if (structured) {
      message = structured.message ?? message;
      code = structured.code ?? null;
      retryable = Boolean(structured.retryable);
      retryAfter = structured.retry_after ?? null;
      requestId = structured.request_id ?? null;
    }
  } catch {
    // Keep fallback message.
  }
  throw new ApiError(message, { status: response.status, code, retryable, retryAfter, requestId });
}

export async function fetchHealth(): Promise<HealthResponse> {
  return asJson<HealthResponse>(await fetch("/api/health"));
}

export async function fetchProviderStatus(): Promise<ProviderStatus> {
  return asJson<ProviderStatus>(await fetch("/api/providers/status"));
}

export async function fetchMarketDashboard(): Promise<MarketDashboard> {
  return asJson<MarketDashboard>(await fetch("/api/market/dashboard"));
}

export async function fetchMarketHistory(): Promise<MarketHistory> {
  return asJson<MarketHistory>(await fetch("/api/market/history?points=7"));
}

export async function fetchStockContext(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  options: { signal?: AbortSignal } = {},
): Promise<StockContext> {
  const query = new URLSearchParams({ market });
  return asJson<StockContext>(
    await fetch(
      `/api/stocks/${encodeURIComponent(code.trim().toUpperCase())}/context?${query.toString()}`,
      { signal: options.signal },
    ),
  );
}

export async function fetchStockDataContract(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  options: {
    range?: StockDataContractRange;
    jobId?: string;
    signal?: AbortSignal;
  } = {},
): Promise<StockDataContract> {
  const query = new URLSearchParams({ market });
  if (options.range) query.set("range", options.range);
  if (options.jobId?.trim()) query.set("job_id", options.jobId.trim());
  return asJson<StockDataContract>(
    await fetch(
      `/api/data-contract/stocks/${encodeURIComponent(code.trim().toUpperCase())}?${query.toString()}`,
      { signal: options.signal },
    ),
  );
}

export async function fetchStockNews(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  options: { limit?: number; signal?: AbortSignal } = {},
): Promise<StockNewsResponse> {
  const query = new URLSearchParams({
    market,
    limit: String(options.limit ?? 10),
  });
  return asJson<StockNewsResponse>(
    await fetch(
      `/api/stocks/${encodeURIComponent(code.trim().toUpperCase())}/news?${query.toString()}`,
      { signal: options.signal },
    ),
  );
}


export type StrategyEvaluation = {
  strategy: string;
  score: number | null;
  suitability: string;
  eligible: boolean;
  passed: number;
  total: number;
  reasons: string[];
  unmet: string[];
  blockers: string[];
  note: string;
  action_plan: {
    new_entry: string[];
    holding: string[];
    avoid: string[];
    watch: string[];
    invalidation: string;
  };
  auto_checks: Array<{
    key: string;
    label: string;
    status: "PASS" | "WARN" | "FAIL" | "UNKNOWN";
    value: string;
    explanation: string;
    source: string;
  }>;
};

export type StockChartRange = "1m" | "3m" | "6m" | "1y";

export type StockChartBar = {
  date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
};

export type StockChartResponse = {
  market: string;
  ticker: string;
  range: StockChartRange;
  source: string;
  from_date: string;
  to_date: string;
  requested_bars: number;
  count: number;
  bars: StockChartBar[];
};

export type StockChartPrepareProgress = {
  type: "progress" | "complete" | "error" | string;
  stage: string;
  message: string;
  current: number;
  required: number;
  status?: string;
};

export type StockChartPrepareResult = {
  status: string;
  market: string;
  ticker: string;
  range: StockChartRange;
  latest_confirmed_date: string;
  existing_rows: number;
  prepared_rows: number;
  final_rows: number;
  required_rows: number;
  network_requests: number;
  message: string;
};

export type RiskPlan = {
  strategy: string;
  status: "READY" | "CAUTION" | "HOLD" | "UNAVAILABLE";
  reference_only: boolean;
  basis: "CONFIRMED_EOD" | "MANUAL_REFERENCE" | string;
  entry_price: number;
  structural_anchor: number | null;
  structural_anchor_label: string | null;
  invalidation_price: number | null;
  stop_zone_low: number | null;
  stop_zone_high: number | null;
  target1_price: number | null;
  target1_basis: string | null;
  structural_target1_price?: number | null;
  structural_target1_basis?: string | null;
  target1_cap_price?: number | null;
  target1_cap_applied?: boolean;
  target1_fallback_used?: boolean;
  target2_price: number | null;
  target2_basis: string | null;
  risk_pct: number | null;
  reward1_pct: number | null;
  reward2_pct: number | null;
  rr1: number | null;
  rr2: number | null;
  structure_rating: string;
  summary: string;
  reasons: string[];
  warnings: string[];
  assumptions: string[];
};

export type RiskAnalysis = {
  status: "READY" | "CAUTION" | "HOLD" | "UNAVAILABLE";
  basis: "CONFIRMED_EOD" | "MANUAL_REFERENCE" | string;
  reference_only: boolean;
  selected_strategy: string | null;
  selected_plan: RiskPlan | null;
  plans: RiskPlan[];
  summary: string;
  policy: {
    real_trading: false;
    order_execution: false;
    message: string;
  };
};

export type StrategyAnalysis = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  real_trading: false;
  data_date: string | null;
  data_freshness: {
    price_source: "KRX_EOD" | "USER_INPUT";
    analysis_basis: "CONFIRMED_EOD" | "MANUAL_REFERENCE";
    eod_date: string | null;
    eod_close: number | null;
    reference: null | {
      source: "USER_INPUT";
      status: "REFERENCE_UPDATED" | "STALE" | "EXTREME_MOVE";
      message: string;
      confirmed_date: string | null;
      confirmed_close: number;
      reference_price: number;
      reference_high: number | null;
      reference_low: number | null;
      reference_volume: number | null;
      input_mode: "PRICE_ONLY" | "PRICE_OHLC" | "PRICE_OHLCV";
      supplied: { price: boolean; high: boolean; low: boolean; volume: boolean };
      gap_pct: number;
      stale_threshold_pct: number;
      extreme_threshold_pct: number;
      is_stale: boolean;
      is_extreme_move: boolean;
      estimated: {
        ma20: number | null;
        rsi14: number | null;
        atr14: number | null;
        atr_pct: number | null;
        volume_ratio_20: number | null;
        distance_to_20d_high_pct: number | null;
        support_distance_pct: number | null;
        resistance_distance_pct: number | null;
      };
      confirmed_only: {
        atr_pct: number | null;
        volume_ratio_20: number | null;
        support: number | null;
        resistance: number | null;
      };
    };
  };
  analysis_layers: {
    confirmed_eod: {
      label: string; immutable: true; price: number | null; ma20: number | null; rsi14: number | null;
      atr_pct: number | null; volume_ratio_20: number | null; risk_gate: { active: boolean; decision: string; reasons: string[]; message: string };
    };
    current_reference: null | {
      label: string; temporary: true; input_mode: string; price: number; estimated_ma20: number | null; estimated_rsi14: number | null;
      estimated_atr_pct: number | null; effective_atr_pct: number | null; estimated_volume_ratio_20: number | null; effective_volume_ratio_20: number | null;
      risk_gate: { active: boolean; decision: string; reasons: string[]; message: string };
    };
  };
  history_points: number;
  first_load_note: string;
  technical: {
    data_points: number;
    date_from: string | null;
    date_to: string | null;
    current_price: number;
    ma5: number | null;
    ma20: number | null;
    ma60: number | null;
    ma120: number | null;
    ma20_slope_pct: number | null;
    rsi14: number | null;
    atr14: number | null;
    atr_pct: number | null;
    volume_ratio_20: number | null;
    high20: number | null;
    low20: number | null;
    distance_to_20d_high_pct: number | null;
    support: number | null;
    resistance: number | null;
    support_distance_pct: number | null;
    resistance_distance_pct: number | null;
    higher_high: boolean | null;
    higher_low: boolean | null;
  };
  effective: {
    price: number;
    ma20: number | null;
    rsi14: number | null;
    support_distance_pct: number | null;
    resistance_distance_pct: number | null;
    distance_to_20d_high_pct: number | null;
    atr_pct: number | null;
    volume_ratio_20: number | null;
  };
  market_context: {
    regime: string;
    index_name: string | null;
    index_change_rate: number | null;
  };
  relative_strength: {
    available: boolean;
    source: "KRX_EOD";
    price_basis: "CONFIRMED_EOD";
    benchmark: { market: "KOSPI" | "KOSDAQ" | string; name: string };
    as_of: string | null;
    aligned_points: number;
    primary_period: number | null;
    primary_excess_pct: number | null;
    status: "STRONG" | "OUTPERFORM" | "NEUTRAL" | "UNDERPERFORM" | "WEAK" | "UNKNOWN";
    label: string;
    trend: "IMPROVING" | "STABLE" | "DETERIORATING" | "UNKNOWN";
    trend_label: string;
    trend_message: string;
    summary: string;
    periods: Array<{
      days: 5 | 20 | 60 | number;
      available: boolean;
      stock_return_pct: number | null;
      market_return_pct: number | null;
      excess_return_pct: number | null;
      status: string;
      label: string;
    }>;
    strategy_effects: Array<{
      strategy: string;
      label: string;
      weight: number;
      condition_met: boolean | null;
      direction: "UP" | "DOWN" | "NEUTRAL";
      message: string;
    }>;
    decision: {
      archetype: "MARKET_LEADER" | "SHORT_TERM_RECOVERY" | "STRONG_BUT_FADING" | "OUTPERFORMING" | "MARKET_LIKE" | "RECOVERY_ATTEMPT" | "MARKET_LAGGARD" | "UNKNOWN";
      label: string;
      headline: string;
      summary: string;
      confidence: "HIGH" | "MEDIUM" | "LOW";
      confidence_label: string;
      new_entry: { action: string; summary: string };
      holding: { action: string; summary: string };
      user_response: { perspective: string; action: string; summary: string };
      preferred_strategies: string[];
      deprioritized_strategies: string[];
      why: string[];
      watch_points: string[];
      short_term_heat: "HIGH" | "NORMAL" | "UNKNOWN";
      short_term_heat_label: string;
    };
    note: string;
  };
  sector_relative_strength: {
    available: boolean;
    source: "OpenDART+KRX_EOD" | string;
    price_basis: "CONFIRMED_EOD";
    industry_code: string | null;
    mapping: {
      available?: boolean;
      industry_code?: string | null;
      industry_prefix?: string;
      sector_group?: string | null;
      aliases?: string[];
      mapping_method?: string;
      mapping_confidence?: "HIGH" | "MEDIUM" | "LOW";
      mapping_confidence_label?: string;
      benchmark_name?: string;
      benchmark_class?: string;
      matched_alias?: string;
      index_match_confidence?: "HIGH" | "MEDIUM" | "LOW";
      index_match_confidence_label?: string;
      reason?: string;
    };
    benchmark: null | { market: string; name: string };
    as_of: string | null;
    aligned_points: number;
    primary_period: number | null;
    primary_excess_pct: number | null;
    status: "STRONG" | "OUTPERFORM" | "NEUTRAL" | "UNDERPERFORM" | "WEAK" | "UNKNOWN";
    label: string;
    trend: "IMPROVING" | "STABLE" | "DETERIORATING" | "UNKNOWN";
    trend_label: string;
    trend_message: string;
    periods: Array<{
      days: 5 | 20 | 60 | number;
      available: boolean;
      stock_return_pct: number | null;
      sector_return_pct: number | null;
      excess_return_pct: number | null;
      status: string;
      label: string;
    }>;
    strategy_effects: Array<{
      strategy: string;
      label: string;
      weight: number;
      condition_met: boolean | null;
      direction: "UP" | "DOWN" | "NEUTRAL";
      message: string;
    }>;
    decision: {
      archetype: "DUAL_LEADER" | "INDEPENDENT_LEADER" | "SECTOR_LAGGARD" | "SECTOR_DRIVEN" | "WEAK_SECTOR_WINNER" | "DOUBLE_LAGGARD" | "MIXED" | "UNKNOWN";
      label: string;
      headline: string;
      summary: string;
      user_response: { perspective: string; action: string; summary: string };
      preferred_strategies: string[];
      deprioritized_strategies: string[];
      why: string[];
      watch_points: string[];
      market_excess_pct: number | null;
      sector_excess_pct: number | null;
      sector_vs_market_pct: number | null;
    };
    message: string;
    note: string;
  };
  fundamental: {
    available: boolean;
    engine: "FUNDAMENTAL";
    version: "0.17" | string;
    source: string;
    corp_code?: string;
    company?: { name: string | null; industry_code: string | null; fiscal_month: string | null };
    latest_year: number | null;
    annual_latest_year?: number | null;
    statement_basis?: "CFS" | "OFS" | string;
    statement_basis_label?: string;
    latest_report?: null | {
      business_year: number;
      report_code: string;
      report_label: string;
      period_label: string;
      period_end: string | null;
      fs_div: string;
      fs_label: string;
      is_interim: boolean;
      compare_available: boolean;
      compare_label: string | null;
    };
    recent_performance?: null | {
      year: number;
      report_code: string;
      report_label: string;
      period_label: string;
      compare_label: string | null;
      is_interim: boolean;
      fs_div: string;
      fs_label: string;
      period_end: string | null;
      revenue: number | null;
      operating_profit: number | null;
      net_income: number | null;
      operating_margin_pct: number | null;
      net_margin_pct: number | null;
      debt_ratio_pct: number | null;
      current_ratio_pct: number | null;
      operating_cash_flow: number | null;
      free_cash_flow: number | null;
      revenue_yoy_pct: number | null;
      operating_profit_yoy_pct: number | null;
      net_income_yoy_pct: number | null;
      operating_cash_flow_yoy_pct: number | null;
    };
    prior_same_period?: null | {
      year: number;
      report_code: string;
      report_label: string;
      period_label: string | null;
      revenue: number | null;
      operating_profit: number | null;
      net_income: number | null;
      operating_cash_flow: number | null;
    };
    freshness?: { status: string; label: string; message: string };
    overall: { status: "GOOD" | "CAUTION" | "WEAK" | "UNKNOWN"; label: string; headline: string; summary: string };
    archetype: { code: string; label: string; summary: string };
    axes: Record<string, {
      code: string; label: string; status: "STRONG" | "GOOD" | "NEUTRAL" | "CAUTION" | "WEAK" | "UNKNOWN";
      status_label: string; headline: string; summary: string; evidence: string[];
    }>;
    valuation: {
      available: boolean; status: "LOW_MULTIPLE" | "MID_MULTIPLE" | "HIGH_MULTIPLE" | "LOSS" | "UNKNOWN" | string;
      label: string; message: string; eps?: number | null; bps?: number | null; basis?: string; policy?: string;
      eod: { price?: number | null; per?: number | null; pbr?: number | null; status?: string; label?: string };
      preview: null | { price?: number | null; per?: number | null; pbr?: number | null; status?: string; label?: string };
    };
    latest_metrics?: {
      revenue: number | null; operating_profit: number | null; net_income: number | null; operating_margin_pct: number | null;
      net_margin_pct: number | null; roe_pct: number | null; roa_pct: number | null; debt_ratio_pct: number | null;
      current_ratio_pct: number | null; operating_cash_flow: number | null; free_cash_flow: number | null; eps: number | null;
      bps: number | null; market_cap_eod: number | null; market_cap_preview: number | null;
    };
    years: Array<{
      year: number; fs_div: string; fs_label: string; revenue: number | null; operating_profit: number | null; net_income: number | null;
      assets: number | null; liabilities: number | null; equity: number | null; current_assets: number | null; current_liabilities: number | null;
      operating_cash_flow: number | null; investing_cash_flow: number | null; financing_cash_flow: number | null; capex: number | null;
      free_cash_flow: number | null; eps_reported: number | null; operating_margin_pct: number | null; net_margin_pct: number | null;
      roe_pct: number | null; roa_pct: number | null; debt_ratio_pct: number | null; current_ratio_pct: number | null;
      revenue_growth_pct: number | null; operating_profit_growth_pct: number | null; net_income_growth_pct: number | null;
    }>;
    strengths: string[];
    warnings: string[];
    watch_points: string[];
    data_basis: { financial: string; price: string; as_of?: string | null; note: string };
    policy: string;
  };
  investor_style: {
    available: boolean;
    engine: "INVESTOR_STYLE";
    version: string;
    top_style: null | {
      code: "BUFFETT" | "GRAHAM" | "LYNCH" | "CAN_SLIM";
      label: string;
      score: number | null;
      fit: string;
      fit_label: string;
      coverage_percent: number;
      summary: string;
      current_action?: string;
      action_summary?: string;
    };
    styles: Array<{
      code: "BUFFETT" | "GRAHAM" | "LYNCH" | "CAN_SLIM";
      label: string;
      short_label: string;
      score: number | null;
      fit: "VERY_HIGH" | "HIGH" | "MEDIUM" | "LOW" | "VERY_LOW" | "UNKNOWN" | string;
      fit_label: string;
      coverage: { known_weight: number; total_weight: number; percent: number; known_conditions: number; total_conditions: number };
      overview: {
        core: string;
        horizon: string;
        philosophy: string;
        suited_for: string[];
        less_suited_for: string[];
        process: string[];
      };
      company_type: string | null;
      company_fit: { headline: string; strengths: string[]; weaknesses: string[]; unknowns: string[] };
      action_plan: {
        decision_code: string;
        current_action: string;
        style_action: string;
        headline: string;
        summary: string;
        company_judgment: { label: string; value: string; status: string; summary: string };
        entry_judgment: {
          label: string;
          value: string;
          status: string;
          summary: string;
          progress_label?: string;
          missing?: string[];
          timing_importance?: string;
          timing_note?: string;
        };
        judgments: Array<{ key: string; label: string; status: "GOOD" | "CAUTION" | "WEAK" | "UNKNOWN" | string; status_label: string; summary: string }>;
        reasons: string[];
        blockers: string[];
        do_now: string[];
        avoid_now: string[];
        auto_monitor: Array<{ label: string; current: string; effect: string }>;
        decision_scenarios: Array<{ condition: string; effect: string; tone: "POSITIVE" | "NEGATIVE" | "CAUTION" | string }>;
        watch: string[];
        recheck_conditions: string[];
        score_note: string;
        automation_note: string;
      };
      conditions: Array<{
        key: string; label: string; weight: number; status: "PASS" | "WARN" | "FAIL" | "UNKNOWN";
        status_label: string; value: string; explanation: string;
      }>;
    }>;
    comparison: Array<{
      code: "BUFFETT" | "GRAHAM" | "LYNCH" | "CAN_SLIM";
      label: string; score: number | null; fit_label: string; core: string; horizon: string;
    }>;
    message: string;
    data_basis?: { fundamental?: string | null; relative_strength?: string; event?: string; market?: string };
    policy: string;
  };
  risk_gate: {
    active: boolean;
    decision: "HOLD" | "EVALUATE";
    reasons: string[];
    message: string;
  };
  risk_analysis: RiskAnalysis;
  event_risk: {
    available: boolean;
    engine?: "EVENT_IMPACT";
    version?: string;
    corp_code?: string;
    period?: { begin: string; end: string; days: number };
    total_disclosures?: number;
    classified_count?: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    positive_count: number;
    negative_count: number;
    mixed_count: number;
    risk_gate: boolean;
    message: string;
    policy?: string;
    events: Array<{
      event_type: string;
      level: "HIGH" | "MEDIUM" | "LOW";
      impact_level: "HIGH" | "MEDIUM" | "LOW";
      direction: "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
      confidence: "HIGH" | "MEDIUM" | "LOW";
      confidence_label: string;
      receipt_no: string | null;
      receipt_date: string | null;
      report_name: string | null;
      easy_summary: string;
      facts: Array<{ label: string; value: string; raw?: number | string | null }>;
      document_highlights: string[];
      metrics: Record<string, number | string | null>;
      price_reaction: {
        available: boolean;
        event_date?: string;
        pre_event_close?: number | null;
        analysis_price?: number | null;
        analysis_price_source?: "USER_REFERENCE" | "KRX_EOD" | null;
        price_change_pct?: number | null;
        volume_ratio_20?: number | null;
        reaction?: "UNKNOWN" | "MUTED" | "MODERATE" | "STRONG" | "EXTREME";
        label: string;
      };
      current_conclusion: { headline: string; summary: string };
      strategy_effects: Array<{
        strategy: string;
        direction: "UP" | "DOWN" | "NEUTRAL";
        label: string;
        reason: string;
      }>;
      user_response: { action: string; summary: string };
      watch_points: string[];
      detail_source: "STRUCTURED_API" | "DOCUMENT_XML" | "TITLE_RULE";
      viewer_url: string | null;
    }>;
  };
  strategies: StrategyEvaluation[];
  top_strategy: StrategyEvaluation | null;
  best_regular_strategy: StrategyEvaluation | null;
  eod_risk_gate: { active: boolean; decision: "HOLD" | "EVALUATE"; reasons: string[]; message: string };
  eod_strategies: StrategyEvaluation[];
  reference_strategies: StrategyEvaluation[] | null;
  strategy_comparison: Array<{
    strategy: string; eod_score: number | null; reference_score: number | null; score_delta: number | null;
    reference_eligible: boolean; current_data_status: "PARTIAL" | "PRICE_UPDATED" | "CONFIRMATION_UPDATED";
    current_data_message: string; missing_current_inputs: string[];
  }>;
  position_context: {
    mode: "NOT_HELD" | "HOLDING";
    label: string;
    analysis_price: number;
    average_price: number | null;
    quantity: number | null;
    return_pct: number | null;
    unrealized_pnl: number | null;
    state: "NEW_ENTRY_VIEW" | "STRUCTURE_OK" | "WEAKENING" | "RISK_REVIEW" | "STRATEGY_INVALIDATED";
    summary: string;
    checks: Array<{ key: string; label: string; status: "PASS" | "WARN" | "FAIL" | "UNKNOWN"; value: string; explanation: string }>;
    policy?: string;
  };
  position_action_guide: {
    available: boolean;
    primary_code: "NOT_APPLICABLE" | "HOLD_OBSERVE" | "REDUCE_RISK_REVIEW" | "EXIT_REVIEW" | "EVENT_REVIEW";
    primary_label: string;
    headline: string;
    summary: string;
    best_strategy?: string | null;
    best_strategy_score?: number | null;
    hold?: { decision: string; label: string; reason: string };
    add_position?: { decision: string; label: string; reason: string };
    reduce_position?: { decision: string; label: string; reason: string };
    why?: string[];
    triggers?: Array<{ condition: string; effect: string }>;
    levels?: { ma20: number | null; support: number | null; invalidation: number | null; target1: number | null; target2: number | null };
    policy?: string;
  };
  pullback_confirmation: {
    available: boolean;
    version?: string;
    state: "NOT_PULLBACK" | "PULLBACK_IN_PROGRESS" | "SUPPORT_APPROACH" | "SUPPORT_TESTING" | "REBOUND_WAITING" | "REBOUND_CONFIRMED" | "SUPPORT_FAILED";
    label: string;
    headline: string;
    summary: string;
    basis: "CONFIRMED_EOD" | "INTRADAY_PREVIEW";
    basis_label: string;
    confirmed: boolean;
    anchor: { name: string | null; price: number | null; distance_pct: number | null };
    checks: Array<{
      key: string;
      label: string;
      status: "PASS" | "WARN" | "FAIL" | "UNKNOWN";
      value: string;
      explanation: string;
      source: string;
    }>;
    passed: number;
    failed: number;
    known_checks: number;
    total_checks: number;
    user_response: { perspective: string; action: string; summary: string };
    new_entry: { action: string; summary: string };
    holding: { action: string; summary: string };
    waiting_for: string[];
    auto_check: {
      passed: number;
      failed: number;
      pending: number;
      known: number;
      total: number;
      progress_pct: number;
      progress_label: string;
      progress_message: string;
      passed_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      failed_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      pending_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      basis: "CONFIRMED_EOD" | "INTRADAY_PREVIEW";
      basis_label: string;
      is_confirmed_basis: boolean;
      input_hints: Array<{ field: string; label: string; reason: string }>;
      next_data_note: string;
      policy: string;
    };
    entry_timing: {
      version: string;
      status: "READY" | "WAIT" | "INVALIDATED" | "NOT_APPLICABLE" | string;
      state: string;
      label: string;
      headline: string;
      summary: string;
      basis: "CONFIRMED_EOD" | "INTRADAY_PREVIEW";
      basis_label: string;
      progress: { passed: number; failed: number; pending: number; total: number; percent: number; label: string };
      confirmed_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      failed_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      pending_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      most_missing: string[];
      action: { perspective: string; primary: string; next: string; avoid: string; recheck_note: string };
      levels: { current_price: number | null; ma20: number | null; support: number | null; anchor: number | null; rebound_confirmation: number | null };
      rules: { price_rebound?: string; rsi_recovery?: string; volume_recovery?: string };
      policy: string;
    };
    policy: string;
  };
  analysis_summary: {
    version: string;
    verdict_code: "RISK_FIRST" | "POSITIVE" | "POSITIVE_CAUTION" | "MIXED_POSITIVE" | "CAUTION" | "MIXED";
    verdict_label: string;
    headline: string;
    summary: string;
    primary_action: string;
    perspective: string;
    risk_level: string;
    auto_check_status: {
      state: string;
      label: string;
      headline: string;
      basis: "CONFIRMED_EOD" | "INTRADAY_PREVIEW" | string;
      basis_label: string;
      confirmed: boolean;
      progress: { passed: number; failed: number; pending: number; total: number; percent: number; label: string };
      pending: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      failed: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      input_hints: Array<{ field: string; label: string; reason: string }>;
      next_data_note: string;
      policy: string;
    };
    entry_timing: {
      version: string;
      relevant: boolean;
      status: string;
      state: string;
      label: string;
      headline: string;
      summary: string;
      basis: string;
      basis_label: string;
      progress: { passed: number; failed: number; pending: number; total: number; percent: number; label: string };
      confirmed_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      failed_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      pending_checks: Array<{ key: string; label: string; status: string; status_label: string; value: string; explanation: string; source: string }>;
      most_missing: string[];
      action: { perspective: string; primary: string; next: string; avoid: string; recheck_note: string };
      levels: { current_price?: number | null; ma20?: number | null; support?: number | null; anchor?: number | null; rebound_confirmation?: number | null; invalidation?: number | null };
      rules: { price_rebound?: string; rsi_recovery?: string; volume_recovery?: string };
      style_context: { label: string; score: number | null; fit_label: string; summary: string };
      policy: string;
    };
    signals: Array<{
      key: string;
      label: string;
      status: "POSITIVE" | "NEGATIVE" | "CAUTION" | "NEUTRAL";
      value: string;
      detail: string;
      action_hint: string;
    }>;
    priority_signals: Array<{
      key: string;
      label: string;
      status: "POSITIVE" | "NEGATIVE" | "CAUTION" | "NEUTRAL";
      value: string;
      detail: string;
      action_hint: string;
    }>;
    other_signals: Array<{
      key: string;
      label: string;
      status: "POSITIVE" | "NEGATIVE" | "CAUTION" | "NEUTRAL";
      value: string;
      detail: string;
      action_hint: string;
    }>;
    action_plan: {
      status: "HOLDING" | "RISK_REVIEW" | "READY" | "WAIT" | "REVIEW" | string;
      label: string;
      headline: string;
      summary: string;
      do_now: string[];
      avoid_now: string[];
      decision_scenarios: Array<{ condition: string; effect: string; tone: "POSITIVE" | "NEGATIVE" | "CAUTION" | string }>;
      price_levels: Array<{ key: string; label: string; price: number; meaning: string }>;
      conflict: { show: boolean; headline: string; summary: string; blockers: string[] };
    };
    top_strategy: { strategy: string | null; score: number | null; suitability: string | null };
    key_reasons: string[];
    change_conditions: string[];
    navigation: Array<{ key: string; label: string; description: string }>;
    policy: string;
  };
  limitations: string[];
};

export async function fetchStockChart(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  range: StockChartRange,
): Promise<StockChartResponse> {
  const query = new URLSearchParams({ market, range });
  const response = await fetch(`/api/stocks/${encodeURIComponent(code)}/chart?${query.toString()}`);
  if (!response.ok) {
    let message = `차트 요청 실패 (${response.status})`;
    try {
      const body = await response.json() as { detail?: string | { message?: string } };
      message = typeof body.detail === "string" ? body.detail : body.detail?.message ?? message;
    } catch {
      // keep fallback message
    }
    throw new Error(message);
  }
  return response.json() as Promise<StockChartResponse>;
}

export async function prepareStockChartWithProgress(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  range: StockChartRange,
  onProgress: (progress: StockChartPrepareProgress) => void,
): Promise<StockChartPrepareResult> {
  const query = new URLSearchParams({ market, range });
  const response = await fetch(
    `/api/stocks/${encodeURIComponent(code)}/chart/prepare-stream?${query.toString()}`,
    { method: "POST", headers: { Accept: "application/x-ndjson" } },
  );
  if (!response.ok || !response.body) throw new Error(`차트 데이터 준비 요청 실패 (${response.status})`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: StockChartPrepareResult | null = null;

  const consume = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const event = JSON.parse(trimmed) as StockChartPrepareProgress & {
      code?: string;
      result?: StockChartPrepareResult;
    };
    if (event.type === "progress") {
      onProgress(event);
      return;
    }
    if (event.type === "error") throw new Error(event.message || "차트 데이터를 준비하지 못했습니다.");
    if (event.type === "complete" && event.result) completed = event.result;
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) consume(line);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
  if (!completed) throw new Error("차트 데이터 준비가 완료되기 전에 연결이 종료되었습니다.");
  return completed;
}

export async function fetchStrategyAnalysis(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  referencePrice?: number,
  referenceHigh?: number,
  referenceLow?: number,
  referenceVolume?: number,
  positionMode: "NOT_HELD" | "HOLDING" = "NOT_HELD",
  averagePrice?: number,
  quantity?: number,
  options: { signal?: AbortSignal } = {},
): Promise<StrategyAnalysis> {
  const query = new URLSearchParams({ market, history_points: "60" });
  if (referencePrice != null && Number.isFinite(referencePrice) && referencePrice > 0) query.set("reference_price", String(referencePrice));
  if (referenceHigh != null && Number.isFinite(referenceHigh) && referenceHigh > 0) query.set("reference_high", String(referenceHigh));
  if (referenceLow != null && Number.isFinite(referenceLow) && referenceLow > 0) query.set("reference_low", String(referenceLow));
  if (referenceVolume != null && Number.isFinite(referenceVolume) && referenceVolume >= 0) query.set("reference_volume", String(referenceVolume));
  query.set("position_mode", positionMode);
  if (averagePrice != null && Number.isFinite(averagePrice) && averagePrice > 0) query.set("average_price", String(averagePrice));
  if (quantity != null && Number.isFinite(quantity) && quantity > 0) query.set("quantity", String(quantity));
  return asJson<StrategyAnalysis>(
    await fetch(
      `/api/stocks/${encodeURIComponent(code.trim().toUpperCase())}/strategy-analysis?${query.toString()}`,
      { signal: options.signal },
    ),
  );
}


export type StockSearchItem = {
  code: string;
  standard_code: string;
  name: string;
  full_name: string;
  english_name: string;
  market: "KOSPI" | "KOSDAQ";
  market_name: string;
  security_group: string;
  section: string;
  stock_type: string;
  listed_date: string;
  listed_shares: number | null;
  analysis_as_of_date?: string | null;
};

export type StockSearchResponse = {
  provider: "KRX";
  query: string;
  count: number;
  rows: StockSearchItem[];
  data_dates: Record<string, string>;
  warnings: string[];
};

export async function searchStocks(
  query: string,
  options: { signal?: AbortSignal } = {},
): Promise<StockSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: "12" });
  return asJson<StockSearchResponse>(
    await fetch(`/api/stocks/search?${params.toString()}`, { signal: options.signal }),
  );
}

export type BacktestMetrics = {
  trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number | null;
  average_gross_return_pct: number | null;
  average_net_return_pct: number | null;
  median_net_return_pct: number | null;
  average_win_pct: number | null;
  average_loss_pct: number | null;
  expectancy_pct: number | null;
  profit_factor: number | null;
  average_holding_days: number | null;
  max_consecutive_losses: number;
  max_drawdown_pct: number;
  initial_capital: number;
  final_capital: number;
  total_net_return_pct: number | null;
};

export type BacktestGroupMetrics = BacktestMetrics & { key: string };

export type BacktestAuditCheck = {
  id: string;
  status: "PASS" | "WARN" | "FAIL" | "INFO" | string;
  title: string;
  detail: string;
};

export type BacktestTradeAudit = {
  signal_boundary?: {
    stock_history_start_date?: string | null;
    stock_history_end_date?: string | null;
    index_history_end_date?: string | null;
    market_regime_source_date?: string | null;
    future_data_used?: boolean;
  };
  entry?: {
    signal_close?: number | null;
    entry_date?: string | null;
    entry_open?: number | null;
    gap_from_signal_close_pct?: number | null;
    next_trading_day_open_verified?: boolean;
  };
  risk?: {
    source?: string;
    signal_support?: number | null;
    signal_ma20?: number | null;
    technical_low20?: number | null;
    structural_anchor?: number | null;
    structural_anchor_label?: string | null;
    atr_pct?: number | null;
    atr_value_at_entry?: number | null;
    buffer_factor?: number | null;
    formula?: string;
    invalidation_price?: number | null;
    initial_stop_distance_pct?: number | null;
    anchor_distance_from_entry_pct?: number | null;
    atr_buffer_from_anchor_pct?: number | null;
    risk_plan_status?: string;
    reference_only?: boolean;
    structure_rating?: string;
    summary?: string;
    warnings?: string[];
    reasons?: string[];
  };
  execution?: {
    exit_date?: string | null;
    exit_open?: number | null;
    exit_high?: number | null;
    exit_low?: number | null;
    exit_close?: number | null;
    exit_trigger?: string;
    gross_formula?: string;
    gross_return_pct?: number | null;
    round_trip_cost_pct?: number | null;
    net_return_pct?: number | null;
  };
  flags?: string[];
};

export type BacktestAccuracyAudit = {
  version: string;
  status: string;
  label: string;
  headline: string;
  summary: string;
  checks: BacktestAuditCheck[];
  flagged_trades: Array<{
    signal_date?: string;
    entry_date?: string;
    entry_price?: number | null;
    signal_close?: number | null;
    entry_gap_pct?: number | null;
    stop_price?: number | null;
    stop_distance_pct?: number | null;
    risk_plan_status?: string;
    structure_rating?: string | null;
    structural_anchor?: number | null;
    structural_anchor_label?: string | null;
    anchor_distance_from_entry_pct?: number | null;
    atr_pct?: number | null;
    atr_value_at_entry?: number | null;
    buffer_factor?: number | null;
    flags?: string[];
    cause: string;
  }>;
  policy_observation: string;
  research_observation: string;
  guardrail: string;
  counts: Record<string, number>;
};

export type BacktestRiskPolicyScenario = {
  id: string;
  label: string;
  short: string;
  description: string;
  problem_target: string;
  metrics: BacktestMetrics & {
    closed_trade_max_drawdown_pct?: number;
    max_drawdown_basis?: string;
  };
  eligible_attempts: number;
  blocked_by_policy: number;
  blocked_reasons: Record<string, number>;
  unusable_risk_plan: number;
  caution_trades: number;
  wide_stop_trades: number;
  average_initial_stop_distance_pct: number | null;
  anchor_changed_signals: number;
  anchor_changed_trades: number;
  delta: {
    trades: number;
    expectancy_pctp: number | null;
    total_net_return_pctp: number | null;
    max_drawdown_pctp: number | null;
  };
  interpretation: {
    status: string;
    headline: string;
    meaning: string;
  };
};

export type BacktestRiskPolicyComparison = {
  version: string;
  status: string;
  headline: string;
  summary: string;
  decision: string;
  baseline_problem: {
    caution_trades: number;
    wide_stop_trades: number;
    wide_stop_threshold_pct: number;
  };
  scenarios: BacktestRiskPolicyScenario[];
  next_validation_candidate: null | {
    policy_id: string;
    label: string;
    reason: string;
    next_step: string;
  };
  guardrail: string;
};


export type RiskPolicyCrossStockEvidence = {
  code: string;
  name: string;
  size_band?: string;
  baseline_trades: number;
  candidate_trades: number;
  changed_trades: number;
  triggered: boolean;
  problem_solved: boolean;
  balanced_improvement: boolean;
  harmed: boolean;
  overfiltered: boolean;
  trade_retention_pct: number | null;
  expectancy_delta_pctp: number | null;
  max_drawdown_delta_pctp: number | null;
  baseline_expectancy_pct: number | null;
  candidate_expectancy_pct: number | null;
  baseline_max_drawdown_pct: number | null;
  candidate_max_drawdown_pct: number | null;
  status: string;
};

export type RiskPolicyCrossStockPolicy = {
  policy_id: string;
  label: string;
  problem_target: string;
  tested_stocks: number;
  triggered_stocks: number;
  problem_solved_stocks: number;
  balanced_improvement_stocks: number;
  harmed_stocks: number;
  overfiltered_stocks: number;
  average_trade_retention_pct: number | null;
  average_expectancy_delta_pctp: number | null;
  average_max_drawdown_delta_pctp: number | null;
  verdict: { status: string; label: string; reason: string };
  stock_evidence: RiskPolicyCrossStockEvidence[];
};

export type RiskPolicyCrossValidationStock = {
  code: string;
  name: string;
  market_cap: number | null;
  size_band: string;
  role: "TARGET" | "PEER" | string;
  universe_rank?: number;
  summary: BacktestMetrics;
  risk_policy_comparison: BacktestRiskPolicyComparison;
  accuracy_audit?: BacktestAccuracyAudit;
};

export type RiskPolicyCrossValidationResponse = {
  version: string;
  status: string;
  market: "KOSPI" | "KOSDAQ" | string;
  period: { start: string; end: string };
  target_code: string;
  selection: {
    method: string;
    label: string;
    snapshot_date: string;
    market: string;
    requested_stock_count: number;
    selected_stock_count: number;
    description: string;
  };
  tested_stock_count: number;
  valid_trade_stock_count: number;
  stocks: RiskPolicyCrossValidationStock[];
  policies: RiskPolicyCrossStockPolicy[];
  decision: {
    status: string;
    label: string;
    headline: string;
    reason: string;
    recommended_policy_id: string | null;
    recommended_policy_label: string | null;
    next_step: string;
  };
  guardrail: string;
  limitation: string;
  errors?: Array<{ code: string; name: string; error: string }>;
};

export type BacktestTrade = {
  signal_date: string;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  exit_reason: string;
  holding_days: number;
  strategy_score: number;
  entry_timing_passed: number;
  entry_timing_total: number;
  entry_timing_state: string;
  market_regime: string;
  stop_price: number;
  target1_price: number;
  target2_price: number | null;
  gross_return_pct: number;
  net_return_pct: number;
  risk_plan_status: string;
  research_only: boolean;
  metadata: Record<string, unknown> & { audit?: BacktestTradeAudit };
};


export type BacktestProblemItem = {
  id: string;
  priority: number;
  severity: "HIGH" | "MEDIUM" | "INFO" | string;
  title: string;
  evidence: string;
  meaning: string;
  solution: string;
};

export type BacktestNextAction = {
  id: string;
  type: "RERUN_PERIOD" | "VIEW_SECTION" | string;
  label: string;
  description: string;
  priority: number;
  years?: number;
  section?: string;
};

export type BacktestProblemSolver = {
  status: string;
  label: string;
  headline: string;
  summary: string;
  confidence: { level: string; label: string; reason: string };
  performance: { level: string; label: string; reason: string };
  risk: { level: string; label: string; reason: string };
  problems: BacktestProblemItem[];
  next_actions: BacktestNextAction[];
  strategy_candidate: null | {
    status: string;
    title: string;
    reason: string;
    next_validation: string;
  };
  guardrail: string;
};

export type PullbackBacktestResponse = {
  version: "0.19" | string;
  strategy: "pullback" | string;
  code: string;
  market: "KOSPI" | "KOSDAQ";
  period: { start: string; end: string };
  config: {
    initial_capital: number;
    max_holding_days: number;
    round_trip_cost_pct: number;
    minimum_strategy_score: number;
    entry_policy: string;
    entry_price_policy: string;
    same_day_stop_target_policy: string;
    stop_policy: string;
    target_policy: string;
    overlapping_positions: boolean;
    position_sizing: string;
  };
  summary: BacktestMetrics;
  assessment: { status: string; label: string; summary: string };
  problem_solver?: BacktestProblemSolver;
  accuracy_audit?: BacktestAccuracyAudit;
  risk_policy_comparison?: BacktestRiskPolicyComparison;
  diagnostics: Record<string, number>;
  score_performance: BacktestGroupMetrics[];
  entry_timing_research: Array<BacktestMetrics & { entry_timing: string; signals: number }>;
  market_regime_performance: BacktestGroupMetrics[];
  trades: BacktestTrade[];
  methodology: Record<string, string>;
  data_window: {
    requested_start: string;
    requested_end: string;
    warmup_start: string;
    first_stock_date: string;
    last_stock_date: string;
    stock_rows: number;
    index_rows: number;
    cache_note: string;
  };
  performance?: {
    data_prepare_seconds: number;
    strategy_calculation_seconds: number;
    total_seconds: number;
    history_store_hits: number;
    market_store_hits?: number;
    legacy_rows_imported?: number;
    raw_cache_hits: number;
    cached_symbol_fast_path_hits?: number;
    cached_index_fast_path_hits?: number;
    network_symbol_fast_path_hits?: number;
    network_index_fast_path_hits?: number;
    raw_market_cache_seeded?: number;
    market_wide_sqlite_promotions?: number;
    cold_start_fast_path?: boolean;
    concurrency?: number;
    single_stock_fast_path?: boolean;
    legacy_load_ms?: number;
    market_store_load_ms?: number;
    history_fill_ms?: number;
    data_prepare_ms?: number;
    cache_reuse_pct?: number;
    estimated_network_requests?: number;
    network_requests: number;
    retries: number;
    warmup_rows: number;
    budget_used?: number;
    budget_limit?: number;
    budget_remaining?: number;
  };
  warnings: string[];
};

export type PullbackBacktestRequest = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  start_date: string;
  end_date: string;
  initial_capital: number;
  max_holding_days: number;
  round_trip_cost_pct: number;
};

export async function fetchPullbackBacktest(payload: PullbackBacktestRequest): Promise<PullbackBacktestResponse> {
  return asJson<PullbackBacktestResponse>(
    await fetch("/api/backtest/pullback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}


export type BacktestJob<TResult = PullbackBacktestResponse> = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | string;
  stage: string;
  progress: {
    current: number;
    total: number;
    percent: number;
    message: string;
    details: Record<string, number | string | boolean | null>;
  };
  result: TResult | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  elapsed_seconds: number;
};

export async function createPullbackBacktestJob(payload: PullbackBacktestRequest): Promise<BacktestJob> {
  return asJson<BacktestJob>(
    await fetch("/api/backtest/pullback/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function createRiskPolicyValidationJob(payload: PullbackBacktestRequest): Promise<BacktestJob<RiskPolicyCrossValidationResponse>> {
  return asJson<BacktestJob<RiskPolicyCrossValidationResponse>>(
    await fetch("/api/backtest/pullback/risk-policy-validation/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchBacktestJob<TResult = PullbackBacktestResponse>(jobId: string): Promise<BacktestJob<TResult>> {
  return asJson<BacktestJob<TResult>>(await fetch(`/api/backtest/jobs/${encodeURIComponent(jobId)}`));
}

export async function cancelBacktestJob<TResult = PullbackBacktestResponse>(jobId: string): Promise<BacktestJob<TResult>> {
  return asJson<BacktestJob<TResult>>(
    await fetch(`/api/backtest/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" }),
  );
}

export type MultiStrategyHistoricalFit = {
  status: "GOOD" | "FAIR" | "WEAK" | "INSUFFICIENT" | string;
  label: string;
  summary: string;
};

export type ProductionExitPolicyMetadata = {
  policy_id: string;
  policy_version?: string;
  label: string;
  target1_is_exit: boolean;
  target2_included: boolean;
  target2_label: string;
  holding_policy?: string;
  post_target2_horizon_days?: number;
  policy_source?: string;
  fallback_used?: boolean;
  fallback_reason?: string | null;
  profit_protection?: {
    enabled: boolean;
    activation: "AFTER_TARGET2" | null | string;
    state: "NOT_APPLICABLE" | "POSITION_CONTEXT_REQUIRED" | "PROTECTION_ACTIVE" | string;
    current_protection_price: number | null;
    protection_never_decreases?: boolean;
  };
};

export type ConcretePricePlanConsistency = {
  status: "OK" | "WARNING" | "INVALID" | "NOT_APPLICABLE" | string;
  classification?: "STRATEGY_CONDITION_BAND_OVERLAP" | "DISPLAY_ROUNDING_TOUCH" | "RISK_PLAN_INVALID" | "EXECUTION_PRICE_CONFLICT" | "SEPARATED" | "NOT_APPLICABLE" | string;
  has_conflict: boolean;
  message: string;
  relation_message: string | null;
  root_cause_summary?: string | null;
  issue_codes: string[];
  issues: Array<{ code: string; severity: string; detail: string }>;
  raw_overlap: boolean;
  semantic_overlap?: boolean;
  display_overlap_only: boolean;
  overlap?: { low: number | null; high: number | null; width: number | null; ratio_pct: number | null };
  trace_context?: {
    strategy: string;
    analysis_date: string | null;
    decision_reason: string | null;
    current_price: number | null;
    strategy_rule_status: string | null;
    strategy_rule_basis: string | null;
    strategy_rule_role: string | null;
    risk_status: string | null;
    risk_reference_only: boolean;
    risk_entry_reference: number | null;
    risk_structural_anchor: number | null;
    risk_structural_anchor_label: string | null;
  };
  raw: {
    condition_range_low?: number | null;
    condition_range_high?: number | null;
    entry_range_low: number | null;
    entry_range_high: number | null;
    risk_entry_reference: number | null;
    invalidation_price: number | null;
    stop_zone_low: number | null;
    stop_zone_high: number | null;
    display_stop_zone_low?: number | null;
    display_stop_zone_high?: number | null;
    target1_price: number | null;
    target2_price: number | null;
  };
  display: {
    condition_range_low?: number | null;
    condition_range_high?: number | null;
    entry_range_low: number | null;
    entry_range_high: number | null;
    invalidation_price: number | null;
    stop_zone_low: number | null;
    stop_zone_high: number | null;
  };
  sources: {
    strategy_price?: string;
    entry: string;
    risk_entry: string;
    stop: string;
    invalidation: string;
    targets: string;
  };
};

export type ConcreteEntryRiskGuide = {
  strategy: string;
  as_of_date: string | null;
  current_price: number | null;
  display_current_price?: number | null;
  price_rule: {
    kind: "RANGE" | "ABOVE" | "AT_OR_BELOW" | "REFERENCE" | "UNAVAILABLE" | string;
    label: string;
    status: string;
    basis: string | null;
    range_low: number | null;
    range_high: number | null;
    trigger_price: number | null;
    reference_price: number | null;
    display_range_low?: number | null;
    display_range_high?: number | null;
    display_trigger_price?: number | null;
    display_reference_price?: number | null;
    gap_pct: number | null;
    message: string;
    semantic_role?: "STRATEGY_CONDITION_BAND" | "STRATEGY_CONDITION_THRESHOLD" | "STRATEGY_REFERENCE" | string;
    user_label?: string;
    executable_entry_range?: boolean;
    semantic_note?: string;
  };
  volume_rule: {
    available: boolean;
    status: string;
    current_ratio: number | null;
    required_ratio: number | null;
    comparator: "AT_LEAST" | "AT_MOST" | string | null;
    gap_pct: number | null;
    basis: string | null;
    message: string;
  };
  trend_strength: {
    available: boolean;
    label: string;
    current_value: number | null;
    required_value: string | null;
    status: string;
    metric_key: string | null;
    message: string;
  };
  rebound_rule: {
    available: boolean;
    status: string;
    trigger_price: number | null;
    gap_pct: number | null;
    basis: string | null;
    message: string;
  };
  risk: {
    available: boolean;
    status: string | null;
    reference_only: boolean;
    entry_reference_price: number | null;
    structural_anchor: number | null;
    structural_anchor_label: string | null;
    invalidation_price: number | null;
    display_invalidation_price?: number | null;
    stop_zone_low: number | null;
    stop_zone_high: number | null;
    display_stop_zone_low?: number | null;
    display_stop_zone_high?: number | null;
    target1_price: number | null;
    display_target1_price?: number | null;
    target1_basis?: string | null;
    structural_target1_price?: number | null;
    display_structural_target1_price?: number | null;
    structural_target1_basis?: string | null;
    target1_cap_price?: number | null;
    display_target1_cap_price?: number | null;
    target1_cap_applied?: boolean;
    target1_fallback_used?: boolean;
    target2_price: number | null;
    display_target2_price?: number | null;
    target2_basis?: string | null;
    target1_audit?: {
      available: boolean;
      formula_status: "MATCH" | "MISMATCH" | "UNAVAILABLE" | string;
      message: string;
      entry_reference_price?: number | null;
      stop_reference_price?: number | null;
      risk_amount?: number | null;
      risk_pct?: number | null;
      one_r_price?: number | null;
      one_half_r_price?: number | null;
      two_r_price?: number | null;
      target1_price?: number | null;
      target1_basis?: string | null;
      target1_basis_code?: string | null;
      target1_gain_pct?: number | null;
      target1_r_multiple?: number | null;
      target2_price?: number | null;
      target2_gain_pct?: number | null;
      target2_r_multiple?: number | null;
      expected_target1_price?: number | null;
      expected_target1_basis?: string | null;
      expected_target1_basis_code?: string | null;
      structural_target1_price?: number | null;
      structural_target1_basis?: string | null;
      structural_target1_kind?: string | null;
      target1_cap_price?: number | null;
      target1_cap_applied?: boolean;
      target1_fallback_used?: boolean;
      policy?: string;
      guardrail?: string;
      structural_candidates?: Array<{
        kind: string;
        label: string;
        price: number | null;
        gain_pct: number | null;
        r_multiple: number | null;
        selected: boolean;
      }>;
    } | null;
    risk_pct: number | null;
    reward1_pct: number | null;
    reward2_pct: number | null;
    rr1: number | null;
    rr2: number | null;
    structure_rating: string | null;
    summary: string | null;
    warnings: string[];
    needs_recheck: boolean;
    basis_label: string;
    recheck_message: string | null;
  };
  price_consistency?: ConcretePricePlanConsistency | null;
  action: { status: string; title: string; detail: string };
  historical_verification: { verified: boolean | null; status: string | null; message: string };
  historical_policy?: ProductionExitPolicyMetadata;
  guardrail: string;
};

export type MultiStrategyCurrentState = {
  status: "READY" | "WATCH" | "CAUTION" | "BLOCKED" | "NOT_READY" | string;
  label: string;
  summary: string;
  score: number;
  passed: number;
  missing?: number;
  total: number;
  risk_status: string | null;
  reference_only?: boolean;
  risk_warning?: boolean;
  warnings?: string[];
  decision_reason?: string;
  conditions_complete?: boolean;
  condition_consistency?: {
    ok: boolean;
    engine_passed: number;
    engine_missing: number;
    engine_total: number;
    detail_passed: number;
    detail_missing: number;
    detail_total: number;
  };
  unmet: string[];
  reasons: string[];
  reason_details?: MultiStrategyConditionDetail[];
  unmet_details?: MultiStrategyConditionDetail[];
  suitability?: string;
  eligible?: boolean;
  entry_risk_guide?: ConcreteEntryRiskGuide | null;
};

export type MultiStrategyGuide = {
  easy_name: string;
  professional_name: string;
  description: string;
  when_to_use: string;
};

export type MultiStrategyConditionDetail = {
  condition_id?: string;
  raw: string;
  label: string;
  detail: string;
  status?: "PASS" | "FAIL" | "UNKNOWN" | string;
  current_value?: string | null;
  required_value?: string | null;
  metric_key?: string | null;
};

export type MultiStrategyRow = {
  strategy: string;
  label: string;
  guide: MultiStrategyGuide;
  rank: number;
  selector_score: number;
  historical_fit: MultiStrategyHistoricalFit;
  historical_metrics: BacktestMetrics & {
    closed_trade_max_drawdown_pct?: number;
    max_drawdown_basis?: string;
  };
  signal_count: number;
  risk_blocked_signals: number;
  current: MultiStrategyCurrentState;
  recent_trades: BacktestTrade[];
};

export type MultiStrategyRecommendation = {
  strategy: string | null;
  strategy_label: string | null;
  strategy_easy_name: string | null;
  strategy_description: string | null;
  strategy_when_to_use: string | null;
  action: "ENTRY_CANDIDATE" | "WAIT" | "NO_TRADE" | "NEEDS_VALIDATION" | string;
  action_label: string;
  headline: string;
  reason: string;
  decision_reason?: string;
  additional_warnings?: string[];
  change_conditions: string[];
  change_condition_details: MultiStrategyConditionDetail[];
  user_action: {
    user_task: string;
    title: string;
    detail: string;
    has_immediate_task: boolean;
    stockscope_title: string;
    stockscope_detail: string;
    next_transition: string;
  };
  recheck_mode: "ON_NEXT_ANALYSIS" | string;
  recheck_label: string;
  as_of_date: string;
  market_regime: string;
  guardrail?: string;
  entry_risk_guide?: ConcreteEntryRiskGuide | null;
  historical_best_strategy?: string | null;
  historical_best_easy_name?: string | null;
  historical_best_label?: string | null;
  historical_best_current_status?: string | null;
  historical_best_current_label?: string | null;
  historical_best_passed?: number | null;
  historical_best_total?: number | null;
  selection_rule?: string;
};

export type MultiStrategyBacktestResponse = {
  version: "0.20" | "0.20.1" | "0.20.2" | string;
  code: string;
  market: "KOSPI" | "KOSDAQ";
  period: { start: string; end: string };
  as_of_date: string;
  market_regime: string;
  recommendation: MultiStrategyRecommendation;
  strategies: MultiStrategyRow[];
  historical_policy?: ProductionExitPolicyMetadata;
  config: {
    minimum_strategy_score: number;
    entry_policy: string;
    entry_price_policy: string;
    risk_exit_framework: string;
    same_day_stop_target_policy: string;
    target_policy: string;
    max_holding_days: number;
    round_trip_cost_pct: number;
    overlapping_positions: string;
  };
  methodology: Record<string, string>;
  data_window: PullbackBacktestResponse["data_window"];
  performance?: PullbackBacktestResponse["performance"];
  warnings: string[];
};

export async function createMultiStrategyBacktestJob(payload: PullbackBacktestRequest): Promise<BacktestJob<MultiStrategyBacktestResponse>> {
  return asJson<BacktestJob<MultiStrategyBacktestResponse>>(
    await fetch("/api/backtest/multi-strategy/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export type ExitPolicyAggregateMetrics = {
  trades: number;
  win_rate_pct: number | null;
  average_net_return_pct: number | null;
  profit_factor: number | null;
  median_max_drawdown_pct: number | null;
  worst_max_drawdown_pct: number | null;
  average_holding_days: number | null;
  average_profit_giveback_pct_points: number | null;
};

export type ExitPolicyValidationPolicy = {
  policy_id: string;
  stock_count: number;
  markets: string[];
  aggregate_metrics: ExitPolicyAggregateMetrics;
};

export type ExitPolicyValidationStrategy = {
  strategy: string;
  status: "SELECTED" | "BASELINE_BETTER" | "UNRESOLVED" | "INSUFFICIENT_SAMPLE" | string;
  selected_policy_id: string;
  reason: string;
  baseline?: ExitPolicyValidationPolicy | null;
  selected?: ExitPolicyValidationPolicy | null;
  policies: ExitPolicyValidationPolicy[];
  stock_concentration?: {
    single_stock_dominant?: boolean;
    dominant_code?: string | null;
    [key: string]: unknown;
  };
  regime_metrics?: Record<string, {
    trades: number;
    win_rate_pct: number | null;
    average_net_return_pct: number | null;
    profit_factor: number | null;
  }>;
  max_hold_validation?: {
    status: string;
    selected: string | null;
    reason: string;
  };
};

export type ExitPolicyValidationReport = {
  version: string;
  runner_version?: string;
  research_only: boolean;
  production_policy_changed: false;
  status: "COMPLETED" | "DATA_REQUIRED" | string;
  message?: string;
  signature: string;
  period: { start: string; end: string };
  validation_config?: {
    max_holding_days?: number;
    post_target2_research_days?: number;
    [key: string]: unknown;
  };
  sample?: {
    stocks: number;
    markets: string[];
    minimum_stock_count: number;
    minimum_total_trades: number;
    market_diversity_warning: boolean;
  };
  summary?: {
    selected: number;
    baseline_better: number;
    unresolved: number;
    insufficient_sample: number;
    production_policy_changed: false;
  };
  strategies?: ExitPolicyValidationStrategy[];
  selected_stocks?: Array<{ code: string; market: string; coverage_pct?: number; row_count?: number }>;
  validated_stocks?: Array<{ code: string; market: string }>;
  excluded_stocks?: Array<{ code: string; market: string; reason: string }>;
  market_availability?: Record<string, {
    trading_days: number;
    index_days: number;
    index_coverage_pct: number;
    candidates: Array<{ code: string; market: string; coverage_pct: number; row_count: number }>;
  }>;
  expanded_revalidation?: {
    version?: string;
    base_signature: string;
    expanded_signature: string;
    base_stock_count: number;
    expanded_stock_count: number;
    target_stock_count?: number;
    conditions_match: boolean;
    comparison_fingerprint?: string;
    strategy_count: number;
    same_status_count: number;
    changed_status_count: number;
    same_policy_count?: number;
    previously_sensitive_strategies?: string[];
    previously_sensitive_same_status?: number;
    previously_sensitive_changed_status?: number;
    outcome?: "NO_CANDIDATE_STABLE" | "BASELINE_STRENGTHENED" | "NEW_CANDIDATE" | "MIXED_OR_UNSTABLE" | string;
    transitions?: Record<string, number>;
    strategies: Array<{
      strategy: string;
      before_status: string;
      after_status: string;
      before_policy_id?: string;
      after_policy_id?: string;
      status_same: boolean;
      policy_same?: boolean;
    }>;
    base_summary?: Record<string, unknown>;
    expanded_summary?: Record<string, unknown>;
    sample_plan?: {
      base_market_counts?: Record<string, number>;
      target_market_counts?: Record<string, number>;
      ready_stock_count?: number;
    };
  };
  checkpoint?: {
    reused_stocks: number;
    same_sample_reused_stocks?: number;
    cross_sample_reused_stocks?: number;
    completed_stocks: number;
    resumable?: boolean;
  };
  performance: {
    cache_lookup_seconds?: number;
    market_store_load_seconds?: number;
    exit_policy_calculation_seconds?: number;
    selection_seconds?: number;
    total_seconds: number;
    network_requests: number;
    reused_stock_count?: number;
    same_sample_reused_stock_count?: number;
    cross_sample_reused_stock_count?: number;
    calculated_stock_count?: number;
    research_workers?: number;
  };
  report?: { saved: boolean; filename: string; runtime_area: string };
};

export type ExitPolicyValidationRunnerRequest = {
  start_date: string;
  end_date: string;
  markets?: Array<"KOSPI" | "KOSDAQ">;
  max_stocks?: number;
  minimum_coverage_pct?: number;
  initial_capital: number;
  max_holding_days: number;
  round_trip_cost_pct: number;
  minimum_stock_count?: number;
  minimum_total_trades?: number;
  post_target2_research_days?: number;
  force_refresh?: boolean;
};

export async function createExitPolicyValidationJob(
  payload: ExitPolicyValidationRunnerRequest,
): Promise<BacktestJob<ExitPolicyValidationReport>> {
  return asJson<BacktestJob<ExitPolicyValidationReport>>(
    await fetch("/api/backtest/exit-policy-validation/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchLatestExitPolicyValidationReport(): Promise<{ available: boolean; report: ExitPolicyValidationReport | null }> {
  return asJson<{ available: boolean; report: ExitPolicyValidationReport | null }>(
    await fetch("/api/backtest/exit-policy-validation/latest"),
  );
}

export async function fetchExitPolicyValidationReport(
  signature: string,
): Promise<{ available: boolean; report: ExitPolicyValidationReport | null }> {
  return asJson<{ available: boolean; report: ExitPolicyValidationReport | null }>(
    await fetch(`/api/backtest/exit-policy-validation/report/${encodeURIComponent(signature)}`),
  );
}

export type ExitPolicyValidationHistoryItem = {
  signature: string;
  status: string;
  created_at: string;
  period: { start: string; end: string };
  stock_count: number;
  max_holding_days: number | null;
  summary: {
    selected: number;
    baseline_better: number;
    unresolved: number;
    insufficient_sample: number;
  };
  is_expanded: boolean;
  base_signature: string | null;
  expanded_from: number | null;
};

export async function fetchExitPolicyValidationHistory(
  limit = 20,
): Promise<{ available: boolean; rows: ExitPolicyValidationHistoryItem[] }> {
  const query = new URLSearchParams({ limit: String(limit) });
  return asJson<{ available: boolean; rows: ExitPolicyValidationHistoryItem[] }>(
    await fetch(`/api/backtest/exit-policy-validation/history?${query.toString()}`),
  );
}

export type ExpandedSamplePlan = {
  version: string;
  base_signature: string;
  comparison_fingerprint: string;
  period: { start: string; end: string };
  markets: string[];
  base_stock_count: number;
  target_stock_count: number;
  ready_stock_count: number;
  additional_stock_count: number;
  ready_to_run: boolean;
  missing_base_stocks: string[];
  base_market_counts: Record<string, number>;
  target_market_counts: Record<string, number>;
  selected_stocks: Array<{ code: string; market: string; coverage_pct?: number; row_count?: number }>;
  data_preparation: {
    needed: boolean;
    can_prepare: boolean;
    missing_history_items: number;
    cached_history_items: number | null;
    estimated_network_requests: number | null;
    note: string;
  };
};

export type ExpandedSamplePreparationResult = {
  version: string;
  status: "READY" | "PARTIAL" | "DATA_LIMIT" | string;
  message: string;
  plan: ExpandedSamplePlan;
  errors?: string[];
  performance?: {
    total_seconds?: number;
    prepared_items?: number;
    error_count?: number;
    network_requests?: number;
  };
};

export type ExpandedSampleRequest = {
  target_stocks: 20 | 40 | 60;
  base_signature?: string | null;
  force_refresh?: boolean;
};

export async function planExpandedExitPolicyValidation(payload: ExpandedSampleRequest): Promise<ExpandedSamplePlan> {
  return asJson<ExpandedSamplePlan>(
    await fetch("/api/backtest/exit-policy-validation/expanded/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function createExpandedSamplePreparationJob(
  payload: ExpandedSampleRequest,
): Promise<BacktestJob<ExpandedSamplePreparationResult>> {
  return asJson<BacktestJob<ExpandedSamplePreparationResult>>(
    await fetch("/api/backtest/exit-policy-validation/expanded/prepare/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function createExpandedExitPolicyValidationJob(
  payload: ExpandedSampleRequest,
): Promise<BacktestJob<ExitPolicyValidationReport>> {
  return asJson<BacktestJob<ExitPolicyValidationReport>>(
    await fetch("/api/backtest/exit-policy-validation/expanded/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export type ExitPolicyResearchAuditStrategy = {
  strategy: string;
  research_status: string;
  research_status_label: string;
  selected_policy_id: string;
  decision_trace?: {
    reported_status?: string;
    replayed_status?: string;
    reported_policy_id?: string;
    replayed_policy_id?: string;
    reason_code?: string;
    reason?: string;
  };
  baseline_sample?: {
    trades?: number;
    participating_stocks?: number;
    market_trades?: Record<string, number>;
    largest_stock_trade_share_pct?: number | null;
    top1_abs_net_contribution_share_pct?: number | null;
    top3_abs_net_contribution_share_pct?: number | null;
    largest_contributors?: Array<{
      code?: string;
      market?: string;
      trades?: number;
      net_return_sum_pct?: number;
    }>;
  };
  entry_set?: {
    status?: string;
    divergent_stock_count?: number;
    recent_trade_samples_checked?: number;
    recent_trade_entry_mismatches?: number;
    matched_entry_equality_proven?: boolean;
    note?: string;
  };
  leave_one_out?: {
    status?: string;
    runs?: number;
    same_status?: number;
    same_policy?: number;
    same_status_pct?: number | null;
    status_counts?: Record<string, number>;
    unstable_removed_stocks?: Array<{
      removed?: string;
      status?: string;
      status_label?: string;
      selected_policy_id?: string;
    }>;
  };
  regimes?: Array<{
    regime: string;
    trades: number;
    share_pct: number | null;
    average_net_return_pct: number | null;
    profit_factor: number | null;
  }>;
};

export type ExitPolicyResearchAuditReport = {
  version: string;
  available: boolean;
  status: "PASS" | "PASS_WITH_NOTES" | "FAIL" | "DATA_REQUIRED" | string;
  message?: string;
  validation_signature?: string;
  validation_period?: { start?: string; end?: string } | null;
  checked_at?: string;
  research_only?: boolean;
  production_policy_changed?: false;
  summary?: {
    critical_issue_count?: number;
    critical_issues?: string[];
    note_count?: number;
    notes?: string[];
    validated_stocks?: number;
    strategy_count?: number;
    leave_one_out_sensitive_strategies?: number;
    policy_dependent_entry_strategies?: number;
    high_concentration_strategies?: number;
  };
  checks?: {
    data_coverage?: {
      status?: string;
      minimum_coverage_pct?: number;
      selected_stocks?: number;
      validated_stocks?: number;
      excluded_stocks?: number;
      market_counts?: Record<string, number>;
      low_coverage_stocks?: string[];
      index_coverage_failures?: string[];
      missing_checkpoint_audits?: string[];
      stocks?: Array<{
        code?: string;
        market?: string;
        coverage_pct?: number | null;
        row_count?: number;
        trading_days?: number;
        first_date?: string;
        last_date?: string;
        validated?: boolean;
      }>;
      markets?: Array<{
        market?: string;
        trading_days?: number;
        index_days?: number;
        index_coverage_pct?: number | null;
      }>;
    };
    aggregate_replay?: {
      status?: string;
      checked_policy_aggregates?: number;
      mismatch_count?: number;
      basis?: string;
    };
    decision_replay?: {
      status?: string;
      mismatch_count?: number;
      selection_basis?: string;
    };
    guardrails?: {
      status?: string;
      config_mismatch_count?: number;
      recent_trailing_trade_samples?: number;
      recent_non_decreasing_failures?: number;
      recent_same_day_stop_priority_samples?: number;
      scope?: string;
      limitation?: string;
    };
    leave_one_out?: {
      status?: string;
      sensitive_strategies?: string[];
      strategy_count?: number;
    };
    entry_set?: {
      status?: string;
      policy_dependent_strategies?: string[];
      matched_entry_equality_proven?: boolean;
    };
  };
  strategies?: ExitPolicyResearchAuditStrategy[];
  limitations?: string[];
  report?: { saved?: boolean; filename?: string; runtime_area?: string };
};

export async function runExitPolicyValidationAudit(): Promise<ExitPolicyResearchAuditReport> {
  return asJson<ExitPolicyResearchAuditReport>(
    await fetch("/api/backtest/exit-policy-validation/audit", { method: "POST" }),
  );
}

export async function fetchLatestExitPolicyValidationAudit(): Promise<{ available: boolean; report: ExitPolicyResearchAuditReport | null }> {
  return asJson<{ available: boolean; report: ExitPolicyResearchAuditReport | null }>(
    await fetch("/api/backtest/exit-policy-validation/audit/latest"),
  );
}

export type ProductionExitPolicyStrategy = {
  policy_id: string;
  holding_policy?: string;
  post_target2_horizon_days?: number;
  research_status?: string | null;
  research_reason?: string | null;
  fallback_used?: boolean;
  fallback_reason?: string | null;
};

export type ProductionExitPolicyStatus = {
  available: boolean;
  policy_version: string;
  mapping: null | {
    production_policy_changed?: boolean;
    validation_signature?: string | null;
    validation_period?: { start?: string; end?: string } | null;
    validation_config?: {
      max_holding_days?: number;
      post_target2_research_days?: number;
      [key: string]: unknown;
    };
    strategies?: Record<string, ProductionExitPolicyStrategy>;
    [key: string]: unknown;
  };
  cache_token: string;
};

export async function fetchExitPolicyProductionStatus(): Promise<ProductionExitPolicyStatus> {
  return asJson<ProductionExitPolicyStatus>(
    await fetch("/api/backtest/exit-policy-production/status"),
  );
}

export type ScannerConditionDetail = MultiStrategyConditionDetail;

export type ScannerHistoricalEvidence = {
  status: "GOOD" | "FAIR" | "WEAK" | "INSUFFICIENT" | "NO_CASES" | "DATA_UNAVAILABLE" | string;
  label: string;
  summary: string;
  verified: boolean;
  unavailable_reason?: "MISSING_HISTORY" | "UNSUPPORTED_STRATEGY" | string | null;
  preparation_available?: boolean;
  sample_sufficient: boolean;
  minimum_sample: number;
  validation_years: number;
  period: { start: string; end: string };
  sample_count: number;
  wins: number;
  losses: number;
  win_rate_pct: number | null;
  average_net_return_pct: number | null;
  median_net_return_pct: number | null;
  expectancy_pct: number | null;
  profit_factor: number | null;
  max_drawdown_pct: number | null;
  average_win_pct: number | null;
  average_loss_pct: number | null;
  exit_counts: { stop: number; target1: number; time_exit: number; other: number };
  market_regime_summary: Array<{
    regime: string;
    trades: number;
    average_net_return_pct: number;
    wins: number;
    losses: number;
  }>;
  warnings: string[];
  target1_audit?: {
    available: boolean;
    sample_count: number;
    skipped_trades?: number;
    max_holding_days?: number;
    average_target_distance_pct?: number | null;
    median_target_distance_pct?: number | null;
    average_target_r_multiple?: number | null;
    median_target_r_multiple?: number | null;
    target_hit_count?: number;
    target_hit_pct?: number | null;
    target_hit_days?: { within_5_days: number; within_10_days: number; within_20_days: number };
    average_target_hit_days?: number | null;
    median_target_hit_days?: number | null;
    stop_first_count?: number;
    time_exit_count?: number;
    distance_bins?: Array<{ label: string; sample_count: number }>;
    basis_summary?: Array<{
      basis_code: string;
      label: string | null;
      sample_count: number;
      average_target_distance_pct: number | null;
      average_target_r_multiple: number | null;
    }>;
    policy_comparison?: Array<{
      policy_id: string;
      label: string;
      sample_count: number;
      target_hit_count: number;
      target_hit_pct: number | null;
      stop_first_count: number;
      time_exit_count: number;
      average_net_return_pct: number | null;
      median_net_return_pct: number | null;
      profit_factor: number | null;
      closed_trade_max_drawdown_pct: number | null;
      average_holding_days: number | null;
      average_target_hit_days: number | null;
    }>;
    comparison_mode?: string;
    comparison_limitations?: string[];
    guardrail?: string;
  } | null;
  guardrail: string;
  signal_count?: number;
  risk_blocked_signals?: number;
  strategy?: string;
};


export type ScannerCandidatePriority = {
  tier: "READY" | "NEAR_READY" | "WAIT" | "RISK_HOLD" | "LOW_PRIORITY" | string;
  label: string;
  reason: string;
  strengths: string[];
  facts: string[];
  penalties: string[];
  entry_gap_pct: number | null;
  entry_gap_basis: string | null;
  historical_status: string;
  ranking_rule: string;
  rank: number;
  previous_rank: number;
  rank_change: number;
};

export type ScannerCandidate = {
  code: string;
  name: string;
  market: "KOSPI" | "KOSDAQ";
  data_date: string;
  current_price: number | null;
  candidate_state: "READY" | "WATCH" | "VALIDATION" | "EXCLUDED" | string;
  candidate_label: string;
  strategy: string;
  strategy_easy_name: string;
  strategy_name: string;
  strategy_description: string;
  action: "ENTRY_CANDIDATE" | "WAIT" | "NO_TRADE" | "NEEDS_VALIDATION" | string;
  action_label: string;
  headline: string;
  reason: string;
  conditions: {
    passed: number;
    total: number;
    missing: number;
    top_missing: ScannerConditionDetail[];
  };
  risk: {
    status: string | null;
    warning: boolean;
    warnings: string[];
  };
  historical_fit: {
    status: string;
    label: string;
    summary: string;
    trades: number;
    verified?: boolean;
  };
  verification_level?: "CURRENT_ONLY" | "CURRENT_AND_HISTORY" | "CURRENT_AND_3Y_EVIDENCE" | string;
  historical_evidence?: ScannerHistoricalEvidence | null;
  priority?: ScannerCandidatePriority | null;
  entry_risk_guide?: ConcreteEntryRiskGuide | null;
  user_action: {
    title: string | null;
    detail: string | null;
    next_transition: string | null;
  };
};

export type ScannerResponse = {
  version: string;
  scanner_cache_hit: boolean;
  generated_at: string;
  requested_as_of: string;
  market_scope: "ALL" | "KOSPI" | "KOSDAQ";
  data_dates: Partial<Record<"KOSPI" | "KOSDAQ", string>>;
  market_summary: Array<{
    market: "KOSPI" | "KOSDAQ";
    data_date: string;
    regime: string;
  }>;
  partial_data?: boolean;
  preparation_required?: Array<{
    market: "KOSPI" | "KOSDAQ" | string;
    estimated_network_requests: number;
    items_missing: number;
    message: string;
  }>;
  fast_request_limit?: number;
  summary: {
    universe_total: number;
    special_excluded: number;
    liquidity_filtered: number;
    quick_analyzed: number;
    data_insufficient: number;
    deep_analyzed: number;
    historically_verified?: number;
    current_only?: number;
    three_year_evidence_verified?: number;
    three_year_evidence_data_unavailable?: number;
    three_year_evidence_sample_insufficient?: number;
    three_year_evidence_cache_hits?: number;
    candidate_count: number;
    shown_count: number;
    excluded_after_analysis: number;
  };
  candidates: ScannerCandidate[];
  more_candidates: ScannerCandidate[];
  empty_message: string | null;
  exclusion_policy: {
    default: string[];
    liquidity: string;
  };
  methodology: {
    meaning: string;
    pipeline: string[];
    guardrail: string;
  };
  diagnostics: {
    market_store_reused_items: number;
    estimated_network_requests: number;
    network_requests: number;
    raw_cache_hits: number;
    retries: number;
    budget_used: number;
    budget_limit: number;
    budget_remaining: number;
    fast_request_limit?: number;
    large_sync_blocked?: boolean;
    bootstrap_processed_items?: number;
    bootstrap_peak_concurrency?: number;
    bootstrap_errors?: number;
    bootstrap_request_rate?: number;
    data_prepare_seconds?: number;
    quick_filter_seconds?: number;
    deep_analysis_seconds?: number;
    total_seconds?: number;
    ranking_changes?: Array<{
      code: string;
      name: string;
      previous_rank: number;
      new_rank: number;
      rank_change: number;
      tier: string;
      reason: string;
    }>;
  };
};

export type ScannerRequest = {
  market_scope?: "ALL" | "KOSPI" | "KOSDAQ";
  as_of_date?: string;
  candidate_limit?: number;
  force_refresh?: boolean;
  allow_large_sync?: boolean;
};

export type ScannerFreshnessResponse = {
  status: "READY" | "UPDATED" | "UPDATE_FAILED" | "DATA_INCONSISTENT" | string;
  market_scope: "ALL" | "KOSPI" | "KOSDAQ";
  requested_date: string;
  latest_confirmed_date: string | null;
  resolved_as_of_date: string | null;
  known_data_date: string | null;
  previous_data_dates: Partial<Record<"KOSPI" | "KOSDAQ", string | null>>;
  previous_index_dates?: Partial<Record<"KOSPI" | "KOSDAQ", string | null>>;
  data_dates: Partial<Record<"KOSPI" | "KOSDAQ", string | null>>;
  available_data_date: string | null;
  stored_common_date?: string | null;
  current_date_valid?: boolean;
  fallback_allowed?: boolean;
  consistency_status?: string;
  failure_reason?: string | null;
  market_data_updated: boolean;
  date_changed: boolean;
  updated_dates: string[];
  diagnostics: { network_requests: number; raw_cache_hits: number; retries: number };
  message: string;
};

export async function prepareScannerLatestData(payload: {
  market_scope?: "ALL" | "KOSPI" | "KOSDAQ";
  known_data_date?: string | null;
}): Promise<ScannerFreshnessResponse> {
  return asJson<ScannerFreshnessResponse>(
    await fetch("/api/backtest/scanner/freshness", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function createScannerJob(payload: ScannerRequest): Promise<BacktestJob<ScannerResponse>> {
  return asJson<BacktestJob<ScannerResponse>>(
    await fetch("/api/backtest/scanner/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}


export type ScannerEvidencePrepareRequest = {
  market: "KOSPI" | "KOSDAQ";
  code: string;
  strategy: string;
  data_end: string;
  market_scope: "ALL" | "KOSPI" | "KOSDAQ";
  candidate_limit?: number;
};

export async function createScannerEvidenceJob(
  payload: ScannerEvidencePrepareRequest,
): Promise<BacktestJob<ScannerResponse>> {
  return asJson<BacktestJob<ScannerResponse>>(
    await fetch("/api/backtest/scanner/evidence/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}
