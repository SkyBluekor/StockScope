# NEXT-6B-S4.2-B.1.6-R2.3 — Independent Reference-Adequacy Evidence & Risk-Budget Preregistration

## 1. Scope

R2.3 preregisters the **rules for choosing and running** a future Reference Adequacy uncertainty procedure before any new tolerance, suffix threshold, or minimum prior-support boundary is selected from Development evidence.

This is a **research / preregistration only** task.

It does not:

- select a TAIL tolerance,
- select a MAD tolerance,
- select a validation suffix count or duration,
- select `minimum_prior_observations`,
- approve Reference Adequacy,
- calibrate RATE_SPIKE,
- access Holdout,
- modify code,
- create a runtime artifact,
- modify Production behavior.

Frozen baseline:

- GitHub `main`: `a8d0e4fdfb5923a4cd6a83195b00bececf298650`
- Reference Adequacy Protocol: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`
- R2.1 current compact evidence: `REFERENCE-ADEQUACY-EVIDENCE-46e5a9c059f72187.json.gz`
- common support points: 1,488
- reference families: 6
- forward comparisons: 8,716,632
- `minimum_prior_observations = null`
- `recommended_support = null`
- `reference_adequacy = UNRESOLVED`
- `RATE_SPIKE = UNCALIBRATED`
- Holdout: locked / unread
- Production impact: `NONE`

R2.2 concluded:

- U01 TAIL tolerance → `NEEDS_PREREGISTERED_EVIDENCE`
- U02 MAD tolerance structure → two normalized dimensions are justified, but numeric tolerances remain unresolved
- U03 suffix sufficiency → `NEEDS_PREREGISTERED_EVIDENCE`

---

## 2. Preregistration objective

The objective is not to obtain a favorable numeric result.

The objective is to constrain researcher degrees of freedom before Development evidence is used again.

The prohibited order is:

```text
inspect Development envelope
→ choose bootstrap / block length / alpha that looks reasonable
→ obtain a tolerable boundary
→ declare the procedure justified
```

The required order is:

```text
freeze admissible assumptions
→ freeze method-selection rules
→ freeze tuning rules
→ freeze risk-budget source rules
→ freeze multiplicity handling
→ freeze fail-closed behavior
→ only then permit a later Development evaluation
```

Candidate survival, signal survival, episode survival, covered-year count, and a visually desirable N distribution remain forbidden inputs.

---

## 3. Frozen lineage

R2.3 is anchored to the current Development-only lineage.

The future procedure may use only artifacts that validate against the current Development lineage and current V3 Reference Adequacy contract.

The procedure must not accept:

- Holdout content,
- Holdout-derived statistics,
- Production outcomes,
- future candidate performance,
- broker activity,
- scanner behavior changes.

Any future implementation must preserve:

```text
holdout_locked = true
holdout_accessed = false
network_requests = 0 during local evidence evaluation
macro_db_writes = 0
production_impact = NONE
```

---

## 4. Statistical uncertainty and operational risk budget are separate

R2.3 freezes the distinction:

### 4.1 Statistical uncertainty

```text
STATISTICAL_UNCERTAINTY
=
uncertainty caused by finite, dependent observations
when estimating the reference state / reference-change statistic
```

### 4.2 Operational risk budget

```text
OPERATIONAL_RISK_BUDGET
=
how much reference movement StockScope is willing to regard
as acceptable for the purpose of using that reference operationally
```

A confidence interval width does not automatically become an operational tolerance.

Example of a forbidden inference:

```text
estimated uncertainty = 0.017
therefore TAIL tolerance = 0.017
```

R2.3 therefore requires future contracts to store these separately:

```text
uncertainty_method
risk_budget_source
risk_budget_value
```

The uncertainty method may estimate variability while the risk budget remains unresolved.

---

## 5. Risk-budget source hierarchy

A future numeric tolerance is admissible only if its source is one of:

```text
1. EXISTING_PROJECT_REQUIREMENT
2. EXTERNAL_DOMAIN_REQUIREMENT
3. FORMAL_STATISTICAL_ERROR_CONTROL
4. NONE
```

The following are explicitly **not admissible** risk-budget sources:

- Development envelope shape,
- Development quantiles selected after inspection,
- candidate survival,
- signal survival,
- episode survival,
- covered years,
- number of passing N values,
- desired UI behavior,
- desire to preserve a method or horizon.

Current R2.3 state:

```text
risk_budget_source = NONE
risk_budget_value = null
numeric_policy_status = UNJUSTIFIED
```

This is not a failure of computation. It is a deliberate fail-closed policy state.

---

## 6. Conventional confidence levels are not silently adopted

R2.3 does not adopt:

```text
alpha = 0.05
confidence = 95%
```

merely because those values are conventional.

A future confidence/error budget must contain:

```text
value
source
justification
scope
multiplicity_scope
status
```

Until an independent source exists:

```text
confidence_level = null
error_budget = null
status = UNJUSTIFIED
```

---

## 7. Dependence assumption contract

### 7.1 Why iid is not the default

The three RATE_SPIKE feature series are chronological DGS10-derived time-series features.

The repository constructs:

```text
delta_bp_1obs
delta_bp_5obs
delta_bp_10obs
```

from successive observations.

R2.3 therefore forbids treating the input sequence as i.i.d. merely for convenience.

### 7.2 Primary admissible assumption class for block resampling

The literature supports stationary-bootstrap inference for weakly dependent stationary observations.

Politis and Romano introduced the stationary bootstrap for standard errors and confidence regions under weak dependence and stationarity:

- D. N. Politis and J. P. Romano,
  *The Stationary Bootstrap*,
  Journal of the American Statistical Association 89(428), 1994.
- DOI: https://doi.org/10.1080/01621459.1994.10476870

Later consistency work gives validity under near-epoch-dependence / mixing-style conditions and weak moment assumptions:

- S. Gonçalves and R. de Jong,
  *Consistency of the stationary bootstrap under weak moment conditions*,
  Economics Letters 81(2), 2003.
- DOI: https://doi.org/10.1016/S0165-1765(03)00192-7

Therefore the conditional assumption class is frozen as:

```text
PRIMARY_DEPENDENCE_ASSUMPTION
=
STATIONARY_WEAK_DEPENDENCE
```

This is a **required modeling assumption**, not a claim that StockScope has proven it.

Current assumption state:

```text
assumption_required = true
assumption_verified = false
assumption_proven = false
```

---

## 8. Assumption diagnostics

R2.3 rejects the idea that one statistical test can prove stationarity or weak dependence.

Diagnostics may be used to identify obvious incompatibility, but they cannot upgrade the assumption to `PROVEN`.

Future diagnostics may include:

- serial-correlation summaries,
- correlogram structure,
- rolling distribution summaries,
- structural-break sensitivity,
- stationarity-oriented diagnostics,
- dependence-strength summaries.

Their allowed roles are:

```text
INFORMATIONAL
ASSUMPTION_SUPPORTING
ASSUMPTION_REJECTING
```

No future diagnostic may use:

```text
p < 0.05
```

as an automatic project-level assumption approval unless that error budget itself has been independently preregistered.

R2.3 therefore does **not** freeze a pass/fail stationarity-test threshold.

---

## 9. External empirical-process evidence

Dependent empirical-distribution theory exists, including nonasymptotic and asymptotic results under explicit dependence conditions.

Example:

- J. Dedecker and F. Merlevède,
  *The empirical distribution function for dependent variables: asymptotic and nonasymptotic results in Lp*,
  ESAIM: Probability and Statistics 11, 2007.
- DOI: https://doi.org/10.1051/ps:2007009

This supports the conclusion that dependence-aware empirical-process analysis is possible.

It does not provide StockScope with a parameter-free numeric TAIL tolerance for the current nested forward-envelope statistic.

R2.3 therefore does not adopt a closed-form analytic bound.

---

## 10. Primary uncertainty-method candidate

### 10.1 Conditional primary method

R2.3 preregisters the **stationary bootstrap** as the primary method candidate if all method-applicability requirements can be justified.

Reason:

- it is specifically designed for weakly dependent stationary observations,
- it preserves temporal dependence through block resampling,
- it avoids pretending the chronological feature rows are independent,
- it can generate joint resampling distributions rather than independent per-family approximations.

Frozen label:

```text
PRIMARY_UNCERTAINTY_METHOD_CANDIDATE
=
STATIONARY_BOOTSTRAP
```

### 10.2 Execution status

The method is not yet executable as a frozen StockScope adequacy procedure.

Current status:

```text
method_candidate_frozen = true
method_execution_ready = false
```

The reason is the unresolved statistic-specific tuning rule and unresolved risk budget described below.

---

## 11. Block-length tuning is not manually selectable

R2.3 freezes:

```text
MANUAL_BLOCK_LENGTH = FORBIDDEN
```

Politis and White proposed automatic block-length estimators for dependent bootstrap procedures:

- D. N. Politis and H. White,
  *Automatic Block-Length Selection for the Dependent Bootstrap*,
  Econometric Reviews 23(1), 2004.
- DOI: https://doi.org/10.1081/ETC-120028836

A published correction changed the optimal-block-size algorithms:

- A. Patton, D. N. Politis, H. White,
  *Correction to “Automatic Block-Length Selection for the Dependent Bootstrap”*,
  Econometric Reviews 28(4), 2009.
- DOI: https://doi.org/10.1080/07474930802459016

However R2.3 does **not** freeze that algorithm as the final StockScope block selector yet.

Why:

- the target R2.1 statistics are joint ECDF-sup and robust median/MAD forward-envelope statistics,
- optimal block size can depend on the target statistic / inferential problem,
- statistic-specific block selection is a real issue in the literature.

For example, dependent sample quantiles have dedicated block-selection theory:

- T. A. Kuffner, S. M. S. Lee, G. A. Young,
  *Block bootstrap optimality and empirical block selection for sample quantiles with dependent data*,
  Biometrika 108(3), 2021.
- DOI: https://doi.org/10.1093/biomet/asaa075

Therefore:

```text
automatic_block_selector
=
UNRESOLVED_STATISTIC_SPECIFIC_RULE
```

and:

```text
manual_override = forbidden
```

---

## 12. No outcome-driven method fallback

R2.3 explicitly rejects a broad method-shopping hierarchy.

Forbidden:

```text
stationary bootstrap gives a large N
→ try moving-block bootstrap

