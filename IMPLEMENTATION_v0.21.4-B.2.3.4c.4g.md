# IMPLEMENTATION v0.21.4-B.2.3.4c.4g

## 구현 내용
- `apply_c4g_breakout_rs_production_fix.py`
  - AST로 `_breakout()`의 Market/Sector RS tuple을 검사.
  - 정확히 legacy market=[6], sector=[4,8]일 때만 patch.
  - Market 6→10, Sector 4 제거, Sector 8 유지.
  - 이미 10+8이면 idempotent 성공.
  - 알 수 없는 구조는 fail-closed.
- Scanner version: `0.21.3.5`.
- Frontend Scanner decision/session version: `0.21.3.5`.
- strategy-integrity audit version: `v0.21.4-B.2.3.4c.4g`.
- audit source gate는 real Production에 대해 market=[10], sector=[8], sector condition count=1을 강제.
- 결과에 `c4g_production_rs_acceptance` 추가.
- `STATIC_CURRENT` historical Sector RS는 계속 audit-only.

## 로컬 검증
작성 환경에서 다음 focused tests 통과:
- `test_breakout_rs_production_v0214b234c4g.py`
- `test_sector_rs_counterfactual_v0214b234c4f4.py` (c.4g 호환 갱신)
- `test_sector_rs_audit_coverage_v0214b234c4f3.py` (c.4g 호환 갱신)

결과: 9 passed.

실제 StockScope 전체 회귀/10D/80D는 사용자 로컬 Market Store와 Production source에 overlay 적용 후 실행한다.
