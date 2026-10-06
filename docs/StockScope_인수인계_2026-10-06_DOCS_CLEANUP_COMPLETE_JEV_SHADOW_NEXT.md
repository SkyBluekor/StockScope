# StockScope 인수인계 — 2026-10-06
## Docs Cleanup 완료 / JEV Shadow Implementation 다음

작성일: 2026-10-06 (Asia/Seoul)
현재 branch: main
현재 HEAD: e1c3b954ae9eb2ac77457c8b39e41c03f0c6b2bf

---

# 0. 이 문서의 목적

이 문서는 대화 길이 제한 때문에 새 채팅으로 이동할 때 StockScope의 흐름을 잃지 않도록 만든 handoff다.

새 채팅에서는 과거 R4/R5/R5R 중간 문서를 다시 처음부터 읽거나, 이미 해결한 blocker를 다시 설계하지 않는다.

우선 이 문서와 아래 현재 active 문서를 기준으로 이어간다.

읽는 순서:

1. docs/StockScope_MASTER_ARCHITECTURE_vNext.md
2. docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md
3. 현재 작업 기준
   - R5R: docs/설계/StockScope_NEXT6E_R5R_통합설계기준_2026-10-05.md
   - JEV: docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md
4. docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md
5. 필요할 때만 docs/history/StockScope_R4_R5_R5R_설계변경이력.md

---

# 1. StockScope의 제품 목적

StockScope는 통계 논문이나 AI 실험 프로젝트가 아니다.

핵심 목적:

여러 데이터·전략·검증 결과를 내부에서 분석해 사용자가 주식 상태를 빠르고 이해하기 쉽게 판단하도록 돕는 투자 판단 보조 프로그램.

절대 목적이 아닌 것:

- 미래 주가 보장
- 투자 수익 보장
- AI에게 모든 판단권 이전
- 실제 주문 자동 실행
- theorem 자체를 제품 목표로 삼기
- JEV PASS 자체를 프로젝트 목표로 삼기

핵심 방향:

StockScope 기존 분석과 검증이 중심이고, JEV/R5R은 그 판단 품질을 보조하는 내부 수단이다.

---

# 2. 작업 운영 규칙 — 매우 중요

## 2.1 명세와 실행 분리

사용자가 "다음 작업 명세해", "명세"라고 하면 SPEC ONLY.

GitHub write, 구현, 평가 실행을 하지 않는다.

사용자가 "작업 시작해", "진행해", "작업 진행해"라고 하면 실제 변경을 진행한다.

## 2.2 설계를 과도하게 늘리지 않는다

기본 원칙:

틀리지 않을 만큼 충분히 설계하고, 실제로 써볼 수 있을 만큼 빠르게 구현한다.

새 phase/BR은 다음 경우에만 만든다.

- contract contradiction
- 실제 계산 defect
- data leakage 위험
- 재현성 failure
- 구현을 진행할 수 없는 genuine blocker

단순히 더 엄밀하게 작성할 수 있다는 이유로 단계를 늘리지 않는다.

## 2.3 설계 완결성과 제품 속도의 균형

필수 safety / reproducibility는 엄격하게 유지한다.

제품에 불필요한 학술 완결성은 추가하지 않는다.

---

# 3. 현재 StockScope 주요 구조

## Scanner

역할:

- 시장/종목 데이터 기반 후보 생성
- 전략 조건 평가
- Risk를 포함한 후보 판단
- 최종 candidate ranking

JEV는 Scanner를 대체하지 않는다.

## Strategy

여러 전략을 내부 운영하며 strategy version / validation / governance 구조를 가진다.

핵심 원칙:

- 전략은 후보 판단의 근거
- 검증되지 않은 전략을 자동 승격하지 않음
- Adaptive Strategy는 검증/승인/rollback 구조 안에서만 동작

## Risk

Risk Engine은 AI보다 상위 hard boundary다.

JEV가 Risk FAIL을 PASS로 바꾸는 경로는 없다.

Risk는 weighted AI score와 상쇄하지 않는다.

## Holdings / Recovery

보유종목 판단 지원:

- 현재 포지션 문맥
- 손절 / 회복 / 추가매수 검토
- plan revision
- stale 방지
- stop-loosening 차단
- Recovery / Watch

JEV Phase 1에서는 Holdings를 건드리지 않는다.

## Watch

보유 계획에 기반한 관찰/알림 역할.

자동 계획변경 또는 자동매매가 아니다.

## Event / News / Macro

OpenDART / News / Macro reference는 각각 source/time/use 권한이 있다.

현재 JEV Phase 1은 quant-only이므로 News 원문, Event Evidence, Macro reference, 보유정보, 계좌정보를 입력하지 않는다.

## Validation

Historical / Execution / Prospective / Tracking / Strategy Governance / Reference validation을 구분한다.

평가 결과가 마음에 들지 않는다는 이유로 threshold나 protocol을 역으로 바꾸지 않는다.

---

# 4. 문서 정리 상태 — 완료

2026-10-06 Docs cleanup이 실제 완료됐다.

Pre-cleanup planning baseline:
893f2b96289a02f7cfce46b2a4ea7abb0d86326c

정리 전 docs tracked files:
154

- Markdown 126
- JSON 27
- DOCX 1

Astra cleanup manifest 분류:

- KEEP_ACTIVE 17
- MERGE_INTO_ACTIVE 95
- KEEP_HISTORY 33
- DELETE_REDUNDANT 9

실제 cleanup:

- MERGE 원본 제거 95
- DELETE_REDUNDANT 제거 9
- total removed 104

현재 docs:

- Markdown 25
- JSON 27
- DOCX 1
- total 53

Machine-readable JSON 27개는 전부 보존했고 rename/move/reserialize하지 않았다.

KEEP_ACTIVE / KEEP_HISTORY 누락 0.
Holdout 접근 0.
R5R actual evaluation 0.
JEV model call 0.
DEV T/L/S/Common-N 계산 0.

