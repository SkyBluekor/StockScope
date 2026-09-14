# StockScope v0.21 Scanner overlay

## 적용 목적
- 상단 `종목 찾기` 기능 활성화
- KOSPI + KOSDAQ 일반 주식 자동 후보 검색
- 기본 후보 5개
- 우선주 / SPAC / ETF / ETN / 거래정지 / 데이터 부족 기본 제외
- 기존 10전략 Selector + Risk Engine + 1년 과거 근거 재사용
- v0.20.3 Historical Market Store / API Budget 재사용

## 주요 파일
- `backend/app/backtest/scanner.py` 신규
- `backend/app/backtest/market_store.py` 시장 단위 조회 helper 추가
- `backend/app/api/backtest.py` scanner job API 추가
- `backend/tests/test_scanner_v021.py` 추가
- `frontend/src/components/ScannerPanel.tsx` 신규
- `frontend/src/services/api.ts` scanner 타입/API 추가
- `frontend/src/App.tsx` `/scanner` 페이지와 상단 네비게이션 연결
- `frontend/src/styles.css` Scanner 반응형 Dark/Light UI 추가

## 주의
이 기능은 매수 추천 확률/자동주문 기능이 아니다. 현재 전략 준비도, 위험, 시장환경, 과거 근거를 바탕으로 `먼저 확인할 후보`를 줄여주는 EOD Scanner이다.
