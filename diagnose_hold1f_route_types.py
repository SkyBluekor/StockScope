from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import __version__ as fastapi_version
import starlette
import app.api.router as router_module
import app.api.health as health_module
import app.api.data_sources as data_sources_module
import app.api.backtest as backtest_module
import app.api.simulation as simulation_module

print("FASTAPI:", fastapi_version)
print("STARLETTE:", starlette.__version__)
print()

for label, router in (
    ("central", router_module.api_router),
    ("health", health_module.router),
    ("data_sources", data_sources_module.router),
    ("backtest", backtest_module.router),
    ("simulation", simulation_module.router),
):
    print(f"=== {label} router ===")
    print("type:", type(router))
    print("routes:", len(getattr(router, "routes", [])))
    for index, route in enumerate(getattr(router, "routes", [])):
        print(
            index,
            "type=", type(route),
            "repr=", repr(route),
            "path=", getattr(route, "path", "<NO_ATTR>"),
            "path_format=", getattr(route, "path_format", "<NO_ATTR>"),
            "methods=", getattr(route, "methods", "<NO_ATTR>"),
        )
    print()

print("=== include_router implementation ===")
import inspect
from fastapi import APIRouter
print(inspect.getsource(APIRouter.include_router))
