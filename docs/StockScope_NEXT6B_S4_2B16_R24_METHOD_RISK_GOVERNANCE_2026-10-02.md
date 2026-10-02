# NEXT-6B-S4.2-B.1.6-R2.4 — Statistic-Specific Dependence Method & Risk-Budget Governance Review

## 1. Status

Research stage: NEXT-6E-S5  
Research lineage: NEXT-6B-S4.2-B.1.6-R2.4  
Research base main SHA: `1088f0994c9712a7a9b64dd852d9ecb36d4447d8`  
Specified task base SHA: `1088f0994c9712a7a9b64dd852d9ecb36d4447d8`  
Base comparison: MATCH  
Reference Adequacy protocol preserved: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`  
Code changes: NONE  
Runtime artifact changes: NONE  
Runtime DB writes: 0  
Production impact: NONE

This review answers the two R2.4 questions before any new Development adequacy evaluation:

1. Can a statistic-specific automatic dependence-tuning rule be justified for the joint StockScope TAIL/MAD adequacy target without selecting a favorable rule from Development output?
2. Is there an independent project, domain, or formal statistical governance source for the required numeric family-wide error/risk budget and operational tolerances?

The answer is intentionally allowed to remain negative or unresolved. Removing a blocker is not a success criterion.

---

## 2. Access Boundary

### 2.1 Positive allowlist used for StockScope requirements

Only the following existing project definitions were used for requirement/governance review:

- `docs/StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md`
- `backend/app/macro/reference_adequacy_protocol.py`
- `docs/StockScope_MASTER_ARCHITECTURE_vNext.md`
- `docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md`
- `docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md`

The S4 readiness contract was used only as the immediate stage context. No Development adequacy evidence payload was opened for S5 tuning. No passing-N distribution, forward-envelope values, candidate survival, signal survival, episode survival, covered-year counts, or per-horizon adequacy results were used to choose a method or numeric parameter.

R2.3 contains historical frozen-lineage facts. This review does not use those numerical evidence values as tuning inputs and does not reproduce them as methodological evidence.

### 2.2 Protected data

Holdout was not accessed.

The review did not:

- search for Holdout artifacts,
- inspect Holdout paths,
- perform an existence check,
- inspect metadata,
- compute a hash,
- inspect row/sample counts,
- inspect date ranges.

---

## 3. Frozen R2.3 / V3 State

The following policy state remains unchanged:

```text
Primary method candidate = STATIONARY_BOOTSTRAP
Dependence assumption = STATIONARY_WEAK_DEPENDENCE
Assumption verified = NO
Automatic block selector = UNRESOLVED_STATISTIC_SPECIFIC_RULE
Manual block length = FORBIDDEN

Risk-budget source = NONE
Confidence/error budget = null
TAIL tolerance = null
MAD normalized median tolerance = null
MAD relative scale tolerance = null

Multiplicity scope = ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY
Standalone suffix K = ELIMINATED

