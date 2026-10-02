# StockScope NEXT-6E-S6A-R2 — Candidate-Domain & Multiplier-Profile Resolution

## 1. Status / Research Baseline

- Date: 2026-10-02, Asia/Seoul.
- Stage: **NEXT-6E-S6A-R2 Candidate-Domain & Multiplier-Profile Resolution**.
- Artifact: source-only statistical-method design resolution.
- Research base: `05219786e72d2d56aafb8a6c33e1048a16674cca`.
- Relevant method baseline: `20a8d53a06d3089073333769dd5b1064731c5876`.
- The two later main commits only add unrelated task-spec documents and do not alter NEXT-6E method contracts.
- Parent state: `METHOD_DESIGNED / G-A BLOCKED`.
- S6B state: `POLICY_DESIGNED / G-B BLOCKED`.
- Implementation / V4 / evaluator / Development evaluation: **NOT AUTHORIZED**.
- Holdout: **LOCKED / NOT ACCESSED**.
- Production impact: **NONE**.

Final R2 disposition:

```text
NEXT-6E-S6A-R2 = COMPLETE

Method state = METHOD_DESIGNED
G-A = BLOCKED

Candidate-domain form = FIXED_INTERIOR_FRACTION
Candidate-domain status = CONDITIONALLY_FROZEN
κ classification = METHOD_DESIGN_PARAMETER
κ numeric value = null / UNRESOLVED

Multiplier family = MOVING_AVERAGE_DEPENDENT_MULTIPLIER
Kernel = PARZEN
Bandwidth estimator = BK2016_SECTION_5_1_ADAPTIVE_IMSE
Lag-cutoff algorithm = POLITIS_WHITE_CORRECTED_AUTOMATIC
Multivariate aggregation = MEDIAN
Grid = 5 PER DIMENSION / 125 POINTS FOR d=3
Centering = FULL_SAMPLE_EMPIRICAL_CENTERING
Multiplier profile status = CONDITIONALLY_FROZEN

Actual-process assumptions = NOT ACCEPTED
Reference Adequacy = UNRESOLVED
```

R2 makes material progress but does not promote the method to `METHOD_APPROVED`. The exact lower-domain fraction κ has no theorem-derived or independently approved numeric value, and actual-process assumption acceptance remains a later evidence gate.

---

## 2. R1 Frozen State

R1 froze the following direction:

```text
Target
=
JOINT_SEQUENTIAL_FUNCTIONAL_SAMPLING_FLUCTUATION

Process
=
STRICTLY_STATIONARY_STRONG_MIXING
3D JOINT HORIZON FEATURE PROCESS

dimension
=
3

mixing requirement
=
α(r)=O(r^-a)
a>15/2

resampling family
=
SEQUENTIAL_DEPENDENT_MULTIPLIER
```

R1 already established conditional transfer for:

- ECDF sup;
- median;
- MAD;
- normalized median ratio;
- relative MAD ratio;
- nested forward envelope;
- simultaneous all-candidate inference on an interior domain;
- common-N post-selection under that simultaneous event.

R2 does not reopen those findings.

---

## 3. R2 Problem Definition

Two design blockers remained after R1:

```text
R2-A
exact candidate-domain governance

R2-B
exact reproducible dependent-multiplier profile
```

The required outcome is prospective and result-independent.

No Development envelope, passing N, Production outcome, Holdout, bootstrap run, simulation, diagnostic or runtime database is used.

---

# Part A — Candidate Domain

## 4. Why the Full Finite Domain Is Not Frozen

For prefix fraction:

```text
s = N/n
```

the prefix empirical distribution is obtained from the sequential partial-sum process through normalization proportional to:

```text
1/s
```

The standard sup-norm continuous-mapping argument used by R1 is therefore singular as s approaches zero.

The base sequential empirical-process theorem includes s=0 for the unnormalized partial-sum process. That does not imply uniform validity for the normalized prefix distribution over N=1,...,n-1.

No reviewed theorem closes:

```text
normalized prefix ECDF
+
median
+
MAD
+
random MAD denominator
+
nested later-prefix envelope
+
all candidate N approaching s=0
```

under the exact StockScope process.

Therefore:

