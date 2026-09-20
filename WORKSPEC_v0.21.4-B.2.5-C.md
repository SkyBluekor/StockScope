# Workspec — v0.21.4-B.2.5-C

목적: READY 상단 후보의 score saturation으로 종목코드가 사실상 순위를 결정하는 문제를 줄이되 기존 Production 우선순위의 의미를 보존한다.

결정:
1. 기존 priority components를 먼저 전부 비교한다.
2. 모든 base component가 같은 exact tie에서만 추가 판단한다.
3. 기존 RiskPlan의 structural Target1까지 거리가 가장 가까운 후보 1개만 우선한다.
4. 나머지는 기존 stock-code stable order를 유지한다.
5. Structural Target이 없으면 정책을 만들지 않고 code fallback한다.
6. Historical Evidence와 미래 outcome은 Production Ranking 입력으로 사용하지 않는다.
7. 정책 변경이므로 Scanner decision version을 bump한다.
