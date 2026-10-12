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

## S1.3-UAT 사전 진단 및 실사용 승인 경계

**구현 기준:** Scanner/Production Baseline 및 전략·순위 계산은 변경하지 않고, Prospective 저장 컬럼 `rank`를 실제 Scanner의 `priority.rank`로부터 읽도록 수정했다. 원본 JSON 후보의 우선순위·Action·Risk는 그대로다. 구 저장 기록은 변경하지 않는다.

### 순위 저장 버그

기존 `ProspectiveCatalog.finalize_capture()`는 `candidate.get("rank")`로 별도 `prospective_recommendation_sample.rank` 컬럼을 채웠다. 실제 Scanner는 순위를 `candidate["priority"]["rank"]`에 기록하므로 이 컬럼이 NULL인 경우가 발생할 수 있다. S1.2의 `scanner_repro_candidate_key()`를 재사용해 검증된 정수 rank만 저장한다. 회귀 테스트에서 실제 Scanner 모양의 샘플로 **스냅샷 priority.rank와 DB rank의 일치**를 확인한다. 과거 NULL을 소급 수정하지 않는다.

### 읽기 전용 도구

`tools/data/audit_jev_act1_s1_3_uat.py`은 세 가지 동작을 제공한다.

1. `preflight --as-of YYYY-MM-DD --scope ALL --limit 5`: 현재 DB/시장별 확정일·최근 220일 평일 `day_status`·정책 Pin·기존 캡처·캐시 파일 존재 가능성을 조회한다. Provider 인스턴스를 생성하지 않으며 `_history_plan()`이나 `Scanner.run()`을 호출하지 않는다. 시장 슬롯 부족은 **KRX 호출량 추정치가 아니다**. `READY_FOR_APPROVAL_NOT_EXECUTION`도 0 네트워크 보증이 아니며, 사용자 별도 승인 전 Scanner를 실행하지 않는다.
2. `baseline`: **UAT 실행 이전** 최종 상태의 기존 캡처/샘플 스냅샷을 전체 읽어 캡처 ID별 Digest를 JSON으로 표준출력한다. 실제 시세/종목명/종목코드는 출력하지 않는다. 사용자가 별도 저장한 JSON은 `inspect --before`에 입력할 수 있다.
3. `inspect --capture-id <ID> --before <JSON파일> --scanner-result <원본Scanner결과JSON>`: 1건의 캡처 상태·정책 provenance·조건 근거·V2 무결성·DB rank·원본 Scanner 후보 불변성·전체 감사 출처·기존 캡처 Digest를 재검증한다. **원본 Scanner 결과 또는 UAT 이전 Baseline이 없으면 PASS 불가**; 불충분은 INCONCLUSIVE, 모순·원본 훼손은 FAIL로 구분한다.

### 실사용 UAT 전 사용자 승인

실제 UAT는 코드 작업에 포함되지 않는다. 사용자가 승인하지 않았다면 Scanner 실행, 최신 EOD 조회, `force_refresh`, `allow_large_sync`, 데이터 다운로드, DB 마이그레이션, Runtime 동기화를 수행하지 않는다. 날짜 없는 UI Scanner 요청은 최신 확정 EOD 준비를 시도하므로 **아무 요청 없이 로컬만 쓰는 검증으로 간주하면 안 된다**. 같은 날짜 기존 COMPLETE 또는 캐시가 있으면 신규 COMPLETE 대신 DUPLICATE/캐시 재사용이 될 수 있다.

### 현단계 완료 조건

- 읽기 전용 preflight/Baseline/inspect 테스트와 전체 CI PASS
- 순위 저장 컬럼 회귀 테스트 PASS
- 기존 Scanner/Rank/Risk·시장 데이터·기존 Prospective 기록 무수정
- 실제 신규 캡처 테스트는 **미실행**. 따라서 S1.3 실사용 UAT 결과는 PASS라고 선언하지 않음

## DATA-AUTO-S1 (1차 구현) — 새 기기에서 대량 수집 전 자동 안내

