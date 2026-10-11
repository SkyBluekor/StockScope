# JEV-ACT1-S1.2 — Scanner 의미 자료 생성·전달 계약 정합성

**구현 기준:** `85457c6` (JEV-ACT1-S1.1) · **작업:** JEV-ACT1-S1.2
**범위:** 신규 Scanner 후보의 의미 자료 입력·Prospective 저장 경로
**범위 밖:** Jev 유료 호출·기능 활성화·기존 캡처 재기록·Selection Policy 변경·Horizon 정책 변경·Scanner 의사결정 변경

## 확인된 사실과 아직 미확인인 것

사용자 PC: 2026-09-27 진입 후보 15건은 `semantic_source_v2` 자체가 없고, 2026-10-10 신규 진입 후보 6건은 `LOCAL_INCOMPLETE`였다. 후자 6건 전부 `SEMANTIC_CONTRACT_BINDING_MISSING`, `CONDITION_ASSERTION_SOURCE_MISSING`이 함께 관측되었다.

코드 원인은 다음과 같이 결합될 수 있다:

1. Scanner의 `_quick_candidate()`는 실제 평가한 전략을 알고 있지만 전략 신원은 Selection Policy의 `strategy_reference()`에서 가져온다.
2. 정상 레거시 정책 `LEGACY_CURRENT_10_FALLBACK`은 정책의 정의상 버전 및 해시를 `None`으로 둔다.
3. `semantic_contract.resolve_strategy_semantic_contract()`는 key/version/hash 모두 필요하다.
4. 원래 `semantic_source.build_semantic_source()`는 위 의미 계약이 연결되지 않으면 조건 요약을 전달하지 않는다. 그 때문에 assertion 쪽도 SOURCE_MISSING이 될 수 있다.

**중요:** 현재 PC의 기존 6건에서 Selection Policy provenance를 확인한 것은 아니다. 캡처 스냅샷에 출처가 별도로 보존되지 않았으면 `LEGACY_UNSPECIFIED` 투자 기간만으로 Selection Policy fallback 사용 여부를 유추해서는 안 된다. `tools/data/audit_jev_act1_s1_2_inputs.py`는 이 점을 명시하고 저장된 필드의 존재 여부만 집계한다.

## 해결 설계 — 기존 Scanner Production Baseline을 그대로 유지

첫 PR CI에서 Scanner 코드에 보조 필드를 추가하자 고정된 Production Baseline 지문 불일치 테스트가 1개 실패했다. 이 방식은 폐기했고 **`backend/app/backtest/scanner.py`를 원본 그대로 복원**했다. Baseline manifest를 재생성하거나 검증을 완화하지 않는다.

기존 Scanner는 `write_scanner_reproducibility_audit()`를 사용해 후보 정보를 정리하기 **전에** `scanner-repro/scanner-repro_*.json` 파일에 다음 원천 자료를 이미 기록한다.

- 실제 엔진의 `_repro_condition_details`: PASS/FAIL, raw 조건명, condition ID
- 선택된 전략·종목·순위·액션·Risk·조건 요약과 입력 fingerprint
- 분석일, scanner version, 결과 출처, 전체 후보 수

이 저장물은 Scanner의 기존 재현성 감사 자료이며, 신규 네트워크 요청이나 시장 데이터 재계산이 아니다.

### 1. Prospective가 허용할 감사 파일

`backend/app/strategy/semantic_identity_bridge.py`는 다음을 모두 충족한 경우에만 이 파일을 **읽기 전용**으로 사용한다.

- `scanner_cache_hit=false`, `result_source=fresh_analysis`
- `written=true`인 기존 감사 파일이 존재
- 파일 위치가 프로젝트의 단일 `scanner-repro/` 폴더 바로 아래
- 파일명·전체 후보 수·분석일·버전·입력 fingerprint·시장 범위가 Scanner 반환 결과와 일치
- 실제 후보의 시장·코드·순위·전략·액션·상태·분석일·가격·조건 요약·Risk가 감사 행과 일치
- 감사 조건이 **실제 전부 PASS**, 중복 없음, 전략별 사전 계약 목록과 정확히 일치
- Scanner 후보의 `conditions` 통과/총개수/미충족 수와 항목이 정확히 일치

