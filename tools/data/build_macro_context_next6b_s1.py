from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.context import MacroContextUsage, build_macro_context
from app.macro.reader import LocalMacroReader
from tools.data.common import macro_db_path


def _usage(value: str) -> MacroContextUsage:
    normalized = value.strip().lower()
    mapping = {
        "reference": MacroContextUsage.REFERENCE_SHADOW,
        "reference_shadow": MacroContextUsage.REFERENCE_SHADOW,
        "historical": MacroContextUsage.HISTORICAL_EVALUATION,
        "historical_evaluation": MacroContextUsage.HISTORICAL_EVALUATION,
    }
    if normalized not in mapping:
        raise argparse.ArgumentTypeError(
            "usage must be reference or historical."
        )
    return mapping[normalized]


def _write_artifact(context: dict[str, object]) -> Path:
    directory = BACKEND / "runtime" / "macro" / "context"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{context['context_id']}.json"
    serialized = json.dumps(
        context,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"

    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current == serialized:
            return target
        raise RuntimeError(
            f"Context artifact identity collision: {target}"
        )

    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f"{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as fp:
            fp.write(serialized)
            fp.flush()
            os.fsync(fp.fileno())
            temporary_path = fp.name
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6B-S1 deterministic Macro Context를 Local Macro Store에서 "
            "read-only로 생성합니다."
        )
    )
    parser.add_argument(
        "--cutoff",
        required=True,
        help="timezone-aware ISO-8601 decision cutoff",
    )
    parser.add_argument(
        "--usage",
        type=_usage,
        default=MacroContextUsage.REFERENCE_SHADOW,
        help="reference 또는 historical",
    )
    parser.add_argument(
        "--write-artifact",
        action="store_true",
        help="immutable JSON context artifact를 runtime/macro/context에 저장합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = macro_db_path()
    reader = LocalMacroReader(path)
    context = build_macro_context(
        reader=reader,
        decision_cutoff=args.cutoff,
        usage=args.usage,
    )
    print(json.dumps(context, ensure_ascii=False, indent=2))

    if args.write_artifact:
        target = _write_artifact(context)
        print("")
        print("Artifact:", target)

    return 0 if context["status"] != "UNAVAILABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
