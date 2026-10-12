"""JEV S1.3 offline-only aggregate policy/engine-provenance audit.

Historical file alignment is useful evidence, but never establishes the missing
original SelectionPolicyPin. Do not auto-backfill old Prospective snapshots.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any

_PROJECT = Path(__file__).resolve().parents[2]
_BACKEND = _PROJECT / "backend"
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.jev.semantic_scope_diagnostic import inspect_stored_semantic_source
from app.prospective.models import digest_json
from app.strategy.semantic_identity_bridge import (
    _actual_passed_conditions,
    scanner_repro_candidate_key,
)
from tools.data.common import simulation_db_path, sqlite_readonly


AUDIT_VERSION = "JEV_ACT1_S1_3_POLICY_PROVENANCE_AUDIT_V1"


def _historical_repro_rows(root: Path, analysis_date: str, scanner_version: str) -> list[dict]:
    if not analysis_date or not scanner_version:
        return []
    # Read candidates from validated *historical* audits only, never create one.
    rows: list[dict] = []
    for path in root.glob(f"scanner-repro_*_analysis-{analysis_date.replace('-', '')}.json"):
        try:
            if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            candidates = payload.get("candidates")
            if (
                payload.get("analysis_date") != analysis_date
                or payload.get("scanner_version") != scanner_version
                or payload.get("result_source") != "fresh_analysis"
                or payload.get("candidate_pool_complete") is not True
                or not isinstance(candidates, list)
                or payload.get("candidate_count") != len(candidates)
            ):
                continue
            rows.extend(row for row in candidates if isinstance(row, dict))
        except (OSError, ValueError, UnicodeError, TypeError):
            continue
    return rows


def audit_policy_provenance(db: Path, repro_root: Path) -> dict[str, Any]:
    by_date: dict[str, Counter[str]] = defaultdict(Counter)
    capture_statuses: Counter[str] = Counter()
    cache: dict[tuple[str, str], list[dict]] = {}
    with sqlite_readonly(db) as conn:
        conn.execute("PRAGMA query_only=ON")
        for row in conn.execute(
            "SELECT status, COUNT(*) AS n FROM prospective_capture_run GROUP BY status"
        ):
            capture_statuses[str(row["status"])] = int(row["n"])
        samples = conn.execute("""
            SELECT r.actual_data_date, r.scanner_version, r.request_json,
                   s.snapshot_json, s.snapshot_hash, s.action
            FROM prospective_recommendation_sample s
            JOIN prospective_capture_run r ON r.id=s.capture_run_id
            WHERE r.status='COMPLETE'
            ORDER BY r.actual_data_date, s.sample_index
        """).fetchall()

    for sample in samples:
        date = str(sample["actual_data_date"] or "UNKNOWN")
        version = str(sample["scanner_version"] or "")
        count = by_date[date]
        count["stored_candidates"] += 1
        if sample["action"] != "ENTRY_CANDIDATE":
            count["non_entry_candidates"] += 1
            continue
        count["entry_candidates"] += 1
        try:
            snap = json.loads(str(sample["snapshot_json"]))
            req = json.loads(str(sample["request_json"]))
            if not isinstance(snap, dict) or not isinstance(req, dict):
                raise ValueError("invalid stored object")
            if digest_json(snap) != sample["snapshot_hash"]:
                count["snapshot_hash_invalid"] += 1
                continue
        except (TypeError, ValueError, json.JSONDecodeError):
            count["snapshot_invalid"] += 1
            continue
        record = snap.get("semantic_policy_provenance")
        if not isinstance(record, dict):
            count["policy_provenance_unknown_old_record"] += 1
        elif (
            record.get("status") == "VERIFIED_PINNED_EXECUTION"
            and record.get("policy_id")
            and record.get("policy_hash")
            and req.get("selection_policy_id") == record.get("policy_id")
            and req.get("selection_policy_hash") == record.get("policy_hash")
        ):
            count["policy_provenance_attested_new_record"] += 1
        else:
            count["policy_provenance_unverified_or_mismatch"] += 1

        count["semantic_" + inspect_stored_semantic_source(
            snap, stored_snapshot_hash=str(sample["snapshot_hash"])
        )] += 1

        cache_key = (date, version)
        if cache_key not in cache:
            cache[cache_key] = _historical_repro_rows(repro_root, date, version)
        key = scanner_repro_candidate_key(snap)
        matches = [
            row for row in cache[cache_key]
            if scanner_repro_candidate_key(row) == key and all(key)
        ]
        if not matches:
            count["historical_repro_candidate_not_found"] += 1
        elif any(_actual_passed_conditions(snap, row) is not None for row in matches):
            count["historical_engine_conditions_match"] += 1
        else:
            count["historical_engine_conditions_mismatch"] += 1

    return {
        "version": AUDIT_VERSION,
        "historical_policy_provenance_rule": (
            "MISSING_EXECUTION_PIN_IS_UNKNOWN; "
            "historical_repro_alignment_does_not_reconstruct_policy"
        ),
        "historical_repro_scope": "date/version/rank/conditions only; not original full execution attestation",
        "capture_statuses": dict(sorted(capture_statuses.items())),
        "by_analysis_date": [
            {"analysis_date": date, **dict(sorted(counts.items()))}
            for date, counts in sorted(by_date.items())
        ],
        "db_writes": 0,
        "external_provider_calls": 0,
        "runtime_sync": False,
        "holdout_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate read-only S1.3 policy provenance")
    parser.add_argument("--simulation-db", type=Path)
    parser.add_argument("--repro-root", type=Path, default=_PROJECT / "scanner-repro")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output = audit_policy_provenance(args.simulation_db or simulation_db_path(), args.repro_root)
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    print("JEV-ACT1-S1.3 정책 출처 및 실제 엔진 조건 근거 (읽기 전용)")
    print("캡처 상태:", output["capture_statuses"])
    for group in output["by_analysis_date"]:
        print(f"분석 기준일: {group['analysis_date']}")
        for key, value in group.items():
            if key != "analysis_date":
                print(f"  {key}: {value}")
    print("과거 캡처의 누락된 정책 Pin은 추정하거나 보완하지 않습니다.")
    print("DB 쓰기 0 / 외부 AI 호출 0 / Runtime 동기화 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
