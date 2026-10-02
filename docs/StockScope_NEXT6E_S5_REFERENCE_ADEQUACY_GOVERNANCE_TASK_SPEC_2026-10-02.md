# StockScope NEXT-6E-S5 — Reference Adequacy Method & Risk-Budget Governance Review

## 1. 문서 상태 / 실행 단계

작성일: 2026-10-02 (Asia/Seoul)  
현재 단계: **SPEC ONLY — 다음 연구 작업 명세 작성**  
권장 실행 모델: **6.1 Sol**  
권장 추론 수준: **High**  
작업 유형: Research / Statistical Governance / Preregistration  
연구 lineage: **NEXT-6B-S4.2-B.1.6-R2.4**  
지정 기준 브랜치: `main`  
지정 기준 SHA: `1088f0994c9712a7a9b64dd852d9ecb36d4447d8`

명세 작성 시 로컬 `main`과 HEAD가 위 SHA인 것을 확인했다. 이것은 연구 실행, 원격 latest main 확인, 방법론 승인 또는 S5 COMPLETE의 근거가 아니다.

**이번 단계의 산출물은 이 작업 명세뿐이다.** 외부 문헌 조사, 기존 requirement의 전수 조사, 최종 연구 verdict, evaluator 구현, adequacy 계산, 테스트 실행, runtime 기록, 브랜치 생성, PR/CI/merge는 수행하지 않는다. 아래의 연구·검증·PR 절차는 후속 연구 실행 요청 이후의 요구사항이다.

## 2. 목적과 핵심 질문

NEXT-6E-S4의 `REFERENCE_ADEQUACY_UNRESOLVED`를 정당하게 해소할 방법과 독립적 정책 근거가 존재하는지 판단한다. blocker 해소 자체를 성공 조건으로 삼지 않는다.

### Q1. Statistic-specific dependence method

아래 통계를 함께 취급하면서 `STATIONARY_WEAK_DEPENDENCE` 가정 아래 사용할 automatic tuning rule을 Development 결과를 보지 않고 사전에 정당화할 수 있는가?

| 영역 | 대상 통계 | 최소 component 수 |
|---|---|---|
| TAIL | `ECDF_SUP_DISTANCE` | 3 horizons |
| MAD 위치 | `NORMALIZED_MEDIAN_SHIFT` | 3 horizons |
| MAD scale | `RELATIVE_MAD_SHIFT` | 3 horizons |

### Q2. Independent risk/error budget

다음 각각에 독립적이고 추적 가능한 requirement/source가 있는가?

- Family-wide confidence/error budget.
- TAIL acceptable movement.
- Normalized median shift tolerance.
- Relative MAD shift tolerance.

Development envelope, passing N 또는 candidate/signal/episode survival에서 숫자를 골라 요구사항으로 승격하는 것은 금지한다.

## 3. Start Conditions — 후속 연구 실행 요청 이후

1. 사용자에게 후속 연구 실행 요청을 받은 뒤 진행한다. 현재 SPEC ONLY 단계에서 연구 완료나 merge를 선언하지 않는다.
2. 적용되는 저장소 지침, `main` 상태, 원격 latest main을 확인한다. 위 지정 SHA와 차이가 있으면 commit 차이와 관련 계약 변경을 기록하고, 연구 기준을 조용히 바꾸지 않는다.
3. R2.3 preregistration 문서와 V3 protocol의 **정의·계약·lineage**를 확인한다. 문서에 Development 수치 결과가 섞여 있으면 결과 표/값을 열람하지 않는 범위로 읽는다.
4. 실제 연구 기준 SHA를 `<S5_RESEARCH_BASE_COMMIT_HASH>`에 기록한다. 지정 SHA는 비교 기준으로 보존한다.
5. 승인된 소스·문서 경로의 positive allowlist를 정한다. Holdout artifact가 존재하는지 알아내기 위한 탐색은 하지 않는다.
6. 연구 전용 브랜치 `research/next6e-s5-reference-adequacy-governance`를 사용한다. 같은 브랜치가 있으면 상태를 확인하고 기존 작업을 덮어쓰지 않는다.
7. 단계 순서를 다음과 같이 유지한다.

