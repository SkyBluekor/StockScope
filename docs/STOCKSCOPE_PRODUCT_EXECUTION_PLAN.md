# StockScope — 제품 목표·단일 실행계획 (현재 사용 브랜치)

> 기준: 2026-11-02 KST · 저장소 `SkyBluekor/StockScope`
>
> **실제 사용자 브랜치: `codex/p0-01-mvp-c1-c2-integration-20261022` · 로컬 `C:\Projects\StockScope`**
>
> **상태: GLOBAL-01 SPEC_READY / IMPLEMENTATION_NOT_STARTED.** MACRO-02는 사후 연구 종료(생산 판단 미승인), MACRO-01 표시는 유지한다. 이 문서는 현재 사용 브랜치에서 다음 제품 작업을 관리하는 단일 기준이다. `codex/jev-reviewer-shadow-bridge`의 오래된 계획서는 역사적 근거 자료이며 **현재 브랜치에 자동 포함되지 않는다**. 기존 P0 Scanner·Holdings·JEV 작업, 동결된 Strategy/Risk/Scanner 계약을 전부 보존한다. 다른 브랜치 전체 병합 금지.

## 1. 제품 목표와 불변 원칙

StockScope는 다수 국내 주식의 OpenAPI 기반 **주가·시장·거시경제·기업/국제 사건** 자료를 검증하고, 기존 10전략과 단·중·장기 관점, Risk·기존 보유 상태를 종합하여 **초보자도 이해하기 쉬운 투자 판단 보조**를 제공한다. 수익을 보장하지 않으며 실제 주문을 실행하지 않는다. JEV는 적법하게 전달할 수 있는 검증된 입력으로 필요한 종목에만 별도 보조 검토하며 기존 Risk/Scanner 결과를 몰래 변경하지 않는다.

**사용자가 원하는 가치:** '왜 후보인가 / 시장이 왜 위험한가 / 지금 확인할 조건 / 기존 보유 대응과 신규 진입의 차이'를 한 화면에서 이해하는 것. 기존 API·모델·시뮬레이션·검증을 최대한 재사용한다. 실시간/확정 EOD/과거 재생/사후 관측/현재 조회 참조의 시점을 섞지 않는다.

**금지:** 원천 권리 미확인 글로벌·공시·뉴스를 JEV 등 제3자에게 전송, 과거에 없던 정보를 시점 이전의 투자 판단 입력으로 사용, 임의 시장 PANIC 기준·승률 부여, 검증 안 된 인과 추론, 관련 없는 기능을 리팩터링, 사용자 DB·기존 동결 캡처 재작성, 별도 진단 UI/실험 계획서 연쇄 생성.

## 2. 실제 확인한 기준선

| 작업 | 상태와 증거 | 남은 경계 |
|---|---|---|
| Scanner 기존 후보 및 P0 사용자 화면 | 새 PC에서 2026-10-30 선익시스템(171090) 후보·조건 6/6 확인. 현재 사용 브랜치의 재검증·보유 대응 UI 유지 | 조건 충족은 매수 허가 아님 |
| MR-01 국내 지수 PANIC 실험 | 새 PC 2026-05-06~10-30 공통 120일, 기존 '강한 하락' 38일, 시험 정책 8일. 10/29·10/30 큰 하락 모두 미포착, 이후 5거래일 위험 분리 근거 부족 → **시험 정책 운영 차단 기각** | 승인된 생산 PANIC Gate 없음; 기존 경고 유지 |
| MACRO-01 금리 참고 UI | 현재 브랜치에 이식: `frontend/src/components/scannerMacroRateReference.ts`, `ScannerDecisionSummary.tsx`, 기존 `GET /api/macro/reference-diagnostic`. GitHub CI 4/4 PASS(코드 `46296a61`), 관측 오래됨 경고/간결화 CI 4/4 PASS(코드 `051d71d`). 사용자 실제 Scanner 화면에 DGS10 참고 표시 확인 | 원천 발표 시각을 `DATE_ONLY`로만 확보, 생산 결정 입력 승인 없음 |
| 2026년 DGS10 로컬 수집 | 2026-11-02 FRED 기존 `tools/data/collect_macro_next6a_s2.py`로 2026-01-01~10-30 216건 요청, 208건 저장·게시, 8건 missing. 사용자 화면에 관측일 2026-10-29 금리 4.98% 표시 확인 | `fetched_at=2026-11-02`, `time_quality=DATE_ONLY`, `historical_pit_eligible_count=0`. 10/30 과거 Scanner에 그 자료가 있었다는 증거 아님 |
| 10/30 국내 위험 참고 | 구 PC에서 2026-10-30 KOSPI -3.48%, KOSDAQ -3.83%, 상승 종목 비율 18.1%, 평균 절대 종목 변동폭 2.913% 확인 | 글로벌 금리로 인한 국내 하락이라고 단정 불가 |
| MACRO-02 | **2026-11-02 새 PC 120일 실자료 사후 비교 완료 · 연구 종료** | 116일 정렬, 금리 상승일의 지수 평균 약세 관찰. 과거 이용 가능 시점 검증 0일 → 인과·예측·생산 Risk Gate 사용 불승인. 기존 MACRO-01 화면 유지 |

