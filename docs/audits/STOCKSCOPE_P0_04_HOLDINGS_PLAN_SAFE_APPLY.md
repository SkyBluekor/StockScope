# StockScope P0-04 — 보유분 관리 계획의 안전한 명시 적용

기준일: 2026-10-27 (KST)  
대상: PR #170 / `codex/p0-01-mvp-c1-c2-integration-20261022`

## 실제 제품 흐름과 변경 지점

기존 HoldingsWorkspace → HoldingDecisionPanel → `POST /api/holdings/decisions/{decision_id}/apply-plan` → HoldingsManagementService 흐름을 그대로 재사용한다. 새로운 주문/거래 기능, 새 DB schema 또는 신규 provider는 만들지 않는다.

P0-04 1차에서 화면은 보유 Position, 최신 분석 Revision, 활성 계획 ID/version이 일치해야 손절·1차 목표·2차 목표 가격의 이전/신규 비교를 열고, 사용자가 두 번째 클릭으로 적용을 확정하도록 바뀌었다. 프런트엔드 단독 검사만으로는 충분하지 않다.

## 서버 검토에서 발견한 경계

`_current_source()`는 `ReadOnlyDataStateReader`의 `analysis_current_use_allowed`를 확인하여 `evidence.proposal_ready`에 반영한다. 그러나 이전 `apply_plan()`은 저장된 결정이 stale인지, Analysis Revision ID가 존재하는지, 손절 완화가 있는지 확인하면서 **proposal_ready가 거짓이어도** 현재 사용이 승인되지 않은 Revision을 관리 계획으로 명시 적용할 수 있는 경로가 있었다.

이번 서버 수정은 `proposal_ready=true`, `new_plan_horizon_activatable=true`, `proposal_conflict=null`의 **저장된 판단 근거**를 적용 전 필수 조건으로 삼는다. `proposal_ready=false` 등은 409 `HOLD_DECISION_PLAN_NOT_READY`로 거부한다. 화면도 `proposal_ready=true`를 요구한다.

또한 가격과 Revision이 불변이어도 현재 사용 승인 상태가 바뀌거나 Horizon 적용 가능성이 변하면 저장 결정의 stale 원인에 `PROPOSAL_READINESS_CHANGED` / `HORIZON_APPLICABILITY_CHANGED`를 기록한다. 이전 결정을 다시 사용할 수 없고, 사용자가 명시적으로 판단을 갱신해야 한다.

## 실제 FastAPI API 회귀 (합성 TEMP SQLite)

- 기존 분석 → 새로운 Revision → `POST /decisions/evaluate` → `POST /decisions/{id}/apply-plan` → **새로운 GET /stocks/{stock_id}/management**에서 활성 plan/version/이전 버전 확인
- `GET /decisions/{id}`에서 적용 이전 판단 stale 및 적용 resolution 연결 확인
- 같은 판단의 재적용은 409로 거부, 보유 수량/평단 및 append-only position event 건수 변화 없음
- `proposal_ready=false`지만 정상 Revision과 손절가가 있는 경우 적용 409, 계획/결정 resolution/원장 기록 추가 없음
- 기준일 가격·분석 Revision은 그대로 두고 analysis current-use 계약만 회수할 경우 읽기 재조회가 stale이고 계획 적용 409
- Node 측 계획 비교 가드도 동일한 readiness와 기존 plan ID/version, Horizon/가격 일치 요구

## 검증 명령 (새 패키지 설치 불필요, 개발/CI 테스트 DB만 사용)

```powershell
cd C:\Projects\StockScope
$work = Join-Path $env:TEMP 'StockScope_P0_02_90745c8d5d49'
git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
if ($LASTEXITCODE -ne 0) { throw 'fetch failed' }
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha
if ($LASTEXITCODE -ne 0) { throw 'worktree update failed' }
& (Join-Path (Get-Location) '.venv\Scripts\python.exe') -m pytest -c (Join-Path $work 'backend\pyproject.toml') (Join-Path $work 'backend\tests\test_holdings_decision_api_vnp3s1.py')
```

이 명령은 기존 설치된 Python/의존성을 재사용하며 테스트의 `tmp_path`에 SQLite를 새로 생성한다. **사용자 운영 Holdings/시장 DB에 대해 계획을 적용하지 않는다.** 위 예시는 경로/임포트 설정에 따라 실제 작업 PC에서는 `$work` 루트에서 실행 환경을 조정해야 할 수 있다. 신뢰할 수 있는 인수 근거는 정확 HEAD의 GitHub CI와 테스트 내용이다.

