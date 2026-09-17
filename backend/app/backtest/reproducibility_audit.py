from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app.backtest.candidate_priority import build_candidate_priority, priority_sort_key


AUDIT_VERSION = "v0.21.4-B.2.3.4a"
KST = timezone(timedelta(hours=9), name="KST")


def _sanitize_label(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip()).strip("-_")
    return cleaned[:32].lower()


def _machine_fingerprint() -> str:
    # Do not persist the raw hostname. The short hash is enough to tell two PCs apart.
    raw = socket.gethostname().encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:12]


def resolve_machine_identity(runtime_root: Path) -> dict[str, str]:
    fingerprint = _machine_fingerprint()
    env_label = _sanitize_label(os.getenv("STOCKSCOPE_REPRO_MACHINE", ""))
    if env_label:
        return {
            "label": env_label,
            "label_source": "environment",
            "fingerprint": fingerprint,
        }

    label_path = runtime_root / "machine_label.txt"
    try:
        file_label = _sanitize_label(label_path.read_text(encoding="utf-8")) if label_path.exists() else ""
    except OSError:
        file_label = ""
    if file_label:
        return {
            "label": file_label,
            "label_source": "machine_label_file",
            "fingerprint": fingerprint,
        }

    return {
        "label": f"pc-{fingerprint[:8]}",
        "label_source": "hashed_hostname_fallback",
        "fingerprint": fingerprint,
    }


