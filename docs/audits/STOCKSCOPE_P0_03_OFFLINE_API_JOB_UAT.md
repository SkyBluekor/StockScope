# P0-03 — Windows 실제 운영 DB의 **격리된** 과거 두 날짜 API Job UAT

사용자 PC에서 P0-02는 2026-10-21 EOD, KOSPI 940·KOSDAQ 1822 행,
실제 Scanner 18개 후보·오프라인 계산 PASS였다.

다음 CLI는 같은 운영 DB를 **SQLite 온라인 read-only 백업**으로 TEMP에 복제,
직전 공통 저장일에 실제 동결 Scanner로 후보를 구한 뒤 지정한 다음 저장일
(예: 2026-10-21)로 **기존 `create_scanner_job` → 실제
`_run_scanner_job` → `/jobs/{id}` GET handler**를 실행한다.
실제 ProspectiveService / ProspectiveCatalog도 **새 임시 Simulation DB**에
대해서만 begin/finalize/read를 수행한다. 모의 분석 결과로 통과시키지 않는다.

**중요:** KRX/TypeSafe 직접 호출 0건; 외부 socket 거부.
freshness 메서드는 네트워크 대신 복제본의 **지정한 과거 저장일**만 반환한다.
이 경로는 **실제 최신 EOD 공표 확인이 아니며**, 브라우저 UI 클릭 테스트도
아니다. Prospective Reference Capture(매크로/별도 migration)도 실행하지 않는다.

## 실행 (기존 PowerShell)

```powershell
cd C:\Projects\StockScope
$repo = (git rev-parse --show-toplevel).Trim()
$db = Join-Path $repo "backend\runtime\market_history\market_history.db"
$python = Join-Path $repo ".venv\Scripts\python.exe"
$work = Join-Path $env:TEMP "StockScope_P0_02_90745c8d5d49"

git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
if ($LASTEXITCODE -ne 0) { throw "fetch 실패" }
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha
if ($LASTEXITCODE -ne 0) { throw "worktree 갱신 실패" }

& $python (Join-Path $work "tools\data\p0_03_offline_api_job_uat.py") `
    --market-db $db `
    --operational-repo $repo `
    --as-of 2026-10-21 `
    --market-scope ALL
```

리포트 `OFFLINE_API_JOB_CAPTURE_VERIFIED`면 **격리된 과거 저장일 2개**의
실제 Scanner 코어/Job/임시 capture 기록 정합성 PASS. 다른 `HOLD_*`는
해당 단계에서 멈춤. 운영 DB·운영 Simulation DB·기존 server Job·정책·
API 키·실제 브로커·실시간 KRX 데이터는 절대로 건드리지 않음.

이후 **별도 실제 앱 사용자 UAT**는 실제 최신 확정 EOD를 검증하고 기존
후보의 재판단 버튼을 눌러 실제 `job_id` 및 저장 capture를 확인해야 한다.
이는 외부 데이터 권한 및 최신 일봉 승인 후에만 진행한다.


## FastAPI 실제 HTTP 라우팅 계약 (기존 동일 운영 시장 DB 스냅샷)

기존 검증 명령 마지막 줄에 **`--verify-asgi-http`**를 추가한다.
기존 `_run_scanner_job` 함수만 직접 부르는 대신, 아래의 진짜
FastAPI HTTP 라우터를 `httpx.ASGITransport`로 호출한다.

- POST `/api/backtest/scanner/jobs` — 올바른 재판단 요청 202
- GET `/api/backtest/jobs/{job_id}` — 같은 Job ID / 완료 결과 200
- 강제 새로고침 미사용, 과거 as-of 직접 지정 — 각각 HTTP 400 필수
- Prospective 캡처 저장은 오직 TEMP Simulation DB. 서버의 전체
  lifespan(Watch, 실시간 시세, 외부 리소스)은 아예 시작하지 않는다.
- 실제 TCP 포트, 일반 uvicorn 프로세스, 운영 웹 서버가 아니라
  **실제 FastAPI ASGI 라우팅/직렬화만 네트워크 없이 검증**한다.
  따라서 완료 시 `OFFLINE_ASGI_JOB_CAPTURE_VERIFIED`를 표시한다.
- 이전 P0-03 실제 DB 검증은 그대로 유효하며 기본 옵션 변경 없음.
  최신 KRX 공식 EOD 확인 및 실제 Windows 브라우저-서버 통신은
  이 모드의 검증 대상이 아님.

```powershell
cd C:\Projects\StockScope
$repo = (git rev-parse --show-toplevel).Trim()
$work = Join-Path $env:TEMP "StockScope_P0_02_90745c8d5d49"
$db = Join-Path $repo "backend\runtime\market_history\market_history.db"
$python = Join-Path $repo ".venv\Scripts\python.exe"

git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
if ($LASTEXITCODE -ne 0) { throw "fetch 실패" }
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha
if ($LASTEXITCODE -ne 0) { throw "worktree 갱신 실패" }

& $python (Join-Path $work "tools\data\p0_03_offline_api_job_uat.py") `
    --market-db $db `
    --operational-repo $repo `
    --as-of 2026-10-21 `
    --market-scope ALL `
    --verify-asgi-http
```
