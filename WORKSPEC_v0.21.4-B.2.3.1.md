# WORKSPEC v0.21.4-B.2.3.1 — Scanner Compact Workspace Runtime Validation & Polish

## 목적
B.2.3 Scanner Compact Decision Workspace를 실제 앱 레이아웃 조건에 맞춰 마감한다. 기능/계산을 추가하지 않고, 후보 없음 UX와 반응형 경계에서 발생할 수 있는 표시 회귀를 보강하고 런타임 검증 절차를 고정한다.

## 변경 범위

### 1. 후보 없음 / NO_TRADE 사용자 문구 보호
- Backend `empty_message`는 계속 사용할 수 있지만, 비어 있거나 내부 상태명 `NO_TRADE`가 포함된 경우 사용자 화면에 그대로 노출하지 않는다.
- 대체 문구:
  - `현재 확정 일봉 기준으로 10개 전략의 진입 조건을 충분히 만족한 종목이 없습니다.`
  - `조건을 억지로 완화하지 않고 다음 확정 일봉에서 다시 확인합니다.`
- 제목은 `억지로 추천할 종목이 없습니다` 대신 `현재 조건에 맞는 후보가 없습니다`로 중립적으로 정리한다.
- 후보 없음 상태에 `role="status"`, `aria-live="polite"`를 추가한다.
- 시장 데이터 자체가 부족한 경우에는 기존 `시장 데이터 준비` 흐름을 안내한다.

### 2. 실제 앱 폭을 고려한 Scanner 반응형 경계 보강
StockScope는 데스크톱에서 Scanner가 viewport 전체 폭을 쓰지 않는다.
- 기본 sidebar: 190px
- 1100px 이하 sidebar: 70px
- content 자체 padding 존재

따라서 기존 B.2.3의 `max-width: 1100px` 전환은 1101~1200px 구간에서 실제 Scanner 폭이 좁아도 desktop 4열 가격 비교가 유지될 수 있다.

B.2.3.1에서는 Scanner 전용 중간 폭 규칙을 `max-width: 1200px`부터 적용한다.
- 후보 비교 핵심 가격: 2 × 2
- 선택 상세 가격 계획: 3 + 2
- 상세 판단 3열: 1열
- 기존 820px 이하 후보 행 stack은 유지
- 전역 `.layout`, `.content`, `.card`, `.row` 수정 없음

### 3. 세션/접힘 상태 유지 확인
B.2.3 동작을 유지한다.
- 새 분석 완료 시 첫 후보 자동 선택
- 새 분석 완료 시 Historical Evidence 기본 접힘
- 선택 후보 key를 sessionStorage에 저장
- 상세 화면 이동 후 복귀/F5 시 선택 후보 복원 가능
- scroll / showMore / evidence expanded 상태 기존 로직 유지

## 변경하지 않는 것
- KRX API / Raw Cache / Market Store
- B.2.2.2d 데이터 무결성 로직
- 분석 기준일 판정
- Scanner candidate selection / Ranking
- 10개 Strategy 계산
- Risk / Entry / Stop / Target
- Historical Evidence 계산
- Backtest
- Production Exit Policy
- Profit Protection 계산

## 변경 파일
- `frontend/src/components/ScannerPanel.tsx`
- `frontend/src/styles.css`
- `frontend/tests/scannerCompactRuntimeRegression_v0214b231.ts`
- `frontend/tests/scannerSelectionSession_v0214b231.ts`
- `frontend/tests/scannerCompactRuntimeLayout_v0214b231.py`

## 검증 결과 — 실제 실행한 것

### PASS
- `analysisDateConsistency_v0214b222b.ts`
- `readabilityRegression_v0214b222.ts`
- `strategyLayoutRegression_v0214b222a.ts`
- `darkThemeRegression_v0214b221.ts`
- `scannerCompactWorkspace_v0214b23.ts`
- `scannerCompactRuntimeRegression_v0214b231.ts`
- `scannerSession_v0214b222b.ts`
- `scannerSelectionSession_v0214b231.ts`
  - 선택 후보 `KOSPI-192820` 직렬화/복원 확인
  - scroll position 동시 유지 확인
- `ScannerPanel.tsx` TypeScript transpile/syntax PASS
- `scannerCompactRuntimeLayout_v0214b231.py` Python syntax/compile PASS

## 브라우저 검증 상태
`scannerCompactRuntimeLayout_v0214b231.py`는 실제 Chromium/Chrome/Edge에서 다음을 검증하도록 작성했다.
- 1920 / 1440 / 1024
- 실제 `.layout + .sidebar + .content + .scanner-workspace` 폭 구조
- 후보 5개 Compact 행
- document/핵심 영역 horizontal overflow
- 종목명/판단/가격 text clipping
- 한국어 `word-break: keep-all`
- 1024에서 핵심가격 2×2
- 1024에서 상세가격 3+2
- Historical Evidence 기본 접힘
- NO_TRADE 사용자 노출 금지

단, 현재 작업 컨테이너의 `/usr/bin/chromium`은 최소 HTML에서도 headless 종료가 되지 않아 timeout이 발생했다. 따라서 이 환경에서 1920/1440/1024를 **실제 브라우저 PASS했다고 보고하지 않는다.**

사용자 PC에서 overlay 적용 후 아래로 자동 브라우저 레이아웃 검증 가능:

```powershell
python .\frontend\tests\scannerCompactRuntimeLayout_v0214b231.py
```

Chrome/Edge 자동 탐색 실패 시 `CHROME_BIN` 환경변수로 브라우저 실행 파일을 지정한다.

## Full build / 실제 앱 실행 상태
- Vite production build: 이번 작업 환경에서는 전체 프로젝트와 node_modules가 없으므로 미실행
- `run-dev.ps1`: 사용자 PC의 전체 프로젝트가 아니므로 미실행
- 실제 KRX 호출: 범위 밖이며 미실행

## 완료 기준
코드/회귀 관점의 B.2.3.1 변경은 완료했다. 최종 실제 앱 확인은 사용자 PC에서 다음을 확인한다.
- 1920 / 1440 / 1024 가로 스크롤 없음
- 후보 5개 비교 정상
- 후보 선택 시 상세 1개만 변경
- 새 분석 첫 후보 자동 선택
- F5/상세 복귀 후 선택 후보 복원
- Historical 기본 접힘
- 후보 없음 안내에서 NO_TRADE 비노출
- 가격 영역 잘림 없음
- 한국어 세로 깨짐 없음
