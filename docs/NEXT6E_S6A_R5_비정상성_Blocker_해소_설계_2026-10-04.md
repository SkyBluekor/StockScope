# StockScope NEXT-6E-S6A-R5 — 비정상성 Blocker 해소 설계

작성일: 2026-10-04, Asia/Seoul  
문서 성격: 정식 방법 설계. 구현·평가·승인 결과가 아니다.  
기준 main: 0c7f422ddb0eab4cab38b2563069288cd899838f  
Stage: NEXT-6E-S6A-R5-D1  
Parent method: NEXT6E_S6A_R4_LATTICE_CDF_PROJECTION_V1  
R4 design hash: 874c3387b54bdeff6701f1ca7b72469cfda158fb588a2b366c2d799754dc2a18

## 1. 결론

R5의 primary route는 다음으로 선택한다.

~~~text
Route B-LDR
LOCAL_DISTRIBUTIONAL_REFERENCE
~~~

핵심 결정은 한 개의 불변 분포 F를 전체 Development record에 강제하지 않는 것이다. R5는 aligned 3D feature process를 locally stationary triangular array로 모델링하고, horizon별 reference law 자체를 시간의 함수로 둔다.

~~~text
R4
F_h(x)

R5
F_h(u, x)
u = rescaled time
~~~

따라서 median과 raw MAD 역시 고정 상수가 아니라 local law의 함수가 된다.

~~~text
m_h(u)
d_h(u)
~~~

Reference Adequacy의 통계 대상도 바뀐다. R4처럼 서로 다른 prefix가 동일한 F_h에서 나온 표본이라는 가정 아래 sampling fluctuation만 설명하지 않는다. R5에서는 anchor time과 later time 사이의 실제 local-law drift를 추론 대상으로 삼는다.

Route A의 사전 고정 piecewise-stationary segmentation은 적절한 외생 breakpoint 근거가 현재 없다. Route C의 change/regime adaptive 방법은 StockScope 운영 의미에는 매력적이지만 estimated segment를 다시 reference inference에 사용하는 순간 post-selection 문제를 만든다. 현재 직접 적용 가능한 EDF monitoring 문헌도 연속 random vector 또는 stationary learning sample을 전제로 하므로 StockScope lattice process에 그대로 적용할 수 없다. Route D의 descriptive-only 축소는 현재 Reference Adequacy가 요구하는 통계적 uncertainty layer를 지나치게 약화한다.

R5-D1은 method route와 target을 설계 수준에서 선택한다. 실제 method approval은 아니다. R5-D2에서 lattice transfer, local-time simultaneous coverage, boundary treatment, dependence class와 bandwidth/bias contract가 닫히지 않으면 R5는 fail-closed로 유지한다. DEV 결과를 보고 Route C나 D로 자동 전환하지 않는다.

최종 상태:

~~~text
NEXT-6E-S6A-R5-D1 = COMPLETE

Primary route
= LOCAL_DISTRIBUTIONAL_REFERENCE

Nonstationary route
= SELECTED

Statistical target
= LOCAL_TIME_REFERENCE_LAW_DRIFT

Theorem family
= IDENTIFIED / APPLICATION PROOF REQUIRED

R4 migration
= COMPLETE AT DESIGN LEVEL

Scope rule
= OUTCOME-INDEPENDENT

Implementation
= NOT AUTHORIZED

R5 G-A
= BLOCKED_PENDING_R5_D2

Holdout
= LOCKED / NOT ACCESSED

Reference Adequacy
= UNRESOLVED

Production impact
= NONE
~~~

---

## 2. R4C-E2에서 확정된 문제

R4C Formal Phase A는 clean local checkout에서 성공했다.

고정 identity:

~~~text
baseline_main_sha
0c7f422ddb0eab4cab38b2563069288cd899838f

Phase A
CLEAN_DIAGNOSTIC_COMPLETE

diagnostic_hash
22da9cac3220594eb49bca06139827e2851f34d7724d7e5410725c8c212d62a5

source_scope_hash
90a0d42a15119f2667ed8401464edf06e1c566ea3134c6f0216116b2defa6700

payload_hash
b69359bb4656f3b53e43d84d748ad21468f5ff8128abb1892fbeefd363b10e96
~~~

Formal deterministic gates:

~~~text
G0
A0 A1 A2 A3 A4
A7 A8 A9 A10
=
PASS
~~~

failure_codes는 비어 있고 clean isolation은 인증되었다.

따라서 현재 blocker는 source corruption, lattice representation, zero sample MAD, clean execution 실패, method implementation failure가 아니다.

E2에서 D1-D4 theorem chain은 R4가 선언한 conditional / asymptotic / conservative simultaneous-coverage claim 범위에서는 승인되었다. 반면 A5와 A6 model-use는 현재 full Development scope에 대해 승인되지 않았다.

특히 R4의 10개 prospective chronological descriptive bins는 후반부에서 full-scope law와 상당한 위치·척도·CDF-shape 차이를 보였다. 이 값들은 새로운 cutoff를 만드는 수치가 아니며, strict stationarity를 full record에 working model로 승인하기 어렵다는 contradiction evidence로만 사용한다.

R5는 이 결과를 다음 용도로만 사용한다.

~~~text
ALLOWED
- R4 full-scope strict stationarity가 왜 막혔는지 설명
- nonstationary method family가 왜 필요한지 설명

FORBIDDEN
- 유리한 historical window 선택
- breakpoint 선택
- local bandwidth 선택
- drift threshold 선택
- passing N 선택
- policy tolerance 선택
~~~

