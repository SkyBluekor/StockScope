from __future__ import annotations

import ast
import os
import re
import tempfile
from pathlib import Path
from typing import Any

MARKET_LABEL = "20일 시장 대비 상대강도 양호"
SECTOR_LABEL = "20일 업종 대비 상대강도 양호"


def _number(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    return None


def _definition(text: str) -> dict[str, Any]:
    tree = ast.parse(text)
    breakout: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_breakout":
            breakout = node
            break
    if breakout is None:
        raise RuntimeError("_breakout() function was not found in strategy/engine.py")

    market: list[dict[str, Any]] = []
    sector: list[dict[str, Any]] = []
    for node in ast.walk(breakout):
        if not isinstance(node, ast.Tuple) or len(node.elts) < 3:
            continue
        label_node, weight_node, predicate_node = node.elts[:3]
        if not isinstance(label_node, ast.Constant) or not isinstance(label_node.value, str):
            continue
        weight = _number(weight_node)
        if weight is None:
            continue
        item = {
            "label": label_node.value,
            "weight": weight,
            "line": int(getattr(node, "lineno", 0) or 0),
            "end_line": int(getattr(node, "end_lineno", 0) or getattr(node, "lineno", 0) or 0),
            "predicate": ast.dump(predicate_node, annotate_fields=True, include_attributes=False),
        }
        if label_node.value == MARKET_LABEL:
            market.append(item)
        elif label_node.value == SECTOR_LABEL:
            sector.append(item)
    return {"market": market, "sector": sector}


def _weights(items: list[dict[str, Any]]) -> list[float]:
    return sorted(float(item["weight"]) for item in items)


def _verify_production(definition: dict[str, Any]) -> None:
    market = definition["market"]
    sector = definition["sector"]
    if len(market) != 1 or _weights(market) != [10.0]:
        raise RuntimeError(f"Expected one Market RS weight 10 after patch; found {_weights(market)}")
    if len(sector) != 1 or _weights(sector) != [8.0]:
        raise RuntimeError(f"Expected one Sector RS weight 8 after patch; found {_weights(sector)}")


def patch_engine(path: Path) -> str:
    original = path.read_text(encoding="utf-8")
    definition = _definition(original)
    market_weights = _weights(definition["market"])
    sector_weights = _weights(definition["sector"])

    if market_weights == [10.0] and sector_weights == [8.0] and len(definition["sector"]) == 1:
        _verify_production(definition)
        return "already-applied"

    if market_weights != [6.0] or sector_weights != [4.0, 8.0]:
        raise RuntimeError(
            "Refusing to patch unexpected Breakout RS definition. "
            f"Expected legacy market=[6], sector=[4, 8]; found market={market_weights}, sector={sector_weights}."
        )
    sector_predicates = {item["predicate"] for item in definition["sector"]}
    if len(sector_predicates) != 1:
        raise RuntimeError("Refusing to patch: the two legacy Sector RS predicates are not equivalent.")

    lines = original.splitlines(keepends=True)
    market_item = definition["market"][0]
    market_index = int(market_item["line"]) - 1
    market_line = lines[market_index]
    pattern = rf'(\(\s*"{re.escape(MARKET_LABEL)}"\s*,\s*)6(\s*,)'
    patched_line, count = re.subn(pattern, r"\g<1>10\2", market_line, count=1)
    if count != 1:
        raise RuntimeError("Could not safely rewrite Market RS weight 6 -> 10 on the expected tuple line.")
    lines[market_index] = patched_line

    sector4 = next(item for item in definition["sector"] if float(item["weight"]) == 4.0)
    start = int(sector4["line"]) - 1
    end = int(sector4["end_line"])
    del lines[start:end]

    updated = "".join(lines)
    _verify_production(_definition(updated))

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".c4g-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return "patched"


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    engine_path = backend_root / "app" / "strategy" / "engine.py"
    if not engine_path.exists():
        raise SystemExit(f"Missing Production strategy engine: {engine_path}")
    result = patch_engine(engine_path)
    definition = _definition(engine_path.read_text(encoding="utf-8"))
    print(f"c.4g Breakout RS Production fix: {result}")
    print(f"market weights={_weights(definition['market'])}, sector weights={_weights(definition['sector'])}")
    print("historical Sector RS activation gate was not changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
