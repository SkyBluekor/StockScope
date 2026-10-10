"""JEV-ACT1-S1 read-only audit of stored Prospective samples.

No network, provider construction, runtime migrations, activation, or DB writes.
Prints aggregate status only; never prints stock names, tickers or raw snapshots.
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
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import project_typesafe_state_v4, route_typesafe_state_v4
from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
)
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly, table_names


AUDIT_VERSION = "JEV_ACT1_S1_PROSPECTIVE_REACHABILITY_V1"
CATEGORIES = (
    "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE",
    "LOCAL_AMBIGUOUS", "PROVIDER_ELIGIBLE", "UNSUPPORTED_SCOPE",
    "LEGACY_SOURCE_MISSING", "INVALID_SEMANTIC_SOURCE",
)
LOCAL_STATUS_CATEGORY = {
    LOCAL_MATCH: "LOCAL_MATCH",
    LOCAL_CONFLICT: "LOCAL_CONFLICT",
    LOCAL_INCOMPLETE: "LOCAL_INCOMPLETE",
    LOCAL_AMBIGUOUS: "LOCAL_AMBIGUOUS",
    RESIDUAL_SEMANTIC_REVIEW: "PROVIDER_ELIGIBLE",
}


def _categorize(sample: dict[str, Any]) -> str:
    if (
        str(sample.get("action") or "") != "ENTRY_CANDIDATE"
        or str(sample.get("horizon_intent") or "") not in {"SHORT", "MEDIUM"}
    ):
        return "UNSUPPORTED_SCOPE"
    snapshot = sample.get("snapshot")
    if not isinstance(snapshot, dict) or not isinstance(
        snapshot.get("semantic_source_v2"), dict
    ):
        return "LEGACY_SOURCE_MISSING"
    try:
        route = route_typesafe_state_v4(sample)
        if route.provider_eligible:
            # Reachability must mean the real provider wire can be projected,
            # not merely that local composition emitted a residual status.
            project_typesafe_state_v4(sample)
        return LOCAL_STATUS_CATEGORY[route.local_status]
    except (TypeSafeStateProjectionError, KeyError, TypeError, ValueError):
        return "INVALID_SEMANTIC_SOURCE"


def audit_stored_prospective(db_path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    groups: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
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
                       s.action, s.snapshot_json, r.horizon_intent
                FROM prospective_recommendation_sample s
                JOIN prospective_capture_run r ON r.id=s.capture_run_id
                WHERE r.status='COMPLETE'
                ORDER BY s.capture_run_id, s.sample_index
                """
            )
            for row in cursor:
                capture_ids.add(str(row["capture_run_id"]))
                market = str(row["market"] or "UNKNOWN").upper()
                strategy = str(row["strategy"] or "UNKNOWN")
                try:
                    snapshot = json.loads(str(row["snapshot_json"]))
                except (TypeError, ValueError):
                    category = "INVALID_SEMANTIC_SOURCE"
                else:
                    category = _categorize({
                        "action": row["action"],
                        "horizon_intent": row["horizon_intent"],
                        "snapshot": snapshot,
                    })
                counts[category] += 1
                groups[(market, strategy)][category] += 1
        finally:
            conn.rollback()  # Ends the read-only snapshot. No writes were possible.

    total = sum(counts.values())
    compatible = sum(
        counts[key] for key in (
            "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE",
            "LOCAL_AMBIGUOUS", "PROVIDER_ELIGIBLE",
        )
    )
    breakdown = [
        {
            "market": market,
            "strategy": strategy,
            "samples": sum(group.values()),
            "provider_eligible": group["PROVIDER_ELIGIBLE"],
            "categories": {key: group[key] for key in CATEGORIES},
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
        "provider_eligible_pct": round(counts["PROVIDER_ELIGIBLE"] * 100 / total, 2) if total else 0.0,
        "categories": {key: counts[key] for key in CATEGORIES},
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
        description="Offline, read-only Prospective semantic reachability and JEV V4 activation checks"
    )
    parser.add_argument("--simulation-db", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print aggregate machine-readable JSON")
    args = parser.parse_args()
    try:
        result = run_readiness_audit(args.simulation_db or simulation_db_path())
    except (DataToolError, sqlite3.Error, OSError) as exc:
        # Never include exception details: filesystem paths may reveal personal information.
        print("JEV-ACT1-S1 FAIL: missing/unsupported/read-locked simulation DB; no changes made", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    audit, gate = result["audit"], result["activation_readiness"]
    print("=" * 70)
    print("JEV-ACT1-S1 실제 Scanner 기록 · 읽기 전용 진단")
    print("=" * 70)
    print(f"분석 캡처 {audit['total_captures']}개 / 저장 후보 {audit['total_samples']}개")
    print(f"V4 검사 가능 {audit['v4_compatible']}개")
    print(f"AI 추가 검토 대상 {audit['provider_eligible']}개 ({audit['provider_eligible_pct']}%)")
    for key in CATEGORIES:
        print(f"  {key:27s} {audit['categories'][key]}")
    print(f"제품 AI 활성화 판정: {gate['activation_verdict']} (활성화하지 않음)")
    for item in gate["checks"]:
        print(f"  {item['status']:5s} {item['code']}: {item['explanation']}")
    print("외부 호출 0건 / DB 쓰기 0건 / Runtime 동기화 없음")
    print("--json 옵션으로 시장·전략별 익명 집계 확인 가능")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
