# StockScope — JEV 실사용 통합 마스터 실행계획 (CURRENT)

> 갱신 기준: 2026-10-28 (KST) · 소유 저장소: `SkyBluekor/StockScope` · 작업 브랜치: `codex/p0-01-mvp-c1-c2-integration-20261022` · Draft PR #170
>
> **우선순위 선언:** G2-05(현재 후보에 과거 추천 변화 배지 붙이기)는 **보류**. 그 대신 **TypeSafe JEV의 실제 API를 Scanner 이후의 보조 판단자로 연결하고 사용자에게 의미 있는 결과를 보여주는 일**이 다음 개발의 최우선 과제다. G2-01~04는 유지·필요한 버그만 수정한다.
>
> **다음 채팅 진입:** [JEV_NEXT_CHAT_HANDOFF.md](./JEV_NEXT_CHAT_HANDOFF.md) → 본 문서 → 명시된 코드/계약. 새 계획서부터 다시 쓰지 말고 가장 이른 미완료 체크포인트부터 구현한다.

## 0. 목표·완료의 정의

StockScope의 기본 `Scanner → 정량 전략/Risk 판단 → Prospective COMPLETE 캡처`를 유지하면서, **실제 TypeSafe JEV System One API가 이미 확정된 후보 판단에 대해 제2 의견**을 낸다. 사용자 화면에는 **기존 판단 / JEV 의견 / 의견 차이가 난 이유 / 근거와 불확실성 / 검토 시각 / 비용·실패 상태**를 표시한다. 결과는 캡처와 함께 보관하여 나중에 기존 평가 엔진으로 유용성을 측정한다.

- 최초 역할은 **Scanner Decision Reviewer**. `PASS_THROUGH`(기존 판단 유지), `REVIEW_REQUIRED`(추가 검토 필요), `ABSTAIN`(판단 유보). JEV가 후보 발굴·재정렬·전략 선정·Risk Gate 우회·매수/매도·보유계획 수정·성과 확률 예측을 하지 않는다.
- **'실제 JEV가 동작한다'**는 것은 등록된 토큰의 사용량 그래프가 아니라 **실제 모델 요청·응답, 후보와 연결된 유효한 검토 결과, 사용자가 읽을 수 있는 화면, 실패 시 기본 분석 유지**가 입증되는 상태다.
- 처음부터 전원 자동 호출은 하지 않는다. **수동 요청 1후보 → 소수 opt-in 배치 → opt-in Scanner 완료 후 자동 검토** 순서. 승인이 되면 실제 API 사용을 불필요하게 미루지 않는다.
- 외부 전송이 불허·미확인인 실제 시장/파생 데이터는 JEV로 보내지 않는다. **순수 합성 데이터의 실제 유료 JEV 테스트는 그 권한 문제와 별개로 바로 진행 가능**, 실제 종목은 로컬 진단과 명확한 HOLD 사유 표시까지 먼저 진행한다. 실종목 API 호출은 해당 입력의 소스 권리 및 시간·대상 승인이 확인된 경우에만 가능하다.
- **제품 성과 기준**: 단순 PASS/CI가 아니라 완성된 UI에서 실제 호출 결과가 읽히는지, 유용한 반례를 발견하는지, 불필요한 재검토를 얼마나 유발하는지, 비용과 지연이 적절한지를 측정한다.

## 1. 2026-10-28 코드 기준 실태 — 다시 구현하지 말 것

