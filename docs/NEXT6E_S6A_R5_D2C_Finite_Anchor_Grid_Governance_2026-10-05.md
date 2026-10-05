# StockScope NEXT-6E-S6A-R5-D2C — Finite Anchor Grid Governance

작성일: 2026-10-05, Asia/Seoul  
문서 성격: 실제 method-governance decision. 구현/평가 문서가 아니다.  
기준 main: `e3c61333db5325b099af9d947622b5f83d4cf50c`  
Parent: `NEXT-6E-S6A-R5-D2B`  
Parent decision: `S2 PROSPECTIVE_FINITE_ANCHOR_GRID`

## 1. 최종 결정

R5 candidate grid를 다음과 같이 동결한다.

```text
NEXT-6E-S6A-R5-D2C
=
COMPLETE

CandidateDomainContract
=
NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2

Grid family
=
UNIFORM_EXACT_RATIONAL_FRACTION_GRID

Lower fraction
=
1/10

Grid step
=
1/20

Upper reserve
=
1/20

Approved fractions
=
j/20, j=2,...,19

Nominal anchor count
=
18

Largest anchor
=
19/20

Integer mapping
=
ceil(j*n/20)

Common-N semantics
=
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR

All-later semantics
=
RETAINED

Latest-state requirement
=
RETAINED

R5 method
=
NOT YET FROZEN

R5 G-A
=
BLOCKED

Implementation
=
NOT AUTHORIZED
```

frozen contract semantic SHA256:

```text
e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09
```

이 hash는 JSON의 `semantic_contract_sha256` 필드를 제외한 canonical semantic payload에 대한 SHA256이다.

## 2. 작업 경계

이번 D2C는 grid governance만 수행했다.

```text
DEV rerun = NO
DEV envelope = NOT ACCESSED
passing N = NOT ACCESSED
Reference Adequacy = NOT ACCESSED
Holdout = LOCKED / NOT ACCESSED
DB/runtime = NOT ACCESSED
Production = NOT ACCESSED
atomic theorem proof = NO
boundary theorem proof = NO
bootstrap/calibration = NO
backend implementation = NO
tests = NO
```

grid는 current Development 결과를 통과시키기 위해 선택하지 않았다.

## 3. 검토한 grid family

| Candidate | Fractions | Nominal anchors | Maximum interior fraction gap | 장점 | 주요 문제 |
| --- | --- | ---: | ---: | --- | --- |
| G1 decile | 1/10 간격 | 9 | 1/10 | 단순, multiplicity 작음 | resolution gap이 κ 자체와 같아 너무 거침 |
| G2 twentieth | 1/20 간격 | 18 | 1/20 | bounded multiplicity, exact rational, 해상도 개선 | G1보다 family 두 배 |
| G3 fortieth | 1/40 간격 | 36 | 1/40 | 가장 세밀 | 아직 theorem이 미해결인데 multiplicity를 다시 두 배 확대 |
| G4 front-dense | 앞쪽만 촘촘 | 설계별 | 최대 1/10 수준 | 작은 anchor 해상도 증가 | 앞쪽을 더 중요하게 취급할 독립 product/theorem 근거가 없음 |

최종 선택:

```text
G2
=
UNIFORM 1/20 FRACTION GRID
```

이다.

## 4. 왜 1/20인가

이 값은 theorem-optimal 숫자라고 주장하지 않는다.

```text
theorem_optimal_claim
=
NO
```

R2A에서 이미 `κ=1/10`을 lower-domain design scale로 고정했다. grid step이 다시 `1/10`이면 candidate granularity가 lower-bound truncation과 같은 크기여서 finite-grid 전환으로 인한 resolution loss가 너무 크다.

따라서 첫 bounded refinement로:

```text
Δ
=
κ/2
=
1/20
```

을 사용한다.

`1/40`은 resolution을 다시 절반으로 줄이는 대신 nominal candidate multiplicity를 36개로 늘린다. 현재 R5가 simultaneous theorem burden을 줄이기 위해 finite-anchor architecture를 선택했다는 점을 고려하면, independent product requirement 없이 36개까지 늘리는 것은 D2B 목적과 어긋난다.

모든 candidate가 `j/20` 정수 비율로 표현되므로 floating identity나 platform-specific rounding이 필요 없다.

