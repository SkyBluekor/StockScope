from pathlib import Path

from app.simulation.validation_catalog import HistoricalValidationCatalog, PRODUCTION_SCANNER_VERSION


def test_validation_draft_create_list_get_delete(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = catalog.create_draft(
        name="전체시장 Scanner · 최근 1년",
        market_scope="ALL",
        requested_period_type="1y",
        requested_start_month="2025-10",
        requested_end_month="2026-09",
        resolved_start_date="2025-10-01",
        resolved_end_date="2026-09-18",
        trading_day_count=248,
    )
    assert draft.status == "DRAFT"
    assert draft.scanner_version == PRODUCTION_SCANNER_VERSION
    assert catalog.get(draft.id) == draft
    assert [item.id for item in catalog.list()] == [draft.id]
    assert catalog.delete(draft.id) is True
    assert catalog.get(draft.id) is None


def test_validation_name_is_required(tmp_path: Path):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    try:
        catalog.create_draft(
            name="  ", market_scope="ALL", requested_period_type="1y",
            requested_start_month="2025-10", requested_end_month="2026-09",
            resolved_start_date="2025-10-01", resolved_end_date="2026-09-18", trading_day_count=248,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "SIM_VALIDATION_NAME_REQUIRED"
    else:
        raise AssertionError("blank validation name must be rejected")
