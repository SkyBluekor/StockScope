# StockScope v0.19.1 — 눌림목 백테스트 성능 최적화

## 목표

v0.19에서 1년 백테스트 최초 실행이 수 분 이상 걸릴 수 있던 병목을 줄이고, 사용자가 작업 상태를 확인하고 취소할 수 있게 한다.

## 핵심 변경

1. KRX 요청마다 새 HTTP 클라이언트를 만들지 않고 백테스트 동안 하나의 연결 풀을 재사용한다.
2. 날짜별 KRX 원본 gzip 캐시에 더해 `backend/runtime/backtest/history`에 종목별/시장지수별 compact Historical Store를 유지한다.
3. 같은 종목과 기간을 다시 실행할 때 Historical Store에 이미 확인된 날짜는 KRX 조회 대상에서 제외한다.
4. 고정 220 calendar day 워밍업을 없애고 100일에서 시작해 시작일 이전 60거래일이 부족할 때만 45일 단위로 뒤로 확장한다.
5. 과거의 확실한 빈 응답은 `.empty` marker로 저장한다. 최근 3일은 게시 지연 가능성이 있어 영구 empty 처리하지 않는다.
6. KRX 호출은 기본 8 동시 요청에서 시작해 정상 batch가 이어지면 최대 12까지 올리고, 오류 비율이 높으면 자동으로 낮춘다.
7. 429/5xx/연결 오류는 제한된 exponential backoff로 재시도한다.
8. 백테스트 API를 Job 방식으로 추가하여 진행률 조회와 취소를 지원한다. 기존 동기 API는 호환성용으로 유지한다.
9. 전략 계산은 thread로 넘겨 API event loop를 막지 않으며 거래일별 진행률을 갱신한다.
10. 사용자 화면에서 `Pullback`은 `눌림목 전략`, `Entry Timing`은 `진입 타이밍`, `Strategy Score`는 `전략 적합도`로 표시한다.

## 사용자 설명

눌림목 전략은 상승 추세를 이어가던 주가가 잠시 조정을 받아 이동평균선이나 주요 지지구간에 접근한 뒤, 다시 반등하는 시점을 진입 후보로 보는 전략이다.

`상승 추세 → 일시 조정 → 지지구간 접근 → 반등 확인 → 진입 후보`

## 신규 API

- `POST /api/backtest/pullback/jobs` — 백테스트 Job 생성
- `GET /api/backtest/jobs/{job_id}` — 진행률/결과 조회
- `DELETE /api/backtest/jobs/{job_id}` — 취소

기존 `POST /api/backtest/pullback`은 호환성 때문에 유지한다.

## 성능 진단

결과 응답의 `performance`에 다음을 포함한다.

- `data_prepare_seconds`
- `strategy_calculation_seconds`
- `total_seconds`
- `history_store_hits`
- `raw_cache_hits`
- `network_requests`
- `retries`
- `warmup_rows`

같은 종목/기간의 두 번째 실행에서 `network_requests`가 크게 줄어드는 것이 정상이다.

## 이번 버전에서 변경하지 않은 것

- 눌림목 전략의 점수 계산식
- 진입 타이밍 7개 조건의 의미
- 다음 거래일 시가 진입
- 동일 일봉 손절/목표가 충돌 시 손절 우선
- Risk Engine의 손절/무효화 기준
- 1차 목표가 전량 가상청산 MVP 정책
- OpenDART/재무를 백테스트 진입판정에서 제외하는 정책

## 다음 정확성 점검

2026-06-26 신호에서 331,000원 진입 후 274,722원 손절로 -17.15%가 나온 거래는 v0.19.1 성능 작업 이후 별도로 Risk Engine/갭 체결/무효화 가격 연결을 검증한다.
