# StockScope Handoff — 2026-10-01 — NEXT-6D-S2 Complete

> Purpose: continue StockScope in a new ChatGPT conversation without rebuilding project context from memory or accidentally reviving obsolete assumptions.
>
> Repository: `SkyBluekor/StockScope`
>
> Authoritative branch: `main`
>
> Verified main SHA at handoff creation: `ecb79b1fb148b33b36e90cf5e48d693e45b75f24`
>
> Latest merged PR: #57 — **feat: add P6 as-of event reference reader**
>
> CI for PR #57: Frontend / Node 22 PASS, Backend / Python 3.11 PASS, Backend / Python 3.14 PASS
>
> Next task has **not** been implemented yet. The natural next step is `NEXT-6D-S3`: expose the new as-of Event Evidence projection together with Macro Context + Market↔Stock Impact + the S1 composition contract through a bounded read API. Exact endpoint/response naming is not frozen yet and must be specified before implementation.

---

# 0. Read this first — authority and anti-hallucination rules

This document is a handoff aid, not a substitute for checking the repository.

When continuing in a new chat, use this precedence:

1. **Current `main` code at the verified/latest SHA**
2. **This handoff**
3. Current dated design/governance documents in `docs/`
4. Older handoffs/history only as historical context

If an old document, memory, or previous message disagrees with current code, inspect current code and use the current code.

Do **not** invent missing contracts, endpoint names, versions, file paths, thresholds, DB schema, migration status, or numerical policy. Inspect the repository first.

Before any real repo change:

1. verify current `main`;
2. inspect the actual target files/signatures;
3. create a dedicated branch;
4. make the smallest scoped change;
5. add/adjust tests;
6. open PR;
7. wait for CI;
8. squash merge only after CI passes;
9. report the new `main` SHA.

Do not edit against assumptions from this handoff if the repo has moved.

---

# 1. User / assistant workflow contract

The user has explicitly fixed the following workflow.

## 1.1 Astra

Astra is for:

- difficult architecture/design review;
- ambiguous tradeoff review;
- comparison/analysis;
- drafting review/design documents.

Astra is **not** for:

- creating branches;
- editing code;
- opening PRs;
- CI;
- merges;
- normal implementation.

If the user says:

> “Astra에 물어보자”
> “Astra로 검토하자”

that means review/design/document work only.

## 1.2 Current assistant

The current assistant performs actual repository implementation.

If the user says:

> “작업 시작해”
> “작업 진행해”
> “진행해”

the current assistant should implement in GitHub using the workflow above.

If the user says:

> “다음 작업 명세해”
> “명세 진행해”

write the implementation specification only. **Do not implement** until the user separately authorizes implementation.

## 1.3 Codex

Do not default to Codex.

Use/prepare a Codex instruction only when the task becomes structurally large enough that direct Sol implementation is a poor fit, e.g.:

- multi-year external-data ingestion;
- large event reconstruction pipelines;
- broad cross-module refactors;
- large migration/backfill systems.

The assistant should say so at that point rather than silently changing workflow.

---

# 2. Product identity and non-negotiable direction

StockScope is a **local Korean-stock decision-support application**, not an automatic trading system.

Core principle:

```text
more internal analysis
→ less user interaction
→ concise result/context
→ user decides
```

The system may analyze, validate, compare, track, and surface context, but the user remains responsible for the decision.

## 2.1 Never turn StockScope into an auto-trader

Do not add or imply:

- automatic brokerage buy/sell orders;
- automatic stop-loss / take-profit execution;
- automatic averaging down;
- automatic strategy promotion/demotion;
- automatic Production Policy replacement;
- automatic Holdings Plan replacement;
- Risk Gate bypass;
- automatic strategy rotation based only on the latest Simulation result.

`NO_TRADE` is a safety result, not an operating Strategy Registry strategy.

Risk Gate remains independent safety logic.

## 2.2 UI/product direction

The user strongly prefers:

- fast decision support;
- concise results;
- internal complexity hidden when the user does not need it;
- minimal tabs/buttons;
- no long “report dumped into UI” experience;
- actions/results in the place where the user needs them;
- the user should not need to click Analyze / Recheck / Verify repeatedly during normal use.

Avoid stereotypical AI-generated UI:

- excessive rounded cards;
- repetitive three-card dashboard blocks;
- gradients everywhere;
- decorative badges;
- giant status boxes;
- needless buttons.

Preferred visual direction is restrained/editorial, with a practical real-product feel.

---

# 3. Technical stack / repository shape

Current project family:

