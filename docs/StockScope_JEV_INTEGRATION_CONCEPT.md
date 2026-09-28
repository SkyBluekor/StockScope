# StockScope Jev Integration Concept

작성일: 2026-09-28 (Asia/Seoul)  
문서 지위: 향후 후보 검토용 개념 설계 · 도입 결정 및 구현 명세 아님  
검토 기준: `feature/ux-redesign-1`, HEAD `c4e690aa44f0b67c246bdac315fb32862abda459` (`feat: add P6 evidence quality gate`)

> Jev 도입 자체가 목적이 아니다. 실제 Historical / Execution Validation 결과에서 StockScope의 판단 성능을 개선하는 경우에만 채택한다.
>
> 지금은 구현하지 않는다. 이번 작업의 산출물은 이 문서 한 개뿐이다.

## 0. 현재 구현 확인과 문서 해석

### 0.1 확인 범위와 한계

현재 소스와 테스트 소스, 최신 handoff, 관련 아키텍처·구현 문서를 읽은 후 아래 후보를 정리했다. **현재 사실**, **향후 후보**, **미결정 정책**을 구분한다. 테스트 실행, runtime DB 조회·Migration, 외부 서비스 접속, 운영 활성화, 브라우저 UAT는 이번 작업에서 수행하지 않았다. 따라서 코드의 존재를 실제 데이터 충분성·로컬 Migration 완료·운영 성능 입증과 동일시하지 않는다.

Jev는 사용자가 지정한 AI Decision Model 후보명이다. 이 문서는 실제 공급자, 제품 식별자, API 제공 여부, 모델 성능, confidence/probability 반환 지원, 과거 version 재사용 가능성, 가격·지연시간·데이터 처리 조건을 확인하거나 보장하지 않는다. 관련 표현은 향후 요구사항 또는 검토 가정이며, 도입 재검토 때 공식 자료로 확인해야 한다.

판단 근거는 현재 코드 → 최신 상태 문서 → 과거 설계 문서 순으로 확인한다. 목표 아키텍처는 현재 기능 완료 선언으로 읽지 않는다.

| 확인 문서 | 사용 방식 |
| --- | --- |
| [최신 handoff: P5-S1-E 완료](StockScope_HANDOFF_2026-09-28_P5S1E_COMPLETE.md) | 제품 원칙·P1~P5 경계의 상태 근거. 기준 HEAD는 `4e781b5`이며 현재 HEAD보다 이전이다 |
| [Master Architecture vNext](StockScope_MASTER_ARCHITECTURE_vNext.md) | 도메인 책임·저장 소유권·명시적 계획 적용·Research/Production 분리 원칙 |
| [Implementation Baseline vNext](StockScope_IMPLEMENTATION_BASELINE_vNext.md) | Frozen Tracking, 완료 검증 결과 불변, 조회의 읽기 전용 경계 등 보존 기준 |
| [Development Roadmap vNext](StockScope_DEVELOPMENT_ROADMAP_vNext.md) | P1~P8 의존성과 아직 결정하지 않은 정책. 현재 진행 상황은 코드와 handoff로 보정 |
| [P2-S1 구현 기록](StockScope_VN_P2_S1_IMPLEMENTATION_2026-09-27.md), [P2-S2 구현 기록](StockScope_VN_P2_S2_IMPLEMENTATION_2026-09-27.md), [P3-S1 구현 기록](StockScope_VN_P3_S1_IMPLEMENTATION_2026-09-27.md) | Feedback·Prospective·Holdings의 기존 계약과 한계 |
| [Tracking Baseline](TRACKING_BASELINE.md) | TRACK.1 CLOSED/FROZEN·D+1 관찰·Manual-only 제외·CLOSED 성과 동결 |

위 vNext 문서들이 참조하는 `StockScope_CURRENT_STATE_2026-09-26.md`, `StockScope_RECOVERY_CONTEXT_2026-09-26.md`, `StockScope_ASTRA_REDESIGN_HANDOFF_2026-09-27.md`는 현재 checkout의 `docs/`에 없다. 해당 문서를 읽었다고 주장하거나 유실된 내용을 복원하지 않는다. 이용 가능한 최신 handoff와 현재 코드를 기준으로 삼았다.

### 0.2 실제 구조와 상태

