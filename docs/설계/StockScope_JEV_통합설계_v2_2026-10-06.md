# StockScope JEV 통합설계 v2

작성일: 2026-10-06 (Asia/Seoul)  
조사 기준: 로컬 `main` / HEAD `893f2b96289a02f7cfce46b2a4ea7abb0d86326c`  
지위: **JEV의 authoritative design baseline. 구현 완료·모델 채택·운영 활성화 승인이 아니다.**

## 1. 결정 요약과 제품 목적

StockScope는 기존 분석·전략·위험·보유·검증 정보를 사용자가 빠르게 이해하고 판단하도록 돕는 제품이다. JEV의 성공은 문장 품질이나 자체 PASS가 아니라 기존 판단 대비 측정 가능한 추가 가치다.

**JEV의 단일 책임은 Decision Reviewer다. Phase 1에서는 Scanner가 이미 반환한 신규 진입 후보에 대해 “기존 후보 판단 유지 / 이번 후보는 재검토 필요 / 판단 유보”라는 별도 shadow 의견만 만든다.** 후보를 발굴·재정렬하거나 새 매매 계획을 만드는 Aggregator, Ranking Assistant, Plan Reviewer를 겸하지 않는다.

결정한 범위:

- 연결 지점은 **Scanner 완료 결과의 Prospective 캡처 이후 한 곳**이다. Holdings는 후속 후보로만 남긴다.
- Quant-only 입력으로 시작한다. NEWS.1, Event Evidence 원문·파생 사건 판단, macro reference, 계좌·보유 정보는 Phase 1 입력에서 제외한다.
- 기존 Risk Gate·NO_TRADE·순위·가격·계획·정책은 그대로 baseline의 결정 권한이다.
- confidence, AI 점수, 동적 가중치, 국면별 AI 비중을 만들지 않는다.
- `NEXT-6E-R5R-JEV`는 **R5R Evaluation**의 과거 단계 별칭으로 분리한다. AI JEV의 성능 평가가 아니다.
- 실행 흐름은 **Design Freeze → Shadow Implementation → Evaluation → Adoption Decision** 네 묶음이다.

이 문서가 기존 [JEV Integration Concept](../StockScope_JEV_INTEGRATION_CONCEPT.md)을 JEV 설계 authority에서 대체한다. 원문은 이번에 수정·이동·삭제하지 않는다. 정리 분류와 실행 조건은 [Docs 정리계획](StockScope_DOCS_정리계획_2026-10-06.md)에 둔다.

## 2. 조사 범위와 authoritative source

판단 순서는 현재 main 코드 → frozen contract/binding → 현재 통합 baseline → 최신 구현 문서 → 과거 JEV → 기타 역사 설계다. 코드가 계약과 다를 경우 조용히 계약을 바꾸는 근거로 쓰지 않고 구체적인 차이를 기록한다.

이번에는 backend·frontend·양측 tests·tools의 소스, docs의 본문/결정/계약/참조 관계와 DOCX의 문단을 조사했다. 실제 테스트는 `backend/tests`, `frontend/tests`에 있고 machine artifact는 `docs/contracts`, `docs/bindings`, `docs/fixtures`, `docs/reviews`에 있다. 별도 최상위 tests/contracts가 있다고 가정하지 않는다.

**실행 경계:** 애플리케이션·테스트·evaluator·binding CLI·Reference Adequacy·JEV를 실행하지 않았다. DEV 원본, runtime DB, 공급자 API를 열지 않았다. Holdout의 내용·검색·metadata·hash·존재 확인을 수행하지 않았다. R5R 계약/기존 binding에 이미 적힌 identity와 구조 정보만 읽었으며 실제 T/L/S·후보 상태·Common-N 결과를 계산하거나 추정하지 않았다. CI의 과거 성공은 아래 구현 문서의 기록으로 인용하며 이번 재실행 결과로 주장하지 않는다.

| 근거 | 현재 역할 |
| --- | --- |
| [Master Architecture](../StockScope_MASTER_ARCHITECTURE_vNext.md) | 도메인·저장 소유권, 제품 경계. 2026-09-27의 미구현 표현을 현재 상태로 재사용하지 않음 |
| [Implementation Baseline](../StockScope_IMPLEMENTATION_BASELINE_vNext.md) | Frozen Tracking·완료 결과 불변, migration/검증/명시적 적용 규칙 |
| [Roadmap](../StockScope_DEVELOPMENT_ROADMAP_vNext.md) | 의존성과 조건부 장기 목표. 실시간 상태표가 아님 |
| [R5R 통합 기준](StockScope_NEXT6E_R5R_통합설계기준_2026-10-05.md) | 계산·claim·lineage. §35/39/40의 갱신 상태와 앞부분 과거 상태를 구별 |
| [R5R 정책](StockScope_NEXT6E_R5R_초기정책결정_2026-10-05.md) | T/L/S 모두 gate, 내부 reference 사용범위와 고정 tolerance |
| [R5R 구현/바인딩](StockScope_NEXT6E_R5R_구현및바인딩_2026-10-06.md) | evaluator 구현, DEV binding, G0~G4 PASS 및 평가 미실행 |

### 2.1 R5R frozen 상태 — 변경하지 않는 계약

