# NEXT-6B-S4.2-B.1.6-R2.4.2 — Reference Adequacy Path Disposition & Prospective Independence-Recovery Design

Date: 2026-10-01 (Asia/Seoul). Research / Architecture / Governance Decision Review ONLY.

## 1. Decision and authority

**PRIMARY_PATH = C. SECONDARY_LONG_TERM_PATH = B.**

StockScope should specify Reference Adequacy as a descriptive / diagnostic governance layer. Numeric minimum-N approval remains unavailable. A future, explicitly new policy may be evaluated through prospective independence recovery, but that is a conditional long-term option, not a prerequisite for useful descriptions and not an approved experiment today.

The decision follows the distinction already frozen in R2.4.1: finite-path description is available; population inference is not closed; future prediction is not defined. It also follows NEXT-6's separation of reference Context from strategy, Risk Gate and operating-policy activation. C makes the supported claim useful without pretending to solve the unsupported claim. B preserves a route to stronger claims if there is a concrete product requirement, accountable policy authority and eligible new evidence.

This document selects a project direction and the next specification task. It does not change Protocol V3, enums, validators, runtime artifacts, UI, detector behavior or Production. The blocked numeric boundary remains a constraint on C; it is not a second primary path. B has not been scheduled or authorized for execution by this review.

## 2. Verified baseline and evidence boundary

GitHub `refs/heads/main` was checked using `git ls-remote` at the start of substantive review and again immediately before creating the documentation branch. Both returned:

```text
05759197b114c34d905c13976291b8a8c7477dc9
```

This equals the requested expected main and the initial local HEAD. The working tree was clean. The initial Windows Schannel transport attempt failed; an invocation-scoped OpenSSL transport retry verified the remote successfully. No Git configuration was changed. No main divergence required premise reconciliation.

Repository findings below are from actual tracked-file reads at that baseline. Historical architecture documents are design evidence; their older implementation inventories are not assumed current where code provides a more precise answer.

| Frozen input | State carried forward |
|---|---|
| U1 | PARTIAL_THEORY_ONLY |
| U2 | NO_JUSTIFIED_BUDGET_SOURCE |
| Combined | NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY |
| JOINT_INFERENCE_PROOF_CLOSED | false |
| INDEPENDENT_BUDGET_PROVENANCE_CLOSED | false |
| EXECUTION_PREREGISTRATION_READY | false |
| R2.5_ALLOWED | false |
| minimum_prior_observations | null |
| recommended_support | null |
| reference_adequacy | UNRESOLVED |
| RATE_SPIKE calibration | UNCALIBRATED |
| B.2 ready / Holdout ready | false / false |
| Holdout accessed | false |
| Production impact | NONE |
| Evidence | REFERENCE-ADEQUACY-EVIDENCE-46e5a9c059f72187.json.gz |
| Common support points / reference families / forward comparisons | 1,488 / 6 / 8,716,632 |

The artifact identity and counts are inherited committed research facts, verified against R2.3/R2.4/R2.4.1. They were not recomputed and do not certify an uninspected runtime copy. Six stored reference families are not nine future inferential components, and millions of comparisons are not millions of independent observations.

No R2.1 envelope was loaded, decoded or reevaluated. No candidate, signal or episode survival result was used for this decision. No Holdout file was searched, read, hashed or existence-checked. Reading source declarations of locked-state contracts is not an inspection of Holdout data or its hash value. No application, data collector, database query or research runner was executed.

## 3. Repository evidence register

Links identify the files read; function names and document sections locate the relevant evidence.

