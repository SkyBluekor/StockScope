# StockScope 개발 인수인계 — SC-UX1 / JEV / Runtime

**작성일:** 2026-10-08 (KST)  
**목적:** 다음 ChatGPT 채팅에서 현재 작업을 중복하거나 흐름을 잃지 않고 이어가기.  
**원칙:** 이 문서는 작성 시점 스냅샷이다. 새 채팅에서는 GitHub 실제 HEAD·CI 및 사용자 PC 출력으로 최신 상태를 먼저 재검증한다.

## 0. 최우선 요약 — 다음 채팅은 여기서부터

1. **SC-UX1은 이미 GitHub main에 구현되고 CI가 통과했다.** 작성 직전 검증한 main 및 feature/sc-ux1-beginner-decision-ui HEAD는 모두 **605b4c8d799c402f497ef695ae9cf2b28f6c639b**였다. GitHub Actions **main CI #2391 SUCCESS**. "설계만 완료·미구현"으로 되돌아가지 말 것.
2. **다음 실제 작업은 현재 PC의 초보자용 Scanner 화면 브라우저 UAT**다. 앱의 쉬운 표현, 매수 오해 가능성, 시세·가격 출처, 관심/보유 기능, X2 비교를 검증하고 문제만 수정.
3. **현재 PC에서 SC-UX1 최신 코드 반영 여부는 아직 확인하지 않았다.** ChatGPT는 사용자의 Windows 파일·브라우저를 직접 만지지 않았다. 사용자에게 최신 코드 내려받기 결과와 실제 화면을 확인받아야 한다.
4. **RT-L1 현재 PC 데이터 복구/원격 게시 완료, 다른 PC 동기화만 보류.** 다른 컴퓨터는 현재 사용 불가. 현재 PC 개발을 막지 말 것.
5. **JEV-X1, JEV-X2는 구현·CI 완료.** JEV-X3는 SC-UX1 브라우저 UAT 후 검토. 외부 AI 실호출 금지.
6. **제품 사용자 = 주식 초보자.** 내부 개발자 용어 대신 "왜 후보인가 → 지금 어떤 상태인가 → 무엇을 기다릴까"의 순서로 설명한다.

## 1. 프로젝트 철학과 사용자 피드백

프로젝트 **StockScope**는 종목 탐색(Scanner) → 과거 검증(Validation) → 실행 판단(Execution) → 보유 관리(Recovery) → 전략 적응·거버넌스를 연결하는 주식 분석 웹앱이다. 기존 백엔드에는 많은 기능이 있으나 모든 결과를 기본 화면에 노출할 필요가 없다.

**반드시 유지할 사용자 요구:**
- "주식을 모르는 사람도 이해하기 쉬워야 한다." 영어 내부 용어 READY, NEAR_READY, Tier, Risk, Evidence, Scanner Ranking, 정책 해시 등을 기본 화면에 내보내지 말 것.
- "삼성증권만 READY면 삼성증권만 사야 하는 것으로 오해한다." **후보 순위 ≠ 매수 추천 ≠ 지금 진입 가능**.
- **KRX 확정 일봉을 분석할 때의 가격**과 **KIS로 새로 확인한 현재/마지막 시세**를 분리할 것. Scanner의 candidate.current_price는 분석일 종가이며 실시간 현재가처럼 설명하지 않는다.
- 사용자가 기대하는 핵심 흐름: **무엇을 살펴볼까 → 왜 선정됐나 → 지금 사도 되는 조건인가 → 못 산다면 무엇을 기다려야 하나 → 나중에 보유 관리**.
- 결론 → 이유 → 다음 확인 사항 → 세부 자료 순서. "READY이므로 매수" 금지. 실시간 시세가 없어도 확정적인 최신 판단처럼 말하지 않는다.
- 과거 3년 성과는 별도 참고 정보. 현재 정렬 이유라고 주장하지 않는다.
- 불필요한 카드·둥근 모서리·파스텔 AI 스타일·중복 표현 지양. 에디토리얼/타이포 중심, 사용자 친화적 다크 테마, 표 중심, 반응형 모바일.
- 가능하면 설계를 먼저 충분히 닫고 단계를 나눠 구현. 문서는 통합·한글 제목 우선, 문서 수 무분별하게 늘리지 않는다.

