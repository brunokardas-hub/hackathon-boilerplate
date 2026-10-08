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
- **Overlays and alerts**: EMAs, VWAP and the prior day's high/low, plus alerts for 52-week breaks, RSI extremes and EMA crosses

**Install:** open TradingView → *Pine Editor* → paste in the contents of `terminal.pine` → *Save* → *Add to chart*. Change symbols, position and size in the indicator's settings.

## Web terminal (`web/index.html`)

A Bloomberg-style page in a single file. Use it at **https://brunokardas-hub.github.io/hackathon-boilerplate/** once GitHub Pages is on (see below), or download the file and double-click it.

- **Command line**: type `AAPL`, `NYSE:BA`, `BTCUSD` or `EURUSD` and press Enter to load a symbol. Other commands: `N`, `GP`, `FA`, `TA` and `ECO` jump to a panel; `HEAT` / `HEAT CRYPTO` open the market heatmap; `EQS` / `EQS CRYPTO` / `EQS FX` open the screener; `ASK <question>` asks the AI analyst; `BRIEF` writes a morning briefing; `HELP` lists everything. Press `/` to focus the command line.
- **MAIN screen**: a large TradingView chart (press **⤢ MAX** or type `MAX` to fill the screen; Esc to exit), security overview, a multi-asset monitor, a technicals summary, company financials (stocks only), an economic calendar, a ticker tape and world clocks.
- **News**: works with no setup, using TradingView's news feed. Paste a free [Finnhub](https://finnhub.io/register) key into the news panel to get live headlines that refresh every 60 seconds, with TICKER / TOP / FX / CRYPTO / M&A tabs and a rough ▲/▼ tone tag based on keywords.
- **HEAT**: market map of the S&P 500, Nasdaq 100, all US stocks, the DAX or crypto. Tile size is market cap and colour is % change.
- **EQS**: TradingView's screener for US stocks, crypto or FX, with filters and column sets.
- **AI analyst**: ask questions in plain English. Claude gets the symbol on screen, plus the live quote and recent headlines if you added a Finnhub key, and can search the web. Add your own [Anthropic API key](https://platform.claude.com/settings/keys) in the AI screen's SETUP panel. You pay Anthropic per question, and the screen shows the estimated cost of each answer. The default model is Claude Opus 5.5; Sonnet 5.5 costs about half as much and Haiku 5.5 far less. Answers are information, not financial advice.

API keys are stored only in your browser and are sent only to their own provider (Finnhub or Anthropic). Don't save them on a shared computer, and set a monthly spend limit in the Claude Console.

The chart is TradingView's embeddable widget, which can't load custom Pine scripts. To use `terminal.pine`, open it on tradingview.com.

### Hosting on GitHub Pages

`.github/workflows/pages.yml` publishes the `web/` folder whenever it changes on `main`. One-time setup:

1. In the repo on GitHub, go to **Settings → Pages** and set **Source** to **GitHub Actions**.
2. Merge this branch into `main`. The workflow runs and the site appears at the address above. You can also run it by hand from the **Actions** tab.
