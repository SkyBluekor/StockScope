# StockScope 인수인계 — 2026-10-02 / NEXT-6E R3 BLOCKED


## 0. 최신 R3 복구 업데이트 — exact DEV 확보 후 진단 실행

> 이 절은 아래의 `EVIDENCE_SOURCE_UNAVAILABLE` 중심 설명과 충돌하는 경우 우선한다. 아래 기존 내용은 최초 blocked 시점의 historical record로 보존한다.

exact frozen Development artifact가 사용자 제공으로 확보되었고 canonical dataset identity가 일치했다.

```text
DEV source
AVAILABLE EXPLICITLY

dataset_id
MACROCAL-DEV-7c3f6660b3aae03f

dataset_hash
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1
```

따라서 기존 primary blocker였던:

```text
EVIDENCE_SOURCE_ACCESS_UNRESOLVED
```

는 해결되었다.

R3 전용 DEV-only diagnostic이 구현/실행되었고 focused tests는 7 PASS다.

현재 결과:

```text
A0 lineage
MATHEMATICALLY_VERIFIED

A1 native completeness
MATHEMATICALLY_VERIFIED

A2 W→X identity
MATHEMATICALLY_VERIFIED

A3 joint alignment
MATHEMATICALLY_VERIFIED

A4 continuity / atom compatibility
ASSUMPTION_NOT_ACCEPTED

A5 stationarity compatibility
UNRESOLVED

A6 strong-mixing model-use
UNRESOLVED

A7 median regularity
ASSUMPTION_NOT_ACCEPTED

A8 positive MAD / zero scale
MATHEMATICALLY_VERIFIED

A9 MAD local regularity
ASSUMPTION_NOT_ACCEPTED

A10 frozen multiplier preprocessor
MATHEMATICALLY_VERIFIED
```

핵심 실질 blocker는 frozen Development feature가 강한 basis-point quantization / ties를 보인다는 점이다. 현재 R1 theorem route는 continuous joint law와 median/MAD local positive-density regularity를 요구하며 jitter는 금지되어 있다. 따라서 해당 가정들을 결과에 맞춰 억지로 승인하지 않는다.

A10 frozen profile은 Development process에서 deterministic하게 계산되었다.

```text
coordinate m
[1, 5, 10]

lag cutoff L
10

bandwidth b
22

effective ell
43

manual fallback
NO
```

현재 formal state:

```text
Method state
METHOD_PROFILE_FROZEN

Assumption Acceptance
NOT_GRANTED

G-A
BLOCKED

G-B
BLOCKED

Reference Adequacy
UNRESOLVED

V3 changed
NO

V4 created
NO

Evaluator implemented
NO

Production impact
NONE
```

또한 이 대화는 diagnostic 실행 전에 과거 context retrieval에서 이미 금지된 인접 metadata가 노출된 incident가 있었으므로 `clean_isolation_certified=NO`로 fail-close 기록했다. 이번 진단 과정에서 새 prohibited-source retrieval은 하지 않았으며 실제 계산 입력은 explicit DEV artifact 하나뿐이다. 금지된 metadata 값은 이 문서에 재기록하지 않는다.

중요:

- 이제 문제는 **DEV 파일 부재가 아니다.**
- 동일 R3를 반복 실행하는 것만으로 G-A가 PASS하지 않는다.
- formal clean-isolation replay가 나중에 필요하더라도, 그것은 process blocker 하나만 제거한다.
- 현재 substantive blocker는 quantization/continuity/median/MAD regularity와 stationarity/mixing acceptance다.
- 따라서 다음 Track-A 작업은 이 blocker들을 실제로 해소할 별도 명세가 필요하다.
- G-B도 여전히 BLOCKED이므로 S6C는 시작하지 않는다.

---

> 목적: ChatGPT 대화 최대 길이 도달로 새 채팅으로 넘어갈 때 프로젝트 흐름, 안전 규칙, 현재 GitHub 상태, 다음 작업 순서가 유실되지 않도록 하는 복구용 handoff 문서.
>
> 이 문서는 **현재 프로젝트 상태를 설명하는 문서**다. 새로운 구현 명세나 TASK SPEC이 아니다.

---

## 1. 가장 먼저 읽을 것

