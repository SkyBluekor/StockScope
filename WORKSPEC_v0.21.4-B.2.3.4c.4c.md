# WORKSPEC v0.21.4-B.2.3.4c.4c
## Strategy Integrity Comparison Normalization & MA120 Input Verification

## 1. 목적
`c.4b`까지 확인된 MA120 입력 누락과 Breakout RS 구조 문제를 Production에 바로 반영하지 않고, 비교 실험 자체의 신뢰도를 먼저 높인다.

이번 단계의 성공 기준은 “어떤 Variant가 더 좋은가”가 아니라 다음이다.

> 같은 입력·같은 평가일·같은 집계 기준에서 Variant 차이를 재현 가능하게 측정할 수 있는가.

Production의 Scanner/Strategy/Ranking/Risk/Entry/Exit 정책은 변경하지 않는다.

## 2. 기준 상태
- Production 후보 정책: Market160 / Quick18 / Strategy Top3 유지
- 현재 Breakout 구조: market RS 6 + sector RS 4 + sector RS 8
- 역사 설계 후보: market RS 10 + sector RS 8
- MA120 문제: 기존 기술지표 snapshot 경로는 60-row 중심이라 `StrategyInput.ma120`이 비어 있음
- 기존 10일 inspect는 80일 full의 부분집합이 아니므로 성과 축소판으로 해석하지 않는다.

## 3. Variant
- `BASELINE`
- `MA120_FIXED_AUDIT` — 기존 c.4 계열 counterfactual 보존
- `MA120_INPUT_ONLY` — 기존 60-row snapshot을 유지하고 as-of 과거 120개 종가에서 SMA120만 별도 공급
- `RS_KEEP_4`
- `RS_KEEP_8`
- `RS_RESTORE_10_8` — audit-only market10 + sector8 복원

## 4. 명시적 평가일
Runner는 아래 입력을 지원한다.
- `--dates` (legacy)
- `--evaluation-dates`
- `--evaluation-dates-file`

동시에 둘 이상을 지정하면 fail-fast한다. 중복 날짜도 거부한다.

기존 c.4b 10일 inspect의 평가일은 `backend/tools/audit_inputs/c4c_10days.txt`에 고정한다.

동일 파일로 inspect/full을 각각 실행해 구조 결과를 비교한다.

## 5. MA120_INPUT_ONLY
### 불변 조건
다음은 기존 snapshot 결과를 그대로 사용한다.
- MA20
- MA60
- ATR/RSI/Volume 등 기타 technical
- RS 입력
- 전략 weight/threshold
- Risk/Ranking

### 변경 조건
평가일(as-of) 이하 stock history만 사용해 최근 120개 종가의 SMA120을 계산하고 `StrategyInput.ma120`만 복제 객체에 주입한다.

120개 미만이면 `None`을 유지한다. 미래 행은 사용하지 않는다.

주입 후 기존 re-evaluator를 통해 전략을 재평가하고 Strategy selection → Quick18 → current candidate → ranking → Top5까지 전파한다.

기존 `MA120_FIXED_AUDIT`는 회귀 비교용으로 남긴다.

## 6. RS_RESTORE_10_8
Audit 내부에서만 다음 구조를 재구성한다.
- market weight: 6 → 10
- sector weight 4 제거
- sector weight 8 유지
- sector missing 시 market fallback 유지
- threshold `> 0` 의미 유지

단순 score 숫자만 바꾸지 않고 reasons/unmet, passed, total, eligible도 함께 갱신한다.

실제 historical scanner 입력에서 sector RS가 없을 수 있으므로 다음 두 축을 분리한다.
1. scanner-realistic replay
2. synthetic sector-aware matrix

Synthetic matrix는 다음 6 case를 검사한다.
- market+/sector+
- market+/sector-
- market-/sector+
- market-/sector-
- market+/sector missing
- market-/sector missing

실제 sector 관측이 0건이면 `INSUFFICIENT_SECTOR_RS_DATA`를 명시하고 synthetic 구조 검증과 실제 데이터 검증을 혼동하지 않는다.

## 7. Membership / Order 분리
Quick18과 Top5에 대해 각각 다음을 기록한다.
- membership changed
- membership replacements/add/remove
- order changed
- order-only changed

Backward compatibility를 위해 기존 `quick_pool_changed`, `top5_changed`는 membership 의미의 alias로 유지한다.

## 8. 메타데이터 / fingerprint
기존 Git/data metadata 외에 실제 감사/결정 경로 파일 SHA256을 기록한다.
최소 대상:
- strategy_integrity_audit.py
- run_scanner_strategy_integrity_audit.py
- early_pruning_audit.py
- candidate_priority.py
- scanner.py
- strategy/engine.py (존재 시)

## 9. Pair output
기존 pair CSV 외에 `scanner-strategy-integrity-ma120-pairs_<timestamp>.csv`를 생성한다.

Pair에는 가능한 범위에서 다음을 포함한다.
- removed/added symbol, strategy, rank
- candidate state
- priority tier
- entry gap
- strategy fit score
- conditions
- risk status
- 5/10/20D removed/added absolute return/R와 delta
- event status
- cause (`MA120_INPUT_SUPPLY`, legacy MA120, RS structure)

## 10. 출력/판정 원칙
결과 요약에서 membership과 order를 분리한다.
Sector available count/rate를 명시한다.
Synthetic matrix와 real historical availability를 별도로 표시한다.

이번 단계에서 Production 적용을 자동 승인하지 않는다.

## 11. Production 변경 금지
이번 overlay는 다음을 수정하지 않는다.
- `backend/app/strategy/engine.py`
- Scanner Production 정책
- Ranking
- Risk gate
- Entry/Invalidation/Target/Exit
- Quick18/Market160/Top3 정책
- Historical Evidence 정책

## 12. 실행 순서
```powershell
# 1) 회귀 테스트
pytest backend/tests/test_scanner_strategy_integrity_audit.py -q

# 2) 동일 10일 inspect
python backend/tools/run_scanner_strategy_integrity_audit.py `
  --mode inspect `
  --market-scope ALL `
  --evaluation-dates-file backend/tools/audit_inputs/c4c_10days.txt

# 3) 동일 10일 full
python backend/tools/run_scanner_strategy_integrity_audit.py `
  --mode full `
  --market-scope ALL `
  --evaluation-dates-file backend/tools/audit_inputs/c4c_10days.txt `
  --min-required-dates 10

# 4) 결과 확인 후 80일 full
python backend/tools/run_scanner_strategy_integrity_audit.py `
  --mode full `
  --market-scope ALL `
  --sample-size 80 `
  --min-date-gap 3
```

## 13. 완료 조건
- explicit dates/file 지원
- code fingerprint 기록
- MA120_INPUT_ONLY 존재
- 기존 60-row snapshot 불변
- Quick18/Top5 membership-order 분리
- RS_RESTORE_10_8 전파
- sector-aware 6-case matrix
- dedicated MA120 pair CSV
- Production 파일 미수정
- 감사/기존 pruning/determinism 회귀 테스트 통과

## 14. 다음 단계
c.4c 결과 확인 후에만 다음을 별도 작업으로 다룬다.
1. MA120 Production 공급 방식 결정
2. RS 10+8 Production 반영 여부 결정
3. MA120 + RESTORE 조합 검증
4. Quick36 재검증
