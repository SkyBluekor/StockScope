# StockScope — 제품 목표·범위·고정 실행계획

> **상태:** 사용자 검토·확정 대기 (2026-11-01, KST)  
> **실제 프로젝트:** C:\TAEWOO\CapstonDesign\StockScope  
> **실제 Git 브랜치:** codex/jev-reviewer-shadow-bridge  
> **문서 지위:** 제품 요구사항·개발 우선순위·진행 상태의 단일 기준. 기술적 Frozen Contract·데이터 보존·보안은 기존 Architecture / Implementation Baseline을 함께 준수한다.  
> **이번 작업:** 문서화만. 사용자 승인 전 제품 코드를 변경하지 않는다.

## 1. 제품을 한 문장으로 정의

**StockScope는 국내 주식 다수 종목의 OpenAPI 기반 주가·시장·경제·기업·국제 정세 데이터를 자동으로 수집·검증하고, 전체 시장 위험과 산업·종목 특성 및 다양한 투자 전략을 종합하여 위험 대비 기대성과가 유리한 접근법을 비교하고, 필요한 판단에만 JEV를 보조 엔진으로 활용해 주식 초보자도 쉽게 이해하도록 설명하는 투자 판단 보조 프로그램이다.**

- **제품의 목적은 더 나은 투자 판단**이지 JEV 호출 성공, 백테스트 PASS, 방대한 기술 로그 생산이 아니다.
- 투자 전략만으로 종목을 판단하지 않는다. 미국 금리·환율·증시·전쟁·호르무즈 해협·코스피 급락 같은 전체 환경도 필수 입력이다.
- 목표는 무조건 높은 예상 수익 숫자가 아니라 **위험·거래비용·투자 기간을 고려한 기대성과 개선**이다. 미래 수익 보장이나 검증되지 않은 수익 확률로 표현하지 않는다.
- 종목 수가 많으므로 **반복 작업은 프로그램이 수행**한다. 사용자가 종목별로 시장 자료를 찾아 복사하거나 투자 조건·관찰 문장 두 개를 입력할 필요가 없어야 한다.
- StockScope는 매매 판단을 **보조**하며 실제 주문을 수행하지 않는다.

## 2. 사용자 경험 — 사용자가 실제로 얻어야 하는 결과

1. 수많은 종목에서 **지금 관심 가질 후보**를 자동으로 찾는다.
2. 오늘 국내외 시장이 위험한지, 무엇 때문에 그런지 간단히 확인한다.
3. 해당 종목에 적합한 **투자 방식·단기/중기/장기 기간**과 진입/관망 조건을 비교한다.
4. **왜 후보인지 / 왜 위험한지 / 조건이 깨지면 어떻게 대응할지** 쉬운 한국어로 본다.
5. 보유 중이라면 신규 매수 후보와 구분하여 보유·축소·손실 대응 시나리오를 참고한다.
6. 데이터가 부족하거나 사건 영향이 불확실하면 억지 추천을 받지 않고 **관망·자료 부족·주의** 상태를 확인한다.
7. JEV가 실제 추가 검토를 했다면 **기본 분석과 무엇이 다른지** 확인한다. 모델 미실행/오류/추정은 실제 모델 검토로 위장하지 않는다.

**사용자가 하지 않을 일:** 종목마다 직접 문장 작성, 경제용어·해시·HOLD·V4/V5·Fake 상태 해석, 여러 페이지를 읽어야 결론을 알 수 있는 작업.

## 3. 필수 분석 차원

| 범주 | 반드시 고려할 요소 | 분석의 목적 |
|---|---|---|
| 글로벌·거시경제 | 미국 기준금리·물가·고용, 주요 미국 증시, 달러/원, 시장 금리, 국제유가·변동성 등 허용된 자료 | 국내 시장·산업에 대한 외부 압력과 기회 |
| 국제 사건·정책 | 전쟁, 호르무즈 해협·원유/물류 차질, 관세·제재·정책 변화 | 사건 신뢰도, 업종 노출, 영향 시차·불확실성 |
| 국내 시장 | KOSPI/KOSDAQ 급락·회복, 시장 변동성·유동성·시장 폭, 공식 수급(제공 시) | 개별 종목의 매수 신호와 전체 시장 위험 구분 |
| 산업·기업 | 산업 강약, 실적·재무·공시, 기업 특성·위험, 해외 요인 민감도 | 동일 사건도 종목마다 영향이 다른 이유 |
| 투자 전략 | 현재 10개 전략, 가격·거래량·추세·돌파·가치 등 지원 범위, 단/중/장기 | 종목·기간에 맞는 전략 및 대안 비교 |
| 위험·성과 | 전략 무효화, 손실 참고 구간, 기대손익비, 변동성, 비용, 최대 낙폭, 과거 성과·표본 | 수익 가능성과 손실 가능성의 균형 |

### 사건을 분석할 때의 원칙

- **KOSPI 급락:** 종목 매수 조건이 좋아도 시장 변동성과 업종·종목 상대 강도를 함께 보고, 실제 진입은 관망할 수 있어야 한다.
- **미국 금리·환율 급변:** 환율·금리 충격이 업종·기업에 따라 다르므로 일률적으로 매수/매도하지 않는다.
- **호르무즈 해협·전쟁:** 유가·해운·항공·화학·정유 등의 영향 경로를 점검하되, 비용·수요·마진·사전 가격 반영을 구분한다. 사건 헤드라인만으로 종목 방향을 확정하지 않는다.
- **기업 공시:** 공식 기업 연결·접수일·정정 여부·최초 관측시각을 검증한다. 공시 존재만으로 전략과 충돌한다고 판단하지 않는다.
- **사건 정보 없음/검증 실패:** 근거 없음과 위험 없음은 다르다. 신뢰 가능한 데이터가 없다면 미확인으로 표시한다.

## 4. 목표 데이터·판단 구조

1. **OpenAPI 및 허용 원천 수집:** KRX 국내 주가·지수, OpenDART, 실제 이용할 수 있는 글로벌·거시경제·사건 자료.
2. **데이터 품질:** 출처·게시시점·최초 관측·수집시각·거래일·결측·정정·사용권 검증.
3. **시장 환경 판단:** 국내/해외 위험과 사건이 특정 산업에 영향을 줄 가능성·근거·확실성 구분.
4. **종목·전략 판단:** 기존 Scanner 및 10개 전략·Risk·Horizon을 재사용하여 종목 적합성과 **현재 진입 적합성**을 분리.
5. **위험 대비 비교:** 동일한 비용·기간·시장 조건에서 전략별 성과와 손실 위험을 비교. 수익 보장 숫자는 없음.
6. **선택적 JEV:** 로컬 분석이 불확실하거나 상충하는 **일부 우선 후보**만 검토. 전 종목 유료 호출은 기본 전략이 아님.
7. **초보자용 출력:** 종목/추천 전략/기다릴 조건/위험/쉬운 이유/데이터 기준시각. 실제 JEV 결과가 있으면 별도 표시.

**핵심 불변식:** 종목 자체의 전략 신호가 좋더라도 시장 전체가 위험하다면 **후보의 전략 적합성**과 **오늘 진입해도 되는지**를 다르게 판정한다. JEV는 기존 Risk Gate·Scanner 순위·주문·Holdings를 임의 변경하지 않는다.

## 5. 데이터와 검증에 관한 공통 계약

- 실제 API 데이터, 캐시, 테스트/Mock, 사용자 입력, 시뮬레이션, JEV 모델 응답을 **서로 분리**한다.
- KRX의 현재 기반은 **장중 실시간이 아닌 EOD 확정 일별 데이터**다. 확인되지 않은 값은 실시간으로 표시하지 않는다.
- 모든 경제 지표와 사건은 발표시각·최초 관측시각·평가 기준일과 정정 이력을 구분한다. 미래 정보를 과거 매매 판단에 소급 적용하지 않는다.
- API로 **조회 가능한 권한**, 로컬 **보존·파생 가공 권한**, 제3자 **AI 전송 권한**은 다르다. 권한이 미확인된 공시·뉴스·시장 데이터는 TypeSafe로 보내지 않는다.
- 서로 다른 공급자의 시차·누락·오류는 자동 성공으로 채우지 않는다. 필요한 기능만 제한하고 나머지 분석은 계속 동작한다.
- 수익 성능 검증에는 수수료·슬리피지·진입/청산 시점·최대 낙폭·손실 분포·표본수·시점 분리 검증을 포함한다.
- 모델/전략을 검증 데이터에 맞춰 사후 튜닝하거나 생존자 편향·미래정보 누수로 성과를 부풀리지 않는다.
- 기존 사용자 DB와 Scanner·Strategy·Risk·Horizon·Holdings·Frozen 캡처는 승인 없는 덮어쓰기/재생성 금지. 필요 변경에는 백업·회귀·사용자 승인.

## 6. JEV의 역할과 현재 구현의 문제

### JEV는 이렇게만 쓴다

- **목적:** 많은 종목을 더 효율적이고 정확하게 평가하도록 **추가 검토의 우선순위와 불확실성을 보완**하는 것.
- **입력:** 프로그램이 이미 수집·검증하고 제3자 전송이 허용된 정보를 자동으로 구성. 사용자가 종목마다 분석 질문을 작성하지 않는다.
- **선별:** 먼저 로컬 엔진으로 광범위하게 평가하고, 해석 충돌·확실성 부족·큰 사건 영향이 있는 종목에만 선택적으로 JEV 사용.
- **출력:** 기존 분석과 비교 가능한 제2 의견, 실제 모델 ID/질문/시각/비용/검토 불가 이유. **사용자에게 쉬운 표현으로 설명**.
- **평가:** 로컬 단독 대비 판정 품질·오탐·누락·지연·비용을 실제 데이터로 비교. JEV가 더 정확하다고 가정하지 않는다.
- **제약:** 실제 TypeSafe가 지원하는 질문/응답 계약의 한계를 먼저 확인. 제공하지 않은 시장 데이터를 모델이 스스로 확인한 것처럼 표현하지 않는다. 실모델 비용은 사용자가 별도 실행 승인.

### 기존 잘못된 B단계 처리

- 현 브랜치의 사용자 문장 두 개 비교 기능(예: backend/app/jev/owned_review_b.py, frontend/src/components/ScannerOwnedReviewB.tsx)은 **코드와 테스트는 존재하지만 StockScope 제품 목표에 부적합**하다.
- **제품 B단계 완료로 인정하지 않음.** 실제 시장 데이터의 JEV 종목 분석이 아니다.
- **이 구현에 대한 유료 API 실호출 진행 금지.** 기존 비활성 설정을 유지하고, 승인된 후속 관련 작업에서 불필요한 입력 UI를 제거/격리한다. 지금은 코드 삭제·수정 없이 상태만 기록한다.
- 기존 JEV 단일 실행계획서의 **문장 비교 → 실모델 1회 → 문장 비교 효용** 순서는 본 문서의 제품 순서로 교체한다. 이미 확인된 **A단계 간결 UI 성과는 보존**한다.

