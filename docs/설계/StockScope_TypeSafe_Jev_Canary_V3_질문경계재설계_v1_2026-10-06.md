# StockScope TypeSafe Jev Canary V3 질문·상태 경계 재설계 v1

작성일: 2026-10-06 (Asia/Seoul)  
모드: **DESIGN / ANALYSIS ONLY**  
분석 기준 repository HEAD: `155aebce115841b2cbec4a74fd527a9d81a0c4bc`  
산출물: 이 Markdown 문서 하나. 구현·machine-readable V3 protocol·실행 결과가 아니다.

## 1. 결정과 제품 목적

**ARCH C + D를 채택한다. Q1의 의미 충돌 명제는 KEEP, Q2는 STRUCTURE하여 local owner로 이전, Q3는 LOCALIZE하여 등록된 의미 의존성의 완결성 검사로 제한한다. 외부 질문은 Q1 한 개다.** 3-Noul 및 Q1/Q2/Q3가 같은 state를 읽는 구조를 종료한다. Q1에 필요한 의미만 실제 request에 넣으며, Q2/Q3를 별도 provider call로 분리하지 않는다.

이 결정은 Q2/Q3가 어떤 형태로도 학습 불가능하다는 결론이 아니다. V2는 현재 명제와 state로 필요한 제품 경계를 구별하지 못했다. 그중 rule identity, 확인/실행 역할, 등록된 정의·연결의 존재는 StockScope가 소유할 수 있는 사실이다. 이를 AI 확률로 다시 판단할 이유보다 로컬에서 명확하게 표현할 이유가 강하다.

제품 목적은 **사용자가 주식 판단을 더 빠르고 명확하게 할 수 있도록 의미 있는 추가 검토 신호만 제공하는 것**이다. 경로는 다음과 같다.

```text
canonical ENTRY_CANDIDATE
  → local eligibility / captured semantic contract 확인
  → local entry-role·link 검사와 Q1 전용 projection
  → 필요한 경우에만 Q1 semantic review 한 번
  → StockScope의 versioned deterministic policy
  → 출처가 구분된 추가 확인 신호
```

Scanner·Strategy·Risk는 기존 주인이다. Jev는 추천, 순위 변경, 가격 산술, condition PASS/FAIL, stop/target/RR, 매수·매도, 미래수익을 판단하지 않는다. Jev가 없어도 baseline을 그대로 유지한다. local signal도 이번 설계에서 후보·주문을 변경하는 권한을 얻지 않는다.

**선택의 대가**도 명시한다. arbitrary prose의 숨은 의미 누락을 Q3가 찾아줄 가능성은 포기한다. 대신 지원하는 의미 계약을 명시하고 지원하지 않는 입력은 no-call로 남긴다. structured provenance를 실제 capture에 공급할 수 있는지, 그 뒤에도 Q1에 local code와 중복되지 않는 가치가 남는지는 아직 미검증이다. 이 공급 조건을 충족하지 못하면 V2 fallback이나 임의 추출로 진행하지 않는다.

## 2. 근거, 읽기 범위와 authority

사용자가 지정한 다음 19개 파일을 읽었다. 이 외 데이터 영역으로 탐색 범위를 확장하지 않았다. 코드 파일은 텍스트로만 읽었고 프로젝트 모듈을 import하거나 runner·dry-run·테스트·평가 엔진을 실행하지 않았다.

| 근거 | 사용한 내용 |
|---|---|
| `docs/StockScope_인수인계_2026-10-06_DOCS_CLEANUP_COMPLETE_JEV_SHADOW_NEXT.md` | 제품 역할, TypeSafe correction, V2 구현·운영 경계 |
| `docs/설계/StockScope_TypeSafe_Jev_설계동결_v1_2026-10-06.md` | external state, deterministic owner, baseline·audit·no-call 불변식 |
| `docs/설계/StockScope_TypeSafe_Jev_Canary_정책재설계_v1_2026-10-06.md` | V1 진단, V2 명제·conflict-first·independent validation 설계 |
| `docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V1.json` | 당시 state/gold 및 공통 band 후보 |
| `docs/contracts/JEV_TYPESAFE_MODEL_BINDING_V1.json` | preview request / concrete response의 역사적 기록 |
| `docs/validation/JEV_TYPESAFE_CANARY_V1_2026-10-06.json` | 실제 V1 FAIL 및 24개 응답 |
| `docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V2.json` | selection/validation fixture, hard gold, 반복·선택 규칙 |
| `docs/contracts/JEV_TYPESAFE_MODEL_BINDING_V2.json` | stable request channel 및 관측 binding |
| `docs/validation/JEV_TYPESAFE_CANARY_V2_2026-10-06.json` | 36개 selection records, 실패·미실행 사실 |
| `backend/app/jev/typesafe_questions.py`, `typesafe_questions_v2.py` | 실제 V1/V2 명제와 참조 범위 |
| `backend/app/jev/typesafe_policy.py`, `typesafe_policy_v2.py` | V1 evidence-first와 V2 conflict-first, threshold 비교 의미 |
| `backend/app/jev/typesafe_state.py` | projector가 공급하는 정보와 빠진 구조 |
| `backend/app/jev/typesafe_service.py` | 동일 state에 질문 묶음을 보내는 실제 request 구성 |
| `backend/app/jev/typesafe_projection.py` | 저장된 답변·model·policy의 version별 재검증 |
| `backend/app/jev/typesafe_evaluation.py` | cohort identity 및 VALID + REVIEW_REQUIRED만 virtual defer하는 규칙 |
| `backend/app/jev/typesafe_canary.py`, `typesafe_canary_v2.py` | fixture 공급, preflight, 선택 실패 후 validation 차단 |

인수인계 §39의 `Real V2 Canary NOT EXECUTED`와 이전 설계의 미실행 표시는 작성 당시 상태다. **실행 여부는 실제 V2 report 및 이번 사용자 지시를 우선한다.** 과거 문서를 수정하여 이 차이를 없애지 않는다. 현재 소스에는 이미 V1/V2 service/projection/evaluation dispatch가 있으므로 과거 설계의 “현재는 low/high만 지원”이라는 설명도 현 HEAD의 사실로 승계하지 않는다.

관찰값은 로컬에 저장된 역사적 자료다. 최신 provider 문서·모델·요금·계정 정책을 조회하거나 추정하지 않았다. 아래 소수는 Noul 출력값이며 교정된 정답 확률, calibration accuracy, 상승 확률이 아니다.

## 3. V2의 공식 역사적 지위

| 항목 | 확정 상태 |
|---|---|
| CANARY V2 | **EXECUTED / DIAGNOSTIC FAIL** |
| report status / error | `FAIL` / `CANARY_V2_NO_ELIGIBLE_THRESHOLD` |
| PROVIDER CONNECTION | **PASS — V2 observed scope** |
| MODEL RESPONSE CONTRACT | **PASS — V2 observed scope** |
| MODEL BINDING | **OBSERVED**, request `jev-latest`, channel `STABLE_ALIAS`, returned concrete `jev-1.13.0` |
| `jev-preview` | `PREVIEW_ALIAS`. V2 acceptance request 아님 |
| model discovery attempts | 1 |
| System One planned / attempted / completed / valid / failed | 72 / **36 / 36 / 36 / 0** |
| total attempts | **37** |
| SELECTION PARTITION | **EXECUTED 36/36 VALID**, 12 fixture × 3회 |
| VALIDATION PARTITION | **NOT EXECUTED**, calls 0, `validation_analysis=null` |
| selected threshold / FINAL THRESHOLDS | `null` / **NOT FROZEN** |
| TRIAL V2 | **BLOCKED**, `BLOCKED_CANARY_FAILED` |
| PROSPECTIVE TRIAL | **NOT STARTED** |
| real StockScope data sent / actual trial activation | false / false |
| ACTUAL EVALUATION / R5R ACTUAL EVALUATION | **NOT EXECUTED / NOT EXECUTED** |
| HOLDOUT | **LOCKED / NOT ACCESSED** |

