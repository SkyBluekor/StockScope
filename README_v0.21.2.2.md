# StockScope v0.21.2.2 — Action Plan Readability & Information Hierarchy

## Purpose
Reorganizes the Quick Analysis Action Plan so a beginner can identify the current action, the top reasons, and the conditions that change the decision before seeing secondary scores and expert details.

## Scope
- Frontend only.
- No Strategy/Risk/Entry Timing/Historical Evidence calculation changes.
- No API schema changes.
- Keeps the existing v0.21.2 historical evidence and v0.21.2.1 dark UI fixes.

## Main UI changes
1. Current decision is the primary hero content.
2. Top 3 decision factors are compact rows instead of three large cards.
3. Decision-change scenarios use a Condition → Decision Change layout.
4. Important price levels remain visible without requiring manual calculation.
5. Company/style/strategy-score/timing explanations move into a collapsed Supporting Analysis section.
6. Other signals and evidence remain collapsed by default.
7. Expert navigation shows compact one-line tabs and moves overflow items into More.
8. Verdict state colors are accents/borders, not full-card color washes.

## Files changed
- `frontend/src/components/AnalysisHub.tsx`
- `frontend/src/styles.css`

## Verification performed
- TypeScript/TSX syntactic transpile check: PASS
- PostCSS parse: PASS
- CSS brace balance: PASS
- ZIP integrity: PASS

A full Vite production build was not run in the overlay-only environment.
