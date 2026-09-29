# StockScope DATA.1 Runtime Tools

이 도구들은 StockScope의 사용자 원장과 Market Store를 분리해서 관리합니다.

## 데이터 분류

- `backend/runtime/holdings/holdings.db`: 사용자 핵심 상태. 기본 백업 대상.
- `backend/runtime/market_history/market_history.db`: 재수집 가능한 시장 데이터. `--include-market`일 때만 백업.
- `backend/runtime/simulation/simulation.db`: 존재하면 기본 백업에 자동 포함. Validation/Feedback/Prospective 평가 상태를 보존.
- `backend/runtime/tracking/recommendation_tracking.db`: 존재하면 기본 백업에 자동 포함. Tracking 원본 owner는 그대로 유지.
- `backend/runtime/macro/macro.db`: NEXT-6A Local Macro Store. 존재하면 기본 백업에 자동 포함하며 Market Store와 분리 유지.
- `.env`, KRX/KIS/DART/FRED 키, 인증 정보: 백업 대상 아님.
- `market_history.db`와 `holdings.db`는 cleanup 과정에서 자동 삭제하지 않습니다.

## 새 PC

```powershell
.\setup.ps1
```

`setup.ps1`은 Python/Node 의존성을 설치하고 Holdings DB schema를 초기화한 뒤 Data Doctor를 실행합니다. 시장 데이터는 자동 대량 다운로드하지 않습니다.

기존 사용자 데이터를 옮기는 경우:

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_...
.\.venv\Scripts\python.exe .\tools\data\doctor.py --verbose
```

필요한 시장 데이터가 부족할 때만:

```powershell
.\.venv\Scripts\python.exe .\tools\data\prepare.py
```

초기 PC처럼 요청량이 큰 경우 준비 계획만 표시하고 차단될 수 있습니다. 확인 후:

```powershell
.\.venv\Scripts\python.exe .\tools\data\prepare.py --allow-large
```

## 상태 검사

```powershell
.\.venv\Scripts\python.exe .\tools\data\doctor.py
.\.venv\Scripts\python.exe .\tools\data\doctor.py --verbose
```

Doctor는 SQLite를 read-only mode로 열며 네트워크 요청, 다운로드, 분석 실행, DB migration을 하지 않습니다.

상태 기준은 Production Scanner의 `MIN_HISTORY_ROWS`와 `FAST_HISTORY_CALENDAR_DAYS`, 그리고 HOLD 차트의 최대 range 요구량을 코드에서 직접 읽습니다.

## 빠른 백업

```powershell
.\.venv\Scripts\python.exe .\tools\data\backup_runtime.py
```

기본 백업은 `holdings.db`를 필수로 포함하고, 존재하는 `simulation.db`, `recommendation_tracking.db`, `macro.db`를 자동 포함합니다. Market Store는 재수집 가능 데이터이므로 기본 제외입니다. Macro Store에는 revision/vintage/PIT 재현 정보가 있으므로 단순 재수집 가능 캐시로 취급하지 않습니다.

## 전체 데이터 백업

```powershell
.\.venv\Scripts\python.exe .\tools\data\backup_runtime.py --include-market
```

Market Store까지 SQLite backup API로 snapshot합니다.

## NEXT-6A-S1 Macro Store 준비

NEXT-6A-S1은 실 FRED/KIS 호출 없이 Macro series/time/vintage/identity와 별도 Local Macro Store의 저장 계약만 준비합니다. 조회 경로는 schema 생성, migration, backfill, provider 호출을 수행하지 않습니다.

명시적으로 한 번 실행합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\migrate_macro_next6a_s1.py
```

기본 경로는 `backend/runtime/macro/macro.db`이며 `STOCKSCOPE_MACRO_DB`로 별도 경로를 지정할 수 있습니다. Migration은 schema만 준비하고 historical backfill과 외부 network request를 수행하지 않습니다.

Macro Store가 존재하면 기본 DATA.1 backup에 포함됩니다. 제외가 필요한 경우에만:

