# StockScope Next Task — Fresh-PC / Fresh-Clone Bootstrap

작성일: 2026-10-02 (Asia/Seoul)  
문서 상태: 다음 구현 작업 전달용 명세 작성 완료  
구현 상태: 미착수 — 선행 Google Drive 자동 handoff/transport 작업 COMPLETE 이후 착수  
권장 실행 모델: **6.1 Sol**  
권장 추론 수준: **High**

이 문서는 구현 요청과 검증 기준이다. 문서 작성 완료는 bootstrap 구현 완료를 의미하지 않는다. 이번 문서 작성 단계에서는 애플리케이션 코드, runtime, migration을 수정하거나 테스트를 실행하지 않는다.

## 1. 목표

완전히 새로운 사용자가 GitHub에서 StockScope를 clone하고 설치 절차 및 자신의 API 설정을 완료하면, 기존 사용자의 runtime DB, handoff bundle, 백업, Google Drive 연결 없이 정상적으로 첫 실행할 수 있게 한다.

사용자가 직접 폴더를 만들거나 SQLite를 실행하거나 migration 여러 개를 수동 실행하거나 다른 PC의 DB를 복사할 필요가 없어야 한다. Python, Node/npm, Git 등의 시스템 선행 설치는 설치 안내에 포함한다.

```text
GitHub clone → setup → API 설정 → 새 runtime/schema/default state 준비 → 앱 실행
```

API 설정을 setup 전에 완료하는 순서도 지원한다. 설정이 누락되어도 로컬 runtime 준비와 설정 안내가 가능해야 하며, 관련 기능을 사용할 때 필요한 설정을 명확히 알려야 한다.

## 2. Prerequisites / Start Conditions

**이 조건들은 실제 구현 착수 조건이다. 명세 문서 작성의 선행 조건이 아니다.**

선행 작업 이름: Google Drive 자동 handoff/transport  
선행 작업 최종 commit hash: `<GOOGLE_DRIVE_HANDOFF_COMPLETE_COMMIT_HASH>`  
선행 작업 완료 보고 / 검증 기록: `<GOOGLE_DRIVE_HANDOFF_COMPLETE_REPORT_PATH_OR_LINK>`  
이번 작업 구현 기준 commit hash: `<BOOTSTRAP_IMPLEMENTATION_BASE_COMMIT_HASH>`

실제 구현 담당자는 착수 전에 다음을 확인하고 placeholder를 채운다.

1. 선행 작업이 구현 → 테스트 → 회귀 검증 → **COMPLETE** 상태에 도달했다.
2. 최종 커밋과 완료 보고를 확보하고, 그 구현이 실제 작업 checkout에 포함되어 있다. 브랜치가 별도라면 포함 관계와 기준 브랜치를 확인한다.
3. 선행 작업의 로컬 handoff export/import 및 Google Drive transport 테스트가 PASS했다. 미해결 실패나 사용자 확인이 필요한 항목을 완료로 간주하지 않는다.
4. 현재 작업 트리와 실행 중인 애플리케이션/전달 작업을 확인한다. 다른 작업의 변경을 덮어쓰거나 진행 중인 transport를 중단하지 않는다.
5. 적용되는 저장소 작업 지침과 보호 대상 데이터 범위를 확인한다. 실제 사용자 runtime을 초기화 대상으로 사용하지 않는다.
6. 선행 작업에서 변경된 CLI, 경로 resolver, 설정, runtime 식별/계보, import 충돌 판정, startup 동작을 다시 읽고 이 명세의 초기 조사 내용을 갱신한다.

조건이 충족되지 않으면 **실제 구현만 대기**한다. 선행 구현이 현재 checkout에 없거나 최종 hash가 미정인 상태에서도 이 명세는 유효하다. 선행 Google Drive 작업을 이번 bootstrap 작업으로 대체하거나 중단하지 않는다.

## 3. 명세 작성 시점의 코드 근거

읽기 전용으로 확인한 기준 커밋: `249247342890d1df446cac5757f05f399d65362e`.

이 hash는 **문서 작성 시점의 참고 기준**이다. 선행 transport 완료 hash나 실제 구현 기준 hash가 아니다. 아래 내용은 구현 착수 시 최신 소스와 대조한다.

