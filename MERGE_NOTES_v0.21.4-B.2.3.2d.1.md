# MERGE NOTES v0.21.4-B.2.3.2d.1

## 적용 전제
B.2.3.2d가 먼저 적용되어 있어야 한다.
즉 Scanner decision version은 `0.21.3.6`이고 Risk payload에 Target1 cap/structural metadata가 존재해야 한다.

## 변경 파일
- `frontend/src/components/ScannerPanel.tsx`
- `frontend/src/components/EntryRiskGuideCard.tsx`

Backend와 Scanner decision version은 변경하지 않는다.

## 적용 후 확인
```powershell
npm --prefix frontend run build
```

그 뒤 Scanner에서 cap 적용 후보 상세를 확인한다.

한미사이언스(008930)가 동일 분석일 조건으로 포함될 경우 기대:
- 1차 목표 52,200원
- 1.50R
- `1.5R 현실성 상한 적용`
- `구조 목표 61,000원 · 최근 저항 후보`
- 2차 목표 62,200원

cap 미적용 후보와 1.5R fallback 후보에는 `현실성 상한 적용` 문구가 나타나면 안 된다.
