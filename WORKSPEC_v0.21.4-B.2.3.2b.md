# WORKSPEC v0.21.4-B.2.3.2b — Target1 Calculation & Realism Audit

## 목적
Scanner의 1차 목표가(Target1)가 (1) 현재 Risk Engine 공식과 정확히 일치하는지, (2) 과거 보유기간 안에서 어느 정도 거리/도달 특성을 보였는지 분리해서 진단한다.

이번 버전은 **감사/설명 계층**이다. Production Target1/Target2 공식, Scanner Ranking, Strategy score, Exit production mapping을 변경하지 않는다.

## 최신 Risk Engine 공식 확인
`backend/app/risk/engine.py` 기준 Target1은 다음 순서다.

1. 현재 분석 기준가(`entry = current_price`)보다 높은 `resistance_price`가 있으면 후보
2. 현재가보다 높은 `high20`이 있으면 후보
3. 유효 구조 목표 후보 중 **가격이 가장 가까운 값**을 Target1으로 선택
4. 구조 목표가 하나도 없을 때만 `entry + risk_amount * 1.5` 사용

따라서 `1.5R`은 Target1 상한이 아니다.

Target2는 기존 그대로:

- `target2_r = entry + risk_amount * 2.0`
- `target2 = max(target2_r, target1 + risk_amount * 0.5)`

## 구현 1 — 현재 Target1 독립 재검산
신규 파일:

`backend/app/backtest/target1_audit.py`

`build_current_target1_audit()`가 RiskPlan을 변경하지 않고 별도로 다음을 계산한다.

- Risk entry reference
- invalidation 기준 risk amount
- 1.0R / 1.5R / 2.0R 가격
- 유효 resistance / high20 후보
- 실제 Target1
- 실제 Target1 basis
- 기대 Target1 / 기대 basis
- Target1 거리 %
- Target1 risk multiple
- `MATCH / MISMATCH / UNAVAILABLE`

감사 결과는 `entry_risk_guide.risk.target1_audit`로 노출한다.

## 구현 2 — Target1 근거 API 노출
기존 RiskPlan에는 있었지만 Scanner용 concrete guide에서 빠져 있던 값을 노출한다.

- `target1_basis`
- `target2_basis`

따라서 UI에서 1차 목표가 왜 나온 값인지 표시 가능하다.

사용자 표시 예:

- 최근 저항
- 20일 고점
- 1.5R 손익 구조

## 구현 3 — 과거 Target1 현실성 감사
기존 3년 Historical Evidence가 실제 거래 history를 만들 수 있을 때 `build_historical_target1_audit()`를 추가 실행한다.

기본 수집값:

- sample count
- Target1 평균/중앙 거리 %
- Target1 평균/중앙 R multiple
- Target1 도달 수 / 과거 도달 비율
- 5/10/20 거래일 내 Target1 도달 수
- Target1 도달 평균/중앙 거래일
- Stop-first 수
- Time-exit 수
- 거리 bin: 0~5 / 5~10 / 10~15 / 15% 이상
- Target1 basis별 sample/평균 거리/평균 R

주의: 과거 도달 비율은 미래 성공확률이 아니다.

## 구현 4 — 연구용 대안 비교
Production 정책은 유지한 채 동일 Entry/Stop을 고정하여 다음 세 목표만 연구용으로 재생한다.

1. `BASELINE_STRUCTURAL` — 기존 Target1
2. `CAP_AT_1_5R` — `min(기존 Target1, 1.5R)`
3. `FIXED_1_5R` — 1.5R 고정

각 정책별:

- sample
- Target hit
- Stop first
- Time exit
- Average / median net
- Profit factor
- closed-trade MDD
- average holding days
- average Target hit days

을 계산한다.

### 중요한 한계
이 대안 비교는 **같은 관측 Entry/Stop을 고정한 replay**이다.

목표가가 바뀌면 실제 청산일이 달라지고, 그 결과 이후 신호에서 포지션 점유/재진입 가능 여부도 달라질 수 있으므로 **완전한 Production 정책 백테스트와 동일하지 않다.**

