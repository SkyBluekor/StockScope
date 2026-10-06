# StockScope Implementation Baseline vNext

작성일: 2026-09-27 (Asia/Seoul) · 설계 버전: `vNext-2026-09-27`

## 1. 적용 범위와 문서 관계

이 문서는 향후 Codex가 [Development Roadmap](StockScope_DEVELOPMENT_ROADMAP_vNext.md)의 `VN-P*` Stage를 구현할 때 적용할 기준이다. 책임·데이터 소유권은 [Master Architecture](StockScope_MASTER_ARCHITECTURE_vNext.md), 현재 구현 사실과 이력은 [Current State](StockScope_CURRENT_STATE_2026-09-26.md), 배경과 미결 질문은 [Recovery Context](StockScope_RECOVERY_CONTEXT_2026-09-26.md), 전체 재설계 원칙은 [Handoff](StockScope_ASTRA_REDESIGN_HANDOFF_2026-09-27.md)를 따른다.

이번에는 세 설계 문서만 작성했다. 여기 적힌 Migration, 테스트, 운영 절차는 **향후 구현의 요구사항이며 수행 결과가 아니다.** 현재 DB 내용·외부 인증·장중 smoke·배포 상태는 확인하지 않았다.

`VN-P1~VN-P8`과 12개 Stage는 이번 설계의 새 체계다. 기존 `TRACK.*`, `SIM.*`, `VAL.*`, `HOLD.*`, `REALTIME.*`, `NEWS.*`, `UX.*` 이력은 원래 의미로 보존한다. `REALTIME.5`, `HOLD.1-H` 대응, `H.0~H.3`, `DEV.*`를 추정해서 새 ID에 대응시키지 않는다.

명시적으로 요청된 Stage의 구현 범위 안에서 작업한다. 기본 보존 규칙을 바꾸거나 새로운 기능/단계로 범위를 넓혀야 하면 변경 근거와 영향을 설계/작업 명세에 먼저 남긴다. 단순 구현 선택을 이유로 사용자에게 같은 승인을 반복 요청하지 않는다. 현재 사용자의 명시적 지시가 이 문서의 일반 작업 절차보다 우선한다.

## 2. 변경 가능한 영역과 소유권

변경 가능은 해당 Stage의 목적에 필요한 최소 범위를 뜻한다. 디렉터리에 접근할 수 있다는 이유로 주변 계산·저장·화면 전체를 재작성하지 않는다.

| 영역 | 허용되는 확장 | 변경 한계 |
| --- | --- | --- |
| Scanner / Strategy / Risk | 입력 manifest, 명시적 Horizon, 검증된 version 선택·평가 연결. 운영 설정 측 Production selection policy/version·active/rollback reference 관리 | 기존 기본 점수·순위·Risk 차단을 foundation 작업에서 바꾸지 않음. 기존 baseline/운영 정책 저장 구조 우선 재사용, Simulation 승인 artifact/version/hash를 검증해 P5에서 명시 활성화 |
| Backtest / Simulation / Validation | 어댑터·cohort·새 정책 run·보고서·추천 캡처, 전략 registry·평가/제안/승인 artifact/version/hash | 기존 계산 재사용. 완료 후보/실행 결과나 Legacy 의미 불변. Production active/rollback reference는 소유하지 않음 |
| Holdings | 분석/계획 부가 문맥·행동 제안·Recovery 검토·감시 저장 | 기존 원장·lifecycle·손익·계획 적용을 유지하고 새 원장/포지션을 병설하지 않음 |
| Quote / 시장 세션 | 서버 감시 수요와 coverage·실패 상태의 연결 | 기존 REST/WS/SSE·fallback 계약과 구독 제한 유지. latest-only를 lossless로 선언하지 않음 |
| Data Contract | 저장 증명·변경 세대·현재 사용 가능 사유 읽기 | read-only. 입력 준비/분석/네트워크/DB 초기화·마이그레이션을 하지 않음 |
| News / OpenDART | 권한 있는 자료의 근거·시점·관련성 평가 | source 정책·독립 뉴스 표시·기존 공시 규칙 보존. 권한 없는 보존/AI/변환 금지 |
| Frontend | Stage별 UX·상태·근거 연결, 기존 Tracking/Validation workspace의 별도 Feedback/Validation view·cohort 비교, P7 시각 통합 | Tracking 기존 행 액션·service semantics·성과 의미와 문맥·세션·역순 응답 보호 유지. 별도 view 추가는 Tracking 기능 변경이 아님. 전면 개편을 앞당기지 않음 |
| DB / DATA.1 | owner별 additive 확장, P1의 extensible backup manifest 계약과 각 Stage의 자기 상태 backup/restore/integrity 추가 | 원본 직접 교정/삭제 금지. P1에서 미래 Watch/Strategy 운영 상태를 선행 구현하지 않음. Migration은 별도 명시 경로에서만 실행 |
| 연결/배포 | P8의 로컬 credential adapter와 조건부 owner 격리 | 로컬 계좌 ID·credential fingerprint를 사용자 인증으로 대체하지 않음. 공개 Full gate 선행 |

