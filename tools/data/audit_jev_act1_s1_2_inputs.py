"""JEV-ACT1-S1.2 aggregate-only, read-only Scanner semantic input audit.

Determines which stored *facts* are missing. Historical Selection Policy
provenance cannot be reconstructed merely from a missing candidate binding;
it is labeled UNKNOWN rather than guessed from a legacy horizon.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly


def audit_semantic_inputs(db: Path) -> dict:
    captures: dict[str, Counter[str]] = defaultdict(Counter)
    with sqlite_readonly(Path(db)) as conn:
        conn.execute("PRAGMA query_only=ON")
        try:
            rows = conn.execute(
                """
                SELECT r.completed_at, s.action, r.horizon_intent, s.snapshot_json
                FROM prospective_recommendation_sample s
                JOIN prospective_capture_run r ON r.id=s.capture_run_id
                WHERE r.status='COMPLETE'
                ORDER BY r.completed_at,s.sample_index
                """
            )
            for row in rows:
                if row["action"] != "ENTRY_CANDIDATE":
                    continue
                date_label = str(row["completed_at"] or "UNKNOWN")[:10]
                counter = captures[date_label]
                counter["entry_candidates"] += 1
                if row["horizon_intent"] == "LEGACY_UNSPECIFIED":
                    counter["legacy_horizon"] += 1
                try:
                    snapshot = json.loads(str(row["snapshot_json"]))
                except (ValueError, TypeError):
                    counter["invalid_snapshot"] += 1
                    continue
                if not isinstance(snapshot, dict):
                    counter["invalid_snapshot"] += 1
                    continue
                for key, label in (
                    ("strategy", "strategy_key_missing"),
                    ("strategy_version_id", "policy_strategy_version_missing"),
                    ("strategy_definition_hash", "policy_strategy_hash_missing"),
                ):
                    if not snapshot.get(key):
                        counter[label] += 1
                conditions = snapshot.get("conditions")
                if not isinstance(conditions, dict):
                    counter["condition_summary_missing"] += 1
                else:
                    counter["conditions_summary_present"] += 1
                    if int(conditions.get("total") or 0) <= 0:
                        counter["condition_count_missing"] += 1
                v2 = snapshot.get("semantic_source_v2")
                if not isinstance(v2, dict):
                    counter["semantic_v2_missing"] += 1
                else:
                    status = (v2.get("readiness") or {}).get("local_semantic_status")
                    counter["semantic_" + str(status or "UNKNOWN")] += 1
                identity = snapshot.get("semantic_strategy_identity")
                if isinstance(identity, dict) and identity.get("source"):
                    counter["attested_engine_identity_present"] += 1
                else:
                    counter["attested_engine_identity_missing"] += 1
                evidence = snapshot.get("semantic_condition_evidence")
                if isinstance(evidence, dict) and evidence.get("source"):
                    counter["attested_conditions_present"] += 1
                else:
                    counter["attested_conditions_missing"] += 1
        except sqlite3.OperationalError as exc:
            raise DataToolError("PROSPECTIVE_SCHEMA_UNAVAILABLE") from exc
    return {
        "version": "JEV_ACT1_S1_2_SEMANTIC_INPUT_AUDIT_V1",
        "policy_source_provenance_for_old_samples": "UNKNOWN_IF_NOT_ATTESTED",
        "by_capture_date": [
            {"date": date, **dict(sorted(count.items()))}
            for date, count in sorted(captures.items())
        ],
        "provider_calls": 0,
        "db_writes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only aggregate Scanner semantic input audit")
    parser.add_argument("--simulation-db", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = audit_semantic_inputs(args.simulation_db or simulation_db_path())
    except (OSError, DataToolError, sqlite3.Error):
        print("JEV-ACT1-S1.2 AUDIT FAIL: simulation DB unavailable; no changes", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