결론적으로 `1/20`은 statistical optimum이 아니라 outcome-independent한 project method-resolution convention이다.

## 5. Upper reserve

largest anchor를:

```text
19/20 = 0.95
```

로 고정한다.

따라서 latest state `1`과 largest anchor 사이 nominal fraction:

```text
ρ = 1/20
```

을 남긴다.

이것은 현재 sample에서 정확히 충분한 later observations가 존재한다는 보장이 아니다. 의미는 candidate design 자체가 latest state와 동일한 위치까지 anchor를 밀어 넣지 않으며 한 grid cell 크기의 positive future-reference region을 남긴다는 것이다.

```text
upper reserve
!=
suffix sufficiency proof
```

이다.

## 6. Frozen anchor family

```text
A02 =  2/20 = 0.10
A03 =  3/20 = 0.15
A04 =  4/20 = 0.20
A05 =  5/20 = 0.25
A06 =  6/20 = 0.30
A07 =  7/20 = 0.35
A08 =  8/20 = 0.40
A09 =  9/20 = 0.45
A10 = 10/20 = 0.50
A11 = 11/20 = 0.55
A12 = 12/20 = 0.60
A13 = 13/20 = 0.65
A14 = 14/20 = 0.70
A15 = 15/20 = 0.75
A16 = 16/20 = 0.80
A17 = 17/20 = 0.85
A18 = 18/20 = 0.90
A19 = 19/20 = 0.95
```

fractions를 reduced form으로 다시 식별하지 않는다. 예를 들어 `A10=10/20`은 grid position identity다.

## 7. Integer mapping

sample size `n`은 aligned 3D horizon process length다.

```text
N_j(n)
=
ceil(j*n/20)
=
floor((j*n+19)/20)
```

positive integer n에 대해 정의한다.

이 rule은 deterministic, monotone, cross-language reproducible이며 floating point를 요구하지 않는다.

## 8. Collision / deduplication

작은 n에서는 서로 다른 fractions가 동일한 integer N으로 매핑될 수 있다.

canonical rule:

```text
deduplicate_by
=
MAPPED_INTEGER_N

canonical representative
=
smallest grid numerator j

source identities
=
retain every contributing anchor_id
```

동일 integer N을 여러 statistical candidate로 세지 않는다.

## 9. Candidate ordering

dedup 후:

```text
ascending mapped integer N
then ascending grid numerator
```

로 정렬한다.

common-N은 이 ordering 안에서의 최소 supported candidate다.

## 10. Structural upper-bound handling

candidate는 later state가 있어야 하므로:

```text
N < n
```

이어야 한다.

작은 n에서 `ceil(jn/20)=n`이면:

```text
STRUCTURALLY_INELIGIBLE_NO_LATER_STATE
```

로 분류한다.

이는 FAIL/INADEQUATE/UNSTABLE을 뜻하지 않는다.

## 11. Effective cardinality

nominal grid size는 18이다.

dedup/structural eligibility 이후:

```text
1 <= effective candidate count <= 18
```

일 때 structural candidate domain이 존재한다.

0개면:

```text
NO_ELIGIBLE_GRID_ANCHOR
```

이다.

후속 theorem contract가 더 강한 minimum-information rule을 요구할 수 있다. D2C의 minimum 1은 statistical sufficiency 보장이 아니다.

## 12. Candidate-resolution semantics

grid resolution:

```text
Δ = 1/20
class = METHOD_RESOLUTION_GRANULARITY
```

이다.

covered fraction span:

```text
[1/10,19/20]
```

이 span 안의 arbitrary fraction `s`를 바로 위 approved grid fraction `r`로 올려 생각하면:

```text
0 <= r-s < 1/20
```

이다.

integer-level prospective bound:

```text
ceil(r*n) - ceil(s*n)
<=
ceil(n/20)
```

이다.

이것은 runtime에서 hidden all-integer optimum을 계산하라는 뜻이 아니다. grid granularity를 설명하는 prospective method bound다.

## 13. 19/20 초과 영역

```text
s > 19/20
```

에는 upward approved anchor가 없다.

따라서:

```text
NO_APPROVED_UPWARD_GRID_ANCHOR
```

이며 1로 반올림하거나 19/20으로 내리지 않는다.

## 14. Out-of-grid semantics

approved mapped candidate가 아닌 N은:

```text
OUTSIDE_R5_APPROVED_CANDIDATE_GRID
```

이다.

FAIL/INADEQUATE/UNSTABLE/ZERO_SUPPORT로 표시하지 않는다.

## 15. Eligibility rule

```text
R5_ELIGIBLE(N_j)
=
APPROVED_GRID_MEMBER
AND
MAPPED_INTEGER_N_LT_N
AND
LATER_STATE_EXISTS
AND
JOINT_FEATURE_AVAILABLE
AND
FUNCTIONAL_COMPUTABLE
AND
R5_METHOD_CONTRACT_APPLICABLE
```

D2C는 마지막 predicate를 승인하지 않는다. R5 theorem/method contract가 아직 frozen되지 않았기 때문이다.

## 16. Common-N semantics

R5 공식 common-N ID:

```text
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR
```

정의:

> frozen CandidateDomain V2의 effective candidate family 안에서, 구조적으로 평가 가능하고 최종 승인된 R5 method 및 policy criteria를 모두 만족하는 가장 작은 mapped integer anchor N.

다음 표현은 R5에서 금지한다.

```text
minimum among all integer N
exact minimum required observations
```

## 17. All-later / latest-state semantics

```text
later_state_scope
=
ALL_APPROVED_LATER_STATES

latest_state_required
=
true
```

finite grid는 anchor index만 축소한다. later states를 sparse grid로 바꾸지 않는다.

## 18. R2A V1 relation

기존 `NEXT6E_S6A_R2A_CANDIDATE_DOMAIN_V1`은 수정하지 않는다.

```text
V1
=
HISTORICAL / IMMUTABLE
VALID FOR ORIGINAL R2/R4 LINEAGE

V2
=
R5 LOCAL-DISTRIBUTIONAL CANDIDATE CONTRACT
```

R5에 대해서만 V1은 `SUPERSEDED_FOR_R5_ONLY`다.

## 19. UI / product wording boundary

향후 product-facing output에서 every-integer optimum처럼 표시하면 안 된다.

금지:

```text
"정확한 최소 필요 관측 수"
```

허용 의미:

```text
"승인된 기준점 중 최소 지원 구간"
"minimum supported approved anchor"
```

UI 자체는 이번 task에서 변경하지 않는다.

## 20. Change control

다음은 모두 CandidateDomain new version을 요구한다.

```text
anchor add/remove
fraction change
grid step change
cardinality change
integer mapping change
collision rule change
upper boundary change
later-state scope change
```

DEV/Production 결과에 맞춰 grid를 수정하거나 과거 evaluation identity를 재라벨링하는 것은 금지한다.

## 21. Frozen contract artifact

actual contract:

```text
docs/contracts/NEXT6E_S6A_R5_CANDIDATE_DOMAIN_V2.json
```

status:

```text
FROZEN
```

semantic SHA256:

```text
e9a0427ea3c5e34b96db3bbaab026de51d83f27fc0f4d0ef32c9122398d31e09
```

이 artifact는 template이 아니라 D2C 실제 governance decision이다.

## 22. 다음 blocker

D2C는 simultaneous theorem을 해결하지 않는다.

남은 핵심:

```text
Atomic transform lemma
One-sided u=1 local EDF
Local functional-dependence contract
Local EDF bias/stochastic limit
Finite-anchor joint coupling
ALL-LATER simultaneous coverage
Calibration
Median/MAD final projection review
```

다음 authorized task:

```text
NEXT-6E-S6A-R5-D2D
FINITE-ANCHOR LOCAL-EDF THEOREM RESOLUTION
```

이다.

## 23. Final state

```text
NEXT-6E-S6A-R5-D2C
=
COMPLETE

Grid family
=
UNIFORM_EXACT_RATIONAL_FRACTION_GRID

Grid cardinality
=
18 FROZEN

Anchor fractions
=
j/20, j=2..19 FROZEN

Grid step
=
1/20 FROZEN

Integer mapping
=
ceil(j*n/20) FROZEN

Collision rule
=
FROZEN

Upper reserve
=
1/20 FROZEN

Resolution contract
=
FROZEN

CandidateDomain V2
=
FROZEN

Common-N
=
MINIMUM_SUPPORTED_APPROVED_GRID_ANCHOR

All-later
=
RETAINED

Latest state
=
REQUIRED

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
```
