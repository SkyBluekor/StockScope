# StockScope v0.20 Multi-Strategy Backtest & Strategy Selector Overlay

프로젝트 루트에 그대로 덮어쓰는 overlay입니다.

## 핵심 변경

- 사용자가 눌림목/돌파 등을 먼저 고르지 않음
- 종목 1개에 대해 기존 10개 전략을 모두 과거 검증
- KRX Historical Store/일별 snapshot을 전략끼리 공유
- 각 전략을 같은 다음 거래일 시가, 비용, 최대 보유기간, RiskEngine 프레임으로 비교
- 과거 표본/거래당 평균/Profit Factor/MDD + 검증 종료시점 현재 조건을 종합
- 수익률 1등이 아니라 현재 가장 우선해서 볼 전략을 추천
- 조건이 부족하거나 과거 근거가 약하면 WAIT/NO_TRADE 가능
- 결과 UI는 `현재 추천 → 왜 → 지금 할 일 → 조건 변경 → 상세 근거` 순서

## 지원 전략

추세 추종, 눌림목, 돌파, 지지 반등, 과매도 반등, 박스권 매매, 모멘텀 지속, 변동성 수축, 20일선 반등, 추세 회복

## 유지되는 기존 기능

기존 `/api/backtest/pullback` 및 v0.19.x 관련 API는 삭제하지 않습니다. v0.20 UI의 기본 실행 경로만 `/api/backtest/multi-strategy/jobs`로 변경합니다.

## 적용 후 확인

1. `./run-dev.ps1`
2. 백테스트 페이지 진입
3. 종목과 기간 선택
4. `10개 전략 자동 비교 시작`
5. 결과 첫 화면에서 추천 전략, 행동, 변경 조건 확인
6. `10개 전략 전체 비교` 상세에서 전략 간 근거 확인

> Strategy Score와 selector 내부 비교값은 미래 상승 확률이 아닙니다.
