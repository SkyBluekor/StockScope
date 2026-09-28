from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.backtest.market_store import HistoricalMarketStore
from app.data_contract.builder import build_stock_data_contract
from app.data_contract.reader import ReadOnlyDataStateReader
from app.backtest.scanner import StockScannerService
from app.holdings import HoldingsCatalog
from app.holdings.analysis import (
    ANALYSIS_ENGINE_VERSION,
    INPUT_FINGERPRINT_CONTRACT_VERSION,
)
from app.backtest.production_exit_policy import production_policy_cache_token
from app.holdings.input_proof import verify_current_analysis_input
from app.input_identity import read_input_generation_token
from app.simulation.input_identity import (
    build_replay_market_manifest,
    verify_validation_input_identity,
)
from app.simulation.validation_catalog import HistoricalValidationCatalog
from tools.data.backup_runtime import create_backup
from tools.data.migrate_input_identity_vnp1s1 import (
    migrate_input_identity,
    migrate_simulation,
)
from tools.data.restore_runtime import restore_backup


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
        scanner_version=StockScannerService.VERSION,
        analysis_engine_version=ANALYSIS_ENGINE_VERSION,
        policy_version=production_policy_cache_token(),
        source_versions={"fingerprint_contract_version": INPUT_FINGERPRINT_CONTRACT_VERSION},
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

        conn.execute(
            "UPDATE stock_daily SET bas_dd='20260924' "
            "WHERE market='KOSPI' AND bas_dd='20260925' AND stock_code='005930'"
        )
        after_date_move = read_input_generation_token(conn, "KOSPI", "005930")
        assert after_date_move is not None
        assert (
            after_date_move["stock_generation"]
            == after_related["stock_generation"] + 1
        )


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
        scanner_version=StockScannerService.VERSION,
        analysis_engine_version=ANALYSIS_ENGINE_VERSION,
        policy_version=production_policy_cache_token(),
        input_fingerprint="different-current-fingerprint",
        source_versions={"fingerprint_contract_version": INPUT_FINGERPRINT_CONTRACT_VERSION, "input_generation": generation},
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


def test_backup_manifest_reports_partial_and_full_identity_restore(tmp_path: Path) -> None:
    market = _market_db(tmp_path / "market.db")
    holdings, _, _ = _holdings_db(tmp_path / "holdings.db")
    migrate_input_identity(holdings_db=holdings, market_db=market)

    partial = create_backup(
        destination=tmp_path / "partial-backup",
        include_market=False,
        holdings_db=holdings,
        market_db=market,
    )
    partial_manifest = json.loads(
        (partial / "backup_manifest.json").read_text(encoding="utf-8")
    )
    partial_identity = partial_manifest["extensions"]["input_identity_v1"]
    assert partial_identity["revision_identity_metadata"] is True
    assert partial_identity["explicit_proof_store"] is True
    assert partial_identity["market_generation_store"] is False
    assert partial_identity["current_identity_verification_capability_restorable"] is False

    full = create_backup(
        destination=tmp_path / "full-backup",
        include_market=True,
        holdings_db=holdings,
        market_db=market,
    )
    full_manifest = json.loads(
        (full / "backup_manifest.json").read_text(encoding="utf-8")
    )
    full_identity = full_manifest["extensions"]["input_identity_v1"]
    assert full_identity["revision_identity_metadata"] is True
    assert full_identity["explicit_proof_store"] is True
    assert full_identity["market_generation_store"] is True
    assert full_identity["current_identity_verification_capability_restorable"] is True

    restored = restore_backup(
        full,
        restore_market=True,
        target_holdings=tmp_path / "restored-holdings.db",
        target_market=tmp_path / "restored-market.db",
    )
    assert (
        restored["input_identity"][
            "current_identity_verification_capability_restored"
        ]
        is True
    )