따라서 자동 정책 선택에 사용하지 않는다.

## 구현 5 — Scanner UI
Compact 후보 행:

- 1차 목표 가격
- Target1 근거
- 현재가 대비 거리 %

선택 상세:

- Target1 근거
- 현재가 대비 거리 %
- Risk multiple

Historical detail에 데이터가 있을 때:

- 평균 Target1 거리
- 평균 R
- 20거래일 내 과거 Target1 도달 건수
- Target1 도달 평균 거래일

을 표시한다.

Target1 독립 재계산이 `MISMATCH`일 때만 계산 확인 경고를 표시한다.

## 2026-09-17 화면 관측값
사용자 화면에서 관측된 15개 후보 Target1 거리의 단순 산술 검산:

- 최소 약 +3.47%
- 중앙값 약 +6.37%
- 평균 약 +7.62%
- 최대 약 +14.70%

대표적으로 큰 사례:

- 대우건설: 18,570 → 21,300, 약 +14.70%
- 메리츠금융지주: 125,000 → 139,100, 약 +11.28%
- DB손해보험: 187,000 → 208,000, 약 +11.23%
- 한국콜마: 150,000 → 165,900, 약 +10.60%
- 코스맥스: 280,500 → 306,500, 약 +9.27%
- 현대해상: 48,500 → 52,500, 약 +8.25%

이 값들은 **스크린샷에서 읽은 가격의 거리 검산**이다. 스크린샷만으로 각 Target1의 실제 basis(resistance/high20/1.5R)는 확정하지 않는다. B.2.3.2b 적용 후 API의 `target1_basis`로 확인한다.

## 변경 금지 확인
변경하지 않음:

- Risk Engine Production Target1 공식
- Risk Engine Production Target2 공식
- Stop / Invalidation 공식
- Strategy score
- Scanner Ranking
- KRX Pipeline
- Market Store
- Production Exit Policy mapping
- Profit Protection

## 테스트
실행 완료:

- `test_target1_audit_v0214b232b.py`
- `test_price_plan_consistency_v0214b232.py`
- `test_entry_stop_overlap_root_cause_v0214b232a.py`
- `test_entry_risk_guide_v0211.py`

Backend targeted: **59 passed**

Frontend static regression:

- `target1Audit_v0214b232b.py` PASS
- `pricePlanConsistency_v0214b232.py` PASS
- `pricePlanRootCause_v0214b232a.py` PASS

Python compile:

- `target1_audit.py` PASS
- `entry_risk_guide.py` PASS
- `historical_evidence.py` PASS

## 미검증 / 환경 제한
현재 overlay 조립 환경에는 원 프로젝트의 일부 기반 모듈(`backtest.models`, `history_store` 등)이 없어서 Scanner/Historical 전체 pytest collection은 완료하지 못했다.

또한 사용자 PC의 실제 Market Store 3년 데이터 자체가 이 실행환경에 없으므로, **실제 15개 현재 후보 각각의 target1_basis 및 실제 3년 정책 비교 수치까지 여기서 생성하지 않았다.**

B.2.3.2b 적용 후 사용자 PC에서 Scanner를 다시 실행하면 현재 후보의 Target1 basis가 화면에 표시되고, 충분한 Historical Evidence가 있는 후보는 Target1 과거 거리/도달 지표가 함께 표시된다.

## 완료 판단
이번 버전의 목표는 Production 목표가를 바꾸는 것이 아니라 다음 질문에 답할 수 있는 진단 구조를 만드는 것이다.

- 왜 이 Target1인가?
- Risk Engine 공식과 실제 값이 일치하는가?
- 현재가에서 몇 % 떨어져 있는가?
- 몇 R인가?
- 과거 동일 전략 거래에서 Target1은 어느 정도 거리였고 보유기간 안에 어떻게 작동했는가?
- 1.5R 대안과 비교하면 어떤 차이가 있었는가?

실제 사용자 Market Store 결과를 확인한 뒤 정책 변경이 필요하다고 판단될 경우 별도 후속 버전에서 검토한다.
