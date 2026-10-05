# StockScope NEXT-6E-S6A-R5-D2D2 — Weighted Gaussian Calibration Resolution

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 calibration-theorem resolution 결과. 구현/평가 문서가 아니다.  
기준 main: db24eff0bf9e6a821e17b19284830884ee8e444c  
Parent: NEXT-6E-S6A-R5-D2D1  
CandidateDomain V2 semantic SHA256: e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09

## 1. 최종 판정

~~~text
NEXT-6E-S6A-R5-D2D2
=
BLOCKED_CALIBRATION_ROUTE_EXHAUSTED

C1 Chang parametric Gaussian bootstrap
=
REJECTED_AS_COMPLETE_STOCKSCOPE_CALIBRATION

C1 oracle covariance-rate feasibility
=
PRESERVED

C1 observable centering
=
UNRESOLVED

C1 uniform root non-degeneracy
=
UNRESOLVED / INCOMPATIBLE WITH GROWING FULL THRESHOLD GRID

C2 theorem-matched direct bootstrap
=
REJECTED_NO_DIRECT_THEOREM_MATCH

W2 Gaussian root
=
FEASIBLE

W2 executable calibration
=
NOT ESTABLISHED

R5 LOCAL_DISTRIBUTIONAL_REFERENCE
=
ARCHITECTURE_RECONSIDERATION_REQUIRED

R5 method
=
NOT FROZEN

R5-D2E FINAL FREEZE
=
NOT AUTHORIZED

R5-D3
=
NOT AUTHORIZED
~~~

D2D2 결과, 현재 R5의 blocker는 Gaussian approximation 가능 여부가 아니다. W2 root의 Gaussian approximation rate는 D2D1에서 non-empty 영역을 확보했다.

막힌 지점은 실제 관측자료에서 covariance / critical value를 추정하면서 time-varying local centering과 atomic tail-coordinate degeneracy까지 함께 정당화하는 calibration layer다.

## 2. 작업 경계

~~~text
DEV raw data = NOT ACCESSED
DEV rerun = NO
sealed diagnostic used for calibration choice = NO
Reference Adequacy = NOT ACCESSED
forward envelope = NOT ACCESSED
passing anchor = NOT ACCESSED
Holdout = LOCKED / NOT ACCESSED
DB/runtime = NOT ACCESSED
Production = NOT ACCESSED
backend/frontend/tests = UNCHANGED
~~~

CandidateDomain V2도 변경하지 않았다.

## 3. Frozen W2 input

~~~text
W1
=
REJECTED_EMPTY_RATE_INTERVAL

W2
=
ONLY SURVIVING WEIGHTED ROUTE

h_n
=
n^(-beta)

1/5
<
beta
<
alpha/(6+3 alpha)

alpha
>
3
~~~

signed one-sided second-order local weighting, all-later semantics, latest-state requirement, lattice/ties, coverage-preserving CDF projection은 그대로 유지한다.

## 4. C1 — Chang parametric Gaussian bootstrap

Primary source:

Jinyuan Chang, Xiaohui Chen, Mingcong Wu, Central limit theorems for high dimensional dependent data, Bernoulli 30(1), 2024, 712–742. DOI: https://doi.org/10.3150/23-BEJ1614

Theorem 10의 hyper-rectangle bootstrap bound는 covariance max-norm error Delta_n,r가 충분히 작아야 함을 요구한다.

~~~text
Delta_n,r
=
o_p((log p)^(-2))
~~~

Theorem 11은 possibly nonstationary physical-dependence sequence에 대한 kernel long-run covariance estimator를 제공한다.

### Oracle covariance-rate feasibility

D2D1의 local weighted vector에서는 다음 scale inflation이 있다.

~~~text
B_n, Phi, Psi
=
O(h_n^(-1/2))
=
O(n^(beta/2))
~~~

Theorem 11의 detailed rate decomposition에 covariance bandwidth와 auxiliary truncation rate를 대입하면 W2 Gaussian interval 일부에서 oracle-centered covariance error가 polynomially 감소하는 parameter region은 존재한다.

