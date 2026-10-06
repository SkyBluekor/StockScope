# StockScope TypeSafe Jev Canary 정책 재설계 v1

작성일: 2026-10-06 (Asia/Seoul)

작업 모드: **DESIGN / ANALYSIS ONLY**

확인한 로컬 `main` 및 작업 HEAD: `8304781928f3e975c7abcd0f49701eeeade70ebf`

산출물: 이 설계 문서 1개. 코드·JSON contract·migration·frontend·기존 문서는 변경하지 않는다.

## 1. 결론과 적용 범위

**Canary V1 실패의 주원인은 연결 장애가 아니라, 모든 질문에 같은 LOW/GRAY/HIGH를 강제하고 Q3의 GRAY를 전면 유보로 바꾼 정책이다. 잘못되거나 모호한 gold와 Q2의 입력 범위 문제도 함께 발견됐다.** 모델의 유용성이 검증됐다는 결론도, 모델이 전반적으로 불안정하다는 결론도 내리지 않는다.

| 결정 항목 | 이번 결정 |
|---|---|
| V1 실패 원인 | threshold architecture + gold 품질 + 질문 범위의 복합 원인. provider failure 증거 없음 |
| Phase 1 architecture | **B: question-specific one-sided escalation**. Q3 evidence gate 후 Q1/Q2 conflict gate |
| Q1 | **유지 + 명료화**: 제공된 condition 의미와 strategy intent의 실질적 충돌 |
| Q2 | **수정 후 검증 대상으로 유지**: strategy description의 price-rule 의미와 entry_context 표현을 직접 비교. 존재하지 않는 UI 문구 추정 금지 |
| Q3 | **유지 + 명료화**: 제한된 두 명제를 해석하는 데 필수 의미가 빠졌는지 판단. 일반적 불확실성과 구분 |
| Risk fuzzy question | 삭제 상태 유지. 복구하지 않음 |
| model binding | request channel과 returned concrete identity 분리. preview를 immutable version으로 분류하지 않음 |
| V1 지위 | **EXECUTED / DIAGNOSTIC FAIL**, 향후 설계를 위한 DIAGNOSTIC / CALIBRATION CANARY |
| V2 | 새 synthetic fixture 24개, 각 3회 반복, 선택용 12개와 확인용 12개. 설계만 완료 |
| threshold | 후보군·선택 절차·실패 규칙 설계. **final threshold NOT FROZEN** |
| Trial V2 | V2 PASS 및 별도 구현·binding·freeze 조건 충족 전 BLOCKED |

이 문서는 미래 acceptance에 사용할 정책 설계를 대체한다. 현재 실행 코드가 이미 바뀌었거나 새 protocol이 machine-readable하게 동결됐다는 뜻은 아니다. 기존 `JEV_TYPESAFE_CANARY_PROTOCOL_V1.json`, 실행 report, model binding 및 설계동결 v1은 당시 이력으로 그대로 보존한다. V1 결과를 PASS로 재작성하지 않는다.

JEV는 **TypeSafe AI Jev / System One**이다. OpenAI/Terra V1은 LEGACY이며 신규 activation 차단을 유지한다. 다음 경계도 유지한다.

`canonical ENTRY_CANDIDATE → minimized semantic state → typed questions → StockScope deterministic policy → disposition`

Strategy eligibility, condition PASS/FAIL, Risk READY/CAUTION/HOLD, entry/stop/target, R/R, ranking, 가격 산술, 매수·매도 및 미래수익 판단은 Jev의 권한이 아니다. `PASS_THROUGH`는 “추가 의미 검토 신호 없음”이며 종목·거래의 안전성 인증이 아니다. `ABSTAIN`도 기존 후보를 제거하지 않는다.

## 2. 근거와 읽기 범위

다음 repository 파일을 근거로 삼았다. 상대경로는 repository root 기준이다.

| 근거 | 사용 범위 |
|---|---|
| `docs/StockScope_인수인계_2026-10-06_DOCS_CLEANUP_COMPLETE_JEV_SHADOW_NEXT.md` | 제품 목적, TypeSafe correction, Monitor/Evaluation 경계 |
| `docs/설계/StockScope_TypeSafe_Jev_설계동결_v1_2026-10-06.md` | state/question/disposition/model의 기존 약속 |
| `docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V1.json` | 12개 state와 사전 expected_bands |
| `docs/validation/JEV_TYPESAFE_CANARY_V1_2026-10-06.json` | 실제 24개 records, 비용 추정, errors |
| `docs/contracts/JEV_TYPESAFE_MODEL_BINDING_V1.json` | discovery 목록과 request/response 관측 |
| `backend/app/jev/typesafe_questions.py` | 실제 instructions와 true/false criteria |
| `backend/app/jev/typesafe_policy.py` | disposition 순서 및 equality 경계 |
| `backend/app/jev/typesafe_canary.py` | model selector, 52개 check의 분모, band stability 계산 |
| `backend/app/jev/typesafe_provider.py` | native response/model/usage 검증 경계 |
| `backend/app/jev/typesafe_state.py` | 실제 projector allowlist와 no-call 조건 |
| `backend/app/jev/typesafe_models.py`, `typesafe_projection.py`, `typesafe_evaluation.py` | threshold slot, disposition 재검증, cohort identity 관련 부분만 |

인수인계의 “REAL CANARY PENDING” 및 설계문서의 과거 HEAD는 작성 당시 상태다. 이번 분석의 실행 사실은 실제 V1 report를 우선한다. 원격 main의 최신 여부는 확인하지 않았으며, 위 SHA는 현재 repository의 로컬 main이다. 이전 R4/R5/R5R 설계 파일은 다시 열지 않았다.

기존 JSON을 읽어 산술과 정책 결과만 독립적으로 재계산했다. project 모듈 import, canary runner, dry-run, runtime service, 평가 엔진을 실행하지 않았다. dry-run도 V1 protocol을 재생성할 수 있으므로 사용하지 않았다. 외부 API·웹 조회 및 credential 접근도 하지 않았다. 아래 가격은 현재 가격 조사 결과가 아니라 **V1 report에 저장된 당시 public-price snapshot**이다.

## 3. V1 실제 결과 재확인

### 3.1 운영과 응답

| 항목 | 기록 및 재확인 |
|---|---|
| discovery / System One / total | 1 / 24 / 25 |
| records | 12 fixture × 2회 = 24, 누락 없음 |
| input / output tokens | records 합계 25,518 / 1,560 |
| 당시 public-price 추정 | `25,518 / 1,000,000 × 0.042 = USD 0.001071756`; output 단가 snapshot은 0 |
| request / response | 전부 `jev-preview` / `jev-1.13.0` |
| identity change error | 0 |
| 최종 status / errors | `FAIL` / `[CANARY_NO_ELIGIBLE_THRESHOLD]` |
| real stock data / actual activation | false / false |
| account policy | `NOT_VERIFIED_BY_CANARY` |

24개 응답이 validator를 통과한 기록으로부터 **이 canary에서 provider connection 및 model response contract는 PASS**라고 판단한다. 계정별 retention/ZDR/billing이나 장기 가용성까지 확인됐다는 뜻은 아니다. public-price estimate는 실제 청구 금액 확정값이 아니다.

### 3.2 모든 probability records

각 셀은 `repetition 1 / repetition 2`다. 값을 반올림해 threshold에 대입하지 않았다.

| fixture_id | Q1 | Q2 | Q3 |
|---|---:|---:|---:|
| normal-01 | .19 / .19 | .28 / .27 | .36 / .38 |
| normal-02 | .20 / .19 | .29 / .29 | .40 / .38 |
| future-uncertainty-control | .21 / .19 | .27 / .26 | .32 / .34 |
| strategy-conflict-01 | .91 / .91 | .49 / .54 | .48 / .47 |
| strategy-conflict-02 | .69 / .62 | .35 / .35 | .47 / .45 |
| entry-conflict-01 | .23 / .24 | .57 / .59 | .49 / .46 |
| entry-conflict-02 | .18 / .18 | .21 / .31 | .39 / .41 |
| evidence-insufficient-01 | .19 / .19 | .66 / .63 | .88 / .87 |
| evidence-insufficient-02 | .14 / .15 | .62 / .62 | .87 / .88 |
| ambiguous-strategy-01 | .27 / .30 | .28 / .28 | .46 / .46 |
| ambiguous-entry-01 | .18 / .18 | .42 / .40 | .46 / .48 |
| compound-conflict-01 | .84 / .83 | .84 / .83 | .49 / .47 |

### 3.3 52개 hard check와 실제 사용자 disposition은 다르다

hard fixture는 10개다. 그중 evidence-insufficient 2개는 Q1/Q2가 ANY이므로, 반복당 `8 × 3 + 2 × 1 = 26`, 두 반복에서 52개 **question-band check**다. 52개 독립 사례나 52개 disposition이 아니다.

