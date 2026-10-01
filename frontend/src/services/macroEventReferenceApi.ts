export type MacroEventReferenceItem = {
  event_type: string;
  relation_type: string;
  relevance_state: string;
  quality_state: "USABLE" | "LIMITED" | string;
  source_kinds: string[];
  available_at: string;
  evidence_as_of: string;
  revision_state: string;
  assessment_as_of: string;
};

export type MacroEventReferenceResponse = {
  contract_version: string;
  status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | string;
  decision_cutoff: string;
  scope: {
    market: "KOSPI" | "KOSDAQ" | string;
    ticker: string;
  };
  composition_id: string;
  composition_hash: string;
  macro: {
    status: string;
    usage_mode: string | null;
  };
  impact: {
    status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | string;
    reason: string | null;
    window: {
      start_date: string | null;
      end_date: string | null;
    };
    market_return_pct: string | null;
    stock_return_pct: string | null;
    stock_vs_market_pctp: string | null;
  };
  sector: {
    historical_sector_status: string;
    historical_impact_mode: string;
    prospective_sector_status: string;
  };
  event_source: {
    reader_status: "AVAILABLE" | "UNAVAILABLE" | string;
    reason: string | null;
    projection_mode: string;
  };
  event_reference: {
    status: string;
    source_status: string;
    source_reference_count: number;
    eligible_reference_count: number;
    latest_as_of: string | null;
    historical_completeness_proven: false;
    items: MacroEventReferenceItem[];
  };
  value_validation: {
    status: string;
    product_scope: string;
  };
  prediction: {
    status: "NOT_VALIDATED" | string;
    direction: null;
    horizon_sessions: null;
    probability: null;
  };
  identity_policy: string;
  limitations: string[];
  governance: {
    claim_scope: string;
    causal_attribution: false;
    macro_exposure_relation_created: false;
    prediction_approved: false;
    strategy_input_approved: false;
    scanner_input_approved: false;
    risk_gate_input_approved: false;
    holdings_plan_input_approved: false;
    production_decision_approved: false;
    network_access: false;
    database_write: false;
  };
  production_decision_approved: false;
};

export class MacroEventReferenceApiError extends Error {
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
    this.name = "MacroEventReferenceApiError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.reason = options.reason ?? null;
  }
}

async function asMacroEventReferenceJson(
  response: Response,
): Promise<MacroEventReferenceResponse> {
  if (response.ok) {
    return response.json() as Promise<MacroEventReferenceResponse>;
  }

  let message = `시장·이벤트 참고 데이터 조회 실패 (${response.status})`;
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

  throw new MacroEventReferenceApiError(message, {
    status: response.status,
    code,
    reason,
  });
}

export async function fetchMacroEventReference(
  market: "KOSPI" | "KOSDAQ",
  ticker: string,
  endDate: string,
  cutoff: string,
  options: {
    signal?: AbortSignal;
  } = {},
): Promise<MacroEventReferenceResponse> {
  const query = new URLSearchParams({
    market,
    ticker: ticker.trim().toUpperCase(),
    end_date: endDate.trim(),
    cutoff,
  });

  return asMacroEventReferenceJson(
    await fetch(`/api/macro/event-reference?${query.toString()}`, {
      signal: options.signal,
    }),
  );
}
