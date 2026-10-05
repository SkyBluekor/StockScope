# StockScope NEXT-6E R5R 통합 설계 기준선

작성일: 2026-10-05 (Asia/Seoul)  
단계: NEXT-6E-R5R-C1  
Baseline main: c4b65a660d8b550545be957f3ae8aeb73171727a

---

## 0. 이 문서의 지위

이 문서는 R4 → R5 → R5R로 이어진 Reference Adequacy / empirical stability 설계 흐름을 앞으로의 작업에서 반복해서 재해석하지 않도록 정리한 **Current Design Baseline**이다.

역할은 세 가지다.

1. 현재 무엇이 authoritative한지 한눈에 보여준다.
2. 과거 설계가 왜 superseded / historical 상태가 되었는지 짧게 보존한다.
3. 다음 작업에서 무엇을 다시 열지 말아야 하고, 무엇만 해결하면 되는지 고정한다.

이 문서는 기존 frozen contract를 대체하는 계산 계약이 아니다. 계산 정의가 충돌할 경우 각 authoritative JSON contract가 우선한다.

---

# 1. StockScope의 본래 목적

StockScope는 통계 논문을 작성하기 위한 프로젝트가 아니다.

목적은:

> 여러 데이터·전략·검증 결과를 내부에서 분석하고, 사용자가 주식 상태를 빠르게 이해하고 판단할 수 있도록 신뢰할 만한 결과와 근거를 제공하는 것.

이다.

StockScope가 하려는 일:

- 후보 종목과 보유 종목에 대한 분석 지원
- 여러 전략의 성능과 적합성 관리
- 시장·기간·상태를 반영한 판단 보조
- 손절·회복·추가매수 등 보유상황 대응 판단 지원
- 내부 계산은 복잡하더라도 사용자에게는 결과 중심으로 제공
- 검증되지 않은 분석을 확정적 사실처럼 보이지 않도록 통제

StockScope가 하려는 일이 아닌 것:

- 미래 주가를 수학적으로 보장
- 투자 수익을 보장
- 모든 실제 금융시장을 하나의 완전한 확률과정으로 증명
- 내부 지표마다 논문 수준의 theorem을 요구
- 검증 체계 자체를 제품의 중심 기능으로 만드는 것

**제품 판단 지원이 목적이고, R5R·JEV·Reference Adequacy는 그 목적을 돕는 내부 수단이다.**

---

# 2. 앞으로의 설계 깊이 원칙

앞으로 StockScope의 기준은 다음이다.

> **틀리지 않을 만큼 충분히 설계하고, 실제로 써볼 수 있을 만큼 빠르게 구현한다.**

계속 엄격하게 유지할 것:

- 데이터 leakage 방지
- Holdout 보호
- 평가 결과를 보고 threshold / 규칙을 역으로 맞추지 않기
- 계산 정의와 입력 identity의 재현성
- 계산 불능·정책 미승인을 PASS로 처리하지 않기
- observed-path 결과를 population/future guarantee로 과장하지 않기
- frozen 계약을 몰래 수정하지 않기

기본적으로 하지 않을 것:

- 실제 blocker가 아닌 사안을 별도 phase로 계속 분할
- 단순 operational threshold에 논문 수준의 theorem 요구
- 같은 결론을 여러 review 문서로 반복
- 내부 metric 하나마다 독립적인 대규모 governance chain 생성
- JEV 실행 자체를 목적으로 설계를 복잡하게 만들기

새로운 단계는 **실제 구현 또는 결과 신뢰성을 막는 문제가 있을 때만** 추가한다.

---

# 3. 전체 설계 lineage

## 3.1 R4 — population-level 접근의 첫 시도

R4에서는 lattice CDF / projection 계열 구조를 이용해 population-level 안정성을 정당화하려 했다.

하지만 actual-process model use에 필요한 다음 조건을 실제 데이터에 대해 충분히 정당화하지 못했다.

- strict stationarity
- alpha mixing 및 관련 dependence 조건
- population-level 확률 보장을 위한 실제 process binding

따라서 R4는 현재:

~~~text
R4
=
HISTORICAL / SUPERSEDED FOR MODEL USE
~~~