| ID | Repository source | Finding and implication |
|---|---|---|
| R1 | [R2.4 review](StockScope_NEXT6B_S4_2B16_R24_DEPENDENCE_RISK_GOVERNANCE_REVIEW_2026-10-01.md), sections 3–4, 13–19 | No complete joint procedure or qualifying independent budgets; refetching/re-encoding does not reset exposure; score movement and inference uncertainty are different objects. |
| R2 | [R2.4.1 closure](StockScope_NEXT6B_S4_2B16_R241_JOINT_INFERENCE_BUDGET_CLOSURE_2026-10-01.md), sections 4–5, 18–21, 24–34 | Frozen U1/U2; descriptive/population/predictive distinction; selectable-N and prospective-policy gaps; explicit request for this disposition. |
| R3 | [R2.3 preregistration](StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md), sections 1–4, 16–23, 25–28 | All-component joint scope; no arbitrary suffix K, conventional budget or outcome-driven fallback; future normalized MAD design does not mean implementation. |
| R4 | [reference_adequacy_protocol.py](../backend/app/macro/reference_adequacy_protocol.py), constants, `_tail_contract`, `_mad_contract`, `_selection_rule`, builder and validator | V3 expanding strictly-prior / common-N / all-family AND contract; null tolerances and selected support; diagnostic roles already exist; B.2 readiness false. |
| R5 | [reference_adequacy_evidence.py](../backend/app/macro/reference_adequacy_evidence.py), `_tail_family_evidence`, `_mad_family_evidence`, decoders and policy validation | Anchor-to-every-later-state paths, per-metric maxima, actual suffix counts, exact TAIL numerators, nullable MAD paths; zero-scale explicit; no selected policy. |
| R6 | [reference_stability.py](../backend/app/macro/reference_stability.py), `_observed_summary`, reference-state builders, `_common_review_points` | DESCRIPTIVE_ONLY and OBSERVED_REFERENCE_STATE already exist; strictly-prior prefix identity and movement history; common review points inherit B.1 overlays. |
| R7 | [calibration_candidate.py](../backend/app/macro/calibration_candidate.py), feature/method constants, `_threshold_values`, `_threshold_definition` | Three observed-feature horizons; Development-derived candidate thresholds; computability conditions are not inferential adequacy. Raw positive-tail method's expanding-reference exemption does not approve that method or allow a shortcut. |
| R8 | [calibration_research.py](../backend/app/macro/calibration_research.py), `validate_development_artifact`, `validate_research_protocol` | DEVELOPMENT-only ordered unique rows, hash/version validation, REFERENCE_RESEARCH_ONLY, no Production approval; existing contract cannot simply be relabeled prospective evaluation. |
| R9 | [features.py](../backend/app/macro/features.py), `MacroFeatureStatus`, `build_dgs10_features` | Yield percentage differences converted to bp; existing 1/5/10 observation horizons; observation distance differs from calendar distance; explicit missing/history states. These existing numbers are not new choices. |
| R10 | [R2 blocker review](StockScope_NEXT6B_S4_2B16_R2_BLOCKER_REVIEW_2026-09-30.md), opening and readiness verdict | B.2 in this workstream means eligibility policy freeze, downstream of unresolved reference adequacy. It is not the separately named historical exit-policy B.2 work. |
| R11 | [NEXT-6 architecture](StockScope_NEXT6_MACRO_EVENT_ARCHITECTURE_DESIGN_2026-09-29.md), sections 2, 7–8, 11, 13–18 | Context/Shadow before operating integration; separate evidence-only and alternative-policy evaluation; NEXT-6C/D/E roadmap; Risk, stale, source/time and plan boundaries survive. |
| R12 | [Implementation baseline](StockScope_IMPLEMENTATION_BASELINE_vNext.md), sections 3 and 7 | Evaluation protocol before results; uncertainty and insufficient evidence preserved; operating activation separate from research approval; understandable proposal/application distinction. |
| R13 | [context.py](../backend/app/macro/context.py), `build_macro_context`; [shock.py](../backend/app/macro/shock.py), `ShockState`, `build_uncalibrated_shock_assessment` | REFERENCE_SHADOW and HISTORICAL_EVALUATION exist. Current context rejects APPROVED_RESEARCH calibration execution. RATE_SPIKE assessment is UNCALIBRATED when rate features exist and UNKNOWN if absent. DIAGNOSTIC_ONLY/RESEARCH_ONLY are not current ShockState enum members. |
| R14 | [models.py](../backend/app/macro/models.py), `MacroObservation.normalized_payload`; [reader.py](../backend/app/macro/reader.py), as-of and fixed-vintage reads | Source revision/time lineage exists, but normalized identity intentionally excludes fetch/first-seen timestamps. Fixed-vintage research chooses revisions, not proof of analyst non-exposure. New independence records are needed. No reader was invoked. |
| R15 | [strategy/context.py](../backend/app/strategy/context.py), `regime_from_index`; [strategy/engine.py](../backend/app/strategy/engine.py), `_risk_gate` | KRX-based regime and PANIC/liquidity/event/extreme-move gates are separate current contracts. Macro diagnosis cannot automatically change them. |
| R16 | [strategy_change.py](../backend/app/simulation/strategy_change.py), `production_blocked_approval_protocol`; [strategy_governance.py](../backend/app/simulation/strategy_governance.py) | Production approval default has activation_eligible=false and q7_precommitted=false; strategy identity/governance is separate from Macro evidence. |
| R17 | [CI workflow](../.github/workflows/ci.yml) | Required checks are Frontend / Node 22, Backend / Python 3.11 and Backend / Python 3.14. Documentation scope does not waive them. |

## 4. Decision matrix

These are explanatory assessments, not ordinal scores. FAVORABLE means suitable for the stated claim and constraints, not scientifically certified. MIXED and UNFAVORABLE identify tradeoffs. BLOCKING identifies a prerequisite that prevents the proposed use today. No totals or numeric ranking are used.

