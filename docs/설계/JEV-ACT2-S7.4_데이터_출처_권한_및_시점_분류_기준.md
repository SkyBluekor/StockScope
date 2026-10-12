# JEV-ACT2-S7.4 데이터 출처·권한 및 시점 분류 기준

## 1. 조사 목적과 범위

**판정: 실제 Scanner 시장 데이터의 TypeSafe 전송은 NO-GO. 로컬 분류·계보·증거 검증 계약 설계는 GO.** `LOCAL_PACKET_READY`는 전송 허가가 아니다. 이 문서는 S7.4 구현 기준이며 구현 완료·권한 승인서가 아니다.

- 조사일: **2026-10-12, Asia/Seoul**. 저장소: `SkyBluekor/StockScope`, 기준 브랜치: `main`.
- 작업 시작 시 `git ls-remote origin refs/heads/main`으로 확인한 HEAD: **`12532ac3b6b35758ac4a471157d3e32fab812368`**. 로컬 HEAD도 동일하며 조사 시작 시 작업 트리는 깨끗했다. 아래 코드 링크는 모두 이 커밋에 고정한다.
- **A = 코드로 확인**, **B = 공식 외부 자료로 확인**, **C = 미확인 또는 설계 제안**. 표에서 `A → C`는 입력·구조는 코드 사실이고 분류·조치는 제안이라는 뜻이다. 권한에 관한 적용 해석은 B 원문과 별도로 C로 표시한다.
- 코드 연결 여부는 확인했지만 사용자 계정의 API 가입·승인 내역, 실행 로그, 원본 응답 또는 Runtime DB를 감사하지 않았다. 따라서 “연결된 경로”는 실제 이번 계정에서 호출했다는 뜻이 아니다.
- 사용자 제공 실환경 보고: Capture `a0f8f2cb-c1ab-4b3a-9488-b125e0369a2b`, 15건 중 진입 1건·참고 14건, 대한항공 `003490`, 신호일 `2026-10-08`, `LEGACY_LIMITED`, `LOCAL_PACKET_READY`, `RETROSPECTIVE_CAPTURE`, `PROVIDER_HOLD`, TypeSafe 0회. **C: 본 조사에서 원본을 재검증하지 않은 사용자 보고**이며 저장소 문서의 과거 기록도 DB 원본을 대신하지 않는다.
- 이번 작업은 Markdown 한 파일만 추가한다. Scanner/JEV 수정, DB 생성·마이그레이션·동기화, Capture 변경, 시장/API 실조회, TypeSafe 호출, 승인 플래그 변경은 수행하지 않는다. 공식 웹 문서 열람과 GitHub 조회·문서 PR은 조사 범위다.
- 기존 [S1.3 검증 문서의 S7.3 기록](../검증/JEV-ACT1-S1.3_정책_출처_및_의미_저장_정합성_검증.md), [JEV 통합 설계](StockScope_JEV_통합설계_v2_2026-10-06.md), [Semantic Source 계약](StockScope_TypeSafe_Jev_V3_Semantic_Source_Contract_v1_2026-10-07.md)과 역할을 구분한다. 이 문서는 **원천 권한·시간·전송 적격성의 단일 기준**이다.

### 1.1 코드 근거 색인 — 모두 A

표의 A 번호는 아래의 파일·함수·고정 줄 번호를 가리킨다. 파일명을 줄인 표에서도 이 색인이 추적 근거다.

