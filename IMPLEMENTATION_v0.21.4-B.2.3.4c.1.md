# IMPLEMENTATION v0.21.4-B.2.3.4c.1
## Early Candidate Pruning Audit

## 구현 목적
Production Scanner의 160개/18개 기본값은 변경하지 않고, 후보 선제 축소가 좋은 종목을 미리 버리는지 동일 데이터에서 비교할 수 있는 오프라인 감사 러너를 추가했다.

## 추가 파일
- `backend/app/backtest/scanner_quality/__init__.py`
- `backend/app/backtest/scanner_quality/models.py`
- `backend/app/backtest/scanner_quality/early_pruning_audit.py`
- `backend/tools/run_scanner_pruning_audit.py`
- `backend/tests/test_scanner_pruning_audit.py`

## Production 변경
없음.
- `scanner.py` 수정 없음
- Ranking 수정 없음
- Strategy 수정 없음
- Risk / Entry / Stop / Target 수정 없음
- KRX/DART 호출 추가 없음

감사 러너는 기존 `StockScannerService`의 다음 production 내부 계산을 그대로 재사용한다.
- `_special_reason()`
- `_quick_current_candidate()`
- `_current_candidate()`
- `rank_candidates()`

따라서 실험에서 바뀌는 것은 market pre-filter 수와 quick pool 수뿐이다.

## Variant
기본값:
- `BASELINE`: 160 / 18
- `MARKET_EXPANDED`: 320 / 18
- `QUICK_EXPANDED`: 160 / 36
- `BOTH_EXPANDED`: 320 / 36

CLI 옵션으로 확대값만 변경할 수 있다. Production 기본값은 바뀌지 않는다.

## 측정값
날짜별로 다음을 기록한다.
- market rank
- quick score / quick rank
- 각 Variant의 market pre-filter 통과 여부
- quick pool 통과 여부
- final evaluation 여부
- final rank
- drop stage
- 5/10/20 거래일 forward return
- MFE / MAE
- Target1 vs invalidation first-event
- event R
- Top 5 집계
- Baseline 대비 새 후보 수 / 새 Top5 수
- 실행 시간

일봉에서 Target1과 invalidation이 같은 날 모두 닿으면 체결 순서를 추측하지 않고 `AMBIGUOUS_SAME_DAY`로 기록한다.

## 네트워크 가드
CLI는 `OfflineAuditKrx`를 사용한다. 감사 중 KRX `stock_daily` / `index_daily` 호출이 발생하면 즉시 오류를 내도록 했다.

따라서 로컬 Market Store에 없는 날짜는 다운로드하지 않고 감사 대상에서 제외한다.

## 기본 실행
backend 디렉터리 기준:

```bash
python tools/run_scanner_pruning_audit.py
```

20개 과거 평가일을 자동 선택한다. 최신 데이터에서 약 35 calendar days를 비워 20거래일 미래 평가 구간을 확보한다.

특정 날짜:

```bash
python tools/run_scanner_pruning_audit.py --dates 2026-05-08,2026-05-15,2026-05-22
```

확대 범위 변경:

```bash
python tools/run_scanner_pruning_audit.py --market-limit 320 --quick-limit 36
```

## 출력
`backend/runtime/quality_audit/pruning/`

- `scanner-pruning-audit_*.json`
- `scanner-pruning-signals_*.csv`
- `scanner-pruning-summary_*.md`

## 검증 결과
실행 환경에서 다음을 확인했다.

- 새 모듈 `py_compile`: PASS
- 신규 pruning audit 테스트: **4/4 PASS**
- B.2.3.4b Scanner determinism 회귀 테스트: **5/5 PASS**
- 기존 Candidate Priority 회귀 테스트: **10/10 PASS**
- 출력 JSON/CSV/MD smoke generation: PASS

신규 테스트가 검증하는 항목:
1. Variant isolation + market 확대 시 후보 복구
2. 동일 입력 결정론
3. 미래 데이터 변경이 후보 선택을 바꾸지 않음
4. 기준일 데이터가 없으면 `SKIPPED_INSUFFICIENT_DATA`

## 제한
실제 사용자의 `market_history.db`는 이 작업 환경에 없으므로 실제 20일 StockScope 감사 결과 자체는 여기서 생성하지 않았다.
오버레이 적용 후 로컬 DB에서 러너를 실행해야 실제 Baseline/A/B/C 성과 비교가 생성된다.

## 다음 판단
실제 결과를 확인한 뒤에만 다음 작업을 정한다.

- 초기 pruning 손실이 확인됨 → `B.2.3.4c.2 Candidate Pool Policy Improvement`
- 영향이 미미함 → `B.2.3.4c.2 Strategy Search Top3 vs All Audit`

이번 단계에서는 Production 정책을 선제 변경하지 않는다.
