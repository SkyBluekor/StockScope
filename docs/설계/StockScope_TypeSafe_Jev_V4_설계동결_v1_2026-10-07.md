# StockScope TypeSafe Jev V4 설계 동결 v1

작성일: 2026-10-07 (Asia/Seoul)  
상태: `TYPE-JEV-V4-DESIGN-FREEZE = COMPLETE`  
범위: 설계만 동결. V4 코드/fixture/protocol JSON/UI 구현/TypeSafe 호출은 이 문서에서 수행하지 않는다.

---

## 1. Executive decision

V3는 다음 상태로 영구 보존한다.

```text
Canary V3 = EXECUTED / DIAGNOSTIC FAIL / PRESERVED
System One = 72 / 72 valid
provider failure = 0
selection = PASS
selected experimental threshold = 0.9
validation = FAIL
final production threshold = NOT FROZEN
Trial = BLOCKED
Holdout = LOCKED
```

V4의 채택 architecture는 다음이다.

```text
ARCH V4 = LOCAL RELATION COMPOSITION + RESIDUAL Q1

Q1 = Jev, residual semantic review only
Q2 = local deterministic entry-role owner
Q3 = local semantic completeness/readiness owner

Baseline authority = unchanged
Jev authority = additional semantic review only
```

제품 실행 방식은 다음 두 모드로 동결한다.

```text
BASELINE_ONLY      = 기본값 / TypeSafe call 0
BASELINE_WITH_JEV  = 사용자 명시 opt-in / baseline 이후 별도 review
```

자동 Jev 실행은 V4 초기 제품 범위에서 금지한다.

---

## 2. V3 evidence preservation and canonicalization defect

### 2.1 실제 확인된 defect

V3 frozen artifact의 저장된 protocol hash field:

```text
3d1b711535e56931d9ba3e4e8d8db184e94f54f1f826d34478ad4bba8a09f356
```

저장된 JSON의 `spec` 자체를 현재 repository의 `digest_json()`으로 계산한 값:

```text
eb1ba813b9d2c803d0edf2c824ffaa233ae7bbcc0b2c2a9263e1cb0f07bb9e23
```

runtime에서 `build_canary_v3_protocol_artifact()`가 생성한 spec digest와 protocol hash:

```text
3d1b711535e56931d9ba3e4e8d8db184e94f54f1f826d34478ad4bba8a09f356
```

stored/runtime spec의 유일하게 확인된 차이:

```text
$.deadline_seconds
stored  = int(10)
runtime = float(10.0)
```

Python object equality에서는 `10 == 10.0`이므로 기존 exact-artifact 검사가 이를 drift로 잡지 못했다. canonical JSON byte representation은 서로 달라 hash는 달라졌다.

### 2.2 공식 분류

```text
V3 semantic protocol drift = NONE OBSERVED
V3 runtime behavior drift = NONE OBSERVED
V3 wire/fixture/question/gold drift = NONE OBSERVED
V3 serialization/canonicalization defect = CONFIRMED
V3 Canary rerun = NOT REQUIRED / FORBIDDEN
V3 diagnostic FAIL = PRESERVED
```

기존 `docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V3.json`을 사후 수정해 hash를 맞추지 않는다.

실제 실행으로 생성된 다음 파일은 V3 evidence이며 삭제·재생성·덮어쓰지 않는다.

```text
docs/contracts/JEV_TYPESAFE_MODEL_BINDING_V3.json
docs/validation/JEV_TYPESAFE_CANARY_V3_2026-10-07.json
```

이 설계 작성 시점에는 위 두 파일이 사용자 로컬에서 untracked였으므로, 후속 구현 단계의 첫 evidence-preservation 작업에서 **내용 변경 없이** secret/value 검사를 거쳐 tracked evidence로 보존한다.

---

## 3. V4 canonicalization contract

V4는 Python object equality를 protocol identity로 사용하지 않는다.

새 계약 식별자:

```text
canonicalization_version = JEV_PROTOCOL_CANONICAL_JSON_V2
hash_algorithm = SHA-256
```

### 3.1 numeric normalization

V4는 JSON 숫자의 의미적 동등성을 canonical identity에 반영한다.

규칙:

1. boolean은 number와 별도 타입이다.
2. NaN, +Inf, -Inf는 금지한다.
3. 정수는 canonical integer로 직렬화한다.
4. 유한 float가 수학적으로 정수이면 canonical integer로 normalize한다.
   - `10.0 -> 10`
   - `0.0 -> 0`
5. 비정수 finite number는 locale에 독립적인 shortest deterministic decimal representation을 사용한다.
6. object key는 UTF-8 key 기준 lexical ascending으로 정렬한다.
7. array 순서는 보존한다.
8. whitespace는 사용하지 않는다.
9. string은 UTF-8 JSON string으로 고정한다.

구현 단계에서 Python별 우연한 `json.dumps()` behavior가 아니라 별도 versioned canonicalizer를 둔다.

### 3.2 frozen artifact hard gate

V4 freeze/load/execute 전 반드시 모두 참이어야 한다.

```text
canonical_bytes(stored.spec) == canonical_bytes(runtime.spec)

stored.protocol_hash
    == sha256(canonical_bytes(stored.spec))

sha256(canonical_bytes(stored.spec))
    == sha256(canonical_bytes(runtime.spec))
```

또한 stored artifact 전체의 canonical identity를 별도 artifact hash로 기록한다.

단순 `stored == runtime`만으로 PASS 처리하는 것은 금지한다.

---

## 4. Production semantic reachability audit

현재 production Q1 source는 `project_passed_condition_meanings()`에서 다음을 모두 요구한다.

```text
total == expected condition count
missing == 0
passed == total
```

즉 현재 `CONDITION_SEMANTIC_MAPPING_V1`은 **모든 조건이 PASS인 candidate**에 대해서만 Q1 meanings를 materialize한다.

현재 10개 operating strategy의 repository-controlled PASS meanings를 authored strategy intent와 대조한 결과는 다음과 같다.

| Strategy | 현재 production PASS 의미의 방향 | 현재 positive semantic conflict reachability | V4 분류 |
|---|---|---:|---|
| TREND_FOLLOWING | 상승 구조, HH/HL, 상대강도, 상승장 지지 | 없음 | PRODUCTION_LOCAL_MATCH |
| PULLBACK | 상승 기반, 지지 근접, HL 유지, 비음수 상대강도 | 없음 | PRODUCTION_LOCAL_MATCH |
| BREAKOUT | 고점 근접, 거래량 증가, 상승 slope/RS/시장 | 없음 | PRODUCTION_LOCAL_MATCH |
| SUPPORT_BOUNCE | 지지 근접, bounded volatility, low 유지, 비급락 | 없음 | PRODUCTION_LOCAL_MATCH |
| OVERSOLD_BOUNCE | oversold, 지지 근접, bounded volatility, no panic, low 미붕괴 | 없음 | PRODUCTION_LOCAL_MATCH |
| RANGE_TRADING | range regime, flat slope, 지지/저항 여유, bounded volatility | 없음 | PRODUCTION_LOCAL_MATCH |
| MOMENTUM_CONTINUATION | strong slope, volume, HH/HL, RS, 비급락 | 없음 | PRODUCTION_LOCAL_MATCH |
| VOLATILITY_SQUEEZE | compression, near-high/reference, non-declining slope, 비급락 | 없음 | PRODUCTION_LOCAL_MATCH |
| MA20_REBOUND | MA20 근접/상승, HL, rebound-compatible momentum, 비급락 | 없음 | PRODUCTION_LOCAL_MATCH |
| TREND_RECOVERY | MA20 회복, 급락 아님, recovering HL, 지지 근접, no panic | 없음 | PRODUCTION_LOCAL_MATCH |

### 4.1 중요한 결론

현재 V1 production mapping에서는 V3 synthetic positive와 같은 다음 문장은 authoritative PASS source에서 직접 생성되지 않는다.

```text
support integrity has failed
structural deterioration is continuing
volatility is expanding beyond the bounded range
participation is contracting instead of supporting the move
directional structure has weakened materially
```

따라서 V3의 positive synthetic families는 현재 제품 acceptance 관점에서는 다음으로 분류한다.

```text
ROBUSTNESS_ONLY
```

특히 V3 `v3-v06`의 range collapse는 현재 `RANGE_TRADING` production PASS mapping에서 도달 불가능하다.

