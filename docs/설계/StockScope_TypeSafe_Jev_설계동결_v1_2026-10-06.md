# StockScope TypeSafe Jev 설계동결 v1

작성일: 2026-10-06 (Asia/Seoul)  
작업 단계: **TYPE-JEV-DESIGN-FREEZE**  
조사 기준: `main = f6c9a799e7ae2e9a15386e3ea5721a34a2fd305c`  
입력 설계: 사용자 제공 `StockScope_TypeSafe_Jev_통합재설계_v3_2026-10-06.md`  
지위: **구현 전 TypeSafe Jev Phase 1 architecture freeze. 실제 provider/model discovery·API 호출·trial activation 승인이 아니다.**

---

## 1. Freeze 결정 요약

StockScope의 JEV는 **TypeSafe AI Jev를 이용하는 제한적 semantic shadow reviewer**다. 기존 Scanner/Strategy/Risk가 계산한 숫자와 enum을 다시 판단하지 않고, 이미 완성된 `ENTRY_CANDIDATE`에서 **전략 조건 맥락과 진입 설명 맥락의 의미상 긴장**만 검토한다.

이번 source-level 검토에서 재설계 v3의 4-Noul 초안을 그대로 채택하지 않는다.

| v3 질문 | Freeze 판정 | 이유 |
|---|---|---|
| `condition_context_conflict` | **MODIFY / KEEP** | canonical snapshot에 strategy 설명과 condition detail이 존재하며, deterministic PASS 이후에도 여러 조건의 의미상 조합을 별도 shadow 진단할 여지는 있음 |
| `entry_context_conflict` | **MODIFY / KEEP** | price rule의 semantic role과 candidate action 사이 설명 일관성은 검토 가능. 단 가격 산술·가격 plan validity는 기존 코드가 선행 판정 |
| `risk_context_caution` | **DROP** | `ENTRY_CANDIDATE`는 이미 Risk READY·reference-only 아님·risk warning 없음으로 제한되고 Risk/price consistency도 deterministic code가 소유. Jev 재판정은 중복 |
| `review_evidence_insufficient` | **KEEP** | 필수 field가 존재해도 제한된 semantic question을 해석할 맥락이 부족할 수 있으므로 model-side uncertainty gate로 필요 |

따라서 Phase 1 wire contract는 **3개의 Noul**로 동결한다.

1. `strategy_context_conflict`
2. `entry_context_conflict`
3. `review_evidence_insufficient`

최종 `PASS_THROUGH / REVIEW_REQUIRED / ABSTAIN`은 TypeSafe native output이 아니라 **StockScope deterministic disposition**이다.

---

## 2. 제품 목적과 권한 경계

StockScope의 목표는 AI 기능 자체가 아니라 사용자가 기존 분석 결과를 빠르게 이해하고 판단하도록 돕는 것이다.

### 2.1 Jev가 소유하지 않는 영역

다음은 기존 deterministic owner가 계속 최종 권한을 가진다.

- Strategy eligibility
- condition PASS/FAIL
- condition count
- Scanner candidate action
- Scanner ranking
- Risk READY/CAUTION/HOLD/UNAVAILABLE
- price threshold/range 계산
- current price와 trigger/range 비교
- invalidation/stop/target 계산
- R/R 산술
- price-plan consistency
- order/매수/매도
- Holdings action
- 미래수익 추정

Jev가 이 계산을 재실행하거나 override하지 않는다.

### 2.2 Jev가 검토하는 영역

Jev가 검토할 수 있는 것은 다음 두 semantic boundary뿐이다.

**A. Strategy context coherence**
- 기존 코드가 PASS로 판정한 조건들의 조합과 frozen strategy intent 사이에 사용자가 다시 확인해야 할 의미상 긴장이 있는가.

**B. Entry context coherence**
- 기존 코드가 유효하다고 판정한 strategy price-rule의 의미와 현재 ENTRY_CANDIDATE 설명 사이에 오해 가능성이 있는 의미상 긴장이 있는가.

여기에 **C. Evidence sufficiency**를 별도 질문으로 둔다.

이는 “이 종목이 좋은가”, “오를 확률이 높은가”, “Risk가 맞는가”를 묻는 질문이 아니다.

---

## 3. 현재 코드에서 확인한 source facts

### 3.1 Scanner candidate

`backend/app/backtest/scanner.py::_current_candidate`는 현재 candidate snapshot에 최소 다음을 넣는다.

