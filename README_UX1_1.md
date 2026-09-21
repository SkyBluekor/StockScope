# UX.1.1 — Intuitive Information Architecture

목표: 설명문을 위에 별도 블록으로 붙이는 방식 대신, 메뉴명/페이지명/버튼명만 봐도 기능을 이해할 수 있게 정리합니다.

## 변경
- 빠른 조회 → 종목 분석
- 종목별 과거 근거 → 종목 과거 성과
- 종목 찾기 → 종목 후보 찾기
- 종목 성과 추적 유지
- 과거 전략 검증 → 전략 성과 검증
- Scanner 상단에 따로 붙은 UX.1 설명 블록 제거
- Scanner의 `STOCK SCANNER` eyebrow → `종목 후보 찾기`
- 종목 성과 추적 설명은 기존 헤더 안의 한 문장으로 축소
- 과거 전략 검증 설명은 기존 헤더 안의 한 문장으로 축소
- 별도 흐름 설명/출처 설명 블록 제거
- 추천/직접 의미는 필터 hover title로 이동
- Tracking의 탭 사이 별도 설명문 제거

## 변경하지 않음
- Backend
- DB
- Scanner 알고리즘/Ranking/Risk/Entry/Stop/Target
- TRACK.1 frozen 동작
- Historical Validation 실행 엔진

## 적용
StockScope 루트에서:

```powershell
python .\apply_ux1_1_intuitive_labels.py
```

기존 TRACK 회귀 테스트, frontend build, TRACK frozen baseline을 통과해야 적용됩니다.
실패하면 이번 UX.1.1 변경만 롤백합니다.

Scanner Production baseline mismatch는 기존 상태이므로 report-only입니다.
