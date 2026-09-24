from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data.common import (
    DataToolError,
    ensure_backend_import_path,
    file_state,
    holdings_db_path,
    latest_common_market_date,
    market_db_path,
    monitored_targets,
    sqlite_readonly,
    validate_holdings_db,
    validate_market_db,
)


def _iso(compact: str | None) -> str | None:
    value = str(compact or "")
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return None


def _backend_checks() -> dict[str, Any]:
    ensure_backend_import_path()
    result: dict[str, Any] = {}
    try:
        import app.main  # noqa: F401

        result["import"] = "PASS"
    except Exception as exc:
        result["import"] = "FAIL"
        result["import_error"] = str(exc)

    try:
        from app.core.config import get_settings

        settings = get_settings()
        result["settings"] = {
            "krx_api_key": bool(settings.krx_api_key),
            "dart_api_key": bool(settings.dart_api_key),
            "kis_credentials": bool(
                settings.kis_app_key
                and settings.kis_app_secret
                and settings.kis_account_no
            ),
        }
    except Exception as exc:
        result["settings"] = {
            "krx_api_key": False,
            "dart_api_key": False,
            "kis_credentials": False,
            "error": str(exc),
        }
    return result


def _frontend_checks() -> dict[str, Any]:
    return {
        "node": bool(shutil.which("node")),
        "npm": bool(shutil.which("npm.cmd") or shutil.which("npm")),
        "node_modules": (ROOT / "frontend" / "node_modules").is_dir(),
        "package_json": (ROOT / "frontend" / "package.json").is_file(),
    }


def _readiness_requirements() -> dict[str, int]:
    ensure_backend_import_path()
    from app.backtest.scanner import StockScannerService
    from app.holdings.chart import RANGE_BARS

    return {
        "analysis_min_rows": int(StockScannerService.MIN_HISTORY_ROWS),
        "analysis_calendar_days": int(
            StockScannerService.FAST_HISTORY_CALENDAR_DAYS
        ),
        "full_chart_rows": int(max(RANGE_BARS.values())),
    }


