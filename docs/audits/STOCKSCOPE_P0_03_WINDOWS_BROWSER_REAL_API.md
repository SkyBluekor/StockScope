# P0-03 — 기존 Google Chrome ↔ 격리 FastAPI ↔ 실제 Scanner

실제 운영 시장 DB의 읽기 전용 SQLite snapshot으로 이전 거래일의 후보를
동결 Scanner 코어에서 가져온 다음, Chromium 버튼 클릭으로 2026-10-21
과거 저장 거래일의 재판단을 실제 로컬 HTTP 서버에 요청한다.

브라우저 127.0.0.1:5279 → Vite Proxy → 격리된 FastAPI 127.0.0.1:5280
→ 실제 Scanner → 오직 TEMP ProspectiveService 저장 경로를 검증한다.

## 안전장치

- 운영 market_history.db: SQLite read-only WAL snapshot 후 사용. 원본 불변.
- 전체 app.main/lifespan, 실시간 Watch, KRX, TypeSafe, 주문은 시작하지 않음.
- 서버는 Scanner preflight/POST job/GET job 및 UAT seed/health만 제공.
- KRX는 OfflineKrx로 대체. 외부 socket 차단, loopback만 허용.
- 브라우저도 외부 요청 차단, 다른 API 보조 조회만 격리 mock 사용.
- 보유자산/운영 Simulation/기존 서버 DB는 쓰지 않음.
- 5279/5280 이미 사용 중이면 서버에 접속하지 않고 HOLD 상태 반환.
- 실행 뒤 서버 종료 및 TEMP 데이터 삭제.

## PowerShell 실행

다음 명령은 메인 Git 브랜치를 변경하지 않고 기존 worktree를 갱신한다.

```powershell
cd C:\Projects\StockScope
$repo = (git rev-parse --show-toplevel).Trim()
$work = Join-Path $env:TEMP 'StockScope_P0_02_90745c8d5d49'
$db = Join-Path $repo 'backend\runtime\market_history\market_history.db'
$python = Join-Path $repo '.venv\Scripts\python.exe'
git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
if ($LASTEXITCODE -ne 0) { throw 'Fetch 실패' }
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha
if ($LASTEXITCODE -ne 0) { throw 'Worktree 갱신 실패' }
cd (Join-Path $work 'frontend')
# 이전 명령에서 npm 의존성을 이미 설치했다면 추가 설치하지 않는다.
# Playwright 테스트 실행기만 검사한다. 전용 Chromium은 내려받지 않는다.
if (-not (Test-Path '.\\node_modules\\@playwright\\test\\cli.js')) {
    throw 'Playwright 테스트 패키지가 없음. 브라우저 다운로드 없이 실행할 수 있도록 테스트 패키지 상태부터 확인하세요.'
}
cd $repo
& $python (Join-Path $work 'tools\data\p0_03_windows_browser_uat.py') `
  --market-db $db `
  --operational-repo $repo `
  --as-of 2026-10-21 `
  --market-scope ALL
```

브라우저는 컴퓨터에 설치된 Google Chrome만 재사용하며 별도 Chromium
다운로드가 필요 없다. 기본 설치 경로 또는 Windows App Paths에서
찾고, 다른 위치에 Chrome이 있으면 실행 전에
`$env:P003_CHROME_EXECUTABLE = 'C:\Path\To\chrome.exe'`
환경변수로 지정할 수 있다. Chrome이 없으면
`HOLD_INSTALLED_GOOGLE_CHROME_NOT_FOUND`로 종료한다.

성공 응답은 OFFLINE_WINDOWS_BROWSER_REAL_FASTAPI_VERIFIED.
그 외에는 HOLD_* 상태가 반환되며 미검증을 PASS로 바꾸지 않는다.

이것은 진짜 Windows 브라우저 ↔ 격리 FastAPI ↔ 과거 데이터 재계산
검증이지, 최신 공식 KRX EOD 확인이나 전체 운영 앱의 라이브 운용
검증은 아니다. LEGACY_CURRENT_10_FALLBACK 활성 정책 문제도 남는다.
## WinError 32 임시 복제본 파일 잠금 대응 (2026-10-27)

이전 PowerShell 실행에서 TEMP/TMP가 `ESTsoft\\CreatorTemp`로 지정되어,
임시 `market_snapshot.sqlite3` 삭제 시 `PermissionError: [WinError 32]`가 발생했다.
외부 보안/인덱싱 프로그램의 잠금인지, 자식 프로세스가 종료된 직후의
짧은 핸들 해제 지연인지는 해당 traceback만으로 확정할 수 없다.

새 실행기는 Windows의 `%LOCALAPPDATA%\\Temp` 폴더를 명시적으로
사용하여 리디렉션된 `TEMP`를 피한다. FastAPI 자식 프로세스 종료를
확인한 뒤 임시 파일 삭제를 여러 번 재시도한다. 끝까지 잠겨 있다면
예외 traceback 대신 `HOLD_TEMP_CLEANUP_FAILED`와
`temp_folder_for_manual_review` 경로를 JSON으로 남겨 사용자에게 알린다.
원본 시장 DB를 건드리지 않으며, 삭제 실패 시 성공 판정을 내리지 않는다.

이전에 남은 `ESTsoft\\CreatorTemp` 폴더는 새 실행기가 자동 삭제하지
않는다. 삭제가 필요한 경우 실행 프로세스가 모두 종료된 뒤 정확한
`StockScope_P0_03_Browser_*` 폴더만 별도 확인해 정리한다.
