# StockScope NEXT-6E-S6A-R5-GA1 — Independent Theorem Review

작성일: 2026-10-05, Asia/Seoul  
Review type: FROZEN-METHOD INDEPENDENT REDERIVATION  
Reviewer type: INTERNAL MODEL REDERIVATION — not external certification  
Baseline main: 1b295e476722b1774d40739af8418a09047330ba

## 1. Review target

Frozen method:

~~~text
NEXT6E_S6A_R5_LOCAL_REFERENCE_CONCENTRATION_V1
~~~

Final method semantic SHA256:

~~~text
6651a174e4b1c2cb92395bb9a2f3b122f49412a07f8b533f764be7cd48f89424
~~~

Design SHA256:

~~~text
351ba2d22352da821b5b3c7711dccc6553745945acd2c16c1b78678bb5a5f432
~~~

Bound CandidateDomain V2:

~~~text
e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09
~~~

Bound ConcentrationBand V1:

~~~text
8a7097992b1fb89478a5d6079df55cc89c39385b6762b9b945ecc19c966f3c6d
~~~

The frozen method and child contracts were treated as immutable during this review.

## 2. Final verdict

~~~text
NEXT-6E-S6A-R5-GA1
=
BLOCKED

P1-P8 mathematical re-derivation
=
NO DECISIVE MATHEMATICAL DEFECT FOUND

Hash bindings
=
PASS

Assumption ownership
=
MAJOR FINDING

G-A1
=
BLOCKED

G-A2
=
NOT AUTHORIZED

Implementation
=
NOT AUTHORIZED
~~~

The review does not reject the A3 method.

The blocker is that the frozen method's finite-memory proof requires an iid innovation-base representation, but the current G-A2 actual-process model-use schema does not explicitly require acceptance of that structural assumption.

This omission leaves a logical route by which the numerical model-use parameters could be approved without explicit approval of the representation required for the independence proof.

The issue is repairable without changing the estimator, CandidateDomain, statistical target, concentration formula, all-later semantics, or latest-state semantics.

It therefore receives:

~~~text
severity
=
MAJOR

not
=
DECISIVE
~~~

and forces GA1 to BLOCKED under the frozen review rule.

---

## 3. Independence statement

This review did not treat D2E1/D2E2 conclusions as proof.

The following were independently rederived:

- local-linear weight identities;
- finite-memory replacement bound;
- finite-memory depth formula;
- residue-class independence;
- Hoeffding probability constants;
- probability-budget allocation;
- bias constants;
- tail envelope;
- CDF projection;
- median inversion;
- MAD inversion;
- TAIL interval;
- location/scale ratio interval;
- all-later/common-N post-selection logic.

No Development outcome, Reference Adequacy result, passing anchor, Holdout, runtime DB, or Production result was used.

---

## 4. Literature boundary

Reviewed external foundations include:

1. Phandoidaen & Richter, *Empirical process theory for nonsmooth functions under functional dependence*.
   - supports locally stationary processes, nonsmooth classes, functional dependence, EDF applications, and nonasymptotic maximal-inequality theory;
   - does not provide the exact final StockScope finite-memory/Hoeffding band formula.

2. Phandoidaen & Richter, *Empirical process theory for locally stationary processes*.
   - supports the general locally stationary functional-dependence framework.

3. Hoeffding, *Probability Inequalities for Sums of Bounded Random Variables*.
   - supplies the independent bounded-sum inequality used after StockScope's project-specific finite-memory residue blocking.

The final StockScope concentration proof remains a project-specific lemma chain rather than a verbatim theorem copied from one paper.

---

## 5. Hash verification

The final method contract binds:

~~~text
CandidateDomain V2
=
e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09

ConcentrationBand V1
=
8a7097992b1fb89478a5d6079df55cc89c39385b6762b9b945ecc19c966f3c6d

Consolidated draft
=
1aa3664d921544a4eb1e2ab24669bc1da46f544b653caa6848c42db8aa38255d
~~~

No mismatch was found.

~~~text
HASH_BINDINGS
=
PASS
~~~

---

## 6. P1 — Atomic / lattice

Final method directly operates on:

~~~text
I{X_i^h <= x}
~~~

for integer-valued features.

For integer X:

~~~text
F(x)
=
F(floor(x))
~~~

so integer thresholds plus the declared tail regions cover the real threshold domain.