**브랜치 차이:** 기존 별도 브랜치의 자동 Scanner 기준일 역행 방지 코드는 현 `p0-01` 브랜치에 이식하지 않았다. 현재 브랜치가 같거나 최신일이라는 가정으로 다른 브랜치를 병합하지 말 것. MACRO-02와 날짜 결함 수정을 섞지 않는다.

## 3. MACRO-02 — 미국 금리 변화와 국내 시장·종목 반응의 시점 안전한 비교

**상태: RESEARCH_CLOSED / OBSERVATIONAL_DIFFERENCE_FOUND / RELATION_UNVERIFIED / PRODUCTION_UNAPPROVED / SCANNER_UI_UNCHANGED.**

### 3.1 이번 단 하나의 목표

현재 금리 수치('미국 10년물 4.98%')를 읽는 것만으로는 국내 주가의 위험을 판단할 수 없다. **DGS10 금리 변화 방향/폭(bp)과 KOSPI·KOSDAQ 확정 지수 변동, 선택 종목의 시장 대비 성과가 서로 다른 관측임을 명확히 한 상태로 비교**하여, 실제 종목 화면에 사용자에게 유익한 설명을 제공할 수 있는지 확인한다.

이 분석은 **'관측된 동행/차이'**에 국한한다. 미국 금리가 지수 급락을 일으켰다고 단정하거나 자동 매수·매도·PANIC·전략 점수/순위를 고치는 것이 목표가 아니다. 같은 화면에 정보만 늘리고 유익성이 확인되지 않으면 구현을 늘리지 않는다.

### 3.2 기존 기능 재사용 (중복 구현 금지)

- `backend/app/macro/context.py` + `features.py`: DGS10 `rate_level_pct`, `delta_bp_1obs/5obs/10obs`, `observation_date`, `available_at`, source quality를 가진 MacroContext.
- `backend/app/macro/reader.py`: 이미 게시된 `macro.db`의 시점 제한 read-only 관측/이력 조회.
- `backend/app/macro/impact.py:LocalMarketImpactReader`, `backend/app/api/macro.py`의 `/market-stock-impact`·`/event-reference`: 기존 KRX EOD 2공통일 및 시장 대비 종목 움직임의 참고 조합. 이 API들은 **미국 금리와 국내 주가 간의 예측적 인과관계를 계산하지 않는다**.
- `frontend/src/components/MacroEventReferenceInline.tsx`, `useMacroEventReference.ts`, `ScannerDecisionSummary.tsx`: 기존 참고 설명·조회 및 선택 종목 UI 경계. 새 대형 카드, 또 다른 별도 페이지는 금지.
- `backend/app/market/service.py` / `MarketDataService._breadth`, `_market_regime`: 기존 국내 시장 폭·약세 문구. PANIC의 운영 승인 기준으로 자동 전환하지 않는다.

### 3.3 실행 작업 순서 (순차 진행)

1. **읽기 전용 현황 확인:** 기존 새 PC 로컬 `macro.db`의 208개 DGS10 관측과 `market_history.db`의 최대 120 공통 거래일을 사용하여, 두 시계열의 겹침·날짜·결측·관측 정정·시각 품질을 확인한다. 새 수집이나 DB 수정을 요구하지 않는다. 관측 `DATE_ONLY`와 `available_at=11/02` 문제를 첫머리에 기록한다. 일부 데이터가 부족하면 관측 불가로 처리.
2. **시점 해석/비교 계약 고정:** 미국 영업일과 한국 거래일은 시간대가 달라 같은 날짜가 같은 정보 시점을 뜻하지 않는다. 과거의 **사후 기술적 비교(RETROSPECTIVE_DESCRIPTIVE)**와 당시 이용 가능함이 검증된 입력(PIT_VERIFIED)은 반드시 구분. 현 2026년 DGS10은 `historical_pit_eligible_count=0`이므로 과거 전략·백테스트 입력으로 **전면 배제**. 분석일 이후 공개/수집한 자료는 당시 시장 판단 근거라고 표현하지 않는다.
3. **관측 연관성 비교 1회:** 복잡한 모델 대신 기존 DGS10 금리 변동(bp), KRX 시장 하락/상승, 시장 대비 선택 종목의 차이를 같은 **명시된 일자 정렬 규칙**으로 read-only 집계. 금리 전일↔한국 당일 및 기간별 정보 시차/결측률을 병기. 시장 수익률과 종목 수익률을 금리 변화의 원인/결과 또는 예측 성과라고 해석하지 않는다. 사전 정하지 않은 임계값을 표본에 맞춰 반복 최적화하지 않는다. 결과가 일관되지 않으면 `RELATION_NOT_ESTABLISHED`.
4. **제품 반영 여부 판단:** '미국 금리 변화 방향 + 국내 지수 약세 + 종목 시장 대비 상대차'를 한 문장으로 기술할 만한 신뢰성·시점 근거가 **충분한 경우에만** 기존 Scanner 요약의 비차단 참고 섹션을 보강. 증거가 부족하면 기존 MACRO-01 UI 유지하고 `RELATION_UNVERIFIED`만 문서로 보고. 단순히 숫자 여러 개를 붙여 '거시경제 분석 완료'라고 표현 금지.
5. **검증 후 종료:** 실제 날짜가 맞는 금리·시장·종목 사례 1건, 누락/미수집/역행/미래시각/양 시장 기준일 불일치 사례, 종목 변경 중 비동기 응답 혼선, 기존 Scanner 후보 점수·순위·Risk·보유 판정 불변을 회귀 검증한다. GitHub CI, 사용자 PC 실행 화면, 로컬 DB 불변을 별도 표기. 충분하면 종료하고 다음 단계 하나만 제시한다.