| 영역 | 현재 코드와 확정 사실 | 남은 간극 |
|---|---|---|
| Scanner/G2 | `frontend/src/components/ScannerPanel.tsx`; G2-01~04 후보 수집·저장 관찰·회차 비교·타임라인·두 탭. G2-04 Chromium CI 통과, 기숙사 PC에서 화면 사용 보고 | AI 실호출 연동과 별개의 완성 기능 |
| Provider | `backend/app/jev/typesafe_provider.py`의 `TypeSafeSystemOneProvider`, `provider_from_typesafe_spec`, `load_typesafe_jev_api_key`가 **실제 TypeSafe HTTP 전송** 지원. `JEV_API_KEY` 사용 | 사용자용 실행 서비스가 실제 provider를 구성·주입하지 않음. 새 HTTP 클라이언트를 중복 구현하지 말 것 |
| V4 reviewer | `backend/app/jev/review_service.py`의 `JevManualReviewService`, `typesafe_state_v4.py`, `typesafe_service.py`, `typesafe_catalog.py`에 로컬 의미 라우팅·V4 요청·중복 억제·저장·결과 변환 구현 | 기본 `feature_status=DISABLED`; 동결 프로토콜·provider 주입 없으면 차단, 현재 API는 이를 주입하지 않음. 비동기 작업 경계도 보완 필요 |
| API·UI | `backend/app/api/jev.py`의 `GET /review-feature`는 `available=false`, `FEATURE_NOT_ACTIVATED` 고정. `POST /reviews`는 기본 비활성 서비스 호출. `GET /reviews` 저장 상태 조회. `scannerAiReviewStatus.ts`는 저장 결과의 identity/무결성 체크 기반 표시를 지원 | 실제 사용 가능한 수동 검토 제어·실행 상태/화면 없음 |
| 실 API canary | `tools/data/run_jev_typesafe_canary_v3.py`, `...v4.py`, `jev_s6_micro_canary.py`; 기존 합성 API 호출 이력 및 단가·모델 binding 실험 경로 존재 | 이를 또 처음부터 만들지 말 것. 합성 live 경로를 서비스 통합 smoke와 연결할 것 |
| S7.3~S8 | `scanner_shadow_s7_3.py`, `scanner_lineage_s7_4.py`, `scanner_v4_readiness_s7_5.py`, `scanner_eligibility_s8.py`; 읽기 전용 원본 대조·권한/시점 진단과 테스트 존재 | `LOCAL_PACKET_READY`·`LOCAL_V4_PROJECTABLE` 등은 **전송 허가가 아니다**. 현재 실제 시장 데이터에 대한 외부 전송 `PROVIDER_HOLD` 상태 |
| 원천 권한 | `docs/설계/JEV-ACT2-S7.4_데이터_출처_권한_및_시점_분류_기준.md` | 실 시장 자료의 TypeSafe 전송은 문서상 **NO-GO**, KRX 유래 파생 판단도 자동 면책 안 됨. 공식·계정별 증거와 수신자 처리 조건 별도 필요 |
| 기존 상위 설계 | `docs/설계/StockScope_JEV_통합설계_v2_2026-10-06.md`, V4 설계 동결 문서·`docs/contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V4.json` | 새 계획은 **실행 순서**를 정하는 문서이며 상위 데이터 권한·Risk/정본 계약을 임의 변경하지 않음 |

기존 `backend/app/jev/provider.py`의 OpenAI Responses 경로와 TypeSafe Jev System One은 **서로 다른 구현**이다. 이번 실사용 연결 대상은 **TypeSafe**이며, OpenAI Terra 경로로 바꿔치기하지 않는다. `jev-latest`는 별칭이므로 요청 ID·반환 model ID/revision(제공되면)·프롬프트/계약/프로토콜 hash를 저장하고 변동은 별도 보고한다.

## 2. 실행 순서 — 이 순서를 따라 실제 구현

한 단계가 완료되면 해당 PR/커밋·테스트·실행 화면 증거를 **본 문서 '진행 기록'에 갱신한 뒤** 다음 단계로 간다. 새로운 기획/감사 문서를 연쇄적으로 추가하지 말 것.

### JEV-LIVE-00 — 현 상태 확인·동결 (이번 계획 작업으로 문서 기준 완료)
- [x] 기존 TypeSafe provider, V4 service, UI, API 비활성 경계, S7.4/S8 데이터 권한 진단을 코드와 대조.
- [x] G2-05 보류, JEV 우선순위 확정, 기준 브랜치·문서·다음 채팅 인계 지정.
- [ ] 실제 실행 시작 시 `git status --short`, `git log -1 --oneline`, 활성 브랜치, 로컬 기숙사/학교 PC의 환경 경로만 점검. 운영 DB 실수 접근 방지.
- **완료 조건:** 새로운 설계 재작성 없이 JEV-LIVE-01 코딩으로 즉시 진입.