새 채팅에서 작업을 시작하기 전에 다음 사실을 기준으로 삼는다.

```text
Repository
SkyBluekor/StockScope

Current main
725b4d0a79344aca4f9fa7e585098059da24bd45

Current stage
NEXT-6E-S6A-R3

R3 status
BLOCKED_EVIDENCE_SOURCE_UNAVAILABLE

Method state
METHOD_PROFILE_FROZEN

G-A
BLOCKED

G-B
BLOCKED

Reference Adequacy
UNRESOLVED

V3 changed
NO

V4 created
NO

Evaluator implemented
NO

Production impact
NONE
```

현재 main의 최신 관련 commit:

```text
725b4d0a79344aca4f9fa7e585098059da24bd45
docs: record blocked NEXT-6E-S6A-R3 evidence gate
```

직전 핵심 commit:

```text
db87d92f3bdceea6e383c715c7fb327335449ece
docs: freeze NEXT-6E-S6A-R2A candidate domain
```

---

# 2. StockScope 프로젝트 목적

StockScope는 한국 주식 중심의 **분석 / 스캐너 / 보유종목 의사결정 지원 도구**다.

핵심 방향:

- 자동 매매 시스템이 아니다.
- 사용자가 빠르게 판단할 수 있도록 결과 중심으로 보여준다.
- 내부 검증 / replay / tracking / 전략 평가 / 재검토는 가능한 한 내부에서 수행하고 UI에는 필요한 결과와 근거만 보여준다.
- 시스템이 판단을 보조하지만 최종 책임은 사용자에게 있다.
- 신뢰성, 재현성, 데이터 lineage, 전략 성능 검증을 지속적으로 강화한다.
- 결과 화면을 연구 보고서처럼 길게 나열하지 않는다.
- UI 버튼을 과도하게 늘리지 않는다.
- 장기 / 중기 / 단기 horizon을 고려한다.
- 보유종목의 큰 손실, 회복, 손절, 추매 판단을 지원할 수 있어야 한다.
- 추천 후보가 실제로 매수되었다고 가정했을 때 이후 성과를 추적해 전략 성능을 평가한다.
- 전략의 승격 / 강등은 governance를 거치며 자동 무제한 변경을 허용하지 않는다.

금지되는 방향:

```text
자동 매수/매도
자동 SL/TP
자동 물타기
자동 전략 승격/강등
Production Policy 자동 교체
Holdings Plan 자동 교체
Risk Gate 우회
```

`NO_TRADE`는 전략 하나가 아니라 안전 동작이다.

---

# 3. 기술 스택

현재 핵심 스택:

```text
Backend
Python
FastAPI

Frontend
TypeScript
React
Vite

Storage
SQLite

Platform
Windows
PowerShell

Repository
GitHub / SkyBluekor/StockScope
```

Local runtime SQLite는 로컬에서만 다룬다.

Cloud sync 폴더에서 live SQLite를 운용하지 않는다.

Google Drive는 API/OAuth 기반 애플리케이션 transport가 아니라 **desktop mirrored/local transport** 용도로만 사용한다.

---

# 4. 작업 방식 — 절대 잊지 말 것

사용자 명령 의미:

```text
"다음 작업 명세해"
"명세 진행해"

→ SPEC ONLY
→ repo mutation 금지
→ 구현 금지


"작업 시작해"
"작업 진행해"
"진행해"

→ 실제 작업 수행 가능
```

명세와 실행을 섞지 않는다.

Codex / 연구 지시문을 만들 때 기본:

```text
권장 모델: 6.1 Sol
권장 추론 수준: High
```

작업 번호를 유지한다.

예:

```text
NEXT-6E-S6A-R3
```

Manual UAT가 필요한 경우:

```text
한 명령 실행
→ 결과 확인
→ 다음 명령
```

방식으로 진행한다.

---

# 5. Git 운영 규칙

실제 repo 작업 기본 흐름:

```text
latest main 확인
→ exact target 확인
→ latest main에서 branch 생성
→ 최소 변경
→ 테스트 / 허용된 검증
→ PR
→ CI
→ squash merge
→ 새 main SHA 확인
```

완료 보고에는 최소:

- PR 번호
- merge SHA
- new main SHA
- 변경 파일
- CI 상태
- 금지 영역 접근 여부

