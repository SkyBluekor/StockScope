# StockScope Docs 정리계획

작성일: 2026-10-06 (Asia/Seoul)  
조사 기준: 로컬 `main` HEAD `893f2b96289a02f7cfce46b2a4ea7abb0d86326c`  
지위: **cleanup manifest + 2026-10-06 실행 기록. 계획에 따른 통합·링크 정정·삭제가 완료됐다.**

## 1. 확정 결론과 집계

현재 main의 `docs/` 추적 파일 **154개**를 분류했다: Markdown 126, JSON 27, DOCX 1. 파일명만으로 정하지 않고 본문의 목적·결정·상태·계약·참조를 검토했다. DOCX는 문단 내용으로 제품 원안 역할을 확인했으며 레이아웃 검수는 하지 않았다.

| 분류 | 기존 파일 수 | 다음 작업 의미 |
| --- | ---: | --- |
| KEEP_ACTIVE | 17 | 현재 읽기/구현 authority로 유지 |
| MERGE_INTO_ACTIVE | 95 | 유효 계약/결정만 지정 대상에 통합한 뒤 원본 narrative 제거 후보 |
| KEEP_HISTORY | 33 | audit·고유 논증·과거 원본 유지, 신규 작업 필독에서 제외 |
| DELETE_REDUNDANT | 9 | 중복/만료 전달문·패치 설명 제거 후보 |
| 합계 | 154 | 각 파일은 아래 manifest에 정확히 한 번 포함 |

**삭제 후보 9개 + 통합 후보 95개 = 104개**다. 104개를 지금 삭제한다는 뜻이 아니다. 통합 후보는 정보 이전·참조 검수 후 원본 제거를 검토한다. JSON 27개는 전부 보존: active 8, history 19. 현재 authoritative 계약·binding·fixtures·review의 byte/hash 변경은 정리 범위가 아니다.

이번에 추가한 [JEV 설계 v2](StockScope_JEV_통합설계_v2_2026-10-06.md)와 본 manifest 2개는 별도로 KEEP_ACTIVE다. 따라서 작업 후 docs 156개를 설명하지만 **후보 집계 분모는 기존 154개**다. root README·tools 문서는 통합 대상/참조 점검에만 포함하고 삭제 수에 넣지 않는다.

Holdout 관련 파일·데이터는 정리 모집단으로 탐색하지 않았다. DEV 원본·runtime DB·실 evaluation 결과도 읽지 않았다. 코드의 계약 정의·테스트 소스와 저장된 문서/JSON을 조사했을 뿐 애플리케이션·test/evaluator를 실행하지 않았다.

## 2. 새 작업자의 읽기 순서

새 index 파일을 계속 늘리는 대신 다음 정리 때 **기존 Master Architecture 맨 앞에 짧은 “현재 기준과 읽는 순서” 표**를 넣는다. 기존 README의 문서 링크도 그 표로 연결한다.

1. **M — Master Architecture:** 제품 목적·도메인/데이터 owner·금지 경계.
2. **I — Implementation Baseline:** 현재 구현 계약·frozen 불변식·회귀/운영 경계.
3. **현재 작업의 기준 하나:** R5R이면 B와 authoritative JSON, JEV이면 J. 과거 resolution 연속 읽기 금지.
4. **R — Roadmap:** 다음 작업·미지원/미승인 정책·조건부 backlog.
5. **H — 통합 변경이력:** 특정 결정의 이유가 필요할 때만 열기. 고유 proof/JSON은 H에서 좁게 연결.

### 2.1 통합 대상의 정확한 경로와 역할

| 약칭 | 대상 경로 | 통합할 내용 / 경계 |
| --- | --- | --- |
| M | `docs/StockScope_MASTER_ARCHITECTURE_vNext.md` | 제품 책임·UX·boundary. 버전별 구현/회귀 로그를 전부 붙이지 않음 |
| I | `docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md` | 도메인별 현재 계약·code/test 참조·legacy 제한·운영 상태. 변경 금지와 체크리스트 중심 |
| R | `docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md` | 현재 의존성·다음 작업·조건부 후보. 과거 “미구현”은 코드와 대조해 갱신 |
| B | `docs/설계/StockScope_NEXT6E_R5R_통합설계기준_2026-10-05.md` | R5R claim·현재 identity/gate·참조 진입점. frozen JSON의 계산 authority를 대신하지 않음 |
| J | `docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md` | 단일 Decision Reviewer·Phase 1·계약·shadow·평가 |
| N | `docs/StockScope_NEXT6_MACRO_EVENT_ARCHITECTURE_DESIGN_2026-09-29.md` | Macro/Event source/time/use boundary 및 실제 구현 연결 |
| H | `docs/history/StockScope_R4_R5_R5R_설계변경이력.md` | **다음 정리에서만 생성할 단일 history 문서**. R2~R3 선행 맥락도 서두에 짧게 포함 |
| Setup | `README.md`, `tools/data/README.md` | 실제 설치/복구 명령과 미검증 조건. 실행 task spec을 사용자 가이드로 무비판 복사하지 않음 |

H는 이번에는 만들지 않는다. 실제 통합 때도 archive 디렉터리에 수십 개 narrative를 옮기는 방식으로 끝내지 않는다. M/I/R/B는 각각 역할을 나누고 현재 상태를 서로 중복 기재하는 부분은 한 owner의 링크로 대체한다.

## 3. 우선 정정할 현재/과거 혼재

| 발견 | 다음 정리에서 할 일 |
| --- | --- |
| R5R B §18/20/31~34의 BLOCKED·정책/구현 미완료와 §35/39/40의 PASS·완료가 함께 있음 | 현재 상태 요약을 첫머리에 하나로 모으고 과거 단계 서술은 H에 날짜/당시 상태와 함께 이동. 과거 PASS로 재작성 금지 |
| 초기정책 문서 §16의 당시 G1/G4 미완료 | “정책 결정 당시 상태”라고 표시하고 현재 상태는 B/구현 문서로 링크 |
| Method V2·Review V2의 과거 gate 상태 | JSON 수정 금지. 현재 effective state는 Policy V1 + Binding V1 + 구현 검증 문서의 조합임을 설명 |
| NEXT-6E-R5R-JEV라는 다음 작업명 | narrative에서는 NEXT-6E-R5R-EVALUATION으로 안내. historical 별칭과 기존 stage_id는 보존. AI 평가는 JEV-REVIEWER-EVALUATION |
| JEV 원문의 Scanner 0.21.3.8 | J의 main 0.21.3.9/manifest ID 사용. 과거 검증 기록의 버전은 그대로 둠 |
| P6를 기반 모듈/향후 작업으로만 표시 | 현재 product/asof/API 경로를 링크. real corpus 가치·AI 사용권·prediction은 완료로 승격하지 않음 |
| Fresh-clone spec의 미착수 | `tools/data/bootstrap_runtime.py`, `tools/runtime/bootstrap_state.py`, `backend/tests/test_env_v2_t2_fresh_clone.py` 존재와 범위를 대조. 미실시 운영 검증은 따로 남김 |
| vNext의 예전 Current State / Recovery Context / Astra handoff 링크 | 이번 main docs inventory에 없는 문서를 현재 필독으로 제시하지 않음. 과거 입력 citation은 고정 revision 근거로 남기거나 “현 checkout에 없음” 명시 |
| input UX 0.15.2와 0.15.3 | 제거된 OHLC 바로가기와 후속 선택 입력 Stepper를 구분. 단순 버전 합치기 금지 |
| fundamental 0.17과 freshness 0.17.1 | 연간 전용 가정 대신 최신 공식 실적과 연간 배수의 분리 의미를 보존 |
| old Scanner/historical 문서의 준비 일수·exit/cache·historical-first 표현 | 현재 scanner/candidate_priority/production policy 기준으로 유효 원칙만 추출 |

