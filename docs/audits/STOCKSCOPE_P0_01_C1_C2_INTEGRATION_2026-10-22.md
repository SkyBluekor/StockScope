# StockScope P0-01 — C1/C2 선별 통합 명세·변경 기록

- 기준 원격 main SHA: `4d057183de59fadf841663f3038bdce3a0bb3463`
- 선택한 제품 변경 원본 SHA: `ce815f8ff89332d534fab8b0e17580b311e5cbf4` (누적 PR #163)
- 목적: Scanner·Holdings의 사용자 과업 화면과 데이터 출처/위험 설명 통합. 동일 릴리스 검증이 끝나기 전 MVP 완료 주장은 금지.

## 포함
- C1: #148–149의 후보 근거/동률/기준일, #159–161의 기존 Risk 참고선/시세 제공 시점/보유 원장 구분.
- C2: #162–163의 보유 보호 요약/적용 계획과 제안 구분/Watch 미승인 표시.
- 프런트엔드의 필요한 imports, shared helpers, CSS, API types, Node 회귀 6종 및 변경된 기존 Backend 정적 화면 계약 검사.
- 기존 CI Python 3.11/3.14, Node 22, Windows clean setup 구조는 그대로 두고 신규 Node 테스트만 추가.

## 제외·보존
- JEV 외부 유료 호출·real market data outbound·기존 S6 합성 제한 해제·V4 로컬 skip 조작 없음.
- #150–158 연구용 Python CLI/collector, #159 연구용 10/14 고정 분석 Python 변경, #164–168 JEV 고급·합성 UI는 제외.
- 원격 main에 이미 있는 Scanner/Strategy/Risk, Holdings/Watch, Simulation, JEV API/코드·DB schema는 변경하지 않음.
- 별도 #169의 P0-07 G0 계약은 이 통합 PR에 복제하지 않음. 기존 PR 및 원본 branch의 폐기/병합 없음.

## 검증 및 종료 조건
- 동일 통합 SHA에서 4개 CI job과 6개 Node 회귀 PASS 확인 후에만 GitHub 통합 후보 검증을 완료로 판정.
- 이 CI는 PC의 `D:\Projects\StockScope`에서 실제 EOD 확보, Scanner 재검증, 보유 계획 저장·복원, TypeSafe 실사용 UAT 증거가 아님.
- 운영 Market DB·사용자 Holdings DB·Tracking 원장·기존 capture identity 변경 금지.
- 이어지는 범위: P0-02 최신 운영 데이터, P0-03 현재 재판단, P0-04 보유 계획, P0-05 성과 관측, P0-07/08 TypeSafe 실제 연결.
