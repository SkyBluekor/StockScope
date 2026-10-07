# StockScope 인수인계 — TypeSafe Jev Canary V3 Protocol Freeze COMPLETE

작성일: 2026-10-07 (Asia/Seoul)
Authoritative continuation handoff for the next ChatGPT conversation.

## 1. 현재 기준점

- GitHub main 구현 HEAD: `76bce31abd99e3d597fb47e60d25fa20ab3c4fdd`
- Commit: `feat: freeze TypeSafe JEV Canary V3 protocol`
- 기숙사 PC의 마지막 확인 로컬 상태는 `C:\Projects\StockScope`, clean worktree, `25ee641`이었다.
- 따라서 다음 채팅에서는 먼저 `git pull`, `git log -1 --oneline`, `git status --short`를 확인한다.
- 이 handoff docs commit이 추가되므로 실제 최신 HEAD는 `76bce31`보다 이후일 수 있다. 중요한 것은 `76bce31`이 ancestry에 포함되는 것이다.

## 2. 사용자 작업 계약

- 사용자가 `다음 작업 명세해`라고 하면 명세만 작성한다. GitHub 변경 없음.
- 사용자가 `작업 시작해/진행해`라고 하면 직전에 승인된 명세만 구현한다.
- 완료된 설계는 실제 오류나 새 관찰이 전제를 깨뜨리지 않는 한 다시 열지 않는다.
- StockScope 목적은 AI/Jev 자체가 아니라 사용자의 주식 판단을 더 빠르고 명확하게 돕는 것이다.
- Jev는 baseline을 대체하지 않는다.

## 3. 절대 보안 경계

- Holdout은 명시적 사용자 허가 전 `content/search/metadata/hash/existence probe` 모두 금지.
- repository-wide 탐색으로 Holdout 이름이나 존재를 찾지 않는다.
- Canonical secret은 `JEV_API_KEY`.
- 실제 secret 값, prefix, 길이, hash, Authorization header를 읽거나 출력·로그·artifact·Git에 남기지 않는다.
- 실제 실행 단계에서도 credential 출력은 `PRESENT/ABSENT`만 허용.
- `R5R Actual Evaluation`, `TypeSafe Jev Actual Evaluation`, `Prospective Trial`은 아직 실행되지 않았다.

## 4. JEV 의미

`JEV = TypeSafe AI의 Jev / System One decision model`이다.

Jev가 소유하지 않는 것: Strategy eligibility, condition PASS/FAIL/count, Scanner action/rank, Risk status, 가격 산술, stop/target/RR, 매수/매도, Holdings action, 미래수익.

## 5. V1 / V2 역사 상태

V1은 historical diagnostic artifact이며 V3로 재해석하지 않는다.

V2 실제 synthetic Canary 확정 상태:

```text
CANARY V2 = EXECUTED / DIAGNOSTIC FAIL / PRESERVED
request model = jev-latest
request channel = STABLE_ALIAS
returned concrete = jev-1.13.0
selection = 12 fixtures × 3 = 36/36 valid
validation = NOT EXECUTED / 0 calls
error = CANARY_V2_NO_ELIGIBLE_THRESHOLD
final thresholds = NOT FROZEN
Trial V2 = BLOCKED
```

V2 tracked evidence:

```text
docs/contracts/JEV_TYPESAFE_MODEL_BINDING_V2.json
docs/validation/JEV_TYPESAFE_CANARY_V2_2026-10-06.json
```

V2 failure diagnosis: Q1은 promising이었지만 validation이 없었고, Q2/Q3는 현재 proposition/state 구조에서 hard separation이 불가능했다. V2를 threshold fitting으로 구제하지 않는다.

## 6. V3 architecture — 확정

Authoritative design:

`docs/설계/StockScope_TypeSafe_Jev_Canary_V3_질문경계재설계_v1_2026-10-06.md`

채택:

```text
ARCH C + D1
Q1 = KEEP / Jev
Q2 = STRUCTURE / local deterministic owner
Q3 = LOCALIZE / local completeness owner
provider questions = Q1 Noul 1개
```

