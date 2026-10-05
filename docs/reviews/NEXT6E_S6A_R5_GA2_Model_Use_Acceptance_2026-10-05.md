# StockScope NEXT-6E-S6A-R5-GA2 — Actual-Process Model-Use Acceptance

작성일: 2026-10-05, Asia/Seoul  
단계: NEXT-6E-S6A-R5-GA2  
문서 성격: frozen R5 method의 actual-process model-use acceptance 결과.  
Method ID: NEXT6E_S6A_R5_LOCAL_REFERENCE_CONCENTRATION_V1  
Final Method Contract: NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V2  
Final Contract semantic SHA256: b1fffaeb292f1a7f513ca7d3376a0febbb4ad34aaa3bc4e6c63d951efb2a168c  
Design SHA256: 351ba2d22352da821b5b3c7711dccc6553745945acd2c16c1b78678bb5a5f432

## 1. 쉬운 결론

GA2의 질문은 다음이었다.

> frozen R5 theorem assumptions를 실제 StockScope Development process scope에 적용해도 되는가?

결론:

~~~text
NEXT-6E-S6A-R5-GA2
=
BLOCKED

Actual-process model use
=
UNRESOLVED

G-A2
=
BLOCKED_INSUFFICIENT_MODEL_USE_EVIDENCE
~~~

이 결과는 frozen method의 수학이 틀렸다는 뜻이 아니다.

GA1에서 P1-P8 theorem chain은 PASS 상태다.

문제는 실제 DGS10 Development process에 대해 다음 population-level assumptions / bounds를 승인할 충분한 독립 근거가 현재 없다는 것이다.

~~~text
A_R5_01 IID innovation representation

C_dep / rho
geometric finite-memory indicator approximation

C_ls / zeta
uniform local marginal approximation rate

L2
uniform second-time-derivative bound

q / M_q
uniform population moment bound
~~~

DEV diagnostics는 supporting / contradiction evidence로만 사용했고, finite-sample non-rejection을 population truth로 승격하지 않았다.

## 2. Declared process scope

GA2에서 고정한 scope:

~~~text
provider
=
FRED

provider_series_id
=
DGS10

series_id
=
US_10Y_CONSTANT_MATURITY_YIELD

feature_contract
=
VN_NEXT6B_S1_MACRO_FEATURE_V1

dataset_contract
=
VN_NEXT6B_S2_CALIBRATION_DATASET_V1

split_role
=
DEVELOPMENT

usage_scope
=
REFERENCE_RESEARCH_ONLY

declared observation range
=
2016-01-04 through 2023-12-29 manifest scope

analysis rows
=
1999

required features
=
delta_bp_1obs
delta_bp_5obs
delta_bp_10obs

unit
=
BASIS_POINT
~~~

DEV file SHA256 verified:

~~~text
7b1dfe33537bb8855b9441b2aeb24338a13950abf8cdc186b2821898d47313f4
~~~

The dataset manifest itself carries:

~~~text
historical_evaluation_eligible
=
false

limitations
=
HISTORICAL_TIME_NOT_PROVEN

production_decision_approved
=
false
~~~

This limitation is preserved and is not overridden by GA2.

## 3. Evidence-use boundary

Before diagnostics, GA2 predeclared use of DEV only for:

1. process identity / feature construction;
2. tail / sample moment diagnostics;
3. serial-dependence / volatility-clustering diagnostics;
4. time-varying distribution / local-smoothness contradiction search.

GA2 did not use DEV for:

~~~text
Reference Adequacy

passing anchor

forward envelope

tau_T / tau_L / tau_S

beta / mu tuning

alpha_stat tuning

Production decision
~~~

Holdout was not accessed.

## 4. External theory boundary

Phandoidaen & Richter provide theory for locally stationary processes under functional dependence and nonsmooth function classes, including EDF applications and maximal inequalities.

That literature establishes that the frozen method's abstract process class is mathematically meaningful.

It does **not** establish that FRED DGS10 Development data specifically satisfies:

~~~text
iid innovation representation

geometric indicator finite-memory bound

a particular C_dep or rho

a particular C_ls or zeta

a finite approved L2 bound

a finite approved M_q bound
~~~

Those remain model-use questions.

Separate Treasury-yield literature has documented variance / volatility regime changes in changes of 10-year Treasury yields. This is contradiction-supporting context against casual structural-stability assumptions, not a direct theorem rejection of the R5 model class.

## 5. DEV diagnostic summary

### delta_bp_1obs

~~~text
n
=
1999

median
=
0 bp

sample MAD
=
3 bp

sample std
≈
5.345 bp

range
=
[-30, 29] bp

99% |value| quantile
=
16 bp

lag-1 raw ACF
≈
-0.011

lag-1 squared-value ACF
≈
0.228
~~~

