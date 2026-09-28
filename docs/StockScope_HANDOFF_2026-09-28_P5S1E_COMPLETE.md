# StockScope Handoff — 2026-09-28 — P5-S1-E Complete

> Purpose: continue the current StockScope implementation in a new ChatGPT conversation without reconstructing context from memory.
>
> Repository: `SkyBluekor/StockScope`
>
> Working branch: `feature/ux-redesign-1`
>
> PR: #8 — **UX-REDESIGN.1: unify data status and recovery flows** — OPEN, mergeable/clean, base `main`
>
> Current verified HEAD: `4e781b577fad9c786d676531ab9d8846b0ab0ba2`
>
> HEAD message: `test: clean scanner baseline verification diagnostics`

---

## 1. Product direction that must not be lost

StockScope is a decision-support system. It must **not place real brokerage buy/sell orders**.

Core product direction:

- internal analysis complexity may grow, but user interaction should shrink;
- “new feature” does not automatically mean “new button”;
- avoid long report-style screens that make the user read everything;
- convert data into concise decision context and explain what changed;
- do not make the user repeatedly click Analyze / Recheck / Validate / Verify for ordinary use;
- Holdings and Watch should help react quickly, but existing user-approved plans must not be silently rewritten;
- Production Strategy changes must follow evidence → proposal → approval → explicit activation;
- the latest Simulation row must never automatically control Production;
- current strategy suitability score is **not a probability of future profit**;
- Risk Gate and NO_TRADE remain safety mechanisms;
- automatic strategy rotation is not part of current P5 completion.

UI principle: avoid stereotypical AI-generated rounded-card dashboards, pastel gradients, repetitive 3-card layouts, excessive badges, and button proliferation. Prefer a restrained, editorial, real-service feel.

---

## 2. Environment / local PC context

The school PC project path is:

```text
D:\Projects\StockScope
```

The virtual environment is:

```text
D:\Projects\StockScope\.venv
```

The user normally works in PowerShell with `.venv` activated.

### Windows backup issue already fixed

The school PC security environment blocked Python directory rename via `os.replace()`.

Original failure:

```text
PermissionError: [WinError 5]
... .tmp -> final backup directory
```

Fix commits:

- `8be5ab1` — `fix: fallback when Windows blocks backup directory rename`
- `a0e8c28` — `test: cover Windows backup publish fallback`

The runtime backup tool now uses a copy-only fallback **only for backup publication** if directory rename is blocked.

Verified successful school-PC backup:

```text
D:\Projects\StockScope\backups\StockScope_20260928T002526Z
```

Important distinction: Production `active.json` policy publication does **not** use copy fallback. If atomic replace is unavailable, activation must fail and preserve the previous active reference.

---

## 3. Local migrations already completed on school PC

The following were successfully applied locally:

### P1-S1
```text
VN-P1-S1 INPUT IDENTITY MIGRATION PASS
market generation_rows: 3004
```

### P1-S2
```text
VN-P1-S2 HORIZON CONTEXT MIGRATION PASS
```

### P2-S1
```text
VN-P2-S1 FEEDBACK MIGRATION PASS
```

### P2-S2
```text
VN-P2-S2 PROSPECTIVE MIGRATION PASS
historical_backfill_performed: False
```

### P3-S1
```text
VN-P3-S1 HOLDING DECISION MIGRATION PASS
position_count: 1
analysis_revision_count: 10
management_plan_count: 0
historical_decision_backfill_performed: False
```

### P3-S2
```text
VN-P3-S2 HOLDING RECOVERY MIGRATION PASS
historical_recovery_backfill_performed: False
```

### P4-S1
```text
VN-P4-S1 WATCH MIGRATION PASS
active_plan_count: 0
historical_watch_backfill_performed: False
production_watch_activation_performed: False
```

### P5 migration status

**P5 migration has NOT been run on the school PC yet.**

This was intentional while A/B/C storage contracts were still evolving.

The current P5 migration command is:

```powershell
.\.venv\Scripts\python.exe .\tools\data\migrate_strategy_governance_vnp5s1.py
```

At the current E-complete state, the P5 Simulation schema is stable enough to run once before F/API/UI work if needed.

Recommended before running P5 locally:

```powershell
.\.venv\Scripts\python.exe .\tools\data\backup_runtime.py
```

---

## 4. Completed roadmap through P4

Official roadmap file:

```text
docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md
```

Architecture file:

```text
docs/StockScope_MASTER_ARCHITECTURE_vNext.md
```

### P3-S1 — Holdings Decision / Management Plan

Completed and browser-UAT'd.

Verified behaviors include:

- first Management Plan apply;
- HOLD decision;
- stale detection;
- same-analysis dedupe;
- quantity-change stale protection;
- stop-loosening conflict;
- backend bypass protection;
- frontend stale refresh.

Safe UAT fixture:

```text
tools/data/prepare_vnp3s1_stop_loosening_fixture.py
```

### P3-S2 — Recovery Review

Recovery is manual review context only.

It does **not**:

- automatically start from loss percentage;
- perform averaging down;
- calculate a “recovery probability”;
- auto-buy or auto-sell;
- loosen stops;
- infer account exposure;
- execute orders.

States include thesis:

```text
INTACT | WEAKENED | BROKEN | UNKNOWN
```

and review action:

```text
UNDECIDED | HOLD | REDUCE | EXIT | ADD_REVIEW
```

`ADD_REVIEW` is review intent only, not permission to buy.

Browser UAT for LVMC Holdings passed manual start → assessment → Decision linkage → manual close.

### P4-S1 — Realtime Watch

Implemented with:

```text
VN_P4_S1_WATCH_V1
VN_P4_S1_WATCH_POLICY_CONTRACT_V1
```

Production policy is intentionally still BLOCKED because confirmation/rearm/freshness thresholds are unresolved.

Watch does not:

- place trades;
- change Management Plan;
- auto-start Recovery.

Watch engine has its own server-side QuoteEventHub consumer; browser SSE is not the watch engine.

---

## 5. P5-S1 overall architecture

P5 official scope:

> Strategy version · change proposal · validation · approval · activation.

Intended lifecycle:

```text
measurement
→ proposal
→ fixed-condition validation
→ approval
→ activation with effective time
→ observation / rollback
```

Current 10 Production strategy names:

```text
trend_following
pullback
breakout
support_bounce
oversold_bounce
range_trading
momentum_continuation
volatility_squeeze
ma20_rebound
trend_recovery
```

`NO_TRADE` is explicitly **not** a Strategy Registry version. It remains a safety result.

Unresolved Q7 items remain unresolved:

- minimum sample size;
- recent/long evaluation windows;
- promotion threshold;
- demotion threshold;
- regime-specific numeric requirements.

Do not invent these numbers.

---

# 6. P5-S1-A — Strategy Registry — COMPLETE

Main file:

```text
backend/app/simulation/strategy_governance.py
```

Important constants:

```text
VN_P5_S1_STRATEGY_GOVERNANCE_V1
VN_P5_S1_STRATEGY_FINGERPRINT_V1
VN_P5_S1_CURRENT_10_BOOTSTRAP_V1
```

Initial current ten strategies are bootstrapped as:

```text
operational_status = OPERATING
validation_status  = UNVERIFIED
```

No fake historical validation backfill is performed.

Registry table:

```text
strategy_registry_version
```

States:

```text
CANDIDATE
OPERATING
ON_HOLD
DEMOTED
```

Validation states:

```text
UNVERIFIED
EVALUATING
VALIDATED
INSUFFICIENT_EVIDENCE
BLOCKED
```

Key safety:

- exactly one OPERATING version per strategy key;
- NO_TRADE excluded;
- implementation drift changes fingerprint;
- migration does not silently register changed implementation.

A-stage commits include:

```text
0de0210 feat: define strategy governance registry fingerprints
7b0f06a feat: add VN-P5-S1 strategy registry migration
3d47c41 test: cover VN-P5-S1 strategy registry bootstrap
```

---

# 7. P5-S1-B — Strategy Evaluation Artifact — COMPLETE

Main file:

```text
backend/app/simulation/strategy_evidence.py
```

Storage:

```text
strategy_evaluation_artifact
```

Supported sources:

```text
FEEDBACK_REPORT
PROSPECTIVE_REPORT
```

Behavior:

- binds immutable P2 evidence to a specific Strategy Version;
- validates Prospective report/run/protocol versions and hashes;
- requires Prospective run COMPLETE;
- extracts only the matching strategy breakdown;
- preserves P2 limitations;
- verifies Feedback source state;
- rejects stale/missing Feedback sources;
- does not merge distinct comparison groups;
- deterministic/idempotent Artifact identity;
- SHA-256 Artifact hash;
- UPDATE/DELETE blocked by DB triggers;
- source can later report CURRENT / SOURCE_CHANGED / SOURCE_MISSING;
- does not change Registry validation or operational status.