응답 36건이 유효했다는 제한적 연결·응답 계약 성공과, semantic acceptance 실패를 분리한다. provider/API/auth/schema failure로 분류하지 않는다. account policy는 report상 `NOT_VERIFIED_BY_CANARY`, actual provider cost는 `UNKNOWN`이다. concrete 이름이 같다는 사실이 model weights의 불변성이나 최신 request 가능성을 증명하지 않는다.

V1도 FAIL 그대로 보존한다. V1의 preview 분류 오류, 공통 band 문제와 일부 gold 문제는 V2 설계의 동기였으며, V2가 다시 실패했다는 이유로 V1을 정당화하지 않는다. V2는 미래 architecture의 진단 자료이고 새 contract의 calibration sample이 아니다.

## 4. 실제 selection records에서 확인되는 경계

아래는 V2 report `records.selection`을 fixture와 repetition으로 정렬한 원래 값이다. T/F는 V2 protocol의 `(Q1,Q2,Q3)` gold다. 마지막 행만 soft다.

| fixture | gold | Q1 (1 / 2 / 3) | Q2 (1 / 2 / 3) | Q3 (1 / 2 / 3) |
|---|---|---|---|---|
| s01 | F,F,F | .10 / .12 / .11 | .20 / .22 / .21 | .62 / .64 / .65 |
| s02 | F,F,F | .05 / .05 / .05 | .15 / .15 / .14 | .68 / .71 / .70 |
| s03 | F,F,F | .20 / .24 / .21 | .50 / .30 / .39 | .65 / .67 / .61 |
| s04 | F,F,F | .15 / .14 / .11 | .18 / .18 / .18 | .56 / .59 / .57 |
| s05 | T,F,F | .91 / .90 / .91 | .20 / .21 / .19 | .29 / .30 / .28 |
| s06 | T,F,F | .75 / .79 / .75 | .27 / .31 / .30 | .35 / .31 / .31 |
| s07 | F,T,F | .15 / .18 / .15 | .93 / .92 / .92 | .32 / .35 / .37 |
| s08 | F,T,F | .13 / .12 / .12 | .41 / .39 / .38 | .70 / .71 / .71 |
| s09 | F,F,T | .21 / .22 / .26 | .17 / .19 / .19 | .72 / .70 / .67 |
| s10 | F,F,T | .18 / .19 / .15 | .23 / .22 / .24 | .65 / .67 / .66 |
| s11 | T,T,F | .92 / .92 / .93 | .89 / .86 / .87 | .26 / .26 / .26 |
| s12 | soft | .14 / .12 / .13 | .16 / .15 / .15 | .59 / .58 / .57 |

### 4.1 Q2는 grid를 촘촘하게 만들어도 현재 hard gate를 만족시킬 수 없다

V2는 `p >= T`를 positive로 판정하고 모든 hard 반복을 맞춰야 한다. s08을 전부 positive로 만들려면 `T_entry <= .38`, s03을 전부 negative로 만들려면 `T_entry > .50`이어야 한다. 두 조건은 양립하지 않는다. 더 약하게 s08의 max .41과 s03의 max .50만 비교해도 순서 역전이 보인다.

이는 어떤 grid를 더 조회할 문제가 아니라 **저장된 이 records와 명제의 hard separation 불가능**이다. 새로운 state·명제도 실패한다는 증명은 아니다. 평균이나 유리한 repetition만 택하면 V2의 acceptance 기준 자체를 사후 변경하게 된다.

### 4.2 Q3도 normal과 missing을 분리하지 못한다

s09/s10을 모두 positive로 하려면 `T_evidence <= .65`, 정상 s02를 모두 negative로 하려면 `T_evidence > .71`이 필요하다. 명백한 Q2 충돌인 s08에서도 Q3가 .70–.71이다. 반면 clear conflict s05/s07/s11에서는 낮다. Q3는 단순 missing detector보다 “충돌을 쉽게 확립했는가”와 결합된 패턴을 보인다. 그 인과 메커니즘은 관측만으로 확정할 수 없다.

### 4.3 Q1은 유지할 근거가 있으나 합격 근거는 아니다

hard negative의 Q1 최대는 .26, hard positive 최소는 .75다. s06에서는 Q2의 selected-band 연결이 없어도 Q1 .75–.79가 유지됐다. 그러나 11개 hard fixture의 3회 반복은 33개의 독립 의미 사례가 아니다. validation을 실행하지 않았고 설명도 매우 직접적이다. 지금 Q1 threshold를 freeze하는 답은 **NO**다.

## 5. Q2 root-cause: 확인된 구조와 가설의 분리

| 원인 후보 | 관찰 사실 → 문제 | 선택지 → 채택 결정 | 이유 → 다음 검증 |
|---|---|---|---|
| A. wording | V2 Q2는 `strategy_context.strategy_description`에서 same price rule을 찾도록 명시한다. 같은 문자열에 전략 방향과 entry 의도가 섞임 | 문장만 강화 / typed separation → **typed separation** | 읽지 말아야 할 전략 정의도 물리적으로 입력됨 → Q1 정의의 유무와 Q2 역할 방향을 독립적으로 바꾸는 대조 |
| B. state coupling | service는 하나의 state와 3질문을 전송. s08의 Q1 K 정의 부재와 Q2 낮은 값이 공존 | 같은 payload에 scope 지시 / 필요한 payload만 전송 → **물리적 projection** | instructions는 접근 경계가 아님. 다만 coupling이 s08의 원인이라는 인과 증명은 없음 → local entry 변형 시 Q1 wire bytes 동일성 검사 |
| C. referential link | s06/s10은 Alpha=confirmation, Beta=executable이지만 selected band의 identity 없음 | 자연어 추측 / captured reference → **captured reference** | 두 가능한 완성이 entry 비교를 바꿈. s08은 “single entry_context rule”이므로 same-rule 연결 자체는 명백함 → s08을 link-missing gold로 바꾸지 않음 |
| D. deterministic ownership | 현재 state에는 represented role/flag가 있지만 별도 captured intended role/reference는 없음 | 자연어 역할 해석 유지 / 출처 있는 role·ID 도입 → **후자** | 두 역할과 동일 rule이 authoritative하게 주어지면 비교는 enum 규칙. 현재 코드가 이미 모두 처리한다고 주장하지 않음 → intended role의 독립 출처와 rendering 경로 검증 |
| E. 사용자 가치 | s07은 confirmation→execution 혼동, s08은 execution→confirmation의 반대 혼동 | 둘을 동일 위험으로 취급 / 양방향 검사·사유 구분 → **로컬 양방향 검사** | 실행 오해 방지는 유용하지만 AI 소유일 필요가 없음. 반대 혼동의 사용자 손실은 같다고 가정하지 않음 → 두 방향의 설명·중복 경고 부담 별도 측정 |

