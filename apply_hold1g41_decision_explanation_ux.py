from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

DECISION = BACKEND / "app" / "holdings" / "decision_context.py"
DECISION_TEST = BACKEND / "tests" / "test_holdings_decision_context_hold1g4.py"
HOLDINGS_API = BACKEND / "app" / "api" / "holdings.py"
ANALYSIS = BACKEND / "app" / "holdings" / "analysis.py"
ANALYSIS_HISTORY = BACKEND / "app" / "holdings" / "analysis_history.py"
SCANNER = BACKEND / "app" / "backtest" / "scanner.py"
CHART = FRONTEND / "src" / "components" / "HoldingsPriceChart.tsx"
SERVICE = FRONTEND / "src" / "services" / "holdingsApi.ts"
WORKSPACE = FRONTEND / "src" / "components" / "HoldingsWorkspace.tsx"
CSS = FRONTEND / "src" / "holdings.css"
PACKAGE = FRONTEND / "package.json"


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


def patch_decision(source: str) -> str:
    old = '''ENTRY_LABELS = {
    "READY": "진입 후보",
    "WATCH": "조건 형성 중",
    "NOT_READY": "조건 부족",
    "BLOCKED": "위험 때문에 보류",
    "CAUTION": "위험 주의",
    "NO_TRADE": "신규 진입 제외",
    "UNKNOWN": "판단 정보 없음",
}

PLAN_LABELS = {
    "NO_PREVIOUS_PLAN": "비교할 이전 계획 없음",
    "WITHIN_PLAN": "이전 계획 범위 내",
    "STOP_BREACHED": "이전 계획 손절 기준 이탈",
    "TARGET1_REACHED": "이전 계획 1차 목표 이상",
    "TARGET2_REACHED": "이전 계획 2차 목표 이상",
}
'''
    new = '''ENTRY_LABELS = {
    "READY": "진입 후보",
    "WATCH": "관심 유지",
    "NOT_READY": "현재 우선순위 낮음",
    "BLOCKED": "위험 때문에 보류",
    "CAUTION": "주의하며 관찰",
    "NO_TRADE": "신규 진입 제외",
    "UNKNOWN": "판단 정보 없음",
}

PLAN_LABELS = {
    "FIRST_PLAN": "첫 계획 설정됨",
    "PREVIOUS_PLAN_UNAVAILABLE": "이전 가격 계획 정보 없음",
    "WITHIN_PLAN": "이전 계획 범위 내",
    "STOP_BREACHED": "이전 계획 손절 기준 이탈",
    "TARGET1_REACHED": "이전 계획 1차 목표 이상",
    "TARGET2_REACHED": "이전 계획 2차 목표 이상",
}
'''
    source = replace_once(source, old, new, "decision labels")

    old = '''        readiness = snapshot.get("readiness_state")
        readiness = readiness if isinstance(readiness, dict) else {}

        raw_entry_state = str(
'''
    new = '''        readiness = snapshot.get("readiness_state")
        readiness = readiness if isinstance(readiness, dict) else {}
        condition_state = snapshot.get("condition_state")
        condition_state = condition_state if isinstance(condition_state, dict) else {}

        raw_entry_state = str(
'''
    source = replace_once(source, old, new, "condition state source")

    old = '''        warnings = readiness.get("warnings")
        warnings = (
            [str(item) for item in warnings if str(item).strip()]
            if isinstance(warnings, list)
            else []
        )

        entry = {
            "state": raw_entry_state,
            "label": ENTRY_LABELS[raw_entry_state],
            "summary": (
                str(readiness.get("summary")).strip()
                if readiness.get("summary") not in (None, "")
                else None
            ),
            "decision_reason": (
                str(readiness.get("decision_reason")).strip()
                if readiness.get("decision_reason") not in (None, "")
                else None
            ),
            "missing": _safe_int(readiness.get("missing")),
            "total": _safe_int(readiness.get("total")),
            "warnings": warnings,
        }
'''
    new = '''        warnings = readiness.get("warnings")
        warnings = (
            [str(item) for item in warnings if str(item).strip()]
            if isinstance(warnings, list)
            else []
        )

        raw_missing_details = condition_state.get("missing_details")
        missing_details: list[dict[str, str | None]] = []
        if isinstance(raw_missing_details, list):
            for item in raw_missing_details:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("raw") or "").strip()
                if not label:
                    continue
                missing_details.append(
                    {
                        "label": label,
                        "detail": (
                            str(item.get("detail")).strip()
                            if item.get("detail") not in (None, "")
                            else None
                        ),
                        "current_value": (
                            str(item.get("current_value")).strip()
                            if item.get("current_value") not in (None, "")
                            else None
                        ),
                        "required_value": (
                            str(item.get("required_value")).strip()
                            if item.get("required_value") not in (None, "")
                            else None
                        ),
                        "raw": (
                            str(item.get("raw")).strip()
                            if item.get("raw") not in (None, "")
                            else None
                        ),
                    }
                )

        passed = _safe_int(condition_state.get("passed"))
        if passed is None:
            passed = _safe_int(readiness.get("passed"))
        missing = _safe_int(condition_state.get("missing"))
        if missing is None:
            missing = _safe_int(readiness.get("missing"))
        total = _safe_int(condition_state.get("total"))
        if total is None:
            total = _safe_int(readiness.get("total"))
        if missing_details:
            missing = len(missing_details)
            if total is not None and passed is None:
                passed = max(0, total - missing)

        entry = {
            "state": raw_entry_state,
            "label": ENTRY_LABELS[raw_entry_state],
            "summary": (
                str(readiness.get("summary")).strip()
                if readiness.get("summary") not in (None, "")
                else None
            ),
            "decision_reason": (
                str(readiness.get("decision_reason")).strip()
                if readiness.get("decision_reason") not in (None, "")
                else None
            ),
            "passed": passed,
            "missing": missing,
            "total": total,
            "warnings": warnings,
            "missing_details": missing_details,
        }
'''
    source = replace_once(source, old, new, "decision evidence payload")

    old = '''        previous_stop = previous.stop_price if previous is not None else None
        previous_target1 = previous.target1_price if previous is not None else None
        previous_target2 = previous.target2_price if previous is not None else None
        current_close = current.reference_price
        has_previous_plan = previous is not None and any(
            value is not None
            for value in (previous_stop, previous_target1, previous_target2)
        )

        if not has_previous_plan or current_close is None:
            plan_state = "NO_PREVIOUS_PLAN"
        elif previous_stop is not None and current_close <= previous_stop:
            plan_state = "STOP_BREACHED"
        elif previous_target2 is not None and current_close >= previous_target2:
            plan_state = "TARGET2_REACHED"
        elif previous_target1 is not None and current_close >= previous_target1:
            plan_state = "TARGET1_REACHED"
        else:
            plan_state = "WITHIN_PLAN"

        previous_plan = {
            "state": plan_state,
            "label": PLAN_LABELS[plan_state],
            "previous_market_date": (
                str(previous_row["market_date"]) if previous_row is not None else None
            ),
            "previous_stop_price": _decimal_text(previous_stop),
            "previous_target1_price": _decimal_text(previous_target1),
            "previous_target2_price": _decimal_text(previous_target2),
            "current_close": _decimal_text(current_close),
        }
'''
    new = '''        previous_reference = previous.reference_price if previous is not None else None
        previous_stop = previous.stop_price if previous is not None else None
        previous_target1 = previous.target1_price if previous is not None else None
        previous_target2 = previous.target2_price if previous is not None else None
        current_close = current.reference_price

        if previous is None:
            plan_state = "FIRST_PLAN"
        elif (
            current_close is None
            or all(
                value is None
                for value in (previous_stop, previous_target1, previous_target2)
            )
        ):
            plan_state = "PREVIOUS_PLAN_UNAVAILABLE"
        elif previous_stop is not None and current_close <= previous_stop:
            plan_state = "STOP_BREACHED"
        elif previous_target2 is not None and current_close >= previous_target2:
            plan_state = "TARGET2_REACHED"
        elif previous_target1 is not None and current_close >= previous_target1:
            plan_state = "TARGET1_REACHED"
        else:
            plan_state = "WITHIN_PLAN"

        previous_plan = {
            "state": plan_state,
            "label": PLAN_LABELS[plan_state],
            "previous_market_date": (
                str(previous_row["market_date"]) if previous_row is not None else None
            ),
            "previous_reference_price": _decimal_text(previous_reference),
            "previous_stop_price": _decimal_text(previous_stop),
            "previous_target1_price": _decimal_text(previous_target1),
            "previous_target2_price": _decimal_text(previous_target2),
            "current_close": _decimal_text(current_close),
        }
'''
    return replace_once(source, old, new, "plan continuity payload")


