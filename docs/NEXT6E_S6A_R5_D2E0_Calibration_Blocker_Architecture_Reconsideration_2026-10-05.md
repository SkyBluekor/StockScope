# StockScope NEXT-6E-S6A-R5-D2E0 — Calibration-Blocker Architecture Reconsideration

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 architecture decision. 구현/평가 문서가 아니다.  
기준 main: 90d2e290485fdd0d863f656364eed7546277ef8a  
Parent: NEXT-6E-S6A-R5-D2D2  
CandidateDomain V2 semantic SHA256: e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09

## 1. 쉬운 요약

지금까지 만든 W2 통계량 자체는 폐기할 필요가 없다.

문제는 "이 정도 오차면 정상 범위다"를 bootstrap으로 정하는 마지막 calibration 단계였다.

D2E0에서는 네 가지 대안을 비교했고, 최종적으로:

~~~text
A3
=
ANALYTICAL_CONSERVATIVE_CONCENTRATION_BAND
~~~

를 선택한다.

핵심 이유:

- A1은 Gaussian을 일부 유지하지만 D2D2의 local-centering blocker를 그대로 남긴다.
- A2는 현재 R5의 nonstationary + dependent + high-dimensional + atomic indicator 구조를 직접 덮는 self-normalized theorem route가 확인되지 않았다.
- A3는 covariance matrix 추정, positive variance floor, bootstrap critical value를 요구하지 않고, locally stationary / dependent nonsmooth empirical-process의 maximal/concentration inequality를 직접 사용해 Fhat - E[Fhat]를 제어할 수 있다.
- 따라서 D2D2에서 막힌 두 핵심 문제를 가장 직접적으로 제거하면서 기존 TAIL / all-later / latest-state / CandidateDomain V2 의미를 유지할 수 있다.

A3는 더 보수적인 band를 만들 수 있다. 하지만 현재 단계의 우선순위는 "좁아 보이는 band"가 아니라 "정당화 가능한 band"다.

---

## 2. 최종 결정

~~~text
NEXT-6E-S6A-R5-D2E0
=
COMPLETE

Selected calibration architecture
=
A3 ANALYTICAL_CONSERVATIVE_CONCENTRATION_BAND

A1 HYBRID_GAUSSIAN_TAIL
=
NOT SELECTED

A2 SELF_NORMALIZED_MAX
=
NOT SELECTED

A3 ANALYTICAL_CONCENTRATION
=
SELECTED

A4 TARGET_REDUCTION
=
NOT REQUIRED AT THIS STAGE

R5 statistical target
=
RETAINED

CandidateDomain V2
=
UNCHANGED / FROZEN

W2 local estimator family
=
RETAINED

Gaussian calibration
=
NO LONGER PRIMARY

Bootstrap calibration
=
NO LONGER REQUIRED BY SELECTED ARCHITECTURE

R5 method
=
NOT YET FROZEN

Implementation
=
NOT AUTHORIZED
~~~

---

## 3. Current blocker inherited from D2D2

D2D2 ended with:

~~~text
BLOCKED_CALIBRATION_ROUTE_EXHAUSTED
~~~

The two decisive obstacles were:

~~~text
B1
=
LOW_VARIANCE / DEGENERATE ATOMIC COORDINATES

B2
=
OBSERVABLE LOCAL CENTERING FOR COVARIANCE / BOOTSTRAP
~~~

The Gaussian root itself was not the blocker.

~~~text
W2 Gaussian root
=
FEASIBLE
~~~

but executable calibration was not established.

---

## 4. Architecture comparison principle

D2E0 compares architectures by:

1. preservation of the full TAIL CDF-sup target;
2. all-later preservation;
3. latest-state u=1 preservation;
4. lattice/ties preservation;
5. CandidateDomain V2 preservation;
6. direct treatment of degenerate coordinates;
7. observable implementability;
8. removal of D2D2 centering/covariance blockers;
9. theorem tractability;
10. auditability.

No DEV result, passing N, observed tail profile, or actual variance profile was used.

---

## 5. A1 — Hybrid Gaussian + Deterministic Tail Envelope

### Concept

Use Gaussian calibration on a non-degenerate central core and deterministic bounds outside that core.

