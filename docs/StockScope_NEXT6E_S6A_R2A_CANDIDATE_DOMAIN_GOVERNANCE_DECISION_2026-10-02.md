# StockScope NEXT-6E-S6A-R2A — Candidate-Domain Governance Decision

## 1. Status / Baseline

- Date: 2026-10-02, Asia/Seoul.
- Stage: **NEXT-6E-S6A-R2A Candidate-Domain Governance Decision**.
- Artifact type: **actual governance decision**, not a task specification.
- Research / decision base: `c2cc9ab370f0dadc602adfeb19fdd7efece79325`.
- Parent R2 state: `METHOD_DESIGNED / G-A BLOCKED`.
- Candidate-domain form inherited from R2: `FIXED_INTERIOR_FRACTION`.
- Multiplier profile inherited from R2: `CONDITIONALLY_FROZEN`.
- Development outcome use: **NONE**.
- Holdout access: **NONE**.
- Runtime/statistical execution: **NONE**.
- Production impact: **NONE**.

Final decision:

```text
NEXT-6E-S6A-R2A = COMPLETE

CandidateDomainContract
=
FROZEN

κ
=
0.10
=
1/10 exactly

κ classification
=
METHOD_DESIGN_PARAMETER

κ source
=
PROJECT_METHOD_GOVERNANCE_DECISION

κ theorem-optimal
=
NO

Candidate-domain rule
=
ceil(n/10) ≤ N ≤ n-1
plus structural eligibility rules

Out-of-domain state
=
OUTSIDE_APPROVED_METHOD_DOMAIN

MultiplierProfileContract
=
UNCHANGED / CONDITIONALLY_FROZEN

Method state
=
METHOD_PROFILE_FROZEN

G-A
=
BLOCKED_ONLY_ON_ASSUMPTION_ACCEPTANCE

Reference Adequacy
=
UNRESOLVED
```

The selected value is a prospective project method-design convention. It is not a theorem-derived optimum, external regulatory requirement, product risk threshold, Development-tuned value, or Monte Carlo parameter.

---

## 2. Frozen R2 State

R2 established:

```text
Statistical target
=
JOINT_SEQUENTIAL_FUNCTIONAL_SAMPLING_FLUCTUATION

Process
=
3D JOINT HORIZON FEATURE PROCESS

Dependence family
=
STRICTLY_STATIONARY_STRONG_MIXING

Mixing theorem class
=
α(r)=O(r^-a), a>15/2

Candidate-domain form
=
FIXED_INTERIOR_FRACTION

Candidate-domain status
=
CONDITIONALLY_FROZEN

κ
=
null / UNRESOLVED

Multiplier family
=
MOVING_AVERAGE_DEPENDENT_MULTIPLIER

Kernel
=
PARZEN

Bandwidth estimator
=
BK2016_SECTION_5_1_ADAPTIVE_IMSE

Lag cutoff
=
POLITIS_WHITE_CORRECTED_AUTOMATIC

Multivariate aggregation
=
MEDIAN

Centering
=
FULL_SAMPLE_EMPIRICAL_CENTERING
```

R2A does not reopen the theorem route, median/MAD transfer, multiplier family, kernel, bandwidth method, lag selector, grid, centering, or common-N theorem structure.

The only design question resolved here is the exact interior lower-bound fraction.

---

## 3. Decision Question

The current method requires an approved domain of the form:

```text
C_n(κ)
=
{
  N:
  ceil(κ n) ≤ N ≤ n-1
}

0 < κ < 1
```

because normalized prefix empirical distributions introduce a factor proportional to:

```text
1 / s
where
s = N / n
```

and the currently approved continuous-mapping route does not claim uniform validity through the singular boundary at `s=0`.

The theorem requirement is only:

```text
κ fixed
κ > 0
```

It does not supply a unique numeric κ.

Therefore the exact numeric value is a method-domain governance decision.

---

## 4. Scientific vs Governance Boundary

R2A freezes the following distinction:

```text
THEOREM REQUIREMENT
=
fixed κ > 0

PROJECT METHOD-DESIGN DECISION
=
κ = 0.10

DOWNSTREAM EMPIRICAL RESULT
=
not used
```

