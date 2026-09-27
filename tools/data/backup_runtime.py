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
    p1_storage_evidence,
    project_version,
    secret_like_paths,
    simulation_db_path,
    sqlite_snapshot,
    tracking_db_path,
    utc_stamp,
    validate_holdings_db,
    validate_market_db,
    validate_simulation_db,
    validate_tracking_db,
    write_json_atomic,
)


P1_BACKUP_MANIFEST_SCHEMA = "VN_P1_S1_BACKUP_MANIFEST_V1"


def create_backup(
    *,
    destination: Path | None = None,
    include_market: bool = False,
    include_tracking: bool = False,
    include_simulation: bool = False,
    holdings_db: Path | None = None,
    market_db: Path | None = None,
    tracking_db: Path | None = None,
    simulation_db: Path | None = None,
) -> Path:
    source_holdings = Path(holdings_db or holdings_db_path())
    source_market = Path(market_db or market_db_path())
    source_tracking = Path(tracking_db or tracking_db_path())
    source_simulation = Path(simulation_db or simulation_db_path())

    validate_holdings_db(source_holdings)
    if include_market:
        validate_market_db(source_market)
    if include_tracking:
        validate_tracking_db(source_tracking)
    if include_simulation:
        validate_simulation_db(source_simulation)

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
            "tracking_db": False,
            "simulation_db": False,
        }
        validations: dict[str, object] = {
            "holdings": {
                "integrity": holdings_validation["integrity"],
                "foreign_keys": holdings_validation["foreign_keys"],
                "domain": holdings_validation["domain"],
            },
            "market_history": None,
            "tracking": None,
            "simulation": None,
        }

        if include_market:
            market_copy = temp_dir / "market_history.db"
            sqlite_snapshot(source_market, market_copy)
            market_summary = validate_market_db(market_copy)
            files["market_history.db"] = manifest_file_entry(market_copy)
            contents["market_history_db"] = True
            validations["market_history"] = market_summary

        if include_tracking:
            tracking_copy = temp_dir / "recommendation_tracking.db"
            sqlite_snapshot(source_tracking, tracking_copy)
            tracking_summary = validate_tracking_db(tracking_copy)
            files["recommendation_tracking.db"] = manifest_file_entry(tracking_copy)
            contents["tracking_db"] = True
            validations["tracking"] = tracking_summary

        if include_simulation:
            simulation_copy = temp_dir / "simulation.db"
            sqlite_snapshot(source_simulation, simulation_copy)
            simulation_summary = validate_simulation_db(simulation_copy)
            files["simulation.db"] = manifest_file_entry(simulation_copy)
            contents["simulation_db"] = True
            validations["simulation"] = simulation_summary

        p1_contract = {
            "schema_version": P1_BACKUP_MANIFEST_SCHEMA,
            "domains": {
                "holdings": {
                    "included": True,
                    **p1_storage_evidence(holdings_copy, domain="holdings"),
                },
                "market": {
                    "included": bool(include_market),
                    **(
                        p1_storage_evidence(temp_dir / "market_history.db", domain="market")
                        if include_market
                        else p1_storage_evidence(source_market, domain="market")
                    ),
                },
                "tracking": {
                    "included": bool(include_tracking),
                    "frozen_contract": "TRACK.1",
                    "source_available": source_tracking.is_file(),
                },
                "simulation": {
                    "included": bool(include_simulation),
                    **(
                        p1_storage_evidence(temp_dir / "simulation.db", domain="simulation")
                        if include_simulation
                        else p1_storage_evidence(source_simulation, domain="simulation")
                    ),
                },
            },
            "future_stage_state": {
                "watch": "NOT_OWNED_BY_P1",
                "strategy_activation": "NOT_OWNED_BY_P1",
            },
        }

        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": iso_now(),
            "stockscope_version": project_version(),
            "git_commit": git_commit(),
            "contents": contents,
            "p1_storage_contract": p1_contract,
            "counts": holdings_validation["counts"],
            "files": files,
            "validation": validations,
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
        "--include-tracking",
        action="store_true",
        help="Frozen Tracking DB를 읽기 snapshot으로 함께 백업합니다.",
    )
    parser.add_argument(
        "--include-simulation",
        action="store_true",
        help="Simulation/Validation DB와 P1 근거를 함께 백업합니다.",
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
            include_tracking=args.include_tracking,
            include_simulation=args.include_simulation,
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
        print("Tracking DB      " + ("INCLUDED" if args.include_tracking else "SKIPPED"))
        print("Simulation DB    " + ("INCLUDED" if args.include_simulation else "SKIPPED"))
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