| 확인한 코드 | 현재 동작 / 구현 단계에서 해결할 사항 |
|---|---|
| `setup.ps1` | Python 환경과 backend/frontend 설치·검증 후 DATA.1 bootstrap/doctor를 호출한다. 기존 설치 책임을 재사용할 수 있다. 전체 backend 테스트를 설치 중 실행하는 구조의 fresh 환경 적합성도 확인한다. |
| `tools/data/bootstrap_runtime.py` | Holdings schema와 Holdings/Market/backup 디렉터리를 준비한다. Market DB는 생성하지 않으며 Simulation과 나머지 runtime의 완전한 첫 실행 준비를 담당하지 않는다. |
| `stockscope.ps1` | `status`, `sync`, `handoff`, `bootstrap`을 제공한다. 모든 명령 전에 `.venv` 존재를 요구하므로 새 `setup` 명령을 추가한다면 venv 생성 이전에도 진입할 수 있어야 한다. |
| `tools/runtime/cli.py` | 기본 bootstrap은 상태 조회이고, DB가 없으면 restore를 권한다. 새 Simulation 생성은 별도 flag/확인을 요구하고 기존 Holdings·Market DB를 검증한다. 완전 신규 설치의 진입점으로 그대로 쓰기 어렵다. |
| `tools/dev/sync_local.py` | 경로·migration 상태·의존성·write domain을 관리하며 NEXT-6E-S3도 등록되어 있다. 현재 planner/executor를 우선 재사용한다. |
| `backend/app/main.py` | lifespan에서 Prospective 정리, Watch 관찰·조정, quote transport를 시작한다. 빈 runtime과 API 미설정 환경의 실제 startup/shutdown을 검증해야 한다. |
| `backend/app/core/config.py`, `.env.example` | 프로젝트 루트 `.env`와 API 설정/default를 사용한다. 신규 설정을 생성할 때 기존 설정과 credential을 보존해야 한다. |
| `tools/runtime/handoff.py` | 선택적 domain export/import와 runtime continuity 상태를 관리한다. 새 runtime에 import할 때 lineage/conflict 판정을 깨뜨리지 않아야 한다. |

문서 작성 시점의 소스 확인은 fresh-install 테스트 PASS의 근거로 사용하지 않는다. 최종 판단은 실제 구현 기준 커밋에서 수행한 검증으로만 한다.

## 4. 기능 경계와 세 가지 실행 흐름

### A. 신규 사용자 / 새 프로젝트

```text
clone → setup → absent runtime 생성 → migrations CURRENT
      → 로컬 기본 상태 준비 → API 설정 확인 → 앱 실행
```

Google Drive credential, Drive 폴더, bundle, 이전 사용자의 DB 또는 계정은 필요하지 않다. restore를 내부적으로 호출하거나 임의 bundle을 만들지 않는다.

### B. 기존 사용자 / 새 PC

```text
clone → setup → 명시적 handoff/Drive restore
      → 복원된 runtime 검사 및 필요한 migration → 기존 이력으로 앱 실행
```

setup이 먼저 만든 빈 runtime 때문에 restore가 불필요한 충돌로 차단되어서는 안 된다. 반대로 setup 이후 사용자가 추가한 데이터는 “새 PC”라는 이유로 덮어쓰면 안 된다. 정상 상태 검사와 기존 import의 안전 규칙을 통해 두 경우를 구별한다.

### C. 기존 사용자 / 기존 PC

```text
pull → 기존 sync/migration/check → 기존 runtime과 이력 유지 → 앱 실행
```

새 setup을 기존 PC에서 반복 실행하더라도 동일하게 데이터를 보존해야 한다. 기존 데이터가 있다는 이유로 초기화하거나 신규 프로젝트로 재등록하지 않는다.

Bootstrap은 **로컬 설치와 새 runtime 준비**, Restore는 **기존 이력 복원**, Drive Sync/Transport는 **bundle 전달**을 담당한다. 신규 setup의 성공 여부를 Drive 연결 상태에 종속시키지 않는다.

