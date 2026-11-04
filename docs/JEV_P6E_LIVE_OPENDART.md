# StockScope P6-E — OpenDART 실공시 조회 연결 (2026-10-30)

## 이번 구현 결과

기존 P6-D에서 Windows 격리 simulation.db는 EventEvidence 스키마 9/9 정상, source_refs / event_revisions / entities / quality 모두 0건으로 확인되었다. 이는 수집 데이터 미존재이며 기존 7개 종목이 안전하다거나 V5에 실제 추가 검토가 불필요하다는 의미가 아니다.

P6-E는 OpenDartProvider의 기존 corpCode.xml, list.json 경로를 재사용하여 유료 TypeSafe 없이 실제 OpenDART 공시를 UI에서 조회하는 **사용자 명시적 클릭 경로**를 우선 연결했다.

- backend/app/market/providers/dart.py: **운영 Scanner 기준 해시 보호를 위해 원본 그대로 유지**. 신규 backend/app/market/providers/dart_disclosure_p6e.py에서 기존 Provider의 인증·HTTP 조회를 재사용하는 별도 읽기 전용 어댑터 구현. 정확한 날짜 검증, max_pages 최대 5, total_page 확인, 중복 접수번호 제거, malformed 원본 거절, status=013(공시 없음) 정상 처리, corp_code 확인, 공식 viewer URL, DATE_ONLY, truncated/total_count 추가. 기본 1페이지 기존 API 응답 유지. DB 저장 없음.
- backend/app/api/data_sources.py: 새 GET /api/dart/stocks/{stock_code}/disclosures. 기존 OpenDART 6자리 종목→8자리 corp_code 조회 후 최대 31일, 기본 2페이지/20건(최대 3페이지/50건), 종목 신원 재검증, queried time UTC, event_evidence_storage=NOT_PERSISTED_RIGHTS_UNVERIFIED / external_ai_transfer=BLOCKED / db_writes=0 반환. 원천에 없으면 OpenDART 인증키 미설정 오류를 정상 노출. 기존 GET /api/dart/disclosures/{corp_code}에는 max_pages 옵션(기본 1)만 추가.
- frontend/src/components/ScannerDartDisclosure.tsx: Scanner → AI 검토 → 실제 OpenDART 공시 조회(접힘). 사용자의 '공시 새로 조회' 클릭으로만 API 요청. 선택 종목 변경 시 이전 응답 취소·화면 초기화. 접수일/공시 제목/공식 DART 링크, 총건수·일부 페이지만 표시 여부, 영구 저장/외부 전송 미실행을 고지. 기존 P6-D 진단 표기와 별개.
- frontend/src/services/jevApi.ts: 타입/실조회 API, cache=no-store, AbortSignal. backend/tests/test_jev_open_dart_live_p6e.py 및 frontend/e2e/p003-scanner-recheck.spec.mjs에 페이지/중복/013/날짜/다른 종목/비저장 및 클릭 전 무호출 E2E 테스트 추가.

## 공식 근거와 정책 범위

공식 OpenDART 공시검색 개발가이드: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001 . list.json은 total_count/total_page, corp_code, stock_code, rcept_no(14자리), rcept_dt(YYYYMMDD)를 반환한다. 접수일은 시각 없는 DATE_ONLY이며 최초 공표 시각으로 사용하면 안 된다.

공식 이용약관: https://opendart.fss.or.kr/intro/terms.do . 공시정보 직접 활용은 개방되어 있으나 원본 저작권 및 제3자 AI 수신/보관 범위는 별도 검토가 필요하다. 현행 app.event_evidence.policy.opendart_event_evidence_policy()는 DERIVED_RETENTION, AI_TRANSFORM=false이므로 EventEvidenceStore.store_source_ref()가 저장을 거부한다. 이번 P6-E에서는 소스 권한이 없는 한 이를 우회하지 않는다. 이미 제공되는 기존 제품의 조회 범위만 동작한다.

