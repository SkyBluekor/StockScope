from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.core.config import get_settings
from app.integrations.fred import FredClient, FredConfigurationError
from app.macro.providers import collect_fred_dgs10
from app.macro.store import MacroStore
from tools.data.common import macro_db_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NEXT-6A-S2 bounded live Macro ingestion. 현재 FRED DGS10만 허용합니다."
    )
    parser.add_argument("--provider", choices=("FRED",), default="FRED")
    parser.add_argument("--series", choices=("DGS10",), default="DGS10")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--as-of",
        default=None,
        help="FRED realtime as-of date. 생략하면 --end를 사용합니다.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="설정/Store/요청 계획만 확인하고 network/DB write를 수행하지 않습니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = macro_db_path()
    store = MacroStore(path)
    state = store.inspect()

    if not state.get("present"):
        print("ERROR: Macro Store가 준비되지 않았습니다.")
        print("Run: .\.venv\Scripts\python.exe .\tools\data\migrate_macro_next6a_s1.py")
        return 2

    settings = get_settings()
    plan = {
        "provider": args.provider,
        "series": args.series,
        "start": args.start,
        "end": args.end,
        "as_of": args.as_of or args.end,
        "macro_db": str(path),
        "network": "0" if args.check_only else "EXPLICIT_BOUNDED",
        "db_write": 0 if args.check_only else "ON_SUCCESS",
        "production_decision_approved": False,
    }
    if args.check_only:
        configured = bool(settings.fred_api_key)
        plan["fred_configured"] = configured
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0 if configured else 2

    try:
        with FredClient(settings) as client:
            result = collect_fred_dgs10(
                store=store,
                client=client,
                observation_start=args.start,
                observation_end=args.end,
                as_of_date=args.as_of,
            )
    except FredConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