- Backend: Python + FastAPI
- Frontend: TypeScript + React + Vite
- Runtime stores: SQLite
- Local Windows/PowerShell development
- Multiple PCs are used by the user

Historical project paths have included:

```text
C:\TAEWOO\CapstonDesign\StockScope
D:\Projects\StockScope
C:\Users\...\OneDrive\Documents\Projects\StockScope
```

Do **not** assume one path is always current. Repository work is normally done through GitHub; only give local path-specific commands when the user shows the current local path.

Important runtime DB families include:

```text
holdings.db
market_history.db
simulation.db
macro.db
```

Never casually delete/replace these DBs or WAL files. There was a prior readonly-database incident. Treat runtime DBs as user data.

Do not commit `.env`.

`.vscode/settings.json` may be user-owned. Do not overwrite it without a clear need.

---

# 4. One-click local synchronization

Root script:

```powershell
.\sync_local.ps1
.\sync_local.ps1 -CheckOnly
```

Current sync behavior includes:

- tracked working tree check;
- Git fetch/pull from `origin/main`;
- self-restart if `sync_local.ps1` itself changed during pull;
- runtime migration checks/runs;
- Development-only Macro artifact synchronization via:
  `tools/dev/sync_macro_artifacts.py`.

If sync fails, do not guess or recreate runtime artifacts manually unless the exact failure and recovery path are established.

Fixed Macro seeds must never be regenerated from guesswork.

---

# 5. High-level product areas already built

StockScope has grown through several user-facing and infrastructure areas.

Major product areas include:

- Scanner / candidate discovery
- Single-stock analysis
- Strategy suitability / strategy analysis
- Historical/backtest evidence
- Simulation / validation
- Holdings
- Management Plan
- Recovery Review
- Realtime Watch
- Strategy Governance / Production Selection Policy
- Event Evidence
- Market Overview
- Macro reference diagnostics
- Market↔Stock impact reference

Not every backend capability must become a visible UI feature. A recurring design rule is:

> If the user only needs the result, keep the machinery internal.

---

# 6. Historical project milestones before NEXT-6

These are historical milestone facts and architecture context. Do not re-run them just because they are mentioned here.

## 6.1 Simulation / Tracking / validation era

Historical milestones included:

- Simulation UI
- Tracking Track 1
- Manual Tracking
- VAL.1 A–E PASS
- VAL.2 B–E PASS
- PERF.1

Historical one-year replay:

```text
236 trading days
3538 candidates
```

Historical VAL.2 result counts:

```text
CLOSED       2192
CENSORED       76
NOT_EXECUTED 1249
```

Historical PERF.1 range was approximately:

```text
1.06–1.12 sec/day
```

These values are historical evidence/results, not a guarantee of current runtime performance after later code changes.

---

# 7. vNext roadmap phases P1–P6

The major vNext architecture is documented in:

```text
docs/StockScope_MASTER_ARCHITECTURE_vNext.md
docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md
```

## 7.1 P1 — Input identity / Horizon context

Implemented.

Key migration families:

```text
VN-P1-S1 Input Identity
VN-P1-S2 Horizon Context
VN-P1-S3 Selection Policy Pin
```

Historical migration output included market generation rows around 3004.

P1 provides reproducibility/context identity boundaries rather than user-facing “features.”

## 7.2 P2 — Feedback / Prospective evidence

Implemented.

Key stages:

```text
VN-P2-S1 Feedback
VN-P2-S2 Prospective
```

Important safety rule:

- Prospective evidence does not automatically promote/demote Production strategies.
- Minimum sample / promotion thresholds are not to be invented ad hoc.

## 7.3 P3 — Holdings Decision / Recovery

Implemented.

### Holdings Decision

Supports Management Plan/decision context with stale protection and quantity/price consistency checks.

Safety:

- no automatic brokerage action;
- no silent stop loosening;
- existing plan cannot be silently rewritten.

Historical safe UAT fixture included LVMC Holdings / `900140`, qty 2, avg 5000. Treat this as historical UAT data, **not current user holdings**.

### Recovery Review

Recovery is a manual review context.

It does not automatically trigger merely because a position is deeply negative.

Thesis states include:

```text
INTACT
WEAKENED
BROKEN
UNKNOWN
```

Review actions include:

```text
UNDECIDED
HOLD
REDUCE
EXIT
ADD_REVIEW
```

`ADD_REVIEW` is review intent, not automatic permission to buy.

## 7.4 P4 — Realtime Watch

Implemented.

Watch is separate from execution.

It does not:

- place orders;
- automatically change Management Plan;
- automatically start Recovery.

## 7.5 P5 — Strategy Governance

