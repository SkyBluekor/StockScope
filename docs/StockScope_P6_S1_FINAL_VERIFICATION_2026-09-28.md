# StockScope P6-S1 Final Verification — 2026-09-28

## 1. Final Decision

**VN-P6-S1: COMPLETE**

P6-S1의 Event Evidence 기반 구조, 품질 검증, 과거 반응 평가, 증분 가치 Gate, 최소 제품 통합, Backup/Restore, Regression, Browser UAT까지 완료했다.

이 완료 판정은 **뉴스 기반 주가 방향 예측 완료**를 의미하지 않는다.

현재 제품 상태:

- Event Evidence infrastructure: 구현 완료
- Reference product integration: 구현 완료
- Real historical event corpus: 없음
- Incremental value demonstrated on real corpus: 아님
- Prediction: 미출시
- Prediction probability/direction: 미제공
- Automatic Strategy integration: 미출시
- Scanner integration: 없음
- Holdings/Watch integration: 없음

Scanner baseline은 **0.21.3.8**로 유지한다.

## 2. Product Boundary

P6-S1은 다음 경계를 유지한다.

- 최근 뉴스 목록은 참고 정보이며 Strategy, Scanner, Ranking, Risk 계산을 변경하지 않는다.
- P6 Event Evidence는 NEWS.1 검색 결과와 별도 계약으로 관리한다.
- 검증되지 않은 호재/악재, 상승/하락 방향, 확률, 목표가를 표시하지 않는다.
- Synthetic fixture 결과는 Production evidence 또는 Product PASS로 승격하지 않는다.
- P6-S1-F의 Value Gate V1은 prediction을 승인하지 않는다.
- P5 Strategy Governance와 P6 Event Evidence Governance는 독립 상태를 유지한다.
- StockScope는 실제 매수·매도 주문을 실행하지 않는다.

## 3. Implementation Summary

### P6-S1-A — Source Rights + Temporal Contract

완료.

- source capability 계약
- fail-closed rights policy
- source/available/fetched/corrected time provenance
- EXACT / PROVIDER_TIME / DATE_ONLY / INFERRED / UNKNOWN 구분
- historical evaluation 시간 적격성 분리
- Naver/OpenDART의 P6 research 권한을 기존 display path에서 자동 승계하지 않음

### P6-S1-B — Immutable Event Evidence Store

완료.

- immutable policy snapshot / SourceRef / Event revision
- deterministic source bundle/event hash
- append-only revision chain
- raw article/document body 저장 금지
- migration idempotency
- historical/news/DART backfill 0
- external network requests 0

### P6-S1-C — Entity / Dedup / Correction

완료.

- listed-company entity identity
- Event↔Entity relevance
- canonical event resolution
- duplicate/correction identity 보존
- as-of semantics 유지
- uncertain duplicate를 임의 합치지 않음

### P6-S1-D — Evidence Quality

완료.

Quality는 숫자 점수가 아니라 다음 gate 상태로 유지한다.

- USABLE
- LIMITED
- INSUFFICIENT
- BLOCKED

REFERENCE와 HISTORICAL_EVALUATION scope를 분리한다.

### P6-S1-E — Historical Event Evaluation

완료.

관찰 window:

- +1 trading session
- +5 trading sessions
- +20 trading sessions

Reference price는 **PREVIOUS_CONFIRMED_DAILY_CLOSE**를 사용한다.

측정값:

- stock return
- market return
- market-adjusted observed return

이 값은 causal event effect로 해석하지 않는다.

### P6-S1-F — Incremental Value Gate

완료.

Decision state:

- PASS
- HOLD
- FAIL
- BLOCKED

Production 기본 Gate는 criteria 미승인 상태이며 fail-closed 한다.

현재 real corpus가 없으므로 Production 측면에서 incremental value는 **입증되지 않은 상태**다.

P6-S1-F V1:

- prediction_eligible = false
- Strategy activation 없음
- Scanner 변경 없음
- Risk Gate 변경 없음
- Holdings/Watch 변경 없음

Synthetic fixture는 PASS/FAIL 엔진 검증에만 사용한다.

### P6-S1-G — Minimal Product Integration

완료.

신규 read-only endpoint:

`GET /api/stocks/{code}/event-evidence?market=KOSPI`

Product Query는 Simulation DB를 read-only로 조회한다.

현재 real P6 evidence가 없을 때 정상 product state:

- event_evidence.status = NO_VALIDATED_EVIDENCE
- reference_count = 0
- value_validation.status = NOT_EVALUATED
- product_scope = RESEARCH_ONLY
- prediction.status = NOT_VALIDATED
- direction = null
- probability = null

StockNewsPanel full view에서만 P6 상태를 표시한다.

Scanner/Holdings의 compact NEWS.1 view에는 P6 product state를 추가하지 않는다.

## 4. Persistent State and Migration

Local P6 migration은 최종 H 검증 전에 성공적으로 완료되었다.

최종 확인된 local P6 count:

- policy_snapshot_count: 0
- source_ref_count: 0
- event_evidence_count: 0
- entity_count: 0
- relevance_count: 0
- canonical_group_count: 0
- resolution_count: 0
- quality_assessment_count: 0
- evaluation_protocol_count: 0
- outcome_observation_count: 0
- control_match_count: 0
- evaluation_report_count: 0
- value_gate_protocol_count: 0
- value_gate_decision_count: 0

또한:

- historical_backfill_performed: false
- news_backfill_performed: false
- dart_eventrisk_backfill_performed: false
- external_network_requests: 0
- real_corpus_evaluation_performed: false

Zero counts는 real P6 corpus가 승인·수집되지 않았기 때문에 정상이다.

## 5. Backup / Restore Verification

P6-S1-H에서 backup manifest extension을 추가했다.

`event_evidence_v1`

최종 로컬 백업:

`D:\Projects\StockScope\backups\StockScope_20260928T075637Z`

Backup 결과:

- Holdings DB: PASS
- Integrity: PASS
- Foreign Keys: PASS
- Domain Check: PASS
- Simulation DB: AUTO
- Tracking DB: AUTO
- Secrets: EXCLUDED
- Manifest: PASS

최종 local `event_evidence_v1` manifest:

- present = true
- restorable = true
- prediction_enabled = false
- 모든 P6 row count = 0
- 모든 contract version이 현재 A-F 코드 계약과 일치

Manifest에 포함된 P6 persistent tables:

1. event_evidence_schema_meta
2. event_evidence_policy_snapshot
3. event_evidence_source_ref
4. event_evidence_record
5. event_evidence_record_source
6. event_evidence_entity
7. event_evidence_entity_relevance
8. event_evidence_canonical_group
9. event_evidence_resolution
10. event_evidence_quality_assessment
11. event_evidence_evaluation_protocol
12. event_evidence_outcome_observation
13. event_evidence_control_match
14. event_evidence_evaluation_report
15. event_evidence_value_gate_protocol
16. event_evidence_value_gate_decision

Automated synthetic backup/restore lifecycle은 restore 전후 다음 대표 immutable hash가 동일함을 검증한다.

- source_ref_hash
- event_hash
- entity_hash
- relation_hash
- reference quality_hash
- historical quality_hash
- report_hash
- decision_hash

부분 P6 migration은 backup publication을 차단한다.

Manifest/database 불일치는 restore가 target을 변경하기 전에 차단한다.

## 6. Final Regression

H.1-H.3 최종 CI:

- Frontend / Node 22: PASS
- Backend / Python 3.11: **1307 passed, 1 warning**
- Backend / Python 3.14: **1307 passed, 1 warning**
- CI run: **#1217 SUCCESS**
- PR #8: OPEN / mergeable

Final lifecycle regression:

Migration
→ Source/Policy
→ Event
→ Entity/Relevance
→ Quality
→ Historical Evaluation
→ Evaluation Report
→ Value Gate
→ Product Query
→ Backup
→ Restore
→ Product Query equivalence

## 7. Browser UAT

### 7.1 Stock Analysis — Dark Mode

**PASS**

확인 사항:

- 기존 NEWS.1 기사 목록 정상
- `검증된 이벤트 근거 없음 · 방향 예측 미제공` 정상 표시
- `뉴스·이벤트 근거 범위 보기` 정상 확장
- Recent News / Event Evidence / Product Value / Direction Prediction 의미 구분 가능
- positive/negative event badge 없음
- prediction probability 없음
- UP/DOWN direction 없음
- 새 prediction card 없음
- 레이아웃 깨짐 없음

### 7.2 Stock Analysis — Light Mode

**PASS**

로컬 브라우저 캡처에서 확인:

- P6 상태 문구 가독성 정상
- details 위계 정상
- NEWS.1 카드 가독성 정상
- P6로 인한 overlap/clipping 없음
- 호재/악재 예측 색상 추가 없음
- 기존 light theme 흐름 유지

### 7.3 Rapid Stock Switching

**PASS**

Samsung Electronics → SK hynix → Samsung Electronics 빠른 전환에서 이전 종목의 뉴스/Event Evidence 상태가 새 종목 아래에 남지 않았다.

실제 브라우저에서도 AbortController + request identity guard가 정상 동작했다.

### 7.4 Holdings Compact NEWS.1 Boundary

**PASS**

로컬 Holdings 화면에서 compact StockNewsPanel은 기존 최근 뉴스만 유지했다.

다음 P6 full-view 내용은 Holdings compact view에 노출되지 않았다.

- validated event-evidence state
- product value validation
- direction prediction state

따라서 P6-S1-G가 Holdings/Watch 통합으로 확장되지 않았음을 확인했다.

### 7.5 Narrow Viewport

별도의 mobile/narrow manual capture는 최종 closeout에서 추가 요구하지 않았다.

Frontend build/regression은 green이며 제공된 브라우저 캡처에서 P6 integration으로 인한 layout 문제는 관찰되지 않았다. 별도 mobile-layout redesign은 P6-S1 범위 밖이다.

## 8. Final Safety / Governance Verification

최종 상태:

- Naver NEWS.1 display remains independent
- Naver AI transform remains disallowed by current source policy
- P6 real corpus ingestion: not enabled
- automatic historical backfill: not enabled
- external network work during migration/evaluation: 0
- synthetic evidence shown as product evidence: no
- synthetic PASS converted to Production PASS: no
- prediction direction shown: no
- prediction probability shown: no
- automatic Strategy weight change: no
- Scanner change: no
- Risk Gate change: no
- Holdings plan rewrite: no
- Watch rule mutation: no
- brokerage order execution: no

## 9. Final P6-S1 Status

**VN-P6-S1 COMPLETE**

Completed scope:

- rights/time contract
- immutable evidence ledger
- entity/relevance/dedup/correction
- evidence quality
- historical outcome evaluation framework
- incremental-value governance gate
- minimal read-only product integration
- persistent-state migration
- backup/restore manifest and integrity verification
- full regression
- dark/light browser UAT
- rapid stock-switch UAT
- compact-view boundary UAT

Explicitly deferred:

- approved real historical corpus
- real-corpus incremental-value demonstration
- prediction model
- probability calibration
- direction/horizon prediction product
- automatic Strategy/Scanner integration
- Holdings/Watch event integration

향후 P6 evidence를 Strategy scoring이나 Production selection에 사용하려면 기존 P5 governance를 계속 따라야 한다.

**Evidence → Proposal → Approval → Explicit Production Policy → Run Pin**

P6-S1 completion은 이 계약을 우회하지 않는다.
