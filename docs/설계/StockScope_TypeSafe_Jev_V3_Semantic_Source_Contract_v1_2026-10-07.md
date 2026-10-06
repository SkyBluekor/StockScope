# StockScope TypeSafe Jev V3 Semantic Source Contract v1

작성일: 2026-10-07 (Asia/Seoul)  
모드: **DESIGN / ANALYSIS ONLY**  
분석 기준 repository HEAD: `155aebce115841b2cbec4a74fd527a9d81a0c4bc`  
산출물: 이 Markdown 문서 하나. source code, runtime DB, migration, frontend, Canary V3 protocol을 변경하지 않는다.

## 1. 결정 요약

이번 문서는 V3 질문·상태 경계 재설계의 결정을 다시 열지 않는다.

- Q1 `strategy semantic conflict`: **KEEP / external Jev candidate**
- Q2 `entry-rule semantic conflict`: **STRUCTURE / local deterministic owner**
- Q3 `semantic evidence completeness`: **LOCALIZE / local deterministic owner**
- 외부 provider 질문 수: callable candidate당 **Q1 Noul 1개**
- Q1 wire: `strategy_intent + term_definitions + passed_condition_meanings`만 허용
- Q2/Q3 정보는 Q1 provider state에 넣지 않는다.
- V1/V2 history, report, model binding, threshold는 변경하지 않는다.
- V3 Canary와 Trial은 계속 BLOCKED다.

이번 작업의 핵심 결론은 **semantic truth를 analysis 시점에 최신 registry에서 재구성하지 않고, candidate capture 시점에 authoritative source와 version/hash를 함께 snapshot으로 고정한다**는 것이다.

최종 readiness는:

`V3 IMPLEMENTATION = READY FOR SEPARATE APPROVAL / SOURCE CHANGES REQUIRED`

이다.

현재 production snapshot이 필요한 semantic field를 이미 충분히 제공한다는 뜻은 아니다. 오히려 핵심 field 다수가 `NEEDS_SOURCE_CHANGE`다. 다만 아래에서 owner, provenance, version/hash, capture boundary, failure behavior까지 닫았기 때문에 source contract 자체에는 미해결 provenance blocker가 남지 않는다.

---

## 2. 현재 코드에서 확인한 사실

### 2.1 Strategy implementation identity는 이미 version/hash로 관리된다

`backend/app/simulation/strategy_governance.py::strategy_definition()`은 `StrategyEngine`의 strategy method AST와 shared engine AST를 canonical payload로 만들고 `definition_hash` 및 deterministic `strategy_version_id`를 생성한다.

현재 definition payload는 대략 다음 의미다.

```text
strategy implementation identity
= strategy method AST
+ shared risk/action/scoring AST
+ scope metadata
```

`tools/data/migrate_strategy_governance_vnp5s1.py`의 `strategy_registry_version`에는 다음이 이미 있다.

- `strategy_version_id`
- `strategy_key`
- `definition_version`
- `definition_hash`
- `fingerprint_contract_version`
- `implementation_key`
- `definition_json`

즉 **strategy implementation provenance 자체는 이미 authoritative하다.**

하지만 현재 `definition_json`은 authored strategy intent, semantic definition manifest, entry-role intent를 담는 semantic contract가 아니다. AST fingerprint를 semantic prose로 해석하거나 자동 요약하여 V3 source로 쓰면 안 된다.

### 2.2 Production selection pin은 strategy version/hash를 Scanner-side payload까지 전달할 수 있다

`backend/app/strategy/production_selection_policy.py::SelectionPolicyPin.strategy_reference()`는 operating strategy에 대해 `strategy_version_id`, `strategy_key`, `definition_hash`를 제공한다.

`backend/app/strategy/service.py::_evaluation_payloads()`는 해당 reference를 evaluation payload의:

- `strategy_version_id`
- `strategy_definition_hash`

로 복사한다.

따라서 새 semantic contract는 "현재 어떤 strategy implementation version에 붙은 의미 계약인가"를 별도 추측 없이 bind할 수 있다.

### 2.3 현재 condition output에는 deterministic evaluation 사실이 있지만 V3 semantic source contract는 없다