이다.

R4 결과를 retroactive PASS로 바꾸지 않는다.

---

## 3.2 R5 — 더 정교한 population method

R5에서는 기존 문제를 해결하기 위해 다음 방향으로 확장했다.

- locally stationary process
- functional dependence
- analytical conservative concentration band
- prospective candidate grid
- all-later / latest-state validation 구조

R5 자체의 theorem 설계와 내부 정합성은 상당 부분 닫혔다.

그러나 실제 DGS10 process에 다음을 감사 가능한 수준으로 bind하지 못했다.

- iid innovation representation
- dependence constants C_dep / rho
- local approximation constants C_ls / zeta
- global time smoothness L2
- moment conditions q / M_q

GA2-BR1의 결론은:

~~~text
MODEL_USE_BINDING_ROUTE
=
PARTIALLY_FEASIBLE

COMPLETE_AUDITABLE_ROUTE_FOR_CURRENT_R5
=
NO

METHOD_USE_REDESIGN
=
REQUIRED
~~~

였다.

따라서 legacy R5는 현재:

~~~text
FROZEN HISTORICAL METHOD

MODEL USE
=
BLOCKED

IMPLEMENTATION
=
NOT AUTHORIZED
~~~

이다.

---

# 4. R4/R5 작업은 헛된 작업이 아니다

R4/R5에서 얻은 핵심 교훈은 앞으로 계속 유지한다.

### 교훈 1

~~~text
theorem이 내부적으로 맞다
!=
actual data에 사용 가능하다
~~~

### 교훈 2

실제 데이터에 증명하기 어려운 stochastic process를 단순히 분석을 통과시키기 위해 가정하지 않는다.

### 교훈 3

방법론의 수학적 정합성과 actual-process model-use validity는 구분한다.

### 교훈 4

검증 결과에 맞추기 위해 dependence constant, window, threshold 등을 역산하지 않는다.

### 교훈 5

실제 제품에 필요하지 않은 population claim이라면 더 약하고 직접 측정 가능한 target을 사용하는 것이 낫다.

이 교훈이 R5R 전환의 근거가 되었다.

---

# 5. MUR1 — R5R로의 전환

MUR1에서 선택된 primary architecture:

~~~text
R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1
~~~

핵심 전환:

~~~text
population-law stability를 증명
        ↓
하지 않음

fixed observed path에서
empirical stability를 직접 측정
~~~

즉 R5R은 legacy R5를 억지로 PASS시킨 patch가 아니다.

~~~text
R5R
=
NEW TARGET / METHOD FAMILY
~~~

이다.

---

# 6. 현재 R5R이 주장하는 것

현재 target:

~~~text
NEXT6E_S6A_R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1
~~~

현재 method:

~~~text
NEXT6E_S6A_R5R_EMPIRICAL_STABILITY_V1
~~~

R5R의 정확한 claim은 다음 범위다.

> 하나의 고정된 declared observed path에서, 사전에 고정된 backward window와 approved anchor를 사용하여 empirical distribution / location / scale의 변화가 지정된 operational policy 안에 있었는지를 결정론적으로 평가한다.

---

# 7. R5R이 주장하지 않는 것

다음 표현은 금지한다.

- population CDF confidence coverage
- future distribution stability probability
- p-value / statistical significance
- latent population의 minimum sample size theorem
- iid innovation representation 승인
- mixing / functional-dependence model 승인
- 미래 주가 안정성 보장
- 투자성과 보장

R5R은 **observed-path empirical certificate**다.

---

# 8. 현재 authoritative artifacts

## 8.1 Method Contract

경로:

~~~text
docs/contracts/NEXT6E_S6A_R5R_METHOD_CONTRACT_V2.json
~~~

Status:

~~~text
TARGET_DESIGN_FROZEN
METHOD_DESIGN_FROZEN
~~~

Target:

~~~text
NEXT6E_S6A_R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1
~~~

Method:

~~~text
NEXT6E_S6A_R5R_EMPIRICAL_STABILITY_V1
~~~

Design SHA256:

~~~text
05852b077e6c29820643299f66984f496ffe806d88c6544c577ee3357c5f74eb
~~~

