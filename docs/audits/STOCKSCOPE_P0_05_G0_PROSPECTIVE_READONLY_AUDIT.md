# StockScope P0-05/G0 — 기존 Prospective 운영 데이터 읽기 전용 인수검증

기준일: 2026-10-27 KST · 관련 Issue #171 / Draft PR #170

## 배경과 범위

기병합 #130의 S17 `tools/data/prospective_daily.py`는 사용자 **명시 설치 전에는**
자동 실행/일정 등록이 없다. S17은 Market Store의 새 확정 EOD를 사전 조건으로
Scanner job과 frozen Prospective capture를 기록하고, S16
`app.jev.q7_observation_s16.measure`로 **저장된 미래 바에 대한 기술통계**를
조회한다. S16은 증권 실거래 수익률, 독립 보유기간 성과, Q7 승인 증명이 아니다.

이번 G0는 **새 Capture 생성·장전 실행·S16 관측 재계산이 아니라**
운영 `simulation.db`와 `market_history.db`의 현재 저장 상태를 안전하게 측정하는 단계다.

## 구현

`tools/data/p0_05_prospective_readonly_audit.py` (stdlib-only):

- 실제 원본 2개 SQLite를 `mode=ro`/`PRAGMA query_only=ON`으로 조회. 기존
  DB가 없거나 Prospective migration/시장 스키마가 누락된 경우 스스로 생성하지 않고
  명확한 `HOLD_*`로 종료한다. WAL의 committed 기록을 읽고 해당 DB 파일에 쓰지 않는다.
- 실제 `prospective_capture_run` Capture 상태를 COMPLETE/PENDING/PARTIAL/
  DUPLICATE/FAILED/CANCELLED/INTERRUPTED/UNRECOGNIZED 별로 집계한다.
  중복 Scope·날짜, 동일 신호 key(신호일·시장·종목·전략),
  Canonical Duplicate 참조 이상 및 완료 Capture에 샘플이 없는 상태를 분리한다.
  합당하게 생성된 DUPLICATE 자체를 무조건 데이터 손상으로 처리하지 않는다.
- 수집 출처(Scanner version/baseline, fingerprint, horizon policy, source job/key,
  실제 데이터 기준일, 완료 시각)는 **값 자체를 출력하지 않고 누락 건수**만 표시한다.
  Strategy selection fallback 정책의 진위나 독립 시각 공증을 증명하지 않는다.
- COMPLETE Capture의 `ENTRY_CANDIDATE`만 5·10·20 거래일 구간 별
  **저장된 시장 거래일 증거가 몇 세션 존재하는지** 집계한다.
  `day_status(kind=stock,status=data)`와 같은 날짜의 `main_index_daily`
  교집합에서 신호일 이후~cutoff 이전 시장 세션을 계산한다.
  **각 종목의 실제 OHLC 완전성·공식 KRX 휴장일·손익/수익률 관측 완료를
  검증하지 않는다**. 대상 종목/시장/신호일이 없으면 `market_evidence_unknown`,
  표본이 아직 n거래일 미만이면 `awaiting_market_sessions`을 분리한다.
  같은 신호에 여러 Capture가 있어도 독립 표본으로 승격하지 않는다.
- 이미 저장된 Evaluation run/unit 및 5·10·20d 값 존재 건수는 **기존 저장 행**
  관점으로만 표기한다. 서로 다른 평가 run 중복, 정책 적합성, 재현/성과/거래 가능성
  미검증이므로 관측 완료 숫자 또는 성능 통계로 해석하지 않는다.
- 상한 260 Capture / 6000 샘플 초과 시 `HOLD_EXCEEDS_AUDIT_LIMIT`로
  모든 후속 집계를 중단한다. stdout에 종목·계좌·capture/job ID·가격·수익률·
  원본 JSON·토큰·파일 경로·에러 메시지를 포함하지 않는다.
- 외부 인터넷/로컬 서비스/유료 API 요청, SQLite schema 변경, scheduler 등록,
  수집기 실행/신규 capture 생성/보유 계획 적용 **모두 없음**.

**결과 해석**: `READ_ONLY_PROSPECTIVE_INVENTORY_OBSERVED`는 저장된 행의
증거가 조회되었다는 뜻만 포함한다. 0 Capture는 `HOLD_NO_CAPTURES`,
스키마 누락은 `HOLD_PROSPECTIVE_SCHEMA_NOT_READY`,
일관성 이상은 `HOLD_INCONSISTENT_CAPTURE_EVIDENCE`로 별도 보류한다.
언제나 `q7_approval_eligible=false`, `production_activation_allowed=false`,
`official_latest_eod_verified=false`.

## 사용자 Windows 명령 — 원본 DB 읽기만 실행

기존 사용자가 보존 중인 독립 TEMP worktree와 원래 가상환경을 재사용한다.
`$work`에 설치된 추가 라이브러리는 필요 없다. 스크립트는 Python 표준
라이브러리만 사용하며 `tzdata` 설치를 요구하지 않는다.

```powershell
cd C:\Projects\StockScope
$repo = (git rev-parse --show-toplevel).Trim()
$work = Join-Path $env:TEMP "StockScope_P0_02_90745c8d5d49"
$python = Join-Path $repo ".venv\Scripts\python.exe"
$simulation = Join-Path $repo "backend\runtime\simulation\simulation.db"
$market = Join-Path $repo "backend\runtime\market_history\market_history.db"

git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha
if ($LASTEXITCODE -ne 0) { throw "Checkout failed" }

& $python (Join-Path $work "tools\data\p0_05_prospective_readonly_audit.py") `
  --simulation-db $simulation `
  --market-db $market
```

`--as-of YYYY-MM-DD`는 과거 날짜를 조회해야 할 때만 사용한다.
기본 cutoff는 **오늘 이전 KST 달력일**이다. 사용자가 실행한 실제 결과가
없으면 운영 자료의 최신 상태를 PASS로 작성하지 않는다.

## 증거 및 다음 게이트

합성 SQLite/실제 VN-P2-S2 Prospective schema로 unit/CLI/개인정보 비출력/
없음·미성숙·중복·WAL 친화적 read-only 검증을 통과해야 한다. Backend Python
3.11/3.14 전체 회귀와 Windows Fresh Clone 직접 pytest가 동시 HEAD에서 PASS여야 한다.

- G0: 운영 DB의 실제 Capture·세션 증거 사용 가능성 확정 (**읽기 전용**).
- G1: 명시 승인 하 실제 새 확정 공식 EOD·수집 권리·요청량을 확인한 뒤
  실제 S17 Scanner/Prospective 수집. 이 문서로 승인받은 것이 아니다.
- G2: S16의 진짜 저장 바·Capture 무결성/시각·5/10/20 관측과
  사전등록 Q7 기준의 독립 성숙 분모 확인. G0의 시장 세션 경과만으로
  G2 성과 인수를 대체하지 않는다.

**P0-04 운영 판단은 여전히 STALE(계획 변경)이며 Recovery OPEN이다.
이 도구는 보유 계획·원장·Recovery와 무관하고 이를 수정하지 않는다.**
