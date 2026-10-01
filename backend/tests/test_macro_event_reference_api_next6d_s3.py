from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.macro as macro_api
from app.event_evidence import EventEvidenceContractError
from app.main import app


client = TestClient(app)
CUTOFF = "2026-09-30T11:00:00+00:00"
CONTEXT_HASH = "a" * 64


def _context(
    *,
    status: str = "COMPLETE_REFERENCE",
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": "VN_NEXT6B_S1_MACRO_CONTEXT_V2",
        "context_id": "MACROCTX-1234567890abcdef",
        "context_hash": CONTEXT_HASH,
        "decision_cutoff": CUTOFF,
        "usage_mode": "REFERENCE_SHADOW",
        "status": status,
        "reason": reason,
        "availability": {
            "reader_reason": reason,
        },
        "limitations": [],
    }


def _event_item(
    *,
    event_type: str = "EARNINGS",
    available_at: str = "2026-09-30T08:00:00+00:00",
    evidence_as_of: str = "2026-09-30T08:05:00+00:00",
    assessment_as_of: str = "2026-09-30T08:10:00+00:00",
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "relation_type": "DIRECT_COMPANY",
        "relevance_state": "CONFIRMED",
        "quality_state": "USABLE",
        "source_kinds": ["OPENDART_DISCLOSURE"],
        "available_at": available_at,
        "evidence_as_of": evidence_as_of,
        "revision_state": "ORIGINAL",
        "assessment_as_of": assessment_as_of,
    }


def _event_product(
    *,
    event_status: str = "REFERENCE_AVAILABLE",
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = [_event_item()] if items is None else items
    return {
        "contract_version": "VN_NEXT6D_S2_EVENT_REFERENCE_AS_OF_V1",
        "projection_id": "EVASOF-test",
        "projection_hash": "b" * 64,
        "status": "AVAILABLE" if rows else "PARTIAL",
        "code": "005930",
        "market": "KOSPI",
        "decision_cutoff": CUTOFF,
        "temporal_projection": {
            "mode": "SYSTEM_OBSERVED_AS_OF",
            "decision_cutoff": CUTOFF,
            "storage_observation_cutoff_enforced": True,
            "historical_source_completeness_proven": False,
            "historical_evaluation_approved": False,
        },
        "event_evidence": {
            "status": event_status,
            "reference_count": len(rows),
            "projected_reference_count": len(rows),
            "latest_as_of": (
                max(str(row["assessment_as_of"]) for row in rows)
                if rows
                else None
            ),
            "items": rows,
            "diagnostics": {},
        },
        "value_validation": {
            "status": "NOT_PROJECTED_AS_OF",
            "product_scope": "RESEARCH_ONLY",
        },
        "prediction": {
            "status": "NOT_VALIDATED",
            "direction": None,
            "horizon_sessions": None,
            "probability": None,
        },
        "governance": {
            "claim_scope": "REFERENCE_CONTEXT_AS_OF_ONLY",
            "historical_evaluation_approved": False,
            "prediction_approved": False,
            "strategy_input_approved": False,
            "scanner_input_approved": False,
            "risk_gate_input_approved": False,
            "holdings_plan_input_approved": False,
            "production_decision_approved": False,
            "network_access": False,
            "database_write": False,
        },
    }


class _MarketReader:
    payload: dict[str, Any] = {
        "status": "AVAILABLE",
        "reason": None,
        "stock_rows": [
            {"date": "20260929", "close": "100"},
            {"date": "20260930", "close": "103"},
        ],
        "market_rows": [
            {"date": "20260929", "close": "200"},
            {"date": "20260930", "close": "202"},
        ],
    }
    error: ValueError | None = None

    def __init__(self, _path: Path) -> None:
        pass

    def read_pair_as_of(self, **_kwargs: Any) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return deepcopy(self.payload)


class _EventReader:
    payload: dict[str, Any] | None = _event_product()
    error: EventEvidenceContractError | None = None
    calls: list[tuple[str, str, str]] = []

    def __init__(self, _path: Path) -> None:
        pass

    def stock_reference_as_of(
        self,
        code: str,
        market: str,
        decision_cutoff: str,
        *,
        limit: int = 3,
    ) -> dict[str, Any]:
        del limit
        self.calls.append((code, market, decision_cutoff))
        if self.error is not None:
            raise self.error
        assert self.payload is not None
        return deepcopy(self.payload)


def _install_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: dict[str, Any] | None = None,
    market_payload: dict[str, Any] | None = None,
    market_error: ValueError | None = None,
    event_payload: dict[str, Any] | None = None,
    event_error: EventEvidenceContractError | None = None,
) -> None:
    selected_context = deepcopy(context or _context())
    monkeypatch.setattr(macro_api, "LocalMacroReader", lambda _path: object())
    monkeypatch.setattr(
        macro_api,
        "build_macro_context",
        lambda **_kwargs: deepcopy(selected_context),
    )

    _MarketReader.payload = deepcopy(
        market_payload
        or {
            "status": "AVAILABLE",
            "reason": None,
            "stock_rows": [
                {"date": "20260929", "close": "100"},
                {"date": "20260930", "close": "103"},
            ],
            "market_rows": [
                {"date": "20260929", "close": "200"},
                {"date": "20260930", "close": "202"},
            ],
        }
    )
    _MarketReader.error = market_error
    monkeypatch.setattr(macro_api, "LocalMarketImpactReader", _MarketReader)

    _EventReader.payload = deepcopy(
        _event_product() if event_payload is None else event_payload
    )
    _EventReader.error = event_error
    _EventReader.calls = []
    monkeypatch.setattr(macro_api, "EventEvidenceAsOfReader", _EventReader)