### 4.2 제품 의미

현재 source만으로는 **production에서 Jev가 발견해야 하는 positive residual conflict가 입증되지 않았다.**

따라서 다음은 금지한다.

- Jev 호출량을 만들기 위해 synthetic conflict를 production source에 인위적으로 삽입
- 이미 deterministic PASS인 사실을 부정문으로 재작성해 Jev에게 전달
- provider 사용 자체를 목표로 relation ambiguity를 의도적으로 생성

V4는 이 사실을 architecture의 activation gate로 사용한다.

---

## 5. V4 semantic relation contract

새 설계 식별자:

```text
STRATEGY_SEMANTIC_RELATION_CONTRACT_V1
CONDITION_SEMANTIC_ASSERTION_MAPPING_V1
JEV_SEMANTIC_SOURCE_V2
```

### 5.1 authored concept

각 strategy는 기존 definition을 concept identity로 승격한다.

```json
{
  "concept_id": "trend_structure",
  "definition_id": "trend_structure"
}
```

concept text는 기존 repository-authored definition에서만 가져온다. LLM/regex로 생성하지 않는다.

### 5.2 relation schema

허용 relation kind:

```text
REQUIRES_ALL
REQUIRES_ANY
ALLOWS_IF
EXCLUDES
```

고정 shape:

```json
{
  "relation_id": "relation-...",
  "kind": "REQUIRES_ALL",
  "members": ["concept-a", "concept-b"],
  "guards": [],
  "materiality": "HARD"
}
```

규칙:

- `REQUIRES_ALL`: members가 모두 관계를 지지해야 한다.
- `REQUIRES_ANY`: members 중 최소 하나가 관계를 지지해야 한다.
- `ALLOWS_IF`: members로 표현된 약화/예외는 guards가 유지될 때만 허용한다.
- `EXCLUDES`: members가 명시적으로 성립하면 authored intent와 양립할 수 없다.
- `guards`는 `ALLOWS_IF`에서만 필수이며 다른 kind에서는 빈 배열이다.
- `materiality`는 `HARD | SOFT`만 허용한다.

### 5.3 condition semantic assertion

각 repository-controlled condition meaning은 concept binding을 가진다.

```json
{
  "condition_id": "condition-01",
  "concept_refs": ["trend_structure"],
  "stance": "SUPPORTS"
}
```

허용 stance:

```text
SUPPORTS
WEAKENS
CONTRADICTS
NEUTRAL
UNRESOLVED
```

`stance`는 repository-authored mapping이다. runtime prose 추론으로 만들지 않는다.

---

## 6. Local semantic composition

V4 local owner는 authored relation + authored condition assertion을 결합한다.

결과 enum:

```text
LOCAL_MATCH
LOCAL_CONFLICT
LOCAL_INCOMPLETE
LOCAL_AMBIGUOUS
RESIDUAL_SEMANTIC_REVIEW
```

### 6.1 deterministic rules

- required concept 또는 relation binding이 없으면 `LOCAL_INCOMPLETE`
- 같은 concept에 mutually incompatible authored assertions가 동시에 있으면 `LOCAL_AMBIGUOUS`
- HARD relation을 `CONTRADICTS` assertion이 명시적으로 위반하면 `LOCAL_CONFLICT`
- HARD relation의 충족 여부가 `WEAKENS` 또는 `UNRESOLVED`에 의존하면 `RESIDUAL_SEMANTIC_REVIEW`
- 모든 HARD relation이 deterministic하게 충족되고 unresolved material relation이 없으면 `LOCAL_MATCH`
- SOFT relation의 unresolved 의미가 사용자 재확인 가치가 있도록 authored되어 있으면 `RESIDUAL_SEMANTIC_REVIEW`

### 6.2 Jev attribution

```text
LOCAL_MATCH / LOCAL_CONFLICT / LOCAL_INCOMPLETE / LOCAL_AMBIGUOUS
= Jev performance로 계산하지 않음

RESIDUAL_SEMANTIC_REVIEW
= Q1 provider eligibility
```

local 결과와 Jev 결과의 probability를 합산하거나 하나의 score로 만들지 않는다.

---

## 7. V4 Q1 scope and wire

Q1은 1개를 유지한다.

역할:

> 로컬 deterministic composition으로 확정되지 않고 남은 authored semantic relation과 supplied passed meanings 사이에, 사용자가 다시 확인할 가치가 있는 명시적·중대한 의미 충돌이 있는지 검토한다.

새 external wire의 top-level은 다음 4개만 허용한다.

```text
strategy_intent
term_definitions
authored_relations
passed_condition_meanings
```

예시:

```json
{
  "strategy_intent": {"text": "..."},
  "term_definitions": [
    {"ref": "term-01", "text": "..."}
  ],
  "authored_relations": [
    {
      "ref": "relation-01",
      "kind": "ALLOWS_IF",
      "member_refs": ["term-01"],
      "guard_refs": ["term-02"],
      "materiality": "HARD"
    }
  ],
  "passed_condition_meanings": [
    {
      "ref": "condition-01",
      "concept_refs": ["term-01"],
      "meaning": "..."
    }
  ]
}
```

provider wire에 다음을 넣지 않는다.

```text
local composition result
stance
gold
expected disposition
Q2 status/result
ticker/name/rank
capture id
price/current price
risk
stop/target/RR
buy/sell
holdings
future return
news
account/user identity
```

`concept_refs`는 authored structural binding이지 local verdict가 아니다.

---

## 8. Ownership boundary

V4에서도 다음은 Jev가 소유하지 않는다.

```text
Strategy eligibility
condition PASS/FAIL/count
Scanner action/rank
Risk status
price arithmetic
entry/stop/target/RR
BUY/SELL
Holdings action
future outcome/return
Q2 entry-role correctness
Q3 semantic completeness
```

Jev 출력은 오직:

```text
PASS_THROUGH
REVIEW_REQUIRED
```

의 additional semantic review다.

---

## 9. V4 threshold-selection contract

V4 candidate grid는 V3와 동일하게 유지하여 grid 확장을 사후 구제 수단으로 사용하지 않는다.

```text
T_strategy = {0.50, 0.70, 0.90}
comparison = raw p >= T_strategy
round-before-compare = false
```

### 9.1 hard selection gate

각 candidate threshold는 selection에서 다음을 모두 만족해야 eligible이다.

```text
hard false review = 0
hard missed review = 0
hard disposition/reason error = 0
provider error = 0
route/isolation error = 0
hard disposition crossing across repetitions = 0
```

### 9.2 class margin

hard positive/negative **unique Q1 wires**만 사용한다.

```text
positive_margin(T) = min(all hard-positive repetition p) - T
negative_margin(T) = T - max(all hard-negative repetition p)

worst_class_margin(T)
    = min(positive_margin(T), negative_margin(T))
```

selection eligibility 추가 조건:

```text
positive_margin >= 0.10
negative_margin >= 0.10
worst_class_margin >= 0.10
```

이 0.10은 V3를 소급 구제하기 위한 값이 아니라, V3에서 +0.01 separation이 unseen 표현에 취약했던 사실을 반영한 **V4 사전 안전 여유**다.

### 9.3 tie-break

eligible threshold가 여러 개면 다음 순서로 하나만 고른다.

```text
1. worst_class_margin DESC
2. soft_review_required_count ASC
3. threshold_strategy ASC
```

마지막 ascending rule은 동일 margin일 때 high-threshold 자동 선호를 제거하기 위한 최종 tie-break일 뿐이며 hard margin 조건을 우회하지 않는다.

### 9.4 validation

- selection에서 선택된 threshold 하나만 사용
- validation fallback 금지
- validation 뒤 grid/threshold/gold 수정 금지
- validation에서도 hard error 0 및 양 class margin >= 0.10 요구
- FAIL이면 V4 Canary는 diagnostic FAIL로 보존

---

## 10. V4 fixture/partition design rule

이 문서에서는 실제 fixture 문장을 생성하지 않는다.

필수 broad failure mode:

```text
DIRECT_CONTRADICTION
REQUIRED_CONDITION_COLLAPSE
COMPOSITIONAL_CONFLICT
ALLOWED_EXCEPTION
WEAK_SEMANTIC_PHRASING
NEAR_BOUNDARY_AMBIGUITY
NEGATIVE_TRAP
LOCAL_DETERMINISTIC_CONFLICT
LOCAL_MISSING
LOCAL_AMBIGUOUS
Q1_Q2_ISOLATION
```

