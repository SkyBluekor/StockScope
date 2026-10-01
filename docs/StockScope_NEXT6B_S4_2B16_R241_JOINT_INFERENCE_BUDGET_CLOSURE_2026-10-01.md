# NEXT-6B-S4.2-B.1.6-R2.4.1 — Joint Sequential Inference Proof & Independent Budget Provenance Closure

Date: 2026-10-01 (Asia/Seoul). Research / proof / governance review only.

## 1. Executive verdict

| Decision | R2.4.1 result |
|---|---|
| U1 — joint sequential inference closure | **PARTIAL_THEORY_ONLY** |
| U2 — independent budget provenance | **NO_JUSTIFIED_BUDGET_SOURCE** |
| Combined | **NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY** |
| R2.5 numeric evaluation | BLOCKED |
| minimum-N selection | BLOCKED |
| Holdout accessed | NO |
| Code/runtime changes | 0 |
| Production impact | NONE |

R2.4.1 does not close the full StockScope inference chain.

The literature supports several important building blocks: dependent sequential empirical-process resampling under explicit mixing assumptions; regular sample-quantile block-bootstrap theory; functional/directional delta-method theory; and simultaneous resampling procedures under appropriately defined roots.

However, no reviewed theorem directly establishes the complete StockScope procedure:

~~~text
chronological dependent source process
→ three overlapping horizons
→ nested expanding references
→ ECDF sup forward envelopes
→ median/MAD forward envelopes
→ random anchor-MAD normalization
→ nine required adequacy components
→ data-derived candidate support points
→ selectable common N
→ exact automatic dependence tuning
→ one simultaneous coverage event
~~~

The gaps concern the inferential target, endpoint domain, regularity of median/MAD under ties and dependence, selectable-N protection, and statistic-specific automatic tuning.

The budget side also does not close. R2.4's repository and domain search found no qualifying pre-existing inference-error budget or movement-acceptance budget. R2.4.1 found no new source that changes that result. A new project-owner policy can be created prospectively, but it would be a NEW_POST_EVIDENCE_POLICY, not independent pre-existing evidence. It therefore requires an independence-recovery plan before Development can be used as a calibration/evaluation sample.

## 2. Verified repository state

GitHub main was verified before branch creation:

~~~text
4f5a49bf16530aff78db2619cc7075b008458130
~~~

This main includes PR #43, the R2.4 dependence method and risk-budget governance review.

Authoritative R2.4 input:

~~~text
docs/StockScope_NEXT6B_S4_2B16_R24_DEPENDENCE_RISK_GOVERNANCE_REVIEW_2026-10-01.md
~~~

Frozen state carried forward:

~~~text
Reference Adequacy Protocol
VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3

Current compact evidence
REFERENCE-ADEQUACY-EVIDENCE-46e5a9c059f72187.json.gz

Common support points
1488

Reference families
6

Forward comparisons
8716632

minimum_prior_observations = null
recommended_support = null
reference_adequacy = UNRESOLVED
RATE_SPIKE = UNCALIBRATED

B.2 ready = false
Holdout ready = false
Holdout accessed = false
Production impact = NONE
~~~

R2.4 final state:

~~~text
U1 = METHOD_NOT_JUSTIFIED
U2 = NO_INDEPENDENT_RISK_BUDGET
Combined = NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY
~~~

R2.4.1 did not decode or inspect R2.1 Development envelope values.

No Holdout file was searched, opened, hashed, existence-checked or statistically evaluated.

## 3. Frozen R2.4 constraints

R2.4.1 preserves all previously frozen constraints:

- no iid shortcut;
- no independent two-sample KS substitution;
- no manual block length;
- no outcome-driven method fallback;
- no conventional 95% / 99% / alpha=0.05 default;
- no arbitrary standalone validation-suffix K;
- no candidate/signal/episode-survival input;
- no method-specific or horizon-specific N;
- no post-hoc tolerance relaxation;
- no Holdout access;
- NO_SUPPORTED_BOUNDARY remains a valid future result.