## 7. 초보자용 화면 원칙

기본 화면에서 한눈에 보이는 내용:

- **오늘 시장:** 평온/주의/위험과 핵심 이유 1~3개, 데이터 기준시각.
- **후보 목록:** 종목 이름, 적합한 전략·기간, 관심/조건부/관망/주의, 주요 근거.
- **종목 상세:** 왜 후보인지, 왜 지금 진입을 기다려야 하는지, 어떤 조건이 깨지면 다시 판단해야 하는지.
- **보유 중:** 신규 매수 후보와 다른 위험·계획·대응 정보.
- **JEV:** 실제 실행한 경우에만 보조 의견과 기존 판단의 차이.

기술 이름·해시·HOLD·Mock·상태 열거를 기본 화면에 반복하지 않는다. 상세 원천/진단은 펼쳐보기로 제공한다. 전문 경제용어는 툴팁이나 쉬운 말로 설명한다.

**설명용 예시(실제 투자 추천 아님):** "종목 A — 중기 추세추종에 적합하나 현재는 관망. 주가 흐름은 양호하지만 국내 시장 변동성이 커서 지금 진입 시 손실 위험이 높습니다. 시장이 안정되고 진입 조건이 다시 충족되는지 확인하세요."

## 8. 현재 상태 — 코드 기반과 실사용 검증 구분

| 영역 | 확인된 내용 | 미확인/미완료 |
|---|---|---|
| KRX EOD·시장 지수·종목 검색 | 현재 README에 구현 기재 | 실제 PC 최신 원천·결측·운영 안정성 |
| OpenDART 기업·공시 | 기존 코드와 사용자 Windows 실제 공시 조회 사례 | 지속 수집, 산업/종목 의미 연결 범위 |
| 기존 10전략·Scanner·Risk·Horizon·Holdings | README와 Architecture에 기반 구현 기재 | 국제 사건·글로벌 매크로가 실제 최종 판단에 반영되는 정도 |
| 백테스트·시뮬레이션 | 기존 구조·설계 존재 | 시점 분리·실제 비용·전략 비교·표본 충분성 |
| TypeSafe 제공자 | 기존 provider·합성 호출 기록과 테스트 존재 | 실종목의 적법한 자동 입력에 대한 실제 추가 가치 |
| A단계 사용자 UI 간소화 | 실제 Windows 스크린샷 및 CI | 유지 |
| B단계 문장 2개 비교 | 기능 구현·화면 존재 | **제품 목표 불합격**, 실종목 자동 분석 아님 |

"기반 구현 존재"는 **현재 실행에서 정상 연결됐다는 뜻이 아니다.** 미검증 부분을 완료로 주장하지 않는다.

## 9. **고정 실행 순서** — 승인 후 순차 진행

### 1단계: 실제 구현·데이터 연결 현황 확인 — 실행 명세 v1

**작업 상태:** SPEC_READY / IMPLEMENTATION_NOT_STARTED. 이 작업은 **분석·현황 확인**이며 기능 구현, 기존 로직 수정, DB 변경, 신규 JEV 호출이 아니다. 사용자에게 구현을 지시받기 전에는 아래 작업을 실행하지 않는다.

**실제 작업 기준:** C:\TAEWOO\CapstonDesign\StockScope · codex/jev-reviewer-shadow-bridge. 시작 시 git branch --show-current, git rev-parse --short HEAD, git status --short로 브랜치/커밋/로컬 변경 상태를 확인한다. 다른 브랜치, C:\Projects, 사용자 보유 DB의 대체본을 이용하지 않는다. 사용자의 최신 커밋과 원래 파일은 모두 보존한다.

#### 목표 / 이 단계에서 답할 질문

> "현재 StockScope는 실제 API의 국내외 시장·국제 정세·기업 정보를 어디까지 읽고, 이를 어떤 경로로 Scanner의 종목/전략/위험 판단에 반영하는가? 끊어진 연결 중 제품 가치에 가장 큰 영향을 주는 **하나**는 무엇인가?"

**핵심:** 시장/이벤트 분석 코드가 존재한다는 사실과, 실제 종목 Scanner의 최종 판단에 그 값이 적용된다는 사실은 다르다. 두 경로를 반드시 분리해 확인한다. 특히 현재 StrategyEngine._risk_gate에는 market_regime == PANIC, event_risk 입력 차단이 이미 존재하므로 이것을 "미구현"이라고 단정하지 말고 **원천 데이터가 어디에서 생성되어 이 필드까지 도달하는지** 추적한다.

#### 조사 순서 — 1→2→3→4→5→6, 병렬 확장 금지

1. **원천·시각 현황 확인:** KRX EOD 주가/지수, OpenDART 공시·기업, 국내 시장 위험, FRED 등 해외 거시·환율·국제 이벤트/뉴스 사용 가능 경로를 조사한다. 각 데이터에 대해 실제 provider 또는 로컬 DB, 최신 관측 기준일, 수집/발표/사용 가능 시각, 결측·오류, 표시/파생/외부 AI 전송 권한을 기재한다. "API 연결됨"과 "현재 DB에 실제 데이터 있음"은 별개 상태로 기록한다. 지표/이벤트가 존재하지 않으면 없는 그대로 기록한다.
2. **시장·매크로 영향 소비자 확인:** backend/app/api/macro.py의 /market-stock-impact, /event-reference는 **reference/shadow** 응답임을 확인하고, 실제 Scanner job 결과나 StrategyInput에 연결되는 호출 지점을 검색한다. 산업/종목 연결도 '기업·업종 식별이 확인되는지'와 '최종 전략 평가의 입력인지'를 구분한다.
3. **전략·Risk 실제 경로 확인:** backend/app/api/backtest.py의 _run_scanner_job → app.backtest.scanner.StockScannerService → 전략/시장 위험/기간/리스크 산출 → 최종 결과 형성을 추적한다. backend/app/strategy/engine.py의 market_regime, event_risk, tradable, liquidity_ok, extreme_move 차단 입력의 **생산자·시간·fallback**을 확인한다. RiskEngine, 기존 10개 전략, Horizon의 실사용/참고/차단 여부를 별도 표시한다. Strategy score는 수익 확률이 아니며, 입력 누락 시 기본값이 무엇인지 확인한다.
4. **성과·검증 소비자 확인:** 현재 backtest/Prospective/Execution의 과거/향후 평가 경로가 실제 후보/전략별 **수익과 손실·비용·표본·평가 기간**을 어디까지 계산하고, Scanner 사용자 화면에서 그 정보를 직접 활용하는지 확인한다. 확인 전 "최고 수익 전략 판별 완료"라고 쓰지 않는다.
5. **JEV 실제 입력 확인:** backend/app/api/jev.py, app/jev/review_service.py, owned_review_b.py, frontend/src/components/ScannerAiReview.tsx, ScannerOwnedReviewB.tsx를 확인한다. 기존 Scanner 결과가 실제 TypeSafe wire에 들어가는지/어떤 권한으로/어떤 질문으로 들어가는지 분리하여 기재. **사용자 직접 작성 문장 2개 비교는 제품 목표 불합격**이며 실제 종목·시장 JEV 분석이라고 인정하거나 유료 실행하지 않는다.
6. **현재 Windows 사용자 흐름 관찰:** 기존 Windows 환경에서 마지막 완료된 **실제 종목 1개**(예: 과거 확인된 선익시스템 171090; 현재 데이터가 다르면 사용자가 선택한 기존 후보)로 기존 Scanner 화면·API 응답·데이터 기준일·위험/전략 판단을 확인한다. 먼저 **이미 저장된 결과/DB 조회만** 사용하고 외부 OpenAPI 재조회나 신규 Scanner 실행이 필요하면 사용자에게 비용·데이터 쓰기 여부를 밝힌 뒤 별도 진행한다. PC에 직접 접근할 수 없다면 코드만으로 확인된 항목과 **Windows UAT 미실시**를 분리하며 임의 성공 처리하지 않는다.

#### 꼭 확인할 기존 소스(시작점, 전체 목록이 아님)

- 수집: backend/app/market/providers/krx.py, backend/app/api/news.py, backend/app/api/macro.py, 기존 OpenDART API/provider, 관련 source policy.
- Scanner: backend/app/api/backtest.py (_run_scanner_job), backend/app/backtest/scanner.py (StockScannerService), backend/app/strategy/engine.py, backend/app/risk/engine.py, backend/app/horizon.py.
- 저장·평가: backend/app/prospective/catalog.py, 기존 Backtest/Execution·Market/Macro Store.
- 사용자 표시/JEV: frontend/src/components/ScannerPanel.tsx, ScannerAiReview.tsx, ScannerOwnedReviewB.tsx, backend/app/api/jev.py, backend/app/jev/review_service.py, owned_review_b.py.
- 확인 대상: 실제 호출 관계·생성되는 객체/필드·최종 응답/화면. 파일명만 나열하거나 README 문구로 "연결 완료" 판정하지 않는다.

#### 결과물 — **이 문서 한 곳에만** 기록

**A. 데이터·의사결정 연결표** (각 항목 1행)

| 데이터/요인 | 실제 원천·기준시각 | 최종 소비자(실제 함수/필드) | 상태 | 근거 | 사용자 결과에 미치는 영향 |
|---|---|---|---|---|---|

항목은 최소 KRX 주가, KOSPI/KOSDAQ 지수 급락, 글로벌 금리/환율/해외지수, 국제 사건(전쟁/호르무즈 등), 산업·공시, 10개 전략, Risk/Horizon, 과거성과·위험, JEV를 포함한다.

**상태는 정확히 하나:** VERIFIED_CONNECTED(실제 최종 출력까지 확인), IMPLEMENTED_NOT_CONNECTED(구현은 있으나 최종 출력 미연결), DATA_UNAVAILABLE(원천/현재 데이터 부족), RIGHTS_BLOCKED(허용 범위 차단), UNVERIFIED(코드·Windows 확인 부족). 동일 항목에 혼합 사유가 있으면 대표 상태를 택하고 근거에 다른 차단을 함께 적는다. "코드에 클래스 있음"만으로 VERIFIED_CONNECTED 금지.

**B. 실제 종목 1개 추적표**

- 종목명/코드/시장, 조회한 캡처 ID 또는 결과 식별자, 분석 기준일과 데이터 시각.
- 현재 기본 Scanner 판단/전략/기간/Risk(실제 값 또는 미확인).
- 글로벌·시장 위험과 국제 사건이 **실제 판단에 반영된 값 / 단순 별도 표시 / 데이터 없음** 중 어디에 해당하는지.
- JEV 결과가 없으면 **모델 미실행**, 기존 B 입력 방식은 제품 미적합으로 표시.
- 실제 Windows 사용자 관찰 여부, API 성공·실패/DB 원본 불변 여부.

