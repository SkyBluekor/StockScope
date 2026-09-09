# StockScope

국내 주식의 KRX 시장 데이터와 OpenDART 기업/공시 데이터를 결합해 **시장 상태, 기술적 전략 적합도, 리스크 구조, 보유 포지션 시나리오**를 설명하는 투자 판단 보조 웹앱입니다.

> **중요:** StockScope는 실제 매수·매도·정정·취소 주문을 수행하지 않습니다. 증권사 주문 API를 구현하지 않으며, 모든 가격·전략·손절·목표 값은 분석/시뮬레이션 참고용입니다.

## 현재 구현 범위

- KRX KOSPI/KOSDAQ 최근 확정 일별 데이터
- KRX KOSPI/KOSDAQ 지수 및 시장 대시보드
- KRX 종목명/종목코드 자동검색
- OpenDART 기업개황/최근 공시
- 최근 60거래일 기술지표 분석
- 현재 참고가격 수동 입력 시 예상 MA20/RSI 및 가격 위치 재계산
- 10개 전략 + 매매 보류(NO TRADE) 평가
- 전략별 조건 적합도와 프로그램 자동 점검
- Risk Engine: 전략 무효화, 손절 참고구간, 1·2차 목표, R:R
- 미보유/보유 중 상황별 대응 가이드
- 평균 매수가/수량을 이용한 보유 포지션 가정 분석

## 기술 스택

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Market Data: KRX OPEN API
- Corporate/Disclosure Data: OpenDART
- Local cache: `backend/runtime/krx` (Git 제외)

## 다른 PC에서 실행하기

### 1. 준비물

- Git
- Python 3.11 이상
- Node.js LTS / npm
- KRX OPEN API 인증키
- OpenDART 인증키

### 2. 저장소 Clone

```powershell
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd StockScope
```

### 3. API 키 발급

상세 절차는 [`docs/API_KEYS.md`](docs/API_KEYS.md)를 참고하세요.

StockScope V1에서 KRX는 아래 6개 서비스 활용 승인을 사용합니다.

1. 유가증권 일별매매정보
2. 코스닥 일별매매정보
3. 유가증권 종목기본정보
4. 코스닥 종목기본정보
5. KOSPI 시리즈 일별시세정보
6. KOSDAQ 시리즈 일별시세정보

### 4. `.env` 생성

루트의 `.env.example`을 복사합니다.

```powershell
Copy-Item .env.example .env
```

`.env`에 본인의 키를 입력합니다.

```env
KRX_API_KEY=본인의_KRX_인증키
DART_API_KEY=본인의_OpenDART_인증키
ENVIRONMENT=development
```

`.env`는 `.gitignore`에 포함되어 있으며 **절대로 GitHub에 커밋하지 않습니다.**

### 5. 최초 설치

먼저 Python/Node 설치 여부를 확인할 수 있습니다.

```powershell
python --version
node --version
npm --version
```

Node/npm이 없다면 Windows에서 Node.js LTS를 설치합니다.

```powershell
winget install OpenJS.NodeJS.LTS
```

설치 직후에는 기존 PowerShell이 PATH 변경을 모를 수 있으므로 **PowerShell/VS Code 터미널을 완전히 닫고 다시 엽니다.**

그다음:

```powershell
.\setup.ps1
```

PowerShell에서 다운로드한 스크립트 실행이 차단되면 프로젝트의 스크립트만 차단 해제합니다.

```powershell
Unblock-File .\setup.ps1
Unblock-File .\run-dev.ps1
.\setup.ps1
```

`setup.ps1`은 다음을 수행합니다.

- Python / Node.js / npm 사전 검사
- `.venv` 생성
- **검증된 FastAPI/Starlette 버전으로 의존성 설치/복구**
- 백엔드 테스트 실행
- `package-lock.json`이 있으면 `npm ci`, 없으면 `npm install`
- 프론트 빌드 검증

> `.venv`를 수동으로 Activate하지 않아도 `setup.ps1`과 `run-dev.ps1`은 `.venv\Scripts\python.exe`를 직접 사용합니다.

