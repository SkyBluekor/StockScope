# B.2.5-D Research Result

## 결론
기존 strategy-integrity historical audit를 재사용한 Smoke/consistency 분석에서 강제 READY/ENTRY 승격은 확인되지 않았다. Production decision logic 수정 근거가 없으므로 **NO CODE POLICY CHANGE**가 적절하다.

## 재사용한 표본
- 80 evaluation dates
- 1,338 actionable candidates
- READY=0 날짜: 8일

## 모순 검사
- READY + 부족 조건: 0건
- READY + Risk 경고/차단: 0건
- ENTRY_CANDIDATE + non-READY: 0건
- READY=0인데 ENTRY_CANDIDATE 강제 생성: 0건

## 대표 weak-market
### 2026-07-07
- candidates: 18
- READY: 0
- WATCH: 18
- ENTRY_CANDIDATE: 0
- WAIT: 18
- Top 후보들의 미충족 사유에 `market_regime=하락장`이 실제 포함됨

Scanner가 후보를 화면에는 유지하지만 진입 후보로 승격하지 않았다.

## 대표 Risk-gate
### 2023-08-01
- candidates: 1
- READY: 0
- WATCH: 1
- ENTRY_CANDIDATE: 0
- WAIT: 1
- Risk: CAUTION / warning=true
- missing conditions: 2

Risk 경고 후보가 READY로 올라가지 않았다.

## 코드 경로 확인
현재 Scanner decision gate는 조건/Risk로 candidate_state/action을 정한 뒤 actionable 목록을 만들고, `candidate_limit`은 마지막 표시 개수를 자르는 데만 사용된다. READY 수를 맞추기 위한 threshold 완화/WAIT→READY 승격 분기는 확인되지 않았다.

B.2.5-C의 tie-break는 동률 순서만 바꾸며 Strategy/Risk 조건을 완화하지 않는다.

## 버전 주의
재사용 historical audit의 scanner version은 `0.21.3.3`이다. 현재 `0.21.3.7`까지의 이후 변경에서 decision-gate 분기 자체는 변경하지 않았고, B.2.5-C는 Ranking tie-break만 추가했다. 따라서 historical 결과는 gate sanity 증거로 사용하고, 새 D 도구는 로컬 보유 historical audit에도 동일한 모순 검사를 재실행할 수 있게 제공한다.
