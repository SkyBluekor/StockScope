from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

AUDIT_VERSION = "v0.21.4-B.2.5-C.2"
_MIN_SCANNER_VERSION = (0, 21, 3, 7)
_SORT_COMPONENTS = (
    "tier_order",
    "missing",
    "risk_quality",
    "entry_gap_missing",
    "entry_gap_pct",
    "strategy_fit_desc",
    "tie_focus_order",
    "code",
)
_BLOCKING_RISK = {"BLOCK", "BLOCKED", "RISK_BLOCKED", "REFERENCE_ONLY"}
_CAUTION_RISK = {"CAUTION", "WARNING", "WARN"}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _risk_bad(candidate: dict[str, Any]) -> bool:
    risk = candidate.get("risk") or {}
    status = str(risk.get("status") or "").upper()
    return bool(risk.get("warning")) or status in _BLOCKING_RISK or status in _CAUTION_RISK


def _sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    raw = list(candidate.get("final_sort_key") or [])
    if not raw:
        return (999, 999, 9, 1, 999999.0, 0.0, 0, str(candidate.get("code") or ""))
    values: list[Any] = []
    for index, value in enumerate(raw):
        if index == len(raw) - 1:
            values.append(str(value or ""))
        else:
            number = _number(value)
            values.append(999999.0 if number is None else number)
    return tuple(values)


def _sort_component_names(length: int) -> tuple[str, ...]:
    # Legacy repro payloads (scanner <= 0.21.3.6) had no tie_focus_order.
    if length == 7:
        return (
            "tier_order",
            "missing",
            "risk_quality",
            "entry_gap_missing",
            "entry_gap_pct",
            "strategy_fit_desc",
            "code",
        )
    return _SORT_COMPONENTS