The R2.3 candidate method remains only a candidate:

~~~text
PRIMARY_UNCERTAINTY_METHOD_CANDIDATE
=
STATIONARY_BOOTSTRAP
~~~

R2.4.1 does not silently upgrade it to an approved method.

## 4. Inferential claim definition

R2.4 identified an ambiguity that must be resolved before a bootstrap has a well-defined target.

Three distinct claims exist.

### 4.1 Finite-path descriptive claim

For the observed Development path:

~~~text
the exact forward envelope from anchor N is value D
~~~

R2.1 already computes this exactly. This requires no bootstrap.

### 4.2 Population/reference-process inference

A repeated-sample claim about a population or stochastic process parameter:

~~~text
the underlying reference-generating process has movement bounded by delta
with a specified simultaneous error guarantee
~~~

This requires a process model, estimand, limiting/root statistic and valid inference method.

### 4.3 Future-path predictive claim

A predictive statement:

~~~text
future expanding references will remain within a movement bound
with specified probability
~~~

This is not the same as population inference or finite-path description.

### R2.4.1 freeze

The three claims must remain distinct.

A future executable Reference Adequacy procedure must state exactly which claim it certifies.

Current state:

~~~text
finite_path_description = AVAILABLE
population_inference = NOT_CLOSED
future_prediction = NOT_DEFINED
~~~

Therefore a descriptive R2.1 envelope must not be relabeled as a probabilistic adequacy guarantee.

## 5. Exact observed statistics

For horizon h in {1obs, 5obs, 10obs}, let F[h,k] be the ECDF of the first k strictly-prior available feature values, m[h,k] their sample median, d[h,k] their unscaled MAD about the sample median, and M[h] the last available prior-state size.

Observed R2.4 future-design metrics:

~~~text
T[h,N]
=
max_{N < t <= M[h]}
sup_x |F[h,t](x) - F[h,N](x)|
~~~

~~~text
C[h,N]
=
max_{N < t <= M[h]}
|m[h,t] - m[h,N]| / |d[h,N]|
~~~

~~~text
S[h,N]
=
max_{N < t <= M[h]}
|d[h,t] - d[h,N]| / |d[h,N]|
~~~

for computable nonzero d[h,N].

There are nine future adequacy components per N:

~~~text
3 TAIL
3 normalized center
3 relative MAD
~~~

The six stored R2.1 reference families must not be confused with nine future inferential components.

## 6. Sequential-process formulation

For the TAIL component, the nested identity is:

~~~text
F_t - F_N
=
((t-N)/t) * (F_(N+1:t) - F_N)
~~~

but prefix and suffix are not independent under serial dependence.

A natural process-level route is to begin from a sequential empirical process such as:

~~~text
A_M(s,x)
=
M^(-1/2)
sum_{i=1}^{floor(Ms)}
{1(X_i <= x) - F(x)}
~~~

and map it to nested prefix differences.

The reviewed dependent-multiplier literature shows that genuinely sequential empirical-process bootstraps can be valid under explicit strong-mixing and multiplier/bandwidth conditions. Bücher and Kojadinovic develop a sequential dependent multiplier bootstrap and a data-adaptive bandwidth estimator for their empirical-copula setting, with a sequential empirical-process result as a building block.

Source:

- Axel Bücher and Ivan Kojadinovic, A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing.
- https://arxiv.org/abs/1306.3930

This establishes an important building block. It does not directly establish the StockScope TAIL/MAD/common-N procedure.

## 7. Endpoint analysis

For a sequential empirical process, nested prefix differences contain factors behaving like 1/s when an anchor fraction s=N/M is mapped back to a prefix ECDF.

Two endpoint issues remain.

### 7.1 Early-anchor endpoint

