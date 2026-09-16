# v0.21.4-B.2.2.2a — Strategy Tab Layout Hotfix

## 목적
B.2.2.2 가독성 개선 후 선택 전략 상세 영역이 기존 `.strategy-row`의 3열 Grid를 상속하면서 본문이 42px 순위 열에 들어가 한글이 한 글자씩 세로로 분리되는 회귀를 수정한다.

## 실제 원인
- 기존 `.strategy-row`: `42px minmax(0,1fr) 94px`
- B.2.2.2에서 선택 전략 상세는 순위 셀을 제거했지만 동일 `.strategy-row` 클래스를 재사용했다.
- CSS Grid 자동 배치 때문에 첫 번째 실제 자식 `.strategy-info`가 42px 열에 들어갔다.
- `.strategy-score`는 기존 반응형/배치 규칙 영향을 받아 본문보다 안정적인 폭을 유지해 증상이 더 심하게 보였다.

## 수정
- `.strategy-detail-selected .strategy-row`를 `본문 + 점수` 전용 2열 Grid로 재정의한다.
- 본문 `minmax(0,1fr)`, 점수 `minmax(104px,120px)`.
- 선택 전략 내부에서 기존 `.strategy-score`의 `grid-column` 강제 배치를 무효화한다.
- 전략명/조건/설명은 `word-break: keep-all`, `overflow-wrap: break-word`를 사용한다.
- 700px 이하에서는 선택 상세를 1열로 전환한다.
- 폰트 크기, 전략 점수, 조건 계산, 전략 정렬은 변경하지 않는다.

## 회귀 방지
`frontend/tests/strategyLayoutRegression_v0214b222a.ts`를 추가해 다음을 검사한다.
- 선택 상세 2열 Grid 존재
- 점수 영역 legacy grid-column 해제
- 한글 `keep-all`
- `break-all` / `overflow-wrap:anywhere` 재유입 금지
- 700px 이하 1열 전환 규칙 존재

## 제외
Backend/API/전략 로직/Risk/Scanner ranking/Backtest/전역 Typography/Dark Theme 재작업은 하지 않는다.

## 완료 기준
`박스권 매매`, `4/6개 조건 충족`, 긴 한국어 전략 설명이 정상적인 가로 문장으로 표시되고, 좁은 화면에서는 글씨 축소가 아니라 1열 레이아웃으로 전환되어야 한다.
