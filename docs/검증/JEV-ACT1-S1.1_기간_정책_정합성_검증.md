# JEV-ACT1-S1.1 — Scanner·Jev 기간 정책 정합성 검증

- 기준: S1 `68795d8`
- 범위: **읽기 전용 로컬 의미 진단의 범위 확장**; Jev V4 모델 호출 지원 범위는 확장하지 않음
- 사용자 PC 확인 근거: COMPLETE 캡처 2개, 후보 30개 중 `ENTRY_CANDIDATE+LEGACY_UNSPECIFIED` 21개, `WAIT+LEGACY_UNSPECIFIED` 9개 (S1 실행 당시)
- 사용자 PC의 새 S1.1 결과: **미실행·확인 대기**
- TypeSafe API, 모델 조회, 키 접근, DB 기록/재실행, Google Drive Runtime 동기화, Holdout 접촉: **0**

## 1. 문제 원인과 결정

Scanner UI `ScannerPanel.tsx`는 `horizon_intent`를 보내지 않는다. 서버 `resolve_horizon_context(None)`는 유효한 기본값 `LEGACY_UNSPECIFIED`를 기록한다. SHORT·MEDIUM을 명시하면 현재 `HORIZON_NUMERIC_POLICY_NOT_APPROVED` 때문에 실행 승인되지 않는다.

하지만 `typesafe_state_v4._validated_source()`는 `SHORT/MEDIUM`만 허용한다. 따라서 기존 21개 진입 후보는 전략 의미 관계를 판단하기도 전에 기간 가드에서 제외됐다. WAIT 후보 9개는 처음부터 AI 진입 검토 대상이 아니다.

**선택:** 기간 미지정 저장 자료에 대한 *오프라인 로컬 의미 검사*만 확장한다. 현재 Scanner 기간 정책, 모델 프로젝터, V4 Canary 프로토콜, 해시, 실제 AI 제공자 라우팅은 변경하지 않는다. LEGACY를 SHORT로 바꾸거나 미정 정책에 수치를 채우지 않는다.

## 2. 코드 근거 — 의미 검사와 기간 의존성

- `backend/app/strategy/semantic_source_v2.py`: 저장된 전략 의미, 조건 assertion, authored relation, 로컬 composition을 만드는 과정에 horizon 입력 없음
- `backend/app/strategy/semantic_composition.py`: 각 의미 관계의 SUPPORTS/WEAKENS/CONTRADICTS 등 stance를 평가하며 시간대 계산이나 주가 재산정이 없음
- `backend/app/jev/typesafe_state_v4.py`: 실제 V4 제공자 라우트는 별도 가드로 action=ENTRY_CANDIDATE, horizon=SHORT/MEDIUM만 허용
- `backend/app/horizon.py`: LEGACY는 정상 기본 문맥이지만 기간 수치 정책 미승인 상태이며, 과거 기록 backfill 금지

**이 사실은 로컬 의미 검사가 가능하다는 코드 수준 근거일 뿐, 모든 전략이 투자 기간에 독립적이거나 실제 Jev provider 호출 범위를 넓혀도 안전하다는 증거는 아니다.** 실행 계약 확장은 별도 설계/새 검증·승인이 필요하다.

## 3. 구현

- `backend/app/jev/semantic_scope_diagnostic.py` 신설: 기존 V2 의미 소스의 계약 버전·해시/저장 snapshot hash, 로컬 composition 재검사, 저장 판단·reason·relation result 일치 여부를 확인. 조건이나 전략/목표가/위험도를 재계산하지 않음
- `tools/data/audit_jev_act1_readiness.py` 확장:
  - `ACTION_OUT_OF_SCOPE`: WAIT 등 진입 후보 아님
  - `LEGACY_HORIZON_BLOCKED`: 진입 후보지만 정식 Jev 모델 검사 범위 밖
  - `EXPLICIT_HORIZON_UNSUPPORTED`: LONG/기타 미지원 기간
  - `SEMANTIC_SOURCE_MISSING`, `SEMANTIC_SOURCE_INVALID`: 정식 검사 또는 로컬 검사 실패
  - `legacy_local_inspection`: 기간 미지정 진입 후보에 대한 로컬 결과 `LOCAL_MATCH/CONFLICT/INCOMPLETE/AMBIGUOUS/RESIDUAL_REVIEW_OBSERVED` 및 미비·무결성 상태를 중첩 집계
  - `provider_eligible`: 이전과 동일하게 **정식 SHORT/MEDIUM V4 검사를 통과한 후보만 카운트**; LEGACY 진단은 포함하지 않음
- `backend/app/jev/activation_readiness.py`: `HORIZON_SCOPE_COMPATIBILITY` HOLD 별도 추가; legacy residual 관측 시 `LEGACY_RESIDUAL_OBSERVED_PROVIDER_NOT_AUTHORIZED` 명시
- 회귀 테스트: 유효 자료, 손상 데이터, 21/9 분리, LEGACY 잔여 검사, 원본 DB 불변, 실제 V4 기간 차단 유지, 기존 SHORT 동작 유지, 호출 0

## 4. 집계 의미

기존 `v4_compatible` / `provider_eligible`는 **정식 V4 범위만** 뜻하며 의미와 수치를 변경하지 않는다.

신규 `legacy_local_inspection` 구조:

```json
{
  "total": 21,
  "inspectable": 0,
  "residual_observed": 0,
  "categories": {
    "LOCAL_MATCH": 0,
    "LOCAL_CONFLICT": 0,
    "LOCAL_INCOMPLETE": 0,
    "LOCAL_AMBIGUOUS": 0,
    "RESIDUAL_REVIEW_OBSERVED": 0,
    "SEMANTIC_SOURCE_MISSING": 0,
    "SEMANTIC_SOURCE_INVALID": 0
  },
  "provider_eligible": 0
}
```

위 값들은 **구조 설명용 샘플**이다. 합계 일치하는 실제 값은 반드시 PC에서 측정한다. 특별히 `RESIDUAL_REVIEW_OBSERVED`는 **로컬 후속 검토 필요성이 관측되었음을 뜻할 뿐, Jev 모델 호출 승인 또는 예측 정확도 향상이 아님**.

## 5. PC 검증 명령

현재 PC (`C:\TAEWOO\CapstonDesign\StockScope`):

```powershell
git status --short
git pull --ff-only origin main
git log -1 --oneline
.\sync_local.ps1 -CheckOnly
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py
```

추가로 시장/전략별 **익명 집계만** 출력하려면:

```powershell
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py --json
```

이 명령어는 SQLite `mode=ro`, `PRAGMA query_only=ON`으로만 SELECT한다. 후보 종목명·코드·원문 데이터·API 키는 출력하지 않는다. DB 스키마 호환이 안 맞거나 파일이 없다면 자동 복원·마이그레이션 없이 오류 처리한다.

## 6. 완료 및 이후 승인 조건

완료 판정 순서: 구현/CI 통과 → 현재 PC에서 21개 진입 후보의 진단 결과 확인 → 원인/빈도 정리 → 향후 개발 방향 결정.

만약 검사 대상 중 LOCAL_MATCH만 발견된다면 Jev 실제 연결을 서두를 근거가 없다. 잔여 의미 검토가 관측되더라도 **현재 V4가 LEGACY를 허용하지 않으므로** 모델 호출은 여전히 금지다.

V4 로컬/protocol 계약 변경, 실사용 AI feature ACTIVE, 실제 TypeSafe 호출·유료 비용, Holdout 접근은 이번 작업의 범위 밖이다. 기존 V4 동결된 `docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V4.json`을 수정하거나 재생성하지 않는다.
