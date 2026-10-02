# StockScope NEXT-6E-S6A — Method Contract Resolution

## 1. Status / Research Boundary

- Date: 2026-10-02, Asia/Seoul.
- Stage: **NEXT-6E-S6A Method Contract Resolution**.
- Artifact: source-only statistical-method research result.
- Research base: `a2057cb48dc11982ac6b1696e581aa52f135a940`.
- Architecture baseline: `StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md`.
- Current V3: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`.
- Executable implementation authorized: **NONE**.
- Development adequacy evaluation authorized: **NONE**.
- Holdout access: **NONE**.
- Production impact: **NONE**.

Final S6A task status:

```text
NEXT-6E-S6A = COMPLETE

Method state = METHOD_DESIGNED
G-A = BLOCKED

Target = TARGET_REQUIRES_REVISION
Representation = REPRESENTATION_CONDITIONALLY_ACCEPTED
Dependence contract = DESIGNED / ACTUAL-PROCESS ACCEPTANCE UNRESOLVED
Automatic selector = SELECTOR_UNRESOLVED
Joint resampling = DESIGNED AS RESEARCH INTERFACE
Joint inference = UNRESOLVED
All-N/common-N post-selection = UNRESOLVED
Suffix rule = PROCEDURE-RELATIVE / EXECUTABLE RULE UNRESOLVED
```

S6A completed the requested method research honestly. It did **not** find sufficient primary support to promote the complete StockScope method to `METHOD_APPROVED`.

No current Development evidence payload, envelope values, passing N, survival values, covered years, current adequacy distribution or per-horizon result was inspected. No bootstrap, diagnostic, simulation, DB access, runtime artifact generation, migration, application startup or evaluator was run.

Holdout remained locked and was not read, searched, enumerated, existence-probed, hashed, counted or inspected for dates/metadata.

---

## 2. Starting Architecture and Frozen Constraints

The accepted architecture document recommends, conditionally:

```text
Architecture C
Reference-Stability Confidence Region
+
Separate Operational Governance Gate

Candidate engine
single joint dependence-aware resampling engine

Organization
S6A Method Resolution
S6B Risk-Budget Resolution
S6C Convergence / Numerical Contract
```

The following constraints remain frozen:

```text
V3 remains immutable.

Required adequacy family:
3 × ECDF_SUP_DISTANCE
3 × NORMALIZED_MEDIAN_SHIFT
3 × RELATIVE_MAD_SHIFT

Selection:
COMMON_N_FIRST
ALL_FAMILIES_AND

Reference:
EXPANDING_STRICTLY_PRIOR
current observation excluded
BOUNDARY_ANCHORED_FORWARD_ENVELOPE

No:
manual block length
outcome-driven selector changes
method shopping
horizon removal
method-specific N
horizon-specific N
zero-MAD rescue
tolerance relaxation
```

The current state also remains:

```text
Reference Adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED
V4 = NOT CREATED
Evaluator = NOT IMPLEMENTED
Development evaluation = NOT AUTHORIZED
```

---

## 3. Exact Observed Functional

For a source level series Y_1,...,Y_R, define the h-observation feature:

```text
X_i^h = 100 × (Y_i - Y_{i-h}) bp
h ∈ {1,5,10}
```

For horizon h, let the chronological feature sequence be X_1^h,...,X_m^h.

For anchor N and later state t>N:

```text
T_h,N,t
=
sup_x | F_h,t(x) - F_h,N(x) |

L_h,N,t
=
| median_h,t - median_h,N |
/
| MAD_h,N |

S_h,N,t
=
| MAD_h,t - MAD_h,N |
/
| MAD_h,N |
```

and:

```text
E_h,q,N
=
max_{t>N} q_h,N,t

