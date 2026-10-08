# Scanner 판단 근거 및 AI 확장 계약 — JEV-X1

## 목적
Scanner가 최종 후보 순위를 계산한 순간 사용한 근거를 별도로 보존한다.
후속 후보 비교 및 이전 판단 대비 변화 설명의 사실 기반이다.
Jev를 호출하거나 기존 순위·Risk·가격·전략 판단을 변경하는 단계가 아니다.

- 근거 계약: `SCANNER_RANK_EVIDENCE_V1`
- 저장 버전: `SCANNER_RANK_EVIDENCE_STORAGE_V1`
- 신규 DB: `simulation.db`의 `scanner_rank_evidence` 및 `scanner_rank_evidence_schema_meta`
- 선행 요구: 기존 `VN-P2-S2` Prospective
- 적용: `sync_local.ps1`의 `JEV-X1` 마이그레이션 또는 명시적 migration 명령

## 기록 시점과 범위
기존 순위는 조건 충족·Risk·진입 거리·전략 적합도 순으로 결정한다.
완전 동률일 때는 구조 목표 거리가 가장 가까운 후보 한 개를 먼저
표시하고 나머지는 종목코드 순서를 유지한다.

`rank_candidates`의 선택적 `evidence_sink`가 실제 정렬 값을
순위 확정 시점에만 복사한다. 정렬 계약의 원본 숫자 및 방향과
동률 그룹·처리 방식을 보존하며, 기존 내부 `_sort` 제거는 유지한다.
3년 과거 근거는 현행 순위에 관여하지 않으므로 순위 결정 요인으로
표시하지 않는다.

## 격리·동일성
1. 신규 Scanner 결과에는 비공개 `_rank_evidence`가 포함되며,
   같은 날 Scanner 캐시에도 저장된다.
2. API는 Prospective 캡처 생성 **전에** 이를 제거한다. 그러므로
   `source_snapshot_hash`, `result_hash` 및 기존 후보 snapshot에
   정렬 근거를 끼워 넣지 않는다.
3. Prospective finalize 이후 샘플의 시장·종목코드·전략·순서·순위와
   근거가 일치하는 경우에만 새 테이블에 저장한다.
4. 중복 캡처는 canonical 캡처에 실제 근거가 존재할 때만 재사용한다.
5. 이전 Scanner 캐시나 과거 캡처에 정렬 근거가 없으면
   `NOT_AVAILABLE_LEGACY`다. 과거 기록을 현재 코드로 소급 계산하지 않는다.
6. DB 마이그레이션이나 근거 저장이 실패하더라도 Scanner의 기존
   기본 분석은 계속 반환한다. 실패 상태는 `rank_evidence_recording`에 표시한다.

추가 레코드는 기존 Prospective 원본과 분리된
`(capture_run_id,sample_index)` 키와 FK에 연결한다.
UPDATE/DELETE는 DB 트리거로 차단하고 재요청은 Hash 일치 시에만
REUSED로 반환한다.

## 백업·복원
`scanner_rank_evidence`는 `simulation.db` 내부 테이블이다.
따라서 simulation DB 전체를 포함하는 기존 백업·복원에 함께 포함된다.
holdings DB만 복원하면 근거는 복원되지 않으므로 사용자가
`restore_simulation`을 선택한 경우에만 이 정보가 복원된다.
시뮬레이션 DB를 복원한 뒤 `sync_local.ps1 -CheckOnly` 상태를 확인한다.

## 후속 구현
- X2: 같은 캡처 내 두 후보 정렬값을 비교하고 최초로 달라진 순위 요소 설명
- X3: 두 날짜의 확정 캡처를 비교해 실제 조건·정책·모집단 변화 구분
- X4: X2/X3에서 로컬로 풀리지 않는 의미 문제에만 별도 Jev 질문 설계

현재 `rank_change`는 같은 실행의 **정렬 전후 변화**다.
이전 날짜 대비 변화로 재사용하지 않는다.
