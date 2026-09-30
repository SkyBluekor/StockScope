# NEXT-6B-S4.2-B.1.6-R2 — Remaining Reference Adequacy Blocker Resolution Review

## 1. Purpose

This review reduces the remaining reference-adequacy design freedom before any B.1.7 evidence generation or B.2 eligibility policy freeze.

This is a **Development-informed review only**. It does not select a minimum prior-support boundary, does not approve RATE_SPIKE, and does not access Holdout.

Review baseline:

- GitHub `main`: `68b1f9e6eb1b33b32e3864f3553667d3bd75b64d`
- Reference Adequacy contract: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V2`
- Current unresolved blocker count: 11
- TAIL local append: `DIAGNOSTIC_ONLY`
- `minimum_prior_observations = null`
- `recommended_support = null`
- `ready_for_b17 = false`
- `ready_for_b2 = false`
- `ready_for_holdout = false`
- Holdout: locked / unread
- RATE_SPIKE: `UNCALIBRATED`
- Production impact: `NONE`

The B.1.5 evidence already showed why a single append transition cannot establish reference adequacy:

- TAIL append ECDF drift has a mechanical sample-size effect under an expanding reference.
- MAD can remain unchanged for many transitions and then change again much later.
- 5obs MAD changed at 1935→1936 and 1936→1937.
- 10obs MAD changed at 1979→1980 and 1980→1981.
- A boundary immediately after the last observed change would be a post-hoc choice.

Therefore R2 does **not** search for a favorable N, tolerance, interval, segment length, or violation budget.

---

## 2. Review principle

The current V2 protocol contains several parameters that exist only because the validation design was expressed as separate local, cumulative, and perturbation tests.

R2 applies one rule first:

> Before selecting a number, determine whether that number is actually necessary for the operational claim.

A reference-support boundary is intended to mean:

> At support N, the strictly-prior reference is sufficiently formed that its subsequent Development reference evolution remains within an independently justified tolerance for a sufficiently long validation suffix.

This definition suggests a simpler validation structure than fixed-`K` cumulative comparisons plus arbitrary contiguous-segment perturbations.

---

## 3. Proposed structural replacement: boundary-anchored forward envelope

For a candidate support boundary `N`, define the reference state at N as the anchor.

For every later strictly-prior reference state `t > N` inside the Development validation suffix, compare the later state directly with the anchor.

### TAIL

For feature/horizon `h`:

```text
D_tail(N, t) = sup_x |F_h,N(x) - F_h,t(x)|
```

Evaluation support remains the union of actually observed values. No synthetic x-grid is introduced.

The raw evidence must preserve the entire ordered path:

```text
N -> N+1
N -> N+2
...
N -> final eligible Development reference state
```

The adequacy statistic, if later approved, is the envelope:

```text
TAIL_ENVELOPE(N) = max_t D_tail(N, t)
```

### MAD

For the same candidate N and every later reference state t:

```text
ABS_MEDIAN_SHIFT(N,t) = |median_t - median_N|
ABS_MAD_SHIFT(N,t)    = |MAD_t - MAD_N|
REL_MAD_SHIFT(N,t)    = |MAD_t - MAD_N| / MAD_N
```

If anchor MAD is zero, relative MAD shift remains non-computable. It must not be converted to zero.

The raw evidence must preserve every later comparison. Future acceptance, if approved, uses the per-metric maximum envelope and logical AND across required MAD metrics.

### Why this structure

This directly tests the property needed from a support boundary:

> Once N is declared sufficient, how far does the reference move afterwards?

It removes the need to choose a special cumulative lag `K`.

It also contains the immediate `N -> N+1` comparison, so a separate local-transition tolerance is not needed as an adequacy gate.

---

## 4. Temporal perturbation scope decision

The current V2 protocol treats time-order-preserving contiguous segment perturbation as a possible adequacy gate, which creates two more free parameters:

- segment length
- perturbation tolerance

R2 concludes that this test addresses a **different question**:

> How sensitive would the reference be if real historical observations from a contiguous period were counterfactually removed?

That is a useful robustness diagnostic, but it is not the same as asking whether the **actual expanding reference used by the model** has reached sufficient support.

There is no current Production operation that removes an arbitrary contiguous historical segment from the reference. Without an independently defined corruption/missing-history failure model, choosing a deletion length creates a new research degree of freedom without a direct operational meaning.

Therefore temporal perturbation should be retained, if desired, only as:

```text
role = OPTIONAL_DIAGNOSTIC_ONLY
adequacy_gate = false
segment_length_required = false
tolerance_required = false
```

It must not select N and must not block B.1.7 evidence generation.

---

## 5. Violation policy decision

V2 currently asks whether validation should use:

```text
ZERO_VIOLATIONS
or
BOUNDED_VIOLATIONS
```

R2 removes this separate policy degree of freedom.

The proposed acceptance form is an **envelope / maximum-norm criterion**:

```text
max deviation over the validation suffix <= approved tolerance
```

Under this definition there is no separate "allowed number of violations" parameter.

An exceedance simply contributes to the maximum. If the maximum exceeds the tolerance, that candidate N does not satisfy the criterion.

This is **not** the same as choosing `ZERO_VIOLATIONS` merely because fail-closed sounds conservative. It is a structural consequence of defining adequacy through the maximum observed forward deviation.

Exceedance counts may still be stored as descriptive audit data, but they do not become a second selection knob.

---

## 6. Blocker-by-blocker decision matrix

| ID | Current blocker | R2 status | Decision |
|---|---|---|---|
| B02 | `TAIL_CUMULATIVE_INTERVAL_UNRESOLVED` | **CONSOLIDATED** | Remove fixed `N-K -> N` interval. Use the common boundary-anchored forward envelope over every later reference state. No `K` parameter. |
| B03 | `TAIL_CUMULATIVE_TOLERANCE_UNJUSTIFIED` | **UNJUSTIFIED** | A probability-distance tolerance is still required for a TAIL adequacy gate. Current Development outcomes cannot choose it without post-hoc tuning. |
| B04 | `TAIL_PERTURBATION_SEGMENT_LENGTH_UNRESOLVED` | **STRUCTURALLY_RESOLVED** | Temporal segment deletion is not a required adequacy gate. Keep only optional diagnostic semantics; no segment length is required. |
| B05 | `TAIL_PERTURBATION_TOLERANCE_UNJUSTIFIED` | **STRUCTURALLY_RESOLVED** | No perturbation gate means no perturbation tolerance is required. |
| B06 | `MAD_LOCAL_TOLERANCES_UNJUSTIFIED` | **STRUCTURALLY_RESOLVED** | Local MAD transition metrics remain descriptive. The anchored forward envelope already contains `N -> N+1`, so local tolerances are not a separate gate. |
| B07 | `MAD_CUMULATIVE_INTERVAL_UNRESOLVED` | **CONSOLIDATED** | Same common boundary-anchored forward envelope as TAIL. No separate MAD `K`. |
| B08 | `MAD_CUMULATIVE_TOLERANCES_UNJUSTIFIED` | **UNJUSTIFIED** | MAD location/scale tolerances remain unresolved. Current Development values must not choose them. |
| B09 | `MAD_PERTURBATION_SEGMENT_LENGTH_UNRESOLVED` | **STRUCTURALLY_RESOLVED** | Same temporal-perturbation demotion as TAIL. No required segment length. |
| B10 | `MAD_PERTURBATION_TOLERANCES_UNJUSTIFIED` | **STRUCTURALLY_RESOLVED** | No perturbation gate means no perturbation tolerance is required. |
| B11 | `VALIDATION_SUFFIX_LENGTH_UNRESOLVED` | **NEW_EVIDENCE_REQUIRED** | A boundary near the Development end must not pass on a tiny suffix. The required suffix size remains unresolved; no conventional 30/50/100 or arbitrary calendar window is selected. |
| B12 | `VIOLATION_POLICY_UNRESOLVED` | **STRUCTURALLY_RESOLVED** | Remove the separate violation-policy parameter. Use a maximum-envelope criterion; exceedance count is diagnostic only. |

---

## 7. Independent unresolved policy quantities after R2

If the R2 structure is accepted, the eleven V2 blockers reduce to three unresolved blocker classes:

### R2-U01 — TAIL forward-envelope tolerance

```text
TAIL_ENVELOPE_TOLERANCE = null
unit = ABSOLUTE_PROBABILITY_DIFFERENCE
```

The tolerance cannot be inferred from:

- candidate survival
- signal survival
- episode survival
- covered years
- a visually convenient point on the Development curve
- `1/N` probability resolution
- iid/exchangeability bounds whose assumptions are not established by the current protocol

### R2-U02 — MAD forward-envelope tolerances

```text
ABS_MEDIAN_SHIFT_TOLERANCE = null
ABS_MAD_SHIFT_TOLERANCE = null
REL_MAD_SHIFT_TOLERANCE = null
```

The current evidence can measure these quantities but does not establish how much location or scale movement is research-acceptable.

The three metrics must not be collapsed into a weighted score.

### R2-U03 — Validation suffix sufficiency

```text
MINIMUM_VALIDATION_SUFFIX_TRANSITIONS = null
```

The future evidence artifact must expose exact suffix transition counts for every candidate N, but the observed counts must not themselves be used to choose a convenient minimum.

---

## 8. Evidence-generation protocol can now be frozen

**YES — a parameter-free raw evidence-generation protocol can be frozen before any new Development replay.**

The next evidence generator should calculate measurements only. It must not apply acceptance thresholds.

### Proposed next evidence artifact

Suggested contract family:

```text
VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_EVIDENCE_V1
```

Suggested immutable artifact:

```text
REFERENCE-ADEQUACY-EVIDENCE-<hash>.json
```

### Required inputs

- DEV
- PROTOCOL
- RESEARCH
- ELIGIBILITY-RECONSTRUCTION
- REFERENCE-STABILITY
- current Reference Adequacy Protocol lineage

No Holdout input option.

### Required candidate support universe

Use the existing common review-point universe derived from the six TAIL/MAD families.

Do not introduce:

- 20/30/50/100 grids
- visually selected N values
- candidate-preservation points
- method-specific support exceptions
- horizon-specific support exceptions

### Required TAIL evidence per candidate N / horizon

Store:

- anchor prior count N
- every later comparable reference count t
- exact ECDF sup distance between anchor reference and later reference
- observed-support-only calculation
- ordered comparison list
- maximum distance
- argmax reference count
- suffix transition count
- hashes for anchor and later reference states

### Required MAD evidence per candidate N / horizon

Store:

- anchor median / MAD
- every later median / MAD
- absolute median shift from anchor
- absolute MAD shift from anchor
- relative MAD shift from anchor when computable
- explicit zero-scale non-computable state
- ordered comparison list
- maximum per metric
- argmax per metric
- suffix transition count

### Required diagnostics retained but excluded from gating

- existing TAIL local append drift
- existing MAD local transition changes
- optional temporal perturbation, only if implemented without affecting readiness or N

### Required policy state

The evidence artifact must still report:

```text
reference_adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
selection_status = NOT_SELECTED
eligibility_policy_status = UNDEFINED
admissibility_policy_status = UNDEFINED
final_candidate_status = NOT_SELECTED
ready_for_b2 = false
ready_for_holdout = false
RATE_SPIKE = UNCALIBRATED
Holdout locked = true
Holdout accessed = false
network_requests = 0
macro_db_writes = 0
production_impact = NONE
```

The artifact may mark **evidence generation complete**, but it must not mark reference adequacy approved.

---

## 9. Anti-overfitting rules for R2.1

The following remain hard constraints:

1. Do not open Holdout.
2. Do not choose N during evidence generation.
3. Do not choose TAIL/MAD tolerances from the resulting envelope curves.
4. Do not choose a suffix length because it preserves more candidates.
5. Do not use candidate/signal/episode/covered-year survival as a criterion input.
6. Do not relax a rule because a method or horizon fails.
7. Do not create method-specific or horizon-specific N automatically.
8. Preserve every evaluated common support N and every forward comparison.
9. If a future approved criterion has no passing boundary, return `NO_SUPPORTED_BOUNDARY`.
10. Any later contract revision must create a new immutable identity/version.

---

## 10. One-click local recovery requirement

R2 itself creates only this review document.

If R2.1 adds a new runtime artifact such as:

```text
REFERENCE-ADEQUACY-EVIDENCE-<hash>.json
```

the same implementation PR must also update the one-click local recovery path:

```text
.\sync_local.ps1
```

The local sync must detect/restore/validate the new derived artifact in dependency order without accessing Holdout and without overwriting immutable artifacts.

This is part of the implementation completion criteria, not a later cleanup task.

---

## 11. R2 final result

```text
R2 RESULT
PARTIAL_STRUCTURAL_REDUCTION

