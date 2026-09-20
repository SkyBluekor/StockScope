from __future__ import annotations

import ast
import asyncio
import hashlib
import copy
import csv
import inspect
import json
import math
import re
import time
from dataclasses import is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from app.backtest.candidate_priority import rank_candidates
from app.backtest.scanner_quality.early_pruning_audit import (
    _candidate_snapshot,
    _compact,
    _float,
    _future_metrics,
    _mean,
    _median,
    _row_date,
    _safe_json,
    _trimmed_mean,
)
from app.backtest.scanner_quality.models import AuditHorizons

KST = timezone(timedelta(hours=9), name="KST")
AUDIT_VERSION = "v0.21.4-B.2.3.4c.4g"
BASELINE = "BASELINE"
MA120_FIXED = "MA120_FIXED_AUDIT"
MA120_INPUT_ONLY = "MA120_INPUT_ONLY"
# Legacy name kept only for import compatibility with c.4 tests/tools.
RS_DEDUP = "RS_DEDUP_AUDIT"
RS_KEEP_4 = "RS_KEEP_4"
RS_KEEP_8 = "RS_KEEP_8"
RS_RESTORE_10_8 = "RS_RESTORE_10_8"
RS_DEDUP_VARIANTS = (RS_KEEP_4, RS_KEEP_8)
RS_VARIANTS = (RS_KEEP_4, RS_KEEP_8, RS_RESTORE_10_8)
# Legacy c.4f.4 research variants retained for backward-compatible reports.
# c.4g Production itself is market 10 + sector 8; historical Sector input remains audit-only.
RS_AUDIT_CURRENT = "RS_PRODUCTION_10_8_SECTOR_AWARE"
RS_AUDIT_KEEP_4 = "RS_AUDIT_KEEP_4"
RS_AUDIT_KEEP_8 = "RS_AUDIT_KEEP_8"
RS_AUDIT_RESTORE_10_8 = "RS_AUDIT_RESTORE_10_8"
RS_AUDIT_DEDUP_VARIANTS = (RS_AUDIT_KEEP_4, RS_AUDIT_KEEP_8)
RS_AUDIT_VARIANTS = (RS_AUDIT_KEEP_4, RS_AUDIT_KEEP_8, RS_AUDIT_RESTORE_10_8)
RS_AUDIT_ALL_VARIANTS = (RS_AUDIT_CURRENT, *RS_AUDIT_VARIANTS)
RS_REMOVED_WEIGHT = {RS_KEEP_4: 8.0, RS_KEEP_8: 4.0, RS_RESTORE_10_8: 4.0}
RS_KEPT_WEIGHT = {RS_KEEP_4: 4.0, RS_KEEP_8: 8.0, RS_RESTORE_10_8: 8.0}
LEGACY_BASELINE_MARKET_RS_WEIGHT = 6.0
# Compatibility alias used only by legacy 6+4+8 counterfactual helpers.
BASELINE_MARKET_RS_WEIGHT = LEGACY_BASELINE_MARKET_RS_WEIGHT
PRODUCTION_MARKET_RS_WEIGHT = 10.0
RESTORED_MARKET_RS_WEIGHT = 10.0
BREAKOUT_RS_CONDITION = "20일 업종 대비 상대강도 양호"
EXPECTED_BREAKOUT_RS_WEIGHTS = (8.0,)
LEGACY_BREAKOUT_RS_WEIGHTS = (4.0, 8.0)
MA120_CONDITION = "60일선이 120일선 위"


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 4) if denominator else None


def _num(value: Any) -> float | None:
    value = _float(value)
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def _same_number(left: Any, right: Any, *, tol: float = 1e-9) -> bool:
    lval = _num(left)
    rval = _num(right)
    if lval is None or rval is None:
        return False
    return math.isclose(lval, rval, rel_tol=1e-9, abs_tol=tol)


