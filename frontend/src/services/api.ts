export type HealthResponse = { status: string };

export type ProviderStatus = {
  krx: { configured: boolean; role: string };
  dart: { configured: boolean; role: string };
  kis: { enabled: boolean; role: string };
  real_trading: boolean;
};

export type KrxStockRow = {
  date: string | null;
  code: string | null;
  name: string | null;
  market: string | null;
  close: number | null;
  change: number | null;
  change_rate: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  trade_value: number | null;
  market_cap: number | null;
};

export type DartCompany = {
  provider: "OpenDART";
  corp_code: string | null;
  corp_name: string | null;
  corp_name_eng: string | null;
  stock_name: string | null;
  stock_code: string | null;
  ceo: string | null;
  corp_class: string | null;
  business_number: string | null;
  established_date: string | null;
  address: string | null;
  homepage: string | null;
  phone: string | null;
  fiscal_month: string | null;
};

export type DartDisclosureResponse = {
  provider: "OpenDART";
  corp_code: string;
  begin_date: string;
  end_date: string;
  count: number;
  rows: Array<{
    receipt_no: string | null;
    corp_name: string | null;
    report_name: string | null;
    filer_name: string | null;
    receipt_date: string | null;
    remark: string | null;
  }>;
};

export type StockContext = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  real_trading: false;
  data_date: string;
  requested_date: string | null;
  fallback_used: boolean;
  stock: KrxStockRow;
  market_index: {
    date: string | null;
    name: string | null;
    close: number | null;
    change: number | null;
    change_rate: number | null;
  } | null;
  company: DartCompany;
  disclosures: DartDisclosureResponse;
  sources: Record<string, string>;
};

async function asJson<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let message = `요청 실패 (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) message = body.detail;
  } catch {
    // Keep fallback.
  }
  throw new Error(message);
}

export async function fetchHealth(): Promise<HealthResponse> {
  return asJson<HealthResponse>(await fetch("/api/health"));
}

export async function fetchProviderStatus(): Promise<ProviderStatus> {
  return asJson<ProviderStatus>(await fetch("/api/providers/status"));
}

export async function fetchStockContext(code: string, market: "KOSPI" | "KOSDAQ"): Promise<StockContext> {
  const query = new URLSearchParams({ market });
  return asJson<StockContext>(
    await fetch(`/api/stocks/${encodeURIComponent(code)}/context?${query.toString()}`),
  );
}