Semantic SHA256:

~~~text
5519ad12a6e3dafb30041935c6ead2869d35148aadb2a6bab8443521ea8310c4
~~~

## 8.2 CandidateDomain

~~~text
docs/contracts/NEXT6E_S6A_R5R_CANDIDATE_DOMAIN_V1.json

SHA256
=
2f89ea3fdf775d718fabf955ee266b5cf36736f68b0fe97ced2cc5da83e0cdb4
~~~

## 8.3 Window Profile

~~~text
docs/contracts/NEXT6E_S6A_R5R_WINDOW_PROFILE_V1.json

SHA256
=
47a11455b159564db80eaf2c61bd89710a4bf56aea5d740eb60617ac2a3d385c
~~~

## 8.4 Deterministic Review

현재 authoritative review:

~~~text
docs/reviews/NEXT6E_S6A_R5R_DETERMINISTIC_REVIEW_RESULT_V2.json

Verdict
=
PASS
~~~

MUR3에서 발견된 세 ambiguity:

- missing-horizon / joint chronology semantics
- chronology hash canonicalization
- exact numeric comparison semantics

은 MUR3-BR1에서 모두 RESOLVED 상태다.

관련 문서:

~~~text
docs/reviews/
NEXT6E_S6A_R5_MUR3_BR1_R5R_계약_모호성_해소_2026-10-05.md
~~~

---

# 9. 현재 frozen 계산 구조

## 9.1 Horizon

~~~text
h ∈ {1, 5, 10}

1  -> delta_bp_1obs
5  -> delta_bp_5obs
10 -> delta_bp_10obs
~~~

## 9.2 Window

~~~text
w(n)
=
ceil(n/10)
~~~

세 horizon이 동일 observation-count window를 사용한다.

Window는 backward-only다.

## 9.3 T_EMP

~~~text
T_EMP,h(s,v)
=
sup_x |Fhat_h,v(x)-Fhat_h,s(x)|
~~~

두 window의 observed-value union에서 exact하게 계산한다.

Synthetic x-grid는 사용하지 않는다.

## 9.4 L_EMP

~~~text
L_EMP,h(s,v)
=
|mhat_h(v)-mhat_h(s)| / dhat_h(s)
~~~

Median은 midpoint sample median이다.

## 9.5 S_EMP

~~~text
S_EMP,h(s,v)
=
|dhat_h(v)-dhat_h(s)| / dhat_h(s)
~~~

MAD는 midpoint median of absolute deviations다.

Anchor MAD가 0이면 fail-close한다.

---

# 10. Candidate 구조

Frozen grid:

~~~text
j/20
j = 2,...,19
~~~

총 18 prospective fractions.

Mapping:

~~~text
N_j(n)
=
ceil(j*n/20)
~~~

Integer collision:

~~~text
canonical representative
=
smallest j
~~~

---

# 11. All-later / latest

현재 target에서는 anchor N 이후:

~~~text
v = N+1,...,n
~~~

전부 평가한다.

Latest:

~~~text
v=n
~~~

도 반드시 포함한다.

현재 observed-path suffix claim을 유지하는 동안 이 규칙은 frozen이다.

Persistence rule, 최근 몇 state만 평가, 허용 위반 횟수 등으로 바꾸려면 **새 target/version의 명시적 변경**이 필요하다.

---

# 12. 현재 metric aggregation

**현재 Method Contract V2 기준 authoritative rule은 아직:**

~~~text
ALL_HORIZONS_AND
AND
ALL_METRICS_AND
AND
ALL_LATER_STATES
~~~

이다.

즉 현재 V2를 그대로 구현한다면 T/L/S 세 metric 모두 policy tolerance가 필요하다.

다만 다음 제품 중심 정책 검토에서 실제 StockScope reuse purpose상 일부 metric이 단순 diagnostic이면 충분하다고 결정할 수 있다.

그 경우:

- T/L/S formula 자체를 다시 연구하지 않는다.
- observed-path target을 불필요하게 다시 뜯지 않는다.
- gate activation / aggregation 부분만 작은 versioned contract 변경으로 처리한다.