새 논리 책임이 반드시 새 서버나 최상위 모듈을 뜻하지 않는다. 기존 기능과 공유 입력/계산이 있으면 재사용하되, `StrategyAnalysisService`와 Scanner/Holdings의 서로 다른 입력 경로를 같은 것으로 숨기지 않는다.

## 3. 변경 금지와 Frozen 규칙

### 3.1 TRACK.1

[TRACKING_BASELINE](TRACKING_BASELINE.md)의 **CLOSED / FROZEN**을 기본 계약으로 유지한다.

- 기준점은 `market + ticker + recommendation_date + reference_price`다. 같은 기준의 Scanner/Manual 병합과 출처·snapshot을 유지한다.
- 확정 EOD 종가가 D의 기준이며 D+1부터 관찰한다. 미래 기간 부족은 `null`/`-`다.
- Entry/Stop/Target 도달은 관찰이며 체결·도달 순서를 확정하지 않는다.
- Manual-only는 Scanner 성과 근거에 포함하지 않는다.
- ACTIVE는 갱신/종료할 수 있고 직접 삭제할 수 없다. CLOSED는 성과 동결, 기존 규칙에 따른 삭제만 가능하다.
- Tracking의 기존 DB schema, service semantics, 등록·병합·종료·삭제·행 액션 및 성과 의미는 변경하지 않는다. Feedback adapter는 읽는 시각과 source hash를 외부 평가 저장소에 기록한다.
- 기존 Tracking/Validation workspace에 별도 Feedback/Validation view와 근거 이동·cohort 비교 화면을 추가하는 것은 허용한다. 이를 Tracking 기능 자체의 변경으로 해석하지 않으며 기존 Tracking 행 액션을 확장 지점으로 사용하지 않는다.
- 꾸미기·새 대시보드·추측한 엣지 사례를 이유로 Frozen Tracking 기능을 재개하지 않는다. 위 별도 view 추가는 이 금지에 해당하지 않는다. 기존 Tracking 계약 변경은 재현 가능한 실제 결함이나 명시적으로 범위를 승인한 변경만 별도 작업으로 다룬다.

### 3.2 모든 Stage에 적용하는 경계

1. 실제 증권사 매수·매도·정정·취소 주문은 추가하지 않는다. 수동 원장 기록·가상 체결·행동 제안과 구분한다.
2. 실시간 quote·수동 참고가격은 확정 EOD·공식 전략 판단·원장·적용 계획을 덮어쓰지 않는다.
3. 분석은 거래를 만들지 않고, 새 분석·전략 version·알림·Recovery 검토가 계획을 자동 교체하지 않는다.
4. KIS 잔고 변화는 관찰/대조다. 거래나 확정 실현손익을 추정하지 않는다. 관측 범위를 표시한다.
5. 기존 계획의 명시적 적용·version·이전 계획 관계와 손절 완화 차단을 보존한다. Horizon 변경으로 우회하지 않는다.
6. 기존 완료 VAL.1/VAL.2와 당시 snapshot·정책은 불변이다. 20거래일·0% 가정 변경은 새 정책/run에서 수행한다.
7. 신호 D에 D+1 이후 자료를 넣지 않는다. 현재 업종·재무·공시 자료를 과거 시점 자료로 소급 확정하지 않는다.
8. Data Contract reader는 provider 호출·토큰 발급·job 생성/취소·분석·DB 생성/DDL/쓰기·캐시 쓰기를 하지 않는다. 기존 catalog의 initialize가 부작용을 가지면 조회에서 호출하지 않는다.
9. 연구 보고서나 코드가 존재해도 운영 반영으로 보지 않는다. B.2.6/B.2.7의 기존 비반영 경계를 유지하며 새 운영 변경은 근거와 version을 갖춘다.
10. 데이터 부족·표본 부족·낮은 성과·미증명·미지원·운영 미검증을 서로 다른 상태로 표현한다. 점수를 미래 수익 확률로 표시하지 않는다.