| Dimension | PATH A | PATH B | PATH C | PATH D |
|---|---|---|---|---|
| Scientific integrity | FAVORABLE: preserves unresolved numeric claim | BLOCKING now: new budgets do not close U1; conditional validity needs an executable justified procedure | FAVORABLE for finite-path description only; no generalization claim | MIXED: potentially simpler target, but replacement is not a theorem |
| Independence integrity | FAVORABLE: no new fitting/evaluation | BLOCKING until freeze and separate eligible evaluation evidence | FAVORABLE for disclosed retrospective description; cannot claim independent validation | MIXED: Development-informed redesign still needs independent evaluation |
| Engineering cost | FAVORABLE for code maintenance; UNFAVORABLE for indefinite research dependency | UNFAVORABLE: exposure ledger, capture, versioned evaluation and inference maintenance | MIXED: bounded projection/state/lineage work; no bootstrap in descriptive path | UNFAVORABLE: new reference engine, compatibility, replay, lineage and validation |
| Product usefulness | UNFAVORABLE for calibrated RATE_SPIKE progress; existing Macro context can continue | MIXED: possible numeric product benefit after uncertain accumulation and proof effort | FAVORABLE: concise support/movement/context explanation; calibrated alert remains unavailable | MIXED: possible adaptation/reproducibility benefit after substantial redesign |
| Governance clarity | FAVORABLE: explicit blocked state, though indefinite waiting is a weak roadmap | MIXED: clear if post-evidence origin, budgets and claims stay separate | FAVORABLE if diagnostics, computability and inference status remain separate | MIXED: needs explicit old/new contract retirement and migration decisions |
| Future extensibility | MIXED: preserves research but retains the full current burden | FAVORABLE: versioned policy/evidence separation can support later justified claims | FAVORABLE: description can coexist with future independently justified inference | MIXED: modular redesign may help, but compatibility costs are substantial |
| Overfit risk | FAVORABLE: no further selection | MIXED: reduced by preregistration, independent evidence and change control; not erased | MIXED: cherry-picked displays or hidden stability thresholds remain risks | UNFAVORABLE unless candidate architecture and evaluation protocol freeze before evaluation |
| B.2 impact | BLOCKING: existing eligibility freeze stays blocked | BLOCKING until policy, inference and independent validation prerequisites close | BLOCKING for original numeric B.2; requires a separately specified diagnostic-use contract | BLOCKING: original B.2 would require replacement/redefinition and fresh review |
| RATE_SPIKE impact | Current UNCALIBRATED; future uncalibrated/research role | Current UNCALIBRATED; future calibration only after all separate gates | Current UNCALIBRATED; future diagnostic/research usage alongside that calibration state | Current UNCALIBRATED; future role depends on the new architecture and validation |
| User-facing consequence | Honest uncalibrated label; no new movement explanation | Eventually a bounded, scoped claim if justified; no immediate new certainty | Proposed short support/movement/limitation display with optional detail | New reference meaning and continuity explanation required; no immediate benefit |

## 5. PATH A — keep the numeric path blocked

A is scientifically defensible and has nearly no implementation cost. It prevents post-hoc fitting and preserves all immutable evidence. For a product requirement explicitly demanding a numeric minimum-N guarantee, A is the only currently honest disposition of that particular claim.

It is not the only honest disposition of the whole Macro product. R11/R13 already separate readable Context from calibrated shock detection, and R2 recognizes exact finite-path description. Making further explanation wait for the complete joint theorem would sacrifice supported product value without improving the truth of a descriptive statement.

A leaves B.2 blocked, RATE_SPIKE uncalibrated and R2.1 outside active policy. It does not require discarding or hiding historical research. Existing unrelated product work can continue. As the primary project direction, however, it supplies no bounded delivery target for this research branch and retains all endpoint, denominator, common-N, automatic-tuning and budget blockers. We retain its fail-closed constraint, not indefinite theorem search as the primary work program.

## 6. PATH B — a new post-evidence numeric policy

### 6.1 Policy inputs and authority

B is possible only as **NEW_POST_EVIDENCE_POLICY**. Owner approval can establish a new acceptance preference; it cannot establish that a preference existed before R2.1, prove a theorem or manufacture independent evidence. Neither this review nor an assistant chooses a numeric input.

| Required policy input | Required rationale / approval responsibility |
|---|---|
| Intended use and exact claim | Project/product owner: which user decision or informational error matters; finite-path, process or future-predictive target explicitly distinguished |
| Movement acceptance and downstream loss | Project owner with risk/use-case responsibility: consequences and acceptable loss domain, independently of observed envelopes and surviving candidates |
| Inference-error budget | Same accountable owner: cost of false adequacy and scope of the joint claim; separate from movement budgets and numerical approximation error |
| Method, assumptions, endpoints, ties/zero scale, joint root and selectable-N protection | Statistical reviewer: applicability proof for the actual executable procedure, not a conventional default or an isolated building-block theorem |
| Evidence population, exclusions, dependence/overlap handling, stopping and failure rules | Statistical reviewer and data custodian: appropriate evaluation and auditable non-exposure |
| Versioning, PRNG/numerical reproducibility if applicable, schemas and rollback | Architecture/engineering owner: deterministic replay and separation from operating-policy activation |

These are proposed responsibilities, not a claim that a staffed review committee exists. The next numeric-governance specification must name accountable approvers and record their decisions; if one person occupies multiple roles, the record must disclose that limitation. No approvals or numeric values are implied by merging R2.4.2.

Freeze the complete policy and evaluation protocol before exposure to the eligible evaluation sample. Freezing budgets while leaving method, stopping, exclusions or endpoints adjustable is insufficient. If the current expanding/common-N architecture is retained, B still needs U1 closure. If the target/architecture changes materially, classify and review that change explicitly rather than silently substituting it under B.