q ∈ {T,L,S}
```

TAIL uses the exact union of observed support values and right-continuous empirical CDF semantics already frozen by the project.

If the anchor MAD is zero:

```text
L_h,N,t = NON_COMPUTABLE_ZERO_SCALE
S_h,N,t = NON_COMPUTABLE_ZERO_SCALE
```

No epsilon denominator or stable/pass conversion is permitted.

The nine minimum required component coordinates are (h,q), h ∈ {1,5,10}, q ∈ {T,L,S}. The actual selection family is larger because N is selected after examining the required family.

---

## 4. Resolution D04 — Statistical Target / Estimand

### 4.1 Observed envelope is not the uncertainty target

The finite recorded-path quantity `E(D)` is deterministic once the record D is fixed. A confidence interval around the already-observed number itself does not create a meaningful unknown statistical parameter.

The statistical question must instead concern an unknown process law, population functional, or sampling distribution under a declared repeated-record experiment.

This part of the architecture is correct.

### 4.2 Review of the proposed law-level target

The architecture proposed:

```text
G_R(P)
=
joint law under process P
of the complete indexed envelope array
{E_h,q,N}
and non-computability indicators
for a fresh record of the declared finite construction.
```

It further proposed a confidence region `C_stat(D)` for that law itself, followed by a worst-case recurrence-risk projection.

That target is conceptually clean but is stronger than the primary bootstrap results identified in S5/S6A.

Politis–Romano establish the stationary bootstrap as a way to approximate sampling distributions / standard errors / confidence regions for parameters based on weakly dependent stationary observations. Block-bootstrap empirical-process results establish weak convergence of bootstrap empirical processes under explicit dependence conditions. Those results are not, by themselves, confidence-set constructions for an entire unknown finite-record law `G_R(P)`.

A bootstrap empirical distribution `G_hat*` is an estimator of a sampling law under a bootstrap approximation. It is **not automatically a confidence region for that law**.

No reviewed source supplies the exact additional layer needed to turn the StockScope whole-record bootstrap law into a valid confidence region for `G_R(P)`, uniformly over the complete selected-N family and its non-computability mass.

### 4.3 S6A target verdict

```text
D04
TARGET_REQUIRES_REVISION
```

The repeat-record interpretation remains a useful product/statistical question, but the architecture-level object `confidence region for G_R(P)` is not yet supported as the executable inferential target.

### 4.4 Preferred research replacement

The strongest directly supported research direction is an **asymptotic sequential functional-process target**, not a finite-record law-confidence-region target.

Conceptually:

```text
chronological dependent process
→ sequential empirical process
→ jointly derived quantile / MAD functionals
→ envelope/max functional over a preregistered interior index set
→ simultaneous asymptotic distribution / confidence bound
```

This aligns more closely with literature on empirical processes for stationary mixing sequences, block-bootstrap empirical-process weak convergence, sequential empirical processes, dependent multiplier bootstrap for sequential empirical processes, and quantile/MAD functional asymptotics.

However, this replacement creates an important limitation:

```text
full finite candidate domain including arbitrarily small N
is not automatically covered by interior asymptotic theory.
```

Therefore the target cannot be marked accepted until the candidate-domain/small-anchor issue is solved prospectively.

---

## 5. Evidence: Empirical and Sequential Empirical Processes

### 5.1 Block-bootstrap empirical process

Bühlmann (1995) proves a bootstrap central limit theorem for empirical processes of stationary beta-mixing variables indexed by suitable function classes, under moment/bracketing and exponential mixing-decay conditions.

Radulović (1996) proves weak convergence of the blockwise-bootstrap empirical process for stationary beta-mixing sequences indexed by VC-subgraph classes under explicit empirical-process conditions.

These results support:

```text
dependence-aware empirical-CDF functional inference
is theoretically possible under explicit dependence conditions.
```

They do not directly establish the StockScope all-prefix/all-N decision.

### 5.2 Sequential empirical-process direction

The StockScope statistic is intrinsically sequential:

```text
prefix N
versus
every later prefix t
```

A sequential empirical process is therefore more directly matched to the problem than a theorem for one fixed terminal empirical distribution.

Bücher and Kojadinovic's 2016 Bernoulli work develops a genuinely sequential dependent multiplier bootstrap under strong mixing. Its principal target is the sequential empirical copula process, but the paper also develops sequential empirical-process resampling machinery and proposes a data-adaptive bandwidth procedure.

This is important because it directly addresses two StockScope structural concerns:

```text
1. prefix/sequential dependence;
2. automatic dependence-bandwidth tuning.
```

It does **not** solve the complete StockScope target automatically because StockScope additionally requires ECDF-sup envelopes, median, MAD, random anchor-MAD denominators, zero-scale mass, candidate-N selection and common-N minimum selection.

### 5.3 Consequence

The Architecture A candidate family is broadened:

```text
A1 stationary block bootstrap
A2 moving/blockwise empirical-process bootstrap
A3 sequential dependent multiplier bootstrap
B  functional-specific procedures + proved joint coupling
```

No engine is execution-approved.

---

## 6. Resolution D05 — Dependence / Regularity Contract

### 6.1 Representation-level process

The most coherent proposed primitive remains:

```text
W_i = 100 × (Y_i - Y_{i-1})
```

because, when all native positions are present:

```text
X_i^h
=
sum of h consecutive W values
```

This creates one chronological primitive from which the 1/5/10-observation features can be rebuilt jointly.

### 6.2 Exact theorem class is required

The label `STATIONARY_WEAK_DEPENDENCE` is insufficient for execution.

A future method must name a concrete theorem class.

Candidate requirements include:

- strict stationarity of the declared primitive;
- exact alpha/strong-mixing, beta-mixing or another justified weak-dependence condition;
- coefficient decay/summability required by the selected theorem;
- theorem-specific moment assumptions;
- theorem-specific quantile and MAD regularity.

Association is a distinct class, not an automatic fallback for mixing.

### 6.3 Median regularity

Dependent quantile inference typically requires conditions such as uniqueness of the target quantile and local smoothness/positive density assumptions. Exact conditions must come from the selected theorem rather than be summarized loosely.

### 6.4 MAD regularity

MAD is the median of absolute deviations about an estimated median. Mazumder–Serfling's sample-MAD Bahadur work demonstrates that local regularity around the median and MAD points matters and that the joint median/MAD structure is nontrivial.

That work is useful for identifying the functional conditions. It is not a stationary dependent sequential-bootstrap theorem for the StockScope all-N ratio statistic.

### 6.5 Ties and rounded observations

Repeated/rounded observations cannot be jittered away.

If the selected theorem requires a continuous marginal or strictly positive local density, the project must either accept those assumptions for the exact scoped process with evidence or select another method.

### 6.6 Structural breaks / regimes

An unmodeled break is incompatible with a single stationary-process interpretation over the same scope.

Future diagnostics may have roles:

```text
INFORMATIONAL
ASSUMPTION_SUPPORTING
ASSUMPTION_REJECTING
```

but cannot establish mixing/stationarity as mathematical fact.

Post-outcome segmentation remains forbidden.

### 6.7 Proposed DependenceAssumptionContract

```text
contract_version
process_representation
stationarity_class
dependence_class
dependence_rate_requirements
moment_requirements
median_regularities
MAD_regularities
tie_atom_policy
zero_scale_policy
break_regime_incompatibility
diagnostic_protocol_id
diagnostic_roles
acceptance_scope
acceptance_evidence
rejection_evidence
unverifiable_limitations
review_status
approval_reference
```

### 6.8 D05 verdict

```text
Dependence contract = DESIGNED
Actual process acceptance = UNRESOLVED
Assumption verified = NO
```

---

## 7. Resolution D07 — Resampling Representation

| Representation | Cross-horizon coupling | Main problem | Verdict |
| --- | --- | --- | --- |
| Raw DGS10 levels | Can rebuild features jointly | Synthetic level jumps at seams; level stationarity not justified | NOT PREFERRED |
| Aligned 1/5/10 feature vector | Direct row coupling | Complete-case alignment changes support; cross-seam rolling identity not exact | RESEARCH ALTERNATIVE |
| Independent feature series | No | Destroys joint cross-horizon law | REJECT |
| One-observation increments | Strong; all horizons rebuilt from one primitive | Requires complete interior increments; stricter than current endpoint feature availability | CONDITIONALLY PREFERRED |

### 7.1 Why increments are preferred

A resampled increment path lets every horizon be rebuilt from the same synthetic sequence. It preserves the algebraic overlap among 1/5/10-observation deltas better than separately resampling already-derived feature series.

### 7.2 Missingness conflict

Current StockScope feature construction uses endpoint deltas. A longer-horizon endpoint delta can exist even if an interior level is absent.

The increment route requires every required consecutive increment.

S6A does not inspect current Development data to determine whether the condition holds.

Forbidden:

- timeline compression;
- silent row deletion;
- interpolation;
- calendar filling;
- synthetic imputation.

### 7.3 D07 verdict

```text
REPRESENTATION_CONDITIONALLY_ACCEPTED

