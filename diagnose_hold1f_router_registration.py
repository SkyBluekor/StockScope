from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "backend"))

print("PROJECT ROOT:", ROOT)
print("HOLD.1-F ROUTER DIAGNOSTIC")
print("MODIFIES FILES: NO")
print()

import app.main as main_module
import app.api.router as router_module

print("=== MODULE RESOLUTION ===")
print("app.main:", Path(main_module.__file__).resolve())
print("app.api.router:", Path(router_module.__file__).resolve())
print()

main_router = getattr(main_module, "api_router", None)
router_router = getattr(router_module, "api_router", None)

print("=== ROUTER OBJECT IDENTITY ===")
print("main_module.api_router exists:", main_router is not None)
print("router_module.api_router exists:", router_router is not None)
if main_router is not None and router_router is not None:
    print("same object:", main_router is router_router)
    print("main api_router id:", id(main_router))
    print("router api_router id:", id(router_router))
print()

print("=== api_router ROUTES ===")
if router_router is None:
    print("api_router: MISSING")
else:
    paths = [getattr(route, "path", None) for route in router_router.routes]
    print("count:", len(paths))
    for path in paths:
        print(" -", path)
print()

print("=== FastAPI app ROUTES ===")
app = main_module.app
app_paths = [getattr(route, "path", None) for route in app.routes]
print("count:", len(app_paths))
for path in app_paths:
    print(" -", path)
print()

router_path = Path(router_module.__file__).resolve()
main_path = Path(main_module.__file__).resolve()

print("=== router.py CURRENT SOURCE ===")
print(router_path.read_text(encoding="utf-8-sig"))
print()

print("=== main.py CURRENT SOURCE ===")
print(main_path.read_text(encoding="utf-8-sig"))
print()

print("=== F FILE EXISTENCE ===")
for rel in (
    "backend/app/api/holdings.py",
    "backend/app/api/integrations.py",
    "backend/tests/test_holdings_api_hold1f.py",
    "backend/tests/test_integrations_status_hold1f.py",
):
    path = ROOT / rel
    print(rel, "=>", "EXISTS" if path.exists() else "MISSING")
print()

print("DIAGNOSTIC COMPLETE")