### 6. 개발 서버 실행

```powershell
.\run-dev.ps1
```

- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

## 테스트

백엔드:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
```

프론트:

```powershell
cd frontend
npm run build
```

## 데이터 기준

KRX OPEN API는 StockScope에서 **확정 일별(EOD) 데이터**로 사용합니다. 장중 실시간 현재가가 아닙니다.

사용자가 다른 앱에서 확인한 현재 가격을 직접 입력할 수 있지만, 해당 값은 임시 시나리오 계산에만 사용합니다.

- KRX 확정 일봉 변경 안 함
- 로컬 KRX 캐시 변경 안 함
- 사용자 입력 현재가를 과거 종가로 저장하지 않음
- 현재가만 입력한 경우 예상 MA20/RSI 등 계산 가능
- 당일 고가/저가/거래량까지 입력하면 일부 지표를 더 현재 상황에 가깝게 보완

## 보유 포지션 분석

전략 분석 전에 다음 중 하나를 선택할 수 있습니다.

- `아직 보유하지 않음`: 신규 진입 관점
- `현재 보유 중`: 평균 매수가와 선택적 수량을 입력해 보유 포지션 관점

보유 중 분석은 실제 계좌 조회가 아니라 **사용자가 입력한 가정값**입니다. StockScope는 평균가 대비 손익, 20일선/지지선/저점 구조, 전략 무효화 기준 등을 자동 점검합니다.

## 프로젝트 구조

```text
StockScope/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ backtest/
│  │  ├─ core/
│  │  ├─ market/
│  │  ├─ risk/
│  │  ├─ scanner/
│  │  ├─ simulation/
│  │  └─ strategy/
│  └─ tests/
├─ frontend/
│  ├─ public/
│  └─ src/
├─ docs/
├─ .env.example
├─ setup.ps1
└─ run-dev.ps1
```

## 자주 발생하는 문제

### KRX 401

인증키를 발급받아도 각 API 서비스 **활용 신청 + 관리자 승인**이 별도로 필요합니다. `docs/API_KEYS.md`의 KRX 6개 서비스가 모두 승인됐는지 확인하세요.

### 오늘 날짜의 KRX 데이터가 없음

KRX를 일별 확정 데이터 소스로 사용하기 때문에 장 마감 후에도 OPEN API 게시 시점까지 당일 데이터가 `count: 0`일 수 있습니다. StockScope는 최근 사용 가능한 거래일을 자동 탐색합니다.

v0.14부터는 **당일 빈 응답을 디스크에 영구 저장하지 않습니다.** 빈 응답은 5분만 임시 캐시한 뒤 KRX를 다시 확인합니다. 대시보드에서도 fallback 사용 이유를 직접 표시합니다.

Swagger에서 직접 확인하려면:

1. `http://127.0.0.1:8000/docs`
2. `GET /api/krx/stocks/{code}/daily` 또는 `GET /api/krx/index/{market}/daily`
3. 날짜를 명시하여 실행

예: `005930 / KOSPI / 2026-09-08`

과거 v0.13 이하에서 만들어진 빈 캐시를 수동 정리해야 할 때만 서버를 끄고 다음을 사용합니다.

```powershell
Remove-Item .\backend\runtime\krx\*20260908*.json.gz -ErrorAction SilentlyContinue
```

날짜는 확인하려는 날짜에 맞게 바꾸세요. v0.14에서는 빈 캐시 파일을 발견하면 자동 폐기합니다.

### `.env`를 수정했는데 반영되지 않음

백엔드 개발 서버를 종료 후 다시 실행하세요.

### `setup.ps1` / `.venv\Scripts\Activate.ps1` 보안 오류

GitHub에서 받은 프로젝트의 스크립트만 차단 해제하려면:

```powershell
Unblock-File .\setup.ps1
Unblock-File .\run-dev.ps1
```

현재 PowerShell 창에서만 임시 허용:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

개발 PC의 현재 사용자에 대해 매번 허용하기 싫다면 한 번만:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

`Activate.ps1` 실행은 선택사항입니다. 수동 활성화가 필요하면:

