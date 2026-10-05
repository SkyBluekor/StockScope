# StockScope NEXT-6E-S6A-R5-D2E1 — Conservative Local-CDF Concentration Band Design

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 theorem-design resolution 결과. 구현/DEV 평가 문서가 아니다.  
기준 main: 6c445f72c157b50143e86a6142bbf69089541a88  
Parent: NEXT-6E-S6A-R5-D2E0  
CandidateDomain V2 semantic SHA256: e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09

## 1. 쉬운 요약

이번 단계의 질문은 다음이었다.

> Bootstrap 없이도 StockScope가 실제로 계산할 수 있는 CDF 오차범위를 만들 수 있는가?

결론은 YES다.

다만 published maximal inequality의 숨은 universal constant를 그대로 사용하는 대신, StockScope의 구조에 맞는 explicit finite-memory blocking bound를 설계했다.

구조:

~~~text
locally stationary atomic indicator
        ↓
finite-memory approximation
        ↓
m-dependent bounded sequence
        ↓
residue-class independent blocks
        ↓
Hoeffding + family union bound
        ↓
explicit stochastic CDF width
        +
explicit local bias
        +
explicit tail envelope
        ↓
coverage-preserving CDF projection
~~~

이 설계는 covariance matrix, variance lower bound, Gaussian critical value, bootstrap을 요구하지 않는다.

## 2. 최종 판정

~~~text
NEXT-6E-S6A-R5-D2E1
=
COMPLETE

Architecture
=
R5_CONSERVATIVE_LOCAL_CDF_CONCENTRATION_V1

Primary concentration route
=
PROJECT_EXPLICIT_FINITE_MEMORY_BLOCKING_V1

Estimator
=
BACKWARD_DISCRETE_LOCAL_LINEAR_CDF

Stochastic width
=
EXPLICIT

Bias width
=
EXPLICIT

Tail width
=
EXPLICIT

All-later
=
SUPPORTED AT THEOREM-DESIGN LEVEL

Latest-state
=
SUPPORTED AT THEOREM-DESIGN LEVEL

CDF projection
=
APPROVED

TAIL projection
=
APPROVED

Median/MAD projection
=
RETAINED CONDITIONALLY

Bandwidth rate region
=
NONEMPTY

Band non-vacuity
=
PROVED ASYMPTOTICALLY

Hidden universal theorem constant
=
NONE IN FINAL PROJECT BOUND

External model-use parameters
=
BINDING STILL REQUIRED

R5 method
=
NOT YET FINAL-FROZEN

Implementation
=
NOT AUTHORIZED
~~~

## 3. Literature disposition

### Phandoidaen & Richter

Empirical process theory for nonsmooth functions under functional dependence, EJS 2022.

Useful facts:

- permits nonstationary Bernoulli-shift arrays;
- explicitly discusses localized EDFs;
- uses deterministic localization weights D_f,n;
- develops nonasymptotic maximal inequalities;
- allows nonsmooth indicator classes;
- provides the functional-dependence/local-stationarity framework used by R5.

However its maximal inequalities contain theorem constants and compatibility objects that are not directly numerical implementation inputs for StockScope.

Therefore it is used as foundational theory, not as the final executable width formula.

### Alvarez & Pinto

A maximal inequality for local empirical processes under weak dependence, 2023.

Useful facts:

- genuinely nonasymptotic;
- uniform over evaluation point, bandwidth and function class;
- permits increasing class complexity.

But the published theorem is stated under exponential strong mixing with a common marginal density for its localizing variable. This is not the final R5 atomic/local-time setup.

Therefore it is supporting evidence only.

### Final project choice

~~~text
published maximal inequality
→ framework validation

project explicit blocking lemma
→ executable band formula
~~~

## 4. Why a project-specific explicit lemma is used

D2E0 selected A3 specifically to avoid:

- covariance estimation;
- Gaussian non-degeneracy;
- bootstrap calibration;
- estimated residual centering.

Using an asymptotic statement of the form:

~~~text
sup error = O_p(rate)
~~~