def test_match_proof_becomes_invalid_only_after_related_input_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    market = _market_db(tmp_path / "market.db")
    holdings, stock_id, _ = _holdings_db(tmp_path / "holdings.db")
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
        scanner_version=StockScannerService.VERSION,
        analysis_engine_version=ANALYSIS_ENGINE_VERSION,
        policy_version=production_policy_cache_token(),
        input_fingerprint="stored-fingerprint",
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
    assert result.verification_result == "MATCH"

    reader = ReadOnlyDataStateReader(market_store_db=market, holdings_db=holdings)
    valid = build_stock_data_contract(reader.read_stock_state("KOSPI", "005930"))
    assert valid.resources.analysis_result.status == "VALID"
    assert valid.resources.analysis_result.current_use_allowed is True

    with sqlite3.connect(market) as conn:
        conn.execute(
            "UPDATE stock_daily SET row_json=? "
            "WHERE market='KOSPI' AND bas_dd='20260925' AND stock_code='000660'",
            (json.dumps({"code": "000660", "close": 111}),),
        )
    still_valid = build_stock_data_contract(
        reader.read_stock_state("KOSPI", "005930")
    )
    assert still_valid.resources.analysis_result.status == "VALID"

    with sqlite3.connect(market) as conn:
        conn.execute(
            "UPDATE stock_daily SET row_json=? "
            "WHERE market='KOSPI' AND bas_dd='20260925' AND stock_code='005930'",
            (json.dumps({"code": "005930", "close": 112}),),
        )
    changed = build_stock_data_contract(
        reader.read_stock_state("KOSPI", "005930")
    )
    assert changed.resources.analysis_result.status == "INVALID"
    assert (
        changed.resources.analysis_result.reason_code
        == "CURRENT_INPUT_CHANGED_SINCE_PROOF"
    )
    assert changed.resources.analysis_result.current_use_allowed is False


def test_validation_manifest_ignores_future_rows_but_detects_used_range_change(
    tmp_path: Path,
) -> None:
    market = _market_db(tmp_path / "market.db")
    simulation = tmp_path / "simulation.db"
    catalog = HistoricalValidationCatalog(simulation)
    catalog.initialize()
    migrate_simulation(simulation)

    draft = catalog.create_draft(
        name="P1 identity test",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-09",
        requested_end_month="2026-09",
        resolved_start_date="2026-09-25",
        resolved_end_date="2026-09-25",
        trading_day_count=1,
    )
    store = HistoricalMarketStore(market)
    replay_day = __import__("datetime").date(2026, 9, 25)
    manifest = build_replay_market_manifest(store, draft, replay_day)

    catalog.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-09-25",
        scanner_version=draft.scanner_version,
        market_scope=draft.market_scope,
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"fixture": "v1"},
        input_manifest=manifest,
        market_summary={},
        summary={},
        methodology={},
        diagnostics={},
        candidates=[],
    )

    initial = verify_validation_input_identity(catalog, store, draft.id)
    assert initial["status"] == "VALID"
    assert initial["counts"]["valid"] == 1

    with sqlite3.connect(market) as conn:
        conn.execute(
            "INSERT INTO stock_daily VALUES(?,?,?,?)",
            (
                "KOSPI",
                "20260928",
                "005930",
                json.dumps({"code": "005930", "close": 120}),
            ),
        )
        conn.execute(
            "INSERT INTO main_index_daily VALUES(?,?,?)",
            ("KOSPI", "20260928", json.dumps({"close": 3100})),
        )
        conn.execute(
            "INSERT INTO day_status VALUES('KOSPI','20260928','stock','data')"
        )
        conn.execute(
            "INSERT INTO day_status VALUES('KOSPI','20260928','index','data')"
        )

    future_added = verify_validation_input_identity(catalog, store, draft.id)
    assert future_added["status"] == "VALID"

    with sqlite3.connect(market) as conn:
        conn.execute(
            "UPDATE stock_daily SET row_json=? "
            "WHERE market='KOSPI' AND bas_dd='20260925' AND stock_code='005930'",
            (json.dumps({"code": "005930", "close": 999}),),
        )

    changed = verify_validation_input_identity(catalog, store, draft.id)
    assert changed["status"] == "INVALID"
    assert changed["counts"]["changed"] == 1
