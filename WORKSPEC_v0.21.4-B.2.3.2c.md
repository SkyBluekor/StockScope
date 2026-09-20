# WORKSPEC v0.21.4-B.2.3.2c
## Target1 Historical Realism Validation — Smoke First

### 목적
한미사이언스(008930)에서 확인된 `48,500 -> 61,000 (+25.77%, 5.05R)` Target1은 계산 버그가 아니라 현재 Production 정책의 정상 결과다. 이번 단계는 공식을 수정하지 않고, 로컬 Market Store로 현재 구조형 Target1과 1.5R 대안을 같은 신호에서 비교해 "1차 목표" 현실성을 빠르게 검증한다.

### 범위
- 기본 20개 평가일 smoke audit.
- 동일 date+ticker의 Entry / Invalidation / Strategy / Ranking / Risk 고정.
- Target1만 세 Variant로 비교:
  - `CURRENT_STRUCTURAL`: 현재 Production Target1.
  - `CAP_1_5R`: `min(CURRENT, Entry + 1.5R)`.
  - `FIXED_1_5R`: `Entry + 1.5R`.
- 5/10/20 거래일 Target-first / Stop-first / No-event 집계.
- 일봉에서 Target과 Stop이 같은 봉에 닿으면 raw=`AMBIGUOUS_SAME_BAR`, Primary는 Stop-first, sensitivity는 Target-first.
- 거리 bucket: `0~5`, `5~10`, `10~15`, `15~20`, `20%+`.
- R bucket: `<=1.5R`, `1.5~2R`, `2~3R`, `3~4R`, `4R+`.
- Target source: resistance / high20 / resistance==high20 / 1.5R fallback.
- `20%+ or 4R+` extreme group 별도 집계.

### 실행 원칙
- Offline only. KRX/OpenDART network 호출 금지.
- 기존 Production Scanner current candidate path를 재사용한다.
- 미래 OHLC는 outcome 판정에만 사용한다.
- 기본은 20일만 실행한다. 결과가 애매하거나 extreme 표본이 부족할 때만 사용자가 `--sample-size 80`으로 확대한다.

### Production 안전선
이번 overlay는 다음 Production 파일을 수정하지 않는다.
- `backend/app/risk/engine.py`
- `backend/app/market/technical.py`
- `backend/app/backtest/scanner.py`
- Strategy / Ranking / Entry / Stop / Target2 / Exit
- Scanner VERSION (`0.21.3.5` 유지)

### 출력
`backend/runtime/quality_audit/target1_realism/`
- `target1-realism-audit_<timestamp>.json`
- `target1-realism-signals_<timestamp>.csv`
- `target1-realism-summary_<timestamp>.md`

### 기본 실행
```powershell
python backend\tools\run_target1_realism_audit.py --sample-size 20
```

결과가 애매할 때만:
```powershell
python backend\tools\run_target1_realism_audit.py --sample-size 80 --min-required-dates 60
```

### 완료 기준
- CURRENT Target1이 Production candidate의 실제 Target1과 동일.
- CAP/FIXED는 Target1만 바뀌고 Entry/Stop/Strategy/Ranking은 고정.
- 20일 smoke 결과와 extreme group 표본 수가 저장됨.
- 같은 봉 ambiguity가 Primary/Sensitivity로 분리됨.
- 네트워크 요청 없이 완료.
- Production 파일 변경 0건.
