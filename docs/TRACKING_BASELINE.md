# TRACK.1 Production Baseline

**Status:** CLOSED / FROZEN  
**Closed after:** TRACK.1.10.4 — Same Baseline Tracking Merge

## Purpose

TRACK.1 is the user-facing stock tracking baseline. Future work should treat the behavior below as stable production behavior unless a real defect requires a targeted fix or a new TRACK phase explicitly changes the contract.

## Completed behavior

- Run the existing Production Scanner inside Stock Tracking and add recommendation candidates.
- Search stocks independently and add them as manual tracking records.
- Keep Scanner and Manual provenance separately while rendering one row when they share the exact same baseline.
- Use confirmed EOD close as the tracking reference price.
- Evaluate tracking performance from D+1 onward only.
- Track current return, maximum rise/fall, and 5D/10D/20D returns when enough trading days exist.
- Record Entry/Stop/Target touches as price-level observations, not simulated fills.
- Support ACTIVE → CLOSED lifecycle and delete only after closing.
- Freeze CLOSED performance; closed records are not refreshed.
- Preserve Scanner snapshots and snapshot integrity for later analysis.

## Frozen rules

### Reference baseline

A tracking baseline is identified by:

`market + ticker + recommendation_date + reference_price`

If Scanner and Manual tracking have the same baseline, they are merged into one tracking row with both source flags. If date or reference price differs, the records remain separate.

### Performance timing

- D = confirmed reference trading day / EOD close.
- D+1 and later = performance observation period.
- Missing future horizons remain `null` / `-`; they are never treated as 0%.

### Source semantics

- `has_scanner_source = true` means the record participates in Scanner evidence/analysis.
- `has_manual_source = true` means the user directly chose the stock.
- A record may contain both sources.
- A Manual-only record does not count as Scanner evidence.

### Lifecycle

- ACTIVE records may be refreshed and closed.
- CLOSED records are frozen and cannot be refreshed.
- ACTIVE records cannot be deleted directly.
- A same-baseline CLOSED Manual record is not reopened on the same confirmed trading day; a new baseline requires a later confirmed trading day.

### Data source

Market Store remains the source of truth for confirmed market bars. Tracking does not maintain a competing OHLC history database.

## Change policy

Do not reopen TRACK.1 for cosmetic tweaks, extra dashboards, or speculative edge cases. A future change should happen only when:

1. a reproducible TRACK defect is found, or
2. a new explicitly scoped TRACK phase changes the product contract.

Historical strategy validation, execution simulation, and post-analysis belong to their own phases and must not silently change this baseline.
