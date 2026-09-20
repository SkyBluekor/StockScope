# Scanner NO_TRADE / Weak-Market Audit — v0.21.4-B.2.5-D

- verdict: **PASS**
- source scanner version: `0.21.3.3`
- checked dates: `80`
- checked candidates: `1338`
- dates with READY=0: `8`
- forced ENTRY with READY=0: `0`

## Representative weak cases

| Kind | Date | READY | WATCH | ENTRY | WAIT | Bad Risk | Market-regime fails | Candidates |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| WEAK_MARKET_NO_READY | 2026-07-07 | 0 | 18 | 0 | 18 | 0 | 5 | 18 |
| RISK_GATE_NO_READY | 2023-08-01 | 0 | 1 | 0 | 1 | 1 | 0 | 1 |

## Consistency checks

- READY + missing conditions: `0`
- READY + bad Risk: `0`
- ENTRY_CANDIDATE without READY: `0`
- READY=0인데 강제 ENTRY 생성: `0`

## Issues

- 발견된 decision-gate consistency issue 없음

> 이 감사는 후보를 항상 N개 채우는지 자체가 아니라, 약한 날에도 WATCH/WAIT가 READY/ENTRY_CANDIDATE로 강제 승격되는지를 검사합니다.