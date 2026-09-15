# Scanner Price Plan & Entry Position Clarity

사용자 화면에서 `0.0%`를 보여주는 대신 가격 관계를 직접 설명한다.

- RANGE 내부: `현재가가 관심 구간 안에 있습니다.`
- RANGE 아래: `관심 구간까지 N원 남았습니다.`
- RANGE 위: `관심 구간보다 N원 높습니다.`
- Breakout 전: `돌파 기준까지 N원 남았습니다.`
- Breakout 후: `돌파 기준을 N원 넘었습니다.`

Ranking 엔진은 기존 `entry_gap_pct`를 내부 정렬에 계속 사용하며 이 버전은 정렬 정책을 변경하지 않는다.
