# StockScope NEXT-6E-S6A-R5-GA2-BR1 — Model-Use Evidence / Assumption Binding Route Resolution

작성일: 2026-10-05, Asia/Seoul
단계: NEXT-6E-S6A-R5-GA2-BR1
Baseline main: 10ebeb804d4bad614b9a02a0790312f433099747

## 1. 결론

GA2에서 실제 DGS10 process에 바인딩하지 못한 A_R5_01, C_dep/rho, C_ls/zeta, L2, q/M_q에 대해 실제 evidence route를 조사했다.

최종 상태:

~~~text
NEXT-6E-S6A-R5-GA2-BR1 = COMPLETE
MODEL_USE_BINDING_ROUTE = PARTIALLY_FEASIBLE
COMPLETE_AUDITABLE_ROUTE_FOR_CURRENT_R5 = NO
METHOD_USE_REDESIGN = REQUIRED
GA2-BR2 ACTUAL ASSUMPTION BINDING = NOT AUTHORIZED
~~~

이론적으로는 locally stationary causal / Markov / time-varying autoregressive model family에서 frozen assumptions가 함께 성립할 수 있다.
그러나 현재 StockScope DGS10 scope에 대해 frozen R5가 요구하는 structural representation과 population constants를 독립적으로 감사 가능하게 바인딩할 complete route는 확인되지 않았다.

## 2. Frozen identity

~~~text
Method = NEXT6E_S6A_R5_LOCAL_REFERENCE_CONCENTRATION_V1
Final Method Contract = NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V2
Semantic SHA256 = b1fffaeb292f1a7f513ca7d3376a0febbb4ad34aaa3bc4e6c63d951efb2a168c
Design SHA256 = 351ba2d22352da821b5b3c7711dccc6553745945acd2c16c1b78678bb5a5f432
~~~

BR1은 frozen method를 수정하지 않는다.

## 3. 외부 theory review

### Wu (2005)

Nonlinear system theory: Another look at dependence, PNAS 102(40), 14150-14154, DOI 10.1073/pnas.0506715102.

iid innovations에 대한 causal measurable functional과 physical/functional dependence measure를 제공한다. 이는 A_R5_01의 abstract architecture를 지지하지만 실제 DGS10가 어떤 Bernoulli-shift representation을 갖는지 또는 StockScope의 C_dep/rho를 제공하지 않는다.

### Dahlhaus, Richter & Wu (2019)

Towards a general theory for nonlinear locally stationary processes, Bernoulli 25(2), 1013-1044, DOI 10.3150/17-BEJ1011.

stationary approximation, derivative process 및 nonlinear nonstationary Markov models를 포함하는 locally stationary framework를 제공한다.

### Phandoidaen & Richter

Empirical process theory for nonsmooth functions under functional dependence.

locally stationary Bernoulli-shift representation, functional dependence, nonsmooth classes와 EDF inference가 함께 가능한 이론적 framework를 제공한다. 그러나 actual DGS10-specific C_dep, rho, C_ls, zeta, L2, M_q를 제공하지 않는다.

### Truquet

Local stationarity and time-inhomogeneous Markov chains 및 A perturbation analysis of some Markov chains models with time-varying parameters.

contracting / V-geometrically ergodic time-varying Markov kernels에서 local stationary approximation, mixing, invariant distribution regularity가 가능함을 보인다. Integer-valued autoregressive examples도 포함한다.

이들은 one-model theoretical route 후보를 제공하지만 DGS10에 대한 calibrated model-use certificate가 아니다.

## 4. Treasury-yield evidence

Covarrubias, Ewing, Hein & Thompson (2006), Modeling volatility changes in the 10-year Treasury, Physica A 369(2), 737-744, DOI 10.1016/j.physa.2006.01.074 는 daily 10-year Treasury yield changes의 volatility regime shifts를 직접 연구한다.

Bansal, Tauchen & Zhou, Federal Reserve FEDS 2003-21은 US Treasury term structure에서 regime-shift models가 yield transition dynamics를 설명하는 데 중요함을 보고한다.

이 자료들은 locally stationary model 자체를 반박하지 않지만 global smoothness를 실제 process에 당연한 가정으로 두는 것은 방어하기 어렵다는 evidence다.

## 5. Single-model 후보

~~~text
SM1 = LOCALLY_STATIONARY_CONTRACTING_CAUSAL_MODEL
~~~

