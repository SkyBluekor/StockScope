# Implementation — v0.21.4-B.2.5-C

## 변경 파일

- `backend/app/backtest/candidate_priority.py`
  - 기존 base priority는 그대로 유지
  - exact tie group 탐지
  - structural Target1 거리 계산
  - 가장 가까운 후보 1개만 tie group 첫 위치로 승격
  - 나머지 peer는 기존 종목코드 순서 유지
  - tie metadata 추가

- `backend/app/backtest/reproducibility_audit.py`
  - `priority_tie` snapshot 추가
  - 새 tie focus가 포함된 effective final sort key 기록

- `backend/app/backtest/scanner_quality/decision_quality_audit.py`
  - B.2.5-C sort key 해석 지원
  - structural focus가 실제 최단 구조 목표 후보인지 검증
  - tie metadata를 Markdown에 표시

- `backend/tools/apply_b25c_ranking_tiebreak.py`
  - `scanner.py` 전체 파일을 덮어쓰지 않고 VERSION 한 줄만 안전하게 `0.21.3.7`로 변경
  - `0.21.3.6` + Historical Evidence v2 guard가 아닐 경우 중단

- `backend/tests/test_candidate_priority_v0214b25c.py`
  - exact tie promotion
  - structural target unavailable fallback
  - 기존 우선순위 경계 보존
  - final sort reproducibility / decision audit 검증

## Production 변경

변경됨:
- exact tie 해소 방식
- Scanner decision version `0.21.3.7`

변경 안 됨:
- Strategy 조건
- Risk gate
- Entry / Stop
- Target1 1.5R cap
- Target2
- Historical Evidence 역할
- Sector RS temporal gate
- MA120 policy

## 검증

로컬 staging 기준:

```text
pytest backend/tests/test_candidate_priority_v0214b25c.py
4 passed

py_compile
candidate_priority.py           PASS
reproducibility_audit.py        PASS
decision_quality_audit.py       PASS
apply_b25c_ranking_tiebreak.py  PASS
```

실제 사용자 working tree / Market Store runtime은 overlay 적용 후 Scanner 재실행으로 확인한다.
