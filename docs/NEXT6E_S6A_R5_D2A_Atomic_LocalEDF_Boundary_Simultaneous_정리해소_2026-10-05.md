# StockScope NEXT-6E-S6A-R5-D2A — Atomic Local-EDF / Boundary / Simultaneous 정리 해소

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 theorem-blocker resolution 결과. 구현 문서가 아니다.  
기준 main: `b4e7268a9cb855768d7db7692894b728cea08ae6`  
Parent: `NEXT-6E-S6A-R5-D2`  
Primary route: `LOCAL_DISTRIBUTIONAL_REFERENCE`

## 1. 최종 판정

```text
NEXT-6E-S6A-R5-D2A
=
BLOCKED_SIMULTANEOUS_LOCAL_TIME

Atomic / lattice local-EDF
=
PROOF_CANDIDATE_IDENTIFIED
FORMAL_PROJECT_LEMMA_REQUIRED

Latest-state u=1 boundary
=
PROOF_CANDIDATE_IDENTIFIED
FORMAL_ONE_SIDED_COROLLARY_REQUIRED

All-anchor / all-later simultaneous event
=
BLOCKED

Calibration
=
BLOCKED_BY_SIMULTANEOUS_EVENT

R5 method freeze
=
NOT AUTHORIZED

R5-D3 implementation
=
NOT AUTHORIZED
```

D2A의 핵심 결과는 blocker의 위치가 더 좁아졌다는 것이다.

D2에서 다음 여섯 항목이 동시에 막혀 있었다.

```text
BLOCKED_LATTICE_LOCAL_TRANSFER
BLOCKED_LOCAL_DEPENDENCE
BLOCKED_LOCAL_EDF_LIMIT
BLOCKED_BOUNDARY_INFERENCE
BLOCKED_SIMULTANEOUS_LOCAL_TIME
BLOCKED_CALIBRATION
```

D2A 검토 결과:

1. atomic/lattice local EDF는 직접 published corollary 적용은 불가능하지만 project-specific proof route가 존재한다.
2. latest-state `u=1`도 symmetric interior theorem을 그대로 쓸 수는 없으나 one-sided kernel을 general theorem에 넣는 proof route가 존재한다.
3. 그러나 StockScope common-N에 필요한 all-anchor/all-later `sup` event는 현재 확보한 이론으로 닫히지 않는다.
4. 따라서 calibration도 아직 freeze할 수 없다.

즉 현재 가장 근본적인 blocker는:

```text
BLOCKED_SIMULTANEOUS_LOCAL_TIME
```

이다.

---

## 2. 읽기 / 실행 경계

이번 D2A에서는 theorem research와 기존 설계 문서만 사용했다.

```text
DEV rerun = NO
sealed DEV numerical retuning = NO
Holdout = NOT ACCESSED
Reference Adequacy = NOT ACCESSED
forward envelope = NOT ACCESSED
passing N = NOT ACCESSED
minimum passing N = NOT ACCESSED
recommended support = NOT ACCESSED
DB/runtime = NOT ACCESSED
Production = NOT ACCESSED
fresh source data download = NO
bandwidth grid search = NO
breakpoint fitting = NO
```

R4C-E1 result는 parent history identity 외에 새 theorem parameter 선택 근거로 사용하지 않았다.

---

## 3. D2A-1 — Atomic / lattice local EDF

### 3.1 Direct published corollary는 여전히 적용 불가

Phandoidaen & Richter (2022), *Empirical process theory for nonsmooth functions under functional dependence*의 Corollary 2.6은 localized EDF에 가장 가까운 직접 결과다.

하지만 해당 corollary는:

- fixed `v∈(0,1)`;
- `x↦G(x,v)` Lipschitz;
- conditional distribution functions에 대한 Lipschitz 조건;
- compact supported Lipschitz kernel;
- functional-dependence decay;
- `nh→∞`, `h→0`

을 요구한다.

StockScope의 observed horizon features는 integer basis-point lattice이고 CDF는 jump를 갖는다.

따라서:

```text
Corollary 2.6
DIRECT_APPLICATION
=
REJECTED
```

이다.

### 3.2 하지만 atomic law 자체가 theorem impossibility를 뜻하지는 않는다

같은 논문의 일반 empirical-process theorem은 nonsmooth function class를 다루고 functional dependence를 사용한다.

R5에서 가능한 project-specific route는 proof-only distributional transform을 local stationary tangent process에 적용하는 것이다.

각 local time `u`에서 tangent marginal CDF `F_u`와 independent `V_i~Unif(0,1)`를 두고:

```text
U_i(u)
=
F_u(X_i(u)-)
+
V_i {F_u(X_i(u))-F_u(X_i(u)-)}
```

를 proof space에서만 정의한다.

