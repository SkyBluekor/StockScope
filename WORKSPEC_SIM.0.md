# StockScope SIM.0 — Production Baseline Freeze

Purpose: freeze Scanner `0.21.3.7` as the reproducible Simulation baseline without changing Production behavior.

The baseline is built from a recursive local `app.*` import graph starting at Scanner production entrypoints plus static config files under `backend/app`. Research (`scanner_quality`), baseline, tests, runtime, and simulation modules are excluded from the production fingerprint.

The generated manifest records Git HEAD/branch/dirty state, per-file SHA256, aggregate production fingerprint, explicit policy fingerprint, research-only rule status, and a stable baseline ID.

B.2.6 Overextension and B.2.7 Volume-Low Guard remain non-Production. No Scanner/Ranking/Risk/Entry/Stop/Target behavior is modified.
