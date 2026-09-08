# StockScope API 키 발급 가이드

이 문서는 새 개발 PC에서 StockScope를 Clone한 뒤 필요한 데이터 공급자 인증을 준비하기 위한 안내입니다.

## 1. KRX OPEN API

공식 사이트: https://openapi.krx.co.kr/

KRX 공식 이용절차는 다음 순서입니다.

1. Data Marketplace 회원가입 / 로그인
2. API 인증키 신청
3. 서비스 목록에서 필요한 API 검색
4. 각 API 활용 신청
5. 관리자 승인 후 사용

### StockScope에서 신청할 서비스

#### 주식

- 유가증권 일별매매정보
- 코스닥 일별매매정보
- 유가증권 종목기본정보
- 코스닥 종목기본정보

#### 지수

- KOSPI 시리즈 일별시세정보
- KOSDAQ 시리즈 일별시세정보

> 인증키가 발급돼도 위 서비스 활용승인이 없으면 API별로 401이 발생할 수 있습니다.

### 신청 목적 예시

> 개인 프로젝트용 주식 분석 웹 애플리케이션 개발을 위해 국내 주식의 종목정보, 일별 시세, 지수, 거래량 데이터를 조회하고 전략 분석·백테스트·시뮬레이션 기능을 구현하는 용도로 사용합니다. 실제 매매 주문 기능은 제공하지 않습니다.

### `.env`

```env
KRX_API_KEY=발급받은_인증키
```

## 2. OpenDART

공식 사이트: https://opendart.fss.or.kr/

1. OpenDART 접속
2. 인증키 신청 메뉴에서 인증키 발급
3. 발급받은 인증키를 `.env`에 설정

```env
DART_API_KEY=발급받은_인증키
```

StockScope는 현재 OpenDART에서 기업개황, 고유번호 매핑, 최근 공시 등의 데이터를 사용합니다.

## 3. 최종 `.env` 예시

```env
KRX_API_KEY=
DART_API_KEY=
ENVIRONMENT=development
```

실제 인증키는 `.env.example`이나 README에 넣지 마세요.

## 4. 연결 확인

StockScope 실행 후 화면 우측 상단에서 다음 상태를 확인합니다.

- `API 정상`
- `KRX` 활성
- `DART` 활성

Swagger에서도 확인할 수 있습니다.

http://127.0.0.1:8000/docs

## 5. KRX 401 체크리스트

- `.env`에 KRX 인증키가 정확한가?
- 백엔드를 `.env` 수정 후 재시작했는가?
- 조회 중인 API의 활용 신청이 승인됐는가?
- 위 6개 StockScope 필수 서비스가 모두 활성화됐는가?

## 보안

- 실제 API 키를 채팅, GitHub Issue, Screenshot에 노출하지 않습니다.
- 키가 GitHub에 한 번이라도 Push됐다면 삭제만 하지 말고 해당 키를 폐기/재발급하는 것이 안전합니다.
