from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data.backup_runtime import create_backup
from tools.data.common import (
    DEFAULT_BACKUP_ROOT,
    DataToolError,
    ensure_backend_import_path,
    iso_now,
    sqlite_readonly,
    utc_stamp,
    validate_holdings_db,
    validate_market_db,
    validate_simulation_db,
    validate_tracking_db,
)
from tools.data.macro_runtime import validate_macro_db
from tools.dev.sync_local import RuntimePaths, sync_runtime
from tools.runtime.bootstrap_state import (
    pristine_candidates,
    record_pristine_domains,
)
from tools.runtime.handoff import RuntimeLocations


SETUP_CONTRACT = "STOCKSCOPE_ENV_V2_T2_FRESH_SETUP_V1"


def _domain_paths(runtime: RuntimeLocations) -> dict[str, Path]:
    return {
        "holdings": Path(runtime.holdings),
        "market": Path(runtime.market),
        "simulation": Path(runtime.simulation),
        "tracking": Path(runtime.tracking),
        "macro": Path(runtime.macro),
    }


def _tracking_version(path: Path) -> int:
    with sqlite_readonly(path) as conn:
        try:
            row = conn.execute(
                "SELECT value FROM tracking_meta WHERE key='schema_version'"
            ).fetchone()
        except sqlite3.Error as exc:
            raise DataToolError(
                "Tracking DB schema version을 읽을 수 없습니다."
            ) from exc
    if row is None:
        raise DataToolError("Tracking DB schema_version이 없습니다.")
    try:
        return int(str(row[0]))
    except ValueError as exc:
        raise DataToolError("Tracking DB schema_version 형식이 잘못되었습니다.") from exc


def _simulation_version(path: Path) -> int | None:
    with sqlite_readonly(path) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "simulation_schema_meta" not in names:
            return None
        row = conn.execute(
            "SELECT value FROM simulation_schema_meta WHERE key='schema_version'"
        ).fetchone()
    if row is None:
        raise DataToolError("Simulation schema_version이 없습니다.")
    try:
        return int(str(row[0]))
    except ValueError as exc:
        raise DataToolError("Simulation schema_version 형식이 잘못되었습니다.") from exc


def _validate_existing(runtime: RuntimeLocations) -> dict[str, bool]:
    ensure_backend_import_path()

    from app.simulation.sim1_store import CURRENT_SCHEMA_VERSION
    from app.tracking.store import RecommendationTrackingRepository

    paths = _domain_paths(runtime)
    existing = {domain: path.is_file() for domain, path in paths.items()}

    # A durable non-Holdings domain without Holdings is ambiguous: it may be a
    # failed setup, a partial restore, or real user history. Do not silently
    # classify it as a new project and create a new root identity around it.
    if not existing["holdings"] and any(
        existing[domain]
        for domain in ("simulation", "tracking", "macro")
    ):
        raise DataToolError(
            "기존 durable runtime 일부가 있지만 Holdings DB가 없습니다. "
            "Fresh setup으로 자동 재구성하지 않습니다. restore/repair 상태를 확인하세요."
        )

    if existing["holdings"]:
        validate_holdings_db(paths["holdings"])
    if existing["market"]:
        validate_market_db(paths["market"])
    if existing["simulation"]:
        validate_simulation_db(paths["simulation"])
        version = _simulation_version(paths["simulation"])
        if version is not None and version > int(CURRENT_SCHEMA_VERSION):
            raise DataToolError(
                "현재 코드보다 새로운 Simulation schema입니다: "
                f"{version} > {CURRENT_SCHEMA_VERSION}"
            )
    if existing["tracking"]:
        validate_tracking_db(paths["tracking"])
        version = _tracking_version(paths["tracking"])
        if version > int(RecommendationTrackingRepository.SCHEMA_VERSION):
            raise DataToolError(
                "현재 코드보다 새로운 Tracking schema입니다: "
                f"{version} > {RecommendationTrackingRepository.SCHEMA_VERSION}"
            )
    if existing["macro"]:
        validate_macro_db(paths["macro"])
    return existing