가능한 구현은 time-varying AR, nonlinear time-varying Markov process, V-geometrically ergodic Markov kernel, smooth-parameter causal Bernoulli shift 등이다.

충분히 강한 조건을 주면 iid innovation representation, geometric forgetting, local approximation, time regularity, finite moments를 하나의 model에서 동시에 가질 수 있다.

하지만 StockScope에는 이런 generative model이 prospectively frozen되어 있지 않고, DGS10에 대한 independent parameter bounds도 없다.

새 generative model을 solely for constants 용도로 추가하면 evidence problem을 해결한다기보다 assumption을 새 layer로 옮기는 문제가 생긴다.

## 6. A_R5_01 — IID innovation representation

~~~text
Burden = CRITICAL
Route verdict = THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE
Redesign trigger = YES
~~~

Published theory는 iid-innovation causal representation이 넓고 유용한 class임을 보여준다. 그러나 유한한 observed DGS10 path로 해당 representation membership을 증명할 수 없다. Explicit model assumption으로 채택하는 것은 가능하지만 evidence binding과는 다르다.

## 7. A_R5_02 — C_dep / rho

Frozen requirement:

~~~text
sup ||Y_i-Y_i^[d]||_1 <= C_dep rho^d
~~~

Contracting Markov or stochastic-recursion model은 geometric forgetting을 제공할 수 있다. 특히 total-variation / Dobrushin contraction은 indicators 같은 bounded measurable functions와 구조적으로 잘 맞는다.

하지만 current R5는 actual DGS10에 대한 explicit uniform indicator finite-memory constants를 요구한다. Reviewed sources 어디에도 DGS10-specific C_dep/rho는 없으며 ACF/PACF fitting은 해당 functional-dependence object가 아니다.

~~~text
Burden = CRITICAL
Route verdict = THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE
Redesign trigger = YES
~~~

## 8. A_R5_03 — C_ls / zeta

Dahlhaus/Truquet 계열 theory는 smooth parameter paths와 contraction conditions 아래 local stationary approximation rates를 만들 수 있다.

따라서 구조적으로 불가능한 assumption은 아니다. 단 numerical C_ls/zeta는 explicit adopted model과 그 smoothness/contraction constants를 필요로 한다.

~~~text
Burden = HIGH
Route verdict = BINDABLE_WITH_DEDICATED_EVIDENCE_STAGE
Complete current binding = NO
~~~

이 route는 A_R5_01/A_R5_02와 동일 model을 사용해야 한다.

## 9. A_R5_04 — L2

Frozen requirement:

~~~text
sup_{h,u,x} |partial_u^2 F_h(u,x)| <= L2
~~~

Smooth time-varying parametric process에서는 이론적으로 가능하지만, actual DGS10에 대한 global uniform second-derivative bound를 제공하는 reviewed source는 없다.

10-year Treasury volatility regime-shift evidence와 기존 GA2 DEV time-variation diagnostics는 global L2를 casually accept하는 데 반대되는 material evidence다.

~~~text
Burden = CRITICAL
Route verdict = THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE
Redesign trigger = YES
~~~

향후 redesign에서는 weaker local regularity 또는 regime/piecewise-local regularity를 비교해야 한다.

## 10. A_R5_05 — q / M_q

Stable AR/Markov model과 finite-q-moment innovations를 명시하면 explicit moment bound를 만들 수 있어 다른 assumptions보다 tractable하다.

하지만 현재 feature contract에는 hard clipping/support bound가 없다. Sample maximum이나 sample moment는 population uniform bound가 아니다.

~~~text
Burden = MEDIUM
Route verdict = BINDABLE_WITH_DEDICATED_EVIDENCE_STAGE
Complete current binding = NO
~~~

동일 adopted process model의 innovation-tail/stability bound가 필요하다.

## 11. Route ledger

| Assumption | Burden | Route verdict | Complete current binding | Redesign trigger |
| --- | --- | --- | --- | --- |
| A_R5_01 iid innovation | CRITICAL | THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE | NO | YES |
| A_R5_02 C_dep/rho | CRITICAL | THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE | NO | YES |
| A_R5_03 C_ls/zeta | HIGH | BINDABLE_WITH_DEDICATED_EVIDENCE_STAGE | NO | CONDITIONAL |
| A_R5_04 L2 | CRITICAL | THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE | NO | YES |
| A_R5_05 q/M_q | MEDIUM | BINDABLE_WITH_DEDICATED_EVIDENCE_STAGE | NO | CONDITIONAL |

