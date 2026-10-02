# StockScope NEXT-6E-S6A-R1 — Sequential Functional Theorem Resolution

## 1. Status / Research Baseline

- Date: 2026-10-02, Asia/Seoul.
- Stage: **NEXT-6E-S6A-R1 Sequential Functional Theorem Resolution**.
- Artifact: source-only statistical-theory resolution.
- Research base: `dd310f2a7528e44bb5cf8df31b9921e9467b7582`.
- Parent state: `METHOD_DESIGNED / G-A BLOCKED`.
- S6B state: `POLICY_DESIGNED / G-B BLOCKED`.
- V3: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`.
- Implementation / V4 / evaluator / Development evaluation: **NOT AUTHORIZED**.
- Holdout: **LOCKED / NOT ACCESSED**.
- Production impact: **NONE**.

```text
NEXT-6E-S6A-R1 = COMPLETE

Method state = METHOD_DESIGNED
G-A = BLOCKED

Route = SEQUENTIAL_DEPENDENT_MULTIPLIER
Route verdict = CONDITIONALLY_SUPPORTED

Revised target = TARGET_CONDITIONALLY_ACCEPTED
Process class = EXACT_THEOREM_CLASS_DEFINED
Representation = JOINT_3D_FEATURE_PROCESS_CONDITIONALLY_ACCEPTED

Sequential empirical process = SUPPORTED
Dependent multiplier = SUPPORTED_CONDITIONALLY
ECDF transfer = SUPPORTED_CONDITIONALLY
Median transfer = SUPPORTED_CONDITIONALLY
MAD transfer = SUPPORTED_CONDITIONALLY
Ratio mapping = SUPPORTED_CONDITIONALLY
Nested envelope = SUPPORTED_ON_INTERIOR_DOMAIN
All-N simultaneous inference = SUPPORTED_ON_INTERIOR_DOMAIN
Common-N post-selection = SUPPORTED_CONDITIONALLY

Automatic bandwidth = SELECTOR_CONDITIONALLY_JUSTIFIED / NOT FROZEN
Candidate domain = INTERIOR_DOMAIN_REQUIRED / κ UNRESOLVED
Suffix sufficiency = PROCEDURE_RELATIVE / NOT EXECUTABLE
Actual-process assumptions = NOT VERIFIED

γ_repeat = REMOVE_FROM_METHOD_CONTRACT / REDEFINE_AS_SEPARATE_POLICY_CONCEPT

Reference Adequacy = UNRESOLVED
```

R1 does not promote the method to METHOD_APPROVED. The remaining blockers are candidate-domain governance, the exact reproducible multiplier/bandwidth profile, and later actual-process assumption acceptance.

---

## 2. S6A Gap Register

S6A left the following Track-A gaps:

1. law-level target G_R(P) / C_stat(D) was stronger than the reviewed theory;
2. exact process/dependence class was unresolved;
3. automatic selector was unresolved;
4. dependent sequential MAD transfer was unresolved;
5. full finite candidate domain was unsupported;
6. simultaneous all-N inference was missing;
7. common-N post-selection was conditional only;
8. suffix sufficiency was not executable.

R1 focuses only on this theorem chain:

```text
joint horizon feature process
→ sequential empirical process
→ dependent multiplier process
→ ECDF / median / MAD functional mapping
→ nested envelope
→ simultaneous interior-domain inference
→ minimum common-N selection
```

---

## 3. Revised Statistical Target

R1 does not revive a confidence region for the complete finite-record law G_R(P).

The reviewed literature directly supports weak approximation of sequential empirical processes and regular functionals derived from them, not a confidence set for the entire unknown law of the complete envelope array.

The revised target is:

```text
JOINT_SEQUENTIAL_FUNCTIONAL_SAMPLING_FLUCTUATION
```

under a scoped stationary dependent model.

Let the aligned feature vector be:

```text
Z_i = (X_i^(1), X_i^(5), X_i^(10)) ∈ R^3
```

and F its stationary joint distribution.

Define the sequential empirical partial-sum process:

```text
B_n(s,x)
=
n^(-1/2)
Σ_{i=1}^{floor(ns)}
{ 1(Z_i ≤ x) - F(x) }

