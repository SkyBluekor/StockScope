# StockScope NEXT-6E-S6A-R5-D2D1 — Local-Weighted Atomic Max-Inference Resolution

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 theorem-rate resolution 결과. 구현/평가 문서가 아니다.  
기준 main: 0f8517f01da65b420be36a7a9881e71510ca63d0  
Parent: NEXT-6E-S6A-R5-D2D  
CandidateDomain V2 semantic SHA256: e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09

## 1. 최종 판정

~~~text
NEXT-6E-S6A-R5-D2D1
=
BLOCKED_W2_CALIBRATION_RATE_UNRESOLVED

W1
=
REJECTED_EMPTY_RATE_INTERVAL

W2
=
GAUSSIAN_RATE_FEASIBLE
CDF_PROJECTION_RESOLVED
CALIBRATION_NOT_FROZEN

R5 local-distributional route
=
STILL ALIVE

Architecture reconsideration
=
NOT YET REQUIRED

R5 method
=
NOT FROZEN

R5-D2E
=
NOT AUTHORIZED

R5-D3 implementation
=
NOT AUTHORIZED
~~~

이번 단계의 핵심 진전은 두 가지다.

1. W1은 theorem-rate 수준에서 배제됐다.
2. W2는 local Gaussian root와 CDF-shape correction까지는 non-empty rate class를 갖는다.

남은 blocker는 W2의 data-dependent critical value를 만드는 calibration / long-run covariance approximation rate다.

## 2. 작업 경계

~~~text
DEV raw data = NOT ACCESSED
DEV rerun = NO
sealed diagnostic used for tuning = NO
Reference Adequacy = NOT ACCESSED
passing anchor = NOT ACCESSED
forward envelope = NOT ACCESSED
Holdout = LOCKED / NOT ACCESSED
DB/runtime = NOT ACCESSED
Production = NOT ACCESSED
backend/tests/frontend = UNCHANGED
~~~

CandidateDomain V2도 변경하지 않았다.

## 3. Core theorem engine

Primary rate engine:

Jinyuan Chang, Xiaohui Chen, Mingcong Wu,
Central limit theorems for high dimensional dependent data,
Bernoulli 30(1), 2024, 712–742.
DOI: https://doi.org/10.3150/23-BEJ1614

사용한 published facts:

- physical-dependence model의 time-varying map f_t는 nonstationary arrays를 허용한다.
- Theorem 3은 physical dependence 아래 high-dimensional maxima의 Gaussian approximation rate를 제공한다.
- weak-dependence regime에서는 Theorem 3(ii)가 relevant branch다.
- Condition 3은 coordinate-wise non-degeneracy를 요구한다.
- Theorem 10은 bootstrap error를 Gaussian approximation error와 covariance-estimation error에 연결한다.
- Theorem 11은 kernel long-run covariance estimator의 physical-dependence bound를 제공한다.

이 theorem은 StockScope procedure를 직접 제공하지 않는다. 아래는 R5 weighted indicator vector에 대한 project-specific mapping이다.

## 4. Local weighted vector representation

local time u, horizon h, lattice threshold x에 대해 centered weighted coordinate를:

~~~text
Y_i(u,h,x)
=
b_n^(-1/2)
K_-((i/n-u)/b_n)
[
  1{X_i^h <= x}
  -
  E 1{X_i^h <= x}
]
~~~

로 둔다.

그러면:

~~~text
1/sqrt(n) sum_i Y_i(u,h,x)
~~~

는:

~~~text
sqrt(n b_n)
[
  Fhat_h,n(u,x)
  -
  E Fhat_h,n(u,x)
]
~~~

의 stochastic part다.

simultaneous vector coordinate index는:

~~~text
anchor
× later chronology state
× horizon
× threshold
~~~

이다.

## 5. Local-weight norm inflation

bounded kernel과 bounded indicator 때문에:

~~~text
|Y_i|
<=
C b_n^(-1/2)
~~~

