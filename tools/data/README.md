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

기존 작업 PC를 바꿔서 이어갈 때는 개별 migration/artifact 명령을 다시 치지 않고 루트 원클릭 동기화를 사용합니다.

```powershell
.\sync_local.ps1
```

이 명령은 `main` fast-forward 동기화 → Runtime migration → NEXT-6 Macro Development-only artifact chain 복구/검증까지 순서대로 수행합니다. 현재 Macro chain은 `RESEARCH → FRONTIER-DIAGNOSTIC → ADMISSIBILITY-EVIDENCE → ELIGIBILITY-RECONSTRUCTION → REFERENCE-STABILITY → REFERENCE-ADEQUACY-PROTOCOL V3 → REFERENCE-ADEQUACY-EVIDENCE`을 자동 확인하며 누락된 derived artifact만 immutable하게 재생성합니다. Holdout은 읽지 않고 외부 network request도 수행하지 않습니다. `DEV-7c3f6660b3aae03f.json`과 `PROTOCOL-e1de868dc8f16670.json`은 고정 seed artifact라서 둘 중 하나가 없으면 자동으로 추측/재생성하지 않고 안전하게 중단합니다.

쓰기 없이 상태만 확인하려면:

```powershell
.\sync_local.ps1 -CheckOnly
```

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

## NEXT-6B-S4.1 Candidate Frontier Compression
### 금리 충격 후보 행동 중복 제거 및 교차 방식 후보 압축

NEXT-6B-S4.1은 S4 후보 생성 규칙을 그대로 재생한 뒤 **Development에서 실제로 같은 판단을 만드는 후보를 한 그룹으로 묶고**, 같은 feature 안에서 method를 가리지 않는 Pareto 압축을 수행합니다. Holdout artifact는 입력 옵션 자체가 없습니다.

압축 순서:

1. S4 raw candidate와 method-local Pareto를 그대로 재현
2. eligible한 모든 양(+)의 금리 움직임을 그대로 잡는 `TRIVIAL_DIRECTION_RULE` 제거
3. Development row별 `eligible/signal` sequence와 episode boundary로 behavior signature 생성
4. 서로 다른 threshold/method라도 behavior가 같으면 하나의 behavior group으로 병합
5. `delta_bp_1obs`, `delta_bp_5obs`, `delta_bp_10obs`를 각각 독립적으로 cross-method Pareto
6. weighted score나 목표 후보 수 없이 compressed frontier 생성

Behavior group은 source candidate hash/method/threshold provenance를 모두 보존합니다. signal 날짜가 같더라도 eligibility가 다르면 다른 behavior로 취급하므로 표본 부족/UNKNOWN을 NORMAL처럼 합치지 않습니다.

Preview:

```powershell
.\.venv\Scripts\python.exe .\tools\data\compress_macro_calibration_candidates_next6b_s4_1.py `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json `
  --research-artifact .\backend\runtime\macro\calibration\RESEARCH-cdd96e164e12017d.json
```

Preview 검수 후 `--write-artifact`를 추가하면 `backend/runtime/macro/calibration/CANDIDATES-V2-<hash>.json`을 immutable artifact로 저장합니다.

완료 후에도 최종 candidate는 선택하지 않고 minimum sample도 고정하지 않습니다. `RATE_SPIKE`는 `UNCALIBRATED`, Holdout은 locked/unread, NORMAL/DETECTED label과 Network/Macro DB write/Production 영향은 모두 0입니다.

## NEXT-6B-S4.1R Frontier Admissibility Gate
### 과도한 금리 충격 후보 프런티어를 확정하지 않고 충격 후보 자격 기준을 분리

S4.1R은 S4/S4.1의 후보 생성·행동 중복 제거·교차 방식 Pareto 압축을 그대로 재생한 뒤, **어느 정도부터 RATE_SPIKE로 인정할지 아직 정책이 정의되지 않았다는 사실을 명시적으로 고정**합니다. Development 데이터가 희소성·포착률·episode 분포를 보여줄 수는 있지만, 5%·1%·95%·99%·MAD 3 같은 숫자를 자동으로 충격 기준으로 승격하지 않습니다.