단 하나라도 다르면 추가 의미 신원을 생성하지 않는다. 최신 엔진 의미 정의에서 조건을 임의로 만들어내지 않는다.

### 2. 레거시 정책 보존 및 의미 분석만 강화

`strategy_selection_policy.policy_source=LEGACY_CURRENT_10_FALLBACK` 및 `fallback_used=true` 조건에서만:

- 실제 후보의 전략 키를 확인하고 현재 StrategyEngine의 정식 AST 기반 전략 정의 버전·해시와 연결
- 정책 자체의 None 신원은 그대로 보존
- **Prospective 의미 자료 생성용 임시 복사본**에만 위 검증된 신원을 사용
- 별도의 `semantic_strategy_identity`, `semantic_condition_evidence` 출처를 저장 스냅샷에 남김

이미 전략 버전/해시가 있으면 기존 코드를 우선하고, 스스로 다른 정책의 버전을 덮어쓰지 않는다.

### 3. 지원 범위 및 실패 시 동작

캐시 재사용, 과거 자료, 파일 유실, 다른 머신의 감사 파일, 미확인 신원·불완전한 조건의 경우에는 기존 `LOCAL_INCOMPLETE` 등 부족 판정을 보존한다.

**감사 파일을 못 읽어도 Scanner 분석은 실패하지 않는다.** Prospective 의미 검토의 추가 보강만 보류된다.

기존 V4의 `SHORT/MEDIUM` 한정 provider route, 유료 호출 금지, 원본 후보·순위·Risk·가격·기간 및 Selection Policy 동작은 전부 불변이다.

## 검증

- `backend/tests/test_jev_act1_s1_2_semantic_pipeline.py`: 실제 `_current_candidate()` → `ProspectiveCatalog._candidate_snapshot()` → 진짜 SQLite Prospective `finalize_capture()` 저장/재로드/해시/중복 판정까지 연결
- 실제 엔진 전략 신원 검증, 조건 한 건 실패·삭제·중복·조작, 정책 불일치, 기존 버전 신원 부분/불일치, 오래된 캐시 attestation 없음, WAIT 차단, LEGACY HORIZON 정식 V4 차단, 네트워크 차단 검사
- 기존 Python 3.11·3.14, Node 22, Windows Fresh Clone CI 완료 필요
- 실제 사용자 Runtime은 GitHub CI에서 접근 불가하므로 검증되지 않았다고 명시

## 사용자 PC에서 읽기 전용 원인 집계

```powershell
cd C:\TAEWOO\CapstonDesign\StockScope
git status --short
git pull --ff-only origin main
git log -1 --oneline
.\sync_local.ps1 -CheckOnly
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_s1_2_inputs.py
.\.venv\Scripts\python.exe .\tools\data\audit_jev_act1_readiness.py
```

구 분석 결과가 바뀌지 않는 것이 정상이다. 사용자의 새로운 Scanner 실행은 별도로 승인받고 계획해야 한다. 기존 입력을 바꾸지 않고 바로 의미 자료를 확정하려는 시도나 fallback 정책의 자동 활성화는 금지.

## 후속 판단

1. 원본 6건에서 실제 어떤 필드가 저장돼 있는지 집계 결과 확인
2. 합성/고정 입력을 사용한 통합 테스트에서 새로운 의미 자료 생성 성공 확인
3. 새 Scanner 기록에서 engine attestation과 의미 소스 확인
4. 여전히 미비하면 전략별 조건 어휘/배열과 정책 바인딩을 별도 계약 오류로 분리
5. 실제 Jev 호출은 현행 `LEGACY_UNSPECIFIED` 차단과 V4 Canary PASS 부재 때문에 **계속 HOLD**, 별도 승인 없는 유료 API 호출 없음

완료 정의는 코드+CI+현재 PC 읽기 전용 진단 검토이다. 실제 Scanner 새 캡처 검사는 별도 사용자 UAT 단계로 남는다.