따라서 C1은 long-run covariance 추정 자체가 원천적으로 불가능해서 탈락하는 것이 아니다.

~~~text
ORACLE-CENTERED WEIGHTED COVARIANCE RATE
=
FEASIBLE
~~~

그러나 oracle centering은 executable procedure가 아니다.

## 5. C1 blocker A — observable local centering

R5 stochastic coordinate는 chronology-dependent mean을 가진 indicator를 centered한 형태다.

~~~text
Y_t,j
=
h_n^(-1/2)
K_j(t)
[
 I_t,j - E(I_t,j)
]
~~~

여기서 E(I_t,j)=F_h(t/n,x)는 실제 실행 시 알려져 있지 않다.

실제 covariance estimator는 이를 estimated local CDF로 residualize해야 한다.

후보 perturbation 계산상 local mean uniform error가

~~~text
r_n
=
O_p(
 sqrt(log p / (n h_n))
 +
 h_n^2
)
~~~

라면 covariance bandwidth ell_n=n^rho에 대한 centering perturbation은 대략

~~~text
ell_n h_n^(-1) r_n
~~~

scale로 제어될 가능성이 있으며,

~~~text
rho < beta

rho + 3 beta / 2 < 1/2
~~~

같은 non-empty candidate condition도 존재한다.

하지만 이 계산은 아직 project derivation이다.

필요한 theorem은 동시에 다음을 다뤄야 한다.

- 모든 approved anchors
- 모든 approved later chronology states
- 3 horizons
- active atomic thresholds
- overlapping local windows
- 같은 자료로 local mean과 covariance를 모두 추정하는 효과
- signed W2 local smoother

따라서:

~~~text
C1_OBSERVABLE_CENTERING
=
UNRESOLVED

reason
=
LOCAL_MEAN_RESIDUALIZATION_RATE_UNRESOLVED
~~~

이다.

## 6. C1 blocker B — uniform root non-degeneracy

Chang et al. Condition 3은 모든 Gaussian-calibrated coordinate에 대해 normalized partial-sum variance가 universal positive constant 이상임을 요구한다.

R5 coordinate는 atomic thresholds:

~~~text
1{X_t^h <= x}
~~~

이다.

far-left / far-right thresholds에서는 Bernoulli probability가 0 또는 1에 접근할 수 있으므로 variance 역시 0에 접근할 수 있다.

D2D1의 deterministic threshold range

~~~text
|x| <= M_n

M_n -> infinity
~~~

은 omitted tail mass를 제어하는 장치이지 coordinate variance lower bound를 보장하는 장치가 아니다.

오히려 growing threshold domain은 더 extreme한 thresholds를 포함한다.

따라서:

~~~text
moment tail control
!=
Gaussian coordinate non-degeneracy
~~~

이다.

현재 R5 assumption set으로는:

~~~text
min_j V_n,j >= K3 > 0
~~~

를 전체 growing threshold family에 대해 승인할 수 없다.

### 검토했지만 자동 도입하지 않은 우회책

- fixed central threshold domain: full CDF-sup target을 보존하지 못함
- data-dependent variance screening: random selection + excluded-coordinate coverage라는 새 architecture 필요
- tail-coordinate deletion: full TAIL target 변경
- oracle active-set selection: 실행 불가능

따라서:

~~~text
C1_UNIFORM_ROOT_NONDEGENERACY
=
UNRESOLVED
~~~

이다.

## 7. C1 최종 판정

C1은 oracle covariance rate가 불가능해서 실패한 것이 아니다.

complete executable calibration에 필요한 두 연결이 닫히지 않았다.

~~~text
1. observable local-mean residualization
2. non-degenerate Gaussian core와 low-variance atomic coordinates의 valid joint treatment
~~~

따라서:

~~~text
C1
=
REJECTED_AS_COMPLETE_ROUTE

reason_codes
=
LOCAL_MEAN_RESIDUALIZATION_RATE_UNRESOLVED
UNIFORM_ROOT_NONDEGENERACY_UNRESOLVED
~~~

oracle covariance-rate feasibility는 향후 architecture에서 재사용 가능하다.