| 영역 | 현재 코드에서 확인한 사실 | Jev 검토에 주는 조건 |
| --- | --- | --- |
| Scanner | [`StockScannerService`](../backend/app/backtest/scanner.py), `VERSION=0.21.3.8`. EOD universe 필터 → 빠른 전략/Risk 평가 → 제한된 후보 분석 → 과거 근거 부착 → 최종 우선순위. 현재 조건·Risk·진입 근접도·전략 적합도로 순위를 정하며 3년 근거는 참고 정보 | 하나의 보편적인 Scanner 확률 점수가 없다. 사전 필터에서 탈락한 전체 종목을 Jev가 평가했다고 볼 수 없음 |
| Strategy / Risk | [`StrategyEngine`](../backend/app/strategy/engine.py)은 현재 10전략을 평가하고 허용된 Pool을 필터링한다. 적합도는 수익확률이 아니다. Risk Gate는 Pool과 독립이며 차단 시 NO_TRADE가 우선한다. 기존 최소 적합도 55 기준이 존재. [`RiskEngine`](../backend/app/risk/engine.py)은 구조·ATR 기반 손절/목표·손익비를 계산 | Jev가 안전 차단을 점수 합산으로 해제하거나 적합도를 확률로 재해석하면 안 됨. 55는 현재 코드 기준이며 새로운 AI 임계값 제안이 아님 |
| Strategy Governance | [`strategy_governance.py`](../backend/app/simulation/strategy_governance.py), [`strategy_evidence.py`](../backend/app/simulation/strategy_evidence.py), [`strategy_change.py`](../backend/app/simulation/strategy_change.py)에 Registry·평가·제안·승인 artifact가 있다. 초기 운영 10전략은 OPERATING/UNVERIFIED로 등록하며 NO_TRADE는 Registry 전략이 아님 | 운영 중이라는 사실이 검증 완료를 뜻하지 않음. Jev의 제안은 운영 승격 권한이 아님 |
| Production 선택 정책 | [`production_selection_policy.py`](../backend/app/strategy/production_selection_policy.py)의 불변 snapshot·active/rollback·실행별 `SelectionPolicyPin`. Production은 운영 파일을 읽으며 Simulation 최신 행을 자동 채택하지 않는다. active 호환성 실패 시 호환 rollback, 이어 Legacy current 10 fallback | 미래 AI/집계 정책도 실행 중 고정·명시적 활성화·rollback이 필요. 기존 selection과 exit policy의 의미를 합치지 않음 |
| Historical Validation | [`validation_catalog.py`](../backend/app/simulation/validation_catalog.py), [`validation_replay.py`](../backend/app/simulation/validation_replay.py)에 과거 Scanner 후보 재생·당시 snapshot/hash·입력 식별이 있다. Replay는 로컬 Market Store 경로 | 기존 후보 재생을 활용하되 AI 결과는 별도 비교 근거. 완료 run을 덮어쓰지 않음 |
| Execution Validation | [`execution_catalog.py`](../backend/app/simulation/execution_catalog.py), [`execution_engine.py`](../backend/app/simulation/execution_engine.py), [`execution_service.py`](../backend/app/simulation/execution_service.py)가 저장 후보를 기존 simulator로 가상 실행. 신호는 D까지, 실행은 D+1부터. 기존 VAL.2는 최대 20거래일·왕복 비용 0%, CENSORED·정책 불일치 처리 | 기존 실행 계산은 결정론적으로 유지. 다른 기간·비용 가정은 새 정책/run에서 비교 |
| Feedback / Prospective | [`feedback/adapter.py`](../backend/app/feedback/adapter.py)는 Tracking·Validation·Execution·Backtest 원본을 읽는다. [`prospective/`](../backend/app/prospective/service.py)는 완료 Scanner 반환 후보를 사후 선택 전에 보존하고 시간 분리 평가. 최소 표본 정책·성능 우수 판정·승격·자동 Rotation은 승인되지 않음 | Jev 평가도 분모·누락·편향·표본 성숙도를 보존. 현재 인프라 존재를 채택 근거로 오인하지 않음 |
| Holdings / Plan | 원장·lifecycle·손익·KIS 잔고 관찰과 [`analysis_history.py`](../backend/app/holdings/analysis_history.py)의 분석 리비전, [`management.py`](../backend/app/holdings/management.py)의 계획 version이 있다. [`decision_support.py`](../backend/app/holdings/decision_support.py)는 확정 EOD·최신 분석·적용 계획으로 HOLD/STOP/TAKE_PROFIT 등 판단과 검토 선택지를 생성. ADD는 BLOCKED. stale·수량/계획 변경·손절 완화 차단 및 명시적 적용 | 유지/강화/완화/재검토는 제안 의미로 한정. Jev 출력이 적용 계획·원장·추가매수 정책을 바꾸지 않음 |
| Recovery | [`recovery.py`](../backend/app/holdings/recovery.py)는 동일 포지션의 수동 검토 시작·평가·판단 연결·종료. thesis: INTACT/WEAKENED/BROKEN/UNKNOWN, action: UNDECIDED/HOLD/REDUCE/EXIT/ADD_REVIEW | 자동 물타기·회복확률·자동 시작/종료가 아님. ADD_REVIEW는 추가매수 허용이 아님 |
| Watch | [`watch/coordinator.py`](../backend/app/watch/coordinator.py)의 서버 시세 소비·수요 lease, [`state_machine.py`](../backend/app/watch/state_machine.py)의 confirmation/rearm, [`storage.py`](../backend/app/watch/storage.py)의 상태·알림. [`policy.py`](../backend/app/watch/policy.py)의 Production policy는 수치 기준 미승인으로 `enabled=False` | 구현과 운영 활성화를 분리. Jev가 Watch를 활성화하거나 가격 관찰·confirmation·계획 변경을 대신하지 않음 |
| Horizon | [`horizon.py`](../backend/app/horizon.py)에 LEGACY_UNSPECIFIED와 SHORT/MEDIUM/LONG 문맥 계약. 명시 Horizon은 EVALUATION_PENDING이며 기간·Review Cycle·Time Stop 등의 수치 정책이 미승인 | Horizon 간 충돌 조정은 후속 후보. 기존 20일 검증이나 5/10/20일 관찰을 투자 의도로 역추정하지 않음 |
| News / 기존 EventRisk | [`news/policy.py`](../backend/app/news/policy.py)의 NAVER NEWS.1은 표시/표시 정규화 경로이며 AI/변환 불허. [`market/event_risk.py`](../backend/app/market/event_risk.py)의 기존 OpenDART 공시 규칙 분석은 단일 종목 Strategy의 event_risk/Risk Gate에 연결 | 뉴스 패널 표시와 AI 입력 허용은 별개. 기존 OpenDART 연계도 별도 P6 연구/AI 권한으로 확대 해석하지 않음 |
| P6 Event Evidence | [`event_evidence/`](../backend/app/event_evidence/__init__.py)에 source 권한·시간 계약, 불변 SourceRef/Event 저장·hash 검증, entity 관련성, canonical resolution/중복·정정·철회, as-of Evidence Quality가 있다. Quality는 USABLE/LIMITED/INSUFFICIENT/BLOCKED와 사용 범위 판정이며 방향 점수·확률·Strategy 입력이 아님 | 기반 계약 개발은 진행됐지만 Jev 입력·뉴스 예측·Production 판단 통합이 완료된 상태는 아님 |

최신 handoff는 P5-F/API·UI와 P5-G/복구를 NEXT, P6를 LATER로 기록한다. 현재 코드에는 [`strategy_governance` API](../backend/app/api/strategy_governance.py), [`StrategyOperationsPanel`](../frontend/src/components/StrategyOperationsPanel.tsx), [`backup_runtime.py`](../tools/data/backup_runtime.py)/[`restore_runtime.py`](../tools/data/restore_runtime.py)의 P5 운영 상태 연계, P6 기반 모듈이 추가되어 있다. 따라서 handoff의 NEXT/LATER를 그대로 현재 미구현 판정으로 사용하지 않는다. 다만 이번 소스 검토만으로 최신 단계 전체의 운영/UAT 완료를 선언하지 않는다. 기본 Production 승인 프로토콜은 여전히 `activation_eligible=False`, `q7_precommitted=False`다.

