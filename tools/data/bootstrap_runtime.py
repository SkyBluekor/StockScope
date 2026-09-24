from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data.common import (
    DEFAULT_BACKUP_ROOT,
    DataToolError,
    ensure_backend_import_path,
    holdings_db_path,
    market_db_path,
    validate_holdings_db,
)


def bootstrap_runtime(*, backup_root: Path | None = None) -> dict[str, str]:
    ensure_backend_import_path()

    from app.holdings import HoldingsCatalog

    holdings = holdings_db_path()
    market = market_db_path()

    holdings.parent.mkdir(parents=True, exist_ok=True)
    market.parent.mkdir(parents=True, exist_ok=True)
    backups = Path(backup_root or DEFAULT_BACKUP_ROOT)
    backups.mkdir(parents=True, exist_ok=True)

    catalog = HoldingsCatalog(holdings)
    catalog.initialize()
    validate_holdings_db(holdings)

    return {
        "holdings_db": str(holdings),
        "market_history_db": str(market),
        "backup_root": str(backups),
    }


def main() -> int:
    try:
        result = bootstrap_runtime()
        print("=" * 78)
        print("STOCKSCOPE RUNTIME BOOTSTRAP")
        print("=" * 78)
        print("Holdings directory       PASS")
        print("Holdings schema          PASS")
        print("Market directory         PASS")
        print("Market DB created        NO")
        print("Market DB deleted        NO")
        print("Backup directory         PASS")
        print("")
        print("Holdings DB:", result["holdings_db"])
        print("Market DB  :", result["market_history_db"])
        return 0
    except (DataToolError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