P2 safety limitations remain preserved:

```text
minimum_sample_policy_defined = False
performance_conclusion_allowed = False
strategy_promotion_allowed = False
adaptive_rotation_enabled = False
```

Key commits:

```text
3ebea0b feat: add strategy evaluation evidence artifacts
cc6c3a3 feat: add immutable strategy evidence artifact storage
953055c test: cover P2 strategy evidence artifacts
d28b58b fix: harden strategy evidence source contracts
339e326 test: harden strategy evidence safety invariants
```

---

# 8. P5-S1-C — Change Proposal + Approval Artifact — COMPLETE

Main file:

```text
backend/app/simulation/strategy_change.py
```

Storage:

```text
strategy_change_proposal
strategy_change_proposal_evidence
strategy_approval_artifact
```

Proposal captures:

- Registry snapshot hash;
- Strategy definition hashes;
- expected → proposed operational state changes;
- affected Horizon/Regime context;
- Evidence bundle and bundle hash;
- candidate policy intent;
- rollback basis;
- Scanner production baseline identity;
- Approval Protocol version/hash;
- limitations / approval gate state.

Approval is research/validation approval only.

Approval does **not**:

- activate Production;
- change Registry status;
- change Scanner behavior;
- change Holdings.

Default real Production Approval Protocol remains blocked:

```text
activation_eligible = False
q7_precommitted = False
```

Synthetic test protocol is permitted only when explicitly enabled.

Important gate: Proposal creation pins the approval protocol version/hash; a different protocol cannot later approve the old Proposal.

Key commits:

```text
18533df feat: add strategy change proposal and approval contracts
72b5fe9 feat: add strategy proposal and approval storage
b1104b0 fix: pin approval protocol at proposal creation
0ef17e9 fix: persist proposal approval protocol identity
98f8a7a test: cover strategy change proposal approval lifecycle
50b7120 fix: wire proposal approval protocol parameter correctly
5821fbc test: avoid collecting approval protocol fixture helper
```

---

# 9. P5-S1-D — Production Selection Policy + Active/Rollback Publisher — COMPLETE

Main file:

```text
backend/app/strategy/production_selection_policy.py
```

Runtime ownership:

```text
backend/runtime/strategy_selection/
    README.md
    policies/<policy-id>.json   # runtime-generated, gitignored
    active.json                 # runtime-generated, gitignored
```

Core contract:

```text
VN_P5_S1_SELECTION_POLICY_V1
```

Behavior:

- immutable, content-addressed Selection Policy snapshots;
- explicit Approval Artifact → policy conversion;
- CAS activation using expected active policy ID;
- first activation creates rollback snapshot from C rollback basis;
- explicit rollback;
- rollback is one-way until a new explicit activation;
- active corruption can fall back to recorded rollback;
- active+rollback invalid/missing can fall back to Legacy current 10;
- normal Production resolver reads runtime files only;
- Simulation DB is not polled for “latest” state;
- Risk Gate, NO_TRADE, suitability score semantics, and candidate priority are preserved;
- Exit Policy is a separate contract.

Atomic publication rule:

- Production `active.json` requires atomic replace;
- if atomic replace fails, no copy fallback;
- old active reference is preserved.

Key commits:

```text
ff84c64 feat: add production strategy selection policy registry
83647d8 chore: document strategy selection runtime ownership
9ab5fa1 docs: define strategy selection runtime store
40696ab test: cover production selection policy lifecycle
2bc136a test: integrate approval artifacts with selection publisher
```

---

# 10. P5-S1-E — Scanner/Strategy Integration + Run Pinning — COMPLETE

This stage was being implemented when the current chat hit the UI maximum-length warning. **The implementation itself is complete and verified in GitHub.**

## 10.1 Current HEAD

```text
4e781b577fad9c786d676531ab9d8846b0ab0ba2
test: clean scanner baseline verification diagnostics
```

## 10.2 SelectionPolicyPin

`backend/app/strategy/production_selection_policy.py` now defines an immutable `SelectionPolicyPin`.

It includes:

- policy ID/hash;
- contract version;
- source;
- fallback state/reason;
- operating Strategy refs;
- Scanner baseline identity;
- cache token;
- per-strategy version/hash reference lookup.

`pin_active_selection_policy()` resolves one fixed policy context for a run.

Baseline compatibility is checked before using an active Production policy.

If an active policy was approved against a different current Production baseline:

1. compatible rollback is attempted;
2. otherwise Legacy current 10 fallback is used;
3. the fallback reason is recorded.

## 10.3 StrategyEngine pool filter

`backend/app/strategy/engine.py`:

```python
evaluate_all(data, allowed_strategies=...)
```

was added while preserving old call compatibility.

Rules:

- default `None` means current 10 strategies;
- NO_TRADE is never taken from the Selection Pool;
- Risk Gate runs independently of Pool membership;
- after Pool filtering, existing score ordering remains;
- existing minimum suitability threshold 55 remains;
- if no allowed regular strategy reaches 55, NO_TRADE is inserted as before.

This is a true Production Pool filter, not cosmetic UI hiding.

## 10.4 Scanner integration

`backend/app/backtest/scanner.py` is now:

```text
VERSION = 0.21.3.8
HISTORICAL_EVIDENCE_POLICY_VERSION = v2
```

Scanner Run accepts/uses a single Selection Policy Pin.

The same Pin flows through quick candidate analysis and the rest of that Scanner run.

Scanner result includes:

```text
strategy_selection_policy
```

metadata.

Candidate records now carry internal reproducibility context such as:

```text
strategy_version_id
strategy_definition_hash
```

where applicable.

## 10.5 Scanner cache isolation

Scanner cache identity now includes Selection Policy cache token in addition to the existing Exit Policy token.

Therefore:

```text
same date + same market + same input + P1
!=
same date + same market + same input + P2
```

Cache payload also validates policy ID/hash before reuse.

## 10.6 Historical Evidence cache identity

Historical Evidence cache now includes:

- Strategy Version ID;
- definition hash;

with legacy fallback identity when no version ref exists.

This prevents evidence computed for Strategy v1 from being silently reused after v2 changes implementation.

## 10.7 Single-stock analysis pinning

`backend/app/strategy/service.py` now pins one Selection Policy for an entire analysis request.

The same Pin is used for:

- confirmed EOD evaluations;
- manual reference-price evaluations;
- strategy payloads;
- top/best strategy context.

EOD cannot use P1 while the reference-price branch uses P2 in the same request.

The result includes Selection Policy metadata.

## 10.8 Prospective identity separation

`ProspectiveCaptureRequest` now carries:

```text
selection_policy_id
selection_policy_hash
```

Prospective source identity includes those fields.

Therefore P1 and P2 runs over otherwise identical data are not deduplicated as the same execution.

No new P2 DB columns were required; policy context is carried in existing JSON/identity structures.

## 10.9 Scanner job pinning

Scanner jobs pin Selection Policy at run start.

Activation occurring while a job is already running must not change that job's policy.

The next run resolves the new policy.

Direct helper/adaptor calls were kept backward compatible after initial E changes.

Relevant compatibility commits:

```text
12035b9 fix: preserve legacy strategy evaluator call contract
9256b4f fix: keep direct scanner candidate adapters backward compatible
df0914d fix: keep selection pin scoped to scanner jobs
```

## 10.10 E implementation commit sequence

Main E sequence:

```text
feda2a6 feat: add run-pinned strategy selection policy context
4f063e3 feat: filter production strategy pool without changing risk gates
ab888f5 feat: carry allowed strategy pool into scanner snapshots
b98ac77 feat: pin selection policy through scanner execution
62619aa feat: pin selection policy across single stock analysis
4ba7876 feat: carry selection policy identity in prospective capture request
825dbf4 feat: pin prospective capture to scanner selection policy
fd204d9 feat: separate prospective identity by selection policy
d352f3e feat: pin scanner jobs to one selection policy
df0914d fix: keep selection pin scoped to scanner jobs
12035b9 fix: preserve legacy strategy evaluator call contract
9256b4f fix: keep direct scanner candidate adapters backward compatible
f3bb99d..fc43ceb test: advance scanner contract to 0.21.3.8
81f2010 test: advance scanner progress contract version
fd2df6b feat: advance production baseline contract for selection policy pinning
75d3b3f chore: align validation catalog with scanner 0.21.3.8
f3f4f6a fix: reject unsupported production strategy keys
1c74ebb test: cover strategy selection run pinning semantics
22ba812 test: cover baseline-aware selection policy pinning
7697bde test: align baseline fixtures with scanner 0.21.3.8
e85bdd7 fix: describe active strategy pool accurately in scanner metadata
b486791 chore: freeze scanner production baseline 0.21.3.8
ba2615f test: verify committed scanner 0.21.3.8 baseline
91827d6 test: lock scanner and evidence cache policy pin contracts
```

