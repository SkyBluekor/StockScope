from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "SCANNER_RANK_EVIDENCE_V1"


def extract_rank_evidence_from_audit(
    result: dict[str, Any],
    *,
    audit_root: Path | None = None,
) -> list[dict[str, Any]] | None:
    """Project actual ranking-time audit facts; never rerank or infer hidden keys.

    The Scanner production files and their frozen fingerprint stay unchanged.
    Reject missing, foreign, stale, mismatched or incomplete audit records.
    """
    diagnostics = result.get("diagnostics")
    info = (
        diagnostics.get("reproducibility_audit")
        if isinstance(diagnostics, dict)
        else None
    )
    if not isinstance(info, dict) or info.get("written") is not True:
        return None
    root = audit_root or (Path(__file__).resolve().parents[3] / "scanner-repro")
    try:
        path = Path(str(info.get("path") or "")).resolve(strict=True)
        if path.parent != root.resolve() or path.stat().st_size > 20_000_000:
            return None
        raw = path.read_bytes()
        audit = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError, TypeError):
        return None

    if not isinstance(audit, dict) or any((
        str(audit.get("scanner_version")) != str(result.get("version")),
        str(audit.get("analysis_date")) != str(result.get("requested_as_of")),
        str(audit.get("market_scope")) != str(result.get("market_scope")),
        audit.get("result_source") != "fresh_analysis",
    )):
        return None

    returned = [
        row
        for bucket in ("candidates", "more_candidates")
        for row in (result.get(bucket) or [])
        if isinstance(row, dict)
    ]
    audited = audit.get("candidates")
    if not isinstance(audited, list) or len(audited) < len(returned):
        return None
    if audit.get("candidate_count") != len(audited):
        return None

    fingerprint = hashlib.sha256(raw).hexdigest()
    projection: list[dict[str, Any]] = []
    for index, candidate in enumerate(returned):
        row = audited[index]
        if not isinstance(row, dict):
            return None
        priority = candidate.get("priority")
        priority = priority if isinstance(priority, dict) else {}
        if any((
            row.get("market") != candidate.get("market"),
            row.get("code") != candidate.get("code"),
            row.get("strategy") != candidate.get("strategy"),
            row.get("rank") != index + 1,
            priority.get("rank") != index + 1,
            row.get("priority_tier") != priority.get("tier"),
            row.get("candidate_state") != candidate.get("candidate_state"),
            row.get("action") != candidate.get("action"),
            row.get("conditions") != (candidate.get("conditions") or {}),
        )):
            return None
        order = row.get("final_sort_key")
        sort = row.get("priority_sort_components")
        tie = row.get("priority_tie")
        if (
            not isinstance(order, list) or len(order) != 8
            or not isinstance(sort, dict) or not isinstance(tie, dict)
            or order[-1] != candidate.get("code")
        ):
            return None
        expected = [
            sort.get("tier_order"),
            sort.get("missing"),
            sort.get("risk_quality"),
            sort.get("entry_gap_missing"),
            sort.get("entry_gap_pct"),
            -float(sort.get("strategy_fit") or 0.0),
            tie.get("focus_order", 0),
            candidate.get("code"),
        ]
        if order != expected:
            return None
        if any(
            priority.get(public) != tie.get(audit_key)
            for public, audit_key in (
                ("tie_group", "group"),
                ("tie_size", "size"),
                ("tie_focus_order", "focus_order"),
                ("tie_breaker", "breaker"),
            )
        ):
            return None
        projection.append({
            "contract_version": CONTRACT_VERSION,
            "market": str(candidate["market"]),
            "code": str(candidate["code"]),
            "strategy": str(candidate["strategy"]),
            "strategy_version_id": candidate.get("strategy_version_id"),
            "strategy_definition_hash": candidate.get("strategy_definition_hash"),
            "final_rank": index + 1,
            "priority_tier": row.get("priority_tier"),
            "condition_counts": {
                "passed": (candidate.get("conditions") or {}).get("passed"),
                "total": (candidate.get("conditions") or {}).get("total"),
                "missing": sort.get("missing"),
            },
            "risk_status": (candidate.get("risk") or {}).get("status"),
            "entry_basis": row.get("entry_gap_basis"),
            "sort_components": {
                "tier_order": order[0],
                "missing": order[1],
                "risk_quality": order[2],
                "entry_gap_missing": order[3],
                "entry_gap_pct": order[4],
                "negative_strategy_fit": order[5],
                "tie_focus_order": order[6],
                "code": order[7],
            },
            "tie_resolution": {
                "group": tie.get("group"),
                "size": tie.get("size"),
                "focus": tie.get("focus"),
                "focus_order": tie.get("focus_order"),
                "breaker": tie.get("breaker"),
                "structural_target_distance_pct": tie.get("structural_target_distance_pct"),
                "structural_target_basis": tie.get("structural_target_basis"),
            },
            "audit_payload_sha256": fingerprint,
            "source_paths": {
                "conditions": "candidate.conditions",
                "risk": "candidate.risk",
                "entry": "candidate.entry_risk_guide",
                "strategy_fit": "scanner.reproducibility_audit.candidates[].strategy_fit_score",
                "ranking": "scanner.reproducibility_audit.candidates[].final_sort_key",
            },
            "historical_evidence_used_in_rank": False,
        })
    return projection or None