moving-block bootstrap still large
→ try subsampling

subsampling looks better
→ keep subsampling
```

Instead:

```text
if the preregistered primary method is not theoretically justified
or its required tuning rule cannot be frozen
→ METHOD_INAPPLICABLE / UNRESOLVED
```

No alternative method is selected based on favorable Development output.

A future R2.4 research task may replace the primary method only **before** evaluation and only through a new preregistered contract/version.

---

## 13. Why subsampling is not silently used as a fallback

Subsampling has broad theory for stationary and nonstationary time series, and the standard reference explicitly treats block-size choice as a separate practical issue:

- D. N. Politis, J. P. Romano, M. Wolf,
  *Subsampling*,
  Springer Series in Statistics, 1999.
- DOI: https://doi.org/10.1007/978-1-4612-1554-7

The book contains separate chapters for:

- stationary time series,
- nonstationary time series,
- confidence sets for general parameters,
- choice of block size.

Therefore subsampling does not remove the tuning problem.

R2.3 does not use it as an automatic escape hatch.

---

## 14. Numerical approximation parameters are separate from policy parameters

R2.3 distinguishes:

```text
POLICY_PARAMETER
```

from:

```text
NUMERICAL_ACCURACY_PARAMETER
```

Examples of numerical parameters:

- number of resamples,
- Monte Carlo convergence tolerance,
- PRNG configuration,
- maximum compute cap.

These parameters do not define acceptable reference movement, but they still affect reproducibility.

R2.3 does not choose a resample count merely by convention.

Future implementation must preregister either:

- a deterministic count with independent numerical justification, or
- a deterministic Monte Carlo stopping rule.

Current:

```text
resample_count = null
monte_carlo_stopping_rule = null
```

---

## 15. Reproducibility contract for any future resampling

If stochastic resampling is eventually approved, future implementation must freeze:

```text
PRNG algorithm
seed derivation
resample ordering
parallelism-independent logical identity
```

The seed must not be manually entered per run.

Preferred deterministic derivation shape:

```text
seed_material =
  Development dataset hash
  + Reference Adequacy protocol hash
  + preregistration contract version
  + target statistic identity