---

# 5. 현재 문서 구조

## Master
docs/StockScope_MASTER_ARCHITECTURE_vNext.md

제품 목적, 도메인 owner, 데이터 owner, 금지 경계.

## Implementation Baseline
docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md

현재 구현 불변식, migration, regression, recovery, activation rule.

## Roadmap
docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md

장기 의존성 및 조건부 개발 흐름.

Roadmap은 실시간 완료표와 혼동하지 않는다.

## R5R Baseline
docs/설계/StockScope_NEXT6E_R5R_통합설계기준_2026-10-05.md

현재 R5R authoritative narrative.

## JEV Baseline
docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md

현재 JEV authoritative design.

## History
docs/history/StockScope_R4_R5_R5R_설계변경이력.md

과거 실패/전환의 핵심 이유만 통합.

---

# 6. R4 → R5 → R5R 설계 흐름

## R4

Population-level CDF / stationarity / mixing 계열 접근.

문제:

- actual process에 strict stationarity를 충분히 bind하지 못함
- alpha mixing / population assumptions 정당화 실패

결론:
R4 = HISTORICAL / SUPERSEDED FOR MODEL USE

## R5

더 정교한 구조:

- locally stationary
- functional dependence
- concentration band
- prospective finite anchor grid
- all-later/latest

Theorem 내부 정합성은 상당 부분 해결.

하지만 actual DGS10 process에 iid innovation, C_dep/rho, C_ls/zeta, L2, q/M_q 등을 감사 가능한 수준으로 bind하지 못함.

GA2/BR1 결론:

MODEL_USE_BINDING_ROUTE = PARTIALLY_FEASIBLE
COMPLETE_AUDITABLE_ROUTE_FOR_CURRENT_R5 = NO
METHOD_USE_REDESIGN = REQUIRED

R5는 retroactive PASS로 바꾸지 않는다.

## R5R

MUR1에서 population law 증명을 포기하고 observed-path empirical stability로 전환.

Architecture:
R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1

R5R은 R5 patch가 아니라 새로운 target/method family다.

---

# 7. 현재 R5R authoritative state

Target:
NEXT6E_S6A_R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1

Method:
NEXT6E_S6A_R5R_EMPIRICAL_STABILITY_V1

Method Contract:
docs/contracts/NEXT6E_S6A_R5R_METHOD_CONTRACT_V2.json

Semantic SHA:
5519ad12a6e3dafb30041935c6ead2869d35148aadb2a6bab8443521ea8310c4

Design SHA:
05852b077e6c29820643299f66984f496ffe806d88c6544c577ee3357c5f74eb

CandidateDomain SHA:
2f89ea3fdf775d718fabf955ee266b5cf36736f68b0fe97ced2cc5da83e0cdb4

Window SHA:
47a11455b159564db80eaf2c61bd89710a4bf56aea5d740eb60617ac2a3d385c

---

# 8. R5R frozen 계산

Horizon:
1 / 5 / 10

Metrics:

T_EMP = exact empirical CDF sup distance
L_EMP = normalized midpoint-median shift
S_EMP = relative midpoint-MAD shift

Window:
w(n)=ceil(n/10)

Candidate grid:
j/20, j=2,...,19

총 18 anchors.

Current aggregation:
ALL_HORIZONS_AND
AND ALL_METRICS_AND
AND ALL_LATER_STATES

Latest state 포함.

Numeric:
R5R_EXACT_RATIONAL_V1

Chronology:
PREBOUND_COMPLETE_JOINT_CHRONOLOGY
R5R_JOINT_CHRONOLOGY_HASH_V1

---

# 9. R5R Policy V1

Policy:
docs/contracts/NEXT6E_S6B_R5R_POLICY_V1.json

Policy ID:
NEXT6E_S6B_R5R_INITIAL_OPERATIONAL_POLICY_V1

Semantic hash:
8934d99d808b8c7afa837fb71601695457154747fbcafd592da44b337343bc22

Metric activation:

T_EMP = GATE
L_EMP = GATE
S_EMP = GATE

Tolerance:

tau_T = 0.10
tau_L = 0.50
tau_S = 0.25

이 값은 population truth / industry standard가 아니다.

초기 내부 operational policy다.

결과를 보고 자동 완화하지 않는다.

---

# 10. R5R 구현 / Binding

Pure evaluator:
backend/app/macro/r5r_evaluator.py

Binding:
backend/app/macro/r5r_binding.py

Tests:
backend/tests/test_macro_r5r_evaluator_next6e.py
backend/tests/test_macro_r5r_binding_next6e.py

Binding CLI:
tools/data/bind_macro_r5r_evaluation_next6e.py

---

# 11. Frozen DEV binding

Binding artifact:
docs/bindings/NEXT6E_R5R_EVALUATION_BINDING_V1.json

Binding ID:
R5RBIND-b27cf5c12ab37aac

Binding hash:
b27cf5c12ab37aac93a524387f47fbc4086b5d8d6ced75cd1bf211fea587a716

Dataset:
MACROCAL-DEV-7c3f6660b3aae03f

Dataset hash:
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1

Source SHA:
7b1dfe33537bb8855b9441b2aeb24338a13950abf8cdc186b2821898d47313f4

Joint rows:
1999

Window:
200

Joint chronology hash:
f2fa057b25e1ff9b2012b76f29f28b40627a4040a3dffa0e4c3b9b8ea430a62d

Effective anchors:
200, 300, 400, ..., 1900

---

# 12. R5R Gate 상태

현재 effective state:

R5R-G0 = PASS
R5R-G1 = PASS
R5R-G2 = PASS
R5R-G3 = PASS
R5R-G4 = PASS

Reference Adequacy:
AUTHORIZED / NOT EXECUTED

즉 아직 실제 DEV에 대해 다음을 계산하지 않았다.

- T_EMP
- L_EMP
- S_EMP
- candidate status
- OBSERVED_PATH_COMMON_N
- overall SUPPORTED_WITHIN_POLICY / NOT_SUPPORTED / BLOCKED

