# Runtime 로컬 우선 동기화 복구 — RT-L1

## 작업 대상과 현재 상태
- 정본 PC: 현재 `C:\Projects\StockScope`의 `holdings.db`와 `simulation.db`
- 목적: Google Drive Desktop Runtime에 현재 DB를 새 공통 기준으로 게시
- 다른 PC에서 입력한 실험적인 Holdings / Simulation 변경분은 별도 승인 후 대체 가능
- JEV 호출·Canary·전략·Holdout·선정 정책 변경 금지
- Snapshot 기록, 기존 bundle, 기존 원격 head 파일은 삭제하지 않는다

## 사전 조건
1. **두 PC에서 StockScope와 관련 서버를 종료하고** 다른 PC의 동기화/게시 작업을 멈춘다.
2. 정본 PC에서 `git pull --ff-only origin main`으로 코드 업데이트.
3. 정본 PC의 `transport status`는 **DISABLED**여야 한다. 환경변수 override로 READY라면 중단한다.
4. 정본 PC의 로컬 데이터베이스를 보존한다. 이 작업 자체에서 백업을 새로 생성하며, 원본 DB를 원격 데이터로 교체하지 않는다.
5. 두 PC가 같은 Google Drive 폴더를 사용하고, 해당 폴더가 동기화 완료 상태여야 한다.
6. 이 프로토콜은 Google Drive Desktop에 분산 트랜잭션/원자적 CAS가 있다는 전제를 사용하지 않는다. 다른 PC가 게시 중이면 중단한다.

## 실행 절차 — 정본 PC

아래 명령은 새 코드가 GitHub CI 검증을 통과하고 PC에 내려온 뒤에만 사용한다.

```powershell
# 읽기 전용: 원격 head, snapshot, 로컬 DB 및 미승인 도메인 불일치 확인
python .\tools\runtime\cli.py transport reconcile --prefer-local --domains holdings,simulation --dry-run

# 계획을 확인한 후 새 백업 생성과 명시적 게시 실행
python .\tools\runtime\cli.py transport reconcile --prefer-local --domains holdings,simulation --confirm
```

Dry-run은 로컬 Runtime DB, continuity 상태, 원격 bundles/heads, 백업에 영구 변경을 남기지 않는다.
`--confirm`은 fresh backup을 만든 다음 SQLite 스냅샷과 계보를 검증하여 별도 번들을 게시한다.
**백업과 실행 명령을 한꺼번에 작성하지 말고 Dry-run 결과를 먼저 확인한다.**

예상 완료 상태: `PUBLISHED` (반복 시 `CURRENT`).
`transport_enabled: False`는 정상이며, 완료 상태와 전송 재활성화는 별개다.

정본 PC에서 확인 후 별도로 활성화:

```powershell
python .\tools\runtime\cli.py transport configure "G:\내 드라이브\StockScopeRuntime"
python .\tools\runtime\cli.py transport status
.\sync_local.ps1 -CheckOnly
```

## 다른 PC에서 새 기준 수신

다른 PC의 Runtime은 기본 동작에서 로컬 변경을 보호하므로, `pre-sync`가 `LOCAL_CHANGED_REMOTE_DESCENDANT`로
차단될 수 있다. 해당 컴퓨터의 Holdings/Simulation 실험 변경을 버리기로 명시적으로 결정한 경우에만 아래 실행.

```powershell
git pull --ff-only origin main
python .\tools\runtime\cli.py transport reconcile --prefer-remote --replace-local-changes --domains holdings,simulation --confirm
.\sync_local.ps1
```

원격 우선 실행도 교체 전 새 백업을 생성하며, 현재 DB가 **확인된 같은 계보의 원격 후속 스냅샷**인 경우에만
로컬 변경 교체를 허용한다. 계보가 다르거나 불분명한 경우 자동 교체하지 않는다.
Tracking, Macro, Market, Strategy Selection 데이터는 사용자가 승인한 Holdings/Simulation 교체와 별개다.
마이그레이션/정책을 강제로 재설정하는 명령은 사용하지 않는다.

## 오류와 복구

- `LOCAL_RECONCILE_UNAPPROVED_DOMAIN_CONFLICT`: Tracking/Macro/Market의 원격과 로컬 데이터가 서로 다르다. **해당 데이터를 조용히 덮어쓰지 않는다.**
- `LOCAL_RECONCILE_REMOTE_HEAD_CHANGED`: 게시 중 다른 PC가 새 상태를 발표했다. 프로세스를 중단하고 재검증한다.
- `LOCAL_RECONCILE_LOCAL_DB_CHANGED`: Snapshot 생성 중 원본 DB가 바뀌었다. 원본 분석 서버 종료 후 재검증한다.
- `LOCAL_RECONCILE_CONTINUITY_CHANGED`: 다른 프로세스가 continuity 상태를 바꿨다. 중단한다.
- `LOCAL_RECONCILE_LINEAGE_NOT_DESCENDANT`: 새 기준이 이전 원격 head를 후속 계보로 포함하지 못한다. 게시를 완료하지 않는다.
- `LOCAL_RECONCILE_REQUIRES_DISABLED_TRANSPORT`: 정본 PC Transport가 활성화되어 있다. 자동 pre-sync 경로를 먼저 차단한다.
- 알 수 없는 오류, 원격 파일 전파 지연, 동시 게시 발생 시 **반복 confirm하지 말고** local backup과 remote head/bundle 상태를 먼저 검사한다.

### 데이터 불변성·동기화 의미
- 정본 PC의 DB는 **항상 동일한 내용**으로 남아야 한다.
- 버린 원격 기록도 기존 bundle 파일에 남을 수 있지만, 신규 head의 활성 정본에서는 사용하지 않는다.
- 원격 위에 로컬 내용을 선택한 것은 **명시적인 override**이며 정상적인 병합이라고 주장하지 않는다.
- 원격 bundle을 먼저 완료 검증하고, local continuity를 마지막 단계에서 확정한 뒤 head를 게시한다.
- 파일시스템과 Google Drive 클라이언트 특성상 물리적으로 완전한 멀티 파일 원자성이 보장되지는 않는다.
  출처 변경 감시와 중간 실패 보호는 **최선 노력 방식**이며, 다중 PC 동시 게시가 허용된다는 의미가 아니다.

## 완료 기준

Backend Python 3.11/3.14, Windows fresh clone, 프론트 CI PASS와
테스트용 2PC RT-L1 dry-run/게시/불일치 차단/명시적 원격 수신 PASS.
실제 정본 PC 및 다른 PC에서 명령을 실행하여 정상 동기화가 관찰되기 전에는
운영 수준에서 `RT-L1 배포 완료`라고 표시하지 않는다.