## 미완료 / 금지

이 단계의 API 회귀는 운영 DB에 실제 보유분이 있는 사용자 PC UAT의 대체가 아니다. StockScope 생산 환경의 Holdings migration 실행, live KRX/TypeSafe/JEV 요청, 실제 증권 주문, 운영 데이터 변경, PR 병합, 배포는 수행하지 않는다. 특히 실제 사용자 보유 계획 적용은 테스트를 빙자해 자동 실행하지 않는다.

## P0-04 3차: 레거시 직접 적용 엔드포인트 폐쇄

- 기존 `POST /api/holdings/positions/{position_id}/plans/apply`는 `analysis_revision_id`만 받아 활성 계획을 직접 변경했다. 이는 판단 생성→가격 검토→명시 적용 경로를 우회할 수 있었으며, 내부 `HoldingManagementService.apply_analysis_plan()`의 구조적인 가격·Horizon 검증만으로는 최신 data contract의 `current_use_allowed`를 보장하지 못했다.
- 이 **외부 HTTP 엔드포인트만** `deprecated`로 표시하고 항상 HTTP **409** `HOLD_PLAN_DECISION_REVIEW_REQUIRED`를 반환한다. 실제 DB 초기화/조회/변경, 자동 승인 결정 생성, 계획 적용은 하지 않는다. 요청 형식은 유지해 기존 호출자가 이유를 알 수 있게 한다.
- 이전 프런트엔드의 더 이상 사용되지 않는 `applyHoldingManagementPlan()` helper를 제거했다. 현재 화면은 원래부터 `applyHoldingDecisionPlan()`만 사용한다.
- 유일하게 지원하는 쓰기 흐름: `POST /api/holdings/positions/{position_id}/decisions/evaluate` → 저장된 결정/관리 가격 비교 → 사용자가 확정 → `POST /api/holdings/decisions/{decision_id}/apply-plan`. 같은 decision의 중복 적용 및 오래된 분석은 서버에서 거부된다.
- 내부 `HoldingManagementService.apply_analysis_plan()`은 기존 Fixtures/마이그레이션 테스트의 명시적 운영 서비스로 보존한다. 임시 테스트 DB에서는 기존 계획 버전/위험 차단 테스트가 그대로 유지되어야 한다. **구형 외부 클라이언트는 반드시 호출 경로를 바꿔야 한다.**
- API 회귀 테스트는 마이그레이션 전/후에 유효한 Revision으로 레거시 URL에 POST해도 `_catalog()` 접근이 없고 Holdings SQLite 바이트가 동일함을 확인한다. OpenAPI deprecated 속성과 409 안내도 확인한다.

P0-04의 이 3차 작업은 **기존 우회 엔드포인트 폐쇄**이지, 사용자 Windows 실보유 데이터 UAT 완료가 아니다. 기존 일봉/원본 DB, 실제 계좌·주문, KRX/유료 provider, 배포/병합은 그대로 금지한다.

P0-04 완료 판정에는 사용자 보유 계좌의 실제 데이터 조회 가능성, 기존 기능의 안전한 migration 준비 상태, 사용자 명시 확정 후 영속 저장·재조회, 충돌 UX 확인이 추가로 필요하다.

## P0-04 4차: 운영 Windows Holdings 저장 상태 읽기 전용 사전 점검

신규 `tools/data/p0_04_holdings_readonly_preflight.py`는 **표준 라이브러리만 사용**한다. 실제 운영 Holdings SQLite와 실제 Market SQLite를 각각 `mode=ro` + `PRAGMA query_only=ON`으로 열고, 기존 DB를 생성하거나 migration하지 않는다. WAL이 남아 있는 SQLite를 잘못 무시할 수 있는 `immutable=1`도 사용하지 않는다. 네트워크, KIS, KRX, JEV, TypeSafe, 서버 시작·계획 적용 호출을 포함하지 않는다.

검사: 두 DB 존재/기본 스키마, Holdings quick_check, P3-S1 decision·P3-S2 recovery·P4-S1 watch 테이블 및 schema version 존재, 등록 계좌/감시 종목/OPEN·CLOSED Position/원장 이벤트/활성 관리 계획/분석 Revision **집계 건수**, 활성 계획이 종료된 Position에 붙거나 없는 Position을 참조하는 등 구조 불일치, 저장된 Market 일봉·지수 행 건수와 마지막 저장일. **계좌명, UUID, 종목코드, 가격·평단·수량은 stdout에 출력하지 않는다.** 날짜·집계 건수는 출력된다.