### JEV-LIVE-01 — 기존 TypeSafe를 '실제로 호출 가능한 실행 경로'에 연결 (가장 먼저 구현)
- [ ] `TypeSafeSystemOneProvider` + 기존 V4 질문/응답 검증 + `JevManualReviewService`의 fake 주입과 **실제 TypeSafe 주입을 동일한 경계**로 연결. 중복 provider, 새 독립 JEV DB, 새 판단 엔진 금지.
- [ ] 개발자 전용 **synthetic-only 실행 경로**를 마련: 실제 TypeSafe 호출 1~소수 회, 명시적 실행 동의, 전송 직전 payload preview(마스킹), 요청·응답 스키마, 비용/토큰/실패 상태를 확인. 코드와 프로토콜에 합성임을 명시; 실 캡처 원본에서 파생된 fixture를 합성이라 재분류하지 않는다.
- [ ] fake/HTTP mock로 200·401·422·429·5xx·timeout·invalid JSON·model identity mismatch·중복 요청·비용 알 수 없음 테스트; live smoke는 사용자의 요청당/기간당 승인 안에서만 실시.
- [ ] 부하 테스트·수십 회짜리 canary를 재실행하지 않는다. **기존 합성 실험은 이미 수행됐다.** 이번 검증은 '사용자용 실행 서비스까지 이어지는지'를 입증해야 한다.
- **완료 조건:** 네트워크가 허용된 합성 입력에서 **TypeSafe 실제 응답 → V4 검증 결과 → 별도 저장 기록**까지 한 경로에서 재현되고 CI는 유료 호출 0회. 실패해도 Scanner 결과가 그대로다.
- **막히면:** 입력/권한 HOLD와 실제 provider 연결 오류를 구분해 보고, 전체 일정은 멈추지 않고 JEV-LIVE-02 로컬 UI를 병행한다.

### JEV-LIVE-02 — 실제 후보에서 JEV 검토 가능 여부를 사용자에게 보이게 (로컬 진단부터)
- [ ] COMPLETE / canonical Scanner 캡처를 고정 입력으로 사용하고 **S7.3 / S7.4 / S7.5 / S8 기존 read-only 검사 결과**를 한 종목별 preflight 응답으로 제공. Snapshot hash, rank/전략·Risk 신원, source 시각, V4 eligibility, 전송 권한을 서로 구분.
- [ ] 현재 후보에 `LOCAL_READY` / `LOCAL_ONLY` / `NEEDS_EVIDENCE` / `SOURCE_RIGHTS_HOLD` / `NOT_ENTRY_CANDIDATE` 등의 **표시용 상태**를 만들되 기존의 확정 enum을 함부로 재명명하지 말고 내부 reason codes로 매핑. 출시 가능하다는 오해를 막는다.
- [ ] 상위 화면에는 'AI가 실제로 검토했는지'와 '검토 미실행 이유'를 그대로 표시. 실질적 입력 부족을 'AI가 합격/불합격 판단함'으로 표시하지 않는다.
- [ ] 학교/기숙사에서 사용한 15개 후보 포함 실제 사용자 데이터는 **로컬 복제본으로만** 진단. 전송·출력·원본 수정 0.
- **완료 조건:** 실제 사용자 후보를 선택하면 JEV 준비/차단/미실행 이유가 특정 코드와 사용자 문장으로 보인다. 기본 Scanner 계속 정상.
- **중요:** 이 단계는 실제 Jev의 **실시장 호출 성공이라고 주장하지 않는다.**