## 4. Migration과 기존 데이터의 호환

### 4.1 기본 방식

도메인별 기존 SQLite 저장소를 유지하고 DB 확장이 필요한 책임은 별도 테이블/부가 참조로 추가한다. Production selection policy/version·active/rollback reference는 Scanner/Strategy 운영 설정이 소유하며 기존 production baseline/정책의 저장·게시 구조를 우선 재사용한다. 이를 Simulation DB 테이블로 옮기거나 분리만을 위해 새 DB를 만들지 않는다. 세부 DDL·운영 설정 스키마·호환 API는 Stage 작업 명세에서 확정한다. 기존 의미를 바꾸는 NOT NULL 기본값이나 추정 backfill을 넣지 않는다. Tracking DB는 새 평가를 위해 Migration하지 않는다.

구형 데이터는 원래 의미로 읽는다. Horizon 미지정, 옛 fingerprint 범위, 당시 알 수 없는 version은 미지정/LEGACY/미증명으로 남긴다. 기존 ID·source·시각·수량·금액·계획 연결·완료 상태를 보존한다. 과거 결과를 새 기준으로 평가할 때는 별도 보고서 version을 만들고 원본은 그대로 둔다.

Migration은 조회/API import에 숨기지 않는다. 명시적인 관리 작업에서 대상 DB와 schema version을 확인하고 실행한다. 재실행 안전성, 중간 실패 처리, 잠금/동시 프로세스 조건, rollback 또는 backup 복원 경로를 명세에 포함한다.

### 4.2 실행 전후 요구

| 시점 | 필요한 증거 |
| --- | --- |
| 작업 명세 | 바꿀 owner/테이블·읽기/쓰기 경로·version, 구/신 클라이언트 호환 범위, 데이터 변환/미변환 이유 |
| 사전 dry-run | 임시 DB fixture 또는 권한 있는 복제본에서 row 수·ID·참조·불변 snapshot/hash·금액·상태 분포 비교 |
| 실행 전 | 정확한 대상, backend/worker의 쓰기 중지 또는 지원되는 배타 조건, 검증된 일관 backup과 artifact manifest |
| 실행 중 | transaction 경계·schema marker·부분 실패 기록, retry 시 중복/이중 변환 없음 |
| 실행 후 | integrity/FK/domain 검증, 기존/신규 read path와 계획/원장 회귀, cross-DB 참조·artifact hash 확인 |
| 실패/되돌림 | 검증한 복원 절차, 코드와 schema 호환성 확인, 사용자에게 데이터 보존/복원 결과 보고 |

`simulation.db`와 `holdings.db`, Scanner/Strategy 운영 설정 사이에 전역 원자성이 있는 것으로 가정하지 않는다. 소유 영역의 source commit 후 idempotent 연결 작업으로 완료하고 부분 실패를 표시한다. watch 상태·outbox는 같은 Holdings DB transaction에 둔다. 전략 활성화는 운영 설정 owner가 고정된 Simulation 승인 artifact/version/hash를 검증한 뒤 정책 snapshot과 active/rollback reference를 일관되게 게시한다. 기존 원자적 파일 교체 등 운영 정책 패턴을 우선 재사용하고 실패·동시 활성화·재시작에서도 이전 정상 reference가 보존되는지 검증한다. 임의 재시도로 사용자 command를 두 번 적용하지 않는다.

### 4.3 백업·삭제·보존

현재 DATA.1 기본 백업은 Holdings 중심이고 Market Store는 선택 포함이다. **P1-S1은 extensible backup manifest 계약과 현재 존재하는 DB·입력 근거의 포함·제외·복원 관계를 확정한다.** P1에서 생성하는 증명/artifact의 복원 검증은 포함하지만 아직 생성되지 않은 P4 Watch·P5 Strategy 운영 상태의 구현·복원 검증은 포함하지 않는다.

새 영속 상태를 추가하는 Stage가 자신의 manifest 항목과 backup/restore/integrity 검증을 추가한다. P4는 watch 설정·상태·알림·계획 참조, P5는 Simulation 승인 artifact/version/hash와 Scanner/Strategy 운영 설정의 정책 snapshot·active/rollback reference 및 양측 연결 검증을 담당한다. 다른 Stage도 같은 원칙을 따른다. 기존 키·인증 정보를 일반 백업에 추가하지 않는다.