## 5. 구현 전 필수 조사 산출물

현재 코드와 migration을 source of truth로 삼아 runtime inventory를 작성한다. 문서만 보고 DB를 추가하거나 seed를 추정하지 않는다. 각 항목에 실제 경로·환경 변수/alias·schema owner·version 검사·migration chain·선행 조건·default/seed 요구·검증 방법을 기록한다.

아래는 현재 확인된 조사 시작점이며 완전한 목록이라고 가정하지 않는다.

| 물리 저장소 / 영역 | 기본 위치 또는 소유 코드 | 준비 범위 |
|---|---|---|
| Holdings | `backend/runtime/holdings/holdings.db`; `backend/app/holdings/catalog.py` | 보유·계좌·관심종목·이벤트·분석 이력·management plan, 관련 analysis proof/input identity 확장 |
| Holdings Decision / Recovery / Watch | Holdings DB; 해당 catalog/storage 및 `tools/data/migrate_holdings_*`, `migrate_watch_*` | Decision, Recovery, Watch/observability schema 및 코드가 요구하는 기본 policy/state |
| Market history | `backend/runtime/market_history/market_history.db`; `backend/app/backtest/market_store.py` | 일별 시장/지수, completeness, integrity, input identity 등 실제 최신 schema |
| Legacy Simulation | `backend/runtime/simulation/simulation.db`; `backend/app/simulation/sim1_store.py` | SIM.1–SIM.3 schema, 메타데이터 및 안전한 version upgrade |
| Historical Validation / Execution | Simulation DB; `validation_catalog.py`, `execution_catalog.py` | 각각의 독립 schema family 및 의존 관계 |
| Feedback / Prospective | Simulation DB; 각 catalog와 VN-P2 migration | 빈 이력과 최신 schema, NEXT-6E-S3 reference extension |
| Strategy Governance / Event Evidence | Simulation DB; VN-P5/VN-P6 migration 및 소유 모듈 | governance/evidence schema; 평가·승인·과거 attachment를 임의 생성하지 않음 |
| Horizon Context / Selection Policy Pin | Holdings/Simulation 및 관련 VN-P1 migration | 실제 domain별 확장 및 version 검사 |
| Recommendation Tracking | `backend/runtime/tracking/recommendation_tracking.db`; `backend/app/tracking/store.py` | tracking schema와 빈 사용자 이력 |
| Macro | `backend/runtime/macro/macro.db`; `backend/app/macro/store.py` | 로컬 schema 및 필수 계약/default; 관측치·연구 이력은 별도 데이터 준비 상태 |
| Strategy Selection / Baseline | `backend/runtime/strategy_selection/`, `backend/runtime/baseline/`; production selection/baseline 코드 | Git 제공 artifact와 사용자 runtime을 구분하고 현재 코드 기본 정의의 사용 가능성 검증 |
| 로컬 캐시 / 운영 상태 | KRX, KIS, Scanner, quote/session 관련 소유 코드 | 실제 첫 사용에 필요한 디렉터리와 로컬 구조; API token과 사용자 identity를 seed로 복사하지 않음 |
| 설정 / continuity 상태 | 설정 코드, `tools/runtime/handoff.py`, 최신 transport 코드 | 기존 설정 보존, 새 runtime과 restore 대상의 구분, 경로 일치 |

특히 같은 Simulation DB 안의 여러 독립 schema family를 하나의 schema version으로 대체하지 않는다. DB 하나가 존재하거나 일부 테이블이 있다는 사실만으로 전체 runtime을 CURRENT로 판정하지 않는다.

Fresh 상태에서 CLI → 초기화 → migration → lifespan → 주요 API → frontend 경로를 따라가며 missing file/table/version, prerequisite, seed/default, 경로 불일치, 빈 응답 처리 실패를 목록화하고 해결한다.

## 6. 구현 범위와 Entry Point

사용자에게 설치 진입점 **하나**를 안내한다. 권장 인터페이스는 `./stockscope.ps1 setup`이며, 기존 설치 책임에 더 잘 맞으면 `./setup.ps1`을 canonical entry point로 유지할 수 있다. 실제 선택과 이유를 구현 보고에 기록한다. 기존 명령 호환성을 유지한다.

