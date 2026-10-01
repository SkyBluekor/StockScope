export type MarketStockImpactResponse = {
  contract_version: string;
  status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | string;
  macro_context: {
    contract_version: string;
    context_id: string;
    context_hash: string;
    decision_cutoff: string;
    status: string;
    limitations: string[];
  };
  impact: {
    contract_version: string;
    impact_id: string;
    impact_hash: string;
    status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | string;
    reason: string | null;
    context_ref: {
      macro_context_id: string;
      macro_context_hash: string;
      decision_cutoff: string;
    };
    scope: {
      market: "KOSPI" | "KOSDAQ" | string;
      ticker: string;
      price_basis: string;
    };
    window: {
      mode: string;
      session_count: number;
      requested_end_date: string;
      start_date: string | null;
      end_date: string | null;
      common_session_count: number;
    };
    market: {
      start_close: string | null;
      end_close: string | null;
      return_pct: string | null;
      unit?: "PERCENT" | string;
    };
    stock: {
      start_close: string | null;
      end_close: string | null;
      return_pct: string | null;
      unit?: "PERCENT" | string;
    };
    relative: {
      stock_vs_market_pctp: string | null;
      unit?: "PERCENTAGE_POINT" | string;
    };
    sector: {
      status: string;
      temporal_status: string | null;
      return_pct: string | null;
      sector_vs_market_pctp: string | null;
      stock_vs_sector_pctp: string | null;
      reason: string | null;
      production_safe: boolean;
    };
    limitations: string[];
    governance: {
      claim_scope: string;
      production_decision_approved: false;
      strategy_input_approved: false;
      scanner_input_approved: false;
      risk_gate_input_approved: false;
      holdings_plan_input_approved: false;
      network_access: false;
    };
  };
  sector_route: {
    contract_version: string;
    historical_sector_status: string;
    historical_impact_mode: string;
    prospective_sector_status: string;
    unlock_requirements: string[];
    current_unlock_state: Record<string, boolean>;
    prohibited_unlock_inputs: string[];
    limitations: string[];
    production_decision_approved: false;
  };
  production_decision_approved: false;
};

export class MarketImpactApiError extends Error {
  status: number;
  code: string | null;
  reason: string | null;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string | null;
      reason?: string | null;
    },
  ) {
    super(message);
    this.name = "MarketImpactApiError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.reason = options.reason ?? null;
  }
}

async function asMarketImpactJson(
  response: Response,
): Promise<MarketStockImpactResponse> {
  if (response.ok) {
    return response.json() as Promise<MarketStockImpactResponse>;
  }

  let message = `시장 대비 비교 데이터 조회 실패 (${response.status})`;
  let code: string | null = null;
  let reason: string | null = null;

  try {
    const body = (await response.json()) as {
      detail?:
        | string
        | {
            code?: string;
            reason?: string;
            message?: string;
          };
    };
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (body.detail) {
      code = body.detail.code ?? null;
      reason = body.detail.reason ?? null;
      message = body.detail.message ?? message;
    }
  } catch {
    // Keep the neutral fallback message.
  }

  throw new MarketImpactApiError(message, {
    status: response.status,
    code,
    reason,
  });
}

export async function fetchMarketStockImpact(
  market: "KOSPI" | "KOSDAQ",
  ticker: string,
  endDate: string,
  options: {
    signal?: AbortSignal;
  } = {},
): Promise<MarketStockImpactResponse> {
  const query = new URLSearchParams({
    market,
    ticker: ticker.trim().toUpperCase(),
    end_date: endDate.trim(),
  });

  return asMarketImpactJson(
    await fetch(`/api/macro/market-stock-impact?${query.toString()}`, {
      signal: options.signal,
    }),
  );
}
