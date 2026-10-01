# NEXT-6C-S3 — Historical Sector Membership Source Feasibility

Date: 2026-10-01
Repository baseline: d63f0ab7089dd92b5bd7cffb172868631c7cea35

## Decision

```text
SOURCE_DECISION = DIRECT_PIT_SOURCE
PRIMARY_SOURCE = KRX
PUBLIC_SURFACE = KRX Data Marketplace [11006] 지수구성종목
STRONGER_SOURCE = KRX 지수정보상품 구성종목정보/지수조치정보

HISTORICAL_DATE_SUPPORTED = true
CONSTITUENT_IDENTITY_SUPPORTED = true
EFFECTIVE_DATE_SUPPORTED = true
KNOWN_AT_SUPPORTED = false on the verified public historical-query surface
BENCHMARK_IDENTITY_SUPPORTED = true

PIT_CONTRACT_COMPATIBLE = false today
RUNTIME_INTEGRATION = NONE
PRODUCTION_IMPACT = NONE
HOLDOUT_ACCESSED = false
```

KRX is confirmed as the authoritative source family for dated index membership. The free/public constituent screen can directly answer which securities belong to a selected index on a selected query date, but the verified surface does not expose a publication/availability timestamp that satisfies NEXT-6C-S2 `known_at` proof. Therefore no historical membership is promoted to `PIT_ELIGIBLE` yet.

## 1. KRX Data Marketplace — direct dated constituent snapshot

Official source:
https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT006.jsp

KRX screen **[11006] 지수구성종목** exposes:

- 지수명
- 조회일자
- 종목코드
- 종목명
- 종가
- 대비
- 등락률
- 상장시가총액

This is direct dated membership evidence rather than a current-company-industry proxy. The same page contains date-specific notes for sector-index discontinuations and index-base changes, so dated index state is a first-class concept on the screen.

### Proven by this surface

- historical/query-date dimension exists;
- constituent stock identity exists;
- selected benchmark/index identity exists;
- a dated constituent snapshot can establish membership effective on the selected date.

### Not proven by this surface

- when the historical membership fact first became knowable;
- publication/availability timestamp for each membership snapshot;
- machine-readable access rights for StockScope automation;
- complete 2016-2023 coverage for every sector index currently used by StockScope.

Because S2 separates `effective_*` from `known_at`, selected-date membership alone is insufficient for `PIT_ELIGIBLE`.

## 2. Official KRX Open API — no constituent-membership service verified

Official service list:
https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd

The current KRX Open API service catalog publishes index daily-price services and states that the service catalog generally covers data from 2010 onward. No stock-to-index constituent-membership API was identified in the verified catalog.

Consequences:

- StockScope must not assume its current KRX Open API integration can fetch historical constituents;
- index price history and constituent history remain separate capabilities;
- no new KRX Open API endpoint is added in this task.

## 3. KRX 지수정보상품 — stronger PIT evidence path exists

Official source:
https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA005.jsp

KRX describes three index-information files:

1. **종가지수정보 파일** — closing/next-day index information;
2. **구성종목정보 파일** — closing/next-day constituent information, including constituents and index-reflected stock information;
3. **지수조치정보 파일 (Corporate Action)** — individual-security index changes, including constituent changes.

This establishes that KRX has an official source family capable of representing both membership state and membership-change events. The closing/next-day distinction and corporate-action records are the most promising route for satisfying S2 `known_at` and effective-date lineage.

However, StockScope does not currently have verified authorized access to this product. This task does not assume a license or silently use it.

## 4. OpenDART remains STATIC_CURRENT

Official corporate overview:
https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019002

OpenDART `company.json` exposes `induty_code`, but its request contract takes only an API key and `corp_code`; it has no historical date parameter for industry membership.

Official corporation-code API:
https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018

`modify_date` is documented as the **final modification date of corporate-overview information**. It is not documented as an industry-change event or an effective date for `induty_code`.

Therefore:

```text
OpenDART company.json
→ STATIC_CURRENT
→ audit/current-reference use only
→ historical PIT promotion forbidden
```

No date interval may be inferred from `modify_date`.

## 5. Capability matrix

| Capability | KRX constituent screen | KRX index information product | OpenDART company |
| --- | --- | --- | --- |
| stock ↔ index membership | Yes | Yes | No direct index membership |
| selected historical date | Yes | Product/file history dependent | No |
| stock identity | Yes | Yes | Yes |
| benchmark/index identity | Yes | Yes | No direct benchmark identity |
| effective membership state | Yes, selected snapshot date | Yes | No |
| constituent-change evidence | Not established by screen alone | Yes | No |
| historical `known_at` proof | No verified timestamp | Strong candidate via closing/next-day/action files | No |
| current StockScope machine access | Not established | Not established | Existing OpenDART provider |
| S2 `PIT_ELIGIBLE` today | No | Not operationally verified | No |

## 6. Why no provider/backfill is implemented now

S2 requires all of the following before historical sector membership can be used:

```text
effective membership
+
source-time proof / known_at
+
benchmark identity
+
deterministic source lineage
```

The public KRX constituent screen currently proves the first and third items, but not the second. Fabricating `known_at = query_date` would create look-ahead risk and violate the S2 contract.

Therefore:

- no `SectorMembershipEvidence` is generated from KRX yet;
- no historical sector DB/cache is created;
- no current OpenDART mapping is backfilled into the past;
- NEXT-6C-S1 remains Market↔Stock only;
- Strategy/Scanner/Risk/Holdings remain unchanged.

## 7. Next task

```text
NEXT-6C-S3.1
KRX Historical Constituent Access & Known-At Proof
```

Bounded objectives:

1. verify authenticated/permitted machine-readable access to dated KRX constituent results;
2. verify stable KRX benchmark identities for the sector indexes mapped by StockScope;
3. verify whether response/file metadata can produce defensible `known_at`;
4. if not, determine whether the KRX constituent/corporate-action information product is required;
5. test coverage only against the Development-era sector universe without accessing Holdout;
6. populate S2 `SectorMembershipEvidence` only if every required field is source-supported.

## 8. Explicit non-actions

```text
Provider integration = NONE
DB migration/backfill = NONE
3-way Market→Sector→Stock impact = NONE
Strategy/Scanner/Risk/Holdings changes = NONE
R2.5 = NOT STARTED
Holdout access = 0
```
