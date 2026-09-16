# v0.21.4-B.2.2.2c — Confirmed EOD Empty-Marker Hotfix

## 1. 배경
B.2.2.2b 적용 후 최신 확정 시세 준비 단계에서는 `2026.09.15 기준으로 분석` 안내가 표시됐지만, 실제 Scanner 실행 단계에서는 KOSPI/KOSDAQ 모두 2026.09.15에 맞추지 못했다는 오류가 발생했다.

## 2. 실제 원인
`HistoricalMarketStore.day_complete()`는 해당 날짜를 이미 확인했다는 의미로 `data`뿐 아니라 `empty` 상태도 완료로 취급한다. 이는 휴일/빈 응답의 반복 요청을 막는 용도에는 맞지만, Scanner의 `prepare_latest_confirmed_data()`가 이 값을 "실제 분석 가능한 확정 일봉이 존재한다"는 의미로 사용하고 있었다.

따라서 과거에 2026.09.15가 빈 응답으로 기록되어 `day_status=empty`가 남아 있으면:

1. 최신 시세 준비 단계가 9/15를 이미 준비된 날짜로 오판할 수 있다.
2. 실제 stock/index row는 9/15에 존재하지 않아도 `새로운 확정 시세를 반영했습니다`가 표시될 수 있다.
3. 이후 Scanner 본 실행의 `latest_complete_date(... status='data')`는 실제 데이터가 있는 9/14를 반환한다.
4. 결과적으로 준비 단계는 9/15 성공, Scanner 본 실행은 9/15 불일치로 실패하는 모순이 발생한다.

## 3. 수정 원칙
- `checked`와 `has data`를 구분한다.
- `empty` marker는 휴일/빈 응답 캐시에는 계속 사용할 수 있다.
- 분석 기준일 검증에는 실제 `status='data'`가 존재하는 날짜만 인정한다.
- 과거 empty marker가 있더라도 provider에 실제 데이터가 생겼다면 다시 조회하여 `data` 상태로 갱신한다.

## 4. Backend 수정
### 4.1 `_day_has_data()` 추가
정확한 날짜의 stock/index가 실제 data 상태인지 `latest_complete_date(market, kind, bas_dd) == bas_dd`로 검증한다.

### 4.2 `_date_complete_for_markets()` 수정
기존 `day_complete()` 대신 `_day_has_data()`를 사용하여 KOSPI/KOSDAQ의 stock/index가 모두 실제 data일 때만 분석 가능한 날짜로 인정한다.

### 4.3 최신 날짜 저장 단계 수정
resolved date의 stock/index에 기존 `empty` marker만 존재하면 완료로 간주하지 않고 provider를 다시 조회한다. 실제 rows가 확인되면 Market Store에 저장하면서 상태를 `data`로 갱신한다.

## 5. 기존 동작 유지
- 휴일/빈 날짜 자체의 checked marker는 삭제하지 않는다.
- 기존 History bootstrap의 중복 요청 방지 정책은 유지한다.
- 유효한 현재 분석일보다 과거 날짜로 자동 후퇴하지 않는 B.2.2.2b 규칙을 유지한다.
- Frontend UI, 전략, Risk, Scanner ranking, Backtest 로직은 변경하지 않는다.

## 6. 핵심 회귀 테스트
### Case A — 실제 재현 케이스
- 9/14: 실제 data 존재
- 9/15: KOSPI/KOSDAQ stock/index가 checked-empty 상태
- Provider: 현재 9/15 실제 data 제공

기대:
- 9/15는 처음에는 분석 준비 완료로 인정하지 않음
- 9/15를 다시 조회
- 네 데이터(KOSPI stock/index, KOSDAQ stock/index)를 실제 data로 저장
- `resolved_as_of_date = 2026-09-15`
- Scanner 본 실행에서 9/15 정합성 통과

### Case B — Provider에도 아직 9/15 없음
- 9/15 empty marker가 있어도 새 날짜 성공 안내 금지
- 기존 실제 data인 9/14 유지
- `date_changed = false`

### Case C — 이미 실제 9/15 data 존재
- 추가 다운로드 없이 기존 9/15 유지

### Case D — 최신화 실패 + 유효한 현재 날짜 존재
- B.2.2.2b와 동일하게 현재 날짜 유지
- 과거 날짜 자동 fallback 금지

## 7. 완료 조건
- `day_status=empty`만 있는 날짜를 분석 가능 날짜로 인정하지 않는다.
- empty marker가 최신 데이터 재확인을 막지 않는다.
- 준비 단계에서 `9/15 반영 완료`를 표시한 뒤 Scanner가 다시 9/15 불일치로 실패하는 경로가 제거된다.
- 기존 날짜 후퇴 방지 동작은 유지된다.

## 8. 패키징
현재 작업 명세 `WORKSPEC_v0.21.4-B.2.2.2c.md`만 포함한다. 이전 WORKSPEC은 포함하지 않는다.
