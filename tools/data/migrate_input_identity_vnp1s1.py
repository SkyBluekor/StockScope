from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.input_identity import (
    ANALYSIS_PROOF_VERSION,
    INPUT_IDENTITY_SCHEMA_VERSION,
    PROOF_TABLE,
    VALIDATION_PROOF_TABLE,
    VALIDATION_PROOF_VERSION,
)
from tools.data.common import (
    DataToolError,
    holdings_db_path,
    market_db_path,
    sqlite_readonly,
)


def _existing_core_tables(path: Path, required: set[str]) -> None:
    if not path.is_file():
        raise DataToolError(f"SQLite DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = sorted(required - names)
    if missing:
        raise DataToolError(
            f"{path.name}에 필요한 기존 table이 없습니다: {', '.join(missing)}"
        )


def migrate_market_store(path: Path) -> dict[str, int | str]:
    path = Path(path)
    _existing_core_tables(
        path,
        {"stock_daily", "main_index_daily", "day_status"},
    )
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS input_identity_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS input_change_generation (
                scope TEXT NOT NULL CHECK(scope IN ('STOCK','STOCK_STATUS','INDEX')),
                market TEXT NOT NULL,
                subject TEXT NOT NULL,
                generation INTEGER NOT NULL CHECK(generation >= 1),
                PRIMARY KEY(scope,market,subject)
            )
            """
        )
        marker = conn.execute(
            "SELECT value FROM input_identity_meta WHERE key='schema_version'"
        ).fetchone()
        if marker is None:
            conn.execute(
                """
                INSERT INTO input_change_generation(scope,market,subject,generation)
                SELECT 'STOCK',market,stock_code,1
                FROM stock_daily
                GROUP BY market,stock_code
                """
            )
            conn.execute(
                """
                INSERT INTO input_change_generation(scope,market,subject,generation)
                SELECT 'STOCK_STATUS',market,'*',1
                FROM day_status
                WHERE kind='stock'
                GROUP BY market
                """
            )
            conn.execute(
                """
                INSERT INTO input_change_generation(scope,market,subject,generation)
                SELECT 'INDEX',market,'*',1
                FROM (
                    SELECT market FROM main_index_daily
                    UNION
                    SELECT market FROM day_status WHERE kind='index'
                )
                GROUP BY market
                """
            )
            conn.execute(
                "INSERT INTO input_identity_meta(key,value) VALUES('schema_version',?)",
                (INPUT_IDENTITY_SCHEMA_VERSION,),
            )
        elif str(marker[0]) != INPUT_IDENTITY_SCHEMA_VERSION:
            raise DataToolError(
                f"지원하지 않는 input identity schema입니다: {marker[0]}"
            )

        trigger_sql = (
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_stock_insert
            AFTER INSERT ON stock_daily
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('STOCK',NEW.market,NEW.stock_code,1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_stock_delete
            AFTER DELETE ON stock_daily
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('STOCK',OLD.market,OLD.stock_code,1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_stock_update_old_key
            AFTER UPDATE ON stock_daily
            WHEN OLD.market<>NEW.market OR OLD.stock_code<>NEW.stock_code
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('STOCK',OLD.market,OLD.stock_code,1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_stock_update_new
            AFTER UPDATE ON stock_daily
            WHEN OLD.market<>NEW.market OR OLD.stock_code<>NEW.stock_code OR OLD.row_json<>NEW.row_json
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('STOCK',NEW.market,NEW.stock_code,1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_index_insert
            AFTER INSERT ON main_index_daily
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('INDEX',NEW.market,'*',1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_index_delete
            AFTER DELETE ON main_index_daily
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('INDEX',OLD.market,'*',1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_index_update_old_market
            AFTER UPDATE ON main_index_daily
            WHEN OLD.market<>NEW.market
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('INDEX',OLD.market,'*',1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_index_update_new
            AFTER UPDATE ON main_index_daily
            WHEN OLD.market<>NEW.market OR OLD.bas_dd<>NEW.bas_dd OR OLD.row_json<>NEW.row_json
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES('INDEX',NEW.market,'*',1)
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_status_insert
            AFTER INSERT ON day_status
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES(
                CASE WHEN NEW.kind='stock' THEN 'STOCK_STATUS' ELSE 'INDEX' END,
                NEW.market,'*',1
              )
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_status_delete
            AFTER DELETE ON day_status
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES(
                CASE WHEN OLD.kind='stock' THEN 'STOCK_STATUS' ELSE 'INDEX' END,
                OLD.market,'*',1
              )
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_status_update_old_scope
            AFTER UPDATE ON day_status
            WHEN OLD.market<>NEW.market OR OLD.kind<>NEW.kind
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES(
                CASE WHEN OLD.kind='stock' THEN 'STOCK_STATUS' ELSE 'INDEX' END,
                OLD.market,'*',1
              )
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_input_gen_status_update_new
            AFTER UPDATE ON day_status
            WHEN OLD.market<>NEW.market OR OLD.bas_dd<>NEW.bas_dd OR OLD.kind<>NEW.kind OR OLD.status<>NEW.status
            BEGIN
              INSERT INTO input_change_generation(scope,market,subject,generation)
              VALUES(
                CASE WHEN NEW.kind='stock' THEN 'STOCK_STATUS' ELSE 'INDEX' END,
                NEW.market,'*',1
              )
              ON CONFLICT(scope,market,subject)
              DO UPDATE SET generation=generation+1;
            END
            """,
        )
        for statement in trigger_sql:
            conn.execute(statement)
        conn.commit()
        count = int(
            conn.execute("SELECT COUNT(*) FROM input_change_generation").fetchone()[0]
        )
        return {
            "schema_version": INPUT_IDENTITY_SCHEMA_VERSION,
            "generation_rows": count,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_holdings(path: Path) -> dict[str, str]:
    path = Path(path)
    _existing_core_tables(
        path,
        {"stock_analysis_day", "stock_analysis_revision", "monitored_stock"},
    )
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {PROOF_TABLE} (
                revision_id TEXT PRIMARY KEY,
                proof_version TEXT NOT NULL,
                input_fingerprint TEXT NOT NULL,
                generation_json TEXT NOT NULL,
                verification_result TEXT NOT NULL
                    CHECK(verification_result IN ('MATCH','MISMATCH')),
                current_fingerprint TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                FOREIGN KEY(revision_id)
                    REFERENCES stock_analysis_revision(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
        return {"proof_version": ANALYSIS_PROOF_VERSION}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_simulation(path: Path) -> dict[str, str]:
    path = Path(path)
    _existing_core_tables(
        path,
        {"historical_validation_run", "historical_validation_day"},
    )
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {VALIDATION_PROOF_TABLE} (
                validation_id TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                proof_version TEXT NOT NULL,
                market_manifest_json TEXT NOT NULL,
                source_input_fingerprint_json TEXT,
                day_result_hash TEXT,
                captured_at TEXT NOT NULL,
                PRIMARY KEY(validation_id,trading_date),
                FOREIGN KEY(validation_id,trading_date)
                    REFERENCES historical_validation_day(validation_id,trading_date)
                    ON DELETE CASCADE
            )
            """
        )
        conn.commit()
        return {"proof_version": VALIDATION_PROOF_VERSION}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_input_identity(
    *,
    holdings_db: Path | None = None,
    market_db: Path | None = None,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    market_result = migrate_market_store(Path(market_db or market_db_path()))
    holdings_result = migrate_holdings(Path(holdings_db or holdings_db_path()))

    default_simulation = BACKEND / "runtime" / "simulation" / "simulation.db"
    simulation_path = Path(
        simulation_db
        or os.getenv("STOCKSCOPE_SIM_DB")
        or default_simulation
    )
    simulation_result: dict[str, str]
    if simulation_path.is_file():
        simulation_result = migrate_simulation(simulation_path)
    else:
        simulation_result = {"status": "SKIPPED_MISSING"}
    return {
        "market": market_result,
        "holdings": holdings_result,
        "simulation": simulation_result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VN-P1-S1 입력 identity generation/proof 저장 구조를 명시적으로 추가합니다."
    )
    parser.add_argument("--holdings-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_input_identity(
            holdings_db=args.holdings_db,
            market_db=args.market_db,
            simulation_db=args.simulation_db,
        )
        print("VN-P1-S1 INPUT IDENTITY MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