순서는 다음과 같다.

1. Python 최소 버전, Node/npm, 설치 경로 및 쓰기 가능 여부를 확인한다. dependency가 없으면 정확한 설치 안내와 실패 단계·종료 상태를 제공한다.
2. 기존 installer를 재사용해 venv/backend/frontend dependency를 설치 또는 확인한다. secret이나 runtime을 dependency 재설치 대상으로 취급하지 않는다.
3. `.env`가 없으면 추적 중인 예제의 키 이름과 공개 기본값만으로 안내 파일을 준비할 수 있다. API 키는 비워 두며 임의 credential을 만들지 않는다. 기존 `.env`는 덮어쓰지 않는다.
4. 앱, migration, status, backup, handoff가 같은 실제 runtime 경로를 사용하도록 확인한다. 환경 변수/alias 충돌은 조용히 다른 DB를 선택하지 말고 명확히 처리한다.
5. 필요한 디렉터리와 **없는 DB의 실제 base schema**를 owner 코드로 생성한다. `touch` 또는 빈 SQLite 파일 생성만으로 끝내지 않는다.
6. base schema → 독립 schema family → dependency-aware migration을 적용해 코드가 요구하는 최신 상태에 도달한다.
7. 필요한 default/configuration/state를 추가하고 DB integrity, foreign key, schema family/version 및 readiness를 검증한다.
8. 앱이 실행 가능한 상태, API 설정 상태, 시장 데이터 준비 상태를 각각 출력한다.

기존 initializer/migration/planner 재사용 → entry point 보완 → fresh-start 호환성 수정 → 최소 helper 추가 순으로 구현한다. migration SQL을 별도 bootstrap에 복제하지 않는다. 기존 `sync_local`을 첫 실행 설치 명령으로 강제 재설계하지 않는다.

## 7. 데이터와 안전성 계약

### 신규 기본 상태

- Holdings: 0 positions, 사용자 거래·보유 이력 없음. schema상 필수 기본 계좌/설정 행이 필요하면 코드 정의를 기준으로 생성하고 목적을 기록한다.
- Tracking: 0 items. Feedback/Recovery: empty. Simulation/Validation/Execution: 사용자 run/history 없음.
- Prospective/Event Evidence: 과거 sample, prediction, capture, attachment를 생성하지 않는다.
- Settings: 현재 코드의 정상 기본값. Strategy: 코드 제공 definition/default reference 사용 가능; bootstrap을 이유로 promotion/demotion, custom active policy 변경, 새로운 승인 이력을 만들지 않는다.
- Macro/시장 데이터: 관측치나 가격을 더미 seed로 채우지 않는다. 미준비 상태와 준비 방법을 제공한다.

### Idempotency와 기존 사용자 보호

- 반복 실행은 이미 준비된 항목을 PASS/CURRENT로 처리한다. holdings, simulation 결과, tracking, feedback, governance, recovery와 settings를 삭제·재생성하지 않는다.
- 기존 지원 version은 기존 migration으로 upgrade한다. 코드보다 높은 version이나 알 수 없는/손상된 구조를 현재 version으로 덮어쓰지 않는다.
- 부분 schema, 손상 DB, expected-but-missing durable domain과 정상 신규 부재를 구분한다. 기존 프로젝트에서 사라진 history를 자동으로 새 history로 대체하지 않는다.
- 해당 DB와 무관한 domain을 초기화하거나 lineage/identity를 새로 쓰지 않는다. 신규 setup의 의도는 명확히 하되 정상 fresh 설치에 여러 DB 생성 확인 절차를 요구하지 않는다.
- 기존 DB를 변경하는 migration은 기존 backup/maintenance 경로를 재사용하고 실제 write set 전체를 보호한다. 실행 중 writer/transport와 충돌하면 명확히 대기/중단한다.
- 중간 실패 시 완료된 항목과 실패 단계를 알려준다. 지원되는 재실행으로 이어갈 수 있어야 하며, 실패한 초기화를 READY로 보고하지 않는다.
- DB, `.env`, token, credential, 사용자 history를 Git에 추가하지 않는다. credential 값은 출력·로그·API 응답에 노출하지 않는다.

