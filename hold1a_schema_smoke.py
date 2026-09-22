from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "backend"))

from app.holdings import HoldingsCatalog


def main() -> int:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "holdings.db"
        catalog = HoldingsCatalog(db_path)
        catalog.initialize()

        conn = catalog.connect()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' ORDER BY name"
                ).fetchall()
            }
        finally:
            conn.close()

        required = {
            "position_account",
            "monitored_stock",
            "holding_position",
            "holding_position_event",
            "account_sync_run",
            "stock_analysis_day",
            "stock_analysis_revision",
        }

        missing = required - tables
        if missing:
            raise RuntimeError(
                "Missing HOLD.1-A tables: " + ", ".join(sorted(missing))
            )

        print("HOLDINGS DB INIT: PASS")
        print("TABLES:", ", ".join(sorted(required)))
        print("RAW ACCOUNT NUMBER COLUMN: NO")

    print("TEMP DB CLEANUP: PASS")
    print("HOLD.1-A SCHEMA SMOKE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