Windows 사용자가 실제 PC에서 확인할 때의 읽기 전용 명령(기존 Python venv만 재사용):

```powershell
cd C:\Projects\StockScope
$repo = (git rev-parse --show-toplevel).Trim()
$work = Join-Path $env:TEMP "StockScope_P0_02_90745c8d5d49"
$holdings = Join-Path $repo "backend\runtime\holdings\holdings.db"
$market = Join-Path $repo "backend\runtime\market_history\market_history.db"
$python = Join-Path $repo ".venv\Scripts\python.exe"
git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
if ($LASTEXITCODE -ne 0) { throw "fetch failed" }
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha
if ($LASTEXITCODE -ne 0) { throw "detached worktree update failed" }
& $python (Join-Path $work "tools\data\p0_04_holdings_readonly_preflight.py") --holdings-db $holdings --market-db $market
```

CLI는 JSON 보고서를 stdout으로 출력한다. 상태가 `BLOCKED_*` 또는 `HOLD_*`인 경우 exit=2이며, 이는 **자동 복구가 아니라** 추가 검토가 필요함을 의미한다. `READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED` 또는 `NO_OPEN_POSITIONS_TO_UAT`는 exit=0이나, 이는 **DB 스키마/집계 상태를 읽었다는 의미뿐**이고 라이브 데이터 제공자 승인·완전한 시장 데이터·보유 계획 적용 권한을 뜻하지 않는다.

CI는 Python 전체 백엔드 테스트와 별도 Windows Fresh Clone에서 합성 `tmp_path` SQLite를 사용해 누락 DB, migration 미수행, 정상 schema, 손상/부분 schema, 읽기 전용·개인정보 비출력, 열린 WAL 반영, CLI 경로를 점검한다. 실제 사용자 Windows 운영 DB 결과는 **사용자 PC에서 명령을 실행한 로그가 있어야** 확인된 것으로 인정한다. 운영 마이그레이션·실제 보유 계획 적용은 이 진단으로 절대 자동 수행하지 않는다.

## P0-04 4차 Windows 사용자 운영 DB 사전 점검 증거 — 2026-10-27

사용자 Windows에서 `bc75d5636560f2747583376b57df9aee09d37ffd`를 별도 TEMP worktree로 체크아웃하고 **실제 운영 Holdings/Market DB를 mode=ro로 조회**했다. 사용자 로그의 결과는 `READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED`.

- 2 계좌, 11 감시 종목, 1 OPEN Position, 0 CLOSED Position, 1 ACTIVE Plan, 8 Analysis Revisions, 1 ledger event.
- Decision / Recovery / Watch domain tables 모두 `READY` (4/4, 3/3, 6/6).
- 종료 Position의 활성 계획, 없는 Position의 활성 계획, 여러 ACTIVE 계획, ACTIVE 없는 OPEN Position은 각각 **0건**.
- Market `stock_rows=448301`, `index_rows=324`, 마지막 저장 `20261021` (**공식 최신 EOD 검증 아님**). 2026-10-27 기준 6일 이전의 기록이므로 신규 판단의 현재 사용 가능 여부는 별도 평가 필요.
- `db_write_calls=0`, `external_requests=0`, `actual_plan_applied=false`, `ready_for_plan_write=false`. 이번 조회 결과만으로 live KIS 계좌 확인이나 신규 계획 적용을 인정하지 않는다.

**판정: 실제 Windows 운영 DB의 저장 구조/관계 점검 통과. 계획 적용 UAT는 미수행.**

## P0-04 5차: 실제 보유 Position의 최신 분석 사용 가능 여부 — 읽기 전용

새 스크립트 `tools/data/p0_04_holdings_workspace_probe.py`는 동일한 두 운영 SQLite를 읽기 전용으로 검사하고, 이미 만들어진 `HoldingsWorkspaceQueryService`가 보유 Position에 대해 반환하는 **저장된 EOD 분석 계약과 활성 계획 보호 상태**를 종목코드·계좌명·가격·Position ID를 출력하지 않고 요약한다. 실제 Position은 스크립트가 내부적으로 조회하되 stdout에는 민감한 원본 객체 대신 allowlist 상태 코드만 표시한다.