## 8. C2 — direct theorem-matched bootstrap

D2D2에서 다음 exact target을 직접 다루는 theorem을 다시 조사했다.

~~~text
nonstationary triangular array
physical dependence
time-varying deterministic local weights
high-dimensional max
growing dimension
all-later index
latest state
atomic threshold coordinates
bootstrap critical value
~~~

가장 가까운 새 source는:

Miaoshiqi Liu, Jun Yang, Zhou Zhou, Wasserstein and Convex Gaussian Approximations for Non-stationary Time Series of Diverging Dimensionality, arXiv:2506.08723, 2025.

이 논문은 분명 중요한 진전이다.

- nonstationary triangular array를 time-varying Bernoulli shift로 모델링
- physical dependence 사용
- multiplier bootstrap을 이론적으로 정당화
- block sums + Gaussian multipliers로 covariance structure 근사

그러나 R5 direct adoption에는 핵심 mismatch가 있다.

## 9. C2 mismatch A — covariance non-degeneracy

Liu–Yang–Zhou Assumption 1은 normalized sum covariance matrix의 smallest eigenvalue가 fixed positive constant lambda_* 이상이기를 요구한다.

이는 Chang의 coordinate-wise Condition 3보다 강하다.

R5 vector에는 같은 distribution의 여러 nested indicator coordinates가 들어간다.

~~~text
1{X<=x1}
1{X<=x2}
...
~~~

threshold dimension이 커지면 nested / near-redundant / tail-degenerate coordinates가 함께 포함된다.

현재 R5 model contract는 full covariance의 minimum eigenvalue가 dimension-uniform positive constant라는 가정을 정당화하지 않는다.

따라서:

~~~text
DIRECT_BOOTSTRAP_NONDEGENERACY_MISMATCH
~~~

이다.

## 10. C2 mismatch B — dimension growth

Liu–Yang–Zhou의 favorable bootstrap/GA rate도 dimension d의 성장에 강한 제약을 둔다.

논문은 favorable high-moment / short-memory regime에서 convex GA가 대략 n^(2/5) 미만 규모의 dimension까지 가능함을 강조하고, Wasserstein branch도 typical favorable regime에서 n^(1/2)보다 작은 차원 성장과 결합된다.

R5 simultaneous coordinate family는 threshold를 넣기 전에도:

~~~text
18 anchors
× O(n) later chronology states
× 3 horizons
~~~

을 포함한다.

따라서 direct-vector dimension은 이미:

~~~text
Omega(n)
~~~

이다.

growing threshold coordinates를 넣으면 더 커진다.

따라서 direct application의 dimension regime를 만족하지 않는다.

Reason:

~~~text
DIRECT_BOOTSTRAP_DIMENSION_RATE_MISMATCH
~~~

## 11. C2 mismatch C — estimated local centering

Liu–Yang–Zhou core theorem 역시 centered HDNS vectors를 대상으로 한다.

논문의 regression application에서 estimated residuals를 쓰는 사례가 있지만, 그것은 해당 estimating equation에 대한 별도 proof다.

이를 R5의 chronology-varying local CDF mean residualization에 자동 이전할 수 없다.

따라서:

~~~text
DIRECT_BOOTSTRAP_CENTERING_NOT_TRANSFERRED
~~~

이다.

## 12. Other C2 candidates

### Ma & Zhang 2026

High-dimensional maxima bootstrap을 제공하지만 reviewed setup은 current R5 nonstationary local-weighted triangular array를 직접 덮지 않는다.

~~~text
DIRECT MATCH = NO
~~~

### Dette & Wu 2026

locally stationary simultaneous confidence-surface bootstrap은 제공하지만 functional-coordinate smoothness가 direct atomic step-function EDF coordinate와 맞지 않는다.

~~~text
DIRECT MATCH = NO
~~~

### Hill 2026 wild bootstrap

broad motivation은 heterogeneous/nonstationary setting을 언급하지만 reviewed main bootstrap assumptions에는 second-order stationarity가 포함된다.

~~~text
DIRECT MATCH = NO
~~~

### Recent degenerate high-dimensional CLT work

