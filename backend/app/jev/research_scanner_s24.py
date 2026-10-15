"""S24 isolated research-only Scanner source identities, NEVER a production pin.

The current 10 strategy definitions are captured BEFORE a new research run.
They are fed to the unmodified Scanner strategy engine as an explicit pin, not
copied onto old Scanner output. This does NOT make them Q7 operating policies.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo

from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.models import StrategyName
from app.strategy.production_selection_policy import (
    SELECTION_POLICY_CONTRACT_VERSION, SelectionPolicyPin,
)
from app.strategy.semantic_identity_bridge import scanner_repro_candidate_key

VERSION = "Q7_S24_ISOLATED_RESEARCH_SCANNER_V1"
SOURCE = "RESEARCH_ISOLATED_NOT_Q7_APPROVED"
KST = ZoneInfo("Asia/Seoul")
START = time(5, 0)
END = time(8, 45)


class ResearchCaptureError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def research_pin() -> SelectionPolicyPin:
    """Bind the real engine definitions for a research run, NOT active policy."""
    definitions = current_strategy_definitions()
    expected = {s.value for s in StrategyName if s is not StrategyName.NO_TRADE}
    rows = sorted(
        ((d.strategy_version_id, d.strategy_key, d.definition_hash) for d in definitions),
        key=lambda x: x[1],
    )
    if ({x[1] for x in rows} != expected or len(rows) != len(expected)
            or any(not x[0] or not x[2] for x in rows)):
        raise ResearchCaptureError("RESEARCH_STRATEGY_DEFINITIONS_INCOMPLETE")
    identity = {
        "contract_version": VERSION, "source": SOURCE,
        "selection_contract": SELECTION_POLICY_CONTRACT_VERSION,
        "strategies": rows,
    }
    identity_hash = digest(identity)
    return SelectionPolicyPin(
        policy_id="research-" + identity_hash[:24],
        policy_hash=identity_hash,
        policy_contract_version=SELECTION_POLICY_CONTRACT_VERSION,
        policy_source=SOURCE,
        fallback_used=False, fallback_reason=None,
        operating_strategies=tuple(rows),
        scanner_baseline_id=None,
        production_fingerprint=None,
        production_policy_fingerprint=None,
    )


def recent_eod_source_date(
    clock: datetime, *, complete_market_day: date | None,
) -> date:
    """No backdating. Never claim a capture is a precommitted prediction."""
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ResearchCaptureError("RESEARCH_AWARE_KST_CLOCK_REQUIRED")
    current = clock.astimezone(KST)
    if current.weekday() >= 5 or not START <= current.time().replace(tzinfo=None) <= END:
        raise ResearchCaptureError("RESEARCH_PREMARKET_WINDOW_REQUIRED")
    day = complete_market_day
    if day is None or type(day) is not date or not 1 <= (current.date() - day).days <= 4:
        raise ResearchCaptureError("RESEARCH_FRESH_EOD_REQUIRED")
    return day


def receipt_for_scanner(
    result: dict[str, Any], *, policy: SelectionPolicyPin,
    source_date: date, market: str, recorded_at: datetime,
) -> dict[str, Any]:
    """Keep all original Scanner fields; never posthoc-fill strategy IDs."""
    if (result.get("scanner_cache_hit") is not False
            or result.get("requested_as_of") != source_date.isoformat()
            or result.get("market_scope") != market
            or result.get("strategy_selection_policy") != policy.metadata()):
        raise ResearchCaptureError("RESEARCH_SCANNER_EXECUTION_PROVENANCE_MISMATCH")
    if result.get("partial_data") is True or result.get("preparation_required"):
        raise ResearchCaptureError("RESEARCH_SCANNER_PARTIAL_OR_PREPARATION_REQUIRED")
    data_dates = result.get("data_dates")
    if not isinstance(data_dates, dict) or data_dates.get(market) != source_date.isoformat():
        raise ResearchCaptureError("RESEARCH_SCANNER_SOURCE_DATE_MISMATCH")
    finger = result.get("input_fingerprint")
    if not isinstance(finger, dict) or not finger.get("id"):
        raise ResearchCaptureError("RESEARCH_INPUT_FINGERPRINT_MISSING")
    candidates = result.get("candidates")
    more = result.get("more_candidates")
    if not isinstance(candidates, list) or not isinstance(more, list):
        raise ResearchCaptureError("RESEARCH_RESULT_CANDIDATES_INVALID")
    original = candidates + more
    if len(original) > 20 or len(original) != len({(x.get("market"), x.get("code")) for x in original if isinstance(x, dict)}):
        raise ResearchCaptureError("RESEARCH_RESULT_DUPLICATE_OR_LIMIT")
    entry_count = 0
    for item in original:
        if not isinstance(item, dict):
            raise ResearchCaptureError("RESEARCH_RESULT_CANDIDATE_INVALID")
        ref = policy.strategy_reference(str(item.get("strategy") or ""))
        if (not ref or not ref.get("strategy_version_id")
                or not ref.get("definition_hash")
                or item.get("strategy_version_id") != ref["strategy_version_id"]
                or item.get("strategy_definition_hash") != ref["definition_hash"]):
            raise ResearchCaptureError("RESEARCH_ORIGINAL_STRATEGY_IDENTITY_MISMATCH")
        if not all(scanner_repro_candidate_key(item)):
            raise ResearchCaptureError("RESEARCH_ORIGINAL_SCANNER_RANK_INVALID")
        if item.get("data_date") != source_date.isoformat():
            raise ResearchCaptureError("RESEARCH_CANDIDATE_SOURCE_DATE_MISMATCH")
        entry_count += item.get("action") == "ENTRY_CANDIDATE"

    # Do not take production Prospective/JEV snapshots or rewrite baseline.
    # No independent time or KRX publication evidence is obtainable here.
    payload = {
        "version": VERSION, "authority": SOURCE,
        "recorded_at_local_unverified": recorded_at.isoformat(),
        "source_date": source_date.isoformat(),
        "market_scope": market,
        "scanner_version": result.get("version"),
        "selection_policy": policy.metadata(),
        "original_strategy_rows": [
            {"strategy_version_id": v, "strategy_key": k, "definition_hash": h}
            for v, k, h in policy.operating_strategies
        ],
        "scanner_fingerprint": finger,
        "scanner_reproducibility_audit": result.get("diagnostics", {}).get("reproducibility_audit"),
        "scanner_cache_hit": False,
        "original_scanner_candidates": original,
        "candidate_count": len(original),
        "entry_candidates": entry_count,
        "q7_approval_eligible": False,
        "production_policy_activation_allowed": False,
        "q7_study_bound": False,
        "trusted_precommit_timestamp_proven": False,
        "independent_capture_timestamp_proven": False,
        "market_publication_timestamp_proven": False,
        "baseline_scanner_equivalence_proven": False,
        "jev_model_improvement_verified": False,
        "provider_calls": 0,
        "orders": 0,
        "production_scanner_result_modified": False,
        "source_market_db_writes": 0,
        "production_simulation_db_writes": 0,
        "evaluation_use": "DESCRIPTIVE_RESEARCH_ONLY",
    }
    return {
        **payload,
        "payload_hash": digest(payload),
    }