과거 특정 날짜의 Market DB를 복구하는 작업 대신, 사용자 버튼 `종목 찾기`로 새 기기에서도 자동 준비되도록 기본 경로를 개선한다.

- 기존 `prepare_latest_confirmed_data()`와 `StockScannerService.run()`은 이미 최신 확정일 확인, 기본 소량 증분 준비, API 예산, 준비 완료 시 Scanner 자동 계속 실행, 작업 취소 및 저장된 작업 재조회 기능이 있다. **중복 구현하지 않는다**.
- 사용자 클릭 시 신규 `POST /api/backtest/scanner/data-plan`을 먼저 호출한다. 읽기 전용 `plan_scanner_data()`는 당시 로컬 DB의 `day_status`, 필요한 최근 220일(달력 기준) 평일, 실제 gzip 캐시 정상 여부를 살피고 **기본 역사 데이터 요청량을 보수적으로 산정**한다. KRX Provider 또는 MarketStore 인스턴스, Budget 인스턴스는 생성하지 않으며 DB·파일을 변경하지 않는다.
- 기존 빠른 요청 한도 이하라면 사용자에게 불필요한 승인 창을 열지 않고 **현재 Scanner 작업**을 그대로 시작한다. 기존 Scanner가 확정일 탐색·정합성 검증·부족한 데이터 보충·분석 재개를 처리한다.
- 기본 한도보다 요청량이 많으면 종목 찾기 **실행 전에** 사용자의 데이터 준비 승인을 요청한다. 승인 후에만 `allow_large_sync=true`로 기존 Scanner 작업을 시작한다. 이때 `force_refresh`를 임의로 켜지 않는다.
- 로컬 KRX 안전 예산에 이미 부족함이 확인되면 막고 안내한다. 예산 DB가 아직 없으면 미확인으로 표기하며, 실제 실행에서는 기존 API Budget 차단을 유지한다.
- 원본 KRX 캐시 손상은 정상 캐시로 인정하지 않으며, 캐시 검증은 원본을 삭제하거나 수정하지 않는다. 과거 정상 빈 거래일 마커는 재사용한다.
- **계획 날짜는 최신 확정 거래일 자체가 아님**: 네트워크 최신 EOD 검증, 휴장일 탐색, 요청 재시도, 무결성 검증으로 실제 호출 수가 더 발생할 수 있다. 예측치는 확정 비용이나 총 API 사용량이 아니다. 최종 실행 한도는 실제 Scanner의 KRX Budget이 강제한다.
- 브라우저가 도중에 닫혀도 이미 저장된 Market DB/원본 캐시는 다음 시도에서 재사용하고, 기존 세션 작업 재연결 계약을 유지한다.

### 1차와 남은 범위

이 PR에서 달성할 범위는 **읽기 전용 계획 → 소량 자동 시작 / 대량 승인 → 기존 Scanner 자동 실행** 및 이에 대한 합성 테스트/CI다. 새로운 시장 데이터나 사용자 기록을 실제로 변경하는 테스트는 수행하지 않는다.

추가 검증 필요: 복잡한 최초 설치·휴장일·무결성 오류·요청 예산·브라우저 이탈 실제 동작, 분석 전에 데이터 부족 때문에 생성되는 부분 결과의 사용자 표현, 실제 사용자 승인에 따른 제한된 신규 KRX 실행. **학교 PC에서 실제 UAT가 성공하기 전까지 DATA-AUTO-S1 실사용 완료라고 선언하지 않는다.**

## JEV-ACT2-S1 — 실제 호출 전 Fake Provider 실행 및 V4 조회 정합성

**범위:** JEV UI 애니메이션이 아니라 Backend의 안전한 실제 실행 경로 검증. 운영 기능은 계속 `DISABLED_VALIDATION_PENDING`이고, 외부 TypeSafe 모델 호출·API 인증·비용 지출·Scanner 실행·과거 자료 보완·Holdout 접근은 하지 않는다.

### 기존 엔진에서 발견한 결함

