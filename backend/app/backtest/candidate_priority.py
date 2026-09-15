from __future__ import annotations

from typing import Any


TIER_ORDER = {
    "READY": 0,
    "NEAR_READY": 1,
    "WAIT": 2,
    "RISK_HOLD": 3,
    "LOW_PRIORITY": 4,
}

TIER_LABELS = {
    "READY": "현재 진입 후보",
    "NEAR_READY": "진입 후보 가까움",
    "WAIT": "조건 확인 필요",
    "RISK_HOLD": "위험 때문에 보류",
    "LOW_PRIORITY": "현재 우선순위 낮음",
}

_HISTORICAL_ORDER = {
    "GOOD": 0,
    "FAIR": 1,
    "INSUFFICIENT": 2,
    "NO_CASES": 2,
    "DATA_UNAVAILABLE": 2,
    "NOT_RUN": 2,
    "WEAK": 3,
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _conditions(candidate: dict[str, Any]) -> tuple[int, int, int]:
    state = candidate.get("conditions") or {}
    total = max(0, int(state.get("total") or 0))
    passed = max(0, int(state.get("passed") or 0))
    missing = state.get("missing")
    missing_count = max(0, int(missing if missing is not None else max(0, total - passed)))
    return passed, total, missing_count


def _risk_quality(candidate: dict[str, Any]) -> tuple[int, bool, str | None]:
    risk = candidate.get("risk") or {}
    guide = candidate.get("entry_risk_guide") or {}
    action_status = str((guide.get("action") or {}).get("status") or "").upper()
    risk_status_raw = risk.get("status")
    risk_status = None if risk_status_raw is None else str(risk_status_raw).upper()
    warning = bool(risk.get("warning"))

    blocked = action_status == "RISK_BLOCKED" or risk_status in {
        "BLOCK",
        "BLOCKED",
        "RISK_BLOCKED",
        "REFERENCE_ONLY",
    }
    caution = warning or risk_status in {"CAUTION", "WARNING", "WARN"}
    if blocked:
        return 2, True, risk_status
    if caution:
        return 1, True, risk_status
    return 0, False, risk_status


def _entry_gap(candidate: dict[str, Any]) -> tuple[float | None, str | None]:
    """Return the engine-derived distance to the next concrete entry reference.

    No threshold is invented here. Values come only from the existing Concrete
    Entry & Risk Guide, which already translates Strategy/Entry Timing rules.
    """

    guide = candidate.get("entry_risk_guide") or {}
    rebound = guide.get("rebound_rule") or {}
    if bool(rebound.get("available")):
        gap = _number(rebound.get("gap_pct"))
        if gap is not None:
            return abs(gap), "반등 확인 가격"

    price = guide.get("price_rule") or {}
    if str(price.get("kind") or "") != "UNAVAILABLE":
        gap = _number(price.get("gap_pct"))
        if gap is not None:
            return abs(gap), str(price.get("label") or "진입 가격 기준")
    return None, None


def _historical_status(candidate: dict[str, Any]) -> str:
    evidence = candidate.get("historical_evidence") or {}
    if evidence:
        return str(evidence.get("status") or "DATA_UNAVAILABLE").upper()
    fit = candidate.get("historical_fit") or {}
    if bool(fit.get("verified")):
        return str(fit.get("status") or "INSUFFICIENT").upper()
    return "NOT_RUN"


def _strategy_fit(candidate: dict[str, Any]) -> float:
    value = candidate.get("_strategy_fit_score")
    if value is None:
        value = candidate.get("internal_rank")
    number = _number(value)
    return number if number is not None else 0.0


def build_candidate_priority(candidate: dict[str, Any]) -> dict[str, Any]:
    passed, total, missing = _conditions(candidate)
    risk_quality, risk_bad, risk_status = _risk_quality(candidate)
    gap_pct, gap_basis = _entry_gap(candidate)
    historical_status = _historical_status(candidate)

    if total <= 0:
        tier = "LOW_PRIORITY"
        reason = "현재 전략 조건을 충분히 계산하지 못해 우선순위를 높일 근거가 부족합니다."
    elif missing == 0 and risk_bad:
        tier = "RISK_HOLD"
        reason = "현재 전략 조건은 충족했지만 Risk 경고 때문에 우선순위를 낮췄습니다."
    elif missing == 0:
        tier = "READY"
        reason = "현재 전략 조건을 모두 충족했고 Risk 구조도 현재 판단을 막지 않습니다."
    elif missing <= 2 and not risk_bad:
        tier = "NEAR_READY"
        reason = f"부족 조건이 {missing}개뿐이고 Risk 구조가 현재 판단을 막지 않아 다음 확인 가치가 높습니다."
    else:
        tier = "WAIT"
        reason = f"현재 조건 {passed}/{total}이 충족됐지만 아직 부족한 조건이 있어 진입 후보보다 뒤에 둡니다."

    strengths: list[str] = []
    facts: list[str] = []
    penalties: list[str] = []

    if total > 0 and missing == 0:
        strengths.append(f"진입 조건 {passed}/{total} 충족")
    elif total > 0 and missing <= 2:
        facts.append(f"부족 조건 {missing}개")
    elif total > 0:
        penalties.append(f"아직 부족 조건 {missing}개")

    if risk_bad:
        if risk_status:
            penalties.append(f"Risk {risk_status}")
        else:
            penalties.append("Risk 경고 있음")
    else:
        strengths.append("Risk 구조 양호")

    if gap_pct is not None:
        facts.append(f"{gap_basis or '진입 기준'} 거리 {gap_pct:.1f}%")

    if historical_status == "GOOD":
        strengths.append("3년 과거 근거 양호")
    elif historical_status == "FAIR":
        strengths.append("3년 과거 근거 보통")
    elif historical_status == "WEAK":
        penalties.append("3년 과거 근거 약함")
    elif historical_status == "INSUFFICIENT":
        penalties.append("3년 과거 표본 부족")
    elif historical_status == "NO_CASES":
        penalties.append("3년 유사 사례 없음")
    elif historical_status == "DATA_UNAVAILABLE":
        penalties.append("3년 검증 데이터 부족")
    else:
        penalties.append("3년 과거 근거 확인 전")

    return {
        "tier": tier,
        "label": TIER_LABELS[tier],
        "reason": reason,
        "strengths": strengths[:4],
        "facts": facts[:4],
        "penalties": penalties[:4],
        "entry_gap_pct": None if gap_pct is None else round(gap_pct, 3),
        "entry_gap_basis": gap_basis,
        "historical_status": historical_status,
        "ranking_rule": "현재 조건 → Risk → 진입 근접도 → 3년 과거 근거 → 전략 적합도",
        "_sort": {
            "tier_order": TIER_ORDER[tier],
            "missing": missing,
            "risk_quality": risk_quality,
            "entry_gap_missing": 1 if gap_pct is None else 0,
            "entry_gap_pct": 999999.0 if gap_pct is None else gap_pct,
            "historical_order": _HISTORICAL_ORDER.get(historical_status, 2),
            "strategy_fit": _strategy_fit(candidate),
        },
    }


def priority_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    priority = candidate.get("priority") or build_candidate_priority(candidate)
    sort = priority.get("_sort") or {}
    return (
        int(sort.get("tier_order", TIER_ORDER["LOW_PRIORITY"])),
        int(sort.get("missing", 999)),
        int(sort.get("risk_quality", 9)),
        int(sort.get("entry_gap_missing", 1)),
        float(sort.get("entry_gap_pct", 999999.0)),
        int(sort.get("historical_order", 9)),
        -float(sort.get("strategy_fit", 0.0)),
        str(candidate.get("code") or ""),
    )


def rank_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank a bounded Scanner candidate pool without inventing probability scores."""

    previous_rank = {id(candidate): index for index, candidate in enumerate(candidates, start=1)}
    for candidate in candidates:
        candidate["priority"] = build_candidate_priority(candidate)

    ranked = sorted(candidates, key=priority_sort_key)
    changes: list[dict[str, Any]] = []
    for new_rank, candidate in enumerate(ranked, start=1):
        old_rank = previous_rank[id(candidate)]
        priority = candidate["priority"]
        priority.pop("_sort", None)
        priority["rank"] = new_rank
        priority["previous_rank"] = old_rank
        priority["rank_change"] = old_rank - new_rank
        candidate["candidate_label"] = str(priority.get("label") or candidate.get("candidate_label") or "")
        tier = str(priority.get("tier") or "")
        if tier == "READY":
            candidate["candidate_state"] = "READY"
        elif tier in {"NEAR_READY", "WAIT", "RISK_HOLD"}:
            candidate["candidate_state"] = "WATCH"
        else:
            candidate["candidate_state"] = "EXCLUDED"
        changes.append({
            "code": str(candidate.get("code") or ""),
            "name": str(candidate.get("name") or ""),
            "previous_rank": old_rank,
            "new_rank": new_rank,
            "rank_change": old_rank - new_rank,
            "tier": tier,
            "reason": str(priority.get("reason") or ""),
        })
    return ranked, changes