| ID | 파일·함수 및 확인 범위 |
|---|---|
| A01 | [market/providers/krx.py:28](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/market/providers/krx.py#L28) `KrxProvider`: 제품별 endpoint, `_save_disk_cache`(366), `_request_rows`(393), `_get_rows`(456), `stock_daily`(574), `basic_info`(628), `index_daily`(809) |
| A02 | [backtest/market_store.py:22](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/market_store.py#L22) `HistoricalMarketStore`: schema(53), `put_stock_day`(104), `replace_stock_day`(132), `put_index_day`(234), 데이터 지문 |
| A03 | [backtest/scanner.py:37](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/scanner.py#L37) `StockScannerService`: 생성자(68), 수집 래퍼(431/441), `_ensure_market_history`(1168), `_quick_current_candidate`(1638), `_current_candidate`(1805), `_deep_candidate`(1918), `run`(2189), 최종 순위(2593), `generated_at`(2638) |
| A04 | [backtest/engine.py:85](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/engine.py#L85) `BacktestEngine._signal_snapshot`: as-of 행 절단, 기술지표·상대강도·StrategyInput·Risk Gate |
| A05 | [market/technical.py:7](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/market/technical.py#L7) `TechnicalAnalyzer._sma/_rsi14/_atr14/analyze`; [strategy/engine.py:217](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/strategy/engine.py#L217) `_evaluate` 및 전략별 조건(259~) |
| A06 | [backtest/selector.py:424](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/selector.py#L424) `build_condition_state`, `current_readiness`(536); [risk/engine.py:9](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/risk/engine.py#L9) `RiskEngine.build_plan`(121); [backtest/multi_strategy.py:67](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/multi_strategy.py#L67) `_current_risk_plan` |
| A07 | [backtest/candidate_priority.py:135](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/candidate_priority.py#L135) `_base_priority_sort_key`, `build_candidate_priority`, `rank_candidates`(279) |
| A08 | [api/backtest.py:551](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/api/backtest.py#L551) Scanner 생성 및 Capture 최종화(637); [prospective/service.py:82](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/prospective/service.py#L82) `try_finalize_scanner_capture` |
| A09 | [prospective/catalog.py:234](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/prospective/catalog.py#L234) `_candidate_snapshot`, `finalize_capture`(295), sample INSERT(524), `_now`(46), `_result_identity`(190) |
| A10 | [strategy/semantic_identity_bridge.py:126](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/strategy/semantic_identity_bridge.py#L126) `_actual_passed_conditions`, `semantic_projection_candidate`(185); [semantic_policy_provenance.py:26](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/strategy/semantic_policy_provenance.py#L26) `validate_pinned_selection_policy`, `verify_candidate_policy_binding`, `semantic_policy_record` |
| A11 | [strategy/semantic_source_v2.py:74](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/strategy/semantic_source_v2.py#L74) `build_semantic_source_v2`, `verify_semantic_source_v2`(175); [condition_semantics.py:158](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/strategy/condition_semantics.py#L158) `project_passed_condition_meanings` |
| A12 | [jev/scanner_shadow_s7.py:38](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/jev/scanner_shadow_s7.py#L38) `_connect_readonly`, `load_frozen_candidates`; [scanner_integrity_s7_1.py:61](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/jev/scanner_integrity_s7_1.py#L61) `assess_frozen_candidate` |
| A13 | [jev/scanner_shadow_s7_3.py:108](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/jev/scanner_shadow_s7_3.py#L108) `_local_packet`: evidence(185~), body(201~), `prepare_shadow_candidate`(259), `preflight_shadow_candidate`(293); `_historical_capture_status`(96) |
| A14 | [jev/decision_reviewer_offline.py](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/jev/decision_reviewer_offline.py) `build_scanner_review_input`: S3 로컬 계약(104), `available_on`과 `available_at=None` |
| A15 | [jev/typesafe_provider.py:20](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/jev/typesafe_provider.py#L20) endpoint, `TypeSafeSystemOneProvider.review`(191); [decision_reviewer_micro_canary.py:337](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/jev/decision_reviewer_micro_canary.py#L337) `micro_packet`, `SystemOneMicroProvider.ask` |
| A16 | [horizon.py:62](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/horizon.py#L62) `resolve_horizon_context`; [tools/data/jev_s7_shadow.py:62](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/tools/data/jev_s7_shadow.py#L62) `execute`, `run-approved`도 HOLD |
| A17 | [integrations/kis/quote.py:97](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/integrations/kis/quote.py#L97) `inquire_domestic_price`; [quotes/service.py:257](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/quotes/service.py#L257) `_fetch_upstream`, `provider_timestamp=None`, UTC `received_at`(336) |
| A18 | [api/router.py:1](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/api/router.py#L1) 제품 라우터 목록; [market/kis/client.py:26](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/market/kis/client.py#L26) `KisReadOnlyClient`; [api/kis.py](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/api/kis.py) 구형 라우터 |
| A19 | [market/providers/dart.py:16](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/market/providers/dart.py#L16) `OpenDartProvider`; [market/service.py:16](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/market/service.py#L16) `stock_context`; [strategy/service.py](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/strategy/service.py) 개별 종목 분석 |
| A20 | [backtest/sector_rs_prefetch.py:71](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/sector_rs_prefetch.py#L71) `HistoricalSectorInputPrefetcher`; [sector_rs_input.py](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/backtest/sector_rs_input.py) `evaluate_historical_sector_input`, `STATIC_CURRENT` 시간 차단 |
| A21 | [news/naver.py:22](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/news/naver.py#L22), [news/policy.py:22](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/news/policy.py#L22), [api/news.py:15](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/api/news.py#L15) 검색 공급자·정책·라우팅 |
| A22 | [macro/providers/fred.py:151](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/macro/providers/fred.py#L151) `collect_fred_dgs10`; [macro/providers/kis.py:41](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/macro/providers/kis.py#L41) `probe_kis_daily_chart`; [collect_macro_next6a_s2.py:76](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/tools/data/collect_macro_next6a_s2.py#L76) 별도 수집 CLI |
| A23 | [event_evidence/time.py:14](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/event_evidence/time.py#L14) `EvidenceTimeQuality`, `TemporalEvidence`; [event_evidence/policy.py:26](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/event_evidence/policy.py#L26) `EventEvidenceSourcePolicy` |

## 2. 현재 실제 데이터 흐름

### 2.1 Scanner → S7.3 경로 — A

```text
api/backtest → StockScannerService(KrxProvider)
  KRX 주식 일별 응답 ─┬─ 메모리/원본 gzip 캐시
  KRX 지수 일별 응답 ─┘   → HistoricalMarketStore(정규화 행)
    → 종목/지수 as-of 이력 → BacktestEngine._signal_snapshot
    → 기술지표·시장 국면·상대강도 → 전략 평가
    → 조건 PASS/FAIL + RiskPlan → current_readiness → 후보
    → rank_candidates → 현재 추천 + 재현성 감사
    → ProspectiveCatalog: 의미 투영을 포함한 snapshot 생성·해시·동일 값 저장
    → S7 읽기 전용 로더 → S7.1 정합성 → S7.3 제한적 로컬 패킷
    → preflight: PROVIDER_HOLD (외부 호출 경로 없음)
```

Semantic Source는 저장된 Snapshot을 나중에 최신 데이터로 다시 만드는 단계가 아니다. 신규 Capture 최종화 중 의미 투영을 한 번 만들고, 해시에 사용한 그 값을 저장한다(A09). 기존 Capture를 현재 전략 정의로 재작성하면 안 된다.

### 2.2 계산과 판단의 구분 — A → C

| 계층 | 확인한 계산·판단 | 데이터 의존성과 의미 |
|---|---|---|
| 기술지표 | SMA는 최근 N 종가의 산술평균. RSI14는 최근 14 변화량의 평균 상승/하락 비율; Wilder 평활로 가정하지 않음. ATR14는 True Range 14개 평균. 거래량비는 최신 거래량/최근 20개 평균(A05) | 원본 OHLCV의 `EXTERNAL_DERIVED` |
| 시간 절단 | `_signal_snapshot`은 기본 60행 기술분석, 상대강도용 61행; MA120만 별도 과거 120행 보완. 지수는 신호일까지 절단(A04) | 미래 **거래일** 방어가 원천 **공개 시각/수정 이력** 증명을 대신하지 않음 |
| 전략 | `trend_following`, `pullback`, `breakout`, `support_bounce`, `oversold_bounce`, `range_trading`, `momentum_continuation`, `volatility_squeeze`, `ma20_rebound`, `trend_recovery`; MA 배열·기울기, RSI, ATR, 거래량, 고저점, 지지/저항, 상대강도, 시장 국면의 조건·가중치(A05) | 조건 정의는 `INTERNAL_POLICY`; 특정 후보의 점수·충족 결과는 `INTERNAL_DECISION`이며 외부 원천 의존성을 유지 |
| 실제 PASS | `build_condition_state`가 엔진 reasons/unmet를 PASS/FAIL로 투영. 의미 문장은 고정 매핑으로 생성. 원본 조건명 `source_condition`으로 엔진 증거와 의미 항목을 1:1 대조(A06/A10/A11/A13) | Semantic Source는 새 시장 원천도 LLM 분석 결과도 아님. 조건 ID 두 네임스페이스를 동일하다고 가정하지 않음 |
| Risk | 전략별 구조적 기준가, ATR buffer, 손절·목표·RR, Risk Gate 등으로 `RiskPlan` 생성. `current_readiness`가 reference-only/CAUTION/blockers를 warning에 반영(A06) | Risk 규칙은 내부 정책, status/warning은 시장 데이터에 의존하는 내부 판단. `False`는 독립적인 안전 인증이 아님 |
| 추천·순위 | quick score/조건비/Risk 감점은 후보 축소에 사용. 최종 순위는 tier, 미충족 수, Risk, 진입 거리, 전략 적합도 및 결정적 동률 처리(A03/A07) | 특정 후보뿐 아니라 비교 모집단의 데이터에도 의존. 점수는 확률이 아님. 선택된 전략 키도 “이 후보에 선택되었다”는 시장 의존 정보 |
| 과거 성과 | 3년 이력 설명은 최종 현재 전략/생산 순위를 바꾸지 않는 경로(A03 `run`) | Snapshot에 있을 수 있지만 S7.3 전송 후보에는 미포함. 현재 판단 근거와 사후 성과를 합치지 않음 |

### 2.3 계보·저장·손실 표 — A, 마지막 열은 C

| 입력 원천/제품 | 수집 → 변환 | 저장 위치 | Snapshot → S7.3 필드 | 손실 정보/권한 증거 및 조치 |
|---|---|---|---|---|
| KRX OPEN API 주식 일별 OHLCV·종목정보 | A01 `stock_daily` → A02 → A04/A05/A06 | `backend/runtime/krx` gzip; `backend/runtime/market_history/market_history.db`: `stock_daily`의 `row_json` | `current_price`, `conditions`, `risk`, `entry_risk_guide` → `baseline.conditions/risk`, `evidence[].statement` | 응답 상위 `provider/endpoint`는 DB 행에 함께 저장되지 않음. 수집 ID·약관 버전·공개/수집 시각 없음. 행별 origin은 별도 증거 없으면 UNKNOWN |
| KRX OPEN API 지수 일별 | A01 `index_daily` → A04 시장 국면/상대강도 → A05 전략 | 같은 DB `main_index_daily`, `day_status` | 조건·선택 전략·Risk에 간접 반영 → 조건 statement | 종목과 지수 원천을 별도 부모로 남겨야 함. `SCANNER_ENGINE_DERIVED`만으로는 제품·행을 식별 못함 |
| 후보 모집단과 내부 순위 규칙 | A03 전체 후보 → A07 `rank_candidates` | Scanner 결과 캐시 `backend/runtime/scanner`, 재현성 감사 | `priority.rank` 및 sample `rank` → `baseline.rank` | 순위는 모든 비교 후보의 입력 지문·모집단 경계 필요. 최종 한 종목 원천만 허가해도 rank는 자동 허가 불가 |
| 전략 정의·선택 정책 pin | `ProductionStrategySelectionRegistry` → A10 pin 검증 | 실행 요청/결과 및 Snapshot | `strategy_version_id`, `strategy_definition_hash`, `semantic_strategy_identity`, `semantic_policy_provenance` → `baseline.strategy_identity/policy_id/policy_hash` | 정책 검증은 실행 신원 검증이지 KRX 이용권 검증이 아님. Legacy 원본 null 유지 |
| 조건 PASS·정적 의미 사전 | A10 독립 감사 대조 → A11 매핑/의미 조합 | Snapshot의 `semantic_condition_evidence`, `semantic_source_v2` | `conditions.items[].observed_meaning` → `evidence[].statement` | 패킷은 원본 조건명·엔진 ID·semantic hash를 직접 싣지 않음. 외부 전송 시에도 로컬 sidecar에 필드→원본 조건→원천 행 연결 필요 |
| Capture 메타데이터 | A09 `_result_identity`/`finalize_capture` | 전달된 simulation DB의 `prospective_capture_run`, `prospective_recommendation_sample` | `snapshot_json/hash`, `signal_date`, `completed_at` → `source.*` | 완료 시각은 공개/최초 수집 시각 아님. 해시는 정합성 증거일 뿐 발행자 서명/권한 증거 아님 |
| S7.3 로컬 패킷 | A12 검사 → A13 `_local_packet` | 기본 반환 객체; 명시적 저장 시 별도 `data/jev_research/s7_shadow.sqlite3`의 `jev_s7_3_preflight` | `input_hash`, `limitations`, prepared identity | 이번 조사에서는 저장·로딩 명령 실행 안 함. 준비 결과 전체를 provider state로 직렬화하면 종목 식별자까지 포함될 수 있으므로 별도 allowlist 필요 |

**C: 여러 원천을 결합한 판단은 DAG로 보존한다.** 원천 행/응답을 leaf, 지표·조건·Risk·순위를 변환 node, 패킷의 JSON Pointer를 출력 node로 둔다. `derived_from`은 모든 부모를 가리키며, 부모 하나라도 미확인·제한이면 자식의 자동 전송 승인을 금지한다. 저장소의 KRX 코드만으로 외부에서 가져온 DB 행 전체를 KRX라고 소급 인증할 수 없다.

## 3. 제공처 및 API별 원천 목록

다음은 **A: 정적 코드 연결 조사**다. “제품 연결”과 “본 계정 실제 사용 입증”을 구별한다. 실제 사용 시 credential 또는 runtime 값을 읽어 증명한 항목은 없다.

| 제공처·제품 | 코드에 있는 정확한 경로/조회 목적 | 현재 연결 범위 | S7.3 계보 판정 |
|---|---|---|---|
| KRX Data Marketplace **OPEN API** | `https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd`, `sto/ksq_bydd_trd`; `AUTH_KEY`, `basDd` 사용(A01) | 기본 Scanner의 KOSPI/KOSDAQ 일별 OHLCV·거래대금·시총·종목명/코드 | 주된 원천. 승인된 개별 계정·제품 및 실제 행 계보는 C |
| 같은 OPEN API의 지수 상품 | 위 base의 `idx/kospi_dd_trd`, `idx/kosdaq_dd_trd`(A01) | 기본 Scanner 시장 국면·시장 상대강도 | 주식 원천과 별도 source ID |
| 같은 OPEN API의 종목기본정보 상품 | `sto/stk_isu_base_info`, `sto/ksq_isu_base_info`, `basic_info/search_stocks`(A01) | 검색/종목 식별 제품 경로 | 기본 Scanner 후보 이름은 일별 응답에서 옴. 모든 후보가 기본정보 API를 거쳤다고 쓰지 않음 |
| KRX Marketplace 웹 조회·다운로드/유료 분배상품 | 이번 조사한 기본 Scanner에서 해당 수집 경로·계약 바인딩 없음 | **현재 원천으로 확인되지 않음** | OPEN API 약관과 통합 금지. 대체 계약 후보일 뿐 |
| KIS Open API REST 현재가 | `/uapi/domestic-stock/v1/quotations/inquire-price`, `FHKST01010100`(A17) | quotes 제품 경로에 연결; 실/모의 환경 구분, 캐시 QuoteSnapshot | 기본 Scanner 및 S7.3에 연결되지 않음. 현재가를 과거 후보에 섞지 않음 |
| KIS 실시간 WebSocket 현재가 | `integrations/kis/websocket_client.py:17`: `ws://ops.koreainvestment.com:21000`(실전), `:31000`(모의); `quotes/websocket_parser.py:13`의 `H0STCNT0`(KRX), `H0NXCNT0`(NXT), `H0UNCNT0`(통합) | `quotes/service.py:561`이 WebSocket manager를 주입하고 `QuoteStore` 메모리 캐시에 tick 저장. 사용 가능 시 WS, 그 외 REST 경로 | S7.3 미연결. KRX/NXT/통합 venue의 원천 권리를 하나로 합치지 않음. 실제 구독/계정 승인 여부는 C |
| KIS 잔고·휴장일 | `integrations/kis/account.py::inquire_domestic_balance`, `/uapi/domestic-stock/v1/trading/inquire-balance`; `holiday.py::KisHolidayProvider`, `/quotations/chk-holiday`, `CTCA0903R` | `holdings/kis_sync.py`(106), `market_session/service.py`(28)에 연결 | 계좌/세션 기능; S7.3 입력 아님. 계좌정보를 시장정보와 동일 분류하지 않음 |
| KIS 구형 읽기 클라이언트 | `market/kis/client.py::get_quote/get_daily_chart`, `/inquire-daily-itemchartprice`, `FHKST03010100`(A18) | `api/kis.py`에 구현되어 있으나 현재 `api/router.py`에 등록되지 않음 | **코드 존재만 확인**, 생산 Scanner 사용으로 간주 금지 |
| KIS 해외 지표 probe | `/uapi/overseas-price/v1/quotations/inquire-daily-chartprice`, `FHKST03030100`(A22) | 별도 `macro_capability_next6a_s2.py` CLI | 연구 capability 탐색; S7.3 미연결 |
| OpenDART | `https://opendart.fss.or.kr/api/`: `corpCode.xml`, `company.json`, `list.json`, `fnlttSinglAcntAll.json`, `document.xml`, 주요사건 API(A19) | data_sources/개별 종목 재무·공시·EventRisk 경로. provider cache는 메모리 | 기본 Scanner에는 DART 주입 없음. `event_risk=False`는 실제 공시 조회로 위험 부재를 확인한 값이 아님(A04) |
| OpenDART 업종 + KRX 업종지수 | A20 optional `sector_company_provider/sector_prefetcher` | 명시적 주입 시 감사용. 현재 회사정보는 `STATIC_CURRENT`; 시간 gate가 생산 반영을 제한 | 현재 기본 Scanner 사용 원천으로 승격 금지; 향후 혼합 계보 시험 사례 |
| FRED / DGS10 | `https://api.stlouisfed.org/fred`의 series·observations·vintagedates; A22 수집 CLI | Macro 연구 저장/조회 경로, production 승인과 분리 | 실제 일별 주가 대체재 아님. S7.3 미연결 |
| NAVER 검색 Developer Center | `https://openapi.naver.com/v1/search/news.json`(A21) | 선택 가능한 뉴스 표시 경로 | `ai_allowed=False`; S7.3 미연결 |
| NAVER Cloud API Hub 검색 | `https://naverapihub.apigw.ntruss.com/search/v1/news`(A21) | 현재 설정 기본 provider kind는 `api_hub`(`core/config.py:22`); 실제 키/호출 여부는 미검증 | Developer Center와 계약 분리. `ai_allowed=False`, 서버 결과 cache 0초 정책 |
| 자체 합성 fixture | A15 `CASES`, `synthetic_projection` | S5/S6 합성 전용 별도 경로 | 실제 시장자료의 익명화/말바꾸기와 다름. 실제 후보 주입 거부 |

pykrx, FinanceDataReader, yfinance, data.go.kr을 기본 Scanner 수집원이라고 확인할 코드 근거는 없다. 유사 데이터 사이트의 약관을 이 KRX OPEN API 원천에 대신 적용하지 않는다.

**A: 추가 캐시 구분.** `backtest/history_store.py::HistoricalStore`(20)의 `backend/runtime/backtest/history/{market}/stock_{code}.json.gz`, `market_index.json.gz`는 정규화된 rows/checked_dates를 저장하는 종목별 캐시다. `backtest/service.py`(323~)의 legacy 이력 재사용과 A02 `import_legacy_stock/index` 구현이 존재하지만, 기본 Scanner의 직접 읽기 원천은 시장 단위 DB다. 어느 저장 구조에도 파일 경로만으로 출처·권한을 인증하는 기능은 없다. KIS `quotes/store.py::QuoteStore`(9)는 메모리 최신 tick 저장소이며 KRX EOD DB와 합치지 않는다.

## 4. 원본·파생·내부 계산 데이터 분류

**C: 새로운 S7.4 분류 계약. 현재 S7.3에는 이 enum이 구현되어 있지 않다.** `origin_type`과 외부 의존성은 별도 축이다.

| origin_type | 분류 기준·예시 | 권한 전파 |
|---|---|---|
| `EXTERNAL_RAW` | 제공자 응답의 가격·종목명·지수·공시. 숫자 형 변환/필드명 변경도 원본 계보 유지 | 개별 제품의 해당 행·필드 이용조건 |
| `EXTERNAL_DERIVED` | SMA/RSI/ATR/상대강도, 원본 수치로 만든 의미 진술 | 모든 부모 원천의 제한 + 파생정보 조항 |
| `INTERNAL_POLICY` | 시장 관측값을 포함하지 않는 조건 정의·가중치·선택 규칙·질문 | 자체 저작·공개 권한과 외부 계약 의존성을 별도 확인; 특정 후보와의 연결은 추가 파생 node |
| `INTERNAL_DECISION` | 실제 조건 PASS, Risk status, 후보 선택·rank | `derived_from`으로 시장 원천 제한을 그대로 추적. 내부 계산이라는 이유로 허가 금지 |
| `PROVENANCE_METADATA` | capture ID, snapshot hash, source ID, 시각·제품 식별자 | 해시가 참조하는 자료와 결합 식별 가능성·계약 적용 범위를 검사. 무조건 면제 아님 |
| `SYNTHETIC` | 등록된 순수 자체 작성 fixture, 시장 원천 부모 없음 | fixture 전체 동일성 및 작성 권한 확인. 실행 승인은 별도 |
| `UNKNOWN_ORIGIN` | DB/CSV/캐시에 원천 연결 증거 없음, 부모 누락 | `SOURCE_ORIGIN_UNVERIFIED`, HOLD. 파일명·provider 문자열만으로 해제 금지 |

“상승 구조다”라는 문구 사전 자체는 내부 정책일 수 있다. 특정 날짜 후보에서 그 문구가 **참이라고 선택된 사실**은 외부 가격에 의존한다. 식별자를 지우거나 수치 대신 문장/해시를 보내도 그 의존성을 제거하지 못한다.

## 5. 공식 이용 권한 근거 및 판단표

### 5.1 공식 근거 원장

모든 확인 날짜는 **2026-10-12**. `NOT_VERIFIED`는 근거 확보 상태, `UNVERIFIED`는 전송 권한 판정 상태다. B는 확인한 원문 범위만, 적용·후속 조치는 C다. 이번 조사는 별도 계약서를 받거나 제공처에 문의를 발송하지 않았다.

| ID / 제공처·문서 | 공식 원문·조항 | B: 확인된 범위 | C: 적용 판단·불확실성·추가 확인 |
|---|---|---|---|
| B01 KRX OPEN API 국문 약관 | [국문 원문](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp), 제6조②, 제10조③, 제11조②③, 제12조③; 시행 2025-12-26 | 비상업 목적, 결과 대가 청구 제한, 화면 출처 표시, 받은 정보의 제3자 제공 금지, 계약 종료 후 이용 제한. 가공 부가정보에 관한 면책은 있음 | **받은 원본의 제3자 제공은 `VERIFIED_PROHIBITED`**로 처리. 시장 파생 조건·Risk·순위의 AI 처리 포함 범위는 `UNVERIFIED`; 면책은 전송 허가가 아님. KRX 데이터 담당 `krxdata@krx.co.kr`에 실제 필드·처리 목적을 제시해 확인 |
| B02 KRX 상품·이용 절차 | [공식 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd), [주식 일별 상품](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC), [KOSPI 지수 상품](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=EREKZauXnMmxyIlqzeDN), [이용방법](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp) STEP 1~4 | 명명된 일별 상품 및 인증키·상품 활용 승인 절차 존재 | A01 endpoint와 상품명 대조. 정적 웹 본문에서 실제 endpoint/시간 상세가 비어 있는 부분은 **NOT_VERIFIED**. 계정의 승인 상품·신청 목적·적용 약관 버전은 별도 원문 승인서 필요. 대외 서비스 안내 문구가 B01 제3자 제공 제한의 포괄 예외라는 해석 금지 |
| B03 KRX 데이터 분배상품 | [공식 분배상품 안내](https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA002.jsp), Data feed/EOD 항목 | 별도 데이터 분배상품·전송 방식과 EOD 전송 시간 안내 | 현재 OPEN API의 공개 시각으로 전용 금지. 별도 유료/분배 계약에서 파생정보·외부 AI·재위탁·보관 허용 범위를 협의할 대안. 실제 체결·허용은 **NOT_VERIFIED** |
| B04 KIS Developers | [제휴안내](https://apiportal.koreainvestment.com/provider), 제휴대상·시세 API 유의사항 | 개인 본인 자산 이용과 제3자 서비스 법인 제휴 구분. 제휴기관 시세 이용에 거래소/코스콤 등의 정보이용계약 필요 안내 | 해당 안내를 개인 외부 AI 처리에 그대로 확대 적용하지 않음. 웹의 이용약관 팝업 본문은 확보하지 못해 **NOT_VERIFIED**. 개인 Open API 서비스 약관·시세정보 이용계약·외부 처리업체 제공 범위를 KIS 서비스/제휴 담당 및 해당 정보권리자에게 확인 |
| B05 OpenDART | [이용약관](https://opendart.fss.or.kr/intro/terms.do) 제5·16·19·23조, [소개](https://opendart.fss.or.kr/intro/main.do); 약관 부칙 2020-01-21 | 공시 활용 서비스, 저작권/관계법령, 키 관리·제출인 책임 명시 | 자료 활용 안내는 모든 공시 문서의 외부 AI 재제공·보관 허가를 특정하지 않음. 자료 유형별 제3자 권리 및 사용 목적을 OpenDART Q&A/담당자에게 확인. 현재 S7.3에는 미포함 |
| B06 FRED | [API 이용약관](https://fred.stlouisfed.org/docs/api/terms_of_use.html), General/이용조건 | API 이용조건 외에도 해당 제3자 계약·권리 준수 요구 | 계열 전체를 같은 권리로 취급하지 않음. DGS10 원천/계열별 사용·AI 조건은 별도 확인, 이번 외부 전송 grant는 **NOT_VERIFIED** |
| B07 NAVER 두 제품 | [개발자센터 약관 접근 대상](https://developers.naver.com/terms/), [Ncloud 서비스 약관 접근 대상](https://www.ncloud.com/policy/terms/svc) | 이번 열람에서 각 적용 약관 본문을 확보하지 못함: **NOT_VERIFIED** | Developer Center·API Hub 계약을 각각 고객센터에서 확보하고 뉴스 제공자의 권리도 확인. A21의 AI 금지는 **코드 정책 사실**이며 공식 약관 확정 인용이 아님 |
| B08 TypeSafe 처리 범위 | [Master Customer Agreement](https://typesafe.ai/legal/mca) §4.1/4.3/5/10.3; [Privacy](https://typesafe.ai/legal/privacy-policy) Services/Retention/International Visitors | MCA는 서비스 처리·저장 및 telemetry 등을 규정하고 고객의 필요한 권리 확보를 요구. Privacy는 입력 학습 미사용 및 미국 처리·보관을 안내 | 학습 미사용을 보관 없음으로 해석 금지. 실제 계정 적용 계약·주문서·보존기간·하위처리자·telemetry/hash 처리 범위를 확보해야 함. 원천 권리자가 허용한 처리 범위와 교집합 검증 |
| B09 TypeSafe 문서 적용 경계 | [Terms](https://typesafe.ai/legal/terms) 서두, [DPA](https://typesafe.ai/legal/data-processing) §1~2 | 사이트 약관과 별도 제품 계약 구분. DPA는 개인정보 처리 범위 | 일반 시세/파생정보 이용권을 DPA가 부여하지 않음. 계정 적용 증거 없이는 `CONDITIONAL/UNVERIFIED` 유지 |

### 5.2 행위별 판단

**C: 아래 판정은 해당 범위에 한정한 구현용 보수적 적용이다.** `CONDITIONAL`도 실행 불가다. “로컬 구현이 존재”와 “그 저장·분석 계약이 검증됨”은 다르다.

| 행위 | KRX OPEN API 원본·파생 | KIS 시세·파생 | OpenDART / FRED / NAVER |
|---|---|---|---|
| 로컬 데이터 조회 | `CONDITIONAL`: B01/B02 승인 상품·비상업 목적·계약 유효성 확인 필요 | `CONDITIONAL`: 개인/제휴 구분과 승인 확인(B04) | 각 제품 승인/조건 별도. 현재 코드 연결만으로 권한 확정 불가 |
| 개인 분석 | `CONDITIONAL`: B01 비상업 범위. 외부 전송 포함 아님 | `CONDITIONAL`: 본인 자산 안내 범위(B04) | 제품·원천별 `UNVERIFIED`; 공개 접근을 포괄 허가로 해석 금지 |
| 로컬 저장 | `UNVERIFIED`: 보존 범위·기간 확인; 계약 종료 후 이용 제한 확인(B01) | `UNVERIFIED`: cache·영구보관 조건 미확보 | A23의 P6 정책 및 A21 뉴스 cache 제한 유지. 정식 보관 grant 별도 |
| 기술지표/파생 계산 | `CONDITIONAL`: 로컬 비상업 적용 범위 확인. B01 면책은 별도 라이선스 아님 | `UNVERIFIED`: 가공 조항 확보 필요 | 별도 원천 계약 확인; 원본을 못 저장하는데 계산 후 폐기하면 된다는 추정 금지 |
| 계산 결과 외부 제공 | `UNVERIFIED`: 조건 문장·순위가 제11조② 정보에 포함되는지 문의 | `UNVERIFIED`: 파생/정보분배 조건 문의 | 세 제품 모두 field/use scope를 확인하기 전 HOLD |
| 외부 AI로 원본 전송 | **`VERIFIED_PROHIBITED`**: B01 제11조②의 제3자 제공 제한 적용 | `UNVERIFIED`: 외부 AI 수탁 처리 예외 확인 안 됨 | 이번 조사에서 `VERIFIED_ALLOWED` 확보 없음 |
| 외부 AI로 조건/Risk/순위 전송 | `UNVERIFIED`: 받은 정보의 파생 범위 및 처리 예외 확인 필요 | `UNVERIFIED` | 뉴스는 A21 내부 정책상 차단. 외부 권리 판단은 별도 |
| 외부 AI 서버 처리 | `UNVERIFIED`: 처리·재위탁 허가 필요 | `UNVERIFIED` | TypeSafe 처리 계약(B08/B09)도 함께 충족해야 함 |
| 외부 서비스 보관 | `UNVERIFIED`: prompt/output/log/hash/backup 모두 범위 확인 | `UNVERIFIED` | 학습 미사용·무료·일회성이라는 사유로 허가하지 않음 |
| 다른 사용자에게 분석 결과 제공 | 원본 재제공은 금지; 파생 결과는 `UNVERIFIED`, 유료화는 B01 제한 별도 적용 | `CONDITIONAL`: 제휴/정보이용계약 안내 범위; 본 프로젝트 충족 여부 미확인 | 출력물/표시/재배포 권리 각각 검증 필요 |

**이번 조사에서 실제 시장 데이터 또는 그 파생 패킷 중 `VERIFIED_ALLOWED`로 확인된 항목은 없다.** 자체 질문·정책·순수 합성 fixture는 외부 시장 권리를 상속하지 않는 후보이나, 작성 권한·정확한 처리 계약·실행 승인을 확인하는 별도 범위다. 데이터 자체의 허용 가능성과 이 실험의 호출 승인을 혼동하지 않는다.

## 6. 데이터 공개·수집·판단 시각 분류

### 6.1 현재 존재하는 필드 — A

| 개념 | 실제 코드/필드 | 증명 가능한 범위와 한계 |
|---|---|---|
| `signal_date` | sample `signal_date`, Snapshot `data_date`; 원천 `BAS_DD/date`(A01/A09/A12) | 거래일, `DATE_ONLY`. 공개 시각·당시 확보를 증명하지 않음 |
| `source_published_at` | S7.3 및 KRX 저장 경로에 없음. 별도 `TemporalEvidence`에는 같은 이름 존재(A23) | 다른 하위시스템의 필드 존재를 Scanner에 있다고 쓰지 않음 |
| `source_available_at` | S7.3 `source.source_available_at`, `evidence[].source_available_at`은 **명시적 null**(A13) | 모든 evidence에 실제 시각 근거 없음 |
| `retrieved_at` | 이 이름의 Scanner 원천 수집 필드 없음 | KRX 캐시 파일 mtime, `verified_at`, API 요청 횟수는 대체 불가 |
| KIS 수신 시각 | REST QuoteSnapshot `received_at=datetime.now(timezone.utc)`, `provider_timestamp=None`(A17) | 시스템 수신 시각은 있음. 원천 공개 시각은 없음; Scanner에 전달되지 않음 |
| KIS WS 체결 시각 | `quotes/websocket_parser.py::_provider_timestamp`(123)가 `BSOP_DATE + STCK_CNTG_HOUR`를 KST-aware로 구성. `websocket_manager.py`(348~)가 provider_timestamp와 UTC received_at을 별도 저장 | 제공된 **체결 시각**과 시스템 수신 시각을 구분할 수 있음. 원천의 최초 공개 시각·개별 이용권 증거로 자동 승격 불가. REST에는 이 체결 시각이 없으므로 경로별로 다르게 처리 |
| `known_to_system_at` | S7.3 `source.known_to_system_at = capture.completed_at`(A13) | Capture 최종화 기록의 별칭. 원천 최초 수집 시각으로 해석 금지 |
| `capture_completed_at` | 정확한 이름의 S7.3 필드는 없음. 원본 capture `completed_at` 재사용 가능(A09) | 기본은 UTC-aware `_now()`. 값은 `finalize_capture` 시작 시 결정되므로 DB commit 직후의 정밀 실측 완료 시각도 아님. 주입 값 검증 필요 |
| `jev_decision_at` | S7.3 로컬 패킷에 없음; 실제 provider 실행도 없음 | 연구 preflight 저장 시각 또는 합성 trial 완료 시각을 실제 시장 JEV 판단 시각으로 대체 금지 |
| 기타 | Scanner `generated_at`, 무결성 `verified_at`은 naive `datetime.now()`(A03); KRX 변동 날짜 판단은 `market/kst.py::today_kst` | 프로젝트 전체 TZ 일관성 미충족. offset 없는 과거 시각을 임의 KST/UTC로 해석하지 않음 |

### 6.2 검증 규칙 — C

기존 A23의 `EXACT / PROVIDER_TIME / DATE_ONLY / INFERRED / UNKNOWN` 명칭과 aware ISO-8601 파서를 재사용한다. 단일 quality로 모든 시각을 승인하지 말고 **시간 필드마다 값·quality·evidence_ref·의미 범위**를 붙인다.

| 신뢰도 | 허용 증거 | 부여하면 안 되는 증거/판정 |
|---|---|---|
| `EXACT` | 해당 데이터 revision에 결합된 공개/이용 가능 시각 원문, 또는 시스템의 실제 수신·확보 로그를 그 의미 범위에서 검증 | 정확한 수집 시각이 있어도 공개 시각을 EXACT로 승격 불가 |
| `PROVIDER_TIME` | 제공자가 기록한 타임존 포함 시각, endpoint·응답/공시 revision과 연결 | 일괄 업데이트 안내·홈페이지 수정일만으로 개별 행의 공개 시각 승인 불가 |
| `DATE_ONLY` | 거래일/공시 접수일만 존재 | 자정·장마감·익일 08:00/13:00 등을 임의 보충 금지 |
| `INFERRED` | 운영 일정으로 추정한 범위, 또는 Capture 시각을 원천 확보의 대리값으로 사용 | exact gate 통과 불가. 추정 사유와 범위를 보존 |
| `UNKNOWN` | 누락, naive 시간의 TZ 불명, 원천/revision 결합 실패 | HOLD |

- **KRX 공개 시간:** 이번에 읽은 해당 OPEN API 공식 상품 본문에서 각 거래일의 정확한 공개 시각은 확보하지 못했다. 다른 분배상품의 EOD 안내(B03), 타 제공처의 갱신 시각, 장마감 시간을 대입하지 않는다. 공식 갱신 일정이 확보되어도 개별 지연·정정·최초 확보를 증명하는 로그는 별도로 필요하다.
- **과거 EOD 재현:** 날짜 절단(A04)은 미래 날짜 사용을 제한하지만, 최근에 수정된 과거 행의 이전 revision·공개 시각·당시 확보 이력을 복원하지 못한다. A02 upsert/replace는 행을 갱신할 수 있다. 현재 DB로 계산이 재현된다는 사실을 과거 시점 재현 증명으로 승격하지 않는다.
- **최신 정보 혼입:** S7은 동결 Snapshot을 읽는다. 보충한다고 최신 KIS 현재가, OpenDART 현재 회사정보, 최신 선택 정책/의미 매핑을 끼워 넣지 않는다. A20의 `STATIC_CURRENT` 차단을 유지한다. 별도 `MarketDataService.stock_context`는 공시 기간을 `date.today()` 기준으로 잡는 경로이므로 과거 입력 대용으로 사용 금지(A19).
- **시간 순서:** 같은 데이터 revision에서 검증된 값만 비교한다. 공개시각 ≤ 해당 상품 가용시각 ≤ 수집완료 ≤ 시스템 원천확보 ≤ 파생 계산완료 ≤ Capture commit 기록 ≤ 실제 JEV 판단완료. 네트워크 요청 시작은 수집완료와 분리한다. unknown은 순서 통과가 아니다. 과거 캐시 재조회는 최초 확보를 덮어쓰지 않는다. 정정 revision은 새 node로 새 시각을 갖는다.
- **TZ:** 순간 비교는 aware 시각을 UTC로 정규화하고 원래 offset/의미를 보존한다. 한국 거래일과 비교할 때는 Asia/Seoul로 변환한다. A13 `_historical_capture_status`는 현재 `completed.date() > signal`만 비교하며 KST 변환이 없다. UTC 날짜 경계 오분류와 당일 Capture의 순서 미확인을 회귀 시험에 포함한다.
- **사전/사후:** `FORWARD_ASOF`는 별도 사전 고정 cutoff와 입력확보 증거가 모두 필요하다. `signal_date`와 같은 날이라고 사전 판단이 아니다. 뒤늦게 실행한 실제 JEV는 `RETROSPECTIVE_CAPTURE/RETROSPECTIVE_REVIEW` 계열로 분리하며 당시 실시간 성능에 넣지 않는다. 사후 연구도 전송 권한·시점 gate를 면제하지 않는다.

## 7. JEV 입력 필드별 외부 전송 적격성

**대상은 A13 `_local_packet`의 `packet`이다.** prepared 결과의 `identity`, S3 offline 입력(A14), 일반 TypeSafe 요청(A15)은 서로 다른 객체다. 아래에서 코드 출처는 A, 분류·권한·조치는 C이며 공식 제한 근거는 B 번호로 표시한다.

약어: `RAW=EXTERNAL_RAW`, `DER=EXTERNAL_DERIVED`, `POL=INTERNAL_POLICY`, `DEC=INTERNAL_DECISION`, `META=PROVENANCE_METADATA`, `UNK=UNKNOWN_ORIGIN`. `U=UNVERIFIED`, `P=VERIFIED_PROHIBITED`, `CND=CONDITIONAL`; 이 표에 자동 호출 허용 행은 없다. `T0=UNKNOWN`, `TD=DATE_ONLY`, `TC=Capture 기록(공개/최초 확보는 INFERRED)`, `TN=시장 공개 시각 비대상인 정의/상수, 정의·생성시각은 별도 검증`이다. KRX라고 표시한 행도 **설계된 경로의 제공자**일 뿐, 실제 행 계보가 없으면 leaf는 UNK다.

| 필드 | 실제 코드 출처 | 원천 제공처 | 데이터 유형 | 가공 관계 | 외부 전송 권한 | 시점 신뢰도 | 근거 | 구현 조치 |
|---|---|---|---|---|---|---|---|---|
| `version` | A13 `PACKET_VERSION` | 내부 | POL | 스키마 상수 | CND | TN | A13/B08 | 내부 작성·처리 범위 승인, 정확한 버전 바인딩 |
| `review_scope` | A13 `SCOPE` | 내부 | POL | 로컬 전용 scope | CND | TN | A13 | 문구 변경으로 호출 허가 금지 |
| `question_hash` | A13 `QUESTION_HASH` | 내부 | META(POL) | QUESTIONS digest | CND | TN | A13/B08 | 질문 원문·버전과 대조 |
| `source.capture_id` | A09 → A13 | 내부 Capture | META | 특정 후보군 식별 | U | TC | A09/B08 | 로컬 보존 기본; 외부 필요성·연결 가능성 검사 |
| `source.sample_index` | A09 → A13 | 내부 Capture | META | 원본 저장 순번 | U | TC | A09/A13 | rank와 혼동 금지 |
| `source.snapshot_hash` | A09 `digest_json(snapshot)` | 내부 + KRX 계보 | META(DER) | 가격·종목 식별자를 포함할 수 있는 전체 snapshot digest | U | TC/TD | A09/B01/B08 | hash 면제 금지, 원본 결합·계약 범위 검증 |
| `source.scanner_version` | capture → A13 | 내부 | POL/META | 생성 엔진 신원 | CND | TN/TC | A03/A13 | 정의 버전·실행 결합 검증 |
| `source.signal_date` | sample → A13 | KRX 거래일 | META(RAW) | 원천 기준일 | U | TD | A01/A09 | 시각 보충 금지 |
| `source.known_to_system_at` | capture `completed_at` → A13 | 내부 기록 | META | 완료시각 별칭 | U | TC | A09/A13 | 최초 확보로 승격 금지; 시간 의미 분리 |
| `source.source_available_at` | A13 명시적 null | 미확인 | META | 없음 | U | T0 | A13 | 원천 revision별 증거 필요 |
| `source.source_time_proof` | A13 미검증 상수 | 내부 | META | 미확인 표시 | CND | T0 | A13 | 문자열만 VERIFIED로 바꾸지 않음 |
| `baseline.strategy` | sample strategy | 내부 규칙 + KRX | DEC | 특정 후보에 선택된 전략 | U | TD/TC | A03/A05/B01 | 규칙 정의와 선택 사실 분리 |
| `baseline.entry_action` | A13 `ENTRY_CANDIDATE` | 내부 + KRX | DEC | 후보 자격 확인 후 상수화 | U | TD/TC | A12/A13/B01 | 문자열 상수여도 시장 선택 결과 계보 유지 |
| `baseline.rank` | sample rank, Snapshot `priority.rank` 검증 | 내부 + KRX 모집단 | DEC | 상대 순위 | U | TD/TC | A07/A12/B01 | 모집단·비교 원천까지 폐쇄 검사 |
| `baseline.conditions.passed` | Snapshot conditions | 내부 + KRX | DEC | PASS 수 | U | TD/TC | A06/A13/B01 | 모든 대응 조건 부모 보존 |
| `baseline.conditions.total` | Snapshot conditions | 내부 정의 + 선택 사실 | POL/DEC | 평가한 조건 총수 | U | TN/TC | A05/A13 | 조건 정의 hash와 후보 결합 검사 |
| `baseline.conditions.missing` | Snapshot conditions | 내부 + KRX | DEC | 미충족 수 | U | TD/TC | A06/A13/B01 | 누락=0도 파생 사실 |
| `baseline.risk.status` | Snapshot risk | 내부 + KRX | DEC | RiskPlan/readiness | U | TD/TC | A06/B01 | 가격·정책 부모별 권한 전파 |
| `baseline.risk.warning` | Snapshot risk | 내부 + KRX | DEC | warning boolean | U | TD/TC | A06/B01 | boolean 축약으로 권리 제거 안 됨 |
| `baseline.strategy_identity.origin` | A13 category 분기 | 내부 | META | ORIGINAL/LEGACY_DERIVED | U | TC | A10/A12 | Legacy 제한 유지 |
| `baseline.strategy_identity.original_version` | Snapshot `strategy_version_id` | 내부 정의 | POL/META | 원본 값; Legacy null | CND | TN/TC | A10/A13 | null 소급 채움 금지 |
| `baseline.strategy_identity.original_definition_hash` | Snapshot `strategy_definition_hash` | 내부 정의 | META(POL) | 원본 정의 digest; Legacy null | CND | TN/TC | A10/A13 | 정의 권리 및 hash 대상 확인 |
| `baseline.strategy_identity.derived_version` | semantic strategy; Legacy만 | 내부 정의 + 실제 PASS 검증 | META | 검증된 엔진 유도 ID | U | TC | A10/A13 | 원본 버전으로 오기 금지 |
| `baseline.strategy_identity.derived_definition_hash` | semantic strategy; Legacy만 | 내부 정의 | META(POL) | 유도 정의 digest | U | TN/TC | A10/A13 | 유도 근거·원본 부재 보존 |
| `baseline.strategy_identity.derived_evidence_source` | `semantic_strategy_identity.source` | 내부 감사 | META | 검증 경로 이름 | U | TC | A10/A13 | 시장 제공자 이름으로 사용 금지 |
| `baseline.policy_id` | `semantic_policy_provenance.policy_id` | 내부 정책 | POL/META | 실행 시 pin | CND | TN/TC | A10 | KRX source policy와 다른 namespace |
| `baseline.policy_hash` | 같은 객체 policy_hash | 내부 정책 | META(POL) | 선택 정책 digest | CND | TN/TC | A10 | 데이터 이용권 evidence로 사용 금지 |
| `baseline.horizon_intent` | capture | 사용자/내부 | POL/META | 원본 intent | CND | TC | A16 | Legacy 자동 보충 금지 |
| `baseline.horizon_policy_version` | capture | 내부 | POL/META | 기간 정책 버전 | CND | TN/TC | A16 | 수치 정책 활성 여부 별도 |
| `evidence[].id` | A13 `condition-N`, `risk-1` | 내부 | META | 패킷 내부 ID | U | TC | A13 | 원본 엔진/의미 ID와 로컬 매핑 보존 |
| `evidence[].source` | A13 `SCANNER_ENGINE_DERIVED`/`SCANNER_RISK_DERIVED` | 내부 라벨 | META | 가공 소유자 표시 | U | TN/TC | A13 | KRX 제품·endpoint 증거 아님 |
| `evidence[condition].statement` | `semantic_source_v2.conditions.items[].observed_meaning` | KRX + 내부 의미 사전 | DER/DEC | 실제 PASS 의미 진술 | **U** | TD/TC | A10/A11/B01 | 파생정보 AI 처리 허가 및 원천시간 검증 필수 |
| `evidence[risk-1].statement` | risk status/warning 문자열 | KRX + 내부 Risk | DER/DEC | 두 결과의 문장화 | **U** | TD/TC | A06/A13/B01 | baseline risk와 동일 계보·권한 |
| `evidence[].source_available_at` | A13 null | 미확인 | META | 없음 | U | T0 | A13 | 항목마다 부모시간 증거 |
| `evidence[].source_release_proof` | A13 미검증 상수 | 내부 | META | 공개시간 미확인 | CND | T0 | A13 | 증거 없는 상태 승격 금지 |
| `evidence[].external_transmission_rights` | A13 `UNVERIFIED` | 내부 판정 | META | 권한 상태 선언 | U | TN | A13/B01 | 선언을 권한 근거로 신뢰 금지 |
| `limitations[]` | A13 상수+Legacy 분기 | 내부 | META | 제약 고지 | CND | TN/TC | A13 | 삭제로 허용 상태 만들지 않음 |
| `input_hash` / prepared `packet_hash` | A13 전체 body digest | 내부 + 모든 부모 | META(DER) | 동일값 두 위치 | U | TC | A13/B08 | 별도 hash 2개 생성 불필요; 전체 payload와 결합 |
| 엔진 PASS 원본 항목·`source_condition` | Snapshot `semantic_condition_evidence.items` | 내부 + KRX | DEC/META | 패킷 생성 전 대조 | 현재 미포함; 추가 시 U | TD/TC | A10/A13 | 로컬 sidecar로 증거 보존; provider에 자동 추가 금지 |
| 종목명·코드 | Snapshot `name/code`, sample `name/ticker`, prepared `identity` | KRX 일별 정보 | RAW | 로컬 식별 | **packet에는 현재 미포함**; 원본 추가 시 P | TD/TC | A01/A09/A13/B01 | prepared 전체를 전송하지 않음 |
| 가격·OHLCV·기술지표 수치 | Snapshot current_price/guide, 상류 engine technical | KRX | RAW/DER | 원본/계산 | **현재 미포함**; 원본 P/파생 U | TD | A04/A09/A13/B01 | 의미 문장이 이미 이 자료에 의존함을 유지 |
| 후보 점수·tier·가격 위험가이드·과거 성과 | Scanner/전체 Snapshot | KRX + 내부 | DEC/DER | 선택·설명용 | **현재 미포함**, U | TD/TC | A03/A07/A13 | rank만 포함; S3와 혼동 금지 |
| `source_hash` / semantic `source_snapshot_hash` / capture `source_snapshot_hash` | A11 semantic digest, A09 전체 결과 digest; 다른 JEV 계약에도 source_hash 존재 | 내부 + 원천 부모 | META(DER) | 서로 다른 hash 대상 | **이 이름으로 S7.3 packet에 현재 미포함**, U | TC | A09/A11/A13/A14 | `source.snapshot_hash`와 구별. 로컬 참조 필요성만 설계 |
| `source_published_at`, `retrieved_at`, `capture_completed_at`, `jev_decision_at` | 일부 개념의 다른 필드는 §6 참조 | 원천/내부 | META | 향후 구분 | **이 이름으로 현재 미포함** | T0 | A13/A23 | 증거와 함께 신규/재사용 매핑 |
| `questions`, `model`, `state` | A15 일반/합성 요청에 존재 | 내부/TypeSafe | POL/META | HTTP body | **S7.3 packet에는 현재 미포함** | TN | A13/A15 | 실제 전송 어댑터가 구현됐다고 기술하지 않음 |

## 8. 기존 S7.3 구조와의 연결

**A:** S7.3는 `LOCAL_VALIDATED`와 `LEGACY_LIMITED`에 대해서만 제한적 packet을 만든다. `INVALID`는 LOCAL_HOLD, 비진입 후보는 REFERENCE_ONLY다. prepare는 Snapshot hash/정본 연결을 검사하고 preflight는 항상 `PROVIDER_HOLD`, `eligible_for_real_market_provider=False`, 호출 0을 반환한다. `REAL_MARKET_PROVIDER_ENABLED=False`이며 `S73DisabledActualProvider`도 차단한다.

**A:** 기존 preflight는 evidence의 `external_transmission_rights == VERIFIED_GRANTED`를 비교한다. 이 문자열은 새 분류의 `VERIFIED_ALLOWED`와 다르며, baseline/source의 모든 전송 필드를 심사하는 권한 원장도 아니다. hash는 caller가 본문과 함께 재계산할 수 있으므로 그 자체로 승인 주체의 진위를 인증하지 못한다. 현재의 무조건 차단을 해제하기 위한 충분조건으로 사용할 수 없다.

**A:** 실제 일반 TypeSafe transport는 `POST https://api.typesafe.ai/v1/systemone`에 `{state, questions, model}`만 구성하며 Authorization은 header에 둔다(A15). 합성 micro 경로는 등록 fixture 전체 일치, 질문/모델/별도 승인을 검증하고 `state={synthetic_only, strategy_intent, evidence}`를 보낸다. **S7.3 packet을 이 body로 연결하는 승인된 실제 시장 어댑터는 없다.** S3 `baseline_decision.entry_risk_guide` 등이 S7.3에도 전송된다고 기술하면 틀린다.

**C:** S7.4의 첫 연결점은 `prepare_shadow_candidate` 결과를 읽는 **별도 로컬 eligibility report/sidecar**다. 기존 Snapshot·S7.3 hash는 유지한다. 새로운 계약 버전에서 필드 allowlist와 별도 adapter hash를 정의하고, 오래된 `VERIFIED_GRANTED` 문자열을 무조건 새 허가로 매핑하지 않는다. 권한 원장 검증을 거친 경우에만 명시적 호환 projection을 허용한다. 이번 문서 PR은 어떤 차단도 바꾸지 않는다.

## 9. S7.4에 필요한 최소 코드 계약 — 전체 C

### 9.1 재사용/추가/불필요 구분

| 구분 | 계약 | 처리 |
|---|---|---|
| 재사용 | capture/sample identity, snapshot hash, S7.3 input hash, 선택 정책 pin, 엔진 PASS↔source_condition 검증(A09~A13) | 새로운 ID로 원본을 덮지 않고 참조. 값/버전 변경 시 eligibility 무효화 |
| 제한적 재사용 | A23 `EvidenceTimeQuality`, aware 파싱, 시간 순서 규칙 | 시간 enum을 새로 중복 정의하지 않음. `TemporalEvidence.available_at/fetched_at`은 필수이므로 모르는 과거 시각을 채워 객체를 억지로 생성하지 말고 nullable 조사 record를 앞에 둠 |
| 제한적 재사용 | A23 `EventEvidenceSourcePolicy` capability와 `policy_basis` | 원본/파생 보관·AI 용도 분리를 참고. bool `ai_transform_allowed` 하나를 외부 AI 전송·처리·보관 허가로 대체하지 않음 |
| 신규 | `SourceArtifact`, `LineageNode`, `RightsEvidence`, `TimeEvidence`, `EligibilityReport` | 아래 최소 필드와 불변 증거 참조를 갖는 로컬 계약부터 구현 |
| 추가 불필요 | 기존 hash의 단순 별명 hash, 새 `selection_policy`와 중복되는 데이터 이용권 이름, 실제 종목 이름이 든 또 다른 패킷 복사본 | `selection_policy_id`와 `rights_policy/evidence_ref` namespace만 구분. 인용 전문/원본 응답을 모든 node에 복제하지 않음 |

| 객체 | 최소 필드 및 의미 |
|---|---|
| `SourceArtifact` | `artifact_id`, `source_id`(제공자+제품 식별), `source_product`, `source_endpoint`(키 제거), `origin_type`, `record_key`(시장/거래일/종목/지수), `payload_hash`, `revision_id`, `acquisition_ref`, `source_time_ref`, `rights_evidence_refs[]`. endpoint/product를 모르면 null+UNKNOWN, provider 추측 금지 |
| `LineageNode` | `node_id`, `origin_type`, `derived_from[]`, `transform_id/version/hash`, `value_hash`, `calculated_at`, `field_paths[]`. 시장 leaf 없는 POL/SYNTHETIC도 작성 근거 참조 필요. rank는 모집단 manifest hash 및 부모 node 포함 |
| `RightsEvidence` | `evidence_id`, `provider`, `source_product`, `document_url`, `clause`, `document_version/hash_or_archive_ref`, `checked_at`, `rights_verified_at`, `verifier_ref`, `effective_from/to`, `revocation_ref`, `scope`, `transmission_rights_status`, `conditions[]`, `evidence_status`. scope는 원본/파생·필드·목적·수신자·지역·보관기간·재위탁·재배포를 특정 |
| `TimeEvidence` | `time_evidence_id`, `artifact/revision_ref`, `source_published_at`, `source_available_at`, `request_started_at`, `retrieved_at`(수집완료), `known_to_system_at`(최초 원천 확보), 필드별 `quality/evidence_ref`, `original_timezone`, `correction_ref`. 기존 capture `completed_at`은 `capture_recorded_at` 의미로 참조, 향후 commit 완료 관측은 별도 기록 |
| `EligibilityReport` | `contract_version`, `input_hash`, `outbound_projection_hash`, `lineage_manifest_hash`, `rights_manifest_hash`, `time_manifest_hash`, `checked_at`, `evaluation_mode/cutoff`, `field_verdicts[]`, `eligibility_status`, `eligibility_reason_codes[]`, `execution_status/reason_codes[]`. 아직 wire projection이 없으면 hash=null, 전송 적격 불가 |

권한 evidence 파일/계약서의 위치는 공개 Git 문서일 필요가 없다. 비공개 승인서는 접근 통제된 로컬/조직 보관소 참조와 digest로 결합하고, provider payload에는 evidence 원문·API 키·계약 개인정보를 넣지 않는다. 이 문서의 B URL은 조사 참조이며 immutable 원문 snapshot을 확보했다고 주장하지 않는다.

### 9.2 권한 검증·전파·충돌 규칙

1. 권한을 검사하는 행위를 최소 `LOCAL_READ`, `PERSONAL_ANALYSIS`, `LOCAL_STORE`, `DERIVE`, `DERIVED_DISCLOSURE`, `AI_TRANSMIT`, `AI_PROCESS`, `AI_STORE`, `USER_REDISTRIBUTE`로 나눈다. 각 scope별 네 상태를 평가한다.
2. `VERIFIED_ALLOWED`는 적용 제품·자료 유형·목적·수신자·지역·보관/재위탁이 명시된 유효 근거와 검증 책임자 기록이 있는 경우만. 신청 승인·출처 표기·사용자 동의·API 성공·유료 구매 사실만으로 AI 권한을 만들지 않는다.
3. `VERIFIED_PROHIBITED`는 명시된 제한의 **해당 행위/범위**에만 부여한다. `CONDITIONAL`은 조건 확인 전 호출 차단, `UNVERIFIED`는 자료 부족/범위 불명으로 차단한다. 조건이 충족돼도 승인 원장을 검증한 새 record를 만들어야 하며 자동 bool 전환하지 않는다.
4. 모든 전송 필드의 부모 closure를 검사한다. applicable 금지가 하나라도 있으면 DENIED, 그 외 미확인/미충족 조건이면 HOLD. 상태를 하나로 합쳐 나머지 원천 사유를 잃지 않는다. 원본 금지의 파생 결과 적용 범위가 불명하면 파생 결과를 합법 허용 또는 법적 금지로 단정하지 않고 UNVERIFIED로 둔다.
5. 서로 상충하는 약관/승인서는 우선순위·적용기간·서명 주체를 확인할 때까지 HOLD. 날짜가 최신이라는 이유만으로 자동 승리시키지 않는다. 만료·철회·목적/수신자/모델 처리조건 변경 시 report 무효화 후 재평가한다.
6. hash·숫자 제거·요약·번역·문장화·익명화는 계보 단절 사유가 아니다. 자체 내부 규칙만 남겨 시장 부모가 실제로 없어졌더라도 질문의 평가 목적이 유지되는지 별도 점검한다.

### 9.3 최종 적격성 결정 흐름

```text
동결 원본·hash·S7.1 정합성
  → 전송 후보 JSON Pointer 전수 분류 + 모든 leaf의 실제 origin 증거
  → field × purpose × recipient 권한 증거 + 부모 closure
  → revision별 공개/확보시각 + 평가 cutoff + timezone 검증
  → 남은 조건·Risk 근거의 충분성/Legacy 제한 확인
  → data eligibility (ELIGIBLE / HOLD / DENIED)
별도: Horizon + 모델 고정 + 계정 요금/예산 + 명시적 실행 승인 + 실제 adapter 승인
  → execution status (READY / HOLD)
최종: ELIGIBLE ∧ READY ∧ 현재 payload/증거 hash 일치인 경우만 호출 검토 가능
```

`data eligibility=ELIGIBLE`이어도 실행을 허가하지 않는다. `LEGACY_LIMITED`의 원본 전략 신원 부재는 검증 목적이 그것을 허용하는 별도 사후 프로토콜 없이는 근거 충분성 HOLD다. `RETROSPECTIVE_CAPTURE`를 사전 성과 집계에 넣지 않는다. 최소 조건은 조건별 실제 PASS와 의미 대응, Risk status/warning 및 그 판단 범위, 실행 정책/기간 맥락이다. 필드 제거로 조건 일관성 검토 자체가 성립하지 않으면 `EVIDENCE_INSUFFICIENT`로 로컬 종료한다.

누락·순환 계보, 미분류 필드, 패킷 hash 불일치, 원천 모순, timezone 없음은 예외를 허용 방향으로 삼키지 않는다. 기존 `SOURCE_RIGHTS_UNVERIFIED`, `SOURCE_RELEASE_TIME_UNVERIFIED`를 유지하고, 세부 사유로 `SOURCE_ORIGIN_UNVERIFIED`, `SOURCE_RIGHTS_PROHIBITED`, `RIGHTS_CONDITION_UNMET`, `RIGHTS_SCOPE_MISMATCH`, `RIGHTS_EVIDENCE_EXPIRED`, `LINEAGE_INCOMPLETE`, `LINEAGE_CYCLE`, `UNCLASSIFIED_OUTBOUND_FIELD`, `SOURCE_TIME_INCONSISTENT`, `TIMEZONE_UNVERIFIED`, `REVISION_ASOF_UNPROVEN`, `EVIDENCE_INSUFFICIENT`를 제안한다. 동일 hash 재계산으로 승인되지 않도록 trusted evidence resolver와 전송 직전 결합 검증이 필요하다.

## 10. 미확인 사항 및 추가 확인 대상

| 우선순위·대상 | 확보할 정확한 증거/답변 | 완료 판정 |
|---|---|---|
| P0 KRX 데이터 담당 | 현재 계정의 OPEN API 상품 승인·적용 약관; 조건 PASS 문장, Risk boolean, 후보 순위, 가격 포함 Snapshot hash를 미국 TypeSafe에 보내 처리·저장·telemetry에 사용하는 범위의 서면 답변 | 항목/목적/수신자/기간별 allow/deny 명시. “개인 연구 가능”만으로 완료 아님 |
| P0 수집·DB 관리 | 원천 endpoint·행/revision·응답 digest·실제 수집/확보 로그; 외부 반입 DB의 원본 manifest | 기존 행별 재결합이 가능한 것만 분류. 불가능한 과거 자료는 UNKNOWN/DATE_ONLY 유지 |
| P0 KRX 시점 담당 | 해당 OPEN API별 공개/갱신·정정 정책과 원본 행에 연결 가능한 시각 증거 | EOD 제공 스케줄과 개별 공개·확보 증거를 분리 |
| P1 TypeSafe 계정 담당 | 적용 MCA/주문서, input/output/log/hash/backup의 보관·처리지역·하위처리자·삭제, 계정별 조건 | KRX가 허용한 범위와 모순 없음. 모델/요금 승인은 별도 |
| P1 KIS | 개인 Open API 약관 원문, 거래소 시세 조건, 외부 AI 처리 허용 범위; 실제 연결된 REST/WS별 데이터 권리 | 향후 KIS를 추가할 때 검증. 구형 일봉 경로 존재로 사용권을 주장하지 않음 |
| P2 OpenDART/FRED/NAVER | 데이터 유형/계열/검색 제품별 AI·재제공·보관 근거 | 현재 S7.3 데이터 적격성과 분리. “공공/무료/공개”라는 이유로 대체 허가 불가 |

### 10.1 대체 경로 — C

| 선택지 | 가능한 평가 목적 | 필요한 선행조건 / 현재 판정 |
|---|---|---|
| KRX 별도 데이터 구입·분배 계약(B03) | 기존 OHLCV 기반 Scanner 평가 유지 가능성 | 외부 AI 처리·파생/순위·저장/재위탁 범위를 계약에 명시. **CONDITIONAL**, 체결·데이터 구매 안 함 |
| KIS 또는 다른 시세 제공자 | 동일 지표 계산 가능성은 기술적으로 별개 | 해당 거래소 권리와 처리 계약, point-in-time revision 증거, 지표/종목 coverage 검증까지 필요. KIS로 바꾸기만 하면 허용되는 것은 아님 |
| OpenDART 또는 FRED | 공시/거시 데이터 자체의 별도 질문 | OHLCV·Scanner 조건/Risk를 동등하게 대체하지 못함. 질문·평가 cohort 재설계 및 권리 검증 필요 |
| 자체 규칙/순수 합성 자료 | 질문 스키마·응답 타입·충돌/ABSTAIN·차단 규칙 시험 | 실제 시장 판단 성능 증거가 아님. 실제 데이터 변형을 SYNTHETIC으로 표시 금지. 외부 유료 실행은 별도 승인 |
| 필요한 필드 제외 | 허가된 나머지 증거로 동일한 질문이 성립할 때만 | 모든 남은 부모 권한과 충분성 재검증. 종목코드·가격만 제거하는 우회 불가 |
| 로컬 규칙/로컬 모델 검토 | 외부 전송 없는 정합성·의미 충돌 검사 | 원천의 로컬 이용조건 안에서 수행. 로컬 모델도 외부 telemetry·업로드가 없는 경계 확인; 경제적 유효성은 별도 |

## 11. 구현 우선순위와 검증 테스트

**C: 앞으로의 구현 순서. 이번 PR에서는 테스트 코드를 만들거나 Runtime 실행하지 않는다.**

1. **출처와 계보 결합:** 신규 수집 manifest와 변환 DAG부터 설계·구현하고, 동결 Capture에는 외부 sidecar로만 연결한다. 기존 불명 자료는 실패 상태로 보존한다.
2. **권한 증거 원장:** KRX 파생 데이터 및 TypeSafe 처리 범위의 공식 답변을 받아 scope별 fail-closed 검증을 구현한다. 답변이 금지/미확인인 동안 실제 adapter 구현·활성화는 진행하지 않는다.
3. **시점 증거와 별도 승인 상태:** 신규 수집의 실제 확보 기록·revision을 보존하고 KST/UTC·사전/사후를 분리한다. 데이터 적격성이 검증된 뒤에도 Horizon·모델·계정요금·실행 승인 gate는 독립적으로 남긴다.

| 단계 | 회귀 검증 항목 | 기대 결과 |
|---|---|---|
| 기존 동작 | `backend/tests/test_jev_act2_s7_3_real_preflight.py`, `test_jev_act2_s7_real_scanner_shadow.py`, `test_jev_act2_s7_2_fresh_capture.py`, `test_jev_act1_s1_3_provenance.py`의 관련 사례 | 정상 LOCAL_PACKET_READY/HOLD, snapshot 불변, provider 0, Legacy null 유지 |
| 조건 신원 | 엔진/semantic ID가 달라도 동일 source_condition 1:1; 중복·누락·FAIL·충돌 주입 | 전자는 로컬 준비 가능, 나머지는 거부 |
| 원천 | 동일 행에 다른 제품/endpoint, 수동 반입 DB, 부모 1개 누락, 순환 DAG | origin 추정 없이 HOLD; provenance mismatch 별도 사유 |
| 혼합 원천 | KRX+KIS/OpenDART 부모 중 하나 금지/미확인; rank 모집단 일부 미허가 | 해당 필드 DENIED/HOLD, 전체 원인 보존 |
| 권한 | 개인 조회 허가만 있음; AI 전송 허가 있으나 저장/지역/하위처리자 scope 불일치; 만료·철회·상충 승인 | 호출 불가. `VERIFIED_GRANTED`/`VERIFIED_ALLOWED` 단순 문자열 또는 `ai_allowed=True` 위조도 거부 |
| 완전 분류 | baseline/source/evidence뿐 아니라 새 필드·hash·중첩 문자열 추가; prepared identity 통째 직렬화 | 미분류 필드로 HOLD; 종목 식별자 누출 차단 |
| 시간 | 날짜만 존재, naive 시각, 미래 available, Capture 이전/이후 UTC↔KST 자정, 수집 시작/완료 역전 | exact 승인 금지, 시간 모순 거부; 날짜 경계 회귀 |
| 수정/캐시 | 과거 EOD 정정, 늦은 다운로드, cache hit/replay, 최신 회사정보 또는 KIS 가격 혼입 | 원본 revision/최초 확보 보존; 과거 이용 가능성 재현 실패면 HOLD |
| 사후·충분성 | 신호일 이후 Capture/판단, 원본 전략 ID 부재, 필수 Risk/조건 제거 | 사전 성과 제외, 허용된 사후 프로토콜 없으면 HOLD/불충분 |
| 실행 독립성 | 데이터 증거만 완비, Horizon/모델/요금/동의 중 하나 누락; 승인 후 payload 변경 | 자격 증명/네트워크 접근 전 HOLD. 승인 hash 불일치 거부 |
| 합성 분리 | 실제 후보에 `synthetic_only=True`, 변경된 fixture, 합성 결과를 실제 cohort로 합산 | S5/S6 거부 및 실제 평가 분모 오염 방지 |

문서 검증은 기준 커밋·코드 경로/줄 링크·S7.3 leaf 필드 전수 대조·Markdown 표 구조·문서 한 파일만 변경 여부로 수행한다. 이 검증을 실제 Capture 재현 성공이나 S7.4 구현 테스트 PASS라고 보고하지 않는다.

## 12. 최종 GO / CONDITIONAL / NO-GO 판단

| 범위 | 판정 | 사실 수준·이유 |
|---|---|---|
| 로컬 분류/계보/증거 계약 및 차단 검증 구현 | **GO** | C: 이 문서의 신규 설계 범위. 원천 조회·저장 자체의 계약 문제를 면제하는 승인은 아님 |
| 별도 허가를 받은 미래 데이터·수신 조건으로 외부 평가 | **CONDITIONAL** | C: field별 권리·원천/revision·시간·충분성 및 독립 실행 승인이 모두 필요 |
| 현재 S7.3 실제 시장 packet 외부 TypeSafe 호출 | **NO-GO** | A: 실제 adapter 비활성·항상 HOLD. B01: 원본 제3자 제공 제한. C: 파생정보 AI 범위·개별 계보/공개시각 미확인 |
| 기존 사용자 Capture를 당시 사전 JEV 성과로 평가 | **NO-GO** | C: 사용자 보고가 사후 Capture이며 본 조사에서 원본 미재검증. A: 실제 시장 JEV 호출 경로 없음 |

**S7.4가 우선 해결할 세 문제는 (1) 행·필드별 제품/계보 증거의 부재, (2) 파생정보와 TypeSafe 처리·보관까지 포괄하는 권한 증거의 부재, (3) 원천 공개·최초 확보·수정 revision 시각 증거의 부재다.** 이를 해결해도 `LEGACY_HORIZON_UNDEFINED` 또는 수치 기간 정책, `PINNED_MODEL_AND_BILLING_NOT_VERIFIED`, `EXPLICIT_EXECUTION_APPROVAL_MISSING`, `REAL_MARKET_PROVIDER_NOT_AUTHORIZED`는 별도의 차단이다. 현재 시장 데이터 중 외부 AI 전송을 검증 완료한 자료는 **없다**.