`StrategyAnalysisService._automatic_checks()`는 condition별로 다음 형태의 deterministic output을 만든다.

```text
key
label
status
value
explanation
source
```

status는 numeric/boolean input과 strategy-specific local rule로 결정된다. 예를 들어 moving-average slope, volume, RSI, relative strength 등은 local code가 PASS/WARN/FAIL을 정한다.

이 output은 useful source evidence지만 그대로 V3 Q1 wire로 쓰지 않는다.

이유:

1. `value`는 formatting된 numeric text일 수 있다.
2. `explanation`은 user-facing 문구이며 semantic contract version으로 관리되지 않는다.
3. 현재 V2 projector의 metric naming과 `auto_checks.key`가 1:1 contract로 닫혀 있지 않다.
4. Q1은 numeric PASS/FAIL 재판정을 Jev에 맡기면 안 된다.

따라서 future owner는 **deterministic evaluator + versioned fixed semantic mapping**의 조합이다.

### 2.4 현재 RiskPlan은 Q2의 authoritative entry-role source가 아니다

`backend/app/risk/models.py::RiskPlan`과 `RiskEngine`은 entry reference price, stop/target/risk 구조를 만든다. 현재 확인한 production model에는 V2 synthetic state에서 사용한:

- `semantic_role`
- `executable_entry_range`
- same-rule `reference_id`

를 authoritative contract로 제공하는 source가 없다.

따라서 V2 synthetic `entry_context.price_rule` shape를 현재 production source가 이미 제공한다고 간주하면 안 된다.

Q2는 새 source contract가 필요하다.

### 2.5 Prospective capture는 candidate snapshot을 그대로 immutable snapshot_json에 넣을 수 있다

`backend/app/prospective/catalog.py::finalize_capture()`는 Scanner result의 candidate dict를 복사하여 `snapshot_json` 및 `snapshot_hash`로 저장한다. `source_snapshot_hash` 계산에도 candidate 전체가 포함된다.

따라서 nested semantic source snapshot을 candidate에 추가하는 경우 **새 SQL column 없이도 immutable capture에 포함할 수 있다.**

하지만 snapshot 의미 계약이 바뀌므로 `PROSPECTIVE_CAPTURE_VERSION`은 bump해야 한다.

과거 capture의 snapshot을 새 semantics로 backfill하지 않는다.

---

## 3. Source class

각 future field를 아래 네 종류로 분류한다.

- **A — EXISTING_AUTHORITATIVE**: 현재 canonical source가 있으며 그대로 쓸 수 있음
- **B — EXISTING_BUT_INSUFFICIENT**: 관련 값은 있으나 semantic provenance/version이 부족
- **C — DERIVABLE_DETERMINISTIC**: authoritative inputs에서 local deterministic 계산 가능
- **D — NEW_SOURCE_CONTRACT_REQUIRED**: 현재 canonical source에 없어서 새 contract가 필요

이 분류는 "코드가 비슷한 문자열을 가지고 있다"와 "V3 semantic truth가 이미 존재한다"를 구분하기 위한 것이다.

---

## 4. Source lineage 최종표

| Semantic fact | 현재 source | class | future authoritative owner | capture snapshot | provider 전송 |
|---|---|---|---|---|---|
| strategy implementation identity | Strategy Governance `strategy_version_id/definition_hash` | A | 기존 Strategy Governance | YES | NO |
| strategy Q1 intent | 없음. AST/설명문에서 추론 금지 | D | **Strategy Semantic Contract** | YES | Q1 only |
| required semantic definition IDs | 없음 | D | Strategy Semantic Contract | YES | 필요한 definition만 |
| semantic definitions | 없음 | D | Strategy Semantic Contract | YES | Q1 referenced subset |
| deterministic condition result | Strategy evaluator / auto checks | A/B | 기존 evaluator | YES | 직접 전송 NO |
| condition observed meaning | user-facing explanation은 있으나 semantic contract 아님 | D/C | **Condition Semantic Mapping + evaluator result** | YES | Q1 only |
| price-rule intended role | authoritative source 없음 | D | Strategy Semantic Contract의 Entry Rule Definition | YES | NO |
| intended rule ID | authoritative source 없음 | D | Strategy Semantic Contract | YES | NO |
| represented rule ID | authoritative source 없음 | D | **Entry Rule Representation contract** | YES | NO |
| represented role | production authoritative semantic role 없음 | D | Entry Rule Representation contract | YES | NO |
| executable-entry flag | V3용 authoritative source 없음 | D | Entry Rule Representation contract | YES | NO |
| Q1 semantic readiness | source fields에서 계산 | C | Local Semantic Readiness Evaluator | derived+snapshot | NO |
| Q2 semantic result | intent/representation에서 계산 | C | Local Entry Semantic Checker | derived+snapshot | NO |
| overall semantic source snapshot hash | 없음 | C | capture assembler | YES | NO |