시장 입력 artifact는 재현 목적으로만 보존하며 일반 조회의 경쟁 OHLC 저장소로 쓰지 않는다. source별 보존 가능 범위·기간·삭제 규칙을 따른다. 삭제 요청을 피해 숨은 원본 사본을 만들지 않는다. 원본 삭제 시 파생 source 참조를 제거/사용 불가로 처리하고 보고서 유효성을 갱신한다. 최소 감사 ID/hash 보존의 범위도 명세에 설명한다.

공개 owner Migration은 P8-S2 이전에 수행하지 않는다. 로컬 데이터를 자동으로 첫 로그인 사용자에게 귀속하지 않는다. DB 엔진 전환도 격리·동시성·복구 요구가 입증된 별도 범위에서 수행한다.

## 5. 데이터 재현성과 입력 동일성

### 5.1 필수 근거

새 판단·평가·운영 변경은 해당 경로에서 실제 사용한 다음 정보를 추적할 수 있어야 한다.

- 계산 경로·코드/엔진/정책 version, 시장/종목·run/decision ID, 실제 선별 범위.
- 시장 기준일, source 발표/수집/사용 가능 시각, 시간대·거래일 기준, cutoff.
- 사용한 행/기간·source 내용 식별자, 보존 가능한 입력 artifact 또는 재생 불가 이유.
- Horizon 정책 version·미지정 여부, 전략 선택 정책과 exit policy의 각각의 version.
- 관찰/가상 체결/사용자 기록 구분, 실행·비용·슬리피지·종료 가정, metric 정의와 관찰 기간.
- 누락·제외·CENSORED·실패·부분 수집 상태, 당시 입력과 현재 입력의 일치 검증 범위.

기존 hash·source_versions·snapshot을 우선 재사용한다. hash 알고리즘/정규화/입력 범위가 다르면 같은 값 이름을 이유로 비교하지 않는다. 정렬·숫자·날짜·결측 표현을 명세에 고정하고 scheme version을 포함한다. 키·토큰·개인 비밀은 hash 입력이나 근거 출력에 포함하지 않는다.

### 5.2 최신성 증명의 lifecycle

생산자 또는 명시적 검증 작업이 증명을 만들고, Data Contract는 그것을 읽는다. 데이터/정책 변경 경로는 변경 세대를 갱신해야 한다. 증명 생성과 사용 사이 변경·경쟁·누락을 검출할 수 없으면 UNVERIFIED를 유지한다. 일부 경로만 증명한 상태를 모든 종목 분석의 최신성 증명으로 확대하지 않는다.

상태 표시에서 **저장 결과가 있음**, **당시 입력으로 재생 가능**, **현재 입력과 같음**, **현재 목적에 사용 가능**을 구분한다. resource별 시각을 하나의 최신 날짜로 합치지 않는다. 이미 생성된 증명의 사용도 source version/세대가 일치하는 동안으로 제한한다.

정확한 원본이 없는데 hash만 남아 있으면 재현 가능으로 판정하지 않는다. 외부 자료의 현재 응답을 과거 입력 대체물로 사용하지 않는다. runtime policy fallback이 발생하면 실제 선택한 fallback version과 이유를 기록한다.

## 6. 테스트 기준과 회귀 방지

현재 CI는 backend Python 3.11/3.14의 앱 import·pytest와 frontend Node 22의 TypeScript/Vite 빌드다. 이것은 현재 테스트 구성의 사실이며 브라우저 E2E나 실제 provider 연결 완료가 아니다. 새 테스트는 실패 가능한 계약·도메인 경계·동시성·복구를 검증한다. 구현 문장을 그대로 반복하는 테스트나 단순 문서 변경을 위한 불필요한 테스트는 만들지 않는다.

구현 시작 시 현재 CI와 실제 환경에 맞는 명령을 확인한다. 기본 명령은 저장소 기준 `python -m pytest -c backend/pyproject.toml backend/tests`, frontend 디렉터리의 `npm run build`다. app import·Migration·통합 테스트는 runtime 쓰기가 사용자 DB로 향하지 않도록 임시 경로/격리 환경을 먼저 확인한다. 설치·외부 연결·운영 DB 접근을 테스트 성공의 숨은 전제로 두지 않는다.

### 필수 회귀 묶음

