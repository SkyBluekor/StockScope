# IMPLEMENTATION v0.21.4-B.2.3.4c.2
## Temporal Spread Validation for Quick Pool 18 vs 36

## 구현 목적
B.2.3.4c.1에서 `160/18` 대비 `160/36`이 소폭 우수했지만, 20개 평가일이 짧은 기간에 몰렸고 Top5 교체가 1일뿐이었다. 이번 구현은 Production Scanner를 바꾸지 않고, Quick pool 18 vs 36을 넓게 분산된 과거 날짜에서 다시 검증한다.

## 변경 파일
- `backend/app/backtest/scanner_quality/early_pruning_audit.py`
- `backend/app/backtest/scanner_quality/__init__.py`
- `backend/tools/run_scanner_pruning_audit.py`
- `backend/tests/test_scanner_pruning_audit.py`

Production `scanner.py`, Strategy, Ranking, Risk, Target/Stop 계산 파일은 수정하지 않았다.

## 주요 구현

### 1. Temporal validation mode
CLI에 다음 모드를 추가했다.

```bash
python tools/run_scanner_pruning_audit.py --mode temporal-validation --sample-size 80 --min-date-gap 3
```

이 모드에서는 두 Variant만 실행한다.
- `BASELINE`: Market 160 / Quick 18
- `QUICK_EXPANDED`: Market 160 / Quick 36

### 2. 분산 평가일 샘플링
- 로컬 Market Store에서 KOSPI/KOSDAQ stock + index가 모두 `data`인 공통 거래일만 사용
- 미래 20거래일이 남아 있는 날짜만 평가 가능
- 최근 연속 날짜가 아니라 전체 유효 기간에 균등 분산
- `--min-date-gap`은 공통 거래일 기준 선호 간격
- 선호 간격 때문에 최소 검증일 수를 채울 수 없으면 3 → 2 → 1 순으로 자동 완화하고 실제 적용값을 결과에 기록

### 3. Top5 Change Frequency
18과 36의 Top5가 실제로 달라진 날짜를 기록한다.
- changed / unchanged dates
- change rate
- 날짜당 평균 교체 종목 수
- 최대 교체 종목 수

### 4. Paired Replacement Analysis
Top5가 바뀐 날짜에 대해 빠진 종목과 새로 들어온 종목을 대응시켜 다음을 기록한다.
- 5D / 10D / 20D 수익률 차이
- 20D R 차이
- Target1 / Stop event 차이

별도 `scanner-pruning-pairs_*.csv`를 생성한다.

### 5. Date-level delta + trimmed mean
각 날짜의 Quick36 Top5 성과에서 Quick18 Top5 성과를 뺀 delta를 계산한다.
- 평균 / 중앙값
- 5% trimmed mean
- 개선 / 악화 / 동일 날짜 수
- R delta
- Target1-first / Stop-first delta

### 6. 보수적 판정
결과는 다음 중 하나로 요약한다.
- `KEEP_18`
- `CONSIDER_36`
- `INCONCLUSIVE`

최소 유효 평가일 수를 채우지 못하면 자동으로 `INCONCLUSIVE`다. `CONSIDER_36`은 평균수익만 좋아서는 나오지 않으며, temporal / paired / trimmed / R / Stop 조건이 함께 맞아야 한다.

### 7. 18 vs 36 계산비용 계측 개선
c.1은 감사 편의를 위해 current candidate를 넓게 선계산했기 때문에 18 vs 36의 추가 계산비용을 직접 비교하기 어려웠다.

c.2에서는 각 Variant가 실제 선택한 Quick pool에 대해서만 `_current_candidate()`를 실행하고 `evaluation_runtime_seconds`를 별도로 기록한다. 이는 감사 러너 내부 변경이며 Production Scanner에는 영향이 없다.

### 8. 진행상황 표시
긴 감사 실행 중 빈 터미널로 보이지 않도록 날짜별 진행을 출력한다.

예:
```text
[  1/65] 2026-02-10 OK 1.82s
[  2/65] 2026-02-12 OK 1.77s
...
```

### 9. Temporal JSON 크기 절감
c.1의 20일 JSON은 종목별 전체 trace 때문에 약 28MB였다. Temporal mode에서는 분석에 필요한 candidate/outcome/pair/date-level 근거는 유지하고 수천 종목의 중복 trace는 결과 JSON에서 제거한다.

기존 c.1 20일 결과를 temporal summary로 변환한 smoke test 기준 JSON이 약 8.2MB로 감소했다.

## 출력
기본 위치:
`backend/runtime/quality_audit/pruning/`

생성 파일:
- `scanner-pruning-audit_<timestamp>.json`
- `scanner-pruning-signals_<timestamp>.csv`
- `scanner-pruning-pairs_<timestamp>.csv`
- `scanner-pruning-summary_<timestamp>.md`

Markdown 최상단에서 다음을 바로 확인할 수 있다.
- 평가일 범위
- 요청/실제 date gap
- Top5 changed dates / change rate
- 5D/10D/20D delta
- trimmed mean
- R / Stop delta
- 18 vs 36 current-eval runtime
- 최종 verdict

## 검증 결과

### 신규/확장 감사 테스트
`backend/tests/test_scanner_pruning_audit.py`
- 7 passed

검증 항목:
- Variant isolation
- 결정론적 결과(시간 필드 제외)
- 미래 데이터가 후보 선택에 영향 없음
- 정확한 분석일 데이터가 없으면 skip
- temporal sampling 결정론 및 기간 분산
- paired replacement 계산
- trimmed mean outlier 완화
- unchanged Top5 집계

### 기존 회귀 테스트
- B.2.3.4b Scanner determinism: 5 passed
- Candidate Priority: 10 passed

총 실행:
```text
22 passed
```

### 실제 c.1 결과 재사용 smoke test
사용자가 생성한 20일 c.1 JSON을 c.2 temporal summary에 입력하여:
- changed date 1/20 탐지
- paired CSV 생성
- date-level delta 생성
- `INCONCLUSIVE` 판정
- JSON/CSV/Pairs/Markdown 생성
을 확인했다.

## 검증 한계
현재 작업 환경에는 사용자의 전체 StockScope 저장소와 실제 `market_history.db`가 없어서, 새 CLI를 실제 DB로 60~80일 실행하는 full integration은 여기서 수행하지 않았다. 실제 학교 PC의 로컬 Market Store에서 실행해 최종 결과를 확인해야 한다.

## 실제 실행 명령
`backend` 폴더 터미널 기준:

```powershell
python tools/run_scanner_pruning_audit.py --mode temporal-validation --sample-size 80 --min-date-gap 3
```

로컬 market-wide 완전 데이터 일수가 부족하면 선택 수가 80보다 적을 수 있다. CLI가 `requested`, `selected`, `gap 3->2` 같은 실제 샘플링 상태를 출력한다.

## 이번 버전에서 하지 않은 것
- Production Quick limit 18 → 36 변경
- Market limit 160 변경
- Strategy Top3 → All 변경
- MA120 / 중복 조건 수정
- Ranking 공식 변경
- Market Regime 변경
- Historical Evidence Ranking 재투입
