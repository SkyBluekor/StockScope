from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
CATALOG = ROOT / "backend" / "app" / "holdings" / "catalog.py"


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(cmd: list[str], label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    if not CATALOG.is_file():
        fail(f"Missing file: {CATALOG}")

    original = CATALOG.read_text(encoding="utf-8-sig")
    patched = original

    if "from contextlib import contextmanager" not in patched:
        anchor = "import json\nimport re\nimport sqlite3\n"
        if anchor not in patched:
            fail("Import anchor not found.")
        patched = patched.replace(
            anchor,
            "import json\nimport re\nimport sqlite3\nfrom contextlib import contextmanager\n",
            1,
        )

    if "def connection(self)" not in patched:
        anchor = (
            "    def connect(self) -> sqlite3.Connection:\n"
            "        self.db_path.parent.mkdir(parents=True, exist_ok=True)\n"
            "        conn = sqlite3.connect(self.db_path)\n"
            "        conn.row_factory = sqlite3.Row\n"
            "        conn.execute(\"PRAGMA foreign_keys=ON\")\n"
            "        return conn\n\n"
        )
        replacement = anchor + (
            "    @contextmanager\n"
            "    def connection(self):\n"
            "        \"\"\"Transaction scope that always closes the SQLite handle.\"\"\"\n"
            "        conn = self.connect()\n"
            "        try:\n"
            "            with conn:\n"
            "                yield conn\n"
            "        finally:\n"
            "            conn.close()\n\n"
        )
        if anchor not in patched:
            fail("connect() anchor not found.")
        patched = patched.replace(anchor, replacement, 1)

    replaced_count = patched.count("with self.connect() as conn:")
    patched = patched.replace(
        "with self.connect() as conn:",
        "with self.connection() as conn:",
    )

    if "with self.connect() as conn:" in patched:
        fail("Unconverted connection scope remains.")

    compile(patched, str(CATALOG), "exec")

    try:
        CATALOG.write_text(patched, encoding="utf-8", newline="\n")

        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        python_exe = str(
            venv_python if venv_python.is_file() else Path(sys.executable)
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_holdings_catalog_hold1a.py",
                "-q",
            ],
            "HOLD.1-A persistence regression",
        )

        kis_tests = [
            "backend/tests/test_kis_client.py",
            "backend/tests/test_kis_account.py",
            "backend/tests/test_kis_quote.py",
            "backend/tests/test_kis_websocket.py",
        ]
        existing = [p for p in kis_tests if (ROOT / p).is_file()]
        if existing:
            run(
                [python_exe, "-m", "pytest", *existing, "-q"],
                "Existing KIS regression",
            )

        smoke = (
            "import sys\n"
            "from pathlib import Path\n"
            "from tempfile import TemporaryDirectory\n"
            "sys.path.insert(0, 'backend')\n"
            "from app.holdings import HoldingsCatalog\n"
            "with TemporaryDirectory() as tmp:\n"
            "    db = Path(tmp) / 'holdings.db'\n"
            "    catalog = HoldingsCatalog(db)\n"
            "    catalog.initialize()\n"
            "    with catalog.connection() as conn:\n"
            "        tables = {row['name'] for row in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()}\n"
            "    required = {'position_account','monitored_stock','holding_position','holding_position_event','account_sync_run','stock_analysis_day','stock_analysis_revision'}\n"
            "    assert required.issubset(tables)\n"
            "    print('HOLDINGS DB INIT: PASS')\n"
            "    print('TABLES:', ', '.join(sorted(required)))\n"
            "print('TEMP DB CLEANUP: PASS')\n"
            "print('HOLD.1-A CONNECTION LIFECYCLE: PASS')\n"
        )
        run([python_exe, "-c", smoke], "Windows temp DB cleanup smoke")

        print()
        print("HOLD.1-A CONNECTION FIX COMPLETE")
        print(f"Converted connection scopes: {replaced_count}")
        print("SQLite handles now close deterministically: YES")
        print("HOLD.1-A tests: PASS")
        print("KIS regression: PASS")
        print("Windows temp DB cleanup: PASS")
        return 0

    except Exception:
        CATALOG.write_text(original, encoding="utf-8", newline="\n")
        print()
        print("FAILED — catalog.py restored to its pre-fix state.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