preferred primitive
=
raw one-observation increments

required prerequisite
=
prospectively validated native-position completeness
for the declared source scope
```

---

## 8. Resolution D06 — Automatic Selector

### 8.1 Politis–White / corrected Patton–Politis–White

Politis–White propose automatic optimal-block estimators based on spectral/flat-top ideas. Patton–Politis–White (2009) correct the optimal block-size algorithms.

Therefore any future implementation must pin the corrected algorithm.

But:

```text
automatic block length
does not imply
automatic validity for an arbitrary statistic.
```

No reviewed result makes the corrected selector optimal for the combined StockScope ECDF-sup + median/MAD ratio + nested/all-N functional.

Verdict:

```text
PPW
=
AUTOMATIC CANDIDATE
FULL TRANSFER UNRESOLVED
```

### 8.2 Bühlmann–Künsch influence-function selector

Bühlmann–Künsch propose a fully data-driven block-length method based on the spectral density of the estimated influence-function process of the statistic.

This is highly relevant to regular scalar nonlinear statistics.

It does not automatically provide one optimal law for an indexed empirical-process supremum, random-MAD ratios, nested maxima and later common-N selection.

Verdict:

```text
INFLUENCE_SELECTOR
=
CONDITIONALLY SUPPORTED FOR REGULAR COMPONENTS
FULL FAMILY UNRESOLVED
```

### 8.3 Kuffner–Lee–Young quantile-specific selection

Kuffner, Lee and Young establish block-bootstrap distribution-estimation optimality for sample quantiles under mild strong-mixing conditions, using a hybrid bootstrap with jointly optimized block number and block length.

This is direct evidence that the median has statistic-specific tuning requirements.

It is not a theorem for MAD ratios, ECDF-sup envelopes or all-N selection.

Verdict:

```text
QUANTILE_SELECTOR
=
DIRECT MEDIAN RELEVANCE
NOT FULL-FAMILY
```

### 8.4 Sequential dependent multiplier bandwidth

Bücher–Kojadinovic provide a genuinely sequential dependent multiplier bootstrap under strong mixing and a data-adaptive bandwidth method.

This is more structurally aligned with prefix-indexed empirical-process inference than a fixed-terminal scalar block selector.

It still requires functional transfer to median/MAD, nonregular behavior and common-N selection.

Verdict:

```text
DEPENDENT_MULTIPLIER_BANDWIDTH
=
PREFERRED NEXT RESEARCH DIRECTION
FULL STOCKSCOPE TRANSFER UNRESOLVED
```

### 8.5 Custom joint selector

A custom selector requires a derived objective, loss, rate, internal tuning, candidate-domain relationship and failure rule. None currently exists.

Verdict:

```text
CUSTOM SELECTOR = NOT YET JUSTIFIED
```

### 8.6 Common versus component-specific selection

Rejected heuristic:

```text
fit one optimal length per component
→ take max/mean/median
→ declare joint validity
```

There is no identified theorem for that aggregation.

Separate unrelated resampling laws are also rejected for a joint cross-component claim unless an explicit coupling theorem is provided.

### 8.7 D06 final verdict

```text
SELECTOR_UNRESOLVED
```

No exact whole-family selector can be frozen into V4.

---

## 9. Joint Resampling Contract

The mechanical joint interface can still be specified.

### 9.1 Shared random object

One replicate defines one shared synthetic sequential object.

Every h, q, N and t is a deterministic view of that object.

Forbidden absent a separate proof:

```text
separate TAIL bootstrap
separate median bootstrap
separate MAD bootstrap
separate horizon bootstrap
separate N bootstrap
separate window bootstrap
```

### 9.2 Horizon rebuild

For the increment proposal:

```text
W* path
→ X*^(1)
→ X*^(5)
→ X*^(10)
```

using the exact approved native-position semantics.

### 9.3 Prefix recomputation

Within each replicate:

- recompute every empirical prefix CDF;
- recompute every prefix median;
- recompute every prefix MAD;
- recompute all anchor denominators;
- recompute every later-state comparison;
- recompute every envelope maximum.

Observed anchor MAD is never held fixed while resampling only the numerator.

### 9.4 Zero-scale

A replicate with zero anchor MAD is not deleted.

The statistical target must represent its non-computability mass or the chosen method must fail explicitly.

Conditioning on convenient valid replicates changes the target.

### 9.5 Proposed JointResamplingContract

```text
contract_version
source_representation_id
assumption_contract_id
selector_contract_id
resampling_engine
engine_parameters
shared_path_scope
horizon_rebuild_rule
candidate_domain
nested_state_rule
functional_rule_versions
zero_scale_rule
noncomputability_rule
randomness_profile_interface
joint_family_identity
limitations
status
```

Current:

```text
JOINT_RESAMPLING_INTERFACE_DESIGNED
EXECUTION_BLOCKED_BY_D04_D05_D06_D08
```

---

## 10. Median and MAD Transfer

### 10.1 Median

The median is a sample quantile. Under explicit local regularity and dependence assumptions, dependent quantile inference and block-bootstrap quantile distribution estimation are supported in the literature.

Thus:

```text
MEDIAN
=
THEORETICALLY PLAUSIBLE
UNDER EXACT REGULARITY
```

not approved by default.

### 10.2 MAD

MAD combines a location quantile and a quantile of absolute deviations about that estimated location.

Sample-MAD Bahadur theory supports the need for explicit joint median/MAD regularity. The located bootstrap-MAD literature does not supply the required stationary dependent sequential all-N theorem.

Thus:

```text
MAD
=
MARGINAL FUNCTIONAL THEORY EXISTS
DEPENDENT SEQUENTIAL JOINT TRANSFER UNRESOLVED
```

### 10.3 Ratios

For NORMALIZED_MEDIAN_SHIFT and RELATIVE_MAD_SHIFT, numerator and anchor MAD must have a joint asymptotic/resampling argument on a domain where the relevant population scale is nondegenerate.

Finite sample zero-scale remains a separate explicit failure.

---

## 11. Resolution D08 — Joint / Simultaneous Inference

### 11.1 Romano–Wolf boundary

Romano–Wolf support resampling-based joint dependence-aware FWER control at a chosen level for properly specified multiple-testing problems and advocate studentization where feasible.

That supports joint treatment rather than independent per-component alpha.

It does not define the StockScope adequacy claim.

In particular:

```text
failure to reject instability
!=
evidence of adequacy
```

### 11.2 Candidate constructions

#### Joint raw max

Requires a valid centered/scaled joint approximation to the entire indexed estimation error. No such StockScope root is approved.

#### Studentized max

Adds requirements for stable inferential scales, density/long-run variance estimation and nondegenerate studentizers. No default is justified.

#### Simultaneous confidence bands

This remains the preferred interface because a truly simultaneous event could protect later common-N selection.

The exact sequential nonlinear construction/proof is missing.

#### Law-level confidence region

The architecture-level `C_stat(D)` for a complete repeat-record law is not directly supported by reviewed primary theory.

Verdict:

```text
LAW_LEVEL_CONFIDENCE_REGION
=
NOT APPROVED AS CURRENT METHOD TARGET
```

#### Sequential dependent multiplier functional process

This is the preferred next route:

```text
sequential dependent empirical process
→ functional mapping
→ median/MAD joint process
→ envelope max
→ all-candidate simultaneous statement
```

Each arrow still requires exact proof.

### 11.3 Full finite-domain problem

The architecture proposed the structural domain:

```text
C_R
=
{1, ..., min_h(m_h - 1)}
```

The reviewed asymptotic literature does not justify uniform approximation down to arbitrarily small N.

This is a decisive blocker.

A future method might use an interior asymptotic domain such as N/R bounded away from zero, but S6A has no independent basis for choosing a numeric boundary and does not create one.

### 11.4 Post-selection common N

Conditional logic:

```text
valid simultaneous coverage over every eligible N
→ selecting the smallest passing common N is protected by that event
```

is reasonable.

But the required simultaneous coverage construction is missing.

### 11.5 D08 verdict

```text
Joint inference = UNRESOLVED
All-N uniform inference = UNRESOLVED
Common-N post-selection =
CONDITIONALLY LOGICAL / COVERAGE THEOREM MISSING
```

---

## 12. Suffix Sufficiency

No arbitrary standalone K is introduced.

Method-level meaning:

```text
SUFFICIENT
iff
the approved inference procedure is valid and computable
for the candidate/family
using genuinely later Development states
under frozen method and numerical contracts.
```

Candidate states should distinguish:

```text
SUFFICIENT
INSUFFICIENT_EVIDENCE
NON_COMPUTABLE
UNRESOLVED_METHOD
```

Because D06 and D08 are unresolved, an executable suffix rule is not available.

---

## 13. Candidate Method Architecture After S6A

### M1 — Stationary block bootstrap

```text
joint mechanics = plausible
automatic whole-family selector = unresolved
sequential/all-N theory = incomplete
median/MAD transfer = incomplete
status = CONDITIONAL RESEARCH CANDIDATE
```

### M2 — Blockwise empirical-process bootstrap

```text
ECDF empirical-process basis = stronger
sequential/all-N mapping = additional work
median/MAD functional mapping = additional work
status = CONDITIONAL RESEARCH CANDIDATE
```

### M3 — Sequential dependent multiplier bootstrap

```text
sequential empirical-process fit = strongest identified
automatic bandwidth = literature-supported within its target
median/MAD/envelope/all-N transfer = unresolved
status = PREFERRED NEXT RESEARCH DIRECTION
```

### M4 — Functional-specific procedures + joint coupling

```text
specialist component methods = possible
coherent joint law = not established
status = NOT READY
```

S6A does not mark M3 executable.

---

## 14. Selector Matrix

| Route | Objective | TAIL | Median | MAD | Joint | All-N / sequential | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PPW corrected | dependent-bootstrap block optimization for paper's target | Indirect | Indirect | Indirect | No direct theorem | No | UNRESOLVED TRANSFER |
| Influence-function selector | spectral selection on regular statistic influence process | Indexed transfer missing | Relevant | Derivation required | Missing | Missing | PARTIAL |
| Kuffner–Lee–Young | quantile distribution-estimation optimality | No | Direct | No direct ratio theorem | No | No | MEDIAN-SPECIFIC |
| Sequential dependent multiplier bandwidth | sequential dependent empirical-process resampling | Strongest relevance | Functional mapping needed | Functional/nonregular mapping needed | Shared primitive possible | Strong relevance | PREFERRED RESEARCH |
| Custom joint-functional selector | exact StockScope objective | Possible | Possible | Possible | Possible | Possible | NOT DERIVED |

No route is `SELECTOR_JUSTIFIED` for the full current contract.

---

## 15. Inference Matrix

| Construction | Statistical claim | Selection-safe now? | Nonregular support | Missing evidence | Verdict |
| --- | --- | ---: | ---: | --- | --- |
| Pointwise bootstrap CI per N | fixed-N uncertainty | NO | Weak | multiplicity/selection | REJECT AS FINAL |
| Joint raw max | max indexed estimation error | NO | Weak | root/scale/uniform theorem | RESEARCH ONLY |
| Studentized max | standardized simultaneous error | NO | Degeneracy risk | studentizers + process proof | RESEARCH ONLY |
| Romano–Wolf stepdown | FWER for specified hypotheses | Not for present adequacy claim | root-dependent | valid adequacy hypotheses/joint limit | NOT DEFAULT |
| Simultaneous functional band | all-index confidence event | Potentially | Must encode failures | exact sequential functional theorem | PREFERRED INTERFACE |
| Law-level `C_stat(D)` | confidence region for repeat-record law | NO | Conceptually possible | no identified construction | TARGET REVISION |
| Sequential dependent multiplier functional process | sequential-process approximation | Potentially | MAD mapping unresolved | functional mapping + domain + selection | PREFERRED RESEARCH |

---

## 16. Primary Evidence Matrix

| Claim | Primary source | Supported scope | StockScope mapping | Missing transfer | Verdict |
| --- | --- | --- | --- | --- | --- |
| Stationary bootstrap | Politis & Romano (1994), JASA 89, 1303–1313, DOI 10.1080/01621459.1994.10476870 | weakly dependent stationary-data bootstrap for sampling distributions / SE / confidence regions under stated conditions | dependence-aware candidate | no exact all-N nonlinear envelope theorem | CONDITIONAL |
| General empirical-process block bootstrap | Bühlmann (1995), SPA 58, 247–265, DOI 10.1016/0304-4149(95)00019-4 | empirical-process block-bootstrap CLT for stationary beta-mixing classes | ECDF functional basis | sequential selection + median/MAD | PARTIAL |
| Empirical-process bootstrap | Radulović (1996), SPA 65, 259–279, DOI 10.1016/S0304-4149(96)00102-0 | moving/block bootstrap weak convergence for VC-subgraph empirical processes under beta mixing | indicator/ECDF relevance | nonlinear all-N family | PARTIAL |
| Automatic block selection | Politis & White (2004), Econometric Reviews 23, 53–70, DOI 10.1081/ETC-120028836 | automatic block-size estimation for dependent bootstrap objectives | automaticity discipline | whole-family objective mismatch | UNRESOLVED |
| Corrected algorithm | Patton, Politis & White (2009), Econometric Reviews 28, 372–375, DOI 10.1080/07474930802459016 | correction to optimal block-size algorithms | exact version requirement | no expanded target validity | REQUIRED CORRECTION |
| Influence selector | Bühlmann & Künsch (1999), CSDA 31, 295–310, DOI 10.1016/S0167-9473(99)00014-6 | influence-process spectral approach for data-driven block length | regular nonlinear component candidate | ECDF index/MAD/max/all-N | PARTIAL |
| Quantile block selection | Kuffner, Lee & Young (2021), Biometrika 108, 675–692, DOI 10.1093/biomet/asaa075 | block-bootstrap optimality and empirical selection for sample quantiles under strong mixing | direct median relevance | MAD/ECDF/joint/all-N | PARTIAL |
| Sequential dependent multiplier | Bücher & Kojadinovic (2016), Bernoulli 22, 927–968, DOI 10.3150/14-BEJ682 | genuinely sequential dependent multiplier scheme under strong mixing with data-adaptive bandwidth; sequential empirical-process machinery | strongest prefix-indexed route | median/MAD/all-N functional transfer | PREFERRED RESEARCH |
| MAD Bahadur representation | Mazumder & Serfling (2009), SPL 79, 1774–1783, DOI 10.1016/j.spl.2009.05.006 | sample-MAD Bahadur representations / median-MAD asymptotic structure under local regularity | regularity and nonlinear structure | not dependent sequential bootstrap | PARTIAL |
| Joint multiple testing | Romano & Wolf (2005), Econometrica 73, 1237–1282, DOI 10.1111/j.1468-0262.2005.00615.x | resampling-based asymptotic FWER control at chosen level for specified family | joint-dependence philosophy | not stability certification or all-N target | FRAMEWORK ONLY |

---

## 17. Why METHOD_APPROVED Is Not Available

### A. Target mismatch

The law-confidence-region target lacks identified direct support. A sequential functional target is better supported but not yet frozen.

### B. Actual-process assumption acceptance

The theorem contract can be designed, but no actual-process acceptance exists. No diagnostics were run.

### C. Selector

No automatic selector is justified for the complete required functional.

### D. MAD transfer

MAD marginal theory exists; exact dependent sequential joint transfer remains unresolved.

### E. Full finite candidate domain

Uniform validity down to arbitrarily small N is unsupported.

### F. Simultaneous post-selection theorem

Common-N logic requires an all-N simultaneous event that has not been established.

### G. Suffix execution

Suffix sufficiency cannot be executable until the inference method is resolved.

Therefore:

```text
G-A = BLOCKED
```

---

## 18. Narrow Method Research Needed to Close G-A

Do not repeat a broad literature survey.

Preferred route:

```text
sequential dependent empirical-process /
dependent multiplier framework
```

Required closure work:

1. freeze one exact process/dependence class;
2. freeze a revised sequential functional target;
3. define a theorem-supported candidate index domain;
4. establish joint sequential empirical-process resampling for the declared class;
5. map median and MAD through exact functional/Bahadur conditions;
6. represent zero-scale/nonregular mass explicitly;
7. derive the nine-component envelope as a valid mapping;
8. freeze one automatic bandwidth/selector under the same theorem;
9. prove simultaneous validity over every eligible candidate N;
10. prove common-N minimum selection inherits that event;
11. define method-relative suffix sufficiency.

Alternative: derive a custom block-bootstrap theorem for the complete joint functional, with a substantially larger proof burden.

Forbidden:

```text
implement first
→ simulate on Development
→ choose the method that behaves best
→ approve retrospectively
```

---

## 19. Method Contract Draft

### 19.1 ReferenceAdequacyMethodContract / RESEARCH-DRAFT-S6A

```text
status
=
METHOD_DESIGNED / APPROVAL_BLOCKED