Implemented through Registry/Evidence/Proposal/Approval/Production Selection integration.

Current Production strategy set is exactly 10 regular strategies:

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

`NO_TRADE` is not part of the Registry.

Key P5 concepts:

```text
Strategy Registry Version
Strategy Evaluation Artifact
Change Proposal
Approval Artifact
Selection Policy
Active/Rollback publication
Run-pinned Selection Policy
```

Production policy is not “latest Simulation wins.”

A run pins one Selection Policy identity so the policy cannot change halfway through the same Scanner/single-stock run.

### Current Scanner version

Current code at this handoff:

```text
backend/app/backtest/scanner.py
VERSION = 0.21.3.9
HISTORICAL_EVIDENCE_POLICY_VERSION = v2
DATA_INTEGRITY_VERSION = v0.21.4-B.2.2.2d
```

Older handoffs that say `0.21.3.8` are historical and no longer authoritative.

Do not bump Scanner version for unrelated Macro/Event work unless Scanner behavior/contract actually changes.

## 7.6 P6 — Event Evidence

Implemented as immutable evidence infrastructure plus bounded product projection.

Core areas:

- source rights policy snapshots;
- source references;
- immutable event records/revisions;
- entity identity;
- entity relevance;
- canonical resolution;
- quality assessment;
- evaluation artifacts;
- value gate artifacts;
- user-facing bounded product projection.

Important P6 semantics:

- `USABLE` / `LIMITED` quality are not predictions;
- revisions include states such as ORIGINAL/CORRECTED/WITHDRAWN/SUPERSEDED;
- current product projection is read-only;
- prediction remains NOT_VALIDATED;
- source policy must be preserved;
- Test/Synthetic evidence must not become a real user reference.

---

# 8. Strategy-governance safety state

The project intentionally avoids making Strategy governance self-modifying.

Key rules:

- 10 regular Production strategies are versioned/fingerprinted;
- implementation drift changes Strategy fingerprint;
- Evaluation Evidence is immutable;
- Proposal/Approval are separate from Production activation;
- activation is explicit;
- rollback is explicit;
- active Selection Policy is runtime-owned;
- current Simulation rows do not directly control Production;
- Risk Gate and NO_TRADE remain separate safety behavior.

Do not add “recent strategy leaderboard automatically changes Production” unless a future approved contract explicitly authorizes it.

---

# 9. Capital-aware / user-decision design is separate

Design document:

```text
docs/StockScope_CAPITAL_AWARE_RECOMMENDATION_DESIGN_2026-09-29.md
```

This design discusses decision support around:

- user horizon;
- existing Holdings;
- losses/recovery;
- capital constraints;
- concise recommendations.

Do **not** mix Capital-Aware work into Macro/Event work unless explicitly requested.

A common user requirement is:

> StockScope should process data internally and help the user decide quickly, but not pretend to own the investment decision.

---

# 10. NEXT-6 Macro/Event architecture

Primary architecture document:

```text
docs/StockScope_NEXT6_MACRO_EVENT_ARCHITECTURE_DESIGN_2026-09-29.md
```

NEXT-6 was intentionally split into bounded layers rather than immediately feeding Macro/Event information into Strategy or Scanner.

Current broad structure:

```text
NEXT-6B  Macro Context / Reference Diagnostic
NEXT-6C  Market / Sector / Stock Impact
NEXT-6D  Macro + Event reference composition
```

Strategy/Scanner/Risk/Holdings remain untouched by these reference layers unless a later explicit approval stage changes that.

---

# 11. NEXT-6B — Macro Context / Reference Diagnostic

NEXT-6B went through a long reference-adequacy governance review.

## 11.1 Current governance conclusion

The authoritative current conclusion is:

```text
PRIMARY_PATH = C
SECONDARY_LONG_TERM_PATH = B

CURRENT_NUMERIC_POLICY = NONE
CURRENT_REFERENCE_ADEQUACY = UNRESOLVED
CURRENT_RATE_SPIKE = UNCALIBRATED
R2.5_ALLOWED = false
HOLDOUT_ACCESSED = false
```

Meaning:

- supported finite-path diagnostics may be used as **descriptive reference**;
- no numeric “minimum N sufficient” policy has been justified;
- RATE_SPIKE is not calibrated;
- reference diagnostics do not become Strategy/Risk/Production input;
- a future numeric policy would require a separately frozen, independently evaluated process.

Key governance document:

```text
docs/StockScope_NEXT6B_S4_2B16_R242_PATH_DISPOSITION_INDEPENDENCE_RECOVERY_2026-10-01.md
```

## 11.2 Holdout is locked

This is a strict boundary.

