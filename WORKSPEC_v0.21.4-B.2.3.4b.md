# StockScope v0.21.4-B.2.3.4b — Deterministic Scanner & Data-Prepare Progress

## 1. 목적

같은 분석 기준일과 같은 최신 KRX 입력을 사용하면 실행 PC의 로컬 장기 데이터 보유량과 무관하게 현재 후보, 현재 전략, Risk, 기본 우선순위가 동일하게 나오도록 Scanner를 결정론적으로 고친다.

동시에 `필요 데이터 확인` 단계에서 실제 KRX 검증이 진행 중인데 UI가 장시간 0%로 보이는 문제를 개선하고, 같은 날짜의 무결성 검증이 이미 끝난 경우 강제 KRX 재검증을 반복하지 않는지 보장한다.

## 2. 확인된 원인

현재 Scanner는 상위 후보 18개를 처리할 때 로컬 장기 데이터 행 수에 따라 서로 다른 계산 경로를 탄다.

- 장기 stock/index rows >= 220: `_deep_candidate()`
- 220 미만: `_fast_candidate()`

`_deep_candidate()`는 `MultiStrategyBacktestEngine.run()`의 historical selector 결과로 현재 strategy와 selector score를 다시 선택한다. 반면 `_fast_candidate()`는 최근 데이터로 이미 선택한 `quick_strategy`/`quick_score`를 유지한다.

따라서 동일한 2026-09-17 최신 Market Store 입력이어도:

- HOME: 후보별 장기 데이터 약 151행 -> fast path
- SCHOOL: 후보별 장기 데이터 약 801행 -> deep path

으로 갈라져 현재 전략, strategy_fit, 최종 순위가 달라진다.

이는 CPU/OS 차이가 아니라 선택적 로컬 history 보유량이 production decision path를 바꾸는 구조적 재현성 결함이다.

## 3. 설계 원칙

### 3.1 현재 판단은 오직 canonical current path로 계산

현재 후보 판단에 사용하는 값은 모든 PC에서 같은 경로로 계산한다.

- current strategy
- conditions
- candidate state
- Risk
- Entry/Stop/Invalidation/Target
- current strategy fit
- current priority inputs

장기 데이터의 존재 여부가 위 값을 바꾸면 안 된다.

### 3.2 deep/fast 분기 제거

production Scanner에서 `HISTORICAL_VALIDATION_MIN_ROWS`에 따른 `_deep_candidate()` / `_fast_candidate()` 선택 분기를 제거한다.

상위 후보 18개는 항상 최근 Scanner 입력으로 이미 계산된 current result를 canonical candidate로 변환한다.

구현은 기존 `_fast_candidate()`를 의미가 명확한 함수명으로 정리하거나 동등한 current-only builder로 통합한다.

예:

```python
_current_candidate(item)
```

장기 데이터가 151행이든 801행이든 같은 item 입력이면 동일 candidate payload를 생성해야 한다.

### 3.3 historical evidence는 current decision과 분리

3년 과거 근거 계산은 canonical current candidate가 확정된 뒤 별도 attach 단계에서만 수행한다.

Historical Evidence는 다음을 절대 변경하지 않는다.

- selected current strategy
- current condition pass/fail
- Risk status
- Entry/Stop/Target
- candidate READY/WATCH 판정

### 3.4 최종 순위 재현성 정책

선택적 로컬 3년 데이터의 보유 여부가 PC마다 다르므로, local-only Historical Evidence를 production 최종 순위의 정렬 키로 사용하면 cross-PC 동일성을 보장할 수 없다.

따라서 B.2.3.4b에서는 최종 production rank를 다음 deterministic current keys로 제한한다.

1. current tier / readiness
2. missing current conditions
3. Risk quality
4. concrete entry gap
5. current strategy fit
6. ticker code tie-break

Historical Evidence는 후보 상세와 설명에는 유지하지만 rank를 재정렬하지 않는다.

