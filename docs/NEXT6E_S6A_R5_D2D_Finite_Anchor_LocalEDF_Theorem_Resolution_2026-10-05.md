# StockScope NEXT-6E-S6A-R5-D2D — Finite-Anchor Local-EDF Theorem Resolution

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 theorem-resolution 결과. 구현/평가 문서가 아니다.  
기준 main: \`fa57e5670429d25219c44be826d7d77cf75d4692\`  
Parent: \`NEXT-6E-S6A-R5-D2C\`  
CandidateDomain V2 semantic SHA256: \`e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09\`

## 1. 최종 판정

\`\`\`text
NEXT-6E-S6A-R5-D2D
=
BLOCKED_THEOREM_ROUTE_UNRESOLVED

Decisive blockers
=
BLOCKED_LOCAL_WEIGHT_RATE_COMPATIBILITY
BLOCKED_ALL_LATER_SIMULTANEOUS
BLOCKED_CALIBRATION

R5 method
=
NOT FROZEN

R5-D2E
=
NOT AUTHORIZED

R5-D3 implementation
=
NOT AUTHORIZED
\`\`\`

D2C의 finite-anchor 전환은 의미가 있었다. nominal anchor multiplicity는 18개로 고정되어 이전의 every-integer anchor family 문제는 제거됐다.

하지만 StockScope가 보존한 요구사항:

\`\`\`text
ALL_APPROVED_LATER_STATES
+
LATEST_STATE_REQUIRED
+
ATOMIC / LATTICE EDF
\`\`\`

를 하나의 theorem/calibration chain으로 묶는 데 필요한 마지막 연결은 아직 닫히지 않았다.

이번 D2D는 이 gap을 숨기지 않고 fail-closed한다.

---

## 2. Data / execution boundary

이번 단계는 theorem research만 수행했다.

\`\`\`text
DEV raw data
=
NOT ACCESSED

DEV rerun
=
NO

sealed DEV result for tuning
=
NO

Reference Adequacy
=
NOT ACCESSED

forward envelope
=
NOT ACCESSED

passing N / minimum supported anchor
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

backend code
=
UNCHANGED

tests
=
UNCHANGED
\`\`\`

CandidateDomain V2도 변경하지 않았다.

---

## 3. Frozen input contract

D2D는 다음을 reopen하지 않는다.

\`\`\`text
CandidateDomain architecture
=
PROSPECTIVE_FINITE_ANCHOR_GRID

anchor fractions
=
j/20
j=2,...,19

nominal anchor count
=
18

integer mapping
=
ceil(j*n/20)

common-N semantics
=
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR

later-state scope
=
ALL_APPROVED_LATER_STATES

latest-state
=
REQUIRED

observed unit
=
BASIS_POINT INTEGER LATTICE

ties
=
PRESERVE

jitter/randomized implementation
=
FORBIDDEN
\`\`\`

---

## 4. Literature reviewed in D2D

### 4.1 Phandoidaen & Richter — nonsmooth empirical processes

Nathawut Phandoidaen and Stefan Richter, *Empirical process theory for nonsmooth functions under functional dependence*, Electronic Journal of Statistics 16(1), 2022.  
arXiv: https://arxiv.org/abs/2108.08512  
DOI: https://doi.org/10.1214/22-EJS2023

Relevant results:

- Theorem 2.3: functional CLT in \(\ell^\infty(\mathcal F)\) under functional dependence and entropy/compatibility conditions.
- The framework explicitly allows nonstationary Bernoulli-shift arrays \(X_i=J_{i,n}(\mathcal A_i)\).
- Localized EDFs are an explicit motivating example.
- The direct EDF corollaries impose regularity on conditional/marginal distribution functions which the StockScope atomic lattice law does not directly satisfy.

Disposition:

\`\`\`text
GENERAL NONSMOOTH EMPIRICAL-PROCESS FRAMEWORK
=
RELEVANT

DIRECT ATOMIC LOCAL-EDF COROLLARY
=
NOT APPLICABLE AS WRITTEN
\`\`\`

### 4.2 Chang, Chen & Wu — high-dimensional dependent CLT

Jinyuan Chang, Xiaohui Chen, Mingcong Wu, *Central limit theorems for high dimensional dependent data*, Bernoulli 30(1), 2024, 712–742.  
DOI: https://doi.org/10.3150/23-BEJ1614  
arXiv: https://arxiv.org/abs/2104.12929

Important point for D2D:

the physical-dependence setup allows

\`\`\`text
X_t = f_t(ε_t, ε_{t-1}, ...)
\`\`\`

with \(f_t\) changing in \(t\), hence possibly nonstationary high-dimensional arrays.

The paper gives Gaussian approximation and parametric-bootstrap tools for maxima / hyper-rectangles under uniform physical-dependence controls.

Disposition:

\`\`\`text
FINITE / GROWING HIGH-DIMENSIONAL NONSTATIONARY VECTOR
=
SUPPORTED AS A RESEARCH BRIDGE

STOCKSCOPE LOCAL-EDF MAX PROCEDURE
=
NOT DIRECTLY PROVIDED
\`\`\`

The crucial unresolved issue is that local smoothing introduces coordinate weights of order \(b_n^{-1/2}\) after CLT normalization. The high-dimensional moment/dependence norms therefore grow as bandwidth shrinks, and the resulting approximation rate must still dominate both local bias and the growing simultaneous family.

No final compatible \(b_n\) / kernel / approximation-rate chain is frozen here.

### 4.3 Dette & Wu — locally stationary confidence surfaces

Holger Dette, Weichi Wu, *Confidence Surfaces for the Mean of Locally Stationary Functional Time Series*, Statistica Sinica 36, 2026, 583–604.  
DOI: https://doi.org/10.5705/ss.202023.0150  
arXiv: https://arxiv.org/abs/2109.03641

This is the strongest reviewed evidence that full local-time simultaneous inference is possible in principle.

The paper constructs simultaneous confidence surfaces by sparse high-dimensional Gaussian approximation and a specialized multiplier bootstrap.

However its theorem assumptions are not compatible with StockScope EDF indicators without new work.

In particular:

- the functional coordinate is treated as a smooth functional curve;
- Assumption 4.3 requires differentiability in the functional argument;
- StockScope's natural curve \(x\mapsto 1\{X_i\le x\}\) is a càdlàg step function;
- the paper uses a smooth symmetric kernel and its uniform arguments are built on an interior time region, while StockScope requires \(u=1\).

Therefore:

\`\`\`text
ALL-TIME CONFIDENCE-SURFACE IDEA
=
HIGHLY RELEVANT

DIRECT SUBSTITUTION
Y_i(x)=1{X_i<=x}
=
INVALID UNDER PUBLISHED ASSUMPTIONS
\`\`\`

### 4.4 Heinrichs — localized FCLT

Florian Heinrichs, *A Functional Central Limit Theorem for Localized Partial Sums of Non-Stationary Time Series*, arXiv:2607.17697, 2026.

The paper provides weak convergence of localized partial sums for piecewise locally stationary processes under geometric physical dependence, including an isonormal extension on \(L^2\) and totally bounded \(L^2\) classes.

It does not provide the required StockScope sup-norm confidence process over the shrinking local-time / atomic-threshold family.

Disposition:

\`\`\`text
LOCALIZED PROCESS LIMIT
=
RELEVANT

DIRECT ALL-LATER SUP BAND
=
NOT PROVIDED
\`\`\`

### 4.5 Ma & Zhang — high-dimensional maxima bootstrap

Ruru Ma, Shibin Zhang, *Multiplier and empirical subsample bootstraps for maxima in high dimensional time series analysis*, Journal of Multivariate Analysis 213, 2026, 105579.

This provides modern bootstrap approximation for maxima of high-dimensional time-series statistics.

The published setup is not a direct theorem for StockScope's locally weighted nonstationary atomic EDF array.

Disposition:

\`\`\`text
CALIBRATION RESEARCH FAMILY
=
RELEVANT

DIRECT R5 CALIBRATION APPROVAL
=
NO
\`\`\`

---

## 5. P1 — Atomic Local Transform

### Result

\`\`\`text
P1
=
CONDITIONAL_PROJECT_LEMMA_RESOLVED
\`\`\`

The proof-only distributional transform remains viable.

At fixed local time \(u\), for lattice-valued tangent variable \(X(u)\) with CDF \(F_u\), introduce an independent auxiliary \(V\sim U(0,1)\) and define only in proof space:

\`\`\`text
U(u)
=
F_u(X(u)-)
+
V {F_u(X(u))-F_u(X(u)-)}
\`\`\`

Then:

1. \(U(u)\) is marginally uniform.
2. For a lattice threshold \(x\),

\`\`\`text
1{X(u)<=x}
=
1{U(u)<=F_u(x)}
\`\`\`

almost surely, up to the null event associated with a boundary auxiliary draw.
3. No jitter or transformed observation is required in implementation.

### Dependence transfer lemma

Let \(X,X^*\) be coupled lattice variables on the same integer grid and use the same auxiliary \(V\).

If \(X=X^*\), then the transforms agree.

Since a nonzero lattice difference has magnitude at least one:

\`\`\`text
P(X != X*)
<=
E|X-X*|^r
\`\`\`

for any \(r>0\).

Because transformed values lie in \([0,1]\):

\`\`\`text
||U-U*||_q
<=
P(X != X*)^(1/q)
<=
||X-X*||_r^(r/q)
\`\`\`

Thus geometric physical dependence of the lattice tangent process transfers to geometric physical dependence of the proof transform, with a possibly weakened exponent.

### Remaining condition

Time-smooth transfer requires an explicit uniform local coupling / Hölder contract for the tangent laws.

Therefore P1 is a valid project lemma **conditional on** the R5 local-stationarity model contract; it is not evidence that the actual Development process satisfies that model.

---

## 6. P2 — Local Dependence Contract

### Result

\`\`\`text
P2
=
THEOREM_CLASS_IDENTIFIED
NOT FINAL-FROZEN
\`\`\`

Preferred class:

\`\`\`text
UNIFORM_GEOMETRIC_PHYSICAL_DEPENDENCE
OF LOCALLY STATIONARY TANGENT PROCESS
\`\`\`

Rationale:

- compatible with Phandoidaen–Richter style nonsmooth empirical-process theory;
- compatible with recent locally stationary FCLT literature;
- compatible with high-dimensional Gaussian approximation literature;
- preserved under the P1 lattice-transform lemma up to modified constants/rates.

Required exact contract later:

\`\`\`text
Bernoulli-shift representation
uniform moment order
uniform physical-dependence coefficient
geometric decay
uniform local-time coupling/Hölder rate
joint 3-horizon finite-window transfer
non-degeneracy for the final root
\`\`\`

P2 is not frozen because the exact moment/rate values depend on the stochastic engine ultimately selected for P6/P7.

---

## 7. P3 — Local EDF stochastic construction

### Candidate estimator direction

A backward-looking one-sided local estimator is now preferred for **all** local times, not only \(u=1\).

This is architecturally preferable because anchor-local reference estimation should not borrow post-anchor observations.

Generic form:

\`\`\`text
Fhat_h,n(u,x)
=
1/(n b_n)
Σ K_-((i/n-u)/b_n) 1{X_i^h <= x}
\`\`\`

with support:

\`\`\`text
supp(K_-)
subset of [-1,0]
\`\`\`

Benefits:

- no post-anchor leakage;
- same estimator form at interior times and latest state;
- \(u=1\) no longer requires a distinct symmetric-kernel boundary patch.

### Bias problem

A positive one-sided local-constant kernel generally has first-order time bias.

Then asymptotic negligibility at stochastic scale requires roughly:

\`\`\`text
sqrt(n b_n) * b_n
→ 0
\`\`\`

together with:

\`\`\`text
n b_n → infinity
b_n → 0
\`\`\`

which pushes bandwidth to an undersmoothing regime.

At the same time, generic high-dimensional Gaussian approximation sees coordinate magnitudes inflated by the local weighting, roughly of order \(b_n^{-1/2}\).

The reviewed high-dimensional theorem does not automatically guarantee that the required Gaussian-approximation remainder vanishes for the same bandwidth class.

### Possible repair

A higher-order one-sided signed kernel can cancel first-order bias.

For example, on \([-1,0]\):

\`\`\`text
K_-(r)
=
4 + 6r
\`\`\`

satisfies:

\`\`\`text
∫ K_-(r) dr = 1
∫ r K_-(r) dr = 0
\`\`\`

and can reduce deterministic local bias under stronger time smoothness.

But signed weights mean the raw localized estimate is no longer automatically a monotone CDF and a monotone/clipped band-construction layer must be proved before median/MAD inversion.

No published source reviewed here provides this complete StockScope chain.

### Result

\`\`\`text
P3
=
BLOCKED_LOCAL_WEIGHT_RATE_COMPATIBILITY
\`\`\`

This is a new, more precise blocker than the earlier generic "local EDF limit" label.

---

## 8. P4 — Latest-State u=1 Boundary

### Result

\`\`\`text
P4
=
CONSTRUCTION_IDENTIFIED
DEPENDENT_ON_P3
\`\`\`

Using a backward one-sided kernel for every local time eliminates the conceptual need to evaluate future observations beyond \(u=1\).

Thus latest-state support is no longer a separate route-selection problem.

However:

- the one-sided kernel bias;
- stochastic normalization;
- signed-vs-positive kernel choice;
- local-CDF band construction

must be solved in P3/P6.

Therefore:

\`\`\`text
u=1 structural access
=
RESOLVED

u=1 valid confidence inference
=
NOT YET RESOLVED
\`\`\`

---

## 9. P5 — Finite-Anchor Joint Coupling

### Result

\`\`\`text
P5
=
RESOLVED_AT_ARCHITECTURE_LEVEL
\`\`\`

CandidateDomain V2 fixes at most 18 anchors.

This removes the old every-integer anchor index.

The resulting family can be represented as a finite/growing high-dimensional vector and jointly calibrated without assigning an independent alpha to each anchor.

Chang–Chen–Wu's nonstationary physical-dependence framework confirms that high-dimensional sums with time-varying coordinate maps are a legitimate theorem family.

This does **not** by itself solve all-later or threshold uniformity.

---

## 10. P6 — ALL-LATER simultaneous coverage

### Product index clarified

"ALL-LATER" in the current project means all approved later **observed chronology states / integer positions** required by the Reference Adequacy procedure.

It does not require an uncountable continuum of hypothetical unobserved times.

Thus the later-time index for a record of aligned length \(n\) is finite and grows at most linearly in \(n\).

This is an important reduction relative to D2A's continuum interpretation.

### Remaining stochastic family

Even after this clarification the required maximum contains:

\`\`\`text
up to 18 anchors
× O(n) later chronology states
× 3 horizons
× CDF threshold class
\`\`\`

The finite-anchor and finite-later-time parts can in principle be embedded in a high-dimensional vector.

The unresolved component is the simultaneous **atomic threshold process** plus local-weight rate.

### Why Dette–Wu does not directly close P6

A natural idea is:

\`\`\`text
Y_i(x)
=
1{X_i <= x}
\`\`\`

and then treat \(x\) as the functional coordinate in the 2026 confidence-surface theorem.

This is not valid under the published assumptions.

The paper requires differentiability/smoothness in its functional coordinate, while \(x\mapsto1\{X_i\le x\}\) is a step function.

Moreover, the paper's interior smoothing theory does not directly supply the exact latest-state one-sided EDF procedure required here.

### Why generic high-dimensional CLT is not enough yet

A deterministic finite threshold truncation can turn the problem into a large vector, and lattice structure makes such a route plausible.

However a valid final theorem would still need all of the following in one proof:

1. deterministic threshold-domain construction;
2. conservative tail remainder outside that threshold domain;
3. local one-sided weighted-array Gaussian approximation;
4. growing dimension from later states and thresholds;
5. cross-horizon and cross-anchor covariance;
6. localization bias;
7. latest-state coverage;
8. a computable critical-value approximation.

That complete chain has not been established in the reviewed sources or in a finished StockScope project lemma.

### Result

\`\`\`text
P6
=
BLOCKED_ALL_LATER_SIMULTANEOUS
\`\`\`

The blocker is now narrower:

> not anchor multiplicity, but all-later local EDF max inference under atomic threshold indexing and shrinking local weights.

---

## 11. P7 — Calibration

### Candidate families

Relevant families include:

\`\`\`text
high-dimensional Gaussian approximation
kernel long-run-covariance parametric bootstrap
block / multiplier bootstrap for maxima
specialized locally-stationary confidence-surface bootstrap
\`\`\`

But no calibration engine may be selected before the exact P3/P6 root is fixed.

In particular:

- Ma–Zhang 2026 is not a direct nonstationary local-EDF theorem;
- Chang–Chen–Wu's parametric bootstrap must be checked against the final weighted-array covariance and bandwidth profile;
- Dette–Wu's multiplier bootstrap is tied to their smooth functional-surface construction.

### Result

\`\`\`text
P7
=
BLOCKED_CALIBRATION
\`\`\`

Reason:

\`\`\`text
FINAL_ROOT_AND_RATE_CLASS_NOT_FROZEN
\`\`\`

---

## 12. P8 — Median / MAD projection

### Result

\`\`\`text
P8
=
CONDITIONALLY_RESOLVED
\`\`\`

Nothing found in D2D invalidates the R4 density-free deterministic projection.

If a simultaneous local CDF band exists for every required anchor/later/horizon index, the same event can be projected to:

- generalized median set;
- midpoint-median outer interval;
- center-aware raw-MAD outer interval;
- infinite endpoints where necessary;
- zero-scale fail-close semantics.

Therefore:

\`\`\`text
R4 D4
=
RETAIN_CONDITIONALLY
\`\`\`

No density derivative / unique-median assumption is reintroduced.

---

## 13. Proof ledger

| Proof Unit | D2D result | Blocking? |
| --- | --- | --- |
| P1 Atomic local transform | CONDITIONAL_PROJECT_LEMMA_RESOLVED | NO, conditional on model contract |
| P2 Local dependence | THEOREM_CLASS_IDENTIFIED / NOT FINAL-FROZEN | YES downstream |
| P3 Local EDF stochastic construction | BLOCKED_LOCAL_WEIGHT_RATE_COMPATIBILITY | **YES** |
| P4 Latest-state u=1 | CONSTRUCTION_IDENTIFIED / DEPENDENT_ON_P3 | YES downstream |
| P5 Finite-anchor coupling | RESOLVED_AT_ARCHITECTURE_LEVEL | NO |
| P6 ALL-LATER simultaneous | BLOCKED_ALL_LATER_SIMULTANEOUS | **YES** |
| P7 Calibration | BLOCKED_CALIBRATION | **YES** |
| P8 Median/MAD projection | CONDITIONALLY_RESOLVED | NO, conditional on band |

Therefore:

\`\`\`text
P1-P8
!=
RESOLVED

R5 method
!=
READY_FOR_FINAL_FREEZE
\`\`\`

---

## 14. CandidateDomain V2 disposition

No CandidateDomain change is required by D2D.

\`\`\`text
NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2
=
VALID / UNCHANGED

semantic hash
=
e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09
\`\`\`

The 18-anchor architecture succeeded at its intended job:

> it removed the open-ended every-integer anchor selection problem.

The remaining blocker is now orthogonal to candidate-grid governance.

---

## 15. What D2D did NOT do

\`\`\`text
reduce anchor count
NO

change grid spacing
NO

drop latest state
NO

sparsify later chronology
NO

replace TAIL with integrated drift
NO

jitter lattice observations
NO

assume continuous raw CDF
NO

pick bandwidth from DEV
NO

pick bootstrap because it gives favorable result
NO

run DEV
NO
\`\`\`

---

## 16. Next blocker-resolution task

The next task must target only the remaining stochastic root.

Recommended stage:

\`\`\`text
NEXT-6E-S6A-R5-D2D1
LOCAL-WEIGHTED ATOMIC MAX-INFERENCE RESOLUTION
\`\`\`

D2D1 should compare exactly two proof constructions.

### Route W1 — positive one-sided local constant + stronger undersmoothing

Goal:

- keep localized estimator a genuine CDF;
- use positive backward kernel;
- accept first-order time bias;
- derive a bandwidth class that simultaneously makes:
  - bias negligible;
  - physical-dependence high-dimensional Gaussian error vanish;
  - growing all-later/threshold dimension admissible.

If no nonempty rate interval exists:

\`\`\`text
W1
=
REJECT
\`\`\`

### Route W2 — second-order one-sided kernel + CDF band projection

Goal:

- cancel first-order bias using a signed one-sided kernel;
- prove high-dimensional rate compatibility;
- construct lower/upper envelopes and a monotone/clipped CDF band before median/MAD projection.

Must prove that the projection is coverage-preserving.

If both W1 and W2 fail:

\`\`\`text
R5 LOCAL DISTRIBUTIONAL ROUTE
=
ARCHITECTURE RECONSIDERATION REQUIRED
\`\`\`

D2D1 must not use DEV outcomes.

---

## 17. Final state

\`\`\`text
NEXT-6E-S6A-R5-D2D
=
BLOCKED_THEOREM_ROUTE_UNRESOLVED

P1
=
CONDITIONAL_PROJECT_LEMMA_RESOLVED

P2
=
THEOREM_CLASS_IDENTIFIED

P3
=
BLOCKED_LOCAL_WEIGHT_RATE_COMPATIBILITY

P4
=
CONSTRUCTION_IDENTIFIED / DEPENDENT_ON_P3

P5
=
RESOLVED_AT_ARCHITECTURE_LEVEL

P6
=
BLOCKED_ALL_LATER_SIMULTANEOUS

P7
=
BLOCKED_CALIBRATION

P8
=
CONDITIONALLY_RESOLVED

CandidateDomain V2
=
UNCHANGED / FROZEN

R5 method
=
NOT FROZEN

R5 G-A
=
BLOCKED

R5-D2E
=
NOT AUTHORIZED

R5-D3
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
\`\`\`