---

## 3. 문제를 다시 정의한다

R4의 target은 하나의 stationary law F를 전제로 한 joint sequential sampling fluctuation이었다.

~~~text
Z_i = (X_i^1, X_i^5, X_i^10)
F = invariant joint law
~~~

R4의 reference movement는 같은 population law에서 나온 prefix 간 차이를 sampling fluctuation으로 설명하려는 구조였다.

R5는 이 population object를 교체한다.

표본 크기 n에 따라 triangular array를 두고:

~~~text
Z_i,n
=
(X_i,n^1, X_i,n^5, X_i,n^10)
~~~

각 rescaled time u in [0,1]에서 stationary approximation:

~~~text
Z_tilde_j(u)
~~~

이 존재한다고 가정하는 local-stationarity route를 연구한다.

horizon별 marginal local law:

~~~text
F_h(u, x)
=
P{ X_tilde_0^h(u) <= x }
~~~

이제 다음이 허용된다.

~~~text
F_h(u1, .) != F_h(u2, .)
m_h(u1)    != m_h(u2)
d_h(u1)    != d_h(u2)
~~~

즉 시장 feature distribution의 gradual evolution 자체를 model violation이 아니라 inference target에 넣는다.

이것이 R5의 핵심 변경이다.

---

## 4. 새 statistical target

R5 target ID 제안:

~~~text
NEXT6E_S6A_R5_LOCAL_TIME_REFERENCE_LAW_DRIFT_V1
~~~

human-readable target:

~~~text
LOCAL_TIME_REFERENCE_LAW_DRIFT
~~~

anchor:

~~~text
s = N / n
~~~

later time:

~~~text
v = t / n
s < v <= 1
~~~

각 horizon h in {1,5,10}에 대해 population local-law drift를 정의한다.

### 4.1 TAIL

~~~text
T_h(s,v)
=
sup_x | F_h(v,x) - F_h(s,x) |
~~~

R4의 empirical prefix-to-prefix sup distance와 다르다.

R5의 T_h는 두 local population CDF 사이의 이동이다.

### 4.2 Location

각 local law G에 대해 R4와 동일한 generalized median convention을 사용한다.

~~~text
q^-_G(1/2)
q^+_G(1/2)

M(G)
=
[q^-_G(1/2), q^+_G(1/2)]

m°(G)
=
midpoint of M(G)
~~~

따라서:

~~~text
m_h(u)
=
m°( F_h(u, .) )
~~~

그리고:

~~~text
L_h(s,v)
=
| m_h(v) - m_h(s) | / d_h(s)
~~~

### 4.3 Scale

local raw MAD:

~~~text
d_h(u)
=
raw MAD of F_h(u, .)
around m_h(u)
~~~

scale drift:

~~~text
S_h(s,v)
=
| d_h(v) - d_h(s) | / d_h(s)
~~~

d_h(s)=0 또는 uncertainty lower bound가 0을 포함해 denominator validity를 확정할 수 없으면 fail-close한다.

### 4.4 Nested reference envelope

향후 policy/evaluation layer가 요구할 population target은:

~~~text
E_h,q,N
=
sup over v > s
q_h(s,v)
~~~

이다.

단, R5-D1은 이것을 계산하지 않는다.

이 target은 "record가 stationary인가?"를 묻지 않는다.

대신:

> anchor local reference와 이후 local reference law가 얼마나 움직였는가?

를 묻는다.

이 target이 StockScope의 Reference Adequacy product purpose와 더 직접적으로 맞는다.

---

## 5. 문헌 조사와 적용 한계

이번 route 선택은 현재 DEV에서 통과하기 쉬운 방법을 찾은 결과가 아니다. 아래 문헌의 theorem object와 StockScope object를 비교한 결과다.

### 5.1 Dahlhaus local stationarity

Rainer Dahlhaus, Locally Stationary Processes, Handbook of Statistics 30, 2012.

DOI:
https://doi.org/10.1016/B978-0-444-53858-1.00013-2

핵심:

- global stationarity 대신 local stationary approximation을 사용한다.
- time-varying parameters / spectra / nonlinear locally stationary process를 다룬다.
- rescaled time u를 중심으로 local model을 정의한다.

StockScope 적용:

~~~text
SUPPORT
- 하나의 global invariant law를 버리는 이론적 방향
- time-varying process / local approximation architecture

NOT DIRECTLY SUPPORTED
- StockScope lattice EDF band
- midpoint median / raw MAD outer interval
- all-anchor/all-later simultaneous coverage
~~~

### 5.2 Birr et al. — local strict stationarity

Stefan Birr, Stanislav Volgushev, Tobias Kley, Holger Dette, Marc Hallin,
Quantile Spectral Analysis for Locally Stationary Time Series,
JRSS B 79(5), 2017, 1619-1643.

DOI:
https://doi.org/10.1111/rssb.12231

이 논문은 local strict stationarity를 joint distribution function 자체의 시간변화로 정의한다.

특히 marginal CDF가 rescaled time에 따라 변하는 구조를 허용한다.

이 점은 StockScope와 매우 중요하게 맞는다.

~~~text
F_t,T(.)
approximately
G^u(.)
~~~

StockScope에 주는 이점:

- covariance-only local stationarity보다 distributional change를 직접 다룬다.
- TAIL/quantile 중심 method와 개념적으로 가깝다.
- 특정 parametric DGP에 강제로 묶이지 않는 distribution-level local model을 제시한다.