If N/M tends to zero, the transformation may become non-uniform unless a theorem explicitly controls that endpoint.

### 7.2 Late-anchor endpoint

If M-N is very small, only a tiny future suffix remains.

The previous arbitrary suffix K was intentionally eliminated.

R2.4.1 found no theorem that simultaneously covers the exact StockScope nested transformation, all currently allowed candidate anchors, no independently chosen trimming fraction, and no newly selected suffix count.

Therefore:

~~~text
endpoint_problem = UNRESOLVED
~~~

A future theorem requiring s in [epsilon, 1-epsilon] cannot be adopted unless the resulting epsilon has independent justification.

Introducing epsilon only to make the theorem applicable would recreate the policy-selection problem under another name.

## 8. TAIL theorem mapping

### 8.1 What is supported

Dependent sequential empirical-process bootstrap theory exists under explicit dependence assumptions.

The Bücher–Kojadinovic work provides sequential dependent multiplier resampling, strong-mixing assumptions, an automatic data-adaptive bandwidth proposal, and change-point / sequential-process applications.

This supports:

~~~text
DEPENDENT_SEQUENTIAL_EMPIRICAL_PROCESS
=
THEORETICALLY_POSSIBLE
~~~

### 8.2 What is not closed

StockScope needs more than a raw empirical process:

~~~text
sequential process
→ nested prefix differences
→ sup over x
→ max over all later t
→ simultaneous over candidate N
→ simultaneous over 3 horizons
→ common-N selection
~~~

The reviewed theorem is not an exact theorem for this complete transformation and selection rule.

The data-adaptive bandwidth is constructed for the paper's multiplier/covariance setting; R2.4 already found no proof that its objective is the exact StockScope joint adequacy objective.

Therefore:

~~~text
TAIL_THEOREM_MAPPING
=
PARTIAL_BUILDING_BLOCK_ONLY
~~~

not DIRECTLY_JUSTIFIED.

## 9. Supremum and directional differentiability

A maximum/supremum map can be continuous while still failing full Hadamard differentiability at nonunique maximizers or zero/tie configurations.

Fang and Santos show that for directionally differentiable but not fully differentiable maps, the standard bootstrap can fail even when the underlying estimator has a Gaussian limit. They develop alternative inference for such cases.

Source:

- Zheng Fang and Andres Santos, Inference on Directionally Differentiable Functions, Review of Economic Studies 86(1), 2019.
- https://doi.org/10.1093/restud/rdy049

Implication for StockScope:

~~~text
bootstrap works for base sequential process
~~~

does not automatically imply:

~~~text
standard centered bootstrap works for
sup/max/selection transformation
~~~

A future proof must explicitly identify the function space, derivative/continuous map, whether the map is fully or only directionally differentiable, and the appropriate resampling transform.

R2.4.1 does not find that complete proof in the reviewed sources.

## 10. Median theorem mapping

The median is a quantile functional.

Regular quantile inference typically requires conditions such as a unique quantile, positive local density, suitable continuity/smoothness, and appropriate serial-dependence conditions.

Kuffner, Lee and Young establish block-bootstrap optimality and empirical block selection for sample quantiles under strong-mixing conditions.

Source:

- T. A. Kuffner, S. M. S. Lee, G. A. Young, Block bootstrap optimality and empirical block selection for sample quantiles with dependent data, Biometrika 108(3), 2021.
- https://doi.org/10.1093/biomet/asaa075

This is strong evidence for regular dependent sample quantiles.

It does not directly establish:

~~~text
max over later prefixes
of
|median_t - median_N| / MAD_N
~~~

simultaneously over N and horizons.

It also does not establish the MAD denominator or measurement-tie conditions.

Therefore:

~~~text
MEDIAN_THEOREM_MAPPING
=
PARTIAL_THEORY_ONLY
~~~

## 11. MAD theorem mapping

StockScope MAD is:

~~~text
median(|X - sample_median|)
~~~

