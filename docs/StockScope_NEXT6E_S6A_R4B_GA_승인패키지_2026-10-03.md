# StockScope NEXT-6E-S6A-R4B — G-A 승인 패키지 및 Clean Replay 준비

작성일: 2026-10-03, Asia/Seoul  
기준 main: `d853eaf82dad3fbd7369cb865810ff4bbd7e3b8d`  
Stage: `NEXT-6E-S6A-R4B`  
Method: `NEXT6E_S6A_R4_LATTICE_CDF_PROJECTION_V1`  
Target: `JOINT_SEQUENTIAL_CDF_AND_FUNCTIONAL_ERROR_COVERAGE_V1`  
Design hash: `874c3387b54bdeff6701f1ca7b72469cfda158fb588a2b366c2d799754dc2a18`

## 1. 목적

R4B는 G-A를 자동 승인하는 단계가 아니다.

R4A에서 A10 provenance blocker는 해소되었다. 현재 남은 blocker는 실제 외부 검토가 필요한 G1 theorem review와 A5/A6 model-use approval, 그리고 그 승인 결과를 exact clean diagnostic hash에 결속한 뒤 수행할 G0 clean replay다.

R4B의 완료 조건은 다음이다.

```text
Theorem review packet     COMPLETE
Model-use review packet   COMPLETE
Unapproved templates      COMPLETE
Approval preflight        COMPLETE
Clean replay handoff      COMPLETE

Actual G1 approval        NOT CREATED
Actual A5/A6 approval     NOT CREATED
Formal clean replay       NOT EXECUTED
G-A                       BLOCKED
```

## 2. 승인 artifact와 review package의 구분

다음 세 종류를 엄격히 구분한다.

### Review package

검토자가 판단하기 위한 설명·증거·질문 목록이다.

```text
review package != approval
```

### Template

schema와 필요한 필드를 보여주는 미승인 입력 양식이다.

```text
template status
UNRESOLVED
```

Template을 그대로 validator에 넣어도 PASS하면 안 된다.

### Final approval artifact

실제 reviewer/owner identity, approval reference, exact hash binding이 존재하고 validator를 통과한 객체다.

R4B에서는 final approval artifact를 생성하지 않는다.

## 3. G1 — D1 review packet

### Claim

R4의 관측 lattice indicator process를 continuous-margin dependent multiplier theorem에 연결하기 위해 proof-only distributional transform을 사용한다.

```text
U_ih
=
F_h(X_i^h-)
+
V_ih {F_h(X_i^h)-F_h(X_i^h-)}

V_ih ~ Uniform(0,1)
```

그 결과 lattice threshold에서:

```text
1{X_i^h <= x}
=
1{U_ih <= F_h(x)}
```

를 사용한다.

### 반드시 확인할 사항

- V/U는 proof-only auxiliary variable이다.
- 구현에서 V/U를 생성·저장·추정하지 않는다.
- raw X, ties, median, MAD를 바꾸지 않는다.
- randomized empirical ranks 또는 jitter로 사용하지 않는다.
- 독립 V 확장 후 stationarity가 보존되는 논리가 타당한지 검토한다.
- measurable mapping 후 mixing rate가 악화되지 않는다는 연결을 검토한다.
- joint horizon restriction이 source theorem의 약수렴 결과에서 정당한지 검토한다.
- full-sample empirical centering이 실제 raw indicator multiplier process와 일치하는지 검토한다.

### Reviewer disposition

```text
D1
APPROVED / REJECTED / UNRESOLVED
```

현재:

```text
D1
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

## 4. G1 — D2 review packet

### Claim

새 calibration은 하나의 data-selected bandwidth를 승인하지 않는다.

```text
Lambda_n
=
{1,...,n}
```

모든 span에 대해 covariance-Parzen multiplier root를 정의하고:

```text
R*_env
=
max over ell in Lambda_n R*_ell
```

을 사용한다.

### Proof witness

```text
ell_n^0
=
floor(n^(1/5))
```

은 실제 선택 bandwidth가 아니다.

목적은 admissible deterministic witness sequence 하나가 `Lambda_n` 안에 존재함을 이용하는 것이다.

검토할 핵심:

1. `ell_n^0 -> infinity`.
2. 적절한 epsilon에 대해 `ell_n^0=O(n^(1/2-epsilon))`.
3. 모든 replicate에서 `R*_env >= R*_(ell_n^0)`.
4. 따라서 corresponding conditional critical quantile이 witness critical quantile보다 작아지지 않는지.
5. 이 논리로 얻는 결과가 exact nominal coverage가 아니라 conservative liminf coverage임을 유지하는지.
6. 모든 `ell=1..n`이 theorem-valid하다고 주장하지 않는지.
7. 일부 span을 생략한 작은 maximum을 반환하지 않는지.
8. PSD/factorization failure에서 ridge/eigenvalue clipping을 자동 수행하지 않는지.

### Reviewer disposition

```text
D2
APPROVED / REJECTED / UNRESOLVED
```

현재:

```text
D2
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