```text
FULL_FINITE_DOMAIN
=
NOT_SUPPORTED_BY_CURRENT_ROUTE
```

---

## 5. Candidate-Domain Alternatives

| Candidate | Basis | Numeric design choice? | StockScope transfer | Verdict |
| --- | --- | ---: | --- | --- |
| Full N=1,...,n-1 | Structural project domain | NO | normalized boundary singularity unresolved | REJECT FOR CURRENT METHOD |
| Fixed interior κ≤N/n<1 | R1 continuous-mapping route | YES: κ | directly compatible once κ>0 fixed | PREFERRED FORM |
| Fixed integer N_min | Product-like threshold | YES | N_min/n→0; returns asymptotically to boundary | NOT SUPPORTED |
| N_min(n)→∞, N_min/n→0 | possible intermediate sequence | YES: growth law | needs boundary/weighted theorem | RESEARCH ALTERNATIVE |
| Weighted boundary process | weighted sequential-process literature | YES: weighting law | no complete median/MAD/ratio/all-N transfer found | NOT RESOLVED |

---

## 6. Weighted / Boundary Literature Review

Weighted sequential empirical-process results exist in specialized settings, including weighted norms and dependent processes.

Those results do not supply the complete StockScope chain:

```text
strong-mixing 3D feature process
→ normalized prefix distributions near s=0
→ median/MAD functional maps
→ random denominator ratios
→ nested envelope
→ all-N simultaneous selection
```

The located weighted-process literature therefore does not justify silently replacing R1's interior domain with a boundary-inclusive method.

Verdict:

```text
WEIGHTED_BOUNDARY_ROUTE
=
SEPARATE_THEOREM_RESEARCH_REQUIRED
```

not an R2 fallback.

---

## 7. κ Classification

The sequential theorem does not identify a unique κ.

It requires only a fixed positive lower fraction for the current direct continuous-mapping route.

Therefore:

```text
κ IS NOT
=
THEOREM-DERIVED_NUMERIC_CONSTANT

κ IS NOT
=
PRODUCT_RISK_TOLERANCE

κ IS NOT
=
MONTE_CARLO_NUMERICAL_PARAMETER
```

R2 classifies κ as:

```text
METHOD_DESIGN_PARAMETER
```

Its role is to define the claim domain over which uniform inference is asserted.

Choosing a smaller κ expands the inferential claim closer to the singular boundary.

Choosing a larger κ narrows the claim domain.

The theorem says neither that a particular value is optimal nor that one fixed value is universally preferable.

---

## 8. Why R2 Does Not Choose a Numeric κ

Forbidden justifications include:

```text
κ = 0.1 because it is common
κ = 0.2 because it looks conservative
N ≥ 30 because 30 is a familiar sample size
κ chosen to preserve a desired passing N
κ chosen from current Development envelope behavior
```

No primary source reviewed supplies an exact κ for this StockScope target.

No independent approved project requirement supplies one.

No result-independent product requirement supplies one.

Therefore:

```text
κ numeric value = null
```

This is a method-design blocker, not a missing Development statistic.

---

## 9. Candidate-Domain Structural Decision

R2 nevertheless freezes the **form** of the current method domain:

```text
C_n(κ)
=
{
  N:
  ceil(κ n) ≤ N ≤ n-1
}

κ fixed
0 < κ < 1
```

subject to exact horizon alignment, warmup, later-state availability and function computability.

This is not an executable domain until κ is versioned and prospectively approved.

Status:

```text
CANDIDATE_DOMAIN_FORM
=
FIXED_INTERIOR_FRACTION

CANDIDATE_DOMAIN_STATUS
=
CONDITIONALLY_FROZEN

κ
=
UNRESOLVED
```

---

## 10. Out-of-Domain Semantics

An N excluded by the approved method domain is not a statistical failure.

Required future state:

```text
OUTSIDE_APPROVED_METHOD_DOMAIN
```

It must not be represented as:

- unstable;
- policy fail;
- insufficient Development performance;
- zero support.

Common-N semantics become:

> smallest supported common N **within the approved method domain**.

The method must never describe that result as the minimum over all positive integers unless a separate theorem later establishes the full domain.

---

## 11. Candidate Domain vs Product Support

