# StockScope NEXT-6E-S6A-R5-D2E — Final Method Contract Freeze

작성일: 2026-10-05, Asia/Seoul  
단계: NEXT-6E-S6A-R5-D2E  
문서 성격: R5 statistical method 최종 설계 계약 동결. 구현/DEV/Reference Adequacy 실행 문서가 아니다.

## 1. 쉬운 결론

R5에서 사용할 통계 방법의 **설계 자체는 이제 고정됐다.**

지금까지 따로 정리했던:

~~~text
18개 prospective anchor
+
local time-varying CDF
+
backward local-linear estimator
+
finite-memory dependence
+
all-later simultaneous concentration band
+
latest-state
+
TAIL / median / MAD / location / scale projection
~~~

을 하나의 method identity로 묶고, 변경 시 새 contract version이 필요하도록 freeze했다.

하지만 이것은:

~~~text
실제 StockScope 데이터에 사용 승인 완료
~~~

와 같은 뜻이 아니다.

실제 사용 전에는 독립 theorem review, actual-process model-use acceptance, numerical profile, alpha_stat governance가 별도로 통과해야 한다.

## 2. Final Method Identity

~~~text
method_id
=
NEXT6E_S6A_R5_LOCAL_REFERENCE_CONCENTRATION_V1

contract
=
NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V1

status
=
METHOD_CONTRACT_FROZEN
~~~

Design hash:

~~~text
351ba2d22352da821b5b3c7711dccc6553745945acd2c16c1b78678bb5a5f432
~~~

Final contract semantic SHA256:

~~~text
6651a174e4b1c2cb92395bb9a2f3b122f49412a07f8b533f764be7cd48f89424
~~~

## 3. Bound child contracts

### CandidateDomain V2

~~~text
NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2

semantic SHA256
=
e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09

status
=
FROZEN
~~~

Core identity:

~~~text
18 nominal anchors
j/20, j=2,...,19
N_j=ceil(j*n/20)
all-later retained
latest-state required
common-N =
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR
~~~

### ConcentrationBand V1

~~~text
NEXT6E_S6A_R5_CONCENTRATION_BAND_V1

semantic SHA256
=
8a7097992b1fb89478a5d6079df55cc89c39385b6762b9b945ecc19c966f3c6d

status
=
THEOREM_DESIGN_FROZEN
~~~

Core identity:

~~~text
BACKWARD_DISCRETE_LOCAL_LINEAR_CDF
+
PROJECT_EXPLICIT_FINITE_MEMORY_BLOCKING
+
RESIDUE_CLASS_HOEFFDING
+
DETERMINISTIC_TAIL_ENVELOPE
+
GENERAL_CDF_BAND_INVERSION
~~~

### Consolidated draft

~~~text
NEXT6E_S6A_R5_METHOD_CONSOLIDATED_V1

semantic SHA256
=
1aa3664d921544a4eb1e2ab24669bc1da46f544b653caa6848c42db8aa38255d

status
=
READY_FOR_FINAL_METHOD_FREEZE
~~~

D2E consumes this draft into the final frozen contract.

## 4. Frozen statistical target

~~~text
target_id
=
NEXT6E_S6A_R5_LOCAL_TIME_REFERENCE_LAW_DRIFT_V1
~~~

For h in {1,5,10}:

~~~text
T_h(s,v)
=
sup_x |F_h(v,x)-F_h(s,x)|

L_h(s,v)
=
|m_h(v)-m_h(s)| / d_h(s)

S_h(s,v)
=
|d_h(v)-d_h(s)| / d_h(s)
~~~

Median:

~~~text
midpoint generalized median
~~~

Scale:

~~~text
raw midpoint MAD
~~~

Atomic lattice and ties remain part of the model object.

## 5. Frozen estimator

~~~text
w_n
=
ceil(n^(1-beta))

a_{r,w}
=
2(2w-1-3r)
/
[w(w+1)]

Ftilde_h,t(x)
=
sum_{r=0}^{w-1}
a_{r,w}
I{X^h_{t-r}<=x}
~~~

Exact design properties:

~~~text
sum a_r = 1
sum r a_r = 0
backward only
signed weights
latest state uses no future observation
~~~

The final method does not implement jitter or randomized distributional transforms.

## 6. Frozen concentration architecture

~~~text
architecture
=
R5_CONSERVATIVE_LOCAL_CDF_CONCENTRATION_V1
~~~

The primary calibration path is not Gaussian/bootstrap.

It uses:

~~~text
finite-memory approximation
→
m-dependent residue classes
→
Hoeffding
→
family union bound
~~~

with explicit width.