### JEV-LIVE-03 — 실종목 입력의 외부 전송 경계·권한 확인 (작게, 명확하게)
- [ ] 위 S7.4 문서 §9~11을 재사용해 **필요한 실제 외부 전송 필드만** 선정. KRX 원시·파생 지표, 조건 문장, 위험 판정 등 각 필드의 부모 원천, 수신자(TypeSafe), 처리/보관 범위, 시점 근거를 확인.
- [ ] 현재 계정에 적용되는 KRX 상품/이용 조건과 TypeSafe 입력·로그·telemetry/재위탁 처리 조건의 근거를 확보. **공식 자료만으로 불충분하면 공급자 확인이 필요**하며, 사용자가 API 키를 갖고 있다는 사실만으로 허가가 생기지 않는다.
- [ ] `scanner_eligibility_s8.py`의 원칙을 기준으로 최소 outbound `{state,questions,model}`를 구성하고 **실제로 전송되는 bytes의 hash + 승인 주체·범위·시간/프로토콜 + 민감정보 차단**을 결합한다. 단순 hash나 설정 플래그만으로 권한을 인정하지 않는다.
- [ ] 기존 데이터가 `LEGACY_LIMITED` 또는 시간 근거가 빈약하면 검토 목적·연구/forward 구분을 유지. 사후 생성된 답을 과거 거래시점의 '당시 예측'으로 둔갑시키지 않는다.
- **완료 조건:** 특정 소수 입력에 대해 `ALLOW` 또는 `HOLD/DENY + 구체적 사유`가 증거와 함께 일관되게 나온다. `HOLD` 상태도 진단 기능의 정상 산출물이며 전송 허가가 아니다.
- **진행 결정:** `ALLOW`로 증명된 **그 필드/목적/모델/계정 조건에 한해서만** JEV-LIVE-04 실종목 API 호출 진행. 승인 불가면 **불가능한 이유·필요한 대체 수단**을 명시하고 JEV-LIVE-04의 실제 시장 API 호출만 중지; 합성 live와 로컬 후보 진단·UI까지 되돌리지 않는다. KRX만 제거한 가짜 익명화·무허가 파생 데이터 전송을 금지.

### JEV-LIVE-04 — 한 종목 수동 실제 검토 E2E (첫 '실사용' 목표)
- [ ] `POST /api/simulation/jev/reviews`(또는 계약이 필요한 경우 명시적 신규 endpoint)에 **서버사이드 opt-in 활성화** + 동결 프로토콜 + 실제 provider 주입. 기존 `review-feature` 고정 false는 권한과 설정이 충족되었을 때만 ACTIVE를 반환.
- [ ] UI에서 'JEV 추가 검토'를 **사용자가 명시적으로 선택한 후보 1건**에 제공. 호출 버튼은 LIVE 가능, LOCAL_ONLY, HOLD, 실행 중/완료/실패를 정확히 구분한다.
- [ ] 요청은 baseline Scanner 완료 후 별도 worker/job으로 실행. 메인 후보 UI/Scanner 완료 응답을 모델 네트워크에 종속시키지 않는다. capture/sample/snapshot/protocol/model/request identity로 **재요청 중복 과금 방지**, 요청 시간·완료 시간·에러·유효모델 증거 및 비용을 저장.
- [ ] 서버 재시작 후 `PENDING`을 자동 재청구하지 않음. 결과 오류 또는 지연 시 baseline만 유지, `LATE`는 사전 예측 성과로 집계 금지.
- [ ] 한 건 성공·대기·오류·재시작·고의 응답 지연을 모두 확인. 원본 Scanner rank/action/Risk/selection policy 불변.
- **완료 조건:** **사용자 UI에서 실제 Scanner 1후보 → 적법한 JEV API 실제 호출 → 검증된 PASS_THROUGH/REVIEW_REQUIRED/ABSTAIN 저장 → 화면 재조회**의 작업 흐름을 직접 재현.