The method-domain lower boundary is not:

```text
minimum_prior_observations
recommended_support
```

Those remain downstream results and currently remain null.

Even if a future κ is approved, the first method-eligible candidate can still fail adequacy.

---

# Part B — Exact Multiplier Profile

## 12. Primary Method Source

The primary practical source is:

Bücher, A. & Kojadinovic, I. (2016),  
"A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing," Bernoulli 22(2), 927–968.

Relevant sections include:

- Theorem 2.1;
- Corollary 2.2;
- Section 5.1, bandwidth estimation;
- Propositions 5.1–5.2;
- Section 5.2, generation of dependent multiplier sequences;
- Section 6, practical finite-sample comparisons.

The paper explicitly describes the procedure as data-adaptive, while also noting that simulation is used to suggest choices for additional practical parameters.

Therefore R2 separates:

```text
THEOREM_REQUIREMENT
from
LITERATURE-GUIDED_PRACTICAL_PROFILE
```

rather than calling every practical choice theorem-optimal.

---

## 13. Multiplier Generation Alternatives

The paper gives two main constructions.

### A. Moving-average approach

A finite weighted moving average of an initial i.i.d. standard-normal sequence produces dependent multipliers.

Advantages identified by the source:

- compatible with dependent-multiplier assumptions asymptotically;
- computationally cheaper;
- more numerically stable;
- avoids large covariance-matrix square roots.

### B. Covariance-matrix approach

Construct covariance matrix:

```text
Σ_n(i,j)
=
φ((i-j)/ℓ_n)
```

and generate correlated normal multipliers using a matrix square root.

The kernel must have a nonnegative Fourier transform so Σ_n is positive semidefinite.

Disadvantages:

- matrix square root;
- higher memory/compute;
- numerical stability burden.

The source explicitly suggests the moving-average approach because it is faster and more stable numerically.

R2 decision:

```text
MULTIPLIER_FAMILY
=
MOVING_AVERAGE_DEPENDENT_MULTIPLIER
```

---

## 14. Kernel Decision

The practical paper studies truncated, Bartlett, Parzen and flat-top-related constructions in the moving-average formulation.

For covariance-matrix generation it notes that truncated and flat-top kernels cannot be used when they fail the positive-definiteness condition required for Σ_n.

In finite-sample comparisons reported in the primary paper, the Parzen-related construction was among the best-performing tested choices for dependent settings, and later applications by the authors use the moving-average approach with Parzen-type weighting.

R2 does not interpret this as a universal theorem of optimality.

It is an independent published practical recommendation made without StockScope outcomes.

R2 decision:

```text
MOVING_AVERAGE_WEIGHT_KERNEL
=
PARZEN

status
=
LITERATURE_GUIDED_PRACTICAL_CHOICE
```

The exact Parzen formula must be versioned, not delegated to a library name.

---

## 15. Bandwidth Estimator

Section 5.1 derives an integrated mean squared error structure:

```text
IMSE
≈
Γ_bar^2 / ℓ_n^4
+
Δ_bar ℓ_n / n
```

whose asymptotic minimizer has the form:

```text
ℓ_opt
=
(4 Γ_bar^2 / Δ_bar)^(1/5)
n^(1/5)
```

The n^(1/5) term is an asymptotic rate.

It is not a complete finite-sample bandwidth by itself.

The adaptive procedure estimates Γ_bar and Δ_bar from data and then plugs them into the formula.

R2 decision:

```text
BANDWIDTH_METHOD
=
BK2016_SECTION_5_1_ADAPTIVE_IMSE
```

not:

```text
ℓ_n = n^(1/5)
```

with an omitted constant.

---

## 16. Lag Cutoff Algorithm

The practical estimator needs a lag cutoff L.

Bücher–Kojadinovic explicitly suggest adapting Politis–White Section 3.2.

The author-maintained/reference implementation in the `npcp` package makes this choice deterministic.

For a sample of length n:

```text
k_n
=
max(5, ceil(log n))

lag_max
=
ceil(sqrt n) + k_n

rho_crit
=
1.96 sqrt(log n / n)
```

for each coordinate.

The algorithm searches for the first run of k_n consecutive estimated autocorrelations below rho_crit in absolute value, with deterministic fallback rules matching the Politis–White procedure.

