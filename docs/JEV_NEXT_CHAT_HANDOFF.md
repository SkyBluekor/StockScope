# StockScope — 다음 ChatGPT/Codex 채팅 HANDOFF (JEV LIVE 우선)

**기준 시각:** 2026-10-28 (Asia/Seoul). 이 문서는 **다음 채팅의 첫 페이지**다.

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

## 6. 단계별 상태표 (2026-10-28)

| 단계 | 상태 | 다음 행동 |
|---|---|---|
| JEV-LIVE-00 | 완료: 문서 기준점 설정 | 브랜치 HEAD·로컬 환경만 확인 |
| **JEV-LIVE-01** | **코드·HTTP mock 통합 PASS / 유료 합성 live 미실시** | 실제 TypeSafe 1회 실행 승인과 사용자 PC에서 합성 live smoke, 저장 검증이 남음. 2026-10-28 코드 커밋 `90f3d5d`, [CI 4/4 PASS](https://github.com/SkyBluekor/StockScope/actions/runs/40709954313) |
| JEV-LIVE-02 | 미착수 | 실후보 로컬 검토 준비도 화면 |
| JEV-LIVE-03 | 미착수: 실제 시장 외부 전송 HOLD | source 권한/시점/수신자/실 outbound body 검증 |
| JEV-LIVE-04 | 미착수, 실 market 호출은 LIVE-03 권한 결과 필요 | 사용자 선택 후보 1건 end-to-end 실제 review |
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