### Bootstrap 이후 Restore

선행 구현의 lineage/conflict 정책을 읽은 뒤 **정상적으로 비어 있는 bootstrap 대상**에 기존 bundle을 import할 수 있는지 확인한다. 초기 metadata/default 행과 실제 사용자 데이터를 구분하되 단순 row count 또는 파일 존재만으로 덮어쓰기 허용을 판단하지 않는다.

필요한 호환성 수정은 이 새 대상의 표현과 기존 import 계약에 한정한다. divergence, destination-newer, unknown history, domain 선택, pre-restore backup 등의 기존 보호를 완화하지 않는다. restore 완료 후 다시 setup/sync를 실행해도 복원 history와 effective policy가 유지되어야 한다.

## 8. Market Data / API / UX 정책

기본 구현 방향은 **B: DB/schema를 준비하고 UI에 데이터 준비 필요 상태를 명확히 표시**하는 것이다. 현재 코드와 기능 요구를 조사한 뒤 A 또는 C가 더 적절하면 근거·수집 범위·실패/재시도 정책을 기록한다. 다른 사용자의 Market DB 복사는 어떤 정책에서도 사용하지 않는다.

Schema readiness와 데이터 coverage/freshness를 별도로 판정한다. 빈 Market DB는 정상 신규 상태이며 “시장 데이터 확보 완료”라고 표시해서는 안 된다. 사용자에게 기존 데이터 준비/refresh 기능의 명확한 다음 행동을 제공한다. 첫 종목 조회나 분석에 필요한 준비는 일반 앱 흐름으로 수행하며 수동 DB 작업을 요구하지 않는다.

API 필수/선택 여부는 최신 provider와 기능 경로를 기준으로 확인한다. 현재 `.env.example`의 KRX, DART, KIS, NAVER, FRED 등을 모두 전역 필수로 강제하지 않는다. credential 없는 기능은 어떤 설정이 필요한지 표시하고, health 및 빈 holdings/history 조회와 로컬 앱 기동은 가능해야 한다.

권장 출력 상태는 다음과 같으며 기존 CLI 스타일에 맞춘다.

```text
STOCKSCOPE SETUP
Environment             PASS
Python                  PASS
Frontend                PASS
Runtime directories     CREATED / PASS
Holdings database       CREATED / CURRENT
Simulation database     CREATED / CURRENT
Market schema           CREATED / CURRENT
Runtime migrations      CURRENT
Configuration           PASS / ACTION_REQUIRED
Market data             READY / DATA_REQUIRED
Application             READY
```

Configuration이 부족하면 `SETUP COMPLETE — API SETTINGS REQUIRED`처럼 정확한 상태를 출력한다. `READY`가 로컬 앱 기동 준비를 뜻하는지 데이터 의존 기능까지 준비됐다는 뜻인지 명확히 구분한다. bootstrap/schema 실패는 실패 종료 상태를 반환한다. 설정/데이터 미준비 상태의 종료 규칙도 문서와 테스트에 고정하고 stack trace만으로 안내하지 않는다.

Frontend는 빈 배열, 0개 history, default 설정과 DATA_REQUIRED를 정상 상태로 렌더링한다. 필요한 bootstrap 관련 빈 상태/안내만 보완하고 전체 UI를 재설계하지 않는다.

## 9. 실제 구현 단계의 검증 시나리오

**아래는 향후 실행할 테스트 요구사항이다. 이 명세 작성 단계에서는 실행하지 않는다.**

격리된 fresh checkout 또는 그에 준하는 임시 workspace에서 수행한다. 로컬 `.venv`, node_modules, runtime, `.env`, backup, credential cache가 우연히 성공을 돕지 않도록 초기 조건을 명시한다. 사용자 runtime이나 다른 PC 데이터는 테스트 fixture로 직접 변경하지 않는다.

