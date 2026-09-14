# v0.20.2.1 Dark UI & Layout Polish

## 디자인 원칙

1. **다크 화면 안에 흰색 섬을 만들지 않는다.**
2. 입력창은 카드보다 약간 어두운 표면을 사용한다.
3. 선택 상태는 흰색이 아니라 짙은 블루로 표시한다.
4. 설명과 전략 목록을 좌우로 억지로 나누지 않는다.
5. 큰 화면에서 읽는 폭은 약 1320px 안으로 제한한다.
6. 글자가 커졌다는 이유로 버튼/카드에 고정 높이를 강제하지 않는다.
7. 1024px에서도 페이지 전체 가로 스크롤을 만들지 않는다.

## Theme surface

Light:
- page `#f4f7fb`
- surface `#ffffff`
- muted `#f7f9fc`
- input `#ffffff`
- selected `#eaf2ff`

Dark:
- page `#10151d`
- surface `#171e28`
- muted `#1d2632`
- input `#111924`
- selected `#203451`
- hover `#243142`

## Backtest responsive layout

- > 1320px: 전략 5열
- <= 1320px: 전략 4열
- <= 1120px: 전략 2열, 설정 필드 2열
- <= 760px: 전략 2열, 설정 필드 1열
- <= 520px: 전략 1열

백테스트 계산 로직은 변경하지 않습니다.