```text
외부/독립 근거 조사
→ 방법론 타당성 검토
→ governance source 검토
→ 정당화된 규칙만 문서에서 동결
→ preregistration verdict
```

연구 실행 중에도 evaluator 구현과 adequacy evaluation은 하지 않는다. 이들은 별도 다음 작업이다.

## 4. Frozen R2.3 / V3 출발 상태

아래는 사용자 요청에 주어진 출발 상태를 보존한 것이다. 이번 명세에서 새 값이나 판정을 부여하지 않는다.

```text
Primary method candidate = STATIONARY_BOOTSTRAP
Dependence assumption = STATIONARY_WEAK_DEPENDENCE
Assumption verified = NO
Automatic block selector = UNRESOLVED_STATISTIC_SPECIFIC_RULE
Manual block length = FORBIDDEN
Risk-budget source = NONE
Confidence/error budget = null
TAIL tolerance = null
MAD normalized median tolerance = null
MAD relative scale tolerance = null
Multiplicity scope = ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY
Standalone suffix K = ELIMINATED
Reference Adequacy = UNRESOLVED
minimum_prior_observations = null
recommended_support = null
RATE_SPIKE = UNCALIBRATED
```

현재 protocol `VN_NEXT6B_S4_2B16_REFERENCE_ADEQUACY_PROTOCOL_V3`는 수정하지 않는다. 새 규칙이 정당화되어도 문서의 frozen contract 초안까지만 작성하고, V4 preregistration은 별도 단계로 둔다.

## 5. 접근 범위와 결과 독립성

### Development

기존 artifact는 lineage/structure 확인만 허용한다. 다음 수치 결과는 inspection하거나 tuning에 사용하지 않는다.

```text
forward envelope 크기
passing N 분포
candidate survival
signal survival
episode survival
covered-year count
특정 horizon 결과
현재 reference adequacy evidence 값
```

수치 결과를 출력한 뒤 “판정에 사용하지 않았다”고 주장하는 것은 충분하지 않다. 열람 단계부터 결과를 차단한다. 이전 단계에서 결과가 존재했다는 사실은 이번 연구의 tuning 근거가 될 수 없다.

### Holdout

**절대 접근 금지.** read뿐 아니라 existence check, filename search, directory discovery, metadata, hash, row/sample count, date range를 확인하지 않는다. 접근 금지 경로를 찾기 위해 먼저 전체 runtime을 검색하는 방식도 금지한다.

승인된 코드·계약·문서만 대상으로 조사한다. 명세 및 연구 보고의 `Holdout accessed`는 실제 무접근에 근거해 `NO`여야 한다.

## 6. S5-A — Stationary Bootstrap 방법론 검토

`STATIONARY_BOOTSTRAP`은 primary candidate이며 자동 승인된 방법이 아니다. 아래 항목마다 원 논문의 적용 조건과 현재 통계/구조의 연결을 문서화한다.

1. **ECDF sup statistic:** dependent empirical process의 bootstrap 근사와 sup functional에 대한 타당성. 단순 평균/분산에 대한 결과를 그대로 대체 근거로 쓰지 않는다.
2. **Median/MAD statistics:** dependent quantile 및 robust scale의 정칙성 조건, median/MAD의 비매끄러움, density/uniqueness, ties·zero scale·discrete observations의 처리. 현재 normalization/denominator는 V3 정의를 먼저 확인하고 임의 재정의하지 않는다.
3. **Joint procedure:** 세 horizon과 위치/scale 통계 사이 의존 관계를 보존할 수 있는가? 공통 원시 관측과 joint resampling identity를 기준으로 검토한다.
4. **Nested forward envelope:** 서로 겹치는 reference windows, genuinely future Development suffix 및 nested 비교를 어떻게 재표본화하는지 논리적으로 기술한다. 순서/정보집합과 공유 관측 구조를 잃는 독립 resampling을 승인하지 않는다.
5. **Common N selection:** 여러 N을 비교하고 공통 N을 선택하는 절차와 simultaneous coverage가 양립하는지 검토한다. 사후 선택을 고정 N의 추론으로 치환하지 않는다.
6. **Finite sample:** 문헌의 asymptotic consistency, simulation evidence, finite-sample guarantee를 구분한다. asymptotic theorem만으로 현재 미확인 표본에서의 보장이나 assumption verification을 주장하지 않는다.

