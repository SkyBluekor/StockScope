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
- Node.js / npm
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

- `.venv` 생성
- FastAPI 의존성 설치
- 백엔드 테스트 실행
- 프론트 `npm install`
- 프론트 빌드 검증

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

KRX를 일별 확정 데이터 소스로 사용하기 때문에 장중에는 당일 데이터가 아직 없을 수 있습니다. StockScope는 최근 사용 가능한 거래일을 자동 탐색합니다.

### `.env`를 수정했는데 반영되지 않음

백엔드 개발 서버를 종료 후 다시 실행하세요.

### `setup.ps1`이 실행되지 않음

```powershell
Unblock-File .\setup.ps1
```

그래도 현재 PowerShell 프로세스에서만 임시 허용해야 한다면:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

시스템 전체 실행정책을 낮추는 방식은 권장하지 않습니다.


### OpenDART Event Risk

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
