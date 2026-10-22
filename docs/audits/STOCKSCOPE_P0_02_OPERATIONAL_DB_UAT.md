# StockScope P0-02 — 사용자 운영 Market Store 읽기 전용 UAT

## 목적과 범위

기존 `Scanner → data-plan → freshness → job` 경로가 사용하는 **운영 DB**
`backend/runtime/market_history/market_history.db`를 직접 점검한다.
연구용 `S31` SQLite DB, 합성 자료 및 CI 임시 DB를 운영 성공 근거로 사용하지 않는다.

이 도구는 표준 라이브러리만 사용하며 **KST(UTC+09:00)는 고정 오프셋으로 계산한다.**
시스템 timezone DB나 Python `tzdata` 설치가 없는 Windows Python 3.14에서도 실행할 수 있다.
원본 DB를 `mode=ro` 및
`query_only=ON`으로 연다. KRX/TypeSafe 요청, API 사용료, DB 변경,
원장/보유 데이터 접근, 스케줄러 설치, Runner 자동 시작이 없다.
SQLite WAL의 커밋된 최신 상태를 읽기 위해 `immutable=1`을 쓰지 않는다.

## 실사용 검증 (원본 작업 폴더·브랜치 보존)

아래 명령은 **실제 StockScope 프로젝트 폴더**에서 실행한다.
기존 브랜치와 수정 파일을 바꾸지 않고 검증 도구만 별도 worktree로 읽는다.
작업 전 `git status --short`에 로컬 변경이 있어도 `git reset`/`stash`하지 않는다.

```powershell
$repo = (git rev-parse --show-toplevel).Trim()
$db = Join-Path $repo "backend\runtime\market_history\market_history.db"
git status --short
git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
$ref = "origin/codex/p0-01-mvp-c1-c2-integration-20261022"
$sha = (git rev-parse $ref).Trim()
Write-Host "P0-02 검증 대상 SHA: $sha"
# GitHub의 exact SHA에 있는 검증 도구를 별도 폴더에 배치; 운영 DB는 절대 수정하지 않는다.
$work = Join-Path ([System.IO.Path]::GetTempPath()) "StockScope_P0_02_Readonly_$($sha.Substring(0,12))"
git worktree add --detach $work $sha
$scriptPath = Join-Path $work "tools\data\p0_02_operational_store_audit.py"
py -3 $scriptPath --market-db $db --as-of 2026-10-21 --market-scope ALL --lookback-calendar-days 220
```

Windows에서 `py -3`가 없으면 기존 프로젝트의
`.\.venv\Scripts\python.exe` 또는 `python`을 명시하여 실행한다.
출력은 stdout JSON뿐이므로 결과를 기록하려면 `| Out-File`로 **원본 DB
바깥**에 따로 저장한다. 보고서에 가격·종목코드·계좌정보·API 키는 없다.
`2026-10-21` 기준일은 실제 검증 날짜로 바꿔 재실행할 수 있지만,
장중 당일 시세는 확정 EOD가 아니다.

## 판정 기준

- `last_common_marked_stock_index_date`: 선택 시장의 **종목·지수
  status=data 표시와 실제 저장 행이 같은 날짜**가 존재하는 최신일.
  실시간 시세/공표 시간/내용 정확성 증명이 아니다.
- `markets.*.latest_marked_stock_row_date`와
  `latest_marked_index_row_date`: 저장된 두 원천의 시차.
- `weekdays_without_both_marked_rows`: 확인 창 내 평일의 빈 슬롯 개수.
  실제 휴장도 포함될 수 있으므로 **결측 거래일 개수로 단정하지 않는다**.
- `weekday_gap_examples`: 원본 가격 없이 날짜·자료 종류·불일치 원인 표시.
- `unverified_empty_markers`: 빈 KRX 응답을 공식 휴장으로 승격 금지.
- `full_strategy_lookback_proven=false`,
  `provider_data_confirmed=false`: DB 행 존재만으로 전체 전략 입력 검증을
  통과한 것처럼 주장하지 않음.

## 다음 게이트 (아직 완료 아님)

1. 사용 PC의 동일 SHA, 원본 Market DB 경로·수정 시각과 감사 JSON 확보.
2. 인증/권리 확인된 기존 KRX 경로에서 실제 공표일/휴장/지수와 일치 여부 점검.
3. 신규 `/scanner/data-plan` → 명시적 자료 준비 → `/scanner/jobs`의
   실제 결과가 동일 운영 DB/기준일을 쓰는지 원본 손실 없이 비교.
4. 동일 release의 실제 Scanner capture/job ID와 결과까지 검증해야 P0-02를 PASS 판정.
5. 검증 실패는 HOLD로 남기고 필요한 최소 결함만 수정한다.