| L / H | Q1 mismatch / 16 | Q2 mismatch / 16 | Q3 mismatch / 20 | 합계 / 52 | hard band instability | 정책을 records에 적용한 disposition |
|---|---:|---:|---:|---:|---:|---|
| .10 / .90 | 14 | 16 | 20 | 50 | 0 | ABSTAIN 24, REVIEW_REQUIRED 0, PASS_THROUGH 0 |
| .15 / .85 | 14 | 16 | 16 | 46 | 0 | ABSTAIN 24, REVIEW_REQUIRED 0, PASS_THROUGH 0 |
| .20 / .80 | 5 | 14 | 16 | 35 | 1 | ABSTAIN 24, REVIEW_REQUIRED 0, PASS_THROUGH 0 |

세 후보 모두 Q3의 최솟값 .32가 L을 초과하므로 Q1/Q2까지 도달하지 못하고 전건 ABSTAIN이 된다. 위 disposition은 report에 저장된 실적값이 아니라, **저장된 확률에 현재의 순수 policy 정의를 적용한 진단값**이다.

유일한 hard band instability는 `.20/.80`의 `future-uncertainty-control / Q1`: `.21 → .19`에 따른 GRAY→LOW다. 모든 후보의 disposition crossing은 0/12 fixture지만, 전건 같은 ABSTAIN이기 때문이며 바람직한 안정성을 뜻하지 않는다.

### 3.4 반복 차이와 해석 한계

| 질문 | 12쌍의 최대 절대차 | 평균 절대차 |
|---|---:|---:|
| Q1 | .07 | .01333 |
| Q2 | .10 | .02083 |
| Q3 | .03 | .01667 |

Q1 최대차는 strategy-conflict-02, Q2 최대차는 entry-conflict-02다. 두 번씩의 짧은 실행만으로 deterministic이라고 하거나 장기 안정성을 주장하지 않는다. 반대로 광범위한 무작위 변동이 주원인이라는 증거도 없다. 독립 시행 여부, 장기간 channel 변화 및 다른 model에서의 재현성은 미검증이다.

Q3는 normal군 .32–.40, insufficient군 .87–.88로 분리됐다. 다만 후자는 설명 자체가 불완전함을 선언하고 UNSPECIFIED/UNKNOWN을 포함하는 쉬운 대조다. 실용적인 의미 부족 전반에 대한 감도를 증명하지 않는다. Noul을 교정된 빈도 확률이나 정답률로 취급하지 않는다.

## 4. 12 fixture의 gold 의미 감사

감사의 근거는 **state와 question proposition**이다. 출력에 맞춰 label을 수정하지 않는다. 이번 분석자는 records도 읽었으므로 감사 절차 자체를 맹검이라고 부르지 않는다. 아래 논증은 출력과 무관하게 state에서 도출했으며, V2에서는 응답 전에 같은 감사를 마친다.

분류 단위는 fixture 전체다. 일부 기대가 타당해도 하나의 hard 기대가 명백하게 모순되면 INVALID_GOLD다. VALID_GOLD는 명제의 긍정/부정 방향이 타당하다는 뜻이며, .10/.90 같은 수치 band의 정당성까지 뜻하지 않는다.

| fixture_id / V1 기대(Q1,Q2,Q3) | state와 proposition에 근거한 논증 | 판정과 처리 | 다음 검증 |
|---|---|---|---|
| normal-01 / LOW,LOW,LOW | continuation과 above, adequate participation과 1.3x, executable role과 true가 일치한다. PASS를 재계산할 필요가 없다 | **VALID_GOLD**. 음성 의미 대조로 타당하나 수치 LOW 강제는 별도 문제 | 새 normal에서 불필요한 review/abstain 측정 |
| normal-02 / LOW,LOW,LOW | 설명은 trend와 participation을 전제하지만 conditions는 slope와 relative strength뿐이다. 상대강도를 참여량으로 바꿔 읽을 근거는 없다. already-passed를 충분한 보증으로 볼지 참여량 설명이 빠졌다고 볼지 모호하다 | **AMBIGUOUS_GOLD**. Q1 충돌은 명백하지 않지만 Q3 LOW도 유일한 hard truth가 아니다 | V2 normal에 필수 의미 전제를 모두 명시 |
| future-uncertainty-control / LOW,LOW,LOW | 현재 trend review에 필요한 above/participation이 있고 미래수익은 불필요하다고 명시한다. 미래를 모르는 것은 이 명제의 근거 부족이 아니다 | **VALID_GOLD**. 미래정보 부재를 이유로 Q3를 긍정할 필요가 없다 | 다른 문구의 future negative control |
| strategy-conflict-01 / HIGH,LOW,LOW | strategy는 below를 요구하고 above continuation을 명시적으로 피한다. condition은 above다. 설명 사이의 반대 관계로 Q1을 긍정할 수 있고 entry는 내부적으로 일치한다 | **VALID_GOLD**. 명백한 모순 자체가 Q3 부족은 아니다 | 충분한 근거가 있는 충돌을 ABSTAIN으로 숨기지 않는지 검증 |
| strategy-conflict-02 / HIGH,LOW,LOW | weak participation / unusually active의 정의 없이 1.6x를 반드시 unusually active로 분류하려면 정도 해석이 필요하다. 충돌 방향은 있지만 HIGH를 강제할 의미상 강도는 고정되지 않았다 | **AMBIGUOUS_GOLD**. 방향 진단에만 사용하고 모델 오류로 단정하지 않는다 | 산술 재계산 없이 참여량의 의미를 명시한 새 대조 |
| entry-conflict-01 / LOW,HIGH,LOW | description은 확인 threshold와 buy range를 구분한다. state도 STRATEGY_CONDITION_THRESHOLD, false, SEPARATED다. ENTRY_CANDIDATE가 그 threshold를 buy range로 표시했다는 증거는 없다 | **INVALID_GOLD**. Q2 HIGH의 근거가 없고 구분은 오히려 일치한다 | condition-only를 정상 통과시키는 false-positive trap |
| entry-conflict-02 / LOW,HIGH,LOW | 확인 band와 실행을 구분하라는 설명에 condition role / false / SEPARATED가 일치한다. RANGE는 형태이지 실행 허가가 아니다. 입력에는 잘못된 실제 표시문이 없다 | **INVALID_GOLD**. Q2 HIGH가 state와 반대 해석을 강제한다. 낮은 출력을 모델 오류로 계산하지 않는다 | 같은 구분을 새 문구의 음성 대조로, 명시적인 의미 불일치를 양성 대조로 구성 |
| evidence-insufficient-01 / ANY,ANY,HIGH | intent를 결정할 수 없다고 명시하고 condition 값은 null, entry role은 UNSPECIFIED다. 없는 의미를 창작하지 않고 두 review를 판단할 수 없다 | **VALID_GOLD**, 단 provider 단독의 쉬운 부족 대조다. 실제 local gate 통과 여부는 별개 | 알려진 enum과 비어 있지 않은 field를 유지하면서 의미만 부족한 예 |
| evidence-insufficient-02 / ANY,ANY,HIGH | description이 의도적으로 불완전하고 participation 값은 null, entry 의미도 불명확하다. Q3 긍정은 state만으로 논증된다 | **VALID_GOLD**, local gate와 중복될 수 있다 | insufficient라는 정답 표현을 직접 주지 않는 예 |
| ambiguous-strategy-01 / ANY,LOW,LOW (soft) | mild pullback의 허용 조건은 broader structure constructive지만 near threshold / slightly positive만으로 그 의미가 확정되지는 않는다 | **AMBIGUOUS_GOLD**. Q1 ANY는 타당하지만 Q3 LOW도 유일한 답으로 강제하지 않는다 | 주어진 정보 안의 정도 모호성과 필수 의미 누락 분리 |
| ambiguous-entry-01 / LOW,ANY,LOW (soft) | 확인과 실행을 구분하는 description과 false는 일치한다. 다만 CONDITION_BAND_NEAR_EXECUTION / NEAR의 정의가 부족하다. 근접 자체가 오표시는 아니다 | **AMBIGUOUS_GOLD**. Q2 양성의 증거로 쓰지 않는다 | 알려진 role로 근접/overlap 음성 대조 구성 |
| compound-conflict-01 / HIGH,HIGH,LOW | below와 above의 Q1 충돌은 유효하다. Q2는 비실행 threshold와 후보 상태가 함께 있을 뿐, 실행 범위라는 표시를 보여주지 않는다. only executable range as entry도 후보를 주문과 동일시할 근거는 아니다 | **INVALID_GOLD: Q1 부분은 유효, Q2 부분은 무효**. 두 질문 모두 양성이라는 증거로 쓰지 않는다 | 전략 충돌과 동일 price-rule의 설명 충돌을 각각 명시 |

집계는 **VALID_GOLD 5 / AMBIGUOUS_GOLD 4 / INVALID_GOLD 3**이다. V1 report의 52 check를 다시 쓰는 집계가 아니다. 당시 mismatch는 당시 protocol의 실패로 보존하고 모델 품질의 오류율로 전용하지 않는다.