최종 연구 문서에는 적용 조건, 충족 여부를 이번 연구에서 확인할 수 없는 조건, 실패/비계산 조건, 남은 정당화 공백을 각각 적는다. 이 연구에서 Development adequacy 계산이나 결과 기반 후보 비교를 실행하지 않는다.

## 7. Automatic Block-Length Rule

최우선 연구 대상은 **현재 statistic-specific automatic selector의 정당화**다.

### 조사 후보

- Politis–White automatic block-length selection.
- Patton–Politis–White correction.
- Statistic-specific block selection.
- Dependent quantile/robust-statistic bootstrap 및 dependent empirical-process 관련 selector.

### 후보별 요구사항

| 항목 | 반드시 답할 내용 |
|---|---|
| Original target | 원 논문이 최적화/보장하는 statistic 또는 error criterion은 무엇인가? |
| Transfer to StockScope | ECDF sup, normalized median shift, relative MAD shift 각각으로 옮길 수 있는 직접 정리나 유효한 논증이 있는가? |
| Dependence conditions | Stationarity·mixing/weak dependence·moment/regularity 조건은 무엇인가? |
| Joint tuning | 여러 component/horizon에 공통 tuning을 쓰거나 다르게 선택할 때 joint procedure를 어떻게 유지하는가? |
| Automatic algorithm | 입력, 추정량, lag/truncation, tie-breaking, 경계·실패 처리까지 사전에 명시할 수 있는가? |
| Hidden tuning | selector 내부의 추가 상수/threshold가 관행 또는 결과 선택에 기대고 있지 않은가? |
| Nested/common N | window와 N에 대한 selector 호출 및 공통 선택 절차의 유효성이 정당화되는가? |
| Finite sample | 정리의 범위와 실제 적용 한계, non-computable 조건은 무엇인가? |

평균 기반 selector가 유명하다는 이유만으로 quantile/MAD/ECDF sup의 공통 rule로 승인하지 않는다. statistic-specific 변환 또는 영향함수 접근을 검토한다면 그 적용 정칙성과 joint functional의 연결까지 증명 근거를 제시한다.

금지: 수동 `block_length = 5`, `10`, 임의 `sqrt(N)`, 여러 길이를 실행한 뒤 좋은 결과 선택, 결과에 따른 method fallback.

Automatic rule의 최종 상태는 다음 중 하나만 사용한다.

```text
JUSTIFIED
CONDITIONALLY_JUSTIFIED
NOT_JUSTIFIED
UNRESOLVED
```

조건부 정당화는 어떤 미충족/미확인 조건이 남았는지 명시한다. 공동 대상 전체를 정당화하지 못한 rule을 일부 component의 근거만으로 전체 JUSTIFIED 처리하지 않는다.

## 8. Dependence Assumption Review

현재 `STATIONARY_WEAK_DEPENDENCE`는 REQUIRED / NOT VERIFIED다. S5에서 `PROVEN`으로 바꾸지 않는다.

문헌 및 구조에 대한 검토 상태는 아래 중 하나다.

```text
ASSUMPTION_COMPATIBLE
ASSUMPTION_INCOMPATIBLE
ASSUMPTION_UNRESOLVED
```

방법이 가정과 이론적으로 compatible하다는 것과 실제 Development 과정이 그 가정을 만족한다는 것을 분리한다. 데이터 diagnostics를 이번 방법 선택의 tuning 근거로 사용하지 않는다.

향후 diagnostics의 허용 역할은 `INFORMATIONAL`, `ASSUMPTION_SUPPORTING`, `ASSUMPTION_REJECTING`이다. 단일 stationarity test의 `p < 0.05`, 또는 귀무가설 비기각만으로 project-level assumption 승인을 하지 않는다.

## 9. S5-B — Independent Risk/Error Budget Source 조사

Source hierarchy는 그대로 유지한다.

```text
1. EXISTING_PROJECT_REQUIREMENT
2. EXTERNAL_DOMAIN_REQUIREMENT
3. FORMAL_STATISTICAL_ERROR_CONTROL
4. NONE
```