No continuity or density in x is used.

The earlier randomized distributional transform is not needed by the final A3 proof.

~~~text
P1
=
PASS
~~~

---

## 7. P2 — Finite-memory dependence theorem logic

Define:

~~~text
Y_i
=
I{X_i^h<=x}

Y_i^[d]
=
E[
Y_i
|
epsilon_i,...,epsilon_{i-d+1}
]
~~~

with the declared method assumptions:

~~~text
{epsilon_i}
=
iid innovations
~~~

and:

~~~text
||Y_i-Y_i^[d]||_1
<=
C_dep rho^d
~~~

uniformly over the required family.

Because Y_i^[d] is measurable with respect to:

~~~text
sigma(
epsilon_i,...,epsilon_{i-d+1}
)
~~~

two approximated variables with index difference at least d depend on disjoint innovation sets.

Example:

~~~text
j=i+d

block i
=
[i-d+1, i]

block j
=
[i+1, i+d]
~~~

which are disjoint.

Independence of the iid innovation blocks therefore implies independence of the two measurable finite-memory approximations.

No off-by-one defect was found.

~~~text
P2 THEOREM LOGIC
=
PASS
~~~

However P2 generates the cross-gate finding in Section 20 because the iid innovation-base assumption must also be accepted for the actual process before this theorem can be used.

---

## 8. P3 — Local-linear weights

For:

~~~text
a_{r,w}
=
2(2w-1-3r)
/
[w(w+1)]

r=0,...,w-1
~~~

direct summation gives:

~~~text
sum a_r
=
1
~~~

and:

~~~text
sum r a_r
=
0
~~~

The squared-weight sum is:

~~~text
Q_w
=
sum a_r^2
=
2(2w-1)
/
[w(w+1)]
~~~

and therefore:

~~~text
Q_w
<
4/w
~~~

For the maximum absolute weight, the linear sequence has its largest absolute magnitude at an endpoint, and:

~~~text
max |a_r|
<
4/w
~~~

Hence the conservative bound:

~~~text
sum |a_r|
<=
w max|a_r|
<
4
~~~

is valid.

~~~text
P3
=
PASS
~~~

---

## 9. P4 — earliest and latest boundaries

Earliest approved anchor:

~~~text
N_min(n)
=
ceil(n/10)
~~~

Frozen structural eligibility requires:

~~~text
w_n
<=
N_min(n)
~~~

so at t=N_min:

~~~text
t-w_n+1
>=
1
~~~

and the full backward window exists.

At the latest state t=n the estimator uses only:

~~~text
n-w_n+1,...,n
~~~

so future leakage is absent.

~~~text
P4
=
PASS
~~~

---

## 10. P5 — CandidateDomain

The review confirmed the frozen deterministic structure:

~~~text
j/20
j=2,...,19

N_j
=
ceil(j*n/20)
~~~

with mapped-integer deduplication and N<n structural eligibility.

The CandidateDomain is independent of stochastic outcomes.

~~~text
P5
=
PASS
~~~

---

## 11. P6 — simultaneous family and common-N

The local CDF event is indexed by:

~~~text
chronology state
×
horizon
×
threshold
~~~

not by anchor/later pairs.

This is valid because an anchor CDF is the same local CDF object already included at its chronology state.

Once the common event covers every required chronology state, every approved anchor/later comparison is a deterministic function of already-covered bands.

Therefore the stochastic family does not need an extra factor of 18 merely because 18 anchor labels exist.

Likewise, choosing the first supported approved anchor afterward does not introduce a new stochastic event because all candidate states were covered before selection.

~~~text
P6
=
PASS
~~~

---

## 12. P7-A — finite-memory replacement bound

For one weighted centered coordinate:

~~~text
S
=
sum a_i(Y_i-EY_i)

S^[d]
=
sum a_i(Y_i^[d]-EY_i^[d])
~~~

Then:

~~~text
E|
(Y_i-Y_i^[d])
-
E(Y_i-Y_i^[d])
|
<=
2 E|Y_i-Y_i^[d]|
<=
2 C_dep rho^d
~~~

and therefore:

~~~text
E|S-S^[d]|
<=
2 C_dep rho^d
sum |a_i|
<=
8 C_dep rho^d
~~~

Across p_n coordinates:

