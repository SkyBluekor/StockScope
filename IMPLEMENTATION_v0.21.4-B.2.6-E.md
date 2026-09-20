# Implementation — v0.21.4-B.2.6-E

Added research-only final confirmation tooling:

- `backend/app/backtest/scanner_quality/candidate_quality_final_confirmation.py`
- `backend/tools/run_scanner_candidate_quality_final_confirmation.py`
- `backend/tests/test_scanner_candidate_quality_final_confirmation_v0214b26e.py`
- `backend/tools/audit_inputs/b26e_holdout_dates.txt`

Key safeguards:
- exact Scanner 0.21.3.7 guard;
- B.2.6-D verdict/source validation;
- literal frozen-rule SHA256 fingerprint;
- deterministic holdout with prior-date overlap/gap rejection;
- CURRENT and refined ranks frozen before D+1 data is read;
- WATCH/WAIT/VALIDATION slots never promoted or displaced by READY-only guard logic;
- no Production source file modifications;
- first 20 holdout dates remain frozen when extending to 30 for insufficient sample.

Output directory:
`backend/runtime/quality_audit/candidate_quality_final/`

Run:
```powershell
python backend\tools\run_scanner_candidate_quality_final_confirmation.py
```

If and only if the verdict is `INSUFFICIENT_FINAL_SAMPLE`:
```powershell
python backend\tools\run_scanner_candidate_quality_final_confirmation.py --sample-size 30 --min-required-dates 30
```