def _backup_existing(
    *,
    runtime: RuntimeLocations,
    existing: dict[str, bool],
    backup_root: Path,
) -> Path | None:
    if not existing["holdings"]:
        return None
    destination = (
        backup_root
        / f"StockScope_Setup_{utc_stamp()}_{uuid4().hex[:8]}"
    )
    return create_backup(
        destination=destination,
        include_market=existing["market"],
        holdings_db=runtime.holdings,
        market_db=runtime.market,
        simulation_db=runtime.simulation,
        tracking_db=runtime.tracking,
        macro_db=runtime.macro,
        include_simulation=existing["simulation"],
        include_tracking=existing["tracking"],
        include_macro=existing["macro"],
        strategy_selection_runtime=runtime.strategy_selection,
    )


def _initialize_owner_schemas(runtime: RuntimeLocations) -> None:
    ensure_backend_import_path()

    from app.backtest.market_store import HistoricalMarketStore
    from app.holdings import HoldingsCatalog
    from app.macro import MacroStore
    from app.simulation.execution_catalog import HistoricalExecutionCatalog
    from app.simulation.sim1_store import SimulationRepository
    from app.tracking.store import RecommendationTrackingRepository

    HoldingsCatalog(runtime.holdings).initialize()
    HistoricalMarketStore(runtime.market)

    # Fresh setup intentionally prepares both legacy Simulation and VAL.1/VAL.2
    # base families. VN migrations remain the owner of later extensions.
    SimulationRepository(runtime.simulation).initialize()
    HistoricalExecutionCatalog(runtime.simulation).initialize()

    RecommendationTrackingRepository(runtime.tracking).initialize()

    if not Path(runtime.macro).is_file():
        MacroStore(runtime.macro).initialize()
    else:
        validate_macro_db(runtime.macro)


def _configuration_status() -> dict[str, object]:
    values: dict[str, str] = {}
    env_path = ROOT / ".env"
    if env_path.is_file():
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip().upper()] = value.strip().strip('"').strip("'")
        except OSError:
            pass

    for key in (
        "KRX_API_KEY",
        "DART_API_KEY",
        "FRED_API_KEY",
        "NAVER_NEWS_CLIENT_ID",
        "NAVER_NEWS_CLIENT_SECRET",
        "KIS_APP_KEY",
        "KIS_APP_SECRET",
        "KIS_ACCOUNT_NO",
    ):
        env_value = (os.getenv(key) or "").strip()
        if env_value:
            values[key] = env_value

    providers: list[str] = []
    if values.get("KRX_API_KEY"):
        providers.append("KRX")
    if values.get("DART_API_KEY"):
        providers.append("DART")
    if values.get("FRED_API_KEY"):
        providers.append("FRED")
    if (
        values.get("NAVER_NEWS_CLIENT_ID")
        and values.get("NAVER_NEWS_CLIENT_SECRET")
    ):
        providers.append("NAVER")
    if values.get("KIS_APP_KEY") and values.get("KIS_APP_SECRET"):
        providers.append("KIS")

    return {
        "status": "PASS" if providers else "ACTION_REQUIRED",
        "configured_providers": providers,
        "secrets_exposed": False,
    }


def _market_data_status(path: Path) -> dict[str, object]:
    with sqlite_readonly(path) as conn:
        rows = int(
            conn.execute(
                "SELECT COUNT(*) FROM day_status WHERE status='data'"
            ).fetchone()[0]
        )
        stock_rows = int(
            conn.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0]
        )
        index_rows = int(
            conn.execute("SELECT COUNT(*) FROM main_index_daily").fetchone()[0]
        )
    ready = rows > 0 and stock_rows > 0 and index_rows > 0
    return {
        "status": "READY" if ready else "DATA_REQUIRED",
        "day_status_rows": rows,
        "stock_rows": stock_rows,
        "index_rows": index_rows,
    }