would still not tell implementation what width to calculate.

The D2E1 route therefore exposes every term entering the probability bound.

No unspecified universal constant is required by the final project formula.

## 5. Local estimator

Let n be the aligned chronology length.

Choose:

~~~text
beta in (0,1)

w_n
=
ceil(n^(1-beta))

h_n
=
w_n / n
~~~

For each required chronology state t, use only:

~~~text
t,
t-1,
...,
t-w_n+1
~~~

No future observation is used.

For r=0,...,w-1 define:

~~~text
a_{r,w}
=
2(2w-1-3r)
/
[w(w+1)]
~~~

and:

~~~text
Ftilde_h,t(x)
=
sum_{r=0}^{w-1}
a_{r,w}
1{X^h_{t-r} <= x}
~~~

This is the exact discrete backward local-linear version whose limiting equivalent kernel is:

~~~text
K_-(z)
=
4 + 6z,
-1 <= z <= 0
~~~

## 6. Exact weight identities

For w>=2:

~~~text
sum_r a_{r,w}
=
1

sum_r r a_{r,w}
=
0
~~~

and:

~~~text
max_r |a_{r,w}|
<
4/w

sum_r |a_{r,w}|
<=
4

Q_w
:=
sum_r a_{r,w}^2
=
2(2w-1)
/
[w(w+1)]
<
4/w
~~~

Consequences:

1. constant local level is reproduced exactly;
2. first-order time drift cancels exactly at finite n;
3. signed weights are bounded explicitly;
4. concentration variance proxy is explicit.

## 7. Structural eligibility

The estimator is valid only if:

~~~text
w_n >= 2
~~~

and every required local time has a complete backward window.

Because the minimum approved CandidateDomain V2 anchor is:

~~~text
ceil(n/10)
~~~

D2E1 freezes:

~~~text
w_n
<=
ceil(n/10)
~~~

as a finite-sample structural eligibility condition.

If false:

~~~text
INSUFFICIENT_LOCAL_WINDOW_DOMAIN
~~~

No shortened early window is silently substituted.

## 8. Indicator finite-memory dependence contract

For horizon h and threshold x define:

~~~text
Y_i(h,x)
=
1{X_i^h <= x}
~~~

For d>=1 define:

~~~text
Y_i^[d](h,x)
=
E[
  Y_i(h,x)
  |
  epsilon_i,...,epsilon_{i-d+1}
]
~~~

D2E1 uses the explicit model contract:

~~~text
sup_{n,i,h,x}
||
Y_i(h,x)
-
Y_i^[d](h,x)
||_1

<=
C_dep rho^d
~~~

with:

~~~text
C_dep > 0
0 < rho < 1
~~~

This is an external model-use assumption.

It is not estimated from DEV in D2E1.

## 9. Relation to previous lattice functional-dependence work

The contract is consistent with the previous lattice coupling route.

For integer-valued X and coupled X*:

~~~text
|1{X<=x}-1{X*<=x}|
<=
1{X!=X*}
~~~

and because nonzero integer differences have magnitude at least one:

~~~text
P(X!=X*)
<=
E|X-X*|^r
~~~

Thus geometric physical dependence of the integer horizon process implies geometric indicator dependence under the corresponding moment/coupling assumptions.

A standard projection/telescoping argument then motivates the finite-memory form above.

This bridge remains subject to the later independent theorem-chain review.

## 10. Family index

A local CDF band only needs to be constructed once per:

~~~text
chronology state
× horizon
× threshold
~~~

The same local CDF band is reused by every approved anchor/later pair.

Therefore the anchor count does not multiply the raw stochastic family dimension.

For deterministic threshold radius M_n:

~~~text
p_n
<=
3 n (2 M_n + 1)
~~~

is a conservative upper bound.

This is smaller than the earlier bookkeeping bound:

~~~text
18 × n × 3 × thresholds
~~~

without changing CandidateDomain semantics.

## 11. Threshold route

D2E1 selects:

~~~text
H2
=
DETERMINISTIC_LATTICE_TRUNCATION
~~~

