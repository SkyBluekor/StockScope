# v0.21.2.1 Quick Analysis Dark UI Consistency Polish

이 패치는 v0.21.2 위의 UI-only hotfix다.

## 문제
- stock suggestion row의 `color: #15223c`가 dark surface에서도 남아 종목명이 거의 보이지 않았다.
- KOSDAQ badge의 `#f3efff` 배경이 dark UI에서 과도하게 밝았다.
- `.position-context-editor`와 active position button이 `#fbfcff`, `#f0f5ff` 라이트 전용 배경을 사용해 큰 white island가 생겼다.
- 일부 position/result/helper 카드에도 near-white 고정 배경이 남아 있었다.

## 원칙
모든 수정은 기존 `--surface`, `--surface-muted`, `--input-surface`, `--selected-surface`, `--text`, `--text-strong`, `--text-subtle`, `--line`, `--primary-*` 토큰을 우선 사용한다.