### 3.4 작업 범위/금지

**허용:** 기존 조회 계약에 최소 additive reference 필드(필요할 때만), 결과 조합을 위한 소규모 pure/read-only 함수, 선택 종목 설명 한 줄, 필요한 테스트, **이 단일 문서의 결과 갱신**.

**금지:** 새 외부 거시 지표 수집기·뉴스/전쟁 크롤러, 규칙 기반 거짓 인과 설명, 국채금리/지수 단독값으로 위험등급을 임의 승격, 수익 확률 계산, 기존 10전략·Risk Gate·후보 순위·Holdings/P0-03/04/05·JEV 활성화 및 과거 캡처 변경. AI 데이터 전송 금지.

### 3.5 합격 기준

- 실제 KRX 확정 2026-10-30 후보를 예시로 **(1) 종목 전략 기준일, (2) 국내 지수 위험, (3) 가장 가까운 미국 금리 관측일과 이후 조회 시각, (4) 시장 대비 종목 상대 성과**를 혼동 없이 설명 가능. 당시 의사결정 근거라는 가짜 주장은 없음.
- 연구 분석 결과가 불충분하면 적절히 보류하고, UI에 추측 문구·불필요한 코드가 생기지 않는 것이 합격.
- 신규 진입 권고/차단 등 프로덕션 정책은 기존과 동일. 코드 회귀 CI 통과만으로 Windows 실사용 검증을 대체하지 않는다.
- 장기적 '시장 위험을 실제 의사결정에 반영'은 **별도의 충분한 검증 및 정책 승인**을 요한다. MACRO-02 완료만으로 기능 전체 DONE 또는 글로벌 사건/전쟁 해석 완료라고 주장하지 않는다.

### 3.6 MACRO-02 실행 기록 — 읽기 전용 연구 단계 (2026-11-02)

**판정: 연구용 도구 구현·CI 완료, 실제 새 PC 데이터 분석 확인, MACRO-02 사후 연구 종료. 과거 PIT 검증 실패로 생산 반영·추가 UI 설명 보류.**

