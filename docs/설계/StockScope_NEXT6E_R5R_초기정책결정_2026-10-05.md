# StockScope NEXT-6E-S6B-R5R-POLICY — 초기 운영 정책 결정

작성일: 2026-10-05 (Asia/Seoul)  
단계: NEXT-6E-S6B-R5R-POLICY  
Baseline main: 0c9e2cb1a76df0186e4c4d62253cbcb5107fb044


## 현재 상태 주석 — 2026-10-06

이 문서의 gate 표는 **정책 결정 당시 상태**를 기록한다. 이후 IMPLEMENT 단계에서 DEV binding과 deterministic implementation verification이 완료되어 현재 effective state는 G0~G4 PASS다. 현재 상태는 `StockScope_NEXT6E_R5R_통합설계기준_2026-10-05.md`와 `StockScope_NEXT6E_R5R_구현및바인딩_2026-10-06.md`를 우선한다.

## 1. 결론

이번 작업에서 R5R의 초기 내부 운영 정책을 확정했다.

~~~text
NEXT-6E-S6B-R5R-POLICY
=
COMPLETE

Reference Use
=
FROZEN

T_EMP
=
GATE

L_EMP
=
GATE

S_EMP
=
GATE

tau_T
=
1/10
=
0.10

tau_L
=
1/2
=
0.50

tau_S
=
1/4
=
0.25

R5R-G3
=
PASS

Method Contract V3
=
NOT REQUIRED
~~~

이 정책은 외부 규제 기준이나 statistically optimal threshold가 아니다.

**StockScope의 현재 내부 reference / research-context 용도에 맞춘 설명 가능한 초기 운영 기준**이다.

---

## 2. 제품 사용범위 확인

현재 코드에서 Macro reference diagnostic의 허용 용도는 다음으로 제한돼 있다.

~~~text
REFERENCE_CONTEXT
HISTORICAL_EVALUATION
SHADOW_RESEARCH
USER_INFORMATION
~~~

반대로 다음 consumer는 명시적으로 금지돼 있다.

~~~text
SHOCK_CALIBRATION
SHOCK_DETECTION_APPROVAL
STRATEGY_INPUT
MARKET_REGIME_OVERRIDE
RISK_GATE
ORDER_DECISION
PRODUCTION_POLICY
AUTO_BUY
AUTO_SELL
~~~

MacroContext 역시 현재 approved shock calibration을 실행하지 않고, production decision approved 상태를 생성하지 않는다.

NEXT-6 macro architecture도 기본 완료범위를 Shadow / Evidence-only로 두며 Scanner 점수, Holdings plan, Watch, Production을 자동 변경하지 않는다.

따라서 이번 정책은:

> **reference를 내부 설명·연구·historical evaluation에서 재사용해도 되는지를 판단하는 정책**

이다.

투자 실행 policy가 아니다.

---

## 3. 왜 T/L/S를 모두 gate로 유지했는가

단순화를 위해 T만 gate로 두는 안도 검토할 수 있었지만 현재 코드와 맞지 않는다.

현재 expanding reference 연구는 이미 다음을 사용한다.

### Empirical probability

~~~text
empirical_percentile_le
positive_tail_fraction_ge
~~~

### Robust location / scale

~~~text
prior_median
prior_mad
robust_deviation_mad
~~~

또한 RATE_SPIKE candidate 연구 계열에는:

~~~text
EXPANDING_POSITIVE_TAIL_FRACTION
EXPANDING_ROBUST_MAD
~~~

가 모두 존재한다.

즉 현재 reference 의미는 probability 하나로만 제한돼 있지 않다.

따라서 현재 시점에서:

~~~text
T_EMP = GATE
L_EMP = GATE
S_EMP = GATE
~~~

를 유지한다.

이 결정 덕분에 기존 Method V2의:

~~~text
ALL_HORIZONS_AND
ALL_METRICS_AND
ALL_LATER_STATES
~~~

를 그대로 유지할 수 있다.

Method V3는 만들지 않는다.

---

## 4. Tolerance 결정 원칙

이번 tolerance는 다음 순서로 정했다.

~~~text
제품의 reference 의미
→
허용 가능한 해석 변화
→
간단한 analytical meaning
→
최소 synthetic boundary check
→
초기 운영값
~~~

사용하지 않은 것:

~~~text
DEV max metric
current passing N
current adequacy result
forward envelope result
Holdout
Production outcome
Strategy outcome
Holdings outcome
~~~

---

