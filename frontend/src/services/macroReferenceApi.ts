export type MacroReferenceFeatureId =
  | "delta_bp_1obs"
  | "delta_bp_5obs"
  | "delta_bp_10obs";

export type MacroReferenceHorizon = {
  feature_id: MacroReferenceFeatureId;
  observation_distance: number;
  current_feature_available: boolean;
  current_feature_value: string | null;
  derived_feature_unavailable_count: number;
  reference_count: number;
  tail: {
    status: string;
    reason: string | null;
    ecdf_sup_drift_from_previous: string | null;
    adequacy_pass: null;
    threshold: null;
  };
  mad: {
    status: string;
    reason: string | null;
    median: string | null;
    mad: string | null;
    scale_status: string;
    normalized_median_shift_from_previous: string | null;
    relative_mad_change_from_previous: string | null;
    adequacy_pass: null;
    threshold: null;
  };
};

export type MacroReferenceDiagnosticResponse = {
  contract_version: string;
  status: string;
  decision_cutoff: string;
  macro_context: {
    contract_version: string;
    context_id: string;
    context_hash: string;
    status: string;
    limitations: string[];
  };
  reference_diagnostic: {
    projection_contract_version: string;
    diagnostic_contract_version: string;
    diagnostic_id: string;
    diagnostic_hash: string;
    projection_mode: "AS_OF";
    status: string;
    source: {
      series_id: string;
      decision_cutoff: string;
      eligible_observation_count: number;
      observation_refs_hash: string;
      current_observation_date: string | null;
    };
    horizons: MacroReferenceHorizon[];
    limitations: string[];
    governance: {
      claim_scope: "DESCRIPTIVE_ONLY";
      allowed_usage: string[];
      prohibited_consumers: string[];
      point_in_time_eligible: boolean;
      numeric_policy_defined: false;
      reference_adequacy: "UNRESOLVED";
      minimum_prior_observations: null;
      recommended_support: null;
      rate_spike_state: "UNCALIBRATED";
      production_decision_approved: false;
    };
    context_projection_hash: string;
  };
  reference_adequacy: {
    state: "UNRESOLVED";
    numeric_policy_defined: false;
    minimum_prior_observations: null;
    recommended_support: null;
  };
  rate_spike: {
    state: "UNCALIBRATED" | "UNKNOWN" | string;
    reason: string | null;
  };
  production_decision_approved: false;
};

export class MacroReferenceApiError extends Error {
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
    this.name = "MacroReferenceApiError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.reason = options.reason ?? null;
  }
}

async function asMacroReferenceJson(
  response: Response,
): Promise<MacroReferenceDiagnosticResponse> {
  if (response.ok) {
    return response.json() as Promise<MacroReferenceDiagnosticResponse>;
  }

  let message = `금리 참고 데이터 조회 실패 (${response.status})`;
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

  throw new MacroReferenceApiError(message, {
    status: response.status,
    code,
    reason,
  });
}

export async function fetchMacroReferenceDiagnostic(
  options: {
    cutoff?: string;
    signal?: AbortSignal;
  } = {},
): Promise<MacroReferenceDiagnosticResponse> {
  const query = new URLSearchParams();
  if (options.cutoff?.trim()) {
    query.set("cutoff", options.cutoff.trim());
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return asMacroReferenceJson(
    await fetch(`/api/macro/reference-diagnostic${suffix}`, {
      signal: options.signal,
    }),
  );
}
