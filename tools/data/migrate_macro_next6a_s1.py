from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data.common import ensure_backend_import_path, macro_db_path


def migrate_macro_store(path: Path | None = None) -> dict[str, object]:
    ensure_backend_import_path()
    from app.macro.store import MacroStore

    target = Path(path or macro_db_path())
    store = MacroStore(target)
    state = store.initialize()
    return {
        **state,
        "historical_backfill_performed": False,
        "external_network_requests": 0,
    }


def main() -> int:
    result = migrate_macro_store()
    print("=" * 78)
    print("STOCKSCOPE NEXT-6A-S1 MACRO STORE MIGRATION")
    print("=" * 78)
    print("Schema               PASS")
    print("Historical backfill  NO")
    print("External network     0")
    print("Series contracts    ", result["counts"]["series_contract_count"])
    print("Observations        ", result["counts"]["observation_revision_count"])
    print("Prepared ranges     ", result["counts"]["prepared_range_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
