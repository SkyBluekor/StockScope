from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
scanner = (ROOT / "src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
guide = (ROOT / "src/components/EntryRiskGuideCard.tsx").read_text(encoding="utf-8")
api = (ROOT / "src/services/api.ts").read_text(encoding="utf-8")
styles = (ROOT / "src/styles.css").read_text(encoding="utf-8")

assert "1차 목표 · {targetBasisLabel(candidate)}" in scanner
assert "현재가 대비 ${formatSignedPct(targetGainPct(candidate))}" in scanner
assert "target1_audit?.available" in scanner
assert "20거래일 내 Target1 도달" in scanner
assert "1차 목표 · {targetBasisText(guide)}" in guide
assert 'formula_status === "MISMATCH"' in guide
assert "target1_basis?: string | null" in api
assert "policy_comparison?: Array" in api
assert ".scanner-target1-audit" in styles
print("target1Audit_v0214b232b: PASS")