| Artifact | 의미 / 고정 identity |
| --- | --- |
| [Method V2](../contracts/NEXT6E_S6A_R5R_METHOD_CONTRACT_V2.json) | semantic `5519ad12a6e3dafb30041935c6ead2869d35148aadb2a6bab8443521ea8310c4` |
| [Policy V1](../contracts/NEXT6E_S6B_R5R_POLICY_V1.json) | semantic `8934d99d808b8c7afa837fb71601695457154747fbcafd592da44b337343bc22` |
| [CandidateDomain V1](../contracts/NEXT6E_S6A_R5R_CANDIDATE_DOMAIN_V1.json) | approved 18 nominal fractions, 정수 mapping/collision |
| [Window V1](../contracts/NEXT6E_S6A_R5R_WINDOW_PROFILE_V1.json) | 공통 backward window `w(n)=ceil(n/10)`, h=1/5/10 |
| [Evaluation Binding V1](../bindings/NEXT6E_R5R_EVALUATION_BINDING_V1.json) | `R5RBIND-b27cf5c12ab37aac`; `metrics_computed=false`, `reference_adequacy_evaluated=false` |
| [Deterministic Review V2](../reviews/NEXT6E_S6A_R5R_DETERMINISTIC_REVIEW_RESULT_V2.json) | 계약 모호성 해소 PASS. 기록 당시 G1/G3/G4 상태는 historical snapshot |
| [기본 fixtures](../fixtures/NEXT6E_S6A_R5R_DETERMINISTIC_FIXTURES_V1.json), [BR1 fixtures](../fixtures/NEXT6E_S6A_R5R_MUR3_BR1_TARGETED_FIXTURES_V1.json) | 합성·결정론적 검산 자산. DEV 성과 증거가 아님 |

현재 effective state는 **R5R-G0/G1/G2/G3/G4 모두 PASS**, Reference Adequacy는 **AUTHORIZED / NOT EXECUTED**다. 이 과거 단계의 실행 가능 상태가 이번 문서 작업의 실행 허가는 아니다.

`r5r_evaluator.py`의 exact Fraction, all-horizons AND / all-metrics AND / all-later, latest 포함, zero-MAD fail-close를 유지한다. 고정 tolerance는 `tau_T=1/10`, `tau_L=1/2`, `tau_S=1/4`다. 결과에 따른 완화·window 변경·anchor 변경을 하지 않는다.

실제 직렬화 명칭은 candidate `SUPPORTED_WITHIN_POLICY / EXCEEDS_POLICY / BLOCKED`, overall `SUPPORTED_WITHIN_POLICY / NOT_SUPPORTED / BLOCKED`다. 과거 narrative의 “SUPPORTED”는 축약이지 새 enum이 아니다. 현재 이 중 어떤 DEV 결과가 나오는지는 **알 수 없다**.

Binding의 `HISTORICAL_TIME_NOT_PROVEN`과 `REFERENCE_RESEARCH_ONLY`는 유지한다. binding 완료는 과거 시점 적합성이나 투자성과 입증이 아니다. frozen JSON 내부 과거 상태 문자열을 현재 PASS로 고쳐 hash를 바꾸지 않는다.

## 3. 현재 architecture와 JEV 연결 위치

| Owner / 직접 확인한 소스 | 실제 책임과 JEV 경계 |
| --- | --- |
| [Scanner](../../backend/app/backtest/scanner.py), [candidate priority](../../backend/app/backtest/candidate_priority.py) | EOD 자료·유동성·전략/Risk로 후보 생성. 현재 version **0.21.3.9**, manifest ID **SS-SCANNER-0.21.3.9-cf48adb0d19e7953**. 최종 순위는 현재 조건→Risk→진입 근접도→전략 적합도와 동률 규칙. 과거 근거는 순위 점수로 합산하지 않음 |
| [Strategy](../../backend/app/strategy/engine.py), [Risk](../../backend/app/risk/engine.py) | 10전략 적합도·Pool·독립 Risk Gate와 구조/ATR 가격 가이드. JEV가 재계산하거나 점수로 차단을 상쇄하지 않음 |
| [Historical Replay](../../backend/app/simulation/validation_replay.py), [Validation catalog](../../backend/app/simulation/validation_catalog.py) | 당시 후보 snapshot/hash, 날짜별 재생과 입력 식별. AI 결과를 과거 원본에 덮어쓰지 않음 |
| [Execution](../../backend/app/simulation/execution_engine.py), [Execution catalog](../../backend/app/simulation/execution_catalog.py) | D까지 신호, D+1 이후 가상 실행. 기존 최대 20거래일·왕복 비용 0%, 정책 불일치·CENSORED 처리. JEV 전용 체결 엔진을 만들지 않음 |
| [Prospective service](../../backend/app/prospective/service.py), [catalog](../../backend/app/prospective/catalog.py), [evaluation](../../backend/app/prospective/evaluation.py) | 사후 사용자 선택 전 `candidates + more_candidates`를 보존·중복 제거. 5/10/20일 관찰과 별도 실행 결과. AI 의견 저장/paired comparison은 아직 없음 |
| [Holdings Decision](../../backend/app/holdings/decision_support.py), [analysis](../../backend/app/holdings/analysis.py), [management](../../backend/app/holdings/management.py) | 로컬 EOD 분석·포지션·계획 version을 기반으로 판단, stale/ADD/손절 완화 차단, 명시적 적용. 계좌·계획을 JEV 입력/쓰기 경로로 연결하지 않음 |
| [Recovery](../../backend/app/holdings/recovery.py) | 수동 검토 lifecycle과 thesis/action 기록. 회복확률·자동 물타기·자동 종료 기능으로 해석하지 않음 |
| [Watch](../../backend/app/watch/coordinator.py), [policy](../../backend/app/watch/policy.py) | 서버 시세 소비·confirmation·알림. 현재 production policy `enabled=False`. JEV가 감시 활성화·confirmation을 대신하지 않음 |
| [Event Evidence](../../backend/app/event_evidence/product.py), [as-of reader](../../backend/app/event_evidence/asof.py), [source policy](../../backend/app/event_evidence/policy.py) | source 권한·시점·중복/정정·품질·참고 제품 통합. 구현 존재는 실 corpus 증분 가치나 AI 사용 승인이 아님 |
| [Horizon](../../backend/app/horizon.py) | LEGACY_UNSPECIFIED, SHORT/MEDIUM/LONG 문맥. 명시 Horizon 수치 정책은 EVALUATION_PENDING. JEV가 기간을 임의 지정하지 않음 |
| [Strategy Governance](../../backend/app/simulation/strategy_governance.py), [selection policy](../../backend/app/strategy/production_selection_policy.py) | 근거→제안→승인→운영 설정의 명시적 활성화·run pin. 현 P5가 AI reviewer 배포까지 이미 승인한다는 뜻이 아님 |
| [Scanner API](../../backend/app/api/backtest.py), [Scanner UI](../../frontend/src/components/ScannerPanel.tsx), [Prospective UI](../../frontend/src/components/ProspectiveEvaluationPanel.tsx) | API 완료 흐름에 baseline capture와 별도 reference capture가 존재. 기존 화면/응답에는 JEV 비교가 구현되지 않음 |