핵심 결과: `analysis_contract_status`, `analysis_reason_code`, `analysis_current_use_allowed`, `active_plan_count`, `stored_eod_management_state`(절대로 현재 실시간 가격 판정 아님), `decision_effective_status`, `decision_stale`, `review_conditions`. 모든 `ready_for_plan_write`는 **false**, 외부 호출·migrate·evaluate·apply·거래 기록 없음. 사전 점검이 통과한 경우에만 실행하고, 실제 보유건수와 활성 계획 건수의 변경을 감지하면 결과를 차단한다.

Windows에서 로컬 브랜치 fetch/임시 worktree 업데이트를 완료한 다음, 기존 `$repo`, `$work`, `$python`, `$holdings`, `$market` 변수를 재사용한다:

```powershell
& $python (Join-Path $work "tools\data\p0_04_holdings_workspace_probe.py") --holdings-db $holdings --market-db $market
```

CLI 스크립트는 `C:\Projects\StockScope\.venv` 기존 라이브러리를 사용하며 추가 프로그램/서비스 기동·환경 변경 없이 실행된다. 반환 상태가 `READ_ONLY_WORKSPACE_STORED_STATE_OBSERVED`더라도 **현재 분석의 신규 사용 승인 여부는 필드별로 확인해야 한다.** 최종 사용자 승인하에만 앞으로 별도 계획 적용 UAT를 진행한다.

## P0-04 6차 — 사용자 실제 Windows 상태 기반 STALE / Recovery 사유만 출력

사용자의 P0-04 5차 원본 데이터 읽기 전용 점검 결과: `analysis_current_use_allowed=true`, `analysis_contract_status=VALID`, `analysis_basis_date=2026-10-21`, 활성 계획 1건 `WITHIN_PLAN`(저장 EOD 기준), 계획 제안 `SAME_AS_ACTIVE`, 현재 판단 `STALE`, `RECOVERY_REVIEW_OPEN`. **신규 계획을 적용하거나 이미 적용된 손절 값을 변경할 이유는 확인되지 않았다.** 이는 실시간 시세나 공식 최신 KRX 게시 데이터의 정확성을 검증한 것은 아니다.

V2 `tools/data/p0_04_holdings_workspace_probe.py`의 허용 출력에 다음을 추가했다.
- `decision_stale_reasons` 및 `stale_reason_counts`: 서버의 `_stale_reasons`에서 생성된 **정해진 10개 사유 코드**만 출력. 누락 시 `STALE_REASONS_UNAVAILABLE`; 비표준 값은 `UNRECOGNIZED_STALE_REASON`.
- `recovery.open_review_status`(`OPEN`/`CLOSED`), `opened_date`, `open_review_assessment_count`, `latest_assessment_present`, `latest_assessment_thesis_state`, `latest_assessment_review_action`, `latest_assessment_date`, 이전 평가 당시의 분석/관리 계획이 현재와 일치하는지 여부(둘 중 하나의 source ID가 없다면 `null`). 원본 note/ID/가격/수량은 절대 출력하지 않음.
- `open_recovery_reviews`, `open_recovery_reviews_without_assessment` 집계. `ready_for_plan_write=false` 유지.

**중요:** `STALE`는 이전 판단의 전제 변경을 뜻한다. 원인 코드가 나오더라도 자동 판단 생성 또는 Recovery 종료 금지. Recovery `thesis_state`/`review_action`은 저장된 사용자의 과거 검토 기록이지 현재 매매 추천이 아니다. `WITHIN_PLAN`은 저장 EOD 근거일 뿐 현재 안전성 보장이 아니다.

동일 Windows PowerShell 변수 (`$work`, `$holdings`, `$market`, `$python`) 및 최신 브랜치 커밋으로 worktree를 교체한 뒤 기존 **동일 스크립트** 재실행:

```powershell
& $python (Join-Path $work "tools\data\p0_04_holdings_workspace_probe.py") --holdings-db $holdings --market-db $market
```

테스트는 합성 TEMP SQLite에 기존 판단 평가→보유 수량 정정→STALE 판정, Recovery 개설·평가 저장→별도 읽기 전용 workspace 조회를 수행한다. **이 쓰기 시뮬레이션은 테스트 전용 임시 SQLite에만 적용**된다. Windows 운영 Holdings/Market DB는 읽기 전용 조회만 수행한다.