not a quantile of residuals around a fixed known center.

Median uncertainty therefore propagates into MAD uncertainty.

R2.4 already derived the conditional functional relationship showing that both the distribution around m, m-d and m+d matter.

The reviewed MAD literature supplies useful regular iid/robust-statistic building blocks, but R2.4.1 did not identify an exact theorem giving:

~~~text
dependent sequential
joint median + MAD
prefix process
uniform over selectable N
with random anchor denominator
and simultaneous horizon inference
~~~

for the StockScope statistic.

Therefore:

~~~text
MAD_THEOREM_MAPPING
=
PARTIAL_THEORY_ONLY
~~~

## 12. Ratio and zero-scale analysis

Future MAD metrics divide by d[h,N], so a theorem must control the denominator uniformly on the allowed N domain.

The existing StockScope rule remains:

~~~text
d[h,N] == 0
→ NON_COMPUTABLE_ZERO_SCALE
~~~

Frozen:

~~~text
null_to_zero = forbidden
zero_scale_as_pass = forbidden
zero_scale_as_stable = forbidden
~~~

A valid asymptotic ratio proof generally requires an anchor scale separated from zero on the inferential domain.

R2.4.1 finds no pre-existing project rule defining a minimum positive MAD floor, and does not create one.

Therefore uniform denominator regularity across selectable N remains unresolved.

## 13. Measurement ties and discreteness

The repository uses Decimal feature values derived from normalized DGS10 yields and observation differences.

Decimal representation does not establish a continuous population distribution. Rounded source measurements can create repeated values.

This matters because standard quantile differentiability arguments can require a unique population quantile, positive local density, and absence of problematic atoms/flat regions.

Potential fixes such as jitter, kernel smoothing or smoothed quantiles would introduce new modeling and tuning choices.

The bootstrap literature itself treats smoothing as a substantive choice for median inference; it is not a free technical patch.

Source:

- B. M. Brown, Peter Hall, G. A. Young, The smoothed median and the bootstrap, Biometrika 88(2), 2001.
- https://doi.org/10.1093/biomet/88.2.519

R2.4.1 does not introduce jitter or smoothing.

Therefore:

~~~text
TIE_ATOM_REGULARITY
=
UNRESOLVED_MODEL_ASSUMPTION
~~~

## 14. Common joint procedure review

The preferred design remains a single common joint procedure.

Conceptually:

~~~text
one synchronized source-path resampling / multiplier process
↓
reconstruct 1obs / 5obs / 10obs features consistently
↓
recompute TAIL / median / MAD paths
↓
form all nine components
↓
construct one simultaneous coverage event
~~~

This is preferable to independent per-component resampling because it preserves cross-component dependence.

However, R2.4.1 does not find a reviewed theorem that directly validates the entire transformation from one resampled source path to all overlapping horizons, all nested reference prefixes, the MAD estimated-center functional, all selectable N, and the minimum passing common N.

The sequential dependent multiplier literature shows that common process-level resampling is plausible, but the complete StockScope mapping remains unproved.

Therefore:

~~~text
COMMON_JOINT_PROCEDURE
=
PLAUSIBLE_RESEARCH_TARGET
NOT_EXECUTION_READY
~~~

## 15. Calendar alignment and missingness

Equal prior counts across horizons do not imply equal calendar endpoints if availability differs.

A synchronized joint procedure must explicitly define whether it resamples raw source chronology or already-transformed horizon-specific available sequences.

These are different stochastic objects.

Resampling horizon sequences independently would destroy cross-horizon dependence.

Resampling the raw source chronology is structurally cleaner, but a future proof must map:

~~~text
source process
→ overlapping 1/5/10 observation transformations
→ missingness/availability filters
→ joint sequential statistics
~~~

No such full theorem is frozen.

## 16. Automatic tuning closure

### 16.1 Stationary-bootstrap / Politis–White style selector

