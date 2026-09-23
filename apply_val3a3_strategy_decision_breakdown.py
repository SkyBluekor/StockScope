from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

OUTCOME = BACKEND / "app" / "simulation" / "validation_outcome.py"
API = BACKEND / "app" / "api" / "simulation.py"
TEST = BACKEND / "tests" / "test_validation_breakdown_val3a3.py"
SERVICE = FRONTEND / "src" / "services" / "simulationApi.ts"
WORKSPACE = FRONTEND / "src" / "components" / "SimulationWorkspace.tsx"
CSS = FRONTEND / "src" / "simulation.css"
CATALOG = BACKEND / "app" / "simulation" / "validation_catalog.py"
SCANNER = BACKEND / "app" / "backtest" / "scanner.py"
PACKAGE = FRONTEND / "package.json"

BACKEND_APPEND = '\n\n    def _breakdown_rows(\n        self,\n        rows: list[dict[str, Any]],\n        *,\n        group_key: str,\n        uppercase: bool = False,\n    ) -> list[dict[str, Any]]:\n        grouped: dict[str, list[dict[str, Any]]] = {}\n        for row in rows:\n            raw = str(row.get(group_key) or "").strip()\n            key = raw.upper() if uppercase else raw\n            if not key:\n                key = "UNKNOWN"\n            grouped.setdefault(key, []).append(row)\n\n        result: list[dict[str, Any]] = []\n        for key, group_rows in grouped.items():\n            result.append(\n                {\n                    "key": key,\n                    "candidate_count": len(group_rows),\n                    "horizons": {\n                        "5d": self._metric(group_rows, "return_5d"),\n                        "10d": self._metric(group_rows, "return_10d"),\n                        "20d": self._metric(group_rows, "return_20d"),\n                    },\n                    "mfe_20d": self._metric(group_rows, "mfe_pct", mature_only=True),\n                    "mae_20d": self._metric(group_rows, "mae_pct", mature_only=True),\n                    "touches": {\n                        name: self._touch(group_rows, name)\n                        for name in ("entry", "stop", "target1", "target2")\n                    },\n                }\n            )\n\n        # Candidate count is a stable browsing order only; it is not a performance rank.\n        result.sort(key=lambda item: (-int(item["candidate_count"]), str(item["key"])))\n        return result\n\n    def breakdown(self, validation_id: str) -> dict[str, Any]:\n        draft = self.catalog.get(validation_id)\n        if draft is None:\n            raise HistoricalValidationOutcomeError(\n                "VAL3_VALIDATION_NOT_FOUND",\n                "저장된 Historical Validation을 찾을 수 없습니다.",\n            )\n\n        # A3 reads only already-computed Simulation DB outcomes.\n        # It does not open Market Store or rerun Scanner.\n        with self.catalog.connect() as conn:\n            rows = conn.execute(\n                """\n                SELECT\n                    c.strategy,\n                    c.decision_status,\n                    o.*\n                FROM historical_validation_candidate c\n                JOIN historical_validation_candidate_outcome o\n                  ON o.validation_id=c.validation_id\n                 AND o.trading_date=c.trading_date\n                 AND o.market=c.market\n                 AND o.ticker=c.ticker\n                WHERE c.validation_id=?\n                ORDER BY c.trading_date,c.market,c.ticker\n                """,\n                (validation_id,),\n            ).fetchall()\n\n        data = [dict(row) for row in rows]\n        if not data:\n            return {\n                "validation_id": validation_id,\n                "status": "NOT_CALCULATED",\n                "strategy": [],\n                "decision_status": [],\n            }\n\n        return {\n            "validation_id": validation_id,\n            "status": "READY",\n            "strategy": self._breakdown_rows(data, group_key="strategy"),\n            "decision_status": self._breakdown_rows(\n                data,\n                group_key="decision_status",\n                uppercase=True,\n            ),\n        }\n'
TEST_CONTENT = 'from __future__ import annotations\n\nfrom pathlib import Path\n\nfrom app.simulation.validation_catalog import HistoricalValidationCatalog\nfrom app.simulation.validation_outcome import HistoricalValidationOutcomeService\n\n\ndef _make_catalog(tmp_path: Path):\n    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")\n    catalog.initialize()\n    draft = catalog.create_draft(\n        name="VAL.3-A3 fixture",\n        market_scope="KOSPI",\n        requested_period_type="custom",\n        requested_start_month="2026-01",\n        requested_end_month="2026-01",\n        resolved_start_date="2026-01-02",\n        resolved_end_date="2026-01-02",\n        trading_day_count=1,\n    )\n    catalog.save_completed_day(\n        validation_id=draft.id,\n        trading_date="2026-01-02",\n        scanner_version=draft.scanner_version,\n        market_scope="KOSPI",\n        scanner_cache_hit=False,\n        partial_data=False,\n        input_fingerprint={"fixture": "a3"},\n        market_summary={},\n        summary={},\n        methodology={},\n        diagnostics={"network_requests": 0},\n        candidates=[\n            {\n                "market": "KOSPI",\n                "ticker": "000001",\n                "name": "Momentum A",\n                "rank": 1,\n                "result_bucket": "TOP",\n                "strategy": "momentum_continuation",\n                "decision_status": "READY",\n                "snapshot": {},\n            },\n            {\n                "market": "KOSPI",\n                "ticker": "000002",\n                "name": "Momentum B",\n                "rank": 2,\n                "result_bucket": "TOP",\n                "strategy": "momentum_continuation",\n                "decision_status": "READY",\n                "snapshot": {},\n            },\n            {\n                "market": "KOSPI",\n                "ticker": "000003",\n                "name": "Pullback C",\n                "rank": 3,\n                "result_bucket": "TOP",\n                "strategy": "pullback",\n                "decision_status": "WATCH",\n                "snapshot": {},\n            },\n            {\n                "market": "KOSPI",\n                "ticker": "000004",\n                "name": "Unknown D",\n                "rank": 4,\n                "result_bucket": "TOP",\n                "strategy": "",\n                "decision_status": "",\n                "snapshot": {},\n            },\n        ],\n    )\n    with catalog.connect() as conn:\n        conn.execute(\n            """\n            UPDATE historical_validation_run\n            SET status=\'COMPLETED\',processed_day_count=trading_day_count\n            WHERE id=?\n            """,\n            (draft.id,),\n        )\n    return catalog, draft.id\n\n\ndef _insert_outcome(\n    catalog: HistoricalValidationCatalog,\n    validation_id: str,\n    ticker: str,\n    *,\n    days: int,\n    r5: float | None,\n    r10: float | None,\n    r20: float | None,\n    mfe: float | None,\n    mae: float | None,\n    stop: int,\n    target1: int,\n    target2: int,\n):\n    payload = {\n        "validation_id": validation_id,\n        "ticker": ticker,\n        "days": days,\n        "r5": r5,\n        "r10": r10,\n        "r20": r20,\n        "mfe": mfe,\n        "mae": mae,\n        "stop": stop,\n        "target1": target1,\n        "target2": target2,\n        "stop_date": "2026-01-06" if stop else None,\n        "target1_date": "2026-01-07" if target1 else None,\n        "target2_date": "2026-01-08" if target2 else None,\n    }\n    with catalog.connect() as conn:\n        conn.execute(\n            """\n            INSERT INTO historical_validation_candidate_outcome(\n                validation_id,trading_date,market,ticker,\n                reference_price,entry_rule_json,stop_price,target1_price,target2_price,\n                available_trading_days,evaluated_through,\n                return_5d,return_10d,return_20d,mfe_pct,mae_pct,\n                entry_comparable,entry_touched,entry_touch_date,\n                stop_comparable,stop_touched,stop_touch_date,\n                target1_comparable,target1_touched,target1_touch_date,\n                target2_comparable,target2_touched,target2_touch_date,\n                computed_at\n            ) VALUES(\n                :validation_id,\'2026-01-02\',\'KOSPI\',:ticker,\n                \'100\',\'{}\',\'90\',\'110\',\'120\',\n                :days,\'2026-02-02\',\n                :r5,:r10,:r20,:mfe,:mae,\n                1,1,\'2026-01-05\',\n                1,:stop,:stop_date,\n                1,:target1,:target1_date,\n                1,:target2,:target2_date,\n                \'2026-03-01T00:00:00+00:00\'\n            )\n            """,\n            payload,\n        )\n\n\ndef test_breakdown_groups_strategy_and_decision_without_ranking(tmp_path: Path):\n    catalog, validation_id = _make_catalog(tmp_path)\n    _insert_outcome(catalog, validation_id, "000001", days=20, r5=1, r10=2, r20=3, mfe=10, mae=-5, stop=0, target1=1, target2=0)\n    _insert_outcome(catalog, validation_id, "000002", days=20, r5=2, r10=4, r20=5, mfe=14, mae=-7, stop=1, target1=1, target2=1)\n    _insert_outcome(catalog, validation_id, "000003", days=10, r5=-1, r10=0.5, r20=None, mfe=8, mae=-9, stop=1, target1=0, target2=0)\n    _insert_outcome(catalog, validation_id, "000004", days=20, r5=-2, r10=-2, r20=-2, mfe=3, mae=-6, stop=1, target1=0, target2=0)\n\n    service = HistoricalValidationOutcomeService(catalog, tmp_path / "does-not-exist.db")\n    result = service.breakdown(validation_id)\n\n    assert result["status"] == "READY"\n\n    momentum = next(row for row in result["strategy"] if row["key"] == "momentum_continuation")\n    assert momentum["candidate_count"] == 2\n    assert momentum["horizons"]["20d"] == {\n        "sample_count": 2,\n        "average_pct": 4.0,\n        "median_pct": 4.0,\n    }\n    assert momentum["mfe_20d"]["average_pct"] == 12.0\n    assert momentum["mae_20d"]["average_pct"] == -6.0\n    assert momentum["touches"]["target1"]["touched_count"] == 2\n    assert momentum["touches"]["target1"]["comparable_count"] == 2\n\n    pullback = next(row for row in result["strategy"] if row["key"] == "pullback")\n    assert pullback["candidate_count"] == 1\n    assert pullback["horizons"]["5d"]["sample_count"] == 1\n    assert pullback["horizons"]["20d"]["sample_count"] == 0\n    assert pullback["mfe_20d"]["sample_count"] == 0\n    assert pullback["touches"]["stop"]["comparable_count"] == 0\n\n    ready = next(row for row in result["decision_status"] if row["key"] == "READY")\n    assert ready["candidate_count"] == 2\n    assert ready["horizons"]["20d"]["average_pct"] == 4.0\n\n\ndef test_unknown_groups_are_kept_instead_of_dropped(tmp_path: Path):\n    catalog, validation_id = _make_catalog(tmp_path)\n    _insert_outcome(catalog, validation_id, "000004", days=20, r5=-2, r10=-2, r20=-2, mfe=3, mae=-6, stop=1, target1=0, target2=0)\n\n    result = HistoricalValidationOutcomeService(\n        catalog,\n        tmp_path / "unused-market.db",\n    ).breakdown(validation_id)\n\n    unknown_strategy = next(row for row in result["strategy"] if row["key"] == "UNKNOWN")\n    unknown_decision = next(row for row in result["decision_status"] if row["key"] == "UNKNOWN")\n    assert unknown_strategy["candidate_count"] == 1\n    assert unknown_decision["candidate_count"] == 1\n\n\ndef test_breakdown_reads_simulation_db_only() -> None:\n    source = Path("backend/app/simulation/validation_outcome.py").read_text(encoding="utf-8")\n    start = source.index("    def breakdown(")\n    breakdown_source = source[start:]\n    assert "_market_conn(" not in breakdown_source\n    assert "StockScannerService" not in breakdown_source\n    assert "KrxProvider" not in breakdown_source\n    assert "requests." not in breakdown_source\n    assert "httpx." not in breakdown_source\n'
CSS_APPEND = '/* VAL.3-A3 — strategy / decision outcome breakdown */\n.sim-breakdown-scroll{width:100%;overflow-x:auto;margin-top:10px}\n.sim-breakdown-table{width:100%;min-width:820px;border-collapse:collapse;font-size:var(--font-meta)}\n.sim-breakdown-table th,.sim-breakdown-table td{padding:9px 8px;border-bottom:1px solid var(--border-subtle);text-align:right;white-space:nowrap}\n.sim-breakdown-table th:first-child,.sim-breakdown-table td:first-child{text-align:left}\n.sim-breakdown-table th{color:var(--text-muted);font-weight:800}\n.sim-breakdown-table td{color:var(--text-primary)}\n.sim-breakdown-action{border:0;border-bottom:1px solid var(--border-strong);background:transparent;color:var(--accent-primary);padding:2px 0;font:inherit;font-size:var(--font-meta);font-weight:800}\n.sim-breakdown-action:hover{border-bottom-color:var(--accent-primary)}\n.sim-breakdown-detail{margin-top:12px;padding:12px 0 2px;border-top:1px solid var(--border-default);border-bottom:1px solid var(--border-default)}\n.sim-breakdown-detail>strong{display:block;margin-bottom:8px;color:var(--text-primary)}\n.sim-breakdown-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid var(--border-subtle)}\n.sim-breakdown-detail-grid>div{padding:10px 12px;border-right:1px solid var(--border-subtle)}\n.sim-breakdown-detail-grid>div:last-child{border-right:0}\n.sim-breakdown-detail-grid span,.sim-breakdown-detail-grid small{display:block;color:var(--text-muted)}\n.sim-breakdown-detail-grid strong{display:block;margin:3px 0;color:var(--text-primary)}\n.sim-breakdown-detail-meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin-top:8px;border-top:1px solid var(--border-subtle)}\n.sim-breakdown-detail-meta>div{padding:9px 12px 9px 0}\n.sim-breakdown-detail-meta>div+div{padding-left:14px;border-left:1px solid var(--border-subtle)}\n.sim-breakdown-detail-meta span,.sim-breakdown-detail-meta small{display:block;color:var(--text-muted)}\n.sim-breakdown-detail-meta strong{display:block;margin-top:3px;color:var(--text-primary)}\n.sim-breakdown-note{margin-top:8px!important;color:var(--text-muted)!important}\n@media(max-width:800px){\n  .sim-breakdown-detail-grid,.sim-breakdown-detail-meta{grid-template-columns:1fr}\n  .sim-breakdown-detail-grid>div{border-right:0;border-bottom:1px solid var(--border-subtle)}\n  .sim-breakdown-detail-meta>div+div{padding-left:0;border-left:0;border-top:1px solid var(--border-subtle)}\n}\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"{label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    files = [path] if path.is_file() else sorted(
        p for p in path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    )
    for item in files:
        hasher.update(str(item.relative_to(ROOT)).replace("\\", "/").encode())
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def run(cmd: list[str], cwd: Path, label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def patch_api(source: str) -> str:
    if "/outcomes/breakdown" in source:
        fail("simulation.py already appears to contain VAL.3-A3.")
    marker = '''# --- VAL.2-D: execution validation API lifecycle ---------------------------
'''
    endpoint = '''@router.get(
    "/simulation/validations/{validation_id}/outcomes/breakdown",
    tags=["simulation-validation"],
)
def get_validation_outcome_breakdown(validation_id: str):
    try:
        return _validation_outcome_service().breakdown(validation_id)
    except HistoricalValidationOutcomeError as error:
        _validation_outcome_http_error(error)


''' + marker
    return replace_once(source, marker, endpoint, "A3 breakdown API")


def patch_service(source: str) -> str:
    if "HistoricalValidationOutcomeBreakdown" in source:
        fail("simulationApi.ts already appears to contain VAL.3-A3.")

    fn_anchor = '''export function getValidationOutcomeSummary(id: string) {
'''
    types = '''export type ValidationOutcomeBreakdownRow = {
  key: string;
  candidate_count: number;
  horizons: {
    "5d": ValidationOutcomeMetric;
    "10d": ValidationOutcomeMetric;
    "20d": ValidationOutcomeMetric;
  };
  mfe_20d: ValidationOutcomeMetric;
  mae_20d: ValidationOutcomeMetric;
  touches: {
    entry: ValidationOutcomeTouch;
    stop: ValidationOutcomeTouch;
    target1: ValidationOutcomeTouch;
    target2: ValidationOutcomeTouch;
  };
};

export type HistoricalValidationOutcomeBreakdown = {
  validation_id: string;
  status: "NOT_CALCULATED" | "READY" | string;
  strategy: ValidationOutcomeBreakdownRow[];
  decision_status: ValidationOutcomeBreakdownRow[];
};

''' + fn_anchor
    source = replace_once(source, fn_anchor, types, "A3 frontend types")

    refresh_anchor = '''export function refreshValidationOutcomes(id: string) {
'''
    fn = '''export function getValidationOutcomeBreakdown(id: string) {
  return apiJson<HistoricalValidationOutcomeBreakdown>(
    `/api/simulation/validations/${encodeURIComponent(id)}/outcomes/breakdown`,
  );
}

''' + refresh_anchor
    return replace_once(source, refresh_anchor, fn, "A3 frontend fetch")


def patch_workspace(source: str) -> str:
    if "outcomeBreakdown" in source:
        fail("SimulationWorkspace.tsx already appears to contain VAL.3-A3.")

    source = replace_once(
        source,
        '''  getValidationDraft,
  getValidationOutcomeSummary,
  listLegacyValidations,
''',
        '''  getValidationDraft,
  getValidationOutcomeBreakdown,
  getValidationOutcomeSummary,
  listLegacyValidations,
''',
        "A3 workspace import function",
    )
    source = replace_once(
        source,
        '''  type HistoricalValidationDraft,
  type HistoricalValidationOutcomeSummary,
''',
        '''  type HistoricalValidationDraft,
  type HistoricalValidationOutcomeBreakdown,
  type HistoricalValidationOutcomeSummary,
  type ValidationOutcomeBreakdownRow,
''',
        "A3 workspace import types",
    )

    helper_anchor = '''function averageMedianNote(average: number | null | undefined, median: number | null | undefined) {
  if (average == null || median == null || !Number.isFinite(average) || !Number.isFinite(median)) {
    return "평균과 중앙값은 확인 가능한 표본만 사용합니다.";
  }
  const gap = average - median;
  if (Math.abs(gap) < 0.005) {
    return "평균과 중앙값이 거의 같습니다. 두 값 모두 결과 분포를 이해할 때 함께 확인합니다.";
  }
  return `평균은 중앙값보다 ${Math.abs(gap).toFixed(2)}%p ${gap > 0 ? "높습니다" : "낮습니다"}. 큰 상승·하락 사례가 평균에 영향을 줄 수 있으므로 두 값을 함께 확인합니다.`;
}
'''
    helper_new = helper_anchor + '''
const validationStrategyLabels: Record<string, string> = {
  trend_following: "상승 흐름 유지",
  pullback: "눌림 후 반등 흐름",
  breakout: "강한 돌파 흐름",
  support_bounce: "지지 가격에서 반등",
  oversold_bounce: "많이 떨어진 뒤 반등",
  range_trading: "일정 가격 사이 움직임",
  momentum_continuation: "강한 상승 지속",
  volatility_squeeze: "조용한 움직임 뒤 방향 대기",
  ma20_rebound: "최근 평균 가격에서 반등",
  trend_recovery: "다시 상승 흐름",
  no_trade: "지금은 관망",
  UNKNOWN: "전략 정보 없음",
};
const validationDecisionLabels: Record<string, string> = {
  READY: "진입 후보",
  WATCH: "관심 유지",
  NOT_READY: "현재 우선순위 낮음",
  CAUTION: "주의하며 관찰",
  BLOCKED: "위험 때문에 보류",
  NO_TRADE: "신규 진입 제외",
  UNKNOWN: "판단 정보 없음",
};
function validationStrategyLabel(key: string) {
  return validationStrategyLabels[key] ?? key;
}
function validationDecisionLabel(key: string) {
  return validationDecisionLabels[key] ?? key;
}
function touchPctText(value: { comparable_count: number; touched_count: number; touched_pct: number | null }) {
  if (value.comparable_count <= 0 || value.touched_pct == null) return "-";
  return `${value.touched_pct.toFixed(1)}%`;
}

function ValidationBreakdownDetail({
  row,
  label,
}: {
  row: ValidationOutcomeBreakdownRow;
  label: string;
}) {
  return (
    <div className="sim-breakdown-detail">
      <strong>{label} 상세</strong>
      <div className="sim-breakdown-detail-grid">
        {(["5d", "10d", "20d"] as const).map((horizon) => {
          const metric = row.horizons[horizon];
          const title = horizon === "5d" ? "5거래일 뒤" : horizon === "10d" ? "10거래일 뒤" : "20거래일 뒤";
          return (
            <div key={horizon}>
              <span>{title}</span>
              <strong>{pctText(metric.average_pct)}</strong>
              <small>중앙값 {pctText(metric.median_pct)} · 표본 {countText(metric.sample_count)}</small>
            </div>
          );
        })}
      </div>
      <div className="sim-breakdown-detail-meta">
        <div>
          <span>20거래일 가격 움직임</span>
          <strong>최고 상승폭 {pctText(row.mfe_20d.average_pct)}</strong>
          <small>최대 하락폭 {pctText(row.mae_20d.average_pct)}</small>
        </div>
        <div>
          <span>20거래일 가격 기준 도달</span>
          <strong>1차 목표 {touchText(row.touches.target1)}</strong>
          <small>2차 목표 {touchText(row.touches.target2)} · 손절 기준 {touchText(row.touches.stop)}</small>
        </div>
      </div>
    </div>
  );
}
'''
    source = replace_once(source, helper_anchor, helper_new, "A3 workspace helper UI")

    state_anchor = '''  const [outcomeBusy, setOutcomeBusy] = useState(false);
  const [outcomeSummary, setOutcomeSummary] = useState<HistoricalValidationOutcomeSummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);
'''
    state_new = '''  const [outcomeBusy, setOutcomeBusy] = useState(false);
  const [outcomeSummary, setOutcomeSummary] = useState<HistoricalValidationOutcomeSummary | null>(null);
  const [outcomeBreakdown, setOutcomeBreakdown] = useState<HistoricalValidationOutcomeBreakdown | null>(null);
  const [expandedStrategyKey, setExpandedStrategyKey] = useState<string | null>(null);
  const [expandedDecisionKey, setExpandedDecisionKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
'''
    source = replace_once(source, state_anchor, state_new, "A3 workspace state")

    effect_old = '''  useEffect(() => {
    if (mode !== "saved" || !selectedDraft || selectedDraft.status !== "COMPLETED") {
      setOutcomeSummary(null);
      return;
    }
    let disposed = false;
    setOutcomeBusy(true);
    void getValidationOutcomeSummary(selectedDraft.id)
      .then((summary) => { if (!disposed) setOutcomeSummary(summary); })
      .catch((error) => { if (!disposed) setMessage(errorText(error)); })
      .finally(() => { if (!disposed) setOutcomeBusy(false); });
    return () => { disposed = true; };
  }, [mode, selectedDraft?.id, selectedDraft?.status]);
'''
    effect_new = '''  useEffect(() => {
    setExpandedStrategyKey(null);
    setExpandedDecisionKey(null);
    if (mode !== "saved" || !selectedDraft || selectedDraft.status !== "COMPLETED") {
      setOutcomeSummary(null);
      setOutcomeBreakdown(null);
      return;
    }
    let disposed = false;
    setOutcomeBusy(true);
    setOutcomeBreakdown(null);
    void getValidationOutcomeSummary(selectedDraft.id)
      .then(async (summary) => {
        if (disposed) return;
        setOutcomeSummary(summary);
        if (summary.status === "READY") {
          const breakdown = await getValidationOutcomeBreakdown(selectedDraft.id);
          if (!disposed) setOutcomeBreakdown(breakdown);
        }
      })
      .catch((error) => { if (!disposed) setMessage(errorText(error)); })
      .finally(() => { if (!disposed) setOutcomeBusy(false); });
    return () => { disposed = true; };
  }, [mode, selectedDraft?.id, selectedDraft?.status]);
'''
    source = replace_once(source, effect_old, effect_new, "A3 breakdown load effect")

    action_old = '''  async function calculateOutcomes(row: HistoricalValidationDraft) {
    if (outcomeBusy || row.status !== "COMPLETED") return;
    setOutcomeBusy(true); setMessage(null);
    try {
      const summary = await refreshValidationOutcomes(row.id);
      setOutcomeSummary(summary);
      setMessage(`'${row.name}' 후보 ${summary.outcome_count}건의 D+1~D+20 성과를 계산했습니다.`);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setOutcomeBusy(false);
    }
  }
'''
    action_new = '''  async function calculateOutcomes(row: HistoricalValidationDraft) {
    if (outcomeBusy || row.status !== "COMPLETED") return;
    setOutcomeBusy(true); setMessage(null);
    try {
      const summary = await refreshValidationOutcomes(row.id);
      setOutcomeSummary(summary);
      const breakdown = summary.status === "READY"
        ? await getValidationOutcomeBreakdown(row.id)
        : null;
      setOutcomeBreakdown(breakdown);
      setExpandedStrategyKey(null);
      setExpandedDecisionKey(null);
      setMessage(`'${row.name}' 후보 ${summary.outcome_count}건의 D+1~D+20 성과를 계산했습니다.`);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setOutcomeBusy(false);
    }
  }
'''
    source = replace_once(source, action_old, action_new, "A3 refresh breakdown")

    details_anchor = '''                <details className="sim-outcome-method">
'''
    sections = '''                <section className="sim-outcome-section">
                  <span className="sim-section-kicker">그룹 비교</span>
                  <h5>전략별 결과</h5>
                  <p>같은 Scanner 후보라도 당시 적용된 전략에 따라 이후 가격 움직임이 어떻게 달랐는지 나눠 봅니다.</p>
                  <p className="sim-breakdown-note">표는 과거 후보 수가 많은 순으로 표시하며 성과 순위가 아닙니다. 후보 수가 적은 그룹은 수치가 크게 흔들릴 수 있으므로 표본 수를 함께 확인하세요.</p>
                  {outcomeBreakdown?.status === "READY" && outcomeBreakdown.strategy.length > 0 ? <>
                    <div className="sim-breakdown-scroll">
                      <table className="sim-breakdown-table">
                        <thead><tr><th>전략</th><th>과거 후보</th><th>20일 확인</th><th>20일 평균</th><th>중앙값</th><th>1차 목표</th><th>손절 기준</th><th>상세</th></tr></thead>
                        <tbody>
                          {outcomeBreakdown.strategy.map((row) => (
                            <tr key={row.key}>
                              <td>{validationStrategyLabel(row.key)}</td>
                              <td>{countText(row.candidate_count)}</td>
                              <td>{countText(row.horizons["20d"].sample_count)}</td>
                              <td>{pctText(row.horizons["20d"].average_pct)}</td>
                              <td>{pctText(row.horizons["20d"].median_pct)}</td>
                              <td>{touchPctText(row.touches.target1)}</td>
                              <td>{touchPctText(row.touches.stop)}</td>
                              <td><button type="button" className="sim-breakdown-action" onClick={() => setExpandedStrategyKey((current) => current === row.key ? null : row.key)}>{expandedStrategyKey === row.key ? "닫기" : "상세 보기"}</button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {outcomeBreakdown.strategy.filter((row) => row.key === expandedStrategyKey).map((row) => (
                      <ValidationBreakdownDetail key={row.key} row={row} label={validationStrategyLabel(row.key)} />
                    ))}
                  </> : <p className="sim-outcome-note">성과 계산 후 전략별 결과를 확인할 수 있습니다.</p>}
                </section>

                <section className="sim-outcome-section">
                  <h5>당시 판단별 결과</h5>
                  <p>Scanner가 후보를 찾았을 때의 판단 상태에 따라 이후 가격 움직임을 나눠 봅니다. 현재 종목에 대한 매수·매도 지시가 아니라 과거 판단의 특성을 확인하기 위한 통계입니다.</p>
                  {outcomeBreakdown?.status === "READY" && outcomeBreakdown.decision_status.length > 0 ? <>
                    <div className="sim-breakdown-scroll">
                      <table className="sim-breakdown-table">
                        <thead><tr><th>당시 판단</th><th>과거 후보</th><th>20일 확인</th><th>20일 평균</th><th>중앙값</th><th>1차 목표</th><th>손절 기준</th><th>상세</th></tr></thead>
                        <tbody>
                          {outcomeBreakdown.decision_status.map((row) => (
                            <tr key={row.key}>
                              <td>{validationDecisionLabel(row.key)}</td>
                              <td>{countText(row.candidate_count)}</td>
                              <td>{countText(row.horizons["20d"].sample_count)}</td>
                              <td>{pctText(row.horizons["20d"].average_pct)}</td>
                              <td>{pctText(row.horizons["20d"].median_pct)}</td>
                              <td>{touchPctText(row.touches.target1)}</td>
                              <td>{touchPctText(row.touches.stop)}</td>
                              <td><button type="button" className="sim-breakdown-action" onClick={() => setExpandedDecisionKey((current) => current === row.key ? null : row.key)}>{expandedDecisionKey === row.key ? "닫기" : "상세 보기"}</button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {outcomeBreakdown.decision_status.filter((row) => row.key === expandedDecisionKey).map((row) => (
                      <ValidationBreakdownDetail key={row.key} row={row} label={validationDecisionLabel(row.key)} />
                    ))}
                  </> : <p className="sim-outcome-note">성과 계산 후 당시 판단별 결과를 확인할 수 있습니다.</p>}
                </section>

''' + details_anchor
    return replace_once(source, details_anchor, sections, "A3 breakdown UI")


def patch_css(source: str) -> str:
    if "VAL.3-A3" in source:
        fail("simulation.css already appears to contain VAL.3-A3.")
    return source.rstrip() + "\n\n" + CSS_APPEND.strip() + "\n"


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("VAL.3-A3 — 전략별 · 판단 상태별 성과 비교")
    print("A1 performance formula changes: NO")
    print("DB schema changes: NO")
    print("Market Store access for breakdown: NO")
    print("Scanner rerun: NO")
    print("External network: NO")
    print("Theme support: LIGHT + DARK")

    required = [OUTCOME, API, SERVICE, WORKSPACE, CSS, CATALOG, SCANNER, PACKAGE]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")
    if TEST.exists():
        fail("VAL.3-A3 test file already exists; stop to avoid double apply.")

    originals = {
        OUTCOME: OUTCOME.read_text(encoding="utf-8-sig"),
        API: API.read_text(encoding="utf-8-sig"),
        SERVICE: SERVICE.read_text(encoding="utf-8-sig"),
        WORKSPACE: WORKSPACE.read_text(encoding="utf-8-sig"),
        CSS: CSS.read_text(encoding="utf-8-sig"),
    }

    preflight = {
        "VAL.3-A1 outcome": "historical_validation_candidate_outcome" in originals[OUTCOME],
        "VAL.3-A2 result summary": "검증 결과 요약" in originals[WORKSPACE],
        "VAL.3-A2.1 layout": "VAL.3-A2.1 — result layout recovery" in originals[CSS],
        "A1 summary API": "/outcomes/summary" in originals[API],
    }
    for name, ok in preflight.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not all(preflight.values()):
        fail("VAL.3-A1/A2/A2.1 is not in the expected state.")

    protected = {
        "catalog": sha256(CATALOG),
        "scanner": sha256(SCANNER),
        "tracking": tree_hash(BACKEND / "app" / "tracking"),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "holdings": tree_hash(BACKEND / "app" / "holdings"),
        "market_store": sha256(BACKEND / "app" / "backtest" / "market_store.py"),
    }

    created: list[Path] = []
    try:
        OUTCOME.write_text(
            originals[OUTCOME].rstrip() + BACKEND_APPEND + "\n",
            encoding="utf-8",
            newline="\n",
        )
        API.write_text(patch_api(originals[API]), encoding="utf-8", newline="\n")
        SERVICE.write_text(patch_service(originals[SERVICE]), encoding="utf-8", newline="\n")
        WORKSPACE.write_text(patch_workspace(originals[WORKSPACE]), encoding="utf-8", newline="\n")
        CSS.write_text(patch_css(originals[CSS]), encoding="utf-8", newline="\n")
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        print()
        print("=== VAL.3-A3 STATIC CONTRACT ===")
        outcome = OUTCOME.read_text(encoding="utf-8")
        api = API.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        workspace = WORKSPACE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        package = PACKAGE.read_text(encoding="utf-8").lower()

        breakdown_pos = outcome.index("    def breakdown(")
        breakdown_source = outcome[breakdown_pos:]

        checks = {
            "A1 source prefix preserved": outcome.startswith(originals[OUTCOME].rstrip()),
            "strategy grouping": 'group_key="strategy"' in breakdown_source,
            "decision grouping": 'group_key="decision_status"' in breakdown_source,
            "unknown group kept": 'key = "UNKNOWN"' in outcome,
            "20D maturity reused": "mature_only=True" in BACKEND_APPEND,
            "A1 touch semantics reused": "self._touch(group_rows, name)" in BACKEND_APPEND,
            "no Market Store in breakdown": "_market_conn(" not in breakdown_source,
            "no Scanner in breakdown": "StockScannerService" not in breakdown_source,
            "breakdown endpoint": "/outcomes/breakdown" in api,
            "typed frontend breakdown": "HistoricalValidationOutcomeBreakdown" in service,
            "strategy section": "전략별 결과" in workspace,
            "decision section": "당시 판단별 결과" in workspace,
            "no automatic ranking": "1위" not in workspace and "최고 전략" not in workspace,
            "candidate-count order explained": "성과 순위가 아닙니다" in workspace,
            "no win-rate label": "승률" not in workspace,
            "no buy/sell instruction": "매수하세요" not in workspace and "매도하세요" not in workspace,
            "detail 5/10/20": all(label in workspace for label in ("5거래일 뒤", "10거래일 뒤", "20거래일 뒤")),
            "theme tokens": "var(--text-primary)" in CSS_APPEND and "var(--border-subtle)" in CSS_APPEND,
            "no theme fork": 'html[data-theme=' not in CSS_APPEND and ":root" not in CSS_APPEND,
            "no paid dependency": all(name not in package for name in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            fail("Static contract failed: " + ", ".join(failed))

        python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            fail(f"Project venv python not found: {python}")

        run(
            [
                str(python), "-m", "pytest",
                "backend/tests/test_validation_breakdown_val3a3.py",
                "backend/tests/test_validation_outcome_val3a1.py",
                "-q",
            ],
            ROOT,
            "Focused backend regression",
        )

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            fail("npm was not found.")
        run([npm, "run", "build"], FRONTEND, "Frontend build")

        protected_after = {
            "catalog": sha256(CATALOG),
            "scanner": sha256(SCANNER),
            "tracking": tree_hash(BACKEND / "app" / "tracking"),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "holdings": tree_hash(BACKEND / "app" / "holdings"),
            "market_store": sha256(BACKEND / "app" / "backtest" / "market_store.py"),
        }
        if protected_after != protected:
            fail("Protected Catalog/Scanner/Tracking/Strategy/Risk/HOLD/Market Store source changed.")

        print()
        print("VAL.3-A3 IMPLEMENTATION READY")
        print("Added:")
        print(" - backend/tests/test_validation_breakdown_val3a3.py")
        print("Modified:")
        print(" - backend/app/simulation/validation_outcome.py (additive breakdown only)")
        print(" - backend/app/api/simulation.py")
        print(" - frontend/src/services/simulationApi.ts")
        print(" - frontend/src/components/SimulationWorkspace.tsx")
        print(" - frontend/src/simulation.css")
        print("Strategy breakdown: PASS")
        print("Decision-state breakdown: PASS")
        print("A1 calculation changes: 0")
        print("DB schema changes: 0")
        print("Market Store access for breakdown: 0")
        print("Scanner rerun: 0")
        print("External network: 0")
        print("Frontend build: PASS")
        print()
        print("NEXT UAT:")
        print(" 1) Open the existing completed validation.")
        print(" 2) Confirm 전략별 결과 shows multiple strategies.")
        print(" 3) Confirm 당시 판단별 결과 shows stored decision states.")
        print(" 4) Open one strategy 상세 보기 and one decision 상세 보기.")
        print(" 5) Confirm the A2 overall numbers above are unchanged.")
        print(" 6) Capture one Dark screenshot.")
        return 0

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — VAL.3-A3 changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