s ∈ [0,1]
x ∈ R^3
```

where ≤ is componentwise.

Each horizon marginal empirical process is obtained from the same joint process. Prefix empirical distributions introduce a normalization proportional to 1/s, so the direct continuous-mapping route is valid only on an index set bounded away from s=0.

The transformed target contains:

- ECDF prefix differences;
- median prefix differences;
- MAD prefix differences;
- normalized median ratios;
- relative MAD ratios;
- nested later-prefix envelopes;
- every method-eligible anchor fraction.

This is a stationary sampling-fluctuation claim. It is not a claim that future market regimes remain stationary.

Verdict:

```text
TARGET_CONDITIONALLY_ACCEPTED
```

Conditions:
- theorem-supported interior candidate domain;
- accepted process/regularity assumptions;
- frozen multiplier/bandwidth profile;
- explicit asymptotic/stationary scope.

---

## 4. Exact Process Class

S6A proposed native one-observation increments:

```text
W_i = 100 × (Y_i - Y_{i-1})
```

with finite-window features:

```text
X_i^(h) = Σ_{j=0}^{h-1} W_{i-j}
h ∈ {1,5,10}
```

when all required native positions exist.

For theorem work, R1 uses one aligned three-dimensional process:

```text
Z_i = (X_i^(1), X_i^(5), X_i^(10))
```

rather than separately resampling each horizon.

If W is strictly stationary, a fixed finite-window measurable transform is strictly stationary.

Because Z_i is measurable with respect to σ(W_{i-9},...,W_i), sigma-field inclusion gives, for r>9:

```text
α_Z(r) ≤ α_W(r-9)
```

so a polynomial strong-mixing exponent transfers through this finite-window construction.

Bücher and Kojadinovic's dependent-multiplier theorem for a continuous d-dimensional strictly stationary strong-mixing sequence requires:

```text
α_Z(r) = O(r^(-a))
a > 3 + 3d/2
```

For d=3:

```text
a > 15/2
```

R1 therefore defines the theorem class:

```text
STRICTLY_STATIONARY_STRONG_MIXING_JOINT_FEATURE_PROCESS

dimension = 3
α_Z(r) = O(r^(-a))
a > 15/2
joint distribution = continuous
marginal regularity = functional-specific
```

Equivalent primitive proposal:

```text
W strictly stationary
α_W(r) = O(r^(-a)), a>15/2
native positions complete
Z well-defined as the fixed finite-window transform
joint Z distribution continuous
```

Actual process acceptance is not performed here:

```text
THEOREM CLASS = DEFINED
ACTUAL PROCESS ACCEPTANCE = UNRESOLVED
ASSUMPTION VERIFIED = NO
```

---

## 5. Representation / Missingness

The joint 3D process is preferred because one path preserves:

- serial dependence;
- overlapping-window dependence;
- contemporaneous cross-horizon dependence;
- shared multiplier randomness.

Required:

```text
JOINT_NATIVE_POSITION_COMPLETENESS
```

after declared warmup.

Forbidden:
- silently dropping one horizon independently;
- compressing chronology;
- interpolation;
- calendar filling;
- reconstructing missing native increments;
- independent horizon resampling.

If the source contract cannot supply the required native positions, this route fails closed or requires a separately justified missing-data method.

Verdict:

```text
JOINT_3D_FEATURE_PROCESS
=
REPRESENTATION_CONDITIONALLY_ACCEPTED
```

---

## 6. Sequential Empirical-Process Basis

Bücher (2014) establishes weak convergence of the multivariate sequential empirical process under polynomial strong mixing.

Bücher and Kojadinovic (2016), Theorem 2.1 and Corollary 2.2, establish joint weak convergence of the observed sequential empirical process and dependent-multiplier copies under stronger mixing and multiplier conditions.

For the R1 d=3 joint feature process, this supplies an explicit base-process theorem route.

```text
SEQUENTIAL_EMPIRICAL_PROCESS = SUPPORTED
DEPENDENT_MULTIPLIER_BASE_PROCESS = SUPPORTED_CONDITIONALLY
```

The condition is that the stated process class and multiplier profile are actually satisfied.

---

## 7. Dependent Multiplier Contract

The future multiplier sequence must follow the selected theorem's requirements, including:

- strict stationarity of multiplier sequence;
- zero mean and unit variance;
- required uniformly bounded moments;
- independence from observed data;
- finite dependence controlled by ℓ_n;
- covariance kernel of the theorem-compatible form;
- ℓ_n → ∞;
- theorem-specific upper growth restriction.

One multiplier realization applies to the entire joint vector sequence.

Forbidden absent a new coupling proof:

```text
separate multiplier stream per horizon
separate stream per functional
separate stream per N
separate stream per later prefix t
```

Future implementation must freeze the exact centering rule consistent with the selected theorem/corollary rather than invent a prefix-centering variant.

---

## 8. Automatic Bandwidth / Selector

The dependent-multiplier theorem permits a class of asymptotically admissible bandwidth sequences.

Bücher and Kojadinovic also derive an IMSE-oriented bandwidth analysis for long-run covariance approximation. Its leading bias/variance orders yield an n^(1/5) optimal rate for that objective.

This gives a non-arbitrary theoretical basis for bandwidth research, but it does not by itself freeze one complete StockScope selector.

The practical data-adaptive procedure still needs a reproducible profile for:
- covariance-sum estimation;
- lag cutoff;
- flat-top/lag window;
- multiplier covariance kernel;
- numerical grid/integration;
- multivariate aggregation choices;
- multiplier construction.

Critical distinction:

```text
theorem-admissible bandwidth
≠
uniquely justified whole-StockScope selector
```

The full StockScope family contains ECDF sup, median, MAD, ratios, nested envelopes and candidate-N selection. R1 does not claim that an IMSE optimum for covariance approximation is uniquely optimal for that complete nonlinear family.

Verdict:

```text
AUTOMATIC BANDWIDTH
=
SELECTOR_CONDITIONALLY_JUSTIFIED