현재 baseline 3개를 없애 하나의 대형 연대기로 만들지 않는다. 반대로 수십 개 중간 R5 문서를 현재 필독으로 남기지도 않는다.

## 4. 삭제 전에 보존할 결정 ledger

H에는 단계별 전체 본문이 아니라 **날짜 / source path와 main revision / 결정 / 이유 / 당시 verdict / 대체 계약 / 현재 영향**만 남긴다.

| 이력 묶음 | 반드시 남길 정보 |
| --- | --- |
| R2~S6 초기 Reference Adequacy | DEV-informed origin·독립 정책 근거의 미해결·path description과 population inference 구분. 나중에 data-blind였던 것처럼 바꾸지 않음 |
| R3/R4 | lattice/quantization·stationarity/mixing 및 actual-process binding 한계. 진단 비기각은 assumption 승인 아님 |
| R5 D2A/B/C | atomic/local-time 문제, prospective finite grid 선택과 j/20 mapping, all-later/latest 유지 이유 |
| R5 D2D/D2D1/D2D2 | local weighted inference·atomic variance/calibration 실패. 고유 증명 상세는 H2 원본 링크 |
| R5 D2E0/E1/E2/Final | analytical conservative band 선택·consolidation·최종 계약. theorem validity와 model-use 분리 |
| GA1/BR1 | assumption ownership finding→V2/targeted review 해소. 이전 BLOCKED는 유지 |
| GA2/BR1 | actual DGS10 process에 모든 상수/가정을 감사 가능하게 bind할 경로 부족, PARTIALLY_FEASIBLE, METHOD_USE_REDESIGN_REQUIRED |
| MUR1/2 | R5R은 R5 patch가 아닌 새 observed-path target. T/L/S·window/grid·Common-N의 제한된 의미 |
| MUR3/BR1 | missing horizon, chronology hash, exact rational ambiguity 해소; fixture·review V1/V2 lineage |
| POLICY / IMPLEMENT | T/L/S 모두 gate, 0.10/0.50/0.25, 구현/DEV binding 완료, G0~G4 PASS, 실제 평가 미실행 |
| JEV 명칭 | R5R 실행 별칭과 AI reviewer 평가를 분리한 v2 결정 |

원문 제거 후 독자가 현재 규칙과 중요한 실패 이유를 active+H에서 이해할 수 있어야 한다. 보존하지 않은 중간 유도/문헌 조사/작업 지시의 상세는 이 manifest의 기준 SHA와 파일 경로로 Git에서 복원한다. **“현재 정보 유실 없음”과 “원문 전체가 새 문서에 남음”은 다르다.**

## 5. 참조 때문에 보존해야 하는 예외

소스와 frozen JSON의 직접 참조를 확인했다.

- `backend/app/macro/r4_contract.py`가 `docs/StockScope_NEXT6E_S6A_R3_방법론_Blocker_해소_설계_2026-10-03.md`를 design_path로 기록한다.
- R5R Method V1/V2와 legacy R5 Final Method V1/V2가 `docs/StockScope_NEXT6E_S6B_RISK_BUDGET_GOVERNANCE_RESOLUTION_2026-10-02.md`를 source_document/document로 참조한다.
- R5 theorem-review template/result가 `docs/NEXT6E_S6A_R5_D2E2_Theorem_Chain_Consolidation_2026-10-05.md`를 직접 참조한다.
- R5R review와 backend tests가 `docs/fixtures/`의 두 fixture를 직접 사용한다.

위 원본은 현 경로에 유지한다. 정리 편의 때문에 frozen contract 경로를 수정해 semantic hash를 바꾸거나, 증명 본문을 링크 한 줄로 덮어쓰지 않는다. HISTORY 분류는 파일 자체의 재직렬화/이동 허가가 아니다.

R5_D2*가 모두 불필요한 것도 아니다. D2D1/D2D2/E1/E2와 GA1 재유도에는 고유 논증이 있으므로 KEEP_HISTORY다. GA2/MUR narrative는 결과 JSON과 함께 H에 결정 맥락을 압축할 수 있다. 이름이 R24로 같은 두 문서는 날짜·연구 기준과 역할이 달라 중복 파일로 즉시 삭제하지 않고 M3 통합 대상으로 둔다.

## 6. 파일군별 manifest

각 파일은 아래 **파일군의 분류·이유·통합 대상·정보 유실 판정**을 상속한다. 표의 “현재 역할”은 실제 내용의 역할이다. 분류는 네 값만 사용한다. MERGE/HISTORY/DELETE는 아직 수행 결과가 아니다.

### A1. 상위 기준과 운영 읽기 진입점 — 6개

- 분류: **KEEP_ACTIVE**
- 통합/유지 대상: 현 경로 유지; M/I/R에 현재 authority 안내
- 이유: 제품 책임·구현 불변식·개발 순서·사용 준비를 서로 다른 owner 문서로 유지한다.
- 삭제 후 정보 유실 여부: 없음. 삭제하지 않음.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/API_KEYS.md` | 새 PC 공급자 인증 준비·연결 안내(비밀값 저장소 아님) |
| `docs/TRACKING_BASELINE.md` | TRACK.1 CLOSED/FROZEN, D+1 관찰·동일 기준 병합·CLOSED 동결 |
| `docs/StockScope_MASTER_ARCHITECTURE_vNext.md` | 제품 도메인 책임·저장 owner·UX·미결정 질문 |
| `docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md` | 구현 불변식·migration·검증·복구·명시적 활성화 규칙 |
| `docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md` | 조건부 단계와 의존성·지원 범위; 현재 완료표 아님 |
| `docs/StockScope_NEXT6_MACRO_EVENT_ARCHITECTURE_DESIGN_2026-09-29.md` | Macro/Event 책임과 source/time/제품 연결의 상위 경계 |

### A2. R5R 현재 기준·정책·구현 — 3개

- 분류: **KEEP_ACTIVE**
- 통합/유지 대상: 현 경로 유지; B의 현재 상태 요약을 갱신
- 이유: 계산 설계·정책 근거·구현 및 binding 증거의 서로 다른 역할이다. 과거 상태와 현재 상태가 섞인 부분만 다음 정리에서 정정한다.
- 삭제 후 정보 유실 여부: 없음. frozen JSON은 손대지 않음.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/설계/StockScope_NEXT6E_R5R_구현및바인딩_2026-10-06.md` | NEXT-6E-R5R-IMPLEMENT — 구현 및 DEV 바인딩 |
| `docs/설계/StockScope_NEXT6E_R5R_초기정책결정_2026-10-05.md` | NEXT-6E-S6B-R5R-POLICY — 초기 운영 정책 결정 |
| `docs/설계/StockScope_NEXT6E_R5R_통합설계기준_2026-10-05.md` | NEXT-6E R5R 통합 설계 기준선 |

