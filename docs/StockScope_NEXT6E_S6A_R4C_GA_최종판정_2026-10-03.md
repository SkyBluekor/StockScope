# StockScope NEXT-6E-S6A-R4C — Formal Clean Replay & G-A Final Decision

작성일: 2026-10-03, Asia/Seoul  
구현 기준 main: `15a001d83779072b7e007c8d16fc0d6e82bf5eca`  
Stage: `NEXT-6E-S6A-R4C`

## 1. 현재 상태

R4C 실행 계약과 two-phase runner를 구현한다.

현재 실제 project approval artifact는 제공되지 않았으므로 본 문서의 execution state는 다음으로 유지한다.

```text
R4C implementation
IN PROGRESS / TARGET COMPLETE AFTER CI

Formal Phase A clean replay
NOT EXECUTED

TheoremReviewDossier
NOT PROVIDED

ModelUseDossier
NOT PROVIDED

G-A
BLOCKED

Execution state
WAITING_FOR_EXTERNAL_APPROVAL
```

본 구현 작업 자체를 clean replay로 취급하지 않는다.

## 2. Canonical R4C route

```text
CleanReplayAttestation
→ Phase A explicit DEV diagnostic
→ sealed diagnostic_hash/source_scope_hash
→ external approval binding
→ Phase B GateAssessment
→ G-A final decision
```

기존 `analyze_macro_r4_dev_assumptions.py`는 R4 development diagnostic 도구로 유지한다.

Formal R4C route는:

```text
tools/data/run_macro_r4c_clean_replay.py
```

이다.

## 3. Phase A

Phase A는 clean attestation을 먼저 검증한 뒤에만 명시적으로 전달된 Development artifact를 연다.

금지:

- directory discovery / glob;
- replacement Development;
- network retrieval;
- runtime DB;
- Holdout의 모든 접근;
- Development adequacy output;
- multiplier simulation;
- Reference Adequacy.

Phase A 성공 시 다음 sealed identity가 생성된다.

```text
diagnostic_hash
source_scope_hash
clean_attestation_hash
Phase A payload hash
```

A5/A6/G1 approval은 Phase A에서 생성하지 않는다.

## 4. CleanReplayAttestation

Schema:

```text
NEXT6E_S6A_R4C_CLEAN_REPLAY_ATTESTATION_V1
```

Template:

```text
docs/templates/NEXT6E_R4C_CLEAN_REPLAY_ATTESTATION_TEMPLATE.json
```

Template 자체는 clean execution 증거가 아니다.

실제 attestation에는 nonblank operator/reference와 exact explicit DEV transport SHA-256이 필요하며 다음 값은 모두 false여야 한다.

```text
network_accessed
runtime_db_accessed
directory_discovery_performed
replacement_dev_used
holdout_accessed
adequacy_outputs_accessed
```

## 5. Approval checkpoint

Phase A 이후 상태는 다음 네 종류만 허용한다.

```text
WAITING_FOR_THEOREM_APPROVAL
WAITING_FOR_MODEL_USE_APPROVAL
APPROVAL_BINDING_INVALID
READY_FOR_PHASE_B
```

사람의 승인을 기다리는 상태는 implementation failure가 아니다.

## 6. Phase B

Phase B는 DEV를 다시 읽거나 diagnostic을 다시 계산하지 않는다.

입력:

1. sealed Phase A result;
2. approved TheoremReviewDossier;
3. approved ModelUseDossier.

Phase A payload 및 embedded diagnostic/source-scope hash를 재검증한다.

Tampering이면:

```text
SEALED_EVIDENCE_HASH_MISMATCH
```

로 종료한다.

두 dossier가 exact hash/version에 결속되고 validator PASS인 경우에만 final GateAssessment를 생성한다.

## 7. G-A semantics

모든 gate가 PASS하면:

```text
G-A
PASS

Method state
METHOD_APPROVED_CONDITIONAL_ON_DECLARED_MODEL
```

이어도:

```text
downstream_execution_authorized
false

G-B
NOT_STARTED

Reference Adequacy
UNRESOLVED

V4
NOT CREATED

Evaluator
NOT IMPLEMENTED

Production impact
NONE
```

을 유지한다.

## 8. 현재 실제 disposition

실제 theorem/model-use approval이 없고 본 구현 채팅은 formal clean execution context로 재분류하지 않는다.

따라서 현재 실제 상태:

```text
Phase A
NOT EXECUTED

G0
NOT EXECUTED

A5
UNRESOLVED

A6
UNRESOLVED

G1
BLOCKED

G-A
BLOCKED

G-B
BLOCKED

Reference Adequacy
UNRESOLVED

Holdout accessed
NO

Production impact
NONE
```

실제 승인 artifact가 제공된 별도 clean execution에서만 Phase A/Phase B evidence를 생성하고 이 문서의 disposition을 갱신한다.
