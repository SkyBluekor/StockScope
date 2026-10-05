# StockScope NEXT-6E-S6A-R5-D2B — Simultaneous-Index Architecture 결정

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 architecture / governance decision. 구현 문서가 아니다.  
기준 main: \`4f65f02a6fe99a6874589f8a599eb249965ba4d4\`  
Parent: \`NEXT-6E-S6A-R5-D2A\`  
Parent verdict: \`BLOCKED_SIMULTANEOUS_LOCAL_TIME\`

## 1. 최종 결정

R5의 simultaneous-index architecture는 다음으로 선택한다.

\`\`\`text
S2
=
PROSPECTIVELY_FIXED_FINITE_ANCHOR_GRID
\`\`\`

정확한 의미는:

> R5는 더 이상 \`ceil(n/10) <= N <= n-1\`의 모든 정수 N을 statistical post-selection candidate로 사용하지 않는다.  
> 대신 Development/Reference Adequacy/Production 결과를 보기 전에 별도 governance 단계에서 고정한 유한 anchor family 안에서만 common-N을 선택한다.

새 common-N 의미:

\`\`\`text
R5_COMMON_N
=
smallest supported candidate N
within the prospectively approved finite anchor family
\`\`\`

이번 D2B에서는 **anchor grid의 실제 숫자를 고르지 않는다.**

\`\`\`text
grid values
=
UNRESOLVED / D2C OWNED
\`\`\`

R2A의 기존 CandidateDomainContract V1은 수정하지 않는다.

\`\`\`text
R2A V1
=
HISTORICAL / IMMUTABLE

R5 CandidateDomainContract V2
=
REQUIRED
\`\`\`

최종 stage state:

\`\`\`text
NEXT-6E-S6A-R5-D2B
=
COMPLETE

Selected architecture
=
PROSPECTIVE_FINITE_ANCHOR_GRID

Current CandidateDomain V1
=
NOT MUTATED

New CandidateDomain V2
=
REQUIRED

Grid values
=
NOT YET SELECTED

R5 Method
=
NOT FROZEN

R5 G-A
=
BLOCKED

Implementation
=
NOT AUTHORIZED
\`\`\`

---

## 2. 이번 결정이 필요한 이유

D2A에서 가장 근본적인 blocker는 atomic/ties 자체가 아니었다.

현재 proof state:

\`\`\`text
Atomic lattice local-EDF
=
PROOF_CANDIDATE_IDENTIFIED

Latest-state u=1
=
PROOF_CANDIDATE_IDENTIFIED

All-anchor / all-later simultaneous event
=
BLOCKED

Calibration
=
BLOCKED_BY_SIMULTANEOUS_EVENT
\`\`\`

기존 R2A architecture는 모든 정수 anchor를 candidate로 사용한다.

\`\`\`text
ceil(n/10) <= N <= n-1
\`\`\`

R5의 local-distributional route에서는 각 candidate가 local time:

\`\`\`text
s=N/n
\`\`\`

을 만든다.

그리고 각 anchor는 이후 local states:

\`\`\`text
v=t/n, v>s
\`\`\`

와 비교되어야 한다.

따라서 required stochastic index는 사실상:

\`\`\`text
horizon h
× anchor s
× later v
× threshold x
\`\`\`

이다.

bandwidth가 n과 함께 줄어드는 localized inference에서는 이 index family가 단순한 fixed Donsker class가 아니다.

D2A에서 검토한 2026 localized FCLT도 fixed/totally-bounded projection에는 중요한 진전을 제공하지만 StockScope의 shrinking localization centers 전체에 대한 direct sup-band를 제공하지 않는다.

이 상태에서 S1을 무기한 계속하는 것은 구현 전 설계를 충분히 닫는다는 프로젝트 원칙과 달리, 종료 기준이 불명확한 새로운 theorem-development project로 커질 위험이 있다.

---

## 3. 결정 원칙

S1-S4는 다음 사전 기준으로 비교했다.

1. statistical validity를 현실적으로 확보할 수 있어야 한다.
2. integer lattice와 ties를 보존해야 한다.
3. latest-state inference를 포기하지 않아야 한다.
4. 1/5/10 horizon joint structure를 보존해야 한다.
5. DEV outcome에 따라 architecture가 바뀌어서는 안 된다.
6. Holdout/Reference Adequacy outcome을 사용하지 않아야 한다.
7. 기존 Reference Adequacy product meaning을 가능한 한 많이 보존해야 한다.
8. common-N의 사용자 해석이 명확해야 한다.
9. 새 theorem work의 범위가 versionable하고 종료 가능해야 한다.
10. 구현과 audit이 현실적이어야 한다.
11. statistical error와 product movement tolerance를 계속 분리해야 한다.
12. 향후 method failure가 생기면 fail-close할 수 있어야 한다.

"수학적으로 가장 쉬운 route"를 고르는 것이 목적이 아니다.

---

## 4. S1 — Full all-anchor theorem continuation

### 정의

현재 R2A semantics를 완전히 유지한다.

\`\`\`text
candidate anchors
=
every integer N
such that
ceil(n/10) <= N <= n-1
\`\`\`

required claim:

\`\`\`text
one simultaneous event
covers every eligible anchor
and every required later local state
\`\`\`

### 장점

- 기존 common-N 의미 완전 보존.
- "승인된 domain 내 최소 N"이라는 해석이 가장 정확함.
- candidate-resolution approximation error가 없음.
- 기존 R2A contract change가 최소.

### 문제

D2A 결과상 theorem target은:

\`\`\`text
n-dependent localized indicator class
× all local centers
× threshold class
× 3 horizons
× right boundary
\`\`\`

이다.

현재 reviewed literature는 이 exact object에 대한 ready-made theorem을 제공하지 않는다.

추가로 필요한 것은 기존 theorem 적용이 아니라 project-specific uniform/high-dimensional approximation의 실질적인 신규 연구다.

S1을 선택하면 다음 종료 조건을 미리 특정하기 어렵다.

\`\`\`text
How much theorem development is enough?
Which approximation theorem is final?
Which growing-class rate is sufficient?
Which critical-value construction is final?
\`\`\`

이것은 product meaning을 가장 잘 보존하지만 Track-A를 사실상 open-ended statistical-theory research로 바꾼다.

### 판정

\`\`\`text
S1
=
REJECTED_FOR_CURRENT_R5_ARCHITECTURE

reason
=
THEOREM_SCOPE_OPEN_ENDED
\`\`\`

중요:

S1을 "수학적으로 불가능"이라고 선언하지 않는다.

판정은:

> 현재 StockScope 목적 대비 요구되는 추가 theorem scope가 불명확하고 지나치게 크므로 이번 R5 architecture로 채택하지 않는다.

이다.

---

## 5. S2 — Prospectively fixed finite anchor grid

### 정의

anchor candidate family를 유한하고 versioned하게 고정한다.

\`\`\`text
A_n
=
{N_1(n), ..., N_m(n)}

m
=
finite / prospectively governed
\`\`\`

각 anchor는 data outcome이 아니라 사전에 고정한 exact rational fraction rule 등으로 결정한다.

예시 형태만:

\`\`\`text
N_j(n)
=
deterministic_integer_map(r_j, n)
\`\`\`

실제 \`r_j\`는 D2C에서 정한다.

### 보존되는 것

S2는 다음을 유지한다.

\`\`\`text
κ = 1/10 lower claim boundary
1/5/10 joint horizons
integer lattice
ties
right-continuous CDF
midpoint median
raw MAD
density-free CDF-band projection
latest-state requirement
TAIL / location / scale separation
worst-case later-state semantics
ALL_FAMILIES_AND
statistical uncertainty vs policy tolerance separation
fail-closed governance
\`\`\`

### 변경되는 것

오직 candidate selection resolution이 바뀐다.

기존:

\`\`\`text
minimum supported N
among every eligible integer N
\`\`\`

R5:

\`\`\`text
minimum supported N
among the prospectively approved finite anchor family
\`\`\`

따라서 이것을 단순히 "minimum observations"라고 표시해서는 안 된다.

정확한 scientific meaning:

\`\`\`text
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR
\`\`\`

이다.

### 왜 선택하는가

S2는 D2A의 blocker를 완전히 없애는 마법이 아니다.

특히:

\`\`\`text
later-time index v
threshold index x
latest-state boundary
atomic EDF transfer
\`\`\`

는 여전히 theorem work가 필요하다.

그러나 **post-selection anchor multiplicity를 fixed/versioned family로 제한**해 theorem target을 명확히 줄인다.

이 변경은:

- Development passing result를 사용하지 않고;
- R2A κ 하한을 유지하며;
- worst-case later movement를 유지하고;
- TAIL/median/MAD product meaning을 유지하면서;
- theorem family와 critical-value target을 versionable한 finite-anchor architecture로 만든다.

고차원 dependent-data literature에는 finite/growing vector의 maximum에 대한 Gaussian approximation과 bootstrap theory가 존재한다. 이는 StockScope의 locally stationary lattice problem을 자동 해결하지 않지만, finite/versioned anchor family가 full continuum/every-integer selector보다 후속 theorem 설계에 현실적인 bridge를 제공한다.

따라서:

\`\`\`text
S2
=
SELECTED
\`\`\`

---

## 6. S2가 해결하지 않는 것

이 결정을 과대해석하지 않는다.

S2만으로 다음은 PASS되지 않는다.

\`\`\`text
atomic local-EDF theorem
NO

functional-dependence transfer
NO

u=1 one-sided theorem
NO

all-later local-time uncertainty
NO

critical-value calibration
NO
\`\`\`

특히 all-later semantics는 유지한다.

S2 때문에 몰래:

\`\`\`text
later v
=
finite favorable dates only
\`\`\`

로 바꾸지 않는다.

D2C 이후 theorem research에서도 all-later component가 계속 막히면 반드시 새 blocker를 반환한다.

그 경우:

\`\`\`text
R5 method
=
NOT FROZEN
\`\`\`

을 유지하며 S3/S4로 자동 전환하지 않는다.

---

## 7. S3 — Integrated local-drift target

### 장점

통계적으로:

\`\`\`text
∫ w(v) D(s,v) dv
\`\`\`

같은 integrated functional은 \`L²\` / distribution-valued FCLT와 더 자연스럽게 연결될 가능성이 있다.

### 문제

Reference Adequacy의 현재 product concern은:

> 이후 어느 지점에서라도 reference reuse가 더 이상 적절하지 않을 정도로 움직이는가?

라는 worst-case semantics에 가깝다.

integrated target은 큰 localized movement를 평균으로 희석할 수 있다.

따라서 TAIL/median/MAD tolerance의 기존 의미까지 바뀐다.

### 판정

\`\`\`text
S3
=
REJECTED_PRODUCT_SEMANTIC_DRIFT
\`\`\`

수학적 편의를 위해 product target을 바꾸지 않는다.

---

## 8. S4 — Local estimation + prospective revocation monitor

### 장점

운영 관점에서는 자연스럽다.

\`\`\`text
estimate current local law
→ monitor change
→ revoke stale reference
\`\`\`

방식은 실제 시장 regime 변화에 빠르게 대응할 수 있다.

### 문제

이 route는 현재 Reference Adequacy architecture를 작은 수정으로 고치는 것이 아니다.

새로 필요한 것:

\`\`\`text
ReferenceEstimationContract
ChangeMonitorContract
FalseAlarmBudget
DetectionDelayContract
RevocationContract
ResetContract
PostAlarmEvidenceContract
\`\`\`

또한 기존 common-N 의미를 대부분 다시 정의해야 한다.

### 판정

\`\`\`text
S4
=
NOT_SELECTED_FOR_R5_METHOD_RESOLUTION
\`\`\`

향후 operational revocation feature로는 유지할 수 있으나 현재 Track-A theorem blocker의 fallback으로 사용하지 않는다.

---

## 9. Decision matrix

| Criterion | S1 Full all-anchor | S2 Finite anchor grid | S3 Integrated drift | S4 Estimation + monitor |
| --- | --- | --- | --- | --- |
| statistical research tractability | LOW | MEDIUM/HIGH | MEDIUM | MEDIUM |
| lattice/ties preservation | YES | YES | YES | YES |
| latest-state requirement | YES | YES | POSSIBLE | YES |
| 1/5/10 joint structure | YES | YES | POSSIBLE | POSSIBLE |
| original worst-case later meaning | YES | YES | NO / materially changed | CHANGED |
| existing common-N meaning | FULL | MODIFIED MINIMALLY | LOST | REPLACED |
| outcome independence | YES | YES | YES | YES |
| R2A κ retention | YES | YES | MAYBE | MAYBE |
| new governance burden | LOW | MODERATE | HIGH | VERY HIGH |
| theorem scope bounded/versionable | LOW | HIGH | HIGH | MEDIUM |
| user interpretation | HIGH | HIGH if labeled correctly | LOWER | DIFFERENT |
| selected | NO | **YES** | NO | NO |

---

## 10. CandidateDomain V1 preservation

기존:

\`\`\`text
NEXT6E_S6A_R2A_CANDIDATE_DOMAIN_V1
\`\`\`

은 immutable history다.

그 문서의 당시 decision은 당시 R2 stationary theorem architecture 안에서 유효했다.

R5 nonstationary method가 candidate family를 바꾼다고 해서 과거 V1을 수정하거나 잘못된 것으로 재분류하지 않는다.

상태:

\`\`\`text
R2A CandidateDomain V1
=
HISTORICAL / IMMUTABLE / SUPERSEDED_FOR_R5_ONLY
\`\`\`

R4 historical artifacts는 계속 V1 identity를 사용한다.

---

## 11. R5 CandidateDomain V2 requirement

후속 D2C는 새 contract를 만들어야 한다.

권장 identity:

\`\`\`text
NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2
\`\`\`

필수 fields:

\`\`\`text
contract_version
contract_id

lower_fraction
=
1/10 exact

candidate_family
=
PROSPECTIVE_FINITE_ANCHOR_GRID

grid_rule_id
grid_rule_version

anchor_fractions[]
integer_mapping_rule
deduplication_rule
ordering_rule

minimum_cardinality
maximum_cardinality

latest_state_rule
later_state_scope

common_N_semantics
=
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR

grid_resolution_semantics
candidate_resolution_error_semantics

out_of_grid_state
change_control
retroactive_relabeling
status
\`\`\`

이번 D2B는 values를 채우지 않는다.

---

## 12. κ=1/10 disposition

R2A에서 고정한:

\`\`\`text
κ
=
1/10
\`\`\`

은 유지한다.

R5에서 새 의미:

> approved finite anchors는 모두 \`s >= 1/10\` 안에 있어야 한다.

따라서:

\`\`\`text
κ
=
RETAINED LOWER CLAIM BOUNDARY
\`\`\`

이다.

하지만:

\`\`\`text
κ
!=
grid spacing
κ
!=
number of anchors
κ
!=
minimum_prior_observations
\`\`\`

이다.

---

## 13. Grid 숫자를 지금 선택하지 않는 이유

D2B에서 실제 anchor fractions를 선택하지 않는다.

금지 예:

\`\`\`text
0.10, 0.20, ..., 0.90
because round numbers are convenient

or

200,400,600,...
because n≈1999
\`\`\`

grid resolution은 별도 method-design decision이다.

D2C는 outcome-independent하게 최소 다음을 비교해야 한다.

1. product resolution requirement;
2. maximum allowed candidate-resolution loss;
3. multiplicity burden;
4. local estimator support / bandwidth geometry;
5. latest-state later-window availability;
6. integer-rounding stability;
7. cross-n consistency;
8. computation;
9. auditability;
10. downstream UI terminology.

---

## 14. Candidate resolution error

finite grid를 도입하면 새로운 approximation concept가 생긴다.

가상의 every-integer solution \`N_integer*\`와 grid-selected \`N_grid*\` 사이 차이는:

\`\`\`text
candidate resolution loss
=
N_grid* - N_integer*
\`\`\`

로 생각할 수 있다.

그러나:

\`\`\`text
N_integer*
\`\`\`

는 R5 method가 실제로 평가하지 않는 counterfactual object일 수 있으므로 runtime에서 계산하거나 보고하지 않는다.

따라서 D2C는 practical contract를:

\`\`\`text
maximum spacing / resolution
\`\`\`

형태로 prospective하게 정의해야 한다.

이 오차는:

\`\`\`text
statistical uncertainty
NO

Monte Carlo uncertainty
NO

policy tolerance
NO

method-resolution granularity
YES
\`\`\`

이다.

별도 ledger/metadata로 관리해야 한다.

---

## 15. UI / output semantic change

R5가 향후 최종 사용 단계에 도달한다면 아래 표현은 금지한다.

\`\`\`text
"정확한 최소 필요 관측 수"
"모든 N 중 최소"
\`\`\`

허용 표현:

\`\`\`text
"승인된 기준점 중 최소 지원 구간"
"minimum supported approved anchor"
\`\`\`

사용자에게 grid mechanics 전체를 노출할 필요는 없지만, 결과를 실제보다 더 정밀하게 보이게 해서는 안 된다.

---

## 16. All-later semantics preservation

이번 decision의 중요한 제한이다.

S2는 anchor만 finite family로 바꾼다.

다음 product requirement는 유지한다.

\`\`\`text
for selected anchor N_j,
required later-state scope
must represent the complete approved later interval
\`\`\`

따라서 D2C에서:

\`\`\`text
latest_state_rule
later_state_scope
\`\`\`

를 정확히 고정해야 한다.

나중에 theorem convenience 때문에 later states도 sparse grid로 줄이려면:

\`\`\`text
NEW ARCHITECTURE DECISION REQUIRED
\`\`\`

이다.

D2B decision으로 자동 허용되지 않는다.

---

## 17. Statistical research implication

S2 이후 stochastic object는 개념적으로:

\`\`\`text
finite anchor family
× all approved later local states
× horizon
× threshold
\`\`\`

이다.

anchor post-selection multiplicity는 finite and prospectively fixed가 된다.

이 때문에 후속 theorem은 다음 bridge를 연구할 수 있다.

1. atomic local transform lemma;
2. one-sided local EDF boundary result;
3. finite-anchor coupled local processes;
4. high-dimensional / growing-vector approximation for discretized later-time representation if theoremically justified;
5. conservative critical-value construction.

최근 high-dimensional dependent-data Gaussian approximation literature는 temporally dependent high-dimensional vectors의 maxima와 bootstrap에 대한 nonasymptotic tools를 제공한다.

이 문헌은 StockScope theorem을 제공하지 않는다.

정확한 의미:

\`\`\`text
RESEARCH BRIDGE
not
METHOD APPROVAL
\`\`\`

이다.

---

## 18. D2C next task

다음 authorized design task:

\`\`\`text
NEXT-6E-S6A-R5-D2C
FINITE ANCHOR GRID GOVERNANCE
\`\`\`

목표:

1. exact grid-construction family 비교;
2. grid cardinality freeze;
3. exact rational anchor fractions freeze;
4. deterministic integer mapping;
5. duplicate/collision rule;
6. edge/boundary rule;
7. maximum anchor spacing / resolution semantics;
8. latest-state pairing;
9. all-later scope identity;
10. new CandidateDomainContract V2;
11. R2A V1 supersession relation;
12. version/change-control rules.

D2C도 DEV 결과를 사용하지 않는다.

D2C가 완료되어도 method 전체가 바로 frozen되는 것은 아니다.

그 다음에는 architecture-specific theorem resolution이 필요하다.

---

## 19. Post-D2C theorem work

D2C 이후 예상 단계:

\`\`\`text
R5-D2D
FINITE-ANCHOR LOCAL-EDF THEOREM RESOLUTION
\`\`\`

최소 proof obligations:

\`\`\`text
atomic transform lemma
one-sided latest-state corollary
local functional-dependence contract
local EDF bias/stochastic limit
finite-anchor joint coupling
all-later simultaneous coverage
calibration
median/MAD projection
\`\`\`

D2D가 닫혀야 R5-D2 final method freeze로 돌아갈 수 있다.

---

## 20. S6B / risk-budget impact

이번 decision은 numeric risk tolerance를 만들지 않는다.

계속:

\`\`\`text
τ_T = null
τ_L = null
τ_S = null
α_stat = null
γ_repeat = null
\`\`\`

이다.

다만 \`α_stat\`이 향후 적용될 statistical family identity는:

\`\`\`text
all integer anchor family
\`\`\`

에서:

\`\`\`text
approved finite anchor family
× approved later-state family
\`\`\`

로 바뀐다.

따라서 S6B/S6C convergence 때 exact target-version compatibility를 다시 확인해야 한다.

---

## 21. Fail-closed rules

다음 행동은 금지한다.

\`\`\`text
DEV passing N를 본 뒤 anchor 추가
NO

DEV failing N를 grid에서 제거
NO

grid 사이에 결과가 좋아 보이면 anchor 삽입
NO

grid가 너무 보수적으로 나오면 spacing 축소
NO

R2A V1 역사 수정
NO

all-later가 어려우면 sparse later points로 자동 축소
NO

S3 integrated target 자동 전환
NO

S4 monitor architecture 자동 전환
NO
\`\`\`

grid가 실패하면 새 versioned governance decision이 필요하다.

---

## 22. Data / execution isolation

이번 D2B:

\`\`\`text
DEV rerun
=
NO

DEV envelope
=
NOT ACCESSED

passing candidate
=
NOT ACCESSED

Reference Adequacy result
=
NOT ACCESSED

Holdout
=
LOCKED / NOT ACCESSED

runtime DB
=
NOT ACCESSED

Production outcome
=
NOT ACCESSED

Backend code
=
UNCHANGED

Tests
=
UNCHANGED
\`\`\`

external literature는 architecture feasibility 확인에만 사용했다.

---

## 23. Literature / feasibility register

### 23.1 Chang et al. — high-dimensional dependent Gaussian approximation

Chang, Chen, Wu 계열의 2024 high-dimensional dependent-data work는 dependent random-vector sums에 대해 hyper-rectangle / max-type Gaussian approximation과 kernel-type long-run covariance bootstrap을 다룬다.

Relevance:

\`\`\`text
finite / growing vector max inference
=
SUPPORTED AS A RESEARCH FAMILY

StockScope locally stationary lattice EDF
=
NOT DIRECTLY COVERED
\`\`\`

이 차이를 유지한다.

### 23.2 2025/2026 high-dimensional maxima bootstrap work

최근 multiplier / empirical-subsample bootstrap literature도 temporally dependent high-dimensional maxima에 대한 inference를 확장한다.

이는 finite anchor architecture가 full continuum all-anchor route보다 후속 approximation design에 더 자연스럽다는 feasibility evidence다.

StockScope-specific local-time nonstationarity, lattice transform, boundary bias는 여전히 별도 proof obligation이다.

### 23.3 Time-varying simultaneous bands

locally stationary regression / smooth statistics에 대해 full-time simultaneous confidence bands가 구성되는 문헌이 존재한다.

이는 "local-time simultaneous band가 원천적으로 불가능"하다는 뜻이 아님을 보여준다.

하지만 해당 bands는 statistic-specific smooth expansion을 사용하며 atomic EDF threshold process를 자동 승인하지 않는다.

따라서 S2 decision은:

\`\`\`text
theorem already solved
\`\`\`

가 아니라:

\`\`\`text
theorem target narrowed to a bounded, versionable research problem
\`\`\`

이라는 의미다.

---

## 24. Decision register

| Decision | Alternatives | Selected | Reason |
| --- | --- | --- | --- |
| simultaneous-index architecture | S1/S2/S3/S4 | S2 | product semantics를 대부분 보존하면서 theorem scope를 finite/versionable하게 줄임 |
| all-integer candidate family | retain/change | CHANGE FOR R5 | D2A all-anchor blocker의 primary source |
| κ lower fraction | retain/change | RETAIN 1/10 | outcome-independent historical method boundary |
| actual grid values | choose/defer | DEFER TO D2C | numeric grid requires separate governance |
| all-later scope | retain/change | RETAIN | worst-case Reference Adequacy meaning 보존 |
| target TAIL/L/S | retain/change | RETAIN | S3 semantic drift 회피 |
| monitoring split | primary/future | FUTURE ONLY | S4 architecture expansion 회피 |
| implementation | start/block | BLOCK | method not frozen |

---

## 25. Final state

\`\`\`text
NEXT-6E-S6A-R5-D2B
=
COMPLETE

Architecture decision
=
S2 PROSPECTIVE_FINITE_ANCHOR_GRID

R2A CandidateDomain V1
=
HISTORICAL / IMMUTABLE
SUPERSEDED FOR R5 ONLY

R5 CandidateDomain V2
=
REQUIRED

κ
=
1/10 RETAINED

Grid values
=
UNRESOLVED
D2C OWNED

Common-N semantics
=
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR

All-later semantics
=
RETAINED

TAIL / location / scale target
=
RETAINED

Latest-state requirement
=
RETAINED

R5 method
=
NOT FROZEN

R5 G-A
=
BLOCKED

R5-D3
=
NOT AUTHORIZED

DEV
=
NOT RERUN

Reference Adequacy
=
NOT ACCESSED

Holdout
=
LOCKED / NOT ACCESSED

DB/runtime
=
NOT ACCESSED

Production impact
=
NONE
\`\`\`
