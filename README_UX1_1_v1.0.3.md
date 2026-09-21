# UX.1.1 v1.0.3 — Runtime DB Portability Hotfix

이 hotfix는 UX.1.1 적용 검증이 특정 PC의 로컬 Tracking runtime DB 존재 여부에 묶여 있던 문제를 수정합니다.

## 원인
학교 PC에는 다음 DB가 있었지만 홈 PC에는 아직 없습니다.

`backend/runtime/tracking/recommendation_tracking.db`

기존 적용 스크립트는 UX-only 변경임에도 `verify_tracking_baseline.py`를 무조건 REQUIRED로 실행해, 소스 테스트와 frontend build가 모두 통과한 뒤 로컬 DB가 없다는 이유만으로 전체 패치를 롤백했습니다.

## 수정
- Tracking runtime DB가 **있으면** 기존처럼 frozen runtime baseline verifier를 REQUIRED로 실행합니다.
- Tracking runtime DB가 **없으면** 명확한 SKIP 메시지를 출력하고 계속 진행합니다.
- DB가 존재하는데 verifier가 실패하면 여전히 적용 실패/롤백합니다.
- TRACK 관련 source/backend 회귀 테스트와 frontend production build는 계속 필수입니다.
- Scanner production baseline은 기존처럼 report-only입니다.

즉, 기기별 로컬 runtime 데이터가 없다는 이유로 순수 frontend UX 패치를 실패시키지 않습니다.

## 변경하지 않음
- Backend 로직
- DB 생성/복사/초기화
- Scanner 알고리즘
- TRACK.1 도메인 동작
- UX.1.1 화면 변경 내용

## 적용
StockScope 루트에서:

```powershell
python .\apply_ux1_1_intuitive_labels.py
```
