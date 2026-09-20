# StockScope v0.21.4-B.2.5-A — Scanner Decision Trace Smoke

## 목적

Scanner의 Production 판단식은 바꾸지 않고 다음을 관측 가능하게 만든다.

1. 최종 선택 전략이 왜 선택됐는지
2. 다른 전략은 어떤 selector 순위/조건 누락/Risk/current score 때문에 밀렸는지
3. READY/ENTRY_CANDIDATE와 Risk/조건 누락이 모순되지 않는지
4. 최종 후보 순서가 실제 `priority_sort_key`와 일치하는지
5. scanner-repro JSON에 Target1 cap/structural metadata가 빠지지 않는지

## 범위

- `scanner.py`: current-only strategy selection trace를 diagnostic hidden field로 수집
- `reproducibility_audit.py`: strategy trace + Target1 cap metadata 기록
- `scanner_quality/decision_quality_audit.py`: repro JSON 기반 consistency audit
- `tools/run_scanner_decision_quality_audit.py`: 최신 scanner-repro 자동 선택/실행
- focused tests 2개

## 비범위

- Strategy 조건/가중치 변경 없음
- Candidate ranking policy 변경 없음
- READY/WAIT policy 변경 없음
- RiskEngine 변경 없음
- Entry/Stop/Target1/Target2 계산 변경 없음
- Historical Evidence를 Production rank에 추가하지 않음
- Scanner decision version 변경 없음

## 실행 순서

1. 현재 working tree에 overlay 병합
2. focused tests 실행
3. Scanner에서 `다시 분석` 1회 실행해 fresh scanner-repro 생성
4. 아래 명령 실행

```powershell
.\.venv\Scripts\Activate.ps1
python backend\tools\run_scanner_decision_quality_audit.py --top 5
```

5. `backend/runtime/quality_audit/decision_quality/`의 최신 `.md/.json` 확인

## 1차 완료 기준

- fresh repro Top 5 모두 `strategy_trace` 존재
- final_sort_key 재정렬과 실제 후보 순서 일치
- READY + missing > 0 없음
- READY + Risk warning/block 없음
- 선택 전략 current score가 평가된 상위 3개 중 최고점과 일치

이 단계에서 이상이 없으면 B.2.5-B/C의 대형 검사는 하지 않고 다음 표본으로 넘어간다.