Finite-memory depth:

~~~text
d_n
=
max(
 1,
 ceil(
  log(16 p_n C_dep n / alpha_stat)
  /
  (-log rho)
 )
)
~~~

Stochastic width:

~~~text
epsilon_stoch
=
d_n
sqrt(
 (Q_w/2)
 log(4 p_n d_n/alpha_stat)
)
+
1/n
~~~

Bias width:

~~~text
epsilon_bias
=
4 C_ls n^(-zeta)
+
2 L2 (w_n/n)^2
~~~

Threshold radius:

~~~text
M_n
=
ceil(n^mu)
~~~

Tail width:

~~~text
tau_n
=
min(
 1,
 M_q/M_n^q
)
~~~

No covariance matrix, Gaussian critical value, bootstrap seed or hidden theorem constant is part of the frozen procedure.

## 7. Frozen assumption schema

One method-level structural assumption:

~~~text
iid innovation base
~~~

Actual-process model-use inputs:

~~~text
C_dep
rho

C_ls
zeta

L2

q
M_q
~~~

These are not populated by D2E.

They must later be accepted for one identical declared source/process scope.

Forbidden logic:

~~~text
finite diagnostic non-rejection
=
population assumption proof
~~~

and:

~~~text
choose assumption constants because
they improve Reference Adequacy
~~~

## 8. Frozen numerical-profile schema

Numerical inputs:

~~~text
beta
mu
~~~

Theorem domains:

~~~text
0 < beta < 1
mu > 0
~~~

They must be selected prospectively and outcome-independently.

Forbidden selection evidence:

~~~text
DEV passing rate
Reference Adequacy result
Holdout
Production outcome
~~~

Finite-sample eligibility remains mandatory.

## 9. Statistical / risk governance boundary

Statistical family error alpha_stat is governance-owned and must satisfy:

~~~text
0 < alpha_stat < 1
~~~

Operational movement tolerances remain separate:

~~~text
tau_T
tau_L
tau_S
~~~

and are owned by S6B risk governance.

D2E does not assign any numeric value.

S6B remains:

~~~text
POLICY_DESIGNED
G-B = BLOCKED
~~~

until numeric policy entries and approval authority are established.

## 10. Frozen structural eligibility

A method evaluation is structurally eligible only when:

~~~text
w_n >= 2

w_n <= N_min(n)=ceil(n/10)

d_n <= w_n

candidate N is an effective CandidateDomain V2 anchor

N < n

later state exists

joint horizons are available

model-use inputs are bound

beta/mu profile is approved

alpha_stat is approved
~~~

Otherwise the corresponding fail-closed state is returned.

## 11. Frozen functional projections

### CDF

Coverage-preserving monotone outer envelope.

### Median

General CDF-band inversion:

~~~text
I_m
=
[
 q^-_{U*}(1/2),
 q^+_{L*}(1/2)
]
~~~

### MAD

Center-aware general CDF-band inversion from H_low / H_up.

### TAIL

Difference-band pointwise absolute interval followed by supremum.

### Location / scale

Interval-distance numerator bounds divided by anchor MAD interval only when the anchor denominator is separated from zero.

If not:

~~~text
ANCHOR_SCALE_ZERO_NOT_EXCLUDED
~~~

## 12. Final failure-code set

~~~text
MODEL_PARAMETER_BINDING_MISSING
MODEL_USE_SCOPE_MISMATCH
INSUFFICIENT_LOCAL_WINDOW_DOMAIN
FINITE_MEMORY_DEPTH_EXCEEDS_WINDOW
EMPTY_PROJECTED_CDF_BAND
ANCHOR_SCALE_ZERO_NOT_EXCLUDED
OUTSIDE_R5_APPROVED_CANDIDATE_GRID
NO_ELIGIBLE_GRID_ANCHOR
STRUCTURALLY_INELIGIBLE_NO_LATER_STATE
NUMERICAL_PROFILE_UNBOUND
STATISTICAL_ALPHA_UNBOUND
POLICY_TOLERANCE_UNBOUND
THEOREM_REVIEW_NOT_APPROVED
METHOD_HASH_MISMATCH
~~~

These are not automatically converted to adequacy FAIL.

## 13. Gate structure

### G-A0 — Method Freeze

~~~text
status
=
PASS
~~~

Requirement:

> Frozen final method contract and all bound hashes are internally valid.

### G-A1 — Independent Theorem Review

~~~text
status
=
BLOCKED_PENDING_REVIEW
~~~

Required artifact:

~~~text
docs/templates/NEXT6E_S6A_R5_THEOREM_REVIEW_V1.json
~~~

