# UX.1.2.1 — BacktestPanel Visual Density Polish

범위는 `종목 과거 성과` 화면 하나입니다.

## 변경
- 상단 제목 영역을 카드가 아닌 일반 페이지 헤더처럼 보이도록 정리
- `설정 / 결과`를 얇은 underline 탭 형태로 정리
- `검증 종목` 내부 중첩 카드 표현 제거
- 최대 보유기간 카드의 시각 강도 축소
- `비교할 전략 10개`, `공정 비교 기준`을 보조 정보처럼 평평하게 표시
- CTA 옆 `10가지 전략을 같은 조건으로 비교합니다.` 중복 문구 제거
- `고급 검증 · Exit 정책 연구`의 시각 우선순위 축소
- 작은 화면에서 CTA는 전체 폭 사용

## 변경하지 않음
- Backtest/전략/Risk/Exit 계산
- 종목 검색 동작
- 날짜/자본/비용/보유기간 상태
- Backend/API/Scanner/Tracking/DB
- 결과 화면 판단 로직

## 적용
먼저 dry-run:

```powershell
python .\apply_ux1_2_1_backtest_visual_density.py --dry-run
```

`DRY-RUN PATCH: PASS` 확인 후:

```powershell
python .\apply_ux1_2_1_backtest_visual_density.py
```

적용 스크립트는 `BacktestPanel.tsx`와 `styles.css`만 백업하며, frontend production build 실패 시 두 파일만 원복합니다.

## 시각 확인
빌드 성공 후 브라우저에서 `Ctrl + Shift + R`로 hard refresh한 뒤 `종목 과거 성과` 화면만 확인합니다. `details`는 `open` 속성을 사용하지 않으므로 fresh mount에서는 접힌 상태가 기준입니다.
