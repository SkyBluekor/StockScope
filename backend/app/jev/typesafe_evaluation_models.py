from __future__ import annotations


JEV_TYPESAFE_EVALUATION_SCHEMA_VERSION = "JEV_TYPESAFE_EVALUATION_STORAGE_V2"
JEV_TYPESAFE_EVALUATION_RUN_VERSION = "JEV_TYPESAFE_EVALUATION_RUN_V2"
JEV_TYPESAFE_EVALUATION_REPORT_VERSION = "JEV_TYPESAFE_EVALUATION_REPORT_V2"
JEV_TYPESAFE_EVALUATION_POLICY_ID = "JEV_TYPESAFE_EVALUATION_POLICY_V2"

JEV_TYPESAFE_EVALUATION_STATES = frozenset(
    {
        "COLLECTING",
        "HOLD",
        "REJECT",
        "ELIGIBLE_FOR_ADOPTION_REVIEW",
    }
)

JEV_TYPESAFE_EVALUATION_GATE_KEYS = (
    "min_mature_candidates",
    "min_closed_disagreements",
    "max_skip_rate",
    "min_attempt_coverage",
    "max_error_rate",
    "max_late_rate",
    "max_interrupted_rate",
    "max_abstain_rate",
    "max_review_rate",
    "max_single_ticker_share",
    "max_single_signal_date_share",
    "max_budget_exposure_usd",
)
