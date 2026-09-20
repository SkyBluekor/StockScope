# B.2.5-D Implementation

## 추가 파일
- `backend/app/backtest/scanner_quality/no_trade_audit.py`
- `backend/tools/run_scanner_no_trade_audit.py`
- `backend/tests/test_scanner_no_trade_audit_v0214b25d.py`

## Production 변경
없음.

Scanner Strategy / Risk / Ranking / Entry / Stop / Target 계산식은 수정하지 않는다.

## 실행
```powershell
python backend\tools\run_scanner_no_trade_audit.py
```

기존 audit 파일 자동 검색이 실패하면:
```powershell
python backend\tools\run_scanner_no_trade_audit.py --input <scanner-strategy-audit.json>
```

결과는 `backend/runtime/quality_audit/no_trade/` 아래 JSON/Markdown으로 저장된다.
