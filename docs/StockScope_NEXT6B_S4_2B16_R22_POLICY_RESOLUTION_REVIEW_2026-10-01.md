# NEXT-6B-S4.2-B.1.6-R2.2 — Remaining Three Policy-Class Resolution Review

## 1. Purpose

R2.2 reviews the three unresolved Reference Adequacy policy classes that remain after R2/R2.1:

1. `TAIL_FORWARD_ENVELOPE_TOLERANCE_UNJUSTIFIED`
2. `MAD_FORWARD_ENVELOPE_TOLERANCES_UNJUSTIFIED`
3. `VALIDATION_SUFFIX_SUFFICIENCY_UNRESOLVED`

This is a **Development-informed research/review task only**.

It does not:

- choose a TAIL tolerance,
- choose a MAD tolerance,
- choose a validation suffix length,
- choose `minimum_prior_observations`,
- approve Reference Adequacy,
- calibrate RATE_SPIKE,
- access Holdout,
- modify Production behavior.

Current baseline:

- GitHub `main`: `f2bd6ff0141f6c7de0ac281da1fc26cea1c450f4`
- Protocol: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`
- Current unresolved policy classes: 3
- Current compact R2.1 evidence: `REFERENCE-ADEQUACY-EVIDENCE-46e5a9c059f72187.json.gz`
- Common support points: 1,488
- Reference families: 6
- Forward comparisons: 8,716,632
- `minimum_prior_observations = null`
- `recommended_support = null`
- `reference_adequacy = UNRESOLVED`
- `RATE_SPIKE = UNCALIBRATED`
- Holdout remains locked and unread.

---

## 2. Review rule

R2.1 already contains the full Development forward-envelope evidence.

Therefore R2.2 must not work backwards from a visually convenient Development result.

The forbidden pattern is:

```text
inspect Development envelope
→ find a visually stable region
→ choose tolerance / suffix
→ report that the rule is justified
```

The permitted order is:

```text
define operational/statistical meaning
→ identify candidate-independent basis
→ enumerate assumptions and new free parameters
→ decide whether the basis is independently justified
→ only later apply a preregistered rule to Development evidence
```

Candidate survival, signal survival, episode survival, covered-year count, and a desirable number of surviving N values remain forbidden policy inputs.

---

## 3. External statistical research summary

### 3.1 Classical DKW does not directly justify the StockScope TAIL tolerance

Massart's sharp Dvoretzky–Kiefer–Wolfowitz result is stated for an empirical distribution based on **i.i.d.** observations and bounds the distance between that empirical CDF and a population CDF.

Source:

- Pascal Massart, *The Tight Constant in the Dvoretzky-Kiefer-Wolfowitz Inequality*, Annals of Probability 18(3), 1990, DOI 10.1214/aop/1176990746.
- https://doi.org/10.1214/aop/1176990746

The StockScope R2.1 statistic is not this setting.

It compares:

```text
F_N
vs
F_t, t > N
```

where:

- the samples are nested,
- the later empirical reference contains the earlier reference,
- the observations are chronologically ordered macro time-series feature values.

Two-sample DKW literature normally formulates the two empirical CDFs as coming from independent i.i.d. samples under the null. That is also not the R2.1 nested-sample construction.

Source:

- Fan Wei and Richard M. Dudley, *Two-sample Dvoretzky–Kiefer–Wolfowitz inequalities*, Statistics & Probability Letters 82(3), 2012.
- https://doi.org/10.1016/j.spl.2011.11.012

**R2.2 decision:** a classical one-sample or independent two-sample DKW number must not be copied into the StockScope protocol.

---

### 3.2 Dependence-aware empirical-process theory exists, but it introduces assumptions

The literature contains empirical-process and empirical-distribution results for dependent observations, including weakly dependent and mixing processes.

Examples:

- Jérôme Dedecker and Florence Merlevède, *The empirical distribution function for dependent variables: asymptotic and nonasymptotic results in Lp*, ESAIM: Probability and Statistics 11, 2007.
- https://doi.org/10.1051/ps:2007009

- Herold Dehling and Walter Philipp (eds./related literature surveyed in), *Empirical Process Techniques for Dependent Data*, Springer.
- https://doi.org/10.1007/978-1-4612-0099-4

These results do **not** give StockScope a parameter-free tolerance for free. They require assumptions about the dependence structure, stationarity/mixing behavior, regularity, or the statistic being studied.

R2.2 has not established those assumptions as project invariants for the three DGS10-derived feature series.

**R2.2 decision:** dependence-aware theory is a valid future basis, but no current theorem is adopted as a numeric TAIL tolerance.

---

### 3.3 Block bootstrap is not a parameter-free escape hatch

Block bootstrap and subsampling are established tools for dependent data, but they require a block/window choice.

Lahiri treats block-size choice as a dedicated methodological problem.

Source:

- S. N. Lahiri, *Resampling Methods for Dependent Data*, Springer, 2003.
- https://doi.org/10.1007/978-1-4757-3803-2

Politis and White proposed automatic block-length selection procedures; the fact that such procedures are needed confirms that dependence-aware resampling contains a nontrivial tuning dimension.

Source:

- Dimitris N. Politis and Halbert White, *Automatic Block-Length Selection for the Dependent Bootstrap*, Econometric Reviews 23(1), 2004.
- https://doi.org/10.1081/ETC-120028836

A later correction modified the optimal-block-size algorithms.

Source:

- Andrew Patton, Dimitris N. Politis, Halbert White, *Correction to “Automatic Block-Length Selection for the Dependent Bootstrap”*, Econometric Reviews 28(4), 2009.
- https://doi.org/10.1080/07474930802459016

Block-bootstrap results for sample quantiles under dependence also require mixing assumptions and explicit block-number/block-length choices.

Source:

- T. A. Kuffner, S. M. S. Lee, and G. A. Young, *Block bootstrap optimality and empirical block selection for sample quantiles with dependent data*, Biometrika 108(3), 2021.
- https://doi.org/10.1093/biomet/asaa075

**R2.2 decision:** bootstrap/subsampling may be preregistered later, but R2.2 must not introduce an arbitrary block length, confidence level, repetition count, or candidate-specific tuning step.

---

### 3.4 Median/MAD sampling theory does not directly yield StockScope operational tolerances

The sample median and MAD have established asymptotic theory under standard sampling assumptions.

Source:

- Michael Falk, *Asymptotic independence of median and MAD*, Statistics & Probability Letters 34(4), 1997.
- https://doi.org/10.1016/S0167-7152(96)00199-X

Exact finite-sample MAD distribution results are also available for independent observations with a common distribution.

Source:

- Hideki Nagatsuka et al., *The exact finite-sample distribution of the median absolute deviation about the median of continuous random variables*, Statistics & Probability Letters 83(4), 2013.
- https://doi.org/10.1016/j.spl.2012.12.023

Robust inference for time-series settings requires additional dependence assumptions; published work commonly invokes stationarity/weak-mixing style conditions.

Source:

- Tadeusz Bednarski, *Fréchet differentiability in statistical inference for time series*, Statistical Methods & Applications 19, 2010.
- https://doi.org/10.1007/s10260-010-0143-y

The existence of a sampling distribution or confidence interval for median/MAD does not by itself answer:

> How much movement should StockScope regard as operationally acceptable?

That is a different policy question.

---

## 4. U01 — TAIL forward-envelope tolerance

### 4.1 Operational alignment is valid

StockScope's TAIL candidate method uses:

```text
positive_tail_fraction_ge
```

from the expanding strictly-prior empirical reference.

For any fixed threshold x:

```text
tail_fraction(x) = 1 - F(x-)
```

so a uniform empirical-CDF bound of size epsilon also bounds the change in a fixed-threshold tail probability by epsilon.

Therefore:

```text
sup_x |F_N(x) - F_t(x)| <= epsilon
```

is an operationally relevant reference-stability quantity for the TAIL method.

This justifies the **metric**, not a numeric epsilon.

### 4.2 Why no numeric tolerance is justified

The following candidate-independent numeric sources were considered:

| Basis | R2.2 result |
|---|---|
| Classical DKW | Rejected for direct adoption: i.i.d. / different sampling structure |
| Independent two-sample KS/DKW | Rejected: R2.1 samples are nested, not independent |
| 1/N ECDF resolution | Already rejected in R2; mechanical sample-size effect |
| Measurement precision | Does not define acceptable probability movement |
| Development envelope quantile/max | Post-hoc if used to choose tolerance |
| Dependent empirical-process bound | Potentially usable only after assumptions are preregistered and verified |
| Block bootstrap/subsampling | Potentially usable, but adds block/bandwidth and confidence-policy choices |

### 4.3 U01 decision

```text
policy_class:
  R2-U01 TAIL_FORWARD_ENVELOPE_TOLERANCE

