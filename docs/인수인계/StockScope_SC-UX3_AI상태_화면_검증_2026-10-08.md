# StockScope Scanner SC-UX3 — 상태 신뢰성과 탭형 상세 검증

작성 기준: 2026-10-08 / GitHub PR #90  
범위: 사용자용 Scanner 화면·상태 표시·저장된 Jev 결과의 조회. Production Scanner, 전략, Ranking, Risk, Runtime 계산 변경 없음.

## 1. 확인한 실제 경로

1. Scanner: `backend/app/api/backtest.py`의 완료 처리 후 `enrich_scanner_result_with_ai_presentation` 실행.
2. 로컬 의미 분석: `backend/app/jev/review_presentation.py`에서 `provider_status=NOT_REQUESTED`, `provider_result=None`로 사용자용 준비 정보를 작성.
3. 기본 실행 상태: `execution_mode=BASELINE_ONLY`, `jev_review.status=NOT_REQUESTED`, `jev_shadow.status=NOT_REQUESTED`.
4. 기능 상태 API: `backend/app/api/jev.py`의 `GET /api/simulation/jev/review-feature`가 `feature_status=DISABLED_VALIDATION_PENDING`, `available=false` 반환.
5. 수동 AI 요청 API: `POST /api/simulation/jev/reviews`는 구현되어 있지만 `JevManualReviewService`에서 기능 비활성 또는 provider 미설정 시 거부. **이번 변경에서는 호출하지 않음.**
6. 저장된 결과 읽기: 기능 ACTIVE인 경우에 한하여 프론트에서 `GET /api/simulation/jev/reviews?capture_id=...`을 읽기 전용으로 사용. capture, sample index, ticker, market를 맞추고 서버가 반환한 VALID + MATCHED 무결성/모델 일치 + review_id + completed_at + disposition일 때만 AI 완료 표시.
7. 과거 검증: `historical_evidence` 별도 표시. 데이터 부족이 AI 기능 미제공의 원인이라는 주장을 하지 않음.

## 2. 변경 전/후 사용자 화면

| 영역 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 상단 AI 토글 | ON / OFF | 설정 켜짐 / 설정 꺼짐 (실제 모델 실행과 별개) |
| 추가 검토 진행 화면 | 로컬 의미 분석과 provider 검토를 혼동하기 쉬운 단계 | 기본 분석 완료와 실제 Jev 검토 상태를 별도로 표시 |
| 후보 목록 | AI 검토 상태가 보이지 않음 | 종목별 동일한 상태 판정 결과 표시 |
| 선택 종목 | 하나의 긴 상세 보고서 | 요약 / 전략·가격 / AI 검토 / 과거 검증 / 뉴스 단일 선택 탭 |
| 기본 요약 | 모든 정보가 아래로 연속 표시 | 선정 이유, 경고, AI·과거 상태, 핵심 가격, 최대 2건 뉴스 |
| 후보 비교 | 긴 상세 패널 뒤에 있음 | 후보 목록 바로 아래 |
| 과거 자료 없음 | 큰 상세 영역/경고 | 과거 상태 한 줄과 필요할 때만 데이터 준비 버튼 |
| 모바일 | 후보를 선택해도 상세까지 스크롤 필요 | 선택하면 상세 위치로 이동 |

이 표는 **코드 차이 기반 설명**이다. 실제 브라우저 전후 스크린샷은 현재 PC에서 추가 확보해야 한다.

## 3. 상태 표 및 검증

| 상태/근거 | 사용자 문구 | 출처·검증 |
| --- | --- | --- |
| 기본 분석 완료 | 기본 분석 완료 | Scanner result (모델 결과 아님) |
| AI 사용자 설정 꺼짐 | AI 검토 꺼짐 | UI 설정 |
| 기능 비활성 | AI 검토 기능 준비 중 | GET review-feature |
| 실행 안 함 | AI 검토 미실행 | BASELINE_ONLY / NOT_REQUESTED |
| 로컬 의미 정보 없음 | AI 검토 불가 · 입력 정보 부족 | ai_review_presentation.state |
| 실제 저장 요청 대기 | AI 검토 대기 중 | 캡처 일치 PENDING + review_id |
| 실제 처리 중 | AI 검토 중 | RUNNING 상태 |
| 검증된 저장 결과 | AI 검토 완료 / 추가 확인 필요 / 판단 보류 | 저장된 VALID + MATCHED + ID + completed_at |
| 오류·지연·중단 | AI 검토 실패 · 결과 확인 필요 | ERROR/LATE/INTERRUPTED |
| 무결성 불일치 | AI 검토 결과 확인 필요 | VALID이나 무결성 또는 모델 식별 불일치 |
| 과거 자료 부족 | 과거 검증 불가 · 데이터 부족 | historical_evidence |

반드시 지킬 조건: Jev confidence를 주가 상승률·투자 성공 확률로 해석하지 않는다. 현재 AI 완료/미실행 결과로 종목 순위와 전략, Risk를 변경하지 않는다.

## 4. 테스트 및 제약

- `frontend/tests/scannerAiReviewStatus.test.mjs`: 기본/로컬 완료 오해 방지, OFF/기능 미제공/입력 부족/미실행/대기/실패/유효 검토/판단 보류, 데이터 동일성 검사.
- `backend/tests/test_scanner_ai_truth_tabs_contract.py`: 모델 미실행 경계, 탭/뉴스 제한/후보 비교 위치/저장 결과 무결성 계약.
- 기존 SC-UX1·SC-UX2/보유·시장 데이터 준비 회귀 테스트 유지.
- 외부 provider 실호출, Canary, Holdout, 타 PC Runtime 동기화는 실행하지 않음.
- **미완료**: 실제 PC 1440x900/모바일 스크린샷과 상호작용 UAT; 실제 Jev 호출 성공·응답 내용/효용 비교(기능 비활성 정책상 불가능).
- **후속 검증**: 동일 후보 데이터로 AI 사용/미사용 시 확인 필요 항목 적중률과 확인 시간 비교. 실제 모델 호출 승인과 테스트 데이터를 별도로 확보해야 함.