The project must never claim:

```text
κ = 0.10
because statistical theory proves 0.10 is optimal
```

or:

```text
κ = 0.10
because Development data performs best there
```

The correct statement is:

> StockScope prospectively defines the lower boundary of the approved sequential candidate domain at one tenth of the aligned record length. This convention stays inside the fixed-positive-interior theorem route while balancing boundary separation, candidate preservation, auditability, and version stability.

---

## 5. Candidate-Domain Purpose

κ defines the lower boundary of the **statistical claim domain**.

It does not define:

- `minimum_prior_observations`;
- `recommended_support`;
- Reference Adequacy;
- operational tolerance;
- risk appetite;
- bootstrap bandwidth;
- Monte Carlo precision;
- passing N;
- product performance.

The method-domain lower boundary determines where StockScope is willing to make the current simultaneous statistical claim.

---

## 6. Decision Criteria

The candidate is evaluated prospectively on:

1. theorem compatibility;
2. separation from the `s=0` normalization singularity;
3. preservation of a broad candidate fraction;
4. deterministic definition across record lengths;
5. simple auditability;
6. cross-language reproducibility;
7. stability against later outcome-driven changes;
8. compatibility with the frozen R2 method route.

No Development, Production, or Holdout outcome criterion is allowed.

---

## 7. Prospective Candidate Set

R2A fixes the comparison set before any empirical adequacy evaluation:

```text
κ ∈ {0.05, 0.10, 0.20}
```

These are simple auditable fixed fractions spanning a materially broader, middle, and materially narrower interior claim domain.

They are not claimed to be exhaustive or theorem-optimal.

For a fixed κ, the normalization factor satisfies:

```text
1/s ≤ 1/κ
```

over the approved candidate domain.

Therefore:

| κ | Exact fraction | Maximum 1/s on domain | Approx. retained fractional anchor span | Governance interpretation |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 1/20 | 20 | 95% | broad domain, close to boundary |
| 0.10 | 1/10 | 10 | 90% | middle interior convention |
| 0.20 | 1/5 | 5 | 80% | narrower domain, stronger truncation |

The retained-span percentages describe the fractional index interval, not the number of statistically adequate candidates.

---

## 8. Candidate Comparison

### 8.1 κ = 0.05

Advantages:

- preserves the broadest candidate range among the three;
- excludes only the first twentieth of the fractional index domain.

Disadvantages:

- permits normalized-prefix amplification up to 20 at the lower boundary;
- places the approved claim materially closer to the singular edge that caused the interior-domain restriction;
- creates a comparatively aggressive claim-domain extension without a theorem or product requirement specifically supporting that extra proximity.

Decision:

```text
REJECTED
```

Reason: too boundary-proximate for the first frozen project convention.

### 8.2 κ = 0.10

Advantages:

- remains a fixed positive interior fraction;
- caps the prefix normalization factor at 10 on the approved domain;
- retains approximately nine tenths of the fractional anchor interval;
- has a direct exact rational representation `1/10`;
- supports platform-independent integer eligibility using `ceil(n/10)`;
- is easy to audit and explain;
- does not require a hidden constant or data-dependent calculation.

Disadvantage:

- no theorem establishes 0.10 as uniquely optimal;
- the first tenth of the anchor fraction is deliberately outside the claim domain.

Decision:

```text
SELECTED
```

### 8.3 κ = 0.20

Advantages:

- moves farther from the singular boundary;
- caps the prefix normalization factor at 5.

Disadvantages:

- removes the first fifth of the fractional candidate domain from the current statistical claim;
- is a substantially narrower claim than required merely to remain inside a fixed-positive interior region;
- sacrifices materially more candidate coverage without an independent theorem or product requirement demanding that stronger truncation.

Decision:

```text
REJECTED
```

Reason: excessive claim-domain truncation for the initial frozen convention.

---

## 9. Selected κ

R2A selects:

```text
κ
=
0.10
=
1/10 exactly
```

Classification:

```text
METHOD_DESIGN_PARAMETER
```