### 10.1 leakage rule

각 fixture는 다음 두 identity를 가진다.

```text
failure_mode
semantic_scenario_id
```

같은 `semantic_scenario_id`의 phrase variants는 반드시 같은 partition에 둔다.

Selection/Validation 모두 같은 broad `failure_mode`를 가질 수 있지만, scenario/concept/strategy 조합은 서로 독립이어야 한다.

즉 validation은 selection 문장의 단순 paraphrase가 아니다.

### 10.2 production vs robustness

각 provider fixture는 반드시 다음 중 하나로 표시한다.

```text
PRODUCTION_REACHABLE
ROBUSTNESS_ONLY
```

제품 activation gate 계산에는 `PRODUCTION_REACHABLE` 결과를 별도로 보고한다.

현재 V1 source에서는 positive production-reachable residual conflict가 확인되지 않았으므로, V4 fixture 구현 단계에서 이를 억지로 만들어서는 안 된다.

---

## 11. Repetition and duplicate-wire rule

V4 기본 반복:

```text
5 repetitions per unique Q1 wire
retry = 0
concurrency = 1
```

동일 `projected_state_hash`를 가진 isolation fixture는 provider에 별도 독립 fixture처럼 중복 전송하지 않는다.

한 partition/repetition에서 같은 Q1 wire는 **한 번만 호출**하고 해당 provider response를 동일-wire isolation rows에 공유한다.

따라서:

```text
provider attempt count
= unique provider Q1 wires × 5
```

이지 fixture row 수 × 5가 아니다.

이는 V3의 동일-wire v07/v08을 별도 의미 표본처럼 보이게 했던 혼동을 제거하고 비용도 줄인다.

---

## 12. Budget contract

V4 Canary exact fixture count가 생성되기 전에는 임의 call count를 동결하지 않는다.

Protocol freeze 전 반드시 다음을 계산한다.

```text
unique selection provider wires
unique validation provider wires
planned System One calls
model discovery attempts
total attempt hard cap
max request size
current public/account pricing evidence
per-call reservation
max reserved exposure
```

V4 Canary budget 규칙:

```text
retry = 0
model discovery max = 1
reserved exposure <= USD 0.05
project absolute ceiling <= USD 0.25
```

정확한 per-call reservation은 실행 preflight에서 최신 가격/계정 조건을 확인한 뒤 고정한다.

---

## 13. Product execution modes

정식 backend mode 이름을 다음으로 동결한다.

```text
BASELINE_ONLY
BASELINE_WITH_JEV
```

### 13.1 BASELINE_ONLY

기본값이다.

```text
StockScope baseline pipeline 실행
prospective capture 가능
semantic source capture 가능
Jev queue scheduling = 0
provider construction = 0
TypeSafe model discovery = 0
System One = 0
```

현재 Scanner 완료 뒤 무조건 `try_schedule_capture()`를 호출하는 경로는 V4 구현 시 execution-mode gate 뒤로 이동해야 한다.

### 13.2 BASELINE_WITH_JEV

baseline을 다시 계산하는 별도 Scanner 실행을 의미하지 않는다.

권장 orchestration:

```text
baseline Scanner 완료
→ immutable candidate/capture 선택
→ 사용자가 "Jev 추가 검토" 클릭
→ BASELINE_WITH_JEV follow-up review request
→ semantic readiness
→ local composition
→ provider eligibility
→ 필요할 때만 Q1 최대 1회
```

따라서 UI 버튼을 여러 번 눌러 Scanner 전체를 다시 돌리지 않는다.

---

## 14. UI contract

초기 UI:

```text
[ 기본 분석 ]          기본/항상 사용 가능
[ Jev 추가 검토 ]      명시 opt-in
```

자동 Jev 모드는 V4 초기 범위에서 제공하지 않는다.

Baseline과 Jev review는 같은 카드의 단일 결론으로 합치지 않는다.

예:

```text
StockScope 분석
현재 판단: 관찰 필요

----------------

Jev 추가 검토
추가 의미 충돌 없음
```

또는:

```text
Jev 추가 검토
재확인 권장
전략 의도와 통과 조건의 의미를 다시 확인하세요.
```