**C. 핵심 결함 한 가지와 다음 단계 범위**

- 가장 큰 결함 한 가지를 **정확한 생산자 → 끊긴 소비자 → 사용자 체감 문제**로 기술한다.
- 기존 재사용 가능한 코드와 필요한 최소 연결 변경만 추려 **2단계 작업 후보**로 연결한다.
- 영향이 큰 문제가 여러 개여도 제품의 다음 단계는 하나만 제시. 원천 권한·실데이터 미확인 등 막힌 이유는 정직하게 기술하고 임의 구현하지 않는다.

#### 금지 및 회귀 조건

- **이번 단계에서는 제품 소스, SQL 스키마, 사용자 DB, UI, 모델 프롬프트, Strategy/Risk 판정, 기존 Frozen 검증 자료를 수정하지 않는다.**
- 외부 JEV/TypeSafe 호출·유료 토큰 소비·신규 데이터 배치 수집 금지. 개발자용 진단기/Mock 테스트/새 상태 패널/새 보고서 파일 추가 금지.
- 보안: API 키·토큰·보유계좌·원문 개인정보를 문서나 콘솔 로그에 기록하지 않는다. 사용권을 추측으로 승인 처리하지 않는다.
- 테스트는 필요할 때 기존 읽기 전용 검사·기존 UI를 활용한다. 테스트 수행 자체가 DB migration/캐시/재수집 write를 유발하면 실행 전에 범위를 확인한다.
- 자료가 없는 경우 임의 숫자·수익률·사건 시나리오로 결과를 채우지 않는다. CI 통과 ≠ 실제 Windows 종목 연결 통과.
- **완료되면 멈춘다.** 이 단계에서 2단계 기능 코드를 미리 구현하지 않는다.

#### 1단계 완료 판정

1. A/B/C 결과가 이 문서의 1단계 결과란에 기록됨.
2. 대표 종목을 통해 최종 Scanner 소비 여부가 확인되거나, 사용자 Windows 확인 불가 항목을 구체적 미완료로 표시함.
3. 제품 개선에 직접 연결되는 **최우선 결함 1개**와 기존 코드 재사용 지점이 밝혀짐.
4. 기존 소스·DB·정책·브랜치의 불필요한 변경이 없음을 확인함.
5. 사용자에게 간결하게 조사 결론과 **2단계에서 해결할 단 하나의 작업**을 제시함.

**1단계 조사 결과 (2026-11-01): CODE_AUDIT_COMPLETE / WINDOWS_UAT_PENDING**

**조사 방식과 한계:** 지정 브랜치의 GitHub 원본 파일들을 읽어서 함수·필드·API 호출 관계를 추적했다. 프로젝트 소스·SQL·런타임 DB를 수정하지 않았고 로컬/외부 시장 API 및 TypeSafe 유료 호출도 실행하지 않았다. 해당 Windows PC, 개인 API 키, KRX/DART/Macro DB, 실행 중인 서버에 직접 접근할 수 없으므로 실제 원천의 **최신 관측 날짜·수집 성공·실제 종목 가격/점수·DB 무결성**은 이번 조사에서 검증하지 못했다. 과거 사용자가 보여준 선익시스템(171090) UI는 **종목명이 표시되었다는 증거일 뿐**, 최신 실제 분석이 완료되었다는 근거는 아니다.

#### A. 데이터·의사결정 연결표 (현재 브랜치의 코드 근거)

상태: VERIFIED_CONNECTED = 실제 데이터부터 사용자 결과까지 확인, IMPLEMENTED_NOT_CONNECTED = 기능 존재하나 대상 판단 경로까지 미연결, DATA_UNAVAILABLE = 데이터 미확보 확인, RIGHTS_BLOCKED = 현재 정책의 사용권 제한, UNVERIFIED = 실제 실행·자료 또는 권한 확인이 부족. 이 표에는 **Windows 실행까지 검증된 VERIFIED_CONNECTED를 임의 부여하지 않는다.**

| 데이터·요인 | 원천·최종 소비 경로 | 상태 | 확인한 사실과 남은 확인 |
|---|---|---|---|
| **KRX 주가·거래량(EOD)** | KrxProvider → HistoricalMarketStore → StockScannerService._quick_current_candidate → BacktestEngine._signal_snapshot → 현재 전략/위험 → Scanner 후보 결과 | UNVERIFIED | **코드 경로 연결됨**. StockScannerService.run은 KOSPI/KOSDAQ 종목과 확정 지수 시계열로 후보를 계산. 로컬 실제 최신 데이터·날짜·API 권한은 미검증. [근거: scanner.py](../backend/app/backtest/scanner.py), [backtest.py](../backend/app/api/backtest.py) |
| **KOSPI/KOSDAQ 하락·상승** | KRX index_daily → BacktestEngine._signal_snapshot → regime_from_index → StrategyInput.market_regime → StrategyEngine | UNVERIFIED | **코드 경로 연결됨, 위험 구간 구현 불완전.** 현재 지수 변동률 판정은 TREND_UP/TREND_DOWN/RANGE/UNKNOWN만 반환. 정의된 PANIC/HIGH_VOLATILITY는 이 함수로는 생성 불가. Risk Gate의 PANIC 차단은 현재 Scanner의 이 입력 생성 경로에서는 도달 불가. [근거: strategy/context.py](../backend/app/strategy/context.py), [strategy/engine.py](../backend/app/strategy/engine.py), [backtest/engine.py](../backend/app/backtest/engine.py) |
| **미국 금리·거시 충격** | LocalMacroReader → MacroContext(현재 US 10Y DGS10 계열) → GET /api/macro/market-stock-impact 및 /event-reference, ProspectiveReferenceCaptureService | IMPLEMENTED_NOT_CONNECTED | 참고·평가 경로 존재. **이미 저장된 Scanner 결과 뒤에** reference가 붙으며 governance: decision_input/scanner_input/risk_gate_input/production_decision_approved 모두 False. 외환·미국 지수·금리 전 분야를 이 경로가 포괄한다고 주장하지 않음. Macro DB의 실데이터와 기준시각 미확인. [근거: macro/context.py](../backend/app/macro/context.py), [macro.py](../backend/app/api/macro.py), [reference_capture.py](../backend/app/prospective/reference_capture.py) |
| **전쟁·호르무즈·글로벌 사건** | 기존 Event Evidence reference, Naver 종목 뉴스 표시, Macro/Event 결합 조회 | IMPLEMENTED_NOT_CONNECTED | 일부 사건 근거 확인/표시 경로는 존재하지만, **구체적 글로벌 사건의 수집·산업별 영향·Scanner 최종 판단 소비자**는 확인된 코드 경로에 없음. 이벤트 자동 수집이 성공했다고 단정할 수 없음. 허용 원천·사건 종류·시점·업종 매핑을 별도 확인해야 함. [근거: api/news.py](../backend/app/api/news.py), [api/macro.py](../backend/app/api/macro.py), [event_evidence/policy.py](../backend/app/event_evidence/policy.py) |
| **OpenDART 공시 이벤트: 개별 종목** | StrategyAnalysisService.analyze → EventRiskAnalyzer.analyze → event_analysis.risk_gate → StrategyInput.event_risk → StrategyEngine | UNVERIFIED | **개별 종목 전략 분석의 공시 위험 연결 코드는 존재함.** DART API 성공·사건 위험 판정 실사례는 Windows 미검증. [근거: strategy/service.py](../backend/app/strategy/service.py), [market/event_risk.py](../backend/app/market/event_risk.py) |
| **OpenDART 이벤트: 다종목 Scanner** | StockScannerService → BacktestEngine._signal_snapshot(event_risk=False) | IMPLEMENTED_NOT_CONNECTED | **대량 후보 Scanner는 event_risk=False 고정.** 개별 종목 분석의 OpenDART 이벤트 위험은 Scanner 선별에 자동 전파되지 않음. Scanner 생성자는 기본 KRX만 받아 DART 호출도 없음. [근거: backtest/engine.py](../backend/app/backtest/engine.py), [backtest/scanner.py](../backend/app/backtest/scanner.py) |
| **산업 상대강도** | 개별 분석은 OpenDART 업종코드 + KRX 업종지수. Scanner는 optional sector_prefetcher → historical sector projection | IMPLEMENTED_NOT_CONNECTED | 개별 분석 경로 존재. Scanner 기본 생성 시 업종 prefetcher는 None이고 선택적 source를 넣어도 STATIC_CURRENT / production_enabled False로 남음. 업종 입력이 현재 Scanner 순위를 보편적으로 바꾼다고 말할 수 없음. [근거: strategy/service.py](../backend/app/strategy/service.py), [scanner.py](../backend/app/backtest/scanner.py) |
| **10개 전략 및 Risk** | StrategyEngine.evaluate_all(10개) → 선별된 정책 전략 → Scanner에서 **상위 최대 3개**를 current 조건·Risk로 다시 검토 → current_readiness → rank_candidates | UNVERIFIED | 코드 연결됨. fast 후보는 시장별 유동성 상위 최대 160개, 정밀 현재 판단은 전체 중 상위 최대 18개로 제한. **모든 상장 종목에 모든 전략을 똑같이 상세 검토하는 구조가 아님.** 최종 후보의 실제 PC 수치는 미확인. [근거: scanner.py](../backend/app/backtest/scanner.py), [strategy/engine.py](../backend/app/strategy/engine.py) |
| **단기·중기·장기 기간 정책** | POST /api/backtest/scanner/jobs → resolve_horizon_context → require_horizon_activatable | IMPLEMENTED_NOT_CONNECTED | 현재 SHORT/MEDIUM/LONG은 numeric policy EVALUATION_PENDING이며 명시 기간 요청은 409로 차단. 레거시 기본 흐름은 실행 가능. **세 기간별 전략/성과를 실제로 선택하는 기능은 활성화되지 않음.** [근거: horizon.py](../backend/app/horizon.py), [api/backtest.py](../backend/app/api/backtest.py) |
| **과거 수익·손실·낙폭** | BacktestEngine/metrics → MultiStrategyBacktestEngine, 별도 검증·과거 근거 → Scanner의 참고 설명 | IMPLEMENTED_NOT_CONNECTED | 승률·평균 순수익·기대값·profit factor·낙폭 계산 로직 존재. 현재 Scanner 최종 순위는 **현재 조건·Risk·진입 근접도 중심**이며 3년 근거는 설명용. Scanner의 빠른 후보 설정에는 round_trip_cost_pct=0.0. 현실적 거래비용 반영·전략별 최대 수익/위험 성과 최적화 완료로 주장하지 않는다. [근거: backtest/metrics.py](../backend/app/backtest/metrics.py), [backtest/scanner.py](../backend/app/backtest/scanner.py) |
| **JEV 실제 종목 보조 검토** | Scanner API에서 execution_mode=BASELINE_ONLY, jev_shadow=NOT_REQUESTED → 별도 수동 reviewer / B 사용자 작성 경로 | IMPLEMENTED_NOT_CONNECTED | Scanner 실행은 JEV 미요청. 기존 V4 입력·검증 코드는 있으나 **현재 제품이 원하는 자동 시장·종목 분석 연결이 아님**. B 경로의 TypeSafe wire는 사용자 작성 문장 2개뿐; 종목은 결과 저장 ID로만 연결. 유료 실행 0회(이 조사 기준 실행하지 않음). [근거: api/backtest.py](../backend/app/api/backtest.py), [jev/owned_review_b.py](../backend/app/jev/owned_review_b.py) |
| **외부 뉴스/공시의 JEV 전송** | news.policy / event_evidence.policy | RIGHTS_BLOCKED | 기존 Naver 뉴스 source 정책은 transform_allowed=False, ai_allowed=False. Event Evidence의 Naver/OpenDART 외부 변환·보존·AI 권한도 별도 미승인. **화면 표시 권한 ≠ 모델 외부 전송권한**. [근거: news/policy.py](../backend/app/news/policy.py), [event_evidence/policy.py](../backend/app/event_evidence/policy.py) |