그러면 tangent process marginal에서:

```text
U_i(u) ~ Uniform(0,1)
```

이고 lattice threshold `x`에 대해:

```text
1{X_i(u) <= x}
=
1{U_i(u) <= F_u(x)}
```

의 exact indicator identity를 얻는 것이 R4 D1과 동일한 핵심 아이디어다.

구현에서는:

```text
U
V
jitter
randomized rank
```

를 생성하지 않는다.

### 3.3 R5에서 새로 필요한 transfer

R4에서는 alpha-mixing이 measurable mapping 아래 증가하지 않는 성질을 사용했다.

R5는 functional/physical dependence를 사용할 예정이므로 같은 한 줄 argument를 복사할 수 없다.

필요한 새 lemma:

```text
R5_ATOMIC_LOCAL_TRANSFORM_LEMMA
```

최소 증명 항목:

1. time-varying `F_u`를 사용한 distributional transform identity;
2. local-time Hölder/Lipschitz variation이 transform에 전달되는 rate;
3. innovation coupling `X-X*`가 transformed `U-U*`에 주는 bound;
4. 1/5/10 finite-window joint process로의 dependence transfer;
5. general empirical-process theorem의 compatibility class 만족.

integer lattice에는 유용한 구조가 있다.

coupled lattice variables `X,X*`에 대해:

```text
X != X*
→
|X-X*| >= 1
```

이므로:

```text
P(X != X*)
<=
E |X-X*|^p
```

형태의 bound가 가능하다.

또 transform은 `X=X*`이면 같은 auxiliary `V`를 사용할 때 동일하다. 따라서 geometric/sufficiently fast physical-dependence contract 아래 transformed process dependence를 제어할 가능성이 있다.

그러나 이 coupling-to-transform inequality와 exact exponent/moment mapping은 reviewed source에 StockScope 형태로 존재하지 않는다.

따라서 현재 판정:

```text
D2A-1
=
PROOF_CANDIDATE_IDENTIFIED

NOT
=
FORMALLY_APPROVED
```

Reason code:

```text
PROJECT_ATOMIC_TRANSFORM_LEMMA_REQUIRED
```

---

## 4. D2A-2 — Latest-state u=1 boundary

### 4.1 Published EDF corollary의 경계

Phandoidaen & Richter Corollary 2.6은 명시적으로:

```text
v ∈ (0,1)
```

에 대해 stated되어 있다.

symmetric kernel support를 쓸 때 `0,1` 경계에서는 ordinary interior normalization이 깨진다.

따라서 기존 corollary를:

```text
v=1에도 당연히 적용
```

하는 것은 금지한다.

### 4.2 General theorem에서는 proof candidate가 보인다

같은 paper의 local empirical-process framework는 local case에서 localization center `v∈[0,1]`를 허용하는 구조를 갖는다.

따라서 R5-specific one-sided kernel:

```text
K_R(r)
support ⊂ [-1,0]
∫ K_R(r) dr = 1
```

를 사용해:

```text
Fhat_n(1,x)
=
1/(nh)
Σ K_R((i/n-1)/h) 1{X_i<=x}
```

형태를 만드는 route가 있다.

이 construction은 미래 `u>1` observation을 요구하지 않는다.

검토해야 할 formal points:

1. one-sided `D_{f,n}(u)`의 bounded variation;
2. `D^∞_{f,n}/sqrt(n)→0`;
3. local support condition;
4. covariance normalization `∫K_R^2`;
5. local approximation bias at the right boundary;
6. atomic transform lemma와의 결합.

이 항목들은 symmetric kernel interior proof와 유사하지만 동일하지 않다.

따라서:

```text
D2A-2
=
PROOF_CANDIDATE_IDENTIFIED
FORMAL_ONE_SIDED_COROLLARY_REQUIRED
```

로 둔다.

이전 D2의 `BLOCKED_BOUNDARY_INFERENCE`는 이제 “route 없음” blocker가 아니라 “formal project corollary 미완” blocker로 좁혀졌다.

새 reason code:

```text
ONE_SIDED_LOCAL_EDF_COROLLARY_REQUIRED
```

---

## 5. D2A-3 — All-anchor / all-later simultaneous event

이 부분은 이번 조사에서도 닫히지 않았다.

### 5.1 Fixed local time theorem은 충분하지 않다

StockScope common-N은:

```text
horizon h
× anchor s
× later v
× CDF threshold x
```

전체 selectable family가 하나의 simultaneous event 안에 들어가야 한다.

그러나 Corollary 2.6은 한 fixed `v`의 localized EDF process in `x`를 다룬다.

```text
functional CLT over x at one v
```

는:

```text
sup over all v
```

coverage를 의미하지 않는다.

### 5.2 2026 localized FCLT가 이 문제를 해결하는지 검토

