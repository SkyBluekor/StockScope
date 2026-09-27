# StockScope DATA.1 Runtime Tools

이 도구들은 StockScope의 사용자 원장과 Market Store를 분리해서 관리합니다.

## 데이터 분류

- `backend/runtime/holdings/holdings.db`: 사용자 핵심 상태. 기본 백업 대상.
- `backend/runtime/market_history/market_history.db`: 재수집 가능한 시장 데이터. `--include-market`일 때만 백업.
- `backend/runtime/simulation/simulation.db`: 존재하면 기본 백업에 자동 포함. Validation/Feedback/Prospective 평가 상태를 보존.
- `backend/runtime/tracking/recommendation_tracking.db`: 존재하면 기본 백업에 자동 포함. Tracking 원본 owner는 그대로 유지.
- `.env`, KRX/KIS/DART 키, 인증 정보: 백업 대상 아님.
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

기본 백업은 `holdings.db`를 필수로 포함하고, 존재하는 `simulation.db`와 `recommendation_tracking.db`를 자동 포함합니다. Market Store는 재수집 가능 데이터이므로 기본 제외입니다.

## 전체 데이터 백업

```powershell
.\.venv\Scripts\python.exe .\tools\data\backup_runtime.py --include-market
```

Market Store까지 SQLite backup API로 snapshot합니다.

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

기본 복원은 Holdings DB만 복원합니다. Simulation/Tracking은 백업에 포함되어 있어도 명시적으로 복원합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_...
```

Market Store까지 포함된 백업이라면 명시적으로:

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_... --restore-market
```

Simulation/Tracking 상태까지 복원할 때는 필요한 owner를 명시합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_... --restore-simulation --restore-tracking
```

복원은 manifest/hash/integrity/FK/domain 검사를 먼저 수행합니다. 기존 DB가 있으면 `*.pre_restore_*.bak` snapshot을 만든 뒤 교체합니다. StockScope 서버가 DB를 사용 중이면 복원을 거부합니다.