```powershell
.\.venv\Scripts\Activate.ps1
```

가상환경 Python이 맞는지 확인:

```powershell
python -c "import sys; print(sys.executable)"
```

프로젝트 경로의 `.venv\Scripts\python.exe`가 출력되면 정상입니다. 시스템 전체 실행정책을 낮추는 방식은 권장하지 않습니다.


### Clone 후 `_IncludedRouter` 테스트 오류

다음 오류가 새 PC에서만 발생한다면 코드부터 수정하지 말고 FastAPI/Starlette 버전을 확인하세요.

```text
AttributeError: '_IncludedRouter' object has no attribute 'path'
```

확인:

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, starlette; print(fastapi.__version__, starlette.__version__)"
```

StockScope v0.14 기준 검증 버전은 **FastAPI 0.128.2 / Starlette 0.50.0**입니다. `setup.ps1`을 다시 실행하면 `backend/pyproject.toml`의 고정 버전으로 복구합니다. 이 문제는 새 clone에서 허용 범위의 최신 FastAPI/Starlette가 설치되면서 내부 라우터 구조가 달라져 발생했던 환경 재현성 문제입니다.

### `npm` 명령을 찾을 수 없음

```powershell
winget install OpenJS.NodeJS.LTS
```

설치 후 새 PowerShell에서:

```powershell
node -v
npm -v
```

둘 다 버전이 출력되어야 합니다.

자세한 새 PC 복구/데이터 최신성 절차는 [`docs/setup-data-freshness-v0.14.md`](docs/setup-data-freshness-v0.14.md)를 참고하세요.


### Windows에서 `Asia/Seoul` / `tzdata` 오류

다음 오류가 발생하면 v0.14에서 추가된 한국시간 처리에 필요한 timezone 데이터가 없는 환경입니다.

```text
ZoneInfoNotFoundError: No time zone found with key Asia/Seoul
ModuleNotFoundError: No module named 'tzdata'
```

v0.15부터 `tzdata`가 백엔드 필수 의존성에 포함됩니다. 프로젝트 루트에서 다음을 다시 실행하면 자동 설치됩니다.

```powershell
.\setup.ps1
```

급히 현재 가상환경만 복구하려면:

```powershell
.\.venv\Scripts\python.exe -m pip install tzdata
```

### OpenDART Event Impact

최근 공시를 HIGH / MEDIUM / LOW로 분류하고, 구조화 API가 있는 주요사항은 핵심 수치를 추출해 초보자용 설명과 전략 영향으로 연결합니다. HIGH 이벤트는 신규 진입 Risk Gate에 반영됩니다.

## 보안 원칙

- `.env` / API 인증키 Git 커밋 금지
- KRX/OpenDART 조회 API만 사용
- 실제 증권 주문 Endpoint 없음
- 사용자 입력 현재가/보유 가정은 분석 데이터와 분리
- 공개 배포 시 Cloudflare Secrets 등 서버측 Secret Store 사용 예정

## 라이선스 / 데이터

소스코드 라이선스와 별개로 KRX/OpenDART 데이터 사용은 각 제공기관의 이용조건을 따라야 합니다. 공개 서비스나 데이터 재배포로 확장하기 전에는 각 제공기관의 최신 이용조건을 다시 확인하세요.


## Event Impact Engine

StockScope는 OpenDART 공시를 제목만 나열하지 않고 `공시 사실 → 핵심 조건 → 회사 규모 비교 → 가격 반응 → 전략 영향 → 사용자 대응` 순서로 분석합니다.

현재 지원 예시:
- 유상증자 / CB / BW / 합병: OpenDART 구조화 주요사항 API 우선
- 판매·공급계약 등: 공시 원문 보조추출
- 판매·공급계약은 가능하면 최근 사업보고서 매출액과 계약규모를 비교
- 공시 전후 가격 반응은 KRX EOD 또는 사용자가 입력한 현재 참고가격으로 계산

자동 해석이 불완전한 경우에는 값을 추측하지 않고 원문 확인을 안내합니다.


## 입력 UX v0.15.2

현재 참고가격은 직접 입력과 버튼 조작을 함께 제공합니다. `- / +`는 가격대별 KRX 호가가격단위를 사용하며, 짧게 누르면 1호가씩 이동하고 약 0.32초 이상 꾹 누르면 연속 이동하면서 점차 빨라집니다. `-5% / -1% / KRX 종가 / +1% / +5%`는 고정 점프가 아니라 **현재 누적 변동률에서 계속 더하고 빼는 방식**으로 동작하며 버튼 조정 범위는 최근 확정 종가 대비 `-30% ~ +30%`입니다. 최근 KRX 확정 일봉의 시가·고가·저가·종가도 한 번에 현재 참고가격으로 선택할 수 있습니다. 평균 매수가와 보유 수량에도 `- / +` 조작을 제공합니다. 숫자는 입력 즉시 천 단위 콤마로 표시됩니다.

분석 후 가격·보유정보가 변경되면 기존 결과를 지우지 않고 **이전 입력 기준 결과**라고 경고하며 재분석을 유도합니다. 자세한 내용은 [`docs/input-ux-v0.15.2.md`](docs/input-ux-v0.15.2.md)를 참고하세요.

## 개발 로드맵

현재 계획은 다음 순서입니다.

1. **v0.15.2 입력 UX** — 누적 ±%·OHLC 빠른 선택·롱프레스 연속 호가·입력 변경 감지
2. **v0.16 Relative Strength** — 종목 vs KOSPI/KOSDAQ, 업종 vs 시장 상대강도
3. **v0.17.1 Action Plan + Fundamental Freshness** — 최신 분기/반기/3분기/사업보고서 자동 선택, 전년동기 비교, 행동 중심 Analysis Hub
4. **v0.18 Investor Style Engine** — Buffett/Graham/Lynch/CAN SLIM 등 유명 투자 방식에서 공개적으로 알려진 원칙을 규칙화해 `스타일 적합도`로 설명. 특정 투자자의 실제 추천이나 수익 확률로 표현하지 않음
5. **v0.19 Backtest Engine** — 기술 전략과 정량 규칙을 과거 데이터로 검증
6. **v0.20 Strategy Scanner** — 검증된 조건으로 전체 종목 탐색
7. **이후 Portfolio Simulator / 설명 레이어 / 배포**

Investor Style Engine은 이름만 붙이는 기능으로 만들지 않습니다. 먼저 Fundamental Engine에서 ROE/ROIC, 이익·현금흐름 지속성, 부채, 성장성, 밸류에이션 등 필요한 입력을 구조화한 뒤 스타일별 근거와 약점을 함께 보여주는 방향으로 구현합니다.


### Input UX v0.15.3

- Removed the redundant latest-KRX OHLC shortcut cards.
- Current reference price keeps direct input, cumulative ±1%/±5%, reset-to-KRX-close, and long-press tick adjustment.
- Intraday high, low, and cumulative volume are optional advanced inputs rather than required fields.
- Intraday high/low use the same direct-input + short/long-press stepper UX.
- Cumulative volume uses adaptive step sizes and long-press repeat.
- If intraday optional values are omitted, analysis continues using confirmed KRX EOD values.


### Input UX v0.15.4

- Fixed clipping of large numeric values in intraday high/low/volume steppers.
- Intraday high/low cards now automatically collapse to one column when the available container width is too narrow.
- Numeric inputs keep a minimum readable width and use tabular digits for stable alignment.

### Relative Strength v0.16

StockScope now compares each stock with its own KOSPI/KOSDAQ benchmark using confirmed KRX EOD data.

- 5 / 20 / 60-session stock return vs market return
- market excess return in percentage points
- relative-strength label: strong / outperform / neutral / underperform / weak
- short-term relative-strength trend: improving / stable / deteriorating
- connected to Trend Following, Pullback, Breakout, and Momentum Continuation strategy suitability
- manual current-price input is intentionally excluded from relative strength because the benchmark is confirmed EOD
- sector-relative strength remains a later step after verified KRX sector mapping

Roadmap after v0.16:
1. verified sector mapping + sector-relative strength
2. Fundamental Engine
3. Investor Style Engine (Buffett / Graham / Peter Lynch / CAN SLIM style-fit analysis)
4. Backtest
5. Scanner


### Relative Strength v0.16.1 — 결과 우선 UX
- 5/20/60일 숫자 표보다 시장 주도형·단기 회복형·시장 소외형 등 프로그램 해석을 먼저 표시합니다.
- 미보유/보유 상태에 맞춘 대응 방향, 우선 전략, 판단 변경 조건을 제공합니다.
- 상세 수익률 표는 `근거 데이터 보기`로 접어 메인 화면의 정보 과부하를 줄였습니다.


### Beginner Explanation Layer v0.16.2
- RSI, MA20, ATR, 거래량비, 지지선, 저항선 등 핵심 지표에 초보자용 쉬운 설명을 추가합니다.
- 정의만 보여주지 않고 현재 계산값이 실제로 어떤 상태를 뜻하는지 동적으로 번역합니다.
- Risk Gate, 전략 무효화 기준, 손절 참고구간, 목표가, R:R, 상대강도 등 위험·전략 용어에도 `?` 도움말을 제공합니다.
- 전체 용어 사전에서 돌파, 눌림목, 모멘텀, 과매수/과매도, EOD, 공시 영향 등의 개념을 다시 확인할 수 있습니다.
- 각 설명은 `한줄 설명 → 현재값 해석 → 자세한 의미 → 주의점` 순서를 사용합니다.


### Beginner Help Popover v0.16.3
- `?` 도움말은 바깥 클릭/탭 시 자동으로 닫힙니다.
- `ESC`로 닫을 수 있고, 같은 `?`를 다시 누르면 토글됩니다.
- 다른 `?`를 열면 기존 도움말은 자동으로 닫혀 한 번에 하나만 표시됩니다.
- 팝오버가 화면 오른쪽/아래쪽 밖으로 잘리지 않도록 뷰포트 기준 위치를 자동 보정합니다.
- 모바일에서도 동일하게 바깥 탭으로 닫히며, 별도 닫기 버튼을 제공합니다.

### Sector Relative Strength v0.16.4
- 시장 상대강도에 더해 `종목 vs 같은 업종` 상대강도를 추가합니다.
- OpenDART `induty_code`를 보수적인 업종 그룹으로 매핑하고, 실제 KRX KOSPI/KOSDAQ 업종지수 이름이 확인될 때만 계산합니다.
- 메인 결과는 `시장·업종 동시 주도형 / 독립 강세형 / 업종 수혜형 / 업종 내 열위형 / 시장·업종 동시 소외형`처럼 결과 중심으로 표시합니다.
- 5/20/60거래일 원시 데이터는 `근거 데이터 보기` 안에서 시장/업종을 나눠 확인할 수 있습니다.
- 추세추종·눌림목·돌파·모멘텀 지속 전략은 시장 상대강도와 업종 상대강도를 함께 반영합니다.
- 업종 자동 매핑이 불확실하면 임의 추정하지 않고 시장 상대강도만 사용합니다.

**v0.17.1까지 완료했습니다.** Analysis Hub는 행동 계획을 먼저 보여주고, Fundamental Engine은 최신 정기보고서를 전년 동일 기간과 비교합니다. 다음 큰 단계는 v0.18 Investor Style Engine입니다.


### Analysis Hub v0.16.5
- 분석 결과를 긴 보고서처럼 전부 펼쳐 놓지 않고 `종합 요약`을 먼저 보여줍니다.
- 상세 영역은 `종합 / 전략 / 위험 / 상대강도 / 공시 / 지표` Navigation으로 한 번에 하나만 표시합니다.
- 새로운 분석을 실행하면 항상 종합 화면부터 시작합니다.
- 종합 화면은 각 엔진의 긍정/주의/부정 신호를 합쳐 현재 대응, 핵심 근거, 판단 변경 조건을 먼저 제공합니다.

### Pullback Confirmation Engine v0.16.5
- `눌림 지지 확인`을 사용자에게 요구하지 않고 앱이 직접 판정합니다.
- 상태: 눌림목 아님 / 눌림 진행 중 / 지지구간 접근 / 지지 테스트 중 / 반등 확인 / 지지 실패
- 상승 추세, 조정 폭, 지지 접근, 실제 지지 유지, 가격 반등, RSI 회복, 거래량을 자동 점검합니다.
- 장중 현재가만 입력해 확정할 수 없는 항목은 추측하지 않고 `미확정`으로 표시합니다.
- 눌림목 전략의 대응 문구도 자동 확인 결과를 우선 보도록 변경했습니다.

### Decision Status & Auto Check UX v0.16.6
- `앱 자동 확인 대기` 같은 모호한 표현을 제거하고 `지지 테스트 중`, `반등 신호 대기`, `지지 실패` 등 실제 자동 판정 단계를 표시합니다.
- Analysis Hub에서 눌림·지지 조건의 확인 개수, 부족한 조건, 데이터 기준(EOD/장중 Preview), 다음 자동 재판정 시점을 짧게 보여줍니다.
- 상세 전략 화면에서는 아직 확인 중인 조건의 현재 값과 이유를 먼저 보여주고, 전체 7개 체크는 기본 접힘으로 이동합니다.
- 장중 Preview에 오늘 저가/누적 거래량이 없으면 선택 입력 힌트를 제공하되 필수 입력으로 요구하지 않습니다.
- 조건 진행도는 상승확률이나 전략 성공확률이 아니라 자동 확인 체크리스트 진행도입니다.
- 향후 돌파·추세·지지반등 자동 판정에도 재사용할 수 있도록 공통 `auto_check` 상태 모델을 추가했습니다.


### Fundamental Engine v0.17
- OpenDART 연간 사업보고서의 연결재무제표를 우선 사용하고, 없으면 별도재무제표로 fallback합니다.
- 매출·영업이익·순이익·ROE·ROA·부채비율·유동비율·영업현금흐름을 최근 여러 연도끼리 비교합니다.
- `고품질 성장형 / 수익성 개선형 / 저성장 안정형 / 외형 성장·이익 부진형 / 재무 주의형 / 적자·수익성 주의형 / 혼합형`으로 결과를 먼저 분류합니다.
- PER/PBR은 KRX 확정 가격 기준과 사용자 참고가격 Preview를 분리하며, 낮은 배수를 저평가로 단정하지 않습니다.
- Analysis Hub에 `재무` Navigation과 `재무 체력` 종합 신호를 추가했습니다. 가격 흐름이 강하지만 재무가 약한 경우 두 분석축의 충돌을 종합 결론에서 직접 설명합니다.
- 상세 재무제표 숫자는 기본 접힘으로 유지하고 사용자가 원할 때만 최근 연도별 근거를 펼칩니다.
- ROE, PER, 부채비율, 영업현금흐름 등 재무 용어를 초보자 설명 레이어에 추가했습니다.

다음 단계: **v0.18 Investor Style Engine** — Buffett / Graham / Peter Lynch / CAN SLIM의 공개적으로 알려진 투자 원칙을 v0.17.1의 최신 재무·장기 재무 데이터를 결합해 스타일 적합도와 근거/약점을 설명합니다.


### Action Plan UX + Fundamental Freshness v0.17.1
- Analysis Hub 첫 화면을 `분석 결과 나열`에서 `현재 행동 계획` 중심으로 재구성했습니다.
- `지금 할 것 / 지금 피할 것 / 앱이 자동으로 보는 가격 기준 / 다음에 결론이 바뀌는 조건`을 먼저 보여줍니다.
- 전략 적합도 점수와 실제 현재 행동 단계를 분리해 `100점 = 지금 진입`으로 오해하지 않도록 했습니다.
- 현재 결정에 중요한 분석 3개만 먼저 표시하고 나머지 분석은 기본 접힘으로 이동했습니다.
- Analysis Hub 및 상세 화면의 본문·카드·Navigation 글자 크기와 줄간격을 전반적으로 키웠습니다.
- OpenDART 정기보고서는 1분기(11013), 반기(11012), 3분기(11014), 사업보고서(11011)를 지원합니다.
- 최신 사용 가능한 정기보고서를 자동 선택하며 분기/반기/3분기 실적은 전년 **동일 기간 YoY**와만 비교합니다.
- 최신 상반기 실적과 전년도 연간 실적을 직접 성장률로 비교하지 않습니다.
- 장기 추세·ROE·PER/PBR 기준은 최근 연간 사업보고서 데이터를 별도로 유지합니다.

### Investor Style Engine + Style Playbook v0.18
- Buffett / Graham / Peter Lynch / CAN SLIM 스타일을 StockScope의 재무·상대강도·공시·시장 데이터로 모델링합니다.
- `투자스타일` Navigation에서 각 방식의 핵심 철학, 투자 진행 순서, 잘 맞는 사용자, 덜 맞는 사용자부터 먼저 설명합니다.
- 종목별 스타일 적합도와 평가 커버리지를 제공하며 UNKNOWN 조건은 0점 벌점으로 처리하지 않습니다.
- 사용자가 `StockScope 자동 / Buffett / Graham / Lynch / CAN SLIM` 관점을 직접 선택해 해당 스타일 기준의 현재 적용 방향·확인 항목·재평가 조건을 볼 수 있습니다.
- 간단한 3문항 성향 안내로 자신이 어떤 투자 철학과 가까운지 학습용으로 비교할 수 있습니다.
- 장기 투자 스타일 적합도와 현재 단기 Action Plan은 서로 다른 판단으로 명확하게 분리합니다.
- 모든 스타일 점수는 상승확률·수익률 예측·실제 매수/매도 신호가 아닙니다.


### Investor Style Action Engine v0.18.1
- 스타일 적합도에서 끝나지 않고 `현재 행동 → 앱 자동판정 → 이유 → 자동 재확인 조건 → 상세 데이터` 순서로 제공합니다.
- Buffett/Graham/Lynch/CAN SLIM의 계산 가능한 재무·가격 조건은 StockScope가 직접 판정하며 사용자에게 수동 확인을 요구하지 않습니다.
- 스타일 적합성과 현재 단기 진입 단계는 분리하며 Risk Gate와 눌림·지지 자동판정을 현재 행동에 함께 반영합니다.
- 새 실적·가격·시장 데이터가 들어오면 앱이 조건을 자동 재평가합니다.

### Entry Timing Action Engine v0.18.2
- `반등 확인 대기`만 보여주던 단기 진입 상태를 `현재 행동 → 자동 확인 진행도 → 확인됨/부족 → 가격 기준 → 자동 재판정` 구조로 확장했습니다.
- 가격 반등은 EOD의 실제 시가/종가/지지 anchor 또는 장중 Preview의 실제 저가/현재가를 사용하며 근거 없는 확인 가격을 만들지 않습니다.
- 장중 RSI Preview는 최신 확정 EOD RSI와 비교해 회복 여부를 자동 판정합니다.
- 미보유는 `신규 추격 대기`, 보유는 `보유 관찰/추가매수 보류`처럼 행동을 분리합니다.
- Analysis Hub에는 기업 조건·전략 형태 적합도·단기 타이밍을 짧게 압축하고 상세 조건은 기본 접힘으로 유지합니다.
- Buffett/Graham은 단기 타이밍을 보조축으로, Lynch는 중요축으로 처리합니다.
- CAN SLIM은 Pullback 상태를 잘못 재사용하지 않고 C/S/L/M(최근 실적·수요/거래량·주도력·시장)의 자체 타이밍을 사용합니다.
- Pullback 계열이 아닌 전략에서는 눌림 지지 실패가 현재 상위 전략의 행동을 잘못 차단하지 않도록 분리했습니다.
- 조건 확인 개수와 스타일/전략 점수는 상승확률이 아닙니다.

현재 구현 기준: **v0.18.2 완료 → 다음 큰 단계 v0.19 Backtest**
