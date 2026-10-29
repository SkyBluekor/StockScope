"""ACT2-S7: real frozen Scanner capture + local forward-market observation.

Real candidates are read from Prospective in SQLite query-only mode. Market
observations reuse the production ProspectiveEvaluator in OBSERVATION_ONLY mode.
Nothing here sends real-market fields to TypeSafe, creates an order, or
overrides an unapproved Horizon/source-rights policy.

S7 is a *data collection and eligibility gate*, not JEV efficacy proof.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.prospective.evaluation import ProspectiveEvaluator, ProspectiveEvaluationError
from app.prospective.models import digest_json
from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate
from app.jev.decision_reviewer_offline import (
    DecisionReviewContractError, build_scanner_review_input,
)

VERSION = "JEV_ACT2_S7_REAL_SCANNER_SHADOW_V1"
WINDOWS = (5, 10, 20)
EVALUATION_SPEC: dict[str, Any] = {
    "observation_windows": list(WINDOWS),
    "max_holding_days": 20,
    "execution_mode": "OBSERVATION_ONLY",
}
# Sentinel: there is no provider-capable real candidate adapter until source
# rights, publication timestamps, horizon and owner scope can all be proven.
PROVIDER_CALLS_SUPPORTED = False


def _connect_readonly(path: Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.is_file():
        raise DecisionReviewContractError("S7_SOURCE_DB_NOT_FOUND")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def load_frozen_candidates(
    simulation_db: Path, *, capture_id: str | None = None,
    limit: int = 60,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Read canonical COMPLETE captures, no duplicate or pending samples."""
    if type(limit) is not int or not 1 <= limit <= 500:
        raise DecisionReviewContractError("S7_LIMIT_INVALID")
    with _connect_readonly(simulation_db) as conn:
        try:
            params: list[Any] = []
            constraint = ""
            if capture_id:
                # A duplicate capture points at the immutable canonical record.
                requested = conn.execute(
                    "SELECT id,status,canonical_capture_id "
                    "FROM prospective_capture_run WHERE id=?",
                    (capture_id,),
                ).fetchone()
                if requested is None or requested["status"] not in ("COMPLETE", "DUPLICATE"):
                    raise DecisionReviewContractError("S7_CAPTURE_NOT_COMPLETE")
                canonical = (
                    requested["canonical_capture_id"]
                    if requested["status"] == "DUPLICATE" else requested["id"]
                )
                if not canonical:
                    raise DecisionReviewContractError("S7_CANONICAL_CAPTURE_MISSING")
                constraint = "AND r.id=?"
                params.append(canonical)
            # LIMIT on actual samples (rather than captures) to cap work.
            params.append(limit)
            rows = conn.execute(
                "SELECT r.*,s.sample_index,s.snapshot_json,s.snapshot_hash,"
                "s.capture_run_id,s.signal_date,s.market,s.ticker,s.name,"
                "s.strategy,s.action,s.rank,s.decision_status,s.candidate_state "
                "FROM prospective_recommendation_sample s "
                "JOIN prospective_capture_run r ON r.id=s.capture_run_id "
                "WHERE r.status='COMPLETE' " + constraint +
                " ORDER BY s.signal_date DESC,s.capture_run_id,s.sample_index LIMIT ?",
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DecisionReviewContractError("S7_SOURCE_SCHEMA_NOT_READY") from exc
    candidates = []
    for row in rows:
        capture = {
            key: row[key] for key in (
                "id", "status", "source_execution_key", "scanner_version",
                "scanner_baseline", "input_fingerprint", "actual_data_date",
                "horizon_intent", "horizon_policy_version",
                "created_at", "started_at", "completed_at",
                "request_json",
            )
        }
        sample = {
            key: row[key] for key in (
                "sample_index", "snapshot_hash", "capture_run_id",
                "signal_date", "market", "ticker", "name", "strategy",
                "action", "rank", "decision_status", "candidate_state",
            )
        }
        try:
            snapshot = json.loads(str(row["snapshot_json"]))
        except (ValueError, TypeError) as exc:
            raise DecisionReviewContractError("S7_SNAPSHOT_INVALID") from exc
        if not isinstance(snapshot, dict) or (
            not sample["snapshot_hash"]
            or digest_json(snapshot) != sample["snapshot_hash"]
        ):
            raise DecisionReviewContractError("S7_SNAPSHOT_HASH_MISMATCH")
        sample["snapshot"] = snapshot
        candidates.append((capture, sample))
    return candidates


def _observation(
    evaluator: ProspectiveEvaluator, sample: dict[str, Any],
) -> dict[str, Any]:
    """Never confuse observed EOD returns with an executable entry price."""
    try:
        ev = evaluator.evaluate_sample(sample=sample, spec=EVALUATION_SPEC)
    except (ProspectiveEvaluationError, sqlite3.Error, ValueError, KeyError) as exc:
        return {
            "status": "UNAVAILABLE",
            "reason": getattr(exc, "code", "S7_MARKET_EVIDENCE_INVALID"),
            "reference_price": None,
            "return_5d": None, "return_10d": None, "return_20d": None,
            "mfe_pct": None, "mae_pct": None,
            "available_trading_days": 0, "evaluated_through": None,
        }
    reference = (ev.get("details") or {}).get("reference_price")
    values = {f"return_{i}d": ev.get(f"return_{i}d") for i in WINDOWS}
    return {
        "status": "OBSERVATION_ONLY" if reference is not None else "NO_SIGNAL_PRICE",
        "reason": (
            "SIGNAL_CLOSE_NOT_EXECUTABLE_ENTRY"
            if reference is not None else "SIGNAL_EOD_REFERENCE_MISSING"
        ),
        "reference_price": reference,
        "return_5d": values["return_5d"],
        "return_10d": values["return_10d"],
        "return_20d": values["return_20d"],
        "mfe_pct": ev.get("mfe_pct"),
        "mae_pct": ev.get("mae_pct"),
        "available_trading_days": ev.get("available_trading_days"),
        "evaluated_through": ev.get("evaluated_through"),
        "maturity_status": ev.get("maturity_status"),
        "split": ev.get("split"),
    }


def inspect_candidate(
    capture: dict[str, Any],
    sample: dict[str, Any],
    evaluator: ProspectiveEvaluator,
) -> dict[str, Any]:
    """Immutable baseline and factual observation, with explicit provider HOLD."""
    identity = {
        "capture_id": capture["id"],
        "sample_index": int(sample["sample_index"]),
        "snapshot_hash": sample["snapshot_hash"],
        "signal_date": sample["signal_date"],
        "market": sample["market"],
        "ticker": sample["ticker"],
    }
    integrity = assess_frozen_candidate(capture, sample)
    blockers: list[str] = []
    try:
        projected = build_scanner_review_input(
            capture, sample, protocol_id=VERSION,
        )
        blockers.extend(projected["input"].get("limitations") or [])
        if projected["status"] != "OFFLINE_INSPECTABLE_ONLY":
            blockers.append(projected["reason_code"])
    except DecisionReviewContractError as exc:
        blockers.append(exc.code)
    if sample.get("action") != "ENTRY_CANDIDATE":
        blockers.append("NOT_ENTRY_CANDIDATE")
    else:
        blockers.extend(integrity["codes"])
    # Neither capture completed_at nor EOD signal_date proves the exact time
    # when source facts became legally available to an outside model.
    blockers.extend([
        "SOURCE_RELEASE_TIME_UNVERIFIED",
        "EXTERNAL_SOURCE_RIGHTS_UNVERIFIED",
        "HORIZON_NUMERIC_POLICY_NOT_APPROVED",
        "REAL_MARKET_PROVIDER_ADAPTER_NOT_AUTHORIZED",
    ])
    blockers = sorted(set(blockers))
    observation = (
        _observation(evaluator, sample)
        if sample.get("action") == "ENTRY_CANDIDATE"
        else {
            "status": "NOT_ENTRY_CANDIDATE",
            "reference_price": None, **{f"return_{i}d": None for i in WINDOWS},
        }
    )
    return {
        **identity,
        "name": sample.get("name"),
        "strategy": sample.get("strategy"),
        "rank": sample.get("rank"),
        "risk_status": (
            (sample.get("snapshot") or {}).get("risk") or {}
        ).get("status"),
        "capture_completed_at": capture.get("completed_at"),
        "baseline_action": sample.get("action"),
        "baseline_snapshot_hash": sample["snapshot_hash"],
        "integrity": integrity,
        "review_status": "PROVIDER_HOLD",
        "blockers": blockers,
        "review_source": "NO_REAL_JEV_CALL",
        "jev_decision": None,
        "model_returned": None,
        "observation": observation,
        "comparison_status": "NOT_EVALUATED_NO_AUTHORIZED_JEV",
        "economic_effect_proven": False,
    }


def inspect_real_candidates(
    simulation_db: Path, market_db: Path, *,
    capture_id: str | None = None, limit: int = 60,
) -> dict[str, Any]:
    """Read original EOD Scanner signals and subsequent existing market bars."""
    rows = load_frozen_candidates(simulation_db, capture_id=capture_id, limit=limit)
    evaluator = ProspectiveEvaluator(market_db)
    records = [inspect_candidate(c, s, evaluator) for c, s in rows]
    counts = Counter(reason for rec in records for reason in rec["blockers"])
    observed = sum(rec["observation"]["status"] == "OBSERVATION_ONLY" for rec in records)
    groups = Counter(rec["integrity"]["category"] for rec in records)
    issue_counts = Counter(
        code
        for rec in records
        if rec["integrity"]["category"] != "REFERENCE_ONLY"
        for code in rec["integrity"]["codes"]
    )
    return {
        "version": VERSION,
        "source_scope": "REAL_PROSPECTIVE_READ_ONLY",
        "status": "LOCAL_OBSERVATION_READY_PROVIDER_HOLD",
        "candidate_count": len(records),  # total inspected historical rows
        "entry_candidate_count": sum(
            rec["baseline_action"] == "ENTRY_CANDIDATE" for rec in records
        ),
        "reference_count": groups["REFERENCE_ONLY"],
        "local_validated_count": groups["LOCAL_VALIDATED"],
        "legacy_limited_count": groups["LEGACY_LIMITED"],
        "integrity_invalid_count": groups["INVALID"],
        "integrity_category_counts": dict(sorted(groups.items())),
        "integrity_issue_counts": dict(sorted(issue_counts.items())),
        "observed_price_count": observed,
        "real_jev_review_count": 0,
        "model_requests": 0,
        "real_stock_provider_eligible": 0,
        "window_definitions": {
            "windows_trading_days": list(WINDOWS),
            "reference": "SIGNAL_DAY_CLOSE_OBSERVATION_ONLY_NOT_EXECUTABLE",
            "entry_returns_or_strategy_uplift": "NOT_MEASURED",
        },
        "blocker_counts": dict(sorted(counts.items())),
        "records": records,
        "investment_uplift_proven": False,
    }


class S7ShadowJournal:
    """Separate append-only research store. No writing original source DBs."""

    def __init__(self, db: Path):
        self.db = Path(db)

    def initialize(self) -> None:
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS jev_s7_local_observation (
                evidence_hash TEXT PRIMARY KEY,
                capture_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                snapshot_hash TEXT NOT NULL,
                observed_through TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS jev_s7_immutable_update
            BEFORE UPDATE ON jev_s7_local_observation
            BEGIN SELECT RAISE(ABORT,'S7 observations immutable'); END;
            CREATE TRIGGER IF NOT EXISTS jev_s7_immutable_delete
            BEFORE DELETE ON jev_s7_local_observation
            BEGIN SELECT RAISE(ABORT,'S7 observations immutable'); END;

            -- S7.1 is a second immutable source of diagnostics so the
            -- first 60 real S7 research records are not modified/re-written.
            CREATE TABLE IF NOT EXISTS jev_s7_1_integrity_audit (
                diagnostic_hash TEXT PRIMARY KEY,
                capture_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                snapshot_hash TEXT NOT NULL,
                diagnostic_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS jev_s7_1_audit_immutable_update
            BEFORE UPDATE ON jev_s7_1_integrity_audit
            BEGIN SELECT RAISE(ABORT,'S7.1 diagnostics immutable'); END;
            CREATE TRIGGER IF NOT EXISTS jev_s7_1_audit_immutable_delete
            BEFORE DELETE ON jev_s7_1_integrity_audit
            BEGIN SELECT RAISE(ABORT,'S7.1 diagnostics immutable'); END;
            """)

    def capture(self, report: dict[str, Any]) -> dict[str, Any]:
        if report.get("version") != VERSION or report.get("model_requests") != 0:
            raise DecisionReviewContractError("S7_RESEARCH_INPUT_INVALID")
        self.initialize()
        inserted = reused = 0
        with sqlite3.connect(self.db) as conn:
            for item in report["records"]:
                if item.get("review_source") != "NO_REAL_JEV_CALL":
                    raise DecisionReviewContractError("S7_PROVIDER_RESULT_FORGED")
                integrity = item.get("integrity")
                if isinstance(integrity, dict):
                    audit_identity = {
                        "capture_id": item["capture_id"],
                        "sample_index": item["sample_index"],
                        "snapshot_hash": item["snapshot_hash"],
                        "diagnostic": integrity,
                    }
                    diagnostic_hash = digest_json(audit_identity)
                    conn.execute(
                        "INSERT OR IGNORE INTO jev_s7_1_integrity_audit "
                        "(diagnostic_hash,capture_id,sample_index,snapshot_hash,"
                        "diagnostic_json,created_at) VALUES(?,?,?,?,?,?)",
                        (
                            diagnostic_hash, item["capture_id"], item["sample_index"],
                            item["snapshot_hash"], json.dumps(integrity, ensure_ascii=False,
                                                              sort_keys=True),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                identity = {
                    "capture_id": item["capture_id"],
                    "sample_index": item["sample_index"],
                    "snapshot_hash": item["snapshot_hash"],
                    "observed_through": item["observation"].get("evaluated_through"),
                    "evidence": digest_json(item["observation"]),
                }
                key = digest_json(identity)
                before = conn.execute(
                    "SELECT 1 FROM jev_s7_local_observation WHERE evidence_hash=?",
                    (key,),
                ).fetchone()
                if before is not None:
                    reused += 1
                    continue
                conn.execute(
                    "INSERT INTO jev_s7_local_observation "
                    "(evidence_hash,capture_id,sample_index,snapshot_hash,"
                    "observed_through,payload_json,created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (
                        key, item["capture_id"], item["sample_index"],
                        item["snapshot_hash"],
                        item["observation"].get("evaluated_through"),
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                inserted += 1
        return {"inserted": inserted, "reused": reused, "provider_calls": 0}

    def report(self) -> dict[str, Any]:
        if not self.db.is_file():
            return self._summary([])
        with _connect_readonly(self.db) as conn:
            rows = conn.execute(
                "SELECT payload_json FROM jev_s7_local_observation "
                "ORDER BY created_at DESC,evidence_hash DESC"
            ).fetchall()
            has_diagnostics = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='jev_s7_1_integrity_audit'"
            ).fetchone()
            diag_rows = conn.execute(
                "SELECT capture_id,sample_index,snapshot_hash,diagnostic_json "
                "FROM jev_s7_1_integrity_audit "
                "ORDER BY created_at DESC,diagnostic_hash DESC"
            ).fetchall() if has_diagnostics else []
        latest_diags: dict[tuple[str, int, str], dict[str, Any]] = {}
        for row in diag_rows:
            key = (row["capture_id"], row["sample_index"], row["snapshot_hash"])
            latest_diags.setdefault(key, json.loads(row["diagnostic_json"]))
        by_candidate: dict[tuple[str, int, str], dict[str, Any]] = {}
        for row in rows:
            item = json.loads(row["payload_json"])
            key = (item["capture_id"], item["sample_index"], item["snapshot_hash"])
            if key in latest_diags:
                item["integrity"] = latest_diags[key]
            by_candidate.setdefault(key, item)
        return self._summary(list(by_candidate.values()))

    @staticmethod
    def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(r["observation"]["status"] for r in records)
        # The 5/10/20d denominator is ENTRY_CANDIDATE only, never all saved
        # references. Distinguish missing prices from insufficient future bars.
        entry = [r for r in records if r.get("baseline_action") == "ENTRY_CANDIDATE"]

        def window_summary(group: list[dict[str, Any]], window: int) -> dict[str, Any]:
            key = f"return_{window}d"
            measured: list[float] = []
            pending = unavailable = 0
            for row in group:
                observation = row["observation"]
                value = observation.get(key)
                if value is not None:
                    measured.append(float(value))
                    continue
                available = observation.get("available_trading_days")
                if (
                    observation.get("status") == "OBSERVATION_ONLY"
                    and type(available) is int and available < window
                ):
                    pending += 1
                else:
                    unavailable += 1
            return {
                "observed": len(measured),
                "average_signal_close_change_pct": (
                    round(sum(measured) / len(measured), 4) if measured else None
                ),
                "not_yet_observed": len(group) - len(measured),
                "awaiting_future_trading_days": pending,
                "price_unavailable_or_incomplete": unavailable,
                "entry_candidate_denominator": len(group),
            }

        per_window = {
            f"{window}d": window_summary(entry, window) for window in WINDOWS
        }
        # Old S7 journal rows survive untouched. Until a new capture has
        # written S7.1 diagnostics, category is explicitly NOT_DIAGNOSED.
        # Baseline action, not a potentially missing/older diagnostic tag,
        # establishes the entry vs reference denominator.
        groups = Counter(
            "REFERENCE_ONLY"
            if r.get("baseline_action") != "ENTRY_CANDIDATE"
            else (r.get("integrity") or {}).get("category", "NOT_DIAGNOSED")
            for r in records
        )
        validated = [
            r for r in entry
            if (r.get("integrity") or {}).get("category") == "LOCAL_VALIDATED"
        ]
        by_category = {
            category: {
                f"{window}d": window_summary(
                    [
                        r for r in entry
                        if (r.get("integrity") or {}).get(
                            "category", "NOT_DIAGNOSED"
                        ) == category
                    ],
                    window,
                ) for window in WINDOWS
            }
            for category in ("LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID", "NOT_DIAGNOSED")
        }
        errors = Counter(
            code for r in records if isinstance(r.get("integrity"), dict)
            and r["integrity"].get("category") != "REFERENCE_ONLY"
            for code in r["integrity"].get("codes", [])
        )
        return {
            "version": VERSION,
            "status": "LOCAL_PRICE_OBSERVATION_NOT_JEV_EFFICACY",
            "candidate_count": len(records),  # total historical rows
            "entry_candidate_count": len(entry),
            "reference_count": groups["REFERENCE_ONLY"],
            "local_validated_count": groups["LOCAL_VALIDATED"],
            "legacy_limited_count": groups["LEGACY_LIMITED"],
            "integrity_invalid_count": groups["INVALID"],
            "not_diagnosed_count": groups["NOT_DIAGNOSED"],
            "integrity_category_counts": dict(sorted(groups.items())),
            "integrity_issue_counts": dict(sorted(errors.items())),
            "validated_window_summaries": by_category["LOCAL_VALIDATED"],
            "entry_window_summaries_by_integrity": by_category,
            "price_statuses": dict(counts),
            "window_summaries": per_window,
            "actual_jev_reviews": 0,
            "provider_calls": 0,
            "avoided_loss_pct": None,
            "missed_gain_pct": None,
            "economic_uplift_proven": False,
            "blockers": sorted({x for r in records for x in r["blockers"]}),
            "records": records,
        }