## 5. G1 — D3 review packet

D2의 simultaneous root event에서:

```text
epsilon_k
=
c_env(alpha) sqrt(n) / k
```

를 사용한다.

CDF band:

```text
L_h,k(x)
=
max(0,Fhat_h,k(x)-epsilon_k)

U_h,k(x)
=
min(1,Fhat_h,k(x)+epsilon_k)
```

검토할 핵심:

- 하나의 simultaneous event가 모든 horizon/prefix를 보호하는가.
- probability-space clipping과 value-support clipping을 혼동하지 않는가.
- unobserved value tails를 관측 min/max로 잘라내지 않는가.
- alpha는 symbolic input으로 남는가.
- R4B에서 real critical value/Monte Carlo를 계산하지 않는가.

현재:

```text
D3
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

## 6. G1 — D4 review packet

### Median

```text
q^-_G(p)
=
inf{x:G(x)>=p}

q^+_G(p)
=
inf{x:G(x)>p}

M(G)
=
[q^-_G(1/2),q^+_G(1/2)]
```

관측 scalar median은 두 endpoint의 midpoint를 사용한다.

### MAD

median uncertainty interval `I_m=[a,b]`를 먼저 만든 뒤 center radius:

```text
r_m
=
max(|a-mhat|,|b-mhat|)
```

를 사용한다.

관측 center 기준 absolute deviation ECDF `G_D`에 대해 CDF error가 `2e`까지 확대될 수 있음을 반영하고:

```text
I_d
=
[max(0,a_D-r_m), b_D+r_m]
```

를 사용한다.

검토할 핵심:

- `>=`와 `>` quantile endpoint 차이가 유지되는가.
- even-sample midpoint convention이 기존 statistic과 동일한가.
- nonunique median을 failure로 바꾸지 않는가.
- estimated-center uncertainty가 빠지지 않는가.
- MAD CDF transfer에서 `2e`를 `e`로 축소하지 않는가.
- zero/infinite endpoint를 그대로 fail-close/uncertainty 상태로 유지하는가.
- later common-N selection이 이미 simultaneous event에 포함된 index 위에서만 수행되는가.

현재:

```text
D4
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

## 7. G1 승인 조건

TheoremReviewDossier는 다음 exact design에 결속한다.

```text
method_id
NEXT6E_S6A_R4_LATTICE_CDF_PROJECTION_V1

design_hash
874c3387b54bdeff6701f1ca7b72469cfda158fb588a2b366c2d799754dc2a18
```

필수:

```text
D1 APPROVED
D2 APPROVED
D3 APPROVED
D4 APPROVED

reviewer_identity nonblank
approval_reference nonblank
unresolved_objections = []
status = APPROVED
```

하나라도 없으면:

```text
G1
BLOCKED
```

Template:

`docs/templates/NEXT6E_R4_THEOREM_REVIEW_TEMPLATE.json`

Template은 의도적으로 모든 proof unit이 `UNRESOLVED`다.

## 8. A5 — strict stationarity review packet

A5가 요구하는 것은 finite sample proof가 아니다.

검토 대상:

```text
Z_i
=
(X_i^1,X_i^5,X_i^10)
```

에 대해 승인 scope 전체에 하나의 invariant joint law를 working model로 사용하는 것이 허용되는지다.

### Evidence to inspect

- exact DEV lineage 및 source definition.
- feature construction과 native chronology.
- 10개의 고정 non-overlapping chronological bins.
- 각 bin의 empirical CDF, median set/midpoint, raw MAD, frequency structure.
- bin-vs-full CDF sup distance.
- raw-coordinate lag covariance.
- support-threshold indicator lag covariance.
- cross-horizon covariance/overlap structure.

이 값들은 INFORMATIONAL이다.

R4B는 stationarity p-value, break cutoff, custom stability score를 추가하지 않는다.

### Reviewer questions

1. approved scope 전체에 하나의 invariant joint law를 working model로 사용하는가?
2. source definition 또는 measurement convention 변경이 있는가?
3. known structural contradiction이 있는가?
4. finite diagnostics의 반대 신호를 어떻게 disposition 했는가?
5. 어떤 사건에서 approval을 revoke하는가?

A5는 실제 owner/reviewer approval이 없으면:

```text
UNRESOLVED
```

이다.

## 9. A6 — dependence / limit-root review packet

요구 condition:

```text
alpha_Z(r)
=
O(r^-a)

exists a > 15/2
```

finite sample에서 a를 추정해 proof했다고 표시하지 않는다.

### Evidence to inspect

- joint temporal dependence rationale.
- raw/indicator lag covariance.
- horizon overlap 및 cross-horizon dependence.
- long-memory/regime-persistence objections.
- selected working-model basis.
- nondegenerate Gaussian root applicability.
- critical-quantile continuity applicability.

### Reviewer questions