def _target_readiness(
    holdings_path: Path,
    market_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, str | None], dict[str, int]]:
    requirements = _readiness_requirements()
    targets = monitored_targets(holdings_path)
    latest_by_market: dict[str, str | None] = {
        "KOSPI": None,
        "KOSDAQ": None,
    }
    results: list[dict[str, Any]] = []

    with sqlite_readonly(market_path) as conn:
        for market in latest_by_market:
            latest_by_market[market] = _iso(
                latest_common_market_date(conn, market)
            )

        for target in targets:
            market = target["market"]
            ticker = target["ticker"]
            market_latest = latest_common_market_date(conn, market)

            row = conn.execute(
                """
                SELECT MAX(sd.bas_dd)
                FROM stock_daily sd
                WHERE sd.market=?
                  AND sd.stock_code=?
                  AND EXISTS(
                      SELECT 1 FROM day_status ds
                      WHERE ds.market=sd.market
                        AND ds.bas_dd=sd.bas_dd
                        AND ds.kind='stock'
                        AND ds.status='data'
                  )
                  AND EXISTS(
                      SELECT 1 FROM day_status di
                      WHERE di.market=sd.market
                        AND di.bas_dd=sd.bas_dd
                        AND di.kind='index'
                        AND di.status='data'
                  )
                  AND EXISTS(
                      SELECT 1 FROM main_index_daily mi
                      WHERE mi.market=sd.market
                        AND mi.bas_dd=sd.bas_dd
                  )
                """,
                (market, ticker),
            ).fetchone()
            ticker_latest = str(row[0] or "") if row else ""

            if len(ticker_latest) != 8:
                results.append(
                    {
                        **target,
                        "status": "MISSING",
                        "analysis_ready": False,
                        "latest_date": None,
                        "stock_history_rows": 0,
                        "index_history_rows": 0,
                        "chart_rows": 0,
                        "message": "확정 EOD 데이터가 없습니다.",
                    }
                )
                continue

            latest_date = datetime.strptime(ticker_latest, "%Y%m%d").date()
            start = (
                latest_date
                - timedelta(days=requirements["analysis_calendar_days"])
            ).strftime("%Y%m%d")

            stock_rows = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM stock_daily
                    WHERE market=? AND stock_code=?
                      AND bas_dd>=? AND bas_dd<=?
                    """,
                    (market, ticker, start, ticker_latest),
                ).fetchone()[0]
            )
            index_rows = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM main_index_daily
                    WHERE market=? AND bas_dd>=? AND bas_dd<=?
                    """,
                    (market, start, ticker_latest),
                ).fetchone()[0]
            )
            chart_rows = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM stock_daily
                    WHERE market=? AND stock_code=? AND bas_dd<=?
                    """,
                    (market, ticker, ticker_latest),
                ).fetchone()[0]
            )

            aligned = bool(
                market_latest
                and ticker_latest == market_latest
            )
            analysis_ready = bool(
                aligned
                and stock_rows >= requirements["analysis_min_rows"]
                and index_rows > 0
            )

            if not analysis_ready:
                status = "MISSING"
                message = (
                    f"분석 이력 부족 또는 최신 시장일 불일치 "
                    f"({stock_rows}/{requirements['analysis_min_rows']} rows)"
                )
            elif chart_rows < requirements["full_chart_rows"]:
                status = "PARTIAL"
                message = (
                    f"분석 가능, 1년 차트는 부분 데이터 "
                    f"({chart_rows}/{requirements['full_chart_rows']} rows)"
                )
            else:
                status = "READY"
                message = "분석 및 1년 차트 준비 완료"

            results.append(
                {
                    **target,
                    "status": status,
                    "analysis_ready": analysis_ready,
                    "latest_date": _iso(ticker_latest),
                    "stock_history_rows": stock_rows,
                    "index_history_rows": index_rows,
                    "chart_rows": chart_rows,
                    "message": message,
                }
            )

    return results, latest_by_market, requirements


def collect_report(
    *,
    holdings_path: Path | None = None,
    market_path: Path | None = None,
) -> dict[str, Any]:
    holdings = Path(holdings_path or holdings_db_path())
    market = Path(market_path or market_db_path())

    before_holdings = file_state(holdings)
    before_market = file_state(market)

    report: dict[str, Any] = {
        "python": {
            "version": sys.version.split()[0],
            "supported": sys.version_info >= (3, 11),
        },
        "backend": _backend_checks(),
        "frontend": _frontend_checks(),
        "holdings": {
            "path": str(holdings),
            "status": "MISSING",
        },
        "market_store": {
            "path": str(market),
            "status": "MISSING",
        },
        "targets": [],
        "market_latest_confirmed": {
            "KOSPI": None,
            "KOSDAQ": None,
        },
        "requirements": None,
        "network_requests": 0,
    }

    structural_error = False

    if holdings.is_file():
        try:
            validation = validate_holdings_db(holdings)
            report["holdings"] = {
                "path": str(holdings),
                "status": "PASS",
                **validation,
            }
        except DataToolError as exc:
            structural_error = True
            report["holdings"] = {
                "path": str(holdings),
                "status": "ERROR",
                "error": str(exc),
            }

    if market.is_file():
        try:
            validation = validate_market_db(market)
            report["market_store"] = {
                "path": str(market),
                "status": "PASS",
                **validation,
            }
        except DataToolError as exc:
            structural_error = True
            report["market_store"] = {
                "path": str(market),
                "status": "ERROR",
                "error": str(exc),
            }

    if (
        report["holdings"]["status"] == "PASS"
        and report["market_store"]["status"] == "PASS"
    ):
        try:
            targets, latest, requirements = _target_readiness(
                holdings,
                market,
            )
            report["targets"] = targets
            report["market_latest_confirmed"] = latest
            report["requirements"] = requirements
        except Exception as exc:
            structural_error = True
            report["readiness_error"] = str(exc)

    after_holdings = file_state(holdings)
    after_market = file_state(market)
    read_only_preserved = (
        before_holdings == after_holdings
        and before_market == after_market
    )
    report["read_only_preserved"] = read_only_preserved
    if not read_only_preserved:
        structural_error = True

    backend_ok = report["backend"].get("import") == "PASS"
    python_ok = bool(report["python"]["supported"])
    frontend_ok = all(
        bool(report["frontend"].get(key))
        for key in ("node", "npm", "package_json")
    )
    setup_ready = backend_ok and python_ok and frontend_ok

    data_gap_count = sum(
        1
        for item in report["targets"]
        if item.get("status") in {"MISSING", "ERROR"}
    )
    partial_count = sum(
        1
        for item in report["targets"]
        if item.get("status") == "PARTIAL"
    )

    if structural_error or not setup_ready:
        result = "ERROR"
    elif report["holdings"]["status"] != "PASS":
        result = "SETUP_REQUIRED"
    elif report["market_store"]["status"] != "PASS":
        result = "READY_WITH_DATA_GAPS"
    elif data_gap_count:
        result = "READY_WITH_DATA_GAPS"
    elif partial_count:
        result = "READY_WITH_PARTIAL_CHARTS"
    else:
        result = "READY"

    report["summary"] = {
        "result": result,
        "monitored_stocks": len(report["targets"]),
        "analysis_ready": sum(
            1 for item in report["targets"] if item.get("analysis_ready")
        ),
        "data_gaps": data_gap_count,
        "partial_charts": partial_count,
    }
    return report


def _print_text(report: dict[str, Any], *, verbose: bool) -> None:
    print("=" * 78)
    print("STOCKSCOPE DATA DOCTOR")
    print("=" * 78)
    print(
        "Python environment       ",
        "PASS" if report["python"]["supported"] else "FAIL",
        report["python"]["version"],
    )
    print(
        "Backend imports          ",
        report["backend"].get("import", "FAIL"),
    )
    print(
        "Holdings DB              ",
        report["holdings"]["status"],
    )
    print(
        "Market Store             ",
        report["market_store"]["status"],
    )
    print(
        "Frontend dependencies    ",
        "PASS"
        if all(
            report["frontend"].get(key)
            for key in ("node", "npm", "node_modules", "package_json")
        )
        else "CHECK",
    )
    print("Doctor network requests   0")
    print(
        "Read-only preserved      ",
        "PASS" if report["read_only_preserved"] else "FAIL",
    )
    print("")
    print(
        "KOSPI latest confirmed   ",
        report["market_latest_confirmed"].get("KOSPI") or "-",
    )
    print(
        "KOSDAQ latest confirmed  ",
        report["market_latest_confirmed"].get("KOSDAQ") or "-",
    )
    print("")
    summary = report["summary"]
    print("Monitored stocks          ", summary["monitored_stocks"])
    print("Ready for analysis        ", summary["analysis_ready"])
    print("Need data                 ", summary["data_gaps"])
    print("Partial 1y chart          ", summary["partial_charts"])

    if verbose and report["targets"]:
        print("")
        print("TARGETS")
        for item in report["targets"]:
            print(
                f" - {item['market']} {item['ticker']} {item['name']}: "
                f"{item['status']} | {item['message']}"
            )

    print("")
    print("RESULT")
    print(summary["result"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope 실행 환경과 런타임 데이터 상태를 읽기 전용으로 검사합니다."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = collect_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(report, verbose=args.verbose)
    # DATA.1 doctor reports readiness; missing market data is not a process error.
    return 1 if report["summary"]["result"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
