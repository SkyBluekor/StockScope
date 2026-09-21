from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "src" / "components" / "RecommendationTracking.tsx"
API = ROOT / "src" / "services" / "trackingApi.ts"


def test_tracking_ui_supports_combined_scanner_manual_source():
    text = COMPONENT.read_text(encoding="utf-8")
    assert 'return "추천 · 직접"' in text
    assert "hasScannerSource(row)" in text
    assert "hasManualSource(row)" in text
    assert "rows.filter(hasScannerSource).length" in text
    assert "rows.filter(hasManualSource).length" in text
    assert "sourceDetailLabel(row)" in text


def test_tracking_ui_uses_scanner_snapshot_for_merged_manual_origin():
    text = COMPONENT.read_text(encoding="utf-8")
    assert "row.scanner_snapshot" in text
    assert "Object.keys(row.scanner_snapshot ?? {}).length" in text


def test_tracking_api_contract_exposes_source_flags_and_scanner_snapshot():
    text = API.read_text(encoding="utf-8")
    assert "has_scanner_source: boolean" in text
    assert "has_manual_source: boolean" in text
    assert "scanner_snapshot: Record<string, unknown>" in text
    assert "sources: string[]" in text
