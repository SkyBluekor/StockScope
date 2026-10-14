"""Inspect a manually downloaded KRX annual holiday export, without side effects.

Examples:
  python tools/data/krx_calendar_audit_s23.py --source-file holiday.json --year 2026
  python tools/data/krx_calendar_audit_s23.py --source-file holiday.csv --year 2026 --expected-sha256 ...
This tool NEVER downloads files or changes the market calendar / runtime DB.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.market.calendar_source_audit_s23 import (
    MAX_SOURCE_BYTES, CalendarSourceAuditError, audit_source,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="S23-C local KRX holiday export audit (read-only)")
    p.add_argument("--source-file", type=Path, required=True)
    p.add_argument("--year", type=int, default=2026)
    p.add_argument("--expected-sha256", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        path = args.source_file.expanduser()
        if path.suffix.lower() not in (".json", ".csv"):
            raise CalendarSourceAuditError("ONLY_ORIGINAL_JSON_OR_CSV_EXPORTS_SUPPORTED")
        if not path.is_file():
            raise CalendarSourceAuditError("SOURCE_FILE_NOT_FOUND")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise CalendarSourceAuditError("SOURCE_MISSING_OR_OVERSIZE")
        report = audit_source(
            path.read_bytes(), year=args.year, source_format=path.suffix.lower()[1:],
            expected_sha256=args.expected_sha256,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["status"] == "MATCHES_REVIEWED_CLOSURES" else 2
    except (OSError, CalendarSourceAuditError) as exc:
        reason = str(exc) if isinstance(exc, CalendarSourceAuditError) else "SOURCE_FILE_READ_FAILED"
        print(json.dumps({
            "status": "BLOCKED", "reason": reason,
            "full_calendar_eligible": False, "runtime_calendar_updated": False,
            "external_requests": 0, "runtime_db_writes": 0,
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
