# StockScope NEXT-6E Post-S5 — Design Document Task Specification

## 1. Document status and assignment

- Date: 2026-10-02 (Asia/Seoul)
- Artifact type: **DESIGN DOCUMENT TASK SPEC**
- Research baseline: **NEXT-6E-S5 / NEXT-6B-S4.2-B.1.6-R2.4**
- Research verdict: **NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY**
- Repository baseline: `020d2bf842b1e0e1d8ad33e7d20856463476c373`
- Current Reference Adequacy protocol: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`
- Implementation, evaluation, Holdout access, and Production activation authorized by this document: **NONE**

**Assignment to the next model/work owner:** Write a separate Architecture/Design Document that investigates how StockScope should resolve the statistical-method and independent operational-risk-budget blockers left by S5. Compare the required alternatives, justify proposed decisions, and identify unresolved prerequisites and their closure evidence. Do not implement the design or perform an adequacy evaluation.

This specification defines what that later design must answer. It does not select a workstream order, statistical architecture, automatic selector, simultaneous procedure, PRNG, error budget, tolerance, or compute budget. None of those choices becomes approved merely because it appears as a candidate here.

Recommended later deliverable:

```text
docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md
```

The name follows the repository's `StockScope_NEXT6..._<PURPOSE>_<DATE>.md` convention, including its existing NEXT6 architecture and dated research/task documents. It distinguishes an architecture deliverable from this task specification. If the later task occurs on another date, use its actual Asia/Seoul date and record the final path in its handoff. Do not create that design file during the present task. No new Stage ID is assigned here; the design must propose its Stage/workstream identity after comparing the alternatives.

Recommended execution settings for the later author: 6.1 Sol, High reasoning. This recommendation does not change an active session's settings.

## 2. Verified repository baseline

The following verification preceded authoring:

| Check | Observed fact | Consequence |
| --- | --- | --- |
| Remote latest `main` | GitHub commit lookup and compare confirmed `020d2bf842b1e0e1d8ad33e7d20856463476c373` | Use this SHA, rather than assuming the supplied SHA is current |
| Initial local branch / HEAD | `main` / `1088f0994c9712a7a9b64dd852d9ecb36d4447d8` | Local checkout initially predates the merged S5 review |
| Initial working tree | No tracked modifications; two pre-existing untracked task documents | Preserve both; exclude them from this change |
| Supplied baseline to latest main | Identical; zero additional commits | No post-S5 contract change found |
| Initial local HEAD to latest main | One commit: `020d2bf`, `docs: complete NEXT-6E-S5 adequacy governance review` | Adds the R2.4 method/risk-governance review only; no executable contract change |
| Authoring checkout | Fast-forwarded to verified main; `docs/next6e-post-s5-design-task-spec` created | Present task adds this document only |

The preserved untracked files are `docs/StockScope_FRESH_CLONE_BOOTSTRAP_TASK_SPEC_2026-10-02.md` and `docs/StockScope_NEXT6E_S5_REFERENCE_ADEQUACY_GOVERNANCE_TASK_SPEC_2026-10-02.md`. Their local presence is not evidence that they are merged or authoritative baseline inputs.

The initial Git remote query encountered a local TLS credential error. The connected GitHub read API established the remote SHA; a subsequent Git fetch using the available OpenSSL backend confirmed it. Repository metadata operations are distinct from StockScope runtime execution and data access.

The next author must repeat remote-main, branch/HEAD, working-tree, and baseline-delta checks in that order. If main has advanced, enumerate added commits and changed permitted source files, assess NEXT-6E contract impact, and record the actual design baseline SHA. Stop dependent design claims if source contracts conflict; do not silently replace S5 facts or use a stale local checkout. Limit delta inspection to source/document changes; never use it to discover or inspect protected artifacts.

## 3. Required source inputs and reading boundary

Read these tracked sources at the verified baseline. Cite the relevant section or symbol for factual claims and distinguish current code, research constraints, proposed design, and inference.

| Required input | Required use |
| --- | --- |
| [S5 / R2.4 result](StockScope_NEXT6B_S4_2B16_R24_METHOD_RISK_GOVERNANCE_2026-10-02.md) | §§3–4 frozen/target structure, §§7–10 method gaps, §§11–14 budget provenance, §§15–17 reproducibility/suffix/common-N, §§19–22 verdict and next-step boundary |
| [R2.3 preregistration](StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md) | §§3–8 lineage, uncertainty/budget distinction and diagnostics; §§10–23 candidate/tuning, multiplicity, normalized MAD, suffix and fail-closed constraints |
| [Reference Adequacy Protocol](../backend/app/macro/reference_adequacy_protocol.py) | V3 constants, builders, identity payload, zero-scale handling, selection and validation guardrails; read source only |
| [Validation entry gate](../backend/app/macro/validation_entry_gate.py) | `build_next6e_validation_entry_gate`, existing lane enums, governance, policy pin and unresolved input restrictions |
| [Development coverage](../backend/app/macro/development_coverage.py) | Sample/manifest identity, cutoff, read-only coverage boundary, source immutability and limitations; coverage is not adequacy |
| [Reference readiness](../backend/app/macro/reference_readiness.py) | `_readiness_state`, `_next_allowed_scope`, linkage checks and governance; readiness is not method approval |
| [Prospective reference capture](../backend/app/prospective/reference_capture.py) | Capture/storage/cutoff versions, attachment lineage and `POST_SCANNER_CAPTURE` boundary; do not execute capture |
| [Master Architecture](StockScope_MASTER_ARCHITECTURE_vNext.md) | Responsibilities, input identity, validation and explicit Production activation separation |
| [Development Roadmap](StockScope_DEVELOPMENT_ROADMAP_vNext.md) | Dependency/Stage conventions and distinctions between delivery, evidence and activation |
| [Implementation Baseline](StockScope_IMPLEMENTATION_BASELINE_vNext.md) | Frozen boundaries, identity, preregistration, validation, Stage handoff and UNKNOWN handling |

Additional source or documentation may be read only when necessary to explain a named contract gap. Record its exact path, purpose, version and permitted scope before reading; do not broaden into unrelated functionality or runtime directories. Existing source tests may clarify contract expectations but must not be executed in the design task.

Primary literature already registered by S5 is a research starting point, not automatic proof of transfer. The later author must verify original primary sources when making a new theoretical claim and provide a claim-to-source matrix with assumptions, theorem/section, target functional, applicability limits, finite-sample versus asymptotic scope, and remaining gaps. Do not treat a title, citation, abstract, or support for a scalar component as support for the whole StockScope procedure. Any newly reviewed external requirement must have a dated official source and an explicit applicability argument; preserve the bounded nature of S5's reviewed-scope conclusion.

### 3.1 Allowed structural inspection versus forbidden results

Allowed: tracked schema and builder definitions, field meanings, declared units, version constants, source-level identity/lineage rules, and immutable identifiers already recorded in approved research documents. This task does not authorize loading runtime manifests, rehashing data, connecting to DBs, or checking artifact presence to populate these fields.

Forbidden as design/tuning inputs: forward envelope values, passing N, candidate survival, signal survival, episode survival, covered years, per-horizon adequacy results, current evidence distribution, favorable candidate counts, Production outcomes, broker activity, or desired UI behavior. Do not open Development evidence payloads or run diagnostics/bootstrap/statistics during design authoring. Historical numeric facts embedded in preregistration documents remain historical context; do not use them to choose a method, budget, threshold, or boundary, and do not reproduce them as tuning evidence.

R2.3/V3 records `POLICY_ORIGIN = DEVELOPMENT_INFORMED`, Development evidence already observed, and a prohibition on claiming data blindness. The design must preserve this research history even though the new choices must precede any new evaluation and must not use observed outcomes for tuning.

### 3.2 Holdout boundary — absolute prohibition

```text
Holdout read = FORBIDDEN
Holdout existence probe = FORBIDDEN
Holdout directory search = FORBIDDEN
Holdout metadata = FORBIDDEN
Holdout hash = FORBIDDEN
Holdout sample count = FORBIDDEN
Holdout date-range inspection = FORBIDDEN
Holdout-derived input = FORBIDDEN
```

Apply these prohibitions to this specification task, the later design task, their tools, searches, validation, and handoffs. Avoid broad filesystem/data searches that could enumerate protected artifacts. Source code declaring a Holdout prohibition is readable; actual protected data or metadata is not. Future Holdout compatibility means a conceptual boundary design only. It is not permission to probe Holdout or to unlock it after Development evaluation.

## 4. Frozen S5 result to reproduce in the design

The later document must include this starting-state block without promoting any unresolved item:

```text
NEXT-6E-S5 = COMPLETE
Research lineage = NEXT-6B-S4.2-B.1.6-R2.4
Final verdict = NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY

Primary dependence method candidate = STATIONARY_BOOTSTRAP
Automatic tuning rule = UNRESOLVED
Dependence assumption = ASSUMPTION_UNRESOLVED
Assumption verified = NO
Joint multiplicity framework = CONCEPTUALLY_SUPPORTED
StockScope simultaneous procedure = UNRESOLVED

Risk-budget source = NONE
Confidence/error budget = null
TAIL tolerance = null
MAD normalized median tolerance = null
MAD relative scale tolerance = null
Suffix sufficiency = UNRESOLVED_POLICY
Reference Adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED

Ready for V4 evaluator = NO
Ready for adequacy evaluation = NO
Ready for Holdout = NO
Holdout = LOCKED / NOT ACCESSED
Production impact = NONE
```

S5 research completion is not Reference Adequacy resolution. A conditionally supported stationary-bootstrap candidate and conceptually supported multiplicity framework do not constitute a complete method. `ASSUMPTION_UNRESOLVED` is not a claim of incompatibility and never means verified/proven.

### 4.1 Source/code reconciliation that the design must address

Do not conceal differences between frozen implementation and research intent:

| Layer | Baseline fact | Required design treatment |
| --- | --- | --- |
| Executable V3 | MAD forward fields are `ABSOLUTE_MEDIAN_SHIFT`, `ABSOLUTE_MAD_SHIFT`, `RELATIVE_MAD_SHIFT`; absolute tolerances use basis points | Explicitly map these existing fields to any future proposal; no V3 rewrite |
| R2.3 / S5 target | Normalized median movement and relative MAD movement are the two intended MAD adequacy dimensions; absolute shifts are audit diagnostics | Explain a prospective, separately versioned V4 contract and compatibility boundary; do not claim these research dimensions are already implemented in V3 |
| Executable V3 suffix | `minimum_validation_suffix_transitions = null`, `UNRESOLVED_PARAMETER`; violation policy is null | Preserve literal current representation |
| R2.3 / S5 suffix intent | Arbitrary standalone K structurally eliminated; procedure-defined sufficiency still `UNRESOLVED_POLICY` | Describe future semantics without inventing a K or claiming current operational sufficiency |
| Dependence assumption | `STATIONARY_WEAK_DEPENDENCE` is the candidate's required class; S5 assessment is `ASSUMPTION_UNRESOLVED` | Separate assumption class from verification status |
| V3 policy status | `BLOCKED_UNJUSTIFIED_TOLERANCE`, three frozen blocker codes, all numeric boundary fields null | Keep V3 unchanged; model richer research blockers separately |

Preserve `EXPANDING_STRICTLY_PRIOR`, exclusion of the current observation, `BOUNDARY_ANCHORED_FORWARD_ENVELOPE`, observed-values-union TAIL support with no invented x-grid, `COMMON_N_FIRST`, and `ALL_FAMILIES_AND`. TAIL/MAD require common method/horizon N; EPT does not use expanding reference support and remains excluded. Local append and temporal perturbation remain diagnostics, not substitute gates. Weighted stability scores, automatic tolerance relaxation, and automatic method/horizon-specific N remain forbidden.

### 4.2 Existing NEXT-6E integration boundaries

The later design must locate its responsibility alongside these existing contracts, without changing them:

- S1: `VN_NEXT6E_S1_VALIDATION_ENTRY_GATE_V1`; `REFERENCE_VALIDATION_ONLY`; `ELIGIBLE`, `READY_TO_IMPLEMENT`, `BLOCKED`, `LOCKED` are existing lane states. The pure builder accepts unresolved adequacy/uncalibrated RATE_SPIKE; it does not approve effectiveness or Production.
- S2: `VN_NEXT6E_S2_DEVELOPMENT_REFERENCE_COVERAGE_V1` and `VN_NEXT6E_S2_DEVELOPMENT_DAY_END_CUTOFF_V1`; day-end source coverage, not signal-time equivalence, adequacy or effectiveness. Its source immutability/manifest linkage is a structural precedent, not permission to inspect current coverage counts.
- S3: `VN_NEXT6E_S3_PROSPECTIVE_REFERENCE_CAPTURE_V1`, `VN_NEXT6E_S3_PROSPECTIVE_REFERENCE_STORAGE_V1`, and `VN_NEXT6E_S3_CAPTURE_COMPLETED_AT_CUTOFF_V1`; `POST_SCANNER_CAPTURE`, no Scanner decision input, no proven signal-time equivalence. The existing service has an explicit attachment-write path; reading its source never authorizes running that path.
- S4: `VN_NEXT6E_S4_REFERENCE_READINESS_V1`; linkage of S1/S2/S3 and a reference-adequacy-review scope. `REFERENCE_VALIDATION_READY` and `REFERENCE_ADEQUACY_UNRESOLVED` are readiness states, not new adequacy evaluator results. Source/accumulation blockers remain meaningful and must not be overridden by design completion.

## 5. Two independent blockers and work organization

Track A — **Statistical Method Design** must define the dependence-aware uncertainty procedure for the heterogeneous joint functional, including automatic tuning, nested windows and common-N selection.

Track B — **Operational Risk-Budget Governance Design** must define why a level of reference movement is acceptable to StockScope and what independent evidence and approval would authorize it. A statistical calculation does not create that product requirement.

The design must compare all four organization options below before proposing one. This task specification selects none.

| Option | Structure to assess |
| --- | --- |
| 1 | Fully separate Statistical Method Design and Risk-Budget Governance Design Stages |
| 2 | One NEXT-6E Architecture Stage with two distinct workstreams and approvals |
| 3 | Define the risk budget first, then design the statistical procedure |
| 4 | Design the method first; resolve the operational budget through a separate governance gate |

For every option compare advantages, disadvantages, dependencies, failure propagation, implementation order, review ownership, rollback and fail-closed behavior. Explain which work can proceed without the other track and which readiness gate requires both. A method-only completion must not authorize numeric adequacy evaluation or operational use. If a preferred organization cannot yet be justified, mark the choice OPEN with closure requirements.

## 6. Required statistical target and dependence design

Describe the inferential target before selecting machinery:

```text
3 horizons: delta_bp_1obs, delta_bp_5obs, delta_bp_10obs
3 TAIL components: ECDF_SUP_DISTANCE
3 MAD location components: NORMALIZED_MEDIAN_SHIFT
3 MAD scale components: RELATIVE_MAD_SHIFT
anchor N compared with every later reference state
nested forward envelopes and repeated candidate N
minimum common N satisfying every required method/horizon component
```

The design must define the estimand, observed statistic, uncertainty statement, acceptance event, candidate-N set construction, nested-state indexing, and selection event. Specify whether uncertainty concerns the reference process, envelope, estimated bound, or another precisely identified object. Separate computability, sufficiency, uncertainty, acceptable movement, and selection. Fixed-N or marginal validity must not silently become post-selection common-N validity.

Require explicit treatment of stationarity, weak dependence, mixing/association applicability, moments/regularity, structural breaks, regime shifts, overlapping feature horizons and chronology/alignment. Explain which theorem conditions are assumed, which can be diagnostically challenged, and what remains unverified. Define diagnostic roles as `INFORMATIONAL`, `ASSUMPTION_SUPPORTING`, or `ASSUMPTION_REJECTING`; specify permitted future evidence, responsible review and rejection effects. A single p-value or a conventional unapproved threshold cannot approve or prove assumptions. Do not run diagnostics now.

Any segmentation, regime handling or alternative method must have an outcome-independent design and new preregistration where required; it cannot shorten away inconvenient evidence or serve as an evaluation-time fallback. iid defaults are forbidden.

## 7. Required resampling architecture questions

Require the design to explain this logical flow, including whether theoretical requirements justify a different construction:

```text
raw chronological observations
→ automatic block-selection
→ joint resample
→ recompute all horizons/components
→ nested forward envelope
→ candidate-N evaluation
→ common-N decision
```

For each step specify input/output contracts, deterministic identity, immutable source lineage, preconditions, failure states, and consuming responsibility. The design must answer:

1. What is the resampling unit: raw DGS10 observations, aligned derived vectors, or another justified unit? How are chronology, overlapping feature construction, warmup/missing observations and cross-horizon dependence preserved? Compare necessary choices without opening observations.
2. How are block starts/lengths, boundaries and wraparound represented? On which approved input/stage is automatic tuning performed, and how does the rule remain outcome-independent?
3. Which joint resample identity is shared across components, candidate N and forward states? Independent marginal seeds must not destroy the joint dependence being claimed.
4. How are overlapping anchor/suffix states reconstructed inside one replicate? How does every later valid state enter the envelope without unrelated window-by-window resampling?
5. How are medians, anchor MAD and later MAD jointly recomputed? Account for the stochastic denominator, ties, regularity and zero-scale failure; do not assume a risk-free denominator without a target-specific argument.
6. What normalization/studentization makes heterogeneous components comparable? Distinguish policy normalization from inferential studentization and specify failures of either.
7. Where are candidate-N/common-N selection and the envelope maximum represented in the simultaneous statement? What prevents a favorable pointwise interval from being selected after evaluation?
8. How is genuinely future suffix evidence defined, and how does the approved procedure determine sufficiency without an arbitrary standalone K?

## 8. Automatic tuning comparison

Compare at least these candidates; a recognized method name is not sufficient justification:

```text
Politis-White
Patton-Politis-White correction
influence-function selector
quantile-specific selector
custom statistic-specific rule
```

Use a matrix covering ECDF sup, normalized median, relative MAD, heterogeneous joint family, nested windows and common-N selection. For each include exact target/assumptions, primary evidence and correction/version, objective optimized, transfer argument, remaining theorem gaps, computability conditions, deterministic identity, complexity and failure behavior. Distinguish first-order variance/standard-error support from distribution, studentized, envelope or simultaneous inference support.

A custom rule needs an explicit derivation and review/closure path; familiarity, convenience or passing outcomes are not evidence. Explain whether one common selector or a justified joint aggregation of functional-specific selectors is possible and how that affects the claimed joint resampling law. Leave the final selector unresolved if complete transfer cannot be defended. Manual fixed length, conventional `sqrt(N)`, manual override, block sweeps chosen for favorable results, and outcome-driven fallback remain forbidden.

## 9. Joint multiplicity and simultaneous inference

The minimum family is nine components: 3 TAIL + 3 normalized median + 3 relative MAD. Retain `ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY` and the prohibition on independent per-component alpha.

Require an indexed family definition and a reasoned decision on whether candidate-N, nested forward-state and common-N selection dimensions enter that family explicitly or are covered by a formally justified envelope/selection construction. If a dimension is omitted, explain why the claimed error/coverage guarantee remains valid for the actual decision. No scope reduction to preserve a passing result is admissible.

Compare joint max statistic, studentized max statistic, Romano-Wolf stepdown, simultaneous confidence bands, and any other formally justified joint procedure. For each define hypotheses or coverage event, direction of the adequacy claim, centering, normalization, joint dependence representation, critical-value/bound construction, post-selection scope and limits. Explain whether false adequacy support is the controlled error and how a procedure yields that claim. A generic rejection procedure cannot be assumed to certify stability; non-rejection alone is not adequacy evidence.

Distinguish asymptotic from finite-sample guarantees and the numerical Monte Carlo approximation from the statistical error target. Formal control conditional on a chosen error level does not choose the level or operational tolerances for StockScope.

## 10. Numerical reproducibility decisions to request

The design must produce a decision/OPEN record for each of:

```text
PRNG algorithm/version
seed derivation and integer mapping
canonical serialization and hash version
domain separator
joint resample identity
substream derivation
parallel execution and scheduling independence
resample ordering
tie-breaking
Monte Carlo error allocation/measurement
stopping rule
maximum compute budget
```

Require lineage-aware identity material, a distinction between scientific and execution identities, and reproducibility across worker counts, retries and resume. Explain deterministic aggregation and dependency/numerical-platform compatibility limits. Specify which changes invalidate comparability or require a new version. No manually entered run seed or separate unrelated component streams may compromise a shared joint sample.

The later design may provide justified recommendations or leave exact choices OPEN. It must not insert customary resample counts, alpha, stopping tolerances or compute caps without evidence. Numerical accuracy parameters remain distinct from policy parameters. If stopping precision or compute budget is unresolved, the evaluation gate remains closed. Do not generate samples, benchmark or run convergence experiments in the design task.

## 11. Operational risk-budget governance requirements

Start with the product question: **Why does StockScope need to limit reference movement before using that reference for calibration?** Define the intended internal product semantics, harms from unsupported reference reuse, decision scope and evidence limitations. Treat examples such as drift undermining calibration trust as hypotheses to justify, not already approved requirements. Stable references alone do not approve calibration, effectiveness, prediction or Production.

Keep separate:

```text
Statistical uncertainty
Operational acceptable movement
Statistical confidence/error budget
Numerical Monte Carlo accuracy/compute budget
```

The design must explicitly prohibit `bootstrap CI width = operational tolerance`. It must explain how an uncertainty statement would be compared with a separately approved acceptable-movement budget, without deriving that budget from current Development envelopes.

Review the frozen source hierarchy without changing V3/R2.3 in place:

```text
1. EXISTING_PROJECT_REQUIREMENT
2. EXTERNAL_DOMAIN_REQUIREMENT
3. FORMAL_STATISTICAL_ERROR_CONTROL
4. NONE
```

For each source define approval evidence, provenance/date/version, authority/owner, applicability to the exact statistic and units, scope, review/expiry/revocation and conflict handling. Assess whether the hierarchy should be retained in a future contract; any proposed change needs a prospective governance rationale and separate approval. Formal statistical error control may justify a conditional procedure but cannot manufacture an operational movement limit. Do not invent an existing approving role or claim a project requirement absent from the baseline.

Preserve the current findings: existing project requirement `NONE`; applicable external requirement `NONE_IN_REVIEWED_SCOPE`; formal statistical control `PROCEDURE_SUPPORT_ONLY`; operational source `NONE`. A new proposal must be clearly separated from these observed facts. Define a legitimate route to approve a new project requirement, including purpose, consequences, required evidence and accountable sign-off, if no existing source applies.

Require separate policy entries for TAIL absolute probability movement, normalized median movement, relative MAD movement and family-wide confidence/error budget. Each proposed numeric entry requires value, units, source, justification, scope, status, approval evidence and version. If any basis is absent, leave the value null and report the blocked gate. No convenient confidence level, regulatory number for another object, desired support N or UI requirement may fill it.

## 12. Architecture alternatives to compare

Require at least three realistic architectures, including these candidates or clearly mapped refinements:

| Candidate | Architecture question |
| --- | --- |
| A | Single joint stationary-bootstrap evaluator recomputing the complete required functional |
| B | Functional-specific uncertainty estimation with a formally justified joint error-control layer |
| C | Reference-stability confidence region with a separate operational governance gate |

For each compare theoretical support, implementation complexity, reproducibility, joint-inference correctness, common-N compatibility, failure modes, computational cost, maintainability, auditability, conceptual future Holdout compatibility and Production isolation. Identify shared versus separate responsibilities, integration with S1–S4/V3, remaining proof/approval obligations and rollback behavior. Describe comparative compute complexity without using runtime benchmarks or evidence-size tuning.

Do not imply B's separate components are valid jointly without a coupling argument, or that C removes the need for a dependence-aware procedure. Statistical architecture comparison and the four work-organization options are separate required comparisons. A preferred proposal is permitted in the later design only with support and stated conditions; no defensible winner is an allowed conclusion.

## 13. Expected prospective data contracts

The design must assess these logical contracts without implementing classes, schema, DB tables or runtime artifacts:

| Candidate contract | Questions to define |
| --- | --- |
| `ReferenceAdequacyMethodContract` | Statistic definitions, candidate method/tuning rule, applicability, joint-family scope and execution readiness |
| `DependenceAssumptionContract` | Required assumption class, diagnostics' roles, acceptance/rejection evidence and unverified limitations |
| `JointResamplingContract` | Resampling unit/coupling, window recomputation, normalization, reproducibility and approximation failure |
| `RiskBudgetContract` | Separate operational/statistical budgets, units, independent source, authority, approval and revocation |
| `AdequacyEvaluationContract` | Approved inputs, suffix/common-N decision, result states, lineage and permitted downstream claim |

For each assess version, identity, source lineage, inputs, outputs, status, limitations and governance, including types/nullability, invalid combinations, producer/consumer ownership, immutability and validation obligations. Include protocol/preregistration/input identities, units, missing-value semantics, evidence/approval references and change invalidation where relevant. Identity definitions must not require protected data or secrets.

Provide a compatibility mapping from V3 and S1–S4 fields to proposed contracts. These names are design candidates, not existing code. Clearly label document-only sketches. Decide which absent field prevents computation versus decision versus downstream use; never fill missing values with permissive defaults. Discuss prospective storage/migration requirements only as future scope, with no implementation or writes now.

## 14. Required dependency graph and stage gates

The later design must include a directed dependency graph with justified edges, independent workstreams, approval convergence and blocked routes. Investigate and revise this illustrative graph; it is not a selected execution order:

```text
Track A: dependence assumption design
         → automatic tuning design
         → joint resampling and nested-envelope design
         → simultaneous/common-N inference design

