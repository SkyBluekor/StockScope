# JEV-ACT2-S7.4 데이터 출처·권한 및 시점 분류 기준

## 1. 조사 목적과 범위

**판정: 실제 Scanner 시장 데이터의 TypeSafe 전송은 NO-GO. 로컬 분류·계보·증거 검증 계약 설계는 GO.** `LOCAL_PACKET_READY`는 전송 허가가 아니다. 이 문서는 S7.4 구현 기준이며 구현 완료·권한 승인서가 아니다.

- 조사일: **2026-10-12, Asia/Seoul**. 저장소: `SkyBluekor/StockScope`, 기준 브랜치: `main`.
- 작업 시작 시 `git ls-remote origin refs/heads/main`으로 확인한 HEAD: **`12532ac3b6b35758ac4a471157d3e32fab812368`**. 로컬 HEAD도 동일하며 조사 시작 시 작업 트리는 깨끗했다. 아래 코드 링크는 모두 이 커밋에 고정한다.
- **A = 코드로 확인**, **B = 공식 외부 자료로 확인**, **C = 미확인 또는 설계 제안**. 표에서 `A → C`는 입력·구조는 코드 사실이고 분류·조치는 제안이라는 뜻이다. 권한에 관한 적용 해석은 B 원문과 별도로 C로 표시한다.
- 코드 연결 여부는 확인했지만 사용자 계정의 API 가입·승인 내역, 실행 로그, 원본 응답 또는 Runtime DB를 감사하지 않았다. 따라서 “연결된 경로”는 실제 이번 계정에서 호출했다는 뜻이 아니다.
- 사용자 제공 실환경 보고: Capture `a0f8f2cb-c1ab-4b3a-9488-b125e0369a2b`, 15건 중 진입 1건·참고 14건, 대한항공 `003490`, 신호일 `2026-10-08`, `LEGACY_LIMITED`, `LOCAL_PACKET_READY`, `RETROSPECTIVE_CAPTURE`, `PROVIDER_HOLD`, TypeSafe 0회. **C: 본 조사에서 원본을 재검증하지 않은 사용자 보고**이며 저장소 문서의 과거 기록도 DB 원본을 대신하지 않는다.
- 최초 S7.4 조사에서는 Markdown 한 파일만 추가했고, DOC-R1은 같은 파일만 보완한다. Scanner/JEV 수정, DB 접근·생성·마이그레이션·동기화, Capture 변경, 시장/API 실조회, TypeSafe 호출, 승인 플래그 변경은 수행하지 않는다. 공식 웹 문서 열람과 GitHub 조회·문서 PR은 조사 범위다.
- 기존 [S1.3 검증 문서의 S7.3 기록](../검증/JEV-ACT1-S1.3_정책_출처_및_의미_저장_정합성_검증.md), [JEV 통합 설계](StockScope_JEV_통합설계_v2_2026-10-06.md), [Semantic Source 계약](StockScope_TypeSafe_Jev_V3_Semantic_Source_Contract_v1_2026-10-07.md)과 역할을 구분한다. 이 문서는 **원천 권한·시간·전송 적격성의 단일 기준**이다.
- **DOC-R1 보완(2026-10-12):** [PR #115](https://github.com/SkyBluekor/StockScope/pull/115)의 open/미병합 상태와 당시 head `327a2fc2e5d234012b0436b30dbd5f2575386c23`을 확인한 뒤 같은 브랜치의 이 문서만 수정한다. 기존 A/B 조사 기준은 그대로 두고 §6·8~12의 C 계약을 보완한다. 신규 권한 승인·시점 증거를 확보했다는 의미가 아니다. Runtime DB에는 접근하지 않는다.

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
- **시간 순서:** 원천 수집·Scanner 계산·Capture·JEV 후처리는 서로 다른 이벤트다. Scanner 판단에 쓰인 원천 확보는 해당 입력 고정 이전이어야 하지만, 동결 Capture를 읽는 로컬 패킷 생성은 Capture 이후여도 정상이다. 모든 계산을 Capture 이전으로 강제하지 않는다. 이벤트별 부분 순서와 모드별 gate는 §6.3~6.4를 따른다. unknown은 순서 통과가 아니다.
- **TZ:** 순간 비교는 aware 시각을 UTC로 정규화하고 원래 offset/의미를 보존한다. 한국 거래일과 비교할 때는 Asia/Seoul로 변환한다. A13 `_historical_capture_status`는 현재 `completed.date() > signal`만 비교하며 KST 변환이 없다. UTC 날짜 경계 오분류와 당일 Capture의 순서 미확인을 회귀 시험에 포함한다.
- **사전/사후:** 평가 모드는 `RETROSPECTIVE_RESEARCH`와 `FORWARD_ASOF`로 구분한다. A13의 `RETROSPECTIVE_CAPTURE`는 현재 코드의 시간 진단 라벨이며 평가 모드/실제 모델 판단 시각과 다르다. `signal_date`와 같은 날이라는 이유로 사전 판단으로 승격하지 않는다. 사후 연구도 권한 검증을 면제하지 않으며, 시점 미입증은 보고서에 남긴다.

### 6.3 R1-B 단계별 시간 이벤트 계약 — 현재 필드는 A, 요구 증거·판정은 C

아래 신규 시각은 S7.4 제안이며 이미 저장되는 필드로 간주하지 않는다. §9.1의 `TimeEvidence.events[]`에 이벤트 종류·대상 hash/revision·시각·quality·증거 참조를 함께 기록한다. 정확한 값이 없으면 null이며, 이벤트 종류나 로그의 존재만으로 `EXACT`가 되지 않는다.

| 이벤트 / 의미 | 현재 필드·코드 근거(A) | 필요한 증거와 신뢰 수준(C) |
|---|---|---|
| 원천 공개 / 발행자가 처음 공개한 순간 | KRX 경로 없음; A23에만 `source_published_at` 계약 존재 | 해당 원문·revision에 결합된 발행 기록. 확보 전 UNKNOWN/DATE_ONLY; 제공자 시각은 PROVIDER_TIME, 의미·진위까지 검증한 경우만 그 범위에서 EXACT |
| 특정 revision 가용 / 해당 API 제품·이용 목적에서 제공되기 시작한 순간 | A13 `source_available_at=null` | 제품·revision·승인 범위에 결합된 가용 기록. 원천 첫 공개와 이후 수정본 공개를 혼동하지 않음 |
| 원천 요청·응답 / 네트워크 요청 시작과 유효 응답 수신 완료 | KRX에는 영속 이벤트 필드 없음; KIS REST `received_at`은 별도 경로(A17) | `request_started_at` ≤ `retrieved_at`, 요청/응답 식별·상태·payload hash. 오류/빈 응답을 시장 행 확보로 기록하지 않음 |
| StockScope 최초 확보 / 동일 revision을 이 시스템이 처음 유효하게 확보한 순간 | A13 `known_to_system_at`은 Capture 완료값의 별칭이며 이 이벤트를 증명하지 못함 | 해당 시스템·revision의 최초 성공 수집/검증 로그. 최초 수신과 검증완료가 다르면 후자를 `known_to_system_at`, 전자를 `retrieved_at`으로 보존. 재수집과 분리 |
| Scanner 입력 고정 / 정확히 어떤 행·정책을 사용할지 고정 | A03 `_build_input_fingerprint`, A09 `input_fingerprint`는 있지만 고정 순간을 입증하는 전용 시각 없음 | `scanner_input_frozen_at`, 입력 manifest/hash, 정책 pin 및 실제 소비 revision. 사후 계산한 fingerprint만으로 당시 고정 입증 불가 |
| Scanner 판단 / 고정 입력으로 전략·Risk·추천 결과 계산 | A03 결과 `generated_at`은 naive; capture `started_at`은 Scanner 판단 시작의 대체값 아님 | `scanner_decision_started_at/finished_at`, input/result hash와 실행 버전. 원래 TZ 근거 없는 generated_at은 UNKNOWN으로 유지 |
| Prospective Capture 기록 / 결과·의미 투영의 저장 시도와 commit | A09 `completed_at`은 최종화 시작 시 기본 생성, sample `created_at`도 같은 now; `conn.commit()` 뒤 별도 실측 시각 없음 | 기존값은 `capture_recorded_at` 의미로만 참조. 원래 필드명·생성 위치도 보존. 향후 `capture_commit_observed_at`은 commit 성공 뒤 실제 관측한 경우만 기록; 미측정이면 null |
| JEV 로컬 패킷 생성 / 동결 Snapshot의 허용된 후처리 | A13 `_local_packet`의 `input_hash`는 존재, 패킷 생성 시각 없음; preflight journal `created_at`은 다른 이벤트 | `local_packet_built_at`, 원본 snapshot hash·adapter 버전·packet hash. Capture를 읽은 뒤 생성 가능하며 원본 Scanner 판단 시각을 변경하지 않음 |
| 실제 JEV 요청·응답 / 전송 시작과 응답 수신, 응답 검증 | A13 실제 시장 호출 없음. A15 HTTP 구현 존재가 이 이벤트의 실측 증거는 아님 | 향후 `jev_request_started_at`, `jev_response_received_at`, `jev_response_validated_at`, body/response hash·provider/model 신원. 타임아웃은 응답 시각/판단 성공을 만들지 않음. `jev_decision_at`은 유효 응답을 확보·검증한 마지막 이벤트에만 대응 |
| 후속 시장 결과 관찰 / 결과 거래일과 시스템이 결과를 본 순간 | A12 `_observation`(121)의 `evaluated_through`, S7 journal `observed_through/created_at`은 범위·연구 저장값 | `outcome_event_at`(또는 DATE_ONLY), `outcome_first_observed_at`, 관찰 구간/revision·결과 hash를 별도 기록. 저장/보고 시각은 최초 관찰의 대체가 아님 |

**C: revision별 증거 결합 조건.** 원천 node는 `(source_id, product, record_key, revision_id, payload_hash)`와 성공 acquisition을 결합한다. 제공자 revision ID가 없으면 로컬 관측 버전을 발급하되 `revision_id_kind=LOCAL_OBSERVATION`으로 표시하고 제공자 발행 순서/정정 시점을 안다고 주장하지 않는다. 서로 다른 payload는 거래일이 같아도 다른 버전이며, 늦게 받은 수정본에 예전 확보 시각을 상속하지 않는다. Cache hit는 기존 acquisition을 참조할 뿐 최초 확보를 갱신하지 않는다. 최초 로그가 없는 legacy cache는 UNKNOWN을 유지한다. 빈 응답·실패·동일 payload 재수집은 요청 이벤트만 추가하며 허위 최초확보를 생성하지 않는다.

시간 순서는 **같은 revision의 첫 유효 획득**에 대해 `published ≤ available ≤ retrieved ≤ known`을 검증하고, Scanner의 모든 소비 부모에 대해 `known ≤ scanner_input_frozen ≤ scanner_decision_started ≤ scanner_decision_finished`를 검증한다. 재수집의 retrieved는 최초 known보다 늦을 수 있다. 동결 결과 저장/읽기와 패킷 생성의 인과관계는 별도 이벤트로 검증한다. `completed_at`을 commit 관측값으로 넣어 이 순서를 억지로 만족시키지 않는다.

### 6.4 R1-B 평가 모드별 시간 gate — C

`evaluation_mode`는 실행 전에 프로토콜에 명시하며 현재 라벨로 추론하지 않는다. 데이터 cutoff는 **정보 사용 경계**, decision deadline은 **모델 판단 완료 경계**로 구별한다. 아래 조건은 향후 검증기의 계약이며 현재 실제 전송은 어느 모드에서도 비활성이다.

| 검사 | `RETROSPECTIVE_RESEARCH` | `FORWARD_ASOF` |
|---|---|---|
| 목적·분모 | 과거 동결 후보를 현재 검토. 과거 시점 JEV 성능 분모에 절대 포함하지 않음 | 사전 등록한 입력/판단/관찰 구간의 cohort만 포함. 사후 라벨 변경으로 편입 금지 |
| 프로토콜 경계 | 원본 신호 거래일과 현재 연구·패킷·판단 시각을 별도 기록. 옛 평가 cutoff를 사후 생성하지 않음 | `protocol_frozen_at`, `data_cutoff_at`, `decision_deadline_at`, `outcome_window_start_at`을 사전 고정. `protocol_frozen ≤ data_cutoff ≤ decision_deadline < outcome_window_start` |
| 원천 revision | Snapshot에 결합된 원래 입력만 사용. 과거 공개/확보가 입증되지 않으면 `REVISION_ASOF_UNPROVEN` 유지. 로컬 진단은 가능하나 그 상태로 외부 ELIGIBLE 판정 불가 | 사용한 모든 revision의 공개/가용/최초 확보가 입증되고 `known ≤ scanner_input_frozen ≤ data_cutoff`. cutoff 뒤 수정본·현재가·외부 검색·새 시장 사실 유입은 거부 |
| Capture 이후 계산 | Capture 읽기 → 고정 의미/정책 참조에 의한 packet projection은 정상. 미래 정보가 들어간 새 의미 진술·정책으로 원본을 재해석하면 별도 연구 input/version이며 기존 승인 재사용 금지 | 고정 입력으로 Scanner 계산·Capture·packet 생성이 cutoff 뒤라도 decision deadline 이전이면 가능. 모든 변환/질문 버전은 프로토콜에 고정하고 시장 정보 재조회 금지 |
| 실제 판단 | 현재 요청/유효 응답 시각을 기록. 과거 신호일에 판단했다고 표시하지 않음 | `capture commit 증거 → 동결 Capture 읽기 → packet 생성 ≤ request 시작 ≤ response 수신 ≤ response 검증 ≤ decision_deadline`. 현재 completed_at만으로 commit 시각 증명 불가 |
| 결과 관찰 | 기존 S7 관찰 결과는 별도 outcome channel. 입력/정답에 섞인 경우 오염을 표시하고 독립 성능 주장 금지 | 실제 판단 고정 전 결과 관찰 접근 차단. `response 검증 < outcome_first_observed_at`과 사전 outcome 구간을 모두 입증. “나중에 DB에 기록”만으로 미관찰 증명 불가 |
| 변경·재시도 | input/질문/권한/변환 변경은 새 연구 revision·report 필요 | 결과를 본 후 선택·재시도·판단 변경 금지. deadline 초과/응답 실패는 실패 cohort로 보존, 유리한 응답만 선택 금지 |
| 미확인 시간·권한 | 사후 로컬 보고에 누락 사유 표시; 권한·필요 시각 증거를 면제하지 않고 provider HOLD | 미입증은 forward 부적격/HOLD. 실제 clock 오차·순서 불확실도 거부 |

두 모드 모두 naive datetime은 비교 전에 차단한다. UTC `2026-10-08T15:30:00Z`가 KST `2026-10-09`라는 날짜 경계, 장마감 이후 지연 공개, 첫 확보와 재수집, 과거 EOD 정정, Cache hit, 요청 시작/응답 완료를 각각 검증한다. `source_available_at`이 데이터 공개를 뜻하는지 계약상 이용 가능을 뜻하는지도 evidence에 명시하고, 어느 하나가 충족됐다고 다른 조건까지 승인하지 않는다. 누락된 실제 이벤트는 정밀 시각 대신 검증 가능한 인과 로그를 기록할 수 있지만, 그것으로 알 수 없는 cutoff 전후 관계를 통과시키지 않는다.

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

**C:** S7.4의 첫 코드 연결점은 `prepare_shadow_candidate` 결과를 읽는 **별도 로컬 진단 report/sidecar**다. 착수 순서는 §11의 P0 권한 확인이 먼저다. 기존 Snapshot·S7.3 hash는 유지한다. 새로운 계약 버전에서 필드 allowlist와 별도 outbound hash를 정의하고, 오래된 `VERIFIED_GRANTED` 문자열을 무조건 새 허가로 매핑하지 않는다. 검증된 증거를 참조한 경우에만 명시적 호환 projection을 허용한다. 이번 문서 PR은 어떤 차단도 바꾸지 않는다.

### 8.1 R1-C 로컬 packet과 미래 전송 전용 body의 경계 — C

로컬 packet은 원본 대조·계보 진단용이고 외부 전송 허가서가 아니다. 미래 전송 body는 정확히 `{state, questions, model}`의 세 최상위 키만 갖는 별도 projection이다. `prepared`, `prepared.identity`, `source`, 로컬 진단/권한 문서 전체를 직렬화하지 않는다. §7의 필드 표는 현재 packet의 전수 목록이며 전송 allowlist 자체는 아니다.

최소 검토 목적은 **조건 PASS 의미와 Risk 설명의 일관성**으로 한정한다. 그 목적에 대한 최초 allowlist 후보는 아래와 같다. 실제 채택에는 §9의 권한·시점·충분성 검증과 계약 버전 고정이 필요하며, 아래 목록에 있다는 이유로 현재 허용된 것은 아니다.

| 최종 body 경로 | 허용 후보·제약 | 로컬에만 남길 정보 |
|---|---|---|
| `/state/baseline` | `strategy`, `entry_action`, `conditions.{passed,total,missing}`, `risk.{status,warning}`, `horizon_intent`, `horizon_policy_version`만. 각각 타입/enum/nullable 여부를 고정하고 시장 파생 여부는 §7대로 심사 | rank·모집단, 전략 정본 식별/hash, policy ID/hash 등 검증용 연결. 순위 비교나 원본 전략 재현이 질문에 필요하면 이 최소 목적에는 불충분으로 HOLD |
| `/state/evidence/*` | `id`, `statement`만. 각 원소와 문자열의 원천 부모·정해진 생성 규칙을 확인. 임의 문자열 덧붙임 금지 | 원문, 원천 endpoint, 시각/권한 증거 참조와 조사 주석 |
| `/questions` | 해당 목적의 질문 계약에 정의된 키·배열·타입·문자열을 재귀적으로 열거하고 정확한 내용/버전/hash 고정. 자유 확장 키 없음 | 다른 실험의 질문·추가 시장 맥락 |
| `/model` | 승인된 정확한 model ID 문자열. transport에 설정된 실제 ID와 동일해야 함 | 계정/API 키/과금 증거 |

위 중첩 키 이외의 `state` 필드, 모든 객체의 미등록 키, 배열 원소의 추가 필드, 알 수 없는 타입은 차단한다. 질문의 구체적 전체 스키마가 고정되지 않은 초안은 아직 전송 적격이 아니다. 누락 허용과 null 허용도 별도로 고정하며, 필수 근거를 삭제해서 통과시키지 않는다. 제거 후 동일한 질문이 성립하지 않으면 `EVIDENCE_INSUFFICIENT`다.

종목명·종목코드는 기본 전송 제외이며 식별용 hash/별칭으로 자동 치환하여 보내지 않는다. **KIS 개인 계좌, 잔고, 보유 수량, 계좌 식별자 및 토큰·키·인증 정보는 명시적 전송 금지**다. 이는 향후 경로 결합에 대한 제외 규칙이며 현재 S7.3 packet에 계좌정보가 있다는 주장이 아니다. 입력 선택부터 시장 데이터 경로와 개인 계좌 경로를 분리하고 값의 계보를 검사한다. 허용 키의 `statement`, 질문 문자열 등에 포함된 식별자·민감 값도 금지하며 키 이름 필터만으로 통과시키지 않는다. 출처가 불명한 자유 문장/인코딩 값은 HOLD, 민감 원천을 가진 값은 제외 후 충분성을 재검사한다. 금지어/패턴 검사는 보조 수단이며 allowlist·계보 검사를 대체하지 않는다.

## 9. S7.4에 필요한 최소 코드 계약 — 전체 C

### 9.1 재사용/추가/불필요 구분

| 구분 | 계약 | 처리 |
|---|---|---|
| 재사용 | capture/sample identity, snapshot hash, S7.3 input hash, 선택 정책 pin, 엔진 PASS↔source_condition 검증(A09~A13) | 새로운 ID로 원본을 덮지 않고 참조. 값/버전 변경 시 eligibility 무효화 |
| 제한적 재사용 | A23 `EvidenceTimeQuality`, aware 파싱, 시간 순서 규칙 | 시간 enum을 새로 중복 정의하지 않음. `TemporalEvidence.available_at/fetched_at`은 필수이므로 모르는 과거 시각을 채워 객체를 억지로 생성하지 말고 nullable 조사 record를 앞에 둠 |
| 제한적 재사용 | A23 `EventEvidenceSourcePolicy` capability와 `policy_basis` | 원본/파생 보관·AI 용도 분리를 참고. bool `ai_transform_allowed` 하나를 외부 AI 전송·처리·보관 허가로 대체하지 않음 |
| 논리 계약 후보 | `SourceArtifact`, `LineageNode`, `RightsEvidence`, `TimeEvidence`, `EligibilityReport` | 다섯 개 DB/서비스의 선행 구축 요구가 아님. §11의 단계에서 필요한 참조/부분 record만 로컬 진단 결과에 담고, 증거 없는 필드는 null+사유. 기존 원본 불변 |
| 추가 불필요 | 기존 hash의 단순 별명 hash, 새 `selection_policy`와 중복되는 데이터 이용권 이름, 실제 종목 이름이 든 또 다른 패킷 복사본 | `selection_policy_id`와 `rights_policy/evidence_ref` namespace만 구분. 인용 전문/원본 응답을 모든 node에 복제하지 않음 |

| 객체 | 최소 필드 및 의미 |
|---|---|
| `SourceArtifact` | `artifact_id`, `source_id`(제공자+제품 식별), `source_product`, `source_endpoint`(키 제거), `origin_type`, `record_key`(시장/거래일/종목/지수), `payload_hash`, `revision_id`, `acquisition_ref`, `source_time_ref`, `rights_evidence_refs[]`. endpoint/product를 모르면 null+UNKNOWN, provider 추측 금지 |
| `LineageNode` | `node_id`, `origin_type`, `derived_from[]`, `transform_id/version/hash`, `value_hash`, `calculated_at`, `field_paths[]`. 시장 leaf 없는 POL/SYNTHETIC도 작성 근거 참조 필요. rank는 모집단 manifest hash 및 부모 node 포함 |
| `RightsEvidence` | 기존 `evidence_id`, `provider`, `source_product`, `document_url`, `clause`, `document_version/hash_or_archive_ref`, `checked_at`, `rights_verified_at`, `verifier_ref`, `effective_from/to`, `revocation_ref`, `scope`, `transmission_rights_status`, `conditions[]`, `evidence_status` 재사용. `roles.{rightsholder_ref,issuer_ref,collector_ref,verifier_ref,consumer_ref}`, `authority_basis_ref`, `authenticity_checks[]`, `applicable_party_ref`, `supersedes/conflict_refs[]`, `decision_basis_refs[]`, `bound_subject_hash`를 같은 record에 추가하는 C안. scope는 행위·제품·원본/파생·필드·목적·수신자·지역·보관/로그·재위탁·재배포 특정; 역할/진위/검증 결과를 모르면 미확인 |
| `TimeEvidence` | `time_evidence_id`, `artifact/revision_ref`, `source_published_at`, `source_available_at`, `request_started_at`, `retrieved_at`(수집완료), `known_to_system_at`(최초 원천 확보), 필드별 `quality/evidence_ref`, `original_timezone`, `correction_ref`; §6.3의 `events[]`로 Scanner·Capture·packet·요청/응답·결과 이벤트를 구분. 기존 `completed_at`은 생성 위치의 의미만 보존하고 commit 관측이나 최초 확보로 승격 금지 |
| `EligibilityReport` | `contract_version`, `input_hash`, `outbound_projection_hash`, `lineage_manifest_hash`, `rights_manifest_hash`, `time_manifest_hash`, `checked_at`, `evaluation_mode/cutoff`, `field_verdicts[]`, `eligibility_status/reason_codes[]`, `execution_status/reason_codes[]` 재사용. `canonicalization_version`, `allowlist_version/hash`, `request_purpose`, `recipient/processing_scope`, `question_hash`, `model_id`, `protocol_hash`, `decision_deadline`, `bound_subject_hash`, `execution_approval_ref`, `invalidated_at/reasons[]`를 필요 단계에 추가. 아직 최종 body가 없으면 outbound hash=null, 전송 적격 불가 |

권한 evidence 파일/계약서의 위치는 공개 Git 문서일 필요가 없다. 비공개 승인서는 접근 통제된 로컬/조직 보관소 참조와 digest로 결합하고, provider payload에는 evidence 원문·API 키·계약 개인정보를 넣지 않는다. 이 문서의 B URL은 조사 참조이며 immutable 원문 snapshot을 확보했다고 주장하지 않는다.

### 9.2 권한 검증·전파·충돌 규칙

§5·§7에 보존한 `CONDITIONAL/CND`는 조사 단계의 조건부 검토 대상으로, 실제 계정의 증거 검증 완료 상태가 아니다. 실행용 RightsEvidence로 옮길 때에는 아래 기준으로 다시 판정하며, 진위·적용 범위가 미확인인 기존 항목은 UNVERIFIED에서 시작한다. §12의 CONDITIONAL은 사업/구현 단계의 진행 조건이지 데이터 권한 상태가 아니다.

1. 권한을 검사하는 행위를 최소 `LOCAL_READ`, `PERSONAL_ANALYSIS`, `LOCAL_STORE`, `DERIVE`, `DERIVED_DISCLOSURE`, `AI_TRANSMIT`, `AI_PROCESS`, `AI_STORE`, `USER_REDISTRIBUTE`로 나눈다. 각 scope별 네 상태를 평가한다.
2. `VERIFIED_ALLOWED`는 적용 제품·자료 유형·목적·수신자·지역·보관/재위탁이 명시된 유효 근거와 검증 책임자 기록이 있는 경우만. 신청 승인·출처 표기·사용자 동의·API 성공·유료 구매 사실만으로 AI 권한을 만들지 않는다.
3. `VERIFIED_PROHIBITED`는 명시된 제한의 **해당 행위/범위**에만 부여한다. `CONDITIONAL`은 진위·적용 범위를 확인한 근거에 명시된 조건이 아직 미충족인 경우다. `UNVERIFIED`는 자료 부족/진위·범위 불명이다. 둘 다 호출 차단이며 계약 체결 가능성만 있는 대안은 검증된 조건부 권한이 아니다. 조건이 충족돼도 새 검증 이력을 기록하며 자동 bool 전환하지 않는다.
4. 모든 전송 필드의 부모 closure를 검사한다. applicable 금지가 하나라도 있으면 DENIED, 그 외 미확인/미충족 조건이면 HOLD. 상태를 하나로 합쳐 나머지 원천 사유를 잃지 않는다. 원본 금지의 파생 결과 적용 범위가 불명하면 파생 결과를 합법 허용 또는 법적 금지로 단정하지 않고 UNVERIFIED로 둔다.
5. 서로 상충하는 약관/승인서는 우선순위·적용기간·서명 주체를 확인할 때까지 HOLD. 날짜가 최신이라는 이유만으로 자동 승리시키지 않는다. 만료·철회·목적/수신자/모델 처리조건 변경 시 report 무효화 후 재평가한다.
6. hash·숫자 제거·요약·번역·문장화·익명화는 계보 단절 사유가 아니다. 자체 내부 규칙만 남겨 시장 부모가 실제로 없어졌더라도 질문의 평가 목적이 유지되는지 별도 점검한다.

### 9.2.1 R1-A 역할과 신뢰 경계

| 역할 | 확인할 근거와 책임 | 확인되지 않은 경우 |
|---|---|---|
| 권리자/계약상 부여 권한자 | 원천 권리 및 해당 파생·AI 행위를 허가할 권한의 근거. 중개 제공자는 원권리자의 위임/재허가 범위까지 확인 | API 운영자라는 이유로 권한을 추정하지 않음 |
| 실제 발급 주체 | 약관 공표 주체, 계약 상대/서명자, 서면 허가 발급자; 공식 경로·서명/발급 기록 및 필요한 위임 관계 | 출처 불명 첨부 파일·이메일 텍스트만으로 진위 확정 불가 |
| 증거 수집 주체 | 누가 언제 어디서 어떤 원문/버전을 확보했는지와 보관 참조를 기록 | 수집자에게 이용권을 부여하는 권한이 생기지 않음 |
| 진위·적용 범위 검증 주체 | 확인된 검증 책임/권한, 검증 방법·근거·시점과 RA01~RA10 결과를 기록. 데이터 권한자는 아니며 근거를 적용해 판정 | 실제 지정/신원이 없으면 `verifier_ref=null`, 승인 불가 |
| 검증 결과 사용 시스템 | 신뢰된 보관소/resolver에서 증거 버전·검증자 권한·현재 유효 상태를 확인하고 대상 요청과 대조 | caller가 보낸 status·verifier 이름·hash를 신뢰 경계 안으로 자동 수용하지 않음 |

동일 주체가 여러 역할을 맡을 수는 있으나 각 역할의 근거를 별도로 남긴다. 이 문서는 특정 개인/조직을 실제 검증자로 지정하지 않으며 현재 사용자 계약·별도 승인서의 진위 검증이 끝났다는 뜻도 아니다. 신뢰된 보관소는 별도 대규모 서비스가 필수라는 뜻이 아니다. 초기에는 접근 통제된 증거 파일과 검증 이력으로 시작할 수 있으나, caller의 임의 JSON으로 그 내용을 교체할 수 없어야 한다.

### 9.2.2 R1-A `VERIFIED_ALLOWED` 검증 조건표

각 적용 행위별로 아래 10개를 모두 통과해야 한다. 해당 없음은 검증된 근거와 사유가 있을 때만 인정하며 빈 값이나 조사자의 추측은 통과가 아니다.

| ID | 검증 조건 | 남길 증거 / 실패 판정 |
|---|---|---|
| RA01 | 공식 원문·계약·권한 있는 주체의 승인 존재 및 진위 | 공식 발급 경로/원문 보관 참조, 문서 버전·조항, 서명/위임 확인 방법. 파일 hash만 있으면 UNVERIFIED |
| RA02 | 출처와 적용 주체 일치 | 권리자→발급자 권한 관계 및 계약 적용 계정/법인/사용자 확인. 타 계정 계약을 가져오면 UNVERIFIED·scope mismatch |
| RA03 | 현재 API 제품·자료 유형 일치 | 실제 source_product/endpoint와 약관 상품 범위 대조. KRX 다른 상품이나 KIS REST/WS를 무조건 동일시하지 않음 |
| RA04 | 원본·파생 및 부모 closure의 범위 일치 | OHLCV 원본, 조건 문장, Risk, rank, hash 각각의 해당 조항/답변. 파생 미명시는 UNVERIFIED; 명시적 적용 금지는 VERIFIED_PROHIBITED |
| RA05 | 외부 AI 수신자·처리 목적 일치 | TypeSafe 수신 주체/서비스와 일관성 검토 목적을 특정. 개인 조회/로컬 분석 허가만이면 AI 행위는 UNVERIFIED |
| RA06 | 처리지역·저장·로깅·재위탁 등 실제 조건 일치 | 적용 MCA/주문서/처리조건을 원천 허용 범위와 대조. 확정된 허가 조건 미충족은 CONDITIONAL, 실제 조건을 모르면 UNVERIFIED |
| RA07 | 유효 기간·적용 시점 확인 | effective_from/to와 전송 및 보관 행위 시점 확인. 명시적 무기한과 기한 미확인을 구별. 만료 시 이전 허용 재사용 금지 |
| RA08 | 철회·변경·충돌 확인 | 공식 확인 경로, 확인 시각, revocation/supersedes/conflict 참조. 확인 불가·미해결 충돌은 UNVERIFIED/HOLD; 최신 문서 자동 우선 금지 |
| RA09 | 증거와 대상 요청의 불변 결합 | 원문 digest+검증 이력+field/parent scope를 §9.4의 `bound_subject_hash`에 결합. 대상이 바뀌면 이전 판정 불일치 |
| RA10 | 판정 책임·근거·시점 기록 | 권한이 확인된 verifier_ref, RA별 결과, decision_basis_refs, rights_verified_at와 상태를 보존. 판정 문자열만 제출하면 거부 |

사용자 실행 동의는 제공처 이용권을 대신하지 않는다. 과거 승인, 유료 이용, 내부 파생 표시, 재해싱은 RA01~RA10의 대체 증거가 아니다. `VERIFIED_ALLOWED`는 확인된 **그 행위와 요청 범위**의 판정이며 무제한 사용권 표시가 아니다.

### 9.2.3 R1-A 상태 전이·만료·철회·충돌

| 현재 → 다음 | 전이 조건 | report/승인 처리 |
|---|---|---|
| 신규 → UNVERIFIED | 진위·범위·역할·시간 근거 중 하나라도 미확인 | HOLD, 미확인 이유 유지 |
| UNVERIFIED → CONDITIONAL | 권한 근거의 진위/범위 확인, 명시된 미충족 조건 존재 | HOLD; 조건과 충족 증거 요구 |
| UNVERIFIED/CONDITIONAL → VERIFIED_ALLOWED | RA01~RA10 통과 및 모든 조건 충족 | 새 검증 버전으로 대상 요청을 재평가. 실행 승인은 별도 |
| 어느 상태 → VERIFIED_PROHIBITED | 진위·적용 범위를 확인한 명시적 금지 | 해당 행위/부모 closure DENIED. 파생까지 적용되는지 모르면 그 파생 범위는 UNVERIFIED |
| VERIFIED_ALLOWED → UNVERIFIED 또는 CONDITIONAL | 만료·진위 훼손·철회·미해결 충돌·scope 변경이면 UNVERIFIED; 여전히 유효한 근거의 명시 조건 미충족만 CONDITIONAL | 관련 field verdict, data eligibility, 대기 중 실행 승인과 미전송 요청을 즉시 무효화. 명시적 금지가 확인되면 VERIFIED_PROHIBITED |
| VERIFIED_PROHIBITED/무효화 상태 → VERIFIED_ALLOWED | 기존 제한을 정당하게 대체하는 권한 있는 근거와 우선순위/유효기간 확인 후 RA 전체 재검증 | 최신 날짜/수동 status 변경만으로 복구 불가 |

원문과 과거 판정은 감사 이력으로 보존하고 현재 허용 상태로 덮어쓰지 않는다. 증거 버전·scope·부모 closure에 의존하는 report 및 아직 사용하지 않은 실행 승인을 추적해 무효화한다. 캐시된 성공 판정도 전송 직전에 현재 유효성을 다시 확인하며, 오래된 `checked_at`만으로 철회 없음이라고 추정하지 않는다. 공식 변경 확인이 불가능하면 HOLD다. 이미 보낸 요청은 소급해 취소됐다고 주장할 수 없다. 향후 그런 경우에는 신규/재시도 호출을 차단하고 영향 요청을 기록하며, 이미 보관된 자료는 적용 계약의 삭제·보관 의무를 별도로 확인한다. 이번 작업에서는 조회·삭제·전송을 수행하지 않는다.

### 9.3 최종 적격성 결정 흐름

```text
1. 동결 Capture·Snapshot hash·S7.1 정합성 확인
2. 전송 후보 JSON Pointer 재귀 분류 + 모든 leaf/부모 closure의 실제 origin 확인
3. field × action × purpose × recipient 권한(RA01~10) 및 평가 모드별 시간(§6) 검증
4. 남은 조건·Risk·기간 맥락의 충분성/Legacy 제한 확인
5. 검증된 필드만으로 전송 전용 최소 body {state, questions, model} 생성
6. 엄격한 타입/allowlist 검사 → 전체 body canonicalization → outbound_projection_hash
7. 최종 body와 증거를 결합한 data eligibility 결정 + 독립 실행 승인 범위 대조
8. 미래 전송 직전 전체 body·증거 유효성·실제 모델/질문/목적·승인 재검증
9. ELIGIBLE ∧ execution READY ∧ 현재 검증/승인 결합 일치일 때만 향후 호출 가능
   현재 S7.4: 8~9의 호출 구현/활성화 없음. 기존 PROVIDER_HOLD 유지
```

`data eligibility=ELIGIBLE`이어도 실행을 허가하지 않는다. `LEGACY_LIMITED`의 원본 전략 신원 부재는 검증 목적이 그것을 허용하는 별도 사후 프로토콜 없이는 근거 충분성 HOLD다. `RETROSPECTIVE_CAPTURE`를 사전 성과 집계에 넣지 않는다. 최소 조건은 조건별 실제 PASS와 의미 대응, Risk status/warning 및 그 판단 범위, 실행 정책/기간 맥락이다. 필드 제거로 조건 일관성 검토 자체가 성립하지 않으면 `EVIDENCE_INSUFFICIENT`로 로컬 종료한다.

시간 검증은 모든 계산을 Capture 이전으로 강제하지 않는다. §6.4의 `RETROSPECTIVE_RESEARCH`는 동결 Snapshot의 현재 후처리를 허용하되 과거 사전 성능 분모에 넣지 않는다. `FORWARD_ASOF`는 사전 고정한 cutoff의 입력 revision과 판단 deadline·결과 관측의 순서를 입증해야 한다. 두 모드 모두 외부 전송 권한을 요구한다.

누락·순환 계보, 미분류 필드, 패킷 hash 불일치, 원천 모순, timezone 없음은 예외를 허용 방향으로 삼키지 않는다. 기존 `SOURCE_RIGHTS_UNVERIFIED`, `SOURCE_RELEASE_TIME_UNVERIFIED`를 유지하고, 세부 사유로 `SOURCE_ORIGIN_UNVERIFIED`, `SOURCE_RIGHTS_PROHIBITED`, `RIGHTS_CONDITION_UNMET`, `RIGHTS_SCOPE_MISMATCH`, `RIGHTS_EVIDENCE_EXPIRED`, `RIGHTS_EVIDENCE_REVOKED`, `RIGHTS_EVIDENCE_CONFLICT`, `RIGHTS_AUTHENTICITY_UNVERIFIED`, `LINEAGE_INCOMPLETE`, `LINEAGE_CYCLE`, `UNCLASSIFIED_OUTBOUND_FIELD`, `SENSITIVE_OUTBOUND_DATA`, `OUTBOUND_APPROVAL_MISMATCH`, `SOURCE_TIME_INCONSISTENT`, `TIMEZONE_UNVERIFIED`, `REVISION_ASOF_UNPROVEN`, `EVIDENCE_INSUFFICIENT`를 제안한다. 동일 hash 재계산으로 승인되지 않도록 trusted evidence resolver와 전송 직전 결합 검증이 필요하다.

### 9.4 R1-C 최종 HTTP 본문·증거·실행 승인 결합

`input_hash`/Snapshot hash는 기존 로컬 원본을 식별한다. `outbound_projection_hash`는 **최종 `{state, questions, model}` 전체**를 아래 방식으로 정규화한 UTF-8 bytes의 SHA-256이며 `state`만의 hash가 아니다. 기존 원본 hash의 의미/알고리즘은 바꾸지 않는다.

1. **정규화 계약:** body는 JSON 값만 허용하고 키 중복, NaN/Infinity, 알 수 없는 타입, 문자열로의 임의 강제 변환을 거부한다. 객체 키 정렬·공백 없는 구분자·UTF-8·문자열 그대로 보존을 버전으로 고정한다. 배열 순서, null과 키 생략, 숫자 타입은 임의로 합치지 않는다. A09가 사용하는 [prospective/models.py:24의 canonical_json](https://github.com/SkyBluekor/StockScope/blob/12532ac3b6b35758ac4a471157d3e32fab812368/backend/app/prospective/models.py#L24)은 `default=str`를 사용하므로 무검증 입력에 그대로 재사용하지 않는다. 엄격한 사전 타입 검사 후 검증된 범위에서 재사용하거나 별도 버전의 outbound 정규화를 사용한다.
2. **증거 결합:** `bound_subject_hash`는 원본 identity/hash, outbound hash, lineage/rights/time manifest hash, contract/allowlist/canonicalization 버전, 질문 hash, model ID, 목적, 수신자/처리조건, 평가 모드·cutoff·deadline·protocol hash를 결합한 대상 식별값이다. rights manifest의 hash 대상은 원문 참조/검증 버전·scope·RA01~08의 검증 이력이며, 뒤에 생성되는 `bound_subject_hash`, RA09~10의 요청 결합 판정, 실행 승인 참조는 제외하여 순환을 막는다. RA09~10은 이 manifest와 대상 hash를 참조하는 불변 후속 판정 이력으로 같은 RightsEvidence 계약 안에 기록한다. 모든 실제 허용 판정은 후속 이력까지 resolver로 검증해야 하며 hash에서 제외됐다는 이유로 검사를 생략하지 않는다.
3. **독립 실행 승인:** 신원이 확인된 실행 승인자의 승인 참조가 이 대상 식별값 및 모델·요금/예산·유효기간·요청 횟수/재시도 범위를 명시해야 한다. Horizon 정책과 실제 adapter 승인도 필요하다. 사용자 실행 동의만으로 원천 권한을 만들 수 없으며 데이터 적격성만으로 실행을 승인하지 않는다. 실행 승인자 지정과 실제 승인 증거는 현재 미확정이다.
4. **전송 직전 재검증:** 미래 wrapper는 자격 증명 로딩/네트워크 접근 전에 실제 transport가 쓸 전체 body를 만들고 승인 대상과 대조한다. A15 transport는 `request`의 model 값을 그대로 쓰지 않고 설정된 `self.model_id`로 body를 구성하므로 그 **실제 모델**을 검사해야 한다. 원본·질문·모델·처리조건·권한 원문/검증 이력·기간·철회 상태·시점 증거 중 하나라도 달라지면 기존 report/승인을 무효화하고 1단계부터 재평가한다. 질문 변경 후 같은 state hash를 재사용하는 것도 차단한다.
5. **검사와 사용의 일치:** 검사한 canonical bytes를 불변으로 고정하여 바로 전송하도록 미래 adapter 계약을 정한다. 승인 후 필드 추가, SDK의 다른 직렬화, model 교체, 재시도 시 재구성으로 다른 body가 나가면 안 된다. 현 A15의 `json=body` 전송이 이 bytes 결합을 이미 보장한다고 주장하지 않는다. 전송 직전 증거/승인 상태 버전 확인과 요청 소비를 결합하고, 그 사이 변경이 감지되면 보내지 않는다. 최종 body hash·승인/증거 버전·요청/응답 시각을 기록하되 키/Authorization은 body·진단 로그에 넣지 않는다.

`outbound_projection_hash` 및 대상 hash는 **필요하지만 충분조건이 아니다**. 누구나 같은 내용의 hash를 계산할 수 있으므로 제공처 허가의 진위나 실행 승인자의 권한을 증명하지 못한다. trusted resolver가 확인한 증거와 승인 기록을 각각 검증해야 한다. 현재는 이 계약만 설계하며 실제 wrapper·HTTP 호출·승인 플래그 변경은 구현하지 않는다.

## 10. 미확인 사항 및 추가 확인 대상

| 우선순위·대상 | 확보할 정확한 증거/답변 | 완료 판정 |
|---|---|---|
| P0 KRX 데이터 담당 | 현재 계정의 OPEN API 상품 승인·적용 약관; 조건 PASS 문장, Risk boolean, 후보 순위, 가격 포함 Snapshot hash를 미국 TypeSafe에 보내 처리·저장·telemetry에 사용하는 범위의 서면 답변 | 항목/목적/수신자/기간별 allow/deny 명시. “개인 연구 가능”만으로 완료 아님 |
| P1 수집 증거 확인 | 허가된 소수 동결 입력에 연결된 원천 endpoint·행/revision·응답 digest·실제 수집/확보 로그; 외부 반입 자료의 제공된 manifest | 기존 자료에 재결합 가능한 증거만 분류. 불가능한 과거 자료는 UNKNOWN/DATE_ONLY 유지. 이번 작업의 Runtime DB 접근 또는 과거 전체 DB 조사 요청이 아님 |
| P0 KRX 시점 담당 | 해당 OPEN API별 공개/갱신·정정 정책과 원본 행에 연결 가능한 시각 증거 | EOD 제공 스케줄과 개별 공개·확보 증거를 분리 |
| P0 TypeSafe 계정 담당 | 적용 MCA/주문서, input/output/log/hash/backup의 보관·처리지역·하위처리자·삭제, 계정별 조건 | KRX가 허용한 범위와 모순 없음. 모델/요금 승인은 별도 |
| 대체/확장 시 KIS | 개인 Open API 약관 원문, 거래소 시세 조건, 외부 AI 처리 허용 범위; 실제 연결된 REST/WS별 데이터 권리 | 향후 KIS를 추가할 때 검증. 구형 일봉 경로 존재로 사용권을 주장하지 않음 |
| 대체/확장 시 OpenDART/FRED/NAVER | 데이터 유형/계열/검색 제품별 AI·재제공·보관 근거 | 현재 S7.3 데이터 적격성과 분리. “공공/무료/공개”라는 이유로 대체 허가 불가 |

### 10.1 대체 경로 — C

| 선택지 | 가능한 평가 목적 | 필요한 선행조건 / 현재 판정 |
|---|---|---|
| KRX 별도 데이터 구입·분배 계약(B03) | 기존 OHLCV 기반 Scanner 평가 유지 가능성 | 외부 AI 처리·파생/순위·저장/재위탁 범위를 계약에 명시해야 하는 조건부 대안. 체결·데이터 구매 안 함. 실제 권한 상태는 **UNVERIFIED**이며 §9.2의 검증된 CONDITIONAL 권한을 확보했다는 뜻이 아님 |
| KIS 또는 다른 시세 제공자 | 동일 지표 계산 가능성은 기술적으로 별개 | 해당 거래소 권리와 처리 계약, point-in-time revision 증거, 지표/종목 coverage 검증까지 필요. KIS로 바꾸기만 하면 허용되는 것은 아님 |
| OpenDART 또는 FRED | 공시/거시 데이터 자체의 별도 질문 | OHLCV·Scanner 조건/Risk를 동등하게 대체하지 못함. 질문·평가 cohort 재설계 및 권리 검증 필요 |
| 자체 규칙/순수 합성 자료 | 질문 스키마·응답 타입·충돌/ABSTAIN·차단 규칙 시험 | 실제 시장 판단 성능 증거가 아님. 실제 데이터 변형을 SYNTHETIC으로 표시 금지. 외부 유료 실행은 별도 승인 |
| 필요한 필드 제외 | 허가된 나머지 증거로 동일한 질문이 성립할 때만 | 모든 남은 부모 권한과 충분성 재검증. 종목코드·가격만 제거하는 우회 불가 |
| 로컬 규칙/로컬 모델 검토 | 외부 전송 없는 정합성·의미 충돌 검사 | 원천의 로컬 이용조건 안에서 수행. 로컬 모델도 외부 telemetry·업로드가 없는 경계 확인; 경제적 유효성은 별도 |

## 11. R1-D 단계별 최소 구현 범위와 검증 테스트

**C: 앞으로의 구현 순서. 이번 PR에서는 테스트 코드를 만들거나 Runtime 실행하지 않는다.**

목표는 **JEV 실종목 평가가 가능한지 소수 입력으로 판별**하는 것이다. P0를 먼저 진행하고 P1은 제한된 로컬 진단으로 묶는다. 다섯 논리 객체를 모두 영속화하거나 과거 시장 DB 전체의 DAG를 구축하는 일을 선행조건으로 삼지 않는다. 아래 수정 대상은 향후 별도 구현 작업의 후보이며 이번 PR은 문서만 수정한다.

| 항목 | S7.4-P0 실제 원천 권한 확인 |
|---|---|
| 목표 | 현재 사용 KRX 제품·적용 계약과 원본/파생 외부 AI 행위의 가능 여부를 먼저 확인 |
| 선행조건 | 실제 계정/상품 확인 자료와 공식 약관·계약·서면 답변에 대한 정당한 열람. 없으면 미확인 유지 |
| 수정 대상 | 이 문서 §10의 질문·근거 및 기존 RightsEvidence 논리 계약의 확인 항목. 실행 코드·DB 추가 없음 |
| 재사용 | §3 제품 구분, §5 공식 근거, §7 필드 표, §9.2의 역할·RA 검사 |
| 필수 검증 | 타 상품/계정 계약, 출처 불명 승인서, 개인 조회 허가만 제시, 파생 scope 누락을 허용으로 판정하지 않는 사례 검토 |
| 완료 조건 | 필요한 행위마다 확인된 허용/금지/조건/미확인과 원문·조항·담당 역할의 확인 여부를 기록. 답변 미수신은 조사 공백으로 남기며 권한 확보 완료가 아님 |
| 진행/중단 | 허용 가능한 경로 또는 해소할 명확한 조건이 있으면 P1 및 제한적 P2를 검토. 미확인 동안 전송 HOLD. 권한 확보 불가가 확인되면 그 원천의 외부 JEV adapter, 외부 평가용 수집 확장·전면 계보 구축·P3 허용 경로를 중단. 합법적 로컬 진단/별도 합성 목적만 독립 검토 |

| 항목 | S7.4-P1 읽기 전용 패킷 계보 진단 |
|---|---|
| 목표 | 제공된 소수 동결 Capture/fixture의 S7.3 필드를 따라가며 원천·부모·누락 증거를 표시 |
| 선행조건 | P0의 제품/권한 공백 목록 및 해당 입력의 로컬 열람 권한. Runtime 접근은 향후 별도 작업 범위가 허용하는 경우에만; 이번 PR에서는 접근 없음 |
| 수정 대상 | S7.3 prepare 결과를 소비하는 별도 진단 함수/기존 report 확장과 그 테스트. Snapshot/catalog/시장 DB 정본 수정 없음 |
| 재사용 | prepare 무결성 검사, input_hash, 조건 신원 검증, §7 경로 표. SourceArtifact/LineageNode를 필요한 필드 참조로만 사용 |
| 필수 테스트 | 원본 bytes/hash 불변, 부모 누락/순환/혼합 원천/미분류 필드 표시, prepared.identity 전송 금지, provider 0건 |
| 완료 조건 | 선택 입력의 모든 leaf에 원천 확인 또는 UNKNOWN 사유가 있고 별도 진단 결과로 저장 가능. 계보 미확인은 실패를 숨기지 않는 정상 진단 결과이며 외부 적격이 아님 |
| 진행/중단 | P0에서 수집·이용 가능한 경로가 확인되고 실제 시점 공백 해소가 필요할 때만 P2. 과거 UNKNOWN을 해소하려고 DB 전면 역추적/재작성으로 확장하지 않음 |

| 항목 | S7.4-P2 신규 데이터 수집 증거 축적 |
|---|---|
| 목표 | 확인된 제품의 제한된 신규 수집에서 출처·응답/revision·최초 확보와 실패/캐시 의미를 입증 |
| 선행조건 | P0에서 해당 수집·로컬 보관 권한 확인 및 외부 평가 가능성에 대한 근거/구체적 조건, P1에서 필요한 공백 특정. API 호출·보관 범위는 향후 작업에서 명시적으로 확정 |
| 수정 대상 | 해당 수집 경계의 선택적 증거 기록과 read-only 연결만. 기존 DB 전체 migration, 과거 행 일괄 수정, Capture 재생성 없음 |
| 재사용 | 기존 수집 응답/캐시 경계, digest, 시간 품질 enum/aware 파싱, SourceArtifact/TimeEvidence 부분 record. 최소 sidecar 우선 |
| 필수 테스트 | 오류/타임아웃/부분 응답을 정상 확보 증거로 만들지 않음; cache hit는 원래 receipt 참조, 없으면 최초 확보 UNKNOWN; 같은 revision 재수집은 최초 시각 보존; EOD 수정은 새 revision; UTC/KST·naive·시작/수신 역전 검사 |
| 완료 조건 | 제한된 신규 성공 응답의 payload/revision과 실제 측정된 시간 이벤트가 불변 결합되고, 오류/캐시/정정 사례가 검증됨. 시각을 제공하지 않는 원천의 공개시각은 여전히 UNKNOWN일 수 있음 |
| 진행/중단 | P0 권한과 필요한 시간 증거가 검증 가능하면 P3. 정확한 revision/시점 입증이 불가능하면 해당 모드는 HOLD; 시각을 역산·생성하지 않음. 권한 확보 불가이면 외부 평가 목적의 확장 중단 |

| 항목 | S7.4-P3 권한 및 시점 적격성 판정 |
|---|---|
| 목표 | 선택 입력과 최소 body에 대해 검증된 권한·시점·충분성을 결합한 로컬 EligibilityReport 생성 |
| 선행조건 | 진위·적용 범위가 확인된 권한 증거와 모드별 시간 증거, 완전한 후보 필드 분류. 권한 없는 fixture로는 HOLD/거부 테스트만 수행 |
| 수정 대상 | 기존 preflight와 분리된 report validator/순수 projection·hash 검증 및 테스트. 기존 무조건 PROVIDER_HOLD·비활성 provider 유지; 실제 transport 연결 없음 |
| 재사용 | RightsEvidence·TimeEvidence 참조, prepare/기존 hash, 질문 계약/모델 pin 구조, §9.3~9.4 순서. 별도 승인 서비스·통합 원장 DB 구축 불필요 |
| 필수 테스트 | RA01~RA10 위조/범위 불일치, 권한 만료·철회·충돌, 두 모드 시간 규칙, 전체 body 변경·민감 값, hash 재계산, 실행 승인 분리 |
| 완료 조건 | 허용 fixture는 근거를 추적할 수 있고 모든 미확인/금지/불충분 사례는 HOLD/DENIED. 실제 증거가 없으면 실제 결과도 PROVIDER_HOLD가 정답이며 “전송 가능 검증 완료”로 보고하지 않음 |
| 진행/중단 | 모든 데이터 조건이 충족돼도 실제 호출은 별도 adapter 구현 검토, Horizon·모델·요금/예산·정확한 요청 실행 승인 이후의 별도 작업. P3 완료는 호출 활성화 승인이 아님 |

위 완료 조건은 향후 검증 기준이며 P0~P3 구현이 완료됐다는 선언이 아니다. 이번 작업에서 외부 문의 발송이나 신규 수집도 수행하지 않는다. 권한 문의를 위한 정확한 질문을 준비하는 것과 제공처가 실제 허가하는 것은 구분한다.

### 11.1 구현 시 필수 회귀 테스트 계약

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
| R1-A 진위 | status/verifier_ref/hash를 함께 위조; 실제 공식 문서와 다른 bytes; 발급자 위임 불명; 다른 계정/제품의 진짜 계약 | RA01/02/03/10 실패. caller 재해싱으로 통과 불가; 적용 scope별 UNVERIFIED/HOLD |
| R1-A 범위 | 원본 허용이나 파생 미명시, AI 처리 허용이나 로그/미국 지역/하위처리자 불명, 확정된 조건 미충족 | RA04~06 결과를 각각 UNVERIFIED 또는 CONDITIONAL로 구분; 명시 금지만 VERIFIED_PROHIBITED |
| R1-A 무효화 | 승인 이후 만료/철회/충돌 발견, evidence 버전 변경, 오래된 성공 report 재사용 | RA07~09 재검사, 의존 report·대기 실행 승인 무효화; 이력 보존, 자동 최신 우선/복구 금지 |
| R1-B 정상 후처리 | 동결 Capture 뒤 현재 packet 생성; cutoff 입력만 사용해 deadline 전에 정상 응답 | 사후 모드는 후처리 시각만으로 거부하지 않음; 사전 모드도 후처리 자체는 허용하되 각 증거/권한 gate 필수 |
| R1-B 미래 혼입 | cutoff 뒤 revision/재수집을 당시 확보로 표시; 최신 가격을 과거 snapshot에 주입; outcome 확인 후 질문·판단 수정 | FORWARD_ASOF 거부. 사후 분석으로 명시한 새 revision도 과거 사전 분모에 포함 불가 |
| R1-B 이벤트 의미 | completed_at을 최초 확보/commit으로 대체; 요청 시작만 deadline 이전이고 검증 응답은 이후; 결과 관측 이력 누락 | 거짓 증거 승격 금지; 사전 모드 HOLD/기한 실패. 기록이 늦다는 이유로 최초 관측이 늦었다고 추정하지 않음 |
| R1-C 전체 body | 같은 state에서 questions/model 교체; transport의 self.model_id 불일치; 추가 중첩 키; canonical 이후 body 수정 | 전체 outbound hash/승인 결합 불일치로 credential/network 접근 전 차단 |
| R1-C 엄격한 JSON | 중복 키·NaN/Infinity·datetime 객체 강제 문자열화·배열 재정렬·필수 키 누락 | 정규화 전 거부 또는 승인 대상 불일치. input_hash가 같아도 최종 body 검사 생략 불가 |
| R1-C 민감 정보 | 허용 키 statement/questions에 종목명·코드·계좌·잔고·수량·인증 정보 삽입; 별칭/인코딩한 계좌 원천 값 | 값의 계보/고정 생성 규칙으로 제외·차단, 불명 자유 텍스트 HOLD. 현재 packet에 계좌정보가 있다는 전제 없이 음성 fixture 사용 |
| R1-D 범위 제한 | 기존 DB 전체 migration 없이 소수 fixture 진단; P0 권한 불가/응답 미수신 | 전자는 원본 불변·UNKNOWN 표시 가능; 후자는 HOLD 및 외부 평가 목적 구현 확장 중단, 시간 증거 조작으로 우회 불가 |

문서 검증은 기준 커밋·코드 경로/줄 링크·S7.3 leaf 필드 전수 대조·Markdown 표 구조·문서 한 파일만 변경 여부로 수행한다. 이 검증을 실제 Capture 재현 성공이나 S7.4 구현 테스트 PASS라고 보고하지 않는다.

## 12. 최종 GO / CONDITIONAL / NO-GO 판단

| 범위 | 판정 | 사실 수준·이유 |
|---|---|---|
| P0 권한 확인 및 P1 소수 입력의 읽기 전용 진단 | **GO** | C: 착수 가능한 최소 범위. 로컬 열람 권한과 실제 입력 확보는 별도 조건이며 원천 조회·저장 자체의 계약 문제를 면제하는 승인은 아님 |
| P2 신규 수집 증거 및 P3 적격성 판정 구현 | **CONDITIONAL** | C: §11의 선행조건을 충족하는 범위에서 단계적으로 착수. 현재 조사만으로 권한/시간 확보 또는 구현 완료를 주장하지 않음 |
| 별도 허가를 받은 미래 데이터·수신 조건으로 외부 평가 | **CONDITIONAL** | C: field별 권리·원천/revision·시간·충분성 및 독립 실행 승인이 모두 필요 |
| 현재 S7.3 실제 시장 packet 외부 TypeSafe 호출 | **NO-GO** | A: 실제 adapter 비활성·항상 HOLD. B01: 원본 제3자 제공 제한. C: 파생정보 AI 범위·개별 계보/공개시각 미확인 |
| 기존 사용자 Capture를 당시 사전 JEV 성과로 평가 | **NO-GO** | C: 사용자 보고가 사후 Capture이며 본 조사에서 원본 미재검증. A: 실제 시장 JEV 호출 경로 없음 |

**S7.4가 우선 해결할 세 문제는 (1) 행·필드별 제품/계보 증거의 부재, (2) 파생정보와 TypeSafe 처리·보관까지 포괄하는 권한 증거의 부재, (3) 원천 공개·최초 확보·수정 revision 시각 증거의 부재다.** 이를 해결해도 `LEGACY_HORIZON_UNDEFINED` 또는 수치 기간 정책, `PINNED_MODEL_AND_BILLING_NOT_VERIFIED`, `EXPLICIT_EXECUTION_APPROVAL_MISSING`, `REAL_MARKET_PROVIDER_NOT_AUTHORIZED`는 별도의 차단이다. 현재 시장 데이터 중 외부 AI 전송을 검증 완료한 자료는 **없다**.

### 12.1 DOC-R1 계약 완결성 확인

| 질문 | 답변과 연결 절 | 남은 미확정 사항 |
|---|---|---|
| 1. 어떤 데이터가 KRX 원본/내부 계산인가? | §2~4·§7: 가격/거래량 등 원본과 조건 PASS·Risk·rank·hash 등 파생/내부 판단을 필드별 구분 | 개별 사용자 자료의 실제 원천은 제공된 증거로 별도 확인 필요 |
| 2. 내부 계산의 외부 부모는 무엇인가? | §2·§7·§9.2: KRX 가격/지표·모집단 등 closure를 유지; 문장화/해싱으로 단절되지 않음 | 기존 자료의 행/revision 연결 공백은 UNKNOWN |
| 3. 제품 약관은 어떤 행위에 적용되는가? | §3·§5·§9.2/RA03~06: 제품과 LOCAL_READ/DERIVE/AI_TRANSMIT/PROCESS/STORE 등 개별 행위를 대응 | 실제 계정 계약 및 파생 AI·보관 범위 미확인 |
| 4. 누가 무엇으로 VERIFIED_ALLOWED를 판정하는가? | §9.2.1~9.2.2: 권한자/발급자와 검증자를 구분, 진위·scope 등 RA01~10 통과 후 검증 책임자가 근거·시점 기록 | 실제 검증자 지정 및 사용자 승인서 진위 확인 미완료 |
| 5. 사후/사전 시점 증거는 무엇인가? | §6.3~6.4·§9.3: 이벤트별 revision 증거, 사후 표시/분모 분리, 사전 cutoff·deadline·결과 관측 분리 | 실제 공개/최초 확보·commit/판단 증거 누락은 보충 없이 HOLD |
| 6. 전송 body와 검증 입력의 일치는? | §8.1·§9.4: 원본→allowlist projection 연결, 전체 body canonical bytes/hash와 증거/모델/질문/실행 승인 결합, 직전 재검사 | 미래 adapter 미구현; 실제 일치 검증 완료가 아님 |
| 7. 만료·철회는 무엇을 무효화하는가? | §9.2.3·§9.4: 의존 field verdict/report·대기 실행 승인·미전송 요청, 캐시된 성공 판정 재사용 차단 | 실제 증거 변경 확인 경로/운영 책임은 P0에서 확인 |
| 8. 최소 구현 범위는? | §9.1·§11: P0 우선, P1 소수 read-only 진단, P2/P3는 필요 증거·판정만 단계적으로 | 신규 5개 DB/과거 전체 DAG는 요구하지 않음 |
| 9. 권한 확보 불가이면 무엇을 중단하는가? | §11 P0/P2/P3: 해당 원천의 외부 adapter·외부 평가용 수집/계보 확장·허용 경로 중단 | 대체 원천도 자동 허가되지 않으며 별도 권한/목적 검토 |
| 10. TypeSafe를 왜 계속 비활성화하는가? | §8·§12: 원본 제3자 제공 제한, 파생 AI 권한·시점 증거 부족, 실제 adapter 및 독립 실행 승인 부재 | 실제 시장 호출 **NO-GO / PROVIDER_HOLD**, 본 문서 보완으로 해제되지 않음 |

설계 규칙을 구체화한 것과 실제 사용자 계약/허가·시점 증거를 확보한 것은 별개다. 따라서 DOC-R1 문서 보완은 검토 가능하지만 실제 데이터의 권한 확보나 S7.4 구현 완료를 뜻하지 않는다.

## 13. JEV-ACT2-S8 소수 입력 권한·시점 판정 구현 및 외부 확인 (2026-10-13)

**구현 범위:** `backend/app/jev/scanner_eligibility_s8.py`, `tools/data/jev_s7_shadow.py s8-readiness`. S7.5 브랜치를 부모로 한 후속 작업이다. 여기서 작성한 권한·시각의 **검사 함수는 진위 인증서가 아니며**, 외부 TypeSafe 호출을 활성화하지 않는다. 소스별 원본의 행/revision, 최초 확보, 계약 적용 계정 및 실제 허가는 현재 Runtime 자료에서 입증되지 않았다. 기존 Cache mtime·Capture 완료시각을 원천 시각으로 승격하지 않는다.

### 13.1 공식 공개 자료 재확인

- [KRX OPEN API 국문 약관](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp): 제11조②는 제공받은 정보의 제3자 제공을 제한한다. 제12조③의 새로운 부가정보 면책은 파생 자료의 외부 TypeSafe 처리 허가 조항이 아니다. 계정별 별도 허가/상품 계약은 이번 확인에서 입증되지 않았다. **받은 KRX 원본 제3자 전송은 공개약관상 제한**, 조건 문장·Risk·순위 등 파생정보의 AI 처리 범위는 **UNVERIFIED**로 구분한다.
- [TypeSafe MCA](https://typesafe.ai/legal/mca): §4.3의 Telemetry 및 §5의 제3자 데이터 권리 확보 의무는 원천 권리자의 별도 허가가 필요함을 보여준다. [TypeSafe 개인정보 처리방침](https://typesafe.ai/legal/privacy-policy)에는 입력의 모델 학습 미사용과 별도의 보관·미국 호스팅/처리 설명이 있다. 개인정보 처리방침만으로 특정 고객 계정의 서비스 계약·로그/파생 시세 처리 권리가 확보된 것은 아니다.
- [KRX OPEN API 이용 방법](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp): 인증키 및 개별 상품 활용 승인 절차가 존재한다. 실제 계정에 승인된 상품은 개별 승인 내역을 확인해야 한다.

### 13.2 제공처에 확인할 최소 질문 (별도 답변 없으면 HOLD)

**KRX에 확인:** 현재 사용 중인 주식 일별/지수 일별 OPEN API 상품 및 승인 계정 기준으로,

1. OHLCV·지수 원본을 TypeSafe AI(미국 소재 외부 수신자)에 전송하여 분석하는 것이 허용되는가? 금지/허용을 구체적인 상품과 행위별로 구분할 수 있는가?
2. 원본 수치가 아니라 StockScope가 계산한 기술조건 PASS 문장, 전략 의미 관계, Risk status/warning, 후보 순위 및 Snapshot hash만 외부 TypeSafe에 전송하여 판단·기록하는 것도 허용되는가?
3. TypeSafe 서비스의 처리·보관·진단로그/telemetry·백업·하위처리자 사용 및 지역 범위에 대한 별도 조건이나 재위탁·분배 계약이 필요한가?
4. KOSPI/KOSDAQ 주식/지수 OPEN API의 공개/갱신·정정(개별 revision 포함) 시점을 확인할 수 있는 공식 기록이나 제공 방법이 있는가? 별도 계약/상품이 필요하면 무엇인가?

**TypeSafe 계정 담당에 확인:**

1. 실제 계정의 적용 MCA/주문서, input·output·hash·telemetry·로그·백업의 보관기간과 처리/삭제 범위는 무엇인가?
2. 실제 처리 국가, 하위처리자, 외부 입력 파생정보의 모델 학습/제품 개선 이용 범위는 무엇인가?
3. 당시 실행 가능한 모델 ID·요금·호출 예산 및 해당 계정의 별도 이용 제한은 무엇인가?

공식 답변은 권한 있는 주체, 해당 계정·제품·행위·기간·대상에 결합한 뒤 RA01~RA10으로 검증해야 한다. 사용자가 임의로 작성한 승인 문자열, hash, 시각, 증거참조는 그 자체로 허가가 아니다. 응답 미수신은 금지 확정이 아니라 **UNVERIFIED / HOLD**다.

### 13.3 실행과 완료 경계

- `s8-readiness --capture-id <ID>`는 S7.5의 정합성·Horizon·V4 로컬 판정과 S7.4 계보를 재사용해, 시장 원천·revision·권한·공개/확보 시각의 빈자리를 **읽기 전용**으로 요약한다.
- 새로운 `inspect_temporal_chain`은 synthetic 이벤트의 UTC-aware 순서만 검증하며 이벤트 원문·최초 수신의 진위는 인증하지 않는다. `hash_local_outbound_candidate`도 정확한 로컬 `{state, questions, model}` 후보의 해시만 계산할 뿐 실제 전송 바이트·모델 binding·실행 승인을 검증하지 않는다.
- 실제 수집 경로의 신규 sidecar 기록은 관련 상품·목적의 이용 조건이 확인되고 사용자가 실제 조회/저장 실행을 승인한 경우에만 추가한다. 과거 원천 자료를 수정하거나 숨겨진 API 호출로 증거를 만들지 않는다.
- **판정:** 현재 KRX OPEN API 원본 제3자 전송은 공개약관상 제한, 파생정보 TypeSafe 사용권 및 개별 원천·시간 증거는 미확인. 따라서 현 실제 시장 Capture에 대한 전송은 **NO-GO**, 데이터 적격성은 **HOLD_UNVERIFIED**, 로컬 진단은 가능하다. 공식 답변을 얻어도 Provider 호출과 유료 실행은 독립 승인 대상이다.
