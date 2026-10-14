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


## 9. S16 — 실제 추천 이후 수익률 관측 현황 (2026-10-14)

학교 PC에서 S15 `inventory` 실측: COMPLETE 3회, 저장 45건, 진입 24건, 평가 보고서 0건. 원시 24건은 독립/성숙 표본이 **아니다**. 전략별 원시 수: ma20_rebound 12, pullback 4, trend_recovery 4, support_bounce 3, range_trading 1.

- 실행 명령: `python tools/data/q7_precommit.py observe` (기본적으로 `STOCKSCOPE_SIM_DB`, `STOCKSCOPE_MARKET_STORE_DB` 또는 각 Runtime DB 경로 사용). 둘 다 **읽기 전용**, 외부 시세 요청·AI 호출 없음.
- 현재 서울 날짜까지만 이용. Market Store에 미래 날짜 데이터가 섞인 샘플은 **모든 구간의 수익률을 제외**하고 `FUTURE_DATED_MARKET_EVIDENCE`로 기록.
- 기존 ProspectiveEvaluator로 신호일 종가 기준 5·10·20 거래일 뒤 종가 변화율 관측. 실제 매수가·실제 주문 수익률·JEV 증분 효과가 아니다.
- `LOCAL_VALIDATED`, `LEGACY_LIMITED`만 **관측 통계** 대상으로 사용하고 `INVALID`는 제외. 레거시는 원본 전략 ID가 없으므로 정식 Q7 승인 샘플이 아니다.
- 각 구간에서 `observed`, `awaiting_future_trading_days`, `price_missing`, `market_evidence_unavailable`, `post_as_of_data_rejected`을 분리한다. 표본 부족과 가격 누락을 0% 수익률로 계산하지 않는다.
- 완료된 Capture가 20개 초과 또는 Capture당 499개 초과이면 **전체 코호트 분모를 주장하지 않고 중단**한다. 동일 날짜·시장·종목·전략 키의 단순 중복은 표시하되 독립 표본 수를 계산했다고 주장하지 않는다.
- 과거 Scanner 완료 시각이 신호일 이후면 `retrospective_or_later_capture_count`에 별도로 표시하며, 시각 증거가 불명확하면 `timing_not_proven_count`로 표시. 둘 다 현재 시점의 사전고정 성과라는 결론을 허용하지 않는다.
- `q7_approval_eligible=False`, `production_activation_allowed=False`, `model_uplift_verified=False`. 기존 운영 정책·Risk·Capture·전략/시장 SQLite는 변경하지 않는다.

**S16에서 아직 필요한 실제 근거:** 거래일별 독립성/시장 국면 분류, 분리된 미래 Holdout 평가 및 독립적인 시점 증명, 실제 JEV 미사용 대조군 및 비용·위험 반영. 관측 건수가 늘었다는 사실만으로 진짜 모델 개선이나 전략 승격으로 바꾸지 않는다.


## 10. S17 — 다음 영업일 추천 자동 기록·성과 추적 (2026-10-14)

**실행 대상:** Windows 한국시간 PC의 로컬 StockScope `backend`. 사용자가 명시적으로 설치한 Windows Task Scheduler만 자동 실행한다. `git pull` 자체는 작업을 등록하지 않는다.

**자동 실행 로직:** 주중 오전 7시(실제 허용 시간 05:00~08:45 KST)에 루프백 백엔드가 없으면 임시로 실행하여 `POST /api/backtest/scanner/freshness`를 호출한다. 확정된 기준일은 **오늘 이전**이며 4일 이내여야 한다. 휴장일·장기 지연·오래된 시세는 실행 건수를 채우려고 소급 생성하지 않고 보류한다. 사전 Capture 조회로 동일 시장·기준일의 이미 완료/진행 중인 작업이 있으면 Scanner를 재실행하지 않는다. 새 데이터라면 `POST /api/backtest/scanner/jobs`에 `force_refresh=true`, `allow_large_sync=false`, 실제 기준일을 제공하고, 완료될 때까지 job status를 확인한다. 정식 COMPLETE Capture ID가 생긴 경우에만 관측 단계로 이동한다.