### SC-UX1 이전 실제 화면에서 사용자가 지적한 장면

2026-10-08 사용자가 제공한 Scanner 스크린샷은 **SC-UX1 적용 전의 화면**이었다. 삼성증권이 1위 READY, 나머지 종목 다수가 NEAR_READY로 보였다. 삼성증권의 분석 당시 종가는 **89,400원**, 표시된 매수 참고 기준은 **88,300원 이하**로 보였는데, READY 배지가 "당장 삼성증권을 사라"처럼 오해될 위험이 있었다. 참고 가격은 실행 가능한 진입 범위인지와 별개이며, 실제 KIS 새 시세도 없는 상태에서 "지금 매수 가능"이라고 결론 내려서는 안 된다.

사용자는 "개발자에게 적는 글 같다"고 강하게 지적했다. **SC-UX1은 개발자 용어의 단순 번역이 아니라 판단 정보 구조 자체의 수정**이다.

## 2. GitHub / 환경의 확인된 기준

- Repository: https://github.com/SkyBluekor/StockScope
- Working branch: **feature/sc-ux1-beginner-decision-ui**
- 주 로컬 폴더: **C:\Projects\StockScope**, PowerShell, .venv
- 작성 직전 조회한 main HEAD: **605b4c8d799c402f497ef695ae9cf2b28f6c639b**
- 작성 직전 조회한 feature/sc-ux1-beginner-decision-ui HEAD: 같은 SHA
- main GitHub Actions **#2391 success**. Python 3.11/3.14 백엔드, Node 22 프론트, Windows Fresh Clone 검사 통과. 사용자의 실제 브라우저 동작은 이 CI만으로 검증되지 않는다.
- 본 인수인계 문서를 저장하면 HEAD가 추가 변경되므로 **이 SHA는 문서 생성 이전 기준**이다. 이후 코드 변경이 발생했다면 그것이 최신 기준이다.
- 작업 방식: GitHub 커넥터로 저장소의 파일을 직접 확인·편집, 별도 브랜치에서 테스트 후 검증된 내용만 main 반영. 로컬 Windows에 접근해 수동 변경했다고 주장하지 않는다.

### 단계별 상태

| 단계 | 확인된 상태 |
| --- | --- |
| VN-P1~P6, NEXT-6E-S3 | 현재 PC의 관련 런타임 정상. VN-P1-S3는 선택적 NOT_APPLICABLE |
| JEV-X1 | 코드·CI 완료, 현재 PC DB 마이그레이션 CURRENT |
| JEV-X2 | 코드·CI 완료. 동일 캡처 후보 2개 순위의 결정 이유를 읽기 전용 비교 |
| RT-L1 | 현재 PC 로컬 우선 게시 완료, 다른 PC 수신 보류 |
| **SC-UX1** | **main 구현·CI PASS, 실제 사용자 PC 화면 UAT 대기** |
| JEV-X3 | 아직 착수하지 않음. SC-UX1 확인 후 |

## 3. SC-UX1 — 이미 구현된 것과 아직 남은 일

**새 코드를 중복 작성하기 전 다음 파일을 직접 읽을 것.**

### 구현된 주요 파일

- **frontend/src/components/scannerDecisionPresentation.ts**
  - simpleConditionStatus(), priceReferenceText(), assessPriceRule(), beginnerCandidatePresentation().
  - 실제 후보 등급·조건·경고에서 초보자 친화 문장 생성. 가격 규칙 AT_OR_BELOW / ABOVE / RANGE / REFERENCE 등을 구분.
  - 가격 상태 IN_RANGE도 '지금 사세요'가 아님. 정확한 기준 없으면 UNKNOWN.
- **frontend/src/components/ScannerDecisionSummary.tsx**
  - 결론 한 문장 + "왜 찾았나요?", "무엇을 조심해야 하나요?", "다음에는 뭘 확인할까요?"를 우선 표시.