candidate_independent_basis:
  EXTERNAL_STATISTICAL_THEORY — POTENTIAL ONLY

required_assumptions:
  dependence/stationarity model or dependence class
  applicability to nested expanding empirical references
  error/confidence budget

new_free_parameters:
  confidence/error budget
  possible dependence bandwidth / block length
  possible resampling count if simulation is used

assumptions_verified:
  false

resolution:
  NEEDS_PREREGISTERED_EVIDENCE

numeric_value_selected:
  false

holdout_used:
  false
```

**U01 remains unresolved.**

---

## 5. U02 — MAD tolerance structure

### 5.1 Current StockScope robust score

The repository computes:

```text
robust_deviation_mad
=
(value - prior_median) / prior_mad
```

and the MAD method is unavailable when prior MAD is zero.

Therefore reference change affects the method through exactly two reference components:

1. center: prior median,
2. scale: prior MAD.

### 5.2 The current three-gate representation contains an avoidable scale duplication

V3 currently measures:

```text
ABS_MEDIAN_SHIFT
ABS_MAD_SHIFT
REL_MAD_SHIFT
```

For a fixed anchor N with nonzero anchor MAD:

```text
REL_MAD_SHIFT
=
ABS_MAD_SHIFT / abs(MAD_N)
```

So absolute and relative MAD shift are not two independent pieces of evidence. One is an exact rescaling of the other once the anchor scale is known.

R2.1 already stores enough information to reconstruct this relation exactly.

### 5.3 Candidate-independent normalized representation

For the robust score, a more structurally aligned representation is:

```text
NORMALIZED_MEDIAN_SHIFT(N,t)
=
|median_t - median_N| / MAD_N

