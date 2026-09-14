# v0.20.3 KRX API Budget & Historical Market Store

데이터 준비를 `SQLite market store -> 기존 GZIP cache -> KRX network` 순서로 변경했습니다.

핵심 불변식:
1. 전략 계산 단계에서는 KRX를 호출하지 않습니다.
2. 같은 시장+날짜의 stock bulk 응답은 모든 종목이 공유합니다.
3. 실제 HTTP 재시도도 Budget 사용량에 포함합니다.
4. 안전 상한을 넘을 것으로 예상되면 네트워크 동기화를 시작하지 않습니다.
5. 중간까지 저장한 날짜는 다음 실행에서 재사용합니다.
6. 당일/최근 빈 응답은 영구 휴장 데이터로 고정하지 않습니다.
