# StockScope NEXT-6E-S6A-R5-MUR3-BR1 — R5R 계약 모호성 해소

작성일: 2026-10-05, Asia/Seoul  
단계: NEXT-6E-S6A-R5-MUR3-BR1  
Baseline main: `4404618cf90e3a340f275b4481c7fdaec6f8d918`

## 1. 결론

MUR3에서 발견한 세 가지 deterministic contract ambiguity를 모두 해소했다.

```text
NEXT-6E-S6A-R5-MUR3-BR1
=
COMPLETE

MUR3-F01
=
RESOLVED

MUR3-F02
=
RESOLVED

MUR3-F03
=
RESOLVED

R5R deterministic contract review
=
PASS

Implementation
=
NOT AUTHORIZED
```

이번 BR1은 계산 방법을 바꾸지 않았다.

다음은 그대로다.

```text
Target ID
=
NEXT6E_S6A_R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1

Method ID
=
NEXT6E_S6A_R5R_EMPIRICAL_STABILITY_V1

T_EMP / L_EMP / S_EMP
=
UNCHANGED

w(n)=ceil(n/10)
=
UNCHANGED

18-anchor grid
=
UNCHANGED

all-later
=
UNCHANGED

latest-state
=
UNCHANGED

common-N intent
=
UNCHANGED
```

## 2. Method Contract V2

새 frozen contract:

```text
docs/contracts/
NEXT6E_S6A_R5R_METHOD_CONTRACT_V2.json
```

Design SHA256:

```text
05852b077e6c29820643299f66984f496ffe806d88c6544c577ee3357c5f74eb
```

Semantic SHA256:

```text
d3b133f01f8d705fabd1456d5d5053570ff6d73586675c80903b06ce72c6e8e8
```

V1은 historical frozen artifact로 유지한다.

V2는 다음 ambiguity만 명시적으로 닫는다.

1. joint chronology / missing-horizon boundary
2. canonical chronology hash
3. exact rational numeric comparison

## 3. Child contracts

CandidateDomain:

```text
NEXT6E_S6A_R5R_CANDIDATE_DOMAIN_V1

SHA256
=
2f89ea3fdf775d718fabf955ee266b5cf36736f68b0fe97ced2cc5da83e0cdb4
```

Window:

```text
NEXT6E_S6A_R5R_WINDOW_PROFILE_V1

SHA256
=
47a11455b159564db80eaf2c61bd89710a4bf56aea5d740eb60617ac2a3d385c
```

둘 다 변경하지 않았다.

## 4. MUR3-F01 Resolution

Finding:

```text
MISSING_HORIZON_JOINT_CHRONOLOGY_SEMANTICS
```

기존 ambiguity:

- "all horizons AVAILABLE인 row만 joint chronology에 포함"
- "missing required horizon = invalid input"

두 문장이 evaluator 단계와 preprocessing 단계를 구분하지 않아 충돌했다.

최종 rule:

```text
PREBOUND_COMPLETE_JOINT_CHRONOLOGY
```

흐름:

```text
SOURCE DATASET

→
PREDEFINED JOINT ELIGIBILITY RULE

→
RECORD EXCLUSION PROVENANCE

→
FREEZE EVALUATION DATASET IDENTITY/HASH

→
R5R EVALUATOR
```

source 단계에서는 required horizon이 모두 AVAILABLE/exact-valid한 row만 evaluation chronology 후보로 남길 수 있다.

단 이 filtering은 evaluation dataset identity를 freeze하기 전에만 허용한다.

Evaluator에 전달된 bound payload에는 모든 required horizon이 존재해야 한다.

Evaluator 내부에서:

```text
drop
filter
impute
repair
```

전부 금지한다.

bound payload 안에서 required horizon이 빠져 있으면:

```text
BLOCKED

MISSING_REQUIRED_HORIZON
```

이다.

Evaluator는 그 row를 제거해서 joint n을 다시 계산하면 안 된다.