한계:

- 논문의 주 inference object는 local copula spectrum이다.
- StockScope local EDF confidence band를 직접 제공하는 문헌은 아니다.
- 실제 theorem에는 mixing, smoothness, quantile 관련 regularity가 추가된다.
- R5가 필요한 discrete lattice median/MAD inference를 자동 승인하지 않는다.

따라서 이 논문은 R5 process definition 후보의 중요한 근거지만 완성된 StockScope theorem은 아니다.

### 5.3 Phandoidaen & Richter — locally stationary empirical process

Nathawut Phandoidaen, Stefan Richter,
Empirical process theory for locally stationary processes,
Bernoulli 28(1), 2022, 453-480.

DOI:
https://doi.org/10.3150/21-BEJ1351

핵심:

- functional dependence measure를 이용한 locally stationary empirical-process framework.
- functional CLT와 maximal inequality 제공.
- stationary mixing sequence보다 time-varying process를 직접 다룰 수 있다.

StockScope 적용:

~~~text
SUPPORT
- locally stationary process를 empirical-process 대상으로 놓는 framework
- dependence를 functional-dependence language로 기술할 후보

NOT DIRECTLY SUPPORTED
- R5 lattice local EDF band 전체
- median/MAD transfer
- all s,v family의 final simultaneous confidence construction
~~~

### 5.4 Phandoidaen & Richter — nonsmooth / localized EDF

Nathawut Phandoidaen, Stefan Richter,
Empirical process theory for nonsmooth functions under functional dependence,
Electronic Journal of Statistics 16(1), 2022.

DOI:
https://doi.org/10.1214/22-EJS2023

핵심:

- indicator 같은 nonsmooth function class를 다룬다.
- locally stationary process에 대해 localized empirical distribution function을 직접 연구한다.
- functional CLT를 제공한다.
- functional dependence measure를 사용한다.

특히 localized EDF라는 object가 R5와 가장 가깝다.

그러나 중요한 incompatibility가 있다.

해당 locally-stationary EDF corollary는 CDF에 Lipschitz regularity를 둔다. StockScope observed feature law는 integer basis-point lattice이며 atoms/ties가 존재한다.

따라서:

~~~text
PUBLISHED COROLLARY
!=
DIRECT R5 APPROVAL
~~~

R5-D2는 반드시 다음 중 하나를 증명해야 한다.

1. R4 D1과 같은 proof-only distributional transform을 local stationary approximation에 확장하여 lattice indicator process를 theorem class에 연결한다.
2. 또는 atoms를 직접 허용하는 다른 local empirical-process theorem을 확정한다.

이 gap을 무시하고 "논문에 local EDF가 있으니 PASS"라고 처리하는 것은 금지한다.

### 5.5 Kojadinovic & Verdier — sequential distribution change

Ivan Kojadinovic, Ghislain Verdier,
Nonparametric sequential change-point detection for multivariate time series based on empirical distribution functions,
Electronic Journal of Statistics 15(1), 2021, 773-829.

DOI:
https://doi.org/10.1214/21-EJS1798

이 논문은:

- multivariate empirical distribution function 차이 기반 sequential monitoring;
- dependent multiplier bootstrap;
- false-alarm probability control;
- financial-data application

을 제공한다.

Route C에 매우 적합해 보인다.

하지만 base framework의 learning sample은 stationary time series의 continuous random vectors를 전제로 한다.

StockScope에는:

- lattice atoms;
- 현재 full-history stationary model rejection;
- detected segment를 reference inference에 재사용할 때의 selection coupling

이 존재한다.

따라서 이번 R5 primary inference route로 채택하지 않는다.

향후 별도 prospective monitoring/revocation guard에는 다시 검토할 수 있다.

### 5.6 Zhao, Jiang & Shao — self-normalized segmentation

Zifeng Zhao, Feiyu Jiang, Xiaofeng Shao,
Segmenting Time Series via Self-Normalisation,
JRSS B 84(5), 2022, 1699-1725.

DOI:
https://doi.org/10.1111/rssb.12552

장점:

- piecewise stationary model.
- temporal dependence에 robust.
- mean, variance, correlation, quantile 등 broad functionals.
- long-run variance bandwidth 추정을 피하는 self-normalization.

한계:

- piecewise-constant structural model이 필요하다.
- nonlinear functional은 approximately-linear expansion을 요구한다.
- quantile verification은 smooth/bounded density regularity를 이용한다.
- StockScope lattice midpoint median / raw MAD 전체가 자동 포함되지 않는다.
- estimated break 이후 segment inference의 post-selection 문제를 별도로 닫아야 한다.

따라서 Route C 또는 A를 primary로 선택할 이유가 충분하지 않다.

---

## 6. Route A-D 비교와 결정

| Route | 핵심 idea | 장점 | 주요 blocker | 결정 |
| --- | --- | --- | --- | --- |
| A — Exogenous piecewise stationary | 사전 알려진 regime별 stationary law | R4 재사용 가능성이 높음 | 독립적인 breakpoint source 없음. 임의 날짜 또는 DEV-driven breakpoint 금지 | REJECT |
| B — Local stationarity | F_h(u,x)가 smooth하게 시간에 따라 변화 | segmentation 불필요, full record 사용 가능, actual drift가 target | lattice local-EDF theorem transfer, bandwidth/bias, boundary, simultaneous family | SELECT |
| C — Change/regime adaptive | distribution-change alarm 후 regime reset | 운영 반응성이 높고 시장 regime 의미와 직관적 | continuous/stationary learning assumptions, breakpoint selection, post-selection inference | NOT PRIMARY |
| D — Claim reduction | descriptive stability only | 강한 population assumptions 감소 | statistical uncertainty target 약화, S6A architecture 목적 축소 | REJECT |