### A3. 현재 R5R machine authority와 fixtures — 8개

- 분류: **KEEP_ACTIVE**
- 통합/유지 대상: 원래 경로·내용·hash 그대로 유지
- 이유: 실제 evaluator/binding/test가 의존하는 현재 계약 및 검산 자료다. narrative 통합과 분리해 보존한다.
- 삭제 후 정보 유실 여부: 없음. 삭제·이동·재직렬화 금지.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/bindings/NEXT6E_R5R_EVALUATION_BINDING_V1.json` | DEV identity/chronology/구조 binding; 실 T/L/S·Common-N 결과 없음 |
| `docs/contracts/NEXT6E_S6A_R5R_CANDIDATE_DOMAIN_V1.json` | 고정 계산/구조 계약 — NEXT6E_S6A_R5R_CANDIDATE_DOMAIN_V1 |
| `docs/contracts/NEXT6E_S6A_R5R_METHOD_CONTRACT_V2.json` | 현재 exact R5R target/method/chronology/numeric/failure 계약 |
| `docs/contracts/NEXT6E_S6A_R5R_WINDOW_PROFILE_V1.json` | 고정 계산/구조 계약 — NEXT6E_S6A_R5R_WINDOW_PROFILE_V1 |
| `docs/contracts/NEXT6E_S6B_R5R_POLICY_V1.json` | 현재 내부 reference 용도·T/L/S gate·고정 tolerance·governance |
| `docs/fixtures/NEXT6E_S6A_R5R_DETERMINISTIC_FIXTURES_V1.json` | 수기 exact 계산·edge-case fixtures; backend test 직접 소비 |
| `docs/fixtures/NEXT6E_S6A_R5R_MUR3_BR1_TARGETED_FIXTURES_V1.json` | chronology/numeric/missing-horizon BR1 fixtures; review/test 직접 소비 |
| `docs/reviews/NEXT6E_S6A_R5R_DETERMINISTIC_REVIEW_RESULT_V2.json` | 현재 contract targeted review PASS; gate snapshot은 당시 이력 |

### H1. 과거 machine contract·review·template — 19개

- 분류: **KEEP_HISTORY**
- 통합/유지 대상: 원래 경로 유지; H에서 ID·상태·계승 관계만 연결
- 이유: BLOCKED→PASS 및 R5→R5R lineage, 과거 서명/hash와 템플릿 참조를 보존한다. UNFILLED_TEMPLATE은 승인 결과가 아니다.
- 삭제 후 정보 유실 여부: 없음. audit 원본 보존.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/contracts/NEXT6E_S6A_R5R_METHOD_CONTRACT_V1.json` | BR1 이전 모호성이 남은 method V1, superseded audit |
| `docs/contracts/NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2.json` | 고정 계산/구조 계약 — NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2 |
| `docs/contracts/NEXT6E_S6A_R5_CONCENTRATION_BAND_V1.json` | 고정 계산/구조 계약 — NEXT6E_S6A_R5_CONCENTRATION_BAND_V1 |
| `docs/contracts/NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V1.json` | 고정 계산/구조 계약 — NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V1 |
| `docs/contracts/NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V2.json` | 고정 계산/구조 계약 — NEXT6E_S6A_R5_FINAL_METHOD_CONTRACT_V2 |
| `docs/contracts/NEXT6E_S6A_R5_METHOD_CONSOLIDATED_V1.json` | 고정 계산/구조 계약 — NEXT6E_S6A_R5_METHOD_CONSOLIDATED_V1 |
| `docs/reviews/NEXT6E_S6A_R5R_DETERMINISTIC_REVIEW_RESULT_V1.json` | 이전 BLOCKED_CONTRACT_AMBIGUITY 판정과 finding 기록 |
| `docs/reviews/NEXT6E_S6A_R5_METHOD_USE_REDESIGN_DECISION_V1.json` | 역사 review/의사결정 결과 — NEXT6E_S6A_R5_METHOD_USE_REDESIGN_DECISION_V1 |
| `docs/reviews/NEXT6E_S6A_R5_MODEL_USE_BINDING_ROUTE_V1.json` | 역사 review/의사결정 결과 — NEXT6E_S6A_R5_MODEL_USE_BINDING_ROUTE_V1 |
| `docs/reviews/NEXT6E_S6A_R5_MODEL_USE_RESULT_V1.json` | 역사 review/의사결정 결과 — NEXT6E_S6A_R5_MODEL_USE_RESULT_V1 |
| `docs/reviews/NEXT6E_S6A_R5_THEOREM_REVIEW_RESULT_V1.json` | 역사 review/의사결정 결과 — NEXT6E_S6A_R5_THEOREM_REVIEW_RESULT_V1 |
| `docs/reviews/NEXT6E_S6A_R5_THEOREM_REVIEW_RESULT_V2.json` | 역사 review/의사결정 결과 — NEXT6E_S6A_R5_THEOREM_REVIEW_RESULT_V2 |
| `docs/templates/NEXT6E_R4C_CLEAN_REPLAY_ATTESTATION_TEMPLATE.json` | 미작성 역사 template — NEXT6E_S6A_R4C_CLEAN_REPLAY_ATTESTATION_V1 |
| `docs/templates/NEXT6E_R4_MODEL_USE_TEMPLATE.json` | 미작성 역사 template — NEXT6E_S6A_R4_MODEL_USE_V1 |
| `docs/templates/NEXT6E_R4_THEOREM_REVIEW_TEMPLATE.json` | 미작성 역사 template — NEXT6E_S6A_R4_THEOREM_REVIEW_V1 |
| `docs/templates/NEXT6E_S6A_R5_MODEL_USE_APPROVAL_V1.json` | 미작성 역사 template — NEXT6E_S6A_R5_MODEL_USE_APPROVAL_V1 |
| `docs/templates/NEXT6E_S6A_R5_MODEL_USE_APPROVAL_V2.json` | 미작성 역사 template — NEXT6E_S6A_R5_MODEL_USE_APPROVAL_V2 |
| `docs/templates/NEXT6E_S6A_R5_NUMERICAL_PROFILE_V1.json` | 미작성 역사 template — NEXT6E_S6A_R5_NUMERICAL_PROFILE_V1 |
| `docs/templates/NEXT6E_S6A_R5_THEOREM_REVIEW_V1.json` | 미작성 역사 template — NEXT6E_S6A_R5_THEOREM_REVIEW_V1 |

