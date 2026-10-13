# StockScope Q7 승인 기준 및 전략 버전 연결 설계 — S14 (2026-10-13)

> 상태: **승인 전 설계 기준 / 운영 활성화 금지**. 이 문서는 Q7 승인이 아니며, 임계값·표본·실제 성능을 만들어내지 않는다.

## 1. 확인된 현재 상태와 목표

- 최신 Scanner Capture `19e0ba21-5fd5-4202-a244-e65a3dad839a`: 15건 중 진입 후보 3건, 3건 모두 `LEGACY_LIMITED`, `LOCAL_PACKET_READY`. 완전 검증 0건, 실제 TypeSafe 호출 0건.
- 현재 이 PC에서 `LEGACY_CURRENT_10_FALLBACK` 사용. 레거시 원본에는 `strategy_version_id`, `strategy_definition_hash`가 없으며 유도한 엔진 식별자는 원본 필드가 아니다.
- Q7 승인 기준은 `production_blocked_approval_protocol()`에서 `activation_eligible=False`, `q7_precommitted=False`. 이 PC의 Evaluation/Proposal/Approval Artifact는 모두 0건이었다.
- 목표는 **미래 결과로 검증할 수 있는 전략 버전별 평가 기준을 결과 관찰 *전에* 고정**, 독립 근거를 얻은 뒤 승인/운영 선택 정책으로 연결하는 것. JEV와 Scanner의 실제 성능 향상을 주장하는 것이 아니다.

## 2. Q7에서 반드시 사전에 결정할 항목

아래는 필수 **결정 항목**이지 승인된 기준이 아니다. 각 수치는 실제 개발 코호트와 사용 가능한 자료를 분석한 뒤 사람이 명시적으로 승인해야 한다.

| 항목 | 사전 고정할 내용 | 현재 |
|---|---|---|
| 장기·최근 평가 기간 | 거래일/달력 기간, 종목 universe, 데이터 수집 시점, 기준일까지 평가 가능한 정보 | **미정** |
| 최소 독립 표본 | 전략/기간/국면별 최소 표본 및 중복·상관 표본 처리, 성숙·중도절단 정의 | **미정** |
| 시장 국면 | 국면 정의, 당시 알 수 있었던 데이터, 시장·기간별 층화 원칙 | **미정** |
| 비교 기준 | 현재 운영 전략 및 NO_TRADE, 같은 날짜·종목군·위험·비용에서의 대응 비교 | **미정** |
| 성과·리스크 평가 | 수익·손실·하방 위험·회복·신뢰구간, 다중 검정 및 선택 편향 처리 | **미정** |
| 체결·비용 가정 | 실거래가 아닌 평가가격, 수수료, 세금, 슬리피지, 미체결·유동성 처리 | **미정** |
| 시간 분리 | DEVELOPMENT에서 기준 결정, 별도 HOLDOUT/전진 시점 잠금, 공개·수집 시각 확인 | **미정** |
| 승격·유보·강등·롤백 | 정량 임계값, 안전 조건, 실패 시 변경 취소, 명시적 승인 주체 | **미정** |

**합격 원칙:** 하나라도 미정인 상태에서는 Q7 승인/전략 승격/자동 Rotation을 허용하지 않는다. `INSUFFICIENT_EVIDENCE`, `SAMPLE_SIZE_POLICY_UNDEFINED` 같은 부정적 근거 상태를 합격으로 바꾸지 않는다.

## 3. 증거의 연결과 전략 원본 식별

- 원본 증거는 `strategy_registry_version`의 **실제** `strategy_version_id + definition_hash`를 참조해야 한다. 단순히 전략 이름이나 현재 코드가 계산한 버전만 과거 후보에 적용해서는 안 된다.
- `Scanner` 실행 시 확정한 `SelectionPolicyPin`과 실행 메타데이터를 Capture 요청·원본 후보 스냅샷에 연결한다. 캐시 결과는 fresh engine PASS 증거를 계승할 수 없다.
- Prospective/Feedback의 Evaluation Artifact는 **원본 전략 버전, 신호일, 평가 run, 평가 프로토콜, 결과 잠금/성숙 조건**을 확인해야 한다.
- 레거시에서 엔진 재현 근거로 파생한 `semantic_strategy_identity`는 `LEGACY_LIMITED` 로컬 관찰만 가능하다. `strategy_version_id` 원본을 사후 생성하거나 기존 Capture를 덮어쓰지 않는다.
- **부트스트랩 문제:** 활성 정책이 없으면 새 Scanner는 레거시 버전을 기록하고, 승인에는 완전한 원본 전략 버전 근거가 필요하다. 이 순환 의존성은 *읽기 전용 연구 검증 코호트와 사전 고정된 미래 평가 프로토콜*을 분리해 해결하도록 별도 명세/검증해야 한다. 레거시 결과를 정식 승인으로 둔갑시키는 우회는 금지한다.

## 4. 정식 승인 연결 계약 (아직 미구현)

1. **Q7 기준 사전고정**: 숫자·국면·비용·시간 경계·성공/실패/롤백 기준을 결과 관찰 전에 고정한 불변 artifact, 해시, 작성/승인 주체와 시각.
2. **검증 가능한 데이터**: 대상 전략의 원본 ID/해시를 참조한 시점증명된 prospective 및 외부 근거; 사전 기준 충족 여부 자동 계산, 개발/검증 분리.
3. **독립 재검증**: source report·evaluation protocol·전략 definition·기준 해시의 일치 및 non-stale, holdout 누출/소급승인 금지.
4. **StrategyChange Proposal + Approval**: 각 변경 전략에 대한 증거 coverage를 만족하고 검증된 Q7 프로토콜을 참조하는 정식 승인만 유효.
5. **명시적 Selection Policy 활성화**: 승인/롤백 근거·불변 스냅샷, 현재 production baseline 일치, CAS 및 idempotency. Risk Gate·NO_TRADE·점수·현재 우선순위 보존.
6. **별도 JEV Provider Gate**: 위의 승인과 별개로 외부 자료 전송 권한, 원천 행/공개·취득 시각, 과금·모델 승인 확인. Q7을 통과해도 TypeSafe 자동 허용은 아니다.