Do not:

- read Holdout;
- search for Holdout rows;
- hash Holdout;
- check Holdout existence;
- inspect Holdout files.

Unless a future explicitly authorized stage says otherwise.

The project intentionally preserves Holdout independence.

## 11.3 Development evidence

Development reference period:

```text
2016-01-04 .. 2023-12-29
1999 rows
warmup = 10
time quality = DATE_ONLY
```

Fixed Development seed/artifact lineage includes:

```text
DEV-7c3f6660b3aae03f.json
PROTOCOL-e1de868dc8f16670.json
```

Do not recreate fixed seeds.

Macro artifact synchronization is handled by:

```text
tools/dev/sync_macro_artifacts.py
```

The compact R2.1 reference-adequacy evidence was designed to replace a much larger representation while preserving logical evidence. Do not re-run heavy evidence generation unless justified/authorized.

## 11.4 Reference Diagnostic implementation

Contract:

```text
VN_NEXT6B_S4_2B16_REFERENCE_DIAGNOSTIC_V1
```

Feature horizons:

```text
delta_bp_1obs
delta_bp_5obs
delta_bp_10obs
```

Governance remains descriptive-only.

No threshold/pass is inferred from drift/MAD metrics.

Current API:

```text
GET /api/macro/reference-diagnostic
```

Frontend Market Overview exposes only a compact reference:

- 1 observation change;
- 5 observation change;
- 10 observation change;
- date;
- limitation language.

Raw ECDF/MAD/hash internals are not shown to the user.

---

# 12. NEXT-6C — Market / Sector / Stock impact

NEXT-6C started from the intended decomposition:

```text
Market
  ↓
Sector
  ↓
Stock
```

but historical Sector membership turned out to require stronger PIT evidence.

Therefore the implemented safe path is currently:

```text
Market ↔ Stock
```

with Sector explicitly blocked.

---

# 13. NEXT-6C-S1 — Market↔Stock Impact

Implemented contract:

```text
VN_NEXT6C_S1_MARKET_STOCK_IMPACT_V1
```

Main file:

```text
backend/app/macro/impact.py
```

Core calculation over the same two common confirmed EOD sessions:

```text
r_market = (market_end / market_start - 1) * 100
r_stock  = (stock_end  / stock_start  - 1) * 100

stock_vs_market = r_stock - r_market
```

Units:

```text
market_return_pct       %
stock_return_pct        %
stock_vs_market_pctp    percentage points (%p)
```

This is descriptive arithmetic only.

Do not reinterpret positive excess return as:

- strong;
- safe;
- buyable;
- resilient;
- caused by rates.

Reader:

```text
LocalMarketImpactReader
```

uses SQLite read-only/query-only behavior and confirmed EOD rows.

Missing data is not filled with zero.

Future Market rows must not change a frozen historical impact identity.

---

# 14. NEXT-6C Sector PIT boundary

Implemented:

```text
backend/app/macro/sector_evidence.py
backend/app/macro/sector_pit_audit.py
```

Contracts include:

```text
VN_NEXT6C_S2_SECTOR_MEMBERSHIP_EVIDENCE_V1
VN_NEXT6C_S2_SECTOR_PIT_COVERAGE_AUDIT_V1
```

Key rule:

```text
STATIC_CURRENT != POINT_IN_TIME
```

OpenDART current industry metadata remains:

```text
STATIC_CURRENT
```

and can never be silently promoted into historical PIT membership.

Evidence separates:

```text
effective_from / effective_to
known_at
```

because “true for a past date” and “known by the decision time” are different claims.

Audit states include:

```text
PIT_ELIGIBLE
STATIC_ONLY
MAPPING_MISSING
EFFECTIVE_RANGE_MISMATCH
SOURCE_TIME_UNPROVEN
BENCHMARK_UNRESOLVED
CONFLICTING_PIT_EVIDENCE
```

---

# 15. KRX historical Sector research result

Documents:

```text
docs/StockScope_NEXT6C_S3_SECTOR_PIT_SOURCE_FEASIBILITY_2026-10-01.md
docs/StockScope_NEXT6C_S31_KRX_MEMBERSHIP_ACCESS_PROOF_2026-10-01.md
```

Current conclusion:

```text
KRX historical constituent snapshot exists
historical date supported = true
constituent identity supported = true
benchmark identity supported = true

known_at proof = false
public automated ingestion authorization = false

S2 PIT compatibility = false
```

Public KRX Data Marketplace proves dated snapshots but not a defensible historical `known_at` for StockScope.

The project deliberately does not turn undocumented KRX web BLD endpoints into a Production API.

