# v0.21.2 Historical Evidence 설계 메모

## 처리 순서

```text
전체 시장
→ 기존 Fast Scanner
→ 기존 현재 전략/Risk 기반 후보 분석 및 순위 확정
→ Top 후보 고정
→ 같은 전략만 최근 3년 Backtest Engine으로 재검증
→ Historical Evidence를 후보 카드에 부착
```

Historical Evidence 결과는 v0.21.2에서 후보 순위를 다시 계산하지 않습니다.

## 재사용하는 기존 정책

- EOD signal
- 다음 거래일 시가 진입
- 같은 봉 stop/target 동시 도달 시 stop 우선
- Max hold 20 trading days
- Target1 full exit
- daily-close mark-to-market MDD
- 기존 Strategy / Risk / Backtest 계산식 변경 없음

## Evidence Builder

`backend/app/backtest/historical_evidence.py`

입력:

- 현재 Scanner가 선택한 strategy
- 종목 3년 + warm-up Market Store rows
- 동일 기간 시장 index rows
- 기존 `MultiStrategyBacktestEngine`

출력:

- 검증 상태
- sample count / wins / losses
- win rate (과거 통계로만 표시)
- average/median net return
- expectancy
- profit factor
- MDD
- average win/loss
- exit counts
- market regime summary
- warnings / guardrail

## 표본 정책

평가 문구는 거래 10건 이상부터 허용합니다.

```text
0             NO_CASES
1 ~ 9         INSUFFICIENT
10+           GOOD / FAIR / WEAK 평가 가능
```

`GOOD / FAIR / WEAK`는 미래 상승 확률이 아니라 과거 동일 전략 결과의 설명용 상태입니다.

## 캐시

Evidence cache key:

```text
market + stock_code + strategy + data_end + policy_version
```

검증 완료된 evidence만 저장합니다. `DATA_UNAVAILABLE`은 저장하지 않습니다.

이유: 같은 거래일에도 Market Store가 나중에 보충될 수 있으므로 데이터 부족 상태를 영구적인 결과처럼 고정하면 안 됩니다.

## 네트워크 정책

이 기능의 Historical Evidence 단계에서는 KRX Provider를 호출하지 않습니다. Market Store에 이미 저장된 데이터만 사용합니다.

3년 데이터가 부족하면 `DATA_UNAVAILABLE`로 끝내며 Scanner 실행 중 대량 historical bootstrap을 자동 수행하지 않습니다.