특히 entry-conflict-01과 02는 현행 Q2가 참조할 수 있는 **entry_context와 baseline이 완전히 동일**하다. 둘 다 비실행 확인 구간을 명시적으로 구분한다. 출력 차이의 원인은 반복 변동, 한 request에 함께 제공된 다른 field의 영향 등을 별도로 검증해야 한다. 원인은 미확정이지만 한 사례만 정상 gold로 바꾸고 나머지를 양성으로 남길 근거는 없다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: 위 의미 모순이 존재 → band mismatch와 모델 오판을 혼동 → 출력에 맞춘 gold 수정 / 전부 폐기 / 의미 감사를 별기 → **감사를 별기하고 V1을 diagnostic으로 제한** → 이력과 설계상 교훈을 모두 보존 → V2 gold는 응답 전에 state로 논증한다.

## 5. 핵심 가설과 실패 원인 판정

| 가설·원인 | 관찰 사실 → 문제 | 선택지 → 채택 결정 | 이유 → 다음 검증 |
|---|---|---|---|
| A: 극단적인 binary band 전제 | normal도 전건 ABSTAIN, Q3 최솟값 .32 > 모든 L | L만 상향 / architecture 변경 → **architecture 변경 지지** | 모든 질문의 부정 확률을 작게 증명할 필요가 없다. 다른 모델의 일반적 baseline은 단정하지 않는다 → 새 normal의 false intervention 측정 |
| B: 강한 문제 신호만 escalation | 추가 의미 검토가 제품 목적이고 Q1 양성도 Q3 GRAY에 차단 | one-sided / 모든 GRAY 유보 → **one-sided 채택** | 불필요한 경고를 줄이면서 양성 감도도 별도로 요구할 수 있다 → false positive와 miss를 모두 gate화 |
| C: 질문별 threshold | Q1/Q2는 conflict, Q3는 evidence 부족으로 양성 의미와 분포가 다름 | 공통값 / 질문별 값 → **질문별 slot** | 같은 p가 같은 제품 손실이라는 근거가 없다 → 명제별 gate와 최종 disposition 분리 |
| provider/API/auth/schema | 완료 24건, 운영 error 없음 | 장애 원인으로 분류 / 이번 원인에서 제외 → **주원인에서 제외** | 응답 도달과 의미 품질은 다르다 → V2도 모든 응답 validator 통과 요구 |
| model instability | 작은 차이 중심, hard band flip 1, identity 변화 0 | deterministic / 불안정 실패 / 제한적 안정 → **제한적 안정** | 두 번으로 장기·경계 동작을 추정할 수 없다 → 3회 반복의 disposition/reason crossing |
| gold / question design | entry 양성 근거 부족, Q2에 strategy text 참조권 없음 | threshold로 구제 / gold와 질문 분리 교정 → **분리 교정** | 무효 gold에 맞추면 사용자에게 오경고를 줄 수 있다 → 새 Q2 정·부 대조 |
| model selector | preview를 versioned로 오분류 | latest 문자열 제외 / channel 명시 분류 → **명시 분류** | immutable성 증거가 없다. binding 결함이나 유일한 canary error의 직접 원인은 아니다 → §9 |

V1은 architecture를 의심할 충분한 진단 자료지만 one-sided의 실효성이나 특정 threshold의 우위를 증명한 비교 시험은 아니다.

## 6. policy architecture 비교와 채택

| 평가 기준 | A: 공통 LOW/GRAY/HIGH | B: 질문별 one-sided | C: evidence 우선 + threshold 근처만 유보 |
|---|---|---|---|
| 사용자 가치 | 명확한 부정이 모여야 통과. V1에서는 유용할 수 있는 신호까지 유보에 묻힘 | 충분한 문제 신호만 재검토로 전달 | 경계 변동에 따른 표시 반전을 국소적으로 줄일 가능성 |
| review / abstain burden | 세 질문의 GRAY가 누적. V1은 abstain 100% | 중간 p만으로 유보하지 않음. 감도 gate가 필수 | 근처 구간 폭에 따라 유보가 다시 증가 |
| false escalation | HIGH만 쓰면 적어 보이나 전부 유보라면 무가치 | Q1/Q2별 음성 대조와 잘못된 reason 측정 가능 | 경계 제외로 줄 수 있으나 miss를 유보로 숨길 위험 |
| fail-safe | 운영 실패와 의미 유보를 분리할 수 있음 | 같은 분리 유지. Q3가 의미 부족을 담당 | 운영 분리에 근처 구간 처리 사유·우선순위가 추가됨 |
| 해석 가능성 | 작은 p가 필수인 이유를 제품 목적과 연결하기 어려움 | 근거 부족 / 의미 충돌 / 추가 신호 없음에 직접 대응 | uncertainty 폭의 의미를 추가 설명해야 함 |
| 평가 가능성 | band 정답과 제품 행동이 섞이기 쉬움 | 명제별 gate, disposition, 부담 분리가 쉬움 | threshold와 구간 폭 동시 선택은 자유도를 늘림 |
| V1 근거 | 현 후보에서는 부적합 | 개선 가설, 성능은 미검증 | 추가 복잡성을 정당화할 경계 반전 근거가 아직 부족 |

C에서는 같은 response의 Q3를 먼저 적용하는 논리적 두 단계와, Q3만 별도 호출하는 물리적 두 단계를 구분한다. 후자는 call 수·지연·질문 맥락을 바꾸므로 채택하지 않는다. B도 Q3가 우선이지만 C와 같은 추가 근처 band는 없다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: V1 전건 유보, 주요 경계 반전은 미검증 → A의 부담은 과도하고 C의 추가 parameter 이익은 불명확 → A/B/C → **B 채택** → 세 threshold로 제품 행동에 직접 대응 → V2의 clear-gold error·부담·crossing gate로 검증. B 실패 시 C로 자동 전환하지 않고 새 protocol에서 필요성을 논증한다.

### 6.1 채택 논리

다음은 설계 의사 코드이며 현재 runtime 변경이 아니다.

```text
local deterministic gate failure -> SKIPPED, disposition=null, no call
provider/schema/usage/model identity failure -> ERROR, disposition=null
deadline/recovery failure -> LATE or INTERRUPTED, disposition=null

on-time, typed valid, verified response only:
  if p3 >= T_evidence:
      ABSTAIN / EVIDENCE_INSUFFICIENT
  else if p1 >= T_strategy or p2 >= T_entry:
      REVIEW_REQUIRED / applicable conflict reasons
  else:
      PASS_THROUGH / NO_ADDITIONAL_CONTEXT_CONFLICT
```

비교는 `p<T`와 `p>=T`이며 표시용 반올림 전의 값을 사용한다. 누락·bool·NaN·무한대·범위 밖 값은 threshold 미도달로 통과시키지 않는다. 질문 간 확률을 합산·평균·곱하여 점수를 만들지 않는다.

Q3 미도달은 충분성의 증명이 아니라 근거 부족 escalation 기준에 도달하지 않았다는 뜻이다. Q1/Q2 미도달도 정확성 인증이 아니다. Q1/Q2의 중간 p만으로 ABSTAIN을 부여하지 않는다. threshold 근처는 local 진단으로 기록하고 자동 재호출·다수결·임의 유보를 추가하지 않는다.

reason은 threshold 이상인 질문만 사용한다. 둘 다 해당하면 **고정 순서 Q1→Q2**이며 원시 p 크기로 우선순위를 정하지 않는다. 다른 명제의 p 크기가 사용자 중요도를 뜻하지 않기 때문이다. Q3 우선이면 높은 Q1/Q2도 사용자용 review reason으로 승격하지 않는다. typed answer 전체는 audit에 남긴다.

fail-safe는 운영상 무효 응답을 정상 판단에 넣지 않고 기존 baseline을 유지하는 방식으로 보장한다. shadow 비교의 virtual defer는 계속 `VALID + REVIEW_REQUIRED`만 사용한다. SKIPPED/ERROR/LATE/INTERRUPTED/ABSTAIN을 후보 제거 또는 0% 수익으로 바꾸지 않는다.

## 7. Q1/Q2/Q3의 가치와 질문 교정

### 7.1 질문별 가치 판정

| 관점 | Q1 | Q2 | Q3 |
|---|---|---|---|
| 단일 명제인가 | 조건 의미와 전략 의도의 실질적 충돌 하나로 제한 가능 | 현행 could mislead는 알 수 없는 UI 해석까지 넓음. 교정 후 같은 rule의 설명과 state 의미 불일치 하나로 제한 | 두 review를 위한 필수 의미가 부족한가라는 한 명제. 어느 질문이 부족한지는 scalar로 분리되지 않음 |
| current state만으로 가능한가 | 명시된 description과 condition으로 제한하면 가능 | 현행 entry_context/baseline만으로 실제 표시 의미를 비교할 수 없음. 이미 있는 strategy_description 참조를 허용하면 가능한 사례가 있음 | field 존재는 local, 그 뒤 남는 의미 누락은 가능 |
| deterministic 중복인가 | 숫자 PASS/FAIL 재판정은 중복. 설명 조합의 의미만 검토 | role/flag 모순과 가격 유효성은 local. 자연어 description과 role의 의미 비교만 유지 | 필수 field 누락/unknown mapping/크기 초과는 local에서 처리. Q3로 구제하지 않음 |
| normal baseline p의 가능한 이유 | material의 정도, 축약 설명, 응답 척도. 원인 미확정 | 실제 UI 부재 및 후보를 실행 지시로 오해할 수 있는 넓은 wording. 원인 미확정 | reliably와 ambiguous가 일반적 불확실성까지 포함할 수 있음. 원인 미확정 |
| 실제 분리 증거 | 명백한 below/above는 .91, normal은 .19 전후로 제한적 지지 | 유효한 clear positive군이 없어 감도·분리 미입증 | 쉬운 부족 .87–.88 대 normal .32–.40으로 가치 가설 지지 |
| 사용자 추가 가치 | PASS 조건과 전략 설명의 불일치 재확인 | 확인 조건과 실행 범위 설명의 혼동 재확인 | 빠진 의미를 모델이 보충하여 단정하는 일을 억제 |
| 결정 | KEEP + CLARIFY | MODIFY / KEEP FOR V2 VALIDATION | KEEP + CLARIFY |