- `JevManualReviewService`는 저장된 검토의 `ABSTAIN`을 수동 호출 반환과 재사용 결과에서 `PASS_THROUGH`로 바꿀 가능성이 있었다. VALID 판정값을 각각 정확히 보존하도록 수정했다. 단, **현행 V4 단일 Q1 결정 정책은 PASS_THROUGH/REVIEW_REQUIRED만 산출**하므로 ABSTAIN 처리 검증은 합성 코어 응답 및 저장 계약을 테스트하는 것이다.
- `project_typesafe_review`의 저장 결과 재검증은 V1~V3만 인식해, V4의 유효한 모델 결과도 조회에서 `CONTRACT_VERSION_MISMATCH`나 미인식 분기로 오류가 날 수 있었다. V4 Question/Disposition 계약을 명시적으로 분기하고 V4 Q1 확률과 고정 임계값을 사용해 저장된 결과를 **서버에서 다시 계산/검증**하도록 변경했다. 원본 Scanner 판단에는 영향 없음.

### 오프라인 통합 검증

`backend/tests/test_jev_act2_s1_fake_pipeline.py`에서는 **별도 임시 SQLite**에 Prospective와 TypeSafe V2 테이블을 생성하고, Canary V4의 합성 잔여 의미 검토 소스에서 다음을 실행한다.

1. 명시적인 합성 SHORT 기간, 유효 V4 source, FAKE 전용 고정 프로토콜 및 Test Fake Provider
2. V4 Q1 호출 → PASS_THROUGH 또는 REVIEW_REQUIRED → DB의 VALID 저장 → 모니터 조회의 `integrity_status=MATCHED` 및 같은 disposition 재검증
3. 동일 요청 두 번: 새로운 Provider 호출 없이 저장 결과 재사용
4. 모델 오류·잘못된 응답: ERROR 저장, 기존 Scanner 캡처 유지
5. 기간 미지정 기존 캡처: V4 진입 실패, Provider 호출 없음
6. synthetic VALID ABSTAIN 저장/재사용 표현: PASS_THROUGH로 변조되지 않음 (V4 Q1 정책의 실제 출력은 아님)

오프라인 Fake Provider 결과는 실제 모델의 정확도·추가 유용성 또는 운영 입력에서의 잔여 사례 출현을 증명하지 않는다. 테스트용 SHORT 캡처는 제품용 Horizon 숫자 정책 승인과 전혀 관계가 없다.

### 실제 사용자 JEV가 여전히 비활성인 근거

기존 읽기 전용 감사 도구:
```powershell
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py
```

- 진입 후보에 대해 `LEGACY_UNSPECIFIED`를 SHORT/MEDIUM으로 추정하거나 소급 변경하지 않음
- LOCAL_MATCH는 모델 호출 필요 없음
- SHORT/MEDIUM 숫자 Horizon 정책은 아직 EVALUATION_PENDING
- 실제 V4 Canary, 모델 버전/가격·권한·외부 전송 승인, 사용자 기능 활성화가 아직 HOLD
- `--json`에는 `user_jev_execution`이 추가되어 차단 이유·LOCAL_MATCH 수·기술적 잔여 검토 적격 건수를 익명 집계하고, 실제 AI 호출 수 0건을 명시함

**최종 판정:** ACT2-S1 오프라인 실행 경로와 조회 회귀 통과 후에도, 실제 외부 모델 호출 및 사용자 기능 제공은 별도 승인·UAT 이전까지 완료가 아니다. V4 모델 호출 후보가 없는 경우 가짜 호출을 만들지 않는다.

## JEV-ACT2-S2 — Horizon 차단 및 실제 의미 검토 도달성 진단

**범위:** 2026-10-12 `01d0b7c` 이후 안전한 오프라인 검증 단계. 현재 Scanner 규칙과 의미 계약의 *구조적* 도달성을 구분한다. 운영 Scanner/DB 쓰기, KRX, 외부 모델, 정책 승인, Holdout, Runtime sync, 기존 기록 수정은 모두 제외한다.

### 정책 경계 (승인하지 않음)