---

# 13. R5R에서 다시 열지 않을 것

특별한 defect가 없으면 재설계 금지:

- observed-path target
- T/L/S formula
- midpoint median/MAD
- w(n)=ceil(n/10)
- 18-anchor grid
- all-later
- latest state
- chronology hash
- exact rational semantics
- Policy V1 tolerance

R5R actual result가 마음에 들지 않는다는 이유로 바꾸지 않는다.

---

# 14. Holdout 규칙

Holdout은 명시적 허가 전 LOCKED.

금지:

- 내용 읽기
- 검색
- metadata
- hash
- 존재 확인 probe
- Reference Adequacy 튜닝에 사용

지금까지 cleanup/JEV 설계에서도 Holdout 접근 0.

---

# 15. JEV — 이름 혼동 해결

과거 NEXT-6E-R5R-JEV라는 이름을 R5R actual evaluation에 사용하며 AI JEV와 혼동이 생겼다.

이제 분리:

NEXT-6E-R5R-EVALUATION
= R5R observed-path actual evaluation

JEV-REVIEWER-EVALUATION
= AI Decision Reviewer incremental-value evaluation

과거 NEXT-6E-R5R-JEV는 historical alias로만 본다.

---

# 16. JEV authoritative design

문서:
docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md

기존 docs/StockScope_JEV_INTEGRATION_CONCEPT.md 는 cleanup에서 삭제됐으며 Git history에서만 복원한다.

---

# 17. JEV Phase 1 역할

JEV의 단일 역할:
Decision Reviewer

연결 위치:

Scanner 완료
→ Prospective candidate capture
→ JEV shadow review

대상:
ENTRY_CANDIDATE

Phase 1 input:
quant-only allowlist

제외:

- News
- Event Evidence
- Macro reference
- 보유정보
- 계좌정보

---

# 18. JEV output

최소 structured decision:

- PASS_THROUGH
- REVIEW_REQUIRED
- ABSTAIN

JEV가 하지 않는 것:

- 종목 발굴
- 순위 변경
- Risk 우회
- entry/stop/target 변경
- 보유계획 변경
- 자동매수/자동매도

기존 StockScope baseline은 항상 유지된다.

---

# 19. JEV Shadow 비교 가설

Phase 1에서 실제 Scanner 결과를 바꾸지 않는다.

Offline comparison rule:
JEV_DEFER_THIS_OPPORTUNITY_V1

의미:

- REVIEW_REQUIRED만 가상으로 이번 opportunity skip
- PASS_THROUGH / ABSTAIN / model error / no-call은 baseline 그대로

실제 후보 제거가 아니다.

---

# 20. JEV 평가 기준

JEV가 유용하다는 근거는 문장 품질이 아니다.

핵심 측정:

- baseline vs JEV shadow disagreement
- 회피 손실
- 놓친 이익
- 기회당 순증분 가상수익
- 유지 후보 손실률
- coverage
- abstain/error/late
- latency
- cost

Historical 결과만으로 채택하지 않는다.

실제 채택 판단에는 frozen prospective shadow 기간이 필요하다.

---

# 21. JEV 실행 큰 단계

JEV v2는 4개로 단순화됐다.

Design Freeze
→ Shadow Implementation
→ Evaluation
→ Adoption Decision

현재:
Design Freeze = COMPLETE

다음:
JEV-SHADOW-IMPLEMENT

---

# 22. JEV API key 상태

Canonical env:
JEV_API_KEY

현재 local .env에는 사용자가 실제 key를 추가해둔 상태.

절대 기록하지 말 것:

- 실제 key value
- Git
- log
- artifact
- backup

Repository .env.example에는 JEV_API_KEY= placeholder만 존재.

docs/API_KEYS.md에도 변수명만 문서화됐다.

중요:
Credential slot READY != Provider/model/prompt frozen

현재 provider / model revision / prompt는 아직 freeze되지 않았다.

---

# 23. 다음 작업 1 — JEV-SHADOW-IMPLEMENT

새 채팅에서 사용자가 "다음 작업 명세해"라고 하면 가장 우선적으로 이 작업 명세를 작성한다.

범위:

- minimal provider adapter
- JEV_API_KEY loader
- strict quant-only allowlist projector
- structured output validator
- PASS_THROUGH / REVIEW_REQUIRED / ABSTAIN
- timeout/model failure fallback
- async shadow review record
- baseline immutability
- comparison join/report
- fake-provider deterministic tests
- model/prompt/provider/policy identity pin
- result persistence / backup boundary
- trial protocol skeleton

절대 이번 단계에 자동매매/순위변경/보유계획 변경을 넣지 않는다.

---

# 24. 다음 작업 2 — JEV-REVIEWER-EVALUATION

Shadow Implementation 이후.

순서:

1. fake/synthetic provider 검증
2. 허용된 Development historical diagnostic
3. 사전 고정된 미래 prospective shadow
4. incremental value / cost / failure 비교
5. Adoption Decision

---

# 25. 별도 작업 — NEXT-6E-R5R-EVALUATION

R5R actual evaluation은 JEV와 별도다.

현재 실행 가능하지만 아직 미실행.

사용:

Method V2 + Policy V1 + Binding V1 + verified evaluator

결과:

- T/L/S
- per-anchor state
- Common-N
- overall status

를 처음 계산한다.

JEV Phase 1은 macro를 사용하지 않으므로 R5R evaluation을 JEV Shadow 시작의 불필요한 선행조건으로 만들지 않는다.

---

# 26. 문서 cleanup 완료 후 중요 변경

삭제된 대표 파일:

- 오래된 JEV Integration Concept
- 오래된 handoff
- R5/R5R 중간 narrative
- 중복 UX/version docs
- 완료 task spec/hotfix docs

중요 결정은 Master / Implementation Baseline / R5R baseline / JEV baseline / History에 통합됐다.