~~~text
FULL THRESHOLD FAMILY
=
GAUSSIAN CORE
+
DETERMINISTIC TAIL
~~~

### Positive aspects

- reuses D2D1 Gaussian-rate work;
- can potentially preserve the full CDF target;
- isolates tail degeneracy instead of deleting it;
- CandidateDomain V2 can remain unchanged.

### Remaining problems

A1 does not remove the observable-centering problem.

The Gaussian core still requires a data-based covariance object for chronology-varying centered coordinates.

Therefore A1 still needs a formal theorem chain:

~~~text
local mean estimation
→ residualization error
→ covariance estimation
→ Gaussian max calibration
~~~

D2D2 did not close this chain.

Additionally the Gaussian/tail partition must be outcome-independent or must carry a full selection-error proof.

### A1 decision

~~~text
A1
=
NOT SELECTED

reason
=
RETains_PRIMARY_D2D2_CENTERING_BLOCKER
~~~

A1 remains a possible future refinement if a valid observable-centering theorem becomes available.

---

## 6. A2 — Self-Normalized / Variance-Adaptive Max Inference

### Concept

Replace raw Gaussian coordinates with self-normalized or studentized coordinates so near-zero variance does not require a common positive variance floor.

### Research outcome

The reviewed literature contains substantial self-normalized and studentized time-series inference, but no theorem was identified that directly covers the full R5 object:

~~~text
locally/nonstationary process
+
physical/functional dependence
+
time-varying deterministic local weights
+
high-dimensional maximum
+
atomic indicator coordinates
+
all-later O(n) index
+
latest state
~~~

Exact zero-variance coordinates also still require separate formal handling.

Selecting A2 now would therefore replace one unresolved theorem chain with another.

### A2 decision

~~~text
A2
=
NOT SELECTED

reason
=
NO_DIRECT_THEOREM_ROUTE_IDENTIFIED
~~~

This is not a universal claim that self-normalization is impossible.

---

## 7. A3 — Analytical Conservative Concentration Band

### Core idea

Do not estimate a covariance matrix and do not approximate a Gaussian maximum.

Instead construct a direct high-probability bound:

~~~text
P(
 max over required family
 |Ftilde - E[Ftilde]|
 >
epsilon_stoch
)
<=
alpha_stat
~~~

Then combine:

~~~text
stochastic concentration width
+
local smoothing bias
+
threshold/tail remainder
~~~

to obtain a simultaneous CDF band.

The final band is then passed through the already resolved coverage-preserving CDF projection.

---

## 8. Why A3 directly addresses D2D2 blocker B1

Concentration/maximal inequalities for bounded dependent variables do not require every coordinate to have variance bounded below by a universal positive constant.

A coordinate with tiny or zero variance does not invalidate the whole family.

It merely contributes little or no stochastic fluctuation.

Therefore:

~~~text
UNIFORM_ROOT_NONDEGENERACY
=
NOT REQUIRED BY SELECTED ARCHITECTURE
~~~

This removes the key atomic-tail problem that blocked the Gaussian bootstrap route.

---

## 9. Why A3 directly addresses D2D2 blocker B2

For a concentration band, implementation does not need to observe the unknown local mean in order to estimate a covariance matrix.

The theoretical event directly controls:

~~~text
Ftilde
-
E[Ftilde]
~~~

and the bias analysis connects:

~~~text
E[Ftilde]
~~~

to the target local CDF:

~~~text
F(u,x)
~~~

Thus no data residualization step of the form:

~~~text
indicator
-
estimated local CDF
~~~

is required merely to produce a covariance estimate.

Therefore:

~~~text
LOCAL_MEAN_RESIDUALIZATION_FOR_BOOTSTRAP
=
REMOVED FROM ARCHITECTURE
~~~

The method still needs a deterministic/stated bias bound, but that is the ordinary local-smoothing problem already compatible with W2's second-order kernel design.

---

## 10. Literature feasibility for A3

### Phandoidaen & Richter

Their locally stationary empirical-process framework under functional dependence provides:

- nonasymptotic maximal inequalities;
- treatment of nonsmooth function classes;
- explicit EDF applicability;
- locally stationary process support;
- uniform convergence applications.

