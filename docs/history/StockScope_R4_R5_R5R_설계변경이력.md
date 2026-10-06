# StockScope R4·R5·R5R 설계 변경 이력

작성일: 2026-10-06 (Asia/Seoul)  
Cleanup 기준 revision: `893f2b96289a02f7cfce46b2a4ea7abb0d86326c`  
지위: **History / audit entry point**. 현재 계산 authority는 frozen JSON과 Active baseline이 우선한다.

## 읽는 법

이 문서는 과거 narrative 문서를 계속 현재 필독으로 남기지 않기 위한 결정 ledger다. 삭제된 원문은 Git history의 위 기준 revision 및 각 경로에서 복원할 수 있다. 과거 BLOCKED/FAIL을 현재 PASS로 재작성하지 않는다.

현재 기준:
- R5R baseline: `docs/설계/StockScope_NEXT6E_R5R_통합설계기준_2026-10-05.md`
- Method: `docs/contracts/NEXT6E_S6A_R5R_METHOD_CONTRACT_V2.json`
- Policy: `docs/contracts/NEXT6E_S6B_R5R_POLICY_V1.json`
- Binding: `docs/bindings/NEXT6E_R5R_EVALUATION_BINDING_V1.json`
- Deterministic review: `docs/reviews/NEXT6E_S6A_R5R_DETERMINISTIC_REVIEW_RESULT_V2.json`

## R2~S6 초기 Reference Adequacy

초기 Reference Adequacy 흐름은 Development 자료에서 문제를 발견하고 보완하는 성격이 강했다. 따라서 이후 설계에서 “처음부터 data-blind policy였다”고 재해석하지 않는다. Path description과 population inference를 분리하고, 실제 결과를 본 뒤 threshold를 맞추지 않는 원칙이 점차 강화됐다.

대표 당시 narrative:
- `docs/StockScope_NEXT6B_S4_2B16_R2_BLOCKER_REVIEW_2026-09-30.md`
- `docs/StockScope_NEXT6B_S4_2B16_R22_POLICY_RESOLUTION_REVIEW_2026-10-01.md`
- `docs/StockScope_NEXT6B_S4_2B16_R23_REFERENCE_ADEQUACY_PREREGISTRATION_2026-10-01.md`
- `docs/StockScope_NEXT6B_S4_2B16_R241_JOINT_INFERENCE_BUDGET_CLOSURE_2026-10-01.md`
- `docs/StockScope_NEXT6B_S4_2B16_R242_PATH_DISPOSITION_INDEPENDENCE_RECOVERY_2026-10-01.md`
- `docs/StockScope_NEXT6B_S4_2B16_R24_DEPENDENCE_RISK_GOVERNANCE_REVIEW_2026-10-01.md`
- `docs/StockScope_NEXT6B_S4_2B16_R24_METHOD_RISK_GOVERNANCE_2026-10-02.md`

현재 영향: 이 흐름은 R5/R5R로 superseded되었고 현재 gate authority가 아니다.

## R3 / R4 — Population-level 실제 적용 한계

R3/R4에서 lattice/quantization, stationarity/mixing, dependence assumption을 실제 DGS10 process에 연결하려 했다. 진단에서 특정 가정을 기각하지 못했다는 사실은 그 가정의 승인과 다르다는 원칙을 확정했다.

대표 원문 중 고유 설계/직접 참조 때문에 유지:
- `docs/StockScope_NEXT6E_S6A_R3_방법론_Blocker_해소_설계_2026-10-03.md`
- `docs/StockScope_NEXT6E_S6A_R4B_GA_승인패키지_2026-10-03.md`
- `docs/StockScope_NEXT6E_S6A_R4C_GA_최종판정_2026-10-03.md`

삭제되는 중간 narrative의 결론은 여기와 Active baseline에 흡수한다. R4 model-use 결과를 retroactive PASS로 바꾸지 않는다.

## R5 D2A/B/C — Candidate 구조