### 결정

~~~text
PRIMARY
=
B / LOCAL_DISTRIBUTIONAL_REFERENCE

C
=
FUTURE OPERATIONAL REVOCATION-GUARD CANDIDATE ONLY

A
=
REJECTED

D
=
REJECTED
~~~

Route B가 쉬워서 선택된 것이 아니다.

오히려 theorem work는 많다.

선정 이유는 현재 StockScope problem object와 가장 정확히 일치하기 때문이다.

~~~text
observed problem
=
distribution evolves over time

selected inference object
=
time-varying local distribution
~~~

---

## 7. R5 process contract draft

제안 contract ID:

~~~text
NEXT6E_S6A_R5_LOCAL_DISTRIBUTIONAL_PROCESS_V1
~~~

process:

~~~text
Z_i,n
=
(X_i,n^1, X_i,n^5, X_i,n^10)
~~~

required local stationary approximation:

~~~text
for each u in [0,1]
there exists stationary
Z_tilde_j(u)
~~~

R5-D2가 정확한 approximation norm과 rate를 문헌 theorem에 맞춰 고정한다.

preferred dependence language:

~~~text
FUNCTIONAL_DEPENDENCE
OF STATIONARY APPROXIMATIONS
~~~

R4의:

~~~text
GLOBAL_STRICT_STATIONARITY
+
ALPHA_MIXING a>15/2
~~~

는 R5에서 자동 유지하지 않는다.

새 dependence class와 exact decay/moment assumptions는 R5-D2 theorem binding에서 확정한다.

중요:

~~~text
finite ACF
finite covariance decay
old ell=43
~~~

을 functional-dependence proof로 승격하지 않는다.

---

## 8. lattice / ties contract

R5에서도 다음은 그대로 유지한다.

~~~text
observed unit
=
BASIS_POINT

integer lattice
=
REAL DATA PROPERTY

ties
=
PRESERVE

jitter
=
FORBIDDEN

randomized empirical ranks
=
FORBIDDEN

latent continuous replacement of observed statistic
=
FORBIDDEN
~~~

R4 D1에서 사용한 distributional transform idea는 R5-D2의 proof candidate다.

그러나 R5에서는 local law가 u에 따라 달라지므로 다음을 새로 증명해야 한다.

~~~text
L1
For each local stationary approximation,
proof-only distributional transform preserves
the required indicator representation.

L2
The transform does not break
local-stationarity approximation rates.

L3
The chosen functional-dependence condition
is preserved or bounded after augmentation/mapping.

L4
Implementation still computes raw lattice indicators only.
~~~

이 네 연결 중 하나라도 닫히지 않으면 R5 theorem route는 BLOCKED다.

---

## 9. Local EDF estimator architecture

R5-D1은 estimator family만 고정한다.

generic localized empirical CDF:

~~~text
Fhat_h,n(x,u;b)
=
weighted empirical CDF
around rescaled time u
~~~

where:

~~~text
b
=
temporal localization bandwidth
~~~

필수 properties:

1. right-continuous CDF semantics.
2. raw lattice values preserved.
3. all ties preserved.
4. horizon 1/5/10 aligned chronology preserved.
5. common temporal localization rule across joint horizon process unless R5-D2 proves a different coupled rule.
6. no outcome-driven window selection.
7. no historical "stable region" search.
8. explicit boundary rule.
9. deterministic kernel/bandwidth identity.
10. bias and stochastic error kept separate.

이번 문서에서 kernel 또는 numeric bandwidth를 고르지 않는다.

왜냐하면:

- local inference에서 bandwidth는 theorem/bias/variance object다.
- 현재 DEV result로 고르면 새 leakage가 된다.
- conventional default도 StockScope requirement가 아니다.

R5-D2가 theorem-admissible family와 bias contract를 먼저 닫고, S6C가 실제 numerical profile을 버전 고정한다.

---

## 10. Boundary problem

R5의 product meaning상 u=1, 즉 latest state가 중요하다.

그러나 locally-stationary kernel theorem은 흔히 interior point를 가장 간단히 다룬다.

따라서 다음은 별도 blocker다.

~~~text
R5_BOUNDARY_LATEST_STATE
~~~

금지되는 편법:

- 마지막 b*n observations를 잘라 conventional sample CDF로 사용;
- observed data를 보고 window length 변경;
- last-point inference를 interior theorem이라고 표시;
- 마지막 구간을 삭제.

R5-D2가 다음 중 하나를 formal하게 선택해야 한다.

1. theorem-backed one-sided local estimator;
2. boundary-corrected kernel construction;
3. explicit latest-state exclusion with product consequence review.

StockScope 목적상 1 또는 2가 preferred다.

3을 선택하면 latest reference support를 직접 판단하지 못하므로 architecture compatibility를 다시 검토해야 한다.

---

## 11. Local median / MAD transfer

이 부분은 R4의 가장 재사용 가치가 높다.

R4 D4의 deterministic CDF-band inversion은 density derivative에 의존하지 않는 outer-bound construction이다.

따라서 R5에서는:

~~~text
R4 D4
=
RETAIN_CONDITIONALLY
~~~

조건:

> 각 local time u에서 F_h(u,.)에 대한 valid sup-norm band가 먼저 확보되어야 한다.

