# TRACK.1.10.4 — Same Baseline Tracking Merge

같은 시장/종목/기준일/기준가의 직접 추적과 Scanner 추천을 한 개의 추적 기록으로 합칩니다.

- `market + ticker + recommendation_date + reference_price`가 모두 같으면 병합
- 기준일 또는 기준가가 다르면 별도 기록 유지
- 기존에 이미 생긴 `추천`/`직접` 중복 행도 schema v4 migration에서 자동 병합
- 한 행이 `추천 · 직접` 출처를 동시에 가질 수 있음
- Scanner Snapshot/Rank/전략/Entry/Stop/Target은 병합 후에도 보존
- 추천 필터와 직접 필터 양쪽에 포함되지만 전체 목록에서는 한 번만 표시
- Production Scanner 알고리즘은 변경하지 않음