Scanner의 고정 baseline manifest는 [`scanner-production-baseline_0.21.3.8.json`](../backend/runtime/baseline/scanner-production-baseline_0.21.3.8.json), ID는 `SS-SCANNER-0.21.3.8-dd1e7a75ab4aaac9`다. 이번 작업은 baseline 파일과 fingerprint를 변경하거나 재동결하지 않는다.

### 0.3 최종 판단이 생성되는 현재 흐름

현재는 공통 Jev 호출 지점이나 모든 경로를 통합하는 단일 Decision Aggregation 계층이 없다. 아래 경로들은 관련 계산을 재사용하지만 입력과 결과 의미가 다르다.

```text
[Scanner]
확정 EOD / 시장·업종 입력 + 실행 시작 시 SelectionPolicyPin
  → universe·유동성·자료 필터
  → 빠른 Strategy 평가 / 조건 상태 / Risk / readiness
  → 제한된 후보의 현재 판단·진입 가이드
  → 제한된 최종 후보군의 3년 Historical Evidence 부착
  → 현재 조건 → Risk → 진입 근접도 → 전략 적합도 순위
  → 후보/action 반환 → 완료 실행의 Prospective 캡처 경로

[단일 종목 상세 분석: StrategyAnalysisService]
KRX 이력 + 시장/업종 상대강도 + OpenDART 이벤트·재무
  → 동일 SelectionPolicyPin으로 EOD / 수동 참고가격 시나리오 평가
  → Risk / 보유 관점 가이드 / 눌림 확인 / 투자 스타일
  → AnalysisHub 요약·전략/위험 payload 반환

[Holdings]
로컬 Market Store → Scanner 현재 경로 재사용 → 분석 리비전
  + 포지션 수량·평균가 + 적용 계획 version + 확정 EOD 평가가격
  → HoldingDecisionSupportService의 판단/대안/충돌·stale 검사
  → 사용자 검토·선택 → 명시적 계획 적용
  → 기존 계획을 기준으로 관찰하는 live 평가 / Watch

[Recovery]
사용자의 수동 검토 시작 → 논리 상태·근거 평가 → 보유 판단 연결
  → 사용자 검토·수동 종료; 계획 변경은 기존 명시적 적용 경로
```

Scanner 빠른 경로는 selector eligible/score 상위 3개를 현재 조건·Risk로 재평가한다. Jev에 현재 선택된 전략만 주면 선택 이전 전략 충돌 전체를 검토한 것으로 볼 수 없다. Holdings의 [`analysis.py`](../backend/app/holdings/analysis.py)는 네트워크를 금지하는 로컬 EOD adapter이며 업종 입력도 `NONE_PRODUCTION_SAFE`다. 상세 분석의 뉴스·공시·재무 문맥이 Holdings에 모두 전달된다고 가정해서는 안 된다. 이 차이는 향후 입력 계약 검토 대상이다.

[`candidate_priority.py`](../backend/app/backtest/candidate_priority.py)의 실제 순위 키는 현재 tier·미충족 조건·Risk·진입 거리·전략 적합도다. 과거 근거는 설명에 사용하며 현재 순위 키에는 들어가지 않는다. 정확한 동률 안에서는 기존 구조 목표 거리와 안정된 종목코드 순서로 정리한다. Jev 비교에서 현재 기준을 단순한 `Scanner Score` 한 숫자로 축소하지 않는다.

### 0.4 논의 아이디어와 현재 구조의 충돌

| 아이디어 | 현재 구조와의 충돌 | 이 문서에서의 처리 |
| --- | --- | --- |
| Scanner + Jev + Historical Performance를 바로 합산 | 현재 과거 근거는 순위와 분리되어 있으며 점수/확률의 의미도 다름 | 연구용 집계 가설로만 보존. baseline 대조·시점 검증·별도 변경 검토 필요 |
| Jev가 NEWS.1 기사나 기존 공시를 바로 분석 | 현재 source 정책은 AI 사용을 허용하지 않음 | source별 명시적으로 허용된 자료가 확보되기 전 해당 입력 경로 보류 |
| AI가 보유 계획을 자동 강화/완화 | 새 분석·실시간 가격·알림이 기존 계획을 자동 교체하지 않는 계약과 충돌. 손절 완화는 차단 | 자동 재평가·제안 생성까지만 후보. 실제 적용은 사용자 명시적 적용; 완화 우회 금지 |
| High Volatility에서 Risk Engine 비중을 조정 | Risk Gate는 성과와 교환할 수 있는 가중 점수가 아님 | 안전 제약을 먼저 고정하고 허용된 후보 안에서만 AI 영향 조정 |
| Horizon·회복 가능성·최소 표본을 AI가 정함 | 수치 정책 미승인, 회복확률 미정의, Q7 미결정 | AI가 미결정 정책을 대체하지 않음. 근거와 프로토콜 확정 이후 재검토 |
| 최근 Jev 성과가 좋으면 자동 Production 변경 | 근거 → 제안 → 승인 → 명시적 활성화·run pin 경계와 충돌 | 추적 결과는 변경 제안의 근거. 운영 가중치 자동 변경은 이번 후보의 기본 범위 밖 |

## 1. Jev 도입 목적

목표는 기존 StockScope 판단 성능 보조, 복수 신호 충돌의 의사결정 개선, 손실 위험을 제한하며 기대수익이 높은 계획 선택 보조, 규칙 기반 판단의 복합 문맥 처리 보완, 다른 AI Decision Model로 교체 가능한 확장 구조 확보다. AI 기능의 존재나 설명의 유창함만으로 채택하지 않는다.

> Jev 도입 자체가 목적이 아니다. 실제 Historical / Execution Validation 결과에서 StockScope의 판단 성능을 개선하는 경우에만 채택한다.

평가 도구 구현, 설명 품질 개선, 기대수익 개선, 실제 운영 가능성은 서로 다른 판정이다. 현재 Jev가 이 중 어느 항목을 개선한다는 증거는 없다.

## 2. StockScope가 중심이라는 원칙

Jev는 StockScope 핵심 판단 시스템을 대체하지 않는 보조 후보다. 데이터 수집·정량 계산·판단 문맥·평가·계획 적용의 owner는 기존 StockScope다. Jev 미사용·장애·교체 상태에서도 기존 기능이 동작해야 한다.

