# Implementation — v0.21.4-B.2.7-E

Added research-only tooling:
- `entry_stability_volume_holdout.py`
- `run_scanner_entry_stability_volume_holdout.py`
- focused tests
- static exclusion manifest containing the 93 previously inspected dates

The runner requires the latest B.2.7-D JSON with `FREEZE_VOLUME_LOW_GUARD`, Scanner `0.21.3.7`, and `production_changed=false`.

On first execution it selects and writes a frozen holdout file under the runtime output directory. Later executions validate and reuse those dates rather than silently replacing them.

The rule fingerprint is locked to:
`bcb71bbb21fa3e16c91f973ea0f91cd81130c169f5dcd45cb6c2dcbc25390b56`

Focused tests cover fingerprint lock, Q25 semantics, non-READY immutability, outcome-independent ranking hash, deterministic fresh selection, spacing, future-session availability, verdict gates, and D-source validation.