S14에서는 단계 1~5의 **무단 우회 차단**을 구현한다. 정식 Q7 프로토콜 발급·평가·운영 활성화는 증거와 수치 기준이 실제로 확정되기 전까지 **구현 완료로 간주하지 않는다**.

## 5. S14 구현 경계와 테스트

- 제안/승인 서비스가 전달받은 임의 객체의 `activation_eligible=True` 또는 `q7_precommitted=True`를 정식 근거로 신뢰하지 않는다.
- 운영 Selection Policy 게이트도 승인 기록의 해시가 맞는다는 이유만으로 출처 미확인 Q7을 통과시키지 않는다.
- 명시적인 `TEST_ONLY_SYNTHETIC` 프로토콜을 사용하는 자동 테스트는 해당 테스트 환경에서만 허용하고, 운영에서는 차단한다.
- 전략 원본 버전·순위·엔진 PASS 및 `LEGACY_LIMITED`의 차단 방식은 유지한다.
- 이번 단계는 기존 SQLite, Capture, 전략 선택 정책, Scanner 결과를 수정하지 않고 운영 정책을 활성화하지 않는다.

## 6. 다음 단계 인수 조건

**S15 (Q7 기준 고정)**: 개발 코호트의 실제 분포·성숙도·편향을 먼저 조사, 운영자가 정한 숫자를 불변 사전고정 artifact에 담는 저장·검증 경로를 구현한다. 빈 기준이나 임의의 수치로 승인시키지 않는다.

**S16 (독립 평가)**: Versioned Research/Prospective의 결과 시점·전략 원본 identity·holdout 분리를 확인하고 진짜 승인 적격성을 판정한다. 필요한 표본이 부족하면 계속 `HOLD`.

**S17 (활성화)**: 검증된 Q7 artifact를 StrategyChange Proposal/Approval/Selection Registry에서 재검증하고, 승인된 최신 후보부터 운영 정책을 명시적으로 활성화한다. 이후 새로운 Scanner Capture가 `LOCAL_VALIDATED`인지를 실측한다.

## 7. 설계 원문

- `docs/StockScope_MASTER_ARCHITECTURE_vNext.md` §8, §13 Q7: 평가·승인 절차는 설계에서 정해졌으나 장기/최근·국면·최소 표본은 **미정**, cohort 분석 후 사전 고정 필요.
- `docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md` P2-S2 / P5-S1: Q7 평가 기준 및 최소 표본을 수치 기반 승격 활성화 **전에** 고정, 숫자 임의 설정 금지.


---

## 8. S15 구현 결과 (2026-10-14)

**구현 범위**: S15는 연구용 평가 계획을 미래 Holdout 관측 전에 기록하는 **로컬 write-once 파일**을 제공한다. 검증 가능한 Q7 정식 승인 artifact는 아직 아니다.

- 읽기 전용 코호트 현황: `python tools/data/q7_precommit.py inventory`. 현재 Prospective 동결 Capture 원시 표본, 전략별 signal-date/market/ticker/strategy 중복 키, 평가 리포트 건수를 읽는다. 이 숫자는 **독립 성숙 표본/성과가 아님**.
- 실제 엔진 전략 identity를 포함한 빈 기준 초안: `python tools/data/q7_precommit.py template --strategy pullback`. 기간·최소 표본·비용·승격·롤백 등 미결정 수치는 `null`.
- 내용 검토: `python tools/data/q7_precommit.py check --file <spec.json>`. 비용·표본·국면·시장 기간, 현재 strategy version/hash, 결과 미관측 Holdout 시작일 등을 검증한다.
- 명시적 연구 확정: `python tools/data/q7_precommit.py freeze --file <spec.json> --acknowledge-research-only`. 기본 저장 `data/q7_precommit/<study_id>.json`; Git에는 포함되지 않으며 **다른 PC의 DB·장부와 자동 동기화되지 않는다**.
- 내용·SHA-256 확인: `python tools/data/q7_precommit.py verify --study-id <study_id>`. 동일 study_id로 수정된 계획은 저장 불가; 이후 전략 코드 변경과 무관하게 과거 파일의 해시를 검증할 수 있다.
- **신뢰 한계**: 파일의 시간은 운영 PC 시스템 시각이므로 공인 타임스탬프가 아니다. OS 파일 권한·백업·외부 증명을 침해할 수 있는 운영자가 파일과 해시를 통째로 재작성하는 것까지 방어하지는 못한다. S16에서 독립 시점·원천 증명을 연결하기 전에는 역사적 사전고정으로 인정하지 않는다.
- **승인 경계**: `q7_approval_eligible=False`, `production_activation_allowed=False` 상수로 유지한다. S14의 production 승인/활성화 차단은 변경하지 않는다. 기존 완료 Capture에 strategy_version_id를 소급 첨가하지 않는다.

### 인수 기준

새로운 Research Study에서 미래 Holdout을 향한 계획을 처음 1회 생성·해시 검증하는 것까지 S15 범위다. 완료된 실제 평가 결과 및 사람이 수치 기준을 결정하지 않았다면 연구 계획을 **확정하지 않는다**. S16은 시장 데이터의 시점·출처 권한, 성숙 평가 표본, 독립/중복, 국면별 성능과 holdout 누출을 검증하며 S17에서만 운영 승인/활성화 authority를 구축한다.