1. alpha-mixing working model을 사용할 근거는 무엇인가?
2. required rate class가 approved scope에서 허용 가능한 assumption인가?
3. long-memory 또는 persistent regime 반대 근거가 있는가?
4. 반대 근거를 어떻게 disposition 했는가?
5. Gaussian root degeneracy 가능성은 검토됐는가?
6. critical-quantile continuity 사용 근거는 무엇인가?
7. 어떤 조건에서 approval을 revoke하는가?

finite ACF 또는 historical `ell=43`은 승인 근거가 아니다.

A6는 실제 approval 없이는:

```text
UNRESOLVED
```

이다.

## 10. ModelUseDossier binding

Template:

`docs/templates/NEXT6E_R4_MODEL_USE_TEMPLATE.json`

중요한 차이:

TheoremReviewDossier는 design hash에 결속할 수 있으므로 clean diagnostic 전에 formal review가 가능하다.

ModelUseDossier는:

```text
diagnostic_hash
source_scope_hash
```

에 결속해야 한다.

따라서 template의 두 필드는 placeholder이고 approval artifact가 아니다.

## 11. Clean replay two-phase protocol

### Phase A — isolated diagnostic

입력은 다음만 허용한다.

```text
Explicit exact frozen DEV
Exact MethodDesignManifest
Clean input allowlist
Clean isolation attestation
```

출력:

```text
DevAssumptionDiagnostic
diagnostic_hash
source_scope_hash
```

Phase A에서는 ModelUseDossier가 아직 clean diagnostic hash에 결속되지 않았으므로 G-A PASS를 만들지 않는다.

### Phase B — approval binding and gate assessment

Phase A의 exact:

```text
diagnostic_hash
source_scope_hash
```

를 승인된 ModelUseDossier에 결속한다.

TheoremReviewDossier는 exact design hash에 결속한다.

그 뒤에만 GateAssessment를 생성한다.

## 12. Formal replay input allowlist

최종 gate assessment 단계의 허용 객체:

1. exact frozen DEV diagnostic identity produced in Phase A.
2. exact MethodDesignManifest.
3. exact approved ModelUseDossier.
4. exact approved TheoremReviewDossier.

금지:

- Holdout path lookup/existence/metadata/hash/count/date/content.
- directory glob 또는 path guessing.
- Development adequacy output.
- forward envelope.
- passing candidate.
- recommended support.
- Production result.
- runtime DB.
- replacement/fresh-downloaded DEV.
- source window/segment post-selection.

## 13. Approval preflight

R4B는 다음 CLI를 제공한다.

```text
tools/data/preflight_macro_r4_approval.py
```

이 도구는:

- DEV를 읽지 않는다.
- Holdout을 읽지 않는다.
- DB/runtime을 읽지 않는다.
- network를 사용하지 않는다.
- directory scan을 하지 않는다.
- approval을 생성하지 않는다.
- clean replay를 실행하지 않는다.

역할은 supplied dossier가 현재 contract validator 기준으로 어떤 상태인지 확인하는 것이다.

### No dossier example

```text
python tools/data/preflight_macro_r4_approval.py
```

정상 결과:

```text
Theorem review
BLOCKED

Model use
UNRESOLVED

Ready for external review
YES

Formal clean replay executed
NO

G-A
BLOCKED
```

### Bound dossier preflight

ModelUseDossier를 검사할 때는 반드시 Phase A에서 나온 expected hash를 CLI에 별도로 제공한다.

```text
python tools/data/preflight_macro_r4_approval.py \
  --theorem-review-dossier <path> \
  --model-use-dossier <path> \
  --expected-diagnostic-hash <exact Phase A hash> \
  --expected-source-scope-hash <exact Phase A hash>
```

expected hash를 공급하지 않고 ModelUseDossier를 넣으면:

```text
CLEAN_DIAGNOSTIC_BINDING_REQUIRED
```

로 unresolved 처리한다.

## 14. Current expected R4B completion state

R4B 완료 직후의 정상 state는:

```text
A10
RESOLVED / PASS-ELIGIBLE

Theorem review packet
COMPLETE

TheoremReviewDossier
UNAPPROVED TEMPLATE ONLY

A5/A6 review packet
COMPLETE

ModelUseDossier
UNAPPROVED TEMPLATE ONLY

Approval preflight
AVAILABLE

Formal clean replay
NOT EXECUTED

G0
NOT EXECUTED

G1
BLOCKED

A5
UNRESOLVED

A6
UNRESOLVED

G-A
BLOCKED

G-B
BLOCKED

Reference Adequacy
UNRESOLVED

V4
NOT CREATED

Evaluator
NOT IMPLEMENTED

Production impact
NONE
```

## 15. R4B 이후

실제 reviewer/owner approval을 확보한 뒤 다음 단계는:

```text
NEXT-6E-S6A-R4C
Formal Clean Replay & G-A Final Decision
```

R4C에서만 clean Phase A diagnostic, approval hash binding, final GateAssessment를 수행한다.

G-A PASS가 확인된 뒤에만 G-B를 진행한다.