따라서 corresponding sub-exponential / physical-dependence norms는:

~~~text
B_n = O(b_n^(-1/2))
Phi_{psi,nu,alpha} = O(b_n^(-1/2))
Psi_{2,alpha} = O(b_n^(-1/2))
~~~

scale을 갖는다.

bandwidth를:

~~~text
b_n = n^(-beta)
~~~

로 두면:

~~~text
b_n^(-1/2) = n^(beta/2)
~~~

이다.

이 inflation을 무시하면 high-dimensional rate를 잘못 판단하게 된다.

## 6. Gaussian approximation upper rate

Chang–Chen–Wu Theorem 3(ii)에 위 scaling을 대입하면, logarithmic factors를 제외한 principal terms는:

~~~text
TERM 1
~
b_n^(-1/2)
n^(-alpha/(12+6 alpha))

TERM 2
~
b_n^(-1/3)
n^(-alpha/(12+6 alpha))

TERM 3
~
b_n^(-1/2)
n^(-alpha/(4+2 alpha))
~~~

이다.

가장 강한 upper bound는 TERM 1에서 나온다.

~~~text
beta/2
<
alpha/(12+6 alpha)
~~~

즉:

~~~text
beta
<
alpha/(6+3 alpha)
~~~

Define:

~~~text
U(alpha)
=
alpha/(6+3 alpha)
~~~

모든 finite alpha>0에 대해:

~~~text
U(alpha) < 1/3
~~~

이며 alpha→infinity에서 1/3으로 접근한다.

## 7. W1 — positive one-sided local constant

first-order time bias:

~~~text
Bias = O(b_n)
~~~

local stochastic scale에서 bias negligibility는:

~~~text
sqrt(n b_n) b_n -> 0
~~~

즉:

~~~text
beta > 1/3
~~~

을 요구한다.

Gaussian rate는:

~~~text
beta < U(alpha) < 1/3
~~~

이므로 두 조건의 교집합은 모든 finite alpha에서 비어 있다.

### W1 verdict

~~~text
W1
=
REJECTED_EMPTY_RATE_INTERVAL
~~~

Reason:

~~~text
FIRST_ORDER_BIAS_VS_HIGH_DIMENSIONAL_GAUSSIAN_RATE_CONFLICT
~~~

이 판정은 DEV 결과와 무관하다.

## 8. W2 — second-order signed one-sided kernel

candidate witness kernel:

~~~text
K_-(r)
=
4 + 6r

for -1 <= r <= 0
and 0 otherwise
~~~

이 kernel은:

~~~text
integral K_-(r) dr = 1
integral r K_-(r) dr = 0
~~~

을 만족한다.

이 exact polynomial을 theorem-optimal이라고 주장하지 않는다. one-sided second-order kernel existence를 보여주는 simple witness다.

## 9. W2 time smoothness and bias

required symbolic regularity:

~~~text
for every horizon h and lattice threshold x,
u -> F_h(u,x)
admits a uniformly controlled second-order
left/time Taylor remainder
on the approved local-time domain
~~~

그러면:

~~~text
Bias = O(b_n^2)
~~~

이고:

~~~text
sqrt(n b_n) b_n^2 -> 0
~~~

는:

~~~text
beta > 1/5
~~~

을 요구한다.

## 10. W2 Gaussian rate interval

combine:

~~~text
beta > 1/5
~~~

and:

~~~text
beta < alpha/(6+3 alpha)
~~~

non-empty iff:

~~~text
alpha > 3
~~~

이다.

따라서 symbolic W2 interval:

~~~text
1/5
<
beta
<
alpha/(6+3 alpha)
~~~

가 존재한다.

theorem witness:

~~~text
alpha = 4
→
1/5 < beta < 2/9
~~~

이 예시는 numeric beta freeze가 아니다.

### W2 Gaussian-rate verdict

~~~text
PASS
~~~

subject to the declared model assumptions.

## 11. Dependence interpretation

