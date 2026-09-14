# StockScope v0.20.2 overlay

적용 전 기준: v0.20.1 Beginner Strategy & Action UX 적용 상태

## 포함 변경

- `frontend/src/App.tsx`
  - 상단 우측 다크/라이트 전환
  - OS 테마 초기 반영
  - 사용자 선택 localStorage 저장
- `frontend/src/styles.css`
  - 공통 테마 변수
  - 다크모드
  - 전체 가독성/폰트 확대
  - 줄바꿈 및 반응형 깨짐 방지
  - 조건 현재값/필요값 카드 스타일
- `frontend/src/components/BacktestPanel.tsx`
  - 현재 조건 X/Y 표시
  - 현재값 / 필요값 / 충족 여부 표시
  - 추상적인 조건 문장보다 실제 조건 근거 우선
- `frontend/src/services/api.ts`
  - 조건 근거 타입 확장
- `backend/app/backtest/selector.py`
  - 전략 조건을 초보자용 현재값/필요값으로 변환
- `backend/app/backtest/multi_strategy.py`
  - 동일 snapshot의 StrategyInput/technical 값을 조건 설명에 연결
- `backend/tests/test_multi_strategy_v020.py`
  - 구체적 거래량/가격 조건 표시 테스트 추가

## 검증

- 멀티전략 관련 테스트 9개 통과
- 변경 Python 파일 `py_compile` 통과
- App/BacktestPanel/api TypeScript `transpileModule` 구문 검사 통과
- CSS `tinycss2` 파싱 오류 0건

전체 프로젝트 의존성이 없는 overlay 재구성 환경이므로 실제 Vite production build 및 브라우저 픽셀 단위 스크린샷 검증은 수행하지 않았다.
