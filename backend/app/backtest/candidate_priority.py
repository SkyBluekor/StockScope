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


def _structural_target_distance(candidate: dict[str, Any]) -> tuple[float | None, str | None]:
    """Return distance to the existing structural Target1 reference.

    B.2.5-C uses this only inside an *exact* production-priority tie.  The
    value already exists in RiskPlan/Concrete Entry & Risk Guide and therefore
    introduces no new market signal, future data, or historical outcome into
    today's decision.  The 1.5R realism cap is intentionally not used here: the
    tie-break asks which tied candidate has the nearer real chart structure.
    """

    guide = candidate.get("entry_risk_guide") or {}
    risk = guide.get("risk") or {}
    structural = _number(risk.get("structural_target1_price"))
    entry = _number(risk.get("entry_reference_price"))
    if entry is None:
        entry = _number(candidate.get("current_price"))
    if structural is None or entry is None or entry <= 0 or structural <= entry:
        return None, None
    basis_raw = risk.get("structural_target1_basis")
    basis = str(basis_raw) if basis_raw not in (None, "") else "구조 목표"
    return (structural / entry - 1.0) * 100.0, basis


def _base_priority_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    """Production priority before the deterministic tie presentation layer."""

    # Rebuild the base components because rank_candidates removes the private
    # ``_sort`` payload from the public priority object before API serialization.
    priority = build_candidate_priority(candidate)
    sort = priority.get("_sort") or {}
    return (
        int(sort.get("tier_order", TIER_ORDER["LOW_PRIORITY"])),
        int(sort.get("missing", 999)),
        int(sort.get("risk_quality", 9)),
        int(sort.get("entry_gap_missing", 1)),
        float(sort.get("entry_gap_pct", 999999.0)),
        -float(sort.get("strategy_fit", 0.0)),
    )


def build_candidate_priority(candidate: dict[str, Any]) -> dict[str, Any]:
    passed, total, missing = _conditions(candidate)
    risk_quality, risk_bad, risk_status = _risk_quality(candidate)
    gap_pct, gap_basis = _entry_gap(candidate)
    historical_status = _historical_status(candidate)
    structural_target_distance_pct, structural_target_basis = _structural_target_distance(candidate)

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
        "structural_target_distance_pct": (
            None if structural_target_distance_pct is None else round(structural_target_distance_pct, 4)
        ),
        "structural_target_basis": structural_target_basis,
        "historical_status": historical_status,
        "ranking_rule": (
            "현재 조건 → Risk → 진입 근접도 → 현재 전략 적합도 → "
            "완전 동률이면 구조 목표가 가장 가까운 후보 1개 우선 → 나머지 종목코드"
        ),
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
    """Return the effective deterministic key after B.2.5-C tie promotion.

    Before ``rank_candidates`` assigns tie metadata, all candidates use focus
    order 0 and this reduces to the legacy current-only key plus the stock code.
    After ranking, the one evidence-backed focus candidate in an exact tie gets
    focus order 0 while its peers get 1, so the key reproduces the emitted rank.
    """

    priority = candidate.get("priority") or build_candidate_priority(candidate)
    focus_order = int(priority.get("tie_focus_order", 0) or 0)
    return (*_base_priority_sort_key(candidate), focus_order, str(candidate.get("code") or ""))


def _promote_structural_focus(group: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, int]]:
    """Promote one structural-nearest candidate; preserve every other peer order."""

    if len(group) <= 1:
        return list(group), {id(group[0]): 0} if group else {}

    available: list[tuple[float, str, int]] = []
    for index, candidate in enumerate(group):
        priority = candidate.get("priority") or {}
        distance = _number(priority.get("structural_target_distance_pct"))
        if distance is not None:
            available.append((distance, str(candidate.get("code") or ""), index))

    if not available:
        return list(group), {id(candidate): 0 for candidate in group}

    _distance, _code, best_index = min(available)
    best = group[best_index]
    promoted = [best, *group[:best_index], *group[best_index + 1 :]] if best_index else list(group)
    focus = {id(candidate): (0 if candidate is best else 1) for candidate in promoted}
    return promoted, focus


def rank_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank by current deterministic inputs, then resolve *exact* ties narrowly.

    B.2.5-C does not replace the production priority model.  Candidates are first
    ordered by the existing current-only priority components.  Only candidates
    whose complete base key is identical are peers.  Within each peer group, the
    candidate with the nearest existing *structural* Target1 is promoted to the
    front; every other peer stays in the legacy stock-code order.

    Historical Evidence remains explanation-only and never participates in the
    key.  Missing structural targets simply fall back to the legacy code order.
    """

    previous_rank = {id(candidate): index for index, candidate in enumerate(candidates, start=1)}
    for candidate in candidates:
        candidate["priority"] = build_candidate_priority(candidate)

    baseline = sorted(candidates, key=lambda candidate: (*_base_priority_sort_key(candidate), str(candidate.get("code") or "")))
    ranked: list[dict[str, Any]] = []
    focus_orders: dict[int, int] = {}
    group_sizes: dict[int, int] = {}
    group_ids: dict[int, int] = {}
    tie_breakers: dict[int, str] = {}

    group_number = 0
    cursor = 0
    while cursor < len(baseline):
        end = cursor + 1
        current_key = _base_priority_sort_key(baseline[cursor])
        while end < len(baseline) and _base_priority_sort_key(baseline[end]) == current_key:
            end += 1
        group = baseline[cursor:end]
        group_number += 1
        promoted, group_focus = _promote_structural_focus(group)
        has_structural_focus = len(group) > 1 and any(value == 1 for value in group_focus.values())
        for candidate in promoted:
            cid = id(candidate)
            focus_orders[cid] = int(group_focus.get(cid, 0))
            group_sizes[cid] = len(group)
            group_ids[cid] = group_number
            tie_breakers[cid] = (
                "STRUCTURAL_TARGET_NEAREST_PROMOTE"
                if has_structural_focus
                else "CODE_STABLE_ORDER" if len(group) > 1 else "NONE"
            )
        ranked.extend(promoted)
        cursor = end

    changes: list[dict[str, Any]] = []
    for new_rank, candidate in enumerate(ranked, start=1):
        old_rank = previous_rank[id(candidate)]
        priority = candidate["priority"]
        priority["tie_group"] = group_ids.get(id(candidate))
        priority["tie_size"] = group_sizes.get(id(candidate), 1)
        priority["tie_focus_order"] = focus_orders.get(id(candidate), 0)
        priority["tie_focus"] = bool(priority.get("tie_size", 1) > 1 and priority.get("tie_focus_order") == 0)
        priority["tie_breaker"] = tie_breakers.get(id(candidate), "NONE")
        priority["strict_rank"] = bool(priority.get("tie_size", 1) == 1)
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
            "tie_group": priority.get("tie_group"),
            "tie_size": priority.get("tie_size"),
            "tie_focus": priority.get("tie_focus"),
            "tie_breaker": priority.get("tie_breaker"),
            "structural_target_distance_pct": priority.get("structural_target_distance_pct"),
            "reason": str(priority.get("reason") or ""),
        })
    return ranked, changes

