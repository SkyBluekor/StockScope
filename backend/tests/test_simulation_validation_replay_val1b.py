from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.backtest.scanner import StockScannerService
from app.simulation.validation_catalog import HistoricalValidationCatalog
from app.simulation.validation_replay import (
    HistoricalValidationReplayError,
    HistoricalValidationReplayService,
)


class FakeMarketStore:
    def day_status_range(self, market: str, start_dd: str, end_dd: str):
        start = date(int(start_dd[:4]), int(start_dd[4:6]), int(start_dd[6:8]))
        end = date(int(end_dd[:4]), int(end_dd[4:6]), int(end_dd[6:8]))
        result = {}
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                key = cursor.strftime("%Y%m%d")
                result[(key, "stock")] = "data"
                result[(key, "index")] = "data"
            cursor += timedelta(days=1)
        return result


class FakeScanner:
    def __init__(self, *, mode: str = "ok"):
        self.mode = mode
        self.calls: list[str] = []

    async def run(self, *, market_scope, as_of_date, candidate_limit, force_refresh, allow_large_sync):
        self.calls.append(as_of_date)
        day = date.fromisoformat(as_of_date)
        candidate_day = day + timedelta(days=1) if self.mode == "lookahead" else day
        markets = ["KOSPI", "KOSDAQ"] if market_scope == "ALL" else [market_scope]
        return {
            "version": StockScannerService.VERSION,
            "scanner_cache_hit": False,
            "requested_as_of": as_of_date,
            "market_scope": market_scope,
            "data_dates": {market: as_of_date for market in markets},
            "input_fingerprint": {"id": f"fp-{as_of_date}"},
            "market_summary": [{"market": market, "date": as_of_date} for market in markets],
            "partial_data": self.mode in {"partial", "evidence_partial"},
            "preparation_required": (
                [{"market": "KOSPI", "message": "recent history missing"}]
                if self.mode == "partial"
                else []
            ),
            "summary": {
                "candidate_count": 2,
                "three_year_evidence_data_unavailable": 2 if self.mode == "evidence_partial" else 0,
            },
            "methodology": {"guardrail": "point-in-time"},
            "diagnostics": {"network_requests": 1 if self.mode == "network" else 0},
            "candidates": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "market": "KOSPI",
                    "data_date": candidate_day.isoformat(),
                    "candidate_state": "READY",
                    "strategy": "PULLBACK",
                }
            ],
            "more_candidates": [
                {
                    "code": "000660",
                    "name": "SK하이닉스",
                    "market": "KOSPI",
                    "data_date": candidate_day.isoformat(),
                    "candidate_state": "WATCH",
                    "strategy": "BREAKOUT",
                }
            ],
        }


def _draft(catalog: HistoricalValidationCatalog):
    return catalog.create_draft(
        name="VAL.1-B 3일 Replay",
        market_scope="ALL",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-05",
        resolved_end_date="2026-01-07",
        trading_day_count=3,
    )


@pytest.mark.asyncio
async def test_replay_runs_three_days_and_persists_candidates(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)
    scanner = FakeScanner()
    progress = []
    service = HistoricalValidationReplayService(
        catalog,
        FakeMarketStore(),
        scanner_factory=lambda: scanner,
    )

    completed = await service.run(draft.id, progress=progress.append)

    assert completed.status == "COMPLETED"
    assert completed.processed_day_count == 3
    assert completed.candidate_count == 6
    assert scanner.calls == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert len(catalog.list_days(draft.id)) == 3
    assert len(catalog.list_candidates(draft.id)) == 6
    assert progress[-1]["current"] == 3
    assert progress[-1]["total"] == 3


@pytest.mark.asyncio
async def test_replay_resume_skips_completed_days(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)

    hashes = []
    for replay_day in ("2026-01-05", "2026-01-06"):
        saved = catalog.save_completed_day(
            validation_id=draft.id,
            trading_date=replay_day,
            scanner_version=StockScannerService.VERSION,
            market_scope="ALL",
            scanner_cache_hit=False,
            partial_data=False,
            input_fingerprint={"id": f"existing-{replay_day}"},
            market_summary=[],
            summary={},
            methodology={},
            diagnostics={"network_requests": 0},
            candidates=[
                {
                    "market": "KOSPI",
                    "ticker": "005930",
                    "name": "삼성전자",
                    "rank": None,
                    "result_bucket": "TOP",
                    "strategy": "PULLBACK",
                    "decision_status": "READY",
                    "snapshot": {
                        "code": "005930",
                        "name": "삼성전자",
                        "market": "KOSPI",
                        "data_date": replay_day,
                    },
                }
            ],
        )
        hashes.append(saved.result_hash)

    scanner = FakeScanner()
    service = HistoricalValidationReplayService(
        catalog,
        FakeMarketStore(),
        scanner_factory=lambda: scanner,
    )
    completed = await service.run(draft.id)

    assert completed.status == "COMPLETED"
    assert scanner.calls == ["2026-01-07"]
    assert catalog.get_day(draft.id, "2026-01-05").result_hash == hashes[0]
    assert catalog.get_day(draft.id, "2026-01-06").result_hash == hashes[1]


@pytest.mark.asyncio
async def test_replay_rejects_lookahead_and_marks_failed(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)
    scanner = FakeScanner(mode="lookahead")
    service = HistoricalValidationReplayService(
        catalog,
        FakeMarketStore(),
        scanner_factory=lambda: scanner,
    )

    with pytest.raises(HistoricalValidationReplayError) as caught:
        await service.run(draft.id)

    assert caught.value.code == "VAL_REPLAY_LOOKAHEAD_DETECTED"
    current = catalog.get(draft.id)
    assert current is not None
    assert current.status == "FAILED"
    failed_day = catalog.get_day(draft.id, "2026-01-05")
    assert failed_day is not None
    assert failed_day.status == "FAILED"
    assert failed_day.error_code == "VAL_REPLAY_LOOKAHEAD_DETECTED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("network", "VAL_REPLAY_NETWORK_USED"),
        ("partial", "VAL_REPLAY_DATA_INCOMPLETE"),
    ],
)
async def test_replay_rejects_network_or_partial_results(tmp_path: Path, mode: str, expected_code: str):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)
    scanner = FakeScanner(mode=mode)
    service = HistoricalValidationReplayService(
        catalog,
        FakeMarketStore(),
        scanner_factory=lambda: scanner,
    )

    with pytest.raises(HistoricalValidationReplayError) as caught:
        await service.run(draft.id)

    assert caught.value.code == expected_code
    current = catalog.get(draft.id)
    assert current is not None
    assert current.status == "FAILED"
    assert current.processed_day_count == 0

@pytest.mark.asyncio
async def test_replay_accepts_evidence_only_partial_and_preserves_snapshot(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)
    scanner = FakeScanner(mode="evidence_partial")
    service = HistoricalValidationReplayService(
        catalog,
        FakeMarketStore(),
        scanner_factory=lambda: scanner,
    )

    completed = await service.run(draft.id)

    assert completed.status == "COMPLETED"
    assert completed.processed_day_count == 3
    days = catalog.list_days(draft.id)
    assert len(days) == 3
    assert all(day.partial_data is True for day in days)
    assert completed.candidate_count == 6