현재 admissibility policy는 다음 상태로만 생성됩니다.

- policy id: `RATE_SPIKE_ADMISSIBILITY_UNSET`
- policy version: `UNSET`
- event unit: `UNSET`
- maximum signal fraction / positive capture / episode rate: `null`
- minimum year coverage / minimum sample: `null`
- status: `UNDEFINED`
- approved: `false`

진단은 `delta_bp_1obs`, `delta_bp_5obs`, `delta_bp_10obs` × 3개 방법의 **9개 family**를 모두 보고합니다. 각 family에는 후보 수, 고유 behavior 수, threshold 범위, signal fraction 범위, positive-move capture 범위, signal row/episode/episode-start 범위, 연도별 episode 범위, nested behavior, behavior/candidate hash가 포함됩니다. exact 100% positive capture는 기존 S4.1의 `TRIVIAL_DIRECTION_RULE`만 적용하며, 99.9%·98%·95% 같은 sub-100% capture에는 추가 cutoff를 두지 않습니다.

Preview:

```powershell
.\.venv\Scripts\python.exe .\tools\data\diagnose_macro_calibration_frontier_next6b_s4_1r.py `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json `
  --research-artifact .\backend\runtime\macro\calibration\RESEARCH-cdd96e164e12017d.json
```

검수 후 immutable diagnostic artifact가 필요할 때만 `--write-artifact`를 추가합니다. 결과는 `backend/runtime/macro/calibration/FRONTIER-DIAGNOSTIC-<hash>.json`에 저장되며 Git 대상이 아닙니다.

S4.1R 완료 상태는 `candidate generation=COMPLETE`, `compression=COMPRESSION_COMPLETE`, `diagnostics=COMPLETE`, `admissibility=ADMISSIBILITY_POLICY_UNDEFINED`, `ready_for_holdout=false`입니다. Holdout 입력 옵션은 없고 Holdout은 계속 locked/unread입니다. 최종 threshold/minimum sample/event unit/evaluation rule은 선택하지 않으며 `RATE_SPIKE`는 계속 `UNCALIBRATED`입니다. 다음 단계에서 별도 사전등록 작업으로 admissibility policy를 정의해야 합니다.

## NEXT-6B-S4.2-A Admissibility Review Report
### 금리 충격 후보 자격 기준 결정을 위한 개발 데이터 검토 보고서

S4.2-A는 S4.1R에서 이미 고정한 `FRONTIER-DIAGNOSTIC-*.json` 하나만 읽는 **review-only layer**입니다. DEV/PROTOCOL/RESEARCH를 다시 계산하지 않고 Holdout 입력도 받지 않습니다. 9개 feature × method family를 한 화면에서 비교할 수 있도록 candidate/behavior 수, threshold 범위, signal 빈도, positive capture, signal row/episode/연도별 episode 범위, nested behavior를 compact table로 보여줍니다.

실행:

```powershell
.\.venv\Scripts\python.exe .\tools\data\review_macro_admissibility_next6b_s4_2a.py `
  --diagnostic-artifact .\backend\runtime\macro\calibration\FRONTIER-DIAGNOSTIC-74458592d2e610da.json