FULL EXECUTABLE SELECTOR PROFILE
=
NOT FROZEN
```

This remains a G-A blocker.

---

## 9. ECDF Sup Transfer

For horizon h and prefix fractions s,t, the prefix empirical-cdf difference is a coordinate-marginal functional of the joint sequential empirical process.

On an interior domain s≥κ>0, the prefix-normalization map is bounded and continuous.

The map:

```text
f ↦ sup_x |f(x)|
```

is Lipschitz in sup norm.

The theorem chain is:

```text
dependent-multiplier sequential empirical process
→ horizon marginal projection
→ normalized two-prefix difference
→ sup norm
→ joint multiplier approximation
```

Verdict:

```text
ECDF_SUP_TRANSFER
=
SUPPORTED_CONDITIONALLY
```

conditioned on the interior candidate domain and process assumptions.

---

## 10. Median Functional Transfer

Let m_h be the unique population median of horizon h.

Required regularity includes:

```text
F_h locally continuous/differentiable at m_h
f_h(m_h) > 0
m_h unique
```

For empirical-cdf perturbation g_h, the usual quantile first-order map is:

```text
D Med_F[g_h]
=
- g_h(m_h) / f_h(m_h)
```

Thus the median process can be obtained as a functional-delta/Bahadur mapping of the sequential empirical process on the regular domain.

Dependent quantile Bahadur literature supports the regular median component under mixing conditions, but R1 still requires the common process assumptions to be reconciled at final approval.

Verdict:

```text
MEDIAN_TRANSFER
=
SUPPORTED_CONDITIONALLY
```

---

## 11. MAD Functional Transfer

Define:

```text
m = Med(F)
d = MAD(F) = Med(|X-m|)
```

For continuous F around the required points, d solves:

```text
F(m+d) - F(m-d) = 1/2
```

For cdf perturbation g:

```text
m'[g] = -g(m)/f(m)
```

Differentiating the MAD defining relation gives the candidate first-order map:

```text
d'[g]
=
-
[
  g(m+d) - g(m-d)
  +
  {f(m+d)-f(m-d)} m'[g]
]
/
[
  f(m+d)+f(m-d)
]
```

provided:

```text
f(m) > 0
f(m+d)+f(m-d) > 0
d > 0
```

and the required local smoothness holds.

Mazumder and Serfling establish sample-MAD Bahadur representations and joint median/MAD asymptotic structure. Their paper is not itself the exact dependent sequential multiplier theorem needed here.

R1's transfer is therefore explicitly a derived chain:

```text
sequential empirical-process theorem
+
regular median/MAD functional map
+
functional delta / continuous mapping
+
same mapping on multiplier copies
```

No new nonregular theorem is claimed.

Verdict:

```text
MAD_TRANSFER
=
SUPPORTED_CONDITIONALLY_WITH_EXPLICIT_REGULAR_DOMAIN
```

This materially narrows the S6A MAD blocker.

---

## 12. Ratio Mapping / Zero Scale

Research metrics are:

```text
L_h,n(s,t)
=
|m_h(t)-m_h(s)| / d_h(s)

