export type HealthResponse = { status: string };

export type ProviderStatus = {
  krx: { configured: boolean; role: string };
  dart: { configured: boolean; role: string };
  kis: { enabled: boolean; role: string };
  real_trading: boolean;
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

async function asJson<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let message = `요청 실패 (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) message = body.detail;
  } catch {
    // Keep fallback message.
  }
  throw new Error(message);
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
): Promise<StockContext> {
  const query = new URLSearchParams({ market });
  return asJson<StockContext>(
    await fetch(`/api/stocks/${encodeURIComponent(code.trim().toUpperCase())}/context?${query.toString()}`),
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
  limitations: string[];
};

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
    await fetch(`/api/stocks/${encodeURIComponent(code.trim().toUpperCase())}/strategy-analysis?${query.toString()}`),
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
};

export type StockSearchResponse = {
  provider: "KRX";
  query: string;
  count: number;
  rows: StockSearchItem[];
  data_dates: Record<string, string>;
  warnings: string[];
};

export async function searchStocks(query: string): Promise<StockSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: "12" });
  return asJson<StockSearchResponse>(await fetch(`/api/stocks/search?${params.toString()}`));
}
