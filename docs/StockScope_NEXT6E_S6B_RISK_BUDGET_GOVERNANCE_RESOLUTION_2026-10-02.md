# StockScope NEXT-6E-S6B — Risk-Budget Governance Resolution

## 1. Status / Baseline

- Date: 2026-10-02, Asia/Seoul.
- Stage: NEXT-6E-S6B Risk-Budget Governance Resolution.
- Artifact: source-only governance / product-risk requirement research result.
- Research base: `c3eb5c3d5610af1f09f0715b27fed0c9210a2005`.
- Architecture baseline: `StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md`.
- S6A baseline: `StockScope_NEXT6E_S6A_METHOD_CONTRACT_RESOLUTION_2026-10-02.md`.
- Current V3: `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`.
- Backend / Frontend / DB / Migration / Runtime / V3 / V4 changes: NONE.
- Holdout access: NONE.
- Production impact: NONE.

Final disposition:

```text
NEXT-6E-S6B = COMPLETE

Policy state = POLICY_DESIGNED
G-B = BLOCKED

Product purpose = ACCEPTED_FOR_GOVERNANCE_DESIGN
Harm model = DESIGNED
Metric semantics = DESIGNED

τ_T = null / UNRESOLVED
τ_L = null / UNRESOLVED
τ_S = null / UNRESOLVED
α_stat = null / TARGET_AND_AUTHORITY_DEPENDENT
γ_repeat = null / REDEFINE_AFTER_METHOD_TARGET
δ_MC = null / OUT_OF_SCOPE_S6C

Existing project requirement = NONE_IN_APPROVED_SCOPE
Applicable external numeric requirement = NONE_IN_REVIEWED_SCOPE
Approval authority = NOT_APPOINTED
Synthetic / analytical sensitivity evidence = REQUIRED_FOR_NUMERIC_POLICY_PROPOSAL
Reference Adequacy = UNRESOLVED
```

No current Development adequacy result, forward envelope value, passing N, survival metric, covered-year count, current evidence distribution, per-horizon adequacy result, Production outcome, holdings result, recommendation result, or broker activity was used. No bootstrap, simulation, synthetic experiment, statistics execution, diagnostics, runtime DB access, runtime artifact read/write, migration, or evaluator was run.

Holdout remained locked and was not read, searched, enumerated, existence-probed, hashed, counted, or inspected for dates/metadata.

## 2. S6A Interface State

S6A ended with:

```text
Method state = METHOD_DESIGNED
G-A = BLOCKED
Target = TARGET_REQUIRES_REVISION
Representation = REPRESENTATION_CONDITIONALLY_ACCEPTED
Automatic selector = SELECTOR_UNRESOLVED
Joint inference = UNRESOLVED
All-N/common-N = UNRESOLVED
```

Therefore S6B cannot assume the Architecture's original law-level target `G_R(P)` / `C_stat(D)` or `γ_repeat` definition will survive unchanged.

Policy entries are classified as:
- METHOD_INTERFACE_DEPENDENT
- TARGET_AND_METHOD_DEPENDENT
- TARGET_DEPENDENT
- NUMERICAL_LEDGER_ONLY

No value may be approved against an obsolete or unstable target identity.

## 3. Product Purpose and Harm Model

Reference Adequacy exists to prevent unsupported reuse of an expanding empirical reference under unchanged calibration/research semantics when probability, robust location, or robust scale characteristics have moved beyond an independently approved boundary.

This is an internal research/governance purpose. It is not a claim that a given amount of reference movement directly causes trading loss or financial loss.

Harm chain:

```text
reference property changes
→ probability/location/scale interpretation changes
→ prior reference-reuse assumption may no longer mean the same thing
→ continued reuse becomes insufficiently justified
→ future internal research decisions may rely on an invalidated reference assumption
```

Metric-specific harm semantics:
- TAIL: ECDF movement can change empirical event-probability interpretation.
- Normalized median: robust center can move materially relative to prior robust scale.
- Relative MAD: robust dispersion can move materially relative to prior scale.

No mapping from a specific movement amount to a monetary, Strategy, Scanner, Holdings, or Production loss is established.