S_h,n(s,t)
=
|d_h(t)-d_h(s)| / d_h(s)
```

On the regular population domain d_h>0, the ratio mapping is continuous locally.

This does not erase finite-sample zero MAD.

Executable semantic remains:

```text
sample anchor MAD == 0
→ NON_COMPUTABLE_ZERO_SCALE
```

No epsilon rescue.

A future direct nonlinear resampling implementation must not silently delete zero-denominator replicates. A future linearized multiplier implementation must state that it operates under the regular population domain and retain the separate finite-sample non-computability state.

Verdict:

```text
ZERO_SCALE
=
OUTSIDE_REGULAR_FUNCTIONAL_DOMAIN
+
FINITE_NON_COMPUTABLE_STATE_PRESERVED
```

---

## 13. Multi-Horizon Mapping

The joint observation:

```text
Z_i = (X_i^1, X_i^5, X_i^10)
```

carries cross-horizon and overlapping-window dependence into one empirical process.

TAIL, median and MAD are horizon-marginal functionals of the joint law and are extracted through coordinate projection/marginalization.

Verdict:

```text
MULTI_HORIZON_MAPPING
=
SUPPORTED_CONDITIONALLY
```

subject to native completeness and the common theorem class.

---

## 14. Candidate-N Domain

This is the main unresolved mathematical-design boundary.

The structural candidate concept includes anchors as small as N=1.

The raw sequential partial-sum process exists at s=0, but normalized prefix empirical distributions introduce:

```text
1/s
```

with s=N/n.

Therefore the standard continuous-mapping route is singular as s→0.

R1 does not find theorem support for uniform normalized-prefix inference over the full finite domain N=1,...,n-1.

The direct theorem-supported route is an interior domain:

```text
I_κ = [κ,1]
κ > 0 fixed
```

with pair domain:

```text
Δ_κ = {(s,t): κ ≤ s ≤ t ≤ 1}
```

and finite candidates:

```text
C_n(κ)
=
{ N : ceil(κ n) ≤ N ≤ n-1 }
```

after final horizon/source alignment.

The theorem requires κ>0 but does not identify a unique operational κ.

R1 has no independent basis for choosing 0.1, 0.2, 0.5, or any other value. κ must not be chosen from observed passing-N behavior.

A weighted-boundary process is a possible separate research route if no defensible interior κ can be frozen, but R1 has not established the nonlinear StockScope mapping for that route.

Verdict:

```text
CANDIDATE_DOMAIN
=
INTERIOR_DOMAIN_REQUIRED

κ
=
UNRESOLVED_METHOD_PARAMETER
```

This is a decisive G-A blocker.

---

## 15. Nested Forward Envelope

For eligible anchor s:

```text
E_h,q,n(s)
=
sup_{t ∈ [s,1]}
R_h,q,n(s,t)
```

on Δ_κ.

The supremum map is Lipschitz in sup norm:

```text
|sup f - sup g|
≤
sup |f-g|
```

Therefore, once the underlying transformed process is uniformly defined on the compact interior domain, the nested-envelope operation does not require a separate resampling theorem.

Verdict:

```text
NESTED_FORWARD_ENVELOPE
=
SUPPORTED_ON_INTERIOR_DOMAIN
```

---

## 16. Simultaneous All-N Inference

The sequential-process route avoids separate pointwise confidence intervals for each N.

If the transformed functional process converges jointly over:

```text
horizon
× functional
× Δ_κ
```

then one max/sup root can cover:

```text
3 horizons
× 3 required functionals
× all eligible anchors
× all later prefixes
```

inside one asymptotic simultaneous event.

Thus candidate-N multiplicity can be part of the indexed process rather than corrected after separately testing each N.

The exact final root/normalization and α_stat remain unfrozen.

Verdict:

```text
ALL_N_SIMULTANEOUS_INFERENCE
=
SUPPORTED_IN_STRUCTURE
ON_INTERIOR_DOMAIN
```

---

## 17. Common-N Post-Selection

Suppose one valid simultaneous event covers all eligible candidates:

```text
E_sim
=
{
 all required statistical bounds
 hold for every N ∈ C_n(κ)
}
```

and define:

```text
A
=
{
 N ∈ C_n(κ):
 all required families satisfy
 separately approved policy criteria
}
```

Then:

```text
N* = min A
```

does not require a new pointwise inference step. On E_sim, every candidate in A is already protected by the simultaneous event.

If A is empty, no supported boundary exists.

Verdict:

```text
COMMON_N_POST_SELECTION
=
SUPPORTED_CONDITIONALLY
```

conditioned on the final simultaneous process/bound.

---

## 18. Suffix Sufficiency

No arbitrary standalone K is introduced.

A candidate is statistically evaluable only if:

1. it lies in the frozen candidate domain;
2. later-prefix support required by the method exists;
3. all required joint horizon features exist;
4. functional computability/regularity requirements hold;
5. the approved simultaneous method applies.

Proposed states:

```text
SUFFICIENT
INSUFFICIENT_EVIDENCE
NON_COMPUTABLE
UNRESOLVED_METHOD
```

Because κ and the exact method profile remain unfrozen:

```text
EXECUTABLE_SUFFIX_RULE
=
UNRESOLVED
```

---

## 19. Statistical Claim

Forbidden claim:

```text
not significantly different
→ adequate
```

Forbidden interpretation:

```text
stationary-model inference
→ future structural stability certified
```

Proposed statistical statement:

> Under the approved stationarity/dependence and regularity contract, and over the approved interior sequential candidate domain, the joint sampling-fluctuation process for the declared ECDF, robust-location and robust-scale reference functionals is covered by the approved simultaneous inference procedure at the separately governed family-wide statistical support level.

Operational adequacy additionally requires separately approved movement thresholds.

This claim is asymptotic, conditional on assumptions, simultaneous over the approved domain, and unrelated to Production performance.

---

## 20. S6B Compatibility

R1 returns:

```text
target
=
JOINT_SEQUENTIAL_FUNCTIONAL_SAMPLING_FLUCTUATION