local band:

~~~text
L_h,u(x) <= F_h(u,x) <= U_h,u(x)
~~~

가 simultaneous event 안에서 유효하다면:

- generalized median set;
- midpoint median outer interval;
- estimated-center uncertainty를 포함한 raw MAD outer interval;
- zero / infinite endpoint fail-close semantics

을 local law별로 적용할 수 있다.

즉 R5는 discrete median/MAD를 다시 smooth influence-function route로 되돌리지 않는다.

이것은 중요한 design freeze다.

---

## 12. Local-law drift uncertainty

R5가 원하는 최종 inference는 단일 local CDF의 band 하나가 아니다.

anchor s와 later v의 차이를 동시에 다뤄야 한다.

예를 들어:

~~~text
T_h(s,v)
=
||F_h(v)-F_h(s)||_infinity
~~~

local CDF bands에서 deterministic outer bound를 만들 수 있다.

예:

~~~text
upper_T
<=
sup_x
max(
  |U_h,v(x)-L_h,s(x)|,
  |U_h,s(x)-L_h,v(x)|
)
~~~

정확한 sharp form은 R5-D2에서 고정한다.

median/MAD drift 역시 두 local functional interval의 interval-distance outer bound로 전달할 수 있다.

핵심은:

~~~text
local CDF simultaneous event
→ local median/MAD intervals
→ anchor-vs-later drift outer bounds
~~~

의 deterministic chain이다.

R5-D2가 stochastic theorem은 CDF level에서 최대한 닫고, nonlinear median/MAD는 deterministic projection으로 유지하는 것이 preferred다.

---

## 13. Simultaneous family와 common-N

R4의 common-N product meaning은 유지할 가치가 있다.

하지만 statistical event는 바뀐다.

R5 desired index:

~~~text
horizon h
× anchor s
× later v
× local-CDF threshold x
~~~

후속 deterministic map:

~~~text
TAIL
LOCATION
SCALE
~~~

하나의 valid simultaneous event가 전체 selectable family를 덮는다면:

~~~text
N*
=
minimum candidate N
satisfying all approved policy conditions
~~~

이라는 post-selection structure를 다시 사용할 수 있다.

그러나 현재 literature review만으로 이 all-s/all-v event가 승인됐다고 주장하지 않는다.

따라서:

~~~text
COMMON_N_SEMANTICS
=
RETAIN

COMMON_N_THEOREM_SUPPORT
=
R5_D2_REQUIRED
~~~

이다.

---

## 14. CandidateDomainContract migration

R2A의 frozen κ=1/10은 Development result와 무관한 prospective method-governance decision이었다.

따라서 이번 blocker 때문에 κ를 다시 고르지 않는다.

decision:

~~~text
R2A κ = 1/10
=
RETAIN_WITH_REINTERPRETATION
~~~

R5에서 의미:

~~~text
anchor time s=N/n
must satisfy
s >= 1/10
~~~

이 rule은 local bandwidth validity를 자동 보장하지 않는다.

따라서 eligibility는:

~~~text
R5_ELIGIBLE(N)
=
R2A_FRACTION_DOMAIN_ELIGIBLE
AND
LOCAL_ESTIMATOR_BOUNDARY_VALID
AND
JOINT_FEATURE_AVAILABLE
AND
FUNCTIONAL_COMPUTABLE
AND
R5_METHOD_CONTRACT_APPLICABLE
~~~

이다.

금지:

~~~text
bandwidth가 불편함
→ κ 수정

DEV late drift가 큼
→ κ 수정

passing N가 없음
→ κ 수정
~~~

κ를 바꾸려면 새로운 CandidateDomainContract version이 필요하다.

---

## 15. R4 → R5 migration map

| R4 element | R5 action | Rationale |
| --- | --- | --- |
| aligned Z=(X1,X5,X10) | RETAIN | joint horizon dependence 보존 |
| native chronology | RETAIN | local-time index의 핵심 |
| integer bp lattice | RETAIN | observed law identity |
| ties | RETAIN | 실제 분포 특성 |
| right-continuous ECDF | RETAIN | CDF semantics |
| midpoint median | RETAIN | 기존 observed statistic identity |
| raw MAD | RETAIN | 기존 scale identity |
| generalized median-set interval | RETAIN | discrete-law outer inference |
| center-aware MAD outer interval | RETAIN | density-free deterministic transfer |
| zero-scale fail-close | RETAIN | denominator safety |
| CandidateDomain κ=1/10 | RETAIN / REINTERPRET | anchor-time lower domain |
| global strict stationarity | REPLACE | blocker의 직접 원인 |
| one invariant F_h | REPLACE | F_h(u,.) |
| α-mixing a>15/2 exact R4 class | REPLACE | local functional-dependence theorem class 연구 |
| R4 span-envelope multiplier | REPLACE / NOT ASSUMED | local empirical-process calibration 새로 필요 |
| R4 full-sample empirical centering | REPLACE | local centering target 필요 |
| R4 D1 global lattice transform | MODIFY | local transform proof 필요 |
| R4 D2 calibration dominance | REMOVE FROM R5 PRIMARY | 다른 stochastic engine |
| R4 D3 stationary simultaneous DF band | REPLACE | local-time band |
| R4 D4 median/MAD projection | RETAIN CONDITIONALLY | local CDF band 이후 사용 |
| common-N semantics | RETAIN | downstream decision rule |
| all-N simultaneous theorem | REPLACE | local-time all-anchor/all-later theorem 필요 |
| G0 isolation | RETAIN | source governance |
| G1 theorem review | REPLACE VERSION | R5 proof units로 새 review |
| A0-A3 lineage/alignment | RETAIN | source structure |
| A4 lattice compatibility | MODIFY | local lattice theorem |
| A5 strict stationarity | REPLACE | LOCAL_STATIONARITY_MODEL_USE |
| A6 mixing | REPLACE | LOCAL_DEPENDENCE_MODEL_USE |
| A7/A9 density replacement | RETAIN R4 RESOLUTION | 다시 density derivative로 회귀 금지 |
| A8 sample scale computability | RETAIN |
| A10 calibration profile | REPLACE | local numerical contract |

