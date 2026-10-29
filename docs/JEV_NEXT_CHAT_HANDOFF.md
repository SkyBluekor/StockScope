# StockScope — 다음 ChatGPT/Codex 채팅 HANDOFF (JEV LIVE 우선)

**기준 시각:** 2026-10-29 (Asia/Seoul), LIVE-01 사용자 실모델 성공 반영. 이 문서는 **다음 채팅의 첫 페이지**다.

## 반드시 가장 먼저 읽을 것

1. **[JEV 실사용 마스터 실행계획](./JEV_LIVE_INTEGRATION_MASTER_PLAN.md)** — 진행 단계·완료 판정·불변식·소스 파일의 단일 작업 체크리스트.
2. [JEV v2 원래 제품 설계](./설계/StockScope_JEV_통합설계_v2_2026-10-06.md) — Scanner Decision Reviewer의 책임과 기본 판단 우선 원칙.
3. [S7.4 외부 전송 권한·시점 기준](./설계/JEV-ACT2-S7.4_데이터_출처_권한_및_시점_분류_기준.md) — 실제 KRX 유래 자료의 외부 TypeSafe 전송은 현재 HOLD/NO-GO. `LOCAL_PACKET_READY`는 허가가 아니다.
4. 코드의 **현재 HEAD**로 `backend/app/jev/typesafe_provider.py`, `review_service.py`, `backend/app/api/jev.py`, `frontend/src/components/ScannerPanel.tsx`, `scannerAiReviewStatus.ts`를 확인. 오래된 handoff 문서보다 실제 코드와 마스터 계획을 우선.

## 1. 사용자 목표: 잊지 말 것

사용자는 StockScope가 **TypeSafe AI의 Jev/System One API를 실제로 사용해 주식 Scanner의 후보를 추가 검토**하도록 원한다. 비용이 저렴한데도 계속 '준비·감사·UI 기록·초미세 테스트'만 반복하고 실사용을 미룬 점에 강한 불만이 있었다.

**더 이상 G2 후보 기록 장식을 다음 우선순위로 제안하지 말 것.** G2-05는 보류이며 JEV-LIVE-01을 먼저 개발한다.

사용자가 원하는 사용 흐름은:
`기존 Scanner 결과 확인 → (opt-in) JEV 실모델의 두 번째 의견 요청 → Scanner 기본 판단 + JEV 의견 및 모순/근거 보기 → 이후 누적된 결과로 유효성 판단`.
후보를 추천/발굴하거나 우회 매매시키는 새로운 AI 엔진이 목적이 아니다.

### 중요한 표현

- 'API 키를 만들었다/요금이 찍혔다/합성 실험을 성공했다' ≠ '현재 Scanner 후보에 실 JEV가 연동됐다'.
- 기존 JEV API 실험을 반복 검증하기보다 **실제 후보 리뷰 서비스와 화면에 이어 붙이는 개발**을 하라.
- 비용이 적다는 것을 감안해 실용적인 호출 한도로 소수 통합 시험을 설계하고, 돈 걱정 때문에 아무것도 하지 않는 답변을 하지 말라.
- 권리나 시점 확인이 필요한 실 시장 데이터를 무단으로 전송하지 말 것. 그 대신 권한 확인과 **합성 데이터를 사용한 실제 유료 Provider 연결 작업**을 병행하여 목표를 전진시켜라.

## 2. GitHub 상태와 안전한 개발 위치

- Repository: `https://github.com/SkyBluekor/StockScope`
- 기존 통합/개발 브랜치: `codex/p0-01-mvp-c1-c2-integration-20261022`
- Draft PR: **#170** `https://github.com/SkyBluekor/StockScope/pull/170`
- 최종 G2-04 코드 커밋: `eb83d5aa16c903b487b4e8d83d2538b3fd1368b2`; G2-04 Push/PR CI 모두 **4/4 PASS**. 사용자는 기숙사 PC에서 새 「이번 분석 / 저장 기록」 화면을 봤다고 스크린샷 제공.
- 이번 handoff는 문서 커밋이 더해지므로 **브랜치 HEAD는 위 G2-04 SHA보다 나중**이다. `git rev-parse HEAD`로 실제 SHA부터 확인한다.
- **`main`에 병합 금지**(별도 사용자 요청 전까지 Draft PR 유지). 각 단계는 동일 작업 브랜치 또는 해당 브랜치에서 갈라진 작업 PR로 명시적으로 남기고 링크 기록. 사용자의 운영 DB/캡처를 자동 수정·마이그레이션하지 말 것.
- 현재 GitHub 파일로 저장된 계획의 위치는 **`docs/JEV_LIVE_INTEGRATION_MASTER_PLAN.md`**. 이 handoff는 **`docs/JEV_NEXT_CHAT_HANDOFF.md`**. 미래 채팅에서 개별 문서를 다시 추측하지 말 것.

## 3. 사용자가 실제 쓰는 Windows 환경

**기숙사 컴퓨터 (2026-10-28 대화에서 확인):**
- 기존 사용자 StockScope: `C:\TAEWOO\CapstonDesign\StockScope` — `.venv`가 있었고 기존 runtime DB·API 설정 사용 가능성. 존재 여부는 실제 파일 검사.
- G2-04 실험 Clone: `C:\Projects\StockScope-G2` — 브랜치 `codex/p0-01-mvp-c1-c2-integration-20261022`, 당시 SHA `eb83d5a`.
- `tools/data/g2_03_run_preview.ps1 -OperationalRepo "C:\TAEWOO\CapstonDesign\StockScope"`는 Snapshot Simulation/Market DB와 KRX 공개 캐시를 격리해 개발 서버 8000/5173을 구동. 처음에는 DART·NAVER News 키가 새 clone에서 자동 반영되지 않아 사용자가 `.env` 문제를 지적함. **JEV_API_KEY도 해당 preview의 런타임에서 명시적으로 안전하게 읽히는지 확인**해야 함; API 키를 채팅/로그/PR에 출력하지 말 것. G2-03 preview 스크립트는 원 프로젝트 KRX 키만 전달하도록 만들어졌으며 다른 provider 키는 자동 복사하지 않는다.
- `C:\Projects\StockScope-G2`을 그냥 `run-dev.ps1`로 실행하면 새 clone의 데이터/설정 상태가 기존 원본과 다를 수 있다. 운영 DB를 연결하는 미리보기 사용 금지; snapshot 절차를 유지.
- 이전 학교 PC 경로는 주로 `C:\Projects\StockScope`와 `%TEMP%\StockScope_P0_02_90745c8d5d49`였다. 학교 PC와 기숙사 PC에 동일 프로젝트 폴더가 있다고 가정하지 마라.
- 사용자에게 DB·API 키·계좌정보를 채팅에 붙여 넣게 하지 마라. 기능 검증은 키 **존재 여부만**, 운영 DB는 복제본으로.

**기숙사 PC Git 상태 확인 예시 (데이터 보존):**
```powershell
$work = "C:\Projects\StockScope-G2"
git -C $work status --short
git -C $work fetch origin codex/p0-01-mvp-c1-c2-integration-20261022
git -C $work log -1 --oneline
# 로컬 변경이 있으면 강제 checkout/reset하지 말고 보존한 뒤 안전하게 업데이트.
```
브랜치 최신 코드로 실행하더라도 **GitHub 코드 동기화 ≠ 기숙사와 학교의 로컬 runtime 데이터 동기화**.

## 4. JEV 실물 코드 — 이미 있다

- `backend/app/jev/typesafe_provider.py`: **실제** `TypeSafeSystemOneProvider` HTTP 클라이언트, `JEV_API_KEY` 로딩, 모델 식별·HTTP 에러 처리. **새로운 HTTP 어댑터를 처음부터 만들지 말 것.**
- `backend/app/jev/review_service.py`: `JevManualReviewService` V4 semantic route, 프로토콜 확인, provider_override, dedupe/저장, 결과 정규화. 기본 `DISABLED` 및 provider 주입 부재.
- `backend/app/api/jev.py`: `GET /api/simulation/jev/review-feature`에서 `available=false` 고정, `POST /api/simulation/jev/reviews`는 기본 OFF 서비스, `GET /api/simulation/jev/reviews`는 저장 결과 조회. **단지 frontend 토글을 켜는 것만으로 실제 API 사용 불가.**
- `frontend/src/components/ScannerPanel.tsx` + `scannerAiReviewStatus.ts`: AI 검토 결과 표시와 저장된 review integrity/model 검증 경계가 이미 있음.
- `backend/app/jev/typesafe_canary_v4.py`, `tools/data/run_jev_typesafe_canary_v4.py`, `tools/data/jev_s6_micro_canary.py`: 이전 합성 계약/실제 유료 호출 실험 기반. **실제로 수행된 과거 합성 호출과 사용자가 볼 수 있는 실제 후보 기능이 다름**.
- `backend/app/jev/scanner_lineage_s7_4.py`, `scanner_v4_readiness_s7_5.py`, `scanner_eligibility_s8.py`: real capture 로컬 진단/외부 전송 HOLD. 15개 후보 기록의 일부 `LEGACY_LIMITED`는 JEV '모델이 읽을 수 있음'과 '원천이 외부 전송 가능'을 증명하지 못함.

### 구현 시 확인할 미완성

