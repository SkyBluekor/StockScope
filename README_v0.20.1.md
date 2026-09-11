# StockScope v0.20.1 Beginner Strategy & Action UX Overlay

프로젝트 루트에 그대로 덮어쓰는 v0.20 기반 overlay입니다.

## 이번 버전의 목표

v0.20의 10개 전략 자동 비교 로직은 유지하면서, 초보자가 결과를 보고 바로 다음을 이해할 수 있게 바꿉니다.

1. 추천된 방법이 무엇인지
2. 전문 전략명이 무슨 뜻인지
3. 지금 진입해도 되는지
4. 현재 사용자가 실제로 해야 할 일이 있는지
5. StockScope가 다음 분석에서 무엇을 자동으로 다시 확인하는지
6. 어떤 조건이 바뀌어야 판단이 달라지는지

## 핵심 UX 변경

- 10개 전략 모두 `쉬운 이름 + 전문 전략명 + 한 줄 설명 + 언제 쓰는지` 제공
- `대기`를 사용자 행동으로 쓰지 않고 상태와 행동을 분리
- WAIT / NO_TRADE / NEEDS_VALIDATION은 `현재 할 일 없음`을 명시
- 거래량, RSI, ATR, 이동평균 같은 조건은 초보자 표현을 먼저 노출
- 사용자가 지표를 직접 계산하라고 요구하지 않음
- 조건 하나 충족 = 즉시 매수로 처리하지 않음
- 다음 분석 실행 때 최신 확정 데이터로 전략 조건과 위험을 자동 재평가
- 상시 백그라운드 감시/알림은 이번 버전에 포함하지 않음

## A안 동작

현재 버전은 상시 감시가 아닙니다.

`최신 확정 데이터로 다시 분석`을 실행하거나 이후 앱에서 다시 분석하면 종료일을 현재 날짜로 갱신하고, KRX에서 사용 가능한 최신 확정 거래일까지 다시 계산합니다.

사용자는 거래량 배수, RSI, ATR, 이동평균을 직접 계산할 필요가 없습니다.

## 변경 파일

- `backend/app/backtest/selector.py`
- `backend/app/backtest/multi_strategy.py`
- `frontend/src/components/BacktestPanel.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/styles.css`
- `backend/tests/test_multi_strategy_v020.py`
- `docs/beginner-strategy-action-ux-v0.20.1.md`

## 유지되는 원칙

- Strategy Score / 내부 selector 점수는 미래 상승 확률이 아님
- 실제 주문은 수행하지 않음
- 과거 성과만으로 전략을 추천하지 않음
- 표본 부족은 별도 상태로 취급
- 10개 전략은 같은 과거 데이터와 공통 Risk/Exit 프레임으로 비교