**현재 V2의 사실과, 향후 제품 단순화 가능성을 혼동하지 않는다.**

---

# 13. Common-N의 정확한 의미

ID:

~~~text
OBSERVED_PATH_COMMON_N
~~~

현재 정의:

> approved grid 안에서 모든 required horizon / later state / active policy metric 조건을 만족한 가장 이른 effective anchor.

현재 V2에서는 T/L/S 모두 active gate이므로 세 metric 전부를 포함한다.

다음으로 표현하지 않는다.

~~~text
minimum population sample size
theorem-required N
future-stability point
production safety threshold
optimal training size
~~~

Common-N은 **frozen observed path / window / candidate grid / policy에서의 retrospective suffix summary**다.

---

# 14. Joint chronology

MUR3-BR1에서 다음으로 고정됐다.

~~~text
PREBOUND_COMPLETE_JOINT_CHRONOLOGY
~~~

흐름:

~~~text
SOURCE DATASET
→
PREDEFINED JOINT ELIGIBILITY
→
EXCLUSION PROVENANCE
→
EVALUATION IDENTITY/HASH FREEZE
→
R5R EVALUATOR
~~~

Evaluator 내부에서는:

- row drop 금지
- dynamic filtering 금지
- imputation 금지
- repair 금지

Bound payload 안에서 required horizon이 누락되면:

~~~text
BLOCKED
MISSING_REQUIRED_HORIZON
~~~

이다.

---

# 15. Numeric semantics

Authoritative numeric contract:

~~~text
R5R_EXACT_RATIONAL_V1
~~~

Metric 및 policy comparison은 exact rational arithmetic을 사용한다.

~~~text
a/b <= c/d
iff
a*d <= c*b
~~~

Binary floating point epsilon은 policy 판정 authority가 아니다.

Decimal은 UI/display 용도로 사용할 수 있다.

---

# 16. Chronology identity

Chronology hash contract:

~~~text
R5R_JOINT_CHRONOLOGY_HASH_V1
~~~

- date: YYYY-MM-DD
- row order: strictly ascending
- canonical compact JSON
- recursive lexicographic key order
- SHA-256
- lowercase 64 hex

이 규칙은 deterministic review에서 검증됐다.

---

# 17. Deterministic 상태

Historical Review V1:

~~~text
BLOCKED_CONTRACT_AMBIGUITY
~~~

이는 당시 실제 contract ambiguity가 있었기 때문에 historical fact로 유지한다.

현재 Review V2:

~~~text
PASS
~~~

따라서 특별한 새로운 defect가 발견되지 않는 한 다음은 다시 열지 않는다.

- odd/even midpoint median
- MAD semantics
- ties
- exact ECDF support
- zero-MAD fail-close
- window boundary
- candidate collision
- all-later / latest
- common-N deterministic semantics
- chronology hash
- exact rational comparison

---

# 18. 현재 Gate 상태

~~~text
R5R-G0
=
PASS

R5R-G1
=
BLOCKED_PENDING_EVALUATION_DATA_BINDING

R5R-G2
=
PASS

R5R DETERMINISTIC CONTRACT REVIEW
=
PASS

R5R-G3
=
BLOCKED_PENDING_R5R_POLICY_RESOLUTION

R5R-G4
=
NOT AUTHORIZED

R5R REFERENCE ADEQUACY EVALUATION
=
NOT AUTHORIZED

IMPLEMENTATION
=
NOT AUTHORIZED
~~~

주의:

Frozen Review V2에는 R5R-G3가 BLOCKED_PENDING_S6B_R5R_POLICY_AMENDMENT로 기록돼 있다.

이 통합 baseline에서는 다음 정책 작업을 여러 작은 P단계로 분해하지 않고 하나의 제품 중심 resolution 작업으로 묶기 때문에, 프로젝트 계획상 의미를 BLOCKED_PENDING_R5R_POLICY_RESOLUTION으로 요약한다.

Frozen Review V2 자체를 수정하거나 과거 기록을 재라벨하지 않는다.

---

# 19. 이미 해결된 것 — 특별한 defect가 없으면 다시 열지 않는다

## DO NOT REOPEN

