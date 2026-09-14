# StockScope v0.21.0.2 — Windows KST Runtime Hotfix

## 문제
Scanner 시작 직후 Windows/Python 환경에서 다음 오류가 발생할 수 있었습니다.

`No time zone found with key Asia/Seoul`

KRX API Budget 및 KRX Provider가 `ZoneInfo("Asia/Seoul")`을 직접 사용했지만,
일부 Windows Python 설치에는 IANA timezone database가 기본 포함되지 않기 때문입니다.

## 수정
- `backend/app/market/kst.py` 추가
- IANA `Asia/Seoul`이 있으면 그대로 사용
- 없으면 KST 고정 UTC+9 timezone으로 자동 fallback
- KRX Budget 날짜/시각 계산과 KRX Provider의 오늘 날짜 계산이 공통 KST helper를 사용
- Scanner version을 `0.21.0.2`로 올려 이전 Scanner 결과 캐시와 구분

## 변경하지 않은 것
- Scanner 후보 선정 규칙
- Strategy Engine
- Risk Engine
- KRX API Budget 8,000회 정책
- Scanner Fast Budget 60회 정책
- UI/진행률 구조

## 적용
v0.21.0.1 적용 상태에서 이 overlay를 프로젝트 루트에 덮어씁니다.
그 후 서버를 재시작하고 `종목 찾기 → 오늘의 후보 찾기`를 다시 실행합니다.

## 검증
- Python compileall 통과
- timezone fallback 격리 테스트 2개 통과
- 누적 overlay 테스트 환경은 일부 과거 공통 모듈이 없어 전체 pytest 수집은 불가능했음
