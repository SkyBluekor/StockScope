# UX.1.3 — Scanner Candidate Finder Action-First

Scope: main `frontend/src/components/ScannerPanel.tsx` only, plus a scoped CSS override in `frontend/src/styles.css`.

Changes:
- flatten the decorative Scanner hero
- remove the 3-step workflow rail
- remove the explanation-only strategy card
- simplify title, intro, market selection heading and primary CTA
- keep a single compact exclusion note
- preserve Scanner job/progress/result/session behavior

Safety:
- preflight requires the current UX.1.1 markers
- removal candidates are rejected if they contain buttons or handlers
- button count and Scanner behavior-anchor counts must be unchanged
- internal dry-run is always performed before writes
- build failure rolls back ScannerPanel, styles and any copy-only test assertions
- Scanner production baseline is report-only because this patch is frontend-only

Run from the StockScope project root:

```powershell
python .\apply_ux1_3_scanner_action_first.py --dry-run
python .\apply_ux1_3_scanner_action_first.py
```