**중요한 confound**: s07과 s08은 Q1 completeness뿐 아니라 Q2 충돌 방향, condition 방향, 설명 문구도 다르다. s07 대비 s08 하락을 Q1 누락의 영향만으로 설명할 수 없다. confirmation 표현을 일괄적으로 안전한 negative로 읽는 방향 비대칭도 가설이다. s03의 Q2 최대 .50은 정상 확인 band에도 오경고가 생길 수 있음을 보여준다.

따라서 후속 offline 검사에는 intended role 2종 × represented role 2종 × Q1 정의 완결/누락의 factorial truth table을 둔다. Q2가 로컬 owner가 되면 Q1 정의 변경은 Q2 결과에 아무 영향도 없어야 한다. 이 검사는 실패 원인의 신경망 내부 메커니즘을 입증하려는 추가 provider 실험이 아니다.

자연어 가격 설명과 structured role이 어긋나는 문제는 남는다. 승인된 제품 설명을 역할별 template/typed clause로 관리하고 작성 시 의미 감사를 해야 한다. 임의의 자유문장에서 `intent_role`을 추론하여 넣는 projector는 채택하지 않는다. 그 경로를 유지해야 할 실제 제품 필요가 나중에 입증되면, 독립된 text-versus-role Q2를 새 contract로 검토할 수 있다. 지금은 그런 production 필요나 빈도가 확인되지 않았다.

## 6. Q3 root-cause와 소유권

### 6.1 복합 명제와 baseline bias

V2 Q3 instructions/criteria는 실질적으로 다음을 요구한다.

```text
no evidenced Q1 conflict AND no evidenced Q2 conflict
AND at least one essential intent/definition/link missing
AND overall review cannot be completed without invented meaning
```

Q3가 다른 Noul 값을 입력받지는 않는다. 같은 state에서 Q1/Q2의 의미 판단을 다시 해야 한다. 정책의 conflict-first와 질문 내부의 no-conflict 조건이 중복된다. scalar 하나에서는 어떤 정의가 빠졌는지, 어느 비교가 불가능한지 식별되지 않는다.

normal s02 .68–.71, missing s09 .67–.72와 s10 .65–.67의 겹침은 분리 실패의 사실이다. “충돌 없음”이 Q3를 올리는 baseline bias, bearish state에 대한 외부 직관, `overall semantic review`, `cannot be completed`, `essential meaning`이 통상적 불확실성을 흡수하는 wording 문제는 모두 가능한 설명이다. **정상 대조가 높다는 것만으로 모델의 내부 bias를 확정하지 않는다.**

### 6.2 simpler proposition은 가능하지만 자동 채택하지 않는다

대안 ARCH B에서는 “이 비교가 참조하는 명시적인 의미 정의 또는 same-rule 연결이 제공되지 않았는가?”만 묻는다. Q1/Q2 conflict 여부는 묻지 않는다. 이 경우 conflict와 evidence missing은 동시에 참일 수 있고, local policy가 conflict-first를 담당하면 s06/s08형 suppression을 논리적으로 피할 수 있다.

하지만 다음 문제가 남는다.

1. 등록된 reference/definition의 존재는 local join으로 확인할 수 있다. 같은 boolean을 Noul로 다시 묻는 일은 중복이다.
2. arbitrary prose에 숨은 참조를 전부 찾아내는 문제는 단순 field presence와 다르다. 문구만 단순화했다고 해결됐다고 할 수 없다.
3. 한 evidence Noul로 여러 질문의 누락을 모으면 scope 오염과 위치 설명의 한계가 남는다.

**관찰 사실 → 문제 → 선택지 → 채택 결정 → 이유 → 다음 검증**: normal/missing 중첩과 복합 instruction → 유보가 제품 신호를 흐림 → overall 유지 / pure-missing Noul / local dependency 검사 → **LOCALIZE** → 지원 범위를 명시한 missing field/link는 deterministic owner가 적합 → 등록 누락·stale binding·빈 정의·정의의 의미 불충분을 구분한 사전 감사.

### 6.3 LOCALIZE의 한계와 방어선

`semantic_link_status=COMPLETE`는 **등록된 의존성이 모두 resolve됐음**만 뜻한다. 모든 자연어가 이해 가능하다거나 Q1에 충돌이 없다는 뜻이 아니다. nonempty string만으로 semantic adequacy를 인증하지 않는다.

지원하는 strategy version은 작성 시 필요한 term/condition reference를 명시하고, 그 정의가 실제 비교 의미를 담는지 검토해야 한다. “K는 이 전략의 K다” 같은 순환 정의, 선언하지 않은 외부 참조, 어느 쪽도 판정할 수 없는 정의는 승인된 semantic contract에 들어갈 수 없다. projector가 이 문제를 일반 NLP로 완전 탐지한다고 주장하지 않는다. 작성 감사를 통과하지 않은 자유문서는 `UNSUPPORTED_SEMANTIC_CONTRACT`로 no-call한다.

이 제한으로 예상치 못한 semantic gap을 놓칠 잔여 위험은 있다. 후속 독립 synthetic gold 감사와 허용된 production contract 감사에서 local completeness가 충분하지 않음이 드러나면 이 architecture의 준비 gate가 실패한다. missing Noul을 몰래 복구하거나 누락을 negative로 위장하지 않는다. 새로운 근거를 가지고 설계를 다시 결정한다.

## 7. architecture 비교

다음 비용·안정성 평가는 설계상 기대다. 실제 latency/cost 개선이나 production 재현성을 측정한 결과가 아니다.

| 안 | 사용자 추가 가치·deterministic 중복 | false review / ABSTAIN 위험 | 설명·production 재현성 | 비용·복잡성 / baseline fallback | 결정 |
|---|---|---|---|---|---|
| **A: 현재 3-Noul, wording만 수정** | 변경량은 작지만 Q2의 rule 찾기와 Q3 복합 판단 유지 | s03/s08 및 s02/s09 중첩 원인을 제거하지 못함 | 문구 개선만으로 scope 강제 불가 | 1 call, 세 질문. 실패 시 baseline 유지 가능 | 미채택. 구별 가능한 개선 가설이 약함 |
| **B: 직교화 3-Noul** | Q1 strategy conflict, Q2 entry-rule conflict, Q3 pure missing. 정책과 명제 분리의 가치 | compound Q3 부담 감소 가설. 같은 state 노출과 local truth 중복은 남음 | overall보다 명확하나 missing 위치·범위가 다시 합쳐짐 | 1 call, 세 threshold. baseline 유지 가능 | 합리적 비교 대안이나 기본안 아님 |
| **C: structured state 강화** | captured intended role/reference와 representation을 연결하면 Q2의 추측 제거 | enum/ID는 안정적이나 잘못 채운 값·누락 은폐가 위험 | 출처·version을 갖추면 설명 가능. 현재 capture 공급은 미입증 | 로컬 작성·검증 비용 증가, provider 정보·질문 감소 가능 | **채택**. 결정된 local truth는 외부 전송하지 않음 |
| **D1: Q1만 유지** | 남는 자연어 의도/조건 조합만 AI. Q2/Q3 의미는 로컬에 남김 | Q2/Q3발 오경고·유보 제거, 대신 no-call 증가 가능 | 좁은 supported contract와 정확한 coverage 보고 필요 | 최대 1 call, 1 threshold. 모든 장애에서 baseline 유지 | **C와 결합하여 채택** |
| **D2: Q1+Q2** | 자유문장 가격 설명이 꼭 필요한 경우 잔여 가치 | Q2 오경고·방향 비대칭, completeness 별도 필요 | ID만 추가하고 intent를 자유문장에 두면 잔여 semantic 비교 가능 | 1 call 2질문. strict isolation은 추가 구조 필요 | 현재 production 추가 가치 미입증으로 미채택 |
| **D3: Q1+evidence** | arbitrary prose 누락을 잡을 가능성 | evidence가 다시 일반 불확실성을 흡수할 위험 | local로 못 잡는 누락의 gold와 위치가 필요 | 1 call 2질문. baseline 유지 가능 | local completeness 한계가 실제 확인될 때 재검토 |
| **E: Q1/Q2별 실제 call 분리** | 물리적 isolation, 양쪽 residual semantic 검토 가능 | 각각의 명제 실패는 해결하지 못함 | scope는 강하지만 부분 실패·join·cohort 관리 추가 | 보통 2 calls. 직렬 지연 또는 병렬 예산·상태 복잡성 | 중복된 Q2까지 호출할 이점이 없어 미채택 |

