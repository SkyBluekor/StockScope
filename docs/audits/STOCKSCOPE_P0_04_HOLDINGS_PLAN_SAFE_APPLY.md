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

P0-04 완료 판정에는 사용자 보유 계좌의 실제 데이터 조회 가능성, 기존 기능의 안전한 migration 준비 상태, 사용자 명시 확정 후 영속 저장·재조회, 충돌 UX 확인이 추가로 필요하다.
