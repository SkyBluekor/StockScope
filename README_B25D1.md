# B.2.5-D.1 — NO_TRADE audit source fallback hotfix

문제: `run_scanner_no_trade_audit.py`가 사용자 PC에 과거 `scanner-strategy-audit_*.json`이 이미 존재한다고 가정해 실행이 중단됨.

수정:
- 로컬 strategy audit가 있으면 최신 파일을 우선 사용합니다.
- 로컬 파일이 없으면 B.2.5-D 검증에 사용했던 80일 audit에서 decision-gate 검사 필드만 추출한 경량 snapshot으로 자동 fallback합니다.
- bundled snapshot은 Production 데이터가 아니라 B.2.5-D 회귀/일관성 검사용 baseline evidence입니다.
- Ranking/Strategy/Risk/Target Production 코드는 변경하지 않습니다.