## 12. Single-model verdict

~~~text
SINGLE_MODEL_THEORETICAL_COMPATIBILITY = PASS
SINGLE_MODEL_ACTUAL_DGS10_BINDING = NOT_ESTABLISHED
~~~

즉 assumptions가 수학적으로 서로 모순되는 것은 아니다. 문제는 actual DGS10에 대해 그 model과 constants를 독립적으로 고정할 수 없다는 것이다.

## 13. 왜 PARTIALLY_FEASIBLE인가

모든 가능한 model에서 불가능하다는 뜻은 아니다. Literature에는 조건을 충분히 강하게 주면 requirements를 충족하는 model families가 존재한다.

그러나 StockScope가 요구하는 것은 theorem existence가 아니라 auditable actual-process binding이다. 현재 architecture에서는 complete route가 없다.

따라서:

~~~text
MODEL_USE_BINDING_ROUTE = PARTIALLY_FEASIBLE
METHOD_USE_REDESIGN = REQUIRED
~~~

가 가장 정확하다.

## 14. GA2-BR2 미승인

현재 상태에서 BR2를 시작하면 A_R5_01, C_dep, rho, C_ls, zeta, L2, q, M_q를 채워야 한다.

A_R5_01, A_R5_02, A_R5_04에 auditable route가 없으므로 BR2를 시작하면 DEV fitting, convenient model adoption 또는 guessed constants로 흐를 위험이 크다.

~~~text
GA2-BR2 = NOT AUTHORIZED
~~~

## 15. Redesign 방향 요구사항

다음 단계는 현재 A3 method를 억지로 rescue하는 것이 아니라 assumption burden이 낮은 architectures를 비교해야 한다.

필수 원칙:

1. observable/auditable quantities와 연결되는 assumptions 우선.
2. 독립적으로 bound할 수 없는 population constants 최소화.
3. Treasury regime variation 허용.
4. atomic/lattice data와 ties 유지.
5. prospective CandidateDomain semantics는 가능하면 유지.
6. all-later/latest-state 요구는 statistical support 가능 여부를 다시 평가.
7. bounded/robust transform으로 moment burden을 줄일 수 있는지 비교.
8. descriptive stability evidence와 probability guarantee를 분리.
9. nominally nonparametric method 아래 strong hidden generative model을 숨기지 않기.

비교 후보만 기록하며 이번 단계에서 선택하지 않는다:

~~~text
DIRECT_WEAK_DEPENDENCE_ROUTE
REGIME_OR_PIECEWISE_LOCALLY_STATIONARY_ROUTE
BOUNDED_TRANSFORM_FINITE_SAMPLE_ROUTE
TARGET_REDUCED_CONSERVATIVE_ROUTE
EXPLICIT_PARAMETRIC_MODEL_ROUTE
~~~

## 16. Access boundary

~~~text
Additional DEV diagnostics = NONE
Existing GA2 DEV diagnostics = CONTEXT ONLY
Reference Adequacy = NOT ACCESSED
Passing N = NOT ACCESSED
Forward envelope = NOT ACCESSED
Holdout = LOCKED / NOT ACCESSED
Runtime DB = NOT ACCESSED
Production = NONE
~~~

## 17. Final state

~~~text
NEXT-6E-S6A-R5-GA2-BR1 = COMPLETE
MODEL_USE_BINDING_ROUTE = PARTIALLY_FEASIBLE
A_R5_01 = THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE
A_R5_02 = THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE
A_R5_03 = BINDABLE_WITH_DEDICATED_EVIDENCE_STAGE
A_R5_04 = THEORETICALLY_POSSIBLE_BUT_NOT_AUDITABLY_BINDABLE
A_R5_05 = BINDABLE_WITH_DEDICATED_EVIDENCE_STAGE
GA2 = BLOCKED
GA2-BR2 = NOT AUTHORIZED
G-A = BLOCKED
Implementation = NOT AUTHORIZED
~~~

## 18. Next task

~~~text
NEXT-6E-S6A-R5-MUR1
METHOD-USE REDESIGN ARCHITECTURE COMPARISON
~~~

다음 단계는 lower-assumption architectures를 소수 후보로 비교한 뒤 한 route를 선택해야 한다. 새 theorem derivation이나 구현은 그 이후다.