```

표의 `Signal%`과 `Capture%`는 사람이 읽기 위한 표시값이며 source hash나 향후 정책 계산에는 사용하지 않습니다. 원본 Decimal 범위와 family hash는 review model에 그대로 보존됩니다.

S4.2-A는 policy를 결정하지 않습니다. `event_unit=UNSET`, `evaluation_rule=UNSET`, threshold/minimum sample/event unit 미선택, `ready_for_holdout=false`, `RATE_SPIKE=UNCALIBRATED`를 유지합니다. exact 100% positive capture에 대한 기존 `TRIVIAL_DIRECTION_RULE` 외에 99.9%·98%·95% 같은 sub-100% 후보를 자동 탈락시키지 않습니다. Network request와 Macro DB write, Production 영향은 모두 0입니다.

이 단계에서는 새 immutable policy artifact를 만들지 않습니다. 실제 9개 family review 결과를 검수한 뒤 다음 단계에서 admissibility policy 사전등록 여부를 결정합니다.

## NEXT-6B-S4.2-B Admissibility Evidence Matrix
### 금리 충격 자격 기준 사전등록을 위한 개발 데이터 근거 행렬

S4.2-B는 S4.1R diagnostic과 S2/S3의 Development·Protocol·Research artifact를 입력으로 받아 S4/S4.1 frontier를 **Development에서 deterministic replay**합니다. 재생된 `frontier_hash`가 diagnostic의 `source_frontier_hash`와 다르면 즉시 중단합니다. Holdout artifact는 입력하지 않습니다.

각 compressed frontier behavior group을 evidence row로 펼쳐 다음 관측값을 보존합니다.

- eligible / signal count와 signal fraction
- positive move count / capture count / capture fraction
- episode count와 별도 의미의 episode-start count
- Development 실제 연도 수와 episode starts per year
- eligible 대비 episode-start fraction
- year coverage / max-year concentration / episode separation
- source method / candidate / threshold provenance

9개 feature × method family마다 policy 축의 **실제 observed breakpoint만** 사용한 curve를 만듭니다. 사람이 만든 1%·5%·10% 같은 고정 grid는 추가하지 않습니다. maximum 성격의 축은 `AT_OR_BELOW`, minimum 성격의 축은 `AT_OR_ABOVE` 누적 개수를 보고합니다.

Descriptive summary의 Q1/median/Q3는 보간값을 새로 만들지 않고 `OBSERVED_ORDER_STATISTIC_FLOOR_V1` 방식으로 실제 관측 breakpoint에 snap합니다. 이 값들은 모두 `DESCRIPTIVE_ONLY`이며 policy threshold가 아닙니다.

Preview:

```powershell
.\.venv\Scripts\python.exe .\tools\data\build_macro_admissibility_evidence_next6b_s4_2b.py `
  --diagnostic-artifact .\backend\runtime\macro\calibration\FRONTIER-DIAGNOSTIC-74458592d2e610da.json `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json `
  --research-artifact .\backend\runtime\macro\calibration\RESEARCH-cdd96e164e12017d.json
```

Preview 검수 후 재현 가능한 full evidence를 저장할 때만 `--write-artifact`를 추가합니다. 파일명은 `ADMISSIBILITY-EVIDENCE-<hash>.json`이고 Git 대상이 아닙니다. 이 artifact는 policy approval artifact가 아니므로 `policy_defined=false`, `policy_approved=false`, `ready_for_holdout=false`를 유지합니다.

S4.2-B 완료 후에도 `event_unit=UNSET`, `episode_rate_unit=UNSET`, `minimum_sample_unit=UNSET`, `evaluation_rule=UNSET`, threshold/minimum sample/event unit 미선택, Holdout locked/unread, `RATE_SPIKE=UNCALIBRATED` 상태를 유지합니다. Network request, Macro DB write, Production 영향은 모두 0입니다.

## NEXT-6B-S4.2-B.1 Raw Universe & Eligibility Reconstruction
### 정책 적용 전 원시 후보 집합과 판단 가능 조건 분리

S4.2-B.1은 기존 S4/S4.1/S4.2-B artifact를 수정하지 않고, S4의 `FROZEN_RAW_GENERATION` 후보 집합을 Development에서 deterministic replay합니다. 기존 method-local Pareto, trivial-direction 제거, behavior grouping, cross-method Pareto, 최종 frontier까지 각 raw candidate의 legacy lineage를 기록합니다.

핵심 목적은 `computable`과 `policy eligible`을 분리하는 것입니다. 현재 TAIL/MAD는 metric이 계산 가능하면 baseline candidate behavior에 참여하지만, 이것은 승인된 minimum prior support가 아닙니다. 기존 `derived_minimum_prior_support=CEIL(eligible/signal)`도 metadata일 뿐 eligibility gate나 통계적 정밀도 보장으로 사용되지 않습니다.