핵심은 **intended role과 represented role이 서로 다른 provenance를 갖는 것**이다.

represented role에서 intended role을 복사하거나, 둘 다 같은 helper가 같은 값을 두 번 내보내는 구조는 금지한다.

---

## 5. Strategy Semantic Contract

### 5.1 별도 companion artifact를 채택한다

현재 `strategy_registry_version.definition_json`은 implementation AST fingerprint다.

V3 semantic intent를 여기에 직접 섞어 기존 `definition_hash` 의미를 바꾸지 않는다.

새 논리 artifact:

```text
STRATEGY_SEMANTIC_CONTRACT_V1
```

를 두고 기존 strategy implementation identity에 **immutable companion binding**한다.

논리 shape:

```yaml
contract_version: STRATEGY_SEMANTIC_CONTRACT_V1
semantic_contract_hash: <canonical hash>

strategy_version_id: <existing strategy version>
strategy_definition_hash: <existing definition hash>
strategy_key: <existing strategy key>

q1:
  intent_text: <authored Q1-only intent>
  required_definition_ids: [...]
  definitions:
    - id: ...
      text: ...

entry_rules:
  - rule_id: ...
    intent_role: CONFIRMATION_ONLY | EXECUTABLE_ENTRY
```

### 5.2 왜 기존 strategy definition hash와 분리하는가

implementation AST와 semantic prose는 서로 다른 변경 축이다.

- 코드 변화 없음 + semantic 문구 교정
- 코드 변화 있음 + semantic contract unchanged 불가
- semantic contract 변화 + review/binding 필요

를 각각 추적해야 한다.

따라서:

```text
strategy_definition_hash
!= semantic_contract_hash
```

이다.

단 semantic contract는 반드시 정확한 `strategy_version_id + strategy_definition_hash`에 bind된다.

동일 semantic contract를 임의의 다른 strategy version에 재사용하지 않는다.

### 5.3 Authoring / 변경 정책

`intent_text`와 definitions는 runtime LLM, regex, AST-to-prose generator가 작성하지 않는다.

authoritative source는 repository-controlled authored contract다.

변경 시:

1. 기존 artifact 수정 금지
2. 새 canonical payload/hash 생성
3. target strategy version/hash 재검증
4. future capture에서만 새 binding 사용
5. 과거 capture에는 적용 금지

semantic contract는 user-facing marketing copy가 아니다. Q1이 읽을 최소 의미 clause만 포함한다.

entry 역할 설명, risk, 미래수익, 추천 문구를 `intent_text`에 섞지 않는다.

---

## 6. Condition Semantic Contract

### 6.1 owner

Condition truth의 owner는 기존 deterministic strategy evaluator다.

Jev는:

- numeric threshold 계산
- PASS/FAIL 재판정
- indicator 계산

을 하지 않는다.

### 6.2 observed_meaning 생성 방식

새 논리 output:

```yaml
condition_semantics:
  condition_id: ...
  source_check_key: ...
  status: PASS
  observed_meaning: ...
  mapping_version: CONDITION_SEMANTIC_MAPPING_V1
  mapping_hash: ...
```

`observed_meaning`은 formatted `value` 문자열이나 `explanation`을 다시 NLP parsing해서 만들지 않는다.

다음 두 사실의 deterministic 조합으로 생성한다.

```text
evaluator branch/result
+
versioned semantic mapping
```