- **frontend/src/components/ScannerPriceStatus.tsx**
  - 분석 당시 종가와 전략상 참고 가격을 분리.
  - **사용자가 '새 시세 확인'을 누를 때만** 기존 fetchStockQuote 및 fetchDomesticMarketSession API 호출.
  - 수신 시각, 실거래/모의 KIS 환경, 장 상태, 캐시 여부 등을 표시. 가격만 비교하고 Scanner 순위·전략·Risk는 재실행하지 않음.
- **frontend/src/components/ScannerPanel.tsx**
  - 후보 목록 행의 사용자 표현 축약; 분석일 종가라고 명시.
  - 선택 후보에 ScannerDecisionSummary, ScannerPriceStatus 배치.
  - 장황한 고급 설명은 "전략·과거 기록·목표 가격 자세히 보기"로 접음.
  - 진행 상태의 기술적 진단과 추가 검토 절차를 선택적으로 접음.
  - 관심종목 등록, 기존 보유 등록, 후보 선택 간 동작·접근성 보존.
- **frontend/src/components/ScannerRankComparison.tsx**
  - JEV-X2 비교 기본 접힘. 사용자가 열면 쉬운 "먼저 보여준 이유"부터 표시.
  - 8개 정렬값은 "비교한 계산 기준 자세히 보기"에만.
- **frontend/src/styles.css**, **frontend/src/components/scannerRankComparison.css**
  - 기본/고급 내용의 시각적 우선순위 정돈.
- **backend/tests/test_ux_redesign1_contract.py** 및 신규 표현 테스트·Node 회귀 runner, CI 구성.
  - 기본 용어, 가격 규칙, 관심/보유 별도 버튼, 접근성 등에 대한 자동 검증.

### 실제 사용자 PC에서 아직 확인하지 않은 것

- git pull을 받아 사용자의 실제 브라우저에 위 최신 UI가 나타나는지.
- 최신 화면이 사용자의 눈높이에 정말 맞는지, 종목 1위 READY 오해가 사라졌는지.
- KIS 사용 가능/불가, 장 마감, 캐시, 지연, 시세 요청 실패 시 실제 사용자 경험.
- 후보 선택, 관심 등록, 보유 등록, 세션 복원과 X2 비교의 실제 동작.
- 새 Scanner 실행의 JEV-X1 저장 근거가 STORED/REUSED인지. **마이그레이션 CURRENT = 실제 근거 STORED라는 뜻은 아님.**

**중요: SC-UX1 코드/CI 완료와 실제 UI 사용 승인(UAT)은 별개의 마일스톤이다.** UAT 전에 제품 사용성이 완료됐다고 단정하지 말 것.

## 4. JEV와 Scanner의 절대 경계

- 기존 Production Scanner의 종목 순위·조건·Risk·전략을 건드리지 않는다.
- 핵심 경로: backend/app/backtest/candidate_priority.py, backend/app/backtest/reproducibility_audit.py.
- X1: backend/app/prospective/rank_audit_adapter.py 및 rank_evidence.py, Simulation의 scanner_rank_evidence 불변 sidecar.
- X2: backend/app/prospective/rank_comparison.py, API GET /api/simulation/prospective/captures/{capture_id}/candidate-comparison.
- 실제 정렬 원인 순서: tier_order → missing → risk_quality → entry_gap_missing → entry_gap_pct → negative_strategy_fit → tie_focus_order → code.
- 최초로 달라진 요소만 순위가 갈린 실제 이유. 후순위 차이는 참고. 마지막 code 정렬은 투자 우열이 아님.
- X1 근거 없는 캐시·과거 캡처에 억지로 증거를 만들어 끼우거나 무단 backfill 금지.
- X2 비교는 사용자에게 후보를 먼저 보여주는 이유이며, 예측 수익률·즉시 매수 추천이 아니다.
- 외부 AI/Jev provider 실호출, Canary 재실행은 신규 명시적 승인 없이는 금지.