를 포함한다.

---

# 6. Holdout 규칙 — 최우선 안전 조건

**사용자의 명시적 허가 전 Holdout은 절대 접근 금지.**

금지 범위는 파일 본문만이 아니다.

```text
read
search
existence probe
path discovery
directory listing
metadata
hash
sample count
date range
```

모두 금지.

"파일을 열지만 않으면 된다"가 아니다.

## R3에서 발생한 중요 incident

현재 main의 R3 기록에는 다음이 남아 있다.

- Holdout runtime artifact 자체는 열지 않았다.
- Holdout 경로를 직접 검색하지 않았다.
- Holdout 디렉터리를 enumerate하지 않았다.
- 그러나 Development artifact 이름을 복구하기 위해 과거 handoff context를 조회하던 중 **인접한 Holdout metadata가 문맥상 우발적으로 노출된 것으로 기록됨**.
- 따라서 해당 R3 실행은 "clean Holdout-isolated run"으로 사용할 수 없다.

현재 R3 문서 상태:

```text
Holdout runtime artifact accessed
NO

Holdout metadata exposed incidentally
YES

Holdout guard clean for this R3 run
NO
```

다음 R3 재실행에서는 이 incident를 반복하지 않는다.

Holdout 관련 값은 새 문서 / 새 대화에 재기록하지 않는다.

---

# 7. Production 전략

현재 Production 전략은 정확히 10개다.

```text
trend_following
pullback
breakout
support_bounce
oversold_bounce
range_trading
momentum_continuation
volatility_squeeze
ma20_rebound
trend_recovery
```

전략 baseline:

```text
CURRENT_10_BASELINE
```

과거 governance 단계에서 10전략 운영 상태까지 완료했다.

---

# 8. 이전 주요 완료 단계

NEXT-6A ~ NEXT-6D는 완료된 상태로 취급한다.

NEXT-6E의 주요 진행:

```text
S1
Validation Entry Gate
COMPLETE

S2
Development-only Reference Coverage Audit
COMPLETE

S3
Prospective Reference Capture
COMPLETE

S4
Reference Validation Consolidation & Readiness Review
COMPLETE

S5
Reference Adequacy Method & Risk-Budget Governance Review
COMPLETE
```

S3 핵심 contract:

```text
VN_NEXT6E_S3_PROSPECTIVE_REFERENCE_CAPTURE_V1
VN_NEXT6E_S3_PROSPECTIVE_REFERENCE_STORAGE_V1
VN_NEXT6E_S3_CAPTURE_COMPLETED_AT_CUTOFF_V1

temporal mode
POST_SCANNER_CAPTURE
```

즉 Reference evidence는 Scanner 이후 evidence이며 Scanner input으로 사용하지 않는다.

---

# 9. S4 결과

S4는 Reference Readiness를 통합했다.

주요 구현:

```text
backend/app/macro/reference_readiness.py
backend/tests/test_macro_reference_readiness_next6e_s4.py
```

contract:

```text
VN_NEXT6E_S4_REFERENCE_READINESS_V1
```

S4는 S1/S2/S3를 조합하지만:

```text
decision_input = false
signal_time_equivalence = false
```

를 유지한다.

당시 결과:

```text
REFERENCE_ADEQUACY_UNRESOLVED
```

---

# 10. S5 결과

S5는 method / risk-budget governance research 단계였다.

최종 verdict:

```text
NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY
```

즉:

- stationary bootstrap / dependent methods는 연구 후보가 될 수 있음.
- 그러나 exact StockScope joint target 전체를 바로 자동 승인할 근거는 없음.
- operational tolerance 숫자를 외부 통계 원리에서 자동으로 가져올 수 없음.
- `τ_T / τ_L / τ_S / α_stat / γ_repeat`를 임의로 만들지 않음.
- Reference Adequacy는 계속 unresolved.

---

# 11. Architecture / S6 구조

NEXT-6E post-S5 architecture는 두 독립 blocker를 분리한다.

```text
Track A
Statistical Method

Track B
Operational Risk-Budget / Governance
```

둘 중 하나가 다른 하나를 대신할 수 없다.

향후 convergence 단계인 S6C는:

```text
G-A = PASS
AND
G-B = PASS
```