| ID | 시나리오와 절차 | PASS 기준 / 남길 증거 |
|---|---|---|
| A | runtime/DB/handoff/backup/Drive 설정이 전혀 없는 설치에서 canonical setup 실행 | 필요한 directory와 DB 생성, 모든 필수 schema family·migration CURRENT, 필요한 default 존재, integrity/FK 검증 통과. CLI 결과와 resolved path 기록 |
| B | A 직후 setup을 2회 이상 다시 실행 | PASS/CURRENT, business row·metadata identity·schema version 보존, default 중복 없음, 오류 없음 |
| C | 현재 정상 runtime의 안전한 snapshot/copy 또는 대표 기존 데이터 fixture에서 setup 실행 | holdings/trades/simulation runs/tracking/governance/recovery/settings 보존. 논리 데이터·참조·version 비교; 앱 startup의 정상 bookkeeping 변경은 삭제/손실과 구분 |
| D | fresh setup → 기존 bundle import → setup/sync → 앱 실행 | 기존 이력 정상 복원. 빈 bootstrap 대상의 불필요한 conflict 없음. domain 선택과 effective policy 보존 |
| D2 | setup 이후 실제 사용자 데이터를 추가한 대상에 충돌/이전 lineage bundle import 시도 | 기존 import 보호 적용, 조용한 overwrite/rollback 없음. 양쪽 데이터 보존 |
| E | Drive credential·sync 설정·remote session이 없는 환경에서 A/B/startup 수행 | bootstrap와 기본 앱 실행 가능. Drive client/token/config/file 접근 및 네트워크 호출 없음. Google Drive 코드 사용을 막는 fixture로 숨은 의존성 검증 |
| F | API credential 없는 환경에서 setup/startup와 로컬 빈 상태 API 조회 | 프로그램 전체 crash 없음, 설정 항목과 다음 행동 안내, secret 노출 없음 |
| G | 자신의 유효 API 설정 또는 결정적인 provider stub을 적용한 fresh 설치에서 정상 시장 준비/종목 조회 흐름 수행 | DB 수동 조작 없이 필요한 데이터 확보/분석 경로 도달. schema 성공과 데이터 coverage/freshness를 구분 |
| H | 실제 FastAPI lifespan/startup/shutdown과 frontend를 빈 runtime에서 실행 | 빈 holdings/tracking/simulation/history 및 설정 관련 주요 API가 정상 응답. UI empty/data-required 상태 표시, 콘솔·backend에 missing table 오류 없음 |
| I | 구 version의 지원 DB에서 최신 migration 실행; 대표 dependency chain을 빈 DB에서도 실행 | 지원 upgrade와 EMPTY→CURRENT 모두 통과. family별 version 검사, 기존 row 보존 |
| J | 손상 DB, 부분 schema, 미래 version, 읽기/쓰기 불가 path, alias 충돌, expected domain 유실, 중간 초기화 실패 | 명확한 상태/오류 및 지원되는 재시도 안내. 데이터 재생성·schema downgrade·거짓 READY 없음 |
| K | runtime 경로 override를 적용하고 setup → startup → status → handoff 경로 확인 | 모든 경로 일치, 기본 실제 사용자 runtime에 쓰기 없음 |
| L | 신규 setup 및 기존 sync 중 반복 실행·활성 writer/transport 상황 확인 | 기존 maintenance 규칙 준수, 실행 중 데이터 손상·중복 초기화 없음 |

G의 stub 통과는 schema/사용 흐름 검증 근거이지 실제 외부 API 접속 성공의 근거가 아니다. 실서비스 credential 검증이 불가능하면 별도 한계로 보고한다. 실제 credential 값이나 provider 개인 응답은 테스트 결과에 포함하지 않는다.

Fresh 테스트는 공통 DB validator 하나의 PASS로 끝내지 않는다. 예를 들어 Simulation의 한 schema family가 있으면 성공하는 legacy 검증만으로 Validation/Execution/Governance/Event Evidence까지 CURRENT라고 주장하지 않는다.

## 10. 회귀 검증 범위

구현 기준 commit에서 최신 테스트 목록을 확인하고 아래 영역을 실행한다. 테스트 이름이나 경로가 변경됐으면 실제 최신 항목으로 대체하며 정확한 command/result를 기록한다.

