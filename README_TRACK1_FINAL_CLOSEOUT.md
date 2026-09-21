# TRACK.1 FINAL — Closeout & Freeze

This overlay closes the Stock Tracking phase without adding new product features.

## What it adds

- `docs/TRACKING_BASELINE.md`
  - records the frozen TRACK.1 behavior and change policy.
- `backend/tools/verify_tracking_baseline.py`
  - read-only runtime verifier for the tracking SQLite database.
  - checks schema v4, source flags, same-baseline duplicate removal, snapshot integrity, CLOSED freeze state, and orphan performance rows.

## What it does not change

- Scanner algorithms
- Tracking service/store/model behavior
- Tracking UI
- Market Store
- Historical Validation
- Legacy Simulation

The apply script runs the existing TRACK regression set and frontend production build. It does not add a new regression test merely for closeout.