- `strategy`
- `strategy_version_id`
- `strategy_definition_hash`
- `strategy_description`
- `action`
- `candidate_state`
- `conditions.passed/total/missing/top_missing`
- `risk.status/warning/warnings`
- `entry_risk_guide`
- `_repro_condition_details`

`_repro_condition_details`는 `build_condition_state()`가 만든 전체 condition detail을 보존한다.

각 detail은 현재 소스상 다음 정보를 가질 수 있다.

- `raw`
- `label`
- `detail`
- `status`
- `current_value`
- `required_value`
- `metric_key`
- `condition_id`

### 3.2 ENTRY_CANDIDATE gate

`current_readiness()`에서 READY가 되려면 source-level로 다음이 필요하다.

- risk status가 `READY`
- strategy score가 70 이상
- conditions complete
- blocker/reference-only/caution path가 아님

그리고 Scanner `_current_candidate()`는 `status == READY`이며 `risk_warning == false`일 때만 `action = ENTRY_CANDIDATE`를 만든다.

따라서 Phase 1 Jev에 별도 “Risk caution 판정”을 맡기지 않는다.

### 3.3 Risk/entry semantics

`entry_risk_guide.py`는 이미 다음을 deterministic하게 계산한다.

- strategy price rule의 `semantic_role`
- strategy condition band/threshold와 executable entry의 구분
- Risk entry reference / invalidation / stop / target 관계
- `price_consistency.status`
- `price_consistency.classification`
- issue codes
- overlap semantics

Risk payload도 ENTRY_CANDIDATE이면 `needs_recheck=false`를 계산한다.

따라서 Jev는 이 산술·유효성 검사를 반복하지 않는다.

### 3.4 Prospective canonical snapshot

`ProspectiveCatalog._candidate_snapshot()`은 Scanner candidate dict를 그대로 snapshot으로 보존하고, `prospective_recommendation_sample.snapshot_json`에 저장한다.

Jev는 **capture 이후 현재 코드를 다시 실행해 의미를 보충하지 않는다.** 가능한 한 canonical snapshot에 이미 보존된 의미를 사용한다.

현재 JEV v1 projection은 `conditions`를 `passed/total/missing/top_missing`로 축약하고, `risk`, 일부 `entry_risk_guide`만 뽑는다. TypeSafe V2에서는 이 projection을 그대로 재사용하지 않는다.

---

## 4. Jev Value Boundary Matrix

| 정보/판단 | deterministic code로 해결 | Phase 1 Jev 추가 가치 | 외부 state |
|---|---:|---:|---:|
| condition PASS/FAIL | 예 | 없음 | 결과 자체만 context |
| passed/total | 예 | 없음 | 선택적 audit context |
| current vs required 산술 | 예 | 재계산 금지 | normalized result만 가능 |
| strategy eligibility | 예 | 없음 | 전송 안 함 |
| Risk READY/FAIL | 예 | 없음 | call gate에서만 사용 |
| stop/target/RR | 예 | 없음 | 기본 전송 안 함 |
| price-plan validity | 예 | 없음 | classification만 local gate |
| strategy intent와 여러 PASS condition의 의미 조합 | 완전 rule화하지 않음 | **검증 대상** | 예 |
| strategy price-rule의 의미와 ENTRY_CANDIDATE 설명의 의미 조합 | 일부 deterministic | **제한적 검증 대상** | 예 |
| 입력 의미가 제한된 질문에 충분한가 | local field existence만으로 불충분할 수 있음 | **예** | Jev q3 |
| 뉴스/이벤트 해석 | Phase 1 제외 | 금지 | 아니오 |
| 미래 상승/수익 가능성 | Phase 1 목적 아님 | 금지 | 아니오 |
| 종목 순위 | 기존 Scanner | 금지 | 아니오 |

**No fuzzy context = 정상 no-call**이다. Jev를 호출하기 위해 입력 범위를 억지로 넓히지 않는다.

---

## 5. Phase 1 대상 모집 범위

### 5.1 기본 scope

Phase 1 efficacy trial의 기본 모집군은 다음으로 동결한다.

- canonical prospective capture
- `action == ENTRY_CANDIDATE`
- explicit horizon only
- `SHORT`, `MEDIUM`
- activation 이후 신규 observation
- 동일 analysis-unit의 최초 canonical observation

### 5.2 제외

