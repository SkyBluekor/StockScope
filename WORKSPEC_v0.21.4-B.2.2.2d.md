# v0.21.4-B.2.2.2d — KRX Input Data Integrity Audit & Refresh Correction

## 목적
KRX 확정 일봉이 `KRX 직접 응답 → raw cache → Market Store(SQLite) → Scanner 입력` 전 구간에서 같은 날짜와 같은 OHLCV로 유지되는지 검증하고, stale cache·부분 저장·stale row·같은 날짜의 오래된 Scanner cache를 교정한다.

## 범위
- KRX stock/index 직접 강제 조회 경로 추가 (`force_refresh`)
- 강제 조회 시 메모리/디스크 raw cache를 최신 응답으로 교체
- 빈 강제 응답이면 과거 non-empty 디스크 cache를 남기지 않음
- gzip raw cache 저장을 임시 파일 + atomic replace 방식으로 변경
- Market Store의 하루/시장 stock snapshot을 transaction 단위 전체 교체
- 대표지수 snapshot도 동일 날짜 기준 교체
- 저장 직후 row count / ticker set / OHLCV / index read-back 검증
- 데이터 무결성 검증 완료 상태를 Market Store에 기록하여 같은 날짜를 매번 전체 재다운로드하지 않음
- B.2.2.2d 적용 후 기존 최신 날짜는 최초 1회 KRX 직접 검증 후 재사용
- Scanner 결과에 stock/index dataset fingerprint 추가
- 같은 날짜라도 Market Store 내용이 바뀌면 기존 Scanner cache 재사용 금지
- 개발 진단 API `POST /api/backtest/scanner/data-integrity-audit` 추가
- 진단 API는 KRX 직접 응답, 기존 raw cache, 기존 Market Store, 교정 후 Market Store를 비교하고 최대 20건 mismatch sample 제공
- 기본 trace 종목은 코스맥스 `192820`

## 데이터 무결성 완료 조건
한 시장/날짜가 분석 가능하다고 인정되려면:
1. KRX 응답 내부 기준일이 요청일과 일치한다.
2. 주식 snapshot이 비어 있지 않는다.
3. 대표지수가 존재하고 기준일이 일치한다.
4. Market Store snapshot 교체 후 row count가 KRX와 일치한다.
5. ticker set이 일치한다.
6. Open/High/Low/Close/Volume이 일치한다.
7. 대표지수 read-back 값이 KRX와 일치한다.

## 캐시 정책
- 일반 과거 데이터 재사용 정책은 유지한다.
- 최신 확정 분석일은 `DATA_INTEGRITY_VERSION = v0.21.4-B.2.2.2d` 기준으로 최초 1회 직접 검증한다.
- 검증 fingerprint가 현재 Store와 같으면 다음 실행부터 KRX 네트워크 재검증을 생략한다.
- Store가 변경되면 verification hash 불일치로 다시 검증한다.
- Scanner 결과 cache도 현재 dataset fingerprint와 일치할 때만 재사용한다.

## 수정 금지 범위
- 전략 조건
- Risk / Entry / Stop / Target 계산
- 후보 Ranking 원칙
- 과거 성과 검증 로직
- UI 스타일/레이아웃

## 검증 시나리오
- stale raw cache → KRX 직접 응답으로 교정
- stale Market Store → snapshot 교체 및 stale ticker 제거
- 부분/중복 저장 실패 시 기존 snapshot transaction rollback
- 동일 날짜 최초 실행은 KRX 직접 검증, 2회차는 verified snapshot 재사용
- 동일 snapshot은 동일 fingerprint
- 같은 날짜 OHLCV 변경 시 fingerprint 변경 및 Scanner cache 무효화
- B.2.2.2c 날짜 후퇴/empty-marker 회귀 시나리오 유지

## 완료 기준
StockScope가 `2026.09.15 확정 일봉`이라고 표시할 때, 해당 날짜의 Scanner 입력 OHLCV가 KRX 직접 응답과 동일함을 추적 가능해야 하며, 동일 dataset fingerprint에서는 Scanner cache가 같은 입력만 재사용해야 한다.
