# StockScope NEXT-6E-R5R-IMPLEMENT — 구현 및 DEV 바인딩

작성일: 2026-10-06 (Asia/Seoul)  
단계: NEXT-6E-R5R-IMPLEMENT

## 1. 결론

이번 단계에서 R5R을 실제 코드로 구현하고 frozen deterministic fixture로 검증한 뒤, frozen DEV dataset의 identity / chronology / structural metadata를 바인딩했다.

최종 상태:

~~~text
R5R-G0 = PASS
R5R-G1 = PASS
R5R-G2 = PASS
R5R-G3 = PASS
R5R-G4 = PASS

R5R Reference Adequacy Evaluation
=
AUTHORIZED / NOT EXECUTED

JEV
=
NEXT
~~~

이번 단계에서는 실제 R5R metric 결과를 계산하지 않았다.

~~~text
T_EMP / L_EMP / S_EMP
=
NOT EVALUATED ON DEV

candidate support status
=
NOT EVALUATED

OBSERVED_PATH_COMMON_N
=
NOT EVALUATED

Reference Adequacy PASS / NOT_SUPPORTED
=
NOT EVALUATED
~~~

---

## 2. Authoritative bindings

Method:

~~~text
NEXT6E_S6A_R5R_METHOD_CONTRACT_V2

semantic
=
5519ad12a6e3dafb30041935c6ead2869d35148aadb2a6bab8443521ea8310c4
~~~

Policy:

~~~text
NEXT6E_S6B_R5R_POLICY_V1

semantic
=
8934d99d808b8c7afa837fb71601695457154747fbcafd592da44b337343bc22
~~~

CandidateDomain:

~~~text
2f89ea3fdf775d718fabf955ee266b5cf36736f68b0fe97ced2cc5da83e0cdb4
~~~

Window:

~~~text
47a11455b159564db80eaf2c61bd89710a4bf56aea5d740eb60617ac2a3d385c
~~~

---

## 3. 구현 파일

Pure evaluator:

~~~text
backend/app/macro/r5r_evaluator.py
~~~

주요 구현:

- exact Fraction arithmetic
- midpoint median
- midpoint MAD
- exact two-ECDF sup distance
- w(n)=ceil(n/10)
- 18-anchor candidate mapping
- collision canonicalization
- all-later evaluation
- latest-state inclusion
- T/L/S exact policy comparison
- argmax earliest-later tie rule
- SUPPORTED / EXCEEDS / BLOCKED
- normal NOT_SUPPORTED result
- OBSERVED_PATH_COMMON_N

Evaluator는 network / DB / filesystem / current time / randomness에 의존하지 않는 pure deterministic module이다.

Binding:

~~~text
backend/app/macro/r5r_binding.py
~~~

역할:

~~~text
frozen source dataset
→ identity validation
→ joint eligibility
→ chronology validation
→ exact integer BP validation
→ chronology hash
→ structural window/anchor binding
~~~

Evaluator 내부에서는 row filtering을 하지 않는다.

Binding CLI:

~~~text
tools/data/bind_macro_r5r_evaluation_next6e.py
~~~

이 CLI는 identity / chronology / structure만 바인딩하며 R5R metric을 실행하지 않는다.

Package export:

~~~text
backend/app/macro/__init__.py
~~~

에 R5R evaluator / binding public symbols를 연결했다.

---

## 4. Deterministic verification

추가 테스트:

~~~text
backend/tests/test_macro_r5r_evaluator_next6e.py

backend/tests/test_macro_r5r_binding_next6e.py
~~~

검증 범위:

- odd midpoint median
- even midpoint median
- ties
- MAD
- zero MAD fail-close
- exact ECDF sup distance
- exact T/L/S primitives
- minimum chronology
- window
- candidate collision
- first supported Common-N selection
- latest-state inclusion
- missing horizon fail-close
- exact rational boundary
- contract identity mismatch fail-close
- prebinding exclusion provenance
- invalid fractional BP rejection
- duplicate chronology rejection
- canonical chronology SHA-256 fixture
- binding contains no evaluation result

기존 frozen fixture:

~~~text
NEXT6E_S6A_R5R_DETERMINISTIC_FIXTURES_V1

NEXT6E_S6A_R5R_MUR3_BR1_TARGETED_FIXTURES_V1
~~~

를 사용했다.

---

## 5. G4 verification

코드 구현 완료 HEAD:

~~~text
a1e5eb7af4de3bbe4ff4eafdec6069e14197c4b7
~~~

GitHub CI:

~~~text
run
=
37391620961

status
=
COMPLETED

conclusion
=
SUCCESS
~~~

CI 범위:

- backend Python 3.11
- backend Python 3.14
- full backend pytest
- frontend Node 22 build
- Windows fresh-clone / setup verification

따라서:

~~~text
R5R-G4
=
PASS
~~~

로 기록한다.

---

## 6. Frozen DEV source

사용한 Library file:

~~~text
DEV-7c3f6660b3aae03f(1).json
~~~

Source file SHA256:

~~~text
7b1dfe33537bb8855b9441b2aeb24338a13950abf8cdc186b2821898d47313f4
~~~

Dataset:

~~~text
dataset_id
=
MACROCAL-DEV-7c3f6660b3aae03f

dataset_hash
=
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1
~~~

Contract:

~~~text
VN_NEXT6B_S2_CALIBRATION_DATASET_V1
~~~

Split:

~~~text
DEVELOPMENT
~~~

Usage:

~~~text
REFERENCE_RESEARCH_ONLY
~~~