둘 다 필요하다.

---

# 12. Track A — S6A / R1 / R2 / R2A

## S6A

S6A는 Method Contract를 설계했지만:

```text
METHOD_DESIGNED
G-A = BLOCKED
```

였다.

기존 law-level target이 지나치게 강하다는 문제가 드러났다.

---

## R1 — Sequential Functional Theorem Resolution

R1에서 preferred route를 좁혔다.

```text
Route
SEQUENTIAL_DEPENDENT_MULTIPLIER

Target
JOINT_SEQUENTIAL_FUNCTIONAL_SAMPLING_FLUCTUATION
```

joint process:

```text
Z_i
=
(
  X_i^(1),
  X_i^(5),
  X_i^(10)
)
```

theorem class:

```text
STRICTLY_STATIONARY_STRONG_MIXING

α(r)=O(r^-a)
a > 15/2
```

R1에서 조건부로 정리된 것:

```text
Sequential empirical process
SUPPORTED

Dependent multiplier
SUPPORTED CONDITIONALLY

ECDF transfer
SUPPORTED CONDITIONALLY

Median transfer
SUPPORTED CONDITIONALLY

MAD transfer
SUPPORTED CONDITIONALLY

Nested envelope
SUPPORTED ON INTERIOR DOMAIN

All-N simultaneous inference
SUPPORTED ON INTERIOR DOMAIN

Common-N post-selection
SUPPORTED CONDITIONALLY
```

`γ_repeat`는 기존 law-level target에 묶여 있었기 때문에 Method Contract에서 제거하고, 필요 시 Track B에서 별도 policy concept으로 재정의하도록 했다.

---

## R2 — Candidate Domain / Multiplier Profile

R2에서 multiplier profile을 크게 고정했다.

```text
Multiplier family
MOVING_AVERAGE_DEPENDENT_MULTIPLIER

Kernel
PARZEN

Bandwidth
BK2016_SECTION_5_1_ADAPTIVE_IMSE

Lag cutoff
POLITIS_WHITE_CORRECTED_AUTOMATIC

Multivariate aggregation
MEDIAN

Grid
5 points per dimension
d=3 → 125 points

Centering
FULL_SAMPLE_EMPIRICAL_CENTERING

Manual fallback
FORBIDDEN
```

당시 남은 blocker:

```text
κ
actual-process assumption acceptance
```

---

## R2A — Candidate Domain Governance Decision

R2A에서 exact κ를 **project method-design convention**으로 고정했다.

```text
κ
=
0.10
=
1/10 exact

classification
=
METHOD_DESIGN_PARAMETER

source
=
PROJECT_METHOD_GOVERNANCE_DECISION

theorem-optimal
=
NO
```

canonical lower bound:

```text
N_min_method(n)
=
ceil(n/10)
```

floating point에 의존하지 않는 equivalent integer form:

```text
floor((n+9)/10)
```

CandidateDomainContract:

```text
FROZEN
```

out-of-domain:

```text
OUTSIDE_APPROVED_METHOD_DOMAIN
```

이는 FAIL / UNSTABLE / INADEQUATE와 동일하지 않다.

R2A 이후 상태:

```text
Method state
METHOD_PROFILE_FROZEN

G-A
BLOCKED_ONLY_ON_ASSUMPTION_ACCEPTANCE
```

---

# 13. 현재 R3 상태 — 매우 중요

R3 목적은 처음으로 실제 Development input process가 frozen method assumptions와 양립하는지를 검사하는 것이었다.

원래 허용:

```text
Development INPUT
YES

Development ADEQUACY OUTCOME
NO
```

금지:

```text
passing N
minimum passing N
forward envelopes
Reference Adequacy result
candidate survival
recommended_support
Production outcome
Holdout
```

그러나 현재 R3는 진단까지 가지 못했다.

현재 main에 기록된 R3 final state:

```text
NEXT-6E-S6A-R3
BLOCKED_EVIDENCE_SOURCE_UNAVAILABLE

Method state
METHOD_PROFILE_FROZEN

G-A
BLOCKED

Primary blocker
EVIDENCE_SOURCE_ACCESS_UNRESOLVED

Assumption diagnostics executed
NO

Reference Adequacy
UNRESOLVED
```

---

