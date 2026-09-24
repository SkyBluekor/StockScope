from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