- R5R observed-path target class
- T_EMP formula
- L_EMP formula
- S_EMP formula
- midpoint median / MAD definition
- w(n)=ceil(n/10)
- 18-anchor prospective grid
- integer collision rule
- all-later
- latest-state inclusion
- PREBOUND_COMPLETE_JOINT_CHRONOLOGY
- R5R_JOINT_CHRONOLOGY_HASH_V1
- R5R_EXACT_RATIONAL_V1
- outcome-driven tuning 금지
- Holdout lock 원칙

다만 실제 contract defect, 재현성 오류, leakage 위험이 발견되면 별도 BR을 허용한다.

---

# 20. 아직 해결되지 않은 것

현재 남은 핵심은 다음이다.

## 20.1 Reference reuse purpose

StockScope가 이 empirical reference를 실제로 어디에 사용할 것인지 아직 최종 고정되지 않았다.

예:

- empirical cumulative/cutoff probability
- median
- MAD / scale normalization
- 그 외 특정 판단 출력

## 20.2 Metric activation

현재 V2는 T/L/S 모두 gate다.

하지만 실제 제품 용도를 확인한 뒤 각 metric을:

~~~text
GATE
DIAGNOSTIC
NOT_USED
~~~

중 하나로 확정해야 한다.

이 결정은 **제품 목적 기반**이어야 한다.

현재 PASS/FAIL이나 passing N을 보고 정하지 않는다.

## 20.3 Initial operational tolerance

필요한 active gate에 대해서만 합리적인 초기 tolerance가 필요하다.

목표:

~~~text
유일한 수학적 정답 증명
❌

제품 용도에 맞고 설명 가능한 초기 운영 기준
✅
~~~

이다.

## 20.4 Evaluation data binding

Policy 이후 실제 evaluation payload identity / chronology binding을 완료해야 한다.

## 20.5 Implementation

Evaluator와 deterministic verification을 코드로 내려야 한다.

---

# 21. 고급 설계 검토에서 채택한 원칙

2026-10-05 별도 고급 설계 검토의 핵심 중 다음을 채택한다.

### 채택 1

Tolerance 숫자를 먼저 고르지 않는다.

먼저:

~~~text
무엇을 reuse하는가
→
어느 정도 output 변화가 허용되는가
→
어떤 metric이 실제 gate인가
~~~

를 정한다.

### 채택 2

모든 metric을 무조건 gate로 유지할 필요는 없다.

예:

~~~text
empirical probability reference 사용
→ T_EMP가 핵심 gate 후보

median reuse
→ L_EMP gate 후보

MAD/scale reuse
→ S_EMP gate 후보
~~~

### 채택 3

Synthetic study는 metric 동작과 blind spot을 확인하는 도구다.

Synthetic PASS 비율을 보고 threshold를 고르는 도구가 아니다.

### 채택 4

Common-N을 minimum sample size처럼 과장하지 않는다.

### 채택 5

Governance는 StockScope 규모에 맞게 단순화한다.

---

# 22. 고급 검토에서 그대로 채택하지 않는 것

다음은 자동으로 도입하지 않는다.

- P1~P9를 모두 별도 phase/document로 생성
- 처음부터 모든 synthetic family를 대규모 실행
- 은행 수준의 조직·위원회 구조
- 실제 행동 차이가 없는 GREEN/AMBER/RED 다단계 체계
- 분석 complexity 자체를 품질의 증거로 취급

필요한 경우에만 추가한다.

---

# 23. Synthetic sensitivity의 앞으로의 수준

필요하다면 최소한 다음부터 시작한다.

- pure location shift
- pure scale shift
- tail / outlier movement
- lattice / ties stress
- location + scale

목적:

~~~text
metric이 어떤 변화에 어떻게 반응하는지 이해
~~~

목적이 아닌 것:

~~~text
Development가 PASS하도록 tau를 찾기
earliest common-N을 좋게 만들기
특정 horizon 실패율을 맞추기
~~~

필요한 operational interpretation이 이 최소 study로 충분히 설명되면 연구를 더 확장하지 않는다.

---

# 24. Policy governance의 최소 구조

필요한 기능은 세 가지다.

