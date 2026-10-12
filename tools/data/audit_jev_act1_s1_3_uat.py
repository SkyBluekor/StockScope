"""JEV S1.3 UAT preflight and capture inspection; strictly read-only.

No Scanner/KRX session, runtime sync, migrations, AI or evaluation provider.
Never treat historical audit coincidence as original execution attestation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner import StockScannerService
from app.jev.semantic_scope_diagnostic import inspect_stored_semantic_source
from app.prospective.models import digest_json
from app.strategy.production_selection_policy import ProductionStrategySelectionRegistry
from app.strategy.semantic_identity_bridge import (
    _actual_passed_conditions,
    scanner_repro_candidate_key,
    verified_scanner_repro_rows,
)
from app.strategy.semantic_policy_provenance import validate_pinned_selection_policy
from app.strategy.semantic_source_v2 import verify_semantic_source_v2
from tools.data.common import (
    market_db_path,
    simulation_db_path,
    sqlite_readonly,
    table_names,
)

VERSION = "JEV_ACT1_S1_3_UAT_READONLY_V1"
TERMINAL = ("COMPLETE", "DUPLICATE", "PARTIAL", "FAILED", "CANCELLED", "INTERRUPTED")


def _status_counts(db: Path) -> dict[str, int]:
    with sqlite_readonly(db) as conn:
        conn.execute("PRAGMA query_only=ON")
        if not {"prospective_capture_run", "prospective_recommendation_sample", "prospective_schema_meta"}.issubset(table_names(conn)):
            raise ValueError("PROSPECTIVE_SCHEMA_MISSING")
        return {
            str(row["status"]): int(row["n"])
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM prospective_capture_run GROUP BY status")
        }


def baseline(db: Path) -> dict[str, Any]:
    """Immutable checksums for all *existing* finalized captures and samples.

    A later UAT run may add new IDs, but must not alter these exact rows.
    Exposes opaque capture IDs and digests only, never stocks or source data.
    """
    with sqlite_readonly(db) as conn:
        conn.execute("PRAGMA query_only=ON")
        if not {"prospective_capture_run", "prospective_recommendation_sample"}.issubset(table_names(conn)):
            raise ValueError("PROSPECTIVE_SCHEMA_MISSING")
        rows = conn.execute("""
            SELECT id, status, canonical_capture_id, source_execution_key,
                   source_snapshot_hash, result_hash, request_json
            FROM prospective_capture_run
            WHERE status IN ('COMPLETE','DUPLICATE','PARTIAL','FAILED','CANCELLED','INTERRUPTED')
            ORDER BY id
        """).fetchall()
        captures: dict[str, str] = {}
        for row in rows:
            samples = conn.execute("""
                SELECT sample_index, snapshot_hash, snapshot_json, rank
                FROM prospective_recommendation_sample
                WHERE capture_run_id=? ORDER BY sample_index
            """, (row["id"],)).fetchall()
            record = {k: row[k] for k in row.keys() if k != "id"}
            record["samples"] = [dict(item) for item in samples]
            captures[str(row["id"])] = digest_json(record)
    return {
        "version": VERSION,
        "capture_count": len(captures),
        "captures": captures,
        "db_writes": 0,
    }


def _latest_complete_data(conn: Any, market: str) -> str | None:
    row = conn.execute("""
        SELECT bas_dd FROM day_status
        WHERE market=? AND status='data' AND kind IN ('stock','index')
        GROUP BY bas_dd HAVING COUNT(DISTINCT kind)=2
        ORDER BY bas_dd DESC LIMIT 1
    """, (market,)).fetchone()
    return str(row["bas_dd"]) if row else None


def preflight(
    *,
    db: Path,
    market_db: Path,
    analysis_date: str,
    market_scope: str = "ALL",
    candidate_limit: int = 5,
    repro_root: Path | None = None,
    cache_root: Path | None = None,
    pin_resolver: Callable[[], Any] | None = None,
    check_git: bool = True,
    today: date | None = None,
) -> dict[str, Any]:
    """No provider objects created. Missing history counts are *store slots*,
    never represented as exact KRX network call estimates."""
    if market_scope not in {"ALL", "KOSPI", "KOSDAQ"} or not 1 <= candidate_limit <= 10:
        raise ValueError("INVALID_SCANNER_REQUEST")
    parsed = date.fromisoformat(analysis_date)
    kst_today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    reasons: list[str] = []
    warnings: list[str] = []
    if parsed >= kst_today:
        reasons.append("ANALYSIS_DATE_NOT_CONFIRMED")
    markets = ["KOSPI", "KOSDAQ"] if market_scope == "ALL" else [market_scope]
    result: dict[str, Any] = {
        "version": VERSION,
        "mode": "PREFLIGHT_NO_SCANNER_RUN",
        "analysis_date": analysis_date,
        "market_scope": market_scope,
        "candidate_limit": candidate_limit,
        "scanner_version": StockScannerService.VERSION,
    }
    try:
        result["existing_capture_statuses"] = _status_counts(db)
        with sqlite_readonly(db) as conn:
            conn.execute("PRAGMA query_only=ON")
            record = conn.execute("""
                SELECT COUNT(*) FROM prospective_capture_run
                WHERE status='COMPLETE' AND actual_data_date=? AND market_scope=?
            """, (analysis_date, market_scope)).fetchone()
            result["same_date_complete_captures"] = int(record[0])
            if record[0]:
                warnings.append("SAME_DATE_DUPLICATE_RISK")
    except Exception as exc:
        reasons.append("PROSPECTIVE_DB_NOT_READY")
        result["prospective_db_error_type"] = type(exc).__name__

    try:
        with sqlite_readonly(market_db) as conn:
            conn.execute("PRAGMA query_only=ON")
            if not {"stock_daily", "main_index_daily", "day_status"}.issubset(table_names(conn)):
                raise ValueError("MARKET_SCHEMA_MISSING")
            latest: dict[str, str | None] = {}
            requested_complete: dict[str, bool] = {}
            missing_slots: dict[str, int] = {}
            start = parsed - timedelta(days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS)
            start_key = start.strftime("%Y%m%d")
            end_key = parsed.strftime("%Y%m%d")
            dates = [
                (start + timedelta(days=i)).strftime("%Y%m%d")
                for i in range((parsed - start).days + 1)
                if (start + timedelta(days=i)).weekday() < 5
            ]
            for market in markets:
                latest[market] = _latest_complete_data(conn, market)
                status_rows = conn.execute("""
                    SELECT bas_dd, kind, status FROM day_status
                    WHERE market=? AND bas_dd BETWEEN ? AND ?
                """, (market, start_key, end_key)).fetchall()
                available = {(str(row["bas_dd"]), str(row["kind"])): row["status"] for row in status_rows}
                missing_slots[market] = sum(
                    1 for day in dates for kind in ("stock", "index")
                    if (day, kind) not in available
                )
                today_stock = available.get((end_key, "stock")) == "data"
                today_index = available.get((end_key, "index")) == "data"
                stock_count = conn.execute(
                    "SELECT COUNT(*) FROM stock_daily WHERE market=? AND bas_dd=?",
                    (market, end_key),
                ).fetchone()[0]
                index_count = conn.execute(
                    "SELECT COUNT(*) FROM main_index_daily WHERE market=? AND bas_dd=?",
                    (market, end_key),
                ).fetchone()[0]
                requested_complete[market] = bool(today_stock and today_index and stock_count and index_count)
                if not requested_complete[market]:
                    reasons.append(f"REQUESTED_DATE_MISSING_{market}")
                if latest[market] and latest[market] > end_key:
                    warnings.append(f"NEWER_LOCAL_DATE_EXISTS_{market}")
            result["latest_local_complete_day"] = {
                market: (value[:4] + "-" + value[4:6] + "-" + value[6:])
                if value else None for market, value in latest.items()
            }
            result["requested_date_complete"] = requested_complete
            result["missing_market_store_slots_220d"] = missing_slots
            result["missing_market_store_slots_total"] = sum(missing_slots.values())
            if any(missing_slots.values()):
                warnings.append("NETWORK_OR_RAW_CACHE_CHECK_REQUIRED")
    except Exception as exc:
        reasons.append("MARKET_DB_NOT_READY")
        result["market_db_error_type"] = type(exc).__name__

    try:
        pin = (pin_resolver or (lambda: ProductionStrategySelectionRegistry().pin_active_selection_policy()))()
        valid, why = validate_pinned_selection_policy(
            scanner_policy=pin.metadata(),
            request_policy_id=pin.policy_id,
            request_policy_hash=pin.policy_hash,
            pin=pin,
        )
        result["selection_policy_source"] = pin.policy_source
        result["policy_pin_valid"] = valid
        if not valid:
            reasons.append("POLICY_" + why)
    except Exception as exc:
        reasons.append("POLICY_PIN_UNAVAILABLE")
        result["policy_error_type"] = type(exc).__name__

    cache_dir = cache_root or StockScannerService.CACHE_ROOT
    files = list(cache_dir.glob(f"scanner_{market_scope.lower()}_{analysis_date}_{candidate_limit}_*.json")) if cache_dir.is_dir() else []
    result["possible_scanner_cache_files"] = len(files)
    if files:
        warnings.append("CACHE_REUSE_POSSIBLE")
    repro_dir = repro_root or PROJECT_ROOT / "scanner-repro"
    audits = list(repro_dir.glob(f"scanner-repro_*_analysis-{parsed.strftime('%Y%m%d')}.json")) if repro_dir.is_dir() else []
    result["existing_audit_files_same_date"] = len(audits)

    if check_git:
        try:
            git = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=12,
                check=True,
            )
            result["tracked_git_tree_clean"] = not bool(git.stdout.strip())
            if git.stdout.strip():
                reasons.append("TRACKED_WORKTREE_NOT_CLEAN")
        except (OSError, subprocess.SubprocessError):
            reasons.append("GIT_STATUS_UNAVAILABLE")

    result["known_network_requests"] = "UNKNOWN_NO_PROVIDER_OR_RAW_CACHE_INSPECTION"
    result["requires_explicit_execution_approval"] = True
    result["db_writes"] = 0
    result["external_provider_calls"] = 0
    result["reasons"] = sorted(set(reasons))
    result["warnings"] = sorted(set(warnings))
    if reasons:
        result["status"] = "BLOCKED"
    elif "NETWORK_OR_RAW_CACHE_CHECK_REQUIRED" in warnings:
        result["status"] = "REVIEW_NETWORK"
    elif "SAME_DATE_DUPLICATE_RISK" in warnings or "CACHE_REUSE_POSSIBLE" in warnings:
        result["status"] = "REVIEW_DUPLICATE"
    elif any(x.startswith("NEWER_LOCAL_DATE_EXISTS_") for x in warnings):
        result["status"] = "REVIEW_STALE_DATE"
    else:
        result["status"] = "READY_FOR_APPROVAL_NOT_EXECUTION"
    return result


def inspect(
    *,
    db: Path,
    repro_root: Path,
    capture_id: str,
    before: dict[str, Any] | None = None,
    scanner_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A verifiable UAT verdict requires a captured original Scanner result and
    before-state; stored snapshot + historical audit alone are insufficient."""
    problems: list[str] = []
    unresolved: list[str] = []
    with sqlite_readonly(db) as conn:
        conn.execute("PRAGMA query_only=ON")
        run = conn.execute(
            "SELECT * FROM prospective_capture_run WHERE id=?",
            (capture_id,),
        ).fetchone()
        if run is None:
            raise ValueError("CAPTURE_NOT_FOUND")
        rows = conn.execute("""
            SELECT rank, action, snapshot_hash, snapshot_json
            FROM prospective_recommendation_sample WHERE capture_run_id=?
            ORDER BY sample_index
        """, (capture_id,)).fetchall()
    out: dict[str, Any] = {
        "version": VERSION, "mode": "CAPTURE_INSPECT",
        "capture_status": run["status"],
        "candidate_rows": len(rows),
        "entry_candidates": 0,
    }
    if run["status"] != "COMPLETE":
        unresolved.append("NEW_COMPLETE_CAPTURE_REQUIRED")

    n_policy = n_engine = n_semantic = n_rank = 0
    stored_entry: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        try:
            snap = json.loads(str(row["snapshot_json"]))
            if not isinstance(snap, dict) or digest_json(snap) != row["snapshot_hash"]:
                problems.append("SAMPLE_SNAPSHOT_HASH_INVALID")
                continue
            if row["action"] != "ENTRY_CANDIDATE":
                continue
            out["entry_candidates"] += 1
            key = scanner_repro_candidate_key(snap)
            if all(key) and row["rank"] is not None and int(row["rank"]) == int(key[2]):
                n_rank += 1
                if key in stored_entry:
                    problems.append("DUPLICATE_STORED_CANDIDATE_KEY")
                else:
                    stored_entry[key] = snap
            else:
                problems.append("SAMPLE_RANK_MISMATCH")
            proof = snap.get("semantic_policy_provenance")
            request = json.loads(str(run["request_json"]))
            if (
                isinstance(proof, dict)
                and proof.get("status") == "VERIFIED_PINNED_EXECUTION"
                and proof.get("policy_id")
                and proof.get("policy_hash")
                and isinstance(request, dict)
                and proof["policy_id"] == request.get("selection_policy_id")
                and proof["policy_hash"] == request.get("selection_policy_hash")
            ):
                n_policy += 1
            else:
                unresolved.append("POLICY_ATTESTATION_NOT_STORED")
            evidence = snap.get("semantic_condition_evidence")
            if (
                isinstance(evidence, dict)
                and evidence.get("source") == "SCANNER_REPRO_ENGINE_PASSED_CONDITIONS_V1"
                and isinstance(evidence.get("items"), list)
                and evidence.get("passed") == evidence.get("total") == len(evidence["items"])
                and all(isinstance(item, dict) and item.get("status") == "PASS"
                        and item.get("condition_id") for item in evidence["items"])
            ):
                n_engine += 1
            else:
                unresolved.append("ENGINE_EVIDENCE_NOT_STORED")
            valid_v2, _ = verify_semantic_source_v2(snap.get("semantic_source_v2"))
            semantic_status = inspect_stored_semantic_source(snap, stored_snapshot_hash=str(row["snapshot_hash"]))
            if valid_v2 and semantic_status not in ("SEMANTIC_SOURCE_INVALID", "SEMANTIC_SOURCE_MISSING", "LOCAL_INCOMPLETE"):
                n_semantic += 1
            else:
                unresolved.append("SEMANTIC_V2_INVALID_OR_INCOMPLETE")
        except (TypeError, ValueError, KeyError, AttributeError):
            problems.append("SAMPLE_MALFORMED")
    out["rank_column_match"] = n_rank
    out["policy_attested"] = n_policy
    out["engine_evidence_stored"] = n_engine
    out["semantic_v2_complete"] = n_semantic

    if not out["entry_candidates"]:
        unresolved.append("NO_ENTRY_CANDIDATES")

    if before is None:
        unresolved.append("BEFORE_BASELINE_NOT_SUPPLIED")
    else:
        current = baseline(db)
        prior = before.get("captures") if isinstance(before, dict) else None
        if before.get("version") != VERSION or not isinstance(prior, dict):
            problems.append("BEFORE_BASELINE_INVALID")
        elif any(current["captures"].get(k) != v for k, v in prior.items()):
            problems.append("PRE_EXISTING_CAPTURES_MUTATED")
        elif capture_id in prior:
            unresolved.append("CAPTURE_ALREADY_PRESENT_BEFORE_UAT")
        else:
            out["preexisting_captures_unchanged"] = True

    if scanner_result is None:
        unresolved.append("ORIGINAL_SCANNER_RESULT_NOT_SUPPLIED")
    else:
        result_capture = scanner_result.get("prospective_capture")
        if (
            not isinstance(result_capture, dict)
            or result_capture.get("capture_id") != capture_id
            or result_capture.get("status") != "COMPLETE"
        ):
            problems.append("SCANNER_RESULT_CAPTURE_MISMATCH")
        if scanner_result.get("scanner_cache_hit") is not False:
            unresolved.append("SCANNER_NOT_FRESH_ANALYSIS")
        if bool(scanner_result.get("partial_data")):
            unresolved.append("SCANNER_PARTIAL")
        if scanner_result.get("requested_as_of") != run["actual_data_date"] or scanner_result.get("version") != run["scanner_version"]:
            problems.append("SCANNER_RUN_IDENTITY_MISMATCH")
        # Use the *original* result to enforce the full S1.2 audit file metadata,
        # fingerprint, path and candidate pool contract, not just historical date.
        from app.strategy import semantic_identity_bridge as bridge
        original_root = bridge.REPRO_ROOT
        try:
            bridge.REPRO_ROOT = repro_root
            verified = verified_scanner_repro_rows(scanner_result)
        finally:
            bridge.REPRO_ROOT = original_root
        result_candidates = [
            item for item in [*(scanner_result.get("candidates") or []), *(scanner_result.get("more_candidates") or [])]
            if isinstance(item, dict)
        ]
        if not verified:
            unresolved.append("ORIGINAL_REPRO_FULL_ATTESTATION_MISSING")
        if out["entry_candidates"] and verified:
            for item in result_candidates:
                if item.get("action") != "ENTRY_CANDIDATE":
                    continue
                key = scanner_repro_candidate_key(item)
                audit_row = verified.get(key)
                if not audit_row or _actual_passed_conditions(item, audit_row) is None:
                    problems.append("ORIGINAL_CANDIDATE_AUDIT_MISMATCH")
        if len(result_candidates) != len(rows):
            problems.append("SCANNER_CANDIDATE_ROW_COUNT_MISMATCH")
        source_entry = {}
        for candidate in result_candidates:
            if candidate.get("action") != "ENTRY_CANDIDATE":
                continue
            key = scanner_repro_candidate_key(candidate)
            if not all(key) or key in source_entry:
                problems.append("SCANNER_RESULT_CANDIDATE_KEY_INVALID")
                continue
            source_entry[key] = candidate
        if set(source_entry) != set(stored_entry):
            problems.append("SCANNER_STORED_ENTRY_KEYS_MISMATCH")
        for key in set(source_entry) & set(stored_entry):
            candidate, snap = source_entry[key], stored_entry[key]
            for field in (
                "market", "code", "priority", "strategy", "action",
                "candidate_state", "data_date", "current_price",
                "risk", "conditions", "strategy_version_id",
                "strategy_definition_hash",
            ):
                if candidate.get(field) != snap.get(field):
                    problems.append("ORIGINAL_SCANNER_CANDIDATE_CHANGED")
                    break
        if scanner_result.get("strategy_selection_policy") and rows:
            try:
                request = json.loads(str(run["request_json"]))
                policy_meta = scanner_result["strategy_selection_policy"]
                if (
                    policy_meta.get("policy_id") != request.get("selection_policy_id")
                    or policy_meta.get("policy_hash") != request.get("selection_policy_hash")
                ):
                    problems.append("ORIGINAL_SCANNER_POLICY_MISMATCH")
            except (TypeError, ValueError, AttributeError):
                problems.append("ORIGINAL_SCANNER_POLICY_MISMATCH")

    out["reasons"] = sorted(set(problems))
    out["inconclusive_reasons"] = sorted(set(unresolved))
    out["status"] = "FAIL" if problems else ("INCONCLUSIVE" if unresolved else "PASS")
    out["db_writes"] = 0
    out["external_provider_calls"] = 0
    out["runtime_sync"] = False
    out["holdout_accessed"] = False
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="UAT preflight/snapshot/inspect: offline and read-only")
    parser.add_argument("--simulation-db", type=Path, default=simulation_db_path())
    parser.add_argument("--market-db", type=Path, default=market_db_path())
    parser.add_argument("--repro-root", type=Path, default=PROJECT_ROOT / "scanner-repro")
    parser.add_argument("--cache-root", type=Path, default=StockScannerService.CACHE_ROOT)
    sub = parser.add_subparsers(dest="operation", required=True)
    pre = sub.add_parser("preflight", help="Read existing market coverage, policy and cache; no Scanner run")
    pre.add_argument("--as-of", required=True)
    pre.add_argument("--scope", choices=("ALL", "KOSPI", "KOSDAQ"), default="ALL")
    pre.add_argument("--limit", type=int, default=5)
    sub.add_parser("baseline", help="Print old capture fingerprints before approved UAT; redirect output yourself")
    post = sub.add_parser("inspect", help="Inspect one new capture without writing")
    post.add_argument("--capture-id", required=True)
    post.add_argument("--before", type=Path, help="Previously saved JSON baseline file")
    post.add_argument("--scanner-result", type=Path, help="Original JSON result for strict full repro checks")
    args = parser.parse_args()
    try:
        if args.operation == "preflight":
            output = preflight(
                db=args.simulation_db, market_db=args.market_db,
                analysis_date=args.as_of, market_scope=args.scope,
                candidate_limit=args.limit, repro_root=args.repro_root,
                cache_root=args.cache_root,
            )
        elif args.operation == "baseline":
            output = baseline(args.simulation_db)
        else:
            before = json.loads(args.before.read_text(encoding="utf-8")) if args.before else None
            result = json.loads(args.scanner_result.read_text(encoding="utf-8")) if args.scanner_result else None
            output = inspect(
                db=args.simulation_db, repro_root=args.repro_root,
                capture_id=args.capture_id, before=before, scanner_result=result,
            )
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"version": VERSION, "status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
