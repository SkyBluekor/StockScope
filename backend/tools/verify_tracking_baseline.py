from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA_VERSION = 4
REQUIRED_COLUMNS = {
    "id",
    "ticker",
    "name",
    "market",
    "source",
    "recommendation_date",
    "reference_price",
    "snapshot_json",
    "snapshot_schema_version",
    "snapshot_hash",
    "has_scanner_source",
    "has_manual_source",
    "scanner_snapshot_json",
    "scanner_snapshot_hash",
    "scanner_attached_at",
    "status",
    "created_at",
    "closed_at",
    "closed_market_date",
    "close_performance_status",
}


def project_root() -> Path:
    # backend/tools/verify_tracking_baseline.py -> project root is two parents up:
    # tools -> backend -> StockScope
    return Path(__file__).resolve().parents[2]


def canonical_snapshot(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_snapshot(value).encode("utf-8")).hexdigest()


def load_json_dict(raw: str | None) -> dict[str, Any] | None:
    if raw is None or raw == "":
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def normalized_price(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None


def connect_read_only(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only TRACK.1 final baseline verifier")
    parser.add_argument(
        "--db",
        type=Path,
        default=project_root() / "backend" / "runtime" / "tracking" / "recommendation_tracking.db",
        help="Tracking SQLite database path",
    )
    args = parser.parse_args()
    db_path = args.db

    print("TRACK.1 Final Baseline Verification")
    print(f"Database: {db_path}")

    errors: list[str] = []
    warnings: list[str] = []

    if not db_path.exists():
        print("Status: FAILED")
        print("ERROR: tracking database does not exist")
        return 1

    with connect_read_only(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for required in {"tracking_meta", "tracked_recommendation", "recommendation_performance"}:
            if required not in tables:
                errors.append(f"missing table: {required}")

        if errors:
            print("Status: FAILED")
            for error in errors:
                print(f"ERROR: {error}")
            return 1

        meta_row = conn.execute(
            "SELECT value FROM tracking_meta WHERE key='schema_version'"
        ).fetchone()
        schema_version = int(meta_row["value"]) if meta_row and str(meta_row["value"]).isdigit() else None
        if schema_version != EXPECTED_SCHEMA_VERSION:
            errors.append(
                f"schema_version must be {EXPECTED_SCHEMA_VERSION}, got {schema_version!r}"
            )

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(tracked_recommendation)").fetchall()
        }
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            errors.append("missing columns: " + ", ".join(missing_columns))

        rows = conn.execute(
            "SELECT * FROM tracked_recommendation ORDER BY recommendation_date, created_at, id"
        ).fetchall()
        performance_rows = conn.execute(
            "SELECT recommendation_id FROM recommendation_performance"
        ).fetchall()

        row_ids = {row["id"] for row in rows}
        orphan_performance = [
            row["recommendation_id"]
            for row in performance_rows
            if row["recommendation_id"] not in row_ids
        ]
        if orphan_performance:
            errors.append(
                f"orphan performance rows: {len(orphan_performance)}"
            )

        baseline_groups: dict[tuple[str, str, str, Decimal], list[str]] = defaultdict(list)
        active_count = 0
        closed_count = 0
        scanner_count = 0
        manual_count = 0
        combined_count = 0
        snapshot_failures = 0
        scanner_snapshot_failures = 0

        for row in rows:
            status = str(row["status"] or "").upper()
            if status == "ACTIVE":
                active_count += 1
            elif status == "CLOSED":
                closed_count += 1
                if row["close_performance_status"] != "FROZEN":
                    warnings.append(
                        f"legacy CLOSED row lacks FROZEN metadata: {row['ticker']} {row['recommendation_date']} ({row['id']}); "
                        "runtime refresh is still blocked by CLOSED status"
                    )
            else:
                errors.append(f"invalid status {status!r} for row {row['id']}")

            source = str(row["source"] or "").upper()
            has_scanner = bool(row["has_scanner_source"]) or source == "SCANNER"
            has_manual = bool(row["has_manual_source"]) or source == "MANUAL"
            if source == "SCANNER" and not bool(row["has_scanner_source"]):
                errors.append(f"legacy SCANNER source flag not migrated: {row['id']}")
            if source == "MANUAL" and not bool(row["has_manual_source"]):
                errors.append(f"legacy MANUAL source flag not migrated: {row['id']}")

            scanner_count += int(has_scanner)
            manual_count += int(has_manual)
            combined_count += int(has_scanner and has_manual)

            price = normalized_price(row["reference_price"])
            if price is None:
                errors.append(f"invalid reference_price for row {row['id']}")
            else:
                baseline_groups[
                    (row["market"], row["ticker"], row["recommendation_date"], price)
                ].append(row["id"])

            snapshot = load_json_dict(row["snapshot_json"])
            if snapshot is None or not row["snapshot_hash"] or snapshot_digest(snapshot) != row["snapshot_hash"]:
                snapshot_failures += 1

            if has_scanner:
                scanner_snapshot = load_json_dict(row["scanner_snapshot_json"])
                if (
                    scanner_snapshot is None
                    or not row["scanner_snapshot_hash"]
                    or snapshot_digest(scanner_snapshot) != row["scanner_snapshot_hash"]
                ):
                    scanner_snapshot_failures += 1

        duplicates = [ids for ids in baseline_groups.values() if len(ids) > 1]
        if duplicates:
            errors.append(
                f"same-baseline duplicate groups remain: {len(duplicates)}"
            )
        if snapshot_failures:
            errors.append(f"snapshot integrity failures: {snapshot_failures}")
        if scanner_snapshot_failures:
            errors.append(f"scanner snapshot integrity failures: {scanner_snapshot_failures}")

        if not rows:
            warnings.append("tracking database has no rows; runtime lifecycle data could not be sampled")

        print(f"Schema version : {schema_version}")
        print(f"Rows           : {len(rows)}")
        print(f"ACTIVE/CLOSED  : {active_count}/{closed_count}")
        print(f"Scanner source : {scanner_count}")
        print(f"Manual source  : {manual_count}")
        print(f"Combined       : {combined_count}")
        print(f"Performance    : {len(performance_rows)}")
        print(f"Duplicate key  : {len(duplicates)}")

    for warning in warnings:
        print(f"WARNING: {warning}")

    if errors:
        print("Status: FAILED")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("Status: PASS")
    print("TRACK.1 runtime data satisfies the frozen baseline invariants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