Reference Adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED
```

V3 remains unchanged. R2.4 does not create V4 and does not run an evaluator.

---

## 4. Target Statistical Structure

The required adequacy family is not a sample-mean problem and not a single fixed statistic.

### TAIL

Three horizon components use:

```text
ECDF_SUP_DISTANCE
comparison = ANCHOR_N_TO_EVERY_LATER_REFERENCE_STATE
aggregation = MAX_OVER_VALIDATION_SUFFIX
```

### MAD location

Three horizon components use:

```text
NORMALIZED_MEDIAN_SHIFT
=
|median_t - median_N| / |MAD_N|
```

### MAD scale

Three horizon components use:

```text
RELATIVE_MAD_SHIFT
=
|MAD_t - MAD_N| / |MAD_N|
```

subject to the V3 zero-scale fail-closed rule.

The minimum joint family is therefore nine heterogeneous required components before additionally accounting for repeated candidate N, nested forward windows, common-N selection, and any resulting selection-induced simultaneous inference requirement.

A valid method must therefore address more than marginal bootstrap consistency for a fixed scalar estimator.

---

## 5. Primary Literature Reviewed

### 5.1 Politis & Romano — Stationary Bootstrap

Dimitris N. Politis and Joseph P. Romano,  
"The Stationary Bootstrap",  
Journal of the American Statistical Association 89(428), 1994, 1303-1313.  
DOI: https://doi.org/10.1080/01621459.1994.10476870

The paper introduces random-length block resampling whose conditional bootstrap series is stationary and develops consistency and weak-convergence properties for weakly dependent stationary observations.

**What it supports for StockScope**

- Block resampling is a defensible candidate class when stationarity and suitable weak-dependence conditions hold.
- A common resampled time-series path can preserve temporal dependence for recomputing multiple statistics jointly.

**What it does not establish for StockScope**

- It does not provide a parameter-free block length.
- It does not verify that the StockScope feature process satisfies its assumptions.
- It does not directly prove validity of the complete nested TAIL/median/MAD/common-N decision rule.
- It does not supply an operational reference-drift tolerance or family-wide error budget.

Verdict for role: **PRIMARY METHOD CANDIDATE SUPPORTED, EXECUTION NOT YET JUSTIFIED**.

---

### 5.2 Bühlmann — Blockwise Empirical Process

Peter Bühlmann,  
"Blockwise Bootstrapped Empirical Process for Stationary Sequences",  
The Annals of Statistics 22(2), 1994, 995-1012.  
DOI: https://doi.org/10.1214/aos/1176325508

This work establishes weak-convergence results for blockwise-bootstrapped empirical processes under explicit stationary/mixing and block-length conditions.

**StockScope connection**

This is direct support for the proposition that dependent empirical-distribution functionals can be handled through block bootstrap theory rather than pretending observations are iid.

However, it is not an automatic block-selection theorem for the StockScope TAIL statistic, and the bootstrap construction/conditions are not identical to a complete stationary-bootstrap policy for the current joint procedure.

Verdict: **EMPIRICAL-PROCESS COMPATIBILITY SUPPORT, NOT A COMPLETE S5 SELECTOR**.

---

### 5.3 Hwang — Stationary Bootstrap Empirical Process and Quantiles

Eunju Hwang,  
"Weak convergence for stationary bootstrap empirical processes of associated sequences",  
Journal of the Korean Mathematical Society 58(1), 2021, 237-264.  
DOI: https://doi.org/10.4134/JKMS.j200064

The paper gives weak-convergence results for stationary-bootstrap empirical processes for stationary associated random variables and discusses stationary-bootstrap quantiles.

**StockScope connection**

It strengthens the direct link from stationary bootstrap to empirical-distribution and quantile functionals.

**Limitation**

"Associated sequences" is a specific dependence class. S5 has not established that StockScope's chronological feature process belongs to that class. It therefore cannot be used to mark the project dependence assumption as verified.

Verdict: **DIRECT FUNCTIONAL SUPPORT UNDER A SPECIFIC UNVERIFIED DEPENDENCE CLASS**.

---

### 5.4 Dedecker & Merlevède — Dependent Empirical Distribution

Jérôme Dedecker and Florence Merlevède,  
"The empirical distribution function for dependent variables: asymptotic and nonasymptotic results in Lp",  
ESAIM: Probability and Statistics 11, 2007, 102-114.  
DOI: https://doi.org/10.1051/ps:2007009

The paper derives asymptotic and non-asymptotic results for empirical distribution functions for broad classes of dependent sequences.

**StockScope connection**

It supports the general legitimacy of dependence-aware empirical-distribution analysis.

**Limitation**

It does not provide the StockScope ECDF-sup operational tolerance, a stationary-bootstrap block selector, or a joint nested/common-N adequacy rule.

Verdict: **BACKGROUND EMPIRICAL-PROCESS SUPPORT ONLY**.

---

### 5.5 Politis & White plus Patton–Politis–White — Automatic Block Length

Dimitris N. Politis and Halbert White,  
"Automatic Block-Length Selection for the Dependent Bootstrap",  
Econometric Reviews 23(1), 2004, 53-70.  
DOI: https://doi.org/10.1081/ETC-120028836

Andrew Patton, Dimitris N. Politis and Halbert White,  
"Correction to 'Automatic Block-Length Selection for the Dependent Bootstrap'",  
Econometric Reviews 28(4), 2009, 372-375.  
DOI: https://doi.org/10.1080/07474930802459016

The 2004 method uses spectral estimation/flat-top lag windows to estimate optimal block size. The 2009 paper corrects the optimal-block-size algorithms after a correction to underlying theoretical results.

**StockScope connection**

This is evidence that automatic block selection can be defined without manually sweeping block lengths after seeing desired outcomes.

**Critical transfer limitation**

The published automatic selector does not by itself establish an optimal common selector for the exact StockScope family:

- ECDF-sup forward envelopes,
- normalized median-shift envelopes,
- relative MAD-shift envelopes,
- nested overlapping future windows,
- candidate common-N selection,
- joint simultaneous error control.

The correction also means that an implementation must use corrected formulas rather than treating the original 2004 algorithm as immutable.

Verdict for complete StockScope use: **UNRESOLVED**.

---

### 5.6 Bühlmann & Künsch — Statistic-Specific Influence-Function Selector

Peter Bühlmann and Hans R. Künsch,  
"Block length selection in the bootstrap for time series",  
Computational Statistics & Data Analysis 31(3), 1999, 295-310.  
DOI: https://doi.org/10.1016/S0167-9473(99)00014-6

This paper is particularly relevant because its data-driven block-length method works through the time series of an estimated influence function of the statistic. It explicitly treats nonlinear statistics and includes median examples.

The paper also states an important limitation: its main target is first-order accuracy for variance/standard-error estimation, and different higher-order/studentized procedures can require a block length of a different order.

**StockScope consequence**

The influence-function route provides a plausible theoretical bridge for regular scalar location/scale estimators. It does not automatically solve:

- the max-over-forward-suffix TAIL statistic,
- the ratio structure involving anchor MAD,
- zero-MAD non-computability,
- a heterogeneous nine-component joint statistic,
- repeated candidate-N selection,
- the common-N first rule.

No direct theorem was identified in the reviewed sources showing that the same automatically selected block length is optimal for this whole joint functional.

Verdict: **PARTIAL STATISTIC-SPECIFIC SUPPORT; COMPLETE JOINT SELECTOR UNRESOLVED**.

---

### 5.7 Kuffner, Lee & Young — Quantile-Specific Block Selection

T. A. Kuffner, S. M. S. Lee and G. A. Young,  
"Block bootstrap optimality and empirical block selection for sample quantiles with dependent data",  
Biometrika 108(3), 2021, 675-692.  
DOI: https://doi.org/10.1093/biomet/asaa075

The paper develops block-bootstrap optimality and empirical block selection specifically for sample quantiles under strong-mixing conditions and shows that tuning depends on the quantile distribution-estimation problem.

**StockScope consequence**

This is positive support for dependence-aware median/quantile bootstrap inference, but it also demonstrates why a generic mean/variance-oriented block selector cannot be assumed automatically optimal for quantiles.

The paper studies its own hybrid block-bootstrap construction and quantile target. It does not directly justify the StockScope joint ECDF-sup/median/MAD/nested/common-N rule.

Verdict: **STATISTIC-SPECIFIC TUNING IS REAL; DIRECT TRANSFER TO FULL STOCKSCOPE FAMILY NOT ESTABLISHED**.

---

### 5.8 Romano & Wolf — Joint Multiplicity

Joseph P. Romano and Michael Wolf,  
"Stepwise Multiple Testing as Formalized Data Snooping",  
Econometrica 73(4), 2005, 1237-1282.  
DOI: https://doi.org/10.1111/j.1468-0262.2005.00615.x

The paper gives resampling-based stepwise procedures that asymptotically control familywise error and explicitly exploit the joint dependence structure of test statistics. It advocates studentization when feasible.

**StockScope connection**

The paper supports:

- treating required components jointly rather than with independent per-component alpha,
- preserving dependence in the resampling distribution,
- using studentization/normalization rather than a raw max across incomparable scales.

**Limitation**

The procedure controls FWER at a **desired level**. It does not select that level for StockScope. It also does not directly define the operational movement tolerances or prove that the current nested/common-N adequacy selection can be reduced to the paper's hypothesis-testing setup without an additional contract.

Verdict: **JOINT-ERROR-CONTROL FRAMEWORK SUPPORTED; STOCKSCOPE TRANSFER AND NUMERIC LEVEL UNRESOLVED**.

---

## 6. Evidence Matrix

| Claim / candidate | Primary source | Statistic-specific applicability | Joint / nested / common-N applicability | Finite-sample scope | Remaining gap | Verdict |
|---|---|---|---|---|---|---|
| Stationary bootstrap for weak dependence | Politis & Romano 1994 | Broad resampling framework | Can resample shared time path jointly | Primarily asymptotic consistency/weak convergence | Project assumption not verified; no exact joint adequacy theorem | CONDITIONALLY_SUPPORTED_CANDIDATE |
| Empirical-process block bootstrap | Bühlmann 1994 | Direct empirical-process relevance | Does not solve common-N selection | Asymptotic under explicit block/mixing conditions | Not an automatic selector for current statistic | PARTIAL_SUPPORT |
| Stationary-bootstrap empirical process/quantile | Hwang 2021 | Direct EDF/quantile relevance | No StockScope nested/common-N theorem | Weak convergence under associated sequences | Dependence class not verified | PARTIAL_SUPPORT |
| Automatic dependent-bootstrap block length | Politis & White 2004; correction 2009 | Practical automatic block size | Whole heterogeneous family not covered directly | Asymptotic/attainable-efficiency motivation | Statistic-specific transfer unresolved | UNRESOLVED |
| Influence-function block selector | Bühlmann & Künsch 1999 | Strong relevance to regular scalar statistics; median example | No proof for heterogeneous max/nested/common-N rule | First-order SE/variance focus | Joint functional and selection effect unresolved | CONDITIONALLY_SUPPORTED_PART |
| Quantile-specific block selection | Kuffner et al. 2021 | Direct median/quantile relevance | Different hybrid bootstrap target | Asymptotic theory plus simulations | Does not establish MAD/joint TAIL rule | PARTIAL_SUPPORT |
| Joint resampling multiplicity | Romano & Wolf 2005 | General multiple-statistic framework | Captures joint dependence; common-N mapping not established | Asymptotic FWER control | Desired alpha and operational tolerance not supplied | FRAMEWORK_SUPPORTED_POLICY_UNRESOLVED |
| Dependent EDF theory | Dedecker & Merlevède 2007 | EDF dependence support | Not an adequacy-selection procedure | Includes non-asymptotic Lp results under stated conditions | Not sup-tolerance/block-selector source | BACKGROUND_SUPPORT |

---

## 7. Statistic-by-Statistic Applicability

### 7.1 TAIL / ECDF_SUP_DISTANCE

There is credible literature support for bootstrapped empirical processes for stationary dependent sequences under explicit dependence and block conditions.

That does **not** by itself justify the complete StockScope statistic:

```text
max over every later reference state
after choosing an anchor N
then selecting a common N across all families
```

The nested windows share observations and the candidate N is itself part of the eventual policy decision. A theorem for a fixed empirical-process functional is not automatically a simultaneous theorem after this additional selection layer.

**TAIL method status:** theoretical bootstrap route plausible, exact execution rule unresolved.

### 7.2 NORMALIZED_MEDIAN_SHIFT

Dependent-quantile bootstrap theory exists and statistic-specific block-selection theory exists.

However StockScope normalizes the movement by the anchor MAD. The joint distribution of numerator and denominator must be respected. The method cannot separately bootstrap the median and then treat the observed anchor MAD as a risk-free constant if the eventual inferential target includes its sampling uncertainty.

**Median-shift status:** conditionally supportable as a component, joint normalized rule unresolved.

### 7.3 RELATIVE_MAD_SHIFT

MAD is a robust scale functional but has regularity requirements. The center estimate enters the absolute deviations; ties, density behavior near the median and median absolute deviation, and zero-scale behavior matter.

R2.4 did not identify a primary source that directly supplies an automatic stationary-bootstrap block-selection theorem for the exact relative-MAD forward-envelope statistic combined with the other eight required components.

The existing V3 rule for zero anchor MAD remains fail-closed.

**Relative-MAD status:** unresolved for automatic joint execution.

---

## 8. Dependence Assumption Review

Current assumption:

```text
STATIONARY_WEAK_DEPENDENCE
REQUIRED / NOT VERIFIED
```

The reviewed literature makes stationary/weak-dependence or more specific mixing/association assumptions central to the relevant bootstrap validity results.

R2.4 does not run diagnostics against Development observations and therefore does not verify those assumptions.

The correct state is:

```text
Dependence assumption = ASSUMPTION_UNRESOLVED
Assumption verified = NO
Assumption proven = NO
```

This is not the same as `ASSUMPTION_INCOMPATIBLE`. The literature is compatible with the modeling direction, but S5 does not have admissible evidence that the actual StockScope feature process satisfies all conditions required by the chosen theorem.

Future diagnostics may reject obvious incompatibility or provide supporting information, but they must not convert a single stationarity-test p-value into a project-level proof.

---

## 9. Automatic Block-Length Rule Verdict

### 9.1 Rules rejected

The following remain prohibited:

```text
manual fixed block length
sqrt(N) by convention
try multiple lengths and choose the favorable Development result
method fallback based on favorable output
```

### 9.2 Politis–White / corrected Politis–White

These algorithms are credible automatic selectors for the block-bootstrap problems they target, but direct whole-family transfer is not established.

Status:

```text
POLITIS_WHITE_TRANSFER = UNRESOLVED
```

### 9.3 Influence-function route

Bühlmann–Künsch provides a stronger statistic-specific route and explicitly includes median examples, but its main first-order variance/SE target is narrower than the StockScope nested joint policy.

Status:

```text
INFLUENCE_FUNCTION_SELECTOR = CONDITIONALLY_JUSTIFIED_FOR_REGULAR_COMPONENTS
FULL_STOCKSCOPE_SELECTOR = UNRESOLVED
```

### 9.4 Quantile-specific route

Kuffner–Lee–Young confirms that quantile block-bootstrap tuning deserves its own treatment. It does not provide a common selector for TAIL + normalized median + relative MAD.

Status:

```text
QUANTILE_SELECTOR_TRANSFER = CONDITIONALLY_JUSTIFIED_FOR_QUANTILE_PROBLEM
FULL_STOCKSCOPE_SELECTOR = UNRESOLVED
```

### 9.5 Overall automatic tuning state

Because the task requires one defensible joint procedure for all required components and the nested/common-N selection layer, partial component support cannot be promoted to a full approval.

```text
Automatic tuning rule = UNRESOLVED
```

---

## 10. Joint Multiplicity Review

The multiplicity scope remains:

```text
ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY
```

Romano–Wolf supports resampling-based joint dependence-aware familywise error control at a specified level and supports studentization where feasible.

For StockScope, a future V4 would still have to define before evaluation:

1. the exact joint resample identity shared by all horizons/components;
2. the normalization/studentization for heterogeneous TAIL and MAD statistics;
3. the statistic produced for each candidate N;
4. how nested future windows are represented in each resample;
5. whether candidate-N/common-N selection is inside the simultaneous statement;
6. the critical-value/stepdown or simultaneous-bound construction;
7. failure/non-computability handling;
8. the numeric family-wide error budget.

R2.4 therefore records:

```text
Joint multiplicity framework = CONCEPTUALLY_SUPPORTED
StockScope joint procedure = UNRESOLVED
Joint error budget = null
```

Independent per-component alpha remains forbidden.

---

## 11. Existing StockScope Requirement Review

The positive allowlist was reviewed for an independently approved numeric requirement that predates and is independent of the Development adequacy envelope.

No such applicable numeric requirement was identified for:

- TAIL acceptable probability movement,
- normalized median movement,
- relative MAD movement,
- family-wide confidence/error budget.

R2.3 itself explicitly records the absence of such a project requirement and freezes the risk-budget source hierarchy.

The Architecture, Roadmap, and Implementation Baseline contain general validation, reproducibility, activation, and fail-closed requirements but no independently approved numerical threshold in the units of the three Reference Adequacy statistics.

Therefore:

```text
EXISTING_PROJECT_REQUIREMENT = NONE
```

This statement is scoped to the approved project definitions in the S5 positive allowlist; it is not a claim about documents outside that approved research scope.

---

## 12. External Domain Requirement Review

Official model-risk and market-risk sources were reviewed for a directly transferable numeric stability requirement.

### 12.1 Federal Reserve model-risk guidance

The Federal Reserve's 2026 revised model-risk guidance emphasizes risk-based, model-specific validation, assumptions, limitations, monitoring, and meaningful performance deviations. It does not prescribe a universal numeric TAIL ECDF drift, normalized median shift, or relative MAD shift tolerance for a StockScope-like reference process.

Source:
- Federal Reserve, SR 26-2 / Revised Guidance on Model Risk Management, 2026.
- https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm
- https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm

### 12.2 Basel market-risk framework

Basel market-risk rules include model validation and regulatory backtesting requirements. Some rules use explicit confidence levels for specific regulatory risk measures such as VaR.

Those numbers have a different object and purpose:

```text
VaR regulatory coverage/backtesting
!=
acceptable change in an empirical DGS10 reference distribution
```

Using a regulatory VaR confidence level as StockScope's Reference Adequacy operational tolerance would be a category error.

Sources:
- Basel Framework, market-risk model validation.
- https://www.bis.org/baselframework/
- Basel MAR99 backtesting framework.

### 12.3 External-domain conclusion

No directly applicable official domain requirement was identified in the surveyed Federal Reserve/Basel scope that supplies the required numeric values in the units and purpose of the current StockScope statistics.

Therefore:

```text
EXTERNAL_DOMAIN_REQUIREMENT = NONE_IN_REVIEWED_SCOPE
```

This is a bounded research conclusion, not a proof that no standard anywhere could ever exist.

---

## 13. Formal Statistical Error-Control Review

Formal procedures can control statistical error **conditional on a chosen target level and assumptions**.

Romano–Wolf is a clear example: it provides asymptotic FWER control at a desired level and captures dependence among the statistics.

This does not answer either of the following policy questions:

```text
Why should StockScope choose that family-wide level?
How much reference movement is operationally acceptable?
```

Therefore a formal error-control framework can be part of the future uncertainty mechanism but does not independently produce the operational tolerance.

R2.4 preserves the R2.3 distinction:

```text
STATISTICAL_UNCERTAINTY
!=
OPERATIONAL_RISK_BUDGET
```

Current state:

```text
confidence_level = null
joint_error_budget = null
TAIL tolerance = null
normalized_median_shift_tolerance = null
relative_mad_shift_tolerance = null
```

---

## 14. Risk-Budget Source Decision

Applying the frozen hierarchy:

| Source | S5 result | Reason |
|---|---|---|
| EXISTING_PROJECT_REQUIREMENT | NONE | No independent numeric adequacy requirement in the positive allowlist |
| EXTERNAL_DOMAIN_REQUIREMENT | NONE_IN_REVIEWED_SCOPE | Official model/market-risk guidance does not provide directly transferable values for these statistics |
| FORMAL_STATISTICAL_ERROR_CONTROL | PROCEDURE_SUPPORT_ONLY | Can control error at a chosen level; does not choose the project risk budget or operational tolerance |
| NONE | ACTIVE | Numeric policy remains independently unjustified |

Therefore:

```text
risk_budget_source = NONE
risk_budget_value = null
numeric_policy_status = UNJUSTIFIED
```

---

## 15. Numerical Reproducibility Contract Review

A future approved stochastic evaluator should have deterministic logical identity independent of worker scheduling.

### 15.1 Structurally justifiable contract sketch

A future V4 may define seed material from already approved immutable identities:

```text
domain_separator
+ Development dataset identity
+ Reference Adequacy protocol identity
+ V4 preregistration contract version
+ joint family/statistic identity
```

The seed derivation must use canonical serialization, an explicitly versioned hash, and a defined integer mapping.

Joint components must not receive unrelated seeds that break shared resampling dependence. A family-level resample identity with deterministic substream derivation is preferable.

### 15.2 Still unresolved

R2.4 does not identify an independent basis for choosing:

- a specific PRNG implementation/version,
- a specific number of resamples,
- a Monte Carlo error allocation,
- a stopping tolerance,
- a maximum resample cap.

It would be inappropriate to insert `1000`, `10000`, `0.05`, or another conventional number solely because it is common practice.

State:

```text
deterministic seed architecture = STRUCTURALLY_SPECIFIABLE
exact PRNG contract = UNRESOLVED
resample_count = null
monte_carlo_stopping_rule = null
Monte Carlo error budget = null
```

No bootstrap was executed in S5.

---

## 16. Suffix Sufficiency

The R2.3 structural elimination of an arbitrary standalone suffix K is retained.

```text
suffix sufficient iff
the approved uncertainty procedure can produce the required joint
uncertainty statement from genuinely future Development observations
```

Because the full uncertainty policy is not executable:

```text
suffix sufficiency = UNRESOLVED_POLICY
```

S5 does not inspect the actual suffix to attempt a sufficiency decision.

---

## 17. Common-N / Nested-Envelope Governance

A future evaluator must not first compute pointwise/marginal intervals for each N and then pick the N whose interval happens to look favorable.

The inferential scope must cover the actual decision mechanism.

At minimum, a future V4 must explicitly answer whether the simultaneous family includes:

- all required TAIL/MAD components,
- all candidate N examined by the policy,
- all nested forward states used in each envelope,
- the final common-N selection rule.

If a theorem supports only a fixed N or fixed statistic, the project may not silently extend it to post-selection common-N validity.

This remains an independent reason why the current method cannot be marked execution-ready.

---

## 18. Method Decision

### Stationary Bootstrap

```text
candidate = STATIONARY_BOOTSTRAP
candidate theoretical compatibility = CONDITIONALLY_SUPPORTED
execution readiness = NO
```

The method is credible as a research candidate under explicit stationary/dependence/regularity conditions.

### Automatic tuning

```text
automatic tuning rule = UNRESOLVED
```

No reviewed source directly justifies one fully specified automatic rule for the complete heterogeneous nested/common-N StockScope target.

### Dependence assumption

```text
dependence assumption = ASSUMPTION_UNRESOLVED
assumption verified = NO
assumption proven = NO
```

### Joint multiplicity

```text
joint dependence-aware error control = CONCEPTUALLY_SUPPORTED
StockScope simultaneous procedure = UNRESOLVED
joint error budget = null
```

---

## 19. Final R2.4 Verdict

The requirements for `METHOD_AND_RISK_BUDGET_JUSTIFIED` are not met.

The requirements for `METHOD_JUSTIFIED_RISK_BUDGET_UNRESOLVED` are also not met because the complete statistic-specific automatic tuning and nested/common-N joint procedure remain unresolved. Partial support for the stationary bootstrap and for individual functionals cannot be promoted to a full method approval.

Therefore:

```text
R2.4 VERDICT
NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY

Dependence method
STATIONARY_BOOTSTRAP
CONDITIONALLY_SUPPORTED_CANDIDATE / NOT EXECUTION_READY

Automatic tuning rule
UNRESOLVED

Dependence assumption
ASSUMPTION_UNRESOLVED
Assumption verified = NO

Joint multiplicity
CONCEPTUALLY_SUPPORTED
STOCKSCOPE_TRANSFER_UNRESOLVED

Risk-budget source
NONE

Confidence/error budget
null

TAIL tolerance
null

MAD normalized median tolerance
null

MAD relative scale tolerance
null

Suffix sufficiency
UNRESOLVED_POLICY

Reference Adequacy
UNRESOLVED

minimum_prior_observations
null

recommended_support
null

RATE_SPIKE
UNCALIBRATED

Ready for V4 evaluator implementation
NO

Ready for adequacy evaluation
NO

Ready for Holdout
NO

Production impact
NONE
```

This is a normal fail-closed research result.

---

## 20. Why the Verdict Is Not Stronger

The negative verdict does **not** mean:

- stationary bootstrap is invalid,
- block bootstrap can never work for the StockScope statistics,
- no future statistic-specific selector can be designed,
- no future risk budget can be approved.

It means the reviewed primary literature and approved project/domain governance sources do not currently justify the complete numeric policy required by V3 without introducing additional unapproved assumptions or project choices.

In particular, four gaps remain:

1. actual dependence assumptions are not verified;
2. a full-family statistic-specific automatic block selector is not justified;
3. simultaneous coverage for the nested/common-N selection mechanism is not frozen;
4. no independent operational risk budget exists.

---

## 21. Next-Step Contract

Do **not** proceed directly to Development adequacy evaluation.

The next work should first decide how the project wishes to resolve the two qualitatively different blockers.

### Track A — Method research

A future research task may attempt to derive or locate a formally justified selector and simultaneous procedure for the exact joint functional.

It must be preregistered before inspecting favorable Development outcomes.

### Track B — Risk-budget requirement

A separate governance decision is required if StockScope wants an operational tolerance.

That decision must define why a level of reference movement is acceptable for the product. Statistical uncertainty may inform the decision but may not silently become the operational tolerance.

Until both tracks are resolved:

```text
NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY
```

remains active.

---

## 22. Self-Check

```text
Development result inspected for tuning = NO
Development adequacy evaluator executed = NO
Development numeric parameter selected = NO