Track B: product purpose and requirement provenance
         → operational risk-budget governance/approval

Track A + Track B + reproducibility/sufficiency contracts
         → design review and blocker disposition
         → separate future V4 preregistration
         → separately scoped evaluator implementation
         → Development-only evaluation
         → Reference Adequacy decision
```

Show statistical-error and Monte Carlo budget dependencies wherever they actually apply. Explain how method and budget design inform one another without allowing current outcomes to set tolerances. Attach entry criteria, required evidence, accountable review/approval, permitted activities, exit criteria, failure result and allowed next work to each gate. Include version invalidation/rollback edges. Reference Adequacy support must not have an automatic edge to Holdout access, RATE_SPIKE calibration or Production activation.

## 15. Required state-machine design

Review at least these proposed states:

```text
UNRESOLVED
METHOD_DESIGNED
METHOD_PREREGISTERED
EVALUATION_READY
EVALUATION_COMPLETE
REFERENCE_ADEQUACY_SUPPORTED
NO_SUPPORTED_BOUNDARY
NON_COMPUTABLE
```

Require a transition table or state diagram defining each meaning, evidence, guards, terminal/nonterminal behavior, re-entry, policy/version invalidation and downstream permissions. Consider separate method, governance, sufficiency, evaluation and readiness axes to avoid falsely collapsing distinct states. These are prospective design states, not modifications to runtime enums.

Reconcile the proposal with S1 lane enums, S4 readiness values, V3 `UNRESOLVED`/`BLOCKED_UNJUSTIFIED_TOLERANCE`, and `NON_COMPUTABLE_ZERO_SCALE`. Make clear that `METHOD_DESIGNED` does not imply approval, `METHOD_PREREGISTERED` alone does not imply `EVALUATION_READY`, and `EVALUATION_COMPLETE` includes negative/non-supported outcomes. Never silently overwrite a current readiness enum with a similarly named design state.

## 16. Required failure and fail-closed model

For every row require detection/precondition, failure granularity, proposed result/reason, null-field preservation, audit evidence, permitted next action and restart/version rule. The dispositions below are constraints; exact future status mapping must be designed.

| Failure to cover | Required consequence |
| --- | --- |
| Dependence assumption unsupported/unaccepted | Do not execute an unsupported inference or claim adequacy |
| Automatic block selector unresolved/non-computable | No manual block override or convenient iid fallback |
| Zero anchor MAD | Preserve `NON_COMPUTABLE_ZERO_SCALE`; no null-to-zero, epsilon denominator, stable/pass conversion |
| Insufficient suffix | Distinguish insufficient evidence from instability; no arbitrary K or suffix shortening |
| Joint bootstrap failure | No successful partial-family promotion or silent replicate deletion |
| Monte Carlo convergence failure/compute cap | Report unresolved numerical precision; no approximate pass without approved rule |
| Lineage/version mismatch | Reject incompatible inputs/approvals and invalidate comparability |
| Policy/error budget unresolved or revoked | Keep the relevant decision gate closed even if uncertainty is computable |
| No common N under complete approved evaluable policy | `NO_SUPPORTED_BOUNDARY`; do not relax policy to obtain N |

Design how ties, missing/alignment errors, degenerate studentizers, invalid resamples, partial runs and cancellation interact with the above. Differentiate candidate-level non-computability from whole-procedure failure and an evaluable no-match outcome. Preserve `reference_adequacy = UNRESOLVED`, null minimum/recommended support and `RATE_SPIKE = UNCALIBRATED` when prerequisites fail; specify how a future no-match result represents unsupported support without claiming instability from missing computation.

Forbidden recovery: tolerance relaxation, horizon removal, method shopping, manually changed block length, scope shrinkage, method/horizon-specific N, zero-scale rescue or favorable rerun selection. A legitimate scientific change needs a separately reviewed/versioned preregistration before its corresponding evaluation; logging a post-outcome change does not make it outcome-independent. Rollback revokes prospective readiness and preserves immutable prior records; it never enables Production or edits historical evidence to appear successful.

## 17. Decisions, OPEN items and evidence requirements

Require a decision register with ID, question, `DECIDED`/`OPEN`/blocked status, alternatives, rationale, primary/project sources, assumptions, authority/approval status, affected contract/gate, closure evidence owner and next action. Label recommendations as proposals until their approval evidence exists. Do not equate design-author preference with product risk approval.

Fixed constraints to carry forward include Holdout inaccessibility, frozen V3, no iid default, no manual/outcome-driven tuning, no Development-result policy selection and Production isolation. The later design must decide or explicitly leave OPEN the track organization, statistical architecture, exact automatic selector, simultaneous/selection procedure, assumption diagnostics, risk/error budgets, PRNG and numerical compute/stopping policy.

An unresolved decision is acceptable when the document describes its precise gap, consequence, required evidence, responsible role to confirm, resolution stage and permitted work in the meantime. Numbers without independent justification remain null. A fully reviewed design with unresolved blockers may be **DESIGN_DOCUMENT_COMPLETE / IMPLEMENTATION_BLOCKED**; it is not an executable or approved numeric adequacy policy.

## 18. V3 → future V4 → evaluator → evaluation boundary

Require an explicit authorization matrix:

| Phase | Permitted output | Prohibited promotion |
| --- | --- | --- |
| Present task | This task specification only | Actual design or implementation |
| Next design task | Separate architecture/design document, proposals and blocker register | V3 edit, V4 creation, evaluator, runtime/data inspection, numerical evaluation |
| Later design approval | Evidence of accepted design decisions and unresolved gates | Implicit approval of missing numeric policy |
| Separate future V4 preregistration task | Only after required decisions/approvals exist: separately versioned protocol/preregistration and exact execution contracts | Outcome-informed defaults, modification of frozen V3 or immediate evaluation |
| Separately scoped evaluator implementation | Implementation of approved, frozen contracts with isolated contract verification | User-runtime execution or adequacy approval from tests alone |
| Separate Development-only evaluation | Only when all method, policy, lineage, numerical and scope gates pass | Holdout unlock, RATE_SPIKE calibration, effectiveness or Production approval |

Future protocol identifier, usable only in a separately authorized task after design approval:

```text
VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V4
```

The design must specify V4 preregistration entry criteria, exact fields to freeze, review/approval evidence and version-change rules. It must not construct or activate V4 now. Incomplete assumptions, tuning, joint procedure, policy budgets or numerical rules keep subsequent gates blocked.

## 19. Validation boundaries and prospective verification plan

Current specification and later design authoring use document/source self-review only: source traceability, internal consistency, complete question coverage, version/enum reconciliation, inaccessible-data constraints and file-scope checks. No runtime startup, app import, evaluator, bootstrap, diagnostics, statistics, DB access, migration or local application test execution is permitted. A documentation-only change does not require new implementation-mirroring tests.

The design must describe, without executing, future verification obligations: serial-dependence and cross-horizon preservation, nested-window/common-N inference scope, selector applicability, normalization/zero-scale behavior, deterministic replay across scheduling, convergence failure, immutable lineage/revocation and absence of Production side effects. Identify which obligations need a theoretical argument, future isolated synthetic fixture, governance approval, or separately approved Development evaluation. Do not claim tests alone establish statistical validity, empirical diagnostics prove assumptions, or a simulation supplies an operational budget.

Existing repository CI may be observed for the documentation PR. Its hosted disposable test/build environment is distinct from user runtime; do not invoke local setup/startup or change workflows. Record actual CI checks and results. Passing CI confirms repository checks, not Reference Adequacy, theoretical validity or governance approval.

## 20. Scope exclusions and Production isolation

Frontend, UI, Dashboard and user-facing expressions are outside this design task. Reference Adequacy is internal validation architecture; user-facing work requires a separate later Stage after usable adequacy status exists.

No impact or change is authorized to:

```text
Scanner scoring
Strategy Engine
Strategy Governance
Production Selection
Risk Gate
Holdings Decision
Holdings Plan
Recovery
Watch
Execution Policy
Prediction
NO_TRADE semantics
```

No Backend/Frontend code, DB schema/data, migration, runtime artifact or protocol V3 changes. Do not generate evidence, inspect live coverage/readiness/capture outputs, change the Production baseline, or imply an adequacy proposal is an input to operational decisions. External scholarly/governance source reads and repository metadata access are distinguishable from evaluator network access; future local evaluation must preserve its preregistered no-network/no-DB-write scope.

## 21. Mandatory structure of the later design document

The next author must deliver substantive content under this minimum outline; headings may be renamed while retaining every requirement:

1. Status, purpose, actual baseline SHA, delta review and source/access ledger.
2. S5/R2.4 verdict and exact frozen starting state; no readiness promotion.
3. Current architecture/contract inventory and V3 versus research reconciliation.
4. Statistical uncertainty versus operational acceptable movement; product purpose.
5. Track A/Track B responsibilities and comparison of all four organization options.
6. At least three architecture alternatives and full comparison matrix.
7. Statistical estimand, component family, nested envelopes and common-N selection.
8. Dependence assumptions, regularity, breaks/regimes and diagnostic roles.
9. Automatic tuning candidates, evidence/transfer matrix and unresolved gaps.
10. Resampling unit, joint identity, horizon recomputation and nested-window architecture.
11. Joint multiplicity, normalization/studentization and selection-valid inference.
12. Independent risk-budget provenance, policy entries and approval/revocation governance.
13. Numerical reproducibility, Monte Carlo precision/stopping and compute limits.
14. Prospective data contracts, ownership, versioning, identity and compatibility.
15. Dependency graph and separate design/V4/implementation/evaluation gates.
16. State machine, guards and reconciliation with existing runtime enums.
17. Failure model, non-computability, no-boundary behavior and rollback.
18. Validation/evidence plan, prohibited Development inputs and Holdout/Production boundaries.
19. Decisions/OPEN register, implementation-blocking conditions and limitations.
20. Design completion criteria, approval/readiness verdict and downstream handoff.
21. Primary/project source register and requirement-to-section traceability matrix.

Use sufficient equations, tables and diagrams to make the proposed semantics reviewable, but do not write executable evaluator code or present invented output. Rejected alternatives and known theoretical gaps must remain visible.

## 22. Acceptance criteria for the actual design document

The later design is document-complete only when reviewers can verify all of the following:

- Actual latest-main baseline and relevant delta are recorded; every present-state claim is grounded in the approved source inventory.
- S5 `NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY`, all null/unresolved values and no-readiness verdicts are visible and unchanged as baseline facts.
- V3 code/research differences, S1–S4 boundaries and existing enums are accurately mapped; no claim that research intent is already implemented.
- Statistical-method and operational-risk-budget blockers remain distinct, with all four organization options assessed and dependencies/failure/rollback explained.
- At least three realistic architectures are compared across every criterion in §12; proposal conditions or reasons for no selection are explicit.
- The exact nine-component target, temporal dependence, nested windows, candidate-N selection and common-N simultaneous-inference scope are addressed without marginal-to-joint shortcuts.
- Every required tuning, diagnostic, uncertainty and numerical decision has a justified recommendation or a precise OPEN record and blocked-gate consequence.
- Product semantics, independent policy provenance and approval evidence precede any proposed operational tolerance; CI width and conventional alpha do not manufacture budgets.
- Prospective contracts, dependency graph, state machine and every required fail-closed case are sufficiently specified for later review, including non-computability versus no-supported-boundary distinctions.
- V3 remains frozen; V4 preregistration, implementation and Development evaluation have separate explicit gates. Design completion does not declare evaluation readiness when blockers remain.
- Development-result tuning, all Holdout access/probes and Production/UI scope expansion are prohibited; the access/self-review report confirms the boundary.
- Mandatory outline and a requirement-to-section/decision matrix are complete; unresolved work has concrete closure evidence and ownership to confirm.
- The handoff in §23 identifies exactly what later work is permitted or blocked. No implementation, runtime writes, statistical execution or actual adequacy decision occurred during design authoring.

Positive statistical or numeric resolution is not required for document completion. An honest supported negative/OPEN conclusion with a reviewable closure plan satisfies the writing task; it leaves implementation/evaluation gates closed.

## 23. Required handoff after the later design

Require a concise handoff containing the design path/version/commit, verified source-main SHA, PR/merge/CI evidence if applicable, frozen S5 verdict, chosen or OPEN work organization, proposed architecture/selection rationale, decision and blocker IDs, and exact permitted next task.

Before any subsequent implementation request can be issued, the handoff must supply or explicitly mark missing:

1. Accepted dependence/regularity assumptions and evidence/diagnostic governance.
2. A fully specified automatic selector and complete joint/nested/common-N inference construction with applicability support.
3. Independently approved operational budgets and a separately justified family-wide error budget with scope/provenance.
4. Frozen PRNG/identity/substream/order, numerical precision/stopping/compute contracts and failure behavior.
5. Compatibility mapping and separately approved V4 preregistration entry/exit evidence; existing V3 remains immutable.
6. Future implementation scope, isolated verification obligations, artifact ownership/version rules and no-runtime/no-Production side effects.
7. A separately scoped Development-only evaluation entry gate and immutable input lineage; outcome-driven adjustment remains forbidden.

The implementation owner must receive these as concrete contracts or blocked prerequisites, not as permission to fill defaults. Future evaluation outcomes cannot retroactively complete missing design/governance approvals. Holdout and Production remain independently inaccessible/unapproved even after a supported Development adequacy result.

Required handoff distinctions:

```text
Design document complete? = factual document-review result
Design approved? = explicit approval evidence or pending
Method executable? = prerequisite-based result
Numeric policy justified? = independent evidence-based result
V4 preregistration allowed? = explicit gate result
Evaluator implementation allowed? = explicit separate task/gate result
Development evaluation allowed? = explicit separate task/gate result
Reference Adequacy resolved by design authoring? = NO
Holdout accessed? = NO
Production impact? = NONE
```

## 24. Present task completion and Git delivery

The present authorized repository change is exactly:

```text
ADD docs/StockScope_NEXT6E_POST_S5_DESIGN_DOCUMENT_TASK_SPEC_2026-10-02.md
```

Preserve unrelated local files. Complete document creation, self-review, a one-file PR against verified main, observation of existing CI, squash merge and verification of the merge/new-main SHA. If main changes before merge, reassess the source delta and update this specification only if its factual baseline/requirements need revision. Do not bypass failed checks or report an unverified merge. Do not change workflows, code, runtime, V3 or data to make this documentation change pass.

Self-review must confirm source/verdict fidelity, every requirement in §§3–23, exact one-file addition, Markdown/link consistency, absence of selected numeric defaults and no actual design/implementation. Git/repository metadata writes are not StockScope runtime writes. Report hosted CI separately from local runtime activity.

Authoring self-review: required source paths and version constants checked against the verified main; R2.4 verdict and frozen values preserved; V3/research differences explicitly recorded; all four organization options and at least three architectures requested; joint/nested/common-N, governance, reproducibility, contracts, dependencies, states and failures covered; separate design/V4/evaluator/evaluation gates retained. Relative source links resolve and fenced blocks are balanced. No statistical method, numeric policy or actual architecture was selected. No local application, statistical computation, DB access, migration, capture or evaluator was executed; local runtime writes were zero, Holdout was not accessed, and Production impact was NONE. PR/CI/merge outcomes belong to the delivery report and are not assumed in this pre-merge document.

The completion report must identify this outcome as **POST-S5 DESIGN TASK SPEC COMPLETE**, name this document, state its purpose (require a separate Architecture/Design Document before any V4/evaluator implementation), include NEXT-6E-S5 / R2.4 and `NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY`, and report one document only, no Backend/Frontend changes, zero local runtime writes, no Holdout access, no Production impact, PR, merge SHA and verified new main.

Completion of this task means **the specification for writing the next design document is complete**. It does not mean the architecture has been selected, the Reference Adequacy design has been completed, or numeric policy/evaluator/evaluation is ready.
