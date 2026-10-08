"""JEV-X2: read-only explanation of two Scanner candidates' recorded ranking.

Never re-rank the Scanner output, infer missing historical evidence, or call AI.
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from app.prospective.catalog import ProspectiveCatalog, ProspectiveCatalogError
from app.prospective.models import digest_json

COMPARISON_VERSION = "SCANNER_CANDIDATE_COMPARISON_V1"
EVIDENCE_VERSION = "SCANNER_RANK_EVIDENCE_V1"
SORT_FIELDS = (
    ("tier_order", "후보 우선순위 구간"),
    ("missing", "미충족 전략 조건"),
    ("risk_quality", "Risk 품질"),
    ("entry_gap_missing", "진입 거리 근거 유무"),
    ("entry_gap_pct", "진입 기준 거리"),
    ("negative_strategy_fit", "현재 전략 적합도"),
    ("tie_focus_order", "동률 시 구조 목표 우선 표시"),
    ("code", "동률 시 종목코드 순서"),
)
TIER_ORDER = {
    "READY": 0, "NEAR_READY": 1, "WAIT": 2,
    "RISK_HOLD": 3, "LOW_PRIORITY": 4,
}
RISK_LABELS = {0: "경고 없음", 1: "주의", 2: "차단·참고 전용"}


def _unavailable(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "comparison_version": COMPARISON_VERSION,
        "ranking_changed": False,
        "provider_called": False,
    }


def _sort_values(evidence: dict[str, Any]) -> tuple[int | float | str, ...] | None:
    raw = evidence.get("sort_components")
    if not isinstance(raw, dict):
        return None
    result: list[int | float | str] = []
    for key, _ in SORT_FIELDS:
        value = raw.get(key)
        if key == "code":
            if not isinstance(value, str) or not value:
                return None
            result.append(value)
        elif key in {"tier_order", "missing", "risk_quality", "entry_gap_missing", "tie_focus_order"}:
            if type(value) is not int or value < 0:
                return None
            result.append(value)
        else:
            if type(value) not in (int, float) or not math.isfinite(value):
                return None
            result.append(float(value))
    if (
        result[3] not in (0, 1)
        or result[2] not in (0, 1, 2)
        or result[6] not in (0, 1)
        or result[0] not in TIER_ORDER.values()
        or str(evidence.get("code") or "") != result[-1]
        or TIER_ORDER.get(evidence.get("priority_tier")) != result[0]
    ):
        return None
    return tuple(result)


def _display(field: str, value: int | float | str, evidence: dict[str, Any]) -> str:
    if field == "tier_order":
        return str(evidence.get("priority_tier"))
    if field == "missing":
        return f"{value}개"
    if field == "risk_quality":
        return RISK_LABELS[int(value)]
    if field == "entry_gap_missing":
        return "근거 있음" if value == 0 else "근거 없음"
    if field == "entry_gap_pct":
        return "계산 불가" if evidence["sort_components"]["entry_gap_missing"] else f"{value:.2f}%"
    if field == "negative_strategy_fit":
        return f"{-float(value):.3f}"
    if field == "tie_focus_order":
        return "우선 표시" if value == 0 else "일반 순서"
    return str(value)


def _reason(field: str, winner: dict[str, Any], loser: dict[str, Any]) -> str:
    a = winner["name"]
    b = loser["name"]
    w = winner["evidence"]
    l = loser["evidence"]
    key = w["sort_components"]
    other = l["sort_components"]
    if field == "tier_order":
        return (
            f"{a}의 후보 우선순위 구간({w['priority_tier']})이 "
            f"{b}({l['priority_tier']})보다 앞서기 때문입니다."
        )
    if field == "missing":
        return (
            f"{a}의 미충족 전략 조건은 {key['missing']}개로, "
            f"{b}의 {other['missing']}개보다 적기 때문입니다."
        )
    if field == "risk_quality":
        return (
            f"{a}의 현재 Risk 분류({RISK_LABELS[key['risk_quality']]})가 "
            f"{b}({RISK_LABELS[other['risk_quality']]})보다 우선하기 때문입니다."
        )
    if field == "entry_gap_missing":
        return f"{a}는 진입 기준 거리를 계산할 수 있지만 {b}는 해당 근거가 없기 때문입니다."
    if field == "entry_gap_pct":
        return (
            f"{a}의 진입 기준 거리({key['entry_gap_pct']:.2f}%)가 "
            f"{b}({other['entry_gap_pct']:.2f}%)보다 가까워서입니다."
        )
    if field == "negative_strategy_fit":
        return (
            f"{a}의 현재 전략 적합도({-key['negative_strategy_fit']:.3f})가 "
            f"{b}({-other['negative_strategy_fit']:.3f})보다 높아서입니다."
        )
    if field == "tie_focus_order":
        return (
            "기본 우선순위가 완전히 같아, 저장된 구조 목표 근거상 "
            f"{a}가 동률 그룹 대표 후보로 먼저 표시됐기 때문입니다."
        )
    return (
        f"모든 실제 우선순위 요소가 같고, 마지막 안정적 종목코드 정렬로 "
        f"{a}가 {b}보다 앞서 표시됐습니다. 투자 품질의 차이를 의미하지 않습니다."
    )


def _make_comparison(
    left: dict[str, Any], right: dict[str, Any], *,
    canonical_id: str, capture_status: str,
) -> dict[str, Any]:
    lkey, rkey = _sort_values(left["evidence"]), _sort_values(right["evidence"])
    if lkey is None or rkey is None:
        return _unavailable("EVIDENCE_CONTEXT_MISMATCH")
    lrank = left["final_rank"]
    rrank = right["final_rank"]
    if (lkey < rkey) != (lrank < rrank) or lkey == rkey:
        return _unavailable("RANK_ORDER_INCONSISTENT")

    first = next(
        (index for index, (a, b) in enumerate(zip(lkey, rkey)) if a != b), None
    )
    if first is None:
        return _unavailable("RANK_ORDER_INCONSISTENT")
    name = SORT_FIELDS[first][0]
    winner, loser = (left, right) if lkey < rkey else (right, left)
    if name == "tie_focus_order":
        x, y = left["evidence"]["tie_resolution"], right["evidence"]["tie_resolution"]
        if not all((
            isinstance(x, dict), isinstance(y, dict),
            x.get("group") is not None,
            x.get("group") == y.get("group"),
            type(x.get("size")) is int, x.get("size") >= 2,
            x.get("size") == y.get("size"),
            x.get("breaker") == "STRUCTURAL_TARGET_NEAREST_PROMOTE",
            y.get("breaker") == "STRUCTURAL_TARGET_NEAREST_PROMOTE",
            x.get("focus_order") == lkey[6],
            y.get("focus_order") == rkey[6],
        )):
            return _unavailable("EVIDENCE_CONTEXT_MISMATCH")
    factors = [
        {
            "field": field, "label": label,
            "left_value": _display(field, lkey[i], left["evidence"]),
            "right_value": _display(field, rkey[i], right["evidence"]),
            "decisive": i == first,
            "used_for_decision": i <= first,
        }
        for i, (field, label) in enumerate(SORT_FIELDS)
    ]
    limitations = [
        "이 순위는 동일 실행 안에서의 우선 검토 순서이며, 실시간 매수 추천이나 수익 확률이 아닙니다.",
        "3년 과거 검증과 실시간 가격은 현재 순위를 결정한 항목에 포함되지 않습니다.",
    ]
    if capture_status == "PARTIAL":
        limitations.insert(0, "부분 데이터 캡처입니다. 비교는 저장된 반환 후보에만 적용됩니다.")
    return {
        "status": "AVAILABLE",
        "comparison_version": COMPARISON_VERSION,
        "capture_id": canonical_id,
        "capture_status": capture_status,
        "left": {k: left[k] for k in ("sample_index", "market", "code", "name", "strategy", "final_rank")},
        "right": {k: right[k] for k in ("sample_index", "market", "code", "name", "strategy", "final_rank")},
        "winner_sample_index": winner["sample_index"],
        "decisive_field": name,
        "decisive_reason": _reason(name, winner, loser),
        "factors": factors,
        "tie_resolution": winner["evidence"].get("tie_resolution") if name in ("tie_focus_order", "code") else None,
        "evidence_hashes": {
            str(left["sample_index"]): left["evidence_hash"],
            str(right["sample_index"]): right["evidence_hash"],
        },
        "limitations": limitations,
        "ranking_changed": False,
        "provider_called": False,
    }


def compare_capture_candidates(
    *, db_path: Path, capture_id: str, left_sample_index: int, right_sample_index: int,
) -> dict[str, Any]:
    """Only read immutable X1 evidence and matching Prospective samples."""
    if left_sample_index < 0 or right_sample_index < 0 or left_sample_index == right_sample_index:
        return _unavailable("INVALID_COMPARISON_PAIR")
    conn: sqlite3.Connection | None = None
    try:
        conn = ProspectiveCatalog(db_path).connect()
        conn.execute("BEGIN")  # same read snapshot for capture, samples, evidence
        cap = conn.execute(
            "SELECT * FROM prospective_capture_run WHERE id=?", (capture_id,)
        ).fetchone()
        if cap is None:
            return _unavailable("CAPTURE_NOT_FOUND")
        canonical_id = (
            str(cap["canonical_capture_id"])
            if cap["status"] == "DUPLICATE" and cap["canonical_capture_id"]
            else capture_id
        )
        canonical = conn.execute(
            "SELECT * FROM prospective_capture_run WHERE id=?", (canonical_id,)
        ).fetchone()
        if canonical is None:
            return _unavailable("CAPTURE_NOT_FOUND")
        if canonical["status"] not in ("COMPLETE", "PARTIAL"):
            return _unavailable("CAPTURE_NOT_FINALIZED")
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scanner_rank_evidence'"
        ).fetchone() is None:
            return _unavailable("RANK_EVIDENCE_MIGRATION_REQUIRED")
        rows = conn.execute(
            "SELECT s.sample_index,s.market,s.ticker,s.name,s.rank,s.strategy,"
            "s.snapshot_hash,s.snapshot_json,e.evidence_json,e.evidence_hash "
            "FROM prospective_recommendation_sample s "
            "LEFT JOIN scanner_rank_evidence e "
            "ON e.capture_run_id=s.capture_run_id AND e.sample_index=s.sample_index "
            "WHERE s.capture_run_id=? AND s.sample_index IN (?,?) ORDER BY s.sample_index",
            (canonical_id, left_sample_index, right_sample_index),
        ).fetchall()
        if len(rows) != 2:
            return _unavailable("SAMPLE_NOT_FOUND")
        found: dict[int, dict[str, Any]] = {}
        for row in rows:
            if row["evidence_json"] is None:
                return _unavailable("NOT_AVAILABLE_LEGACY")
            evidence = json.loads(str(row["evidence_json"]))
            snapshot = json.loads(str(row["snapshot_json"]))
            if (
                not isinstance(evidence, dict)
                or not isinstance(snapshot, dict)
                or digest_json(evidence) != row["evidence_hash"]
                or digest_json(snapshot) != row["snapshot_hash"]
            ):
                return _unavailable("EVIDENCE_HASH_MISMATCH")
            idx = int(row["sample_index"])
            if any((
                evidence.get("contract_version") != EVIDENCE_VERSION,
                evidence.get("market") != row["market"],
                evidence.get("code") != row["ticker"],
                evidence.get("strategy") != row["strategy"],
                evidence.get("final_rank") != idx + 1,
                row["rank"] is not None and int(row["rank"]) != idx + 1,
                evidence.get("sample_snapshot_hash") != row["snapshot_hash"],
                evidence.get("scanner_version") != canonical["scanner_version"],
                evidence.get("requested_as_of") != canonical["requested_as_of"],
                evidence.get("market_scope") != canonical["market_scope"],
                evidence.get("data_date") != canonical["actual_data_date"],
                evidence.get("source_snapshot_hash") != canonical["source_snapshot_hash"],
            )):
                return _unavailable("EVIDENCE_CONTEXT_MISMATCH")
            request = json.loads(str(canonical["request_json"]))
            if (
                evidence.get("selection_policy_id") != request.get("selection_policy_id")
                or evidence.get("selection_policy_hash") != request.get("selection_policy_hash")
            ):
                return _unavailable("EVIDENCE_CONTEXT_MISMATCH")
            found[idx] = {
                "sample_index": idx,
                "market": str(row["market"]),
                "code": str(row["ticker"]),
                "name": str(row["name"]),
                "strategy": str(row["strategy"] or ""),
                "final_rank": idx + 1,
                "evidence": evidence,
                "evidence_hash": str(row["evidence_hash"]),
            }
        left, right = found[left_sample_index], found[right_sample_index]
        return _make_comparison(
            left, right, canonical_id=canonical_id, capture_status=str(canonical["status"]),
        )
    except (ProspectiveCatalogError, sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        return _unavailable("RANK_EVIDENCE_STORE_UNAVAILABLE")
    finally:
        if conn is not None:
            conn.close()