**결정 근거**: V2의 세 질문 수를 보존해야 한다는 제품 요구는 없다. C+D1은 참조 찾기를 제품 계약으로 만들고, local truth를 AI에게 재질문하지 않으며, Q1의 제한적 분리 가설만 새 검증에 남긴다. 모든 안에서 baseline 보존은 필수라서 그것만으로 특정 안의 우위를 주장하지 않는다.

AI 사용 의미가 없어질 가능성도 수용한다. Q1까지 같은 enum/조건식을 비교하는 것으로 완전히 해결된다면 **NO_FUZZY_CONTEXT / no-call**이 정답이다. Q1을 남기기 위해 전략 설명이나 상태를 일부러 모호하게 만들지 않는다.

## 8. 현재 external state 감사와 새 읽기 경계

### 8.1 현재 코드가 실제로 하는 일

`typesafe_state.py::project_typesafe_state`는 Risk READY/no warning, condition missing=0 및 각 detail PASS, 알려진 metric mapping, description 존재/길이, price consistency OK 등을 확인한다. condition의 current/required는 null을 허용하고, price-rule role은 nonempty인지 확인한다. executable flag는 값이 없으면 false로 변환한다. 이는 semantic dependency completeness나 strict role/boolean 계약의 완전 검증이 아니다.

외부 state는 context, strategy_context, condition_context, entry_context, baseline의 다섯 영역이다. `reference_id`, `description_rule_id`, 독립적인 `intent_role`, Q1 dependency manifest는 현재 projector에 없다. 이를 이미 보유한 production field라고 기술하지 않는다.

V2 harness는 synthetic state를 wrapper에 넣어 production projector round-trip을 확인한다. 따라서 **projector shape 도달성**은 검증한 구조다. wrapper 자체가 synthetic description과 값들을 주입하므로 실제 production capture가 동일한 표현력이나 source provenance를 갖는다는 증거는 아니다.

### 8.2 field별 owner와 허용 독자

| 현재 field | 현재 문제·용도 | 새 설계에서의 처리 |
|---|---|---|
| `strategy_context.strategy_description` | Q1 intent, Q2 price-rule intent, K/selected 참조가 한 문장 영역에 혼합 | 자유문장 통째 전송 종료. 사전 작성·version binding된 strategy intent clause만 Q1로 projection. 원문/출처는 local audit |
| `strategy_context.strategy_key` | semantic 비교 자체에 불필요한 identity | local audit. Q1 wire에는 보내지 않음 |
| `condition_context` | 의미 label과 current/required가 함께 있어 산술 재판정 유혹 | Q1에만 허용. local evaluator가 제공한 의미 사실과 fixed term definition으로 제한. required numerical threshold·원시값은 제외 |
| `entry_context.price_rule` | represented role/flag는 있지만 intended role/동일 rule 근거가 자유문장 | Q2 local checker만 읽음. Q1 wire에는 없음 |
| `entry_context.price_consistency` | 이미 local 소유. SEPARATED/NEAR/overlap을 conflict로 오인 가능 | 기존 hard gate/audit에만 사용. semantic 역할 대용 금지 |
| `entry_context.action`, `baseline.action/candidate_state` | 후보 상태는 실행 지시가 아님 | eligibility/audit only. Q1 evidence나 Q2 conflict의 positive 근거 아님 |
| `context.market/as_of_date/horizon_intent` | market/date의 상식 개입 가능 | 시장·날짜는 local. horizon에 따라 의미가 달라지면 이미 해당 version의 intent에 bind하고 필요한 정의만 전송 |
| capture/hash/rank/ticker/name/금지 정보 | identity, outcome 또는 scope 밖 사실 | 기존 금지 유지. audit ID도 provider에 보내지 않음 |

질문별 허용 scope는 다음과 같이 닫는다.

* **Q1 외부**: strategy intent + 참조된 용어 정의 + already-passed condition meaning only.
* **Q2 local**: captured price-rule intended role + 같은 rule의 represented role/flag + reference binding only. 전략 방향·Q1 결론은 입력이 아니다.
* **Q3 local**: Q1/Q2 각각의 required reference 목록과 resolved definition/link, version·지원 여부 only. conflict 결과나 확률은 completeness의 입력이 아니다.

Q2 연결 누락은 Q1 payload를 바꾸지 않는다. Q1 정의 누락은 Q2 역할 비교를 바꾸지 않는다. 단 Risk/가격 유효성 등 기존 전체 no-call gate는 계속 최상위이며 semantic isolation을 이유로 우회하지 않는다.

### 8.3 최소 structured local contract

아래는 설계용 field 의미이며 현재 runtime schema나 새 JSON artifact가 아니다.

| field | owner / 출처 | 검증과 사용 |
|---|---|---|
| `strategy_semantics.intent_text` | 승인된 strategy version의 고정 Q1 전용 문장 | 가격 role 설명을 포함하지 않는 authored clause. runtime 요약/번역/regex 문장 추출 금지 |
| `strategy_semantics.required_definition_ids` | 같은 version에서 작성 시 선언 | 명시적으로 빈 목록도 허용. 빠진 목록을 빈 목록으로 default하지 않음 |
| `strategy_semantics.definitions` | 같은 canonical capture에 저장된 definition id/text | 참조 유일성, 중복·누락·순환·지원 여부 및 작성 시 의미 감사 |
| `condition_semantics` | 기존 evaluator의 captured 의미 사실 + versioned fixed mapping | 숫자를 Jev가 해석하지 않도록 `observed_meaning` 제공. mapping이 새 판단을 발명하면 지원 불가 |
| `price_rule.intent_role` | strategy rule 정의의 확인 전용/실행 범위 역할 | `CONFIRMATION_ONLY` 또는 `EXECUTABLE_ENTRY`. 역할이 조건부이면 captured selection이 하나로 resolve돼야 함 |
| `price_rule.reference_id` | entry representation이 가리키는 captured rule ID | 종목/사용자 식별자 아님. local join 전용 |
| `description_rule_id` | 승인된 가격 설명 clause가 가리키는 rule ID | reference와 동일 source version의 같은 rule인지 검증 |
| represented role + executable flag | captured entry-guide 표현 | 두 값 일치도 strict check. absent/unknown과 false를 구분 |
| `semantic_link_status` | projector의 local 계산 결과 | Q1/Q2별 `COMPLETE / MISSING / AMBIGUOUS / UNSUPPORTED`. 사람/AI가 채우는 정답 flag 아님 |