금지 UI:

```text
Jev 추천: 매수
Jev 판단: 매도
Jev 목표가
Jev 위험도
```

---

## 15. UI/backend review state machine

내부 status:

```text
NOT_REQUESTED
UNAVAILABLE
NOT_READY
QUEUED
RUNNING
PASS_THROUGH
REVIEW_REQUIRED
SKIPPED
ERROR
```

필수 reason 예:

```text
FEATURE_NOT_ACTIVATED
SEMANTIC_SOURCE_NOT_READY
NO_RESIDUAL_SEMANTIC_REVIEW
LOCAL_CONFLICT_ALREADY_DETERMINED
DUPLICATE_REVIEW_REUSED
PROVIDER_ERROR
```

사용자 표시 예:

| 내부 상태 | 사용자 문구 |
|---|---|
| NOT_REQUESTED | 아직 추가 검토를 실행하지 않았습니다 |
| UNAVAILABLE | 현재 Jev 추가 검토를 사용할 수 없습니다 |
| NOT_READY | 이 분석은 아직 추가 검토 준비가 되지 않았습니다 |
| QUEUED/RUNNING | 추가 검토 중 |
| PASS_THROUGH | 추가 의미 충돌이 발견되지 않았습니다 |
| REVIEW_REQUIRED | 전략 의미를 다시 확인하는 것이 좋습니다 |
| SKIPPED + NO_RESIDUAL_SEMANTIC_REVIEW | 현재는 AI 추가 판단이 필요하지 않습니다 |
| ERROR | 추가 검토를 완료하지 못했습니다. 기본 분석 결과는 그대로 유효합니다 |

---

## 16. Idempotency/cache contract

동일 semantic snapshot의 반복 클릭으로 TypeSafe를 재호출하지 않는다.

새 identity version:

```text
JEV_REVIEW_IDENTITY_V1
```

review identity 구성:

```text
semantic_source_snapshot_hash
relation_contract_hash
question_set_hash
disposition_policy_hash
threshold_strategy
requested_model_channel
review_epoch
```

위 값의 canonical digest를 idempotency key로 사용한다.

`observed_response_model`은 결과 evidence에 기록하지만 최초 pre-call key에 포함하지 않는다.

rolling alias가 이후 바뀌더라도 같은 snapshot 버튼 반복 클릭은 기존 결과를 재사용한다. 운영자가 새 모델로 재평가해야 할 경우 자동 재호출하지 않고 `review_epoch` 또는 contract version을 명시적으로 올린다.

---

## 17. Failure policy

Jev failure는 baseline failure가 아니다.

```text
baseline_status = VALID
jev_review_status = ERROR
```

provider timeout/auth/rate-limit/unavailable/model-change 등으로 Jev가 실패해도 Scanner 결과, risk, holdings, 가격 판단을 변경하지 않는다.

Jev failure를 이유로 baseline candidate를 제거하거나 순위를 변경하지 않는다.

---

## 18. Activation gate

UI 구조 구현과 Jev 기능 활성화는 분리한다.

현재:

```text
V3 = FAIL
V4 = DESIGN ONLY
Jev user feature = DISABLED_VALIDATION_PENDING
```

실제 Jev 버튼을 enabled 상태로 전환하려면 최소:

```text
V4 implementation complete
V4 protocol canonical freeze PASS
V4 Canary PASS
production reachability/value evidence reviewed
trial policy separately approved/frozen
```

가 필요하다.

특히 current V1 semantic source에서 production positive residual이 0으로 확인된 상태에서는 synthetic robustness PASS만으로 production utility를 주장할 수 없다.

---

## 19. V3 evidence follow-up rule

후속 구현의 첫 단계는 다음 두 로컬 actual-run evidence를 **내용 변경 없이** 확인하고 추적하는 것이다.

```text
docs/contracts/JEV_TYPESAFE_MODEL_BINDING_V3.json
docs/validation/JEV_TYPESAFE_CANARY_V3_2026-10-07.json
```

검사:

- secret value/prefix/hash 없음
- Authorization header 없음
- real stock payload 없음
- synthetic records만 존재
- observed model/budget/usage/result가 실제 실행 로그와 일치

V3 protocol JSON 자체는 수정하지 않는다.