~~~text
E max_j |S_j-S_j^[d]|
<=
8 p_n C_dep rho^d
~~~

using max <= sum.

~~~text
P7-A
=
PASS
~~~

---

## 13. P7-B — finite-memory depth

The frozen depth:

~~~text
d_n
=
max(
 1,
 ceil[
  log(
   16 p_n C_dep n / alpha_stat
  )
  /
  (-log rho)
 ]
)
~~~

was checked in both regimes.

If:

~~~text
16 p_n C_dep n / alpha_stat
>=
1
~~~

then the ceiling ensures:

~~~text
rho^d_n
<=
alpha_stat
/
(16 p_n C_dep n)
~~~

and Markov gives:

~~~text
P(
max |S-S^[d_n]| > 1/n
)
<=
alpha_stat/2
~~~

If the logarithm argument is below one, d_n=1 and:

~~~text
8 p_n C_dep rho
<
8 p_n C_dep
<
alpha_stat/(2n)
~~~

so the same result holds.

~~~text
P7-B
=
PASS
~~~

---

## 14. P7-C — Hoeffding range

For an approximated indicator:

~~~text
0
<=
Y_i^[d]
<=
1
~~~

because it is a conditional expectation of a Bernoulli indicator.

Thus:

~~~text
Y_i^[d]-EY_i^[d]
~~~

lies in an interval of width exactly 1.

After multiplication by signed weight a_i, the interval width is:

~~~text
|a_i|
~~~

not 2|a_i|.

Therefore Hoeffding's squared-range denominator is the sum of a_i^2.

~~~text
P7-C
=
PASS
~~~

---

## 15. P7-D — residue-class Hoeffding constant

Partition the local window into d_n residue classes.

Within a residue class the finite-memory innovation blocks are disjoint and hence independent.

For one residue class c:

~~~text
P(
|S_c|>t
)
<=
2 exp(
 -2 t^2 / Q_c
)
~~~

with:

~~~text
Q_c
<=
Q_w
~~~

If:

~~~text
|sum_c S_c|
>
epsilon
~~~

then at least one class satisfies:

~~~text
|S_c|
>
epsilon/d_n
~~~

Therefore over p_n coordinates:

~~~text
P(
max_j |S_j^[d_n]| > epsilon
)
<=
2 p_n d_n
exp(
 -2 (epsilon/d_n)^2 / Q_w
)
~~~

Set:

~~~text
epsilon
=
d_n
sqrt(
 (Q_w/2)
 log(
 4 p_n d_n / alpha_stat
 )
)
~~~

Then the right side is exactly bounded by:

~~~text
alpha_stat/2
~~~

No missing two-sided, coordinate, residue or alpha-split factor was found.

~~~text
P7-D
=
PASS
~~~

---

## 16. P7-E — total stochastic probability

Finite-memory replacement consumes:

~~~text
alpha_stat/2
~~~

and residue-class Hoeffding consumes:

~~~text
alpha_stat/2
~~~

so the union bound gives:

~~~text
P(
all required central stochastic coordinates
within epsilon_stoch
)
>=
1-alpha_stat
~~~

where:

~~~text
epsilon_stoch
=
epsilon_ind
+
1/n
~~~

Bias and moment-tail bounds are deterministic conditional on the declared model assumptions and do not consume an additional probability budget.

~~~text
P7-E
=
PASS
~~~

---

## 17. P7-F — bias

Local marginal mismatch contributes:

~~~text
C_ls n^-zeta
sum |a_r|
<=
4 C_ls n^-zeta
~~~

For the local tangent law, a second-order expansion in rescaled time gives a remainder bounded by:

~~~text
(1/2)
L2
(r/n)^2
~~~

The exact first-moment cancellation:

~~~text
sum r a_r
=
0
~~~

removes the first-order term.

Thus:

~~~text
(1/2)L2
sum |a_r|(r/n)^2

<=
(1/2)L2
×4
×(w_n/n)^2

=
2 L2(w_n/n)^2
~~~

and the frozen:

~~~text
epsilon_bias
=
4 C_ls n^-zeta
+
2 L2(w_n/n)^2
~~~

is valid and conservative.

~~~text
P7-F
=
PASS
~~~

---

## 18. P7-G — tail envelope and non-vacuity

From:

~~~text
E|Xtilde_h(u)|^q
<=
M_q
~~~