R4 historical gate states를 R5 PASS로 복사하지 않는다.

---

## 16. R5 theorem proof units 제안

R5-D2는 최소 다음 proof units를 닫아야 한다.

### L1 — Local process definition / approximation

증명/검토 대상:

~~~text
Z_i,n
is approximable by
Z_tilde_i(u)
under exact declared local-stationarity contract
~~~

필요:

- joint 3D horizon process;
- chronology;
- time smoothness;
- source/feature transformation과 approximation compatibility.

### L2 — Lattice local-EDF transfer

목표:

> StockScope의 atomic CDF를 direct Lipschitz-CDF theorem에 억지로 넣지 않고, raw lattice statistic을 유지하면서 local empirical-process theorem에 연결한다.

R4 distributional-transform proof를 local setting으로 확장할 수 있는지 검토한다.

### L3 — Dependence contract

정확한:

- functional-dependence coefficient;
- moment class;
- decay rate;
- stationary approximation dependence;
- joint 3D transfer

를 문헌 theorem에 맞춰 고정한다.

finite covariance diagnostics를 proof로 사용하지 않는다.

### L4 — Local EDF stochastic limit

localized EDF가 exact local F_h(u,.)를 대상으로 어떤 normalization과 bias term을 갖는지 고정한다.

필요:

~~~text
stochastic error
+
localization bias
~~~

분리.

### L5 — Lattice median/MAD deterministic projection

R4 D4가 local CDF band에 pointwise-in-u 및 simultaneous family에서 정확히 승계되는지 검토한다.

### L6 — Boundary latest-state inference

u near 0 / 1, 특히 u=1의 one-sided/boundary inference를 닫는다.

### L7 — All-anchor/all-later simultaneous event

common-N post-selection을 보호할 수 있는 joint event를 확정한다.

이게 불가능하면 common-N architecture를 다시 설계해야 한다.

### L8 — Calibration / bootstrap / Gaussian approximation

local empirical process의 critical value construction을 고정한다.

R4 multiplier profile을 자동 재사용하지 않는다.

---

## 17. Bandwidth와 bias governance

R5에서는 bandwidth가 method-design parameter다.

~~~text
bandwidth
!=
product tolerance

bandwidth
!=
passing-N knob

bandwidth
!=
risk appetite
~~~

R5-D1 decision:

~~~text
NUMERIC BANDWIDTH
=
UNRESOLVED

BANDWIDTH SOURCE
=
R5_D2 THEOREM + LATER NUMERICAL CONTRACT

DEV OUTCOME TUNING
=
FORBIDDEN
~~~

R5-D2는 최소 다음을 정한다.

- kernel support / regularity;
- bandwidth asymptotic rate;
- shared-vs-horizon-specific rule;
- undersmoothing 또는 explicit bias correction;
- boundary bandwidth behavior;
- automatic selector 허용 여부;
- selector가 inference theorem에 포함되는지;
- numerical precision owner.

DEV에서 가장 잘 맞는 bandwidth를 grid-search해 선택하는 것은 금지한다.

---

## 18. Route C의 위치

Change-point detection은 버리지 않는다.

다만 역할을 분리한다.

~~~text
R5 primary inference
=
LOCAL DISTRIBUTIONAL REFERENCE

future optional guard
=
REGIME CHANGE REVOCATION MONITOR
~~~

그 guard가 들어가더라도:

- R5 inference theorem을 대신하지 않는다.
- no alarm을 local-stationarity proof로 사용하지 않는다.
- alarm 뒤 데이터를 같은 inference artifact에 post-hoc 재사용하지 않는다.
- change threshold를 current DEV passing result로 정하지 않는다.
- guard의 false-alarm budget은 별도 statistical ledger다.

즉 Route C는 "R5가 실패하면 몰래 사용하는 fallback"이 아니다.

별도 versioned feature다.

---

## 19. Risk-budget interface 영향

S6B의 핵심 separation은 유지한다.

~~~text
statistical uncertainty
!=
operational acceptable movement
~~~

R5는 오히려 이 구분을 더 명확하게 만든다.

R5 statistical producer:

~~~text
confidence / upper bound
for local-law drift
~~~

Risk policy:

~~~text
τ_T
τ_L
τ_S
~~~

는 그 drift 중 어느 정도까지 reference reuse에 허용되는지 별도로 정한다.

따라서 τ 값들은 이번 문서에서 선택하지 않는다.

R5 때문에 α_stat의 event identity는 변경된다.

R4 event:

~~~text
stationary sampling fluctuation
~~~

R5 event:

~~~text
simultaneous local-law estimation / drift coverage
~~~

따라서 과거 α_stat proposal이 존재하더라도 exact target compatibility review가 필요하다.

현재 값은 계속 null이다.

---

## 20. R5 model-use acceptance contract

R4의 A5/A6를 그대로 재승인하지 않는다.