Automatic block-length rules exist for specific objectives, especially long-run variance / smooth-statistic settings.

R2.4 already established that the corrected Politis–White objective is not the same as StockScope's joint sequential envelope coverage objective.

R2.4.1 does not identify a theorem transferring that selector to the complete StockScope root.

### 16.2 Quantile-specific selector

Kuffner–Lee–Young is closer to the median component because it is quantile-specific.

But it is not a theorem for estimated-center MAD, not a theorem for the nested forward maximum, and not a theorem for the nine-component joint/common-N procedure.

### 16.3 Dependent multiplier bandwidth

Bücher–Kojadinovic propose a data-adaptive bandwidth for their dependent multiplier setting.

This is an attractive candidate building block.

But the StockScope target still lacks an exact process theorem for all components, exact root/normalization, endpoint handling, and selectable-N protection.

Therefore its bandwidth rule cannot by itself close U1.

### U1 tuning result

~~~text
EXACT_AUTOMATIC_TUNING_RULE
=
NOT_JUSTIFIED_FOR_COMPLETE_STOCKSCOPE_PROCEDURE
~~~

## 17. Consistency versus optimality

R2.4.1 distinguishes two claims.

A broad block regime may require conditions such as:

~~~text
block_length → infinity
block_length / n → 0
~~~

or an analogous multiplier-bandwidth regime.

This can be enough for asymptotic validity under a matching theorem.

An executable implementation still needs a deterministic sequence or automatic selector.

Choosing floor(n^c) requires fixing c.

A theorem that merely allows a range of c does not uniquely select one project implementation.

The same problem appears with bandwidth kernels, pilot cutoffs, block search grids, smoothing choices and numerical caps.

R2.4.1 does not treat any theoretically admissible value as a uniquely justified governance choice.

Therefore even consistency-level building blocks do not yet produce an immutable executable contract.

## 18. Common-N selection protection

A future procedure ultimately searches candidate N values and selects:

~~~text
minimum N passing all approved criteria
~~~

Pointwise coverage at each fixed N is insufficient for a statement about the selected minimum N.

The support set itself is inherited from Development-informed B.1 overlays.

A valid procedure therefore needs simultaneous coverage over a deterministic containing N domain or a proved selection-aware procedure, plus justified treatment of the data-derived support subset.

R2.4.1 found no reviewed theorem that exactly closes this selection layer for the complete StockScope procedure.

No N grid, trimming range or selection correction is invented.

## 19. Multiplicity and normalization

A raw maximum across TAIL probability distance, normalized median movement and relative MAD movement is not statistically meaningful merely because all values are dimensionless.

Candidate structures remain:

- studentized maximum root;
- pivotal transformation;
- component-wise simultaneous upper confidence bounds;
- stepdown resampling.

Romano and Wolf show how resampling can support joint multiple-testing control when the underlying approximation and statistic construction are valid.

Source:

- Joseph P. Romano and Michael Wolf, Stepwise Multiple Testing as Formalized Data Snooping, Econometrica 73(4), 2005.
- https://doi.org/10.1111/j.1468-0262.2005.00615.x

This does not choose StockScope's alpha, component acceptance budgets, normalization estimator or selectable-N correction.

Current:

~~~text
joint_multiplicity_scope = FROZEN
joint_numeric_error_budget = null
joint_normalization = NOT_EXECUTABLE
~~~

## 20. Numerical reproducibility requirements

Because U1 is not closed, R2.4.1 does not invent implementation parameters.

A future executable preregistration must freeze:

~~~text
PRNG algorithm
seed derivation hash
multiplier / resampling law
replicate ordering
parallelism-independent identity
resample count OR deterministic stopping rule
Monte Carlo error handling
numerical failure behavior
~~~

Current:

~~~text
resample_count = null
monte_carlo_stopping_rule = null
PRNG_contract = not_implemented
~~~

These are implementation prerequisites, not substitutes for statistical justification.

