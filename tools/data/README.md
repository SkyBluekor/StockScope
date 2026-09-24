# StockScope DATA.1 Runtime Tools

이 도구들은 StockScope의 사용자 원장과 Market Store를 분리해서 관리합니다.

## 데이터 분류

- `backend/runtime/holdings/holdings.db`: 사용자 핵심 상태. 기본 백업 대상.
- `backend/runtime/market_history/market_history.db`: 재수집 가능한 시장 데이터. `--include-market`일 때만 백업.
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

기본 백업은 `holdings.db`와 `backup_manifest.json`만 포함합니다.

## 전체 데이터 백업

```powershell
.\.venv\Scripts\python.exe .\tools\data\backup_runtime.py --include-market
```

Market Store까지 SQLite backup API로 snapshot합니다.

## 복원

기본 복원은 Holdings DB만 복원합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_...
```

Market Store까지 포함된 백업이라면 명시적으로:

```powershell
.\.venv\Scripts\python.exe .\tools\data\restore_runtime.py .\backups\StockScope_... --restore-market
```

복원은 manifest/hash/integrity/FK/domain 검사를 먼저 수행합니다. 기존 DB가 있으면 `*.pre_restore_*.bak` snapshot을 만든 뒤 교체합니다. StockScope 서버가 DB를 사용 중이면 복원을 거부합니다.