실행:

```powershell
.\.venv\Scripts\python.exe .\tools\data\reconstruct_macro_eligibility_next6b_s4_2b1.py `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json `
  --research-artifact .\backend\runtime\macro\calibration\RESEARCH-cdd96e164e12017d.json `
  --diagnostic-artifact .\backend\runtime\macro\calibration\FRONTIER-DIAGNOSTIC-74458592d2e610da.json `
  --evidence-artifact .\backend\runtime\macro\calibration\ADMISSIBILITY-EVIDENCE-da7b94a2a51e3ff6.json
```

Family audit는 first-computable prior count와 first-signal prior count를 보여주고, TAIL/MAD에는 Development에 실제 존재하는 prior-count만 사용한 support counterfactual을 제공합니다. 이 curve는 signal/event behavior가 변하는 point만 저장하며 eligible-only denominator 변화는 별도 point를 만들지 않습니다. 임의의 20/30/50/100 grid는 만들지 않고 `recommended_support=null`을 유지합니다.

향후 pipeline ordering은 `RAW_CANDIDATE_GENERATION → ELIGIBILITY → ADMISSIBILITY → BEHAVIOR_GROUPING → POLICY_PRESERVING_COMPRESSION`으로 선언하지만, B.1에서는 eligibility/admissibility 수치나 새 compression 규칙을 선택하지 않습니다.

Episode 의미는 기존 `VN_NEXT6B_S4_CONSECUTIVE_TRUE_RUN_V1`을 유지하고 event count 의미를 `EPISODE_START`로 기록합니다. 평가 왼쪽 경계에서 이미 진행 중인 episode를 새 event로 세지 않도록 `REQUIRE_PRIOR_STATE` 규칙을 명시하지만 Holdout 평가는 수행하지 않습니다.

Preview 검수 후에만 `--write-artifact`를 추가해 `ELIGIBILITY-RECONSTRUCTION-<hash>.json`을 저장합니다. 이 artifact는 policy preregistration이 아니므로 eligibility/admissibility는 계속 UNDEFINED, minimum prior observations는 UNSET, `ready_for_holdout=false`, `RATE_SPIKE=UNCALIBRATED`, Network/Macro DB/Production 영향은 0입니다.

## NEXT-6B-S4.2-B.1.5 Reference Stability Evidence
### TAIL/MAD 최소 참조 표본 수 결정을 위한 기준 분포 안정성 근거

S4.2-B.1.5는 B.1에서 확인한 candidate/event 손실과 별도로, expanding strictly-prior reference 자체가 관측 추가에 따라 얼마나 변하는지 Development에서 측정합니다. 이 단계는 minimum prior observations나 reference adequacy criterion을 선택하지 않습니다.

분석 대상은 `delta_bp_1obs`, `delta_bp_5obs`, `delta_bp_10obs`의 TAIL/MAD 여섯 family입니다. EPT는 expanding reference distribution을 사용하지 않으므로 세 family 모두 reference-support stability 분석에서 명시적으로 제외합니다.

TAIL은 prior N에서 N+1로 한 관측을 추가했을 때 empirical CDF의 exact sup drift를 실제 observed support만으로 계산합니다. synthetic x-grid는 만들지 않으며 `1/N` probability resolution은 설명용 metric일 뿐 안정성 판정 점수로 사용하지 않습니다.

MAD는 동일 transition에서 prior median과 prior MAD의 절대 변화, 그리고 이전 MAD가 양수일 때만 relative MAD change를 기록합니다. 이전 MAD가 0이면 relative change는 `null`과 `NON_COMPUTABLE_ZERO_SCALE`로 남기며 weighted stability score는 만들지 않습니다.

B.1의 실제 support-change point와 stability evidence를 join하고, 여섯 TAIL/MAD curve의 support point 합집합을 `common_support_review_points`로 생성합니다. 특정 family에 해당 support point가 없더라도 이전 값을 복사하지 않고 그 prior count의 reference state를 직접 계산합니다.