### Existing Project Requirement

승인된 StockScope 문서·계약·설계 정의 전체에서 acceptable reference drift, probability movement, normalized median movement, relative scale movement, family-wise error budget의 독립 정의를 조사한다.

발견한 후보마다 document/section, 제정 목적, 수치/단위, 적용 scope, 승인 상태, 생성 lineage를 기록한다. 과거 Development 결과에서 유도한 숫자, unrelated trading risk threshold, 개인적 선호는 기존 adequacy requirement로 취급하지 않는다. 해당 요구가 없으면 `EXISTING_PROJECT_REQUIREMENT = NONE`을 명시한다. 이번 명세 작성 단계에서는 아직 이 조사 결과를 확정하지 않는다.

### External Domain Requirement

금리/시장 데이터 reference stability의 공식 표준 또는 domain requirement를 조사한다. 원문 출처, 적용 대상, 단위 및 StockScope의 세 statistic에 직접 연결되는 근거가 필요하다. 단순 업계 관행, 다른 목적의 표준, 일반적인 안정성 권고만으로 tolerance를 도출하지 않는다.

직접 연결할 근거가 없으면 `EXTERNAL_DOMAIN_REQUIREMENT = NONE`을 유지한다. 검색하지 못한 것과 적용 가능한 source가 없다는 판단을 구분하고 조사 범위를 기록한다.

### Formal Statistical Error Control

Simultaneous confidence construction, FWER, joint bootstrap distribution, studentization/normalization, multiplicity 및 finite-sample applicability를 검토한다.

**Statistical uncertainty와 operational tolerance는 별개다.** Confidence width가 어떤 값으로 계산되었다고 해서 같은 값을 acceptable movement로 채택할 수 없다. Error-control 방법은 주어진 alpha를 제어하는 방법일 수 있으나 프로젝트가 선택할 alpha 자체나 허용 이동량의 독립 source를 자동 제공하지 않는다.

각 budget/tolerance의 source는 개별 판정한다. 한 항목의 외부 근거를 다른 항목으로 확대 적용하지 않는다.

## 10. Joint Multiplicity 및 Error Budget

Frozen scope: `ALL_REQUIRED_REFERENCE_ADEQUACY_COMPONENTS_JOINTLY`.

최소 family는 3 TAIL + 3 median + 3 MAD scale = **9 required components**다. 실제 V3에 정의된 horizon·window·forward comparison·common N 선택까지 추론 family에 미치는 영향을 확인한다. “최소 9”를 사후 탐색을 제외하는 근거로 사용하지 않으며 V3 scope를 변경하지 않는다.

검토 내용:

- 공유 관측의 의존성을 보존하는 joint bootstrap distribution.
- 서로 다른 statistic 단위/scale의 studentization 또는 정당화된 normalization.
- Simultaneous bounds/max procedure 및 Romano–Wolf 계열 multiplicity control의 적용 조건.
- Joint resampling이 가능한 경우와 별도 유효 marginal bounds/적절한 error allocation이 필요한 경우의 구별.
- Family-wide alpha를 각 component에 독립적으로 반복 사용하는 오류 방지.
- Normalization 없이 raw statistic max를 취하는 오류 방지.
- Common N 또는 nested envelope 선택에 필요한 simultaneous statement의 범위.

일반적인 `alpha = 0.05` / `confidence = 95%`를 자동 채택하지 않는다. 새 budget을 정당화하려면 최소 아래 필드가 필요하다.

```text
value
source
justification
scope
multiplicity_scope
status
```

근거가 없으면 `confidence_level = null`, `joint_error_budget = null`을 유지한다. 연구 문서에서 parameterized 절차를 기술하는 것과 특정 numeric policy를 승인하는 것을 구별한다.

## 11. Numerical Reproducibility Contract 검토

Policy tolerance와 numerical approximation을 분리한다. 아래 내용을 문헌/계약 수준에서 확정할 수 있는지 검토하되 bootstrap은 실행하지 않는다.

