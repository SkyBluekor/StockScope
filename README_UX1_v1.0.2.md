# UX.1 v1.0.2 — regression compatibility hotfix

Cause: existing TRACK regression checks the stable phrase `이 화면에서 Scanner 종목 찾기를 직접 실행`. UX.1 v1.0.1 replaced that sentence, so the regression failed and the apply script rolled back.

Fix: preserve that frozen TRACK phrase inside the new `종목 성과 추적` explanation while retaining all UX.1 guidance.

No Backend, DB, Scanner algorithm, TRACK lifecycle, performance calculation, or source-merge behavior is changed.

Apply from the StockScope root:

```powershell
python .\apply_ux1_feature_orientation.py
```

The failed v1.0.1 attempt rolled back its frontend changes, so no cleanup is required.
