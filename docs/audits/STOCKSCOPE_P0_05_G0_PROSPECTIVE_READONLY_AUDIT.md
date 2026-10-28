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

## P0-05/G0b — 기존 S16 read-only 관측 결과 재조회 (실제 종목·수익률 출력 없음)

사용자의 Windows G0 실제 운영 실행(2026-10-27): 전체 21 Capture(8 COMPLETE/13 DUPLICATE), COMPLETE 샘플 120, ENTRY_CANDIDATE 61(고유 신호키 60). 시장 세션만 계산하면 5d 기준 37, 10d 기준 23, 20d 기준 0이었으나, 이는 각 종목의 주가/EOD 완전성 또는 성과 관측 성공으로 인정하지 않는다. 저장 Prospective Evaluation Run/Unit는 모두 0. scanner_baseline과 horizon_policy_version 각 21개 미기재이며 출처 조작/과거 보충은 금지한다.

새 `tools/data/p0_05_s16_readonly_coverage.py`는 실제 운영 DB 원본을 먼저 위 G0로 검사하여 일관성을 확인하고, **기존** `app.jev.q7_observation_s16.measure`를 읽기 전용으로 호출한다. S16은 immutable COMPLETE Capture의 Snapshot 해시 검사, S7 integrity 분류, 기존 `ProspectiveEvaluator`의 `mode=ro` Market Store, 확정 EOD 요구, 신호일 이후 거래일 공백·cutoff 조건을 사용한다. S16은 새 Prospective Evaluation Run/Unit/Report를 저장하지 않고, 기존 0건도 그대로다.

**매우 중요한 구분**:
- `captured_entry_rows`: 원본 COMPLETE frozen Capture에서 나온 후보 수.
- `integrity_eligible_for_readonly_observation`: S7의 `LOCAL_VALIDATED`/ `LEGACY_LIMITED`인 후보 수. 무결성 `INVALID` 후보는 분모에서 제외하고 별도 집계한다. LEGACY_LIMITED는 현재 전략 버전/선정정책 정식 검증이 아니라 제한된 로컬 근거다.
- `on_demand_window_status_counts[5d|10d|20d].observed`: 기존 Market DB의 저장된 각 종목 EOD를 이용한 **신호일 종가 대비 로컬 기술 관측 수**. 이는 실매매·독립 표본·투자 전략 성과 검증이 아니다. 관측 수익률 수치 및 종목별 내용은 출력하지 않는다.
- `awaiting_future_trading_days`, `price_missing`, `unverified_calendar_or_market_gap`, `post_as_of_data_rejected`, `market_evidence_unavailable`로 누락·미성숙·공백·미래 정보 거부를 분리한다. 분모/사유 집계 불일치는 `HOLD_*`로 fail-closed.
- `source_missing_field_counts`는 G0에서 발견된 기재 누락의 **집계만** 재현하며 과거 Scanner baseline·Horizon numeric policy를 자동 보완하지 않는다.

**안전성/기한**: 표준 G0 스크립트와 같은 두 DB를 `mode=ro`로 열며, 외부 TCP를 허용하지 않는 wrapper로 S16을 감싼다. 입력 부족/실제 S16 오류/명시적 네트워크 시도/날짜 오류는 `HOLD_*`로 출력한다. 예외 원본 메시지나 종목/계좌/가격/종목코드/원본 JSON/관측 수익률 퍼센트는 stdout에 출력하지 않는다. on-demand 임시 계산만 하고 파일 저장/DB 쓰기/Scanner Job/스케줄 등록/외부 KRX/유료 API/거래는 수행하지 않는다.

### 사용자 Windows PowerShell 실행

위 G0가 성공했던 것과 동일한 `$repo`, `$work`, `$python`, `$simulation`, `$market` 및 최신 detached HEAD를 사용한다:

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

& $python (Join-Path $work "tools\data\p0_05_s16_readonly_coverage.py") `
  --simulation-db $simulation `
  --market-db $market