| 변경 영향 | 기존 근거 | 반드시 유지/추가할 검증 |
| --- | --- | --- |
| Tracking / adapter | `test_tracking_same_baseline_merge_track1104.py`, `test_tracking_integrity_track19.py`, `test_tracking_performance_track1.py`와 frontend Tracking 검사 | 기준·출처·D+1·CLOSED·Manual-only·읽기 무변경·삭제 후 파생 상태. 별도 Feedback/Validation view 추가 후 기존 등록/병합/종료/삭제/행 액션·service semantics·성과 의미 회귀 |
| Replay / Execution | `test_simulation_validation_replay_val1b.py`, `test_simulation_execution_store_val2b.py`, `test_simulation_execution_engine_val2c.py`, `test_validation_breakdown_val3a3.py` | 로컬 전용·source 불변·정책 mismatch·CENSORED·분모·run 버전 분리 |
| Scanner / Strategy / Risk | `test_scanner_determinism_v0214b234b.py`, `test_strategy_engine.py`, `test_risk_engine.py`, production baseline | 기본 입력에서 순위/점수/위험/계획 동등성, 미래 데이터·업종 시점 경계, 승인된 정책 차이만 반영 |
| Backtest | `test_backtest_accuracy_v0194.py`, `test_multi_strategy_v020.py`, `test_production_exit_policy_v0214b21.py` | D+1 진입·일봉 보수적 순서·비용·실제 활성 정책/fallback·새 정책 비교 |
| Holdings | `test_holdings_ledger1_opening_balance.py`, `test_holdings_lifecycle_hold1c.py`, `test_holdings_kis_sync_hold1d.py`, `test_holdings_pnl1_performance.py`, `test_holdings_plan1_g6_management.py` | 원장·손익 범위·명시 계획·version 충돌·손절 완화 차단·부분/전량 종료·제안 무부작용 |
| Data Contract | `test_data_contract_read_only_reader.py`, `test_data_contract_api.py`, `test_data_contract_websocket.py` | 누락 DB 생성 없음, SQL/네트워크 쓰기 없음, 표시/사용 구분, 시각 분리·입력 갱신 경쟁 |
| Realtime / Watch | `test_quote_sse.py`, `test_quote_websocket_transport.py`, `test_quote_service.py`, `test_market_session.py`, Holdings live 테스트 | 기존 전달/limit·latest-only·오래된 응답 보호, 새 episode·중복·gap·재시작·outbox·계획 무변경 |
| News / DART | `test_news1_naver.py`, `test_strategy_event_integration.py`, `test_event_risk.py` | provider policy·캐시·오류 격리·비밀 비노출, 공시와 뉴스 경로 분리·시간 누수 |
| Runtime / 배포 | `test_data1_runtime_tools.py`, `test_no_order_routes.py`, `test_kis_read_only.py` | backup/restore·Migration·주문 부재, 새 owner/cache/SSE/job 격리와 secret lifecycle |
| Frontend UX | `test_ux_redesign1_contract.py`, `test_ux_flow1_contract.py`, `frontend/tests` | 기존 정적 계약 유지, 새 실제 브라우저 동선·키보드·reload·오프라인·느린 응답·문맥 보존 |

모든 Stage에서 모든 검사를 무작정 반복하지 않는다. 영향받는 도메인의 의미 있는 검사를 먼저 실행하고, 구현 변경의 전체 회귀 gate에서는 기존 backend 전체 suite와 frontend build를 포함한다. 브라우저 행동을 바꾼 Stage는 실제 상호작용 검증을 추가한다. 통과 후 새로운 변경/실패/미해결 위험 없이 동일 검사를 반복하지 않는다.

신규 상태/시간 로직은 주입 가능한 시계·fake provider·고정 입력으로 검증한다. 실제 운영 키로만 재현되는 테스트를 기본 CI에 넣지 않는다. 장중 smoke는 별도 결과로 환경·시각·버전·관찰 범위·실패/공백을 기록하며 못 수행하면 미검증으로 남긴다.

## 7. Validation 기준

테스트는 코드가 계약대로 동작하는지, Validation은 판단·비교 근거가 타당한지, UAT는 사용자가 실제 흐름을 이해하고 완료하는지 검증한다. 세 가지 증거를 서로 대신하지 않는다.

### 7.1 평가 프로토콜

평가를 실행하기 전에 대상 질문, 대조군, 기간/시장/universe, 전략·Horizon·입력·정책 version, 학습/조정과 평가 구간, 지표·분모·제외 규칙·비용/체결 가정, 허용된 의사결정 범위를 고정한다. 결과를 보고 프로토콜을 바꿨다면 새 평가 version으로 기록한다.

시간 분리 평가에서 label/보유기간이 경계를 넘는 누수와 동일 종목/날짜의 상관 표본을 고려한다. 현재 시장 구성만으로 과거 상장폐지까지 포함한 결과라고 주장하지 않는다. 당시 사용 가능 시각을 증명할 수 없는 입력은 해당 과거 평가에서 제외하거나 명시적으로 제한된 결과로 분리한다.

