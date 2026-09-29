from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.holdings import HoldingsCatalog
from app.macro import (
    LocalMacroReader,
    MacroObservation,
    MacroPreparedRangeManifest,
    MacroStore,
    fred_dgs10_candidate_contract,
)
from tools.data.backup_runtime import create_backup
from tools.data.common import DataToolError
from tools.data.macro_runtime import inspect_macro_store
from tools.data.restore_runtime import restore_backup


NOW = "2026-09-29T07:30:00+00:00"


def _holdings(path: Path) -> Path:
    HoldingsCatalog(path).initialize()
    return path


def _macro(path: Path) -> tuple[Path, str]:
    store = MacroStore(path, clock=lambda: NOW)
    store.initialize()
    store.register_series_contract(fred_dgs10_candidate_contract())
    run = store.begin_collection_run(provider="FRED", run_id="BACKUP-RUN")
    temporal = TemporalEvidence(
        event_time=None,
        source_published_at=None,
        provider_published_at="2026-09-29T06:00:00+00:00",
        first_seen_at="2026-09-29T06:00:00+00:00",
        available_at="2026-09-29T06:00:00+00:00",
        fetched_at="2026-09-29T06:01:00+00:00",
        time_quality=EvidenceTimeQuality.PROVIDER_TIME,
    )
    store.store_observation(
        run_id=run["run_id"],
        observation=MacroObservation(
            series_id="US_10Y_CONSTANT_MATURITY_YIELD",
            native_observation_id="DGS10:2026-09-28",
            observation_date="2026-09-28",
            source_value="4.10",
            normalized_value="4.10",
            source_unit="PERCENT",
            source_payload_hash="a" * 64,
            normalizer_version="DGS10-PERCENT-V1",
            realtime_start="2026-09-28",
            realtime_end="2026-09-28",
            vintage_id="2026-09-29",
            temporal=temporal,
        ),
    )
    store.publish_collection_run(run["run_id"])
    store.store_prepared_range(
        MacroPreparedRangeManifest(
            series_id="US_10Y_CONSTANT_MATURITY_YIELD",
            start_date="2026-09-28",
            end_date="2026-09-28",
            expected_count=1,
            stored_count=1,
            missing_count=0,
            unavailable_count=0,
            date_only_count=0,
            eligible_count=1,
            source_contract_version="FRED-DGS10-CANDIDATE-V1",
            normalizer_version="DGS10-PERCENT-V1",
            source_manifest_hash="b" * 64,
            prepared_at=NOW,
        )
    )
    snapshot = LocalMacroReader(path).read_snapshot(
        ["US_10Y_CONSTANT_MATURITY_YIELD"],
        cutoff="2026-09-29T07:00:00+00:00",
    )
    return path, snapshot["snapshot_hash"]


def test_macro_backup_restore_roundtrip_preserves_store_and_snapshot_hash(tmp_path: Path):
    holdings = _holdings(tmp_path / "holdings.db")
    macro, expected_snapshot_hash = _macro(tmp_path / "macro.db")
    before = inspect_macro_store(macro)

    backup = create_backup(
        destination=tmp_path / "backup",
        holdings_db=holdings,
        include_simulation=False,
        include_tracking=False,
        include_macro=True,
        macro_db=macro,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["contents"]["macro_db"] is True
    assert "macro.db" in manifest["files"]
    assert manifest["extensions"]["macro_store_v1"] == before
    assert manifest["secret_files_included"] == []

    target_holdings = tmp_path / "restored-holdings.db"
    target_macro = tmp_path / "restored-macro.db"
    result = restore_backup(
        backup,
        restore_macro=True,
        target_holdings=target_holdings,
        target_macro=target_macro,
    )

    after = inspect_macro_store(target_macro)
    restored_snapshot = LocalMacroReader(target_macro).read_snapshot(
        ["US_10Y_CONSTANT_MATURITY_YIELD"],
        cutoff="2026-09-29T07:00:00+00:00",
    )

    assert after == before
    assert restored_snapshot["snapshot_hash"] == expected_snapshot_hash
    assert result["macro_db"] == str(target_macro)
    assert result["macro_store"]["manifest_present"] is True
    assert result["macro_store"]["store_present_in_backup"] is True
    assert result["macro_store"]["store_restored"] is True
    assert result["macro_store"]["counts"] == before["counts"]


def test_partial_macro_schema_blocks_backup_publication(tmp_path: Path):
    holdings = _holdings(tmp_path / "holdings.db")
    macro = tmp_path / "macro.db"
    with sqlite3.connect(macro) as conn:
        conn.execute(
            """
            CREATE TABLE macro_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

    destination = tmp_path / "bad-backup"
    with pytest.raises(DataToolError, match="부분 migration"):
        create_backup(
            destination=destination,
            holdings_db=holdings,
            include_simulation=False,
            include_tracking=False,
            include_macro=True,
            macro_db=macro,
        )
    assert not destination.exists()


def test_tampered_macro_backup_manifest_blocks_restore_before_target_change(tmp_path: Path):
    holdings = _holdings(tmp_path / "holdings.db")
    macro, _ = _macro(tmp_path / "macro.db")
    backup = create_backup(
        destination=tmp_path / "backup",
        holdings_db=holdings,
        include_simulation=False,
        include_tracking=False,
        include_macro=True,
        macro_db=macro,
    )

    manifest_path = backup / "backup_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["extensions"]["macro_store_v1"]["counts"][
        "observation_revision_count"
    ] = 999
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    target_holdings = _holdings(tmp_path / "target-holdings.db")
    target_macro, _ = _macro(tmp_path / "target-macro.db")
    with sqlite3.connect(target_macro) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM macro_observation_revision"
        ).fetchone()[0]

    with pytest.raises(DataToolError, match="backup manifest"):
        restore_backup(
            backup,
            restore_macro=True,
            target_holdings=target_holdings,
            target_macro=target_macro,
        )

    with sqlite3.connect(target_macro) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM macro_observation_revision"
        ).fetchone()[0]
    assert after == before
