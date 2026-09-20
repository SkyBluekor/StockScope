# v0.21.4-B.2.7-D — Volume Signal Robustness & Aggressiveness Audit

- Freeze the only B.2.7-C survivor: `VOLUME_LOW_GUARD`.
- No Q25 retuning, numeric threshold search, strategy exception, feature combination, weight, ML, or Production change.
- Reuse B.2.7-A/B development JSON and B.2.7-C current-version JSON.
- Primary: T1-first nonworse, Stop-first nonworse, policy-aware event-R improvement, MAE protection.
- Audit time blocks, date-level event-R wins/losses, GOOD/BAD swaps, and Top3 demotion aggressiveness.
- Verdict: `FREEZE_VOLUME_LOW_GUARD`, `VOLUME_SIGNAL_TOO_AGGRESSIVE`, `VOLUME_SIGNAL_NOT_ROBUST`, or `INSUFFICIENT_ROBUSTNESS_EVIDENCE`.