def bootstrap_runtime(
    *,
    backup_root: Path | None = None,
    locations: RuntimeLocations | None = None,
    migration_backup_factory: Callable[..., Path] = create_backup,
) -> dict[str, object]:
    runtime = locations or RuntimeLocations.current()
    paths = _domain_paths(runtime)
    backups = Path(backup_root or DEFAULT_BACKUP_ROOT)
    backups.mkdir(parents=True, exist_ok=True)

    existing = _validate_existing(runtime)
    pristine = pristine_candidates(
        continuity_state=runtime.continuity_state,
        domain_paths=paths,
    )
    pre_setup_backup = _backup_existing(
        runtime=runtime,
        existing=existing,
        backup_root=backups,
    )

    _initialize_owner_schemas(runtime)

    sync_paths = RuntimePaths(
        holdings=Path(runtime.holdings),
        market=Path(runtime.market),
        simulation=Path(runtime.simulation),
    )
    effective_migration_backup_factory = migration_backup_factory
    if migration_backup_factory is create_backup:
        def setup_migration_backup() -> Path:
            destination = (
                backups
                / f"StockScope_SetupMigration_{utc_stamp()}_{uuid4().hex[:8]}"
            )
            return create_backup(
                destination=destination,
                include_market=True,
                holdings_db=runtime.holdings,
                market_db=runtime.market,
                simulation_db=runtime.simulation,
                tracking_db=runtime.tracking,
                macro_db=runtime.macro,
                include_simulation=True,
                include_tracking=True,
                include_macro=True,
                strategy_selection_runtime=runtime.strategy_selection,
            )

        effective_migration_backup_factory = setup_migration_backup

    sync_result = sync_runtime(
        paths=sync_paths,
        backup_factory=effective_migration_backup_factory,
    )

    validate_holdings_db(runtime.holdings)
    validate_market_db(runtime.market)
    validate_simulation_db(runtime.simulation)
    validate_tracking_db(runtime.tracking)
    validate_macro_db(runtime.macro)

    marker = record_pristine_domains(
        continuity_state=runtime.continuity_state,
        domain_paths=paths,
        eligible_domains=pristine,
    )

    return {
        "contract_version": SETUP_CONTRACT,
        "status": "COMPLETE",
        "environment": sync_result["environment"],
        "paths": {key: str(value) for key, value in paths.items()},
        "created": {
            domain: not existing[domain]
            for domain in paths
        },
        "pre_setup_backup": (
            str(pre_setup_backup) if pre_setup_backup is not None else None
        ),
        "migration_backup": sync_result.get("backup"),
        "runtime_migrations": sync_result["statuses"],
        "fresh_bootstrap_domains": sorted(
            (marker.get("domains") or {}).keys()
        ),
        "configuration": _configuration_status(),
        "market_data": _market_data_status(Path(runtime.market)),
        "application": "READY",
        "google_drive_required": False,
        "external_network_requests": 0,
        "secrets": "UNCHANGED",
        "completed_at": iso_now(),
    }


def _print_result(result: dict[str, object]) -> None:
    created = dict(result["created"])
    configuration = dict(result["configuration"])
    market_data = dict(result["market_data"])

    print("=" * 78)
    print("STOCKSCOPE SETUP")
    print("=" * 78)
    print("Environment             PASS")
    print("Runtime directories     PASS")
    for domain, label in (
        ("holdings", "Holdings database"),
        ("simulation", "Simulation database"),
        ("market", "Market schema"),
        ("tracking", "Tracking database"),
        ("macro", "Macro database"),
    ):
        state = "CREATED / CURRENT" if created.get(domain) else "CURRENT"
        print(f"{label:<24}{state}")
    print("Runtime migrations      " + str(result["environment"]))
    print(
        "Configuration           "
        + str(configuration.get("status"))
    )
    print("Market data             " + str(market_data.get("status")))
    print("Google Drive            NOT REQUIRED")
    print("External network        0")
    print("Application             " + str(result["application"]))
    print("")
    if configuration.get("status") == "ACTION_REQUIRED":
        print("SETUP COMPLETE - API SETTINGS REQUIRED")
        print("Copy .env.example to .env and add only the providers you use.")
    elif market_data.get("status") == "DATA_REQUIRED":
        print("SETUP COMPLETE - MARKET DATA REQUIRED FOR DATA-DEPENDENT FEATURES")
    else:
        print("SETUP COMPLETE")


def main() -> int:
    try:
        result = bootstrap_runtime()
        _print_result(result)
        return 0
    except (DataToolError, sqlite3.Error, OSError) as exc:
        print("=" * 78, file=sys.stderr)
        print("STOCKSCOPE SETUP FAILED", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "No automatic reset, destructive overwrite, or schema downgrade was performed.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