### 6.2 Independence-recovery candidates

| Candidate | StockScope feasibility | Blocking issue / disposition |
|---|---|---|
| B1. Prospective accumulation | **FAVORABLE as a future design:** current reader exposes available_at, first_seen_at, source/revision and cutoff fields; Context supports as-of identity | Current runtime does not establish a policy-freeze/non-exposure ledger. New observations are potentially eligible, not statistically independent by timestamp. Overlapping features and serial dependence remain. Preferred acquisition route, not ready today. |
| B2. Untouched historical segment | **MIXED / NOT ESTABLISHED:** fixed-vintage research infrastructure could address a separately authorized non-Holdout segment | No untouched segment has been established from the reviewed lineage. Absence from this review is not evidence of non-exposure. Require prior research/access/derivative-use records, exact predeclared selection and compatible time semantics; unknown exposure fails eligibility. No data search or candidate interval selection was performed. |
| B3. External calibration dataset | **MIXED / NOT QUALIFIED:** compatible source adapters are structurally possible | Must prove measurement, dependence and transfer compatibility. Another vendor's copy of the same dates is not new independent market evidence. No qualifying external dataset is claimed or acquired. |
| B4. Formal downstream loss criterion | **FAVORABLE as a budget-design precursor**, conditional on a real product use and accountable owner | It is not an evaluation dataset and does not independently recover a sample. Pair with B1, or a separately qualified B2/B3. Does not close inference error or U1 by itself. |

B1 is the realistic default because it does not require proving that an already-public historical interval was never examined. It still needs future infrastructure and time to accumulate evidence; no validation duration or observation count is chosen. The feasible long-term combination is B4 for operational rationale plus B1 for new evidence, with both method and policy frozen before evaluation.

For B2, source availability dates, repository commit dates and analyst exposure dates answer different questions. Revisions of an already-seen interval, a new vintage label, compact encoding, a random re-split of Development, and cached derived summaries do not make it untouched. Holdout is categorically outside this candidate route; no Holdout inventory or disjointness scan is authorized here.

For B3, qualification must cover:

- **Measurement compatibility:** the same economic object, tenor, yield convention, units, rounding, observation cadence, missingness rules, revision/vintage policy, and point-in-time availability. R9's observation-indexed bp changes must retain their meaning; calendar-day substitutions and price/yield substitutions require a new contract.
- **Dependence compatibility:** joint source chronology, cross-horizon overlap, serial dependence, and shared macro shocks. Different provider ownership is not statistical independence. Another tenor/country may add evidence but changes the population and dependence structure.
- **Transferability:** explain why a bound or loss finding transfers to StockScope's target series and operating context, including regime/measurement differences. A theorem, a deterministic bound or a preregistered external-to-target validation argument is required for the chosen claim; convenient similarity is insufficient.

Official [FRED real-time-period documentation](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) distinguishes currently known historical information from historical vintages and uses date-based real-time fields. This supports revision-aware design, not analyst non-exposure, intraday availability or independence certification. Public documentation only was consulted; no observation API was called.

### 6.3 Formal downstream loss without selecting numbers

R1/R2 show how reference movement affects a fixed feature's robust score. With nonzero anchor scale, define signed center movement c and scale movement s:

```text
z_N = (x - m_N) / d_N
c = (m_t - m_N) / d_N
s = (d_t - d_N) / d_N
z_t = (z_N - c) / (1 + s)
```

A bound on score error requires an authorized score domain and scale regularity as well as movement bounds. None is selected. Similarly, ECDF sup distance can constrain tail-probability movement at a fixed threshold but does not choose acceptable user-facing error. A downstream binary classification near a threshold can change even under small score movement; a score-error bound alone is not a no-flip guarantee.

B4 must therefore define the loss object, domain, weighting of consequences, intended user interpretation and whether the target is a continuous description or a classification. It must derive a traceable budget and validate the full claim on eligible evidence. It must not infer tolerances from candidate/signal/episode survival, choose a convenient threshold margin from Development, or translate user responsibility into unlimited system error tolerance. It supplies neither an alpha nor a complete inference theorem.

## 7. PATH C — descriptive / diagnostic reference governance

### 7.1 Scope and state semantics

C removes a numeric minimum-N gate from the proposed **diagnostic-use decision**, not from the current V3 contract by declaration. A future versioned specification must distinguish computational availability, observed measurements, provenance, inference limitations and permission to use. It must not introduce a replacement hidden threshold under an adjective.

