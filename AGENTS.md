# StockScope agent/developer continuation guide

> Updated 2026-10-28. **Read before starting further StockScope development.** This is a routing note for Codex/other ChatGPT sessions, not a license to ignore product safety or the user's instructions.

## Current user priority

**Implement real TypeSafe JEV (System One) integration for Scanner Decision Reviewer**, not additional G2 candidate-history UI. G2-05 is paused. G2-01 through G2-04 are existing working features.

Read:
1. [Next-chat handoff](docs/JEV_NEXT_CHAT_HANDOFF.md).
2. [JEV live integration master plan](docs/JEV_LIVE_INTEGRATION_MASTER_PLAN.md) — authoritative **step/status checklist for this implementation**.
3. [Existing JEV v2 design](docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md).
4. [S7.4 source/rights/time boundary](docs/설계/JEV-ACT2-S7.4_데이터_출처_권한_및_시점_분류_기준.md).

**Next uncompleted stage:** JEV-LIVE-01 — connect the *existing* `TypeSafeSystemOneProvider` and V4 `JevManualReviewService` using synthetic-only real provider E2E, then continue sequentially. Before work, read the master plan's current status: it may have been updated after this AGENTS file.

## Non-negotiable development behavior

- Do **real code implementation**, not another audit/handoff/spec loop. Reuse `backend/app/jev/typesafe_provider.py`, `review_service.py`, `typesafe_service.py`, `backend/app/api/jev.py`, existing Scanner UI and JEV identity/policy/tests.
- Existing default `GET /api/simulation/jev/review-feature` is **disabled**, despite real TypeSafe transport already existing. Do not report JEV as product-ready merely because synthetic canary/API usage exists.
- Existing S7.4/S8 documents mark **real market-derived data outbound to TypeSafe NO-GO / PROVIDER_HOLD** until verified permission, source rights, proper as-of data and target-bound execution approval are established. Do not bypass this with text paraphrase, hashing, aliases, user key possession, or "synthetic" labeling of market-derived data. **Real JEV calls with genuinely synthetic original test data may proceed under separate explicit billable approval**, so engineering is not stalled.
- JEV is advisory only. Preserve Scanner ranking/decisions/Risk, Prospectve frozen captures, holdings and no-real-orders boundary. Provider error/timeout/schema drift must leave baseline unchanged.
- Never commit or print `.env`, `JEV_API_KEY`, provider/brokerage credentials, raw user-market datasets or sensitive provider payloads.
- No paid live provider requests in CI, no implicit auto-trigger upon UI visits; explicit opt-in with meaningful cap for pilot usage.
- Use the existing development branch `codex/p0-01-mvp-c1-c2-integration-20261022` and Draft PR #170 unless the user requests otherwise. Never silently merge to `main`.
- User dorm PC: old data in `C:\TAEWOO\CapstonDesign\StockScope`; new dev clone in `C:\Projects\StockScope-G2`. Other PCs have different paths. Use copy-isolated preview for existing local DBs.
- Every completed stage: update the master plan status table and handoff with commit SHA, CI and real Windows UI state. Do not claim CI equals actual live JEV review.

## Reference

GitHub repo: https://github.com/SkyBluekor/StockScope · PR: https://github.com/SkyBluekor/StockScope/pull/170 .