Baseline verification was then hardened for cross-platform line ending differences:

```text
8a87572 test: expose scanner baseline verification drift
0f761d2 test: print baseline drift details
1c640ef fix: make scanner baseline verification newline-stable
3f468cc test: verify scanner baseline across line endings
5c32485 fix: align scanner baseline with committed production sources
4e781b5 test: clean scanner baseline verification diagnostics
```

---

# 11. Scanner Production baseline after E

New frozen baseline:

```text
backend/runtime/baseline/scanner-production-baseline_0.21.3.8.json
```

Baseline ID:

```text
SS-SCANNER-0.21.3.8-dd1e7a75ab4aaac9
```

The old `0.21.3.7` baseline remains historical evidence and must not be rewritten/deleted.

The baseline manifest says:

```text
production_changed: false
```

meaning the E legacy-current-10 path was frozen as behavior-equivalent rather than intentionally changing the default Production policy.

Cross-platform verification was explicitly fixed so line-ending conversion alone does not create false baseline drift.

---

# 12. Latest CI status

Latest PR workflow:

```text
Run: 36369529304
HEAD: 4e781b577fad9c786d676531ab9d8846b0ab0ba2
Conclusion: SUCCESS
```

Jobs:

```text
Backend / Python 3.11  PASS
Backend / Python 3.14  PASS
Frontend / Node 22     PASS
```

Python 3.14 backend summary:

```text
1211 passed, 1 warning in 27.07s
```

The remaining warning is the existing Starlette/anyio deprecation warning.

Earlier intermediate E workflow failures/cancellations were superseded by the final green HEAD.

---

# 13. Current behavior / safety boundaries after E

### Default user behavior

With no active Selection Policy runtime state:

```text
LEGACY_CURRENT_10_FALLBACK
```

is used.

This means the ordinary user should continue to see the current ten strategies with existing Risk Gate / NO_TRADE / candidate priority semantics.

### Q7 remains unresolved

Real Production strategy promotion remains blocked.

The system structure can create and test synthetic approvals, but do not present that as a real Production strategy promotion policy.

### Do not silently activate anything

Do not manually create `active.json` just to test ordinary local startup.

Do not activate test-only Approval outside explicitly isolated tests.

### Existing Holdings remain untouched

Selection Policy activation applies to future Scanner/analysis execution.

It must not mutate existing:

- Holding Decision;
- Management Plan;
- Recovery Review;
- Watch rule/episode.

### Research remains broader than Production

`MultiStrategyBacktestEngine.SUPPORTED_STRATEGIES` remains the ten-strategy research pool.

Do not shrink historical validation/research just because a Production strategy is ON_HOLD/DEMOTED.

---

# 14. What is NOT done yet

The next planned stage is:

```text
VN-P5-S1-F — Strategy Governance API + minimal existing Validation UI integration
```

Then:

```text
VN-P5-S1-G — backup/restore + synthetic validation + final regression
```

P5 is not complete until F/G are done.

No Strategy Governance management UI has been browser-UAT'd yet.

Do not ask for browser verification after each small F commit. The user explicitly wants manual browser testing batched.

---

# 15. Next stage: P5-S1-F expected direction

F should expose the already-built contracts without creating a button-heavy new workflow.

Likely API responsibilities:

- read current Strategy Registry / versions;
- list/get Evaluation Artifacts;
- list/get Change Proposals;
- list/get Approval Artifacts;
- read Production Selection Policy status;
- expose active / rollback / fallback metadata;
- create Proposal where allowed;
- explicit Approval only when policy gate allows;
- explicit Activation/Rollback endpoints with CAS;
- clear blocked/stale states.

Important:

- API must never accept an arbitrary list of Production strategies for activation;
- activation must derive the Strategy set from immutable Approval → Proposal intent;
- Q7-unapproved Production approval must return a clear BLOCKED state, not invent thresholds;
- latest Simulation artifacts must not auto-activate Production;
- no new top-level “do everything” button.