`intent_role`을 represented role에서 복사해서 “일치”를 검증하면 tautology다. 두 값은 **의도 정의와 표현 생성 경로라는 서로 다른 역할의 provenance**를 가져야 한다. 같은 canonical rule을 사용해 표현을 올바르게 생성하는 것이 최선이고, 그 경우 runtime 비교의 가치는 invariant 검사에 가깝다. 이를 AI의 추가 발견으로 계상하지 않는다.

현재 capture에 없는 정보를 최신 registry에서 사후 보충하지 않는다. 후속 구현에서 필요하면 source contract를 새 version으로 바꾸고 신규 capture부터 공급한다. 과거 snapshot/backfill/V1·V2 artifact는 변경하지 않는다. 승인된 의미 계약을 만들 수 없는 strategy는 지원 범위에서 제외하고 no-call 분모에 남긴다.

외부 Q1 state의 논리적 shape는 `strategy_intent`, `term_definitions`, `passed_condition_meanings` 세 영역이다. definitions의 local ID는 필요한 경우 request 안에서만 쓰는 중립 reference로 변환한다. field별 길이·배열 수와 UTF-8 총 8 KiB 상한, 조건 최대 12개를 사전 고정한다. 전체 intent 360자, 개별 의미/정의 160자를 기본 한도로 삼되 넘어가면 truncate하지 않고 no-call한다. label/gold/purpose/split·local conflict/completeness flag는 외부에 넣지 않는다.

### 8.4 same-request와 실제 isolation의 선택

하나의 request에 `q1_scope`, `q2_scope`를 모두 넣고 각 질문에 subtree만 읽으라고 지시하는 방식은 call 한 번으로 처리할 수 있지만 모델은 여전히 다른 subtree를 볼 수 있다. 이름과 instruction은 엄격한 정보 차단이 아니다.

질문별 실제 payload/call 분리는 그 오염 경로를 없애지만 두 semantic 질문을 유지할 때 call·latency·partial failure 비용이 증가한다. 채택안은 **한 번의 Q1-only request에서 Q2/Q3 substate 자체를 제외**하므로 두 번째 호출 없이 정보 경계를 강제한다. “same-request 유지”는 **다문항 공동 요청 NO, 요청 수는 callable candidate당 최대 1**이다.

## 9. Q1 KEEP의 정확한 의미와 검증할 반례

KEEP은 V2의 “제공된 의미로 성립하는 명시적·실질적 strategy conflict”라는 명제를 보존한다는 뜻이다. wire scope와 state가 바뀌므로 question/state/projector identity는 반드시 새 version이다. V2 probability나 threshold를 승계하는 KEEP이 아니다.

후속 freeze에 사용할 단일 Noul 문안 초안은 다음과 같다. 이번 문서가 provider wire의 machine freeze를 완료한 것은 아니다.

> Using only strategy_intent, term_definitions and passed_condition_meanings, judge whether the supplied condition meanings establish an explicit, material contradiction of the stated strategy intent. Treat the supplied condition results as already evaluated by StockScope. Do not recalculate eligibility or numeric pass/fail, infer absent definitions, or judge entry execution, risk, attractiveness or future returns.

True: 제공된 condition 의미가 정의된 intent의 요구·배제 관계와 명시적으로 충돌한다.  
False: 의미가 일치하거나 명시적으로 허용된 변동이거나, 주어진 근거만으로 명시적 충돌이 성립하지 않는다. 이 false는 모든 뜻을 이해했다는 보증이 아니다.

Q1 readiness가 false이면 위 question을 호출하지 않는다. 일반적인 정도의 애매함은 “등록된 필수 정의가 빠짐”과 다르며 soft 사례로 검증한다. 중간 p 자체로 ABSTAIN을 만들지 않는다.

| 확인 사항 | V2로 알 수 있는 것 / 남은 한계 | 다음 검증 |
|---|---|---|
| gold artifact / 누설 | harness는 state와 questions만 보내고 expected_propositions·rationale는 보내지 않음. 그러나 문장 안에 정답을 암시하는 쉬운 표현이 많음 | gold metadata 완전 분리, 같은 어휘의 정·부 minimal pair, case ID를 text에 넣지 않음 |
| 직접적 synthetic wording | s05/s11의 only/excluded와 반대 방향은 쉬운 비교 | 단순 반대뿐 아니라 조건 조합·허용 예외·부정 범위·동의어 포함. 단 유일한 hard gold를 논증할 수 있어야 함 |
| production signal | 현재 projector가 description을 운반한다는 사실만 확인 | 승인된 strategy intent의 capture 경로와 condition meaning 공급 가능성을 별도 offline 감사. 실제 종목 데이터는 이번에 읽지 않음 |
| deterministic 중복 | PASS detail와 strategy 설명의 의미 비교는 수치 PASS 재계산과 구별 가능 | numeric/required_value를 wire에서 제외. enum lookup으로 정답이 완전히 결정되면 local-only 사례로 분류 |
| 보존할 가치 | 명시적 설명과 여러 조건 조합의 불일치 재확인이라는 가설 | local-only 대비 Q1에서만 생기는 유효 signal과 false review를 이후 별도 prospective 절차에서 측정 |
| threshold freeze | selection 분리는 promising, validation 0 | **지금 freeze 금지**, 새 V3 selection/validation 필요 |

## 10. 새 policy precedence와 status 의미

local checker와 Jev review의 출처를 합쳐 `VALID`를 조작하지 않는다. 다음 순서는 미래 구현 설계이며 현재 소스 동작을 바꾼 것이 아니다.

1. 기존 canonical/Risk/가격 유효성/범위·승인·budget 등 전체 hard gate 실패: Jev `SKIPPED`, disposition `null`, baseline 유지. local owner가 이미 가진 issue는 해당 경로에 남긴다.
2. 전체 gate가 허용하는 범위에서 local Q2 역할/연결 검사와 Q1 readiness를 독립 계산한다. 명백한 local entry-role 불일치는 **local review signal**로 남기고 Q1의 정의 누락이나 provider 장애로 지우지 않는다. 이 신호는 Jev Noul 결과가 아니다.
3. Q1 essential definition/mapping/지원 계약이 없으면 Jev `SKIPPED / Q1_SEMANTIC_CONTEXT_UNAVAILABLE`, disposition `null`. Q2만 불완전해도 Q1이 준비됐으면 Q1 호출을 막지 않는다.
4. Q1 request의 provider/schema/model/usage 실패는 `ERROR`, deadline은 `LATE`, 중단은 `INTERRUPTED`, 각각 disposition `null`. 정상 값으로 보충하거나 재호출하지 않는다.
5. on-time valid Q1 답변만 `p1 >= T_strategy`이면 `REVIEW_REQUIRED / STRATEGY_CONTEXT_CONFLICT`, 아니면 `PASS_THROUGH / NO_ADDITIONAL_STRATEGY_CONFLICT`다. equality 포함, 원시값 비교, probability 결합 없음.
6. 전체 제품 신호 해석은 **근거 있는 local/Jev conflict를 먼저 보존 → 미검토 scope 명시 → 검토한 scope에서 추가 signal 없음**이다. 다른 scope의 missing이 이미 성립한 conflict를 veto하지 않는다.