# 14. 사용자가 방금 물은 "저 파일이 어딨는데?"의 정확한 답

현재 프로젝트 문서가 요구하는 frozen Development artifact identity는 다음이다.

```text
expected project path
backend/runtime/macro/calibration/DEV-7c3f6660b3aae03f.json

artifact filename
DEV-7c3f6660b3aae03f.json

dataset hash
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1

provider
FRED

series
DGS10

Development scope
2016-01-04 .. 2023-12-29

vintage
2023-12-29

analysis rows
1999

warmup
10

historical time quality
DATE_ONLY

PIT eligible rows
0
```

**중요: 위 경로는 "GitHub에서 현재 존재한다고 확인한 파일"이 아니다.**

현재 R3 문서의 실제 결론:

```text
GitHub repository copy
NOT AVAILABLE

connected execution surface
NOT AVAILABLE

working environment exact artifact
NOT AVAILABLE
```

즉 다음 채팅에서:

> "그 파일은 backend/runtime/...에 있습니다."

라고 단정하면 안 된다.

정확한 표현:

> 프로젝트의 frozen artifact identity상 기대 경로가 저 경로로 기록되어 있지만, 현재 GitHub/연결 실행환경에서 실제 파일 bytes는 확인되지 않았다.

이다.

또한 새 FRED 다운로드로 대체하면 안 된다.

이유:

```text
새 다운로드
≠
frozen vintage artifact
≠
declared dataset hash
```

따라서 R3 lineage가 깨진다.

---

# 15. R3에서 원래 확인해야 했던 항목

정확한 frozen Development artifact를 확보한 뒤에만 다음을 검사한다.

```text
A0
Evidence lineage

A1
Native-position completeness

A2
W → X representation identity

A3
Joint alignment

A4
Quantization / ties / atom compatibility

A5
Stationarity compatibility

A6
Strong-mixing model-use compatibility

A7
Median regularity

A8
Positive MAD / zero-scale

A9
MAD local regularity

A10
Multiplier-profile preprocessor computability
```

---

# 16. R3에서 절대 과장하면 안 되는 것

finite sample로:

```text
strict stationarity proven
strong mixing proven
α(r)=O(r^-a), a>15/2 empirically proven
population continuity proven
positive density mathematically proven
```

이라고 하면 안 된다.

허용되는 semantic:

```text
ASSUMPTION_ACCEPTED_FOR_MODEL_USE
```

와:

```text
MATHEMATICALLY_VERIFIED
```

를 분리한다.

---

# 17. R3 clean rerun 조건

다음 R3는 **clean rerun**이어야 한다.

먼저 필요한 것은 exact frozen Development artifact 하나다.

```text
DEV-7c3f6660b3aae03f.json
```

그리고 hash가:

```text
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1
```

와 일치해야 한다.

조건:

1. Holdout 관련 파일/문서/metadata가 노출되지 않는 scope에서 시작한다.
2. exact Development artifact만 확보한다.
3. runtime directory를 광범위하게 enumerate하지 않는다.
4. 새 FRED 데이터를 다운로드해 대체하지 않는다.
5. 다른 vintage를 사용하지 않는다.
6. downstream adequacy outcome에서 raw series를 역추론하지 않는다.
7. artifact가 없으면 다시 BLOCKED 처리한다.

---

# 18. 다음 채팅 첫 행동

새 채팅에서 **바로 진단을 돌리지 않는다.**

첫 순서:

```text
1. latest main 확인

2. 현재 R3 BLOCKED 문서 읽기

3. 사용자에게 exact frozen DEV artifact의 실제 위치를 확인
   또는 사용자가 해당 파일을 대화에 첨부

4. 파일을 확보한 경우 hash 검증

5. Holdout이 전혀 노출되지 않는 clean scope 확인

6. 그 다음 R3 diagnostic protocol 실행
```

사용자에게 묻지 않고 PC 전체, runtime 전체, Drive 전체를 뒤져서 찾으면 안 된다.

---

# 19. 만약 파일이 사용자 PC에 있다면

사용자에게 다음 정도만 확인하면 된다.

예:

```text
StockScope 프로젝트 폴더의
backend/runtime/macro/calibration/
안에
DEV-7c3f6660b3aae03f.json
파일이 실제로 있는지 확인해주세요.
```

