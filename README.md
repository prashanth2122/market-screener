Available Data APIs (Stocks, Crypto, Indices, Commodities)
A key first step is choosing free data feeds. For stocks and indices, popular free APIs include Alpha Vantage and Finnhub. Alpha Vantage “provides realtime and historical financial market data” across many asset classes – global equities, forex, commodities, crypto, ETFs, indices and more
. It covers over 200,000 tickers (20+ exchanges) and even includes fundamental data and built-in technical indicators
. Finnhub’s free tier also offers global equities and crypto (40+ exchanges) with real-time and fundamental data
. FinancialModelingPrep (FMP) is another free option with broad coverage – U.S., Canada, EU, Asia, and asset types including stocks, ETFs, indices, crypto and forex
. For Indian markets like NIFTY, one can use Yahoo Finance (via the Python yfinance library) or dedicated APIs. (For example, an open-source “Indian Stock Market API” proxies Yahoo data for NSE/BSE tickers.)

For cryptocurrencies, CoinGecko’s public API is a widely used free source. CoinGecko “offers the most comprehensive and reliable crypto market data” via REST endpoints, covering >18,000 coins across 600+ categories
. It requires no authentication and provides real-time prices, market cap, and historical charts. (Another option is CryptoCompare or exchange APIs like Binance via CCXT, but CoinGecko’s simplicity and coverage make it ideal for rapid prototyping.)

For commodities and forex, Alpha Vantage and FMP again help: Alpha Vantage has dedicated time-series endpoints for commodities (e.g. gold, oil) and FX, while FMP includes commodity and forex price APIs.

For news and sentiment, use financial news APIs. For example, Marketaux offers a free stock-news API: “Instant access to global stock market and finance news… including crypto… along with comprehensive sentiment analysis”
. Similarly, FMP has a Stock News API giving real-time and historical news for specified tickers
. Alternately, Finnhub and Alpha Vantage provide news/sentiment endpoints. In practice, you’d call something like stock_news?tickers=AAPL&from=2026-04-01&apikey=... to fetch recent headlines (as JSON with title, snippet, URL)
.

Key free APIs summary:

Stocks & Indices: Alpha Vantage (free tier, 5 calls/min), Finnhub (free tier), FinancialModelingPrep (free plan), Yahoo Finance via yfinance (unofficial).
Crypto: CoinGecko (no key required, REST); also CryptoCompare, Binance API (via CCXT).
Commodities/Forex: Alpha Vantage time series, FMP Forex/Commodity APIs.
News: Marketaux News API (free), Finnhub news, FMP Stock News, or generic NewsAPI.
Each service has limits (calls/minute or daily cap), but for a personal screener they are generally sufficient. You may need to combine multiple sources or cache results to stay within quotas.

Data Model & Screening Metrics
With data flowing in, define how to store and score each asset. A typical data model might have an “Asset” (stock/crypto symbol) entity with fields for current price, historical price series, and computed signals. Related tables could include Indicators (RSI, moving averages, etc.), Fundamentals (P/E, earnings, debt), NewsEvents (latest headlines), and Alerts/Scores. For example, each day you might insert the latest price into a Prices table (timestamp, open/high/low/close, volume) and compute technical indicators from that series.

Screening metrics should combine technical signals, valuation, and news. Key metrics might include:

Price Targets & Ranges: Track each asset’s All-Time High (ATH) date and value. Compute % distance from current price to ATH (e.g. “X% below ATH”). Also compute 52-week high/low ranges and relative position within them. These help identify breakout candidates.

Technical Indicators: Compute standard indicators via a library like TA-Lib
. For instance: 50-day and 200-day Moving Averages (MA50, MA200), MACD, RSI (14-day), Bollinger Bands, Average True Range (ATR), on-balance volume, etc. Detect crossovers (e.g. golden cross MA50>MA200) or breakouts above resistance (price > previous swing high). Chart patterns could be flagged (e.g. ascending triangle, bull flag). Using TA-Lib’s 200 built-in indicators makes this easy
.

Trend/Bias: Determine if the asset is in a bullish or bearish regime. For example, set a flag if price > MA200 (long-term uptrend) or if RSI > 50 (momentum up). Identify “new high” stocks (making a new 52-week or ATH high) as especially strong
. Flag “squeeze” conditions (tight Bollinger/Keltner band) as potential breakout setups (as per various technical strategies).