### JEV-LIVE-05 — 소수 후보 배치/opt-in 자동 검토
- [ ] 별도 feature flag 기본 OFF. 사용자가 활성화한 경우에만 **COMPLETE 캡처 이후** ENTRY_CANDIDATE만 review job 큐에 제출. 참조 후보나 차단 후보는 미호출 사유 기록.
- [ ] 소수 캡처/후보 한도, 모델·protocol pin, idempotency, rate limit, timeout, 중복 클릭·브라우저 재접속·새로고침·실패 복구, kill switch / rollback 구현.
- [ ] 기존 `GET /api/simulation/jev/reviews`, 모니터링 및 `ScannerPanel`의 AI 검토 상태를 재사용해 통합 카드: 기본 판단, JEV 추가 검토 이유, 근거와 반대 근거, 적용되지 않는 영역, 검토 시각/대상. 유료 API는 탭 진입·조회·페이지 열기만으로 절대 재실행하지 않는다.
- [ ] 비용은 모델이 싸다는 장점을 살려 **실험을 거의 무의미하게 만드는 극소 예산 대신** 초기 단일 통합 테스트와 소수 opt-in 배치에 맞는 상한을 사용자와 정한다. 예시 제안: 첫 live smoke 1~3회, 배치 10~30후보, 총 노출 예산 $1의 *제안값* (확정 요금/실 청구 약속 아님). 승인된 한도·남은 잔액·과금 미확정·토큰 수를 별개 기록; 예상 비용이 낮아도 제로 비용으로 주장하지 않는다. API 가격/모델 정보는 실행 시 실제 계정/공식 사양으로 확인한다.
- **완료 조건:** 사용자 opt-in 배치의 실제 검토 결과가 후보별로 읽히고, 실패해도 기존 정량분석은 동일하며 no-opt-in 회귀·Windows 실제 브라우저 실사용 통과.

### JEV-LIVE-06 — 결과 유효성·효과 측정과 보조 기능 유지/확대 결정
- [ ] 'JEV가 좋은 문장을 썼다'가 아닌 **baseline / JEV 동의·이견 / 모델 오류·유보 / 실제 검토 부담 / 사용자 유용성 / per-call 비용·지연**을 캡처별로 수집.
- [ ] Prospectve 관찰(5/10/20일 EOD)과 실제 체결·가상 실행을 혼동하지 않는다. 과거 자료로 지금 JEV에 물어본 결과는 **retrospective 연구**이며 그날 사전 JEV 예측으로 취급하지 않는다.
- [ ] forward 검토에서 사전 시각과 후속 outcome이 증명된 cohort만 비교. 기존 평가/Execution 정책을 재사용. skip 가설은 오프라인에만 적용; JEV 의견으로 운영 후보를 실제로 제외/재정렬하지 않는다.
- [ ] 도움이 되는 조건, 불필요한 경고와 손실 기회, ABSTAIN, 잘못된 근거, 비용을 보고 제한적 채택·수정·중단을 결정. 확대/활성화 승인 전 실제 거래와 연결하지 않는다.
- **완료 조건:** 투입 대비 가치를 판단할 최소 비교 리포트 + 사용자용 참고 의견 제공 여부 결정; 이미 구현된 G2 기록 UI를 필요할 때만 연결.

## 3. 모든 단계의 공통 불변식

1. **실제 모델 통합이 목표다.** 'S7 또 감사', 'canary 또 수십 번', 새 G2 장식, 새 구상만 반복하는 우회 작업 금지. 코드부터 구현하고 보여줄 것.
2. 기본 Scanner 후보, 순위, 전략/Risk, Prospective COMPLETE 스냅샷/hash, Holdings/Watch, 주문 관련 상태 **수정 금지**. JEV는 add-on.
3. 실제 외부 JEV에 전송될 payload를 검사하는 곳과 **실제 HTTP body**가 일치해야 함. 단순 요약/가짜 테스트 payload와 실제 wire를 바꾸지 않는다.
4. `.env`, `JEV_API_KEY`, KRX·DART·NAVER·KIS 계정 정보, 실제 시장 원문·민감 데이터·모델 원문은 Git/PR/로그에 노출 금지. fake 데이터는 명확하게 합성.
5. API 실패·모델 응답 불일치·schema/identity 검증 실패·예산 한도·원천 권한 HOLD·늦은 의견은 모두 **baseline 정상 사용 + JEV 사유 표시**.
6. 원칙적으로 기존 실험 프로토콜/contract hash를 소급 수정하지 않는다. 새 실사용 프로토콜은 별도 version과 명시적 연결. S7.4 권한 gate를 임의로 통과 처리하지 않는다.
7. 같은 일을 학교/기숙사 각 PC에서 복제하여 반복하지 않는다. GitHub 브랜치는 코드의 기준, 각 PC의 runtime DB와 API 키는 별개. **시연은 기존 데이터 백업/격리 복제본에서 먼저** 수행; 정상 운영 이력으로 승격하려면 사용자 승인과 명확한 경로가 필요.
8. **CI 통과 ≠ 실사용 완료**. 실제 사용자는 Windows에서 JEV 검토 버튼 및 결과를 직접 확인해야 한다. CI에서는 mock/fake만 사용하며 외부 요금 0.
9. 판단 결과를 모델 성능 확률·미래 수익률·투자 보증으로 표시하지 않는다.

