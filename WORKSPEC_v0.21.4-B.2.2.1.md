# v0.21.4-B.2.2.1 — Global Dark Theme System Audit & Regression Fix

## 목적
StockScope 전체 Frontend에서 기능 추가 시 다시 등장하는 흰색/연회색 surface 회귀를 제거하고, 신규 컴포넌트가 기본적으로 동일한 다크 테마를 사용하도록 공통 Theme Token 체계를 고정한다.

## 핵심 변경
- 기존 정상 다크 톤을 기준으로 `:root`를 dark-first canonical token 체계로 전환한다.
- `--bg-page`, `--bg-surface`, `--bg-surface-raised`, `--bg-surface-soft`, `--bg-input`, border/text/status/accent token을 정의한다.
- 기존 `--surface`, `--line`, `--text-*` 계열은 호환 alias로 유지해 대규모 컴포넌트 회귀를 막는다.
- CSS 전체에서 밝은 surface/background 및 밝은 border 하드코딩을 dark token/status token으로 치환한다.
- 중립 텍스트 하드코딩은 공통 text token으로 통합한다.
- input/select/textarea/option의 native 기본 표면도 dark token을 기본값으로 사용한다.
- B.2.2 수익 보호 UI와 B.2.1.12 Research Workspace가 동일 Theme Token을 사용하도록 유지한다.

## 회귀 방지
`frontend/tests/darkThemeRegression_v0214b221.ts`를 추가한다.
- 필수 Theme Token 존재 확인
- dark-first `color-scheme` 확인
- CSS background/border에 밝은 surface literal 재유입 검사
- TS/TSX inline bright surface 검사
- `var(--surface, #fff)` 같은 라이트 fallback 검사
- B.2.2 수익 보호 영역의 token 사용 확인

## 범위
- Frontend 스타일 시스템과 표현만 변경한다.
- 전략/Risk/가격/Scanner ranking/Backtest/Production 정책/수익 보호 계산 로직은 변경하지 않는다.
- Light theme/toggle은 추가하지 않는다.
- 빠른 조회의 긴 정보 구조 자체는 다음 별도 UX 작업으로 남긴다.

## 완료 기준
1. 페이지 중간에 흰색/연회색 대형 surface가 나타나지 않는다.
2. 밝은 surface/background 및 밝은 border 정적 검사가 0건으로 통과한다.
3. 신규 폼 컨트롤도 dark surface를 기본 상속한다.
4. Profit Protection / Research Workspace 등 최근 기능도 동일 테마를 사용한다.
5. Dark Theme regression test가 통과한다.

## 패키징
현재 작업 명세 `WORKSPEC_v0.21.4-B.2.2.1.md`만 포함하고 이전 WORKSPEC은 제외한다.
