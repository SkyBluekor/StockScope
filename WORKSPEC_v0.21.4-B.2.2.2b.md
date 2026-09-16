# StockScope v0.21.4-B.2.2.2b
## Analysis Date State Consistency Hotfix

### 목적
StockScope에서 최신 확정 거래일, Market Store의 시장별 저장 날짜, Scanner 결과의 분석 기준일, 최신화 실패 시 fallback 날짜가 서로 다른 규칙으로 계산되어 한 화면/흐름 안에서 날짜가 모순되는 문제를 수정한다.

### 확인된 실제 원인
- Frontend `latestScannerDataDate()`가 `data_dates`를 정렬한 뒤 가장 큰 날짜를 반환했다.
- 따라서 `KOSPI=2026-09-15`, `KOSDAQ=2026-09-14`처럼 시장별 날짜가 다른 결과도 `2026-09-15` 하나의 정상 분석 기준일처럼 표시될 수 있었다.
- Backend freshness는 별도의 공통 저장 날짜를 기준으로 fallback을 계산해 2026-09-14를 반환할 수 있었다.
- 기존 freshness 검증은 stock 일자 중심이었고, 동일 날짜의 대표 시장지수까지 함께 완료됐는지 하나의 규칙으로 검증하지 않았다.

### 핵심 원칙
1. KOSPI/KOSDAQ 전체 분석은 선택 시장의 주식 일봉과 대표 시장지수가 같은 날짜에 모두 준비된 경우에만 하나의 분석 기준일로 인정한다.
2. 현재 사용 중인 날짜가 실제 Market Store에서 유효하면 최신화 실패 때문에 더 과거 날짜로 자동 후퇴하지 않는다.
3. 새로운 날짜는 필요한 시장 데이터가 모두 저장·검증된 뒤에만 `resolved_as_of_date`로 승격한다.
4. 현재 결과가 시장별 혼합 날짜라면 가장 큰 날짜를 대표 날짜로 표시하지 않는다. `확정 일봉 확인 필요` 상태로 처리한다.
5. 이전 날짜 fallback 버튼은 Backend가 `fallback_allowed=true`로 명시한 경우에만 표시한다.
6. 장중 미확정 데이터 사용, 시장별 날짜 혼합, 자동 과거 fallback은 계속 금지한다.

### Backend 변경
대상: `backend/app/backtest/scanner.py`

- `StockScannerService.VERSION`을 `0.21.3.1`로 올려 기존 혼합 날짜 Scanner cache를 자동 무효화한다.
- 날짜 정규화 helper 추가.
- 선택 시장 전체에서 stock + index가 정확히 같은 날짜에 존재하는지 확인하는 `_date_complete_for_markets()` 추가.
- stock/index 양쪽을 포함한 최신 공통 확정일 계산 `_latest_common_complete_date()` 추가.
- Scanner cache가 요청 기준일과 시장별 `data_dates`가 모두 일치할 때만 재사용되도록 검증 추가.
- freshness 성공 시 새 날짜를 모든 시장의 stock/index 저장 완료 후에만 적용.
- 유효한 현재 기준일보다 Provider가 더 오래된 날짜를 반환하면 현재 날짜 유지.
- 최신화 실패 시:
  - 현재 날짜가 유효하면 `available_data_date`와 `resolved_as_of_date` 모두 현재 날짜 유지, fallback 금지.
  - 현재 날짜가 실제 저장 데이터와 불일치하면 `DATA_INCONSISTENT`로 구분.
  - 유효한 현재 날짜가 없는 경우에만 마지막 공통 확정일을 명시적 fallback 후보로 제공.
- pinned `as_of_date`로 Scanner를 실행할 때 실제 시장별 최신 데이터가 그 날짜와 일치하지 않으면 혼합 날짜 분석을 중단한다.

### Frontend 변경
대상:
- `frontend/src/components/scannerSession.ts`
- `frontend/src/components/ScannerPanel.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`

#### Scanner 날짜 판정
- `latestScannerDataDate()`의 max-date 방식 제거.
- `resolveScannerDataDate()` 도입.
- 필요한 시장 날짜가 하나라도 없거나 서로 다르거나 `requested_as_of`와 다르면 단일 분석 날짜를 반환하지 않는다.

#### 최신화 요청
- 기존 Scanner 결과가 주장한 `requested_as_of`를 Backend에 전달하고 Backend가 실제 Market Store와 대조하도록 한다.

#### 오류/경고 UI
- 현재 날짜가 유효하고 새 데이터 확인만 실패한 경우 큰 오류가 아니라 warning tone 사용.
- 이 경우 현재 유효 날짜를 계속 사용할 수 있음을 표시하고 과거 날짜 fallback 버튼은 숨긴다.
- 실제 기준일 불일치 시 `현재 분석 기준 데이터를 다시 확인해야 합니다`로 구분한다.
- Backend 상세 원인은 보조 정보로만 표시한다.
- 혼합 시장 날짜의 기존 결과는 `확정 일봉 확인 필요`로 표시한다.

#### Dashboard 문구
- 빠른 조회 상단의 `데이터 기준`을 `시장 요약 기준`으로 변경해 Market Dashboard 날짜를 앱 전체의 단일 분석 기준일처럼 오해하지 않도록 한다.

### 테스트 시나리오
1. 현재 2026-09-15가 stock/index 양쪽에서 유효 + 최신화 실패
   - 2026-09-15 유지
   - 2026-09-14 후퇴 금지
   - fallback 버튼 금지
2. 현재 결과가 2026-09-15를 주장하지만 실제 공통 저장 데이터는 2026-09-14
   - `DATA_INCONSISTENT`
   - 자동 9/14 실행 금지
   - 명시적 fallback만 허용
3. Provider가 로컬 유효 날짜보다 오래된 날짜를 반환
   - 현재 유효 날짜 유지
4. 9/14 -> 9/15 갱신 성공
   - KOSPI/KOSDAQ stock/index 모두 9/15 완료 후에만 9/15 적용
5. 혼합 Scanner cache
   - 재사용 금지
6. Frontend `KOSPI=9/15, KOSDAQ=9/14`
   - 9/15로 표시 금지
   - 날짜 불일치 상태 처리

### 기존 기능 보존
- Dark Theme B.2.2.1
- Typography/Readability B.2.2.2
- Strategy Tab Hotfix B.2.2.2a
- Profit Protection B.2.2
- Scanner ranking/전략/Risk 계산
- 과거 성과 검증 및 Research Workspace

### 제외 범위
- 실시간 시세 도입
- KRX Provider 교체
- 전략/점수/Ranking 변경
- 매도 정책 변경
- 연구 알고리즘 변경

### 완료 기준
- 유효한 2026-09-15 분석 기준일이 최신화 실패 때문에 2026-09-14로 자동 후퇴하지 않는다.
- 시장별 날짜가 다른 결과를 가장 최신 날짜 하나로 포장해 보여주지 않는다.
- 새 기준일은 KOSPI/KOSDAQ의 stock/index가 모두 같은 날짜로 검증된 이후에만 적용된다.