D2D에서 preferred class는 uniform geometric physical dependence였다.

geometric decay이면 polynomial dependence-adjusted norm은 모든 fixed alpha에서 finite할 수 있으므로:

~~~text
alpha > 3
~~~

의 theorem requirement와 양립 가능하다.

이것은 actual Development process에 대한 empirical proof가 아니다.

## 12. Non-degeneracy requirement

Chang–Chen–Wu Condition 3은 included coordinate root의 variance가 uniformly bounded away from zero이기를 요구한다.

따라서 R5 method contract에는:

~~~text
UNIFORM_LOCAL_ROOT_NONDEGENERACY
~~~

가 필요하다.

far-tail indicator처럼 거의 deterministic coordinate를 무조건 Gaussian family에 포함할 수 없다.

## 13. Deterministic lattice threshold truncation

deterministic threshold radius:

~~~text
M_n = ceil(n^mu)
~~~

threshold family:

~~~text
T_n
=
{x in Z:
 -M_n <= x <= M_n}
~~~

로 둔다.

이 rule은 observed DEV range와 무관하다.

uniform q-moment:

~~~text
sup_{u,h} E|X_h(u)|^q <= C_q
~~~

가 있으면:

~~~text
sup_{u,h}
P(|X_h(u)| > M_n)
<=
C_q M_n^(-q)
~~~

이다.

tail term을 local stochastic width보다 작게 만들기 위한 sufficient symbolic condition:

~~~text
mu q
>
(1-beta)/2
~~~

이다.

## 14. Dimension-growth bound

conservative nominal dimension:

~~~text
p_n
<=
18
*
n
*
3
*
(2 M_n + 1)
~~~

따라서:

~~~text
p_n
=
O(n^(1+mu))
~~~

이고:

~~~text
log p_n
=
O(log n)
~~~

이다.

즉 threshold/later dimension이 polynomial growth로 유지되면 Theorem 3의 logarithmic dimension factors 자체는 W2 Gaussian-rate feasibility를 깨지 않는다.

## 15. W2 raw estimator is not a CDF

signed weights 때문에 raw estimator는 반드시:

~~~text
0 <= Ftilde <= 1
~~~

도 아니고 monotone CDF도 아니다.

따라서:

~~~text
RAW SIGNED LOCAL ESTIMATOR
!=
FINAL CDF OBJECT
~~~

이다.

## 16. Coverage-preserving CDF band projection

raw simultaneous band event E에서:

~~~text
L_raw(x)
<=
F(x)
<=
U_raw(x)
~~~

가 모든 required x에 대해 성립한다고 하자.

Define:

~~~text
L_star(x)
=
max(
  0,
  sup_{y <= x} L_raw(y)
)

U_star(x)
=
min(
  1,
  inf_{y >= x} U_raw(y)
)
~~~

true CDF monotonicity 때문에 event E 위에서:

~~~text
L_star(x)
<=
F(x)
<=
U_star(x)
~~~

가 유지된다.

따라서 event E 위에서는 자동으로:

~~~text
L_star(x)
<=
U_star(x)
~~~

이다.

realized projection에서 crossing이 관측되면:

~~~text
EMPTY_PROJECTED_CDF_BAND
~~~

로 fail-close한다.

coverage proof 없이 endpoint 평균이나 cosmetic isotonic repair를 하지 않는다.

### Projection verdict

~~~text
W2 CDF-band projection
=
RESOLVED
~~~

at deterministic-lemma level.

## 17. Median / MAD consequence

projected band가 simultaneous-valid이면 R4 density-free deterministic projection을 다시 사용할 수 있다.

~~~text
signed local estimator
↓
raw simultaneous band
↓
coverage-preserving CDF projection
↓
generalized median set
↓
midpoint median interval
↓
raw MAD interval
~~~

따라서 signed raw estimator를 CDF로 직접 해석할 필요가 없다.

## 18. Why W2 is not yet frozen

