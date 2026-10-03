# StockScope NEXT-6E-S6A-R4A — 승인 Blocker 해소 및 G-A 재판정 준비

작성일: 2026-10-03, Asia/Seoul  
기준 main: `69395fbff0fdc445156609e83329a74d91aeb4a3`  
작업 성격: R4 이후 승인 blocker 해소. Reference Adequacy / V4 / evaluator / Production 실행이 아니다.

## 1. 결론

R4A에서 A10 legacy profile 불일치의 원인을 확정했다.

```text
classification
REFERENCE_SPEC_TRANSCRIPTION_ERROR_LOG_BASE

historical R3 selector
NATURAL_LOG

canonical npcp selector
LOG10
```

R2 문서는 lag selector를 `log n`으로 기록했지만, R2가 authority로 지정한 CRAN `npcp` reference implementation은 `log10(n)`을 사용한다.

Canonical implementation evidence:

```text
repository
cran/npcp

commit
d602c9b50730560c947fb776bfd3c7b4f4905bf8

path
R/lnOpt.R

blob
b9c92dcf245106b0a122035214e269a05fbe392f

Lval formula
kn       = max(5, ceiling(log10(n)))
lagmax   = ceiling(sqrt(n)) + kn
rho.crit = 1.96 * sqrt(log10(n)/n)
```

과거 R3 기록은 immutable historical evidence로 유지한다. 과거 값을 새 canonical 값으로 덮어쓰지 않는다.

## 2. Exact DEV reproduction

입력:

```text
dataset_id
MACROCAL-DEV-7c3f6660b3aae03f

dataset_hash
7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1

n
1999
```

### 2.1 Canonical npcp log10 profile

```text
k_n
5

lag_max
50

rho_crit
0.0796452942827935

coordinate m
[1, 5, 21]

lag cutoff L
10

bandwidth b
22

effective ell
43
```

### 2.2 Historical natural-log profile

```text
k_n
8

lag_max
53

rho_crit
0.120855930272575

coordinate m
[1, 5, 10]

lag cutoff L
10
```

이 값은 R3 historical record의:

```text
k_n=8
lag_max=53
rho_crit=0.120855930272575
coordinate m=[1,5,10]
```

을 정확히 설명한다.

따라서 ACF normalization이나 DEV 데이터 차이를 원인으로 둘 필요가 없다.

## 3. A10 처리

R4 이전 구현은 historical `[1,5,10]`과 다르면 전체 A10을 막았다.

이 방식은 R4 blocker-resolution design의 의미와 맞지 않는다.

A10의 새 의미는:

```text
GAUSSIAN_COVARIANCE_MULTIPLIER_SPAN_ENVELOPE
```

의 symbolic method contract다.

Legacy R2 profile은:

```text
LEGACY_REPRODUCTION_ONLY
```

로만 남는다.

R4A 변경:

1. canonical legacy expected profile을 exact npcp `log10` 구현에 결속한다.
2. historical natural-log variant도 함께 계산하여 과거 record provenance를 검증한다.
3. historical mismatch 자체를 A10 failure로 사용하지 않는다.
4. canonical npcp reproduction이 깨지면 `LEGACY_R2_CANONICAL_MISMATCH`로 fail-close한다.
5. 새 span-envelope contract의 exact symbolic fields가 깨지면 `CALIBRATION_CONTRACT_INVALID`로 fail-close한다.
6. real Gaussian draw, covariance factorization, critical value, confidence band는 여전히 S6C 범위다.

현재 code-level A10 disposition:

```text
A10 symbolic contract
PASS-ELIGIBLE

legacy historical discrepancy
RESOLVED / INFORMATIONAL

S6C numerical approval
NOT GRANTED
```

## 4. G1 theorem review 준비 상태

검토한 primary source:

Bücher & Kojadinovic (2016), *A dependent multiplier bootstrap for the sequential empirical copula process under strong mixing*, Bernoulli 22(2), 927-968, arXiv:1306.3930 v4.

Primary theorem facts used by the R4 design:

