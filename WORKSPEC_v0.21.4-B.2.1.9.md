# StockScope v0.21.4-B.2.1.9 작업 명세

## Expanded Sample Revalidation

### 목적
현재 20종목 매도 기준 연구에서 일부 전략이 종목 구성에 민감하게 반응한 결과를 바탕으로, 기존 연구 조건을 그대로 유지한 채 더 넓은 종목 표본에서 같은 결론이 유지되는지 재검증한다.

### 사용자 흐름
1. 기존 연구 결과와 신뢰성 검증을 확인한다.
2. `확대 표본 검증 준비`를 누른다.
3. 40종목(권장) 또는 60종목을 선택한다.
4. 저장된 시세 데이터가 충분하면 추가 다운로드 없이 바로 재검증한다.
5. 데이터가 부족하면 `검증 데이터 준비`를 사용자가 직접 실행한다.
6. 준비 완료 후 확대 표본 연구를 실행한다.
7. 기존 표본과 확대 표본의 전략별 결론을 자동 비교한다.
8. 확대 연구가 끝난 뒤 신뢰성 검증을 다시 실행할 수 있다.

### 표본 선정 규칙
- 기존 연구에 사용된 종목은 확대 표본에도 그대로 포함한다.
- 추가 종목은 기존 연구 기간에서 데이터 보유율 기준을 만족하는 종목만 사용한다.
- KOSPI/KOSDAQ을 가능한 한 균형 있게 추가한다.
- 연구 결과에 유리한 종목을 임의로 골라 넣지 않는다.
- 기본 확대 표본은 40종목이며 60종목까지 지원한다.

### 비교 조건 고정
확대 표본 재검증에서는 종목 수 외 다음 조건을 기존 연구와 동일하게 유지한다.
- 연구 시작일 / 종료일
- 초기 자본
- 왕복 거래비용
- 최대 보유기간
- 최소 데이터 보유율
- 정책 선택 최소 종목 수
- 정책 선택 최소 거래 수
- 2차 목표가 이후 연구 기간
- 10개 전략 및 Exit 후보

비교 조건 fingerprint는 `max_stocks`를 제외한 연구 조건으로 계산한다.

### 데이터 준비
- Scanner 실행과 분리한다.
- 이미 Market Store에 완료 표시된 날짜는 재요청하지 않는다.
- 부족한 과거 시장 일별 데이터만 준비한다.
- 주식 일별 API는 날짜별 시장 전체 응답을 Market Store에 저장해 이후 종목이 재사용한다.
- 시장지수 데이터도 같은 기간에 함께 준비한다.
- KRX 요청 예상량을 실행 전에 표시한다.
- KRX API budget 검사를 통과한 경우에만 시작한다.
- 사용자가 명시적으로 버튼을 누르기 전에는 네트워크 다운로드를 시작하지 않는다.

### 진행률
데이터 준비와 확대 연구는 각각 기존 cancellable Backtest Job 구조를 사용한다.
- 데이터 준비: 완료 항목 / 전체 부족 항목
- 확대 연구: 완료 종목 / 전체 확대 표본

### 결과 보존
- 기존 20종목 리포트를 확대 연구로 덮어쓰지 않는다.
- 연구 signature별 리포트를 별도 archive 파일로 보존한다.
- 최신 리포트 파일은 현재 화면 복원용으로 계속 유지한다.

### 확대 결과 비교
확대 연구 완료 후 다음 정보를 저장하고 표시한다.
- 기존 표본 수 → 확대 표본 수
- 동일 조건 여부
- 10개 전략 중 같은 결론 유지 개수
- 결론 변경 개수
- 전략별 이전 상태 → 확대 후 상태
- 이전 신뢰성 검증에서 민감했던 전략의 상태 변화

### Production 안전선
- 확대 연구 실행만으로 실제 매도 기준을 변경하지 않는다.
- Production activate는 실행하지 않는다.
- 확대 결과에 새 후보가 생겨도 별도 검토 후 적용한다.

### 함께 보정한 항목
현재 실제 적용 기준 API가 backend reload 순간 일시 실패하는 경우를 줄이기 위해 frontend에서 짧은 자동 재시도를 추가한다.
계속 실패할 경우 전체 연구 결과를 오류 처리하지 않고 `다시 확인` 버튼만 표시한다.

### 변경 파일
- `backend/app/api/backtest.py`
- `backend/app/backtest/expanded_sample_validation.py` (신규)
- `backend/app/backtest/market_store.py`
- `backend/app/backtest/exit_policy_validation_runner.py`
- `backend/app/backtest/service.py`
- `backend/tests/test_expanded_sample_validation_v0214b219.py` (신규)
- `frontend/src/components/BacktestPanel.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/styles.css`

### 변경하지 않는 것
- Exit 정책 선택 Pareto 알고리즘
- 기존 20종목 연구 결과
- Production mapping / activation
- 전략 Entry / Stop / Exit 계산식
- Scanner ranking
- EOD 기준일 정책

### 검증 기준
- 확대 표본 planner가 기존 표본을 유지하는지 확인
- KOSPI/KOSDAQ 추가 표본 균형 확인
- 비교 fingerprint가 종목 수 변경만 허용하는지 확인
- signature별 리포트 archive 확인
- 20→40/60 전략 상태 비교 확인
- TypeScript 정적 검사
- CSS 파싱
- Python compile
- ZIP 무결성 확인

### 버전 정의
`v0.21.4-B.2.1.9`는 현재 연구의 종목 표본만 확대하고 다른 연구 조건은 유지하여, 20종목에서 얻은 결론이 더 넓은 종목에서도 유지되는지 검증하기 위한 단계이다.
