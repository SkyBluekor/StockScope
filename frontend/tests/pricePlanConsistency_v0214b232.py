from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
scanner = (ROOT / "src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
guide = (ROOT / "src/components/EntryRiskGuideCard.tsx").read_text(encoding="utf-8")
api = (ROOT / "src/services/api.ts").read_text(encoding="utf-8")
styles = (ROOT / "src/styles.css").read_text(encoding="utf-8")

assert "price_consistency?: ConcretePricePlanConsistency" in api
assert "display_stop_zone_low?: number | null" in api
assert "display_stop_zone_high?: number | null" in api

# Scanner rows and detail must use the real stop zone, not invalidation, for '손절 참고'.
assert "risk.display_stop_zone_low ?? risk.stop_zone_low" in scanner
assert "risk.display_stop_zone_high ?? risk.stop_zone_high" in scanner
assert "전략 무효화 기준" in scanner
assert "손절 참고구간과 별개의 전략 전제 기준" in scanner
assert "price_consistency.status" in scanner

assert "function stopZoneText" in guide
assert "<small>손절 참고구간</small>" in guide
assert "<small>전략 무효화 기준</small>" in guide
assert "손절 참고구간과 같은 개념이 아닙니다" in guide
assert "consistencyNotice(guide)" in guide

# B.2.3.2 styling stays scoped; no global row/card selector is introduced here.
assert "v0.21.4-B.2.3.2" in styles
assert ".scanner-price-consistency" in styles
assert ".scanner-price-invalidation" in styles

print("pricePlanConsistency_v0214b232: PASS")

# B.2.3.2a keeps the existing stop/invalidation split while clarifying strategy-condition prices.
assert "STRATEGY_CONDITION_BAND_OVERLAP" in api
assert "semantic_role?" in api
assert "strategyPriceLabel" in scanner
assert "전략 조건 가격대" in scanner
assert "손절 참고구간" in scanner
assert "가격 기준 구분" in scanner
assert "semantic_note" in guide
assert ".scanner-price-consistency.context" in styles