추천 관찰, 실행 가정, 실제 사용자 원장 성과를 별도 집계한다. 기준가격·진입 시점·기간이 다른 MFE/MAE를 같은 지표로 합치지 않는다. 같은 Scanner 실행/후보가 Embedded Scanner·Tracking 등 여러 경로에 나타나도 동일 평가 단위에서 중복 집계하지 않는다.

보고서에는 전체·실행 가능·미실행·미성숙·제외·실패 수, source 비율, 비용 민감도, 손실/낙폭·국면 편중·불확실성을 포함한다. CENSORED를 실현손익이나 0%로 만들지 않는다. 표본 부족이면 승격/예측/성과 우수 결론을 내리지 않는다.

### 7.2 운영 반영 gate

- P5는 장기/최근·국면·Horizon별 근거와 승인 절차를 사용한다. Q7의 임계값·최소 표본·평가 구간이 미정이면 이를 숫자로 채워 자동 승격을 활성화하지 않는다.
- 승인 artifact/version/hash는 Simulation에서 제공할 수 있지만 활성화는 Scanner/Strategy 운영 설정 owner가 검증한 뒤 명시적으로 수행한다. Production active/rollback reference와 실행에 사용할 정책 snapshot/version은 운영 설정 측에 둔다. 실행은 Simulation의 최신 승인 행에 직접 의존하지 않으며 연구 재실행/행 변경만으로 active reference가 바뀌어서는 안 된다. 기존 baseline·정책 version/근거 서명·활성화·원자적 게시·fallback 구조를 우선 재사용하고 selection과 exit policy의 의미는 분리한다. 진행 중 run과 기존 보유 계획은 version을 유지한다. rollback 대상과 실패 감지 기준을 명세에 둔다. 소유권 분리·hash 불일치·동시 활성화·rollback·운영 설정 복원을 P5 검증에 포함한다.
- 자동 Rotation은 기본 비활성이다. 독립 평가·prospective 관찰·shadow·rollback 증거를 갖춘 별도 범위 결정이 필요하다.
- P6의 뉴스는 자료 권한과 시점 corpus, 관련성 품질, 기존 분석 대비 증분 효과가 선행한다. 예측은 별도 평가·표현 기준을 갖추기 전 제품 점수/확률로 노출하지 않는다.
- Recovery 수동 검토 기능의 완료는 자동 진입/해제·추가매수 정책의 성능 입증을 의미하지 않는다.

### 7.3 사용자 경험 검증

UAT 기록은 사전 조건·fixture/환경·실행 행동·기대/실제 결과·근거 화면/로그·미실시 항목을 포함한다. 계획 적용, 평가 비교, 알림 확인, 연결 테스트의 주요 동선에서 사용자가 제안/적용, 관찰/체결, 자료 부족/성과 약함, 기능 테스트/운영 검증을 구분할 수 있어야 한다.

시각 변경만으로 판단 상태의 의미를 바꾸지 않는다. 읽기만 하는 화면이 계산·등록·준비를 조용히 시작해서는 안 된다. 실제 브라우저 UAT가 없으면 소스 문자열 검사나 build를 그 완료 증거로 보고하지 않는다.

### 7.4 P7 Visual 디자인·리뷰·UAT 검수 기준

최종 Visual 방향은 **Editorial + Product UI, typography 중심, low-glare dark, restrained light, 데이터 중심 시각화**다. 반복적인 둥근 카드, 흔한 3분할 통계 카드, 의미 없는 badge, pastel gradient 남발, generic AI-generated SaaS 느낌, 박스 나열형 관리툴 스타일을 피한다. 이는 단순 참고가 아니라 P7 디자인·리뷰·UAT와 완료 판정에 적용하는 필수 기준이다.

대표 화면을 dark/light와 주요 화면 폭에서 대조해 다음을 리뷰/UAT 기록으로 남긴다: 글자 크기·굵기·간격에 의한 결론/선택지/근거의 위계, 두 테마의 눈부심·대비·가독성, 실제 비교·판단에 도움이 되는 데이터 시각화, 위의 반복 카드·무의미한 장식·박스 나열 패턴의 부재. 기능 UAT 통과만으로 Visual 검수를 대체하지 않으며, 기준 미충족 화면은 수정·재검수 전 P7 완료로 판정하지 않는다.

## 8. Stage 완료 정의와 상태 보고

