# v0.21.4-B.2.2.2 — Typography & Readability System Restoration

## 목적
B.2.2.1 이후 남은 초소형 폰트, 좁은 행간/여백, 과도한 정보 밀도를 복구한다. 100% 브라우저 배율에서 핵심 판단·가격·이유를 확대 없이 읽을 수 있어야 하며, 한 화면에 많이 넣기 위해 글자를 줄이지 않는다.

## 핵심 변경
- 전역 typography token: page/result/section/card/body/small/meta/badge 및 line-height 추가.
- 전역 spacing token 추가.
- legacy CSS의 8~13px hard-coded font를 가독성 기준 이상으로 승격.
- 일반 본문 15px, 보조 본문 14px, metadata 13px, badge 12px 계층을 공통 token으로 정의.
- 주요 카드/분석 영역의 padding, gap, line-height를 확대.
- 가격 계획/수익 실현 영역의 본문과 핵심 정책 가독성 보강.
- 표는 글씨를 줄여 맞추지 않고 14px 수준을 유지.
- Sidebar/버튼/상세 펼치기 클릭 영역을 읽고 누르기 쉬운 크기로 유지.

## 전략 10개 영역
기존에는 10개 전략의 이유·자동 점검·대응 기준이 동시에 반복 노출되어 페이지가 매우 길고 조밀했다.
- 10개 전략은 compact selector 목록으로 먼저 표시.
- 전략명, 조건 충족 수, 점수/상태만 목록에서 비교.
- 사용자가 선택한 전략 1개만 상세 내용 표시.
- 자동 점검과 충족/부족 조건은 선택된 전략에만 표시.
- 대응 기준은 기본 접힘 상태로 두고 필요할 때 펼친다.
- 1024px 이하에서는 목록/상세를 세로 배치하며 폰트를 축소하지 않는다.

## Dark Theme 보존
B.2.2.1의 dark theme token과 밝은 surface 회귀 방지 규칙을 유지한다. 가독성 개선을 위해 라이트 카드나 흰 배경을 다시 도입하지 않는다.

## 변경 파일
- `frontend/src/styles.css`
- `frontend/src/App.tsx`
- `frontend/tests/readabilityRegression_v0214b222.ts` (신규)
- `WORKSPEC_v0.21.4-B.2.2.2.md`

## 변경하지 않는 것
- 전략 점수/조건 계산
- Risk/Stop/Target 계산
- Production 매도 정책
- 수익 보호 계산
- Scanner ranking
- Backtest/연구 결과
- Backend API/계산 로직

## 완료 기준
- hard-coded `font-size` 14px 미만 0건(0px decorative 제외); 실제 작은 metadata/badge는 token으로만 관리.
- 주요 본문은 15px / 보조는 14px 계층을 사용.
- 10개 전략 상세 동시 노출 제거, 선택 전략 1개 상세만 표시.
- strategy detail response는 기본 접힘.
- 1100px/700px breakpoint에서 전략 UI가 세로로 재배치되고 폰트를 축소하지 않음.
- Dark Theme regression test 유지.
- TypeScript syntax, CSS parser, readability regression, 기존 관련 regression을 통과.

## 범위 밖
Quick Analysis 전체를 별도 Workspace로 재설계하는 작업은 다음 버전으로 분리한다. 이번 버전은 가독성 시스템 복구와 전략 영역의 기본 노출량 축소까지 수행한다.
