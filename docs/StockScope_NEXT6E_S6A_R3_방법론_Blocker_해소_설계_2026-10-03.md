# StockScope NEXT-6E / S6A / R3 이후 방법론 Blocker 해소 설계

작성일: 2026-10-03, Asia/Seoul  
문서 성격: 정식 방법 설계 및 다음 구현 명세. 실행·승인 결과가 아니다.  
설계 식별자: NEXT6E_S6A_R3_BLOCKER_RESOLUTION_DESIGN_V1  
권장 다음 단계: NEXT-6E-S6A-R4 — 이산분포 방법 계약 및 Development 전용 승인 진단  
저장소 반영 예정 경로: docs/StockScope_NEXT6E_S6A_R3_방법론_Blocker_해소_설계_2026-10-03.md

## 1. 문서 목적 / 범위

권장 primary route는 **원자료 ECDF의 sequential dependent-multiplier 동시대역 → 집합값 median / MAD 오차 구간**이다. 연속밀도에 의존하는 R1의 quantile/MAD 미분 경로는 교체한다. 관측 통계량의 기존 median·raw MAD 정의, 공동 horizon, κ=1/10, G-A → G-B → S6C 순서는 보존한다.

bandwidth에 관해서는 기존 자동 선택값을 곧바로 새 정리의 유효성으로 간주하지 않는다. 새 추론 계약은 **정확한 Gaussian covariance multiplier와 모든 구조적으로 허용된 정수 span의 최대 root**를 사용한다. §6의 지배 부등식으로 보수적 coverage를 확보하며, 관측 결과를 보고 유리한 span을 선택하지 않는다. 이는 R2의 단일 적응형 moving-average profile과 다른 계약이다. 계산 비용과 보수성이 증가하므로 이를 숨기지 않는다.

설계 결정과 실제 사용 승인을 분리한다. 이 문서는 R3 결과를 PASS로 바꾸지 않는다. A5/A6는 유한 표본으로 증명할 수 없는 모집단 가정이다. 구체적인 model-use 승인, 새 증명 사슬의 검토, clean DEV replay가 없으면 새 G-A도 BLOCKED다. 구현자가 가정이나 수치 기본값을 발명하지 않도록 입력·판정·실패 동작까지 정의한다.

이번 작업은 Markdown 한 개 작성으로 한정한다. 코드·테스트·DB·runtime·V3·V4·evaluator·Production을 변경하거나 실행하지 않는다. main 및 기존 문서도 변경하지 않는다. 현재 산출물은 별도 outputs/docs에 제공하며 위 저장소 경로로의 반영은 후속 문서 변경 작업이다.

## 2. 현재 R3 상태와 기준 자료

### 2.1 검토 시점의 Git 기준

| 기준 | 확인한 ref / SHA | 적용 |
|---|---|---|
| remote main | bbee4008fafab86d336c89ea7bb79e2684414554 | 기존 R1/R2/R2A 및 상위 계약 |
| remote next6e-s6a-r3-clean-rerun | 57bfe9ba517602e592be4e566d866be59c0616d5 | 최신 R3 handoff 및 evidence 문서의 §0 |
| 로컬 main | bbee4008fafab86d336c89ea7bb79e2684414554 | 읽기 확인만 수행 |

main의 R3 문서 서두는 source-unavailable 역사 상태를 기록하지만 rerun branch의 두 R3 문서 §0은 exact DEV 확보 및 진단 실행을 기록한다. 따라서 후자를 우선한다. 오래된 handoff의 “DEV 파일을 먼저 찾아라”를 현재 작업의 지시로 재사용하지 않는다. branch 이름에 clean이 있어도 기록된 isolation certification이 자동으로 YES가 되지 않는다.

### 2.2 허용된 Development evidence

| 필드 | 값 |
|---|---|
| dataset_id | MACROCAL-DEV-7c3f6660b3aae03f |
| dataset_hash | 7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1 |
| aligned analysis rows | 1999 |
| A0 / A1 / A2 / A3 / A8 / A10 | MATHEMATICALLY_VERIFIED — 기존 R3 실행의 사실 |
| A4 / A7 / A9 | ASSUMPTION_NOT_ACCEPTED |
| A5 / A6 | UNRESOLVED |
| 기존 multiplier 결과 | coordinate m=[1,5,10], L=10, b=22, effective ell=43, manual fallback=NO |

R3에서 보고된 입력 진단은 다음과 같다. 이 문서 작성 중 raw DEV나 runtime을 다시 열거나 계산하지 않았다.

| horizon | unique values | median | median ties | raw MAD | MAD ties |
|---|---:|---:|---:|---:|---:|
| 1obs | 46 | 0 | 188 | 3 | 297 |
| 5obs | 81 | 0 | 91 | 7 | 118 |
| 10obs | 113 | 1 | 69 | 10 | 95 |

세 좌표는 정수 bp grid이며, 공동 1999행 중 unique triples는 1884이다. 관측 grid를 population의 유한 support로 간주하지 않는다. 아직 관측되지 않은 정수 bp 값도 존재할 수 있다.

현재 유지하는 formal state:

~~~
Method state: METHOD_PROFILE_FROZEN          # 기존 R3 계약
Assumption Acceptance: NOT_GRANTED
G-A: BLOCKED
G-B: BLOCKED
Reference Adequacy: UNRESOLVED
V3 changed: NO
V4 created: NO
Evaluator implemented: NO
Production impact: NONE
~~~

R3 evidence에는 clean_isolation_certified=NO가 남아 있다. 역사적 incident의 금지 metadata 값은 가져오거나 재기록하지 않는다. 이 문서의 source-only 검토는 그 certification을 수정하지 않으며, 새 승인에는 별도의 clean 실행 증거가 필요하다.

### 2.3 핵심 기존 문서

모든 경로는 SkyBluekor/StockScope 기준이다.

| 문서 | 읽은 기준 | 복구한 계약 |
|---|---|---|
| docs/StockScope_인수인계_2026-10-02_NEXT6E_R3_BLOCKED.md | rerun branch | 최신 상태·우선순위·isolation |
| docs/StockScope_NEXT6E_S6A_R3_ASSUMPTION_ACCEPTANCE_EVIDENCE_GATE_2026-10-02.md | rerun branch; main 서두 비교 | A0~A10 실제 evidence·제약 |
| docs/StockScope_NEXT6E_S6A_R1_SEQUENTIAL_FUNCTIONAL_THEOREM_RESOLUTION_2026-10-02.md | main | sequential target·정리·median/MAD·공동 N |
| docs/StockScope_NEXT6E_S6A_R2_CANDIDATE_DOMAIN_MULTIPLIER_PROFILE_RESOLUTION_2026-10-02.md | main | adaptive IMSE·PW·Parzen·centering |
| docs/StockScope_NEXT6E_S6A_R2A_CANDIDATE_DOMAIN_GOVERNANCE_DECISION_2026-10-02.md | main | exact κ·out-of-domain·versioning |
| docs/StockScope_NEXT6E_S6A_METHOD_CONTRACT_RESOLUTION_2026-10-02.md | main | 정리 사슬의 초기 한계 |
| docs/StockScope_NEXT6E_S6B_RISK_BUDGET_GOVERNANCE_RESOLUTION_2026-10-02.md | main | G-B·정책 수치·승인 역할 |
| docs/StockScope_NEXT6E_REFERENCE_ADEQUACY_RESOLUTION_ARCHITECTURE_2026-10-02.md | main | Track A/B·S6C·V3/V4·관측량과 추론 대상 구별 |

현재 결과, 승인 상태 및 target에는 R3 → R2A → R2 → R1 → S6A → 초기 architecture 순서를 적용한다. 초기 architecture의 전체 record-law confidence region 및 γ_repeat는 복원하지 않는다. 더 오래된 handoff, 실행 결과 artifact, 광범위한 runtime/데이터 검색은 근거로 사용하지 않는다.

## 3. 문제 정의

1. **Quantization / ties:** 측정된 feature가 이산값이다. 중복 횟수는 오류가 아니며 모든 행을 원래 chronology와 함께 보존한다. 연속 latent 금리 모형이 가능하더라도 실제 사용 대상은 기록된 bp feature다.
2. **Continuity:** R1이 인용한 continuous-marginal 정리를 이산 Z에 그대로 대입할 수 없다. ECDF에 대한 별도의 transfer가 필요하다.
3. **Median / MAD:** 양의 국소밀도는 grid law와 맞지 않는다. atom 안에서 median이 고정되는 경우와 누적확률이 정확히 1/2인 경계는 서로 다른 비정규 동작이다. 표본 median ties가 있다는 것만으로 population median이 비유일하다고 단정하지도 않는다.
4. **A5:** R3에는 사전 승인된 수치 진단 판정 규칙과 scope-specific model-use 승인이 없다. “stationarity 기각 안 됨”은 strict stationarity의 증명이 아니다.
5. **A6:** finite ACF나 1999행으로 무한 시차의 α(r)=O(r^-a), a>15/2를 확인할 수 없다. overlap가 10obs라는 사실도 9-dependent 또는 iid를 뜻하지 않는다.
6. **A10:** finite preprocessor 재현성과 multiplier의 점근 유효성은 다르다. 특히 데이터로 선택된 bandwidth를 그대로 사용하면서 multiplier가 데이터와 독립이라는 deterministic-bandwidth 정리를 인용하면 추가 정당화가 필요하다.

요구되는 해결은 측정값 변경이 아니라 정리의 적용 대상·오차 사건·승인 계약의 교체다. finite sample을 population assumption의 증명으로 승격시키는 방법은 채택하지 않는다.

## 4. 기존 theorem route 분석과 적용 문헌

### 4.1 R1 중 보존 / 교체할 부분

| R1 구성 | 결정 | 근거 |
|---|---|---|
| aligned Z_i=(X_i^1,X_i^5,X_i^10) | 보존 | serial·overlap·cross-horizon 의존성을 함께 보존 |
| sequential empirical process | 수정 보존 | 원래 indicator에 대한 lattice transfer를 §6에서 제시 |
| continuity of observed law | 삭제 | 실제 이산 law를 모델 대상으로 인정 |
| median/MAD Hadamard derivative | 폐기 | 양의 밀도·유일성 없이 역변환/포함관계 사용 |
| regular scalar Gaussian median/MAD law | 승계 금지 | 새 구간은 비대칭·비축소·무한대 가능 |
| nested/all-N structure | 보존 | 하나의 prefix 동시 사건과 결정적 부등식 |
| R2 adaptive single-bandwidth calibration | 새 추론에서 교체 | 기존 계산 결과만 보존; §6.3의 보수적 envelope 채택 |
| exact κ=1/10 | 보존 | R2A governance; 새 coverage도 동일 domain에 제한 |

### 4.2 원 문헌에서 빌리는 범위

