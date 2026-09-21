# UX.1.3 Scanner Candidate Finder Action-First v1.0.4

Hotfix scope: pre-write TSX safety checker only.

- Keeps the exact ScannerPanel transformation from v1.0.3.
- Normalizes TypeScript CommonJS/default export shapes.
- Removes enum-valued compiler options from the syntax-only check.
- Treats compiler-API incompatibility as a non-fatal SKIP; the authoritative frontend production build still runs after write.
- Actual TSX syntax diagnostics remain fatal before write when the compiler API is available.
- Existing rollback still restores only UX.1.3-touched files if tests/build fail.

Run from the StockScope project root:

```powershell
python .\apply_ux1_3_scanner_action_first.py
```