def _first_sort_difference(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    left_key = list(_sort_key(left))
    right_key = list(_sort_key(right))
    names = _sort_component_names(max(len(left_key), len(right_key)))
    for index, (left_value, right_value) in enumerate(zip(left_key, right_key)):
        if left_value == right_value:
            continue
        component = names[index] if index < len(names) else f"sort_{index}"
        return {
            "component": component,
            "left": left_value,
            "right": right_value,
        }
    return None


def _version_tuple(value: Any) -> tuple[int, ...] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts: list[int] = []
    for token in raw.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def _source_compatibility_checks(payload: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    scanner_version_raw = str(payload.get("scanner_version") or "")
    scanner_version = _version_tuple(scanner_version_raw)
    if scanner_version is None or scanner_version < _MIN_SCANNER_VERSION:
        issues.append({
            "severity": "ERROR",
            "kind": "STALE_SCANNER_SOURCE",
            "rank": 0,
            "code": "",
            "message": (
                f"B.2.5-C는 scanner >= 0.21.3.7 repro가 필요하지만 source={scanner_version_raw or '-'}입니다. "
                "실행 중인 backend를 재시작한 뒤 Scanner '다시 분석'으로 repro를 새로 생성하세요."
            ),
        })
        return issues

    for candidate in candidates:
        tie = candidate.get("priority_tie")
        sort_key = candidate.get("final_sort_key") or []
        if not isinstance(tie, dict) or "size" not in tie or "breaker" not in tie:
            issues.append({
                "severity": "ERROR",
                "kind": "B25C_TIE_METADATA_MISSING",
                "rank": int(candidate.get("rank") or 0),
                "code": str(candidate.get("code") or ""),
                "message": "scanner version은 새 버전인데 B.2.5-C priority_tie metadata가 없습니다.",
            })
            break
        if len(sort_key) != len(_SORT_COMPONENTS):
            issues.append({
                "severity": "ERROR",
                "kind": "B25C_SORT_KEY_SHAPE_MISMATCH",
                "rank": int(candidate.get("rank") or 0),
                "code": str(candidate.get("code") or ""),
                "message": (
                    f"B.2.5-C final_sort_key 길이는 {len(_SORT_COMPONENTS)}이어야 하지만 {len(sort_key)}입니다. "
                    "stale backend/repro 여부를 확인하세요."
                ),
            })
            break
    return issues


def _strategy_trace_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    trace = candidate.get("strategy_trace") or {}
    evaluations = list(trace.get("evaluations") or [])
    selected_strategy = str(trace.get("selected_strategy") or candidate.get("strategy") or "")
    selected = next(
        (
            row
            for row in evaluations
            if bool(row.get("selected")) or str(row.get("strategy") or "") == selected_strategy
        ),
        None,
    )
    alternatives = [
        {
            "strategy": row.get("strategy"),
            "selector_rank": row.get("selector_rank"),
            "selector_eligible": row.get("selector_eligible"),
            "selector_score": row.get("selector_score"),
            "current_evaluated": row.get("current_evaluated"),
            "current_status": row.get("current_status"),
            "current_internal_score": row.get("current_internal_score"),
            "missing": row.get("missing"),
            "risk_status": row.get("risk_status"),
            "risk_warning": row.get("risk_warning"),
            "selector_unmet": list(row.get("selector_unmet") or [])[:3],
        }
        for row in evaluations
        if str(row.get("strategy") or "") != selected_strategy
    ]
    return {
        "selection_method": trace.get("selection_method"),
        "selected_strategy": selected_strategy,
        "selected": selected,
        "alternatives": alternatives,
        "evaluation_count": len(evaluations),
    }


def _candidate_checks(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    rank = int(candidate.get("rank") or 0)
    code = str(candidate.get("code") or "")
    state = str(candidate.get("candidate_state") or "").upper()
    action = str(candidate.get("action") or "").upper()
    priority_tier = str(candidate.get("priority_tier") or "").upper()
    conditions = candidate.get("conditions") or {}
    missing = int(conditions.get("missing") or 0)
    risk_bad = _risk_bad(candidate)

    def add(severity: str, kind: str, message: str) -> None:
        issues.append({
            "severity": severity,
            "kind": kind,
            "rank": rank,
            "code": code,
            "message": message,
        })

    if state == "READY" or action == "ENTRY_CANDIDATE":
        if missing > 0:
            add("ERROR", "READY_WITH_MISSING_CONDITIONS", f"READY/ENTRY_CANDIDATE인데 부족 조건이 {missing}개입니다.")
        if risk_bad:
            add("ERROR", "READY_WITH_BAD_RISK", "READY/ENTRY_CANDIDATE인데 Risk 경고/차단 상태가 함께 존재합니다.")
        if priority_tier and priority_tier != "READY":
            add("ERROR", "READY_TIER_MISMATCH", f"candidate_state는 READY인데 priority_tier={priority_tier}입니다.")

    if action == "WAIT" and missing == 0 and not risk_bad:
        add("REVIEW", "WAIT_WITH_COMPLETE_GOOD_RISK", "조건 누락과 Risk 경고가 없는데 WAIT입니다. 추가 대기 조건이 있는지 확인이 필요합니다.")

    trace = _strategy_trace_summary(candidate)
    evaluations = list((candidate.get("strategy_trace") or {}).get("evaluations") or [])
    if not evaluations:
        add("REVIEW", "STRATEGY_TRACE_MISSING", "선택/탈락 전략 trace가 없습니다. 새 Scanner 실행으로 repro를 다시 생성해야 합니다.")
    else:
        selected = trace.get("selected")
        if selected is None:
            add("ERROR", "SELECTED_STRATEGY_TRACE_MISSING", "현재 선택 전략이 strategy_trace에서 발견되지 않습니다.")
        else:
            evaluated = [row for row in evaluations if bool(row.get("current_evaluated"))]
            scored = [
                row
                for row in evaluated
                if _number(row.get("current_internal_score")) is not None
            ]
            if scored:
                best_score = max(float(row["current_internal_score"]) for row in scored)
                selected_score = _number(selected.get("current_internal_score"))
                if selected_score is None or selected_score + 1e-9 < best_score:
                    add(
                        "ERROR",
                        "STRATEGY_SELECTION_SCORE_MISMATCH",
                        f"선택 전략 current score={selected_score}가 평가된 최고 score={best_score}보다 낮습니다.",
                    )

    return issues


def _tie_group_checks(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    groups: dict[Any, list[dict[str, Any]]] = {}
    for candidate in candidates:
        tie = candidate.get("priority_tie") or {}
        group = tie.get("group")
        size = int(tie.get("size") or 1)
        if group is None or size <= 1:
            continue
        groups.setdefault(group, []).append(candidate)

    for group, rows in groups.items():
        rows = sorted(rows, key=lambda item: int(item.get("rank") or 999999))
        first = rows[0]
        first_tie = first.get("priority_tie") or {}
        breaker = str(first_tie.get("breaker") or "")
        if breaker == "STRUCTURAL_TARGET_NEAREST_PROMOTE":
            distances = [
                (_number((row.get("priority_tie") or {}).get("structural_target_distance_pct")), row)
                for row in rows
            ]
            valid = [(distance, row) for distance, row in distances if distance is not None]
            if valid:
                expected_distance, expected = min(
                    valid,
                    key=lambda pair: (pair[0], str(pair[1].get("code") or "")),
                )
                if str(first.get("code") or "") != str(expected.get("code") or ""):
                    issues.append({
                        "severity": "ERROR",
                        "kind": "TIE_FOCUS_NOT_STRUCTURAL_NEAREST",
                        "rank": int(first.get("rank") or 0),
                        "code": str(first.get("code") or ""),
                        "message": (
                            f"동률 그룹 {group}의 첫 후보가 구조 목표 최단 후보가 아닙니다. "
                            f"expected={expected.get('code')} distance={expected_distance:.4f}%"
                        ),
                    })
                if not bool(first_tie.get("focus")) or int(first_tie.get("focus_order") or 0) != 0:
                    issues.append({
                        "severity": "ERROR",
                        "kind": "TIE_FOCUS_METADATA_MISMATCH",
                        "rank": int(first.get("rank") or 0),
                        "code": str(first.get("code") or ""),
                        "message": f"동률 그룹 {group}의 focus metadata가 실제 첫 후보와 일치하지 않습니다.",
                    })
        elif breaker == "CODE_STABLE_ORDER":
            codes = [str(row.get("code") or "") for row in rows]
            if codes != sorted(codes):
                issues.append({
                    "severity": "ERROR",
                    "kind": "CODE_FALLBACK_ORDER_MISMATCH",
                    "rank": int(first.get("rank") or 0),
                    "code": str(first.get("code") or ""),
                    "message": f"구조 목표가 없는 동률 그룹 {group}의 종목코드 fallback 순서가 비결정적입니다.",
                })
    return issues


def audit_repro_payload(payload: dict[str, Any], *, top_n: int = 5) -> dict[str, Any]:
    candidates = list(payload.get("candidates") or [])
    top_n = max(1, int(top_n))
    considered = candidates[:top_n]
    issues: list[dict[str, Any]] = []
    issues.extend(_source_compatibility_checks(payload, candidates))

    expected_order = sorted(candidates, key=_sort_key)
    actual_codes = [str(row.get("code") or "") for row in candidates]
    expected_codes = [str(row.get("code") or "") for row in expected_order]
    if actual_codes != expected_codes:
        issues.append({
            "severity": "ERROR",
            "kind": "FINAL_SORT_ORDER_MISMATCH",
            "rank": 0,
            "code": "",
            "message": "repro candidate 순서와 final_sort_key 재정렬 결과가 다릅니다.",
            "actual_codes": actual_codes,
            "expected_codes": expected_codes,
        })

    issues.extend(_tie_group_checks(candidates))

    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(considered):
        issues.extend(_candidate_checks(candidate))
        trace = _strategy_trace_summary(candidate)
        next_candidate = considered[index + 1] if index + 1 < len(considered) else None
        rows.append({
            "rank": candidate.get("rank") or index + 1,
            "code": candidate.get("code"),
            "name": candidate.get("name"),
            "strategy": candidate.get("strategy"),
            "candidate_state": candidate.get("candidate_state"),
            "action": candidate.get("action"),
            "conditions": candidate.get("conditions") or {},
            "risk": candidate.get("risk") or {},
            "priority_tier": candidate.get("priority_tier"),
            "entry_gap_pct": candidate.get("entry_gap_pct"),
            "entry_gap_basis": candidate.get("entry_gap_basis"),
            "strategy_fit_score": candidate.get("strategy_fit_score"),
            "final_sort_key": candidate.get("final_sort_key") or [],
            "priority_tie": candidate.get("priority_tie") or {},
            "why_above_next": _first_sort_difference(candidate, next_candidate) if next_candidate else None,
            "strategy_trace": trace,
            "price_plan": candidate.get("price_plan") or {},
        })

    error_count = sum(1 for row in issues if row.get("severity") == "ERROR")
    review_count = sum(1 for row in issues if row.get("severity") == "REVIEW")
    verdict = "ERROR" if error_count else "REVIEW" if review_count else "PASS"
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "repro_audit_version": payload.get("audit_version"),
            "scanner_version": payload.get("scanner_version"),
            "analysis_date": payload.get("analysis_date"),
            "market_scope": payload.get("market_scope"),
            "candidate_count": len(candidates),
            "candidate_pool_complete": payload.get("candidate_pool_complete"),
            "git": payload.get("git") or {},
        },
        "top_n": min(top_n, len(candidates)),
        "verdict": verdict,
        "summary": {
            "error_count": error_count,
            "review_count": review_count,
            "source_scanner_version": payload.get("scanner_version"),
            "b25c_source_ready": not any(
                row.get("kind") in {"STALE_SCANNER_SOURCE", "B25C_TIE_METADATA_MISSING", "B25C_SORT_KEY_SHAPE_MISMATCH"}
                for row in issues
            ),
            "ranking_order_consistent": actual_codes == expected_codes,
            "strategy_trace_available_count": sum(
                1 for row in considered if bool((row.get("strategy_trace") or {}).get("evaluations"))
            ),
            "ready_count": sum(1 for row in considered if str(row.get("candidate_state") or "").upper() == "READY"),
            "risk_warning_count": sum(1 for row in considered if _risk_bad(row)),
            "tied_candidate_count": sum(
                1 for row in considered if int(((row.get("priority_tie") or {}).get("size") or 1)) > 1
            ),
            "structural_focus_count": sum(
                1
                for row in considered
                if bool((row.get("priority_tie") or {}).get("focus"))
                and str((row.get("priority_tie") or {}).get("breaker") or "") == "STRUCTURAL_TARGET_NEAREST_PROMOTE"
            ),
            "code_fallback_tie_count": sum(
                1
                for row in considered
                if int(((row.get("priority_tie") or {}).get("size") or 1)) > 1
                and str((row.get("priority_tie") or {}).get("breaker") or "") == "CODE_STABLE_ORDER"
            ),
        },
        "candidates": rows,
        "issues": issues,
    }


def _fmt(value: Any) -> str:
    return "-" if value is None or value == "" else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    source = report.get("source") or {}
    summary = report.get("summary") or {}
    lines = [
        f"# Scanner Decision Quality Audit — {AUDIT_VERSION}",
        "",
        f"- verdict: **{report.get('verdict')}**",
        f"- analysis date: `{_fmt(source.get('analysis_date'))}`",
        f"- scanner version: `{_fmt(source.get('scanner_version'))}`",
        f"- B.2.5-C source ready: `{summary.get('b25c_source_ready')}`",
        f"- checked: Top {report.get('top_n')} / {source.get('candidate_count', 0)} candidates",
        f"- ranking order consistent: `{summary.get('ranking_order_consistent')}`",
        f"- strategy trace available: `{summary.get('strategy_trace_available_count')}/{report.get('top_n')}`",
        f"- tied candidates in checked range: `{summary.get('tied_candidate_count', 0)}`",
        f"- structural-focus candidates: `{summary.get('structural_focus_count', 0)}`",
        "",
        "## Top candidates",
        "",
        "| Rank | Candidate | Strategy | Decision | Conditions | Risk | Entry gap | Fit | Tie |",
        "|---:|---|---|---|---|---|---:|---:|---|",
    ]
    for row in report.get("candidates") or []:
        conditions = row.get("conditions") or {}
        risk = row.get("risk") or {}
        lines.append(
            "| {rank} | {name} `{code}` | {strategy} | {state}/{action} | {passed}/{total} (missing {missing}) | {risk_status}{warning} | {gap} | {fit} | {tie} |".format(
                rank=_fmt(row.get("rank")),
                name=_fmt(row.get("name")),
                code=_fmt(row.get("code")),
                strategy=_fmt(row.get("strategy")),
                state=_fmt(row.get("candidate_state")),
                action=_fmt(row.get("action")),
                passed=_fmt(conditions.get("passed")),
                total=_fmt(conditions.get("total")),
                missing=_fmt(conditions.get("missing")),
                risk_status=_fmt(risk.get("status")),
                warning=" ⚠" if risk.get("warning") else "",
                gap=_fmt(row.get("entry_gap_pct")),
                fit=_fmt(row.get("strategy_fit_score")),
                tie=(
                    "focus " + _fmt((row.get("priority_tie") or {}).get("structural_target_distance_pct")) + "%"
                    if bool((row.get("priority_tie") or {}).get("focus"))
                    else (
                        "peer" if int(((row.get("priority_tie") or {}).get("size") or 1)) > 1 else "-"
                    )
                ),
            )
        )

    lines.extend(["", "## Ranking reasons", ""])
    for row in report.get("candidates") or []:
        diff = row.get("why_above_next")
        if diff:
            lines.append(
                f"- #{row.get('rank')} {_fmt(row.get('name'))}: next candidate보다 먼저 갈린 기준 = "
                f"`{diff.get('component')}` ({diff.get('left')} vs {diff.get('right')})"
            )
        else:
            lines.append(f"- #{row.get('rank')} {_fmt(row.get('name'))}: 비교 대상 없음")

    lines.extend(["", "## Strategy selection", ""])
    for row in report.get("candidates") or []:
        trace = row.get("strategy_trace") or {}
        selected = trace.get("selected") or {}
        lines.append(
            f"### #{row.get('rank')} {_fmt(row.get('name'))} — {_fmt(trace.get('selected_strategy'))}"
        )
        lines.append(
            f"- selected: selector rank `{_fmt(selected.get('selector_rank'))}`, "
            f"current score `{_fmt(selected.get('current_internal_score'))}`, "
            f"status `{_fmt(selected.get('current_status'))}`"
        )
        alternatives = trace.get("alternatives") or []
        if alternatives:
            for alternative in alternatives[:4]:
                lines.append(
                    f"- alternative {_fmt(alternative.get('strategy'))}: selector rank `{_fmt(alternative.get('selector_rank'))}`, "
                    f"score `{_fmt(alternative.get('current_internal_score'))}`, "
                    f"missing `{_fmt(alternative.get('missing'))}`, "
                    f"risk `{_fmt(alternative.get('risk_status'))}`"
                )
        else:
            lines.append("- alternatives: trace 없음")
        lines.append("")

    lines.extend(["## Issues", ""])
    issues = report.get("issues") or []
    if not issues:
        lines.append("- 발견된 consistency issue 없음")
    else:
        for issue in issues:
            lines.append(
                f"- **{issue.get('severity')} / {issue.get('kind')}** "
                f"#{issue.get('rank')} `{issue.get('code')}` — {issue.get('message')}"
            )
    lines.append("")
    lines.append("> 이 감사는 B.2.5-C의 동률 해소 규칙까지 포함해 Production Ranking의 재현성과 일관성을 검사합니다.")
    return "\n".join(lines)


def write_report(
    report: dict[str, Any],
    *,
    output_dir: Path,
    source_name: str = "scanner-repro",
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_date = str((report.get("source") or {}).get("analysis_date") or "unknown").replace("-", "")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"scanner-decision-quality_{analysis_date}_{timestamp}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    report = dict(report)
    report["source_file"] = source_name
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