- `WAIT`
- `NO_TRADE`
- `LEGACY_UNSPECIFIED`
- `LONG` Phase 1 efficacy cohort
- PARTIAL/FAILED canonical capture
- local identity/time proof 불충분
- source contract에서 필요한 semantic context 미충족

`LONG`은 Jev 자체가 처리할 수 없어서가 아니라, 현재 Phase 1의 20거래일 outcome 비교만으로 장기 판단 가치를 주장하지 않기 위해 제외한다. 향후 LONG 전용 관찰 계약을 만들면 별도 cohort/version으로 확장한다.

---

## 6. Frozen state contract

제안 identity:

`JEV_TYPESAFE_STATE_V1`

외부 TypeSafe state와 local audit envelope를 분리한다.

### 6.1 외부 state 최상위 구조

```json
{
  "context": {},
  "strategy_context": {},
  "condition_context": [],
  "entry_context": {},
  "baseline": {}
}
```

### 6.2 context

외부 전송:

- `market`
- `as_of_date`
- `horizon_intent`

기본 제외:

- ticker
- company name
- capture ID
- request ID
- hashes
- rank

종목 식별은 Phase 1 질문에 필요하지 않다.

### 6.3 strategy_context

외부 전송:

- `strategy_key`
- `strategy_description`

`strategy_description`은 canonical capture에 이미 저장된 fixed product description을 사용한다.

현재 capture에 없는 `when_to_use`를 현재 코드의 최신 dictionary에서 사후 재생성해 붙이지 않는다.

향후 `when_to_use`가 필요하다고 판단되면 Scanner capture contract를 별도 version으로 바꾼 뒤 신규 cohort에서 사용한다.

### 6.4 condition_context

source:
`snapshot._repro_condition_details`

Phase 1 external projection은 **PASS condition만** 사용한다. ENTRY_CANDIDATE는 이미 missing=0이어야 한다.

각 item의 wire shape:

```json
{
  "metric_key": "stable metric key or null",
  "status": "PASS",
  "current_value": "bounded scalar/string or null",
  "required_value": "bounded scalar/string or null",
  "semantic_label": "bounded fixed label"
}
```

규칙:

- `status`는 PASS만 허용.
- `current_value/required_value`로 Jev가 산술 PASS/FAIL을 재계산하도록 질문하지 않는다.
- `semantic_label`은 raw free text를 그대로 전달하는 범용 channel이 아니다.
- current source의 `raw/label/detail`은 local audit에서 보존하되 external semantic label은 **versioned fixed mapping**으로 만든다.
- mapping 불가 condition이 전체 의미에서 중요하면 `SKIPPED / SEMANTIC_MAPPING_INCOMPLETE`.
- unknown text를 자동 번역/요약해서 보내지 않는다.
- 최대 12개 condition item.
- 동일 candidate에서 12개를 초과하면 truncate하지 않고 `SKIPPED / STATE_LIMIT_EXCEEDED`.

### 6.5 entry_context

외부 전송 허용:

- `price_rule.kind`
- `price_rule.status`
- `price_rule.semantic_role`
- `price_rule.executable_entry_range` if captured
- `entry_risk_guide.action.status`
- `price_consistency.classification`
- `price_consistency.semantic_overlap` if captured
- local code가 만든 current-price position enum이 향후 projector에 명시적으로 추가되는 경우 그 enum

외부 기본 제외:

- stop 가격
- target 가격
- rr1/rr2
- risk_pct
- raw overlap prices
- numeric geometry

local deterministic gate:

- `price_consistency.status == INVALID` 또는 `WARNING`이면 Jev로 보내서 해결하지 않는다.
- 해당 candidate는 `SKIPPED / LOCAL_PRICE_PLAN_NOT_CLEAN`.
- `price_consistency`가 capture에 없거나 의미 확인에 필요한 entry context가 없으면 `SKIPPED / ENTRY_CONTEXT_INSUFFICIENT`.

### 6.6 baseline

외부 전송:

```json
{
  "action": "ENTRY_CANDIDATE",
  "candidate_state": "READY"
}
```

그 외 ranking/score/history는 보내지 않는다.

### 6.7 외부 전송 금지

- News
- Event Evidence
- Macro reference
- Holdings
- account/user data
- future outcome
- historical evaluation result
- historical fit 성과
- ranking score
- internal strategy score
- secret
- raw provider/vendor source
- arbitrary user text
- full snapshot dump

### 6.8 local audit envelope

로컬에는 다음 identity를 보존한다.