Volume & Liquidity: Look at recent volume relative to average; spikes in volume can confirm breakouts or signal accumulation by large players.

Volatility: Compute metrics like volatility index (VIX) or asset-specific ATR. High implied volatility might mean caution, or opportunities if priced-in event is known.

Fundamental Scores: Incorporate fundamental health metrics. For example, calculate a Piotroski F-Score (0–9) based on nine accounting factors
. An F-Score of 8–9 (very strong) often signals improving fundamentals (per Piotroski’s research)
. Also compute an Altman Z-score for bankruptcy risk – values <1.8 imply distress, >3.0 imply healthy
. Other fundamentals: P/E ratio (vs industry), debt/equity, revenue & earnings growth rates, cash flow trends. These come from company financials (Alpha Vantage or FMP APIs can supply income statements and balance sheets
).

Recent News/Events: Store recent headlines or filings. Identify major news flags (earnings releases, product launches, management changes, legal issues). Tag if negative (e.g. CEO scandal, regulatory crackdown). Use sentiment analysis (Marketaux provides sentiment scores, or run a simple NLP sentiment on headlines). For example, a negative news alert might immediately penalize a stock’s score.

Event Calendar: Track upcoming events like earnings dates, dividends, IPOs or central bank meetings. Out-of-cycle events can cause spikes. Linking a calendar API or scraping a corporate schedule would enrich the screener (e.g. “Tesla earnings on 5/4/2026”).

Finally, combine these into a score or ranking. One approach is to weight factors (e.g. 50% technical strength, 30% fundamentals, 20% sentiment) to produce a composite “buy” score. Or use machine learning on historical winners vs losers. At minimum, present each metric so you can eyeball good candidates: e.g. “Stock A: 10% below ATH, in uptrend, RSI=70, F-Score=8, Altman Z=4.2, no bad news → strong buy candidate.”

Data Ingestion & Real-Time Pipeline
For real-time (or near-real-time) updates, build a lightweight data pipeline. Since this is a personal project, simplicity is best. A common pattern is:

Data Fetch Service: A scheduled job (cron or a Python schedule loop) that calls each API for your watched symbols. For example, every minute fetch the latest price for each stock/crypto via your chosen API (e.g. Alpha Vantage or Finnhub for stocks, CoinGecko for crypto). Store the results in your database. If high-frequency streaming is not needed, polling every 30–60 seconds is often enough.

Message Queue (Optional): For high reliability, you could insert new quotes into a queue (Kafka, RabbitMQ, Redis Streams, etc.) before processing. This decouples data fetching from analysis. As one reference notes, a message queue “acts as a buffer with durability” to handle mismatched producer/consumer rates
. (In practice, for a small personal app you might skip Kafka complexity and write directly to DB.)

Realtime Updates: Some APIs offer WebSockets (e.g. Finnhub, Coinbase). If using those, you could maintain a live websocket client pushing updates into your pipeline. Otherwise, REST polling is fine. Just respect rate limits (cache intermediate data to avoid redundant calls
).

Storage: A simple relational database (PostgreSQL/MySQL) or even SQLite (for small scale) can hold the data tables (Prices, Indicators, News, etc.). Alternatively, a time-series DB like InfluxDB could store price ticks. The key is that each new data point triggers recalculation of your metrics.

In summary, a scheduler (or daemon) fetches APIs, and the pipeline writes raw data into storage. Then downstream processes (either immediately after fetch, or as separate worker tasks) compute and update the technical/fundamental indicators and signals for each asset.

Example: You might create a Python script src/fetch_data.py that runs every minute. It calls, say, https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=RELIANCE.NS&apikey=... and parses the JSON into your Stocks table. Another script src/compute_indicators.py would read new prices and update RSI, moving averages, and scores.

Analysis Modules: Technical, Fundamental, News
Once data is ingested, implement modules to compute insights:

Technical Analysis Module: Use libraries like TA-Lib (Python or others) which provide ~200 indicators (ADX, MACD, RSI, Bollinger, etc)
. For each asset’s price series, compute these indicators (e.g. RSI14, MACD (12,26,9), 20-day Bollinger bands). Detect key patterns: e.g. if price crosses above its 50-day MA (bullish signal), or if RSI just exited oversold. Compute moving-average crossovers: a “golden cross” (50-day MA crossing above 200-day MA) is often bullish. Also look at chart patterns (support/resistance breaches, flag/pennant breakouts, etc.).