### delta_bp_5obs

~~~text
median
=
0 bp

sample MAD
=
7 bp

sample std
≈
11.568 bp

range
=
[-56, 51] bp

99% |value| quantile
=
35 bp

lag-1 raw ACF
≈
0.795

lag-1 squared-value ACF
≈
0.661
~~~

### delta_bp_10obs

~~~text
median
=
1 bp

sample MAD
=
10 bp

sample std
≈
16.491 bp

range
=
[-84, 69] bp

99% |value| quantile
=
51 bp

lag-1 raw ACF
≈
0.900

lag-1 squared-value ACF
≈
0.806
~~~

The very high 5/10-observation autocorrelation is partly expected from overlapping feature construction and cannot be interpreted as an estimate of rho.

Squared-value dependence indicates material volatility clustering.

## 6. Time-variation diagnostics

Year-level 1obs sample standard deviations:

~~~text
2016  4.418
2017  3.545
2018  3.497
2019  4.346
2020  5.495
2021  4.279
2022  7.786
2023  7.487
~~~

Year-level 10obs sample standard deviations:

~~~text
2016  15.621
2017  10.060
2018  10.813
2019  14.030
2020  15.593
2021  11.192
2022  23.549
2023  22.185
~~~

Year-level 10obs sample MAD:

~~~text
2016  10
2017   7
2018   9
2019   9
2020   6
2021   8
2022  16
2023  17
~~~

These diagnostics show substantial time variation in scale.

They do not by themselves prove failure of local stationarity, but they prevent treating a stable-law assumption as self-evident.

## 7. Adjacent-window distribution diagnostic

GA2 used adjacent 125-observation windows only as a contradiction search.

Observed large two-window empirical-CDF distances included approximately:

~~~text
1obs
max diagnostic KS-like distance
≈
0.232

5obs
≈
0.352

10obs
≈
0.488
~~~

These are descriptive Development diagnostics only.

No statistical acceptance threshold was attached to them and they were not used to tune method parameters.

## 8. A_R5_01 — IID innovation base

Frozen statement:

~~~text
There exists an iid innovation sequence
supporting the finite-memory indicator representation.
~~~

Important:

~~~text
This does NOT mean observed DGS10 changes are iid.
~~~

A causal Bernoulli-shift process may be serially dependent.

However, neither:

- the FRED data contract;
- the StockScope feature construction;
- the Development record;
- the reviewed locally stationary empirical-process literature;

proves that the declared DGS10 scope admits the exact iid innovation representation required by the project proof.

DEV diagnostics cannot establish this representation.

Verdict:

~~~text
A_R5_01_IID_INNOVATION_BASE
=
UNRESOLVED
~~~

Reason code:

~~~text
BLOCKED_IID_REPRESENTATION_UNRESOLVED
~~~

## 9. A_R5_02 — Indicator finite-memory dependence

Required:

~~~text
sup
||Y_i-Y_i^[d]||_1
<=
C_dep rho^d

C_dep < infinity
0 < rho < 1
~~~

The observed autocorrelation structure is not the functional-dependence coefficient in the frozen assumption.

Therefore ACF fitting cannot validly produce C_dep or rho.

No independent source or construction-level proof currently supplies a conservative population bound.

Verdict:

~~~text
C_dep
=
UNBOUND

rho
=
UNBOUND

A_R5_02
=
UNRESOLVED
~~~

Reason:

~~~text
BLOCKED_FINITE_MEMORY_BOUND_UNRESOLVED
~~~

## 10. A_R5_03 — Local marginal approximation

Required:

~~~text
sup_{i,h,x}
|
P(X_i^h<=x)-F_h(i/n,x)
|
<=
C_ls n^(-zeta)
~~~

No construction-level theorem for the actual DGS10 scope supplies numerical:

~~~text
C_ls
zeta
~~~

The Development record can show time variation but cannot identify a uniform population approximation rate.

The manifest limitation:

~~~text
HISTORICAL_TIME_NOT_PROVEN
~~~

also prevents silently promoting the record to a fully validated chronological population-law scope.

Verdict:

~~~text
C_ls
=
UNBOUND

zeta
=
UNBOUND

A_R5_03
=
UNRESOLVED
~~~

Reason:

~~~text
BLOCKED_LOCAL_APPROXIMATION_RATE_UNRESOLVED
~~~

## 11. A_R5_04 — Time smoothness

Required:

~~~text
sup_{h,u,x}
|partial_u^2 F_h(u,x)|
<=
L2
~~~

The Development diagnostics show strong changes in volatility and local distributions, including the 2020 and 2022-2023 periods.

External Treasury-yield literature also documents volatility-regime changes / structural instability in 10-year Treasury yield dynamics.

These facts are contradiction-supporting evidence against casually assuming a small global smoothness bound.