### R5-A5 — Local stationarity model use

질문:

> full Development scope가 하나의 invariant law인가?

가 아니다.

새 질문:

> declared local-stationarity approximation과 time-smoothness class를 이 source/feature process의 working model로 사용할 수 있는가?

필수 dossier:

- exact process/scope identity;
- local approximation meaning;
- allowed type of time variation;
- smoothness assumption;
- abrupt-break limitation;
- source-definition change handling;
- contradictions and dispositions;
- revocation rule.

finite local diagnostics는 informational이다.

### R5-A6 — Local dependence model use

필수:

- exact functional-dependence class;
- decay/moment assumptions;
- joint horizon overlap interpretation;
- long-memory limitation;
- theorem-specific root/bias conditions;
- contradiction disposition.

이번에도 finite ACF가 assumption proof가 아니다.

---

## 21. Fail-closed semantics

다음 중 하나면 R5 method approval은 BLOCKED다.

| Condition | State |
| --- | --- |
| lattice local-EDF transfer 미증명 | BLOCKED_LATTICE_LOCAL_TRANSFER |
| local dependence theorem binding 미완 | BLOCKED_LOCAL_DEPENDENCE |
| boundary u=1 미해결 | BLOCKED_BOUNDARY_INFERENCE |
| localization bias control 미해결 | BLOCKED_LOCAL_BIAS |
| bandwidth selector theorem 밖 | BLOCKED_BANDWIDTH_SELECTION |
| all-anchor/all-later coverage 미해결 | BLOCKED_SIMULTANEOUS_LOCAL_TIME |
| local median/MAD projection 오류 | BLOCKED_FUNCTIONAL_TRANSFER |
| sample scale zero | NON_COMPUTABLE_ZERO_SCALE |
| model-use approval 부재 | BLOCKED_MODEL_USE |
| theorem review 부재 | BLOCKED_THEOREM_REVIEW |
| forbidden source 노출 | ISOLATION_NOT_CERTIFIED |
| numerical profile 미완 | BLOCKED_NUMERICAL_PROFILE |

하나의 blocker가 난 뒤:

- window를 줄여 재시도;
- bandwidth를 바꿔 재시도;
- late period 삭제;
- change-point route 자동 전환;
- claim을 descriptive로 몰래 축소

하지 않는다.

새 version과 명시적 authorization이 필요하다.

---

## 22. Data / isolation policy

R5-D1에서 허용된 Development use:

~~~text
sealed R4C E1 diagnostic
as problem evidence only
~~~

실제 raw DEV 재실행:

~~~text
NO
~~~

금지:

~~~text
Holdout
Reference Adequacy output
forward envelope
passing candidate
minimum passing N
recommended support
runtime DB
Production outcome
replacement DEV
fresh download
historical stable-window search
breakpoint fitting
bandwidth tuning
~~~

R5-D2도 theorem research 단계에서는 같은 금지 원칙을 유지한다.

DEV를 다시 실행하는 것은 R5 method/parameter contract가 frozen된 이후 별도 clean diagnostic stage에서만 허용한다.

---

## 23. Implementation architecture proposal

R5-D1에서는 코드 구현하지 않는다.

후속 구현 시 권장 layer:

~~~text
backend/app/macro/r5_contract.py
backend/app/macro/r5_local_process.py
backend/app/macro/r5_local_cdf.py
backend/app/macro/r5_projection.py
backend/app/macro/r5_gate.py
~~~

이는 path proposal일 뿐 현재 생성 지시가 아니다.

핵심 separation:

~~~text
source reconstruction
→ local process diagnostic
→ localized CDF engine
→ simultaneous uncertainty object
→ deterministic median/MAD projection
→ local-law drift bounds
→ gate assessment
~~~

policy tolerance와 common-N evaluation은 method approval 뒤 downstream layer다.

---

## 24. 다음 단계

### R5-D2 — Method Contract / Theorem Resolution

해야 할 일:

1. L1-L8 proof units formal resolution.
2. exact theorem sources / theorem numbers.
3. local stationarity definition freeze.
4. functional dependence class freeze.
5. lattice transfer proof.
6. boundary inference.
7. local EDF normalization/bias.
8. bandwidth/kernel symbolic contract.
9. simultaneous index family.
10. R5 GateAssessment schema.
11. theorem-review template.
12. model-use dossier template.

완료 condition:

~~~text
R5 METHOD CONTRACT
=
FROZEN

R5 G1 theorem review packet
=
READY

R5 A5/A6 model-use packet
=
READY

Implementation
=
AUTHORIZED ONLY BY SEPARATE USER COMMAND
~~~

### R5-D3 — Implementation

D2 승인 이후에만.

### R5-D4 — Formal Clean DEV Diagnostic

frozen R5 contract만 사용.

DEV result를 보고 method parameter를 변경하면 새 version으로 돌아간다.

### 이후

~~~text
R5 theorem review
+
R5 model-use approval
+
formal clean diagnostic
↓
R5 G-A
~~~

R5 G-A가 PASS하기 전:

~~~text
G-B convergence
V4
Reference Adequacy evaluation
Holdout
Production
~~~

은 계속 차단한다.

---

## 25. R5-D1 completion checklist

~~~text
R4C-E2 blocker recorded
PASS

Nonstationary route compared
PASS

Primary route selected
PASS

Route selected independent of passing-N outcome
PASS

Statistical target frozen at design level
PASS

Time-varying law semantics defined
PASS

TAIL / location / scale target mapping defined
PASS