과거 원문이 꼭 필요하면 cleanup 이전 revision:
893f2b96289a02f7cfce46b2a4ea7abb0d86326c
에서 복원한다.

---

# 27. 현재 main HEAD

이 handoff 작성 직전 확인:
e1c3b954ae9eb2ac77457c8b39e41c03f0c6b2bf

Docs cleanup은 이 HEAD 기준 완료 상태다.

---

# 28. 새 채팅에서 하지 말아야 할 것

- R4/R5 population theorem 처음부터 재논의
- R5R tolerance 재선정
- R5R window/anchor 재설계
- docs cleanup 다시 설계
- 구 JEV Integration Concept을 authority로 사용
- R5R evaluation을 AI JEV evaluation이라고 부르기
- JEV에게 Risk/주문 권한 주기
- Holdout 탐색
- outcome 보고 threshold 수정

---

# 29. 새 채팅에서 먼저 확인할 것

실제 작업 시작 전에 main HEAD 확인.

기준:
e1c3b954ae9eb2ac77457c8b39e41c03f0c6b2bf

변경됐다면 새 commit diff만 확인하고 흐름을 유지한다.

---

# 30. 사용자 작업 선호

StockScope 작업에서는:

- GitHub normal chat에서 직접 작업
- Work 사용 지양
- "명세" → 명세만
- "작업 시작" → 실제 변경
- 설계 후 구현
- 하지만 논문급 과설계 금지
- 비슷한 문서는 통합
- 가능하면 한글 제목
- 사용자 UI는 결과 중심
- 내부 계산/검증은 필요할 때만 노출
- 기능 추가보다 판단 품질 개선이 핵심

---

# 31. 프로젝트에서 가장 중요한 제품 철학

StockScope의 목표는 복잡한 AI/통계 시스템을 만드는 것이 아니라, 사용자가 주식 판단을 더 빠르고 더 잘 할 수 있게 만드는 것이다.

AI/JEV가 새로운 주인이 되는 구조가 아니라:

StockScope 기존 계산 + 검증된 AI 리뷰 = 더 나은 판단 보조

가 목표다.

---

# 32. 다음 채팅 첫 기준

현재 가장 자연스러운 다음 흐름:

Docs Cleanup = COMPLETE
JEV Design v2 = FROZEN
R5R implementation/binding = COMPLETE
R5R actual evaluation = NOT EXECUTED
JEV Shadow Implementation = NEXT

사용자가 다음 채팅에서 "다음 작업 명세해"라고 하면:

JEV-SHADOW-IMPLEMENT 명세부터 작성한다.

사용자가 R5R 실제 평가를 먼저 하자고 명시하면:

NEXT-6E-R5R-EVALUATION으로 진행한다.

둘을 섞지 않는다.


# 33. 다음 채팅에 그대로 붙여넣을 문장

아래 문장을 새 채팅 첫 메시지로 그대로 사용한다.

> StockScope 작업 이어서 진행하자. 먼저 `docs/StockScope_인수인계_2026-10-06_DOCS_CLEANUP_COMPLETE_JEV_SHADOW_NEXT.md`를 읽고 현재 `main` HEAD만 확인해. 이 문서를 authoritative handoff로 사용하고, 이미 끝난 R4/R5/R5R 설계와 docs cleanup은 다시 열지 마. 현재 상태는 **Docs Cleanup COMPLETE / JEV Design v2 FROZEN / R5R G0~G4 PASS / R5R evaluator·DEV binding COMPLETE / R5R actual evaluation NOT EXECUTED / JEV Shadow Implementation NEXT**다. R5R actual evaluation과 AI JEV evaluation은 반드시 분리해. 내가 **"다음 작업 명세해"**라고 하면 `JEV-SHADOW-IMPLEMENT` 명세만 작성하고 실제 GitHub 변경은 하지 마. 내가 **"작업 시작해/진행해"**라고 할 때만 실제 변경해. Holdout은 명시적 허가 전 검색·metadata·hash·존재 probe 포함 전부 접근 금지. `JEV_API_KEY` 실제 secret 값은 절대 읽거나 출력·로그·artifact·backup·Git에 남기지 마. StockScope의 목적은 AI나 JEV 자체가 아니라 사용자의 주식 판단을 더 잘 돕는 프로그램이라는 기준을 유지해.

짧게 시작하고 싶다면:

> StockScope 이어서 하자. `docs/StockScope_인수인계_2026-10-06_DOCS_CLEANUP_COMPLETE_JEV_SHADOW_NEXT.md` 먼저 읽고 main HEAD 확인해. 다음 작업은 JEV-SHADOW-IMPLEMENT이고, 명세/실행 분리·Holdout lock·JEV_API_KEY secret 비노출 원칙 그대로 유지해.


---

# 34. 2026-10-06 Post-Handoff Update — JEV Trial Freeze COMPLETE

이 섹션은 기존 handoff의 후속 실행 결과만 추가한다. 앞의 historical 상태를 삭제하거나 R4/R5/R5R frozen 설계를 다시 열지 않는다.

## 완료된 후속 작업