Scanner의 fast path는 selector 상위 3개를 현재 조건·Risk로 재평가한다. JEV는 제공되지 않은 전략 전체의 충돌을 해소했다고 주장할 수 없다. `historical_evidence`가 없어도 현재 Scanner 완료 상태가 유지될 수 있으므로, JEV에도 3년 근거 존재를 필수로 강제하지 않는다.

Phase 1의 저장 owner는 **Simulation/Prospective 평가 영역**이다. 향후 작은 별도 review 기록과 비교 report를 추가하며 Tracking·Holdings 원본이나 기존 완료 Validation run은 수정하지 않는다. 새 DB·별도 서버·전 시스템 DecisionProvider 계층을 선행 구축하지 않는다.

## 4. Phase 1 범위와 제외 이유

**대상 모집단:** protocol에 사전 고정된 시장·기간·정책의 canonical COMPLETE Scanner 캡처에 실제 반환된 모든 후보. 그중 신규 진입 `action=ENTRY_CANDIDATE`, 기존 Risk 사용 가능, EOD/as-of identity가 증명된 후보만 모델 호출 대상으로 한다. 해당 조건의 판정은 adapter가 현재 owner 필드로 수행하며 새로운 점수 임계값을 만들지 않는다.

- `candidates`뿐 아니라 `more_candidates`도 원래 bucket/rank를 보존한다.
- WAIT/NO_TRADE/Risk 차단, 미지원 Horizon은 OUT_OF_SCOPE로 기록하고 진입으로 승격하지 않는다.
- 부분·실패·취소 캡처, duplicate, 저장 실패, 미호출, timeout도 모집 흐름에서 별도 수로 남긴다.
- 전체 시장의 사전 pruning 후보나 반환되지 않은 actionable 전체가 표본이라는 주장은 금지한다.
- 동일 canonical capture/candidate의 화면 재진입·Embedded Scanner·재시도는 새 독립 표본이 아니다.
- source identity가 부족한 legacy replay는 UNKNOWN/제외이며 최신 입력으로 채워 넣지 않는다.

| 검토한 지점 | 결정 / 이유 |
| --- | --- |
| Scanner 최종 반환 후보 | **채택**. baseline snapshot과 후보별 execution/prospective outcome 연결이 가장 짧음 |
| Holdings 판단 뒤 / 계획 적용 전 | 보류. 사용자 선택 편향·계획/수량 version·행동 반사실 평가가 추가로 필요 |
| 상세 종목·Recovery·Watch·Horizon | 보류. 입력 경로와 미승인 정책을 늘리지 않음 |
| Event/macro 충돌 검토 | 보류. AI/source 사용권·시간 적합성·reference 사용범위가 별도 조건 |

## 5. 하지 않는 일과 권한

JEV는 신호·Risk·가격·수익률·새 전략·macro 안정성을 직접 계산하지 않는다. 최종 rank/score/action을 수정하지 않고 다른 종목을 대체 추천하지 않는다.

`AUTO_BUY`, `AUTO_SELL`, `AUTO_PLAN_CHANGE`, `AUTO_STOP_RELAXATION` 권한은 없다. 실제 증권사 주문은 제품의 기존 금지 경계다. JEV의 “유지”는 안전 승인이나 사용자 매수 지시가 아니다.

Phase 1 결과는 연구용 shadow opinion / review recommendation / comparison evidence다. 운영 후보 카드에 자동 노출하거나 사용자 계획으로 적용하지 않는다. 채택 후에도 최초 허용 범위는 명시적으로 켠 **보조 검토 표시**이며 자동 필터링은 별도 설계 변경이다.

## 6. Input contract — JEV_SCANNER_REVIEW_INPUT_V1

아래는 **새 구현이 따라야 할 논리 계약**이다. 기존 API 필드가 모두 이 형태로 존재한다는 뜻은 아니다. adapter는 저장 baseline에서 allowlist projection을 만들며 모델은 데이터 조회 tool을 갖지 않는다.

| 필드 | 필요 내용 / 출처 |
| --- | --- |
| `schema_version, request_id, evaluation_protocol_id/hash` | 입력 계약·단일 요청·사전 protocol 식별 |
| `source_kind, source_ref, candidate_ref` | HISTORICAL_REPLAY 또는 PROSPECTIVE_CAPTURE, run/canonical capture·candidate key·원본 snapshot hash |
| `as_of` | signal date, 실제 source available/captured 시각, cutoff, EOD 구분, 시간 증명 상태. 역사 신호일과 오늘 생성 시각을 혼합하지 않음 |
| `baseline_identity` | Scanner version/baseline ID, input fingerprint의 scheme·범위, strategy version/definition hash, 실제 SelectionPolicyPin 및 exit policy token, Horizon 정책 |
| `baseline_decision` | 원래 action/state/tier/rank/bucket, strategy, conditions/reasons/unmet, Risk 상태·blockers, 기존 entry/risk guide. 합산 “Scanner 확률” 없음 |
| `evidence_items[]` | `evidence_id, owner, field_path, value, source_ref/hash, available_at, limitations, source_policy_ref`. 기존 구조화 quant 사실만 사용 |
| `allowed_decisions` | PASS_THROUGH / REVIEW_REQUIRED / ABSTAIN |
| `missing_evidence[], limitations[]` | 확인 불가능·누락·현재 지원범위. 추정 보충 금지 |
| `input_hash, adapter_version` | 실제 전송 projection의 canonical JSON identity. 원본 hash와 별도 보존 |