- `ScannerRequest.horizon_intent`가 명시된 경우 `POST /scanner/jobs`의 `require_horizon_activatable()`에서 실행 전에 거절한다. `resolve_horizon_context("SHORT"/"MEDIUM")`은 모두 `EVALUATION_PENDING`/`HORIZON_NUMERIC_POLICY_NOT_APPROVED` 상태다.
- Prospective의 `capture_request_from_scanner_payload()`는 그 기간 문자열 및 정책 버전을 **기록**할 수 있지만, 그 자체가 신규 Scanner 실행 승인을 의미하지 않는다. 정식 실행은 API entry gate가 선행되어야 한다.
- `LEGACY_UNSPECIFIED`의 과거 캡처는 소급 편집하지 않는다. 5/10/20일 관찰창을 승인된 SHORT/MEDIUM 기간으로 전환하지 않는다.
- 투자 기간 숫자 정책(기간 정의·재검토·타임스톱·지원 전략·필수 입력·확인 규칙)은 동결 계약에 충분한 승인 근거가 확보되기 전까지 미승인이다.

### 기존 의미 계약의 구조적 차단

현재 `semantic_relations.py`의 10개 등록 전략 관계는 전부 `REQUIRES_ALL` / `HARD`이며, `condition_assertions.py`의 *통과한 조건* 매핑은 전부 `SUPPORTS`다. `project_passed_condition_assertions()`는 정확한 전체 PASS 조건 집합을 요구하므로, 해당 계약을 그대로 재조합하면 10개 모두 `LOCAL_MATCH`, `RESIDUAL_SEMANTIC_REVIEW`는 0개다.

추가한 `audit_current_pass_mapping_reachability()`는 실제 전략 정의 버전·관계·조건 매핑을 재사용하여 임시 합성 PASS 입력으로 이를 오프라인 증명한다. 실제 시장 데이터, 실제 후보, 실제 모델 성공을 재현한 것이 아니다. 정의/매핑이 누락되면 `UNDETERMINED_CONTRACTS`를 반환하여 'residual 없음'으로 잘못 단정하지 않는다.

실제 저장된 후보의 집계 결과와 합성 구조 진단은 `audit_jev_act1_readiness.py --json`의 독립 필드(`audit`, `horizon_gate`, `semantic_reachability`, `candidate_path`)로 분리한다. `PROVIDER_ELIGIBLE`은 기술적 V4 자격만 나타내며 외부 호출 승인이나 제품 활성화를 의미하지 않는다.

### 테스트·운영상 한계

- `backend/tests/test_jev_act2_s2_reachability.py`: 실제 등록된 10개 전략의 PASS 매핑 및 0 residual, 합성 UNRESOLVED 입력의 composer 도달성, 매핑 누락 시 fail-closed, 미승인 SHORT/MEDIUM 거절 및 LEGACY 보존.
- `backend/tests/test_jev_act1_s1_readiness.py`: 임시 SQLite 읽기 전용 진단 통합 결과와 원본 불변 검증을 확장했다.
- 기존 `test_jev_act2_s1_fake_pipeline.py`와 전체 backend/frontend/fresh-clone CI 회귀를 유지한다.
- **실사용 승인은 계속 HOLD**. 실사용 도달성 확보에 필요한 의미 소스/검토 역할 확장은 독립 계약과 사용자 승인 후 별도 과제로 취급한다. `LOCAL_MATCH`를 억지 residual로 바꾸거나 통과한 조건에 조작된 의미를 삽입하지 않는다.

## JEV-ACT2-S3 — Decision Reviewer 독립 오프라인 입력·Fake Shadow 검증

**범위:** 기존 TypeSafe V4(잔여 의미 전용)는 변경하지 않는다. 이미 동결된 `JEV_SCANNER_REVIEW_INPUT_V1` / `OUTPUT_V1` 통합 설계의 기능 일부를 **외부 호출 없는 별도 오프라인 계약 검증**으로 만든다. 실제 운영 모델 호출·Horizon 숫자 승인·전송 동의·미래 성과 평가를 대신하지 않는다.