또는 파일 자체를 현재 대화에 업로드 받는다.

**Holdout filename / 위치를 같이 요청하지 않는다.**

---

# 20. Track B — 현재 상태

S6B는 완료되었으나 승인 상태가 아니다.

```text
Policy state
POLICY_DESIGNED

G-B
BLOCKED
```

현재 policy entries:

```text
τ_T
null / UNRESOLVED

τ_L
null / UNRESOLVED

τ_S
null / UNRESOLVED

α_stat
null

γ_repeat
removed from Method Contract
future separate policy concept if required

δ_MC
S6C-owned
```

현재 외부 / 기존 프로젝트 근거로 exact numeric threshold를 정당화하지 못했다.

---

# 21. Track B의 남은 blocker

```text
independent numeric evidence
target compatibility
authority appointment
explicit approval
review / expiry details where required
```

필요한 방향:

```text
OUTCOME-INDEPENDENT ANALYTICAL / SYNTHETIC SENSITIVITY
```

단:

- current Development envelope에 맞추기 금지
- passing N 보존을 위해 threshold 선택 금지
- Strategy / Production 성능에 맞추기 금지

---

# 22. S6C 진입 조건

아직 S6C로 가면 안 된다.

필수:

```text
G-A = PASS
AND
G-B = PASS
```

현재:

```text
G-A = BLOCKED
G-B = BLOCKED
```

따라서 S6C approval task 금지.

---

# 23. ENV-V2 / PC 간 운용

이미 완료된 환경 bootstrap 상태:

- PC-A ↔ PC-B ↔ PC-A Drive physical roundtrip PASS
- PC-B는 계속 켜둘 필요 없음
- Fresh clone bootstrap T2 COMPLETE
- `setup.ps1` canonical
- 5 runtime DB safe initialization 확인
- blank API keys → READY + ACTION_REQUIRED
- blank market data → DATA_REQUIRED
- Drive 없는 신규 사용자도 bootstrap 가능
- pristine marker가 있는 경우만 safe restore 허용
- CI에 Fresh Clone / Windows 포함

사용자가 학교/기숙사 PC를 오가므로 repo 기준 상태와 local runtime 상태를 섞지 않는다.

---

# 24. Runtime / SQLite 안전 규칙

절대 casually 하지 않는다.

```text
runtime SQLite 새로 생성
runtime DB reset
WAL 삭제/조작
migration 임의 실행
cloud synced path에서 live DB 운용
```

R3 evidence 때문에 임의 SQLite를 열어 찾는 것도 금지.

정확한 DB / table / query가 기존 contract로 식별된 경우에만 read-only/query-only 접근을 고려한다.

---

# 25. UI 철학

앞으로 기능 개발 시 반드시 유지:

- 내부 계산은 내부에서 처리.
- UI에는 결과와 필요한 맥락 중심.
- 사용자가 빠르게 판단할 수 있어야 함.
- 검증 / 추적 / replay 버튼을 화면에 남발하지 않는다.
- 흔한 AI dashboard 느낌을 피한다.
- 책임을 StockScope가 전부 지는 구조로 만들지 않는다.
- 과도한 장문 보고서형 UI를 피한다.
- 보유 종목 급변 대응을 돕되 자동 행동은 하지 않는다.

---

# 26. 중요한 기존 문서

현재 NEXT-6E 소스오브트루스 우선순위:

```text
docs/StockScope_NEXT6E_S6A_R3_ASSUMPTION_ACCEPTANCE_EVIDENCE_GATE_2026-10-02.md

docs/StockScope_NEXT6E_S6A_R2A_CANDIDATE_DOMAIN_GOVERNANCE_DECISION_2026-10-02.md

docs/StockScope_NEXT6E_S6A_R2_CANDIDATE_DOMAIN_MULTIPLIER_PROFILE_RESOLUTION_2026-10-02.md

docs/StockScope_NEXT6E_S6A_R1_SEQUENTIAL_FUNCTIONAL_THEOREM_RESOLUTION_2026-10-02.md

docs/StockScope_NEXT6E_S6A_METHOD_CONTRACT_RESOLUTION_2026-10-02.md

docs/StockScope_NEXT6E_S6B_RISK_BUDGET_GOVERNANCE_RESOLUTION_2026-10-02.md

docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md
```