아래는 **향후 개념 구조**다. 현재 이런 계층이 구현되어 있다는 뜻이 아니며 Validation 결과는 검증 근거로 제공되는 관계이지 매 판단마다 검증을 새로 실행하는 단계가 아니다.

```text
Market / Holdings / 허용된 Event Data
                 ↓
StockScope Existing Engines
  ├ Scanner / Strategy
  ├ Validation에서 확보한 당시 사용 가능한 근거
  ├ Risk
  ├ 기존 EventRisk / 허용된 Event Evidence
  └ Holdings / Recovery 문맥
                 ↓
Existing Quantitative Decision + 고정된 입력 문맥
            ┌────┴────┐
            ↓         ↓
   Existing Engine   Jev 보조 의견
            └────┬────┘
                 ↓
Decision Aggregation 후보 책임
                 ↓
Risk Guardrail / 지원 정책 / stale 재검사
                 ↓
Final Decision / Plan Proposal
                 ↓
보유 계획 변경이 필요하면 사용자 검토 → 명시적 적용 → version 보존
```

기존 Risk Gate는 분기 이전에도 유지하고 집계 후에도 재확인한다. 최종 Risk Guardrail을 그렸다는 이유로 기존 위험 판단을 뒤로 옮기지 않는다. `Final Plan`은 적용 전 제안과 실제 적용 계획을 구분한다.

## 3. Jev의 역할 후보와 맡기지 않을 책임

다음은 실제 코드의 문맥과 연결한 후보이며 현재 호출 지점·API·새 서비스 구현을 확정하지 않는다.

| 후보 지점 | 활용 가설 | 필요한 입력과 한계 |
| --- | --- | --- |
| Scanner 빠른/최종 판단 뒤의 전략 충돌 검토 | 여러 eligible 전략의 조건·반대 근거가 충돌할 때 기존 선택의 재검토 필요성을 제안 | 실행의 전략 trace와 검토한 범위, 조건·Risk·선택 정책을 고정. 초기에는 shadow로 기록. 사전 탈락 종목의 재발굴은 별도 실험 |
| 상세 분석의 국면·종목·업종 충돌 | `StrategyAnalysisService` 결과에서 시장 국면과 상대강도·개별 전략의 불일치를 설명하고 허용된 계획 후보를 비교 | 동일 as-of/EOD 기준. 수동 참고가격 시나리오는 확정 EOD와 별도 식별 |
| Event Evidence와 Quant Signal 충돌 | 권한·관련성·시점·중복 검사를 통과한 사건과 정량 신호의 불일치 검토 | P6 품질 상태만으로 AI 권한을 얻지 않음. NAVER/현재 P6 OpenDART 정책의 AI 불허를 먼저 해결해야 하는 조건부 후보 |
| Holdings 판단 제안 후·계획 적용 전 | 적용 계획 유지, 보호 강화 검토, 목표 도달 후 재검토, 논리 변화에 대한 대안 비교 | analysis revision·position·plan version을 고정하고 적용 직전 stale 검사. 수량/비율·ADD 허용·손절 완화를 AI가 만들어내지 않음 |
| Recovery 수동 검토 중 | 논리 유지/약화/훼손/미확인의 근거와 반대 근거, HOLD/REDUCE/EXIT 검토 논리를 보조 | 손실률만으로 시작·물타기·회복확률 제안 금지. 사용자 판단·수동 종료를 보존 |
| Horizon 간 검토 | 향후 승인된 기간 정책의 판단이 다를 때 계획 의도와 충돌 이유 비교 | 현재 명시 Horizon 수치 정책은 미승인. Jev가 SHORT/MEDIUM/LONG 규칙을 발명하지 않음 |
| Watch 확인 이후의 재검토 문맥 | 향후 승인된 Watch의 알림에 연결된 근거를 요약하고 보유 판단 재검토를 보조 | tick/confirmation/rearm/stale 판정은 결정론적 엔진 소유. 고빈도 시세 경로의 필수 의존성으로 두지 않음 |

정형 규칙으로 표현하기 어려운 복합 상태에서 **기존 지원 선택지 비교·재검토·유보**를 보조하는 것이 우선 가설이다. 근거가 없으면 판단 유보/abstain을 허용한다. 미래 예상 수익이나 회복확률을 생성한 문장만으로 선택을 정당화하지 않는다.

Jev에 맡기지 않는 영역은 가격·거래량·기술지표 계산, 수익률·손익·수량 계산, Historical Validation, Execution Simulation, DB 무결성·hash 검증, 명확한 Risk Guardrail, source 권한 판정, Watch 상태 전이, 결정론적으로 처리 가능한 규칙이다. 검증은 StockScope가 Jev를 평가하는 책임이며 Jev가 자신의 성능 판정이나 합격 기준을 결정하지 않는다.

## 4. 기존 Scanner와 Jev 결합 아이디어

논의한 관계는 아래와 같이 보존한다. `+`와 `=`는 고려 요소의 조합을 뜻하며 수치 합산 공식이 아니다.

```text
Existing StockScope Signal
 + Jev Decision
 + Historical Performance
 + Confidence
 + Risk Guardrail
 = Final Decision 후보
```

검토 가능한 집계 방식은 ① 충돌 설명만 제공, ② 허용된 후보 사이 비교/재검토 제안, ③ 적합도와 의미를 맞춘 점수 조합, ④ 검증된 Regime별 조합이다. 초기에는 기존 판단을 그대로 반환하는 baseline과 shadow 비교를 우선한다.

가중치 실험 예시는 다음과 같다. **어떤 비율도 현재 확정하지 않는다.**

```text
Scanner 100 / Jev 0    ← 대조군
Scanner 90  / Jev 10
Scanner 80  / Jev 20
Scanner 70  / Jev 30
...                    ← 연구용 후보이며 운영 설정 아님
```

Jev의 행동 의견, Scanner의 적합도·tier, 과거 수익률은 같은 단위가 아니다. 점수 조합을 검토하려면 출력 의미·정규화·허용 행동·보류 처리·Risk 제약을 먼저 정의한다. Historical Performance는 우선 신뢰도와 평가 근거로 사용하며, 현재 순위에 직접 반영하는 변경은 별도 검증·승인 대상이다. 자료 보유량이 늘었다는 이유로 현재 판단이 달라지지 않는 기존 원칙을 보존한다.

