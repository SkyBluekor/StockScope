# WORKSPEC v0.21.4-B.2.3.2d — Target1 Production Policy Correction

## 1. 목적
B.2.3.2c 20-date smoke 결과에서 현재 구조형 Target1보다 `CAP_1_5R` 정책이 더 현실적인 1차 목표 후보로 확인되었다. 이번 단계는 연구용 비교가 아니라 Production Target1 정책을 아래와 같이 변경한다.

```text
Target1 = min(nearest structural target, Entry + 1.5R)
```

구조 목표가 없으면 기존과 동일하게 1.5R fallback을 사용한다.

## 2. 근거
B.2.3.2c smoke:
- 20 valid dates / 324 signals
- CURRENT 20D Target-first: 32.0988%
- CAP_1_5R: 41.0494%
- FIXED_1_5R: 38.5802%
- 20%+ 또는 4R+ 극단 Target: 68건, CURRENT Target-first 14.7059%
- verdict: `CAP_1_5R_REVIEW`

한미사이언스 `008930`, 2026-09-18 재현값:
- Entry 48,500
- Invalidation 46,025.04
- Risk 2,474.96
- resistance/high20 61,000
- legacy Target1 61,000 = 5.05R
- 1.5R = 52,212.44

## 3. Production 정책
- 가장 가까운 유효 `resistance_price/high20`을 structural Target1으로 선정한다.
- structural Target1 <= 1.5R: 구조 목표를 그대로 Target1으로 사용한다.
- structural Target1 > 1.5R: Target1만 1.5R로 제한한다.
- structural Target1 없음: 기존 1.5R fallback을 유지한다.
- cap 적용과 fallback은 별도 metadata로 구분한다.

## 4. Target2 불변
Target2 공식은 이번 작업의 검증 대상이 아니므로 결과를 변경하지 않는다.

기존 공식:
```text
target2 = max(entry + 2R, legacy_target1 + 0.5R)
```

Target1 cap 적용 후에도 Target2 계산에는 cap 전 legacy Target1을 사용한다. 따라서 한미사이언스 Target2 약 62,237.48원은 유지된다.

## 5. 설명 metadata
RiskPlan/Entry Risk Guide에 다음 정보를 보존한다.
- `structural_target1_price`
- `structural_target1_basis`
- `target1_cap_price`
- `target1_cap_applied`
- `target1_fallback_used`

cap 적용 시 Target1 basis는 `1.5R 현실성 상한`으로 표시하고 기존 구조 목표는 별도로 노출한다.

## 6. Cache/version
Target1은 Scanner decision field이므로:
- Scanner VERSION `0.21.3.5 -> 0.21.3.6`
- Browser Scanner decision version `0.21.3.5 -> 0.21.3.6`
- Session schema는 `2` 유지

Target1 변경은 Historical Evidence의 과거 outcome에도 영향을 주므로 stale evidence 재사용을 막기 위해:
- `HISTORICAL_EVIDENCE_POLICY_VERSION v1 -> v2`

## 7. 변경 금지
이번 단계에서 아래는 변경하지 않는다.
- Strategy 선택/점수/Ranking
- Quick18 / Market160
- Entry / Invalidation / Stop zone
- resistance / high20 계산
- Target2 정책
- Exit 정책
- MA120 / Market RS / Sector RS
- Historical Evidence 입력/선정 정책 자체

## 8. 완료 조건
- structural <= 1.5R이면 기존 구조 Target 유지
- structural > 1.5R이면 Target1=1.5R
- 구조 목표 없으면 기존 1.5R fallback
- resistance == high20 동가에서는 resistance source 우선 유지
- 한미사이언스 Target1 약 52,212.44 / RR1 1.50
- 한미사이언스 Target2 약 62,237.48 / RR2 약 5.55 유지
- B.2.3.2c CAP 공식과 Production parity
- Scanner/session/evidence caches 새 버전으로 분리
- Backend focused tests PASS
- Frontend TypeScript/full build 확인
