# StockScope v0.21.4-B.2.4a — Frontend TypeScript Build Hotfix

## 목적
B.2.4 적용 후 `npm --prefix frontend run build`에서 확인된 두 TypeScript 오류만 수정한다. Scanner 동작, 전략, ranking, risk, progress contract는 변경하지 않는다.

## 수정
1. `freshness_failure`는 `BacktestJob.progress.details`의 정적 타입이 primitive union으로 좁게 선언되어 있으므로 직접 `ScannerFreshnessResponse`로 단언하지 않는다. 먼저 `unknown`으로 승격한 뒤 non-null object인지 검사하고 단언한다.
2. `progressDetails.current_item`은 `unknown`이므로 JSX에서 직접 truthiness 조건으로 사용하지 않는다. `!= null`의 boolean 조건 + ternary로 렌더링한다.

## 변경 파일
- `frontend/src/components/ScannerPanel.tsx`

## 변경 금지
- Backend
- Scanner VERSION 0.21.3.5
- B.2.4 progress stage contract
- Strategy / Ranking / Risk / Entry / Stop / Target / Exit
- Theme tokens

## 검증
- 두 오류 패턴을 재현하는 strict TypeScript 최소 typecheck PASS.
- 실제 full frontend build는 사용자 로컬 repo에서 수행한다.
