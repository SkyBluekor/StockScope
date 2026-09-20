# StockScope v0.21.4-B.2.4 — Scanner Data Preparation Progress UX

## Goal
Scanner 실행 버튼을 누른 뒤 최신 EOD 검증과 후보 분석이 서로 끊긴 작업처럼 보이지 않게 한다. 실제 backend stage/count만 사용하고 시간 비율을 추정한 가짜 퍼센트는 표시하지 않는다.

## Production invariants
- Scanner decision version은 `0.21.3.5` 유지한다.
- Strategy / Ranking / Risk / Entry / Stop / Target / Exit 계산을 변경하지 않는다.
- Historical Sector RS temporal gate를 변경하지 않는다.
- Scanner result/session decision cache를 불필요하게 무효화하지 않는다.

## Canonical preparation stages
- local Market Store 확인
- latest confirmed EOD probe
- KOSPI stock
- KOSPI index
- KOSDAQ stock
- KOSDAQ index
- Market Store final verification

단일 시장 검색에서는 해당 시장에 필요한 5개 stage만 렌더링한다.

## Analysis stages
- recent market history preparation
- universe quick filter
- candidate strategy / Risk analysis
- final priority/ranking

## Progress truth policy
- denominator가 실제 존재할 때만 `done / total`을 표시한다.
- 전체 시간 퍼센트 progress bar는 제거한다.
- `VERIFIED_REUSE`는 `저장 데이터 재사용`으로 표시한다.
- network/API 내부 수치는 기본 화면에서 숨기고 `진행 상세`에 둔다.
- provider await가 2초 이상이면 heartbeat callback을 다시 보내 UI가 멈춘 것으로 오해하지 않게 한다.

## Unified job flow
Frontend가 `/scanner/freshness` 동기 요청을 먼저 기다린 뒤 Scanner job을 시작하던 흐름을 제거한다.
Scanner job이 freshness preparation을 먼저 수행하고 같은 cancellable job stream에서 Scanner analysis까지 이어간다.

Fallback 날짜를 사용자가 명시적으로 선택한 경우에는 `as_of_date`를 pin하여 freshness probe를 다시 하지 않는다.

## Failure
freshness가 실패하면 실패 stage와 기존 `ScannerFreshnessResponse`를 job progress details에 보존하여 기존 재시도/과거 확정일 fallback UI를 유지한다.

## UX
Preparation 중에는 세부 preparation stage를 보여준다. Candidate analysis가 시작되면 preparation은 `최신 확정 시세 준비 완료` 한 줄로 접고 분석 4단계를 표시한다.

## Acceptance
- new day: preparation sub-stage가 실제 순서대로 갱신
- same day: VERIFIED_REUSE가 network download처럼 보이지 않음
- slow provider: heartbeat 갱신
- failure: 실패 stage 유지 + retry/fallback 유지
- transition: preparation -> analysis가 같은 progress card에서 이어짐
- no fake overall percent
- Quick18/Top5/Strategy/Ranking/Risk/price plan 결과 변경 없음