**추적:** 매일 갱신된 로컬 Market Store를 가지고 S16의 5·10·20 거래일 종가 변화 기술통계를 읽기 전용 재계산한다. 같은 EOD일의 Scanner 기록이 이미 있더라도 관측 결과를 확인한다. **진입가·주문 수익률·JEV 개선 효과·정식 사전승인 자료는 아니다.** 분석 대상이 과거 신호일인 것은 정상 EOD 처리 지연의 결과이며, 작업이 시작된 날짜를 과거로 옮기지 않는다. 완료 시각이 오전 9시를 넘었으면 `completed_before_open=false`로 표시하며 장전 기록임을 주장하지 않는다.

**운영 로그:** `data/prospective_daily/YYYY-MM-DD_kospi.json` 등 현황 파일. 중복 실행 방지에 `.lock` 파일을 사용하며 프로세스 강제 종료로 남은 lock은 사용자가 원본 Capture 상태를 확인한 후 수동으로 정리해야 한다. 로그/로컬 시계는 외부 공인 타임스탬프가 아니다. PC가 꺼져 있거나 사용자가 로그아웃한 시간에는 실행되지 않으며 지난 거래일을 자동 소급하지 않는다. 로컬 SQLite와 로그는 다른 PC로 Git 동기화되지 않는다.

**수동 검증 (전송·주문 없음):**
```powershell
python .\tools\data\prospective_daily.py --dry-run
python .\tools\data\q7_precommit.py inventory
python .\tools\data\q7_precommit.py observe
```

