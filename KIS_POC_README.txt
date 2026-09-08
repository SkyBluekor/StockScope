StockScope KIS Read-Only PoC v0.2

포함 기능
- 사용자 BYOK App Key / App Secret 연결 테스트
- 자격증명은 디스크/DB에 저장하지 않고 FastAPI 프로세스 메모리에만 임시 유지
- 브라우저에는 임시 session_id만 sessionStorage에 저장
- 국내주식 현재가 조회
- 국내주식 기간별 일봉 조회
- KIS 호출 경로 Allowlist 적용
- 실제 매수/매도/정정/취소 주문 API 미구현 + 비허용 Endpoint 차단 테스트

적용 방법
1. 실행 중인 run-dev.ps1 창 두 개를 Ctrl+C로 종료
2. 이 압축파일의 내용을 D:\Projects\StockScope 에 덮어쓰기
3. 프로젝트 루트에서 .\setup.ps1 실행 (기존 환경이면 빠르게 완료됨)
4. .\run-dev.ps1 실행
5. http://localhost:5173 접속
6. 본인의 KIS App Key / App Secret 입력 → 연결 테스트
7. 005930 현재가 + 일봉 조회 확인

주의
- 실제 API 키를 Git에 커밋하지 마세요.
- App Key / App Secret은 채팅에 보내지 마세요.
- 이 버전은 PoC이며 주문/계좌/잔고 API를 호출하지 않습니다.
