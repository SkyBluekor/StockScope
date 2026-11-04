"""Create only the JEV-B3 Choice result table; preserves V4 and Scanner tables.

Example:
    .venv/Scripts/python.exe tools/data/migrate_jev_stock_choice.py
The simulation DB must already exist with Prospective capture tables.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.jev.stock_choice_catalog import migrate_stock_choice, StockChoiceStorageError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or ROOT / "backend" / "runtime" / "simulation" / "simulation.db"))
    args = parser.parse_args(argv)
    try:
        result = migrate_stock_choice(args.db)
    except StockChoiceStorageError as exc:
        print(json.dumps({"status": "BLOCKED", "code": exc.code, "db_writes": 0}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