### 연결 경로와 근거
- `backend/app/jev/decision_reviewer_offline.py`는 원래 Simulation DB의 canonical COMPLETE 및 그에 귀속된 sample을 `SQLite mode=ro`로만 읽는다. DUPLICATE는 canonical 식별자로 재지정하며 PARTIAL·FAILED·없는 캡처는 거절한다. 별도 Scanner 실행은 없다.
- 원본 candidate snapshot 해시·행 ID(action/rank/strategy/ticker)·정책 Pin 출처·기존 TypeSafe 의미 소스 V2 서명·실제 PASS 조건의 원본 식별자와 출처·Risk 및 필수 entry guide 구조를 검사한다. 불완전·위조·미지원 입력은 fail-closed이며 최신 데이터로 소급 채우지 않는다.
- 입력 `as_of`는 기준일과 캡처 시각을 분리하며 EOD 자료의 정확한 외부 공개 시간은 증명되지 않았으므로 `EOD_DATE_ONLY_EXACT_RELEASE_TIME_UNPROVEN`을 표시한다. 미래 날짜로 바뀐 필드는 차단하며, 독립적인 cutoff/외부 소스 보존·전송 권한이 없으므로 실제 모델 적격 또는 성과 모집으로 계산하지 않는다.
- LEGACY_UNSPECIFIED는 `LEGACY_INSPECTION_ONLY`이고 Fake 경로에서도 거절한다. 합성 SHORT/MEDIUM은 `OFFLINE_INSPECTABLE_ONLY`이며 숫자 Horizon 미승인 사유를 유지한다. 운영 Scanner가 SHORT/MEDIUM을 받아들이도록 바꾸지 않는다.

### 응답과 Shadow
- `validate_decision_review_response()`는 허용된 세 판단과 근거 코드·실제 입력 evidence ID, 응답 상한·유보 사유·근거 배열·금지 필드를 검증한다. 참조 근거에 없는 수치의 추가 주장은 보수적으로 거절한다. **정성적 문장의 사실성과 투자 효용까지 검증했다고 주장하지 않는다.**
- `OfflineFakeShadowSession`은 FAKE 표시가 있는 로컬 프로젝션만 처리하고, 입력·출력 계약 해시에 따른 메모리 내 독립 일지를 만든다. 중복/alias 리뷰는 최초 결과를 재사용한다. 부적합 출력은 `ERROR`·`MODEL_ERROR`·baseline 불변으로 닫는다.
- `audit_capture_review_scope_readonly()`는 단일 COMPLETE/canonical 캡처의 반환 후보를 전체 검사하고, 오프라인에서 검사 가능한 건수와 기존 LEGACY 검사 전용 건수·제외 사유를 익명 집계한다. 외부 호출·운영 DB 수정 없이 기술적 탈락 사유만 다룬다.
- `shadow_action=DEFER_THIS_OPPORTUNITY`은 유효한 `REVIEW_REQUIRED`인 경우에만 별도 연구용 가상 의견이다. 원래 `ENTRY_CANDIDATE`는 그대로며, 수익률·손실 회피·AI 효용·실제 매매 결과는 `NOT_EVALUATED`/`null`이다.
- Shadow 일지는 **오프라인 세션 메모리**에만 존재한다. Production Simulation DB 기록, 별도 review job/outbox, 장기 persistence, 사전 동결된 평가 protocol, 미래 검증 데이터 join은 S4 이후의 승인된 개발 대상이다. S3를 제품에 연결했다고 주장하지 않는다.

### 검증
`backend/tests/test_jev_act2_s3_decision_reviewer.py`는 `tmp_path`에 생성한 Prospective schema/가짜 Scanner와 같은 필드·V2 의미 계약에서 정상 PASS_THROUGH/REVIEW_REQUIRED/ABSTAIN, 해시 불변, 중복 canonical, 레거시 차단, 입력·근거 위조/시점 변조, Fake Provider 실패, 금지 응답과 in-memory 재사용을 확인한다.

S3 성공 판정은 **오프라인 계약을 완주하는 Fake 검토 및 CI**까지. 실제 JEV 호출·수익 개선·사용자 화면 기능의 완성 판정은 계속 `HOLD`다. 기존 S1/S2 회귀, Scanner/Rank/Risk, 데이터 이관·Runtime 동기화, Holdout은 건드리지 않는다.