Research-only probe:

```text
tools/research/probe_krx_sector_membership.py
```

is offline-only and does not perform live scraping.

A stronger path would require:

- explicit KRX permission/API documentation; or
- authorized KRX index-information constituent/action product.

Until then:

```text
Historical Sector = blocked
```

---

# 16. NEXT-6C-S3.2 — Sector route closure

Implemented:

```text
backend/app/macro/sector_route.py
```

Contract:

```text
VN_NEXT6C_S32_SECTOR_ROUTE_V1
```

Current route:

```text
historical_sector_status = BLOCKED_EXTERNAL_SOURCE
historical_impact_mode    = MARKET_STOCK_ONLY
prospective_sector_status = NOT_STARTED
```

Unlock requires all of:

```text
AUTHORIZED_KRX_SOURCE
KNOWN_AT_PROVEN
EFFECTIVE_MEMBERSHIP_PROVEN
BENCHMARK_IDENTITY_PROVEN
S2_PIT_COMPATIBLE
```

Forbidden unlock evidence includes:

```text
OPENDART_STATIC_CURRENT
CURRENT_INDUSTRY_BACKFILL
QUERY_DATE_AS_KNOWN_AT
FETCH_TIME_AS_KNOWN_AT
UNAUTHORIZED_KRX_WEB_BACKEND
```

---

# 17. Market↔Stock Impact read API and UI

Read API:

```text
GET /api/macro/market-stock-impact
```

API contract:

```text
VN_NEXT6C_S32_MARKET_STOCK_IMPACT_API_V1
```

Input includes:

```text
market
ticker
end_date
cutoff (optional timezone-aware Macro cutoff)
```

The endpoint composes existing read-only Macro Context + Market Impact calculation.

Failure model:

```text
Macro Store unavailable
→ 503 MACRO_IMPACT_CONTEXT_UNAVAILABLE

Market Store missing/schema/read unavailable
→ 503 MARKET_IMPACT_STORE_UNAVAILABLE

invalid request
→ 400 MACRO_IMPACT_INVALID_REQUEST

insufficient common confirmed sessions
→ 200 + impact.status = UNAVAILABLE
```

Frontend files:

```text
frontend/src/services/marketImpactApi.ts
frontend/src/hooks/useMarketStockImpact.ts
frontend/src/components/MarketStockImpactInline.tsx
```

The single-stock analysis screen now displays:

```text
시장 대비 최근 움직임

시장 변동       %
종목 변동       %
시장 대비 차이  %p
```

using:

```tsx
endDate={stock.data_date}
```

not the current wall-clock date.

The UI states clearly that this is a simple return difference over the same two confirmed sessions and does not mean causality or buy/sell guidance.

Request staleness is protected with AbortController/generation identity.

---

# 18. NEXT-6D-S1 — Macro / Event Reference Composition

Merged PR #56.

Main file:

```text
backend/app/macro/event_composition.py
```

Contract:

```text
VN_NEXT6D_S1_MACRO_EVENT_REFERENCE_COMPOSITION_V1
```

Purpose:

```text
Macro Context
+
Market↔Stock Impact
+
Sector Route
+
P6 Event Evidence projection
↓
one bounded reference composition
```

It is a pure composition contract.

It does not perform:

- provider/network calls;
- DB writes;
- Strategy scoring;
- Risk decisions;
- Holdings decisions;
- prediction.

Identity requirements:

```text
MacroContext.context_id/hash/cutoff
must match
Impact.context_ref

Impact market/ticker
must match
Event Evidence market/code
```

Mismatch fails closed.

Cutoff filtering uses:

```text
available_at
evidence_as_of
assessment_as_of
```

but S1 explicitly admits that the current P6 product projection is not a complete historical as-of source.

Hence:

```text
historical_completeness_proven = false
```

Future references after cutoff are excluded from composition identity.

Identity policy:

```text
CUTOFF_ELIGIBLE_REFERENCES_ONLY
```

Governance remains:

```text
claim_scope = REFERENCE_COMPOSITION_ONLY
causal_attribution = false
macro_exposure_relation_created = false
prediction_approved = false

strategy_input_approved = false
scanner_input_approved = false
risk_gate_input_approved = false
holdings_plan_input_approved = false
production_decision_approved = false
```

An existing P6 `MACRO_EXPOSURE` relation may be preserved as evidence, but this composer never creates/invents one.

---

# 19. NEXT-6D-S2 — P6 As-of Event Reference Reader — CURRENT LATEST WORK

Merged PR #57.

Current main SHA after merge:

```text
ecb79b1fb148b33b36e90cf5e48d693e45b75f24
```

