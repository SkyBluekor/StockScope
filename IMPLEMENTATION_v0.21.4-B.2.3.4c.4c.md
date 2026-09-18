# IMPLEMENTATION v0.21.4-B.2.3.4c.4c
## Strategy Integrity Comparison Normalization & MA120 Input Verification

## 구현 완료

### 감사 버전
- `AUDIT_VERSION = v0.21.4-B.2.3.4c.4c`

### 수정 파일
- `backend/app/backtest/scanner_quality/strategy_integrity_audit.py`
- `backend/tools/run_scanner_strategy_integrity_audit.py`
- `backend/tests/test_scanner_strategy_integrity_audit.py`

### 추가 파일
- `backend/tools/audit_inputs/c4c_10days.txt`
- `WORKSPEC_v0.21.4-B.2.3.4c.4c.md`
- `IMPLEMENTATION_v0.21.4-B.2.3.4c.4c.md`

Production 파일은 수정하지 않았다.

## 주요 구현

### 1. `MA120_INPUT_ONLY`
기존 snapshot/technical 계산 결과는 그대로 두고, 평가일까지의 stock history에서 최근 120개 close만 사용해 SMA120을 계산한다.

`StrategyInput.ma120`만 복제해 re-evaluation하고 기존 scanner 파이프라인으로 전파한다.

기존 `MA120_FIXED_AUDIT`는 비교용으로 유지한다.

### 2. `RS_RESTORE_10_8`
`market6 + sector4 + sector8`에서 audit-only `market10 + sector8`을 재구성한다.

sector4 조건 제거와 market weight +4를 함께 적용하며 reasons/unmet, passed, total, score, eligible을 일관되게 갱신한다.

sector missing fallback에서는 baseline과 restore의 RS score가 같을 수 있으나 condition count가 감소하는 상황을 별도 집계한다.

### 3. Sector-aware matrix
실제 historical sector RS 부재와 구조적 weight split 검증을 분리하기 위해 6개 결정론적 sign/fallback case를 추가했다.

- 동일 부호 positive: score delta 0
- market+/sector-: restore가 +4
- market-/sector+: restore가 -4
- 둘 다 negative: 0
- sector missing: market fallback 때문에 score delta 0

실제 sector data availability는 별도 count/rate로 출력한다.

### 4. Membership / Order 분리
Quick18 및 Top5 비교를 set membership과 ordered sequence로 분리했다.

추가 필드 예:
- `quick_membership_changed`
- `quick_membership_replacements`
- `quick_order_changed`
- `quick_order_only_changed`
- Top5 대응 필드

기존 c.4a/c.4b consumer 호환을 위해 `quick_pool_changed`, `top5_changed`는 membership alias로 유지한다.

### 5. Explicit evaluation dates
Runner에 다음을 추가했다.
- `--evaluation-dates`
- `--evaluation-dates-file`

기존 `--dates`는 유지한다. 둘 이상 동시 지정 및 duplicate date는 fail-fast한다.

`c4c_10days.txt`는 c.4b `154016` inspect에 실제 기록된 10개 평가일을 사용한다.

### 6. Audit code fingerprint
감사/결정 경로의 source SHA256을 결과 payload에 기록한다.

### 7. Pair output 확장
기존 pair CSV를 확장하고 MA120_INPUT_ONLY 전용 pair CSV를 추가했다.

- rank/state/tier/entry gap/strategy fit/conditions/risk
- removed/added absolute return/R
- delta와 event
- change cause

## 검증 결과
Overlay sandbox에서 이전 단계 의존 파일을 합쳐 실행했다.

```text
backend/tests/test_scanner_strategy_integrity_audit.py
backend/tests/test_scanner_pruning_audit.py
backend/tests/test_scanner_determinism_v0214b234b.py

28 passed
```

Python compile도 통과했다.

## 중요한 한계
이 작업 환경에는 사용자의 현재 `D:\Projects\StockScope` 작업 트리와 `market_history.db`가 직접 마운트되어 있지 않다.

따라서 다음은 이 환경에서 실행하지 않았다.
- 실제 동일 10일 inspect/full c.4c replay
- 실제 80일 full c.4c replay
- 실제 19개 MA120_INPUT_ONLY 교체 pair 분석

또한 보관함에는 최신 로컬 c.4b `strategy_integrity_audit.py` 자체가 없고 `c.4a` overlay, c.4b WORKSPEC, c.4b 실행 결과가 남아 있었다. 따라서 이 overlay는 **c.4a 코드 기반에서 c.4b `RS_RESTORE_10_8` 동작을 재구성한 뒤 c.4c를 추가한 버전**이다. 현재 로컬 c.4b와 byte-for-byte 동일한 기반이라고 주장하지 않는다.

Production 파일을 포함하지 않으므로 운영 전략 가중치나 Scanner 정책을 자동 변경하지 않는다.

## 실제 PC 권장 실행
```powershell
cd D:\Projects\StockScope

pytest backend\tests\test_scanner_strategy_integrity_audit.py -q

python backend\tools\run_scanner_strategy_integrity_audit.py `
  --mode inspect `
  --market-scope ALL `
  --evaluation-dates-file backend\tools\audit_inputs\c4c_10days.txt

python backend\tools\run_scanner_strategy_integrity_audit.py `
  --mode full `
  --market-scope ALL `
  --evaluation-dates-file backend\tools\audit_inputs\c4c_10days.txt `
  --min-required-dates 10
```

두 실행에서 동일 평가일의 strategy/Quick18/Top5 membership 구조가 일치하는지 먼저 확인한 뒤 80일 full을 실행한다.
