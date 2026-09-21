# StockScope TRACK.1 Phase 1 — Recommendation Tracking Foundation

범위: TRACK.1.0 ~ TRACK.1.2

- 기존 Historical Simulation을 `과거 전략 검증`으로 재분류
- 메인 Simulation 진입을 `추천 추적` Workspace로 전환
- 추천 추적 전용 SQLite DB (`backend/runtime/tracking/recommendation_tracking.db`)
- Scanner 추천 Snapshot + 추천일 확정 종가 저장
- 동일 종목/시장/추천일 중복 등록 idempotent 처리
- 추적 종료 시 데이터 삭제 없이 CLOSED 유지
- 최근 Scanner session 후보를 추천 추적 화면에서 바로 추가
- 기존 Historical Simulation은 두 번째 `과거 전략 검증` 탭에서 그대로 접근

이번 단계에는 아직 일별 성과 backfill, MFE/MAE, 5D/10D/20D 성과 계산은 포함하지 않는다. 해당 부분은 TRACK.1.3 이후다.


## v1.0.1 regression hotfix
- TRACK.1.0에서 Historical Simulation을 `과거 전략 검증`으로 의도적으로 재분류했으나, 기존 SIM.UI.1 source regression test가 예전 문구 `시뮬레이션 시작`을 계속 요구해 적용이 롤백되는 문제를 수정했다.
- 기존 기능을 되돌리는 대신 regression expectation을 새 제품 역할에 맞게 갱신한다.
- apply script가 해당 regression test 파일도 payload에서 함께 업데이트하도록 변경했다.