## 4. Metric Semantics

### τ_T

```text
metric = ECDF_SUP_DISTANCE
unit = absolute probability difference
domain = [0,1]
policy meaning = maximum operationally acceptable movement for reuse of the declared empirical probability reference
class = METHOD_INTERFACE_DEPENDENT
value = null
status = UNRESOLVED
```

### τ_L

```text
metric = NORMALIZED_MEDIAN_SHIFT
formula = |median_t - median_N| / |MAD_N|
unit = anchor-MAD units
policy meaning = maximum operationally acceptable robust-location movement for reuse under the same declared reference interpretation
class = METHOD_INTERFACE_DEPENDENT
value = null
status = UNRESOLVED
```

Zero anchor MAD remains non-computable. Policy does not rescue it.

### τ_S

```text
metric = RELATIVE_MAD_SHIFT
formula = |MAD_t - MAD_N| / |MAD_N|
unit = dimensionless relative scale movement
policy meaning = maximum operationally acceptable robust-scale movement
class = METHOD_INTERFACE_DEPENDENT
value = null
status = UNRESOLVED
```

### α_stat

```text
meaning = family-wide risk appetite for false statistical support of Reference Adequacy under the final approved joint procedure
class = TARGET_AND_METHOD_DEPENDENT
value = null
status = UNRESOLVED
```

A general risk appetite is governance-owned, but the exact controlled event depends on the final S6A target/procedure.

### γ_repeat

Architecture proposed a recurrence-risk budget on a fresh/repeat record. S6A found the law-level target requires revision.

```text
class = TARGET_DEPENDENT
disposition = REDEFINE_AFTER_METHOD_TARGET
value = null
status = TARGET_REDEFINITION_REQUIRED
```

The general idea may remain useful, but the old event is not approved.

### δ_MC

```text
class = NUMERICAL_LEDGER_ONLY
owner = S6C numerical contract
value = null
status = OUT_OF_SCOPE_S6B
```

## 5. V3 / Future Policy Boundary

Current V3 contains `ABSOLUTE_MEDIAN_SHIFT`, `ABSOLUTE_MAD_SHIFT`, and `RELATIVE_MAD_SHIFT`. Research intent uses `NORMALIZED_MEDIAN_SHIFT` and `RELATIVE_MAD_SHIFT`.

S6B does not use current observed MAD to convert a future normalized tolerance into a V3 basis-point tolerance. V3 remains `BLOCKED_UNJUSTIFIED_TOLERANCE` with current null fields unchanged.

## 6. Source Hierarchy

Retain provenance categories:

```text
1. EXISTING_PROJECT_REQUIREMENT
2. EXTERNAL_DOMAIN_REQUIREMENT
3. FORMAL_STATISTICAL_ERROR_CONTROL
4. NONE
```

Clarification: source rank never overrides applicability. An inapplicable official rule cannot populate a StockScope metric merely because it is official. Formal statistical error control can implement a chosen error budget; it does not choose an operational movement threshold or risk appetite.

## 7. Existing Project Requirement Review

Approved project sources reviewed:
- R2.3 preregistration
- R2.4 method/risk governance review
- NEXT-6E Reference Adequacy Resolution Architecture
- S6A Method Contract Resolution
- Master Architecture vNext
- Development Roadmap vNext
- Implementation Baseline vNext
- current V3 policy definitions

These sources define validation, preregistration, fail-closed, reproducibility and activation-governance principles. They do not contain an independently approved numeric requirement for `τ_T`, `τ_L`, `τ_S`, `α_stat`, or `γ_repeat` independent from observed Development evidence.

Historical Development-informed values cannot be relabeled as independent requirements.

| Entry | Independent approved value found? | Exact metric match | Approval evidence | Verdict |
| --- | ---: | ---: | ---: | --- |
| τ_T | NO | Concept yes | NO | NO_APPROVED_VALUE |
| τ_L | NO | Concept yes | NO | NO_APPROVED_VALUE |
| τ_S | NO | Concept yes | NO | NO_APPROVED_VALUE |
| α_stat | NO | Target dependent | NO | NO_APPROVED_VALUE |
| γ_repeat | NO | Target requires revision | NO | REDEFINE |
| δ_MC | NO | S6C ledger | NO | OUT_OF_SCOPE |

