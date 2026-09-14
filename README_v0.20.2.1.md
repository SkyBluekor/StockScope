# StockScope v0.20.2.1 — Dark UI & Layout Polish

기준 버전: **v0.20.2 Visual & Concrete Action UX**

## 목적

v0.20.2에서 추가한 다크모드/폰트 확대를 실제 백테스트 화면에서 다시 다듬습니다.
이번 버전은 계산 엔진을 바꾸지 않고 **색상 통일, 입력 UI, 전략 배치, 반응형 레이아웃**만 수정합니다.

## 변경 사항

- 백테스트 본문 최대 폭을 1320px로 제한하고 가운데 정렬
- `이 기능으로 무엇을 해결하나요?` 설명을 위에 두고 10개 전략을 아래 Grid로 재배치
- 전략 카드 반응형: 대형 화면 5열, 1280 전후 4열, 1024 전후 2열
- 다크모드 입력창/검색창/날짜/숫자 입력을 네이비·슬레이트 계열로 통일
- 검증 종목 영역의 흰색 배경 제거
- 최대 보유기간의 선택 항목을 흰색 대신 어두운 블루 계열로 변경
- 설정/결과 단계 탭에 다크모드용 선택 상태 추가
- hover/focus/검색 결과 배경을 테마 변수로 통일
- Light/Dark 공통 테마 변수 누락 및 자기참조 변수 수정
- 폰트 확대 상태에서도 Grid/입력/버튼이 밀리지 않도록 `min-width: 0`, 내용 기반 높이, 반응형 규칙 보강

## 수정 파일

- `frontend/src/styles.css`
- `frontend/src/components/BacktestPanel.tsx` — 표시 버전만 v0.20.2.1로 갱신
- `docs/dark-ui-layout-polish-v0.20.2.1.md`

## 변경하지 않은 것

- 백테스트 계산식
- 10개 전략 조건
- Strategy Selector
- Risk Engine
- KRX/OpenDART 호출 로직
- API schema

## 검증

- TypeScript 5.8 `transpileModule` TSX 구문 검사 통과
- `tinycss2` 전체 CSS 파싱 오류 0건
- Chromium 대표 DOM 렌더링으로 1920 / 1440 / 1366 / 1280 / 1024px 확인
- 위 해상도에서 `documentElement.scrollWidth === clientWidth` 확인
- Dark mode 측정값
  - 검증 종목 wrapper: `rgb(29, 38, 50)`
  - 입력창: `rgb(17, 25, 36)`
  - 선택된 보유기간: `rgb(32, 52, 81)`
- 1440px Light mode 대표 화면도 확인

> 전체 원본 프로젝트와 `node_modules`가 없는 overlay 작업 환경이므로 실제 Vite production build 전체 실행은 하지 않았습니다.