**L1.** Bücher & Kojadinovic (2016), Bernoulli 22(2), 927–968, Theorem 2.1, Corollary 2.2, §5.1, §5.2.2, Remark 2.3 / Supplement Proposition F.1. 연속 marginal로 표현된 empirical process와 dependent multiplier의 공동 약수렴을 사용한다. d=3에서 mixing exponent는 a>15/2이고 deterministic span은 발산하면서 O(n^(1/2-ε))이어야 한다. Gaussian covariance construction을 차용한다. 논문의 copula derivative theorem을 StockScope에 적용하지 않는다. 실제 Z의 stationarity/mixing은 미승인이다. [원 논문](https://arxiv.org/pdf/1306.3930)

**L2.** Rüschendorf (2009), Proposition 2.1의 distributional-transform 표현; Oertel (2015), Proposition 2.16 / Theorem 2.18의 직접 분석과 증명. 임의 cdf를 일반화 역함수로 표현할 수 있다는 확률공간의 항등식만 사용한다. 실데이터에 perturbation을 적용하는 절차가 아니다. 이 표현 자체가 StockScope의 dependence나 bootstrap 유효성을 증명하지는 않는다. [원 논문 서지](https://doi.org/10.1016/j.jspi.2009.05.030), [Oertel 원 preprint](https://arxiv.org/pdf/1312.4997)

**L3.** Chernozhukov, Fernández-Val, Melly & Wüthrich (2020), JASA 115(529), 123–137, preprint의 Theorem 1 / Theorem 2. 유효한 동시 DF band를 quantile band로 역변환하는 포함관계만 사용한다. 논문이 StockScope의 dependent sequential DF band 또는 MAD를 직접 제공한다고 주장하지 않는다. MAD 및 midpoint median의 보수적 transfer는 §7에서 별도 도출한다. [원 preprint](https://arxiv.org/pdf/1608.05142), [학술지](https://doi.org/10.1080/01621459.2019.1611581)

**L4.** Bücher, “A note on weak convergence …”, Journal of Theoretical Probability 28(3), 1028–1037, 2015. 기존 R1/R2의 연도 표기는 최종 학술지 기준으로 정정한다. Theorem 1의 base-process 약수렴 조건이 더 약하다는 사실만으로 multiplier 조건까지 a>1로 바꾸지 않는다. [원 preprint](https://arxiv.org/pdf/1304.5113), [저자 서지](https://math.ruhr-uni-bochum.de/en/faculty/professorships/stochastics/group-buecher/research-publications/publications/)

**L5.** Shao (2010), Theorem 2.1 / Assumptions 2.1–2.2. self-normalization도 영향함수 FCLT, 비퇴화 및 remainder 조건을 요구한다. variance estimator 제거가 이산 median의 비정규성을 제거하지 않는다. 본 설계에는 이 정리를 채택하지 않는다. [저자 원문](https://publish.illinois.edu/xshao/files/2012/11/SNfinal.pdf)

**L6.** Politis & Romano (1994)의 subsampling 연구. 일반적인 subsampling 가능성을 검토하는 자료이며 정확한 StockScope all-prefix median/MAD 사슬의 승인 근거로 사용하지 않는다. 수렴률·limit law·block-length 조건을 새로 확인해야 하므로 이번 primary/fallback으로 채택하지 않는다. [저자 기관 자료](https://statistics.stanford.edu/technical-reports/general-theory-large-sample-confidence-regions-based-subsamples-under-minimal)

이하 D1~D4는 위 결과를 연결하는 **본 문서의 도출**이다. 출판된 StockScope 정리나 완료된 독립 심사로 표시하지 않는다. G-A의 method reviewer가 연결 조건을 검토하고 승인해야 한다.

## 5. 대안 방법론 비교

| 후보 | 이산자료 적합성 / 정리 연결 | 구현·검증 | Governance 영향 | 결정 |
|---|---|---|---|---|
| 기존 continuous-law route 그대로 | observed-law continuity와 density 부적합; latent law로 대체하면 대상 변경 | 구현 재사용은 쉽지만 증명 공백 지속 | 사후 가정 완화 위험 | 현재 입력에는 채택 불가 |
| empirical discrete law를 population으로 고정하고 iid resample | ties는 보존하나 serial law 제거 | 쉬움; 잘못된 의존성 | 모집단·sampling target 변경 | 기각 |
| atom 내부의 strict quantile margin | F(m-)<1/2<F(m)이 population에서 엄격하면 quantile이 국소 상수 | finite jump로 population margin 증명 불가; boundary 경우 별도 필요 | atom class 추가 승인 | primary로 부적합 |
| lattice ECDF band + generalized/set quantile | 밀도 없이 포함관계 사용; boundary도 큰 집합으로 표현 | inverse 순서·strict inequality·tails 검증 가능 | inference target/version 변경 | **채택** |
| ties-aware rank / midrank만 사용 | rank transform은 밀도나 dependence 조건을 해결하지 않음 | rank CDF와 원 bp metric 구별 필요 | 원 metric 단위 소실 가능 | bandwidth audit에만 기존 역할 보존 |
| lower empirical median으로 통일 | 비유일성 선택은 명확하나 기존 even median과 다름; density 문제 잔존 | 검증 쉬움 | 관측 metric 변경 | 미채택; midpoint 관측량 유지 |
| trimmed mean / winsorized estimator | trim 경계 atom·cutoff·moment 조건 필요 | 새 trim 규칙 및 영향함수 필요 | 새 τ_L 의미·수치 근거 필요 | 미채택 |
| Huber location / robust M-scale | score와 derivative 조건이 만족되면 atoms 허용 가능 | tuning constant·식별성·joint FCLT 추가 필요 | estimator·scale·policy 재설계 | 미채택 |
| IQR | density-free inversion 가능하나 quartile interval/zero IQR 발생 | MAD보다 단순하나 본 경로로 MAD도 가능 | scale 의미 및 τ_S 재정의 | 교체 이득 부족 |
| Qn / Sn | 강한 ties에서 0 가능; U-quantile 또는 복합 quantile 비정규성 | 새 dependent sequential theorem 필요 | scale convention/상수/identity 변경 | 미채택 |
| block bootstrap | dependence 보존 후보이나 block 선택·law 조건 필요 | 새 engine·전체 joint transfer 필요 | R2 폐기 및 재동결 | 이번 route보다 보존 이점 적음 |
| subsampling | 특정 비정규 통계에 가능; 자동 만능 대안 아님 | rates·block sequence·joint indexed limit 필요 | 새 method/numerical profile | 미채택 |
| self-normalized | variance tuning 감소 가능; FCLT와 비퇴화가 여전히 필요 | median/MAD degeneracy·joint inversion 재연구 | statistic/root 교체 | 미채택 |
| weaker dependence / local-stationary theorem | 원론적으로 가능; reviewed theorem과 자동 연결 불가 | 새로운 limit process 및 시변 calibration 필요 | source scope·domain·policy 전면 재검토 | 이번 fallback으로 채택 안 함 |

primary는 가장 작은 관측-statistic 변경으로 atoms를 정면 처리한다. 단일 R2 bandwidth의 유효성 공백을 숨기지 않기 위해 추론 calibration은 더 보수적인 §6.3으로 교체한다. **별도의 통계 fallback은 두지 않는다.** primary 전제가 승인되지 않으면 BLOCKED를 반환한다. 이는 가정을 느슨하게 하거나 다른 방법을 결과에 맞춰 자동 선택하는 것을 방지한다.

## 6. 채택 설계 및 이론 사슬

### 6.1 Primary method / target

~~~
method_id (design): NEXT6E_S6A_R4_LATTICE_CDF_PROJECTION_V1
target_id (design): JOINT_SEQUENTIAL_CDF_AND_FUNCTIONAL_ERROR_COVERAGE_V1
inference: ASYMPTOTIC_CONSERVATIVE_SIMULTANEOUS
process: observed aligned Z, arbitrary lattice masses
stationarity: STRICT, scope-specific model-use acceptance required
mixing: alpha_Z(r)=O(r^-a), a>15/2
functional transfer: ORDER_INVERSION_AND_DETERMINISTIC_OUTER_BOUNDS
calibration: GAUSSIAN_COVARIANCE_MULTIPLIER_SPAN_ENVELOPE
fallback: NONE
~~~

새 target은 기존 nonlinear median/MAD sampling law 전체의 bootstrap 일치성이 아니다. 모든 허용 prefix의 원 cdf 오차를 동시에 감싼 사건으로부터 위치·척도 오차 구간을 보수적으로 도출한다. 정확한 confidence 대상은 미지의 F_h 및 그 선택된 median/MAD다. 이미 관측된 prefix 간 차이에 “그 알려진 수치의 신뢰구간”을 붙이지 않는다.

### 6.2 D1 — observed lattice empirical process transfer

이 절은 데이터 처리 알고리즘이 아니라 정리의 연결 증명이다.

가정: Z가 엄격 정상이고 위 mixing rate를 만족한다. 확률공간만 확장하여 원 과정과 독립인 iid V_ih~Uniform(0,1)를 둔다. F_h는 **미지의 진짜 marginal cdf**이다.

U_ih = F_h(X_i^h-) + V_ih {F_h(X_i^h)-F_h(X_i^h-)}.

L2에 의해 U_ih는 uniform이고 X_i^h=F_h^←(U_ih) a.s. 따라서 모든 lattice threshold x에서

1{X_i^h≤x}=1{U_ih≤F_h(x)}

이며 joint lower orthant도 같은 항등식을 만족한다. lattice threshold와 시간은 가산이므로 공통 probability-one 집합에서 이 항등식을 취할 수 있다. 정수 사이 cdf 값은 동일하다.

독립 iid V를 붙여도 시간별 동일한 변환은 stationarity를 보존한다. 과거/미래 event를 V에 대해 적분하면 [0,1]-값 조건부 함수의 covariance가 되므로 α_(Z,V)(r)≤α_Z(r); U의 measurable mapping도 이를 증가시키지 않는다.

따라서 L1 Theorem 2.1을 U에 적용한 후 고정된 index restriction u=(F_1(x_1),F_5(x_5),F_10(x_10))을 취한다. 이 restriction은 sup norm에서 contraction이다. 표본 전체 centering도 동일 indicator의 평균이므로 원자료 multiplier process와 정확히 일치한다. centered Gaussian limit의 covariance는 원 indicator들의 long-run covariance다. 연속 joint observed law는 필요하지 않다.

**NO_JITTER의 정확한 의미:** V나 U를 생성·추정·저장·입력하지 않는다. raw X, 순위, ties, median, MAD, bandwidth evidence를 전혀 바꾸지 않는다. unknown F를 empirical F로 대체해 randomized rank를 계산하는 구현은 금지한다. 증명에서 사용하는 보조 확률공간은 “기록된 데이터를 연속형처럼 바꾸는 방법”이 아니며 관측 통계량은 항등적으로 그대로다. 이 구분을 지킬 수 없는 구현은 A4 실패다.

### 6.3 D2 — tuning 선택에 의존하지 않는 보수적 calibration

기존 ell=43을 무한 n에 대해 고정하면 ell_n→∞가 아니다. R2의 데이터 기반 선택기에 대해서도 finite 결과 재현만으로 random-bandwidth validity를 증명할 수 없다. 이번 설계는 새 적응형 선택기나 임의 constant를 만들지 않고 다음 **완전한 정수 span 집합**을 사용한다.

Λ_n={1,2,…,n}.

상한 n은 기록 길이이고 하한 1은 양의 정수 span의 최소값이다. 데이터 결과로 선택한 수치 threshold가 아니다. 이 집합의 모든 원소가 점근 admissible하다고 주장하지 않는다.

각 ell∈Λ_n에 대해 covariance kernel을 다음과 같이 고정한다.

~~~
phi(u) = 1 - 6u^2 + 6|u|^3           if |u| <= 1/2
       = 2(1-|u|)^3                  if 1/2 < |u| <= 1
       = 0                           otherwise
Sigma_ell[i,j] = phi((i-j)/ell)
xi^(r,ell) = principal_symmetric_sqrt(Sigma_ell) g^(r)
g^(r) ~ N(0, I_n), independent across r and of the data
~~~

phi는 covariance로 쓰는 Parzen이다. R2의 **moving-average weight Parzen**과 역할이 다르며 같은 kernel profile이라고 표시하면 안 된다. L1 §5.2.2의 PSD covariance construction을 사용하므로 deterministic admissible ell_n에 대해 multiplier 조건을 직접 만족한다. 같은 r에서는 모든 ell에 같은 g를 사용한다. 각 ell의 marginal multiplier law는 정확하고, 서로 다른 ell 사이 coupling은 이 보수적 방법의 설계로 고정된다.

N_0=ceil(n/10), s_k=k/n라 하자. 각 horizon에 대해

~~~
B*_h,ell(k,x)
 = n^(-1/2) sum(i=1..k) xi_i^(r,ell)
     [1{X_i^h <= x} - Fhat_h,n(x)]
R*_ell = max(h, k=N_0..n) sup_x |B*_h,ell(k,x)|
R*_env = max(ell in Lambda_n) R*_ell
c_env(alpha) = conditional (1-alpha) quantile of R*_env
~~~

이론상 c_env는 정확한 conditional quantile이다. 실제 Monte Carlo 근사는 S6C의 별도 precision 계약으로만 허용한다. α는 symbolic input이며 이번에 값을 선택하지 않는다.

**계산 정의를 닫는 규칙:** 각 h의 전체 record distinct support를 S_h라 하면 multiplier root의 x supremum은 S_h와 양쪽 tail에서 정확히 계산할 수 있다. 각 ell,r에서 C(k)=sum_(i≤k)xi_i, A_h(k,x)=sum_(i≤k)xi_i 1{X_i^h≤x}를 순서대로 누적하고 B*=n^-1/2[A_h(k,x)-Fhat_h,n(x)C(k)]를 사용한다. tails의 multiplier 값은 0이다. 125-point rank grid는 새 root에 사용하지 않는다. 세 marginal root를 하나의 공통 xi로 계산하므로 full 3D orthant 배열을 수치 생성할 필요는 없지만 cross-horizon dependence는 그대로 남는다. 이 계산의 정확한 시간 비용은 구현 방식에 달리므로 S6C에서 측정한다.

**지배 증명.** 증명용 deterministic witness ell_n^0=floor(n^(1/5))를 취할 수 있다. 이는 실제 채택 bandwidth가 아니며 Λ_n에 들어가는 유효한 한 수열의 존재를 보여줄 뿐이다. ell_n^0→∞이고, 예를 들어 ε=1/5에서 ell_n^0=O(n^(1/2-ε))이다. 모든 replicate에서 R*_env≥R*_(ell_n^0)이므로 모든 α에 대해 c_env(α)≥c_(ell_n^0)(α)이다.

D1과 L1에 의한 witness의 conditional bootstrap consistency 및 그 Gaussian sup limit의 해당 quantile 연속성이 성립하면

liminf P{R_n≤c_env(α)} ≥ 1-α,

R_n=max_(h,k=N_0..n) sup_x |n^(-1/2) sum_(i≤k)[1{X_i^h≤x}-F_h(x)]|.

증명은 “모든 bandwidth에서 일치” 또는 “n개 bootstrap의 joint growing-dimension theorem”을 요구하지 않는다. **한 유효한 witness를 지배한다**는 부등식만 사용한다. large span에서 bootstrap 근사가 부정확할 수 있어도 그 root를 추가하는 것은 critical value를 낮추지 않는다. 반면 일부 ell을 계산하지 않고 작은 최대값을 반환하는 것은 금지한다.

위 결과는 conservative liminf coverage다. 정확한 nominal coverage, 유한표본 distribution-free 보장, 최적 power, minimax optimality를 주장하지 않는다. Gaussian sup의 비퇴화/critical-quantile continuity는 별도 이론 조건이며 A6의 model/theorem ledger에 들어간다. 경험분산 양수만으로 long-run variance 양수를 증명하지 않는다.

conditional consistency는 L1의 둘 이상의 독립 replicate에 대한 공동 약수렴과 conditional-law equivalence를 이용한다. lattice restriction 이후에도 독립 limit copies가 유지되며, fixed κ domain의 max/sup은 연속 mapping이다. 따라서 witness의 critical quantile 수렴을 사용할 수 있다. indicator는 bounded이므로 이 empirical-process 사슬에 raw X의 고차 적률 조건을 임의 추가하지 않는다. 완전퇴화 limit나 해당 quantile의 연속성이 미확인인 경우는 이 논증으로 통과시키지 않는다.

이 선택은 명시적 비용을 가진다. covariance factorization의 단순 기준 구현은 모든 ell에 대해 O(n^4) 전처리, 반복 계산은 매우 클 수 있다. 보수성이 커서 구간이 유용하지 않을 수 있다. 자원 부족은 RESOURCE_INCOMPLETE로 종료하며 span 축소·유리한 ell 선택을 허용하지 않는다. 효율적 동등 알고리즘은 수학적 동일성 및 수치 검증 후 S6C에서 사용할 수 있다.

### 6.4 D3 — simultaneous DF band

ε_k=c_env(α)/(sqrt(n) s_k)=c_env(α) sqrt(n)/k.

동시 사건 E_CDF={모든 h,k≥N_0에서 ||Fhat_h,k-F_h||∞≤ε_k}는 D2의 사건과 같다. F_h는 각 prefix마다 다른 모수가 아니라 승인된 정상 모형의 동일 marginal이다.

L_h,k(x)=max(0,Fhat_h,k(x)-ε_k), U_h,k(x)=min(1,Fhat_h,k(x)+ε_k).

모든 threshold의 band이므로 데이터에서 정한 median 위치나 absolute-deviation endpoint에서도 유효하다. 수치 x-grid로 대체하지 않는다. 추론의 tails에서는 아직 관측되지 않은 support를 배제할 수 없으므로 무한 endpoint를 허용한다.

### 6.5 D4 — 하나의 사건과 downstream selection

§7의 모든 median/MAD 구간 포함은 E_CDF의 결정적 결과다. horizon, prefix, 함수마다 α를 별도로 사용하거나 별도의 random path를 만들지 않는다.

공동 N을 나중에 골라도 모든 허용 k를 이미 포함하는 E_CDF는 유지된다. 다만 이것이 “적정 reference”, 미래 regime stability 또는 새로운 record의 recurrence probability를 의미하지는 않는다. 정책 의미는 §14에서 별도 승인한다. 기존 γ_repeat를 다시 끼워 넣지 않는다.

## 7. 통계량 / estimator 정의

### 7.1 원자료·관측 통계량

native source Y와 W_i=100(Y_i-Y_(i-1)), X_i^h=sum_(j=0..h-1)W_(i-j), h∈{1,5,10}를 유지한다. 실제 분석 index는 세 horizon 모두 유효한 동일 native row들의 chronology다. warmup·단위·cutoff는 기존 source contract에서 가져온다.

Fhat_h,k(x)=k^-1 sum_(i≤k)1{X_i^h≤x}. right-continuous, ties 포함.

q^-_G(p)=inf{x:G(x)≥p}, q^+_G(p)=inf{x:G(x)>p}, 0<p<1.

M(G)=[q^-_G(1/2), q^+_G(1/2)], m°(G)=(두 endpoint의 합)/2.

이 m°를 empirical cdf에 적용하면 홀수 표본 중앙값, 짝수 표본 중앙 두 값 평균과 일치한다. 전체 M(G)는 비유일성을 나타내는 추론 보조량이며 기존 scalar median을 몰래 lower median으로 바꾸지 않는다.

H_G,m(r)=G(m+r)-G((m-r)-), r≥0.

d°(G)=midpoint median of H_G,m°(G). 표본 d°는 기존 raw MAD다. normal-consistency multiplier, epsilon floor, 임의 rounding을 넣지 않는다. bp lattice에서도 midpoint는 반 bp 또는 그에 따른 더 세밀한 유리수가 될 수 있으므로 integer 강제 반올림을 하지 않는다.

관측 metric 정의는 계속 다음이다.

~~~
T_h,N,t = ||Fhat_h,t-Fhat_h,N||infinity
L_h,N,t = |mhat_h,t-mhat_h,N| / dhat_h,N
S_h,N,t = |dhat_h,t-dhat_h,N| / dhat_h,N
E_h,q,N = max(t=N+1..n) q_h,N,t
~~~

위 식은 설계 interface다. 이번 및 R4 assumption diagnostic에서 실제 forward envelope나 passing decision을 계산하는 지시가 아니다.

### 7.2 Median outer interval

한 prefix에서 e=ε_k, G=Fhat_h,k라 하자.

I_m(h,k)=[q^-_G(1/2-e), q^+_G(1/2+e)].

확장 규칙: 아래 확률이 0 이하이면 lower endpoint=-∞, 위 확률이 1 이상이면 upper endpoint=+∞이다. 임의 관측 최솟값/최댓값으로 잘라내지 않는다. 그 외에는 위 ≥ / >를 정확히 구별한다.

||G-F||∞≤e이면 q^-_G(1/2-e)≤q^-_F(1/2)≤q^+_F(1/2)≤q^+_G(1/2+e). 따라서 M(F) 전체와 m°(F)를 포함한다. density나 strict atom-margin threshold는 필요 없다. e=0에서도 1/2 plateau의 두 endpoint를 보존한다.

### 7.3 MAD outer interval — estimated center 포함

I_m=[a,b], mhat=m°(G), r_m=max(|a-mhat|,|b-mhat|)라 하자. 무한 endpoint이면 r_m=+∞다.

G_D는 원 prefix 값들의 |X_i-mhat| empirical cdf다. 임의 r에서

|H_F,mhat(r)-G_D(r)|≤2e

이다. 두 cdf endpoint 차이로 표현했기 때문이다. 이 부등식은 모든 center와 r에 대해 동시에 성립하므로 mhat가 데이터 의존적이어도 사용할 수 있다.

또한 ||X-m°(F)|-|X-mhat||≤r_m이므로 두 deviation law의 각 quantile endpoint는 최대 r_m만큼 이동한다. 결과적으로

~~~
a_D = q^-_G_D(1/2-2e), with a_D=0 if 1/2-2e<=0
b_D = q^+_G_D(1/2+2e), with b_D=+infinity if 1/2+2e>=1
I_d(h,k) = [max(0,a_D-r_m), b_D+r_m]
if r_m is infinite: I_d=[0,+infinity]
~~~

I_d는 d°(F)를 포함한다. estimated center 효과를 무시한 “MAD는 그냥 또 하나의 quantile”이라는 처리를 하지 않는다. 같은 F의 위치·척도 joint image보다 큰 outer interval이지만 coverage를 잃지 않는다. 양의 밀도나 MAD quantile 유일성은 요구하지 않는다.

### 7.4 오차·ratio·nested mapping

R_m(h,k)=sup_(u∈I_m)|mhat_h,k-u|, R_d(h,k)=sup_(v∈I_d)|dhat_h,k-v|.

E_CDF 위에서 모든 h,k의 sample-to-population location/scale 오차가 이 radius로 제한된다. 공통 population m°,d°를 이용한 triangle inequality로, dhat_h,N>0일 때 모든 N<t에 대해

~~~
T_h,N,t <= epsilon_N+epsilon_t             # 필요시 이론적 범위 1과 min
L_h,N,t <= [R_m(h,N)+R_m(h,t)]/dhat_h,N
S_h,N,t <= [R_d(h,N)+R_d(h,t)]/dhat_h,N
~~~

이는 관측된 movement를 중심으로 만든 confidence interval이 아니라 **정상모형 하 simultaneous error event의 결과**다. 이 부등식의 비기각을 adequacy로 선언하지 않는다. 모든 later t에 max를 적용해도 동일 사건이 유지된다.

기존 metric의 분모는 관측 anchor MAD이므로 이 부등식에서 고정된 관측 denominator를 쓰는 것은 정확하다. resampled ratio-law를 근사한다고 주장하지 않는다. population MAD로 정규화한 새 metric이 필요하면 I_d의 lower bound>0을 별도 요구해야 하며 현재 설계는 그 metric으로 바꾸지 않는다.

sample dhat=0 → NON_COMPUTABLE_ZERO_SCALE. I_d lower=0 또는 infinite interval은 삭제할 표본이 아니라 불확실성 상태다. 넓은 구간·비축소 구간을 PASS나 “0 변화”로 바꾸지 않는다.

## 8. Stationarity / dependence 모델과 승인

### 8.1 요구하는 정상성 수준

| 개념 | 의미 / 본 설계 사용 |
|---|---|
| strict stationarity | 모든 유한차원 law가 시간 이동에 불변. Z의 theorem-level 요구 |
| weak stationarity | 평균·공분산 안정; 존재하는 경우의 2차 조건. indicator-process joint law 보장에 부족 |
| distributional stability | 동일 marginal만을 뜻하면 lag/joint law 안정까지 보장하지 못함 |
| local stationarity | 시간에 따라 변하는 근사 law. 이번 단일 F_h·long-run covariance와 다른 정리 필요 |
| piecewise stationarity | 알려진 구간별 law. 전체 record를 하나로 분석하는 본 계약의 대체 조건이 아님 |

StockScope의 이번 inferential claim은 **기록된 aligned feature 과정 Z의 scoped strict-stationary sampling model**이다. 금리 level Y 자체의 정상성, 모든 향후 시점의 정상성, 정책의 시장 안전성을 요구하거나 인증하는 것으로 확대하지 않는다.

W가 strict stationary/mixing인 모형을 제시하는 경우에는 Z가 길이 10의 measurable transform이므로 α_Z(r)≤α_W(r-9), r>9를 사용할 수 있다. 그러나 W 모형이 없으면 Z에 대한 직접 승인도 가능하다. horizon overlap를 dependence 종결 시점으로 해석해서는 안 된다.

### 8.2 세 층의 분리

| 층 | 산출물 | 허용 판정 |
|---|---|---|
| Assumption-level declaration | process·scope·stationarity·rate·nondegenerate limit·근거·제한·책임자 | PROPOSED / ACCEPTED_FOR_MODEL_USE / REJECTED |
| Diagnostic-level evidence | source 구조, 고정 구간 ECDF, indicator lag covariance 등 | VERIFIED_FINITE_FACT / INFORMATIONAL / CONTRADICTION_REQUIRES_REVIEW |
| Operational acceptance | 정확한 method/scope에 묶인 서명 및 모든 contradiction disposition | MODEL_USE_ACCEPTED / UNRESOLVED / NOT_ACCEPTED |

자동 p-value threshold나 관행적 5%를 추가하지 않는다. finite diagnostics에 PASS cutoff가 없으면 numerical acceptance field는 null이다. missing cutoff를 “검사 생략 후 승인”으로 처리하지 않는다. 모델 사용 승인은 수치검정 통과를 대신하는 사실 주장이 아니라 조건부 추론의 적용 책임을 명시하는 별도 결정이다.

### 8.3 A5 acceptance의 정확한 조건

Model owner가 선언할 항목:

- 명시된 source/vintage/feature 규칙으로 정의된 Z의 전체 분석 scope에 하나의 invariant joint law를 사용한다.
- 알려진 source 정의·측정 resolution·calendar/native-order 변경과 model-scope 불일치가 없는지 근거를 설명한다.
- 비정상 금리 level과 stationary feature model을 혼동하지 않았음을 확인한다.
- §11 진단 전체에 대해 고정된 해석 항목별로 rationale을 제공한다. 해석 불가능, 알려진 structural break 또는 반대 근거는 UNRESOLVED/NOT_ACCEPTED로 남긴다.
- regime 변경을 사후 segmentation이나 cutoff 이동으로 숨기지 않는다.

독립 method reviewer가 exact scope와 조건부 claim의 사용을 승인하고, 승인 근거·날짜·효력 조건·revocation trigger를 남겨야 A5=ASSUMPTION_ACCEPTED_FOR_MODEL_USE다. “금융데이터는 보통 정상” 또는 “기각되지 않음”만 있는 문서는 불충분하다. 실제 owner/reviewer는 본 문서가 임명하지 않는다.

### 8.4 A6 acceptance의 정확한 조건

a>15/2를 완화하지 않는다. 이는 현 primary의 충분조건이며 모든 통계 방법의 필수조건이라고 주장하지 않는다. 요구 declaration은 “어떤 a>15/2에 대해 α_Z(r)=O(r^-a)”이고 empirical a 추정치를 승인 수단으로 요구하지 않는다.

owner/reviewer는 joint 시간의존성을 포함한 working-model 근거, 장기 의존성에 대한 한계, 반대 진단의 disposition, long-run indicator Gaussian root 비퇴화 및 quantile continuity의 적용 근거를 기록한다. 특정 stationary Markov/innovation model의 정리를 제시하는 경우 그 정리의 모든 가정을 별도 대조한다. 존재하지 않는 모형이나 검증 안 된 mixing 증명을 대신 만들어 주지 않는다.

finite ACF가 작거나 ell=43이 계산된다는 사실은 이 승인 조건을 충족하지 않는다. model-use declaration과 reviewer acceptance가 없으면 A6=UNRESOLVED다. 수학적으로 증명된 mixing이 아니라는 limitations 필드는 항상 남긴다.

이 조건을 받아들일 수 없다면 G-A는 BLOCKED로 유지한다. 더 약한 dependence, nonstationary inference 또는 distribution-free guarantee는 새로운 method version의 별도 과제다. R4 실행 중 자동 변경하지 않는다.

## 9. 새 G-A acceptance contract

### 9.1 공통 evidence 및 state 규칙

Permitted evidence source의 약칭:

- P1: 사용자가 명시적으로 제공한 exact frozen DEV 입력 한 개와 그 내부 source lineage. 다음 구현에서는 runtime 밖의 명시적 복사본만 받는다.
- P2: §2.3의 명시된 이론·설계 문서 및 R3의 입력 진단 기록.
- P3: 원 논문, 본 문서의 D1~D4, 독립된 theorem review 및 outcome-independent algebraic/synthetic 검증.
- P4: exact method/scope에 결속된 model owner와 method reviewer의 선언·승인·revocation 기록.

**모든 gate의 Forbidden evidence source F0**: Holdout 데이터·경로 탐색·존재 확인·metadata·hash·표본 수·날짜; Development adequacy 산출물 및 forward envelope·passing candidate·지원 추천; Production 결과; DB/runtime; 새 다운로드로 재생성한 대체 DEV; 사후 선택된 source window/segment. 기존 문서에 적힌 금지사항의 문장 자체는 정책이며, 금지 대상의 실제 값과 구분한다. 금지 값은 수집하지 않는다.

각 gate의 accepted evidence에는 source ID, method ID, scope ID, evidence hash, 수행자/검토자, rule version을 붙인다. 과거 R3의 MATHEMATICALLY_VERIFIED를 새 실행 결과로 복사하지 않는다.

Finite deterministic 사실의 상태는 MATHEMATICALLY_VERIFIED, 모집단 모델 사용은 ASSUMPTION_ACCEPTED_FOR_MODEL_USE로 구분한다. REPLACED는 migration 표지이고 성공 판정이 아니다. UNRESOLVED와 NOT_ACCEPTED 모두 전체 gate를 막는다. true/false 필드에서 null을 true로 해석하지 않는다.

### 9.2 공통 선행 gate

**Gate ID: G0 — Clean evidence scope**

- Purpose: 오염된 context나 forbidden source를 사용한 승인을 방지한다.
- Required evidence: 실행 전 input allowlist, source-access audit, 문맥 isolation 확인, prohibited-input guard.
- Permitted evidence source: P1/P2의 허용 범위와 실행 access log.
- Forbidden evidence source: F0 전체. 감사를 이유로 금지 경로나 값을 찾지 않는다.
- Acceptance rule: clean execution evidence가 명시적으로 YES이며 unauthorized retrieval 0; R3의 non-certified evidence는 역사적 참고로만 표시.
- Failure rule: scope 오염, 로그 누락, 불명확한 source 또는 clean 상태 unknown.
- Fail-closed behavior: 평가 즉시 중단; 이유 코드만 남기고 금지 값을 복제하지 않는다.
- Downstream effect: G-A BLOCKED; 나머지 값이 통과해도 override 불가.

**Gate ID: G1 — Theorem / target / version review**

- Purpose: 구현 테스트와 수학적 유효성 승인을 분리한다.
- Required evidence: D1 lattice restriction, D2 span dominance, D3 simultaneous event, D4 inversion/MAD·selection 증명 검토; target migration 승인; α∈(0,1)의 symbolic interface.
- Permitted evidence source: P2/P3/P4.
- Forbidden evidence source: F0 전체 및 “DEV에서 잘 작동했다”는 theorem 대체 근거.
- Acceptance rule: 지정 reviewer가 정확한 문서·method hash와 조건부 보수적 claim을 승인; 미해결 proof objection 0.
- Failure rule: proof 오류·새 target 미승인·누락된 theorem 조건·approval 부재.
- Fail-closed behavior: METHOD_REVIEW_REQUIRED; 코드 실행 성공으로 대체하지 않는다.
- Downstream effect: G-A BLOCKED. reviewer 수정이 필요하면 새 설계 버전; R3 역사 불변.

### 9.3 A0~A10별 계약

**Gate ID: A0 — Evidence lineage / RETAIN**

- Purpose: exact DEV identity 및 source-only 실행 확보.
- Required evidence: canonical dataset ID/hash, 내부 row/feature lineage 검증, 별도의 transport bytes digest, 명시적 input manifest.
- Permitted evidence source: P1; P2의 expected DEV identity.
- Forbidden evidence source: F0.
- Acceptance rule: 기존 canonical identity 알고리즘으로 expected identity와 정확히 일치; 모든 필수 lineage 검증 성공. canonical hash와 단순 file SHA-256을 혼동하지 않는다.
- Failure rule: 파일 부재·identity mismatch·대체 vintage·알 수 없는 canonicalization.
- Fail-closed behavior: SOURCE_UNAVAILABLE 또는 LINEAGE_MISMATCH; source 자동 검색/복구 없음.
- Downstream effect: source-dependent A1~A10 실행 중단; G-A BLOCKED.

**Gate ID: A1 — Native-position completeness / RETAIN**

- Purpose: 시간축 압축·누락 보간을 막는다.
- Required evidence: ordered native position/date map, warmup, 중복·결측 검사.
- Permitted evidence source: P1.
- Forbidden evidence source: F0 및 결과 artifact에서 원자료 역추론.
- Acceptance rule: 선언된 native-position contract의 모든 required position이 정확히 한 번 존재하고 chronology가 일치한다.
- Failure rule: 누락·충돌·비수치값·순서 불명.
- Fail-closed behavior: NATIVE_POSITION_INCOMPLETE; 행 삭제·imputation 없음.
- Downstream effect: A2/A3 중단, G-A BLOCKED.

**Gate ID: A2 — W→X identity / RETAIN**

- Purpose: 실제 bp feature와 theoretical finite-window representation을 연결한다.
- Required evidence: 각 row 및 1/5/10obs의 exact Decimal 또는 rational 비교.
- Permitted evidence source: P1/P2의 feature semantics.
- Forbidden evidence source: F0 및 float tolerance로 equality를 구제하는 규칙.
- Acceptance rule: 모든 허용 비교에서 endpoint 차이와 increment 합이 정확히 동일.
- Failure rule: mismatch 하나 이상, 단위·warmup 불일치.
- Fail-closed behavior: REPRESENTATION_MISMATCH.
- Downstream effect: G-A BLOCKED; 잘 맞는 horizon만 선택 불가.

**Gate ID: A3 — Joint alignment / RETAIN**

- Purpose: 세 horizon의 공동 index 및 dependence 보존.
- Required evidence: Z row map, 공통 endpoint, n, horizon 순서, cutoff scope.
- Permitted evidence source: P1/P2.
- Forbidden evidence source: F0 및 독립적인 horizon별 complete-case 축소.
- Acceptance rule: 모든 분석 row에 3좌표가 있고 동일 native endpoint에 대응한다.
- Failure rule: coordinate별 다른 시간축·부분 누락·n 불일치.
- Fail-closed behavior: JOINT_ALIGNMENT_INVALID.
- Downstream effect: 공통 domain/다변량 추론 생성 금지; G-A BLOCKED.

**Gate ID: A4 — Observed-law lattice / indicator contract / REPLACE**

- Purpose: continuity 대신 arbitrary atom law의 exact ECDF 사용을 확인한다.
- Required evidence: source precision 규칙, 정수 bp membership, 원값/ties 보존, D1 승인, left-limit와 right-continuous indicator 규칙.
- Permitted evidence source: P1/P2/P3.
- Forbidden evidence source: F0, jitter·randomized ranks·unobserved support 삭제.
- Acceptance rule: source normalization과 실제 값이 lattice 계약에 정확히 부합하고 D1의 raw-indicator 구현 규칙이 충족된다. tie 비율 상한은 없다.
- Population scope rule: 정수 bp support를 모집단 규칙으로 사용할 때에는 canonical 측정/표현 규칙의 근거를 함께 제시한다. 관측 off-grid count=0만으로 미관측 값의 support를 증명하지 않는다. 이 근거가 없으면 lattice-specific applicability는 UNRESOLVED로 둔다.
- Failure rule: 격자 불일치·측정 convention 미정·tie 변경·proof review 부재.
- Fail-closed behavior: OBSERVED_LAW_CONTRACT_MISMATCH 또는 THEOREM_TRANSFER_UNREVIEWED.
- Downstream effect: G-A BLOCKED; A7/A9의 regular density 검사로 회귀하지 않는다.

**Gate ID: A5 — Scoped strict-stationary model-use / MODIFY**

- Purpose: 단일 F_h 및 invariant serial law의 적용 scope 승인.
- Required evidence: §8.3 declaration, §11 고정 진단, 모든 반대 근거 disposition, owner/reviewer 승인.
- Permitted evidence source: P1/P2/P4; source 정의에 관한 outcome-independent 근거.
- Forbidden evidence source: F0, 사후 segmentation, p-value 비기각만을 이용한 승인.
- Acceptance rule: 전체 scope에 대한 §8.3 조건을 충족한 유효한 승인. finite 진단 결과는 proof로 표기하지 않는다.
- Failure rule: 선언·서명·근거 누락, scope mismatch, 미해결 contradiction, 승인 취소.
- Fail-closed behavior: UNRESOLVED 또는 ASSUMPTION_NOT_ACCEPTED.
- Downstream effect: G-A BLOCKED; 더 짧은 구간으로 자동 재실행하지 않는다.

**Gate ID: A6 — Mixing / limit-root model-use / MODIFY**

- Purpose: D1/D2가 요구하는 dependence 및 critical-value 적용 조건 승인.
- Required evidence: §8.4 declaration, joint indicator lag evidence, a>15/2 조건 대조, Gaussian root 비퇴화/quantile continuity 검토.
- Permitted evidence source: P1/P2/P3/P4.
- Forbidden evidence source: F0, ACF cutoff로 mixing exponent를 “검증”한 결과.
- Acceptance rule: 해당 모집단 조건의 scope-specific model-use가 명시적으로 승인되고 theoretical 조건의 누락이 없다.
- Failure rule: long memory 반대 근거 미처리, 조건 거절·미정, 완전퇴화 root의 근거 없는 calibration.
- Fail-closed behavior: DEPENDENCE_MODEL_UNRESOLVED 또는 ROOT_REGULARITY_UNRESOLVED.
- Downstream effect: G-A BLOCKED; iid·self-normalized fallback 없음.

**Gate ID: A7 — Median set / inversion contract / REPLACE**

- Purpose: density 없이 기존 midpoint median 및 그 전체 uncertainty interval을 보존한다.
- Required evidence: ≥와 >의 quantile 구별, M(G), even-sample midpoint, §7.2 포함관계 증명·검증.
- Permitted evidence source: P1의 입력 진단 및 P2/P3.
- Forbidden evidence source: F0, finite ties로 population uniqueness를 승인하는 주장.
- Acceptance rule: exact midpoint가 기존 convention과 일치하고 boundary/tail 규칙 및 theorem review가 충족된다. median 비유일 자체는 실패가 아니다.
- Failure rule: lower median 대체·plateau 삭제·무한 endpoint clipping·검토 부재.
- Fail-closed behavior: MEDIAN_INVERSION_INVALID.
- Downstream effect: G-A BLOCKED; 좁은 구간을 만들기 위한 tie 해소 금지.

**Gate ID: A8 — Finite anchor scale / MODIFY**

- Purpose: 실제 metric 분모의 computability와 population 추론 범위를 구별한다.
- Required evidence: 전체 approved-domain anchor의 raw MAD zero/nonfinite mask, exact convention; I_d의 zero/infinite 출력 규칙.
- Permitted evidence source: P1/P2/P3.
- Forbidden evidence source: F0 및 zero 사례 제거·epsilon rescue.
- Acceptance rule: 현재 DEV 적용 승인을 위해 모든 required anchor의 sample MAD>0; future engine의 zero/infinite handling 계약도 승인되어야 한다.
- Failure rule: anchor 하나라도 sample MAD=0 또는 nonfinite. “population MAD 양수 미증명”은 삭제된 density route의 자동 failure가 아니라 명시적 uncertainty 상태다.
- Fail-closed behavior: NON_COMPUTABLE_ZERO_SCALE; 일부 anchor 제외 후 공통 N을 반환하지 않는다.
- Downstream effect: 해당 DEV applicability G-A BLOCKED. 현재 R3 positive-MAD 사실은 새 clean 실행에서 재확인한다.

**Gate ID: A9 — MAD outer projection / REPLACE**

- Purpose: center 추정오차와 이산 MAD의 비정규성을 동시에 처리.
- Required evidence: §7.3의 2e bound, center radius, quantile Lipschitz transfer, zero/infinite case 검토.
- Permitted evidence source: P2/P3; P1의 deviation ties/quantiles 진단.
- Forbidden evidence source: F0 및 estimated median을 true center처럼 고정한 density 추론.
- Acceptance rule: proof와 exact reference cases에서 outer inclusion, center propagation, endpoint semantics가 일치한다.
- Failure rule: center uncertainty 누락·2e를 e로 축소·무한/0 bound 삭제.
- Fail-closed behavior: MAD_PROJECTION_INVALID.
- Downstream effect: G-A BLOCKED. I_d가 넓은 것만으로 원자료를 불량 판정하지 않는다.

**Gate ID: A10 — Calibration profile / REPLACE**

- Purpose: 기존 preprocessor 재현과 새 추론 calibration의 유효성을 분리.
- Required evidence: Λ_n={1..n}, exact covariance-Parzen 식, full-sample centering, 동일 r의 공통 g, D2 지배 증명 승인; 기존 R2 audit 결과의 재현 기록.
- Permitted evidence source: P1/P2/P3. 실제 bootstrap 수치 실행은 향후 S6C 이후다.
- Forbidden evidence source: F0, favorable span 선택, 불완전 span max, manual bandwidth/PSD repair.
- Acceptance rule: 새 profile의 정의·증명·future computability/failure 계약이 일치; R2 audit 불일치는 원인 규명 전 unresolved. n개 span 모두의 정리 일치성을 요구하는 잘못된 판정은 하지 않는다.
- Failure rule: 단일 ell=43으로 새 profile 대체, kernel 역할 혼동, unreviewed proof, 임의 regularization 또는 numerical default.
- Fail-closed behavior: CALIBRATION_CONTRACT_INVALID; 새 numerical engine 미승인은 §15의 execution guard로 분리.
- Downstream effect: G-A BLOCKED. 모든 R4 단위검증 성공만으로 S6C numerical approval을 만들지 않는다.

### 9.4 전체 평가 순서와 PASS 조건

~~~
G0 clean scope
 -> A0 lineage
 -> A1/A2/A3 structure
 -> A4 observed-law contract
 -> A7/A8/A9 functional/computability contracts
 -> A10 method calibration contract
 -> A5/A6 model-use review
 -> G1 final theorem / target / version reconciliation
 -> G-A decision
~~~

G-A=PASS iff G0/G1 accepted AND A0~A10의 해당 acceptance rule 전부 충족 AND 모든 evidence가 동일 method/source/domain scope에 결속 AND active blocker=0.

통과 시 상태명은 METHOD_APPROVED_CONDITIONAL_ON_DECLARED_MODEL이다. 기존 METHOD_APPROVED label을 사용해야 하면 동일 limitation 필드를 필수로 붙인다. 모집단 가정이 수학적으로 검증되었다는 label은 금지한다.

G-A는 α 값을 정하지 않고, 승인 가능한 α∈(0,1)에 대해 수학적 procedure family를 승인한다. 실제 α는 G-B, PRNG·Monte Carlo error·factorization 수치 오차는 S6C다. 이 분리 덕분에 G-A와 G-B가 서로의 숫자를 먼저 요구하는 순환 의존을 만들지 않는다.

## 10. A0~A10 migration mapping

| ID | 기존 의미 | 조치 | 새 의미 | 기존 R3 evidence 재사용 한계 |
|---|---|---|---|---|
| A0 | exact DEV lineage | RETAIN | 동일 + 실행 identity 분리 | 참고만; clean replay 필수 |
| A1 | native completeness | RETAIN | 동일 | 동일 |
| A2 | W→X equality | RETAIN | 동일 | 동일 |
| A3 | joint alignment | RETAIN | 동일 | 동일 |
| A4 | continuous law / atoms 호환 | REPLACE | lattice indicator + D1 | ties는 허용 사실; old rejection은 역사 보존 |
| A5 | stationarity compatibility | MODIFY | strict scoped model-use 3층 승인 | 미승인 상태 승계 |
| A6 | mixing compatibility | MODIFY | 동일 exponent + limit-root 조건 + 승인 | finite proof로 승격 금지 |
| A7 | unique median / density | REPLACE | midpoint median, median set, inversion | ties 진단 보존; density 조건 REMOVE |
| A8 | positive MAD | MODIFY | sample computability; uncertainty의 0/∞ 보존 | clean replay 전 단정 금지 |
| A9 | MAD local density | REPLACE | center-aware outer projection | density 조건 REMOVE |
| A10 | adaptive preprocessor 계산 | REPLACE | span-envelope theorem/profile + legacy audit | m/L/b/ell은 역사적 expected 결과 |

REMOVE는 A7/A9 내부의 밀도·미분 의무에 적용한다. gate ID 자체를 지우지 않아 audit continuity를 유지한다. old gate status와 new gate status는 서로 다른 version namespace에 저장한다. REPLACE를 old gate PASS로 덮어쓰지 않는다.

## 11. Development-only 검증 절차

### 11.1 입력과 출력

입력은 네 객체로 고정한다.

1. ExplicitDevInput: runtime 밖의 명시적 exact frozen DEV JSON 한 개. directory glob, 경로 추측, 인접 파일 열람 없음.
2. DesignManifest: 본 설계·source normalization·candidate domain·gate rule의 버전과 content hash.
3. ModelUseDossier: A5/A6 declaration 및 승인. 없으면 빈 객체 대신 MISSING으로 기록한다.
4. TheoremReviewDossier: G1 및 D1~D4 review. 없으면 G-A는 반드시 BLOCKED다.

출력은 research evidence 객체와 사람이 읽는 gate report다. bootstrap replicate, α 입력, policy tolerance, adequacy verdict, forward envelope, candidate survival, support recommendation은 이 diagnostic interface에 존재하지 않는다.

### 11.2 고정 계산 순서

1. allowlist와 clean-scope audit를 검증한다. unauthorized URI/path는 값 공개 없이 즉시 reject.
2. transport bytes digest와 canonical project identity를 별도로 검증한다. 파일 digest가 canonical dataset hash와 다르다고 임의 변환하지 않는다.
3. native map/warmup/chronology를 검증하고 W 및 공동 Z를 exact arithmetic으로 복구한다.
4. 정수 bp membership, marginal frequency table, joint duplicate summary를 산출한다. duplicates를 제거하지 않는다.
5. 각 h에서 full-record q^-/q^+, midpoint median, raw MAD 및 각 지점의 left/right cumulative counts를 기록한다.
6. n에서 N_0=floor((n+9)/10)를 계산한다. N=N_0..n-1의 raw MAD zero mask만 검사한다. 모든 later t와의 movement 또는 envelope는 계산하지 않는다.
7. 아래의 고정 descriptive stationarity/dependence battery를 수행한다.
8. 기존 R2 preprocessor를 입력 진단으로만 재현하고 expected m/L/b/ell과 비교한다. actual output과 mismatch 이유를 남기며 expected 값으로 강제 교정하지 않는다.
9. 새 calibration의 symbolic Λ_n coverage, kernel/centering/coupling 계약을 확인한다. real DEV로 Gaussian draw, critical value 또는 band를 계산하지 않는다.
10. deterministic diagnostic artifact를 seal한 뒤, owner/reviewer의 model/theorem disposition을 연결한다. diagnostic을 승인 의견에 맞춰 재계산하지 않는다.
11. §9의 conjunction으로 G-A를 판정한다. missing signature, 미해결 contradiction, hash mismatch는 BLOCKED다.

### 11.3 필요한 통계량과 진단량

| 영역 | 고정 산출량 | 판정 역할 |
|---|---|---|
| lineage/structure | 내부 identity 검증 목록, row map, missing/duplicate/native gap count | exact structural gate |
| quantization | exact off-grid count, marginal counts, joint duplicate count | off-grid는 mismatch; tie 크기에 cutoff 없음 |
| median | q^-, q^+, midpoint, Fhat(q^- -), Fhat(q^-), Fhat(q^+), tie multiplicity | finite fact; population uniqueness/density 증명 아님 |
| MAD | deviation support/ties, raw MAD, anchor zero mask | sample computability |
| chronological marginal drift | 10개의 연속 비중첩 bin의 ECDF·median interval·MAD·frequency table; 각 bin 대 전체 cdf의 sup distance | INFORMATIONAL, numeric PASS cutoff 없음 |
| serial dependence | 각 raw coordinate와 각 관측 support threshold indicator의 모든 lag r=1..n-1 covariance; 유효 pair count 동반 | INFORMATIONAL; a 추정/검증 금지 |
| overlap/cross-horizon | 동일 native position 관계, horizon pair lag cross-covariance | 구조 및 정보성; independence 증거로 사용 금지 |
| R2 audit | coordinate m, L, gamma/delta 유한성, b, effective ell, rounding mode | 재현성; 새 추론 유효성 대체 아님 |

10-bin은 기존 exact tenth domain을 이용한 **전망적으로 고정된 설명용 partition**이다. bin j는 floor((j-1)n/10)+1..floor(jn/10), j=1..10. κ가 population segmentation 근거라는 의미는 아니다. 빈 bin이면 명시적으로 EMPTY를 기록하고 임의 병합하지 않는다. 전체 scope나 candidate domain은 변하지 않는다.

lag covariance는 a_i의 full-sample 평균을 이용한 n^-1 sum_(i=1..n-r)(a_i-abar)(b_(i+r)-bbar)로 고정한다. 분모 n-r로 임의 교체하지 않는다. correlation을 추가할 경우 denominator=0은 UNDEFINED다. 이 숫자로 “mixing proven”을 만들지 않는다.

이 battery는 금지된 **anchor N × 모든 later prefix t** adequacy 계산과 다르다. disjoint descriptive bins와 input-level dependence만 다룬다. 값이 크다는 이유로 bin 수·범위·진단 family를 바꾸지 않는다.

### 11.4 Acceptance / fail-close

정확한 equality, identity, domain arithmetic, sample denominator positivity는 자동 판정할 수 있다. stationarity·mixing·root regularity는 자동 판정하지 않는다. 진단은 raw 사실과 한계를 기록하고 P4 review가 승인/거절/미정으로 분리 판정한다.

새로운 quantitative break-test cutoff, tie cutoff, density cutoff, minimum effective sample size, lag-decay cutoff는 **UNRESOLVED_PARAMETER / NOT_USED**다. R4 구현자가 값을 넣을 필요가 없다. 해당 수치가 필요한 별도 test를 추가하려면 prospective 근거·버전 변경부터 수행해야 한다.

다음 중 하나면 fail-close: 불명확 input, clean audit 부재, identity 실패, 구조 실패, sample zero scale, proof/approval 미정, 금지 source exposure, output schema extra field, nonfinite 계산, preprocessor mismatch, 승인 만료/취소. reason code는 나열하되 gate success를 숨긴 default로 만들지 않는다.

### 11.5 재현성 / determinism

- source text → Decimal → exact bp rational 순서와 기존 normalization version을 고정한다.
- frequency/ECDF cumulative counts는 integer로 계산하고 quantile 비교에는 rational 1/2를 사용한다.
- horizon 순서 [1,5,10], native row 오름차순, support 수치 오름차순, gate ID 순서를 고정한다.
- midpoint와 MAD의 유리수 결과를 무손실 문자열 또는 numerator/denominator로 저장한다.
- 진단 covariance는 rational reference result를 기준으로 한다. R2 legacy floating output은 기존 구현의 정확한 arithmetic/rounding version과 결속하며, 비교 tolerance가 필요하면 S6C 수치 근거 없이 새 값을 만들지 않는다.
- diagnostic semantic hash에서 wall-clock time, 절대 local path, 로그 순서 등 비의미적 metadata를 제외한다. provenance는 별도 sealed envelope로 보존한다.
- 같은 입력·계약·arithmetic version에는 같은 diagnostic payload/hash가 나와야 한다. 인간 승인 dossier는 별도 identity이므로 승인 갱신으로 diagnostic을 다시 쓰지 않는다.
- R4는 stochastic computation을 하지 않는다. 따라서 seed 선택도 필요 없다.

## 12. Sequential / multiplier framework 영향

보존: 공동 Z, full-sample empirical centering, sequential prefix indexing, horizon별 독립 resampling 금지, 하나의 replicate가 모든 required indices에 공유되는 원칙, interior domain, simultaneous selection 보호.

교체:

| 기존 계약 | 변경 이유 | 새 계약 | migration impact |
|---|---|---|---|
| continuous empirical-process 적용 | lattice 관측 law | D1 indicator restriction | 새 theorem certificate |
| regular nonlinear functional law | density / uniqueness 충돌 | CDF event의 set-valued error coverage | target ID와 statistical claim 변경 |
| moving-average Parzen weights | 정확 covariance theorem과 직접 연결 | Gaussian covariance-Parzen | kernel의 역할·multiplier ID 변경 |
| adaptive single ell | random tuning의 유효성을 finite 재현으로 대체 불가 | 모든 ell=1..n의 max root | numerical cost·conservatism 증가 |
| rank-grid IMSE가 추론 핵심 | 원자료 cdf band에 필요한 조건과 분리 | 원 indicator sup, legacy audit만 보존 | rank/tie convention은 과거 audit에만 사용 |

**m=[1,5,10], L=10, b=22, ell=43을 유지할 수 있는가?**

- 기존 R3 evidence 및 R2 automatic-rule 재현 기대값으로 **유지**한다.
- 새 primary의 **단일 추론 calibration으로 유지할 수 없다**.
- ell=43은 n=1999에서 Λ_n에 포함되지만 새 covariance 생성기의 ell=43 law는 기존 moving-average b=22와 동일하다고 주장하지 않는다.
- coordinate m은 lag-selector output이며 horizon labels와 뜻이 다르다.
- b는 새 covariance generator에 사용하지 않는다. old b→ell 변환과 manual fallback=NO는 legacy audit에 남는다.

새 방식에서도 미래 PRNG seed, normal generator, matrix factorization, finite precision, Monte Carlo quantile precision은 S6C 소유다. Gaussian vector의 principal square root는 수학적 유일성을 정하고, 그것만으로 모든 플랫폼의 bitwise equality가 확보된다고 주장하지 않는다.

## 13. Candidate domain 영향

R2A CandidateDomainContract V1 및 exact κ=1/10은 변경하지 않는다.

~~~
n = aligned 3D feature rows
N_0 = floor((n+9)/10)
C_n = {N_0,...,n-1}
prefixes used by simultaneous event = {N_0,...,n}
pairs for later authorized evaluation = {N<t<=n, N in C_n}
~~~

n=1999에서 N_0=200이라는 값은 순수 domain arithmetic 예시이며 적정성 결과나 추천이 아니다. domain 밖은 OUTSIDE_APPROVED_METHOD_DOMAIN이지 FAIL/INADEQUATE가 아니다. κ를 작게 만들거나 n을 바꾸어 유리한 candidate를 확보하지 않는다.

새 calibration span ell과 N을 연결하는 N≥ell 또는 N≥2ell 규칙을 만들지 않는다. 큰 ell도 보수적 max에 들어가며 그 자체가 candidate 하한을 바꾸지 않는다. finite zero scale 등 structural noncomputability는 추가 predicate로 남는다.

## 14. G-A 이후 G-B 진입 / 승인 조건

G-A는 통계적 방법의 적용 가능성을 승인하는 gate이고, G-B는 독립적인 operational risk-budget 및 승인 권한을 확인하는 gate다. 둘은 대체 관계가 아니다.

Track B의 독립적인 synthetic/analytical policy 연구는 기존 architecture대로 G-A 전에 진행할 수 있다. 다만 **새 primary에 결속된 실행 가능한 G-B approval의 최종 심사**는 다음 패키지를 G-A 이후 전달받아야 한다.

1. G-A PASS certificate와 정확한 method/source/domain/assumption IDs.
2. 새 target의 문장: 공동 prefix sampling-error coverage이며 repeat-record law confidence region, 미래 안정성 또는 population drift 검정이 아님.
3. 관측 T/L/S는 보존하지만 uncertainty semantics가 바뀌었다는 migration statement.
4. 넓거나 무한인 I_m/I_d, sample zero scale, incomplete numerical computation의 fail-close 해석.
5. τ_T/τ_L/τ_S의 단위, α_stat의 family event, expiry/revocation 적용 범위.

G-B PASS에는 별도로 다음이 필요하다: 실제 risk policy owner/approval authority 임명, outcome-independent 수치 근거, 정확한 τ 및 α의 승인, method/target compatibility, review/expiry/revocation 계약, 미해결 conflict 0. 현재 수치나 임명은 이 문서가 생성하지 않는다.

특히 “stationary population prefix 차이=0”이라는 모형적 사실은 adequacy 증거가 아니다. 관측 movement와 sampling-error enclosure를 reference reuse에 어떻게 사용할지 operational 의미를 승인해야 한다. τ를 통과하면 어떤 제품상 손실이 제한된다고 주장하려면 그 연결 근거가 필요하다. 본 method coverage만으로 false-adequacy probability가 자동으로 α 이하라고 주장하지 않는다.

S6B는 새 event를 받아 α_stat 의미를 재검토해야 한다. 기존 target에 묶인 policy를 이름만 바꾸어 승계하지 않는다. γ_repeat는 계속 method 밖에 남는다. G-A가 PASS해도 G-B는 독립 승인 전까지 BLOCKED다.

## 15. Reference Adequacy 재개 조건

아래 조건은 모두 필요하며 이 문서 작성이나 R4 diagnostic 성공만으로 충족되지 않는다.

1. 새 method/assumption/theorem certificate에 대한 G-A PASS.
2. 같은 target 및 metric scope에 대한 G-B PASS.
3. S6C convergence review: 정확한 계약 결속, deterministic numerical algorithm, Monte Carlo probability error 및 arithmetic error, 자원 중단 처리, root quantile 산출 규칙 승인.
4. 별도 승인된 미래 V4 preregistration. 기존 V3는 불변으로 보존.
5. 별도로 허가된 evaluator 구현 및 검증 완료.
6. 명시적으로 승인된 Development-only evaluation scope와 exact frozen source.

그 다음에만 Development Reference Adequacy 평가를 재개할 수 있다. Holdout은 별도 명시적 사용자 허가 전 계속 닫혀 있고, Development 평가 완료가 그 허가를 대신하지 않는다. Production 반영도 별도 절차다.

Monte Carlo 관점에서 c_env는 conditional quantile의 하향 추정으로 coverage를 훼손하면 안 된다. S6C는 order-statistic/binomial bound 등 이론적 근거로 conservative quantile 상계를 만들고, δ_MC와 α_stat의 결합 오차 문장을 승인해야 한다. B=1000, seed=42, δ_MC=0.001 같은 기본값을 여기서 정하지 않는다. covariance PSD 실패에 ridge·eigenvalue clipping을 자동 적용하지 않는다.

## 16. Artifact / schema 설계

이번에 실제 JSON artifact를 만들지 않는다. 아래는 다음 구현의 schema 명세이며 method protocol V4가 아니다.

### 16.1 immutable design / diagnostic / approval 분리

~~~
MethodDesignManifest
  schema_id: NEXT6E_S6A_R4_METHOD_DESIGN_V1
  document_sha256
  source_refs: {main_sha, r3_branch_sha, document_blob_ids}
  method_id, target_id
  parent_method_id, migration_mapping
  domain: {contract_id, kappa_num:1, kappa_den:10}
  statistic: {ecdf_rule, median_rule, mad_rule, zero_scale_rule}
  calibration:
    family: GAUSSIAN_COVARIANCE_MULTIPLIER_SPAN_ENVELOPE
    span_set: ALL_INTEGERS_1_THROUGH_N
    covariance_kernel: PARZEN_COVARIANCE_V1
    centering: FULL_SAMPLE_EMPIRICAL
    coupling: SHARED_GAUSSIAN_VECTOR_PER_REPLICATE
  theorem_conditions[]
  proof_units: [D1,D2,D3,D4]
  status: DESIGN_SELECTED_NOT_EXECUTION_APPROVED

DevAssumptionDiagnostic
  schema_id: NEXT6E_S6A_R4_DEV_DIAGNOSTIC_V1
  design_hash
  source: {dataset_id, canonical_dataset_hash, canonicalization_version,
           transport_digest, native_map_hash}
  scope: {development_only:true, input_allowlist_id, isolation_audit_id}
  representation: {units, horizon_order, n, warmup_rule, alignment_hash}
  domain: {domain_id, lower_bound, upper_anchor}
  diagnostics:
    lineage_checks[], native_checks[], representation_checks[]
    lattice_counts[], frequency_tables[], median_quantile_counts[]
    mad_diagnostics[], zero_scale_mask
    chronological_bin_summaries[], indicator_lag_covariances[]
    legacy_r2_profile_audit
  arithmetic_profile_id
  computation_status
  failure_codes[]
  semantic_payload_hash

ModelUseDossier
  schema_id: NEXT6E_S6A_R4_MODEL_USE_V1
  method_id, diagnostic_hash, source_scope_hash
  stationarity: {class:STRICT, rationale, evidence_refs[],
                 contradictions[], dispositions[], decision}
  dependence: {class:ALPHA_MIXING, rate:"exists a>15/2",
               rationale, evidence_refs[], contradictions[], dispositions[],
               nondegenerate_root_condition, quantile_continuity_review, decision}
  finite_sample_proof_claim:false
  owner_identity, reviewer_identity, authority_reference
  approval_reference, approved_scope, validity_rule, revocation_rule
  status

GateAssessment
  schema_id: NEXT6E_S6A_R4_GATE_ASSESSMENT_V1
  design_hash, diagnostic_hash, model_use_hash, theorem_review_hash
  gates[]:
    gate_id, migration_action, status, rule_id
    evidence_refs[], reason_codes[], reviewer_reference
  ga_status: PASS | BLOCKED
  ga_claim_scope
  gb_effect: NO_AUTOMATIC_PROMOTION
  downstream_execution_authorized:false
  assessment_hash
~~~

### 16.2 필드 / identity 규칙

- JSON unknown fields는 reject하는 closed schema다. 금지 결과용 필드는 schema에 두지 않는다.
- null은 미정이다. empty list는 없음으로 검증된 경우에만 사용하고 missing과 구별한다.
- 수치 진단에서 ±∞는 JSON NaN/Infinity 대신 {kind:NEG_INF/POS_INF}와 같은 tagged value로 표현한다.
- hashes는 UTF-8 canonical payload에 적용하고, key order·Unicode·decimal/rational serialization version을 manifest에 명시한다.
- forbidden URI나 내용을 담은 오류 message 대신 source class와 reason code만 남긴다.
- gate assessment는 diagnostic을 수정하지 않고 별도 생성한다. 승인 취소도 새 event이며 과거 artifact를 재기록하지 않는다.
- legacy profile 결과에는 LEGACY_REPRODUCTION_ONLY를 붙여 새 inferential profile과 혼동하지 않는다.

### 16.3 다음 구현의 제한된 출력 계약

R4는 진단 payload와 gate assessment만 출력할 수 있다. 권장 implementation API는 explicit DEV path + exact contract/dossier objects만 받으며, input directory·DB connection·network endpoint·result store 연결을 받지 않는다. 출력은 호출자가 정한 비runtime 연구 디렉터리로 한정한다.

stderr/stdout도 같은 closed schema 수준으로 민감 경로와 금지 결과 노출을 막는다. auto-find, fallback-source, evaluate, holdout 같은 확장 진입점은 R4 범위 밖이다.

## 17. Fail-closed / isolation 정책

| 상황 | 동작 | 금지되는 구제 |
|---|---|---|
| DEV 없음 / identity 다름 | SOURCE_UNAVAILABLE / LINEAGE_MISMATCH | 다운로드·다른 vintage·파일 탐색 |
| prohibited context 또는 source | ISOLATION_NOT_CERTIFIED, 즉시 중단 | 실제 금지 값을 audit에 재기록 |
| finite 구조 실패 | 해당 gate BLOCKED | chronology 압축·보간·부분 horizon |
| model-use 승인 미정 | A5/A6 UNRESOLVED | conventional assumption 자동 승인 |
| proof 검토 미완 | G1 BLOCKED | tests PASS를 정리 승인으로 사용 |
| zero sample MAD | NON_COMPUTABLE_ZERO_SCALE | epsilon denominator·candidate 삭제 |
| nonunique median / atom | 정해진 집합·구간 보존 | jitter·밀도 추정으로 강제 정규화 |
| interval unbounded | UNBOUNDED_UNCERTAINTY | observed support로 잘라내기 |
| span computation 미완 | RESOURCE_INCOMPLETE | 계산한 span들만으로 max 반환 |
| 수치 PSD / covariance 오류 | NUMERICAL_PROFILE_INVALID | ridge/eigenvalue repair default |
| G-A만 PASS | G-B/S6C 차단 유지 | 바로 V4/evaluator/evaluation |

한 가지 실패가 난 뒤 다른 입력이나 방법으로 자동 성공을 시도하지 않는다. 새로운 계약이 필요하면 새 version과 명시적 prospective rationale을 남긴다. 기존 R3 evidence와 과거 status는 immutable하다.

## 18. 다음 구현 단계 분해

기존 R1 → R2 → R2A → R3 명명 규칙에 따라 후속 단계는 **NEXT-6E-S6A-R4**로 제안한다. 기존 문서에 정의된 단계를 완료했다고 주장하는 이름이 아니다.

| 작업 단위 | 구현할 내용 | 산출물 / 완료 판정 |
|---|---|---|
| R4-1 Contract | §16 closed schema, migration IDs, deterministic gate rules | schema 및 rule review; old status 보존 |
| R4-2 Pure functional definitions | exact median endpoints/midpoint, deviation quantiles, §7 outer-bound helper | 독립된 exact reference 사례 통과 |
| R4-3 DEV diagnostics | §11 source-only 절차; 기존 R3 검증 자산 재사용 가능 | clean diagnostic payload/hash |
| R4-4 Evidence review interface | A5/A6/G1 dossier validation 및 reason codes | missing/revoked 승인에서 fail-close |
| R4-5 Gate evaluation | 모든 gate conjunction 및 source/version binding | G-A PASS 또는 정직한 BLOCKED report |

R4-2 helper는 synthetic/rational 입력 및 symbolic band width에 대한 결정적 함수다. 실제 DEV의 critical value나 confidence band를 계산하는 evaluator가 아니다. 기존 R3 코드의 위치는 참조용으로만 알고 있으며, 이번 설계 단계에서 코드를 수정·실행하지 않았다.

이후 별도 작업: G-B policy resolution → S6C numerical profile 및 feasibility → 미래 V4 preregistration → 별도 evaluator 구현 → 승인된 DEV-only evaluation. 단계별 authorization을 건너뛰지 않는다.

## 19. 검증 계획과 완료 판정

### 19.1 R4에서 필요한 focused tests

| 검증군 | 핵심 사례 / 실패를 잡는 이유 |
|---|---|
| source isolation | explicit single input 외 read를 막는 adapter; schema에 outcome input 주입 시 reject |
| lineage | canonical identity와 bytes digest를 혼동한 입력; 잘못된 vintage·row 변경 탐지 |
| alignment | native gap, 같은 날짜의 충돌값, horizon별 누락; silent drop 방지 |
| median convention | 홀수·짝수, all ties, 두 atom의 각 질량 1/2, median plateau; 기존 midpoint 재현 |
| band inversion | e=0, mass crossing, probability 0/1 boundary, 미관측 tail mass; strict > 오류 검출 |
| MAD transfer | median center 이동, asymmetric two/three-atom law, 0 scale, infinite r_m; center uncertainty 누락 검출 |
| deterministic inclusion | exact rational finite laws와 compatible empirical cdf를 열거해 §7의 포함관계 검증; 수학적 증명 보조 |
| calibration contract | ell=1..n completeness; covariance kernel과 MA weight 구분; 동일 g coupling manifest 검사 |
| gate semantics | missing/revoked A5/A6/G1; 모두 finite diagnostics 성공이어도 BLOCKED여야 함 |
| immutable identity | source·method·domain·approval 변경 시 assessment identity 변경; 원 diagnostic 불변 |

D2 지배 부등식의 small deterministic fixture는 주어진 Gaussian-vector 대용 숫자 배열에 대해 max 포함을 검사할 수 있다. 이는 coverage simulation이나 finite mixing 증명이 아니다.

### 19.2 S6C 이후의 별도 검증

실제 covariance factorization, 모든 span의 root, conservative MC quantile, 플랫폼별 수치 오차는 S6C 승인된 profile의 대상이다. 이 검증 없이는 Reference Adequacy를 실행할 수 없다.

향후 fully synthetic lattice iid/finite-memory/허용 stationary Markov 예제에서는 atom 내부·half-mass 경계·zero-scale·cross-horizon overlap을 검토한다. break·long-memory 예제는 model mismatch 및 부적절한 승인 방지에 사용한다. simulation 성공을 theorem 증명으로, synthetic pass rate를 실제 DEV 가정 승인으로 바꾸지 않는다.

S6C가 허용 coverage deviation·MC 오차·비용 예산을 사전 동결하기 전에는 통계적 “simulation PASS” threshold를 만들지 않는다. failure 관찰 후 τ, κ, span set, tie convention을 조정하면 새 method version이 필요하다.

### 19.3 이번 문서 작성의 검증

이번에는 요구한 설계 항목의 완결성, 수식의 정의역·strict inequality·무한 endpoint, gate 간 의존성, 문헌 적용 범위, 금지 영역과 단계 순서를 문서 수준에서 점검한다. 코딩 tests, DEV 진단 재실행, bootstrap, simulation, DB/runtime 접근은 수행하지 않는다.

## 20. 기존 문서 / 계약 영향도

| 기존 문서/계약 | 다음 반영에서 필요한 변경 | 보존할 기록 |
|---|---|---|
| R3 handoff / evidence | 후속 설계 링크와 새 method namespace만 추가 가능 | 원 A0~A10 상태·isolation 기록 불변 |
| R1 Method / JointInferenceContract | target·lattice transfer·set-valued error coverage·claim 한계 | 기존 conditional route는 historical |
| R2 MultiplierProfileContract | 새로운 covariance-span-envelope version 분리 | R2 algorithm 및 기존 m/L/b/ell 결과 |
| R2A CandidateDomainContract V1 | 수치·산술·out-of-domain 변경 없음; 새 method 참조 결속 | κ=1/10 governance |
| S6A DependenceAssumptionContract | strict/mixing model-use 3층, root condition, review/revocation | population proof와 model-use 구별 |
| S6B RiskBudgetContract | 새 target의 α 의미 및 observed/error-bound 사용 검토 | 독립 authority·τ 결정·outcome isolation |
| S6C numerical ledger | covariance factorization·공통 g·span completeness·MC quantile·비용 guard | 수치 정책 소유권 |
| V3 | 변경 없음 | 기존 protocol 의미·identity |
| 미래 V4 | 모든 gate 이후 별도 preregistration에서 새 IDs 결속 | 이번 문서로 생성하지 않음 |

초기 architecture의 full-record law confidence region, repeat risk 및 γ_repeat를 새 구간의 이름으로 되살리지 않는다. 이번에 새 method version의 **설계 명칭**을 정하는 것은 V4 protocol artifact 생성과 다르다.

R2와의 자산 보존을 더 우선하여 단일 adaptive MA profile을 쓰고 싶다면, 새 이산 law에서 adaptive bandwidth와 실제 MA covariance를 포함하는 일치성 증명을 별도로 승인해야 한다. 이는 현재 primary의 runtime fallback이 아니며 본 문서의 선택을 바꾸려면 다음 설계 버전으로 진행한다.

## 21. 최종 결정표

여기서 “새 상태”는 본 설계의 결정 및 필요한 승인 상태다. 현재 실행 결과를 갱신한 상태가 아니다.

| 항목 | 현재 상태 | 결정 | 새 상태 |
|---|---|---|---|
| A4 continuity | NOT_ACCEPTED | observed lattice + 원 indicator transfer로 대체 | REPLACEMENT_DESIGNED / REVIEW_REQUIRED |
| A5 stationarity | UNRESOLVED | scoped strict stationarity; declaration/diagnostic/acceptance 분리 | MODEL_USE_APPROVAL_REQUIRED |
| A6 strong mixing | UNRESOLVED | a>15/2 유지; finite proof 요구 제거; root 조건 명시 | MODEL_USE_APPROVAL_REQUIRED |
| A7 median regularity | NOT_ACCEPTED | density/uniqueness 미분 제거; median set 역변환 | REPLACEMENT_DESIGNED / REVIEW_REQUIRED |
| A9 MAD regularity | NOT_ACCEPTED | center-aware 2e outer bound로 대체 | REPLACEMENT_DESIGNED / REVIEW_REQUIRED |
| median statistic | current midpoint median | 관측값 유지; 추론에 median interval 추가 | OBSERVED_STATISTIC_RETAINED |
| scale statistic | raw MAD | 관측값 유지; 추론은 outer interval | OBSERVED_STATISTIC_RETAINED |
| A8 zero scale | finite MAD VERIFIED | clean replay 및 zero/∞ 상태 계약 | APPLICABILITY_REPLAY_REQUIRED |
| multiplier profile | FROZEN R2; m/L/b/ell 기록 | 기존은 legacy audit; 새 covariance span-envelope | NEW_PROFILE_DESIGNED, NOT EXECUTION_APPROVED |
| κ=1/10 | FROZEN | 동일 contract·integer arithmetic 유지 | UNCHANGED |
| R1 route 전체 | continuous regular-functional route | **수정**; base sequential 구조 보존, nonlinear density route 폐기 | LATTICE_CDF_PROJECTION_PRIMARY |
| G-A | BLOCKED | §9 gate conjunction으로 재설계 | BLOCKED UNTIL NEW EVIDENCE/APPROVAL |
| G-B | BLOCKED | G-A 이후 새 target compatibility와 독립 risk approval | BLOCKED |
| Reference Adequacy | UNRESOLVED | §15 전부 충족한 뒤 별도 DEV 평가 | UNRESOLVED |
| V3 / V4 | V3 unchanged / V4 absent | 불변 / 생성 안 함 | UNCHANGED |

### 21.1 완료 요건 추적

| 사용자 요구 | 닫힌 설계 위치 |
|---|---|
| 5개 substantive blocker 각각 해결 방향 | §§3,6~10 |
| continuous route 유지/수정/폐기 결정 | §§4,6,21 |
| median/MAD 유지 여부 | §7 |
| stationarity / mixing 계약 | §8 및 A5/A6 |
| 새 G-A / migration | §§9~10 |
| DEV-only 검증 절차·schema·determinism | §§11,16 |
| G-B 진입 조건 | §14 |
| Reference Adequacy 재개 조건 | §15 |
| 다음 구현의 정확한 범위 | §§18,19,22 |
| Holdout 접근·runtime·코드 변경 없음 | 현재 작업 범위 §§1,17,19.3 |

실행 승인까지 이미 완료되었다는 체크는 없다. 모델 가정의 실제 승인, proof review, clean R4 execution, G-B 수치·authority, S6C 수치 profile은 미래 evidence다. 그 값이나 성공을 현재 문서가 만들어내지 않는다.

## 22. 다음 작업 명세에서 구현해야 할 정확한 범위

**NEXT-6E-S6A-R4 — 이산분포 방법 계약 및 Development 전용 승인 진단**

입력: 본 설계의 exact revision, 명시적으로 제공된 frozen DEV 복사본, 기존 source/candidate contracts, model-use 및 theorem-review dossier.

구현 범위:

1. §16의 closed schemas와 immutable identity.
2. exact ECDF/median endpoints/midpoint/MAD 및 결정적 outer-bound helpers.
3. §11의 Development input diagnostic. raw source·구조·quantization·descriptive stationarity/dependence·legacy R2 audit까지만.
4. §9의 G0/G1/A0~A10 acceptance logic와 approval binding.
5. §19.1의 focused tests.
6. clean scope에서 DEV-only diagnostic → dossier 검토 → G-A evaluation report.

구현 완료의 의미는 진단과 gate 판정이 정확하고 재현 가능하다는 것이다. G-A PASS가 반드시 나와야 하는 작업이 아니다. dossier가 없거나 조건이 부적합하면 정확한 BLOCKED와 다음 필요 evidence를 반환해야 한다.

제외 범위: real DEV multiplier replicates, numerical critical values, confidence-band 평가, forward envelopes, passing candidate 탐색, operational tolerance 결정, V4 생성, evaluator 구현, Reference Adequacy 실행, Holdout의 모든 접근, DB/runtime, Production 변경, PR merge, main 직접 변경.

이번 작업의 실제 산출물은 이 설계 Markdown 한 개다. 코드 변경 없음. 테스트 코드 변경 없음. Holdout 접근 없음. runtime 접근·변경 없음. DB 접근 없음. V3 변경 없음. V4 생성 없음. evaluator 구현 없음. main 변경·PR merge 없음.
