# StockScope v0.21.1 — Concrete Entry & Risk Guide

## 변경 내용
- Scanner 후보에 `구체적인 타이밍·위험 기준` 카드 추가
- 10전략 비교 결과에도 동일 가이드 추가
- 현재가 / 가격 조건 / 필요한 변화율 / 거래량 현재·필요 배수 표시
- Risk Engine의 전략 무효가격을 손절 참고가격으로 표시
- Target1 / Target2 / Risk:Reward 표시
- 조건이 아직 부족하면 손절·목표를 `현재 종가 기준 참고값`으로 명시하고 다음 분석에서 재계산
- 과거 검증 여부와 현재 진입조건을 분리
  - 현재 조건 + Risk 통과 시 과거 검증 전이어도 `현재 조건상 진입 후보`
  - 과거 표본 부족/약함은 별도 경고로 표시
- Strategy Engine에 없는 임의 상승률/거래량/손절 기준은 추가하지 않음

## 검증
- `test_entry_risk_guide_v0211.py`: 4개 통과
- selector 격리 회귀 테스트: 19개 통과
- Scanner fast-candidate 격리 스모크: READY/WATCH 분리 확인
- 변경 Python 파일 `py_compile` 통과
- 변경 TS/TSX 4개 TypeScript `transpileModule` 구문 진단 0건
- CSS brace 구조 확인

전체 StockScope 원본 환경의 전체 pytest / Vite production build는 overlay 작업 환경에서는 실행하지 않았다.