### H2. 고유 증명·실패 근거 및 고정 경로 참조 — 9개

- 분류: **KEEP_HISTORY**
- 통합/유지 대상: 원래 경로 유지; H에 결론만 통합
- 이유: JSON에 없는 증명·반례·재유도 또는 코드/frozen JSON의 직접 경로 참조가 있다. '계약만으로 전부 복원 가능'으로 처리하면 안 된다.
- 삭제 후 정보 유실 여부: 지금 삭제하면 상세 논증 또는 참조 관계가 유실됨. 삭제 대상 아님.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/NEXT6E_S6A_R5_D2D1_Local_Weighted_Atomic_Max_Inference_Resolution_2026-10-05.md` | NEXT-6E-S6A-R5-D2D1 — Local-Weighted Atomic Max-Inference Resolution |
| `docs/NEXT6E_S6A_R5_D2D2_Weighted_Gaussian_Calibration_Resolution_2026-10-05.md` | NEXT-6E-S6A-R5-D2D2 — Weighted Gaussian Calibration Resolution |
| `docs/NEXT6E_S6A_R5_D2E1_Conservative_LocalCDF_Concentration_Band_Design_2026-10-05.md` | NEXT-6E-S6A-R5-D2E1 — Conservative Local-CDF Concentration Band Design |
| `docs/NEXT6E_S6A_R5_D2E2_Theorem_Chain_Consolidation_2026-10-05.md` | NEXT-6E-S6A-R5-D2E2 — Theorem Chain Consolidation |
| `docs/reviews/NEXT6E_S6A_R5_GA1_Independent_Theorem_Review_2026-10-05.md` | NEXT-6E-S6A-R5-GA1 — Independent Theorem Review |
| `docs/StockScope_NEXT6E_S6A_R3_방법론_Blocker_해소_설계_2026-10-03.md` | NEXT-6E / S6A / R3 이후 방법론 Blocker 해소 설계 |
| `docs/StockScope_NEXT6E_S6B_RISK_BUDGET_GOVERNANCE_RESOLUTION_2026-10-02.md` | NEXT-6E-S6B — Risk-Budget Governance Resolution |
| `docs/StockScope_NEXT6E_S6A_R4B_GA_승인패키지_2026-10-03.md` | NEXT-6E-S6A-R4B — G-A 승인 패키지 및 Clean Replay 준비 |
| `docs/StockScope_NEXT6E_S6A_R4C_GA_최종판정_2026-10-03.md` | NEXT-6E-S6A-R4C — Formal Clean Replay & G-A Final Decision |

### H3. 제품 원안 및 고유 검증 기록 — 5개

- 분류: **KEEP_HISTORY**
- 통합/유지 대상: 원래 경로 유지; M/I에서 필요한 제품 원칙과 결과 경계만 참조
- 이유: DOCX 제품 원안과 P6 검증/UAT, Backtest 진단은 현재 계약과 별개인 역사 증거다. 당시 수치/스크린샷/완료 기록을 새 현재 상태로 재라벨하지 않는다.
- 삭제 후 정보 유실 여부: 삭제하면 원안/진단/UAT 증거 유실. 보존.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/StockScope_적응형_분석_보유관리_제품고도화_기준문서_2026-09-26.docx` | 제품 목적·다섯 책임·장기 확장·미정 수치를 담은 원안 |
| `docs/StockScope_P6_S1_FINAL_VERIFICATION_2026-09-28.md` | P6-S1 Final Verification — 2026-09-28 |
| `docs/backtest-accuracy-v0.19.4.md` | v0.19.4 — Backtest Accuracy Audit |
| `docs/backtest-risk-policy-v0.19.5.md` | v0.19.5 — Risk Gate & Stop Policy Comparison |
| `docs/backtest-risk-policy-decision-v0.19.6.md` | v0.19.6 — Risk Policy Decision |

### M1. 기존 JEV 개념과 조건부 제품 후보 — 2개

- 분류: **MERGE_INTO_ACTIVE**
- 통합/유지 대상: J (§1~17); Capital 후보는 M의 제약 책임·R의 조건부 backlog
- 이유: JEV 좋은 원칙은 v2에 흡수했고 역할/가중치 후보는 명시적으로 폐기·보류했다. Capital 설계는 미승인 제안이므로 완료 기능으로 옮기지 않는다.
- 삭제 후 정보 유실 여부: 원칙/결정/보류 이유를 이전한 뒤 운영 정보 유실 없음. 옛 가설 상세는 Git revision으로만 복원.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/StockScope_JEV_INTEGRATION_CONCEPT.md` | 2026-09-28의 후보 역할·가중치·confidence·shadow 개념; v2로 superseded |
| `docs/StockScope_CAPITAL_AWARE_RECOMMENDATION_DESIGN_2026-09-29.md` | Capital Aware Recommendation Design |

### M2. R5 D2·GA·MUR 중간 narrative — 15개

- 분류: **MERGE_INTO_ACTIVE**
- 통합/유지 대상: B의 현재 계약/lineage + H의 결정 ledger
- 이유: 현재 계산 authority는 R5R JSON/B다. finite grid, calibration 실패, assumption ownership, model-use BLOCKED, observed-path 전환, BR1 해소 결정을 한 흐름으로 통합한다.
- 삭제 후 정보 유실 여부: 결정 ID·당시 verdict·이유·후속 contract 참조를 이전한 뒤 현재 구현 정보 유실 없음. 고유 proof는 H2에 남김.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/NEXT6E_S6A_R5_D2A_Atomic_LocalEDF_Boundary_Simultaneous_정리해소_2026-10-05.md` | NEXT-6E-S6A-R5-D2A — Atomic Local-EDF / Boundary / Simultaneous 정리 해소 |
| `docs/NEXT6E_S6A_R5_D2B_Simultaneous_Index_Architecture_결정_2026-10-05.md` | NEXT-6E-S6A-R5-D2B — Simultaneous-Index Architecture 결정 |
| `docs/NEXT6E_S6A_R5_D2C_Finite_Anchor_Grid_Governance_2026-10-05.md` | NEXT-6E-S6A-R5-D2C — Finite Anchor Grid Governance |
| `docs/NEXT6E_S6A_R5_D2D_Finite_Anchor_LocalEDF_Theorem_Resolution_2026-10-05.md` | NEXT-6E-S6A-R5-D2D — Finite-Anchor Local-EDF Theorem Resolution |
| `docs/NEXT6E_S6A_R5_D2E0_Calibration_Blocker_Architecture_Reconsideration_2026-10-05.md` | NEXT-6E-S6A-R5-D2E0 — Calibration-Blocker Architecture Reconsideration |
| `docs/NEXT6E_S6A_R5_D2E_Final_Method_Contract_Freeze_2026-10-05.md` | NEXT-6E-S6A-R5-D2E — Final Method Contract Freeze |
| `docs/NEXT6E_S6A_R5_D2_방법계약_정리해소_2026-10-04.md` | NEXT-6E-S6A-R5-D2 — 방법계약 / 정리 해소 판정 |
| `docs/NEXT6E_S6A_R5_MUR2_관측경로_경험적안정성_계약설계_2026-10-05.md` | NEXT-6E-S6A-R5-MUR2 — 관측경로 경험적 안정성 Target / Contract 설계 |
| `docs/NEXT6E_S6A_R5_비정상성_Blocker_해소_설계_2026-10-04.md` | NEXT-6E-S6A-R5 — 비정상성 Blocker 해소 설계 |
| `docs/reviews/NEXT6E_S6A_R5_GA1_BR1_Assumption_Ownership_Resolution_2026-10-05.md` | NEXT-6E-S6A-R5-GA1-BR1 — Assumption Ownership Blocker Resolution |
| `docs/reviews/NEXT6E_S6A_R5_GA2_BR1_Model_Use_Evidence_Route_Resolution_2026-10-05.md` | NEXT-6E-S6A-R5-GA2-BR1 — Model-Use Evidence / Assumption Binding Route Resolution |
| `docs/reviews/NEXT6E_S6A_R5_GA2_Model_Use_Acceptance_2026-10-05.md` | NEXT-6E-S6A-R5-GA2 — Actual-Process Model-Use Acceptance |
| `docs/reviews/NEXT6E_S6A_R5_MUR1_방법사용_재설계_아키텍처_비교_2026-10-05.md` | NEXT-6E-S6A-R5-MUR1 — 방법사용 재설계 아키텍처 비교 |
| `docs/reviews/NEXT6E_S6A_R5_MUR3_BR1_R5R_계약_모호성_해소_2026-10-05.md` | NEXT-6E-S6A-R5-MUR3-BR1 — R5R 계약 모호성 해소 |
| `docs/reviews/NEXT6E_S6A_R5_MUR3_R5R_결정론적_계약_검토_2026-10-05.md` | NEXT-6E-S6A-R5-MUR3 — R5R 결정론적 계약 / Edge-Case 검토 |