1. `review_service`의 provider_override가 실제 TypeSafe production provider로 구성되지 않음.
2. API의 feature 상태는 고정 비활성이고, 명시적 사용 허가·protocol 고정·승인된 권한 경로를 연결해야 함.
3. `request_review`는 긴 HTTP 호출이 가능하므로 사용자 Scanner 요청을 막지 않는 작업 경계 및 모니터링 필요.
4. 모델 반환 id/prompt/hash/질문 상태와 비용이 검증되고, UI에 처음부터 '완료'라고 표시되지 않아야 함.
5. TypeSafe live가 싸더라도 실제 토큰 요금·모델 alias는 변할 수 있다. 기존 V4 artifact 예약금액과 현재 실제 계정 청구액은 다르다.
6. S7.4 source-rights/time 문서: 실제 시장 유래 자료의 외부 전송 NO-GO. 이 gate를 화면 토글로 우회하지 말 것. 대신 synthetic real-provider 개발과 로컬 실후보 시연은 계속 가능.

## 5. 다음 작업: 정확한 시작 지시 (새 채팅에서 그대로 실행)

> **'StockScope JEV-LIVE-01을 지금 구현해. GitHub의 `docs/JEV_NEXT_CHAT_HANDOFF.md`와 `docs/JEV_LIVE_INTEGRATION_MASTER_PLAN.md`를 먼저 읽고, 브랜치 `codex/p0-01-mvp-c1-c2-integration-20261022`의 최신 HEAD에 이어서 작업해. G2-05는 보류하고, 기존 `TypeSafeSystemOneProvider` / V4 `JevManualReviewService` / `typesafe_service`를 재사용해 synthetic-only 실모델 E2E를 서비스 경계까지 연결해. 데이터 권한 없는 실종목 payload를 전송하지 말고, user API 기본 OFF·기존 Scanner 불변을 지켜. fake/mock 관련 테스트와 필요하면 명시적 소수 live smoke를 수행하고, 변경 코드·CI·검증 증거를 GitHub PR #170 및 마스터 진행표에 남겨. 새로운 전체 기획/반복 감사로 우회하지 말고 실제 기능부터 완성해.'**

## 6. 단계별 상태표 (최신: 2026-10-29)

| 단계 | 상태 | 다음 행동 |
|---|---|---|
| JEV-LIVE-00 | 완료: 문서 기준점 설정 | 브랜치 HEAD·로컬 환경만 확인 |
| **JEV-LIVE-01** | **DONE — 합성 실제 TypeSafe 1회 E2E 성공** | 사용자 Windows `C:\\Projects\\StockScope`에서 `jev-1.14.0` 실제 응답 `PASS_THROUGH`, SQLite `VALID`, `MATCHED`, 1회 호출, CLI 0; 기존 CI 4/4 PASS. 실종목 UI는 아직 별도 단계. |
| **JEV-LIVE-02** | **DONE — 코드/CI + 사용자 실제 Windows AI 검토 탭 확인** | 셀트리온(KOSPI 068270) 저장 Scanner 2026-10-28 후보의 입력 근거·V4 차단·출처/권한 사유가 표시됨. index 0 수정 후 선택 종목 불일치 오류 없음. 코드 CI 4/4 PASS, Windows pytest 3/3 PASS. |
| **JEV-LIVE-03** | **로컬 검사/차단 DONE — 사용자 Windows 실제 후보 화면 검증, 결과 HOLD** | `GET /outbound-preflight` + AI 탭의 셀트리온(KOSPI 068270) LIVE-03 외부 전송 보류 및 사유 표시 확인. 모델 호출 0, 권한 진위/공개 시점 `UNVERIFIED`, resolver `NOT_CONFIGURED`. 실제 시장 데이터 전송 권한 미확보. |
| **JEV-LIVE-04** | **합성 Mock 수동 검토 사용자 Windows UI PASS · 실종목 TypeSafe HTTP BLOCKED** | 셀트리온 선택 화면에 별도 `999991` 가상 후보 결과 `REVIEW_REQUIRED` / `jev-mock-returned` / `MATCHED` / Mock 1회·실제 Provider 0회·review ID 표시. 새로고침·중복 실제 수동 재검증은 미확인 (CI/API 테스트 PASS). 실종목 공급자 호출·권한 `HOLD` 유지. |
| JEV-LIVE-05 | 미착수 | 명시 opt-in 소수 배치/자동 review, rollback |
| JEV-LIVE-06 | 미착수 | 후속 outcome·유용성·비용 평가 |

**단계 완료 시 반드시:** 마스터 진행표 행 + 해당 커밋 SHA + CI(통과/실패 명시) + user Windows 수동 확인 여부 + 단계별 미해결 blocker 갱신. 단순 '완료' 표시만 쓰지 말 것.

## 7. 실행 경계와 인계 품질

- 사용자가 요청한 것은 **길게 이어지는 실행 가능한 개발 로드맵과 GitHub 보존**이다. 문서만 계속 수정하는 프로젝트가 아니다.
- User는 기숙사 PC 화면에서 G2-04 적용을 확인했고, JEV를 소극적으로 쓰는 이유를 질책함. 이제 UI 장식보다 실제 JEV 추가 검토가 핵심.
- 원래 JEV 설계의 책임 제한(Decision Reviewer)은 비용 때문이 아니라 기본 분석과 사용자를 보호하기 위한 명시적 제품 경계다. **기본 분석을 유지하면서 실제 유료 TypeSafe를 연결하는 일은 양립한다.**
- 실 외부 시장 데이터의 권한은 계정·원천·수신자·목적별로 다르며 `JEV_API_KEY` 보유가 전송허가가 아니다. 사용자에게 '모두 활성화됨'이라고 추측하지 말 것.

## 8. JEV-LIVE-01 actual progress (2026-10-28)