statistical_target
=
SEQUENTIAL_FUNCTIONAL_TARGET_TO_BE_FINALIZED

observed_functional
=
nine envelope components E_h,q,N

family
=
all required horizons/functionals
× all method-eligible candidate N

selection
=
smallest common N only after simultaneous valid classification

representation
=
one-observation increment path
CONDITIONALLY_ACCEPTED

assumption_contract
=
exact theorem-specific dependence/regularity contract required
actual-process acceptance unresolved

automatic_selector
=
UNRESOLVED

joint_resampling
=
one shared sequential random object
all horizons/components/N/t derived jointly

joint_inference
=
simultaneous sequential functional confidence construction
UNRESOLVED

suffix
=
procedure-relative
no arbitrary K

zero_scale
=
NON_COMPUTABLE_ZERO_SCALE

coverage_claim
=
NONE APPROVED
```

### 19.2 DependenceAssumptionContract / RESEARCH-DRAFT-S6A

```text
process
=
native one-observation increments, conditional proposal

required class
=
exact theorem-specific strict stationarity
+ explicit mixing/dependence conditions

quantile regularity
=
exact theorem conditions required

MAD regularity
=
median/MAD local regularity + positive population scale
+ finite zero-scale policy

diagnostics
=
INFORMATIONAL / ASSUMPTION_SUPPORTING / ASSUMPTION_REJECTING

