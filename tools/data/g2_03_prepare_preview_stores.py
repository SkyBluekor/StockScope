"""Prepare isolated G2-03 preview copies without changing operational SQLite.

Uses SQLite's online backup API (includes committed WAL state) instead of
raw file copying. Only writes under --destination; no migrations or imports.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def backup_readonly(source: Path, destination: Path) -> dict[str, str | int]:
    if not source.is_file():
        raise ValueError("SOURCE_SQLITE_MISSING")
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("SOURCE_AND_DESTINATION_SAME")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(
        prefix="g2-preview-", suffix=".db", dir=str(destination.parent),
    )
    os.close(fd)
    working = Path(temp)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            origin.execute("PRAGMA query_only=ON")
            with closing(sqlite3.connect(str(working))) as target:
                origin.backup(target)
                result = target.execute("PRAGMA integrity_check").fetchone()
                if result is None or result[0] != "ok":
                    raise ValueError("DESTINATION_INTEGRITY_FAILED")
        os.replace(working, destination)
        return {"status": "COPIED_TO_PREVIEW", "size_bytes": destination.stat().st_size}
    finally:
        working.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operational-simulation", type=Path, required=True)
    parser.add_argument("--operational-market", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    parser.add_argument("--operational-krx-budget", type=Path)
    parser.add_argument("--preview-krx-budget", type=Path)
    args = parser.parse_args()
    sources = [args.operational_simulation.resolve(), args.operational_market.resolve()]
    targets = [args.preview_dir.resolve() / "simulation.db",
               args.preview_dir.resolve() / "market_history.db"]
    if len(set(sources)) != 2 or set(sources) & set(targets):
        raise ValueError("PREVIEW_SOURCE_PATH_CONFLICT")
    if not all(s.is_file() for s in sources):
        raise ValueError("OPERATIONAL_DB_MISSING")
    report = [
        backup_readonly(source, target)
        for source, target in zip(sources, targets)
    ]
    if bool(args.operational_krx_budget) != bool(args.preview_krx_budget):
        raise ValueError("PREVIEW_BUDGET_ARGUMENTS_INCOMPLETE")
    budget = None
    if args.operational_krx_budget and args.preview_krx_budget:
        budget_source = args.operational_krx_budget.resolve()
        budget_target = args.preview_krx_budget.resolve()
        if budget_source in targets or budget_target in sources:
            raise ValueError("PREVIEW_BUDGET_SOURCE_PATH_CONFLICT")
        if budget_source.is_file():
            budget = backup_readonly(budget_source, budget_target)
    print(json.dumps({
        "status": "G2_PREVIEW_SNAPSHOT_READY", "operational_db_writes": 0,
        "preview_simulation": str(targets[0]),
        "preview_market": str(targets[1]),
        "copies": report,
        "budget_snapshot": budget,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
