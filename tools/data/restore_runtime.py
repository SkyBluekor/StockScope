from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data.common import (
    BACKUP_FORMAT_VERSION,
    DataToolError,
    assert_replaceable,
    holdings_db_path,
    market_db_path,
    secret_like_paths,
    sqlite_snapshot,
    utc_stamp,
    validate_holdings_db,
    validate_manifest_hash,
    validate_market_db,
)


def _load_manifest(backup_dir: Path) -> dict:
    manifest_path = backup_dir / "backup_manifest.json"
    if not manifest_path.is_file():
        raise DataToolError("backup_manifest.json이 없습니다.")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataToolError("backup_manifest.json을 읽을 수 없습니다.") from exc
    if int(payload.get("format_version") or 0) != BACKUP_FORMAT_VERSION:
        raise DataToolError(
            f"지원하지 않는 backup format입니다: {payload.get('format_version')}"
        )
    return payload


def _prepare_restore_copy(
    source: Path,
    target: Path,
    *,
    validator,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.restore.{uuid4().hex}.tmp")
    sqlite_snapshot(source, temp)
    validator(temp)
    return temp


def restore_backup(
    backup_dir: Path,
    *,
    restore_market: bool = False,
    target_holdings: Path | None = None,
    target_market: Path | None = None,
) -> dict[str, object]:
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        raise DataToolError(f"백업 디렉터리를 찾을 수 없습니다: {backup_dir}")

    blocked = secret_like_paths(backup_dir)
    if blocked:
        raise DataToolError(
            "백업 폴더에 민감 파일이 포함되어 복원을 차단했습니다: "
            + ", ".join(blocked)
        )

    manifest = _load_manifest(backup_dir)
    contents = dict(manifest.get("contents") or {})
    files = dict(manifest.get("files") or {})

    if not contents.get("holdings_db"):
        raise DataToolError("백업에 holdings.db가 없습니다.")

    source_holdings = backup_dir / "holdings.db"
    if not source_holdings.is_file():
        raise DataToolError("백업 holdings.db 파일이 없습니다.")
    validate_manifest_hash(
        source_holdings,
        dict(files.get("holdings.db") or {}),
        "holdings.db",
    )
    validate_holdings_db(source_holdings)

    source_market: Path | None = None
    if restore_market:
        if not contents.get("market_history_db"):
            raise DataToolError(
                "이 백업에는 Market Store가 없습니다. --restore-market을 제거하세요."
            )
        source_market = backup_dir / "market_history.db"
        if not source_market.is_file():
            raise DataToolError("백업 market_history.db 파일이 없습니다.")
        validate_manifest_hash(
            source_market,
            dict(files.get("market_history.db") or {}),
            "market_history.db",
        )
        validate_market_db(source_market)

    holdings_target = Path(target_holdings or holdings_db_path())
    market_target = Path(target_market or market_db_path())

    targets: list[tuple[str, Path, Path, object]] = [
        ("holdings", source_holdings, holdings_target, validate_holdings_db)
    ]
    if restore_market and source_market is not None:
        targets.append(
            ("market", source_market, market_target, validate_market_db)
        )

    for _, _, target, _ in targets:
        assert_replaceable(target)

    stamp = utc_stamp()
    pre_restore: dict[str, Path | None] = {}
    existed_before: dict[str, bool] = {}
    temps: dict[str, Path] = {}

    try:
        for label, _, target, validator in targets:
            existed = target.exists()
            existed_before[label] = existed
            if existed:
                backup_path = target.with_name(
                    f"{target.name}.pre_restore_{stamp}.bak"
                )
                if backup_path.exists():
                    raise DataToolError(
                        f"복원 전 안전 백업 경로가 이미 존재합니다: {backup_path}"
                    )
                sqlite_snapshot(target, backup_path)
                validator(backup_path)
                pre_restore[label] = backup_path
            else:
                pre_restore[label] = None

        for label, source, target, validator in targets:
            temps[label] = _prepare_restore_copy(
                source,
                target,
                validator=validator,
            )

        replaced: list[str] = []
        try:
            for label, _, target, validator in targets:
                os.replace(temps[label], target)
                replaced.append(label)
                validator(target)
        except Exception:
            for label, _, target, validator in reversed(targets):
                if label not in replaced:
                    continue
                safe = pre_restore.get(label)
                if safe is not None and safe.exists():
                    rollback_temp = _prepare_restore_copy(
                        safe,
                        target,
                        validator=validator,
                    )
                    os.replace(rollback_temp, target)
                    validator(target)
            raise

        return {
            "holdings_db": str(holdings_target),
            "market_history_db": (
                str(market_target) if restore_market else None
            ),
            "pre_restore_backups": {
                key: (str(value) if value else None)
                for key, value in pre_restore.items()
            },
        }
    finally:
        for temp in temps.values():
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope 백업을 검증한 뒤 안전하게 복원합니다."
    )
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument(
        "--restore-market",
        action="store_true",
        help="백업에 포함된 market_history.db도 복원합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = restore_backup(
            args.backup_dir,
            restore_market=args.restore_market,
        )
        print("=" * 78)
        print("STOCKSCOPE RESTORE")
        print("=" * 78)
        print("Manifest          PASS")
        print("Backup Hash       PASS")
        print("Integrity         PASS")
        print("Foreign Keys      PASS")
        print("Domain Check      PASS")
        print("Holdings Restore  PASS")
        print("Market Restore    " + ("PASS" if args.restore_market else "SKIPPED"))
        print("")
        for label, path in result["pre_restore_backups"].items():
            if path:
                print(f"Pre-restore {label} backup:", path)
        return 0
    except DataToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