예를 들어 local evaluator가 이미 "MA20 slope positive branch가 PASS"라고 결정했다면 semantic mapping은 numeric 값을 재노출하지 않고 "20-day moving-average direction is rising"과 같은 bounded meaning을 제공할 수 있다.

### 6.3 mapping identity

최소 identity:

- `condition_semantic_mapping_version`
- `condition_semantic_mapping_hash`

mapping은 전략별 의미가 달라지는 condition을 구분할 수 있어야 한다.

예: 같은 volume ratio라도 breakout과 pullback의 semantic 역할이 다르므로 metric 이름 하나만으로 global meaning을 고정하지 않는다.

### 6.4 unsupported

evaluator result를 안정된 semantic meaning으로 deterministic mapping할 수 없으면:

```text
SEMANTIC_MAPPING_UNSUPPORTED
```

로 Q1 readiness를 실패시킨다.

unknown을 일반적인 negative meaning으로 변환하지 않는다.

---

## 7. Entry Rule Semantic Contract — Q2 local owner

### 7.1 두 provenance

Q2 local checker는 두 source를 비교한다.

**Intent source**

```text
Strategy Semantic Contract.entry_rules[]
```

**Representation source**

```text
Entry Rule Representation contract
```

둘은 같은 값을 복사한 duplicate field가 아니다.

### 7.2 logical shape

Intent:

```yaml
rule_id: <strategy-owned stable semantic rule id>
intent_role: CONFIRMATION_ONLY | EXECUTABLE_ENTRY
```

Representation:

```yaml
represented_rule_id: <rule being rendered>
represented_role: CONFIRMATION_ONLY | EXECUTABLE_ENTRY
executable_entry_range: true | false
representation_contract_version: ENTRY_RULE_REPRESENTATION_V1
representation_contract_hash: ...
```

`executable_entry_range`의 absent와 false는 구분한다.

### 7.3 rule identity

same-rule 여부는 자연어 문장에서 추측하지 않는다.

```text
intent.rule_id == representation.represented_rule_id
```

로 확인한다.

reference가 없거나 둘 이상이면 conflict를 추측하지 않고 MISSING/AMBIGUOUS다.

### 7.4 deterministic truth table

| intended_role | represented_role | reference | 결과 |
|---|---|---|---|
| CONFIRMATION_ONLY | CONFIRMATION_ONLY | MATCH | MATCH |
| CONFIRMATION_ONLY | EXECUTABLE_ENTRY | MATCH | CONFLICT_CONFIRMATION_AS_EXECUTION |
| EXECUTABLE_ENTRY | EXECUTABLE_ENTRY | MATCH | MATCH |
| EXECUTABLE_ENTRY | CONFIRMATION_ONLY | MATCH | CONFLICT_EXECUTION_AS_CONFIRMATION |
| any | UNKNOWN/ABSENT | MATCH | MISSING |
| any | any | missing | MISSING |
| any | any | multi/ambiguous | AMBIGUOUS |
| any | any | unsupported version | UNSUPPORTED |
| any | any | stale binding | STALE_VERSION |

Q2 local checker에는 probability와 threshold가 없다.

---

## 8. Q3 Local Completeness Contract

Q3 Noul은 복구하지 않는다.

local completeness는 "모든 자연어 의미가 완벽히 이해된다"는 인증이 아니다.

정확한 의미는:

```text
registered semantic dependencies required by this supported contract
are present, version-compatible, uniquely resolved, and non-cyclic
```

이다.

### 8.1 Q1 readiness

Q1 COMPLETE에 필요한 최소 항목:

- strategy semantic contract가 target strategy version/hash와 일치
- `intent_text` 존재 및 bounded
- `required_definition_ids` manifest 존재
- required definitions 전부 unique resolve
- empty/cyclic/invalid definition 거부
- 각 passed condition에 supported `observed_meaning`
- mapping version/hash 존재
- semantic contract가 Q1 supported 상태

### 8.2 Q2 readiness

Q2 COMPLETE에 필요한 최소 항목:

- intended `rule_id`
- `intent_role`
- represented `rule_id`
- `represented_role`
- explicit executable flag
- representation contract identity
- unique same-rule binding

