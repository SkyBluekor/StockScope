# UX.1 — Feature Orientation & Tab Guidance

목적: StockScope의 주요 화면에서 사용자가 5초 안에 “무엇을 하는 곳인지 / 무엇을 하면 되는지 / 결과가 어디에 쓰이는지” 이해하도록 안내 문구와 용어를 정리한다.

## 변경 범위
- `종목 추적` 사용자 표시명 → `종목 성과 추적`
- 종목 찾기: 현재 Scanner 후보를 찾는 화면임을 설명
- 종목 성과 추적: 선택 종목의 이후 성과를 쌓아 Scanner 개선 자료로 쓰는 화면임을 설명
- 과거 전략 검증: 개별 종목 추적이 아니라 Scanner 전략 전체를 과거 시장에서 평가하는 연구 기능임을 설명
- 빠른 조회 / 종목별 과거 근거: 해당 화면의 제목을 찾을 수 있는 현재 App 구조에서는 짧은 역할 설명을 추가
- 추천 / 직접 / 추천·직접 출처 정의 표시
- 기준가 / 현재 / 최대 상승 / 최대 하락 헤더에 짧은 도움말 추가

## 변경하지 않음
- Backend / DB
- Scanner 알고리즘
- TRACK.1 D+1 성과 계산
- same-baseline merge
- ACTIVE/CLOSED lifecycle
- Historical Validation 실행 엔진

## 적용
프로젝트 루트(`D:\Projects\StockScope`)에서:

```powershell
python .\apply_ux1_feature_orientation.py
```

적용 스크립트는 기존 TRACK regression, frontend production build, TRACK frozen baseline verifier를 실행하며 실패하면 이번 UX 변경만 롤백한다.


## v1.0.1 precheck hotfix
- Current compact ScannerPanel has no stable page heading.
- Scanner guidance is now inserted at the App.tsx ScannerPanel mount boundary.
- Quick lookup / historical evidence nav items receive native tooltips instead of relying on nonexistent headings.
- No backend, DB, Scanner algorithm, or TRACK behavior changes.