def patch_test(source: str) -> str:
    old = '''        ("READY", "진입 후보"),
        ("WATCH", "조건 형성 중"),
        ("NOT_READY", "조건 부족"),
        ("BLOCKED", "위험 때문에 보류"),
        ("CAUTION", "위험 주의"),
'''
    new = '''        ("READY", "진입 후보"),
        ("WATCH", "관심 유지"),
        ("NOT_READY", "현재 우선순위 낮음"),
        ("BLOCKED", "위험 때문에 보류"),
        ("CAUTION", "주의하며 관찰"),
'''
    source = replace_once(source, old, new, "decision test labels")

    old = '''    assert context["previous_plan"]["previous_market_date"] == "2026-09-21"
    assert context["previous_plan"]["previous_stop_price"] == "100"
'''
    new = '''    assert context["previous_plan"]["previous_market_date"] == "2026-09-21"
    assert context["previous_plan"]["previous_reference_price"] == "105"
    assert context["previous_plan"]["previous_stop_price"] == "100"
'''
    source = replace_once(source, old, new, "previous reference test")

    old = '''def test_first_analysis_has_initial_strategy_and_no_previous_plan(tmp_path: Path):
'''
    new = '''def test_first_analysis_has_initial_strategy_and_first_plan(tmp_path: Path):
'''
    source = replace_once(source, old, new, "first plan test name")

    old = '''    assert context["previous_plan"]["state"] == "NO_PREVIOUS_PLAN"
'''
    new = '''    assert context["previous_plan"]["state"] == "FIRST_PLAN"
    assert context["previous_plan"]["label"] == "첫 계획 설정됨"
'''
    source = replace_once(source, old, new, "first plan expectation")

    insert_before = '''def test_decision_context_is_database_only() -> None:
'''
    additions = '''def test_missing_condition_details_are_exposed_from_snapshot(tmp_path: Path):
    catalog, stock = _catalog(tmp_path)
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock.id,
        market_date="2026-09-22",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="details",
        strategy_key="momentum_continuation",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="110",
        target2_price="120",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="P1",
        source_versions={"fixture": "details"},
        snapshot={
            "readiness_state": {
                "status": "WATCH",
                "missing": 2,
                "total": 8,
            },
            "condition_state": {
                "passed": 6,
                "missing": 2,
                "total": 8,
                "missing_details": [
                    {
                        "raw": "조건 A",
                        "label": "최근 저점이 무너지지 않기",
                        "detail": "최근 저점 구조가 유지되는지 확인합니다.",
                        "current_value": "낮아짐",
                        "required_value": "최근 저점 유지 또는 상승",
                    },
                    {
                        "raw": "조건 B",
                        "label": "거래량 조건 충족",
                        "detail": "거래 참여가 충분한지 확인합니다.",
                        "current_value": "0.8배",
                        "required_value": "1.2배 이상",
                    },
                ],
            },
        },
        revision_reason="INITIAL",
        computed_at="2026-09-22T08:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)

    assert context["entry"]["passed"] == 6
    assert context["entry"]["missing"] == 2
    assert context["entry"]["total"] == 8
    assert len(context["entry"]["missing_details"]) == 2
    assert context["entry"]["missing_details"][0]["label"] == "최근 저점이 무너지지 않기"
    assert context["entry"]["missing_details"][0]["current_value"] == "낮아짐"
    assert context["entry"]["missing_details"][0]["required_value"] == "최근 저점 유지 또는 상승"


def test_previous_analysis_without_price_plan_is_distinguished(tmp_path: Path):
    catalog, stock = _catalog(tmp_path)
    _store(
        catalog,
        stock.id,
        market_date="2026-09-21",
        fingerprint="previous-no-plan",
        reference="100",
        stop=None,
        target1=None,
        target2=None,
    )
    _store(
        catalog,
        stock.id,
        market_date="2026-09-22",
        fingerprint="current",
        reference="102",
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)

    assert context["previous_plan"]["state"] == "PREVIOUS_PLAN_UNAVAILABLE"
    assert context["previous_plan"]["previous_market_date"] == "2026-09-21"
    assert context["previous_plan"]["previous_reference_price"] == "100"


'''
    return replace_once(source, insert_before, additions + insert_before, "new G.4.1 tests")