Original unresolved blockers        11

Consolidated
B02 + B07
→ COMMON BOUNDARY-ANCHORED FORWARD ENVELOPE

Structurally resolved
B04
B05
B06
B09
B10
B12

Still unresolved
B03  TAIL envelope tolerance
B08  MAD envelope tolerances
B11  validation suffix sufficiency

Independent unresolved classes      3

Can freeze raw evidence-generation protocol?  YES
Can select minimum N?                         NO
Can approve reference adequacy?               NO
Ready for B.1.7 evidence generation?          YES, after R2.1 contract implementation
Ready for B.2 policy freeze?                  NO
Ready for Holdout?                            NO

minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED
Holdout = locked / unread
Production = NONE
```

---

## 12. Next implementation task

If this review is accepted, the next implementation task is:

```text
NEXT-6B-S4.2-B.1.6-R2.1
Boundary-Anchored Reference Adequacy Evidence

Model: GPT-6.0 Sol
Reasoning: Medium
```

R2.1 should:

1. add a versioned boundary-anchored evidence contract,
2. generate the full TAIL/MAD forward paths for every common support N,
3. preserve local metrics as diagnostic-only,
4. keep perturbation outside the adequacy gate,
5. keep all three unresolved policy classes null,
6. create a new immutable evidence artifact,
7. update `sync_local.ps1` in the same PR,
8. add tests proving Holdout/network/Production remain untouched.

No tolerance, suffix length, or minimum N is to be selected in R2.1.
