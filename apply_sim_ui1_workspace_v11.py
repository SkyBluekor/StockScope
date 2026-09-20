from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PAYLOAD = Path(__file__).resolve().parent / "sim_ui1_v11_payload"

NEW_FILES = [
    "backend/app/api/simulation.py",
    "backend/tests/test_simulation_ui1_api_integration.py",
    "frontend/src/services/simulationApi.ts",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/simulation.css",
    "frontend/tests/test_simulation_ui1_source.py",
]


def run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    print("RUN ", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def require(path: str) -> Path:
    target = ROOT / path
    if not target.exists():
        raise RuntimeError(f"Required file missing: {path}")
    return target


def install_new_file(rel: str, created: list[Path]) -> None:
    src = PAYLOAD / rel
    dst = ROOT / rel
    if dst.exists():
        if dst.read_bytes() == src.read_bytes():
            print(f"KEEP {rel}")
            return
        raise RuntimeError(f"Refusing to overwrite changed existing file: {rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    created.append(dst)
    print(f"ADD  {rel}")


def patch_api_router(text: str) -> str:
    if "simulation_api.router" in text:
        return text
    match = re.search(r"(?m)^(\w+)\s*=\s*APIRouter\(", text)
    if not match:
        raise RuntimeError("Could not find APIRouter assignment in backend/app/api/router.py")
    router_var = match.group(1)
    import_line = "from app.api import simulation as simulation_api\n"
    if import_line.strip() not in text:
        insert_at = match.start()
        text = text[:insert_at] + import_line + text[insert_at:]
    text = text.rstrip() + f"\n{router_var}.include_router(simulation_api.router)\n"
    return text


def patch_app(text: str) -> str:
    if 'import SimulationWorkspace from "./components/SimulationWorkspace";' not in text:
        anchor = 'import ScannerPanel from "./components/ScannerPanel";'
        if anchor not in text:
            raise RuntimeError("App.tsx ScannerPanel import anchor not found")
        text = text.replace(anchor, anchor + '\nimport SimulationWorkspace from "./components/SimulationWorkspace";', 1)

    text = re.sub(
        r'type AppPage = "analysis" \| "backtest" \| "scanner";',
        'type AppPage = "analysis" | "backtest" | "scanner" | "simulation";',
        text,
        count=1,
    )
    if 'if (lower.startsWith("/simulation")) return "simulation";' not in text:
        anchor = 'if (lower.startsWith("/scanner")) return "scanner";'
        if anchor not in text:
            raise RuntimeError("App.tsx pathname anchor not found")
        text = text.replace(anchor, 'if (lower.startsWith("/simulation")) return "simulation";\n  ' + anchor, 1)

    nav_old = '<button className="nav-item" disabled>시뮬레이션 <em>준비중</em></button>'
    nav_new = '<button className={`nav-item ${appPage === "simulation" ? "active" : ""}`} onClick={() => navigateApp("simulation")}>시뮬레이션</button>'
    if nav_old in text:
        text = text.replace(nav_old, nav_new, 1)
    elif nav_new not in text:
        raise RuntimeError("App.tsx Simulation nav anchor not found")

    old_path = 'const pathname = page === "analysis" ? "/analysis" : page === "scanner" ? "/scanner" : "/backtest";'
    new_path = 'const pathname = page === "analysis" ? "/analysis" : `/${page}`;'
    if old_path in text:
        text = text.replace(old_path, new_path, 1)
    elif new_path not in text:
        raise RuntimeError("App.tsx navigateApp pathname anchor not found")

    if '<SimulationWorkspace />' not in text:
        pattern = re.compile(
            r'(\)\s*:\s*\(\s*)(<ScannerPanel\b[\s\S]*?\/>)(\s*\)\})',
            re.MULTILINE,
        )
        matches = list(pattern.finditer(text))
        if not matches:
            raise RuntimeError("App.tsx ScannerPanel terminal render block not found")
        match = matches[-1]
        scanner = match.group(2)
        replacement = ') : appPage === "scanner" ? (\n            ' + scanner + '\n          ) : (\n            <SimulationWorkspace />\n          )}'
        text = text[:match.start()] + replacement + text[match.end():]

    required = [
        '"simulation"',
        '<SimulationWorkspace />',
        'navigateApp("simulation")',
        'lower.startsWith("/simulation")',
    ]
    if not all(token in text for token in required):
        raise RuntimeError("App.tsx patch validation failed")
    return text


def main() -> int:
    require("backend/app/simulation/sim1_api.py")
    require("backend/app/simulation/sim2_api.py")
    require("backend/app/simulation/sim3_api.py")
    require("backend/tools/verify_scanner_production_baseline.py")
    router_path = require("backend/app/api/router.py")
    app_path = require("frontend/src/App.tsx")
    require("frontend/package.json")

    created: list[Path] = []
    originals = {router_path: router_path.read_text(encoding="utf-8"), app_path: app_path.read_text(encoding="utf-8")}
    try:
        for rel in NEW_FILES:
            install_new_file(rel, created)

        patched_router = patch_api_router(originals[router_path])
        patched_app = patch_app(originals[app_path])
        if patched_router != originals[router_path]:
            router_path.write_text(patched_router, encoding="utf-8", newline="\n")
            print("UPDATE backend/app/api/router.py")
        else:
            print("KEEP backend/app/api/router.py")
        if patched_app != originals[app_path]:
            app_path.write_text(patched_app, encoding="utf-8", newline="\n")
            print("UPDATE frontend/src/App.tsx")
        else:
            print("KEEP frontend/src/App.tsx")

        env_python = sys.executable
        tests = [
            "backend/tests/test_scanner_production_baseline_sim0.py",
            "backend/tests/test_simulation_domain_sim1.py",
            "backend/tests/test_simulation_trading_sim2.py",
            "backend/tests/test_simulation_playback_sim3.py",
            "backend/tests/test_simulation_ui1_api_integration.py",
            "frontend/tests/test_simulation_ui1_source.py",
        ]
        run([env_python, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"])
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found on PATH")
        run([npm, "--prefix", "frontend", "run", "build"])
        run([env_python, "backend/tools/verify_scanner_production_baseline.py"])

        print("SIM.UI.1 v1.1 Simulation Workspace applied; backend/SIM regression + frontend build passed.")
        print("Simulation API router is live under /api/simulation; Production Scanner baseline was re-verified.")
        return 0
    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        for path in reversed(created):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        print("SIM.UI.1 apply failed; patched files were rolled back.", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