필수 identity·Risk 상태·핵심 조건이 없으면 INSUFFICIENT_EVIDENCE다. optional historical evidence가 없다는 이유만으로 모든 후보를 탈락시키지 않는다. Phase 1은 현재 quant 조건만 검토하도록 고정하고 `historical_evidence`의 성과 수치·미래 outcome은 모델 입력에서 제외한다. 기존 최종 결과 snapshot 자체는 baseline 증거로 별도 보존한다.

원시 시장 데이터를 복사해 모델에게 같은 지표를 재계산시키지 않는다. 종목명·날짜 등 식별자도 필요한 최소 범위로 전송하며 source 권한이 외부 AI 전송/파생정보 보존을 허용하는지 model/provider 선정 시 확인한다. 권한이 증명되지 않으면 그 자료를 전송하지 않고 해당 pilot은 시작하지 않는다. 기존 프로그램 내부 이용권을 외부 모델 전송권으로 간주하지 않는다.

## 7. Structured output contract — JEV_SCANNER_REVIEW_OUTPUT_V1

### 7.1 모델 응답과 서버 envelope 분리

모델이 반환할 필드는 다음 네 가지로 제한한다. 정의되지 않은 필드·행동은 reject한다.

| 모델 필드 | 타입 / 의미 |
| --- | --- |
| `decision` | `PASS_THROUGH \| REVIEW_REQUIRED \| ABSTAIN` |
| `abstain_reason` | ABSTAIN이면 `INSUFFICIENT_EVIDENCE \| CONFLICT_UNRESOLVED \| OUT_OF_SCOPE \| STALE_INPUT`; 그 외 null |
| `supporting_reasons[]` | 객체 `{code, evidence_refs[], explanation}`; baseline 유지에 유리한 근거 |
| `opposing_reasons[]` | 같은 형태; baseline 유지에 반대되는 근거 |

`code`는 `CONDITION_ALIGNMENT / CONDITION_CONFLICT / ENTRY_CONTEXT_CONFLICT / RISK_CAUTION / EVIDENCE_LIMITATION`으로 제한한다. 각 reason의 evidence_refs는 입력 evidence_id의 비어 있지 않은 부분집합이어야 한다. 두 reason 배열을 모두 허용하며 없는 쪽은 빈 배열이다. 설명은 간결한 사실 해석이며 새 가격·확률·매매 명령을 만들 수 없다. 위험 관련 근거는 이미 입력된 owner 상태에만 연결한다.

PASS_THROUGH는 supporting reason 1개 이상, REVIEW_REQUIRED는 opposing reason 1개 이상이 필요하다. ABSTAIN은 이유가 필수이고 모델 이유 목록이 비어 있어도 된다. 서로 반대되는 해석을 입력 근거로 해소할 수 없으면 CONFLICT_UNRESOLVED로 유보한다. 단순 구조 검증이 문장의 경제적 진실성을 보증하지 않으므로 근거 불일치/환각은 품질 오류로 별도 검토한다.

서버가 붙이는 envelope:

- `review_id, request_id, input_hash, source_ref, candidate_ref`
- `provider, model_id, model_revision, prompt_version/hash, output_contract_version, adapter_version, generation_settings`
- `requested_at, completed_at, deadline, status, failure_code, latency_ms, usage/cost` (공급자가 확인하지 못한 비용은 null)
- `raw_response_ref/hash`와 검증된 위 네 필드 또는 오류 결과

모델이 스스로 적은 identity를 신뢰하지 않는다. 모델 revision pin이 확인되지 않는 응답은 같은 cohort에 합치지 않는다. confidence와 risk_flags 별도 배열은 제외한다. confidence는 보정된 확률이 아니며 위험 사유는 opposing reasons의 owner evidence 참조로 충분하다.

### 7.2 Abstain과 기술적 실패

서버 검증·네트워크·schema 오류는 `status=ERROR, decision=ABSTAIN, abstain_reason=MODEL_ERROR`로 정규화한다. MODEL_ERROR는 서버 예약 사유이며 모델 자가 판정이 아니다. 미호출은 `status=SKIPPED`, 늦은 응답은 `status=LATE`다. 모델이 정상적으로 유보한 경우는 `status=VALID`이며 기술 오류와 집계에서 분리한다.

입력 hash/source revision이 바뀌었거나 deadline을 넘긴 의견은 당시 유효한 판단으로 사용하지 않는다. baseline이 미지원·차단인 경우의 fallback은 그 차단 상태 자체다.

## 8. Shadow 실행·저장·실패 처리

Shadow 호출은 기본 비활성이다. 승인된 trial protocol과 model 설정을 사용자가 명시적으로 활성화한 경우에만 시작한다. 조회·앱 시작·JEV 문서 존재만으로 호출을 시작하지 않는다.

미래 구현 흐름:

1. 기존 Scanner가 기존 정책 pin으로 완료한다.
2. 기존 Prospective가 canonical capture와 후보 snapshot을 보존한다. capture가 평가 가능하지 않으면 JEV는 미호출 사유만 기록한다.
3. 별도 review job이 protocol 모집단과 input allowlist를 확인하고 immutable request를 저장한다.
4. baseline 반환은 기다리지 않는다. 모델 응답은 단일 요청에 귀속해 검증하고 Simulation/Prospective 영역에 별도 저장한다.
5. 아직 결과를 모르는 시점의 유효한 의견을 동결한다. D+1 실행 창이 시작된 뒤 생성/도착한 의견은 prospective 효능 평가에서 제외하고 LATE로 집계한다.
6. 이후 기존 outcome engine이 만든 결과를 읽어 새 comparison report에 join한다. 원본 baseline/review/완료 run을 수정하지 않는다.