- Code SHA [`90f3d5d`](https://github.com/SkyBluekor/StockScope/commit/90f3d5d5e2b1ae010cbeca8bf8da4d786e2a03b0); [CI #40709954313](https://github.com/SkyBluekor/StockScope/actions/runs/40709954313) **4/4 PASS**, Backend Python 3.11/3.14 each **2,589 passed / 2 skipped**; Frontend and Fresh Clone Windows PASS.
- New developer-only source: `backend/app/jev/synthetic_live_01.py`, `tools/data/jev_live_01_synthetic_smoke.py`, `backend/tests/test_jev_live_01_synthetic_service.py`. It uses the real TypeSafe adapter (HTTP mock in CI), existing V4 manual review service and TypeSafe catalog. Only fixed, authored synthetic sample, fresh temporary SQLite and masked preview; Scanner/API default OFF unchanged.
- User Windows runtime check still **NOT DONE**. Paid TypeSafe live smoke still **NOT DONE** (no billable authorization and no local API credential accessible to CI). Both remain explicitly pending before LIVE-01 DONE. Real market input source-rights gate remains HOLD/NO-GO. Do not describe CI/mocked TypeSafe as an actual billable model review.
- Local offline commands after pulling branch: `python -m tools.data.jev_live_01_synthetic_smoke --mode preflight`, `python -m tools.data.jev_live_01_synthetic_smoke --mode mock`. Both use a newly-created isolated temp DB; mock makes no network calls. Actual live requires one-call explicit approval and verified provider/model evidence, never an operational dataset.

- **Additional CI/WIN CLI verified:** [run #40710701393](https://github.com/SkyBluekor/StockScope/actions/runs/40710701393) on `6d6c35a`, 4/4 PASS. Actual Windows Fresh Clone `preflight` + `mock` CLI returned stored `VALID` / `REVIEW_REQUIRED` / model identity `MATCHED` / billed requests `0`. This remains a **mock** endpoint run, not live TypeSafe or user-PC validation.


## 2026-10-29 LIVE-01 코드 보완

- 작업 브랜치 동일, Draft PR #170 유지. `01f27ba`에서 synthetic live CLI의 Mock/미검증 provider 증빙 거부, `77bdefd`에서 회귀 테스트 추가.
- 새 커밋의 CI 상태는 **미확인/대기**, 실제 TypeSafe 유료 1회 요청과 사용자 Windows 수동 검증은 **미실시**. 기존 4/4 PASS를 이번 커밋의 CI 결과로 표시하면 안 됨.
- LIVE-01 최종 완료 판정은 계속 보류. 별도 승인된 실제 synthetic-only provider 요청 및 저장 검증 후 완료 처리. S7.4 실시장 데이터 전송 금지, G2-05 보류 유지.

- **2026-10-29 CI 확인:** [GitHub Actions #40713831348](https://github.com/SkyBluekor/StockScope/actions/runs/40713831348) **4/4 SUCCESS** (Backend Python 3.11/3.14, Frontend Node 22, Windows Fresh Clone). Windows synthetic preflight 및 HTTP Mock V4 integration 단계 성공. 이전 #40713750927은 **CANCELLED**이며 실패 테스트의 근거가 아님. 실제 유료 TypeSafe 요청·사용자 Windows 확인 **미실시**, LIVE-01 **NOT DONE**, 시장 원천 외부 전송 **HOLD**.


### 2026-10-29 사용자 PC 실제 Windows 확인 (HTTP mock; paid live 아님)

- `C:\Projects\StockScope`에서 올바른 개발 브랜치 `codex/p0-01-mvp-c1-c2-integration-20261022`와 `8b50afd` 확인. `--mode preflight` 및 `--mode mock` 사용자 실행 PASS.
- Mock 검증 저장값: `VALID` / `REVIEW_REQUIRED` / `MATCHED`; billable provider 요청 0. G2-01~04 및 Scanner baseline 유지, G2-05 계속 보류.
- 사용자가 실제 합성 유료 호출 1회 승인했지만 실행되지 않았음. PowerShell 환경변수 `JEV_API_KEY`가 NOT SET; provider 코드가 프로젝트 루트 `.env` fallback을 지원하므로 다음에 로컬 키 존재 여부를 출력 없이 확인할 것.
- TypeSafe 공식 문서에서 `jev-1.14.0` 및 `jev-latest` 매핑 확인(2026-10-29); authenticated model catalog + hash/retention 증빙 고정 후 synthetic-only 1회 호출. LIVE-01은 그 검증 전까지 NOT DONE.


## 2026-10-29 LIVE-01 **DONE** 인수 및 다음 실제 개발

이전 문서의 LIVE-01 `PENDING` / `NOT DONE` 문장은 해당 시점의 과거 기록이며 **최신 상태를 대체하지 않는다**. 사용자 PC `C:\\Projects\\StockScope` 브랜치 `codex/p0-01-mvp-c1-c2-integration-20261022`, 호출 당시 HEAD `10af121`에서 **실제 유료 TypeSafe 1회 성공**. 단일 작성 합성 fixture, 원천시장 데이터 0; V4 request `jev-1.14.0` / returned `jev-1.14.0`, `model_identity_status=MATCHED`. 결과 `PASS_THROUGH` / `NO_ADDITIONAL_RELATION_CONFLICT`, 기존 catalog 조회 `stored_status=VALID`, `review_id=ff4f5134-a65f-485c-87ca-c163c8a9dad0`, input/output 1073/23, 비용 미확정, `failure_code=null`, `billable_provider_requests=1`, exit code 0. Mock은 REVIEW_REQUIRED였으나 실제 응답은 PASS_THROUGH였음을 구분한다.

- 개발자 CLI·코드·CI 4/4 통과([#40713831348](https://github.com/SkyBluekor/StockScope/actions/runs/40713831348)) 및 사용자 Windows 실제 합성 E2E를 기준으로 **LIVE-01 완료**. 실제 시장 후보 모델 검토가 완료됐다는 뜻은 아님. 이번 실호출 승인은 **1회 사용 완료**, 별도 승인 없이 추가 과금 호출 금지.
- **NEXT: JEV-LIVE-02**. `backend/app/jev/scanner_lineage_s7_4.py`, `scanner_v4_readiness_s7_5.py`, `scanner_eligibility_s8.py`, `backend/app/api/jev.py`, `frontend/src/components/ScannerPanel.tsx`의 기존 read-only 데이터 흐름을 재사용해 사용자 후보별 준비/차단 이유를 표시. 외부 호출/DB write 없이 구현 및 CI. 실제 사용자 데이터 테스트는 로컬 격리 스냅샷에서.
- LIVE-03의 KRX·시장 파생 데이터 전송권한은 여전히 HOLD. `GET /review-feature` 고정 OFF 및 `POST /reviews` 기본 OFF 유지. PR #170 Draft, G2-01~04 유지, G2-05 보류.


## 2026-10-29 LIVE-02 구현 현황 — 다음 채팅 반드시 반영

- Backend `GET /api/simulation/jev/local-readiness?capture_id=<id>&sample_index=<1-based>` 구현: 기존 `load_frozen_candidates` (canonical COMPLETE, SQLite mode=ro)와 S7.5/S8 및 S7.1 integrity 검증을 그대로 사용. 전송 허가/모델 호출·DB 쓰기 없이 `status` (`SOURCE_RIGHTS_HOLD`, `LOCAL_ONLY`, `NEEDS_EVIDENCE`, `NOT_ENTRY_CANDIDATE`), `local_readiness` (`LOCAL_READY` 포함), 순위·전략·Risk·정책·시점/권한 신원 및 이유 코드 반환.
- Frontend `ScannerAiReview`가 사용자가 선택한 후보의 1-based sample index와 capture id로 이 API를 조회하고, market/ticker/capture/sample 신원이 다르면 표시 금지. AI 검토가 완료됐다고 가장하지 않고 로컬 진단·모델 미실행을 구별하며 기존 G2 UI 보존.
- Backend 합성 HTTP 계약/원본 SQLite 불변성/비활성 user review-feature 테스트 + 전체 Frontend build/Chromium, Windows Fresh Clone CI **4/4 SUCCESS**, HEAD `17212739a7d317a0344a6b6a17e9ecd7662b53e4`, [GitHub Actions #40795790479](https://github.com/SkyBluekor/StockScope/actions/runs/40795790479). 다음 커밋 문서 CI는 별도 추적.
- **LIVE-02는 아직 DONE 아님.** 사용자 실제 Windows `C:\\Projects\\StockScope`의 COMPLETE 캡처에 대해 실제 Browser + FastAPI 읽기 전용 상태 표시, 후보를 바꿨을 때 신원과 차단 코드의 변화 확인 필요. 특정 real 15-snapshot 통과를 가정하지 마라. 운영 원본 DB를 덮거나 새 마이그레이션하지 말고 격리 preview / 기존 snapshot 사용.
- 이미 승인한 **TypeSafe 합성 유료 1회 소진**, 추가 과금 요청 금지. 시장 유래 원천 데이터 전송 NO-GO 유지; 기존 POST reviews 기본 OFF. G2-05 보류; G2-01~04 유지, Draft PR #170 merge 금지.
- 예전 `C:\\Projects\\StockScope-G2` 경로는 해당 사용자 현재 Windows PC에 없고, 사용자가 실제 확인한 경로는 `C:\\Projects\\StockScope`. 새 worktree를 강제 만들지 말 것. `git status --short`가 깨끗하면 최신 개발 브랜치 `git pull --ff-only` 후 기존 가상환경 재사용.


## 2026-10-29 사용자 Windows LIVE-02 API 테스트 결과 추가

- 사용자 `C:\Projects\StockScope` checkout은 `git pull --ff-only` 정상 적용, HEAD `7d99e6a`.
- 새 `backend/tests/test_jev_live_02_local_readiness_api.py`를 사용자 Windows `.venv`에서 실행해 **2 passed, 0 failed**; Starlette/AnyIO deprecation warning은 비차단.
- 동일 HEAD GitHub [CI #40796193659](https://github.com/SkyBluekor/StockScope/actions/runs/40796193659) **4/4 SUCCESS**.
- 다음 미완료 인수는 **실제 사용자 COMPLETE 캡처를 격리 SQLite snapshot에서 조회하고 선택 종목 브라우저 AI 탭의 준비도·NO_GO/미실행 사유가 맞는지 확인**. API 테스트만으로 LIVE-02 DONE 처리하지 말 것. 데이터/키 출력 금지, TypeSafe 추가 유료 요청 0, G2-05 보류.


## 2026-10-29 LIVE-02 사용자 브라우저 첫 UAT 실패와 정확한 수정

- 사용자 2026-10-28 Scanner 저장 후보 `셀트리온/KOSPI 068270` 선택 화면에서 LIVE-02 카드가 렌더링되었으나 `저장 캡처와 선택 종목의 식별 정보가 다릅니다`가 표시됨. 실제 후보 선택/브라우저 로딩은 확인되었으나 **LIVE-02 미완료**.
- 원인: `backend/app/prospective/catalog.py` 저장 `sample_index`는 0-based, LIVE-02의 React 표시 `rank`는 1-based. 1번 후보 선택 때 API에서 1번 저장 행(두 번째 후보)을 조회해 ticker mismatch 차단됨. 데이터가 망가진 게 아닌 UI/API index 연결 버그.
- 해결: `ScannerPanel.tsx`에서 `sampleIndex={rank-1}`, `ScannerAiReview.tsx`에서 인덱스 0 허용, `backend/app/api/jev.py` GET에서 Query ge=0 허용, TS API 주석 보완. `backend/tests/test_jev_live_02_local_readiness_api.py`에 첫 후보 index0/다음 후보 index1 distinct hash 및 진단 DB 바이트 불변 검증 추가. 수정 마지막 코드 커밋 `52d680480508b9aea857dc71436e5227fee53d55`, [CI #40797590774](https://github.com/SkyBluekor/StockScope/actions/runs/40797590774) **4/4 SUCCESS**.
- 다음은 사용자 로컬 checkout pull 후 **기존 격리 SQLite preview를 물고 있는 backend 서버를 재시작**하고 (PowerShell 환경변수를 날리지 말 것), frontend 강력 새로고침하여 선택한 후보의 readiness/no-go 이유 표시 확인. 재확인 전 LIVE-02 DONE 아님. LIVE-01 합성 유료 1회는 완료·추가 호출 불가; 실종목 전송 HOLD.


## 2026-10-29 최종 우선순위 갱신 — LIVE-02 DONE, 다음은 LIVE-03

- 사용자가 2026-10-28 저장 Scanner 후보 **셀트리온(KOSPI 068270)** 를 선택한 실제 Windows 브라우저 `http://127.0.0.1:5173` AI 검토 탭 스크린샷을 제시함. **이전 다른 후보 식별 정보 오류가 해소**되고, 해당 선택 종목의 로컬 준비도 결과와 구체적 차단 이유가 화면에 표시됨.
- 표시된 상태: 입력 근거 확인 필요, `V4 BLOCKED_HORIZON`, 출처 연결 `COMPLETE`, 순위·Risk·정책 `PASS`, 전략 `LEGACY_DERIVED`, 원천 공개 시각 `UNKNOWN`, 권한 `UNVERIFIED`, TypeSafe 전송 금지 (`SOURCE_RIGHTS_HOLD`), 실제 모델 요청 0회. 준비도 결과는 AI 판정이 아니며 PASS를 전송 허가로 해석 금지.
- 사용자 Windows pytest `backend/tests/test_jev_live_02_local_readiness_api.py` **3 passed**. 마지막 코드 SHA `52d680480508b9aea857dc71436e5227fee53d55`; [코드 CI #40797590774](https://github.com/SkyBluekor/StockScope/actions/runs/40797590774) 4/4 SUCCESS. [직전 문서 CI #40797912620](https://github.com/SkyBluekor/StockScope/actions/runs/40797912620) 4/4 SUCCESS.
- **LIVE-02 DONE** (개별 실제 후보를 선택하면 읽기 전용 준비도와 차단 이유가 표시되는 단계의 완료 기준 충족). 이전 섹션의 `PENDING` 표기는 시점별 과거 이력이며 현재 완료 판정이 아님. 다른 종목 선택 후 상태변경 검증은 추가로 유용하지만 이 단계 범위의 단일 실제 후보 UI 인수를 막지 않는다.
- **NEXT LIVE-03**: 실 시장 원천 KRX 및 조건 PASS·Risk·순위 등 파생 판단의 TypeSafe 외부 제공 권한, 소스·시점·사용자 계정 범위를 검증. S7.4/S8 기존 자료 재사용, 허가 없는 market-derived 전송 금지. 환경 및 화면이 정상이라도 실모델 실종목 사용 가능 상태가 아니다. API default review OFF 및 G2-01~04 보존, G2-05 pause, PR #170 Draft 유지. 추가 유료 TypeSafe 호출 미승인.

 
## 2026-10-29 LIVE-03 신규 구현과 다음 인수 (반드시 읽기)

- 코드 `backend/app/jev/scanner_outbound_gate_live_03.py` [`226af65`](https://github.com/SkyBluekor/StockScope/commit/226af65b8b839477d721cdeed33185811a86701c): S7.4/S8 불변, 원천 종목의 V4 field-by-field 경로·부모 KRX/내부 조건, 권한/시점/수신자·모델 처리 조건의 미확인 결과와 HOLD reason 코드. 프로젝트가 보유하지 않은 개별 KRX source/revision 승인·공개 시각을 스스로 만들어내지 않음.
- 요청 검사: `inspect_wire_body`는 형태를 엄격 검증한 구조의 httpx 실제 `json=body` serialization 바이트 지문 SHA256/길이를 로컬에서 계산함 (기존 canonical sort JSON hash와 구별). `verify_http_request_binding`은 재구성된 HTTP 요청의 byte/URL/메서드/model 변조를 탐지하는 helper이며 **권한 인증 및 provider 런타임 발송 승인을 부여하지 않는다**. 현재 실제 market API 발송 경로는 OFF.
- [Backend GET `df19037`](https://github.com/SkyBluekor/StockScope/commit/df190373150e6f5e65c59cfc1eb8625f92cd29f1), [Frontend TS API `4a5da68`](https://github.com/SkyBluekor/StockScope/commit/4a5da6840b895ead8f676f4b4d1d5efbb94cc384), [Scanner UI `9ad76ad`](https://github.com/SkyBluekor/StockScope/commit/9ad76adbb4ed7270bead838e18898f5667eb6daa). 실제 캡처 identity 일치 시 로컬 HOLD/시점·권한 사유 표시, TypeSafe calls 0, DB writes 0.
- [합성 API/HTTP mutation 테스트 `3f3bb62`](https://github.com/SkyBluekor/StockScope/commit/3f3bb62d8dcb1efc3e37c3dabf6a60c5e2c50c0f), [실제 코드 HEAD CI #40805284863](https://github.com/SkyBluekor/StockScope/actions/runs/40805284863) **4/4 SUCCESS**: Python 3.11/3.14 backend, frontend Node22/Chromium, Windows Fresh Clone. CI 유료 TypeSafe 0. 사용자 실제 Windows `C:\Projects\StockScope` 신규 LIVE-03 UI 수동 검증은 아직 수행하지 않았음.
- **다음:** 같은 개발 브랜치 `git pull --ff-only` 후 기존 격리 preview backend/frontend에서 사용자가 실제 저장 후보(셀트리온 2026-10-28) 선택 → AI 검토 탭 LIVE-03 외부 전송 상태/권한 사유, 증거 없는 `HOLD`와 0 호출 확인. 실서버 외부 전송 허가가 없으므로 LIVE-03 전체 DONE 아님. TypeSafe 담당자/계약 및 KRX 계정 상품별 원천·파생 사용권 증거, 수집 revision/시점, 신뢰된 RA01~10 검증자/approved scope 준비가 추가 과제로 남음.
- **명확한 경계:** 원시/파생 시장데이터를 실모델로 보내지 말 것. 현재 HOLD가 안전한 정확한 판정이고 hash, 사용자 클릭/키 또는 편의상 flag만으로 허가로 바꾸지 말 것. LIVE-04 실제 실종목 API 호출은 이 조건 충족 후 별도 실행 승인. G2-01~04 유지, G2-05 보류, PR #170 Draft, 운영 sqlite 불변, LIVE-01/02 DONE.


## 2026-10-29 LIVE-03 사용자 Windows 스크린샷 인수 — 최신 상태

- 사용자가 C:\Projects\StockScope 브랜치 최신 pull (0873079), targeted backend/tests/test_jev_live_03_outbound_gate.py **4 passed** 실행 로그 제공. 실제 localhost:5173 Scanner 2026-10-28 셀트리온(KOSPI 068270) 선택 AI 검토 스크린샷에는 새로운 LIVE-03 카드가 정상 렌더됨. 후보 ticker mismatch 없음.
- 화면 판정은 **외부 전송 보류**이며 실제 TypeSafe 호출 없음. NOT_AUTHORIZED, time_authenticity=UNVERIFIED, trusted_rights_resolver=NOT_CONFIGURED, OUTBOUND_BODY_NOT_VERIFIABLE, EXECUTION_APPROVAL_NOT_GRANTED, LEGACY_HORIZON_UNDEFINED 등 실제 부족한 근거 표시. LIVE-02에서 이 셀트리온 후보가 BLOCKED_HORIZON이었으므로 V4 body 미생성/전송 차단이 올바르다.
- [LIVE-03 코드 CI #40805284863](https://github.com/SkyBluekor/StockScope/actions/runs/40805284863) **4/4 PASS**, [직전 문서 CI #40805668772](https://github.com/SkyBluekor/StockScope/actions/runs/40805668772) **4/4 PASS**. 본 사용자 화면은 실제 HTTP 발송 테스트가 아니며 합성 wire hash 변조 시험과 구분한다.
- **최신 LIVE-03 상태: LOCAL GATE + WINDOWS UI DONE, outbound authorization=HOLD/NO-GO.** 당초 단계의 ALLOW 또는 HOLD/DENY + 이유 요구에서 현재 실제 후보는 HOLD로 정확히 검증됨. 기존 NOT DONE / 화면 미검증 문장은 이전 시점 기록이다. 단 KRX 원천/파생 외부 AI 처리 권한·계정별 TypeSafe 보관조건·source revision/공개시간·RA01-RA10 신뢰된 증빙 확보는 아직 미완료이며 실종목 호출 가능하다는 의미는 아니다.
- **NEXT: LIVE-04 실종목 HTTP provider 실행은 권한·시점·execution approval 확보까지 BLOCKED.** 합성/Mock 단일 후보 UI opt-in, background job 및 중복과금/오류 경계 구현은 가능. 실제 TypeSafe provider adapter에 trusted resolver + byte-exact binding을 send 경계에 붙이지 않고 실종목 전송 활성화 금지. 추가 유료 TypeSafe 호출 승인 없음. G2-01~04 유지, G2-05 보류, PR #170 Draft, 정상 Scanner/Risk/DB 불변.


## 2026-10-29 LIVE-04 Mock 수동 검토 실제 구현 및 다음 UAT

- **현재 코드 마지막 합성 UI 커밋:** [`286faf1`](https://github.com/SkyBluekor/StockScope/commit/286faf1134abb20c276b2e20d88ad72e9d714fce), [앱 startup lazy import 수정 `8b7e1ad`](https://github.com/SkyBluekor/StockScope/commit/8b7e1ad8b13a659382f370e641ee68900cb60870). [백엔드 테스트 `a74c343`](https://github.com/SkyBluekor/StockScope/commit/a74c343c0a507bbccf290f23020e797871253ff5). [코드 CI #40808788891](https://github.com/SkyBluekor/StockScope/actions/runs/40808788891) **4/4 PASS**: Backend Python 3.11/3.14, Frontend Node22/Chromium, Windows Fresh Clone.
- `backend/app/jev/synthetic_live_04_demo.py`는 server OS env `STOCKSCOPE_JEV04_SYNTHETIC_DEMO=1` + 요청 host/remote loopback일 때만 사용 가능. `POST /api/simulation/jev/synthetic-demo/start`는 명시 확인 헤더 `X-StockScope-Synthetic-Demo: confirmed` 요구, **실제 종목 id/사용자 payload 요청 필드 받지 않음**. `GET /synthetic-demo/status`는 임시 경로 합성 저장 상태만 반환. 앱 시작부터 Fixture를 import하지 않고 첫 opt-in 때만 원래 LIVE-01 작성 합성 함수 및 개발용 migration 코드를 불러온다 (CI 초기 import 문제 해결).
- 사용자가 누르면 가상 ticker `999991` 전용 새 OS temp SQLite + FROZEN V4 protocol + job record 생성. 기존 `JevManualReviewService`에 `FakeTypeSafeJevProvider` 주입하여 실제 V4 판정·TypeSafeJevCatalog 저장, ASGI `BackgroundTasks` 사용(외부 분산 worker가 아님). job 상태는 `QUEUED→RUNNING→VALID/ERROR`; 중복 클릭 시 기존 job 반환. 프로세스가 재시작되어 미완료면 `INTERRUPTED`로 처리, 자동 재시도·재청구 없음. **실제 TypeSafe 전송·과금 0**. 임시 DB는 운영 `STOCKSCOPE_SIM_DB`와 분리.
- Scanner AI 탭 상단에 `JevSyntheticDemo.tsx`를 넣어 수동 합성 버튼·V4 저장 결과를 확인하고 LIVE-02/03 상세 근거는 접힌 섹션으로 정리. 다만 사용자 실제 Windows 브라우저 클릭 UAT 및 새로고침 재조회는 **아직 하지 않았다**. CI 통과로 DONE 판정 불가.
- **다음 사용자 Windows 실행:** 기존 `C:\Projects\StockScope`에서 `git pull --ff-only`, `.venv\Scripts\python.exe -m pytest -c .\backend\pyproject.toml .\backend\tests\test_jev_live_04_synthetic_demo.py -q`; 기존 dev 서버 종료 후 같은 터미널에서 `$env:STOCKSCOPE_JEV04_SYNTHETIC_DEMO='1'`, `.\run-dev.ps1`로 실행. localhost Scanner AI 탭에서 합성 체험 체크박스→버튼 클릭→`REVIEW_REQUIRED` / `VALID` / mock model matched / real requests 0 재조회 후 증거 제출. **실종목 셀트리온 결과와 구분할 것**. OS temp one-shot이므로 중복 클릭 시 새 Mock 작업 만들지 않고 이미 저장된 결과를 보여줌.
- **LIVE-04 상태:** Synthetic Mock CODE+CI PASS, 사용자 Windows UAT PENDING; 실제 시장 데이터의 real paid JEV 검토 BLOCKED by LIVE-03 rights (KRX raw/derived, as-of, account scope and trusted adapter execution approval). 기존 `GET /review-feature` default OFF, public `POST /reviews` disabled. G2-01~04 유지, G2-05 보류, Draft PR #170 유지. 새 유료 승인 없음.


## 2026-10-29 LIVE-04 실제 Windows 브라우저 결과 확인 — 최신

- 사용자가 Scanner AI 검토 탭에서 선택 실제 후보 **셀트리온 / KOSPI 068270**와 별도 가상 후보 **999991의 `JEV 수동 검토 체험 · 순수 합성 데이터 (개발 전용)` 결과**를 한 화면에 제시함. 가상 Mock 상태 **`합성 결과 검증·저장 완료`**; 결과 **`추가 확인 필요 (REVIEW_REQUIRED)`**, 반환 모델 **`jev-mock-returned`**, `MATCHED`, 실제 API 사용량 **0**, 합성 Mock 호출 **1**, Mock 비용 **$0.0000**, 저장 review ID가 표시됨. 화면은 실제 셀트리온에 대해 여전히 `AI 검토 미제공`을 표시하므로 결과가 섞이지 않음.
- **LIVE-04 합성 Mock UI UAT PASS**. 사용자 screenshot은 저장 결과 표시까지 증명하지만 새로고침 후 영속성이나 중복 재클릭을 실제 조작으로 확인한 근거는 아님. 이 부분은 [기존 합성 HTTP 테스트](https://github.com/SkyBluekor/StockScope/commit/a74c343c0a507bbccf290f23020e797871253ff5) + [CI #40809193328](https://github.com/SkyBluekor/StockScope/actions/runs/40809193328) 4/4 PASS가 검증함.
- **LIVE-04 실제 실종목 real TypeSafe E2E는 계속 BLOCKED**: S7.4/S8 원천 및 파생권·공개시간·revision/계정별 처리조건·송신 직전 trusted authorization, 지원 Horizon 및 전략 신원 미확보. 합성 Mock 성공은 실종목의 전송 승인이나 JEV 의견이 절대 아님. 무료 Mock 1회 외 새 유료 API 호출·시장 정보 전송 금지. Draft PR #170, G2-01~04 유지, G2-05 보류.
- 다음 개발에서는 실종목 JEV 허용에 필요한 증거가 외부 조건으로 막힌 현실을 명시하고, **근거 없는 반복적인 HOLD 진단/긴 로그 UI** 대신 사용자 실사용 가치가 있는 대안을 검토. 단 권한 없는 외부 전송·승인 플래그 우회를 하지 말 것.
- **사용자 PC 개발 실행 명령은 명확히 `.\run-dev.ps1`**. 과거 문서의 `.\dev` 표기는 잘못된 안내로 간주. 기존 `C:\Projects\StockScope` 폴더 사용, 사용자가 불필요한 새 worktree 원치 않음.


## 2026-10-29 LIVE-04R CODE/CI PASS · 사용자 Windows UAT PENDING

- **새 기능(코드 구현):** `GET /api/simulation/jev/local-readiness`에 `input_contract` 추가. 저장된 `horizon_intent`/정책 버전 및 실제 승인 상태(`EVALUATION_PENDING`, `LEGACY_UNSPECIFIED`, `UNSUPPORTED`)를 구분, 원본 전략은 `strategy + policy + engine PASS`일 때만 `CAPTURED_ORIGINAL`로 표시하고 레거시 유도 신원은 `LEGACY_DERIVED_NOT_ORIGINAL`로 남김. 캡처 생성/시작/완료 시각과 **입증되지 않은 실제 원천 최초 공개시각(null)** 구분. 구형 캡처 DB 시각 컬럼이 없으면 null; 원본 SQLite/snapshot 변경 없음.
- **UI:** `ScannerAiReview.tsx`에 선택한 실제 종목의 로컬 V4 준비도·전략 원본 신원·기간 정책 상태·TypeSafe 권한 HOLD를 짧게 표시하고 실제 JEV 버튼 비활성화. 내부 원인/hash는 접힌 상세에 유지. `JevSyntheticDemo.tsx` Mock 결과는 접힌 개발자 영역으로 이동. 사용자가 이전 합성 Mock 결과를 실제 종목 의견으로 오해하지 않도록 구분.
- **핵심 구조 사실:** `ProspectiveService.capture_request_from_scanner_payload`는 이미 명시된 Horizon을 기록하고 미지정은 `LEGACY_UNSPECIFIED`로 보존한다. `verify_candidate_policy_binding`는 실제 ACTIVE 실행 Pin의 전략 버전/hash가 후보 원본과 일치해야만 승인한다. **이 방어를 우회해 LEGACY 신원을 원본으로 만들지 말 것**. `resolve_horizon_context`의 수치 정책은 아직 `EVALUATION_PENDING`; 임의로 활성화하거나 기간을 부여하면 안 된다. 신규 실후보 V4 구조적 준비 완료는 **입증 안 됨**.
- **CI:** 신규 저장 캡처 경계/구형 DB/invalid Horizon 안전 테스트 포함 [코드 HEAD `9dac50d`](https://github.com/SkyBluekor/StockScope/commit/9dac50da0227a42c44adc8e943d1fc6ab2ef2f45), [Actions #40823176776](https://github.com/SkyBluekor/StockScope/actions/runs/40823176776) **4/4 SUCCESS** (Backend Python 3.11/3.14, Frontend Node22/Chromium, Windows Fresh Clone). 첫 CI 실패는 구형 fixture에 생성/시작 timestamp 컬럼이 없던 점 및 터미널 불변 캡처 변경을 시도한 새 테스트; 둘 다 코드를 방어적으로 수정하고 테스트를 순수 함수로 옮겨 해결. 실제 TypeSafe 유료 호출 0.
- **다음 인수:** 사용자 Windows `C:\Projects\StockScope` `git pull --ff-only`, 기존 서버 중지 후 `.\run-dev.ps1` 재시작, Scanner > 실제 종목 > AI 검토 요약/전략·Horizon·권한 정보 및 합성 Mock 접힌 화면 확인. 해당 브라우저 UAT 전 LIVE-04R DONE 판정 금지. 실제 소스 KRX 원본/파생 권한과 TypeSafe 계정 처리조건, 수치 Horizon 승인·원본 전략 신규 생성 경로는 아직 미해결이고 실종목 TypeSafe 호출 NO-GO.
- **보존:** G2-01~04 유지, G2-05 보류, Draft PR #170 유지, LIVE-01 합성 유료 실행 1회 완료, LIVE-02/03 및 LIVE-04 Mock 기존 인수 보존, 실제 시장 provider 0 호출 유지.


## 2026-10-29 LIVE-04R Windows screenshot — visual layout PASS, backend UAT NOT PASS

- 사용자 실제 `http://127.0.0.1:5173` Scanner 스크린샷에서 셀트리온(068270) AI 검토 요약, 비활성 실종목 JEV 검토 버튼, 접힌 LIVE-02/03 상세, 접힌 합성 개발용 체험이 정상 표시됨. **UI 배치 확인됨.**
- 그러나 **서버 준비도/전송 자격 결과는 실제로 받아오지 못함**. 화면: `후보 신원 검증 실패 · 결과 표시 차단`, `로컬 준비도를 확인하지 못했습니다. 저장 캡처와 DB 상태를 확인하세요`, `외부 전송 근거를 조회할 수 없습니다`. 이는 응답된 `HOLD`가 아니라 클라이언트의 `catch`에 따른 **API 조회 실패**임. `LOCAL_V4_PROJECTABLE` 또는 실종목 정책 판정 검증으로 기록하지 말 것.
- 공통 의존성: 두 GET 경로 `/api/simulation/jev/local-readiness`, `/api/simulation/jev/outbound-preflight`는 `backend/app/api/jev.py`의 `_db()` = `STOCKSCOPE_SIM_DB` 또는 `backend/runtime/simulation/simulation.db`와 요청 `capture_id`, `sample_index`로 동일 COMPLETE 캡처를 읽음. 오류 원인은 **미확정**; 과거 Windows에서 임시 DB 경로 환경변수를 설정한 적 있어 경로 실재/서버 상속 여부 검사 필요. 프런트의 공통 catch가 HTTP 응답 코드/세부 reason을 감추므로 브라우저 Network의 두 요청 status+response JSON 및 backend 콘솔 확인.
- 최소 재현: `http://127.0.0.1:8000/` 접속 및 backend 8000 동작 확인; 서버를 시작한 창에서 `$env:STOCKSCOPE_SIM_DB`와 `Test-Path` 확인. Chrome F12 → Network → `local-readiness`, `outbound-preflight` Response 코드 확인. **운영 DB 변경·캡처 재작성·TypeSafe 유료 호출 금지**. 정확한 실패 응답을 확인하기 전에는 이전 UAT PASS 주장 금지.
- 기존 [코드 CI #40823176776](https://github.com/SkyBluekor/StockScope/actions/runs/40823176776) 4/4 PASS는 유지하되, **Windows 실제 후보 API UAT 실패/진단 대기**로 상태 분리. 평소 실행 `.\run-dev.ps1`, 기존 `C:\Projects\StockScope`, Draft PR #170, G2-05 보류 유지.


## 2026-10-29 LIVE-04R actual Windows 422 investigation — backend DB process mismatch suspected

- User's PowerShell read-only SQLite query against `$env:STOCKSCOPE_SIM_DB` (existing `C:\Users\USER\AppData\Local\Temp\StockScope-JEV02-...\simulation.db`) **found** a `COMPLETE` 2026-10-28 셀트리온 `068270` candidate, `sample_index=0`. Same PowerShell request to `127.0.0.1:8000` gave **both** `GET /api/simulation/jev/local-readiness` and `GET /outbound-preflight` **HTTP 422 / S7_CAPTURE_NOT_COMPLETE**. Basic backend `GET /` 200, local DB file exists. With identical capture id and sample index, this strongly suggests **backend PID uses a different SQLite file** than the requesting PowerShell; not yet conclusively proven by process-level inspection.
- Root of launcher risk: `run-dev.ps1` previously started new backend/frontend PowerShell processes **unconditionally** and immediately printed "servers started"; when an older `uvicorn --reload` occupied port 8000, the new backend could fail to bind while the old server kept serving the different DB. Changed [`a6baa41`](https://github.com/SkyBluekor/StockScope/commit/a6baa4169932cd30738ec0fcbd7ceb1616d8cde6): fail before launching either server if 8000/5173 port is already LISTEN, report owning PIDs; reject missing explicit `STOCKSCOPE_SIM_DB`; print configured DB scope and "launches requested" rather than unverified readiness. Does not stop/kill existing processes automatically.
- **Not verified fixed** until user stops prior backend/frontend PowerShell via Ctrl+C, observes 8000/5173 free, pulls new script and restarts `.\run-dev.ps1` from the PowerShell with valid `$env:STOCKSCOPE_SIM_DB`, then retries two read-only API GETs. Keep LIVE-04R actual Windows API UAT **FAIL/PENDING** until both return 200 with selected candidate. No SQLite mutation, TypeSafe network or paid calls.


## 2026-10-29 LIVE-04R Windows API recovery CONFIRMED — user actual log

- **Follow-up user test after launcher/port handling:** local read-only SQLite still finds **셀트리온 068270**, COMPLETE saved capture, `sample_index=0`. The **same exact PowerShell `$check`** now obtains `GET /api/simulation/jev/local-readiness` **HTTP 200** with `ticker=068270`, `status=NEEDS_EVIDENCE`, and `GET /api/simulation/jev/outbound-preflight` **HTTP 200** with `ticker=068270`, `decision=HOLD`. Earlier both requests yielded `422 S7_CAPTURE_NOT_COMPLETE`. **This concrete failure is resolved at the backend HTTP/read-only database boundary.**
- Most likely cause was a previous server process using a different SQLite store; user logs did **not** demonstrate process-level forensic attribution, so mark it **suspected, not proven**. [Launcher port guard `a6baa41`](https://github.com/SkyBluekor/StockScope/commit/a6baa4169932cd30738ec0fcbd7ceb1616d8cde6) prevents new duplicate port owners and warns if the configured isolated DB path is missing.
- **Do not confuse successful HTTP GET with actual TypeSafe authorization:** local input remains `NEEDS_EVIDENCE`, outbound remains `HOLD`, no actual model call. Browser refresh showing error banners disappear **has not yet been provided**; LIVE-04R UI+actual candidate end-to-end UAT is pending final screenshot. User Windows startup is `.\run-dev.ps1` from `C:\Projects\StockScope`.


## 2026-10-29 LIVE-04R 최종 기존 후보 브라우저 재검증 — UI/API PASS, V4 신규 후보 준비 미완료

- 사용자의 후속 Windows 브라우저 스크린샷에서 **셀트리온(KOSPI 068270)** 선택 후보 AI 검토 탭에 간결 요약 **선택 종목, 기존 Scanner 판단 유지, 로컬 입력 근거 확인 필요, 원본 전략 신원 미확인, Horizon 상태 확인 필요, 외부 TypeSafe 권한 보류**가 정확히 표시되며, 앞선 `로컬 준비도 확인 실패`와 `외부 전송 근거 조회 실패`는 사라짐. 실제 종목 JEV 추가 검토 버튼 비활성 상태 유지. 개발용 합성 Mock 결과는 실제 셀트리온 의견과 별도 영역으로 구분됨.
- 브라우저 증거 + 직전 사용자 로컬 HTTP 검사: `GET /local-readiness` **200, ticker 068270, status NEEDS_EVIDENCE**, `GET /outbound-preflight` **200, ticker 068270, decision HOLD**. 기존 실제 후보의 **API 조회 장애 해결 + LIVE-04R 요약 UI Windows UAT PASS**. 종목 선정·Risk·정본 DB·과거 캡처 변경 없음. 기존 코드 [CI #40823176776](https://github.com/SkyBluekor/StockScope/actions/runs/40823176776) 4/4 PASS.
- 422 오류는 재시작 후 해결되었으나 백엔드 프로세스가 다른 DB를 읽은 것이 **가능성이 높은 원인이지 PID별 증명은 없다**. [launcher guard `a6baa41`](https://github.com/SkyBluekor/StockScope/commit/a6baa4169932cd30738ec0fcbd7ceb1616d8cde6) 반영.
- **판정의 한계:** LIVE-04R의 **기존 후보 read-only 준비도/간결 UI 부분은 수동 검증 PASS**. **새로운 실시장 Scanner 캡처에서 `LOCAL_V4_PROJECTABLE` 도달, 수치 Horizon 정책 승인, 전략 원본 연결, 원천 시각/수신 권리 확보는 확인되지 않음**; LIVE-04R 전체 실사용 입력 개선 완료로 과대평가 금지. LIVE-04 실종목 TypeSafe E2E, LIVE-05 여전히 BLOCKED. 추가 실제 Provider 요청/과금 0. G2-01~04 유지, G2-05 보류, PR #170 Draft, 시작 명령 `.\run-dev.ps1`.


## 2026-10-29 LIVE-04R-P2 — 신규 Scanner 캡처 Pin 및 원본 V2 증거 경로 코드+CI 완료

- **구현 코드:** [`ProspectiveCatalog` `00186d6`](https://github.com/SkyBluekor/StockScope/commit/00186d65703df0fe09d46b4ced8d1619a0c21b89): 동일 `source_job_id`의 Scanner `begin_capture`에 저장된 `request_json` 전체와 `finalize_capture`의 요청 전체가 동일해야 한다. Horizon/정책 버전, Selection Policy id/hash, as-of, market_scope, candidate_limit 변경 시 `PROSPECTIVE_CAPTURE_REQUEST_DRIFT`로 동결 거부. 이미 COMPLETE/DUPLICATE/PARTIAL은 기존 idempotent 상태 조회, 이전 동결 데이터 불변. [`ProspectiveService` `8171f6e`](https://github.com/SkyBluekor/StockScope/commit/8171f6ede1a74f4c2f463cd1f4be9bfb0e43617f): drift/invalid begin contract는 보조 캡처만 `FAILED`로 반환하고 실제 Scanner 본 분석은 중단시키지 않음.
- **작성 합성 신선한 ACTIVE 증거 테스트:** [`test_jev_live_04r_fresh_scanner_evidence.py` `0c1533d`](https://github.com/SkyBluekor/StockScope/commit/0c1533d87b6e6624630adc7d92694131d3f7405d)에서 기존 `ProspectiveCatalog`의 시작→최종동결→SQLite 재조회로 원본 version/hash와 Pin, 조건 PASS engine audit가 매칭할 때 `semantic_policy_provenance` VERIFIED 및 `semantic_condition_evidence`, 검증되는 `semantic_source_v2` 저장 확인. PASS 감사 reader는 **의도적으로 작성 합성 row를 monkeypatch**한 것이므로 **실제 신규 KRX Scanner 캡처가 통과했다는 증거 아님**. 감사 누락/변조/정책 불일치 때 V2 원본 증거를 허위로 인정하지 않음을 검증. [Horizon/Policy drift 테스트 `c3198ac`](https://github.com/SkyBluekor/StockScope/commit/c3198ac4ee36448ec6e980a5520ecea09825f947).
- **CI:** [Code HEAD `c3198ac`](https://github.com/SkyBluekor/StockScope/commit/c3198ac4ee36448ec6e980a5520ecea09825f947), [Actions #40826721313](https://github.com/SkyBluekor/StockScope/actions/runs/40826721313) **4/4 PASS** (Python 3.11, 3.14, Frontend Node22, Windows Fresh Clone; 3.11 전체 2623 passed/2 skipped). 서버/실시장 provider 요청·과금 0.
- **현재 판정:** LIVE-04R-P2 **code/CI PASS; 실제 신규 후보 생성 및 Windows UAT 대기**. 현장 원본 Scanner fresh 재현성 artifact, ACTIVE/ROLLBACK policy Pin/후보 hash 결합·평가 Horizon 수치 정책의 `EVALUATION_PENDING` 해소는 미완료. `LOCAL_V4_PROJECTABLE`에 신규 실제 후보가 도달했다고 말하지 말 것. Market raw/derived TypeSafe source-rights HOLD는 변경 없음, 실종목 provider HTTP BLOCKED. LIVE-05 보류, G2-01~04 유지/G2-05 보류, Draft PR #170.
- **Windows 진행:** 사용자는 기존 `C:\Projects\StockScope`의 현재 개발 브랜치를 `git pull --ff-only` 하고 `.venv\Scripts\python.exe -m pytest -c .\backend\pyproject.toml .\backend\tests\test_jev_live_04r_new_capture_pinning.py .\backend\tests\test_jev_live_04r_fresh_scanner_evidence.py -q`로 격리 검증 가능. 사용자 PC의 **기존 실 DB/과거 COMPLETE 캡처를 수정하지 않는다**. 신규 실제 캡처 E2E는 사용자가 별도 승인한 격리 환경에서 확인하고, 기존 평소 실행은 `.\run-dev.ps1`.


## 2026-10-29 LIVE-04R-P2 Windows 테스트 사용자 확인

- 사용자가 이전 안내한 2개 대상 pytest를 **전부 통과했다고 직접 보고**함. 출력 원문·정확한 통과 개수는 미제출. 이 인수는 **작성 합성 기반 변경/불변성 테스트에 대한 Windows 성공**이며 실제 시장 신규 캡처 생성·모델 전송 성공을 뜻하지 않음.
- GitHub [코드 CI #40826721313](https://github.com/SkyBluekor/StockScope/actions/runs/40826721313) **4/4 PASS**, [후속 문서 CI #40827102901](https://github.com/SkyBluekor/StockScope/actions/runs/40827102901) **SUCCESS**. 따라서 LIVE-04R-P2 **코드/CI/사용자 Windows 자동 테스트 PASS**로 기록.
- 다음 반드시 별도 수행할 일: 운영 DB·기존 COMPLETE 불변으로 **신규 실제 Scanner 캡처 1건**의 원본 Selection Policy Pin, fresh Scanner 재현성 감사, 원본 전략 버전/해시, Semantic Source V2, 고정 Horizon 상태를 확인하고 `LOCAL_V4_PROJECTABLE` 가능 여부를 실증. 실제 market TypeSafe HTTP는 원천/파생 데이터 외부 제공권 및 처리 조건 부재로 **HOLD/NO-GO**; 수치 Horizon `EVALUATION_PENDING`이며 LIVE-04 실모델/ LIVE-05 배치로 넘어가지 말 것. 프로젝트 `C:\Projects\StockScope`, 실행 `.\run-dev.ps1`, Draft PR #170 및 G2 상태 유지.


## 2026-10-29 JEV-LIVE-04R-P3 — 단일 신규 실시장 캡처 검사 도구 CODE/CI PASS

- [`live_04r_p3_capture_probe.py` `596092f`](https://github.com/SkyBluekor/StockScope/commit/596092f717a71a018871f3f15d4074262a4e936f), [CLI `29b68bf`](https://github.com/SkyBluekor/StockScope/commit/29b68bf23bdfc465d2f700bc6433a6673c39473a). 기존 `load_frozen_candidates` read-only 및 S7.1/S7.5/S8/V2 함수를 재사용해 **명시 `capture_id` 1건의 실제 저장 후보**에 대해 후보 snapshot hash, original strategy, Selection Policy Pin, engine PASS 감사, V2 계약, Horizon, V4 구조적 입력 및 최초 차단 지점을 로컬 JSON으로 출력. 타입 있는 실제 KRX 수신 증명이나 TypeSafe 전송권을 생성하지 않는다. 원문 시장 가격·V4 전송 본문/비밀 키 출력 없음.
- `--find-new --captured-after <ISO8601 timezone-aware>` 모드에서는 지정 시간 이후 **COMPLETE+ENTRY** 신규 캡처의 ID/생성시각/source_job_id만 목록 조회 (자동 선택 금지). `--capture-id ID --captured-after ... [--sample-index 0]` 는 정확히 그 캡처만 검사. `created_at`이 지정한 새 Scanner 시작 시각보다 오래되었으면 첫 차단 `P3_NEW_CAPTURE_TIME_NOT_VERIFIED`, CLI exit 3. 타임존 없는 시간 거부. 이는 실제 fresh Scanner 수행 증명의 **필요조건**일 뿐 독립 증거가 아님.
- [코드 CI #40829679177](https://github.com/SkyBluekor/StockScope/actions/runs/40829679177) **4/4 SUCCESS**, 대상 테스트는 [`test_jev_live_04r_p3_one_capture.py` `5f1dbc9`](https://github.com/SkyBluekor/StockScope/commit/5f1dbc9864cb9a5f421de562b208826b94da31c4). 테스트는 **작성 합성 SQLite**로 read-only/오래된 캡처 거부/새 ID 검색 등을 확인. **사용자 Windows에서 신규 실제 시장 Scanner 캡처를 실행하고 P3 CLI를 확인한 증거는 아직 없음.**
- **Windows 인수:** 같은 기존 `C:\Projects\StockScope`와 **실제로 `.\run-dev.ps1` 백엔드가 사용하는 격리 `STOCKSCOPE_SIM_DB`** 확인. *새 Scanner 버튼 누르기 전* `$p3Start=(Get-Date).ToString('o')` 기록 → 기존 Scanner 새 분석 실행 → `.\.venv\Scripts\python.exe -m tools.data.jev_live_04r_p3_one_capture --find-new --captured-after "$p3Start" --simulation-db "$env:STOCKSCOPE_SIM_DB"` → 출력 ID 선택 → 동일 CLI `--capture-id "<ID>" --captured-after "$p3Start" --simulation-db "$env:STOCKSCOPE_SIM_DB"`. 신규 COMPLETE+ENTRY가 없으면 절대 과거 ID로 대신 통과 처리하지 않음. 최초 기술적 차단 출력이 나오면 **해당 생성 경로의 실제 코드를 다음으로 수정**, 외부 정책/실제 원천 감사 없는 값은 합성으로 보강하지 말 것.
- **P3 상태:** 검증 코드 + CI PASS / **실신규 Windows 캡처 UAT 미실행**, `LOCAL_V4_PROJECTABLE` 아직 미확인. LIVE-04 실모델 TypeSafe HTTP와 LIVE-05는 계속 BLOCKED: Horizon 수치 정책 `EVALUATION_PENDING`, KRX raw/derived 외부 처리권 `HOLD`, 계정별 TypeSafe 이용/보관 조건 및 독립 source revision/time 부재. 운영 DB 불변/G2-01~04 유지/G2-05 보류, Draft PR #170 유지.


## 2026-10-29 LIVE-04R-P3 `NONE_FOUND` Windows 후속 및 수정

- 실제 사용자 Windows에서 `test_jev_live_04r_p3_one_capture.py` **11/11 PASS**, 격리 `STOCKSCOPE_SIM_DB` 존재. 기준 `2026-10-29T15:36:39.9323285+09:00`; 두 번 `--find-new` 결과 `NONE_FOUND`. 증거상 **새 Scanner job 실행 여부 확인되지 않음**(터미널에는 P3 CLI만 있고 Scanner UI 완료/Job ID 기록 없음). **이것은 아직 Scanner 생성 코드 장애를 입증하지 않는다**.
- GitHub [P3 진단 결함 개선 `23b5f4c`](https://github.com/SkyBluekor/StockScope/commit/23b5f4c69314a60830d13d4a35d68dbafbee87c0), [CLI `78a227c`](https://github.com/SkyBluekor/StockScope/commit/78a227cc44b8b077d9a7ca913fb89c8a1c94c171), [테스트 `a46d42f`](https://github.com/SkyBluekor/StockScope/commit/a46d42feb6903eeb336aaafc53539e9e06f495cd). 종전 `status=COMPLETE+ENTRY`만 조회해 새 분석 `DUPLICATE`, `PARTIAL`, `FAILED`, `PENDING`, `COMPLETE_NO_ENTRY`도 무조건 `NONE_FOUND`로 보이던 문제 해결. `--find-new`는 이제 `new_scanner_capture_attempts` 전체와 상태별 `diagnosis`, 진입 후보 수, DB의 마지막 기록 시각을 읽기 전용 출력. `status`는 `FOUND`, `NOT_ELIGIBLE`, `NO_CAPTURE_AFTER_START`로 구분; 기존 `new_complete_entry_captures`는 유지. 코드 [CI #40831227686](https://github.com/SkyBluekor/StockScope/actions/runs/40831227686) 4/4 PASS.
- 다음 사용자 확인: `git pull --ff-only`, **이미 저장한 동일 시간** `$p3Start="2026-10-29T15:36:39.9323285+09:00"`, 기존 격리 `$env:STOCKSCOPE_SIM_DB`, 동일 `python -m tools.data.jev_live_04r_p3_one_capture --find-new --captured-after "$p3Start" --simulation-db "$env:STOCKSCOPE_SIM_DB"` 호출. `NO_CAPTURE_AFTER_START`이면 아직 UI에서 새로운 Scanner Job 수행과 같은 백엔드 DB 바인딩 확인이 필요. DUPLICATE 등은 기술적 생성 결과로 구분하며 실신규 COMPLETE로 오인하지 않음. 실제 KRX 분석/TypeSafe 호출은 수행하지 않았음, `LOCAL_V4_PROJECTABLE` 미확인, Horizon/rights HOLD 유지.


## 2026-10-29 LIVE-04R-P3 실제 신규 Scanner 작업 → DUPLICATE (사용자 Windows)

- `run-dev.ps1` 실제 표시 DB는 `C:\\Users\\USER\\AppData\\Local\\Temp\\StockScope-JEV02-760bf7b7532c4a26b949cdfc53745e41\\simulation.db`이며 `--find-new --captured-after 2026-10-29T15:36:39.9323285+09:00` 결과 **새 작업 기록 1건 확인**: 2026-10-29 16:06:14 KST, `source_job_id=f6c2081a94ea41b6b3ea52b688f2c3f2`, `capture_id=89c9c2ed-114d-4eb7-80d6-4d03d640b483`, **DUPLICATE**, `canonical_capture_id=ee8bc385-1939-4626-aecc-20e6bdb32645`, 0 저장 샘플, `new_complete_entry_captures=[]`, TypeSafe 호출 0.
- **해석:** 기존 `ProspectiveCatalog.finalize_capture`는 scanner/version/market/asof/candidate limit/input fingerprint/Selection Policy pin/source snapshot hash를 사용한 execution key 동일하면 새 행을 DUPLICATE로 저장하고 원본 COMPLETE을 참조. 따라서 Scanner 신규 작업과 저장 경로는 확인되었으나 실제 fresh 재분석/새 market evidence/V4 projectable은 입증되지 않음. 같은 파라미터 재실행으로 무한 반복 금지.
- **권장 후속:** 중복 ID를 기존 P3 CLI의 `--capture-id`로 검사하면 `load_frozen_candidates()`가 canonical COMPLETE 샘플을 참조해 Pin/전략/V2/V4 원인을 표시하나, `captured_after`보다 원본 생성시각이 오래되면 정상적으로 exit 3 (FRESH_CAPTURE BLOCKED). 신규 검사 완료로 승격시키면 안 됨. 실제 신규 시장 EOD 입력/승인된 정책·증거가 있을 때 별도 신규 실캡처 E2E 수행. 수치 Horizon 미승인, TypeSafe 실시장 권한 HOLD, LIVE-05 보류, G2-01~04 보존.


## 2026-10-29 LIVE-04R-P3 중복 정본 상세 검사 — 실질적 구조 차단 확인

- Windows 사용자 출력: DUPLICATE 캡처 `89c9c2ed-114d-4eb7-80d6-4d03d640b483`의 기존 canonical `ee8bc385-1939-4626-aecc-20e6bdb32645`에 대해 P3 CLI `evidence/checks/v4` 조회. 엔진 PASS 조건 6개, 정책 Pin PASS(`VERIFIED_PINNED_EXECUTION`), rank/dates/risk PASS, Semantic V2 hash PASS, lineage COMPLETE. 그러나 정책 자체가 `LEGACY_CURRENT_10_FALLBACK`이고 **전략 원본 version/hash 없음**, `LEGACY_DERIVED`만 존재. Horizon `LEGACY_UNSPECIFIED` → **`BLOCKED_HORIZON`**, V4 state hash 없음. 이는 옛 정본의 read-only 진단이므로 신규 실제 1건 V4 승인 불가.
- **소스 검사로 드러난 중요한 교착:** 현 `ScannerPanel.tsx`는 `createScannerJob`에 Horizon을 보내지 않음. `api/backtest.py::create_scanner_job`는 수치 정책 승인 이전의 명시 SHORT/MEDIUM을 `require_horizon_activatable`로 HTTP409 차단. `horizon.py`에는 SHORT/MEDIUM/LONG numeric `EVALUATION_PENDING`. 그러므로 사용자가 후보찾기만 반복해서 V4에서 요구하는 SHORT/MEDIUM이 채워질 수 없음. **이것을 P3 신선한 결과가 안 나와서라고 반복 진단하지 말고, 다음 개발에서 local-only Horizon intent 동결 경로와 별도 numeric execution HOLD를 분리**해야 함.
- `production_selection_policy.py`의 LEGACY fallback 기본 10 전략 원본 version/hash는 설계상 None임. ACTIVE 정책은 `ProductionStrategySelectionRegistry`의 승인된 reference/approval artifact와 정확한 baseline 연결이 있어야만 적용. 임의 fallback 신원 조작이나 과거 snapshot 소급변경 금지.
- **다음 단계:** P4 신규 코드 구현: local-only Horizon intent 명시 UI + Scanner request capture + V4 구조 경로(미승인 수치 정책은 계속 실행 차단), 읽기 전용 ACTIVE policy 상태/근거 점검, 정상 신규 real 캡처로 확인. KRX 출처·파생데이터 제3자 처리권/TypeSafe 약관 및 시각증거 unresolved, 실제 JEV 시장 전송 HOLD, LIVE-05 보류, G2-01~04 보존, G2-05 보류, Draft PR #170 유지.


## 2026-10-29 JEV-LIVE-04R-P4 코드 구현 — Horizon 선택/로컬 모드/동결

- **코드:** `backend/app/api/backtest.py` [`3387768`](https://github.com/SkyBluekor/StockScope/commit/3387768c96703182982d22361a5cd3173bd496e1), `frontend/src/components/ScannerPanel.tsx` [`251b53f`](https://github.com/SkyBluekor/StockScope/commit/251b53f749de61b83b2815058cf934fa917677cf), `frontend/src/services/api.ts`, `scannerUX.css`. Scanner 사용자에게 미지정/SHORT/MEDIUM/LONG 검토기간을 선택하게 하고 **명시된 기간만 `horizon_purpose=LOCAL_REVIEW_ONLY`**와 함께 서버에 전달. 저장된 분석의 기간은 현재 UI 선택과 독립적으로 표시. 일반 기본 Scanner 기존 동작 보존.
- **보호:** API `PRODUCTION_POLICY`에서 SHORT/MEDIUM/LONG `EVALUATION_PENDING`은 여전히 HTTP409; `LOCAL_REVIEW_ONLY`는 숫자 정책 승인·매매 활성화가 아니라 capture 컨텍스트 기록만 허용하고 미지정 로컬 모드는 HTTP409. V4 로컬 검사 가능성과 실종목 TypeSafe 외부 처리권/시간·숫자 Horizon activation은 완전히 별개의 판정. LIVE-04 real-market provider HTTP 금지, LIVE-05 보류.
- **동결:** `ProspectiveCaptureRequest`에 `horizon_purpose`를 기록하고 시작/완료 전체 request binding 보존. `catalog._source_hashes` execution key에는 Horizon/버전/목적 추가되어 동일 원본 시장 결과라도 서로 다른 Local Horizon 캡처가 엉뚱하게 합쳐지지 않음. 과거 COMPLETE 원본·선호 Rank·Risk 수정 없음.
- **전략 Pin:** [`ddce94e`](https://github.com/SkyBluekor/StockScope/commit/ddce94ef455235f46f8b1c0424d8b56d1f9e76cc)에서 Scanner도 Strategy Governance가 사용하는 `STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR` override를 존중, 승인 원본 정책 없으면 LEGACY 10종 fallback 보존. 실제 Windows에 어떤 ACTIVE/ROLLBACK artifact가 있는지는 **미확인**; 기존 `LEGACY_DERIVED` 정본을 실제 원본 버전/hash로 속이지 않음.
- **자동 tests:** [`test_jev_live_04r_p4_local_horizon.py` `8e71cd8`](https://github.com/SkyBluekor/StockScope/commit/8e71cd8b1f652d748abfc0d3b4e4719dc7f07b18)에서 모드별 FastAPI 202/409/422, 로컬·숫자 policy 분리, 작성 합성 DB의 freeze/dedup/drift, Governance와 runtime path 일치 확인. 실제 데이터 Provider 호출 0; Windows 실제 선택/검색 E2E는 별도.
- **Windows 검증 지시:** 기존 `C:\Projects\StockScope`에서 `git pull --ff-only`, `.\.venv\Scripts\python.exe -m pytest -c .\backend\pyproject.toml .\backend\tests\test_jev_live_04r_p4_local_horizon.py -q`, `.\run-dev.ps1`; UI의 '살펴볼 종목 찾기' → '검토 기간' SHORT/MEDIUM 선택 → 기존 버튼 실행. 내부 `horizon_context.intent`, `purpose`, `prospective_capture`의 캡처 ID와 LIVE-04R P3 읽기 전용 도구 결과 확인. 같은 시장 EOD의 cached Scanner가 재사용되면 P4 UI 경로 및 capture pin 검증은 가능하나 새 엔진 재현성/신규 V4 projectable 성공으로 과대해석하지 말 것. `strategy-governance/production-policy` GET만으로 실제 ACTIVE/LEGACY 상태 점검 가능하며 별도 승인 없이 activate POST 사용 금지.
- **완료 단계 구분:** 코드와 자동 CI는 전파 가능하나, **사용자 Windows 브라우저 UAT 미수행**, 신규 real `LOCAL_V4_PROJECTABLE` 미입증, ORIGINAL strategy version/hash 확보 미완료. 계속 LIVE-04R-P4 PARTIAL로 인계, 기존 PR #170 Draft/G2-01~04 유지/G2-05 보류.