1. **Policy Owner**
   - 무엇을 어느 정도 허용할지 결정
2. **Method Review**
   - metric이 그 목적과 맞는지 검토
3. **Approval**
   - 적용 범위와 제한을 받아들이고 정책 발효

그러나 세 사람이 반드시 따로 있을 필요는 없다.

작은 프로젝트에서는 Owner / Approver 역할을 한 사람이 맡을 수 있다.

AI는 설계 초안, 계산, 반례 탐색, 리뷰 보조를 할 수 있지만 최종 human approval authority를 대체하지 않는다.

별도 위원회 수준으로 확장하지 않는다.

---

# 25. 문서 운영 원칙

앞으로는:

~~~text
하나의 실제 작업
→ 가능하면 하나의 핵심 문서
~~~

로 간다.

BR 분기는 다음에만 사용한다.

- contract contradiction
- 실제 계산 defect
- 재현성 failure
- data leakage 위험
- 구현을 진행할 수 없는 genuine blocker

단순히 더 엄밀하게 적을 수 있다는 이유만으로 BR을 만들지 않는다.

---

# 26. Artifact 분류

## ACTIVE — 현재 작업에서 직접 참조

| 역할 | Artifact |
|---|---|
| Method | docs/contracts/NEXT6E_S6A_R5R_METHOD_CONTRACT_V2.json |
| Candidate domain | docs/contracts/NEXT6E_S6A_R5R_CANDIDATE_DOMAIN_V1.json |
| Window | docs/contracts/NEXT6E_S6A_R5R_WINDOW_PROFILE_V1.json |
| Deterministic review | docs/reviews/NEXT6E_S6A_R5R_DETERMINISTIC_REVIEW_RESULT_V2.json |
| MUR3 ambiguity resolution | docs/reviews/NEXT6E_S6A_R5_MUR3_BR1_R5R_계약_모호성_해소_2026-10-05.md |
| Targeted deterministic fixtures | docs/fixtures/NEXT6E_S6A_R5R_MUR3_BR1_TARGETED_FIXTURES_V1.json |
| Current baseline | 이 문서 |

## LINEAGE — 설계 이유를 확인할 때만 참조

| 단계 | 의미 |
|---|---|
| GA2 / GA2-BR1 | R5 actual-process binding이 왜 막혔는지 |
| MUR1 | R5R architecture를 왜 선택했는지 |
| MUR2 | R5R target / window / candidate structure를 어떻게 고정했는지 |
| MUR3 | deterministic edge-case review |
| MUR3-BR1 | 세 contract ambiguity 해소 |

대표 lineage artifacts:

~~~text
docs/reviews/NEXT6E_S6A_R5_MODEL_USE_BINDING_ROUTE_V1.json

docs/reviews/NEXT6E_S6A_R5_METHOD_USE_REDESIGN_DECISION_V1.json

docs/NEXT6E_S6A_R5_MUR2_관측경로_경험적안정성_계약설계_2026-10-05.md
~~~

## HISTORICAL / SUPERSEDED

- R4 population-law method / reviews
- legacy R5 concentration-band method
- NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V2
- NEXT6E_S6A_R5_CONCENTRATION_BAND_V1
- GA2 blocked actual-process results
- R5R Method Contract V1
- Deterministic Review Result V1

이들은 삭제 대상이 아니다.

History / audit / 설계 이유 확인용이다.

하지만 새 구현의 authoritative source로 사용하지 않는다.

---

# 27. Historical artifact 사용 규칙

새 작업은 먼저 이 문서의 ACTIVE 목록을 사용한다.

Historical artifact는 다음 상황에서만 연다.

- 왜 현재 설계가 선택됐는지 설명이 필요함
- 새로운 변경이 과거 실패를 반복하는지 확인해야 함
- lineage / audit evidence가 필요함

Historical artifact에 더 복잡한 식이 있다는 이유로 현재 설계를 되돌리지 않는다.

---

# 28. DEV / Reference Adequacy / Holdout 원칙

현재 기준:

~~~text
DEV
=
정해진 stage에서만 명시적으로 사용

Reference Adequacy
=
현재 미실행

