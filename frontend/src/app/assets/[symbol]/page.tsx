import Link from "next/link";
import { notFound } from "next/navigation";

import type { AssetDetailNewsRow, AssetDetailPriceRow } from "@/lib/assetDetail";
import { fetchAssetDetail } from "@/lib/assetDetail";

export const dynamic = "force-dynamic";

type PageProps = {
  params: { symbol: string };
  searchParams?: Record<string, string | string[] | undefined>;
};

function toLabel(value: string): string {
  return value
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function formatNumber(value: number | null, digits = 2): string {
  if (value === null) {
    return "-";
  }
  if (!Number.isFinite(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function formatPercent(value: number | null): string {
  if (value === null) {
    return "-";
  }
  if (!Number.isFinite(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatDatetime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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

function getSearchParam(
  searchParams: PageProps["searchParams"],
  key: string,
): string | undefined {
  const value = searchParams?.[key];
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

function computeMovingAverage(values: Array<number | null>, windowSize: number): Array<number | null> {
  if (windowSize <= 1) {
    return values.map((value) => (value === null ? null : value));
  }
  const output: Array<number | null> = new Array(values.length).fill(null);
  let sum = 0;
  let count = 0;
  const queue: Array<number | null> = [];

  for (let index = 0; index < values.length; index += 1) {
    const next = values[index];
    queue.push(next);
    if (next !== null) {
      sum += next;
      count += 1;
    }

    if (queue.length > windowSize) {
      const removed = queue.shift() ?? null;
      if (removed !== null) {
        sum -= removed;
        count -= 1;
      }
    }

    if (queue.length === windowSize && count > 0) {
      output[index] = sum / count;
    }
  }
  return output;
}

function buildPath(points: Array<{ x: number; y: number; defined: boolean }>): string {
  let path = "";
  let started = false;
  for (const point of points) {
    if (!point.defined) {
      started = false;
      continue;
    }
    const command = started ? "L" : "M";
    path += `${command}${point.x.toFixed(2)},${point.y.toFixed(2)} `;
    started = true;
  }
  return path.trim();
}

function buildChartSeries(
  prices: AssetDetailPriceRow[],
  series: Array<number | null>,
  config: {
    width: number;
    height: number;
    padding: number;
    minValue: number;
    maxValue: number;
  },
): Array<{ x: number; y: number; defined: boolean }> {
  const { width, height, padding, minValue, maxValue } = config;
  const usableWidth = Math.max(1, width - padding * 2);
  const usableHeight = Math.max(1, height - padding * 2);
  const span = Math.max(1e-9, maxValue - minValue);

  return series.map((value, index) => {
    const fractionX = prices.length <= 1 ? 0 : index / (prices.length - 1);
    const x = padding + fractionX * usableWidth;
    if (value === null || !Number.isFinite(value)) {
      return { x, y: padding + usableHeight, defined: false };
    }
    const fractionY = (value - minValue) / span;
    const y = padding + (1 - fractionY) * usableHeight;
    return { x, y, defined: true };
  });
}

function normalizeSymbol(value: string): string {
  return (value || "").trim().toUpperCase();
}

function sentimentTone(value: number | null): "pos" | "neg" | "neu" | "na" {
  if (value === null || !Number.isFinite(value)) {
    return "na";
  }
  if (value >= 0.2) {
    return "pos";
  }
  if (value <= -0.2) {
    return "neg";
  }
  return "neu";
}

function formatSentiment(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function computeAverageSentiment(rows: AssetDetailNewsRow[]): number | null {
  const values = rows
    .map((row) => row.sentiment_score)
    .filter((value): value is number => value !== null && Number.isFinite(value));
  if (values.length === 0) {
    return null;
  }
  const sum = values.reduce((total, value) => total + value, 0);
  return sum / values.length;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function scoreBand(score: number | null): "high" | "constructive" | "mixed" | "weak" | "unavailable" {
  if (score === null || !Number.isFinite(score)) {
    return "unavailable";
  }
  if (score >= 80) {
    return "high";
  }
  if (score >= 65) {
    return "constructive";
  }
  if (score >= 50) {
    return "mixed";
  }
  return "weak";
}

export default async function AssetDetailPage({ params, searchParams }: PageProps) {
  const symbol = normalizeSymbol(params.symbol);
  if (!symbol) {
    notFound();
  }

  const lookbackDays = parseOptionalNumber(getSearchParam(searchParams, "days")) ?? 180;
  const limit = parseOptionalNumber(getSearchParam(searchParams, "limit")) ?? 260;

  let detail: Awaited<ReturnType<typeof fetchAssetDetail>> | null = null;
  let errorMessage: string | null = null;

  try {
    detail = await fetchAssetDetail(symbol, { price_lookback_days: lookbackDays, price_limit: limit });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown API error";
    if (message.includes("(404)")) {
      notFound();
    }
    errorMessage = message;
  }

  const prices = detail?.history.prices ?? [];
  const news = detail?.history.news ?? [];
  const closes = prices.map((row) => row.close ?? null);
  const ma50 = computeMovingAverage(closes, 50);
  const ma200 = computeMovingAverage(closes, 200);
  const averageSentiment = computeAverageSentiment(news);

  const visibleValues: number[] = [];
  for (const value of [...closes, ...ma50, ...ma200]) {
    if (value !== null && Number.isFinite(value)) {
      visibleValues.push(value);
    }
  }
  const minValue = visibleValues.length ? Math.min(...visibleValues) : 0;
  const maxValue = visibleValues.length ? Math.max(...visibleValues) : 1;

  const width = 980;
  const height = 320;
  const padding = 18;
  const closePoints = buildChartSeries(prices, closes, {
    width,
    height,
    padding,
    minValue,
    maxValue,
  });
  const ma50Points = buildChartSeries(prices, ma50, {
    width,
    height,
    padding,
    minValue,
    maxValue,
  });
  const ma200Points = buildChartSeries(prices, ma200, {
    width,
    height,
    padding,
    minValue,
    maxValue,
  });

  const closePath = buildPath(closePoints);
  const ma50Path = buildPath(ma50Points);
  const ma200Path = buildPath(ma200Points);

  const latest = detail?.latest;
  const latestSignal = latest?.signal;
  const latestScore = latest?.score;
  const latestIndicator = latest?.indicator;
  const lastClose = closes.length ? closes[closes.length - 1] : null;
  const lastMa50 = ma50.length ? ma50[ma50.length - 1] : null;
  const lastMa200 = ma200.length ? ma200[ma200.length - 1] : null;

  const resolvedCompositeScore =
    latestScore?.composite_score ?? latestSignal?.score ?? null;
  const band = scoreBand(resolvedCompositeScore);
  const signalDetails = asRecord(latestSignal?.details);
  const scoreDetails = asRecord(latestScore?.details);
  const scoreBandOverride =
    typeof signalDetails.score_band === "string" ? signalDetails.score_band : null;
  const effectiveWeights = asRecord(scoreDetails.effective_weights);
  const unavailableComponents = asStringArray(scoreDetails.unavailable_components);

  const componentRows = [
    {
      key: "technical_strength",
      label: "Technical",
      score: latestScore?.technical_score ?? null,
      weight: asNumber(effectiveWeights.technical_strength) ?? 0,
    },
    {
      key: "fundamental_quality",
      label: "Fundamental",
      score: latestScore?.fundamental_score ?? null,
      weight: asNumber(effectiveWeights.fundamental_quality) ?? 0,
    },
    {
      key: "sentiment_event_risk",
      label: "Sentiment/Risk",
      score: latestScore?.sentiment_risk_score ?? null,
      weight: asNumber(effectiveWeights.sentiment_event_risk) ?? 0,
    },
  ].map((row) => {
    const edge =
      row.score === null ? null : row.weight * (row.score - 50);
    const impact =
      edge === null ? "na" : edge > 0.5 ? "pos" : edge < -0.5 ? "neg" : "neu";
    return { ...row, edge, impact };
  });

  const bestDriver =
    componentRows
      .filter((row) => row.edge !== null)
      .sort((a, b) => (b.edge ?? 0) - (a.edge ?? 0))[0] ?? null;
  const worstDriver =
    componentRows
      .filter((row) => row.edge !== null)
      .sort((a, b) => (a.edge ?? 0) - (b.edge ?? 0))[0] ?? null;

  return (
    <main className="asset-shell">
      <section className="asset-hero">
        <div className="asset-hero-top">
          <Link href="/" className="asset-back">
            ← Back to Screener
          </Link>
          <span className="asset-pill">{errorMessage ? "Disconnected" : "Live Snapshot"}</span>
        </div>

        <div className="asset-title-row">
          <h1 className="asset-title">{symbol}</h1>
          {detail ? (
            <div className="asset-meta">
              <span>{toLabel(detail.asset.asset_type)}</span>
              <span>•</span>
              <span>{detail.asset.exchange}</span>
              <span>•</span>
              <span>{detail.asset.quote_currency}</span>
            </div>
          ) : null}
        </div>

        {latestSignal ? (
          <div className="asset-kpis">
            <div className="kpi-card">
              <span className="kpi-label">Signal</span>
              <span className={`kpi-value signal-chip signal-${latestSignal.signal}`}>
                {toLabel(latestSignal.signal)}
              </span>
              <span className="kpi-sub">{latestSignal.blocked_by_risk ? "Risk Blocked" : "Risk Clear"}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Composite Score</span>
              <span className="kpi-value">{formatNumber(latestScore?.composite_score ?? latestSignal.score)}</span>
              <span className="kpi-sub">As of {formatDatetime(latestSignal.as_of_ts)}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Confidence</span>
              <span className="kpi-value">{formatPercent(latestSignal.confidence)}</span>
              <span className="kpi-sub">{(latestSignal.reasons ?? []).slice(0, 2).join(" • ") || "—"}</span>
            </div>
          </div>
        ) : null}
      </section>

      <section className="asset-panel">
        <div className="asset-panel-header">
          <div>
            <h2>Score Explanation</h2>
            <p>
              {resolvedCompositeScore === null
                ? "Composite score unavailable."
                : `Band: ${scoreBandOverride ?? band} • support=${
                    bestDriver?.label ?? "n/a"
                  } • drag=${worstDriver?.label ?? "n/a"}`}
            </p>
          </div>
          <div className="legend">
            <span className="legend-item">
              <span className="legend-swatch impact-pos" /> Positive
            </span>
            <span className="legend-item">
              <span className="legend-swatch impact-neu" /> Neutral
            </span>
            <span className="legend-item">
              <span className="legend-swatch impact-neg" /> Negative
            </span>
            <span className="legend-item">
              <span className="legend-swatch impact-na" /> Missing
            </span>
          </div>
        </div>

        {unavailableComponents.length > 0 ? (
          <div className="gaps-row">
            <span className="gaps-label">Gaps</span>
            <div className="gaps-chips">
              {unavailableComponents.map((item) => (
                <span key={item} className="gap-chip">
                  {item}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="explanation-grid">
          {componentRows.map((row) => (
            <div key={row.key} className="explain-card">
              <div className="explain-top">
                <span className="explain-title">{row.label}</span>
                <span className={`impact-pill ${row.impact}`}>
                  {row.edge === null ? "Missing" : row.edge > 0 ? "Support" : row.edge < 0 ? "Drag" : "Neutral"}
                </span>
              </div>
              <div className="explain-metrics">
                <div className="explain-metric">
                  <span className="metric-label">Score</span>
                  <span className="metric-value">{formatNumber(row.score)}</span>
                </div>
                <div className="explain-metric">
                  <span className="metric-label">Weight</span>
                  <span className="metric-value">{formatNumber(row.weight, 2)}</span>
                </div>
                <div className="explain-metric">
                  <span className="metric-label">Edge</span>
                  <span className="metric-value">{row.edge === null ? "-" : formatNumber(row.edge, 1)}</span>
                </div>
              </div>
              <p className="explain-note">
                Edge = weight × (component_score − 50). Positive edge supports the composite score.
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="asset-panel">
        <div className="asset-panel-header">
          <div>
            <h2>Price + Overlays</h2>
            <p>
              Close with MA50/MA200 overlays ({prices.length} points). Latest close {formatNumber(lastClose)}.
            </p>
          </div>
          <div className="legend">
            <span className="legend-item">
              <span className="legend-swatch close" /> Close ({formatNumber(lastClose)})
            </span>
            <span className="legend-item">
              <span className="legend-swatch ma50" /> MA50 ({formatNumber(lastMa50)})
            </span>
            <span className="legend-item">
              <span className="legend-swatch ma200" /> MA200 ({formatNumber(lastMa200)})
            </span>
          </div>
        </div>

        {errorMessage ? (
          <div className="state-card error-card">
            <h3>Unable to load asset detail</h3>
            <p>{errorMessage}</p>
            <p>
              Confirm backend is running at <code>http://localhost:8000</code> or set
              <code> MARKET_SCREENER_API_BASE_URL</code>.
            </p>
          </div>
        ) : null}

        {!errorMessage && prices.length === 0 ? (
          <div className="state-card">
            <h3>No price history available</h3>
            <p>The backend returned zero price rows for the configured lookback window.</p>
          </div>
        ) : null}

        {!errorMessage && prices.length > 1 ? (
          <div className="chart-card">
            <svg className="price-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Price chart">
              <defs>
                <linearGradient id="closeFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="rgba(31, 122, 69, 0.26)" />
                  <stop offset="100%" stopColor="rgba(31, 122, 69, 0.02)" />
                </linearGradient>
              </defs>
              <path
                d={`${closePath} L ${width - padding},${height - padding} L ${padding},${height - padding} Z`}
                fill="url(#closeFill)"
                opacity={0.9}
              />
              <path d={closePath} className="chart-line close" />
              <path d={ma50Path} className="chart-line ma50" />
              <path d={ma200Path} className="chart-line ma200" />
            </svg>
          </div>
        ) : null}

        {latestIndicator ? (
          <div className="overlay-metrics">
            <div className="metric">
              <span className="metric-label">Indicator Source</span>
              <span className="metric-value">{latestIndicator.source}</span>
            </div>
            <div className="metric">
              <span className="metric-label">MA50</span>
              <span className="metric-value">{formatNumber(latestIndicator.ma50)}</span>
            </div>
            <div className="metric">
              <span className="metric-label">MA200</span>
              <span className="metric-value">{formatNumber(latestIndicator.ma200)}</span>
            </div>
            <div className="metric">
              <span className="metric-label">RSI14</span>
              <span className="metric-value">{formatNumber(latestIndicator.rsi14)}</span>
            </div>
          </div>
        ) : null}
      </section>

      <section className="asset-panel">
        <div className="asset-panel-header">
          <div>
            <h2>News + Sentiment</h2>
            <p>
              {news.length === 0
                ? "No recent articles available."
                : `Recent coverage (${news.length} articles) • avg sentiment ${formatSentiment(
                    averageSentiment,
                  )}`}
            </p>
          </div>
          <div className="legend">
            <span className="legend-item">
              <span className="legend-swatch sentiment-pos" /> Positive
            </span>
            <span className="legend-item">
              <span className="legend-swatch sentiment-neu" /> Neutral
            </span>
            <span className="legend-item">
              <span className="legend-swatch sentiment-neg" /> Negative
            </span>
            <span className="legend-item">
              <span className="legend-swatch sentiment-risk" /> Risk
            </span>
          </div>
        </div>

        {errorMessage ? (
          <div className="state-card error-card">
            <h3>Unable to load asset news</h3>
            <p>{errorMessage}</p>
          </div>
        ) : null}

        {!errorMessage && news.length === 0 ? (
          <div className="state-card">
            <h3>No news items</h3>
            <p>The backend returned zero news rows for this symbol.</p>
          </div>
        ) : null}

        {!errorMessage && news.length > 0 ? (
          <div className="news-list">
            {news.map((item, index) => {
              const tone = sentimentTone(item.sentiment_score);
              const toneClass = `sentiment-pill ${tone}`;
              const isRisk = Boolean(item.risk_flag);
              const eventText = item.event_type ? toLabel(item.event_type) : null;
              return (
                <article key={`${item.published_at}-${index}`} className="news-card">
                  <header className="news-card-top">
                    <div className="news-meta">
                      <span className="news-source">{item.source}</span>
                      <span className="news-sep">•</span>
                      <span>{formatDatetime(item.published_at)}</span>
                      {eventText ? (
                        <>
                          <span className="news-sep">•</span>
                          <span>{eventText}</span>
                        </>
                      ) : null}
                    </div>
                    <div className="news-tags">
                      <span className={toneClass}>{formatSentiment(item.sentiment_score)}</span>
                      {isRisk ? <span className="risk-pill">Risk</span> : null}
                    </div>
                  </header>
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="news-title"
                    >
                      {item.title}
                    </a>
                  ) : (
                    <div className="news-title">{item.title}</div>
                  )}
                  {item.description ? <p className="news-desc">{item.description}</p> : null}
                </article>
              );
            })}
          </div>
        ) : null}
      </section>
    </main>
  );
}