This is structurally much closer to a concentration-band architecture than to the failed covariance-bootstrap architecture.

### Alvarez & Pinto

Their local empirical-process maximal inequality gives nonasymptotic bounds uniform over:

- evaluation points;
- bandwidths;
- function classes;

under exponential weak dependence, and explicitly allows growing function-class complexity.

The exact process assumptions differ from the current R5 physical-dependence contract, so it is supporting evidence rather than a direct plug-in theorem.

### Hill / physical-dependence maximal inequalities

Recent physical-dependence work provides maximal/moment inequalities for possibly nonstationary triangular arrays.

This supports a direct concentration route without requiring a Gaussian covariance inversion or variance floor.

### Architecture conclusion

~~~text
A3 theorem family
=
IDENTIFIED / PLAUSIBLE / BOUNDED

A3 exact StockScope theorem
=
NOT YET FROZEN
~~~

That distinction is important.

D2E0 selects the architecture; D2E1 must still derive the exact band.

---

## 11. Expected A3 error decomposition

D2E1 should target a band of the form:

~~~text
epsilon_total(n)
=
epsilon_stochastic(n)
+
epsilon_bias(n)
+
epsilon_tail(n)
~~~

with a typical target order:

~~~text
epsilon_stochastic
~
C_dep
sqrt(
 log p_n
 /
 (n h_n)
)
+
higher-order concentration term

epsilon_bias
~
C_smooth h_n^2

epsilon_tail
~
deterministic moment/tail remainder
~~~

The exact constants and remainder terms are not frozen in D2E0.

---

## 12. Non-vacuity feasibility

D2D1 already uses:

~~~text
h_n
=
n^(-beta)
~~~

A3 no longer needs the previous Gaussian upper bound:

~~~text
beta
<
alpha/(6+3 alpha)
~~~

because that restriction came from high-dimensional Gaussian approximation.

Under a concentration route, the fundamental consistency requirements are instead expected to include:

~~~text
h_n -> 0

n h_n / log p_n -> infinity

h_n^2 -> 0
~~~

plus dependence-specific remainder conditions.

Since the current simultaneous family is polynomial-size after deterministic threshold truncation:

~~~text
log p_n
=
O(log n)
~~~

there exists a broad nonempty generic range:

~~~text
0 < beta < 1
~~~

for the basic stochastic-width condition.

W2 second-order bias remains compatible.

The exact approved beta interval is a D2E1 responsibility.

---

## 13. A3 preserves all-later semantics

A3 does not reduce later chronology.

The event remains over:

~~~text
approved anchors
× all approved later chronology states
× 3 horizons
× approved threshold representation
~~~

A polynomial number of coordinates affects the concentration width through logarithmic complexity rather than requiring each coordinate to satisfy a positive variance floor.

Thus:

~~~text
ALL-LATER
=
RETAINED
~~~

---

## 14. A3 preserves latest-state semantics

W2 already uses backward-looking one-sided local weighting.

Therefore no future observation is required at u=1.

A3 changes the uncertainty engine, not the estimator chronology.

~~~text
LATEST_STATE_REQUIRED
=
RETAINED
~~~

---

## 15. A3 and signed W2 weights

W2's signed second-order kernel is retained because it controls first-order local bias.

Concentration analysis must therefore support bounded deterministic signed weights.

This is an explicit D2E1 proof obligation.

The architecture does not assume positivity of weights.

---

## 16. A3 and CDF validity

The signed W2 estimator is not automatically a CDF.

The previously proved deterministic band projection remains part of the architecture:

~~~text
raw concentration band
↓
coverage-preserving monotone CDF projection
↓
valid CDF band
↓
median / MAD projection
~~~

Therefore no earlier W2 shape work is discarded.

---

## 17. A3 and TAIL target

The target remains:

~~~text
T_h(s,v)
=
sup_x
|F_h(v,x)-F_h(s,x)|
~~~

A3 does not replace it with an integrated metric.

The concentration band is an uncertainty engine around local CDF objects, not a new product metric.

~~~text
TAIL TARGET
=
RETAINED
~~~

---

## 18. A3 and threshold representation

D2E0 does not freeze the final threshold-domain construction.

D2E1 must choose between theoremically justified options such as:

- direct empirical-process supremum over the threshold class;
- deterministic lattice truncation plus explicit tail remainder;
- another coverage-preserving finite representation.

What is forbidden:

~~~text
drop low-variance thresholds
because Gaussian calibration dislikes them
~~~

That Gaussian-specific problem is precisely what A3 is intended to avoid.

---

## 19. A3 and statistical error budget

A3 still accepts a family-wide statistical error budget:

~~~text
alpha_stat
~~~

but the critical width is now derived analytically from a concentration inequality rather than a bootstrap quantile.

Numeric alpha_stat remains Track-B / convergence-governance owned.

D2E0 does not choose its value.

---

## 20. A3 downside

A3 is expected to be more conservative than a successful Gaussian/bootstrap calibration.

Potential consequences:

- wider CDF bands;
- larger supported anchor requirements;
- more frequent fail-closed states;
- less power to detect subtle distribution shifts.

None of these are reasons to reject A3 at architecture stage.

DEV outcomes must not be used to tune architecture.

The relevant question here is validity and non-vacuity, not favorable passing rates.

---

## 21. A4 — Target / Architecture Reduction

A4 is not required at this stage because A3 offers a plausible theorem family that keeps:

~~~text
TAIL
all-later
latest-state
lattice/ties
CandidateDomain V2
median/MAD projection
~~~

intact.

Therefore:

~~~text
A4
=
DEFERRED / NOT REQUIRED
~~~

Target reduction becomes necessary only if D2E1 proves the A3 concentration route cannot yield a shrinking, implementable band under acceptable assumptions.

---

## 22. Architecture decision matrix

| Criterion | A1 Hybrid Gaussian | A2 Self-normalized | A3 Concentration | A4 Target reduction |
| --- | --- | --- | --- | --- |
| Full TAIL preserved | likely | possible | YES | maybe not |
| All-later preserved | possible | unproven | YES target retained | uncertain |
| Latest state | YES | possible | YES | uncertain |
| CandidateDomain V2 | YES | YES | YES | maybe |
| Degenerate coordinates | tail split required | intended benefit | **no variance floor needed** | avoided by redesign |
| Observable centering blocker | **remains** | theorem unresolved | **removed from covariance-calibration layer** | changed problem |
| Direct theorem family | partial | weak | **strongest identified** | N/A |
| Reuse W2 estimator | high | medium | **high** | uncertain |
| New architecture burden | medium | high | medium | very high |
| Selected | NO | NO | **YES** | NO |

---

## 23. What remains frozen

~~~text
NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2
=
FROZEN / UNCHANGED

anchors
=
18

grid
=
j/20, j=2..19

common-N
=
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR

all-later
=
RETAINED

latest-state
=
REQUIRED
~~~

No CandidateDomain V3 is created.

---

## 24. Gaussian work disposition

The prior W2 Gaussian results are not deleted.

~~~text
W2_GAUSSIAN_RATE_FEASIBILITY
=
HISTORICAL / REUSABLE RESEARCH RESULT
~~~

But they are no longer the primary calibration path for the current R5 architecture.

This matters because future work may use Gaussian calibration as an optional refinement only after a valid baseline concentration band exists.

D2E0 does not authorize that refinement.

---

## 25. Selected architecture identity

Recommended architecture ID:

~~~text
R5_CONSERVATIVE_LOCAL_CDF_CONCENTRATION_V1
~~~

Meaning:

- W2 one-sided second-order local CDF estimator;
- direct dependence-aware maximal/concentration bound;
- explicit local bias term;
- explicit tail/threshold approximation term if required;
- coverage-preserving CDF projection;
- density-free median/MAD projection;
- family-wide simultaneous coverage over CandidateDomain V2 and all-later chronology.

This identity is a design direction, not yet a frozen method contract.

---

## 26. Next authorized task

~~~text
NEXT-6E-S6A-R5-D2E1
CONSERVATIVE LOCAL-CDF CONCENTRATION BAND DESIGN
~~~

D2E1 must close:

1. exact maximal/concentration theorem source;
2. exact dependence contract;
3. signed-weight compatibility;
4. exact function/index class;
5. stochastic band width;
6. local bias bound;
7. threshold/tail handling;
8. family multiplicity;
9. latest-state coverage;
10. all-later simultaneous event;
11. symbolic bandwidth-rate interval;
12. non-vacuity proof;
13. CDF projection linkage;
14. median/MAD linkage.