baseline p의 원인은 가설이며 확인된 provider 특성이 아니다.

현재 projector는 condition의 `current_value/required_value=null`을 허용하며 `semantic_role`은 비어 있지 않은지만 검사한다. 따라서 V1의 부족 fixture가 반드시 local에서 차단됐을 것이라고 단정하지 않는다. V1 harness는 external state를 직접 호출했으므로 production local gate 통과 증거도 없다. 선택적 값의 null 하나를 무조건 의미 부족으로 해석하지 말고, 실제로 그 빠진 의미에 따라 제한된 명제의 결론이 달라지는지를 확인해야 한다.

### 7.2 새 question contract에 넣을 고정 의미

아래는 후속 새 question version의 문안이다. V1 instructions/hash는 변경하지 않는다. Q2의 참조 범위를 명시적으로 고치지만 **외부 state field 추가는 요구하지 않는다**.

**Q1 — strategy_context_conflict**

> 제공된 strategy description의 조건 관련 의도와, 이미 PASS로 판정된 condition_context의 의미 사이에 사용자가 재확인할 만한 명시적·실질적 불일치가 있는가. entry role 비교는 Q2에 맡긴다. 숫자 판정을 다시 계산하거나 미기재 시장 조건을 보충하지 않는다.

true: 주어진 조건 의미가 설명된 의도를 부정하거나 배제한다.

false: 의미가 일치하거나 명시적으로 허용된 변동 범위다. 통상적인 미래 불확실성은 충돌이 아니다.

**Q2 — entry_context_conflict**

> strategy_context.strategy_description에 적힌 해당 price rule의 확인 조건/실행 범위라는 의미와, entry_context.price_rule이 표현하는 같은 rule의 의미가 실질적으로 불일치하는가. baseline은 후보라는 배경만 제공한다. ENTRY_CANDIDATE 자체는 주문이나 실행 범위 선언이 아니다.

true: 설명이 확인 용도로 제한한 같은 rule을 entry context가 실행 가능하다고 표현하는 등, 양쪽 근거가 실제로 제공되고 의미가 반대다.

false: condition-only를 false로 구분하는 등 양쪽 의미가 일치한다. RANGE·SEPARATED·NEAR·overlap 자체는 양성 근거가 아니다. 입력에 없는 화면 문구나 사용자 오독을 창작하지 않는다.

description이 다른 band를 설명할 가능성이 남으면 Q2 양성 gold를 강제하지 않는다. 동일 rule이라는 필수 대응 관계가 빠졌다면 Q3 검증 대상이다. state 자체 enum/boolean 모순과 기존 deterministic issue는 local owner가 처리한다.

**Q3 — review_evidence_insufficient**

> Q1/Q2 중 적어도 하나의 제한된 의미 판단에 필요한 의도·용어·지시 대상이 제공되지 않아, 그 빠진 의미를 창작해야만 판단할 수 있는가.

true: 필수 정의 또는 같은 rule과의 대응 관계가 없고, 서로 다른 보충에 따라 결론이 달라진다.

false: 의미가 제공되어 일치/불일치를 검토할 수 있다. 명백한 모순, 일반적인 정도의 망설임, 미래 불명, News/종목명/가격 상세의 의도적 제외는 부족이 아니다.

Q3가 참이면 전체 review를 유보한다. Q1만 부분 채택하는 확장은 넣지 않는다. 반대로 clear conflict를 근거 부족으로 처리하지 않도록 false-abstain trap으로 검증한다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: Q1/Q3에는 제한적 분리, Q2에는 무효 gold와 범위 불일치 → 세 질문 무조건 유지도 일괄 삭제도 부적절 → 삭제 / 현상 유지 / 제한 교정 → **교정된 세 질문을 새 version으로 검증** → 기존 state 안에서 측정 가능한 보조 가치가 있음 → V2에서 Q1/Q2 단독 양성과 정확한 reason을 요구한다. Q2가 실패하면 삼문항 정책 전체를 FAIL로 하고, 몰래 제외하여 PASS로 만들지 않는다. 삭제하려면 새 question/protocol로 검증한다.

후속 source 감사에서 Q2 양성이 고정 mapping만으로 완전히 해결됨이 확인되면 중복 질문을 유지할 이유가 없다. 그때는 V2 호출 전에 설계를 version 변경한다. 읽은 projector에는 자연어 description과 role의 의미 비교가 없지만, synthetic 분리만으로 production의 추가 가치가 증명되지는 않는다.

## 8. V1의 공식 지위

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: V1을 보고 architecture와 gold를 교정 → 같은 records로 최적화하여 독립 합격을 주장할 수 없음 → V1 재채점으로 승인 / 진단용 보존 → **DIAGNOSTIC / CALIBRATION CANARY로 제한** → 설계에 학습한 증거와 acceptance 증거를 분리 → 새 V2 검증.

CALIBRATION은 설계 참고 용도이며 확률 교정 완료를 뜻하지 않는다. 기존 FAIL, threshold 후보, 52 check, binding의 `alias_used=false`까지 역사적 기록으로 보존하고 이 문서에 오류를 별기한다.

| 구분 | 이번에 가능한 일 | 이번에 하지 않는 일 |
|---|---|---|
| architectural inference from V1 | 공통 L/H 문제, 질문 경계, gold 결함 논증 | B의 실효성 합격 인정 |
| candidate threshold range | §11의 거친 후보 집합 설계 | V1에 모두 맞는 값을 final 선언 |
| final frozen threshold | 선택 방법과 freeze 순서 결정 | 현재 값을 Trial에 bind |
| independent V2 validation | 새 fixture·partition·gate 설계 | V1의 기대만 고쳐 V2로 명명 |

## 9. model binding 재설계

V1 selector는 `jev-`로 시작하며 `latest`가 없는 이름을 versioned 후보로 취급한다. 그 결과 `jev-preview`를 선택하고 `alias_used=false`로 기록했다. **preview channel을 immutable version으로 취급할 근거가 없으므로 이 분류를 폐기한다.**

| identity | 의미와 채택 규칙 |
|---|---|
| request model identity | API에 보낼 exact name. discovery의 requestable 목록에 있어야 함 |
| request channel class | IMMUTABLE_VERSION_VERIFIED / STABLE_ALIAS / PREVIEW_ALIAS / UNKNOWN 명시. 문자열 제외 규칙만으로 version 인정 금지 |
| returned concrete identity | response.model의 exact concrete identifier. 요청명으로 보충 금지 |
| expected returned identity | 승인된 canary에서 관측·고정한 cohort binding. trial의 모든 응답이 일치해야 함 |
| verification evidence | discovery snapshot, 분류 근거, request/returned, protocol/question/policy/state/adapter identity와 시각 |

선택 순서는 다음과 같다.

1. account에 explicit immutable version ID가 **requestable로 노출**되고 불변성 근거도 확인되면 우선한다. version 모양의 정규식만으로 입증하지 않는다.
2. 없으면 승인된 production/stable alias를 요청한다.
3. preview는 기본 prospective trial model로 사용하지 않는다. preview만 가능해도 자동 fallback하지 않고 binding BLOCKED다.
4. unknown/alias response를 concrete로 받지 않는다. 누락·unknown·request alias만 반환되면 unverified이며 disposition을 만들지 않는다.

저장된 계정 목록에는 `jev-latest`, `jev-preview`만 있고 `jev-1.13.0`은 requestable로 노출되지 않았다. 따라서 **request 후보=`jev-latest`, returned concrete는 별도 고정** 구조가 현실적이다. latest의 production 용도 적합성은 binding 시 확인할 사항이며 이름만으로 SLA·불변성을 보증하지 않는다.

`request=jev-latest / response=jev-1.13.0`은 **허용할 구조의 예**다. V1에서 관측한 조합은 preview→1.13.0뿐이다. latest도 같은 model을 반환한다고 가정하거나 preview의 분포·threshold를 latest에 승계하지 않는다.

V2의 첫 승인된 응답에서 결과의 좋고 나쁨과 무관하게 concrete identity를 묶고, 이후 변경은 전체 V2 identity gate FAIL이다. 첫 응답부터 unknown이면 실패한다. preview에서 latest로 request channel을 바꾸는 일도 새 binding이다.