canonicalization defect는 본 문서를 V3 errata authority로 사용한다.

---

## 20. Implementation order after this freeze

V4 구현은 한 번에 모두 섞지 않는다.

### V4-I0 — V3 evidence preservation + canonicalizer

- actual V3 evidence track
- `JEV_PROTOCOL_CANONICAL_JSON_V2`
- strict canonical hash validation tests
- int/float regression test

### V4-I1 — semantic relation source

- `STRATEGY_SEMANTIC_RELATION_CONTRACT_V1`
- `CONDITION_SEMANTIC_ASSERTION_MAPPING_V1`
- local composition truth table
- reachability tests for 10 strategies
- `JEV_SEMANTIC_SOURCE_V2`

### V4-I2 — residual Q1 core

- V4 state projector
- V4 Q1 contract
- V4 policy
- no-call routing for local terminal states
- V1/V2/V3 historical dispatch preserved

### V4-I3 — execution mode/backend boundary

- `BASELINE_ONLY`
- `BASELINE_WITH_JEV`
- remove unconditional shadow scheduling from baseline path
- idempotent follow-up review endpoint
- baseline failure independence

### V4-I4 — UI shell

- 기본 분석 / Jev 추가 검토
- status state machine
- V4 activation 전 disabled state
- baseline/Jev visual separation

### V4-I5 — Canary fixture/protocol freeze

- fixture generation
- partition leakage audit
- 5 repetitions / unique-wire dedupe
- margin threshold policy
- exact cost/attempt caps
- machine-readable frozen protocol

실제 Canary 실행은 다시 별도 preflight와 명시적 사용자 승인 뒤에만 가능하다.

---

## 21. Security and holdout boundary

이 설계 이후에도 다음은 변하지 않는다.

```text
Holdout content access = forbidden
Holdout search = forbidden
Holdout metadata/hash/existence probe = forbidden

JEV_API_KEY value/prefix/length/hash logging = forbidden
Authorization header logging = forbidden

real stock data in synthetic Canary = forbidden
```

Holdout은 별도 명시적 사용자 승인 전 어떤 V4 구현 단계에서도 접근하지 않는다.

---

## 22. Frozen decisions vs intentionally open values

### 이번 문서에서 동결

- V3 FAIL 보존 및 rerun 금지
- V3 canonicalization defect 분류
- V4 canonicalization V2 원칙
- local relation composition + residual Q1 architecture
- Q2/Q3 local 유지
- V4 Q1 1개
- V4 wire 4영역
- threshold grid `{0.50, 0.70, 0.90}`
- class-margin 0.10 hard gate
- margin-based tie-break
- 5 repetitions per unique Q1 wire
- 동일 wire provider-call dedupe
- `BASELINE_ONLY` / `BASELINE_WITH_JEV`
- manual opt-in only
- idempotent review
- baseline/Jev result 분리
- feature activation gate

### fixture/protocol 구현 전까지 열어둠

- 실제 V4 fixture 문장
- 정확한 unique wire 개수
- 정확한 System One planned call 수
- per-call reservation
- exact V4 protocol hash
- final selected threshold
- actual concrete model binding
- production Jev utility

열어둔 값은 실제 selection/validation 결과를 보기 전에 별도 protocol-freeze 단계에서 닫는다.

---

## 23. Completion statement

```text
TYPE-JEV-V4-DESIGN-FREEZE = COMPLETE

V3 = EXECUTED / DIAGNOSTIC FAIL / PRESERVED
V3 canonicalization defect = DOCUMENTED
V3 rerun = FORBIDDEN

V4 architecture = LOCAL RELATION COMPOSITION + RESIDUAL Q1
V4 Q2/Q3 = LOCAL
V4 provider question count = 1

Production reachability audit =
current V1 PASS mappings expose no confirmed positive residual conflict

Execution mode =
BASELINE_ONLY default
BASELINE_WITH_JEV explicit opt-in

Jev feature activation =
DISABLED_VALIDATION_PENDING

V4 implementation = NOT STARTED
V4 fixture generation = NOT STARTED
V4 Canary = NOT EXECUTED
TypeSafe calls during design = 0
Holdout access = 0
```

다음 작업은 `V4-I0 — V3 evidence preservation + canonicalizer` 명세/구현이다.
