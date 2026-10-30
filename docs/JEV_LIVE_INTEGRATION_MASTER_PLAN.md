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
| LIVE-01 실제 provider 합성 E2E 연결 | **DONE — synthetic-only real TypeSafe V4 E2E (2026-10-29)** | [`90f3d5d`](https://github.com/SkyBluekor/StockScope/commit/90f3d5d5e2b1ae010cbeca8bf8da4d786e2a03b0) · [CI 4/4 PASS](https://github.com/SkyBluekor/StockScope/actions/runs/40713831348) · [Draft PR #170](https://github.com/SkyBluekor/StockScope/pull/170) | **사용자 Windows `C:\\Projects\\StockScope` 실제 유료 합성 호출 1회 PASS** (HEAD `10af121`): `jev-1.14.0` 요청/반환 일치 `MATCHED`, `PASS_THROUGH` / `NO_ADDITIONAL_RELATION_CONFLICT`, 저장 후 조회 `VALID`, review ID `ff4f5134-a65f-485c-87ca-c163c8a9dad0`, 사용량 1,073 input / 23 output, `cost_unknown=true`, `failure_code=null`, CLI exit 0. 데이터 `JEV-LIVE-01-AUTHORED-SYNTHETIC`만 전송; 실제 시장 정보 아님. **사용자용 실종목 UI·outbound 권한은 아직 미검증 및 HOLD**. |
| LIVE-02 실종목 로컬 준비도 화면 | **DONE — 2026-10-29 실제 Windows Scanner UI 확인** | [최종 0-based 수정 `52d6804`](https://github.com/SkyBluekor/StockScope/commit/52d680480508b9aea857dc71436e5227fee53d55) · [CI 4/4 PASS #40797590774](https://github.com/SkyBluekor/StockScope/actions/runs/40797590774) · [문서 CI 4/4 PASS #40797912620](https://github.com/SkyBluekor/StockScope/actions/runs/40797912620) · [PR #170](https://github.com/SkyBluekor/StockScope/pull/170) | 사용자 Windows `C:\Projects\StockScope`의 2026-10-28 저장 Scanner 1위 셀트리온(KOSPI 068270) → AI 검토 탭에 **해당 종목 준비도·미실행 사유 표시 성공**, 기존 ticker mismatch 오류 해소. 로컬 상태 `NEEDS_EVIDENCE`, V4 `BLOCKED_HORIZON`, 출처 `COMPLETE`, Rank/Risk/Policy `PASS`, Strategy `LEGACY_DERIVED`, source time `UNKNOWN`, rights `UNVERIFIED`, 외부 전송 금지, 호출 0. Windows pytest 3/3 PASS. 추가 후보 전환·서버측 실제 전송 허가 검증은 수행하지 않음. 이 단계는 모델 추론/실시장 외부전송 성공을 의미하지 않음. |
| LIVE-03 실제 입력 권한·시점 증거 | **LOCAL AUDIT DONE — 사용자 Windows UI 확인, 판단 HOLD/NO-GO (외부 전송 허가 아님)** | [`9ad76ad`](https://github.com/SkyBluekor/StockScope/commit/9ad76adbb4ed7270bead838e18898f5667eb6daa) · [코드 CI 4/4 #40805284863](https://github.com/SkyBluekor/StockScope/actions/runs/40805284863) · [문서 CI 4/4 #40805668772](https://github.com/SkyBluekor/StockScope/actions/runs/40805668772) · [PR #170](https://github.com/SkyBluekor/StockScope/pull/170) | 사용자 실제 Windows 브라우저 `http://127.0.0.1:5173` 저장 Scanner 2026-10-28 셀트리온(KOSPI 068270) AI 검토 탭에서 **LIVE-03 카드 렌더·선택 후보 연결·외부 전송 보류 확인**. `NOT_AUTHORIZED`, 시각 진위 `UNVERIFIED`, rights resolver `NOT_CONFIGURED`, 부족한 근거 사유 코드, 모델 요청 0. `BLOCKED_HORIZON`/`LEGACY_DERIVED` 때문에 해당 후보의 V4 wire 본문 미생성: 정상 차단. HTTPX wire hash/변조 비교는 합성 테스트로만 확인. 사용자 Windows pytest 4/4 PASS, GitHub CI 4/4 PASS. **실 KRX 원시/파생 데이터 TypeSafe 전송 권한 미입증**. LIVE-04 real-market HTTP 요청은 HOLD; LIVE-03은 로컬 검사·차단 판정만 완료. |
| LIVE-04 선택 후보 1건 수동 실검토 | **SYNTHETIC MOCK UI USER WINDOWS UAT PASS / ACTUAL REAL-MARKET PROVIDER BLOCKED (FULL LIVE-04 NOT DONE)** | [`286faf1`](https://github.com/SkyBluekor/StockScope/commit/286faf1134abb20c276b2e20d88ad72e9d714fce) · [CI #40808788891](https://github.com/SkyBluekor/StockScope/actions/runs/40808788891) · [CI #40809193328](https://github.com/SkyBluekor/StockScope/actions/runs/40809193328) (both 4/4 PASS) · [PR #170](https://github.com/SkyBluekor/StockScope/pull/170) | **2026-10-29 사용자 Windows 실제 브라우저 스크린샷:** Scanner 실제 선택 후보 셀트리온(KOSPI 068270)의 AI 검토 탭에서 별도로 분리된 **합성 검토 체험** 결과 표시. 가상 `999991`: `합성 결과 검증·저장 완료`, `추가 확인 필요` (`REVIEW_REQUIRED`), `jev-mock-returned`, `MATCHED`, 저장 review ID 노출, 합성 Mock 호출 1회, 실제 API 사용 0, 비용 `$0.0000 (Mock)`. 개발용 ASGI opt-in→기존 V4 Reviewer/Catalog 저장→조회 UI **시각적으로 확인됨**. 그러나 사용자가 **새로고침 후 저장 유지** 및 중복 재클릭을 직접 시험했다는 증거는 없음 (CI 단위/ASGI 테스트는 통과). 실제 셀트리온은 `AI 검토 미제공`/실시장 HOLD; real-market TypeSafe HTTP 0, 전체 LIVE-04 실종목 E2E BLOCKED. |
| LIVE-04R-P2 신규 Scanner 입력 계약/동결 연결 | **PARTIAL: CODE + CI 4/4 PASS, USER WINDOWS NEW CAPTURE PENDING** | [`c3198ac`](https://github.com/SkyBluekor/StockScope/commit/c3198ac4ee36448ec6e980a5520ecea09825f947) · [CI #40826721313](https://github.com/SkyBluekor/StockScope/actions/runs/40826721313) | 신규 `ProspectiveCatalog.begin_capture/finalize_capture`는 같은 source_job의 원본 요청 전체(종목시장·날짜·상한·Horizon·policy id/hash) 불일치를 감지해 다른 정책으로 동결되는 일을 차단. 보조 begin 오류는 Scanner 본 분석에 전파하지 않고 실패 판정만 반환. 작성 합성 ACTIVE Pin + engine PASS audit가 V2 동결·재조회되는 로컬 E2E 및 누락/조작 시 불완전 판정 테스트 PASS. **실제 신규 시장 캡처의 ACTIVE Pin/원본 audit/LOCAL_V4_PROJECTABLE 성공은 아직 미확인, 수치 Horizon 정책 EVALUATION_PENDING, 실시장 TypeSafe 권한 HOLD.** |
| LIVE-04R-P3 신규 실제 COMPLETE 캡처 1건 진단 | **READ-ONLY PROBE CODE + CI 4/4 PASS / USER WINDOWS NEW REAL SCAN PENDING** | [`5f1dbc9`](https://github.com/SkyBluekor/StockScope/commit/5f1dbc9864cb9a5f421de562b208826b94da31c4) · [CI #40829679177 4/4 PASS](https://github.com/SkyBluekor/StockScope/actions/runs/40829679177) | `tools/data/jev_live_04r_p3_one_capture.py`: `--find-new --captured-after`로 지정한 실행 시각 이후 COMPLETE+ENTRY 캡처 ID만 로컬 검색, `--capture-id`와 `--sample-index`로 실제 새 후보 1건 지정해 read-only snapshot/integrity/Pin/엔진 PASS/V2/기간/V4 최초 차단 지점 보고. UTC 오프셋 없는 실행 시각 거부, 이전 캡처는 비정상 종료 코드, DB 변경 0/외부 TypeSafe 호출 0. 테스트는 **작성 합성 SQLite**에서만 실행. **실제 신규 KRX Scanner 캡처 1건의 Windows 실사용 검증·V4 준비도 판정은 아직 미수행**. 수치 Horizon `EVALUATION_PENDING`, 실데이터 전송 권한 HOLD, LIVE-05 보류. |
| LIVE-04R-P4 로컬 Horizon 선택·정본 동결·정책 경로 통일 | **CODE + CI 4/4 PASS / USER WINDOWS UAT PENDING** | [`3387768`](https://github.com/SkyBluekor/StockScope/commit/3387768c96703182982d22361a5cd3173bd496e1) · [`251b53f`](https://github.com/SkyBluekor/StockScope/commit/251b53f749de61b83b2815058cf934fa917677cf) · [`ddce94e`](https://github.com/SkyBluekor/StockScope/commit/ddce94ef455235f46f8b1c0424d8b56d1f9e76cc) | Scanner에 미지정/SHORT/MEDIUM/LONG 선택 UI 및 `LOCAL_REVIEW_ONLY` 요청, 기본 `PRODUCTION_POLICY` 실행 계약 유지. HTTP409 숫자 정책 차단은 일반 목적에만 적용; 로컬 목적은 Horizon 기록을 허용하나 실행 허가 아님. Prospective 요청 JSON/Source execution digest에 Horizon 의도·버전·목적 동결, 다른 기간과 의미가 다른 실행의 잘못된 중복 합치기 방지. 전략 정책 경로를 Governance 런타임 설정과 동일하게 해 선택 Pin 조회; LEGACY는 진실대로 표시하고 기존 원본 신원 미생성. 실제 시장 TypeSafe 전송 HOLD. CI 및 Windows 실사용 화면 검증 별개. |
| LIVE-04R-P4-FINAL 실제 저장 SHORT 정본·V4 로컬 입력 4게이트 진단 | **LOCAL CAPTURE UAT PASS — SKIPPED_LOCAL / REAL PROVIDER HOLD** | [`836067d`](https://github.com/SkyBluekor/StockScope/commit/836067dcd2a87ab2340a3a0e23b9d0e0a2cb7012) · [`da14b4a`](https://github.com/SkyBluekor/StockScope/commit/da14b4a7f6a9137b1a41275449e97575548f6b49) · [Actions #40978076734](https://github.com/SkyBluekor/StockScope/actions/runs/40978076734) | 신규 `tools/data/jev_live_04r_p4_final.py`: `--find-short`는 기존 COMPLETE/DUPLICATE SHORT 캡처 메타데이터만 읽어 **ID 자동선정 금지**; `--capture-id ID`는 정본 SQLite 읽기 전용 로더의 snapshot hash, V2, baseline integrity, S7.5 실제 V4 로컬 상태를 재사용. `local_v4`, `strategy_identity`, `horizon_execution`, `provider_authorization` 별도 반환. `--policy-status` 읽기 전용 ACTIVE/ROLLBACK/LEGACY 판정. 작성 합성 캡처 및 mocked V4 격리 검증과 CI 모두 PASS. 사용자 Windows에서 실제 SHORT 정본 `a1e9c341-7542-4511-8740-e07f4ee250ff` 진입 후보 **1건** 검사: `SKIPPED_LOCAL`/`LOCAL_MATCH`, V2 및 rank/engine/policy/dates/risk PASS, `LEGACY_DERIVED` 유지. P4 로컬 의미 라우팅 인수 통과, **V4 state hash 생성·실제 JEV provider 호출은 수행되지 않음**. TypeSafe real outbound HOLD, 수치 Horizon 미승인, 과거 COMPLETE 불변. |
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

- **Additional Windows CLI proof (code + CI workflow SHA `6d6c35a`):** [GitHub Actions #40710701393](https://github.com/SkyBluekor/StockScope/actions/runs/40710701393) **4/4 PASS** (Python 3.11/3.14, Frontend, Windows Fresh Clone). The newly added Windows job directly ran `python -m tools.data.jev_live_01_synthetic_smoke --mode preflight` and `--mode mock` on an isolated SQLite store. Windows job log verified `result.status=REVIEW_REQUIRED`, `stored_status=VALID`, `stored_disposition=REVIEW_REQUIRED`, `model_identity_status=MATCHED`, `usage.input_tokens=120`, `usage.output_tokens=10`, `cost_unknown=true`, `billable_provider_requests=0`. This is HTTP mock **NOT** real provider E2E. No user Windows manual validation; paid TypeSafe response remains the sole LIVE-01 provider acceptance blocker.


### 2026-10-29 LIVE-01 추가 보완 (실모델 완료 판정 아님)

- [`01f27ba`](https://github.com/SkyBluekor/StockScope/commit/01f27badf2c626830e23db3d24df01d37ef26092): developer-only 유료 합성 CLI에서 `MOCK_ONLY`, `MOCK_OR_PREFLIGHT_ONLY`, `UNVERIFIED`, `UNKNOWN`, `TBD`, `NONE` 또는 빈 provider 증빙값을 네트워크 실행 전에 거부하도록 변경.
- [`77bdefd`](https://github.com/SkyBluekor/StockScope/commit/77bdefd268600b16e374f04d64266640a80426b9): 해당 사전 차단 회귀 테스트 추가. **이 변경의 CI는 확인 대기**(기존 4/4 PASS는 이전 커밋의 증거이며 새 커밋 검증으로 재사용하지 않음).
- 실제 유료 TypeSafe 요청: **0회 (이번 작업)**. 사용자의 로컬 API 키 및 별도의 1회 유료 실행 승인 부재. LIVE-01은 **NOT DONE**, LIVE-02는 아직 진행하지 않음. G2-01~04 유지, G2-05 보류, 실시장 외부 전송 HOLD 유지.

- **2026-10-29 CI 확인:** [GitHub Actions #40713831348](https://github.com/SkyBluekor/StockScope/actions/runs/40713831348) **4/4 SUCCESS** (Backend Python 3.11/3.14, Frontend Node 22, Windows Fresh Clone). Windows synthetic preflight 및 HTTP Mock V4 integration 단계 성공. 이전 #40713750927은 **CANCELLED**이며 실패 테스트의 근거가 아님. 실제 유료 TypeSafe 요청·사용자 Windows 확인 **미실시**, LIVE-01 **NOT DONE**, 시장 원천 외부 전송 **HOLD**.


### 2026-10-29 사용자 Windows CLI 사전 검증 (이후 실제 live 성공, 아래 최신 기록 참고)

- 사용자 PC `C:\Projects\StockScope`에서 기존 개발 브랜치 `codex/p0-01-mvp-c1-c2-integration-20261022` 및 HEAD `8b50afd` 확인, `tools/data/jev_live_01_synthetic_smoke.py` 존재 확인.
- `--mode preflight` 성공: `synthetic_only=true`, `market_data_outbound_allowed=false`, `wire_bytes=2906`, `max_calls=1`, `billable_provider_requests=0`.
- `--mode mock` 성공: `result.status=REVIEW_REQUIRED`, `stored_status=VALID`, `stored_disposition=REVIEW_REQUIRED`, `model_identity_status=MATCHED`, `failure_code=null`, `usage=120/10`, `cost_unknown=true`, `billable_provider_requests=0`. 사용자 실제 Windows 실행 결과 기반이지만 HTTP mock이며 **실제 TypeSafe 응답이 아니다**.
- **사용자가 합성 유료 호출 1회 승인함**. 그러나 사용자 shell의 `JEV_API_KEY` 환경변수는 NOT SET으로 확인되었고 프로젝트 루트 `.env` 로딩 성공 여부는 아직 미확인. 실제 API 호출/DB 재조회는 미실시.
- TypeSafe 공식 공개 문서 조회(2026-10-29): `jev-1.14.0` 최신 안정 버전, `jev-latest` 별칭은 이를 가리킴. 합성 live 시 버전 pin, authenticated `GET /v1/models`의 결과/hash와 공급자 정책 증빙을 고정해서 실행 필요. 실 시장 외부 전송 HOLD, Scanner API default OFF.
- 다음 조건: 로컬에서 API 키 사용 가능 확인 → 모델 목록 조회 및 증빙 결합 → **승인된 합성 단 1회** 실행 → 기존 V4 catalog에 `VALID` 저장·모델 신원/usage 검증. 실패 시 자동 재시도하지 않음.


### 2026-10-29 LIVE-01 최종 인수 증거 — 사용자 실제 TypeSafe 호출

- **DONE 범위: 작성된 순수 합성 fixture의 실제 TypeSafe System One → 기존 V4 `JevManualReviewService` → 기존 `TypeSafeJevCatalog` 검증·저장·재조회.** 사용자 Windows 경로 `C:\\Projects\\StockScope`; 확인된 HEAD `10af121`. `GET /v1/models` 계정 모델 목록 조회 후 `--mode live --model jev-1.14.0 --expected-returned-model jev-1.14.0` 1회 실행, 종료 코드 0.
- 실측: `fixture=JEV-LIVE-01-AUTHORED-SYNTHETIC`, `market_data_outbound_allowed=false`, `wire_bytes=2906`, `wire_sha256=4057b796c308389d5a92f44b328dc6d56986acffd0a36d22f9158e0bb9932570`, `snapshot_hash=0149b561a8bf406bae227492486268394dba4df136df88fd31ee0b611febb3a3`, `protocol_hash=f566633cd9581a10bf5c9c0b86841cb54afdbacd66222ec79b5cfd88afe1ebd5`. 출처는 사용자가 제시한 CLI 출력이며 공급자 HTTP 원문을 보유한 것은 아님.
- 검토: `capture_id=d0812012-fa48-426a-a6fc-4dedbf2dae3b`, `review_id=ff4f5134-a65f-485c-87ca-c163c8a9dad0`, `result.status=PASS_THROUGH`, `reason_codes=[NO_ADDITIONAL_RELATION_CONFLICT]`, `stored_status=VALID`, `stored_disposition=PASS_THROUGH`, `model_returned=jev-1.14.0`, `model_identity_status=MATCHED`, `usage=1073 input / 23 output`, `cost_usd=null`, `cost_unknown=true`, `failure_code=null`, `billable_provider_requests=1`.
- API 호출을 통한 **합성 실모델 연동은 검증됨**. Mock의 `REVIEW_REQUIRED`와 실제 `PASS_THROUGH`는 서로 다른 응답으로, 실제 응답을 보존한 결과다. 비용의 실제 청구액은 미확인. 별도 서버 사용량 영수증/로그 검증 없음.
- 구현 코드·CLI·Windows Mock CI는 이전 커밋에서 통과: [CI #40713831348](https://github.com/SkyBluekor/StockScope/actions/runs/40713831348) 4/4 PASS. **본 문서 갱신 SHA의 CI는 별도 확인**.
- **다음 가장 이른 단계 LIVE-02**: 실제 Scanner 캡처를 로컬 READ-ONLY로 분석해 후보별 준비/차단 이유를 API·UI에 표시. LIVE-03 실제 시장 외부 전송 증빙 전까지 실종목 TypeSafe 호출은 NO-GO. 사용자 브라우저 실제 후보 UI 검증은 아직 수행하지 않았고 LIVE-02/04 인수 범위다. G2-01~04 유지, G2-05 보류.


### 2026-10-29 LIVE-02 실제 코드 진행 및 인수 대기

- **기능 변경:** [백엔드 read-only 후보별 진단 API](https://github.com/SkyBluekor/StockScope/commit/3f0f4f2e6454a26f9529419a468b3c7481d32cdc), [API TypeScript client](https://github.com/SkyBluekor/StockScope/commit/4533873817283620b9d3de6087febf8db1b2aa6b), [Scanner AI 탭 후보별 준비 상태/NO_GO 사유](https://github.com/SkyBluekor/StockScope/commit/cdbeeb606eee08df28306e3ed81d1839b320de28), [선택 후보 인덱스 연결](https://github.com/SkyBluekor/StockScope/commit/48c9a4d001bfff49ee1017173691fa715adc4f38), [rank/strategy/policy/Risk 검사 확장](https://github.com/SkyBluekor/StockScope/commit/af00b1a97cdce0b791455dbecd9a2437e03b68a8), [Frontend 정합성 타입/표시](https://github.com/SkyBluekor/StockScope/commit/17212739a7d317a0344a6b6a17e9ecd7662b53e4).
- **검증:** [격리 합성 캡처 HTTP GET 테스트](https://github.com/SkyBluekor/StockScope/commit/d41e79eb1937784cb405cee2778f59ff451dc2f9) (시작 수명주기의 운영 write를 거치지 않음, snapshot 해시 및 원본 SQLite 바이트 불변, 기본 review-feature OFF, 없는 캡처/샘플 fail-closed). [동일 구현 HEAD CI #40795790479](https://github.com/SkyBluekor/StockScope/actions/runs/40795790479) **4/4 SUCCESS**: Python 3.11/3.14 backend, Node22 frontend/build/Chromium, Windows fresh clone. CI는 **사용자 실제 Windows 브라우저 검증을 대체하지 않는다**.
- **결과 API:** `GET /api/simulation/jev/local-readiness?capture_id=<UUID>&sample_index=<1-based>` (읽기만), `status` ∈ `SOURCE_RIGHTS_HOLD/LOCAL_ONLY/NEEDS_EVIDENCE/NOT_ENTRY_CANDIDATE`, 별도 `local_readiness=LOCAL_READY` 등 구분. `model_review_executed=false`는 **이 진단 조회가 모델을 호출하지 않았다는 뜻**이며, 기존 저장된 AI 검토 이력을 지우거나 재판정하지 않는다. 캡처·샘플 신원 불일치 시 UI에 다른 후보의 증거를 표시하지 않는다.
- **LIVE-02 미완료 판정 근거:** 사용자 PC의 실제 COMPLETE 캡처를 격리/읽기 전용으로 연결한 FastAPI와 브라우저에서 선택 종목별 상태·코드를 확인하지 못함. 실제 원본 DB write/market provider 호출 0. 사용자 UI 검증 후만 DONE 전환; G2-01~04 유지, G2-05 보류, JEV-LIVE-03 전까지 실종목 외부 전송 NO-GO.


### 2026-10-29 LIVE-02 사용자 Windows API 회귀 확인 (브라우저 UAT는 대기)

- 사용자가 `C:\Projects\StockScope`에서 `git pull --ff-only`로 개발 브랜치 HEAD `7d99e6a`까지 fast-forward 확인 (기존 작업 트리 경로 재사용, 별도 worktree 없음).
- `.\.venv\Scripts\python.exe -m pytest -c .\backend\pyproject.toml .\backend\tests\test_jev_live_02_local_readiness_api.py -q` 사용자 Windows 실행 결과: **2 passed, 0 failed**. Starlette/AnyIO `DeprecationWarning` 1건은 비차단 경고이며 해당 기능 실패 증거가 아님.
- [HEAD `7d99e6a` CI #40796193659](https://github.com/SkyBluekor/StockScope/actions/runs/40796193659) **4/4 SUCCESS**, backend Python 3.11/3.14, frontend, Windows Fresh Clone 완료.
- **완료 판정은 여전히 LIVE-02 CODE+CI+USER WINDOWS API TEST PASS / 실제 저장 COMPLETE 후보의 브라우저 UAT PENDING**. 운영 DB 복제·격리와 브라우저 선택 후보의 `local-readiness` 원인 코드 검증이 남았음. TypeSafe/시장 데이터 외부 전송 허용 아님.


### 2026-10-29 LIVE-02 실제 Windows 브라우저 피드백 및 후보 번호 불일치 수정

- 사용자가 실제 `http://127.0.0.1:5173` Scanner 화면에서 2026-10-28 선택 후보 셀트리온(KOSPI 068270), AI 검토 탭의 `이 후보의 JEV 실행 준비도 · 로컬 읽기 전용` 부분을 확인. 화면 오류: `저장 캡처와 선택 종목의 식별 정보가 다릅니다. 다른 후보 결과를 표시하지 않습니다.` → UI identity fail-closed는 정상 작동했으나 **정확한 준비도 조회는 실패**. LIVE-02 DONE 불가.
- 근본 원인 코드 대조: `ProspectiveCatalog.finalize_capture`의 `enumerate(candidates)`가 `sample_index=0`부터 저장, LIVE-02는 UI의 1-based 표시 순위 `rank`를 그대로 API에 전달했으며 GET Query도 `ge=1`, React hook도 `sampleIndex<1` 거부. 따라서 화면 1위는 저장 샘플 1(두 번째 후보)을 조회했고, 다른 ticker여서 가려진 것.
- 실제 코드 수정: [API 0-based 허용 `bc1c65a`](https://github.com/SkyBluekor/StockScope/commit/bc1c65ab4290f5f73fce7eed508e98d35b83f6a5), [표시순위→저장 인덱스 `00c957d`](https://github.com/SkyBluekor/StockScope/commit/00c957dde1fdd8aacc006748e0f8abb8ac118f04), [첫 후보 요청 허용 `b45ead7`](https://github.com/SkyBluekor/StockScope/commit/b45ead7fe349364fb607636e7758cd57f52b1c5a), [API 번호 계약 주석 `db67963`](https://github.com/SkyBluekor/StockScope/commit/db67963a343829930816d764c31a7b9a71424386), [첫 행 0·다음 행 1의 서로 다른 해시 검증과 마이너스 인덱스 거부 `52d6804`](https://github.com/SkyBluekor/StockScope/commit/52d680480508b9aea857dc71436e5227fee53d55).
- [동일 수정 HEAD CI #40797590774](https://github.com/SkyBluekor/StockScope/actions/runs/40797590774) **Backend Python 3.11/3.14 · Frontend Node22 · Windows Fresh Clone = 4/4 SUCCESS**. 리그레션은 합성 SQLite sample 0/1의 다른 identity와 읽기 전용 바이트 불변성을 확인. 외부 유료 TypeSafe 0.
- **남은 검증:** 사용자 현재 PC `C:\Projects\StockScope`에서 `git pull --ff-only` 후 backend 서버를 **기존 격리 preview 환경변수를 보존한 동일 PowerShell 세션에서 재시작**, 브라우저 강력 새로고침; AI 검토 탭의 선택 후보 정확 일치 및 준비도/차단 이유를 확인. UI 확인 전에는 LIVE-02 **NOT DONE**. 기존 G2-01~04 유지, G2-05 보류, 실제 시장 외부 전송 NO-GO, 실모델 유료 추가 요청 없음.


### 2026-10-29 LIVE-02 최종 Windows 인수 완료 (앞선 PENDING 기록은 과거 상태)

- 사용자가 최신 코드 (`1373e7b` pull 후 `backend/tests/test_jev_live_02_local_readiness_api.py` **3 passed** 확인), `http://127.0.0.1:5173` 실제 브라우저에서 **셀트리온(KOSPI 068270), Scanner 저장 분석 2026-10-28**의 **AI 검토** 탭 스크린샷 제공. 이전 캡처/종목 mismatch 경고가 사라졌고 선택 후보의 `이 후보의 JEV 실행 준비도 · 로컬 읽기 전용` 진단이 실제 보임.
- 확인된 사용자 표시: `입력 근거 확인 필요`, `V4: BLOCKED_HORIZON`, `출처 연결: COMPLETE`, `순위 PASS / 전략 LEGACY_DERIVED / Risk PASS / 정책 PASS`, `원천 공개 시각 UNKNOWN`, `사용 권한 UNVERIFIED`, `SOURCE_RIGHTS_HOLD`(전송 불가), `이 조회에서 모델 요청 0회`; 미실행 사유 코드 및 캡처 해시 표시. **AI 모델 추론 결과는 없음**, 실종목 API 요청/과금 0.
- [후보 index0/1 수정·회귀 코드 `52d6804`](https://github.com/SkyBluekor/StockScope/commit/52d680480508b9aea857dc71436e5227fee53d55) [CI #40797590774](https://github.com/SkyBluekor/StockScope/actions/runs/40797590774) **4/4 PASS**. 직전 문서 HEAD [CI #40797912620](https://github.com/SkyBluekor/StockScope/actions/runs/40797912620) **4/4 PASS**. **LIVE-02 DONE**은 이 단일 사용자 실제 후보 화면 검증을 포함한 단계 인수 판정이며, 다양한 후보 전환이나 시장 데이터 outbound 허가를 증명하지 않는다.
- **NEXT LIVE-03**: 원천 KRX 주식/지수 정보 및 파생된 Scanner 판단을 TypeSafe 외부 수신자로 전송할 권리, 공개/수집/동결 시각, 적용 계약과 payload 실제 wire 검증. 근거 확보 전 실종목 TypeSafe 호출은 `NO_GO / PROVIDER_HOLD` 계속. LIVE-01 순수 합성 유료 1회 완료, 추가 유료 호출 승인 없음. G2-01~04 불변, G2-05 보류, PR #170 Draft 유지.

 
### 2026-10-29 LIVE-03 구현 1차 결과 — 로컬 차단 경계 (실제 수신 권한 확보 아님)

- **코드:** [`scanner_outbound_gate_live_03.py` `226af65`](https://github.com/SkyBluekor/StockScope/commit/226af65b8b839477d721cdeed33185811a86701c) 로컬 전용 전송 형식 검사. S8 기존 권한/시점 결과를 재사용하며, S7.4 expected producer 목록만으로 실제 개별 KRX 행 원천을 인증하지 않는다. 원문/키/시장 데이터 출력 없이 **V4 실제 leaf 경로별 `expected_parents`·미확인 여부**를 반환한다. `state.passed_condition_meanings`의 문장도 시장 원천 상속을 유지한다.
- **바이트 경계:** httpx `Request("POST", TYPESAFE_SYSTEM_ONE_URL, json=body)` 로 실제 transport JSON 직렬화 방식의 bytes를 생성해 SHA256 및 byte count와 서버의 고정 질문/모델·수신자 binding을 진단한다. 기존 `hash_local_outbound_candidate`의 **정렬 canonical projection hash와 실제 HTTP body hash를 별도 유지**. `verify_http_request_binding`은 변조/모델 변경/URL 변경/HTTP 메서드 차이를 거부하는 **순수 함수**이며 권한을 생성하거나 Provider에 자동 주입되지 않는다. 실제 전송 adapter binding은 미래 권한 검증·LIVE-04 준비 시 fail-closed로 연결 필요.
- **API/UI:** [GET `/api/simulation/jev/outbound-preflight` `df19037`](https://github.com/SkyBluekor/StockScope/commit/df190373150e6f5e65c59cfc1eb8625f92cd29f1), [Frontend TS 계약 `4a5da68`](https://github.com/SkyBluekor/StockScope/commit/4a5da6840b895ead8f676f4b4d1d5efbb94cc384), [Scanner AI 탭 `9ad76ad`](https://github.com/SkyBluekor/StockScope/commit/9ad76adbb4ed7270bead838e18898f5667eb6daa). 다른 종목/캡처 identity 불일치 시 차단, GET으로 시장/TypeSafe API 호출·운영 DB write 없음. `review-feature` 기본 OFF/실종목 POST 미호출 유지.
- **검증:** [`backend/tests/test_jev_live_03_outbound_gate.py` `3f3bb62`](https://github.com/SkyBluekor/StockScope/commit/3f3bb62d8dcb1efc3e37c3dabf6a60c5e2c50c0f) 합성 저장소 GET HOLD, 미존재/invalid 인덱스 차단, 동일 body 검증/변조·모델·수신자·method 거부, 자격 위장 필드 비승인, 본문 민감 문자열 거부, SQLite 바이트 불변. [전체 CI #40805284863](https://github.com/SkyBluekor/StockScope/actions/runs/40805284863) **4/4 SUCCESS** (Backend Python 3.11/3.14 + Frontend Node22/Chromium + Windows fresh clone). CI 실제 TypeSafe 과금 0.
- **다음 인수:** 사용자 Windows `C:\Projects\StockScope` 기존 격리 DB preview로 `GET /outbound-preflight?capture_id=...&sample_index=0` 및 Scanner AI 탭에서 셀트리온의 **HOLD와 정확한 사유**, 유료 호출 0 확인. 원천 제공처/TypeSafe의 실제 적용 권한·원천 revision/공개 시간 진위·RA01~RA10 신뢰된 검증자·실행 승인 아직 확보하지 않음. 기존 시장 후보는 반드시 계속 HOLD. 실제 ALLOW 구현/전송/유료 1회 실행은 별도 근거와 승인이 필요하다.
- **운영 불변:** G2-01~04, Scanner/Prospective 원본, Holdings 불변. G2-05 보류, PR #170 Draft, LIVE-01의 합성 유료 한 번 사용 완료, LIVE-02 DONE 보존. **LIVE-03는 현재 CODE+CI DONE이지만 단계 인수와 법적 권한 확보는 NOT DONE**.


### 2026-10-29 LIVE-03 사용자 Windows 브라우저 인수 — 로컬 HOLD 판정 완료

- 사용자가 `C:\Projects\StockScope`에서 최신 LIVE-03 변경까지 `git pull --ff-only` 적용, `backend/tests/test_jev_live_03_outbound_gate.py` **4 passed**, Starlette/AnyIO 비차단 DeprecationWarning만 있음을 실행 로그로 제시함. 실제 브라우저 이미지에는 **셀트리온(KOSPI 068270) 2026-10-28 저장 후보**, AI 검토 탭 LIVE-03의 **「실제 데이터의 외부 전송 자격」** 영역이 렌더링됨.
- 실제 표시: `외부 전송 보류`, `실제 JEV 모델 호출 없음`, `검토 입력 또는 권한 근거 부족 → 요청 본문 생성 안 함`, 실행 권한 `NOT_AUTHORIZED`, 수신자 `TYPESAFE_SYSTEM_ONE`, 원천 시각 진위 `UNVERIFIED`, trusted rights resolver `NOT_CONFIGURED`, `OUTBOUND_BODY_NOT_VERIFIABLE`, `EXECUTION_APPROVAL_NOT_GRANTED`, `LEGACY_DERIVED_IDENTITY`, `LEGACY_HORIZON_UNDEFINED` 등의 사유가 표시됨. 앞선 LIVE-02의 `BLOCKED_HORIZON`이므로 이 실제 후보는 TypeSafe V4 요청을 만들 수 없음.
- [LIVE-03 코드 CI #40805284863](https://github.com/SkyBluekor/StockScope/actions/runs/40805284863) **4/4 PASS**, [직전 문서 CI #40805668772](https://github.com/SkyBluekor/StockScope/actions/runs/40805668772) **4/4 PASS**. 합성 V4 body를 실제 httpx JSON과 동일하게 재현하는 SHA256/변조 검사는 테스트됨. **사용자 화면에서 실제 종목의 HTTP 바이트 생성·전송 테스트는 실행되지 않았음.**
- **LIVE-03 로컬 차단·진단 단계는 DONE (HOLD/NO-GO 결론)**. 권리자로부터 KRX 원시 및 조건·순위·Risk 파생 정보의 TypeSafe 수신/처리·보관 허가, 계정별 TypeSafe 처리조건, 원천 revision/publication 시각 및 RA01~10 신뢰 증빙은 별도 미확보. `HOLD`는 **정상 차단 결과**, 법적 전송 승인이나 구현된 실제 발송 gate를 의미하지 않는다.
- **NEXT LIVE-04는 실종목 유료 API 호출 BLOCKED**. 그동안 허용되는 일은 실제 HTTP 전송을 일으키지 않는 사용자용 단일 후보 opt-in/job/중복·실패 경계의 합성 Mock 구현 및 실사용 UI, 승인된 원천 계약 증거 확보, 지원되는 Horizon/원본 전략 신원 경로 점검뿐이다. LIVE-04 real-market provider 실행 전 실제 adapter에 trusted rights resolver·검증된 exact HTTP body·모델/계정/목적/예산 승인 결합을 반드시 구축하고 새로 검증한다. 시장 원시·파생 데이터 전송 금지, G2-01~04 유지/G2-05 보류, LIVE-01/02 DONE, PR #170 Draft.


### 2026-10-29 LIVE-04 합성 Mock 단일 후보 수동 검토 — 첫 구현

- **실제 코드 구현:** [개발용 job/store `f658430`](https://github.com/SkyBluekor/StockScope/commit/f658430e4a82c96fc857b144db6fe89a726daf60) + [명시적 localhost API `8058ec0`](https://github.com/SkyBluekor/StockScope/commit/8058ec0f34c83d3ab2ae8d35ac9dc556a58ab4de) + [프런트 타입 `e21cf02`](https://github.com/SkyBluekor/StockScope/commit/e21cf025b4e033ec9b1ec2731a90e8ffadf5e502) + [Mock 수동 버튼 `96761d1`](https://github.com/SkyBluekor/StockScope/commit/96761d1d7f6635e2d6967a911eba92731e877a0c) + [Scanner AI 탭 삽입 및 진단 목록 접기 `286faf1`](https://github.com/SkyBluekor/StockScope/commit/286faf1134abb20c276b2e20d88ad72e9d714fce).
- **경계:** `STOCKSCOPE_JEV04_SYNTHETIC_DEMO=1`이 서버 OS 환경에 있어야 개발용 GET `/api/simulation/jev/synthetic-demo/status` 및 POST `/api/simulation/jev/synthetic-demo/start` 사용 가능. HTTP 연결 소스·host는 loopback/testclient만 허용, POST에 `X-StockScope-Synthetic-Demo: confirmed` 명시 헤더 요구. payload에 종목·실시장 capture id·API 키를 받지 않음. `JEV_API_KEY` 로딩·실제 network provider 생성/시장 DB 열기 없음. 실제 `GET /review-feature`는 `available=false`, `POST /reviews` 기본 `FEATURE_NOT_ACTIVATED` 유지.
- **Mock 실행:** 작성 합성 ticker `999991`, `JEV-LIVE-01-AUTHORED-SYNTHETIC` 재사용. 최초 승인 시 OS temp 내 repo별 고정 별도 폴더 `stockscope-jev04-synthetic-mock-...`에 새 SQLite, 기존 V4 FROZEN protocol, job JSON 파일 생성. ASGI BackgroundTasks로 `QUEUED → RUNNING → VALID/ERROR`. 기존 `JevManualReviewService.request_review`와 `TypeSafeJevCatalog`에 FakeTypeSafeJevProvider 하나를 주입하므로 **모델 HTTP 호출 0, 실제 과금 0**. 동일 job POST는 reusable, one-shot claim 파일이 남으면 재시도 금지. 서버 재시작 도중 `PENDING` job은 `INTERRUPTED` 및 `PROCESS_RESTARTED_NO_RETRY`로 표시, 자동 재실행/재과금 불가. `cost_usd=0`은 **Fake Mock 비용**이며 실제 TypeSafe 단가 보장이 아님.
- **원인·수정:** 첫 CI에서 기존 개발 fixture의 `tools.data` import를 일반 FastAPI 앱 import 시 실행해 Python 3.11/3.14 startup 실패. [Lazy-import 수정 `8b7e1ad`](https://github.com/SkyBluekor/StockScope/commit/8b7e1ad8b13a659382f370e641ee68900cb60870): 루프백 opt-in POST 뒤에만 개발용 fixture import하여 일반 서버와 CI import를 보존.
- **검증:** [Backend 수동 Demo E2E 테스트 `a74c343`](https://github.com/SkyBluekor/StockScope/commit/a74c343c0a507bbccf290f23020e797871253ff5) enabled/disabled gate, header, 저장, 중복, reload status 및 interrupted fail-closed 등. [코드 CI #40808788891](https://github.com/SkyBluekor/StockScope/actions/runs/40808788891) **4/4 SUCCESS** (Python 3.11/3.14; Frontend Node22; Windows fresh clone). 실제 브라우저 Mock 버튼 직접 클릭/저장 상태 확인은 사용자 Windows UAT 전까지 미실시.
- **다음 Windows UAT:** 기존 `C:\Projects\StockScope` 브랜치 pull → 기존 서버 종료 → 동일 터미널에서 `$env:STOCKSCOPE_JEV04_SYNTHETIC_DEMO='1'` 설정 → 일반 `.\dev` 또는 `.\run-dev.ps1` 실행 → Scanner AI 검토 탭에서 **현재 실제 종목과 별개의** '순수 합성 데이터' 버튼을 체크 후 한 번 클릭 → 결과 `VALID`, 저장된 `REVIEW_REQUIRED`, 모델 `jev-mock-returned`, mock requests 1, actual provider 0 확인 → 새로고침 때 재요청 없음. 두 번째 실행 불가를 명확히 안내.
- **완료 범위:** CODE+CI PASS, 실제 사용자 UI 인수 대기. **LIVE-04 real-market E2E 미완료 및 BLOCKED**: 검증된 원천/파생 권한·실 요청 직전 trusted rights resolver·정확한 outbound transport body/계정/목적/모델 예산 승인 결합이 선행되어야 함. G2-01~04 보존, G2-05 pause, Draft PR #170 유지. 이번 Mock 이외 실제 유료 호출 없음.


### 2026-10-29 LIVE-04 사용자 Windows 합성 수동 검토 스크린샷 인수

- **사용자 실제 브라우저 확인:** `C:\Projects\StockScope` 개발 화면의 **선택 후보 셀트리온 / KOSPI 068270** AI 검토 탭 안에 **독립된 `JEV 수동 검토 체험 · 순수 합성 데이터 (개발 전용)`** 결과 영역이 표시됨. 가상 종목 `999991`에 대해서만 `합성 결과 검증·저장 완료` / `추가 확인 필요`를 표시, `Mock 모델: jev-mock-returned · 검증: MATCHED`, `합성 Mock 호출 1회`, `실제 API 사용량 0`, `비용 $0.0000 (Mock)`, 저장 `review ID`를 확인. 이 화면은 실종목 셀트리온 분석 결과가 아니고 위쪽의 `AI 검토 미제공`과 구분됨.
- **범위 판정:** LIVE-04 **합성 Mock 수동 검토 UI 사용자 검증 PASS**. 실제 비동기 요청부터 카탈로그 저장 후 화면 렌더까지의 사용자 경로가 확인되었으나 사용자가 **페이지 새로고침 후 유지/중복 요청 재실행**을 직접 했는지는 화면 하나로 확정 불가. 새로고침 유지·중복·재시작 무재실행은 [합성 API 테스트 `a74c343`](https://github.com/SkyBluekor/StockScope/commit/a74c343c0a507bbccf290f23020e797871253ff5)과 [CI #40809193328](https://github.com/SkyBluekor/StockScope/actions/runs/40809193328) **4/4 PASS**로 별도 근거.
- **미완료·차단:** 실종목 TypeSafe provider 엔드투엔드 검토 **NO-GO/HOLD**. LIVE-03 `SOURCE_RIGHTS_HOLD`, `BLOCKED_HORIZON`, `LEGACY_DERIVED`, trusted source/right/as-of verification 및 runtime exact HTTP authorization 부재. **이후 이 코드를 실제 종목 전송에 연결하지 말 것**. 사용자 API 키 존재와 합성 성공만으로 권한이 생기지 않음. G2-01~04 유지, G2-05 보류, PR #170 Draft 유지. 다음 단계는 실제로 해결할 수 있는 제한 조건과 승인된 데이터 소스 및 UI 일치 여부를 판단하고, 사용자용 기능을 실제 종목 검토처럼 가장하지 않는 범위에서 발전시키는 것.


### 2026-10-29 LIVE-04R 1차 구현 — 실제 후보 입력 계약/간결 UI (CODE+CI PASS, Windows UAT 대기)

- **실제로 구현:** [`scanner_shadow_s7.py` `6e691f6`](https://github.com/SkyBluekor/StockScope/commit/6e691f6b9a870cab7761a729ebd2cd28d29b6558)에서 기존 정본 COMPLETE 캡처의 `created_at/started_at`가 실제 존재할 때만 read-only로 표시. 구형 DB에는 컬럼이 없을 수 있어 `None` (미확인)으로 반환; 원천 공개 시각으로 추정하지 않음. [`api/jev.py` `992e97f`](https://github.com/SkyBluekor/StockScope/commit/992e97fb012249fd9e2425cca2c1c36a86f31800): LIVE-02 `GET /local-readiness`의 `input_contract`에 동결 Horizon/정책·수치 승인 상태·전략 원본 신원·캡처 이벤트 시각·원천 최초 공개 UNVERIFIED를 구별. 전략 원본은 strategy+policy+engine 모두 PASS일 때만 `CAPTURED_ORIGINAL`, 레거시 유도 신원은 `LEGACY_DERIVED_NOT_ORIGINAL`로 유지. 비정상 Horizon도 서버 500 대신 `UNSUPPORTED`로 진단.
- **Frontend:** [`ScannerAiReview.tsx` `bfbc338`](https://github.com/SkyBluekor/StockScope/commit/bfbc3385e5f255805984d04c55bc63bc987c6a89) 사용자용 **선택 종목 · 로컬 입력 · 원본 전략 · 평가 기간 · 외부 전송 보류** 요약을 우선 배치, 실제 리뷰 버튼은 비활성/권한 확인 전이라고 명시. 상세 hash/코드 목록은 기존 접힌 영역에서만 보이며 [`JevSyntheticDemo.tsx` `8f29a72`](https://github.com/SkyBluekor/StockScope/commit/8f29a72b57f8652715ae6eacd07ffd7c7ccca011) 합성 Mock 체험도 별도 접힌 개발용 영역으로 이동. 실종목 결과와 Mock 결과 혼동 방지. TS 응답 계약 확장 [`5a6822f`](https://github.com/SkyBluekor/StockScope/commit/5a6822f4cfab01a37596ccd99d2fca0d87f792c2).
- **회귀 테스트:** [`9dac50d`](https://github.com/SkyBluekor/StockScope/commit/9dac50da0227a42c44adc8e943d1fc6ab2ef2f45), [`e592d39`](https://github.com/SkyBluekor/StockScope/commit/e592d39d9ab6ba19fdfdc83e1300ed4640c49910) 등: 원본 전략/Policy/엔진 결합, Horizon 미지정/SHORT/잘못된 값, snapshot 및 SQLite 불변, 기존 ACTIVE Selection Policy 후보 원본 버전/해시 검증 재사용을 테스트로 고정. 첫 CI의 Python 3.11/3.14 실패 원인은 구형 연구 fixture의 시각 컬럼 부재와 COMPLETE 캡처를 수정하려 한 신규 테스트였음. [코드 패치 `6e691f6`](https://github.com/SkyBluekor/StockScope/commit/6e691f6b9a870cab7761a729ebd2cd28d29b6558) 및 [순수 진단 테스트 `9dac50d`](https://github.com/SkyBluekor/StockScope/commit/9dac50da0227a42c44adc8e943d1fc6ab2ef2f45)로 수정함. **최신 HEAD 코드 CI [#40823176776](https://github.com/SkyBluekor/StockScope/actions/runs/40823176776) 4/4 SUCCESS** (Backend Python 3.11/3.14, Frontend Node22/Chromium, Windows Fresh Clone); CI TypeSafe 호출/과금 0.
- **미완료를 명확히:** 신규 Scanner 캡처에 기존 `ProspectiveService.capture_request_from_scanner_payload`가 이미 명시 Horizon을 보존하고 `verify_candidate_policy_binding`이 원본 버전/해시 불일치를 거부함을 확인했지만, **새 실제 운영 정책을 활성화하거나 새 전략 원본 증거를 만들어낸 것은 아님**. VN P1 S2 Horizon 수치 정책은 `EVALUATION_PENDING`; 구형 셀트리온 캡처의 `LEGACY_UNSPECIFIED`/`LEGACY_DERIVED`를 복구하지 않음. 개별 source revision/공개시각 및 TypeSafe 권한 증빙도 확보되지 않음. 실제 후보 `LOCAL_V4_PROJECTABLE` 달성, 신규 캡처 브라우저 검증 및 외부 원천 계약 확인은 **PENDING**. LIVE-04 실종목 provider E2E HOLD, LIVE-05 시작 금지.
- **Windows 다음 인수:** 기존 `C:\Projects\StockScope`에서 최신 개발 브랜치 pull 후 `.\run-dev.ps1` 재시작, 기존 격리 DB preview/저장 캡처 사용, Scanner AI 검토의 새 짧은 요약과 접힌 개발 Mock 분리 여부 확인. LIVE-02/03 API/기존 Scanner base 정합성 유지 및 외부 호출 0. G2-01~04 유지, G2-05 보류, PR #170 Draft.


### 2026-10-29 LIVE-04R 실제 Windows SQLite/API 장애 복구 확인

- 실제 사용자 로그에서 격리 DB 읽기 전용 SELECT로 **2026-10-28 셀트리온(KOSPI 068270), COMPLETE, sample_index=0** 확인 후 동일 candidate id로 GET `/local-readiness`, GET `/outbound-preflight`가 처음에는 모두 **422 S7_CAPTURE_NOT_COMPLETE**. 기본 `GET /`은 200, 임시 DB 파일은 존재함. 새로 시작한 서버가 기존 8000 포트를 점유한 별도 프로세스에 가려졌거나 다른 SQLite를 읽었을 가능성이 큼. PID 수준의 사후 확정 증거는 없음.
- `run-dev.ps1`의 [port 중복 차단 `a6baa41`](https://github.com/SkyBluekor/StockScope/commit/a6baa4169932cd30738ec0fcbd7ceb1616d8cde6) 반영 후 사용자가 **동일 `$check` 재실행**: **`local-readiness` HTTP 200, ticker 068270, `status=NEEDS_EVIDENCE`; `outbound-preflight` HTTP 200, ticker 068270, `decision=HOLD`**. 따라서 이전 422 API 장애는 Windows에서 해결 확인됨. 운영 정본 DB/캡처 변경 없음.
- 구분: **백엔드 실제 후보 API READINESS+HOLD 테스트 PASS**, 그러나 브라우저에서 재연결된 새 LIVE-04R 요약 화면 스크린샷은 아직 미제출. 임의로 LIVE-04R 전체 DONE 또는 `LOCAL_V4_PROJECTABLE`이라고 표시하지 말 것. 실시장 원천·파생 자료의 TypeSafe 전송은 계속 NO-GO; JEV 유료 호출 0, G2-05 보류, PR #170 Draft 유지.


### 2026-10-29 LIVE-04R 후속 Windows 스크린샷 인수 — 저장 후보 로컬 표시 성공

- 직전 사용자 PowerShell 읽기 전용 SELECT는 `COMPLETE` 2026-10-28 셀트리온(068270), sample_index=0을 확인. 재시작 후 `GET /api/simulation/jev/local-readiness`가 **HTTP 200 / ticker 068270 / status NEEDS_EVIDENCE**, `GET /api/simulation/jev/outbound-preflight`가 **HTTP 200 / ticker 068270 / decision HOLD**로 복구됨. 사용자 후속 실제 브라우저 스크린샷에서도 **같은 선택 종목·로컬 입력 근거 확인 필요·전략 원본 미확인·Horizon 상태 미확인·외부 전송 보류·실종목 JEV 검토 버튼 비활성**을 확인하며, 이전 두 API catch 오류 문구가 사라짐. 실제 저장 후보 **read-only API + 간결 UI Windows UAT PASS**.
- 기존 검증 코드 [#40823176776](https://github.com/SkyBluekor/StockScope/actions/runs/40823176776) **4/4 PASS**, UI 후속 재검증은 사용자가 제시한 스크린샷 증거이며 저장 데이터 수정이나 실모델 호출 없음. [`run-dev.ps1` port 중복 방지 `a6baa41`](https://github.com/SkyBluekor/StockScope/commit/a6baa4169932cd30738ec0fcbd7ceb1616d8cde6) 반영. 정확한 과거 422의 backend PID/DB 불일치 원인은 추정이며 로그로 입증되지는 않음.
- **하위 단계 인정:** 기존 후보의 입력/권한 분리·화면 단순화·HTTP 장애 수정 DONE. **전체 LIVE-04R 목표 중 신규 실캡처 V4 입력 정상화는 아직 PENDING**: 실제 신규 후보의 `LOCAL_V4_PROJECTABLE`, 승인된 SHORT/MEDIUM 수치 정책, 검증된 원본 전략 신원, KRX 원천 권한·공개시각 evidence 확보는 현재 없음. **`NEEDS_EVIDENCE` / `HOLD`는 정상 차단, 실제 JEV 판단 완료 아님**. LIVE-04 real-market API/TypeSafe outbound NO-GO, LIVE-05 대기, G2-01~04/G2-05 기존 상태 유지.


### 2026-10-29 JEV-LIVE-04R-P2 실행 기록 — 신규 Scanner 시작/완료 계약 동결

- **실제 생성/저장 경로 수정**: [ProspectiveCatalog `00186d6`](https://github.com/SkyBluekor/StockScope/commit/00186d65703df0fe09d46b4ced8d1619a0c21b89) 에서 같은 `source_job_id`의 이미 저장된 **PENDING request_json 전체**와 후속 `begin_capture`/ `finalize_capture` 요청이 완전히 같은지 확인. Horizon 의도/정책버전, ACTIVE/ROLLBACK Selection Policy id/hash, as-of/시장범위/후보 수가 작업 도중 달라지면 `PROSPECTIVE_CAPTURE_REQUEST_DRIFT`로 안전하게 거부하고 원본 COMPLETE/스냅샷/순위·Risk는 수정하지 않는다. 잘못된 시작 계약은 `PROSPECTIVE_CAPTURE_REQUEST_INVALID`로 분리. 이미 COMPLETE/DUPLICATE/PARTIAL인 작업은 기존 idempotent 조회 유지.
- **기본 Scanner 보호:** [ProspectiveService `8171f6e`](https://github.com/SkyBluekor/StockScope/commit/8171f6ede1a74f4c2f463cd1f4be9bfb0e43617f) 는 보조 캡처 begin의 두 새 계약 오류를 `FAILED` reason으로 반환, 일반 Scanner 분석까지 예외를 전파하지 않음.
- **증거 연결 테스트:** [신규 동결/변조 회귀 `c3198ac`](https://github.com/SkyBluekor/StockScope/commit/c3198ac4ee36448ec6e980a5520ecea09825f947) 는 7가지 begin/finalize 요청 변경, snapshot/storage 불변, 재호출 중복 금지와 안전한 Scanner 서비스 반환을 검증. [작성 합성 ACTIVE 원본·감사 V2 테스트 `0c1533d`](https://github.com/SkyBluekor/StockScope/commit/0c1533d87b6e6624630adc7d92694131d3f7405d)는 기존 `ProspectiveCatalog`의 실제 begin→finalize→DB 저장→list_samples를 통해 **Pin과 조건 PASS 원본 감사가 일치할 때** `semantic_policy_provenance=VERIFIED_PINNED_EXECUTION`, `semantic_condition_evidence`, `semantic_source_v2` hash 검증 및 전략 version/hash·Rank/Risk 보존을 확인한다. 감사 reader는 테스트에서 **작성 합성 Mock**으로 주입했으며 실제 user KRX 재현성 artifact를 성공 검증한 것이 아니다. 누락/조건 위변조/정책 불일치의 회귀도 포함.
- **CI 결과:** [Actions #40826721313](https://github.com/SkyBluekor/StockScope/actions/runs/40826721313) **4/4 SUCCESS**: Backend Python 3.11/3.14, Frontend Node22, Fresh Clone Windows. Python 3.11 2623 passed, 2 skipped. 실제 TypeSafe HTTP/과금 0.
- **남은 목표를 축소하지 말 것:** 코드상 시작/완료 Pin drift를 막고 **작성 합성 E2E**는 검증했지만, **신규 실제 KRX Scanner 캡처**에서 ACTIVE/ROLLBACK 증거 원본이 모두 기록되는지/정본 audit가 1:1 매칭하는지/`LOCAL_V4_PROJECTABLE`에 도달하는지 사용자 Windows 격리 저장소에서 **아직 확인하지 않음**. 승인되지 않은 VN_P1_S2 Horizon 수치 정책(`EVALUATION_PENDING`)을 임의 승인하지 않았고 실데이터 원천/파생 TypeSafe 전송권은 `HOLD`. LIVE-04 실제 JEV 호출 및 LIVE-05 배치는 아직 금지. Draft PR #170, G2-01~04 보존, G2-05 보류.


### 2026-10-29 LIVE-04R-P2 사용자 Windows 대상 테스트 결과

- **사용자 직접 보고:** 기존 `C:\Projects\StockScope`에서 안내한 `test_jev_live_04r_new_capture_pinning.py` 및 `test_jev_live_04r_fresh_scanner_evidence.py`의 **Windows 로컬 대상 테스트 모두 통과**. 사용자 로그의 개별 테스트 개수·실행 출력은 제출되지 않았으므로 정확한 건수나 실제 화면 E2E를 별도로 단정하지 않음.
- **GitHub 이중 검증:** [최신 문서 포함 CI #40827102901](https://github.com/SkyBluekor/StockScope/actions/runs/40827102901)도 **SUCCESS**. 앞선 코드 CI [#40826721313](https://github.com/SkyBluekor/StockScope/actions/runs/40826721313) 4/4 PASS 보존. **LIVE-04R-P2: 코드·자동 CI·사용자 Windows 합성 대상 테스트 PASS**로 인수.
- **별도 미완료:** 신규 **실제 시장** Scanner 실행 → 정본 Policy Pin/재현성 감사 → V4 `LOCAL_V4_PROJECTABLE` 검증은 아직 사용자 증거 없음. 실행 수치 Horizon 정책 `EVALUATION_PENDING`, KRX 원천·파생권/TypeSafe 처리조건 `HOLD`, LIVE-04 실모델 검토 및 LIVE-05 대기. 기존 저장 캡처 불변, G2-05 보류, PR #170 Draft 유지.


### 2026-10-29 LIVE-04R-P3 구현 기록 — 실제 신규 Scanner 검증을 위한 읽기 전용 추적

- **코드:** [`backend/app/jev/live_04r_p3_capture_probe.py` `596092f`](https://github.com/SkyBluekor/StockScope/commit/596092f717a71a018871f3f15d4074262a4e936f) 및 [`tools/data/jev_live_04r_p3_one_capture.py` `29b68bf`](https://github.com/SkyBluekor/StockScope/commit/29b68bf23bdfc465d2f700bc6433a6673c39473a) 생성. `load_frozen_candidates`의 기존 SQLite `mode=ro`/query_only + `assess_frozen_candidate`, `diagnose_v4`, `diagnose_s8`, `verify_semantic_source_v2` 재사용. 새 엔진·새 Provider·실시장 API 호출 경로 없음.
- **실사용 절차:** 서버가 운영하던 바로 그 **격리 `STOCKSCOPE_SIM_DB`** 경로를 확인하고 신규 Scanner 실행 시작 전에 `$p3Start=(Get-Date).ToString('o')` 저장. 이후 현재 Scanner UI에서 **새로운 분석 1회** 실행. `python -m tools.data.jev_live_04r_p3_one_capture --find-new --captured-after "$p3Start" --simulation-db "$env:STOCKSCOPE_SIM_DB"`로 생성된 `COMPLETE`+진입 후보 캡처 ID를 발견하고, 발견된 ID를 `--capture-id`로 명시해 같은 CLI에서 후보 1건 검증. 도구는 분석/주문/데이터 수집을 대신 수행하지 않음.
- **무결성:** `--captured-after`는 타임존 있는 시각만 받고 동결된 `created_at`보다 미래면 신선성 FAIL(종료코드 3). 운영 DB를 쓰거나 기존 COMPLETE/정본 Snapshot/전략 원본을 변형하지 않음. 새 캡처 원본이 실제 시장 실행인지 **시각 비교만으로 인증하지 않고** `source_kind=NOT_INDEPENDENTLY_ATTESTED`를 표시함. 보고는 제한된 ID/해시/상태/최초 차단 지점만이며 원문 시장 가격·V4 전송 본문 출력 없음. `outbound.decision=HOLD`, Provider calls 0.
- **테스트와 CI:** [`backend/tests/test_jev_live_04r_p3_one_capture.py` `5f1dbc9`](https://github.com/SkyBluekor/StockScope/commit/5f1dbc9864cb9a5f421de562b208826b94da31c4) : 기존 작성 합성 SQLite에서 동일 캡처 ID 조회, 새/오래된 생성 시각, timezone 필수, 다른 capture/sample 거부, `--find-new` 검색, HTTP/DB 불변·원문 미출력. [코드 CI #40829679177](https://github.com/SkyBluekor/StockScope/actions/runs/40829679177) **4/4 PASS** (Python 3.11/3.14, Frontend, Windows Fresh Clone). 검증 중 실제 KRX 신규 Scanner를 실행하거나 외부 JEV API 과금하지 않았음.
- **완료 판정:** P3 **검증 도구·테스트·CI 구현 완료**, 실사용 Windows **새 캡처 E2E 미확정**. 새 실캡처 1건에서 전략 Pin·fresh engine audit·V2/V4 실패 사유가 출력된 후 필요한 실제 생성 경로 버그를 식별/수정하는 후속 인수 필요. `LOCAL_V4_PROJECTABLE` 미증명, 수치 Horizon 정책 `EVALUATION_PENDING`, KRX/TypeSafe 권한 `HOLD`, LIVE-04 real-model/ LIVE-05 NO-GO. 기존 G2-01~04, G2-05 pause, Draft PR #170 유지.


### 2026-10-29 LIVE-04R-P3 Windows `NONE_FOUND` 진단 보완

- 사용자 Windows `C:\Projects\StockScope`에서 P3 대상 테스트 **11/11 PASS**, 격리 `STOCKSCOPE_SIM_DB` 파일 존재, 실행전 기준 `2026-10-29T15:36:39.9323285+09:00`. 이후 `--find-new` 두 번 모두 `NONE_FOUND`. 제공된 터미널 로그에는 새 Scanner UI 실행 완료/Job ID/신규 시세 준비 결과가 보이지 않아 **Scanner 실제 재실행 여부 미확정**.
- **발견된 진단 결함:** 기존 CLI [P3 `--find-new`]는 `status=COMPLETE AND sample.action=ENTRY_CANDIDATE`만 쿼리해 **DUPLICATE/PARTIAL/PENDING/FAILED/CANCELLED/INTERRUPTED 및 COMPLETE without entry를 모두 동일한 `NONE_FOUND`로 오표시**. Scanner의 정상 `finalize_capture()`는 동일 실행키에서 `DUPLICATE`를 남길 수 있으므로 결과 없는 원인을 혼동하면 안 됨. 기존 Scanner/시장 판단 코드에는 이번에 결함이 있다고 증명되지 않음.
- [`live_04r_p3_capture_probe.py` `23b5f4c`](https://github.com/SkyBluekor/StockScope/commit/23b5f4c69314a60830d13d4a35d68dbafbee87c0) 에 읽기 전용 `explain_new_capture_attempts()` 추가: 지정 시각 이후 **모든 캡처 상태**+후보 수/진입 후보 수/중복 원본 ID/오류 코드 구분. `FOUND` vs `NOT_ELIGIBLE` vs `NO_CAPTURE_AFTER_START`, 기존 `new_complete_entry_captures` 호환 유지. [CLI `78a227c`](https://github.com/SkyBluekor/StockScope/commit/78a227cc44b8b077d9a7ca913fb89c8a1c94c171) `--find-new`에서 새 정보 출력. [Test `a46d42f`](https://github.com/SkyBluekor/StockScope/commit/a46d42feb6903eeb336aaafc53539e9e06f495cd) 에 작성 합성 DB로 PENDING/FAILED/DUPLICATE/COMPLETE_NO_ENTRY, 시간 기준 없음, DB 읽기 전용 검증.
- [코드 CI #40831227686](https://github.com/SkyBluekor/StockScope/actions/runs/40831227686) **4/4 PASS**. 시장 전송·JEV 유료 호출 0. **사용자 실제 신규 Scanner 캡처 P3 인수는 아직 미확정**: 업데이트된 코드 Pull 후 동일 `$p3Start`로 `--find-new` 재조회, `new_scanner_capture_attempts`의 `diagnosis` 확인. `NO_CAPTURE_AFTER_START`이면 UI에서 실제 새 Scanner Job 수행 여부 및 백엔드/현재 CLI의 동일 `STOCKSCOPE_SIM_DB` 경로 여부 먼저 확인. 기존 완료 캡처 재사용으로 신규 실캡처 통과 판정 금지, 정책 Horizon `EVALUATION_PENDING`, 실제 TypeSafe outbound HOLD.


### 2026-10-29 LIVE-04R-P3 사용자 Windows 실제 Scanner 실행 증거 — DUPLICATE 확인

- 사용자 `.\\run-dev.ps1`은 로컬 격리 `STOCKSCOPE_SIM_DB=C:\\Users\\USER\\AppData\\Local\\Temp\\StockScope-JEV02-760bf7b7532c4a26b949cdfc53745e41\\simulation.db`를 백엔드 DB로 표시. 기존 기준시각 `2026-10-29T15:36:39.9323285+09:00` 이후 P3 `--find-new` 재실행 결과 **new_attempts_exist=true, status=NOT_ELIGIBLE, 신규 COMPLETE/ENTRY=0**, 시각 `2026-10-29T07:06:14.513503+00:00` (= 16:06:14 KST), source_job_id `f6c2081a94ea41b6b3ea52b688f2c3f2`, 새 캡처 `89c9c2ed-114d-4eb7-80d6-4d03d640b483`, **DUPLICATE_REUSED_CANONICAL**, 정본 `ee8bc385-1939-4626-aecc-20e6bdb32645`. 중복 행의 샘플 0은 설계상 정상(정본 행을 재사용), TypeSafe 호출 0/DB 진단 쓰기 0.
- **의미:** 새 Scanner 작업이 캡처 저장 경로를 지나 기존 `source_execution_key`/원본 snapshot 조건과 같아져 DUPLICATE로 종결된 **운영 사용자 증거**. 더는 신규 캡처가 아예 없다는 가설을 유지하지 않는다. 다만 이 로그만으로 Scanner가 캐시를 사용했는지 아니면 실제 fresh 엔진을 재계산했는지는 확정할 수 없다. `StockScannerService.run`은 `force_refresh=False`일 때 캐시를 사용 가능; 결과 동일성이 신규 독립 원본 감사/신규 실시장 V4 E2E 성공을 입증하지 않는다.
- **다음 단계:** 같은 조건으로 끝없이 Scanner를 재실행하지 말 것. 원본 `ee8bc385-...`에 연결된 COMPLETE 저장 후보에 대해 **기존 read-only 검사**로 전략 신원/Pin/V2/V4 막힘을 확인할 수 있지만 이는 과거 정본 참고 분석이며 P3 fresh 신규 capture PASS가 아니다. 권장: `python -m tools.data.jev_live_04r_p3_one_capture --capture-id 89c9c2ed-114d-4eb7-80d6-4d03d640b483 --captured-after '2026-10-29T15:36:39.9323285+09:00' --simulation-db <격리 DB>`는 중복을 기존 정본으로 해소해 진단하고 `freshness_time_consistent=false`에 따라 exit 3을 반환할 수 있음. `LOCAL_V4_PROJECTABLE` 신규 fresh 증명 여전히 PENDING, Horizon `EVALUATION_PENDING`, 실시장 TypeSafe rights HOLD, LIVE-05 보류.


### 2026-10-29 LIVE-04R-P3 사용자 Windows 실제 정본 V4 증거 진단 — 재검색 반복 금지

- 새 job `f6c2081a94ea41b6b3ea52b688f2c3f2`의 DUPLICATE `89c9c2ed-114d-4eb7-80d6-4d03d640b483` → 기존 정본 `ee8bc385-1939-4626-aecc-20e6bdb32645`을 P3 읽기 전용 도구로 진단한 **사용자 직접 PowerShell 결과**: `engine_audit_status=PASS`, PASS 조건 6개, `policy_binding_status=PASS`, `recorded_policy_provenance=VERIFIED_PINNED_EXECUTION`, dates/rank/risk PASS, Semantic Source V2 hash valid, lineage COMPLETE. **원본 strategy version/hash 둘 다 없음**, `strategy_integrity_status=LEGACY_DERIVED` (`LEGACY_DERIVED_IDENTITY`), `selection_policy_id=LEGACY_CURRENT_10_FALLBACK`, Horizon `LEGACY_UNSPECIFIED`, local V4 `BLOCKED_HORIZON`, state hash 없음. 소스 원천 release time 검증 없음. 이는 **기존 canonical 캡처 진단이지 신규 독립 COMPLETE 캡처 인수 PASS 아님**.
- **현재 코드 구조의 실제 진입 차단 확인:** `frontend/src/components/ScannerPanel.tsx`에서 `createScannerJob(request)`에 `horizon_intent`를 아예 전달하지 않음. `backend/app/api/backtest.py::create_scanner_job`는 명시 SHORT/MEDIUM일 때 `require_horizon_activatable(resolve_horizon_context(...))` 검사를 거쳐, `backend/app/horizon.py`의 수치 정책 `EVALUATION_PENDING`으로 HTTP409 `HORIZON_POLICY_NOT_ACTIVE`를 반환. 따라서 **현재 UI의 정상 신규 Scanner 실행으로는 명시 Horizon을 캡처할 수 없으며 기존 데이터 반복 분석만으로 `LOCAL_V4_PROJECTABLE`를 인수할 수 없는 구조적 한계**.
- **전략 신원 차단:** `production_selection_policy.py::legacy_selection_policy()`의 10개 operating strategy는 의도적으로 version/hash NULL이고, `pin_active_selection_policy()`는 승인된 ACTIVE policy/ref가 없거나 baseline 불일치 시 LEGACY fallback. 기존 정본에 원본 신원을 생성·주입·backfill 금지. ACTIVE/ROLLBACK 정책은 실제 승인/원본 증거 경로로만 획득할 것.
- **다음 실제 코드 작업 제안 (P4 범위):** (1) baseline-only Scanner에 사용자가 **명시적으로 선택한 투자기간을 로컬 검토 컨텍스트로만 전달·동결**하는 UI/API 동선을 설계/구현하고, Horizon 수치 정책 미승인 상태에서는 매매·수치 전략 activation과 실제 JEV 시장 데이터 전송은 계속 거부할 것. (2) ACTIVE 정책/승인 artifact 존재 여부를 읽기 전용 확인하고 실제 승인된 policy pin을 사용한 신규 원본 신원 보존을 검증할 것. 원본 없는 LEGACY를 ACTIVE로 임의 승격 금지. (3) 새 거래일 신선한 데이터와 비중복 캡처로 신규 real V4 로컬 경로 인수. (4) 외부 KRX/TypeSafe 출처·파생정보권 및 시간 권리 HOLD 별도 해결. **같은 날 같은 조건 후보찾기 재실행, P3 합성 테스트 재실행, 기존 정본 리라이팅은 해결책 아님**.


### 2026-10-29 JEV-LIVE-04R-P4 구현 증거 — 로컬 의미 검토/수치 실행 분리

- **UI/타입:** `frontend/src/components/ScannerPanel.tsx`, `frontend/src/services/api.ts`, `scannerUX.css`에 기존 UI 스타일의 작은 검토 기간 선택 추가: 미지정(기존 Scanner), 단기(SHORT), 중기(MEDIUM), 장기(LONG·V4 미지원). 선택 상태는 브라우저 탭 `sessionStorage`에만 유지; **현재 선택**과 **저장된 Scanner 결과의 과거 선택**은 다른 표시. `LOCAL_REVIEW_ONLY`는 사용자가 명시적으로 기간을 선택할 때만 요청에 첨부. 기존 Scanner 후보 선정/Rank/Risk/보유 관리 코드를 바꾸지 않음. 현재 시장 후보의 `LEGACY_CURRENT_10_FALLBACK` 출처를 승인 원본 전략인 것처럼 안내하지 않음.
- **백엔드 API/계약:** `backend/app/api/backtest.py`: `ScannerRequest.horizon_purpose`는 기본 `PRODUCTION_POLICY`, 선택적으로 `LOCAL_REVIEW_ONLY`. `horizon_intent`가 명시된 로컬 모드에서는 SHORT/MEDIUM/LONG `EVALUATION_PENDING`을 수치 정책 활성화로 다루지 않고 컨텍스트로 기록; 미지정 로컬 목적은 `HORIZON_LOCAL_REVIEW_REQUIRES_EXPLICIT_INTENT` HTTP409; 일반 `PRODUCTION_POLICY` 요청은 종전 `require_horizon_activatable` 및 HTTP409 유지. `result.horizon_context.purpose`에 최초 요청 모드를 기록; TypeSafe 실제 outbound 비활성 유지.
- **동결/중복:** `backend/app/prospective/models.py` `ProspectiveCaptureRequest.horizon_purpose`, `service.py` payload → request 이행, `catalog.py` `source_execution_key`에 `horizon_intent` / `horizon_policy_version` / `horizon_purpose` 포함. 시작-종료 request 전체 불변 검사 보존; 다른 Horizon/목적의 동일 market candidate를 기존 정본에 잘못 동결·합치기 금지. 이전 COMPLETE 스냅샷 후처리·백필 금지.
- **Policy 런타임 원인:** `api/backtest.py::_selection_policy_registry()`가 Strategy Governance API와 같은 `STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR` override를 존중하도록 수정. 설정된 승인 ACTIVE/ROLLBACK artifact가 없으면 정본 10종 LEGACY fallback을 그대로 반환하며 정책을 자동 승인·발행하지 않음. **사용자 Windows 실제 ACTIVE artifact 존재 여부는 아직 확인 필요**.
- **Tests:** `backend/tests/test_jev_live_04r_p4_local_horizon.py`에서 실제 FastAPI route 대상으로 SHORT/MEDIUM/LONG `LOCAL_REVIEW_ONLY` 202, 일반 목적 409, 무기간 로컬 409, invalid input 422/409, 수치 정책 미승인 확인. 작성 합성 격리 SQLite로 시작·동결·재읽기 요청 계약, 다른 기간/목적의 source execution key 분리, 동일 요청 DUPLICATE, start/end drift 차단 검증. 정책 runtime env와 Governance 일치 확인. 실제 시장 데이터/실 TypeSafe API 호출 없음.
- **남은 Windows 사용자 인수:** `C:\Projects\StockScope` 브랜치 Pull + `.\run-dev.ps1`; 신규 Scanner 화면에서 단기/중기 선택 후 로컬 검색이 HTTP409 없이 시작되는지, 실제 결과에 `horizon_context.intent`와 `purpose=LOCAL_REVIEW_ONLY`, 새 `prospective_capture`에 같은 기간·Pin 기록이 맞는지 확인. 캐시 재사용이면 원본 엔진 fresh 감사 증거를 새로 생산한 것이 아니므로 V4 준비도 성공으로 인정하지 말 것. 현재 선택기간 미승인, LEGACY strategy version/hash 미입증, 원천 데이터 TypeSafe 제3자 권한 HOLD 지속, LIVE-05 보류.


### P4 최종 코드 CI 확인

- [GitHub Actions #40838635212](https://github.com/SkyBluekor/StockScope/actions/runs/40838635212): **4/4 SUCCESS**, Backend Python 3.11/3.14, Frontend Node22, Fresh Clone Windows 모두 PASS.
- P4 사용자 Windows 브라우저 선택→Scanner 신규 캡처 저장→V4 구조 입력 인수는 **아직 진행되지 않았으므로 별도 PENDING**. 과거 LEGACY 원본 version/hash 문제를 해결했다고 주장하지 말 것. 실종목 TypeSafe 전송 HOLD 및 numeric Horizon `EVALUATION_PENDING` 유지.


### 2026-10-29 P4 사용자 화면 배치 회귀 긴급 수정

- **사용자 실제 Windows 스크린샷** `localhost_5173_scanner(4).png`: 상단 Scanner '시장 선택' 설명·후보 재검색 안내가 세로 한 글자씩 표시되고 첫 컨트롤 카드가 비정상적으로 길어짐. 이는 P4에서 기존 `.scanner-control-card` **3열 Grid**에 `.scanner-horizon-control`을 3번째 직계 자식으로 삽입하여 4개 자식을 3열 그리드에 자동 배치하고 기존 콘텐츠 폭을 축소한 레이아웃 회귀.
- **실제 UI 코드 수정:** [`ScannerPanel.tsx` `90d4dfa`](https://github.com/SkyBluekor/StockScope/commit/90d4dfa90d37c4ca51024b78a06bb63551721db5)에서 기존 '시장 설명 / 시장 버튼 / 후보 찾기'를 원래 순서와 3열로 복원, Horizon은 네 번째 자식인 2행으로 이동. [`scannerUX.css` `d701638`](https://github.com/SkyBluekor/StockScope/commit/d7016389daff93181b9af880d5d4e2ba252b6cce)에서 신규 Horizon 2행의 `grid-column:1/-1` 전체 너비 보장, 미디어쿼리 모바일 1열 보호 및 긴 문구 wrap 적용. P4 기능·백엔드·투자 판단 변경 없음.
- **브라우저 회귀 테스트:** [`p003-scanner-recheck.spec.mjs` `17f7d43`](https://github.com/SkyBluekor/StockScope/commit/17f7d4394c8bd9ea094d90a7ca260bd72fbf816f) 신규 테스트는 실제 Chromium에서 폭 1400/900/420 카드 높이, 첫 설명 텍스트 최소 너비, 전체 폭 Horizon 후행, 수평 스크롤 방지, SHORT 클릭→`LOCAL_REVIEW_ONLY` 서버 요청, 새로고침 선택 유지 및 외부 네트워크 차단까지 검증. [Actions #40840131900](https://github.com/SkyBluekor/StockScope/actions/runs/40840131900) **4/4 PASS** (Backend 3.11/3.14, Frontend Node22 Playwright, Windows Fresh Clone).
- **인수 상태:** 원인·코드·CI Chromium 정량 회귀 PASS. **동일 사용자 Windows 실제 화면이 정상으로 복구되었는지는 아직 재촬영/확인 전**. 기존 `C:\Projects\StockScope`에서 `git pull --ff-only`, 브라우저 강력 새로고침 후 Scanner 상단 카드 다시 확인. 이 UI 수정은 P4 실제 신규 시장 V4 입증이나 TypeSafe 권한 변동이 아님; real outbound HOLD, LEGACY 원본 신원 미확정 유지.


### 2026-10-29 P4 사용자 Windows 화면 재확인 — UI 붕괴 복구 PASS

- 사용자 후속 **실제 Windows 브라우저 스크린샷** `localhost_5173_scanner (5)(1).png` 확인: 전날 수정한 Scanner `시장 설명 / 시장 선택 / 후보 다시 찾기` 첫 행 정상 배치, `검토 기간` 별도 2행 정상 표시, 기존 종목 리스트/우측 상세 패널 정상. 앞서 발생한 세로 한 글자 배치·과도한 빈 카드 높이는 나타나지 않음. **사용자 화면 레이아웃 UAT PASS**(스냅샷 범위).
- 스크린샷에는 현재 검토 기간 선택 **단기(SHORT)** 및 `저장된 분석의 선택 기간: 단기 · 수치 정책 미승인` 표시. 또한 `이 분석의 전략 기준: 기존 10개 전략 · 승인된 원본 버전 미확인` 유지. 이는 **프런트 화면에서 저장된 분석의 SHORT 컨텍스트가 표시되는 증거**이며 DB 원본 capture ID/정본 SHA·V4 준비도나 실제 시장 JEV 호출을 증명하지 않음.
- P4 최종 상태 구분: **UI 레이아웃 복구 실제 사용자 Windows PASS**, 코드/Playwright CI PASS, Local Horizon 저장 화면 라벨 PASS; 신규 실제 COMPLETE 캡처와 `LOCAL_V4_PROJECTABLE`은 여전히 진단 미확정. 다음은 기존 P3 read-only CLI로 최신 실제 캡처 ID/진입 후보의 V4 상태만 확인하고, 또다시 동일 날 동일 시장 Scanner를 반복 실행하지 않는다. 시장 데이터 TypeSafe outbound HOLD, 숫자 Horizon `EVALUATION_PENDING`, 전략 원본 LEGACY 신원 미확정.


### 2026-10-30 JEV-LIVE-04R-P4-FINAL 코드/CI 완료 — 실제 사용자 SHORT 인수 별도

- **완료한 실제 코드**: [`backend/app/jev/live_04r_p4_final.py`](https://github.com/SkyBluekor/StockScope/commit/836067dcd2a87ab2340a3a0e23b9d0e0a2cb7012), [`tools/data/jev_live_04r_p4_final.py`](https://github.com/SkyBluekor/StockScope/commit/da14b4a7f6a9137b1a41275449e97575548f6b49), [`backend/tests/test_jev_live_04r_p4_final.py`](https://github.com/SkyBluekor/StockScope/commit/c2029d5f116087d2e9bfad1e59d34ffe6fb11967). `--find-short`는 DB의 SHORT COMPLETE/DUPLICATE 후보 ID와 원본 참조만 조회. `--capture-id`는 사용자가 지정한 ID만 진단하고 이전 정본 또는 타 후보로 자동 성공 승격하지 않는다. `--policy-status`는 현재 Runtime의 effective ACTIVE/ROLLBACK/LEGACY policy status 및 fallback reason만 로컬 확인.
- **정본 진단 분리**: 입력 snapshot은 기존 `load_frozen_candidates`가 digest 검증 후 제공; `assess_frozen_candidate`, S7.5 `diagnose_candidate`, S8 eligibility, `verify_semantic_source_v2`를 그대로 호출. 결과는 `local_v4.status`(+state_hash/reason), `strategy_identity.status`/원본 version/hash 여부, `horizon_execution.support_status`/숫자 정책 승인, `provider_authorization.decision=HOLD`/원천권한 확인을 독립 보고. 저장 전 이후 capture의 frozen Horizon intent·policy version·purpose 일치 검사, DUPLICATE는 canonical COMPLETE를 가리켜야 함. 과거 캡처인지 신규 fresh 실행인지 **독립 재현성 인증하지 않음**. JEV 실시장 HTTP, 시세 재다운로드, SQLite write, 매매 및 정책 승인 없음.
- **자동 검증**: 작성 합성 isolated SQLite 1건과 같은 실행 결과 DUPLICATE 1건, 저장된 요청/정본/context 구분, readonly file bytes, 샘플 선택 실패, 미존재 캡처 거부, 미승인 Horizon/LEGACY/V4 기술적 경로의 독립 표시. 실제 외부 Provider 요청 0. [GitHub Actions #40978076734](https://github.com/SkyBluekor/StockScope/actions/runs/40978076734) **4/4 SUCCESS**: Backend Python 3.11/3.14, Frontend Node 22, Windows Fresh Clone.
- **여전히 PENDING인 사용자 인수**: 사용자 Windows `C:\Projects\StockScope`에서 `git pull --ff-only` 후 `$env:STOCKSCOPE_SIM_DB`의 **실제 backend와 같은 격리 DB**에 대해 `.\.venv\Scripts\python.exe -m tools.data.jev_live_04r_p4_final --find-short --simulation-db "$env:STOCKSCOPE_SIM_DB"` → 결과에서 정확한 saved SHORT capture ID 선택 → `--capture-id "<ID>"` 재진단. `--policy-status`로 정책 원본 확인. 이 출력이 아직 없으므로 **실사용 SHORT V4가 LOCAL_V4_PROJECTABLE이라고 주장할 수 없음**. 실제 장애 증거가 나타나면 그 생성/조회 연결만 수정; 동일 시세 신규 Scanner 재실행 금지.
- **보존/차단**: 기존 Scanner 계산 Rank/Risk/보유/주문, COMPLETE snapshots 및 LEGACY 원본 신원 불변. Horizon `EVALUATION_PENDING`, TypeSafe 시장 원천·파생 데이터 권한 `HOLD`, LIVE-05 미실행, G2-01~04 유지/G2-05 보류, Draft PR #170 유지.


### 2026-10-30 LIVE-04R-P4-FINAL 실제 Windows SHORT 정본 인수 — SKIPPED_LOCAL 정상 종료

사용자 Windows `C:\Projects\StockScope`에서 새 PowerShell 세션의 `STOCKSCOPE_SIM_DB` 환경변수 누락으로 최초 `S7_SOURCE_DB_NOT_FOUND`가 발생했으나, **기존 격리 DB** `C:\Users\USER\AppData\Local\Temp\StockScope-JEV02-760bf7b7532c4a26b949cdfc53745e41\simulation.db`를 명시해 해결함. 새 DB 생성·수정·신규 Scanner 검색 없음.

**실제 저장 캡처 증거** (`--find-short`, 읽기 전용):
- SHORT / LOCAL_REVIEW_ONLY 정본 `a1e9c341-7542-4511-8740-e07f4ee250ff`, source job `5f0ed8d5b3634948903e506338e1421d`, `COMPLETE`, 전체 샘플 15·ENTRY_CANDIDATE 7.
- 동일 정본 참조 중복 `630043c5-414c-467b-b882-40d02a168530`, source job `72e086475bd54ab488678583f43681c3`, `DUPLICATE`; 중복 행의 저장 샘플 0 정상.
- `--capture-id a1e9c341-7542-4511-8740-e07f4ee250ff`는 **이 정본의 선택된 진입 후보 1건**을 검사함. 나머지 6개 진입 후보에 대한 V4 결과는 이 증거만으로 일반화하지 말 것. 실제 fresh Scanner 독립 재현성은 `fresh_scan_independently_verified=false`.

**실제 후보 1건 상세 결과** (`--capture-id`, DB 읽기 전용):
- `frozen_contract`: `horizon_intent=SHORT`, `horizon_purpose=LOCAL_REVIEW_ONLY`, `horizon_policy_version=VN_P1_S2_HORIZON_CONTEXT_V1`; 정본 request/canonical context 둘 다 true, `semantic_source_v2_valid=true`. Selection Policy `LEGACY_CURRENT_10_FALLBACK`, policy hash `531660e462820f606e033e0ec65eed0b7f441ea870e7e22e47b85fc84152b4e7`.
- `checks`: **rank, policy, engine, dates, risk 모두 PASS**; strategy `LEGACY_DERIVED`/`LEGACY_DERIVED_IDENTITY`. 실제 원본 strategy version/hash 두 개 모두 없음, `verified_original=false`.
- `local_v4`: `source_v4_status=SKIPPED_LOCAL`, `status=SKIPPED_LOCAL`, `semantic_status=LOCAL_MATCH`, `lineage_status=COMPLETE`, `state_hash` 빈 값. **의미 조합이 로컬에서 일치하므로 추가 TypeSafe 잔여 의미 검토 대상이 아님; V4 외부 요청 state가 투영·전송되었다는 뜻은 아니다.** `reason_codes`에 `EXPLICIT_EXECUTION_APPROVAL_MISSING`, `HORIZON_NUMERIC_POLICY_NOT_APPROVED`, `LEGACY_DERIVED_IDENTITY`, `LINEAGE_PARENT_UNVERIFIED` 등 안전 제약 지속.
- `horizon_execution`: `support_status=EVALUATION_PENDING`, `numeric_policy_approved=false`, `HORIZON_NUMERIC_POLICY_NOT_APPROVED`.
- `provider_authorization`: `decision=HOLD`, source publication UNKNOWN / revision UNVERIFIED / rights UNVERIFIED / account approval false, TypeSafe provider calls **0**, DB writes **0**.
- `--policy-status` 실제 Windows 결과: effective `LEGACY_CURRENT_10_FALLBACK`, `fallback_reason=ACTIVE_REFERENCE_MISSING`, active reference valid false, 원본 전략 신원 개수 0, snapshot hash valid true. 현재 CLI 정책 런타임에 ACTIVE 참조가 없다는 **실제 원인** 확인. 다른 실행 프로세스의 별도 환경 설정은 별도 증거 없으면 추측하지 않음.

**완료/미완료 구분:** P4-FINAL의 *기존 SHORT 정본 진입 후보 1건 로컬 V4 판정 연결* **WINDOWS PASS — SKIPPED_LOCAL (정상 분기)**. 이는 `LOCAL_V4_PROJECTABLE`로 잔여 의미 검토가 필요한 다른 후보의 구조적 state hash를 생성한 검증도, 실제 시장 TypeSafe API 실행 검증도 아니다. Horizon 수치 정책 미승인·ACTIVE 전략 원본 부재·원천 시장 데이터 권한/시각 불확실성은 **별도 단계로 남음**. 같은 후보를 재검색하거나 같은 의미 결과를 무한 반복하지 말 것. G2-01~04 유지, G2-05 보류, 기존 Draft PR #170 유지.

| LIVE-04R-P5 진입 후보 일괄 분류·제품 UI 표시 | **LOCAL BATCH CODE + CI 4/4 PASS / REAL 7-CANDIDATE UAT PASS (7 MATCH, 0 RESIDUAL) / UI UAT PENDING** | [`9a2dba4`](https://github.com/SkyBluekor/StockScope/commit/9a2dba4e69b4de3212d5ba4c4176d0347a42b168) · [`434fc48`](https://github.com/SkyBluekor/StockScope/commit/434fc482ae4313757622b8ffddca072ac5f219f0) · [`6d5c575`](https://github.com/SkyBluekor/StockScope/commit/6d5c575180be01d379b7225bbfb85ead3ea8fd5c) · [`2fadf70`](https://github.com/SkyBluekor/StockScope/commit/2fadf7079d29c00cb5fed1a453aa260d670e117a) | 기존 SHORT 정본 모든 ENTRY 후보를 P4 frozen inspector로 분류: MATCH/CONFLICT/INCOMPLETE/AMBIGUOUS/RESIDUAL_READY/RESIDUAL_BLOCKED/BLOCKED_EVIDENCE 별도 개수, 외부 실행 허용 false. `GET /api/simulation/jev/entry-routing` 및 `python -m tools.data.jev_live_04r_p5_batch --capture-id ID`. Scanner AI 탭에서 분류 합계·선택 후보 사유 표시, 제품 CTA는 실제 outbound 미승인 시 disabled. 브라우저 새로고침·조회는 유료 모델 호출 0. **기존 Reviewer POST는 실제 시장에서 여전히 DISABLED**, P5-C 실시장 provider 연결 미승인. Windows의 7개 실제 후보 결과는 로컬 DB가 있으나 아직 반환되지 않았으므로 개수 미확정. |


### 2026-10-30 P5 코드 구현(부분) — 실제 기존 7개 SHORT 후보 분류 및 화면 연결

- **Batch:** `backend/app/jev/live_04r_p5_batch.py`는 실제 READ-ONLY 정본 `load_frozen_candidates`에서 `ENTRY_CANDIDATE`만 선택, 각 sample_index를 P4 `inspect_stored_horizon_capture`로 재검증해 기존 S7.1/S7.5/S8/V2 정본 계약을 그대로 사용. `LOCAL_MATCH`/ `LOCAL_CONFLICT`/ `LOCAL_INCOMPLETE`/ `LOCAL_AMBIGUOUS`/ `RESIDUAL_READY`/ `RESIDUAL_BLOCKED`/ `BLOCKED_EVIDENCE` 7유형. 특히 S7.5의 `SKIPPED_LOCAL`을 의미 일치·충돌·증거 부족으로 구분하고, `RESIDUAL_READY`조차 `external_model_call_allowed=false`, outbound HOLD 유지. 계산 결과는 immutable sample hash와 sample index에 결합; 신규 후보 추가·원본 스냅샷 변형 없음.
- **API/CLI:** `backend/app/api/jev.py`의 `GET /simulation/jev/entry-routing?capture_id=`, `tools/data/jev_live_04r_p5_batch.py`의 `--capture-id` (같은 `STOCKSCOPE_SIM_DB`) 구현. API 호출·CLI 모두 TypeSafe provider/KRX 다운로드·SQLite write 0. 기존 P4 개별 진단 및 숫자 Horizon activation 정책 변경 없음.
- **UI:** 기존 `ScannerAiReview.tsx`의 선택 종목 AI 탭에 전체 진입 후보 counts와 정확히 일치하는 `sample_index/market/ticker` 현재 종목의 분기 및 미호출 원인을 표시. 다른 capture의 요약이면 차단. ROUTE별 비활성 CTA 문구를 의미 있게 표시하며 브라우저 열기·읽기만으로 유료 호출 0. 이미 작동하는 합성 Demo/저장 review UI 보존, 별도 카드 대형화 없음.
- **테스트:** `backend/tests/test_jev_live_04r_p4_final.py`에 실제 저장-정본 일괄 분기/API+CLI 결과 일치/결과 카운트 합계, 작성 합성 분기 가짜 provider 차단 검증. `frontend/e2e/p003-scanner-recheck.spec.mjs`에 실제 Chromium AI 탭의 local MATCH 표기, 수동버튼 disabled, 모델 POST 0회, 상단 카드 레이아웃 회귀 포함.
- **실제 Windows UAT 명령** (재검색 불필요): `cd C:\Projects\StockScope`, `git pull --ff-only`, `.\.venv\Scripts\python.exe -m tools.data.jev_live_04r_p5_batch --capture-id "a1e9c341-7542-4511-8740-e07f4ee250ff" --simulation-db "$env:STOCKSCOPE_SIM_DB"` (PowerShell 새 세션은 환경변수를 복구하거나 기존 `$db` 경로 전달). 결과의 `entry_count=7`, `counts`, `rows[].routing`을 사용해 어느 후보에 잔여 검토가 필요한지 **실제 수치로** 확정; GitHub CI 합성 결과를 현실의 7개 결과로 대체하지 말 것.
- **미완료/안전:** 실제 시장 TypeSafe 수동 Reviewer POST는 feature disabled, 원천 데이터/파생권한·원천 공표시점·ACTIVE 전략 reference·Horizon 수치 정책 미승인. 이번 단계는 로컬 후보 분류 및 사용자 표시 구현 범위이고 유료 실종목 JEV 호출 성공은 아님. 다음 실제 제품 연결에서는 승인된 입력만 기존 `JevManualReviewService`와 권한 분리된 provider에 연결하며 무허가 활성화 금지. Draft PR #170 유지, G2-01~04 유지, G2-05 보류.


### 2026-10-30 P5 최종 코드 CI 확인 및 로컬 의미 근거 부족 판정 개선

- [GitHub Actions #40984504198](https://github.com/SkyBluekor/StockScope/actions/runs/40984504198) **4/4 SUCCESS**: Backend Python 3.11/3.14, Frontend Node22 (Chromium P5 선택 종목 AI 탭 브라우저 회귀), Windows Fresh Clone PASS.
- [`2bedaf1`](https://github.com/SkyBluekor/StockScope/commit/2bedaf152e17da9b360b16dcf91f9e2f4ec5313c)에서 기존 `/local-readiness`가 LOCAL_INCOMPLETE/LOCAL_AMBIGUOUS를 `LOCAL_ONLY`(완료로 오해 가능)로 분류하던 버그 수정: 기존 공개 enum만 써서 `NEEDS_EVIDENCE`로 fail-closed. [`80c7a38`](https://github.com/SkyBluekor/StockScope/commit/80c7a38de3d42e26cb4c5ede285c1bd7eb20897b) 2가지 의미상태 FastAPI 테스트 추가. UI는 [`259d662`](https://github.com/SkyBluekor/StockScope/commit/259d6628c523efd6296d0d7b31b8bc747febab65)에서 선택 후보의 분기 의미를 최우선 안내하여 단순 SKIPPED_LOCAL 문구로 성공처럼 오해하지 않음.
- 이번 P5 *개발된 범위*는 **기존 SHORT 정본의 모든 ENTRY 읽기 전용 분류 + 화면 라우팅 + HOLD/분기 규칙 테스트**. **사용자 실제 격리 DB의 7개 ENTRY 분류 결과는 아직 받지 못했고, 운영 real-market Reviewer POST/유료 실제 TypeSafe 호출은 승인 전이므로 미완료**. CI 성공을 실제 7개 종목 분류 성공이나 모델 E2E 성공으로 쓰지 않는다.


### 2026-10-30 P5 사용자 Windows 실제 7개 ENTRY 인수 및 JEV 호출 0의 구조적 원인 확인

**Windows 실제 사용자 제공 출력:** `C:\Projects\StockScope`에서 기존 격리 DB, SHORT `LOCAL_REVIEW_ONLY` canonical COMPLETE `a1e9c341-7542-4511-8740-e07f4ee250ff`에 `tools.data.jev_live_04r_p5_batch` 실행. 재검색 없이 ENTRY 7개 모두 성공 분류:
- `entry_count=7`; `LOCAL_MATCH=7`, `LOCAL_CONFLICT=0`, `LOCAL_INCOMPLETE=0`, `LOCAL_AMBIGUOUS=0`, `RESIDUAL_READY=0`, `RESIDUAL_BLOCKED=0`, `BLOCKED_EVIDENCE=0`.
- 실제 화면 데이터가 아닌 정본 DB에서 읽은 7개 진입 후보: rank 1 `068270`, 2 `011200`, 3 `018880`, 4 `086450`, 5 `131970`, 6 `373220`, 7 `396300`; 전부 `routing=LOCAL_MATCH`, `semantic_status=LOCAL_MATCH`, `local_v4_status=SKIPPED_LOCAL`.
- **P5-A/B 배치 분류 Windows UAT PASS**. 이는 모델의 독립 검토가 필요 없음을 증명한 결과가 아니라 **현재 동결된 V2 의미 매핑·분기 계약에 따라 잔여 검토 대상이 0건**이라는 결과임. 실제 TypeSafe model calls 0은 설계 분기/HOLD에 의한 정상 차단이지 모델 유효성 검증 아님.

**2026-10-30 소스 원인 분석 (코드 읽기만, 수정/승인 없음):**
- `backend/app/strategy/condition_assertions.py`: 현재 10개 전략의 `_ASSERTIONS`는 모두 `STANCE_SUPPORTS`. `project_passed_condition_assertions`는 저장된 `status=PASS` 조건만 받아 매핑함. `UNRESOLVED/WEAKENS/CONTRADICTS`를 합법적으로 전달하는 독립 증거 경로가 현재 매핑에서 사실상 존재하지 않음.
- `backend/app/strategy/semantic_relations.py`: 현재 10개 전략 `_AUTHORED_RELATIONS`는 전부 `RELATION_REQUIRES_ALL` (HARD). `backend/app/strategy/semantic_composition.py`: 각 required concept에 SUPPORTS가 있으면 `RELATION_MATCH`, 모든 relation이 MATCH면 `LOCAL_MATCH`. 완성된 현행 ENTRY 소스가 일관된 SUPPORTS만 담으면 사실상 항상 SKIPPED_LOCAL이며, 모델에 맡길 잔여 의미가 설계상 발생하지 않음.
- 그러므로 `LOCAL_MATCH=7`을 모델 불필요/전략 우수성/미래 수익률의 독립 증명으로 해석하지 않음. **현 설계는 이미 PASS 된 정량 신호를 동일 계약으로 다시 확인하는 데 치우쳐 JEV 부가가치를 드러내지 못함**. 임의로 FAIL을 UNRESOLVED로 바꾸거나 근거 없이 `RESIDUAL_SEMANTIC_REVIEW`로 전환해 유료 호출을 늘리지 말 것.

**다음 구현 우선순위 (새 LIVE-05 자동 배치 아님):** 본래 정량 PASS와 독립된 **증거가 있는 잔여 의미 판단 대상**을 정의. 예: 원천 시각·뉴스/공시 관계·조건 정의 간 실제 모순, 출처 검증, 불확실한 자연어 의미 관계(실제 출처와 판단 시각 입증 시에만) 등. 유효한 반대/불확실성 정보가 없는 경우 `LOCAL_MATCH` 자체는 정직하게 유지. 새 버전의 source/composition contract, 정본 시간·권한 원칙, 실제/합성 검증 구분, 사용자 가치 확인까지 설계·구현하고, 기존 IMMUTABLE source v2 hash/이력은 소급 변경하지 않음. 실종목 TypeSafe 전송은 여전히 `HOLD` (소스 권리·수치 Horizon·ACTIVE reference 미승인); 승인 전 실시장 모델 실행 경로에 붙이지 않음. 브라우저 P5 화면 실물 확인은 별개 PENDING.


### 2026-10-30 P6-A: EventEvidence as-of 읽기 전용 참고 경로 추가

- 실제 7개 SHORT ENTRY 후보의 P5 구조적 로컬 경로는 모두 LOCAL_MATCH여서 기본 V4 잔여 Reviewer 요청이 0건이다. 기존 PASS assertion을 억지로 WEAKENS/CONTRADICTS로 전환하지 않고 독립 이벤트 근거의 별도 경로를 열었다.
- 독립 데이터의 실제 source는 기존 app.event_evidence/asof.py만 재사용한다. P6-A API는 기존 COMPLETE capture/sample identity를 검증하고 캡처 생성시각까지 관측된 참조만 읽는다. UI에는 참고 근거 없음/있음(충돌 미판정)/근거 불가 상태만 표시한다. 위 결과는 개별 종목 매수·매도 또는 외부 JEV 응답이 아니다.
- 현재 코드가 보유한 Naver/OpenDART 정책의 AI_TRANSFORM 권한은 false이며, stock-specific TypeSafe outbound permit을 자동 부여하지 않는다. 기존 external_model_call_allowed=false를 유지한다. P6-A API는 안전한 readonly 구현이지 LIVE-04 실종목 유료 호출 완료 증명이 아니다.
- 코드와 테스트 파일/최종 인수는 최신 JEV_NEXT_CHAT_HANDOFF.md를 기준으로 확인한다. Windows 실제 이벤트 DB UAT는 별도 미완료. 다음 P6-B는 timestamp/source·human-approved independent assertion 계약, P6-C는 V4와 다른 새 question version 및 실제 provider 전송권한 gate를 필요로 한다.


### 2026-10-30 P6-B: independent event assertion (local operator-authored) implementation

- P6-B adds a **separate contract/version** rather than modifying frozen V4 semantics. EventEvidence as-of's existing public identity hash remains byte-for-byte identical; a private-only pin projection exposes the verified event/version/quality/source identifiers needed to bind authored claims.
- Local signed-by-hash (tamper-detectable, NOT cryptographically signed by an external authority) assertion records are accepted only with explicit review metadata, as-of approved_at <= capture cutoff, exact candidate+source+quality identity, and an actual Source V2 authored strategy concept binding. Never infer a contradiction from headlines, price or event category. No default approval records. Legacy-derived original strategy provenance is not upgraded.
- Meaning verdicts are independently stored in API response and UI as EVENT_CONFLICT/COMPATIBLE/UNCERTAIN etc, separate from existing P5 LOCAL_MATCH. Naver/OpenDART derived retention and AI transformation remain disabled. Real TypeSafe market-data transmission, Scanner policy/numeric Horizon activation, and model training/evaluation are outside this stage. No DB writes/providers.
- New endpoint: GET /api/simulation/jev/independent-event-assessment. Optional local read-only assertion manifest requires STOCKSCOPE_JEV_P6_ASSERTIONS_FILE; absent by default => uncertain. This manifest is an operator-authored claim, not evidence of real-world authoritative approval. See docs/JEV_NEXT_CHAT_HANDOFF.md for tests and the next P6-C gate.


### 2026-10-30 P6-C: independent event-V5 pipeline (synthetic fake E2E; real HOLD)

- Added app.jev.event_v5 independent event question contract and synthetic test-only policy; V4 question/state/projector unchanged. Fixed authored fake fixture 999992 is the only accepted model input in this new path. The localhost opt-in demo performs hashed request -> FakeTypeSafeJevProvider -> validated noul response -> synthetic disposition -> isolated persisted JSON -> GET/UI reread, with no real-market provider calls and no original DB writes.
- Real candidate V5 routing is read-only and invokes P6-B inspect_frozen_event_assertions: all live paths return external_model_call_allowed=false, transmission_status=PROVIDER_HOLD, actual_provider_calls=0. REVIEW_CANDIDATE_PROVIDER_HOLD only means potentially meaningful semantics, not any third-party AI transfer permission.
- GET /api/simulation/jev/event-v5-routing?capture_id=&sample_index= is connected to Scanner AI compact summary. Localhost-only mock GET /event-v5-demo/status and POST /event-v5-demo/start require STOCKSCOPE_JEV_V5_SYNTHETIC_DEMO=1 and explicit confirmation, and never accept live ticker/capture arguments.
- CI and Windows real UAT statuses are independent. Next stage must assess real independent event availability and source rights, then separate V5 live entitlement/rollout protocol and empirical incremental-value comparison. Synthetic success never activates live V5. Refer to docs/JEV_NEXT_CHAT_HANDOFF.md.


### 2026-10-30 P6-D: real event evidence inventory and blocker resolution

- Introduced real_event_audit_p6d.py and its CLI jev_p6d_real_audit.py, alongside a read-only FastAPI endpoint and compact Scanner AI display. A canonical saved Scanner capture is matched to actual local SQLite data, if accessible, with capture/sample integrity checks. The audit distinguishes missing schema (unknown counts, not zero), zero source ingestion, zero event revisions, entity/relevance/quality gaps, as-of limitations and missing authored assertions. Stored table counts must not be interpreted as facts available at the original market decision time. No new market fetches, model calls, DB migrations or writes are allowed.
- GitHub runners cannot access the user's prior Windows isolated simulation.db. Therefore real entry/event counts, compatibility and source rights still need separate local Windows UAT. Seven preexisting P5 LOCAL_MATCH entries are not silently reclassified. This milestone is a diagnostic and cause-classification implementation, not live JEV validation.
- Official NAVER Search API terms explicitly prohibit search results and derivatives in AI inputs and generally prohibit persistent storage/third-party provision outside narrow caching exceptions. OpenDART's open-data purpose is documented but the exact right to send user-specific disclosure/derivative data to TypeSafe remains unverified; current P6 source policy stays blocked. TypeSafe MCA separates training from service/telemetry/retention processing and requires customers to respect third-party rights. KRX-derived market-data outbound rights are not proven. Details, official source links and the exact Windows CLI appear in docs/JEV_P6D_REAL_SOURCE_AUDIT.md.
- Do not add more generic HOLD/Mock scaffolding to claim progress. Next action is inspect the existing exact SQLite and permitted source contract; implement ingestion of authorized data or correct actual entity binding only where evidence and rights exist.


### 2026-10-30 Actual Windows P6-D UAT: all seven ENTRY lack ingested EventEvidence

- User ran P6-D read-only CLI against the existing isolated Windows simulation.db for canonical SHORT capture a1e9c341-7542-4511-8740-e07f4ee250ff after pulling b128ec1. Schema READY (9/9 as-of tables, no missing columns), but source refs=0, event revisions=0, entities=0, relevance=0, quality assessments=0, policy snapshots=0. All 7 ENTRY candidates are NO_INGESTED_EVENTS / NO_INDEPENDENT_EVIDENCE / SKIPPED_NO_EVIDENCE, reviewed assertions 0, actual TypeSafe calls 0, DB writes 0. This establishes missing ingestion in this exact database, not a successful semantic event assessment or proof that the seven investments were safe.
- Existing OpenDART provider exposes disclosure list GET, but no live ingest bridge to EventEvidence provenance/entity/quality store was identified. Next P6-E priority: verify source usage rights and implement authorized prospective ingestion in a separately controlled flow with genuine first-seen timestamps; NEVER claim today's newly fetched data was known when the older frozen Scanner capture was created. Naver provider_kind omitted in CLI caused known_policy=false for NAVER_NEWS; policies do exist but both disallow AI transform. TypeSafe market outbound remains HOLD. Exact UAT result and continuation plan in docs/JEV_NEXT_CHAT_HANDOFF.md.


## 2026-10-30 P6-E 실제 OpenDART 공시 조회 구현 (조회/화면 우선)

- P6-D 사용자 Windows 실검증에서 7 ENTRY 후보 전부 NO_INGESTED_EVENTS, EventEvidence 스키마 READY but source_refs/event_revisions/entity/quality 전부 0건이었다. 따라서 기존 7개 SHORT 원본을 다시 평가하거나 새 EventEvidence가 이미 존재하는 것으로 주장하지 않는다.
- P6-E 구현된 운영 경로: OpenDartProvider.disclosures()의 기존 list.json을 보존하며 명시적인 max_pages(기본 1, 최대 5)/total_page 검증, receipt_no 중복 제거, source identity/date 검증, API 013 정상 공시없음, DATE_ONLY receipt date, official viewer_url, truncated 표시. FastAPI GET /api/dart/stocks/{stock_code}/disclosures 는 기존 corp-code mapping을 통해 종목별 최대 31일·기본 2페이지·최대 3페이지, 수신 종목이 다른 공시 차단, DB write/모델 호출 0. Scanner AI 탭에 별도 축소된 '실제 OpenDART 공시 조회 · 최근 30일' 펼침과 수동 조회 단추; 자동 fetch/원본 저장 없음. 실데이터가 들어오면 공식 링크·건수/조회 기준 시각을 직접 볼 수 있다.
- 소스 정책: official DART API list.json guide https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001 , terms https://opendart.fss.or.kr/intro/terms.do . 현재 derived retention/AI transform 권한이 미승인인 EventEvidenceStore.store_source_ref() 보호장치를 우회하지 않는다. E4 공시 메타데이터의 영구 저장 및 event revision/entity/quality 연결은 실제 이용권 범위가 검증되기 전까지 실행하지 않았다. 실 OpenDART 서버/개인 계정 키는 GitHub CI에 없으므로 Windows 사용자 실조회 UAT는 별도.
- 테스트: backend/tests/test_jev_open_dart_live_p6e.py + Chromium frontend/e2e/p003-scanner-recheck.spec.mjs. 페이지 이동/013/DATE_ONLY/중복/상대 종목 및 날짜/무호출 UI/기존 사용자 데이터 무변경을 검사. 실제 commit HEAD CI 최종 확인 후 상태 보고. 전체 추가 설명과 Windows 확인 방법 docs/JEV_P6E_LIVE_OPENDART.md.
- 다음 실행은 일반 Mock/HOLD 추가가 아니라 사용자 Windows에서 기존 DART_API_KEY를 이용한 실제 목록 결과 확인과 허용된 source rights의 event ingest scope 증거 수집이다. 과거 SHORT 종목을 현재 조회해도 그 공시가 과거 판단 당시 관측됐다고 주장할 수 없다.


### P6-E 고정 Scanner 파일 보호 수정 (실제 CI 회귀 발견)

- 초기 P6-E는 backend/app/market/providers/dart.py에 직접 페이지 처리를 추가하여 고정 production baseline fingerprint 회귀 테스트 2개 실패를 유발했다. **이 잘못된 변경은 완전히 되돌렸으며** 1ce13cc8 원본 OpenDartProvider 파일의 GitHub blob SHA 1422609b51f678ef9f03547d9369fecf04d389ef가 다시 동일하다. baseline manifest를 바꾸지 않았다.
- 최종 P6-E 실조회 페이지 처리/013 status/검증은 신규 backend/app/market/providers/dart_disclosure_p6e.py로 분리했다. 기존 OpenDartProvider는 변경하지 않고 신규 API는 기존 provider._get()을 재사용하며, legacy GET /dart/disclosures/{corp_code}의 1페이지 동작은 원래 provider를 계속 호출한다. 신규 종목별 API는 전용 adapter 사용. Python 테스트도 별도 adapter 대상으로 변경했다.
- P6-E의 영구 EventEvidence 저장을 아직 수행하지 않았다는 사실과 실 OpenDART API 사용자 키 환경 UAT 미실시는 유지한다. docs/JEV_P6E_LIVE_OPENDART.md 참고. 수정된 최종 HEAD CI의 성공을 확인해야 한다.
