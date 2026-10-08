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

기존 `write_scanner_reproducibility_audit`는 실제 순위 확정 직후
내부 정렬값 및 `final_sort_key`를 이미 기록한다. 이 감사 기록을
`rank_audit_adapter.py`에서 검증하고 필요한 필드만 추출한다.
`scanner.py` 및 `candidate_priority.py`의 생산 코드와 고정 기준선은
**변경하지 않는다.** 정렬 값의 원본·방향 및 동률 처리 근거가 유지된다.
3년 과거 근거는 현행 순위에 관여하지 않으므로 순위 결정 요인으로
표시하지 않는다.

## 격리·동일성
1. 기존 Scanner 감사 기록이 실제 로컬 파일로 존재하는 경우에만
   그 내용과 현재 Scanner 결과의 버전·기준일·시장·후보·순위·정렬키를
   대조해 근거를 추출한다. 경로는 전용 `scanner-repro` 경로로 제한한다.
2. 추출된 내용은 기존 Scanner 후보나 Prospective 캡처 입력에 **추가하지
   않는다.** `source_snapshot_hash` 및 `result_hash`를 변경하지 않는다.
3. Prospective finalize 이후 샘플의 시장·종목코드·전략·순서·순위와
   근거가 일치하는 경우에만 새 테이블에 저장한다.
4. 중복 캡처는 canonical 캡처에 실제 근거가 존재할 때만 재사용한다.
5. 이전 Scanner 캐시에 감사 파일이 없거나 과거 캡처에 근거가 없으면
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


## JEV-X2 — Scanner 두 후보의 실제 순위 차이 설명

`SCANNER_CANDIDATE_COMPARISON_V1`은 새 DB 테이블, Scanner 재계산 또는 AI 호출을 사용하지 않는다.
하나의 canonical Prospective capture에 보존된 두 개의 `SCANNER_RANK_EVIDENCE_V1`
불변 근거를 같은 읽기 트랜잭션에서 확인하고, 정렬키의 최초 차이만 순위 결정
이유로 반환한다. 후속 차이는 참고 수치일 뿐 결정 요인으로 취급하지 않는다.

- API: `GET /api/simulation/prospective/captures/{capture_id}/candidate-comparison?left_sample_index=0&right_sample_index=1`
- 구현: `backend/app/prospective/rank_comparison.py`
- UI: 기존 Scanner 후보 표 아래 두 후보 선택과 결론/8개 정렬항목 표
- 비교 키: tier_order → missing → risk_quality → entry_gap_missing →
  entry_gap_pct → negative_strategy_fit → tie_focus_order → code
- 동률 구조 목표 승격은 저장된 같은 tie group / tie breaker 증거가 맞는 경우에만 설명한다.
- 코드 정렬은 투자 우열이 아니라 표시 안정화를 위한 최종 정렬이다.
- 캡처·샘플·해시·정책·버전·기준일 불일치 시 fail-closed; 근거 없는 오래된 캡처를
  새 정렬 함수로 역산하지 않는다.
- Duplicate는 canonical capture로 이동; Partial은 저장된 반환 후보의
  비교만 허용하고 데이터 범위 제한을 고지한다.
- 실시간 KIS 시세 변동이나 과거 검증 성과를 실제 순위 결정 근거로 표시하지 않는다.
- 사용자가 이전 세션에서 복원한 Scanner 결과라도 서버가 기록을 다시 검증한다.
- Production baseline, 전략 로직, Prospective snapshot/result 해시, 데이터베이스 원본은
  변경하지 않는다.

X1의 신규 근거 저장이 성공했는지 실제 PC에서 `rank_evidence_recording.status=STORED`
여부를 확인해야만 사용자 환경 적용을 완료 처리한다. 마이그레이션 CURRENT만으로
추가 근거가 생성됐다고 판단하지 않는다.


## SC-UX1 — 초보자용 종목 후보 판단 화면 (사용자 표현 계약)

**목적:** 투자 조건 충족(Scanner READY)을 실제 매수 가능 신호로 오인하지 않도록 한다.
이 계약은 UI 표시와 읽기 전용 시세 조회만 다루며 종목의 원래 순위·전략·Risk 기준을 수정하지 않는다.

### 첫 화면에서 먼저 보여줄 것

1. 해당 거래일에 확인된 종목의 목록과 *검토 순서* (매수 순위 아님)
2. 각 종목의 투자 조건 상태와 분석일 종가 기준 가격 참고 상태
3. 선택 종목에 대한 **왜 찾았는지 / 무엇을 조심해야 하는지 / 다음 확인 사항**
4. *분석 당시 종가*와 *전략의 참고 가격*을 나란히 제시
5. 새 시세는 사용자가 **새 시세 확인**을 명시적으로 선택한 경우에만 조회
6. 고급 목표가격·과거 자료·AI 관련 진행/검토·X2 계산값은 기본 접힘

### 상태 구분

- 투자 조건: `priority.tier`, `conditions`, `risk`, `action` 등 **이미 계산된 상태**의 쉬운 설명
- 가격 기준: `entry_risk_guide.price_rule`이 실제로 제공하는 `RANGE`, `ABOVE`, `AT_OR_BELOW` 조건에 대해서만 분석 종가 또는 조회 시세와 비교
- `REFERENCE` 및 자료 부족 시에는 비교 불가 처리; 참조 가격에 접근했다는 이유로 매수 가능 상태 만들지 않음
- 시세 출처: KIS 응답의 실거래/모의 환경, 수신 시각, 제공 시각, 캐시 출처, 시장 상태를 함께 명시
- 새 시세 확인은 **기존 전략 조건을 갱신하지 않음**; 조회 시세의 가격 조건에 진입해도 주문이나 매수 신호를 자동 발생시키지 않음

### 관련 코드

- `scannerDecisionPresentation.ts` — 순위·Risk·조건·가격을 보수적으로 풀이하는 순수 함수
- `ScannerDecisionSummary.tsx` — 결론·이유·주의·다음 행동
- `ScannerPriceStatus.tsx` — 선택 종목 수동 KIS 조회 / 시각·시장·출처 표시
- `ScannerPanel.tsx` — 쉬운 후보 목록, 기본 상세, 고급 정보 접기
- `ScannerRankComparison.tsx` — 두 종목 차이를 일상적인 설명으로 우선 표현, 실제 정렬값은 별도 펼쳐보기
- `scannerUX.css` — 표형 편집 디자인과 작은 화면 레이아웃

### 검증

`npm run test:sc-ux1`의 Node 22 회귀 검사에서 READY이면서 가격이 범위 밖인 경우, NEAR_READY이면서 가격만 맞는 경우,
위험 경고 우선, ABOVE/AT_OR_BELOW/RANGE 경계값, REFERENCE·결측 처리 상태를 확인한다.
GitHub CI 프론트 빌드와 기존 백엔드/Windows 검사는 별도로 통과해야 한다.
**실제 기기 화면·KIS 연결 UAT를 완료하기 전에는 운영 환경 검증 완료로 표현하지 않는다.**

### 범위 제외

실제 주문·자동매매·Scanner/Strategy/Prospective/JEV-X1/X2 순위 재계산, 새로운 API 인증 처리,
장시간 자동 새로고침, 사용자 DB 마이그레이션, 외부 Jev/LLM 호출.
