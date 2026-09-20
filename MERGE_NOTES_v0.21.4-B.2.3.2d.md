# MERGE NOTES v0.21.4-B.2.3.2d

## 적용 전제
현재 프로젝트가 최소 다음 상태를 포함한다고 가정한다.
- B.2.3.2c Target1 historical realism audit 적용 완료
- c.4g Scanner decision version 0.21.3.5
- B.2.4/B.2.4a Scanner progress UX 적용 완료

## 적용 후 확인
프로젝트 루트에서:

```powershell
pytest backend\tests\test_target1_production_policy_v0214b232d.py -q
npm --prefix frontend run build
```

그 뒤 Scanner를 새로 실행한다. 기존 0.21.3.5 브라우저 세션/Scanner cache는 새 decision version에서 재사용되지 않는다. Historical Evidence도 policy cache v2로 새로 계산될 수 있다.

## 화면 확인
한미사이언스(008930)가 후보에 포함될 경우 기대값:
- 1차 목표: 약 52,200원
- 손익비: 약 1 : 1.50
- 산정 기준: 1.5R 현실성 상한
- 구조 목표: 61,000원 / 최근 저항 후보
- 2차 확장 목표: 약 62,200원 (기존 값 유지)

## 주의
이번 변경은 Target1 Production 정책만 수정한다. 추가 80-date audit은 완료 조건에 포함하지 않는다.