Q1 missing은 Q2 결과를 삭제하지 않는다.

Q2 missing은 Q1 call을 자동 차단하지 않는다.

---

## 9. semantic status는 scope별로 분리한다

전체 boolean `semantic_link_status=true/false`는 사용하지 않는다.

최소:

```text
q1_semantic_status
q2_semantic_status
```

enum:

```text
COMPLETE
MISSING
AMBIGUOUS
UNSUPPORTED
STALE_VERSION
INVALID_BINDING
```

필요하면 reason code를 별도로 둔다.

예:

```text
Q1_DEFINITION_MISSING
Q1_CONDITION_MAPPING_UNSUPPORTED
Q2_RULE_REFERENCE_MISSING
Q2_REPRESENTATION_ROLE_ABSENT
SEMANTIC_CONTRACT_STRATEGY_BINDING_MISMATCH
```

status/reason은 provider에 보내지 않는다.

---

## 10. Capture-time immutable snapshot

### 10.1 lineage

새 canonical 흐름:

```text
Strategy implementation pin
        +
Strategy Semantic Contract
        +
deterministic condition evaluation
        +
Condition Semantic Mapping
        +
Entry Rule Representation
            ↓
Semantic Source Assembler
            ↓
candidate.semantic_source
            ↓
Prospective capture snapshot_json
            ↓
future V3 local checker / Q1 projector
```

### 10.2 candidate snapshot logical shape

```yaml
semantic_source:
  source_contract_version: JEV_SEMANTIC_SOURCE_V1
  source_snapshot_hash: ...

  strategy:
    strategy_version_id: ...
    strategy_definition_hash: ...
    semantic_contract_version: ...
    semantic_contract_hash: ...
    intent_text: ...
    required_definition_ids: [...]
    definitions: [...]

  conditions:
    mapping_version: ...
    mapping_hash: ...
    items:
      - condition_id: ...
        source_check_key: ...
        status: PASS
        observed_meaning: ...

  entry_rule:
    intended_rule_id: ...
    intent_role: ...
    represented_rule_id: ...
    represented_role: ...
    executable_entry_range: ...
    representation_contract_version: ...
    representation_contract_hash: ...

  readiness:
    q1_status: ...
    q1_reasons: [...]
    q2_status: ...
    q2_reasons: [...]

  local_entry_semantic_result:
    status: MATCH | CONFLICT | MISSING | AMBIGUOUS | UNSUPPORTED
    reason_code: ...
```

이 전체 snapshot은 local audit용이다.

Jev provider에는 여기서 Q1 허용 필드만 새 state로 projection한다.

### 10.3 과거 capture 불변성

금지:

- capture 후 최신 semantic registry 조회로 보충
- old `snapshot_json` rewrite
- current definition을 old candidate에 적용
- missing field를 inferred default로 채우기
- V1/V2 artifact를 V3 shape로 migration

---

## 11. Prospective version / DB 결정

### 11.1 Capture contract version bump

**YES.**

현재 `PROSPECTIVE_CAPTURE_VERSION = VN_P2_S2_CAPTURE_V1`의 candidate snapshot 의미가 바뀐다.

따라서 future implementation은 새 capture contract version을 사용해야 한다.

구체 version token은 implementation spec에서 확정하되 의미상 최소:

```text
PROSPECTIVE_CAPTURE_V2
```

성격이다.

### 11.2 SQL schema migration

**현재 설계 기준 NO.**

이유:

- `prospective_recommendation_sample.snapshot_json`이 candidate 전체 snapshot을 이미 보존
- `snapshot_hash`가 전체 candidate snapshot을 hash
- `source_snapshot_hash` 계산에 candidates 전체가 들어감
- 새 semantics는 nested snapshot data로 저장 가능

따라서 semantic source를 위해 prospective sample에 별도 SQL column을 우선 추가할 이유가 없다.

단 implementation audit에서 downstream query가 JSON 내부 identity를 사용할 수 없어서 정규화 column이 반드시 필요하다는 구체적 blocker가 발견되면 별도 migration spec으로 분리한다. 이번 설계에서 선제 migration을 만들지 않는다.

