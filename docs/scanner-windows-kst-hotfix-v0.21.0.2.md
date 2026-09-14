# Scanner Windows KST hotfix v0.21.0.2

StockScope는 KRX 일일 API budget 날짜 구분과 최신 날짜 캐시 정책에 한국 현지 날짜가 필요합니다.
Windows Python에서 IANA tzdata가 없는 경우 `ZoneInfo("Asia/Seoul")`가 실패할 수 있으므로,
공통 helper가 Asia/Seoul을 우선 사용하고 사용할 수 없을 때 UTC+9 고정 KST로 fallback합니다.

이 경로는 현재 시점의 KRX 날짜/시간 판정에만 사용되며 투자 전략 계산 기준은 변경하지 않습니다.