not because Gaussian tails are degenerate, but because it gives a completely explicit finite stochastic family.

Set:

~~~text
mu > 0

M_n
=
ceil(n^mu)
~~~

Central thresholds:

~~~text
x in Z
-M_n <= x <= M_n
~~~

## 12. Uniform moment contract and tail envelope

Require:

~~~text
sup_{h,u}
E |Xtilde_h(u)|^q
<=
M_q

q > 0
M_q < infinity
~~~

Then:

~~~text
tau_n
=
M_q / M_n^q
~~~

gives:

~~~text
F_h(u,x)
<=
tau_n
for x < -M_n
~~~

and:

~~~text
1-F_h(u,x)
<=
tau_n
for x > M_n
~~~

by Markov's inequality.

Thus the full CDF target is retained.

Tail thresholds are not deleted.

## 13. Local marginal approximation contract

Require:

~~~text
sup_{i,h,x}
|
P(X_i^h <= x)
-
F_h(i/n,x)
|

<=
C_ls n^(-zeta)
~~~

where:

~~~text
C_ls >= 0
zeta > 0
~~~

This explicitly separates the observed triangular-array marginal from the stationary local tangent law.

## 14. Second-order time smoothness contract

Require:

~~~text
sup_{h,u,x}
|
partial_u^2 F_h(u,x)
|
<=
L2
~~~

with:

~~~text
L2 < infinity
~~~

No density derivative in x is required.

Atomic jumps in x remain allowed.

The smoothness is only in rescaled time u.

## 15. Explicit bias bound

Using:

~~~text
sum a_r = 1

sum r a_r = 0
~~~

the constant and first-order time terms cancel exactly.

Using:

~~~text
sum |a_r| <= 4
~~~

gives:

~~~text
epsilon_bias
=
4 C_ls n^(-zeta)
+
2 L2 (w_n/n)^2
~~~

such that for every required central coordinate:

~~~text
|
E Ftilde_h,t(x)
-
F_h(t/n,x)
|
<=
epsilon_bias
~~~

No hidden big-O constant remains in this project bound.

## 16. Finite-memory approximation error

For one coordinate, let S denote the centered weighted indicator sum and S^[d] its finite-memory version.

The centered replacement satisfies:

~~~text
E|S-S^[d]|
<=
2
sum_r |a_r|
C_dep rho^d
<=
8 C_dep rho^d
~~~

For p_n coordinates:

~~~text
E max_j |S_j-S_j^[d]|
<=
8 p_n C_dep rho^d
~~~

Use half of alpha_stat for this approximation step.

Define:

~~~text
d_n
=
ceil(
 log(
   16 p_n C_dep n / alpha_stat
 )
 /
 (-log rho)
)
~~~

Then Markov's inequality yields:

~~~text
P(
 max_j |S_j-S_j^[d_n]|
 >
1/n
)
<=
alpha_stat/2
~~~

Therefore:

~~~text
epsilon_dep
=
1/n
~~~

is an explicit finite-memory approximation width.

## 17. m-dependent structure

Each:

~~~text
Y_i^[d_n]
~~~

depends only on:

~~~text
epsilon_i,
...,
epsilon_{i-d_n+1}
~~~

Hence observations whose indices differ by at least d_n use disjoint innovation blocks.

Partition each local window into d_n residue classes.

Within each residue class the approximated variables are independent.

Required finite-sample eligibility:

~~~text
d_n
<=
w_n
~~~

Otherwise:

~~~text
FINITE_MEMORY_DEPTH_EXCEEDS_WINDOW
~~~

## 18. Explicit Hoeffding width

For each coordinate, the weighted approximated sum is partitioned into d_n independent residue classes.

Using:

~~~text
Q_w
=
sum a_r^2
=
2(2w-1)/(w(w+1))
~~~

and a two-sided Hoeffding bound followed by union bounds over:

- residue classes;
- all p_n coordinates;

define:

