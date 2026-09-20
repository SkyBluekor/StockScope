# v0.21.4-B.2.3.4c.4f.1 — MA120 regression test compatibility hotfix

## Scope
Test-only compatibility update after c.4f intentionally restores the Sector RS input path.

## Why
The c.4d MA120 regression test contained a stage-specific source assertion requiring
`relative_strength_sector_pct=None`. That assertion was correct for c.4d, but becomes
obsolete once c.4f intentionally replaces the hardcoded `None` with prepared Sector RS input.

## Production impact
None. No production files are included or changed.

## Changed file
- `backend/tests/test_ma120_production_input_v0214b234c4d.py`

The test continues to verify the c.4d invariants: 60-row technical path, dedicated MA120
calculation, no lookahead, and scanner cache version. It no longer owns Sector RS behavior,
which is covered by c.4f tests.
