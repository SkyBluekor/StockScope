# StockScope — 제품 목표·단일 실행계획 (현재 사용 브랜치)

> 기준: 2026-11-03 KST · 저장소 `SkyBluekor/StockScope`
>
> **실제 사용자 브랜치: `codex/p0-01-mvp-c1-c2-integration-20261022` · 로컬 `C:\Projects\StockScope`**
>
> **현재 상태: JEV-B2 OFFLINE_CHOICE_CONTRACT_IMPLEMENTED / CI_4_OF_4_PASS / REAL_TYPESAFE_CALL_NOT_APPROVED / JEV_A_WINDOWS_UAT_PARTIAL / PRODUCTION_POLICY_FROZEN.** GLOBAL-02-S2 오프라인 계약·Windows 합성 검증 완료, UN 실자료 자동 추출 권리·발표시각 미확인으로 live BLOCKED; S3/S4 보류. STRATEGY-01은 Windows 실데이터 10전략 연구 실행 완료·전략당 2~4건으로 성능 판정 보류. 생산 전략/Risk/JEV/기간 정책은 동결한다. GLOBAL-01-S2의 Windows Scanner 참고표시는 검증 완료(개인·공개 이용권은 별도 확인 중). 생산 전략·Risk 정책은 변경하지 않는다. MACRO-02는 사후 연구 종료(생산 판단 미승인), MACRO-01 표시는 유지한다. 이 문서는 현재 사용 브랜치에서 다음 제품 작업을 관리하는 단일 기준이다. `codex/jev-reviewer-shadow-bridge`의 오래된 계획서는 역사적 근거 자료이며 **현재 브랜치에 자동 포함되지 않는다**. 기존 P0 Scanner·Holdings·JEV 작업, 동결된 Strategy/Risk/Scanner 계약을 전부 보존한다. 다른 브랜치 전체 병합 금지.

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

**작업 상태: GLOBAL-01-S2 WINDOWS_SCANNER_DISPLAY_PASS / LOCAL_RIGHTS_UNVERIFIED / PRODUCTION_UNAPPROVED (2026-11-02).**

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