각 Stage에는 최소 다음 다섯 상태를 분리해 기록한다. 아래 용어는 작업 보고 기준이며 기존 runtime enum을 재정의하지 않는다.

| 축 | 보고 내용 |
| --- | --- |
| 범위/결정 | Stage 명세·의존성·보존 경계 확정 여부, 조건부 분기 선택/보류 |
| 구현 | 코드·저장·UI·복구가 명세의 지원 범위를 충족하는지 |
| 테스트 / UAT | 수행한 검사·환경·결과·실패·미실시 항목 |
| 성능/근거 | Validation 프로토콜·표본·결과와 한계, 승격/예측 등 결론의 허용 범위 |
| 활성화/운영 | feature/policy 활성 여부, 장중/외부 연결·배포 검증 상태와 rollback |

기본 Definition of Done은 다음과 같다.

1. 현재 구현을 재사용하는 지점과 새 변경이 명세·diff에서 일치한다. 범위 밖 변경을 포함하지 않는다.
2. 입력/정책/결과와 새 영속 상태가 추적 가능하고, 구형 자료를 추정으로 채우지 않는다.
3. 해당 도메인 회귀·오류·동시성·부분 실패·복구 테스트와 필요한 브라우저 UAT가 통과한다.
4. 새 영속 상태를 추가한 Stage는 자신의 manifest 확장·backup/restore/integrity 증거를 갖춘다. P1-S1은 extensible 계약과 현재 DB·P1 입력 근거 범위로 한정한다. Migration이 있으면 dry-run·전후 무결성·재실행/rollback 증거가 있다. 사용자 runtime에 실행한 경우 그 사실을 따로 기록한다.
5. Validation의 질문·프로토콜·분모·부족 표본·실제 결론이 기록된다. 도구 완료를 성능 성공으로 바꾸지 않는다.
6. 기존 Frozen/주문 금지/read-only/원장·계획 경계를 보존한다. 의도한 예외는 별도 승인된 범위와 증거가 있다.
7. 문서·API/저장 계약·기능 지원/보류 목록·남은 UNKNOWN이 실제 결과와 일치한다.
8. P7은 §7.4의 Editorial + Product UI·typography·테마·데이터 시각화 및 회피 패턴 기준의 디자인/리뷰/UAT 검수 증거를 갖춘다.

P6에서 권한이 없어 보류한 경우는 **범위 판정 완료 / 분석 기능 미구현**으로 기록한다. P5에서 표본이 부족하면 **운영 도구 완료 / 승격 보류 / 자동화 비활성**으로 기록한다. P4 장중 smoke 미실시와 P8 공개 격리 gate 미충족도 각각 운영 미검증·공개 Full 보류로 남긴다. 이를 전체 기능 COMPLETE로 합치지 않는다.

## 9. Stage 작업 명세 작성 규칙

각 구현 요청은 다음 틀을 사용한다. 빈 칸은 '해당 없음'과 이유 또는 미결정/차단 조건을 적으며 임의의 과거 번호로 채우지 않는다.

```text
설계 버전 / Stage ID / 단계 이름
구현 시작 HEAD / 현재 변경 상태 / 참조 근거
목적 / 왜 지금 필요한가
현재 존재하는 기능과 코드·테스트 근거
재사용할 코드 / 데이터 / 저장 구조
새 구현 범위 / 명시적 제외 범위
선행 조건 충족 증거 / 후속 단계 계약
Backend / Frontend / DB·저장 / 외부 데이터 변경
조회·명시적 계산·적용·활성화의 구분
입력·정책·결과 version과 시점 / source·owner
Migration·호환·backup·복원·삭제·rollback
기존 보존 경계 / Frozen 영향 없음 또는 별도 변경 근거
정상·부족·실패·취소·중복·동시성·재시작 시나리오
테스트 계획 / 회귀 묶음 / 브라우저 검증
Validation 프로토콜 / 대조군 / 분모 / 미성숙 처리
UAT 사전 조건·행동·기대 결과
완료 조건 / 운영 활성화 조건 / 성능 결론 허용 범위
위험 / 미결정 사항 / 증거 수집 주체·방법·해결 시점
Q1~Q15 중 관련 질문 / 상태 변경 근거
```

Stage 명세는 경로·스키마·API·정책값을 구현 가능한 수준으로 구체화해야 한다. Architecture가 미결정으로 남긴 Horizon 기간, Recovery 수치, 전략 평가 임계값, secret 저장/배포 구조가 해당 기능 구현에 필수라면 먼저 결정하거나 그 분기를 차단한다. 단순히 TODO를 달고 임의 기본값으로 운영하지 않는다.

