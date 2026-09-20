from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

AUDIT_VERSION = "v0.21.4-B.2.5-D"
_BLOCKING_RISK = {"BLOCK", "BLOCKED", "RISK_BLOCKED", "REFERENCE_ONLY"}
_CAUTION_RISK = {"CAUTION", "WARNING", "WARN"}


def _risk_bad(candidate: dict[str, Any]) -> bool:
    risk = candidate.get("risk") or {}
    status = str(risk.get("status") or "").upper()
    return bool(risk.get("warning")) or status in _BLOCKING_RISK or status in _CAUTION_RISK


def _variant(run: dict[str, Any]) -> dict[str, Any]:
    variants = run.get("variants") or {}
    if "BASELINE_TOP3" in variants:
        return dict(variants.get("BASELINE_TOP3") or {})
    if variants:
        first_key = next(iter(variants))
        return dict(variants.get(first_key) or {})
    return {}


def _candidate_issue(date: str, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    state = str(candidate.get("candidate_state") or "").upper()
    action = str(candidate.get("action") or "").upper()
    conditions = candidate.get("conditions") or {}
    missing = int(conditions.get("missing") or 0)
    risk = candidate.get("risk") or {}
    risk_status = str(risk.get("status") or "").upper()
    risk_bad = _risk_bad(candidate)
    code = str(candidate.get("code") or "")

    def add(severity: str, kind: str, message: str) -> None:
        issues.append({
            "severity": severity,
            "kind": kind,
            "analysis_date": date,
            "code": code,
            "name": candidate.get("name"),
            "message": message,
        })

    if state == "READY":
        if missing > 0:
            add("ERROR", "READY_WITH_MISSING_CONDITIONS", f"READY인데 부족 조건이 {missing}개입니다.")
        if risk_bad:
            add("ERROR", "READY_WITH_BAD_RISK", f"READY인데 Risk={risk_status or '-'} 경고/차단이 존재합니다.")
        if action != "ENTRY_CANDIDATE":
            add("ERROR", "READY_ACTION_MISMATCH", f"READY인데 action={action or '-'}입니다.")

    if action == "ENTRY_CANDIDATE" and state != "READY":
        add("ERROR", "ENTRY_WITHOUT_READY", f"ENTRY_CANDIDATE인데 candidate_state={state or '-'}입니다.")

    if state == "WATCH" and action not in {"WAIT", "NEEDS_VALIDATION"}:
        add("REVIEW", "WATCH_ACTION_MISMATCH", f"WATCH인데 action={action or '-'}입니다.")

    if action == "NO_TRADE" and state in {"READY", "WATCH", "VALIDATION"}:
        add("ERROR", "NO_TRADE_ACTIONABLE_STATE", f"NO_TRADE인데 candidate_state={state}입니다.")

    return issues


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    variant = _variant(run)
    candidates = list(variant.get("candidates") or [])
    states = Counter(str(row.get("candidate_state") or "UNKNOWN").upper() for row in candidates)
    actions = Counter(str(row.get("action") or "UNKNOWN").upper() for row in candidates)
    bad_risk = sum(1 for row in candidates if _risk_bad(row))
    market_regime_failures = 0
    missing_total = 0
    for row in candidates:
        conditions = row.get("conditions") or {}
        missing_total += int(conditions.get("missing") or 0)
        for detail in conditions.get("top_missing") or []:
            if str(detail.get("metric_key") or "") == "market_regime":
                market_regime_failures += 1

    return {
        "analysis_date": str(run.get("analysis_date") or ""),
        "candidate_count": len(candidates),
        "ready_count": states.get("READY", 0),
        "watch_count": states.get("WATCH", 0),
        "validation_count": states.get("VALIDATION", 0),
        "entry_count": actions.get("ENTRY_CANDIDATE", 0),
        "wait_count": actions.get("WAIT", 0),
        "no_trade_count": actions.get("NO_TRADE", 0),
        "bad_risk_count": bad_risk,
        "market_regime_failure_count": market_regime_failures,
        "missing_condition_count": missing_total,
        "selected_stock_count": variant.get("selected_stock_count"),
        "actionable_count": variant.get("actionable_count"),
    }


def _representative_samples(run_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not run_summaries:
        return []

    no_ready = [row for row in run_summaries if int(row.get("ready_count") or 0) == 0 and int(row.get("candidate_count") or 0) > 0]
    samples: list[dict[str, Any]] = []

    # Prefer a broad weak-market day: many visible candidates, no READY, and explicit market-regime failures.
    weak_market = sorted(
        no_ready,
        key=lambda row: (
            int(row.get("market_regime_failure_count") or 0),
            int(row.get("candidate_count") or 0),
            str(row.get("analysis_date") or ""),
        ),
        reverse=True,
    )
    if weak_market:
        sample = dict(weak_market[0])
        sample["sample_kind"] = "WEAK_MARKET_NO_READY"
        samples.append(sample)

    # Prefer a separate Risk-gate day where a risky candidate remains WAIT instead of being promoted.
    risk_days = sorted(
        [row for row in no_ready if int(row.get("bad_risk_count") or 0) > 0],
        key=lambda row: (int(row.get("bad_risk_count") or 0), str(row.get("analysis_date") or "")),
        reverse=True,
    )
    if risk_days:
        candidate = risk_days[0]
        if not samples or candidate.get("analysis_date") != samples[0].get("analysis_date"):
            sample = dict(candidate)
            sample["sample_kind"] = "RISK_GATE_NO_READY"
            samples.append(sample)

    return samples[:2]


def audit_history_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runs = [row for row in payload.get("runs") or [] if str(row.get("status") or "OK").upper() == "OK"]
    issues: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    total_candidates = 0

    for run in runs:
        date = str(run.get("analysis_date") or "")
        variant = _variant(run)
        candidates = list(variant.get("candidates") or [])
        total_candidates += len(candidates)
        summary = _run_summary(run)
        summaries.append(summary)

        for candidate in candidates:
            issues.extend(_candidate_issue(date, candidate))

        if summary["ready_count"] == 0 and summary["entry_count"] > 0:
            issues.append({
                "severity": "ERROR",
                "kind": "FORCED_ENTRY_WITHOUT_READY",
                "analysis_date": date,
                "code": "",
                "name": "",
                "message": f"READY=0인데 ENTRY_CANDIDATE={summary['entry_count']}개입니다.",
            })

    error_count = sum(1 for row in issues if row.get("severity") == "ERROR")
    review_count = sum(1 for row in issues if row.get("severity") == "REVIEW")
    no_ready_dates = [row for row in summaries if row.get("ready_count") == 0 and row.get("candidate_count", 0) > 0]
    samples = _representative_samples(summaries)

    verdict = "ERROR" if error_count else "REVIEW" if review_count else "PASS"
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "verdict": verdict,
        "source": {
            "source_audit_version": payload.get("audit_version"),
            "scanner_version": payload.get("scanner_version"),
            "generated_at": payload.get("generated_at"),
            "valid_date_count": payload.get("valid_date_count"),
        },
        "summary": {
            "checked_dates": len(runs),
            "checked_candidates": total_candidates,
            "error_count": error_count,
            "review_count": review_count,
            "no_ready_date_count": len(no_ready_dates),
            "forced_entry_without_ready_count": sum(
                1 for row in issues if row.get("kind") == "FORCED_ENTRY_WITHOUT_READY"
            ),
            "ready_with_missing_count": sum(
                1 for row in issues if row.get("kind") == "READY_WITH_MISSING_CONDITIONS"
            ),
            "ready_with_bad_risk_count": sum(
                1 for row in issues if row.get("kind") == "READY_WITH_BAD_RISK"
            ),
            "entry_without_ready_count": sum(
                1 for row in issues if row.get("kind") == "ENTRY_WITHOUT_READY"
            ),
        },
        "representative_samples": samples,
        "no_ready_dates": no_ready_dates,
        "issues": issues,
    }


def render_markdown(report: dict[str, Any]) -> str:
    source = report.get("source") or {}
    summary = report.get("summary") or {}
    lines = [
        f"# Scanner NO_TRADE / Weak-Market Audit — {AUDIT_VERSION}",
        "",
        f"- verdict: **{report.get('verdict')}**",
        f"- source scanner version: `{source.get('scanner_version') or '-'}`",
        f"- checked dates: `{summary.get('checked_dates', 0)}`",
        f"- checked candidates: `{summary.get('checked_candidates', 0)}`",
        f"- dates with READY=0: `{summary.get('no_ready_date_count', 0)}`",
        f"- forced ENTRY with READY=0: `{summary.get('forced_entry_without_ready_count', 0)}`",
        "",
        "## Representative weak cases",
        "",
        "| Kind | Date | READY | WATCH | ENTRY | WAIT | Bad Risk | Market-regime fails | Candidates |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.get("representative_samples") or []:
        lines.append(
            "| {kind} | {date} | {ready} | {watch} | {entry} | {wait} | {bad} | {market} | {candidates} |".format(
                kind=row.get("sample_kind") or "-",
                date=row.get("analysis_date") or "-",
                ready=row.get("ready_count", 0),
                watch=row.get("watch_count", 0),
                entry=row.get("entry_count", 0),
                wait=row.get("wait_count", 0),
                bad=row.get("bad_risk_count", 0),
                market=row.get("market_regime_failure_count", 0),
                candidates=row.get("candidate_count", 0),
            )
        )

    lines.extend([
        "",
        "## Consistency checks",
        "",
        f"- READY + missing conditions: `{summary.get('ready_with_missing_count', 0)}`",
        f"- READY + bad Risk: `{summary.get('ready_with_bad_risk_count', 0)}`",
        f"- ENTRY_CANDIDATE without READY: `{summary.get('entry_without_ready_count', 0)}`",
        f"- READY=0인데 강제 ENTRY 생성: `{summary.get('forced_entry_without_ready_count', 0)}`",
        "",
        "## Issues",
        "",
    ])
    issues = report.get("issues") or []
    if not issues:
        lines.append("- 발견된 decision-gate consistency issue 없음")
    else:
        for issue in issues:
            lines.append(
                f"- **{issue.get('severity')} / {issue.get('kind')}** "
                f"{issue.get('analysis_date')} `{issue.get('code')}` — {issue.get('message')}"
            )
    lines.extend([
        "",
        "> 이 감사는 후보를 항상 N개 채우는지 자체가 아니라, 약한 날에도 WATCH/WAIT가 READY/ENTRY_CANDIDATE로 강제 승격되는지를 검사합니다.",
    ])
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, output_dir: Path, source_name: str) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"scanner-no-trade-audit_{timestamp}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    payload = dict(report)
    payload["source_file"] = source_name
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
