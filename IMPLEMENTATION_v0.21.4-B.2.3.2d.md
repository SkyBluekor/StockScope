# IMPLEMENTATION v0.21.4-B.2.3.2d

## 구현 내용
- `backend/app/risk/target1_policy.py` 추가
  - Target1 cap/fallback 결정을 한 곳에서 수행
  - structural target metadata와 legacy target을 함께 반환
- `backend/app/risk/engine.py`
  - Production Target1을 `min(structural, 1.5R)`로 변경
  - Target2는 cap 전 legacy Target1으로 계산해 기존 값을 보존
  - cap 적용 이유를 설명 trace에 추가
- `backend/app/risk/models.py`
  - structural Target1 / cap metadata 추가 및 직렬화
- `backend/app/backtest/target1_audit.py`
  - 새 Production 공식으로 독립 재검산
  - `RISK_1_5R_CAP`과 fallback을 구분
  - 구조 목표 trace 유지
- `backend/app/backtest/entry_risk_guide.py`
  - 새 metadata와 KRX 표시가격을 UI payload로 전달
- Frontend
  - cap이면 `1.5R 현실성 상한` 표시
  - 기존 구조 목표 가격/근거를 함께 표시
  - API type 확장
- Scanner
  - decision version `0.21.3.6`
  - Historical Evidence policy cache `v2`
  - frontend Scanner decision session `0.21.3.6`, schema `2` 유지

## 한미사이언스 fixture
`008930`, 2026-09-18 조건:
- Entry: 48,500
- Invalidation: 46,025.04
- Structural: 61,000
- New Target1: 52,212.44
- RR1: 1.50
- Target2: 62,237.48 (불변)
- RR2: 5.55 (불변)

## 검증 수행
- Python `py_compile`: PASS
- focused pytest: 10/10 PASS
- isolated TypeScript strict compile (`api.ts`, `EntryRiskGuideCard.tsx`, `scannerSession.ts` + dependency): PASS
- 실제 전체 사용자 repo frontend build: 이 환경에서는 실행하지 못함
- 실제 사용자 Market Store/브라우저 integration: 적용 후 사용자 PC에서 확인 필요

## Production 영향
의도적으로 변경:
- Target1 / reward1 / rr1
- Target1 설명 metadata
- Scanner 및 Historical Evidence cache version

변경하지 않음:
- Target2 / reward2 / rr2
- Entry / Invalidation / Stop
- Strategy / Ranking / candidate selection
- resistance/high20 계산
