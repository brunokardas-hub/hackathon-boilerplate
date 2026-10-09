# hackathon-boilerplate
🚀 Production-ready boilerplate for rapid hackathon development and high-performance econometric data analysis in 2026. Optimized for Cursor AI.

## TradingView terminal (`tradingview/terminal.pine`)

A Bloomberg-style dashboard for TradingView, written in Pine Script v6. It draws an amber-on-black panel over any chart:

- **Quote**: last price, net and % change, open, high, low, previous close, volume compared with its 20-day average
- **52-week range**: the high, the low and a bar showing where the price sits between them
- **Performance**: 1D / 1W / 1M / 3M / YTD / 1Y returns, plus relative strength against a benchmark (SPY by default)
- **Technicals**: RSI, ATR, MACD, three EMAs, VWAP and an overall trend read
- **Fundamentals** (stocks only): market cap, P/E, EPS, revenue and year-over-year revenue growth, free cash flow, margins, return on equity, debt-to-equity, dividend yield, the last earnings surprise and the next earnings date
- **Macro**: policy rate, inflation (CPI year-over-year), unemployment and quarterly GDP growth for a country you choose, each with its change since the previous release
- **Monitor**: six symbols you choose (default SPY, QQQ, DXY, US10Y, Gold, BTC)
- **Analyst note and score**: a plain-English summary of the move, trend, momentum, 52-week position, relative strength and upcoming earnings, plus a 0–100 score (shown in the Data Window, with alerts above 70 and below 30). It's rule-based arithmetic on the panel's numbers, not AI and not advice.
- **MARKET panel** (a second panel, bottom-left by default): a 4×3 heatmap coloured by % change, a breadth line with the day's leader and laggard, and a screener you can sort by % change, RSI or relative volume and filter to gainers, losers, oversold, overbought or unusual volume. Choose the universe: US sectors, US mega caps, crypto, global macro, or your own list of up to 12 tickers.
- **24/7 alerts**: alert conditions for your own price levels, prior-day high/low breaks, gaps, volume spikes, 52-week breaks, RSI, EMA crosses and the score, plus one bundled alert ("Any alert() function call") that covers them all. Setup: [docs/TRADINGVIEW_ALERTS.md](docs/TRADINGVIEW_ALERTS.md).
- **Overlays and alerts**: EMAs, VWAP and the prior day's high/low, plus alerts for 52-week breaks, RSI extremes and EMA crosses

**Install:** open TradingView → *Pine Editor* → paste in the contents of `terminal.pine` → *Save* → *Add to chart*. Change symbols, position and size in the indicator's settings.

## Web terminal (`web/index.html`)

A Bloomberg-style page in a single file. Use it at **https://brunokardas-hub.github.io/hackathon-boilerplate/** once GitHub Pages is on (see below), or download the file and double-click it.