| 조건 | local entry 결과 | Jev status / disposition | 해석 |
|---|---|---|---|
| Q1 ready+양성, Q2 link missing | `MISSING` | VALID / REVIEW_REQUIRED(Q1) | Q1 신호 유지, entry 검토 미완결 별도 |
| Q1 missing, Q2 역할 충돌 | local entry conflict | SKIPPED / null | 로컬 확인 신호 유지. 가짜 Jev VALID 생성 금지 |
| Q1 ready+음성, Q2 역할 충돌 | local entry conflict | VALID / PASS_THROUGH(Q1 범위) | Jev가 entry 정상이라고 인증한 것이 아님 |
| Q1 양성, Q2 역할 충돌 | local entry conflict | VALID / REVIEW_REQUIRED(Q1) | 두 출처 표시 가능, probability 통합 금지 |
| Q1 missing, Q2 complete·일치 | 일치 | SKIPPED / null | Q1 검토 안 함. 전체 PASS_THROUGH로 승격 금지 |
| Q1 ready+음성, Q2 complete·일치 | 일치 | VALID / PASS_THROUGH | 제한된 Q1 추가 신호 없음 |
| Q1 provider failure, Q2 어떤 상태든 | 로컬 결과 보존 | ERROR 등 / null | Jev 실패와 local 결과 분리, baseline 유지 |

**Q3 localize는 모델 ABSTAIN을 local ABSTAIN으로 이름만 바꾸는 일이 아니다.** 필수 근거 부족을 pre-call에서 알면 SKIPPED다. 이 단일 명제 설계의 정상 valid path에는 ABSTAIN을 새로 만들지 않는다. 역사적 V1/V2 ABSTAIN은 그대로 보존한다. 낮아진 ABSTAIN 비율을 개선 성과라고 주장하지 않으며 `semantic no-call / in-scope`, valid coverage, local unavailable 비율과 함께 보고해야 한다.

현 evaluation은 `VALID + REVIEW_REQUIRED`만 virtual defer한다. Q2 로컬 신호는 그 성과를 Jev에 귀속하지 않는다. 이후 평가에서도 local-only baseline과 Q1 추가분을 분리해야 하며, local conflict를 Jev valid review로 섞는 변경은 금지한다. actual evaluation은 이번 범위 밖이다.

## 11. Canary V3: 필요하지만 아직 실행할 protocol은 아니다

**V3는 필요하다.** Q1 명제 핵심을 보존해도 입력을 분리하고 질문 수·policy·projector가 바뀐다. V2 validation fixture를 그대로 실행하면 변경한 architecture를 설계에 이미 이용한 경계·문구로 평가하게 된다. V1/V2 state의 rename/paraphrase와 기존 gold만 바꾼 세트도 새 independent acceptance로 사용하지 않는다.

V3는 채택한 C+D1을 검증한다. A/B/E를 같은 예산에서 동시에 탐색하고 좋은 안을 사후 선택하는 bake-off가 아니다. Q2/Q3 provider 질문은 없다. Q2 positive 및 evidence-missing은 **local route의 gold**로 남겨 기능 삭제가 오류 은폐가 되지 않게 한다.

### 11.1 fixture 작성·분할 방법

전체 40개의 새로운 synthetic canonical context를 **selection 20 / validation 20**으로 설계한다. 각 partition은 provider-callable 12개와 local-only 8개다. provider-callable만 3회 반복하므로 selection 36 responses, validation 36 responses, 최대 System One 72 attempts다. local-only는 사전 예상 경로가 no-call이고 provider 응답 수에 포함하지 않는다.

selection과 validation은 서로 다른 의미 조합·문장 구성·정의 방식을 사용한다. 같은 문장에서 rising/falling 또는 숫자만 바꾼 짝을 양 partition으로 갈라 독립성을 주장하지 않는다. 하나의 counterfactual family와 그 변형은 같은 partition에 둔다. split과 authoring 규칙은 응답 전에 확정한다. gold는 state 의미에서 작성하고, 가능하면 응답을 보지 않은 별도 검토자가 논증을 확인한다. 이번 작업에서 subagent나 외부 검토자에게 전송하지 않았다.

현재 설계는 fixture **architecture**를 닫는다. exact 40 payload/gold는 생성하지 않았다. 후속 작업에서 exact state·questions·gold를 모두 고정하기 전에는 network가 금지된다. 이 문서의 개념 예시는 frozen fixture 또는 PASS 증거가 아니다.

### 11.2 partition당 provider-callable 12개

| 구성 | 개수 | gold / 검증 목적 |
|---|---:|---|
| clear negative와 false-positive/false-abstain trap | 4 | Q1 F. 명시적으로 허용된 약세·예외, 정의된 경미한 변동, 금지 정보의 의도적 부재 등을 포함. 전부 PASS_THROUGH |
| 독립 Q1 positive | 2 | Q1 T. 하나는 직접 모순, 하나는 다중 조건의 의미 조합·예외 범위 모순. 숫자 PASS 재판정으로 정답을 만들지 않음 |
| mixed-context isolation family A | 2 | 동일 Q1 positive substate, local entry link complete ↔ missing. 두 경우 모두 정확히 같은 Q1 wire state와 REVIEW_REQUIRED |
| mixed-context isolation family B | 2 | 동일 Q1 negative substate, local entry 역할 일치 ↔ 불일치. 두 경우 모두 같은 Q1 wire와 PASS_THROUGH. local 신호만 바뀜 |
| soft ambiguity | 2 | 필수 정의는 있지만 정도 표현에 복수의 합리적 해석. binary gold를 강제하지 않고 반복·부담 기록 |

hard 10개 = Q1 negative 6 + positive 4. partition마다 hard response 30개, negative 18개, positive 12개, soft response 6개다. 같은 Q1 payload 쌍은 서로 다른 전체 local context의 isolation 검사를 위한 것이며 독립 의미 표본 두 개로 부풀리지 않는다.

false-abstain trap에서는 미래수익·종목명·뉴스·가격 상세의 부재를 readiness failure로 만들지 않는다. false-positive trap에서는 `ENTRY_CANDIDATE`, RANGE, proximity, bearish meaning 자체를 conflict로 취급하지 않는다. Q1에 entry text를 일부러 보내어 “무시하는가”를 시험하지 않고, projector가 그 text를 보내지 않는지 검증한다.

### 11.3 partition당 local-only 8개

| 구성 | 개수 | 사전 기대 |
|---|---:|---|
| Q1 required definition absent / empty or cyclic definition rejected | 2 | Q1 no-call, local entry는 일치. field 이름 존재를 의미 완결로 취급하지 않음 |
| intended confirmation ↔ represented execution / 역방향 | 2 | Q1 정의 부족과 동시에 두 방향 local entry conflict 각각 보존. Q1 no-call로 local 신호가 사라지면 실패 |
| same-rule reference missing / ambiguous multi-rule selection | 2 | Q1도 준비되지 않은 사례. Q2는 conflict 대신 MISSING/AMBIGUOUS. 역할을 추측하지 않음 |
| stale semantic version 또는 unsupported contract | 1 | no-call. 현재 registry로 소급 보충 금지 |
| Q1·Q2 모두 missing | 1 | no-call, 양쪽 부족 scope 기록, 전체 PASS나 Jev ABSTAIN 조작 금지 |

추가 offline truth-table 검증은 intended/represented role 2×2와 Q1 completeness 2종, missing ID, duplicate ID, unknown enum, absent boolean, 참조가 다른 rule인 경우를 포함한다. 이들은 provider 호출 수를 늘리는 calibration sample이 아니다. compound case는 callable positive+local conflict 조합과 local conflict+Q1 missing 조합 모두 포함하도록 exact fixture 작성 시 배치하며, 필요한 경우 family A의 complete variant에 local conflict를 둔다. Q1 wire 동일성은 유지한다.