This exact algorithm is implementation-reference evidence, not a claim that every constant is theorem-optimal for StockScope.

R2 freezes it prospectively because it is:

- published/reference-implemented;
- automatic;
- result-independent with respect to adequacy outcomes;
- deterministic given the feature path;
- versionable.

Decision:

```text
LAG_CUTOFF_ALGORITHM
=
POLITIS_WHITE_CORRECTED_AUTOMATIC
WITH BK/NPCP DETERMINISTIC PROFILE
```

---

## 17. Multivariate Aggregation

Bücher–Kojadinovic describe:

```text
L
=
2 ψ(L_1,...,L_d)
```

and discuss median, mean, minimum and maximum aggregation.

The paper explicitly states that the multivariate extension is not unique, but reports the median as giving meaningful results in its Monte Carlo work.

R2 freezes:

```text
ψ
=
MEDIAN
```

as a **literature-guided practical choice**, not theorem necessity.

For d=3, the median is unambiguous and introduces no even-dimension averaging convention.

Decision:

```text
MULTIVARIATE_L_AGGREGATION
=
MEDIAN
```

---

## 18. Empirical-Process Grid

The bandwidth estimator approximates integrals over the d-dimensional probability cube with a uniform interior grid.

The author reference implementation `npcp::bOptEmpProc` uses:

```text
m = 5
```

grid positions per coordinate by default:

```text
j / (m+1)
j=1,...,m
```

For d=3:

```text
5^3
=
125
```

joint grid points.

R2 freezes this as an **implementation-reference grid**, not a theorem-derived optimum.

Decision:

```text
GRID_RULE
=
5 EQUALLY SPACED INTERIOR POINTS PER DIMENSION

d=3
→ 125 JOINT GRID POINTS
```

A future change requires a new multiplier-profile version.

---

## 19. Rank / Pseudo-Observation Rule for Bandwidth Estimation

The reference empirical-process estimator transforms each coordinate through ranks:

```text
U_ij
=
rank(X_ij) / (n+1)
```

before grid-indicator covariance calculations.

R2 freezes the transform as part of the bandwidth-estimation profile.

This rank transform is used for bandwidth estimation only.

It does not replace StockScope's underlying ECDF, median or MAD statistic definitions.

---

## 20. Flat-Top Lag Window for Γ / Δ Estimation

The adaptive bandwidth estimator uses a flat-top lag window for estimating the required covariance sums.

R2 freezes the reference trapezoidal flat-top estimator used by the Bücher–Kojadinovic / Politis–White procedure.

This is distinct from the Parzen kernel used to create the dependent multiplier sequence.

Required separation:

```text
flat-top lag window
=
bandwidth-estimator covariance-sum tool

Parzen weights
=
moving-average multiplier-generation kernel
```

They must not be collapsed into one "kernel" configuration field.

---

## 21. Bandwidth Integer Conversion

The moving-average implementation parameter b and effective dependence span ℓ are related by:

```text
ℓ = 2b - 1
```

The reference implementation estimates ℓ_opt and returns:

```text
b
=
round((ℓ_opt + 1)/2)
```

Future cross-language implementation must freeze the rounding convention rather than rely on platform defaults.

R2 requires:

```text
ROUNDING_MODE
=
ROUND_TO_NEAREST_TIES_TO_EVEN
```

to mirror the reference R implementation's numeric round semantics.

Then:

```text
effective_ell
=
2b - 1
```

must be recorded.

This is an implementation-identity field, not a hidden coercion.

---

## 22. Centering

R1 required theorem-consistent centering.

R2 freezes:

```text
CENTERING_RULE
=
FULL_SAMPLE_EMPIRICAL_CENTERING
```

for the sequential dependent-multiplier empirical process as specified by the selected theorem/corollary route.

No prefix-specific ad-hoc recentering is permitted.

A future implementation must reproduce the exact selected empirical-process formula rather than infer centering from a generic bootstrap API.

---

## 23. Shared Randomness Scope

One multiplier replicate is shared across:

```text
all 3 horizons
all 3 functional families
all eligible anchors
all later prefixes
```

No independent random stream per component.

