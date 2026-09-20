# Implementation — v0.21.4-B.2.5-A

## 변경 사항

### 1. Strategy decision trace

`StockScannerService._quick_current_candidate()`에서 selector 평가 목록을 기록한다.

- selector rank
- eligible
- selector score
- reasons / unmet
- current evaluation 여부
- current status / internal score
- passed / total / missing
- Risk status / warning
- selected 여부

기존과 동일하게 selector 상위 3개만 current readiness/Risk를 계산하며, 최종 전략도 기존과 동일하게 그 3개 중 `current_internal_score` 최대 전략을 선택한다.

### 2. Repro snapshot 보강

`_candidate_snapshot()`에 다음을 추가한다.

- `strategy_trace`
- `target1_cap_applied`
- `target1_cap_price`
- `structural_target1_price`
- `structural_target1_basis`
- `target1_audit`

Production API schema에는 추가하지 않는다.

### 3. Decision-quality audit

fresh `scanner-repro_*.json`을 읽어 다음을 검사한다.

- 실제 후보 순서 vs `final_sort_key`
- READY/ENTRY_CANDIDATE + missing 조건 모순
- READY/ENTRY_CANDIDATE + Risk 경고/차단 모순
- READY vs priority tier 모순
- WAIT인데 조건/리스크 모두 정상인 사례
- selected strategy trace 존재 여부
- selected current score가 평가된 최고 current score와 일치하는지

결과는 JSON + Markdown으로 출력한다.

## 검증

패키징 환경에서 실행:

```text
3 passed — decision quality audit unit tests
1 passed — repro Target1/strategy trace metadata test
py_compile PASS — scanner.py / reproducibility_audit.py / new audit module / runner
```

최신 사용자 local Market Store/working tree에서의 fresh Scanner runtime 실행은 이 환경에서 수행하지 못했다. 실제 런타임 PASS는 overlay 적용 후 fresh repro로 확인해야 한다.
