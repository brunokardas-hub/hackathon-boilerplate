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
- **Overlays and alerts**: EMAs, VWAP and the prior day's high/low, plus alerts for 52-week breaks, RSI extremes and EMA crosses

**Install:** open TradingView → *Pine Editor* → paste in the contents of `terminal.pine` → *Save* → *Add to chart*. Change symbols, position and size in the indicator's settings.

## Web terminal with news (`web/terminal.html`)

A Bloomberg-style page in a single file. Open it in any browser by double-clicking it; there's nothing to install.

- **Command line**: type `AAPL`, `NYSE:BA`, `BTCUSD` or `EURUSD` and press Enter to load a symbol. Type `N`, `GP`, `FA`, `TA` or `ECO` to jump to a panel, or `HELP` for the list. Press `/` to focus the command line.
- **Panels**: security overview, a full TradingView chart, a multi-asset monitor, a technicals summary, company financials (stocks only), an economic calendar, a ticker tape and world clocks.
- **News**: works with no setup, using TradingView's news feed. Paste a free [Finnhub](https://finnhub.io/register) key into the news panel to get live headlines that refresh every 60 seconds, with TICKER / TOP / FX / CRYPTO / M&A tabs and a rough ▲/▼ tone tag based on keywords. The key is stored only in your browser.

The chart is TradingView's embeddable widget, which can't load custom Pine scripts. To use `terminal.pine`, open it on tradingview.com.