Source:

```text
PROJECT_METHOD_GOVERNANCE_DECISION
```

The selection is intentionally a middle prospective convention between the compared broader and narrower domains.

It is not inferred from current adequacy behavior.

---

## 10. Why the Smaller Alternative Was Not Selected

The project does not select `κ=0.05` because the additional candidate coverage comes from moving the approved claim twice as close to the problematic boundary in fractional terms.

At its lower boundary:

```text
1/s
≤
20
```

rather than 10.

There is no independent requirement in the current method architecture that justifies taking that additional boundary exposure for the initial frozen contract.

This is a method-scope judgment, not an empirical performance judgment.

---

## 11. Why the Larger Alternative Was Not Selected

The project does not select `κ=0.20` because it removes the first fifth of the fractional anchor domain.

At its lower boundary:

```text
1/s
≤
5
```

but no theorem reviewed by R1/R2 requires that stronger separation.

The extra truncation would materially narrow the supported candidate domain without an independent project requirement demanding it.

Again, no Development outcome is involved.

---

## 12. Exact CandidateDomainContract

```text
contract_version
=
NEXT6E_S6A_R2A_CANDIDATE_DOMAIN_V1

contract_id
=
STOCKSCOPE_REFERENCE_ADEQUACY_CANDIDATE_DOMAIN_V1

domain_type
=
FIXED_INTERIOR_FRACTION

κ
=
1/10 exact

κ_decimal_display
=
0.10

κ_classification
=
METHOD_DESIGN_PARAMETER

κ_source
=
PROJECT_METHOD_GOVERNANCE_DECISION

theorem_requirement
=
κ fixed > 0

theorem_optimal_claim
=
NO

sample_size
=
n = aligned 3D joint feature-process length

fraction_domain_eligible
=
ceil(n/10) ≤ N ≤ n-1

canonical_integer_lower_bound
=
N_min_method(n) = ceil(n/10)

canonical_integer_arithmetic
=
N_min_method(n) = floor((n+9)/10)
for positive integer n

additional_eligibility
=
later state exists
AND joint horizon feature exists
AND required functional is computable
AND approved method assumptions/contracts apply

out_of_domain_state
=
OUTSIDE_APPROVED_METHOD_DOMAIN

common_N_semantics
=
smallest supported common N
within the approved method domain

full_positive_integer_minimum_claim
=
FORBIDDEN

change_control
=
new κ requires a new CandidateDomainContract version

retroactive_relabeling
=
FORBIDDEN

status
=
FROZEN
```

The integer rule is defined without floating-point multiplication.

---

## 13. Domain Eligibility Semantics

Candidate eligibility is not equivalent to the κ check alone.

The prospective structure is:

```text
ELIGIBLE(N)
=
FRACTION_DOMAIN_ELIGIBLE(N)
AND
LATER_STATE_AVAILABLE(N)
AND
JOINT_FEATURE_AVAILABLE(N)
AND
FUNCTIONAL_COMPUTABLE(N)
AND
METHOD_CONTRACT_APPLICABLE
```

The exact κ rule supplies only the first predicate.

A candidate can be inside the fraction domain and still be non-computable or structurally unavailable.

---

## 14. Out-of-Domain Semantics

If:

```text
N < ceil(n/10)
```

the required state is:

```text
OUTSIDE_APPROVED_METHOD_DOMAIN
```

It must not be mapped to:

- FAIL;
- UNSTABLE;
- INADEQUATE;
- zero support;
- policy violation.

The method makes no current adequacy claim for that anchor.

---

## 15. Common-N Semantics

The official common-N meaning becomes:

> the smallest supported common N **within the approved CandidateDomainContract V1 domain** for which all required families satisfy the final approved adequacy criteria.

Forbidden shorthand:

```text
minimum N over all positive integers
```

unless a future theorem contract explicitly expands the domain.

---

## 16. Candidate Domain vs Product Support

The method lower bound:

```text
ceil(n/10)
```

must not be exposed as:

```text
minimum_prior_observations
```

or:

```text
recommended_support
```

Those remain downstream Reference Adequacy outputs and remain:

```text
null
```

until a later authorized evaluation supports them.

---

## 17. Change Control

κ is frozen prospectively.

A future change from `1/10` requires:

1. a new CandidateDomainContract version;
2. an explicit governance rationale;
3. no reuse of current evaluation identity;
4. re-evaluation under the new domain when evaluation is authorized;
5. immutable retention of old artifacts.

Forbidden:

```text
evaluation unfavorable
→ change κ
→ relabel prior result
```

No Development or Production result may be used as an informal reason to loosen or tighten κ without a new governed method-design process.

---

## 18. Multiplier Compatibility

R2A does not alter the R2 multiplier profile.

It remains:

```text
family
=
MOVING_AVERAGE_DEPENDENT_MULTIPLIER

kernel
=
PARZEN

bandwidth
=
BK2016_SECTION_5_1_ADAPTIVE_IMSE

lag cutoff
=
POLITIS_WHITE_CORRECTED_AUTOMATIC

multivariate aggregation
=
MEDIAN

grid
=
5 per dimension / 125 for d=3

centering
=
FULL_SAMPLE_EMPIRICAL_CENTERING

manual fallback
=
FORBIDDEN
```

No source-level contradiction was identified between the fixed `κ=1/10` domain convention and the R2 multiplier profile.

R2A does not invent a rule such as:

```text
N ≥ ell
N ≥ 2 ell
N ≥ 10 ell
```

No such coupling is authorized.

---

## 19. Statistical Claim Scope After R2A

The current method claim domain is now versionable and exact:

```text
s = N/n

1/10 ≤ s < 1
```

subject to structural eligibility.

The statistical claim remains:

- asymptotic;
- conditional on the approved process/regularity assumptions;
- simultaneous over the approved indexed family;
- not a structural-regime forecast;
- not a Production-performance claim.

The domain freeze removes the κ design blocker. It does not establish the process assumptions.

---

## 20. Method-Design Authority Boundary

R2A records the decision under the role:

```text
METHOD_DESIGN_AUTHORITY
```

Decision basis:

```text
PROJECT_METHOD_GOVERNANCE_DECISION
```

This authority concerns the statistical claim domain.

It does not approve:

- `τ_T`;
- `τ_L`;
- `τ_S`;
- `α_stat`;
- `γ_repeat`;
- `δ_MC`.

Those remain separate governance/numerical ledgers.

The artifact does not claim external regulatory or scientific-consensus authority.

---

## 21. S6B Boundary

No S6B numeric policy state changes.

```text
τ_T = null
τ_L = null
τ_S = null
α_stat = null
```

The method event identity remains:

```text
SIMULTANEOUS_JOINT_FUNCTIONAL_COVERAGE
OVER_APPROVED_INTERIOR_DOMAIN
```

The phrase `APPROVED_INTERIOR_DOMAIN` now resolves to CandidateDomainContract V1 with `κ=1/10`.

`γ_repeat` remains outside the Method Contract and, if desired, must be separately redefined by Track B.

---

## 22. R3 Handoff

With κ frozen, the next Track-A blocker is actual-process assumption acceptance.

Preferred next task:

```text
NEXT-6E-S6A-R3
Assumption Acceptance Evidence Gate
```

R3 should assess, without overstating finite-data evidence:

- joint native-position completeness;
- stationarity compatibility;
- strong-mixing model-use compatibility and limitations;
- joint-law continuity / atom compatibility;
- unique median compatibility;
- positive local density compatibility;
- positive population-scale plausibility;
- MAD local regularity;
- fail-closed conditions.

R3 must distinguish:

```text
ASSUMPTION_ACCEPTED_FOR_MODEL_USE
```

from:

```text
MATHEMATICALLY_PROVEN_TRUE
```

Finite observed data cannot prove the infinite-process strong-mixing law.

---

## 23. G-A Gate Assessment