| Regime별 아이디어 | 현재 코드와 연결할 때의 해석 |
| --- | --- |
| Bull: Scanner 비중 ↑ | 현재 `TREND_UP` 문맥에서 검증할 가설이며 상승장이라는 이유만으로 신뢰도 증가를 확정하지 않음 |
| Sideways: Jev 비중 일부 ↑ | `RANGE`에서 전략 충돌 보조의 증분 효과를 검증 |
| High Volatility: Risk Engine 비중 ↑ | `HIGH_VOLATILITY`에서 위험 제약을 우선. Risk Gate는 혼합 점수가 아니므로 Jev 의견으로 상쇄 불가 |
| Event Driven: Event Evidence + Jev 영향 조정 | 현재 `MarketRegime` enum에 EVENT_DRIVEN은 없음. 별도 이벤트 cohort/context 후보이며 승인된 자료만 사용 |
| PANIC / UNKNOWN | PANIC 차단은 보존. UNKNOWN에 새 AI 비율을 임의로 부여하지 않고 기존 판단·유보 경로 사용 |

가중치·국면 매핑은 Development 구간에서 비교하고 독립 Holdout·Prospective로 평가한다. 운영 변경이 필요하면 P5의 근거·제안·승인·명시적 활성화 원칙에 맞춘 별도 계약을 검토한다. 현 P5가 AI 집계 정책 활성화를 이미 지원한다고 가정하지 않는다.

## 5. 중복 신호 문제

**핵심 설계 위험: 같은 근거를 다른 이름의 점수로 이중 반영할 수 있다.**

```text
RSI / MACD / 이동평균 / 거래량 → Scanner 파생 판단
            └──────────────→ Jev 입력
Scanner Score도 Jev에 제공
            ↓
최종 Scanner Score + Jev Score
            ↓
독립 근거처럼 보이지만 같은 입력을 반복 가중할 위험
```

위 지표 목록은 중복 위험의 예시이며 모든 지표가 현재 Scanner 입력이라는 주장이 아니다. 기존 EventRisk가 Gate에 반영된 사건을 Jev가 다시 위험 점수로 부여하거나, 동일 사건 기사 여러 개를 독립 근거로 세는 경우도 같은 문제다. AI와 기존 엔진의 일치를 독립적인 두 번의 확인으로 간주하지 않는다.

향후 검토할 내용:

- Quant Engine은 계산·조건/Risk 판정, Jev는 충돌 해석과 허용 선택지 비교를 담당하는 입력 역할 분리.
- raw signal·derived signal·Scanner 결과의 계보를 보존. 입력 제거 실험으로 같은 정보가 중복 가중되는지 확인.
- Jev가 Scanner 결과를 직접 받는 실험과 받지 않는 실험을 구분. 결과를 받으면 기존 판단에 대한 anchoring과 동조 편향을 별도 평가.
- Feature provenance: source ID/hash, 기준·사용 가능 시각, 계산 version, 원천 feature와 파생 관계, 이미 반영된 Gate/점수·event canonical ID.
- P6 중복·정정·철회와 entity 관련성을 사용하되 품질/관련성 상태를 시장 방향 점수로 변환하지 않음.
- Quant-only / Jev-only 연구군 / 결합군 / 입력 제거군 비교로 Jev의 추가 정보와 추가 가치 검증. Jev-only도 모든 StockScope 안전 제약을 유지.

입력 중복 자체를 항상 금지할 필요는 없다. 문맥 설명에 같은 근거를 제공하더라도 최종 영향력을 독립 근거로 중복 계산하지 않는지를 검증한다.

## 6. Confidence 활용

Jev가 confidence/probability를 반환할 수 있다는 가정 아래 검토한다. 반환 여부·의미는 미확인이다. 자기 보고 confidence를 수익확률이나 검증된 신뢰도로 그대로 사용하지 않는다.

```text
Jev raw confidence
       × Jev historical reliability
       × current regime reliability
       ↓
effective Jev weight 후보
       ↓
승인된 최대 영향 / 자료 충분성 / Risk Guardrail 확인
```

이는 개념식이다. 세 항의 독립성·척도·중복 여부가 검증되지 않았으므로 곱셈을 운영 공식으로 확정하지 않는다. 행동·Horizon·Regime별 calibration과 실제 증분 성과를 확인해야 한다. probability가 명확한 사건·기간을 대상으로 정의되는 경우에만 Brier score 등 확률 calibration을 검토하고, 그렇지 않으면 확률처럼 표시하지 않는다.

```text
high confidence   → 신뢰도 검증을 통과한 승인 비중 범위
medium confidence → 영향력 감소 후보
low confidence    → 기존 엔진 사용
누락/미보정/자료 부족 → 유보 또는 기존 엔진 사용
```

high/medium/low 경계·최대 비중·최근 N·국면별 최소 표본은 **현재 정하지 않는다**. Historical Validation으로 후보를 비교하고 독립 평가로 결정한다. 해당 판단 시각보다 뒤에 성숙한 결과나 Holdout 결과를 그 판단의 신뢰도에 소급 반영하지 않는다. self-confidence가 높아도 Risk·권한·지원 정책 차단을 해제할 수 없다.

## 7. Shadow Mode

최초 단계에서는 반드시 Shadow Mode를 우선 검토한다. Jev 의견은 실제 후보 순위·action·적용 계획·Watch·Production 활성화에 영향을 주지 않는다.

```text
고정된 동일 판단 입력 / 당시 정책 / as-of 문맥
              ├→ 실제 StockScope 판단 → 기존 경로 그대로 반환·운영
              └→ Jev → 별도 Shadow Decision 근거 보존 후보
                         → 이후 동일 조건 비교
```

여기서 동일 입력은 **같은 시점의 비교 가능한 허용 입력 묶음**을 뜻한다. baseline이 사용한 quant 결과와 Jev에 추가로 제공한 event 문맥의 차이도 기록한다. 서로 다른 분석 경로를 같은 입력이라고 합치지 않는다.