Florian Heinrichs (2026),
*A Functional Central Limit Theorem for Localized Partial Sums of Non-Stationary Time Series*,
arXiv:2607.17697을 추가 검토했다.

이 논문은 중요한 진전이다.

- piecewise locally stationary processes;
- geometric physical-dependence decay;
- kernel-weighted localized partial sums;
- process-level weak convergence

를 다룬다.

하지만 limit space는:

```text
D'(0,1)
```

즉 test-function dual의 random distribution이다.

논문도 이 convergence가 ordinary sup-norm process convergence보다 약하다는 점을 명시한다.

또 pointwise Gaussian limit은:

```text
t ∈ (0,1)
```

interior에 한정되고, boundary contribution은 compactly supported test functions를 통해 제외된다.

Theorem 2/3는 `L²` projection 및 totally bounded subsets of `L²`에 대한 weak convergence를 제공한다.

하지만 local point evaluation / shrinking kernel centers 전체를 대상으로 하는:

```text
sup_{v∈[κ,1]}
|local estimation error(v)|
```

형태의 direct simultaneous confidence band를 제공하지 않는다.

논문 자체도 function family가 너무 크면 induced process의 tightness를 기대할 수 없다고 명시한다.

### 5.3 왜 shrinking local kernels가 핵심 문제인가

bandwidth `h_n→0`일 때 서로 다른 local centers에 대응하는 normalized kernel functions:

```text
K((.-v)/h_n)
```

는 increasingly localized된다.

즉 n이 증가함에 따라 index family 자체가 복잡해진다.

StockScope가 필요한 family는 단순한 fixed totally bounded class가 아니라:

```text
G_n
=
{
localized kernel centered at v:
v ranges over selectable times
}
```

처럼 n-dependent한 class다.

따라서 2026 paper의 fixed totally bounded `G⊂L²` result를 그대로 common-N sup band로 바꿀 수 없다.

### 5.4 Extreme-value SCB literature도 직접 연결되지 않는다

local autocorrelation 등 특정 smooth statistic에는 local-time simultaneous confidence band와 Gumbel/extreme-value calibration 문헌이 존재한다.

하지만 해당 proof는:

- statistic-specific linearization;
- smooth time-varying moments;
- variance estimation;
- bias reduction;
- interior interval `[b,1-b]`

등에 의존한다.

이를 StockScope의:

```text
atomic EDF threshold class
× 3 horizons
× local times
× boundary u=1
```

로 자동 확장할 수 없다.

### 판정

```text
D2A-3
=
BLOCKED_SIMULTANEOUS_LOCAL_TIME
```

이 blocker는 현재 D2A의 decisive blocker다.

---

## 6. D2A-4 — Calibration

Calibration은 stochastic target이 먼저 확정되어야 한다.

현재 L7 event가 닫히지 않았으므로:

- Gaussian critical value;
- multiplier bootstrap;
- dependent wild bootstrap;
- locally stationary bootstrap;
- extreme-value critical value

중 어느 것도 final engine으로 선택하지 않는다.

2026 localized FCLT는 Gaussian random distribution / isonormal process representation을 제공하지만 StockScope가 요구하는 sup-index event의 law는 제공하지 않는다.

따라서:

```text
D2A-4
=
BLOCKED_BY_D2A-3
```

Reason code:

```text
NO_VALID_CRITICAL_VALUE_FOR_REQUIRED_INDEX_FAMILY
```

---

## 7. D2A proof-state matrix

| Item | Before D2A | After D2A |
| --- | --- | --- |
| Atomic lattice EDF | BLOCKED | PROOF_CANDIDATE_IDENTIFIED / formal lemma required |
| Functional dependence transfer | BLOCKED | conditionally approachable if atomic transform lemma closes |
| Local EDF limit | BLOCKED | fixed-time route identified; atomic formalization still required |
| Latest-state u=1 | BLOCKED | one-sided proof candidate identified / formal corollary required |
| All-local-time simultaneous event | BLOCKED | BLOCKED / decisive |
| Calibration | BLOCKED | BLOCKED by simultaneous-event target |
| R4 D4 median/MAD projection | conditional | unchanged / still conditionally reusable |
| common-N | blocked | blocked |

---

## 8. What was NOT done

다음 편법을 사용하지 않았다.

```text
continuous latent data assumed
NO

jitter inserted
NO

ties removed
NO

u=1 dropped
NO

late observations deleted
NO

finite set of favorable anchors selected
NO

candidate grid reduced
NO

Bonferroni level invented
NO

DEV-informed bandwidth selected
NO

common-N semantics silently weakened
NO
```

특히 all-anchor theorem이 어렵다는 이유로 R2A candidate domain을 임의의 sparse anchor grid로 바꾸지 않았다.