```powershell
.\.venv\Scripts\python.exe .\tools\data\backup_runtime.py --exclude-macro
```

복원은 명시적으로 요청합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_... --restore-macro
```

## NEXT-6A-S2 Provider capability / bounded live ingestion

S2부터 외부 provider 호출이 허용되지만 **명시적 CLI에서만** 수행합니다. Scanner/API/reader가 FRED/KIS를 자동 호출하지 않습니다.

FRED는 프로젝트 루트 `.env`의 `FRED_API_KEY`를 backend에서만 읽습니다. 키를 로그, report, DB, hash, GitHub에 저장하지 않습니다.

Capability probe:

```powershell
.\.venv\Scripts\python.exe .\tools\data\macro_capability_next6a_s2.py --provider FRED
.\.venv\Scripts\python.exe .\tools\data\macro_capability_next6a_s2.py --provider KIS
```

KIS 해외지수 기본 probe code `.DJI`는 공식 KIS 예제에서 확인된 값입니다. 환율/국채 코드는 추측하지 않으며 공식 master/example에서 확인한 값을 명시적으로 전달할 때만 probe합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\macro_capability_next6a_s2.py --provider KIS --kis-fx-code <OFFICIAL_CODE> --kis-treasury-code <OFFICIAL_CODE>
```

DGS10 bounded collection은 `--start`/`--end`를 반드시 지정합니다. `--check-only`는 network와 DB write 모두 0입니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\collect_macro_next6a_s2.py --provider FRED --series DGS10 --start 2026-09-01 --end 2026-09-28 --check-only
.\.venv\Scripts\python.exe .\tools\data\collect_macro_next6a_s2.py --provider FRED --series DGS10 --start 2026-09-01 --end 2026-09-28
```

Historical FRED backfill은 provider의 날짜 단위 vintage를 정확한 장중 availability로 승격하지 않습니다. 저장된 row는 `DATE_ONLY`이며 reference 조회는 가능하지만 엄격한 PIT historical evaluation에는 부적격입니다. 실제 수집 성공은 DGS10을 research owner로만 승인하며 Production decision scope를 활성화하지 않습니다.

## NEXT-6B-S1 Deterministic Macro Context

NEXT-6B-S1은 Local Macro Store만 읽어 versioned Macro Context와 feature를 생성합니다. Provider network, backfill, DB write, Scanner/Strategy/Risk 변경을 수행하지 않습니다.

현재 DGS10 feature:

- `rate_level_pct`
- `delta_bp_1obs`
- `delta_bp_5obs`
- `delta_bp_10obs`

`obs`는 calendar day가 아니라 사용 가능한 observation 거리입니다. DATE_ONLY FRED backfill은 `reference` usage에서 설명용으로 사용할 수 있지만 `historical` usage에서는 엄격한 PIT 평가 입력으로 사용할 수 없습니다.

Reference Shadow 예시:

```powershell
.\.venv\Scripts\python.exe .\tools\data\build_macro_context_next6b_s1.py --cutoff 2026-09-29T21:00:00+09:00 --usage reference
```

Historical Evaluation 예시:

```powershell
.\.venv\Scripts\python.exe .\tools\data\build_macro_context_next6b_s1.py --cutoff 2026-09-28T15:30:00+09:00 --usage historical
```

S1에서는 shock threshold/calibration을 실행하지 않습니다. DGS10 feature가 준비돼도 `RATE_SPIKE` 상태는 `UNCALIBRATED`이며 `NORMAL` 또는 `DETECTED`로 자동 분류하지 않습니다. immutable JSON 산출물이 필요할 때만 `--write-artifact`를 사용합니다.

## NEXT-6B-S2 Calibration research dataset / protocol freeze

NEXT-6B-S2는 fixed-vintage DGS10 archive를 **REFERENCE_RESEARCH_ONLY**로 읽어 Development/Holdout feature dataset을 준비합니다. 분석 중 provider network와 Macro DB write는 0입니다.

먼저 로컬 Macro Store에 어떤 DGS10 vintage/range가 준비되어 있는지 확인합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\inspect_macro_calibration_next6b_s2.py
```