~~~text
epsilon_ind
=
d_n
sqrt(
  (Q_w/2)
  log(
    4 p_n d_n
    /
    alpha_stat
  )
)
~~~

Then:

~~~text
P(
 max_j
 |S_j^[d_n]|
 >
epsilon_ind
)
<=
alpha_stat/2
~~~

## 19. Final stochastic width

Combine the two probability events.

~~~text
epsilon_stoch
=
epsilon_ind
+
1/n
~~~

Then:

~~~text
P(
 max over every required
 chronology × horizon × central threshold

 |Ftilde - E Ftilde|
 <=
epsilon_stoch
)
>=
1-alpha_stat
~~~

under the declared finite-memory model contract and structural eligibility.

No covariance estimate appears.

No variance floor appears.

No bootstrap appears.

## 20. Central CDF width

Define:

~~~text
epsilon_core
=
epsilon_stoch
+
epsilon_bias
~~~

For:

~~~text
-M_n <= x <= M_n
~~~

the raw band is:

~~~text
L_raw
=
Ftilde
-
epsilon_core

U_raw
=
Ftilde
+
epsilon_core
~~~

## 21. Tail raw bands

For x < -M_n:

~~~text
L_raw(x)=0
U_raw(x)=tau_n
~~~

For x > M_n:

~~~text
L_raw(x)=1-tau_n
U_raw(x)=1
~~~

For integer-valued horizon features, real x values are extended by the ordinary step-CDF convention.

## 22. Coverage-preserving CDF projection

Signed local-linear estimates need not themselves be monotone CDFs.

Use the already established deterministic projection:

~~~text
L_star(x)
=
max(
  0,
  sup_{y<=x} L_raw(y)
)

U_star(x)
=
min(
  1,
  inf_{y>=x} U_raw(y)
)
~~~

On the valid raw-band event:

~~~text
L_star(x)
<=
F(x)
<=
U_star(x)
~~~

for all x.

If realized endpoints cross:

~~~text
EMPTY_PROJECTED_CDF_BAND
~~~

is returned.

No cosmetic averaging is allowed.

## 23. TAIL drift projection

For two simultaneously covered local laws at anchor s and later state v:

~~~text
D_x
=
F_v(x)-F_s(x)
~~~

lies in:

~~~text
[
 L_v(x)-U_s(x),
 U_v(x)-L_s(x)
]
~~~

Define pointwise upper absolute bound:

~~~text
A_upper(x)
=
max(
 |L_v(x)-U_s(x)|,
 |U_v(x)-L_s(x)|
)
~~~

and pointwise lower absolute bound:

~~~text
A_lower(x)
=
0
if the difference interval contains 0

otherwise
min(
 |L_v(x)-U_s(x)|,
 |U_v(x)-L_s(x)|
)
~~~

Then:

~~~text
TAIL_lower
=
sup_x A_lower(x)

TAIL_upper
=
sup_x A_upper(x)
~~~

is a deterministic outer interval for:

~~~text
T_h(s,v)
=
sup_x
|F_h(v,x)-F_h(s,x)|
~~~

No operational tolerance tau_T is chosen here.

## 24. Median / MAD

The projected CDF band is an ordinary simultaneous CDF outer band.

Therefore the existing R4 density-free deterministic projection remains applicable:

~~~text
generalized median set
midpoint median outer interval
raw MAD outer interval
center uncertainty
zero-scale fail-close
~~~

Disposition:

~~~text
R4 D4
=
RETAIN_CONDITIONALLY
~~~

Final chain review remains D2E2-owned.

## 25. All-later coverage

The family event is built over every required observed chronology state from the minimum approved grid anchor through the latest state.

Therefore:

~~~text
ALL-LATER
=
SUPPORTED
~~~

at theorem-design level.

No later-time subsampling is introduced.

## 26. Latest-state coverage

The estimator is purely backward-looking.

At:

~~~text
t=n
u=1
~~~

the same w_n observations immediately preceding and including n are used.

No special symmetric-boundary approximation is required.

Therefore:

~~~text
LATEST_STATE
=
SUPPORTED
~~~

