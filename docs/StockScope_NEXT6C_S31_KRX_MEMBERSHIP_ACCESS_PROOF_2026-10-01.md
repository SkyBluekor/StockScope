# NEXT-6C-S3.1 — KRX Historical Constituent Access & Known-At Proof

Date: 2026-10-01
Repository baseline: 8bf92b21b3af6ca9785b93b127fd9ca83934c17d

## Decision

```text
MACHINE_READABLE_ACCESS = PARTIAL_DISCOVERY_ONLY
PUBLIC_AUTOMATED_INGESTION_AUTHORIZED = false
ACCESS_CLASS = PUBLIC_MANUAL_SNAPSHOT + LICENSED_KRX_PRODUCT_REQUIRED

HISTORICAL_SNAPSHOT = true
STABLE_BENCHMARK_IDENTITY = true for the KRX index-selection surface
EFFECTIVE_MEMBERSHIP_PROVEN = true for a selected historical snapshot date
KNOWN_AT_PROVEN = false

S2_PIT_COMPATIBLE = false

NEXT_ACTION = REQUIRE_KRX_PRODUCT_OR_EXPLICIT_KRX_PERMISSION

RUNTIME_INTEGRATION = NONE
PRODUCTION_IMPACT = NONE
HOLDOUT_ACCESSED = false
```

The KRX public Data Marketplace clearly supports historical, date-scoped membership/sector snapshots, and third-party open-source bindings demonstrate that its web backend is machine-readable. However, StockScope does not treat the web backend as an authorized Production ingestion API. The verified KRX website terms do not provide affirmative automated-ingestion permission and explicitly restrict copying/reproduction/distribution/transmission without prior permission.

The public historical snapshots also do not provide source-time metadata sufficient for NEXT-6C-S2 `known_at`. Therefore StockScope must not generate `PIT_ELIGIBLE` sector evidence from the public screen/backend today.

## 1. Historical snapshot capability is real

Official KRX Data Marketplace constituent screen:

https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT006.jsp

The page exposes:

- index selection;
- 조회일자;
- constituent stock code;
- constituent name;
- close/change/market-cap fields.

This proves a historical membership snapshot can be requested for a selected date.

KRX also exposes a historical **업종별 분류 현황** data family. Current pykrx source maps this to KRX BLD `dbms/MDC/STAT/standard/MDCSTAT03901` and returns, for a selected date and market, stock code plus `IDX_IND_NM` industry name. This is a useful corroborating discovery because it directly represents stock→industry classification for the requested date.

The pykrx implementation is corroborating evidence only; it is not treated as authorization for StockScope scraping or as the source of record.

## 2. A machine-readable web backend exists, but StockScope does not adopt it

Current pykrx source maps the KRX constituent screen to:

```text
dbms/MDC/STAT/standard/MDCSTAT00601
parameters:
  trdDd
  indIdx
  indIdx2
```

and maps historical sector classification to:

```text
dbms/MDC/STAT/standard/MDCSTAT03901
parameters:
  trdDd
  mktId
```

This demonstrates that the web UI is backed by structured data responses.

It does **not** establish that StockScope is permitted to automate that backend.

Official KRX Data Marketplace website terms:

https://data.krx.co.kr/contents/MMC/COMS/client/MMCCOMS002_S1.cmd?isPreviousMember=N&type=C

The terms state that users may not copy, reproduce, distribute, transmit or publicly communicate site information without KRX prior permission. Accordingly, StockScope does not interpret the public web backend as an authorized bulk/provider interface.

Consequences:

```text
undocumented web BLD endpoint
→ research discovery only
→ no Production KrxProvider endpoint
→ no unattended historical backfill
→ no local runtime database population
```

No CAPTCHA/session/rate-limit bypass or browser-cookie automation is attempted.

## 3. Existing official KRX Open API remains insufficient

StockScope's Production `KrxProvider` currently uses:

```text
https://data-dbg.krx.co.kr/svc/apis
```

for documented KRX Open API services.

The verified KRX Open API catalog provides market/index price services but does not expose the historical constituent/sector-membership service required by NEXT-6C.

Therefore the existing `KRX_API_KEY` must not be assumed to authorize or cover the Data Marketplace web BLD endpoints.