### M3. R2~R4 및 구 Reference Adequacy 설계 흐름 — 14개

- 분류: **MERGE_INTO_ACTIVE**
- 통합/유지 대상: B의 범위/비재개 원칙 + H의 R2→R4→R5R 요약
- 이유: 옛 population/theorem·정책 미결 상태가 현재 gate처럼 읽힌다. 역사적 실패와 DEV-informed origin은 보존하고 과거 next-task 반복을 걷어낸다.
- 삭제 후 정보 유실 여부: 결정 근거·노출/독립성 이력·제한을 H에 옮긴 후 현재 authority 유실 없음. 상세 문헌 논의는 지정 Git revision으로 복원.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/StockScope_NEXT6B_S4_2B16_R22_POLICY_RESOLUTION_REVIEW_2026-10-01.md` | NEXT-6B-S4.2-B.1.6-R2.2 — Remaining Three Policy-Class Resolution Review |
| `docs/StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md` | NEXT-6B-S4.2-B.1.6-R2.3 — Independent Reference-Adequacy Evidence & Risk-Budget Preregistration |
| `docs/StockScope_NEXT6B_S4_2B16_R241_JOINT_INFERENCE_BUDGET_CLOSURE_2026-10-01.md` | NEXT-6B-S4.2-B.1.6-R2.4.1 — Joint Sequential Inference Proof & Independent Budget Provenance Closure |
| `docs/StockScope_NEXT6B_S4_2B16_R242_PATH_DISPOSITION_INDEPENDENCE_RECOVERY_2026-10-01.md` | NEXT-6B-S4.2-B.1.6-R2.4.2 — Reference Adequacy Path Disposition & Prospective Independence-Recovery Design |
| `docs/StockScope_NEXT6B_S4_2B16_R24_DEPENDENCE_RISK_GOVERNANCE_REVIEW_2026-10-01.md` | NEXT-6B-S4.2-B.1.6-R2.4 — Statistic-Specific Dependence Method & Risk-Budget Governance Review |
| `docs/StockScope_NEXT6B_S4_2B16_R24_METHOD_RISK_GOVERNANCE_2026-10-02.md` | NEXT-6E-S5 결과; 10/01 R2.4와 제목은 같지만 실행 기준·lineage가 다른 후속 조사 |
| `docs/StockScope_NEXT6B_S4_2B16_R2_BLOCKER_REVIEW_2026-09-30.md` | NEXT-6B-S4.2-B.1.6-R2 — Remaining Reference Adequacy Blocker Resolution Review |
| `docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md` | NEXT-6E — Reference Adequacy Resolution Architecture |
| `docs/StockScope_NEXT6E_S6A_METHOD_CONTRACT_RESOLUTION_2026-10-02.md` | NEXT-6E-S6A — Method Contract Resolution |
| `docs/StockScope_NEXT6E_S6A_R1_SEQUENTIAL_FUNCTIONAL_THEOREM_RESOLUTION_2026-10-02.md` | NEXT-6E-S6A-R1 — Sequential Functional Theorem Resolution |
| `docs/StockScope_NEXT6E_S6A_R2A_CANDIDATE_DOMAIN_GOVERNANCE_DECISION_2026-10-02.md` | NEXT-6E-S6A-R2A — Candidate-Domain Governance Decision |
| `docs/StockScope_NEXT6E_S6A_R2_CANDIDATE_DOMAIN_MULTIPLIER_PROFILE_RESOLUTION_2026-10-02.md` | NEXT-6E-S6A-R2 — Candidate-Domain & Multiplier-Profile Resolution |
| `docs/StockScope_NEXT6E_S6A_R3_ASSUMPTION_ACCEPTANCE_EVIDENCE_GATE_2026-10-02.md` | NEXT-6E-S6A-R3 — Assumption Acceptance Evidence Gate |
| `docs/StockScope_NEXT6E_S6A_R4A_승인_Blocker_해소_2026-10-03.md` | NEXT-6E-S6A-R4A — 승인 Blocker 해소 및 G-A 재판정 준비 |

### M4. P2/P3 구현 checkpoint와 bootstrap 명세 — 4개

- 분류: **MERGE_INTO_ACTIVE**
- 통합/유지 대상: I의 도메인 구현 계약·검증 근거; M의 owner; setup는 README.md / tools/data/README.md
- 이유: API·migration·불변식·legacy 한계를 현재 코드와 대조해 한곳으로 이동한다. bootstrap의 '미착수'는 구현 도구/테스트 존재와 달라 정정 필요; 이 조사로 운영 완료를 선언하지 않는다.
- 삭제 후 정보 유실 여부: API/schema/회귀/검증 기록과 미검증 항목을 이전한 후 유실 없음.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/StockScope_VN_P2_S1_IMPLEMENTATION_2026-09-27.md` | VN-P2-S1 Implementation Checkpoint |
| `docs/StockScope_VN_P2_S2_IMPLEMENTATION_2026-09-27.md` | VN-P2-S2 Implementation Checkpoint |
| `docs/StockScope_VN_P3_S1_IMPLEMENTATION_2026-09-27.md` | VN-P3-S1 Implementation Checkpoint |
| `docs/StockScope_FRESH_CLONE_BOOTSTRAP_TASK_SPEC_2026-10-02.md` | Next Task — Fresh-PC / Fresh-Clone Bootstrap |