- 구현: `tools/data/analyze_macro02_eod_relation.py`. 기존 `LocalMacroReader.read_series_window`로 게시된 DGS10 관측/개정본을 조회하고, KRX `day_status` 네 마커와 **실제 양 시장 주식·지수 행**을 확인한 최근 최대 120 공통 거래일만 읽음. 선택 종목 171090/KOSDAQ의 2개 유효 일자 수익률 및 시장 대비 차이는 기존 `LocalMarketImpactReader`를 사용해 별도 계산. 새 데이터 수집·DB/캐시 쓰기·API/JEV 네트워크 없음. `STOCKSCOPE_MACRO_DB`, `STOCKSCOPE_MARKET_STORE_DB` 환경변수 적용.
- 정렬 계약: 한국 EOD 날짜 **이전**인 가장 가까운 미국 DGS10 관측일 하나를 대응하고 이전 미국 관측값과의 **관측 1회 변동 bp**를 계산. 7일 이상 지난 관측·미확보 기준 관측·같은 미국 관측일 중복 사용은 별도 누락 사유 집계. 이 7일은 **단순 데이터 결합 허용 범위**이지 금융 위험 임계값이 아니다. `DATE_ONLY` 데이터는 관측일 선후가 맞아도 당시 한국 장 마감 전 이용 가능성을 증명하지 않으므로 항상 `RETROSPECTIVE_DESCRIPTIVE_ONLY`·`RELATION_UNVERIFIED`; 생산 판단 입력으로 승격하지 않는다.
- 출력: 각 상승/하락/불변 금리 변화군의 겹친 거래일 수와 KOSPI/KOSDAQ 평균 하루 지수 등락률, 누락·재사용 제외 개수, 시점 검증 가능 건수, 최신 대응 날짜 및 선택 종목 상대 수익률. **상관관계가 성립한다/금리가 국내 폭락 원인** 같은 결론 자동 생성 금지.
- 회귀: `backend/tests/test_macro02_retrospective_pairing.py`에서 미국 **당일 관측의 한국 당일 연결 금지**, `DATE_ONLY` 비PIT, 누락/오래된 날짜/중복 관측 제외, 미래 `available_at` 제외, KRX 상태/실제 행 완전성, 선택 종목 비교, 읽기 전용 DB 원본 보존/없는 DB 미생성 검증. 기존 종목 점수·Risk·Holdings·JEV 제품 파일은 변경하지 않았다.
- 검증: 코드 HEAD `848414c7` 기준 [GitHub Actions CI #41381201813](https://github.com/SkyBluekor/StockScope/actions/runs/41381201813) **4/4 PASS**(Backend Python 3.11/3.14 각 2,764 PASS, 2 SKIP, 1 WARNING; Frontend Node 22 PASS; Windows Fresh Clone PASS).
- **실자료 검사 실행 명령 (새 PC `C:\Projects\StockScope`):** `git pull --ff-only` 후 `.\.venv\Scripts\python.exe .\tools\data\analyze_macro02_eod_relation.py --end 2026-10-30 --days 120 --market KOSDAQ --ticker 171090`. 기존 DB를 삭제·재수집하지 않는다. JSON에는 날짜별 집계만 남기고 API 키·포트폴리오는 포함하지 않는다.
- **실자료 집계 확인 완료:** 사용자 새 PC `C:\Projects\StockScope`에서 직접 출력한 읽기 전용 결과를 아래 3.7에 기록함. 데이터 분석은 마쳤으나 **예측·판단 규칙 및 Scanner 설명 추가에는 근거가 부족해 반영하지 않음**. 기존 MACRO-01 화면을 유지.

### 3.7 새 PC 실제 실행 결과 및 최종 판정 (2026-11-02)

**근거:** 사용자가 직접 실행한 `analyze_macro02_eod_relation.py --end 2026-10-30 --days 120 --market KOSDAQ --ticker 171090`의 JSON 콘솔 출력. `macro_reader_status=COMPLETE`, `snapshot_cutoff_utc=2026-11-02T03:11:51.004502+00:00`.

| 평가 | 실제 값 |
|---|---|
| KRX 공통 확정 거래일 | 120일 |
| DGS10 reader 적재 이력 | 1000개 관측 항목(요청 관측 상한 기준, 해당 120일과 일대일 대응 수 아님) |
| 한국 거래일보다 **앞선** 미국 관측일과 대응 | 116일 |
| 제외 | 4일: 미국 관측일 중복 사용. 이전 미국 관측 없음/7일 초과/직전 기준 누락 0건 |
| 과거 정확한 시각까지 검증된 대응(PIT) | **0/116일** |
| 금리 상승 58일 | KOSPI -0.624%, KOSDAQ -0.728% (평균 일간 지수 등락률) |
| 금리 하락 50일 | KOSPI +0.532%, KOSDAQ -0.055% |
| 금리 변화 없음 8일 | KOSPI +0.810%, KOSDAQ +0.682% |
| 가장 마지막 대응 2026-10-30 | 선행 미국 DGS10 관측일 2026-10-29, 직전 관측 대비 **-7bp**, KOSPI **-3.48%**, KOSDAQ **-3.83%** |
| 선익시스템(171090), 10/29→10/30 | 종목 **+0.756%**, KOSDAQ **-3.83%**, 시장 대비 **+4.586%p** |

**판단:** 금리 상승 58일의 두 지수 평균은 금리 하락 50일보다 낮았다(KOSPI 차이 -1.156%p, KOSDAQ 차이 -0.673%p). 이는 관측된 집단 평균 차이이지 금리 때문에 하락했다는 인과관계나 예측 검증이 아니다. 2026-10-30에는 미국 금리가 직전 관측 대비 -7bp 하락했음에도 두 지수가 -3% 이상 떨어져, 금리 방향을 단독으로 사용하는 규칙이 적합하지 않음을 보여준다. 독립된 검증기간·시차의 공개 시각·다른 요인 통제·분산/신뢰구간·거래비용과 실제 영향 평가가 없다. 한 달 또는 특정 사건에 편중됐는지도 집계되지 않았다. **금리/지수 변동이 동행한 관측을 과도한 수익 예측 또는 신호로 확대하지 않는다.**

**데이터 적격성:** 이번 FRED 이력은 `time_quality=DATE_ONLY`, 2026-11-02에 수집되었고 `pit_verified_pairs=0`. 10/30 과거 종목 판단 전에 존재했던 입력이라고 소급할 수 없다. 특히 금리 관측일이 한국 거래일보다 이르다는 것만으로 미국 발표가 한국 장 마감 전임이 증명되지 않는다. `RETROSPECTIVE_DESCRIPTIVE_ONLY`, `RELATION_UNVERIFIED`, `policy_input_approved=false` 유지.

**제품 결정: MACRO-02 사후 연구는 CLOSED.** 현재 데이터를 이유로 Scanner에 '금리 상승으로 약세', '금리 하락으로 반등' 등 새로운 해석 문구나 Risk Gate·전략 점수·후보 순위·JEV 요청·Holdings 변경을 추가하지 않는다. MACRO-01의 실제 금리 수치·관측일·현재 조회 참고 정보는 그대로 제공한다. 이 결론은 단순 금리 자료 표시를 폐기한다는 뜻이 아니다. **실거래 판단에 이용할 수 있는 해외 위험 신호 검증 및 국제 사건 연결은 아직 미완료**이며, 사용자 PC에서 별도의 UI 변경을 확인할 필요도 생기지 않았다.

**다음 단일 작업 제안:** 2단계 잔여 중 **국제 사건/정책·원유·환율·해외지수 자료의 기존 공급자·데이터 권한·최초 이용 가능 시점 점검**. 이미 구현된 `backend/app/macro/event_composition.py`, `backend/app/market/event_risk.py`, `/api/macro/event-reference` 경로 재사용 범위를 확인하되 승인 전 생산 Risk Gate 연결, 신규 크롤러, 뉴스 원문 AI 전송을 하지 않는다. 다음 단계는 별도 착수 요청 이후 진행한다.

## 4. GLOBAL-01 — 해외 위험 자료 사용성 검증 및 첫 참조 신호 연결

**작업 상태: LIVE_KIS_INDEX_DATA_CONFIRMED / OFFICIAL_CODE_IDENTITY_FIXED / USAGE_RIGHTS_UNVERIFIED / SCANNER_NOT_CONNECTED (2026-11-02).**

**작업 범위는 딱 하나:** 국내 KRX 시장 위험을 해석할 때 실제 사용할 수 있는 **해외 증시 대표지수 1종**을 기존 공급자로부터 검증하고, 관측일·시각·권한이 허용되는 경우에만 **선택된 Scanner 종목의 비차단 참고 설명**에 최소 연결한다. 실행 여건이 충족되지 않으면 `SOURCE_UNVERIFIED` 또는 `RIGHTS_UNVERIFIED`를 남기고 기능을 억지로 구현하지 않는다. **환율·유가·전쟁/국제 사건은 같은 단계에서 실제 수집/판정/화면까지 확장하지 않는다.** 다만 원천 가능성·부재·권리 상태를 함께 기록해 향후 작업 순서를 확정한다.

### 4.1 GitHub 코드로 확인한 기준선 — 가정으로 구현하지 말 것

| 자료·경로 | 현재 코드에서 확인한 사실 | GLOBAL-01의 실증해야 할 부분 |
|---|---|---|
| 해외지수 | `backend/app/macro/providers/kis.py`는 KIS 해외 일봉 `inquire-daily-chartprice`의 `N` division capability probe가 있음. `tools/data/macro_capability_next6a_s2.py`는 `.DJI` 기본 예제를 제공 | 사용자의 실제 KIS 계정에서 해당 종목 코드/응답/거래일/단위/출처가 맞는지, 보존·표시 사용이 허용되는지. **probe 성공 ≠ 수집/저장/투자 판단 연결 완료** |
| 환율 | 같은 provider에 `X`(FX) capability probe가 있지만 `--kis-fx-code` 기본값은 None이며 공식 기호 검증이 없으면 `SEMANTICS_UNVERIFIED` | 실제 종목 코드·통화 방향(USD/KRW와 역수 구분)·시각/권한 확인 전 수집/표시 금지 |
| 해외 국채 | `I`(TREASURY) probe 지원. 현재 미국 10년물 DGS10 FRED 수집·MACRO-01 참고 표시가 동작 | 같은 금리를 새 KIS 시계열로 **중복 수집하지 않음**, 측정 정의 비교가 승인될 때만 재검토 |
| 국제 사건/정책·전쟁 | `backend/app/macro/event_composition.py`, `backend/app/api/macro.py:/event-reference`는 DGS10 MacroContext + KRX 시장/종목 반응 + 저장된 P6 Event Evidence의 **참고 조합**. 이 경로만으로 국제 전쟁 뉴스나 호르무즈 사건이 실제 수집/분류되는 것은 아님 | P6 원천/기업-국가·업종 관계/사건시각/정정·철회·권한이 실제로 확보됐는지 확인; 데이터 없으면 `NO_VERIFIED_GLOBAL_EVENT_SOURCE` |
| 유가/원유 | 현재 확인한 KIS Macro probe에는 유가 전용 `OIL/WTI/BRENT` 데이터 소유/수집 경로가 없음 | 기존 제공자/series 계약·접근·라이선스가 확인될 때만 후속 후보. 이 단계에서 가격이나 충격 추정치 생성 금지 |
| 뉴스·공시 권리 | `backend/app/news/policy.py`의 NAVER는 표시 범위, 미승인 AI 변환/원문 보존 제한. `backend/app/event_evidence/policy.py`의 OpenDART는 기존 제품 표시 외 역사 연구·예측/AI 활용 미승인 | 외부 데이터 수집 허용·화면 표시·로컬 보존·과거 평가·제3자 JEV 전송 **각각 독립 권한 판정**. 무근거 승인/전송 금지 |
| 제품 판정 | MACRO-02 KRX 120일 / DGS10 대응 116일 / PIT 0건 → 생산 사용 불승인. Scanner/10전략/Risk/보유 판단은 동결 | 해외지수 값 하나로 국내 급락 원인, PANIC, 매수·매도 추천 또는 AI 최종 판정을 만들어서는 안 됨 |

### 4.2 실행 순서 — 1→2→3→4→5, 한 번에 하나씩

1. **브랜치/데이터 보존 및 공급자 계약 검사:** `C:\Projects\StockScope`, `codex/p0-01-mvp-c1-c2-integration-20261022`에서 HEAD·local diff 확인. 기존 `KIS` 인증/권한/코드·원천 시각 계약 재사용. `macro.db` 및 `market_history.db`를 새 데이터로 덮어쓰지 않음. 사용자의 로컬 키 값을 출력하지 않음.
2. **기존 probe로 좁은 날짜 범위의 해외지수 1종만 실증:** `tools/data/macro_capability_next6a_s2.py --provider KIS --kis-index-only --start 2026-10-22 --end 2026-10-30 --kis-index-code .DJI --no-report-file` 경로 우선. 실행은 실제 작업 착수 후 **외부 요청·계정 비용/호출 가능성 설명과 확인**을 거쳐 수행. probe는 조회에 따른 네트워크만 사용하고 결과를 파일로 저장하지 않도록 `--no-report-file` 적용. `SUPPORTED_WITH_LIMITATIONS`이면 행 수, 날짜 의미·timezone·지수 명칭·식별 코드·누락, 인증 상태, 이용 가능한 필드, retention/redistribution/AI 권한을 별도로 검토. 오류·자격 미설정·빈 데이터면 `SOURCE_UNVERIFIED`로 그날 종료 가능.
3. **시점·사용권 게이트 명확화:** `source_observation_date`, `provider_available_at`, `first_seen_at`, `fetched_at`, `KRX_analysis_date`, `quality`, `rights`를 혼동하지 않는다. 해외 거래일과 국내 EOD 일자 기준의 시차, 결측, 통화/단위의 일관성을 확인한다. 발표/이용 시각 근거가 없으면 **조회 시점 참고만**, 시점 이전 재현·백테스트·프로덕션 결정 입력은 불허. 전송·보존 권한 미확인이면 원시 응답을 저장하지 않는다.
4. **사용자 가치 조건부 연결:** (2)·(3)이 충족되고 **화면 표시 권한이 확인된 경우에 한해서만**, 이미 존재하는 Macro/Market의 **read-only reference API와 `ScannerDecisionSummary` 선택 종목 영역**을 최소 보강한다. 결과는 예컨대 '미국 대표지수의 최근 관측 변화 · 관측일/현재 조회 · 한국 시장과 별개 자료'처럼 사실만 표시. 미국 주가가 한국 지수 하락의 원인이라는 단정, 확률, 가중치, 신규 Risk Gate 차단, 종목별 중복 API 호출 금지. 권한·자료 미흡 시 코드는 추가하지 않고 기존 MACRO-01 유지.
5. **품질·종료:** 원천 성공 1건 또는 미확인 상태 1건의 실제 사용자 PC 증거, 타임스탬프/누락/오류/계정 제한, 종목 전환 stale 비노출, 기존 후보·순위·점수·Risk·Holdings·JEV 불변을 확인. 필요한 코드만 기존 테스트에 추가하고 GitHub CI·Windows 실제 화면·외부 소스 권리 검증을 분리해 기록한다. 한 번의 실증으로 가치가 없으면 `NO_ADDITIONAL_VALUE`로 종료하며 외부 공급자 탐색을 무한 확장하지 않는다.

### 4.2.1 GLOBAL-01 사전 보강 — 해외지수 공급자 응답의 보수적 판정

- 기존 `backend/app/macro/providers/kis.py` probe를 유지하면서 `N` 해외지수에 대해 **종목명(`output1.hts_kor_isnm`), 실제 날짜(`stck_bsop_date`), 양수 유효 지수값(`ovrs_nmix_prpr`), 요청 기간 이내 여부**를 확인한다. 공식 KIS 예제와 필드 이름 대조: [한국투자증권 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_daily_chartprice/chk_inquire_daily_chartprice.py).
- KIS `rt_cd=0`이더라도 행 0개/유효일자 0개/종목명 미확인이라면 `SEMANTICS_UNVERIFIED`로 보고하며 **지원·데이터 완전·권한 승인으로 판정하지 않는다**. 원본 행 대신 유효/무효 개수, 가장 최근 실제 관측일·지수값, 확인된 이름만 요약.
- 기존 `tools/data/macro_capability_next6a_s2.py`에 `--kis-index-only`를 추가해 FX·국채 미설정 상태를 함께 성공/실패로 오인하지 않는다. `--no-report-file`로 보고서 파일을 남기지 않는다. `SEMANTICS_UNVERIFIED`나 `NOT_SUPPORTED`는 종료 코드 비정상으로 보고하여 오류를 성공으로 위장하지 않는다.
- 응답 시각, 지수 세션 마감 시점, 제공자 보존/화면표시·재배포/AI 전송 권한은 **계속 미확인**으로 명시. 이번에는 실제 KIS 네트워크 접속이나 사용자 로컬 데이터 사용 없이 코드를 보강하며 사용자 PC에서 실증이 필요하다. 원본 데이터 DB 쓰기·API 키 노출·Scanner/Risk/JEV 변경은 하지 않는다.
- 공식 API 응답 확인만으로 지수값을 과거 매매 판단이나 국내 지수 하락의 원인 추론에 사용하지 않는다.

**GLOBAL-01 코드 검증 (2026-11-02):** 공급자 검증 보강 커밋 `f93afaa4`, [GitHub Actions #41392802703](https://github.com/SkyBluekor/StockScope/actions/runs/41392802703) **4/4 PASS**. Python 3.11·3.14 각각 **2,767 PASS / 2 SKIP / 1 WARNING**; Frontend Node 22, Windows Fresh Clone PASS. HTTP 200 및 `rt_cd=0`에 행이 없거나 유효 일자·종가/지수값·종목명이 없으면 `SEMANTICS_UNVERIFIED`로 분류하는 테스트 포함. **실제 KIS 계정 응답과 실제 제공자 권한은 아직 검증하지 않았음**. 외부 공급자 호출이 없는 CI는 LIVE_PROVIDER_PASS가 아님.

**새 PC 실조회 명령(조회 1회, 파일 저장 없음):** `cd C:\Projects\StockScope` → `git pull --ff-only` → `.\.venv\Scripts\python.exe .\tools\data\macro_capability_next6a_s2.py --provider KIS --kis-index-only --start 2026-10-22 --end 2026-10-30 --kis-index-code .DJI --no-report-file`. KIS 인증에 따른 API 호출은 실제로 수행하며 원본 시세 DB나 보고서 파일은 작성하지 않는다. 결과 `status`, `index_name`, `index_sample.valid_index_rows`, `index_sample.latest_observation_date`, `limitations`만 확인하고 비밀키·토큰은 공유하지 않는다. `SUPPORTED_WITH_LIMITATIONS`도 **화면 표시/데이터 재배포 권리 확인 전까지 Scanner 연결 승인 상태가 아니다**.

### 4.2.2 사용자 PC 실조회 — KIS `.DJI` 실제 관측 성공, 검증기 이름 가정 수정

- **실제 실행 근거 (2026-11-02):** 사용자 PC `C:\Projects\StockScope`, 계정 `environment=real`, `configured=true`, `authenticated=true`; KIS 해외지수 `N / .DJI` 2026-10-22~2026-10-30 요청에 `row_count=7`, 유효 날짜·양수 지수값 **7/7**, `latest_observation_date=2026-10-30`, `latest_index_level=51770.31`, `has_continuation=false`. 사용자는 실제 API 키/원시 응답/계좌 비밀값을 제공하지 않았다.
- **실제 발견한 결함:** KIS 실응답 `output1`에 `hts_kor_isnm`이 없고 시세 요약 필드만 들어 있음. 기존 GLOBAL-01 코드가 이 선택 필드를 필수로 간주해 `SEMANTICS_UNVERIFIED`를 반환했지만, 지수 영업일과 값의 유효성 검사는 통과했음. 즉 **데이터 조회 실패가 아니라 이름 검증기의 잘못된 필수 조건**.
- **정정 정책:** KIS 공식 예제에서 `FID_COND_MRKT_DIV_CODE=N`, `FID_INPUT_ISCD=.DJI` 요청이 지원됨을 확인하고, S&P DJI도 Reuters 코드 `.DJI`를 Dow Jones Industrial Average로 표기. 공식 코드 정확히 `.DJI`일 때만 `다우존스 산업평균지수`로 식별하고 `index_name_source=OFFICIAL_KIS_REQUEST_CODE`로 구분한다. 제공자 이름이 있다면 `PROVIDER_RESPONSE`가 우선하고, 코드와 이름이 충돌하면 실패 처리. 다른 미승인 코드로 일반화하지 않는다. 공식 참고: https://github.com/koreainvestment/open-trading-api/blob/main/MCP/Kis%20Trading%20MCP/configs/overseas_stock.json 및 https://www.spglobal.com/spdji/kr/indices/equity/dow-jones-industrial-average/
- **판정:** **실제 KIS 해외지수 원천 접속과 일자/값 확인은 성공.** 그러나 소스의 정확한 게시/이용 시각, 거래 세션 마감 의미, 사용자 계정/개인 로컬 활용 이외 공개 앱 배포·재배포·보존 권한, 타인 대상 화면 제공 권한은 **미확인**. KIS는 개인이 자신의 프로그램을 개발하는 사용과 제휴사/외부 고객에게 시세를 제공하는 상황을 구분해 안내한다. 개인용이라고 권리 전체가 승인된 것은 아님: https://apiportal.koreainvestment.com/about-howto 및 https://apiportal.koreainvestment.com/provider.
- **제품 안전선:** 실제 공급자 지표를 통한 시장 비교는 다음 검증 후보지만, 현재 `display_rights_approved=false`, `retention_rights_approved=false`, `ai_transfer_approved=false`, `production_decision_approved=false` 유지. **실제 API 재호출은 필요 없음.** 기존 Scanner·Strategy·Risk·Holdings·JEV에 연결하지 않고 공식 권한의 사용범위를 확정한 다음 최소 참고 표시 여부를 결정한다.

### 4.3 명확한 완료 기준

- **PASS / REFERENCE_CONNECTED:** 실제 사용자 KIS 계정에서 정체·거래일·시각·사용권을 확인한 1개 해외지수를 Scanner 선택 종목의 참고 설명에 안전하게 연결하고, 정상·결측·실패·다른 종목 전환을 검증함. **전략/리스크/매수 판단은 그대로 유지**.
- **BLOCKED / EVIDENCE_INSUFFICIENT:** KIS 미설정·계정 사용 불가·공식 시계열 코드/값 미검증·시각 또는 사용권 미확인 시 사용자에게 **막힌 한 가지 원인과 필요한 조치**만 남기고 종료. 다른 데이터로 거짓 대체하거나 가짜 녹색 PASS를 만들지 않음.
- **마감 기록:** 이 문서에 ① 확인한 실제 공급자/상태 ② 최초 시각·권한 ③ 연결 여부/보류 이유 ④ Git commit/CI/Windows 증거 ⑤ **후속 단계 하나**만 기록. **이번 단계에서 FX/유가/전쟁 자동 해석 구현 완료를 선언하지 않는다.**

**GLOBAL-01 금지 범위:** 신규 대규모 크롤러, 무차별 provider 수집/DB 백필, 가짜 시장 급락 임계값, 뉴스 원문 JEV 전송, 상품/지수별 무한 벤치마크, 기존 Scanner·Risk·Strategy·Holdings·P0·JEV 코드 변경, DB 마이그레이션/기존 캡처 수정, 관련 없는 UI 재구성.

## 5. 고정된 이후 순서

1. **MACRO-02 사후 연구 종료(2026-11-02):** KRX 120일·DGS10 결합 116일 분석, PIT 0건. 단순 평균 차이는 관찰됐지만 인과·예측·생산 판단 승인 불가. 기존 MACRO-01 표시 유지. 같은 표본 임계값 반복 튜닝 금지.
2. **GLOBAL-01 실행:** KIS 해외지수 1종의 실제 계정/권한·기준일·시각/보존 범위를 검증하고 조건을 충족할 경우에만 비차단 참고 연결. FX/유가/국제 사건 자료는 사용 가능성만 기록하고 별도 후속으로 다룬다. 생산 PANIC Gate는 독립 실증·사용자 승인 없이는 불가.
3. **3단계:** 기존 전략 10개·기간·Risk를 단일 후보 화면에서 비교하고 위험 대비 성과를 검증.
4. **4단계:** 허용 입력이 준비된 경우에만 실제 TypeSafe JEV를 선택 후보 보조검토에 사용. 이미 구현된 제공자·비용 제한·P0 기능 재사용.
5. **5단계:** 국내/글로벌/JEV 추가 분석의 실제 효용·오탐·낙폭·비용/지연, 사용자 Windows 경험 평가.

새 작업은 위 계획의 가장 이른 미완료 항목만 실시한다. 기존 `docs/JEV_SINGLE_EXECUTION_PLAN.md` 등은 관련 이전 개발의 기술·이력 자료로 유지하되 이 제품 실행 순서를 재정의하지 않는다.
