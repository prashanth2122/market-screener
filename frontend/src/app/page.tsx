import Link from "next/link";

import { fetchScreenerRows } from "@/lib/screener";

export const dynamic = "force-dynamic";

type PageProps = {
  searchParams?: Record<string, string | string[] | undefined>;
};

function toLabel(value: string): string {
  return value
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function formatScore(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return value.toFixed(2);
}

function formatConfidence(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatAsOf(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getSearchParam(searchParams: PageProps["searchParams"], key: string): string | undefined {
  const value = searchParams?.[key];
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

function parseOptionalNumber(value: string | undefined): number | undefined {
  if (!value) {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return undefined;
  }
  return parsed;
}

function parseOptionalBoolean(value: string | undefined): boolean | undefined {
  if (!value) {
    return undefined;
  }
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return undefined;
}

function buildHrefWithParams(
  params: URLSearchParams,
  updates: Record<string, string | number | boolean | undefined>,
): string {
  const next = new URLSearchParams(params);
  for (const [key, value] of Object.entries(updates)) {
    if (value === undefined || value === "") {
      next.delete(key);
      continue;
    }
    next.set(key, String(value));
  }
  const query = next.toString();
  return query ? `/?${query}` : "/";
}

export default async function HomePage({ searchParams }: PageProps) {
  const assetTypes = getSearchParam(searchParams, "asset_types") ?? "";
  const exchanges = getSearchParam(searchParams, "exchanges") ?? "";
  const quoteCurrencies = getSearchParam(searchParams, "quote_currencies") ?? "";
  const signals = getSearchParam(searchParams, "signals") ?? "";
  const symbolQuery = getSearchParam(searchParams, "symbol_query") ?? "";
  const minScore = parseOptionalNumber(getSearchParam(searchParams, "min_score"));
  const minConfidence = parseOptionalNumber(getSearchParam(searchParams, "min_confidence"));
  const blockedByRisk = parseOptionalBoolean(getSearchParam(searchParams, "blocked_by_risk"));
  const sortBy = getSearchParam(searchParams, "sort_by") ?? "score";
  const sortDir = (getSearchParam(searchParams, "sort_dir") ?? "desc") as "asc" | "desc";
  const limit = parseOptionalNumber(getSearchParam(searchParams, "limit")) ?? 50;
  const offset = parseOptionalNumber(getSearchParam(searchParams, "offset")) ?? 0;

  let rows: Awaited<ReturnType<typeof fetchScreenerRows>> | null = null;
  let errorMessage: string | null = null;

  try {
    rows = await fetchScreenerRows({
      asset_types: assetTypes,
      exchanges,
      quote_currencies: quoteCurrencies,
      signals,
      symbol_query: symbolQuery,
      min_score: minScore,
      min_confidence: minConfidence,
      blocked_by_risk: blockedByRisk,
      sort_by: sortBy,
      sort_dir: sortDir,
      limit,
      offset,
    });
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : "Unknown API error";
  }

  const currentParams = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (Array.isArray(value)) {
      value.forEach((item) => currentParams.append(key, item));
    } else if (value !== undefined) {
      currentParams.set(key, value);
    }
  }

  const total = rows?.pagination.total ?? 0;
  const returned = rows?.pagination.returned ?? 0;
  const prevOffset = Math.max(0, offset - limit);
  const nextOffset = offset + limit;
  const canPrev = offset > 0;
  const canNext = nextOffset < total;
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = total === 0 ? 0 : Math.min(total, offset + returned);

  return (
    <main className="screener-shell">
      <section className="hero-panel">
        <p className="eyebrow">Day 76 Frontend Delivery</p>
        <h1 className="hero-title">Elite Screener Table</h1>
        <p className="hero-subtitle">
          Filter, sort, and page through the latest ranked symbols from the backend screener API.
          Saved as URL query params so you can bookmark a setup.
        </p>
      </section>

      <section className="table-panel">
        <div className="table-header">
          <div>
            <h2>Screener Rankings</h2>
            <p>
              {rows
                ? `${rows.pagination.total} symbols found • showing ${rows.pagination.returned}`
                : "No data loaded"}
            </p>
          </div>
          <span className="status-pill">{errorMessage ? "Disconnected" : "Live Snapshot"}</span>
        </div>

        <form className="filters-panel" method="get">
          <input type="hidden" name="offset" value="0" />
          <div className="filters-grid">
            <label className="filter-field">
              <span>Symbol</span>
              <input
                name="symbol_query"
                placeholder="AAPL, RELIANCE, BTC"
                defaultValue={symbolQuery}
              />
            </label>
            <label className="filter-field">
              <span>Asset Types</span>
              <input name="asset_types" placeholder="equity,crypto" defaultValue={assetTypes} />
            </label>
            <label className="filter-field">
              <span>Exchanges</span>
              <input name="exchanges" placeholder="US,NSE,GLOBAL" defaultValue={exchanges} />
            </label>
            <label className="filter-field">
              <span>Quote Ccy</span>
              <input
                name="quote_currencies"
                placeholder="USD,INR,USDT"
                defaultValue={quoteCurrencies}
              />
            </label>
            <label className="filter-field">
              <span>Signals</span>
              <input
                name="signals"
                placeholder="strong_buy,buy,watch,avoid"
                defaultValue={signals}
              />
            </label>
            <label className="filter-field">
              <span>Min Score</span>
              <input
                name="min_score"
                inputMode="decimal"
                placeholder="70"
                defaultValue={minScore === undefined ? "" : String(minScore)}
              />
            </label>
            <label className="filter-field">
              <span>Min Conf</span>
              <input
                name="min_confidence"
                inputMode="decimal"
                placeholder="0.65"
                defaultValue={minConfidence === undefined ? "" : String(minConfidence)}
              />
            </label>
            <label className="filter-field">
              <span>Risk Block</span>
              <select
                name="blocked_by_risk"
                defaultValue={blockedByRisk === undefined ? "" : String(blockedByRisk)}
              >
                <option value="">Any</option>
                <option value="false">Clear only</option>
                <option value="true">Blocked only</option>
              </select>
            </label>
            <label className="filter-field">
              <span>Sort</span>
              <select name="sort_by" defaultValue={sortBy}>
                <option value="score">Score</option>
                <option value="confidence">Confidence</option>
                <option value="as_of_ts">As Of</option>
                <option value="signal">Signal</option>
                <option value="symbol">Symbol</option>
              </select>
            </label>
            <label className="filter-field">
              <span>Dir</span>
              <select name="sort_dir" defaultValue={sortDir}>
                <option value="desc">Desc</option>
                <option value="asc">Asc</option>
              </select>
            </label>
            <label className="filter-field">
              <span>Page Size</span>
              <select name="limit" defaultValue={String(limit)}>
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="200">200</option>
              </select>
            </label>
          </div>
          <div className="filter-actions">
            <button type="submit" className="primary-button">
              Apply
            </button>
            <Link href="/" className="secondary-link">
              Clear
            </Link>
            {rows ? (
              <span className="filters-meta">
                Showing {pageStart}-{pageEnd} of {total}
              </span>
            ) : null}
          </div>
        </form>

        {errorMessage ? (
          <div className="state-card error-card">
            <h3>Unable to load screener data</h3>
            <p>{errorMessage}</p>
            <p>
              Confirm backend is running at <code>http://localhost:8000</code> or set
              <code> MARKET_SCREENER_API_BASE_URL</code>.
            </p>
          </div>
        ) : null}

        {!errorMessage && rows && rows.items.length === 0 ? (
          <div className="state-card">
            <h3>No symbols available</h3>
            <p>The screener endpoint returned an empty set for current filters.</p>
          </div>
        ) : null}

        {!errorMessage && rows && rows.items.length > 0 ? (
          <div className="table-scroll">
            <table className="screener-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Signal</th>
                  <th>Score</th>
                  <th>Confidence</th>
                  <th>Type</th>
                  <th>Exchange</th>
                  <th>Risk</th>
                  <th>As Of</th>
                </tr>
              </thead>
              <tbody>
                {rows.items.map((item) => {
                  const signalClass = `signal-chip signal-${item.signal}`;
                  const riskClass = item.blocked_by_risk ? "risk-flag yes" : "risk-flag no";
                  return (
                    <tr key={`${item.symbol}-${item.as_of_ts}`}>
                      <td>
                        <Link href={`/assets/${item.symbol}`} className="symbol-link">
                          {item.symbol}
                        </Link>
                      </td>
                      <td>
                        <span className={signalClass}>{toLabel(item.signal)}</span>
                      </td>
                      <td>{formatScore(item.score)}</td>
                      <td>{formatConfidence(item.confidence)}</td>
                      <td>{toLabel(item.asset_type)}</td>
                      <td>{item.exchange}</td>
                      <td>
                        <span className={riskClass}>{item.blocked_by_risk ? "Blocked" : "Clear"}</span>
                      </td>
                      <td>{formatAsOf(item.as_of_ts)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {!errorMessage && rows && rows.items.length > 0 ? (
          <div className="pagination-bar">
            <Link
              href={buildHrefWithParams(currentParams, { offset: prevOffset, limit })}
              aria-disabled={!canPrev}
              className={canPrev ? "pager-link" : "pager-link disabled"}
            >
              Prev
            </Link>
            <span className="pager-meta">
              {pageStart}-{pageEnd} of {total}
            </span>
            <Link
              href={buildHrefWithParams(currentParams, { offset: nextOffset, limit })}
              aria-disabled={!canNext}
              className={canNext ? "pager-link" : "pager-link disabled"}
            >
              Next
            </Link>
          </div>
        ) : null}
      </section>
    </main>
  );
}