### M5. Sector PIT source/권한 조사 — 2개

- 분류: **MERGE_INTO_ACTIVE**
- 통합/유지 대상: N의 sector source capability·한계 절
- 이유: source feasibility와 접근 증명은 상호 보완이다. public surface 발견과 automated ingestion 승인을 구분한 채 함께 읽도록 통합한다.
- 삭제 후 정보 유실 여부: PIT/known-at 증거 한계와 권한 미승인 상태·근거 링크를 모두 이전하면 유실 없음.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/StockScope_NEXT6C_S31_KRX_MEMBERSHIP_ACCESS_PROOF_2026-10-01.md` | NEXT-6C-S3.1 — KRX Historical Constituent Access & Known-At Proof |
| `docs/StockScope_NEXT6C_S3_SECTOR_PIT_SOURCE_FEASIBILITY_2026-10-01.md` | NEXT-6C-S3 — Historical Sector Membership Source Feasibility |

### M6. 도메인 계산·정책·데이터 계약 설명 — 32개

- 분류: **MERGE_INTO_ACTIVE**
- 통합/유지 대상: I의 Scanner/Strategy/Risk/검증/데이터 계약 절; M의 책임 요약
- 이유: 파일별 유효 불변식만 현재 구현과 대조해 통합한다. 버전별 전체 본문을 붙이거나 과거 수치/순위를 current로 승격하지 않는다.
- 삭제 후 정보 유실 여부: 보존 체크리스트와 code/test 링크 이전 후 유실 없음. obsolete 동작은 한 줄 변경 이력으로 남김.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/backtest-interpretation-price-accuracy-v0.21.4-A.2.md` | v0.21.4-A.2 interpretation rules |
| `docs/backtest-pullback-v0.19.md` | v0.19 — Backtest Engine / Pullback MVP |
| `docs/concrete-entry-risk-guide-v0.21.1.md` | v0.21.1 — Concrete Entry & Risk Guide |
| `docs/condition-decision-consistency-v0.20.2.4.md` | 조건 집계 불변식 및 옛 historical-first 우선순위(현재 순위에 복사 금지) |
| `docs/entry-timing-action-v0.18.2.md` | v0.18.2 — Entry Timing Action Engine |
| `docs/event-impact-v0.13.md` | Event Impact Engine v0.13 |
| `docs/event-risk-v0.12.md` | OpenDART Event Risk v0.12 |
| `docs/exit-policy-research-v0.21.4-A.md` | v0.21.4-A — Exit Policy Research & Backtest Audit |
| `docs/exit-policy-selection-v0.21.4-B.1.md` | Exit Policy Selection & Validation — v0.21.4-B.1 |
| `docs/exit-policy-validation-runner-v0.21.4-B.1.1.md` | Exit Policy Validation Runner v0.21.4-B.1.1 |
| `docs/fundamental-engine-v0.17.md` | 연간 재무 비교·해석의 초기 계약; 최신 보고서 선택은 v0.17.1로 보정 |
| `docs/fundamental-freshness-v0.17.1.md` | 분기/반기/3분기 포함 최신 공식 실적·동기간 YoY·연간 배수 분리 |
| `docs/historical-evidence-v0.21.2.md` | 과거 근거를 현재 후보 순위와 분리; 과거 고정 exit/cache 상세는 현재 코드로 보정 |
| `docs/investor-style-action-v0.18.1.md` | Investor Style Action Engine v0.18.1 |
| `docs/investor-style-v0.18.md` | Investor Style Engine + Style Playbook v0.18 |
| `docs/krx-api-budget-market-store-v0.20.3.md` | v0.20.3 KRX API Budget & Historical Market Store |
| `docs/manual-reference-price-v0.9.1.md` | v0.9.1 — EOD 기준과 현재 참고 시나리오 분리 |
| `docs/manual-reference-price-v0.9.md` | v0.9 — 현재 참고가격 Override 설계 |
| `docs/multi-strategy-backtest-v0.20.md` | v0.20 — Multi-Strategy Backtest & Strategy Selector |
| `docs/position-action-guide-v0.11.1.md` | Position Action Guide v0.11.1 |
| `docs/position-context-v0.11.md` | Position Context + Automated Strategy Checks v0.11 |
| `docs/production-exit-policy-v0.21.4-B.2.1.md` | Production Exit Policy — v0.21.4-B.2.1 |
| `docs/pullback-confirmation-v0.16.5.md` | Pullback Confirmation Engine v0.16.5 |
| `docs/relative-strength-v0.16.md` | Relative Strength v0.16 |
| `docs/risk-engine-v0.10.md` | Risk Engine v0.10 |
| `docs/scanner-candidate-ranking-v0.21.3.md` | v0.21.3 Scanner Candidate Ranking & Priority Explanation |
| `docs/sector-relative-strength-v0.16.4.md` | Sector Relative Strength v0.16.4 |
| `docs/stock-code-domain-v0.8.1.md` | StockCode Domain Rule v0.8.1 |
| `docs/stock-scanner-v0.21.md` | Scanner 초기 485일 준비·후보 설명; 현재 0.21.3.9 경로와 다른 과거 가정 |
| `docs/strategy-v0.6.md` | Strategy Engine v0.6 |
| `docs/strategy-v0.8.md` | Strategy + Stock Search v0.8 |
| `docs/technical-analysis-v0.7.md` | Technical + Strategy Analysis v0.7 |

### M7. 제품 UX·입력·성능 설명 — 26개