향후 Historical Evidence를 다시 rank에 반영하려면 모든 실행 환경이 동일한 canonical historical dataset fingerprint를 보유하는 동기화 정책을 먼저 도입해야 한다.

## 4. 데이터 준비 단계 개선

### 4.1 신규 확정일 첫 검증

새로운 전일 EOD 날짜가 처음 등장한 날에는 KRX 확정 여부와 KOSPI/KOSDAQ stock/index 무결성 검증이 필요하므로 일정 시간이 걸릴 수 있다.

이 자체는 오류로 취급하지 않는다.

### 4.2 같은 날짜 재실행은 VERIFIED_REUSE

한 번 무결성 검증이 성공하고 다음 조건이 모두 맞으면 같은 날짜의 다음 분석에서는 강제 KRX 재호출을 하지 않는다.

- integrity record 존재
- integrity version 일치
- stock row count 일치
- stock hash 일치
- index hash 일치
- Market Store day status=data

이 경우 `VERIFIED_REUSE`로 즉시 통과한다.

### 4.3 0% 정지처럼 보이는 UI 제거

`prepare_latest_confirmed_data()` 내부에 progress callback을 전달할 수 있게 하고 다음 sub-stage를 보고한다.

- local store 확인
- 최신 날짜 probe
- KOSPI stock 검증
- KOSPI index 검증
- KOSDAQ stock 검증
- KOSDAQ index 검증
- Market Store read-back / integrity 기록

Frontend의 `필요 데이터 확인` 단계는 이 값을 받아 0% 고정이 아니라 실제 진행 상태와 현재 작업을 표시한다.

장시간 네트워크 대기 중에도 heartbeat/progress timestamp가 갱신되어 `마지막 진행 103초 전` 같은 오해를 줄인다.

## 5. 재현성 Audit 확장

기존 B.2.3.4a JSON은 유지하고 다음 필드를 추가한다.

```json
{
  "decision_pipeline": "CURRENT_ONLY_V1",
  "ranking_policy": "CURRENT_DETERMINISTIC_V1",
  "historical_evidence_affects_rank": false,
  "current_history_window": {
    "start": "...",
    "end": "...",
    "fingerprint": "..."
  },
  "historical_coverage": {
    "candidate_rows_min": 151,
    "candidate_rows_max": 801
  }
}
```

목적은 향후 두 PC 파일만 비교해도 production decision path가 동일했는지 즉시 확인하는 것이다.

## 6. 변경 대상 예상

### Backend

- `backend/app/backtest/scanner.py`
  - deep/fast production 분기 제거
  - canonical current candidate path 통합
  - prepare_latest_confirmed_data progress callback 지원
  - VERIFIED_REUSE 진단 강화
  - Scanner VERSION/cache token 갱신

- `backend/app/backtest/candidate_priority.py`
  - local-only Historical Evidence를 production sort key에서 제거
  - current deterministic sort key 명시
  - ticker code stable tie-break 유지

- `backend/app/backtest/reproducibility_audit.py`
  - decision pipeline / ranking policy metadata 추가
  - current window fingerprint / history coverage 진단 추가

- 필요 시 Scanner API job progress relay 파일
  - prepare 단계의 세부 progress 이벤트 전달

### Frontend

- Scanner progress UI
  - `필요 데이터 확인` sub-progress/current item 표시
  - heartbeat 반영

UI 레이아웃이나 테마는 변경하지 않는다.

## 7. 삭제/비활성화 대상

production path에서는 아래 로직을 더 이상 사용하지 않는다.

```python
if enough_history:
    _deep_candidate(...)
else:
    _fast_candidate(...)
```

`_deep_candidate()`는 다른 기능에서 필요하면 보존할 수 있으나 Scanner production ranking/strategy selection에는 연결하지 않는다.