def _run_async(coro: Any) -> Any:
    """Run one audit prefetch coroutine from the synchronous audit runner."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("StrategyIntegrityAuditor.run_date() cannot live-prefetch Sector RS inside an active event loop")


def _strategy_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _evaluation_name(evaluation: Any) -> str:
    return _strategy_name(getattr(evaluation, "strategy", ""))


def _evaluation_conditions(evaluation: Any) -> tuple[list[str], list[str]]:
    return (
        [str(item) for item in (getattr(evaluation, "reasons", None) or [])],
        [str(item) for item in (getattr(evaluation, "unmet", None) or [])],
    )


def _evaluation_map(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "evaluations" in value and isinstance(value.get("evaluations"), dict):
            value = value["evaluations"]
        result: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                continue
            name = _evaluation_name(item) or _strategy_name(key)
            if name:
                result[name] = item
        return result or None
    if isinstance(value, (list, tuple, set)):
        result = {_evaluation_name(item): item for item in value if item is not None and _evaluation_name(item)}
        return result or None
    evaluations = getattr(value, "evaluations", None)
    if evaluations is not None:
        return _evaluation_map(evaluations)
    return None


def _find_eval(evaluations: dict[str, Any], name: str) -> Any | None:
    wanted = str(name)
    for key, evaluation in evaluations.items():
        if _strategy_name(key) == wanted or _evaluation_name(evaluation) == wanted:
            return evaluation
    return None


def _replace_input(data: Any, **changes: Any) -> Any | None:
    if data is None:
        return None
    if is_dataclass(data):
        try:
            return replace(data, **changes)
        except (TypeError, ValueError):
            return None
    cloned = copy.copy(data)
    try:
        for key, value in changes.items():
            setattr(cloned, key, value)
        return cloned
    except Exception:
        return None


def _clone_evaluation(evaluation: Any, **changes: Any) -> Any | None:
    if evaluation is None:
        return None
    if is_dataclass(evaluation):
        try:
            return replace(evaluation, **changes)
        except (TypeError, ValueError):
            pass
    cloned = copy.copy(evaluation)
    try:
        for key, value in changes.items():
            try:
                setattr(cloned, key, value)
            except Exception:
                object.__setattr__(cloned, key, value)
        return cloned
    except Exception:
        return None


def _sma(rows: list[dict[str, Any]], length: int) -> float | None:
    closes: list[float] = []
    for row in rows[-length:]:
        value = _num(row.get("close"))
        if value is None:
            return None
        closes.append(value)
    if len(closes) < length:
        return None
    return sum(closes) / length


def _formula_matches(data: Any, rows: list[dict[str, Any]]) -> bool | None:
    checks = []
    for field, length in (("ma20", 20), ("ma60", 60)):
        actual = _num(getattr(data, field, None))
        expected = _sma(rows, length)
        if actual is None or expected is None:
            continue
        tolerance = max(1e-6, abs(expected) * 1e-6)
        checks.append(math.isclose(actual, expected, rel_tol=1e-6, abs_tol=tolerance))
    return all(checks) if checks else None


def _metric_key_for_condition(condition: str, data: Any, technical: dict[str, Any]) -> str | None:
    try:
        from app.backtest.selector import plain_condition

        return (plain_condition(condition, data=data, technical=technical) or {}).get("metric_key")
    except Exception:
        text = condition.lower()
        if "업종" in condition and "상대강도" in condition:
            return "relative_strength_sector"
        if "시장" in condition and "상대강도" in condition:
            return "relative_strength_market"
        if "120일" in condition:
            return "ma60_vs_ma120"
        return None


def _source_tree(scanner: Any) -> list[Path]:
    try:
        scanner_file = Path(inspect.getfile(scanner.__class__)).resolve()
        app_root = next(parent for parent in scanner_file.parents if parent.name == "app")
    except Exception:
        return []
    candidates: list[Path] = []
    for path in (app_root / "strategy", app_root / "backtest" / "engine.py", app_root / "backtest" / "selector.py", app_root / "backtest" / "scanner.py"):
        if path.is_dir():
            candidates.extend(sorted(path.rglob("*.py")))
        elif path.is_file():
            candidates.append(path)
    return candidates


def _line_window(lines: list[str], index: int, radius: int = 3) -> str:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return "\n".join(f"{line_no + 1}: {lines[line_no]}" for line_no in range(start, end))


def _numeric_candidates_from_line(line: str) -> list[float]:
    values: list[float] = []
    for raw in re.findall(r"(?<![A-Za-z_])(-?\d+(?:\.\d+)?)", line):
        try:
            value = float(raw)
        except ValueError:
            continue
        if 0 < value <= 30:
            values.append(value)
    return values


def _ast_number(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)):
        return -float(node.operand.value)
    return None


def _breakout_rs_definition_from_source(path: Path) -> dict[str, Any] | None:
    """Read Breakout market/sector RS tuples from strategy/engine.py.

    c.4a scoped duplicate extraction to the exact sector label. c.4c keeps that
    guarantee and additionally records the market-RS tuple so the 6+4+8 -> 10+8
    counterfactual can fail fast when Production structure differs.
    """
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None

    breakout: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_breakout":
            breakout = node
            break
    if breakout is None:
        return None

    all_entries: list[dict[str, Any]] = []
    for node in ast.walk(breakout):
        if not isinstance(node, ast.Tuple) or len(node.elts) < 3:
            continue
        label_node, weight_node, predicate_node = node.elts[0], node.elts[1], node.elts[2]
        if not isinstance(label_node, ast.Constant) or not isinstance(label_node.value, str):
            continue
        label = str(label_node.value)
        if "상대강도" not in label:
            continue
        weight = _ast_number(weight_node)
        if weight is None:
            continue
        all_entries.append({
            "label": label,
            "weight": float(weight),
            "line": int(getattr(node, "lineno", 0) or 0),
            "predicate_ast": ast.dump(predicate_node, annotate_fields=True, include_attributes=False),
            "predicate_source": (ast.get_source_segment(text, predicate_node) or "").strip(),
        })

    sector_entries = [item for item in all_entries if item["label"] == BREAKOUT_RS_CONDITION]
    market_entries = [item for item in all_entries if "시장" in item["label"]]
    sector_entries.sort(key=lambda item: (int(item.get("line") or 0), float(item.get("weight") or 0.0)))
    market_entries.sort(key=lambda item: (int(item.get("line") or 0), float(item.get("weight") or 0.0)))
    predicate_dumps = [str(item.get("predicate_ast") or "") for item in sector_entries]
    return {
        "source_file": str(path),
        "condition_label": BREAKOUT_RS_CONDITION,
        "duplicate_count": len(sector_entries),
        "weights": [float(item["weight"]) for item in sector_entries],
        "predicate_equivalent": bool(sector_entries) and len(set(predicate_dumps)) == 1,
        "entries": sector_entries,
        "market_entries": market_entries,
        "market_weights": [float(item["weight"]) for item in market_entries],
        "market_condition_labels": [str(item["label"]) for item in market_entries],
        "all_rs_entries": all_entries,
    }


def _eligible_threshold_from_source(path: Path) -> float | None:
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "_evaluate":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Compare) or len(child.ops) != 1 or len(child.comparators) != 1:
                continue
            names = {item.id for item in ast.walk(child.left) if isinstance(item, ast.Name)}
            if "score" not in names:
                continue
            threshold = _ast_number(child.comparators[0])
            if threshold is None:
                continue
            if isinstance(child.ops[0], (ast.GtE, ast.Gt)) and 0 <= threshold <= 100:
                return float(threshold)
    return None


def _validate_breakout_rs_definition(report: dict[str, Any], *, allow_legacy_fixture: bool = False) -> str:
    """Validate the c.4g Production Breakout RS definition.

    Real Production must be market 10 + exactly one sector 8.  The old 6+4+8
    shape is accepted only for the dedicated in-memory audit fixture so legacy
    counterfactual unit tests remain useful without weakening the Production gate.
    """
    definition = report.get("breakout_rs_definition") or {}
    weights = tuple(sorted(float(value) for value in (definition.get("weights") or [])))
    count = int(definition.get("duplicate_count") or 0)
    equivalent = bool(definition.get("predicate_equivalent"))
    label = str(definition.get("condition_label") or "")
    market_weights = tuple(sorted(float(value) for value in (definition.get("market_weights") or [])))

    production_ok = (
        count == 1
        and weights == EXPECTED_BREAKOUT_RS_WEIGHTS
        and market_weights == (PRODUCTION_MARKET_RS_WEIGHT,)
        and label == BREAKOUT_RS_CONDITION
        and equivalent
    )
    if production_ok:
        return "PRODUCTION_10_8"

    legacy_ok = (
        allow_legacy_fixture
        and count == 2
        and weights == LEGACY_BREAKOUT_RS_WEIGHTS
        and market_weights == (LEGACY_BASELINE_MARKET_RS_WEIGHT,)
        and label == BREAKOUT_RS_CONDITION
        and equivalent
    )
    if legacy_ok:
        return "LEGACY_6_4_8_FIXTURE"

    errors: list[str] = []
    if count != 1:
        errors.append(f"sector_condition_count={count}")
    if weights != EXPECTED_BREAKOUT_RS_WEIGHTS:
        errors.append(f"sector_weights={list(weights)}")
    if market_weights != (PRODUCTION_MARKET_RS_WEIGHT,):
        errors.append(f"market_weights={list(market_weights)}")
    if label != BREAKOUT_RS_CONDITION:
        errors.append(f"label={label!r}")
    if not equivalent:
        errors.append("predicate_equivalent=False")
    raise RuntimeError(
        "RS audit aborted: c.4g expects Production Breakout market 10 + exactly one sector 8 "
        f"condition; found {', '.join(errors)}"
    )

def inspect_strategy_sources(scanner: Any) -> dict[str, Any]:
    terms = [
        "_signal_snapshot",
        "ma120",
        MA120_CONDITION,
        "relative_strength_market_pct",
        "relative_strength_sector_pct",
        "20일 시장 대비 상대강도",
        "20일 업종 대비 상대강도",
        "breakout",
    ]
    hits: dict[str, list[dict[str, Any]]] = {term: [] for term in terms}
    condition_weights: dict[str, list[float]] = {}
    files = _source_tree(scanner)
    fallback_hits: list[dict[str, Any]] = []
    breakout_definition: dict[str, Any] | None = None
    eligible_threshold: float | None = None
    for path in files:
        if path.name == "engine.py" and path.parent.name == "strategy":
            breakout_definition = breakout_definition or _breakout_rs_definition_from_source(path)
            eligible_threshold = eligible_threshold if eligible_threshold is not None else _eligible_threshold_from_source(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for term in terms:
            for index, line in enumerate(lines):
                if term in line:
                    if len(hits[term]) < 20:
                        hits[term].append({
                            "file": str(path),
                            "line": index + 1,
                            "snippet": _line_window(lines, index),
                        })
                    if "상대강도" in term and "상대강도" in line:
                        condition_weights.setdefault(term, []).extend(_numeric_candidates_from_line(line))
        for index, line in enumerate(lines):
            if "relative_strength_sector_pct" in line:
                window = "\n".join(lines[max(0, index - 2): min(len(lines), index + 3)])
                if "relative_strength_market_pct" in window and (" or " in window or "if" in window or "else" in window or "None" in window):
                    fallback_hits.append({"file": str(path), "line": index + 1, "snippet": _line_window(lines, index)})

        # AST pass catches weights placed beside a condition string in tuples/calls/dicts.
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            strings = [child.value for child in ast.walk(node) if isinstance(child, ast.Constant) and isinstance(child.value, str)]
            relevant = [value for value in strings if "상대강도" in value]
            if not relevant:
                continue
            nums = [float(child.value) for child in ast.walk(node) if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)) and 0 < float(child.value) <= 30]
            if not nums:
                continue
            for condition in relevant:
                condition_weights.setdefault(condition, []).extend(nums[:8])

    signal_snapshot_source = ""
    signal_snapshot_window_candidates: list[int] = []
    try:
        engine = getattr(scanner, "engine", None)
        signal_snapshot_source = inspect.getsource(engine._signal_snapshot) if engine is not None else ""
    except Exception:
        signal_snapshot_source = ""
    if signal_snapshot_source:
        patterns = (
            r"\[-(\d+)\s*:\]",
            r"index\s*-\s*(\d+)",
            r"max\([^\n]{0,80}index\s*-\s*(\d+)",
            r"lookback\s*=\s*(\d+)",
            r"window\s*=\s*(\d+)",
        )
        for pattern in patterns:
            for raw in re.findall(pattern, signal_snapshot_source, flags=re.IGNORECASE):
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    continue
                if 20 <= value <= 1000:
                    signal_snapshot_window_candidates.append(value)

    clean_weights = {
        key: sorted({round(value, 6) for value in values})
        for key, values in condition_weights.items()
        if values
    }

    # Test/audit hook: production does not define this.  It lets fixtures provide
    # an exact source definition without creating a fake app/strategy tree.
    hook = getattr(scanner, "_strategy_integrity_audit_breakout_source", None)
    if callable(hook):
        supplied = hook()
        if supplied:
            breakout_definition = dict(supplied)
            eligible_threshold = _num(breakout_definition.get("eligible_score_threshold")) or eligible_threshold

    return {
        "files_scanned": len(files),
        "hits": hits,
        "condition_weight_candidates": clean_weights,  # legacy diagnostic only; c.4a never uses it for dedup weights
        "breakout_rs_definition": breakout_definition or {},
        "strategy_eligible_score_threshold": eligible_threshold,
        "sector_market_fallback_source_hits": fallback_hits[:20],
        "signal_snapshot_window_candidates": sorted(set(signal_snapshot_window_candidates)),
        "signal_snapshot_source_excerpt": signal_snapshot_source[:8000],
    }


def _discover_revaluator(scanner: Any, snapshot: dict[str, Any], patched_input: Any) -> tuple[dict[str, Any] | None, str | None]:
    hook = getattr(scanner, "_strategy_integrity_audit_revaluate", None)
    if callable(hook):
        try:
            result = hook(snapshot=snapshot, strategy_input=patched_input)
            mapped = _evaluation_map(result)
            if mapped:
                return mapped, "scanner_hook"
        except Exception:
            pass

    engine = getattr(scanner, "engine", None)
    candidates: list[tuple[Any, str]] = []
    if engine is not None:
        candidates.append((engine, "engine"))
        for name in dir(engine):
            if name.startswith("_"):
                continue
            if not any(token in name.lower() for token in ("strategy", "evaluat", "signal")):
                continue
            try:
                obj = getattr(engine, name)
            except Exception:
                continue
            if obj is not None and not inspect.ismodule(obj):
                candidates.append((obj, f"engine.{name}"))

    preferred = ("evaluate_all", "evaluate_strategies", "evaluate", "evaluate_all_strategies")
    seen: set[int] = set()
    for obj, label in candidates:
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        for method_name in preferred:
            method = getattr(obj, method_name, None)
            if not callable(method):
                continue
            try:
                signature = inspect.signature(method)
            except (TypeError, ValueError):
                continue
            required = [
                param for param in signature.parameters.values()
                if param.default is inspect.Parameter.empty
                and param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            # bound method should require exactly one StrategyInput-like argument.
            if len(required) > 1:
                continue
            try:
                result = method(patched_input)
            except Exception:
                continue
            mapped = _evaluation_map(result)
            if mapped and any(_evaluation_name(item) for item in mapped.values()):
                return mapped, f"{label}.{method_name}"

    # Last-resort: inspect _signal_snapshot source for self.<attr>.<method>(...) evaluator calls.
    try:
        source = inspect.getsource(engine._signal_snapshot) if engine is not None else ""
    except Exception:
        source = ""
    for attr, method_name in re.findall(r"self\.([A-Za-z_]\w*)\.([A-Za-z_]\w*)\(", source):
        if not any(token in (attr + method_name).lower() for token in ("strategy", "evaluat")):
            continue
        try:
            target = getattr(getattr(engine, attr), method_name)
            result = target(patched_input)
        except Exception:
            continue
        mapped = _evaluation_map(result)
        if mapped:
            return mapped, f"engine.{attr}.{method_name}"
    return None, None


def _dedup_exact_condition(
    evaluation: Any,
    condition: str,
    remove_weight: float | None,
    *,
    eligible_threshold: float | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    reasons, unmet = _evaluation_conditions(evaluation)
    reason_count = reasons.count(condition)
    unmet_count = unmet.count(condition)
    if max(reason_count, unmet_count) < 2:
        return None, {"applied": False, "reason": "no_exact_duplicate"}

    passed_removed = reason_count >= 2
    target = reasons if passed_removed else unmet
    removed = False
    new_target: list[str] = []
    for item in target:
        if item == condition and not removed:
            removed = True
            continue
        new_target.append(item)
    new_reasons = new_target if passed_removed else reasons
    new_unmet = unmet if passed_removed else new_target

    score = _num(getattr(evaluation, "score", None))
    new_score: Any = getattr(evaluation, "score", None)
    if passed_removed and score is not None and remove_weight is not None:
        new_score = max(0.0, score - float(remove_weight))
        if isinstance(getattr(evaluation, "score", None), int):
            new_score = int(round(new_score))
    passed = int(getattr(evaluation, "passed", len(reasons)) or 0)
    total = int(getattr(evaluation, "total", len(reasons) + len(unmet)) or 0)
    changes = {
        "reasons": new_reasons,
        "unmet": new_unmet,
        "passed": max(0, passed - (1 if passed_removed else 0)),
        "total": max(0, total - 1),
        "score": new_score,
    }
    if eligible_threshold is not None and hasattr(evaluation, "eligible") and _num(new_score) is not None:
        changes["eligible"] = bool(float(_num(new_score)) >= float(eligible_threshold))
    cloned = _clone_evaluation(evaluation, **changes)
    return cloned, {
        "applied": cloned is not None,
        "passed_duplicate_removed": passed_removed,
        "remove_weight": remove_weight,
        "original_score": score,
        "new_score": _num(new_score),
        "eligible_threshold": eligible_threshold,
        "new_eligible": getattr(cloned, "eligible", None) if cloned is not None else None,
    }


def _remove_condition_once(evaluation: Any, condition: str, remove_weight: float | None) -> tuple[Any | None, dict[str, Any]]:
    reasons, unmet = _evaluation_conditions(evaluation)
    if condition not in reasons and condition not in unmet:
        return None, {"applied": False, "reason": "condition_not_present"}
    passed_removed = condition in reasons
    target = reasons if passed_removed else unmet
    removed = False
    new_target: list[str] = []
    for item in target:
        if item == condition and not removed:
            removed = True
            continue
        new_target.append(item)
    new_reasons = new_target if passed_removed else reasons
    new_unmet = unmet if passed_removed else new_target
    score = _num(getattr(evaluation, "score", None))
    new_score: Any = getattr(evaluation, "score", None)
    if passed_removed and score is not None and remove_weight is not None:
        new_score = max(0.0, score - float(remove_weight))
        if isinstance(getattr(evaluation, "score", None), int):
            new_score = int(round(new_score))
    passed = int(getattr(evaluation, "passed", len(reasons)) or 0)
    total = int(getattr(evaluation, "total", len(reasons) + len(unmet)) or 0)
    cloned = _clone_evaluation(
        evaluation,
        reasons=new_reasons,
        unmet=new_unmet,
        passed=max(0, passed - (1 if passed_removed else 0)),
        total=max(0, total - 1),
        score=new_score,
    )
    return cloned, {
        "applied": cloned is not None,
        "passed_condition_removed": passed_removed,
        "remove_weight": remove_weight,
        "original_score": score,
        "new_score": _num(new_score),
    }


def _market_rs_condition(evaluation: Any) -> str | None:
    reasons, unmet = _evaluation_conditions(evaluation)
    for condition in reasons + unmet:
        if "시장" in condition and "상대강도" in condition:
            return condition
    return None


def _restore_breakout_evaluation(
    evaluation: Any,
    *,
    relative_strength_market_pct: Any,
    relative_strength_sector_pct: Any,
    eligible_threshold: float | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    """Rebuild the audit-only Breakout RS structure from 6+4+8 to 10+8.

    This is not a Production mutation. It updates score, reasons/unmet, passed,
    total and eligibility together. The sector predicate preserves current
    fallback semantics: missing sector RS uses market RS.
    """
    reasons, unmet = _evaluation_conditions(evaluation)
    sector_occurrences = reasons.count(BREAKOUT_RS_CONDITION) + unmet.count(BREAKOUT_RS_CONDITION)
    if sector_occurrences < 2:
        return None, {"applied": False, "reason": "sector_duplicate_not_present"}

    # Remove one sector condition (the historical accidental weight-4 entry).
    reduced, remove_meta = _remove_condition_once(evaluation, BREAKOUT_RS_CONDITION, 4.0)
    if reduced is None:
        return None, {"applied": False, "reason": "sector_remove_failed"}

    market_value = _num(relative_strength_market_pct)
    sector_value = _num(relative_strength_sector_pct)
    market_pass = market_value is not None and market_value > 0
    sector_effective = sector_value if sector_value is not None else market_value
    sector_pass = sector_effective is not None and sector_effective > 0

    reduced_score = _num(getattr(reduced, "score", None))
    restored_score: Any = getattr(reduced, "score", None)
    if reduced_score is not None and market_pass:
        restored_score = reduced_score + (RESTORED_MARKET_RS_WEIGHT - BASELINE_MARKET_RS_WEIGHT)
        if isinstance(getattr(evaluation, "score", None), int):
            restored_score = int(round(restored_score))

    changes: dict[str, Any] = {"score": restored_score}
    if eligible_threshold is not None and hasattr(reduced, "eligible") and _num(restored_score) is not None:
        changes["eligible"] = bool(float(_num(restored_score)) >= float(eligible_threshold))
    restored = _clone_evaluation(reduced, **changes)
    return restored, {
        "applied": restored is not None,
        "removed_weight": 4.0,
        "baseline_market_weight": BASELINE_MARKET_RS_WEIGHT,
        "restored_market_weight": RESTORED_MARKET_RS_WEIGHT,
        "market_pass": market_pass,
        "sector_pass": sector_pass,
        "sector_fallback_used": sector_value is None,
        "original_score": _num(getattr(evaluation, "score", None)),
        "new_score": _num(getattr(restored, "score", None)) if restored is not None else None,
        "original_passed": int(getattr(evaluation, "passed", len(reasons)) or 0),
        "new_passed": int(getattr(restored, "passed", 0) or 0) if restored is not None else None,
        "original_total": int(getattr(evaluation, "total", len(reasons) + len(unmet)) or 0),
        "new_total": int(getattr(restored, "total", 0) or 0) if restored is not None else None,
        "eligible_threshold": eligible_threshold,
        "new_eligible": getattr(restored, "eligible", None) if restored is not None else None,
        "condition_count_changed": restored is not None and int(getattr(restored, "total", 0) or 0) != int(getattr(evaluation, "total", 0) or 0),
        "removed_condition_passed": bool(remove_meta.get("passed_condition_removed")),
    }


def _ordered_keys(items: Iterable[dict[str, Any]], *, limit: int | None = None) -> list[str]:
    values = list(items)
    if limit is not None:
        values = values[:limit]
    return [f"{_candidate_key(item)[0]}:{_candidate_key(item)[1]}" for item in values]


def _sequence_comparison(baseline: list[str], variant: list[str], *, prefix: str) -> dict[str, Any]:
    base_set = set(baseline)
    var_set = set(variant)
    membership_changed = base_set != var_set
    order_changed = baseline != variant
    replacements = max(len(var_set - base_set), len(base_set - var_set))
    return {
        f"{prefix}_membership_changed": membership_changed,
        f"{prefix}_membership_replacements": replacements,
        f"{prefix}_membership_added": sorted(var_set - base_set),
        f"{prefix}_membership_removed": sorted(base_set - var_set),
        f"{prefix}_order_changed": order_changed,
        f"{prefix}_order_only_changed": bool(order_changed and not membership_changed),
        f"{prefix}_baseline_order": list(baseline),
        f"{prefix}_variant_order": list(variant),
    }



def _sector_aware_rs_matrix() -> list[dict[str, Any]]:
    """Deterministic structural comparison for market/sector sign combinations."""
    cases = [
        ("MARKET_POS_SECTOR_POS", 1.0, 1.0),
        ("MARKET_POS_SECTOR_NEG", 1.0, -1.0),
        ("MARKET_NEG_SECTOR_POS", -1.0, 1.0),
        ("MARKET_NEG_SECTOR_NEG", -1.0, -1.0),
        ("MARKET_POS_SECTOR_MISSING", 1.0, None),
        ("MARKET_NEG_SECTOR_MISSING", -1.0, None),
    ]
    rows: list[dict[str, Any]] = []
    for name, market, sector in cases:
        market_pass = market > 0
        effective_sector = market if sector is None else sector
        sector_pass = effective_sector > 0
        baseline_score = (6 if market_pass else 0) + (4 if sector_pass else 0) + (8 if sector_pass else 0)
        restore_score = (10 if market_pass else 0) + (8 if sector_pass else 0)
        baseline_passed = int(market_pass) + int(sector_pass) * 2
        restore_passed = int(market_pass) + int(sector_pass)
        rows.append({
            "case": name,
            "market_value": market,
            "sector_value": sector,
            "sector_fallback": sector is None,
            "baseline_score": baseline_score,
            "restore_score": restore_score,
            "score_delta": restore_score - baseline_score,
            "baseline_passed": baseline_passed,
            "baseline_total": 3,
            "restore_passed": restore_passed,
            "restore_total": 2,
            "score_changed": baseline_score != restore_score,
            "condition_count_changed": True,
        })
    return rows

def audit_code_fingerprint(project_root: Path) -> dict[str, Any]:
    """Fingerprint the audit and decision-path source actually used by this run."""
    candidates = [
        "backend/app/backtest/scanner_quality/strategy_integrity_audit.py",
        "backend/tools/run_scanner_strategy_integrity_audit.py",
        "backend/app/backtest/scanner_quality/early_pruning_audit.py",
        "backend/app/backtest/candidate_priority.py",
        "backend/app/backtest/scanner.py",
        "backend/app/strategy/engine.py",
    ]
    files: dict[str, str] = {}
    digest = hashlib.sha256()
    for rel in candidates:
        path = project_root / rel
        if not path.exists() or not path.is_file():
            continue
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        files[rel] = sha
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha.encode("ascii"))
        digest.update(b"\n")
    return {"sha256": digest.hexdigest() if files else None, "files": files}


def _candidate_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("market") or ""), str(item.get("code") or "")


def _status(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    return str(candidate.get("candidate_state") or candidate.get("action") or "") or None


def _risk(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    return str((candidate.get("risk") or {}).get("status") or "") or None


def _forward(candidate: dict[str, Any] | None, horizon: int) -> dict[str, Any]:
    if not candidate:
        return {}
    return (((candidate.get("outcome") or {}).get("forward") or {}).get(str(horizon)) or {})


def _delta(left: Any, right: Any) -> float | None:
    lval = _num(left)
    rval = _num(right)
    if lval is None or rval is None:
        return None
    return round(lval - rval, 6)


class StrategyIntegrityAuditor:
    """Audit strategy-definition integrity without mutating production strategy code."""

    def __init__(self, scanner: Any, market_store: Any) -> None:
        self.scanner = scanner
        self.market_store = market_store
        self.source_report = inspect_strategy_sources(scanner)
        # Only the dedicated unit-test fixture may retain the legacy 6+4+8 shape.
        # Real Scanner versions must satisfy the c.4g Production 10+8 definition.
        allow_legacy_fixture = str(getattr(scanner, "VERSION", "")) == "test"
        self.breakout_definition_mode = _validate_breakout_rs_definition(
            self.source_report, allow_legacy_fixture=allow_legacy_fixture
        )
        definition = self.source_report.get("breakout_rs_definition") or {}
        self.breakout_rs_weights = tuple(sorted(float(value) for value in (definition.get("weights") or [])))
        self.eligible_score_threshold = _num(self.source_report.get("strategy_eligible_score_threshold"))

    @staticmethod
    def _markets(scope: str) -> list[str]:
        normalized = scope.upper().strip()
        if normalized == "ALL":
            return ["KOSPI", "KOSDAQ"]
        if normalized in {"KOSPI", "KOSDAQ"}:
            return [normalized]
        raise ValueError("market_scope은 ALL, KOSPI, KOSDAQ 중 하나여야 합니다.")

    def _exact_day_available(self, markets: list[str], as_of: date) -> bool:
        key = _compact(as_of)
        return all(
            self.market_store.latest_complete_date(market, "stock", key) == key
            and self.market_store.latest_complete_date(market, "index", key) == key
            for market in markets
        )

    def _quick_from_snapshot(
        self,
        *,
        snapshot: dict[str, Any],
        market: str,
        latest_date: str,
        row: dict[str, Any],
        strategy_limit: int = 3,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        hook = getattr(self.scanner, "_strategy_integrity_audit_quick_from_snapshot", None)
        if callable(hook):
            return hook(snapshot=snapshot, market=market, latest_date=latest_date, row=row, strategy_limit=strategy_limit)

        from app.backtest.entry_risk_guide import build_entry_risk_guide
        from app.backtest.selector import build_condition_state, current_readiness, strategy_guide

        evaluations = list((snapshot.get("evaluations") or {}).values())
        evaluations.sort(
            key=lambda item: (bool(getattr(item, "eligible", False)), int(getattr(item, "score", 0) or 0)),
            reverse=True,
        )
        chosen = evaluations[: max(0, min(int(strategy_limit), len(evaluations)))]
        trace: list[dict[str, Any]] = []
        trace_map: dict[str, dict[str, Any]] = {}
        for rank, evaluation in enumerate(evaluations, start=1):
            name = _evaluation_name(evaluation)
            record = {
                "initial_rank": rank,
                "strategy": name,
                "initial_score": _num(getattr(evaluation, "score", None)),
                "eligible": bool(getattr(evaluation, "eligible", False)),
                "current_evaluated": rank <= strategy_limit,
            }
            trace.append(record)
            trace_map[name] = record

        best: dict[str, Any] | None = None
        for evaluation in chosen:
            strategy = evaluation.strategy
            strategy_name = _evaluation_name(evaluation)
            condition_state = build_condition_state(
                evaluation,
                data=snapshot.get("strategy_input"),
                technical=snapshot.get("technical") or {},
            )
            risk_plan = self.scanner.multi._current_risk_plan(snapshot, strategy)  # noqa: SLF001
            current = current_readiness(evaluation=evaluation, risk_plan=risk_plan, condition_state=condition_state)
            record = trace_map.get(strategy_name)
            if record is not None:
                record.update({
                    "current_internal_score": _num(current.get("internal_score")),
                    "status": current.get("status"),
                    "passed": int(current.get("passed") or 0),
                    "total": int(current.get("total") or 0),
                    "missing": int(current.get("missing") or 0),
                    "risk_warning": bool(current.get("risk_warning")),
                })
            if best is None or float(current.get("internal_score") or 0.0) > float(best["current"].get("internal_score") or 0.0):
                best = {
                    "strategy": strategy_name,
                    "strategy_obj": strategy,
                    "guide": strategy_guide(strategy),
                    "current": current,
                    "condition_state": condition_state,
                    "risk_plan": risk_plan,
                    "strategy_input": snapshot.get("strategy_input"),
                    "technical": snapshot.get("technical") or {},
                    "entry_timing": snapshot.get("entry_timing") or None,
                }
        if best is None:
            return None, trace
        current = best["current"]
        total = int(current.get("total") or 0)
        passed = int(current.get("passed") or 0)
        ratio = passed / total if total else 0.0
        risk_penalty = 18.0 if current.get("risk_warning") else 0.0
        quick_score = float(current.get("internal_score") or 0.0) + ratio * 20.0 - risk_penalty
        entry_risk_guide = build_entry_risk_guide(
            strategy=best["strategy"],
            data=best["strategy_input"],
            technical=best["technical"],
            condition_state=best["condition_state"],
            risk_plan=best["risk_plan"],
            current_state=current,
            historical_verified=False,
            historical_status="NOT_RUN",
            as_of_date=str(latest_date or "") or None,
            entry_timing=best.get("entry_timing"),
        )
        try:
            resolution = self.scanner.multi.production_exit.registry.resolve(best["strategy"])
            entry_risk_guide["historical_policy"] = self.scanner.multi.production_exit.historical_policy_metadata(resolution)
        except Exception:
            pass
        selected_rank = next((item["initial_rank"] for item in trace if item["strategy"] == best["strategy"]), None)
        for item in trace:
            item["selected"] = item["strategy"] == best["strategy"]
        return {
            "code": str(row.get("code") or ""),
            "name": str(row.get("name") or ""),
            "market": market,
            "latest_date": latest_date,
            "current_price": row.get("close"),
            "trade_value": row.get("trade_value"),
            "market_cap": row.get("market_cap"),
            "quick_strategy": best["strategy"],
            "quick_guide": best["guide"],
            "quick_current": current,
            "quick_condition_state": best["condition_state"],
            "quick_entry_risk_guide": entry_risk_guide,
            "quick_score": round(quick_score, 4),
            "_audit_initial_strategy_rank": selected_rank,
        }, trace

    @staticmethod
    def _ordered_quick(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        result = list(items)
        result.sort(
            key=lambda item: (float(item.get("quick_score") or 0.0), float(item.get("trade_value") or 0.0), str(item.get("code") or "")),
            reverse=True,
        )
        return result

    def _future_rows_many(self, *, codes_by_market: dict[str, set[str]], as_of: date, max_horizon: int) -> dict[tuple[str, str], list[dict[str, Any]]]:
        result: dict[tuple[str, str], list[dict[str, Any]]] = {}
        start = _compact(as_of + timedelta(days=1))
        end = _compact(as_of + timedelta(days=max(45, max_horizon * 3)))
        for market, codes in codes_by_market.items():
            if not codes:
                continue
            series_map = self.market_store.stock_series_many(market, sorted(codes), start, end)
            for code, series in series_map.items():
                result[(market, code)] = sorted((dict(row) for row in series.rows.values()), key=_row_date)
        return result

    @staticmethod
    def _aggregate_top_metrics(candidates: list[dict[str, Any]], horizons: tuple[int, ...]) -> dict[str, Any]:
        output: dict[str, Any] = {"count": len(candidates), "horizons": {}}
        for horizon in horizons:
            returns: list[float] = []
            rs: list[float] = []
            mfes: list[float] = []
            maes: list[float] = []
            target1 = 0
            stop = 0
            complete = 0
            for candidate in candidates:
                metric = _forward(candidate, horizon)
                if not metric.get("complete"):
                    continue
                complete += 1
                for bucket, key in ((returns, "return_pct"), (rs, "event_r"), (mfes, "mfe_pct"), (maes, "mae_pct")):
                    value = _num(metric.get(key))
                    if value is not None:
                        bucket.append(value)
                status = str((metric.get("event") or {}).get("status") or "")
                target1 += int(status == "TARGET1_FIRST")
                stop += int(status == "STOP_FIRST")
            output["horizons"][str(horizon)] = {
                "complete": complete,
                "mean_return_pct": _mean(returns),
                "median_return_pct": _median(returns),
                "mean_event_r": _mean(rs),
                "median_event_r": _median(rs),
                "mean_mfe_pct": _mean(mfes),
                "mean_mae_pct": _mean(maes),
                "target1_first_pct": _pct(target1, complete),
                "stop_first_pct": _pct(stop, complete),
            }
        return output

    def run_date(
        self,
        *,
        as_of: date,
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
        mode: str = "full",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        mode = mode.lower().strip()
        if mode not in {"inspect", "full"}:
            raise ValueError("mode must be inspect or full")
        markets = self._markets(market_scope)
        if not self._exact_day_available(markets, as_of):
            return {
                "analysis_date": as_of.isoformat(),
                "status": "SKIPPED_INSUFFICIENT_DATA",
                "runtime_seconds": round(time.perf_counter() - started, 6),
            }

        market_limit = int(self.scanner.QUICK_LIMIT_PER_MARKET)
        quick_limit = int(self.scanner.DEEP_LIMIT)
        latest_key = _compact(as_of)
        fast_start = as_of - timedelta(days=int(self.scanner.FAST_HISTORY_CALENDAR_DAYS))
        horizons_tuple = horizons.normalized()

        quick_by_variant: dict[str, list[dict[str, Any]]] = {
            BASELINE: [],
            MA120_FIXED: [],
            MA120_INPUT_ONLY: [],
            RS_KEEP_4: [],
            RS_KEEP_8: [],
            RS_RESTORE_10_8: [],
            RS_AUDIT_CURRENT: [],
            RS_AUDIT_KEEP_4: [],
            RS_AUDIT_KEEP_8: [],
            RS_AUDIT_RESTORE_10_8: [],
        }
        trace: dict[str, dict[str, Any]] = {}
        ma_stats = {
            "snapshots": 0,
            "input_rows_ge_120": 0,
            "ma120_available": 0,
            "ma120_unavailable": 0,
            "formula_verified": 0,
            "trend_evaluations": 0,
            "ma120_condition_present": 0,
            "ma120_condition_missing": 0,
            "ma120_would_pass": 0,
            "counterfactual_attempted": 0,
            "counterfactual_supported": 0,
            "counterfactual_changed_quick": 0,
            "input_only_attempted": 0,
            "input_only_supported": 0,
            "input_only_changed_quick": 0,
        }
        rs_stats = {
            "breakout_evaluations": 0,
            "market_condition_count": 0,
            "sector_condition_count": 0,
            "exact_duplicate_evaluations": 0,
            "metric_duplicate_evaluations": 0,
            "fallback_duplicate_evaluations": 0,
            "equal_runtime_value_evaluations": 0,
            "sector_missing_evaluations": 0,
            "sector_available_evaluations": 0,
            "market_fallback_evaluations": 0,
            "both_missing_evaluations": 0,
        }
        sector_input_stats: dict[str, Any] = {
            "prefetch_enabled": bool(getattr(self.scanner, "sector_prefetcher", None)),
            "evaluations": 0,
            "input_prepared": 0,
            "industry_code_available": 0,
            "industry_mapped": 0,
            "benchmark_resolved": 0,
            "sector_history_available": 0,
            "sector_20d_available": 0,
            "production_safe": 0,
            "future_rows_ignored": 0,
            "future_boundary_violations": 0,
            "temporal_status_counts": {},
            "unavailable_reason_counts": {},
            "prefetch_markets": {},
        }
        sector_counterfactual_stats: dict[str, Any] = {
            "attempted": 0,
            "supported": 0,
            "real_sector_available": 0,
            "market_sector_sign_divergent": 0,
            "current_score_changed_signals": 0,
            "current_strategy_changed_signals": 0,
            "current_breakout_score_changed_signals": 0,
            "current_breakout_score_delta_sum": 0.0,
            "fallback_used": 0,
        }
        sector_rs_variant_stats: dict[str, dict[str, Any]] = {
            RS_AUDIT_KEEP_4: {
                "kept_weight": 4.0, "removed_weight": 8.0, "dedup_attempted": 0, "dedup_supported": 0,
                "passed_condition_removed": 0, "condition_count_changed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
            },
            RS_AUDIT_KEEP_8: {
                "kept_weight": 8.0, "removed_weight": 4.0, "dedup_attempted": 0, "dedup_supported": 0,
                "passed_condition_removed": 0, "condition_count_changed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
            },
            RS_AUDIT_RESTORE_10_8: {
                "kept_weight": 8.0, "removed_weight": 4.0, "market_weight": 10.0,
                "dedup_attempted": 0, "dedup_supported": 0, "passed_condition_removed": 0,
                "condition_count_changed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
                "identical_score_but_condition_count_changed": 0,
            },
        }

        rs_variant_stats: dict[str, dict[str, Any]] = {
            RS_KEEP_4: {
                "kept_weight": 4.0, "removed_weight": 8.0, "dedup_attempted": 0, "dedup_supported": 0,
                "passed_condition_removed": 0, "condition_count_changed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
            },
            RS_KEEP_8: {
                "kept_weight": 8.0, "removed_weight": 4.0, "dedup_attempted": 0, "dedup_supported": 0,
                "passed_condition_removed": 0, "condition_count_changed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
            },
            RS_RESTORE_10_8: {
                "kept_weight": 8.0, "removed_weight": 4.0, "market_weight": 10.0,
                "dedup_attempted": 0, "dedup_supported": 0, "passed_condition_removed": 0,
                "condition_count_changed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
                "identical_score_but_condition_count_changed": 0,
            },
        }
        reeval_paths: dict[str, int] = {}
        duplicate_conditions: dict[str, int] = {}
        duplicate_weights_used: dict[str, list[float]] = {BREAKOUT_RS_CONDITION: list(self.breakout_rs_weights)}
        input_row_counts: list[int] = []
        special_excluded = 0
        liquidity_filtered = 0
        data_insufficient = 0
        universe_total = 0

        for market in markets:
            ordinary: list[dict[str, Any]] = []
            day_rows = self.market_store.stock_day_rows(market, latest_key)
            universe_total += len(day_rows)
            for raw in day_rows:
                row = dict(raw)
                if self.scanner._special_reason(row) is not None:  # noqa: SLF001
                    special_excluded += 1
                    continue
                if float(row.get("trade_value") or 0.0) < self.scanner.engine.LIQUIDITY_THRESHOLD:
                    liquidity_filtered += 1
                    continue
                ordinary.append(row)
            ordinary.sort(
                key=lambda item: (float(item.get("trade_value") or 0.0), float(item.get("market_cap") or 0.0)),
                reverse=True,
            )
            prefiltered = ordinary[:market_limit]
            index_series = self.market_store.index_series(market, _compact(fast_start), latest_key)
            index_rows = sorted((dict(row) for row in index_series.rows.values()), key=_row_date)
            series_map = self.market_store.stock_series_many(
                market,
                [str(row.get("code") or "") for row in prefiltered],
                _compact(fast_start),
                latest_key,
            )

            sector_inputs: dict[str, Any] = {}
            sector_prefetcher = getattr(self.scanner, "sector_prefetcher", None)
            if sector_prefetcher is not None and prefiltered:
                sector_inputs, prefetch_stats = _run_async(
                    sector_prefetcher.prepare(
                        market=market,
                        codes=[str(row.get("code") or "") for row in prefiltered],
                        as_of=as_of,
                        points=int(self.scanner.engine.RELATIVE_STRENGTH_POINTS),
                        lookback_days=140,
                    )
                )
                sector_input_stats["prefetch_markets"][market] = _safe_json(prefetch_stats)

            for row in prefiltered:
                code = str(row.get("code") or "")
                series = series_map.get(code)
                stock_rows = sorted((dict(item) for item in ((series.rows.values()) if series is not None else [])), key=_row_date)
                if len(stock_rows) < int(self.scanner.MIN_HISTORY_ROWS):
                    data_insufficient += 1
                    continue
                try:
                    from app.backtest.models import BacktestConfig

                    config = BacktestConfig(
                        code=code,
                        market=market,
                        start_date=self.scanner._iso(latest_key),  # noqa: SLF001
                        end_date=self.scanner._iso(latest_key),  # noqa: SLF001
                        initial_capital=10_000_000,
                        max_holding_days=20,
                        round_trip_cost_pct=0.0,
                    )
                    snapshot = self.scanner.engine._signal_snapshot(  # noqa: SLF001
                        stock_rows=stock_rows,
                        index_rows=index_rows,
                        index=len(stock_rows) - 1,
                        config=config,
                        sector_input=sector_inputs.get(code),
                    )
                except Exception:
                    hook = getattr(self.scanner, "_strategy_integrity_audit_snapshot", None)
                    snapshot = hook(market=market, latest_date=latest_key, row=row, stock_rows=stock_rows, index_rows=index_rows) if callable(hook) else None
                if snapshot is None:
                    data_insufficient += 1
                    continue

                ma_stats["snapshots"] += 1
                input_row_counts.append(len(stock_rows))
                if len(stock_rows) >= 120:
                    ma_stats["input_rows_ge_120"] += 1
                data = snapshot.get("strategy_input")
                technical = snapshot.get("technical") or {}
                ma120 = _num(getattr(data, "ma120", None))
                if ma120 is None:
                    ma_stats["ma120_unavailable"] += 1
                else:
                    ma_stats["ma120_available"] += 1
                formula_ok = _formula_matches(data, stock_rows)
                if formula_ok is True:
                    ma_stats["formula_verified"] += 1
                computed_ma120 = _sma(stock_rows, 120)

                prepared_sector = sector_inputs.get(code)
                sector_audit = dict(snapshot.get("sector_input_audit") or {})
                sector_input_stats["evaluations"] += 1
                if prepared_sector is not None:
                    sector_input_stats["input_prepared"] += 1
                    if getattr(prepared_sector, "industry_code", None):
                        sector_input_stats["industry_code_available"] += 1
                    if bool((getattr(prepared_sector, "mapping", {}) or {}).get("available")):
                        sector_input_stats["industry_mapped"] += 1
                    if getattr(prepared_sector, "benchmark_name", None):
                        sector_input_stats["benchmark_resolved"] += 1
                    if getattr(prepared_sector, "sector_rows", None):
                        sector_input_stats["sector_history_available"] += 1
                audit_sector_value = _num(sector_audit.get("audit_relative_strength_pct"))
                if audit_sector_value is not None:
                    sector_input_stats["sector_20d_available"] += 1
                if bool(sector_audit.get("production_safe")):
                    sector_input_stats["production_safe"] += 1
                temporal = str(sector_audit.get("temporal_status") or "NONE")
                temporal_counts = sector_input_stats["temporal_status_counts"]
                temporal_counts[temporal] = int(temporal_counts.get(temporal) or 0) + 1
                unavailable_reason = str(sector_audit.get("unavailable_reason") or ("AVAILABLE" if audit_sector_value is not None else "UNKNOWN"))
                reason_counts = sector_input_stats["unavailable_reason_counts"]
                reason_counts[unavailable_reason] = int(reason_counts.get(unavailable_reason) or 0) + 1
                ignored = int(sector_audit.get("future_rows_ignored") or 0)
                sector_input_stats["future_rows_ignored"] += ignored
                sector_end = str(sector_audit.get("sector_history_end_date") or "").replace("-", "")
                if sector_end and sector_end > latest_key:
                    sector_input_stats["future_boundary_violations"] += 1

                evaluations = _evaluation_map(snapshot.get("evaluations")) or {}
                trend_eval = _find_eval(evaluations, "trend_following")
                trend_reasons: list[str] = []
                trend_unmet: list[str] = []
                if trend_eval is not None:
                    ma_stats["trend_evaluations"] += 1
                    trend_reasons, trend_unmet = _evaluation_conditions(trend_eval)
                    if MA120_CONDITION in trend_reasons or MA120_CONDITION in trend_unmet:
                        ma_stats["ma120_condition_present"] += 1
                    if MA120_CONDITION in trend_unmet:
                        ma_stats["ma120_condition_missing"] += 1

                breakout_eval = _find_eval(evaluations, "breakout")
                breakout_conditions: list[str] = []
                breakout_duplicates: list[str] = []
                rel_market = _num(getattr(data, "relative_strength_market_pct", None))
                rel_sector = _num(getattr(data, "relative_strength_sector_pct", None))
                if breakout_eval is not None:
                    rs_stats["breakout_evaluations"] += 1
                    b_reasons, b_unmet = _evaluation_conditions(breakout_eval)
                    breakout_conditions = b_reasons + b_unmet
                    counts: dict[str, int] = {}
                    metric_counts: dict[str, int] = {}
                    sector_conditions: list[str] = []
                    market_conditions: list[str] = []
                    for condition in breakout_conditions:
                        counts[condition] = counts.get(condition, 0) + 1
                        metric_key = _metric_key_for_condition(condition, data, technical)
                        if metric_key:
                            metric_counts[metric_key] = metric_counts.get(metric_key, 0) + 1
                        if metric_key == "relative_strength_market":
                            rs_stats["market_condition_count"] += 1
                            market_conditions.append(condition)
                        elif metric_key == "relative_strength_sector":
                            rs_stats["sector_condition_count"] += 1
                            sector_conditions.append(condition)
                    breakout_duplicates = [condition for condition, count in counts.items() if count >= 2]
                    if any(count >= 2 for count in metric_counts.values()):
                        rs_stats["metric_duplicate_evaluations"] += 1
                    if breakout_duplicates:
                        rs_stats["exact_duplicate_evaluations"] += 1
                        for condition in breakout_duplicates:
                            duplicate_conditions[condition] = duplicate_conditions.get(condition, 0) + 1
                    if rel_sector is None:
                        rs_stats["sector_missing_evaluations"] += 1
                        if rel_market is None:
                            rs_stats["both_missing_evaluations"] += 1
                        else:
                            rs_stats["market_fallback_evaluations"] += 1
                    else:
                        rs_stats["sector_available_evaluations"] += 1
                    if rel_market is not None and rel_sector is not None and _same_number(rel_market, rel_sector):
                        rs_stats["equal_runtime_value_evaluations"] += 1
                    source_fallback = bool(self.source_report.get("sector_market_fallback_source_hits"))
                    if source_fallback and sector_conditions and market_conditions and (rel_sector is None or _same_number(rel_market, rel_sector)):
                        rs_stats["fallback_duplicate_evaluations"] += 1

                baseline_quick, baseline_trace = self._quick_from_snapshot(
                    snapshot=snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                )
                if baseline_quick is None:
                    continue
                quick_by_variant[BASELINE].append(baseline_quick)
                ma_quick = baseline_quick
                ma_input_quick = baseline_quick
                rs_quick_by_variant = {RS_KEEP_4: baseline_quick, RS_KEEP_8: baseline_quick, RS_RESTORE_10_8: baseline_quick}
                rs_meta_by_variant: dict[str, dict[str, Any]] = {}
                sector_quick_by_variant = {
                    RS_AUDIT_CURRENT: baseline_quick,
                    RS_AUDIT_KEEP_4: baseline_quick,
                    RS_AUDIT_KEEP_8: baseline_quick,
                    RS_AUDIT_RESTORE_10_8: baseline_quick,
                }
                sector_meta_by_variant: dict[str, dict[str, Any]] = {}
                sector_current_breakout = None

                ma_would_pass = (
                    ma120 is None
                    and computed_ma120 is not None
                    and _num(getattr(data, "ma60", None)) is not None
                    and float(getattr(data, "ma60")) > computed_ma120
                    and MA120_CONDITION in trend_unmet
                )
                if ma_would_pass:
                    ma_stats["ma120_would_pass"] += 1
                    patched_input = _replace_input(data, ma120=computed_ma120)
                    if patched_input is not None:
                        ma_stats["counterfactual_attempted"] += 1
                        patched_evals, resolver = _discover_revaluator(self.scanner, snapshot, patched_input)
                        if patched_evals:
                            ma_stats["counterfactual_supported"] += 1
                            if resolver:
                                reeval_paths[resolver] = reeval_paths.get(resolver, 0) + 1
                            patched_snapshot = dict(snapshot)
                            patched_snapshot["strategy_input"] = patched_input
                            original_mapping = snapshot.get("evaluations") or {}
                            new_mapping: dict[Any, Any] = {}
                            for key, original in original_mapping.items():
                                name = _evaluation_name(original) or _strategy_name(key)
                                new_mapping[key] = patched_evals.get(name, original)
                            patched_snapshot["evaluations"] = new_mapping
                            candidate, _ = self._quick_from_snapshot(
                                snapshot=patched_snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                            )
                            if candidate is not None:
                                ma_quick = candidate
                                if (
                                    candidate.get("quick_strategy") != baseline_quick.get("quick_strategy")
                                    or candidate.get("quick_score") != baseline_quick.get("quick_score")
                                ):
                                    ma_stats["counterfactual_changed_quick"] += 1

                # c.4c: production-like MA120 supply experiment. Existing 60-row technical
                # snapshot remains untouched; only StrategyInput.ma120 is supplied from as-of history.
                if ma120 is None and computed_ma120 is not None:
                    patched_input = _replace_input(data, ma120=computed_ma120)
                    if patched_input is not None:
                        ma_stats["input_only_attempted"] += 1
                        patched_evals, resolver = _discover_revaluator(self.scanner, snapshot, patched_input)
                        if patched_evals:
                            ma_stats["input_only_supported"] += 1
                            if resolver:
                                reeval_paths[resolver] = reeval_paths.get(resolver, 0) + 1
                            patched_snapshot = dict(snapshot)
                            patched_snapshot["strategy_input"] = patched_input
                            original_mapping = snapshot.get("evaluations") or {}
                            new_mapping: dict[Any, Any] = {}
                            for eval_key, original in original_mapping.items():
                                name = _evaluation_name(original) or _strategy_name(eval_key)
                                new_mapping[eval_key] = patched_evals.get(name, original)
                            patched_snapshot["evaluations"] = new_mapping
                            candidate, _ = self._quick_from_snapshot(
                                snapshot=patched_snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                            )
                            if candidate is not None:
                                ma_input_quick = candidate
                                if (
                                    candidate.get("quick_strategy") != baseline_quick.get("quick_strategy")
                                    or candidate.get("quick_score") != baseline_quick.get("quick_score")
                                ):
                                    ma_stats["input_only_changed_quick"] += 1

                # c.4g: audit-only real Sector RS verification. The prepared Sector RS may be
                # STATIC_CURRENT, so it is never written to Production StrategyInput. We patch
                # only this offline copy and reevaluate the Production 10+8 definition.
                if prepared_sector is not None:
                    sector_counterfactual_stats["attempted"] += 1
                    if audit_sector_value is None:
                        sector_counterfactual_stats["fallback_used"] += 1
                    else:
                        sector_counterfactual_stats["real_sector_available"] += 1
                        if rel_market is not None and ((rel_market > 0) != (audit_sector_value > 0)):
                            sector_counterfactual_stats["market_sector_sign_divergent"] += 1
                    sector_patched_input = _replace_input(data, relative_strength_sector_pct=audit_sector_value)
                    if sector_patched_input is not None:
                        sector_evals, resolver = _discover_revaluator(self.scanner, snapshot, sector_patched_input)
                        if sector_evals:
                            sector_counterfactual_stats["supported"] += 1
                            if resolver:
                                reeval_paths[resolver] = reeval_paths.get(resolver, 0) + 1
                            sector_snapshot = dict(snapshot)
                            sector_snapshot["strategy_input"] = sector_patched_input
                            original_mapping = snapshot.get("evaluations") or {}
                            sector_mapping: dict[Any, Any] = {}
                            for eval_key, original in original_mapping.items():
                                name = _evaluation_name(original) or _strategy_name(eval_key)
                                sector_mapping[eval_key] = sector_evals.get(name, original)
                            sector_snapshot["evaluations"] = sector_mapping
                            sector_current_breakout = _find_eval(sector_evals, "breakout")
                            if sector_current_breakout is not None and breakout_eval is not None:
                                production_breakout_score = _num(getattr(breakout_eval, "score", None))
                                sector_breakout_score = _num(getattr(sector_current_breakout, "score", None))
                                if production_breakout_score is not None and sector_breakout_score is not None:
                                    sector_breakout_delta = round(sector_breakout_score - production_breakout_score, 6)
                                    sector_counterfactual_stats["current_breakout_score_delta_sum"] += sector_breakout_delta
                                    if not math.isclose(sector_breakout_delta, 0.0, abs_tol=1e-12):
                                        sector_counterfactual_stats["current_breakout_score_changed_signals"] += 1
                            sector_current_quick, _ = self._quick_from_snapshot(
                                snapshot=sector_snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                            )
                            if sector_current_quick is not None:
                                sector_quick_by_variant[RS_AUDIT_CURRENT] = sector_current_quick
                                if sector_current_quick.get("quick_score") != baseline_quick.get("quick_score"):
                                    sector_counterfactual_stats["current_score_changed_signals"] += 1
                                if sector_current_quick.get("quick_strategy") != baseline_quick.get("quick_strategy"):
                                    sector_counterfactual_stats["current_strategy_changed_signals"] += 1

                            if sector_current_breakout is not None:
                                sector_reasons, sector_unmet = _evaluation_conditions(sector_current_breakout)
                                sector_duplicates = [
                                    condition for condition in set(sector_reasons + sector_unmet)
                                    if (sector_reasons + sector_unmet).count(condition) >= 2
                                ]
                                if BREAKOUT_RS_CONDITION in sector_duplicates:
                                    for variant_name, remove_weight in (
                                        (RS_AUDIT_KEEP_4, 8.0),
                                        (RS_AUDIT_KEEP_8, 4.0),
                                    ):
                                        variant_stats = sector_rs_variant_stats[variant_name]
                                        variant_stats["dedup_attempted"] += 1
                                        cloned, dedup_meta = _dedup_exact_condition(
                                            sector_current_breakout,
                                            BREAKOUT_RS_CONDITION,
                                            remove_weight,
                                            eligible_threshold=self.eligible_score_threshold,
                                        )
                                        sector_meta_by_variant[variant_name] = dedup_meta
                                        if cloned is None:
                                            continue
                                        variant_stats["dedup_supported"] += 1
                                        if dedup_meta.get("passed_duplicate_removed"):
                                            variant_stats["passed_condition_removed"] += 1
                                        if int(getattr(cloned, "total", 0) or 0) != int(getattr(sector_current_breakout, "total", 0) or 0):
                                            variant_stats["condition_count_changed"] += 1
                                        original_score = _num(dedup_meta.get("original_score"))
                                        new_score = _num(dedup_meta.get("new_score"))
                                        if original_score is not None and new_score is not None:
                                            score_delta = round(new_score - original_score, 6)
                                            variant_stats["score_deltas"].append(score_delta)
                                            if not math.isclose(score_delta, 0.0, abs_tol=1e-12):
                                                variant_stats["score_changed_signals"] += 1
                                        patched_sector_snapshot = dict(sector_snapshot)
                                        patched_mapping = dict(sector_mapping)
                                        for eval_key, original in list(patched_mapping.items()):
                                            if _evaluation_name(original) == "breakout":
                                                patched_mapping[eval_key] = cloned
                                        patched_sector_snapshot["evaluations"] = patched_mapping
                                        candidate, _ = self._quick_from_snapshot(
                                            snapshot=patched_sector_snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                                        )
                                        if candidate is not None:
                                            sector_quick_by_variant[variant_name] = candidate
                                            current_strategy = str((sector_quick_by_variant[RS_AUDIT_CURRENT] or {}).get("quick_strategy") or "")
                                            variant_strategy = str(candidate.get("quick_strategy") or "")
                                            if variant_strategy != current_strategy:
                                                variant_stats["strategy_changed_signals"] += 1
                                                if current_strategy == "breakout" and variant_strategy != "breakout":
                                                    variant_stats["breakout_to_other"] += 1
                                                elif current_strategy != "breakout" and variant_strategy == "breakout":
                                                    variant_stats["other_to_breakout"] += 1

                                    variant_stats = sector_rs_variant_stats[RS_AUDIT_RESTORE_10_8]
                                    variant_stats["dedup_attempted"] += 1
                                    restored, restore_meta = _restore_breakout_evaluation(
                                        sector_current_breakout,
                                        relative_strength_market_pct=rel_market,
                                        relative_strength_sector_pct=audit_sector_value,
                                        eligible_threshold=self.eligible_score_threshold,
                                    )
                                    sector_meta_by_variant[RS_AUDIT_RESTORE_10_8] = restore_meta
                                    if restored is not None:
                                        variant_stats["dedup_supported"] += 1
                                        if restore_meta.get("removed_condition_passed"):
                                            variant_stats["passed_condition_removed"] += 1
                                        if restore_meta.get("condition_count_changed"):
                                            variant_stats["condition_count_changed"] += 1
                                        original_score = _num(restore_meta.get("original_score"))
                                        new_score = _num(restore_meta.get("new_score"))
                                        if original_score is not None and new_score is not None:
                                            score_delta = round(new_score - original_score, 6)
                                            variant_stats["score_deltas"].append(score_delta)
                                            if not math.isclose(score_delta, 0.0, abs_tol=1e-12):
                                                variant_stats["score_changed_signals"] += 1
                                            elif restore_meta.get("condition_count_changed"):
                                                variant_stats["identical_score_but_condition_count_changed"] += 1
                                        patched_sector_snapshot = dict(sector_snapshot)
                                        patched_mapping = dict(sector_mapping)
                                        for eval_key, original in list(patched_mapping.items()):
                                            if _evaluation_name(original) == "breakout":
                                                patched_mapping[eval_key] = restored
                                        patched_sector_snapshot["evaluations"] = patched_mapping
                                        candidate, _ = self._quick_from_snapshot(
                                            snapshot=patched_sector_snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                                        )
                                        if candidate is not None:
                                            sector_quick_by_variant[RS_AUDIT_RESTORE_10_8] = candidate
                                            current_strategy = str((sector_quick_by_variant[RS_AUDIT_CURRENT] or {}).get("quick_strategy") or "")
                                            variant_strategy = str(candidate.get("quick_strategy") or "")
                                            if variant_strategy != current_strategy:
                                                variant_stats["strategy_changed_signals"] += 1
                                                if current_strategy == "breakout" and variant_strategy != "breakout":
                                                    variant_stats["breakout_to_other"] += 1
                                                elif current_strategy != "breakout" and variant_strategy == "breakout":
                                                    variant_stats["other_to_breakout"] += 1

                if breakout_eval is not None and BREAKOUT_RS_CONDITION in breakout_duplicates:
                    for variant_name in RS_DEDUP_VARIANTS:
                        variant_stats = rs_variant_stats[variant_name]
                        remove_weight = float(RS_REMOVED_WEIGHT[variant_name])
                        variant_stats["dedup_attempted"] += 1
                        cloned, dedup_meta = _dedup_exact_condition(
                            breakout_eval,
                            BREAKOUT_RS_CONDITION,
                            remove_weight,
                            eligible_threshold=self.eligible_score_threshold,
                        )
                        rs_meta_by_variant[variant_name] = dedup_meta
                        if cloned is None:
                            continue
                        variant_stats["dedup_supported"] += 1
                        if dedup_meta.get("passed_duplicate_removed"):
                            variant_stats["passed_condition_removed"] += 1
                        if int(getattr(cloned, "total", 0) or 0) != int(getattr(breakout_eval, "total", 0) or 0):
                            variant_stats["condition_count_changed"] += 1
                        original_score = _num(dedup_meta.get("original_score"))
                        new_score = _num(dedup_meta.get("new_score"))
                        if original_score is not None and new_score is not None:
                            score_delta = round(new_score - original_score, 6)
                            variant_stats["score_deltas"].append(score_delta)
                            if not math.isclose(score_delta, 0.0, abs_tol=1e-12):
                                variant_stats["score_changed_signals"] += 1

                        patched_snapshot = dict(snapshot)
                        new_mapping = dict(snapshot.get("evaluations") or {})
                        for eval_key, original in list(new_mapping.items()):
                            if _evaluation_name(original) == "breakout":
                                new_mapping[eval_key] = cloned
                        patched_snapshot["evaluations"] = new_mapping
                        candidate, _ = self._quick_from_snapshot(
                            snapshot=patched_snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                        )
                        if candidate is None:
                            continue
                        rs_quick_by_variant[variant_name] = candidate
                        baseline_strategy = str(baseline_quick.get("quick_strategy") or "")
                        variant_strategy = str(candidate.get("quick_strategy") or "")
                        if variant_strategy != baseline_strategy:
                            variant_stats["strategy_changed_signals"] += 1
                            if baseline_strategy == "breakout" and variant_strategy != "breakout":
                                variant_stats["breakout_to_other"] += 1
                            elif baseline_strategy != "breakout" and variant_strategy == "breakout":
                                variant_stats["other_to_breakout"] += 1

                if breakout_eval is not None and BREAKOUT_RS_CONDITION in breakout_duplicates:
                    variant_stats = rs_variant_stats[RS_RESTORE_10_8]
                    variant_stats["dedup_attempted"] += 1
                    restored, restore_meta = _restore_breakout_evaluation(
                        breakout_eval,
                        relative_strength_market_pct=rel_market,
                        relative_strength_sector_pct=rel_sector,
                        eligible_threshold=self.eligible_score_threshold,
                    )
                    rs_meta_by_variant[RS_RESTORE_10_8] = restore_meta
                    if restored is not None:
                        variant_stats["dedup_supported"] += 1
                        if restore_meta.get("removed_condition_passed"):
                            variant_stats["passed_condition_removed"] += 1
                        if restore_meta.get("condition_count_changed"):
                            variant_stats["condition_count_changed"] += 1
                        original_score = _num(restore_meta.get("original_score"))
                        new_score = _num(restore_meta.get("new_score"))
                        if original_score is not None and new_score is not None:
                            score_delta = round(new_score - original_score, 6)
                            variant_stats["score_deltas"].append(score_delta)
                            if not math.isclose(score_delta, 0.0, abs_tol=1e-12):
                                variant_stats["score_changed_signals"] += 1
                            elif restore_meta.get("condition_count_changed"):
                                variant_stats["identical_score_but_condition_count_changed"] += 1
                        patched_snapshot = dict(snapshot)
                        new_mapping = dict(snapshot.get("evaluations") or {})
                        for eval_key, original in list(new_mapping.items()):
                            if _evaluation_name(original) == "breakout":
                                new_mapping[eval_key] = restored
                        patched_snapshot["evaluations"] = new_mapping
                        candidate, _ = self._quick_from_snapshot(
                            snapshot=patched_snapshot, market=market, latest_date=latest_key, row=row, strategy_limit=3
                        )
                        if candidate is not None:
                            rs_quick_by_variant[RS_RESTORE_10_8] = candidate
                            baseline_strategy = str(baseline_quick.get("quick_strategy") or "")
                            variant_strategy = str(candidate.get("quick_strategy") or "")
                            if variant_strategy != baseline_strategy:
                                variant_stats["strategy_changed_signals"] += 1
                                if baseline_strategy == "breakout" and variant_strategy != "breakout":
                                    variant_stats["breakout_to_other"] += 1
                                elif baseline_strategy != "breakout" and variant_strategy == "breakout":
                                    variant_stats["other_to_breakout"] += 1

                quick_by_variant[MA120_FIXED].append(ma_quick)
                quick_by_variant[MA120_INPUT_ONLY].append(ma_input_quick)
                for variant_name in RS_VARIANTS:
                    quick_by_variant[variant_name].append(rs_quick_by_variant[variant_name])
                for variant_name in RS_AUDIT_ALL_VARIANTS:
                    quick_by_variant[variant_name].append(sector_quick_by_variant[variant_name])

                key = f"{market}:{code}"
                if ma_would_pass or breakout_duplicates or breakout_eval is not None or ma120 is None:
                    trace[key] = {
                        "market": market,
                        "code": code,
                        "name": row.get("name"),
                        "input_rows": len(stock_rows),
                        "ma20": _num(getattr(data, "ma20", None)),
                        "ma60": _num(getattr(data, "ma60", None)),
                        "ma120": ma120,
                        "computed_ma120": computed_ma120,
                        "ma_formula_verified": formula_ok,
                        "trend_ma120_condition_missing": MA120_CONDITION in trend_unmet,
                        "ma120_would_pass": ma_would_pass,
                        "relative_strength_market_pct": rel_market,
                        "relative_strength_sector_pct": rel_sector,
                        "audit_relative_strength_sector_pct": audit_sector_value,
                        "sector_temporal_status": sector_audit.get("temporal_status"),
                        "sector_production_safe": bool(sector_audit.get("production_safe")),
                        "sector_benchmark_name": sector_audit.get("benchmark_name"),
                        "sector_unavailable_reason": sector_audit.get("unavailable_reason"),
                        "sector_history_end_date": sector_audit.get("sector_history_end_date"),
                        "sector_future_rows_ignored": int(sector_audit.get("future_rows_ignored") or 0),
                        "relative_strength_equal": _same_number(rel_market, rel_sector),
                        "breakout_conditions": breakout_conditions,
                        "breakout_exact_duplicates": breakout_duplicates,
                        "baseline_quick_strategy": baseline_quick.get("quick_strategy"),
                        "baseline_quick_score": baseline_quick.get("quick_score"),
                        "ma120_quick_strategy": ma_quick.get("quick_strategy"),
                        "ma120_quick_score": ma_quick.get("quick_score"),
                        "ma120_input_quick_strategy": ma_input_quick.get("quick_strategy"),
                        "ma120_input_quick_score": ma_input_quick.get("quick_score"),
                        "rs_group": (
                            "SECTOR_AVAILABLE" if rel_sector is not None
                            else "MARKET_FALLBACK" if rel_market is not None
                            else "BOTH_MISSING"
                        ),
                        "rs_keep4_quick_strategy": rs_quick_by_variant[RS_KEEP_4].get("quick_strategy"),
                        "rs_keep4_quick_score": rs_quick_by_variant[RS_KEEP_4].get("quick_score"),
                        "rs_keep4_removed_weight": 8.0,
                        "rs_keep4_passed_removed": bool((rs_meta_by_variant.get(RS_KEEP_4) or {}).get("passed_duplicate_removed")),
                        "rs_keep8_quick_strategy": rs_quick_by_variant[RS_KEEP_8].get("quick_strategy"),
                        "rs_keep8_quick_score": rs_quick_by_variant[RS_KEEP_8].get("quick_score"),
                        "rs_keep8_removed_weight": 4.0,
                        "rs_keep8_passed_removed": bool((rs_meta_by_variant.get(RS_KEEP_8) or {}).get("passed_duplicate_removed")),
                        "rs_restore_quick_strategy": rs_quick_by_variant[RS_RESTORE_10_8].get("quick_strategy"),
                        "rs_restore_quick_score": rs_quick_by_variant[RS_RESTORE_10_8].get("quick_score"),
                        "rs_restore_score_delta": _delta(
                            (rs_meta_by_variant.get(RS_RESTORE_10_8) or {}).get("new_score"),
                            (rs_meta_by_variant.get(RS_RESTORE_10_8) or {}).get("original_score"),
                        ),
                        "rs_restore_condition_count_changed": bool((rs_meta_by_variant.get(RS_RESTORE_10_8) or {}).get("condition_count_changed")),
                        "sector_audit_current_quick_strategy": sector_quick_by_variant[RS_AUDIT_CURRENT].get("quick_strategy"),
                        "sector_audit_current_quick_score": sector_quick_by_variant[RS_AUDIT_CURRENT].get("quick_score"),
                        "sector_audit_keep4_quick_strategy": sector_quick_by_variant[RS_AUDIT_KEEP_4].get("quick_strategy"),
                        "sector_audit_keep4_quick_score": sector_quick_by_variant[RS_AUDIT_KEEP_4].get("quick_score"),
                        "sector_audit_keep8_quick_strategy": sector_quick_by_variant[RS_AUDIT_KEEP_8].get("quick_strategy"),
                        "sector_audit_keep8_quick_score": sector_quick_by_variant[RS_AUDIT_KEEP_8].get("quick_score"),
                        "sector_audit_restore_quick_strategy": sector_quick_by_variant[RS_AUDIT_RESTORE_10_8].get("quick_strategy"),
                        "sector_audit_restore_quick_score": sector_quick_by_variant[RS_AUDIT_RESTORE_10_8].get("quick_score"),
                        "baseline_strategy_trace": baseline_trace,
                    }

        for variant in quick_by_variant:
            quick_by_variant[variant] = self._ordered_quick(quick_by_variant[variant])

        selected_by_variant = {variant: values[:quick_limit] for variant, values in quick_by_variant.items()}
        results: dict[str, Any] = {}
        current_by_variant: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
        ranked_by_variant: dict[str, list[dict[str, Any]]] = {}
        outcome_codes: dict[str, set[str]] = {market: set() for market in markets}
        for variant, selected in selected_by_variant.items():
            current_map: dict[tuple[str, str], dict[str, Any]] = {}
            for quick in selected:
                current = self.scanner._current_candidate(quick)  # noqa: SLF001
                if current is None:
                    continue
                key = _candidate_key(quick)
                current_map[key] = current
                outcome_codes.setdefault(key[0], set()).add(key[1])
            actionable = [item for item in current_map.values() if item.get("candidate_state") in {"READY", "WATCH", "VALIDATION"}]
            ranked, ranking_changes = rank_candidates(actionable)
            current_by_variant[variant] = current_map
            ranked_by_variant[variant] = ranked
            results[variant] = {
                "quick_candidate_count": len(quick_by_variant[variant]),
                "quick_selected_count": len(selected),
                "quick_selected_keys": [f"{_candidate_key(item)[0]}:{_candidate_key(item)[1]}" for item in selected],
                "ranking_changes": _safe_json(ranking_changes),
            }

        future_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
        if mode == "full":
            future_rows = self._future_rows_many(codes_by_market=outcome_codes, as_of=as_of, max_horizon=max(horizons_tuple))

        for variant, ranked in ranked_by_variant.items():
            snapshots: list[dict[str, Any]] = []
            for rank_value, candidate in enumerate(ranked, start=1):
                key = (str(candidate.get("market") or ""), str(candidate.get("code") or ""))
                snap = _candidate_snapshot(candidate, rank=rank_value)
                if mode == "full":
                    snap["outcome"] = _future_metrics(candidate=candidate, future_rows=future_rows.get(key, []), horizons=horizons_tuple)
                snapshots.append(snap)
            results[variant]["candidates"] = snapshots
            results[variant]["top5_metrics"] = self._aggregate_top_metrics(snapshots[:5], horizons_tuple) if mode == "full" else {"count": len(snapshots[:5]), "horizons": {}}

        baseline_quick_order = list(results[BASELINE]["quick_selected_keys"])
        baseline_top5_order = _ordered_keys(results[BASELINE]["candidates"], limit=5)
        comparisons: dict[str, Any] = {}
        baseline_current = current_by_variant.get(BASELINE) or {}
        for variant in (MA120_FIXED, MA120_INPUT_ONLY, RS_KEEP_4, RS_KEEP_8, RS_RESTORE_10_8, *RS_AUDIT_ALL_VARIANTS):
            quick_order = list(results[variant]["quick_selected_keys"])
            top5_order = _ordered_keys(results[variant]["candidates"], limit=5)
            variant_current = current_by_variant.get(variant) or {}
            shared_keys = sorted(set(baseline_current) & set(variant_current))
            state_changes = sum(1 for key in shared_keys if _status(variant_current.get(key)) != _status(baseline_current.get(key)))
            risk_changes = sum(1 for key in shared_keys if _risk(variant_current.get(key)) != _risk(baseline_current.get(key)))
            quick_cmp = _sequence_comparison(baseline_quick_order, quick_order, prefix="quick")
            top5_cmp = _sequence_comparison(baseline_top5_order, top5_order, prefix="top5")
            comparisons[variant] = {
                **quick_cmp,
                **top5_cmp,
                # Backward-compatible membership aliases used by c.4a/c.4b reports.
                "quick_pool_changed": quick_cmp["quick_membership_changed"],
                "quick_pool_replacements": quick_cmp["quick_membership_replacements"],
                "quick_pool_added": quick_cmp["quick_membership_added"],
                "quick_pool_removed": quick_cmp["quick_membership_removed"],
                "top5_changed": top5_cmp["top5_membership_changed"],
                "top5_replacements": top5_cmp["top5_membership_replacements"],
                "top5_added": top5_cmp["top5_membership_added"],
                "top5_removed": top5_cmp["top5_membership_removed"],
                "candidate_state_changes": state_changes,
                "risk_status_changes": risk_changes,
            }

        sector_baseline_quick_order = list(results[RS_AUDIT_CURRENT]["quick_selected_keys"])
        sector_baseline_top5_order = _ordered_keys(results[RS_AUDIT_CURRENT]["candidates"], limit=5)
        sector_comparisons: dict[str, Any] = {}
        sector_baseline_current = current_by_variant.get(RS_AUDIT_CURRENT) or {}
        for variant in RS_AUDIT_VARIANTS:
            quick_cmp = _sequence_comparison(sector_baseline_quick_order, list(results[variant]["quick_selected_keys"]), prefix="quick")
            top5_cmp = _sequence_comparison(sector_baseline_top5_order, _ordered_keys(results[variant]["candidates"], limit=5), prefix="top5")
            state_changes = 0
            risk_changes = 0
            variant_current = current_by_variant.get(variant) or {}
            for candidate_key in set(sector_baseline_current) | set(variant_current):
                left = sector_baseline_current.get(candidate_key)
                right = variant_current.get(candidate_key)
                if left is None or right is None:
                    state_changes += 1
                    risk_changes += 1
                    continue
                if left.get("candidate_state") != right.get("candidate_state"):
                    state_changes += 1
                left_risk = left.get("risk") or {}
                right_risk = right.get("risk") or {}
                if (left_risk.get("status") if isinstance(left_risk, dict) else left_risk) != (right_risk.get("status") if isinstance(right_risk, dict) else right_risk):
                    risk_changes += 1
            sector_comparisons[variant] = {
                **quick_cmp, **top5_cmp,
                "quick_pool_changed": quick_cmp["quick_membership_changed"],
                "quick_pool_replacements": quick_cmp["quick_membership_replacements"],
                "quick_pool_added": quick_cmp["quick_membership_added"],
                "quick_pool_removed": quick_cmp["quick_membership_removed"],
                "top5_changed": top5_cmp["top5_membership_changed"],
                "top5_replacements": top5_cmp["top5_membership_replacements"],
                "top5_added": top5_cmp["top5_membership_added"],
                "top5_removed": top5_cmp["top5_membership_removed"],
                "candidate_state_changes": state_changes,
                "risk_status_changes": risk_changes,
            }

        rs_variant_summary: dict[str, dict[str, Any]] = {}
        for variant_name, raw_stats in rs_variant_stats.items():
            score_deltas = [float(value) for value in (raw_stats.get("score_deltas") or [])]
            rs_variant_summary[variant_name] = {
                key: value for key, value in raw_stats.items() if key != "score_deltas"
            }
            rs_variant_summary[variant_name].update({
                "mean_breakout_score_delta": _mean(score_deltas),
                "median_breakout_score_delta": _median(score_deltas),
            })

        sector_rs_variant_summary: dict[str, dict[str, Any]] = {}
        for variant_name, raw_stats in sector_rs_variant_stats.items():
            score_deltas = [float(value) for value in (raw_stats.get("score_deltas") or [])]
            sector_rs_variant_summary[variant_name] = {
                key: value for key, value in raw_stats.items() if key != "score_deltas"
            }
            sector_rs_variant_summary[variant_name].update({
                "mean_breakout_score_delta": _mean(score_deltas),
                "median_breakout_score_delta": _median(score_deltas),
            })

        return {
            "analysis_date": as_of.isoformat(),
            "status": "OK",
            "mode": mode,
            "market_scope": market_scope.upper(),
            "fast_history_start": fast_start.isoformat(),
            "market_limit": market_limit,
            "quick_limit": quick_limit,
            "universe_total": universe_total,
            "special_excluded": special_excluded,
            "liquidity_filtered": liquidity_filtered,
            "data_insufficient": data_insufficient,
            "input_rows": {
                "count": len(input_row_counts),
                "min": min(input_row_counts) if input_row_counts else None,
                "max": max(input_row_counts) if input_row_counts else None,
                "mean": _mean([float(value) for value in input_row_counts]),
            },
            "integrity": {
                "ma120": ma_stats,
                "sector_rs_input": sector_input_stats,
                "breakout_rs": rs_stats,
                "breakout_rs_variants": rs_variant_summary,
                "sector_rs_counterfactual": sector_counterfactual_stats,
                "sector_rs_counterfactual_variants": sector_rs_variant_summary,
                "revaluator_paths": reeval_paths,
                "duplicate_conditions": duplicate_conditions,
                "duplicate_weights_used": duplicate_weights_used,
            },
            "variants": results,
            "comparisons": comparisons,
            "sector_comparisons": sector_comparisons,
            "trace": trace,
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }

    def run_dates(
        self,
        *,
        dates: list[date],
        market_scope: str = "ALL",
        horizons: AuditHorizons = AuditHorizons(),
        mode: str = "full",
        progress_callback: Callable[[int, int, date, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        runs: list[dict[str, Any]] = []
        for index, as_of in enumerate(dates, start=1):
            run = self.run_date(as_of=as_of, market_scope=market_scope, horizons=horizons, mode=mode)
            runs.append(run)
            if progress_callback is not None:
                progress_callback(index, len(dates), as_of, run)
        valid = [run for run in runs if run.get("status") == "OK"]
        payload = {
            "audit_version": AUDIT_VERSION,
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "scanner_version": getattr(self.scanner, "VERSION", None),
            "market_scope": market_scope.upper(),
            "mode": mode,
            "evaluation_dates": [item.isoformat() for item in dates],
            "valid_date_count": len(valid),
            "skipped_date_count": len(runs) - len(valid),
            "source_integrity": self.source_report,
            "runs": runs,
            "runtime_seconds": round(time.perf_counter() - started, 6),
        }
        payload["strategy_integrity_validation"] = build_integrity_validation(payload, horizons=horizons.normalized())
        return payload


def _sum_nested(valid: list[dict[str, Any]], section: str, key: str) -> int:
    return sum(int((((run.get("integrity") or {}).get(section) or {}).get(key)) or 0) for run in valid)


def _aggregate_variant_top5(valid: list[dict[str, Any]], variant: str, horizon: int) -> dict[str, Any]:
    returns: list[float] = []
    rs: list[float] = []
    stops: list[float] = []
    targets: list[float] = []
    for run in valid:
        metric = (((((run.get("variants") or {}).get(variant) or {}).get("top5_metrics") or {}).get("horizons") or {}).get(str(horizon)) or {})
        for bucket, key in ((returns, "mean_return_pct"), (rs, "mean_event_r"), (stops, "stop_first_pct"), (targets, "target1_first_pct")):
            value = _num(metric.get(key))
            if value is not None:
                bucket.append(value)
    return {
        "mean_return_pct": _mean(returns),
        "median_return_pct": _median(returns),
        "trimmed_mean_return_pct": _trimmed_mean(returns),
        "mean_event_r": _mean(rs),
        "median_event_r": _median(rs),
        "mean_stop_first_pct": _mean(stops),
        "mean_target1_first_pct": _mean(targets),
    }


def _impact_summary(
    valid: list[dict[str, Any]],
    variant: str,
    horizons: tuple[int, ...],
    *,
    baseline_variant: str = BASELINE,
    comparisons_key: str = "comparisons",
) -> dict[str, Any]:
    quick_changed = [run for run in valid if (((run.get(comparisons_key) or {}).get(variant) or {}).get("quick_membership_changed", ((run.get(comparisons_key) or {}).get(variant) or {}).get("quick_pool_changed")))]
    top5_changed = [run for run in valid if (((run.get(comparisons_key) or {}).get(variant) or {}).get("top5_membership_changed", ((run.get(comparisons_key) or {}).get(variant) or {}).get("top5_changed")))]
    quick_order_changed = [run for run in valid if (((run.get(comparisons_key) or {}).get(variant) or {}).get("quick_order_changed"))]
    top5_order_changed = [run for run in valid if (((run.get(comparisons_key) or {}).get(variant) or {}).get("top5_order_changed"))]
    horizon_result: dict[str, Any] = {}
    for horizon in horizons:
        baseline = _aggregate_variant_top5(valid, baseline_variant, horizon)
        changed = _aggregate_variant_top5(valid, variant, horizon)
        horizon_result[str(horizon)] = {
            "baseline": baseline,
            "variant": changed,
            "mean_return_delta_pct": _delta(changed.get("mean_return_pct"), baseline.get("mean_return_pct")),
            "median_return_delta_pct": _delta(changed.get("median_return_pct"), baseline.get("median_return_pct")),
            "trimmed_return_delta_pct": _delta(changed.get("trimmed_mean_return_pct"), baseline.get("trimmed_mean_return_pct")),
            "mean_r_delta": _delta(changed.get("mean_event_r"), baseline.get("mean_event_r")),
            "stop_first_delta_pct": _delta(changed.get("mean_stop_first_pct"), baseline.get("mean_stop_first_pct")),
            "target1_first_delta_pct": _delta(changed.get("mean_target1_first_pct"), baseline.get("mean_target1_first_pct")),
        }
    return {
        "quick_pool_changed_date_count": len(quick_changed),
        "quick_pool_changed_rate_pct": _pct(len(quick_changed), len(valid)),
        "quick_pool_changed_dates": [run.get("analysis_date") for run in quick_changed],
        "quick_pool_replacements": sum(int((((run.get(comparisons_key) or {}).get(variant) or {}).get("quick_membership_replacements", ((run.get(comparisons_key) or {}).get(variant) or {}).get("quick_pool_replacements"))) or 0) for run in valid),
        "quick_order_changed_date_count": len(quick_order_changed),
        "quick_order_only_changed_date_count": sum(1 for run in valid if (((run.get(comparisons_key) or {}).get(variant) or {}).get("quick_order_only_changed"))),
        "top5_changed_date_count": len(top5_changed),
        "top5_changed_rate_pct": _pct(len(top5_changed), len(valid)),
        "top5_changed_dates": [run.get("analysis_date") for run in top5_changed],
        "top5_replacements": sum(int((((run.get(comparisons_key) or {}).get(variant) or {}).get("top5_membership_replacements", ((run.get(comparisons_key) or {}).get(variant) or {}).get("top5_replacements"))) or 0) for run in valid),
        "top5_order_changed_date_count": len(top5_order_changed),
        "top5_order_only_changed_date_count": sum(1 for run in valid if (((run.get(comparisons_key) or {}).get(variant) or {}).get("top5_order_only_changed"))),
        "horizons": horizon_result,
    }


def build_integrity_validation(payload: dict[str, Any], *, horizons: tuple[int, ...] = (5, 10, 20)) -> dict[str, Any]:
    valid = [run for run in payload.get("runs") or [] if run.get("status") == "OK"]
    mode = str(payload.get("mode") or "full").lower()

    ma_snapshots = _sum_nested(valid, "ma120", "snapshots")
    ma_ge120 = _sum_nested(valid, "ma120", "input_rows_ge_120")
    ma_available = _sum_nested(valid, "ma120", "ma120_available")
    ma_missing = _sum_nested(valid, "ma120", "ma120_unavailable")
    ma_condition_missing = _sum_nested(valid, "ma120", "ma120_condition_missing")
    ma_condition_present = _sum_nested(valid, "ma120", "ma120_condition_present")
    ma_would_pass = _sum_nested(valid, "ma120", "ma120_would_pass")
    ma_supported = _sum_nested(valid, "ma120", "counterfactual_supported")
    ma_attempted = _sum_nested(valid, "ma120", "counterfactual_attempted")
    ma_formula_verified = _sum_nested(valid, "ma120", "formula_verified")
    ma_availability = _pct(ma_available, ma_snapshots)

    if ma_snapshots == 0:
        ma_verdict = "MA120_PARTIAL"
    elif ma_ge120 > 0 and ma_condition_present > 0 and ma_condition_missing > 0 and ma_available == 0:
        ma_verdict = "CONFIRMED_MA120_INPUT_DEFECT"
    elif ma_condition_missing > 0 and ma_available < ma_snapshots:
        ma_verdict = "MA120_PARTIAL"
    else:
        ma_verdict = "MA120_OK"

    rs_breakouts = _sum_nested(valid, "breakout_rs", "breakout_evaluations")
    rs_exact = _sum_nested(valid, "breakout_rs", "exact_duplicate_evaluations")
    rs_metric_dup = _sum_nested(valid, "breakout_rs", "metric_duplicate_evaluations")
    rs_fallback_runtime = _sum_nested(valid, "breakout_rs", "fallback_duplicate_evaluations")
    rs_equal = _sum_nested(valid, "breakout_rs", "equal_runtime_value_evaluations")
    rs_sector_missing = _sum_nested(valid, "breakout_rs", "sector_missing_evaluations")
    rs_sector_available = _sum_nested(valid, "breakout_rs", "sector_available_evaluations")
    rs_market_fallback = _sum_nested(valid, "breakout_rs", "market_fallback_evaluations")
    rs_both_missing = _sum_nested(valid, "breakout_rs", "both_missing_evaluations")

    sector_input_evaluations = _sum_nested(valid, "sector_rs_input", "evaluations")
    sector_input_prepared = _sum_nested(valid, "sector_rs_input", "input_prepared")
    sector_industry_available = _sum_nested(valid, "sector_rs_input", "industry_code_available")
    sector_industry_mapped = _sum_nested(valid, "sector_rs_input", "industry_mapped")
    sector_benchmark_resolved = _sum_nested(valid, "sector_rs_input", "benchmark_resolved")
    sector_history_available = _sum_nested(valid, "sector_rs_input", "sector_history_available")
    sector_20d_available = _sum_nested(valid, "sector_rs_input", "sector_20d_available")
    sector_production_safe = _sum_nested(valid, "sector_rs_input", "production_safe")
    sector_future_ignored = _sum_nested(valid, "sector_rs_input", "future_rows_ignored")
    sector_future_violations = _sum_nested(valid, "sector_rs_input", "future_boundary_violations")
    sector_temporal_counts = _merge_count_dicts([((run.get("integrity") or {}).get("sector_rs_input") or {}).get("temporal_status_counts") or {} for run in valid])
    sector_unavailable_reasons = _merge_count_dicts([((run.get("integrity") or {}).get("sector_rs_input") or {}).get("unavailable_reason_counts") or {} for run in valid])
    sector_prefetch_market_stats = _merge_last_dicts([((run.get("integrity") or {}).get("sector_rs_input") or {}).get("prefetch_markets") or {} for run in valid])

    def _sum_sector_prefetch_metric(key: str) -> int:
        total = 0
        for run in valid:
            markets_payload = ((run.get("integrity") or {}).get("sector_rs_input") or {}).get("prefetch_markets") or {}
            for item in markets_payload.values():
                total += int((item or {}).get(key) or 0)
        return total

    sector_matrix = _sector_aware_rs_matrix()
    sector_matrix_divergent = sum(1 for item in sector_matrix if item.get("score_changed"))
    source = payload.get("source_integrity") or {}
    definition = source.get("breakout_rs_definition") or {}
    fallback_source_hits = len(source.get("sector_market_fallback_source_hits") or [])
    detected_weights = [float(value) for value in (definition.get("weights") or [])]

    production_definition_ok = (
        tuple(sorted(float(value) for value in (definition.get("market_weights") or []))) == (PRODUCTION_MARKET_RS_WEIGHT,)
        and tuple(sorted(float(value) for value in (definition.get("weights") or []))) == EXPECTED_BREAKOUT_RS_WEIGHTS
        and int(definition.get("duplicate_count") or 0) == 1
        and rs_exact == 0
        and rs_metric_dup == 0
    )
    if production_definition_ok:
        rs_verdict = "PRODUCTION_10_8_CONFIRMED"
    elif rs_exact > 0 or rs_metric_dup > 0:
        rs_verdict = "CONFIRMED_RS_DUPLICATION"
    else:
        rs_verdict = "RS_DEFINITION_MISMATCH"

    ma_impact = _impact_summary(valid, MA120_FIXED, horizons)
    ma_input_impact = _impact_summary(valid, MA120_INPUT_ONLY, horizons)
    rs_impacts = {variant: _impact_summary(valid, variant, horizons) for variant in RS_VARIANTS}
    sector_current_impact = _impact_summary(valid, RS_AUDIT_CURRENT, horizons)
    sector_rs_impacts = {
        variant: _impact_summary(
            valid, variant, horizons, baseline_variant=RS_AUDIT_CURRENT, comparisons_key="sector_comparisons"
        )
        for variant in RS_AUDIT_VARIANTS
    }
    sector_cf_attempted = _sum_nested(valid, "sector_rs_counterfactual", "attempted")
    sector_cf_supported = _sum_nested(valid, "sector_rs_counterfactual", "supported")
    sector_cf_real = _sum_nested(valid, "sector_rs_counterfactual", "real_sector_available")
    sector_cf_sign_divergent = _sum_nested(valid, "sector_rs_counterfactual", "market_sector_sign_divergent")
    sector_cf_score_changed = _sum_nested(valid, "sector_rs_counterfactual", "current_score_changed_signals")
    sector_cf_strategy_changed = _sum_nested(valid, "sector_rs_counterfactual", "current_strategy_changed_signals")
    sector_cf_breakout_score_changed = _sum_nested(valid, "sector_rs_counterfactual", "current_breakout_score_changed_signals")
    sector_cf_breakout_score_delta_sum = sum(
        float((((run.get("integrity") or {}).get("sector_rs_counterfactual") or {}).get("current_breakout_score_delta_sum")) or 0.0)
        for run in valid
    )
    sector_cf_fallback = _sum_nested(valid, "sector_rs_counterfactual", "fallback_used")

    def aggregate_variant_stats(variant: str, *, stats_key: str = "breakout_rs_variants") -> dict[str, Any]:
        items = [(((run.get("integrity") or {}).get(stats_key) or {}).get(variant) or {}) for run in valid]
        integer_keys = (
            "dedup_attempted", "dedup_supported", "passed_condition_removed", "condition_count_changed", "score_changed_signals",
            "strategy_changed_signals", "breakout_to_other", "other_to_breakout", "identical_score_but_condition_count_changed",
        )
        result = {key: sum(int(item.get(key) or 0) for item in items) for key in integer_keys}
        audit_weight_map = {
            RS_AUDIT_KEEP_4: (4.0, 8.0),
            RS_AUDIT_KEEP_8: (8.0, 4.0),
            RS_AUDIT_RESTORE_10_8: (8.0, 4.0),
        }
        if variant in audit_weight_map:
            result["kept_weight"], result["removed_weight"] = audit_weight_map[variant]
        else:
            result["kept_weight"] = RS_KEPT_WEIGHT.get(variant)
            result["removed_weight"] = RS_REMOVED_WEIGHT.get(variant)
        if variant in {RS_RESTORE_10_8, RS_AUDIT_RESTORE_10_8}:
            result["market_weight"] = RESTORED_MARKET_RS_WEIGHT
        means = [_num(item.get("mean_breakout_score_delta")) for item in items]
        medians = [_num(item.get("median_breakout_score_delta")) for item in items]
        result["mean_breakout_score_delta"] = _mean([value for value in means if value is not None])
        result["median_breakout_score_delta"] = _median([value for value in medians if value is not None])
        result["counterfactual_supported"] = result["dedup_attempted"] == result["dedup_supported"]
        return result

    rs_variant_stats = {variant: aggregate_variant_stats(variant) for variant in RS_VARIANTS}
    sector_rs_variant_stats = {
        variant: aggregate_variant_stats(variant, stats_key="sector_rs_counterfactual_variants")
        for variant in RS_AUDIT_VARIANTS
    }

    def robust_positive(impact: dict[str, Any]) -> bool:
        h10 = ((impact.get("horizons") or {}).get("10") or {})
        h20 = ((impact.get("horizons") or {}).get("20") or {})
        values = (
            _num(h10.get("mean_return_delta_pct")),
            _num(h20.get("mean_return_delta_pct")),
            _num(h20.get("trimmed_return_delta_pct")),
            _num(h20.get("mean_r_delta")),
            _num(h20.get("stop_first_delta_pct")),
        )
        if any(value is None for value in values):
            return False
        return bool(values[0] > 0 and values[1] > 0 and values[2] > 0 and values[3] > 0 and values[4] <= 0)

    def robust_harmful(impact: dict[str, Any]) -> bool:
        h10 = ((impact.get("horizons") or {}).get("10") or {})
        h20 = ((impact.get("horizons") or {}).get("20") or {})
        r10 = _num(h10.get("mean_return_delta_pct"))
        r20 = _num(h20.get("mean_return_delta_pct"))
        rr = _num(h20.get("mean_r_delta"))
        stop = _num(h20.get("stop_first_delta_pct"))
        if None in (r10, r20, rr, stop):
            return False
        return bool(r10 < 0 and r20 < 0 and rr < 0 and stop >= 0)

    keep4_impact = rs_impacts[RS_KEEP_4]
    keep8_impact = rs_impacts[RS_KEEP_8]
    keep4_material = int(keep4_impact.get("top5_changed_date_count") or 0) >= 2
    keep8_material = int(keep8_impact.get("top5_changed_date_count") or 0) >= 2
    keep4_positive = keep4_material and robust_positive(keep4_impact)
    keep8_positive = keep8_material and robust_positive(keep8_impact)
    keep4_harmful = keep4_material and robust_harmful(keep4_impact)
    keep8_harmful = keep8_material and robust_harmful(keep8_impact)

    if production_definition_ok:
        rs_policy_verdict = "PRODUCTION_10_8_ACTIVE"
    elif mode != "full":
        rs_policy_verdict = "INCONCLUSIVE"
    elif not keep4_material and not keep8_material:
        rs_policy_verdict = "RS_DUPLICATION_NO_MATERIAL_IMPACT"
    elif keep4_positive and not keep8_positive:
        rs_policy_verdict = "RS_KEEP_4_PREFERRED_CANDIDATE"
    elif keep8_positive and not keep4_positive:
        rs_policy_verdict = "RS_KEEP_8_PREFERRED_CANDIDATE"
    elif keep4_positive and keep8_positive:
        rs_policy_verdict = "RS_DEDUP_MATERIAL_BUT_WEIGHT_UNCLEAR"
    elif keep4_harmful and keep8_harmful:
        rs_policy_verdict = "RS_DEDUP_HARMFUL"
    else:
        rs_policy_verdict = "INCONCLUSIVE"

    ma_confirmed = ma_verdict == "CONFIRMED_MA120_INPUT_DEFECT"
    ma_partial = ma_verdict == "MA120_PARTIAL"
    rs_defect = rs_verdict in {"CONFIRMED_RS_DUPLICATION", "RS_DEFINITION_MISMATCH"}
    ma_top5 = int(ma_impact.get("top5_changed_date_count") or 0)
    ma_h20 = ((ma_impact.get("horizons") or {}).get("20") or {})
    ma_positive = (
        (_num(ma_h20.get("mean_r_delta")) or 0.0) > 0
        and (_num(ma_h20.get("stop_first_delta_pct")) or 0.0) <= 0
        and (_num(ma_h20.get("trimmed_return_delta_pct")) or 0.0) > 0
    )
    ma_impact_supported = ma_attempted == ma_supported
    rs_impact_supported = all(bool(rs_variant_stats[variant].get("counterfactual_supported")) for variant in RS_VARIANTS)
    rs_material = rs_policy_verdict in {
        "RS_KEEP_4_PREFERRED_CANDIDATE", "RS_KEEP_8_PREFERRED_CANDIDATE",
        "RS_DEDUP_MATERIAL_BUT_WEIGHT_UNCLEAR", "RS_DEDUP_HARMFUL",
    }
    ma_material = ma_confirmed and ma_top5 >= 2 and ma_positive

    if mode != "full":
        overall = "INCONCLUSIVE"
    elif ma_partial:
        overall = "INCONCLUSIVE"
    elif not ma_confirmed and not rs_defect:
        overall = "NO_INTEGRITY_DEFECT"
    elif (ma_confirmed and not ma_impact_supported) or (rs_defect and not rs_impact_supported):
        overall = "INCONCLUSIVE"
    elif ma_material and rs_material:
        overall = "BOTH_MATERIAL"
    elif ma_material:
        overall = "MA120_DEFECT_MATERIAL"
    elif rs_material:
        overall = "RS_DUPLICATION_MATERIAL"
    elif ma_top5 == 0 and all(int(rs_impacts[v].get("top5_changed_date_count") or 0) == 0 for v in RS_VARIANTS):
        overall = "DEFECT_CONFIRMED_NO_MATERIAL_IMPACT"
    else:
        overall = "INCONCLUSIVE"

    all_input_mins = [((run.get("input_rows") or {}).get("min")) for run in valid if ((run.get("input_rows") or {}).get("min")) is not None]
    all_input_maxs = [((run.get("input_rows") or {}).get("max")) for run in valid if ((run.get("input_rows") or {}).get("max")) is not None]
    c4g_acceptance_verdict = "PASS" if production_definition_ok and sector_future_violations == 0 else "FAIL"
    return {
        "valid_dates": len(valid),
        "c4g_production_rs_acceptance": {
            "verdict": c4g_acceptance_verdict,
            "production_definition": "market 10 + sector 8",
            "market_weights": [float(value) for value in (definition.get("market_weights") or [])],
            "sector_weights": detected_weights,
            "sector_condition_count": int(definition.get("duplicate_count") or 0),
            "duplicate_present": bool(rs_exact > 0 or rs_metric_dup > 0 or int(definition.get("duplicate_count") or 0) > 1),
            "future_boundary_violations": sector_future_violations,
            "historical_sector_activation_allowed": False,
            "scanner_version": payload.get("scanner_version"),
        },
        "ma120": {
            "verdict": ma_verdict,
            "required_rows": 120,
            "runtime_snapshot_count": ma_snapshots,
            "input_rows_ge_120": ma_ge120,
            "observed_input_rows_min": min(all_input_mins) if all_input_mins else None,
            "observed_input_rows_max": max(all_input_maxs) if all_input_maxs else None,
            "availability_count": ma_available,
            "unavailable_count": ma_missing,
            "availability_rate_pct": ma_availability,
            "formula_verified_count": ma_formula_verified,
            "affected_condition": MA120_CONDITION,
            "condition_present_count": ma_condition_present,
            "condition_missing_count": ma_condition_missing,
            "would_pass_if_sma120_available_count": ma_would_pass,
            "counterfactual_attempted": ma_attempted,
            "counterfactual_supported": ma_supported,
        },
        "sector_rs_input": {
            "prefetch_enabled": any(bool(((run.get("integrity") or {}).get("sector_rs_input") or {}).get("prefetch_enabled")) for run in valid),
            "evaluations": sector_input_evaluations,
            "input_prepared": sector_input_prepared,
            "industry_code_available": sector_industry_available,
            "industry_mapped": sector_industry_mapped,
            "benchmark_resolved": sector_benchmark_resolved,
            "sector_history_available": sector_history_available,
            "sector_20d_available": sector_20d_available,
            "sector_20d_availability_rate_pct": _pct(sector_20d_available, sector_input_evaluations),
            "production_safe": sector_production_safe,
            "production_activation_allowed": sector_input_evaluations > 0 and sector_production_safe == sector_20d_available and sector_20d_available > 0,
            "temporal_status_counts": sector_temporal_counts,
            "unavailable_reason_counts": sector_unavailable_reasons,
            "future_rows_ignored": sector_future_ignored,
            "future_boundary_violations": sector_future_violations,
            "temporal_integrity": "PASS" if sector_future_violations == 0 else "FAIL",
            "prefetch_market_stats": sector_prefetch_market_stats,
            "prefetch_totals": {
                "company_requests": _sum_sector_prefetch_metric("company_requests"),
                "company_cache_hits": _sum_sector_prefetch_metric("company_cache_hits"),
                "index_daily_calls": _sum_sector_prefetch_metric("index_daily_calls"),
                "index_cache_hits": _sum_sector_prefetch_metric("index_cache_hits"),
                "errors": _sum_sector_prefetch_metric("errors"),
            },
        },
        "sector_rs_counterfactual": {
            "audit_only": True,
            "historical_sector_activation_authorized": False,
            "attempted": sector_cf_attempted,
            "supported": sector_cf_supported,
            "support_complete": sector_cf_attempted > 0 and sector_cf_attempted == sector_cf_supported,
            "real_sector_available": sector_cf_real,
            "fallback_used": sector_cf_fallback,
            "market_sector_sign_divergent": sector_cf_sign_divergent,
            "market_sector_sign_divergence_rate_pct": _pct(sector_cf_sign_divergent, sector_cf_real),
            "production_10_8_quick_score_changed_signals": sector_cf_score_changed,
            "production_10_8_strategy_changed_signals": sector_cf_strategy_changed,
            "production_10_8_breakout_score_changed_signals": sector_cf_breakout_score_changed,
            "production_10_8_mean_breakout_score_delta": (
                round(sector_cf_breakout_score_delta_sum / sector_cf_breakout_score_changed, 6)
                if sector_cf_breakout_score_changed else 0.0
            ),
            "production_10_8_sector_aware_vs_fallback": sector_current_impact,
            "variants": {
                variant: {**sector_rs_variant_stats[variant], "impact": sector_rs_impacts[variant]}
                for variant in RS_AUDIT_VARIANTS
            },
            "ready_for_production_validation": bool(
                sector_cf_real > 0
                and sector_cf_attempted == sector_cf_supported
                and sector_future_violations == 0
            ),
            "temporal_caveat": "STATIC_CURRENT industry metadata remains audit-only unless point-in-time provenance is proven.",
        },
        "breakout_rs": {
            "verdict": rs_verdict,
            "definition_condition": definition.get("condition_label"),
            "production_sector_weights": detected_weights,
            "detected_duplicate_weights": [] if production_definition_ok else detected_weights,
            "predicate_equivalent": bool(definition.get("predicate_equivalent")),
            "source_file": definition.get("source_file"),
            "eligible_score_threshold": source.get("strategy_eligible_score_threshold"),
            "breakout_evaluation_count": rs_breakouts,
            "exact_duplicate_evaluation_count": rs_exact,
            "metric_duplicate_evaluation_count": rs_metric_dup,
            "fallback_duplicate_evaluation_count": rs_fallback_runtime,
            "equal_market_sector_value_count": rs_equal,
            "sector_missing_count": rs_sector_missing,
            "sector_available_count": rs_sector_available,
            "market_fallback_count": rs_market_fallback,
            "both_missing_count": rs_both_missing,
            "source_fallback_hit_count": fallback_source_hits,
            "sector_aware_matrix": sector_matrix,
            "sector_aware_score_divergence_cases": sector_matrix_divergent,
            "duplicate_conditions": _merge_count_dicts([((run.get("integrity") or {}).get("duplicate_conditions") or {}) for run in valid]),
            "duplicate_weights_detected": {} if production_definition_ok else _merge_last_dicts([((run.get("integrity") or {}).get("duplicate_weights_used") or {}) for run in valid]),
        },
        "ma120_impact": ma_impact,
        "ma120_input_only_impact": ma_input_impact,
        "comparison_normalization": {
            "membership_order_split": True,
            "sector_rs_available_rate_pct": _pct(rs_sector_available, rs_breakouts),
            "sector_rs_design_validation": "INSUFFICIENT_SECTOR_RS_DATA" if rs_sector_available == 0 else "STRUCTURAL_EFFECT_CONFIRMED",
            "synthetic_sector_matrix_status": "STRUCTURAL_EFFECT_CONFIRMED" if sector_matrix_divergent > 0 else "NO_STRUCTURAL_SCORE_DIVERGENCE",
            "historical_sector_activation_authorized": False,
        },
        "rs_variants": {
            variant: {**rs_variant_stats[variant], "impact": rs_impacts[variant]}
            for variant in RS_VARIANTS
        },
        "rs_policy_verdict": rs_policy_verdict,
        "overall_verdict": overall,
    }

def _merge_count_dicts(values: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for mapping in values:
        for key, value in mapping.items():
            result[str(key)] = result.get(str(key), 0) + int(value or 0)
    return result


def _merge_last_dicts(values: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for mapping in values:
        result.update(mapping)
    return result


def compact_integrity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    for run in result.get("runs") or []:
        trace = run.get("trace") or {}
        compact_trace = {}
        for key, item in trace.items():
            if (
                item.get("trend_ma120_condition_missing")
                or item.get("ma120_would_pass")
                or item.get("breakout_exact_duplicates")
                or item.get("relative_strength_equal")
                or item.get("audit_relative_strength_sector_pct") is not None
                or item.get("sector_unavailable_reason") not in (None, "SECTOR_INPUT_NOT_PREPARED")
            ):
                compact_trace[key] = item
        run["trace"] = compact_trace
        # Quick selected keys are enough for pool comparisons; large ranking-change prose is not needed in JSON.
        for variant in (run.get("variants") or {}).values():
            variant.pop("ranking_changes", None)
    return result


def _pair_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in payload.get("runs") or []:
        if run.get("status") != "OK":
            continue
        variants = run.get("variants") or {}
        production_baseline_map = {f"{item.get('market')}:{item.get('code')}": item for item in (variants.get(BASELINE) or {}).get("candidates", [])[:5]}
        sector_baseline_map = {f"{item.get('market')}:{item.get('code')}": item for item in (variants.get(RS_AUDIT_CURRENT) or {}).get("candidates", [])[:5]}
        for variant_name in (MA120_FIXED, MA120_INPUT_ONLY, RS_KEEP_4, RS_KEEP_8, RS_RESTORE_10_8, RS_AUDIT_CURRENT, *RS_AUDIT_VARIANTS):
            is_sector_dedup = variant_name in RS_AUDIT_VARIANTS
            comparison_source = run.get("sector_comparisons") if is_sector_dedup else run.get("comparisons")
            comparison = ((comparison_source or {}).get(variant_name) or {})
            if not comparison.get("top5_changed"):
                continue
            baseline_map = sector_baseline_map if is_sector_dedup else production_baseline_map
            variant_map = {f"{item.get('market')}:{item.get('code')}": item for item in (variants.get(variant_name) or {}).get("candidates", [])[:5]}
            removed = [baseline_map[key] for key in baseline_map if key not in variant_map]
            added = [variant_map[key] for key in variant_map if key not in baseline_map]
            for index in range(max(len(removed), len(added))):
                old = removed[index] if index < len(removed) else {}
                new = added[index] if index < len(added) else {}
                row = {
                    "analysis_date": run.get("analysis_date"),
                    "variant": variant_name,
                    "removed_weight": (
                        {RS_AUDIT_KEEP_4: 8.0, RS_AUDIT_KEEP_8: 4.0, RS_AUDIT_RESTORE_10_8: 4.0}.get(variant_name)
                        if variant_name in RS_AUDIT_VARIANTS else RS_REMOVED_WEIGHT.get(variant_name)
                    ),
                    "pair_index": index + 1,
                    "removed_market": old.get("market"),
                    "removed_code": old.get("code"),
                    "removed_name": old.get("name"),
                    "removed_strategy": old.get("strategy"),
                    "removed_rank": old.get("rank"),
                    "removed_candidate_state": old.get("candidate_state"),
                    "removed_priority_tier": old.get("priority_tier"),
                    "removed_entry_gap_pct": old.get("entry_gap_pct"),
                    "removed_strategy_fit_score": old.get("strategy_fit_score"),
                    "removed_conditions": json.dumps(old.get("conditions") or {}, ensure_ascii=False),
                    "removed_risk": (old.get("risk") or {}).get("status") if isinstance(old.get("risk"), dict) else old.get("risk"),
                    "added_market": new.get("market"),
                    "added_code": new.get("code"),
                    "added_name": new.get("name"),
                    "added_strategy": new.get("strategy"),
                    "added_rank": new.get("rank"),
                    "added_candidate_state": new.get("candidate_state"),
                    "added_priority_tier": new.get("priority_tier"),
                    "added_entry_gap_pct": new.get("entry_gap_pct"),
                    "added_strategy_fit_score": new.get("strategy_fit_score"),
                    "added_conditions": json.dumps(new.get("conditions") or {}, ensure_ascii=False),
                    "added_risk": (new.get("risk") or {}).get("status") if isinstance(new.get("risk"), dict) else new.get("risk"),
                    "cause": (
                        "MA120_INPUT_SUPPLY" if variant_name == MA120_INPUT_ONLY
                        else "LEGACY_MA120_COUNTERFACTUAL" if variant_name == MA120_FIXED
                        else "REAL_SECTOR_INPUT" if variant_name == RS_AUDIT_CURRENT
                        else "REAL_SECTOR_RS_STRUCTURE_CHANGE" if variant_name in RS_AUDIT_VARIANTS
                        else "RS_STRUCTURE_CHANGE"
                    ),
                }
                for horizon in (5, 10, 20):
                    old_metric = _forward(old, horizon)
                    new_metric = _forward(new, horizon)
                    row[f"removed_return_{horizon}d"] = _num(old_metric.get("return_pct"))
                    row[f"added_return_{horizon}d"] = _num(new_metric.get("return_pct"))
                    row[f"return_{horizon}d_delta"] = _delta(new_metric.get("return_pct"), old_metric.get("return_pct"))
                    row[f"removed_r_{horizon}d"] = _num(old_metric.get("event_r"))
                    row[f"added_r_{horizon}d"] = _num(new_metric.get("event_r"))
                    row[f"r_{horizon}d_delta"] = _delta(new_metric.get("event_r"), old_metric.get("event_r"))
                    row[f"removed_event_{horizon}d"] = str((old_metric.get("event") or {}).get("status") or "") or None
                    row[f"added_event_{horizon}d"] = str((new_metric.get("event") or {}).get("status") or "") or None
                rows.append(row)
    return rows

def write_integrity_outputs(payload: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"scanner-strategy-integrity-audit_{stamp}.json"
    signals_path = output_dir / f"scanner-strategy-integrity-signals_{stamp}.csv"
    pairs_path = output_dir / f"scanner-strategy-integrity-pairs_{stamp}.csv"
    ma120_pairs_path = output_dir / f"scanner-strategy-integrity-ma120-pairs_{stamp}.csv"
    md_path = output_dir / f"scanner-strategy-integrity-summary_{stamp}.md"

    json_path.write_text(json.dumps(_safe_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    signal_fields = [
        "analysis_date", "market", "code", "name", "input_rows", "ma20", "ma60", "ma120", "computed_ma120",
        "ma_formula_verified", "trend_ma120_condition_missing", "ma120_would_pass",
        "relative_strength_market_pct", "relative_strength_sector_pct", "relative_strength_equal", "rs_group",
        "breakout_exact_duplicates", "baseline_quick_strategy", "baseline_quick_score",
        "ma120_quick_strategy", "ma120_quick_score", "ma120_input_quick_strategy", "ma120_input_quick_score",
        "rs_keep4_quick_strategy", "rs_keep4_quick_score", "rs_keep4_removed_weight", "rs_keep4_passed_removed",
        "rs_keep8_quick_strategy", "rs_keep8_quick_score", "rs_keep8_removed_weight", "rs_keep8_passed_removed",
        "rs_restore_quick_strategy", "rs_restore_quick_score", "rs_restore_score_delta", "rs_restore_condition_count_changed",
        "audit_relative_strength_sector_pct", "sector_temporal_status", "sector_production_safe",
        "sector_benchmark_name", "sector_unavailable_reason", "sector_history_end_date", "sector_future_rows_ignored",
        "sector_audit_current_quick_strategy", "sector_audit_current_quick_score",
        "sector_audit_keep4_quick_strategy", "sector_audit_keep4_quick_score",
        "sector_audit_keep8_quick_strategy", "sector_audit_keep8_quick_score",
        "sector_audit_restore_quick_strategy", "sector_audit_restore_quick_score",
    ]
    with signals_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=signal_fields)
        writer.writeheader()
        for run in payload.get("runs") or []:
            for item in (run.get("trace") or {}).values():
                writer.writerow({
                    "analysis_date": run.get("analysis_date"),
                    **{field: item.get(field) for field in signal_fields if field not in {"analysis_date", "breakout_exact_duplicates"}},
                    "breakout_exact_duplicates": " | ".join(item.get("breakout_exact_duplicates") or []),
                })

    pair_fields = [
        "analysis_date", "variant", "removed_weight", "pair_index",
        "removed_market", "removed_code", "removed_name", "removed_strategy", "removed_rank", "removed_candidate_state",
        "removed_priority_tier", "removed_entry_gap_pct", "removed_strategy_fit_score", "removed_conditions", "removed_risk",
        "added_market", "added_code", "added_name", "added_strategy", "added_rank", "added_candidate_state",
        "added_priority_tier", "added_entry_gap_pct", "added_strategy_fit_score", "added_conditions", "added_risk", "cause",
        "removed_return_5d", "added_return_5d", "return_5d_delta", "removed_r_5d", "added_r_5d", "r_5d_delta", "removed_event_5d", "added_event_5d",
        "removed_return_10d", "added_return_10d", "return_10d_delta", "removed_r_10d", "added_r_10d", "r_10d_delta", "removed_event_10d", "added_event_10d",
        "removed_return_20d", "added_return_20d", "return_20d_delta", "removed_r_20d", "added_r_20d", "r_20d_delta", "removed_event_20d", "added_event_20d",
    ]
    pair_rows = _pair_rows(payload)
    with pairs_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        for row in pair_rows:
            writer.writerow(row)
    with ma120_pairs_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        for row in pair_rows:
            if row.get("variant") == MA120_INPUT_ONLY:
                writer.writerow(row)

    validation = payload.get("strategy_integrity_validation") or {}
    ma = validation.get("ma120") or {}
    rs = validation.get("breakout_rs") or {}
    sector_input = validation.get("sector_rs_input") or {}
    ma_imp = validation.get("ma120_impact") or {}
    ma_input_imp = validation.get("ma120_input_only_impact") or {}
    rs_variants = validation.get("rs_variants") or {}
    source = payload.get("source_integrity") or {}

    lines = [
        f"# Scanner Strategy Definition Integrity Audit — {payload.get('audit_version')}",
        "",
        f"- Scanner version: `{payload.get('scanner_version')}`",
        f"- Market scope: `{payload.get('market_scope')}`",
        f"- Mode: `{payload.get('mode')}`",
        f"- Valid dates: **{payload.get('valid_date_count', 0)}** / {len(payload.get('evaluation_dates') or [])}",
        f"- Runtime: **{payload.get('runtime_seconds')}s**",
        f"- Overall verdict: **{validation.get('overall_verdict')}**",
        f"- RS policy verdict: **{validation.get('rs_policy_verdict')}**",
        "",
        "## MA120 integrity",
        "",
        f"- Verdict: **{ma.get('verdict')}**",
        f"- Observed Market history rows: **{ma.get('observed_input_rows_min')} ~ {ma.get('observed_input_rows_max')}**",
        f"- `_signal_snapshot` window candidates from source: **{(source.get('signal_snapshot_window_candidates') or [])}**",
        f"- MA120 required rows: **{ma.get('required_rows')}**",
        f"- MA120 availability: **{ma.get('availability_count')} / {ma.get('runtime_snapshot_count')} ({ma.get('availability_rate_pct')}%)**",
        f"- `{MA120_CONDITION}` missing: **{ma.get('condition_missing_count')}** / present {ma.get('condition_present_count')}",
        f"- Would pass with local SMA120: **{ma.get('would_pass_if_sma120_available_count')}**",
        f"- Counterfactual supported: **{ma.get('counterfactual_supported')} / {ma.get('counterfactual_attempted')}**",
        f"- Legacy MA120_FIXED Quick18 membership changed dates: **{ma_imp.get('quick_pool_changed_date_count')}**",
        f"- Legacy MA120_FIXED Top5 membership changed dates: **{ma_imp.get('top5_changed_date_count')}**",
        f"- MA120_INPUT_ONLY Quick18 membership/order changed dates: **{ma_input_imp.get('quick_pool_changed_date_count')} / {ma_input_imp.get('quick_order_changed_date_count')}**",
        f"- MA120_INPUT_ONLY Top5 membership/order changed dates: **{ma_input_imp.get('top5_changed_date_count')} / {ma_input_imp.get('top5_order_changed_date_count')}**",
        "",
        "## Sector RS input coverage (c.4f.3 audit-only)",
        "",
        f"- Prefetch enabled: **{sector_input.get('prefetch_enabled')}**",
        f"- Prepared inputs: **{sector_input.get('input_prepared')} / {sector_input.get('evaluations')}**",
        f"- Industry code available: **{sector_input.get('industry_code_available')}**",
        f"- Industry mapped: **{sector_input.get('industry_mapped')}**",
        f"- Benchmark resolved: **{sector_input.get('benchmark_resolved')}**",
        f"- Sector history available: **{sector_input.get('sector_history_available')}**",
        f"- 20D Sector RS available: **{sector_input.get('sector_20d_available')} / {sector_input.get('evaluations')} ({sector_input.get('sector_20d_availability_rate_pct')}%)**",
        f"- Temporal status: `{json.dumps(sector_input.get('temporal_status_counts') or {}, ensure_ascii=False)}`",
        f"- Production safe: **{sector_input.get('production_safe')}**",
        f"- Production activation allowed: **{sector_input.get('production_activation_allowed')}**",
        f"- Unavailable reasons: `{json.dumps(sector_input.get('unavailable_reason_counts') or {}, ensure_ascii=False)}`",
        f"- Future rows ignored: **{sector_input.get('future_rows_ignored')}**",
        f"- Future boundary violations: **{sector_input.get('future_boundary_violations')}**",
        f"- Temporal integrity: **{sector_input.get('temporal_integrity')}**",
        f"- Prefetch totals: `{json.dumps(sector_input.get('prefetch_totals') or {}, ensure_ascii=False)}`",
        "",
        "## Sector-aware Production 10+8 verification (c.4g audit-only input)",
        "",
        f"- Re-evaluation supported: **{(validation.get('sector_rs_counterfactual') or {}).get('supported')} / {(validation.get('sector_rs_counterfactual') or {}).get('attempted')}**",
        f"- Real 20D Sector RS injected: **{(validation.get('sector_rs_counterfactual') or {}).get('real_sector_available')}**",
        f"- Market/Sector sign divergence: **{(validation.get('sector_rs_counterfactual') or {}).get('market_sector_sign_divergent')} ({(validation.get('sector_rs_counterfactual') or {}).get('market_sector_sign_divergence_rate_pct')}%)**",
        f"- Production 10+8 score-changed signals vs market fallback: **{(validation.get('sector_rs_counterfactual') or {}).get('production_10_8_quick_score_changed_signals')}**",
        f"- Production 10+8 strategy-changed signals vs market fallback: **{(validation.get('sector_rs_counterfactual') or {}).get('production_10_8_strategy_changed_signals')}**",
        f"- Production 10+8 Breakout score-changed signals vs market fallback: **{(validation.get('sector_rs_counterfactual') or {}).get('production_10_8_breakout_score_changed_signals')}**",
        f"- Production 10+8 mean Breakout score Δ (changed only): **{(validation.get('sector_rs_counterfactual') or {}).get('production_10_8_mean_breakout_score_delta')}**",
        f"- Ready for Production validation: **{(validation.get('sector_rs_counterfactual') or {}).get('ready_for_production_validation')}**",
        "- Production activation: **False** (audit-only; STATIC_CURRENT temporal caveat remains)",
        "",
    ]

    sector_cf = validation.get("sector_rs_counterfactual") or {}
    sector_cf_variants = sector_cf.get("variants") or {}
    for variant_name in RS_AUDIT_VARIANTS:
        item = sector_cf_variants.get(variant_name) or {}
        impact = item.get("impact") or {}
        lines.extend([
            f"### {variant_name} (vs {RS_AUDIT_CURRENT})",
            "",
            f"- Kept weight: **{item.get('kept_weight')}**",
            f"- Removed weight: **{item.get('removed_weight')}**",
            f"- Counterfactual supported: **{item.get('dedup_supported')} / {item.get('dedup_attempted')}**",
            f"- Breakout score changed signals: **{item.get('score_changed_signals')}**",
            f"- Mean Breakout score Δ: **{item.get('mean_breakout_score_delta')}**",
            f"- Strategy changed signals: **{item.get('strategy_changed_signals')}**",
            f"- Quick18 membership/order changed dates: **{impact.get('quick_pool_changed_date_count')} / {impact.get('quick_order_changed_date_count')}**",
            f"- Top5 membership/order changed dates: **{impact.get('top5_changed_date_count')} / {impact.get('top5_order_changed_date_count')}**",
            "",
        ])

    acceptance = validation.get("c4g_production_rs_acceptance") or {}
    lines.extend([
        "## c.4g Production RS acceptance",
        "",
        f"- Verdict: **{acceptance.get('verdict')}**",
        f"- Definition: **{acceptance.get('production_definition')}**",
        f"- Market weights: **{acceptance.get('market_weights')}**",
        f"- Sector weights: **{acceptance.get('sector_weights')}**",
        f"- Sector condition count: **{acceptance.get('sector_condition_count')}**",
        f"- Duplicate present: **{acceptance.get('duplicate_present')}**",
        f"- Future boundary violations: **{acceptance.get('future_boundary_violations')}**",
        f"- Historical Sector activation allowed: **{acceptance.get('historical_sector_activation_allowed')}**",
        "",
        "## Breakout relative-strength integrity",
        "",
        f"- Verdict: **{rs.get('verdict')}**",
        f"- Production sector weights: **{rs.get('production_sector_weights')}**",
        f"- Predicate equivalent: **{rs.get('predicate_equivalent')}**",
        f"- Strategy eligible-score threshold: **{rs.get('eligible_score_threshold')}**",
        f"- Breakout evaluations: **{rs.get('breakout_evaluation_count')}**",
        f"- Exact duplicate evaluations: **{rs.get('exact_duplicate_evaluation_count')}**",
        f"- Duplicate metric evaluations: **{rs.get('metric_duplicate_evaluation_count')}**",
        f"- Fallback duplicate evaluations: **{rs.get('fallback_duplicate_evaluation_count')}**",
        f"- Sector available: **{rs.get('sector_available_count')}**",
        f"- Sector availability rate: **{((validation.get('comparison_normalization') or {}).get('sector_rs_available_rate_pct'))}%**",
        f"- Real sector-data status: **{((validation.get('comparison_normalization') or {}).get('sector_rs_design_validation'))}**",
        f"- Synthetic sector-aware matrix: **{((validation.get('comparison_normalization') or {}).get('synthetic_sector_matrix_status'))}** ({rs.get('sector_aware_score_divergence_cases')} score-divergent cases)",
        f"- Market fallback: **{rs.get('market_fallback_count')}**",
        f"- Both RS missing: **{rs.get('both_missing_count')}**",
        f"- Duplicate conditions: `{json.dumps(rs.get('duplicate_conditions') or {}, ensure_ascii=False)}`",
        "",
    ])

    for variant_name in RS_VARIANTS:
        item = rs_variants.get(variant_name) or {}
        impact = item.get("impact") or {}
        lines.extend([
            f"### {variant_name}",
            "",
            f"- Kept weight: **{item.get('kept_weight')}**",
            f"- Removed weight: **{item.get('removed_weight')}**",
            f"- Counterfactual supported: **{item.get('dedup_supported')} / {item.get('dedup_attempted')}**",
            f"- PASS duplicate removed: **{item.get('passed_condition_removed')}**",
            f"- Breakout score changed signals: **{item.get('score_changed_signals')}**",
            f"- Mean breakout score Δ: **{item.get('mean_breakout_score_delta')}**",
            f"- Strategy changed signals: **{item.get('strategy_changed_signals')}**",
            f"- Breakout→other: **{item.get('breakout_to_other')}**",
            f"- Other→breakout: **{item.get('other_to_breakout')}**",
            f"- Quick18 membership/order changed dates: **{impact.get('quick_pool_changed_date_count')} / {impact.get('quick_order_changed_date_count')}**",
            f"- Quick18 membership replacements: **{impact.get('quick_pool_replacements')}**",
            f"- Top5 membership/order changed dates: **{impact.get('top5_changed_date_count')} / {impact.get('top5_order_changed_date_count')}**",
            f"- Top5 membership replacements: **{impact.get('top5_replacements')}**",
            "",
        ])

    lines.extend([
        "## Counterfactual Top5 delta",
        "",
        "| Variant | Horizon | Mean return Δ | Median return Δ | Trimmed return Δ | Mean R Δ | Stop-first Δ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    sector_cf = validation.get("sector_rs_counterfactual") or {}
    sector_cf_variants = sector_cf.get("variants") or {}
    table_variants = [("MA120_FIXED", ma_imp), ("MA120_INPUT_ONLY", ma_input_imp)] + [
        (variant_name, (rs_variants.get(variant_name) or {}).get("impact") or {}) for variant_name in RS_VARIANTS
    ] + [
        (RS_AUDIT_CURRENT, sector_cf.get("production_10_8_sector_aware_vs_fallback") or {})
    ] + [
        (variant_name, (sector_cf_variants.get(variant_name) or {}).get("impact") or {}) for variant_name in RS_AUDIT_VARIANTS
    ]
    for label, impact in table_variants:
        for horizon in (5, 10, 20):
            row = ((impact.get("horizons") or {}).get(str(horizon)) or {})
            lines.append(
                f"| {label} | {horizon}D | {row.get('mean_return_delta_pct')} | {row.get('median_return_delta_pct')} | "
                f"{row.get('trimmed_return_delta_pct')} | {row.get('mean_r_delta')} | {row.get('stop_first_delta_pct')} |"
            )
    lines.extend([
        "",
        "## Source inspection",
        "",
        f"- Python files scanned: **{source.get('files_scanned')}**",
        f"- Breakout definition source: `{rs.get('source_file')}`",
        f"- Sector→market fallback source hits: **{len(source.get('sector_market_fallback_source_hits') or [])}**",
        "",
        "The audit does not modify Production strategy definitions. Counterfactual variants exist only inside this offline runner.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "csv": str(signals_path), "pairs_csv": str(pairs_path), "ma120_pairs_csv": str(ma120_pairs_path), "markdown": str(md_path)}