| 항목 | 요구사항 |
|---|---|
| Deterministic seed | 수동 입력 금지. Dataset identity/hash, protocol hash, preregistration version, statistic/family identity로부터 versioned algorithm 정의 가능성 검토 |
| Canonicalization | Hash 입력의 serialization, encoding, field order, domain separation, seed mapping 명시 가능성 검토 |
| Joint dependence | 각 component seed 분리로 joint resampling 관계를 깨지 않도록 family-level resample identity와 substream 역할 정의 |
| PRNG | Algorithm·version·seed 폭·stream/substream contract 및 재현 범위 명시 |
| Resample ordering | 안정된 resample index/order, 집계 방식과 tie-breaking 정의 |
| Parallelism | worker 수/스케줄 변경이 resample identity 또는 판정을 바꾸지 않도록 계약화 |
| Monte Carlo error | uncertainty approximation 오차와 정책 허용량을 구별하고 오차 제어 source를 기록 |
| Stopping rule | outcome-driven stopping을 피하고 adaptive 반복 관찰의 error-control 조건 검토 |

단순 관행으로 `B = 1000` 또는 `10000`을 선택하지 않는다. convergence tolerance, Monte Carlo error allocation, maximum resamples 역시 이유 없이 새 숫자로 채우지 않는다. 독립 근거가 없으면 해당 numerical parameter를 unresolved로 남긴다.

Seed derivation의 dataset hash는 **향후 승인된 evaluator의 입력 후보**다. 이 S5 연구를 위해 Development 수치 artifact를 새로 해시하거나 Holdout에 접근하라는 허가가 아니다. 구조 확인에 승인된 기존 lineage identity만 참조한다.

정확한 algorithm을 동결할 수 있으면 문서의 versioned contract 초안으로 제시한다. 확정할 수 없는 항목은 이유와 함께 unresolved로 유지한다. 실제 V3 protocol/code/runtime에는 반영하지 않는다.

## 12. Suffix Sufficiency

Standalone `minimum_validation_suffix_transitions = K`를 다시 만들지 않는다.

```text
suffix sufficient iff
approved uncertainty procedure can compute required joint adequacy evidence
using genuinely future Development observations
```

상태 vocabulary는 `SUFFICIENT`, `INSUFFICIENT`, `NON_COMPUTABLE`, `UNRESOLVED_POLICY`다.

S5에서는 실제 suffix evidence를 계산하지 않는다. Uncertainty policy가 미확정이면 `UNRESOLVED_POLICY`를 유지한다. 방법론이 정당화되어도 실제 suffix의 sufficiency 판정은 별도 승인된 evaluation까지 유보한다.

## 13. 외부 문헌 조사와 Evidence Matrix

후속 연구에서는 원 논문, journal, DOI 및 저자/공식 publication을 우선 확인한다. 블로그나 2차 요약만으로 방법론을 승인하지 않는다.

우선 조사 범위:

1. Politis & Romano — Stationary Bootstrap.
2. Politis & White — Automatic Block-Length Selection.
3. Patton / Politis / White — Automatic Block-Length correction.
4. Statistic-specific selector 및 dependent empirical process.
5. Dependent quantiles/robust statistics와 time-series median/MAD bootstrap validity.
6. Joint bootstrap, simultaneous inference, Romano–Wolf style multiplicity control.
7. 적용 가능한 공식 domain stability requirement.

각 primary source는 title/authors/year/journal/DOI 또는 공식 원문 링크, theorem/section, 가정, 대상 functional, 제공하는 보장, StockScope로의 연결, 한계를 기록한다. 원문을 확인하지 못한 source는 그 한계를 명시하고 승인 근거로 과장하지 않는다.

연구 문서에 최소 아래 matrix를 포함한다.

| Claim / candidate | Primary source | Statistic-specific applicability | Joint/nested/common N applicability | Finite-sample scope | Remaining gap | Verdict |
|---|---|---|---|---|---|---|
| 연구 실행 시 작성 | 실제 확인한 source | 구체적 논증 | 구체적 논증 | 보장/한계 구분 | 미해결 조건 | 승인 vocabulary 사용 |

부정적 결론은 조사한 범위에서의 정당화 부족으로 표현한다. 모든 가능한 방법의 불가능성을 증명한 것처럼 일반화하지 않는다.