```

The exact PRNG and derivation hash are deferred until implementation and must become versioned contract fields.

---

## 16. Multiplicity policy

### 16.1 Multiplicity exists

Required adequacy components are not one scalar test.

After R2.2 structural reduction there are:

- 3 TAIL horizon components,
- 3 MAD horizon families × 2 normalized components.

Therefore the future procedure must account for a **joint set of required adequacy components**.

### 16.2 Independent per-component alpha is forbidden

R2.3 freezes:

```text
INDEPENDENT_PER_COMPONENT_ALPHA
=
FORBIDDEN
```

A future uncertainty method must use a joint/simultaneous error-control structure.

Resampling-based multiple-testing literature demonstrates procedures that capture dependence among test statistics while controlling familywise error:

- J. P. Romano and M. Wolf,
  *Stepwise Multiple Testing as Formalized Data Snooping*,
  Econometrica 73(4), 2005.
- DOI: https://doi.org/10.1111/j.1468-0262.2005.00615.x

This supports use of a joint resampling distribution rather than pretending components are independent.

### 16.3 What is frozen now

R2.3 freezes the scope, not a numeric alpha:

```text
multiplicity_scope
=
ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY
```

and:

```text
joint_error_budget = null
```

Raw heterogeneous statistics must not be directly maxed without justified normalization/studentization.

---

## 17. TAIL preregistration

TAIL adequacy metric remains:

```text
ECDF_SUP_DISTANCE
```

with:

```text
comparison
=
ANCHOR_N_TO_EVERY_LATER_REFERENCE_STATE