향후 보존을 검토할 항목은 기존 결정 ID/hash·입력 manifest·분석 리비전·포지션/계획 version, selection/exit 정책 식별자, Horizon/Regime, Jev provider/model version·요청/출력 계약·prompt/집계 정책 version, 근거 provenance, raw/effective confidence, abstain, 요청/완료 시각·지연·비용·실패 사유다. 정확한 저장 형식과 owner는 후속 아키텍처에서 정하며 **지금 테이블·DDL·서비스를 만들지 않는다**.

평가·연구 근거는 기존 Simulation/Prospective 소유권을 우선 검토하되 기존 완료 run과 Frozen Tracking을 변경하지 않는다. 원문·응답의 보존과 외부 전송도 허용된 범위 안에서만 한다. shadow 작업·기록 실패가 기존 판단 성공을 막지 않게 설계하고 실패/누락 분모를 남긴다.

충돌 사례에만 shadow를 실행하면 그 결과의 범위도 충돌 사례로 제한한다. 전체 성과를 주장하려면 미실행·유보·NO_TRADE·실패를 포함한 실행 범위와 대조군을 고정해야 한다. 모델 응답의 비결정성에 대비해 원 응답과 version을 보존하며 나중에 다시 호출한 결과로 당시 의견을 덮어쓰지 않는다.

## 8. 평가 방법

### 8.1 공정한 비교 조건

기존 StockScope와 StockScope + Jev는 같은 시장 universe·선별 범위·기준 시각·데이터 revision·selection/exit 정책·Horizon·체결/비용 가정으로 비교한다. 같은 후보에 대한 판단 개선과 후보 선별 변경의 효과를 별도 실험으로 구분한다. 이미 잘 나온 후보만 사후 선택하지 않는다.

기존 Historical Replay·Execution·Backtest 계산을 재사용하고 Jev의 판단 차이와 집계 가정만 별도 버전의 연구 근거/run으로 보존하는 방향을 검토한다. 현재 엔진에 AI 입력/계획 비교 기능이 이미 있다는 뜻은 아니다. 기존 완료 VAL.1/VAL.2·20일/0% 결과는 불변으로 둔다. 현실 비용·세금·수수료·슬리피지·다른 기간은 P2의 버전 있는 비교 프로토콜과 추가 지원 범위를 검토해 새 run에서 평가한다.

누수 방지 조건:

- 신호 시점 D까지 알 수 있었던 quant·재무·event만 입력. 실행/관찰은 D+1 이후. 실시간/수동 참고가격과 확정 EOD는 다른 cohort.
- Event는 발표일만으로 시점 적합성을 판단하지 않음. source 권한, 실제 `available_at`, 수집·정정·철회 revision, entity 관련성·canonical resolution, 목적별 quality를 고정.
- 현재 P6 시간 계약의 DATE_ONLY/INFERRED/UNKNOWN은 시간 분리 평가에 부적합. USABLE 판정과 AI_TRANSFORM/PREDICTION_INPUT 허용은 별도 확인.
- Development/Calibration과 Holdout을 시간으로 분리하고 겹치는 보유기간을 purge. 결과를 본 뒤 바꾼 가중치·prompt·threshold는 새 프로토콜과 새 독립 평가 필요.
- 미래에 학습된 모델이 과거 사건의 결과를 기억할 위험을 기록. 과거 as-of 자료만 제공해도 모델 내부의 미래 지식까지 제거했다고 보장할 수 없으므로 Historical 결과만으로 확정하지 않고 Prospective Shadow 검증을 요구.
- 시장 universe·상장폐지·과거 구성 자료의 불완전성, 후보 pruning·사용자 선택·상관 표본·국면 편중을 한계로 표시.
- 전체/평가 가능/미실행/유보/실패/제외/미성숙·CENSORED 분모를 기록. 관찰 도달을 체결로 확정하지 않고 Holdings 사용자 선택을 전략 인과효과로 단정하지 않음.

### 8.2 평가 항목

아래는 **향후 평가 후보**다. 현재 모든 지표가 구현되었다는 뜻은 아니다. 계산 정의·분모·관찰기간·비용을 평가 전에 고정한다.

| 항목 | 확인할 의미와 주의점 |
| --- | --- |
| Average Return | 동일 기간·체결/비용 가정의 평균 수익. 무진입·현금 유지와 실행된 거래의 성과를 따로 표시 |
| MDD | 동일 자본·중복 포지션·시간순 equity 기준 최대 낙폭. 종목별 MAE를 포트폴리오 MDD로 대체하지 않음 |
| Win Rate | 평가 가능한 가상 체결 결과의 비율과 분모. NO_TRADE/유보를 자동 정답으로 세지 않음 |
| Profit Factor | 같은 비용 기준의 이익/손실 합계. 손실 거래가 없거나 표본이 적으면 불안정성 표시 |
| Risk-adjusted Return | 기간·노출·변동성과 손실 위험을 반영한 비교. 지표/연율화 가정은 사전 명시 |
| Large Loss Frequency | 사전 정의한 큰 손실 사건의 빈도·심각도. 손실 경계를 이번 문서에서 정하지 않음 |
| False Defensive Action | 유효한 안전 차단 밖에서 불필요한 방어 제안으로 놓친 성과. Risk Gate 우회를 정당화하는 지표로 쓰지 않음 |
| False Relaxation | 보호·검토를 완화한 의견이 손실 위험을 키운 경우. 금지된 손절 완화는 성과와 관계없이 정책 위반으로 분리 |
| Incorrect Entry Support | 진입 지지 후 사전 정의한 실패/손실 기준을 충족한 비율. 기대수익·손실 심각도도 비교 |
| Incorrect Hold | HOLD 유지 의견 후 정해진 기간에 논리 무효화·손실 기준이 나타난 경우. 사용자 실제 체결과 구분 |
| Recovery Performance | 논리·검토·계획 선택의 품질과 관측 가능한 결과. 사용자 선택 편향을 표시하고 회복확률·추가매수 효과로 단정하지 않음 |
| Horizon별 성능 | 승인된 기간 정책별 독립 cohort. LEGACY_UNSPECIFIED는 별도 유지 |
| Market Regime별 성능 | 당시 국면 정의/version에 따른 성과·표본·실패율. 사후 국면 재라벨로 좋은 결과만 선택하지 않음 |
| Event 발생/미발생별 성능 | 허용되고 당시 사용 가능한 event 문맥의 증분 효과. 중복 기사 수를 독립 표본 수로 세지 않음 |
| 판단 안정성 / 운영 비용 | 작은 입력 변화에 따른 잦은 판단 반전·계획 변경 제안 빈도, 지연·실패·유보율·모델 비용 대비 효과 |

