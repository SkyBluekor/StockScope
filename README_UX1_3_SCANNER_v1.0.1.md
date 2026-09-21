# UX.1.3 — Scanner Candidate Finder Action-First v1.0.1

## Why this hotfix exists
v1.0 removed only the inner `scanner-empty-start` section from a conditional React expression and left the surrounding `{condition && (...)}` wrapper dangling. TypeScript then failed with `TS1109` at the closing `)}`.

v1.0.1 is based on the exact current `ScannerPanel.tsx` supplied after rollback.

## Changes
- Replace the exact full Scanner header block; remove the decorative 1→2→3 workflow rail.
- Simplify the market copy and primary CTA.
- Replace the **entire** pre-result conditional expression with a compact `후보 결과 / 아직 후보가 없습니다.` state, so no conditional wrapper is left dangling.
- Rename the result section eyebrow from `오늘 먼저 볼 후보` to `후보 결과`.
- Keep Scanner job/progress/result/session behavior unchanged.

## New safety gate
Before touching project source, the apply script sends the planned patched TSX through the installed TypeScript parser (`transpileModule`). A syntax error therefore fails **before write**.

## Apply
From the StockScope project root:

```powershell
python .\apply_ux1_3_scanner_action_first.py --dry-run
```

Only if that passes:

```powershell
python .\apply_ux1_3_scanner_action_first.py
```

The real apply then runs the existing Scanner source regressions when present and the frontend production build. On failure it restores the files modified by this patch.