Result:

```text
EXISTING_PROJECT_REQUIREMENT = NONE_IN_APPROVED_SCOPE
```

## 8. External Governance Review

### 8.1 2026 U.S. interagency Model Risk Management guidance

The Federal Reserve, FDIC and OCC issued revised interagency Model Risk Management guidance on 2026-04-17.

Relevant transferable governance principles:
- model risk management should be tailored to model purpose, use, materiality and organizational risk profile;
- model development begins with a clear statement of purpose;
- validation evaluates reliability, limitations, assumptions, methods and data;
- validation may inform judgments about acceptable performance ranges;
- persistent deviations outside an organization's established performance thresholds may warrant adjustment, recalibration or redevelopment;
- governance benefits from clear roles, accountability, documentation and controls.

The guidance does not prescribe a StockScope ECDF, normalized-median, relative-MAD or family-wide error value.

It is primarily guidance for regulated banking organizations, not a binding StockScope requirement. It is therefore governance evidence, not a direct numeric policy source.

### 8.2 Basel market-risk internal-model standards

Basel MAR30/MAR32/MAR99 include independent validation, backtesting, and explicit numeric rules for specific bank internal-model uses. MAR32 uses 99th-percentile VaR in its regulatory backtesting context, and MAR99 defines exception-zone interpretations.

Those numbers apply to:

```text
bank regulatory capital
VaR coverage
daily P&L backtesting
supervisory exception zones
```

StockScope policy concerns:

```text
ECDF sup movement
normalized median movement
relative MAD movement
internal calibration/reference reuse
```

The objects, units, intended uses and consequences differ. Basel numeric values are not transferable.

### 8.3 External requirement matrix

| Candidate | Official source | Object / use | StockScope applicability | Verdict |
| --- | --- | --- | --- | --- |
| Organization-established model performance thresholds | 2026 Fed/OCC/FDIC guidance | model-specific validation / monitoring | governance principle only | PARTIALLY_APPLICABLE |
| 99% VaR confidence | Basel MAR32 | bank regulatory VaR backtesting | different object/use/unit | NOT_APPLICABLE |
| VaR backtesting zones | Basel MAR99 | supervisory exception counts | different statistic/consequence | NOT_APPLICABLE |
| Independent validation / role separation | Basel MAR30; 2026 guidance | model governance | governance principle | PARTIALLY_APPLICABLE |
| Numeric τ_T / τ_L / τ_S | none identified | StockScope reference reuse | direct source absent | INSUFFICIENT_EVIDENCE |
| Numeric α_stat | none identified | StockScope false-support appetite | final method target unresolved | INSUFFICIENT_EVIDENCE |

Result:

```text
EXTERNAL_DOMAIN_REQUIREMENT = NONE_IN_REVIEWED_SCOPE
```

This is a bounded review, not a universal claim that no external standard could ever exist.

## 9. Formal Statistical Error Control

A formal statistical procedure can control a declared error probability conditional on a valid statistical claim, assumptions, and a chosen level.

It cannot choose the organization's appetite for false support.

Therefore:

```text
formal statistical procedure = mechanism
α_stat value = governance decision
```

A conventional example such as 5% does not create a StockScope requirement.

Result:

```text
FORMAL_STATISTICAL_ERROR_CONTROL = PROCEDURE_SUPPORT_ONLY
```

## 10. Outcome-Independent Analytical / Synthetic Evidence

Because project and external sources do not supply numeric movement thresholds, a future numeric-policy proposal needs an independent evidence path.

Preferred next source:

```text
outcome-independent analytical / fully synthetic sensitivity
```

Questions should include:
- If ECDF sup movement is d, what probability-interpretation change does that permit?
- If normalized median movement is l, what robust-location interpretation changes in prior-scale units?
- If relative MAD movement is s, what robust-scale interpretation changes?

This evidence must characterize product/reference semantics, not optimize current Development outcomes.

