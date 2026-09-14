# StockScope v0.21.0.3 — Scanner Market Bootstrap Performance

## 적용 순서
이 overlay는 `v0.21.0.2`까지 적용된 StockScope 프로젝트 위에 덮어씁니다.

## 수정 파일
- `backend/app/backtest/scanner.py`
- `backend/app/market/providers/krx.py`
- `backend/tests/test_scanner_bootstrap_performance_v02103.py`
- `frontend/src/components/ScannerPanel.tsx`
- `frontend/src/services/api.ts`
- `docs/scanner-market-bootstrap-performance-v0.21.0.3.md`

## 핵심
새 PC 최초 Scanner 데이터 준비에서 날짜별 KRX 요청을 하나씩 기다리지 않습니다.

- 시작 동시 처리 8
- 정상 시 최대 12까지 증가
- retry/오류 시 최소 4까지 자동 감속
- KOSPI/KOSDAQ을 포함한 KRX Provider 전체 최대 동시 네트워크 요청 12
- HTTP connection pool 재사용
- Budget SQLite / gzip cache / Market Store 저장 때문에 event loop가 멈추지 않도록 I/O 분리
- 완료된 날짜는 즉시 보존하여 중단 후 다시 실행해도 남은 날짜만 처리

## 화면에서 확인할 값
시장 데이터 준비 중:
- `처리 224 / 314`
- `처리 속도 7.4건/초`
- `예상 남은 시간 약 12초`
- `동시 처리 10 / 10`
- `실제 KRX 요청 224회`

## 테스트
새 PC 또는 누락 기간이 많은 상태에서 `시장 데이터 준비 시작`을 실행합니다.

확인:
1. 동시 처리 값이 8 부근에서 시작하는지
2. 정상 응답이 이어지면 9~12까지 증가하는지
3. 진행률이 계속 움직이는지
4. 처리 속도와 예상 남은 시간이 표시되는지
5. 중간 종료 후 재실행하면 이미 받은 날짜를 다시 받지 않는지
6. 완료 후 다시 Scanner를 실행하면 KRX 요청이 거의 0인지

## 검증 범위
- 변경 Python 파일 compile 통과
- adaptive concurrency 격리 스모크 테스트: 초기 8 → 최대 12, 120개 처리 완료
- retry 신호 격리 테스트: 동시 처리 자동 감속 확인
- Provider 글로벌 12개 동시 요청 제한 격리 테스트 확인
- TS/TSX transpile syntax diagnostics 0건

전체 StockScope 원본 프로젝트의 전체 pytest/Vite production build는 현재 누적 overlay 작업 환경에서 수행하지 못했습니다.