## 5. tau_T

Frozen value:

~~~text
tau_T
=
1/10
=
0.10
~~~

Metric:

~~~text
T_EMP
=
ECDF_SUP_DISTANCE
~~~

의미:

> anchor와 later empirical CDF의 모든 cutoff에서 empirical cumulative probability 차이를 최대 10 percentage points까지 동일 reference 범위로 허용한다.

즉:

~~~text
T_EMP <= 0.10
~~~

이면 cutoff probability의 absolute empirical movement가 10%p를 넘지 않는다.

이 값은 future probability error나 statistical confidence level이 아니다.

### 왜 10%p인가

현재 사용범위는 REFERENCE_CONTEXT / SHADOW_RESEARCH이며 직접 주문·risk gate·production 판단에는 사용할 수 없다.

따라서 지나치게 작은 변화까지 모두 invalidation시키기보다, reference probability interpretation이 눈에 띄게 달라졌다고 볼 수 있는 **단순하고 설명 가능한 초기 경계**로 10%p를 사용한다.

향후 probability reference가 실제 Strategy/Risk 입력으로 승격된다면 이 tolerance를 자동 승계하지 않는다.

---

## 6. tau_L

Frozen value:

~~~text
tau_L
=
1/2
=
0.50
~~~

Metric:

~~~text
L_EMP
=
|median_v - median_s| / MAD_s
~~~

의미:

> later median이 anchor median에서 anchor MAD의 절반까지 이동한 경우를 동일 robust-location reference 범위로 허용한다.

즉 0.50은:

~~~text
median 50% change
~~~

가 아니라:

~~~text
median 이동량
=
0.5 × anchor MAD
~~~

이다.

Robust-MAD candidate interpretation이 median을 기준으로 하기 때문에 L_EMP는 gate로 유지한다.

---

## 7. tau_S

Frozen value:

~~~text
tau_S
=
1/4
=
0.25
~~~

Metric:

~~~text
S_EMP
=
|MAD_v - MAD_s| / MAD_s
~~~

의미:

> later MAD가 anchor MAD에서 ±25% 범위 안에 있을 때 동일 robust-scale reference 범위로 허용한다.

Pure scale change라면:

~~~text
scale multiplier 1.25
→
S_EMP = 0.25
~~~

이므로 boundary pass다.

Scale이 50% 바뀌는 수준은 초기 동일-reference 정책에서는 허용하지 않는다.

---

## 8. 최소 synthetic boundary check

이번 synthetic check는 실제 데이터를 흉내내거나 최적 threshold를 찾기 위한 것이 아니다.

경계 의미만 확인했다.

### T_EMP

~~~text
0.05
→ WITHIN

0.10
→ WITHIN / boundary

0.20
→ EXCEEDS
~~~

### L_EMP

Pure location shift:

~~~text
0.25 MAD
→ WITHIN

0.50 MAD
→ WITHIN / boundary

1.00 MAD
→ EXCEEDS
~~~

### S_EMP

Pure scale multiplier:

~~~text
1.10
→ S=0.10
→ WITHIN

1.25
→ S=0.25
→ WITHIN / boundary

1.50
→ S=0.50
→ EXCEEDS
~~~

---

## 9. Blind spot 확인

중요한 반례도 정책에 남긴다.

작은 비율의 관측치를 매우 먼 tail로 이동하면:

~~~text
T_EMP
L_EMP
S_EMP
~~~

가 모두 tolerance 안에 남을 수 있으면서 tail magnitude 또는 mean이 크게 변할 수 있다.

따라서 이 정책은 다음을 승인하지 않는다.

~~~text
TAIL_MAGNITUDE_GUARANTEE
MEAN_STABILITY_GUARANTEE
FUTURE_PROBABILITY_GUARANTEE
INVESTMENT_OUTCOME_GUARANTEE
~~~

이것은 threshold를 더 엄격하게 만들 문제가 아니라 **R5R claim scope의 경계**다.

---

## 10. Metric combination

현재 정책:

~~~text
ALL_HORIZONS_AND
AND
ALL_METRICS_AND
AND
ALL_LATER_STATES
~~~

를 유지한다.

Weighted score는 만들지 않는다.

한 metric의 좋은 결과로 다른 metric violation을 상쇄하지 않는다.

---

## 11. Horizon-specific tolerance

현재는 h=1/5/10에 동일 tolerance를 사용한다.

~~~text
tau_T,h = 0.10
tau_L,h = 0.50
tau_S,h = 0.25
for all h in {1,5,10}
~~~

