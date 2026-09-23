from __future__ import annotations

from pathlib import Path

from app.simulation.validation_catalog import HistoricalValidationCatalog
from app.simulation.validation_outcome import HistoricalValidationOutcomeService


def _make_catalog(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = catalog.create_draft(
        name="VAL.3-A3 fixture",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-02",
        resolved_end_date="2026-01-02",
        trading_day_count=1,
    )
    catalog.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version=draft.scanner_version,
        market_scope="KOSPI",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"fixture": "a3"},
        market_summary={},
        summary={},
        methodology={},
        diagnostics={"network_requests": 0},
        candidates=[
            {
                "market": "KOSPI",
                "ticker": "000001",
                "name": "Momentum A",
                "rank": 1,
                "result_bucket": "TOP",
                "strategy": "momentum_continuation",
                "decision_status": "READY",
                "snapshot": {},
            },
            {
                "market": "KOSPI",
                "ticker": "000002",
                "name": "Momentum B",
                "rank": 2,
                "result_bucket": "TOP",
                "strategy": "momentum_continuation",
                "decision_status": "READY",
                "snapshot": {},
            },
            {
                "market": "KOSPI",
                "ticker": "000003",
                "name": "Pullback C",
                "rank": 3,
                "result_bucket": "TOP",
                "strategy": "pullback",
                "decision_status": "WATCH",
                "snapshot": {},
            },
            {
                "market": "KOSPI",
                "ticker": "000004",
                "name": "Unknown D",
                "rank": 4,
                "result_bucket": "TOP",
                "strategy": "",
                "decision_status": "",
                "snapshot": {},
            },
        ],
    )
    with catalog.connect() as conn:
        conn.execute(
            """
            UPDATE historical_validation_run
            SET status='COMPLETED',processed_day_count=trading_day_count
            WHERE id=?
            """,
            (draft.id,),
        )
    return catalog, draft.id


def _insert_outcome(
    catalog: HistoricalValidationCatalog,
    validation_id: str,
    ticker: str,
    *,
    days: int,
    r5: float | None,
    r10: float | None,
    r20: float | None,
    mfe: float | None,
    mae: float | None,
    stop: int,
    target1: int,
    target2: int,
):
    payload = {
        "validation_id": validation_id,
        "ticker": ticker,
        "days": days,
        "r5": r5,
        "r10": r10,
        "r20": r20,
        "mfe": mfe,
        "mae": mae,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "stop_date": "2026-01-06" if stop else None,
        "target1_date": "2026-01-07" if target1 else None,
        "target2_date": "2026-01-08" if target2 else None,
    }
    with catalog.connect() as conn:
        conn.execute(
            """
            INSERT INTO historical_validation_candidate_outcome(
                validation_id,trading_date,market,ticker,
                reference_price,entry_rule_json,stop_price,target1_price,target2_price,
                available_trading_days,evaluated_through,
                return_5d,return_10d,return_20d,mfe_pct,mae_pct,
                entry_comparable,entry_touched,entry_touch_date,
                stop_comparable,stop_touched,stop_touch_date,
                target1_comparable,target1_touched,target1_touch_date,
                target2_comparable,target2_touched,target2_touch_date,
                computed_at
            ) VALUES(
                :validation_id,'2026-01-02','KOSPI',:ticker,
                '100','{}','90','110','120',
                :days,'2026-02-02',
                :r5,:r10,:r20,:mfe,:mae,
                1,1,'2026-01-05',
                1,:stop,:stop_date,
                1,:target1,:target1_date,
                1,:target2,:target2_date,
                '2026-03-01T00:00:00+00:00'
            )
            """,
            payload,
        )


def test_breakdown_groups_strategy_and_decision_without_ranking(tmp_path: Path):
    catalog, validation_id = _make_catalog(tmp_path)
    _insert_outcome(catalog, validation_id, "000001", days=20, r5=1, r10=2, r20=3, mfe=10, mae=-5, stop=0, target1=1, target2=0)
    _insert_outcome(catalog, validation_id, "000002", days=20, r5=2, r10=4, r20=5, mfe=14, mae=-7, stop=1, target1=1, target2=1)
    _insert_outcome(catalog, validation_id, "000003", days=10, r5=-1, r10=0.5, r20=None, mfe=8, mae=-9, stop=1, target1=0, target2=0)
    _insert_outcome(catalog, validation_id, "000004", days=20, r5=-2, r10=-2, r20=-2, mfe=3, mae=-6, stop=1, target1=0, target2=0)

    service = HistoricalValidationOutcomeService(catalog, tmp_path / "does-not-exist.db")
    result = service.breakdown(validation_id)

    assert result["status"] == "READY"

    momentum = next(row for row in result["strategy"] if row["key"] == "momentum_continuation")
    assert momentum["candidate_count"] == 2
    assert momentum["horizons"]["20d"] == {
        "sample_count": 2,
        "average_pct": 4.0,
        "median_pct": 4.0,
    }
    assert momentum["mfe_20d"]["average_pct"] == 12.0
    assert momentum["mae_20d"]["average_pct"] == -6.0
    assert momentum["touches"]["target1"]["touched_count"] == 2
    assert momentum["touches"]["target1"]["comparable_count"] == 2

    pullback = next(row for row in result["strategy"] if row["key"] == "pullback")
    assert pullback["candidate_count"] == 1
    assert pullback["horizons"]["5d"]["sample_count"] == 1
    assert pullback["horizons"]["20d"]["sample_count"] == 0
    assert pullback["mfe_20d"]["sample_count"] == 0
    assert pullback["touches"]["stop"]["comparable_count"] == 0

    ready = next(row for row in result["decision_status"] if row["key"] == "READY")
    assert ready["candidate_count"] == 2
    assert ready["horizons"]["20d"]["average_pct"] == 4.0


def test_unknown_groups_are_kept_instead_of_dropped(tmp_path: Path):
    catalog, validation_id = _make_catalog(tmp_path)
    _insert_outcome(catalog, validation_id, "000004", days=20, r5=-2, r10=-2, r20=-2, mfe=3, mae=-6, stop=1, target1=0, target2=0)

    result = HistoricalValidationOutcomeService(
        catalog,
        tmp_path / "unused-market.db",
    ).breakdown(validation_id)

    unknown_strategy = next(row for row in result["strategy"] if row["key"] == "UNKNOWN")
    unknown_decision = next(row for row in result["decision_status"] if row["key"] == "UNKNOWN")
    assert unknown_strategy["candidate_count"] == 1
    assert unknown_decision["candidate_count"] == 1


def test_breakdown_reads_simulation_db_only() -> None:
    source = Path("backend/app/simulation/validation_outcome.py").read_text(encoding="utf-8")
    start = source.index("    def breakdown(")
    breakdown_source = source[start:]
    assert "_market_conn(" not in breakdown_source
    assert "StockScannerService" not in breakdown_source
    assert "KrxProvider" not in breakdown_source
    assert "requests." not in breakdown_source
    assert "httpx." not in breakdown_source