```

`READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED`면 구조 일관성/로컬 S16 기술 관측 상태를 확인한 것이다. `HOLD_*`가 나오면 구체적인 값·시세를 억지로 채우지 않고 상태와 사유만으로 후속 문제를 분석한다. Python 런타임 tzdata/ZoneInfo가 없는 Windows에서는 `HOLD_S16_RUNTIME_NOT_READY`가 나올 수 있다. 사용자 운영 DB는 도구 실행으로 변경되지 않으며 2026-10-27 최신 KRX EOD 보장도 없다.

CI: `backend/tests/test_p0_05_s16_readonly_coverage.py` (실제 합성 Prospective 스키마 + S16 관측 응답 shape/무결성 오류, 누락·분모/사유 검증, 개인정보 비출력, 불필요 네트워크 시도 차단). 기존 `test_q7_s16_readonly_maturity.py`는 실제 S16 자체의 관측/거래일 미래정보/무결성 동작 검증을 계속 담당한다.

**P0-05 G1 신규 Capture, G2 운영 성과 검증, Q7 승인, S17 Task 등록, 프로덕션 배포/PR merge는 이번 G0b 결과와 별개로 보류한다.**

## P0-05/G0c — INVALID 근거 상세화 및 미성숙/캘린더 공백 이중 분류

사용자 2026-10-27 Windows G0b 실측: ENTRY 61 중 `INVALID=24`,
`LEGACY_LIMITED=37`, `LOCAL_VALIDATED=0`; 5d S16 observed 13/37,
캘린더 공백 24/37; 10d/20d 각 캘린더 공백 37/37. S16의 기존 보수적
`UNVERIFIED_CALENDAR_OR_DATA_GAP` 판정이 `AWAITING_FUTURE_DAYS`
보다 먼저 적용돼 두 상태의 의미를 혼동하기 쉬웠다.

이번 G0c는 S16 실제 저장 데이터를 **수정하지 않고 출력되는 진단 집계만 확장**한다.

- `invalid_check_failure_counts`: S7 검사 부문 `rank/strategy/policy/engine/dates/risk/strict_s3` 중 실제 `FAIL`이 발생한 INVALID 후보 수. `invalid_reason_code_counts`: 알려진 S7 상태 코드별 발생 후보 수, 예기치 않은 상태 코드는 식별 정보 없이 `OTHER_S7_CODE`로 정규화. **한 후보에 여러 실패가 있으므로 부문별 수치 합산으로 INVALID 24건을 추정하면 안 된다.** `invalid_without_failed_checks`는 S7 검사 결과 자체에 FAIL이 없는 이상 사례의 건수다. 다른 단계의 과거 레거시 식별값을 소급 보정하거나 후보를 무효/유효로 다시 저장하지 않는다.
- 기존 S16 `unverified_calendar_or_market_gap`의 **부가 설명용 겹치는 하위 상태** 두 개:
  - `gap_with_insufficient_confirmed_sessions`: 날짜 공백이 남아 있으며 확정된 시장 세션도 해당 window보다 **적음**. 이것만으로 **진짜 미성숙**이 증명되는 것은 아니다. 확인되지 않은 날짜가 실제 거래일이었는지/휴장일이었는지 모른다.
  - `gap_with_sufficient_confirmed_sessions`: window에 필요한 확정 세션 건수는 충족하나 **구간 내부에 확인되지 않은 평일 날짜가 있음**. 실제 관측/완결 시세라고 인정하면 안 된다.
- 두 부가 상태는 해당 window의 `unverified_calendar_or_market_gap` 합과 정확히 일치해야 한다. `awaiting_future_trading_days`는 기존과 같이 공백 검사 자체는 통과했으나 해당 window의 확정 세션이 부족한 경우에만 집계한다.
- 기존 S16의 `OBSERVED`, `INVALID`, `LEGACY_LIMITED`, Q7 approval=false 및 로컬 provider 차단 **판정 자체는 변경하지 않는다**. 결과 비공개 입력(종목·수익률·source job/UUID·정책 전문)은 출력하지 않는다.
- `tools/data/p0_05_s16_readonly_coverage.py`는 반환 JSON `version=STOCKSCOPE_P0_05_G0C_S16_READONLY_COVERAGE_V2`를 사용하며 S16 원본과 G0의 후보/분모/하위 공백/무결성 건수가 맞지 않으면 `HOLD_*`로 중단한다.

### Windows G0c 실행

이전 G0b와 **동일한** 명령(`p0_05_s16_readonly_coverage.py`)을 최신 SHA에서 사용한다. 운영 DB 원본 2개는 read-only로 열고 새 평가 Run을 만들거나 캡처를 추가하지 않는다. 이번 G0c의 1차 CI 테스트는 `backend/tests/test_q7_s16_readonly_maturity.py -k test_g0c`(실제 S16 함수), `backend/tests/test_p0_05_s16_readonly_coverage.py`(개인정보 비출력/계약검사)로 실행한다. 실환경 분포는 **사용자 Windows 출력이 확인되기 전까지 미확정**이다.

**새 결과의 SAFE PASS는 캘린더 진위, 10/20일 성숙, 과거 capture 독립 시각/정책 버전, Q7 운영승인, 실거래 수익률을 증명하지 않는다.** 프로덕션 DB 쓰기·외부 수집·S17 예약 실행·Q7 승격·PR merge는 보류한다.

## P0-05/G0d — Windows `HOLD_S16_INVALID_DIAGNOSTICS_CONTRACT` 진단 및 정상화

2026-10-27 사용자 실제 Windows G0c 실행(HEAD `d184605ff6b8ed53d57a39f5e1905e078286b8ba`)에서 기존 G0/G0b와 동일 운영 DB를 사용했지만 **`HOLD_S16_INVALID_DIAGNOSTICS_CONTRACT`**가 보고됐다. 이는 G0c 추가 진단 집계의 계약 거부이며, 운영 DB 무결성 손상이나 새로운 주가 수집 실패를 의미하지 않는다. 해당 HOLD에선 개별 INVALID 사유/캘린더 하위 분포를 출력하지 않아 원본 수치는 **미확정**이다.

원인 후보 하나를 코드에서 확인했다: 기존 S16 `INVALID` 처리에서 한 후보의 여러 알 수 없는 S7 코드가 **모두 `OTHER_S7_CODE`로 정규화되는데, 정규화 전에 중복을 제거**했다. 따라서 서로 다른 미정의 코드가 여러 개인 한 후보가 동일 범주에서 복수 번 계상돼 `OTHER_S7_CODE > INVALID 전체 후보 수`를 만들 수 있고, wrapper의 올바른 유효성 검사를 거부시킨다. 사용자의 과거 원본 Snapshot 코드를 공개하지 않았으므로 **실제 HOLD의 원인이 이것이었다고 단정하지 않는다**.

G0d 수정:
- S16의 각 INVALID 후보에서 먼저 원인을 `EXPLAIN` 허용 코드 또는 `OTHER_S7_CODE`로 정규화한 뒤, 정규화된 키 집합을 **후보별 1번씩** 계수한다. 알고 있는 다른 근거 코드는 여전히 서로 겹쳐 계수하며, `INVALID` 후보 자체의 개수·기존 S16 관측 판정은 변경하지 않는다.
- Wrapper는 허용된 소수의 `diagnostic_failure_class`만 추가로 보고한다(예: `REASON_BUCKET_EXCEEDS_INVALID_CANDIDATES`, `CHECK_BUCKET_SHAPE_INVALID`). 개인별 종목·주가·전체 정책 코드/원문·원본 DB 경로·예외 메시지 비출력, `HOLD_*` 시 부분 분포를 반환하거나 성공 처리하지 않는다.
- 테스트에 한 후보가 2개 이상의 서로 다른 미정의 S7 코드를 가진 상황과, 변환 전에는 동일 범주 건수가 INVALID 수를 초과하던 상황을 재현한다. 원본 S16과 wrapper, Windows Fresh Clone 모두 검증한다.

이전 G0c와 **동일** `p0_05_s16_readonly_coverage.py` Windows 명령을 최신 HEAD로 다시 실행한다. `READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED`이면 무결성 사유와 5/10/20일 gap 하위 집계를 판독한다. 계속 `HOLD_S16_INVALID_DIAGNOSTICS_CONTRACT`라면 안전하게 공개한 `diagnostic_failure_class`만 확인한 후, 근거 없는 S16 정책 완화/운영 DB 수정을 금지한다.

운영 Capture/평가 Run/주문·관리 Plan/Recovery는 G0d 패치에서 변경하지 않고, 신규 수집/공식 최신 EOD/Q7 승인/실거래/PR merge는 HOLD로 유지한다.

## P0-05/G0e — S3·S7 원본 계약 대비 INVALID 구조적 원인 분리

2026-10-27 실제 Windows G0d에서 `ENTRY=61`, `INVALID=24`,
`LEGACY_LIMITED=37`, `LOCAL_VALIDATED=0`로 확인됐다. INVALID 24건은
모두 `rank/policy/strategy/engine/strict_s3` 진단에서 실패했으며,
`RANK_MISSING`, `POLICY_PROVENANCE_UNVERIFIED`,
`STRATEGY_IDENTITY_MISSING` 각 24, `ENGINE_EVIDENCE_INCOMPLETE` 9,
`OTHER_S7_CODE` 24였다. 이 집계만으로 원본이 잘못 생성됐는지,
레거시 계약에서 생략됐는지, 작성된 파일이 변경됐는지는 확정할 수 없다.

코드 근거:
- `app.strategy.semantic_identity_bridge.scanner_repro_candidate_key` 및
  `ProspectiveCatalog.finalize_capture`는 Scanner `priority.rank`와
  Repro Audit의 상위 rank 키를 비교한다. 검증 키가 없거나 충돌하면
  **Prospective sample.rank를 NULL로 보존**하고 리스트 순서로 숫자를
  지어내지 않는다.
- `app.jev.scanner_integrity_s7_1.assess_frozen_candidate`는 저장
  `sample.rank`와 frozen `snapshot.priority.rank`를 별도 확인한다.
- `app.jev.decision_reviewer_offline.build_scanner_review_input`(S3)은
  필수 frozen priority/risk/conditions/guide, rank 값 및 원본 전략/정책/
  엔진 근거를 엄격히 검사한다. **첫 위반 시 종료**하기 때문에
  S3의 반환 사유는 해당 후보의 **모든** 누락 항목 목록이 아니다.
- `app.prospective.catalog._candidate_snapshot`는 실제 실행
  selection-policy pin 또는 엔진 PASS 감사가 없으면 semantic
  strategy identity/version을 인증되지 않은 것으로 보존한다.
  이후 현재 정책/오늘 엔진 실행 결과를 옛 Snapshot에 끼워 넣지 않는다.

G0e 코드 변경:
- S16에서 `OTHER_S7_CODE`로 합쳐지는 알려진 S3 projection 실패
  (`BASELINE_EVIDENCE_INCOMPLETE`, `BASELINE_RANK_MISMATCH`,
  `SEMANTIC_SOURCE_V2_*`의 명시적 검증 코드 등)를 **문자열 상수
  허용목록**으로 분리한다. 알 수 없는 코드, 동적 오류 메시지,
  개인 식별 키는 계속 `OTHER_S7_CODE`로만 출력한다. 후보마다 같은
  이유는 1번씩 계수하며 이유 간 겹침은 유지한다.
- `invalid_rank_source_missing_counts`: `snapshot_priority_rank_missing`,
  `stored_sample_rank_missing`, `both_rank_sources_missing` 3종의
  **건수만** 반환한다. 실제 rank 값·코드·후보명은 출력하지 않는다.
  마지막 건수는 두 누락 집합의 교집합이며 별도의 제3 집합으로
  더하면 안 된다.
- 신규 S7/S16 회귀 테스트는 known S3 코드/unknown 비공개 fallback,
  원본 순위와 DB 순위 각각의 누락, 교집합, 잘못된 집계의 HOLD,
  PRIVACY/원본 DB read-only/승격 금지를 검증한다.
- 기존 S16 `INVALID/LEGACY_LIMITED/OBSERVED` 분류와 5/10/20일
  원본 캘린더 차단 기준은 **전혀 완화하지 않는다**. 원본 저장 기록
  backfill·migration·S17 자동 수집·전략 변경 없음.

### Windows G0e 읽기 전용 확인

지난 G0d와 **같은** `p0_05_s16_readonly_coverage.py` 명령을 Git
branch 최신 SHA로 실행한다. 출력 `version`은
`STOCKSCOPE_P0_05_G0E_S3_PROVENANCE_READONLY_V3`이고,
`invalid_reason_code_counts`, `invalid_rank_source_missing_counts`
분포를 확인한다. `READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED`는
출력된 근거의 **조회 상태만** 보장하며 재분류·실제 투자 성과·
정식 정책 승인으로 해석하지 않는다. 실환경 수치는 실제 사용자
Windows 실행 결과가 있기 전까지 추정하지 않는다.

다음 검증이 S3 코드의 구조적 선행 실패를 규명해도
재수집·공식 데이터 연결·원본 Capture 수정·PR 병합에 대한 허가를
의미하지 않는다.

## P0-05/G1 준비 — S17 실제 저장 증거 대조 (운영 실행 미승인)

2026-10-28 KST. 사용자 G0e Windows read-only 실측은
`READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED`: ENTRY 61, INVALID 24
(24개 모두 `sample.rank` 결측), LEGACY_LIMITED 37, 5d 기술 관측 13/37,
10d·20d 0/37이다. 별도 순위 회귀 테스트에서 새 입력의 정당한 rank 저장과
충돌 rank 거부를 확인했으나 **G1 운영 새 Capture가 생성된 것은 아니다.**

이번 후속 코드는 이미 존재하는 **S17 선택 설치형**
`tools/data/prospective_daily.py`의 '성공' 판정을 강화한다.
예전에는 Scanner 작업 JSON에 `prospective_capture.status=COMPLETE/DUPLICATE`
값이 있으면 성공 로그로 넘어갈 수 있었다. 지금은 성공 반환 전에
기존 실제 Simulation SQLite를 **mode=ro + query_only**로 확인한다.

- HTTP 응답의 Capture ID·상태·source_job_id, 요청한 시장과 실제 기준일이
  `prospective_capture_run`의 저장 행과 일치해야 한다.
- COMPLETE는 자기 캡처를, DUPLICATE는 정당한 canonical COMPLETE를 확인한다.
  동일 실행 key / source snapshot hash / result hash / 반환 후보 수가
  canonical과 맞지 않으면 HOLD한다.
- 저장된 실제 샘플 수 및 연속된 sample index, 신호일, 원본 Snapshot
  해시를 조회 시점의 DB에서 확인한다. 불일치·누락·불일치 스키마 등은
  `HOLD_MANUAL_REVIEW` 및 고정 `FROZEN_CAPTURE_*` 오류 코드로 반환하며
  개별 주가·종목·원본 Snapshot·SQL 에러를 출력하지 않는다.
- 정상 저장 증거를 확인한 성공 보고에만
  `persisted_capture_verified=true`,
  `persisted_snapshot_hashes_verified=true`,
  `persisted_sample_count`를 표시한다. 이는 저장 근거 증명이지
  S7 LOCAL_VALIDATED, 정책 승인, 투자 성과·공식 공표 시점 증명은 아니다.
- S17 한국시간 계산은 고정 UTC+09:00을 사용해 Windows에 Python
  `tzdata`가 없어도 동작한다. 원래 장전 실행창/중복 차단/Scanner
  및 S16 처리/사용자 선택 설치 원칙은 변경하지 않았다.

`backend/tests/test_prospective_daily_s17.py`에는 실제 VN-P2-S2 **합성**
SQLite에서 COMPLETE/정당한 DUPLICATE의 읽기 전용 검증, 없는 HTTP ID,
잘못된 job, 변조된 Snapshot hash 거부, 미저장 상태의 성공 거부가 포함된다.
CI `Fresh Clone / Windows`에도 이 새 시나리오를 연결했다.

**범위 및 HOLD:** 실제 Windows 사용자 운영 DB에 쓰거나 새 Scanner job,
KRX/TypeSafe/JEV 연결, S17 예약작업 설치, 실주문, 비공개 실행 정보 업로드,
PR merge를 수행하지 않았다. 기존 Capture를 역산 수정하거나 INVALID 24건을
승격하지 않는다. 실제 G1은 별도 승인 하에 최신 공식 EOD·수집 권리·요청
예산을 확보한 뒤 **새 Capture 실행 및 증거 대조**가 완료돼야 PASS다.