Forbidden:
- choose a threshold just above current Development movement;
- choose a value that preserves a desired passing N;
- tune values to Strategy / Production performance;
- grid-search tolerances and select the favorable result.

S6B does not execute a synthetic experiment. It records:

```text
SYNTHETIC_SENSITIVITY_REQUIRED = YES
```

for a future numeric movement-policy proposal unless another independent approved requirement is found.

## 11. Policy Entry Verdicts

### τ_T

```text
value = null
source = NONE
status = UNRESOLVED
verdict = POLICY_ENTRY_DESIGNED / NUMERIC_VALUE_UNJUSTIFIED
```

#### τ_L

```text
value = null
source = NONE
status = UNRESOLVED
verdict = POLICY_ENTRY_DESIGNED / NUMERIC_VALUE_UNJUSTIFIED
```

### τ_S

```text
value = null
source = NONE
status = UNRESOLVED
verdict = POLICY_ENTRY_DESIGNED / NUMERIC_VALUE_UNJUSTIFIED
```

### α_stat

```text
value = null
source = NONE
status = TARGET_AND_AUTHORITY_DEPENDENT
```

The exact false-support event is not stable until Track A finalizes its target and inference construction.

### γ_repeat

```text
value = null
disposition = REDEFINE_AFTER_METHOD_TARGET
status = TARGET_REDEFINITION_REQUIRED
```

### δ_MC

```text
value = null
status = OUT_OF_SCOPE_S6C
```

## 12. RiskBudgetContract / Research Draft

Required fields:

```text
contract_version
contract_id
contract_hash

product_purpose
harm_model_version

policy_entries[]
  policy_entry_id
  policy_version
  metric_id
  metric_contract_version
  value
  unit
  purpose
  harm
  source_category
  source_reference
  applicability_status
  applicability_evidence
  scope
  use
  owner_role
  approval_authority_role
  owner_identity
  approval_authority_identity
  approval_reference
  approval_date
  status
  review_rule
  review_date
  expiry_rule
  expiry
  revocation_rule
  revocation_reference
  limitations

conflicts[]
governance_status
open_blockers[]
```

`value = null` means NO EXECUTABLE POLICY VALUE. It does not mean zero tolerance, infinite tolerance, disabled metric, or a default.

## 13. Policy States

Recommended:

```text
UNRESOLVED
PROPOSED
POLICY_APPROVED
EXPIRED
REVOKED
INVALIDATED
TARGET_REDEFINITION_REQUIRED
```

A merged document cannot create `POLICY_APPROVED`.

Material method/target changes can invalidate an otherwise approved policy if its scope no longer matches.

## 14. Roles / Authority Model

S6B defines roles only; it does not invent incumbents.

### Risk Policy Owner
- owns product purpose and harm model;
- prepares policy proposal and evidence;
- proposes review/revocation.

### Method Reviewer
- checks target, unit, scope and statistical testability;
- cannot create risk appetite merely by reviewing the method.

### Approval Authority
- approves/rejects exact risk appetite and scope;
- evaluates evidence;
- resolves source conflicts;
- approves review/expiry/revocation rules.

### Convergence Reviewer
- used by S6C to verify G-A/G-B and version compatibility.

Current appointments:

```text
Risk Policy Owner incumbent = NOT APPOINTED
Approval Authority incumbent = NOT APPOINTED
Method Reviewer incumbent = NOT FORMALLY APPOINTED BY THIS TASK
Convergence Reviewer incumbent = NOT APPOINTED
```

Codex/AI authorship is not an appointment.

## 15. Approval Workflow

```text
Risk Policy Owner
→ define purpose / harm / metric / source / scope
→ assemble independent evidence
→ Method Reviewer checks target / unit / testability
→ Approval Authority approves or rejects exact version
→ immutable requirement register records the decision
→ S6C verifies compatibility
→ future V4 may reference exact approved IDs
```

If a required entry is not approved, the policy gate remains blocked.

If policy becomes approved while method remains blocked, method blockage still prevents convergence/evaluation.

## 16. Scope, Conflict, Version, Review, Revocation