## JEV-ACT2-S4 — 실제 AI Canary 실행 사전 준비 / 격리 Mock Shadow 기록

이 단계는 S3 Scanner Decision Reviewer(`JEV_SCANNER_REVIEW_INPUT_V1` / `OUTPUT_V1`)의 **모델 연결 구조를 격리된 테스트로 검증**하며, 동결된 TypeSafe V4 합성 Canary 정책/threshold를 수정하거나 제품 JEV를 활성화하지 않는다.

- `backend/app/jev/decision_reviewer_canary.py`: `assess_actual_canary_preflight`는 입력 해시·원본 기간 정책·자료 사용 가능 시간·source 전송권한·공급자 모델·요금·예산·사용자 별도 실행 승인을 점검한다. **어떤 flag를 모두 True로 넘겨도 현재 S3의 `OFFLINE_INSPECTABLE_ONLY`, 미승인 Horizon 및 정확한 자료 공개시각 부재를 우회할 수 없다.** 진단은 항상 `can_call_actual_provider=false`, 실제 호출 0건을 반환하며 네트워크에 접속하지 않는다.
- `build_mock_request`는 S3 INPUT_V1의 정량적 Scanner condition/Risk 근거만 전송용 형태로 제한한다. 종목 식별 코드·가격/진입 가이드 원문·NEWS·계좌 내용은 mock wire에 보내지 않고 빠진 근거의 제약을 명시한다. **정식 Provider payload로 승인한 출력이 아니다.**
- `MockHttpReviewer`는 `httpx.MockTransport`만 허용한다. 실제 HTTP transport, API key, 공급자 URL 및 유료 모델 실행을 시작하는 경로는 없다. Mock 응답도 S3 `validate_decision_review_response`가 판정·근거 ID·금지 필드를 검증한다.
- `TrialLimits`는 mock 호출 횟수·예약 예산·요청별 예약 한도·단일 동시 요청·재시도 0·deadline을 강제한다. 설정 오염 또는 quota 초과는 fail-closed. 실제 계정의 가격·사용량 증거라고 주장하지 않는다.
- `MockShadowJournal`은 개발 테스트가 명시적으로 전달한 **격리된 임시 SQLite 연결**에서만 스키마를 설치한다. canonical source/sample 해시, protocol/request/prompt/모델 identity, 응답 상태·실패 코드·가상 defer 표시를 기록한다. 중복은 재호출하지 않고, 완료 레코드 수정·삭제를 차단하며, 재시작시 남은 PENDING은 명시적으로 INTERRUPTED 처리할 수 있다. 메모리 내 S3 로그와 달리 테스트 DB 재조회가 가능하다.
- `tools/data/audit_jev_act1_readiness.py`의 기존 CLI/JSON 결과에 `s4_canary_preflight` 요약을 추가했다. 기존 읽기 전용 수집과 DB/Runtime 동기화 없음 원칙을 그대로 유지한다.
- `backend/tests/test_jev_act2_s4_canary.py`: Mock HTTP 성공/유보/오류/timeout, 출처 없는 응답, 요청 예산·중복, 모델/전송 사전 HOLD, 임시 DB 불변성과 종전 Scanner 스냅샷 보호를 확인한다.

**S4 완료의 정확한 의미:** Mock 연결·예약·실패 기록 및 실제 호출 사전 승인 누락을 탐지하는 구조가 준비됨. 실제 공급자 어댑터/모델 고정·source 사용권/보존 규정·Horizon 수치 정책 승인·시점 증명·운영 DB migration·진짜 Canary 실행은 여전히 **별도 사용자 승인 전의 HOLD**이다. `MOCK_HTTP`를 실제 모델 호출 실적으로 세거나 S3 가상 판단으로 효용을 주장하지 않는다. 실제 JEV가 Scanner 기존 판단 대비 좋은 결과를 내는지는 후속 prospective 검증이 필요하다.
