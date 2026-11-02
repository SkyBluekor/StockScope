# StockScope — Coding Agent Instructions

## Mandatory first read
Read **docs/STOCKSCOPE_PRODUCT_EXECUTION_PLAN.md** at the start of every task. It is the single authoritative source for the **product goal, scope, approved step, completion criteria and progress table**. The README, older JEV_SINGLE_EXECUTION_PLAN, Development Roadmap and past P6 handoffs are technical/history references, not permission to implement extra work. Existing frozen technical, source-rights, data-integrity and security contracts remain in force.

## Verified workspace
- User's actual Windows repo: **C:\TAEWOO\CapstonDesign\StockScope**
- Git branch: **codex/jev-reviewer-shadow-bridge**
- Do not switch branches, create a second working directory, merge, or cherry-pick from a different branch without explicit user permission.
- Always check the current branch and working tree before edits.

## Strict execution
1. Before coding, identify the **one** currently user-approved stage in the product plan. If the plan is awaiting approval, **do not write feature code**.
2. Implement only changes directly needed for that stage and preserve unrelated Scanner, Strategy, Risk, Holdings, frozen data, DB and UI behavior.
3. Never turn extra tests, mock pipelines, audit UIs, documents, or data collectors into a new independent product stage. If a blocker needs a directly related fix, fix that blocker; otherwise record it in the existing plan's deferred list.
4. User-requested functionality is automatic market/stock/context analysis with accessible explanations. **The old two-sentence user-authored JEV comparison does not meet product requirements** and must not be treated as an accepted feature or advanced with paid tests.
5. Global and local markets, shocks, geopolitics, industry exposure, strategy fit, investment horizon, and risks are first-class decision inputs. Data sources must be verified; missing data never becomes a fabricated signal.
6. TypeSafe/JEV is a selective assistant to StockScope's existing analysis, **not** the product's objective or an automatic source of live market knowledge. Do not send licensed/third-party raw or derived data to an external model without proven rights. No paid calls without explicit approval.
7. Always distinguish CI/Mock from actual Windows user acceptance. Never mark a stage DONE based only on commits, API availability, or synthetic tests.
8. Update **only the product plan's progress table** for status and next steps. Do not create a new handoff or master plan.
9. When done, report: stage, actual files changed, user-visible behavior, CI and Windows evidence, blockers, and **the next planned stage only**.

## First approved implementation stage
The new product plan is **currently awaiting the user's confirmation**. Once approved, do only **stage 1: inventory the existing data/analysis connections and pinpoint gaps**. No speculative feature expansion or additional AI canaries.