trial 중 identity가 달라지면 그 응답을 원 cohort의 VALID에 넣지 않고 모집·정상 판단을 멈춘다. 새 protocol/cohort와 canary binding이 필요하며 **새 model의 cohort를 자동 시작하지 않는다**. 기존 observation을 다시 호출·재채점·덮어쓰지 않는다. request가 같아도 returned가 다르면 분리한다. concrete 이름이 같다는 사실만으로 내부 weights 불변까지 입증했다고 주장하지 않는다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: preview 오분류, concrete는 응답에서 관측 → request 가능성과 재현성 혼동 → concrete 추측 요청 / preview 유지 / stable alias+concrete binding → **마지막 채택** → 이용 가능한 request와 cohort 재현성을 별도로 감사 가능 → 후속 승인된 V2에서 latest 응답 전체의 identity를 확인한다. 이번 discovery 추가 호출은 없다.

## 10. Canary V2의 새 synthetic validation 설계

### 10.1 구성과 독립성

**24개 신규 fixture**를 선택용 `v2-s01..s12`와 확인용 `v2-v01..v12`로 나눈다. 각 partition은 음성 대조 4, Q1 단독 충돌 2, Q2 단독 충돌 2, 의미 부족 2, 복합 충돌 1, soft ambiguity 1이다. 모든 fixture는 세 번 반복한다.

V1 state의 기대값만 고쳐 재사용하지 않는다. V1은 새 architecture의 동기이며, V2의 payload·question 의미·gold·partition·선택 규칙을 **V2 응답 이전**에 고정한다. 선택용 결과로 하나를 선택한 뒤 확인용은 그 하나만 acceptance 판정한다. 확인용 결과로 다른 후보를 골라내는 경로는 없다. 이는 새 synthetic 자료의 내부 역할 분리이며, 접근 금지된 기존 Holdout 자료와 아무 관련이 없다.

24개는 독립적인 시장 표본이 아니다. 의도적으로 만든 경계 사례이므로 실제 경고율·수익·정확도의 모집단 추정으로 해석하지 않는다. 확인용도 같은 경계 가족을 다른 문구·조건 조합으로 점검하므로 완전히 다른 분포로 일반화한 검증은 아니다. 응답을 보고 작성하거나 선택하지 않았다는 독립성을 확보한다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: V1은 이미 설계에 사용됐고 gold 오류가 있음 → 재사용 합격은 과적합 → 기대값 수정 재사용 / 새로운 단일 선택 set / 새 선택·확인 분리 → **마지막 채택** → 선택의 유연성을 사전 제한하고 별도 확인에 실패할 수 있게 함 → 아래 고정 fixture와 §11–12를 적용한다.

### 10.2 state 완전 정의 방식

아래 표의 `S(description, C, E, horizon)`는 설명용 축약이며 임의 보충 가능한 placeholder가 아니다. 다음 고정 공통부와 각 행의 정확한 문자열·조건 집합·entry 집합을 결합하면 해당 외부 state가 완전히 정의된다. `purpose`, gold, split, fixture_id는 provider state에 넣지 않는 local metadata다.

```text
context = {market: "SYNTHETIC", as_of_date: "2026-10-06", horizon_intent: horizon}
strategy_context = {strategy_key: "SYNTHETIC_CANARY_V2", strategy_description: description}
condition_context = C의 모든 항목, 표 순서 유지
entry_context = E
baseline = {action: "ENTRY_CANDIDATE", candidate_state: "READY"}
```

condition의 모든 항목은 `status="PASS"`다. 아래 tuple은 `(metric_key, current_value, required_value)`이며 값은 모두 합성 문자열이다. semantic_label은 그 아래 고정 mapping을 따른다. 숫자 PASS/FAIL을 재계산하게 만들지 않는다.

| C | condition tuples |
|---|---|
| R | `(ma20_slope, rising, rising)`, `(ma20_vs_ma60, above, above)` |
| F | `(ma20_slope, falling, falling)`, `(ma20_vs_ma60, below, below)` |
| SP | `(relative_strength_sector, positive, positive)`, `(ma20_slope, rising, rising)` |
| SN | `(relative_strength_sector, negative, negative)`, `(ma20_slope, falling, falling)` |
| L | `(ma60_vs_ma120, above, above)`, `(relative_strength_market, positive, positive)` |
| D | `(ma60_vs_ma120, below, below)`, `(relative_strength_market, negative, negative)` |
| M | `(ma20_slope, slightly rising, nondecreasing)`, `(ma20_vs_ma60, above, above)` |

| metric_key | 고정 semantic_label |
|---|---|
| ma20_slope | `20-day moving-average slope condition` |
| ma20_vs_ma60 | `20-day versus 60-day moving-average relation` |
| ma60_vs_ma120 | `60-day versus 120-day moving-average relation` |
| relative_strength_sector | `relative strength versus the sector` |
| relative_strength_market | `relative strength versus the broad market` |

E의 공통부는 `price_rule.kind="RANGE"`, `price_rule.status="MET"`, `action.status="ENTRY_CANDIDATE"`다. 나머지는 다음과 같다.

| E | price_rule.semantic_role | executable_entry_range | price_consistency.classification | semantic_overlap |
|---|---|---:|---|---:|
| X | EXECUTABLE_ENTRY_RANGE | true | ALIGNED | false |
| C | STRATEGY_CONDITION_THRESHOLD | false | SEPARATED | false |

확인 band와 실행 영역이 가깝다는 문구 자체를 실행 허가로 해석하지 않는다. 별도의 가격 geometry나 내부 enum 모순을 일부러 만들어 model에 판정시키지 않는다.

후속 offline preflight에서 synthetic canonical wrapper의 Risk READY/no warning, complete conditions, local `price_consistency.status=OK`를 구성해 projector 도달성을 확인해야 한다. 이 audit context는 외부 state에 추가하지 않는다. 알려진 mapping, 8 KiB/조건 12개/description 360자 제한을 지켜야 한다. 의미 부족 사례도 빈 필수 field, null, UNSPECIFIED를 이용한 local gate 우회가 아니다. 실제 production capture와 같은 값 표현인지 여부는 별도의 projector 적합성 한계로 기록한다. 지금은 wrapper나 JSON artifact를 생성하지 않는다.

### 10.3 선택용 12 fixture

T/F는 semantic proposition의 긍정/부정이며 특정 확률 band가 아니다. `*`는 의미 부족으로 정답을 강제하지 않는 질문이다. hard는 모든 반복에서 해당 명제 방향의 threshold 판정과 disposition을 요구한다. soft는 한 개 band를 hard truth로 만들지 않는다.

| fixture_id | purpose | state = S(description; C; E; horizon) | expected semantic proposition (Q1,Q2,Q3) / disposition | hard/soft | why this is valid gold |
|---|---|---|---|---|---|
| v2-s01 | clear normal | `This strategy accepts a rising 20-day average above the 60-day average. The single rule in entry_context is an executable entry range.`; R; X; SHORT | F,F,F / PASS_THROUGH | hard | 두 조건의 방향과 해당 rule의 실행 의미가 모두 일치 |
| v2-s02 | future uncertainty negative control | `Falling averages with the 20-day below the 60-day are intentional here. The entry_context rule is executable. Later price performance is outside this review.`; F; X; SHORT | F,F,F / PASS_THROUGH | hard | 현재 의미는 완전하며 미래 결과 부재는 무관 |
| v2-s03 | false-positive trap: 확인 band | `Rising averages above the slower average fit this setup. The only rule in entry_context is a confirmation band, never an executable range. Candidate status does not change that role.`; R; C; SHORT | F,F,F / PASS_THROUGH | hard | V1 오류와 같은 개념 경계를 새 state에서 명시. 비실행과 후보 상태는 양립 |
| v2-s04 | false-abstain trap: 불필요한 정보 제외 | `Positive sector-relative strength with a rising average is the intended context. The entry_context rule is executable. Company identity, news and target prices play no role in these meaning comparisons.`; SP; X; SHORT | F,F,F / PASS_THROUGH | hard | 검토할 조건과 rule 의미가 모두 있고 금지·불필요 정보만 빠짐 |
| v2-s05 | clear strategy conflict: 방향 | `Only falling averages with the 20-day below the 60-day fit this strategy; the opposite rising arrangement is excluded. The entry_context rule is executable.`; R; X; SHORT | T,F,F / REVIEW_REQUIRED(Q1) | hard | 설명이 배제한 조합을 conditions가 명시. 산술 없이 반대 관계 확인 |
| v2-s06 | clear strategy conflict: 상대강도 | `Sector underperformance with a falling average is required; sector outperformance with a rising average contradicts that intent. The entry_context rule is executable.`; SP; X; SHORT | T,F,F / REVIEW_REQUIRED(Q1) | hard | positive/rising과 명시적 underperformance/falling 의도가 반대 |
| v2-s07 | clear entry conflict: 확인→실행 혼동 | `Rising averages above the slower average fit the strategy. The sole rule represented in entry_context is confirmation-only and must not denote an executable entry range.`; R; X; SHORT | F,T,F / REVIEW_REQUIRED(Q2) | hard | 같은 rule이라는 지시가 명확하고 설명은 확인 전용, state는 실행 가능 |
| v2-s08 | clear entry conflict: 실행→확인 혼동 | `Falling averages with the 20-day below the 60-day are allowed. The single entry_context rule specifically denotes an executable range, not a strategy confirmation threshold.`; F; C; SHORT | F,T,F / REVIEW_REQUIRED(Q2) | hard | 같은 rule의 실행 의미를 설명하지만 state는 확인 전용. 조건은 일치 |
| v2-s09 | clear evidence insufficiency: 전략 용어 | `Conditions are interpreted according to context class K. Only that class defines the intended directional combination. The entry_context rule is an executable range.`; R; X; SHORT | *,*,T / ABSTAIN | hard | K의 정의가 없어 Q1 결론은 보충한 의미에 따라 달라짐. 필수 field는 존재 |
| v2-s10 | clear evidence insufficiency: rule 지시 대상 | `Rising averages above the slower average fit this setup. Band Alpha is confirmation-only and band Beta is executable. The rule in entry_context represents the selected band.`; R; X; SHORT | *,*,T / ABSTAIN | hard | selected가 Alpha인지 Beta인지 빠져 Q2 판단에 필요한 대응 관계가 없음 |
| v2-s11 | compound conflict / false-abstain trap | `Only falling averages with the 20-day below the 60-day are compatible. The sole rule in entry_context is confirmation-only and is never executable.`; R; X; SHORT | T,T,F / REVIEW_REQUIRED(Q1,Q2) | hard | 두 독립 불일치의 양쪽 정보가 완전. 모순을 부족으로 숨길 수 없음 |
| v2-s12 | semantic ambiguity: 정도 | `This strategy prefers vigorous upward movement but can accept modest progress. A slightly rising average is a borderline fit. The entry_context rule is executable.`; M; X; SHORT | Q1 정도 모호, Q2 일치, Q3 부족 단정 불가 / 단일 disposition 강제 안 함 | soft | 명시된 정도의 경계여서 material conflict의 강도를 하나의 band로 정하기 어려움 |

