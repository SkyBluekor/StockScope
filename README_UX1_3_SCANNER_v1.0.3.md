# StockScope UX.1.3 Scanner Candidate Finder — v1.0.3

This is a narrow safety-check hotfix for the UX.1.3 apply script.

## Fix

- Keeps the v1.0.2 UTF-8 stdin fix for Korean Windows / cp949 terminals.
- Removes the hard-coded `./frontend/node_modules/typescript` require path.
- Resolves `typescript` with Node's normal package resolver from the actual `frontend` workspace, with the project root as a fallback search path.
- This supports normal npm layouts as well as hoisted/junction-based dependency layouts.
- No Scanner UI transform or behavior logic changed from v1.0.2.

## Run

```powershell
python .\apply_ux1_3_scanner_action_first.py --dry-run
python .\apply_ux1_3_scanner_action_first.py
```

The dry run does not write project files.
