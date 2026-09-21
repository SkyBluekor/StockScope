# UX.1.1 v1.0.2 — Intuitive IA + Copy Regression Hotfix

이번 hotfix는 UX.1.1에서 의도적으로 바꾼 UI 문구와 기존 TRACK.1 source regression의 오래된 문구 assertion이 충돌한 문제를 수정합니다.

## 원인
`frontend/tests/test_tracking_track1_source.py`가 다음 기존 UI 문구를 고정 문자열로 검사하고 있었습니다.

- `이 화면에서 Scanner 종목 찾기를 직접 실행`
- `종목 찾기 실행`

UX.1.1은 사용자에게 더 직관적인 용어로 변경하기 때문에, 제품 UI를 옛 문구로 되돌리는 대신 해당 **copy-only regression assertion**을 새 UI 문구에 맞춥니다.

## 추가 변경
- 종목 성과 추적 헤더 문구를 `Scanner 후보를 찾거나 원하는 종목을 직접 추가...`로 자연스럽게 정리
- Embedded Scanner 실행 버튼은 `후보 찾기` 유지
- 기존 TRACK 기능/데이터/동작 검증 assertion은 그대로 유지
- 프로젝트 `.venv` 자동 선택 로직(v1.0.1) 유지

## 변경하지 않음
- Backend
- DB
- Scanner 알고리즘 / Ranking / Risk / Entry / Stop / Target
- TRACK.1 도메인 동작
- Tracking frozen runtime baseline

## 적용
StockScope 루트에서:

```powershell
python .\apply_ux1_1_intuitive_labels.py
```

실패하면 UX.1.1 변경과 함께 수정한 copy-only test assertion도 롤백됩니다.