2026 degenerate Gaussian-approximation results는 non-degeneracy를 완화하는 중요한 방향이지만 reviewed result는 independent-data setting이며 R5의 dependent nonstationary weighted max bootstrap 전체를 제공하지 않는다.

~~~text
DIRECT MATCH = NO
~~~

## 13. C2 판정

현재 확인한 source 중 R5 exact calibration object를 직접 덮는 theorem은 없다.

~~~text
C2
=
REJECTED_NO_DIRECT_THEOREM_MATCH

reason_codes
=
DIRECT_BOOTSTRAP_NONDEGENERACY_MISMATCH
DIRECT_BOOTSTRAP_DIMENSION_RATE_MISMATCH
DIRECT_BOOTSTRAP_CENTERING_NOT_TRANSFERRED
~~~

## 14. Calibration decision table

| Requirement | C1 Chang parametric Gaussian | C2 direct bootstrap |
| --- | --- | --- |
| Nonstationary physical dependence | YES | closest source YES |
| High-dimensional max | YES | partial |
| W2 local-weight rate | oracle feasible | no exact theorem |
| Large dimension | strong | closest source insufficient |
| Covariance estimation | oracle feasible | block multiplier available in closest source |
| Time-varying observable centering | UNRESOLVED | UNRESOLVED |
| Atomic low-variance coordinates | Condition 3 blocker | stronger eigenvalue blocker |
| ALL-LATER family | Gaussian vector representation feasible | dimension mismatch |
| Executable critical value | NOT JUSTIFIED | NOT JUSTIFIED |
| Final | REJECT COMPLETE ROUTE | REJECT DIRECT MATCH |

## 15. No frozen inference contract

D2D2 success 시에만 생성할 예정이던:

~~~text
docs/contracts/NEXT6E_S6A_R5_LOCAL_WEIGHTED_INFERENCE_V1.json
~~~

은 생성하지 않는다.

~~~text
LOCAL_WEIGHTED_INFERENCE_V1
=
NOT CREATED
~~~

calibration이 닫히지 않았기 때문이다.

## 16. Proof-ledger effect

~~~text
P1 Atomic transform
=
CONDITIONAL_PROJECT_LEMMA_RESOLVED

P2 Local dependence
=
GEOMETRIC_PHYSICAL_DEPENDENCE FAMILY IDENTIFIED

P3 Local EDF
=
W2 GAUSSIAN RATE FEASIBLE

P4 Latest-state
=
W2 ONE-SIDED STRUCTURE FEASIBLE

P5 Finite-anchor coupling
=
RESOLVED_AT_ARCHITECTURE LEVEL

P6 ALL-LATER
=
GAUSSIAN VECTOR REPRESENTATION FEASIBLE
BUT COMPLETE BAND CALIBRATION NOT AVAILABLE

P7 Calibration
=
BLOCKED_CALIBRATION_ROUTE_EXHAUSTED

P8 Median/MAD
=
CONDITIONALLY RESOLVED
~~~

P7 때문에 final theorem-chain freeze는 불가능하다.

## 17. CandidateDomain V2

~~~text
NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2
=
UNCHANGED
FROZEN
VALID
~~~

이번 실패 원인은 18-anchor grid가 아니다.

threshold / local-centering / calibration layer다.

CandidateDomain V3를 만들 이유는 없다.

## 18. Architecture reconsideration trigger

D2D2는 approved W2 calibration branch의 종료점이다.

따라서:

~~~text
R5 LOCAL_DISTRIBUTIONAL_REFERENCE
=
ARCHITECTURE_RECONSIDERATION_REQUIRED
~~~

다만 다음 자산은 폐기하지 않는다.

- time-varying local-law target
- atomic transform project lemma
- CandidateDomain V2
- W2 one-sided second-order construction
- coverage-preserving CDF-band projection
- median/MAD deterministic projection
- W2 Gaussian rate interval
- oracle weighted covariance-rate feasibility

다음 architecture decision은 uncertainty calibration layer만 바꿀 수 있는지부터 검토해야 한다.

## 19. 다음 권장 작업