- JEV Shadow Core: IMPLEMENTED / CI PASS
- Minimal Shadow Monitor UI: IMPLEMENTED / CI PASS
- JEV Trial Freeze: IMPLEMENTED / CI PASS
- Read-only monitor API: IMPLEMENTED
- Real provider adapter: IMPLEMENTED but NOT ACTIVATED
- Provider: OpenAI Responses API
- Model: `gpt-5.6-terra`
- Model revision: `NOT_PINNABLE_2026-10-06`
- Revision policy: returned served-model identity + protocol hash cohort separation
- Prompt: `JEV_DECISION_REVIEWER_PROMPT_V1`
- Prompt SHA256: `4f16a87bddd4696bd8d484e949675ff8a7739afaae45af3ad1cc466fc2068319`
- Output schema SHA256: `84a320572bb2753fc98aa65180c7143c6b4c8a8ecbc576b7f919c26081ffa26f`
- Trial artifact: `docs/contracts/JEV_REVIEWER_TRIAL_PROTOCOL_V1.json`
- Trial spec SHA256: `9f4e42fbd5cc957a9dc72ed7ce3f84c0dbf07c4a768b38695e4c90c16297b36b`
- Adapter: `JEV_OPENAI_RESPONSES_ADAPTER_V1`
- Responses storage: `store=false`
- Cohort: activation 이후 새 canonical Scanner capture만 모집
- Duplicate unit: market + ticker + signal_date + strategy_version + horizon의 최초 유효 canonical observation
- Recruitment cap: 200 candidates / 90 calendar days
- Mature minimum: 60
- Disagreement minimum: 12
- Error maximum: 5%
- Abstain maximum: 30%
- Review-rate maximum: 50%
- Trial API budget: USD 5
- Observation: max 20 trading days
- Purge: 20 trading days
- 2026 listed-share statutory market tax assumption: 0.20%; broker fee/slippage는 pilot에서 0.00%로 고정하고 unmodeled로 명시
- Source transmission: derived quant-only; News/Event/Macro/Holdings/account/user/future outcome/raw source content 금지
- Pre-activation capture / recruitment window / recruitment cap / duplicate / budget gate: IMPLEMENTED
- Explicit activation gate: IMPLEMENTED
- Runtime trial configure tool: `tools/data/configure_jev_trial_v1.py`

## 실행하지 않은 것

- 실제 JEV API call: 0
- 실제 JEV token 소비: 0
- JEV Reviewer Evaluation: NOT EXECUTED
- Adoption Decision: NOT EXECUTED
- NEXT-6E-R5R-EVALUATION: NOT EXECUTED
- Holdout: LOCKED / NOT ACCESSED

실제 `JEV_API_KEY` 값은 읽거나 출력·로그·artifact·backup·Git에 남기지 않았다.

## 다음 단계

다음 단계명은 **JEV-REVIEWER-EVALUATION**이다.

단, 사용자가 앞서 정한 원칙에 따라 실제 provider activation과 실제 JEV 호출은 전체 평가 준비가 끝난 뒤 명시적으로 통합 테스트할 때만 수행한다. 다음 명세/구현에서 evaluation join, cohort accounting, maturity/denominator, frozen metric report 경로를 먼저 완성할 수 있으며, 이 과정에서도 실제 model call은 자동으로 시작하지 않는다.

R5R actual evaluation은 계속 별도 작업이며 JEV evaluation과 혼동하지 않는다.


---

# 35. 2026-10-06 Post-Handoff Update — JEV Reviewer Evaluation Prep COMPLETE

이 섹션은 JEV Trial Freeze 이후 후속 구현 상태만 추가한다. 기존 R4/R5/R5R frozen 설계와 이전 완료 상태는 다시 열지 않는다.

## 완료된 후속 작업

- JEV Reviewer Evaluation Prep: IMPLEMENTED / CI PASS
- Evaluation policy artifact: `docs/contracts/JEV_REVIEWER_EVALUATION_POLICY_V1.json`
- Evaluation policy ID: `JEV_REVIEWER_EVALUATION_POLICY_V1`
- Evaluation policy semantic SHA256: `2e31e99ace3b2760dfed1db06466d1f51c44b250e5143acf387de2dc05ae0edc`
- Evaluation report version: `JEV_REVIEWER_EVALUATION_REPORT_V1`
- Evaluation storage: `JEV_REVIEWER_EVALUATION_STORAGE_V1`
- New local-only storage:
  - `jev_evaluation_schema_meta`
  - `jev_evaluation_run`
  - `jev_evaluation_unit`
- Existing `jev_shadow_comparison_report` reused for immutable final report snapshots
- Local sync migration: `JEV-EVALUATION-V1`
- CLI: `tools/data/evaluate_jev_reviewer_v1.py`
- Read-only API:
  - `GET /api/simulation/jev-shadow/evaluation/latest`
  - `GET /api/simulation/jev-shadow/evaluation-runs/{run_id}`
- Backup/restore declaration: COMPLETE
- Interrupted evaluation recovery: COMPLETE
- Outcome engine: existing local Prospective outcome kernel reused without opening legacy split selection paths
- JEV cohort accounting: COMPLETE
- Maturity accounting: COMPLETE
- Primary comparison set: CLOSED + non-null net return only
- CENSORED: never converted to 0% realized return
- Comparison policy: VALID + REVIEW_REQUIRED only means virtual skip; every other review outcome preserves baseline
- Model cohort identity accounting: protocol/provider/model/served-model/prompt/adapter identity
- Concentration gates: ticker and signal-date
- Evaluation states:
  - COLLECTING
  - HOLD
  - REJECT
  - ELIGIBLE_FOR_ADOPTION_REVIEW
- `ELIGIBLE_FOR_ADOPTION_REVIEW` is not automatic adoption.

## Frozen evaluation gates

- Mature candidates >= 60
- Comparable CLOSED disagreements >= 12
- Error rate <= 5%
- Abstain rate <= 30%
- Review rate <= 50%
- Single ticker share <= 20%
- Single signal-date share <= 20%
- Observed API cost <= USD 5
- Primary delta > 0
- Avoided loss - missed profit > 0
- Retained-candidate loss rate <= baseline loss rate
- Mixed served-model cohort => HOLD

## 이번 단계에서 실행하지 않은 것

- 실제 OpenAI/JEV provider call: 0
- 실제 JEV token 소비: 0
- 실제 JEV trial activation: OFF
- 실제 JEV Reviewer Evaluation: NOT EXECUTED
- 자동 adoption: NOT EXECUTED
- R5R Actual Evaluation: NOT EXECUTED
- 잠긴 데이터 영역: LOCKED / NOT ACCESSED
- `JEV_API_KEY` 실제 secret 값: NOT READ / NOT LOGGED / NOT STORED

## 검증