RELATIVE_MAD_SHIFT(N,t)
=
|MAD_t - MAD_N| / MAD_N
```

when `MAD_N != 0`.

These two dimensionless quantities correspond directly to:

- movement of the numerator reference center relative to anchor scale,
- movement of the denominator scale relative to anchor scale.

The raw basis-point shifts remain useful audit diagnostics, but they do not need separate adequacy tolerances.

If `MAD_N == 0`:

```text
MAD reference support = NON_COMPUTABLE_ZERO_SCALE
```

and no normalization to zero is allowed.

### 5.4 What this structural reduction does not solve

It removes a redundant policy dimension, but it still does not tell us what numerical normalized movement is acceptable.

A bound on perturbation of the robust score would still require an allowed score-error budget. For example, changes in center and scale can be translated into a bound on score perturbation, but the amount of score perturbation that StockScope is willing to tolerate remains an external policy choice unless independently justified.

Published median/MAD sampling theory can estimate statistical uncertainty under assumptions, but it does not supply StockScope's operational acceptance budget.

### 5.5 U02 decision

```text
policy_class:
  R2-U02 MAD_FORWARD_ENVELOPE_TOLERANCES

candidate_independent_basis:
  EXISTING_PROJECT_INVARIANT + ALGEBRAIC_STRUCTURE

