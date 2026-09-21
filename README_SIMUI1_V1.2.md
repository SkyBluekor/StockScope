# SIM.UI.1 v1.2 — Low-input stock selection UX

## 변경
- 불필요한 영문 섹션 라벨을 한국어로 정리.
- 보유 종목은 `종목명 + 종목코드`를 한 줄에 표시.
- 매수창의 `종목코드/종목명/시장` 자유입력을 제거해 코드-이름 불일치 차단.
- 종목 찾기(Scanner)의 저장된 추천 결과를 Simulation에서 바로 선택 가능.
- Historical no-lookahead 보호: Scanner 후보 `data_date`와 현재 Simulation 거래일이 같을 때만 추천 바로 추가 허용.
- 직접 찾기는 기존 `/api/stocks/search`를 재사용해 `종목명 또는 종목코드` 한 칸으로 검색.
- 종목 선택 후 현재 Simulation 거래일의 확정 종가를 local HistoricalMarketStore에서 자동 조회.
- 기본 매수 입력은 `종목 선택 + 수량` 중심. 체결가격 수정은 접힌 고급 옵션으로 이동.
- Simulation quote endpoint는 외부 네트워크를 사용하지 않음.

## 적용
프로젝트 루트에서:

```powershell
python .\apply_sim_ui1_v12_ux.py
```

실패하면 이 hotfix가 수정한 파일만 자동 복구합니다.