- Runtime planner/migration, DATA.1 bootstrap/doctor/backup/restore, `sync_local`과 기존 설치·실행 script 계약.
- 로컬 handoff export/import, domain 선택, completed manifest/hash 검증, lineage/fast-forward/divergence 및 rollback/복구 보호.
- **선행 작업에서 추가한 Google Drive 자동 handoff/transport 테스트 전체**. 실제 등록된 테스트 경로는 착수 시 `<GOOGLE_DRIVE_TRANSPORT_REGRESSION_TEST_PATHS>`를 채운다.
- Holdings/decision/recovery/watch, Tracking, Simulation SIM.1–SIM.3, Validation/Execution, Feedback/Prospective, Strategy Governance/Selection Policy, Event Evidence 및 NEXT-6E-S3.
- Backend startup/health/provider configuration, 관련 API 응답과 empty state.
- Frontend 기존 source/behavior 검증 및 `npm run build`; fresh empty/data-required UI 확인.

관련 실패는 수정하고 재검증한다. 기존 무관한 실패는 baseline·재현 조건·영향을 분리해 보고한다. 관련 검증 실패 또는 핵심 acceptance 미검증 상태를 COMPLETE로 처리하지 않는다. 테스트 실행 범위와 외부 API/Drive 실접속 여부를 정확히 구분한다.

## 11. 예상 변경 파일과 제외 범위

실제 수정 대상은 착수 조사 결과에 따라 최소화한다.

- 설치 진입점: `stockscope.ps1`, `setup.ps1` 중 canonical 설치 책임에 필요한 파일.
- bootstrap: `tools/data/bootstrap_runtime.py` 보완 또는 `tools/runtime/`의 최소 orchestrator/helper.
- 경로/검증/migration: 기존 common/planner와 fresh-start에 문제가 확인된 owner/migration만 수정.
- startup/API/frontend: 빈 상태 및 설정/데이터 미준비 안내에 필요한 부분만 수정.
- 테스트: fresh setup·반복·preservation·restore·Drive 독립성·startup 및 확인된 회귀에 필요한 tests.
- 문서: README/설치 안내에 신규 사용자와 기존 사용자 새 PC 복원을 각각 명시.

제외: Google Drive 기능 확장, 새로운 remote 동기화 프로토콜, DB 통합/분리, 전면 아키텍처 재작성, 전략/랭킹/Risk Gate 변경, 과거 evidence backfill, 사용자 DB/기본 runtime DB commit, secret 자동 생성, 실사용 데이터 삭제·복사·초기화.

## 12. 구현 후 설치 문서에 반영할 내용

새 사용자 안내는 다음 수준에서 끝나야 한다.

```text
1. GitHub clone
2. 안내된 setup 명령 실행
3. 자신의 API 설정 입력
4. StockScope 실행
5. 데이터가 필요하면 앱의 데이터 준비 안내 사용
```

기존 사용자 새 PC 이동은 별도 절차로 안내한다.

```text
1. GitHub clone
2. setup
3. 명시적으로 handoff 또는 Google Drive restore
4. 필요한 migration/check 확인
5. StockScope 실행
```

기존 PC의 pull/sync 경로, 반복 setup의 데이터 보존, API 누락 안내, Market schema와 data readiness 차이도 함께 명시한다. 문서의 명령은 최종 구현에서 실제 검증한 이름·순서와 일치해야 한다.

## 13. Acceptance Criteria