단순 적중률을 최적화하지 않는다. 목표는 **손실 위험을 제한하면서 장기 기대수익과 판단 안정성을 개선하는 것**이다. 위험 제약 위반은 수익 개선으로 상쇄할 수 없다. 추가 판단이 낳은 실제 증분 효과·불확실성·비용 민감도를 대조군과 비교하며 숫자가 좋아 보여도 표본이 부족하면 채택을 유보한다.

최소 표본·유효성 기준·큰 손실 기준·신뢰구간 방법·승격/중단 기준은 미결정이다. P5의 Q7 미승인 상태와 별개로 Jev 평가에도 사전 프로토콜이 필요하며, AI가 그 숫자를 임의로 채우지 않는다.

## 9. Jev 성능 추적

Jev 자체도 StockScope의 검증 대상이다. 향후 최근 N건과 장기 누적을 같은 정의·성숙한 결과로 추적하는 구조를 검토한다. N과 평가 기간은 지금 정하지 않는다.

```text
최근 N건 / 누적 / Horizon·Regime·Event별
  Existing Engine accuracy
  Jev accuracy
  Both agreed accuracy
  Disagreement cases
    ├ Existing Engine correct
    ├ Jev correct
    ├ Both incorrect
    └ 미성숙 / 정답 정의 불가 / Jev 유보·실패
  + 증분 수익·낙폭·큰 손실·calibration·지연·비용
```

correct/accuracy는 가격 방향, 가상 실행 결과, 계획 선택 등 어떤 목표와 기간인지 먼저 정의한다. 서로 다른 행동의 성과는 같은 검증 엔진/가정의 반사실 비교로 평가 가능 여부를 판단하고 관측 불가능하면 UNKNOWN으로 남긴다. 둘이 일치한 비율은 정확도·독립 근거의 증명이 아니다.

model/version·prompt·집계 정책·selection/exit 정책이 다른 표본은 분리한다. 최근 표본 편중·drift·가중치 변경 후 성과를 추적해 제안의 근거로 사용하되 최신 수익률이 Production 가중치나 적용 계획을 자동 변경하지 않는다. **현재 성능 추적·저장·가중치 조정은 구현하지 않는다.**

## 10. Provider 추상화

StockScope를 Jev에 종속시키지 않는다. 향후 공통 의미 계약을 검토한다.

```text
DecisionProvider (개념 인터페이스)
  ├ RuleBasedProvider   ← 기존 결정론적 결과의 호환 adapter 후보
  ├ JevProvider
  └ FutureAIProvider
```

이 이름들은 새 클래스 생성 지시가 아니다. 기존 엔진을 모두 재작성하지 않고 공통 비교 문맥과 응답 adapter부터 검토한다. 핵심 로직은 특정 공급자의 SDK·모델명·응답 필드에 직접 종속되지 않는 방향을 권장한다.

향후 의미 계약 후보는 request identity·as-of·입력 provenance·허용 선택지·지원 Horizon, 응답의 선택/재검토/abstain·근거/반대 근거·불확실성·model version·실패 사유다. confidence가 없거나 의미가 다르면 누락/미보정 상태를 명시한다. 공급자 응답을 검증한 뒤 StockScope의 공통 의견으로 변환하고 가격·주문·계획 적용 명령으로 처리하지 않는다.

provider/model·계약·prompt·집계 policy version은 각각 식별하고 실험/캐시를 분리한다. 더 좋은 모델이 등장하면 동일 입력·동일 프로토콜로 교체 또는 병렬 shadow 검증할 수 있어야 한다. 정확한 API·저장 schema·인프라·SDK·모델 선정은 후속 작업에서 결정한다.

## 11. Fallback / Fail-safe

AI 장애가 기존 분석 기능을 중단시키면 안 된다. 기본 fallback은 **해당 실행에 고정된 StockScope 기존 결과**다. 기존 결과에 Risk 차단·유보·자료 부족이 있으면 그 상태 그대로 보존하며 정상 진입 결과로 바꾸지 않는다.

| 상태 | 향후 처리 방향 |
| --- | --- |
| API 장애 / 네트워크 불가 | AI 영향 0, 기존 결과 반환·실패 사유 기록 |
| Timeout | 고정된 예산 안에서 포기하고 기존 결과 사용. 늦은 응답이 이미 반환된 판단/적용 계획을 바꾸지 않음 |
| Rate Limit | 호출 제한·bounded retry 후보. 기존 엔진 성공 경로에 무한 대기를 만들지 않음 |
| Invalid Response | 허용 행동·근거 식별·수치/형식 검증 실패 시 폐기하고 기존 결과 사용 |
| Low Confidence / 미보정 / 자료 부족 | abstain 또는 AI 영향 0. 기존 Risk·유보 상태 유지 |
| Schema Mismatch | 호환되지 않는 응답을 추정 변환하지 않고 미사용 |
| Version Change | 새로운 model/schema/prompt를 별도 shadow cohort로 검증. 과거 신뢰도를 자동 승계하지 않음 |
| 비용 한도 초과 | AI 호출 중단, 기존 분석 계속. 한도 수치는 향후 결정 |
| 입력/계획/정책 변경, hash 불일치 | stale 결과 사용 금지. 현재 실행의 기존 판단 또는 새 명시적 평가 경로 사용 |

Jev 비활성 상태, 설정 미완료, 키 없음도 기존 StockScope 이용을 막지 않아야 한다. AI 평가 저장 실패와 운영 분석 성공은 분리한다. 정상/장애에서 baseline 결과 동등성과 Risk·NO_TRADE 보존을 향후 검증한다. 재시도 횟수·Timeout·비용·중단 임계값은 현재 확정하지 않는다.

## 12. 주문 실행 금지 원칙

**StockScope는 실제 증권사 매수/매도 주문을 실행하지 않는다. Jev가 추가되더라도 이 원칙은 변경되지 않는다.**

