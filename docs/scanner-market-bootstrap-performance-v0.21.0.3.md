# StockScope v0.21.0.3 — Market Bootstrap Performance

## 목적
새 PC에서 Scanner 최초 시장 데이터 준비가 수백 회 KRX 요청 때문에 수 분 걸리는 문제를 줄입니다.
후보 선정 규칙, Strategy Engine, Risk Engine은 변경하지 않습니다.

## 핵심 변경
- Scanner 시장 데이터 준비를 고정 batch 방식에서 **지속형 adaptive concurrency** 방식으로 변경
- 동시 요청: 기본 8개, 최소 4개, 최대 12개
- 정상 응답이 이어지면 단계적으로 동시 처리량 증가
- retry/오류가 발생하면 자동 감속
- KRX Provider 전체에 최대 동시 네트워크 요청 12개 제한
- 공용 `httpx.AsyncClient` connection pool 재사용 유지
- KRX API Budget SQLite 기록과 gzip cache I/O를 event loop 밖으로 이동
- KRX 응답이 끝난 뒤 Market Store SQLite 저장은 별도 writer에서 즉시 수행
- 중간 취소 시 이미 완료되어 writer queue에 들어온 데이터는 보존

## 진행 화면
시장 데이터 준비 중 다음 값을 추가합니다.
- 처리 속도 (건/초)
- 예상 남은 시간
- 현재 동시 처리 / adaptive limit
- 재시도 횟수

## 진단
Scanner 결과의 개발 진단에 다음을 추가합니다.
- 초기 데이터 처리속도
- 최대 동시 처리 수
- 초기 준비 오류 수

## 데이터 부족 상태 문구 수정
종목을 0개 검사한 데이터 부족 상태를 `관망`으로 결론내리지 않습니다.
- 데이터 부족 + 검사 0개: `아직 후보를 판단하지 못했습니다.`
- 실제 종목 검사를 수행했으나 후보 0개: `현재는 관망이 정상 결과입니다.`

## 안전장치
- 기존 KRX 일일 안전 Budget 8,000회 유지
- Scanner Fast Budget 60회 유지
- retry도 실제 API 호출로 Budget에 포함
- 받은 날짜는 즉시 Market Store에 보존

## 성능 목표
실제 속도는 KRX 서버 응답과 네트워크에 따라 달라집니다.
- 기존 약 500~600회 최초 준비: 수 분 → **약 60~90초대 목표**
- 약 300회: **30~60초대 목표**
- 이미 저장된 데이터: 기존처럼 KRX 0회 / 수초 수준 유지

성능 목표는 실측 전 보장값이 아니라 목표값입니다.