```text
backend/app/market/providers/krx.py
→ unchanged
```

## 4. Historical snapshot date is not known_at

The public KRX historical query proves that membership/classification applies to a selected date.

It does not prove when that fact was first available to a historical decision process.

The following values are explicitly rejected as `known_at`:

```text
query_date
current download/fetch timestamp
browser response time
today's observation of an old snapshot
OpenDART modify_date
```

Hence:

```text
effective membership = supported
known_at               = unresolved
S2 PIT_ELIGIBLE        = blocked
```

## 5. Stronger official KRX source

Official KRX index-information product:

https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA005.jsp

KRX documents:

- closing/next-day index-information files;
- closing/next-day constituent-information files;
- index corporate-action files containing constituent changes.

These files are the strongest current candidate for defensible source-time/effective-date lineage.

They also have an explicit product/licensing/contact path, which is preferable to treating Data Marketplace web requests as a Production API.

Therefore the operational next step is not scraping more public snapshots. It is to obtain one of:

1. explicit KRX permission/API documentation for historical constituent/sector automated use; or
2. authorized access to the KRX index-information constituent/action product.

## 6. Offline probe added

Research-only probe:

```text
tools/research/probe_krx_sector_membership.py
```

Purpose:

- inspect a manually downloaded or otherwise authorized KRX CSV/JSON export;
- verify stock-code identity is present;
- record schema fields and deterministic schema hash;
- record constituent-set/payload hashes;
- explicitly report whether source-time-like metadata fields are present;
- never promote those fields to `known_at_proven` on its own.

It contains no HTTP/network client.

Example:

```powershell
python tools/research/probe_krx_sector_membership.py \
  --input .\sample_krx_membership.csv \
  --query-date 20220902 \
  --benchmark-identity "KRX:KOSPI:SECTOR:26"
```

The probe always keeps:

```text
known_at_proven = false
pit_contract_compatible = false
network_access = false
```

until separate authenticated source-time evidence exists.

## 7. Why no live probe was performed

A live automated call to undocumented KRX Data Marketplace web BLD endpoints would not resolve the real blocker:

- it would show that the endpoint responds;
- it would not prove that StockScope has authorized automated-use rights;
- it would not produce historical `known_at`;
- it would therefore still fail S2.

The public website itself already proves the snapshot feature, while KRX product documentation identifies the proper stronger data path.

Avoiding an unnecessary automated scrape is therefore both technically sufficient and consistent with the source-governance boundary.

## 8. S2 field compatibility

| S2 field | Public KRX historical snapshot |
| --- | --- |
| ticker | supported |
| market | supported |
| sector_group / index name | supported |
| benchmark_name | supported |
| benchmark_identity | supported through KRX index selection/code surface |
| effective_from / effective state | selected-date membership supported; full interval requires reconstruction |
| effective_to | not directly proven by one snapshot |
| known_at | **not proven** |
| source | supported |
| source_revision | no durable public revision contract verified |
| source_hash | StockScope can hash authorized export |
| historical_membership_proven | supported for selected snapshot date |
| source_time_proven | **false** |

Result:

```text
S2_PIT_COMPATIBLE = false
```

## 9. Next task

```text
NEXT-6C-S3.2 — KRX Access Decision / Sector PIT Route Closure
```

Choose one operational route:

### Route A — authorized KRX data access is obtained

Then implement:

```text
authorized KRX source
→ immutable raw cache
→ SectorMembershipEvidence
→ Sector PIT Coverage Audit
→ common-session sector impact
```

### Route B — no authorized KRX historical source is obtained

Then stop historical-sector reconstruction and use:

```text
historical:
  Market ↔ Stock only

prospective:
  capture sector membership from a frozen collection start onward
```

No third-party approximation or OpenDART current-industry backfill is permitted.

## 10. Explicit non-actions

```text
Production KrxProvider changes = 0
undocumented KRX web requests = 0
browser cookie/session automation = 0
historical DB/backfill = 0
SectorMembershipEvidence promotion = 0
Market→Sector→Stock impact activation = 0
Strategy/Scanner/Risk/Holdings changes = 0
R2.5 = NOT STARTED
Holdout access = 0
```
