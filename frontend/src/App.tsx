import { useEffect, useState } from "react";
import NumericStepper, { formatIntegerInput, parseFormattedNumber } from "./components/NumericStepper";
import { BeginnerGlossary, BeginnerIndicatorSummary, TermHelp } from "./components/BeginnerHelp";
import { AnalysisDetailHeader, AnalysisHub, PullbackConfirmationPanel, type AnalysisSection } from "./components/AnalysisHub";
import { FundamentalPanel } from "./components/FundamentalPanel";
import { InvestorStylePanel } from "./components/InvestorStylePanel";
import BacktestPanel from "./components/BacktestPanel";
import ScannerPanel from "./components/ScannerPanel";
import TrackingWorkspace from "./components/TrackingWorkspace";
import HoldingsWorkspace from "./components/HoldingsWorkspace";
import StockAnalysisWorkspace from "./components/StockAnalysisWorkspace";
import MarketOverviewWorkspace from "./components/MarketOverviewWorkspace";
import {
  fetchHealth,
  fetchMarketDashboard,
  fetchMarketHistory,
  fetchProviderStatus,
  fetchStockContext,
  fetchStrategyAnalysis,
  searchStocks,
  type IndexPoint,
  type MarketDashboard,
  type ProviderStatus,
  type StockContext,
  type StrategyAnalysis,
  type StockSearchItem,
} from "./services/api";

type AppPage = "dashboard" | "analysis" | "backtest" | "scanner" | "simulation" | "holdings";
type ThemeMode = "light" | "dark";

function initialTheme(): ThemeMode {
  const saved = window.localStorage.getItem("stockscope-theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.dataset.theme = saved;
    return saved;
  }
  const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  const resolved: ThemeMode = systemDark ? "dark" : "light";
  document.documentElement.dataset.theme = resolved;
  return resolved;
}

function pageFromPathname(pathname: string): AppPage {
  const lower = pathname.toLowerCase();
  if (lower.startsWith("/holdings")) return "holdings";
  if (lower.startsWith("/simulation")) return "simulation";
  if (lower.startsWith("/scanner")) return "scanner";
  if (lower.startsWith("/backtest")) return "backtest";
  if (lower.startsWith("/analysis")) return "analysis";
  return "dashboard";
}

function number(value: number | null | undefined, suffix = "") {
  if (value == null) return "-";
  return `${new Intl.NumberFormat("ko-KR").format(value)}${suffix}`;
}

function compactMoney(value: number | null | undefined) {
  if (value == null) return "-";
  if (Math.abs(value) >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(1)}조`;
  if (Math.abs(value) >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}억`;
  if (Math.abs(value) >= 10_000) return `${(value / 10_000).toFixed(1)}만`;
  return number(value);
}

function signedRate(value: number | null | undefined) {
  if (value == null) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function rateClass(value: number | null | undefined) {
  if ((value ?? 0) > 0) return "positive";
  if ((value ?? 0) < 0) return "negative";
  return "neutral";
}

function Sparkline({ points }: { points: IndexPoint[] }) {
  const values = points.map((point) => point.close).filter((value): value is number => value != null);
  if (values.length < 2) return <div className="spark-empty">데이터 준비 중</div>;
  const width = 190;
  const height = 56;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 8) - 4;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} aria-label="최근 지수 흐름">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IndexCard({
  name,
  point,
  history,
}: {
  name: string;
  point: IndexPoint;
  history: IndexPoint[];
}) {
  return (
    <article className="summary-card index-card">
      <div>
        <span className="summary-label">{name}</span>
        <strong className="summary-value">{number(point?.close)}</strong>
        <span className={`summary-change ${rateClass(point?.change_rate)}`}>{signedRate(point?.change_rate)}</span>
      </div>
      <Sparkline points={history} />
    </article>
  );
}