Every approval must bind:
- reference use;
- metric + version;
- target + version;
- feature family;
- horizon scope;
- selection/candidate-domain scope;
- source/cutoff semantics;
- intended research use.

Policy-source conflict cannot be solved automatically by min/max/average or source rank. It requires applicability analysis and Approval Authority resolution.

A material policy change creates a new version. A failed evaluation may not be relabeled by loosening tolerance and reusing the same decision identity.

No conventional review/expiry interval is adopted. Quarterly, six-month, annual, or other periods require their own governance basis. Missing review/expiry details remain unresolved if required for executable policy.

Revocation is an immutable event. Historical artifacts remain immutable; current usability can be invalidated without rewriting history.

## 17. S6A Interface Reconciliation

Policy entries are classified:

| Entry | S6A dependency |
| --- | --- |
| τ_T | METHOD_INTERFACE_DEPENDENT |
| τ_L | METHOD_INTERFACE_DEPENDENT |
| τ_S | METHOD_INTERFACE_DEPENDENT |
| α_stat | TARGET_AND_METHOD_DEPENDENT |
| γ_repeat | TARGET_REDEFINITION_REQUIRED |
| δ_MC | S6C NUMERICAL LEDGER |

S6B may define movement metric semantics before G-A passes, but no executable policy may claim compatibility until exact method/target IDs are frozen.

## 18. G-B Gate Assessment

| Requirement | State |
| --- | --- |
| Product purpose | ACCEPTED_FOR_GOVERNANCE_DESIGN |
| Harm model | DESIGNED |
| τ_T semantics | DESIGNED |
| τ_L semantics | DESIGNED |
| τ_S semantics | DESIGNED |
| α_stat semantics | DESIGNED / TARGET DEPENDENT |
| γ_repeat semantics | REDEFINITION REQUIRED |
| Existing independent numeric requirement | NONE |
| Applicable external numeric requirement | NONE |
| Independent analytical/synthetic numeric evidence | NOT YET PRODUCED |
| Risk Policy Owner appointed | NO |
| Approval Authority appointed | NO |
| Approved numeric entries | NONE |
| Scope/applicability rules | DESIGNED |
| Conflict handling | DESIGNED |
| Version/revocation structure | DESIGNED |
| RiskBudgetContract | DESIGNED |

Therefore:

```text
G-B = BLOCKED
```

## 19. Policy State

The final state is:

```text
POLICY_DESIGNED
```

not `POLICY_APPROVED`, because the governance structure is now precise but the values, target compatibility, authority appointments and approvals are absent.

Remaining blockers:
1. independent numeric evidence for τ_T / τ_L / τ_S;
2. Track A target compatibility for α_stat;
3. redefinition decision for γ_repeat;
4. role appointments;
5. explicit approval;
6. any required review/expiry details.

## 20. S6C Handoff

```text
Policy state = POLICY_DESIGNED
G-B = BLOCKED

τ_T = null
τ_L = null
τ_S = null
α_stat = null
γ_repeat = null
δ_MC = null / S6C-owned

authority = NOT APPOINTED
independent numeric evidence = NOT AVAILABLE

target compatibility:
  τ_T/τ_L/τ_S = METHOD_INTERFACE_DEPENDENT
  α_stat = TARGET_AND_METHOD_DEPENDENT
  γ_repeat = TARGET_REDEFINITION_REQUIRED

next policy evidence:
  OUTCOME-INDEPENDENT ANALYTICAL/SYNTHETIC SENSITIVITY
  or another independently approved applicable requirement
```

S6C convergence approval must not pass with this state.

## 21. Relationship to Track A

```text
S6A = METHOD_DESIGNED / G-A BLOCKED
S6B = POLICY_DESIGNED / G-B BLOCKED
```

Track A blockers are theorem/target/selector/joint-inference problems.

Track B blockers are independent numeric evidence, target compatibility and authority/approval problems.

Neither can rescue the other.

## 22. Frozen Downstream State

```text
Reference Adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED

V3 changed = NO
V4 created = NO
Evaluator implemed = NO
Development evaluation allowed = NO
Holdout = LOCKED / NOT ACCESSED
Production impact = NONE
```