## P0-04 7차 — 실제 Holdings React 패널 브라우저 검증 (완전히 합성된 API)

6차 Windows 읽기 전용 확인: `ACTIVE_PLAN_CHANGED`로 이전 판단이 STALE가 되었고, 최신 저장 Analysis/활성 관리 계획은 `SAME_AS_ACTIVE`로 일치한다. Recovery OPEN(2026-10-20), Assessment 0. **이 기존 계획을 다시 적용하지 않고 보존한다.**

신규 `frontend/e2e/p004-holdings-panel.jsx`는 실사용 `HoldingDecisionPanel.tsx`와 실제 `holdingsApi.ts` 클라이언트를 별도의 테스트 전용 Vite 페이지 `p004-test.html`에 렌더링한다. `frontend/e2e/p004-holdings-panel.spec.mjs`의 Playwright 테스트가 실제 Chromium에서 사용자의 버튼 클릭/비동기 응답/새로고침을 확인한다. **HTTP 응답은 브라우저에서 합성 상태로 완전 intercept되며 실제 FastAPI/운영 DB에 연결하지 않는다.** 따라서 UI와 HTTP 계약 연결 검증이지, 운영 백엔드·실제 DB를 통한 전체 E2E라고 표현하지 않는다.

검증 시나리오:
- `STALE`(`ACTIVE_PLAN_CHANGED`) → 사용자가 **최신 판단 다시 만들기** 선택 → 합성 POST 한 번 → 갱신된 판단이 기존 계획과 `SAME_AS_ACTIVE`일 때 **새 계획 비교/적용 버튼 부재**, 재조회 후에도 v1 ACTIVE 유지.
- 분석 Revision의 새 제안: 비교 전에 적용 불가 → 손절/목표 가격 표시 → 취소 후 apply 호출 없음 → 재비교 후 **이 가격으로 관리 계획 적용** 명시 클릭 → 합성 응답에서 ACTIVE v2 교체, 이전 판단 STALE → 화면 재조회 후 재적용 차단. 원장 이벤트 변경 0.
- 비교 승인 중 합성 가격 제안이 변경되면 확인 버튼이 소멸하고 다시 비교해야 함. 기존 승인 fingerprint는 재사용 불가.
- 브라우저에서 `/api/*` 요청은 항상 mock 응답이며, 타 도메인 요청·예상하지 못한 엔드포인트는 차단. 결제/거래/실 Broker/KRX Provider 호출 불가.

단독 테스트:
```powershell
cd C:\Projects\StockScope\frontend
npx playwright test -c playwright.p004.config.mjs
```
(개발 머신에 Playwright 테스트 러너/Chromium이 이미 설치돼 있을 때만. CI는 기존 P0-03 용 pinned `@playwright/test@1.56.1` 및 Chromium 설치 단계를 재사용.)

본 단계는 기존 Windows 운영 Holdings 파일을 전혀 열지 않고 데이터 변경을 하지 않는다. **실제 Windows 브라우저 전체 HoldingsWorkspace와 실제 FastAPI, Recovery 수동 검토·평가/종료, 운영 DB 기반 Apply UAT는 여전히 미실행**이다. 이 구분을 유지한 상태에서 PR #170 Draft를 보존한다.

## P0-04 8차 — 운영 Windows 데이터 사본 + 실제 FastAPI GET + 실제 Chrome UI UAT

기존 7차는 React 실제 컴포넌트와 모의 HTTP를 연결한 Chromium 3/3 테스트였다. 이번 8차는 두 SQLite **실제 운영 파일을 원본 read-only로 백업**한 일시적 스냅샷과 진짜 Holdings 조회 핸들러를 연결해 한 단계 더 검증한다.

