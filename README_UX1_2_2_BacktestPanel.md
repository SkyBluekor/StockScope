# UX.1.2.2 — BacktestPanel Final Interaction Polish

Narrow final patch for **종목 과거 성과** only.

Changes:
- removes the legacy filled active-state from `설정 / 결과`; active state is text + underline,
- makes the three optional disclosure sections React-controlled and initially closed:
  - 비교할 전략 10개 보기
  - 공정 비교 기준
  - 고급 검증 · Exit 정책 연구
- preserves backtest execution, Exit validation, strategy rendering, APIs and calculations.

Run from StockScope project root:

```powershell
python .\apply_ux1_2_2_backtest_final_interaction.py --dry-run
python .\apply_ux1_2_2_backtest_final_interaction.py
```

The real apply performs the frontend production build and rolls back only `BacktestPanel.tsx` / `styles.css` if build or acceptance fails.