**현재 API 흐름에 capture가 있다는 사실과 새 review job/outbox가 구현돼 있다는 사실을 구분한다.** 후속 구현은 기존 `try_finalize_scanner_capture` 완료 뒤 연결점과 idempotency를 추가한다. 기준 키는 canonical capture 또는 historical run + candidate snapshot hash + protocol + input/model/prompt/contract identity다.

Phase 1은 요청당 모델 호출 한 번을 기본으로 한다. 자동 재시도로 유리한 답을 선택하지 않는다. 수동 재실행은 새 attempt로 남기며 최초 유효 답을 소급 교체하지 않는다. 재시도 정책 변경은 protocol version 변경이다.

timeout·rate limit·키 누락·비용 초과·schema 불일치·provider 변경·저장 실패 시 기존 StockScope 결과를 그대로 제공한다. 저장에 실패한 작업은 성공으로 세지 않고 capture 대비 review 누락 수로 드러낸다. 재시작 시 PENDING을 조용히 재호출하지 않고 INTERRUPTED로 정리한다. record 쓰기는 additive이고 baseline capture transaction과 AI 네트워크 호출을 한 transaction으로 묶지 않는다.

기존 UI에서는 이 단계의 JEV 결과가 판단으로 작동하지 않는다. 향후 비교 화면은 baseline/review/disagreement/outcome/미평가 이유를 한 행에 보여주고 production 화면과 구분한다.

## 9. Baseline comparison의 정확한 의미

비교 실험은 **동일 후보를 그대로 유지한 baseline 대 “재검토 필요 후보를 이번 가상 기회에서 제외하는” 단일 shadow 가설**이다. 실제 Scanner 후보는 제외하지 않는다. REVIEW_REQUIRED의 사유 효과를 측정하기 위한 offline comparison rule을 `JEV_DEFER_THIS_OPPORTUNITY_V1`로 고정한다.

| 구분 | 정의 |
| --- | --- |
| Baseline | 기존 후보 action·rank·entry/stop/target·정책 및 기존 엔진 결과 |
| JEV shadow opinion | PASS_THROUGH / REVIEW_REQUIRED / ABSTAIN 및 근거 |
| Disagreement | 범위 내 ENTRY_CANDIDATE에 대한 유효 REVIEW_REQUIRED |
| Shadow comparison arm | REVIEW_REQUIRED만 해당 가상 기회 skip, PASS_THROUGH·ABSTAIN·모델 오류·미호출은 baseline 그대로 |
| Historical outcome | 과거 as-of 후보의 재생/identity와 그 후보에 연결된 과거 가상 outcome |
| Execution outcome | 동일 entry/exit policy·기간·비용에서의 가상 체결/종료/미체결/CENSORED |
| Prospective outcome | frozen prompt/model로 미래 발생 전에 기록한 의견과 이후 성숙 관찰·가상 실행 결과 |

skip은 다음날 더 싸게 재진입, 대체 종목 편입, 자본 재배치가 아니다. 보유기간·가격·청산 정책을 바꾸지 않으므로 기존 후보별 outcome을 재사용할 수 있다. reviewer의 의견과 skip 가설의 유효성은 구분하며, 좋은 offline skip 결과가 사용자의 실제 검토 행동 개선을 증명하지는 않는다.

## 10. 평가 metrics — 현재 계산 가능한 것만

JEV 비교 집계는 새로 필요하지만 아래 원자료는 기존 Execution/Prospective 구조에 있다. 포트폴리오 거래장을 새로 만들어야 하는 Sharpe·portfolio MDD·risk-adjusted alpha, holdings quality, recovery 성공률, 뉴스 예측확률은 Phase 1 채택 지표에서 제외한다.

동일 cohort에서 호출 대상 자격과 baseline outcome identity가 확인된 closed virtual trade의 net return을 `r_i`, 유효 REVIEW_REQUIRED 여부를 `d_i∈{0,1}`로 둔다. C에는 유보·오류·미호출 후보도 포함하며 이들은 `d_i=0`으로 baseline을 따른다. review가 없다는 이유로 비교 분모에서 제거하지 않는다. 실패를 숨기지 않도록 전체 호출 대상에 대한 운영 성공률도 따로 집계한다.

| 지표 | 고정 정의 / 분모 / 사용 |
| --- | --- |
| **기회당 순증분 가상수익 Δ** | CLOSED 결과를 가진 동일 비교 가능 후보 집합 C에서 `Σ(-d_i × r_i)/count(C)`. baseline은 `Σr_i/count(C)`, shadow는 `Σ((1-d_i)r_i)/count(C)`. 1순위 효과 지표. 포트폴리오 수익률로 부르지 않음 |
| 회피 손실 / 놓친 이익 | C의 disagreement에서 각각 `Σ max(-r_i,0)`, `Σ max(r_i,0)`. 전자는 bad candidate 감소의 크기, 후자는 false-positive 방어 의견의 비용. 차이가 Δ의 분자 |
| 손실 후보 수·비율 | baseline `r_i<0` 건수/count(C), shadow `d_i=0 & r_i<0` 건수/count(C). 별도로 유지 후보 내 손실률도 표시해 “전부 제외하면 개선” 착시 방지 |
| disagreement 정밀도 | C 중 `d_i=1`에서 음수 r 비율. disagreement 0이면 N/A, 0%나 성공으로 표시하지 않음 |
| 관찰 보조 지표 | prospective `return_5d/10d/20d, mae_pct, mfe_pct, stop_touched, target1_touched`. 관찰 윈도·기준가격·성숙도별 표시. stop touch는 실제 체결 손절이 아님 |
| coverage / 운용 부담 | 전체 capture→반환→scope eligible→호출→VALID→비유보→제때 도착→outcome join→CLOSED 수, REVIEW_REQUIRED 비율, 유보/오류/late/누락, 지연·비용 |

