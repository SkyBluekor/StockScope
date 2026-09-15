# Scanner Result Persistence & Back Navigation — v0.21.4-A.3

## 정상 사용자 흐름
1. 사용자가 종목 찾기를 1회 실행한다.
2. 완료 결과 전체를 현재 브라우저 세션에 보존한다.
3. 후보의 `이 종목 자세히 분석`을 연다.
4. 다시 `종목 찾기`로 이동한다.
5. Scanner API를 재호출하지 않고 직전 후보 목록을 즉시 복원한다.
6. 사용자가 원할 때만 `다시 분석`으로 강제 갱신한다.

## 저장 범위
- market scope
- ScannerResponse 전체
- 마지막 완료 시각
- scrollY
- 다른 후보 펼침 여부
- 후보별 Historical Evidence 펼침 상태

## 무효화
- 저장 schema version 불일치
- 저장 market scope와 result market scope 불일치
- 사용자의 market scope 변경

## 날짜 변경
EOD가 실제로 새로 생겼는지 확인하기 위해 Scanner를 자동 재실행하지 않습니다. 날짜가 바뀐 세션이면 화면에 갱신 안내만 표시하고, 사용자가 `다시 분석`을 선택할 수 있습니다. 따라서 상세 화면 왕복 때문에 무거운 Scanner가 실행되는 일은 없습니다.
