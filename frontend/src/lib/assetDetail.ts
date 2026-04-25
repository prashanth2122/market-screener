export type AssetDetailPriceRow = {
  ts: string;
  source: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type AssetDetailNewsRow = {
  published_at: string;
  source: string;
  title: string;
  description: string | null;
  url: string | null;
  language: string | null;
  sentiment_score: number | null;
  event_type: string | null;
  risk_flag: boolean | null;
  details: Record<string, unknown>;
};

export type AssetDetailResponse = {
  status: string;
  asset: {
    symbol: string;
    asset_type: string;
    exchange: string;
    quote_currency: string;
    active: boolean;
  };
  query: {
    price_lookback_days: number;
    price_limit: number;
    indicator_source: string;
    fundamentals_source: string;
    news_source: string;
    model_version: string;
    price_source?: string | null;
  };
  latest_as_of_ts: string | null;
  latest: {
    signal:
      | {
          as_of_ts: string;
          signal: string;
          score: number | null;
          confidence: number | null;
          blocked_by_risk: boolean;
          reasons: string[];
          details: Record<string, unknown>;
        }
      | null;
    score:
      | {
          as_of_ts: string;
          composite_score: number | null;
          technical_score: number | null;
          fundamental_score: number | null;
          sentiment_risk_score: number | null;
          details: Record<string, unknown>;
        }
      | null;
    indicator:
      | {
          ts: string;
          source: string;
          ma50: number | null;
          ma200: number | null;
          rsi14: number | null;
          macd: number | null;
          macd_signal: number | null;
          atr14: number | null;
          bb_upper: number | null;
          bb_lower: number | null;
        }
      | null;
    fundamentals:
      | {
          as_of_ts: string;
          period_type: string;
          period_end: string | null;
          filing_date: string | null;
          statement_currency: string | null;
          revenue: number | null;
          gross_profit: number | null;
          ebit: number | null;
          net_income: number | null;
          operating_cash_flow: number | null;
          total_assets: number | null;
          total_liabilities: number | null;
          market_cap: number | null;
          eps_basic: number | null;
          eps_diluted: number | null;
          details: Record<string, unknown>;
        }
      | null;
  };
  history: {
    prices: AssetDetailPriceRow[];
    news: AssetDetailNewsRow[];
  };
  counts: {
    prices: number;
    news: number;
  };
};

export async function fetchAssetDetail(
  symbol: string,
  options: {
    price_lookback_days?: number;
    price_limit?: number;
  } = {},
): Promise<AssetDetailResponse> {
  const apiBase =
    process.env.MARKET_SCREENER_API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000";

  const searchParams = new URLSearchParams();
  if (options.price_lookback_days !== undefined) {
    searchParams.set("price_lookback_days", String(options.price_lookback_days));
  }
  if (options.price_limit !== undefined) {
    searchParams.set("price_limit", String(options.price_limit));
  }

  const query = searchParams.toString();
  const url = `${apiBase}/api/v1/assets/${encodeURIComponent(symbol)}${query ? `?${query}` : ""}`;

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Asset detail request failed (${response.status})`);
  }
  const payload = (await response.json()) as AssetDetailResponse;
  if (!payload || payload.status !== "ok" || !payload.asset || !payload.history) {
    throw new Error("Invalid asset detail payload shape");
  }
  return payload;
}