aggregation
=
MAX_OVER_VALIDATION_SUFFIX

reference_support
=
OBSERVED_VALUES_UNION_ONLY

invented_x_grid_points
=
0
```

R2.3 freezes no TAIL tolerance.

Current:

```text
tail_tolerance = null
tail_risk_budget_source = NONE
tail_numeric_policy_status = UNJUSTIFIED
```

The future uncertainty method must treat all three TAIL horizon components within the common joint multiplicity scope.

---

## 18. MAD two-dimensional preregistration

R2.2 established that absolute and relative MAD movement are algebraically redundant once anchor MAD is fixed.

R2.3 freezes the future MAD adequacy dimensions as:

```text
NORMALIZED_MEDIAN_SHIFT(N,t)
=
|median_t - median_N| / |MAD_N|

RELATIVE_MAD_SHIFT(N,t)
=
|MAD_t - MAD_N| / |MAD_N|
```

for `MAD_N != 0`.

The following remain audit diagnostics only:

```text
ABS_MEDIAN_SHIFT_BP
ABS_MAD_SHIFT_BP
```

Future gate structure:

```text
MAD adequacy dimensions
=
NORMALIZED_MEDIAN_SHIFT
AND
RELATIVE_MAD_SHIFT
```

Numeric tolerances remain:

```text
normalized_median_shift_tolerance = null
relative_mad_shift_tolerance = null
```

---

## 19. MAD zero-scale handling

Existing behavior is preserved.

If:

```text
MAD_N == 0
```

then:

```text
status = NON_COMPUTABLE_ZERO_SCALE
```

R2.3 freezes:

```text
null_to_zero = forbidden
zero_scale_as_stable = forbidden
zero_scale_as_pass = forbidden
```

Because common N must satisfy all required reference methods/horizons:

```text
MAD non-computable at candidate N
→ candidate N cannot establish complete MAD reference adequacy
```

This is an evidence-computability failure, not evidence of instability.

---

## 20. Validation suffix sufficiency

### 20.1 Standalone arbitrary K is removed as the preferred design

R2.3 freezes the design objective:

```text
DO NOT CREATE AN INDEPENDENT ARBITRARY
MINIMUM_VALIDATION_SUFFIX_TRANSITIONS = K
```

Instead suffix sufficiency should be derived from the approved uncertainty procedure.

Proposed structural rule:

```text
suffix is SUFFICIENT
iff
the preregistered uncertainty procedure can compute
the required joint adequacy statistic and uncertainty statement
using genuinely future Development evidence after anchor N
```

### 20.2 State model

Future suffix status must be one of:

```text
SUFFICIENT
INSUFFICIENT
NON_COMPUTABLE
UNRESOLVED_POLICY
```

`INSUFFICIENT` must not be collapsed into reference instability.

### 20.3 R2.3 decision on U03

R2.3 structurally eliminates the need for a separately hand-selected suffix K.

However, because the final uncertainty procedure is not executable yet, actual suffix sufficiency remains unevaluable.

Decision:

```text
U03 standalone numeric parameter
=
JUSTIFIED_STRUCTURAL_ELIMINATION