They do not mathematically prove that no finite L2 exists for an appropriate locally stationary tangent-law representation.

But no approved numerical L2 upper bound is available.

Verdict:

~~~text
L2
=
UNBOUND

A_R5_04
=
UNRESOLVED
~~~

Reason:

~~~text
BLOCKED_TIME_SMOOTHNESS_UNRESOLVED
~~~

## 12. A_R5_05 — Uniform moment

Required:

~~~text
sup_{h,u}
E|Xtilde_h(u)|^q
<=
M_q
~~~

The finite DEV record has finite sample moments.

For example sample second moments:

~~~text
1obs
≈
28.56

5obs
≈
133.90

10obs
≈
272.49
~~~

and finite sample ranges.

However:

~~~text
finite sample moment
!=
population uniform upper bound
~~~

No independent population-tail model or source currently provides an approved q / M_q pair for the frozen process scope.

Verdict:

~~~text
q
=
UNBOUND

M_q
=
UNBOUND

A_R5_05
=
UNRESOLVED
~~~

Reason:

~~~text
BLOCKED_MOMENT_BOUND_UNRESOLVED
~~~

## 13. Cross-assumption consistency

No logical contradiction was found in the abstract frozen assumptions themselves.

A locally stationary causal Bernoulli-shift process with geometric functional dependence, time smoothness and finite moments can exist.

Therefore the method class is not rejected as mathematically empty.

But no single actual-process evidence package currently binds all required assumptions and constants to the DGS10 scope.

Verdict:

~~~text
CROSS_ASSUMPTION_THEORETICAL_COMPATIBILITY
=
PASS

ACTUAL_PROCESS_BINDING
=
UNRESOLVED
~~~

## 14. Model-use ledger

| Assumption | Required input | Result |
| --- | --- | --- |
| A_R5_01 IID innovation base | structural representation | UNRESOLVED |
| A_R5_02 finite memory | C_dep, rho | UNBOUND / UNRESOLVED |
| A_R5_03 local marginal approximation | C_ls, zeta | UNBOUND / UNRESOLVED |
| A_R5_04 time smoothness | L2 | UNBOUND / UNRESOLVED |
| A_R5_05 uniform moment | q, M_q | UNBOUND / UNRESOLVED |

No entry is ACCEPTED_FOR_MODEL_USE.

No entry is formally REJECTED_FOR_MODEL_USE.

## 15. Why GA2 is BLOCKED rather than REJECTED

REJECTED would require sufficient evidence that the frozen assumption family is incompatible with the declared actual process scope.

Current evidence does not establish that.

The correct result is:

~~~text
insufficient evidence / unbound population parameters
~~~

Therefore:

~~~text
G-A2
=
BLOCKED
~~~

rather than REJECTED.

## 16. Final aggregate verdict

~~~text
NEXT-6E-S6A-R5-GA2
=
BLOCKED

Actual-process model use
=
UNRESOLVED

A_R5_01
=
UNRESOLVED

C_dep
=
UNBOUND

rho
=
UNBOUND

C_ls
=
UNBOUND

zeta
=
UNBOUND

L2
=
UNBOUND

q
=
UNBOUND

M_q
=
UNBOUND

scope consistency
=
PASS FOR THE DECLARED REVIEW SCOPE

outcome independence
=
PASS

contradiction review
=
COMPLETE

limitations
=
RECORDED

G-A2
=
BLOCKED_INSUFFICIENT_MODEL_USE_EVIDENCE

G-A3
=
NOT AUTHORIZED TO PROCEED AS IF G-A2 PASSED

G-A
=
BLOCKED

Implementation
=
NOT AUTHORIZED
~~~

## 17. Frozen artifacts

GA2 does not modify:

~~~text
NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V2

NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2

NEXT6E_S6A_R5_CONCENTRATION_BAND_V1

NEXT6E_S6A_R5_THEOREM_REVIEW_RESULT_V2
~~~

## 18. Access record

~~~text
DEV
=
READ-ONLY ACCESSED FOR PREDECLARED MODEL-USE DIAGNOSTICS

DEV file SHA256
=
7b1dfe33537bb8855b9441b2aeb24338a13950abf8cdc186b2821898d47313f4

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

## 19. Next task

The next task is not GA3.

Required:

~~~text
NEXT-6E-S6A-R5-GA2-BR1
MODEL-USE EVIDENCE / ASSUMPTION BINDING RESOLUTION
~~~

That resolution must decide whether a defensible, prospectively specified evidence route exists for:

~~~text
A_R5_01
C_dep/rho
C_ls/zeta
L2
q/M_q
~~~

without using Holdout, Reference Adequacy outcomes, passing-anchor outcomes, or outcome-driven parameter fitting.

If no such route exists, the frozen R5 method requires model-use redesign rather than parameter guessing.