acceptance status
=
UNRESOLVED
```

### 19.3 JointResamplingContract / RESEARCH-DRAFT-S6A

```text
shared random object = REQUIRED
separate component/horizon/N/window streams = FORBIDDEN absent proof
horizon reconstruction = from approved primitive
all prefix statistics recomputed = REQUIRED
anchor MAD recomputed per replicate = REQUIRED
invalid/zero-scale replicate deletion = FORBIDDEN
engine = UNRESOLVED
selector = UNRESOLVED
```

---

## 20. G-A Gate Result

| Requirement | State |
| --- | --- |
| Observed statistic exact | PASS |
| Unknown target | REVISION REQUIRED |
| Dependence contract structure | DESIGNED |
| Actual-process assumption accepted | NO |
| Representation | CONDITIONALLY ACCEPTED |
| Automatic selector | UNRESOLVED |
| Shared joint mechanics | DESIGNED |
| Median transfer | CONDITIONAL |
| MAD dependent sequential transfer | UNRESOLVED |
| TAIL empirical-process basis | CONDITIONALLY SUPPORTED |
| All-N uniform statement | UNRESOLVED |
| Common-N post-selection | CONDITIONALLY LOGICAL |
| Suffix executable rule | UNRESOLVED |
| Method approval | NO |

```text
G-A = BLOCKED
```

---

## 21. S6B / S6C Boundary

S6B may proceed independently on:

```text
product harm semantics
policy provenance
authority
operational movement budgets
statistical risk appetite
```

S6C must not pass until:

```text
G-A PASS
+
G-B PASS
+
numerical contract ready
```

S6A completion means the method gap is more precise, not closed.

---

## 22. V3 / V4 Boundary

V3 is unchanged.

V4 is not created.

The reserved future identifier:

```text
VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V4
```

remains unauthorized.

A future V4 task cannot choose a method from this document merely because it is listed. G-A must pass first.

---

## 23. Fail-Closed Rules Preserved

```text
assumption unresolved
→ no statistical execution

