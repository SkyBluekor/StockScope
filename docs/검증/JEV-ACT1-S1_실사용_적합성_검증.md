# JEV-ACT1-S1 — 실사용 적합성 및 활성화 사전검증

- 기준 커밋: `38f1121` (SC-UX4-S3)
- 목적: 실제 Prospective Scanner 저장 기록에서 V4 추가 의미 검토 대상이 존재하는지 **읽기 전용으로** 확인하고 활성화 차단 이유를 명시
- 이번 단계에서 허용되는 외부 호출: **0회** (모델 목록 조회 포함)
- 사용자 AI 검토: `DISABLED_VALIDATION_PENDING` 유지
- 기존 Scanner/Strategy/Risk/가격/보유/JEV-X1/X2/Runtime/자동 동기화: 변경 없음

## 지금까지 구현·검증된 것

- `backend/app/jev/typesafe_state_v4.py`: 로컬 의미 관계로 우선 처리하고 `RESIDUAL_SEMANTIC_REVIEW`가 필요할 때만 TypeSafe 모델 대상으로 분류
- `backend/app/jev/typesafe_canary_v4.py`: 18 synthetic fixture, 8개 unique provider wire × 5회 = 40 System One 호출을 **계획**한 동결 Canary 프로토콜
- `docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V4.json`: `FROZEN_BEFORE_REAL_CALLS`. **실제 실행 PASS 아님**
- `backend/app/jev/review_service.py`: Fake provider를 통한 경계·중복 방지 검증. 사용자 API는 현재 실제 provider를 만들지 않음
- `backend/app/api/jev.py`: `/review-feature`는 `available=false`, `DISABLED_VALIDATION_PENDING`
- 과거 V3 실험의 실패/증거는 보존. V4 성공으로 간주하지 않음

## 이번에 추가한 도구

1. `tools/data/audit_jev_act1_readiness.py`: `COMPLETE` 상태의 **저장된 canonical Prospective 캡처**와 그 안의 후보를 선택해 `sqlite3 mode=ro`, `PRAGMA query_only=ON`으로 집계. DB 생성, 마이그레이션, UPDATE/INSERT/DELETE, 모델 호출 없음.
2. `backend/app/jev/activation_readiness.py`: 저장된 V4 Canary freeze JSON을 런타임 생성물과 해시 대조. 활성화 전 반드시 남는 미확인 조건을 `HOLD`로 구분. 해시/계약 오류 시 `BLOCK`; S1 단계에서 제품 AI `ACTIVE`로 바꾸는 코드 없음.
3. `backend/tests/test_jev_act1_s1_readiness.py`: 정상 소스와 레거시, 범위 밖, 손상 JSON, 조회용 스키마 오류, 모델 필요 상태/와이어 변환 실패, DB 불변, 외부 네트워크 차단, Canary 증거가 없는 상태의 HOLD 등 테스트.

### 분류 기준

| 코드 | 일반적인 의미 |
|---|---|
| LOCAL_MATCH | 기존 전략 의미와 조건의 관계를 로컬에서 확인 |
| LOCAL_CONFLICT | 로컬에서 이미 의미적 충돌 판단 |
| LOCAL_INCOMPLETE | 필요한 설명·근거 부족 |
| LOCAL_AMBIGUOUS | 로컬에서 모호 |
| PROVIDER_ELIGIBLE | 로컬에서 닫히지 않은 추가 의미 판단 + 실제 최소 Jev 입력 구성 가능 |
| UNSUPPORTED_SCOPE | ENTRY_CANDIDATE, SHORT/MEDIUM 외의 범위 |
| LEGACY_SOURCE_MISSING | 과거 캡처에 V4 의미 소스 자체가 없는 경우 |
| INVALID_SEMANTIC_SOURCE | 해시/문맥/상태/구조 불일치 또는 잘못된 기록 |

**검사 가능**은 LOCAL_*와 PROVIDER_ELIGIBLE의 합이며, 실제 AI 추가 검토 대상은 PROVIDER_ELIGIBLE만이다.

## 사용자 PC 실행 (다른 PC 데이터는 합치지 않음)

사전 조건: 현재 코드 `main` 최신, `sync_local.ps1 -CheckOnly`가 `CURRENT`.

현재 PC의 PowerShell에서:

```powershell
cd C:\TAEWOO\CapstonDesign\StockScope
git status --short
git pull --ff-only origin main
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py
```

시장·전략별 전체 집계가 필요한 경우:

```powershell
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py --json
```

DB가 다른 위치에 있는 경우 `--simulation-db "C:\...\simulation.db"` 지정 가능. 입력 DB가 없거나 스키마가 호환되지 않으면 **자동 생성·마이그레이션하지 않고 실패**한다. 출력에는 개별 종목명·종목 코드·원본 스냅샷을 포함하지 않는다. **개발 서버 실행·KIS·Google Drive Runtime에 영향 없음.**

실제 PC 실행 결과가 나오기 전까지는 `PRODUCTION_REACHABILITY`가 `RUN_LOCAL_READONLY_AUDIT`인 HOLD로 남는다. 로컬 캡처에 provider 대상 0건이면 AI 효용을 임의로 꾸미지 않는다.

## 활성화 판단

| 검증 | S1에서 기대되는 판정 |
|---|---|
| 동결 V4 프로토콜·해시·fixture 정합성 | PASS, 실패 시 BLOCK |
| Canary 계획 호출 한도·비용 예약 상한 | PASS, 불일치 시 BLOCK |
| 실제 V4 Canary selection/validation 성공 증거 | HOLD |
| 최종 임계값/실제 응답 모델 바인딩 | HOLD |
| 최근 TypeSafe 가격·계정 조건 및 실제 비용 검증 | HOLD |
| 원본 종목 의미 데이터의 외부 전송 및 유료 요청 승인 | HOLD |
| 사용자 Jev 기능 활성화 | HOLD |
| 운영 데이터 추가 검토 후보의 실제 발생·효용 | HOLD (현재 PC 진단으로 증거 보강 가능) |

S1의 결과가 `HOLD`로 나오는 것은 테스트 실패가 아니라 **아직 외부 호출 승인 및 필수 검증이 없기 때문**이다. `HOLD`를 `PASS`로 강제 변경하는 코드나 환경 변수를 추가하지 않는다.

## S1 완료와 다음 단계

S1 완료는 다음을 의미한다: 진단 도구 추가, 자동 테스트·CI 통과, 실제 PC에서 읽기 전용 진단 실행 및 결과 검토. CI만 성공하고 사용자 PC 진단이 없으면 `사용자 데이터 기반 최종 판정 대기`.

S2는 별도 승인 후 **실제 V4 Canary 검증**이다. 기존 동결 프로토콜은 최대 40 System One 시도, 최대 1회 모델 목록 조회, retry=0, concurrency=1, 기존 2026-10-07 가격 근거와 예약 0.04 USD/절대 상한 0.25 USD로 설계되었지만 **현재 가격·계정 청구 조건을 재확인하기 전에는 호출 금지**. Canary PASS와 운영 사용 가치가 확보되지 않으면 S3(사용자 수동 검토 기능 제공)를 활성화할 수 없다.

**재검증할 사항:** 지원되는 현재 분석 기록의 실제 개수, `PROVIDER_ELIGIBLE` 도달 빈도, V4 의미 소스 버전 차이, 향후 보완 가치.

Holdout 파일이나 경로는 어떠한 방식으로도 탐색하지 않는다. API 키 값·길이·해시 및 Authorization 헤더를 읽거나 기록하지 않는다.