- [ ] 선행 Google Drive 자동 handoff/transport가 COMPLETE이며 최종 commit/report가 확인되었다.
- [ ] 완전히 빈 runtime에서 동작하는 canonical setup/독립 bootstrap이 존재한다.
- [ ] 제3자가 이전 사용자의 DB·bundle·Drive 없이 GitHub clone과 자신의 API 설정 및 안내된 설치 절차로 첫 실행할 수 있다.
- [ ] Python/frontend dependency 및 configuration 상태를 확인하고 필요한 runtime directory를 자동 생성한다.
- [ ] 필요한 DB의 실제 base schema와 모든 필수 schema family/default를 자동 준비한다.
- [ ] EMPTY→CURRENT migration과 지원 기존 DB upgrade가 모두 검증되었다.
- [ ] 반복 setup은 사용자 데이터·identity·설정을 보존하고 downgrade하지 않는다.
- [ ] 손상/부분/미래 schema와 기존 history 유실을 신규 설치로 오판하지 않는다.
- [ ] Google Drive 설정 없는 bootstrap·기본 앱 실행·빈 상태 조회가 검증되었다.
- [ ] Market schema 준비와 데이터 준비를 구분하며 필요한 정상 데이터 준비 경로를 제공한다.
- [ ] API 미설정 시 로컬 앱이 시작되고 필요한 설정을 명확히 안내한다.
- [ ] 빈 holdings/tracking/history를 backend와 frontend가 정상 처리한다.
- [ ] fresh setup 이후 기존 상태 restore가 가능하고, 사용자 데이터가 있는 대상의 import 보호는 유지된다.
- [ ] holdings/simulation/tracking/governance/recovery 등 기존 runtime과 effective policy가 보존된다.
- [ ] handoff export/import, Drive transport, migration/sync, backend와 frontend 관련 회귀 테스트가 PASS한다.
- [ ] 설치 문서는 최종 구현과 일치하며 신규 설치·복원·기존 PC upgrade를 구분한다.
- [ ] 사용자 DB·secret이 저장소에 추가되지 않았고 변경 범위가 목적에 한정된다.
- [ ] 최종 보고에 기준/결과 commit, 실행 검증과 한계, 아래 YES/NO 답변이 포함된다.

모든 필수 기준을 만족한 경우만 COMPLETE다. 현재 문서 작성만으로 이 checklist를 체크하지 않는다.

## 14. 실제 구현 작업 완료 보고 형식

```text
STOCKSCOPE FRESH CLONE BOOTSTRAP

Status:
COMPLETE / PARTIAL / BLOCKED

Prerequisites:
- Google Drive handoff/transport COMPLETE commit: <hash>
- Implementation base commit: <hash>

Implemented:
- 선택한 entry point, 초기화/migration/default state 및 Market 정책

Fresh Clone Test:
- 초기 조건, 검증한 schema families, startup/API/UI 결과

Existing Runtime Test:
- 보존 비교, 반복 실행 및 지원 upgrade 결과

No Google Drive Test:
- credential/config/network 차단 조건과 기본 실행 결과

Handoff Regression:
- fresh setup 후 restore, conflict 보호, export/import 및 Drive transport 결과

Files Changed:
- 실제 변경 목록

Tests:
- 실행 command, PASS/FAIL 수, 미실행 항목과 baseline 실패 구분

Known Limitations:
- API 실접속 여부, 시장 데이터 coverage, 남은 조건

Commit:
- 실제 구현 commit hash 또는 미커밋 상태

Final Answer:
YES 또는 NO + 남은 이유
```

마지막 질문에 실제 검증 결과를 근거로 명확하게 답한다.

> 현재 StockScope repository를 처음 받는 제3자가 자신의 API credential만 설정하고 안내된 설치 절차를 따르면, 이태우의 Google Drive / runtime DB / handoff 파일 없이 StockScope를 정상적으로 시작할 수 있는가?

답변의 YES에는 기본 앱 startup과 신규 empty state, 수동 DB 작업 없는 필수 schema/migration 준비가 포함되어야 한다. 시장 데이터 준비나 외부 API 실접속의 범위·한계는 별도로 명시한다. 필요한 검증이 남아 있다면 NO와 남은 이유를 기록한다.

## 15. 다음 구현 담당자 전달문

선행 Google Drive 자동 handoff/transport가 COMPLETE인 것을 확인한 뒤 이 명세의 Start Conditions를 채우고 구현을 시작한다. 권장 실행 모델은 6.1 Sol, 추론 수준은 High다. 신규 사용자 bootstrap을 restore/Drive sync와 분리하고, 현재 코드 및 migration inventory를 갱신한 뒤 기존 initializer/planner를 최대한 재사용한다. 격리된 fresh 설치, 반복 실행, 기존 이력 보존, setup 이후 restore와 No Google Drive 시나리오를 검증하고 관련 회귀까지 PASS시킨다. 모든 acceptance criterion 충족 전에는 COMPLETE를 선언하지 않는다.
