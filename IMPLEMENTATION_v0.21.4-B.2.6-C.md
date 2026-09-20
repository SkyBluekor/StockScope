# Implementation — v0.21.4-B.2.6-C

Added research-only current-version validator:

- `candidate_quality_validation.py`
- `run_scanner_candidate_quality_validation.py`
- fixed 20-date input file
- focused tests

The validator reconstructs the current Production quick/deep candidate path from local Market Store using current `StockScannerService` internals and current `rank_candidates()`. It refuses any Scanner version other than `0.21.3.7`.

Future rows are loaded only after current Production candidates and current-time overextension features are fixed. Outcome fields are never read by the guard ranking function.

No Production file is modified.
