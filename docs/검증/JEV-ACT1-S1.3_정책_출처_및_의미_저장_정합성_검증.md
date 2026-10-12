# JEV-ACT1-S1.3 — 실행 정책 출처와 Prospective 의미 자료 저장 검증

## 목적과 출발점

- 선행: S1.2 순위 연결 수정 PR #97, commit `ddb8b9f`.
- 학교 컴퓨터 기존 완결 캡처에서 실제 Scanner 조건 근거 9/9 일치: **조건 근거만** 입증.
- 구 캡처의 Selection Policy는 `request_json` 일부 필드만으로 출처를 추정할 수 없다. 미확인 과거 자료는 `UNKNOWN`.
- S1.3은 **신규 Scanner 실행**이 전달하는 `SelectionPolicyPin`을 검증한 뒤에만 semantic source V1/V2가 완성될 수 있도록 연결한다.

## 신규 캡처의 증거 경로

1. `ProductionStrategySelectionRegistry.pin_active_selection_policy()`가 실제 Scanner 실행에 정책을 고정한다. ACTIVE/ROLLBACK은 Registry에서 정책 스냅샷 hash, Production Baseline 호환성을 사전에 검증한다.
2. 같은 Pin이 Scanner `run()`과 Prospective `try_finalize_scanner_capture()`에 전달된다. 저장 직전 `Scanner result.strategy_selection_policy` **전체 metadata**와 Pin metadata를 대조한다.
3. `ProspectiveCaptureRequest.selection_policy_id/hash`가 Pin과 일치해야 한다.
4. LEGACY는 `legacy_selection_policy()`에서 재계산한 ID/Hash, 전략 집합, 버전/해시 공백 및 fallback flag를 검증한다. ACTIVE/ROLLBACK은 고정된 Pin의 허용 전략 집합과 version/hash를 후보 원본에 대조한다.
5. 새로 생성한 재현성 감사 파일이 S1.2의 `verified_scanner_repro_rows()` 검사를 통과하고 후보 `priority.rank`, 감사 행 `rank`와 전략/Action/Risk/가격/조건 요약/엔진 PASS 조건이 일치해야만 의미 자료를 완성한다.
6. 한 개라도 불일치하면 **원본 Scanner 후보 필드·결정·Risk·Rank는 변경하지 않는다**. 의미 분석용 입력의 전략 버전과 조건 증거만 보류하여 `LOCAL_INCOMPLETE`로 처리한다.
7. 후보 저장 스냅샷에는 `semantic_policy_provenance`를 남긴다. `VERIFIED_PINNED_EXECUTION`은 그 실행의 Pin 검증을 통과한 경우에만 쓴다. 원본 전략 버전/해시와 의미용 검증 출처는 별개다.
8. `semantic_source_v2`의 실제 판정은 현 계약을 따른다. `LOCAL_MATCH` 등을 인위적으로 만들지 않는다. V4 활성화·모델 전송·가격 및 계정 승인·사용자 동의·Horizon 게이트와 무관하다.

### FAIL-CLOSED 이유 코드

- `POLICY_PROVENANCE_MISSING`: 실행 Pin 또는 필수 출처 없음
- `POLICY_PIN_MISMATCH`: Pin, Scanner metadata, Prospective request 간 불일치
- `POLICY_DEFINITION_MISMATCH`: LEGACY 재계산 해시/집합 불일치, ACTIVE/ROLLBACK 정합성 부적합
- `POLICY_STRATEGY_BINDING_MISMATCH`: 후보 전략 ID/Hash가 정책의 고정된 전략과 불일치
- 감사 파일 증거 누락/불일치: S1.2의 fail-closed 검증에 따라 `semantic_condition_evidence`를 생성하지 않음

### 과거 자료와 감사 진단의 경계

`tools/data/audit_jev_act1_s1_3_provenance.py`는 저장된 **COMPLETE** 후보에 대해 다음을 익명·읽기 전용 집계한다.

- 분석 기준일별 저장 진입 후보 수, 저장 snapshot hash 유효성
- S1.3에 **신규 저장된** `semantic_policy_provenance` 기록과 요청 ID/Hash의 정합성
- 기존 Scanner 재현성 감사 파일을 통한 후보·조건 단위의 역사적 일치 여부
- V2 저장 상태와 전체 캡처 상태(COMPLETE/DUPLICATE/PARTIAL 등)

**중요한 한계:** 과거 감사 파일이 일치해도 당시 Scanner 실행의 원본 Pin/전체 요청/입력 Fingerprint와 연결된 새 `fresh_analysis` 메타가 없는 이상 정책 출처를 **사후 인증하지 않는다**. 이 도구는 기존 DB를 다시 작성하거나 모델 사용을 승인하지 않는다.

### 실행

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_jev_act1_s1_2_semantic_pipeline.py backend/tests/test_jev_act1_s1_3_provenance.py -q
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_s1_3_provenance.py
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py
```

`--json`으로 동일한 익명 진단 결과를 JSON 출력할 수 있다.

## 중복·불변성 및 완료 조건

- 신규 Scanner 결과의 정책/감사 검증과 SQLite 캡처 저장/동일 입력 중복 처리를 통합 테스트한다.
- `source_execution_key`, `source_snapshot_hash`, `result_hash` 산식과 기존 중복 정책을 **변경하지 않았다**. 의미 source가 이전 코드와 달라지면 새 snapshot hash가 생성될 수 있는 **버전 간 호환성 한계**가 존재한다. 기존 캡처를 덮어쓰거나 소급 보완하지 않는다. 해당 케이스의 중복 정책 변경은 별도 승인·설계 필요.
- 기존 Scanner, Production Baseline, Strategy/Risk, Holdout, Runtime 동기화, TypeSafe 모델 호출/비용 승인 모두 변경하지 않는다.
- 테스트 및 CI가 PASS하면 **구현·오프라인 계약 검증 완료**. 신규 실제 Scanner 실행 및 COMPLETE 캡처를 확인하기 전까지 **실사용 UAT 완료는 아님**.

## 후속 UAT

사용자가 별도로 승인하면 최신 확정 시장 데이터로 신규 Scanner 한 번을 수행한 뒤 다음을 점검한다.

1. `scanner_cache_hit=false`, 감사 파일 생성 성공
2. `prospective_capture.status=COMPLETE` 또는 결과가 동일한 경우 `DUPLICATE` 사유 구분
3. 새 COMPLETE의 `semantic_policy_provenance.status=VERIFIED_PINNED_EXECUTION`
4. 엔진 조건 증거·V2 무결성·로컬 판정·중복 처리
5. 독립된 `LEGACY_UNSPECIFIED` Horizon과 TypeSafe V4/provider 활성화 HOLD 유지

실데이터를 강제로 변경해서 UAT 성공을 만들지 않는다.