### 11.4 causal 진단을 acceptance와 혼동하지 않기

새 구조에서 Q2 direction × Q1 completeness는 로컬 factorial로 독립 확인한다. Q1 wire에서는 Q2 field가 제거되므로 context 변형에 따른 payload 동일성이 1차 증거다. 동일 wire에서도 모델 반복 변동은 가능하므로 raw p equality를 요구하지 않고 frozen threshold의 hard decision 일치를 요구한다.

이렇게 통과해도 V2 s08의 원인이 coupling이었는지 방향 비대칭이었는지를 소급 증명하지 않는다. **새 architecture에서 그 경로가 사용자 신호를 오염시키지 않는지**가 V3 acceptance의 목적이다.

## 12. threshold selection, 사전 freeze와 gates

### 12.1 threshold 방법

**FINAL V3 THRESHOLD = NOT FROZEN.** slot은 Q1의 `T_strategy` 한 개만 남긴다. Q2/Q3용 threshold를 숨은 default로 두지 않는다.

후속 protocol의 coarse candidate 제안은 `{0.50, 0.70, 0.90}`이다. 척도의 중간·상위·매우 상위 escalation cut을 넓게 비교하는 세 점이며 확률의 calibration을 가정하지 않는다. V2 .26/.75 사이의 최적 경계를 추정하거나 .38/.50/.65/.71을 피해서 맞춘 grid가 아니다. state가 달라져 이 셋이 모두 부적합할 수 있다. 그 경우 FAIL을 허용하고 후보를 추가 조회하지 않는다.

selection에서 아래 모든 hard/운영 gate를 만족하는 후보만 eligible이다. 복수이면 (1) soft REVIEW_REQUIRED 수 오름차순, (2) T 내림차순으로 단 하나를 고른다. hard positive 감도는 먼저 충족해야 하므로 부담 최소화를 이유로 필요한 신호를 포기할 수 없다. margin 최적화, p 평균, 가장 좋은 반복 선택, 후속 provider threshold 탐색은 없다.

eligible 0이면 실행된 V3는 FAIL, validation provider calls 0, Trial BLOCKED다. eligible 하나를 잠근 뒤 validation은 그 값 하나로만 acceptance 판정한다. validation 실패 후 차순위 적용·grid 확대·gold 수정·질문 교체로 구제하지 않는다. 새 contract가 필요하면 새 독립 fixture와 새 version을 만든다.

### 12.2 응답 전에 함께 고정할 항목

| freeze 항목 | 필수 내용 |
|---|---|
| exact inputs | canonical synthetic source와 실제 projected wire bytes, local-only no-call 이유, 버전·hash |
| exact questions | Q1 ID/type/instructions/true·false criteria. Q2/Q3 미포함 |
| gold | 명제 gold, route, local signal, status, Jev disposition/reason, 의미 논증, hard/soft 구분 |
| split | 20+20, family 소속, 호출 가능 12+12, local-only 8+8, 실행 순서 |
| threshold grid / selection | 세 후보, equality, unrounded 비교, eligible gate, tie-break, 단일 값 잠금 |
| pass/fail gates | 아래 수치와 preflight failure/실행 FAIL 구분 |
| repetition | callable당 3회, 고정 순서; retry 0, concurrency 1 |
| call cap | discovery ≤1, System One ≤72, total attempts ≤73. 실패한 attempt도 포함 |
| budget cap | 총 USD 0.25 제안. 실행 전 계정 근거에 맞는 reservation 및 discovery 비용 처리 고정 |
| model binding | request channel 선택 규칙, 첫 유효 concrete binding, 이후 전건 동일성, unknown/missing 거부 |
| identity | semantic-source/projector/state/question/policy/adapter/protocol 및 threshold의 version binding |

예산은 V2의 실제 비용을 0으로 추정한 것이 아니라 이 synthetic 작업의 제안된 지출 상한이다. 모든 계획된 호출의 예약액과 discovery 예약액 합이 상한 이내임을 **호출 전** 입증해야 한다. 실제 가격·권한을 이번에 조회하지 않았다. 비용 미상은 0으로 해제하지 않으며 실패 시에도 예약 exposure·attempt를 보존한다. 예약을 입증할 수 없으면 preflight BLOCKED이며 1회 시험 호출로 가격을 탐색하지 않는다.

per-call deadline은 10초 제안으로 사전 고정한다. 실행 도중 늦은 응답을 수용하도록 늘리지 않는다. 운영 SLA나 production latency 목표가 검증됐다는 뜻은 아니다.

### 12.3 selection/validation 각각의 gate

| gate | PASS 조건 |
|---|---|
| semantic-source preflight | 모든 fixture source provenance와 projection 경로 설명 가능. gold가 input에 없고 forbidden field 전송 0 |
| route / local ownership | local-only 8/8 정확한 no-call과 이유·local signal. callable 12/12 호출 가능. local Q2 truth table error 0 |
| isolation | family별 Q1 wire 동일, Q1 정의 변경으로 local entry 비교 변동 0, entry missing이 Q1 global gate로 승격되는 오류 0 |
| provider/response | 계획한 36/36 on-time VALID, 정확히 Q1 Noul 하나, model/usage 검증, error/late/interrupted 0 |
| hard proposition | mismatch 0/30. negative false review 0/18, positive missed review 0/12 |
| hard status / disposition / reason | error 0/30. local 결과를 Jev reason에 섞거나 Q1 missing을 정상 응답으로 만드는 오류 0 |
| 반복 | 모든 callable fixture에서 disposition/reason crossing 0/12. hard gate crossing 0/10. soft raw p는 진단만 |
| burden | provider responses 36 중 REVIEW_REQUIRED ≤18, 정상 valid ABSTAIN=0. hard 요구 12건 + soft 최대 6건이라는 구성상 상한 |
| no-call 은폐 방지 | 사전 8개 외 callable의 semantic skip 0. 전체 context 20 중 local-only 8개를 분모와 함께 공개. 응답 실패로 분모 축소 금지 |
| identity / cap / budget | request 규칙 및 returned concrete 전건 일치, 사전 cap·예약 상한 위반 0 |

local-only를 provider response 분모에 섞지 않는다. 0/30 error는 독립 시장 표본 30건에서의 정확도 100% 주장이 아니다. hard 10개 중 isolation 변형도 있으므로 family 수를 별도 보고한다. 8/20 no-call이나 review ≤18/36은 의도한 fixture 구성의 경계이며 실제 시장의 허용 no-call 40%·review 50% 정책이 아니다.

V3 PASS는 **선택용 적격 후보 존재 + 단일 값 잠금 + 확인용 동일 gates + 전체 운영·identity·budget 통과**일 때만 가능하다. 미실행/사전 실패는 BLOCKED, 실행 후 acceptance 실패는 DIAGNOSTIC FAIL로 구분한다. 합격하더라도 production 유용성·계정 정책·Trial activation을 승인하지 않는다.

## 13. 제품 효과와 후속 구현으로 넘어갈 조건