New files:

```text
backend/app/event_evidence/asof.py
backend/tests/test_event_evidence_asof_next6d_s2.py
```

Export updated:

```text
backend/app/event_evidence/__init__.py
```

Contract:

```text
VN_NEXT6D_S2_EVENT_REFERENCE_AS_OF_V1
```

Projection mode:

```text
SYSTEM_OBSERVED_AS_OF
```

Main class:

```python
EventEvidenceAsOfReader
```

Main method:

```python
stock_reference_as_of(
    code,
    market,
    decision_cutoff,
    limit=3,
)
```

## 19.1 What “as-of” means here

It is not “all events that historically happened.”

It means:

> references that the StockScope P6 ledger had actually observed by the cutoff.

The Reader enforces both semantic/source time and storage-observation time.

Examples of enforced fields include:

```text
event.available_at
event.created_at

entity.identity_as_of
entity.created_at

relevance.evidence_as_of
relevance.created_at

quality.assessment_as_of
quality.created_at

source.available_at
source.created_at

policy.created_at
```

This prevents a 2026 backfill of a 2022 event from rewriting a 2022/2025 as-of projection.

## 19.2 Revision resolution

Per `event_id`, the Reader selects the latest revision actually known by cutoff.

Example:

```text
v1 ORIGINAL   before cutoff
v2 CORRECTED  after cutoff

→ as-of cutoff uses v1
```

If the correction is known by cutoff:

```text
→ v2
```

If latest known state is:

```text
WITHDRAWN
SUPERSEDED
```

the event is not an active reference.

## 19.3 Integrity

The Reader verifies pinned identities/hashes for:

- Quality payload/hash;
- Event hash / source bundle hash;
- Entity hash;
- Relevance hash;
- Source ref hash;
- Policy hash;
- Canonical/resolution pins when present.

Integrity mismatch fails closed.

## 19.4 Canonical dedup / limit order

Correct order is:

```text
DB candidates
→ cutoff checks
→ latest known revision
→ integrity verification
→ synthetic exclusion
→ canonical/event dedup
→ deterministic ordering
→ limit
```

Not:

```text
latest 3 current rows
→ cutoff filter
```

This fixes the problem where current future references could hide a valid older reference.

## 19.5 Value/Predictive scope

The as-of Reader does **not** replay Value Gate.

Current output explicitly uses:

```text
value_validation.status = NOT_PROJECTED_AS_OF
value_validation.product_scope = RESEARCH_ONLY

prediction.status = NOT_VALIDATED
```

Governance:

```text
claim_scope = REFERENCE_CONTEXT_AS_OF_ONLY
historical_evaluation_approved = false
prediction_approved = false
strategy_input_approved = false
scanner_input_approved = false
risk_gate_input_approved = false
holdings_plan_input_approved = false
production_decision_approved = false
network_access = false
database_write = false
```

## 19.6 Future invariance

A future late-ingested event with an old `available_at` but a new `created_at` must not alter an old projection hash.

This is explicitly tested.

## 19.7 Read-only boundary

The Reader uses:

```text
SQLite mode=ro
PRAGMA query_only=ON
```

No migration or write happens.

PR #57 CI passed on Node 22, Python 3.11, and Python 3.14.

---

# 20. Current NEXT-6 PR chain

This sequence is useful when reconstructing history.

```text
#45  R2.4.2 Path disposition / independence recovery
      main → e62778a77221905a59efa38134082c944cc145c1

#46  Reference Diagnostic contract
      main → 6094be250644d740ac40f94c563a914c7a00dbc9

#47  Reference Diagnostic → Macro Context wiring
      main → 8f228d11418f8d1204ece39c06985c217221b19f

#48  Macro Reference Diagnostic read API
      main → 175aa8fe5b5d8d05197ec03619faafcc6d0fc675

#49  Macro Reference minimal frontend exposure
      main → 0da64fe05b70e8965db2f885b28bcd5a3c45b730

#50  Market↔Stock Impact projection
      main → e6e4963235a4de3f7547eadc0bce628b14ed1ff7

#51  Sector PIT evidence + coverage audit
      main → d63f0ab7089dd92b5bd7cffb172868631c7cea35

#52  Historical Sector PIT source feasibility
      main → 8bf92b21b3af6ca9785b93b127fd9ca83934c17d

#53  KRX membership access / known-at proof
      main → e651a6b3b93cbdb23bf05309dc5be3b0b975a888

#54  Historical Sector route closure + Market↔Stock read API
      main → 2e48175cd73bb9a84905a52331c941ec91655a75

#55  Market↔Stock Impact frontend exposure
      main → ac989df3235707e9ee98a7629a87ad63de2a4ba3

#56  Macro/Event Reference Composition contract
      main → b9bf8e41dabd098ea50b136a2ca8de0954d06db5

#57  P6 Event Evidence as-of reader
      main → ecb79b1fb148b33b36e90cf5e48d693e45b75f24
```