provided the structural eligibility conditions hold.

## 27. Non-vacuity proof

For fixed model parameters and fixed alpha_stat in (0,1):

~~~text
M_n
=
ceil(n^mu)

p_n
=
O(n^(1+mu))

d_n
=
O(log n)
~~~

and:

~~~text
Q_w
=
O(1/w_n)
=
O(n^(-(1-beta)))
~~~

Hence:

~~~text
epsilon_ind
=
O(
 log(n)^(3/2)
 n^(-(1-beta)/2)
)
~~~

Also:

~~~text
epsilon_dep
=
O(n^-1)

epsilon_bias
=
O(
 n^(-zeta)
 +
 n^(-2 beta)
)

tau_n
=
O(
 n^(-mu q)
)
~~~

Therefore under:

~~~text
0 < beta < 1
mu > 0
zeta > 0
q > 0
0 < rho < 1
finite C_dep
finite C_ls
finite L2
finite M_q
~~~

all declared widths converge to zero.

Thus the band is asymptotically non-vacuous.

## 28. Bandwidth-rate contract

D2E1 freezes the symbolic admissible region:

~~~text
0
<
beta
<
1
~~~

subject to the finite-sample eligibility checks:

~~~text
w_n >= 2

w_n <= ceil(n/10)

d_n <= w_n
~~~

The old Gaussian-specific constraint:

~~~text
beta
<
alpha/(6+3alpha)
~~~

does not belong to this A3 architecture.

## 29. Threshold-growth contract

D2E1 freezes:

~~~text
mu > 0
~~~

as the asymptotic admissible region.

No DEV-observed range is used.

The actual numeric beta and mu profiles are not chosen here.

They belong to later numerical-profile governance.

## 30. Alpha allocation

D2E1 fixes the method split:

~~~text
alpha_dep
=
alpha_stat/2

alpha_ind
=
alpha_stat/2
~~~

Tail and bias bounds are deterministic under the model assumptions and consume no additional probability budget.

The numeric value of alpha_stat remains unresolved and belongs to later risk/statistical governance.

## 31. Unknown-constants ledger

The final formula contains no unnamed theorem constant.

It does require explicit model parameters:

| Parameter | Meaning | D2E1 classification |
| --- | --- | --- |
| C_dep | finite-memory approximation magnitude | EXTERNAL_MODEL_USE_BINDING_REQUIRED |
| rho | finite-memory geometric decay | EXTERNAL_MODEL_USE_BINDING_REQUIRED |
| C_ls | local marginal approximation magnitude | EXTERNAL_MODEL_USE_BINDING_REQUIRED |
| zeta | local approximation rate | EXTERNAL_MODEL_USE_BINDING_REQUIRED |
| L2 | second time-derivative bound | EXTERNAL_MODEL_USE_BINDING_REQUIRED |
| q | uniform moment order | EXTERNAL_MODEL_USE_BINDING_REQUIRED |
| M_q | uniform q-moment bound | EXTERNAL_MODEL_USE_BINDING_REQUIRED |
| alpha_stat | family statistical error budget | GOVERNANCE_INPUT_REQUIRED |
| beta | local-window numerical profile | NUMERICAL_PROFILE_REQUIRED |
| mu | threshold-growth numerical profile | NUMERICAL_PROFILE_REQUIRED |

These values are **identified inputs**, not silently estimated from DEV.

D2E1 does not claim they have already been accepted for the actual StockScope process.

## 32. Implementability assessment

Once the required model/governance inputs are bound, every quantity in the band is deterministic or computed from allowed observed data.

There is no:

- oracle local CDF;
- unknown covariance matrix;
- bootstrap seed;
- hidden theorem constant;
- positive variance floor.

Therefore:

~~~text
IMPLEMENTATION_FORMULA
=
IDENTIFIED
~~~

but:

~~~text
MODEL_USE_INPUT_BINDING
=
PENDING
~~~

## 33. Feasibility witness

A purely mathematical witness demonstrating that the parameter region is non-empty is:

