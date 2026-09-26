from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.holdings.live_management import HoldingsLiveManagementService
from app.holdings.management import HoldingManagementService, management_distance
from app.quotes.models import CachedQuoteObservation


NOW = "2026-09-26T06:00:00+00:00"


def _quote(
    *,
    price: str = "84200",
    age_ms: int = 100,
    freshness_seconds: float = 15.0,
) -> CachedQuoteObservation:
    return CachedQuoteObservation(
        capable=True,
        present=True,
        source="KIS_REST",
        market="KOSPI",
        ticker="005930",
        venue="INTEGRATED",
        provider="KIS",
        mode="SNAPSHOT",
        current_price=Decimal(price),
        provider_timestamp=None,
        received_at=datetime.now(timezone.utc) - timedelta(milliseconds=age_ms),
        age_ms=age_ms,
        freshness_seconds=freshness_seconds,
    )


def _create_fixture(path: Path, *, with_plan: bool = True) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE monitored_stock (
                id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL,
                watch_enabled INTEGER NOT NULL,
                archived_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE position_account (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                account_kind TEXT NOT NULL,
                broker_environment TEXT,
                external_account_fingerprint TEXT,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE holding_position (
                id TEXT PRIMARY KEY,
                monitored_stock_id TEXT NOT NULL,
                position_account_id TEXT NOT NULL,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                current_quantity TEXT NOT NULL,
                current_average_price TEXT,
                current_cost_basis TEXT,
                opened_reason TEXT NOT NULL,
                last_observed_at TEXT,
                last_sync_run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE holding_management_plan (
                id TEXT PRIMARY KEY,
                position_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_analysis_revision_id TEXT NOT NULL,
                reference_price TEXT,
                stop_price TEXT NOT NULL,
                target1_price TEXT,
                target2_price TEXT,
                confirmation_policy TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                change_reason TEXT,
                previous_plan_id TEXT,
                superseded_at TEXT,
                closed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO monitored_stock VALUES(?,?,?,?,?,?,?,?)",
            ("stock-1", "KOSPI", "005930", "삼성전자", 1, None, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO position_account VALUES(?,?,?,?,?,?,?,?,?)",
            ("account-1", "MANUAL", "MANUAL", None, None, "수동", "ACTIVE", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO holding_position VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "position-1", "stock-1", "account-1", "OPEN", NOW, None,
                "10", "69000", "690000", "MANUAL", NOW, None, NOW, NOW,
            ),
        )
        if with_plan:
            conn.execute(
                "INSERT INTO holding_management_plan VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "plan-1", "position-1", 2, "ACTIVE", "ANALYSIS_REVISION", "revision-1",
                    "83000", "77000", "90000", "96000", "EOD_CONFIRMED",
                    NOW, None, None, None, None, NOW, NOW,
                ),
            )


def test_management_distance_helper_preserves_existing_formula() -> None:
    expected = management_distance(Decimal("90000"), Decimal("84200"))
    legacy = HoldingManagementService._distance(Decimal("90000"), Decimal("84200"))

    assert legacy == expected
    assert expected["amount"] == "5800"
    assert Decimal(expected["pct"] or "0") == Decimal("5800") / Decimal("84200") * Decimal("100")


def test_live_proximity_reports_distances_without_creating_live_management_state(tmp_path: Path) -> None:
    db_path = tmp_path / "holdings.db"
    _create_fixture(db_path)

    result = HoldingsLiveManagementService(
        db_path,
        quote_observer=lambda **_kwargs: _quote(price="76000"),
    ).calculate("stock-1")

    assert result.available is True
    assert result.state == "FRESH"
    assert result.reason_code is None
    assert result.quote is not None
    assert result.quote.price == "76000"

    row = result.positions[0]
    assert row.active_plan_id == "plan-1"
    assert row.plan_version == 2
    assert row.distances["stop"]["level"] == "77000"
    assert row.distances["stop"]["amount"] == "1000"
    assert Decimal(row.distances["stop"]["pct"] or "0") == Decimal("1000") / Decimal("76000") * Decimal("100")
    assert row.distances["target1"]["amount"] == "14000"
    assert row.distances["target2"]["amount"] == "20000"

    # The official EOD state remains a separate calculation. Live proximity has no management_state.
    assert HoldingManagementService._state(
        type("Plan", (), {
            "stop_price": Decimal("77000"),
            "target1_price": Decimal("90000"),
            "target2_price": Decimal("96000"),
        })(),
        Decimal("83000"),
    ) == "WITHIN_PLAN"
    assert "management_state" not in result.to_dict()
    assert "STOP_BREACHED" not in str(result.to_dict())


def test_live_proximity_marks_stale_but_keeps_distance_values(tmp_path: Path) -> None:
    db_path = tmp_path / "holdings.db"
    _create_fixture(db_path)

    result = HoldingsLiveManagementService(
        db_path,
        quote_observer=lambda **_kwargs: _quote(age_ms=20_000),
    ).calculate("stock-1")

    assert result.available is True
    assert result.state == "STALE"
    assert result.reason_code == "QUOTE_SNAPSHOT_STALE"
    assert result.positions[0].distances["target1"]["amount"] == "5800"


def test_live_proximity_without_active_plan_is_unavailable_not_error(tmp_path: Path) -> None:
    db_path = tmp_path / "holdings.db"
    _create_fixture(db_path, with_plan=False)

    result = HoldingsLiveManagementService(
        db_path,
        quote_observer=lambda **_kwargs: _quote(),
    ).calculate("stock-1")

    assert result.available is False
    assert result.state == "UNAVAILABLE"
    assert result.reason_code == "ACTIVE_PLAN_ABSENT"
    assert result.quote is None
    assert result.positions[0].active_plan_id is None


def test_live_proximity_without_quote_is_unavailable(tmp_path: Path) -> None:
    db_path = tmp_path / "holdings.db"
    _create_fixture(db_path)
    unavailable = CachedQuoteObservation(
        capable=True,
        present=False,
        source="KIS_REST",
        market="KOSPI",
        ticker="005930",
        venue="INTEGRATED",
        freshness_seconds=15.0,
        reason="QUOTE_NOT_OBSERVED",
    )

    result = HoldingsLiveManagementService(
        db_path,
        quote_observer=lambda **_kwargs: unavailable,
    ).calculate("stock-1")

    assert result.available is False
    assert result.state == "UNAVAILABLE"
    assert result.reason_code == "QUOTE_NOT_OBSERVED"
    assert result.positions == ()


def test_live_proximity_reads_db_without_modification(tmp_path: Path) -> None:
    db_path = tmp_path / "holdings.db"
    _create_fixture(db_path)
    before = db_path.stat()

    result = HoldingsLiveManagementService(
        db_path,
        quote_observer=lambda **_kwargs: _quote(),
    ).calculate("stock-1")

    after = db_path.stat()
    assert result.available is True
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_live_management_source_has_no_network_token_or_write_path() -> None:
    source = Path("backend/app/holdings/live_management.py").read_text(encoding="utf-8")
    readonly = Path("backend/app/holdings/read_only_catalog.py").read_text(encoding="utf-8")

    for forbidden in (
        "inquire_domestic_price",
        "get_access_token",
        "issue_access_token",
        "httpx",
        "requests.",
        "websocket",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        ".initialize(",
    ):
        assert forbidden not in source

    assert "mode=ro" in readonly
    assert "PRAGMA query_only=ON" in readonly