Lattice preservation rule defined
PASS

Median/MAD reuse boundary defined
PASS

R4 migration map complete
PASS

Candidate κ handling defined
PASS

Parameter-selection ownership defined
PASS

Fail-closed behavior defined
PASS

Theorem family identified
PASS

Direct theorem gaps explicitly recorded
PASS

Implementation performed
NO

DEV rerun
NO

Holdout accessed
NO

Reference Adequacy accessed
NO

DB/runtime accessed
NO

Production impact
NONE
~~~

---

## 26. Source register

### Project sources

1. docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md
2. docs/StockScope_NEXT6E_S6A_R1_SEQUENTIAL_FUNCTIONAL_THEOREM_RESOLUTION_2026-10-02.md
3. docs/StockScope_NEXT6E_S6A_R2A_CANDIDATE_DOMAIN_GOVERNANCE_DECISION_2026-10-02.md
4. docs/StockScope_NEXT6E_S6A_R3_방법론_Blocker_해소_설계_2026-10-03.md
5. docs/StockScope_NEXT6E_S6A_R4B_GA_승인패키지_2026-10-03.md
6. backend/app/macro/r4_contract.py
7. backend/app/macro/r4_diagnostic.py
8. backend/app/macro/r4_lattice.py
9. backend/app/macro/r4_gate.py
10. R4C Formal Phase A sealed evidence identified by:
    - diagnostic 22da9cac3220594eb49bca06139827e2851f34d7724d7e5410725c8c212d62a5
    - source scope 90a0d42a15119f2667ed8401464edf06e1c566ea3134c6f0216116b2defa6700
    - payload b69359bb4656f3b53e43d84d748ad21468f5ff8128abb1892fbeefd363b10e96

### Primary / peer-reviewed literature

1. Dahlhaus, R. (2012). Locally Stationary Processes. Handbook of Statistics, 30, 351-413.  
   https://doi.org/10.1016/B978-0-444-53858-1.00013-2

2. Birr, S., Volgushev, S., Kley, T., Dette, H., Hallin, M. (2017). Quantile Spectral Analysis for Locally Stationary Time Series. Journal of the Royal Statistical Society Series B, 79(5), 1619-1643.  
   https://doi.org/10.1111/rssb.12231

3. Phandoidaen, N., Richter, S. (2022). Empirical process theory for locally stationary processes. Bernoulli, 28(1), 453-480.  
   https://doi.org/10.3150/21-BEJ1351

4. Phandoidaen, N., Richter, S. (2022). Empirical process theory for nonsmooth functions under functional dependence. Electronic Journal of Statistics, 16(1).  
   https://doi.org/10.1214/22-EJS2023

5. Kojadinovic, I., Verdier, G. (2021). Nonparametric sequential change-point detection for multivariate time series based on empirical distribution functions. Electronic Journal of Statistics, 15(1), 773-829.  
   https://doi.org/10.1214/21-EJS1798

6. Zhao, Z., Jiang, F., Shao, X. (2022). Segmenting Time Series via Self-Normalisation. Journal of the Royal Statistical Society Series B, 84(5), 1699-1725.  
   https://doi.org/10.1111/rssb.12552

7. Kreiss, J.-P., Paparoditis, E. (2015). Bootstrapping Locally Stationary Processes. Journal of the Royal Statistical Society Series B, 77(1), 267-290.  
   https://doi.org/10.1111/rssb.12068

### Applicability warning

위 논문 어느 것도 StockScope R5 전체 procedure를 그대로 제공하지 않는다.

문헌은 다음 component를 지원한다.

~~~text
local stationarity concepts
local distributional time variation
locally stationary empirical-process theory
localized EDF theory
nonstationary bootstrap families
distribution-change monitoring alternatives
piecewise-stationary segmentation alternatives
~~~

StockScope-specific theorem chain:

~~~text
3D horizon lattice process
→ local stationary approximation
→ atomic local EDF inference
→ boundary-aware simultaneous local bands
→ density-free median/MAD projection
→ anchor-vs-later local-law drift
→ all-anchor common-N selection
~~~

은 R5-D2에서 별도 resolution이 필요하다.

---

## 27. Final state

~~~text
NEXT-6E-S6A-R5-D1
=
COMPLETE

Parent R4C-E2
=
BLOCKED_MODEL_USE_NOT_ACCEPTED

Selected route
=
LOCAL_DISTRIBUTIONAL_REFERENCE

Process class
=
LOCALLY_STATIONARY JOINT 3D HORIZON PROCESS
EXACT CONTRACT PENDING R5-D2

Target
=
LOCAL_TIME_REFERENCE_LAW_DRIFT

Lattice / ties
=
PRESERVED

R4 median/MAD outer projection
=
RETAIN_CONDITIONALLY

R2A κ=1/10
=
RETAIN_WITH_REINTERPRETATION

Global strict stationarity
=
REPLACED

R4 alpha-mixing class
=
REPLACED / R5 DEPENDENCE CONTRACT REQUIRED

R4 calibration
=
REPLACED

R5 theorem family
=
IDENTIFIED

R5 theorem applicability
=
NOT YET APPROVED

R5 G-A
=
BLOCKED_PENDING_R5_D2

Reference Adequacy
=
UNRESOLVED

Implementation
=
NOT STARTED

Holdout
=
LOCKED / NOT ACCESSED

Reference Adequacy outputs
=
NOT ACCESSED

Runtime DB
=
NOT ACCESSED

Production impact
=
NONE
~~~
