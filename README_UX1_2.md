# StockScope UX.1.2 — Action-First Information Hierarchy

UX.1.1 적용 완료 상태에서 실행합니다.

## 적용
프로젝트 루트에서:

```powershell
python .\apply_ux1_2_action_first.py
```

스크립트는 소스를 수정하기 전에 `.venv`/pytest/npm/UX.1.1 마커를 먼저 검사합니다.
실패 시 이번 작업에서 건드린 파일만 원래 바이트로 롤백합니다.

## 핵심 변경
- 종목 후보 찾기: 3단계 pill 제거, 설명용 카드 제거, 시장 선택/후보 찾기 중심으로 압축
- 종목 과거 성과: 3단계 pill 제거, 설정을 먼저 노출, 10개 전략 목록을 접힘 보조 영역으로 이동
- 종목 성과 추적: 반복 제목/긴 빈 상태 문구 축소
- 전략 성과 검증: 큰 개발상태/실행정책 카드 제거, 설정 + 저장을 한 흐름으로 통합

Backend/DB/Scanner 계산/Ranking/Risk/Entry/Stop/Target/TRACK 동작은 변경하지 않습니다.