---

## 27. D2E1 success target

D2E1 should aim for:

~~~text
epsilon_n
→
0

and

P(
 all required local CDFs
 are inside the declared bands
)
>=
1 - alpha_stat
+ o(1)
~~~

without:

- covariance estimation;
- Gaussian critical-value estimation;
- uniform positive coordinate variance;
- bootstrap.

---

## 28. D2E1 must fail closed if necessary

If no theorem chain produces a shrinking concentration band under a realistic R5 dependence/smoothness contract:

~~~text
NEXT-6E-S6A-R5-D2E1
=
BLOCKED_CONCENTRATION_ROUTE_UNRESOLVED

A4
=
TARGET_ARCHITECTURE_REDUCTION_REQUIRED
~~~

Do not return to Gaussian bootstrap by default.

---

## 29. No implementation authorization

~~~text
R5 method
=
NOT FROZEN

R5 G-A
=
BLOCKED

R5-D2E FINAL METHOD FREEZE
=
NOT AUTHORIZED

R5-D3 IMPLEMENTATION
=
NOT AUTHORIZED
~~~

D2E0 is architecture selection only.

---

## 30. Data isolation

~~~text
DEV
=
NOT ACCESSED / NOT RERUN

Reference Adequacy
=
NOT ACCESSED

passing anchor
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

Production
=
NOT ACCESSED
~~~

---

## 31. Primary literature register

1. Phandoidaen, N., Richter, S. — Empirical process theory for nonsmooth functions under functional dependence. Electronic Journal of Statistics 16(1), 2022. DOI: 10.1214/22-EJS2023.
   - locally stationary functional-dependence framework;
   - nonsmooth classes;
   - nonasymptotic maximal inequalities;
   - EDF applicability.

2. Phandoidaen, N., Richter, S. — Empirical process theory for locally stationary processes. Bernoulli, 2022.
   - functional-dependence local-stationarity framework;
   - maximal inequalities;
   - uniform nonparametric convergence applications.

3. Alvarez, L., Pinto, C. — A maximal inequality for local empirical processes under weak dependence. arXiv:2307.01328.
   - nonasymptotic local empirical-process bounds;
   - uniformity over evaluation point/bandwidth/function class;
   - growing class complexity;
   - exponential mixing setting.

4. Hill, J. B. — Mixingale and physical dependence equality with applications. Statistics & Probability Letters, 2025.
   - possibly nonstationary physical-dependence arrays;
   - maximal-moment/concentration implications;
   - geometric-memory equivalence structure.

5. Xu, H., Wang, D., Zhao, Z., Yu, Y. — Change-point inference in high-dimensional regression models under temporal dependence. Annals of Statistics 52(3), 2024.
   - Bernstein inequality under functional dependence;
   - dependence-aware nonasymptotic tools.

---

## 32. Final state

~~~text
NEXT-6E-S6A-R5-D2E0
=
COMPLETE

Selected calibration architecture
=
A3 ANALYTICAL_CONSERVATIVE_CONCENTRATION_BAND

Architecture ID
=
R5_CONSERVATIVE_LOCAL_CDF_CONCENTRATION_V1

A1
=
NOT SELECTED

A2
=
NOT SELECTED

A3
=
SELECTED

A4
=
NOT REQUIRED YET

TAIL
=
RETAINED

All-later
=
RETAINED

Latest-state
=
RETAINED

CandidateDomain V2
=
UNCHANGED / FROZEN

W2 estimator
=
RETAINED

Gaussian/bootstrap calibration
=
REMOVED AS PRIMARY PATH

R5 method
=
NOT FROZEN

Next stage
=
NEXT-6E-S6A-R5-D2E1
CONSERVATIVE LOCAL-CDF CONCENTRATION BAND DESIGN

Implementation
=
NOT AUTHORIZED

DEV
=
NOT RERUN

Reference Adequacy
=
NOT ACCESSED

Holdout
=
LOCKED / NOT ACCESSED

DB/runtime
=
NOT ACCESSED

Production impact
=
NONE
~~~