## 4. Codex/다음 채팅 실행 규칙

- 첫 질문은 '계획 다시 세울까요?'가 아니다. 아래 **상태표에서 가장 이른 미완료 단계의 소스를 확인하고 구현**한다.
- 한 단계의 범위를 작게 고정하고 실제 동작·관련 테스트·최종 커밋·CI 링크·로컬 확인 여부를 보고한다. 성공했다면 다음 미완료 단계로 이동한다.
- 예상치 못한 오래된 실험 파일이나 큰 미완성 기능을 발견하면 새 프레임워크를 만들지 말고 **기존 구현을 먼저 이어 붙인다**.
- 비용이 저렴하다고 수동으로 불필요한 70회짜리 실험을 반복하지 않는다. 또한 비용이 저렴한데도 $0.01 등 임의로 극도로 작은 상한으로 실사용을 계속 지연하지 않는다. **목표·요청 횟수·안전한 상한을 분리**한다.
- 권한/실제 유료 호출/운영 기능 활성화처럼 사용자 결정이 필요한 경계는 정확히 한 번 승인받는다. 그 전 개발·합성 검증·UI는 멈추지 않는다.
- 완료된 G2-01~04/Windows preview/15개 후보 재수집/별도 문서 반복 작성은 JEV 실연동의 선행조건이 아니다.
- 작업 후 이 문서의 `## 5. 진행 기록`과 [HANDOFF](./JEV_NEXT_CHAT_HANDOFF.md) 기준 SHA/상태를 갱신. 기존 사실과 확인 안 된 사실을 구분.

## 5. 진행 기록 (후속 작업에서 반드시 갱신)