최종 implementation CI:
- Frontend / Node 22: PASS
- Backend / Python 3.11: PASS
- Backend / Python 3.14: PASS
- Fresh Clone / Windows: PASS

평가 준비 테스트에는 다음이 포함된다:
- frozen policy/hash 검증
- local-only review→outcome join
- COLLECTING / HOLD / REJECT / ELIGIBLE_FOR_ADOPTION_REVIEW 상태 gate
- migration 외부 network/model call 0 검증
- read-only evaluation API route
- local sync migration order
- backup/restore JEV evaluation store 복원 경계

## 다음 단계

다음 큰 단계는 **JEV-INTEGRATED-SHADOW-TRIAL**이다.

사용자가 정한 원칙에 따라 실제 provider activation과 실제 JEV 호출은 모든 준비 작업이 끝난 뒤 명시적으로 통합 테스트할 때만 수행한다.

통합 시험 시 흐름:
`Scanner → real JEV shadow review → Monitor UI → immutable review storage → 시간이 지난 후 local outcome → JEV evaluation snapshot/report`

R5R Actual Evaluation은 계속 별도 작업으로 유지하며 JEV evaluation과 혼동하지 않는다.

# 36. 2026-10-06 Correction Update — TypeSafe Jev Core Correction COMPLETE

이 section은 §34/§35에 기록된 OpenAI/Terra 기반 JEV 후속 구현의 **현재 해석을 정정**한다. 기존 section은 당시 실제 구현/CI 이력으로 보존하지만, 더 이상 TypeSafe Jev의 올바른 provider/model 설계 authority로 사용하지 않는다.

## 정정된 JEV 정의

- JEV = **TypeSafe AI Jev / System One**
- OpenAI Responses + `gpt-5.6-terra` binding = 잘못된 해석으로 만든 **LEGACY V1**
- 실제 OpenAI/Terra provider call은 수행되지 않았고 실 trial data도 생성되지 않았다.
- 기존 V1 frozen artifact/hash/history는 삭제·변조하지 않고 read-only history로 보존한다.
- 신규 real V1 activation은 code-level에서 **`JEV_LEGACY_V1_ACTIVATION_BLOCKED`**로 차단한다.

## TypeSafe Design Freeze

문서:
`docs/설계/StockScope_TypeSafe_Jev_설계동결_v1_2026-10-06.md`

Commit:
`f808c001825b8aa7b5e24e4acf4ab21925241c8a`

Phase 1 frozen architecture:

`canonical ENTRY_CANDIDATE → minimized semantic state → TypeSafe System One 3 Noul → StockScope deterministic disposition`

3 Noul:

1. `strategy_context_conflict`
2. `entry_context_conflict`
3. `review_evidence_insufficient`

v3 초안의 `risk_context_caution`은 DROP했다. ENTRY_CANDIDATE는 이미 Strategy/Risk deterministic gate를 통과하고 price consistency도 기존 code owner가 계산하므로, Risk를 Jev가 다시 판정하지 않는다.

Application disposition:

- PASS_THROUGH
- REVIEW_REQUIRED
- ABSTAIN

Operational status와 application disposition은 별도 축이다. ERROR/SKIPPED/LATE/INTERRUPTED에는 disposition을 만들지 않는다.

## TypeSafe Core Correction

Implementation baseline:

- Core implementation commit: `dac7e948a2f88bcff2811e4de11d2861e56508ff`
- Fresh setup dependency correction: `5ce2d3c444a5186aa0428acdeb7de5a35f2cdaf0`

완료:

- `TYPESAFE_SYSTEM_ONE` native provider boundary
- `POST /v1/systemone` request shape: state + questions + model only
- 3-Noul fixed question contract
- minimized state projector
- ticker/name/rank/stop/target/RR/future outcome external payload 제외
- Risk fuzzy question 제거
- deterministic disposition policy
- threshold low/high slot architecture
- strict native response/model/usage validator
- request model / returned model 분리
- invalid/missing model fallback 금지
- real provider cost unknown-safe 처리
- fake TypeSafe provider
- retry 0 core
- bounded core queue
- additive TypeSafe V2 protocol/activation/recruitment/review storage
- recruitment ledger idempotency
- reserved/known/unknown cost accounting boundary
- PENDING restart → INTERRUPTED startup recovery
- additive migration `JEV-TYPESAFE-V2`
- Local Sync order: VN-P2-S2 이후
- backup manifest `jev_typesafe_v2`
- restore 후 `enabled=0 / allow_network=0` 강제
- Legacy V1 real activation 차단
- V1 historical tables/artifacts 유지

V2 schema identity:

`JEV_TYPESAFE_STORAGE_V2`

Core contracts:

- state: `JEV_TYPESAFE_STATE_V1`
- projector: `JEV_TYPESAFE_PROJECTOR_V1`
- questions: `JEV_TYPESAFE_QUESTIONS_V1`
- disposition policy: `JEV_TYPESAFE_DISPOSITION_POLICY_V1`
- adapter: `JEV_TYPESAFE_SYSTEMONE_ADAPTER_V1`

## 아직 동결/실행하지 않은 것

다음은 Core Correction 완료와 별개다.

- 실제 TypeSafe model discovery: NOT EXECUTED
- 실제 `GET /v1/models`: 0
- 실제 `POST /v1/systemone`: 0
- 실제 TypeSafe token consumption: 0
- 실제 TypeSafe API cost: 0
- 실제 TypeSafe trial activation: OFF / NOT STARTED
- Trial V2 machine-readable frozen JSON: NOT CREATED
- threshold numeric final freeze: NOT DONE
- real account model availability/returned identity: NOT VERIFIED
- retention/ZDR/account billing binding: NOT VERIFIED
- TypeSafe prospective efficacy evaluation: NOT EXECUTED
- R5R Actual Evaluation: NOT EXECUTED
- 자동 adoption: NOT EXECUTED
- `JEV_API_KEY` actual secret value: NOT READ / NOT LOGGED / NOT STORED