- canonical capture/sample identity
- candidate snapshot hash
- Scanner version/baseline
- input fingerprint
- strategy version/hash
- selection policy ID/hash
- horizon policy
- state contract/projector version/hash
- question contract/hash
- deterministic disposition policy/hash
- protocol hash
- model requested/returned/verification
- adapter version
- exact external state bytes/hash
- exact question set bytes/hash
- typed answers
- operational status
- disposition
- usage/cost/latency
- timestamps/deadline

audit identity를 TypeSafe state에 넣지 않는다.

---

## 7. Frozen no-call gates

TypeSafe call 전에 local code가 다음 순서로 판정한다.

1. canonical capture COMPLETE/DUPLICATE identity 확인
2. ENTRY_CANDIDATE 확인
3. SHORT/MEDIUM horizon 확인
4. activation-forward 모집 범위 확인
5. duplicate analysis-unit 확인
6. Scanner/strategy/selection/horizon identity 확인
7. Risk baseline `READY`, warning false 확인
8. conditions complete 확인
9. semantic condition mapping completeness 확인
10. entry context completeness 확인
11. deterministic price consistency clean 확인
12. state size/array limit 확인
13. provider/model readiness 확인
14. privacy/source-transmission approval 확인
15. budget reservation 확인

실패하면 provider를 호출하지 않고 `SKIPPED + skip_reason`을 기록한다.

---

## 8. Frozen TypeSafe question contract

Question contract identity:

`JEV_TYPESAFE_QUESTIONS_V1`

Phase 1은 **Noul 3개**다.

공통 원칙:

- supplied state only
- external knowledge 금지
- ticker/company 추론 금지
- news/event 추론 금지
- future return 추정 금지
- numeric rule 재계산 금지
- 매수/매도 추천 금지
- Risk 승인/거부 금지
- 한 question은 하나의 명제만 판단

### 8.1 Q1 — strategy_context_conflict

type:
`noul`

고정 의미:
“기존 코드가 PASS로 판정한 조건들의 제공된 의미 조합이, 제공된 strategy description과 실질적으로 충돌하는가?”

권장 wire instructions:

```text
Using only the supplied strategy_context and condition_context, judge whether the
meaning of the already-passed condition context materially conflicts with the
stated strategy description.

Do not recalculate whether any numeric condition passes.
Do not infer missing market data, news, company identity, or future returns.
Do not judge whether the stock is attractive or recommend a trade.
Answer only the proposition about semantic conflict.
```

criteria.true:

```text
The supplied passed-condition context contains a meaningful combination or
qualification that is difficult to reconcile with the stated strategy
description and therefore deserves a human re-check.
```

criteria.false:

```text
The supplied passed-condition context is semantically consistent with the stated
strategy description; any numeric eligibility decision remains owned by
StockScope's deterministic rules.
```

reason code:
`STRATEGY_CONTEXT_CONFLICT`

### 8.2 Q2 — entry_context_conflict

type:
`noul`

고정 의미:
“deterministic price-plan validation을 이미 통과한 상태에서, 제공된 strategy price-rule의 의미와 ENTRY_CANDIDATE 설명 사이에 사용자가 잘못 해석할 만한 semantic conflict가 있는가?”

wire instructions:

```text
Using only entry_context and baseline, judge whether the semantic role of the
strategy price rule materially conflicts with the ENTRY_CANDIDATE presentation.

The local program has already validated arithmetic price relationships.
Do not recompute prices, stops, targets, risk/reward, or eligibility.
A strategy condition band or threshold is not an executable buy range unless the
supplied state explicitly says so.
Do not recommend a trade or predict returns.
Answer only the proposition about semantic presentation conflict.
```

criteria.true:

```text
The supplied entry semantics could materially mislead a user about what the
ENTRY_CANDIDATE state means, even though deterministic price validation itself
has already passed.
```

criteria.false:

```text
The supplied entry semantics and ENTRY_CANDIDATE presentation are mutually
consistent and do not add a material semantic warning.
```

reason code:
`ENTRY_CONTEXT_CONFLICT`

### 8.3 Q3 — review_evidence_insufficient

type:
`noul`

고정 의미:
“local required fields는 존재하지만 Q1/Q2 같은 제한적 semantic 판단을 하기에 supplied state의 의미가 본질적으로 부족한가?”

wire instructions:

```text
Using only the supplied state, judge whether the semantic context is inherently
insufficient to evaluate the two limited review propositions reliably.

Do not treat ordinary uncertainty about future price movement as insufficient
evidence. Do not request news, company identity, account data, holdings, or
future outcomes. Judge only whether the provided semantic context is sufficient
for the limited strategy-context and entry-context review.
```

criteria.true:

```text
The supplied semantic context is too incomplete or ambiguous to support the
limited review without inventing missing meaning.
```

criteria.false:

```text
The supplied semantic context is adequate for the limited review, even if the
result may still be uncertain.
```

uncertainty reason:
`EVIDENCE_INSUFFICIENT`

---

## 9. Dropped Noul — risk_context_caution

`risk_context_caution`은 Phase 1 contract에서 제거한다.

이유:

1. ENTRY_CANDIDATE 자체가 Risk READY + no warning path다.
2. `reference_only`이면 current readiness가 BLOCKED로 간다.
3. CAUTION이면 ENTRY_CANDIDATE가 아니다.
4. RiskEngine이 stop/target/RR/structure를 계산한다.
5. entry-risk guide가 `needs_recheck`를 결정한다.
6. price-plan consistency가 deterministic issue/classification을 계산한다.

따라서 같은 사실을 Jev에게 다시 물으면 “deterministic code로 충분한 영역은 Jev에 맡기지 않는다”는 제품 원칙을 위반한다.

Risk는 local call gate와 audit identity로는 남지만 TypeSafe fuzzy question은 아니다.

---

## 10. Frozen deterministic disposition policy

Policy identity:

`JEV_TYPESAFE_DISPOSITION_POLICY_V1`

### 10.1 threshold architecture

두 threshold slot을 둔다.

- `L = threshold_low`
- `H = threshold_high`
- 제약: `0 <= L < 0.5 < H <= 1`

분류:

- `p <= L` → LOW
- `L < p < H` → GRAY
- `p >= H` → HIGH

**숫자 0.15 / 0.85는 v3의 초기 후보값이며 이 문서에서 final trial value로 동결하지 않는다.**

이유는 실제 TypeSafe Jev에 승인된 synthetic state를 한 번도 호출하지 않은 상태이기 때문이다.

중요: 구현 코드는 숫자를 hard-code하지 않고 frozen Trial V2 artifact가 L/H를 소유한다.

numeric L/H는:
- outcome을 보지 않는 synthetic boundary set
- 사용자 승인된 provider canary
- review/abstain burden 확인

뒤 **prospective trial activation 전에 한 번만** 동결한다.

prospective outcome을 본 뒤 조정하면 새 protocol/cohort가 필요하다.

### 10.2 disposition 순서

`q3 = review_evidence_insufficient`  
`q1 = strategy_context_conflict`  
`q2 = entry_context_conflict`

| 우선 | 조건 | operational | disposition |
|---|---|---|---|
| 1 | local gate 실패 | SKIPPED | null |
| 2 | HTTP/native schema/usage 실패 | ERROR | null |
| 3 | model identity unverified/changed | ERROR | null |
| 4 | deadline 초과 | LATE | null |
| 5 | q3 HIGH | VALID | ABSTAIN / EVIDENCE_INSUFFICIENT |
| 6 | q3 GRAY | VALID | ABSTAIN / MODEL_UNCERTAIN |
| 7 | q3 LOW + q1 또는 q2 HIGH | VALID | REVIEW_REQUIRED |
| 8 | q3 LOW + q1 LOW + q2 LOW | VALID | PASS_THROUGH |
| 9 | 나머지 valid vector | VALID | ABSTAIN / MODEL_UNCERTAIN |

질문 확률을 더하거나 평균내거나 곱하지 않는다.

REVIEW_REQUIRED reason은 HIGH인 q1/q2만 사용한다.
둘 다 HIGH이면 p가 높은 것을 먼저 표시하며 동률은 q1 → q2 순이다.
현재 최대 reason 2개다.

---

## 11. Operational status와 application disposition

서로 다른 축으로 저장한다.

### 11.1 operational status

- `SKIPPED`
- `PENDING`
- `VALID`
- `ERROR`
- `LATE`
- `INTERRUPTED`

### 11.2 application disposition

VALID인 경우만:

- `PASS_THROUGH`
- `REVIEW_REQUIRED`
- `ABSTAIN`

그 외:

- `null`

ERROR/SKIPPED/LATE/INTERRUPTED를 ABSTAIN으로 변환하지 않는다.

---

## 12. Model identity freeze policy