V3 external wire는 오직 `strategy_intent`, `term_definitions`, `passed_condition_meanings` 세 영역이다.

Q2 entry rule, local conflict, readiness status, ticker/name/rank, price, risk, stop/target/RR, future outcome은 Q1 wire에 넣지 않는다.

## 7. Semantic Source Contract — 설계/구현 완료

설계 문서:

`docs/설계/StockScope_TypeSafe_Jev_V3_Semantic_Source_Contract_v1_2026-10-07.md`

구현 merge:

`f3eb17947c9440b223738e7f08985f7ff05d4dfa`

핵심 구현:

```text
backend/app/strategy/semantic_contract.py
backend/app/strategy/condition_semantics.py
backend/app/strategy/entry_semantics.py
backend/app/strategy/semantic_source.py
backend/app/jev/typesafe_state_v3.py
backend/app/jev/typesafe_questions_v3.py
backend/app/jev/typesafe_policy_v3.py
```

현재:

```text
10 operating strategy semantic contracts = IMPLEMENTED
NO_TRADE = excluded
Condition semantic mapping = deterministic/versioned
Q2 entry semantics = local deterministic
Q1/Q2 readiness = isolated
Prospective capture version = VN_P2_S2_CAPTURE_V2
Prospective SQL schema = unchanged
JEV V3 = Q1-only / 1 Noul / threshold_strategy only
V1/V2 dispatch = preserved
```

arbitrary prose/regex/LLM으로 semantic source를 복원하지 않는다. 과거 capture에 최신 semantic registry를 backfill하지 않는다. Q2 local 결과를 Jev 성과로 귀속하지 않는다.

## 8. Canary V3 Protocol Freeze — 구현 완료

핵심 commit:

`76bce31abd99e3d597fb47e60d25fa20ab3c4fdd`

변경 파일:

```text
backend/app/jev/typesafe_canary_v3.py
backend/app/jev/typesafe_canary_v3_fixtures.py
backend/tests/test_jev_typesafe_canary_v3.py
docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V3.json
tools/data/run_jev_typesafe_canary_v3.py
```

Machine-readable authority:

`docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V3.json`

Frozen identity:

```text
artifact_version = JEV_TYPESAFE_CANARY_PROTOCOL_ARTIFACT_V3
protocol_id = JEV-TYPESAFE-CANARY-V3
status = FROZEN_BEFORE_REAL_CALLS
protocol_hash = 3d1b711535e56931d9ba3e4e8d8db184e94f54f1f826d34478ad4bba8a09f356
frozen_at = 2026-10-07
```

## 9. V3 exact fixture architecture

```text
total contexts = 40
selection = 20 = 12 provider-callable + 8 local-only
validation = 20 = 12 provider-callable + 8 local-only
callable hard = 10 per partition
callable soft = 2 per partition
hard negative = 6 per partition
hard positive = 4 per partition
repetitions = 3 per callable fixture
selection System One planned = 36
validation System One planned = 36
max System One planned = 72
```

Selection/Validation은 V3의 새 synthetic contexts다. V1/V2 fixture를 acceptance set으로 재사용하지 않는다.

## 10. V3 threshold / acceptance freeze

Candidate grid:

`T_strategy = {0.50, 0.70, 0.90}`

Rule: `p >= T_strategy`, rounding 전 raw float 비교.

현재:

```text
selected_threshold = null
final_threshold_frozen = false
```

Selection hard gates는 hard proposition mismatch 0/30, false review 0/18, missed review 0/12, disposition/reason error 0, crossing 0, route/isolation/provider error 0, review_required <=18/36, ABSTAIN 0을 요구한다.

Eligible threshold가 여러 개면 soft REVIEW_REQUIRED 수 오름차순, 그 다음 threshold 내림차순으로 하나를 선택한다.

Eligible 0이면 `CANARY_V3_NO_ELIGIBLE_THRESHOLD`, validation calls 0, selected threshold null, Trial BLOCKED다. Validation은 선택된 threshold 하나만 사용하며 실패 후 다른 threshold/grid/gold로 구제하지 않는다.