Threshold policy의 구조는 freeze됐지만 `0.15 / 0.85`는 여전히 candidate value다. actual prospective outcome을 보기 전에 승인된 synthetic/provider canary에서 behavior를 확인한 후 Trial V2 artifact에 final numeric value를 동결한다.

## Core Correction CI

최종 CI run:
`37420771151`

결과:

- Frontend / Node 22: PASS
- Backend / Python 3.11: PASS
- Backend / Python 3.14: PASS
- Fresh Clone / Windows: PASS

첫 implementation run에서 fresh setup planner가 `JEV-TYPESAFE-V2`의 VN-P2-S2 dependency를 알지 못해 prerequisite block이 발생했다. `5ce2d3c...`에서 migration dependency/write-domain/runtime-required identity를 추가했고 두 번째 전체 CI가 PASS했다.

## 다음 단계

다음 작업은 **TYPE-JEV-MONITOR-EVALUATION-CORRECTION**이다.

목적:

- 기존 V1 중심 Monitor projection을 TypeSafe V2 status/disposition/uncertainty semantics로 교정
- Legacy V1과 TypeSafe V2를 UI/API에서 혼합하지 않음
- evaluator 모집 분모를 review row가 아니라 V2 recruitment ledger 기준으로 교정
- ERROR/SKIPPED/LATE/INTERRUPTED와 semantic ABSTAIN 분리
- TypeSafe model/state/question/policy cohort identity 반영
- V2 evaluation denominator/coverage/performance plumbing 교정
- 자동 adoption 없음
- 실제 provider network/model call은 계속 0

그 다음에만 **TYPE-JEV-APPROVED-CANARY-TRIAL**을 별도 명시 승인으로 진행한다.

그리고 Phase 1 correction/canary/trial 작업이 모두 끝난 뒤 별도 **TYPE-JEV-EXPANSION-REVIEW** 문서를 작성해, Holdings/Watch/Recovery/Strategy Governance 등에서 TypeSafe Jev가 deterministic code보다 실제 추가 가치를 낼 수 있는 fuzzy decision 영역이 더 있는지 조사한다. “이미 Jev를 붙였으니 더 사용한다”가 아니라 추가 가치가 있는 경우에만 확장한다.

잠긴 데이터 영역은 계속 **LOCKED / NOT ACCESSED**이며 검색·metadata·hash·존재 probe를 포함해 접근하지 않는다.

# 37. 2026-10-06 Correction Update — TypeSafe Jev Monitor/Evaluation Correction COMPLETE

이 section은 §36의 TypeSafe Core Correction 이후 후속 단계인 **TYPE-JEV-MONITOR-EVALUATION-CORRECTION** 완료 상태를 기록한다.

## Implementation

Implementation commit:

`4d9dff3ba414f4a838bad80c66eecf6ed1b8b913`

Commit message:

`feat: correct TypeSafe JEV monitor and evaluation`

완료된 핵심 변경:

- 현재 Scanner 화면의 Jev Monitor를 Legacy `/simulation/jev-shadow/*`에서 TypeSafe V2 `/simulation/jev/*` read-only API로 전환
- Legacy V1 API는 삭제하지 않고 historical read-only 경로로 보존
- V2 Monitor source of truth를 review row가 아니라 `jev_typesafe_recruitment` ledger로 변경
- callable=false recruitment를 SKIPPED로 유지하여 모집 분모에서 사라지지 않게 함
- Operational status와 application disposition 분리
- `SKIPPED / ERROR / LATE / INTERRUPTED`에 application disposition을 부여하지 않음
- `VALID`일 때만 `PASS_THROUGH / REVIEW_REQUIRED / ABSTAIN` 사용
- TypeSafe reason semantics:
  - `STRATEGY_CONTEXT_CONFLICT`
  - `ENTRY_CONTEXT_CONFLICT`
  - `NO_ADDITIONAL_CONTEXT_CONFLICT`
  - uncertainty: `EVIDENCE_INSUFFICIENT / MODEL_UNCERTAIN`
- Legacy `RISK_CAUTION` Monitor 의미 제거
- stored typed answers를 frozen threshold/policy로 다시 계산하여 stored disposition과 동일한지 검증
- 불일치 시 `DISPOSITION_INTEGRITY_MISMATCH`로 정상 결과에서 제외
- model identity가 MATCHED가 아닌 VALID result를 정상 결과로 인정하지 않음
- raw Noul probability는 기본 UI에 노출하지 않음
- 기본 UI guardrail: Jev 보조 검토가 기존 후보·순위·진입·Risk 판단을 변경하지 않음을 유지

## TypeSafe V2 Monitor API

신규 API:

- `GET /api/simulation/jev/status`
- `GET /api/simulation/jev/reviews?capture_id=...`
- `GET /api/simulation/jev/evaluation/latest`
- `GET /api/simulation/jev/evaluation-runs/{run_id}`

신규 응답은 `engine = TYPESAFE_V2` identity를 명시한다.

현재 Trial V2 machine-readable artifact 및 final threshold/model binding은 아직 없으므로, protocol이 없거나 DRAFT 상태이면 UI/API는 `TRIAL_NOT_FROZEN`을 표시한다. Core ready와 actual trial ready를 혼동하지 않는다.

## TypeSafe Evaluation V2

신규 schema:

`JEV_TYPESAFE_EVALUATION_STORAGE_V2`

신규 logical tables:

- `jev_typesafe_evaluation_schema_meta`
- `jev_typesafe_evaluation_run`
- `jev_typesafe_evaluation_unit`
- `jev_typesafe_evaluation_report`

Migration:

`JEV-TYPESAFE-EVALUATION-V2`

Local Sync dependency:

`JEV-TYPESAFE-V2 → JEV-TYPESAFE-EVALUATION-V2`

Evaluation V2는 Legacy `jev_evaluation_*` / `jev_shadow_comparison_report`를 재사용하거나 mutate하지 않는다.

## Evaluation denominator correction

