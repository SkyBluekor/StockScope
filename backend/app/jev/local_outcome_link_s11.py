"""S11: frozen local-shadow observations joined to existing Prospective outcomes.

Read-only *descriptive* study, never a strategy promotion, causal claim,
provider request, market data download, or runtime write. Exact frozen
capture/sample/date/ticker/strategy identity is required, and incomplete,
purged, immature or non-CLOSED observations never become 0% returns.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
import sqlite3
from typing import Any

from .decision_reviewer_offline import DecisionReviewContractError
from .local_history_review import review_candidate
from .local_shadow_cohort_s10 import build_cohort_report, PROVISIONAL, NO_ADVERSE
from .scanner_shadow_s7 import load_frozen_candidates


VERSION = "JEV_LOCAL_SHADOW_OUTCOME_LINK_AUDIT_V1"
EVALUATION_STATUS = "DESCRIPTIVE_ONLY_NOT_CAUSAL"
_ELIGIBLE_SPLITS = frozenset({"DEVELOPMENT", "HOLDOUT"})


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None and result.utcoffset() is not None else None


def _day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        obj = date.fromisoformat(value)
    except ValueError:
        return None
    return obj if obj.isoformat() == value else None


def _return(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        r = float(value)
    except (OverflowError, ValueError):
        return None
    return r if isfinite(r) else None


def load_evaluation_readonly(simulation_db: Path, *, run_id: str, capture_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Do not instantiate ProspectiveCatalog; it opens a writable connection."""
    path = Path(simulation_db)
    if not path.is_file():
        raise DecisionReviewContractError("S11_SOURCE_DB_NOT_FOUND")
    if not run_id or not capture_id:
        raise DecisionReviewContractError("S11_EVALUATION_ID_REQUIRED")
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            run = conn.execute(
                "SELECT id,status,protocol_id,evaluation_version,completed_at "
                "FROM prospective_evaluation_run WHERE id=?", (run_id,),
            ).fetchone()
            if run is None:
                raise DecisionReviewContractError("S11_RUN_NOT_FOUND")
            units = conn.execute(
                "SELECT evaluation_run_id,capture_run_id,sample_index,signal_date,"
                "market,ticker,strategy,split,maturity_status,execution_status,"
                "net_return_pct,exit_date,evaluated_through,computed_at "
                "FROM prospective_evaluation_unit "
                "WHERE evaluation_run_id=? AND capture_run_id=? "
                "ORDER BY sample_index", (run_id, capture_id),
            ).fetchall()
    except sqlite3.Error as exc:
        raise DecisionReviewContractError("S11_READ_ONLY_SCHEMA_UNAVAILABLE") from exc
    return dict(run), [dict(row) for row in units]


def _source_guard(run: dict[str, Any], *, run_id: str) -> datetime:
    if (
        not isinstance(run, dict) or run.get("id") != run_id
        or run.get("status") != "COMPLETED"
        or not isinstance(run.get("protocol_id"), str)
        or not run["protocol_id"]
    ):
        raise DecisionReviewContractError("S11_EVALUATION_RUN_NOT_COMPLETE")
    completed = _time(run.get("completed_at"))
    if completed is None:
        raise DecisionReviewContractError("S11_EVALUATION_COMPLETION_TIME_UNVERIFIED")
    return completed


def _result_reason(
    capture: dict[str, Any], sample: dict[str, Any], unit: dict[str, Any],
    *, evaluation_run_id: str, completed: datetime,
) -> str:
    if (
        unit.get("evaluation_run_id") != evaluation_run_id
        or unit.get("capture_run_id") != capture.get("id")
        or type(unit.get("sample_index")) is not int
        or unit.get("sample_index") != sample.get("sample_index")
        or unit.get("signal_date") != sample.get("signal_date")
        or unit.get("market") != sample.get("market")
        or unit.get("ticker") != sample.get("ticker")
        or unit.get("strategy") != sample.get("strategy")
    ):
        return "SOURCE_IDENTITY_MISMATCH"

    capture_completed = _time(capture.get("completed_at"))
    unit_computed = _time(unit.get("computed_at"))
    if (
        capture_completed is None or unit_computed is None
        or unit_computed < capture_completed
        or unit_computed > completed
    ):
        return "OBSERVATION_TIME_UNVERIFIED"

    split = unit.get("split")
    if split not in _ELIGIBLE_SPLITS:
        return "PURGED_OR_EXCLUDED" if split in {"PURGED", "EXCLUDED"} else "SPLIT_NOT_VERIFIED"
    if unit.get("maturity_status") != "MATURE":
        return "NOT_MATURE"
    if unit.get("execution_status") != "CLOSED":
        return "NOT_CLOSED"
    signal_day = _day(sample.get("signal_date"))
    exit_day = _day(unit.get("exit_date"))
    through_day = _day(unit.get("evaluated_through"))
    if (
        signal_day is None or exit_day is None or through_day is None
        or not signal_day < exit_day <= through_day
    ):
        return "EXECUTION_TIME_UNVERIFIED"
    if _return(unit.get("net_return_pct")) is None:
        return "NET_RETURN_UNVERIFIED"
    return "CLOSED_COMPARABLE"


def _new_split() -> dict[str, Any]:
    return {
        "matched_closed": 0,
        "flagged_closed": 0,
        "flagged_losses": 0,
        "flagged_non_losses": 0,
        "unflagged_closed": 0,
        "unflagged_losses": 0,
        "unflagged_non_losses": 0,
        "flagged_return_sum_pct": 0.0,
        "unflagged_return_sum_pct": 0.0,
    }


