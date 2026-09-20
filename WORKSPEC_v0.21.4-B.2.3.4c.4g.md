# WORKSPEC v0.21.4-B.2.3.4c.4g
## Breakout RS Production Definition Correction — Market 10 + Sector 8

## 목적
80일 Sector-aware 감사에서 확인된 Breakout RS 중복 정의를 Production에서 원래 설계로 복구한다.

- 기존: Market RS 6 + Sector RS 4 + Sector RS 8
- 수정: Market RS 10 + Sector RS 8
- RS 최대 기여도는 18로 유지한다.
- threshold `> 0`과 Sector missing → Market fallback 의미는 유지한다.

## 근거
- 80/80 valid dates.
- Breakout 23,277 evaluations에서 기존 Sector RS 조건 4/8 중복이 확인됨.
- 실제 historical Sector RS audit coverage 23,095/23,277 (99.2181%).
- Market/Sector sign divergence 2,909 (12.5958%).
- 과거 설계 추적 결과 Breakout 의도 구조는 Market 10 + Sector 8.

## Production 변경
1. `backend/app/strategy/engine.py`
   - Market RS weight 6 → 10
   - duplicate Sector RS weight 4 tuple 삭제
   - Sector RS weight 8 유지
2. `backend/app/backtest/scanner.py`
   - Scanner decision/cache version `0.21.3.4` → `0.21.3.5`
3. `frontend/src/components/scannerSession.ts`
   - browser/session decision version `0.21.3.4` → `0.21.3.5`
4. strategy-integrity audit를 post-fix Production 10+8 acceptance 모드로 갱신.

## 변경 금지
- Market/Sector RS 계산식
- RS threshold
- Sector → Market fallback
- Sector benchmark mapping
- MA120
- Market160 / Quick18 / Quick36 / Top3 / Top5
- Ranking / Risk / Entry / Stop / Target / Exit
- 다른 전략 weight

## Temporal safety
Historical Sector RS의 업종 메타데이터는 `STATIC_CURRENT`이므로 Production StrategyInput 활성화 금지를 유지한다.
`production_safe=False` gate를 해제하지 않는다.

## 적용 방식
현재 대화에 전체 `backend/app/strategy/engine.py` 원본 파일이 없으므로 overlay가 해당 파일을 통째로 덮어쓰지 않는다.
대신 AST로 기존 6+4+8 구조를 확인한 뒤 정확히 10+8로 바꾸는 fail-closed patcher를 제공한다.
예상 구조가 아니면 파일을 수정하지 않고 실패한다.

## Acceptance
### Focused
- c.4g patcher idempotence / unknown-shape fail-closed
- Scanner + frontend cache version 0.21.3.5
- audit Production gate = market10 + sector8
- historical Sector activation = false

### 10D
- 10/10 valid
- `c.4g Production RS: verdict=PASS`
- market=[10], sector=[8]
- duplicate=False
- futureViolations=0

### 80D
- 80/80 valid
- 동일 Production acceptance PASS
- duplicate evaluations 0
- historical Sector activation false
- runtime exception 0

성과 개선은 PASS 조건이 아니다. 이번 작업은 튜닝이 아니라 정의 복구다.
