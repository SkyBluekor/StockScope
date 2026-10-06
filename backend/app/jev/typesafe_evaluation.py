from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any

from .models import JEV_COMPARISON_POLICY, digest_json
from .typesafe_evaluation_models import (
    JEV_TYPESAFE_EVALUATION_GATE_KEYS,
    JEV_TYPESAFE_EVALUATION_POLICY_ID,
)
from .typesafe_models import JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2
from .typesafe_projection import project_typesafe_review


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _share(
    units: list[dict[str, Any]],
    field: str,
) -> tuple[float | None, str | None]:
    if not units:
        return None, None
    counts = Counter(str(unit.get(field) or "UNKNOWN") for unit in units)
    value, count = counts.most_common(1)[0]
    return count / len(units), value


def _latency_summary(units: list[dict[str, Any]]) -> dict[str, Any]:
    values = sorted(
        int(unit["latency_ms"])
        for unit in units
        if unit.get("latency_ms") is not None
    )
    if not values:
        return {"sample_count": 0, "mean_ms": None, "p95_ms": None, "max_ms": None}
    index = min(len(values) - 1, max(0, int(round(0.95 * len(values))) - 1))
    return {
        "sample_count": len(values),
        "mean_ms": mean(values),
        "p95_ms": values[index],
        "max_ms": values[-1],
    }


def typesafe_model_cohort_key(
    *,
    protocol_spec_hash: str,
    protocol_spec: dict[str, Any],
    review: dict[str, Any] | None,
) -> str:
    if review is None:
        return ""
    identity = {
        "protocol_spec_hash": protocol_spec_hash,
        "provider_id": review.get("provider_id"),
        "model_requested": review.get("model_requested"),
        "model_returned": review.get("model_returned"),
        "model_identity_status": review.get("model_identity_status"),
        "state_contract_version": review.get("state_contract_version"),
        "projector_version": review.get("projector_version"),
        "projector_hash": review.get("projector_hash"),
        "question_contract_version": review.get("question_contract_version"),
        "question_set_hash": review.get("question_set_hash"),
        "disposition_policy_version": review.get("disposition_policy_version"),
        "disposition_policy_hash": review.get("disposition_policy_hash"),
        "adapter_version": review.get("adapter_version"),
    }
    if (
        str(review.get("disposition_policy_version") or "")
        == JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2
    ):
        identity["threshold_strategy"] = protocol_spec.get("threshold_strategy")
        identity["threshold_entry"] = protocol_spec.get("threshold_entry")
        identity["threshold_evidence"] = protocol_spec.get("threshold_evidence")
    else:
        identity["threshold_low"] = protocol_spec.get("threshold_low")
        identity["threshold_high"] = protocol_spec.get("threshold_high")
    return digest_json(identity)


def build_typesafe_evaluation_unit(
    *,
    recruitment: dict[str, Any],
    sample: dict[str, Any],
    review: dict[str, Any] | None,
    outcome: dict[str, Any],
    protocol_spec_hash: str,
    protocol_spec: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    if review is None:
        operational_status = (
            "SKIPPED" if not bool(recruitment.get("callable")) else "NOT_CREATED"
        )
        disposition = None
        integrity_status = "NOT_APPLICABLE"
        failure_code = recruitment.get("skip_reason")
        latency_ms = None
        model_returned = None
    else:
        projection = project_typesafe_review(review, protocol_spec)
        operational_status = projection.operational_status
        disposition = projection.disposition
        integrity_status = projection.integrity_status
        failure_code = projection.failure_code
        latency_ms = review.get("latency_ms")
        model_returned = review.get("model_returned")

    comparison_eligible = (
        str(outcome.get("execution_status") or "") == "CLOSED"
        and outcome.get("net_return_pct") is not None
    )
    return {
        "recruitment_id": recruitment["id"],
        "capture_run_id": recruitment["capture_run_id"],
        "sample_index": int(recruitment["sample_index"]),
        "review_id": review.get("id") if review is not None else None,
        "market": str(sample.get("market") or ""),
        "ticker": str(sample.get("ticker") or ""),
        "name": str(sample.get("name") or ""),
        "signal_date": str(sample.get("signal_date") or ""),
        "strategy": sample.get("strategy"),
        "horizon": sample.get("horizon_intent"),
        "callable": 1 if bool(recruitment.get("callable")) else 0,
        "skip_reason": recruitment.get("skip_reason"),
        "operational_status": operational_status,
        "disposition": disposition,
        "failure_code": failure_code,
        "integrity_status": integrity_status,
        "provider_id": review.get("provider_id") if review is not None else None,
        "model_requested": (
            review.get("model_requested") if review is not None else None
        ),
        "model_returned": model_returned,
        "model_identity_status": (
            review.get("model_identity_status") if review is not None else None
        ),
        "model_cohort_key": typesafe_model_cohort_key(
            protocol_spec_hash=protocol_spec_hash,
            protocol_spec=protocol_spec,
            review=review,
        ),
        "latency_ms": latency_ms,
        "reserved_cost_usd": float(recruitment.get("reserved_cost_usd") or 0.0),
        "known_cost_usd": (
            float(recruitment["known_cost_usd"])
            if recruitment.get("known_cost_usd") is not None
            else None
        ),
        "cost_unknown": 1 if bool(recruitment.get("cost_unknown")) else 0,
        "maturity_status": str(outcome.get("maturity_status") or "NOT_CALCULATED"),
        "available_trading_days": int(outcome.get("available_trading_days") or 0),
        "evaluated_through": outcome.get("evaluated_through"),
        "return_5d": outcome.get("return_5d"),
        "return_10d": outcome.get("return_10d"),
        "return_20d": outcome.get("return_20d"),
        "mfe_pct": outcome.get("mfe_pct"),
        "mae_pct": outcome.get("mae_pct"),
        "execution_status": str(outcome.get("execution_status") or "NOT_EVALUATED"),
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
            "review_failure_code": failure_code,
        },
        "computed_at": computed_at,
    }