candidate domain
=
INTERIOR_DOMAIN_REQUIRED
κ UNRESOLVED

statistical event
=
SIMULTANEOUS_JOINT_FUNCTIONAL_COVERAGE
OVER_APPROVED_INTERIOR_DOMAIN

τ_T / τ_L / τ_S
=
separate operational thresholds
METHOD_INTERFACE_DEPENDENT

α_stat
=
policy-owned family-wide support/error appetite
for the final simultaneous event
```

No numeric policy value is created.

---

## 21. γ_repeat Disposition

The old γ_repeat concept was tied to recurrence on a fresh finite record under the rejected law-level target.

The revised method target is a direct sequential-functional sampling-fluctuation process.

Therefore:

```text
γ_repeat
=
REMOVE_FROM_METHOD_CONTRACT
```

If Product/Risk Governance still wants a finite-horizon recurrence-risk concept, Track B may define a separate event and policy later.

It must not be silently merged into α_stat.

```text
γ_repeat disposition
=
REDEFINE_AS_SEPARATE_FUTURE_POLICY_CONCEPT

value = null
```

---

## 22. Research-Final Contract Drafts

### 22.1 ReferenceAdequacyMethodContract / R1

```text
status
=
METHOD_DESIGNED / G-A_BLOCKED

target
=
JOINT_SEQUENTIAL_FUNCTIONAL_SAMPLING_FLUCTUATION

observation_process
=
aligned 3D horizon feature vector

dependence
=
strict stationarity
strong mixing
α(r)=O(r^-a)
a>15/2

regularity
=
continuous joint distribution
unique marginal medians
positive marginal density at medians
positive population MAD
positive f(m+d)+f(m-d)
required local smoothness

candidate_domain
=
[κ,1]
κ>0
κ UNRESOLVED

resampling
=
SEQUENTIAL_DEPENDENT_MULTIPLIER

bandwidth
=
THEOREM_ADMISSIBLE
AUTOMATIC_PROFILE_NOT_FROZEN

joint_family
=
3 horizons
× TAIL / normalized median / relative MAD
× all eligible anchors
× nested later prefixes

selection
=
smallest common N after one valid simultaneous event

zero_scale
=
NON_COMPUTABLE_ZERO_SCALE

coverage
=
ASYMPTOTIC / CONDITIONAL / INTERIOR_DOMAIN
```

### 22.2 DependenceAssumptionContract / R1

```text
process
=
Z_i=(X_i^1,X_i^5,X_i^10)

primitive proposal
=
native one-observation W_i increments

stationarity
=
STRICT

dependence
=
STRONG_MIXING

rate
=
α_Z(r)=O(r^-a), a>15/2

primitive transfer
=
α_Z(r)≤α_W(r-9), r>9

continuity
=
joint Z distribution continuous

actual acceptance
=
UNRESOLVED
```

### 22.3 SequentialResamplingContract / R1

```text
engine
=
DEPENDENT_MULTIPLIER

shared multiplier process
=
REQUIRED

multiplier assumptions
=
THEOREM_COMPATIBLE

bandwidth
=
THEOREM_COMPATIBLE
EXACT PRACTICAL PROFILE UNRESOLVED

separate horizon/function/N/window streams
=
FORBIDDEN

native missingness repair
=
FORBIDDEN
```

### 22.4 JointInferenceContract / R1

```text
index
=
h × q × Δ_κ

TAIL
=
sup-norm map of prefix empirical-cdf difference

median
=
quantile functional derivative

MAD
=
joint median/MAD functional derivative

ratios
=
regular-domain continuous map

nested envelope
=
sup over later t

simultaneous candidate coverage
=
one joint indexed-process event

common-N
=
minimum admissible candidate after simultaneous event

alpha_stat
=
symbolic policy input
```

### 22.5 CandidateDomainContract / R1

```text
type
=
INTERIOR_FRACTION_DOMAIN

domain
=
κ ≤ N/n < 1

κ
=
UNRESOLVED

full N=1..n-1
=
NOT_THEOREM_SUPPORTED_BY_THIS_ROUTE
```

### 22.6 SuffixSufficiencyContract / R1

```text
type
=
PROCEDURE_RELATIVE

requires
=
approved candidate domain
later-prefix support
joint feature availability
functional computability
approved method applicability

standalone K
=
NONE