### G-A2 — Actual-Process Model Use

~~~text
status
=
BLOCKED_PENDING_MODEL_USE
~~~

Required artifact:

~~~text
docs/templates/NEXT6E_S6A_R5_MODEL_USE_APPROVAL_V1.json
~~~

### G-A3 — Numerical Profile

~~~text
status
=
BLOCKED_PENDING_PROFILE
~~~

Required artifact:

~~~text
docs/templates/NEXT6E_S6A_R5_NUMERICAL_PROFILE_V1.json
~~~

### G-A4 — Statistical Governance

~~~text
status
=
BLOCKED_PENDING_ALPHA
~~~

Requires approved alpha_stat for this exact method/target identity.

### Overall G-A

~~~text
G-A
=
BLOCKED
~~~

until G-A0...G-A4 all PASS.

### G-B

~~~text
G-B
=
BLOCKED
~~~

under existing S6B governance state.

## 14. Theorem-review template

Created:

~~~text
docs/templates/NEXT6E_S6A_R5_THEOREM_REVIEW_V1.json
~~~

The independent reviewer must review P1-P8, including:

- finite-memory approximation;
- iid-block implication;
- signed-weight Hoeffding derivation;
- probability factors;
- bias constants;
- tail envelope;
- CDF projection;
- general median/MAD inversion;
- TAIL/location/scale interval mapping.

Allowed final verdict:

~~~text
PASS
BLOCKED
REJECTED
~~~

No review verdict automatically authorizes implementation.

## 15. Model-use template

Created:

~~~text
docs/templates/NEXT6E_S6A_R5_MODEL_USE_APPROVAL_V1.json
~~~

Required bound inputs:

~~~text
C_dep
rho
C_ls
zeta
L2
q
M_q
~~~

Every entry must carry:

~~~text
value_or_bound
scope
source
justification
review_status
approval_reference
~~~

and all must refer to one consistent source/process scope.

## 16. Numerical-profile template

Created:

~~~text
docs/templates/NEXT6E_S6A_R5_NUMERICAL_PROFILE_V1.json
~~~

It freezes the approval structure for:

~~~text
beta
mu
~~~

without choosing their values.

The profile must verify structural eligibility over its declared supported n domain.

## 17. Change control

A new final method contract version is required for:

~~~text
statistical target change
estimator formula change
dependence-assumption family change
concentration formula change
CandidateDomain change
all-later scope change
latest-state removal/change
median/MAD functional definition change
gate semantic change that changes evaluation eligibility
~~~

Historical artifacts are not retroactively relabeled.

## 18. Current execution boundary

During D2E:

~~~text
DEV
=
NOT ACCESSED / NOT RERUN

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

DB/runtime
=
NOT ACCESSED

backend/frontend/tests
=
UNCHANGED

Production impact
=
NONE
~~~

## 19. Implementation state

~~~text
D3 IMPLEMENTATION
=
NOT AUTHORIZED
~~~

Implementation requires at minimum:

~~~text
G-A
=
PASS
~~~

and an explicit implementation authorization.

Reference Adequacy evaluation additionally requires:

~~~text
G-B
=
PASS
~~~

plus implementation/numerical readiness.

## 20. Final D2E state

~~~text
NEXT-6E-S6A-R5-D2E
=
COMPLETE

Method ID
=
NEXT6E_S6A_R5_LOCAL_REFERENCE_CONCENTRATION_V1

Method state
=
METHOD_CONTRACT_FROZEN

Design hash
=
351ba2d22352da821b5b3c7711dccc6553745945acd2c16c1b78678bb5a5f432

Final contract semantic hash
=
6651a174e4b1c2cb92395bb9a2f3b122f49412a07f8b533f764be7cd48f89424

G-A0
=
PASS

G-A1
=
BLOCKED_PENDING_REVIEW

G-A2
=
BLOCKED_PENDING_MODEL_USE

G-A3
=
BLOCKED_PENDING_PROFILE

G-A4
=
BLOCKED_PENDING_ALPHA

G-A
=
BLOCKED

G-B
=
BLOCKED

Implementation
=
NOT AUTHORIZED

Reference Adequacy
=
UNRESOLVED

Holdout
=
LOCKED / NOT ACCESSED

Production impact
=
NONE
~~~

## 21. Next stage

The next method-side task is:

~~~text
NEXT-6E-S6A-R5-GA1
INDEPENDENT THEOREM REVIEW
~~~

It should populate the frozen theorem-review template against the exact final method/design hashes.

It must not change the method while reviewing it. A decisive defect that requires an architecture or method change returns BLOCKED/REJECTED and creates a new versioned design task instead.