Gaussian approximation만으로 executable critical value가 생기지 않는다.

Chang–Chen–Wu Theorem 10은 hyperrectangle bootstrap error를:

~~~text
bootstrap error
<=
Gaussian approximation error
+
Delta_n,r^(1/3) (log p)^(2/3)
~~~

형태로 제어한다.

따라서 sufficient covariance condition은 대략:

~~~text
Delta_n,r
=
o_p((log p)^(-2))
~~~

이다.

## 19. Covariance-estimation scaling blocker

local weighted vector에서는:

~~~text
B_n
Phi
Psi
=
O(b_n^(-1/2))
~~~

이므로 Theorem 11(iii)의 covariance-estimation stochastic prefactor는 최소:

~~~text
O(b_n^(-1))
=
O(n^beta)
~~~

scale을 갖는다.

published Theorem 11(iii)은 schematic하게:

~~~text
Delta_n,r
=
O_p(
 [B_n Phi + B_n^2 + Phi^2]
 n^(-c1)
 polylog(p)
)
+
covariance-bias term
~~~

을 주며:

~~~text
c1 > 0
~~~

임은 보장하지만 theorem statement만으로는 W2의 required beta>1/5에 대해:

~~~text
c1 > beta
~~~

를 검증할 explicit lower bound가 없다.

local-weight inflation n^beta를 상쇄하려면 단순 c1>0만으로는 부족하다.

따라서 현재 source binding으로:

~~~text
Delta_n,r (log p)^2 -> 0
~~~

를 확정할 수 없다.

이것이 현재 decisive blocker다.

## 20. Other bootstrap families are not silently substituted

Ma–Zhang 2026 maxima bootstrap의 main setup은 stationary time series다.

Dette–Wu 2026 locally stationary confidence-surface bootstrap은 smooth functional-coordinate construction에 묶여 있으며 atomic threshold vector의 drop-in theorem이 아니다.

따라서 둘 중 하나를 검증 없이 calibration engine으로 가져오지 않는다.

## 21. Decision matrix

| Requirement | W1 | W2 |
| --- | --- | --- |
| raw estimator CDF | PASS | projection required |
| no future leakage | PASS | PASS |
| latest-state structural access | PASS | PASS |
| bias | O(b) | O(b^2) |
| beta lower | >1/3 | >1/5 |
| Gaussian beta upper | <alpha/(6+3alpha) | same |
| non-empty bias/Gaussian interval | NO | YES iff alpha>3 |
| lattice/ties | PASS | PASS |
| threshold finite-vector route | available | available |
| CDF projection | N/A | RESOLVED |
| Gaussian max root | REJECTED | FEASIBLE |
| executable calibration | N/A | UNRESOLVED |
| disposition | REJECT | SURVIVES / BLOCKED ON CALIBRATION |

## 22. Formal route disposition

### W1

~~~text
W1
=
REJECTED_EMPTY_RATE_INTERVAL
~~~

### W2

~~~text
W2
=
PREFERRED_SURVIVING_ROUTE

Gaussian rate
=
PASS

CDF projection
=
PASS

Calibration
=
BLOCKED
~~~

reason:

~~~text
WEIGHTED_LONG_RUN_COVARIANCE_RATE_UNRESOLVED
~~~

## 23. D2D ledger update

~~~text
P2 Local dependence
=
GEOMETRIC_PHYSICAL_DEPENDENCE PREFERRED
EXACT FINAL CALIBRATION COUPLING PENDING

P3 Local EDF
=
W2 GAUSSIAN RATE FEASIBLE

P4 latest-state
=
ONE-SIDED W2 STRUCTURE FEASIBLE

P5 finite-anchor coupling
=
UNCHANGED / RESOLVED

P6 all-later
=
GAUSSIAN MAX REPRESENTATION FEASIBLE
CALIBRATION PENDING

P7 calibration
=
BLOCKED_WEIGHTED_LRCOV_RATE