status
=
UNRESOLVED UNTIL κ/METHOD FREEZE
```

---

## 23. Functional Transfer Matrix

| Functional | Process support | Mapping | Sequential | All-N interior | Verdict |
| --- | --- | --- | --- | --- | --- |
| ECDF sup | Direct | Sup-norm continuous map | YES | YES | CONDITIONALLY SUPPORTED |
| Median | Marginal cdf | Quantile derivative / Bahadur | YES | YES | CONDITIONALLY SUPPORTED |
| MAD | Marginal cdf | Joint median/MAD derivative | YES by derived mapping | YES | CONDITIONALLY SUPPORTED |
| Normalized median ratio | Joint median/MAD | Continuous if MAD>0 | YES | YES | CONDITIONALLY SUPPORTED |
| Relative MAD ratio | Joint MAD | Continuous if MAD>0 | YES | YES | CONDITIONALLY SUPPORTED |

No robustness to atoms, nonunique medians, or zero population scale is claimed.

---

## 24. Candidate-Domain Matrix

| Domain | Theory fit | Boundary issue | Selection-safe? | Extra parameter | Verdict |
| --- | --- | --- | --- | --- | --- |
| N=1..n-1 | Poor | 1/s singularity | Not established | none | NOT SUPPORTED |
| Fixed interior κ≤N/n<1 | Direct | removed by κ>0 | YES conditionally | κ | PREFERRED / κ UNRESOLVED |
| N≥fixed N_min | N_min/n→0 | returns to boundary | not established | N_min | NOT CURRENTLY SUPPORTED |
| N_min(n)→∞ with N_min/n→0 | weighted/boundary theory needed | unresolved | unresolved | growth rule | RESEARCH ALTERNATIVE |
| Weighted boundary process | possible alternative | nonlinear transfer unproved | unresolved | weights | NOT RESOLVED |

---

## 25. Automatic Tuning Matrix

| Rule | Role | Data-adaptive | Open choices | Whole-family status | Verdict |
| --- | --- | ---: | --- | --- | --- |
| theorem-admissible deterministic ℓ_n | multiplier CLT | NO | exponent/constant | base process | ADMISSIBLE BUT NOT GOVERNED |
| B&K data-adaptive IMSE bandwidth | covariance approximation | YES | lag cutoff/grid/kernel/construction | not uniquely optimal for full nonlinear family | CONDITIONALLY JUSTIFIED |
| Politis–White direct | dependent-bootstrap tuning | YES | algorithm profile | not direct multiplier full family | NOT SELECTED |
| outcome-driven search | favorable result | YES | observed outcomes | invalid | FORBIDDEN |

---

## 26. Primary Evidence Matrix

| Claim | Primary source | Exact support | StockScope mapping | Missing step | Verdict |
| --- | --- | --- | --- | --- | --- |
| Sequential empirical-process weak convergence | Bücher (2014), Theorem 1 | stationary strong-mixing multivariate sequence | joint feature vector | actual assumption acceptance | SUPPORTED |
| Dependent multiplier CLT | Bücher & Kojadinovic (2016), Theorem 2.1 / Cor. 2.2 | empirical process plus multiplier copies | d=3 joint horizon vector | exact executable bandwidth profile | SUPPORTED CONDITIONALLY |
| Data-adaptive bandwidth | Bücher & Kojadinovic (2016), Section 5.1 | IMSE bandwidth, n^(1/5) rate | non-arbitrary tuning basis | practical profile / full-functional optimality | PARTIAL |
| Dependent quantile linearization | Sen (1972); Yoshihara (1995); Wang-Hu-Yang (2011) | dependent quantile Bahadur results | median | common exact assumptions | SUPPORTING |
| MAD linearization | Mazumder & Serfling (2009) | MAD Bahadur / median-MAD structure | MAD derivative | not itself dependent sequential multiplier theorem | SUPPORTING + DERIVED TRANSFER |
| Mixing empirical/quantile process | Babu & Singh (1978) | empirical-quantile approximation | quantile-process support | not exact R1 theorem | SUPPORTING |

---

## 27. Open Track-A Gaps

### Gap A — κ

The current normalized-prefix mapping requires a positive interior lower bound.

No exact κ is justified.

### Gap B — exact multiplier/bandwidth profile

The route has theorem-admissible bandwidth conditions and a data-adaptive research proposal, but the exact reproducible StockScope profile remains unfrozen.

### Gap C — actual-process acceptance

Stationarity, strong-mixing rate, continuity, median density and MAD regularity are assumptions, not facts established here.

### Fail-closed branch — atoms / quantization

If the scoped law has relevant atoms at median/MAD defining points, the regular functional derivative route can fail. No jittering is permitted. A nonregular route would require separate theory.

### Scope limitation

The result is asymptotic and conditional on stationarity. It does not certify future structural stability.

---

## 28. G-A Gate Assessment

| Requirement | R1 state |
| --- | --- |
| Revised target | CONDITIONALLY ACCEPTED |
| Exact process class | DEFINED |
| Joint representation | CONDITIONALLY ACCEPTED |
| Sequential empirical-process theorem | SUPPORTED |
| Dependent multiplier theorem | SUPPORTED CONDITIONALLY |
| Automatic tuning | NOT FROZEN |
| ECDF transfer | SUPPORTED CONDITIONALLY |
| Median transfer | SUPPORTED CONDITIONALLY |
| MAD transfer | SUPPORTED CONDITIONALLY |
| Ratio mapping | SUPPORTED CONDITIONALLY |
| Zero-scale rule | DEFINED |
| Multi-horizon mapping | SUPPORTED CONDITIONALLY |
| Candidate domain | INTERIOR REQUIRED / κ UNRESOLVED |
| Nested envelope | SUPPORTED ON INTERIOR DOMAIN |
| Simultaneous all-N | SUPPORTED ON INTERIOR DOMAIN |
| Common-N post-selection | SUPPORTED CONDITIONALLY |
| Suffix rule | NOT EXECUTABLE |
| Actual process accepted | NO |
| Method approval | NO |

Therefore:

```text
G-A = BLOCKED
```

The important change from S6A is that this route is no longer broadly unresolved. The blockers are concentrated in domain governance, exact multiplier-profile freeze, and later assumption acceptance.

---

## 29. Method State

```text
METHOD_DESIGNED
```

Not METHOD_APPROVED and not METHOD_ROUTE_REJECTED.

The sequential dependent multiplier route remains the preferred Track-A architecture.

---

## 30. Next Track-A Resolution

The next Track-A task should not repeat median/MAD theorem research.

Preferred next task:

```text
NEXT-6E-S6A-R2
Candidate-Domain & Multiplier-Profile Resolution
```

It should resolve two prospective design-governance issues without Development outcomes:

### R2-A Candidate Domain Governance

Resolve whether κ can be justified from:
- theorem validity;
- independent minimum-information requirement;
- prospective method-design principle.

If no defensible κ exists, isolate a weighted/boundary-process route as a separate theorem task.

### R2-B Exact Multiplier Profile

Freeze or reject:
- multiplier construction;
- covariance kernel;
- bandwidth estimator;
- lag-cutoff algorithm;
- numerical grid/integration definition;
- deterministic tie/rounding rules;
- failure conditions.

Actual-process diagnostics remain a later prerequisite and are not authorized by R1.

---

## 31. S6B Handoff

Track B should treat:

```text
γ_repeat
=
REMOVE_FROM_METHOD_CONTRACT
REDEFINE_AS_SEPARATE_POLICY_CONCEPT IF STILL WANTED