Preview:

```powershell
.\.venv\Scripts\python.exe .\tools\data\analyze_macro_reference_stability_next6b_s4_2b15.py `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json `
  --research-artifact .\backend\runtime\macro\calibration\RESEARCH-cdd96e164e12017d.json `
  --reconstruction-artifact .\backend\runtime\macro\calibration\ELIGIBILITY-RECONSTRUCTION-c6db8f9dd260fdd4.json
```

Preview 검수 후에만 `--write-artifact`를 추가해 `REFERENCE-STABILITY-<hash>.json`을 저장합니다. 완료 후에도 `reference_adequacy_criterion=UNSET`, `minimum_prior_observations=null`, `recommended_support=null`, admissibility UNDEFINED, Holdout locked/unread, `RATE_SPIKE=UNCALIBRATED`, Network/Macro DB/Production 영향은 모두 0입니다.

## NEXT-6B-S4.2-B.1.6 Reference Adequacy Validation Protocol
### Development-informed reference adequacy 검증 계약과 미정 tolerance의 명시적 차단

S4.2-B.1.6은 B.1.5에서 생성한 reference stability evidence를 보고 임의의 N을 선택하지 않습니다. 이미 Development curve를 관찰한 상태이므로 `policy_origin=DEVELOPMENT_INFORMED`을 명시하고, Development-blind/ex-ante였다고 주장하지 않습니다.

검증 계약은 reference adequacy를 `COMPUTABILITY → SENSITIVITY → EVIDENCE_SUFFICIENCY`의 세 층으로 분리합니다.

- TAIL: local append ECDF sup drift는 `DIAGNOSTIC_ONLY`로 유지하며 adequacy gate/tolerance 대상에서 제외, cumulative ECDF drift와 time-order-preserving contiguous reference perturbation만 향후 adequacy criterion 대상으로 검토
- MAD: local/cumulative/perturbation의 absolute median change, absolute MAD change, relative MAD change
- MAD의 이전 MAD가 0이면 relative change를 0으로 만들지 않고 `NON_COMPUTABLE_ZERO_SCALE` semantics를 유지
- 단일 zero transition이나 전체 median change=0만으로 adequacy를 승인하지 않음
- TAIL/MAD와 1obs/5obs/10obs에는 common N을 우선하며 모든 family 조건을 AND로 결합
- EPT는 expanding reference distribution을 사용하지 않으므로 reference-support gate에서 계속 제외
- candidate/signal/episode/covered-year survival은 N이나 tolerance 선택 입력으로 사용하지 않음
- 조건을 만족하는 boundary가 없으면 `NO_SUPPORTED_BOUNDARY`

B.1.6-R review에서 TAIL local append drift는 expanding reference 크기 증가 자체로 한 관측의 영향이 작아지는 구조를 포함하므로 adequacy cutoff로 사용하지 않고 descriptive diagnostic으로만 유지하도록 정리했습니다. 이에 따라 `TAIL_LOCAL_TOLERANCE_UNJUSTIFIED` blocker는 제거되고 unresolved blocker는 11개입니다. 나머지 cumulative comparison interval, perturbation segment length, MAD tolerance, validation suffix 길이, violation policy 등은 독립적으로 정당화되지 않았으므로 임의 값을 만들지 않습니다. protocol 상태는 계속 `BLOCKED_UNJUSTIFIED_TOLERANCE`이며 `minimum_prior_observations=null`, `recommended_support=null`, `ready_for_b17=false`, `ready_for_b2=false`, `ready_for_holdout=false`를 유지합니다.

Preview:

```powershell
.\.venv\Scripts\python.exe .\tools\data\preregister_macro_reference_adequacy_next6b_s4_2b16.py `
  --development-artifact .\backend\runtime\macro\calibration\DEV-7c3f6660b3aae03f.json `
  --protocol-artifact .\backend\runtime\macro\calibration\PROTOCOL-e1de868dc8f16670.json `
  --research-artifact .\backend\runtime\macro\calibration\RESEARCH-cdd96e164e12017d.json `
  --reconstruction-artifact .\backend\runtime\macro\calibration\ELIGIBILITY-RECONSTRUCTION-c6db8f9dd260fdd4.json `
  --reference-stability-artifact .\backend\runtime\macro\calibration\REFERENCE-STABILITY-abb0799ddbf8ccfe.json
```

