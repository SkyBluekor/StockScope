# StockScope v0.21.2 — Scanner Historical Evidence

v0.21.1의 Concrete Entry & Risk Guide 다음 단계입니다.

## 목적

Scanner의 기존 후보 순위는 그대로 유지하면서, 최종 Top 후보에 **현재 선택된 동일 전략의 최근 3년 과거 근거**를 별도로 붙입니다.

- 순위 확정: 현재 전략 조건 + 기존 Risk/Scanner 로직
- 순위 확정 뒤: Top 후보만 3년 historical evidence 계산
- 3년 evidence는 v0.21.2에서 후보 순위를 다시 정렬하지 않음
- 과거 승률/수익률을 미래 상승 확률로 표현하지 않음
- Market Store의 저장 데이터가 부족하면 Scanner가 수백 회 KRX 다운로드를 자동 시작하지 않음

## 표본 정책

- 0회: `과거 사례 없음`
- 1~9회: `표본 부족`
- 10회 이상부터 `양호 / 보통 / 약함` 평가 가능

표본이 10회 미만이면 수익률이나 승률이 좋아도 좋은 근거로 승격하지 않습니다.

## 화면에 추가되는 정보

기본 카드:

- 같은 전략의 유사 거래 수
- 수익 거래 수
- 평균 순수익
- 최대 낙폭(MDD)
- 과거 근거 상태

펼쳐보기:

- Profit Factor
- Stop / Target1 / Time Exit 횟수
- 시장 국면별 거래 수와 평균 순수익
- 표본/시장국면 경고
- `과거 결과 != 미래 상승 확률` 가드레일

## 데이터 부족 정책

3년 + 기술지표 warm-up 데이터가 Market Store에 충분할 때만 검증합니다.

데이터가 부족하면:

- `3년 검증 데이터 부족` 표시
- 현재 전략 조건 실패로 바꾸지 않음
- 자동 대량 KRX fetch 금지
- 미완료 결과는 evidence cache에 저장하지 않음
- Top 후보 중 3년 데이터가 부족하면 그날의 전체 Scanner 결과도 고정 cache하지 않아, Market Store가 같은 날 채워진 뒤 재검증 가능

## 수정/추가 파일

- `backend/app/backtest/historical_evidence.py` (new)
- `backend/app/backtest/multi_strategy.py`
- `backend/app/backtest/scanner.py`
- `backend/tests/test_historical_evidence_v0212.py` (new)
- `backend/tests/test_scanner_v021.py`
- `frontend/src/components/ScannerPanel.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/styles.css`
- `docs/historical-evidence-v0.21.2.md` (new)

## 적용

이 overlay를 StockScope 프로젝트 루트에 덮어씌웁니다.

```powershell
cd C:\TAEWOO\CapstonDesign\StockScope
.\run-dev.ps1
```

Scanner를 실행한 뒤 Top 후보 카드에서 `3년 과거 근거` 영역을 확인합니다.

## 검증 기록

이 overlay 제작 환경에서 실제 수행한 검증:

- 관련 Python compile: 통과
- 관련 pytest: **63 collected / 63 passed**
  - v0.21.2 historical evidence
  - Scanner
  - v0.20 multi strategy
  - v0.21.1 entry/risk guide regression
- 변경 TS/TSX 파일 TypeScript syntax diagnostics: 오류 0
- CSS brace balance: 통과
- ZIP integrity: 생성 후 별도 확인

전체 저장소의 full pytest / Vite production build는 overlay 조합 환경에서는 실행하지 않았습니다.
