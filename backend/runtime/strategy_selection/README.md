# Strategy Selection Runtime

This directory is the local Production owner for VN-P5-S1 Strategy Selection Policy state.

Runtime-generated files are intentionally ignored by Git:

- `policies/<policy-id>.json`: immutable, content-addressed Selection Policy snapshots.
- `active.json`: the mutable active/rollback reference, updated only through explicit activation or rollback.

Important boundaries:

- Simulation owns Registry, Evaluation Artifact, Change Proposal, and Approval Artifact.
- Production Selection Policy snapshots are created only from a validated immutable Approval Artifact.
- Normal policy resolution reads this runtime directory only; it must not select the latest row from `simulation.db`.
- Strategy Selection Policy is separate from the Production Exit Policy mapping.
- Risk Gate, NO_TRADE safety behavior, suitability score meaning, and candidate priority are outside the Selection Policy change scope.
- If `active.json` is missing or invalid, runtime resolution fails safe to the legacy current 10-strategy behavior.
- If the active policy snapshot is invalid but the recorded rollback snapshot is valid, resolution may use the rollback snapshot without silently rewriting `active.json`.
- Production active reference publication requires atomic file replacement. If the host blocks atomic replacement, activation fails and the previous active reference is preserved.
- Runtime policy snapshots and active/rollback references will be added to the P5 backup/restore integrity contract before P5 completion.