## 11. Isolation hard gate

Frozen isolation families: `S-A`, `S-B`, `V-A`, `V-B`.

각 pair는 `projected_state_hash`와 canonical Q1 wire가 동일해야 하고 local entry result는 의도대로 달라야 한다. Q2 missing/conflict가 Q1 wire를 바꾸면 protocol preflight FAIL이다.

## 12. Model binding rule

```text
default request model = jev-latest
stable alias required = true
jev-preview = forbidden
```

실제 execution 때 model discovery는 최대 1회. 첫 valid System One concrete response model이 run binding이고 이후 valid response는 전부 같은 concrete identity여야 한다. 중간 model change는 FAIL.

V3 actual model binding은 아직 관측되지 않았다. 실제 `JEV_TYPESAFE_MODEL_BINDING_V3.json`은 아직 evidence가 아니다.

## 13. Attempt / budget / runtime caps

```text
model discovery max = 1
systemone attempts max = 72
total API attempts max = 73
retry = 0
concurrency = 1
deadline = 10 seconds
API budget cap = USD 0.25
per-call reservation = REQUIRED BEFORE EXECUTE, value not frozen
```

실패한 provider request도 attempt와 reservation exposure에서 제거하지 않는다. Selection FAIL이면 validation을 호출하지 않는다.

## 14. V3 runner

Runner:

`tools/data/run_jev_typesafe_canary_v3.py`

기본 실행은 zero-network dry run:

```powershell
.\.venv\Scripts\python.exe .\tools\data\run_jev_typesafe_canary_v3.py
```

Default dry-run은 credential lookup 0, `.env` access 0, network 0, real stock data 0, trial activation false, final threshold frozen false여야 한다.

`--execute` path는 준비돼 있지만 별도 명시적 사용자 승인 전 실행 금지.

## 15. Fake/offline harness coverage

`backend/tests/test_jev_typesafe_canary_v3.py`에는 exact 40 contexts, minimized/gold-free Q1 wire, isolation equality, local-only no-call, protocol drift rejection, threshold selection/tie-break, full mock PASS, selection FAIL→validation 0, failed attempt/reservation 유지, model identity change FAIL, budget preflight 검증이 구현돼 있다.

Mock full PASS는 1 discovery + 72 System One = 73 hard cap을 검증하도록 작성돼 있다.

### CI 주의

`76bce31`의 GitHub Actions run은 이 handoff 작성 시점 API에서 아직 관측되지 않았다. 다음 채팅에서 PASS라고 추정하지 말고 먼저 CI를 확인한다. 필요하면 local zero-network dry-run과 관련 tests를 실행한다.

## 16. 현재 공식 상태

```text
Docs Cleanup = COMPLETE
Canary V1 = HISTORICAL DIAGNOSTIC FAIL / PRESERVED
Canary V2 = EXECUTED / DIAGNOSTIC FAIL / PRESERVED
V3 Question/State Architecture = DESIGNED / ARCH C + D1
V3 Semantic Source Contract = DESIGNED + IMPLEMENTED
V3 Semantic Source Capture = IMPLEMENTED
V3 Core = Q1 ONLY / IMPLEMENTED
V3 Synthetic Fixtures = 40 / FROZEN
V3 Machine Protocol = FROZEN_BEFORE_REAL_CALLS
V3 protocol hash = 3d1b711535e56931d9ba3e4e8d8db184e94f54f1f826d34478ad4bba8a09f356
V3 Dry Run on current local PC = NOT YET CONFIRMED AFTER 76bce31 PULL
Real Canary V3 = NOT EXECUTED
V3 model binding = NOT OBSERVED
Final V3 threshold = NOT FROZEN
Trial = BLOCKED
Prospective Trial = NOT STARTED
Actual Jev Evaluation = NOT EXECUTED
R5R Actual Evaluation = NOT EXECUTED
Holdout = LOCKED / NOT ACCESSED
Real stock data sent during V3 protocol work = 0
Actual TypeSafe calls during V3 protocol-freeze work = 0
Actual secret access during V3 protocol-freeze work = 0
```

