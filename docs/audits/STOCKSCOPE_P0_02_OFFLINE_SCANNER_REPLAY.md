# P0-02 — 실제 Scanner 계산 오프라인 재실행

## 무엇을 검증하는가

2026-10-22 사용 PC의 운영 Market Store read-only 감사에서 2026-10-21
KOSPI 940종목/KOSDAQ 1822종목, 양 시장 지수 1행, 148개 같은 날짜가 관측됐다.
단순 저장 행 증명과 다른 단계로 **기존 StockScannerService.run()** 을
원본 DB에서 만든 일관된 SQLite 백업본으로 직접 실행한다.

네트워크 없는 provider와 외부 socket 거부 장치를 사용하므로 **KRX/TypeSafe/API 호출은 0건**.
필요한 lookback `day_status`가 하나라도 없으면 계산하기 전 HOLD 한다.
빈(휴장 추정) marker 자체는 이전 Scanner 기준을 유지하되
**공식 휴장·실제 KRX 공표/정확성 검증은 별도**다.

## 사용자 PC (PowerShell)

이전 임시 worktree `$work` 변수를 그대로 재사용한다.
코드는 원본 프로젝트 `$repo`가 아닌 검증용 worktree의 최신 SHA에서 실행한다.
원본 Market Store는 연결하지 않고 SQLite 원본을 read-only로 백업하여
시스템 TEMP 아래의 임시 파일만 Scanner에 공급한다.

```powershell
$repo = (git rev-parse --show-toplevel).Trim()
$db = Join-Path $repo "backend\runtime\market_history\market_history.db"
git fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
$sha = (git rev-parse origin/codex/p0-01-mvp-c1-c2-integration-20261022).Trim()
git -C $work switch --detach $sha

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "py" }
$tool = Join-Path $work "tools\data\p0_02_offline_scanner_replay.py"
if ($python -eq "py") {
    py -3 $tool --market-db $db --operational-repo $repo --as-of 2026-10-21 --market-scope ALL
} else {
    & $python $tool --market-db $db --operational-repo $repo --as-of 2026-10-21 --market-scope ALL
}
```

기존 원본 DB·strategy/Risk·JEV 운영 상태는 변경하지 않음.
이 명령은 실제 서버를 실행하거나 prospective capture를 만들지 않고
Python의 실제 Scanner 코어만 계산한다. 전체 220일 범위에 누락 항목이
있거나 모델 연계가 필요하면 계산하지 않고 HOLD JSON을 출력한다.
예상보다 오래 걸려도 별도 유료 외부 호출이나 자동 준비는 하지 않는다.

## 결과 판정

- `OFFLINE_SCANNER_COMPUTATION_VERIFIED`: 기준일, 선택 시장별 실제 저장
  행, 입력 fingerprint, 동결 Scanner 계산이 일치하고 외부 요청 0. **서비스
  계산 검증만 성공**; 전략 수익성/실시간 진입 적합성/추천 유효성은 아님.
- `HOLD_COMMON_AS_OF_MISMATCH`: 복제 시점에 지정 공통일이 없음.
- `HOLD_OFFLINE_LOOKBACK_INCOMPLETE`: 필요한 데이터가 없어 네트워크 차단.
- `HOLD_OFFLINE_SCANNER_EXECUTION_FAILED`: 진짜 Scanner 계산 오류.
- `HOLD_SCANNER_OUTPUT_MISMATCH`: 기준일/출처/partial/네트워크 수치 불일치.

출력은 종목 코드, 종목별 가격, 원본 KRX 행, API 키 없이
시장별 날짜·개수·SHA fingerprint·후보의 개수만 보여준다.

## 남은 필수 조건

실제 `/scanner/jobs`의 `job_id`·새 `capture`, 정확한 운영
정책 버전과 source snapshot, KRX 실공표와 휴장 검증, 실제 UI/DB 동등성은
별도의 유효한 제품 실행에서 확인해야 한다. 이 오프라인 재생을 P0-02
전체 완료나 실시간 매매 승인으로 승격하지 않는다.