R2 freezes the statistical randomness scope but not the numerical PRNG.

```text
STATISTICAL_RANDOMNESS_SCOPE
=
ONE_SHARED_MULTIPLIER_PATH_PER_REPLICATE
```

PRNG, seed derivation, substreams and bitwise reproducibility remain S6C responsibilities.

---

## 24. Replicate Count Boundary

R2 does not choose:

```text
B = 1000
B = 5000
...
```

The paper's simulation settings and package defaults are not converted into a StockScope numerical precision requirement.

Replicate count is governed by:

```text
δ_MC
Monte Carlo precision
S6C
```

---

## 25. Tie / Rounding Compatibility

The statistical theorem assumes a continuous joint law.

That is a model-law assumption.

It is not equivalent to requiring every computer-represented value to be unique.

R2 therefore freezes:

```text
NO_JITTER
```

and preserves project statistic semantics:

- deterministic sorting;
- existing even-sample median convention;
- existing right-continuous ECDF convention;
- raw MAD convention;
- explicit zero-scale non-computability.

Empirical ties are evidence relevant to later assumption acceptance, not something R2 removes numerically.

---

## 26. Failure Model

The future multiplier profile must fail closed on at least:

```text
BANDWIDTH_INPUT_NONFINITE
BANDWIDTH_ESTIMATOR_NONFINITE
BANDWIDTH_ESTIMATOR_NONPOSITIVE
LAG_SELECTOR_FAILURE
GRID_CONSTRUCTION_FAILURE
MULTIPLIER_PROFILE_MISMATCH
KERNEL_PROFILE_MISMATCH
CENTERING_PROFILE_MISMATCH
SOURCE_REGULARITY_UNRESOLVED
CANDIDATE_DOMAIN_UNRESOLVED
CANDIDATE_OUTSIDE_DOMAIN
NATIVE_POSITION_INCOMPLETE
NON_COMPUTABLE_ZERO_SCALE
```

No convenient fallback to a manually chosen bandwidth is authorized.

---

## 27. No Arbitrary Bandwidth Fallback

Forbidden:

```text
adaptive estimator fails
→ use sqrt(n)

adaptive estimator fails
→ use n^(1/5) with constant 1

estimated bandwidth < 1
→ silently clamp to 1

estimated bandwidth too large
→ silently clamp to n/2
```

unless a future exact contract independently justifies the transformation.

Current R2 rule:

```text
PROFILE FAILURE
→ NON_COMPUTABLE_METHOD_PROFILE
```

---

## 28. Multiplier Profile Decision Matrix

| Component | R2 decision | Basis | Status |
| --- | --- | --- | --- |
| Family | Moving-average dependent multiplier | primary paper recommends faster/more stable approach | FROZEN |
| Initial innovations | i.i.d. standard normal | primary construction | FROZEN |
| Weight kernel | Parzen | primary practical comparison / later author usage | CONDITIONALLY FROZEN |
| Bandwidth | B&K 2016 Section 5.1 adaptive IMSE | primary derivation | FROZEN METHOD |
| Rate | n^(1/5) inside adaptive formula | primary IMSE result | FROZEN |
| Lag cutoff | corrected Politis–White automatic profile | primary method + author reference implementation | FROZEN |
| Multivariate aggregation | median | primary paper practical recommendation | CONDITIONALLY FROZEN |
| Grid | 5 interior points per dimension | author reference implementation | CONDITIONALLY FROZEN |
| Rank transform | rank/(n+1) for bandwidth estimator | author implementation | FROZEN |
| Centering | full-sample empirical centering | theorem/corollary route | FROZEN |
| RNG | not selected | S6C | OUT OF SCOPE |
| Replicate count | not selected | S6C | OUT OF SCOPE |

Overall:

```text
MULTIPLIER_PROFILE
=
CONDITIONALLY_FROZEN
```

"Conditionally" means practical parameters are literature/reference-implementation choices rather than uniquely theorem-optimal constants, and the entire profile still depends on later assumption acceptance.

---

## 29. CandidateDomainContract / R2