### 11.3 Strategy Governance DB migration

**Semantic Source V1을 위해 필수로 요구하지 않는다.**

Strategy Semantic Contract는 기존 implementation registry row를 수정하지 않는 immutable companion artifact로 설계한다.

기존 `definition_json`과 `definition_hash`를 semantic prose 때문에 rewrite하지 않는다.

---

## 12. Hash / identity contract

최소 identity:

```text
strategy_version_id
strategy_definition_hash

strategy_semantic_contract_version
strategy_semantic_contract_hash

condition_semantic_mapping_version
condition_semantic_mapping_hash

entry_rule_representation_contract_version
entry_rule_representation_contract_hash

semantic_source_contract_version
semantic_source_snapshot_hash
```

future Q1 cohort identity는 최소:

```text
semantic source identity
+ Q1 state projector identity
+ Q1 question identity
+ Q1 disposition policy identity
+ provider/model request+returned binding
+ frozen T_strategy
```

를 포함해야 한다.

Q2 local result는 Jev model cohort에 넣어 Jev 성과로 귀속하지 않는다.

---

## 13. V3 Q1 external wire contract

provider가 읽을 수 있는 논리 state는 세 영역뿐이다.

```yaml
strategy_intent:
  text: ...

term_definitions:
  - ref: ...
    text: ...

passed_condition_meanings:
  - ref: ...
    meaning: ...
```

전송 금지:

- ticker
- company name
- rank
- capture/recruitment ID
- account/user
- holdings
- price rule / Q2 state
- local Q2 conflict
- local completeness status
- risk
- stop/target/RR
- actual numeric threshold/value
- future outcome
- historical evaluation
- news/macro
- gold/purpose/split
- strategy registry implementation identity

local reference ID가 Q1 문장 연결에 필요하면 provider request 안에서만 사용하는 neutral ephemeral reference로 project하고 original internal ID를 보낼 필요는 없다.

기존 크기 원칙 유지:

- UTF-8 total <= 8 KiB
- conditions <= 12
- oversize => truncate 금지 / no-call
- individual semantic text bounded

---

## 14. 현재 field 공급 가능성

| field | 판정 | 이유 |
|---|---|---|
| `strategy_semantics.intent_text` | **NEEDS_SOURCE_CHANGE** | 현재 AST definition과 UI/action prose는 Q1 authored contract가 아님 |
| `required_definition_ids + definitions` | **NEEDS_SOURCE_CHANGE** | 현재 explicit semantic dependency manifest 없음 |
| `condition_semantics.observed_meaning` | **NEEDS_SOURCE_CHANGE but DERIVABLE** | deterministic evaluator가 있으므로 versioned mapping을 추가하면 authoritative 생성 가능 |
| `price_rule.intent_role + rule_id` | **NEEDS_SOURCE_CHANGE** | current production authoritative source 없음 |
| represented role/reference | **NEEDS_SOURCE_CHANGE** | current RiskPlan/Strategy payload에 V3 role/reference contract 없음 |
| q1/q2 readiness | **DERIVABLE_DETERMINISTIC** | 위 source가 생기면 local validation 가능 |
| immutable capture | **AVAILABLE_NOW WITH CONTRACT BUMP** | candidate snapshot_json이 nested data 보존 가능 |

핵심 source는 현재 존재하지 않지만, **새로운 외부 데이터나 AI 추론 없이 StockScope 내부의 authored contract + deterministic producer로 공급 가능하다.**

따라서 provenance는 설계상 RESOLVED이며 implementation은 별도 승인 후 진행 가능하다.

---

## 15. Q1 residual AI value

Q1을 남기는 이유를 local deterministic 영역과 분리한다.

### A. local deterministic으로 충분한 사례

```text
intended_role = CONFIRMATION_ONLY
represented_role = EXECUTABLE_ENTRY
same rule id
```

이는 Q2 local conflict다. Jev를 호출할 이유가 없다.

또한 required definition의 존재/누락도 local completeness가 판단한다.

### B. Q1이 추가 가치를 가질 수 있는 사례