α_stat
=
risk appetite associated with
the final simultaneous joint-functional support event

τ_T / τ_L / τ_S
=
still separate operational thresholds
```

No numeric policy value is authorized.

S6B remains:

```text
POLICY_DESIGNED
G-B = BLOCKED
```

---

## 32. Frozen Downstream State

```text
Reference Adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED

V3 changed = NO
V4 created = NO
Evaluator implemented = NO
Development evaluation = NO

Holdout = LOCKED / NOT ACCESSED
Production impact = NONE
```

---

## 33. Source Register

### Project sources

- `docs/StockScope_NEXT6E_S6A_METHOD_CONTRACT_RESOLUTION_2026-10-02.md`
- `docs/StockScope_NEXT6E_S6B_RISK_BUDGET_GOVERNANCE_RESOLUTION_2026-10-02.md`
- `docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md`
- `docs/StockScope_NEXT6B_S4_2B16_R24_METHOD_RISK_GOVERNANCE_2026-10-02.md`
- `docs/StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md`
- `backend/app/macro/reference_adequacy_protocol.py`
- `backend/app/macro/features.py`
- `backend/app/macro/distribution.py`
- `backend/app/macro/reference_stability.py`
- `backend/app/macro/identity.py`

### Primary literature

1. Bücher, A. (2014), "A note on weak convergence of the sequential multivariate empirical process under strong mixing." Journal of Theoretical Probability 28, 1028–1037. Preprint: https://arxiv.org/abs/1304.5113

2. Bücher, A. & Kojadinovic, I. (2016), "A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing." Bernoulli 22(2), 927–968. DOI: https://doi.org/10.3150/14-BEJ682. Preprint: https://arxiv.org/abs/1306.3930

3. Mazumder, S. & Serfling, R. (2009), "Bahadur representations for the median absolute deviation and its modifications." Statistics & Probability Letters 79(16), 1774–1783. DOI: https://doi.org/10.1016/j.spl.2009.05.006

4. Sen, P. K. (1972), "On the Bahadur representation of sample quantiles for sequences of φ-mixing random variables." Journal of Multivariate Analysis 2(1), 77–95. DOI: https://doi.org/10.1016/0047-259X(72)90011-5

5. Yoshihara, K. (1995), "The Bahadur representation of sample quantiles for sequences of strongly mixing random variables." Statistics & Probability Letters 24(4), 299–304. DOI: https://doi.org/10.1016/0167-7152(94)00187-D

6. Wang, X., Hu, S. & Yang, W. (2011), "The Bahadur representation for sample quantiles under strongly mixing sequence." Journal of Statistical Planning and Inference 141(2), 655–662. DOI: https://doi.org/10.1016/j.jspi.2010.07.008

7. Babu, G. J. & Singh, K. (1978), "On deviations between empirical and quantile processes for mixing random variables." Journal of Multivariate Analysis 8(4), 532–549. DOI: https://doi.org/10.1016/0047-259X(78)90031-3

8. van der Vaart, A. W. & Wellner, J. A. (1996), "Weak Convergence and Empirical Processes." Springer Series in Statistics.

### Evidence boundary

No single paper is represented as proving the complete StockScope composite. The chain is:

```text
base process theorem
+
functional regularity
+
continuous / functional-delta mapping
+
interior-domain normalization
+
simultaneous sup mapping
```

and remains conditional wherever source assumptions are not accepted.

---

## 34. Self-Check

```text
Development result inspected = NO
Development envelope inspected = NO
Passing N inspected = NO
Production outcome used = NO