def _get(**overrides: str):
    params = {
        "market": "KOSPI",
        "ticker": "005930",
        "end_date": "20260930",
        "cutoff": CUTOFF,
    }
    params.update(overrides)
    return client.get("/api/macro/event-reference", params=params)


def test_macro_event_reference_api_returns_bounded_available_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(monkeypatch)

    response = _get(ticker=" 005930 ")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()

    assert (
        body["contract_version"]
        == "VN_NEXT6D_S3_MACRO_EVENT_REFERENCE_API_V1"
    )
    assert body["status"] == "AVAILABLE"
    assert body["decision_cutoff"] == CUTOFF
    assert body["scope"] == {"market": "KOSPI", "ticker": "005930"}
    assert body["composition_id"].startswith("MEVCOMP-")
    assert len(body["composition_hash"]) == 64
    assert body["macro"] == {
        "status": "COMPLETE_REFERENCE",
        "usage_mode": "REFERENCE_SHADOW",
    }
    assert body["impact"]["status"] == "AVAILABLE"
    assert body["impact"]["market_return_pct"] is not None
    assert body["impact"]["stock_return_pct"] is not None
    assert body["impact"]["stock_vs_market_pctp"] is not None
    assert body["sector"] == {
        "historical_sector_status": "BLOCKED_EXTERNAL_SOURCE",
        "historical_impact_mode": "MARKET_STOCK_ONLY",
        "prospective_sector_status": "NOT_STARTED",
    }
    assert body["event_source"] == {
        "reader_status": "AVAILABLE",
        "reason": None,
        "projection_mode": "SYSTEM_OBSERVED_AS_OF",
    }
    assert body["event_reference"]["status"] == "REFERENCE_AVAILABLE"
    assert body["event_reference"]["eligible_reference_count"] == 1
    assert body["event_reference"]["historical_completeness_proven"] is False
    assert body["value_validation"] == {
        "status": "NOT_PROJECTED_AS_OF",
        "product_scope": "RESEARCH_ONLY",
    }
    assert body["prediction"]["status"] == "NOT_VALIDATED"
    assert body["identity_policy"] == "CUTOFF_ELIGIBLE_REFERENCES_ONLY"
    assert body["production_decision_approved"] is False
    assert _EventReader.calls == [("005930", "KOSPI", CUTOFF)]


def test_event_absence_is_partial_not_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(
        monkeypatch,
        event_payload=_event_product(
            event_status="NO_OBSERVED_ENTITY_BY_CUTOFF",
            items=[],
        ),
    )

    response = _get()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PARTIAL"
    assert body["event_source"]["reader_status"] == "AVAILABLE"
    assert (
        body["event_reference"]["source_status"]
        == "NO_OBSERVED_ENTITY_BY_CUTOFF"
    )
    assert body["event_reference"]["eligible_reference_count"] == 0
    assert "EVENT_REFERENCE_NOT_AVAILABLE_AT_CUTOFF" in body["limitations"]


@pytest.mark.parametrize(
    "code",
    [
        "EVENT_EVIDENCE_STORE_NOT_FOUND",
        "EVENT_EVIDENCE_SCHEMA_NOT_READY",
    ],
)
def test_event_store_degradation_preserves_macro_impact(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    _install_stubs(
        monkeypatch,
        event_error=EventEvidenceContractError(code, "event unavailable"),
    )

    response = _get()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PARTIAL"
    assert body["impact"]["status"] == "AVAILABLE"
    assert body["event_source"]["reader_status"] == "UNAVAILABLE"
    assert body["event_source"]["reason"] == code
    assert body["event_reference"]["status"] == "EVENT_SOURCE_UNAVAILABLE"
    assert body["event_reference"]["eligible_reference_count"] == 0


def test_event_integrity_block_is_partial_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(
        monkeypatch,
        event_payload=_event_product(
            event_status="EVIDENCE_BLOCKED",
            items=[],
        ),
    )

    response = _get()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PARTIAL"
    assert body["event_reference"]["status"] == "EVIDENCE_BLOCKED"
    assert body["event_reference"]["eligible_reference_count"] == 0


def test_macro_context_infrastructure_failure_is_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(
        monkeypatch,
        context=_context(status="UNAVAILABLE", reason="STORE_NOT_FOUND"),
    )

    response = _get()

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == {
        "code": "MACRO_EVENT_CONTEXT_UNAVAILABLE",
        "reason": "STORE_NOT_FOUND",
        "message": "Macro context for Macro/Event reference is not available.",
    }


def test_market_store_infrastructure_failure_is_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(
        monkeypatch,
        market_payload={
            "status": "UNAVAILABLE",
            "reason": "STORE_NOT_FOUND",
            "stock_rows": [],
            "market_rows": [],
        },
    )

    response = _get()

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"]["code"] == (
        "MACRO_EVENT_MARKET_STORE_UNAVAILABLE"
    )