- 분류: **MERGE_INTO_ACTIVE**
- 통합/유지 대상: M의 UX 절; I의 시점/캐시/입력/진행·취소 계약 절
- 이유: 작은 UX 버전 문서들을 현재 동선과 불변식으로 통합한다. 구 화면/구 입력 제어를 새 설계로 되살리지 않는다.
- 삭제 후 정보 유실 여부: 현재 행동/가격/시각·stale·세션·취소 규칙을 이전한 후 현재 정보 유실 없음. 픽셀/과거 미세 튜닝은 Git history.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/action-plan-readability-v0.21.2.2.md` | Action Plan Readability v0.21.2.2 |
| `docs/action-plan-v0.17.1.md` | Action Plan UX v0.17.1 |
| `docs/analysis-hub-v0.16.5.md` | Analysis Hub v0.16.5 |
| `docs/backtest-action-ux-v0.19.7.md` | v0.19.7 — Backtest Action UX |
| `docs/backtest-performance-v0.19.1.md` | v0.19.1 — 눌림목 백테스트 성능 최적화 |
| `docs/backtest-problem-solver-v0.19.2.md` | v0.19.2 — Backtest Problem Solver |
| `docs/beginner-explanation-v0.16.2.md` | Beginner Explanation Layer v0.16.2 |
| `docs/beginner-help-popover-v0.16.3.md` | Beginner Help Popover v0.16.3 |
| `docs/beginner-strategy-action-ux-v0.20.1.md` | v0.20.1 Beginner Strategy & Action UX |
| `docs/dark-ui-layout-polish-v0.20.2.1.md` | v0.20.2.1 Dark UI & Layout Polish |
| `docs/decision-status-auto-check-v0.16.6.md` | Decision Status & Auto Check UX v0.16.6 |
| `docs/input-ux-v0.15.2.md` | 롱프레스·누적 % 입력; 이후 제거된 OHLC 바로가기 설명 포함 |
| `docs/input-ux-v0.15.3.md` | OHLC 바로가기 제거, 선택 장중 입력 Stepper와 EOD fallback |
| `docs/input-ux-v0.15.md` | Input UX v0.15 |
| `docs/investor-style-ux-compression-v0.18.2.1.md` | Investor Style UX Compression v0.18.2.1 |
| `docs/navigation-backtest-ux-v0.19.3.md` | v0.19.3 — Navigation & Backtest UX Restructure |
| `docs/relative-strength-v0.16.1.md` | Relative Strength v0.16.1 — Result First |
| `docs/result-card-consistency-v0.20.2.3.md` | v0.20.2.3 결과 카드 정합성 |
| `docs/scanner-fast-start-progress-v0.21.0.1.md` | v0.21.0.1 — Scanner Fast Start & Progress |
| `docs/scanner-market-bootstrap-performance-v0.21.0.3.md` | v0.21.0.3 — Market Bootstrap Performance |
| `docs/scanner-price-plan-v0.21.4-A.4.md` | Scanner Price Plan & Entry Position Clarity |
| `docs/scanner-result-persistence-v0.21.4-A.3.md` | Scanner Result Persistence & Back Navigation — v0.21.4-A.3 |
| `docs/setup-data-freshness-v0.14.md` | v0.14 - 새 PC 재현성 / KRX 데이터 최신성 가이드 |
| `docs/single-stock-backtest-fast-path-v0.21.4-A.1.md` | v0.21.4-A.1 — Single-Stock Backtest Fast Path |
| `docs/single-stock-cold-start-v0.21.4-A.1.1.md` | v0.21.4-A.1.1 Cold Start Path |
| `docs/visual-concrete-action-ux-v0.20.2.md` | v0.20.2 — 가독성·다크모드·구체적 행동 안내 UX |

### D1. 만료된 handoff와 완료된 문서작성 task spec — 5개

- 분류: **DELETE_REDUNDANT**
- 통합/유지 대상: 현재 상태는 B/J/I/R; 이력은 H에 날짜·당시 HEAD·결론 한 줄
- 이유: 과거 open PR·NEXT·BLOCKED·새 채팅 지시가 현재 흐름과 충돌한다. 실제 결과/계약을 authority로 남기고 전달문은 제거한다.
- 삭제 후 정보 유실 여부: 현재 규칙 유실 없음. 당시 대화 복구·작업 지시 상세는 제거 의도이며 Git revision에서 복원. 고유 결정 발견 시 삭제 대신 M으로 전환.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/StockScope_HANDOFF_2026-09-28_P5S1E_COMPLETE.md` | Handoff — 2026-09-28 — P5-S1-E Complete |
| `docs/StockScope_HANDOFF_2026-10-01_NEXT6D_S2_COMPLETE.md` | Handoff — 2026-10-01 — NEXT-6D-S2 Complete |
| `docs/StockScope_인수인계_2026-10-02_NEXT6E_R3_BLOCKED.md` | 인수인계 — 2026-10-02 / NEXT-6E R3 BLOCKED |
| `docs/StockScope_NEXT6E_POST_S5_DESIGN_DOCUMENT_TASK_SPEC_2026-10-02.md` | NEXT-6E Post-S5 — Design Document Task Specification |
| `docs/StockScope_NEXT6E_S5_REFERENCE_ADEQUACY_GOVERNANCE_TASK_SPEC_2026-10-02.md` | NEXT-6E-S5 — Reference Adequacy Method & Risk-Budget Governance Review |

### D2. 국소 수정·표시 패치 기록 — 4개

- 분류: **DELETE_REDUNDANT**
- 통합/유지 대상: 현재 소스/회귀; 공통 UX 원칙은 M7 통합 내용
- 이유: 다크 표면 수정·NameError·KST fallback 같은 좁은 패치 설명이다. 현재 정책 owner가 아니며 실제 코드/회귀와 일반 원칙으로 복원 가능하다.
- 삭제 후 정보 유실 여부: 현재 정책 유실 없음. 과거 증상 서술은 Git 이력으로 보존. 날짜/가격/권한 정책을 삭제하는 뜻이 아님.

| 실제 파일 경로 | 현재 역할 |
| --- | --- |
| `docs/quick-analysis-dark-ui-v0.21.2.1-hotfix1.md` | v0.21.2.1 hotfix1 — Action Plan Dark Surface |
| `docs/quick-analysis-dark-ui-v0.21.2.1.md` | v0.21.2.1 Quick Analysis Dark UI Consistency Polish |
| `docs/runtime-nameerror-fix-v0.20.2.2.md` | v0.20.2.2 Runtime NameError Fix |
| `docs/scanner-windows-kst-hotfix-v0.21.0.2.md` | Scanner Windows KST hotfix v0.21.0.2 |

## 7. 통합할 때의 정보 보존 체크리스트

M6/M7의 58개 소형 설명 파일을 그냥 삭제하지 않는다. 다음 계약 묶음으로 짧게 재작성하고 현재 code/test owner를 연결한다.

