from __future__ import annotations

import argparse
import os
import sqlite3
import shutil
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.input_identity import (
    INPUT_IDENTITY_SCHEMA_VERSION,
    PROOF_TABLE,
)

from tools.data.common import (
    BACKUP_FORMAT_VERSION,
    DEFAULT_BACKUP_ROOT,
    DataToolError,
    git_commit,
    holdings_counts,
    holdings_db_path,
    iso_now,
    manifest_file_entry,
    market_db_path,
    project_version,
    secret_like_paths,
    sqlite_snapshot,
    utc_stamp,
    validate_holdings_db,
    validate_market_db,
    write_json_atomic,
)


def _table_exists(path: Path, table: str) -> bool:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    return row is not None


def _market_generation_ready(path: Path | None) -> bool:
    if path is None or not path.is_file():
        return False
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not {"input_identity_meta", "input_change_generation"}.issubset(tables):
            return False
        row = conn.execute(
            "SELECT value FROM input_identity_meta WHERE key='schema_version'"
        ).fetchone()
    return row is not None and str(row[0]) == INPUT_IDENTITY_SCHEMA_VERSION


def _input_identity_extension(
    holdings_copy: Path,
    market_copy: Path | None,
) -> dict[str, object]:
    explicit_proof_store = _table_exists(holdings_copy, PROOF_TABLE)
    revision_identity_metadata = _table_exists(holdings_copy, "stock_analysis_revision")
    market_generation = _market_generation_ready(market_copy)
    return {
        "schema_version": INPUT_IDENTITY_SCHEMA_VERSION,
        "revision_identity_metadata": revision_identity_metadata,
        "explicit_proof_store": explicit_proof_store,
        "market_generation_store": market_generation,
        "current_identity_verification_capability_restorable": (
            revision_identity_metadata and market_generation
        ),
        "note": (
            "분석 revision 자체의 fingerprint/source_versions는 Holdings snapshot에 보존됩니다. "
            "현재 입력 동일성을 다시 판정하려면 같은 시점의 Market generation store도 함께 복원해야 합니다. "
            "explicit proof table은 과거 revision을 명시 검증한 이력을 추가로 보존합니다."
        ),
    }


def create_backup(
    *,
    destination: Path | None = None,
    include_market: bool = False,
    holdings_db: Path | None = None,
    market_db: Path | None = None,
) -> Path:
    source_holdings = Path(holdings_db or holdings_db_path())
    source_market = Path(market_db or market_db_path())

    validate_holdings_db(source_holdings)
    if include_market:
        validate_market_db(source_market)

    final_dir = Path(
        destination
        or (DEFAULT_BACKUP_ROOT / f"StockScope_{utc_stamp()}")
    )
    if final_dir.exists():
        raise DataToolError(f"백업 대상이 이미 존재합니다: {final_dir}")

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = final_dir.parent / f".{final_dir.name}.{uuid4().hex}.tmp"
    temp_dir.mkdir(parents=True, exist_ok=False)

    try:
        holdings_copy = temp_dir / "holdings.db"
        sqlite_snapshot(source_holdings, holdings_copy)
        holdings_validation = validate_holdings_db(holdings_copy)

        files: dict[str, dict[str, object]] = {
            "holdings.db": manifest_file_entry(holdings_copy),
        }
        contents = {
            "holdings_db": True,
            "market_history_db": False,
        }

        market_summary = None
        market_copy: Path | None = None
        if include_market:
            market_copy = temp_dir / "market_history.db"
            sqlite_snapshot(source_market, market_copy)
            market_summary = validate_market_db(market_copy)
            files["market_history.db"] = manifest_file_entry(market_copy)
            contents["market_history_db"] = True

        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": iso_now(),
            "stockscope_version": project_version(),
            "git_commit": git_commit(),
            "contents": contents,
            "counts": holdings_validation["counts"],
            "files": files,
            "validation": {
                "holdings": {
                    "integrity": holdings_validation["integrity"],
                    "foreign_keys": holdings_validation["foreign_keys"],
                    "domain": holdings_validation["domain"],
                },
                "market_history": market_summary,
            },
            "extensions": {
                "input_identity_v1": _input_identity_extension(
                    holdings_copy,
                    market_copy,
                ),
            },
            "secret_files_included": [],
        }
        write_json_atomic(temp_dir / "backup_manifest.json", manifest)

        blocked = secret_like_paths(temp_dir)
        if blocked:
            raise DataToolError(
                "백업에 민감 파일이 포함되어 중단했습니다: " + ", ".join(blocked)
            )

        os.replace(temp_dir, final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope 사용자 상태를 일관된 SQLite snapshot으로 백업합니다."
    )
    parser.add_argument(
        "--include-market",
        action="store_true",
        help="재수집 가능한 market_history.db도 함께 백업합니다.",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        help="생성할 백업 디렉터리. 생략하면 backups/ 아래에 시간별 폴더를 만듭니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        path = create_backup(
            destination=args.destination,
            include_market=args.include_market,
        )
        manifest_path = path / "backup_manifest.json"
        print("=" * 78)
        print("STOCKSCOPE BACKUP")
        print("=" * 78)
        print("Holdings DB      PASS")
        print("Integrity        PASS")
        print("Foreign Keys     PASS")
        print("Domain Check     PASS")
        print("Market Store     " + ("INCLUDED" if args.include_market else "SKIPPED"))
        print("Secrets          EXCLUDED")
        print("Manifest         PASS")
        print("")
        print("Backup:", path)
        print("Manifest:", manifest_path)
        return 0
    except DataToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