Provider identity:
`TYPESAFE_SYSTEM_ONE`

Adapter proposal:
`JEV_TYPESAFE_SYSTEMONE_ADAPTER_V1`

정책:

1. production/prospective trial은 versioned model ID를 요청한다.
2. rolling alias는 기본 사용하지 않는다.
3. `model_requested`와 `model_returned`를 분리 저장한다.
4. response.model 누락/예상 불일치 시 request model로 fallback하지 않는다.
5. unverified model response는 application disposition을 만들지 않는다.
6. model target 변경은 새 protocol/cohort다.
7. 기존 observation을 새 모델로 재채점하지 않는다.

정확한 model ID는 이 문서에서 결정하지 않는다. 계정별 access와 실제 returned identity는 승인된 discovery/canary가 필요한 외부 사실이다.

모델 ID의 미확정은 architecture gap이 아니라 **pre-activation binding slot**이다.

---

## 13. Credential / privacy / source transmission freeze

### 13.1 credential

`JEV_API_KEY`의 의미:

**TypeSafe AI Jev credential**

추가 OpenAI key는 요구하지 않는다.

금지:

- secret 출력
- Git 저장
- DB 저장
- log 저장
- artifact/backup 저장
- UI 노출

### 13.2 source transmission class

Phase 1 allowed:

`MINIMIZED_DERIVED_SCANNER_SEMANTIC_STATE_V1`

허용 데이터는 §6 external state뿐이다.

기존 OpenAI Trial V1의 `source_transmission_approved=true`를 TypeSafe 승인으로 승계하지 않는다.

실제 TypeSafe 계정의:
- retention
- ZDR entitlement
- billing terms
- 계정별 model access

는 activation 전 별도 확인해야 하는 외부 blocker다.

이 확인 전 `allow_network=true`가 될 수 없다.

---

## 14. State size / determinism rules

Phase 1 local product limits:

- canonical UTF-8 external state <= 8 KiB
- condition_context <= 12
- arbitrary free text field 금지
- fixed semantic label 160 characters 이하
- unknown mapping 자동 truncate 금지
- state limit 초과는 SKIPPED
- question set은 protocol별 완전 고정
- question 추가/삭제/의미 변경은 새 contract/cohort

실제 provider context maximum과 별개의 StockScope 최소화 정책이다.

---

## 15. Trial V2 required contract

향후 machine artifact는 기존 V1을 mutate하지 않고 새 V2로 만든다.

권장 logical ID:

`JEV_TYPESAFE_REVIEWER_TRIAL_V2`

artifact에 최소 다음을 포함해야 한다.

### 15.1 identity

- protocol ID/version
- semantic hash
- state contract version/hash
- projector version/hash
- question contract version/hash
- disposition policy version/hash
- adapter version
- provider ID
- model requested
- expected returned model
- model discovery reference/hash
- Scanner baseline identity rules
- selection/strategy/horizon identity rules

### 15.2 scope

- market scope
- allowed horizons = SHORT/MEDIUM
- action = ENTRY_CANDIDATE
- activation-forward recruitment
- duplicate analysis-unit rule

### 15.3 thresholds

- threshold_low
- threshold_high
- boundary comparison semantics
- rounding policy

### 15.4 runtime

- total deadline
- concurrency cap
- queue cap
- retry count
- recruitment duration
- max recruited candidates
- budget
- per-call budget reservation
- cost unknown handling

### 15.5 privacy

- approved payload class
- provider policy checked_at
- retention/account note
- source transmission approval identity

### 15.6 outcome/evaluation link

- evaluation policy ID/hash
- observation windows
- max holding
- execution/cost policy token

---

## 16. Trial numeric values — freeze status

다음 **구조는 동결**하지만 숫자값 전체를 이번 문서가 임의로 확정하지 않는다.

| 항목 | Freeze status |
|---|---|
| threshold L/H slot | FROZEN STRUCTURE / VALUE PENDING SYNTHETIC |
| versioned model requirement | FROZEN |
| SHORT/MEDIUM scope | FROZEN |
| retry default 0 | FROZEN |
| explicit activation | FROZEN |
| max recruited | VALUE PENDING TRIAL V2 |
| duration | VALUE PENDING TRIAL V2 |
| min mature | VALUE PENDING EVALUATION V2 |
| min review disagreements | VALUE PENDING EVALUATION V2 |
| semantic abstain gate | VALUE PENDING SYNTHETIC |
| review burden gate | VALUE PENDING SYNTHETIC |
| error/late gate | VALUE PENDING TRIAL V2 |
| API budget | VALUE PENDING ACCOUNT/COST BINDING |