Bootstrap executed = NO
Multiplier bootstrap executed = NO
Simulation executed = NO
Diagnostics executed = NO

Holdout read = NO
Holdout existence probe = NO
Holdout search = NO
Holdout metadata/hash/count/date inspection = NO

Manual bandwidth selected = NO
Outcome-driven selector chosen = NO
Conventional alpha chosen = NO
κ numeric value selected = NO

Operational tolerance selected = NO
Risk-budget value selected = NO

V3 changed = NO
V4 created = NO
Evaluator implemented = NO

Backend changes = NONE
Frontend changes = NONE
DB schema changes = NONE
Migration = NONE
Runtime DB access = NONE
Runtime writes = 0

Production impact = NONE
```

---

## 35. Completion / Handoff

```text
NEXT-6E-S6A-R1 COMPLETE

Statistical target
JOINT_SEQUENTIAL_FUNCTIONAL_SAMPLING_FLUCTUATION
TARGET_CONDITIONALLY_ACCEPTED

Process class
STRICTLY_STATIONARY_STRONG_MIXING
3D JOINT HORIZON FEATURE PROCESS
α(r)=O(r^-a), a>15/2

Representation
CONDITIONALLY_ACCEPTED
JOINT NATIVE COMPLETENESS REQUIRED

Sequential empirical process
SUPPORTED

Dependent multiplier
SUPPORTED CONDITIONALLY

Automatic bandwidth
SELECTOR_CONDITIONALLY_JUSTIFIED
EXECUTABLE PROFILE NOT FROZEN

ECDF transfer
SUPPORTED CONDITIONALLY

Median transfer
SUPPORTED CONDITIONALLY

MAD transfer
SUPPORTED CONDITIONALLY

Zero-scale
OUTSIDE REGULAR DOMAIN
FINITE NON_COMPUTABLE STATE PRESERVED

Candidate-N domain
INTERIOR_DOMAIN_REQUIRED
κ UNRESOLVED

Nested envelope
SUPPORTED ON INTERIOR DOMAIN

All-N simultaneous inference
SUPPORTED ON INTERIOR DOMAIN

Common-N post-selection
SUPPORTED CONDITIONALLY

Suffix sufficiency
PROCEDURE_RELATIVE
NOT EXECUTABLE UNTIL κ/METHOD FREEZE

γ_repeat
REMOVE_FROM_METHOD_CONTRACT
REDEFINE AS SEPARATE POLICY CONCEPT IF REQUIRED

Method state
METHOD_DESIGNED

G-A
BLOCKED

Remaining Track-A blockers
1. κ / candidate-domain governance
2. exact automatic multiplier/bandwidth profile
3. actual-process assumption acceptance at a later authorized evidence gate

Development result inspected
NO

Bootstrap executed
NO

Diagnostics executed
NO

Holdout accessed
NO

Runtime writes
0

V3 changed
NO

V4 created
NO

Production impact
NONE
```

### Next permitted work

```text
NEXT-6E-S6A-R2
Candidate-Domain & Multiplier-Profile Resolution
```

must resolve κ/domain governance and the exact reproducible dependent-multiplier profile without Development outcomes.

Track-B independent analytical/synthetic policy-evidence work may proceed separately.

S6C remains blocked while:

```text
G-A = BLOCKED
or
G-B = BLOCKED
```

No V4, evaluator, Development evaluation, Holdout, or Production task is authorized.