authored strategy intent가 여러 이미 PASS된 condition 의미의 **조합, 허용 예외, 부정 범위**를 설명하고, 개별 enum equality만으로 material semantic contradiction이 완전히 결정되지 않는 경우다.

예시 개념:

```text
Intent:
"단기 약화는 허용하지만 중기 상승 구조가 유지되는 경우에만 continuation으로 본다."

Passed meanings:
- short-term slope is nearly flat
- medium-term structure remains rising
- relative strength remains positive
```

여기서 각 condition은 local PASS이고 required definition도 complete하다. Q1의 역할은 numeric pass를 다시 계산하는 것이 아니라 **제공된 의미 조합이 authored intent와 명시적으로 모순되는지**를 제한적으로 재검토하는 것이다.

이 residual value는 **V3 Canary에서 검증할 hypothesis**다. production usefulness가 확정됐다는 뜻은 아니다.

### C. supported contract에서 제외할 사례

```text
"건강한 모멘텀일 때 진입"
```

처럼 `건강한 모멘텀`의 required definition이 없고 어떤 condition 의미를 참조하는지 명시되지 않은 경우다.

이 경우 Jev에게 추측시키지 않는다.

```text
q1_semantic_status = MISSING / UNSUPPORTED
Jev = SKIPPED
```

이다.

### 15.1 Q1 삭제 gate

후속 구현/fixture authoring 과정에서 hard Q1 examples가 결국 enum/table lookup만으로 모두 결정된다면:

```text
Q1 residual AI value = ABSENT
```

로 재판정하고 Canary V3를 실행하기 전에 Jev Q1 자체를 삭제하는 설계 재검토가 필요하다.

AI를 유지하기 위해 의도적으로 prose를 모호하게 만들지 않는다.

---

## 16. Source contract failure policy

semantic source 조립 실패는 정상 의미로 보정하지 않는다.

| failure | local behavior | Jev |
|---|---|---|
| semantic contract missing | Q1 MISSING | SKIPPED |
| strategy version/hash binding mismatch | INVALID_BINDING | SKIPPED |
| definition missing/cyclic | Q1 MISSING/INVALID | SKIPPED |
| condition semantic mapping unsupported | Q1 UNSUPPORTED | SKIPPED |
| Q2 intended rule missing | Q2 MISSING | Q1 ready이면 Q1 영향 없음 |
| represented rule ambiguous | Q2 AMBIGUOUS | Q1 ready이면 Q1 영향 없음 |
| local Q2 conflict | local review signal 보존 | Q1 독립 실행 가능 |
| Q1 provider failure | local result 보존 | ERROR/LATE/INTERRUPTED |
| oversize Q1 payload | Q1 no-call | SKIPPED |

baseline candidate decision은 모두 그대로 유지한다.

---

## 17. Version transition

### V1/V2

- questions/policies/projectors/artifacts/reports preserved
- historical stored review를 V3 contract로 재해석 금지
- threshold backfill 금지

### V3

새 identity family가 필요하다.

최소 논리 version:

```text
JEV_SEMANTIC_SOURCE_V1
STRATEGY_SEMANTIC_CONTRACT_V1
CONDITION_SEMANTIC_MAPPING_V1
ENTRY_RULE_REPRESENTATION_V1
JEV_TYPESAFE_STATE_V3
JEV_TYPESAFE_PROJECTOR_V3
JEV_TYPESAFE_QUESTIONS_V3
JEV_TYPESAFE_DISPOSITION_POLICY_V3
```

정확한 token/name은 implementation spec에서 확정한다.

V3는 V2의 `QUESTIONS_V2`, 3-threshold policy 또는 old state hash를 mutate하지 않는다.

---

## 18. 다음 구현 단계 범위

별도 승인 후 `TYPE-JEV-V3-SEMANTIC-CONTRACT-IMPLEMENT`에서만 다음을 구현한다.

1. immutable Strategy Semantic Contract source
2. deterministic Condition Semantic Mapping
3. Entry Rule Representation source
4. Semantic Source Assembler / q1,q2 readiness
5. Q2 local deterministic checker
6. prospective capture contract version bump 및 semantic snapshot 포함
7. Q1-only V3 projector/question/policy version dispatch
8. stored projection/cohort identity의 V3 분리
9. fake/offline isolation tests