Markov gives the declared two-sided tail bound:

~~~text
tau_n
=
min(
1,
M_q/M_n^q
)
~~~

for thresholds outside the central deterministic lattice range.

With:

~~~text
M_n
=
ceil(n^mu)
~~~

the family size is polynomial:

~~~text
p_n
=
O(n^(1+mu))
~~~

For fixed model parameters and fixed alpha_stat:

~~~text
d_n
=
O(log n)
~~~

and:

~~~text
Q_w
=
O(
n^{-(1-beta)}
)
~~~

so:

~~~text
epsilon_ind
=
O(
log(n)^(3/2)
n^{-(1-beta)/2}
)
~~~

while the other frozen rates also vanish under their declared domains.

~~~text
P7-G
=
PASS
~~~

Overall:

~~~text
P7
=
PASS
~~~

conditional on the frozen method assumptions.

---

## 19. P8 — functional projections

### CDF projection

If raw bands contain F pointwise, then for y<=x:

~~~text
L_raw(y)
<=
F(y)
<=
F(x)
~~~

so:

~~~text
sup_{y<=x}L_raw(y)
<=
F(x)
~~~

Similarly, for y>=x:

~~~text
F(x)
<=
F(y)
<=
U_raw(y)
~~~

so:

~~~text
F(x)
<=
inf_{y>=x}U_raw(y)
~~~

Clipping to [0,1] preserves the inequalities.

Result:

~~~text
CDF projection
=
PASS
~~~

### Median inversion

For:

~~~text
L<=F<=U
~~~

the upper CDF U reaches a probability level no later than F, while lower CDF L reaches it no earlier.

Thus:

~~~text
q^-_U(p)
<=
q^-_F(p)

q^+_F(p)
<=
q^+_L(p)
~~~

and:

~~~text
[
q^-_U(1/2),
q^+_L(1/2)
]
~~~

contains the complete generalized median set.

Result:

~~~text
median inversion
=
PASS
~~~

### MAD inversion

For any candidate center m in the median outer interval:

~~~text
H_F,m(r)
=
F(m+r)
-
F((m-r)-)
~~~

The CDF band implies:

~~~text
L(m+r)-U((m-r)-)
<=
H_F,m(r)
<=
U(m+r)-L((m-r)-)
~~~

The true midpoint median lies inside I_m, so taking infimum of lower bounds and supremum of upper bounds over m in I_m remains conservative.

The resulting H_low and H_up are nondecreasing in r.

Quantile inversion therefore gives:

~~~text
[
q^-_{H_up}(1/2),
q^+_{H_low}(1/2)
]
~~~

as an outer interval for the raw midpoint MAD, with +infinity allowed.

Result:

~~~text
MAD inversion
=
PASS
~~~

### TAIL interval

For each x the true CDF difference lies inside the difference interval.

Its absolute value is therefore bounded below by the distance of that interval from zero and above by the largest absolute endpoint.

Taking sup_x preserves:

~~~text
TAIL_lower
<=
sup_x |F_v-F_s|
<=
TAIL_upper
~~~

Result:

~~~text
TAIL projection
=
PASS
~~~

### Location / scale ratios

For a nonnegative numerator interval and positive anchor-MAD interval:

~~~text
num_low/d_hi
<=
num/d
<=
num_high/d_lo
~~~

If d_lo<=0 the frozen fail-close:

~~~text
ANCHOR_SCALE_ZERO_NOT_EXCLUDED
~~~

is required.

Result:

~~~text
location/scale projection
=
PASS
~~~

Overall:

~~~text
P8
=
PASS
~~~

---

## 20. MAJOR finding — assumption ownership / G-A2 completeness

Finding ID:

~~~text
GA1-F01
~~~

Severity:

~~~text
MAJOR
~~~

Frozen method assumption:

~~~text
A_R5_01_IID_INNOVATION_BASE
=
There exists an iid innovation sequence supporting
the finite-memory indicator representation.
~~~

This assumption is not merely decorative.

The P2/P7 independence proof explicitly relies on it:

~~~text
disjoint finite-memory innovation blocks
+
iid innovations
→
independent residue-class terms
→
Hoeffding
~~~

Therefore actual use of the method requires the declared StockScope process scope to be accepted as belonging to this innovation-representation class.

However the frozen G-A2 schema currently lists as required actual-process inputs only:

~~~text
C_dep
rho
C_ls
zeta
L2
q
M_q
~~~

and the model-use template likewise lacks an explicit:

~~~text
IID_INNOVATION_REPRESENTATION_ACCEPTED
~~~

field/check.

The template contains a general process_representation field and finite_memory_contract_supported check, but the gate contract does not make approval of A_R5_01 an explicit required acceptance item.

Consequently the current frozen gate could be interpreted as passing G-A2 without a recorded affirmative decision on the structural representation needed for the proof.

This is a governance/proof-interface gap.

It is not a failure of the finite-memory theorem itself.

Required resolution:

~~~text
GA2 actual-process model-use schema
must explicitly require acceptance/rejection
of A_R5_01_IID_INNOVATION_BASE
for the identical declared process scope.
~~~

Because GA1 is a frozen-method review, this review does not patch the method contract or template.

---

## 21. P1-P8 ledger

~~~text
P1 ATOMIC/LATTICE
=
PASS

P2 FINITE-MEMORY THEOREM LOGIC
=
PASS

P3 LOCAL-LINEAR ESTIMATOR
=
PASS

P4 EARLIEST/LATEST BOUNDARY
=
PASS

P5 CANDIDATE DOMAIN
=
PASS

P6 ALL-LATER / POST-SELECTION
=
PASS

P7 EXPLICIT CONCENTRATION
=
PASS

P8 FUNCTIONAL PROJECTIONS
=
PASS
~~~

No DECISIVE mathematical finding was identified.

---

## 22. Review findings ledger

| ID | Severity | Area | Finding | Disposition |
| --- | --- | --- | --- | --- |
| GA1-F01 | MAJOR | Assumption ownership / G-A2 | iid innovation-base representation is proof-critical but not an explicit actual-process model-use acceptance item | BLOCKING |
| GA1-F02 | INFO | Literature boundary | Final finite-memory/Hoeffding band is project-specific, not a verbatim published theorem | DOCUMENTED |
| GA1-F03 | INFO | Review independence | This is frozen-method internal rederivation, not external human/institutional certification | DOCUMENTED |

---

## 23. Final verdict logic

The frozen theorem-review PASS rule requires:

~~~text
all P1-P8 PASS
and
no unresolved MAJOR finding
and
no DECISIVE finding
~~~

Although P1-P8 pass, GA1-F01 is an unresolved MAJOR finding.

Therefore:

~~~text
final_verdict
=
BLOCKED
~~~

not PASS.

The method is not REJECTED because no core mathematical claim was found false.

---

## 24. Gate state after GA1

~~~text
G-A0 METHOD FREEZE
=
PASS

G-A1 INDEPENDENT THEOREM REVIEW
=
BLOCKED

G-A2 MODEL USE
=
NOT AUTHORIZED TO START AS CURRENT SCHEMA

G-A3 NUMERICAL PROFILE
=
PENDING

G-A4 STATISTICAL GOVERNANCE
=
PENDING

G-A
=
BLOCKED

D3 IMPLEMENTATION
=
NOT AUTHORIZED
~~~

---

## 25. Required next task

~~~text
NEXT-6E-S6A-R5-GA1-BR1
ASSUMPTION-OWNERSHIP BLOCKER RESOLUTION
~~~

Scope must be narrow:

1. decide the exact G-A2 ownership of A_R5_01_IID_INNOVATION_BASE;
2. make model-use acceptance explicitly cover it;
3. preserve the frozen estimator, concentration formula, CandidateDomain, targets, all-later and latest-state semantics;
4. version/amend governance artifacts as required rather than silently editing historical approval state;
5. rerun GA1 only for the affected cross-gate finding and hash consistency.

GA2 must not begin until this blocker is resolved.

---

## 26. Access boundary

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

backend/frontend/tests
=
UNCHANGED

Production
=
NONE
~~~

## 27. Final state

~~~text
NEXT-6E-S6A-R5-GA1
=
BLOCKED

Frozen method
=
NOT MODIFIED

Mathematical theorem chain
=
NO DECISIVE DEFECT FOUND

Decisive blocker
=
NONE

Major blocker
=
GA1-F01 ASSUMPTION OWNERSHIP / G-A2 COMPLETENESS

Next
=
NEXT-6E-S6A-R5-GA1-BR1
~~~
