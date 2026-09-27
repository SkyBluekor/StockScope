from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.data_contract.builder import build_stock_data_contract
from app.data_contract.reader import ReadOnlyDataStateReader
from app.holdings import HoldingsCatalog
from app.holdings.input_proof import verify_current_analysis_input
from app.input_identity import read_input_generation_token
from tools.data.migrate_input_identity_vnp1s1 import migrate_input_identity


def _market_db(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily(
                market TEXT NOT NULL, bas_dd TEXT NOT NULL, stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL, PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily(
                market TEXT NOT NULL, bas_dd TEXT NOT NULL, row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd)
            );
            CREATE TABLE day_status(
                market TEXT NOT NULL, bas_dd TEXT NOT NULL, kind TEXT NOT NULL,
                status TEXT NOT NULL, PRIMARY KEY(market,bas_dd,kind)
            );
            """
        )
        for code in ("005930", "000660"):
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSPI", "20260925", code, json.dumps({"code": code, "close": 100})),
            )
        conn.execute(
            "INSERT INTO main_index_daily VALUES(?,?,?)",
            ("KOSPI", "20260925", json.dumps({"close": 3000})),
        )
        conn.execute("INSERT INTO day_status VALUES('KOSPI','20260925','stock','data')")
        conn.execute("INSERT INTO day_status VALUES('KOSPI','20260925','index','data')")
    return path


def _holdings_db(path: Path) -> tuple[Path, str, str]:
    catalog = HoldingsCatalog(path)
    catalog.initialize()
    stock = catalog.create_monitored_stock(
        market="KOSPI", ticker="005930", name="삼성전자"
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock.id, market_date="2026-09-25"
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="stored-fingerprint",
        strategy_key="test",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="110",
        target2_price="120",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="PROD_EXIT_V1",
        source_versions={},
        snapshot={},
        computed_at="2026-09-25T00:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id, revision_id=revision.id
    )
    return path, stock.id, revision.id


def test_migration_is_explicit_repeatable_and_generation_is_scoped(tmp_path: Path) -> None:
    market = _market_db(tmp_path / "market.db")
    holdings, _, _ = _holdings_db(tmp_path / "holdings.db")

    with sqlite3.connect(market) as conn:
        assert read_input_generation_token(conn, "KOSPI", "005930") is None

    first = migrate_input_identity(holdings_db=holdings, market_db=market)
    second = migrate_input_identity(holdings_db=holdings, market_db=market)
    assert first["market"]["schema_version"] == second["market"]["schema_version"]

    with sqlite3.connect(market) as conn:
        before = read_input_generation_token(conn, "KOSPI", "005930")
        other_before = read_input_generation_token(conn, "KOSPI", "000660")
        assert before is not None and other_before is not None

        conn.execute(
            "UPDATE stock_daily SET row_json=? "
            "WHERE market='KOSPI' AND bas_dd='20260925' AND stock_code='000660'",
            (json.dumps({"code": "000660", "close": 101}),),
        )
        after_unrelated = read_input_generation_token(conn, "KOSPI", "005930")
        other_after = read_input_generation_token(conn, "KOSPI", "000660")
        assert after_unrelated == before
        assert other_after is not None
        assert other_after["stock_generation"] == other_before["stock_generation"] + 1

        conn.execute(
            "UPDATE stock_daily SET row_json=? "
            "WHERE market='KOSPI' AND bas_dd='20260925' AND stock_code='005930'",
            (json.dumps({"code": "005930", "close": 102}),),
        )
        after_related = read_input_generation_token(conn, "KOSPI", "005930")
        assert after_related is not None
        assert after_related["stock_generation"] == before["stock_generation"] + 1


def test_data_contract_stays_unverified_without_migration(tmp_path: Path) -> None:
    market = _market_db(tmp_path / "market.db")
    holdings, _, _ = _holdings_db(tmp_path / "holdings.db")
    reader = ReadOnlyDataStateReader(market_store_db=market, holdings_db=holdings)
    state = reader.read_stock_state("KOSPI", "005930")
    contract = build_stock_data_contract(state)
    assert contract.resources.analysis_result.status == "UNVERIFIED"
    assert contract.resources.analysis_result.reason_code == "CURRENT_INPUT_IDENTITY_NOT_PROVEN"


def test_explicit_mismatch_proof_does_not_modify_revision(tmp_path: Path, monkeypatch) -> None:
    market = _market_db(tmp_path / "market.db")
    holdings, stock_id, revision_id = _holdings_db(tmp_path / "holdings.db")
    migrate_input_identity(holdings_db=holdings, market_db=market)

    from app.holdings import input_proof as proof_module
    from app.holdings.analysis import SingleStockAnalysis

    with sqlite3.connect(market) as conn:
        generation = read_input_generation_token(conn, "KOSPI", "005930")
    assert generation is not None

    fake = SingleStockAnalysis(
        market="KOSPI",
        ticker="005930",
        market_date="2026-09-25",
        strategy_key="test",
        action_state="WATCH",
        risk_state="READY",
        reference_price=100.0,
        stop_price=90.0,
        target1_price=110.0,
        target2_price=120.0,
        condition_state={},
        readiness_state={},
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="PROD_EXIT_V1",
        input_fingerprint="different-current-fingerprint",
        source_versions={"input_generation": generation},
        snapshot={},
    )
    monkeypatch.setattr(proof_module, "analyze_single_stock", lambda **_: fake)

    result = verify_current_analysis_input(
        HoldingsCatalog(holdings),
        stock_id,
        market_store_db=market,
        clock=lambda: "2026-09-27T00:00:00+00:00",
    )
    assert result.verification_result == "MISMATCH"

    with sqlite3.connect(holdings) as conn:
        original = conn.execute(
            "SELECT input_fingerprint FROM stock_analysis_revision WHERE id=?",
            (revision_id,),
        ).fetchone()[0]
        proof = conn.execute(
            "SELECT verification_result FROM analysis_input_proof WHERE revision_id=?",
            (revision_id,),
        ).fetchone()[0]
    assert original == "stored-fingerprint"
    assert proof == "MISMATCH"

    reader = ReadOnlyDataStateReader(market_store_db=market, holdings_db=holdings)
    contract = build_stock_data_contract(reader.read_stock_state("KOSPI", "005930"))
    assert contract.resources.analysis_result.status == "INVALID"
    assert contract.resources.analysis_result.reason_code == "CURRENT_INPUT_IDENTITY_MISMATCH"
    assert any(action.id == "VERIFY_ANALYSIS_INPUT" for action in contract.actions)