export default function App() {
  const [apiStatus, setApiStatus] = useState("확인 중");
  const [theme, setTheme] = useState<ThemeMode>(initialTheme);

  useEffect(() => {
    const favicon = document.getElementById("stockscope-favicon") as HTMLLinkElement | null;
    if (favicon) {
      favicon.href = theme === "dark" ? "/stockscope-icon-dark.png" : "/stockscope-icon-light.png";
    }
  }, [theme]);
  const [providers, setProviders] = useState<ProviderStatus | null>(null);
  const [dashboard, setDashboard] = useState<MarketDashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [appPage, setAppPage] = useState<AppPage>(() => pageFromPathname(window.location.pathname));
  const [stockCode, setStockCode] = useState("005930");
  const [stockMarket, setStockMarket] = useState<"KOSPI" | "KOSDAQ">("KOSPI");
  const [stockQuery, setStockQuery] = useState("삼성전자 (005930)");
  const [selectedStockName, setSelectedStockName] = useState("삼성전자");
  const [stockSearchResults, setStockSearchResults] = useState<StockSearchItem[]>([]);
  const [stockSearchBusy, setStockSearchBusy] = useState(false);
  const [stockSearchOpen, setStockSearchOpen] = useState(false);
  const [stock, setStock] = useState<StockContext | null>(null);
  const [stockMessage, setStockMessage] = useState("종목코드로 KRX + OpenDART 통합 조회 가능");
  const [stockBusy, setStockBusy] = useState(false);
  const [strategyAnalysis, setStrategyAnalysis] = useState<StrategyAnalysis | null>(null);
  const [strategyBusy, setStrategyBusy] = useState(false);
  const [strategyMessage, setStrategyMessage] = useState("종목 조회 후 실제 기술지표 기반 전략 분석을 실행할 수 있습니다.");
  const [referencePriceInput, setReferencePriceInput] = useState("");
  const [referenceHighInput, setReferenceHighInput] = useState("");
  const [referenceLowInput, setReferenceLowInput] = useState("");
  const [referenceVolumeInput, setReferenceVolumeInput] = useState("");
  const [positionMode, setPositionMode] = useState<"NOT_HELD" | "HOLDING">("NOT_HELD");
  const [averagePriceInput, setAveragePriceInput] = useState("");
  const [holdingQuantityInput, setHoldingQuantityInput] = useState("");
  const [lastAnalysisInputSignature, setLastAnalysisInputSignature] = useState("");
  const [analysisSection, setAnalysisSection] = useState<AnalysisSection>("summary");
  const [selectedStrategyIndex, setSelectedStrategyIndex] = useState(0);
  const [scannerOrigin, setScannerOrigin] = useState(false);

  const analysisInputSignature = [
    stockCode,
    stockMarket,
    referencePriceInput,
    referenceHighInput,
    referenceLowInput,
    referenceVolumeInput,
    positionMode,
    averagePriceInput,
    holdingQuantityInput,
  ].join("|");
  const analysisOutdated = Boolean(
    strategyAnalysis &&
      lastAnalysisInputSignature &&
      analysisInputSignature !== lastAnalysisInputSignature,
  );
  const selectedStrategyIndexSafe = strategyAnalysis
    ? Math.min(selectedStrategyIndex, Math.max(strategyAnalysis.strategies.length - 1, 0))
    : 0;
  const selectedStrategy = strategyAnalysis?.strategies[selectedStrategyIndexSafe] ?? null;

  async function loadDashboard() {
    setLoading(true);
    setDashboardError(null);
    try {
      // 1) 최신 시장 데이터부터 표시합니다.
      const result = await fetchMarketDashboard();
      setDashboard(result);
      setLoading(false);

      // 2) 최근 지수 차트는 백그라운드에서 늦게 붙입니다.
      // 히스토리 실패는 핵심 시장 데이터 표시를 막지 않습니다.
      void fetchMarketHistory()
        .then((history) => {
          setDashboard((current) =>
            current
              ? {
                  ...current,
                  history: { kospi: history.kospi, kosdaq: history.kosdaq },
                }
              : current,
          );
        })
        .catch(() => {
          // Sparkline만 비워두고 대시보드는 계속 사용합니다.
        });
    } catch (error) {
      setDashboardError(error instanceof Error ? error.message : "시장 대시보드 조회 실패");
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchHealth()
      .then((data) => setApiStatus(data.status === "ok" ? "정상" : "오류"))
      .catch(() => setApiStatus("연결 실패"));
    fetchProviderStatus().then(setProviders).catch(() => setProviders(null));

    if (window.location.pathname === "/") {
      window.history.replaceState({}, "", "/dashboard");
    }

    const handlePopState = () => {
      setAppPage(pageFromPathname(window.location.pathname));
      window.scrollTo({ top: 0, behavior: "auto" });
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (appPage === "dashboard" && dashboard == null && !loading) {
      void loadDashboard();
    }
  }, [appPage]);

  useEffect(() => {
    const query = stockQuery.trim();
    const selectedLabel = selectedStockName ? `${selectedStockName} (${stockCode})` : "";
    if (query === selectedLabel || query.length < 2) {
      setStockSearchResults([]);
      setStockSearchBusy(false);
      return;
    }

    const timer = window.setTimeout(() => {
      setStockSearchBusy(true);
      void searchStocks(query)
        .then((result) => {
          setStockSearchResults(result.rows);
          setStockSearchOpen(true);
        })
        .catch(() => {
          setStockSearchResults([]);
          setStockSearchOpen(true);
        })
        .finally(() => setStockSearchBusy(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [stockQuery, stockCode, selectedStockName]);

  function chooseStock(
    item: StockSearchItem,
    options: { loadContext?: boolean; origin?: "scanner" | null } = {},
  ) {
    const normalizedCode = item.code.trim().toUpperCase();
    const shouldLoadContext = options.loadContext ?? appPage === "analysis";
    setScannerOrigin(options.origin === "scanner");
    setStockCode(normalizedCode);
    setStockMarket(item.market);
    setSelectedStockName(item.name);
    setStockQuery(`${item.name} (${item.code})`);
    setStockSearchResults([]);
    setStockSearchOpen(false);
    setStock(null);
    setStrategyAnalysis(null);
    setSelectedStrategyIndex(0);
    setLastAnalysisInputSignature("");
    setReferencePriceInput("");
    setReferenceHighInput("");
    setReferenceLowInput("");
    setReferenceVolumeInput("");
    setPositionMode("NOT_HELD");
    setAveragePriceInput("");
    setHoldingQuantityInput("");
    setStockMessage(`${item.market} · ${item.name} 선택됨`);

    if (shouldLoadContext) {
      setStockBusy(true);
      setStockMessage(`${item.name} 기본 정보 불러오는 중...`);
      void fetchStockContext(normalizedCode, item.market)
        .then((result) => {
          setStock(result);
          setStrategyAnalysis(null);
          setSelectedStrategyIndex(0);
          setLastAnalysisInputSignature("");
          setStockMessage(`${result.company.corp_name ?? result.stock.name ?? item.code} 조회 완료`);
        })
        .catch((error) => {
          setStock(null);
          setStrategyAnalysis(null);
          setSelectedStrategyIndex(0);
          setLastAnalysisInputSignature("");
          setStockMessage(error instanceof Error ? error.message : "종목 조회 실패");
        })
        .finally(() => setStockBusy(false));
    }
  }

  function changeStockQuery(value: string) {
    setStockQuery(value);
    const selectedLabel = selectedStockName ? `${selectedStockName} (${stockCode})` : "";
    if (value !== selectedLabel) {
      setScannerOrigin(false);
      setSelectedStockName("");
      setStockCode("");
      setStock(null);
      setStrategyAnalysis(null);
      setSelectedStrategyIndex(0);
      setLastAnalysisInputSignature("");
      setReferencePriceInput("");
      setReferenceHighInput("");
      setReferenceLowInput("");
      setReferenceVolumeInput("");
      setPositionMode("NOT_HELD");
      setAveragePriceInput("");
      setHoldingQuantityInput("");
    }
  }

  async function quickAnalyze() {
    setStockBusy(true);
    setStockMessage("KRX + OpenDART 통합 조회 중...");
    try {
      const result = await fetchStockContext(stockCode, stockMarket);
      setStock(result);
      setStrategyAnalysis(null);
      setSelectedStrategyIndex(0);
      setLastAnalysisInputSignature("");
      setStockMessage(`${result.company.corp_name ?? result.stock.name ?? stockCode} 조회 완료`);
    } catch (error) {
      setStock(null);
      setStrategyAnalysis(null);
      setSelectedStrategyIndex(0);
      setLastAnalysisInputSignature("");
      setStockMessage(error instanceof Error ? error.message : "종목 조회 실패");
    } finally {
      setStockBusy(false);
    }
  }


const strategyName: Record<string, string> = {
    trend_following: "추세추종",
    pullback: "눌림목",
    breakout: "돌파",
    support_bounce: "지지선 반등",
    oversold_bounce: "과매도 반등",
    range_trading: "박스권 매매",
    momentum_continuation: "모멘텀 지속",
    volatility_squeeze: "변동성 압축 돌파 준비",
    ma20_rebound: "20일선 반등",
    trend_recovery: "추세 회복",
    no_trade: "매매 보류",
  };

  const strategyEasyDescription: Record<string, string> = {
    trend_following: "이미 상승 흐름이 만들어진 종목을 따라가는 방식입니다. 추세가 꺾이기 전까지 흐름을 이용합니다.",
    pullback: "상승하던 종목이 잠깐 내려왔을 때, 지지 구간에서 다시 오르는 흐름을 노리는 방식입니다.",
    breakout: "최근 고점이나 저항 가격을 거래량과 함께 넘어설 때 추가 상승을 기대하는 방식입니다.",
    support_bounce: "주가가 여러 번 버텼던 가격 근처에서 다시 반등하는지를 보는 방식입니다.",
    oversold_bounce: "짧은 기간 너무 많이 떨어진 종목이 일시적으로 되돌아오르는 구간을 노리는 방식입니다.",
    range_trading: "주가가 일정 범위 안에서 오르내릴 때 아래쪽에서는 반등, 위쪽에서는 저항을 보는 방식입니다.",
    momentum_continuation: "가격과 거래량이 동시에 강한 종목의 상승 흐름이 계속 이어지는지를 보는 방식입니다.",
    volatility_squeeze: "가격 변동과 거래량이 줄어든 압축 구간 뒤 큰 움직임이 나올 준비 상태인지 보는 방식입니다.",
    ma20_rebound: "상승 중인 20일 이동평균선 근처에서 주가가 다시 지지를 받는지를 보는 방식입니다.",
    trend_recovery: "조정이나 약세 뒤 주가가 20일선과 저점 구조를 다시 회복하는 초기 전환을 보는 방식입니다.",
    no_trade: "현재는 어느 전략도 조건이 충분하지 않습니다. 억지로 진입하기보다 기다리거나 관찰하는 쪽이 낫다는 뜻입니다.",
  };

  const strategyBeginnerHint: Record<string, string> = {
    trend_following: "쉽게 말해: 이미 잘 가는 흐름에 올라타는 전략",
    pullback: "쉽게 말해: 오르던 종목이 잠깐 쉬어갈 때 들어가는 전략",
    breakout: "쉽게 말해: 막혀 있던 가격을 강하게 뚫을 때 따라가는 전략",
    support_bounce: "쉽게 말해: 자주 버틴 가격에서 튀어 오르는지 보는 전략",
    oversold_bounce: "쉽게 말해: 너무 많이 떨어진 뒤 단기 반등을 노리는 전략",
    range_trading: "쉽게 말해: 박스권 아래에서 사고 위에서 정리하는 관점",
    momentum_continuation: "쉽게 말해: 강하게 오르는 흐름이 계속 살아 있는지 보는 전략",
    volatility_squeeze: "쉽게 말해: 조용히 힘을 모으다가 터지는 구간을 기다리는 전략",
    ma20_rebound: "쉽게 말해: 상승 중인 20일선에 닿고 다시 튀는지 보는 전략",
    trend_recovery: "쉽게 말해: 약해졌던 흐름이 다시 살아나는 초입을 확인하는 전략",
    no_trade: "쉽게 말해: 지금은 굳이 매매하지 않는 편이 낫다는 판단",
  };

  async function runStrategyAnalysis() {
    const parseOptional = (value: string) => {
      const normalized = value.replace(/,/g, "").trim();
      if (!normalized) return undefined;
      const parsed = Number(normalized);
      return Number.isFinite(parsed) ? parsed : Number.NaN;
    };

    const referencePrice = parseOptional(referencePriceInput);
    const referenceHigh = parseOptional(referenceHighInput);
    const referenceLow = parseOptional(referenceLowInput);
    const referenceVolume = parseOptional(referenceVolumeInput);
    const averagePrice = parseOptional(averagePriceInput);
    const holdingQuantity = parseOptional(holdingQuantityInput);

    if (referencePrice != null && (!Number.isFinite(referencePrice) || referencePrice <= 0)) {
      setStrategyMessage("현재 참고가격은 0보다 큰 숫자로 입력해주세요.");
      return;
    }
    if ((referenceHigh != null || referenceLow != null || referenceVolume != null) && referencePrice == null) {
      setStrategyMessage("오늘 고가·저가·거래량을 사용할 때는 현재 참고가격도 함께 입력해주세요.");
      return;
    }
    if (referenceHigh != null && (!Number.isFinite(referenceHigh) || referenceHigh <= 0)) {
      setStrategyMessage("오늘 고가는 0보다 큰 숫자로 입력해주세요.");
      return;
    }
    if (referenceLow != null && (!Number.isFinite(referenceLow) || referenceLow <= 0)) {
      setStrategyMessage("오늘 저가는 0보다 큰 숫자로 입력해주세요.");
      return;
    }
    if (referenceVolume != null && (!Number.isFinite(referenceVolume) || referenceVolume < 0)) {
      setStrategyMessage("현재 거래량은 0 이상의 숫자로 입력해주세요.");
      return;
    }
    if (positionMode === "HOLDING" && (averagePrice == null || !Number.isFinite(averagePrice) || averagePrice <= 0)) {
      setStrategyMessage("보유 중으로 분석하려면 평균 매수가를 입력해주세요.");
      return;
    }
    if (holdingQuantity != null && (!Number.isFinite(holdingQuantity) || holdingQuantity <= 0)) {
      setStrategyMessage("보유 수량은 0보다 큰 숫자로 입력해주세요.");
      return;
    }

    const scrollPosition = window.scrollY;
    const requestInputSignature = analysisInputSignature;
    setStrategyBusy(true);
    setStrategyMessage(
      referencePrice
        ? "확정 EOD 분석과 현재 참고가격 시나리오를 각각 계산해 전략 변화까지 비교 중..."
        : "최근 KRX 확정 데이터로 EOD 전략 적합도를 계산 중...",
    );
    try {
      const result = await fetchStrategyAnalysis(
        stockCode,
        stockMarket,
        referencePrice,
        referenceHigh,
        referenceLow,
        referenceVolume,
        positionMode,
        averagePrice,
        holdingQuantity,
      );
      setStrategyAnalysis(result);
      setSelectedStrategyIndex(0);
      setAnalysisSection("summary");
      setLastAnalysisInputSignature(requestInputSignature);
      const topName = result.risk_gate.active
        ? "매매 보류"
        : result.best_regular_strategy
          ? (strategyName[result.best_regular_strategy.strategy] ?? result.best_regular_strategy.strategy)
          : "매매 보류";
      setStrategyMessage(`${result.history_points}거래일 분석 완료 · ${result.position_context.label} 기준 · 현재 판단: ${topName}`);
    } catch (error) {
      setStrategyAnalysis(null);
      setSelectedStrategyIndex(0);
      setLastAnalysisInputSignature("");
      setStrategyMessage(error instanceof Error ? error.message : "전략 분석 실패");
    } finally {
      setStrategyBusy(false);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          window.scrollTo({ top: scrollPosition, behavior: "auto" });
        });
      });
    }
  }

  function navigateAnalysis(section: AnalysisSection) {
    setAnalysisSection(section);
    if (section === "summary") return;
    requestAnimationFrame(() => {
      document.getElementById("analysis-detail-stage")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function toggleTheme() {
    const next: ThemeMode = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("stockscope-theme", next);
  }

  function navigateApp(page: AppPage) {
    const pathname = `/${page}`;
    if (window.location.pathname !== pathname) window.history.pushState({}, "", pathname);
    setAppPage(page);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function openHoldingsForStock(target: { market: "KOSPI" | "KOSDAQ"; ticker: string; name: string }) {
    try {
      window.sessionStorage.setItem("stockscope-holdings-target", JSON.stringify(target));
    } catch {
      // Direct navigation still works when sessionStorage is unavailable.
    }
    navigateApp("holdings");
  }

  function openAnalysisFromHoldings(item: StockSearchItem) {
    chooseStock(item, { loadContext: true, origin: null });
    navigateApp("analysis");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-wrap">
          <img
            src={theme === "dark" ? "/stockscope-icon-dark.png" : "/stockscope-icon-light.png"}
            alt=""
            aria-hidden="true"
            width={30}
            height={30}
            style={{ borderRadius: 8, display: "block", flex: "0 0 auto" }}
          />
          <strong className="brand">StockScope</strong>
        </div>
        <nav className="topnav" aria-label="주요 기능">
          <button className={`nav-item ${appPage === "dashboard" ? "active" : ""}`} onClick={() => navigateApp("dashboard")}>시장 현황</button>
          <button className={`nav-item ${appPage === "analysis" ? "active" : ""}`} onClick={() => navigateApp("analysis")}>종목 분석</button>
          <button className={`nav-item ${appPage === "backtest" ? "active" : ""}`} onClick={() => navigateApp("backtest")}>종목 과거 성과</button>
          <button className={`nav-item ${appPage === "scanner" ? "active" : ""}`} onClick={() => navigateApp("scanner")}>종목 후보 찾기</button>
          <button className={`nav-item ${appPage === "simulation" ? "active" : ""}`} onClick={() => navigateApp("simulation")}>종목 성과 추적</button>
          <button className={`nav-item ${appPage === "holdings" ? "active" : ""}`} onClick={() => navigateApp("holdings")}>내 종목 관리</button>
        </nav>
        <div className="header-actions">
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            title={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
          >
            <span aria-hidden="true">{theme === "dark" ? "☀" : "🌙"}</span>
            <b>{theme === "dark" ? "라이트" : "다크"}</b>
          </button>
          <div className="header-status">
            <span className={`dot-status ${apiStatus === "정상" ? "ok" : ""}`}>API {apiStatus}</span>
            <span className={`dot-status ${providers?.krx.configured ? "ok" : ""}`}>KRX</span>
            <span className={`dot-status ${providers?.dart.configured ? "ok" : ""}`}>DART</span>
          </div>
        </div>
      </header>

      <div className="layout backtest-layout">
        <main className="content backtest-page-content">
          {appPage === "dashboard" ? (
            <MarketOverviewWorkspace
              dashboard={dashboard}
              loading={loading}
              error={dashboardError}
              onReload={() => void loadDashboard()}
              onNavigate={navigateApp}
            />
          ) : appPage === "analysis" ? (
            <StockAnalysisWorkspace
              stockQuery={stockQuery}
              stockSearchBusy={stockSearchBusy}
              stockSearchOpen={stockSearchOpen}
              stockSearchResults={stockSearchResults}
              selectedStockName={selectedStockName}
              stockCode={stockCode}
              stockMarket={stockMarket}
              stockBusy={stockBusy}
              stockMessage={stockMessage}
              stock={stock}
              strategyAnalysis={strategyAnalysis}
              strategyBusy={strategyBusy}
              analysisOutdated={analysisOutdated}
              onQueryChange={changeStockQuery}
              onSearchFocus={() => stockSearchResults.length > 0 && setStockSearchOpen(true)}
              onChooseStock={chooseStock}
              onLoadContext={() => void quickAnalyze()}
              onRunAnalysis={() => void runStrategyAnalysis()}
              scannerOrigin={scannerOrigin}
              onBackToScanner={() => navigateApp("scanner")}
              onOpenHoldings={openHoldingsForStock}
            >
            {stock && (
              <div className="strategy-test">
                <div className="strategy-test-head">
                  <div>
                    <h3>분석 세부 설정</h3>
                    <p>{strategyMessage}</p>
                  </div>
                  <button type="button" disabled={strategyBusy} onClick={() => void runStrategyAnalysis()}>
                    {strategyBusy ? "분석 중..." : analysisOutdated ? "변경값 다시 분석" : "분석 실행"}
                  </button>
                </div>

                {analysisOutdated && (
                  <div className="analysis-dirty-notice" role="status">
                    <strong>입력값이 변경되었습니다.</strong>
                    <span>아래 분석 결과는 이전 입력 기준입니다. 변경한 가격·평균가·수량을 반영하려면 다시 분석해주세요.</span>
                  </div>
                )}

                <details className="stock-reference-scenario">
                  <summary>
                    <span>
                      <strong>현재 참고가격·보유상태 시나리오</strong>
                      <small>선택 · 공식 확정 일봉 분석을 덮어쓰지 않습니다.</small>
                    </span>
                    <b>펼치기</b>
                  </summary>
                  <div className="stock-reference-scenario-body">
                <div className="reference-price-editor">
                  <div className="reference-copy">
                    <strong>현재 참고가격 입력 <span>선택</span></strong>
                    <p>
                      현재가격은 직접 입력하거나 호가·누적 퍼센트 버튼으로 빠르게 맞출 수 있습니다.
                      장중 고가·저가·누적 거래량은 선택 항목이며, 입력하지 않아도 KRX 확정 일봉 기준으로 분석할 수 있습니다.
                    </p>
                  </div>
                  <div className="reference-input-grid">
                    <label className="primary-stepper-field">
                      <span>현재 참고가격 <b>핵심</b></span>
                      <NumericStepper
                        value={referencePriceInput}
                        onChange={setReferencePriceInput}
                        unit="원"
                        mode="price"
                        placeholder={stock.stock.close ? `예: ${number(stock.stock.close)}` : "현재 참고가격"}
                        seedValue={stock.stock.close}
                        baseValue={stock.stock.close}
                        baseLabel="KRX 종가"
                        quickPercentages={[-5, -1, 1, 5]}
                        ariaLabel="현재 참고가격"
                      />
                    </label>
                  </div>

                  <details className="intraday-advanced">
                    <summary>
                      <span>
                        <strong>장중 정보 추가 입력</strong>
                        <small>선택 · 실시간 장중 데이터를 알고 있을 때만 입력</small>
                      </span>
                      <b>펼치기</b>
                    </summary>

                    <div className="intraday-advanced-body">
                      <p>
                        KRX OPEN API는 확정 EOD 데이터 기준이라 오늘 장중 고가·저가·누적 거래량을 자동으로 알 수 없습니다.
                        비워두면 확정 일봉 기준으로 분석하고, 알고 있는 경우에만 아래 값을 보완 입력하세요.
                      </p>

                      <div className="intraday-stepper-grid">
                        <label>
                          <span>오늘 고가 <em>선택</em></span>
                          <NumericStepper
                            value={referenceHighInput}
                            onChange={setReferenceHighInput}
                            unit="원"
                            mode="price"
                            placeholder="미입력"
                            seedValue={parseFormattedNumber(referencePriceInput) ?? stock.stock.close}
                            ariaLabel="오늘 고가"
                          />
                          <button
                            type="button"
                            className="intraday-seed-button"
                            disabled={(parseFormattedNumber(referencePriceInput) ?? stock.stock.close) == null}
                            onClick={() => {
                              const value = parseFormattedNumber(referencePriceInput) ?? stock.stock.close;
                              if (value != null) setReferenceHighInput(formatIntegerInput(String(Math.round(value))));
                            }}
                          >
                            현재 참고가격으로 설정
                          </button>
                        </label>

                        <label>
                          <span>오늘 저가 <em>선택</em></span>
                          <NumericStepper
                            value={referenceLowInput}
                            onChange={setReferenceLowInput}
                            unit="원"
                            mode="price"
                            placeholder="미입력"
                            seedValue={parseFormattedNumber(referencePriceInput) ?? stock.stock.close}
                            ariaLabel="오늘 저가"
                          />
                          <button
                            type="button"
                            className="intraday-seed-button"
                            disabled={(parseFormattedNumber(referencePriceInput) ?? stock.stock.close) == null}
                            onClick={() => {
                              const value = parseFormattedNumber(referencePriceInput) ?? stock.stock.close;
                              if (value != null) setReferenceLowInput(formatIntegerInput(String(Math.round(value))));
                            }}
                          >
                            현재 참고가격으로 설정
                          </button>
                        </label>

                        <label className="volume-stepper-field">
                          <span>현재 누적 거래량 <em>선택</em></span>
                          <NumericStepper
                            value={referenceVolumeInput}
                            onChange={setReferenceVolumeInput}
                            unit="주"
                            mode="volume"
                            placeholder="미입력"
                            seedValue={1000}
                            ariaLabel="현재 누적 거래량"
                          />
                          <small>−/+를 꾹 누르면 거래량 규모에 맞춰 연속 조정됩니다.</small>
                        </label>
                      </div>
                    </div>
                  </details>
                  {(referencePriceInput || referenceHighInput || referenceLowInput || referenceVolumeInput) && (
                    <button
                      type="button"
                      className="reference-reset"
                      onClick={() => {
                        setReferencePriceInput("");
                        setReferenceHighInput("");
                        setReferenceLowInput("");
                        setReferenceVolumeInput("");
                      }}
                    >
                      참고정보 초기화
                    </button>
                  )}
                  <small>사용자 입력값은 현재 분석 요청에만 사용하며 KRX 확정 일봉·캐시·DB에는 저장하지 않습니다.</small>
                </div>

                <div className="position-context-editor">
                  <div className="position-context-head">
                    <div>
                      <strong>내 현재 상태 가정</strong>
                      <p>실제 증권계좌와 연결하지 않고, 참고 시나리오를 내 상황에 맞게 비교하기 위한 입력입니다.</p>
                    </div>
                    <span>실제 주문 없음</span>
                  </div>
                  <div className="position-mode-buttons">
                    <button
                      type="button"
                      className={positionMode === "NOT_HELD" ? "active" : ""}
                      onClick={() => { setPositionMode("NOT_HELD"); setAveragePriceInput(""); setHoldingQuantityInput(""); }}
                    >
                      아직 보유하지 않음
                      <small>신규 진입 관점</small>
                    </button>
                    <button
                      type="button"
                      className={positionMode === "HOLDING" ? "active" : ""}
                      onClick={() => { setPositionMode("HOLDING"); }}
                    >
                      현재 보유 중
                      <small>보유 포지션 관리 관점</small>
                    </button>
                  </div>
                  {positionMode === "HOLDING" && (
                    <div className="holding-inputs">
                      <label>
                        <span>평균 매수가 <b>필수</b></span>
                        <NumericStepper
                          value={averagePriceInput}
                          onChange={setAveragePriceInput}
                          unit="원"
                          mode="price"
                          placeholder="예: 245,000"
                          seedValue={stock.stock.close}
                          ariaLabel="평균 매수가"
                        />
                      </label>
                      <label>
                        <span>보유 수량 <em>선택</em></span>
                        <NumericStepper
                          value={holdingQuantityInput}
                          onChange={setHoldingQuantityInput}
                          unit="주"
                          mode="quantity"
                          placeholder="예: 10"
                          ariaLabel="보유 수량"
                        />
                      </label>
                    </div>
                  )}
                </div>
                  </div>
                </details>

                {strategyAnalysis && (
                  <>
                    <AnalysisHub
                      analysis={strategyAnalysis}
                      activeSection={analysisSection}
                      onNavigate={navigateAnalysis}
                    />
                    <div id="analysis-detail-stage" className="analysis-detail-stage">
                    {analysisSection === "fundamental" && (
                      <>
                        <AnalysisDetailHeader
                          title="재무 체력·가치평가"
                          description="OpenDART의 최신 1분기·반기·3분기·사업보고서를 자동 선택해 전년동기와 비교하고, 장기 연간 추세는 상세에서 확인합니다."
                          onClose={() => setAnalysisSection("summary")}
                        />
                        <FundamentalPanel analysis={strategyAnalysis} />
                      </>
                    )}
                    {analysisSection === "investor_style" && (
                      <>
                        <AnalysisDetailHeader
                          title="투자 스타일·플레이북"
                          description="Buffett·Graham·Peter Lynch·CAN SLIM의 투자 방향을 먼저 이해하고, 이 종목의 적합도와 선택한 스타일 기준 대응을 비교합니다."
                          onClose={() => setAnalysisSection("summary")}
                        />
                        <InvestorStylePanel analysis={strategyAnalysis} />
                      </>
                    )}
                    {analysisSection === "risk" && (
                      <>
                        <AnalysisDetailHeader
                          title="위험·보유 관리"
                          description="보유 상태, Risk Gate, 전략 무효화와 손익 구조를 필요한 때만 확인합니다."
                          onClose={() => setAnalysisSection("summary")}
                        />
                    <section className={`position-context-result ${strategyAnalysis.position_context.mode.toLowerCase()} ${strategyAnalysis.position_context.state.toLowerCase()}`}>
                      <div className="position-result-head">
                        <div>
                          <span>MY POSITION CONTEXT</span>
                          <strong>{strategyAnalysis.position_context.mode === "HOLDING" ? "보유 포지션 자동 점검" : "신규 진입 관점"}</strong>
                        </div>
                        <b>{strategyAnalysis.position_context.label}</b>
                      </div>
                      <p>{strategyAnalysis.position_context.summary}</p>
                      {strategyAnalysis.position_context.mode === "HOLDING" && (
                        <>
                          <div className="position-metrics">
                            <div><span>평균 매수가</span><strong>{number(strategyAnalysis.position_context.average_price, "원")}</strong></div>
                            <div><span>분석 기준가격</span><strong>{number(strategyAnalysis.position_context.analysis_price, "원")}</strong></div>
                            <div><span>평균가 대비</span><strong className={rateClass(strategyAnalysis.position_context.return_pct)}>{signedRate(strategyAnalysis.position_context.return_pct)}</strong></div>
                            <div><span>평가손익</span><strong>{strategyAnalysis.position_context.unrealized_pnl == null ? "수량 미입력" : `${strategyAnalysis.position_context.unrealized_pnl >= 0 ? "+" : ""}${number(strategyAnalysis.position_context.unrealized_pnl, "원")}`}</strong></div>
                          </div>

                          {strategyAnalysis.position_action_guide.available && (
                            <div className={`position-action-card ${strategyAnalysis.position_action_guide.primary_code.toLowerCase()}`}>
                              <div className="position-action-main">
                                <span>PROGRAM RESPONSE</span>
                                <strong>{strategyAnalysis.position_action_guide.primary_label}</strong>
                                <h4>{strategyAnalysis.position_action_guide.headline}</h4>
                                <p>{strategyAnalysis.position_action_guide.summary}</p>
                              </div>

                              <div className="position-action-options">
                                <article>
                                  <span>현재 보유분</span>
                                  <b>{strategyAnalysis.position_action_guide.hold?.label}</b>
                                  <p>{strategyAnalysis.position_action_guide.hold?.reason}</p>
                                </article>
                                <article className="add">
                                  <span>추가매수 / 물타기</span>
                                  <b>{strategyAnalysis.position_action_guide.add_position?.label}</b>
                                  <p>{strategyAnalysis.position_action_guide.add_position?.reason}</p>
                                </article>
                                <article className="reduce">
                                  <span>비중 축소 / 정리</span>
                                  <b>{strategyAnalysis.position_action_guide.reduce_position?.label}</b>
                                  <p>{strategyAnalysis.position_action_guide.reduce_position?.reason}</p>
                                </article>
                              </div>

                              {!!strategyAnalysis.position_action_guide.why?.length && (
                                <div className="position-action-why">
                                  <b>왜 이렇게 판단했나?</b>
                                  <ul>{strategyAnalysis.position_action_guide.why.map((text) => <li key={text}>{text}</li>)}</ul>
                                </div>
                              )}

                              {!!strategyAnalysis.position_action_guide.triggers?.length && (
                                <div className="position-action-triggers">
                                  <b>대응이 바뀌는 조건</b>
                                  {strategyAnalysis.position_action_guide.triggers.map((item) => (
                                    <div key={`${item.condition}-${item.effect}`}>
                                      <strong>{item.condition}</strong>
                                      <span>{item.effect}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                          <div className="auto-check-list position-checks">
                            {strategyAnalysis.position_context.checks.map((check) => (
                              <div className={`auto-check ${check.status.toLowerCase()}`} key={check.key}>
                                <span className="check-icon">{check.status === "PASS" ? "✓" : check.status === "FAIL" ? "✕" : check.status === "WARN" ? "!" : "?"}</span>
                                <div><strong>{check.label}</strong><em>{check.value}</em><small>{check.explanation}</small></div>
                              </div>
                            ))}
                          </div>
                        </>
                      )}
                    </section>


                      </>
                    )}
                    {analysisSection === "indicators" && (
                      <>
                        <AnalysisDetailHeader
                          title="기술지표·데이터 기준"
                          description="데이터 신선도와 RSI·20일선·ATR 같은 세부 지표는 여기서 확인합니다."
                          onClose={() => setAnalysisSection("summary")}
                        />
                    <div className={`freshness-card ${strategyAnalysis.data_freshness.reference?.status.toLowerCase() ?? "eod"}`}>
                      <div className="freshness-title">
                        <div>
                          <span>DATA FRESHNESS</span>
                          <strong>
                            {strategyAnalysis.data_freshness.reference
                              ? strategyAnalysis.data_freshness.reference.status === "EXTREME_MOVE"
                                ? "급격한 가격 변동 · 재검토 필요"
                                : strategyAnalysis.data_freshness.reference.status === "STALE"
                                  ? "확정 데이터와 가격 괴리 큼"
                                  : "현재 참고가격 반영"
                              : "KRX 최근 확정 데이터 기준"}
                          </strong>
                        </div>
                        <span className="freshness-source">{strategyAnalysis.data_freshness.price_source === "USER_INPUT" ? "USER INPUT" : "KRX EOD"}</span>
                      </div>
                      <div className="freshness-values">
                        <div><span>확정 거래일</span><strong>{formatDate(strategyAnalysis.data_freshness.eod_date)}</strong></div>
                        <div><span>확정 종가</span><strong>{number(strategyAnalysis.data_freshness.eod_close, "원")}</strong></div>
                        {strategyAnalysis.data_freshness.reference && (
                          <>
                            <div><span>현재 참고가격</span><strong>{number(strategyAnalysis.data_freshness.reference.reference_price, "원")}</strong></div>
                            <div><span>확정 종가 대비</span><strong className={rateClass(strategyAnalysis.data_freshness.reference.gap_pct)}>{signedRate(strategyAnalysis.data_freshness.reference.gap_pct)}</strong></div>
                          </>
                        )}
                      </div>
                      <p>
                        {strategyAnalysis.data_freshness.reference?.message
                          ?? "장중 실시간 가격은 반영되지 않았습니다. 현재 상황과 차이가 크다면 위 입력란에 참고가격을 넣고 다시 분석하세요."}
                      </p>
                      {strategyAnalysis.data_freshness.reference?.is_extreme_move && (
                        <div className="extreme-warning">
                          <b>EXTREME MOVE</b>
                          <span>확정 종가 대비 변동폭이 ATR 기반 허용 범위를 크게 넘어 기존 전략을 그대로 적용하지 않고 Risk Gate를 우선합니다.</span>
                        </div>
                      )}
                    </div>

                    <div className="analysis-layer-section">
                      <div className="layer-section-head">
                        <div>
                          <span>ANALYSIS LAYERS</span>
                          <strong>확정 데이터와 현재 시나리오를 분리해서 봅니다</strong>
                        </div>
                        <p>현재가격을 입력해도 과거 KRX 데이터는 바뀌지 않습니다.</p>
                      </div>
                      <div className="analysis-layer-grid">
                        <article className="analysis-layer-card confirmed">
                          <span className="term-inline">① 확정 일봉 기준 <TermHelp term="eod" /></span>
                          <strong>{formatDate(strategyAnalysis.data_freshness.eod_date)} · {number(strategyAnalysis.analysis_layers.confirmed_eod.price, "원")}</strong>
                          <div><b className="term-inline">MA20 <TermHelp term="ma" /></b><em>{number(strategyAnalysis.analysis_layers.confirmed_eod.ma20, "원")}</em></div>
                          <div><b className="term-inline">RSI14 <TermHelp term="rsi" /></b><em>{number(strategyAnalysis.analysis_layers.confirmed_eod.rsi14)}</em></div>
                          <div><b className="term-inline">ATR <TermHelp term="atr" /></b><em>{strategyAnalysis.analysis_layers.confirmed_eod.atr_pct == null ? "-" : `${strategyAnalysis.analysis_layers.confirmed_eod.atr_pct.toFixed(2)}%`}</em></div>
                          <div><b className="term-inline">거래량비 <TermHelp term="volume_ratio" /></b><em>{strategyAnalysis.analysis_layers.confirmed_eod.volume_ratio_20 == null ? "-" : `${strategyAnalysis.analysis_layers.confirmed_eod.volume_ratio_20.toFixed(2)}배`}</em></div>
                          <small>KRX 확정값 · 수정되지 않음</small>
                        </article>

                        <article className={`analysis-layer-card reference ${strategyAnalysis.analysis_layers.current_reference ? "active" : "empty"}`}>
                          <span>② 현재 참고가격 시나리오</span>
                          {strategyAnalysis.analysis_layers.current_reference ? (
                            <>
                              <strong>{number(strategyAnalysis.analysis_layers.current_reference.price, "원")}</strong>
                              <div><b className="term-inline">예상 MA20 <TermHelp term="ma" /></b><em>{number(strategyAnalysis.analysis_layers.current_reference.estimated_ma20, "원")}</em></div>
                              <div><b className="term-inline">예상 RSI14 <TermHelp term="rsi" /></b><em>{number(strategyAnalysis.analysis_layers.current_reference.estimated_rsi14)}</em></div>
                              <div>
                                <b>{strategyAnalysis.analysis_layers.current_reference.estimated_atr_pct == null ? "ATR" : "예상 ATR"}</b>
                                <em>{strategyAnalysis.analysis_layers.current_reference.effective_atr_pct == null ? "-" : `${strategyAnalysis.analysis_layers.current_reference.effective_atr_pct.toFixed(2)}%`}</em>
                              </div>
                              <div>
                                <b>{strategyAnalysis.analysis_layers.current_reference.estimated_volume_ratio_20 == null ? "거래량비" : "현재 거래량비"}</b>
                                <em>{strategyAnalysis.analysis_layers.current_reference.effective_volume_ratio_20 == null ? "-" : `${strategyAnalysis.analysis_layers.current_reference.effective_volume_ratio_20.toFixed(2)}배`}</em>
                              </div>
                              <small>
                                {strategyAnalysis.analysis_layers.current_reference.input_mode === "PRICE_ONLY"
                                  ? "현재가격 반영 · ATR/거래량은 EOD 유지"
                                  : strategyAnalysis.analysis_layers.current_reference.input_mode === "PRICE_OHLC"
                                    ? "현재가격+고저가 반영 · 거래량은 EOD 유지"
                                    : "현재가격+고저가+거래량 반영"}
                              </small>
                            </>
                          ) : (
                            <p>현재 참고가격을 입력하면 이 영역에 예상 지표와 현재 시나리오가 표시됩니다.</p>
                          )}
                        </article>
                      </div>
                    </div>


                      </>
                    )}
                    {analysisSection === "strategy" && (
                      <>
                        <AnalysisDetailHeader
                          title="전략·눌림 자동 확인"
                          description="앱이 눌림·지지 조건을 직접 판정하고, 그 다음 전략 점수와 대응 근거를 비교합니다."
                          onClose={() => setAnalysisSection("summary")}
                        />
                        <PullbackConfirmationPanel analysis={strategyAnalysis} />
                    {strategyAnalysis.data_freshness.reference && strategyAnalysis.strategy_comparison.length > 0 && (
                      <div className="strategy-change-panel">
                        <div className="strategy-change-head">
                          <div>
                            <span>CURRENT REFERENCE SCENARIO</span>
                            <strong>현재 참고가격을 반영하면 전략 점수가 어떻게 바뀌나</strong>
                          </div>
                          <p>왼쪽은 확정 EOD, 오른쪽은 현재 참고정보를 반영한 임시 시나리오입니다.</p>
                        </div>
                        <div className="strategy-change-list">
                          {strategyAnalysis.strategy_comparison.slice(0, 10).map((row) => (
                            <div className="strategy-change-row" key={row.strategy}>
                              <strong>{strategyName[row.strategy] ?? row.strategy}</strong>
                              <span className="score-before">EOD {row.eod_score ?? "-"}</span>
                              <span className="score-arrow">→</span>
                              <span className="score-after">현재 {row.reference_score ?? "-"}</span>
                              <b className={(row.score_delta ?? 0) > 0 ? "positive" : (row.score_delta ?? 0) < 0 ? "negative" : ""}>
                                {row.score_delta == null ? "-" : `${row.score_delta > 0 ? "+" : ""}${row.score_delta}`}
                              </b>
                              <em className={row.current_data_status === "PARTIAL" ? "partial" : "updated"}>
                                {row.current_data_status === "PARTIAL" ? "부분 반영" : "현재 조건 반영"}
                              </em>
                              <small>{row.current_data_message}</small>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}


                      </>
                    )}
                    {analysisSection === "relative" && (
                      <>
                        <AnalysisDetailHeader
                          title="시장·업종 상대강도"
                          description="종목이 시장과 같은 업종보다 실제로 강한지 결과 중심으로 확인합니다."
                          onClose={() => setAnalysisSection("summary")}
                        />
                    <section className={`relative-strength-panel result-first ${strategyAnalysis.relative_strength.status.toLowerCase()}`}>
                      <div className="relative-strength-head result-head">
                        <div>
                          <span className="panel-kicker">RELATIVE STRENGTH RESULT · v0.16.4</span>
                          <div className="title-with-help">
                            <h3>시장과 같은 업종까지 비교하면</h3>
                            <TermHelp term="relative_strength" current={strategyAnalysis.relative_strength.summary} />
                            <TermHelp
                              term="sector_relative_strength"
                              current={strategyAnalysis.sector_relative_strength.available ? strategyAnalysis.sector_relative_strength.message : strategyAnalysis.sector_relative_strength.message}
                            />
                          </div>
                        </div>
                        <div className="relative-dual-badges">
                          <div className="relative-strength-badge">
                            <span>{strategyAnalysis.relative_strength.benchmark.name} 대비</span>
                            <strong>{strategyAnalysis.relative_strength.decision.label}</strong>
                            <em>{strategyAnalysis.relative_strength.primary_excess_pct == null ? "데이터 부족" : `${strategyAnalysis.relative_strength.primary_excess_pct > 0 ? "+" : ""}${strategyAnalysis.relative_strength.primary_excess_pct.toFixed(2)}%p`}</em>
                          </div>
                          <div className={`relative-strength-badge sector ${strategyAnalysis.sector_relative_strength.available ? "available" : "unavailable"}`}>
                            <span>{strategyAnalysis.sector_relative_strength.benchmark?.name ?? strategyAnalysis.sector_relative_strength.mapping.sector_group ?? "업종"} 대비</span>
                            <strong>{strategyAnalysis.sector_relative_strength.available ? strategyAnalysis.sector_relative_strength.label : "비교 불가"}</strong>
                            <em>{strategyAnalysis.sector_relative_strength.primary_excess_pct == null ? "자동 매핑 확인 필요" : `${strategyAnalysis.sector_relative_strength.primary_excess_pct > 0 ? "+" : ""}${strategyAnalysis.sector_relative_strength.primary_excess_pct.toFixed(2)}%p`}</em>
                          </div>
                        </div>
                      </div>

                      {strategyAnalysis.sector_relative_strength.available ? (
                        <>
                          <div className={`relative-decision-hero combined ${strategyAnalysis.sector_relative_strength.decision.archetype.toLowerCase()}`}>
                            <span>시장 + 업종 종합 결론</span>
                            <h4>{strategyAnalysis.sector_relative_strength.decision.headline}</h4>
                            <p>{strategyAnalysis.sector_relative_strength.decision.summary}</p>

                            <div className="relative-user-action">
                              <div>
                                <span>내 상황 기준 · {strategyAnalysis.sector_relative_strength.decision.user_response.perspective}</span>
                                <strong>{strategyAnalysis.sector_relative_strength.decision.user_response.action}</strong>
                              </div>
                              <p>{strategyAnalysis.sector_relative_strength.decision.user_response.summary}</p>
                            </div>
                          </div>

                          <div className="relative-result-grid">
                            <article>
                              <span>우선 검토할 전략</span>
                              {strategyAnalysis.sector_relative_strength.decision.preferred_strategies.length > 0 ? (
                                <div className="relative-strategy-tags positive-tags">
                                  {strategyAnalysis.sector_relative_strength.decision.preferred_strategies.map((name) => <b key={name}>{name}</b>)}
                                </div>
                              ) : <strong>상대강도만으로 우선 전략 없음</strong>}
                            </article>
                            <article>
                              <span>우선순위를 낮출 것</span>
                              {strategyAnalysis.sector_relative_strength.decision.deprioritized_strategies.length > 0 ? (
                                <div className="relative-strategy-tags caution-tags">
                                  {strategyAnalysis.sector_relative_strength.decision.deprioritized_strategies.map((name) => <b key={name}>{name}</b>)}
                                </div>
                              ) : <strong>특별한 감점 전략 없음</strong>}
                            </article>
                            <article>
                              <span>업종 자체는 시장보다</span>
                              <strong className={rateClass(strategyAnalysis.sector_relative_strength.decision.sector_vs_market_pct)}>
                                {strategyAnalysis.sector_relative_strength.decision.sector_vs_market_pct == null
                                  ? "-"
                                  : `${strategyAnalysis.sector_relative_strength.decision.sector_vs_market_pct > 0 ? "+" : ""}${strategyAnalysis.sector_relative_strength.decision.sector_vs_market_pct.toFixed(2)}%p`}
                              </strong>
                              <small>양수면 업종 자체가 시장보다 강한 편</small>
                            </article>
                          </div>

                          <div className="relative-explanation-grid">
                            <article>
                              <strong>왜 이렇게 판단했나?</strong>
                              <ul>{strategyAnalysis.sector_relative_strength.decision.why.map((text) => <li key={text}>{text}</li>)}</ul>
                            </article>
                            <article>
                              <strong>판단이 바뀌는 조건</strong>
                              <ul>{strategyAnalysis.sector_relative_strength.decision.watch_points.map((text) => <li key={text}>{text}</li>)}</ul>
                            </article>
                          </div>
                        </>
                      ) : (
                        <div className="sector-relative-unavailable">
                          <div>
                            <span>업종 비교는 이번 분석에서 제외</span>
                            <strong>{strategyAnalysis.sector_relative_strength.message}</strong>
                            <p>불확실한 업종을 억지로 연결하지 않고 아래 시장 대비 결과만 사용합니다.</p>
                          </div>
                          <small>{strategyAnalysis.sector_relative_strength.mapping.mapping_method ?? "OpenDART 업종코드 기반 자동 매핑"}</small>
                        </div>
                      )}

                      {!strategyAnalysis.sector_relative_strength.available && (
                        <div className={`relative-decision-hero ${strategyAnalysis.relative_strength.decision.archetype.toLowerCase()}`}>
                          <span>시장 대비 결론</span>
                          <h4>{strategyAnalysis.relative_strength.decision.headline}</h4>
                          <p>{strategyAnalysis.relative_strength.decision.summary}</p>
                          <div className="relative-user-action">
                            <div>
                              <span>내 상황 기준 · {strategyAnalysis.relative_strength.decision.user_response.perspective}</span>
                              <strong>{strategyAnalysis.relative_strength.decision.user_response.action}</strong>
                            </div>
                            <p>{strategyAnalysis.relative_strength.decision.user_response.summary}</p>
                          </div>
                        </div>
                      )}

                      <details className="relative-evidence">
                        <summary>
                          <span>근거 데이터 보기</span>
                          <small>5·20·60거래일 시장/업종 상대수익률과 전략 반영 근거</small>
                        </summary>

                        <div className="relative-evidence-section">
                          <div className="relative-effects-head">
                            <strong>시장 대비</strong>
                            <span>{strategyAnalysis.relative_strength.benchmark.name}와 같은 거래일 KRX EOD 비교</span>
                          </div>
                          <div className="relative-period-grid">
                            {strategyAnalysis.relative_strength.periods.map((period) => (
                              <article key={`market-${period.days}`} className={`relative-period-card ${period.status.toLowerCase()}`}>
                                <div className="relative-period-title"><strong>{period.days}거래일</strong><span>{period.label}</span></div>
                                {period.available ? (
                                  <>
                                    <div><span>종목</span><b className={rateClass(period.stock_return_pct)}>{signedRate(period.stock_return_pct)}</b></div>
                                    <div><span>{strategyAnalysis.relative_strength.benchmark.name}</span><b className={rateClass(period.market_return_pct)}>{signedRate(period.market_return_pct)}</b></div>
                                    <div className="relative-excess"><span>시장 대비</span><b className={rateClass(period.excess_return_pct)}>{period.excess_return_pct == null ? "-" : `${period.excess_return_pct > 0 ? "+" : ""}${period.excess_return_pct.toFixed(2)}%p`}</b></div>
                                  </>
                                ) : <p>같은 거래일 데이터가 부족합니다.</p>}
                              </article>
                            ))}
                          </div>
                        </div>

                        {strategyAnalysis.sector_relative_strength.available && (
                          <div className="relative-evidence-section sector-evidence">
                            <div className="relative-effects-head">
                              <strong>업종 대비</strong>
                              <span>{strategyAnalysis.sector_relative_strength.benchmark?.name} 업종지수와 비교 · 매핑 신뢰도 {strategyAnalysis.sector_relative_strength.mapping.index_match_confidence_label ?? strategyAnalysis.sector_relative_strength.mapping.mapping_confidence_label ?? "보통"}</span>
                            </div>
                            <div className="relative-period-grid">
                              {strategyAnalysis.sector_relative_strength.periods.map((period) => (
                                <article key={`sector-${period.days}`} className={`relative-period-card ${period.status.toLowerCase()}`}>
                                  <div className="relative-period-title"><strong>{period.days}거래일</strong><span>{period.label}</span></div>
                                  {period.available ? (
                                    <>
                                      <div><span>종목</span><b className={rateClass(period.stock_return_pct)}>{signedRate(period.stock_return_pct)}</b></div>
                                      <div><span>{strategyAnalysis.sector_relative_strength.benchmark?.name}</span><b className={rateClass(period.sector_return_pct)}>{signedRate(period.sector_return_pct)}</b></div>
                                      <div className="relative-excess"><span>업종 대비</span><b className={rateClass(period.excess_return_pct)}>{period.excess_return_pct == null ? "-" : `${period.excess_return_pct > 0 ? "+" : ""}${period.excess_return_pct.toFixed(2)}%p`}</b></div>
                                    </>
                                  ) : <p>같은 거래일 데이터가 부족합니다.</p>}
                                </article>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="relative-trend-row dual-trend">
                          <div><span>시장 대비 흐름</span><strong>{strategyAnalysis.relative_strength.trend_label}</strong></div>
                          <p>{strategyAnalysis.relative_strength.trend_message}</p>
                        </div>
                        {strategyAnalysis.sector_relative_strength.available && (
                          <div className="relative-trend-row dual-trend">
                            <div><span>업종 대비 흐름</span><strong>{strategyAnalysis.sector_relative_strength.trend_label}</strong></div>
                            <p>{strategyAnalysis.sector_relative_strength.trend_message}</p>
                          </div>
                        )}

                        <div className="relative-strategy-effects compact">
                          <div className="relative-effects-head">
                            <strong>전략 엔진 반영 근거</strong>
                            <span>추세·눌림목·돌파·모멘텀 계열은 시장 + 업종 상대강도를 함께 반영합니다.</span>
                          </div>
                          <div className="relative-effects-grid">
                            {strategyAnalysis.relative_strength.strategy_effects.map((effect) => (
                              <article className={effect.condition_met === true ? "pass" : effect.condition_met === false ? "fail" : "unknown"} key={`market-${effect.strategy}`}>
                                <div><strong>{strategyName[effect.strategy] ?? effect.label} · 시장 {effect.weight}점</strong><em>{effect.condition_met === true ? "시장 조건 충족" : effect.condition_met === false ? "시장 조건 미충족" : "데이터 부족"}</em></div>
                                <p>{effect.message}</p>
                              </article>
                            ))}
                            {strategyAnalysis.sector_relative_strength.strategy_effects.map((effect) => (
                              <article className={effect.condition_met === true ? "pass" : effect.condition_met === false ? "fail" : "unknown"} key={`sector-${effect.strategy}`}>
                                <div><strong>{strategyName[effect.strategy] ?? effect.label} · 업종 {effect.weight}점</strong><em>{effect.condition_met === true ? "업종 조건 충족" : effect.condition_met === false ? "업종 조건 미충족" : "업종 자료 부족 시 대체 기준"}</em></div>
                                <p>{effect.message}</p>
                              </article>
                            ))}
                          </div>
                        </div>
                      </details>

                      <div className="relative-strength-note compact-note">
                        <strong>업종 매핑 기준</strong>
                        <span>{strategyAnalysis.sector_relative_strength.note}</span>
                      </div>
                    </section>


                      </>
                    )}
                    {analysisSection === "event" && (
                      <>
                        <AnalysisDetailHeader
                          title="공시 영향"
                          description="OpenDART 공시의 핵심 조건, 가격 반응과 현재 대응을 확인합니다."
                          onClose={() => setAnalysisSection("summary")}
                        />
                    <section className={`event-risk-panel event-impact-panel ${strategyAnalysis.event_risk.risk_gate ? "high-active" : ""}`}>
                      <div className="event-risk-head">
                        <div>
                          <span className="panel-kicker">OPENDART EVENT IMPACT · v0.13</span>
                          <div className="title-with-help"><h3>최근 공시가 현재 판단에 미치는 영향</h3><TermHelp term="event_impact" /></div>
                          <p>{strategyAnalysis.event_risk.message}</p>
                        </div>
                        <div className="event-counts impact-counts">
                          <span className="positive"><b>{strategyAnalysis.event_risk.positive_count ?? 0}</b> 긍정</span>
                          <span className="negative"><b>{strategyAnalysis.event_risk.negative_count ?? 0}</b> 부정</span>
                          <span className="mixed"><b>{strategyAnalysis.event_risk.mixed_count ?? 0}</b> 혼재</span>
                          <span className="high"><b>{strategyAnalysis.event_risk.high_count}</b> HIGH</span>
                        </div>
                      </div>

                      {!strategyAnalysis.event_risk.available && (
                        <div className="event-unavailable">공시 세부 분석을 사용할 수 없습니다. 기술 분석은 계속 사용할 수 있습니다.</div>
                      )}

                      {strategyAnalysis.event_risk.events.length === 0 && strategyAnalysis.event_risk.available && (
                        <div className="event-empty">최근 60일 분류 대상 공시에서 현재 판단에 큰 영향을 줄 이벤트가 확인되지 않았습니다.</div>
                      )}

                      {strategyAnalysis.event_risk.events.length > 0 && (
                        <div className="event-list">
                          {strategyAnalysis.event_risk.events.map((event) => {
                            const directionLabel =
                              event.direction === "POSITIVE" ? "긍정 가능성" :
                              event.direction === "NEGATIVE" ? "부정 가능성" :
                              event.direction === "MIXED" ? "혼재" : "중립";
                            const priceSource =
                              event.price_reaction.analysis_price_source === "USER_REFERENCE"
                                ? "사용자 현재 참고가격"
                                : "KRX 확정 종가";

                            return (
                              <article
                                className={`event-card impact-${event.direction.toLowerCase()} level-${event.impact_level.toLowerCase()}`}
                                key={`${event.receipt_no}-${event.report_name}`}
                              >
                                <div className="event-card-head">
                                  <div>
                                    <div className="impact-badges">
                                      <span className={`direction ${event.direction.toLowerCase()}`}>{directionLabel}</span>
                                      <span className={`event-level ${event.impact_level.toLowerCase()}`}>영향도 {event.impact_level}</span>
                                      <span className={`confidence ${event.confidence.toLowerCase()}`}>신뢰도 {event.confidence_label}</span>
                                    </div>
                                    <strong>{event.report_name ?? event.event_type}</strong>
                                    <small>
                                      {event.receipt_date ? formatDate(event.receipt_date) : "날짜 미확인"}
                                      {" · "}
                                      {event.detail_source === "STRUCTURED_API" ? "OpenDART 구조화 데이터" : event.detail_source === "DOCUMENT_XML" ? "공시 원문 자동추출" : "제목 기반 1차 분석"}
                                    </small>
                                  </div>
                                  {event.viewer_url && (
                                    <a href={event.viewer_url} target="_blank" rel="noreferrer">DART 원문</a>
                                  )}
                                </div>

                                <div className={`event-conclusion ${event.direction.toLowerCase()}`}>
                                  <span>현재 결론</span>
                                  <strong>{event.current_conclusion.headline}</strong>
                                  <p>{event.current_conclusion.summary}</p>
                                </div>

                                <div className="event-explain">
                                  <b>이 공시는 무엇을 의미하나?</b>
                                  <p>{event.easy_summary}</p>
                                </div>

                                {event.facts.length > 0 && (
                                  <div className="event-facts-structured">
                                    <b>프로그램이 읽은 핵심 조건</b>
                                    <div>
                                      {event.facts.map((fact, index) => (
                                        <article key={`${fact.label}-${index}`}>
                                          <span>{fact.label}</span>
                                          <strong>{fact.value}</strong>
                                        </article>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                <div className="event-reaction-section">
                                  <b>시장은 어떻게 반응했나?</b>
                                  {event.price_reaction.available ? (
                                    <>
                                      <div className="event-reaction-grid">
                                        <article>
                                          <span>공시 전 확정 종가</span>
                                          <strong>{number(event.price_reaction.pre_event_close, "원")}</strong>
                                        </article>
                                        <article>
                                          <span>{priceSource}</span>
                                          <strong>{number(event.price_reaction.analysis_price, "원")}</strong>
                                        </article>
                                        <article>
                                          <span>가격 변화</span>
                                          <strong className={rateClass(event.price_reaction.price_change_pct)}>
                                            {signedRate(event.price_reaction.price_change_pct)}
                                          </strong>
                                        </article>
                                        <article>
                                          <span>거래량 반응</span>
                                          <strong>
                                            {event.price_reaction.volume_ratio_20 == null
                                              ? "데이터 부족"
                                              : `${event.price_reaction.volume_ratio_20.toFixed(2)}배`}
                                          </strong>
                                        </article>
                                      </div>
                                      <p className="reaction-message">
                                        {event.price_reaction.label}
                                        {event.price_reaction.analysis_price_source === "USER_REFERENCE"
                                          ? " · 현재 참고가격을 사용했으며 KRX 확정 데이터와 분리된 임시 시나리오입니다."
                                          : ""}
                                      </p>
                                    </>
                                  ) : (
                                    <p className="reaction-message unavailable">공시 전후 가격 데이터를 충분히 확보하지 못해 가격 반영 정도를 자동 판단할 수 없습니다.</p>
                                  )}
                                </div>

                                <div className="event-strategy-effects">
                                  <b>현재 전략에는 어떤 영향을 주나?</b>
                                  <div>
                                    {event.strategy_effects.map((effect) => (
                                      <article className={`effect-${effect.direction.toLowerCase()}`} key={effect.strategy}>
                                        <span>{strategyName[effect.strategy] ?? effect.strategy}</span>
                                        <strong>
                                          {effect.direction === "UP" ? "↑ " : effect.direction === "DOWN" ? "↓ " : "→ "}
                                          {effect.label}
                                        </strong>
                                        <p>{effect.reason}</p>
                                      </article>
                                    ))}
                                  </div>
                                </div>

                                <div className="event-user-action">
                                  <span>{positionMode === "HOLDING" ? "내 보유 대응" : "내 신규진입 대응"}</span>
                                  <strong>{event.user_response.action}</strong>
                                  <p>{event.user_response.summary}</p>
                                </div>

                                {event.watch_points.length > 0 && (
                                  <div className="event-watch-points">
                                    <b>앞으로 프로그램이 다시 봐야 할 것</b>
                                    <ul>{event.watch_points.map((item) => <li key={item}>{item}</li>)}</ul>
                                  </div>
                                )}

                                {event.facts.length === 0 && event.document_highlights.length > 0 && (
                                  <details className="event-raw-details">
                                    <summary>자동 구조화하지 못한 원문 참고</summary>
                                    <ul>{event.document_highlights.map((line) => <li key={line}>{line}</li>)}</ul>
                                  </details>
                                )}
                              </article>
                            );
                          })}
                        </div>
                      )}

                      <div className="event-policy">
                        <strong>자동 분석 기준</strong>
                        <span>공시 사실 → 핵심 조건 → 회사 규모 비교 → 공시 전후 가격 반응 → 전략 영향 → 사용자 상태별 대응 순서로 분석합니다. 자동 추출이 불완전한 항목은 원문 확인이 우선입니다.</span>
                      </div>
                    </section>


                      </>
                    )}
                    {analysisSection === "risk" && (
                      <>
                    {strategyAnalysis.risk_gate.active && (
                      <div className="risk-gate-card">
                        <div>
                          <span className="term-inline">RISK GATE <TermHelp term="risk_gate" current={strategyAnalysis.risk_gate.message} /></span>
                          <strong>신규 진입 판단 보류</strong>
                          <p>{strategyAnalysis.risk_gate.message}</p>
                        </div>
                        <ul>
                          {strategyAnalysis.risk_gate.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                        </ul>
                      </div>
                    )}

                    <div className="strategy-summary">
                      <div>
                        <span>현재 결론</span>
                        <strong>
                          {strategyAnalysis.risk_gate.active
                            ? "매매 보류"
                            : strategyName[strategyAnalysis.best_regular_strategy?.strategy ?? "no_trade"] ?? "매매 보류"}
                        </strong>
                      </div>
                      <p>
                        {strategyAnalysis.risk_gate.active
                          ? "현재는 리스크 조건이 우선합니다. 아래 전략들은 '가능한 시나리오' 참고용으로만 확인하세요."
                          : strategyEasyDescription[strategyAnalysis.best_regular_strategy?.strategy ?? "no_trade"]}
                      </p>
                    </div>

                    {strategyAnalysis.risk_analysis.selected_plan && (
                      <section className={`risk-engine-panel ${strategyAnalysis.risk_analysis.status.toLowerCase()}`}>
                        <div className="risk-engine-head">
                          <div>
                            <span className="panel-kicker">위험 관리 기준</span>
                            <h3>
                              {strategyAnalysis.risk_analysis.reference_only ? "참고용 손익 구조" : "현재 전략 손익 구조"}
                            </h3>
                            <p>{strategyAnalysis.risk_analysis.summary}</p>
                          </div>
                          <div className="risk-structure-badge">
                            <strong>{strategyAnalysis.risk_analysis.selected_plan.structure_rating}</strong>
                            <span>{strategyAnalysis.risk_analysis.reference_only ? "참고 시나리오" : "구조 평가"}</span>
                          </div>
                        </div>

                        <div className="risk-strategy-line">
                          <span>기준 전략</span>
                          <strong>{strategyName[strategyAnalysis.risk_analysis.selected_strategy ?? ""] ?? strategyAnalysis.risk_analysis.selected_strategy}</strong>
                          <em>{strategyAnalysis.risk_analysis.basis === "MANUAL_REFERENCE" ? "현재 참고가격 기준" : "확정 일봉 기준"}</em>
                        </div>

                        <div className="risk-price-grid">
                          <div>
                            <span>분석 기준가격</span>
                            <strong>{number(strategyAnalysis.risk_analysis.selected_plan.entry_price, "원")}</strong>
                            <small>실제 주문가격이 아닌 분석 기준</small>
                          </div>
                          <div>
                            <span className="label-with-help">전략 무효화 기준 <TermHelp term="invalidation" /></span>
                            <strong>{number(strategyAnalysis.risk_analysis.selected_plan.invalidation_price, "원")}</strong>
                            <small>{strategyAnalysis.risk_analysis.selected_plan.structural_anchor_label ?? "구조적 기준 부족"}</small>
                          </div>
                          <div>
                            <span className="label-with-help">손절 참고구간 <TermHelp term="stop" /></span>
                            <strong>
                              {strategyAnalysis.risk_analysis.selected_plan.stop_zone_low == null || strategyAnalysis.risk_analysis.selected_plan.stop_zone_high == null
                                ? "-"
                                : `${number(strategyAnalysis.risk_analysis.selected_plan.stop_zone_low)} ~ ${number(strategyAnalysis.risk_analysis.selected_plan.stop_zone_high)}원`}
                            </strong>
                            <small>{strategyAnalysis.risk_analysis.selected_plan.risk_pct == null ? "계산 불가" : `기준가격 대비 약 -${strategyAnalysis.risk_analysis.selected_plan.risk_pct.toFixed(2)}%`}</small>
                          </div>
                          <div>
                            <span className="label-with-help">1차 목표 참고 <TermHelp term="target" /></span>
                            <strong>{number(strategyAnalysis.risk_analysis.selected_plan.target1_price, "원")}</strong>
                            <small>{strategyAnalysis.risk_analysis.selected_plan.target1_basis ?? "-"}</small>
                          </div>
                          <div>
                            <span className="label-with-help">2차 목표 참고 <TermHelp term="target" /></span>
                            <strong>{number(strategyAnalysis.risk_analysis.selected_plan.target2_price, "원")}</strong>
                            <small>{strategyAnalysis.risk_analysis.selected_plan.target2_basis ?? "-"}</small>
                          </div>
                          <div>
                            <span className="label-with-help">손익비(R:R) <TermHelp term="risk_reward" current={strategyAnalysis.risk_analysis.selected_plan.rr1 == null ? null : `1만큼 위험을 감수할 때 1차 목표 보상은 약 ${strategyAnalysis.risk_analysis.selected_plan.rr1.toFixed(2)}만큼입니다.`} /></span>
                            <strong>
                              {strategyAnalysis.risk_analysis.selected_plan.rr1 == null ? "-" : `1 : ${strategyAnalysis.risk_analysis.selected_plan.rr1.toFixed(2)}`}
                            </strong>
                            <small>
                              2차 기준 {strategyAnalysis.risk_analysis.selected_plan.rr2 == null ? "-" : `1 : ${strategyAnalysis.risk_analysis.selected_plan.rr2.toFixed(2)}`}
                            </small>
                          </div>
                        </div>

                        <div className="risk-explain-grid">
                          <div>
                            <b>왜 이 가격인가?</b>
                            <ul>{strategyAnalysis.risk_analysis.selected_plan.reasons.map((text) => <li key={text}>{text}</li>)}</ul>
                          </div>
                          <div className="risk-warning-box">
                            <b>주의할 점</b>
                            {strategyAnalysis.risk_analysis.selected_plan.warnings.length > 0
                              ? <ul>{strategyAnalysis.risk_analysis.selected_plan.warnings.map((text) => <li key={text}>{text}</li>)}</ul>
                              : <p>현재 계산상 추가 경고는 없습니다. 실제 가격 변동과 공시는 별도로 확인해야 합니다.</p>}
                          </div>
                        </div>

                        {strategyAnalysis.risk_analysis.plans.length > 1 && (
                          <div className="risk-plan-compare">
                            <div className="risk-plan-compare-head">
                              <strong>상위 전략별 손익 구조 비교</strong>
                              <span>전략이 달라지면 무효화 기준도 달라집니다.</span>
                            </div>
                            {strategyAnalysis.risk_analysis.plans.map((plan) => (
                              <div className="risk-plan-row" key={plan.strategy}>
                                <strong>{strategyName[plan.strategy] ?? plan.strategy}</strong>
                                <span>손절폭 {plan.risk_pct == null ? "-" : `${plan.risk_pct.toFixed(2)}%`}</span>
                                <span>1차 R:R {plan.rr1 == null ? "-" : `1:${plan.rr1.toFixed(2)}`}</span>
                                <span>2차 R:R {plan.rr2 == null ? "-" : `1:${plan.rr2.toFixed(2)}`}</span>
                                <em>{plan.structure_rating}</em>
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="risk-policy-note">
                          <strong>실제 매매 기능 없음</strong>
                          <span>{strategyAnalysis.risk_analysis.policy.message}</span>
                        </div>
                      </section>
                    )}


                      </>
                    )}
                    {analysisSection === "indicators" && (
                      <>
                    <BeginnerIndicatorSummary
                      price={strategyAnalysis.effective.price}
                      ma20={strategyAnalysis.effective.ma20}
                      rsi14={strategyAnalysis.effective.rsi14}
                      atrPct={strategyAnalysis.effective.atr_pct}
                      volumeRatio20={strategyAnalysis.effective.volume_ratio_20}
                      support={strategyAnalysis.technical.support}
                      resistance={strategyAnalysis.technical.resistance}
                      supportDistancePct={strategyAnalysis.effective.support_distance_pct}
                      resistanceDistancePct={strategyAnalysis.effective.resistance_distance_pct}
                    />

                    <div className="technical-grid">
                      <div>
                        <div className="term-label-line"><span>20일 평균 가격</span><TermHelp term="ma" /></div>
                        <strong>{number(strategyAnalysis.effective.ma20, "원")}</strong>
                        <small>
                          {strategyAnalysis.data_freshness.reference
                            ? `확정 ${number(strategyAnalysis.technical.ma20, "원")} · 현재가를 임시 종가로 가정한 예상값`
                            : "최근 20거래일 확정 종가 평균"}
                        </small>
                      </div>
                      <div>
                        <div className="term-label-line"><span>RSI · 과열/과매도</span><TermHelp term="rsi" /></div>
                        <strong>{number(strategyAnalysis.effective.rsi14)}</strong>
                        <small>
                          {strategyAnalysis.data_freshness.reference
                            ? `확정 RSI ${number(strategyAnalysis.technical.rsi14)} · 현재가 가정 예상 RSI`
                            : "확정 일봉 기준 · 70 이상 과열, 30 이하 과매도 참고"}
                        </small>
                      </div>
                      <div>
                        <div className="term-label-line"><span>ATR · 평균 변동폭</span><TermHelp term="atr" /></div>
                        <strong>{strategyAnalysis.effective.atr_pct == null ? "-" : `${strategyAnalysis.effective.atr_pct.toFixed(2)}%`}</strong>
                        <small>
                          {strategyAnalysis.data_freshness.reference?.estimated.atr_pct != null
                            ? "오늘 고가·저가를 반영한 예상 ATR"
                            : "확정 일봉 기준 · 오늘 고가·저가 미입력 시 유지"}
                        </small>
                      </div>
                      <div>
                        <div className="term-label-line"><span>평균 대비 거래량</span><TermHelp term="volume_ratio" /></div>
                        <strong>{strategyAnalysis.effective.volume_ratio_20 == null ? "-" : `${strategyAnalysis.effective.volume_ratio_20.toFixed(2)}배`}</strong>
                        <small>
                          {strategyAnalysis.data_freshness.reference?.estimated.volume_ratio_20 != null
                            ? "입력한 현재 누적 거래량 ÷ 최근 20일 평균 거래량"
                            : "확정 EOD 거래량 기준 · 현재 거래량 미입력 시 유지"}
                        </small>
                      </div>
                      <div>
                        <div className="term-label-line"><span>지지 가격 후보</span><TermHelp term="support" /></div>
                        <strong>{number(strategyAnalysis.technical.support, "원")}</strong>
                        <small>현재 참고가격과 거리 {strategyAnalysis.effective.support_distance_pct == null ? "-" : `${strategyAnalysis.effective.support_distance_pct.toFixed(2)}%`}</small>
                      </div>
                      <div>
                        <div className="term-label-line"><span>저항 가격 후보</span><TermHelp term="resistance" /></div>
                        <strong>{number(strategyAnalysis.technical.resistance, "원")}</strong>
                        <small>현재 참고가격과 거리 {strategyAnalysis.effective.resistance_distance_pct == null ? "-" : `${strategyAnalysis.effective.resistance_distance_pct.toFixed(2)}%`}</small>
                      </div>
                    </div>


                      </>
                    )}
                    {analysisSection === "strategy" && (
                      <>
                    <div className="strategy-guide">
                      <strong className="term-inline">전략 점수 보는 법 <TermHelp term="strategy_score" /></strong>
                      <p>
                        점수가 높을수록 <b>현재 상태가 그 전략의 조건과 많이 맞는다</b>는 뜻입니다.
                        80점이라고 해서 주가가 80% 확률로 오른다는 의미는 아닙니다.
                      </p>
                    </div>

                    <div className="strategy-catalog-note">
                      <strong>
                        {strategyAnalysis.data_freshness.reference ? "현재 참고가격 시나리오 기준" : "확정 일봉 기준"} · {strategyAnalysis.strategies.filter((item) => item.strategy !== "no_trade").length}개 전략 비교
                      </strong>
                      <span>
                        {strategyAnalysis.data_freshness.reference
                          ? "아래 점수와 대응 가이드는 현재 참고가격을 반영한 임시 시나리오입니다. 현재 거래량/고저가를 입력하지 않은 전략은 일부 EOD 조건을 유지합니다."
                          : "한 종목에 여러 전략이 동시에 일부 성립할 수 있으므로 점수와 대응 가이드를 함께 봅니다."}
                      </span>
                    </div>
                    <div className="strategy-results readability-compact">
                      <div className="strategy-compact-list" role="list" aria-label="전략 비교 목록">
                        {strategyAnalysis.strategies.map((item, index) => (
                          <button
                            type="button"
                            role="listitem"
                            className={`strategy-compact-item ${selectedStrategyIndexSafe === index ? "active" : ""}`}
                            key={`${item.strategy}-${index}`}
                            onClick={() => setSelectedStrategyIndex(index)}
                            aria-pressed={selectedStrategyIndexSafe === index}
                          >
                            <span>
                              <strong>{strategyName[item.strategy] ?? item.strategy}</strong>
                              <small>
                                {item.strategy === "no_trade"
                                  ? "현재 조건에서는 매매 보류"
                                  : `${item.passed}/${item.total}개 조건 충족 · ${item.suitability}`}
                              </small>
                            </span>
                            <b>{item.score == null ? "보류" : `${item.score}점`}</b>
                          </button>
                        ))}
                      </div>

                      {selectedStrategy && (
                        <div className="strategy-detail-selected" aria-live="polite">
                          <article className="strategy-row top">
                            <div className="strategy-info">
                              <div className="strategy-title-line">
                                <strong>{strategyName[selectedStrategy.strategy] ?? selectedStrategy.strategy}</strong>
                                {selectedStrategy.strategy !== "no_trade" && <span>{selectedStrategy.passed}/{selectedStrategy.total}개 조건 충족</span>}
                              </div>
                              <p className="strategy-easy">{strategyEasyDescription[selectedStrategy.strategy] ?? selectedStrategy.note}</p>
                              <p className="strategy-beginner">{strategyBeginnerHint[selectedStrategy.strategy]}</p>

                              <div className="condition-section">
                                <b>현재 맞는 조건</b>
                                <div className="reason-list">
                                  {selectedStrategy.reasons.slice(0, 4).map((reason) => <em key={reason}>✓ {reason}</em>)}
                                  {selectedStrategy.blockers.map((reason) => <em className="blocker" key={reason}>! {reason}</em>)}
                                </div>
                              </div>

                              {selectedStrategy.unmet.length > 0 && (
                                <div className="condition-section unmet-section">
                                  <b>아직 부족한 조건</b>
                                  <div className="reason-list unmet-list">
                                    {selectedStrategy.unmet.slice(0, 3).map((reason) => <em key={reason}>– {reason}</em>)}
                                  </div>
                                </div>
                              )}

                              {selectedStrategy.strategy !== "no_trade" && selectedStrategy.auto_checks.length > 0 && (
                                <div className="program-check-section">
                                  <div className="program-check-head">
                                    <b>프로그램 자동 점검</b>
                                    <span>StockScope가 자동으로 계산한 현재 조건입니다.</span>
                                  </div>
                                  <div className="auto-check-list">
                                    {selectedStrategy.auto_checks.map((check) => (
                                      <div className={`auto-check ${check.status.toLowerCase()}`} key={`${selectedStrategy.strategy}-${check.key}`}>
                                        <span className="check-icon">{check.status === "PASS" ? "✓" : check.status === "FAIL" ? "✕" : check.status === "WARN" ? "!" : "?"}</span>
                                        <div>
                                          <strong>{check.label}</strong>
                                          <em>{check.value}</em>
                                          <small>{check.explanation}</small>
                                        </div>
                                        <i>{check.source === "USER_INPUT" ? "현재 참고" : check.source === "KRX_INDEX" ? "시장지수" : "확정 EOD"}</i>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              <details className="response-guide">
                                <summary>{strategyAnalysis.position_context.mode === "HOLDING" ? "보유 중 대응 기준 보기" : "신규 진입 대응 기준 보기"}</summary>
                                <div className="response-grid contextual">
                                  <section className="primary-response">
                                    <b>{strategyAnalysis.position_context.mode === "HOLDING" ? "보유 중 대응 기준" : "신규 진입 검토 기준"}</b>
                                    <ul>
                                      {(strategyAnalysis.position_context.mode === "HOLDING" ? selectedStrategy.action_plan.holding : selectedStrategy.action_plan.new_entry).map((text) => <li key={text}>{text}</li>)}
                                    </ul>
                                  </section>
                                  <section className="avoid-box">
                                    <b>피해야 할 대응</b>
                                    <ul>{selectedStrategy.action_plan.avoid.map((text) => <li key={text}>{text}</li>)}</ul>
                                  </section>
                                  <section>
                                    <b>앞으로 관찰할 항목</b>
                                    <p className="watch-explain">자동 점검 결과가 바뀌는지 계속 보는 항목입니다.</p>
                                    <ul>{selectedStrategy.action_plan.watch.map((text) => <li key={text}>{text}</li>)}</ul>
                                  </section>
                                </div>
                                <div className="invalidation-box">
                                  <b>전략이 약해지는 기준</b>
                                  <p>{selectedStrategy.action_plan.invalidation}</p>
                                </div>
                              </details>
                            </div>
                            <div className={`strategy-score ${selectedStrategy.strategy === "no_trade" ? "hold" : ""}`}>
                              {selectedStrategy.score == null ? <b>보류</b> : <b>{selectedStrategy.score}점</b>}
                              <span>{selectedStrategy.strategy === "no_trade" ? "Risk Gate / 관찰" : selectedStrategy.suitability}</span>
                              <small>{selectedStrategy.strategy === "no_trade" ? "점수형 전략 아님" : "조건 적합도"}</small>
                            </div>
                          </article>
                        </div>
                      )}
                    </div>


                      </>
                    )}
                    {analysisSection === "indicators" && (
                      <>
                    <BeginnerGlossary />

                    <div className="analysis-limit">
                      <strong>중요</strong>
                      <span>
                        이 결과는 투자 판단을 돕기 위한 설명입니다. 사용자 참고가격은 임시 계산에만 사용되며 KRX 확정 데이터는 수정하지 않습니다.
                        자동 매매나 실제 주문은 수행하지 않으며, 손절·목표가는 위험 관리 기준에 따라 분석 참고값으로 계산하며 실제 주문으로 전송되지 않습니다.
                      </span>
                    </div>

                      </>
                    )}
                    </div>
                  </>
                )}
              </div>
            )}

            </StockAnalysisWorkspace>
          ) : appPage === "backtest" ? (
            <BacktestPanel
              code={stockCode}
              market={stockMarket}
              stockName={selectedStockName}
              onSelectStock={chooseStock}
            />
          ) : appPage === "scanner" ? (
            <ScannerPanel
              onAnalyzeStock={(item) => {
                chooseStock(item, { loadContext: true, origin: "scanner" });
                navigateApp("analysis");
              }}
            />
          ) : appPage === "simulation" ? (
            <TrackingWorkspace />
          ) : (
            <HoldingsWorkspace onAnalyzeStock={openAnalysisFromHoldings} />
          )}

          <footer>
            <span>※ StockScope는 투자 판단 보조용이며 실제 매수·매도 주문 기능을 제공하지 않습니다.</span>
            <span>데이터: KRX · OpenDART</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

/* UX.1.1 intuitive information architecture */
