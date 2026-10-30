# JEV P6-D — 실제 이벤트 데이터 진단 및 이용권 확인 (2026-10-30)

## 상태

P6-C V5 합성 Fake Provider 검토는 코드·CI와 사용자 Windows UI에서 통과했다. 이는 실제 Scanner의 JEV 효용을 증명하지 않는다. P6-D는 새로운 Mock 없이 기존 사용자 SQLite의 사건 증거 존재·품질·시점·출처를 조사한다.

새 real_event_audit_p6d.py는 기존 canonical COMPLETE Scanner ENTRY_CANDIDATE의 snapshot_hash를 검증하면서 읽는다. SQLite는 mode=ro / PRAGMA query_only=ON만 사용한다. 스키마 누락, 수집 원본 없음, 이벤트 revision 없음, 종목 entity/relevance/quality 미연결, as-of 부적격, 검토 주장 없음, 외부권한 차단을 각각 구분한다. 저장 row count는 전체 이력이며 당시 의사결정 시점의 근거 건수와 동일하지 않다. 네트워크 다운로드, 실제 모델 호출, DB write 없음.

GitHub CI에서 사용자 Windows 로컬 격리 DB를 읽을 수 없으므로 실제 7개 종목의 EventEvidence 수는 미확정이다. 합성/빈 migration DB 수치를 실제 인수 결과로 보고하면 안 된다.

## 기존 데이터의 로컬 Windows 조사

PowerShell:

    cd C:\Projects\StockScope
    git status --short
    git pull --ff-only
    $db = $env:STOCKSCOPE_SIM_DB
    if (-not $db -or -not (Test-Path $db)) {
      throw "기존 격리 simulation.db 경로를 STOCKSCOPE_SIM_DB에 지정하세요. DB를 새로 만들지 않습니다."
    }
    .\.venv\Scripts\python.exe -m tools.data.jev_p6d_real_audit --capture-id "a1e9c341-7542-4511-8740-e07f4ee250ff" --simulation-db "$db"

실제 저장 SHORT capture의 7 ENTRY는 068270, 011200, 018880, 086450, 131970, 373220, 396300이며 현재 P5는 LOCAL_MATCH 7 / RESIDUAL 0이었다. 기존 결과 보존. JSON에서 entry_count / store.status / stored_counts_not_asof / cause_counts / 각 row cause/reference_status/assertion_status/v5_route를 확인한다. Scanner → AI 검토의 "실제 이벤트 저장 현황"에서도 API GET /api/simulation/jev/event-data-audit?capture_id=...로 간단히 표시한다.

## 공개 공식 약관 및 권한

- NAVER 공식 검색 API 이용약관: https://developers.naver.com/products/intro/terms/terms.md. 약관 2.3은 검색 데이터와 파생물의 저장·제3자 제공·AI 입력을 명시적으로 제한하며, 예외 캐싱은 2.4에 목적/기한 제한이 있다. 이 검색 API 데이터/파생물을 TypeSafe에 전송하지 않는다. API Hub의 별도 계약과 혼동하지 않는다.
- OpenDART 공식 이용약관: https://opendart.fss.or.kr/intro/terms.do 및 공시정보 활용 목적: https://opendart.fss.or.kr/. 일반 이용약관과 공공데이터 활용 목적만으로 개별 계정/정보 종류의 외부 제3자 AI 전송·보관 허용을 확정할 수 없다. 현재 P6 코드의 derived_retention 및 AI_TRANSFORM 미승인 유지; 실제 계정/라이선스 추가 증거 필요.
- TypeSafe 공식 MCA: https://typesafe.ai/legal/mca 및 Data Handling FAQ: https://help.typesafe.ai/articles/5974925716-how-is-submitted-data-used-or-retained . 고객은 제3자 데이터 권리를 준수해야 하며, 입력은 서비스 제공·요금·남용방지·telemetry 등의 목적으로 처리될 수 있다. 가중치 학습 미사용은 자동 Zero Data Retention 또는 외부 데이터 전송 허용과 동의어가 아니다. ZDR은 계정/별도 계약에 따라 확인: https://typesafe.ai/enterprise .
- KRX: 사용자별 원천 데이터 계약에서 시세 및 파생 Scanner 의미 정보의 제3자 AI 전송을 허용한다는 근거가 이번 조사에서 확보되지 않았다. 허용된 것으로 단정하지 않는다.

## 결함 종류별 조치

- SCHEMA_MISSING/INCOMPLETE: 실제 DB의 EventEvidence migration 상태 확인. 사용자 DB 자동 생성·수정 금지.
- NO_INGESTED_EVENTS/NO_EVENT_REVISIONS: 저장된 EventEvidence 원천/이벤트가 존재하지 않는다. 기존 코드의 EventEvidence store/asof 및 tools/data migration/runtime에서 운영 가능한 자동 수집이 실제로 연결됐는지는 증명되지 않았다. 허용된 소스·수집 경로를 확보하고 실제 연결할 때만 수정.
- ENTITY_NOT_LINKED/NO_RELEVANCE_LINK: 정식 종목·기업 entity 및 해당 이벤트 관계를 확인. 단순 제목 일치로 관련성을 확정하지 않는다.
- NO_QUALITY_ASSESSMENT/NO_ELIGIBLE_ASOF_REFERENCE: 원본 revision, quality, first_seen/source published 시각을 검증한다. capture.created_at을 최초 공표 시각으로 대체하지 않는다.
- NO_PROSPECTIVE_APPROVED_ASSERTION: P6-B 로컬 작성 주장 기록·승인 시간·해시·관련 정의를 검증. 실제 종목에 synthetic event를 생성하지 않는다.
- PROVIDER_RIGHTS_NOT_APPROVED: 원천 데이터·파생물 권리와 TypeSafe 수신자·계정의 처리/보관 조건, 호출 1회 실행 승인을 확인하기 전에는 호출하지 않는다.

실제 API 호출 0은 이 진단의 설계 제약이며 JEV 실모델 유효성 검증이 아니다. 자동으로 HOLD Boolean을 true로 변경하거나 Fake 결과를 실종목 근거로 바꾸지 않는다. 임의의 고정 Mock 테스트 반복 대신, 실제 DB 수집현황과 계약상 허용 가능한 소스의 구체적 확보가 이후 단계의 핵심이다.