Fundamental Analysis Module: Pull key fundamental ratios from your data (some via Alpha Vantage or FMP). For example, fetch latest earnings per share, revenue growth, debt-equity ratio. Compute value metrics (P/E, P/B) and growth metrics (EPS growth YOY). As noted, include an F-Score calculation: this 0–9 score “measures the financial health of a company based on nine accounting signals; a score of 8–9 indicates strong fundamentals
.” Include the Altman Z-score for default risk
. A custom “quality score” could combine these; e.g. penalize stock if F-Score ≤2 or Z-score <1.8.

News/Sentiment Module: Periodically call your news API (Marketaux or FMP). For each fetched article, do entity matching (does it mention your stock ticker?) and basic sentiment scoring (Marketaux may do this, or use a library like VADER). Tag events as “positive”, “negative”, or “neutral.” If negative news is detected (e.g. “layoffs”, “missed earnings”, “management scandal”), mark the stock accordingly. Some systems treat sentiment as an input to the score. You can also tally event counts: e.g. “3 bad news items in last 2 days.”

Signal Aggregator: Combine outputs. For example, set a “Buy/StrongBuy” flag if: price is X% below ATH and 50-day MA > 200-day MA and no bad news and high F-Score. Or generate alerts like “Discounted Buy”: if current price < (average of the past 6 months) – indicating dip. Provide a “Score” per asset summarizing all these signals (on a 0–100 or 0–1 scale).

Each module can run as part of the data pipeline or as a scheduled job (e.g. re-compute every hour or upon new data arrival).

UI and Alerting
Finally, build a user interface to display results and push alerts. For personal use, a lightweight dashboard or web app is ideal. Possible approaches:

Web Dashboard: Use a web framework (e.g. Streamlit, Dash, or a React frontend with a Python/Node.js backend). Show a table of screened stocks/crypto with sortable columns: price, % change, distance from ATH, RSI, score, etc. Include charts (e.g. price trend with MA overlays). Many dashboards embed Plotly or chart libraries. For example, one can build a “Real-Time Stock Dashboard” in Python using Streamlit and Yahoo Finance data
 (the idea is similar). Display color-coded signals (“Strong Buy”, “Weak”, etc.) based on your score.

Alerts: For discounted buys or events, set up notifications. A simple alert engine (Python script) can monitor conditions and send emails/SMS. For example, you might use Python’s smtplib to email yourself when a stock crosses below a threshold
. (As a reference, a blog tutorial shows a “Stock Tracker Bot” using yfinance and smtplib to send email alerts when prices hit set thresholds
.) Alternatively, integrate with messaging APIs (e.g. Twilio for SMS, or Slack Webhooks). An alert could say: “TSLA down 7% today, score=5.7 – potential buy.” Or trigger on events: “Company X Earnings negative, RSI oversold.”

Layout & Features: The UI should allow simple login (your requested email/password auth can be implemented via Auth0 or Firebase Auth). After login, show your personalized screener dashboard. Key UI elements: search/filter stocks, view detailed metrics for a selected stock (e.g. historical chart, fundamental data, news headlines). Provide a way to subscribe to email alerts in-app.

Discount Indicators: Specifically highlight “discount buy” signals. For example, flag a stock if price falls a certain % below its 50-day average or if it hits a 3-month low. Show the % drop and hold period.

In short, the UI ties it all together: it presents the real-time metrics and scores computed by your backend, and lets you easily spot “good buys.” Alerts (email or pop-up) ensure you don’t miss sudden moves.

Overall, this project involves integrating (and citing) many known tools and algorithms: free market data APIs (Alpha Vantage, Finnhub, CoinGecko, etc.), technical analysis libraries (TA-Lib)
, and financial scoring methods (Piotroski F-score
, Altman Z-score
). With this design, your screener can fetch live data, compute dozens of indicators, and present a comprehensive view of which assets are potentially undervalued or poised to move.

Sources: The above design leverages established APIs and strategies. For instance, Alpha Vantage is highlighted as a “one-stop-shop” for equities, forex, crypto, and even built‑in indicators
. Marketaux provides a free news feed with sentiment
, and FMP offers both stock data and a Stock News API
. Technical analysis tools like TA-Lib supply 200 indicators out of the box
. Known quant metrics (Piotroski’s F-Score
, Altman Z-score
) can score fundamentals. Finally, examples like a Python “yfinance + smtplib” alert bot
 show how to implement notifications. Each component above can be built or integrated using these free resources.
