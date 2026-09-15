# Exit Policy Validation Runner v0.21.4-B.1.1

## 목적
v0.21.4-B.1에서 만든 Exit 정책 선택 로직을 실제 여러 종목 데이터에 적용하고, 정책 선택 근거를 사람이 검토할 수 있게 합니다.

## Local-only 연구 경로
Runner는 검증 시 KRX 네트워크를 채우지 않습니다.
1. `HistoricalMarketStore`의 로컬 종목/시장지수 커버리지 확인
2. 기본 90% 이상 커버리지 종목 자동 선택
3. KOSPI/KOSDAQ 후보를 번갈아 선택해 한 시장의 종목만 표본을 독점하지 않게 함
4. 시작일 전 최소 60 거래일 워밍업 데이터가 없는 종목 제외
5. 로컬 종목 + 지수 series로 Exit Policy Research 실행

데이터가 부족하면 `DATA_REQUIRED`로 끝내며 수백 회 KRX 요청을 자동 발생시키지 않습니다.

## Checkpoint
- 각 종목 audit 완료 직후 checkpoint 저장
- 같은 설정 + 같은 자동선정 표본이면 완료 audit 재사용
- `처음부터 다시 검증`은 해당 signature checkpoint 삭제 후 재실행
- 표본 종목 구성이 달라지면 signature가 달라져 기존 checkpoint가 섞이지 않음

## 정책 판정
v0.21.4-B.1의 보수적 판정을 그대로 사용합니다.
- `SELECTED`
- `BASELINE_BETTER`
- `UNRESOLVED`
- `INSUFFICIENT_SAMPLE`

Weighted score를 새로 만들지 않으며 실제 Production 정책은 변경하지 않습니다.

## Report
전략별로 다음을 확인합니다.
- 정책 상태와 선택 후보
- 거래 수
- 평균 Net Return
- Profit Factor
- median MDD
- Profit Giveback
- 평균 보유기간
- 특정 종목 편향
- 시장 상태별 성과
- Target2 이후 Max Hold 비교 결과

## Production Guardrail
`production_policy_changed = false`를 유지합니다. 연구 결과를 실제 Profit Protection으로 연결하는 작업은 v0.21.4-B.2에서 별도로 진행합니다.