U03 operational status
=
BLOCKED_BY_UNRESOLVED_UNCERTAINTY_METHOD
```

---

## 21. No-supported-boundary rule

After all future statistical and risk-budget rules are frozen, a Development evaluation may find no N satisfying all gates.

R2.3 freezes:

```text
no passing common N
→ NO_SUPPORTED_BOUNDARY
```

Forbidden reactions:

- relax TAIL tolerance,
- relax MAD tolerance,
- shrink multiplicity scope,
- remove a horizon,
- switch uncertainty method,
- reduce evidence requirement,
- shorten suffix requirement,
- select method-specific N,
- select horizon-specific N.

---

## 22. Fail-closed conditions

Future evaluation must stop without selecting N if any of the following applies:

```text
dependence assumption not accepted
uncertainty method not justified
automatic tuning rule unresolved
risk budget source NONE
confidence/error budget unresolved
multiplicity handling unresolved
MAD zero-scale prevents required computation
joint procedure non-computable
suffix evidence non-computable
artifact lineage mismatch
Holdout access detected
```

Required result:

```text
reference_adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED
```

---

## 23. Prohibited adaptations

After a future preregistration version is frozen, the following are forbidden:

1. inspect Development outcomes and change the method;
2. inspect Development outcomes and change block length manually;
3. inspect Development outcomes and change confidence/error budget;
4. change joint multiplicity scope to preserve a method;
5. remove a failing horizon;
6. change normalized MAD dimensions;
7. convert zero-scale null to zero;
8. choose N based on candidate/signal/episode survival;
9. choose a smaller evidence requirement because no N passes;
10. use Holdout to decide any calibration parameter.

Any change requires a new preregistration version and must occur before the corresponding evaluation.

---

## 24. Preregistration decision matrix

| Item | R2.3 state | Frozen? | Executable? |
|---|---|---:|---:|
| iid default | FORBIDDEN | YES | N/A |
| dependence assumption class | STATIONARY_WEAK_DEPENDENCE required for primary candidate | YES | NO — not verified |
| primary uncertainty method candidate | STATIONARY_BOOTSTRAP | YES | NO |
| manual block length | FORBIDDEN | YES | N/A |
| exact automatic block selector | UNRESOLVED_STATISTIC_SPECIFIC_RULE | NO | NO |
| automatic outcome-driven fallback | FORBIDDEN | YES | N/A |
| resample count | null | NO | NO |
| deterministic seed requirement | REQUIRED | YES | NO implementation yet |
| risk-budget source hierarchy | frozen hierarchy | YES | YES |
| current risk-budget source | NONE | YES factual state | NO numeric policy |
| confidence/error budget | null | NO | NO |
| multiplicity scope | all required components jointly | YES | NO numeric budget |
| TAIL metric | ECDF_SUP_DISTANCE | YES | YES metric only |
| TAIL tolerance | null | NO | NO |
| MAD dimensions | NORMALIZED_MEDIAN_SHIFT + RELATIVE_MAD_SHIFT | YES | YES metric structure |
| absolute MAD/median bp shifts | DIAGNOSTIC_ONLY | YES | YES |
| MAD numeric tolerances | null | NO | NO |
| zero-scale handling | NON_COMPUTABLE_ZERO_SCALE fail-closed | YES | YES |
| standalone suffix K | structurally rejected | YES | N/A |
| suffix sufficiency | method-defined computability/evidence sufficiency | YES structure | NO |
| no-match result | NO_SUPPORTED_BOUNDARY | YES | YES |

---

## 25. R2.3 readiness verdict

R2.3 does **not** support immediate execution of R2.1 evidence against a numeric adequacy policy.

The method architecture is now substantially constrained, but two critical prerequisites remain independently unresolved:

### R2.3-U1 — Statistic-specific dependence tuning

A stationary-bootstrap candidate is identified, but no automatic block-selection rule has yet been justified specifically for the joint StockScope target statistics:

- TAIL ECDF-sup forward envelopes,
- normalized median-shift envelopes,
- relative MAD-shift envelopes,
- common joint multiplicity scope.

### R2.3-U2 — Independent risk/error budget

No existing StockScope project requirement or external domain requirement currently fixes:

- confidence/error budget,
- TAIL acceptable probability movement,
- normalized center movement,
- relative scale movement.

The R2.1 Development envelope cannot supply these values without post-hoc policy selection.

---

## 26. Final result

```text
R2.3 RESULT
METHOD_FRAMEWORK_PREREGISTERED_NUMERIC_POLICY_BLOCKED