### 10.4 확인용 12 fixture

확인용은 선택 결과를 잠근 뒤 호출·열람한다. 아래 정의는 호출 전에 함께 고정하며, 선택용 결과를 보고 문구를 고치지 않는다.

| fixture_id | purpose | state = S(description; C; E; horizon) | expected semantic proposition (Q1,Q2,Q3) / disposition | hard/soft | why this is valid gold |
|---|---|---|---|---|---|
| v2-v01 | clear normal: 다른 조건·horizon | `A 60-day average above its 120-day counterpart and positive market-relative strength express the intended structure. The rule in entry_context defines executable entries.`; L; X; MEDIUM | F,F,F / PASS_THROUGH | hard | 느린 기준과 시장 상대강도, 실행 의미가 모두 일치 |
| v2-v02 | future uncertainty negative control | `The intended context is a 60-day average below the 120-day average with negative market-relative strength. The entry_context rule is executable. Nothing here asserts what prices will do next.`; D; X; MEDIUM | F,F,F / PASS_THROUGH | hard | 미래 예측 없이도 현재 의도와 조건 비교는 완결 |
| v2-v03 | false-positive trap: 근접 문구 | `The 60-day average above the 120-day and market outperformance fit this setup. The sole entry_context rule is a confirmation band. Its proximity to an execution area does not make it executable.`; L; C; MEDIUM | F,F,F / PASS_THROUGH | hard | 근접 문구와 role은 별개이며 설명과 condition-only false가 일치 |
| v2-v04 | false-abstain trap: 비관적 맥락도 완결 | `Negative sector-relative strength together with a falling average is deliberately accepted by this strategy. The sole rule in entry_context is an executable range; no external event narrative is needed.`; SN; X; MEDIUM | F,F,F / PASS_THROUGH | hard | 조건의 매력도를 묻지 않음. 하락 맥락도 명시된 의도와 일치하면 부족·충돌 아님 |
| v2-v05 | clear strategy conflict: 느린 기준 | `The strategy excludes a 60-day average above the 120-day accompanied by market outperformance; it requires the reverse arrangement. The entry_context rule defines executable entries.`; L; X; MEDIUM | T,F,F / REVIEW_REQUIRED(Q1) | hard | 실제 제공된 조합을 description이 직접 배제 |
| v2-v06 | clear strategy conflict: 반대 방향 | `Sector leadership and a rising average are essential. Sector underperformance combined with a falling average is incompatible. The entry_context rule is executable.`; SN; X; MEDIUM | T,F,F / REVIEW_REQUIRED(Q1) | hard | SN의 의미와 설명된 필수 방향이 반대 |
| v2-v07 | clear entry conflict: 다른 문구 | `A 60-day average above the 120-day and market outperformance match the intent. The only rule supplied in entry_context marks confirmation, and granting execution meaning to that rule contradicts its purpose.`; L; X; MEDIUM | F,T,F / REVIEW_REQUIRED(Q2) | hard | same rule의 확인 목적과 실행 annotation이 충돌. Q1은 일치 |
| v2-v08 | clear entry conflict: 역방향 표현 | `Sector underperformance and a falling average are the intended context. For this setup, the entry_context rule is the executable entry range itself, rather than a non-executable confirmation marker.`; SN; C; MEDIUM | F,T,F / REVIEW_REQUIRED(Q2) | hard | 설명은 실행 범위 자체, state는 비실행 확인. 기준값 계산 불필요 |
| v2-v09 | clear evidence insufficiency: 참조 정의 | `The relationship of the two long averages is evaluated using profile P, which determines whether the observed arrangement matches the strategy. The entry_context rule is executable.`; L; X; MEDIUM | *,*,T / ABSTAIN | hard | P를 긍정/반대 방향 어느 쪽으로 정의하느냐에 따라 Q1 결론이 달라짐 |
| v2-v10 | clear evidence insufficiency: 연결 부재 | `The supplied negative sector-relative strength and falling average are intentional. One strategy band is executable and the other only confirms conditions. The entry_context rule names the chosen band.`; SN; C; MEDIUM | *,*,T / ABSTAIN | hard | chosen band가 어느 것인지 설명과 entry 사이 연결이 빠짐 |
| v2-v11 | compound conflict / false-abstain trap | `Only sector leadership with a rising average fits this strategy. The single rule in entry_context is an executable entry range and must not be classified as a confirmation-only threshold.`; SN; C; MEDIUM | T,T,F / REVIEW_REQUIRED(Q1,Q2) | hard | 조건 방향 및 rule 의미가 각각 반대이며 양쪽 근거는 모두 존재 |
| v2-v12 | semantic ambiguity: 문구 강도 | `The intended structure favors the 60-day above the 120-day with market outperformance. The entry_context band is normally confirmation-only, though its practical entry meaning can vary with context.`; L; C; MEDIUM | Q1 일치, Q2/Q3 해석 여지 / 단일 disposition 강제 안 함 | soft | normally/can vary의 한정 때문에 같은 명확 band를 hard truth로 요구할 수 없음 |

soft 사례의 gold는 “강제할 단일 정답이 없다”는 사전 의미 분류다. 결과가 마음에 들지 않는 hard 사례를 나중에 soft로 강등하지 않는다. soft도 반복 crossing과 burden 계산에는 포함한다.

### 10.5 실행 전 완결성 조건과 호출 계획

후속 구현 단계에서 응답을 보기 전에 다음을 문서/새 artifact에 묶어야 한다.

- 정확한 wire questions: §7 문안과 참조 범위, type=noul, true/false criteria. 언어·문구를 하나로 고정하고 trial에서도 같은 bytes를 사용한다.
- 위 S를 확장한 24개 payload의 canonical bytes/hash, gold 근거, hard/soft, partition, 호출 순서.
- §11 후보 집합·선택 순서, §12 모든 gate, expected count 및 비용/시간 cap.
- 실제 projector의 synthetic wrapper 통과 및 local owner와의 중복 검사. 아직 runtime을 통과했다고 주장하지 않는다.
- gold를 state/proposition으로 다시 감사. 사전 모순이 발견되면 호출 전에 문서를 version 변경하고 다시 고정한다. 실행 중 gold를 수정해 합격시키지 않는다.

계획은 각 partition에서 1회차 `01→12`, 2회차 `12→01`, 3회차 `02→12→01`의 순서로 순차 호출한다. seed나 결과에 따라 순서를 바꾸지 않는다. 같은 fixture의 external state와 questions는 세 번 모두 동일하다. 한 호출에 세 질문을 함께 보낸다.

최대 System One **72회**, discovery **1회**, 전체 **73회**, retry **0회**, 동시성 **1**, 호출별 deadline **10초**, 합성 canary budget **USD 0.25**를 후속 V2의 상한 설계로 둔다. 이는 이번 실행 허가가 아니다. 선택용 FAIL이면 확인용 36회를 호출하지 않는다. 실패한 호출도 attempt cap에 포함한다. 부분 응답에서 token/cost를 알 수 없으면 0으로 간주하지 않고 예약액을 보존한다.