## 5. Runtime 동기화 — 현재 PC 정상, 다른 PC 보류

### 사용자 PC 정본 채택 성공 기록
- Local project: **C:\Projects\StockScope**
- Transport root: **G:\내 드라이브\StockScopeRuntime**
- 현재 PC machine ID: **b4151fbabc8141d280ddc4e16a58c7a7**
- 다른 PC machine ID: **bbb95c2cf6964b43b606db2aa841db0f**
- 사용자는 다른 PC의 실험용 holdings/simulation 자료는 폐기해도 된다고 승인하여 **현재 PC DB를 정본**으로 확정.
- 게시 명령 실행 결과: **PUBLISHED**, bundle **19487cc5a4aa4461a866b87711afb388**.
- 안전 백업: **C:\Projects\StockScope\backups\StockScope_20261008T040630Z**.
- 이후 --prefer-local --dry-run: **CURRENT**. transport configure 후 **READY**, sync_local.ps1 -CheckOnly **PASS**, JEV 마이그레이션 전부 CURRENT, Macro READY, DB writes 0.
- 현재 **다른 컴퓨터를 사용할 수 없다**. 다른 PC 복구까지 완료됐다고 하면 안 되지만 현재 PC에서 UI 개발은 계속 가능.
- 다른 PC 사용 가능해진 뒤에만: Google Drive 동기화, 상대 앱 종료, git 최신화, 백업/status 확인, 실제 승인 재확인 후 명시적인 원격 우선 교체 명령을 검토:
  ~~~powershell
  python .\tools\runtime\cli.py transport reconcile --prefer-remote --replace-local-changes --domains holdings,simulation --confirm
  ~~~
- 이 절차는 **다른 PC에서만** 실행. 현재 PC를 prefer-remote로 덮어쓰지 말 것. remote head/bundle, continuity state 수동 조작 및 강제 리셋 금지.

## 6. 다음 채팅 작업 절차 — 실전 인수인계

### 6-1. 먼저 최신 상태 재확인
1. GitHub main·기능 브랜치 최신 HEAD, 새 커밋, CI 확인.
2. 사용자 로컬 작업 트리 여부를 먼저 확인하고 정상일 때 다음을 진행:
   ~~~powershell
   cd C:\Projects\StockScope
   git status --short
   git pull --ff-only origin main
   .\sync_local.ps1 -CheckOnly
   .\run-dev.ps1
   ~~~
   작업 트리에 변경이 있으면 임의 git reset, stash, checkout 금지. CheckOnly에서 문제 발생 시 본 실행 강요 금지.
3. 이미 정상 실행 중이면 불필요하게 재실행·재분석 요구하지 않는다. 사용자가 제공한 스크린샷과 콘솔 출력 기준으로 확인한다.

### 6-2. SC-UX1 브라우저 UAT 항목
- 후보 리스트 첫눈에 "무엇을 살펴보고, 왜, 무엇을 기다리는지" 이해 가능한가?
- 상위 순위를 매수하라는 뜻으로 오해하지 않는가?
- READY/NEAR_READY/Risk/Tier 등 내부 말 대신 쉽고 정확한 설명인가?
- Scanner의 분석일 종가가 최신 거래 가격처럼 표시되지 않는가?
- KIS 조회 버튼을 누르기 전에는 시세 요청이 발생하지 않는가? 누른 뒤에만 선택 종목 정보 표시, 새 시세/원본 종가 혼동 방지.
- 가격은 맞지만 전략 조건 미충족, 전략 READY지만 가격 기준 밖, 위험 경고, 기준 불명, 오래된 데이터, 장 마감, 모의투자 환경을 정직하게 구분하는가?
- 사용자가 관심 등록/기존 보유 등록 버튼을 눌러도 행 선택이나 신규 BUY 체결이 발생하지 않는가?
- X2 비교는 기본 접힘, 쉬운 결론이 맨 위, 기술 튜플은 상세에 있는가?
- 세부 영역의 길이/중복, 모바일 오버플로우/가독성/키보드 접근성을 점검.
- X1 evidence STORED 여부는 새 실행 결과가 제공될 때만 판단. 기존 분석 캡처에서 근거가 없으면 이유를 먼저 확인하고 무단 데이터 생성 금지.
- 필요하면 사용자의 현재 화면 스크린샷, 브라우저 Console의 일반 오류(비밀값 제외), 관련 네트워크 상태/응답 코드만 요청. 상대 PC 접근을 요구하지 않는다.

