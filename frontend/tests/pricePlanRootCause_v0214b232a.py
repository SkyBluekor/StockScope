from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
scanner = (ROOT / "src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
guide = (ROOT / "src/components/EntryRiskGuideCard.tsx").read_text(encoding="utf-8")
api = (ROOT / "src/services/api.ts").read_text(encoding="utf-8")
styles = (ROOT / "src/styles.css").read_text(encoding="utf-8")

assert 'if (rule.user_label) return rule.user_label' in scanner
assert 'return "전략 조건 가격대"' in scanner
assert "손절 참고구간" in scanner
assert "가격 기준 구분" in scanner
assert "STRATEGY_CONDITION_BAND_OVERLAP" in scanner
assert "user_label" in guide
assert "semantic_note" in guide
assert "STRATEGY_CONDITION_BAND" in api
assert "semantic_overlap?: boolean" in api
assert "root_cause_summary?: string | null" in api
assert "trace_context?:" in api
assert "STOCK SCANNER · v0.21.4-B.2.3.2" in scanner  # accepts .2a/.2b follow-ups
assert 'aria-label="핵심 가격 기준"' in scanner
assert '<span>가격 기준</span>' in guide
assert ".scanner-price-consistency.context" in styles

# Do not reintroduce the ambiguous compact label that made a condition band look like an entry range.
assert '<small>관심 가격</small>' not in scanner
assert '<small>진입 참고</small>' not in guide
assert '관심 가격' not in scanner
assert '관심 구간' not in (ROOT / 'src/components/entryPricePosition.ts').read_text(encoding='utf-8')

print("pricePlanRootCause_v0214b232a: PASS")
