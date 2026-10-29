# StockScope agent/developer continuation guide

> Updated 2026-10-29. **Read before starting further StockScope development.** This is a routing note for Codex/other ChatGPT sessions, not a license to ignore product safety or the user's instructions.

## Current user priority

**Implement real TypeSafe JEV (System One) integration for Scanner Decision Reviewer**, not additional G2 candidate-history UI. G2-05 is paused. G2-01 through G2-04 are existing working features.

Read:
1. [Next-chat handoff](docs/JEV_NEXT_CHAT_HANDOFF.md).
2. [JEV live integration master plan](docs/JEV_LIVE_INTEGRATION_MASTER_PLAN.md) — authoritative **step/status checklist for this implementation**.
3. [Existing JEV v2 design](docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md).
4. [S7.4 source/rights/time boundary](docs/설계/JEV-ACT2-S7.4_데이터_출처_권한_및_시점_분류_기준.md).

**LIVE-01 real authored-synthetic provider PASS; LIVE-02 real Scanner local-readiness UI PASS; LIVE-03 actual-market HOLD diagnostic UI PASS; LIVE-04 authored-synthetic Mock manual request + catalog display USER WINDOWS UI PASS. REAL-MARKET TypeSafe REVIEW REMAINS BLOCKED.** The user supplied a real Windows screenshot showing isolated virtual ticker `999991` with `VALID` saved result, Mock disposition `REVIEW_REQUIRED`, returned model `jev-mock-returned` identity `MATCHED`, one mock call, zero actual provider calls and saved review ID. This is not an AI verdict on selected real ticker 셀트리온 (068270), where the UI still states `AI 검토 미제공`. The screenshot does not independently establish user refresh/double-click behavior, although the existing CI/API tests verify the underlying contract. Preserve KRX raw/derived rights HOLD and default real review OFF. LIVE-04 real-market E2E is NOT DONE. Continue existing V4 Provider and catalog; G2-01~04 preserved, G2-05 paused; PR #170 remains Draft.

## Non-negotiable development behavior

- Do **real code implementation**, not another audit/handoff/spec loop. Reuse `backend/app/jev/typesafe_provider.py`, `review_service.py`, `typesafe_service.py`, `backend/app/api/jev.py`, existing Scanner UI and JEV identity/policy/tests.
- Existing default `GET /api/simulation/jev/review-feature` is **disabled**, despite real TypeSafe transport already existing. Do not report JEV as product-ready merely because synthetic canary/API usage exists.
- Existing S7.4/S8 documents mark **real market-derived data outbound to TypeSafe NO-GO / PROVIDER_HOLD** until verified permission, source rights, proper as-of data and target-bound execution approval are established. Do not bypass this with text paraphrase, hashing, aliases, user key possession, or "synthetic" labeling of market-derived data. **Real JEV calls with genuinely synthetic original test data may proceed under separate explicit billable approval**, so engineering is not stalled.
- JEV is advisory only. Preserve Scanner ranking/decisions/Risk, Prospectve frozen captures, holdings and no-real-orders boundary. Provider error/timeout/schema drift must leave baseline unchanged.
- Never commit or print `.env`, `JEV_API_KEY`, provider/brokerage credentials, raw user-market datasets or sensitive provider payloads.
- No paid live provider requests in CI, no implicit auto-trigger upon UI visits; explicit opt-in with meaningful cap for pilot usage.
- Use the existing development branch `codex/p0-01-mvp-c1-c2-integration-20261022` and Draft PR #170 unless the user requests otherwise. Never silently merge to `main`.
- User's currently verified Windows development folder is `C:\Projects\StockScope`, and the ordinary startup command is `.\run-dev.ps1`. Do not assume `C:\Projects\StockScope-G2` exists on this PC. Other PCs may use different paths. Use copy-isolated preview for existing local DBs.
- Every completed stage: update the master plan status table and handoff with commit SHA, CI and real Windows UI state. Do not claim CI equals actual live JEV review.

## Reference

GitHub repo: https://github.com/SkyBluekor/StockScope · PR: https://github.com/SkyBluekor/StockScope/pull/170 .