If the latest main has advanced in a new chat, verify again and do not force these SHAs.

---

# 21. Current external data boundaries

External data families historically/currently include:

- KRX
- KIS
- OpenDART
- news sources
- FRED / Macro source

The user is expected to provide/configure required external credentials where applicable.

Do not commit credentials.

Do not assume an existing KRX Open API key authorizes undocumented Data Marketplace constituent endpoints.

Do not scrape undocumented KRX endpoints as a substitute for explicit data rights.

OpenDART current `induty_code` is not historical PIT industry membership.

---

# 22. Source-rights / Event Evidence rules

P6 source policies are part of evidence governance.

Do not silently:

- retain raw content if policy does not allow it;
- perform AI transforms if policy disallows them;
- use a source for historical evaluation if the policy does not allow that;
- use reference evidence as prediction input.

Current Macro/Event work should use bounded P6 projections and preserve rights/policy identity.

---

# 23. Strict “do not do this” list

Unless the user explicitly authorizes a later stage:

## Data / evidence

- Do not access Holdout.
- Do not recreate fixed Macro seeds.
- Do not rerun expensive Macro evidence chains without justification.
- Do not treat Development evidence as independent validation.
- Do not treat KRX current/public snapshot date as historical `known_at`.
- Do not treat OpenDART current industry as historical PIT sector membership.
- Do not turn late backfill into earlier observed evidence.

## Decision systems

- Do not feed Macro/Event reference into Strategy automatically.
- Do not alter Scanner ranking from Macro/Event reference.
- Do not alter Risk Gate from Macro/Event reference.
- Do not alter Holdings plan from Macro/Event reference.
- Do not produce causal claims such as “rates caused this stock move.”
- Do not infer `MACRO_EXPOSURE` merely because Macro and Event are shown together.
- Do not claim prediction validation.
- Do not claim RATE_SPIKE is calibrated.

## Production

- Do not replace active Selection Policy automatically.
- Do not auto-promote/demote strategies.
- Do not place trades.
- Do not silently loosen stops.
- Do not silently replace a user-approved Management Plan.

## Repository / local state

- Do not delete user DB/WAL files.
- Do not commit `.env`.
- Do not overwrite user-owned editor settings without need.
- Do not invent local runtime migration results; use `sync_local.ps1 -CheckOnly` on the actual PC.

---

# 24. Historical user/test data — do not treat as current facts

Past development/UAT conversations used examples such as:

```text
000660 SK하이닉스
005930 삼성전자
034730 SK
900140 엘브이엠씨홀딩스
```

and one stop-loosening fixture:

```text
900140
qty 2
avg 5000
```

These are test/history references only.

Do not assume they are the user's current real Holdings.

---

# 25. Current frontend state relevant to NEXT-6

## Market Overview

Already has compact Macro Reference diagnostic display.

## Single-stock analysis

Already has compact Market↔Stock Impact display.

Important design rule:

- backend hash/context/governance internals are not dumped into UI;
- user sees useful values + limitations;
- backend failure does not break the entire stock-analysis screen.

---

# 26. Current backend API state relevant to NEXT-6

Current Macro endpoints include:

```text
GET /api/macro/reference-diagnostic
GET /api/macro/market-stock-impact
```

P6 has its own existing Event Evidence product API, but the new D-S2 as-of reader is **not yet exposed through a new NEXT-6D API**.

That is the important current boundary.

---

# 27. Natural next task — NEXT-6D-S3

Not implemented yet.

The natural next step after D-S2 is to add a bounded read API that composes:

```text
MacroContext
+
Market↔Stock Impact
+
Sector Route
+
EventEvidenceAsOfReader
↓
build_macro_event_reference_composition()
↓
read-only response
```

Before implementing, write an exact S3 specification.

Important questions S3 should freeze:

1. endpoint path/name;
2. required inputs:
   - market;
   - ticker;
   - market impact end_date;
   - timezone-aware decision_cutoff;
3. DB path resolution:
   - Macro store;
   - Market History store;
   - Simulation/P6 store;
4. failure semantics:
   - core Macro/Impact unavailable;
   - Event store unavailable;
   - no observed Event entity by cutoff;
   - evidence blocked/integrity failure;