| 단계 | 상태 | GitHub 커밋/PR | 확인 증거 또는 차단 사유 |
|---|---|---|---|
| LIVE-00 현 상태 기준 정리 | **DONE (docs only)** | 이 계획 문서 커밋 참조 | TypeSafe transport 존재·user review feature OFF·S7.4 시장 전송 HOLD 확인 |
| LIVE-01 실제 provider 합성 E2E 연결 | **CODE + HTTP MOCK E2E VERIFIED / PAID LIVE PENDING (not DONE)** | [`90f3d5d`](https://github.com/SkyBluekor/StockScope/commit/90f3d5d5e2b1ae010cbeca8bf8da4d786e2a03b0) · [CI 4/4 PASS](https://github.com/SkyBluekor/StockScope/actions/runs/40709954313) · [Draft PR #170](https://github.com/SkyBluekor/StockScope/pull/170) | 기존 TypeSafeSystemOneProvider→V4 JevManualReviewService→기존 catalog 저장, 합성 fixture/HTTP MockTransport 200·401·422·429·500·timeout·invalid JSON·model mismatch·usage invalid·duplicate·baseline 불변 확인. Python 3.11/3.14 각 2,589 passed / 2 skipped; Frontend / Windows Fresh Clone PASS. **실제 유료 요청 0, Windows 사용자 수동 호출 미검증, 실모델 응답 미확인**. |
| LIVE-02 실종목 로컬 준비도 화면 | **TODO** | — | 외부 전송 0, 근거별 차단 상태 |
| LIVE-03 실제 입력 권한·시점 증거 | **TODO / 현재 시장 전송 HOLD** | — | 허용된 입력만 검증; 불가 시 해당 outbound만 보류 |
| LIVE-04 선택 후보 1건 수동 실검토 | **TODO / 실제 시장 전송은 LIVE-03 결과에 따름** | — | saved verified response + UI |
| LIVE-05 opt-in 배치·자동 검토 | **TODO** | — | baseline 불변, 예산 및 롤백 |
| LIVE-06 forward 효과 관찰/평가 | **TODO** | — | 타당한 분모·시점·사용자 가치 |

**2026-10-28 기준 검증된 최신 G2-04 HEAD:** `eb83d5aa16c903b487b4e8d83d2538b3fd1368b2` (이후 문서 커밋으로 브랜치 HEAD는 변동). 이는 JEV live 구현 완료 커밋이 아니다.

## 6. 주요 실제 소스 바로가기

- [TypeSafe transport](../backend/app/jev/typesafe_provider.py)
- [User review service](../backend/app/jev/review_service.py) / [API](../backend/app/api/jev.py)
- [V4 review/semantic route](../backend/app/jev/typesafe_service.py) / [V4 frozen contract](./contracts/JEV_TYPESAFE_CANARY_PROTOCOL_V4.json)
- [S7.4 lineage](../backend/app/jev/scanner_lineage_s7_4.py) / [S8 source rights/time](../backend/app/jev/scanner_eligibility_s8.py)
- [Scanner UI](../frontend/src/components/ScannerPanel.tsx) / [AI status](../frontend/src/components/scannerAiReviewStatus.ts)
- [S7.4 source-rights authority](./설계/JEV-ACT2-S7.4_데이터_출처_권한_및_시점_분류_기준.md)
- [Original JEV v2 design](./설계/StockScope_JEV_통합설계_v2_2026-10-06.md)
- [Synthetic micro canary](../tools/data/jev_s6_micro_canary.py)

### JEV-LIVE-01 implementation evidence (2026-10-28, not final acceptance)

- Added [authored synthetic-only fixture and isolated service harness](../backend/app/jev/synthetic_live_01.py), [developer CLI](../tools/data/jev_live_01_synthetic_smoke.py), and [service/HTTP mock tests](../backend/tests/test_jev_live_01_synthetic_service.py). No G2-01~04, Scanner, trading, or default user JEV API behavior was changed. G2-05 remains paused.
- One call path: isolated new SQLite -> synthetic Prospective COMPLETE capture -> V4 residual semantic sample -> frozen V4 protocol -> `provider_from_typesafe_spec` / `TypeSafeSystemOneProvider` -> `JevManualReviewService.request_review` -> existing TypeSafe catalog. Provider injection here is **developer-only** and the user HTTP review endpoint remains disabled. The preflight prints a masked, canonical payload preview and body digest; it is **not** a verified HTTP byte-for-byte outbound receipt (LIVE-03 remains separate).
- Windows offline check after pulling branch: ` .\\.venv\\Scripts\\python.exe -m tools.data.jev_live_01_synthetic_smoke --mode preflight ` (no credential access or network), then ` .\\.venv\\Scripts\\python.exe -m tools.data.jev_live_01_synthetic_smoke --mode mock ` (MockTransport only, writes one new isolated temp DB). Existing operational DBs are never loaded. Do not copy the synthetic review into operational performance history.
- Validated CI (code SHA `90f3d5d`): [run #40709954313](https://github.com/SkyBluekor/StockScope/actions/runs/40709954313) **4/4 jobs PASS**. Backend Python 3.11 and 3.14: **2,589 passed, 2 skipped** each; Frontend and Windows Fresh Clone jobs PASS. Tests make **zero real billed TypeSafe calls**. Existing user Windows UI manual test **NOT RUN** (future LIVE-04); Windows Fresh Clone CI is not a substitute.
- Outstanding LIVE-01 acceptance requirement: actual TypeSafe response on this **strictly authored synthetic sample**, through the same V4 service and persisted review row. It needs explicit separate approval for one billable request, API key in the user's local environment, verified expected returned model identity and provider-policy/retention/model catalog metadata. Do not mark LIVE-01 DONE until that receipt is inspected. S7.4 real market data outbound remains **HOLD/NO-GO**; don't use this synthetic-only harness to re-label market-derived inputs.

