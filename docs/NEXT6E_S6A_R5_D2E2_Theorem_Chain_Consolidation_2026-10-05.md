# StockScope NEXT-6E-S6A-R5-D2E2 — Theorem Chain Consolidation

작성일: 2026-10-05, Asia/Seoul  
문서 성격: R5 theorem-chain 실제 통합 검산 결과. 구현/DEV 평가 문서가 아니다.  
D2E2 시작 기준 main: \`3968e73cddff680e329c8f2699b66118a9a20ebb\`  
D2E2 concentration-contract correction commit: \`0d131a0f1a02dc453c755f4cec531c05b42816bb\`

CandidateDomain V2 semantic SHA256:

\`\`\`text
e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09
\`\`\`

Patched ConcentrationBand V1 semantic SHA256:

\`\`\`text
8a7097992b1fb89478a5d6079df55cc89c39385b6762b9b945ecc19c966f3c6d
\`\`\`

## 1. 쉬운 결론

지금까지 따로 설계한 R5 통계 부품을 하나의 method chain으로 다시 조립해 검산했다.

결론:

\`\`\`text
NEXT-6E-S6A-R5-D2E2
=
COMPLETE

P1-P8
=
CONSOLIDATED / INTERNALLY CONSISTENT

Full theorem chain
=
READY_FOR_FINAL_METHOD_FREEZE

Actual-process model-use
=
NOT YET ACCEPTED

Implementation
=
NOT AUTHORIZED
\`\`\`

D2E2에서 architecture를 다시 바꾸지는 않았다.

다만 D2E1 contract를 그대로 두면 최종 method에서 잘못 연결되는 세부사항이 있어 비architecture correction을 적용했다.

1. finite-memory depth는 항상 최소 1이 되도록 수정;
2. tail probability width는 finite sample에서 1을 넘지 않도록 clip;
3. R4의 symmetric \(\pm e\) CDF band 전용 median/MAD 식을 일반 \([L,U]\) CDF band용 직접 inversion으로 교체;
4. location/scale ratio의 denominator uncertainty를 명시적으로 fail-close;
5. finite-memory residue-class independence에 필요한 iid innovation base를 명시.

이 correction들은 CandidateDomain, TAIL target, all-later, latest-state 또는 A3 architecture를 바꾸지 않는다.

---

## 2. 최종 statistical target

Target ID:

\`\`\`text
NEXT6E_S6A_R5_LOCAL_TIME_REFERENCE_LAW_DRIFT_V1
\`\`\`

horizon:

\`\`\`text
h in {1,5,10}
\`\`\`

anchor:

\`\`\`text
s=N/n
\`\`\`

later state:

\`\`\`text
v=t/n
s < v <= 1
\`\`\`

local law:

\`\`\`text
F_h(u,x)
=
P{X_tilde_0^h(u) <= x}
\`\`\`

targets:

\`\`\`text
T_h(s,v)
=
sup_x |F_h(v,x)-F_h(s,x)|

L_h(s,v)
=
|m_h(v)-m_h(s)| / d_h(s)

S_h(s,v)
=
|d_h(v)-d_h(s)| / d_h(s)
\`\`\`

where \(m_h(u)\) is the midpoint generalized median and \(d_h(u)\) is the raw midpoint MAD around that median.

---

## 3. P1 — Atomic / lattice transfer

Final A3 method does **not** require the proof-only randomized distributional transform used in earlier R4/R5 research.

The final stochastic object is directly:

\`\`\`text
I{X_i^h <= x}
\`\`\`

on the observed integer lattice.

Therefore:

\`\`\`text
distributional transform
=
HISTORICAL PROOF SUPPORT
NOT A FINAL METHOD COMPONENT

implementation jitter
=
FORBIDDEN
\`\`\`

Atomic values and ties are handled directly.

P1 verdict:

\`\`\`text
P1 ATOMIC/LATTICE
=
PASS
\`\`\`

---

## 4. P2 — Final dependence bridge

D2E2 chooses the direct indicator finite-memory contract as the **final method assumption** rather than requiring two separate dependence assumptions.

Innovation base:

\`\`\`text
{epsilon_i}
=
iid innovations
\`\`\`

For:

\`\`\`text
Y_i(h,x)
=
I{X_i^h <= x}
\`\`\`

define:

\`\`\`text
Y_i^[d](h,x)
=
E[
 Y_i(h,x)
 |
 epsilon_i,...,epsilon_{i-d+1}
]
\`\`\`

and require:

\`\`\`text
sup_{n,i,h,x}
||Y_i(h,x)-Y_i^[d](h,x)||_1
<=
C_dep rho^d

C_dep < infinity
0 < rho < 1
\`\`\`

This contract is uniform over chronology, horizon and threshold.

The earlier geometric physical-dependence discussion remains a possible way to justify this assumption, but the final method does not require a second redundant primitive dependence contract.

Actual StockScope model-use acceptance of \(C_dep,\rho\) remains pending.

P2 verdict:

\`\`\`text
P2 DEPENDENCE BRIDGE
=
PASS AT METHOD LEVEL
MODEL-USE BINDING PENDING
\`\`\`

---

## 5. P3 — Backward discrete local-linear estimator

Aligned chronology length:

\`\`\`text
n
\`\`\`

numerical profile:

\`\`\`text
0 < beta < 1
w_n = ceil(n^(1-beta))
\`\`\`

For \(r=0,...,w-1\):

\`\`\`text
a_{r,w}
=
2(2w-1-3r)
/
[w(w+1)]
\`\`\`

Estimator:

\`\`\`text
Ftilde_h,t(x)
=
sum_{r=0}^{w-1}
a_{r,w}
I{X^h_{t-r} <= x}
\`\`\`

Exact finite-sample identities were rechecked:

\`\`\`text
sum a_r
=
1

sum r a_r
=
0

sum a_r^2
=
2(2w-1)
/
[w(w+1)]
<
4/w
\`\`\`

and:

\`\`\`text
sum |a_r|
<=
4
\`\`\`

is conservative but valid.

Thus constant level is preserved and first-order time drift cancels exactly.

P3 verdict:

\`\`\`text
P3 W2 ESTIMATOR
=
PASS
\`\`\`

---

## 6. P4 — Earliest anchor / latest-state boundary

CandidateDomain V2 minimum mapped anchor:

\`\`\`text
N_min(n)
=
ceil(n/10)
\`\`\`

The exact finite-sample structural rule is:

\`\`\`text
w_n
<=
N_min(n)
\`\`\`

At the earliest anchor \(t=N_min\):

\`\`\`text
t-w_n+1
>=
1
\`\`\`

so the entire backward window exists.

At latest state:

\`\`\`text
t=n
\`\`\`

the estimator uses only:

\`\`\`text
n-w_n+1,...,n
\`\`\`

and therefore uses no future observations.

The earlier right-boundary problem is absorbed by the backward estimator.

P4 verdict:

\`\`\`text
P4 BOUNDARY / LATEST STATE
=
PASS
\`\`\`

Failure if the finite-sample window does not fit:

\`\`\`text
INSUFFICIENT_LOCAL_WINDOW_DOMAIN
\`\`\`

---

## 7. P5 — CandidateDomain V2 consistency

CandidateDomain remains unchanged.

\`\`\`text
architecture
=
PROSPECTIVE_FINITE_ANCHOR_GRID

fractions
=
j/20
j=2,...,19

nominal anchors
=
18

integer mapping
=
ceil(j*n/20)

common-N
=
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR
\`\`\`

The local CDF band is computed per chronology-state/horizon/threshold and then reused by every approved anchor/later comparison.

Therefore anchor ID does not need to multiply the stochastic coordinate family.

Every approved anchor is itself one of the covered chronology states.

P5 verdict:

\`\`\`text
P5 CANDIDATE DOMAIN
=
PASS
\`\`\`

---

## 8. P6 — All-later simultaneous family

Threshold radius:

\`\`\`text
M_n
=
ceil(n^mu)

mu > 0
\`\`\`

central lattice thresholds:

\`\`\`text
-M_n <= x <= M_n
\`\`\`

A conservative stochastic-family size is:

\`\`\`text
p_n
<=
3 n (2 M_n + 1)
\`\`\`

covering:

\`\`\`text
all required chronology states
× 3 horizons
× central thresholds
\`\`\`

No later chronology subsampling is used.

Since every approved anchor and every later observed chronology state are inside the same CDF event, all approved anchor/later comparisons are protected before common-N selection.

P6 verdict:

\`\`\`text
P6 ALL-LATER
=
PASS AT METHOD LEVEL
\`\`\`

---

## 9. P7-A — Finite-memory approximation

For each coordinate let \(S\) be the centered weighted indicator sum and \(S^{[d]}\) its finite-memory version.

The centered replacement satisfies:

\`\`\`text
E|S-S^[d]|
<=
2 sum |a_r| C_dep rho^d
<=
8 C_dep rho^d
\`\`\`

Across \(p_n\) coordinates:

\`\`\`text
E max_j |S_j-S_j^[d]|
<=
8 p_n C_dep rho^d
\`\`\`

The corrected depth is:

\`\`\`text
d_n
=
max(
 1,
 ceil[
  log(16 p_n C_dep n / alpha_stat)
  /
  (-log rho)
 ]
)
\`\`\`

This guarantees:

\`\`\`text
P(
 max_j |S_j-S_j^[d_n]|
 >
1/n
)
<=
alpha_stat/2
\`\`\`

including the small-\(C_dep\) finite-sample case.

Thus:

\`\`\`text
epsilon_dep
=
1/n
\`\`\`

is valid.

---

## 10. P7-B — Residue blocking / Hoeffding

Because each \(Y_i^{[d_n]}\) is measurable only with respect to:

\`\`\`text
epsilon_i,...,epsilon_{i-d_n+1}
\`\`\`

and innovations are iid, observations separated by at least \(d_n\) have disjoint innovation blocks.

Partitioning a local window into \(d_n\) residue classes therefore gives independence inside each residue class.

Let:

\`\`\`text
Q_w
=
sum a_r^2
=
2(2w-1)/(w(w+1))
\`\`\`

Hoeffding plus two-sided / coordinate / residue-class union bounds gives:

\`\`\`text
epsilon_ind
=
d_n
sqrt{
 (Q_w/2)
 log(
 4 p_n d_n
 /
 alpha_stat
 )
}
\`\`\`

and:

\`\`\`text
P(
 max_j |S_j^[d_n]|
 >
epsilon_ind
)
<=
alpha_stat/2
\`\`\`

provided:

\`\`\`text
d_n <= w_n
\`\`\`

Otherwise:

\`\`\`text
FINITE_MEMORY_DEPTH_EXCEEDS_WINDOW
\`\`\`

is returned.

The probability accounting was rederived and no missing factor was found.

---

## 11. P7-C — Total stochastic event

Define:

\`\`\`text
epsilon_stoch
=
epsilon_ind
+
1/n
\`\`\`

Then:

\`\`\`text
P(
 max_required_coordinate
 |Ftilde-EFtilde|
 <=
epsilon_stoch
)
>=
1-alpha_stat
\`\`\`

under the bound method assumptions.

No covariance estimate, variance floor, Gaussian quantile or bootstrap is used.

---

## 12. P7-D — Local-law bias

Local marginal approximation:

\`\`\`text
sup_{i,h,x}
|
P(X_i^h<=x)-F_h(i/n,x)
|
<=
C_ls n^(-zeta)
\`\`\`

Second-time-derivative bound:

\`\`\`text
sup_{h,u,x}
|
partial_u^2 F_h(u,x)
|
<=
L2
\`\`\`

Using:

\`\`\`text
sum a=1
sum r a=0
sum |a|<=4
\`\`\`

and second-order Taylor remainder:

\`\`\`text
epsilon_bias
=
4 C_ls n^(-zeta)
+
2 L2 (w_n/n)^2
\`\`\`

is a valid conservative bound.

The coefficient \(2\) comes from:

\`\`\`text
1/2
×
sum |a_r|
×
max(r/n)^2
<=
2(w_n/n)^2
\`\`\`

so the D2E1 constant was confirmed.

---

## 13. P7-E — Full CDF tail coverage

Uniform tangent-law moment contract:

\`\`\`text
sup_{h,u}
E|Xtilde_h(u)|^q
<=
M_q
\`\`\`

Define:

\`\`\`text
tau_n
=
min(
 1,
 M_q/M_n^q
)
\`\`\`

For integer-valued features:

\`\`\`text
x < -M_n
→
F_h(u,x) <= tau_n

x > M_n
→
1-F_h(u,x) <= tau_n
\`\`\`

Finite-sample clipping at \(1\) is now explicit.

Integer threshold coverage extends to real \(x\) by:

\`\`\`text
F(x)
=
F(floor(x))
\`\`\`

for an integer-valued law.

Thus the full real CDF domain is covered; TAIL is not reduced to a central threshold sup.

---

## 14. P7-F — Raw and projected CDF band

Central width:

\`\`\`text
epsilon_core
=
epsilon_stoch
+
epsilon_bias
\`\`\`

Raw band:

central:

\`\`\`text
[
Ftilde-epsilon_core,
Ftilde+epsilon_core
]
\`\`\`

left tail:

\`\`\`text
[0,tau_n]
\`\`\`

right tail:

\`\`\`text
[1-tau_n,1]
\`\`\`

Projection:

\`\`\`text
L*(x)
=
max(
 0,
 sup_{y<=x} L_raw(y)
)

U*(x)
=
min(
 1,
 inf_{y>=x} U_raw(y)
)
\`\`\`

On the raw valid-band event:

\`\`\`text
L*(x)
<=
F(x)
<=
U*(x)
\`\`\`

for all \(x\).

A realized crossing returns:

\`\`\`text
EMPTY_PROJECTED_CDF_BAND
\`\`\`

P7 verdict:

\`\`\`text
P7 A3 CONCENTRATION BAND
=
PASS AT METHOD LEVEL
\`\`\`

---

## 15. Non-vacuity

For fixed bound model parameters and \(alpha_stat\in(0,1)\):

\`\`\`text
M_n
=
O(n^mu)

p_n
=
O(n^(1+mu))

d_n
=
O(log n)
\`\`\`

and:

\`\`\`text
Q_w
=
O(n^{-(1-beta)})
\`\`\`

therefore:

\`\`\`text
epsilon_ind
=
O(
 log(n)^(3/2)
 n^{-(1-beta)/2}
)

epsilon_dep
=
O(n^-1)

epsilon_bias
=
O(
 n^-zeta
 +
 n^-2beta
)

tau_n
=
O(n^-muq)
\`\`\`

Under:

\`\`\`text
0<beta<1
mu>0
zeta>0
q>0
0<rho<1
finite C_dep,C_ls,L2,M_q
\`\`\`

all widths vanish.

The finite-sample structural checks:

\`\`\`text
w_n>=2
w_n<=N_min(n)
d_n<=w_n
\`\`\`

remain mandatory.

---

## 16. P8-A — General CDF-band median inversion

The old R4 formula assumed a symmetric \(\|G-F\|_\infty\le e\) band.

A3 provides a general band:

\`\`\`text
L*(x)
<=
F(x)
<=
U*(x)
\`\`\`

so D2E2 replaces the old e-specific implementation formula with direct band inversion.

Define generalized quantiles:

\`\`\`text
q^-_G(p)
=
inf{x:G(x)>=p}

q^+_G(p)
=
inf{x:G(x)>p}
\`\`\`

Then:

\`\`\`text
q^-_{U*}(p)
<=
q^-_F(p)

q^+_F(p)
<=
q^+_{L*}(p)
\`\`\`

Therefore:

\`\`\`text
I_m(F)
=
[
 q^-_{U*}(1/2),
 q^+_{L*}(1/2)
]
\`\`\`

contains the entire generalized median set and hence the midpoint median.

This patch is deterministic and does not introduce a density assumption.

---

## 17. P8-B — General CDF-band MAD inversion

Let:

\`\`\`text
I_m=[m_lo,m_hi]
\`\`\`

be the median outer interval.

For \(r>=0\), define:

\`\`\`text
H_low(r)
=
max(
 0,
 inf_{m in I_m}
 [
  L*(m+r)
  -
  U*((m-r)-)
 ]
)
\`\`\`

and:

\`\`\`text
H_up(r)
=
min(
 1,
 sup_{m in I_m}
 [
  U*(m+r)
  -
  L*((m-r)-)
 ]
)
\`\`\`

For the true midpoint median \(m^\circ(F)\in I_m\):

\`\`\`text
H_low(r)
<=
P(
 |X-m^\circ(F)| <= r
)
<=
H_up(r)
\`\`\`

for every \(r\).

Therefore:

\`\`\`text
I_d(F)
=
[
 max(0,q^-_{H_up}(1/2)),
 q^+_{H_low}(1/2)
]
\`\`\`

contains the midpoint raw MAD.

If the upper quantile is not finite, \(+\infty\) is preserved.

If the median interval is unbounded, the construction may conservatively return:

\`\`\`text
[0,+infinity]
\`\`\`

No density / unique quantile assumption is added.

---

## 18. P8-C — TAIL interval

For anchor \(s\) and later state \(v\), at each \(x\):

\`\`\`text
D_x
=
F_v(x)-F_s(x)
\`\`\`

lies in:

\`\`\`text
[
 l_x,
 u_x
]
=
[
 L_v(x)-U_s(x),
 U_v(x)-L_s(x)
]
\`\`\`

Define:

\`\`\`text
a_low(x)
=
0
if l_x<=0<=u_x

otherwise
min(|l_x|,|u_x|)
\`\`\`

and:

\`\`\`text
a_up(x)
=
max(|l_x|,|u_x|)
\`\`\`

Then:

\`\`\`text
TAIL_lower
=
sup_x a_low(x)

TAIL_upper
=
sup_x a_up(x)
\`\`\`

satisfies:

\`\`\`text
TAIL_lower
<=
T_h(s,v)
<=
TAIL_upper
\`\`\`

The lower-bound direction was explicitly rechecked and is valid because \(T\) dominates every pointwise \(|D_x|\).

---

## 19. P8-D — Location / scale drift intervals

For intervals:

\`\`\`text
I=[a,b]
J=[c,d]
\`\`\`

define:

\`\`\`text
dist0(I,J)
=
max(
 0,
 c-b,
 a-d
)
\`\`\`

and:

\`\`\`text
distMax(I,J)
=
max(
 |a-c|,
 |a-d|,
 |b-c|,
 |b-d|
)
\`\`\`

with infinity propagated.

For location:

\`\`\`text
num_L
=
|m(v)-m(s)|
\`\`\`

use \(I_m(v),I_m(s)\).

For scale:

\`\`\`text
num_S
=
|d(v)-d(s)|
\`\`\`

use \(I_d(v),I_d(s)\).

If anchor MAD interval:

\`\`\`text
I_d(s)
=
[d_lo,d_hi]
\`\`\`

has:

\`\`\`text
d_lo <= 0
\`\`\`

return:

\`\`\`text
ANCHOR_SCALE_ZERO_NOT_EXCLUDED
\`\`\`

rather than divide.

If \(d_lo>0\), a valid ratio interval uses:

\`\`\`text
ratio_lower
=
numerator_lower / d_hi
\`\`\`

with value \(0\) if \(d_hi=+\infty\), and:

\`\`\`text
ratio_upper
=
numerator_upper / d_lo
\`\`\`

Thus the R5 population location/scale targets are connected without replacing their denominator definition.

P8 verdict:

\`\`\`text
P8 CDF / TAIL / MEDIAN / MAD / DRIFT
=
PASS
\`\`\`

---

## 20. Common-N post-selection

The CDF event is constructed over all required chronology states before candidate evaluation.

Candidate anchors are a deterministic subset of those states.

Therefore choosing later:

\`\`\`text
N*
=
minimum approved mapped anchor
satisfying final method + policy conditions
\`\`\`

does not create a new statistical post-selection event.

Official identity remains:

\`\`\`text
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR
\`\`\`

The method does not claim the minimum over every integer N.

---

## 21. Statistical / policy separation

The theorem layer owns:

\`\`\`text
alpha_stat

CDF band

TAIL interval

median interval

MAD interval

location / scale drift intervals
\`\`\`

The policy layer separately owns:

\`\`\`text
tau_T
tau_L
tau_S
\`\`\`

D2E2 does not assign those policy tolerances.

---

## 22. Parameter ownership

### Method assumptions / actual-process model-use inputs

\`\`\`text
C_dep
rho

C_ls
zeta

L2

q
M_q
\`\`\`

These must be bound and accepted for the actual process before evaluation.

### Numerical-profile inputs

\`\`\`text
beta
mu
\`\`\`

Allowed theorem region:

\`\`\`text
0<beta<1
mu>0
\`\`\`

No numerical values are chosen here.

### Statistical governance input

\`\`\`text
alpha_stat
in (0,1)
\`\`\`

No numerical value is chosen here.

---

## 23. Method validity vs model-use acceptance

D2E2 establishes only:

\`\`\`text
THEOREM CHAIN
=
INTERNALLY CONSISTENT CONDITIONAL ON DECLARED ASSUMPTIONS
\`\`\`

It does **not** establish:

\`\`\`text
C_dep,rho,C_ls,zeta,L2,q,M_q
are valid for the actual Development process
\`\`\`

Those are later model-use acceptance inputs.

This separation is mandatory and prevents repetition of the R4 A5/A6 mistake.

---

## 24. Failure semantics

Consolidated method-level states:

\`\`\`text
MODEL_PARAMETER_BINDING_MISSING
=
method/model-use prerequisite

INSUFFICIENT_LOCAL_WINDOW_DOMAIN
=
structural

FINITE_MEMORY_DEPTH_EXCEEDS_WINDOW
=
structural/method-profile

EMPTY_PROJECTED_CDF_BAND
=
statistical fail-close

ANCHOR_SCALE_ZERO_NOT_EXCLUDED
=
functional/ratio fail-close

OUTSIDE_R5_APPROVED_CANDIDATE_GRID
=
candidate-domain structural state

NO_ELIGIBLE_GRID_ANCHOR
=
candidate-domain structural state

STRUCTURALLY_INELIGIBLE_NO_LATER_STATE
=
candidate-domain structural state
\`\`\`

None of these states is automatically relabeled as reference inadequacy.

---

## 25. P1-P8 final ledger

| Unit | Final D2E2 result |
| --- | --- |
| P1 Atomic/lattice | PASS — direct indicator route; transform non-normative |
| P2 Dependence bridge | PASS — explicit indicator finite-memory method assumption; model-use binding pending |
| P3 W2 estimator | PASS |
| P4 earliest/latest boundary | PASS |
| P5 CandidateDomain V2 | PASS / unchanged |
| P6 all-later family | PASS |
| P7 A3 concentration band | PASS after nonarchitecture correction |
| P8 CDF/TAIL/median/MAD/location/scale projection | PASS after general-band inversion patch |

Therefore:

\`\`\`text
P1-P8
=
CONSOLIDATED
\`\`\`

---

## 26. Cross-contract ledger

\`\`\`text
CandidateDomain V2
vs
ConcentrationBand V1

anchor semantics
=
PASS

chronology semantics
=
PASS

latest-state
=
PASS

all-later
=
PASS

threshold semantics
=
PASS

candidate selection
=
PASS

parameter ownership
=
PASS

failure semantics
=
PASS AFTER D2E2 NORMALIZATION
\`\`\`

---

## 27. No hidden calibration / oracle quantity

The executable theorem-design formula contains no:

\`\`\`text
oracle local CDF
unknown covariance matrix
Gaussian critical quantile
bootstrap seed
hidden universal concentration constant
DEV-selected bandwidth
DEV-selected threshold range
\`\`\`

All non-observed inputs are explicitly classified as method/model-use, numerical-profile or governance inputs.

---

## 28. D2E2 correction scope

D2E2 patched:

\`\`\`text
docs/contracts/NEXT6E_S6A_R5_CONCENTRATION_BAND_V1.json
\`\`\`

only for nonarchitecture theorem-chain corrections.

Patched semantic SHA256:

\`\`\`text
8a7097992b1fb89478a5d6079df55cc89c39385b6762b9b945ecc19c966f3c6d
\`\`\`

CandidateDomain V2 was not modified.

No target, anchor, all-later, latest-state or calibration-architecture decision changed.

---

## 29. Access / execution boundary

\`\`\`text
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

backend/frontend/tests
=
UNCHANGED

Production
=
NONE
\`\`\`

---

## 30. Final state

\`\`\`text
NEXT-6E-S6A-R5-D2E2
=
COMPLETE

P1-P8
=
CONSOLIDATED / INTERNALLY CONSISTENT

CandidateDomain V2
=
VALID / UNCHANGED

ConcentrationBand V1
=
VALID / PATCHED WITH NONARCHITECTURAL CORRECTIONS

Statistical target
=
UNCHANGED

Full theorem chain
=
READY_FOR_FINAL_METHOD_FREEZE

Actual-process model-use parameters
=
UNBOUND

Numerical profile
=
UNBOUND

Statistical alpha
=
UNBOUND

R5 method
=
NOT YET FINAL-FROZEN

Implementation
=
NOT AUTHORIZED

Next stage
=
NEXT-6E-S6A-R5-D2E
FINAL METHOD CONTRACT FREEZE
\`\`\`