상위 설계:

```text
docs/StockScope_MASTER_ARCHITECTURE_vNext.md
docs/StockScope_DEVELOPMENT_ROADMAP_vNext.md
docs/StockScope_IMPLEMENTATION_BASELINE_vNext.md
```

과거 handoff / recovery 문서는 historical context로만 사용하고 최신 계약보다 우선하지 않는다.

---

# 27. 과거 주요 handoff 문서

historical:

```text
StockScope_CURRENT_STATE_2026-09-26.md
StockScope_RECOVERY_CONTEXT_2026-09-26.md
StockScope_ASTRA_REDESIGN_HANDOFF_2026-09-27.md
StockScope_HANDOFF_2026-10-01_NEXT6D_S2_COMPLETE.md
```

오래된 handoff에서 현재 contract와 충돌하는 내용은 최신 NEXT-6E 문서를 우선한다.

특히 과거 handoff context를 검색하다 Holdout metadata가 같이 노출될 수 있으므로 R3 clean rerun에서는 무분별하게 broad search하지 않는다.

---

# 28. 코드 쪽 주요 Reference Adequacy 파일

현재 관련 코드 영역:

```text
backend/app/macro/reference_adequacy_protocol.py
backend/app/macro/reference_readiness.py
backend/app/macro/features.py
backend/app/macro/distribution.py
backend/app/macro/reference_stability.py
backend/app/macro/identity.py
backend/app/macro/calibration_dataset.py
backend/app/macro/development_coverage.py
```

R3 시작 직전에 위 일부 파일은 Development evidence source를 찾기 위해 read-only로 확인했다.

**하지만 exact frozen Development JSON bytes는 repo에서 찾지 못했다.**

---

# 29. Current V3 / V4 상태

현재:

```text
V3
UNCHANGED

V4
NOT CREATED
```

V3에는 기존:

```text
ABSOLUTE_MEDIAN_SHIFT
ABSOLUTE_MAD_SHIFT
RELATIVE_MAD_SHIFT
```

관련 semantics가 존재한다.

NEXT-6E research intent는:

```text
NORMALIZED_MEDIAN_SHIFT
RELATIVE_MAD_SHIFT
```

중심으로 이동했지만 아직 V4를 만들지 않았다.

R3/G-A와 G-B가 닫히기 전에 V4를 구현하지 않는다.

---

# 30. Reference Adequacy 현재 상태

무조건 유지:

```text
Reference Adequacy
UNRESOLVED

minimum_prior_observations
null

recommended_support
null

RATE_SPIKE
UNCALIBRATED
```

현재 R3가 blocked된 상태에서 임의 계산 / 추천 숫자를 만들면 안 된다.

---

# 31. 다음 작업의 정상 흐름

현재 가장 안전한 흐름:

```text
현재
R3 BLOCKED
EVIDENCE_SOURCE_UNAVAILABLE

        ↓

exact frozen Development artifact 확보

        ↓

clean R3 rerun
(no Holdout metadata exposure)

        ↓

G-A PASS 가능 여부 판정

        ↓

Track B blocker resolution
independent sensitivity / governance

        ↓

G-B PASS

        ↓

S6C
Convergence / Numerical Contract

        ↓

future V4 preregistration

        ↓

evaluator implementation

        ↓

Development-only evaluation

        ↓

Holdout
ONLY AFTER EXPLICIT USER PERMISSION
```

---

# 32. 다음 채팅에서 하면 안 되는 실수

1. R3가 완료되었다고 착각하지 말 것.
2. 현재 main의 R3 문서는 **BLOCKED record**다.
3. exact Development JSON이 GitHub에 있다고 가정하지 말 것.
4. 새 FRED 다운로드로 frozen artifact를 대체하지 말 것.
5. Holdout filename/path를 찾지 말 것.
6. broad handoff search로 Holdout metadata를 다시 노출하지 말 것.
7. passing N / adequacy envelope를 assumption evidence로 사용하지 말 것.
8. κ=0.10을 theorem-optimal이라고 표현하지 말 것.
9. `ceil(n/10)`을 recommended_support라고 부르지 말 것.
10. R3가 끝나기 전에 V4/evaluator를 만들지 말 것.
11. G-A만 PASS해도 S6C로 바로 가지 말 것.
12. G-B도 PASS해야 한다.
13. 문서만 늘리고 실제 blocker를 잊지 말 것.
14. 오래된 문서가 최신 contract를 덮어쓰게 하지 말 것.