def patch_service(source: str) -> str:
    old = '''export type HoldingDecisionEntry = {
  state: "READY" | "WATCH" | "NOT_READY" | "BLOCKED" | "CAUTION" | "NO_TRADE" | "UNKNOWN" | string;
  label: string;
  summary: string | null;
  decision_reason: string | null;
  missing: number | null;
  total: number | null;
  warnings: string[];
};
'''
    new = '''export type HoldingConditionDetail = {
  label: string;
  detail: string | null;
  current_value: string | null;
  required_value: string | null;
  raw: string | null;
};

export type HoldingDecisionEntry = {
  state: "READY" | "WATCH" | "NOT_READY" | "BLOCKED" | "CAUTION" | "NO_TRADE" | "UNKNOWN" | string;
  label: string;
  summary: string | null;
  decision_reason: string | null;
  passed: number | null;
  missing: number | null;
  total: number | null;
  warnings: string[];
  missing_details: HoldingConditionDetail[];
};
'''
    source = replace_once(source, old, new, "frontend decision entry type")

    old = '''export type HoldingPreviousPlanContext = {
  state: "NO_PREVIOUS_PLAN" | "WITHIN_PLAN" | "STOP_BREACHED" | "TARGET1_REACHED" | "TARGET2_REACHED" | string;
  label: string;
  previous_market_date: string | null;
  previous_stop_price: string | null;
  previous_target1_price: string | null;
  previous_target2_price: string | null;
  current_close: string | null;
};
'''
    new = '''export type HoldingPreviousPlanContext = {
  state: "FIRST_PLAN" | "PREVIOUS_PLAN_UNAVAILABLE" | "WITHIN_PLAN" | "STOP_BREACHED" | "TARGET1_REACHED" | "TARGET2_REACHED" | string;
  label: string;
  previous_market_date: string | null;
  previous_reference_price: string | null;
  previous_stop_price: string | null;
  previous_target1_price: string | null;
  previous_target2_price: string | null;
  current_close: string | null;
};
'''
    return replace_once(source, old, new, "frontend plan type")


