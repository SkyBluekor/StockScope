from __future__ import annotations

from pathlib import Path

from app.backtest.entry_risk_guide import _hydrate_target1_explainability_metadata


def test_matching_audit_backfills_missing_cap_metadata_without_touching_prices():
    risk = {
        "entry_reference_price": 48_500.0,
        "target1_price": 52_212.44,
        "target1_basis": "1.5R 현실성 상한",
        "target2_price": 62_237.48,
        "rr1": 1.5,
        "rr2": 5.55,
        "structural_target1_price": None,
        "structural_target1_basis": None,
        "target1_cap_price": None,
        "target1_cap_applied": False,
        "target1_fallback_used": False,
    }
    audit = {
        "formula_status": "MATCH",
        "target1_cap_applied": True,
        "target1_fallback_used": False,
        "target1_cap_price": 52_212.44,
        "structural_target1_price": 61_000.0,
        "structural_target1_basis": "최근 저항 후보",
    }

    before_decision = {key: risk[key] for key in ("entry_reference_price", "target1_price", "target2_price", "rr1", "rr2")}
    out = _hydrate_target1_explainability_metadata(risk, audit)

    assert out is risk
    assert {key: out[key] for key in before_decision} == before_decision
    assert out["target1_cap_applied"] is True
    assert out["target1_fallback_used"] is False
    assert out["target1_cap_price"] == 52_212.44
    assert out["structural_target1_price"] == 61_000.0
    assert out["display_structural_target1_price"] == 61_000.0
    assert out["structural_target1_basis"] == "최근 저항 후보"


def test_mismatch_audit_never_overrides_direct_payload():
    risk = {
        "target1_price": 52_212.44,
        "target1_cap_applied": False,
        "structural_target1_price": None,
    }
    audit = {
        "formula_status": "MISMATCH",
        "target1_cap_applied": True,
        "structural_target1_price": 61_000.0,
        "structural_target1_basis": "최근 저항 후보",
    }

    out = _hydrate_target1_explainability_metadata(risk, audit)
    assert out["target1_cap_applied"] is False
    assert out["structural_target1_price"] is None


def test_fallback_is_not_reclassified_as_cap():
    risk = {
        "target1_cap_applied": False,
        "target1_fallback_used": False,
        "structural_target1_price": None,
    }
    audit = {
        "formula_status": "MATCH",
        "target1_cap_applied": False,
        "target1_fallback_used": True,
        "structural_target1_price": None,
        "structural_target1_basis": None,
        "target1_cap_price": 52_212.44,
    }

    out = _hydrate_target1_explainability_metadata(risk, audit)
    assert out["target1_cap_applied"] is False
    assert out["target1_fallback_used"] is True
    assert out["structural_target1_price"] is None


def test_frontend_uses_audit_metadata_as_compatibility_fallback():
    repo_root = Path(__file__).resolve().parents[2]
    scanner = (repo_root / "frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    guide = (repo_root / "frontend/src/components/EntryRiskGuideCard.tsx").read_text(encoding="utf-8")

    assert "audit?.target1_cap_applied === true" in scanner
    assert "audit?.structural_target1_price" in scanner
    assert "audit?.structural_target1_basis" in scanner
    assert "1.5R 현실성 상한 적용" in scanner

    assert "audit?.target1_cap_applied === true" in guide
    assert "audit?.structural_target1_price" in guide
    assert "audit?.structural_target1_basis" in guide
    assert "1.5R 현실성 상한 적용" in guide


def test_scanner_decision_version_stays_02136():
    repo_root = Path(__file__).resolve().parents[2]
    scanner_path = repo_root / "backend/app/backtest/scanner.py"
    if scanner_path.exists():
        scanner = scanner_path.read_text(encoding="utf-8")
        assert 'VERSION = "0.21.3.6"' in scanner
