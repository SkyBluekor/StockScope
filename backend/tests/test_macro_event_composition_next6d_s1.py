from __future__ import annotations

from copy import deepcopy

import pytest

from app.macro import (
    MACRO_EVENT_REFERENCE_COMPOSITION_CONTRACT_VERSION,
    build_macro_event_reference_composition,
    build_market_stock_impact,
    build_sector_route,
)


CUTOFF = "2026-09-30T11:00:00+00:00"
CONTEXT_ID = "MACROCTX-1234567890abcdef"
CONTEXT_HASH = "a" * 64


def _macro_context(
    *,
    status: str = "COMPLETE_REFERENCE",
    cutoff: str = CUTOFF,
) -> dict[str, object]:
    return {
        "contract_version": "VN_NEXT6B_S1_MACRO_CONTEXT_V2",
        "context_id": CONTEXT_ID,
        "context_hash": CONTEXT_HASH,
        "decision_cutoff": cutoff,
        "usage_mode": "REFERENCE_SHADOW",
        "status": status,
    }


def _impact(
    *,
    context_id: str = CONTEXT_ID,
    context_hash: str = CONTEXT_HASH,
    cutoff: str = CUTOFF,
    ticker: str = "005930",
    market: str = "KOSPI",
) -> dict[str, object]:
    return build_market_stock_impact(
        stock_rows=[
            {"date": "20260929", "close": "100"},
            {"date": "20260930", "close": "103"},
        ],
        market_rows=[
            {"date": "20260929", "close": "200"},
            {"date": "20260930", "close": "202"},
        ],
        market=market,
        ticker=ticker,
        end_date="20260930",
        macro_context_id=context_id,
        macro_context_hash=context_hash,
        decision_cutoff=cutoff,
    )


def _event_item(
    *,
    event_type: str = "EARNINGS",
    relation_type: str = "DIRECT_COMPANY",
    quality_state: str = "USABLE",
    revision_state: str = "ORIGINAL",
    source_kinds: list[str] | None = None,
    available_at: str = "2026-09-30T08:00:00+00:00",
    evidence_as_of: str = "2026-09-30T08:05:00+00:00",
    assessment_as_of: str = "2026-09-30T08:10:00+00:00",
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "relation_type": relation_type,
        "relevance_state": "CONFIRMED",
        "quality_state": quality_state,
        "source_kinds": source_kinds or ["OPENDART_DISCLOSURE"],
        "available_at": available_at,
        "evidence_as_of": evidence_as_of,
        "revision_state": revision_state,
        "assessment_as_of": assessment_as_of,
    }


def _event_product(
    *,
    code: str = "005930",
    market: str = "KOSPI",
    items: list[dict[str, object]] | None = None,
    source_status: str = "REFERENCE_AVAILABLE",
    product_scope: str = "REFERENCE_CONTEXT",
    prediction_status: str = "NOT_VALIDATED",
) -> dict[str, object]:
    rows = items if items is not None else [_event_item()]
    return {
        "contract_version": "VN_P6_S1_EVENT_EVIDENCE_PRODUCT_V1",
        "code": code,
        "market": market,
        "recent_news": {
            "mode": "DISPLAY_ONLY",
            "decision_input": False,
        },
        "event_evidence": {
            "status": source_status,
            "reference_count": len(rows),
            "latest_as_of": (
                max(str(row["assessment_as_of"]) for row in rows)
                if rows
                else None
            ),
            "items": rows,
        },
        "value_validation": {
            "status": "NOT_EVALUATED",
            "product_scope": product_scope,
        },
        "prediction": {
            "status": prediction_status,
            "direction": None,
            "horizon_sessions": None,
            "probability": None,
        },
    }


def _compose(
    *,
    macro_context: dict[str, object] | None = None,
    impact: dict[str, object] | None = None,
    event_product: dict[str, object] | None = None,
):
    return build_macro_event_reference_composition(
        macro_context=macro_context or _macro_context(),
        impact=impact or _impact(),
        sector_route=build_sector_route(),
        event_product=(
            _event_product() if event_product is None else event_product
        ),
    )


def test_composition_binds_macro_impact_and_event_reference_identities():
    result = _compose()

    assert (
        result["contract_version"]
        == MACRO_EVENT_REFERENCE_COMPOSITION_CONTRACT_VERSION
    )
    assert result["composition_id"].startswith("MEVCOMP-")
    assert len(result["composition_hash"]) == 64
    assert result["status"] == "AVAILABLE"
    assert result["scope"] == {
        "market": "KOSPI",
        "ticker": "005930",
    }

    assert result["macro"]["context_id"] == CONTEXT_ID
    assert result["macro"]["context_hash"] == CONTEXT_HASH
    assert result["impact"]["impact_id"].startswith("MSIMPACT-")
    assert result["impact"]["market_return_pct"] is not None
    assert result["impact"]["stock_return_pct"] is not None
    assert result["impact"]["stock_vs_market_pctp"] is not None

    event = result["event_reference"]
    assert event["eligible_reference_count"] == 1
    assert event["items"][0]["quality_state"] == "USABLE"
    assert event["items"][0]["relation_type"] == "DIRECT_COMPANY"
    assert event["historical_completeness_proven"] is False

    assert (
        result["sector"]["historical_sector_status"]
        == "BLOCKED_EXTERNAL_SOURCE"
    )
    assert result["prediction"]["status"] == "NOT_VALIDATED"
    assert result["identity_policy"] == "CUTOFF_ELIGIBLE_REFERENCES_ONLY"


