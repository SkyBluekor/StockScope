from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = ROOT / "tools" / "research" / "probe_krx_sector_membership.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "probe_krx_sector_membership",
        PROBE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_is_offline_only_and_has_no_network_dependency():
    source = PROBE_PATH.read_text(encoding="utf-8")

    assert "import requests" not in source
    assert "import httpx" not in source
    assert "urllib.request" not in source
    assert "network_access" in source
    assert '"network_access": False' in source


def test_same_membership_export_has_deterministic_hashes():
    probe = _load_probe()
    rows = [
        {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"},
        {"ISU_SRT_CD": "000660", "ISU_ABBRV": "SK하이닉스"},
    ]

    first = probe.inspect_membership_export(
        rows=rows,
        metadata={},
        query_date="20220902",
        benchmark_identity="KRX:KOSPI:SECTOR:26",
        source_label="KRX_DATA_MARKETPLACE_EXPORT",
    )
    second = probe.inspect_membership_export(
        rows=list(reversed(rows)),
        metadata={},
        query_date="20220902",
        benchmark_identity="KRX:KOSPI:SECTOR:26",
        source_label="KRX_DATA_MARKETPLACE_EXPORT",
    )

    assert first["payload_hash"] == second["payload_hash"]
    assert first["constituents_hash"] == second["constituents_hash"]
    assert first["row_count"] == 2
    assert first["constituent_identity_supported"] is True
    assert first["historical_snapshot_supported"] is True


def test_query_date_and_fetch_context_never_become_known_at():
    probe = _load_probe()
    result = probe.inspect_membership_export(
        rows=[{"종목코드": "005930", "종목명": "삼성전자"}],
        metadata={
            "query_date": "20220902",
            "fetched_at": "2026-10-01T05:00:00+00:00",
        },
        query_date="20220902",
        benchmark_identity="KRX:KOSPI:SECTOR:26",
        source_label="KRX_DATA_MARKETPLACE_EXPORT",
    )

    assert result["known_at_metadata_fields"] == []
    assert result["known_at_proven"] is False
    assert result["pit_contract_compatible"] is False
    assert result["reason"] == "SNAPSHOT_HAS_NO_VERIFIED_SOURCE_TIME_PROOF"
    assert "QUERY_DATE_IS_NOT_KNOWN_AT" in result["limitations"]
    assert "FETCH_TIME_IS_NOT_KNOWN_AT" in result["limitations"]


def test_even_source_time_named_metadata_is_not_authenticated_by_offline_probe():
    probe = _load_probe()
    result = probe.inspect_membership_export(
        rows=[{"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"}],
        metadata={"published_at": "2022-09-01T09:00:00+09:00"},
        query_date="20220902",
        benchmark_identity="KRX:KOSPI:SECTOR:26",
        source_label="TEST_AUTHORIZED_EXPORT",
    )

    assert result["known_at_metadata_fields"] == ["published_at"]
    assert result["known_at_proven"] is False
    assert result["pit_contract_compatible"] is False
    assert (
        result["reason"]
        == "SOURCE_TIME_METADATA_PRESENT_BUT_NOT_AUTHENTICATED_BY_OFFLINE_PROBE"
    )


def test_missing_constituent_code_fails_closed():
    probe = _load_probe()

    with pytest.raises(ValueError, match="does not contain a stock code"):
        probe.inspect_membership_export(
            rows=[{"종목명": "삼성전자"}],
            metadata={},
            query_date="20220902",
            benchmark_identity="KRX:KOSPI:SECTOR:26",
            source_label="KRX_DATA_MARKETPLACE_EXPORT",
        )


def test_csv_export_can_be_inspected_without_network(tmp_path: Path):
    probe = _load_probe()
    path = tmp_path / "membership.csv"
    path.write_text(
        "종목코드,종목명,종가\n005930,삼성전자,60000\n000660,SK하이닉스,90000\n",
        encoding="utf-8-sig",
    )

    rows, metadata = probe.load_membership_export(path)
    result = probe.inspect_membership_export(
        rows=rows,
        metadata=metadata,
        query_date="20220902",
        benchmark_identity="KRX:KOSPI:SECTOR:26",
        source_label="KRX_MANUAL_CSV_EXPORT",
    )

    assert result["row_count"] == 2
    assert result["network_access"] is False
    assert result["known_at_proven"] is False