기존 V1의 90d/200/60/12/5%/30%/50%/$5를 자동 복사하지 않는다.

이 값들은 implementation architecture를 바꾸지 않는 **pre-trial policy binding**이다.

---

## 17. Evaluation V2 denominator freeze

기존 outcome kernel과 `JEV_DEFER_THIS_OPPORTUNITY_V1` 비교 의미는 유지한다.

새 evaluator는 **review row가 아니라 recruitment ledger**를 모집군 source of truth로 사용해야 한다.

### 17.1 funnel

- `captured`: 기간 내 canonical ENTRY_CANDIDATE
- `in_scope`: frozen scope에 맞는 candidate
- `recruited R`: duplicate 제거 후 모집 ledger unit
- `callable Q`: local/provider/privacy/budget gate 통과
- `attempted A`: 실제 provider request 시작
- `valid V`: on-time + typed valid + model verified + mapping 완료
- `decisive`: PASS_THROUGH 또는 REVIEW_REQUIRED
- `performance C`: R 중 CLOSED + non-null baseline net return

### 17.2 rates

- semantic abstain rate = ABSTAIN / V
- review rate valid = REVIEW_REQUIRED / V
- review burden recruited = REVIEW_REQUIRED / R
- skip/no-call rate = pre-call skip / R
- operational failure rate = ERROR/LATE/INTERRUPTED / A
- coverage attempted = A / Q
- coverage valid = V / R

분모 0은 0%가 아니라 null/N/A다.

### 17.3 performance

`d_i = 1` iff:
- on-time VALID
- verified model
- frozen policy
- REVIEW_REQUIRED

그 외 `d_i = 0`.

`C`는 CLOSED + non-null baseline net return.

`r_shadow,i = (1-d_i)r_i`

`Delta = sum(-d_i * r_i) / |C|`

CENSORED는 0 return으로 변환하지 않는다.

### 17.4 probability diagnostics

Phase 1 최소 진단:

- q1/q2/q3 LOW/GRAY/HIGH 비율
- q1/q2 review 기여
- q3 HIGH/GRAY 비율
- threshold 근처 밀도
- model/cohort별 coverage
- skip reason
- ERROR/LATE

미래수익으로 Noul calibration을 주장하지 않는다.

별도 blind semantic label이 없는 한 Brier score를 필수 gate로 만들지 않는다.

---

## 18. UI freeze

기본 Monitor에는 raw probability를 노출하지 않는다.

### 기본 user-facing projection

PASS_THROUGH:
- `추가 확인 신호 없음`

REVIEW_REQUIRED:
- `재검토 필요`
- reason 최대 2개
  - `전략 조건 맥락 확인`
  - `진입 설명 맥락 확인`

ABSTAIN:
- `판단 유보`
- `해석 근거 부족` 또는 `맥락 불확실`

운영상:
- 검토 안 함
- 검토 오류
- 시간 초과
- 중단

금지:

- AI 종목 점수
- 매수 확률
- 수익 확률
- rank badge
- 자동 action

probability 원문은 local audit에서만 기본 보존한다.

---

## 19. Legacy V1 correction freeze

OpenAI/Terra V1은 TypeSafe V2로 mutate하지 않는다.

### V1

- frozen hash/history 보존
- 실제 TypeSafe 준비 상태로 취급 금지
- 신규 activation/readiness 경로에서 차단
- legacy read-only history
- 과거 fake/config record를 TypeSafe typed answer로 backfill 금지

### V2

- 별도 protocol/artifact
- 별도 TypeSafe storage semantics
- 별도 cohort
- 신규 network activation은 V2만 허용

실제 provider call 0이므로 dual-write나 historical response conversion은 필요 없다.

---

## 20. Future storage direction freeze

기존 V1 schema에 TypeSafe semantics를 억지로 넣지 않는다.

향후 additive V2 family를 사용한다.

logical family:

- `jev_typesafe_protocol`
- `jev_typesafe_activation`
- `jev_typesafe_recruitment`
- `jev_typesafe_review`
- `jev_typesafe_evaluation_run`
- `jev_typesafe_evaluation_unit`
- `jev_typesafe_comparison_report`

정확한 SQL은 다음 implementation 단계에서 작성하지만 다음 의미는 변경하지 않는다.

