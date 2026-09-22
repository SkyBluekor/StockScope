from __future__ import annotations

import sqlite3
from pathlib import Path

from app.simulation.validation_catalog import HistoricalValidationCatalog


def _draft(catalog: HistoricalValidationCatalog):
    return catalog.create_draft(
        name="VAL.1-A",
        market_scope="ALL",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-03",
        resolved_start_date="2026-01-02",
        resolved_end_date="2026-03-31",
        trading_day_count=61,
    )


def test_initialize_migrates_existing_draft_without_data_loss(tmp_path: Path):
    db = tmp_path / "simulation.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE historical_validation_run (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                validation_target TEXT NOT NULL,
                market_scope TEXT NOT NULL,
                scanner_version TEXT NOT NULL,
                scanner_baseline TEXT,
                requested_period_type TEXT NOT NULL,
                requested_start_month TEXT NOT NULL,
                requested_end_month TEXT NOT NULL,
                resolved_start_date TEXT NOT NULL,
                resolved_end_date TEXT NOT NULL,
                trading_day_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """INSERT INTO historical_validation_run VALUES(
                'legacy','기존 Draft','PRODUCTION_SCANNER','ALL','0.21.3.7',NULL,
                '1y','2025-10','2026-09','2025-10-01','2026-09-18',248,
                'DRAFT','2026-09-21T00:00:00+00:00','2026-09-21T00:00:00+00:00'
            )"""
        )

    catalog = HistoricalValidationCatalog(db)
    catalog.initialize()
    draft = catalog.get("legacy")
    assert draft is not None
    assert draft.name == "기존 Draft"
    assert draft.processed_day_count == 0
    assert draft.candidate_count == 0
    assert draft.cancel_requested is False


def test_completed_day_saves_candidates_progress_and_is_immutable(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)

    first = catalog.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version="0.21.3.7",
        market_scope="ALL",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"id": "fp-1"},
        market_summary={"ok": True},
        summary={"candidate_count": 2},
        methodology={"mode": "point-in-time"},
        diagnostics={"network_requests": 0},
        candidates=[
            {
                "market": "KOSPI", "ticker": "005930", "name": "삼성전자",
                "rank": 1, "result_bucket": "TOP", "strategy": "PULLBACK",
                "decision_status": "READY", "snapshot": {"code": "005930", "data_date": "2026-01-02"},
            },
            {
                "market": "KOSDAQ", "ticker": "068270", "name": "셀트리온",
                "rank": None, "result_bucket": "MORE", "strategy": "BREAKOUT",
                "decision_status": "WATCH", "snapshot": {"code": "068270", "data_date": "2026-01-02"},
            },
        ],
    )
    assert first.status == "COMPLETED"
    assert first.candidate_count == 2
    assert first.result_hash

    refreshed = catalog.get(draft.id)
    assert refreshed is not None
    assert refreshed.processed_day_count == 1
    assert refreshed.candidate_count == 2
    assert refreshed.last_completed_date == "2026-01-02"

    original_hash = first.result_hash
    second = catalog.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version="0.21.3.7",
        market_scope="ALL",
        scanner_cache_hit=True,
        partial_data=False,
        input_fingerprint={"id": "must-not-overwrite"},
        market_summary={}, summary={}, methodology={}, diagnostics={"network_requests": 999},
        candidates=[
            {"market": "KOSPI", "ticker": "000660", "name": "SK하이닉스", "result_bucket": "TOP", "snapshot": {"code": "000660"}}
        ],
    )
    assert second.result_hash == original_hash
    assert [row.ticker for row in catalog.list_candidates(draft.id, "2026-01-02")] == ["005930", "068270"]


def test_failed_day_does_not_advance_progress_and_delete_cascades(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = _draft(catalog)

    failed = catalog.record_failed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version="0.21.3.7",
        market_scope="ALL",
        error_code="VAL_REPLAY_SCANNER_FAILED",
        error_message="boom",
    )
    assert failed.status == "FAILED"
    current = catalog.get(draft.id)
    assert current is not None
    assert current.processed_day_count == 0
    assert current.candidate_count == 0

    catalog.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version="0.21.3.7",
        market_scope="ALL",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"id": "fp"},
        market_summary={}, summary={}, methodology={}, diagnostics={"network_requests": 0},
        candidates=[
            {"market": "KOSPI", "ticker": "005930", "name": "삼성전자", "result_bucket": "TOP", "snapshot": {"code": "005930"}}
        ],
    )
    assert catalog.delete(draft.id) is True
    with catalog.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM historical_validation_day WHERE validation_id=?", (draft.id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM historical_validation_candidate WHERE validation_id=?", (draft.id,)).fetchone()[0] == 0
