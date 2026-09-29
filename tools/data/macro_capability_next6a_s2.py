from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.core.config import get_settings
from app.macro.identity import content_hash
from app.macro.providers import probe_fred_dgs10, probe_kis_macro_capabilities


REPORT_CONTRACT_VERSION = "VN_NEXT6A_S2_CAPABILITY_REPORT_V1"


def _default_dates() -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=14)
    return start.isoformat(), end.isoformat()


def build_report(
    *,
    provider: str,
    start_date: str,
    end_date: str,
    kis_index_code: str,
    kis_fx_code: str | None,
    kis_treasury_code: str | None,
) -> dict[str, Any]:
    provider_name = provider.strip().upper()
    if provider_name not in {"FRED", "KIS", "ALL"}:
        raise ValueError("provider must be FRED, KIS, or ALL.")
    settings = get_settings()
    results: list[dict[str, Any]] = []
    if provider_name in {"FRED", "ALL"}:
        results.append(
            probe_fred_dgs10(
                settings=settings,
                observation_start=start_date,
                observation_end=end_date,
            ).to_dict()
        )
    if provider_name in {"KIS", "ALL"}:
        results.extend(
            item.to_dict()
            for item in probe_kis_macro_capabilities(
                settings=settings,
                start_date=start_date,
                end_date=end_date,
                index_code=kis_index_code,
                fx_code=kis_fx_code,
                treasury_code=kis_treasury_code,
            )
        )
    payload = {
        "contract_version": REPORT_CONTRACT_VERSION,
        "provider_scope": provider_name,
        "probe_start": start_date,
        "probe_end": end_date,
        "results": results,
        "production_decision_approved": False,
        "secret_values_included": False,
    }
    payload["report_hash"] = content_hash(payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    start, end = _default_dates()
    parser = argparse.ArgumentParser(
        description="NEXT-6A-S2 Macro provider capability를 명시적으로 확인합니다."
    )
    parser.add_argument(
        "--provider",
        choices=("FRED", "KIS", "ALL"),
        default="ALL",
    )
    parser.add_argument("--start", default=start)
    parser.add_argument("--end", default=end)
    parser.add_argument(
        "--kis-index-code",
        default=".DJI",
        help="공식 KIS 예제에서 확인된 해외지수 probe code. 기본값 .DJI",
    )
    parser.add_argument(
        "--kis-fx-code",
        default=None,
        help="공식 master/example에서 확인한 환율 code. 생략 시 추측하지 않습니다.",
    )
    parser.add_argument(
        "--kis-treasury-code",
        default=None,
        help="공식 master/example에서 확인한 국채 code. 생략 시 추측하지 않습니다.",
    )
    parser.add_argument(
        "--no-report-file",
        action="store_true",
        help="runtime JSON report 파일 생성을 생략합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = build_report(
        provider=args.provider,
        start_date=args.start,
        end_date=args.end,
        kis_index_code=args.kis_index_code,
        kis_fx_code=args.kis_fx_code,
        kis_treasury_code=args.kis_treasury_code,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not args.no_report_file:
        reports = BACKEND / "runtime" / "macro" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        target = reports / f"macro-capability_{report['report_hash'][:16]}.json"
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("")
        print("Report:", target)

    blocking = {
        "NOT_CONFIGURED",
        "NOT_AUTHORIZED",
        "ERROR",
    }
    return 2 if any(item["status"] in blocking for item in report["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
