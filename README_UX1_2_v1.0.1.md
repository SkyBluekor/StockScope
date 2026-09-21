# StockScope UX.1.2 v1.0.1 — Source Discovery / Preflight Hotfix

이 패치는 UX.1.2 Action-First Information Hierarchy 적용 스크립트의 사전검사 가정을 수정합니다.

## 수정한 적용 스크립트 문제

이전 v1.0은 `frontend/src/App.tsx` 안에 렌더링된 제목 `10가지 투자 방법 자동 비교`가 하나의 연속 문자열로 존재한다고 가정했습니다. 현재 checkout에서는 화면 구조가 분리되거나 JSX가 나뉘어 있을 수 있으므로, 실제 화면이 존재해도 preflight가 중단될 수 있었습니다.

v1.0.1은:
- 종목 과거 성과 화면을 `frontend/src/**/*.tsx`에서 여러 독립 앵커로 자동 탐색합니다.
- 페이지 제목의 연속 문자열을 preflight 필수조건으로 사용하지 않습니다.
- 제목이 nested JSX로 나뉘어 있어도 semantic H1 탐색을 시도합니다.
- Scanner 제어 제목이 현재 소스처럼 `<strong>`인 경우를 처리합니다.
- RecommendationTracking 상단 설명 문구의 알려진 변형을 모두 처리합니다.
- 모든 preflight는 실제 소스 변경 전에 수행합니다.

## 검증
- ScannerPanel B.2.4a + UX.1.1 상태에서 UX.1.2 patch 함수 적용 확인
- RecommendationTracking 최신 보유 source에 patch 함수 적용 확인
- EmbeddedScanner 최신 보유 source에 patch 함수 적용 확인
- SimulationWorkspace 최신 보유 source에 patch 함수 적용 확인
- 제목이 `<h1>10가지 투자 방법 <em>자동 비교</em></h1>`처럼 분할된 synthetic historical JSX에서:
  - 3단계 rail 제거
  - 설정을 전략 설명보다 앞으로 유지
  - 전략 설명 접힘 이동
  - 실행 버튼 copy 변경
  확인
- Python `py_compile` PASS

## 적용
프로젝트 루트에서:

```powershell
python .\apply_ux1_2_action_first.py
```

이전 실패는 preflight 단계였으므로 UX.1.2 소스 변경은 적용되지 않은 상태입니다.
