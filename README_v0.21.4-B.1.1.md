# StockScope v0.21.4-B.1.1 — Exit Policy Validation Runner & Report

연구용 Exit 정책 선택 엔진(v0.21.4-B.1)을 실제 로컬 Market Store 표본에 반복 실행하고 사람이 검토할 수 있도록 만든 검증 Runner/Report 버전입니다.

## 핵심
- 일반 Scanner/Action Plan의 실제 Exit 정책은 변경하지 않습니다.
- 검증은 로컬 `HistoricalMarketStore`만 사용하며 연구 Runner 자체에서 KRX 네트워크를 추가 호출하지 않습니다.
- KOSPI/KOSDAQ에서 로컬 데이터 커버리지가 충분한 종목을 자동 선택합니다.
- 동일한 연구 조건 + 동일한 검증 표본은 종목별 audit checkpoint를 재사용합니다.
- 중단 후 같은 조건으로 다시 실행하면 완료한 종목은 건너뜁니다.
- 최종 결과는 `SELECTED / BASELINE_BETTER / UNRESOLVED / INSUFFICIENT_SAMPLE`로 표시합니다.
- 실제 정책 적용은 계속 `v0.21.4-B.2`로 유예됩니다.

## UI
Backtest 설정 화면의 `연구용 · Exit 정책 검증`에서 실행할 수 있습니다.
- 진행률 / 현재 종목 / checkpoint 재사용 / 네트워크 요청 수
- 상태별 전략 개수
- 전략별 선택정책, 평균 Net, PF, MDD, Giveback, 보유기간
- 정책별 전체 수치 비교
- 시장 국면별 결과
- Target2 이후 Max Hold 비교 설명
- 검증 사용 종목 / 제외 종목 확인

## 저장
- Checkpoint: `backend/runtime/research/exit_policy_validation_checkpoint_<signature>.json`
- 최신 Report: `backend/runtime/research/exit_policy_validation_report.json`

Checkpoint signature는 연구 설정뿐 아니라 자동 선택된 검증 종목 목록도 포함합니다. Market Store의 표본 구성이 바뀌면 오래된 checkpoint를 잘못 재사용하지 않습니다.

## 검증
- 신규 Runner 집중 테스트 5개 통과
- Exit Selection / Research / Entry Risk / Candidate Ranking / Historical Evidence / Fast Path / Scanner 포함 관련 누적 회귀 88개 통과
- Python compile 통과
- BacktestPanel.tsx / api.ts TypeScript syntax 검사 통과
- PostCSS parse 통과
- 전체 프로젝트 full pytest 및 Vite production build는 이 overlay 조립 환경에서 실행했다고 주장하지 않습니다.