| 질문 / 역할 | 기대 추가 가치 | 중복·실패 비용 | 재현성과 검증 한계 |
|---|---|---|---|
| Q1 KEEP | 여러 condition 의미와 승인된 전략 의도의 명시적 불일치를 빠르게 재확인 | local enum 비교만 남으면 중복. false review는 불필요한 사용자 확인을 만듦 | V2 selection 유망. 새 wire 및 production 표현력은 미검증 |
| Q2 STRUCTURE | 확인 구간을 실행 구간으로 잘못 표현하거나 반대로 표현하는 문제를 출처와 함께 설명 | local field가 같은 값의 복사본이면 추가 가치 없음. 이미 표시되는 local issue와 중복 통지 금지 | captured rule ID/role 제공 시 결정적. arbitrary text 비교까지 해결한 것은 아님 |
| Q3 LOCALIZE | 검토에 없는 정의·link를 발명하는 호출을 줄이고 부족 위치를 명시 | authored manifest 작성 비용, 지원 범위 축소와 no-call 증가. semantic skip을 숨기면 제품 품질이 악화 | 등록된 dependencies만 검사. 일반 자연어의 충분성 인증은 하지 않음 |

latency/cost는 provider 질문 수를 줄여 개선될 가능성이 있지만 Q1 call 자체는 남는다. 3 Noul→1 Noul이 비용 1/3 또는 지연 1/3을 뜻하지 않는다. local completeness 작성·검증 비용도 전체 비용이다. 추가 signal이 이미 local에서 확정되거나 Q1 false review가 이익보다 크다면 Jev를 유지할 이유가 없다.

다음 **구현 단계**로 넘어가려면 아래 조건을 모두 만족해야 한다. 이번에 어느 항목도 실행 승인으로 대체하지 않는다.

1. 이 architecture와 Q1-only supported scope가 다음 구현 작업 범위로 명시적으로 수락되어야 한다. 현재 요청은 design only다.
2. intended role/reference, Q1 전용 authored intent, definition manifest와 condition meaning의 authoritative 공급 경로를 source-contract 수준에서 지정한다. 현재 snapshot에 없으면 신규 capture version의 의무로 정의한다. arbitrary prose 추출이나 사후 backfill로 우회하지 않는다.
3. source-to-state mapping을 기술할 수 있고, local-only로 해결되지 않는 Q1 residual semantic value의 예와 반례가 존재해야 한다. 그 예가 없으면 구현을 늘리지 않고 no-call/질문 삭제 결정을 재검토한다.
4. 구현 범위는 versioned projector/question/policy/service 및 stored projection/cohort dispatch, offline fake 검증으로 제한한다. V1/V2 해석·artifact·threshold를 변경하지 않고 신규 family를 명시적으로 dispatch해야 한다. exact schema/SQL은 이번 산출물이 아니다.
5. local completeness가 문장 의미까지 완전히 검증한다는 허위 보증 없이 supported contract의 작성·검토 절차를 구체화한다. route/isolation/boolean·ID/오류/기준선 보존 검증 항목을 acceptance에 포함한다.

그 후 **Canary 실행 단계**는 별도다. exact synthetic protocol 사전 freeze, fake-only 검사, model/account/reservation 근거, 명시적인 synthetic 전송 실행 권한이 있어야 한다. V3 PASS 전 Trial은 계속 BLOCKED다.

V3 PASS 후에도 계정 retention/ZDR/billing·실제 minimized data 전송 권한, state와 model의 cohort binding, prospective 모집·기간·coverage/no-call·false review·운영 비용·성과 평가 기준의 사전 동결 및 별도 activation이 필요하다. Canary만으로 Trial V2를 freeze/activate하지 않는다. R5R Actual Evaluation과 Holdout은 별개이며 어떤 후속 단계의 묵시적 권한에도 포함되지 않는다.

## 14. 최종 결정 14개

| 요구 결정 | 최종 답 |
|---|---|
| 1. Q1 | **KEEP**. 명제 보존, Q1-only state에 맞춘 새 contract/version 필요. 검증 완료 선언 금지 |
| 2. Q2 | **STRUCTURE**. authoritative role/reference 기반 local 검사로 이전, Noul 제거 |
| 3. Q3 | **LOCALIZE**. 등록된 required definition/link completeness 검사, Noul 제거. arbitrary prose 충분성 보증 없음 |
| 4. 3-Noul 유지 | **NO**. 1 Noul이며 질문 수 자체는 제품 목표가 아님 |
| 5. same-request 유지 | **다문항 공동 요청 NO**. callable당 Q1-only System One 최대 1회, 별도 Q2/Q3 call 없음 |
| 6. question-scoped state | **필수**. instruction만으로 scope를 강제하지 않고 실제 wire에서 무관 영역 제외 |
| 7. structured semantic link | **필수, local-only**. 독립 source provenance·canonical version 필요, 없으면 지원 불가/no-call |
| 8. policy precedence | global safety/운영 유효성 유지; 독립적으로 성립한 local 또는 Q1 conflict 보존 → scope별 미검토 → 검토 범위의 추가 signal 없음. missing으로 타 scope conflict를 veto하지 않음 |
| 9. V2 역사적 지위 | **EXECUTED / DIAGNOSTIC FAIL / PRESERVED**, 연결·응답 contract는 V2 관측 범위 PASS |
| 10. V3 필요 여부 | **YES**, changed architecture의 새 acceptance 필요. **NOT EXECUTED** |
| 11. V3 fixtures | 새 synthetic 20+20, 각 12 callable+8 local-only. clear/positive/missing/mixed/trap/compound/soft/contamination 포함, family 단위 split |
| 12. V3 threshold 방법 | Q1 coarse 사전 grid → selection hard gates → deterministic tie-break → 한 값 잠금 → 새 validation. 실패 후 fitting 금지, **NOT FROZEN** |
| 13. V3 PASS 전 Trial | **BLOCKED**. PASS도 자동 activation 아님 |
| 14. 다음 구현 조건 | §13의 source provenance·supported scope·residual value·version dispatch·offline acceptance를 구체화하고 별도 구현 요청이 있을 때만 |

## 15. 작업 종료 상태

| 항목 | 상태 |
|---|---|
| V2 CANARY | **PRESERVED DIAGNOSTIC FAIL** |
| V2 REPORT / MODEL BINDING | **UNCHANGED** |
| NEW QUESTION/STATE ARCHITECTURE | **DESIGNED — ARCH C + D1** |
| SOURCE CODE / FRONTEND | **UNCHANGED / UNCHANGED** |
| RUNTIME / DB / MIGRATION | **UNCHANGED / 수정 없음 / 작성·실행 없음** |
| CANARY V3 | **NOT EXECUTED**, machine-readable JSON 생성 없음 |
| FINAL THRESHOLDS | **NOT FROZEN** |
| TRIAL | **BLOCKED**, activation/freeze 없음 |
| PROVIDER/API CALLS DURING THIS TASK | **0** |
| REAL STOCK DATA SENT | **0** |
| JEV_API_KEY / .env ACCESS | **0 / 0** |
| HOLDOUT ACCESS | **0** — content/search/metadata/hash/existence probe 모두 없음 |
| ACTUAL EVALUATION | **NOT EXECUTED** |
| R5R ACTUAL EVALUATION | **NOT EXECUTED** |

검증 범위는 저장된 기록·질문·projector·policy의 정적 대조, 설계 문서의 분모·경계·결정 정합성, 지정된 근거 19개 파일의 작성 전후 SHA-256 일치 확인이다. 기존 tracked/staged diff도 없음을 확인했다. 프로젝트 실행이나 새로운 canary/evaluation은 하지 않았다. 문서 작성 기준 commit은 첫머리의 HEAD이며 새 commit은 만들지 않았다. 이 문서가 과거 실행 report를 대체하지 않는다.