## 14. 최종 연구 Verdict 결정 규칙

**이번 명세 단계에서는 세 verdict 중 하나를 미리 선택하지 않는다.** 후속 연구의 source와 분석을 완료한 뒤 판정한다.

### A. `METHOD_AND_RISK_BUDGET_JUSTIFIED`

필수: statistic-specific automatic tuning 정당화, defensible dependence 조건, joint multiplicity 정의, 독립 risk/error budget와 모든 operational tolerance 근거, numerical reproducibility contract 정의.

이 판정이어도 adequacy evaluation은 실행하지 않는다. 다음 별도 `NEXT-6E-S6 — Reference Adequacy V4 Preregistration & Evaluator Implementation`으로 전달한다.

### B. `METHOD_JUSTIFIED_RISK_BUDGET_UNRESOLVED`

방법·자동 tuning·joint 적용이 충분히 정당화되었으나 independently sourced joint error budget 또는 acceptable movement가 미해결인 경우다. Risk-Budget Requirement Resolution 이전에 adequacy evaluation을 실행하지 않는다.

### C. `NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY`

Statistic-specific rule, method validity, joint procedure 등 핵심 방법론이 미해결이거나 필요한 numeric policy를 정당화하지 못한 경우의 fail-closed 판정이다. A/B의 조건을 충족하지 못하면 이 상태를 사용한다. 일부 literature support 또는 미충족 조건부 rule을 B의 “method justified”로 확대하지 않는다.

모든 경우 이번 S5 연구만으로 `Reference Adequacy = RESOLVED`를 선언하지 않는다. 실제 frozen V4 contract와 별도 evaluation이 필요한 동안 `UNRESOLVED`를 유지한다. `minimum_prior_observations = null`, `recommended_support = null`, `RATE_SPIKE = UNCALIBRATED`를 보존한다.

## 15. 후속 연구 산출물과 변경 허용 범위

최종 research review 문서는 기존 lineage 보존을 위해 아래 **하나만** 추가한다.

```text
docs/StockScope_NEXT6B_S4_2B16_R24_METHOD_RISK_GOVERNANCE_2026-10-02.md
```

동일 내용의 `NEXT6E_S5_REFERENCE_ADEQUACY_GOVERNANCE_REVIEW` 문서를 중복 생성하지 않는다. 이 TASK_SPEC은 연구 실행 지시서이고 위 review는 실제 연구 결과 문서이므로 역할이 다르다.

최종 review의 필수 구성:

- 기준 commit·lineage·V3 보존 상태·접근 범위.
- Primary source 목록과 claim-to-source evidence matrix.
- TAIL/median/MAD별 method/selector applicability 및 joint/nested/common N 검토.
- Dependence assumption 상태와 이론적 호환성/실제 검증의 구별.
- Project/external/formal source 조사 기록과 각 budget/tolerance의 독립 근거 여부.
- Statistical uncertainty와 operational tolerance 구별.
- Numerical reproducibility contract 초안 또는 미해결 항목.
- Suffix policy, 최종 verdict, 각 blocker와 다음 단계.
- Self-check 및 production/runtime 변경 없음 확인.

허용 변경은 research 문서뿐이다.

```text
Backend code = NONE
Frontend = NONE
DB schema = NONE
Migration = NONE
Runtime DB write = NONE
Runtime artifact = NONE
V3 protocol modification = NONE
Evaluator implementation/evaluation = NONE
```

Scanner, Strategy Engine/Governance, Selection Policy, Risk Gate, Holdings, Recovery, Watch, Execution Policy, Prediction, P6 Value Gate, Production을 변경하지 않는다. 관측 최소 N·recommended support·RATE_SPIKE threshold를 선택하지 않는다.

## 16. 후속 연구 Workflow와 완료 기준

후속 실행 요청 이후:

```text
latest main 및 지정 SHA 비교
→ R2.3/V3 계약·lineage 확인
→ research-only branch
→ 외부 원문 조사
→ 기존 project requirement 조사
→ statistic-specific method 검토
→ independent risk/error budget 검토
→ verdict 및 review 문서 작성
→ 문서 내부 self-check
→ PR
→ CI
→ squash merge
→ 새 main SHA 보고
```

