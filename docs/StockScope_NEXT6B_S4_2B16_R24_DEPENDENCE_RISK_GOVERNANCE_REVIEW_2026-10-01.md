# NEXT-6B-S4.2-B.1.6-R2.4 — Statistic-Specific Dependence Method & Risk-Budget Governance Review

Date: 2026-10-01 (Asia/Seoul). Research / governance review only.

## 1. Executive verdict

| Decision | R2.4 result |
|---|---|
| U1 | **METHOD_NOT_JUSTIFIED** |
| U2 | **NO_INDEPENDENT_RISK_BUDGET** |
| Combined | **NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY** |
| Inference error budget | UNJUSTIFIED; value = null |
| Movement acceptance budget | UNJUSTIFIED; all metric tolerances = null |
| Development evaluation / minimum-N selection | BLOCKED |
| Production impact | NONE |

These decisions concern the **complete StockScope procedure**. They do not claim that stationary bootstrap or robust-statistic inference are invalid in general. Conditional building-block theory exists. The reviewed evidence does not establish the full joint uncertainty procedure and automatic tuning for nested, boundary-anchored, heterogeneous forward envelopes over selectable N. “Method justified, only tuning unresolved” would therefore overstate the evidence.

No qualifying internal or external source supplies a numeric StockScope inference budget or movement budget. No numeric policy, N, method replacement or runtime contract is adopted.

## 2. Verified repository state

### Authority and verification boundary

