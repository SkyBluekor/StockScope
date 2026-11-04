"""GLOBAL-02-S2 UNSC official-notice contract inspector (research only).

No live fetch is enabled while official automated extraction/derivative rights
remain unverified. No database writes, provider text retention, or AI calls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.event_evidence.global02_official_updates import (
    OfficialUpdateError, blank_report, inspect_rows,
)

# Entirely invented fixtures, not real UN notices or sanctioned persons.
_SYNTHETIC = [
    {
        "change_date": "2026-01-15",
        "sanctions_regime_id": "1267",
        "permanent_reference_numbers": "QDi.901, QDe.902",
        "change_type": "Amendment",
        "number_of_entries_affected": "2",
        "official_notice_id": "SC/99991",
        "official_reference_url": "https://press.un.org/en/2026/sc99991.doc.htm",
    },
    {
        "change_date": "2026-01-16",
        "sanctions_regime_id": "1988",
        "permanent_reference_numbers": "TAi.901",
        "change_type": "De-listing",
        "number_of_entries_affected": "1",
        "official_notice_id": "SC/99992",
        "official_reference_url": "https://press.un.org/en/2026/sc99992.doc.htm",
    },
    {
        "change_date": "2026-01-17",
        "sanctions_regime_id": "1970",
        "permanent_reference_numbers": "LYe.901",
        "change_type": "Listing",
        "number_of_entries_affected": "1",
        "official_notice_id": "SC/99993",
        "official_reference_url": "https://press.un.org/en/2026/sc99993.doc.htm",
    },
]


def run(*, offline_fixture: bool = False, live: bool = False,
        confirm_personal_research: bool = False,
        observed_at_utc: str | None = None) -> dict[str, object]:
    if live:
        # Explicit opt-in is necessary but NOT sufficient. The UN terms do not
        # license automated extraction/derivative works for this project.
        result = blank_report("RIGHTS_UNVERIFIED")
        result["reason"] = (
            "OFFICIAL_AUTOMATED_EXTRACTION_AND_DERIVATIVE_RIGHTS_NOT_VERIFIED"
        )
        result["personal_research_confirmed"] = bool(confirm_personal_research)
        result["network_requests"] = 0
        return result
    if not offline_fixture:
        result = blank_report("NOT_STARTED")
        result["reason"] = "USE_OFFLINE_FIXTURE_OR_EXPLICIT_LIVE_RIGHTS_PREFLIGHT"
        result["network_requests"] = 0
        return result
    observed = observed_at_utc or datetime.now(timezone.utc).isoformat()
    try:
        report = inspect_rows(_SYNTHETIC, observed_at_utc=observed)
    except OfficialUpdateError as exc:
        report = blank_report("FIXTURE_VALIDATION_FAILED")
        report["reason"] = str(exc)
    report["data_origin"] = "SYNTHETIC_TEST_ROWS_NOT_REAL_UNSC_EVENTS"
    report["network_requests"] = 0
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--offline-fixture", action="store_true",
                         help="Validate synthetic notices without network or writes.")
    options.add_argument("--live", action="store_true",
                         help="Rights preflight only; live fetch remains blocked.")
    parser.add_argument("--confirm-personal-research", action="store_true",
                        help="Acknowledge personal use (does not grant source rights).")
    args = parser.parse_args(argv)
    result = run(
        offline_fixture=args.offline_fixture,
        live=args.live,
        confirm_personal_research=args.confirm_personal_research,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["source_status"] in {
        "OFFLINE_FIXTURE_VALIDATED_ONLY", "NOT_STARTED", "RIGHTS_UNVERIFIED",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