passing N
=
정책 설계 근거로 사용 금지

forward envelope
=
정책 설계 근거로 사용 금지

Holdout
=
LOCKED
~~~

Holdout은 명시적 허가 전 내용 열람, 검색, metadata 탐색, hash 확인, 존재 확인을 위한 탐색도 하지 않는다.

---

# 29. JEV의 위치

JEV는 StockScope의 메인 목적이 아니다.

정확한 관계:

~~~text
StockScope 제품 목표
        ↓
분석 / 검증 architecture
        ↓
R5R / policy / implementation
        ↓
JEV execution
~~~

반대로:

~~~text
JEV를 PASS시키기 위해
StockScope 설계를 맞춤
~~~

으로 가지 않는다.

---

# 30. JEV를 빨리 사용하되 주객을 바꾸지 않는다

JEV를 실제로 빨리 실행해 보는 것은 가치가 있다.

이유:

- 설계가 실제 실행에서 어떻게 보이는지 확인
- 구현 문제를 조기에 발견
- 지나치게 이론적인 설계를 현실과 연결

하지만 다음은 금지한다.

- JEV 결과에 맞춰 threshold 사후 변경
- JEV PASS를 위해 target 의미 완화
- JEV 자체를 사용자-facing 핵심 기능처럼 취급
- JEV가 늦어진다는 이유로 leakage 방지나 identity 검증 제거

---

# 31. 다음 작업 — 기존 세분화를 압축

기존 검토에서는 정책 해결을 여러 단계로 세분화할 수 있었지만, 현재 StockScope 규모에서는 각각 별도 task로 만들지 않는다.

다음 하나의 통합 작업으로 묶는다.

~~~text
NEXT-6E-S6B-R5R-POLICY

Reference Use
+
Metric Activation
+
Initial Policy Resolution
~~~

이 작업에서 한 번에 답할 질문:

1. StockScope가 empirical reference에서 실제로 재사용할 출력은 무엇인가?
2. T_EMP / L_EMP / S_EMP 중 무엇이 GATE / DIAGNOSTIC / NOT_USED인가?
3. Active gate의 합리적인 초기 operational tolerance는 무엇인가?
4. 그 tolerance의 최소 synthetic / analytical 근거는 무엇인가?
5. 누가 Owner / Reviewer / Approver 기능을 맡는가?
6. 현재 Method V2의 ALL_METRICS_AND를 유지할지, 제품 목적상 작게 version-up할지?

---

# 32. 다음 정책 작업의 복잡도 제한

기본 제한:

- 핵심 문서 1개
- 필요한 경우 small machine-readable policy artifact 1개
- 처음부터 대규모 synthetic 연구 금지
- 실제 사용 목적에 필요한 metric만 다룸
- Development 결과 / passing N을 보지 않고 기준 설정
- genuine blocker가 없으면 별도 BR 생성 금지

목표는 **정책을 끝내는 것**이지 정책 연구 프로그램을 만드는 것이 아니다.

---

# 33. 정책 이후 예상 작업

Policy resolution이 끝나면 다음 작업은 가능한 한 묶는다.

~~~text
R5R evaluator implementation
+
deterministic fixture verification
+
evaluation data binding
~~~

Implementation 중 실제 contract defect가 발견되면 그때만 좁은 BR을 만든다.

---

# 34. 그 다음

필수 gate가 닫히면 JEV 실제 실행으로 진입한다.

JEV 실행 결과:

- PASS면 다음 validation / product integration으로 연결
- NOT_SUPPORTED면 정상 negative result로 취급
- BLOCKED면 명시적 blocker만 해결

NOT_SUPPORTED를 억지로 PASS로 바꾸기 위한 tuning은 하지 않는다.

---

# 35. CURRENT STATE

~~~text
Architecture
=
R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1

Target
=
NEXT6E_S6A_R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1

Method
=
NEXT6E_S6A_R5R_EMPIRICAL_STABILITY_V1

Method Contract
=
V2 FROZEN

CandidateDomain
=
V1 FROZEN

Window
=
V1 FROZEN

Deterministic Contract Review
=
PASS

Evaluation policy
=
R5R_POLICY_V1 FROZEN

