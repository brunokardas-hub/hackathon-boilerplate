# hackathon-boilerplate
🚀 Production-ready boilerplate for rapid hackathon development and high-performance econometric data analysis in 2026. Optimized for Cursor AI.

## TradingView terminal (`tradingview/terminal.pine`)

A Bloomberg-style dashboard for TradingView, written in Pine Script v6. It draws an amber-on-black panel over any chart:

- **Quote**: last price, net and % change, open, high, low, previous close, volume compared with its 20-day average
- **52-week range**: the high, the low and a bar showing where the price sits between them
- **Performance**: 1D / 1W / 1M / 3M / YTD / 1Y returns, plus relative strength against a benchmark (SPY by default)
- **Technicals**: RSI, ATR, MACD, three EMAs, VWAP and an overall trend read
- **Monitor**: six symbols you choose (default SPY, QQQ, DXY, US10Y, Gold, BTC)
- **Overlays and alerts**: EMAs, VWAP and the prior day's high/low, plus alerts for 52-week breaks, RSI extremes and EMA crosses

**Install:** open TradingView → *Pine Editor* → paste in the contents of `terminal.pine` → *Save* → *Add to chart*. Change symbols, position and size in the indicator's settings.