결정:
- atomic/local-time 문제를 별도 검토했다.
- simultaneous index 구조를 단순 무한 영역으로 두지 않고 prospective finite anchor grid를 선택했다.
- grid는 `j/20, j=2..19`, integer mapping은 `ceil(j*n/20)`.
- collision은 smallest-j canonical.
- all-later와 latest-state를 유지했다.

삭제되는 중간 narrative:
- `docs/NEXT6E_S6A_R5_D2A_Atomic_LocalEDF_Boundary_Simultaneous_정리해소_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2B_Simultaneous_Index_Architecture_결정_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2C_Finite_Anchor_Grid_Governance_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2_방법계약_정리해소_2026-10-04.md`

현재 영향: candidate 구조는 R5R CandidateDomain V1에서 별도 frozen authority를 가진다.

## R5 D2D / D2E — Population theorem 시도와 calibration 실패

Local weighted inference, atomic variance, Gaussian/bootstrap calibration을 검토했고 실제 사용에 필요한 상수와 calibration을 충분히 닫지 못했다. 이후 analytical conservative concentration band로 전환했다.

고유 논증 때문에 유지:
- `docs/NEXT6E_S6A_R5_D2D1_Local_Weighted_Atomic_Max_Inference_Resolution_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2D2_Weighted_Gaussian_Calibration_Resolution_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2E1_Conservative_LocalCDF_Concentration_Band_Design_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2E2_Theorem_Chain_Consolidation_2026-10-05.md`

삭제되는 연결 narrative:
- `docs/NEXT6E_S6A_R5_D2D_Finite_Anchor_LocalEDF_Theorem_Resolution_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2E0_Calibration_Blocker_Architecture_Reconsideration_2026-10-05.md`
- `docs/NEXT6E_S6A_R5_D2E_Final_Method_Contract_Freeze_2026-10-05.md`

현재 영향: legacy R5 theorem의 내부 정합성과 actual-process model-use 가능성을 구분한다.

## GA1 / BR1 — Assumption ownership

GA1 독립 theorem review에서 assumption ownership gap을 발견했고 BR1에서 계약 ownership을 해소했다. 그 결과 theorem review 자체는 통과할 수 있었지만 actual process에 적용할 수 있다는 뜻은 아니었다.

유지:
- `docs/reviews/NEXT6E_S6A_R5_GA1_Independent_Theorem_Review_2026-10-05.md`
- theorem review/result JSON lineage

삭제되는 BR1 narrative의 결정은 위 원본과 JSON에서 추적한다:
- `docs/reviews/NEXT6E_S6A_R5_GA1_BR1_Assumption_Ownership_Resolution_2026-10-05.md`

## GA2 / BR1 — Actual-process model-use BLOCKED

실제 DGS10 observed path 진단 후 R5의 iid innovation, dependence, local approximation, time smoothness, moment bound를 감사 가능한 방식으로 모두 bind하지 못했다.

당시 결론:
- `MODEL_USE_BINDING_ROUTE = PARTIALLY_FEASIBLE`
- `COMPLETE_AUDITABLE_ROUTE_FOR_CURRENT_R5 = NO`
- `METHOD_USE_REDESIGN = REQUIRED`

삭제되는 narrative:
- `docs/reviews/NEXT6E_S6A_R5_GA2_Model_Use_Acceptance_2026-10-05.md`
- `docs/reviews/NEXT6E_S6A_R5_GA2_BR1_Model_Use_Evidence_Route_Resolution_2026-10-05.md`

관련 machine result/route JSON은 History로 계속 보존한다.

## MUR1 — R5R observed-path 전환

R5의 population-level claim을 억지로 통과시키지 않고 새 architecture:
`R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1`
를 선택했다.

핵심:
- population stability/future guarantee를 주장하지 않는다.
- fixed observed path의 empirical drift를 직접 측정한다.
- R5R은 R5의 PASS patch가 아니라 새 target/method family다.

삭제되는 비교 narrative:
- `docs/reviews/NEXT6E_S6A_R5_MUR1_방법사용_재설계_아키텍처_비교_2026-10-05.md`