Policy tolerances
=
tau_T 0.10 / tau_L 0.50 / tau_S 0.25

R5R-G3
=
PASS

Evaluation data binding
=
PENDING

Implementation
=
NOT AUTHORIZED

Reference Adequacy evaluation
=
NOT AUTHORIZED

Holdout
=
LOCKED
~~~

---

# 36. FROZEN DECISIONS

~~~text
Observed-path claim class

T_EMP / L_EMP / S_EMP formulas

midpoint median / MAD

w(n)=ceil(n/10)

18-anchor grid

all-later

latest-state

joint chronology boundary

chronology SHA-256 semantics

exact rational numeric semantics
~~~

은 현재 기준선이다.

---

# 37. DO NOT REOPEN

특별한 defect가 없으면 다음 토론을 반복하지 않는다.

- population theorem으로 되돌아갈지
- alpha-mixing을 다시 맞춰볼지
- R5를 억지로 actual-process PASS로 만들지
- window를 DEV 결과에 맞춰 바꿀지
- anchor grid를 passing N에 맞춰 바꿀지
- exact rational 대신 float epsilon을 쓸지
- chronology row를 evaluator가 편의상 drop할지

이 문제들은 이미 충분히 검토됐다.

---

# 38. UNRESOLVED

현재 실제로 해결해야 하는 것은 다음이다.

~~~text
1. Evaluation data binding

2. R5R evaluator implementation

3. Deterministic implementation verification

4. JEV execution after G1/G4 PASS
~~~

이 목록 밖의 새 연구는 실제 blocker가 확인될 때만 추가한다.

---

# 39. POLICY RESOLUTION COMPLETE

현재 policy:

~~~text
NEXT6E_S6B_R5R_POLICY_V1

Reference Use
=
REFERENCE_CONTEXT
HISTORICAL_EVALUATION
SHADOW_RESEARCH
USER_INFORMATION

Metric Activation
=
T_EMP GATE
L_EMP GATE
S_EMP GATE

tau_T
=
0.10

tau_L
=
0.50

tau_S
=
0.25

R5R-G3
=
PASS
~~~

Method V2의 ALL_METRICS_AND 구조를 그대로 사용하므로 Method V3는 만들지 않았다.

정책 문서:

~~~text
docs/설계/
StockScope_NEXT6E_R5R_초기정책결정_2026-10-05.md

docs/contracts/
NEXT6E_S6B_R5R_POLICY_V1.json
~~~

# 40. NEXT TASK

~~~text
NEXT-6E-R5R-IMPLEMENT
~~~

범위:

~~~text
R5R evaluator implementation
+
deterministic fixture verification
+
evaluation dataset binding
~~~

목적:

> 현재 frozen R5R Method V2 + Policy V1을 코드로 구현하고 G1/G4를 닫는다.

그 다음 실제 JEV 실행으로 이동한다.

---

# 41. 이 기준선의 변경 규칙

이 문서를 변경해야 하는 경우:

- authoritative Method / Candidate / Window contract version 변경
- 제품 목적상 metric activation 변경
- target claim class 변경
- policy resolution 완료
- 실제 implementation에서 contract defect 발견
- JEV 이후 현재 개발 흐름에 영향을 주는 중대한 검증 결과 발생

단순 문구 개선을 이유로 baseline version을 계속 늘리지 않는다.

---

# 42. 최종 원칙

StockScope의 품질은 문서 수나 theorem 수로 결정되지 않는다.

좋은 상태:

~~~text
무엇을 계산하는지 명확하다.

무엇을 주장하지 않는지 명확하다.

데이터 leakage가 없다.

결과를 보고 기준을 바꾸지 않는다.

실패는 실패로 남긴다.

필요한 검증은 한다.

그 후 실제 제품 기능으로 연결한다.
~~~

R4/R5에서 얻은 엄밀성의 교훈은 보존한다.

R5R에서 얻은 재현성과 claim discipline도 보존한다.

그러나 앞으로의 우선순위는 다시:

> **StockScope가 사용자의 주식 판단을 더 잘 도와주는 실제 프로그램으로 발전하는 것**

에 둔다.
