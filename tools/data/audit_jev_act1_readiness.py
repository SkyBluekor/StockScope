"""JEV-ACT1-S1/S1.1 offline audit of immutable Prospective Scanner samples.

Separates baseline scope from horizon scope. A legacy-horizon sample may be
locally inspected, but is NEVER granted provider call eligibility.
No model discovery, network, DB mutation, Runtime transport or replay.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.jev.activation_readiness import assess_jev_act1_readiness
from app.jev.semantic_scope_diagnostic import (
    LOCAL_INSPECTION_CATEGORIES,
    RESIDUAL_REVIEW_OBSERVED,
    inspect_stored_semantic_source,
)
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import project_typesafe_state_v4, route_typesafe_state_v4
from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION, digest_json
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
)
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly, table_names


AUDIT_VERSION = "JEV_ACT1_S1_1_PROSPECTIVE_SCOPE_V2"
CATEGORIES = (
    "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE",
    "LOCAL_AMBIGUOUS", "PROVIDER_ELIGIBLE",
    "ACTION_OUT_OF_SCOPE", "LEGACY_HORIZON_BLOCKED",
    "EXPLICIT_HORIZON_UNSUPPORTED", "SEMANTIC_SOURCE_MISSING",
    "SEMANTIC_SOURCE_INVALID",
)
LOCAL_STATUS_CATEGORY = {
    LOCAL_MATCH: "LOCAL_MATCH",
    LOCAL_CONFLICT: "LOCAL_CONFLICT",
    LOCAL_INCOMPLETE: "LOCAL_INCOMPLETE",
    LOCAL_AMBIGUOUS: "LOCAL_AMBIGUOUS",
    RESIDUAL_SEMANTIC_REVIEW: "PROVIDER_ELIGIBLE",
}
LOCAL_OK = ("LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE",
            "LOCAL_AMBIGUOUS", RESIDUAL_REVIEW_OBSERVED)


def _categorize(sample: dict[str, Any]) -> str:
    """Classify the *approved V4 route*, not speculative local reachability."""
    if str(sample.get("action") or "") != "ENTRY_CANDIDATE":
        return "ACTION_OUT_OF_SCOPE"
    horizon = str(sample.get("horizon_intent") or "")
    if horizon == "LEGACY_UNSPECIFIED":
        return "LEGACY_HORIZON_BLOCKED"
    if horizon not in {"SHORT", "MEDIUM"}:
        return "EXPLICIT_HORIZON_UNSUPPORTED"

    snapshot = sample.get("snapshot")
    if not isinstance(snapshot, dict) or not isinstance(
        snapshot.get("semantic_source_v2"), dict
    ):
        return "SEMANTIC_SOURCE_MISSING"
    if sample.get("snapshot_hash") and digest_json(snapshot) != sample["snapshot_hash"]:
        return "SEMANTIC_SOURCE_INVALID"
    try:
        route = route_typesafe_state_v4(sample)
        if route.provider_eligible:
            # A positive local route alone does not prove provider wire readiness.
            project_typesafe_state_v4(sample)
        return LOCAL_STATUS_CATEGORY[route.local_status]
    except (TypeSafeStateProjectionError, KeyError, TypeError, ValueError):
        return "SEMANTIC_SOURCE_INVALID"


def audit_stored_prospective(db_path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    legacy_local_counts: Counter[str] = Counter()
    groups: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    group_local: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    capture_ids: set[str] = set()
    with sqlite_readonly(Path(db_path)) as conn:
        conn.execute("PRAGMA query_only=ON")
        required = {
            "prospective_schema_meta",
            "prospective_capture_run",
            "prospective_recommendation_sample",
        }
        if not required.issubset(table_names(conn)):
            raise DataToolError("PROSPECTIVE_SCHEMA_MISSING")
        row = conn.execute(
            "SELECT value FROM prospective_schema_meta WHERE key='schema_version'"
        ).fetchone()
        if row is None or str(row["value"]) != PROSPECTIVE_SCHEMA_VERSION:
            raise DataToolError("PROSPECTIVE_SCHEMA_UNSUPPORTED")
        conn.execute("BEGIN")
        try:
            cursor = conn.execute(
                """
                SELECT s.capture_run_id, s.sample_index, s.market, s.strategy,
                       s.action, s.snapshot_json, s.snapshot_hash,
                       r.horizon_intent
                FROM prospective_recommendation_sample s
                JOIN prospective_capture_run r ON r.id=s.capture_run_id
                WHERE r.status='COMPLETE'
                ORDER BY s.capture_run_id, s.sample_index
                """
            )
            for row in cursor:
                capture_ids.add(str(row["capture_run_id"]))
                group_key = (
                    str(row["market"] or "UNKNOWN").upper(),
                    str(row["strategy"] or "UNKNOWN"),
                )
                action = str(row["action"] or "")
                horizon = str(row["horizon_intent"] or "")
                try:
                    snapshot = json.loads(str(row["snapshot_json"]))
                except (TypeError, ValueError):
                    snapshot = None
                sample = {
                    "action": action,
                    "horizon_intent": horizon,
                    "snapshot": snapshot,
                    "snapshot_hash": str(row["snapshot_hash"] or ""),
                }
                if action != "ENTRY_CANDIDATE":
                    category = "ACTION_OUT_OF_SCOPE"
                elif horizon == "LEGACY_UNSPECIFIED":
                    category = "LEGACY_HORIZON_BLOCKED"
                    local_status = inspect_stored_semantic_source(
                        snapshot,
                        stored_snapshot_hash=sample["snapshot_hash"],
                    )
                    legacy_local_counts[local_status] += 1
                    group_local[group_key][local_status] += 1
                elif snapshot is None:
                    category = "SEMANTIC_SOURCE_INVALID"
                else:
                    category = _categorize(sample)
                counts[category] += 1
                groups[group_key][category] += 1
        finally:
            conn.rollback()  # Closes a read-only snapshot; no writes are permitted.

    total = sum(counts.values())
    compatible = sum(counts[key] for key in (
        "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE",
        "LOCAL_AMBIGUOUS", "PROVIDER_ELIGIBLE",
    ))
    legacy_inspected = sum(legacy_local_counts[key] for key in LOCAL_OK)
    breakdown = [
        {
            "market": market,
            "strategy": strategy,
            "samples": sum(group.values()),
            "provider_eligible": group["PROVIDER_ELIGIBLE"],
            "categories": {key: group[key] for key in CATEGORIES},
            "legacy_local_inspection": {
                key: group_local[(market, strategy)][key]
                for key in LOCAL_INSPECTION_CATEGORIES
            },
        }
        for (market, strategy), group in sorted(groups.items())
    ]
    return {
        "version": AUDIT_VERSION,
        "scope": "COMPLETE_CANONICAL_PROSPECTIVE_SAMPLES",
        "total_captures": len(capture_ids),
        "total_samples": total,
        "v4_compatible": compatible,
        "provider_eligible": counts["PROVIDER_ELIGIBLE"],
        "provider_eligible_pct": (
            round(counts["PROVIDER_ELIGIBLE"] * 100 / total, 2) if total else 0.0
        ),
        "categories": {key: counts[key] for key in CATEGORIES},
        "legacy_local_inspection": {
            "total": counts["LEGACY_HORIZON_BLOCKED"],
            "inspectable": legacy_inspected,
            "residual_observed": legacy_local_counts[RESIDUAL_REVIEW_OBSERVED],
            "categories": {
                key: legacy_local_counts[key]
                for key in LOCAL_INSPECTION_CATEGORIES
            },
            "provider_eligible": 0,
        },
        "by_market_strategy": breakdown,
        "external_network_requests": 0,
        "provider_calls": 0,
        "db_writes": 0,
    }


def run_readiness_audit(db_path: Path) -> dict[str, Any]:
    audit = audit_stored_prospective(db_path)
    return {
        "audit": audit,
        "activation_readiness": assess_jev_act1_readiness(audit=audit),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline, read-only Prospective semantic and JEV V4 horizon scope audit"
    )
    parser.add_argument("--simulation-db", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print aggregate machine-readable JSON")
    args = parser.parse_args()
    try:
        result = run_readiness_audit(args.simulation_db or simulation_db_path())
    except (DataToolError, sqlite3.Error, OSError):
        print("JEV-ACT1-S1.1 FAIL: missing/unsupported/read-locked simulation DB; no changes made", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    audit, gate = result["audit"], result["activation_readiness"]
    print("=" * 70)
    print("JEV-ACT1-S1.1 Scanner · 기간별 로컬 의미 관계 진단 (읽기 전용)")
    print("=" * 70)
    print(f"분석 캡처 {audit['total_captures']}개 / 저장 후보 {audit['total_samples']}개")
    print(f"정식 V4 검사 가능 {audit['v4_compatible']}개")
    print(f"정식 AI 호출 승인 후보 {audit['provider_eligible']}개")
    for key in CATEGORIES:
        print(f"  {key:29s} {audit['categories'][key]}")
    legacy = audit["legacy_local_inspection"]
    print(f"기간 미지정 진입 후보 {legacy['total']}개 / 로컬 의미 검증 가능 {legacy['inspectable']}개")
    for key in LOCAL_INSPECTION_CATEGORIES:
        print(f"    {key:27s} {legacy['categories'][key]}")
    print("기간 미지정 로컬 의미 진단은 정식 Jev 모델 검토 승인이 아닙니다.")
    print(f"제품 AI 활성화 판정: {gate['activation_verdict']} (활성화하지 않음)")
    for item in gate["checks"]:
        print(f"  {item['status']:5s} {item['code']}: {item['explanation']}")
    print("외부 호출 0건 / DB 쓰기 0건 / Runtime 동기화 없음")
    print("--json 옵션으로 시장·전략별 익명 집계 확인 가능")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