문서 작업에 관련 없는 evaluator/데이터 테스트를 새로 실행하지 않는다. 필수 CI는 기존 저장소 정책을 따르되 보호 데이터 접근 또는 runtime write를 요구하면 실행 전에 범위를 확인하고 제약을 해결한다. CI 결과를 adequacy evidence로 해석하지 않는다.

**후속 S5 COMPLETE 조건:**

- [ ] Statistic-specific automatic tuning 조사와 rule 상태 판정.
- [ ] Stationary Bootstrap applicability를 근거와 함께 판정.
- [ ] Dependence assumption 상태 명시; PROVEN으로 승격하지 않음.
- [ ] Joint multiplicity/nested envelope/common N 논리 검토.
- [ ] Independent risk/error budget source 조사.
- [ ] Existing Project Requirement 존재 여부와 적용 scope 확인.
- [ ] External Domain Requirement 존재 여부와 단위 연결 확인.
- [ ] Statistical uncertainty와 operational tolerance 분리.
- [ ] Numerical reproducibility/Monte Carlo 요구와 남은 조건 기록.
- [ ] Development output으로 숫자나 method를 선택하지 않음.
- [ ] Holdout 무접근.
- [ ] 최종 verdict는 지정된 세 상태 중 하나.
- [ ] Reference Adequacy UNRESOLVED 및 numeric frozen state 유지.
- [ ] Review 문서 하나, runtime artifact와 code 변경 없음.
- [ ] PR / CI / squash merge 완료.
- [ ] 새 main SHA 보고.

정당화되지 않은 numeric policy를 unresolved로 남기는 것은 정상 연구 결과다. 반면 PR/CI/merge 등 필수 전달 절차가 미완료이면 “NEXT-6E-S5 COMPLETE”로 보고하지 않는다.

## 17. Self-Check와 최종 보고 Template

최종 research review에 아래 항목을 실제 수행 사실에 근거해 명시한다.

```text
Development result inspected for tuning = NO
Holdout accessed = NO
Numeric tolerance invented = NO
Conventional alpha adopted without justification = NO
Manual block length selected = NO
Outcome-driven method fallback = NO
Candidate survival used = NO
Signal survival used = NO
Episode survival used = NO
Production behavior changed = NO
Runtime writes = 0
```

후속 연구 완료 보고:

```text
NEXT-6E-S5 COMPLETE

PR: <PR_URL>
Merge SHA: <SQUASH_MERGE_SHA>
New main SHA: <VERIFIED_MAIN_SHA>
Research base SHA: <S5_RESEARCH_BASE_COMMIT_HASH>
Research lineage: NEXT-6B-S4.2-B.1.6-R2.4

Dependence method: <candidate / reasoned status>
Automatic tuning rule: <JUSTIFIED / CONDITIONALLY_JUSTIFIED / NOT_JUSTIFIED / UNRESOLVED>
Dependence assumption: <ASSUMPTION_COMPATIBLE / ASSUMPTION_INCOMPATIBLE / ASSUMPTION_UNRESOLVED>
Assumption verified: NO
Joint multiplicity: <reviewed procedure / remaining gap>
Risk-budget source: <independently supported source / NONE>
Confidence/error budget: <independently justified value / null>
TAIL tolerance: <independently justified value / null>
MAD normalized median tolerance: <independently justified value / null>
MAD relative scale tolerance: <independently justified value / null>

Verdict:
<METHOD_AND_RISK_BUDGET_JUSTIFIED
 / METHOD_JUSTIFIED_RISK_BUDGET_UNRESOLVED
 / NO_JUSTIFIED_NUMERIC_ADEQUACY_POLICY>

Reference Adequacy: UNRESOLVED
minimum_prior_observations: null
recommended_support: null
RATE_SPIKE: UNCALIBRATED
Development tuning inspection: NO
Holdout accessed: NO
Runtime writes: 0
Production impact: NONE
Next step: <verdict에 따른 별도 작업>
```

아직 미실행한 source 조사나 미확정 verdict를 이 template의 완료 결과로 채우지 않는다. 현재는 **명세 작성만 완료**된 상태다.