def _finish_split(values: dict[str, Any]) -> dict[str, Any]:
    flagged = values["flagged_closed"]
    unflagged = values["unflagged_closed"]
    return {
        "closed_comparable": values["matched_closed"],
        "flagged_closed": flagged,
        "flagged_losses": values["flagged_losses"],
        "flagged_non_losses": values["flagged_non_losses"],
        "unflagged_closed": unflagged,
        "unflagged_losses": values["unflagged_losses"],
        "unflagged_non_losses": values["unflagged_non_losses"],
        "mean_flagged_net_return_pct": (
            round(values["flagged_return_sum_pct"] / flagged, 4) if flagged else None
        ),
        "mean_unflagged_net_return_pct": (
            round(values["unflagged_return_sum_pct"] / unflagged, 4) if unflagged else None
        ),
    }


def build_outcome_link_report(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]], *,
    requested_capture_id: str, limit: int,
    run_id: str, run: dict[str, Any], units: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure audit of cohort coverage and *observed* historical returns only."""
    completed = _source_guard(run, run_id=run_id)
    cohort = build_cohort_report(
        pairs, requested_capture_id=requested_capture_id, limit=limit,
    )
    if cohort["scope"]["completeness"] != "COMPLETE_WITHIN_CAPTURE":
        raise DecisionReviewContractError("S11_FULL_CAPTURE_DENOMINATOR_REQUIRED")

    canonical = cohort["canonical_capture_id"]
    indexed: dict[int, dict[str, Any]] = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise DecisionReviewContractError("S11_UNIT_INVALID")
        idx = unit.get("sample_index")
        if type(idx) is not int or idx < 0 or idx in indexed:
            raise DecisionReviewContractError("S11_UNIT_INDEX_DUPLICATED_OR_INVALID")
        if unit.get("capture_run_id") != canonical:
            raise DecisionReviewContractError("S11_MIXED_CAPTURE_UNITS")
        indexed[idx] = unit

    reasons: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    splits: dict[str, dict[str, Any]] = {
        "DEVELOPMENT": _new_split(), "HOLDOUT": _new_split(),
    }
    matched: set[int] = set()
    observations = 0
    for capture, sample in pairs:
        if sample.get("action") != "ENTRY_CANDIDATE":
            continue
        observations += 1
        observation = review_candidate(capture, sample)
        status = str(observation.get("status"))
        status_counts[status] += 1
        idx = sample["sample_index"]
        unit = indexed.get(idx)
        if unit is None:
            reasons["EVALUATION_UNIT_MISSING"] += 1
            continue
        matched.add(idx)
        why = _result_reason(
            capture, sample, unit, evaluation_run_id=run_id, completed=completed,
        )
        if why != "CLOSED_COMPARABLE":
            reasons[why] += 1
            continue
        # Fail-closed: only the two genuinely inspected S9 groups are compared.
        if status not in {PROVISIONAL, NO_ADVERSE}:
            reasons["REVIEW_NOT_COMPARABLE"] += 1
            continue
        split = unit["split"]
        v = _return(unit["net_return_pct"])
        assert v is not None  # _result_reason has just verified finite numeric.
        slot = splits[split]
        slot["matched_closed"] += 1
        flagged = status == PROVISIONAL
        if flagged:
            slot["flagged_closed"] += 1
            slot["flagged_losses" if v < 0 else "flagged_non_losses"] += 1
            slot["flagged_return_sum_pct"] += v
        else:
            slot["unflagged_closed"] += 1
            slot["unflagged_losses" if v < 0 else "unflagged_non_losses"] += 1
            slot["unflagged_return_sum_pct"] += v

    unbound = len(indexed) - len(matched)
    if unbound:
        reasons["EVALUATION_UNIT_OUTSIDE_ENTRY_COHORT"] += unbound
    report = {
        "version": VERSION,
        "status": "S11_LOCAL_OUTCOME_LINK_DESCRIPTIVE_ONLY",
        "requested_capture_id": requested_capture_id,
        "canonical_capture_id": canonical,
        "evaluation_run_id": run_id,
        "protocol_id": run["protocol_id"],
        "cohort_counts": cohort["counts"],
        "cohort_scope": cohort["scope"],
        "entry_candidates_examined": observations,
        "outcome_units_for_capture": len(indexed),
        "unmatched_outcome_units": unbound,
        "exclusion_reasons": dict(sorted(reasons.items())),
        "review_status_counts": dict(sorted(status_counts.items())),
        "split_descriptive": {
            key: _finish_split(splits[key]) for key in ("DEVELOPMENT", "HOLDOUT")
        },
        "comparison_scope": "S9_SHADOW_RECHECK_VS_NO_ADVERSE_HISTORY_OBSERVATIONAL_ONLY",
        "causal_uplift_pct": None,
        "avoided_loss_claim": None,
        "incremental_investment_value": None,
        "performance_conclusion_allowed": False,
        "adoption_eligible": False,
        "source_release_time_verified": False,
        "evaluation_status": EVALUATION_STATUS,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
    return report


def evaluate_capture_readonly(
    simulation_db: Path, *, capture_id: str | None,
    evaluation_run_id: str | None, limit: int = 500,
) -> dict[str, Any]:
    if not capture_id or not evaluation_run_id:
        raise DecisionReviewContractError("S11_CAPTURE_AND_EVALUATION_RUN_REQUIRED")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise DecisionReviewContractError("S11_LIMIT_INVALID")
    pairs = load_frozen_candidates(
        simulation_db, capture_id=capture_id, limit=limit,
    )
    # canonical capture id must be resolved from the immutable sample loader.
    canonical = pairs[0][0]["id"] if pairs else capture_id
    run, units = load_evaluation_readonly(
        simulation_db, run_id=evaluation_run_id, capture_id=canonical,
    )
    return build_outcome_link_report(
        pairs, requested_capture_id=capture_id, limit=limit,
        run_id=evaluation_run_id, run=run, units=units,
    )