| Concept | Existing vocabulary / proposed treatment |
|---|---|
| Observed state and history | Reuse the meaning of OBSERVED_REFERENCE_STATE and DESCRIPTIVE_ONLY from R6. Display actual measurements with units, reference identity and observation coverage. |
| Computable measurement | AVAILABLE is computational only. It does not mean sufficient, stable, safe or calibrated. |
| Zero anchor scale | Preserve NON_COMPUTABLE_ZERO_SCALE from R4/R5; relative metrics remain null. Raw computable absolute measurements can retain their own status. |
| Missing input or unusable coverage | Preserve UNAVAILABLE, OUT_OF_RANGE, INSUFFICIENT_HISTORY or MISSING_REFERENCE in their existing domains. A future INSUFFICIENT_EVIDENCE label needs a structural reason; it must not conceal an invented minimum count. |
| Inferential limitation | Proposed separate INFERENCE_UNRESOLVED annotation, mapped to current reference_adequacy=UNRESOLVED. This is not an enum change today. |
| Usage permission | Proposed DIAGNOSTIC_ONLY / RESEARCH_ONLY usage scope, compatible in purpose with existing REFERENCE_SHADOW / REFERENCE_RESEARCH_ONLY. Not a replacement ShockState. |
| Stable / moving classification | Do not adopt OBSERVED_REFERENCE_STABLE or OBSERVED_REFERENCE_MOVING as binary acceptance states here. Without a justified classification definition they import a movement tolerance. Report the observed movement value/path instead. |

Even exact zero observed movement is a finite-path fact, not a future stability claim. No confidence percentage, adequacy pass, green safety badge, combined stability score, STATISTICALLY_SAFE or VALIDATED label is justified by C. Ordinary numeric measurements and counts remain useful; the rejected element is a numeric approval policy, not arithmetic description.

### 7.2 Reuse of R2.1 evidence

| Diagnostic | Supported by existing evidence/source | Meaning and limit |
|---|---|---|
| TAIL forward movement | R5 stores exact encoded distances, maximum, anchor and argmax | Observed ECDF differences on the recorded path; no bound on unobserved future movement |
| Median movement | Absolute median shifts and maxima in R5 | bp movement of observed reference center; not a confidence interval |
| MAD movement | Absolute MAD shifts; relative shifts derived from anchor MAD; explicit null status | Scale movement, with non-computability preserved; no stability approval |
| Support depth | anchor_n, prior_count, family/feature identity | Observed prior support, not recommended_support or minimum sufficient N |
| Remaining observed suffix depth | suffix_transition_count and max_prior_count | Number of recorded later states in this research path; not future available data or independent effective N |
| Zero-scale condition | anchor MAD and NON_COMPUTABLE_ZERO_SCALE | Computability limitation; neither instability nor adequacy pass |
| Reference movement history | Encoded paths plus R6 prefix/transition identity | Audit history; retrospective and as-of views must be distinguished |

R2.3's normalized median movement is a future design dimension, not a named stored V3 gate. A future versioned diagnostic view could derive it from the absolute path and nonzero anchor scale with correct units/null propagation. It must disclose derivation and preserve the original artifact. No such projection is produced now.

**Temporal restriction:** an envelope anchored at N contains observations after N. It can describe history at a later research cutoff, but cannot be inserted into a signal or replay as information known at anchor N. A prospective display may show only measurements available by its cutoff, with the comparison range identified. Full Development suffixes stay retrospective. A latest reference has no observed future suffix; missing forward evidence must not become zero movement.

A future descriptive presentation must retain all relevant families/horizons and missingness reasons, avoid highlighting the most favorable anchor, and use a predetermined display rule. The B.1-derived support grid remains Development-informed historical context. It is not a fresh independent sample or a selected adequacy boundary.

### 7.3 RATE_SPIKE and concise product communication

Current calibration remains **UNCALIBRATED**. R13 also correctly emits UNKNOWN when required rate information is unavailable. C preserves this distinction; it does not force absent data into an uncalibrated-but-observed state and does not relabel the detector DETECTED or NORMAL.

Proposed future product role: display rate change and reference diagnostics as reference/research information while calibrated RATE_SPIKE detection remains unavailable. Use a short primary view and optional detail, for example:

```text
금리 변화: [관측값·단위·기준 시점]
참조분포 변화: [관측된 변화·비교 구간]
자료 상태: [관측 수·결측 또는 계산 제한]
RATE_SPIKE 미보정 · 통계적 일반화 미확정
```

Placeholders are presentation concepts, not computed findings or implemented UI. Zero scale can read “기준 MAD가 0이어서 상대 변화 계산 불가.” Retrospective summaries should say “과거 관측 구간” rather than suggest a live warning. Avoid confidence meters and “충분함” badges. Details can expose source/time, method, family and immutable identity without forcing a long research report on the user.

StockScope supplies data, signal context and decision support; the user retains the final investment decision. This responsibility boundary does not excuse misleading certainty. Diagnostic information must not directly trigger buy/sell/stop/take-profit actions, alter Strategy scores or MarketRegime, relax Risk Gate, or update Holdings/Watch plans. Any later operating-policy change requires its own validation and activation path. This review approves no user-facing release.

## 8. PATH D — replacement reference architecture

The current design couples nested expanding references, every-later-state maxima, heterogeneous median/MAD/TAIL functionals, a random anchor denominator, Development-derived anchors and minimum passing common-N selection. R2 explains why this creates a much larger inference burden than describing reference movement. Replacing the architecture is a legitimate option, not a failure of previous work.

All alternatives below are concepts, not selected methods or new window policies. Each can preserve strictly-prior inputs and reproducibility only with a versioned as-of rule and immutable lineage. None automatically supplies a budget or independence.