V2 cohort source of truth:

`R = jev_typesafe_recruitment`

평가 funnel:

`recruited → callable → review_created → VALID/ERROR/LATE/INTERRUPTED → disposition → outcome → mature → comparable CLOSED`

비율 정의를 분리했다:

- skip rate = SKIPPED / recruited
- attempt coverage = review_created / callable
- error rate = ERROR / review_created
- late rate = LATE / review_created
- interrupted rate = INTERRUPTED / review_created
- valid rate = VALID / review_created
- abstain rate = VALID+ABSTAIN / VALID
- review-required rate = VALID+REVIEW_REQUIRED / VALID
- pass-through rate = VALID+PASS_THROUGH / VALID

분모가 0이면 0%가 아니라 null/N/A로 처리한다.

## Performance comparison

성과 비교에서 virtual defer는 오직:

`VALID + REVIEW_REQUIRED`

만 사용한다.

다음은 모두 baseline을 유지한다:

- PASS_THROUGH
- ABSTAIN
- ERROR
- LATE
- INTERRUPTED
- SKIPPED
- review not created

따라서 provider 운영 실패나 semantic abstention 때문에 baseline 후보가 임의로 삭제되지 않는다.

CENSORED는 계속 0% realized return으로 변환하지 않는다.

기존 comparison 의미:

`r_shadow,i = (1-d_i) r_i`

`d_i=1` iff `VALID + REVIEW_REQUIRED`

를 유지한다.

## Evaluation identity / integrity

TypeSafe cohort identity에는 최소 다음을 반영한다:

- protocol spec hash
- provider
- model requested / returned
- model identity status
- state contract
- projector
- question contract/hash
- disposition policy/hash
- threshold low/high
- adapter version

mixed model cohort는 정상 efficacy cohort로 자동 합치지 않는다.

typed-answer/disposition integrity mismatch도 HOLD/integrity failure 대상이다.

## Cost semantics

Unknown provider cost는 0 USD로 해석하지 않는다.

V2 evaluation은 다음을 분리한다:

- known cost
- unknown cost count
- reserved unknown cost
- budget exposure

실제 TypeSafe billing binding이 확인되기 전에는 unknown cost가 있는 cohort를 비용 gate PASS로 자동 처리하지 않는다.

## Evaluation gate status

Evaluation V2의 **metric engine / gate slots / storage contract는 COMPLETE**다.

하지만 실제 Trial V2 숫자는 아직 freeze하지 않았다.

미확정:

- final threshold low/high
- min mature
- min closed disagreements
- max skip/error/late/interrupted/abstain/review rate
- min attempt coverage
- concentration gate
- budget exposure gate
- actual model identity

gate slot이 비어 있으면 evaluator는 `EVALUATION_POLICY_NOT_FROZEN` integrity reason으로 HOLD한다.

기존 OpenAI/Terra V1 숫자를 자동 승계하지 않는다.

## Backup / Restore / Recovery

완료:

- backup manifest에 `jev_typesafe_evaluation_v2` extension 추가
- Evaluation V2 tables restore 경계 추가
- secret value 저장/복원 없음
- startup에서 RUNNING TypeSafe Evaluation V2 → INTERRUPTED recovery
- TypeSafe Core activation은 기존 §36 원칙대로 restore 후 `enabled=0 / allow_network=0`

## Tests / CI

Synthetic/fake-only 회귀 검증 포함:

- SKIPPED와 ABSTAIN 분리
- recruitment row 유지
- valid ABSTAIN projection
- stored disposition integrity mismatch 감지
- recruitment denominator
- ERROR candidate baseline retention
- REVIEW_REQUIRED만 virtual defer
- unknown cost를 0으로 간주하지 않음
- local-only Evaluation V2 migration
- Evaluation V2 catalog roundtrip
- Evaluation V2 backup/restore
- Local Sync migration order
- frontend TypeScript/build

Implementation CI run:

`37426330708`

결과:

- Frontend / Node 22: PASS
- Backend / Python 3.11: PASS
- Backend / Python 3.14: PASS
- Fresh Clone / Windows: PASS

## 실행하지 않은 것

- 실제 TypeSafe model discovery: NOT EXECUTED
- 실제 `GET /v1/models`: 0
- 실제 `POST /v1/systemone`: 0
- 실제 TypeSafe token consumption: 0
- 실제 provider cost: 0
- 실제 TypeSafe Trial: NOT STARTED
- 실제 TypeSafe Evaluation: NOT EXECUTED
- Trial V2 machine-readable frozen artifact: NOT CREATED
- final threshold numeric freeze: NOT DONE
- actual account retention/ZDR/billing binding: NOT VERIFIED
- R5R Actual Evaluation: NOT EXECUTED
- automatic adoption: NOT EXECUTED
- `JEV_API_KEY` actual secret value: NOT READ / NOT LOGGED / NOT STORED
- 잠긴 데이터 영역: LOCKED / NOT ACCESSED

## 현재 상태

`TYPE-JEV-DESIGN-FREEZE                COMPLETE`

`TYPE-JEV-CORE-CORRECTION              COMPLETE`

`TYPE-JEV-MONITOR-EVALUATION-CORRECTION COMPLETE`

다음 단계는 **TYPE-JEV-APPROVED-CANARY-TRIAL**이다.

이 다음 단계에서 처음으로 사용자 명시 승인 하에 TypeSafe 외부 사실(model discovery, account policy/billing, synthetic canary)을 확인하고, prospective actual trial 시작 전 Trial V2 artifact 및 final threshold/gates를 freeze한다.

실제 prospective efficacy trial은 canary/binding 검증과 별개이며, 자동으로 시작하지 않는다.

Phase 1 correction/canary/trial이 끝난 뒤에는 별도 **TYPE-JEV-EXPANSION-REVIEW** 문서를 작성하여 StockScope의 다른 fuzzy decision 영역에서 TypeSafe Jev가 실제 추가 가치를 주는지 검토한다.