```text
contract_version
=
NEXT6E_S6A_R2_CANDIDATE_DOMAIN_V1

domain_type
=
FIXED_INTERIOR_FRACTION

sample_size
=
joint aligned 3D feature-process length n

eligible
=
ceil(κ n) ≤ N ≤ n-1
plus structural later-state and computability rules

κ_classification
=
METHOD_DESIGN_PARAMETER

κ_value
=
null

out_of_domain_state
=
OUTSIDE_APPROVED_METHOD_DOMAIN

selection_scope
=
smallest supported common N
within approved method domain

full_positive_integer_minimum_claim
=
FORBIDDEN

theorem_basis
=
interior-domain continuous mapping

status
=
CONDITIONALLY_FROZEN / NON_EXECUTABLE
```

---

## 30. MultiplierProfileContract / R2

```text
contract_version
=
NEXT6E_S6A_R2_MULTIPLIER_PROFILE_V1

family
=
MOVING_AVERAGE_DEPENDENT_MULTIPLIER

initial_innovations
=
IID_STANDARD_NORMAL

weight_kernel
=
PARZEN_EXACT_FORMULA_VERSIONED

bandwidth_method
=
BK2016_SECTION_5_1_ADAPTIVE_IMSE

bandwidth_asymptotic_rate
=
n^(1/5) WITH ESTIMATED CONSTANT

lag_cutoff
=
POLITIS_WHITE_CORRECTED_AUTOMATIC
BK_NPCP_REFERENCE_PROFILE

lag_multivariate_aggregation
=
MEDIAN

bandwidth_grid
=
5 INTERIOR POINTS PER DIMENSION
125 JOINT POINTS FOR d=3

bandwidth_pseudo_observation
=
COORDINATE_RANK / (n+1)

covariance_sum_window
=
TRAPEZOIDAL_FLAT_TOP

centering
=
FULL_SAMPLE_EMPIRICAL_CENTERING

bandwidth_integer_conversion
=
b = ROUND_TIES_TO_EVEN((ell_hat+1)/2)
effective_ell = 2b-1

shared_multiplier_scope
=
ALL_HORIZONS_ALL_FUNCTIONS_ALL_CANDIDATES_ALL_LATER_PREFIXES

manual_fallback
=
FORBIDDEN

RNG
=
S6C

replicate_count
=
S6C

status
=
CONDITIONALLY_FROZEN
```

---

## 31. Domain–Bandwidth Coupling

R2 does not create an unsupported rule such as:

```text
N ≥ ell
N ≥ 2 ell
N ≥ 10 ell
```

The located theorem does not provide such a StockScope candidate-domain condition.

The bandwidth and candidate-domain contracts therefore remain conceptually distinct:

- bandwidth controls serial dependence of the multiplier approximation;
- κ controls how close normalized prefix inference approaches s=0.

A later proof may expose additional coupling. R2 does not invent one.

---

## 32. Decision Register

| Decision | Candidates | R2 choice | Basis | Remaining dependency |
| --- | --- | --- | --- | --- |
| Domain form | full / fixed interior / sequence / weighted | fixed interior | R1 theorem mapping | numeric κ |
| κ class | theorem / method / policy / numerical | method-design parameter | theorem only requires fixed positive fraction | approval/source for exact value |
| Multiplier family | moving average / covariance matrix | moving average | primary recommendation | assumptions |
| Kernel | Bartlett / Parzen / others | Parzen | primary practical evidence | not unique theorem optimum |
| Bandwidth | manual / deterministic rate / adaptive IMSE | adaptive IMSE | primary derivation | source regularity |
| Lag cutoff | manual / automatic | automatic PW-corrected | literature + author implementation | none at design level |
| Aggregation | max / median / mean / min | median | primary practical recommendation | not unique theorem optimum |
| Grid | unspecified / reference implementation | 5 per dimension | author implementation | profile versioning |
| Centering | ad hoc prefix / theorem route | full-sample empirical | corollary route | exact implementation later |
| Failure | manual fallback / fail closed | fail closed | project governance | none |

---

## 33. Open Register

```text
OPEN-1
Exact κ numeric value

OPEN-2
Actual-process assumption acceptance

OPEN-3
Whether empirical ties/atoms invalidate regular functional assumptions

OPEN-4
Whether later evidence reveals a required domain-bandwidth coupling

OPEN-5
S6C RNG / replicate-count / Monte Carlo precision profile
```