서버/DB 구조나 기본 보존 경계를 바꾸는 결정을 구현 명세의 작은 내부 선택으로 숨기지 않는다. 대안·선택 이유·영향·되돌림을 기록하고 Architecture/Roadmap/Baseline을 일관되게 갱신한다. 이미 승인된 Stage 범위 안의 일반 구현 판단은 자율적으로 진행한다.

## 10. UNKNOWN 관리와 설계 변경

질문 상태의 기준은 [Architecture §13](StockScope_MASTER_ARCHITECTURE_vNext.md#questions)이다. Q1~Q15 모두에 현재 상태·답변/남은 문제·위치/단계가 있다. 초기 집계는 **설계에서 해결 8 / 아직 미결정 4 / 추가 증거 필요 3**이다.

질문이 해결되었다고 갱신할 때는 근거 문서·code/test·평가 보고서·결정 시점을 기록한다. 새 목표 구조를 결정했다는 이유로 과거 Position Manager/Realtime Watch의 공식 형태를 발견한 것으로 쓰지 않는다. `REALTIME.5`, `HOLD.1-H`, `H.0~H.3`, `DEV.*`의 역사적 UNKNOWN은 원본 증거가 생길 때만 바뀐다.

문서 간 변경은 책임(Architecture), 순서/완료 조건(Roadmap), 구현·검증 규칙(Baseline)의 영향을 함께 검토한다. 과거 입력 문서와 완료 이력을 조용히 수정하지 않는다. 구현 시작 HEAD가 이번 설계 기준과 다르면 변경 차이를 먼저 조사하고 사실·설계·추정을 구분해 작업 명세에 남긴다.

## 2026-10-06 통합 구현 불변식

Cleanup으로 개별 버전 설명 문서를 제거한 뒤에도 다음 계약은 이 문서에서 유지한다.

### Strategy / Risk / Entry
- 적합도 점수는 수익확률이 아니다.
- NO_TRADE / Risk Gate가 우선한다.
- 구조적 가격·ATR·전략 owner를 보존하고 새 threshold를 문서 정리 과정에서 만들지 않는다.
- manual/reference 가격은 EOD 원본을 덮어쓰지 않는 별도 scenario다.
- Holdings quantity/plan은 reference/JEV가 자동 변경하지 않는다.

### Scanner / Ranking / Evidence
- 현재조건·랭킹과 과거 evidence를 분리한다.
- 반환 후보 identity, selection policy, exit policy, cache/input identity를 보존한다.
- historical-first 같은 옛 표현을 현재 production 정책으로 승격하지 않는다.

### Backtest / Execution
- D+1/일봉 순서·비용·CENSORED/NOT_EXECUTED/NO_ENTRY_DATA 상태를 구분한다.
- 연구 exit policy와 운영 exit policy는 별도 pin이다.
- 미성숙/CENSORED를 0수익으로 채우지 않는다.

### Fundamental / Event / Relative Strength
- 최신 공식 실적과 연간 장기 지표의 기간 의미를 분리한다.
- 상대강도는 시장/업종 비교 근거이며 수익확률이 아니다.
- Event/reference 표시 가능성과 AI_TRANSFORM/PREDICTION_INPUT 권한을 분리한다.

### UX / Input / Session
- 결론→행동→핵심 근거→상세 순서를 우선한다.
- 관찰값/체결값, 표시값/계산값, EOD/Preview를 혼동하지 않는다.
- 입력 변경은 stale/revision 규칙을 적용하고 back/reload/reanalysis에서도 identity를 보존한다.
- 진행/취소/오류는 기존 결과를 조용히 덮어쓰지 않는다.

### Data / Performance / Fresh setup
- Market store/cache/network 책임을 분리하고 API budget·progress·cancel을 명시한다.
- 역사 성능 측정치를 현재 SLA로 자동 승격하지 않는다.
- `setup.ps1`, runtime bootstrap/state, fresh-clone regression이 현재 setup owner다. 과거 “미착수” task spec은 더 이상 현재 상태가 아니다.

### R5R / JEV
- R5R Method V2 + Policy V1 + Binding V1 및 deterministic evaluator가 현재 authority다.
- R5R actual evaluation은 `NEXT-6E-R5R-EVALUATION`으로 부른다.
- JEV AI reviewer 평가는 `JEV-REVIEWER-EVALUATION`으로 분리한다.
- JEV Phase 1은 shadow reviewer이며 production rank/action/Risk/plan write 권한이 없다.
