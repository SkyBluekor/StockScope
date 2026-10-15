"""Q7 S15→Prospective immutable *study-to-evidence* binding, research-only.

Never create an approval, derive original strategy identity, calculate returns,
read a locked holdout, or infer publication timestamps from local file clocks.
The frozen study is used only to select and audit existing completed captures.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from .decision_reviewer_offline import (
    DecisionReviewContractError, load_canonical_candidate_readonly,
)
from .q7_precommit_s15 import load, verify_artifact
from .scanner_capture_proof import inspect_capture_proof_readonly

VERSION = "Q7_STUDY_CAPTURE_BINDING_V1"
MAX_MATCHED_ENTRIES = 2000
MAX_CAPTURE_PROOFS = 260
_KST = ZoneInfo("Asia/Seoul")


def _report(status: str, **details: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "q7_approval_eligible": False,
        "production_activation_allowed": False,
        "jev_trial_approved": False,
        "model_data_transmission_approved": False,
        "external_provider_calls": 0,
        "runtime_db_writes": 0,
        "independent_samples_verified": None,
        "trusted_source_publication_time_proven": False,
        "trusted_precommit_timestamp_proven": False,
        "model_uplift_verified": False,
        **details,
    }


def audit_study_readonly(
    simulation_db: Path, *, study_id: str, root: Path | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Cross-check the frozen *strategy* identity with saved Scanner entry rows.

    `as_of` bounds observable signal dates; it is not permission to inspect
    a future or otherwise locked evaluation set. Source facts stay local.
    """
    frozen = load(study_id, **({"root": root} if root is not None else {}))
    receipt = verify_artifact(frozen, expected_study_id=study_id)
    spec = frozen["spec"]
    strategy = spec["strategy"]
    scope = spec["market_scope"]
    split = spec["time_split"]
    now = datetime.now(_KST).date()
    if as_of is not None and (type(as_of) is not date or as_of > now):
        return _report("INVALID_AS_OF", counts_complete=False)
    cutoff = as_of or now
    db = Path(simulation_db)
    if not db.is_file():
        return _report("NO_SIMULATION_DB", counts_complete=False)

    # Only the frozen strategy and declared development/holdout windows may be
    # matched. The future split stays uninspected until it has actually begun.
    windows = {
        "DEVELOPMENT": (split["development_start"], split["development_end"]),
        "HOLDOUT": (split["holdout_start"], split["holdout_end"]),
    }
    raw: list[tuple[str, int, str, str, str, str]] = []
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            for label, (start, end) in windows.items():
                # A future holdout cannot be examined just to manufacture
                # favorable counts. Even after the start, independent custody
                # and source as-of proof remain separate requirements.
                if start > cutoff.isoformat():
                    continue
                through = min(end, cutoff.isoformat())
                params: list[Any] = [strategy["strategy_key"], start, through]
                market_filter = ""
                if scope != "ALL":
                    market_filter = " AND s.market=?"
                    params.append(scope)
                rows = conn.execute(
                    "SELECT r.id AS capture_id,s.sample_index,s.signal_date,"
                    "s.market,s.ticker,s.strategy "
                    "FROM prospective_recommendation_sample s "
                    "JOIN prospective_capture_run r ON r.id=s.capture_run_id "
                    "WHERE r.status='COMPLETE' AND s.action='ENTRY_CANDIDATE' "
                    "AND s.strategy=? AND s.signal_date>=? AND s.signal_date<=?"
                    + market_filter +
                    " ORDER BY s.signal_date,r.id,s.sample_index LIMIT ?",
                    (*params, MAX_MATCHED_ENTRIES + 1),
                ).fetchall()
                raw.extend(
                    (label, row["capture_id"], row["sample_index"],
                     row["signal_date"], row["market"], row["ticker"])
                    for row in rows
                )
                if len(raw) > MAX_MATCHED_ENTRIES:
                    return _report(
                        "STUDY_AUDIT_LIMIT_EXCEEDED",
                        counts_complete=False, upper_bound=MAX_MATCHED_ENTRIES,
                    )
    except (sqlite3.Error, OSError, TypeError, ValueError):
        return _report("STUDY_SCHEMA_OR_DB_READ_UNAVAILABLE", counts_complete=False)

    capture_ids = sorted({row[1] for row in raw})
    if len(capture_ids) > MAX_CAPTURE_PROOFS:
        return _report(
            "STUDY_CAPTURE_LIMIT_EXCEEDED",
            counts_complete=False, upper_bound=MAX_CAPTURE_PROOFS,
        )
    proof_by_capture: dict[str, dict[str, Any]] = {}
    for capture_id in capture_ids:
        proof_by_capture[capture_id] = inspect_capture_proof_readonly(
            db, capture_id=capture_id, max_samples=500,
        )
        if proof_by_capture[capture_id]["status"] == "HOLD":
            return _report(
                "STUDY_CAPTURE_PROOF_INCOMPLETE", counts_complete=False,
                capture_failure_codes=dict(sorted(Counter(
                    p["reason_code"] for p in proof_by_capture.values()
                    if p["status"] == "HOLD"
                ).items())),
            )

    counts: dict[str, Counter[str]] = {
        label: Counter() for label in windows
    }
    seen: set[tuple[str, str, str, str]] = set()
    duplicate_keys = 0
    reasons: Counter[str] = Counter()
    for label, capture_id, index, signal_date, market, ticker in raw:
        counts[label]["matched_entries"] += 1
        key = (str(signal_date), str(market), str(ticker), strategy["strategy_key"])
        if key in seen:
            duplicate_keys += 1
        else:
            seen.add(key)
        record = next((
            x for x in proof_by_capture[capture_id].get("records", [])
            if x["sample_index"] == index
        ), None)
        if record is None:
            return _report("STUDY_ENTRY_PROOF_MISSING", counts_complete=False)
        if record["status"] == "LEGACY_INSPECTION_ONLY":
            counts[label]["legacy_limited"] += 1
            reasons["ORIGINAL_STRATEGY_IDENTITY_MISSING"] += 1
            continue
        if record["status"] != "LOCAL_PROJECTION_READY_PROVIDER_HOLD":
            counts[label]["contract_blocked"] += 1
            reasons[record["reason_code"]] += 1
            continue

        # The strict Reviewer contract is not sufficient to match *this*
        # preregistered strategy version. Never infer it from the current
        # engine definition, the semantic projection or a legacy hash.
        try:
            capture, sample = load_canonical_candidate_readonly(
                db, capture_id=capture_id, sample_index=index,
            )
            snapshot = sample["snapshot"]
        except (DecisionReviewContractError, KeyError, TypeError, ValueError):
            return _report("STUDY_ENTRY_SOURCE_CHANGED", counts_complete=False)
        if (snapshot.get("strategy_version_id") == strategy["strategy_version_id"]
                and snapshot.get("strategy_definition_hash") == strategy["definition_hash"]
                and sample.get("strategy") == strategy["strategy_key"]
                and sample.get("signal_date") == signal_date):
            counts[label]["strict_original_identity_match"] += 1
        else:
            counts[label]["study_strategy_version_mismatch"] += 1
            reasons["STUDY_STRATEGY_VERSION_MISMATCH"] += 1

    # "strict_original_identity_match" is a technical lineage check, NEVER a
    # verified independent sample, profitable holdout or lawful provider input.
    frozen_at = frozen["frozen_at"]
    start = split["holdout_start"]
    blockers = {
        "Q7_PRODUCTION_APPROVAL_NOT_IMPLEMENTED",
        "LOCAL_PRECOMMIT_TIME_NOT_INDEPENDENTLY_ATTESTED",
        "MARKET_SOURCE_PUBLICATION_TIME_NOT_PROVEN",
        "INDEPENDENT_SAMPLE_AND_REGIME_NOT_PROVEN",
        "NO_PROSPECTIVE_COMPARATIVE_PERFORMANCE_EVALUATION",
    }
    if start > cutoff.isoformat():
        blockers.add("FUTURE_HOLDOUT_NOT_STARTED")
    if not raw:
        blockers.add("NO_STUDY_MATCHED_FROZEN_ENTRY")
    if any(c["legacy_limited"] for c in counts.values()):
        blockers.add("ORIGINAL_STRATEGY_IDENTITY_MISSING")
    if any(c["contract_blocked"] or c["study_strategy_version_mismatch"]
           for c in counts.values()):
        blockers.add("STUDY_EVIDENCE_INVALID_OR_MISMATCHED")

    return _report(
        "RESEARCH_STUDY_HOLD",
        counts_complete=True,
        study_id=study_id,
        study_spec_hash=receipt["spec_hash"],
        frozen_at=frozen_at,
        local_precommit_authority=frozen["authority"],
        study_strategy_key=strategy["strategy_key"],
        as_of=cutoff.isoformat(),
        holdout_start=start,
        matched_entry_rows=len(raw),
        distinct_signal_keys_descriptive=len(seen),
        duplicate_signal_keys=duplicate_keys,
        capture_count=len(capture_ids),
        cohorts={
            key: {
                "matched_entries": counts[key]["matched_entries"],
                "strict_original_identity_match": counts[key]["strict_original_identity_match"],
                "legacy_limited": counts[key]["legacy_limited"],
                "contract_blocked": counts[key]["contract_blocked"],
                "study_strategy_version_mismatch": counts[key]["study_strategy_version_mismatch"],
            }
            for key in ("DEVELOPMENT", "HOLDOUT")
        },
        failure_reasons=dict(sorted(reasons.items())),
        remaining_blockers=sorted(blockers),
    )
