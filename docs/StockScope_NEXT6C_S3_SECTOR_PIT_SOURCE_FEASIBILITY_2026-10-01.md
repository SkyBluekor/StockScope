# NEXT-6C-S3 — Historical Sector Membership Source Feasibility

Date: 2026-10-01
Repository baseline: d63f0ab7089dd92b5bd7cffb172868631c7cea35

## Decision

- SOURCE_DECISION = DIRECT_PIT_SOURCE
- PRIMARY_SOURCE = KRX Data Marketplace — 지수구성종목
- HISTORICAL_DATE_SUPPORTED = true
- CONSTITUENT_IDENTITY_SUPPORTED = true
- EFFECTIVE_DATE_SUPPORTED = true
- KNOWN_AT_SUPPORTED = false for the verified free historical-query surface
- BENCHMARK_IDENTITY_SUPPORTED = true
- PIT_CONTRACT_COMPATIBLE = false
- RUNTIME_INTEGRATION = NONE
- PRODUCTION_IMPACT = NONE
- HOLDOUT_ACCESSED = false

KRX provides a direct date-scoped historical constituent view, but the currently verified public query surface does not prove when each historical membership fact became knowable. NEXT-6C-S2 requires both effective membership and source-time proof, so the source cannot yet be promoted to PIT_ELIGIBLE.

## Evidence

### KRX Data Marketplace direct constituent snapshot

Official page: https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT006.jsp

Screen [11006] 지수구성종목 exposes 지수명, 조회일자, 종목코드, 종목명, 종가, 대비, 등락률, 상장시가총액. This is direct evidence that KRX exposes index membership scoped by a selected date rather than only today's constituents.

The page also includes date-sensitive notes about sector-index discontinuations and new index bases from 2024-07-01, reinforcing that the screen represents dated index state.

### Historical range corroboration

Current pykrx source maps the same KRX screen to BLD dbms/MDC/STAT/standard/MDCSTAT00601 with parameters trdDd, indIdx and indIdx2, and exposes get_index_portfolio_deposit_file(ticker, date). It explicitly blocks dates on or before 2014-05-01 because the KRX web server does not provide older constituent data.

Reference: https://github.com/sharebook-kr/pykrx/blob/master/pykrx/stock/stock_api.py

This is corroborating implementation evidence, not the authoritative source. The authoritative source remains KRX. StockScope's current Macro Development interval begins in 2016, so the observed historical range is sufficient in principle for that Development period.

### Official KRX Open API gap

Official service list: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd

The verified public Open API list provides index daily price services, but no constituent-membership API was found. StockScope must not assume its existing KRX Open API key authorizes the Data Marketplace constituent-screen backend.

### KRX index information product

Official description: https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA005.jsp

KRX explicitly describes constituent-information files and index corporate-action files. The constituent file contains index constituents, reflected share count, price, weight and free-float information; the corporate-action file contains constituent changes and other per-security index changes.

This confirms KRX is the correct authority for direct membership snapshots and membership-change evidence. It does not prove that StockScope currently has authorized machine-readable access to that product.

### OpenDART remains STATIC_CURRENT

Corporate overview: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019002

OpenDART company.json exposes induty_code but no date parameter or historical industry-membership result.

Corporation-code API: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018

modify_date is the final modification date of corporate-overview information. It is not an industry-change event and cannot prove which industry applied before or after that date.

Therefore OpenDART company.json remains STATIC_CURRENT and historical PIT promotion remains forbidden.

## Capability matrix

| Capability | KRX constituent screen | KRX index information product | OpenDART company |
| --- | --- | --- | --- |
| stock ↔ index membership | Yes | Yes | No direct index membership |
| historical date input | Yes | Yes / product history dependent | No |
| stock code identity | Yes | Yes | Yes |
| benchmark/index identity | Yes | Yes | No |
| effective membership date | Selected snapshot date | Yes | No |
| constituent change events | Not established by this screen | Yes | No |
| historical known-at proof | Not established | Potentially supportable by dated delivery/action files | No |
| current authorized machine access | Not established | No | Existing provider only |
| NEXT-6C-S2 PIT-compatible today | No | Not yet operationally verified | No |

## Why S4 is not authorized yet

S2 deliberately separates effective_from/effective_to from known_at. The historical KRX constituent screen can prove that a stock belonged to a selected index on a selected date, but the verified screen does not expose a publication timestamp or historical availability timestamp for that fact.

Inventing known_at = selected_date would violate S2. Therefore this research does not authorize provider integration yet.

## Next task

NEXT-6C-S3.1 — KRX Historical Constituent Access & Known-At Proof

Verify without changing Production:

1. whether authenticated KRX Data Marketplace access can retrieve MDCSTAT00601 historical constituent responses in a machine-readable and permitted way;
2. whether index identifiers are stable enough to map existing SectorRelativeStrengthAnalyzer aliases to dated KRX index identities;
3. whether official response/file metadata can provide a defensible known_at, or whether the licensed constituent/corporate-action product is required;
4. whether 2016-2023 coverage is complete for the sector indexes StockScope currently maps;
5. whether the result can populate SectorMembershipEvidence without inference.

No provider, DB migration, backfill, Strategy/Scanner/Risk/Holdings integration, R2.5 execution, or Holdout access is authorized by this decision.