#### B. 실제 후보 종목 1개 — 확인한 것 vs 확인 불가

- **선택 사례:** 선익시스템, 171090, KOSDAQ (이전 사용자 Windows 화면에 나타난 실제 선택 종목을 검사 표본으로 지정). 현재 해당 캡처 ID·입력 해시·분석 EOD 기준일·API 수집시각은 **미확인**; GitHub에 사용자 로컬 runtime 데이터가 없으므로 값을 지어내지 않는다.
- **실제 코드 경로:** POST /api/backtest/scanner/jobs → KRX 준비 및 HistoricalMarketStore → StockScannerService.run → BacktestEngine._signal_snapshot(KRX 주가+지수, risk & 전략) → quick current top 3 재평가 → current_readiness / rank_candidates → Prospective 정본 캡처 → **사후** ProspectiveReferenceCaptureService.try_capture → ScannerPanel 후보/종목 상세.
- **사용자 Windows UAT:** 이번 조사에서 직접 확인 불가. 기존 스크린샷은 종목 선택 및 AI UI의 존재만 뒷받침함. **현재 조건, 날짜, 전략, Risk, 실제 시장 하락지표, DART 공시 여부, 입력 출처·캡처 ID는 확인 불가.**
- **시장·국제 사건:** KRX 지수 당일 변동률은 생산 경로에 입력되는 코드가 있음. 미국 10년물·Macro/Event는 사후 reference이며 production 사용 불승인. DART 이벤트 위험은 개별 StrategyAnalysisService에 있지만 Scanner에서는 False.
- **JEV:** Scanner API에서 BASELINE_ONLY / NOT_REQUESTED. 저장된 실제 TypeSafe 결과의 존재나 Windows 재조회는 확인되지 않았음. 기존 B 문장 비교는 제품 목적 불합격.
- **Windows 확인이 필요할 때:** 이미 화면에 보이는 저장된 Scanner 결과의 종목/기준일/전략/Risk/시장요약/AI 상태를 **조회·캡처만** 한다. 신규 Scanner 실행·외부 API 재수집·DB migration·데이터 삭제·유료 JEV 호출을 자동으로 수행하지 않는다. 이 원칙을 충족하는 실제 결과가 확보되기 전엔 "최종 Windows 제품 UAT PASS"로 표시하지 않는다.

#### C. 최우선 결함 1개와 다음 단계 단일 범위

**최우선 결함 = 기존 Scanner의 '실제 시장·사건 위험 신호 → 전략 Risk Gate' 연결 부재/불완전.**

- **생산자:** KRX 지수 하락 → strategy/context.py:regime_from_index. 현재 출력은 상승/하락/횡보/미확인뿐이라 PANIC 차단값에 도달하지 못함. 시장 지수 급락 UI의 별도 표현과도 분리됨.
- **추가로 단절된 생산자:** 개별 StrategyAnalysisService에서 제공하는 OpenDART 이벤트 위험 및 Macro/Event reference.
- **끊긴 소비자:** BacktestEngine._signal_snapshot에서 생성하는 Scanner StrategyInput. event_risk=False 고정, Macro/Event reference는 Scanner 완료 이후 별도 부착되고 governance에서 scanner_input/risk_gate_input=False.
- **사용자 체감:** 국제 충격이나 국내 시장 급락 위험을 충분히 반영하지 못한 채 종목의 가격·전략 조건이 양호한 후보가 기본 Scanner 추천 순위에 나타날 수 있다. 실제 특정 종목에서 오판이 발생했다는 주장이나 손실 추정은 하지 않는다.
- **2단계 첫 수정 후보(아직 실행 금지):** 기존 KRX 지수/MarketRegime/StrategyEngine/Risk Gate를 재사용해서 '강한 시장 급락·PANIC' 신호를 현재 분석 시점에 정합적으로 생성·소비하도록 최소 연결한다. **명시적 정책·기준과 실데이터 검증 없이 임계값을 임의로 만들지 않는다.** 기존 전략 순위·Risk 기본 기준은 보호하고, 레거시 기준과 변경 결과를 실제 종목 1개로 비교한다.
- **2단계 이후 같은 범위 내 후속 의존:** Macro/Event와 OpenDART의 시점·원천·AI/가공 권한 및 실제 산업 연결 증거가 확정돼야 해당 위험을 Scanner에 안전하게 연계할 수 있다. 지금은 독립적인 신규 뉴스 수집기·AI 예측·종목별 유료 모델을 만들지 않는다.
- **별도 남은 제품 갭:** 명시 투자 기간 미활성, 실전 비용/수익 최적화 미검증, 일부 전략/업종 검사 범위 제한, JEV 자동 종목 입력 미연결. 다음 단계에서 모두 구현하지 않는다.

**Stage 1 결과 판정: CODE_AUDIT_COMPLETE_WINDOWS_UAT_PENDING.** 코드의 실제 소비 경로와 핵심 결함 한 가지를 확인했고 계획서 외의 파일 변경 없음. **Windows 표본의 현재 실데이터·API·DB 상태 검증은 미완료**로 남긴다. 사용자 Windows에 접근할 수 없는 한 전체 1단계를 DONE으로 표시하지 않는다. 2단계 제품 코드 개발은 이 결과 검토와 사용자 명시적 착수 지시가 있기 전까지 시작하지 않는다.


### 2단계: 기존 시장 위험을 실제 Scanner 판단에 연결 — 실행 명세 v1

**상태: IMPLEMENTED_REFERENCE_ONLY / CI_PASS / WINDOWS_UAT_PENDING (2026-11-01).** 사용자가 2단계 구현 착수를 지시했고, **KRX 일별 지수 위험 설명의 API·UI 연결까지** 반영했다. 하지만 PANIC 차단 정책 미승인, 실제 Windows 검증 미완료, 글로벌/사건의 실시간 소비 미연결로 **2단계 전체 DONE 아님**. 1단계의 Windows 확인도 별도 프로젝트로 분리하지 않는다.

#### 구현 목표와 성공 장면

> KRX 확정 지수와 검증 가능한 거시/사건 근거를 활용해, **종목의 전략 적합성**과 **오늘의 시장 위험·진입 판단**을 구분한다. 실제로 위험 신호가 확인되면 Scanner의 사용자 결과에 그 이유가 반영되고, 데이터가 없으면 "확인 불가"로 표시한다. 기존 전략·보유·매매 정책을 임의 변경하지 않는다.

**사용자 예시(가상):** "이 종목은 중기 추세에 관심을 가질 만하지만, 해당 거래일의 코스닥 지수 급락 위험이 확인돼 신규 진입은 보류합니다." 실제 원천이 없으면 이러한 판단을 생성하지 말고 "해당 날짜의 시장 위험 정보 부족"으로 표현한다.

#### 실행 절차 — 재사용 우선, 작업 확장 금지

**0. 1단계 잔여 검증 통합 (읽기 전용, 한 차례만)**

- 실제 경로 C:\TAEWOO\CapstonDesign\StockScope, 브랜치 codex/jev-reviewer-shadow-bridge 확인. 로컬 변경/기존 DB 보존. GitHub에서 사용자 브랜치가 다른 곳보다 최신이라고 추측하지 않는다.
- **이미 저장된 Scanner 결과 1건**으로 종목·시장·분석 기준일·기존 전략·현재 진입 판단·Risk·지수 상태를 기록한다. 예전 화면에 나온 선익시스템(171090)을 우선 사례로 삼되 **그 종목이 지금도 존재하거나 그 값이 최신이라고 가정하지 않는다**. 기존 화면의 저장 결과 또는 SQLite **읽기 전용(ro)** 조회를 우선한다.
- 자료가 없거나 사용자의 PC에 직접 접근할 수 없으면 CODE_AUDIT_COMPLETE / WINDOWS_UAT_PENDING 상태를 그대로 기록하고, **관련 없는 추가 Mock/기록 도구를 만들지 않는다**. 초기 개발에서 필요한 것은 이 표본의 확인뿐이다. 서버 신규 실행·Scanner 재수집·DB migration·유료 호출은 자동 수행하지 않는다.

**1. 국내 시장 급락 위험 → Scanner 현재 의사결정 연결 (이번 단계의 중심 구현)**

- 기존 코드의 생산자·소비자를 먼저 재사용한다.
  - KRX 확정 시장 지수: backend/app/market/providers/krx.py, app/backtest/scanner.py, app/backtest/engine.py.
  - 시장 상태: app/strategy/context.py의 regime_from_index(), app/strategy/models.py의 MarketRegime.
  - 위험 소비: app/strategy/engine.py의 _risk_gate(), app/backtest/selector.py의 current_readiness(), Scanner 후보 구성/표시.
- **실제 발견된 결함:** regime_from_index()는 TREND_UP / TREND_DOWN / RANGE / UNKNOWN만 생성하지만, 기존 StrategyEngine은 PANIC일 때 진입을 막는 규칙을 갖고 있다. 현재 Scanner의 표준 입력 경로에서는 해당 PANIC 신호가 생성되지 않는다.
- 먼저 **기존 승인된 위험 규칙·검증된 지수 데이터**에 따라 PANIC/위험 등급을 정할 근거가 있는지 확인한다. **근거 없이 -2%, -3% 같은 새 임계값을 정하거나 TREND_DOWN 전부를 PANIC으로 간주하지 않는다.**
- 위험 경보와 실제 전략/진입 제한을 구별한다.
  - **검증된 시장 위험** + 현 정책에서 승인된 차단 근거 → 기존 Risk Gate를 통해 기존 Scanner 결과에서 이유를 표시하고 진입 조건을 보류.
  - **근거 미완성·임계값 미승인** → 지수 변동과 "주의/판단 보류"를 **비차단 참고 정보**로 표시. 실제 ENTRY_CANDIDATE·정렬을 임의 변경하지 않는다. 이 경우 "시장 위험 차단 구현 완료"로 주장하지 않는다.
  - **지수 누락·시점 불일치** → market UNKNOWN / 사유 표시, 정상 시나리오의 기존 순위·Risk 보존. 정상이라는 가짜 신호를 생성하지 않는다.
