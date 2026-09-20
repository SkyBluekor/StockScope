# c.4f.5 — Audit Market Store Backfill Utility

## 목적
기숙사/새 PC의 `HistoricalMarketStore`가 비어 있어 c.4f 고정 10일 감사가 2/10만 유효한 문제를 해결한다.

## 범위
- Production 전략/Ranking/Risk/MA120/Sector RS 정책 수정 없음.
- 기존 `StockScannerService._history_plan()` / `_ensure_market_history()`와 `KrxProvider` cache/budget을 그대로 재사용.
- 기본 고정 10일 파일의 earliest date - 220 calendar days부터 latest date + 35 calendar days까지 KOSPI/KOSDAQ stock/index Market Store를 채운다.
- 이미 저장된 DATA/EMPTY 날짜는 재사용한다.
- 중단/실패 후 같은 명령으로 재개 가능하다.
- 실행 전에 전체 예상 KRX 신규 요청량을 budget gate로 검사한다.

## 실행
먼저 예상량 확인:

```powershell
python backend\tools\backfill_market_store_for_audit.py --dry-run
```

실제 채우기:

```powershell
python backend\tools\backfill_market_store_for_audit.py
```

완료 후 c.4f.4 고정 10일 감사 재실행:

```powershell
python backend\tools\run_scanner_strategy_integrity_audit.py `
  --mode inspect `
  --evaluation-dates-file backend\tools\audit_inputs\c4c_10days.txt `
  --sector-rs-audit-live
```

## 안전성
- KRX safe budget은 기존 프로젝트 설정을 따른다.
- raw cache/Market Store가 이미 있으면 네트워크 호출 없이 재사용한다.
- Production Scanner 버전/정책은 변경하지 않는다.