## 21. U1 verdict

**PARTIAL_THEORY_ONLY**

Reason:

1. A dependent sequential empirical-process bootstrap building block exists.
2. Regular dependent sample-quantile block-bootstrap theory exists.
3. Joint resampling / simultaneous-control theory exists in narrower settings.
4. Directionally differentiable inference theory explains why naive bootstrap transfer can fail.

But the complete StockScope theorem chain remains open at:

- exact inferential target;
- early/late endpoints;
- median/MAD regularity under ties;
- random anchor-MAD denominator;
- common synchronized horizon transformation;
- simultaneous selectable-N protection;
- data-derived support handling;
- exact automatic tuning;
- executable joint normalization.

Therefore:

~~~text
JOINT_INFERENCE_PROOF_CLOSED = false
R2.5 numeric evaluation = forbidden
~~~

## 22. Budget provenance closure — inherited evidence

R2.4 conducted a repository-wide search of tracked governance/specification documents and relevant source contracts.

It found numeric values in areas such as trade risk geometry, backtest trade-count bands, arithmetic comparison tolerance, local data coverage, scanner ranking, warmup rules and capital-aware recommendation design.

R2.4 rejected them because their original purpose and metric scope do not match Reference Adequacy inference or movement budgets.

R2.4 also reviewed external/domain sources including model-risk governance, Basel market-risk validation, NIST process-control material, resampling theory, empirical-distribution theory and robust-statistic theory.

No source supplied a StockScope-specific inference alpha or movement tolerance.

R2.4.1 treats that audited provenance record as frozen input and looks only for evidence capable of reversing the conclusion.

No such source was identified.

## 23. Current model-risk guidance does not supply a number

The 2026 Federal Reserve/OCC/FDIC revised model-risk guidance emphasizes a risk-based approach tailored to a model's use, materiality, assumptions and organizational risk profile.

It describes principles rather than a universal numeric Reference Adequacy tolerance.

Sources:

- Federal Reserve SR 26-2, Revised Guidance on Model Risk Management, April 17, 2026.
- https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm
- https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm

This supports governance discipline.

It does not supply alpha, TAIL epsilon, normalized median tolerance or relative MAD tolerance for StockScope.

It also does not establish that StockScope is a regulated banking model.

## 24. Inference error budget provenance

Current:

~~~text
INFERENCE_ERROR_BUDGET.status = UNJUSTIFIED
INFERENCE_ERROR_BUDGET.value = null
INFERENCE_ERROR_BUDGET.source = NONE
~~~

A statistical theorem may say coverage = 1-alpha or FWER <= alpha conditional on assumptions.

It does not choose the project's alpha.

Conventional 0.05, 0.01, 95% or 99% remain inadmissible without project/domain authority.

No qualifying pre-R2.1 project requirement fixing that error budget has been identified.

Therefore:

~~~text
INFERENCE_BUDGET_PROVENANCE_CLOSED = false
~~~

## 25. Movement acceptance budget provenance

Current:

~~~text
TAIL_ECDF_MOVEMENT = null
NORMALIZED_MEDIAN_MOVEMENT = null
RELATIVE_MAD_MOVEMENT = null
source = NONE
~~~

Statistical uncertainty does not define acceptable operational movement.

The robust-score algebra:

~~~text
z_N = (x-m_N)/d_N
z_t = (z_N-c)/(1+s)
~~~

with:

~~~text
c = (m_t-m_N)/d_N
s = (d_t-d_N)/d_N
~~~

shows how center/scale changes perturb a robust score.

But to convert this into a movement budget one still needs independently authorized inputs such as acceptable downstream score error, admissible score domain and acceptable scale deformation.

No such pre-existing Reference Adequacy requirement is frozen.

Candidate thresholds or candidate survival cannot be used to create them.

Therefore:

~~~text
MOVEMENT_BUDGET_PROVENANCE_CLOSED = false
~~~

