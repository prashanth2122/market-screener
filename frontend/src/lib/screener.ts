export type ScreenerItem = {
  symbol: string;
  asset_type: string;
  exchange: string;
  quote_currency: string;
  as_of_ts: string;
  signal: string;
  score: number | null;
  confidence: number | null;
  blocked_by_risk: boolean;
  reasons: string[];
};

export type ScreenerApiResponse = {
  status: string;
  filters?: {
    asset_types?: string[];
    exchanges?: string[];
    quote_currencies?: string[];
    signals?: string[];
    symbol_query?: string | null;
    min_score?: number | null;
    max_score?: number | null;
    min_confidence?: number | null;
    blocked_by_risk?: boolean | null;
    sort_by?: string;
    sort_dir?: string;
  };
  pagination: {
    total: number;
    limit: number;
    offset: number;
    returned: number;
  };
  items: ScreenerItem[];
};

export type ScreenerQueryOptions = {
  limit?: number;
  offset?: number;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  asset_types?: string;
  exchanges?: string;
  quote_currencies?: string;
  signals?: string;
  symbol_query?: string;
  min_score?: number;
  min_confidence?: number;
  blocked_by_risk?: boolean;
};

export async function fetchScreenerRows(
  options: ScreenerQueryOptions = {},
): Promise<ScreenerApiResponse> {
  const apiBase =
    process.env.MARKET_SCREENER_API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000";

  const searchParams = new URLSearchParams();
  const appendString = (key: string, value: string | undefined) => {
    if (value !== undefined && value !== "") {
      searchParams.set(key, value);
    }
  };
  const appendNumber = (key: string, value: number | undefined) => {
    if (value !== undefined && Number.isFinite(value)) {
      searchParams.set(key, String(value));
    }
  };

  appendNumber("limit", options.limit);
  appendNumber("offset", options.offset);
  appendString("sort_by", options.sort_by);
  appendString("sort_dir", options.sort_dir);
  appendString("asset_types", options.asset_types);
  appendString("exchanges", options.exchanges);
  appendString("quote_currencies", options.quote_currencies);
  appendString("signals", options.signals);
  appendString("symbol_query", options.symbol_query);
  appendNumber("min_score", options.min_score);
  appendNumber("min_confidence", options.min_confidence);
  if (options.blocked_by_risk !== undefined) {
    searchParams.set("blocked_by_risk", String(options.blocked_by_risk));
  }

  if (!searchParams.has("limit")) {
    searchParams.set("limit", "50");
  }
  if (!searchParams.has("sort_by")) {
    searchParams.set("sort_by", "score");
  }
  if (!searchParams.has("sort_dir")) {
    searchParams.set("sort_dir", "desc");
  }

  const url = `${apiBase}/api/v1/screener?${searchParams.toString()}`;

  const response = await fetch(url, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Screener request failed (${response.status})`);
  }

  const payload = (await response.json()) as ScreenerApiResponse;
  if (!payload || payload.status !== "ok" || !Array.isArray(payload.items)) {
    throw new Error("Invalid screener payload shape");
  }

  return payload;
}
