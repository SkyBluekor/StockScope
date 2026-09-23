from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

CSS = FRONTEND / "src" / "simulation.css"
WORKSPACE = FRONTEND / "src" / "components" / "SimulationWorkspace.tsx"
SERVICE = FRONTEND / "src" / "services" / "simulationApi.ts"
OUTCOME = BACKEND / "app" / "simulation" / "validation_outcome.py"
CATALOG = BACKEND / "app" / "simulation" / "validation_catalog.py"
API = BACKEND / "app" / "api" / "simulation.py"
SCANNER = BACKEND / "app" / "backtest" / "scanner.py"
PACKAGE = FRONTEND / "package.json"

CSS_APPEND = '/* VAL.3-A2.1 — result layout recovery */\n/* Existing .sim-saved-detail dl grid must not leak into nested A2 result layouts. */\n.sim-saved-detail .sim-outcome-facts,\n.sim-saved-detail .sim-outcome-movement,\n.sim-saved-detail .sim-outcome-method dl {\n  margin: 0;\n}\n\n.sim-saved-detail .sim-outcome-facts {\n  display: block;\n}\n\n.sim-saved-detail .sim-outcome-facts > div {\n  display: grid;\n  grid-template-columns: minmax(180px, 0.8fr) max-content;\n  align-items: baseline;\n  gap: 24px;\n  width: 100%;\n  min-width: 0;\n  padding: 9px 0;\n  border-bottom: 1px solid var(--border-subtle);\n}\n\n.sim-saved-detail .sim-outcome-facts dt,\n.sim-saved-detail .sim-outcome-facts dd {\n  min-width: 0;\n}\n\n.sim-saved-detail .sim-outcome-facts dt {\n  word-break: keep-all;\n  overflow-wrap: break-word;\n}\n\n.sim-saved-detail .sim-outcome-facts dd {\n  margin: 0;\n  color: var(--text-primary);\n  font-weight: 800;\n  text-align: right;\n  white-space: nowrap;\n  word-break: keep-all;\n  overflow-wrap: normal;\n}\n\n.sim-saved-detail .sim-outcome-section {\n  width: 100%;\n  min-width: 0;\n}\n\n.sim-saved-detail .sim-outcome-section > p,\n.sim-saved-detail .sim-outcome-explain p {\n  width: 100%;\n  max-width: 1000px;\n  word-break: keep-all;\n  overflow-wrap: break-word;\n}\n\n.sim-saved-detail .sim-outcome-table {\n  table-layout: auto;\n}\n\n.sim-saved-detail .sim-outcome-table th,\n.sim-saved-detail .sim-outcome-table td {\n  word-break: keep-all;\n}\n\n.sim-saved-detail .sim-outcome-table th:not(:first-child),\n.sim-saved-detail .sim-outcome-table td:not(:first-child) {\n  white-space: nowrap;\n}\n\n.sim-saved-detail .sim-outcome-movement {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));\n  width: 100%;\n}\n\n.sim-saved-detail .sim-outcome-movement > div {\n  display: block;\n  min-width: 0;\n}\n\n.sim-saved-detail .sim-outcome-movement dt,\n.sim-saved-detail .sim-outcome-movement dd,\n.sim-saved-detail .sim-outcome-movement small {\n  min-width: 0;\n}\n\n.sim-saved-detail .sim-outcome-movement dt,\n.sim-saved-detail .sim-outcome-movement dd {\n  word-break: keep-all;\n}\n\n.sim-saved-detail .sim-outcome-movement dd {\n  white-space: nowrap;\n}\n\n.sim-saved-detail .sim-outcome-movement small {\n  word-break: keep-all;\n  overflow-wrap: break-word;\n}\n\n.sim-saved-detail .sim-outcome-method dl {\n  display: block;\n}\n\n.sim-saved-detail .sim-outcome-method dl > div {\n  display: grid;\n  grid-template-columns: minmax(170px, 0.7fr) minmax(0, 1fr);\n  gap: 18px;\n  width: 100%;\n  min-width: 0;\n}\n\n.sim-saved-detail .sim-outcome-method dd {\n  min-width: 0;\n  word-break: keep-all;\n  overflow-wrap: break-word;\n}\n\n@media(max-width:800px) {\n  .sim-saved-detail .sim-outcome-facts > div {\n    grid-template-columns: 1fr;\n    gap: 3px;\n  }\n\n  .sim-saved-detail .sim-outcome-facts dd {\n    text-align: left;\n    white-space: normal;\n  }\n\n  .sim-saved-detail .sim-outcome-movement {\n    grid-template-columns: 1fr;\n  }\n\n  .sim-saved-detail .sim-outcome-table {\n    min-width: 620px;\n  }\n}\n\n@media(max-width:620px) {\n  .sim-saved-detail .sim-outcome-method dl > div {\n    grid-template-columns: 1fr;\n    gap: 3px;\n  }\n}\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    files = [path] if path.is_file() else sorted(
        p for p in path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    )
    for item in files:
        hasher.update(str(item.relative_to(ROOT)).replace("\\", "/").encode())
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def run(cmd: list[str], cwd: Path, label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("VAL.3-A2.1 — 전략 성과 검증 결과 화면 레이아웃 복구")
    print("Content wording changes: NO")
    print("Backend changes: NO")
    print("API changes: NO")
    print("Outcome number changes: NO")
    print("Theme support: LIGHT + DARK")

    required = [CSS, WORKSPACE, SERVICE, OUTCOME, CATALOG, API, SCANNER, PACKAGE]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")

    css_before = CSS.read_text(encoding="utf-8-sig")
    workspace_before = WORKSPACE.read_text(encoding="utf-8-sig")

    preflight = {
        "VAL.3-A2 CSS present": "VAL.3-A2 — result interpretation UX" in css_before,
        "result summary present": "검증 결과 요약" in workspace_before,
        "facts markup present": 'className="sim-outcome-facts"' in workspace_before,
        "movement markup present": 'className="sim-outcome-movement"' in workspace_before,
        "method markup present": 'className="sim-outcome-method"' in workspace_before,
    }
    for name, ok in preflight.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not all(preflight.values()):
        fail("VAL.3-A2 is not in the expected state.")
    if "VAL.3-A2.1 — result layout recovery" in css_before:
        fail("VAL.3-A2.1 already appears to be applied.")

    protected = {
        "workspace": sha256(WORKSPACE),
        "service": sha256(SERVICE),
        "outcome": sha256(OUTCOME),
        "catalog": sha256(CATALOG),
        "api": sha256(API),
        "scanner": sha256(SCANNER),
        "tracking": tree_hash(BACKEND / "app" / "tracking"),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "holdings": tree_hash(BACKEND / "app" / "holdings"),
    }

    original_css = css_before
    try:
        CSS.write_text(
            css_before.rstrip() + "\n\n" + CSS_APPEND.strip() + "\n",
            encoding="utf-8",
            newline="\n",
        )

        print()
        print("=== VAL.3-A2.1 STATIC CONTRACT ===")
        css_now = CSS.read_text(encoding="utf-8")
        workspace_now = WORKSPACE.read_text(encoding="utf-8")
        package_now = PACKAGE.read_text(encoding="utf-8").lower()

        checks = {
            "facts overrides inherited dl grid": ".sim-saved-detail .sim-outcome-facts {" in css_now and "display: block;" in css_now,
            "stable fact row": "grid-template-columns: minmax(180px, 0.8fr) max-content;" in css_now,
            "numeric nowrap": "white-space: nowrap;" in css_now,
            "Korean word-break protection": "word-break: keep-all;" in css_now,
            "result section full width": ".sim-saved-detail .sim-outcome-section {" in css_now and "width: 100%;" in css_now,
            "movement two-column desktop": "grid-template-columns: repeat(2, minmax(0, 1fr));" in css_now,
            "method dl override": ".sim-saved-detail .sim-outcome-method dl {" in css_now,
            "responsive fact stack": "@media(max-width:800px)" in css_now and "grid-template-columns: 1fr;" in css_now,
            "price table preserved": "이후 가격 변화" in workspace_now,
            "touch table preserved": "20거래일 안에 가격 기준에 닿은 경우" in workspace_now,
            "A2 wording preserved": "평균과 중앙값은 왜 같이 보나요?" in workspace_now,
            "no theme fork": 'html[data-theme=' not in CSS_APPEND and ":root" not in CSS_APPEND,
            "theme tokens reused": "var(--text-primary)" in CSS_APPEND and "var(--border-subtle)" in CSS_APPEND,
            "no paid dependency": all(name not in package_now for name in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            fail("Static contract failed: " + ", ".join(failed))

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            fail("npm was not found.")
        run([npm, "run", "build"], FRONTEND, "Frontend build")

        protected_after = {
            "workspace": sha256(WORKSPACE),
            "service": sha256(SERVICE),
            "outcome": sha256(OUTCOME),
            "catalog": sha256(CATALOG),
            "api": sha256(API),
            "scanner": sha256(SCANNER),
            "tracking": tree_hash(BACKEND / "app" / "tracking"),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "holdings": tree_hash(BACKEND / "app" / "holdings"),
        }
        if protected_after != protected:
            fail("Protected markup/backend/API/service source changed during CSS-only layout recovery.")

        print()
        print("VAL.3-A2.1 IMPLEMENTATION READY")
        print("Modified:")
        print(" - frontend/src/simulation.css")
        print("SimulationWorkspace content changes: 0")
        print("Backend changes: 0")
        print("API changes: 0")
        print("A1 outcome calculation changes: 0")
        print("Numeric/value nowrap: PASS")
        print("Nested saved-detail dl conflict override: PASS")
        print("Responsive fallback: PASS")
        print("Frontend build: PASS")
        print()
        print("NEXT UAT:")
        print(" 1) Open the same completed validation in Dark.")
        print(" 2) Check 과거 분석 범위 rows are horizontal and readable.")
        print(" 3) Check 5/10/20거래일 표 and price-touch rows do not wrap oddly.")
        print(" 4) Check 평균 최고 상승폭 / 평균 최대 하락폭 descriptions have normal width.")
        print(" 5) Toggle Light once.")
        print(" 6) Send one screenshot before reviewing wording.")
        return 0

    except Exception:
        CSS.write_text(original_css, encoding="utf-8", newline="\n")
        print()
        print("FAILED — VAL.3-A2.1 CSS changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
