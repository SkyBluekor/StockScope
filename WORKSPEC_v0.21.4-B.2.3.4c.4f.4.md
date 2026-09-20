# v0.21.4-B.2.3.4c.4f.4 — Sector-aware RS Counterfactual

## 목적
c.4f.3에서 확보한 audit-only Sector RS를 Production에 활성화하지 않은 채 StrategyInput 복사본에만 주입하여, 실제 업종 상대강도가 존재할 때 Breakout RS 구조를 동일 입력에서 비교한다.

## 비교 구조
- Production baseline: Sector RS `None` → 기존 market fallback
- `RS_AUDIT_CURRENT_6_4_8`: 실제 audit Sector RS + 현재 6+4+8 구조
- `RS_AUDIT_KEEP_4`: 같은 Sector RS + 6+4
- `RS_AUDIT_KEEP_8`: 같은 Sector RS + 6+8
- `RS_AUDIT_RESTORE_10_8`: 같은 Sector RS + 10+8

모든 Sector-aware variant는 같은 `relative_strength_sector_pct` 입력을 사용한다. 데이터 입력 효과와 가중치 구조 효과를 섞지 않는다.

## Temporal Gate
OpenDART `industry_code`는 현재 `STATIC_CURRENT`로 분류된다. 따라서 이번 계산은 audit-only이며 Production StrategyInput에는 주입하지 않는다. `POINT_IN_TIME` provenance가 확인되기 전에는 Production 활성화를 허용하지 않는다.

## 측정
- real Sector RS 주입 성공 수
- market/sector 부호 불일치 수와 비율
- 현재 6+4+8의 Production fallback 대비 Breakout score 변화
- 현재 6+4+8의 Production fallback 대비 선택 전략 변화
- Sector-aware CURRENT 대비 KEEP_4 / KEEP_8 / RESTORE_10_8의 Quick18/Top5 membership/order 변화
- full 모드에서는 동일 Top5 미래 outcome delta

## 금지 범위
- Production StrategyEngine 가중치 수정 금지
- Sector fallback 정책 수정 금지
- Ranking / Quick18 / Quick36 / Market160 수정 금지
- Risk / Entry / Stop / Target / Exit 수정 금지
- MA120 수정 금지
- 현재 OpenDART 업종코드를 point-in-time 데이터로 간주 금지

## 완료 Gate
1. audit Sector RS가 StrategyInput 복사본에만 주입됨
2. Production activation flag는 false 유지
3. 모든 Sector-aware weight variant가 동일 Sector input을 사용함
4. no-lookahead c.4f.3 gate 유지
5. 기존 c.4f/c.4d/scanner 회귀 테스트 통과
6. 고정 historical sample에서 결과 수집 후 c.4g 정책 판단으로 넘김