- **중요 회귀 제약:** regime_from_index()는 과거 백테스트와 개별 분석이 공유한다. 함수 하나를 전역 변경해서 과거 시뮬레이션·Frozen 결과를 조용히 뒤집지 않는다. 새 current-only risk layer 또는 명시적으로 승인된 versioned 정책을 사용하는 **가장 작은 변경**을 선택한다. 모델·전략·보유 정책을 별도로 재작성하지 않는다.
- 결과 기본 표시: 기존 ScannerPanel/ScannerDecisionSummary 구조에서 **현재 전략 상태 + 시장 위험/근거/기준일 + 진입/관망 상태**만 간결하게 추가. 기존 A단계 UI 간소화 유지, 새 진단 탭 금지.

**2. 글로벌/거시 위험 → 시장 상황 설명에 연결 (별도 새 API 개발 금지)**

- 현재 있는 backend/app/macro/context.py의 미국 10년물 금리(DGS10), app/api/macro.py의 market-stock-impact, app/prospective/reference_capture.py의 사후 reference를 우선 재사용한다.
- 해당 자료의 원천·유효 시각·권한·실제 로컬 DB 상태를 확인하고 **Scanner의 종목/시장 위험 설명에 확인된 참고자료로만** 연결한다. 최근 데이터가 없다면 "거시 자료 없음/갱신 확인 필요"로 표시한다.
- 기존 governance의 scanner_input/risk_gate_input/production_decision_approved=False를 임의 해제하지 않는다. 금리 참고 지표를 AI의 수익 예측·매수/매도 신호로 변경하지 않는다.
- 미국 증시·환율이 현재 파이프라인에서 제공되지 않으면 **미연결**이라고 기록한다. 이번 단계에 공급자/뉴스 수집기를 증설하지 않는다.

**3. 국제 사건·산업/기업 위험 → 출처 확인된 경우에만 연결**

- 기존 개별 분석 경로: app/strategy/service.py → app/market/event_risk.py → OpenDART 공시 위험. Scanner 경로: app/backtest/engine.py에서 event_risk=False 고정. 두 경로의 기능·시점 차이를 명확히 지킨다.
- 기존 event-evidence/macro reference와 증빙 자료에서 **사건의 종목·업종 연결/최초 관측시각/원천 이용 범위**를 먼저 확인한다. 기업 공시의 **사후·현재 조회 결과를 과거 Scanner 신호에 소급하지 않는다.**
- 승인된 종목별 사건 위험이 동일한 기준일에 확정되는 경로가 이미 있다면 **후보 단위 최소 결합**을 설계/적용한다. 없으면 이벤트 위험은 *reference/미확인*으로만 표시하고 **false를 "위험 없음"으로 해석하지 않도록** 한다. 알 수 없는 사건을 조작해 보완하지 않는다.
- 전쟁/호르무즈 관련 신뢰 가능한 데이터·산업 영향 경로가 현재 없으면 **실제 사건 검토 불가**를 표시한다. 새 뉴스 크롤러, 원문 재배포, 자동 AI 해석·유료 JEV 호출은 이 단계에서 하지 않는다.
- news.policy 및 event_evidence.policy에서 Naver/OpenDART 관련 AI 변환·보관·재가공 권한 제한을 보존한다. "표시 허용"을 "AI 전송 허용"으로 오해하지 않는다.

#### 실제 수정 허용 범위

- **허용:** 현재 Scanner 판단의 시장 위험 상태를 만들어 **기존** 전략/판단 및 화면에 전달하기 위해 필요한 최소 파일; 해당 지표/시점·근거의 최소 표시; 직접 관련된 기존 테스트만 보강; **본 계획서 상태 갱신**.
- **금지:** 사용자 DB 스키마·실제 계좌/보유 데이터, 단기/중기/장기 정책, 새 종목 전략, 기존 위험 임계값의 임의 변경, 별도의 글로벌 뉴스 인프라, 본래 JEV 문장 입력 UI 확장, 비승인 외부 데이터 전송, P6 후속 진단 루프, 새 HANDOFF·대시보드 추가.
- JEV는 이번 2단계의 실행 대상으로 삼지 않는다. 기존 Scanner 결과가 AI 미실행이면 **미실행** 유지.
- 구현 중 기존 frozen backtest 변경이 불가피하면 **기존과 신규 결과를 먼저 비교하고 변경 범위 승인을 별도 받는다**. 테스트를 통과시키기 위해 기준 데이터를 몰래 수정하지 않는다.

#### 검증 — 최소 회귀 + 실제 Windows 확인

1. **위험 분류:** 실제 KRX 지수 데이터에서 확인된 정상일/급락일/누락일의 시간·시장·source가 맞는지 확인. 테스트용 가정 값은 테스트로만 분리하고 원천 실데이터로 주장하지 않는다.
2. **판단 보존:** 지수 정상·자료 없음이면 기존 10전략, Risk, 순위, Holdings, Frozen 결과와 **불필요한 변화 없음**. 급락일에 승인된 정책이 존재하면 해당 상황에서만 진입 보류 사유가 UI에 표시되는지 확인.
3. **참고 데이터 분리:** 미국 금리·공시/국제 사건이 reference에 머물 때 실제 전략 점수·Rank·Risk Gate에 조용히 들어가지 않는지 확인. 권한/시점 제약은 미해결 상태로 표시.
4. **실제 Windows:** 기존 코드와 변경 후 코드에서 **같은 종목·같은 날짜·같은 KRX EOD**를 확인. 선택 종목에 전략 판단, 지수 위험, 자료 기준시각, 실제 진입 안내가 사용자 화면에서 서로 모순되지 않아야 한다.
5. **완료/미완료 구분:** CI/합성 테스트만 성공하면 IMPLEMENTED_NOT_UAT; Windows 표본과 실제 위험근거도 확인해야 DONE. 로컬 데이터가 없으면 WAITING_FOR_WINDOWS_DATA라 기록하고 무작정 신규 조사/Mock을 돌리지 않는다. 서버/PC를 직접 확인하지 않았다면 검증했다고 주장하지 않는다.

#### 완료 기준과 다음 단계 게이트

- 사용자는 최소 **하나의 실제 후보**에 대해 **전략의 적합성**과 **현재 시장 위험/진입 가능 여부**가 구분된 짧은 설명을 볼 수 있어야 한다. 지표의 원천·거래일도 확인 가능해야 한다.
- 기존 위험/전략/보유 데이터는 승인된 차이를 제외하고 유지된다. 시장 급락 신호에 대한 실제 진입 차단은 **정책·시점·근거가 승인된 경우에만** 완료로 판정한다.
- 글로벌 거시 1종(기존 US10Y) 및 사건/산업 위험 1종(기존 DART 또는 event evidence)은 **사용 가능한 상태이면 근거·시점을 표시**, 제한된다면 **미연결/자료 부족/권한 차단**을 명확히 기록한다. 둘을 실제 투자 판단 입력으로 승인 없이 섞지 않는다.
- 사용자 Windows 실제 결과와 기존 분석 비교, 변경 파일·CI 증거·차단 1~3개를 **이 계획서에만** 기록한다. 2단계 완료/미완료를 정직하게 선언하고 3단계 다전략·기간·성과로 넘어갈지는 **이 결과를 확인한 뒤** 결정한다.

#### 2단계 구현 결과 — 2026-11-01

**반영 완료 (실제 소스 변경):**

- `backend/app/api/backtest.py`: Scanner가 기존 순위·Risk·정본 캡처·사후 reference 기록을 모두 확정한 **후**, `_attach_scanner_market_reference()`에서 기존 KRX EOD 저장소의 **동일 분석일 지수 1건만 읽어** API 최종 응답 `market_summary[]`에 추가. 날짜 불일치/누락/숫자 오류는 `UNKNOWN`. 유료 API 호출/신규 수집/DB 기록·재생성 없음.
- 시장 변동률은 기존 `regime_from_index()`의 `TREND_DOWN` 신호만 재사용. 하락일에 `DECLINE_RECHECK`로 표시하지만 **새 PANIC 임계값 및 진입 차단은 적용하지 않음**. 응답에 `risk_decision_effect=REFERENCE_ONLY_NOT_RISK_GATE` 표기. 동일하지 않은 지수 날짜를 억지로 맞추지 않는다.
- `frontend/src/services/api.ts`, `frontend/src/components/ScannerPanel.tsx`, `frontend/src/components/ScannerDecisionSummary.tsx`: 기존 후보 목록·종목 상세 구조 유지. 종목 상세의 "시장 위험 · 분석일 기준" 영역에 KRX 확정 일별 변화/하락 주의/자료 불명확을 노출하고 **전략 조건에 따른 기존 판단과 시장 참고 경고를 분리**. 미국 금리·국제 사건은 현재 Scanner의 진입·전략 판단에 자동 반영되지 않음을 명시. 이전 캐시·세션에 지수 상태가 없으면 "자료 확인 불가" 처리.
- `backend/tests/test_scanner_v021.py`: 동일 분석일, 전일 데이터 혼용 차단, NaN/결측, 기존 `TREND_DOWN`과 PANIC Gate 불변, API 설명 보강 시 Frozen 후보·순위 불변 검증.
- **중요 복원:** 최초 시도에서 `backend/app/backtest/scanner.py`를 변경하여 Frozen Baseline 검증이 실패했으나 **동일 파일을 기존 원본 blob `39852538b23516fe7acc3136f725d6dd53deb3ab`으로 완전히 복원**한 뒤 API 경계의 설명 전용 확장으로 대체했다. 프로덕션 Scanner/Backtest의 frozen 해시·전략/순위 변경 없음.