Horizon별 실패율이나 JEV 결과를 본 뒤 별도 tolerance를 만들지 않는다.

향후 horizon별 downstream use가 실제로 달라질 경우에만 새 policy version에서 분리할 수 있다.

---

## 12. Governance

Policy Owner:

~~~text
STOCKSCOPE_PROJECT_OWNER
~~~

Method Reviewer:

~~~text
AI_ASSISTED_METHOD_REVIEW_WITH_HUMAN_PROJECT_OWNERSHIP
~~~

Approval Authority:

~~~text
STOCKSCOPE_PROJECT_OWNER
~~~

별도 Risk Committee / Model Validation Board는 만들지 않는다.

현재 프로젝트 규모에는 필요 없다.

AI는 최종 approval authority가 아니다.

이번 policy resolution 실행은 프로젝트 소유자가 명세 확인 후 작업 실행을 명시적으로 요청한 흐름에 따라 초기 내부 정책으로 기록한다.

---

## 13. Policy artifact

Machine-readable policy:

~~~text
docs/contracts/NEXT6E_S6B_R5R_POLICY_V1.json
~~~

Policy ID:

~~~text
NEXT6E_S6B_R5R_INITIAL_OPERATIONAL_POLICY_V1
~~~

Policy class:

~~~text
INITIAL_OPERATIONAL_POLICY
~~~

적용범위:

~~~text
INITIAL_INTERNAL_REFERENCE_VALIDATION
~~~

---

## 14. 정책 변경 규칙

다음은 tolerance 변경 근거가 아니다.

~~~text
JEV FAIL

common-N이 늦음

특정 horizon이 자주 실패

현재 결과가 마음에 들지 않음

PASS율이 낮음
~~~

변경 가능 근거:

- reference use scope 변경
- metric definition 변경
- target 변경
- window/horizon 의미 변경
- feature definition 변경
- 새 downstream decision consumer 승인
- 실제 implementation defect
- 새로운 outcome-independent product requirement

---

## 15. 기존 Method V2와 관계

Method Contract V2는 변경하지 않는다.

현재 V2가 이미:

~~~text
T_EMP
L_EMP
S_EMP
ALL_METRICS_AND
~~~

를 요구하므로 이번 policy가 정확히 그 interface를 채운다.

따라서:

~~~text
Method V3
=
NOT REQUIRED
~~~

이다.

---

## 16. Gate 상태

정책 완료 후 effective project state:

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

R5R Deterministic Contract Review
=
PASS

R5R-G3
=
PASS

R5R-G4
=
NOT_AUTHORIZED_PENDING_IMPLEMENTATION_VERIFICATION

R5R Reference Adequacy Evaluation
=
NOT_AUTHORIZED
~~~

Frozen Method V2 내부의 과거 G3 문자열은 historical contract state로 수정하지 않는다.

새 Policy V1 binding이 현재 effective G3 상태를 PASS로 만든다.

---

## 17. 접근 경계

이번 작업에서:

~~~text
DEV
=
NOT ACCESSED

Reference Adequacy
=
NOT ACCESSED

passing N
=
NOT ACCESSED

forward envelope
=
NOT ACCESSED

Holdout
=
LOCKED / NOT ACCESSED

runtime DB
=
NOT ACCESSED

Production
=
NONE
~~~

이다.

Repo의 설계/코드 structure만 확인했다.

---

## 18. 남은 작업

정책 설계는 이제 끝낸다.

다음 작업:

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

가능하면 하나의 작업으로 묶는다.

실제 contract defect가 발견될 때만 좁은 BR을 만든다.

---

## 19. JEV 위치

구현과 binding이 끝나서 G1/G4가 PASS하면 그 다음 실제 JEV 실행으로 간다.

JEV는:

~~~text
StockScope의 목표
❌

R5R 검증구조의 실제 실행단계
✅
~~~

이다.

JEV 결과가 NOT_SUPPORTED라고 해서 이번 policy를 자동 완화하지 않는다.

---

## 20. 최종 상태

~~~text
NEXT-6E-S6B-R5R-POLICY
=
COMPLETE

Reference Use
=
FROZEN

Metric Activation
=
T/L/S ALL GATE

tau_T
=
0.10

tau_L
=
0.50

tau_S
=
0.25

Method V3
=
NOT REQUIRED

R5R-G3
=
PASS

Next
=
NEXT-6E-R5R-IMPLEMENT
~~~