CENSORED, NOT_EXECUTED, NO_ENTRY_DATA, RISK_PLAN_BLOCKED, FAILED, 데이터 부족·policy mismatch는 각 원본 상태로 분리한다. CENSORED를 0수익으로 채우지 않는다. skip arm의 가상 미참여 0은 **비교 규칙의 값**이며 미성숙 outcome을 0으로 대체한 것이 아니다. CLOSED 기준 C와 5/10/20일 관찰 기준 분모를 섞지 않는다. C가 비면 Δ/손실률은 N/A이며 채택을 보류한다. 유지 후보가 0이면 유지 후보 손실률도 N/A다.

동일 ticker/date의 반복 캡처는 protocol의 사전 규칙으로 하나의 주 분석 단위로 정한다. 새 model/prompt를 동일 후보에 돌린 경우 paired variant이며 독립 표본이 아니다. 일자별 paired Δ, 표본 수, 시장/전략별 편중을 함께 보고한다. 신뢰구간이 필요하면 상관 구조에 맞는 방법을 실행 전에 고정하고 사후 유리한 방법을 선택하지 않는다.

기존 VAL.2의 20일·0% 결과는 진단 비교로 유지한다. 제품 채택 근거에는 현재 Prospective protocol이 지원하는 fee/tax/slippage 및 비용 값을 결과 확인 전에 고정한 별도 run이 필요하다. 임의의 실거래 비용 숫자나 현실 체결 정확성을 이 설계에서 발명하지 않는다.

## 11. 최소 평가 경로와 채택 / 거절 기준

### 11.1 가장 짧은 경로

작은 synthetic input으로 형식·권한·fallback을 검증한 뒤, 허용된 Development 역사 표본에서 한 model/prompt와 한 skip 가설만 비교한다. 결과가 설명이나 비용 측면에서 이미 무가치하면 중단한다. 가능성이 있으면 **새로 시작하는 Prospective shadow 기간**에서 같은 계약을 동결해 검증한다. 역사 재생에 넣는 현대 모델은 당시 이후의 정보를 학습했을 수 있으므로 Historical 성과만으로 채택하지 않는다.

현재 `ProspectiveService.create_protocol`은 development와 holdout 날짜, 최소 20거래일 purge를 요구한다. 따라서 기존 API를 호출하면 Holdout 잠금과 무관한 “DEV-only 실행”이 된다고 가정하면 안 된다. 이번에는 호출하지 않는다. 다음 구현에서 미래 prospective 평가 구간을 명시적으로 정하고 기존 데이터 잠금을 침범하지 않는 실행 scope를 지원/검증해야 한다. 기존 잠긴 Holdout을 새 이름으로 재사용하지 않는다. 새로운 시간 분리 평가 구간 지정도 기존 Holdout 열람 허가가 아니다.

### 11.2 사전 protocol의 최소 내용

Shadow Implementation의 완료 조건 안에서 한 protocol에 다음을 outcome 열람 전에 고정한다. 추가 연구 단계나 여러 task spec을 만들 필요는 없다.

- 실제 provider/model revision·prompt·source 전송/보존 권한과 적용 시장/전략/Horizon.
- Development/미래 prospective 기간, candidate 중복 규칙, cutoff/deadline·최대 관찰기간·purge.
- 위 metrics·분모·비교 정책·비용과 기술 오류/누락 처리.
- 모집 종료일 또는 최대 모집량, 최소 성숙 후보 수와 최소 disagreement 수, 허용 오류/유보/검토 부담·호출 예산.
- 프로젝트 소유자의 trial protocol 승인 기록. 결과를 보기 전에 결정하며 R5R tolerance와 무관하다.

이 수치들은 현재 승인된 JEV 정책이 없으므로 미확정이다. 미확정 상태에서도 synthetic adapter 검증은 가능하지만 유효성/채택 판정을 시작하지 않는다. 숫자를 채우기 위해 R5R passing N이나 DEV T/L/S를 사용하지 않는다. 기존 Prospective의 `SAMPLE_SIZE_POLICY_UNDEFINED`를 AI가 PASS로 덮지 않는다.

### 11.3 단순 판정

| 판정 | 조건 |
| --- | --- |
| **제한적 채택 검토** | 사전 표본/성숙/운영 기준 충족, prospective Δ>0, 놓친 이익을 포함한 회피 손실의 순효과가 양수, 유지 후보 손실률 악화 없음, 날짜/특정 종목 편중과 비용에 결론이 전적으로 의존하지 않음, 금지 권한/누수 위반 없음 |
| **거절** | 충분한 사전 평가 범위에서 Δ≤0, 불필요한 재검토로 이익 손실이 회피 손실 이상, 검토 부담·비용이 승인 범위를 초과. 문장이 좋아도 채택하지 않음 |
| **보류** | 표본/불일치 부족, 시점/권한/identity 미증명, 과다 유보·실패, 미성숙, 비용/운영 기준 미정. 효과 없음과 측정 불능을 구분 |
| **즉시 중단** | Risk 우회, 자동 계획/주문 변경, 정보 누수, 잘못된 source 전송 등 hard boundary 위반 |

제한적 채택 검토는 자동 배포가 아니다. 프로젝트 소유자가 근거·비용·사용 범위를 보고 승인한다. 실제 “더 빠른 사용자 판단”은 제한적 보조 표시 UAT에서 혼동·검토 동선으로 확인하며 가상수익으로 사용자 행동의 인과효과를 주장하지 않는다. Threshold/prompt를 결과에 맞춰 바꾸면 새 protocol과 아직 보지 않은 미래 기간에서 재평가한다.

## 12. R5R과 JEV의 명칭·입력 관계

| 구분 | R5R Evaluation | JEV Decision Reviewer Evaluation |
| --- | --- | --- |
| 권장 단계명 | **NEXT-6E-R5R-EVALUATION** | **JEV-REVIEWER-EVALUATION** |
| 과거 별칭 | NEXT-6E-R5R-JEV | 2026-09-28 AI Decision Model 후보 JEV |
| 질문 | 고정 observed path의 empirical reference가 승인 drift 범위에 있는가? | reviewer가 baseline 후보 판단에 추가 가치를 주는가? |
| 실행 주체 | pure deterministic R5R evaluator | pin된 AI adapter + 기존 outcome engine + 새 비교 report |
| 입력 | Method V2 + Policy V1 + frozen DEV binding/rows | frozen Scanner 판단 projection |
| 출력 | T/L/S, per-anchor status, OBSERVED_PATH_COMMON_N, overall status | structured review, disagreement, 순증분 효과/실패/비용 |
| 현재 상태 | 구현·binding 완료 / 실평가 미실행 | 설계 v2 / adapter·shadow·성능 평가 미구현 |

