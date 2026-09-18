# IMPLEMENTATION v0.21.4-B.2.3.4c.3a
## Pre-Pool Strategy Search Audit — Top3 vs All Before Quick18

### 실행 설정
- Model: GPT-5.6 Sol
- Reasoning: Medium
- Production policy changes: none
- Audit-only / offline-only

## 구현 내용

### 1. Quick18 이전에 Top3 vs All 분기
기존 c.3는 Production `_quick_current_candidate()`로 이미 선택된 Quick18 안에서만 Top3 vs All을 비교했다.
이번 c.3a는 Market prefilter 통과 종목 전체에 대해 다음을 별도로 계산한다.

- Baseline: 실제 Production `_quick_current_candidate()` 사용
- Expanded: c.3의 strategy evaluator를 `strategy_limit=None`으로 실행

그 뒤 각 경로에서 독립적으로 quick score를 정렬하고 Quick18을 만든다.

### 2. 후보군 교체 추적
날짜별로 다음을 기록한다.

- Quick18 overlap
- entrant / displaced candidate
- baseline/all quick rank
- baseline/all quick score
- baseline/all selected strategy
- All 선택 전략의 initial rank

### 3. Outside-Top3 rescue 정의
다음 조건을 모두 만족하면 rescued candidate로 기록한다.

- Baseline Quick18 밖
- All Quick18 안
- All 선택 전략 initial rank >= 4

추가 기록:
- rescued READY
- rescued Top5
- strategy initial-rank distribution

### 4. Final Top5 propagation
각 Variant의 Quick18을 기존 `_current_candidate()`와 `rank_candidates()`로 그대로 통과시켜 Final Top5까지 영향이 전파되는지 확인한다.

### 5. 미래 성과
5D / 10D / 20D에 대해:

- return
- MFE / MAE
- event R
- Target1-first / Stop-first
- date-level delta
- 5% trimmed mean

을 계산한다.

Quick18 entrant와 displaced 후보를 deterministic pair로 만들어 paired delta도 저장한다.

### 6. Quick-rank 이동
공통 후보에 대해:

- mean / median absolute rank change
- rank-up / rank-down
- rank-up >= 5
- rank-up >= 10
- Top18 진입 / 이탈

을 집계한다.

### 7. Runtime
Top3 Production quick path와 All pre-pool path의 wall-clock 비용을 각각 기록한다.
또한 baseline symbol evaluation 수와 All current-strategy evaluation 수를 저장한다.

### 8. 진행 로그
실행 중 다음 형식으로 날짜별 진행이 출력된다.

```text
[  1/80] 2023-06-07 OK poolΔ=2 rescued=1 3.82s
```

### 9. 판정
- `KEEP_TOP3_PREPOOL`
- `CONSIDER_EXPANDED_K`
- `CONSIDER_ALL_PREPOOL`
- `INCONCLUSIVE`

중 하나를 출력한다.

## 실행 명령

backend 폴더에서:

```powershell
python tools\run_scanner_prepool_strategy_audit.py --sample-size 80 --min-date-gap 3
```

Smoke:

```powershell
python tools\run_scanner_prepool_strategy_audit.py --sample-size 10
```

## 출력 위치

```text
backend/runtime/quality_audit/prepool_strategy/
```

생성 파일:

- `scanner-prepool-strategy-audit_<timestamp>.json`
- `scanner-prepool-strategy-signals_<timestamp>.csv`
- `scanner-prepool-strategy-pairs_<timestamp>.csv`
- `scanner-prepool-strategy-summary_<timestamp>.md`

## 검증 결과

실행한 테스트:

- c.3a 신규 테스트: 6/6 PASS
- c.1/c.2/c.3 + c.3a 관련 감사 테스트: 17/17 PASS
- Candidate Priority regression: 10/10 PASS
- Python compile: PASS
- Fake-store output smoke: JSON / CSV / pairs CSV / Markdown 생성 PASS

실제 사용자 `market_history.db`를 이용한 60~80일 통합 감사 실행은 이 환경에서 수행하지 않았다.
Production Scanner 정책/상수는 변경하지 않았다.
