# JEV-ACT1-S1.2 — Scanner 의미 자료 생성·전달 계약 정합성

**구현 기준:** `85457c6` (JEV-ACT1-S1.1) · **작업:** JEV-ACT1-S1.2
**범위:** 신규 Scanner 후보의 의미 자료 입력·Prospective 저장 경로
**범위 밖:** Jev 유료 호출·기능 활성화·기존 캡처 재기록·Selection Policy 변경·Horizon 정책 변경·Scanner 의사결정 변경

## 확인된 사실과 아직 미확인인 것

사용자 PC: 2026-09-27 진입 후보 15건은 `semantic_source_v2` 자체가 없고, 2026-10-10 신규 진입 후보 6건은 `LOCAL_INCOMPLETE`였다. 후자 6건 전부 `SEMANTIC_CONTRACT_BINDING_MISSING`, `CONDITION_ASSERTION_SOURCE_MISSING`이 함께 관측되었다.

코드 원인은 다음과 같이 결합될 수 있다:

1. Scanner의 `_quick_candidate()`는 실제 평가한 전략을 알고 있지만 전략 신원은 Selection Policy의 `strategy_reference()`에서 가져온다.
2. 정상 레거시 정책 `LEGACY_CURRENT_10_FALLBACK`은 정책의 정의상 버전 및 해시를 `None`으로 둔다.
3. `semantic_contract.resolve_strategy_semantic_contract()`는 key/version/hash 모두 필요하다.
4. 원래 `semantic_source.build_semantic_source()`는 위 의미 계약이 연결되지 않으면 조건 요약을 전달하지 않는다. 그 때문에 assertion 쪽도 SOURCE_MISSING이 될 수 있다.

**중요:** 현재 PC의 기존 6건에서 Selection Policy provenance를 확인한 것은 아니다. 캡처 스냅샷에 출처가 별도로 보존되지 않았으면 `LEGACY_UNSPECIFIED` 투자 기간만으로 Selection Policy fallback 사용 여부를 유추해서는 안 된다. `tools/data/audit_jev_act1_s1_2_inputs.py`는 이 점을 명시하고 저장된 필드의 존재 여부만 집계한다.

## 해결 설계 (fail closed)

### 1. 실제 Scanner 전략 평가 시에만 보조 신원 서명

- `backend/app/backtest/scanner.py`에서 실제 엔진의 선택 전략을 사용한 뒤 fallback 정책 출처와 함께 `semantic_strategy_identity`를 생성한다.
- 정책 키·버전·해시 필드는 **원래 그대로 유지**. 레거시 정책의 `None`을 정식 전략 정책 신원으로 소급 채우지 않는다.
- 보조 신원에는 선택 전략 키, 현재 StrategyEngine AST로 계산한 정의 버전·해시, 선택 정책 ID·해시를 기록한다.
- 정상 활성·롤백 정책 경로에는 이 fallback 보조 신원을 만들지 않는다.

### 2. 실제 엔진 통과 조건의 별도 근거

- `build_condition_state()`의 `conditions` 리스트를 사용한다. `passed=total`이라는 숫자만 보고 어떤 조건이 통과했는지 추정하지 않는다.
- 상태는 모두 PASS, 중복 없음, 조건명 집합은 해당 전략의 의미 계약에 수록된 항목과 일치, 엔진·세부 항목의 조건 개수 일치(`consistency.ok`)일 때만 `semantic_condition_evidence`를 생성한다.
- 하나라도 충족하지 못하면 보조 의미 신원은 사용하지 않고 `LOCAL_INCOMPLETE`로 보류한다.

### 3. Prospective 저장 시 별도 재검증

- `backend/app/prospective/catalog.py`는 최종 Scanner result의 `strategy_selection_policy`를 candidate 보조 신원과 대조한다.
- 신원에 적힌 정책 ID·해시·선택 전략·현재 엔진 정의 해시와, 실제 조건 근거를 모두 재검증해야 의미 자료 생성용 **임시 복사본**에만 버전/해시를 채운다.
- 원본 Scanner 후보의 버전·해시는 None 그대로 저장된다. 전략·Risk·액션·순위·기간도 변경하지 않는다.
- 계약은 기존 V1/V2 `semantic_source` 형식 그대로 생성되며, 동결된 V4 프로젝터나 Canary 계약은 수정하지 않는다.
- 과거/캐시된 스냅샷에 보조 근거가 없다면 최신 엔진 정의를 억지로 뒤붙이지 않고 원래 `LOCAL_INCOMPLETE`로 남긴다.
- 변조·중복·누락된 근거는 불완전 상태로 분류하며 생성·저장 경로를 중단시키지 않는다.

### 4. 정확히 바뀌는 것은 의미 자료뿐

프로덕션 Scanner 후보의 `action`, `candidate_state`, `strategy`, `priority`, `rank`, `risk`, `entry_risk_guide`, 정책 참조·fallback 결정은 변경하지 않는다.

Jev 모델/가상 거래/시뮬레이션 평가·진입 가격·실시간 시세에는 아무 영향이 없다.

## 검증

- `backend/tests/test_jev_act1_s1_2_semantic_pipeline.py`: 실제 `_current_candidate()` → `ProspectiveCatalog._candidate_snapshot()` → 진짜 SQLite Prospective `finalize_capture()` 저장/재로드/해시/중복 판정까지 연결
- 실제 엔진 전략 신원 검증, 조건 한 건 실패·삭제·중복·조작, 정책 불일치, 기존 버전 신원 부분/불일치, 오래된 캐시 attestation 없음, WAIT 차단, LEGACY HORIZON 정식 V4 차단, 네트워크 차단 검사
- 기존 Python 3.11·3.14, Node 22, Windows Fresh Clone CI 완료 필요
- 실제 사용자 Runtime은 GitHub CI에서 접근 불가하므로 검증되지 않았다고 명시

## 사용자 PC에서 읽기 전용 원인 집계

```powershell
cd C:\TAEWOO\CapstonDesign\StockScope
git status --short
git pull --ff-only origin main
git log -1 --oneline
.\sync_local.ps1 -CheckOnly
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_s1_2_inputs.py
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py
```

구 분석 결과가 바뀌지 않는 것이 정상이다. 사용자의 새로운 Scanner 실행은 별도로 승인받고 계획해야 한다. 기존 입력을 바꾸지 않고 바로 의미 자료를 확정하려는 시도나 fallback 정책의 자동 활성화는 금지.

## 후속 판단

1. 원본 6건에서 실제 어떤 필드가 저장돼 있는지 집계 결과 확인
2. 합성/고정 입력을 사용한 통합 테스트에서 새로운 의미 자료 생성 성공 확인
3. 새 Scanner 기록에서 engine attestation과 의미 소스 확인
4. 여전히 미비하면 전략별 조건 어휘/배열과 정책 바인딩을 별도 계약 오류로 분리
5. 실제 Jev 호출은 현행 `LEGACY_UNSPECIFIED` 차단과 V4 Canary PASS 부재 때문에 **계속 HOLD**, 별도 승인 없는 유료 API 호출 없음

완료 정의는 코드+CI+현재 PC 읽기 전용 진단 검토이다. 실제 Scanner 새 캡처 검사는 별도 사용자 UAT 단계로 남는다.