Holdout accessed = NO

Numeric tolerance invented = NO
Conventional alpha adopted without justification = NO
Manual block length selected = NO
Outcome-driven method fallback = NO

Candidate survival used = NO
Signal survival used = NO
Episode survival used = NO

Bootstrap executed = NO
Runtime artifact created = NO
Runtime writes = 0
Backend code changed = NO
Frontend changed = NO
DB schema changed = NO
Migration changed = NO
V3 protocol changed = NO

Reference Adequacy resolved = NO
minimum_prior_observations selected = NO
recommended_support selected = NO
RATE_SPIKE calibrated = NO

Production behavior changed = NO
Production impact = NONE
```

---

## 23. Source Register

### Primary/statistical sources

1. Politis, D. N. & Romano, J. P. (1994). The Stationary Bootstrap. JASA 89(428), 1303-1313.  
   https://doi.org/10.1080/01621459.1994.10476870

2. Bühlmann, P. (1994). Blockwise Bootstrapped Empirical Process for Stationary Sequences. Annals of Statistics 22(2), 995-1012.  
   https://doi.org/10.1214/aos/1176325508

3. Bühlmann, P. & Künsch, H. R. (1999). Block length selection in the bootstrap for time series. Computational Statistics & Data Analysis 31(3), 295-310.  
   https://doi.org/10.1016/S0167-9473(99)00014-6

4. Politis, D. N. & White, H. (2004). Automatic Block-Length Selection for the Dependent Bootstrap. Econometric Reviews 23(1), 53-70.  
   https://doi.org/10.1081/ETC-120028836

5. Patton, A., Politis, D. N. & White, H. (2009). Correction to "Automatic Block-Length Selection for the Dependent Bootstrap". Econometric Reviews 28(4), 372-375.  
   https://doi.org/10.1080/07474930802459016

6. Kuffner, T. A., Lee, S. M. S. & Young, G. A. (2021). Block bootstrap optimality and empirical block selection for sample quantiles with dependent data. Biometrika 108(3), 675-692.  
   https://doi.org/10.1093/biomet/asaa075

7. Dedecker, J. & Merlevède, F. (2007). The empirical distribution function for dependent variables: asymptotic and nonasymptotic results in Lp. ESAIM: Probability and Statistics 11, 102-114.  
   https://doi.org/10.1051/ps:2007009

8. Hwang, E. (2021). Weak convergence for stationary bootstrap empirical processes of associated sequences. Journal of the Korean Mathematical Society 58(1), 237-264.  
   https://doi.org/10.4134/JKMS.j200064

9. Romano, J. P. & Wolf, M. (2005). Stepwise Multiple Testing as Formalized Data Snooping. Econometrica 73(4), 1237-1282.  
   https://doi.org/10.1111/j.1468-0262.2005.00615.x

### Official governance/domain sources

10. Board of Governors of the Federal Reserve System (2026). SR 26-2, Revised Guidance on Model Risk Management.  
    https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm

11. Basel Committee on Banking Supervision. Basel Framework — Market Risk, model validation and backtesting provisions.  
    https://www.bis.org/baselframework/

---

## 24. Completion Statement

R2.4 research review is complete as a preregistration/governance investigation.

The result is deliberately fail-closed:

```text
NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY
```

No code, evaluator, runtime state, policy threshold, Development evaluation, Holdout data, or Production behavior was changed.