**이번 단계에서 완료된 것은 실데이터 API 조회 경로 코드와 UI, 자동 테스트다.** 2026-10-30 사용자 Windows 실 OpenDART 인증키로 조회한 결과는 아직 없으므로 실제 7종목 공시 건수를 주장하지 않는다. P6 EventEvidence 영구 저장, source revision·entity relation·quality assessment, 실제 TypeSafe 실종목 호출은 아직 미완료다. 새 조회 결과를 과거 SHORT 정본 캡처에 넣지 않는다.

## 사용자의 Windows 확인

기존 로컬 DB는 수정하지 않는다.

    cd C:\Projects\StockScope
    git status --short
    git pull --ff-only
    .\run-dev.ps1

프론트엔드 http://127.0.0.1:5173 에서 Scanner → 실제 후보 선택 → AI 검토 → '실제 OpenDART 공시 조회 · 최근 30일' → '공시 새로 조회'. 선택 종목의 기업 코드 매핑/실제 공시 건수/에러가 표시된다. DART_API_KEY가 미설정이면 기존 provider 구성을 확인한다. API 키는 GitHub/chat/로그로 공유하지 않는다. 개발 문서와 CI에서 외부 실요청을 수행하지 않는다.

## 이후 정확한 작업

1. 사용자 Windows 실조회 결과에서 corp_code 정상 연결 건수, OpenDART 자료 건수, 013 무자료/020 요청 제한/기타 매핑 오류 분류.
2. 공시 메타데이터의 EventEvidence 영구 보관/파생 활용 권한을 공식 근거와 사용자 계약에 맞춰 검증한다. 별도 source policy version 및 event revision/quality workflow가 허용된 뒤에만 저장하도록 구현한다. 승인되지 않은 권한 토글 추가 금지.
3. 신규 prospective Scanner 캡처 시점 이후 실제로 관측된 이벤트만 독립 평가. rcept_dt 접수일을 과거 최초 관측 시각으로 바꾸지 말 것. P6-B 검토 주장이 실제로 준비된 경우에만 V5 평가 후보로 표기.

## Scanner 고정 기준 보호

P6-E 1차 CI에서 운영 기준 해시 위반이 발생했으며, 원본 backend/app/market/providers/dart.py를 기준 커밋 1ce13cc8의 내용과 동일하게 복구했다. 기준 manifest를 바꾸지 않고 별도 dart_disclosure_p6e.py로 분리했으며 이후 CI에서 회귀 재검증한다. 기준을 새 해시로 밀어넣어 통과 처리하지 않는다.


## 2026-10-30 P6-E 실제 사용자 Windows OpenDART 화면 검증

- 사용자 제공 실제 실행 스크린샷 기준, Scanner → AI 검토 → 선택 종목 동국제약 (086450) → "실제 OpenDART 공시 조회 · 최근 30일" → "공시 새로 조회" 수행 성공. 2026-10-01~2026-10-30 실제 조회 **2건 / 전체 2건**, 화면 조회 시각 2026-10-30T04:59:47.509167+00:00.
- 실제 목록 2건 모두 접수일 2026-10-12: 주주명부폐쇄기간또는기준일설정 receipt_no 20261012900154; 주주총회소집결의(임시주주총회) receipt_no 20261012900140. 제목 및 DART 공식 원문 링크가 표시됨.
- 이 증거는 OpenDART 실제 HTTP 조회, 종목→corp_code 매핑 및 UI 링크의 사용자 PC E2E 성공에 대한 것임. 기존 7개 후보 전부 성공이라고 확대하지 말 것. 화면상 EventEvidence 저장 자료 0건, 영구 저장 미승인/미실행, 외부 AI 전송 차단, AI 모델 의견 없음, JEV V5 실행 0회는 그대로임. 이는 아직 데이터를 저장·평가하지 않았다는 의미이며 실제 공시의 전략 충돌 또는 투자효용을 확인한 것은 아님.
- 다음 개발 우선순위는 페이지 API/Mock 반복이 아니라 실제 공시 메타데이터의 저장·파생 권한 근거 확인 및 승인된 EventEvidence SourceRef→Revision→Entity→Quality prospective 연결. 공시 receipt_date는 DATE_ONLY이므로 원본 발표 시각으로 간주하지 말고 실제 first_seen/fetched_at을 보존. 기존 과거 SHORT 캡처로 시점을 소급하지 않는다.
