# IMPLEMENTATION v0.21.4-B.2.3.4c.4f.4

- `strategy_integrity_audit.py`
  - audit Sector RS를 `StrategyInput` 복사본에만 주입
  - 전체 전략 재평가 후 `RS_AUDIT_CURRENT_6_4_8` 생성
  - 동일 Sector-aware baseline에서 KEEP_4 / KEEP_8 / RESTORE_10_8 생성
  - Production fallback 대비 입력 효과와 Sector-aware baseline 대비 가중치 효과를 분리 집계
  - market/sector sign divergence, Breakout score 변화, 전략 변화 측정
  - `sector_comparisons`와 `sector_rs_counterfactual` validation 추가
  - CSV/Markdown에 c.4f.4 필드 추가
- `run_scanner_strategy_integrity_audit.py`
  - 진행 로그와 완료 요약에 Sector-aware counterfactual 지표 추가
- 신규 테스트
  - `test_sector_rs_counterfactual_v0214b234c4f4.py`

Production 전략 정의, 가중치, fallback, Ranking, Risk는 변경하지 않는다.