| Alternative | Strictly-prior / look-ahead and reproducibility conditions | RATE_SPIKE usefulness and real-world tradeoff | Engineering / inference burden |
|---|---|---|---|
| Fixed rolling reference windows | Freeze window rule; exclude the assessed observation; define missingness and revisions; preserve each cutoff's membership | More recent context may adapt to change, but eviction can move the reference and reduce available support | Bounded reference storage is plausible; exact median/MAD maintenance and replay still cost work. Window choice and overlap dependence remain; no window size selected. |
| Predefined calendar windows | Calendar boundaries fixed before evaluation; use only available prior observations; never use a completed period before it ends | Easy period explanation, but unequal sample counts and boundary discontinuities | Moderate membership/transition design; calendar alignment does not create iid samples or numeric adequacy. |
| Fixed training window + prospective validation | Freeze training membership, reference, transforms and update/retraining policy before validation exposure | Stable comparison basis; may become stale as the market changes | Removes repeated reference reselection during a validation phase, but training uncertainty, temporal dependence, drift and later retraining still require treatment. Moderate new lineage/evaluation work. |
| Regime-segmented references | Regime assignment must use only information available then; labels, transitions and reference reuse fixed prospectively | Potential contextual relevance, but sparse segments and unstable assignments can limit usability | High segmentation/model-selection and cross-regime testing cost. R15's current KRX regime is not a validated segmentation model for US yields. |
| Sequential monitoring | Define filtration, monitored target, update/stopping rule and admissible process assumptions before observations | Could support ongoing monitoring without repeated ad-hoc fixed-sample tests | Substantial theorem/implementation work. Time-uniform theory is available under stated assumptions, not a free guarantee for the existing nested TAIL/MAD/common-N target. |

