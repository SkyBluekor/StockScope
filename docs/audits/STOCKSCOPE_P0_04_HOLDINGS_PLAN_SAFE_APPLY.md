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