machine redesign decision JSON은 보존한다.

## MUR2 — R5R 계약 freeze

확정:
- T_EMP: exact ECDF sup distance
- L_EMP: anchor MAD로 정규화한 midpoint median shift
- S_EMP: anchor MAD relative scale shift
- window: `ceil(n/10)`
- candidate grid: 18 anchors
- all-later/latest
- Common-N은 observed-path retrospective suffix summary일 뿐 minimum population sample size가 아님

삭제되는 상세 narrative:
- `docs/NEXT6E_S6A_R5_MUR2_관측경로_경험적안정성_계약설계_2026-10-05.md`

현재 exact authority는 Method V2 / CandidateDomain / Window JSON이다.

## MUR3 / BR1 — Deterministic ambiguity 해소

MUR3에서 세 ambiguity를 발견:
1. missing horizon / joint chronology
2. chronology hash canonicalization
3. exact numeric comparison

BR1에서:
- PREBOUND_COMPLETE_JOINT_CHRONOLOGY
- R5R_JOINT_CHRONOLOGY_HASH_V1
- R5R_EXACT_RATIONAL_V1

로 해소했다.

삭제되는 narrative:
- `docs/reviews/NEXT6E_S6A_R5_MUR3_R5R_결정론적_계약_검토_2026-10-05.md`
- `docs/reviews/NEXT6E_S6A_R5_MUR3_BR1_R5R_계약_모호성_해소_2026-10-05.md`

V1/V2 machine review와 fixture는 보존한다.

## POLICY — 초기 운영 정책

현재 active policy:
- T_EMP = GATE, tau_T = 0.10
- L_EMP = GATE, tau_L = 0.50
- S_EMP = GATE, tau_S = 0.25
- ALL_HORIZONS_AND / ALL_METRICS_AND / ALL_LATER_STATES
- 결과에 맞춘 완화 금지

Policy V1이 현재 authority다. 이 값은 population truth나 industry standard가 아니라 내부 reference reuse의 초기 operational policy다.

## IMPLEMENT — Evaluator / DEV Binding

완료:
- pure R5R evaluator
- deterministic tests
- frozen DEV identity/chronology binding
- G0~G4 PASS
- actual R5R evaluation은 아직 실행하지 않음

현재 naming:
- `NEXT-6E-R5R-EVALUATION`: R5R observed-path actual evaluation
- `JEV-REVIEWER-EVALUATION`: AI Decision Reviewer incremental-value evaluation

과거 `NEXT-6E-R5R-JEV`는 narrative historical alias로만 취급한다.

## JEV 설계 변경

2026-09-28 JEV concept의 유효 원칙(StockScope 중심, shadow-first, Risk 우회 금지, baseline 비교, explicit activation, fallback)은 v2에 흡수했다.

현재 JEV Phase 1:
- 역할: Decision Reviewer 하나
- 적용점: Scanner 반환 ENTRY_CANDIDATE post-capture
- input: quant allowlist
- output: PASS_THROUGH / REVIEW_REQUIRED / ABSTAIN
- 기존 rank/action/Risk/plan 변경 금지
- 실제 AI 평가 단계명: JEV-REVIEWER-EVALUATION

Authoritative JEV:
`docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md`

구 JEV concept 원문은 cleanup 후 Git history에서만 복원한다.

## 삭제된 문서 복원 규칙

Cleanup에서 제거한 narrative는 정보의 현재 owner가 아니다. 과거 상세가 꼭 필요하면:
1. 이 ledger에서 단계/경로를 찾는다.
2. cleanup 기준 revision `893f2b96289a02f7cfce46b2a4ea7abb0d86326c`의 해당 경로를 연다.
3. 당시 verdict와 현재 effective state를 혼동하지 않는다.

문서 수를 줄인 이유는 audit 삭제가 아니라 **현재 authority와 과거 reasoning의 역할을 분리**하기 위해서다.