[Howard et al., Time-uniform, nonparametric, nonasymptotic confidence sequences](https://arxiv.org/abs/1810.08240) establishes time-uniform methods under specified conditions. [Howard and Ramdas, Sequential estimation of quantiles](https://arxiv.org/abs/1906.09712) explicitly considers an iid observation stream for its quantile confidence sequences. These are primary-source examples of alternative targets, not a new proof for StockScope's dependent reference procedure. No sequential method is adopted.

Our architecture inference is that a fixed reference with prospective evaluation could reduce reference-selection complexity for a future bounded claim. That is not a proof of validity or a commitment to D. D is not primary because C can deliver the presently supported information with less contract replacement; the repository does not yet establish a product need that justifies the migration and fresh validation burden. Reopen D only through an explicit architecture task if a required claim cannot be served by C or a justified B procedure.

## 9. B.2 disposition and production boundaries

R10 explicitly identifies B.2 as **eligibility policy freeze**. R4/R5 retain undefined eligibility/admissibility policy, no final candidate selection and false readiness. No fully specified diagnostic replacement for B.2 is present in these current contracts. Do not confuse this Macro workstream with `v0.21.4-B.2` exit-policy history.

| Path | Existing B.2 | Required future treatment |
|---|---|---|
| A | Remains BLOCKED | Reopen only after complete numeric prerequisites; no diagnostic label can pass it. |
| B | Remains BLOCKED | New policy authority, applicable inference and independent validation must close before a separately reviewed eligibility freeze. Independent validation alone is insufficient. |
| C | Remains BLOCKED | Specify diagnostic display/research eligibility separately from numeric reference adequacy and detector candidate admissibility. Explicitly decide which original B.2 requirements remain required, are deferred, or are replaced in a new contract. Diagnostic publication is not completion of old B.2. |
| D | Remains BLOCKED | Replace/redefine B.2 against the new calibration architecture, preserve old lineage and require fresh approval; no inherited PASS. |

For C, R2.4.3 must define the permitted diagnostic outputs, non-computability/provenance restrictions, consumer boundaries and migration relationship before an implementation task. If the project later requires calibrated RATE_SPIKE, it returns to independently justified numeric/calibration work; C is not a backdoor candidate-selection rule.

R11/R12/R15/R16 retain these distinct responsibilities: Macro describes its own evidence; Strategy/MarketRegime and Risk retain their existing inputs/guards; Simulation evaluates frozen alternatives; operating owners activate separately; Holdings/Watch keep explicit plan/version/stale protection. A descriptive artifact, an approved research result and a Production policy remain different things.

## 10. Artifact disposition and engineering debt

The disposition of `REFERENCE-ADEQUACY-EVIDENCE-46e5a9c059f72187.json.gz` is:

| Role | Decision |
|---|---|
| HISTORICAL_RESEARCH_EVIDENCE | YES — preserve immutable identity, original semantics and exposure history |
| DIAGNOSTIC_EVIDENCE | YES — permitted role for future scoped, traceable descriptive use; no projection is generated now |
| ACTIVE_POLICY_INPUT | NO — cannot select N, approve adequacy, choose thresholds or drive Production |
| DEPRECATED_POLICY_EXPERIMENT | Not the primary artifact label: this artifact never became an active numeric policy. Its attempted numeric-gate research route remains blocked, not erased. |

Protocol/research documents remain ANTI_OVERFIT_GOVERNANCE and FUTURE_RESEARCH_BASIS. The compact encoding remains useful storage/audit engineering; it conveys no new independence or statistical validity. No immutable artifact is deleted, overwritten, regenerated or retroactively relabeled in place. Future derived views must have separate versions and source identity, with original records preserved.

**Does maintaining the numeric minimum-N gate impose disproportionate debt?** For the immediate goal of concise Macro reference context, yes: R2's unresolved proof/tuning/budget chain is not required to truthfully report observed measurements. As a dormant fail-closed record the gate is inexpensive; as a mandatory active research dependency it is disproportionate to that limited product use. This is a scope/dependency assessment, not a measured development-time estimate.

**Does continued research delay other important work?** The documented NEXT-6 roadmap still includes relative market/sector/stock impact, Event Evidence composition, and Historical/Execution/Prospective evaluation (R11 sections 17–18). It also retains PIT-sector, source-rights, data-time and operating-governance prerequisites. Requiring full numeric closure before all descriptive Context work would impose an unnecessary dependency and consume attention those tasks need. The review did not audit current staffing or measure a schedule slip, so no actual delay duration or current completion claim is made.

C permits a bounded specification for supported context; it does not declare NEXT-6C/D/E ready or remove their independent requirements. Signal-conditioned/episode-conditioned validation remains blocked where calibrated detection is genuinely required. General reference, source/time and evidence-only design can proceed within its own scope.

Past R2 effort is neither a reason to preserve numeric minimum-N at any cost nor wasted effort. It supplies exact evidence, reliable compact representation, anti-overfit constraints and a clear boundary on claims. The relevant future question is the value and justified cost of the next claim, not how much work has already been spent.

## 11. Independence recovery plan for secondary PATH B

This is a design, not an executed freeze or collection event. Dates, durations, sample counts, tolerances, confidence levels, alpha and window sizes remain unset.

| Required field | Proposed contract |
|---|---|
| policy_freeze_event | Immutable, approved policy + evaluation-protocol version, content hash and timestamp recorded before eligible evidence exposure. Include intended claim, budgets and rationales, methods, transformations, update rules, exclusions, stopping and failure behavior. No actual freeze event occurs in R2.4.2. |
| policy_authority | Named accountable project owner for acceptable consequences/budgets; documented statistical-method review; data-custodian provenance attestation; architecture owner for reproducibility. Roles/approvals to be recorded in a future specification, not assumed. |
| evidence_eligibility_cutoff | Event-relative boundary at the approved freeze. Admission requires evidence first observed after that event plus source availability, prior exposure and dependence checks; dates are not selected here. |
| allowed_future_evidence | Prospectively captured new observations with verified source/time/measurement lineage, no policy/evaluation leakage, and an approved treatment of serial/cross-horizon dependence. B2/B3 only after separately documented non-Holdout qualification before values are inspected for evaluation. |
| forbidden_pre_freeze_evidence | Already observed/used R2.1 Development and its envelopes, candidate/signal/episode outcomes, derivative reports, re-encodings, overlapping reused evaluation rows, and revised/refetched copies presented as new independent observations. No retrospective repartition can erase exposure. |
| lineage_requirements | Policy/protocol hash and approval record; source/series/units/normalizer/feature versions; observation/revision/vintage and available_at; first-seen and actual analyst/pipeline exposure records; input membership and overlap map; cutoff/time-quality; exclusions; implementation/evaluator identity; deterministic run/failure record. |
| immutable_artifact_requirement | Append-only freeze, acquisition/exposure and evaluation manifests with content identity; preserve every revision and failed evaluation; never overwrite old evidence. Existing normalized_hash alone is insufficient because it excludes operational first-seen/fetch fields (R14). |
| evaluation_start_condition | Policy authority complete; exact claim/method and dependence/selection validity justified; numerical/reproducibility contract frozen; independent evidence eligibility audited; evaluation/stopping and failure rules executable; no unresolved source/time/lineage issue. If any is open, evaluation stays blocked. |
| Holdout_role | No role in policy creation, tolerance/method/minimum-N selection or B1–B4 qualification. Reserved only for a later separately authorized final out-of-sample review of a fully frozen policy; readiness remains false and no access occurs here. |

### 11.1 Exposure and temporal dependence are separate

Pre-freeze observed/used data are ineligible as independent validation. Post-freeze first observations are only **potentially eligible**. Policy immutability protects against adapting to the evaluation set; it does not make adjacent financial observations independent or cure overlapping 1/5/10-observation features.

The future contract must predefine treatment of source-level overlap at the freeze boundary, warmup/reference inputs, label/outcome leakage if applicable, serial dependence, revisions and synchronized horizons. No arbitrary purge gap is chosen. Pre-freeze data may be explicitly pinned training/reference context if the future method justifies that conditional use; they cannot count as fresh validation, supply post-hoc budgets, or be silently included in the evaluation denominator. If validity cannot be established for boundary-crossing features, their eligibility remains unresolved rather than assuming the whole row is new.

Source-normalized identity and immutable dataset hashes support reproducibility, not proof that a human or prior analysis never saw the data. Capture receipts and an exposure ledger must cover the actual research team/pipeline, not just this chat. A later download timestamp cannot reset earlier exposure. Existing fixed-vintage REFERENCE_RESEARCH_ONLY datasets cannot be admitted simply by changing a split label; a future versioned evaluation contract is required.

### 11.2 Changes, stopping and re-entry

No repeated evaluation followed by tolerance, method, horizon, sample-boundary or stopping-rule adjustment is permitted on the same sample. A substantive policy change creates a new version; evidence already revealed becomes exposed for that version and cannot serve as fresh independent evaluation. Keep failed, inconclusive, non-computable and NO_SUPPORTED_BOUNDARY results. No favorable-N or signal-survival rescue rule is allowed.

For a sequential plan, freeze a justified monitoring/stopping construction; for a fixed evaluation plan, freeze its evaluation event and eligibility rule before unblinding. Neither is selected here. Future source loss, incompatible revisions or lineage gaps must stop evaluation or produce the predeclared limited result rather than trigger an unrecorded dataset switch.

Even successful future validation does not retroactively change U2's historical provenance verdict. It may support a new policy under a new record. Reopening numeric work requires an explicit governance decision; **R2.5_ALLOWED remains false now**. B.2, final out-of-sample review and Production activation each keep separate gates.

## 12. Selection rationale and exact next task

C is selected because:

- **Scientific validity:** its finite-path claim is supported by R2/R5; it leaves population/predictive and minimum-N claims unresolved.
- **Independence:** it discloses Development-informed history and does not call it validation. Secondary B provides an explicit route for future separate evidence.
- **Product value:** R11/R13 support reference Context separate from calibrated detection; concise movement/support limitations can inform users without claiming an actionable shock.
- **Engineering burden:** reuse of existing diagnostic/state/identity concepts avoids making the complete joint theorem a dependency for descriptive information. Projection and consumer-boundary work still need specification and tests later.
- **Governance clarity:** computational availability, observed movement, inference limitation and allowed use stay distinct. Old B.2 remains blocked rather than silently passing under a new name.
- **Extensibility:** immutable evidence and versioned diagnostic projections can coexist with a later independently evaluated numeric policy.
- **Overfit control:** no threshold, minimum N, favorable anchor, candidate survival or new window is selected; future displays and evaluation rules must be frozen against cherry-picking.

B is secondary because it addresses future evidence separation and project-owned acceptance requirements, not because it has solved either blocker. A sacrifices useful bounded progress when elevated to the whole project direction. D requires substantial replacement before a stronger product need and applicable inference contract have been established. These are blocking-issue and use-case judgments, not weighted scores.

The next task is:

```text
NEXT-6B-S4.2-B.1.6-R2.4.3
Diagnostic Reference Governance Redesign Specification
```

R2.4.3 should specify a versioned diagnostic contract, state mapping, units/null handling, as-of versus retrospective projection rules, evidence lineage, predetermined display scope, concise user language and explicit consumer restrictions. It must state the old B.2/new diagnostic-use relationship and preserve RATE_SPIKE calibration status, original artifacts, source/time integrity and operating boundaries. It should define acceptance checks for a later implementation: future-row invariance for as-of views, zero-scale/missing-data handling, full-family disclosure, no diagnostic-to-policy promotion and unchanged baseline behavior. It is not a numeric-policy task, immediate implementation, new data collection, Holdout access or R2.5 execution.

## 13. Review and delivery controls

The review checks are complete: all four paths compared on common dimensions; B1–B4 assessed; current facts separated from proposals; one primary and one conditional secondary selected; artifact role and B.2 consequences explicit; independence contract designed; no new numeric parameter, evidence re-evaluation or operating approval introduced.

Authorized repository change: this Markdown file only. No backend, frontend, runtime, scanner, strategy, holdings, risk engine, sync_local.ps1 or Protocol V3 changes. No additional deliverable or runtime file is created.

After the document diff is checked, delivery requires a PR containing exactly this file and all three CI jobs in R17 passing for the submitted revision before squash merge. CI tests software regression/build behavior; passing CI does not validate the statistical policy or implement C. The PR/check records and final delivery report carry the actual CI results and merged main SHA; this pre-merge document does not claim a future result.

## 14. Final verdict

```text
PRIMARY_PATH = C

SECONDARY_LONG_TERM_PATH = B

RATIONALE = Use supported finite-path diagnostics within StockScope's reference-context boundary; retain blocked numeric claims and immutable evidence; permit only a separately approved, justified and independently evaluated post-evidence policy as a future route.

CURRENT_NUMERIC_POLICY = NONE

CURRENT_REFERENCE_ADEQUACY = UNRESOLVED

CURRENT_RATE_SPIKE = UNCALIBRATED

R2.5_ALLOWED = false

HOLDOUT_ACCESSED = false

CODE_CHANGES = 0

RUNTIME_ARTIFACT_CHANGES = 0

NEXT_TASK = NEXT-6B-S4.2-B.1.6-R2.4.3 — Diagnostic Reference Governance Redesign Specification
```