- dependent multiplier sequence requires stationarity, mean 0, variance 1 and sample independence;
- a bandwidth/dependence span sequence `ell_n -> infinity` with finite dependence;
- Theorem 2.1 assumes `ell_n=O(n^(1/2-epsilon))`;
- for dimension `d=3`, the strong-mixing requirement `a > 3 + 3d/2` is exactly `a > 15/2`;
- the theorem gives joint weak convergence with independent multiplier copies.

### D1

Status:

```text
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

The source theorem itself is stated for continuous margins. R4's randomized-PIT lattice restriction is a StockScope derivation, not a sentence copied from the source theorem. The algebraic identity and mixing-preservation argument therefore still require the designated theorem reviewer.

### D2

Status:

```text
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

The witness-span argument uses one deterministic admissible sequence, e.g. `floor(n^(1/5))`, and the pointwise fact that the max over all spans cannot be smaller than that witness root. The resulting conservative-envelope transfer is a StockScope proof construction and requires independent review.

No claim is made that every `ell in {1,...,n}` satisfies the asymptotic theorem.

### D3

Status:

```text
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

The simultaneous CDF band is a deterministic mapping from the approved sequential sup event. Boundary clipping is in probability space only; unobserved value tails remain unbounded.

### D4

Status:

```text
TECHNICAL_REVIEW_READY
FORMAL_APPROVAL_MISSING
```

Median-set and center-aware MAD intervals are deterministic outer mappings from the CDF event. They are project derivations and still require theorem-review approval.

### G1

No designated reviewer identity or approval reference was supplied.

Therefore:

```text
G1
BLOCKED

reason
THEOREM_REVIEW_DOSSIER_MISSING
```

The implementation must not convert this technical desk review into `APPROVED`.

## 5. A5 / A6 model-use status

No valid ModelUseDossier with actual:

- model owner;
- method reviewer;
- approval authority/reference;
- exact scope approval;
- contradiction dispositions;
- validity/revocation rules

was supplied.

Therefore:

```text
A5
UNRESOLVED

A6
UNRESOLVED
```

No identity or approval is invented.

R4A hardens validation so blank owner/reviewer/authority/approval fields cannot produce a PASS. Nested stationarity/dependence payloads are also closed-schema validated.

## 6. Formal clean replay

This conversation cannot be reclassified as a clean execution context because prohibited adjacent metadata had been surfaced earlier in the conversation history.

Therefore the formal clean replay is:

```text
NOT EXECUTED
```

not failed due to Development data, and not PASS.

A future clean replay must start from an isolated execution context with only:

1. exact frozen DEV JSON;
2. exact MethodDesignManifest;
3. approved ModelUseDossier;
4. approved TheoremReviewDossier.

It must not inspect or search for prohibited sources or adequacy outcomes.

## 7. Current gate state after R4A

```text
A10
PASS-ELIGIBLE AFTER CANONICAL REPRODUCTION

A5
UNRESOLVED

A6
UNRESOLVED

G1
BLOCKED

G0 formal clean replay
NOT EXECUTED

G-A
BLOCKED

Method state
DESIGN/IMPLEMENTATION COMPLETE
APPROVAL INCOMPLETE

G-B
BLOCKED

Reference Adequacy
UNRESOLVED

V3
UNCHANGED

V4
NOT CREATED

Evaluator
NOT IMPLEMENTED

Production impact
NONE
```

## 8. Code changes

R4A changes are limited to:

- canonical npcp legacy-reference provenance;
- historical natural-log reproduction evidence;
- A10 gate separation between legacy audit and new span-envelope contract;
- stronger ModelUseDossier validation;
- stronger TheoremReviewDossier validation;
- focused regression tests.

No real multiplier replicate, Reference Adequacy, V4, evaluator, runtime DB, Holdout or Production behavior is introduced.

## 9. Next blocker

The next substantive work is not G-B.

Required order remains:

```text
designated theorem review / G1
+
actual model-use owner/reviewer approval for A5/A6
+
fresh isolated clean replay / G0
-> G-A final decision
```

Until those external governance inputs exist, repeated code reruns cannot legitimately promote G-A.