- recruitment unit이 review 성공 여부보다 먼저 존재
- terminal review immutable
- operational status와 disposition 분리
- external state / typed answer / derived disposition 분리
- known cost와 unknown/outstanding cost 분리
- restore 후 network OFF
- PENDING restart → INTERRUPTED
- 자동 retry 없음

---

## 21. Implementation obligations for TYPE-JEV-CORE-CORRECTION

다음 implementation은 이 문서에서 architecture를 다시 선택하지 않는다.

반드시:

1. OpenAI/Terra wire adapter 제거/격리
2. TypeSafe System One typed adapter 추가
3. prompt/JSON-schema reviewer를 question contract로 대체
4. 3-Noul contract 구현
5. minimized state projector 구현
6. fixed semantic mapping 구현
7. deterministic disposition policy 구현
8. legacy V1 신규 activation 차단
9. additive V2 storage/migration
10. recruitment ledger
11. unknown-cost-safe budget reservation
12. backup/restore V2 추가
13. fake provider deterministic tests
14. baseline immutability regression
15. actual network/API call 0 유지

구현자가 임의로:
- Noul을 다시 4개로 늘리거나
- Score/Choice를 추가하거나
- News/Macro/Holdings를 붙이거나
- Risk 판정을 Jev로 넘기거나
- threshold 값을 코드에 hard-code하거나
- alias model을 기본값으로 쓰면 안 된다.

---

## 22. External blockers — architecture gap 아님

다음은 설계가 부족해서 남은 질문이 아니라 실제 외부 사실을 확인해야 하는 activation blocker다.

1. TypeSafe 계정에서 사용 가능한 versioned model
2. canary에서 실제 `response.model`
3. account retention/ZDR/billing terms
4. 현재 공식 가격과 local budget reservation 기준
5. synthetic boundary set에서 L/H 후보값의 review/abstain burden
6. Trial V2 numeric recruitment/evaluation gates

이 값은 실제 provider를 사용하기 전 확인해야 하지만 Core Correction 코드를 설계하는 데 새 architecture 결정을 요구하지 않는다.

---

## 23. Design Freeze completion gates

| Gate | 결과 |
|---|---|
| DF-1 Jev fuzzy boundary | PASS — strategy/entry semantic coherence만 |
| DF-2 deterministic owner | PASS — Strategy/Risk/price/ranking 유지 |
| DF-3 v3 Q1~Q4 처분 | PASS — MODIFY/KEEP, MODIFY/KEEP, DROP, KEEP |
| DF-4 source path | PASS — Scanner candidate + repro details + entry guide |
| DF-5 external state | PASS — JEV_TYPESAFE_STATE_V1 |
| DF-6 local audit | PASS |
| DF-7 question contract | PASS — 3 Noul |
| DF-8 typed answer→disposition | PASS |
| DF-9 operational semantics | PASS |
| DF-10 threshold governance | PASS — structure frozen, numeric pre-trial binding |
| DF-11 model policy | PASS — versioned + returned verification |
| DF-12 privacy class | PASS — minimized semantic state |
| DF-13 Trial V2 required schema | PASS |
| DF-14 Evaluation V2 denominator | PASS |
| DF-15 V1 legacy handling | PASS |
| DF-16 external blocker separation | PASS |
| DF-17 implementation architecture closure | PASS |

---

## 24. 다음 단계

다음 단계는:

**TYPE-JEV-CORE-CORRECTION**

이다.

단, 이 문서의 완료가 실제 TypeSafe provider 호출 승인이나 prospective trial 시작을 뜻하지 않는다.

다음 단계의 완료 목표는 **코드를 TypeSafe contract에 맞게 교정하되 실제 network/model call은 0으로 유지하는 것**이다.

실제 external discovery/canary는 이후 사용자 명시 승인 단계에서만 수행한다.

---

## 25. 작업 경계 기록

이번 TYPE-JEV-DESIGN-FREEZE에서는:

- backend/frontend 코드 수정 없음
- 기존 JSON contract 수정 없음
- migration 실행 없음
- runtime DB 접근 없음
- TypeSafe API 호출 없음
- OpenAI API 호출 없음
- JEV_API_KEY 값 접근 없음
- .env 접근 없음
- R5R actual evaluation 없음
- Holdout 검색/metadata/hash/존재 probe 포함 접근 없음

변경 대상은 이 설계동결 문서 1개뿐이다.
