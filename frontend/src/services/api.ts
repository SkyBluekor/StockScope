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