**명시적 자동 등록 (사용자가 실행해야 함):**
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\data\install_prospective_daily.ps1
Get-ScheduledTask -TaskName StockScope-Prospective-Daily
# 중단하려면:
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\data\install_prospective_daily.ps1 -Remove
```
이 등록은 **한국시간 PC, 로그인 상태에서만** 작동하도록 안전 제한한다. 별도 상시 서버는 필수가 아니며 시작한 백엔드는 작업 후 종료한다. `KOSPI`가 기본이며 `-Scope KOSDAQ` 또는 `-Scope ALL`을 선택할 수 있다.

**범위 한도:** S16 현황은 COMPLETE Capture 최대 260회, 전체 표본 최대 6000개, 단일 Capture 최대 499개를 읽는다. 이를 초과하면 전체 통계라고 주장하지 않고 `COHORT_TOO_LARGE_FOR_COMPLETE_AUDIT`로 차단한다. 이후의 규모 확장·증분 저장은 별도 구조 검증이 필요하다.

**안전:** 최초 실행시 실제 KRX 시세 조회 및 로컬 Market DB/Prospective DB **저장은 발생**한다. 인터넷 유료 모델·주문 전송은 금지. Q7 운영 정책 승인·원본 전략 ID 복원·운영 전략 승격은 이 기능만으로 일어나지 않는다.

## 11. S18 — 실제 INVALID 원인 확인을 위한 읽기 전용 검사 (2026-10-14)

S16 결과에서 COMPLETE Capture 3회, 전체 후보 45개, 진입 후보 24개 중 S7 `INVALID` 21개가 기록되었다. 이 숫자만으로 `INVALID`의 실제 원인을 특정하거나, 가격 관측 불가·원본 손상·JEV 부적격을 같은 의미로 판단할 수 없다. S18의 우선 과제는 **기존 스냅샷을 수정하지 않고** 실제 원인 코드·원인 조합·검사 영역별 실패를 집계하는 것이다.

실행 예시 (해당 원본 DB를 보유한 PC에서):

```powershell
cd C:\Projects\StockScope
.\.venv\Scripts\python.exe -B .\tools\data\q7_precommit.py diagnose
# DB가 다른 경로라면:
.\.venv\Scripts\python.exe -B .\tools\data\q7_precommit.py diagnose --simulation-db "D:\...\simulation.db"
```

새 모드는 `mode=ro` SQLite 트랜잭션에서 `COMPLETE` 원본을 전부 읽고, 진입 후보 및 참고 후보의 기존 JSON 해시를 검증한 뒤 **기존 S7 검증 함수를 그대로** 호출한다. 진입 후보가 아닌 참고 후보는 해시 검사를 포함하되 JEV 진입 검증과 분리하여 집계한다. 각 `INVALID`의 `codes` 및 복합 발생, `rank/strategy/policy/engine/dates/risk/strict_s3` 실패, 전략·Scanner 버전 분포를 기록한다. JSON 해시가 틀린 후보는 JEV 검증 전에 `SNAPSHOT_UNREADABLE_OR_MISMATCH`로 보류한다.

`completion_timing_counts`는 **신호 날짜 기준 달력상 완료일**과 KST 오전 9시를 기술적으로 구분한다. `NEXT_CALENDAR_DAY_BEFORE_09_KST_UNVERIFIED`도 시세 공급자 공개시각·사용자 제공시각·독립 시각 증명이 확보됐다는 의미는 아니다. 이 검사 결과를 이용해 S16의 기존 retrospective 집계를 임의로 덮어쓰지 않는다.

기본 검사 상한은 `--max-samples 100000`, 자세한 문제 후보는 `--detail-limit 40`개까지 표시한다. 상세를 줄여도 전체 건수·원인별 합계는 유지한다. 상한을 넘거나 스키마가 맞지 않으면 `counts_complete=false`로 차단한다. 결과에는 **종목명, 원본 Snapshot JSON, 계정 정보, 유료 모델 응답이나 시세 데이터가 포함되지 않는다.** Capture ID와 종목 전략 및 날짜 등 기술 진단 필드만 내보낸다.

이 검사로 확인되는 것은 S7 엄격한 검증이 기록을 어떻게 판정했는지까지이며, 가격 관측 가능성, 독립 실시간 추천 증명, JEV 성과 증가 또는 운영 승인을 보장하지 않는다. 오류 코드 진단 결과를 확보한 **이후** 거래일 누락 판정, 구간별 as-of, 증분 관측 결과 보존의 설계를 최종 확정한다.

사용자 동의 없이 Windows 예약 작업을 등록·수정·제거하지 않는다. 기존 S17 작업이 이미 등록됐는지 여부는 각 PC의 Windows 작업 스케줄러에서 별도로 확인해야 하며, 본 코드는 관여하지 않는다.

## 12. S19 — S16 결과의 추천 시각 분류 바로잡기 (2026-10-14)

S18 실제 로컬 진단: COMPLETE 5회, DUPLICATE 9회, 후보 75건(진입 31·참고 44). 진입 31건 중 INVALID 24건(Scanner 0.21.3.7의 15건은 SEMANTIC_SOURCE_V2_MISSING, 0.21.3.9의 9건은 ENGINE_EVIDENCE_INCOMPLETE), LEGACY_LIMITED 7건이며 모든 75개 Snapshot 해시는 일치했다. INVALID 24건에는 모두 RANK_MISSING, POLICY_PROVENANCE_UNVERIFIED, STRATEGY_IDENTITY_MISSING이 동반했다. 이 사실은 원본 내용 훼손이 확인되지 않았음을 뜻하지만 실제 시점 증명·가격 성과의 정당성을 뜻하지 않는다.

과거 S16 필드 `retrospective_or_later_capture_count`는 **캡처 완료일이 신호일보다 뒤인 수**였고, 이 숫자만으로 사후 추천을 입증하지 않는다. 호환성을 위해 기존 필드는 유지하되 `retrospective_or_later_capture_count_deprecated=true`를 표기하고 `later_calendar_day_capture_count`, `completion_timing_counts`를 추가한다. 분류는 S18과 같은 한국시간 완료 시각 규칙으로 계산한다. 이후 생성 기록이라고 해서 장전 사전 확정이나 미래 시세 사용 여부가 증명되는 것은 아니다. `independently_proven_retroactive_count=null`을 명시한다.

이번 S19 범위는 시각 보고 **의미 개선만** 적용하며 거래일 누락·정정 가격 revision·구간별 as-of·S16 후보 무결성 판단·260/6000 상한·관측 계산은 그대로 유지한다. 해당 영역은 별도 테스트와 입력 계약 설계가 필요하다. 자동 수집 작업이나 Windows 예약 작업도 변경하지 않는다.

## 13. S20 — 사용자 수동 실행형 성과 관측 시장 데이터 보충 (2026-10-14)

실제 로컬 출력에서 KOSPI 942종목, KOSDAQ 1,823종목의 마지막 저장일이 2026-10-08로 확인됐다. 해당 시점의 S16 유효·제한적 후보 7개는 신호일 이후 저장 세션 0개였으므로 5/10/20일 관측이 모두 대기였다. 이것은 실제 휴장 여부가 아닌 **로컬 Market Store 수집 공백**의 증거다.

수동 모드만 존재한다. **Windows 예약 작업 추가, 서버 상주, Scanner 실행, 신규 Capture 생성, JEV 외부 호출, 주문 실행은 없다.** 실시간 장중 가격이나 당일 확정되지 않은 EOD는 처리하지 않는다.

### 기본 사용법 (프로젝트 루트, 기존 .venv)

```powershell
.\.venv\Scripts\python.exe -B .\tools\data\prospective_outcome_refresh.py plan
# 결과 확인 후 사용자 명시 승인 시에만 실제 수집:
.\.venv\Scripts\python.exe -B .\tools\data\prospective_outcome_refresh.py apply --acknowledge-market-writes
```

`plan`은 `mode=ro`로 COMPLETE Prospective Capture를 확인하고 S7에서 `LOCAL_VALIDATED` 또는 `LEGACY_LIMITED` 후보의 이후 **저장되지 않은 평일**을 목록화한다. 원본 Snapshot, 전략 식별자, DB를 변경하지 않는다. 260 Capture / 6000 샘플 / 단일 499 샘플의 현재 감사 범위를 초과하면 전체를 거부한다. 분석 대상 날짜가 90달력일보다 길어도 조용히 생략하지 않고 차단한다.

`apply`는 별도 `--acknowledge-market-writes`가 필요하고 최대 40개의 시장·날짜 쌍만 수집한다. 초과 시 일부만 자동 처리하지 않고 차단한다. KRX의 전체 시장 일봉과 해당 시장 대표 지수가 유효한 경우에만, 새 날짜의 종목·지수·완료 표시를 **단일 SQLite 트랜잭션**으로 추가한다. 기존에 어떤 데이터라도 있는 날짜는 덮어쓰지 않으며, 부분 저장일이 발견되면 수집 전에 전체 동작을 중단한다. 심하게 적은 종목 응답, 잘못된 날짜·코드, 대표 지수 누락은 차단한다.

휴장일·공급 장애 판정은 아직 독립 공식 달력과 연결되지 않았다. 평일 KRX 종목·지수가 모두 빈 결과면 `EMPTY_KRX_UNVERIFIED_CLOSURE`로만 표시하고 DB 거래일로 저장하지 않는다. 따라서 10월 9일처럼 빈 날은 계획상 MISSING으로 남아 재검사 대상이 될 수 있다. **실패를 휴장으로 간주하지 않으며, 남은 날짜가 있으면 성과 완성/정확성 보증으로 표시하지 않는다.** 이는 휴장일 계약을 별도로 닫기 전의 의도적인 보수성이다.

시세 보충 후 S16 `observe()`를 읽기 전용으로 호출하여 `outcome_windows`와 구간별 관측 상태를 보고한다. 이 출력은 S16 관측 통계이고, 평가 결과 DB 영속 증분화·구간별 as-of 수정·공식 거래 달력·가격 revision 보존·Q7 적격성 증명은 **아직 구현하지 않았다.** 날짜별 시장 전체 스냅샷 저장은 추후 정정 이력과 충돌할 수 있으므로 기존 날짜는 건드리지 않는다.

테스트는 실제 Runtime/외부 KRX를 사용하지 않고 합성 DB와 가짜 provider로 수동 동의, 부분 날짜 차단, 빈 KRX 응답, 원자적 추가, 중복 실행, 공급 실패, 날짜 상한·미래일 차단을 검증한다.
