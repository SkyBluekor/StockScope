from __future__ import annotations

import ast
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
AUDIT_VERSION = "v0.21.4-B.2.3.4c.4b"
BASELINE = "BASELINE"
MA120_FIXED = "MA120_FIXED_AUDIT"
# Legacy name kept only for import compatibility with c.4 tests/tools.
RS_DEDUP = "RS_DEDUP_AUDIT"
RS_KEEP_4 = "RS_KEEP_4"
RS_KEEP_8 = "RS_KEEP_8"
RS_RESTORE_10_8 = "RS_RESTORE_10_8"
RS_VARIANTS = (RS_KEEP_4, RS_KEEP_8, RS_RESTORE_10_8)
RS_REMOVED_WEIGHT = {RS_KEEP_4: 8.0, RS_KEEP_8: 4.0, RS_RESTORE_10_8: 4.0}
RS_KEPT_WEIGHT = {RS_KEEP_4: 4.0, RS_KEEP_8: 8.0, RS_RESTORE_10_8: 8.0}
BREAKOUT_RS_CONDITION = "20일 업종 대비 상대강도 양호"
EXPECTED_BREAKOUT_RS_WEIGHTS = (4.0, 8.0)
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
    """Read only the two duplicated Breakout RS tuples from strategy/engine.py.

    c.4 used broad numeric harvesting and accidentally selected 1.0.  c.4a scopes
    extraction to StrategyEngine._breakout and the exact duplicated label.
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

    entries: list[dict[str, Any]] = []
    market_entries: list[dict[str, Any]] = []
    for node in ast.walk(breakout):
        if not isinstance(node, ast.Tuple) or len(node.elts) < 3:
            continue
        label_node, weight_node, predicate_node = node.elts[0], node.elts[1], node.elts[2]
        if not isinstance(label_node, ast.Constant) or label_node.value not in {BREAKOUT_RS_CONDITION, "20일 시장 대비 상대강도 양호"}:
            continue
        weight = _ast_number(weight_node)
        if weight is None:
            continue
        (entries if label_node.value == BREAKOUT_RS_CONDITION else market_entries).append({
            "label": label_node.value,
            "weight": float(weight),
            "line": int(getattr(node, "lineno", 0) or 0),
            "predicate_ast": ast.dump(predicate_node, annotate_fields=True, include_attributes=False),
            "predicate_source": (ast.get_source_segment(text, predicate_node) or "").strip(),
        })

    entries.sort(key=lambda item: (int(item.get("line") or 0), float(item.get("weight") or 0.0)))
    predicate_dumps = [str(item.get("predicate_ast") or "") for item in entries]
    return {
        "source_file": str(path),
        "condition_label": BREAKOUT_RS_CONDITION,
        "market_entries": market_entries,
        "market_weights": [item["weight"] for item in market_entries],
        "duplicate_count": len(entries),
        "weights": [float(item["weight"]) for item in entries],
        "predicate_equivalent": bool(entries) and len(set(predicate_dumps)) == 1,
        "entries": entries,
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


def _validate_breakout_rs_definition(report: dict[str, Any]) -> None:
    definition = report.get("breakout_rs_definition") or {}
    weights = tuple(sorted(float(value) for value in (definition.get("weights") or [])))
    count = int(definition.get("duplicate_count") or 0)
    equivalent = bool(definition.get("predicate_equivalent"))
    label = str(definition.get("condition_label") or "")
    errors: list[str] = []
    if count != 2:
        errors.append(f"duplicate_count={count}")
    if weights != EXPECTED_BREAKOUT_RS_WEIGHTS:
        errors.append(f"weights={list(weights)}")
    if label != BREAKOUT_RS_CONDITION:
        errors.append(f"label={label!r}")
    if not equivalent:
        errors.append("predicate_equivalent=False")
    if definition.get("market_weights") != [6.0]:
        errors.append(f"market_weights={definition.get('market_weights')}")
    if errors:
        raise RuntimeError(
            "RS audit aborted: expected exactly two equivalent Breakout RS conditions "
            f"with weights [4, 8]; found {', '.join(errors)}"
        )


def _restore_breakout_evaluation(data: Any, original: Any) -> tuple[Any, dict[str, Any]]:
    """Re-evaluate audit-only conditions; never mutate the production engine."""
    from dataclasses import fields
    from app.strategy.engine import StrategyEngine
    from app.strategy.models import StrategyInput, StrategyName

    class CaptureConditions(StrategyEngine):
        @classmethod
        def _evaluate(cls, strategy, data, conditions, **kwargs):
            return conditions

    conditions = CaptureConditions()._breakout(data)
    restored = []
    for label, weight, predicate in conditions:
        if label == BREAKOUT_RS_CONDITION and weight == 4:
            continue
        if label == "20일 시장 대비 상대강도 양호":
            weight = 10
        restored.append((label, weight, predicate))
    market = [w for label, w, _ in restored if label == "20일 시장 대비 상대강도 양호"]
    sector = [w for label, w, _ in restored if label == BREAKOUT_RS_CONDITION]
    if market != [10] or sector != [8]:
        raise RuntimeError("RS restore aborted: expected market=10, sector=[8], count=1")
    # Minimal audit fixtures may expose only a subset of StrategyInput fields.
    if not isinstance(data, StrategyInput):
        values = {f.name: getattr(data, f.name) for f in fields(StrategyInput) if hasattr(data, f.name)}
        values.setdefault("code", "audit")
        values.setdefault("market", "KOSPI")
        data = StrategyInput(**values)
    if original is None:
        return None, {"market_weight": 10, "sector_weights": [8], "sector_condition_count": 1}
    blockers = list(getattr(original, "blockers", None) or [])
    blockers = list(dict.fromkeys([*blockers, *StrategyEngine._risk_gate(data)]))
    evaluated = StrategyEngine._evaluate(StrategyName.BREAKOUT, data, restored, blockers=blockers)
    result = _clone_evaluation(original, score=evaluated.score, eligible=evaluated.eligible,
                               passed=evaluated.passed, total=evaluated.total,
                               reasons=evaluated.reasons, unmet=evaluated.unmet)
    if result is None:
        raise RuntimeError("RS restore aborted: cannot reconstruct evaluation")
    return result, {"original_score": getattr(original, "score", None), "new_score": evaluated.score,
                    "market_weight": 10, "sector_weights": [8], "sector_condition_count": 1,
                    "original_total": getattr(original, "total", None), "new_total": evaluated.total,
                    "original_passed": getattr(original, "passed", None), "new_passed": evaluated.passed,
                    "eligible": evaluated.eligible, "reasons": evaluated.reasons, "unmet": evaluated.unmet,
                    "passed_duplicate_removed": BREAKOUT_RS_CONDITION in (getattr(original, "reasons", None) or [])}


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
        _validate_breakout_rs_definition(self.source_report)
        definition = self.source_report.get("breakout_rs_definition") or {}
        from app.strategy.models import StrategyInput
        _restore_breakout_evaluation(StrategyInput(code="source-check", market="KOSPI", current_price=1), None)
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
            RS_KEEP_4: [],
            RS_KEEP_8: [],
            RS_RESTORE_10_8: [],
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
        rs_variant_stats: dict[str, dict[str, Any]] = {
            RS_KEEP_4: {
                "kept_weight": 4.0, "removed_weight": 8.0, "dedup_attempted": 0, "dedup_supported": 0,
                "passed_condition_removed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
            },
            RS_KEEP_8: {
                "kept_weight": 8.0, "removed_weight": 4.0, "dedup_attempted": 0, "dedup_supported": 0,
                "passed_condition_removed": 0, "score_changed_signals": 0, "strategy_changed_signals": 0,
                "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
            },
        }
        rs_variant_stats[RS_RESTORE_10_8] = {
            "kept_weight": 8.0, "removed_weight": 4.0, "market_weight": 10,
            "sector_condition_count": 1, "dedup_attempted": 0, "dedup_supported": 0,
            "passed_condition_removed": 0, "score_changed_signals": 0,
            "condition_count_changed_signals": 0, "strategy_changed_signals": 0,
            "breakout_to_other": 0, "other_to_breakout": 0, "score_deltas": [],
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
                rs_quick_by_variant = {variant: baseline_quick for variant in RS_VARIANTS}
                rs_meta_by_variant: dict[str, dict[str, Any]] = {}

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

                if breakout_eval is not None and BREAKOUT_RS_CONDITION in breakout_duplicates:
                    for variant_name in RS_VARIANTS:
                        variant_stats = rs_variant_stats[variant_name]
                        remove_weight = float(RS_REMOVED_WEIGHT[variant_name])
                        variant_stats["dedup_attempted"] += 1
                        if variant_name == RS_RESTORE_10_8:
                            cloned, dedup_meta = _restore_breakout_evaluation(data, breakout_eval)
                            variant_stats["condition_count_changed_signals"] += int(cloned.total != breakout_eval.total)
                        else:
                            cloned, dedup_meta = _dedup_exact_condition(
                                breakout_eval, BREAKOUT_RS_CONDITION, remove_weight,
                                eligible_threshold=self.eligible_score_threshold,
                            )
                        rs_meta_by_variant[variant_name] = dedup_meta
                        if cloned is None:
                            continue
                        variant_stats["dedup_supported"] += 1
                        if dedup_meta.get("passed_duplicate_removed"):
                            variant_stats["passed_condition_removed"] += 1
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

                quick_by_variant[MA120_FIXED].append(ma_quick)
                for variant_name in RS_VARIANTS:
                    quick_by_variant[variant_name].append(rs_quick_by_variant[variant_name])

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
                        "relative_strength_equal": _same_number(rel_market, rel_sector),
                        "breakout_conditions": breakout_conditions,
                        "breakout_exact_duplicates": breakout_duplicates,
                        "baseline_quick_strategy": baseline_quick.get("quick_strategy"),
                        "baseline_quick_score": baseline_quick.get("quick_score"),
                        "ma120_quick_strategy": ma_quick.get("quick_strategy"),
                        "ma120_quick_score": ma_quick.get("quick_score"),
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
                        "rs_restore_evaluation": rs_meta_by_variant.get(RS_RESTORE_10_8),
                        "baseline_current": baseline_quick.get("quick_current"),
                        "rs_restore_current": rs_quick_by_variant[RS_RESTORE_10_8].get("quick_current"),
                        "rs_restore_condition_state": rs_quick_by_variant[RS_RESTORE_10_8].get("quick_condition_state"),
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

        baseline_pool = set(results[BASELINE]["quick_selected_keys"])
        baseline_top5 = {f"{item.get('market')}:{item.get('code')}" for item in results[BASELINE]["candidates"][:5]}
        comparisons: dict[str, Any] = {}
        baseline_current = current_by_variant.get(BASELINE) or {}
        for variant in (MA120_FIXED, *RS_VARIANTS):
            pool = set(results[variant]["quick_selected_keys"])
            top5 = {f"{item.get('market')}:{item.get('code')}" for item in results[variant]["candidates"][:5]}
            variant_current = current_by_variant.get(variant) or {}
            shared_keys = sorted(set(baseline_current) & set(variant_current))
            state_changes = sum(1 for key in shared_keys if _status(variant_current.get(key)) != _status(baseline_current.get(key)))
            risk_changes = sum(1 for key in shared_keys if _risk(variant_current.get(key)) != _risk(baseline_current.get(key)))
            quick_order_changed = results[variant]["quick_selected_keys"] != results[BASELINE]["quick_selected_keys"]
            top5_order_changed = [(item.get("market"), item.get("code")) for item in results[variant]["candidates"][:5]] != [(item.get("market"), item.get("code")) for item in results[BASELINE]["candidates"][:5]]
            comparisons[variant] = {
                "quick_pool_order_changed": quick_order_changed,
                "top5_order_changed": top5_order_changed,
                "quick_pool_changed": (quick_order_changed if variant == RS_RESTORE_10_8 else pool != baseline_pool),
                "quick_pool_replacements": max(len(pool - baseline_pool), len(baseline_pool - pool)),
                "quick_pool_added": sorted(pool - baseline_pool),
                "quick_pool_removed": sorted(baseline_pool - pool),
                "top5_changed": (top5_order_changed if variant == RS_RESTORE_10_8 else top5 != baseline_top5),
                "top5_replacements": max(len(top5 - baseline_top5), len(baseline_top5 - top5)),
                "top5_added": sorted(top5 - baseline_top5),
                "top5_removed": sorted(baseline_top5 - top5),
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
                "breakout_rs": rs_stats,
                "breakout_rs_variants": rs_variant_summary,
                "revaluator_paths": reeval_paths,
                "duplicate_conditions": duplicate_conditions,
                "duplicate_weights_used": duplicate_weights_used,
            },
            "variants": results,
            "comparisons": comparisons,
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
    mfes: list[float] = []
    maes: list[float] = []
    stops: list[float] = []
    targets: list[float] = []
    for run in valid:
        metric = (((((run.get("variants") or {}).get(variant) or {}).get("top5_metrics") or {}).get("horizons") or {}).get(str(horizon)) or {})
        for bucket, key in ((returns, "mean_return_pct"), (rs, "mean_event_r"), (stops, "stop_first_pct"), (targets, "target1_first_pct"), (mfes, "mean_mfe_pct"), (maes, "mean_mae_pct")):
            value = _num(metric.get(key))
            if value is not None:
                bucket.append(value)
    return {
        "mean_return_pct": _mean(returns),
        "median_return_pct": _median(returns),
        "trimmed_mean_return_pct": _trimmed_mean(returns),
        "mean_event_r": _mean(rs),
        "median_event_r": _median(rs),
        "mean_mfe_pct": _mean(mfes),
        "mean_mae_pct": _mean(maes),
        "mean_stop_first_pct": _mean(stops),
        "mean_target1_first_pct": _mean(targets),
    }


def _top5_observation_metrics(valid: list[dict[str, Any]], variant: str, horizon: int) -> dict[str, Any]:
    metrics = [_forward(candidate, horizon) for run in valid
               for candidate in (run.get("variants", {}).get(variant, {}).get("candidates") or [])[:5]]
    metrics = [item for item in metrics if item.get("complete")]
    def values(key):
        return [value for item in metrics if (value := _num(item.get(key))) is not None]
    returns, rs = values("return_pct"), values("event_r")
    return {
        "complete": len(metrics), "mean_return_pct": _mean(returns),
        "median_return_pct": _median(returns), "trimmed_mean_return_pct": _trimmed_mean(returns),
        "mean_event_r": _mean(rs), "median_event_r": _median(rs),
        "mean_mfe_pct": _mean(values("mfe_pct")), "mean_mae_pct": _mean(values("mae_pct")),
        "mean_target1_first_pct": _pct(sum((item.get("event") or {}).get("status") == "TARGET1_FIRST" for item in metrics), len(metrics)),
        "mean_stop_first_pct": _pct(sum((item.get("event") or {}).get("status") == "STOP_FIRST" for item in metrics), len(metrics)),
    }


def _impact_summary(valid: list[dict[str, Any]], variant: str, horizons: tuple[int, ...]) -> dict[str, Any]:
    quick_changed = [run for run in valid if (((run.get("comparisons") or {}).get(variant) or {}).get("quick_pool_changed"))]
    top5_changed = [run for run in valid if (((run.get("comparisons") or {}).get(variant) or {}).get("top5_changed"))]
    horizon_result: dict[str, Any] = {}
    for horizon in horizons:
        baseline = _aggregate_variant_top5(valid, BASELINE, horizon)
        changed = _aggregate_variant_top5(valid, variant, horizon)
        if variant == RS_RESTORE_10_8:
            baseline = _top5_observation_metrics(valid, BASELINE, horizon)
            changed = _top5_observation_metrics(valid, variant, horizon)
        horizon_result[str(horizon)] = {
            "baseline": baseline,
            "variant": changed,
            "mean_return_delta_pct": _delta(changed.get("mean_return_pct"), baseline.get("mean_return_pct")),
            "median_return_delta_pct": _delta(changed.get("median_return_pct"), baseline.get("median_return_pct")),
            "trimmed_return_delta_pct": _delta(changed.get("trimmed_mean_return_pct"), baseline.get("trimmed_mean_return_pct")),
            "mean_r_delta": _delta(changed.get("mean_event_r"), baseline.get("mean_event_r")),
            "median_r_delta": _delta(changed.get("median_event_r"), baseline.get("median_event_r")),
            "mfe_delta_pct": _delta(changed.get("mean_mfe_pct"), baseline.get("mean_mfe_pct")),
            "mae_delta_pct": _delta(changed.get("mean_mae_pct"), baseline.get("mean_mae_pct")),
            "stop_first_delta_pct": _delta(changed.get("mean_stop_first_pct"), baseline.get("mean_stop_first_pct")),
            "target1_first_delta_pct": _delta(changed.get("mean_target1_first_pct"), baseline.get("mean_target1_first_pct")),
        }
    return {
        "quick_pool_changed_date_count": len(quick_changed),
        "quick_pool_changed_rate_pct": _pct(len(quick_changed), len(valid)),
        "quick_pool_changed_dates": [run.get("analysis_date") for run in quick_changed],
        "quick_pool_replacements": sum(int((((run.get("comparisons") or {}).get(variant) or {}).get("quick_pool_replacements")) or 0) for run in valid),
        "top5_changed_date_count": len(top5_changed),
        "top5_changed_rate_pct": _pct(len(top5_changed), len(valid)),
        "top5_changed_dates": [run.get("analysis_date") for run in top5_changed],
        "top5_replacements": sum(int((((run.get("comparisons") or {}).get(variant) or {}).get("top5_replacements")) or 0) for run in valid),
        "candidate_state_changes": sum(int((run.get("comparisons", {}).get(variant, {}).get("candidate_state_changes")) or 0) for run in valid),
        "risk_status_changes": sum(int((run.get("comparisons", {}).get(variant, {}).get("risk_status_changes")) or 0) for run in valid),
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
    source = payload.get("source_integrity") or {}
    definition = source.get("breakout_rs_definition") or {}
    fallback_source_hits = len(source.get("sector_market_fallback_source_hits") or [])
    detected_weights = [float(value) for value in (definition.get("weights") or [])]

    if rs_exact > 0 or rs_metric_dup > 0:
        rs_verdict = "CONFIRMED_RS_DUPLICATION"
    elif rs_breakouts > 0 and fallback_source_hits > 0 and rs_fallback_runtime > 0:
        rs_verdict = "RS_FALLBACK_DUPLICATION"
    else:
        rs_verdict = "RS_DISTINCT"

    ma_impact = _impact_summary(valid, MA120_FIXED, horizons)
    rs_impacts = {variant: _impact_summary(valid, variant, horizons) for variant in RS_VARIANTS}

    def aggregate_variant_stats(variant: str) -> dict[str, Any]:
        items = [(((run.get("integrity") or {}).get("breakout_rs_variants") or {}).get(variant) or {}) for run in valid]
        integer_keys = (
            "dedup_attempted", "dedup_supported", "passed_condition_removed", "score_changed_signals",
            "strategy_changed_signals", "breakout_to_other", "other_to_breakout", "condition_count_changed_signals",
        )
        result = {key: sum(int(item.get(key) or 0) for item in items) for key in integer_keys}
        result["kept_weight"] = RS_KEPT_WEIGHT[variant]
        result["removed_weight"] = RS_REMOVED_WEIGHT[variant]
        if variant == RS_RESTORE_10_8:
            result.update(market_weight=10, sector_condition_count=1)
        means = [_num(item.get("mean_breakout_score_delta")) for item in items]
        medians = [_num(item.get("median_breakout_score_delta")) for item in items]
        result["mean_breakout_score_delta"] = _mean([value for value in means if value is not None])
        result["median_breakout_score_delta"] = _median([value for value in medians if value is not None])
        result["counterfactual_supported"] = result["dedup_attempted"] == result["dedup_supported"]
        return result

    rs_variant_stats = {variant: aggregate_variant_stats(variant) for variant in RS_VARIANTS}

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

    if mode != "full":
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
    rs_defect = rs_verdict in {"CONFIRMED_RS_DUPLICATION", "RS_FALLBACK_DUPLICATION"}
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
    return {
        "valid_dates": len(valid),
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
        "breakout_rs": {
            "verdict": rs_verdict,
            "definition_condition": definition.get("condition_label"),
            "detected_duplicate_weights": detected_weights,
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
            "duplicate_conditions": _merge_count_dicts([((run.get("integrity") or {}).get("duplicate_conditions") or {}) for run in valid]),
            "duplicate_weights_detected": _merge_last_dicts([((run.get("integrity") or {}).get("duplicate_weights_used") or {}) for run in valid]),
        },
        "ma120_impact": ma_impact,
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
        baseline_map = {f"{item.get('market')}:{item.get('code')}": item for item in (variants.get(BASELINE) or {}).get("candidates", [])[:5]}
        for variant_name in (MA120_FIXED, *RS_VARIANTS):
            comparison = ((run.get("comparisons") or {}).get(variant_name) or {})
            if not comparison.get("top5_changed"):
                continue
            variant_map = {f"{item.get('market')}:{item.get('code')}": item for item in (variants.get(variant_name) or {}).get("candidates", [])[:5]}
            removed = [baseline_map[key] for key in baseline_map if key not in variant_map]
            added = [variant_map[key] for key in variant_map if key not in baseline_map]
            for index in range(max(len(removed), len(added))):
                old = removed[index] if index < len(removed) else {}
                new = added[index] if index < len(added) else {}
                row = {
                    "analysis_date": run.get("analysis_date"),
                    "variant": variant_name,
                    "removed_weight": RS_REMOVED_WEIGHT.get(variant_name),
                    "pair_index": index + 1,
                    "removed_market": old.get("market"),
                    "removed_code": old.get("code"),
                    "removed_name": old.get("name"),
                    "removed_strategy": old.get("strategy"),
                    "added_market": new.get("market"),
                    "added_code": new.get("code"),
                    "added_name": new.get("name"),
                    "added_strategy": new.get("strategy"),
                }
                for horizon in (5, 10, 20):
                    old_metric = _forward(old, horizon)
                    new_metric = _forward(new, horizon)
                    row[f"return_{horizon}d_delta"] = _delta(new_metric.get("return_pct"), old_metric.get("return_pct"))
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
    md_path = output_dir / f"scanner-strategy-integrity-summary_{stamp}.md"

    json_path.write_text(json.dumps(_safe_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    signal_fields = [
        "analysis_date", "market", "code", "name", "input_rows", "ma20", "ma60", "ma120", "computed_ma120",
        "ma_formula_verified", "trend_ma120_condition_missing", "ma120_would_pass",
        "relative_strength_market_pct", "relative_strength_sector_pct", "relative_strength_equal", "rs_group",
        "breakout_exact_duplicates", "baseline_quick_strategy", "baseline_quick_score",
        "ma120_quick_strategy", "ma120_quick_score",
        "rs_keep4_quick_strategy", "rs_keep4_quick_score", "rs_keep4_removed_weight", "rs_keep4_passed_removed",
        "rs_keep8_quick_strategy", "rs_keep8_quick_score", "rs_keep8_removed_weight", "rs_keep8_passed_removed",
        "rs_restore_quick_strategy", "rs_restore_quick_score", "rs_restore_evaluation",
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
        "removed_market", "removed_code", "removed_name", "removed_strategy",
        "added_market", "added_code", "added_name", "added_strategy",
        "return_5d_delta", "r_5d_delta", "removed_event_5d", "added_event_5d",
        "return_10d_delta", "r_10d_delta", "removed_event_10d", "added_event_10d",
        "return_20d_delta", "r_20d_delta", "removed_event_20d", "added_event_20d",
    ]
    with pairs_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        for row in _pair_rows(payload):
            writer.writerow(row)

    validation = payload.get("strategy_integrity_validation") or {}
    ma = validation.get("ma120") or {}
    rs = validation.get("breakout_rs") or {}
    ma_imp = validation.get("ma120_impact") or {}
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
        f"- Quick18 changed dates: **{ma_imp.get('quick_pool_changed_date_count')}**",
        f"- Top5 changed dates: **{ma_imp.get('top5_changed_date_count')}**",
        "",
        "## Breakout relative-strength integrity",
        "",
        f"- Verdict: **{rs.get('verdict')}**",
        f"- Detected duplicate weights: **{rs.get('detected_duplicate_weights')}**",
        f"- Predicate equivalent: **{rs.get('predicate_equivalent')}**",
        f"- Strategy eligible-score threshold: **{rs.get('eligible_score_threshold')}**",
        f"- Breakout evaluations: **{rs.get('breakout_evaluation_count')}**",
        f"- Exact duplicate evaluations: **{rs.get('exact_duplicate_evaluation_count')}**",
        f"- Duplicate metric evaluations: **{rs.get('metric_duplicate_evaluation_count')}**",
        f"- Fallback duplicate evaluations: **{rs.get('fallback_duplicate_evaluation_count')}**",
        f"- Sector available: **{rs.get('sector_available_count')}**",
        f"- Market fallback: **{rs.get('market_fallback_count')}**",
        f"- Both RS missing: **{rs.get('both_missing_count')}**",
        f"- Duplicate conditions: `{json.dumps(rs.get('duplicate_conditions') or {}, ensure_ascii=False)}`",
        "",
    ]

    lines[2:2] = ["Current: market 6 + sector 4 + sector 8", "Historical intended: market 10 + sector 8", ""]
    for variant_name in RS_VARIANTS:
        item = rs_variants.get(variant_name) or {}
        impact = item.get("impact") or {}
        lines.extend([
            f"### {variant_name}",
            "",
            f"- Market weight: **{item.get('market_weight', 6)}**",
            f"- Condition count changed signals: **{item.get('condition_count_changed_signals', 0)}**",
            f"- Candidate state changes: **{impact.get('candidate_state_changes')}**",
            f"- Risk status changes: **{impact.get('risk_status_changes')}**",
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
            f"- Quick18 changed dates: **{impact.get('quick_pool_changed_date_count')}**",
            f"- Quick18 replacements: **{impact.get('quick_pool_replacements')}**",
            f"- Top5 changed dates: **{impact.get('top5_changed_date_count')}**",
            f"- Top5 replacements: **{impact.get('top5_replacements')}**",
            "",
        ])

    restore_horizons = (rs_variants.get(RS_RESTORE_10_8) or {}).get("impact", {}).get("horizons", {})
    lines.extend(["#### RS_RESTORE_10_8 forward metrics", "",
                  "| Horizon | Mean return Δ | Median return Δ | Trimmed mean Δ | Mean R Δ | Median R Δ | Target1-first Δ | Stop-first Δ | MFE Δ | MAE Δ |",
                  "|---|---|---|---|---|---|---|---|---|---|"])
    for horizon, metric in restore_horizons.items():
        keys = ("mean_return_delta_pct", "median_return_delta_pct", "trimmed_return_delta_pct", "mean_r_delta", "median_r_delta", "target1_first_delta_pct", "stop_first_delta_pct", "mfe_delta_pct", "mae_delta_pct")
        lines.append("| " + " | ".join([f"{horizon}D"] + [str(metric.get(key)) for key in keys]) + " |")
    lines.append("")
    lines.extend([
        "## Counterfactual Top5 delta",
        "",
        "| Variant | Horizon | Mean return Δ | Median return Δ | Trimmed return Δ | Mean R Δ | Stop-first Δ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    table_variants = [("MA120_FIXED", ma_imp)] + [
        (variant_name, (rs_variants.get(variant_name) or {}).get("impact") or {}) for variant_name in RS_VARIANTS
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
        f"- Breakout duplicate source: `{rs.get('source_file')}`",
        f"- Sector→market fallback source hits: **{len(source.get('sector_market_fallback_source_hits') or [])}**",
        "",
        "The audit does not modify Production strategy definitions. Counterfactual variants exist only inside this offline runner.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "csv": str(signals_path), "pairs_csv": str(pairs_path), "markdown": str(md_path)}
