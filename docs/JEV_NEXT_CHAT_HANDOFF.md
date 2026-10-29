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
| **JEV-LIVE-04** | **NEXT — 실종목 유료 호출 BLOCKED, 합성 Mock 단일 후보 UI/job 개발 가능** | 사용자 opt-in, 비동기 검토, 중복·실패·비용 상한은 합성 Mock으로 구현 가능. 실시장 provider HTTP 전송은 공식 원천/계정 권한 및 exact wire 승인 결합 전까지 금지. |
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