GitHub main for [SkyBluekor/StockScope](https://github.com/SkyBluekor/StockScope) was checked at the start and again after research, before branch creation:

~~~text
16a8a5d16a1ebc0c7234dac12f667c3d7a11b572
~~~

This equals the requested baseline. The initial local checkout was older, at ad8fd9e31dc52bbf8f36c02666213856cb689df6. Git metadata was fetched; current-file reads used git show origin/main:<explicit path> and scoped git grep. No checkout update or application execution was needed. The documentation branch starts at the verified main SHA.

| Frozen fact | Verification source / qualification |
|---|---|
| VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3 | Current reference_adequacy_protocol.py constant |
| REFERENCE-ADEQUACY-EVIDENCE-46e5a9c059f72187.json.gz | Current frozen R2.2 and R2.3 documents |
| 1,488 common support points; 6 reference families; 8,716,632 forward comparisons | Both frozen reviews report these values; current evidence source implements the corresponding count fields and six families |
| Evidence contract V2, lossless compact representation | Current reference_adequacy_evidence.py |
| METHOD_FRAMEWORK_PREREGISTERED_NUMERIC_POLICY_BLOCKED | R2.3 sections 25–28 |
| U1 STATISTIC_SPECIFIC_DEPENDENCE_TUNING; U2 INDEPENDENT_RISK_ERROR_BUDGET | R2.3 remaining research blockers |
| Null support selection; unresolved adequacy; uncalibrated RATE_SPIKE | Current protocol/evidence builders and validators plus R2.3 |
| B.2 / Holdout readiness false | Current protocol/evidence policy fields |
| Holdout accessed false; Production impact NONE | Preserved contract and the conduct of this review |

**Evidence level:** the artifact name and counts are verified as committed frozen-document facts, not newly recomputed runtime measurements. R2.4 did not decode the compact Development artifact, regenerate its hash or inspect envelope values. It does not certify an uninspected local runtime copy. No Holdout file was sought, opened, hashed, existence-checked or statistically evaluated.

### Required repository files actually read

All paths refer to verified main.

| File | Finding |
|---|---|
| docs/StockScope_NEXT6B_S4_2B16_R22_POLICY_RESOLUTION_REVIEW_2026-10-01.md | Nested ECDF issue; normalized MAD structure; no justified numeric tolerance |
| docs/StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md | Candidate method only; joint scope; no arbitrary K; U1/U2 and fail-closed rules |
| backend/app/macro/reference_adequacy_protocol.py | V3; COMMON_N_FIRST; all-family AND; tolerances null |
| backend/app/macro/reference_adequacy_evidence.py | _tail_family_evidence and _mad_family_evidence compare every later prior state; exact ECDF numerator and anchor denominator |
| backend/app/macro/reference_stability.py | Strictly-prior states; _common_review_points is a sorted union of B.1 support overlays, with all six states attached |
| backend/app/macro/calibration_candidate.py | Three feature IDs; positive-tail and robust-MAD metrics; data-derived candidate thresholds |
| backend/app/macro/calibration_research.py | Development-only validation, ordered unique dates, unselected research, locked Holdout contract |
| backend/app/macro/features.py | Decimal (current yield - baseline yield) * 100; 1/5/10 observation horizons; missing references explicit |
| backend/app/macro/distribution.py | statistics.median; MAD about sample median; strictly-prior score; zero MAD unavailable |
| .github/workflows/ci.yml | Node 22 frontend build; Python 3.11 and 3.14 backend tests |

Current V3 code still represents three raw MAD forward metrics and an unresolved suffix field. R2.2/R2.3 freeze the **future research design** with two normalized adequacy dimensions and structural elimination of a separate arbitrary K. They were documentation-only changes. R2.4 does not pretend those design changes are already implemented.

## 3. Frozen R2.3 constraints

- PRIMARY_UNCERTAINTY_METHOD_CANDIDATE = STATIONARY_BOOTSTRAP.
- PRIMARY_DEPENDENCE_ASSUMPTION = STATIONARY_WEAK_DEPENDENCE; required, not proven.
- Manual block length and outcome-driven fallback = FORBIDDEN.
- Multiplicity = ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY.
- TAIL = ECDF_SUP_DISTANCE on the observed-value union; no invented x grid.
- MAD adequacy dimensions = NORMALIZED_MEDIAN_SHIFT and RELATIVE_MAD_SHIFT; absolute median/MAD bp shifts = DIAGNOSTIC_ONLY in the future design.
- MAD_N == 0 = NON_COMPUTABLE_ZERO_SCALE, never zero movement or pass.
- Standalone arbitrary suffix K = STRUCTURALLY ELIMINATED. Actual suffix sufficiency remains blocked by the uncertainty method.
- Common N across methods/horizons; no passing common N = NO_SUPPORTED_BOUNDARY.
- No tuning from Development envelope shape, candidate/signal/episode survival or number of passing N values.
- No conventional alpha, confidence, MAD multiple, support count or calendar duration without independent justification.
- Resampling count/stopping rule, PRNG and deterministic seed derivation still need a versioned reproducibility contract.

## 4. Target statistic classification

### Exact objects

For horizon h in {1obs, 5obs, 10obs}, let X[h,i] be chronological available feature values, F[h,k] the ECDF of the first k strictly-prior values, m[h,k] their median and d[h,k] their **unscaled** MAD about that median. M[h] is the final reference size, len(rows)-1 in evidence code.

~~~text
T[h,N] = max over N < t <= M[h] of sup over x |F[h,t](x) - F[h,N](x)|
C[h,N] = max over N < t <= M[h] of |m[h,t] - m[h,N]| / d[h,N]
S[h,N] = max over N < t <= M[h] of |d[h,t] - d[h,N]| / d[h,N]
~~~

C and S need a nonzero available anchor MAD and the required later states. Their maxima can occur at different t. The shared anchor denominator cannot be replaced by a later-state denominator. The repository uses no Gaussian consistency factor for MAD.

The nested TAIL identity is:

~~~text
F_t - F_N = ((t-N)/t) * (F_(N+1:t) - F_N).
~~~

Temporal dependence can also connect prefix and suffix. Independent two-sample KS critical values therefore do not follow. The 8,716,632 comparisons are not independent observations.

| Object | Class | Differentiability / bootstrap relevance |
|---|---|---|
| ECDF at fixed x | Linear empirical average of indicators | A scalar CLT does not establish tightness or sequential uniform convergence over x and t |
| T[h,N] | Empirical-process functional with absolute value and two suprema | Sup norm is continuous/Lipschitz, but generally not linearly Hadamard differentiable at ties/zero; a centered process followed by continuous mapping differs from centering a bootstrapped scalar maximum |
| Sample median | Quantile functional; nonsmooth in observations | Tangential Hadamard differentiability requires a unique population median and positive continuous local density; atoms/flat regions/zero density need a different argument |
| C[h,N] | Quantile difference, absolute value, random robust-scale denominator and forward maximum | Ratio calculus requires scale separated from zero; absolute value and max retain nonregular points |
| Sample MAD | Quantile-derived robust scale with estimated center | Not a quantile of fixed, independent absolute residuals; center uncertainty must propagate |
| S[h,N] | Relative scale movement and forward maximum | Needs joint median/MAD regularity and uniform prefix control |
| Nine components over selectable N | Heterogeneous simultaneous inference with nonsmooth components and selection | Marginal consistency does not imply joint consistency; dimensionless metrics are not necessarily pivotal |

A **conditional algebraic derivation**, not an adopted StockScope theorem, identifies the MAD requirements. At continuous F with median m, MAD d>0, f(m)>0 and f(m+d)+f(m-d)>0:

~~~text
m'_F[g] = -g(m)/f(m)

d'_F[g] =
 -{g(m+d)-g(m-d) + [f(m+d)-f(m-d)] m'_F[g]}
 /[f(m+d)+f(m-d)].
~~~

These expressions follow by differentiating F(m)=1/2 and F(m+d)-F(m-d)=1/2. Freezing the center omits the second term. Applying this derivative to dependent sequential data additionally requires a process theorem and uniform remainders. Relevant robust-statistic background is [Falk (1997)](https://doi.org/10.1016/S0167-7152(96)00199-X) and [Liu, Liu and Hu](https://arxiv.org/pdf/1802.10302); the latter explicitly starts from iid sampling.

Decimal storage proves neither a continuous nor an atomic population law. Rounded measurements can create ties; code supplies no positive-density guarantee. For a fixed discrete measurement law, the continuous-density route is inapplicable without a separate argument. Adding jitter/smoothing would introduce a model and tuning choice.

### Inference target and endpoints

The stored finite-path envelopes are deterministic, exactly measured summaries conditional on observed data. Their “uncertainty” must specify repeated-sample variation, a population stability parameter or a future-path prediction bound. Those are different coverage claims. Failure to reject a stationarity null is not proof of acceptable movement.

For a sequential empirical process A_M(s,x), nested differences have the form:

~~~text
sqrt(M) (F_t-F_N) =
 (M/t) A_M(t/M,x) - (M/N) A_M(N/M,x).
~~~

As N/M approaches zero, the weights expose an endpoint problem. Near the final prefix, the future suffix can be tiny. A theorem for fixed interior fractions cannot silently cover every allowed anchor. No trimming fraction or minimum suffix count is invented here.

## 5. Stationary Bootstrap applicability

[Politis–Romano (1994)](https://doi.org/10.1080/01621459.1994.10476870) introduces geometrically distributed blocks for stationary weakly dependent observations, including confidence-region applications. Its [Hilbert-space companion](https://www3.stat.sinica.edu.tw/statistica/j4n2/j4n25/j4n25.htm) concerns smooth functionals in its stated topology; an L2 result is not automatically a sup-norm result.

[Gonçalves–de Jong (2003)](https://doi.org/10.1016/S0165-1765(03)00192-7) weakens moment conditions in stationary-bootstrap consistency theory. Mean/linear-statistic results under NED are not blanket theorems for indicators, quantiles and forward maxima.

The basic block regime includes increasing expected length and a vanishing block/sample fraction, together with the chosen theorem's dependence, moment and functional conditions. These generic limits neither identify an automatic selector nor prove finite-sample adequacy.

| Actual component | Conditional building-block support / missing step | StockScope applicability verdict |
|---|---|---|
| TAIL forward ECDF sup envelope | A sequential empirical-process theorem plus the correct continuous map could work; no stationary-bootstrap theorem/selector mapping over the full allowed prefix domain established | PLAUSIBLE_BUT_UNPROVEN |
| Normalized median envelope | Regular single-quantile theory does not settle the random denominator, prefix supremum, ties and endpoints | PLAUSIBLE_BUT_UNPROVEN |
| Relative MAD envelope | Joint functional derivative is available conditionally; iid MAD results do not prove this dependent nested envelope | PLAUSIBLE_BUT_UNPROVEN |
| Joint nine-component/common-N procedure | Shared vector resampling is possible; joint root, normalization, tuning and selection validity remain unresolved | PLAUSIBLE_BUT_UNPROVEN |
| Direct iid/independent-sample substitution | Discards actual nesting and temporal structure | NOT_APPLICABLE |

No exact component is DIRECTLY_JUSTIFIED. JUSTIFIED_BY_GENERAL_FUNCTIONAL_THEORY would require an explicit applicable process theorem, topology, map and satisfied hypotheses. Invoking the delta method alone is insufficient. **PLAUSIBLE_BUT_UNPROVEN is not admissible for execution.**

Nonsmoothness is not proof of impossibility. [Fang–Santos](https://doi.org/10.1093/restud/rdy049) explains why ordinary centered plug-in bootstrap reasoning can fail for merely directionally differentiable maps. This motivates an explicit process-level root or another proved construction, not unproved percentile intervals of recomputed maxima.

## 6. Alternative dependence-method comparison

Automatic below means available for the **published target**. The last column always assesses the complete StockScope target.

| Method | Target statistic class | Required assumptions | Automatic rule exists | Manual tuning required | New free parameters | Consistency evidence | Optimality evidence | Joint-statistic compatibility | StockScope applicability verdict |
|---|---|---|---|---|---|---|---|---|---|
| Stationary bootstrap + corrected Politis–White | Long-run variance / mean or regular smooth statistic | Stationarity, short-range dependence, covariance/moment regularity, nondegeneracy | Yes, variance objective | No hand-set length after algorithm fixed; conventions still need freezing | Pilot cutoff, cap/rounding/degenerate handling, numerical controls | Published for stated class | Variance MSE | Shared vector resampling possible; scalar selector is not a joint proof | PLAUSIBLE_BUT_UNPROVEN |
| Moving-block bootstrap + HHJ/NPPI | Smooth function of means; specified variance/distribution target | Stationary mixing, smoothness/moments, block/subsample rates | Yes, target-specific procedures | Pilot/subsample/delete-block rules remain | Pilot, subsample size, search range, loss, numerical controls | Within smooth-function setting | MSE selector convergence | Needs joint target and multivariate extension | PLAUSIBLE_BUT_UNPROVEN |
| Circular block bootstrap + corrected variance selector | Mean/variance; separate regular-quantile results | Stationarity, suitable mixing/marginal regularity, block rates | Yes for variance; no reviewed full-envelope rule | Conventions must be fixed | Selector controls, wrap convention | Mean/regular quantile theory, not complete target | Variance MSE | Wrapping does not solve joint inference | PLAUSIBLE_BUT_UNPROVEN |
| Subsampling with block calibration | General statistic with suitable limiting law/rate | Appropriate weak dependence, limit continuity; b grows, b/n vanishes in small-b theory | Data-dependent approaches exist | Calibration/pilot/rate choices remain | Search set, loss, root scaling, calibration controls | Broad conditional theory | Purpose-specific | Vector possible if joint law/scaling established | PLAUSIBLE_BUT_UNPROVEN |
| Quantile-specific hybrid block bootstrap | Centered/scaled sample-quantile distribution | Strict stationarity, polynomial strong mixing, positive bounded local density, theorem-specific rates | Empirical block-number/length selection | Grid/pilot/loss/numerical rules remain | Number AND length, pilot, evaluation choices | Quantile-specific | Distribution approximation rate | Not nested median/MAD/sup joint law | PLAUSIBLE_BUT_UNPROVEN |
| Dependent multiplier bootstrap | Sequential multivariate empirical process / copula functionals | Strict stationarity, quantitative strong mixing, valid multipliers/bandwidth, continuity conditions | Covariance-objective bandwidth rule | Kernel/pilot/integration rules remain | Bandwidth, multiplier law, pilot cutoff, integration controls | Sequential-process theorem | Integrated covariance MSE | Promising common driver; MAD/endpoints still need proof | PLAUSIBLE_BUT_UNPROVEN |
| iid bootstrap MAD representations | Median/MAD with estimated center | iid and quantile regularity | No dependence-block selector | Not a dependence solution | A dependence extension adds choices | iid Bahadur representations | No joint-envelope block optimum | Cannot substitute iid residuals | NOT_APPLICABLE |
| Mixing-process modified robust scale | Modified scale under shifts in mean | Paper-specific geometric mixing and continuous marginal regularity | No StockScope-envelope selector established | Model/modification choices remain | Segment/modification/inference choices | Consistency for a different scale object | No reviewed bootstrap optimum here | Not the StockScope joint envelope | PLAUSIBLE_BUT_UNPROVEN |

Primary evidence: [corrected stationary/circular selector](https://public.econ.duke.edu/~ap172/Patton_Politis_White_2009.pdf), [HHJ/NPPI analysis](https://arxiv.org/pdf/1403.3275), [subsampling block choice](https://doi.org/10.1007/978-1-4612-1554-7_9), [quantile study](https://doi.org/10.1093/biomet/asaa075), [sequential multiplier study](https://arxiv.org/pdf/1306.3930), [iid MAD study](https://arxiv.org/pdf/1802.10302), [robust scale under mixing](https://doi.org/10.1080/02331888.2025.2600463).

No alternative is activated as an outcome-driven fallback.

## 7. Automatic block-selection review

### Objective matching

[Politis–White (2004)](https://doi.org/10.1081/ETC-120028836) estimates optimal block size using lag-window quantities. The [2009 correction](https://doi.org/10.1080/07474930802459016) changes the stationary-bootstrap variance constant and selector. The objective is variance-estimation MSE, not joint critical-value or coverage error for T/C/S over N.

StockScope needs dependence of indicator processes across x and of median/MAD influence processes, including cross-horizon covariance. A raw-yield-change correlogram need not capture those. Applying a scalar selector per horizon, then taking the largest length, is not a joint validity proof.

[Nordman–Lahiri](https://arxiv.org/pdf/1403.3275) studies HHJ/NPPI selector convergence for smooth-function variance estimation. Its Conditions D, Mr and S include three-times continuous differentiability, strong-mixing/moment summability and nondegenerate covariance constants. The sup/quantile envelope is not directly a smooth H of a fixed-dimensional mean. An influence approximation still needs uniform remainders before transferring a higher-order optimum.

[Kuffner–Lee–Young](https://doi.org/10.1093/biomet/asaa075) selects both block number and length for sample-quantile distribution approximation. This is stronger evidence for a regular median than a mean selector, but not a proof for estimated-center MAD, ratios or nested maxima. The inspected [author manuscript](https://arxiv.org/pdf/1710.02537), section 2/Theorem 1, assumes strict stationarity, polynomial strong mixing with exponent greater than five in its finite-exponent case, and positive bounded density near the quantile. Detailed rates are manuscript-specific; identity with every final-journal rate is not asserted.

### Empirical-process selector and common procedure

[Bücher–Kojadinovic](https://arxiv.org/pdf/1306.3930), section 5.1, targets integrated MSE of an empirical-process covariance kernel. This is relevant but not a proved optimum for StockScope's joint maximum. A valid consistency argument could suffice without optimality; it still needs the full process/map/selected-bandwidth chain.

Asymptotic admissibility, selector consistency and optimality are separate claims. A deterministic formula may be outcome-independent without justifying the target. No arbitrary exponent/constant is introduced here.

A common procedure should be investigated first: one synchronized multivariate path or shared multiplier path across horizons, preserving nesting and recomputing median and MAD. Date/availability alignment must be explicit; equal prior counts do not prove equal calendar dates. This is a proof target, not an adopted algorithm.

Separate TAIL/MAD selectors add multiple losses, pilots, method choices, coupling and length-reconciliation rules. Independent resampling loses cross-component dependence. A max/average of lengths also needs justification. None is run.

The evidence implementation's _SuffixEnvelope.block_size is a **computational decomposition size for exact arithmetic**, not a dependence-block length. It provides no statistical tuning rule.

## 8. Dependence-assumption governance

| Assumption / fact | Meaning | Verdict |
|---|---|---|
| Chronological strictly-prior references and overlapping horizons | Code invariants motivate dependence-aware inference; specify no mixing rate | PROJECT_GUARANTEED |
| Strict stationarity of joint available features | All finite-dimensional laws invariant to time shift | UNVERIFIABLE_BUT_EXPLICIT_MODEL_ASSUMPTION |
| Weak/covariance stationarity | Constant means and lag-dependent covariance; insufficient alone for indicator/quantile process results | UNVERIFIABLE_BUT_EXPLICIT_MODEL_ASSUMPTION |
| Quantitative alpha/strong mixing | The theorem needs particular decay/summability, not the label “weak dependence” | UNVERIFIABLE_BUT_EXPLICIT_MODEL_ASSUMPTION |
| Near-epoch dependence | Underlying mixing process, approximation rates and moments required; discontinuous indicators need their own transfer argument | UNVERIFIABLE_BUT_EXPLICIT_MODEL_ASSUMPTION |
| Absolute regularity / physical or functional dependence | Possible alternatives only with an exact applicable theorem and transformation conditions | UNVERIFIABLE_BUT_EXPLICIT_MODEL_ASSUMPTION |
| Unique quantiles, local densities, positive long-run scales | Not established by observed positive MAD or Decimal arithmetic | UNVERIFIABLE_BUT_EXPLICIT_MODEL_ASSUMPTION |
| Independent nested references / independent horizon samples | Conflicts with construction | INCOMPATIBLE |

No assumption is DOMAIN_JUSTIFIED merely because these are financial series. No new diagnostics were run, so no new EMPIRICALLY_COMPATIBLE_ONLY finding is claimed.

The inspected [sequential multiplier theorem](https://arxiv.org/pdf/1306.3930), Theorem 2.1, illustrates required precision: strict stationarity, alpha(r)=O(r^-a) with a>3+3d/2, bandwidth O(n^(1/2-epsilon)), and stated multiplier conditions. These are that theorem's conditions, not stationary-bootstrap assumptions by substitution.

Future diagnostics can reveal incompatibility or support empirical compatibility; one realization cannot prove a mixing rate or stationarity. Diagnostic failure must block execution, not trigger favorable retuning. Differencing and 10-observation overlap do not establish that all dependence ends after 10 observations.

## 9. Joint multiplicity review

There are **nine required scalar metric families per N**: three TAIL, three normalized centers and three relative scales. Six stored reference families are not nine inferential components.

| Procedure | Dependence handling | Preconditions / disposition |
|---|---|---|
| Single-step standardized maximum | Shared resampling captures dependence | Consistent joint root, justified scales, critical-value continuity/tie handling; research candidate only |
| Stepdown resampling | Joint subset resampling can control FWER | Valid subset critical values and defined hypotheses; cannot drop required components |
| Simultaneous component-wise confidence region | Retains metric units within one coverage event | Appropriate structure if joint coverage and estimand proved |
| Bonferroni/Holm from valid marginals | Independence not required; adjusted allocation is not independent per-component alpha | Does not repair invalid marginal inference or determine numeric alpha |

[Romano–Wolf (2005)](https://doi.org/10.1111/j.1468-0262.2005.00615.x) supports resampling-based joint control and studentization subject to underlying approximation validity. No procedure is ranked by number of passing StockScope N values.

Every later t is already inside the envelope; **N selection must also be protected**. Pointwise nine-component coverage at each N does not protect the minimum passing N. The support list is inherited from data-derived B.1 overlays. Treating its realized values as exogenous requires justification. A simultaneous result over a deterministic containing prefix set or a proved selection-aware method could address this; neither is frozen.

Adequacy needs a claim about excessive movement, not just failure to reject stationarity. Intersection-union logic for one prespecified N does not authorize relaxing R2.3's simultaneous scope or ignoring N selection.

## 10. Heterogeneous-statistic normalization

A maximum of raw TAIL, normalized median and relative MAD values is forbidden. Dimensionless does not mean statistically comparable.

| Structure | Potential role | Remaining obligation |
|---|---|---|
| Studentized roots | Scale errors by their sampling uncertainty | Consistent positive standard errors; density/bandwidth/zero-variance rules |
| Deterministic standardization | Define a joint region with fixed scales | Independent scale justification, not favorable post-outcome weights |
| Pivotal transformation / valid p-values | Remove nuisance scale if proved | Dependence, ties, nuisance estimation and joint calibration |
| Component-wise simultaneous upper bounds | Preserve metric-specific interpretation | One joint coverage event and independent acceptance budgets |

The clearest research target is simultaneous upper bounds for **explicitly defined** targets theta[j,N]:

~~~text
P(all required j and selectable N: theta[j,N] <= U[j,N]) >= 1-alpha

Future pass at N requires:
all U[j,N] <= delta[j]
AND all computability / suffix / lineage conditions.
~~~

This is a specification shape, not an implemented inference method. Alpha and delta remain null. The finite-path observed envelope must not be called theta without defining the inferential target.

Division by anchor MAD normalizes the **effect metric**, not its sampling uncertainty. Data-estimated standard errors are possible under a frozen valid procedure; scales adjusted to make N pass are forbidden. Division by acceptance budgets is unavailable while they are null.

## 11. Internal pre-existing risk-budget search

### Scope and reproducibility

Scoped searches covered tracked governance/specification Markdown across the repository: root WORKSPEC/README/IMPLEMENTATION/RESEARCH, docs, output, and tools/data/README.md, plus relevant backend/app source contracts/constants. Terms included Macro, Risk, Strategy, validation, simulation, scanner, confidence, capital, tolerance, error/risk budget, family-wise, coverage error, allowed drift and Korean equivalents. Runtime/data payloads and Holdout-named paths were excluded from content searches.

Representative commands used git grep on the verified origin/main revision and git log -1 --format='%H %aI' for explicit paths. This negative finding is bounded by the inspected repository/sources; it is not proof that no outside organizational requirement exists.

Dates below are recorded Git author dates in KST, not policy-approval dates.

| Document / code path | Commit / date | Original purpose and number/status | Reference Adequacy linkage |
|---|---|---|---|
| docs/risk-engine-v0.10.md | 709cd3241d4e76191d69e7d301050082b4dfd57d; 2026-09-08 | R:R 1.0/2.0; 12% stop-width classification | Price-risk geometry, not ECDF movement or inference error; reject |
| docs/backtest-problem-solver-v0.19.2.md | 255c8ca222ba2b62baf1e372d207b9380be78684; 2026-09-10 | Trade-count bands 10/30/60; improvement screens 30/20 trades, PF 1.2, 0.75 percentage-point gain | Explicit UX guardrails, not statistical significance; reject |
| backend/app/backtest/audit.py | Same 255c8ca...; 2026-09-10 | TOLERANCE_PCT=0.0002, numeric equality comparison | Arithmetic tolerance, not acceptable distribution movement; reject |
| docs/exit-policy-validation-runner-v0.21.4-B.1.1.md | a938d9d57378654dcf90bc386980eab5d830b9f0; 2026-09-15 | Default 90% local coverage, 60-day warmup | Availability/warmup, not confidence or adequacy suffix; reject |
| docs/scanner-candidate-ranking-v0.21.3.md | Same a938d9d...; 2026-09-15 | Three-year historical context; NEAR_READY condition count | Ranking explicitly not future probability; no budget |
| README_SIM0.md | af747bad3d306ec0a6b9a0b1f8c794a8c9ae65b5; 2026-09-21 | Immutable scanner baseline/version | Reproducibility, not numeric statistical reliability |
| README_TRACK110_SIMVAL01.md | 511d2d933c99f51848d58d9c31a21cec06ccfc09; 2026-09-21 | DRAFT validation catalog | Workflow, not inferential approval |
| docs/StockScope_MASTER_ARCHITECTURE_vNext.md and docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md | af62172f0403d112707b84b767b43872092f2153; 2026-09-27 | Evaluation/approval versioning; sample and promotion thresholds unresolved | Relevant governance, no number |
| docs/StockScope_JEV_INTEGRATION_CONCEPT.md | ca71348762e44a611cd495d3d92d5d2f4b6dd737; 2026-09-28 | Confidence meaning/support unverified; boundaries/weights unset | No calibrated error requirement |
| docs/StockScope_NEXT6_MACRO_EVENT_ARCHITECTURE_DESIGN_2026-09-29.md | 30f08a7adf185394f46ce5d6e8b2533dba6c4899; 2026-09-29 | Precommit evaluation, dependence and allowed deterioration; numbers unset | Relevant process, no metric-linked budget |
| docs/StockScope_CAPITAL_AWARE_RECOMMENDATION_DESIGN_2026-09-29.md | 11ab4959eb88d1f04c0971f6e86d2c0c44a854ed; 2026-09-29 | Loss/concentration/sizing unresolved; suitability 55 is existing code | risk_pct is entry-to-stop distance, not account/statistical risk; reject |

These are PREEXISTING_PROJECT_REQUIREMENT **candidates under the recorded Git chronology**. None qualifies as an independent Reference Adequacy numeric requirement. Chronology limits are explicit in section 13.

Other backtest/scanner equality tolerances and empirical quartile screens concern computational precision or data-derived application rules. Age and the word “Risk” do not establish budget equivalence. No numeric budget was adopted from Strategy, Risk Gate, validation, simulation, scanner reliability, prediction/confidence or capital design.

## 12. External/domain requirement search

| Domain / source | Actual scope | StockScope inference budget | StockScope movement budget |
|---|---|---|---|
| Official model-risk guidance | Model governance proportionate to use and organizational risk | No project-specific alpha | No tolerance for these metrics |
| Basel market-risk backtesting / P&L attribution | Trading-desk/portfolio testing and capital treatment | Different claims and targets | Even a P&L ECDF distance has different objects/consequences |
| NIST statistical process control | Chart design and false alarms | Assumption/design-dependent | Control limits are not permitted reference movement |
| Time-series resampling | Sampling-law approximation | Requires an externally chosen error level | Does not determine operational acceptance |
| Empirical-distribution inequalities | Estimation/test guarantees under sampling assumptions | No project alpha; iid bounds not directly applicable | No operational delta |
| Robust-statistic validation | Median/scale sampling properties | No prescribed project budget | No justified 1 MAD or 0.5 MAD convention |

The current official US guidance checked is [SR 26-2, April 17, 2026](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm), explicitly superseding SR 11-7 and SR 21-8. The [revised guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) emphasizes risk-specific practice, not a universal enforceable tolerance table. This review does not assert that StockScope is a regulated bank.

[Basel MAR32](https://www.bis.org/basel_framework/chapter/MAR/32.htm?inforce=20230101&published=20200327&tldate=20200824) concerns VaR backtesting and P&L attribution. Percentiles/sample requirements cannot become Reference Adequacy confidence/support limits because both topics involve finance. The link identifies the published chapter version, not a legal applicability determination.

[NIST guidance](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm) shows chart rules affect false alarms; it supplies no StockScope maximum shift. [Subsampling](https://doi.org/10.1007/978-1-4612-1554-7_9) and [MAD theory](https://doi.org/10.1016/S0167-7152(96)00199-X) answer sampling questions, not acceptance preferences.

R2.2's [Massart DKW citation](https://doi.org/10.1214/aop/1176990746) is retained only as background to its frozen iid/non-nested rejection. No new DKW formula is adopted. No blog, rule of thumb, conventional 95%/99% or simulation outcome supplies policy authority.

## 13. Provenance cutoff analysis

| Event | Commit | Recorded KST time |
|---|---|---|
| R2 blocker design review | 56fd32d85de58a5faf63a75093fa2e686395d893 | 2026-09-30 22:06:19 |
| R2.1 boundary-anchored evidence implementation | 32f27a5e6a410de2ea2ba6c4882538e46e0cb96e | 2026-09-30 23:51:24 |
| Compact R2.1 migration | f2bd6ff0141f6c7de0ac281da1fc26cea1c450f4 | 2026-10-01 05:58:16 |
| R2.2 | a8d0e4fdfb5923a4cd6a83195b00bececf298650 | 2026-10-01 07:34:24 |
| R2.3 | 16a8a5d16a1ebc0c7234dac12f667c3d7a11b572 | 2026-10-01 07:44:07 |

**A merge timestamp does not establish the exact first R2.1 Development generation/exposure time.** No runtime generation timestamp is fabricated. Git chronology shows committed requirements, but cannot exclude earlier off-branch exposure.

- September 8–29 requirements are pre-existing candidates relative to recorded implementation; all fail scope/metric linkage anyway. None is admitted by chronology alone.
- Any numeric proposal first created after actual R2.1 exposure, including one in R2.2/R2.3/R2.4, is POST_EVIDENCE_PROPOSAL and cannot be relabeled pre-existing.
- R2.2/R2.3 constrain governance; they do not supply independent numbers. Compact re-encoding does not reset the cutoff.
- An external source's older publication date proves availability, not pre-evidence StockScope adoption.
- A future PREEXISTING_PROJECT_REQUIREMENT claim needs immutable original content, purpose, authority and proof that it preceded actual generation/exposure. Uncertain provenance fails closed.
- A newly designed operational policy must disclose its post-evidence origin and obtain a separately authorized independence/evaluation plan. Calling it preregistered cannot satisfy this cutoff.

The missing exact generation timestamp cannot reverse U2: no candidate with valid metric linkage was found even under the more permissive recorded chronology.

## 14. Inference error budget verdict

~~~text
INFERENCE_ERROR_BUDGET.status = UNJUSTIFIED
INFERENCE_ERROR_BUDGET.value = null
INFERENCE_ERROR_BUDGET.source = NONE
scope = ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY
selection_scope = must account for allowed common-N search
~~~

FWER/coverage theory gives guarantees **indexed by alpha**. It does not choose StockScope's acceptable false-adequacy probability. Regulatory percentiles, UX confidence labels, floating-point tolerances and missing-data coverage are different quantities.

Monte Carlo approximation error is another budget, not a substitute. No resample count or convergence threshold is selected.

## 15. Movement acceptance budget verdict

~~~text
MOVEMENT_ACCEPTANCE_BUDGET.status = UNJUSTIFIED
TAIL_ECDF_MOVEMENT = null
NORMALIZED_MEDIAN_MOVEMENT = null
RELATIVE_MAD_MOVEMENT = null
source = NONE
~~~

TAIL distance bounds fixed-threshold tail-probability movement, but no permitted amount is specified.

An original algebraic linkage illustrates what robust-score policy would need. Set c=(m_t-m_N)/d_N, s=(d_t-d_N)/d_N:

~~~text
z_N = (x-m_N)/d_N
z_t = (z_N-c)/(1+s)

If |c| <= a and |s| <= b < 1:
|z_t-z_N| <= (a+b|z_N|)/(1-b).
~~~

The missing independent inputs are acceptable score error, a justified domain for |z_N| and permitted scale change. With unbounded |z_N|, a nonzero relative-scale budget alone gives no uniform finite score-error bound. No a, b or score range is chosen. Candidate thresholds/survival cannot manufacture them.

Confidence does not generate movement tolerance; movement tolerance does not generate coverage.

## 16. U1 verdict

**METHOD_NOT_JUSTIFIED**

The complete method still lacks:

1. An explicit estimand, root and coverage event.
2. A sequential joint argument covering nesting, quantile/MAD regularity and ties, random anchor scale and allowed endpoints.
3. Valid normalization and common-N selection protection, including data-derived support points.
4. An exact automatic dependence rule justified for that full procedure.

No exact component rises above PLAUSIBLE_BUT_UNPROVEN, which is inadmissible for execution. Building-block theory remains useful. This is not an impossibility result and does not replace the frozen primary candidate.

## 17. U2 verdict

**NO_INDEPENDENT_RISK_BUDGET**

Neither inference nor movement budget is justified. Older internal numbers fail metric/scope linkage. External requirements govern other objects/consequences. Post-evidence proposals cannot become pre-existing requirements. INFERENCE_BUDGET_ONLY would also overstate the result.

## 18. Combined verdict

**NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY**

| Requirement | Ready? |
|---|---|
| Complete dependence/inference procedure | NO |
| Exact automatic tuning | NO |
| Executable joint handling / normalization | NO |
| Independent inference budget | NO |
| Independent movement budgets | NO |
| Execution preregistration | NO |

R2.5 Development evaluation and minimum-N selection remain blocked. Documentation completion and CI success do not approve statistical policy.

## 19. Fail-closed state

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

Only this Markdown document is added. Backend, frontend, runtime, sync script, scanner version, Strategy, Holdings, Risk Gate and Production behavior remain unchanged.

Required integration checks are Frontend / Node 22, Backend / Python 3.11 and Backend / Python 3.14 on the final PR head. Squash merge requires all three PASS. PR/job URLs and the resulting main SHA belong in the delivery report; the final commit cannot contain its own resulting hash.

## 20. Exact next task

**NEXT-6B-S4.2-B.1.6-R2.4.1 — Joint Sequential Inference Proof & Independent Budget Provenance Closure**

Proposed review-only follow-up, **not R2.5 Development Evaluation**:

1. Define the inferential target and adequacy claim; distinguish finite-path description, population inference and future prediction.
2. Map one common joint procedure to a theorem, including prefixes/endpoints, quantile/MAD regularity, measurement ties, missingness/alignment and support selection. Report any domain conflict; do not silently trim anchors or add K.
3. Specify/justify the exact automatic selector, normalization and remaining pilot/kernel/numerical choices, including deterministic failure rules. Separate consistency from optimality.
4. Supply independently applicable inference and movement budgets with immutable provenance predating actual R2.1 exposure when claimed as pre-existing. If none exists, retain the block; new authorization cannot masquerade as old evidence.
5. Only when U1 and U2 close, prepare a new execution preregistration with reproducible numerical controls. Only EXECUTION_PREREGISTRATION_READY can unlock later R2.5 Development evaluation.

No implementation, N selection or Holdout access belongs in that follow-up review.

## Source register

Primary sources checked on 2026-10-01. Abstracts support only their stated scope; inspected manuscripts are identified. Failed publisher retrieval is not represented as full-text verification.

| ID | Citation / official source | Access / use |
|---|---|---|
| S1 | Politis & Romano (1994), The Stationary Bootstrap, JASA 89:1303–1313. [DOI](https://doi.org/10.1080/01621459.1994.10476870); [university-hosted paper](https://www.ssc.wisc.edu/~bhansen/718/Politis%20Romano.pdf) | Candidate method, not exact-target proof |
| S2 | Politis & Romano (1994), Limit Theorems for Weakly Dependent Hilbert Space Valued Random Variables with Application to the Stationary Bootstrap, Statistica Sinica 4:461–476. [Journal](https://www3.stat.sinica.edu.tw/statistica/j4n2/j4n25/j4n25.htm) | Journal abstract; topology limitation |
| S3 | Gonçalves & de Jong (2003), Consistency of the stationary bootstrap under weak moment conditions, Economics Letters 81:273–278. [DOI](https://doi.org/10.1016/S0165-1765(03)00192-7) | Moment/dependence context; no sup/quantile theorem transferred |
| S4 | Politis & White (2004), Automatic Block-Length Selection for the Dependent Bootstrap, Econometric Reviews 23:53–70. [DOI](https://doi.org/10.1081/ETC-120028836) | Published target; S5/S6 corroborate variance objective |
| S5 | Patton, Politis & White (2009), correction, Econometric Reviews 28:372–375. [DOI](https://doi.org/10.1080/07474930802459016); [author PDF](https://public.econ.duke.edu/~ap172/Patton_Politis_White_2009.pdf) | Corrected formulation inspected |
| S6 | Nordman & Lahiri, Convergence rates of empirical block length selectors for block bootstrap. [Author paper](https://arxiv.org/pdf/1403.3275) | Smooth-function objective and Conditions D/Mr/S inspected |
| S7 | Kuffner, Lee & Young (2021), Block bootstrap optimality and empirical block selection for sample quantiles with dependent data, Biometrika 108:675–692. [DOI](https://doi.org/10.1093/biomet/asaa075); [author manuscript](https://arxiv.org/pdf/1710.02537); [university record](https://profiles.wustl.edu/en/publications/block-bootstrap-optimality-and-empirical-block-selection-for-samp/) | Published identity verified; detailed assumptions read in earlier manuscript |
| S8 | Bücher & Kojadinovic, A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing. [Author paper](https://arxiv.org/pdf/1306.3930) | Theorem 2.1, Corollary 2.2, section 5.1 inspected; distinct method |
| S9 | Politis, Romano & Wolf (1999), Subsampling, chapter 9: Choice of the Block Size, pp.188–212. [DOI](https://doi.org/10.1007/978-1-4612-1554-7_9) | Publisher chapter summary; no universal finite-sample rule |
| S10 | Falk (1997), Asymptotic independence of median and MAD, Statistics & Probability Letters 34:341–345. [DOI](https://doi.org/10.1016/S0167-7152(96)00199-X) | Robust-statistic background; no independence claim for StockScope |
| S11 | Liu, Liu & Hu, Bahadur representations for the bootstrap median absolute deviation and the application to projection depth weighted mean. [Manuscript](https://arxiv.org/pdf/1802.10302); [published DOI](https://doi.org/10.1007/s00184-024-00958-0) | iid setting and estimated-center construction inspected |
| S12 | Robust scale estimation for strongly mixing processes under shifts in the mean. [Publisher DOI](https://doi.org/10.1080/02331888.2025.2600463) | Publisher-indexed model/consistency description only; no full bootstrap theorem claimed |
| S13 | Fang & Santos (2019), Inference on Directionally Differentiable Functions, Review of Economic Studies 86:377–412. [DOI](https://doi.org/10.1093/restud/rdy049) | Nonsmooth plug-in caveat |
| S14 | Romano & Wolf (2005), Stepwise Multiple Testing as Formalized Data Snooping, Econometrica 73:1237–1282. [DOI](https://doi.org/10.1111/j.1468-0262.2005.00615.x) | Joint control/studentization, not project critical values |
| S15 | Federal Reserve/OCC/FDIC (2026), Revised Guidance on Model Risk Management, SR 26-2. [Letter](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm); [guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) | Current official guidance; SR 11-7 superseded |
| S16 | Basel MAR32, Internal models approach: backtesting and P&L attribution test requirements. [Identified official version](https://www.bis.org/basel_framework/chapter/MAR/32.htm?inforce=20230101&published=20200327&tldate=20200824) | Regulatory scope mismatch |
| S17 | NIST/SEMATECH e-Handbook, What are Variables Control Charts? [Official page](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm) | Chart assumptions/false alarms |
| S18 | Massart (1990), The Tight Constant in the Dvoretzky–Kiefer–Wolfowitz Inequality, Annals of Probability 18:1269–1283. [DOI](https://doi.org/10.1214/aop/1176990746) | Background from frozen R2.2; fresh full-text verification not claimed |
