"""S12: one-command first local JEV observation using existing frozen records.

Selection is deliberately narrow: the latest completed Prospective evaluation
must link to exactly one canonical, COMPLETE capture, and the full sample count
must fit below the S11 read limit. The command never starts a scan/evaluation,
creates a database, sends data to a provider or claims profitable JEV.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any

from .decision_reviewer_offline import DecisionReviewContractError
from .local_outcome_link_s11 import evaluate_capture_readonly


VERSION = "JEV_LOCAL_FIRST_CHECK_V1"
MAX_FROZEN_SAMPLES = 499
_READ_LIMIT = 500
_REQUIRED_TABLES = frozenset({
    "prospective_capture_run",
    "prospective_recommendation_sample",
    "prospective_evaluation_run",
    "prospective_evaluation_unit",
})


def _status(code: str, **details: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": code,
        "result_kind": "LOCAL_READ_ONLY_DIAGNOSTIC",
        **details,
        "investment_improvement_verified": False,
        "performance_conclusion_allowed": False,
        "provider_status": "PROVIDER_HOLD",
        "external_model_calls": 0,
        "db_writes": 0,
    }


def first_local_check(simulation_db: Path) -> dict[str, Any]:
    """Select the latest completed run, never silently choose a different run."""
    db = Path(simulation_db)
    if not db.is_file():
        return _status("NO_LOCAL_SIMULATION_DB")

    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            actual_tables = {
                row["name"] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not _REQUIRED_TABLES.issubset(actual_tables):
                return _status("PROSPECTIVE_SCHEMA_NOT_READY")

            captures = int(conn.execute(
                "SELECT COUNT(*) FROM prospective_capture_run WHERE status='COMPLETE'"
            ).fetchone()[0])
            completed_runs = int(conn.execute(
                "SELECT COUNT(*) FROM prospective_evaluation_run WHERE status='COMPLETED'"
            ).fetchone()[0])

            if not captures:
                return _status(
                    "NO_COMPLETED_FROZEN_CAPTURE",
                    complete_capture_count=0, completed_evaluation_count=completed_runs,
                )
            if not completed_runs:
                return _status(
                    "NO_COMPLETED_PROSPECTIVE_EVALUATION",
                    complete_capture_count=captures, completed_evaluation_count=0,
                )

            latest = conn.execute(
                "SELECT id FROM prospective_evaluation_run "
                "WHERE status='COMPLETED' "
                "ORDER BY completed_at DESC,id DESC LIMIT 1"
            ).fetchone()
            run_id = str(latest["id"])
            summary = conn.execute(
                "SELECT COUNT(DISTINCT capture_run_id) AS capture_count "
                "FROM prospective_evaluation_unit WHERE evaluation_run_id=?",
                (run_id,),
            ).fetchone()
            linked_capture_count = int(summary["capture_count"])
            if not linked_capture_count:
                return _status(
                    "LATEST_EVALUATION_HAS_NO_UNITS",
                    complete_capture_count=captures,
                    completed_evaluation_count=completed_runs,
                    latest_evaluation_run_id=run_id,
                )
            # Deterministic, non-outcome-based selection: most recent signal
            # date in the latest completed run. No search for favorable results.
            # S11 will audit only this capture, not the entire multi-capture run.
            selected = conn.execute(
                "SELECT capture_run_id,COUNT(*) AS samples "
                "FROM prospective_evaluation_unit WHERE evaluation_run_id=? "
                "GROUP BY capture_run_id "
                "ORDER BY MAX(signal_date) DESC,capture_run_id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            capture_id = str(selected["capture_run_id"])
            evaluation_units = int(selected["samples"])
            cap = conn.execute(
                "SELECT status FROM prospective_capture_run WHERE id=?",
                (capture_id,),
            ).fetchone()
            if cap is None or cap["status"] != "COMPLETE":
                return _status(
                    "EVALUATION_CAPTURE_NOT_COMPLETE",
                    latest_evaluation_run_id=run_id,
                )

            frozen_count = int(conn.execute(
                "SELECT COUNT(*) FROM prospective_recommendation_sample "
                "WHERE capture_run_id=?", (capture_id,),
            ).fetchone()[0])
            if not frozen_count:
                return _status(
                    "EVALUATED_CAPTURE_HAS_NO_FROZEN_SAMPLES",
                    latest_evaluation_run_id=run_id,
                )
            if frozen_count > MAX_FROZEN_SAMPLES:
                return _status(
                    "FROZEN_SAMPLE_COUNT_EXCEEDS_READ_LIMIT",
                    frozen_sample_count=frozen_count,
                    safe_max_samples=MAX_FROZEN_SAMPLES,
                )
    except sqlite3.Error:
        return _status("LOCAL_PROSPECTIVE_READ_UNAVAILABLE")

    try:
        observed = evaluate_capture_readonly(
            db, capture_id=capture_id,
            evaluation_run_id=run_id, limit=_READ_LIMIT,
        )
    except DecisionReviewContractError as exc:
        return _status(
            "LOCAL_EVIDENCE_NOT_COMPARABLE",
            reason_code=exc.code,
            frozen_sample_count=frozen_count,
            evaluation_unit_count=evaluation_units,
        )

    splits = observed["split_descriptive"]
    matched = sum(
        splits[key]["closed_comparable"]
        for key in ("DEVELOPMENT", "HOLDOUT")
    )
    return _status(
        "DESCRIPTIVE_OUTCOMES_AVAILABLE" if matched else "NO_COMPARABLE_CLOSED_OUTCOMES",
        complete_capture_count=captures,
        completed_evaluation_count=completed_runs,
        captures_in_evaluation_run=linked_capture_count,
        selection_scope="LATEST_SIGNAL_CAPTURE_IN_LATEST_COMPLETED_RUN",
        selected_capture_id=capture_id,
        selected_evaluation_run_id=run_id,
        frozen_sample_count=frozen_count,
        evaluation_unit_count=evaluation_units,
        entry_candidates=observed["cohort_counts"]["entry_candidates"],
        reviewable=observed["cohort_counts"]["reviewable"],
        provisional_recheck=observed["cohort_counts"]["provisional_recheck"],
        abstained=observed["cohort_counts"]["abstained"],
        integrity_blocked=observed["cohort_counts"]["integrity_blocked"],
        exclusion_reasons=observed["exclusion_reasons"],
        split_descriptive=splits,
        prospective_evidence_status=observed["evaluation_status"],
        future_release_time_verified=False,
        # Observed outcome differences are not valid causal uplift.
        causal_uplift_pct=None,
        incremental_investment_value=None,
    )