def _find_git_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_command(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def git_metadata(project_root_hint: Path) -> dict[str, Any]:
    root = _find_git_root(project_root_hint)
    if root is None:
        return {"available": False, "commit": None, "branch": None, "dirty": None, "dirty_scope": "tracked_files_only"}

    commit = _git_command(root, "rev-parse", "HEAD")
    branch = _git_command(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git_command(root, "status", "--porcelain", "--untracked-files=no")
    return {
        "available": commit is not None,
        "commit": commit,
        "branch": branch,
        "dirty": None if status is None else bool(status),
        "dirty_scope": "tracked_files_only",
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _candidate_history_hash(series: Any) -> dict[str, Any]:
    rows = getattr(series, "rows", {}) or {}
    hasher = hashlib.sha256()
    for bas_dd in sorted(rows):
        row = rows[bas_dd]
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        hasher.update(f"{bas_dd}|{payload}\n".encode("utf-8"))
    checked_dates = sorted(getattr(series, "checked_dates", set()) or set())
    checked_hasher = hashlib.sha256("\n".join(checked_dates).encode("utf-8"))
    return {
        "row_count": len(rows),
        "row_hash": hasher.hexdigest(),
        "checked_date_count": len(checked_dates),
        "checked_dates_hash": checked_hasher.hexdigest(),
    }


def _historical_snapshot(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = candidate.get("historical_evidence") or {}
    fit = candidate.get("historical_fit") or {}
    return {
        "status": evidence.get("status") or fit.get("status"),
        "verified": evidence.get("verified") if evidence else fit.get("verified"),
        "trades": evidence.get("sample_count") if evidence.get("sample_count") is not None else fit.get("trades"),
        "average_net_return_pct": evidence.get("average_net_return_pct"),
        "expectancy_pct": evidence.get("expectancy_pct"),
        "profit_factor": evidence.get("profit_factor"),
        "max_drawdown_pct": evidence.get("max_drawdown_pct"),
        "sample_sufficient": evidence.get("sample_sufficient"),
    }


def _candidate_snapshot(candidate: dict[str, Any], rank: int) -> dict[str, Any]:
    diagnostic_priority = build_candidate_priority(candidate)
    candidate_for_sort = dict(candidate)
    candidate_for_sort["priority"] = diagnostic_priority
    sort_key = list(priority_sort_key(candidate_for_sort))
    priority_public = dict(diagnostic_priority)
    priority_sort = priority_public.pop("_sort", {})

    guide = candidate.get("entry_risk_guide") or {}
    risk_plan = guide.get("risk") or {}
    price_rule = guide.get("price_rule") or {}
    rebound_rule = guide.get("rebound_rule") or {}

    return {
        "rank": rank,
        "code": str(candidate.get("code") or ""),
        "name": str(candidate.get("name") or ""),
        "market": str(candidate.get("market") or ""),
        "data_date": candidate.get("data_date"),
        "current_price": candidate.get("current_price"),
        "candidate_state": candidate.get("candidate_state"),
        "candidate_label": candidate.get("candidate_label"),
        "strategy": candidate.get("strategy"),
        "action": candidate.get("action"),
        "conditions": _json_safe(candidate.get("conditions") or {}),
        "risk": _json_safe(candidate.get("risk") or {}),
        "historical": _historical_snapshot(candidate),
        "strategy_fit_score": candidate.get("_strategy_fit_score"),
        "internal_rank": candidate.get("internal_rank"),
        "scanner_inputs": {
            "trade_value": candidate.get("_repro_trade_value"),
            "market_cap": candidate.get("_repro_market_cap"),
            "history_points": candidate.get("_repro_history_points"),
            "condition_details": _json_safe(candidate.get("_repro_condition_details") or []),
            "volume_rule": _json_safe(guide.get("volume_rule") or {}),
            "trend_strength": _json_safe(guide.get("trend_strength") or {}),
        },
        "entry_gap_pct": priority_public.get("entry_gap_pct"),
        "entry_gap_basis": priority_public.get("entry_gap_basis"),
        "priority_tier": priority_public.get("tier"),
        "priority_sort_components": _json_safe(priority_sort),
        "final_sort_key": _json_safe(sort_key),
        "price_plan": {
            "entry_reference_price": risk_plan.get("entry_reference_price"),
            "invalidation_price": risk_plan.get("invalidation_price"),
            "stop_zone_low": risk_plan.get("stop_zone_low"),
            "stop_zone_high": risk_plan.get("stop_zone_high"),
            "target1_price": risk_plan.get("target1_price"),
            "target1_basis": risk_plan.get("target1_basis"),
            "target2_price": risk_plan.get("target2_price"),
            "target2_basis": risk_plan.get("target2_basis"),
            "rr1": risk_plan.get("rr1"),
            "rr2": risk_plan.get("rr2"),
        },
        "entry_rule": {
            "kind": price_rule.get("kind"),
            "label": price_rule.get("label"),
            "gap_pct": price_rule.get("gap_pct"),
            "range_low": price_rule.get("range_low"),
            "range_high": price_rule.get("range_high"),
            "trigger_price": rebound_rule.get("trigger_price"),
            "rebound_gap_pct": rebound_rule.get("gap_pct"),
        },
    }


def build_scanner_reproducibility_payload(
    *,
    market_store: Any,
    scanner_version: str,
    market_scope: str,
    analysis_date: date,
    history_start: date,
    candidate_history_start: date,
    markets: Iterable[str],
    latest_dates: dict[str, str],
    ranked_candidates: list[dict[str, Any]],
    input_fingerprint: dict[str, Any] | None,
    ranking_changes: list[dict[str, Any]] | None,
    result_source: str,
    candidate_pool_complete: bool,
    project_root_hint: Path,
    runtime_root: Path,
) -> dict[str, Any]:
    generated = datetime.now(KST)
    machine = resolve_machine_identity(runtime_root)
    expected_dates = []
    cursor = history_start
    while cursor <= analysis_date:
        if cursor.weekday() < 5:
            expected_dates.append(cursor.strftime("%Y%m%d"))
        cursor = date.fromordinal(cursor.toordinal() + 1)

    market_snapshots: dict[str, Any] = {}
    combined = hashlib.sha256()
    for market in markets:
        snapshot = market_store.reproducibility_snapshot(
            market,
            history_start.strftime("%Y%m%d"),
            analysis_date.strftime("%Y%m%d"),
            expected_dates=expected_dates,
        )
        market_snapshots[market] = snapshot
        combined.update(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )

    candidate_codes_by_market: dict[str, list[str]] = {}
    for candidate in ranked_candidates:
        market = str(candidate.get("market") or "")
        code = str(candidate.get("code") or "")
        if market and code:
            candidate_codes_by_market.setdefault(market, []).append(code)

    candidate_input_hashes: dict[str, Any] = {}
    for market, codes in candidate_codes_by_market.items():
        series_map = market_store.stock_series_many(
            market,
            sorted(set(codes)),
            candidate_history_start.strftime("%Y%m%d"),
            analysis_date.strftime("%Y%m%d"),
        )
        for code, series in series_map.items():
            candidate_input_hashes[f"{market}:{code}"] = _candidate_history_hash(series)

    return {
        "audit_version": AUDIT_VERSION,
        "machine": machine,
        "generated_at": generated.isoformat(timespec="seconds"),
        "analysis_date": analysis_date.isoformat(),
        "history_start": history_start.isoformat(),
        "candidate_history_start": candidate_history_start.isoformat(),
        "market_scope": market_scope,
        "scanner_version": scanner_version,
        "result_source": result_source,
        "candidate_pool_complete": bool(candidate_pool_complete),
        "git": git_metadata(project_root_hint),
        "latest_dates": _json_safe(latest_dates),
        "existing_latest_day_fingerprint": _json_safe(input_fingerprint or {}),
        "history_fingerprint": {
            "combined_sha256": combined.hexdigest(),
            "markets": market_snapshots,
            "candidate_series": candidate_input_hashes,
        },
        "candidate_count": len(ranked_candidates),
        "candidates": [
            _candidate_snapshot(candidate, rank)
            for rank, candidate in enumerate(ranked_candidates, start=1)
        ],
        "ranking_changes": _json_safe(ranking_changes or []),
    }


def write_scanner_reproducibility_audit(
    *,
    market_store: Any,
    scanner_version: str,
    market_scope: str,
    analysis_date: date,
    history_start: date,
    candidate_history_start: date,
    markets: Iterable[str],
    latest_dates: dict[str, str],
    ranked_candidates: list[dict[str, Any]],
    input_fingerprint: dict[str, Any] | None,
    ranking_changes: list[dict[str, Any]] | None,
    result_source: str,
    candidate_pool_complete: bool,
    project_root_hint: Path,
    output_root: Path | None = None,
) -> dict[str, Any]:
    identity_root = Path(__file__).resolve().parents[2] / "runtime" / "reproducibility"
    artifact_root = output_root or (project_root_hint / "scanner-repro")
    try:
        identity_root.mkdir(parents=True, exist_ok=True)
        artifact_root.mkdir(parents=True, exist_ok=True)
        payload = build_scanner_reproducibility_payload(
            market_store=market_store,
            scanner_version=scanner_version,
            market_scope=market_scope,
            analysis_date=analysis_date,
            history_start=history_start,
            candidate_history_start=candidate_history_start,
            markets=markets,
            latest_dates=latest_dates,
            ranked_candidates=ranked_candidates,
            input_fingerprint=input_fingerprint,
            ranking_changes=ranking_changes,
            result_source=result_source,
            candidate_pool_complete=candidate_pool_complete,
            project_root_hint=project_root_hint,
            runtime_root=identity_root,
        )
        generated = datetime.fromisoformat(str(payload["generated_at"]))
        machine_label = _sanitize_label(str((payload.get("machine") or {}).get("label") or "unknown")) or "unknown"
        filename = (
            f"scanner-repro_{machine_label}_{generated.strftime('%Y%m%d-%H%M%S')}"
            f"_analysis-{analysis_date.strftime('%Y%m%d')}.json"
        )
        path = artifact_root / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "written": True,
            "path": str(path),
            "filename": filename,
            "machine_label": machine_label,
            "machine_fingerprint": str((payload.get("machine") or {}).get("fingerprint") or ""),
            "analysis_date": analysis_date.isoformat(),
            "candidate_count": len(ranked_candidates),
            "result_source": result_source,
        }
    except Exception as exc:  # diagnostic output must never break Scanner analysis
        return {
            "written": False,
            "error": f"{type(exc).__name__}: {exc}",
            "analysis_date": analysis_date.isoformat(),
            "result_source": result_source,
        }