| StockScope가 담당하는 범위 | 담당하지 않는 범위 |
| --- | --- |
| 분석·위험 평가·대응 계획 생성·사용자 알림·의사결정 지원 | 실제 매수 주문·실제 매도 주문·증권 계좌 자동 주문 실행 |
| 대응 계획 자동 재평가·조정 제안 후보 | AI 출력에 의한 주문·정정·취소, 사용자 검토 없는 적용 계획 변경 |

논의의 “대응 계획 자동 조정”은 현재 구조에서는 **자동 재평가·새 제안 생성**으로 해석한다. 실제 적용 계획 변경은 사용자 명시적 적용과 version·이전 계획 연결·손절 완화 차단을 유지한다. 자동 적용을 추후 검토하려면 별도의 제품 정책·검증·명세가 필요하며 이번 개념 문서는 이를 승인하지 않는다.

수동 원장 기록, KIS 잔고 관찰, 가상 체결, STOP/EXIT/ADD_REVIEW 같은 행동/검토 라벨은 실제 주문과 구분한다. 현재 [`test_no_order_routes.py`](../backend/tests/test_no_order_routes.py), [`test_kis_read_only.py`](../backend/tests/test_kis_read_only.py)의 경계도 향후 보존해야 한다. 이번에는 해당 테스트를 실행하거나 수정하지 않았다.

## 13. MCP와 분리

Jev는 향후 StockScope 백엔드 내부에서 직접 사용하는 Decision Model 후보다. MCP는 필요할 경우 외부 LLM이 StockScope 기능을 호출하는 별도 인터페이스 문제다. 현재 Jev 도입 검토에 필요한 구성요소가 아니며 이 계획의 범위에 포함하지 않는다. MCP 서버·tool·의존성은 추가하지 않는다.

## 14. 도입 시점과 재검토 항목

현재 구현하지 않는다. StockScope 핵심 기능과 Final Decision Flow가 충분히 안정된 뒤 재검토한다. 핵심 기능 안정은 코드 존재만이 아니라 지원/보류 범위·입력 재현성·Risk/계획 계약·평가 자료·장애 복구의 확인을 뜻한다. 불필요한 미지원 기능의 출시를 선행 조건으로 만들어 범위를 확대하지 않는다.

```text
StockScope Core 완료·지원/보류 범위 확정
  → Final Decision Flow 안정화
  → Jev Integration Architecture 재검토
  → Shadow Mode
  → Historical A/B Validation + Execution 비교
  → Prospective 성과·운영 조건 검증
  → 채택 / 제한적 채택 / 보류 / 폐기 결정
  → 채택 시 별도 승인·활성화 계약 아래 제한적 적용
```

| 재검토 항목 | 다음 검토에서 확인할 내용 |
| --- | --- |
| Jev의 실제 제품 계약 | 공급자·공식 API·지원 출력/confidence 의미·version 고정/변경 통지·가용성·비용·지연·입력 전송/보존 조건 |
| 현재 코드와 상태 갱신 | 새 HEAD·최신 handoff·baseline·단계별 구현/검증/활성화 상태. 이번 문서의 후보 지점이 여전히 유효한지 |
| 최종 판단·입력 경계 | Scanner/상세 분석/Holdings 별 입력 차이, 선정 이전/이후 후보 범위, 적용 전 stale, EOD와 참고가격의 구분 |
| Event / News 사용 가능성 | NAVER·OpenDART·다른 source별 AI/보존/평가/예측 권한, corpus·시간/정정/관련성/중복·quality. 허용 자료 없으면 해당 실험 보류 |
| Horizon·Holdings·Recovery·Watch | 수치 정책 승인 상태, ADD 차단, 계획 명시적 적용·손절 완화 보호, 수동 Recovery, Watch 활성화/장중 coverage 검증 |
| 평가 프로토콜 | 최소 표본·기간·목표/정답·비용·큰 손실/승격/중단 기준, Development/Calibration/Holdout, purge·Prospective 성숙도·표본 편향 |
| 중복·confidence·가중치 | provenance·입력 제거 실험·anchoring·calibration·Regime별 추가 가치. 고정 비율과 동적 비율 모두 미확정 |
| Provider·집계·운영 책임 | 기존 엔진 adapter 범위, 공통 의미 계약, run pin·캐시 식별, P5와 충돌 없는 승인/활성화·rollback, 자동 변경 경계 |
| 저장·복구·관측 | 기존 도메인 owner 재사용, 원본/완료 결과 불변, 허용 보존·삭제·연결 hash·backup/restore·실패/누락 추적 |
| 채택 조건 | 수익·낙폭·큰 손실·안정성·비용의 실제 증분 개선, 정책 위반 없음, 장애 시 기존 기능 동등성. 기준 미달은 보류/폐기 |

이번 작업에서는 소스코드, Jev API, 패키지, `.env`, API Key, DB Migration/schema, Scanner/Strategy/Risk/Recovery 로직, UI, 테스트 동작, MCP를 변경하지 않는다. 기존 프로젝트 파일은 수정하지 않으며 문서 생성 이후 구현 작업을 시작하지 않는다.

## 15. 최종 결론

- Jev 도입은 확정 사항이 아닌 **향후 후보**다. 지금 구현하지 않는다.
- 현재 StockScope 아키텍처와 각 도메인의 데이터 소유권·판단 의미·계획 적용 계약을 보존한다.
- 실제 Historical / Execution 비교와 Prospective 관찰에서 성능 개선이 검증되어야만 채택한다.
- 특정 모델 종속성을 피하고 다른 Decision Model의 교체·병렬 검증이 가능하도록 검토한다.
- **Shadow Mode → Validation → 승인된 제한적 적용** 순서를 우선한다. 비율·임계값·정책 수치는 현재 확정하지 않는다.
- Jev가 실패하거나 사라져도 StockScope는 독립적으로 정상 동작해야 한다. Risk Gate·NO_TRADE·주문 실행 금지 원칙은 유지한다.

이번 산출물과 변경 파일은 `docs/StockScope_JEV_INTEGRATION_CONCEPT.md` 한 개다. 코드/DB/UI 변경은 0건이며 이 문서는 다음 구현 단계의 실행 지시가 아니다.