검수 후 현재 blocked protocol 자체를 immutable하게 보존할 때만 `--write-artifact`를 추가합니다. 파일명은 `REFERENCE-ADEQUACY-PROTOCOL-<hash>.json`입니다. 이 artifact는 reference-support approval이나 B.1.7 evidence가 아니며, 남은 11개 unresolved protocol blocker를 해소하기 전에는 B.1.7을 실행할 수 없습니다.

Holdout 입력 옵션은 없고 Holdout은 locked/unread입니다. Network request, Macro DB write, Production 영향은 모두 0이며 Scanner/Strategy/Risk/Holdings/Capital Aware 동작은 변경하지 않습니다.

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


### NEXT-6B-S4.2-B.1.6-R2.1 — Boundary-Anchored Reference Adequacy Evidence

R2.1은 Development-only reference adequacy 원자료를 생성합니다. 기존 B.1.5 common review point를 anchor N으로 사용하고, 각 anchor에서 이후 모든 strictly-prior reference state까지의 forward envelope 경로를 보존합니다.

- TAIL: exact ECDF sup distance, observed support only, invented x-grid 0
- MAD: absolute median shift / absolute MAD shift / relative MAD shift
- MAD anchor scale 0: relative shift는 `null`, `NON_COMPUTABLE_ZERO_SCALE`
- tolerance 선택 없음
- validation suffix minimum 선택 없음
- minimum N 선택 없음
- Holdout 접근 없음
- Production 영향 없음

개별 명령 대신 새 PC/다른 PC에서는 계속 루트 원클릭 동기화를 사용합니다.

```powershell
.\sync_local.ps1
```

R2.1-PERF 이후 current evidence는 `REFERENCE-ADEQUACY-EVIDENCE-<hash>.json.gz` V2 compact 형식입니다. 기존 459.24 MB V1 JSON은 historical immutable evidence로 남기고 삭제하거나 덮어쓰지 않습니다.

V2는 TAIL ECDF distance를 exact numerator varint로, MAD absolute shift를 lossless scaled integer varint로 저장합니다. MAD relative shift는 absolute MAD shift와 anchor MAD에서 정확히 재구성하며 zero-scale은 계속 `null / NON_COMPUTABLE_ZERO_SCALE`을 유지합니다. 전체 logical evidence hash는 저장 표현과 분리되어 V1/V2 전체 comparison 동등성을 검증합니다.

`.\sync_local.ps1`은 compact V2가 없으면 자동 생성하며, historical V1이 있으면 최초 migration에서 전체 logical-equivalence를 검증합니다. V2 compressed size가 V1의 25%를 넘으면 artifact 쓰기 전에 fail closed 합니다. `-CheckOnly`에서는 생성하지 않습니다.

원클릭 출력에는 current V2 artifact 이름, compressed size, support point 수, family 수, forward comparison 수, encoding, DB write/Production 상태가 함께 표시됩니다.


## NEXT-6E R5R binding / evaluation naming

현재 frozen DEV binding 도구:

```powershell
.\.venv\Scripts\python.exe .\tools\data\bind_macro_r5r_evaluation_next6e.py --dataset <DEV.json> --output <binding.json>
```

이 도구는 identity / chronology / structural metadata만 바인딩하며 T_EMP/L_EMP/S_EMP, candidate support, Common-N을 계산하지 않는다.

명칭:
- `NEXT-6E-R5R-EVALUATION`: frozen R5R actual observed-path evaluation
- `JEV-REVIEWER-EVALUATION`: AI Decision Reviewer incremental-value evaluation

둘은 별도 작업이다. 과거 narrative의 `NEXT-6E-R5R-JEV` 표현은 current command/task name으로 사용하지 않는다.
