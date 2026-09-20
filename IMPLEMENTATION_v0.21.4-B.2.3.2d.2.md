# IMPLEMENTATION v0.21.4-B.2.3.2d.2

## Backend
`backend/app/backtest/entry_risk_guide.py`
- Keeps direct RiskPlan metadata as the primary source.
- After building `target1_audit`, backfills missing explainability metadata only when the audit says `MATCH`.
- Does not modify any decision price or R ratio.

## Frontend
`ScannerPanel.tsx` and `EntryRiskGuideCard.tsx`
- Direct cap/structural metadata remains primary.
- `target1_audit` is used as a compatibility fallback when a restored/partial payload lacks the direct fields.
- Cap and 1.5R fallback remain distinct; no inference from RR alone.

## Expected Hanmi Science UI
- Target1: 52,200 / 1.50R
- `1.5R 현실성 상한 적용`
- `구조 목표 61,000원 · 최근 저항 후보`
- Target2: 62,200