def test_macro_and_impact_identity_mismatch_fails_closed():
    with pytest.raises(ValueError, match="macro_context_id"):
        _compose(
            impact=_impact(
                context_id="MACROCTX-fedcba0987654321",
            )
        )

    with pytest.raises(ValueError, match="macro_context_hash"):
        _compose(
            impact=_impact(
                context_hash="b" * 64,
            )
        )

    with pytest.raises(ValueError, match="decision_cutoff"):
        _compose(
            impact=_impact(
                cutoff="2026-09-30T10:00:00+00:00",
            )
        )


def test_event_scope_mismatch_fails_closed():
    with pytest.raises(ValueError, match="market/code"):
        _compose(
            event_product=_event_product(code="000660"),
        )

    with pytest.raises(ValueError, match="market/code"):
        _compose(
            event_product=_event_product(market="KOSDAQ"),
        )


def test_future_event_reference_is_excluded_at_cutoff():
    product = _event_product(
        items=[
            _event_item(),
            _event_item(
                event_type="LARGE_CONTRACT",
                available_at="2026-10-01T01:00:00+00:00",
                evidence_as_of="2026-10-01T01:01:00+00:00",
                assessment_as_of="2026-10-01T01:02:00+00:00",
            ),
        ]
    )

    result = _compose(event_product=product)
    event = result["event_reference"]

    assert event["source_reference_count"] == 2
    assert event["eligible_reference_count"] == 1
    assert event["excluded_after_cutoff_count"] == 1
    assert [row["event_type"] for row in event["items"]] == ["EARNINGS"]


def test_future_event_addition_cannot_rewrite_past_composition_identity():
    before = _compose(
        event_product=_event_product(items=[_event_item()])
    )

    after = _compose(
        event_product=_event_product(
            items=[
                _event_item(),
                _event_item(
                    event_type="FUTURE_EVENT",
                    available_at="2026-10-01T01:00:00+00:00",
                    evidence_as_of="2026-10-01T01:01:00+00:00",
                    assessment_as_of="2026-10-01T01:02:00+00:00",
                ),
            ]
        )
    )

    assert after["composition_id"] == before["composition_id"]
    assert after["composition_hash"] == before["composition_hash"]
    assert after["event_reference"]["items"] == before["event_reference"]["items"]
    assert after["event_reference"]["eligible_reference_count"] == 1
    assert after["event_reference"]["excluded_after_cutoff_count"] == 1


def test_withdrawn_superseded_and_synthetic_references_are_not_active():
    product = _event_product(
        items=[
            _event_item(revision_state="WITHDRAWN"),
            _event_item(
                event_type="SUPERSEDED_EVENT",
                revision_state="SUPERSEDED",
            ),
            _event_item(
                event_type="SYNTHETIC_EVENT",
                source_kinds=["TEST_SYNTHETIC"],
            ),
            _event_item(
                event_type="LIMITED_EVENT",
                quality_state="LIMITED",
                revision_state="CORRECTED",
                source_kinds=["OPENDART_DISCLOSURE"],
            ),
        ]
    )

    result = _compose(event_product=product)
    event = result["event_reference"]

    assert event["eligible_reference_count"] == 1
    assert event["excluded_revision_count"] == 2
    assert event["excluded_synthetic_count"] == 1
    assert event["status"] == "REFERENCE_LIMITED"
    assert event["items"][0]["event_type"] == "LIMITED_EVENT"
    assert event["items"][0]["revision_state"] == "CORRECTED"
    assert event["items"][0]["quality_state"] == "LIMITED"


def test_missing_event_source_keeps_macro_and_impact_as_partial_reference():
    result = build_macro_event_reference_composition(
        macro_context=_macro_context(),
        impact=_impact(),
        sector_route=build_sector_route(),
        event_product=None,
    )

    assert result["status"] == "PARTIAL"
    assert result["event_reference"]["status"] == "EVENT_SOURCE_UNAVAILABLE"
    assert result["event_reference"]["eligible_reference_count"] == 0
    assert "EVENT_REFERENCE_NOT_AVAILABLE_AT_CUTOFF" in result["limitations"]
    assert result["macro"]["context_id"] == CONTEXT_ID
    assert result["impact"]["status"] == "AVAILABLE"


def test_macro_or_impact_unavailable_marks_composition_unavailable():
    macro_partial = _macro_context(status="UNAVAILABLE")
    result = _compose(macro_context=macro_partial)
    assert result["status"] == "UNAVAILABLE"

    unavailable_impact = deepcopy(_impact())
    unavailable_impact["status"] = "UNAVAILABLE"
    result = _compose(impact=unavailable_impact)
    assert result["status"] == "UNAVAILABLE"


def test_prediction_and_product_scope_cannot_be_promoted():
    with pytest.raises(ValueError, match="prediction"):
        _compose(
            event_product=_event_product(
                prediction_status="VALIDATED",
            )
        )

    with pytest.raises(ValueError, match="product_scope"):
        _compose(
            event_product=_event_product(
                product_scope="PRODUCTION_DECISION",
            )
        )


def test_composition_does_not_create_macro_exposure_or_decision_inputs():
    product = _event_product(
        items=[
            _event_item(
                relation_type="MACRO_EXPOSURE",
                event_type="EXISTING_VALIDATED_RELATION",
            )
        ]
    )
    result = _compose(event_product=product)

    # An existing P6 relation can be preserved as a bounded reference, but this
    # composer never creates or infers one from MacroContext itself.
    assert (
        result["event_reference"]["items"][0]["relation_type"]
        == "MACRO_EXPOSURE"
    )
    assert result["governance"] == {
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
    assert "NO_CAUSAL_ATTRIBUTION" in result["limitations"]
    assert "NO_MACRO_EXPOSURE_RELATION_CREATED" in result["limitations"]


def test_same_inputs_produce_same_composition_identity():
    first = _compose()
    second = _compose()

    assert first["composition_id"] == second["composition_id"]
    assert first["composition_hash"] == second["composition_hash"]