required_assumptions:
  anchor MAD nonzero for robust score availability

new_free_parameters:
  normalized center-movement tolerance
  normalized scale-movement tolerance

assumptions_verified:
  robust method already treats MAD=0 as unavailable

resolution:
  JUSTIFIED_STRUCTURAL_REDUCTION
  +
  NEEDS_PREREGISTERED_EVIDENCE

numeric_value_selected:
  false

holdout_used:
  false
```

Recommended future contract shape:

```text
MAD adequacy gates:
  NORMALIZED_MEDIAN_SHIFT
  RELATIVE_MAD_SHIFT

MAD diagnostic-only:
  ABS_MEDIAN_SHIFT_BP
  ABS_MAD_SHIFT_BP
```

This reduces U02 from **three numeric tolerance dimensions to two**, without choosing either value.

---

## 6. Measurement precision review

The repository computes DGS10 rate-delta features as:

```text
(current normalized yield - baseline normalized yield) * 100
```

with unit:

```text
BASIS_POINT
```

This establishes the feature unit and exact Decimal transformation used by StockScope.

It does **not** establish an operational adequacy tolerance.

R2.2 distinguishes:

```text
measurement resolution
!=
acceptable reference movement
```

Therefore a source/feature precision such as one basis point may be relevant as a lower-level representational constraint, but it cannot by itself justify:

```text
ABS_MEDIAN_SHIFT_TOLERANCE = 1 bp
```

or any other acceptance value.

---

## 7. U03 — Validation suffix sufficiency

### 7.1 Purpose

The suffix rule exists to prevent a candidate N close to the end of Development from being declared stable after only a small number of future transitions.

The operational question is:

> Is there enough genuinely future Development evidence after anchor N to support a reference-stability claim?

### 7.2 Fixed-count candidates are not independently justified

R2.2 finds no existing project invariant that uniquely produces:

```text
30
50
100
252
1 year
one quarter
10 observations
```

as the correct minimum suffix.

The existing 1obs / 5obs / 10obs feature horizons describe feature construction, not the amount of future evidence required to validate reference adequacy.

Therefore:

```text
suffix = max feature horizon
```

is rejected.

### 7.3 Calendar duration does not remove the choice

Replacing transition count with:

```text
one month
one quarter
one year
```

still introduces a policy choice unless a pre-existing operational invariant defines that horizon.

No such invariant is currently present in the Reference Adequacy contract.

### 7.4 Uncertainty-based sufficiency is preferable in principle, but not currently closed

A more principled future rule could be:

```text
suffix is sufficient
iff
the preregistered uncertainty procedure has enough future data
to evaluate the approved stability criterion at its frozen error budget
```

This is preferable to an arbitrary transition count because it ties suffix sufficiency to the statistical evidence needed by the criterion.

However it does not currently resolve U03 because the required dependence-aware uncertainty procedure and error budget are themselves not frozen.

### 7.5 U03 decision

```text
policy_class:
  R2-U03 VALIDATION_SUFFIX_SUFFICIENCY

candidate_independent_basis:
  NONE CURRENTLY FROZEN

required_assumptions:
  depends on future uncertainty/evidence procedure

new_free_parameters:
  fixed K if count-based
  calendar duration if time-based
  or confidence/error budget + dependence parameters if uncertainty-based

assumptions_verified:
  false

resolution:
  NEEDS_PREREGISTERED_EVIDENCE

numeric_value_selected:
  false

holdout_used:
  false