**검증:** 최종 코드 `b574b1ab` 기준 [GitHub Actions #41313136517](https://github.com/SkyBluekor/StockScope/actions/runs/41313136517): **Python 3.11 PASS, Python 3.14 PASS, Frontend Node 22 PASS, Fresh Clone Windows PASS (4/4)**. 두 백엔드 환경에서 기존 Frozen Baseline 검증을 포함한 전체 테스트가 통과했다. **사용자 실제 Windows UI/UAT 및 실제 KRX 저장 데이터 시각·지수값은 아직 확인하지 않았으므로 PASS로 쓰지 않음.**

**완료하지 못한 요구사항 / 다음 확인 사항:**

1. **Windows UAT 대기:** 현재 브랜치에서 pull 후 기존 Scanner 분석 결과를 화면에 불러와 **한 번만** 실행/재사용하고, 같은 날 KRX 지수 변화·종목 전략·시장 위험 문구가 함께 보이는지 확인. 결과 날짜·종목 ID·출처와 현재 Risk 변동 여부만 비교. 데이터 미확보 시 임의 값 출력 금지.
2. **PANIC에 따른 실제 신규 진입 차단은 미구현:** 현 코드에 승인된 급락 임계값/거버넌스가 없어, 근거 없이 숫자를 정해 `Risk Gate`를 활성화하지 않았다. 현재 표시되는 것은 **참고 경고**이며 매수/매도/순위가 바뀌지 않는다.
3. **글로벌/국제 사건의 Scanner 소비 미완료:** 기존 DGS10 Macro/Event `reference`는 사후 검토로만 사용. 시간/데이터 이용권 및 업종 연결이 확인되지 않은 자료를 생산 `StrategyInput`으로 승격하거나 외부 JEV로 보내지 않았다. 이번 단계에서 새 공급자를 추가하지 않음.

**2단계 판정:** `IMPLEMENTED_REFERENCE_ONLY_CI_PASS_WINDOWS_UAT_PENDING` / 전체 완료 아님. 사용자 PC에서 KRX 경고 표시를 확인하고, 남은 PANIC 위험 정책 및 실제 거시·이벤트 소비 조건을 명시적으로 결정하기 전에는 3단계로 이동하지 않는다.


#### 2단계 후속 — 신규 진입 안내 분리 (2026-11-02 현재 GitHub 확인)

**상태: CODE_IMPLEMENTED / CI_4_OF_4_PASS / WINDOWS_UAT_PENDING.** 이번 항목은 기존 2단계의 직접적인 후속이며 별도 단계가 아니다.

- 코드 커밋 [`5c7612345a`](https://github.com/SkyBluekor/StockScope/commit/5c7612345a) 및 UX 호환 수정 [`8c86b28939`](https://github.com/SkyBluekor/StockScope/commit/8c86b28939): `frontend/src/components/scannerDecisionPresentation.ts`의 `scannerEntryGuidance()`가 기존 위험/거래 제외/미충족 조건을 우선하고, 분석일·시장·원천·참고 상태가 일치하는 KRX 지수 하락 시 `MARKET_RECHECK`, 일치 자료가 없으면 `MARKET_UNKNOWN`을 반환. 기존 READY/전략 조건은 원본 그대로 유지.
- `frontend/src/components/ScannerDecisionSummary.tsx`: 선택 후보 요약 상단에 **신규 진입 판단 (현재 매수 허가 아님)**을 우선 표시하고 종목 조건을 별도 행으로 분리. 시장 하락 시 신규 진입 재확인, 승인된 실제 Risk Gate 차단과 구분. 진입 재확인에 맞춰 '다음 확인' 문구도 조정.
- `frontend/tests/scannerDecisionPresentation.test.mjs` 및 E2E 회귀에서 선익시스템 171090 / KOSDAQ / 2026-10-30 / 6/6 / -3.83%와 정상/누락/시점 불일치/기존 위험 우선순위를 검증. 테스트 수치는 합성 fixture이며 실제 KRX 추가 수집 결과 아님. 기존 as-of/조건 라벨과 무관한 UX 계약은 보존.
- 최종 HEAD `8c86b28939b427ae960e436f2bc3b42745a352c6` 기준 [GitHub Actions #41321297882](https://github.com/SkyBluekor/StockScope/actions/runs/41321297882) **Backend Python 3.11, 3.14 / Frontend Node 22 / Fresh Clone Windows 모두 PASS (4/4)**. 초기 중간 HEAD `5c761234`의 CI 실패는 이후 `8c86b289`에서 UX 호환성 수정 후 해결됨.
- **Windows 실화면 미검증**: 사용자가 실제 브라우저에서 새 상단 '신규 진입 판단'을 확인하고, 기존 `시장 위험 · 분석일 기준`과 구분되는지 증거 필요. 예전 선익시스템 화면은 이 신규 커밋 이전 화면이며, 신규 변경의 UAT로 재사용하지 않음.
- **미완료 경계:** KRX 하락은 별도 참고 신호이며 PANIC 차단 기준 미승인; 기존 Scanner 순위/Risk/과거 frozen 캡처는 변경하지 않음. 미국 금리·국제 사건 최종 Scanner 소비 및 실제 정책 차단도 아직 미완료. 2단계 전체 DONE 아님. 3단계 착수 금지.

#### 2단계 후속 — 자동 기준일 역행 방지 (2026-11-02)

**현장 근거:** 사용자 Windows `C:\\TAEWOO\\CapstonDesign\\StockScope`의 읽기 전용 조회에서 `simulation.db`의 2026-10-30 COMPLETE 캡처에 선익시스템(171090)이 남아 있고, 2026-11-02 00:43·00:45 KST의 새 자동 Scanner 결과는 2026-10-29 / 동국제약(086450)이었다. 두 요청의 `requested_as_of`는 NULL, 범위는 ALL. `market_history.db`의 10/30 KOSPI 주식 939개·지수 1건, KOSDAQ 주식 1828개·지수 1건과 네 개의 `data` 마커가 확인되었다. 브라우저 결과만 바뀌었으며 원본 캡처 삭제 증거는 없다.

**재현 가능한 코드 결함:** API는 브라우저의 `known_data_date`만 `StockScannerService.prepare_latest_confirmed_data`로 전달한다. 이 함수는 이미 저장된 공통 최신일(`stored_common_before`)을 파악하지만, 전달된 `known_data_date`가 이전 날짜거나 NULL이면 `current_valid_date`가 이전 날짜 또는 NULL로 남는다. 일시적으로 제공자가 구형 날짜를 반환하면 그 날짜로 분석이 진행될 수 있다. 실제 제공자 응답 로그를 보지 못했으므로 이번 현상에서 어떤 공급자 상태였는지는 미확정.

**수정:** `backend/app/api/backtest.py`에서 자동 Scanner 및 freshness API 호출 전에 기존 MarketStore의 지정 범위 전체 시장·주가/지수 `latest_common_complete_date`를 읽어 브라우저 날짜보다 최신인 유효 저장 기준일을 우선 전달한다. 응답이 그 날짜보다 오래되면 `DATA_INCONSISTENT`로 **새 분석을 차단**한다. 명시적 과거 `as_of_date`는 변경하지 않는다. `backend/app/backtest/scanner.py` frozen 파일·기존 전략/랭킹·DB 원본은 수정하지 않는다.

**회귀:** `backend/tests/test_scanner_v021.py`에 이전 브라우저 기준일/누락 기준일/양 시장 완전성/시장별 차이/미래·잘못된 날짜/제공자 역행 차단/정상 최신일 유지 테스트 추가. 이 변경은 새로운 DB 수집이나 JEV 호출 없이 GitHub 코드로만 수행하며 **CI PASS와 사용자 Windows 재현 확인은 별도 판정**한다.

**CI 검증 (2026-11-02):** 최초 변경 `8bdcd077`의 백엔드 1개 실패는 기존 진행률 계약 테스트가 직접 `prepare_latest_confirmed_data` 호출만 허용했기 때문이다. `e2c163c`에서 보호용 함수 내부의 실제 호출과 분석 전 실행 순서를 확인하도록 테스트를 보강했고, [GitHub Actions #41325608233](https://github.com/SkyBluekor/StockScope/actions/runs/41325608233) 4/4 PASS. Python 3.11 백엔드 2,385 PASS, 2 SKIP, 1 WARNING. Frozen Scanner 원본·사용자 DB 변경 없음.

**남은 확인:** 업데이트 후 실제 사용자 PC에서 10/30이 선택되는지 검증. 저장 주가의 EOD 원천 재확인·유료 모델 호출·기존 캡처 재생성은 하지 않는다. 2단계 전체 완료 전 PANIC 정책·국제사건 연계 및 Windows UAT가 남아 있다.

#### 2단계 다음 단일 작업 — MR-01: 국내 시장 급락의 *실제 신규 진입 제한 정책* 검증·확정

**상태: SPEC_READY / POLICY_NOT_APPROVED / CODE_NOT_STARTED (2026-11-02).** 최종 코드 브랜치는 `codex/jev-reviewer-shadow-bridge`. 2026-11-02 사용자가 바꾼 PC에서 선익시스템(171090)이 10월 30일 기준으로 선정됐음을 확인했다. **새 PC 첫 실행의 날짜 정합성은 확인, 같은 PC 반복 실행의 역행 방지 UAT는 미확인**. 별도 무한 진단 단계로 확장하지 않는다.

**단 하나의 제품 목표:** 종목 조건 6/6과 국내 시장 급락이 동시에 나타날 때 초보자에게 '조건 적합'과 '실제 신규 진입 보류 여부'를 혼동 없이 설명할 수 있도록, **근거 있는 `MARKET_PANIC` 판정 정책을 정식으로 정의·비교·승인**한다. 현재 `MARKET_RECHECK` 안내는 비차단 참고 상태다. 실제 Risk Gate 연결 완료로 보고하지 않는다.

**지금 구현으로 확인된 사실:**
- `regime_from_index`는 지수 등락률이 -1% 이하일 때 `TREND_DOWN`을 반환하지만 `PANIC`은 생성하지 않는다. `StrategyEngine._risk_gate`에는 `MarketRegime.PANIC` 차단 규칙이 이미 있다.
- `ScannerDecisionSummary`와 `scannerEntryGuidance`는 KRX 분석일 일치 하락일에 `MARKET_RECHECK`를 보여준다. 이는 원본 Scanner 후보·순위·Risk Gate를 변경하지 않는다.
- 시장 반등/급락 정책이 승인되지 않은 상태에서 `TREND_DOWN == PANIC`으로 치환하거나 -2%/-3%를 근거 없이 임계치로 추가해서는 안 된다.

**착수 후 실행 순서 (MR-01 범위):**

1. **현 데이터 기준 단일 확인:** 사용자 새 PC에서 날짜 역행 방지 재실행 결과 1회만 확인하고, 그 날짜의 KOSPI/KOSDAQ EOD 종목·지수 완전성을 읽기 전용으로 확인한다. 실제 PC 접근이 없으면 사용자 관찰과 코드 검증을 구분하고 현상만 기록한다.
2. **기존 시장 위험 규칙 재사용 조사:** `backend/app/strategy/context.py`, `engine.py`, `backend/app/backtest/engine.py`, `scanner.py`, 기존 risk/policy registry에서 사용 중인 PANIC 또는 지수 급락 정책이 **명시적 승인된 형태로 존재하는지** 확인한다. 새 중복 엔진을 만들지 않는다.
3. **국내 KRX 데이터로 위험 정책 후보 검증:** 이미 저장된 EOD 주가·지수에서 시장별 날짜 정합성과 지수 하락 강도, 지속 기간, 되돌림/변동성, 필요하면 실제 저장된 시장 폭(상승/하락 종목 비율)을 비교한다. 2026-10-29/-30의 결과는 *실제 사례*로 두고, 전체 근거는 충분한 저장 기간 안에서 확인한다. 이때 임계치를 먼저 정하거나 과거 사건을 미래 시점에 사용하지 않는다. 정당한 비교 근거가 불충분하면 `POLICY_EVIDENCE_INSUFFICIENT`로 남긴다.
4. **명시적 정책안과 영향 비교:** 기존 `TREND_DOWN` 경고는 경고로 유지하고, 심각한 급락 상태에만 적용할 `PANIC` 후보를 **지수 입력, 평가 시점, 기준값 선정 근거, 완전성 요구, 시장별 적용, 중복 신호, 누락 시 `UNKNOWN`, 버전/추적 정보**가 포함된 정책표로 제시한다. 선익시스템 171090 / 2026-10-30은 기존 '전략 6/6'과 승인 시 신규 진입 제한 상태가 어떻게 달라지는지 나란히 보여준다. 이때 과거 저장된 Scanner 결정·순위·점수는 불변.
5. **이 단계 종료와 승인 게이트:** 결과를 **이 단일 계획서**에 정책 후보 1개와 실제 데이터의 비교·오탐 우려·필수 미확인 항목으로 짧게 기록한다. 사용자가 정책 기준을 승인하기 전에는 `StrategyInput.market_regime`, Risk Gate, Scanner 순위, 과거 Frozen 캡처를 변경하지 않는다. 승인되면 후속 **MR-02 구현**에서 신규 분석에 한해 버전된 시장 진입 제한 정책을 연결한다. 승인 전엔 실제 차단 대신 기존 경고를 유지한다.

**MR-01 금지 범위:** 사용자 DB 쓰기/삭제·마이그레이션·새 EOD 재수집, 새 외부 뉴스·공시 크롤러, 거시·국제 사건의 생산 Risk Gate 임의 승격, JEV 유료 호출, Frozen Scanner/전략 전역 변경, 신규 문서 다발/진단 UI/점수 조작. 기존 API/정책·읽기 전용 KRX 데이터만 활용한다.

**MR-01 완료 조건:** (a) 이미 승인된 정책의 존재 여부를 근거로 분류, (b) 사용 가능한 실제 KRX 표본으로 정책 후보의 재현성과 부족한 근거 확인, (c) **‘시장 하락 참고’ vs ‘차단 근거 있는 PANIC’ vs ‘자료 부족’**의 사용자 출력 차이와 기존 종목 조건·순위 보존 정리, (d) 이 문서에 정책 1개/승인 대기 여부 기재. **CI/시뮬레이션만으로 실제 운용 정책을 승인한 것으로 간주하지 않는다.**

#### MR-01 실행 기록 — 기존 정책 실체 확인 및 단일 후보 도출 (2026-11-02)

**판정: POLICY_CANDIDATE_DOCUMENTED / LOCAL_EMPIRICAL_EVIDENCE_PENDING / PRODUCTION_GATE_UNAPPROVED.**
이 결과는 사용자의 "작업 시작" 요청에 따라 GitHub에서 실제 코드를 추적한 결과이다. **프로덕션 코드·데이터·Frozen Scanner·Risk·JEV 설정은 변경하지 않았다.** 현재 새 PC의 `market_history.db` 내용은 GitHub에 없으므로 읽거나 검증했다고 주장할 수 없다. 새 PC에서 선익시스템(171090)이 2026-10-30 기준 후보로 나왔다는 사용자 확인은 존재하지만 **반복 실행 날짜 역행 검증은 남아 있다**.

**(1) 확인한 기존 경로 및 결함**
- `backend/app/backtest/engine.py:_signal_snapshot`는 KRX 동일일 지수 `change_rate`를 `regime_from_index`로 전달한다. `backend/app/strategy/context.py`는 <= -1.0%를 `TREND_DOWN`으로 분류하고 `PANIC`은 생성하지 않는다.
- `backend/app/strategy/engine.py:_risk_gate`에는 `MarketRegime.PANIC` 진입 차단이 있으나 현재 Scanner의 지수 경로에서 이 입력이 생산되지 않는다. `backend/app/backtest/engine.py`의 Scanner 계열 `event_risk=False`도 그대로다.
- `backend/app/api/backtest.py:_attach_scanner_market_reference` → `frontend/src/components/scannerDecisionPresentation.ts:scannerEntryGuidance`는 동일 분석일 `TREND_DOWN`을 `MARKET_RECHECK`로 설명하지만 실제 `risk_decision_effect=REFERENCE_ONLY_NOT_RISK_GATE`. **이것은 실제 신규 진입 차단이 아니다.**
- `docs/backtest-risk-policy-v0.19.5.md` / `docs/backtest-risk-policy-decision-v0.19.6.md`에 기존 손절·CAUTION 비교 연구와 표본·거래 유지 가드레일이 있으나 **시장 급락을 PANIC 차단으로 승격하도록 승인한 기준은 아니다**.

**(2) 새 기준 발명 없이 확인한 재사용 요소**
- `backend/app/market/service.py:MarketDataService._breadth`: 동일 시장/일자 종목별 KRX `change_rate`가 있는 행의 상승·하락·보합 수, `up_ratio`, `avg_abs_change_rate`를 계산한다.
- 같은 파일의 `_market_regime(kospi_rate, kosdaq_rate, up_ratio)`: KOSPI/KOSDAQ 등락률 **단순 평균 <= -0.8%** 및 **전체 상승 종목 비율 <= 0.40**일 때 화면용 `강한 하락`으로 표시한다.
- 같은 파일의 `_volatility_label(avg_abs_move)`: 종목별 일간 변동률 절댓값 평균 **>= 4.0%**를 화면용 `높음`으로 분류한다.
- 이 값은 **기존 대시보드용 휴리스틱**이지 검증된 금융시장 PANIC 차단 임계값이 아니다. `backend/tests/test_market_dashboard_logic.py`는 기본 상승/폭 집계만 검증한다. `_market_regime`는 원래 단일일 데이터 유효성/양 시장 날짜 동기화를 자체 강제하지 않으므로 연구·후속 구현에서는 반드시 사전 검증한다.

**(3) MR-01 *단일 시험 정책 후보*: `MR01_BROAD_DOWN_AND_HIGH_MOVE_V0` (비생산)**
- **입력/시점:** 동일한 KRX 확정 EOD 거래일의 KOSPI·KOSDAQ 대표지수 및 종목별 일간 변동률. 4종 데이터 마커(stock/index × 양 시장)가 모두 `data`이고 실제 주가·지수 행도 존재하며 `change_rate`가 유한 숫자일 것. 결측·시장별 날짜 불일치·원천 불명확이면 `UNKNOWN`으로 차단 승인 금지. 이력은 평가일 이전에 관측된 사실만 이용.
- **시험 조건:** 대시보드 기존 `강한 하락` **AND** 기존 변동폭 프록시 `높음`이 동시에 관찰된 날을 `PANIC_CANDIDATE`로 분류. 새로운 -2%/-3% 같은 경계를 만들지 않는다. 단일 시장 급락에 대한 민감도·평균/가중 방식 편향·저유동성/상장 특수주 포함의 영향은 별도 평가 대상이다.
- **현 단계 출력:** `PANIC_CANDIDATE`는 **연구용 분류만** 뜻한다. 운영 Scanner UI는 계속 기존 `MARKET_RECHECK` 또는 `MARKET_UNKNOWN`; `StrategyInput.market_regime`, `risk_gate_active`, 후보 점수·순위·Prospective 저장본은 불변이다.
- **후속 MR-02 조건:** 실제 로컬 과거 EOD 시계열에서 정책 발생일 수, 빈도, 2026-10-29/30 편입 여부, 시장별 누락과 상승/하락 종목 커버리지, 동일일 KRX 날짜 정합성, 비발생일 대비 이후 5/10 거래일 손실/최대 낙폭(**사후 평가만, 판정 입력 금지**), 잘못 차단된 회복장 사례를 검증한다. 기간 분리 및 오탐·거래 기회 상실 비교 뒤 사용자 승인 필요. 승인 시 새 분석의 **별도 버전된 신규 진입 게이트**에서만 실제 보류를 적용하며 공유 `regime_from_index`/Frozen 과거 결과를 직접 고치지 않는다.

**(4) 실제 KRX 데이터 증거 현황 및 차단 사유**
- 사용자 구 PC의 읽기 전용 조회로 2026-10-29 및 10-30 양 시장의 `day_status = stock/index data` 및 해당 일 종목 수·지수 1건이 확인됐다. 선익시스템 171090의 2026-10-30 COMPLETE 캡처도 존재했다. 당시 화면에서 KOSDAQ 지수 하락 참고 신호가 관찰됐다. **이 사실만으로 `_breadth`·`_volatility_label` 또는 전체 과거 표본을 재현할 수는 없다.**
- 이 GitHub 연결에는 구/신 PC 개인 `market_history.db`가 없고 저장소에는 실행용 시장 SQLite가 없다. 실제 국내 EOD 120거래일 이상 분포·후속 손실/오탐 비교를 아직 계산할 수 없다. 따라서 `POLICY_EVIDENCE_INSUFFICIENT`, `PANIC` 위험 차단 **미승인/미구현**으로 기록한다.
- **다음에 필요한 단 하나의 입력:** 사용자 새 PC의 기존 `market_history.db`를 `sqlite3 mode=ro`로 읽고, *양 시장의 공통 거래일*에 대해 기존 `MarketDataService._breadth`, `_market_regime`, `_volatility_label` 분류를 과거 시계열과 2026-10-29/30에서 일관되게 집계한 **집계값만** 수령. 시장 DB 전체·개인 포트폴리오·API 키 업로드는 요청하지 않는다. 실자료가 없으면 임의 표본으로 승인하지 않는다.

**MR-01 남은 작업:** 사용자 새 PC에서 읽기 전용 시장 분포 집계 → 후보의 발생률/추가 차단 영향·거짓 경보 가능성 평가 → 정책 승인 또는 보류 기록. 이번 소스 검증만으로 MR-01을 DONE으로 처리하지 않는다.

#### MR-01 실데이터 검증 결과 — 정책 후보 기각·종료 (2026-11-02)

**상태: MR01_CLOSED_POLICY_REJECTED / PRODUCTION_PANIC_GATE_NOT_APPROVED.** 이 기록은 사용자의 **새 PC `C:\\Projects\\StockScope`**에서 직접 수행한 읽기 전용 집계 출력에 근거한다. 본 검토에서는 GitHub 코드·Scanner/전략 점수·위험차단·사용자 DB를 변경하지 않는다.

**표본/기준:** 로컬 `backend/runtime/market_history/market_history.db`, KOSPI/KOSDAQ 공통 확정 EOD 120거래일(`2026-05-06`~`2026-10-30`). KRX 지수 + 종목 `change_rate`를 기존 `MarketDataService._breadth`, `_market_regime`, `_volatility_label`에 대입한 별도 비생산 연구 결과.

| 평가 항목 | 사용자가 실행한 실제 결과 | 해석 |
|---|---:|---|
| 기존 대시보드 `강한 하락` | 38/120일 (31.7%) | 참고 경보로는 의미 있으나 모두 실제 진입 차단하면 과도 차단 위험 |
| `MR01_BROAD_DOWN_AND_HIGH_MOVE_V0` 동시 충족 | 8/120일 (6.7%) | 제한적으로 발동 |
| 2026-10-29 | KOSPI -1.24%, KOSDAQ -2.34%, 상승 비율 21.9%, 평균 절대 변동폭 2.554%, 커버리지 100% | `강한 하락=True`; PANIC 후보=False |
| 2026-10-30 | KOSPI -3.48%, KOSDAQ -3.83%, 상승 비율 18.1%, 평균 절대 변동폭 2.913%, 커버리지 100% | `강한 하락=True`; PANIC 후보=False. 사용자 선익시스템 171090의 10/30 전략 조건 6/6 사례에서 위험 신호를 반영할 수 없었음 |
| 이후 5거래일 두 지수 중 최악 하락폭 평균: 후보 8일 | -4.36% | 사후 지표·차단 입력 아님 |
| 같은 지표: 비후보 107일 | -6.90% | 후보와 비후보 차이가 정책 효용을 지지하지 않음 |

**중요한 해석 한계:** 사후 평가 표본은 8+107=115일이고 마지막 5거래일은 추적기간이 없어 제외됐다. 위 5거래일 손실은 두 시장의 최악 지수를 택해 최솟값을 0 이하로 제한한 **혼합·사후 지표**다. 각 시장의 동일 종목 진입손익이나 실제 방어 효과가 아니다. 연속 5일 관측창이 중복되고 PANIC 후보 8일은 소표본이므로, 두 집단의 평균 차이만으로 통계적 우열을 확정할 수 없다. **그러나 10월 29~30일의 큰 하락을 모두 탐지하지 못하고, 사후 결과에서도 일관된 유익성이 입증되지 않으므로 생산 차단 정책으로 채택할 근거가 없다.**

**의사결정:**
- `MR01_BROAD_DOWN_AND_HIGH_MOVE_V0`: **REJECTED_FOR_PRODUCTION**, 승인·Risk Gate 적용 금지. 단순 평균 절대 종목 변동폭 >=4%를 급락 차단의 필수 조건으로 쓰는 방식은 10/29와 10/30을 모두 누락했다.
- 기존 `TREND_DOWN` 및 `MARKET_RECHECK` **참고 주의 문구는 유지**, 원래 종목 전략 6/6과 순위·Risk를 변경하지 않는다. `PANIC` 실제 차단은 `POLICY_EVIDENCE_INSUFFICIENT`; 개발자가 임의의 새 숫자(-2%/-3% 등)를 지정하거나 `강한 하락` 38일 전체를 차단하지 않는다.
- **MR-01은 기각 결론을 낸 연구로 종료**. 추가로 같은 표본을 잘게 나눠 임계값을 최적화하는 반복 작업은 실시하지 않는다. 향후 독립 검증기간·손실/오탐 비용 평가와 별도 정책 승인이 확보되면 신규 단계에서만 재검토 가능.
- **2단계 전체는 계속 미완료**: 승인된 실제 시장 PANIC Gate 없음, 기존 글로벌/거시 및 국제 사건은 Scanner production 결정 입력 아님, 새 PC 반복 실행 날짜 역행 검증도 별도 미확인.

**다음 단일 작업(2단계 유지, PANIC 미승인 경로에 대한 우회 없음): `MACRO-01` — 기존 미국 10년물 금리(DGS10)와 국내 KRX 시장 경고의 참조 설명 연결.** 이미 존재하는 `LocalMacroReader`, `GET /api/macro/market-stock-impact`, 사후 reference 결과를 **원천·발표시각·평가 기준일·자료 사용권**과 함께 점검하고, 충분히 확인된 경우에만 기존 Scanner의 **비차단 시장 설명**에 결합. 데이터가 없다면 미확인으로 종료. Risk Gate/점수/순위/JEV/원천 DB를 바꾸거나 임의 국제뉴스 API를 새로 만들지 않는다. 실제 사용자에게 설명되는 변화가 확인되지 않으면 완료라 주장하지 않는다.

### 3단계: 다전략·기간·위험 대비 기대성과 통합

- **목적:** 기존 10전략·단/중/장기·Risk 결과와 시장·산업 조건을 합쳐 종목에 맞는 접근법을 비교.
- **범위:** 새 전략 발명 금지. 기존 평가/시뮬레이션을 재사용. "가장 높은 수익률 보장" 같은 미검증 점수 금지.
- **완료 조건:** 사용자 Windows의 실제 종목 결과에서 **적합한 전략/기간, 진입 vs 관망, 위험과 무효화 조건**을 초보자용 한 화면으로 이해 가능. 근거·기준일 추적 가능.

### 4단계: 자동 생성 입력으로 JEV 실제 보조 검토

- **목적:** 사용자에게 질문 두 개를 쓰게 하지 않고 StockScope가 계산한 **전송권한 있는 정보**로 JEV를 필요한 후보에만 연결.
- **범위:** 기존 TypeSafe 제공자 활용. 실제 종목 1건을 사용자 유료 승인 후 검증. 실모델의 질문 계약이 지원하지 않는 사건 추론은 임의 주장 금지.
- **완료 조건:** 비합성 모델 호출, 입력·모델·시각·결과·비용·오류·중복 차단을 실제 Windows에서 확인하고, 로컬 판단과 구분되는 보조 의견 표시. 허용 데이터로 유의미한 검토가 불가능하면 **B류 가짜 우회 기능을 만들지 말고 정확한 장애를 보고**.

### 5단계: 투자 판단에 실제 도움 되는지 검증·정리

- **목적:** 기존 로컬 단독 vs 글로벌/사건 결합 vs JEV 보조의 **증분 가치**를 비교.
- **검증:** 기간 분리 성과, 비용·낙폭·손실, 시장 환경별 실패, 지연·요금·오류, 초보자 UX. 데이터가 부족하면 "검증 부족"으로 판정.
- **완료 조건:** 실제 검증과 Windows UAT를 토대로 **유지/개선/보류** 결론을 내고 기본 화면은 간결하게 유지. 자동 주문·무제한 뉴스 수집·자동 AI 호출로 범위 확장 금지.

**원칙: 한 번에 한 단계만 개발한다.** 다른 일을 하려면 사용자에게 기존 작업의 무엇을 대신하는지와 실제 효과를 설명하고 명시적으로 승인을 받는다.

## 10. 절대 금지할 개발 방식

1. 사용자 승인 없이 새 P6-G/H·하위 검증기·대형 화면·새 AI 모델을 계속 늘리기.
2. API 조회/Mock/해시/CI 성공만으로 **사용자가 원하는 종목 분석이 완성됐다**고 보고하기.
3. 실제 사용 브랜치와 다른 브랜치·폴더에서 작업한 뒤 사용자가 pull하면 된다고 안내하기.
4. 기능 변경 범위를 넘어 Strategy/Risk/Scanner/보유 DB를 조용히 수정하기.
5. 사용자 문장 입력이나 외부 데이터 수집 부담을 사용자에게 떠넘기기.
6. 국제 뉴스 헤드라인·AI 확률을 그대로 매수/매도·승률로 바꾸기.
7. 권한 미확인 원천을 모델에 보내거나 기존 과거 분석에 미래 사건을 넣기.
8. 실패한 개발을 그대로 두고 다음 단계로 넘어가기.
9. 현재 단계의 근거가 충분한데도 무한 검증·문서 분할 반복하기.

### 개발 완료 보고 — 이 여섯 가지만

- 이번 단계와 제품 목표
- 실제로 바꾼 코드와 변경 이유
- **사용자 Windows에서 달라진 결과**(CI/Mock과 구분)
- 검증·회귀 근거
- 남은 문제와 차단 사유
- 이 문서에 고정된 다음 단계 한 가지

## 11. 단일 진행표

| 구분 | 현재 상태 (2026-11-01) | 다음 |
|---|---|---|
| **제품 목표 문서** | **실행 기준 사용 중 · 단계별 승인** | 1단계 조사 및 2단계 착수 지시 반영. 별도 범위 확대는 승인 필요 |
| 기존 A단계 요약 UI | DONE · 사용자 Windows 확인 | 보존 |
| 기존 B단계 문장 비교 | REJECTED_PRODUCT_FIT · 코드 존재, 실모델 유료 검증 진행 금지 | 후속 해당 범위에서 UI 정리 |
| **1단계 현황 파악** | **CODE_AUDIT_COMPLETE_WINDOWS_UAT_PENDING** | 2026-11-01 지정 브랜치 코드 연결 조사 완료, 실제 Windows·원천 데이터 미확인. 핵심 갭: Scanner 시장·이벤트 위험 → Risk Gate |
| **2단계 시장·국제 사건 연결** | **MR01_CLOSED_POLICY_REJECTED_MACRO01_NEXT** | 새 PC 120일 KRX 실데이터로 PANIC 후보 검증: 8/120 발동, 10/29·10/30 급락 미포착, 사후 5일 위험 분리 미입증 → 운영 차단 기각. MARKET_RECHECK 유지, 실제 PANIC Gate 미승인. 다음은 기존 US10Y Macro 비차단 시장 설명 연결(MACRO-01), 날짜 반복 Windows 검증 별도 미확인 |
| 3단계 다전략/위험 통합 | NOT_STARTED | 2단계 종료 후 |
| 4단계 JEV 실사용 | NOT_STARTED | 3단계 결과와 허용 입력 확인 후 |
| 5단계 효용 평가 | NOT_STARTED | 4단계 후 |

## 12. 관련 문서와 우선순위

- **본 문서 우선:** 사용자 제품 목적, 분석 범위, 개발 순서, 진행표, 범위 변경 승인.
- **기존 기술 안전 규칙 보존:** StockScope_MASTER_ARCHITECTURE_vNext.md, StockScope_IMPLEMENTATION_BASELINE_vNext.md, 고정 contract, 소스 권한/시간 원칙.
- **과거 문서:** JEV_SINGLE_EXECUTION_PLAN.md의 문장 비교 A→B→C, StockScope_DEVELOPMENT_ROADMAP_vNext.md의 오래된 "다음 작업"은 현 제품 실행 순서가 아니다. 필요한 코드·역사 자료로만 참고한다.
- **다음 채팅 인계:** "실제 브랜치 codex/jev-reviewer-shadow-bridge의 docs/STOCKSCOPE_PRODUCT_EXECUTION_PLAN.md부터 읽고, 승인된 가장 이른 미완료 단계만 수행한다. 사용자 승인 없이 새 기능·문서·다른 브랜치 변경 금지."

**본 요청은 문서 확정안을 만들기 위한 작업이다. 현재는 코드·사용자 DB·유료 API를 변경하지 않는다.**