## 26. Pre-existing versus post-evidence policy

R2.4 fixed the key provenance distinction:

~~~text
PREEXISTING_PROJECT_REQUIREMENT
!=
POST_EVIDENCE_PROPOSAL
~~~

R2.4.1 strengthens this into a governance rule.

A numeric value can be labeled pre-existing only if all are available:

1. immutable source;
2. original purpose;
3. authority;
4. direct metric/scope linkage;
5. credible evidence it existed before actual R2.1 evidence exposure.

A publication predating R2.1 does not prove that StockScope adopted its conventional value before R2.1.

A newly written R2.4.1 number cannot become pre-existing by calling it a preregistration.

## 27. Can a new policy be created now?

Yes as governance, but not as pre-existing independent evidence.

A project owner could prospectively authorize:

~~~text
inference error budget = A
TAIL movement budget = B
median movement budget = C
MAD movement budget = D
~~~

provided the rationale and authority are explicit.

Such a decision would be classified:

~~~text
NEW_POST_EVIDENCE_POLICY
~~~

not PREEXISTING_PROJECT_REQUIREMENT.

Because R2.1 Development evidence has already been generated/exposed, applying a newly chosen policy back to the same Development sample as though it were independently calibrated would weaken the independence claim.

Therefore a new numeric policy requires an independence-recovery design.

## 28. Independence recovery options

If a new post-evidence numeric budget is authorized in the future, admissible recovery candidates include:

### A. Prospective accumulation

Freeze the policy first, then accumulate future observations not used to define it.

### B. New untouched calibration segment

Use a newly identified data segment that was genuinely unavailable/unexamined when the policy was chosen.

### C. External calibration dataset

Use an independent dataset with compatible measurement semantics and an explicitly justified transfer argument.

### D. New formal downstream loss requirement

Define an independently authorized user/system loss criterion first, derive movement budgets from that criterion, then validate prospectively.

Forbidden:

~~~text
new policy
→ immediately apply to already-inspected R2.1 Development
→ call result independent
~~~

Holdout remains prohibited for policy creation.

## 29. Can Holdout solve the budget problem?

No.

Holdout is reserved for later out-of-sample review after calibration policy is frozen.

Using Holdout to choose alpha, TAIL tolerance, MAD tolerance, N or tuning method would destroy its intended role.

R2.4.1 therefore freezes:

~~~text
HOLDOUT_AS_BUDGET_SOURCE = FORBIDDEN
~~~

## 30. U2 verdict

**NO_JUSTIFIED_BUDGET_SOURCE**

Sub-verdicts:

~~~text
INFERENCE_ERROR_BUDGET
=
UNJUSTIFIED / null

MOVEMENT_ACCEPTANCE_BUDGET
=
UNJUSTIFIED / null

PREEXISTING_REFERENCE_ADEQUACY_BUDGET
=
NOT_FOUND

NEW_POST_EVIDENCE_POLICY
=
POSSIBLE_ONLY_WITH_EXPLICIT_GOVERNANCE
AND INDEPENDENCE RECOVERY
~~~

Therefore:

~~~text
INDEPENDENT_BUDGET_PROVENANCE_CLOSED = false
~~~

## 31. Combined verdict

**NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY**

| Requirement | R2.4.1 state |
|---|---|
| exact inferential claim | clarified, not operationally chosen |
| exact joint process theorem | NOT CLOSED |
| endpoint handling | NOT CLOSED |
| median/MAD regularity | CONDITIONAL / NOT VERIFIED |
| measurement ties | NOT CLOSED |
| synchronized joint procedure | RESEARCH TARGET ONLY |
| automatic tuning | NOT JUSTIFIED FOR COMPLETE TARGET |
| selectable common-N protection | NOT CLOSED |
| joint normalization | NOT EXECUTABLE |
| inference error budget | null |
| movement budgets | null |
| independent budget provenance | NOT CLOSED |
| R2.5 numeric evaluation | BLOCKED |