P8 median/MAD
=
CONDITIONALLY RESOLVED
~~~

현재 decisive blocker는 W1/W2 estimator 선택이 아니라 W2 weighted max root의 calibration이다.

## 24. No frozen inference contract artifact

task spec상 full route가 닫힌 경우에만:

~~~text
docs/contracts/NEXT6E_S6A_R5_LOCAL_WEIGHTED_INFERENCE_V1.json
~~~

을 생성할 수 있다.

현재 route는 full close가 아니다.

따라서:

~~~text
LOCAL_WEIGHTED_INFERENCE_V1.json
=
NOT CREATED
~~~

이다.

## 25. Next authorized task

recommended:

~~~text
NEXT-6E-S6A-R5-D2D2
WEIGHTED GAUSSIAN CALIBRATION RESOLUTION
~~~

D2D2는 두 route만 검토한다.

### C1 — Chang parametric bootstrap completion

explicit covariance-estimation rate를 확보하고 다음 joint parameter region이 non-empty인지 증명한다.

~~~text
1/5
<
beta
<
alpha/(6+3 alpha)

alpha > 3

plus covariance-bandwidth parameter

such that

Delta_n,r (log p)^2 -> 0
~~~

### C2 — theorem-matched direct bootstrap

다음 exact object를 직접 덮는 bootstrap theorem을 찾거나 project lemma로 완성한다.

~~~text
nonstationary
physical dependence
time-varying deterministic local weights
high-dimensional maximum
polynomial p_n
latest state
~~~

D2D2는 W1을 다시 열지 않는다.

C1/C2 모두 실패하면:

~~~text
R5 LOCAL DISTRIBUTIONAL REFERENCE
=
ARCHITECTURE RECONSIDERATION REQUIRED
~~~

이다.

## 26. Final state

~~~text
NEXT-6E-S6A-R5-D2D1
=
BLOCKED_W2_CALIBRATION_RATE_UNRESOLVED

W1
=
REJECTED_EMPTY_RATE_INTERVAL

W2
=
SURVIVING_ROUTE

W2 Gaussian rate interval
=
1/5
<
beta
<
alpha/(6+3 alpha)

required
=
alpha > 3

W2 CDF projection
=
RESOLVED

W2 threshold truncation
=
SYMBOLICALLY RESOLVED
subject to uniform q-moment
and
mu q > (1-beta)/2

W2 calibration
=
BLOCKED_WEIGHTED_LRCOV_RATE

CandidateDomain V2
=
UNCHANGED / FROZEN

R5 method
=
NOT FROZEN

R5 G-A
=
BLOCKED

R5-D2E
=
NOT AUTHORIZED

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
~~~

## 27. Primary source register

1. Chang, J., Chen, X., Wu, M. (2024). Central limit theorems for high dimensional dependent data. Bernoulli 30(1), 712–742. DOI: https://doi.org/10.3150/23-BEJ1614

2. Phandoidaen, N., Richter, S. (2022). Empirical process theory for nonsmooth functions under functional dependence. Electronic Journal of Statistics 16(1). DOI: https://doi.org/10.1214/22-EJS2023

3. Dette, H., Wu, W. (2026). Confidence Surfaces for the Mean of Locally Stationary Functional Time Series. Statistica Sinica 36, 583–604. DOI: https://doi.org/10.5705/ss.202023.0150

4. Ma, R., Zhang, S. (2026). Multiplier and empirical subsample bootstraps for maxima in high dimensional time series analysis. Journal of Multivariate Analysis 213, 105579. DOI: https://doi.org/10.1016/j.jmva.2025.105579

## 28. Applicability warning

No cited publication provides the complete StockScope W2 procedure verbatim.

The following are project-specific derivations:

~~~text
local-weight norm scaling
W1 empty-rate proof
W2 beta interval
deterministic lattice-tail truncation mapping
coverage-preserving monotone CDF-band projection
StockScope index-family construction
~~~

Independent theorem review remains required before any model-use approval.
