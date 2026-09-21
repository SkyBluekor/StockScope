# StockScope TRACK.1.10 + SIM.VAL.0.1

목적: 종목 추적을 독립 기능으로 완성하고, 과거 전략 검증 설정을 실제 저장/관리 가능한 DRAFT 카탈로그로 만든다.

## 주요 변경
- 종목 추적 화면에서 Scanner 실행 없이 종목명/코드 검색 → 추적 시작
- Scanner 추천 후보 전체 접근(Frontend slice 제거), 실제 후보 개수 표시
- 종목 검색 / Scanner 추천 / 추적 목록을 한 화면에서 항상 확인
- CLOSED 추적 기록 삭제, ACTIVE는 먼저 종료
- 과거 전략 검증 이름/대상/시장/기간을 DRAFT로 저장
- 저장된 검증 목록/상세/삭제
- Legacy Simulation 별도 표시/상세/안전 삭제(연결 기록 있으면 409 차단)
- Production Scanner 알고리즘/추천 개수/Ranking/Strategy는 변경하지 않음
- Historical Execution Engine은 아직 연결하지 않음

## 적용
StockScope 프로젝트 루트에서:

```powershell
python .\apply_track110_simval01.py
```

실패 시 이번 패치가 변경한 파일만 원복한다.