실제 호출 전 계정 가격·최대 응답 비용을 기준으로 사전 예약 가능한 비용 경계를 마련해야 한다. 현재 public-price estimate만으로 예산 준수를 보장하지 않는다. cap 안에서 비용 노출을 예약할 수 없으면 호출 전 BLOCKED다. 예산·deadline·후보·gold를 실행 도중 늘리지 않는다.

## 11. Threshold V2 선택 방법

### 11.1 후보와 final을 분리한다

V1 관찰은 0 근처를 요구하지 않는 architecture와 질문별 slot을 제안할 근거다. 어느 threshold가 최적인지는 제공하지 않는다. 특히 Q2가 교정되고 request channel도 달라지므로 V1 수치로 새 질문의 양성 감도를 추정하지 않는다.

다음은 **후속 V2 protocol에 넣을 candidate grid 설계**이며 final threshold가 아니다.

| slot | candidate set | 설계 이유 |
|---|---|---|
| T_strategy | {.50, .65, .80} | 약한 다수 신호부터 강한 신호까지 거친 간격으로 비교 |
| T_entry | {.50, .65, .80} | 같은 초기 탐색 범위지만 Q1과 독립 slot. 같아야 한다는 제약 없음 |
| T_evidence | {.60, .75, .90} | 의미 부족에 의한 전체 유보를 별도 강도로 검증 |

Cartesian product는 27개다. 각 값은 설계자가 정한 탐색 후보이지 industry standard·교정 확률·V1 최적값이 아니다. V1을 새 grid로 sweep하여 정답에 맞는 조합을 찾지 않았다. 간격을 좁혀 .57/.59 등의 관측값을 끼워 맞추지 않는다.

이 문서가 고정하는 것은 **방법과 위 후보군의 설계안**이다. machine-readable V2 freeze는 별도 후속 작업이며, 모든 후보·gate·문구는 첫 V2 호출 전에 함께 동결해야 한다. final 값은 현재 없음이다.

### 11.2 선택과 독립 확인 순서

1. V2 전체 24개 state/gold와 질문·model 규칙·27개 후보·gate·tie-break를 응답 전에 고정한다.
2. 선택용 12개를 3회씩 실행한다. 구조·identity·complete-count gate를 먼저 확인한다.
3. 선택용 결과에 각 후보를 순수 산술로 적용한다. §12 gate를 전부 통과한 후보만 eligible이다.
4. eligible이 없으면 `CANARY_V2_FAIL`; 확인용 미실행, trial BLOCKED. 새 값을 그 자리에서 추가하지 않는다.
5. 여러 개면 아래 우선순위로 **하나만** 선택하고 그 tuple과 선택 결과를 잠근다. 이 시점 이후 확인용 결과를 보며 바꾸지 않는다.
6. 확인용 12개를 같은 binding·questions·선택된 tuple로 3회씩 검증한다. 다른 tuple은 확인용 acceptance 대안으로 계산하지 않는다.
7. 확인용 gate까지 모두 PASS여야 전체 `CANARY_V2_PASS`. 그 뒤 별도 Trial V2 준비에서 이 tuple을 final로 bind할 수 있다. 이번에는 1–7 중 어떤 provider 실행도 하지 않았다.

tie-break는 사전 고정한 다음 사전식 순서다.

1. 선택용 soft fixture의 `REVIEW_REQUIRED + ABSTAIN` 건수가 적은 후보.
2. 동률이면 같은 soft fixture의 ABSTAIN 건수가 적은 후보.
3. 여전히 같으면 `T_strategy` 내림차순, `T_entry` 내림차순, `T_evidence` 내림차순으로 처음인 tuple.

모든 hard gate를 먼저 통과해야 하므로 부담을 줄이려고 clear conflict나 부족 사례를 놓치는 후보를 선택할 수 없다. 마지막 수치 순서는 동률 해소 규칙일 뿐 우수성 증거가 아니다. margin 최적화, 사후 가중치, 확인용 결과에 의한 재순위는 하지 않는다.

확인용 실패 후 선택용의 차순위 후보를 확인용에 적용해 구제하지 않는다. threshold·question·state·gold·후보·선택 규칙 변경이 필요하면 새 Canary protocol version과 새 응답 미관측 확인 사례가 필요하다. 실패한 V2도 diagnostic으로 보존한다. 기존 observation을 새 정책으로 덮어쓰지 않는다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: V1을 이미 보고 설계를 바꿈 → threshold 최적화와 독립 검증 혼동 가능 → 단일 set에서 최적값 보고 / 사전 후보만으로 선택 / 사전 후보 선택 후 별도 확인 → **마지막 채택** → 방법을 사전에 제한해도 남는 선택 편향을 확인 단계에서 분리 → 한 tuple만 독립 확인하고 실패를 허용한다.

## 12. PASS / FAIL gate와 repetition metric

### 12.1 분모와 계산

각 partition은 12 fixture × 3회 = 36 planned responses, hard는 11 fixture × 3회 = 33이다. normal/negative control은 4 fixture × 3회 = 12, 충분한 근거의 conflict는 5 × 3 = 15, insufficient는 2 × 3 = 6이다. 나머지 soft는 3 responses다. 반복을 서로 독립적인 의미 사례로 계산하지 않고 fixture 수와 response 수를 함께 보고한다.

질문별 binary decision은 `g1=[p1>=T_strategy]`, `g2=[p2>=T_entry]`, `g3=[p3>=T_evidence]`다. Q3 우선순위와 별개로 hard의 알려진 proposition은 각 g와 직접 비교한다. `*,*,T`에서는 g1/g2를 오답 분모에서 빼고 g3만 비교한다. 각 partition의 hard proposition check는 `(9×3 + 2×1)×3 = 87`이다. 이는 독립적인 표본 87개가 아니다.

| metric | 정의 |
|---|---|
| clear gold error | hard에서 알려진 명제의 g가 gold와 다르거나, disposition/reason set이 기대와 다른 경우. 명제 check /87, disposition /33을 각각 보고 |
| false escalation | hard 음성 12 responses 중 REVIEW_REQUIRED 건수 /12 |
| false abstention | 충분한 의미의 hard 27 responses 중 ABSTAIN 건수 /27. 음성 12와 conflict 15를 별도 표기 |
| missed conflict | hard conflict 15 responses 중 정확한 REVIEW_REQUIRED reason set이 아닌 건수 /15. ABSTAIN도 누락에 포함 |
| missed insufficiency | hard insufficient 6 responses 중 ABSTAIN이 아닌 건수 /6 |
| wrong reason | hard 단독 conflict에 다른 질문의 reason이 추가되거나 compound에서 reason이 빠진 건수. disposition만 맞아도 오류 |
| review burden | REVIEW_REQUIRED / VALID, 전체 partition과 category별 병기 |
| abstain burden | ABSTAIN / VALID, 전체 partition과 category별 병기 |
| intervention burden | (REVIEW_REQUIRED + ABSTAIN) / VALID |
| D-crossing | 같은 fixture의 3회 disposition 집합 크기가 1보다 큰 fixture 수 /12 |
| E-crossing | 같은 fixture에서 REVIEW_REQUIRED 여부가 바뀐 fixture 수 /12 |
| A-crossing | 같은 fixture에서 ABSTAIN 여부가 바뀐 fixture 수 /12 |
| reason crossing | REVIEW_REQUIRED 여부가 일정해도 그 reason 집합이 바뀐 fixture 수 /12 |
| question crossing | 각 g1/g2/g3가 반복 사이 달라진 fixture 수 /12, 질문별 보고 |

E/A-crossing은 D-crossing의 세분 진단이며 서로 더해 독립 위험처럼 계산하지 않는다. Q3가 계속 높아 ABSTAIN이고 g1/g2만 바뀌는 경우는 question crossing에 기록하지만 제품 escalation crossing으로 계산하지 않는다. soft의 raw g 변화도 진단에 남긴다. max/min/절대차는 보조 지표이며 큰 차이가 없어도 경계를 넘으면 실패할 수 있다.

분모 0은 0%가 아니라 N/A다. 오류·지연·미호출 때문에 응답이 줄어들면 남은 valid만으로 합격하지 않고 완결성 gate에서 실패한다. 원시 records, 전체 planned/attempted/completed/valid 및 identity별 개수를 함께 남긴다.

### 12.2 선택용과 확인용에 각각 적용할 acceptance gate

