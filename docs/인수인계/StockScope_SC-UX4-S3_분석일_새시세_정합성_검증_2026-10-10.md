# StockScope SC-UX4-S3 — 분석일 판단과 KIS 새 시세의 정합성 검증

- 기준: `main` / `79a6fb5`에서 분기
- 진행: GitHub PR 구현, CI 실행 및 현재 PC 브라우저 UAT 별도
- 코드 위치: `frontend/src/components/scannerQuoteTruth.ts`, `useScannerQuote.ts`, `ScannerPanel.tsx`, `ScannerDecisionSummary.tsx`, `ScannerPriceStatus.tsx`, `scannerUX.css`
- 서버 Scanner/전략/Risk/DB/마이그레이션/Google Drive Runtime: 수정 금지

## 왜 수정하나?

과거 Scanner의 `priority.label='현재 진입 후보'`는 **분석일 기준 순위**다. `ScannerPriceStatus`에서 수동 조회한 새 KIS 시세는 과거 가격 기준과만 비교하고 현재 전략·Risk를 재검증하지 않는다. 이전 화면은 KIS 가격 조건이 벗어나도 별도 우선순위 카드에 현재 진입 후보라고 보여 오독 위험이 있었다.

## 표시 계약

1. **원판정**: `candidate.priority.tier`, `candidate.conditions`, `candidate.risk`, 분석일 날짜를 보존하고 원래 순위를 바꾸지 않는다.
2. **가격 참고**: `assessPriceRule()`로 KIS 가격과 이전 `price_rule`을 비교하며 `IN_RANGE/OUT_OF_RANGE/UNKNOWN`만 표시한다. 새 가격이 과거 범위 안에 들어와도 **실제 매수 신호는 아니다**.
3. **재검증**: 어떤 가격 조회 상태에서도 `strategyRevalidated=false`로 고정. 현재 전략·위험 재검증 전을 명시한다.
4. **정합성**: `quote.ticker`, `market`, `provider`, `mode`가 예상 응답인지 확인한다. 일치하지 않으면 가격을 반영하지 않는다.
5. **시점**: `received_at`, `provider_timestamp`, `delivery.source=CACHE`, 모의·실거래 환경과 장 운영 상태를 표시. 시각 미확인은 명시. 보관된 시세를 실시간으로 표시하지 않는다.
6. **동작**: 종목별 수동 조회만 허용하고 `CandidateDetail`에서 관리해 탭 이동 시 유지한다. 후보 종목/분석 실행이 변경되면 리마운트 후 비어 있는 조회 상태로 시작하며 늦게 도착한 요청은 AbortController로 차단한다.
7. **우선순위**: `RISK_HOLD`, `NO_TRADE`, 미충족 조건의 다음 행동은 가격 관련 권유보다 먼저 전달한다.
8. **5탭/관심·보유/과거/AI/JEV-X2**: UI 레이아웃과 모든 기존 경로를 보존한다.

## 테스트

- `frontend/tests/scannerQuoteTruth.test.mjs`: READY 6/6, NEAR_READY 8/9, 위험 보류, 참고 범위 안/밖/UNKNOWN, 잘못된 종목/시장/제공자, 캐시·모의투자, 제공 시각 누락, 조회 실패/진행 중.
- `backend/tests/test_sc_ux4_s3_quote_truth_contract.py`: 상위 상태 공유, 후보별 재시작, 취소, 프론트 표시/백엔드 경계 회귀.
- 기존 SC-UX2/4 버튼 위치 관련 레거시 계약은 새 구조로 갱신하되, 명시적 사용자 조회/가격 기준 비교 자체는 유지한다.
- CI: Python 3.11, Python 3.14, Node 22 (기존 2테스트 + 새로운 S3 테스트 + 빌드), Windows fresh clone.
- CI 통과만으로 실제 브라우저 UAT를 통과했다고 말하지 않는다.

## 남은 PC 실사용 검사

현재 PC `C:\TAEWOO\CapstonDesign\StockScope`에서 최신 코드를 받은 뒤 다음 검사:

1. 1440×900: 삼성증권 READY/분석일 우선순위 레이블. 전략·가격 탭에서 수동 조회 후 요약에 새 가격, 가격 범위와 검증 전 상태 표시.
2. 가격 참고 범위 안과 밖 두 경우. 어느 경우에도 순위는 변하지 않고 매수 가능이라고 표시하지 않는다.
3. 종목 A 수동 조회 → 요약 탭 이동 → 가격 유지 → 종목 B 선택 → A 가격이 B에 표시되지 않음.
4. 수동 조회 중 종목 B 전환 → 뒤늦게 수신된 A 응답이 B 상태를 덮어쓰지 않음.
5. 작은 창 1280×720, 모바일 390px에서 레이블·가격·시각·버튼 줄바꿈.
6. 이전 SC-UX4-S2 추가 후보 15개 확장/선택 유지와 상단 sticky 내비게이션은 별도 UAT.

## Runtime / 후속

다른 PC Google Drive Runtime 동기화는 **실행하지 않음**. 사용자 PC에서 최근 `JEV-X1` 마이그레이션 `CURRENT` 확인됨. `sync_local.ps1` 전체 실행은 데이터 통합 승인 전 금지하고 `-CheckOnly`만 사용.

이번 작업은 **표시 정합성 개선**이지 현재 일봉 최신화/전략·Risk 재평가 기능 구현이 아니다. 현재 전략 재검증의 자동화는 별도 설계 후 진행한다.