필요한 vintage/range가 없으면 기존 explicit FRED collector로 먼저 준비합니다. Calibration dataset builder가 FRED를 자동 호출하지 않습니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\collect_macro_next6a_s2.py --provider FRED --series DGS10 --start <START> --end <END> --as-of <VINTAGE>
```

Development/Holdout은 chronology가 겹치면 거부됩니다. 각 dataset은 정확히 하나의 `vintage_id`에 pin되며 S1 feature contract(`rate_level_pct`, `delta_bp_1obs`, `delta_bp_5obs`, `delta_bp_10obs`)를 재사용합니다. 최대 feature distance에서 파생된 warm-up observation은 feature 계산에만 사용하고 sample count에는 포함하지 않습니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\prepare_macro_calibration_next6b_s2.py `
  --development-start <DATE> `
  --development-end <DATE> `
  --development-vintage <DATE> `
  --holdout-start <DATE> `
  --holdout-end <DATE> `
  --holdout-vintage <DATE>
```

확인 후 immutable runtime artifact가 필요할 때만 `--write-artifacts`를 추가합니다. 파일은 `backend/runtime/macro/calibration` 아래에 저장되고 Git 대상이 아닙니다.

S2는 threshold, minimum sample, episode policy를 결정하지 않습니다. Holdout은 calibration candidate freeze 전까지 잠긴 상태이며 `RATE_SPIKE`는 계속 `UNCALIBRATED`입니다. DATE_ONLY archive는 연구용 분포 준비에는 사용할 수 있지만 Historical PIT 평가 입력으로 승격하지 않습니다.

## NEXT-6B-S3 Development Distribution Research
### 개발 구간 금리 변화 분포 분석

NEXT-6B-S3는 S2에서 고정한 **Development artifact만** 읽어 DGS10 금리 수준/변화 분포를 조사합니다. Holdout 파일은 입력으로 받지 않으며 calibration threshold, minimum sample, rolling lookback, episode policy를 선택하지 않습니다.

분석 입력:

- `DEV-*.json`: Development feature dataset
- `PROTOCOL-*.json`: Holdout lock과 연구 경계를 고정한 protocol
- `HOLDOUT-*.json`: S3에서는 읽지 않음

분석 항목:

- 금리 수준과 1/5/10 observation 변화의 count/min/max/평균/중앙값/표준편차/MAD
- 상승/하락/절대 변화 tail profile
- 전체 empirical CDF
- 현재 시점보다 **이전 Development row만** 사용하는 expanding percentile
- 이전 Development row만 사용하는 MAD 기반 robust deviation
- 동일 규칙의 연도별 요약

실행 예시:

```powershell
.\.venv\Scripts\python.exe .\tools\data\research_macro_distribution_next6b_s3.py `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json
```

검증 후 full immutable research artifact가 필요할 때만 `--write-artifact`를 추가합니다. 결과는 `backend/runtime/macro/calibration/RESEARCH-<hash>.json`에 저장되며 Git 대상이 아닙니다.

S3 완료 후에도 `RATE_SPIKE`는 `UNCALIBRATED`입니다. `NORMAL`/`DETECTED` label은 생성하지 않으며 Holdout은 S4 calibration candidate freeze 전까지 잠긴 상태를 유지합니다. 분석 중 network request와 Macro DB write는 모두 0입니다.

## NEXT-6B-S4 Calibration Candidate Set Freeze
### 개발 데이터만으로 금리 충격 후보 규칙 집합 고정

NEXT-6B-S4는 S2 Development dataset, S2 Protocol, S3 Research artifact만 읽어 RATE_SPIKE 후보 집합을 고정합니다. Holdout artifact는 입력 옵션 자체가 없으며 S5 전까지 읽지 않습니다.

후보 생성은 사람이 임의의 bp/percentile/MAD 숫자를 코드에 입력하지 않고 Development에서 실제 관측된 breakpoint를 사용합니다.

- `EMPIRICAL_POSITIVE_TAIL`: 실제 양(+)의 bp 변화값
- `EXPANDING_POSITIVE_TAIL_FRACTION`: 각 시점 이전 Development 분포에서 실제 관측된 positive-tail fraction
- `EXPANDING_ROBUST_MAD`: 각 시점 이전 Development 분포에서 실제 관측된 양(+)의 MAD deviation

`rate_level_pct`는 RATE_SPIKE 후보에서 제외하고 `delta_bp_1obs`, `delta_bp_5obs`, `delta_bp_10obs`를 서로 합치지 않고 별도로 평가합니다.

후보 축소는 weighted score가 아니라 Pareto dominance를 사용합니다. 비교 목적은 희소성, 연도 coverage, episode separation, 단일 연도 집중도이며 다른 후보보다 모든 목적에서 나쁜 후보만 제거합니다.

Episode 정책은 `CONSECUTIVE_TRUE_RUN_V1`입니다. 관측 순서에서 TRUE가 연속되는 구간을 하나의 episode로 보고 gap tolerance는 0이며 episode 시작 시 한 번만 알림 가능한 구조로 고정합니다. calendar day 수를 임의로 넣지 않습니다.

Preview:

```powershell
.\.venv\Scripts\python.exe .\tools\data\freeze_macro_calibration_candidates_next6b_s4.py `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json `
  --research-artifact .\backend\runtime\macro\calibration\RESEARCH-cdd96e164e12017d.json
```

검증 후 `--write-artifact`를 추가하면 `backend/runtime/macro/calibration/CANDIDATES-<hash>.json`이 생성됩니다.

S4 완료 후에도 최종 candidate는 선택하지 않으며 `RATE_SPIKE`는 `UNCALIBRATED`입니다. `NORMAL`/`DETECTED` label, Scanner/Strategy/Risk/Holdings/Watch 변경, network request, Macro DB write는 모두 0입니다.

## P2-S2 실제 추천 평가 저장소 준비

P2-S2는 새 Scanner 실행부터 실제 추천 표본을 사후 선택 전에 보존합니다. 과거 Scanner 실행을 prospective 표본으로 소급 생성하지 않습니다.

명시적으로 한 번 실행합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\migrate_prospective_vnp2s2.py
```

조회/API import는 이 migration을 자동 실행하지 않습니다. Migration 전에도 기존 Scanner는 정상 동작하며 prospective 수집만 `NOT_READY` 상태입니다.

## P3-S1 보유 판단 저장소 준비

P3-S1은 기존 Holdings 원장과 적용 계획 위에 별도의 보유 판단/선택 이력을 추가합니다. 기존 Position, 거래 이벤트, 과거 관리 계획을 소급 변환하지 않습니다.

명시적으로 한 번 실행합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\migrate_holdings_decision_vnp3s1.py
```

조회/API import는 이 migration을 자동 실행하지 않습니다. Migration 전에도 기존 Holdings·원장·관리 계획 기능은 유지되며 새 보유 판단 기능만 `HOLD_DECISION_MIGRATION_REQUIRED` 상태입니다.

Decision, Resolution, Plan Context는 `holdings.db`에 저장되므로 기본 Holdings backup에 함께 포함됩니다. Manifest의 `holding_decision_v1` 항목은 해당 optional table family가 완전하고 복원 가능한지 별도로 기록합니다.

## P3-S2 Recovery 검토 저장소 준비

P3-S2는 기존 Position/원장/관리 계획을 바꾸지 않고, 같은 Position에 수동 Recovery 검토와 append-only assessment 이력을 추가합니다. P3-S1 migration이 선행되어야 하며, 과거 손실 Position을 자동으로 Recovery 상태로 backfill하지 않습니다.

Recovery review/assessment는 `holdings.db`의 사용자 기록이므로 DATA.1 기본 Holdings snapshot에 함께 포함됩니다. Backup manifest의 `extensions.holding_recovery_v1`이 세 Recovery 테이블과 schema version을 명시하며, restore 후에도 동일 review/assessment ID와 당시 snapshot을 보존합니다.

명시적으로 한 번 실행합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\migrate_holdings_recovery_vnp3s2.py
```