`HISTORICAL_VALIDATION_MIN_ROWS`도 Scanner 현재 판단 분기 기준으로 사용하지 않는다.

## 8. 캐시 정책

Scanner VERSION을 올려 이전 decision cache를 자동 무효화한다.

예:

```python
VERSION = "0.21.3.3"
```

이전 버전에서 deep/fast path로 생성된 결과를 새 deterministic Scanner가 재사용하면 안 된다.

브라우저 session restore도 새 Scanner policy/version과 맞지 않는 결과는 복원하지 않도록 검증한다.

## 9. 테스트

### 재현성 핵심 테스트

동일한 최근 220일 입력을 만들고 장기 보유량만 다르게 구성한다.

Case A:
- recent current data 동일
- historical rows = 151

Case B:
- recent current data 동일
- historical rows = 801

반드시 동일해야 하는 값:

- candidate 18 codes
- selected strategy
- conditions passed/total
- candidate_state
- risk
- entry/stop/target
- current strategy fit
- final current sort key
- final rank

Historical Evidence 표시만 서로 다를 수 있다.

### 동일 Market Store 입력 테스트

HOME/SCHOOL fixture의 recent combined fingerprint가 같으면 production candidate/rank JSON이 byte-equivalent한 핵심 decision fields를 가져야 한다.

### 순서 안정성 테스트

SQLite row insertion/return order를 바꿔도 최종 rank가 동일해야 한다.

### 데이터 준비 테스트

1. 새 분석일 첫 실행
   - 필요한 KRX verify 수행
   - progress 이벤트가 0%에 정지하지 않음
   - integrity verified 저장

2. 동일 분석일 두 번째 실행
   - `VERIFIED_REUSE`
   - forced network requests = 0
   - 같은 Market Store hash 유지

3. integrity hash 불일치
   - forced verify 수행
   - read-back 검증 후 새 integrity record 생성

4. provider 지연/실패
   - heartbeat/progress 갱신
   - 유효한 기존 날짜를 몰래 과거로 후퇴시키지 않음

### 회귀 테스트

- Target1/Target2 formula unchanged
- Entry/Stop/Invalidation unchanged
- Risk calculation unchanged
- KRX Market Store data unchanged
- Exit production policy unchanged
- Historical Evidence 계산식 자체 unchanged

## 10. 완료 기준

B.2.3.4b 완료는 아래를 모두 만족해야 한다.

- 동일 analysis_date + 동일 recent input fingerprint -> PC와 장기 history 보유량에 관계없이 같은 18개 후보/전략/현재 우선순위
- 151행 vs 801행에서도 current decision fields 동일
- local-only Historical Evidence가 현재 strategy 또는 production rank를 변경하지 않음
- 새 날짜 첫 검증 이후 같은 날짜 재실행은 VERIFIED_REUSE
- 데이터 준비 중 progress/heartbeat가 실제로 갱신됨
- 기존 Target/Risk/Exit 공식에는 영향 없음
- 재현성 JSON에 새 policy metadata 기록
- 기존 Scanner cache/session의 구 decision 결과가 새 버전에서 자동 무효화됨

## 11. 이번 버전에서 하지 않을 것

- 3년 Market Store 전체를 Git으로 동기화하지 않음
- 매 Scanner 실행마다 3년 KRX 데이터를 강제 다운로드하지 않음
- Historical Evidence 계산식을 재설계하지 않음
- 새로운 임의 가중치 점수를 만들지 않음
- UI 테마/레이아웃 변경하지 않음

## 12. 후속 검증

수정 후 HOME과 SCHOOL에서 같은 날짜로 재분석하여 새 audit JSON 2개를 생성한다.

기대 결과:

- recent/current fingerprint 동일
- selected strategy 동일
- current decision sort key 동일
- final rank 동일
- historical coverage는 PC별로 달라도 허용

이 조건이 만족되면 cross-PC Scanner 재현성 문제를 해결한 것으로 판정한다.
