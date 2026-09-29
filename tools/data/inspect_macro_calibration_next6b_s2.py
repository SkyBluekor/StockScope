from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.reader import LocalMacroReader
from tools.data.common import macro_db_path


SERIES_ID = "US_10Y_CONSTANT_MATURITY_YIELD"


def main() -> int:
    reader = LocalMacroReader(macro_db_path())
    result = reader.inspect_reference_archive(SERIES_ID)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