This is not an impossibility theorem for future research.

It is a governance conclusion for the currently justified StockScope evidence.

## 32. Fail-closed state

The exact current state remains:

~~~text
minimum_prior_observations = null
recommended_support = null
reference_adequacy = UNRESOLVED
RATE_SPIKE = UNCALIBRATED

B.2 ready = false
Holdout ready = false
Holdout accessed = false
Production impact = NONE

numeric_policy_selected = false
minimum_N_selected = false
Development_envelope_evaluation_run = false
candidate_signal_episode_survival_used = false

code_changes = 0
runtime_artifact_changes = 0
~~~

No R2.1 envelope value was used to choose a policy number.

## 33. R2.4.1 completion decision

~~~text
U1
=
PARTIAL_THEORY_ONLY

U2
=
NO_JUSTIFIED_BUDGET_SOURCE

Combined
=
NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY

EXECUTION_PREREGISTRATION_READY
=
false

R2.5_ALLOWED
=
false
~~~

## 34. Exact next task

The next task should not be another unconstrained search for a convenient bootstrap theorem and should not be R2.5.

Recommended next task:

~~~text
NEXT-6B-S4.2-B.1.6-R2.4.2
Reference Adequacy Path Disposition & Prospective Independence-Recovery Design
~~~

Purpose:

Decide, at project-architecture/governance level, which path StockScope will take now that retrospective Development-derived numeric adequacy is not independently justified.

The review must choose among explicitly documented paths such as:

~~~text
PATH A
Keep numeric Reference Adequacy blocked indefinitely
until a complete joint theorem + independent budget exists.

PATH B
Authorize a new post-evidence numeric movement/error policy
with explicit project-owner rationale,
then validate only on untouched prospective / independent data.

PATH C
Redesign Reference Adequacy as a non-numeric descriptive /
diagnostic governance layer rather than a numeric minimum-N gate.

PATH D
Replace the current expanding-reference calibration architecture
with a new method whose inferential target and governance budget
can be preregistered cleanly.
~~~

R2.4.2 must not select numeric values.

It must determine the project path, evidence independence plan, and consequences for B.2 / RATE_SPIKE.

Only a path that creates a genuinely independent executable policy may later reopen R2.5.

## 35. Source register

Primary sources supporting R2.4.1 scope conclusions:

| ID | Source | R2.4.1 use |
|---|---|---|
| S1 | Bücher & Kojadinovic, A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing. https://arxiv.org/abs/1306.3930 | dependent sequential-process bootstrap building block; automatic bandwidth in its stated setting |
| S2 | Kuffner, Lee & Young (2021), Block bootstrap optimality and empirical block selection for sample quantiles with dependent data. https://doi.org/10.1093/biomet/asaa075 | regular dependent sample-quantile block theory; not complete MAD/joint envelope |
| S3 | Fang & Santos (2019), Inference on Directionally Differentiable Functions. https://doi.org/10.1093/restud/rdy049 | standard-bootstrap caution for directionally but not fully differentiable maps |
| S4 | Brown, Hall & Young (2001), The smoothed median and the bootstrap. https://doi.org/10.1093/biomet/88.2.519 | smoothing is a substantive median-bootstrap choice, not a free fix |
| S5 | Romano & Wolf (2005), Stepwise Multiple Testing as Formalized Data Snooping. https://doi.org/10.1111/j.1468-0262.2005.00615.x | joint resampling/multiplicity building block |
| S6 | Federal Reserve/OCC/FDIC, SR 26-2 (2026), Revised Guidance on Model Risk Management. https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm | tailored/non-prescriptive model-risk governance; no StockScope numeric budget |
| S7 | StockScope R2.4 governance review | frozen repository-wide internal/external budget provenance audit |

No source is represented as proving the complete StockScope joint procedure unless it actually does so.