| Requirement | R2A state |
| --- | --- |
| Revised statistical target | CONDITIONALLY ACCEPTED |
| Process class | DEFINED |
| Functional theorem chain | CONDITIONALLY SUPPORTED |
| Candidate-domain form | FROZEN |
| Exact κ | FROZEN: 1/10 |
| Domain semantics | FROZEN |
| Common-N semantics | FROZEN |
| Multiplier profile | CONDITIONALLY FROZEN |
| Actual process assumptions | NOT ACCEPTED |
| Method executable for evaluation | NOT YET |
| Method approval | NOT YET |

Therefore:

```text
G-A
=
BLOCKED_ONLY_ON_ASSUMPTION_ACCEPTANCE
```

The candidate-domain design blocker is closed.

---

## 24. Method State

R2A advances the Track-A design state to:

```text
METHOD_PROFILE_FROZEN
```

Meaning:

- statistical target frozen conditionally;
- process class frozen;
- functional theorem chain frozen conditionally;
- candidate-domain contract frozen;
- multiplier profile frozen as the selected literature-guided profile;
- actual-process assumption evidence still pending.

This is not equivalent to:

```text
METHOD_APPROVED
```

until R3 closes the remaining assumption gate.

---

## 25. Decision Register

| Decision | Alternatives | Selected | Basis | Remaining dependency |
| --- | --- | --- | --- | --- |
| Domain form | full / fixed interior / weighted | fixed interior | R1/R2 theorem route | none |
| κ | 0.05 / 0.10 / 0.20 | 0.10 | prospective boundary-vs-coverage governance trade-off | none |
| κ representation | decimal float / exact rational | exact 1/10 | cross-platform reproducibility | none |
| lower-bound arithmetic | floating multiply / integer ceil | `ceil(n/10)` | deterministic exact rule | none |
| out-of-domain | FAIL / separate state | OUTSIDE_APPROVED_METHOD_DOMAIN | semantic separation | none |
| common-N scope | all positive N / approved domain | approved domain | simultaneous claim scope | none |
| multiplier profile | reopen / preserve R2 | preserve R2 | R2 complete | R3 assumptions |
| next gate | evaluation / assumptions | assumptions | G-A residual blocker | R3 |

---

## 26. Self-Check

```text
Development result inspected = NO
Development envelope inspected = NO
Passing N inspected = NO
Current adequacy distribution inspected = NO

Production outcome used = NO

Bootstrap executed = NO
Multiplier bootstrap executed = NO
Simulation executed = NO
Diagnostics executed = NO

Holdout read = NO
Holdout existence probe = NO
Holdout search = NO
Holdout metadata/hash/count/date inspection = NO

κ chosen from Development result = NO
κ claimed theorem-optimal = NO

Operational tolerance selected = NO
Risk-budget value selected = NO

PRNG selected = NO
Monte Carlo replicate count selected = NO

Actual-process assumption accepted = NO

V3 changed = NO
V4 created = NO
Evaluator implemented = NO

Backend changes = NONE
Frontend changes = NONE
DB changes = NONE
Migration = NONE
Runtime DB access = NONE
Runtime writes = 0

Production impact = NONE
```

---

## 27. Completion / Handoff

```text
NEXT-6E-S6A-R2A COMPLETE

Candidate-domain type
FIXED_INTERIOR_FRACTION

Selected κ
0.10
1/10 exact

κ classification
METHOD_DESIGN_PARAMETER

κ source
PROJECT_METHOD_GOVERNANCE_DECISION

Theorem requirement
κ fixed > 0

Claimed theorem-optimal
NO

CandidateDomainContract
FROZEN

Canonical lower bound
ceil(n/10)

Out-of-domain
OUTSIDE_APPROVED_METHOD_DOMAIN

Common-N
minimum supported common N
within approved method domain

MultiplierProfileContract
UNCHANGED / CONDITIONALLY_FROZEN

Method state
METHOD_PROFILE_FROZEN

G-A
BLOCKED_ONLY_ON_ASSUMPTION_ACCEPTANCE

Remaining Track-A blocker
actual-process assumption acceptance

Next
NEXT-6E-S6A-R3
ASSUMPTION ACCEPTANCE EVIDENCE GATE

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

No V4, evaluator, Development evaluation, Holdout, or Production task is authorized by this decision.
