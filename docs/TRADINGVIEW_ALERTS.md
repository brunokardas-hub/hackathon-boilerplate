# Always-on alerts with TradingView

Alerts in the web terminal only work while the page is open. TradingView alerts
run on TradingView's servers around the clock, even when your phone is locked and
your computer is off, and they arrive as push notifications in the TradingView
phone app. Use them for any alert you'd act on.

## One-time setup

1. Add the indicator to a chart: Pine Editor → paste `tradingview/terminal.pine`
   → **Save** → **Add to chart**.
2. Install the **TradingView app** on your phone, sign in with the same account,
   and allow notifications when it asks.

## Option A: one alert for every signal (recommended)

TradingView's free plan allows only a few active alerts. This option uses just
one alert per symbol and covers every signal the terminal knows about.

1. Open the chart of the symbol you want to watch, on the timeframe you trade.
2. Click the **Alert** button (alarm-clock icon) in the top toolbar, or press
   **Alt + A**.
3. **Condition**: choose **TERMINAL**, then **Any alert() function call**.
4. **Trigger**: **Once per bar close**. The alert then fires only on signals
   that are confirmed when the bar closes, never on a signal that appears and
   disappears mid-bar.
5. **Expiration**: as long as your plan allows (open-ended on paid plans).
6. **Notifications**: tick **Notify in app** (phone push). Also tick
   **Show pop-up** and **Play sound** if you watch on a computer, and
   **Send email** as a backup.
7. Click **Create**.

You'll get a message like:

> NVDA 131.42 (60): broke prior-day high, volume 2.4x average

The signals it covers:
- new 52-week high or low;
- your own price levels;
- prior-day high or low breaks (intraday charts);
- gaps at the open;
- volume spikes;
- RSI above 70 or below 30;
- the fast/mid EMA cross;
- the score crossing 70 or 30.

## Option B: one alert per signal

To be told about only one thing, for example "NVDA above 140", follow the same
steps but pick that signal under **Condition** instead of "Any alert() function
call":

| Condition | Fires when |
|---|---|
| Price above my level / Price below my level | Price crosses the level you set in the indicator's settings (Alerts section) |
| Broke prior-day high / low | Price crosses yesterday's high or low (intraday charts) |
| Gap up / Gap down at the open | The day opens at least the set % above or below yesterday's close |
| Volume spike | Bar volume is at least the set multiple of its 20-bar average |
| New 52-week high / low | Price breaks the 52-week range |
| RSI overbought / oversold | RSI crosses above 70 or below 30 |
| EMA fast/mid cross | The 20 and 50 EMAs cross |
| Score turned strong / weak | The terminal score crosses 70 or 30 |

## Setting your own price levels

Open the indicator's settings (gear icon) → **Alerts** → enter **Price crosses
above** and/or **Price crosses below**. Set 0 to turn a level off.

## Things that catch people out

- **Alerts keep the settings they were created with.** If you change the
  indicator's settings or edit the script, delete the alert and create it again.
- **Each alert belongs to one symbol and one timeframe:** the chart's, when you
  created it. A 1-hour chart alert checks 1-hour bars.
- **Plan limits:** the free plan allows only a few active alerts, and they may
  expire. Check **Alerts** in the right-hand panel to see what's running.
- **Delayed data:** some exchanges are delayed on TradingView unless you buy
  their real-time data. Alerts fire on whatever data your plan gets.
- **Test an alert first:** set a level just above the current price on a
  1-minute chart and check that the notification reaches your phone.
- **An alert is a prompt to look, not an instruction to trade.** Check the
  chart before acting.
