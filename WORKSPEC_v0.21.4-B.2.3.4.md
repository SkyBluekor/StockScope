# StockScope v0.21.4-B.2.3.4 — Cross-PC Scanner Reproducibility Audit

## 목적
같은 코드/같은 분석 기준일을 사용했을 때 집 PC와 학교 PC의 Scanner 입력·후보·정렬 결과가 동일한지 증명하고, 다르면 최초 분기 지점을 찾기 위한 비교 JSON을 자동 생성한다.

## 핵심 원칙
- Strategy / Risk / Entry / Stop / Target1 / Target2 / Historical Evidence / Ranking 계산식은 변경하지 않는다.
- 진단 기능은 추가 KRX/OpenDART 요청을 만들지 않는다.
- 비교 파일 저장 실패가 Scanner 결과를 실패시키면 안 된다.
- Backend cache 재사용 결과는 비교 파일을 새로 만들지 않는다. 실제 비교는 UI의 `다시 분석`(force refresh)으로 새 계산을 실행한다.

## 산출물
새 계산 완료 시 프로젝트 루트에 생성:

`scanner-repro/scanner-repro_{machine}_{generated_at}_analysis-{analysis_date}.json`

예:
- `scanner-repro_home_20260918-080712_analysis-20260917.json`
- `scanner-repro_school_20260918-091843_analysis-20260917.json`

`generated_at`은 KST 실제 실행 시각, `analysis_date`는 Scanner가 실제 사용한 확정 EOD 기준일이다.

## PC 식별
1. `STOCKSCOPE_REPRO_MACHINE` 환경변수
2. `backend/runtime/reproducibility/machine_label.txt`
3. 둘 다 없으면 raw hostname을 저장하지 않고 SHA-256 기반 `pc-xxxxxxxx` 라벨 사용

항상 raw hostname 대신 `machine_fingerprint`(12자리 hash)를 함께 기록하여 라벨 설정 실수 시에도 두 PC가 다른지 확인 가능하다.

간편 설정:
- 집: `python backend/tools/set_repro_machine.py home`
- 학교: `python backend/tools/set_repro_machine.py school`

## JSON 기록 항목
### 실행/코드
- audit version
- machine label / machine fingerprint
- generated_at
- analysis_date
- scanner version
- Git commit / branch / tracked-file dirty 여부
- fresh analysis / backend cache 여부

### Market Store
Scanner 현재조건 계산용 220일 범위에 대해 시장별:
- stock/index 실제 row count
- DATA / EMPTY / MISSING 날짜와 개수
- stock SHA-256
- index SHA-256
- day-status SHA-256
- combined SHA-256

Hash는 날짜/종목코드 고정 정렬 + canonical JSON으로 생성하여 SQLite 반환/삽입 순서 차이의 영향을 제거한다.

### 후보별 입력
최종 actionable 후보 전체(Top 5만 아님)에 대해:
- 종목코드/종목명/시장/기준일/현재가
- 후보 상태/전략/action
- 현재 조건
- Risk
- 3년 Historical Evidence 핵심값
- 전략 적합도/internal rank(진단 파일에만 기록)
- entry gap
- 최종 priority sort 구성값과 sort key
- Entry/Invalidation/Stop/Target1/Target2/R:R
- 조건 세부값, 거래대금/시총/history points, volume/trend rule

또한 후보별 3년 Historical Evidence 입력 구간(+warmup)의 실제 stock-series SHA-256을 별도로 기록한다.

## 캐시 정책
- `다시 분석`처럼 새 계산한 결과만 완전한 비교 JSON을 생성한다.
- Backend Scanner cache hit에서는 무거운 전체 history hash를 다시 계산하지 않고 `reproducibility_audit.skipped=backend_cache`를 반환한다.

## 비교 순서
1. analysis_date
2. Git commit / tracked dirty
3. 220일 Market Store fingerprint와 DATA/EMPTY/MISSING
4. 후보별 장기 history fingerprint
5. 후보 집합
6. 조건/전략 결과
7. Risk / Entry gap / Historical Evidence
8. priority sort key
9. 최종 rank

최초로 달라지는 단계가 원인 후보가 된다.

## 수정 파일
- `backend/app/backtest/reproducibility_audit.py` 신규
- `backend/app/backtest/market_store.py`
- `backend/app/backtest/scanner.py`
- `backend/tools/set_repro_machine.py` 신규
- `backend/tests/test_scanner_reproducibility_v0214b234.py` 신규

## 완료 기준
- 동일 데이터의 삽입 순서가 달라도 fingerprint 동일
- 실제 값 하나가 바뀌면 fingerprint 변경
- DATA/EMPTY/MISSING 구분 가능
- home/school + 실행시각 + 분석일 파일명 생성
- 전체 후보에 최종 sort key 기록
- 추가 네트워크 요청 없음
- audit 저장 실패가 Scanner 계산에 영향 없음
- 기존 Production 판단식 무변경