## 23. Source Register

### Project sources

- `docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md`
- `docs/StockScope_NEXT6E_S6A_METHOD_CONTRACT_RESOLUTION_2026-10-02.md`
- `docs/StockScope_NEXT6B_S4_2B16_R24_METHOD_RISK_GOVERNANCE_2026-10-02.md`
- `docs/StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md`
- `backend/app/macro/reference_adequacy_protocol.py`
- `docs/StockScope_MASTER_ARCHITECTURE_vNext.md`
- `docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md`
- `docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md`

### Official external sources

1. Board of Governors of the Federal Reserve System / FDIC / OCC (2026), Supervisory Guidance on Model Risk Management, April 17, 2026.  
   https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm  
   https://www.federalreserve.gov/supervisionreg/srletters/SR2602a1.pdf

2. OCC Bulletin 2026-13, Model Risk Management: Revised Guidance.  
   https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html

3. Basel Committee on Banking Supervision, MAR30 — Internal models approach: general provisions.  
   https://www.bis.org/committees/bcbs/basel-framework/standard/mar/30/

4. Basel Committee on Banking Supervision, MAR32 — Internal models approach: backtesting and P&L attribution test requirements.  
   https://www.bis.org/committees/bcbs/basel-framework/standard/mar/32/

5. Basel Committee on Banking Supervision, MAR99 — Guidance on use of the internal models approach.  
   https://www.bis.org/committees/bcbs/basel-framework/standard/mar/99/

## 24. Self-Check

```text
Development result used = NO
Development envelope inspected = NO
Passing N used = NO
Production outcome used = NO

Bootstrap executed = NO
Simulation executed = NO
Synthetic experiment executed = NO
Diagnostics executed = NO
Statistical evaluation executed = NO

Holdout read = NO
Holdout existence probe = NO
Holdout search = NO
Holdout metadata/hash/count/date inspection = NO

Observed envelope used for policy = NO
External number copied without applicability proof = NO
Conventional alpha adopted by default = NO

Authority invented = NO
Approval fabricated = NO

τ_T numeric value selected = NO
τ_L numeric value selected = NO
τ_S numeric value selected = NO
α_stat numeric value selected = NO
γ_repeat numeric value selected = NO

V3 changed = NO
V4 created = NO
Backend changes = NONE
Frontend changes = NONE
DB schema changes = NONE
Migration = NONE
Runtime DB access = NONE
Runtime writes = 0
Production impact = NONE
```

## 25. Completion / Handoff

```text
NEXT-6E-S6B COMPLETE

Policy state
POLICY_DESIGNED

G-B
BLOCKED

Product purpose
prevent unsupported reuse of an expanding reference
under unchanged internal calibration/reference semantics

Harm model
reference movement
→ interpretation/normalization change
→ prior reuse assumption may be unsupported
→ internal research-decision risk

τ_T
value = null
source = NONE
status = UNRESOLVED

τ_L
value = null
source = NONE
status = UNRESOLVED

τ_S
value = null
source = NONE
status = UNRESOLVED

α_stat
value = null
source = NONE
status = TARGET_AND_AUTHORITY_DEPENDENT

γ_repeat
disposition = REDEFINE_AFTER_METHOD_TARGET
value = null
status = TARGET_REDEFINITION_REQUIRED

δ_MC
value = null
status = OUT_OF_SCOPE_S6C

Approval authority
NOT APPOINTED

Remaining policy blockers
independent numeric evidence
target compatibility
authority appointment
explicit approval
review/expiry details where required

Development result used
NO

Production outcome used
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

### Next permitted work

Because both independent gates are blocked:

```text
G-A = BLOCKED
G-B = BLOCKED
```

S6C convergence approval cannot begin as an approval task.

Permitted blocker-resolution work:
1. Track A theorem/target resolution focused on the sequential dependent empirical-process / multiplier route and exact median/MAD/all-N transfer.
2. Track B outcome-independent analytical/synthetic sensitivity design/research plus explicit governance-role appointment.

No V4, evaluator, Development evaluation, Holdout, or Production task is permitted.