def patch_workspace(source: str) -> str:
    old = '''const actionLabel: Record<string, string> = {
  READY: "진입 조건 확인",
  WATCH: "지켜보기",
  NO_TRADE: "지금은 관망",
  NOT_READY: "조건 더 필요",
  CAUTION: "주의하며 관찰",
  BLOCKED: "지금은 관망",
};
'''
    new = '''const actionLabel: Record<string, string> = {
  READY: "진입 후보",
  WATCH: "관심 유지",
  NO_TRADE: "신규 진입 제외",
  NOT_READY: "현재 우선순위 낮음",
  CAUTION: "주의하며 관찰",
  BLOCKED: "위험 때문에 보류",
};
'''
    source = replace_once(source, old, new, "frontend fallback labels")

    old = '''function holdingManagementText(context: HoldingDecisionContext | null | undefined) {
  switch (context?.previous_plan.state) {
    case "STOP_BREACHED":
      return "확인이 필요한 가격 구간";
    case "TARGET1_REACHED":
    case "TARGET2_REACHED":
      return "목표 가격 도달 구간";
    case "WITHIN_PLAN":
      return "이전 계획 범위 내";
    default:
      return "비교할 이전 계획 없음";
  }
}
'''
    new = '''function holdingManagementText(context: HoldingDecisionContext | null | undefined) {
  switch (context?.previous_plan.state) {
    case "STOP_BREACHED":
      return "확인이 필요한 가격 구간";
    case "TARGET1_REACHED":
    case "TARGET2_REACHED":
      return "목표 가격 도달 구간";
    case "WITHIN_PLAN":
      return "이전 계획 범위 내";
    case "FIRST_PLAN":
      return "첫 계획 기준 저장됨";
    case "PREVIOUS_PLAN_UNAVAILABLE":
      return "이전 계획 정보 확인 필요";
    default:
      return "가격 계획 확인 필요";
  }
}

function conditionCountText(context: HoldingDecisionContext | null | undefined) {
  const total = context?.entry.total;
  const missing = context?.entry.missing;
  if (total == null || missing == null) return null;
  return `현재 전략 조건 ${total}개 중 ${missing}개가 부족합니다.`;
}

function entryGuidanceText(context: HoldingDecisionContext | null | undefined) {
  if (!context) return "현재 판단 근거를 확인할 수 없습니다.";
  const count = conditionCountText(context);
  switch (context.entry.state) {
    case "READY":
      return "현재 전략 조건과 손절·목표 위험 기준이 진입 후보로 다시 검토할 수 있는 수준입니다.";
    case "WATCH":
      return `${count ? `${count} ` : ""}일부 조건은 부족하지만 현재 전략 흐름은 남아 있어 다음 확정 일봉에서 계속 확인합니다.`;
    case "NOT_READY":
      return `${count ? `${count} ` : ""}현재는 신규 진입 관점에서 우선순위가 낮아 적극적으로 볼 단계는 아닙니다.`;
    case "BLOCKED":
      return "전략 조건은 갖춰졌지만 현재 위험 구조 때문에 신규 진입 후보로 보기 어렵습니다.";
    case "CAUTION":
      return "조건은 갖춰졌지만 손절 폭이나 목표 여유에 주의가 필요해 관찰이 필요합니다.";
    case "NO_TRADE":
      return "현재는 신규 진입 후보로 보기 어렵습니다. 다음 확정 일봉에서 조건 변화를 다시 확인합니다.";
    default:
      return context.entry.summary ?? "현재 판단 근거를 확인할 수 없습니다.";
  }
}

function planGuidanceText(
  context: HoldingDecisionContext | null | undefined,
  marketDate: string | null | undefined,
) {
  if (!context) return null;
  const plan = context.previous_plan;
  const previousDate = plan.previous_market_date ? compactDate(plan.previous_market_date) : null;
  switch (plan.state) {
    case "FIRST_PLAN":
      return `${compactDate(marketDate)}의 기준가·손절·목표 가격을 첫 비교 계획으로 저장했습니다. 다음 확정 일봉 분석부터 이 계획과 비교합니다.`;
    case "PREVIOUS_PLAN_UNAVAILABLE":
      return previousDate
        ? `${previousDate} 분석은 있지만 비교 가능한 손절·목표 가격 정보가 충분하지 않습니다.`
        : "이전 분석의 가격 계획 정보를 확인할 수 없습니다.";
    case "STOP_BREACHED":
      return `${previousDate ?? "이전"} 계획의 손절 기준 ${money(plan.previous_stop_price)}보다 현재 확정 종가 ${money(plan.current_close)}가 낮거나 같습니다.`;
    case "TARGET2_REACHED":
      return `현재 확정 종가 ${money(plan.current_close)}가 ${previousDate ?? "이전"} 계획의 2차 목표 ${money(plan.previous_target2_price)} 이상입니다.`;
    case "TARGET1_REACHED":
      return `현재 확정 종가 ${money(plan.current_close)}가 ${previousDate ?? "이전"} 계획의 1차 목표 ${money(plan.previous_target1_price)} 이상입니다.`;
    case "WITHIN_PLAN":
      return `${previousDate ?? "이전"} 계획과 현재 확정 종가를 비교했으며 현재는 이전 계획 범위 안에 있습니다.`;
    default:
      return null;
  }
}

function previousPlanActionLabel(context: HoldingDecisionContext | null | undefined) {
  const plan = context?.previous_plan;
  if (!plan || plan.state === "FIRST_PLAN" || !plan.previous_market_date) return null;
  return plan.state === "PREVIOUS_PLAN_UNAVAILABLE" ? "과거 분석 보기" : "이전 계획 보기";
}
'''
    source = replace_once(source, old, new, "frontend explanation helpers")

    old = '''  const [refreshingAnalysis, setRefreshingAnalysis] = useState(false);
  const [chartRefreshKey, setChartRefreshKey] = useState(0);
  const [syncingKis, setSyncingKis] = useState(false);
'''
    new = '''  const [refreshingAnalysis, setRefreshingAnalysis] = useState(false);
  const [chartRefreshKey, setChartRefreshKey] = useState(0);
  const [syncingKis, setSyncingKis] = useState(false);
  const [showMissingConditions, setShowMissingConditions] = useState(false);
  const [showPreviousPlan, setShowPreviousPlan] = useState(false);
'''
    source = replace_once(source, old, new, "frontend disclosure state")

    old = '''  useEffect(() => {
    if (selectedStockId) void loadSelected(selectedStockId);
  }, [selectedStockId]);
'''
    new = '''  useEffect(() => {
    setShowMissingConditions(false);
    setShowPreviousPlan(false);
    if (selectedStockId) void loadSelected(selectedStockId);
  }, [selectedStockId]);
'''
    source = replace_once(source, old, new, "frontend disclosure reset")

    old = '''                    <>
                      <dl className="holdings-key-values">
                        <div>
                          <dt>진입 상태</dt>
                          <dd>
                            {detail.decision_context?.entry.label
                              ?? actionLabel[selectedAnalysis.action_state]
                              ?? selectedAnalysis.action_state}
                          </dd>
                        </div>
                        <div><dt>현재 전략</dt><dd>{strategyLabel[selectedAnalysis.strategy_key] ?? selectedAnalysis.strategy_key}</dd></div>
                        <div><dt>전략 변화</dt><dd>{strategyChangeText(detail.decision_context)}</dd></div>
                        <div>
                          <dt>가격 계획</dt>
                          <dd className={`holdings-plan-text ${planStateClass(detail.decision_context)}`}>
                            {detail.decision_context?.previous_plan.label ?? "비교할 이전 계획 없음"}
                          </dd>
                        </div>
                        {detail.is_held && (
                          <div><dt>보유 관리</dt><dd>{holdingManagementText(detail.decision_context)}</dd></div>
                        )}
                        <div><dt>위험 계산</dt><dd>{riskLabel[selectedAnalysis.risk_state] ?? selectedAnalysis.risk_state}</dd></div>
                        <div><dt>분석 기준일</dt><dd>{compactDate(selectedAnalysis.market_date)}</dd></div>
                      </dl>
                      {detail.decision_context?.entry.summary && (
                        <p className="holdings-decision-summary">{detail.decision_context.entry.summary}</p>
                      )}
                    </>
'''
    new = '''                    <>
                      <dl className="holdings-key-values">
                        <div>
                          <dt>진입 상태</dt>
                          <dd>
                            {detail.decision_context?.entry.label
                              ?? actionLabel[selectedAnalysis.action_state]
                              ?? selectedAnalysis.action_state}
                          </dd>
                        </div>
                        <div><dt>현재 전략</dt><dd>{strategyLabel[selectedAnalysis.strategy_key] ?? selectedAnalysis.strategy_key}</dd></div>
                        <div><dt>전략 변화</dt><dd>{strategyChangeText(detail.decision_context)}</dd></div>
                        <div>
                          <dt>가격 계획</dt>
                          <dd className={`holdings-plan-text ${planStateClass(detail.decision_context)}`}>
                            {detail.decision_context?.previous_plan.label ?? "가격 계획 확인 필요"}
                          </dd>
                        </div>
                        {detail.is_held && (
                          <div><dt>보유 관리</dt><dd>{holdingManagementText(detail.decision_context)}</dd></div>
                        )}
                        <div><dt>위험 계산</dt><dd>{riskLabel[selectedAnalysis.risk_state] ?? selectedAnalysis.risk_state}</dd></div>
                        <div><dt>분석 기준일</dt><dd>{compactDate(selectedAnalysis.market_date)}</dd></div>
                      </dl>

                      <div className="holdings-decision-explain">
                        <p>{entryGuidanceText(detail.decision_context)}</p>
                        {planGuidanceText(detail.decision_context, selectedAnalysis.market_date) && (
                          <p className="holdings-plan-guidance">
                            {planGuidanceText(detail.decision_context, selectedAnalysis.market_date)}
                          </p>
                        )}

                        <div className="holdings-decision-actions">
                          {(detail.decision_context?.entry.missing_details.length ?? 0) > 0 && (
                            <button
                              type="button"
                              className="holdings-inline-toggle"
                              onClick={() => setShowMissingConditions((value) => !value)}
                            >
                              {showMissingConditions
                                ? "부족한 조건 닫기"
                                : `부족한 조건 ${detail.decision_context?.entry.missing_details.length ?? 0}개 보기`}
                            </button>
                          )}
                          {previousPlanActionLabel(detail.decision_context) && (
                            <button
                              type="button"
                              className="holdings-inline-toggle"
                              onClick={() => setShowPreviousPlan((value) => !value)}
                            >
                              {showPreviousPlan
                                ? "이전 계획 닫기"
                                : previousPlanActionLabel(detail.decision_context)}
                            </button>
                          )}
                        </div>

                        {showMissingConditions && detail.decision_context && (
                          <div className="holdings-decision-expand">
                            <strong>부족한 조건</strong>
                            {detail.decision_context.entry.missing_details.map((condition, index) => (
                              <div className="holdings-condition-row" key={`${condition.raw ?? condition.label}-${index}`}>
                                <strong>{condition.label}</strong>
                                {(condition.current_value || condition.required_value) && (
                                  <span>
                                    {condition.current_value ? `현재 ${condition.current_value}` : ""}
                                    {condition.current_value && condition.required_value ? " · " : ""}
                                    {condition.required_value ? `필요 ${condition.required_value}` : ""}
                                  </span>
                                )}
                                {condition.detail && <small>{condition.detail}</small>}
                              </div>
                            ))}
                          </div>
                        )}

                        {showPreviousPlan && detail.decision_context?.previous_plan.previous_market_date && (
                          <div className="holdings-decision-expand">
                            <strong>
                              이전 계획 · {compactDate(detail.decision_context.previous_plan.previous_market_date)}
                            </strong>
                            <dl className="holdings-previous-plan">
                              <div><dt>기준가</dt><dd>{money(detail.decision_context.previous_plan.previous_reference_price)}</dd></div>
                              <div><dt>손절 기준</dt><dd>{money(detail.decision_context.previous_plan.previous_stop_price)}</dd></div>
                              <div><dt>1차 목표</dt><dd>{money(detail.decision_context.previous_plan.previous_target1_price)}</dd></div>
                              <div><dt>2차 목표</dt><dd>{money(detail.decision_context.previous_plan.previous_target2_price)}</dd></div>
                              <div><dt>현재 확정 종가</dt><dd>{money(detail.decision_context.previous_plan.current_close)}</dd></div>
                            </dl>
                          </div>
                        )}
                      </div>
                    </>
'''
    return replace_once(source, old, new, "frontend current-analysis explanation")