그 변경은 별도의 architecture/governance decision이 필요하다.

---

## 9. New design consequence

현재 R5 local-distributional route를 그대로 유지하면서 다음으로 가려면 두 선택 중 하나가 필요하다.

### Option S — simultaneous theorem을 새로 해결

목표:

```text
uniform / high-dimensional approximation
for the n-dependent localized indicator class
```

필요:

- atomic transformed indicator class;
- one-sided boundary kernels;
- n-dependent localization-center index;
- threshold index;
- 3-horizon coupling;
- bias terms;
- critical-value approximation.

이 route는 mathematically clean하지만 추가 theorem work가 상당하다.

### Option A — common-N architecture를 prospectively 변경

예:

- fixed finite anchor fractions;
- predeclared finite anchor grid;
- non-sup integrated/local-risk target;
- separate monitoring architecture.

하지만 이건 D1/D2 target을 실질적으로 변경하므로 D2A가 자동 수행할 수 없다.

---

## 10. 다음 허용 작업

추천:

```text
NEXT-6E-S6A-R5-D2B
SIMULTANEOUS-INDEX ARCHITECTURE DECISION
```

D2B는 구현 작업이 아니다.

비교해야 할 후보:

1. **S1 — Full all-anchor theorem research continuation**
   - 현재 common-N 의미 완전 보존.
   - 가장 강한 수학 작업 필요.

2. **S2 — Prospectively fixed finite anchor grid**
   - candidate set을 사전 고정된 유한 family로 바꿈.
   - finite-dimensional joint inference 가능성 증가.
   - 기존 "smallest every-integer N" 의미 변경.

3. **S3 — Integrated local-drift uncertainty target**
   - pointwise sup 대신 weighted/integrated local drift.
   - Reference Adequacy metric 의미가 크게 달라짐.

4. **S4 — Separate estimation + prospective revocation monitor**
   - local reference estimation과 change monitoring 역할 분리.
   - common-N architecture 자체 수정 필요.

D2B 선택 기준은 DEV 결과가 아니라:

- product meaning preservation;
- statistical validity;
- lattice compatibility;
- latest-state support;
- common-N meaning;
- computation;
- auditability;
- governance impact

이어야 한다.

D2B가 S1을 선택한다면 theorem research를 계속한다.

S2-S4 중 하나를 선택한다면 새 method target/version으로 돌아가야 한다.

---

## 11. Literature register

### Primary core

1. Nathawut Phandoidaen, Stefan Richter (2022), *Empirical process theory for nonsmooth functions under functional dependence*, Electronic Journal of Statistics 16(1).  
   arXiv: https://arxiv.org/abs/2108.08512  
   DOI: https://doi.org/10.1214/22-EJS2023

Relevant:
- Definition 2.1 compatibility class
- Theorem 2.3
- Corollary 2.6
- Assumptions 3.1–3.4
- general locally stationary empirical-process framework

2. Florian Heinrichs (2026), *A Functional Central Limit Theorem for Localized Partial Sums of Non-Stationary Time Series*, arXiv:2607.17697.  
   https://arxiv.org/abs/2607.17697

Relevant:
- piecewise local stationarity;
- geometric physical dependence;
- localized process convergence in `D'(0,1)`;
- finite `L²` projections;
- weak convergence over totally bounded `L²` classes;
- explicit limitation of pointwise result to interior time due boundary effects.

### Supporting contrast

3. Zhou & Wu, local autocorrelation simultaneous confidence-band literature: demonstrates that local-time SCBs can exist for specific smooth statistics, but requires statistic-specific extreme-value theory and does not close atomic EDF.

4. Mayer, Zähle & Zhou (2020), local empirical process for non-stationary time series: direct local empirical-process result but density/conditional-density assumptions conflict with StockScope atoms.

---

## 12. Final state

```text
NEXT-6E-S6A-R5-D2A
=
BLOCKED_SIMULTANEOUS_LOCAL_TIME

D2A-1 atomic transform
=
PROMISING / FORMAL PROJECT LEMMA REQUIRED

D2A-2 boundary u=1
=
PROMISING / FORMAL ONE-SIDED COROLLARY REQUIRED

D2A-3 all-anchor/all-later
=
BLOCKED

D2A-4 calibration
=
BLOCKED

R5-D2
=
STILL BLOCKED_THEOREM_ROUTE_UNRESOLVED

R5 method
=
NOT FROZEN

Theorem-review template
=
NOT CREATED

Model-use template
=
NOT CREATED

R5-D3 implementation
=
NOT AUTHORIZED

DEV
=
NOT RERUN

Holdout
=
LOCKED / NOT ACCESSED

Reference Adequacy
=
NOT ACCESSED

DB/runtime
=
NOT ACCESSED

Production impact
=
NONE
```
