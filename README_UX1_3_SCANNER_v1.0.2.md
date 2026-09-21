# UX.1.3 Scanner Candidate Finder — v1.0.2 UTF-8 stdin hotfix

## Fix
- The v1.0.1 pre-write TypeScript syntax check used Python subprocess text mode.
- On Korean Windows this used the active cp949 console encoding and crashed before Node received ScannerPanel.tsx because the source contains Unicode glyphs such as `›` (U+203A).
- v1.0.2 sends the planned TSX to Node as explicit UTF-8 bytes and decodes diagnostics as UTF-8 with replacement fallback.

## Scope
No Scanner JSX/CSS behavior change was added beyond the already planned UX.1.3 patch. The hotfix only makes the syntax-check transport locale-independent.

## Verified here
- Python py_compile: PASS
- Current uploaded ScannerPanel exact preflight: PASS
- UX.1.3 patch transform: PASS
- Patched source still contains U+203A and was sent to Node through the new UTF-8 byte path: PASS
- TypeScript `transpileModule` syntax check: PASS

## Run
```powershell
python .\apply_ux1_3_scanner_action_first.py --dry-run
python .\apply_ux1_3_scanner_action_first.py
```