```

**U03 remains unresolved.**

---

## 8. Why a Policy Freeze is not justified yet

R2.2 does not support `R2.3 = Policy Freeze`.

The reason is not lack of data volume. R2.1 already has 8,716,632 forward comparisons.

The remaining problem is **identifiability of acceptable movement**, not absence of measured movement.

More Development-derived envelope values cannot, by themselves, answer what should count as acceptable without creating a post-hoc rule.

The missing ingredients are candidate-independent policy/statistical commitments.

---

## 9. Next step — Independent Evidence & Risk-Budget Preregistration

The next task should be:

```text
NEXT-6B-S4.2-B.1.6-R2.3
Independent Reference-Adequacy Evidence & Risk-Budget Preregistration
```

R2.3 must freeze the experiment **before any tolerance is selected from R2.1 curves**.

### 9.1 Required preregistered decisions

R2.3 should explicitly define:

1. **Dependence model / admissible assumption class**
   - what stationarity or weak-dependence assumptions are required,
   - what can be checked empirically,
   - what cannot be proven from one Development realization.

2. **Uncertainty method**
   - analytic dependent empirical-process result,
   - block bootstrap,
   - stationary bootstrap,
   - subsampling,
   - or another justified method.

3. **Tuning-parameter rule**
   - block length / bandwidth selection, if required,
   - no manual selection after inspecting favorable outcomes.

4. **Error/risk budget**
   - confidence/error level must be frozen independently of candidate survival and Development envelope shape,
   - if there is no independent project requirement for the budget, this fact must remain a blocker.

5. **MAD structural contract**
   - adequacy dimensions:
     - `NORMALIZED_MEDIAN_SHIFT`
     - `RELATIVE_MAD_SHIFT`
   - absolute bp shifts diagnostic-only.

6. **Suffix sufficiency contract**
   - preferably derived from the preregistered uncertainty procedure,
   - otherwise remain unresolved rather than choose an arbitrary K.

### 9.2 R2.3 may still end unresolved

If no candidate-independent error/risk budget can be justified, R2.3 must report:

```text
NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY
```

rather than manufacture a tolerance.

That is a valid fail-closed result.

---

## 10. Decision matrix

| Policy | Current | R2.2 decision | Next step |
|---|---|---|---|
| U01 TAIL tolerance | `None` | **NEEDS_PREREGISTERED_EVIDENCE** | dependence-aware uncertainty + independently frozen error budget |
| U02 MAD tolerances | three `None` tolerances | **JUSTIFIED_STRUCTURAL_REDUCTION + NEEDS_PREREGISTERED_EVIDENCE** | reduce to normalized median + relative MAD gates, then preregister error budget |
| U03 suffix sufficiency | `None` | **NEEDS_PREREGISTERED_EVIDENCE** | derive from preregistered uncertainty procedure if possible; no arbitrary K |

---

## 11. Final R2.2 result

```text
R2.2 RESULT
PREREGISTRATION_REQUIRED

Resolved numeric policy classes
NONE

Structurally reduced
U02
  3 MAD tolerance dimensions
  →
  2 normalized dimensions:
    NORMALIZED_MEDIAN_SHIFT
    RELATIVE_MAD_SHIFT

Still unresolved
U01 TAIL tolerance
U02 normalized MAD tolerances
U03 validation suffix sufficiency

Classical iid DKW directly applicable
NO

Independent two-sample DKW directly applicable
NO

Dependence-aware theory potentially usable
YES, with preregistered assumptions

Block bootstrap parameter-free
NO

Can select minimum N
NO

Can approve reference adequacy
NO

Ready for B.2 policy freeze
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

## 12. R2.2 completion checks

- U01 reviewed: PASS
- U02 reviewed: PASS
- U03 reviewed: PASS
- nested/dependent ECDF issue explicitly reviewed: PASS
- MAD metric redundancy reviewed: PASS
- measurement resolution separated from acceptance tolerance: PASS
- fixed-count/calendar suffix alternatives reviewed: PASS
- hidden bootstrap/bandwidth/confidence parameters enumerated: PASS
- Development envelope not used to choose a value: PASS
- candidate/signal/episode survival not used: PASS
- Holdout accessed: NO
- code changed: NO
- runtime artifact changed: NO
- next stage identified: R2.3 preregistration