selector unresolved
→ no manual block override

joint inference unresolved
→ no marginal-CI fallback

small-N validity unresolved
→ no silent candidate deletion

zero anchor MAD
→ NON_COMPUTABLE_ZERO_SCALE

invalid resample
→ no favorable deletion

method research incomplete
→ Reference Adequacy remains UNRESOLVED
```

Baseline remains:

```text
reference_adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED
```

---

## 24. Source Register

### Project

- `docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md`
- `docs/StockScope_NEXT6E_POST_S5_DESIGN_DOCUMENT_TASK_SPEC_2026-10-02.md`
- `docs/StockScope_NEXT6B_S4_2B16_R24_METHOD_RISK_GOVERNANCE_2026-10-02.md`
- `docs/StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md`
- `backend/app/macro/reference_adequacy_protocol.py`
- `backend/app/macro/features.py`
- `backend/app/macro/distribution.py`
- `backend/app/macro/reference_stability.py`
- `backend/app/macro/identity.py`

### Primary / publisher sources

1. Politis, D. N. & Romano, J. P. (1994), "The Stationary Bootstrap", JASA 89(428), 1303–1313. DOI: https://doi.org/10.1080/01621459.1994.10476870
2. Bühlmann, P. (1995), "The blockwise bootstrap for general empirical processes of stationary sequences", SPA 58(2), 247–265. DOI: https://doi.org/10.1016/0304-4149(95)00019-4
3. Radulović, D. (1996), "The bootstrap for empirical processes based on stationary observations", SPA 65(2), 259–279. DOI: https://doi.org/10.1016/S0304-4149(96)00102-0
4. Politis, D. N. & White, H. (2004), "Automatic Block-Length Selection for the Dependent Bootstrap", Econometric Reviews 23(1), 53–70. DOI: https://doi.org/10.1081/ETC-120028836
5. Patton, A., Politis, D. N. & White, H. (2009), correction, Econometric Reviews 28(4), 372–375. DOI: https://doi.org/10.1080/07474930802459016
6. Bühlmann, P. & Künsch, H. R. (1999), "Block length selection in the bootstrap for time series", CSDA 31(3), 295–310. DOI: https://doi.org/10.1016/S0167-9473(99)00014-6
7. Kuffner, T. A., Lee, S. M. S. & Young, G. A. (2021), "Block bootstrap optimality and empirical block selection for sample quantiles with dependent data", Biometrika 108(3), 675–692. DOI: https://doi.org/10.1093/biomet/asaa075
8. Bücher, A. & Kojadinovic, I. (2016), "A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing", Bernoulli 22(2), 927–968. DOI: https://doi.org/10.3150/14-BEJ682
9. Mazumder, S. & Serfling, R. (2009), "Bahadur representations for the median absolute deviation and its modifications", Statistics & Probability Letters 79(16), 1774–1783. DOI: https://doi.org/10.1016/j.spl.2009.05.006
10. Romano, J. P. & Wolf, M. (2005), "Stepwise Multiple Testing as Formalized Data Snooping", Econometrica 73(4), 1237–1282. DOI: https://doi.org/10.1111/j.1468-0262.2005.00615.x

### Evidence-access limitation

Some final publisher texts are restricted. Abstract/metadata support is not promoted into exact theorem approval. Where exact StockScope transfer was not established, the corresponding contract remains unresolved.

---

## 25. Self-Check

```text
Development result inspected for tuning = NO
Development adequacy evaluator executed = NO