def build_typesafe_comparison_report(
    units: list[dict[str, Any]],
) -> dict[str, Any]:
    comparable = [
        unit
        for unit in units
        if str(unit.get("execution_status") or "") == "CLOSED"
        and unit.get("net_return_pct") is not None
    ]
    if not comparable:
        return {
            "comparison_policy": JEV_COMPARISON_POLICY,
            "comparable_closed_count": 0,
            "baseline_mean_return_pct": None,
            "shadow_mean_return_pct": None,
            "incremental_return_per_opportunity_pct": None,
            "avoided_loss_pct_sum": 0.0,
            "missed_profit_pct_sum": 0.0,
            "disagreement_count": 0,
            "disagreement_precision": None,
            "baseline_loss_rate": None,
            "shadow_loss_rate": None,
            "retained_candidate_loss_rate": None,
        }

    baseline_sum = 0.0
    shadow_sum = 0.0
    avoided_loss = 0.0
    missed_profit = 0.0
    disagreements = 0
    disagreement_losses = 0
    baseline_losses = 0
    shadow_losses = 0
    retained = 0
    retained_losses = 0

    for unit in comparable:
        value = float(unit["net_return_pct"])
        deferred = (
            unit.get("operational_status") == "VALID"
            and unit.get("disposition") == "REVIEW_REQUIRED"
        )
        baseline_sum += value
        if value < 0:
            baseline_losses += 1
        if deferred:
            disagreements += 1
            if value < 0:
                avoided_loss += -value
                disagreement_losses += 1
            elif value > 0:
                missed_profit += value
        else:
            retained += 1
            shadow_sum += value
            if value < 0:
                shadow_losses += 1
                retained_losses += 1

    count = len(comparable)
    return {
        "comparison_policy": JEV_COMPARISON_POLICY,
        "comparable_closed_count": count,
        "baseline_mean_return_pct": baseline_sum / count,
        "shadow_mean_return_pct": shadow_sum / count,
        "incremental_return_per_opportunity_pct": (
            shadow_sum - baseline_sum
        ) / count,
        "avoided_loss_pct_sum": avoided_loss,
        "missed_profit_pct_sum": missed_profit,
        "disagreement_count": disagreements,
        "disagreement_precision": (
            disagreement_losses / disagreements if disagreements else None
        ),
        "baseline_loss_rate": baseline_losses / count,
        "shadow_loss_rate": shadow_losses / count,
        "retained_candidate_loss_rate": (
            retained_losses / retained if retained else None
        ),
    }


