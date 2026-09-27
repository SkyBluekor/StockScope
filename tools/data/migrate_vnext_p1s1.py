from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data.common import (
    DataToolError,
    holdings_db_path,
    market_db_path,
    sqlite_snapshot,
    utc_stamp,
    validate_holdings_db,
    validate_market_db,
)


MIGRATION_ID = "VN_P1_S1_INPUT_IDENTITY_V1"


def _backup_path(path: Path, stamp: str) -> Path:
    return path.with_name(f"{path.name}.pre_{MIGRATION_ID.lower()}_{stamp}.bak")


def _safety_backup(path: Path, stamp: str) -> Path:
    target = _backup_path(path, stamp)
    if target.exists():
        raise DataToolError(f"Migration 안전 백업이 이미 존재합니다: {target}")
    sqlite_snapshot(path, target)
    return target


def _migrate_market(path: Path) -> None:
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=20000")
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            CREATE TABLE IF NOT EXISTS input_change_generation (
                market TEXT PRIMARY KEY
                    CHECK(market IN ('KOSPI','KOSDAQ')),
                generation INTEGER NOT NULL DEFAULT 0
                    CHECK(generation >= 0)
            );
            INSERT OR IGNORE INTO input_change_generation(market,generation)
            VALUES ('KOSPI',0),('KOSDAQ',0);
            COMMIT;
            """
        )
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _migrate_holdings(path: Path) -> None:
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=20000")
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            CREATE TABLE IF NOT EXISTS stock_analysis_input_manifest (
                manifest_hash TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                input_fingerprint TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_input_manifest_no_update
            BEFORE UPDATE ON stock_analysis_input_manifest
            BEGIN
                SELECT RAISE(ABORT, 'stock_analysis_input_manifest is immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_input_manifest_no_delete
            BEFORE DELETE ON stock_analysis_input_manifest
            BEGIN
                SELECT RAISE(ABORT, 'stock_analysis_input_manifest is immutable');
            END;

            CREATE TABLE IF NOT EXISTS stock_analysis_input_proof (
                id TEXT PRIMARY KEY,
                analysis_revision_id TEXT NOT NULL,
                manifest_hash TEXT NOT NULL,
                market_store_generation INTEGER NOT NULL
                    CHECK(market_store_generation >= 0),
                verified_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(
                    analysis_revision_id,
                    manifest_hash,
                    market_store_generation
                ),
                FOREIGN KEY(analysis_revision_id)
                    REFERENCES stock_analysis_revision(id) ON DELETE RESTRICT,
                FOREIGN KEY(manifest_hash)
                    REFERENCES stock_analysis_input_manifest(manifest_hash)
                    ON DELETE RESTRICT
            );

            CREATE INDEX IF NOT EXISTS idx_stock_analysis_input_proof_revision
                ON stock_analysis_input_proof(
                    analysis_revision_id,
                    verified_at DESC
                );

            CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_input_proof_no_update
            BEFORE UPDATE ON stock_analysis_input_proof
            BEGIN
                SELECT RAISE(ABORT, 'stock_analysis_input_proof is append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS trg_stock_analysis_input_proof_no_delete
            BEFORE DELETE ON stock_analysis_input_proof
            BEGIN
                SELECT RAISE(ABORT, 'stock_analysis_input_proof is append-only');
            END;
            COMMIT;
            """
        )
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def migrate_p1_input_identity(
    *,
    holdings_db: Path | None = None,
    market_db: Path | None = None,
    create_backups: bool = True,
) -> dict[str, object]:
    holdings = Path(holdings_db or holdings_db_path())
    market = Path(market_db or market_db_path())

    validate_holdings_db(holdings)
    validate_market_db(market)

    # Unlike restore, this migration does not replace DB files. Each additive DDL
    # transaction acquires its own exclusive writer lock; a live writer therefore
    # fails via SQLite busy/locked rather than by treating harmless WAL sidecars
    # as corruption.
    stamp = utc_stamp()
    backups: dict[str, str | None] = {"holdings": None, "market": None}
    if create_backups:
        backups["holdings"] = str(_safety_backup(holdings, stamp))
        backups["market"] = str(_safety_backup(market, stamp))

    _migrate_market(market)
    _migrate_holdings(holdings)

    validate_market_db(market)
    validate_holdings_db(holdings)
    return {
        "migration_id": MIGRATION_ID,
        "holdings_db": str(holdings),
        "market_history_db": str(market),
        "backups": backups,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VN-P1-S1 input identity evidence schema를 명시적으로 추가합니다."
    )
    parser.add_argument("--holdings-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="테스트/임시 DB에서만 사용하세요. 운영 데이터에는 권장하지 않습니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_p1_input_identity(
            holdings_db=args.holdings_db,
            market_db=args.market_db,
            create_backups=not args.no_backup,
        )
        print("=" * 78)
        print("STOCKSCOPE VN-P1-S1 MIGRATION")
        print("=" * 78)
        print("Input identity schema  PASS")
        print("Holdings integrity     PASS")
        print("Market integrity       PASS")
        for label, path in result["backups"].items():
            if path:
                print(f"Pre-migration {label} backup:", path)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
