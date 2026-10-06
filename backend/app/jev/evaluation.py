from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from app.backtest.production_exit_policy import production_policy_cache_token
from app.prospective.evaluation import ProspectiveEvaluator

from .catalog import JevCatalog
from .comparison import build_comparison_report
from .evaluation_catalog import (
    JevEvaluationCatalog,
    JevEvaluationCatalogError,
)
from .evaluation_models import JEV_EVALUATION_POLICY_ID
from .evaluation_policy import (
    JevEvaluationPolicyError,
    load_evaluation_policy,
)
from .models import digest_json
from .trial import TRIAL_PROTOCOL_ID, JevTrialError, load_trial_artifact


class JevReviewerEvaluationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _first_reviews(
    reviews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered = sorted(
        reviews,
        key=lambda row: (
            str(row.get("requested_at") or ""),
            int(row.get("attempt") or 1),
            str(row.get("id") or ""),
        ),
    )
    seen: set[tuple[str, int]] = set()
    result: list[dict[str, Any]] = []
    for row in ordered:
        key = (
            str(row.get("capture_run_id") or ""),
            int(row.get("sample_index") or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _model_cohort_key(
    review: dict[str, Any],
    protocol_spec_hash: str,
) -> tuple[str, str]:
    usage = review.get("usage")
    served_model = ""
    if isinstance(usage, dict):
        served_model = str(usage.get("served_model") or "").strip()
    effective_served = served_model or str(review.get("model_id") or "")
    identity = {
        "protocol_spec_hash": protocol_spec_hash,
        "provider_id": review.get("provider_id"),
        "model_id": review.get("model_id"),
        "served_model": effective_served,
        "prompt_hash": review.get("prompt_hash"),
        "adapter_version": review.get("adapter_version"),
    }
    return digest_json(identity), effective_served


def _share(
    units: list[dict[str, Any]],
    field: str,
) -> tuple[float, str | None]:
    if not units:
        return 0.0, None
    counts = Counter(str(unit.get(field) or "UNKNOWN") for unit in units)
    value, count = counts.most_common(1)[0]
    return count / len(units), value


def _latency_summary(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    values = sorted(
        int(row["latency_ms"])
        for row in reviews
        if row.get("latency_ms") is not None
    )
    if not values:
        return {
            "sample_count": 0,
            "mean_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }
    index = min(len(values) - 1, max(0, int(round(0.95 * len(values))) - 1))
    return {
        "sample_count": len(values),
        "mean_ms": mean(values),
        "p95_ms": values[index],
        "max_ms": values[-1],
    }


def build_evaluation_summary(
    *,
    policy: dict[str, Any],
    trial_spec: dict[str, Any],
    reviews: list[dict[str, Any]],
    units: list[dict[str, Any]],
    comparison: dict[str, Any],
    evaluation_as_of: str,
    exit_policy_token: str,
) -> dict[str, Any]:
    gates = dict(policy["spec"]["gates"])
    recruited = [row for row in reviews if row.get("status") != "SKIPPED"]
    valid = [row for row in recruited if row.get("status") == "VALID"]
    on_time = valid
    non_abstain = [
        row for row in valid
        if row.get("decision") != "ABSTAIN"
    ]
    mature = [
        unit for unit in units
        if unit.get("maturity_status") == "MATURE"
    ]
    comparable = [
        unit for unit in units
        if bool(unit.get("comparison_eligible"))
    ]

    recruited_count = len(recruited)
    denominator = recruited_count if recruited_count > 0 else 1
    error_rate = sum(
        1 for row in recruited if row.get("status") == "ERROR"
    ) / denominator
    late_rate = sum(
        1 for row in recruited if row.get("status") == "LATE"
    ) / denominator
    abstain_rate = sum(
        1
        for row in recruited
        if row.get("status") == "VALID"
        and row.get("decision") == "ABSTAIN"
    ) / denominator
    review_rate = sum(
        1
        for row in recruited
        if row.get("status") == "VALID"
        and row.get("decision") == "REVIEW_REQUIRED"
    ) / denominator

    total_cost = sum(
        float(row.get("cost_usd") or 0.0)
        for row in recruited
    )
    cost_missing_count = sum(
        1
        for row in recruited
        if str(row.get("provider_id") or "").upper() != "FAKE"
        and row.get("status") in {"VALID", "LATE"}
        and row.get("cost_usd") is None
    )

    valid_cohorts = {
        str(unit.get("model_cohort_key") or "")
        for unit in units
        if unit.get("review_status") == "VALID"
        and str(unit.get("model_cohort_key") or "")
    }
    ticker_share, top_ticker = _share(comparable, "ticker")
    date_share, top_signal_date = _share(comparable, "signal_date")

    disagreement_count = int(comparison.get("disagreement_count") or 0)
    mature_count = len(mature)
    comparable_count = len(comparable)
    net_avoided_minus_missed = (
        float(comparison.get("avoided_loss_pct_sum") or 0.0)
        - float(comparison.get("missed_profit_pct_sum") or 0.0)
    )

    integrity_reasons: list[str] = []
    if len(valid_cohorts) > 1:
        integrity_reasons.append("MODEL_COHORT_CHANGED")

    sample_reasons: list[str] = []
    if mature_count < int(gates["min_mature_candidates"]):
        sample_reasons.append("MIN_MATURE_NOT_REACHED")
    if disagreement_count < int(gates["min_closed_disagreements"]):
        sample_reasons.append("MIN_CLOSED_DISAGREEMENTS_NOT_REACHED")

    operational_reasons: list[str] = []
    if error_rate > float(gates["max_error_rate"]):
        operational_reasons.append("ERROR_RATE_EXCEEDED")
    if abstain_rate > float(gates["max_abstain_rate"]):
        operational_reasons.append("ABSTAIN_RATE_EXCEEDED")
    if review_rate > float(gates["max_review_rate"]):
        operational_reasons.append("REVIEW_RATE_EXCEEDED")
    if ticker_share > float(gates["max_single_ticker_share"]):
        operational_reasons.append("TICKER_CONCENTRATION_EXCEEDED")
    if date_share > float(gates["max_single_signal_date_share"]):
        operational_reasons.append("SIGNAL_DATE_CONCENTRATION_EXCEEDED")
    if total_cost > float(gates["max_api_cost_usd"]):
        operational_reasons.append("API_BUDGET_EXCEEDED")
    if cost_missing_count > 0:
        operational_reasons.append("API_COST_INCOMPLETE")

    performance_reasons: list[str] = []
    delta = comparison.get("incremental_return_per_opportunity_pct")
    if delta is None:
        performance_reasons.append("DELTA_UNAVAILABLE")
    elif float(delta) <= 0.0:
        performance_reasons.append("DELTA_NOT_POSITIVE")
    if net_avoided_minus_missed <= 0.0:
        performance_reasons.append("AVOIDED_MINUS_MISSED_NOT_POSITIVE")
    retained_loss = comparison.get("retained_candidate_loss_rate")
    baseline_loss = comparison.get("baseline_loss_rate")
    if retained_loss is None or baseline_loss is None:
        performance_reasons.append("LOSS_RATE_COMPARISON_UNAVAILABLE")
    elif float(retained_loss) > float(baseline_loss):
        performance_reasons.append("RETAINED_LOSS_RATE_WORSENED")

    if integrity_reasons:
        state = "HOLD"
        state_reasons = integrity_reasons
    elif sample_reasons:
        state = "COLLECTING"
        state_reasons = sample_reasons
    elif operational_reasons:
        state = "HOLD"
        state_reasons = operational_reasons
    elif performance_reasons:
        if any(
            reason in {
                "DELTA_UNAVAILABLE",
                "LOSS_RATE_COMPARISON_UNAVAILABLE",
            }
            for reason in performance_reasons
        ):
            state = "HOLD"
        else:
            state = "REJECT"
        state_reasons = performance_reasons
    else:
        state = "ELIGIBLE_FOR_ADOPTION_REVIEW"
        state_reasons = []

    return {
        "evaluation_policy_id": JEV_EVALUATION_POLICY_ID,
        "evaluation_policy_hash": policy["computed_policy_hash"],
        "trial_protocol_id": policy["spec"]["trial_protocol_id"],
        "trial_spec_hash": policy["spec"]["trial_spec_hash"],
        "comparison_policy": policy["spec"]["comparison_policy"],
        "evaluation_as_of": evaluation_as_of,
        "exit_policy_token": exit_policy_token,
        "funnel": {
            "captured": len(reviews),
            "eligible": recruited_count,
            "recruited": recruited_count,
            "provider_stage": recruited_count,
            "valid": len(valid),
            "on_time": len(on_time),
            "non_abstain": len(non_abstain),
            "outcome_joined": len(units),
            "mature": mature_count,
            "closed": comparable_count,
        },
        "maturity": {
            "mature_count": mature_count,
            "immature_count": sum(
                1
                for unit in units
                if unit.get("maturity_status") in {
                    "IMMATURE",
                    "NOT_CALCULATED",
                }
            ),
            "comparable_closed_count": comparable_count,
        },
        "comparison": {
            **comparison,
            "avoided_minus_missed_pct_sum": net_avoided_minus_missed,
        },
        "operation": {
            "review_rate": review_rate,
            "abstain_rate": abstain_rate,
            "error_rate": error_rate,
            "late_rate": late_rate,
            "api_cost_usd": total_cost,
            "api_cost_missing_count": cost_missing_count,
            "latency": _latency_summary(recruited),
        },
        "identity": {
            "model_cohort_count": len(valid_cohorts),
            "model_cohort_keys": sorted(valid_cohorts),
        },
        "concentration": {
            "top_ticker": top_ticker,
            "top_ticker_share": ticker_share,
            "top_signal_date": top_signal_date,
            "top_signal_date_share": date_share,
        },
        "gate_results": {
            "integrity": {
                "pass": not integrity_reasons,
                "reasons": integrity_reasons,
            },
            "sample": {
                "pass": not sample_reasons,
                "reasons": sample_reasons,
            },
            "operational": {
                "pass": not operational_reasons,
                "reasons": operational_reasons,
            },
            "performance": {
                "pass": not performance_reasons,
                "reasons": performance_reasons,
            },
        },
        "evaluation_state": state,
        "evaluation_state_reasons": state_reasons,
        "automatic_adoption_allowed": False,
        "notes": [
            "CENSORED는 실현수익 0%로 변환하지 않습니다.",
            "VALID REVIEW_REQUIRED만 virtual skip으로 비교합니다.",
            "그 외 review 결과는 baseline을 유지합니다.",
            "ELIGIBLE_FOR_ADOPTION_REVIEW는 자동 채택을 의미하지 않습니다.",
        ],
        "trial_cost_assumption": {
            "round_trip_cost_pct": trial_spec.get("round_trip_cost_pct"),
            "fee_pct": trial_spec.get("fee_pct"),
            "tax_pct": trial_spec.get("tax_pct"),
            "slippage_pct": trial_spec.get("slippage_pct"),
        },
    }


class JevReviewerEvaluationService:
    def __init__(
        self,
        simulation_db: Path,
        market_store_db: Path,
        *,
        outcome_evaluator: Any | None = None,
    ) -> None:
        self.shadow = JevCatalog(simulation_db)
        self.catalog = JevEvaluationCatalog(simulation_db)
        self.outcomes = outcome_evaluator or ProspectiveEvaluator(market_store_db)

    def _runtime_protocol(self) -> dict[str, Any]:
        protocol = self.shadow.get_protocol_by_client_request_id(
            TRIAL_PROTOCOL_ID
        )
        if protocol is None:
            raise JevReviewerEvaluationError(
                "JEV_TRIAL_NOT_CONFIGURED",
                "Frozen JEV trial protocol을 runtime DB에 먼저 configure해야 합니다.",
            )
        return protocol

    def create_run(
        self,
        *,
        client_request_id: str,
        evaluation_as_of: str | None = None,
    ) -> dict[str, Any]:
        try:
            trial = load_trial_artifact()
            policy = load_evaluation_policy()
        except (JevTrialError, JevEvaluationPolicyError) as exc:
            raise JevReviewerEvaluationError(
                getattr(exc, "code", "JEV_EVALUATION_CONFIG_ERROR"),
                str(exc),
            ) from exc

        protocol = self._runtime_protocol()
        if protocol["spec_hash"] != trial["computed_spec_hash"]:
            raise JevReviewerEvaluationError(
                "JEV_TRIAL_RUNTIME_HASH_MISMATCH",
                "runtime trial protocol과 frozen artifact가 일치하지 않습니다.",
            )
        if (
            policy["spec"]["trial_spec_hash"]
            != trial["computed_spec_hash"]
        ):
            raise JevReviewerEvaluationError(
                "JEV_EVALUATION_TRIAL_HASH_MISMATCH",
                "evaluation policy와 frozen trial hash가 일치하지 않습니다.",
            )

        as_of = evaluation_as_of or datetime.now(timezone.utc).date().isoformat()
        return self.catalog.create_run(
            client_request_id=client_request_id,
            protocol_id=protocol["id"],
            protocol_spec_hash=protocol["spec_hash"],
            evaluation_policy_id=policy["policy_id"],
            evaluation_policy_hash=policy["computed_policy_hash"],
            evaluation_as_of=as_of,
            exit_policy_token=production_policy_cache_token(),
        )

    def _sample_map(
        self,
        reviews: list[dict[str, Any]],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        result: dict[tuple[str, int], dict[str, Any]] = {}
        capture_ids = sorted(
            {str(row["capture_run_id"]) for row in reviews}
        )
        for capture_id in capture_ids:
            for sample in self.shadow.load_capture_candidates(capture_id):
                result[
                    (
                        str(sample["capture_run_id"]),
                        int(sample["sample_index"]),
                    )
                ] = sample
        return result

    def execute_run(self, run_id: str) -> dict[str, Any]:
        run = self.catalog.get_run(run_id)
        if run is None:
            raise JevReviewerEvaluationError(
                "JEV_EVALUATION_RUN_NOT_FOUND",
                "JEV evaluation run을 찾을 수 없습니다.",
            )
        if run["status"] == "COMPLETED":
            return self.catalog.detail(run_id)

        protocol = self._runtime_protocol()
        policy = load_evaluation_policy()
        trial = load_trial_artifact()

        if run["protocol_id"] != protocol["id"]:
            raise JevReviewerEvaluationError(
                "JEV_EVALUATION_PROTOCOL_MISMATCH",
                "evaluation run의 trial protocol identity가 다릅니다.",
            )
        if run["protocol_spec_hash"] != protocol["spec_hash"]:
            raise JevReviewerEvaluationError(
                "JEV_EVALUATION_PROTOCOL_HASH_MISMATCH",
                "evaluation run의 trial protocol hash가 다릅니다.",
            )
        if run["evaluation_policy_hash"] != policy["computed_policy_hash"]:
            raise JevReviewerEvaluationError(
                "JEV_EVALUATION_POLICY_HASH_MISMATCH",
                "evaluation run의 frozen policy hash가 다릅니다.",
            )
        current_exit_token = production_policy_cache_token()
        if run["exit_policy_token"] != current_exit_token:
            raise JevReviewerEvaluationError(
                "JEV_EVALUATION_EXIT_POLICY_CHANGED",
                "evaluation run 생성 후 production exit policy가 변경되었습니다.",
            )

        self.catalog.begin_run(run_id)
        try:
            all_reviews = _first_reviews(
                self.shadow.list_reviews(protocol_id=protocol["id"])
            )
            recruited_reviews = [
                row for row in all_reviews
                if row.get("status") != "SKIPPED"
            ]
            sample_map = self._sample_map(recruited_reviews)
            trial_spec = dict(trial["spec"])
            outcome_spec = {
                "observation_windows": list(
                    policy["spec"]["observation_windows"]
                ),
                "max_holding_days": int(
                    policy["spec"]["max_holding_days"]
                ),
                "round_trip_cost_pct": float(
                    trial_spec.get("round_trip_cost_pct") or 0.0
                ),
                "fee_pct": float(trial_spec.get("fee_pct") or 0.0),
                "tax_pct": float(trial_spec.get("tax_pct") or 0.0),
                "slippage_pct": float(
                    trial_spec.get("slippage_pct") or 0.0
                ),
                "execution_mode": "PRODUCTION_POLICY",
                "exit_policy_token": run["exit_policy_token"],
            }

            units: list[dict[str, Any]] = []
            outcome_rows: list[dict[str, Any]] = []
            selected_reviews: list[dict[str, Any]] = []
            for review in recruited_reviews:
                key = (
                    str(review["capture_run_id"]),
                    int(review["sample_index"]),
                )
                sample = sample_map.get(key)
                if sample is None:
                    raise JevReviewerEvaluationError(
                        "JEV_EVALUATION_SAMPLE_MISSING",
                        "JEV review에 대응하는 canonical sample이 없습니다.",
                    )
                outcome = self.outcomes.evaluate_sample(
                    sample=sample,
                    spec=outcome_spec,
                )
                cohort_key, served_model = _model_cohort_key(
                    review,
                    protocol["spec_hash"],
                )
                comparison_eligible = (
                    outcome.get("execution_status") == "CLOSED"
                    and outcome.get("net_return_pct") is not None
                )
                input_payload = review.get("input") or {}
                baseline_identity = (
                    input_payload.get("baseline_identity")
                    if isinstance(input_payload, dict)
                    else {}
                )
                unit = {
                    "capture_run_id": key[0],
                    "sample_index": key[1],
                    "review_id": review["id"],
                    "market": str(sample.get("market") or ""),
                    "ticker": str(sample.get("ticker") or ""),
                    "name": str(sample.get("name") or ""),
                    "signal_date": str(sample.get("signal_date") or ""),
                    "strategy": sample.get("strategy"),
                    "horizon": (
                        baseline_identity.get("horizon_intent")
                        if isinstance(baseline_identity, dict)
                        else None
                    ),
                    "review_status": str(review.get("status") or ""),
                    "review_decision": review.get("decision"),
                    "provider_id": str(review.get("provider_id") or ""),
                    "model_id": str(review.get("model_id") or ""),
                    "served_model": served_model,
                    "model_cohort_key": cohort_key,
                    "maturity_status": str(
                        outcome.get("maturity_status") or "NOT_CALCULATED"
                    ),
                    "available_trading_days": int(
                        outcome.get("available_trading_days") or 0
                    ),
                    "evaluated_through": outcome.get("evaluated_through"),
                    "return_5d": outcome.get("return_5d"),
                    "return_10d": outcome.get("return_10d"),
                    "return_20d": outcome.get("return_20d"),
                    "mfe_pct": outcome.get("mfe_pct"),
                    "mae_pct": outcome.get("mae_pct"),
                    "execution_status": str(
                        outcome.get("execution_status") or "NOT_EVALUATED"
                    ),
                    "execution_reason": outcome.get("execution_reason"),
                    "entry_date": outcome.get("entry_date"),
                    "entry_price": outcome.get("entry_price"),
                    "exit_date": outcome.get("exit_date"),
                    "exit_price": outcome.get("exit_price"),
                    "exit_reason": outcome.get("exit_reason"),
                    "holding_days": outcome.get("holding_days"),
                    "gross_return_pct": outcome.get("gross_return_pct"),
                    "net_return_pct": outcome.get("net_return_pct"),
                    "mark_return_pct": outcome.get("mark_return_pct"),
                    "comparison_eligible": 1 if comparison_eligible else 0,
                    "details": {
                        "outcome_details": outcome.get("details") or {},
                        "review_failure_code": review.get("failure_code"),
                        "review_cost_usd": review.get("cost_usd"),
                    },
                    "computed_at": datetime.now(timezone.utc).isoformat(),
                }
                units.append(unit)
                outcome_rows.append(
                    {
                        "capture_run_id": key[0],
                        "sample_index": key[1],
                        "execution_status": unit["execution_status"],
                        "net_return_pct": unit["net_return_pct"],
                    }
                )
                selected_reviews.append(review)

            comparison = build_comparison_report(
                selected_reviews,
                outcome_rows,
            )
            summary = build_evaluation_summary(
                policy=policy,
                trial_spec=trial_spec,
                reviews=all_reviews,
                units=units,
                comparison=comparison,
                evaluation_as_of=run["evaluation_as_of"],
                exit_policy_token=run["exit_policy_token"],
            )
            source_set_hash = digest_json(
                {
                    "protocol_spec_hash": protocol["spec_hash"],
                    "evaluation_policy_hash": policy["computed_policy_hash"],
                    "exit_policy_token": run["exit_policy_token"],
                    "units": [
                        {
                            "capture_run_id": unit["capture_run_id"],
                            "sample_index": unit["sample_index"],
                            "review_id": unit["review_id"],
                            "review_status": unit["review_status"],
                            "review_decision": unit["review_decision"],
                            "model_cohort_key": unit["model_cohort_key"],
                            "maturity_status": unit["maturity_status"],
                            "execution_status": unit["execution_status"],
                            "net_return_pct": unit["net_return_pct"],
                            "evaluated_through": unit["evaluated_through"],
                        }
                        for unit in units
                    ],
                }
            )
            completed = self.catalog.complete_run(
                run_id=run_id,
                units=units,
                report_summary=summary,
                source_set_hash=source_set_hash,
                recruited_count=len(recruited_reviews),
                mature_count=int(summary["maturity"]["mature_count"]),
                comparable_closed_count=int(
                    summary["maturity"]["comparable_closed_count"]
                ),
                disagreement_count=int(
                    summary["comparison"]["disagreement_count"]
                ),
            )
            return {
                "run": completed,
                "report": self.catalog.get_report(completed),
                "units": self.catalog.list_units(run_id),
            }
        except Exception as exc:
            code = getattr(exc, "code", "JEV_EVALUATION_FAILED")
            message = getattr(exc, "message", str(exc))
            self.catalog.mark_failed(
                run_id,
                code=str(code),
                message=str(message),
            )
            if isinstance(exc, JevReviewerEvaluationError):
                raise
            if isinstance(exc, JevEvaluationCatalogError):
                raise
            raise JevReviewerEvaluationError(
                str(code),
                str(message),
            ) from exc

    def detail(self, run_id: str) -> dict[str, Any]:
        return self.catalog.detail(run_id)

    def latest(self) -> dict[str, Any] | None:
        return self.catalog.latest_completed()