**GLOBAL-01 기술 검증 후속 (2026-11-02):** 커밋 `fc26097a`(KIS 실응답에 선택적 한글 이름 누락 시 공식 `.DJI` 코드 인지, 이름 출처 분리, 이름 충돌 차단, 실제 응답 모형 회귀 테스트). [GitHub Actions #41393803152](https://github.com/SkyBluekor/StockScope/actions/runs/41393803152) **4/4 PASS**: Backend Python 3.11·3.14, Frontend Node 22, Windows Fresh Clone 모두 통과. 실제 사용자의 7/7 KIS 응답은 기술적으로 수집 가능하다는 사실을 입증하지만, 새 커밋을 사용자 PC에서 직접 다시 실행한 것은 아니다. **실자료/기술 연결은 확인, 표시·보존·외부 제공 권한과 시점 적격성이 미확인이므로 프로덕션 Scanner 연결은 계속 보류.** 동일 API를 반복 호출할 필요는 없다.

### 4.3 명확한 완료 기준

- **PASS / REFERENCE_CONNECTED:** 실제 사용자 KIS 계정에서 정체·거래일·시각·사용권을 확인한 1개 해외지수를 Scanner 선택 종목의 참고 설명에 안전하게 연결하고, 정상·결측·실패·다른 종목 전환을 검증함. **전략/리스크/매수 판단은 그대로 유지**.
- **BLOCKED / EVIDENCE_INSUFFICIENT:** KIS 미설정·계정 사용 불가·공식 시계열 코드/값 미검증·시각 또는 사용권 미확인 시 사용자에게 **막힌 한 가지 원인과 필요한 조치**만 남기고 종료. 다른 데이터로 거짓 대체하거나 가짜 녹색 PASS를 만들지 않음.
- **마감 기록:** 이 문서에 ① 확인한 실제 공급자/상태 ② 최초 시각·권한 ③ 연결 여부/보류 이유 ④ Git commit/CI/Windows 증거 ⑤ **후속 단계 하나**만 기록. **이번 단계에서 FX/유가/전쟁 자동 해석 구현 완료를 선언하지 않는다.**

**GLOBAL-01 금지 범위:** 신규 대규모 크롤러, 무차별 provider 수집/DB 백필, 가짜 시장 급락 임계값, 뉴스 원문 JEV 전송, 상품/지수별 무한 벤치마크, 기존 Scanner·Risk·Strategy·Holdings·P0·JEV 코드 변경, DB 마이그레이션/기존 캡처 수정, 관련 없는 UI 재구성.

### 4.4 다음 실행 명세 — GLOBAL-01-S2: 개인 로컬 해외지수 참고 연결

**상태: WINDOWS_SCANNER_DISPLAY_PASS / LOCAL_OPT_IN_RUNTIME_CONFIRMED / RIGHTS_REVIEW_PENDING / PUBLIC_USAGE_UNAPPROVED.**

**하나의 결과물:** 공식적으로 식별한 KIS 다우존스 일봉(현재 검증된 `.DJI`)을 **개인 PC 로컬 StockScope**에서 KOSPI/KOSDAQ·선택 종목의 기존 시장 위험 설명 곁에 **별도의 비차단 참고값**으로 보여준다. 권한이 확인되지 않는 공개·제3자 이용 방식에서는 KIS 시세를 제공하지 않는다. 이 단계는 미국 지수를 새로운 위험 점수나 국내 하락의 원인으로 만드는 작업이 아니다.

**이미 끝난 일(반복 금지):** 본인 KIS 실계정에서 `.DJI` 2026-10-22~10-30 7/7개 유효 일봉, 마지막 2026-10-30, 지수 51,770.31 실조회 성공. 실응답에 `hts_kor_isnm`이 없을 수 있는 문제를 고친 커밋 `fc26097a` CI 4/4 PASS. 단순 capability probe를 다시 여러 차례 실행하지 않는다.

#### 착수 순서 및 구현 경계

1. **사용 방식·공식 약관 확인(일회성):** StockScope를 **본인 계정·본인 PC에서 본인만 조회하는 개인 로컬 사용**으로 한정할 수 있는지 확인한다. KIS 공식 [개인·일반법인 이용 안내](https://apiportal.koreainvestment.com/about-howto)는 본인 자산·전략을 위한 직접 이용을 설명하고, [제휴 안내](https://apiportal.koreainvestment.com/provider)는 제3자 서비스·거래소 시세정보 이용계약을 별도로 다룬다. **개인 사용 안내 ≠ 모든 화면 표출·복제·공개배포 허가**이므로 사용자 계정에 적용되는 원천/계약 조건을 확인하고 이용 방식만 명시한다. 공개 데모·클라우드·다중 사용자·외부 접근은 불허 상태 유지. **권한 판단이 미확정이면 다음 2~4단계의 라이브 시세 출력은 차단하고 종료 사유를 보고한다.**
2. **기존 공급자 최소 재사용:** `backend/app/macro/providers/kis.py`의 `N/.DJI` 정상화·응답 검증과 `app.integrations.kis` 인증/예외 처리를 재사용한다. capability `probe` 출력을 곧바로 화면 값으로 사용하는 대신, 필요할 때에만 유효 **연속 2거래일 종가**를 읽는 재사용 가능한 소규모 내부 참조 함수로 분리한다. **새 시장·거시 DB, migration, 배치 수집, 외부 뉴스 크롤러는 추가하지 않는다.** 종목별 API 호출 대신 동일 세션에서 공유하는 **서버 메모리 내 최소 참조 스냅샷** 하나를 사용하고, 비밀키/토큰·제공자 원문·계좌정보는 캐시/로그/브라우저로 내보내지 않는다. 실패 후 과거 값을 최신으로 둔갑시키지 않는다.
3. **시점·권한이 분리된 read-only 결과:** 기존 `backend/app/api/macro.py`에 최소 additive **해외지수 참고 응답**만 연결한다(별도 대형 서비스/API 재설계 금지). 표시 가능한 필드는 `source=KIS`, `index_code=.DJI`, `index_name`, `observed_date`, `previous_observed_date`, `observed_close`, 유효한 두 종가로 계산한 `daily_change_pct`, `fetched_at_utc`, `source_time_quality=DATE_ONLY`, `status`, `reason` 및 **별도 display/retention/AI/decision 용도 판정** 정도다. `observation_date`와 `fetched_at`를 동의어로 취급하지 않고, 한국 Scanner의 `data_date` 이전에 실제로 공개되었다는 **PIT 주장 금지**. 환율·유가·전쟁 데이터나 전략 판정 값은 이번 응답에 섞지 않는다.
4. **기존 Scanner 최소 표시:** `frontend/src/components/ScannerDecisionSummary.tsx`의 기존 미국 10년물 국채금리 참고 문구와 인접한 **한 줄** 또는 짧은 상세로 연결한다. 예: `미국 다우존스 · 2026-10-30 관측 · 일간 변동 ±x% (현재 조회 참고)`. **실제 계산된 수치만** 표시하고, 휴장일·오래된 자료·오류·권한 미승인·설정 미완료인 경우에는 수치 대신 제한 사유를 간결히 표시한다. KIS `README`·공개 배포 시 시세 데이터 포함 금지. 종목 변경·Scanner 기준일 변경 시 이전 요청 결과가 현재 종목에 잘못 붙지 않도록 기존 Abort/identity 처리 재사용. 화면에서 매번 KIS를 호출하거나 사용자에게 종목마다 설정을 요구하지 않는다.
5. **실행 안전성 및 검증:** 개인 로컬 스위치는 **기본 비활성**이고 실제 라이브 조회 전 확인된 로컬 이용 조건에서만 활성화; 공개 호스트/리버스 프록시·제3자 접속 가능 구성이라면 서버 측에서 조회·전달을 차단한다(프런트 숨김만으로 권한 구현 완료 처리 금지). 테스트에는 자격 누락, 401/403, 응답행 0개, 날짜 역행, 잘못된 종가, 한 거래일만 존재, US 휴장과 KRX 거래일 불일치, 응답 지연·후보 교체, 스냅샷 재사용, 공개 모드 차단, KIS 서비스 장애에도 기존 Scanner/금리 참고 계속 표시 등을 포함. 기존 Strategy 10개·Risk Gate·순위·Horizon·Holdings·JEV·기존 DB·캡처 불변을 확인한다.
6. **사용자 PC 실검증·종료:** GitHub CI + Windows Fresh Clone과 **사용자 PC 실제 Scanner**를 별도 확인한다. 실제 KIS 계정의 개인 로컬 사용 가능 여부, 공식 출처·관측일·가치/최신성, 단 1회 공유 조회, 브라우저 시각 표시, 네트워크 실패시 기본 분석 보존, 접근 차단을 확인한 다음에만 `REFERENCE_CONNECTED_LOCAL_ONLY`로 판정한다. 데이터 자체를 코드/스크린샷으로 공개 저장하거나 JEV로 전송하지 않는다. 성공/차단 증거와 커밋을 **이 문서에만** 기록하고 종료한다.

**합격 기준:** 개인 로컬 사용 범위가 실제 확인된 경우, 미국 다우존스 관측/전일 대비 움직임을 선택 종목의 기존 시장 위험·FRED 참고 곁에서 구분해 확인할 수 있고, **주문·위험 게이트·추천/랭킹에 미반영**, 해외 원시 시세·비밀정보 저장/전송 0, 장애 시 기존 분석 보존, 공개 접근 차단, 실제 Windows 검증. 개인 로컬 사용 범위 또는 공개 송출 허가가 불명확하면 **`RIGHTS_UNVERIFIED`로 차단**하고 권한 검토 없이 우회하지 않는다.

**이번 작업에서 하지 않을 일:** 미국 지수 단독의 매수/매도 신호·금리/환율/원유/전쟁 인과관계, 신규 데이터셋 백필/모델 학습, JEV 실모델 호출, 글로벌 전체 위험 점수/PANIC 자동 승격, 공개 서비스 출시, KIS 이용권을 넘는 지수 재배포.

### 4.5 GLOBAL-01-S2 구현 및 CI 기록 (2026-11-02)

**코드·CI 구현 완료 / 사용자 PC 실화면 참조 표시 확인 / 개인 로컬 사용권 최종 승인 증빙 미제공.**

- **KIS 재사용:** `backend/app/macro/providers/kis.py`에 `include_reference_pair=True`를 추가해 `.DJI` 최신 서로 다른 관측 2개(일자·지수값·변동률)만 추출. 공식 코드·제공자 이름 검증, 누락·무효값·충돌 날짜 차단. 원본 API 응답/토큰은 보존하지 않는다.
- **메모리 참조:** `backend/app/macro/local_dji.py`는 같은 서버 프로세스에서 성공 600초·실패 45초 공유. 사용자 종목마다 KIS로 재호출하지 않고 Market/Macro/Simulation DB·기존 캡처를 수정하지 않는다.
- **기본 차단:** `GET /api/macro/overseas-index-reference`는 개인 로컬 사용 확인 스위치가 꺼져 있으면 데이터 숫자 없이 `UNAVAILABLE` 반환, 네트워크 호출 없음. 켜져 있어도 loopback peer/Host와 Origin·Referer·Forwarded 등 프록시 관련 헤더 검증을 통과해야 한다. `run-dev.ps1` 및 Vite 개발 서버는 127.0.0.1 바인딩. **외부 공개·reverse proxy 접근 금지**(프록시가 출처를 지우거나 조작하는 경우까지 검증된 인증/인가가 아님).
- **설정 분리:** 기존 프로덕션 fingerprint가 고정된 `backend/app/core/config.py`는 원본 복구. 새 로컬 참조 모듈에서만 `.env`의 `STOCKSCOPE_KIS_DJI_PERSONAL_LOCAL_REFERENCE_ENABLED` 플래그를 읽고 기본값 false 유지.
- **UI:** `ScannerDecisionSummary.tsx`의 기존 FRED 금리 참고 영역에 다우존스 한 줄과 설명 추가. `scannerDjiLocalReference.ts`에서 관측일·수집시각·두 값의 변화율을 재검증하고 확정 종가·당시 Scanner 정보·국내 시장 하락 원인이라고 주장하지 않는다. abort/identity 검사로 다른 후보로 이전 응답이 새는 것을 방지. KIS 오류 시 기존 Scanner/FRED 유지.
- **권한/시점:** `DATE_ONLY`, `session_close_verified=false`; 공급자 발표시각·재배포/보존/AI·생산 판단 적격성은 미확인. 반환 `display_rights_approved`, `retention_rights_approved`, `ai_transfer_approved`, `scanner_input_approved`, `risk_gate_input_approved`, `production_decision_approved`는 모두 false. 개인 로컬 opt-in을 제3자 시세 재배포 허가로 확대하지 않는다.
- **검증:** `backend/tests/test_global01_s2_local_dji_reference.py`, 기존 KIS/Scanner UI 테스트. [GitHub Actions #41401174958](https://github.com/SkyBluekor/StockScope/actions/runs/41401174958) **CI 4/4 PASS** (Python 3.11·3.14 각 2,777 passed / 2 skipped, Frontend Node22 PASS, Windows Fresh Clone PASS), 코드 HEAD `905d8e2e`. 초기 core config 해시 회귀를 수정·복구한 뒤 통과한 결과다.

**실제 Windows UAT 절차 — 해당 KIS 계정의 개인 로컬 조회·화면표시 조건을 직접 확인한 경우에만:**

1. `C:\Projects\StockScope`에서 `git pull --ff-only`. 프로젝트 루트의 비공개 `.env`에 `STOCKSCOPE_KIS_DJI_PERSONAL_LOCAL_REFERENCE_ENABLED=true` 추가. 인증정보나 `.env` 파일을 Git/채팅에 올리지 않음. 이용 조건을 확인할 수 없으면 설정하지 않음.
2. 기존 개발 서버 종료 후 `.\run-dev.ps1` 재실행. `http://127.0.0.1:5173` → Scanner → 실제 후보에서 금리와 다우존스 관측일/변동률을 확인. 개인 KIS 상위 API 조회가 발생할 수 있다.
3. 수치·날짜·기존 전략 불변 및 오류/비활성 처리 실제 화면을 확인 후 UAT 판정 갱신. **사용자 PC 정상 참고표시 1건은 아래 4.6에서 확인됐지만, 권한/장애·공개 접근 실환경 UAT는 미확인**이므로 공개·생산 승인으로 확대하지 않는다.

**후속:** 글로벌 자료(FX/유가/전쟁)는 이 작업에서 구현하지 않음. 현재 정상 표시 검증을 완료했으며 개인/공개 이용권 확인 및 실환경 차단 검증 없이 외부 제공하지 않는다.

### 4.6 사용자 PC Scanner 실화면 증거 (2026-11-02)

**판정: `WINDOWS_SCANNER_DISPLAY_PASS` / `PERSONAL_LOCAL_RIGHTS_UNVERIFIED` / `PRODUCTION_DECISION_UNAPPROVED`.**

- **근거:** 사용자가 직접 업로드한 `localhost:5173/scanner` Windows 브라우저 전체 화면 스크린샷. 브라우저가 실제로 기존 Scanner 오른쪽 선택 종목 상세에 KIS 다우존스 지표를 그렸음. 이것은 GitHub CI 결과와 별개의 **실사용 화면 표시 증거**다. 계정의 데이터 권리 범위까지 검증된 증거는 아님.
- **실제 화면 판독:** 선택 종목 `선익시스템` (KOSDAQ 171090), 분석일 2026-10-30, 기존 전략 조건 6/6. 기존 FRED DGS10 미국 10년물 **4.98%**, 관측일 **2026-10-29**, 자료 이용 가능 기록일 2026-11-02 유지.
- **신규 참고 표시:** `미국 다우존스 51,770.31 · 일간 값 변화 -1.09% · 관측 2026-10-30`. KIS 일별 조회값 수집일 **2026-11-02**. 51,770.31과 관측일은 앞선 사용자의 KIS 실계정 API probe 결과(7/7 유효, 10/30 최신)와 일치. **-1.09%는 이번 화면에서 확인된 계산 결과이며 당시 단순 probe는 직전 관측값을 공개하지 않았으므로 별도 실계정 원시값 대조는 수행하지 않음.**
- **경계 표시:** 화면에 `원천 발표·확정 종가 시각 미확인`, `분석일 이후 조회한 자료로 당시 판단 근거가 아니에요`, `국내 지수 변화의 원인이나 매매 신호로 해석하지 않아요`가 실제 노출됨. 기존 Risk 재확인·새 시세 미확인 및 종목 전략 조건이 유지됨. **화면 내용 관찰만으로 알고리즘 내부 점수 불변을 따로 증명한 것은 아님**(앞선 코드 차이/CI 회귀로 검증).
- **아직 증명하지 못한 사항:** 개인 계정이 해당 로컬 화면표시를 허용하는 구체적 KIS/거래소 약관, 외부/프록시 배포 차단의 실제 운영 환경, 사용자 PC의 KIS 서비스 장애/미설정 전환 실험, 다른 종목 전환 후 스냅샷 재사용. 마지막 세 항목은 자동화 CI 테스트로는 확인했지만 **사용자 PC에서 직접 테스트한 것으로 주장하지 않는다**.
- **변경 범위:** 이 증거를 반영하는 작업은 이 제품 실행계획서에 대한 문서 갱신만 해당한다. 종목 순위·전략점수·Risk Gate·JEV·Holdings·데이터베이스·Scanner UI 추가 변경 없음.

**실행 결론:** 요청한 GLOBAL-01-S2의 **실제 사용자 화면 참조 연결 목표는 충족**. 같은 KIS 수집/검증을 다시 반복할 필요 없음. 다만 별도의 공식 사용권 확인 없이 기능을 공용 클라우드/외부 사용자에게 제공하거나 투자 정책 입력으로 승격하면 안 됨. 기능은 개인 로컬 opt-in 경계를 계속 유지한다.

## 5. STRATEGY-01 — 기존 10개 전략의 실제 성능·위험 및 기간 적격성 검증

**상태: READONLY_REAL_DATA_RESEARCH_COMPLETED / STRATEGY_EVIDENCE_INSUFFICIENT / NO_PRODUCTION_SELECTION (2026-11-02).**

**이번 단 하나의 목표:** 기존 10개 전략이 **같은 확정 KRX 데이터·체결·Risk·비용 가정**에서 얼마나 자주 조건을 충족하고, 종목/시장·기간에 따라 수익·손실·미판정 사례가 어떻게 갈리는지 **재현 가능한 읽기 전용 결과**로 확인한다. 이후 기간별(단·중·장기) 정책을 설계할 근거를 제공하되, 이번 결과만으로 최적 전략·수익 확률·생산 전략 선택을 승인하지 않는다. **새 전략이나 다른 UI 페이지를 만들지 않는다.**

### 5.1 현재 소스에서 확인한 재사용 기준선

| 코드 / 현재 사실 | 이번 작업 처리 |
|---|---|
| `backend/app/backtest/multi_strategy.py:SUPPORTED_STRATEGIES`에 **정확히 10개**: `trend_following`, `pullback`, `breakout`, `support_bounce`, `oversold_bounce`, `range_trading`, `momentum_continuation`, `volatility_squeeze`, `ma20_rebound`, `trend_recovery` | 그대로 사용, 전략 추가·가중치 조정·이름 변경 금지 |
| `MultiStrategyBacktestEngine.run`은 같은 과거 기술·시장 스냅샷으로 10전략을 계산하고 다음 거래일 시가, RiskEngine, 보수적 당일 손절 우선, 전략별 기존 Production Exit, 비중첩 재진입 제약을 사용 | 별도 수익률·청산 엔진 만들지 않고 호출·결과 검증. **실험 출력은 신규 매매 신호가 아님** |
| `backend/app/backtest/metrics.py:summarize_trades`에 거래수·승률·기대수익·중앙값·Profit Factor·연속 손실·MDD, `selector.py:historical_fit`에 표본 부족 기준 존재 | 기존 계산을 사용. **거래 0건과 수익률 0%를 혼동하지 않으며**, 작은 표본이면 `INSUFFICIENT` 또는 해당 사유 기록 |
| `backend/app/horizon.py`에서 `SHORT/MEDIUM/LONG`은 모두 **`EVALUATION_PENDING`**, `HORIZON_NUMERIC_POLICY_NOT_APPROVED` | 5/10/20거래일을 곧바로 단·중·장기로 매핑 금지. 이번 검증의 5/10/20은 **관찰 창**일 뿐 실제 운용 기간/시간 손절 승인 아님 |
| `backend/app/strategy/production_selection_policy.py`에는 active/rollback 핀과 무효 시 기존 10전략 fallback | 실제 활성 선택 정책/버전/정의 해시를 조회해 리포트에 남김. **활성화·롤백·승인 artifact/DB 변경 금지** |
| `backend/app/backtest/market_store.py:HistoricalMarketStore` 생성자는 `_ensure_schema()`·WAL 설정으로 디스크를 변경할 수 있고, `BacktestService` 일부 경로는 누락 데이터를 KRX에서 보충 | 검증 경로는 반드시 `sqlite3` **`mode=ro`** 또는 별도 **메모리 복제**로 기존 DB만 읽고 네트워크/API 요청 0회. 해당 쓰기 가능한 Store/Service 객체를 원본 DB에 직접 생성 금지 |
| 사용자 PC에 확인된 KRX 양 시장 공통 120거래일(~2026-10-30), FRED·KIS 해외지수는 지금 **참고 전용** | 120일만으로 MA120 이전 준비구간과 충분한 단·중·장기 평가 기간이 있다고 가정하지 않음. 해외 금리·DJI는 백테스트 입력에서 제외 |

### 5.2 다음 Codex 실행 단계 (순서 고정)

1. **로컬 데이터 가용성 진단:** `C:\Projects\StockScope`의 `backend/runtime/market_history/market_history.db`가 읽기 전용으로 열리는지 검사. KOSPI/KOSDAQ의 종목·지수별 실제 확정 거래일, 최소 선행 120거래일 준비 데이터 존재 여부, 유효 종가/시가·거래량·거래정지/상장폐지·결측 및 표본 구성의 한계를 먼저 보고. 스키마/DB/원본 캐시·FRED·KIS 데이터를 수정하지 않음. 기존 데이터가 충분치 않으면 `DATA_INSUFFICIENT`로 정리하고 **추가 수집을 자동 시작하지 않음**.
2. **기존 10전략의 단일 read-only 연구 실행기 구현:** 기존 `MultiStrategyBacktestEngine`와 현행 Risk/Exit/metric 함수를 **메모리 입력**으로 재사용하는 `tools/data/analyze_strategy01_existing10.py`를 1개 추가한다. 기본은 실제 사용자의 확정 EOD(예: `--end 2026-10-30`)와 기존 데이터 기간 범위만 조사. KOSPI/KOSDAQ 각 시장에서 데이터가 확인된 종목을 **고정·재현 가능한 사전 정렬/표본 규칙**으로 선정하고, 종목·선정·제외 사유·결측·분석일·전체 모집단 한계를 출력. 사용자 지정 종목도 허용하되 **단일 선익시스템만으로 10전략의 일반 성능을 단정하지 않음**. 기존 데이터만으로 실행할 수 없으면 분석 부재를 명확히 표시.
3. **동일 조건/성과·위험 비교:** 같은 과거 시점 정보·진입(다음 거래일 시가)·Exit·Risk·거래비용·최대 보유일 가정을 고정해 10전략 각각에 대해 `거래 수`, `실제 닫힌 거래 수`, `승률`, `순기대수익(평균/중앙값)`, `Profit Factor`, `MDD(평가 방법)`, `최대 연속 손실`, `보유 기간`, `승인/차단/표본 부족 사유`, `시장별 결과`를 계산한다. 비용 0%를 현실 수익이라고 표현하지 않고, **정해진 비용 시나리오의 가정값을 리포트에 기재**한다. 결과가 없는 전략은 0%가 아니라 `NOT_EVALUABLE`.
4. **과대평가 방지:** 계산에 미래 종가·지수·사후 공개 거시 지표가 유입되지 않는지 확인하고, 동일 종목/시점 중복 거래·데이터 커버리지 부족·샘플 선택 편향·단일 시장 편중·후보/비후보 차이를 표시한다. 가능한 경우 **평가 구간을 시간 순서대로 분리**해 후행 구간 결과를 별도로 제시하되 준비/평가 데이터가 부족하면 `OUT_OF_SAMPLE_UNAVAILABLE`라고 표시하고, 표본에 맞게 임계값을 최적화하거나 같은 구간을 재사용해 성공으로 선언하지 않음.
5. **기간 정책의 현재 상태 출력:** `SHORT`, `MEDIUM`, `LONG` 각각에 **`EVALUATION_PENDING`**을 그대로 출력한다. 관찰 창 5/10/20거래일의 전방 결과는 기존 `scanner_quality`의 `AuditHorizons` 지원이 있고 데이터가 충분한 경우 **사후 관찰**로만 제시. 전략별 적합 기간·자동 리밸런싱/손절 일수·추천 전략 전환은 이 결과로 결정하지 않는다. 긴 기간이 데이터로 불가능하면 명확히 미검증으로 종료.
6. **한 번의 실데이터 검증 및 완료:** 신설 실행기의 단일 CLI(구현 후 `--help`와 실제 PC 명령 안내)·순수/무네트워크 회귀 테스트·GitHub CI·사용자 Windows 읽기 전용 결과를 확보한다. 기본 수치의 근거와 편차를 **이 단일 계획서에만** 정리한다. 사용자 원본 DB 파일 크기·수정시각 변화 0, 신규 네트워크 호출 0, 고정 Scanner/10전략/Exit/Risk/P5 활성 정책/보유/JEV 변화 0을 확인. 연구 결론이 부족하면 **실험 종료 + 다음에 필요한 데이터 한 가지만 제시**하고 같은 표본 재최적화 반복 금지.

### 5.3 합격 및 중단 기준

- **PASS / RESEARCH_COMPLETE:** 10개 전략의 **실제 선택·불선택 상태**가 빠짐없이 제시되고, 공통 데이터 범위·샘플 분포·비용·포지션·Risk·Exit·각 전략 성과/결측 근거가 재현되며, 데이터 부족/재현 실패 시 수익 성과를 주장하지 않는다. 기간별 지원 여부는 **승인되지 않았다**는 사실이 출력에 반영된다.
- **BLOCKED / DATA_INSUFFICIENT:** 준비구간/거래수/분산/종목 대표성 또는 한쪽 시장 데이터가 불충분해 효과 비교가 무의미하면 `DATA_INSUFFICIENT`·구체적 누락 사유로 종료. **임의의 과거 거래나 수익을 보충하지 않으며 자동 KRX 재수집 금지**.
- **BLOCKED / REGRESSION:** 생산 전략/선택 정책/리스크/Exit/Scanner의 파일이나 지표가 바뀌면 이번 작업은 실패. 기준 해시·CI·사용자 PC 원본 DB는 보존하고 원인부터 수정.
- **절대 금지:** `EVALUATION_PENDING` 기간을 강제로 `SUPPORTED` 승격, 10전략 가중치 튜닝, 매수 확률/확정 수익·가짜 승률 표시, 거래비용 무시한 최적 전략 선정, 서드파티 AI에 권한 미확인 FRED/KIS/KRX 뉴스 전송, 신규 대시보드·별도 계획서 계속 추가.

**이번 단계가 성공한 뒤의 경계:** 단·중·장기 전략을 실제로 승인하고 사용자 후보 추천에 적용하려면 **독립 표본·기간 정책 설계·검증·명시적 승인**이 추가로 필요하다. 이번 STRATEGY-01은 그 결정을 위한 근거를 확보하는 **연구 완료**이지 생산 활성화가 아니다.

### 5.4 STRATEGY-01 구현·회귀 결과 (2026-11-02)

**판정: 연구 실행기 코드 구현 및 CI 완료 / 사용자 PC의 KRX 실데이터 검증 대기 / 운영 정책 미변경.**

- 코드: `tools/data/analyze_strategy01_existing10.py`. `sqlite3`의 URI `mode=ro` 및 `PRAGMA query_only=ON`으로 기존 `market_history.db`를 조회한다. 기존 쓰기 가능한 `HistoricalMarketStore`와 KRX 공급자를 호출하지 않으며 **네트워크 0·시장 DB 변경 0·신규 시세 수집 0**을 기본 계약으로 둔다.
- 입력: **양 시장 주식·지수 DATA가 동시에 기록된 공통 거래일**, 실제 지수/종목 JSON 날짜 및 OHLC·거래대금 적격성을 검사한다. 기본 **120거래일 준비구간 + 40거래일 평가구간 = 160일**이 없거나 기간 안의 부분 수집일·종목 결측이 확인되면 데이터를 임의 보충하지 않고 `DATA_INSUFFICIENT`로 보고한다.
- 표본: 완전한 시계열 종목을 KOSPI/KOSDAQ 각각 최대 2개 선정, 같은 비용·진입·청산 가정으로 기존 10전략을 반복한다. 이 방식은 **현재까지 살아남아 충분한 데이터가 있는 종목을 우선하는 사후 표본선택 편향**이 있어 전 종목의 예측 효과를 대표하지 않는다.
- 엔진: 기존 `MultiStrategyBacktestEngine`의 과거 시점 스냅샷과 `_run_strategy(include_trade_history=True)`를 재사용. `ProductionExitPolicyRegistry.ensure_mapping`의 운영 정책 자동 생성 부작용을 **`ReadOnlyExitRegistry`로 차단**하고, 존재하는 운영 Exit 매핑만 읽거나 안전 기준선 fallback을 사용한다. 기존 전략 점수·Risk/Exit·운영 선택 정책·Holdings·JEV/Scanner 코드는 수정하지 않았다.
- 출력: 10개 전략 모두의 신호수·Risk 차단·모의 거래·종료일 미청산 거래·실제 종료거래 승률/기대수익/Profit Factor·실험 구간 전후 분할·양 시장별 결과·단일종목 기준 MDD/연속손실·Exit ID. 종료일 임시 청산(`END_OF_DATA`)을 확정 거래 성과와 분리하고, MDD는 **포트폴리오 MDD가 아니라 종목별 기존 엔진 지표**임을 표시한다. 유효 종료 거래가 0건이면 `NOT_EVALUABLE`, 적으면 `INSUFFICIENT_TRADES`로 표시한다.
- 기간: `SHORT/MEDIUM/LONG`은 기존 `EVALUATION_PENDING` 유지. 관찰기간 5·10·20일을 기간 정책으로 임의 승인하지 않는다. 기본 `--cost-pct 0.3`은 **검증 시나리오의 왕복 비용 가정**이며 실제 거래 수수료/세금이 확정되었다는 뜻이 아니다.
- 테스트: `backend/tests/test_strategy01_readonly_research.py`에서 없는 DB 미생성, 읽기 전용, 120일 부족 판정, 양 시장 표본 및 결측, 운영 Exit 자동 생성 차단, 거래 0건 분리, 실제 기존 10전략 엔진 활용을 검증. [GitHub Actions #41407914516](https://github.com/SkyBluekor/StockScope/actions/runs/41407914516) **CI 4/4 PASS**, Backend Python 3.11·3.14 각각 **2,783 passed / 2 skipped**, Frontend Node 22·Windows Fresh Clone PASS. 구현 코드 최종 HEAD `bff7109c`.

**사용자 PC 검증 명령(실제 KRX 원본을 변경하지 않음):**

```powershell
cd C:\Projects\StockScope
git pull --ff-only
$python = '.\.venv\Scripts\python.exe'
$script = '.\tools\data\analyze_strategy01_existing10.py'
& $python $script --end 2026-10-30 --days 40 --warmup 120 --per-market 2 --cost-pct 0.3 --check-only
if ($LASTEXITCODE -eq 0) {
    & $python $script --end 2026-10-30 --days 40 --warmup 120 --per-market 2 --cost-pct 0.3
}
```

`--check-only`가 실패 코드 2를 반환하면서 `DATA_INSUFFICIENT`를 출력했다면 **실제 연구는 실행하지 않도록 명시**했다. 이전 MACRO-02에서 확인된 120 공통일이 로컬 DB 전체인지 확정되지 않았으므로 **160일 충족을 추정해서는 안 된다**. 이 경우 필요한 추가 기간을 1회 보고하고 **사용자 승인 없이 자동 수집하지 않는다**.

**완료 경계:** CI는 코드 품질 근거일 뿐 사용자 로컬 실데이터의 전략별 성과·위험을 의미하지 않는다. 사용자 PC에서 나온 실제 JSON을 확인해 이 문서에 한 번 기록한 뒤에만 연구가 실제 수행되었다고 판정한다. JEV·GLOBAL-02·기간 수치 정책·운영 리스크/전략 선택은 변경하지 않는다.

### 5.5 사용자 PC 최초 실데이터 진단과 휴장 상태 처리 수정 (2026-11-02)

**실행 사실:** 사용자 PC `C:\Projects\StockScope`에서 `git pull --ff-only` 후 `--end 2026-10-30 --days 40 --warmup 120 --per-market 2 --cost-pct 0.3 --check-only`를 실행했다. `required_common_sessions=160`, `available_common_sessions=160`, `warmup_start=20260309`, `evaluation_start=20260901`, `evaluation_end=20261030`. **DB에 공통 160개 DATA 거래일이 확보되었음이 확인됐다.** 다만 검증기가 `PARTIAL_KRX_MARKET_DAYS`로 잘못 중단하여 실제 백테스트는 실행되지 않았다.

**실패 원인:** 구 버전 연구 실행기는 `day_status`의 **모든 날짜**를 공통 거래일과 비교해 차집합을 결측으로 간주했다. 기존 `HistoricalMarketStore.put_stock_day/put_index_day`는 자료가 없는 안정된 날짜를 `status='empty'`로 기록하므로 휴장/비거래 기록도 차집합에 포함되는 결함이 있었다. 사용자 출력에 `20260501,20260505,20260525,20260603,20260717,20260817,20260924,20260925,20261005,20261009` 등이 포함됐다. **이 날짜들의 실제 각 DB 상태 값 자체는 아직 사용자 PC에서 재조회하지 않았으므로 개별 날짜를 전부 휴장이라고 최종 단정하지 않는다.**

**수정:** `tools/data/analyze_strategy01_existing10.py`에서 `status='data'`인 날짜가 공통 4개 DATA 마커에 미달한 경우만 `PARTIAL_KRX_MARKET_DAYS`로 차단하고, **DATA 상태가 전혀 없고 비거래 기록만 있는 날짜는 `ignored_nontrading_marker_dates`의 개수·샘플로 구분**한다. 실제 일부만 수집된 거래일 차단 로직은 유지. 요일/공휴일을 하드코딩하거나 원본 데이터를 지우지 않는다. `backend/tests/test_strategy01_readonly_research.py`에 4개 empty 마커 휴장 통과 및 그 날짜에 data 마커 하나가 생기면 차단되는 회귀 테스트 추가.

**검증:** 코드 수정 커밋 `a151c6c8`, [GitHub Actions #41409450235](https://github.com/SkyBluekor/StockScope/actions/runs/41409450235) **4/4 PASS**, Backend Python 3.11/3.14 각 **2,784 passed, 2 skipped**; Frontend Node 22·Windows Fresh Clone PASS. **사용자 실DB의 수정 후 READY 판정 및 10전략 연구 결과는 아직 미검증**. 기존 Scanner·Risk·Exit·JEV·Holdings·프로덕션 전략·DB는 변경하지 않았다.

**다음 검증은 한 번만:** 동일 사용자 PC에서 `git pull --ff-only` 후 기존 `--check-only`를 다시 실행한다. `READY_TO_RESEARCH`이면 같은 CLI의 실제 연구 모드로 진행한다. 여전히 부분 DATA 날짜 또는 종목/지수 결측이면 출력된 **실제 이유**를 검토하고, 임의로 필터를 더 느슨하게 만들거나 추가 API 수집을 자동 진행하지 않는다.


### 5.6 새 PC 실제 10전략 결과 — 실행 성공, 성능 판정 유보 (2026-11-02)

**증거:** 사용자가 직접 제출한 Windows PowerShell 실실행 로그 `analyze_strategy01_existing10.py --end 2026-10-30 --days 40 --warmup 120 --per-market 2 --cost-pct 0.3`, 먼저 `--check-only`에서 **`READY_TO_RESEARCH`**, 이후 본 실행에서 **`RESEARCH_DESCRIPTIVE_ONLY` / `PIT_AND_INDEPENDENT_OUT_OF_SAMPLE_UNVERIFIED`**. 코드 수정 `a151c6c8`, 최종 문서 동기화 전 `f590b829`까지 Windows pull 성공. 재수집/DB 쓰기/네트워크 0, 정책 활성화 false라고 도구에서 보고.

| 관측 | 결과 |
|---|---|
| 공통 KRX 데이터 | 160거래일: 준비 120일(2026-03-09 시작), 평가 40일(2026-09-01~10-30) |
| 비거래 기록 제외 | 10일 `NO_DATA_MARKERS_IN_EITHER_KRX_MARKET`로 정상 분류. 이력의 과거 `PARTIAL_KRX_MARKET_DAYS` 오판 수정 **실DB에서 검증 완료** |
| 평가한 종목 | KOSPI `000020`, `000050`; KOSDAQ `0001A0`, `000250` (각 40개의 signal snapshots, 양 시장 포함). `000040`은 `STOCK_INCOMPLETE`로 제외 |
| 비교 가정 | 1회 왕복 비용 0.3%(실제 확정 비용 아님), 최대 보유 20거래일(실험상의 제한·승인된 기간 정책 아님), 다음 거래일 시가 진입 / 보수적 손절 우선 |
| 모든 전략에 적용된 Exit | `exit_mapping_present=false`, `EXIT_PRODUCTION_V2-baseline`, **10개 모두 `TARGET1_FULL_EXIT` 기본 정책**. *각 전략에 승인된 개별 운영 Exit 정책을 검증했다는 뜻이 아님* |
| 전략 신호/모의 거래 | 10개 전략 결과를 단순 합산한 신호 41, 모의 거래 41, 만기 `END_OF_DATA` 11, **종료 거래 30**. 동일 종목·거래시점이 여러 전략에 겹칠 수 있으므로 30개 독립 표본이라고 주장하지 않음 |
| 실제 확정된 정책 | `production_decision_approved=false`; SHORT/MEDIUM/LONG 전부 `EVALUATION_PENDING` 유지 |

**전략별 실제 종료 거래(겹침 가능)와 계산된 사후 성과 — *아래 10개 모두 `INSUFFICIENT_TRADES`***:

| 10개 전략 | 종료 거래 | 승률 | 평균 순수익률 | 종료일 검열(미청산) |
|---|---:|---:|---:|---:|
| `trend_following` | 2 | 50.0% | -5.754% | 2 |
| `pullback` | 2 | 50.0% | -4.455% | 2 |
| `breakout` | 4 | 50.0% | -5.058% | 0 |
| `support_bounce` | 4 | 75.0% | +0.808% | 2 |
| `oversold_bounce` | 2 | 50.0% | +1.334% | 1 |
| `range_trading` | 2 | 100.0% | +3.246% | 1 |
| `momentum_continuation` | 2 | 50.0% | -6.775% | 1 |
| `volatility_squeeze` | 4 | 50.0% | -4.258% | 0 |
| `ma20_rebound` | 4 | 25.0% | -5.217% | 1 |
| `trend_recovery` | 4 | 50.0% | -3.287% | 1 |

**해석:** 백테스트는 기술적으로 정상 실행됐으나 **전략당 종료 거래가 최대 4건**이다. 사후 생존·완전 데이터 종목 우선 선택, 전체 4종목·40평가일, 전략별 거래 겹침, 종료일 미완료 거래 11건, 독립된 외표본 검증/원천 시점 증거 부재, 기본 Exit fallback 등으로 인해 **승률·기대수익의 신뢰성/우열을 판단할 근거가 부족**하다. 박스권의 2건/100% 및 반등 전략의 일부 양수 평균을 **추천·확률·승인**으로 전환하지 않는다. 실패 전략으로 확정하거나 가중치를 낮추지도 않는다. 마크투마켓 MDD도 포트폴리오 위험도로 확대하지 않는다.

**STRATEGY-01 판정:** `READONLY_RESEARCH_EXECUTED`, `EVIDENCE_INSUFFICIENT_ALL_10`, `PRODUCTION_STRATEGY_CHANGE=0`. 이번 같은 4종목/40일 구간을 반복 최적화하지 않고 연구 실행 단계는 여기서 **종료**한다. **다음에 전략의 실제 효과를 판단하려면:** KOSPI/KOSDAQ에 걸친 더 넓은 종목·과거 기간, 충분한 독립 종료 거래와 운영 Exit 정책 적용 범위를 확보하고 시점 누수·생존 편향·외표본을 검증해야 한다. 별도 승인 없는 새 KRX 백필/자동 수집은 하지 않는다. 현재 생산 전략/기간 정책은 그대로 유지한다.

## 6. 이후 고정 실행 순서

1. **완료:** MACRO-01 FRED 참고, MACRO-02 120거래일/116금리 관측의 사후 분석(운영 판단 불승인), GLOBAL-01-S2 KIS 다우존스 개인 로컬 표시(Windows 실화면 확인, 외부 권리 미확인). 같은 API 프로브 반복 금지.
2. **STRATEGY-01 실자료 사후 연구 종료(2026-11-02) / 생산 승인 보류:** 160거래일/4종목/10전략 실행, 모두 종료 거래 2~4건으로 `INSUFFICIENT_TRADES`, 기본 Exit fallback. 재현 실행 성공과 전략 효과 검증은 구분. 장기 독립 데이터/종목 범위 확장은 별도 후속 승인 사항이며 전략 가중치·Risk·기간 정책 불변.
3. **GLOBAL-02-S1 사후 연구와 S2 합성 계약·Windows 검증 완료(§7.6–7.8):** FX 38일/Brent 37일 사후 매칭, S2 합성 변경 4건 검증·CI 4/4 PASS. UN 실데이터 자동 추출·파생 이용 권한과 공식 게시 UTC 미확인으로 S2 live BLOCKED, S3/S4 보류. 같은 합성 fixture·권한 미확인 API 프로브를 반복하지 않는다.
4. **다음 단일 작업 JEV-A-WINDOWS-UAT (§8):** 기구현 AI 검토 기본 화면의 Windows 실사용 인수. 기존 CI 결과를 재사용, A 수용 전 B 실제 유료 호출을 구현·실행하지 않음. 이후 B는 사용자가 직접 작성·권리 보유한 입력만 허용하여 기존 TypeSafe로 실제 종목 1건을 수동 검토하도록 준비한다.
5. **제품 통합 검증:** 사용자가 초보자여도 신규 진입·보유 대응·단중장기 전략·국내외 위험·AI 근거를 구분할 수 있는지, 오탐·낙폭·비용/지연·실제 Windows 사용성을 평가.

새 작업은 가장 이른 미완료 항목만 실시한다. 전략 성능 검증 결과가 없다고 **기존 MACRO/UI를 더 늘려 시간을 소비하지 않는다**. `docs/JEV_SINGLE_EXECUTION_PLAN.md` 및 개별 과거 계획은 기술적 근거 문서로 보존하되 본 단일 실행순서를 대체하지 않는다.

## 7. GLOBAL-02 — 환율·원유·국제 사건을 실제 시장 맥락과 연결

**상태: GLOBAL-02-S1 REAL_FRED_KRX_RETROSPECTIVE_RESEARCH_COMPLETED / HISTORICAL_PIT_UNVERIFIED / PUBLIC_REDISTRIBUTION_UNAPPROVED (2026-11-03).**

### 7.1 제품 목표와 이번 작업의 경계

StockScope의 목표는 미국 금리·해외 지수를 단순 표시하는 것이 아니라 **환율 변동·원유 가격·국제 분쟁/제재·정책 변화와 국내 지수/업종/보유종목에 미치는 가능성 있는 영향을 사용자에게 설명할 근거를 마련**하는 것이다. 하지만 **시계열의 동행/후행 관계 ≠ 사건의 인과관계 ≠ 매매 신호**다. MACRO-01 FRED DGS10, MACRO-02 사후 금리연구(116쌍, 인과/시점 적격성 불승인), GLOBAL-01 KIS .DJI 개인 로컬 참고, NEXT-6C `macro/impact.py`의 1공통거래일 시장·종목 서술, NEXT-6D `api/macro.py:event-reference`는 이미 존재한다. 이 경로들을 무시하고 새 거시·사건·Risk 엔진을 중복 개발하면 안 된다.

**이번 S1의 한 가지 실질적 산출물:** 기존 FRED 접속 + 기존 KRX 읽기 전용 데이터를 결합해, **원/달러(미국 뉴욕 기준)와 브렌트유(미국 EIA 자료)의 실제 관측 변화에 대응하는 KOSPI/KOSDAQ의 사후 관측 결과를 설명하는 1개 연구 보고서**를 만든다. 사용자가 보기에 상승·하락 방향과 시장 데이터 기간/부재를 구분할 수 있어야 한다. 이때 자료의 한국 거래시각 선후관계가 입증되지 않았으면 `RETROSPECTIVE_ONLY`로 고정하고 역사적 전략 판단 또는 추천에 투입하지 않는다. **GLOBAL-02-S1에서 새 Scanner 화면 카드나 Risk 점수 추가 없음**; 숫자만 한 줄 더 놓는 일을 완료로 간주하지 않는다.

### 7.2 공식 원천 후보와 데이터 계약 — **실조회/사용권은 구현 단계에서 따로 검증**

| 데이터 | 소스 계약 후보 | 단위/의미 | 확인할 제약 |
|---|---|---|---|
| USD/KRW | FRED `DEXKOUS`, 원 출처 미 연준 Board of Governors, H.10 | **1달러당 KRW**, 뉴욕 정오 기준 구매율. 값 상승 = 원화 약세 | 한국 장 종가·국내 실시간 환율이 아님. 미 영업일, 최초 게시/수정시각·이용권 확인 |
| 원유 | FRED `DCOILBRENTEU`, 원 출처 U.S. EIA | **Brent-Europe 일별 현물 USD/배럴** | WTI·선물·국내 정유사 조달가 아님. 게시 지연·수정·이용권 확인 |
| 국내 비교 | 이미 저장된 `backend/runtime/market_history/market_history.db` | KOSPI/KOSDAQ 확정 지수의 실제 종가 변화 | 공통 거래일/휴장 상태·정합성·사후 관측과 정보 이용 가능 시점의 차이 |

- 공식 시리즈: https://fred.stlouisfed.org/series/DEXKOUS , https://fred.stlouisfed.org/series/DCOILBRENTEU . FRED 이용 조건: https://fred.stlouisfed.org/legal/terms/ .
- FRED 시리즈·제공자별 권리 조건을 구별해야 한다. **FRED API 키가 있다 ≠ 외부 유료 서비스 재배포·AI 입력·장기 보존 허가**. 원 데이터의 권리 소유자, 저작권 표기, 인용 요건, 개인 로컬 사용 범위와 FRED 자체 금지 행위를 점검하고 결과를 `rights_status`로 기록한다. 구체적 사용권이 불확실하면 **외부 제공·AI 송신·원천 저장·화면 공개를 차단**하고 메타데이터만 보고한다. 이번 작업은 원시 뉴스 본문/원시 시세를 LLM에 보내지 않는다.
- KIS 해외일봉의 `X` 환율 division은 **코드·의미 검증이 끝나지 않은 상태**다. 공식 원천 코드를 증명하지 못했으면 임의 티커로 API를 반복 호출하지 않는다. `DEXKOUS`를 KIS 실시간 환율과 같다고 혼합하지 않는다.
- 유가의 대체 WTI `DCOILWTICO`는 **이번 범위의 추가 입력이 아니다**. 추후 Brent 결측/시장 관련성으로 데이터원 교체가 필요할 때 별도 비교한다.

### 7.3 GLOBAL-02-S1 Codex 구현 명세 — 순서 고정

1. **기존 능력의 재사용 지점 확정:** `backend/app/integrations/fred/client.py:FredClient.series/observations`로 DEXKOUS·DCOILBRENTEU의 공급자 메타데이터(시리즈 ID, 제목, 빈도, 단위, 원천, 시계열 기간/게시 정보)와 소량 실관측 가능성을 1회 검증한다. 기존 `backend/app/macro/providers/fred.py`의 DGS10 계약·정규화·비밀키 제외 패턴을 참고하되 DGS10 의존 정규화를 무리하게 재사용하지 않는다. 승인되지 않은 KIS 코드를 추측하거나 별도의 거시 데이터 공급자 스택을 신설하지 않는다. 이용권/원천 확인 실패 시 `SOURCE_RIGHTS_UNVERIFIED`·`SEMANTICS_UNVERIFIED`를 구분해 종료.
2. **두 시계열의 엄격한 정규화:** 신규 소규모 `backend/app/macro/global02_fx_oil.py`(이름 제안)에 `source_series_id`, `unit`, `observation_date`, `value`, `previous_observation_date`, `change_pct`, `retrieved_at_utc`, `provider_published_at_utc|null`, `time_quality`, `rights_status`, `revision_or_vintage_status`, `staleness`를 구별하는 read-only 계약 구현. 두 시리즈의 **원래 방향성**을 숨기지 않음(DEXKOUS 상승=원화 약세, Brent 상승=유가 상승); 값이 `.`/음수/0/비정상/중복·역순 날짜면 필터 또는 `UNAVAILABLE`; 결측 날짜를 이전 가격으로 0% 변화라 채우지 않는다. 관측일 ≠ 공식 게시/한국시장 이용 가능 시각. FRED 최초 조회 시각이나 `realtime_start`만으로 PIT 적격성을 주장하지 않는다.
3. **기존 KRX와 1개 읽기 전용 사후 검증:** 신규 단일 CLI `tools/data/analyze_global02_fx_oil.py`(이름 제안). 기존 DB를 `sqlite3 URI mode=ro`와 `query_only=ON`으로 열며 `HistoricalMarketStore` 생성/스키마 쓰기/신규 KRX 수집을 금지. KOSPI/KOSDAQ의 **완전한 공통 거래일**과 `empty` 비거래 기록을 분리한다(STRATEGY-01에서 바로 수정한 휴장 차단 회귀 재사용). FRED 미국 관측일·KRX 한국 시장일 간 **교차시차를 표기**하고, 해외 자료의 `provider_published_at_utc`가 없으면 미래정보 유출 가능성을 배제하지 않은 `RETROSPECTIVE_ONLY` 자료로만 관측 전후 결과·표본수·상승/하락/결측·차이를 보여준다. **업종·종목 영향은 신뢰할 수 있는 종목별/업종별 시점매핑을 확보하기 전까지 주장하지 않는다.**
4. **실질적 결과 확인:** 보고서는 `data_coverage`, `unit`, `observation_date`, `retrieved_at_utc`, `direction`, `matched_KRX_common_sessions`, `unmatched_reason`, KOSPI/KOSDAQ 관측 변화, `claim_scope=DESCRIPTIVE_ONLY`, `historical_decision_eligible=false`, `production_decision_approved=false`, `ai_transfer_approved=false`를 포함한다. 자료가 부족하면 **`DATA_INSUFFICIENT`**, 실조회 실패면 **`SOURCE_UNAVAILABLE`**, 권리 불명확 시 **`RIGHTS_UNVERIFIED`**로 정확히 출력하고 관계·효과·확률을 추정으로 채우지 않는다. 유의미해 보이는 양·음 상관이 나오더라도 매수확률·전쟁 인과 또는 매매중단 Gate로 변환하지 않는다. 원시 시세의 출력/파일 보존은 이용권 확인 범위 안에서만; 기본은 **요약 JSON stdout만**.
5. **안전성·회귀:** 테스트는 시리즈 오인/역단위·뉴욕 정오와 한국 장 마감 혼동·미국 휴장/한국 거래일·EIA 게시 지연·빈/결측·중복·수정(vintage)·시각 확인 불가·권리 미승인·누락 시장 날짜·미래 데이터 유입·미설정 API/401/429/5xx, API 키 비노출, 기존 KRX DB 원본 미변경, no JEV outbound, 실패 시 정상 Macro/Scanner/FRED DGS10·DJI 그대로 등을 포함한다. 모의 HTTP/fixture 테스트와 실제 인증 1회 검증을 분리. 운영 기능의 snapshot/golden fingerprint와 Windows Fresh Clone CI를 통과해야 한다.
6. **사용자 PC 단 한 번의 UAT:** CI PASS 뒤 `C:\Projects\StockScope`에서 기존 FRED 키를 안전하게 사용해 실제 두 시계열의 메타데이터·공급 가능 범위·관측일과 샘플을 확인하고, KRX 160일 DB의 공통 거래일에 매칭된 **실제 개수**를 검증한다. 민감정보·뉴스 본문/권리 불명확 자료를 GitHub에 올리지 않는다. 결과는 **기존 이 문서 §7에만** 기록. 법적/시점상 사용 불가능하면 차단 사유를 정확히 고정하고 다른 API를 무한히 돌며 우회하지 않는다.

**GLOBAL-02-S1 완료 조건:** 실제 FX와 Brent 각각에 대해 원천/단위·관측/공개시각·결측/권리 판정이 명확하고, 합법적 로컬 이용 범위에서 **기존 국내 시장 공통 거래일과 매칭된 사후 분석을 재현**하며, 데이터 부족·권리 제한을 정직하게 표시한다. **연구 실행 완료는 제품의 인과관계·예측력·투자 정책 승인을 뜻하지 않는다.** 실제 수집·연구가 제한되면 원인과 다음에 필요한 단 한 가지 조건을 제시하고 종료한다.

### 7.4 GLOBAL-02 후속 순서 — S2 오프라인 코드 구현·CI 통과, S3/S4 미착수

- **GLOBAL-02-S2 / 국제 사건 근거 — 다음 단일 구현 작업 (§7.7):** 1차 공식 원천은 UN 안전보장이사회 제재 명단 변경 목록으로 제한해 출처 ID·변경 유형·공식 통지번호·관측일/원문 게시시각 분리·권한 미승인 차단을 검사한다. S2는 제재/외교 사건의 **증거 계약**으로, 전쟁 발생 인과·국내 업종/기업·매매판단을 추정하지 않는다. 기존 `event_evidence/policy.py`, `TemporalEvidence`, 정정·중복 관리, `macro/event_composition.py`를 재사용하며 NAVER_NEWS 원문 저장·AI 전송 금지.
- **GLOBAL-02-S3 / 산업·종목 연결:** S1 환율/유가의 확정된 출처와 S2 사건 입력을 기존 `macro/impact.py`, `macro/sector_route.py`, `api/macro.py`에 read-only 보조 설명으로 연결한다. 정확한 산업·기업 노출도/매출 구조/시점매핑이 증명되지 않으면 `SECTOR_LINK_UNVERIFIED`로 처리. 국제 뉴스 하나로 시장 폭락 원인을 단정하지 않음.
- **GLOBAL-02-S4 / 사용자 제품화 및 결정 여부:** 전·후 시장 비교 및 실제 사용자 설명의 효용을 확인한 뒤에만 기존 Scanner의 **한 곳**에 글로벌 맥락 요약을 추가한다(동일 카드 증식 금지). 출처/관측일/불확실성 구분, 기존 후보 의사결정 불변. 충분한 외표본·PIT·위험 비교·사용자 승인 전까지 `RiskGate`·전략 랭킹·Horizon·Holdings·JEV를 무단 활성화하지 않는다.

**작업 경계:** 지금 구현할 것은 **GLOBAL-02-S1만**. 기존 STRATEGY-01의 4종목·40일 미미한 표본을 재최적화하지 않고, MACRO-01/02, KIS .DJI, 전략 10개, Risk, Exit, JEV, Holdings 및 Production 선택/정책 파일을 그대로 보존한다. 사용자 PC 실제 값은 이 명세 작성 시점에 조회하지 않았으므로 **GLOBAL-02 실데이터 연동/시장 효과를 성공했다고 기록하지 않는다**.

### 7.5 GLOBAL-02-S1 실제 구현 및 CI 결과 (2026-11-03)

**판정: CODE_IMPLEMENTED_CI_PASS / REAL_FRED_FX_OIL_USER_UAT_PENDING / HISTORICAL_PIT_UNVERIFIED / PRODUCTION_POLICY_UNCHANGED.**

- **정규화:** 신규 backend/app/macro/global02_fx_oil.py에서 FRED 시리즈 ID·Daily 빈도·제목·단위·비계절조정 상태 검증. DEXKOUS는 KRW_PER_USD(상승 시 원화 약세), DCOILBRENTEU는 Brent-Europe USD_PER_BARREL(상승 시 유가 증가). '.'·0·음수·NaN·형식 오류·같은 날짜의 충돌 값은 수익률로 만들지 않음. 결측일을 0% 변화로 대체하지 않고, 단순 관측일과 원천 최초 게시/수정 시각을 구분해 DATE_ONLY / HISTORICAL_VINTAGES_NOT_RECONSTRUCTED / source_published_at_utc=null로 보존.
- **CLI:** 신규 tools/data/analyze_global02_fx_oil.py는 --confirm-personal-research 미지정 시 FRED/DB 조회 없이 RIGHTS_UNVERIFIED 반환. --metadata-only는 KRX DB가 없어도 시리즈 의미·단위를 확인하며 **원본 시세값은 조회하지 않는다**. 연구 모드는 기존 FredClient API를 사용하고 Market DB는 SQLite mode=ro + query_only=ON으로만 읽는다. 원시 외국 시세·FRED API 키를 로컬 보고 파일이나 GitHub에 보존하지 않는다.
- **KRX 실데이터:** KOSPI/KOSDAQ의 주식·지수 네 개 status=data 마커 + 실물 종목/지수 row + 일자/종가 유효성을 요구. 비거래 empty 마커와 실제 partial data 결측을 구분하며, 부분 수집일/누락 지수는 DATA_INSUFFICIENT로 차단. 시장 일일 변화는 전일의 *실제 완전 거래일* 종가에서 계산한다.
- **비교 내용:** FRED 미국 관측의 일별 변화와 KRX 시장의 수익률을 *동일 표기 날짜*로 대응시키되 **미국 뉴욕 정오/EIA 자료가 한국 장 마감 시점 이전에 이용 가능했음을 의미하지 않는 사후 비교**로 고정. 해외 변화 상승/하락/불변별 매칭 수, KOSPI/KOSDAQ 평균 일별 수익률, 공통자료 수/결측/출처·단위/관측일 범위/수집시각만 stdout JSON으로 표시. 매칭 5건 미만은 DATA_INSUFFICIENT. 샘플 원문·가격 값, 인증정보를 출력하지 않는다.
- **불변 정책:** historical_decision_eligible=false, independent_pit_verified_pairs=0, production_decision_approved=false, ai_transfer_approved=false, risk_gate_input_approved=false. 지금은 단순 연관 관측이지 전쟁·유가·환율 인과관계·매수/매도 확률이 아님. FRED 원천 제공자 권리와 개인 비상업 이용 조건을 구분하며 **공개 서비스/AI 전송/원천 재배포/장기보존은 별도 승인 전 금지**. 기존 DGS10·DJI·Scanner·10전략·Risk/Exit·Holdings·JEV 코드는 변경하지 않음.
- **테스트:** backend/tests/test_global02_fx_oil_readonly.py에서 메타데이터 ID/단위/빈도 오인, 결측·중복충돌/무효값, opt-in 없을 때 API 차단, KRX empty·partial 및 실제 row 검증, read-only DB와 비노출, 미국/한국 시장 일정 불일치, 401/403/429/5xx 오류, PIT 미검증을 검증. 기존 OpenDART 테스트의 '미래' 고정일 2026-11-03이 실제 현재 날짜가 되어 실패한 회귀는 테스트 입력만 동적인 미래 날짜로 변경; 프로덕션 OpenDART 코드 수정 없음.
- **GitHub Actions:** 코드 최종 HEAD f9d6b795, [CI #41552181305](https://github.com/SkyBluekor/StockScope/actions/runs/41552181305) **4/4 PASS**. Backend Python 3.11과 3.14 각각 **2,798 passed / 2 skipped**, Frontend Node22 **PASS**, Windows Fresh Clone **PASS**. 사용자 PC의 실 FRED FX/Brent 응답과 국내시장 매칭 결과는 **아직 검증하지 않았음**.

**다음 사용자 PC 1회 UAT (사용하는 FRED 계정과 원천 자료가 개인 비상업 로컬 연구에 허용되는 경우에만):**

~~~powershell
cd C:\Projects\StockScope
git pull --ff-only

$py = ".\.venv\Scripts\python.exe"
$tool = ".\tools\data\analyze_global02_fx_oil.py"
$range = @("--start", "2026-09-01", "--end", "2026-10-30")

& $py $tool @range --metadata-only --confirm-personal-research

if ($LASTEXITCODE -eq 0) {
    & $py $tool @range --confirm-personal-research
}
~~~

- 메타데이터 확인 시 METADATA_VERIFIED이면 공식 ID·단위 의미 검증 성공. 실제 연구는 RETROSPECTIVE_DESCRIPTIVE_ONLY, DATA_INSUFFICIENT, SOURCE_UNAVAILABLE, SEMANTICS_UNVERIFIED를 구분한다. 어느 출력도 PIT·상관의 인과/예측력 또는 매매 신호를 승인하지 않음.
- FRED_API_KEY가 기존 MACRO-01에서 이미 설정되어 있다면 추가 키 발급 불필요. 키/.env/원문 응답·원천 시세를 GitHub나 채팅에 붙이지 않는다. 사용자 PC의 실제 JSON(집계 요약만)을 확인해 **이 실행계획서에 한 번만 기록**하고 S1 완료·차단 판정을 내린다.
- 추후 S2 국제 사건 근거는 이 실자료 UAT와 권한 검토가 끝난 다음 착수한다. 이번 범위에 새로운 Scanner 카드, 리스크 점수, 뉴스 자동 인과, 가중치 수정, JEV 실행·학습, 추가 KRX 자동 수집은 포함되지 않는다.

### 7.6 GLOBAL-02-S1 Windows 실제 FRED·KRX 실자료 결과 (2026-11-03)

**판정: `PERSONAL_LOCAL_FRED_KRX_RESEARCH_EXECUTED` / `RETROSPECTIVE_DESCRIPTIVE_ONLY` / `HISTORICAL_PIT_VERIFIED_PAIRS=0` / `PRODUCTION_POLICY_CHANGE=0` / `PUBLIC_DATA_RIGHTS_UNVERIFIED`.**

**근거:** 사용자가 제출한 Windows PowerShell 실실행 로그. `git pull --ff-only`로 `0f03923`까지 적용 후 `tools/data/analyze_global02_fx_oil.py --start 2026-09-01 --end 2026-10-30 --metadata-only --confirm-personal-research`가 **`METADATA_VERIFIED`**였으며, 이어 실제 연구 실행은 **`RETROSPECTIVE_DESCRIPTIVE_ONLY` / `SOURCE_PUBLISHED_TIME_AND_INDEPENDENT_PIT_UNVERIFIED`**. 조회시각 `2026-11-03T00:47:17.354150+00:00`.

| 항목 | Windows 실자료 확인값 |
|---|---|
| KRX | `READY`, 공통 거래일 40개, 수익률 산출 40개, `empty` 4개 별도 제외, `partial` 0개, 무효 실물 행 0개 |
| KRX 분석기간 | 2026-09-01 ~ 2026-10-30, KOSPI·KOSDAQ |
| FRED `DEXKOUS` | `KRW_PER_USD`, 상승=원화 약세, 유효 관측 50개(2026-08-20~10-30), missing 2, invalid/duplicate 0, 마지막 관측과 조회 4일 차이 |
| FRED `DCOILBRENTEU` | Brent-Europe `USD_PER_BARREL`, 유효 관측 48개(2026-08-20~10-27), missing 1, invalid/duplicate 0, 마지막 관측과 조회 7일 차이 |
| FX ↔ KRX | 같은 날짜의 사후 매칭 **38개**, KRX 동명 날짜 없음 12개, PIT 검증 0개 |
| Brent ↔ KRX | 같은 날짜의 사후 매칭 **37개**, KRX 동명 날짜 없음 11개, PIT 검증 0개 |
| 실행기 반환 안전성 | `network_requests_to_krx=0`, `db_writes=0`, `file_writes=0`, 원본 시세 값 비출력·비저장, `ai_transfer_approved=false`, `risk_gate_input_approved=false` |

**사후 관찰된 시장 수익률:** 미국 지표의 관측 **날짜 문자열**과 국내 지수의 거래 날짜를 대응했을 뿐, 미국 지표가 한국 장 마감 전에 이용 가능했던 정보임을 입증하지 않는다.

| 지표 | 사후 분류 | 매칭일 | KOSPI 평균 일수익률 | KOSDAQ 평균 일수익률 |
|---|---|---:|---:|---:|
| `DEXKOUS` | 상승, 원화 약세 | 17 | -0.465% | -0.301% |
| `DEXKOUS` | 하락, 원화 강세 | 21 | -0.424% | -0.187% |
| `DCOILBRENTEU` | 상승 | 20 | -0.380% | -0.346% |
| `DCOILBRENTEU` | 하락 | 17 | -0.598% | -0.200% |

**해석 및 한계:** 상승·하락 어느 구간이든 이 표본에서 국내 두 시장의 평균은 모두 음수였다. 이는 FX·원유의 인과효과/예측력을 증명하지 않는다. 제3요인·계절성·시장 국면·표본 선택·독립 외표본/유의성은 평가되지 않았다. Brent 최신 관측일은 10월 27일로 국내 최종일 10월 30일을 임의로 채우지 않았다. `source_published_at_utc=null`, `HISTORICAL_VINTAGES_NOT_RECONSTRUCTED`, `independent_pit_verified_pairs=0`. 제공자 원천 이용권의 외부 배포/보관·AI 사용 권한은 별도 증빙이 없다.

**S1 종료:** 개인 로컬 데이터 연결·메타데이터 검증·KRX 40거래일 사후 매칭 **실행 목표 완료**. 다시 동일 기간 API를 반복 조회하거나 사후 표본에서 최적 매매 규칙을 만들지 않는다. 사용자 PC 보고서의 `db_writes=0` 등은 실행기가 반환한 진단 필드이며, 운영 환경의 독립 파일 해시/네트워크 패킷 감사까지 수행한 결과는 아니다. 기존 Scanner/10전략/Risk/Exit/Horizon/Holdings/JEV 및 외부 공개 상태 불변.

**다음 작업:** `GLOBAL-02-S2` 국제 정책·지정학적 사건의 공식 ID, 발표 UTC, 정정 이력, 나라/영향 범위, 제공자 권리 검증. 기존 `event_evidence/policy.py`와 `macro/event_composition.py` 재사용. NAVER 뉴스 원문 임의 저장/AI 변환/예측 이용 금지, 사건 하나가 하락의 원인이라고 단정 금지. **S2 구현은 아직 시작하지 않았다.**

### 7.7 다음 실행 명세 — GLOBAL-02-S2: 공식 국제 제재 변경 사건의 근거·시점·권리 검증

**작업 상태: `OFFLINE_CODE_IMPLEMENTED / CI_4_OF_4_PASS / RIGHTS_UNVERIFIED / HISTORICAL_PIT_UNVERIFIED` (2026-11-03).**

**이번 한 단계의 목표:** 글로벌 정책/제재/분쟁 사건을 막연한 뉴스 감성 점수로 취급하지 않기 위해, **국제 공식기관이 실제 발표한 사건 1종을 출처/ID/변경 유형/시점/정정/권한이 있는 작은 참조 레코드로 구분할 수 있는가**를 실데이터 1회로 검증한다. 기존 EVENT P6 인프라를 재사용하고 이번 S2에서는 신규 사업체 매핑·지수/종목 가격 비교·전쟁 확률·AI/JEV·Scanner 화면 **모두 불허**. 글로벌 사건 위험도 임의 숫자와 확정 인과관계는 만들지 않는다.

#### A. 이번에 실제 검사할 공식 원천은 단 1개

- **1차 지정 원천: UN 안전보장이사회(UNSC) 통합 제재 명단 'List of updates to the UNSC Consolidated List'**, https://main.un.org/securitycouncil/en/content/list-updates-unsc-consolidated-list . 이 목록에는 변경 날짜, 제재위원회/제재체제, 영구 참조번호(Permanent Reference Number), 변경 유형(Listing/Delisting/Amendment), 해당 항목수, 공식 통지/보도자료 번호(예: SC/…)가 있다. 통합 명단 원본 https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list 와 서로 다른 문서임을 유지한다. **현재 웹에서 이런 필드의 존재를 확인했지만, 실제 응답 파서/정확한 UTC 게시시각/데이터 이용 허가는 구현 및 사용자 UAT 전 미검증**.
- **S2가 포괄하는 사건:** 해당 제재체제의 **제재 대상 등재/삭제/정보 변경이라는 행정 사실**. 이를 전쟁 개시, 호르무즈 해협 봉쇄, 석유 공급 차질, 미국 연방정부 경제정책, 국내 기업의 해외 매출 충격으로 자동 변환하지 않는다. 전쟁/분쟁 현황과 정책 변동의 더 넓은 원천은 **S2 후속 별도 승인 작업**에서 각 공식 발표/시각 계약을 추가해야 한다. 같은 단계에서 검증 없이 OFAC·뉴스·소셜미디어까지 일괄 수집하지 않는다.
- **교차 참고 후보만:** OFAC 공식 Sanctions List Service(https://ofac.treasury.gov/sanctions-list-service)는 제재 명단 및 변경(delta) 파일을 제공하는 별도 관할의 공식 소스다. 이번 S2에서는 링크/후속 후보로만 기록하고 OFAC 데이터 다운로드, 통합 dedup, 미국 제재의 UN 제재 대체 취급은 하지 않는다.

#### B. 기존 코드 재사용과 신규 최소 구현 위치

| 기존 코드 / 실제 상태 | S2 적용 경계 |
|---|---|
| `backend/app/event_evidence/policy.py`의 `EventEvidenceSourcePolicy`/`EvidenceCapability` 및 `policy_for_event_source` | 현재 승인된 소스는 `NAVER_NEWS`, `OPENDART_DISCLOSURE`뿐. **UNSC는 아직 미승인 소스**이며 정책 목록에 무심코 추가하거나 DISPLAY/NORMALIZE/RETENTION/AI/HISTORICAL/PREDICTION=true로 열지 않는다. 먼저 `UNSC_SANCTIONS_UPDATE_CANDIDATE`를 별도 진단용으로 fail-closed. 원천 조건이 공식적으로 확인돼 별도 정책 결정이 있을 때만 등록 가능 |
| `backend/app/event_evidence/time.py:TemporalEvidence`, `EvidenceTimeQuality`, `conservative_available_at` | `event_date`(공식 변경 날짜), `source_published_at`(공식 UTC가 확인된 경우에만), `first_seen_at`, `fetched_at`, `available_at`, `corrected_at`을 분리. 웹페이지에 날짜만 있으면 `DATE_ONLY`이고 **00:00 UTC/KST 임의 생성 금지**. earliest historical PIT를 추정할 수 없어 `historical_evaluation_eligible=false` |
| `backend/app/event_evidence/models.py:EventEvidenceSourceRef`, `EventRevisionIdentity`, `EventEvidenceState` | 발표·참조 ID 확인 뒤 표준 계약으로 매핑 가능한지 **메모리/fixture에서만 검증**. UN 소스 policy 승인 전 `EventEvidenceStore`나 Simulation DB에 기록 금지. 같은 사건의 amended/delisted/withdrawn 이력을 영구 ID의 다른 revision으로 구분하되 임의 version 발급 금지 |
| `backend/app/event_evidence/resolution.py`/`quality.py`/`asof.py`, `backend/app/macro/event_composition.py` | 기존 중복/품질/컷오프/정정 메커니즘이 있다는 사실을 확인. **S2 공식 데이터는 권한/시점 적격성이 없으므로 생산 경로 또는 과거 백테스트에 주입하지 않는다**. 향후 기존 읽기 전용 제품 경로로 재사용할 계약만 맞춤 |
| `backend/app/news/policy.py` | NAVER_NEWS는 표시/표시용 정규화만 허용. 원문 저장·번역/LLM 변환·역사평가·예측 입력 불승인. S2에서 해당 정책을 우회하지 않음 |

#### C. Codex 다음 실행 작업 — 이 순서로 구현

1. **공식 1회 preflight 및 권리 판정:** UN 공식 URL의 제공 상태·구조·공식 통지 링크·영구 참조번호가 실제 접근 가능한지 확인하고, 원천의 자동 조회·인용·메타데이터 추출·비상업 이용·재배포·파생 저장 조건을 공식 문서로 확인한다. 검증하지 못한 capability는 **기본 false**. 승인 증거(정확한 공식 링크, 확인 날짜, 허용 목적과 제한)가 없는 경우 `RIGHTS_UNVERIFIED`로 안전 종료. 공개 PDF 전체 본문/공식 HTML 전문/개인정보를 LLM 또는 GitHub에 전달하지 않음.
2. **원천 계약 1개 구현:** 신규 `backend/app/event_evidence/global02_official_updates.py`(파일명 제안)에 `UNSC_SANCTIONS_UPDATE_CANDIDATE`용 strict normalizer + rights/time gate를 둔다. 파서에 필요한 필드: `source_kind`, `official_notice_id`, `sanctions_regime_id`, `permanent_reference_numbers[]`, `change_type` (`LISTING/DELISTING/AMENDMENT`), `change_date` (YYYY-MM-DD), `official_reference_url`, `observed_at_utc`, `source_published_at_utc|null`, `time_quality`, `rights_capabilities`, `validation_status`. 원본 기사/제재대상 개인정보/전체 명단/제재 리스트 원문·URL 쿼리 자격정보를 출력하지 않는다. 누락/충돌/링크가 공식 도메인이 아닌 경우 `IDENTITY_UNVERIFIED`/`SOURCE_UNAVAILABLE`/`SEMANTICS_UNVERIFIED`로 중단.
3. **공식 식별자·정정 및 의미 충돌 방지:** 단일 공지에 여러 영구 참조번호가 포함될 수 있으므로 (공식 통지번호+제재체제+영구 참조번호+변경유형)을 **개별 변경 이벤트 식별자 후보**로 사용한다. 단순 해당 날짜, 헤드라인, 유사한 인명/국가 문자열만으로 dedup하지 않는다. 같은 영구 참조번호가 다른 공지에서 `AMENDMENT`/`DELISTING`되면 같은 엔터티의 **서로 다른 변경 사건**이다. 공식 게시일 미상/정정 링크 불명 시 수정 직전 상태로 과거 스냅샷을 재작성하지 않는다. 발표·명단의 수정 사실과 처음 관측했다는 사실은 별개.
4. **시각/권리 정책 fail-closed:** 원천의 `change_date`는 제재 변경일이지 공식 발표 UTC가 아니다. `source_published_at_utc`가 없는 경우 `DATE_ONLY`를 유지하고 `available_at`은 **StockScope가 실제로 해당 버전을 처음 관측·검증한 시각보다 이르게 만들지 않는다**. `TemporalEvidence`의 `historical_evaluation_eligible` 속성에 관계없이 **capability 승인까지 별개 확인**한다. `publication_rights_approved=false`, `retention_approved=false`, `ai_transfer_approved=false`, `historical_decision_eligible=false`, `production_decision_approved=false`를 출력하며 원문/파생 자동 DB 저장, 소스 권리 자동 상속, 제재명단 존재=확정 한국기업 영향 판단을 차단한다.
5. **사용자용 단일 연구 CLI:** `tools/data/inspect_global02_official_events.py`(파일명 제안). 기본 동작은 offline fixture/도움말; live mode는 **명시적 개인 로컬 접근 확인 + 제공자 약관 사전 확인**시에만 공식 원천 *좁은 목록 1회* 요청. 최대 건수/타임아웃/허용 호스트/리다이렉트·크기 제한을 둔다. 실행 후 stdout에 `source_status`, `rights_status`, `identity_validated_count`, `date_only_count`, `notice_id_count`, `change_type_counts`, `excluded_reasons`, `duplicate_conflicts`, `correction_linkage_verified_count`, `historical_pit_verified_count`, `writes=0`, `ai_calls=0`, `production_inputs=0`의 **집계만 출력**. 다운로드 본문/개별 민감정보/원본 파일 저장하지 않고 글로벌 사건 DB·Market/Simulation DB·JEV·Scanner에 연결하지 않는다.
6. **테스트/CI와 실증 완료:** 가짜 UN 변경 목록 fixture에서 `LISTING/DELISTING/AMENDMENT`, 한 공지 안 다수 참조번호, 동일 공지 중복, 공식 통지/영구 ID 부재, 다른 도메인 위장·redirect·수집량/응답 크기 초과, 원천 `DATE_ONLY`/나중에 관측된 정정, 권리 비승인, 403/429/5xx/연결 실패, 무신뢰 HTML 내용, 시간대 해석/미래 cutoff, 소스 변경, NAVER 미승인 capability 및 외부 AI 호출/DB 쓰기 0을 검증한다. 기존 `backend/tests/test_event_evidence_contract_vnp6s1.py`, `test_macro_event_composition_next6d_s1.py` 및 Python 3.11/3.14·Frontend·Windows Fresh Clone 회귀 유지. 사용자 PC 라이브 확인은 조건 충족 시 공식 목록 1회만 실시하고 결과의 **메타데이터 집계/차단 사유만** 이 단일 계획서 §7.8에 기록한다. 권한 또는 공식 시각 부재 때문에 PIT 검증 실패는 정상적인 안전 판정으로 인정하며 무작정 다른 사이트를 재조회하지 않는다.

#### D. 수용/차단 판정

- `SOURCE_CONTRACT_VERIFIED_REFERENCE_ONLY`: 공식 도메인/공지·체제·영구 ID/변경 유형·날짜가 충돌 없이 해석되고, 실조회 이용권 범위가 확인됐으며 권한 제한과 날짜 한계가 분리돼 집계 결과로 재현된다. **단, 이벤트가 전략 판단에 유용하거나 권한이 공개 서비스까지 확대되었다는 뜻은 아님**.
- `RIGHTS_UNVERIFIED`: 해당 데이터의 자동 조회·로컬 이용·인용/파생 처리 조건이 확인되지 않거나 허용 범위가 모호하면 원천 값을 받거나 저장하는 동작을 수행하지 않는다. 공식 링크·부족한 권리 근거를 보고하고 종료.
- `SOURCE_UNAVAILABLE` / `IDENTITY_UNVERIFIED` / `DATE_ONLY_LIMITED` / `CORRECTION_LINK_UNVERIFIED`: 목록 구조/공지·참조번호/UTC 게시시각/정정 연결의 결함을 개별 이유로 기록한다. 출처가 날자만 제공하는 경우는 **참조용 연구까지 가능할 수 있어도 역사적 거래·인과 판단은 계속 차단**한다.
- **절대 변경 금지:** 기존 10전략 순위/점수, Exit/Risk/PANIC/Horizon, 보유 대응, 뉴스/네이버 권한, UN/OFAC의 개인·단체 제재 명단을 로컬 장기 저장하는 기능, JEV AI 요청, Scanner 국제 사건 점수/원인 문구, 자동 거래/외부 공개. **사용자 동의 없이 정부 제재·국제분쟁 관련 사실을 특정 한국 종목의 악재나 주가 폭락 원인으로 표시하지 않는다.**

**GLOBAL-02-S2 후속 연결:** 이 단계에서 제재 변경에 대한 **공식 사건 존재**가 확인돼도, 실제 전쟁·공급망·무역·산업 노출과 한국 기업 피해를 규명하려면 별도 공식 원천·산업 자료가 필요하다. 후속 GLOBAL-02-S3은 S2에서 **검증된 사건 종류만** 대상으로 `sector_route.py`의 업체/업종 맵핑을 별도 실증하고, 실패하면 `SECTOR_LINK_UNVERIFIED`로 남긴다. 우선 S2만 구현하고 문서·진단 UI를 계속 증식시키지 않는다.


### 7.8 GLOBAL-02-S2 오프라인 구현 및 차단 판정 (2026-11-03)

**상태: `OFFLINE_CODE_IMPLEMENTED / CI_4_OF_4_PASS / RIGHTS_UNVERIFIED / HISTORICAL_PIT_UNVERIFIED / NO_LIVE_FETCH`.** S2의 공식 원천 구조는 UN 안전보장이사회 변경 목록에서 확인했지만 자동 추출·파생 정규화 권리까지 확인된 것은 아니다.

- **공식 근거:** UN 공식 변경 목록 `https://main.un.org/securitycouncil/en/content/list-updates-unsc-consolidated-list`에는 변경 날짜, 제재체제, 영구 참조번호, Listing/Delisting/Amendment, 변경 수, SC 통지 링크가 있다. UN 공식 약관 `https://www.un.org/en/about-us/terms-of-use`는 개인·비상업적 방문/복사를 허용하지만 원문 재배포와 파생물 제작을 제한한다. StockScope의 자동 수집·파생 정규화·상업/공개 서비스·AI 입력 허가는 **미확인**.
- **추가 코드:** `backend/app/event_evidence/global02_official_updates.py`는 정책 미승인 `UNSC_SANCTIONS_UPDATE_CANDIDATE`에 대한 별도 deny-all 후보와 strict notice/regime/permanent ref/change type/date/link 정규화, 날짜만 제공된 자료의 `TemporalEvidence.DATE_ONLY`, 최초 검증시각 이전 가용성 역행 금지, 중복/충돌, 입력 크기/건수 제한 및 메모리 내 집계를 구현한다. `policy_for_event_source` 운영 승인 목록은 수정하지 않음.
- **CLI:** `tools/data/inspect_global02_official_events.py`. 기본은 네트워크 없는 안내, `--offline-fixture`는 **실제 UN 사건이 아닌 합성 공지** 3개/고유 변경 4개에 대한 집계만 출력한다. `--live --confirm-personal-research`조차 source rights 확보 전에는 `RIGHTS_UNVERIFIED`와 `network_requests=0`을 반환한다. 원문·개인/단체 제재명단·개별 영구 ID/공지번호를 CLI 출력이나 DB에 쓰지 않는다.
- **테스트:** `backend/tests/test_global02_official_updates_s2.py` 신규. 권리 fail-closed, 실제 UTC 미증명, 날짜만 제공된 사건의 PIT 차단, 참조번호 다수/변경 유형/공지별 수정 사건 구별, 중복/충돌, 공식 도메인 위장/무단 링크, HTML 용량 제한/합성 테이블, opt-in 이후에도 네트워크 0을 검증한다. GitHub Actions [CI #41559484181](https://github.com/SkyBluekor/StockScope/actions/runs/41559484181) **4/4 PASS** (Backend Python 3.11 **2,829 passed / 2 skipped**, Python 3.14 PASS, Frontend Node22 PASS, Windows Fresh Clone PASS). 테스트 초기 1건은 예외 메시지와 내부 오류 코드를 혼동한 테스트 단언 문제였고, 오류 코드 속성을 직접 검사하도록 수정한 커밋 `e8480876`에서 전체 통과.
- **사용자 Windows 로컬 UAT (2026-11-03):** `C:\\Projects\\StockScope`에서 `.\\.venv\\Scripts\\python.exe tools\\data\\inspect_global02_official_events.py --offline-fixture` 실행 결과 사용자 제공 stdout JSON 확인. `source_status=OFFLINE_FIXTURE_VALIDATED_ONLY`, `data_origin=SYNTHETIC_TEST_ROWS_NOT_REAL_UNSC_EVENTS`, `notice_id_count=3`, `identity_validated_count=4`, `change_type_counts={AMENDMENT:2, DELISTING:1, LISTING:1}`, `date_only_count=4`, `excluded_reasons={}`, `duplicate_conflicts=0`, `network_requests=0`, `writes=0`, `ai_calls=0`, `production_inputs=0`. `rights_status=RIGHTS_UNVERIFIED`, `historical_pit_verified_count=0`, `ai_transfer_approved=false`, `production_decision_approved=false`. **결론: 로컬 오프라인 합성 데이터 검증 PASS; 공식 UN 실조회·권리·과거시점 정보 이용 가능성 및 투자판단 유효성은 여전히 미검증.** 로그가 보여주는 것은 CLI의 집계 출력이며 독립 네트워크 패킷 감사를 수행한 것은 아님.
- **수용 경계:** 오프라인 계약이 검증되어도 실제 공식 UN HTML의 자동 추출 권리, UTC 최초 발행 증거, 변경 공지 간 정정 링크는 검증되지 않았다. 따라서 `SOURCE_CONTRACT_VERIFIED_REFERENCE_ONLY`나 실전 가용성으로 승격하지 않는다. `RIGHTS_UNVERIFIED`, `DATE_ONLY_LIMITED`, `CORRECTION_LINK_UNVERIFIED`로 유지하고, 독립적으로 확인 가능한 권리 승인 없이 실네트워크 재시도·다른 공식 기관 우회 조회·DB/JEV/Scanner/전략 반영 금지.
- **다음 완료 조건:** 오프라인 합성 테스트·CI 4/4는 완료. **실자료 UAT/운영 연결을 위해서는 UN의 자동 추출 및 파생 메타데이터 사용 허용을 뒷받침할 별도 공식 근거 또는 권리자의 명시적 허가가 필요**하다. 그전에는 GLOBAL-02-S3/S4로 확대하지 않는다.


## 8. 다음 단일 실행 명세 — JEV-A-WINDOWS-UAT (2026-11-03)

**상태: SPEC_READY / A_UI_ALREADY_IMPLEMENTED / CI_4_OF_4_PASS / USER_WINDOWS_ACCEPTANCE_PENDING / NO_PAID_CALLS.**

### 8.1 선택 이유 / 기존 자산

- GLOBAL-02-S2는 2026-11-03 Windows 오프라인 합성 데이터 3공지/4변경 검증 완료. 공식 UN 자동 추출·파생 데이터 이용 권한/게시 UTC가 미확인되어 실자료 조회·S3/S4 진행은 보류한다. 법적 권한 확보 없이 UN·뉴스·DART·KRX 자료를 JEV 전송하지 않는다.
- 2026-10-30 JEV 단일 실행계획 A의 UI 간결화는 이미 frontend/src/components/ScannerAiReview.tsx, scannerUX.css 및 frontend/e2e/p003-scanner-recheck.spec.mjs에 구현됐다. 자세한 Mock/P5/P6 디버그는 사용자가 개발자 진단을 펼칠 때만 표시한다. 기구현 코드를 다시 만드는 작업이 아니다.
- 통합 브랜치 CI https://github.com/SkyBluekor/StockScope/actions/runs/41559484181 에서 Python 3.11(2,829 PASS/2 SKIP), Python 3.14, Node22, Windows Fresh Clone 4/4 통과. 사용자 Windows에서 **JEV A 간결 UI의 실제 화면 인수는 아직 없음**. 글로벌 S2 Windows CLI 검증을 JEV-A UAT로 오인 금지.
- 이번 작업은 이전 문서 docs/JEV_SINGLE_EXECUTION_PLAN.md의 **A → B → C** 순서를 따른다. A 수용 전 B 유료 실모델 검토를 미리 활성화하지 않는다.

### 8.2 Codex/Windows 작업 (이번에는 A만)

1. C:\Projects\StockScope 에서 git status --short 와 git branch --show-current 로 현재 상태를 확인하고, 기존 수정파일 보존 후 git pull --ff-only. 8000/5173 포트가 사용 중이면 중복 서버를 띄우지 않는다. 필요 시 .\run-dev.ps1 로 기존 개발 서버 시작.
2. 브라우저 http://127.0.0.1:5173 에서 Scanner의 **기존 저장 후보**를 선택. 새 KRX 수집·새 캡처 생성·실거래·유료 모델 호출은 하지 않는다. 일반 사용자 AI 검토 영역에는 선택 종목명/코드, 기존 Scanner 판단, 저장된 실제 JEV 검토 상태, 실행 불가 사유와 비활성 버튼만 간결하게 표시되어야 한다.
3. 저장된 다른 후보 하나로 전환하여 종목명/코드/검토 상태가 섞이지 않는지 확인. 좁은 창에서도 주요 내용이 겹치거나 누락되지 않아야 한다. 기본 영역에는 Mock/V4/V5/SourceRef/P6 기술 라벨이 펼쳐지지 않아야 한다. 아직 실제 JEV 결과가 없으면 **실제 검토 미실행**으로 표시하고 결과를 만들어 내지 않는다.
4. 개발자 진단 및 공시 조회를 직접 펼쳤을 때만 상세 진단이 보이는지 확인. 평소 기본 화면에서 불필요한 P5/P6 조회·유료 모델 요청이 추가로 발생하지 않아야 한다. Scanner/Risk/Holdings 결과는 변경되지 않는다.
5. 사용자 Windows 스크린샷 1~2장 또는 화면 결과로 인수 판정. 정상이라면 **코드 변경 없이** 상태만 이 문서에 기록한다. 문제 발견 시 ScannerAiReview.tsx와 직접 관련 CSS/E2E의 결함만 최소 수정하고 CI+같은 Windows 화면을 재검증한다. 새 Mock 화면/진단기/권한 토글/새 데이터 수집 경로는 추가하지 않는다.
6. 사용자 증거가 없으면 A를 완료 처리하지 않는다. CI PASS만으로 실사용 UAT를 대체하지 않는다.

### 8.3 수용 조건과 다음 단계

| 항목 | 수용 기준 |
|---|---|
| 일반 UI | 실제 선택 종목·기존 Scanner 판단·JEV 상태·불가 사유가 즉시 구분 |
| 기술 내용 | Mock/P6 디버그는 기본 접힘, 개발자 진단 수동 진입 시만 보임 |
| 종목 전환 | 저장 후보 2개 사이 전환해도 이전 종목 결과가 섞이지 않음 |
| 동작 보존 | 실행 버튼은 조건 충족 전 비활성, 외부 JEV 호출 0회, 기존 Scanner/Risk/Holdings 불변 |
| 품질 | 기존 CI 4/4 PASS 유지, 실제 사용자 Windows 화면 확인 |

**진행표:** GLOBAL-02-S2 offline = PASS / live = RIGHTS_UNVERIFIED; JEV-A = WINDOWS_VISUAL_PARTIAL_PASS / CANDIDATE_SWITCH_NOT_VERIFIED; JEV-B = NOT_STARTED; JEV-C = NOT_STARTED.

### 8.4 사용자 Windows 실제 화면 1차 확인 (2026-11-04)

**판정: `WINDOWS_VISUAL_PARTIAL_PASS / FULL_UAT_PENDING`.** 사용자 제출 `127.0.0.1_5173_scanner (2).png` 전체 화면 캡처에서 실제 저장 후보 **동국제약(086450, KOSDAQ)**의 AI 검토 탭이 표시됨. 일반 사용자 요약에 종목명/코드, Scanner 판단, `현재 서버에서 JEV 사용 불가` 상태, `JEV 검토 실행 (사용 불가)` 회색 비활성 버튼, 간결한 사유 문구를 확인. 세부 P5/P6 진단은 `개발자 진단 및 공시 조회`가 **열린 상태**로 촬영됨. 코드 `ScannerAiReview.tsx`는 기본 `developerOpen=false`와 사용자가 상세를 열 때만 진단 컴포넌트 mount를 구현하고 있으며, E2E 테스트에서도 기본 진단 GET 0/유료 POST 0/390px 레이아웃이 확인되었음.

- **확인된 것:** 사용자의 실제 Windows 실행 화면에서 간결 요약/비활성 버튼/기존 판단 구분, 진단 분리 표시. 합성 CI를 실제 TypeSafe 응답이나 Windows 네트워크 감사로 오인하지 않음.
- **미확인:** 실제 Windows에서 두 번째 저장 후보로 전환했을 때 종목/검토 상태가 섞이지 않는지, 해당 사용자 환경에서 기본 접힘 상태의 스크린샷 및 외부 JEV POST 0 별도 관찰. 스크린샷 단일 장만으로 동작/네트워크를 증명하지 않는다. **A 전체 DONE 선언 금지.**
- **남은 간단 인수:** 같은 실행에서 개발자 진단을 닫고 다른 저장 후보 1개를 선택해 기본 AI 검토 요약을 확인. 문제가 없으면 A=`WINDOWS_UAT_PASS`로 기록하고 B 구현 명세로 이동. 문제가 있으면 화면/현상에 직접 관련된 UI 코드만 수정, 별도 GLOBAL-02 fixture 재실행/권한 미확인 데이터 수집 금지.
- **별도 디자인 관찰:** 기본 결과 영역 외의 일부 Scanner 경고와 펼친 개발자 진단에는 LEGACY/P5/P6/HOLD 등 기술어가 남아 있다. 현 A 검증은 사용자 기본 요약만 대상으로 하고, 요청 없는 전체 Scanner UI 재설계나 진단 삭제는 하지 않는다.

**A 통과 이후에만 다음 B를 진행:** 실제 저장된 한 종목과 그 캡처 신원을 읽기 전용으로 연결하고, **사용자 직접 작성·전송 권리 보유 입력**만 기존 TypeSafeSystemOneProvider로 1회 수동 검토하는 기능. 해당 유료 요청은 별도 사용자 명시 승인 필수. 원천 권한 불명 시장 수치/공시/뉴스·UN 자료를 문구만 바꿔 외부 전송 금지. 호출·중복 청구·모델 ID·시각·비용·저장 및 재조회가 확인되어야 B 성공이며, 유효한 입력이 부족하면 B 보류. 이번 A 작업에서 B 구현·유료 호출은 수행하지 않는다.

**다음 실행에 필요한 사용자 확인:** 기존 StockScope 프로그램을 실행해 Scanner의 선택 종목 AI 검토 요약 영역 스크린샷을 전달하면 A 인수 판단 가능. GLOBAL-02-S2 offline-fixture 재실행 불필요.


## 9. JEV-B 다음 구현 명세 — 선택한 실제 종목 수동 TypeSafe 검토 (2026-11-04)

**상태: `READONLY_V4_FIT_IMPLEMENTED / CI_4_OF_4_PASS / REAL_MODEL_INTEGRATION_NOT_STARTED / JEV_A_WINDOWS_UAT_PARTIAL_PASS / MANUAL_REAL_MODEL_CALL_NOT_APPROVED`.**

**최종 사용자 목표:** 실제 저장된 종목 1개를 선택해, 출처·이용 권한을 확인한 입력에 대해 기존 TypeSafe JEV가 검토할 수 있는 질문만 1회 수동 실행하고 StockScope의 로컬 판단과 나란히 확인. 실전 수익률/승률/매수 신호를 모델이 증명했다는 식으로 보여주지 않는다.

### 9.1 이 명세가 필요한 실제 코드 상태 (2026-11-04, 현재 사용자 브랜치)

- `backend/app/jev/typesafe_provider.py:TypeSafeSystemOneProvider`는 /v1/systemone HTTP 요청, 응답 타입/모델/질문/usage 검증과 401/422/429/5xx/timeout 처리가 이미 있다. 기존 검증·클라이언트를 사용하며 새 제공자나 무의미한 합성 유료 canary를 만들지 않는다.
- `backend/app/api/jev.py:jev_review_feature_status`는 `DISABLED_VALIDATION_PENDING`/available=false, `POST /simulation/jev/reviews`는 기본 비활성 `JevManualReviewService`를 생성한다. 프론트 `ScannerAiReview.tsx` 실행 버튼은 의도적으로 disabled. **UI 버튼 활성화만으로는 실모델 호출 경로가 존재하지 않는다.**
- `backend/app/jev/review_service.py`는 완전한 저장 캡처/프로토콜, `semantic_source_v2`, `route_typesafe_state_v4`, `RESIDUAL_SEMANTIC_REVIEW`, 명시적 provider 주입을 요구한다. 과거 실종목 ENTRY 후보 7개는 `LOCAL_MATCH`였으므로 해당 후보를 억지로 잔여 의미 검토 대상으로 바꾸지 않는다.
- `backend/app/jev/typesafe_questions_v4.py`의 `strategy_relation_conflict`는 **작성된 전략 의미 관계의 충돌**을 묻는 계약이다. 사용자가 제공한 투자 관련 자유 텍스트를 이 질문에 무조건 끼워 넣어 '시장 적합성/수익률'을 판단했다는 식으로 표현하지 않는다.
- 현재 JEV-A는 사용자 Windows 실제 종목 요약 화면을 확인했으나 **두 번째 종목 전환과 기본 접힘 상태** 인수가 남아 있다. B의 유료 호출·사용자 활성화보다 먼저 A의 잔여 인수 항목을 1회 완료한다. A 확인을 이유로 추가 P5/P6 진단기를 만들지 않는다.

### 9.2 구현 우선순위 (순서 고정, 기존 자산 우선)

1. **A 잔여 인수는 B 진입 게이트로 한 번만 처리:** 기존 저장 후보 2개 전환, 일반 JEV 요약에 다른 종목/검토 상태 잔존 여부, 개발자 진단 기본 닫힘·수동 열림 확인. Windows 실행 환경에서 오작동 시 해당 UI 결함만 수정한다. 확인되기 전 `A_WINDOWS_UAT_PENDING` 유지. 실제 JEV API 유료 요청 0회.
2. **B의 단일 질문과 실입력 호환성 게이트:** 저장된 real ticker/market/canonical capture ID/sample index/snapshot hash를 읽기 전용으로 연결한다. 기존 V4의 질문·projector·policy를 그대로 사용할 수 있는지 검사한다. `LOCAL_MATCH`를 `RESIDUAL_SEMANTIC_REVIEW`로 조작하거나 user text를 거짓 `semantic_source_v2`로 꾸미면 안 된다. **현재 V4는 전략 의미 충돌 질문이므로 주식시장 평가 질문으로 범위를 확대할 수 없다.** 정당한 실제 입력으로 기존 V4 계약과 검토 목적이 부합하지 않으면 `INPUT_CONTRACT_MISMATCH` 또는 기존 의미 있는 `NOT_READY` 상태로 중단하고, 사용자에게 필요한 **질문 계약 변경 선택지 한 가지**를 설명한다. 사용자 승인 없이 새 V5/V6 질문/점수/모델을 만들지 않는다.
3. **전송 내용·권한 검증:** 실제 검토가 적격한 경우에만 사용자가 직접 작성하고 전송할 권리가 있는 **전략 의도/용어 정의/관계 설명** 등 작은 텍스트를 입력으로 허용. 사용자가 직접 작성했다는 사실만으로 검색 기사·KRX 가격·DART 공시·UN 제재 원문 및 그 변형/전사본이 자동 승인되는 것은 아님. 필드별 원천·권한·입력 시점 확인; 허용되지 않은 캡처/뉴스/시세/감시 데이터는 TypeSafe wire body에 절대 포함하지 않는다. 실제 HTTP 전송 전, 화면에서 사용자에게 전송 범위·모델·비용 추정 가능 여부를 알리고 명시적 **해당 요청 1회 승인**을 받는다.
4. **한 종목 수동 요청 경계:** 기존 `TypeSafeSystemOneProvider`, `review_service.py`, `typesafe_service.py`, `typesafe_catalog.py`, `/api/simulation/jev/reviews`, `jevApi.ts`를 재사용하며 새 provider/스캐너 복제 페이지를 만들지 않는다. 현재 비활성 기본값을 전역적으로 풀지 말고, 특정 검증된 단건 요청만 서버 측 신원·권한·실행 승인과 함께 허용하는 좁은 경계를 추가한다. 브라우저 버튼/feature flag만으로 server gate 우회 금지. `review_epoch` 증가나 재로드로 중복 결제를 재허용하지 않는다. 동일 capture+sample+snapshot+user-input digest+question/model/policy에 대해 **원자적 예약·중복 방지** 후 한 번 호출하고 실패 시 자동 재시도/배치 없음. 검토 불충분/승인 없음/타임아웃 시 Scanner 원본은 변하지 않는다.
5. **실제 응답 검증·영속성:** provider의 `model`, question ID, `noul` 답변 타입, `usage` 검증을 유지한다. `noul`은 '해당 질문의 참값 추정'으로, 주가 상승 확률/수익률 예측/원인 설명이 아니다. TypeSafe 응답으로만 결정할 수 있는 `PASS_THROUGH/REVIEW_REQUIRED/ABSTAIN`을 기록. 모델·질문/입력 해시·캡처 신원·검토 시각·호출 결과·cost_usd 또는 `cost_unknown=true`를 저장하고, 재조회해 **그 종목의 그 입력에만** 결과가 나타나도록 한다. 새로운 실시간 결과로 위장하거나 중복된 자연어 이유를 지어내지 않는다.
6. **기존 간결 화면에만 통합:** 기본 AI 검토 요약에 결과 전/진행/완료/보류/오류, 실제 저장 결과의 모델/시각/비용 불명 여부, 읽기 쉬운 차이만 표시. 개발자 영역의 디버그/원본 해시/근거 라벨 보존. 'JEV 검토 실행' 버튼은 특정 1회 요청이 서버 검사에 적격일 때만 활성. 거절 시 필요한 조치 하나와 이유를 보여주고 새로운 HOLD 카드·팝업/거대 상태 목록을 만들지 않는다.
7. **자동 검증 → 실제 Windows 실행은 별도 승인 후 1회:** 기존 구조의 E2E·백엔드 모의 네트워크로 미승인·권한 불명·해시/원본 불일치·중복 클릭·동시 요청·타임아웃·429/5xx·중복 결과 재조회·모델/질문 불일치·보유/Scanner 변경 없음 테스트. Python 3.11/3.14, Frontend, Windows Fresh Clone CI 유지. 실제 TypeSafe 유료 호출은 **사용자가 해당 호출을 명시적으로 승인한 경우에만 Windows에서 1회 수행**하고, 실모델 응답/저장·재조회/입력 범위·호출 수를 확인. 사용자가 허가하지 않은 동안 실제 외부 API 호출 = 0.

### 9.3 파일 변경 예상 범위

| 재사용/수정 후보 | 이번 단계의 역할 |
|---|---|
| `frontend/src/components/ScannerAiReview.tsx`, `frontend/src/services/jevApi.ts` | 사용자 직접 입력이 정말 필요한 경우 최소 입력/1회 승인/결과 표시; 기존 간결 화면 유지 |
| `backend/app/api/jev.py` | 비활성 기본 보존, 승인된 단건 요청을 위한 서버 측 검증 경계 |
| `backend/app/jev/review_service.py`, `typesafe_service.py` | 권한 있는 적격 입력, 원자적 중복 방지, 기존 provider와 저장 서비스 연결 |
| `backend/app/jev/typesafe_provider.py`, `typesafe_catalog.py`, V4 question/state/policy | **기존 구현 우선 재사용**. 질문 계약·정책 변경 금지. 기존 저장 구조로 충족 불가한 경우 코드를 억지로 확장하지 말고 원인 보고 |
| 기존 JEV 백엔드 테스트 및 `frontend/e2e/p003-scanner-recheck.spec.mjs` | 최소 필요 회귀 추가; 새 테스트 프레임워크/진단 UI 없음 |

### 9.4 정확한 완료·중단 판정

- **B 구현 완료 기준:** A 사용자 Windows 인수 완료, 서버에서 승인 전 차단·권한 검증·신원/입력 해시·중복 안전성 통과, 실제 수동 1회 실행 준비가 됨. 코딩/CI 성공만으로 실모델 사용 성공이라고 하지 않는다.
- **B 실사용 완료 기준:** 실제 **비합성 종목 + 허용 입력 + 별도 승인된 실제 TypeSafe 유료 1회** → 모델 ID/질문 응답 타입 검증 → 저장·재조회 → 동일 입력 중복 과금 0 → 기존 Scanner/Strategy/Risk/Horizon/Holdings 결과 불변 → 사용자 Windows 화면 확인. 응답이 투자 성과 향상/수익 예측 능력을 입증한 것은 아니다.
- **정당한 V4 입력이 없거나 질문이 제품 목표에 부적합한 경우:** `INPUT_CONTRACT_MISMATCH`, `B_BLOCKED_NEEDS_QUESTION_SCOPE_DECISION`으로 명확히 중단. UI 토글 변경·`LOCAL_MATCH` 우회·추가 Mock/외부 데이터 수집·신규 P6/GLOBAL 추론으로 억지 성공하지 않는다. 사용자에게 'V4 의미 충돌 검토로 제한'과 '질문 계약을 별도 승인하여 실제 투자 검토로 재설계' 중 하나를 선택할 수 있게 이유를 제시하되 **이번 단계에서 자동 변경하지 않는다**.
- **다음은 JEV-C:** B가 실제 응답을 확보한 경우에만 기존 Scanner 판단과 JEV의 추가 가치/지연·비용을 한 페이지로 비교. 별도 실거래 자동화나 JEV 배치는 승인되지 않았다.

**상태 요약:** JEV-A=WINDOWS_VISUAL_PARTIAL_PASS/잔여 종목 전환 인수 대기, JEV-B=READONLY_FIT_GATE_CI_PASS/REAL_MODEL_CALL_NOT_IMPLEMENTED_AND_NOT_APPROVED, GLOBAL-02-S2=OFFLINE_PASS/LIVE_RIGHTS_UNVERIFIED, JEV-C=NOT_STARTED. 이 문서 외의 신규 handoff/단계번호 문서를 만들지 않는다.


### 9.5 JEV-B 구현 1차 결과 — 기존 V4 질문 범위 검증 (2026-11-04)

**판정: B_READONLY_CONTRACT_GATE_PASS / B_REAL_TYPESAFE_EXECUTION_NOT_IMPLEMENTED / B_USER_INPUT_AND_QUESTION_SCOPE_NEEDS_DECISION.**

- 코드 HEAD aa8642b8. GitHub Actions: https://github.com/SkyBluekor/StockScope/actions/runs/41755314432 (**4/4 PASS**). Python 3.11: **2,837 PASS, 2 SKIP**; Python 3.14, Frontend Node22, Windows Fresh Clone 모두 PASS. 실제 TypeSafe 호출은 없었다.
- backend/app/api/jev.py: 기존 무인자 GET /api/simulation/jev/review-feature 응답은 보존. 선택 캡처 ID와 sample_index를 명시하면 원본 COMPLETE 캡처를 읽기 전용으로 조회하고 기존 diagnose_v4_candidate의 판정을 재사용한다. 결과는 LOCAL_ALREADY_RESOLVED, INPUT_CONTRACT_MISMATCH, SOURCE_RIGHTS_HOLD, NOT_ENTRY_CANDIDATE 중 하나. 개별 캡처/종목/표본/해시를 함께 반환하고 source_rights_approved=false, provider_eligible=false, external_model_calls=0, db_writes=0으로 차단한다. 시장자료의 외부 전송권을 자동 승인하거나 새 질문을 만들지 않았다.
- frontend/src/services/jevApi.ts, frontend/src/components/ScannerAiReview.tsx: 일반 JEV 실행 버튼은 계속 disabled. 사용자에게는 **'이 종목에서 JEV를 실행할 수 없는 이유'** 단일 접힘 영역을 제공하고, 사용자가 이를 펼친 경우에만 기존 GET으로 적격성을 확인한다. 실제 캡처/종목/표본 식별이 응답과 다르면 표시하지 않으며, 다른 저장 종목으로 바뀌면 이전 결과를 숨긴다. 기본 화면에서 추가 조회/유료 POST 없음.
- 신규 backend/tests/test_jev_b_single_stock_contract_fit.py: 유형별 차단, 요청 누락/유효하지 않은 후보, 기존 GET 계약 불변, SQLite DB 원본 바이트 불변, 실모델 호출 0을 검증. 기존 frontend/e2e/p003-scanner-recheck.spec.mjs에 수동 요청·기본 접힘·JEV 유료 POST 0 테스트를 추가했다. **합성 테스트 결과가 실제 종목의 JEV 적격성 증거는 아님.**
- 실제 입력 범위의 한계: 현재 TypeSafe V4는 전략 의미 관계의 잔여 충돌(strategy_relation_conflict)만 검토한다. 로컬에서 이미 LOCAL_MATCH/LOCAL_CONFLICT로 판정된 실제 후보를 JEV 호출 대상으로 변경하지 않는다. KRX·DART·Naver·UN에서 유래한 시장/공시/뉴스 텍스트, 이를 바꿔 쓴 문구의 외부 전송권·발표시각은 미승인이다. 따라서 **실제 모델 호출, 사용자 자유 텍스트 전송, 새 V5 질문/점수/투자판단은 구현하지 않았다.**
- Windows 잔여 UAT: 작업 브랜치를 업데이트한 뒤 실제 저장 종목의 AI 검토 탭에서 위 접힘 영역을 직접 열고, 표시된 상태가 선택한 종목과 일치하는지 확인. 다른 저장 후보로 전환했을 때 이전 결과가 남지 않는지도 확인. 이는 **읽기 전용 적격성 확인**으로 유료 요청이 아니다. 이 화면 검증 및 질문 계약 범위 승인 없이는 B 완료로 표시하지 않는다.

**다음 결정:** 현재 V4 의미 충돌 검토만 유지할지, 실제 종목을 대상으로 시장·전략 적합성을 검토하도록 **새 질문의 목적/입력권한/검증 기준을 별도 설계 및 승인할지** 결정해야 한다. '현재 V4가 실주식 종합판단 모델'이라고 표시하지 않는다. 권한 없는 데이터를 새 질문에 투입하지 않으며, 유료 호출은 사용자 실행별 별도 승인 이후에만 가능하다.


## 10. 다음 작업 명세 — JEV-B2: 종목 분석 보조 질문·입력 계약 (2026-11-04)

**상태: OFFLINE_CONTRACT_IMPLEMENTED / CI_4_OF_4_PASS / PROVIDER_CALLS_ZERO / EXISTING_V4_UNCHANGED / LIVE_RIGHTS_UNVERIFIED.** 직전 JEV-B 읽기 전용 종목별 검토 가능 여부 확인은 CI 4/4 PASS, 하지만 실모델 연결 0건. 이번 작업은 그 진단 기능을 확장하지 않는다. **실제 종목에 대해 모델이 보조할 가치가 있는 새로운 단일 질문 계약**을 코드로 고정하고 최소 합성 테스트까지 완료한다.

### 10.1 목적과 기술적 선택

1. **최종 제품 목적:** StockScope 기존 Scanner 10전략·단/중/장기·Risk·시장·보유 판단을 보존하면서, JEV가 해당 종목의 허용된 근거만 보고 **"다음에 무엇을 재확인할 가치가 큰가"**를 하나 분류한다. 기존 판단을 직접 바꾸거나 주가/수익률/매매 성공 확률을 생성하지 않는다. 사용자는 JEV를 별도 수동 대본 입력기가 아닌 실제 후보의 선택적 보조 검토로 이용해야 한다.
2. **기존 V4와 명확히 분리:** \`strategy_relation_conflict\`는 작성된 전략 의미 관계 충돌의 잔여 검토 문제. 실종목 \`LOCAL_MATCH\`를 \`RESIDUAL_SEMANTIC_REVIEW\`로 바꾸는 방법은 불허. V4 \`typesafe_questions_v4.py\`·\`typesafe_state_v4.py\`·\`typesafe_policy_v4.py\`의 질문/해시/정책 보존. 새로운 계약 식별자는 \`JEV_STOCK_REVIEW_ROUTING_V1\`(V4 의미 판정 버전 번호 재사용/덮어쓰기 금지).
3. **JEV 응답 형태:** TypeSafe 공식 \`/v1/systemone\` API의 \`choice\` 질문 1개를 채택하되, 응답 스키마는 공식 문서를 기준으로 구현 단계에 다시 확인한다. 공식 근거: https://docs.typesafe.ai/api/system-one , https://docs.typesafe.ai/primitives/choice . 주관적/비결정적 보조 판단이므로 결과 confidence나 choice 확률을 "주가 상승 확률"이라고 표시하지 않는다. 기존 provider의 \`validate_system_one_response\`는 V4 \`noul\` 전용이므로 그걸 위험하게 일반화하지 말고 **새 질문에 한정한 응답 검증기**를 구현한다.

**고정된 첫 질문 (계약 내용):** "제출된 **사용 허가된 관찰과 종목·전략 검토 문맥**만으로 판단할 때, 기존 로컬 판단에 앞서 가장 먼저 확인할 항목은 무엇인가?" 질문은 **사실 생성·원인 추론·미래 시세 예측**을 금지한다. \`choice\`의 옵션은 다음 네 가지로 제한한다.

| 선택 값 | 해석과 후속 행동 | JEV가 주장하지 않는 것 |
|---|---|---|
| \`CHECK_MISSING_EVIDENCE\` | 판단에 필요한 명시 근거/출처/시점이 빠졌는지 확인 | 없는 데이터가 실제로 불리하다는 뜻 아님 |
| \`CHECK_CONFLICTING_SIGNALS\` | 제공된 허용 입력끼리 상충하거나 해석이 모호한 부분 확인 | 종목의 상승/하락 예측 아님 |
| \`CHECK_RISK_CONTEXT\` | 제공된 내부 위험 조건과 사용자 관찰의 부합 여부 확인 | 새로운 Risk/PANIC 기준이나 거래 중단 명령 아님 |
| \`NO_DISTINCT_REVIEW_PRIORITY\` | 허용 자료 안에서 별도의 우선 점검 항목을 식별하지 못함 | 안전·매수 승인, 충분한 시장정보 확보를 의미하지 않음 |

서버는 입력이 부족하거나 권리/시점이 불명확하면 **JEV 호출 전 \`ABSTAIN\`/NOT_READY** 처리한다. 선택값을 모델 단독의 절대적 결정으로 취급하지 않고, 추가 확인 항목의 **표시 후보**로만 쓴다. 숫자 임계값/자동 승격은 근거 검증 전 만들지 않는다. 납득 가능한 \`choice\` 경로를 구현할 수 없으면 계약을 \`BLOCKED_CONTRACT_UNVERIFIED\`로 종료하며 임의 \`noul\`로 대체하지 않는다.

### 10.2 입력 프로젝션과 권한 범위

| 입력 필드 | 포함 여부 | 출처·시점 계약 |
|---|---|---|
| \`review_scope\` / 질문버전 / 내부 작성 전략의 **원래 문구** | 조건부 허용 | 저장소 자체 저작 또는 별도 사용권 입증 필요 |
| \`review_notes\` (사용자가 직접 창작한 구체적인 가설·관찰) | 조건부 허용 | 단순 "내가 작성" 체크만으로 충분하지 않음. 기사·시세표·공시·UN 텍스트 및 말 바꾸기 파생값 금지 |
| \`horizon_intent\` (현재 단·중·장기 선택) | 조건부 허용 | 현재 사용자가 직접 선택한 값인지 확인. 시장 공급자의 저작 컨텐츠로부터 자동 추출한 항목 제외 |
| \`internal_risk_rule_description\` | 조건부 허용 | 내부 작성된 원래 정책 설명만 허용. 실제 KRX 수치·외부 사실·의미가 보존된 파생 라벨은 별도 권한 확인 전 제외 |
| \`market_regime\`, \`price\`, \`return\`, \`scanner_pass_counts\`, \`foreign_event\`, \`news\`, \`dart\`, \`unsc\` | 기본 **외부 전송 불허** | 가격/뉴스/공시/UN 제재·그 계산값/번역/요약·출처 불명 라벨 자동 패킷에 넣지 않음 |
| \`ticker\`, \`market\`, \`capture_id\`, \`sample_index\`, \`snapshot_hash\`, \`data_asof\` | 서버 **로컬 바인딩** | 종목·캡처·시점 식별용. 필요 없으면 모델 payload에 포함하지 않음. 외부 전송에 편입할 경우 필드별 권리 검증 필요 |

- 클라이언트가 보내는 \`source_rights_approved=true\`, \`observed_at\`, \`rights_receipt\` 값만으로 승인하지 않는다. 서버의 신뢰 가능한 권리·출처·시점 확인 근거가 없는 필드는 전부 제외/차단. 사용 허용을 보수적으로 확인한 경우에만 딱 그 목적의 전송 후보를 만들고, **후보만 만들었다고 유료 호출 승인/실전 판단 승인을 뜻하지 않는다**.
- 최소 한 가지 **종목별로 구분되는 적법한 관찰 또는 검토 가설**이 없으면 요청 생성하지 않는다. 기업명과 템플릿만 채워 실종목 분석처럼 보이는 방식 금지. 사용자의 반복 수작업을 필수 운영 경로로 확정하지 말고, 추후 적법한 자동 데이터가 있을 때 이를 활용할 수 있도록 계약만 만든다.
- 동일 종목·같은 캡처/입력·질문/모델 계약 → 동일 검토 정체성. 서버가 사용자 UI의 종목명·코드 문자열을 신뢰하지 않고 기존 COMPLETE immutable 캡처와 snapshot_hash를 재검증한다. \`data_asof\`와 \`fetched_at\`·공식 공개시각 구분, 미래 정보 과거 소급 금지.
- 민감정보/비밀키·외부 데이터 원문·모델 응답 전문은 stdout/GitHub/진단 UI에 출력하거나 영구 저장하지 않는다. 입력/바디 해시 및 허용 여부만 local-only 진단. 기존 Scanner/Simulation/Risk/Holdings DB 수정 금지.

### 10.3 **이번 한 작업에서 실제로 구현할 파일**

**(A) 신규 최소 모듈:** \`backend/app/jev/stock_review_contract_v1.py\`. 내부 상수 \`JEV_STOCK_REVIEW_ROUTING_V1\`, 고정 Choice 질문 구성, 필드별 allowlist + 권리/시점 보수적 validator, 정체성·입력 구별, bounded state 준비, 모델 호출 없는 \`request_preview\` 결과만 구현. 공식 Choice 응답 shape/모델 ID 검증은 타입 단위 함수 또는 필요한 최소 별도 모듈로 작성. 본 단계에 공급자 HTTP POST 금지.

**(B) 기존 코드 재사용:** \`backend/app/jev/typesafe_provider.py\`의 wire 구조 및 HTTP body 바이트 구성 관례, \`scanner_outbound_gate_live_03.py\`의 권한 ≠ 바인딩 검사 원칙, \`review_identity.py\`의 versioned identity 해시, \`scanner_shadow_s7.py\`의 저장 캡처 조회 방식. 단, **기존 V4 리스크/질문/정책 해시를 변경하지 않고, 이미 승인한 raw 시장 데이터가 있는 것으로 가정하지 않는다.**

**(C) 테스트:** \`backend/tests/test_jev_stock_review_contract_v1.py\` 신규. 자체 작성 합성 텍스트에서만 \`choice\` body shape/문항 ID/옵션 집합/정체성 재현성과 fingerprint 안정성 검증. 라이선스 미확인 원천의 문장/수치/파생 라벨, 날짜만 있는 외부 사건, 변조 해시, 시점 불일치, 종목 불일치, 필수 관찰 부재는 유료 전송 후보로 승격 금지. 응답 \`choice\`가 허용 옵션에 없거나 확률·confidence 모델 응답이 형식 위반이면 거부. 10전략/Scanner/Risk/Horizon/Holdings 기존 변경 없음. \`provider_calls=0\`, \`db_writes=0\` 강제.

**(D) 하지 않을 일:** 실제 TypeSafe 호출·유료 재시도·배치·외부 뉴스 수집·UN 권한 우회·기존 JEV-A UI에 추가 접힘 진단기·새 점수/승률 계산·거래 추천·저장 DB 마이그레이션·실시간 투자판단 연결. 현 단계는 제품에 진짜 결과를 보여주었다고 주장하지 않는다.

### 10.4 실행 순서 / 성공 판정

1. 공식 TypeSafe Choice 응답 형식과 기존 프로젝트 provider 계약을 검사하고 **질문 1개와 4개 옵션**을 코드로 동결한다.
2. 입력 출처/관측 시점이 확실한 자체 작성 합성 상태만 projector에 넣고 \`state/questions/model\` **요청 프리뷰**를 메모리에서 만든다. 권한/자료 없으면 설명 가능한 \`INPUT_NOT_ELIGIBLE\`로 중단한다.
3. 허용/차단 케이스를 fixture에서 검증하고 검증 불가 원천·client self-certification·payload 변조·종목 혼합을 fail-closed 테스트한다. 외부 HTTP 요청/DB write 0으로 확인한다.
4. Python 3.11/3.14, Frontend, Windows Fresh Clone 기존 CI 4/4 통과를 확인하고 기존 단일 실행계획서에 결과·한계를 기록한다. 사용자의 실제 종목 Windows 캡처는 **자동으로 JEV 권한을 부여하지 않으며** 별도 A 전환 인수 미확인을 보존한다.

**통과:** \`JEV_B2_QUESTION_CONTRACT_TESTED_OFFLINE\`: 하나의 Choice 질문과 허용/금지 입력 경계가 코드·테스트로 재현되고 기존 V4·Scanner·Risk에 영향 없음. \`JEV_B2_REAL_MODEL_NOT_RUN\` 상태 유지. 단순 fixture PASS를 "실제 종목 분석 완료"로 표현하지 않는다.

**후속 (이번 단계 아님):** 권리가 확인된 특정 종목 입력으로 같은 Choice 계약의 실효성을 검증할 수 있을 때에만 기존 TypeSafe provider/카탈로그/1회 승인 경계에 연결한다. 증빙이 없어 유효한 실종목 입력이 존재하지 않는다면 **\`B2_REAL_INPUT_BLOCKED\`로 명시하고** 사용권 확인이 가능한 공급자·내부 저작 입력의 확보를 별도 작업으로 판단한다. 권한 미승인 데이터를 불법·무단 사용하거나 포장만 바꿔 넣지 않는다.

**단일 현재상태:** JEV-A=WINDOWS_VISUAL_PARTIAL_PASS/후보 전환 실인수 미완; JEV-B read-only=CI_PASS/실제 모델 미실행; **JEV-B2=OFFLINE_CONTRACT_IMPLEMENTED / CI_4_OF_4_PASS / REAL_MODEL_NOT_RUN**; GLOBAL-02-S2=OFFLINE_PASS/UN_LIVE_BLOCKED; JEV-C=NOT_STARTED.

### 10.5 JEV-B2 구현·검증 결과 (2026-11-04)

**완료 판정:** `JEV_B2_QUESTION_CONTRACT_TESTED_OFFLINE` / `CI_4_OF_4_PASS` / `JEV_B2_REAL_MODEL_NOT_RUN`. **이는 실종목 JEV 분석 성공 판정이 아니다.**

- **코드:** `backend/app/jev/stock_review_contract_v1.py`에 `JEV_STOCK_REVIEW_ROUTING_V1` 독립 계약과 Choice 문항 `review_priority` 1개/옵션 4개(`CHECK_MISSING_EVIDENCE`, `CHECK_CONFLICTING_SIGNALS`, `CHECK_RISK_CONTEXT`, `NO_DISTINCT_REVIEW_PRIORITY`) 구현. 기존 TypeSafe System One V4의 `noul` 질문/해시/라우팅/정책과 분리하고 수정하지 않음. 선택 결과와 모델 confidence/옵션별 확률은 `REVIEW_PRIORITY_ONLY_NOT_STOCK_RETURN_PROBABILITY` 범위로만 정규화하여 상승 확률·수익 전망·시장 인과관계·매매 승인으로 해석 불가.
- **공식 형식 근거:** [TypeSafe System One](https://docs.typesafe.ai/api/system-one), [Choice](https://docs.typesafe.ai/primitives/choice) 문서의 `state/questions/model` 및 `answers[review_priority].{type,choice,confidence,probabilities}` + `usage` 형식을 기준으로 각각 타입/선택지/확률 합/최대 선택/모델 ID/사용량 검증기를 작성. 실제 TypeSafe 서버의 실호출 응답 검증은 **미실시**.
- **권한·입력 범위:** `synthetic_fixture()`에서 생성한 **코드 내 완전한 가상 종목** `SYNTH-NOT-TRADED`만 오프라인 요청 프리뷰 생성. 다른 실제 종목, 외부 가격·뉴스·공시·UN 및 파생 텍스트, 사용자 임의 권한 체크값, 변조된 캡처 해시, 메모리에 있는 자체 작성 문자열의 임의 변경, 잘못된 UTC 시각·후행 관측, 모델 ID 오류는 모두 `INPUT_NOT_ELIGIBLE`로 차단. 합성 코드 원본과 일치한다는 것은 실제 서비스 사용권 증명이 아니며 **어떤 사용자 실데이터도 허가하지 않는다**.
- **출력·식별자:** 프리뷰 `request_preview`, `question_hash`, `input_hash`, HTTP body SHA-256과 캡처·표본·모델·문항을 결합한 `review_identity`를 재현 가능하게 계산. `httpx.Request`의 JSON 직렬화 바이트를 계산할 뿐 **network send는 호출하지 않음**. 실제 후보·문항 변경 없이 네트워크/DB/TypeSafe provider를 사용할 수 있는 공개 API·실행 버튼·권한 토글은 추가하지 않음.
- **테스트:** `backend/tests/test_jev_stock_review_contract_v1.py` 신규. 고정 Choice 문항/옵션/응답 스키마, 중복 호출 정체성의 재현성, 모델/투자결과 표시 범위, 원천 사칭·본문/스냅샷 변조·권리 자가 인증·UTC 시점·미확인 데이터 차단, 확률·confidence/응답 무결성, 기존 V4 `noul` 질문 불변을 검증. 별도 임시 SQLite 파일 바이트 불변과 HTTP send 금지 검사 포함.
- **GitHub CI:** [Actions #41757258927](https://github.com/SkyBluekor/StockScope/actions/runs/41757258927) **4/4 PASS**. Backend Python 3.11 `2,884 passed / 2 skipped`; Python 3.14 PASS; Frontend Node22 PASS; Windows Fresh Clone PASS. 전체 CI 성공 외에 사용자 Windows 실종목 시험/모델 호출/사용 권한 검사까지 완료된 것은 아님.
- **남은 실제 제품 연결:** 현재 새 Choice 계약은 의도적으로 **실제 Scanner 캡처를 모델로 전송하지 않는다**. `TypeSafeSystemOneProvider.review`의 기존 응답 검증은 V4 `noul`만 지원하므로 새 Choice를 기존 유료 HTTP 경로에 직접 연결하면 안 됨. 이후 단계는 서버가 검증한 **실제 사용자 또는 내부 저작 원천의 필드별 권리·시점·종목 구분**을 확보하고, 그때에만 새 Choice 응답 검증·원자적 동일 요청 중복 방지·사용자 1회 유료 승인·결과 저장·재조회를 실제 서비스와 연결하는 것. 기존 JEV-A Windows의 후보 전환 실사용 검증도 여전히 미완료.
- **후속 차단:** 출처/권한/데이터 이용 가능 시각 미확인 시 `REAL_INPUT_BLOCKED` 유지. 기존 합성 fixture 반복이나 진단 UI 추가로 실제 성과를 주장하지 말 것. 사용자의 명시적 추가 승인 전 실모델 유료 요청 금지.
