# StockScope v0.14 - 새 PC 재현성 / KRX 데이터 최신성 가이드

## 1. 목적

새 PC에서 Clone했을 때 환경 차이 때문에 테스트가 깨지거나, KRX 당일 데이터가 늦게 게시된 뒤에도 이전 거래일이 계속 표시되는 문제를 방지합니다.

## 2. 새 PC 최초 설정

```powershell
git clone <REPOSITORY_URL>
cd StockScope
python --version
node --version
npm --version
```

Node/npm이 없으면:

```powershell
winget install OpenJS.NodeJS.LTS
```

설치 후 PowerShell/VS Code 터미널을 완전히 닫고 다시 엽니다.

`.env`는 Git에 포함되지 않으므로 직접 생성합니다.

```powershell
Copy-Item .env.example .env
```

KRX/DART 키를 넣은 뒤:

```powershell
Unblock-File .\setup.ps1
Unblock-File .\run-dev.ps1
.\setup.ps1
.\run-dev.ps1
```

## 3. PowerShell 실행 정책

`Activate.ps1`이나 프로젝트 `.ps1`이 보안 오류로 막히면 현재 창에서만:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

개발용 개인 PC에서 현재 사용자 기준으로 유지하려면:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

가상환경 Activate는 필수가 아닙니다. 프로젝트 스크립트는 `.venv\Scripts\python.exe`를 직접 사용합니다.

## 4. FastAPI / Starlette 재현성

새 clone에서 다음 테스트 오류가 발생한 적이 있습니다.

```text
AttributeError: '_IncludedRouter' object has no attribute 'path'
```

원인은 느슨한 버전 범위 때문에 새 환경에 FastAPI 0.141.1 / Starlette 1.6.0이 설치되어, 기존 테스트가 검증된 환경과 내부 라우터 구조가 달라진 것이었습니다.

v0.14에서 검증 버전을 고정합니다.

- FastAPI 0.128.2
- Starlette 0.50.0
- httpx 0.28.1
- uvicorn 0.48.0
- pydantic-settings 2.14.1
- python-dotenv 1.2.2
- pytest 9.0.2
- pytest-asyncio 1.3.0

확인:

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, starlette; print('FastAPI:', fastapi.__version__); print('Starlette:', starlette.__version__)"
```

버전이 다르면 `setup.ps1`을 다시 실행합니다.

## 5. KRX 당일 데이터가 이전 거래일로 표시되는 이유

StockScope는 KRX OPEN API의 확정 일별 데이터를 사용합니다. 장이 끝났더라도 OPEN API에 당일 데이터가 아직 게시되지 않았으면 `count: 0` / `rows: []`가 올 수 있습니다.

그 경우 StockScope는 최근 확정 거래일로 fallback합니다. 이는 정상입니다.

Swagger 확인:

```text
http://127.0.0.1:8000/docs
```

- `GET /api/krx/stocks/{code}/daily`
- `GET /api/krx/index/{market}/daily`

날짜를 직접 입력해 KRX가 해당 날짜 데이터를 실제로 반환하는지 확인합니다.

## 6. v0.13 빈 캐시 문제와 v0.14 수정

기존에는 KRX가 당일에 `[]`를 반환해도 메모리/디스크 캐시에 저장할 수 있었습니다.

```text
당일 조회 -> [] -> 장기 캐시 -> KRX가 나중에 데이터 게시 -> StockScope는 [] 재사용 -> 전 거래일 유지
```

v0.14 정책:

```text
당일/미래 날짜
  -> 디스크 장기 캐시 사용 안 함
  -> 정상 데이터도 5분 TTL 후 재확인

빈 응답
  -> 디스크 저장 안 함
  -> 5분 TTL만 적용
  -> TTL 후 KRX 재조회

과거 확정 데이터
  -> 기존처럼 gzip 디스크 캐시 재사용
```

v0.13 이하의 `[]` 디스크 캐시는 v0.14가 읽을 때 자동으로 삭제합니다.

## 7. 대시보드 표시

fallback 발생 시 단순히 `최근 거래일 자동 보정`이라고만 하지 않고 다음처럼 이유를 표시합니다.

```text
최근 확정 거래일 사용 중
KRX에 2026.09.08 확정 데이터가 아직 제공되지 않아
최근 확인 가능한 거래일인 2026.09.07 데이터를 사용 중입니다.
당일 KRX 빈 응답은 5분만 임시 보관하고 이후 다시 확인합니다.
```

따라서 사용자는 앱 오류인지, KRX 게시 지연인지 구분할 수 있습니다.

## 8. 줄바꿈 경고

Windows에서 다음 경고가 나올 수 있습니다.

```text
LF will be replaced by CRLF
```

v0.14부터 `.gitattributes`로 소스코드는 LF, PowerShell/Windows 스크립트는 CRLF 정책을 명시합니다. 기존 파일을 한 번 정규화하고 싶다면 별도 커밋에서 처리하는 것을 권장합니다.

## 9. v0.15 Windows `tzdata` 보완

v0.14의 한국시간 기준 캐시 판정은 Python `ZoneInfo("Asia/Seoul")`을 사용합니다. Linux/macOS에서는 시스템 timezone DB가 있는 경우가 많지만, Windows Python 환경에서는 다음 오류가 발생할 수 있습니다.

```text
ModuleNotFoundError: No module named 'tzdata'
ZoneInfoNotFoundError: No time zone found with key Asia/Seoul
```

v0.15부터 `backend/pyproject.toml`의 필수 의존성에 `tzdata==2026.2`를 포함합니다. 새 clone 또는 기존 clone 모두 프로젝트 루트에서 다음 명령으로 정상화합니다.

```powershell
.\setup.ps1
```

가상환경만 즉시 고쳐야 할 때는:

```powershell
.\.venv\Scripts\python.exe -m pip install tzdata
```

확인:

```powershell
.\.venv\Scripts\python.exe -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Seoul'))"
```

`Asia/Seoul`이 출력되면 정상입니다. v0.15에는 이 조건을 확인하는 백엔드 테스트도 포함합니다.