그 단계에서도:

- real TypeSafe API call 0
- Canary V3 execution 0
- exact 40 fixture protocol은 별도 freeze 단계
- Trial activation 0

이어야 한다.

---

## 19. Canary V3 전 별도 단계

implementation이 PASS한 뒤에도 바로 provider를 호출하지 않는다.

다음 별도 작업에서:

```text
exact 40 new synthetic contexts
selection 20 / validation 20
partition당 provider-callable 12 + local-only 8
exact Q1 wire bytes
gold
route/local signal
threshold candidate grid
selection/tie-break
repetition
cap/budget
model binding rule
```

을 machine-readable protocol로 response 관측 전에 freeze한다.

V2 validation fixture를 acceptance set으로 재사용하지 않는다.

---

## 20. 최종 결정표

| 결정 | 최종 답 |
|---|---|
| authoritative strategy implementation source | existing Strategy Governance `strategy_version_id + definition_hash` |
| authoritative strategy intent source | **new immutable Strategy Semantic Contract companion artifact** |
| semantic definition source | Strategy Semantic Contract의 authored definitions |
| condition observed meaning source | **deterministic evaluator result + versioned Condition Semantic Mapping** |
| price intent role source | Strategy Semantic Contract entry-rule definition |
| represented role source | **new Entry Rule Representation contract** |
| rule identity/link source | strategy-owned rule_id ↔ represented_rule_id explicit binding |
| Q1 completeness owner | local Semantic Readiness Evaluator |
| Q2 conflict owner | local deterministic Entry Semantic Checker |
| Q3 completeness owner | local scope-specific readiness checks |
| capture version bump | **YES** |
| prospective SQL schema migration | **NO, current design 기준** |
| strategy governance DB migration | **NO, semantic companion artifact 사용** |
| historical backfill | **FORBIDDEN** |
| V1/V2 compatibility | **PRESERVED** |
| Q1 residual AI value | **JUSTIFIED FOR V3 VALIDATION, NOT PROVEN FOR PRODUCTION** |
| V3 implementation readiness | **READY FOR SEPARATE APPROVAL / SOURCE CHANGES REQUIRED** |
| Canary V3 | **NOT EXECUTED** |
| final V3 threshold | **NOT FROZEN** |
| Trial | **BLOCKED** |

---

## 21. 작업 종료 상태

| 항목 | 상태 |
|---|---|
| SEMANTIC SOURCE CONTRACT | **DESIGNED** |
| AUTHORITATIVE PROVENANCE | **RESOLVED BY CONTRACT** |
| Q1 SOURCE | **RESOLVED DESIGN / NEW SOURCE REQUIRED** |
| Q2 LOCAL SOURCE | **RESOLVED DESIGN / NEW SOURCE REQUIRED** |
| Q3 COMPLETENESS SOURCE | **RESOLVED DESIGN / LOCAL DERIVED** |
| CAPTURE VERSIONING | **BUMP REQUIRED** |
| PROSPECTIVE SQL MIGRATION | **NOT REQUIRED BY CURRENT DESIGN** |
| V3 IMPLEMENTATION | **READY FOR SEPARATE APPROVAL** |
| SOURCE CODE / FRONTEND | **UNCHANGED / UNCHANGED** |
| RUNTIME / DB / MIGRATION | **UNCHANGED / UNCHANGED / NONE** |
| CANARY V3 | **NOT EXECUTED** |
| FINAL THRESHOLD | **NOT FROZEN** |
| TRIAL | **BLOCKED** |
| PROVIDER/API CALLS | **0** |
| REAL STOCK DATA SENT | **0** |
| JEV_API_KEY / .env ACCESS | **0 / 0** |
| HOLDOUT ACCESS | **0** |
| ACTUAL EVALUATION | **NOT EXECUTED** |
| R5R ACTUAL EVALUATION | **NOT EXECUTED** |

이번 문서는 implementation을 승인하지 않는다. 다음 단계는 별도 `TYPE-JEV-V3-SEMANTIC-CONTRACT-IMPLEMENT` 승인이다.