조회/API import는 이 migration을 자동 실행하지 않습니다. Migration 전에는 Recovery service가 `HOLD_RECOVERY_MIGRATION_REQUIRED`로 중단되고 기존 Holdings/Decision/Plan 기능은 그대로 유지됩니다.

## VN-P4-S1 Watch 저장소 준비

P4-S1은 기존 KIS quote 전달과 P3-S1의 ACTIVE Plan 위에 서버 Watch 설정·규칙·episode·coverage gap·앱 내 알림 outbox를 추가합니다. 기존 Position/원장/Plan을 수정하지 않으며, migration 시 과거 ACTIVE Plan을 Watch로 자동 backfill하거나 과거 알림을 생성하지 않습니다.

명시적으로 한 번 실행합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\migrate_watch_vnp4s1.py
```

현재 운영 confirmation·재무장·freshness 수치는 검증 전이므로 기본 production Watch policy는 `OPERATING_THRESHOLDS_UNAPPROVED`로 비활성입니다. Migration은 저장 구조만 준비하며 실시간 감시를 임의로 활성화하지 않습니다. 테스트 fixture에서만 명시적인 수치를 주입해 lifecycle을 검증합니다.

Watch 상태는 `holdings.db`에 저장되어 기본 Holdings backup에 포함됩니다. Backup manifest의 `extensions.holding_watch_v1`은 schema/policy contract와 여섯 Watch 테이블의 복원 가능성을 기록합니다. Quote tick 자체는 backup하지 않으며 restore 뒤 서버는 새 live coverage를 다시 확보해야 합니다. 서버 종료 구간의 가격이나 confirmation을 소급 재구성하지 않습니다.

## VN-P3-S1-UAT.4 Stop-Loosening fixture

이 도구는 브라우저 UAT에서 stop-loosening 보호를 확인하기 위한 **일회성 테스트 도구**입니다. 제품 분석 경로가 아니며, 기존 Analysis/Plan/Position을 수정하지 않고 현재 Analysis를 복제한 새 Revision 하나만 append합니다.

기본 실행은 preview만 표시하고 DB를 변경하지 않습니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\prepare_vnp3s1_stop_loosening_fixture.py --ticker 005930 --market KOSPI
```

출력된 Position/Active Plan/stop을 확인한 뒤 실제 fixture를 만들 때만 `--apply`를 추가합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\prepare_vnp3s1_stop_loosening_fixture.py --ticker 005930 --market KOSPI --apply
```

`--apply`는 변경 전에 Holdings snapshot을 자동 생성합니다. 현재 최신 Analysis가 이미 Active Plan의 source와 다르거나, Position/Plan/Analysis가 백업 이후 동시에 바뀌면 fixture 생성을 중단합니다. 생성되는 새 Revision은 현재 Active Plan보다 낮은 stop을 사용하며, 수량/평단/BUY·SELL·기존 Plan은 변경하지 않습니다.

브라우저 UAT가 끝나면 서버를 종료한 뒤 도구가 출력한 restore 명령으로 fixture 전 상태를 복원합니다.

## 복원

기본 복원은 Holdings DB만 복원합니다. Simulation/Tracking/Macro는 백업에 포함되어 있어도 명시적으로 복원합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_...
```

Market Store까지 포함된 백업이라면 명시적으로:

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_... --restore-market
```

Simulation/Tracking/Macro 상태까지 복원할 때는 필요한 owner를 명시합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_... --restore-simulation --restore-tracking --restore-macro
```

복원은 manifest/hash/integrity/FK/domain 검사를 먼저 수행합니다. 기존 DB가 있으면 `*.pre_restore_*.bak` snapshot을 만든 뒤 교체합니다. StockScope 서버가 DB를 사용 중이면 복원을 거부합니다.