### Required provenance

binding artifact에는:

```text
source_row_count

joint_row_count

excluded_before_binding_count

joint_eligibility_rule

excluded_reason_counts
```

가 필요하다.

따라서 source preprocessing과 evaluator contract violation이 명확히 분리됐다.

MUR3-F01:

```text
RESOLVED
```

## 5. MUR3-F02 Resolution

Finding:

```text
JOINT_CHRONOLOGY_HASH_CANONICALIZATION_UNDEFINED
```

새 contract ID:

```text
R5R_JOINT_CHRONOLOGY_HASH_V1
```

chronology hash는 실제 계산에 사용된 날짜 sequence만 고정한다.

feature content integrity는 별도:

```text
dataset_hash
```

가 담당한다.

### Canonical payload

```json
{
  "schema_id": "R5R_JOINT_CHRONOLOGY_HASH_V1",
  "horizon_set": [1, 5, 10],
  "n": 3,
  "rows": [
    {"i": 1, "observation_date": "2026-01-01"},
    {"i": 2, "observation_date": "2026-01-02"},
    {"i": 3, "observation_date": "2026-01-05"}
  ]
}
```

Canonical rule:

```text
UTF-8

recursive lexicographic object-key order

array order preserved

compact separators

no whitespace

observation date
=
YYYY-MM-DD
```

Algorithm:

```text
SHA-256
```

Output:

```text
64 lowercase hex characters
```

### Targeted fixture

Canonical serialization:

```text
{"horizon_set":[1,5,10],"n":3,"rows":[{"i":1,"observation_date":"2026-01-01"},{"i":2,"observation_date":"2026-01-02"},{"i":3,"observation_date":"2026-01-05"}],"schema_id":"R5R_JOINT_CHRONOLOGY_HASH_V1"}
```

Expected SHA-256:

```text
afea17c4285bd17e3e486af30c993cf53093ce30876af4ac6ba37e912767ecf5
```

Targeted fixture:

```text
PASS
```

MUR3-F02:

```text
RESOLVED
```

## 6. MUR3-F03 Resolution

Finding:

```text
NUMERIC_COMPARISON_CANONICALIZATION_UNDEFINED
```

새 contract:

```text
R5R_EXACT_RATIONAL_V1
```

Authoritative representation:

```json
{
  "numerator": "1",
  "denominator": "3"
}
```

numerator / denominator은 base-10 integer string이다.

Normalization:

```text
denominator > 0

gcd(|numerator|,denominator)=1

zero = 0/1

no leading zero

negative sign only on numerator
```

## 7. Exact arithmetic

Authoritative arithmetic:

```text
ARBITRARY_PRECISION_EXACT_RATIONAL
```

적용 대상:

```text
T_EMP

midpoint median

midpoint MAD

L_EMP

S_EMP

tau_T

tau_L

tau_S
```

Binary float는 display에는 사용할 수 있지만 support 판정의 authoritative 값으로 사용할 수 없다.

## 8. Exact policy comparison

Metric:

```text
a/b
```

Tolerance:

```text
c/d
```

이면:

```text
a/b <= c/d
```

판정은:

```text
a*d <= c*b
```

으로 한다.

binary-float epsilon은 금지한다.

Equality:

```text
metric == tau
→
WITHIN_POLICY
```

이다.

## 9. Decimal policy proposal

향후 사람이:

```text
0.05
```

를 승인한다면 authoritative policy binding은 decimal text에서 exact하게:

```text
5/100
→
1/20
```

으로 변환한다.

binary float 0.05를 저장한 뒤 역변환하는 방식은 사용하지 않는다.

## 10. F03 targeted fixtures

### Equal boundary

```text
metric = 1/3
tau    = 1/3

→ WITHIN_POLICY
```

PASS.

### Decimal approximation below 1/3

```text
metric = 1/3

tau
=
333333/1000000
```

Cross multiplication:

```text
1 * 1000000
=
1000000

333333 * 3
=
999999
```

따라서:

```text
metric > tau
→
EXCEEDS_POLICY
```

PASS.

### Decimal text 0.5

```text
0.5
→
5/10
→
1/2
```

metric 1/2와 equality:

```text
WITHIN_POLICY
```

PASS.

MUR3-F03:

```text
RESOLVED
```

## 11. Targeted fixture artifact

생성:

```text
docs/fixtures/
NEXT6E_S6A_R5R_MUR3_BR1_TARGETED_FIXTURES_V1.json
```

Fixture count:

```text
6
```

전체 targeted verdict:

```text
PASS
```

기존 25-fixture artifact는 수정하지 않았다.

## 12. Previous MUR3 result handling

Historical:

```text
NEXT6E_S6A_R5R_DETERMINISTIC_REVIEW_RESULT_V1
=
BLOCKED_CONTRACT_AMBIGUITY
```

그대로 유지한다.

V1 review가 당시 잘못된 것이 아니라, 당시 contract가 실제로 ambiguous했기 때문이다.

BR1은 history를 덮어쓰지 않는다.

## 13. Inherited review units

다음 MUR3 V1 PASS units는 그대로 inherit 가능하다.

```text
primitive arithmetic

exact ECDF

median/MAD/ties

zero-MAD fail-close

window rule

first-anchor/window identity

candidate mapping/collision

all-later

latest-state

horizon AND

metric AND

earliest common-N

no-supported-anchor semantics

BLOCKED vs NOT_SUPPORTED

argmax tie rule

fixture-policy isolation
```

이 계산들은 V2에서 변경되지 않았다.

## 14. Targeted re-review result

```text
MUR3-F01
=
RESOLVED

MUR3-F02
=
RESOLVED

MUR3-F03
=
RESOLVED

unresolved MAJOR
=
0

unresolved MEDIUM
=
0
```

따라서 effective deterministic contract review:

```text
PASS
```

이다.

## 15. Gate impact

현재:

```text
R5R-G0
=
PASS

R5R-G1
=
BLOCKED_PENDING_EVALUATION_DATA_BINDING

R5R-G2
=
PASS

R5R deterministic contract review
=
PASS

R5R-G3
=
BLOCKED_PENDING_S6B_R5R_POLICY_AMENDMENT

R5R-G4
=
NOT AUTHORIZED

Implementation
=
NOT AUTHORIZED

Reference Adequacy
=
NOT AUTHORIZED
```

## 16. Remaining primary blocker

계산계약 ambiguity는 닫혔다.

다음 큰 blocker는:

```text
tau_T
tau_L
tau_S
```

의 R5R-compatible policy value / evidence / approval이다.

현재 S6B의 metric semantics는 R5R와 직접 호환되지만 numeric values와 approval authority가 없다.

따라서 다음 우선 작업:

```text
NEXT-6E-S6B-R5R-P1
R5R POLICY AMENDMENT / TOLERANCE EVIDENCE DESIGN
```

이 적절하다.

## 17. Access boundary

```text
DEV
=
NOT ACCESSED

Reference Adequacy
=
NOT ACCESSED

passing N
=
NOT ACCESSED

forward envelope
=
NOT ACCESSED

Holdout
=
LOCKED / NOT ACCESSED

runtime DB
=
NOT ACCESSED

Production
=
NONE
```

Targeted synthetic fixtures만 사용했다.

## 18. Final state

```text
NEXT-6E-S6A-R5-MUR3-BR1
=
COMPLETE

Method Contract V2
=
FROZEN

Deterministic Contract Review
=
PASS

Target ID
=
UNCHANGED

Method ID
=
UNCHANGED

CandidateDomain
=
UNCHANGED

Window Profile
=
UNCHANGED

Formula architecture
=
UNCHANGED

Policy numeric values
=
UNRESOLVED

Implementation
=
NOT AUTHORIZED
```