def patch_css(source: str) -> str:
    if "HOLD.1-G.4.1" in source:
        fail("holdings.css already appears to contain G.4.1.")
    addition = '''/* HOLD.1-G.4.1 — explain decision reasons and plan continuity */
.holdings-decision-explain {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid var(--border-subtle);
}
.holdings-decision-explain p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-meta);
  line-height: var(--line-body);
}
.holdings-decision-explain p + p { margin-top: 7px; }
.holdings-plan-guidance { color: var(--text-muted) !important; }
.holdings-decision-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 10px;
}
.holdings-inline-toggle {
  border: 0;
  border-bottom: 1px solid var(--border-strong);
  background: transparent;
  color: var(--accent-primary);
  padding: 2px 0 3px;
  font: inherit;
  font-size: var(--font-meta);
  font-weight: 800;
}
.holdings-inline-toggle:hover { border-bottom-color: var(--accent-primary); }
.holdings-decision-expand {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}
.holdings-decision-expand > strong {
  display: block;
  margin-bottom: 5px;
  color: var(--text-primary);
  font-size: var(--font-meta);
}
.holdings-condition-row {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.holdings-condition-row:last-child { border-bottom: 0; }
.holdings-condition-row strong,
.holdings-condition-row span,
.holdings-condition-row small { display: block; }
.holdings-condition-row strong {
  color: var(--text-primary);
  font-size: var(--font-meta);
}
.holdings-condition-row span {
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: var(--font-badge);
}
.holdings-condition-row small {
  margin-top: 3px;
  color: var(--text-muted);
  line-height: var(--line-body);
}
.holdings-previous-plan {
  display: grid;
  grid-template-columns: minmax(92px, .7fr) 1fr;
  gap: 0 16px;
}
.holdings-previous-plan div { display: contents; }
.holdings-previous-plan dt,
.holdings-previous-plan dd {
  margin: 0;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--font-meta);
}
.holdings-previous-plan dt { color: var(--text-muted); }
.holdings-previous-plan dd {
  color: var(--text-primary);
  font-weight: 800;
  text-align: right;
}
'''
    return source.rstrip() + "\n\n" + addition + "\n"


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-G.4.1 — 판단 문구·근거·가격계획 UX 보완")
    print("Decision logic change: NO")
    print("New thresholds: NO")
    print("DB schema change: NO")
    print("KRX/KIS calls: NO")
    print("Market Store write: NO")
    print("Theme support: LIGHT + DARK")

    required = [
        DECISION, DECISION_TEST, HOLDINGS_API, ANALYSIS, ANALYSIS_HISTORY,
        SCANNER, CHART, SERVICE, WORKSPACE, CSS, PACKAGE,
    ]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")

    originals = {
        DECISION: DECISION.read_text(encoding="utf-8-sig"),
        DECISION_TEST: DECISION_TEST.read_text(encoding="utf-8-sig"),
        SERVICE: SERVICE.read_text(encoding="utf-8-sig"),
        WORKSPACE: WORKSPACE.read_text(encoding="utf-8-sig"),
        CSS: CSS.read_text(encoding="utf-8-sig"),
    }

    preflight = {
        "G.4 WATCH label": '"WATCH": "조건 형성 중"' in originals[DECISION],
        "G.4 first-plan placeholder": '"NO_PREVIOUS_PLAN": "비교할 이전 계획 없음"' in originals[DECISION],
        "G.4 frontend": "strategyChangeText" in originals[WORKSPACE],
        "G.3 chart refresh": "chartRefreshKey" in originals[WORKSPACE],
    }
    for name, ok in preflight.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not all(preflight.values()):
        fail("HOLD.1-G.4 is not in the expected pre-G.4.1 state.")

    protected = {
        "api": sha256(HOLDINGS_API),
        "analysis": sha256(ANALYSIS),
        "analysis_history": sha256(ANALYSIS_HISTORY),
        "scanner": sha256(SCANNER),
        "chart": sha256(CHART),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
        "market_store": tree_hash(BACKEND / "app" / "backtest" / "market_store.py"),
    }

    try:
        DECISION.write_text(patch_decision(originals[DECISION]), encoding="utf-8", newline="\n")
        DECISION_TEST.write_text(patch_test(originals[DECISION_TEST]), encoding="utf-8", newline="\n")
        SERVICE.write_text(patch_service(originals[SERVICE]), encoding="utf-8", newline="\n")
        WORKSPACE.write_text(patch_workspace(originals[WORKSPACE]), encoding="utf-8", newline="\n")
        CSS.write_text(patch_css(originals[CSS]), encoding="utf-8", newline="\n")

        print()
        print("=== HOLD.1-G.4.1 STATIC CONTRACT ===")
        decision_now = DECISION.read_text(encoding="utf-8")
        service_now = SERVICE.read_text(encoding="utf-8")
        workspace_now = WORKSPACE.read_text(encoding="utf-8")
        css_now = CSS.read_text(encoding="utf-8")
        package_now = PACKAGE.read_text(encoding="utf-8").lower()

        checks = {
            "WATCH -> 관심 유지": '"WATCH": "관심 유지"' in decision_now,
            "NOT_READY -> 현재 우선순위 낮음": '"NOT_READY": "현재 우선순위 낮음"' in decision_now,
            "CAUTION -> 주의하며 관찰": '"CAUTION": "주의하며 관찰"' in decision_now,
            "vague backend labels removed": "조건 형성 중" not in decision_now and '"조건 부족"' not in decision_now,
            "missing details exposed": '"missing_details": missing_details' in decision_now,
            "FIRST_PLAN": '"FIRST_PLAN": "첫 계획 설정됨"' in decision_now,
            "previous unavailable distinct": '"PREVIOUS_PLAN_UNAVAILABLE": "이전 가격 계획 정보 없음"' in decision_now,
            "previous reference exposed": '"previous_reference_price": _decimal_text(previous_reference)' in decision_now,
            "same-day revisions excluded": "r.id=d.current_revision_id" in decision_now and "ORDER BY d.market_date DESC" in decision_now and "LIMIT 2" in decision_now,
            "frontend condition disclosure": "부족한 조건 ${detail.decision_context?.entry.missing_details.length ?? 0}개 보기" in workspace_now,
            "frontend previous plan disclosure": '"이전 계획 보기"' in workspace_now and '"과거 분석 보기"' in workspace_now,
            "first-plan continuity copy": "첫 비교 계획으로 저장했습니다" in workspace_now,
            "NOT_READY explanation": "신규 진입 관점에서 우선순위가 낮아 적극적으로 볼 단계는 아닙니다" in workspace_now,
            "no buy/sell instruction": all(word not in workspace_now for word in ("매수하세요", "매도하세요", "손절하세요")),
            "typed condition evidence": "export type HoldingConditionDetail" in service_now and "missing_details: HoldingConditionDetail[]" in service_now,
            "no theme fork": 'html[data-theme=' not in css_now and ":root" not in css_now,
            "theme tokens reused": "var(--text-primary)" in css_now and "var(--border-subtle)" in css_now,
            "no paid chart dependency": all(name not in package_now for name in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly")),
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
                "backend/tests/test_holdings_decision_context_hold1g4.py",
                "backend/tests/test_holdings_api_hold1f.py",
                "backend/tests/test_holdings_analysis_history_hold1e.py",
                "backend/tests/test_holdings_freshness_hold1g3.py",
                "backend/tests/test_holdings_chart_hold1g.py",
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
            "api": sha256(HOLDINGS_API),
            "analysis": sha256(ANALYSIS),
            "analysis_history": sha256(ANALYSIS_HISTORY),
            "scanner": sha256(SCANNER),
            "chart": sha256(CHART),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
            "market_store": tree_hash(BACKEND / "app" / "backtest" / "market_store.py"),
        }
        if protected_after != protected:
            fail("Protected API/Analysis/Scanner/Strategy/Risk/KIS/Market Store/Chart source changed.")

        print()
        print("HOLD.1-G.4.1 IMPLEMENTATION READY")
        print("Modified:")
        print(" - backend/app/holdings/decision_context.py")
        print(" - backend/tests/test_holdings_decision_context_hold1g4.py")
        print(" - frontend/src/services/holdingsApi.ts")
        print(" - frontend/src/components/HoldingsWorkspace.tsx")
        print(" - frontend/src/holdings.css")
        print("WATCH -> 관심 유지: PASS")
        print("NOT_READY -> 현재 우선순위 낮음: PASS")
        print("Missing-condition disclosure: PASS")
        print("FIRST_PLAN continuity copy: PASS")
        print("Previous-plan disclosure: PASS")
        print("Decision threshold changes: 0")
        print("DB schema changes: 0")
        print("KRX/KIS calls: 0")
        print("Market Store write: 0")
        print("Frontend build: PASS")
        print()
        print("NEXT UAT:")
        print(" - SK하이닉스: 관심 유지 + 부족한 조건 보기")
        print(" - 대한항공: 진입 후보, 부족한 조건 버튼 없음")
        print(" - 엘브이엠씨홀딩스: 현재 우선순위 낮음 + 설명")
        print(" - 첫 분석 종목: 가격 계획이 '첫 계획 설정됨'")
        print(" - 이전 거래일이 있는 종목: '이전 계획 보기' 펼침")
        return 0

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        print()
        print("FAILED — HOLD.1-G.4.1 changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