~~~text
beta = 1/2
mu = 1/4
q = 2
zeta = 1
C_dep = 1
rho = 1/2
C_ls = 1
L2 = 1
M_q = 1
fixed alpha_stat in (0,1)
~~~

This is **not** a proposed runtime profile and is not a statement about DEV.

It only witnesses non-emptiness of the symbolic theorem region.

## 34. What was not done

~~~text
DEV access
=
NO

DEV rerun
=
NO

Reference Adequacy
=
NO

Holdout
=
NO

backend implementation
=
NO

tests
=
NO

DB/runtime
=
NO

Production
=
NO

observed tail tuning
=
NO

observed dependence fitting
=
NO

observed smoothness fitting
=
NO
~~~

## 35. Primary source register

1. Phandoidaen, N., Richter, S. — Empirical process theory for nonsmooth functions under functional dependence, Electronic Journal of Statistics, 2022.
   - nonstationary Bernoulli-shift arrays;
   - local EDF;
   - deterministic localization weights;
   - nonsmooth empirical processes;
   - nonasymptotic maximal inequalities.

2. Phandoidaen, N., Richter, S. — Empirical process theory for locally stationary processes.
   - local stationary approximation;
   - functional dependence;
   - weighted empirical-process framework.

3. Alvarez, L., Pinto, C. — A maximal inequality for local empirical processes under weak dependence, 2023.
   - explicit nonasymptotic uniform local empirical-process control;
   - increasing class complexity;
   - supporting route only due different mixing/marginal assumptions.

4. Hoeffding, W. — Probability inequalities for sums of bounded random variables, 1963.
   - independent bounded-sum tail inequality used after finite-memory blocking.

## 36. Project-specific theorem warning

The exact StockScope concentration procedure is not copied verbatim from one publication.

Project-specific pieces include:

~~~text
discrete backward local-linear weights

finite-memory indicator contract

explicit dependence-approximation allocation

residue-class blocking

family union bound

full StockScope chronology/horizon/threshold indexing

TAIL interval projection
~~~

These must receive independent theorem review during D2E2 / final method review.

## 37. Contract artifact

D2E1 creates:

~~~text
docs/contracts/NEXT6E_S6A_R5_CONCENTRATION_BAND_V1.json
~~~

with status:

~~~text
THEOREM_DESIGN_FROZEN
~~~

Semantic SHA256:

~~~text
03d77e20b4843d8181b96255691278d954b240f1b558e779309f68a3064aa78b
~~~

This is not METHOD_APPROVED.

## 38. Next authorized task

~~~text
NEXT-6E-S6A-R5-D2E2
THEOREM CHAIN CONSOLIDATION
~~~

D2E2 must combine and review:

~~~text
P1 atomic/lattice transfer
P2 finite-memory dependence bridge
P3 backward local-linear W2 estimator
P4 latest-state
P5 CandidateDomain V2
P6 all-later family
P7 explicit A3 concentration band
P8 CDF / TAIL / median / MAD projections
~~~

It must also identify which external model-use parameters remain unbound.

## 39. Final state

~~~text
NEXT-6E-S6A-R5-D2E1
=
COMPLETE

Concentration architecture
=
A3

Primary project route
=
PROJECT_EXPLICIT_FINITE_MEMORY_BLOCKING_V1

Concentration-band contract
=
THEOREM_DESIGN_FROZEN

Hidden theorem constants
=
NONE

Band widths
=
EXPLICIT

All-later
=
SUPPORTED AT DESIGN LEVEL

Latest-state
=
SUPPORTED AT DESIGN LEVEL

Full TAIL target
=
RETAINED

CandidateDomain V2
=
UNCHANGED / FROZEN

External model parameters
=
BINDING PENDING

R5 method
=
NOT FINAL-FROZEN

R5 G-A
=
BLOCKED

R5-D3
=
NOT AUTHORIZED

Next stage
=
NEXT-6E-S6A-R5-D2E2
THEOREM CHAIN CONSOLIDATION

Production impact
=
NONE
~~~