### 6-3. 수정 필요 시
- 사용자 관찰 증거 기반으로 **수정 명세 → 영향 범위 → 코드·테스트 → CI → main 반영 → 다시 UAT**.
- UI 결론/가격 출처/행동 안내를 우선. 문장만 반복 바꿔도 구조가 길고 복잡하면 제품 목표 미달.
- 새 가격/위험 추정 모델을 만들지 않는다.
- 변경할 때 사용자 PC의 SQLite DB·Runtime Transport에 쓰기 작업을 수반하지 않도록 한다.

### 6-4. 다음 기능
- SC-UX1 사용자 승인 후 **JEV-X3: 분석 기준일이 다른 확정 캡처 간 판단 변화 설명** 설계 진행.
- 다른 컴퓨터 RT-L1 수신은 장비를 사용할 수 있는 날 별도 처리.
- 장기: Scanner-KIS 연동 정교화, Validation/Execution/Recovery 사용자 관점 간소화, 적응형 전략과 거버넌스. 새 기능은 사용자 관점 목표/권한을 분명히 한 후 진행.

## 7. 보안·실험·설계 금지 사항

1. **Holdout LOCKED** — 명시적 신규 사용자 허가 없이 관련 파일/경로/디렉터리/존재 여부/메타데이터/해시를 검색·열람·테스트하지 않는다.
2. **비밀정보 비접근** — .env, API 키, 인증정보, 토큰 내용 열람/노출 금지.
3. **JEV provider 실제 API 호출 금지** — 사용자의 새로운 명확한 허가 필요. BASELINE_ONLY, 선정 권한 동결.
4. 과거 V3 Canary 상태는 EXECUTED / DIAGNOSTIC FAIL / PRESERVED. 재실행하지 않는다.
5. Scanner 순위·전략·Risk 정책, frozen Production baseline, Prospective 원본 해시 변경 금지.
6. 사용자 Windows/GDrive 로컬 DB를 직접 조작했다고 주장하지 않는다.
7. 문서와 디자인에는 쉬운 한국어, 한글 파일명, 중복 문서 축소 및 타이포 중심 UI 적용.

## 8. 다음 채팅에 바로 붙여넣을 지시문

> StockScope 작업을 이어가자. GitHub 저장소 SkyBluekor/StockScope의 docs/인수인계/StockScope_SC-UX1_작업_인수인계_2026-10-08.md 를 먼저 읽어라. main과 feature/sc-ux1-beginner-decision-ui 최신 HEAD와 CI를 먼저 검증해라. SC-UX1 초보자용 Scanner 화면은 GitHub에 구현되어 main CI를 통과했으므로 재구현하지 말고 **현재 PC 브라우저 UAT**부터 이어가자. 주식을 모르는 사람도 이해해야 하며 후보 순위와 매수 여부, 분석 당시 종가와 새로 확인한 KIS 시세를 분리하고, 이유/다음 확인사항을 첫 화면에 둬야 한다. RT-L1 현재 PC는 READY, 다른 컴퓨터 수신은 사용 불가로 보류. JEV-X1/X2 완료, JEV-X3는 이후. Scanner/전략/Risk 프로덕션 계산 동결, Holdout·비밀값 접근/외부 AI 호출 금지. 현재 상태와 실제 스크린샷·출력을 확인한 뒤 필요한 작업만 명세하고 진행하라.

---
**주의:** 이 문서의 GitHub 상태·CI는 검증됐지만, **사용자 PC에서 SC-UX1 새 화면이 정상 작동하는지는 아직 확인되지 않았음.**