~~~text
NEXT-6E-S6A-R5-D2E0
CALIBRATION-BLOCKER ARCHITECTURE RECONSIDERATION
~~~

최소 후보:

### A1 — Hybrid Gaussian + deterministic low-variance envelope

Gaussian inference는 provably non-degenerate core에만 사용하고 tail / low-variance thresholds는 deterministic concentration bound로 덮는다.

핵심은 full CDF band coverage를 유지하면서 random screening을 피하거나 screening error를 formal하게 포함하는 것.

### A2 — Self-normalized / variance-adaptive max inference

uniform raw variance lower bound를 요구하지 않는 dependence-aware theorem을 찾는다.

### A3 — Analytical conservative concentration band

bootstrap을 버리고 theorem-backed physical-dependence concentration inequality로 simultaneous band를 만든다.

더 넓을 수 있지만 calibration audit은 단순해질 수 있다.

### A4 — Target / architecture reduction

A1-A3가 product meaning을 보존하지 못할 때만 검토한다.

D2E0에서 자동 선택하지 않는다.

## 20. 금지되는 해석

이번 결과는 bootstrap 자체가 수학적으로 불가능하다는 뜻이 아니다.

정확한 결론:

> 현재 승인된 R5 target과 reviewed theorem set만으로는 새 inference component 없이 완전한 executable calibration을 정당화하지 못했다.

따라서 다음 편법은 금지한다.

~~~text
normal 1.96 critical value
Bonferroni with independent SE
oracle covariance
stationary bootstrap without transfer proof
variance-screened coordinate deletion
tail threshold deletion
latest-state relaxation
later-state sparsification
~~~

## 21. Final state

~~~text
NEXT-6E-S6A-R5-D2D2
=
BLOCKED_CALIBRATION_ROUTE_EXHAUSTED

C1
=
REJECTED_AS_COMPLETE_ROUTE

C1 oracle covariance rate
=
FEASIBLE / REUSABLE

C1 observable centering
=
UNRESOLVED

C1 coordinate non-degeneracy
=
UNRESOLVED

C2
=
REJECTED_NO_DIRECT_THEOREM_MATCH

W2
=
GAUSSIAN_ROOT_FEASIBLE
BUT NOT CALIBRATABLE UNDER CURRENT APPROVED THEORY

CandidateDomain V2
=
UNCHANGED / FROZEN

R5 method
=
NOT FROZEN

R5 G-A
=
BLOCKED

R5-D2E FINAL FREEZE
=
NOT AUTHORIZED

R5-D3
=
NOT AUTHORIZED

Next stage
=
R5-D2E0 CALIBRATION-BLOCKER ARCHITECTURE RECONSIDERATION

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

## 22. Primary literature register

1. Chang, J., Chen, X., Wu, M. (2024). Central limit theorems for high dimensional dependent data. Bernoulli 30(1), 712–742. DOI: https://doi.org/10.3150/23-BEJ1614

2. Liu, M., Yang, J., Zhou, Z. (2025). Wasserstein and Convex Gaussian Approximations for Non-stationary Time Series of Diverging Dimensionality. arXiv:2506.08723.

3. Ma, R., Zhang, S. (2026). Multiplier and empirical subsample bootstraps for maxima in high dimensional time series analysis. Journal of Multivariate Analysis 213, 105579.

4. Dette, H., Wu, W. (2026). Confidence Surfaces for the Mean of Locally Stationary Functional Time Series. Statistica Sinica 36, 583–604.

5. Fang, X., Koike, Y., Liu, S.-H., Zhao, Y.-K. (2026, accepted/in press). High-dimensional Central Limit Theorems by Stein's Method in the Degenerate Case. Annals of Applied Probability.

## 23. Applicability warning

다음은 published procedure의 verbatim 적용이 아니라 StockScope-specific theorem mapping / blocker analysis다.

~~~text
W2 local weighting representation
local-centering perturbation candidate rate
atomic threshold degeneracy analysis
R5 dimension lower bound
direct nonstationary bootstrap-to-R5 mapping
~~~

향후 새 architecture에서 재사용할 경우 독립 theorem review가 필요하다.