UI direction:

Integrate a compact **Strategy Operations / 전략 운영** area into the existing Validation/Simulation workspace rather than adding another large top-level page unless the current layout requires it.

Show primarily:

- current operating strategy count/state;
- evidence state;
- pending proposal;
- blocked reason;
- current Production policy / fallback source;
- rollback availability.

Avoid exposing UUID/hash noise in normal view; keep it in expandable technical details.

Browser UAT should be requested once after F/G stabilization, not after each substage.

---

# 16. P5-S1-G expected responsibilities

G must close the reliability loop.

Required areas:

1. runtime backup/restore must include P5 Simulation governance tables;
2. backup/restore integrity must include Production Selection runtime snapshots/refs where appropriate;
3. immutable P5 artifacts must survive roundtrip;
4. corrupted Selection Policy snapshots/ref behavior must remain fail-safe;
5. full synthetic Proposal → Approval → Activation → next-run pin → rollback lifecycle;
6. current 10-strategy baseline equivalence;
7. existing Holdings Plan unchanged;
8. Risk Gate unchanged;
9. NO_TRADE unchanged;
10. Exit Policy remains separate;
11. complete backend regression + frontend build;
12. batched browser UAT if F adds visible UI.

---

# 17. Immediate next-chat startup checklist

At the beginning of the next chat:

1. Read this file.
2. Fetch the current branch HEAD instead of assuming it is still `4e781b5`.
3. Confirm PR #8 remains open and branch is clean/green.
4. Do not redo A-E.
5. Do not invent Q7 numeric thresholds.
6. Decide whether to apply local P5 migration before F browser/API testing.
7. Proceed with **P5-S1-F detailed specification**, then implementation when the user says to start.

If the school PC needs the latest branch first:

```powershell
git fetch --all --prune
git switch feature/ux-redesign-1
git pull --ff-only origin feature/ux-redesign-1
git log -1 --oneline
```

Expected handoff HEAD at creation time:

```text
4e781b5 test: clean scanner baseline verification diagnostics
```

If local P5 migration is chosen:

```powershell
.\.venv\Scripts\python.exe .\tools\data\backup_runtime.py
.\.venv\Scripts\python.exe .\tools\data\migrate_strategy_governance_vnp5s1.py
```

Do not activate a test Selection Policy as part of migration.

---

# 18. Suggested first message for the new conversation

The user can paste:

> StockScope 작업 이어가자. `docs/StockScope_HANDOFF_2026-09-28_P5S1E_COMPLETE.md`를 먼저 읽고 현재 브랜치/CI 상태를 확인해. A~E는 다시 하지 말고, 현재 상태가 문서와 일치하면 P5-S1-F 작업 명세부터 진행해. 브라우저 테스트는 작은 단계마다 요구하지 말고 F/G까지 최대한 자동 검증해서 묶어서 진행해.

---

## 19. Final current-state summary

```text
P1-S1 Input Identity                  COMPLETE
P1-S2 Horizon Context                COMPLETE

P2-S1 Feedback                       COMPLETE
P2-S2 Prospective                    COMPLETE

P3-S1 Holdings Decision / Plan       COMPLETE + browser UAT
P3-S2 Recovery                       COMPLETE + browser UAT

P4-S1 Realtime Watch                 IMPLEMENTATION COMPLETE
                                      local migration PASS
                                      production policy intentionally BLOCKED
                                      live KIS session smoke still not claimed

P5-S1-A Strategy Registry            COMPLETE
P5-S1-B Evaluation Artifact          COMPLETE
P5-S1-C Proposal / Approval          COMPLETE
P5-S1-D Selection Policy Publisher   COMPLETE
P5-S1-E Scanner / Strategy Pinning   COMPLETE + CI PASS

P5-S1-F Governance API / UI          NEXT
P5-S1-G Backup / restore / final QA  AFTER F

P6 Event evidence/news validation    LATER
P7 Adaptive UX redesign              LATER
P8 BYOK/public deployment            LATER
```

The critical invariant at handoff is:

```text
Evidence
→ Proposal
→ Approval
→ Explicit Production Policy
→ Run Pin
```

with no automatic latest-row Production behavior, no real brokerage order execution, and no invented Q7 promotion thresholds.
