# StockScope UX.1.2 — BacktestPanel Action-First (single-screen patch)

이번 패치는 UX.1.2 전체를 한 번에 건드리지 않습니다. 사용자가 문제를 지적한 **종목 과거 성과 / BacktestPanel 한 화면만 먼저 수정**합니다.

## 실제 현재 소스 기준 변경

- `multi-strategy-flow`의 `1 · 종목 선택 → 2 · 현재 가능 전략 확인 → 3 · 과거 성과 비교` 삭제
- 상단 `STRATEGY SELECTOR`/장문 설명 제거
- 제목을 `종목 과거 성과`로 단순화
- `1 · 설정 / 2 · 결과`를 실제 뷰 전환인 `설정 / 결과`로 축약
- 상단 `multi-strategy-purpose` 설명 + 10개 전략 벽 제거
- 기존 `strategyGuides.map(...)`은 삭제하지 않고 설정 아래 `비교할 전략 10개 보기` 접힘 영역으로 이동
- `공정하게 비교하기 위해 어떤 조건을 같게 하나요?` → `공정 비교 기준`
- 실행 버튼 → `과거 성과 비교`
- `연구용 · Exit 정책 검증` → `고급 검증 · Exit 정책 연구`

## 변경하지 않는 것

- `runBacktest()` / `createMultiStrategyBacktestJob()`
- Exit validation 실행 로직
- 종목 검색/선택
- 시작일/종료일/자본/비용률/보유기간 상태
- 결과 화면 계산/렌더링
- Backend/API/DB/Scanner/Tracking

## 적용

ZIP을 StockScope 프로젝트 루트에 풀고:

```powershell
python .\apply_ux1_2_backtest_action_first.py --dry-run
python .\apply_ux1_2_backtest_action_first.py
```

첫 명령은 파일을 전혀 수정하지 않고 현재 `BacktestPanel.tsx`가 업로드해 확인한 구조와 정확히 맞는지 검증합니다.

두 번째 명령은 수정 후 `npm --prefix frontend run build`를 실행합니다. Build 실패 시 `BacktestPanel.tsx`를 자동 원복합니다.

## 완료 기준

이 패치는 Build가 성공해도 바로 UX.1.2 전체 CLOSED 처리하지 않습니다. 브라우저에서 **종목 과거 성과 화면 스크린샷을 다시 확인한 뒤** 이 화면을 먼저 닫고 다음 화면으로 이동합니다.
