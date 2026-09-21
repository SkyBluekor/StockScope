# UX.1.1 v1.0.1 — Project Python Auto-Detection Hotfix

## Fix
The apply script no longer assumes that the shell has activated `.venv`.

It now checks, in order:
1. `.venv/Scripts/python.exe`
2. `.venv/bin/python`
3. `venv/Scripts/python.exe`
4. `venv/bin/python`
5. the launcher Python

The first interpreter that can import `pytest` is used for focused regression tests and baseline verifiers.

If no usable Python is found, the script exits during preflight **before modifying source files**.

## Apply
From the StockScope repository root:

```powershell
python .\apply_ux1_1_intuitive_labels.py
```

No manual virtualenv activation is required when the project `.venv` is present and contains pytest.