- **Command line**: type `AAPL`, `NYSE:BA`, `BTCUSD` or `EURUSD` and press Enter to load a symbol. Other commands: `N`, `GP`, `FA`, `TA` and `ECO` jump to a panel; `HEAT` / `HEAT CRYPTO` open the market heatmap; `EQS` / `EQS CRYPTO` / `EQS FX` open the screener; `ASK <question>` asks the AI analyst; `BRIEF` writes a morning briefing; `HELP` lists everything. Press `/` to focus the command line.
- **CHARTS**: a full-height chart with one-click timeframes (1m to 1W), chart styles (candles, Heikin Ashi, line, area) and indicator sets (trend, momentum, volatility), next to your list. Click a symbol to chart it.
- **My list**: a readable live table (big prices that flash on each tick, % change, a freshness dot) on MAIN and CHARTS. Add symbols in the box at the top; ✕ removes one. The MARKETS tab shows TradingView's multi-asset monitor.
- **⚙ SETTINGS**: both API keys, the state of every data source, and backup/restore in one place. First-time visitors get a short welcome card.
- **MAIN screen**: a large TradingView chart (press **⤢ MAX** or type `MAX` to fill the screen; Esc to exit), security overview, a multi-asset monitor, a technicals summary, company financials (stocks only), an economic calendar, a ticker tape and world clocks.
- **News**: works with no setup, using TradingView's news feed. Add a free [Finnhub](https://finnhub.io/register) key in ⚙ SETTINGS to get live headlines that refresh every 60 seconds, with TICKER / TOP / FX / CRYPTO / M&A tabs and a rough ▲/▼ tone tag based on keywords.
- **HEAT**: market map of the S&P 500, Nasdaq 100, all US stocks, the DAX or crypto. Tile size is market cap and colour is % change.
- **EQS**: TradingView's screener for US stocks, crypto or FX, with filters and column sets.
- **AI analyst**: ask questions in plain English. Claude gets the symbol on screen, plus the live quote and recent headlines if you added a Finnhub key, and can search the web. Add your own [Anthropic API key](https://platform.claude.com/settings/keys) in ⚙ SETTINGS (or the AI screen's SETUP panel). You pay Anthropic per question, and the screen shows the estimated cost of each answer. The default model is Claude Opus 5.5; Sonnet 5.5 costs about half as much and Haiku 5.5 far less. Answers are information, not financial advice.

- **Analyst note and score** (MAIN, left): a rule-based 0–100 score and plain-English summary. Crypto uses Binance daily candles (EMAs, RSI, MACD, 1-year range, 30 days vs BTC); US stocks use Finnhub (52-week range, 5-day/13-week/26-week returns, strength vs the S&P 500, analyst consensus, next earnings).
- **Live quote strip** above the chart: the price ticking in real time with the day's change and a sparkline. Crypto works with no key (Binance, every 10 s); stocks and FX use Finnhub (quotes every 60 s, plus real-time trades over its websocket).
- **My list**: `ADD TSLA` / `DEL TSLA` edit the watchlist shown in the monitor and the ticker strip.
- **GRID**: 2 or 4 charts at once, either one symbol on several timeframes or several symbols (`GRID 4 NVDA SPY QQQ SMH`).
- **RES**: earnings calendar (your symbols, the largest companies, or everything), analyst ratings, and insider trades. Needs a free Finnhub key.
- **ORDER FLOW**: who is pushing the price. Buyers' share of traded value, net flow, cumulative volume delta against price, large trades, and plain-English readings (aggressive buying, absorption by passive sellers, and so on) for 1m/5m/15m/1h windows. For crypto, the live order book from Binance: spread, bid/ask imbalance within 0.5/1/2%, the biggest walls and a depth chart. For US stocks, Finnhub trades (buy/sell estimated by the tick rule) and 13F institutional holders with market makers (Citadel, Susquehanna, Virtu, Jane Street…) tagged, where your Finnhub plan includes them. A FLOW chip next to the live price shows the 5-minute buy share, and the AI analyst receives the flow summary. Market makers' actual positions are private; this shows the liquidity they post and the trades that happen.
- **PORT**: portfolio with live value, profit and loss, today's change and weights. `BUY AAPL 10 @ 180`, `SELL AAPL 5`, or use the form.
- **ALRT**: price alerts (`ALERT BTCUSD > 70000`) with a notification, a sound and, optionally, an AI explanation of the move; plus a position-size calculator. Alerts are checked while the page is open.
- **Quick AI questions**: one-tap buttons in the AI screen (explain this move, bull vs bear, latest earnings, levels and catalysts, vs sector).
- **Installable app**: click ⤓ INSTALL APP (Chrome/Edge), or on iPhone use Share → Add to Home Screen. It opens full-screen with its own icon.

- **BACKTEST**: test a setup (breakout, pullback to EMA20, volume spike, score 70/30) on up to 5,000 bars of Binance history for crypto, with ATR stops, R targets, fixed / trailing / half-at-1R exits, commission and slippage. Entries fill on the bar after the signal; if stop and target are both hit in one bar, the stop counts. The last 20–40% of the data is held back as out-of-sample, and a verdict says whether the edge holds there. COMPARE SETUPS and COMPARE TIMEFRAMES rank the options by out-of-sample results. For stocks, use `tradingview/terminal_strategy.pine` in TradingView's Strategy Tester (same rules, with an in-sample / out-of-sample table on the chart).
- **JRNL (trade journal)**: log trades (`LOG LONG NVDA 10 @ 130 STOP 125 TARGET 145`, or the form, with setup and reasons), close them (`CLOSE NVDA @ 140`, or at the live price), and see net P&L, win rate, profit factor, average win and loss, expectancy, average R, max drawdown, an equity curve, and results by setup and symbol. Risk rules (daily loss limit, max risk per trade, max trades per day) show a red banner across the terminal when broken. EXPORT CSV for spreadsheets; AI REVIEW asks the analyst to critique your trades.
- **Backup**: BACKUP ALL saves your watchlist, alerts, portfolio, journal and settings to a file (API keys are left out); RESTORE loads it on another device or browser.
- **Reliability**: lights in the header show each data source's state (TradingView, Binance, Finnhub quotes, Finnhub live feed); every live price carries a LIVE / DELAYED / STALE / CLOSED tag (also in the portfolio and alerts); crypto prices are cross-checked against Coinbase; an offline banner appears when the connection drops; the calculator warns before using a delayed price.

API keys are stored only in your browser and are sent only to their own provider (Finnhub or Anthropic). Don't save them on a shared computer, and set a monthly spend limit in the Claude Console.

The chart is TradingView's embeddable widget, which can't load custom Pine scripts. To use `terminal.pine`, open it on tradingview.com.

### Hosting on GitHub Pages

`.github/workflows/pages.yml` publishes the `web/` folder whenever it changes on `main`. One-time setup:

1. In the repo on GitHub, go to **Settings → Pages** and set **Source** to **GitHub Actions**.
2. Merge this branch into `main`. The workflow runs and the site appears at the address above. You can also run it by hand from the **Actions** tab.