| 묶음 | 필수 보존 / 오래된 가정 처리 |
| --- | --- |
| Strategy·Risk·entry guide | 적합도≠확률, NO_TRADE/Risk 우선, 구조·ATR owner, 기존 조건의 가격 번역, 새 threshold 발명 금지 |
| Scanner·ranking·historical evidence | 현재조건/순위와 과거 근거 분리, top/more/반환 범위, 캐시/selection/exit identity, 0.21.3.9 완료 상태 |
| Backtest·exit research/selection/production | D+1·일봉 순서·비용·CENSORED, 연구/운영 분리, 선택/청산 정책 별도 pin, 과거 고정 Target1과 현재 mapping 혼동 금지 |
| Fundamental·event·relative strength | 공식 보고서 시점/동기간, EOD 기준, 시장/업종 비교와 source 한계, 기존 규칙 공시와 P6/AI 권한 분리 |
| manual reference·position·input UX | EOD 원본 불변, 참고가격 시나리오 구분, quantity/plan을 자동 변경하지 않음, 입력 변경 시 stale |
| UX·설명·도움말·세션 | 결론→행동→핵심 근거, 관찰/체결·표시/계산 구분, 원시 수치/상세 접힘, back navigation·reload·재분석·취소 |
| 성능·data freshness·setup | market store/cache/network 책임, budget·progress/cancel, 현재 설치/복구 절차·시각 의미. 역사 성능 수치를 현재 SLA로 사용 금지 |

삭제 후보 D2의 KST 규칙은 `backend/app/market/kst.py`와 해당 회귀, NameError 수정은 현재 `multi_strategy.py` 및 backtest 회귀를 근거로 유지한다. dark UI는 현재 CSS/컴포넌트와 theme 회귀 기준으로 확인한다. 이런 불변식이 active 통합에서 빠졌다면 원본 제거를 보류하고 manifest를 정정한다.

## 8. 다음 cleanup 작업의 순서

1. 사용자 검토 이후의 main을 다시 확인하고 이 manifest의 154개 목록과 차이를 좁게 대조한다. 새 파일을 자동 삭제 분류하지 않는다.
2. M 맨 앞 읽기 순서와 B의 현재 상태를 정리한다. JEV/R5R 명칭 안내를 추가한다.
3. H 하나를 작성해 §4 ledger와 보존 원본 링크를 넣고, M1~M7의 유효 계약을 지정 active 절에 통합한다. 이 단계에서 원본은 아직 유지한다.
4. 파일별 옛 요구/결정이 어디로 옮겨졌는지 연결표를 검수한다. 잃으면 안 되는 정보가 있으면 먼저 보완한다.
5. 문서·README·tools/source/test의 inbound 링크를 점검한다. 일반 문서 링크는 active/H의 해당 절로 바꾸고 frozen JSON/코드 경로 참조는 원본 보존을 우선한다.
6. 그 뒤 D1/D2와 검수 완료된 MERGE 원본만 제거한다. broad wildcard 삭제나 전체 archive 이동을 하지 않는다. H1~H3/JSON/fixtures는 보존한다.
7. 문서 링크·분류 coverage·기준 SHA·상태/명칭·변경 파일 범위를 확인한다. 코드/데이터 영향이 없으면 평가나 전체 앱 테스트를 cleanup 검증 수단으로 실행하지 않는다.

이 계획이 그대로 완료되고 95개 통합 원본과 9개 redundant가 모두 제거되는 경우, 기존 154개 중 50개가 남는다. 이번 새 문서 2개와 다음 H 1개를 더한 **예상 docs 수는 53개**다. 링크 예외/추가 고유 증거가 있으면 실제 수는 달라질 수 있으며 원본 삭제를 숫자 목표로 강제하지 않는다. KEEP_HISTORY 33개를 모두 새 archive에 옮기는 계획은 아니다.

## 9. 이번 작업의 검수와 다음 작업

검수 기준은 실제 main 파일 목록 154개의 누락/중복 없는 분류, 현재 machine artifact 27개 전부 보존, 핵심 baseline 4개 보존, JEV concept superseded 분류, R5R 과거/현재 gate 구분, R5R/AI 평가 명칭 분리, 고유 proof/직접 경로 참조 보존이다.

**계획 작성 당시 상태:** 신규 설계/계획 문서 2개만 작성했고 기존 문서 정리는 아직 실행하지 않았었다.  
**현재 실행 결과:** 아래 §10에 기록한 cleanup 실행이 완료됐다. Production code, JEV/R5R actual evaluation, DEV T/L/S/Common-N 계산, Holdout 접근, threshold 조정은 수행하지 않았다.

Docs cleanup 실행은 완료됐다. 다음 작업은 **JEV-SHADOW-IMPLEMENT**다. R5R 실제 평가는 별도 **NEXT-6E-R5R-EVALUATION**으로 유지한다.


## 10. Cleanup 실행 결과 — 2026-10-06

실행 기준선:

```text
pre-cleanup planning baseline
=
893f2b96289a02f7cfce46b2a4ea7abb0d86326c
```

실제 수행:

- JEV v2를 authoritative active design으로 main에 반영.
- canonical JEV credential env를 `JEV_API_KEY`로 문서화하고 `.env.example`에는 빈 placeholder만 추가.
- Master / Implementation Baseline / Roadmap / R5R baseline / Macro-Event architecture / README / tools README를 현재 기준에 맞게 통합.
- `docs/history/StockScope_R4_R5_R5R_설계변경이력.md` 생성.
- R5R actual evaluation과 AI JEV reviewer evaluation 명칭을 분리.
- Active 문서의 오래된 handoff/current-state/legacy guide 링크를 현재 baseline/history로 교체.
- `MERGE_INTO_ACTIVE` 95개와 `DELETE_REDUNDANT` 9개를 manifest의 explicit path 목록으로 제거.
- wildcard 삭제 및 전체 archive 이동은 사용하지 않음.

삭제 결과:

```text
MERGE 원본 제거
=
95

DELETE_REDUNDANT 제거
=
9

total removed
=
104
```

현재 docs:

```text
Markdown
=
25

JSON
=
27

DOCX
=
1

total
=
53
```

보존 검증:

- KEEP_ACTIVE / KEEP_HISTORY 누락 0.
- 제거 대상 104개 잔존 0.
- machine-readable JSON 27개의 Git blob SHA 변경 0.
- contracts / bindings / fixtures / review JSON은 rename·move·reserialize하지 않음.
- remaining Markdown의 repository-local 링크를 검사하고 active stale link를 교체함.
- Holdout 접근 0.
- R5R actual evaluation 0.
- JEV model call/evaluation 0.
- DEV T/L/S/Common-N 계산 0.

현재 문서 읽기 순서:

1. `StockScope_MASTER_ARCHITECTURE_vNext.md`
2. `StockScope_IMPLEMENTATION_BASELINE_vNext.md`
3. 현재 작업 기준: R5R baseline 또는 JEV v2
4. `StockScope_DEVELOPMENT_ROADMAP_vNext.md`
5. 필요 시 `history/StockScope_R4_R5_R5R_설계변경이력.md`

다음 작업:

```text
JEV-SHADOW-IMPLEMENT
```

R5R actual observed-path 실행은 별도:

```text
NEXT-6E-R5R-EVALUATION
```

으로 유지한다.