## 17. 바로 다음 작업

다음 단계는 실제 Canary V3 실행이 아니다.

`TYPE-JEV-CANARY-V3-EXECUTE-PREFLIGHT`

목표:

1. local main을 protocol-freeze commit 이상으로 pull
2. working tree clean 확인
3. zero-network V3 dry-run PASS 확인
4. CI 결과 확인
5. frozen protocol hash/runtime identity exact match 확인
6. current TypeSafe public model/pricing 조건 재확인
7. 계정별 model availability / billing / retention·privacy를 가능한 범위에서 확인
8. conservative per-call reservation을 근거와 함께 결정
9. planned maximum reservation이 USD 0.25 hard cap 이하인지 확인
10. 실제 synthetic 전송을 위한 별도 명시적 실행 승인을 받음

Preflight 자체는 System One call을 하지 않는다.

실제 API 호출은 별도 승인 후 `TYPE-JEV-CANARY-V3-EXECUTE` 단계에서만 한다.

## 18. 실제 execution 승인 후 규칙

아직 실행하지 않는다.

Runner 형태:

```powershell
.\.venv\Scripts\python.exe .\tools\data\run_jev_typesafe_canary_v3.py `
  --execute `
  --per-call-reservation-usd <PREFLIGHT에서 검증한 값>
```

Reservation 값을 임의로 추측하지 않는다.

실패 후 threshold를 찾기 위한 재실행, grid 확대, gold 수정, validation 뒤 차순위 threshold 적용은 금지. 실패는 DIAGNOSTIC FAIL로 보존하고 필요하면 새 contract/version으로 간다.

## 19. 다음 채팅 시작용 프롬프트

```text
StockScope 작업 이어서 진행하자.

먼저 docs/StockScope_인수인계_2026-10-07_JEV_CANARY_V3_PROTOCOL_FREEZE_COMPLETE.md 를 읽고 현재 main HEAD만 확인해. 이 문서를 authoritative handoff로 사용해.

현재 핵심 상태는:
- V2 Canary = EXECUTED / DIAGNOSTIC FAIL / PRESERVED
- V3 Architecture = ARCH C + D1 / Q1 Jev only / Q2 local / Q3 local
- V3 Semantic Source Contract = IMPLEMENTED
- Prospective Capture = VN_P2_S2_CAPTURE_V2
- V3 exact synthetic fixtures = 40 FROZEN
- JEV_TYPESAFE_CANARY_PROTOCOL_V3.json = FROZEN_BEFORE_REAL_CALLS
- protocol hash = 3d1b711535e56931d9ba3e4e8d8db184e94f54f1f826d34478ad4bba8a09f356
- Real Canary V3 = NOT EXECUTED
- Final V3 threshold = NOT FROZEN
- Trial = BLOCKED
- Holdout = LOCKED
- R5R Actual Evaluation = NOT EXECUTED

기숙사 로컬은 25ee641 clean 상태까지 확인한 뒤 GitHub main에 76bce31 protocol-freeze commit이 추가됐으니 먼저 git pull / git status를 확인해.

실제 TypeSafe 호출은 별도 명시적 승인 전 절대 하지 마.
JEV_API_KEY 실제 값도 읽거나 출력하지 마.
Holdout은 검색·metadata·hash·존재 probe 포함 접근 금지.

내가 다음 작업 명세해라고 하면 TYPE-JEV-CANARY-V3-EXECUTE-PREFLIGHT 명세만 작성하고 GitHub 변경은 하지 마.
내가 작업 시작해/진행해라고 하면 그 승인된 preflight 작업만 진행해.
실제 --execute는 preflight와 별개의 명시적 실행 승인 후에만 허용한다.
```

## 20. 이 handoff 작성 시 하지 않은 것

```text
TypeSafe real API call = 0
JEV_API_KEY/.env access = 0
Holdout access = 0
Canary V3 actual execution = 0
Trial activation = 0
R5R Actual Evaluation = 0
Actual Jev Evaluation = 0
```