---

# 33. 새 채팅에서 사용자에게 가장 먼저 설명할 현재 상태

짧게 말하면:

> 현재 Track A의 통계 설계는 거의 끝났고 κ=1/10까지 고정됐다. 하지만 R3에서 실제 Development source의 assumption compatibility를 검사하려던 순간, frozen Development JSON의 실제 파일 내용이 GitHub/현재 연결 환경에서 확인되지 않아 fail-close로 중단됐다. 따라서 다음 작업은 그 exact Development artifact를 확보해서 clean R3를 다시 실행하는 것이다. Holdout은 절대 접근하지 않는다.

---

# 34. 사용자가 "다음 작업 명세해"라고 하면

현재 R3 blocked 상태 때문에 바로 새 번호를 만들지 않는다.

먼저 **exact frozen Development artifact를 확보할 방법**이 있는지 확인해야 한다.

파일이 확보된 경우에만 clean R3 rerun 명세를 만든다.

파일이 없으면:

```text
R3 remains BLOCKED
```

로 유지한다.

---

# 35. 사용자가 "작업 진행해"라고 하면

현재 상태에서는 곧바로 diagnostics를 돌리는 것이 아니라:

```text
1. latest main 확인
2. exact DEV artifact 존재 여부를 user-provided / authorized path에서 확인
3. hash 확인
4. clean Holdout isolation 확인
5. 그 다음 R3 diagnostics
```

순서다.

파일 위치를 모르면 사용자가 프로젝트 PC에서 경로를 확인하게 해야 한다.

PC 전체 자동 탐색 금지.

---

# 36. 현재 프로젝트 건강 상태

프로젝트가 망가진 상태가 아니다.

현재:

- main은 clean documented state.
- Production 기능 변경 없음.
- runtime 변경 없음.
- V3 변경 없음.
- V4 없음.
- evaluator 없음.
- Reference Adequacy는 fail-open하지 않고 unresolved 유지.
- R3는 source unavailable 때문에 **정상적으로 fail-close**한 상태.

즉 현재 문제는 코드 파손이 아니라:

```text
정확한 frozen Development evidence artifact가
현재 실행 surface에 없다는 것
```

이다.

---

# 37. 최종 복구 체크리스트

새 채팅에서 이 문서를 읽은 뒤 다음을 확인한다.

```text
[ ] latest main == expected or newer
[ ] newest NEXT-6E docs read
[ ] R3 BLOCKED state understood
[ ] exact DEV artifact location not guessed
[ ] Holdout remains untouched
[ ] no runtime SQLite mutation
[ ] no Development adequacy outcome inspection
[ ] κ remains 1/10 exact
[ ] Multiplier profile unchanged
[ ] Reference Adequacy remains UNRESOLVED
[ ] G-B remains BLOCKED
[ ] S6C not started
[ ] V4 not created
[ ] Production impact remains NONE
```

---

# 38. Handoff Summary

```text
STOCKSCOPE HANDOFF
2026-10-02

main
725b4d0a79344aca4f9fa7e585098059da24bd45

NEXT-6E Track A
METHOD_PROFILE_FROZEN
R3 BLOCKED
G-A BLOCKED

R3 blocker
EVIDENCE_SOURCE_ACCESS_UNRESOLVED

Expected frozen DEV artifact
backend/runtime/macro/calibration/DEV-7c3f6660b3aae03f.json

Exact artifact bytes available in repo/current connected environment
NO

Clean Holdout-isolated R3 completed
NO

Track B
POLICY_DESIGNED
G-B BLOCKED

Reference Adequacy
UNRESOLVED

minimum_prior_observations
null

recommended_support
null

RATE_SPIKE
UNCALIBRATED

V3 changed
NO

V4 created
NO

Evaluator
NO

Production impact
NONE

NEXT ACTION
obtain exact frozen DEV artifact
→ clean R3 rerun
→ G-A decision
→ Track B resolution
→ only then S6C
```
