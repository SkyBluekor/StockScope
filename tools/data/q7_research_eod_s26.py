"""S26 research-only EOD gap preparation.

A missing local weekday is NEVER inferred to be an open market session.
Only a real matching KRX stock+main-index pair may be append-committed to
the ISOLATED research snapshot, reusing S20's strict atomic write validator.
Missing/partial/conflicting source data fails closed. No production DB writes.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable

from app.jev.research_scanner_s24 import ResearchCaptureError
from tools.data.prospective_outcome_refresh import GapFillError, _commit_new_day

MAX_RESEARCH_PREP_DAYS = 3
VERSION = "Q7_S26_ISOLATED_EOD_PREPARATION_V1"


def candidate_missing_days(plan: dict[str, Any]) -> list[str]:
    """Strict zero-side-effect plan: only wholly missing recent weekdays."""
    if plan.get("session_evidence_status") != "UNVERIFIED_PRIOR_WEEKDAY_GAP":
        return []
    if plan.get("closure_data_conflict_dates"):
        return []
    if plan.get("data_readiness_reason") != "UNVERIFIED_PRIOR_WEEKDAY_GAP":
        return []
    source = plan.get("latest_complete_eod_date")
    age = plan.get("local_market_date_age_days")
    if not isinstance(source, str) or type(age) is not int or not 1 <= age <= 4:
        return []
    states = plan.get("unverified_prior_weekday_states")
    if not isinstance(states, list) or not 1 <= len(states) <= MAX_RESEARCH_PREP_DAYS:
        return []
    days: list[str] = []
    for entry in states:
        if not isinstance(entry, dict) or entry.get("state") != "MISSING":
            return []
        raw = entry.get("date")
        if not isinstance(raw, str):
            return []
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            return []
        if day.isoformat() != raw or day.isoformat() <= source or raw in days:
            return []
        days.append(raw)
    if days != sorted(days):
        return []
    return days


async def prepare_missing_days(
    *, market: str, days: list[str], destination_db: Path,
    research_root: Path, provider: Any | None = None,
) -> dict[str, Any]:
    """Fetch bounded EOD into *research* clone; never overwrite existing rows.

    No retry or calendar inference if KRX has not published yesterday's
    stock/index pair. A partial previous attempt must be manually reviewed.
    """
    if market not in ("KOSPI", "KOSDAQ") or not isinstance(days, list):
        raise ResearchCaptureError("RESEARCH_EOD_PREP_ARGUMENT_INVALID")
    if not 1 <= len(days) <= MAX_RESEARCH_PREP_DAYS or days != sorted(set(days)):
        raise ResearchCaptureError("RESEARCH_EOD_PREP_TARGETS_INVALID")
    for day in days:
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ResearchCaptureError("RESEARCH_EOD_PREP_DATE_INVALID") from exc
    db = Path(destination_db).resolve()
    root = Path(research_root).resolve()
    if root not in db.parents or not db.is_file():
        raise ResearchCaptureError("RESEARCH_EOD_PREP_SNAPSHOT_NOT_ISOLATED")

    if provider is None:
        from app.core.config import get_settings
        from app.market.krx_budget import KrxApiBudget
        from app.market.providers.krx import KrxProvider
        key = get_settings().krx_api_key
        if not key:
            raise ResearchCaptureError("RESEARCH_EOD_PREP_KRX_API_KEY_REQUIRED")

        class ResearchEodKrx(KrxProvider):
            _cache_dir = root / "krx_cache"
            _rows_cache = {}
            _cache_expiry = {}
            _inflight_tasks = {}

        provider = ResearchEodKrx(
            key, budget=KrxApiBudget(db_path=root / "budget.sqlite3", safe_limit=60),
        )
    try:
        provider.assert_budget(2 * len(days))
    except Exception as exc:
        raise ResearchCaptureError("RESEARCH_EOD_PREP_KRX_BUDGET_BLOCKED") from exc

    stored: list[dict[str, Any]] = []
    await provider.open_session()
    try:
        for day in days:
            from app.market.session_calendar_s21 import closure_evidence
            if closure_evidence(date.fromisoformat(day)) is not None:
                raise ResearchCaptureError("RESEARCH_EOD_PREP_VERIFIED_CLOSURE_CONFLICT")
            try:
                stocks = await provider.stock_daily(market, day)
                indices = await provider.index_daily(market, day)
            except Exception as exc:
                raise ResearchCaptureError("RESEARCH_EOD_PREP_PROVIDER_UNAVAILABLE") from exc

            compact = day.replace("-", "")
            if (not isinstance(stocks, dict) or not isinstance(indices, dict)
                    or stocks.get("date") != compact or indices.get("date") != compact):
                raise ResearchCaptureError("RESEARCH_EOD_PREP_PROVIDER_DATE_MISMATCH")
            stock_rows = stocks.get("rows")
            index_rows = indices.get("rows")
            if not stock_rows and not index_rows:
                # Empty response is not evidence of a holiday or current EOD.
                raise ResearchCaptureError("RESEARCH_EOD_PREP_EMPTY_KRX_NOT_CLOSURE_PROOF")
            if (not isinstance(stock_rows, list) or not isinstance(index_rows, list)
                    or not stock_rows or not index_rows):
                raise ResearchCaptureError("RESEARCH_EOD_PREP_INCOMPLETE_PROVIDER_PAIR")
            expected_index = "코스피" if market == "KOSPI" else "코스닥"
            main = next(
                (x for x in index_rows if isinstance(x, dict)
                 and x.get("name") == expected_index), None,
            )
            if main is None:
                raise ResearchCaptureError("RESEARCH_EOD_PREP_MAIN_INDEX_NOT_FOUND")
            try:
                count = _commit_new_day(db, market, day, stock_rows, main)
            except (GapFillError, OSError, ValueError) as exc:
                raise ResearchCaptureError("RESEARCH_EOD_PREP_" + (
                    str(exc) if isinstance(exc, GapFillError) else "ATOMIC_WRITE_FAILED"
                )) from exc
            stored.append({"date": day, "stock_rows": count, "index_rows": 1})
    finally:
        await provider.close_session()

    return {
        "version": VERSION,
        "market": market,
        "stored_days": stored,
        "research_only_market_db_writes": len(stored),
        "krx_network_requests_reported": (
            provider.request_stats().get("network_requests")
            if callable(getattr(provider, "request_stats", None)) else None
        ),
        "unknown_market_closures_inferred": False,
        "production_market_db_writes": 0,
        "production_simulation_db_writes": 0,
        "jev_model_calls": 0,
        "q7_approval_eligible": False,
    }