def build_typesafe_evaluation_summary(
    *,
    gates: dict[str, Any],
    recruitments: list[dict[str, Any]],
    units: list[dict[str, Any]],
    comparison: dict[str, Any],
    evaluation_as_of: str,
    protocol_id: str,
    protocol_spec_hash: str,
    evaluation_policy_hash: str,
    exit_policy_token: str,
) -> dict[str, Any]:
    missing_gates = [
        key for key in JEV_TYPESAFE_EVALUATION_GATE_KEYS
        if gates.get(key) is None
    ]

    recruited = len(recruitments)
    callable_count = sum(1 for row in recruitments if bool(row.get("callable")))
    skipped_count = recruited - callable_count
    review_created = sum(1 for row in recruitments if row.get("review_id"))
    valid_units = [
        unit for unit in units if unit.get("operational_status") == "VALID"
    ]
    error_count = sum(
        1 for unit in units if unit.get("operational_status") == "ERROR"
    )
    late_count = sum(
        1 for unit in units if unit.get("operational_status") == "LATE"
    )
    interrupted_count = sum(
        1 for unit in units if unit.get("operational_status") == "INTERRUPTED"
    )
    abstain_count = sum(
        1 for unit in valid_units if unit.get("disposition") == "ABSTAIN"
    )
    review_required_count = sum(
        1 for unit in valid_units
        if unit.get("disposition") == "REVIEW_REQUIRED"
    )
    pass_through_count = sum(
        1 for unit in valid_units if unit.get("disposition") == "PASS_THROUGH"
    )
    mature = [
        unit for unit in units if unit.get("maturity_status") == "MATURE"
    ]
    comparable = [
        unit for unit in units if bool(unit.get("comparison_eligible"))
    ]

    known_cost = sum(
        float(row["known_cost_usd"])
        for row in recruitments
        if row.get("known_cost_usd") is not None
    )
    unknown_cost_count = sum(
        1
        for row in recruitments
        if bool(row.get("callable"))
        and bool(row.get("cost_unknown"))
    )
    reserved_unknown = sum(
        float(row.get("reserved_cost_usd") or 0.0)
        for row in recruitments
        if bool(row.get("callable"))
        and bool(row.get("cost_unknown"))
    )
    budget_exposure = known_cost + reserved_unknown

    rates = {
        "skip_rate": _rate(skipped_count, recruited),
        "attempt_coverage": _rate(review_created, callable_count),
        "error_rate": _rate(error_count, review_created),
        "late_rate": _rate(late_count, review_created),
        "interrupted_rate": _rate(interrupted_count, review_created),
        "valid_rate": _rate(len(valid_units), review_created),
        "abstain_rate": _rate(abstain_count, len(valid_units)),
        "review_required_rate": _rate(review_required_count, len(valid_units)),
        "pass_through_rate": _rate(pass_through_count, len(valid_units)),
    }

    cohorts = {
        str(unit.get("model_cohort_key") or "")
        for unit in valid_units
        if str(unit.get("model_cohort_key") or "")
    }
    integrity_reasons: list[str] = []
    if missing_gates:
        integrity_reasons.append("EVALUATION_POLICY_NOT_FROZEN")
    if len(cohorts) > 1:
        integrity_reasons.append("MODEL_COHORT_CHANGED")
    if any(
        unit.get("integrity_status") == "MISMATCH"
        for unit in units
    ):
        integrity_reasons.append("REVIEW_INTEGRITY_MISMATCH")
    if any(
        unit.get("operational_status") == "VALID"
        and unit.get("model_identity_status") != "MATCHED"
        for unit in units
    ):
        integrity_reasons.append("MODEL_IDENTITY_UNVERIFIED")

    sample_reasons: list[str] = []
    if not missing_gates:
        if len(mature) < int(gates["min_mature_candidates"]):
            sample_reasons.append("MIN_MATURE_NOT_REACHED")
        if int(comparison.get("disagreement_count") or 0) < int(
            gates["min_closed_disagreements"]
        ):
            sample_reasons.append("MIN_CLOSED_DISAGREEMENTS_NOT_REACHED")

    operational_reasons: list[str] = []
    if not missing_gates:
        checks = (
            ("skip_rate", "max_skip_rate", "SKIP_RATE_EXCEEDED", "max"),
            ("attempt_coverage", "min_attempt_coverage", "ATTEMPT_COVERAGE_LOW", "min"),
            ("error_rate", "max_error_rate", "ERROR_RATE_EXCEEDED", "max"),
            ("late_rate", "max_late_rate", "LATE_RATE_EXCEEDED", "max"),
            (
                "interrupted_rate",
                "max_interrupted_rate",
                "INTERRUPTED_RATE_EXCEEDED",
                "max",
            ),
            ("abstain_rate", "max_abstain_rate", "ABSTAIN_RATE_EXCEEDED", "max"),
            (
                "review_required_rate",
                "max_review_rate",
                "REVIEW_RATE_EXCEEDED",
                "max",
            ),
        )
        for metric, gate_key, code, mode in checks:
            value = rates[metric]
            if value is None:
                operational_reasons.append(metric.upper() + "_UNAVAILABLE")
            elif mode == "max" and value > float(gates[gate_key]):
                operational_reasons.append(code)
            elif mode == "min" and value < float(gates[gate_key]):
                operational_reasons.append(code)

        ticker_share, _ = _share(comparable, "ticker")
        date_share, _ = _share(comparable, "signal_date")
        if ticker_share is not None and ticker_share > float(
            gates["max_single_ticker_share"]
        ):
            operational_reasons.append("TICKER_CONCENTRATION_EXCEEDED")
        if date_share is not None and date_share > float(
            gates["max_single_signal_date_share"]
        ):
            operational_reasons.append("SIGNAL_DATE_CONCENTRATION_EXCEEDED")
        if budget_exposure > float(gates["max_budget_exposure_usd"]):
            operational_reasons.append("API_BUDGET_EXPOSURE_EXCEEDED")
        if unknown_cost_count > 0:
            operational_reasons.append("API_COST_INCOMPLETE")

    performance_reasons: list[str] = []
    if not sample_reasons and not missing_gates:
        delta = comparison.get("incremental_return_per_opportunity_pct")
        if delta is None:
            performance_reasons.append("DELTA_UNAVAILABLE")
        elif float(delta) <= 0.0:
            performance_reasons.append("DELTA_NOT_POSITIVE")
        net = (
            float(comparison.get("avoided_loss_pct_sum") or 0.0)
            - float(comparison.get("missed_profit_pct_sum") or 0.0)
        )
        if net <= 0.0:
            performance_reasons.append("AVOIDED_MINUS_MISSED_NOT_POSITIVE")
        retained_loss = comparison.get("retained_candidate_loss_rate")
        baseline_loss = comparison.get("baseline_loss_rate")
        if retained_loss is None or baseline_loss is None:
            performance_reasons.append("LOSS_RATE_COMPARISON_UNAVAILABLE")
        elif float(retained_loss) > float(baseline_loss):
            performance_reasons.append("RETAINED_LOSS_RATE_WORSENED")

    if integrity_reasons:
        state = "HOLD"
        reasons = integrity_reasons
    elif sample_reasons:
        state = "COLLECTING"
        reasons = sample_reasons
    elif operational_reasons:
        state = "HOLD"
        reasons = operational_reasons
    elif performance_reasons:
        unavailable = {
            "DELTA_UNAVAILABLE",
            "LOSS_RATE_COMPARISON_UNAVAILABLE",
        }
        state = (
            "HOLD"
            if any(reason in unavailable for reason in performance_reasons)
            else "REJECT"
        )
        reasons = performance_reasons
    else:
        state = "ELIGIBLE_FOR_ADOPTION_REVIEW"
        reasons = []

    ticker_share, top_ticker = _share(comparable, "ticker")
    date_share, top_signal_date = _share(comparable, "signal_date")
    return {
        "evaluation_policy_id": JEV_TYPESAFE_EVALUATION_POLICY_ID,
        "evaluation_policy_hash": evaluation_policy_hash,
        "trial_protocol_id": protocol_id,
        "trial_spec_hash": protocol_spec_hash,
        "comparison_policy": JEV_COMPARISON_POLICY,
        "evaluation_as_of": evaluation_as_of,
        "exit_policy_token": exit_policy_token,
        "funnel": {
            "recruited": recruited,
            "callable": callable_count,
            "skipped": skipped_count,
            "review_created": review_created,
            "valid": len(valid_units),
            "error": error_count,
            "late": late_count,
            "interrupted": interrupted_count,
            "pass_through": pass_through_count,
            "review_required": review_required_count,
            "abstain": abstain_count,
            "outcome_joined": len(units),
            "mature": len(mature),
            "comparable_closed": len(comparable),
        },
        "rates": rates,
        "cost": {
            "known_cost_usd": known_cost,
            "unknown_cost_count": unknown_cost_count,
            "reserved_unknown_cost_usd": reserved_unknown,
            "budget_exposure_usd": budget_exposure,
        },
        "comparison": comparison,
        "identity": {
            "model_cohort_count": len(cohorts),
            "model_cohort_keys": sorted(cohorts),
        },
        "latency": _latency_summary(units),
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
            "sample": {"pass": not sample_reasons, "reasons": sample_reasons},
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
        "evaluation_state_reasons": reasons,
        "automatic_adoption_allowed": False,
        "notes": [
            "Recruitment ledger가 cohort denominator의 source of truth입니다.",
            "ERROR/LATE/INTERRUPTED/SKIPPED/ABSTAIN은 서로 다른 의미입니다.",
            "VALID + REVIEW_REQUIRED만 virtual defer로 비교합니다.",
            "CENSORED는 실현수익 0%로 변환하지 않습니다.",
            "Unknown provider cost는 0 USD로 간주하지 않습니다.",
        ],
    }