**혼동은 실제로 존재한다.** R5R 구현 문서 §16~18과 통합 기준 §41이 JEV를 R5R 첫 계산 단계로 부른다. 앞으로 새 작업에서는 위 이름을 사용하되 기존 frozen `stage_id`, hash, historical 기록은 바꾸지 않는다. narrative 이름 정정과 cross-link는 다음 docs cleanup 작업에서 한다.

Phase 1은 macro 입력을 쓰지 않으므로 **R5R Evaluation 성공을 JEV shadow 착수의 불필요한 선행 조건으로 만들지 않는다.** R5R의 다음 실평가는 별도 승인된 실행 작업이다.

향후 macro reference 입력을 검토할 때:

| R5R 상태 | 허용 해석 / 처리 |
| --- | --- |
| NOT_EVALUATED | 안정성 evidence 없음. reference 재사용 적격으로 표시하지 않음 |
| BLOCKED | identity/계산/정책 문제. 해당 reference 제외, 다른 입력만의 별도 승인 cohort 또는 abstain |
| NOT_SUPPORTED | 현재 path/policy에서 재사용 근거 미충족. 정상 부정 결과, tolerance 완화 금지 |
| SUPPORTED_WITHIN_POLICY | **그 path·window·grid·정책 범위의 empirical stability evidence만**. 미래 수익확률·전략/Risk 승인으로 승격 금지 |

R5R status는 필요할 경우 **evidence-quality prerequisite**이지 reviewer의 가중 점수가 아니다. SUPPORTED여도 source 사용권, as-of 증명, consumer 사용범위가 별도로 필요하다. 현재 policy의 STRATEGY_INPUT/RISK_GATE/PRODUCTION_POLICY 금지는 JEV를 경유해 우회할 수 없다. 전체 DEV observed suffix 결과를 과거 D 시점에 알고 있었던 signal로 제공하지 않는다. 단순 참고와 실제 후보 판단을 바꾸는 입력은 별도 consumer 변경 검토 대상이다.

## 13. Risk / Holdings / Event boundary

Risk Gate를 존중한다는 것은 가중치를 크게 주는 일이 아니다. 모델 호출 전 기존 차단 결과를 보존하고 출력 검증에서도 금지 행동을 거부한다. JEV PASS_THROUGH가 Risk PASS로 바뀌는 경로는 없다.

Holdings의 quantity·analysis revision·plan version·stale·stop loosening 차단은 기존 owner가 관리한다. 이번에는 Holdings reviewer를 만들지 않으므로 HOLD/ADD/REDUCE/EXIT·수량/가격 변경 필드는 출력 계약에도 없다. Recovery ADD_REVIEW는 추가매수 허가가 아니며 Watch 알림도 계획 변경 권한이 아니다.

현재 NEWS.1과 P6 Naver/OpenDART 정책의 AI_TRANSFORM/PREDICTION_INPUT은 허용되지 않는다. Event 품질 USABLE이나 reference UI가 존재해도 AI 사용권을 부여하지 않는다. 상세 분석에서 이미 계산하는 기존 OpenDART event_risk를 새 이벤트 AI 입력으로 확대하지 않는다. 입력 projection은 NEWS/Event/reference payload를 차단해야 한다.

## 14. Version / logging / 재현성

run마다 model/provider revision, prompt hash, 입력/출력 계약, adapter, comparison policy, protocol, Scanner/strategy/selection/exit/Horizon identity를 고정한다. `latest` 모델 별칭만으로 재현성을 보장하지 않는다. pin 불가 공급자는 모델 변경 감지·별도 cohort 분리 방식이 승인되기 전 채택 근거를 축적하지 않는다.

허용된 input projection bytes, canonical hash, 원 응답/정규화 응답, 실패 사유, 시각·지연·비용, source/outcome 연결을 immutable artifact로 보존한다. hash만 남고 원본 보존 권한이 없으면 byte 재생 가능이라고 표시하지 않는다. source ID와 source revision·available_at을 유지해 중복/미래 근거를 검출한다.

LLM 재호출이 같은 답을 만든다고 보장하지 않는다. **저장된 응답을 재생하는 report reproducibility**와 **모델 재실행 일치성**을 분리한다. provider 변경·prompt 변경·코드 수정 후 성공 응답으로 옛 실패를 교체하지 않는다.

저장 구현 시 기존 Simulation backup/restore manifest에 JEV 부가 기록과 연결 무결성 검사를 포함한다. API key·계좌 비밀·불필요한 원문은 로그/backup에 넣지 않는다. 보존/삭제 정책으로 source가 사라지면 보고서의 사용 가능 상태를 갱신한다.

## 15. Production 진입 조건

Phase 1 끝에서 가능한 최초 제품화는 사용자에게 baseline과 함께 표시하는 **제한적 검토 의견**이다. 조건은 §11의 prospective 추가 가치와 권한/시점/오류 격리 검증, 실제 사용자 동선 검수, 프로젝트 소유자 승인, 명시적 활성화, run pin 및 rollback이다.

운영 설정은 Scanner/Strategy 운영 owner에 version 있는 별도 reviewer 활성화 설정으로 게시하는 방향이다. 기존 SelectionPolicyPin에 AI 필드를 임의로 끼워 넣거나 Simulation 최신 보고서만 보고 활성화하지 않는다. 비활성/rollback에서는 기존 baseline만 보인다. 자동 후보 제거·순위 변경·매매/보유 계획 변경은 이 문서로 승인되지 않는다.