def test_insufficient_common_sessions_is_200_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(
        monkeypatch,
        market_payload={
            "status": "AVAILABLE",
            "reason": None,
            "stock_rows": [{"date": "20260930", "close": "103"}],
            "market_rows": [{"date": "20260930", "close": "202"}],
        },
    )

    response = _get()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UNAVAILABLE"
    assert body["impact"]["status"] == "UNAVAILABLE"
    assert body["impact"]["reason"] == "INSUFFICIENT_COMMON_SESSIONS"


def test_invalid_market_and_ticker_are_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(monkeypatch)

    bad_market = _get(market="NASDAQ")
    assert bad_market.status_code == 400
    assert bad_market.json()["detail"]["code"] == (
        "MACRO_EVENT_REFERENCE_INVALID_REQUEST"
    )

    bad_ticker = _get(ticker="5930")
    assert bad_ticker.status_code == 400
    assert bad_ticker.json()["detail"]["code"] == (
        "MACRO_EVENT_REFERENCE_INVALID_REQUEST"
    )


def test_invalid_end_date_is_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(
        monkeypatch,
        market_error=ValueError(
            "end_date must be YYYY-MM-DD or YYYYMMDD."
        ),
    )

    response = _get(end_date="2026/09/30")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "MACRO_EVENT_REFERENCE_INVALID_REQUEST"
    )


def test_timezone_less_cutoff_is_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(macro_api, "LocalMacroReader", lambda _path: object())

    def _invalid_cutoff(**_kwargs: Any) -> dict[str, Any]:
        raise ValueError(
            "decision_cutoff must be a timezone-aware ISO-8601 datetime."
        )

    monkeypatch.setattr(macro_api, "build_macro_context", _invalid_cutoff)

    response = _get(cutoff="2026-09-30T11:00:00")

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"]["code"] == (
        "MACRO_EVENT_REFERENCE_INVALID_REQUEST"
    )


def test_missing_required_cutoff_uses_fastapi_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(monkeypatch)

    response = client.get(
        "/api/macro/event-reference",
        params={
            "market": "KOSPI",
            "ticker": "005930",
            "end_date": "20260930",
        },
    )

    assert response.status_code == 422


def test_future_event_addition_cannot_rewrite_frozen_api_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(monkeypatch, event_payload=_event_product())
    before = _get().json()

    future = _event_item(
        event_type="FUTURE_EVENT",
        available_at="2026-10-01T01:00:00+00:00",
        evidence_as_of="2026-10-01T01:01:00+00:00",
        assessment_as_of="2026-10-01T01:02:00+00:00",
    )
    _EventReader.payload = _event_product(
        items=[_event_item(), future],
    )

    after = _get().json()

    assert after["composition_id"] == before["composition_id"]
    assert after["composition_hash"] == before["composition_hash"]
    assert after["event_reference"]["items"] == before["event_reference"]["items"]
    assert after["event_reference"]["eligible_reference_count"] == 1


def test_same_inputs_produce_same_api_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(monkeypatch)

    first = _get().json()
    second = _get().json()

    assert second["composition_id"] == first["composition_id"]
    assert second["composition_hash"] == first["composition_hash"]


def test_api_layer_does_not_modify_configured_runtime_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    market_db = tmp_path / "market_history.db"
    simulation_db = tmp_path / "simulation.db"
    for path in (macro_db, market_db, simulation_db):
        path.write_bytes(b"read-only-fixture")

    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(simulation_db))
    _install_stubs(monkeypatch)

    before = {
        path: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in (macro_db, market_db, simulation_db)
    }
    response = _get()
    after = {
        path: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in (macro_db, market_db, simulation_db)
    }

    assert response.status_code == 200
    assert after == before


def test_event_store_failure_never_creates_missing_simulation_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing" / "simulation.db"
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(missing))
    _install_stubs(
        monkeypatch,
        event_error=EventEvidenceContractError(
            "EVENT_EVIDENCE_STORE_NOT_FOUND",
            "Simulation DB not found.",
        ),
    )

    response = _get()

    assert response.status_code == 200
    assert response.json()["status"] == "PARTIAL"
    assert not missing.exists()


def test_reference_governance_remains_non_decision_support_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stubs(monkeypatch)

    body = _get().json()

    assert body["prediction"] == {
        "status": "NOT_VALIDATED",
        "direction": None,
        "horizon_sessions": None,
        "probability": None,
    }
    assert body["event_reference"]["historical_completeness_proven"] is False
    assert body["governance"] == {
        "claim_scope": "REFERENCE_COMPOSITION_ONLY",
        "causal_attribution": False,
        "macro_exposure_relation_created": False,
        "prediction_approved": False,
        "strategy_input_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "holdings_plan_input_approved": False,
        "production_decision_approved": False,
        "network_access": False,
        "database_write": False,
    }