| gate | PASS 조건 | 실패 처리 |
|---|---|---|
| 사전 설계 완결성 | payload/gold/questions/grid/선택 규칙/caps를 응답 전에 고정, local preflight 및 의미 감사 완료 | 호출 전 BLOCKED |
| provider/response | planned 36건 모두 on-time VALID, 정확한 3 Noul과 유효 usage/model, 누락·error·late·interrupt 0 | 해당 partition FAIL |
| identity | request channel 고정, 확인된 concrete가 최초 binding과 전건 일치 | 전체 V2 FAIL, 변경 model 혼합 금지 |
| 명제 및 행동 | hard proposition mismatch 0/87, hard disposition/reason error 0/33 | 후보 ineligible 또는 확인 단계 FAIL |
| false intervention | false escalation 0/12, false abstention 0/27 | 같은 처리 |
| 필요한 신호 | missed conflict 0/15, missed insufficiency 0/6, wrong reason 0 | 같은 처리 |
| 반복 제품 경계 | D/E/A/reason crossing 각각 0/12, soft도 포함 | 같은 처리 |
| hard 질문 경계 | 정답이 고정된 hard proposition의 question crossing 0 | 같은 처리 |
| burden | 전체 36 VALID에서 review ≤18/36(50%), abstain ≤9/36(25%), intervention ≤24/36(66.67%) | 같은 처리 |
| 비용·실행 상한 | 전체 73 attempt 이내, System One 72 이내, discovery 1 이내, retry 0, 예약 포함 budget ≤USD 0.25 | 실행 중단, FAIL 또는 미실행 BLOCKED 구분 |

burden 상한은 fixture 구성에서 도출한 acceptance 한도다. hard 기대가 맞으면 review 15/33, abstain 6/33이고, soft 세 응답이 어디로 가는지에 따라 전체 부담이 달라진다. 따라서 이 상한은 감도·음성 gate를 대체하는 점수가 아니며, 실종목의 허용 경고율 50%를 선언하는 것도 아니다. 미래 trial의 경고율·abstain·coverage 한도는 별도 사전 동결 사항이다.

명확한 소수 경계 사례에서 0 error를 요구하는 이유는 통계적 완벽성을 주장하기 위해서가 아니다. normal을 계속 막거나 명백한 충돌을 놓치는 정책을 다음 단계로 보내지 않기 위해서다. 0/12 crossing도 장기 무변동의 보증은 아니다. 특히 전부 ABSTAIN인 정책은 안정성만 통과하더라도 negative 및 감도 gate에서 반드시 탈락한다.

최종 `CANARY_V2_PASS`는 선택용에서 eligible 후보가 있고, 잠근 단일 후보가 확인용에서도 모든 gate를 통과하며, 전체 운영·identity·budget gate가 충족된 경우에만 가능하다. 어떤 후보도 기준을 만족하지 않거나 확인용이 실패하면 `CANARY_V2_FAIL → trial blocked`다. 미실행·preflight 실패는 PASS나 실행된 FAIL로 위장하지 않는다.

### 12.3 근처 구간과 실패 후 처리

근처 구간의 별도 ABSTAIN 규칙은 채택하지 않는다. 대신 각 fixture의 반복 `min(pq), max(pq)`와 threshold의 상대 위치를 저장하여 실제 crossing을 식별한다. 근처 폭을 결과에 맞춰 추가하지 않는다. 반복 중 하나만 채택하거나 평균 p로 flip을 지우지 않는다.

V2는 미리 정한 세 번을 수행한다. 실패가 난 fixture만 더 호출하여 다수결로 바꾸지 않는다. provider 오류나 identity 변경으로 중단한 경우에도 이미 사용한 attempt와 비용은 남기며 예산을 초기화하지 않는다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: V1의 작은 변화에도 band flip이 있었고 전건 유보는 crossing이 0 → 확률차 또는 안정성 하나만으로 품질 판정 불가 → 차이 크기 gate / 평균값 / 제품 경계+의미 gate → **마지막 채택** → 사용자가 받는 판단 반전과 필요한 신호를 동시에 측정 → 위 gate를 선택·확인 partition에 동일 적용한다.

## 13. 제품 적용과 Trial V2 freeze로 넘어갈 조건

사용자에게 보여줄 기본 의미는 유지한다. PASS_THROUGH는 추가 확인 신호 없음, REVIEW_REQUIRED는 해당 의미 충돌 재확인, ABSTAIN은 해석 근거 부족이다. 원시 확률·AI 종목 점수·매수 확률은 기본 사용자 판단 흐름에 추가하지 않는다. 이 문서에서는 frontend를 바꾸지 않는다.

후속 작업의 순서는 다음과 같다. 이번 작업에서 실행하지 않는다.

1. 새 question/disposition/model binding 및 V2 harness를 별도 승인된 구현 작업에서 반영한다. 현재 threshold_low/high 두 slot에 세 threshold를 억지로 넣지 않는다.
2. Core, Monitor의 stored-answer 재검증, Evaluation의 cohort identity가 같은 새 policy version과 세 threshold를 사용하도록 교정한다. 기존 V1 답변·disposition·artifact는 보존하고 version별 해석을 유지한다.
3. fake-only로 경계 equality, 잘못된 확률, missing/unknown model, channel 분류, ERROR/LATE/SKIPPED의 null disposition 및 baseline 유지, Q3 우선순위를 검증한다. 이는 후속 구현 의무이며 이번 테스트 실행이 아니다.
4. 위 24 fixture와 정확한 wire question 문구, candidate grid/선택 규칙, caps를 새 Canary V2 protocol로 호출 전에 동결한다. 최신 계정 정책·비용·requestable model 근거 및 synthetic 전송 승인 범위를 확인한다.
5. 별도의 실행 권한 아래 Canary V2를 수행하고 선택용→단일 후보 잠금→확인용 순서를 지킨다. V2가 FAIL이면 trial은 계속 BLOCKED다.
6. V2 PASS 뒤 model request/returned, state/projector/questions/policy/adapter, 선택된 threshold tuple 및 protocol identity를 일치시킨다. account retention/ZDR/billing, 실제 minimized StockScope 전송 승인, 예산 예약과 operational gates를 완료한다. synthetic 승인만으로 실데이터 승인을 승계하지 않는다.
7. Trial V2의 recruitment·기간·규모·maturity·coverage·abstain/review·오류/지연·비용·concentration·evaluation 수치를 prospective 결과를 보기 전에 별도 동결한다. Legacy V1 수치를 자동 복사하지 않는다.
8. 이 조건을 충족해야 Trial V2 freeze 검토로 진행할 수 있다. **Canary PASS 자체는 trial activation이나 adoption 승인이 아니다.** prospective activation은 별도 명시 단계이며 기존 observation은 새 모집군으로 재사용하지 않는다.

현재 코드의 `typesafe_projection.py`는 low/high로 stored disposition을 다시 계산하고 `typesafe_evaluation.py`의 identity에도 low/high가 들어간다. 따라서 이 설계는 값만 교체하면 끝나는 변경이 아니다. 그 구현 의존성을 숨긴 채 Trial freeze를 진행해서는 안 된다. 다만 migration의 구체 SQL이나 새 UI 설계로 이번 범위를 확장하지 않는다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: 현재 runtime은 옛 policy를 사용하며 account policy도 미검증 → 문서 완료를 trial 준비 완료로 오인할 수 있음 → 즉시 freeze / 구현·검증·binding 후 freeze → **후자** → 사용자 후보가 재현 가능한 동일 정책으로 해석돼야 함 → 위 조건 확인 후에만 별도 Trial freeze 작업을 진행한다.

## 14. 완료 상태와 작업 경계

| 항목 | 최종 상태 |
|---|---|
| TYPE-JEV CANARY V1 | **EXECUTED / DIAGNOSTIC FAIL** |
| PROVIDER CONNECTION | **PASS — V1 관측 범위** |
| MODEL RESPONSE CONTRACT | **PASS — V1 관측 범위** |
| CANARY V1 POLICY | **INVALID / SUPERSEDED FOR ACCEPTANCE**; 역사적 protocol/report는 보존 |
| NEW DISPOSITION ARCHITECTURE | **DESIGNED — question-specific one-sided** |
| MODEL BINDING POLICY | **REDESIGNED — request channel / returned concrete 분리** |
| CANARY V2 | **DESIGNED / NOT EXECUTED**; wire/protocol의 machine freeze는 후속 작업 |
| FINAL THRESHOLDS | **NOT FROZEN** |
| TRIAL V2 | **BLOCKED UNTIL CANARY V2 PASS** 및 §13의 구현·계정·freeze 조건 충족 |
| PROSPECTIVE TRIAL | **NOT STARTED** |
| ACTUAL EVALUATION / R5R ACTUAL EVALUATION | **NOT EXECUTED** |

이번 작업의 추가 provider/API 호출 **0**, 실제 StockScope 데이터 전송 **0**, source/runtime/frontend 변경 **0**, JSON contract/migration 변경 **0**이다. `JEV_API_KEY` 및 `.env` 접근 **0**, Holdout 검색·metadata·hash·존재 probe를 포함한 접근 **0**이다. 기존 frozen/history artifact를 수정하지 않았다.

이번 검증은 지정된 V1 JSON records의 합계·band mismatch·반복 차이·현재 policy 결과를 독립 산술로 재확인한 것과 이 문서의 일관성 확인이다. 새로운 canary, trial, evaluation, project runtime 또는 테스트 suite를 실행하지 않았다. 생성 산출물은 이 문서 하나다.

보존 확인에서는 명시적으로 읽은 근거 파일 13개의 작업 전후 SHA-256이 일치했다. 대상은 §2의 지정 문서·JSON·TypeSafe 코드뿐이며 금지된 데이터 영역을 탐색하거나 해시하지 않았다.