R2 does not treat these as defaults.

---

## 34. Actual-Process Acceptance Boundary

R2 does not execute:

- stationarity test;
- change-point test;
- autocorrelation diagnostic;
- mixing-rate estimate;
- density estimate;
- tie/atom frequency inspection;
- native-position completeness scan;
- MAD positivity study.

Those require a separate authorized evidence gate.

Important semantic distinction for that gate:

```text
ASSUMPTION_ACCEPTED_FOR_MODEL_USE
≠
MATHEMATICALLY_VERIFIED_TRUE
```

Finite observations cannot generally prove the infinite-process strong-mixing rate.

The future evidence gate must assess compatibility and failure evidence, document limitations, and remain fail closed.

---

## 35. G-A Gate Assessment After R2

| Requirement | R2 state |
| --- | --- |
| Statistical target | CONDITIONALLY ACCEPTED |
| Exact process class | DEFINED |
| Functional theorem chain | CONDITIONALLY SUPPORTED |
| Candidate-domain form | CONDITIONALLY FROZEN |
| Exact κ | UNRESOLVED |
| Multiplier family | FROZEN |
| Kernel/profile | CONDITIONALLY FROZEN |
| Adaptive bandwidth method | FROZEN |
| Lag cutoff | FROZEN |
| Aggregation | CONDITIONALLY FROZEN |
| Centering | FROZEN |
| Failure model | FROZEN |
| Actual process accepted | NO |
| Method executable | NO |
| Method approval | NO |

Therefore:

```text
G-A = BLOCKED
```

Residual blockers:

```text
1. κ numeric method-design decision
2. actual-process assumption acceptance
```

The multiplier-profile blocker from R1 is materially resolved.

---

## 36. Method State

R2 final method state:

```text
METHOD_DESIGNED
```

with:

```text
MULTIPLIER_PROFILE_CONDITIONALLY_FROZEN
CANDIDATE_DOMAIN_FORM_CONDITIONALLY_FROZEN
```

Not `METHOD_PROFILE_FROZEN` because κ remains null.

Not `METHOD_ROUTE_REQUIRES_REVISION` because the sequential multiplier route itself remains coherent.

---

## 37. S6B Interface

R2 does not change the policy thresholds:

```text
τ_T = null
τ_L = null
τ_S = null
α_stat = null
```

The statistical event identity remains:

```text
SIMULTANEOUS_JOINT_FUNCTIONAL_COVERAGE
OVER_APPROVED_INTERIOR_DOMAIN
```

γ_repeat remains:

```text
OUTSIDE METHOD CONTRACT
```

and may only return as a separately defined policy concept.

---

## 38. Next Track-A Work

Because κ is still unresolved, R2 does not authorize the assumption-evidence gate as the sole next step.

Two prospective paths remain:

### Path A — explicit method-domain governance

A separately authorized method-design decision appoints the responsible authority and chooses/version-controls a fixed κ without Development outcomes.

That task must explain the intended inferential scope; it cannot call the number theorem-optimal.

### Path B — boundary-theorem research

If the project refuses any prospective fixed κ, research a weighted/boundary sequential-functional theorem that can support κ_n→0 or a broader candidate domain.

That is a new theorem task and must re-establish median/MAD/ratio/nested/common-N transfer.

R3 assumption evidence should run only after the executable domain is frozen.

---