Bootstrap executed = NO
Diagnostics executed = NO
Simulation executed = NO

Holdout read = NO
Holdout existence probe = NO
Holdout search = NO
Holdout metadata/hash/count/date inspection = NO

Manual block length selected = NO
Outcome-driven method fallback = NO

Operational tolerance selected = NO
Risk-budget numeric value selected = NO
alpha_stat numeric value selected = NO
gamma_repeat numeric value selected = NO

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

## 26. Completion / Handoff

```text
NEXT-6E-S6A COMPLETE

Method state
METHOD_DESIGNED

G-A
BLOCKED

Target
TARGET_REQUIRES_REVISION

Representation
REPRESENTATION_CONDITIONALLY_ACCEPTED
(raw one-observation increments)

Dependence assumptions
CONTRACT DESIGNED
ACTUAL-PROCESS ACCEPTANCE UNRESOLVED

Automatic selector
SELECTOR_UNRESOLVED

Joint resampling
INTERFACE DESIGNED
EXECUTION BLOCKED

Joint inference
UNRESOLVED

All-N/common-N
POST-SELECTION LOGIC CONDITIONAL
UNIFORM COVERAGE THEOREM MISSING

Suffix rule
PROCEDURE-RELATIVE
EXECUTABLE SUFFICIENCY RULE UNRESOLVED

Preferred next method research
SEQUENTIAL DEPENDENT EMPIRICAL-PROCESS /
DEPENDENT MULTIPLIER ROUTE

Risk-budget values selected
NO

Reference Adequacy
UNRESOLVED

minimum_prior_observations
null

recommended_support
null

RATE_SPIKE
UNCALIBRATED

V4 allowed
NO

Evaluator implementation allowed
NO

Development evaluation allowed
NO

Holdout accessed
NO

Runtime writes
0

Production impact
NONE
```

### Permitted next work

The independently scoped:

```text
NEXT-6E-S6B
Risk-Budget Governance Resolution
```

may proceed.

For Track A, a narrower theorem-resolution task is still required before G-A can pass. It should focus on the sequential dependent empirical-process / multiplier route and the exact median/MAD/all-N functional transfer instead of another broad survey.

No implementation owner is permitted to fill unresolved method fields with conventional defaults.