- `tools/data/p0_04_windows_readonly_browser_uat.py`는 운영 `--holdings-db`·`--market-db` 경로를 명시적으로 받는다. 먼저 P0-04 기존 DB preflight(실제 운영 데이터 읽기 전용)가 `READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED`인지 확인하고 OPEN Position이 정확히 1개일 때만 진행한다.
- 기존 P0-03에서 검증한 SQLite `mode=ro`/backup API를 재사용하여 committed WAL까지 포함해 Windows 사용자 전용 LocalAppData Temp의 임시 폴더에 `holdings_snapshot.sqlite3`, `market_snapshot.sqlite3`을 만든다. 임시 사본의 데이터는 민감하므로 정상/에러/중단 이후 반드시 삭제를 시도하고 잠금으로 제거 불가 시 **실패 상태 및 수동 정리 위치**를 출력한다. 원본은 전혀 변경하지 않는다.
- 제한된 FastAPI UAT worker는 `127.0.0.1:5284`에서 실제 `stock_decision_support`, `stock_management`, `holding_recovery_context` **GET 함수만** 노출한다. `/api/holdings/*` 전체 라우터나 FastAPI 앱 lifespan을 기동하지 않는다. 판단 생성/계획 적용/Recovery 평가 기록/종료/잔고 동기화 등 POST는 **등록되지 않는다**. 외부 소켓 연결을 차단한다.
- `127.0.0.1:5283`의 테스트 Vite 서버는 실사용 `HoldingDecisionPanel`·`HoldingRecoveryPanel`을 데이터 사본에서 가져온 실제 FastAPI GET 결과로 렌더링한다. 기존 사용자의 보유 종목, 계좌명, 손절·목표 가격은 그 로컬 헤드리스 브라우저 메모리에서만 사용한다. Playwright reporter는 검증 부울값만 반환하고 trace/screenshot/video는 **off**, 실패 stdout도 폐기한다.
- `frontend/playwright.p004.loopback.config.mjs`는 사용자의 이미 설치된 Google Chrome만 사용한다. 브라우저는 localhost GET만 가능하고 외부 요청/POST를 차단한다.
- 읽기 화면에서 `ACTIVE_PLAN_CHANGED`가 단일 STALE 원인이면 최신 계획과 과거 판단의 불일치 안내를 표시한다. `SAME_AS_ACTIVE`면 새 계획 적용/비교 버튼이 없어야 한다. OPEN Recovery면 진행 중 UI, 아니면 시작 버튼을 표시한다. 새로고침 후에도 3개 실제 GET 모두 성공해야 한다.
- CI는 `backend/tests/test_p0_04_windows_readonly_browser_uat.py`에서 실제 FastAPI GET·모든 mutating route 차단·임시 SQLite 복제/원본 해시 불변·임의 다른 Position 경로 차단을 검증한다. **CI는 사용자의 Windows 운영 DB에 접근하지 못하고, Windows 시스템 Chrome 운영 환경 UAT는 사용자가 실행해야 확인할 수 있다.**

### 사용자 Windows 명령

기존 `$repo`, `$work`, `$python`, `$holdings`, `$market` 변수를 재설정한 후 P0-04 개발 브랜치를 fetch 및 별도 TEMP worktree로 checkout한다. 로컬 main과 사용자 DB는 수정하지 않는다.

```powershell
cd C:\Projects\StockScope
$repo = (git rev-parse --show-toplevel).Trim()
$work = Join-Path $env:TEMP "StockScope_P0_02_90745c8d5d49"
$python = Join-Path $repo ".venv\Scripts\python.exe"
$holdings = Join-Path $repo "backend\runtime\holdings\holdings.db"
$market = Join-Path $repo "backend\runtime\market_history\market_history.db"
git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha
if ($LASTEXITCODE -ne 0) { throw "Checkout failed" }
& $python (Join-Path $work "tools\data\p0_04_windows_readonly_browser_uat.py") `
  --holdings-db $holdings `
  --market-db $market
```

본 도구는 `$work\frontend\node_modules\@playwright\test\cli.js`, Node/npm, 사용자 설치 Chrome이 이미 존재해야 실행한다. 도구는 **브라우저/패키지를 자동 설치하지 않는다**. `HOLD_PLAYWRIGHT_OR_NODE_MISSING` 상태에서는 우선 실행 환경을 점검한다. 임시 DB 삭제가 실패하면 출력되는 `scratch_path`의 삭제 상태를 꼭 수동 검토해야 한다.

판정 `WINDOWS_REAL_HOLDINGS_READONLY_BROWSER_VERIFIED`는 **Windows 운영 파일을 읽기 전용 복사한 임시 사본 + 로컬 실제 GET UI**만 확인한다. 결코 운영 DB에서 신규 판단을 생성/관리 계획을 적용/Recovery 평가하거나 종료한 결과가 아니고, 당일 KRX 최신 공식 EOD 또는 거래 계좌 조회도 아니다. PR은 Draft로 유지하고 승인 없는 실제 데이터 변경을 금지한다.
