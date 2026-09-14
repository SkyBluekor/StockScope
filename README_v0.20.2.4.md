# StockScope v0.20.2.4 — 조건 판정 정합성 Hotfix

## 목적
멀티 전략 결과에서 조건 PASS/FAIL, 충족/부족 개수, 현재 판단, 사용자 설명이 서로 다른 기준으로 보이지 않도록 하나의 조건 상태에서 파생되게 정리합니다.

## 핵심 변경
- StrategyEvaluation의 `reasons` / `unmet`을 조건 상태의 단일 원천으로 사용합니다.
- `passed + missing = total` 및 상세 조건 개수를 함께 검증하는 consistency 진단을 추가합니다.
- 조건이 부족하면서 Risk CAUTION이 함께 있으면 **주판정은 `진입 조건 부족`**, Risk는 **추가 주의**로 표시합니다.
- 전략 조건이 모두 충족된 뒤 Risk가 막는 경우에만 **`위험 때문에 진입 보류`**를 주판정으로 사용합니다.
- 프론트는 `missing`, `decision_reason`, `additional_warnings`, condition consistency를 그대로 렌더링하며 투자 조건을 재계산하지 않습니다.
- 조건 상세가 엔진 집계와 불일치하면 사용자에게 결과를 진입 판단에 사용하지 말라는 경고를 표시합니다.

## 확인 사항
스크린샷을 확대 확인한 결과 문제로 지목했던 시장 조건의 현재값은 `상승장`이 아니라 **`하락장`**이었습니다. 따라서 `시장 급락 아님` 조건이 실패한 것 자체는 기존 규칙상 정상입니다. 이번 Hotfix에서는 시장 규칙을 임의 변경하지 않았습니다.

실제 수정 대상은 `조건 부족 + Risk 경고`가 함께 있을 때 화면이 Risk만 주원인처럼 설명하던 부분과 조건 집계의 단일 원천화입니다.

## 변경 파일
- `backend/app/backtest/selector.py`
- `backend/app/backtest/multi_strategy.py`
- `backend/tests/test_multi_strategy_v020.py`
- `frontend/src/components/BacktestPanel.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/styles.css`

## 검증
- selector 단위/회귀 테스트: 19 passed (격리 테스트 환경)
- 변경 Python 파일 `py_compile` 통과
- TS/TSX TypeScript parser diagnostics 0
- CSS parse errors 0

전체 원본 프로젝트 의존성이 있는 환경에서 전체 pytest/Vite production build는 별도 확인이 필요합니다.