Provider:

~~~text
FRED / DGS10
~~~

Series:

~~~text
US_10Y_CONSTANT_MATURITY_YIELD
~~~

Vintage:

~~~text
2023-12-29
~~~

Feature contract:

~~~text
VN_NEXT6B_S1_MACRO_FEATURE_V1
~~~

---

## 7. Dataset integrity

Dataset hash was independently recomputed from:

~~~text
manifest
+
row_hashes
~~~

using the existing StockScope canonical content-hash rule.

Result:

~~~text
recomputed dataset hash
=
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1

stored dataset hash
=
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1

MATCH
~~~

Source-file bytes also match the previously frozen SHA256.

---

## 8. Joint chronology binding

Source rows:

~~~text
1999
~~~

Rows excluded before binding:

~~~text
0
~~~

Joint rows:

~~~text
1999
~~~

Required feature set on every joint row:

~~~text
delta_bp_1obs
delta_bp_5obs
delta_bp_10obs
~~~

All bound feature values passed exact signed integer BP validation.

First bound observation date:

~~~text
2016-01-04
~~~

Last bound observation date:

~~~text
2023-12-28
~~~

Dataset manifest observation_end remains:

~~~text
2023-12-29
~~~

The binding uses the actual eligible row chronology, not the manifest range endpoint.

---

## 9. Joint chronology identity

Contract:

~~~text
R5R_JOINT_CHRONOLOGY_HASH_V1
~~~

SHA256:

~~~text
f2fa057b25e1ff9b2012b76f29f28b40627a4040a3dffa0e4c3b9b8ea430a62d
~~~

Chronology is unique and strictly ascending.

---

## 10. Structural binding

Joint n:

~~~text
1999
~~~

Window:

~~~text
w(n)
=
ceil(1999/10)
=
200
~~~

Effective approved anchors:

~~~text
200
300
400
500
600
700
800
900
1000
1100
1200
1300
1400
1500
1600
1700
1800
1900
~~~

Count:

~~~text
18
~~~

This is structural metadata only and does not reveal R5R adequacy results.

---

## 11. Binding artifact

Created:

~~~text
docs/bindings/
NEXT6E_R5R_EVALUATION_BINDING_V1.json
~~~

Binding ID:

~~~text
R5RBIND-b27cf5c12ab37aac
~~~

Binding hash:

~~~text
b27cf5c12ab37aac93a524387f47fbc4086b5d8d6ced75cd1bf211fea587a716
~~~

The artifact explicitly records:

~~~text
metrics_computed
=
false

reference_adequacy_evaluated
=
false

holdout_accessed
=
false

runtime_db_accessed
=
false

network_accessed
=
false
~~~

---

## 12. Limitations

The existing dataset limitation is preserved:

~~~text
HISTORICAL_TIME_NOT_PROVEN
~~~

It was not removed or upgraded.

The current R5R claim remains observed-path empirical stability only.

---

## 13. G1 result

Frozen DEV source identity:

~~~text
PASS
~~~

Dataset hash:

~~~text
PASS
~~~

Required identity fields:

~~~text
PASS
~~~

Joint eligibility:

~~~text
PASS
~~~

Chronology:

~~~text
PASS
~~~

Integer BP lattice:

~~~text
PASS
~~~

Chronology hash:

~~~text
FROZEN
~~~

Window / candidate structure:

~~~text
PASS
~~~

Therefore:

~~~text
R5R-G1
=
PASS
~~~

---

## 14. Access boundary

This stage accessed:

~~~text
Frozen DEV file
=
YES, identity/chronology binding only
~~~

Not accessed:

~~~text
Holdout
=
NO / LOCKED

runtime DB
=
NO

network data providers
=
NO

Production outcomes
=
NO
~~~

Not calculated:

~~~text
DEV T_EMP
DEV L_EMP
DEV S_EMP
candidate support
Common-N
Reference Adequacy result
~~~

---

## 15. Effective gate state

~~~text
R5R-G0
=
PASS

R5R-G1
=
PASS

R5R-G2
=
PASS

R5R-G3
=
PASS

R5R-G4
=
PASS
~~~

Therefore:

~~~text
R5R Reference Adequacy Evaluation
=
AUTHORIZED / NOT EXECUTED
~~~

---

## 16. Next task

~~~text
NEXT-6E-R5R-JEV
~~~

JEV will be the first stage that runs:

~~~text
frozen Method V2
+
frozen Policy V1
+
frozen DEV binding
+
verified evaluator
~~~

against the bound DEV rows.

Only there may the project inspect:

~~~text
T_EMP
L_EMP
S_EMP

per-anchor results

SUPPORTED / EXCEEDS / BLOCKED

OBSERVED_PATH_COMMON_N

overall SUPPORTED / NOT_SUPPORTED / BLOCKED
~~~

---

## 17. Policy discipline

JEV result must not retroactively change:

~~~text
tau_T = 0.10
tau_L = 0.50
tau_S = 0.25
~~~

simply because the result is inconvenient.

JEV is now an execution/evidence stage, not another threshold-design stage.

---

## 18. Final state

~~~text
NEXT-6E-R5R-IMPLEMENT
=
COMPLETE

Evaluator
=
IMPLEMENTED

Deterministic verification
=
PASS

DEV evaluation binding
=
FROZEN

R5R-G1
=
PASS

R5R-G4
=
PASS

Reference Adequacy
=
AUTHORIZED / NOT EXECUTED

Next
=
NEXT-6E-R5R-JEV
~~~