초기 provider/API/model은 아직 선정하지 않았다. JEV를 특정 업체의 확인된 제품/API명으로 주장하지 않는다. 후속 선정 시 공식 계약·revision 고정·허용 전송·비용·가용성을 확인한다. Canonical credential environment variable은 `JEV_API_KEY`로 고정하며 실제 secret 값은 로컬 `.env`에만 존재해야 한다. `.env.example`에는 `JEV_API_KEY=` placeholder만 허용한다. API key는 Git commit·로그·artifact·backup에 포함하지 않는다. Credential slot이 준비됐다는 사실은 provider/model/prompt freeze 완료를 의미하지 않는다. SDK는 provider contract를 고정한 뒤 추가한다.

## 16. 다음 구현 단계와 완료 조건

| 큰 단계 | 작업 / 완료 증거 |
| --- | --- |
| Design Freeze | 본 v2를 단일 JEV authority로 사용. 역할·적용점·허용 행동·비교 가설을 고정 |
| Shadow Implementation | 최소 provider adapter, allowlist projector, async review 기록, strict output 검증, baseline fallback, comparison join/report. 같은 작업에서 §11.2 trial 설정 고정 |
| Evaluation | Development 역사 진단과 미래 prospective shadow. 기존 outcome 계산 재사용, 기간/비용/분모 고정, 결과를 보고 변경하지 않음 |
| Adoption Decision | 제한적 보조 표시 / 보류 / 거절. 채택 시에만 명시적 배포·rollback과 UAT |

다음 구현의 의미 있는 검증은 synthetic/fake provider로 먼저 한다:

- 모델 비활성·timeout·잘못된 enum/근거 ID·늦은 응답·저장 실패에서 Scanner rank/action/Risk/plan 동등성.
- canonical capture duplicate/재시작/재시도·input hash mismatch와 미래 outcome 입력 차단.
- PARTIAL/FAILED/OUT_OF_SCOPE/ABSTAIN 분모, CLOSED/CENSORED/NOT_EXECUTED/NO_ENTRY_DATA 구분, skip regret 산식의 작은 수기 사례.
- model/prompt/policy 변경 cohort 분리와 backup/restore 연결, read-only 화면의 무호출.
- Risk·주문 금지·Holdings/Tracking 불변 회귀와 필요한 frontend build. 실제 경로 변경이 있으면 해당 UAT.

참고 회귀 자산: [Prospective tests](../../backend/tests/test_prospective_vnp2s2.py), [R5R evaluator tests](../../backend/tests/test_macro_r5r_evaluator_next6e.py), [R5R binding tests](../../backend/tests/test_macro_r5r_binding_next6e.py), [주문 금지](../../backend/tests/test_no_order_routes.py), [Prospective UI tests](../../frontend/tests/test_prospective_evidence_next3.py). 이번 문서 작업에서는 어느 것도 실행하지 않았다.

## 17. 기존 JEV 개념의 처분과 A~F 답변

| 구분 | 기존 개념 / 현재 처분 |
| --- | --- |
| **A — 유효 원칙** | StockScope 중심·JEV 보조·shadow-first·Risk 우회 금지·baseline 비교·model/prompt pin·Historical/Execution/Prospective 구분·명시적 활성화·계획 자동 변경 금지·실패 시 baseline 유지. 본 문서에 흡수 |
| **이미 해결된 기반** | Prospective 반환 후보 캡처/시간 분리, P5 API/UI와 정책 pin, P6 reference 제품/as-of reader, macro reference 경로, R5R 정책·evaluator·DEV binding. “모두 준비해야 시작”이라는 대기 사유에서 제거 |
| **B — 현재와 맞지 않는 사실** | Scanner 0.21.3.8은 현재 0.21.3.9로 갱신. P6를 기반 모듈만으로 묘사하면 현재 reference/as-of 제품 경로를 누락. 과거 handoff NEXT와 frozen JSON 당시 gate 상태는 현재 미구현 목록이 아님 |
| **더 이상 초기 설계에 필요 없는 후보** | Scanner+AI+Historical 가중 합, 국면별 비율·confidence 곱셈, Jev-only 군, 모든 도메인 동시 통합. 원문도 확정 구현으로 주장하지 않았던 가설이며 본 v2에서는 채택하지 않음 |
| **구체화한 항목** | 단일 역할, post-capture 지점, quant allowlist, output enum/abstain, async 기록 owner, 단일 skip 가설, 비교 분모·후회비용·prospective 채택 조건 |
| **C — 최소 실용 범위** | Scanner의 실제 반환 ENTRY_CANDIDATE만 대상으로 하는 Decision Reviewer. 기존 후보를 바꾸지 않고 재검토 의견을 기록 |
| **D — 이름/역할 혼동** | 있음. NEXT-6E-R5R-JEV는 R5R 첫 observed-path evaluation. 새 이름 NEXT-6E-R5R-EVALUATION과 JEV-REVIEWER-EVALUATION으로 분리 |
| **E — 최단 검증 경로** | 하나의 quant reviewer·한 skip 가설→기존 후보 outcome으로 역사 진단→사전 고정한 미래 prospective→순증분 가치·비용으로 채택 결정. macro/R5R 성공을 선행 gate로 추가하지 않음 |
| **F — 문서 제거 방향** | 중간 task spec·오래된 handoff·반복 resolution/review narrative를 통합/삭제 후보로 분류. 고유 theorem 증명과 machine-readable audit는 보존. 정확한 파일/수는 정리계획에 고정 |

최종 정적 검수: main 코드의 실제 owner와 비교했고, R5R frozen 계산/정책/identity를 변경하지 않았으며, 이미 구현된 기반과 새로 필요한 JEV 기능을 구분했다. 새 파일은 본 문서와 cleanup plan 두 개뿐이다. 코드 구현·평가 실행·threshold 조정·기존 문서 정리는 다음 작업의 범위다.