Preregistration complete for execution
NO

Primary uncertainty method candidate
STATIONARY_BOOTSTRAP

Dependence assumption
STATIONARY_WEAK_DEPENDENCE
REQUIRED / NOT VERIFIED

Automatic block selector
UNRESOLVED_STATISTIC_SPECIFIC_RULE

Manual tuning
FORBIDDEN

Outcome-driven fallback
FORBIDDEN

Risk-budget hierarchy
FROZEN

Current risk-budget source
NONE

Confidence/error budget
null

Multiplicity scope
ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY

TAIL metric
FROZEN

TAIL tolerance
null

MAD dimensions
NORMALIZED_MEDIAN_SHIFT
RELATIVE_MAD_SHIFT

MAD tolerances
null

Standalone suffix K
STRUCTURALLY ELIMINATED

Suffix evaluation
BLOCKED_BY_UNRESOLVED_UNCERTAINTY_METHOD

Can select minimum N
NO

Can approve reference adequacy
NO

Ready for B.2
NO

Ready for Holdout
NO

minimum_prior_observations
null

recommended_support
null

RATE_SPIKE
UNCALIBRATED

Holdout
LOCKED / UNREAD

Production
NONE
```

---

## 27. Next research task

The next task should not be Development evaluation.

It should be:

```text
NEXT-6B-S4.2-B.1.6-R2.4
Statistic-Specific Dependence Method & Risk-Budget Governance Review
```

R2.4 should answer exactly two remaining questions:

1. Can a statistic-specific automatic tuning rule be justified for the joint TAIL/MAD reference-adequacy statistic without inspecting favorable Development outcomes?
2. Is there any independent StockScope/domain/statistical governance basis for a numeric family-wide error/risk budget?

If either remains unresolved, R2.4 must preserve:

```text
NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY
```

and must not proceed to minimum-N selection.

---

## 28. R2.3 completion checks

- frozen lineage recorded: PASS
- uncertainty vs operational risk separated: PASS
- risk-budget source hierarchy frozen: PASS
- conventional 95% default rejected: PASS
- iid default rejected: PASS
- conditional weak-dependence assumption documented: PASS
- stationary-bootstrap primary candidate documented: PASS
- manual block length forbidden: PASS
- statistic-specific tuning gap identified: PASS
- outcome-driven method fallback forbidden: PASS
- numerical vs policy parameters separated: PASS
- deterministic future randomness requirement frozen: PASS
- joint multiplicity scope frozen: PASS
- TAIL metric frozen, tolerance unset: PASS
- MAD 2D structure frozen: PASS
- MAD zero-scale fail-closed rule frozen: PASS
- arbitrary standalone suffix K structurally eliminated: PASS
- NO_SUPPORTED_BOUNDARY frozen: PASS
- prohibited adaptations frozen: PASS
- Development evidence used to choose numeric value: NO
- candidate/signal/episode survival used: NO
- Holdout accessed: NO
- code changed: NO
- runtime artifact changed: NO
- next stage identified: R2.4 method/risk-budget governance