5. whether Event absence should produce PARTIAL instead of 503;
6. response projection — user-safe bounded fields only;
7. no current Product fallback that destroys historical as-of semantics;
8. read-only DB size/mtime tests;
9. future Event/backfill invariance;
10. no Strategy/Scanner/Risk/Holdings wiring.

Do not invent the endpoint path before the specification is agreed.

Likely subsequent order:

```text
NEXT-6D-S3  Read API
NEXT-6D-S4  Minimal frontend reference, only if actually useful
```

---

# 28. Suggested new-chat opening prompt

The user can start the next chat with:

```text
StockScope 작업 이어가자.

먼저 GitHub main을 확인하고
docs/StockScope_HANDOFF_2026-10-01_NEXT6D_S2_COMPLETE.md
를 읽어.

이 문서를 현재 프로젝트 handoff 기준으로 사용하되,
문서와 현재 main 코드가 충돌하면 현재 main 코드를 우선해.

Astra는 어려운 설계/비교/검토 문서용이고,
실제 구현은 네가 한다.
내가 "다음 작업 명세해"라고 하면 명세만 작성하고,
"작업 시작해/진행해"라고 해야 실제 repo 작업을 시작해.

Holdout은 명시적 허가 전까지 읽거나 검색하거나
hash/existence check도 하지 마.

현재 handoff 시점의 완료 상태는 NEXT-6D-S2까지다.
다음 자연스러운 작업은 NEXT-6D-S3 Read API 명세다.
먼저 현재 main이 handoff SHA 이후 바뀌었는지 확인해.
```

---

# 29. Fast sanity checklist for the next assistant

Before answering a project-state question:

```text
[ ] current GitHub main verified
[ ] current scanner VERSION checked if relevant
[ ] actual target files inspected
[ ] old handoff version claims not blindly reused
[ ] Holdout untouched
[ ] Macro numeric policy still NONE unless explicit later change
[ ] RATE_SPIKE still UNCALIBRATED unless explicit later change
[ ] historical Sector still BLOCKED_EXTERNAL_SOURCE unless KRX authorization changed
[ ] Strategy/Scanner/Risk/Holdings not silently connected to Macro/Event
```

Before implementation:

```text
[ ] user explicitly said 작업 시작/진행
[ ] branch created from current main
[ ] minimal scope
[ ] tests added
[ ] PR opened
[ ] all CI green
[ ] squash merge
[ ] final main SHA reported
```

---

# 30. Final handoff state

```text
PROJECT = StockScope

REPOSITORY = SkyBluekor/StockScope

AUTHORITATIVE_MAIN_AT_HANDOFF =
ecb79b1fb148b33b36e90cf5e48d693e45b75f24

LATEST_COMPLETE_TASK =
NEXT-6D-S2 — P6 As-of Reference Reader / Temporal Projection

LATEST_PR = #57

LATEST_CI =
Frontend Node 22 PASS
Backend Python 3.11 PASS
Backend Python 3.14 PASS

SCANNER_VERSION = 0.21.3.9

PRODUCTION_STRATEGIES = 10
NO_TRADE_IS_REGISTRY_STRATEGY = false

CURRENT_NUMERIC_MACRO_POLICY = NONE
CURRENT_REFERENCE_ADEQUACY = UNRESOLVED
CURRENT_RATE_SPIKE = UNCALIBRATED
R2_5_ALLOWED = false

HISTORICAL_SECTOR_STATUS = BLOCKED_EXTERNAL_SOURCE
HISTORICAL_IMPACT_MODE = MARKET_STOCK_ONLY
PROSPECTIVE_SECTOR_STATUS = NOT_STARTED

MACRO_EVENT_COMPOSITION =
REFERENCE_COMPOSITION_ONLY

P6_ASOF_MODE =
SYSTEM_OBSERVED_AS_OF

P6_HISTORICAL_SOURCE_COMPLETENESS_PROVEN = false
P6_HISTORICAL_EVALUATION_APPROVED = false
P6_PREDICTION = NOT_VALIDATED

STRATEGY_INPUT_APPROVED_FROM_NEXT6 = false
SCANNER_INPUT_APPROVED_FROM_NEXT6 = false
RISK_GATE_INPUT_APPROVED_FROM_NEXT6 = false
HOLDINGS_INPUT_APPROVED_FROM_NEXT6 = false
PRODUCTION_DECISION_APPROVED_FROM_NEXT6 = false

HOLDOUT_ACCESSED = false

NEXT_TASK_NOT_STARTED =
NEXT-6D-S3 — bounded read API for
MacroContext + Market↔Stock Impact + EventEvidenceAsOf + composition
```

End of handoff.