## 39. Frozen Downstream State

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
Runtime writes = 0
Production impact = NONE
```

---

## 40. Source Register

### Project sources

- `docs/StockScope_NEXT6E_S6A_R1_SEQUENTIAL_FUNCTIONAL_THEOREM_RESOLUTION_2026-10-02.md`
- `docs/StockScope_NEXT6E_S6A_METHOD_CONTRACT_RESOLUTION_2026-10-02.md`
- `docs/StockScope_NEXT6E_S6B_RISK_BUDGET_GOVERNANCE_RESOLUTION_2026-10-02.md`
- `docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md`

### Primary literature

1. Bücher, A. (2014), "A note on weak convergence of the sequential multivariate empirical process under strong mixing." Journal of Theoretical Probability 28, 1028–1037. https://arxiv.org/abs/1304.5113

2. Bücher, A. & Kojadinovic, I. (2016), "A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing." Bernoulli 22(2), 927–968. DOI: 10.3150/14-BEJ682. https://arxiv.org/abs/1306.3930

3. Politis, D. N. & White, H. (2004), "Automatic Block-Length Selection for the Dependent Bootstrap." Econometric Reviews 23(1), 53–70. DOI: 10.1081/ETC-120028836.

4. Patton, A., Politis, D. N. & White, H. (2009), correction to Automatic Block-Length Selection. Econometric Reviews 28(4), 372–375. DOI: 10.1080/07474930802459016.

### Reference implementation evidence

5. Kojadinovic, I., `npcp` R package, `bOptEmpProc` / `lnOpt.R`. Used only to freeze a transparent author-reference implementation profile for practical parameters. It is not treated as a theorem.

### Evidence boundary

- Primary theorem conditions define admissibility.
- Published simulations/recommendations support prospective practical choices but do not make them unique optima.
- Reference implementation defaults are implementation evidence, not statistical truth.
- No choice in this document uses StockScope adequacy outcomes.

---

## 41. Self-Check

```text
Development result inspected = NO
Development envelope inspected = NO
Passing N inspected = NO
Current adequacy distribution inspected = NO

Production outcome used = NO

Bootstrap executed = NO
Multiplier bootstrap executed = NO
Simulation executed = NO
Synthetic experiment executed = NO
Diagnostics executed = NO

Holdout read = NO
Holdout existence probe = NO
Holdout search = NO
Holdout metadata/hash/count/date inspection = NO

Outcome-driven κ selected = NO
κ numeric value selected = NO
Outcome-driven bandwidth selected = NO
Manual arbitrary bandwidth selected = NO

Operational tolerance selected = NO
Risk-budget numeric value selected = NO

Monte Carlo replicate count selected = NO
PRNG engine selected = NO

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

## 42. Completion / Handoff

```text
NEXT-6E-S6A-R2 COMPLETE

Research base
05219786e72d2d56aafb8a6c33e1048a16674cca

Candidate domain
FIXED_INTERIOR_FRACTION

κ
classification = METHOD_DESIGN_PARAMETER
value = null
status = UNRESOLVED

Out-of-domain semantics
OUTSIDE_APPROVED_METHOD_DOMAIN

Multiplier family
MOVING_AVERAGE_DEPENDENT_MULTIPLIER

Kernel
PARZEN
LITERATURE_GUIDED_PRACTICAL_CHOICE

Bandwidth method
BK2016_SECTION_5_1_ADAPTIVE_IMSE

Bandwidth rate
n^(1/5) WITH ESTIMATED CONSTANT

Lag cutoff
POLITIS_WHITE_CORRECTED_AUTOMATIC
BK_NPCP_REFERENCE_PROFILE

Multivariate aggregation
MEDIAN

Grid
5 PER DIMENSION
125 POINTS FOR d=3

Centering
FULL_SAMPLE_EMPIRICAL_CENTERING

Failure policy
FAIL_CLOSED
NO MANUAL BANDWIDTH FALLBACK

CandidateDomainContract
CONDITIONALLY_FROZEN / NON_EXECUTABLE

MultiplierProfileContract
CONDITIONALLY_FROZEN

Method state
METHOD_DESIGNED

G-A
BLOCKED

Remaining Track-A blockers
1. exact κ method-design decision
2. actual-process assumption acceptance after domain freeze

α_stat interface
UNCHANGED / SYMBOLIC POLICY INPUT

γ_repeat
OUTSIDE METHOD CONTRACT

Development result inspected
NO

Multiplier bootstrap executed
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

### Next

Preferred next decision depends on project policy:

```text
A.
NEXT-6E-S6A-R2A
Candidate-Domain Governance Decision
→ prospectively choose/version κ without Development outcomes

OR

B.
NEXT-6E-S6A-R2B
Boundary-Domain Theorem Research
→ avoid fixed κ by deriving a broader theorem route
```

R3 assumption-evidence work must not become the sole next step until the executable candidate domain is frozen.

No V4, evaluator, Development evaluation, Holdout, or Production task is authorized.
