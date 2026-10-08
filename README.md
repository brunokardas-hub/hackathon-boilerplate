# Predictions Cup bot

Trading bot for the Predictions Cup (sig.thesuper.market).

| file | what it is |
|---|---|
| `run_bot.py` | the launcher - **all settings are at the top of this file** |
| `predictions_cup_bot.py` | the engine (API, strategy, news, trends, risk) |
| `tests/` | offline tests: `python3 -m unittest discover tests` |

## Run

```bash
python3 run_bot.py          # Windows: python run_bot.py
python3 run_bot.py list     # refresh markets.json with every Cup contract
```

First run asks for your API key and saves it in `api_key.txt` (git-ignored, never share it).

## What it does each round

1. Reads Cup prices, your positions and balance.
2. **Fair value** - your `manual` number and/or Kalshi / Polymarket prices.
3. **News** - tournament news feed (if the Cup has one) + Google News headlines
   for each market, scored up/down, newer headlines count more.
   Moves the fair value by at most `NEWS_WEIGHT`.
4. **Trend** - EMA ribbon over Cup prices (up / down / flat).
5. **Strategy** - `fair`, `ribbon` (trend only) or `both` (fair value, skipped if the trend disagrees).
6. **Risk** - half-Kelly size, max `MAX_MARKET_FRACTION` of equity per market,
   take profit, stop loss (or trailing stop), `TRADE_COOLDOWN` rounds after any trade,
   `COOLDOWN` rounds after a take profit / stop loss.

Per market in `markets.json` you can tune news with
`"news_query"` (search text), `"news_keywords"` (words a headline must contain) and
`"news_flip": true` (good news for the subject means NO).

## Before trading real money

The Cup API paths in `ENDPOINTS` (top of `predictions_cup_bot.py`) were written without the
API docs. Until you check them and set `LIVE_ORDERS_VERIFIED = True`, the bot only prints
`[DRY RUN]` orders. Keep `CONFIRM_ORDERS = True` for the first sessions.
