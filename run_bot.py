"""
run_bot.py - launcher for the Predictions Cup bot
=================================================

Put this file in the SAME folder as predictions_cup_bot.py.

  VS Code : open run_bot.py and press the ▶ Run button
  Terminal: python run_bot.py          (Mac: python3 run_bot.py)
            python run_bot.py list     -> refresh the list of Cup markets

API MODE (default) - trades on the Cup by itself:
  1. First run asks for your API key (sig.thesuper.market -> My Profile ->
     API Keys, with the "read" and "trade" scopes) and saves it in api_key.txt.
     Never share or upload that file.
  2. If markets.json has no Cup markets yet, the bot downloads all of them into
     markets.json and stops. Open it and, for each market you want to trade,
     set "enabled": true and give it a fair value: "manual" (your probability,
     0-1) and/or a "kalshi" ticker / "polymarket" slug for the same question.
  3. Run again. Every LOOP_SECONDS the bot fetches live Cup prices and your
     positions, decides, shows the orders and (if CONFIRM_ORDERS) asks y/n
     before sending. Ctrl+C to stop.

MANUAL MODE (MODE = "manual") - no API: you type the prices and place the
printed orders yourself.
"""

import json
import os
import re
import sys
import time

# ============================ SETTINGS ======================================
MODE          = "api"      # "api" = trade through the Cup API, "manual" = type prices
CONFIRM_ORDERS = True      # api mode: ask y/n before sending orders (False = fully automatic)
LOOP_SECONDS  = 60         # api mode: seconds between rounds
TOURNAMENT_SLUG = None     # None = find the Predictions Cup automatically

STRATEGY      = "both"     # "fair", "both" or "ribbon"
TAKE_PROFIT   = 0.08       # take profit, in probability points (0 = off)
STOP_LOSS     = 0.08       # stop loss, in probability points (0 = off)
TRAILING_STOP = False      # True = stop follows the best price since entry
KELLY         = 0.5        # position size multiplier (0.5 = half Kelly)
MIN_EDGE      = 0.03       # min gap between fair value and Cup price to trade
MAX_MARKET_FRACTION = 0.20 # max share of equity at risk in one market
COOLDOWN      = 3          # rounds to wait after a take profit / stop loss
TRADE_COOLDOWN = 1         # rounds to wait after ANY trade in a market
ALLOW_SHORT   = False      # True = sell YES you don't own (only if the Cup allows it)
USE_NEWS      = True       # read tournament news + Google News headlines
NEWS_WEIGHT   = 0.05       # max shift of fair value from news (0.05 = 5 points)
MAX_ORDER_QTY = 5000       # api mode: split bigger orders into chunks of this size
ORDER_TTL     = 15         # api mode: unfilled orders expire after this many seconds
USE_ONLINE_PRICES = True   # fetch Kalshi / Polymarket prices (needs internet)
# ============================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
MARKETS_FILE = os.path.join(HERE, "markets.json")
STATE_FILE = os.path.join(HERE, "bot_state_api.json" if MODE == "api" else "bot_state.json")
KEY_FILE = os.path.join(HERE, "api_key.txt")
sys.path.insert(0, HERE)

try:
    import predictions_cup_bot as bot
except ImportError:
    sys.exit("Can't find predictions_cup_bot.py - put it in the same folder as run_bot.py.")


def make_config():
    return bot.Config(strategy=STRATEGY, take_profit=TAKE_PROFIT, stop_loss=STOP_LOSS,
                      trailing=TRAILING_STOP, kelly_fraction=KELLY, min_edge=MIN_EDGE,
                      max_market_frac=MAX_MARKET_FRACTION, cooldown_runs=COOLDOWN,
                      trade_cooldown_runs=TRADE_COOLDOWN, allow_short=ALLOW_SHORT,
                      use_news=USE_NEWS, news_weight=NEWS_WEIGHT)


# ---------------------------------------------------------------------------
# API mode
# ---------------------------------------------------------------------------

def get_api_key():
    """Returns (key, where it came from)."""
    key = os.environ.get("SIG_API_KEY", "").strip()
    if key:
        return key, "env"
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            key = f.read().strip()
        if key:
            return key, "file"
    key = input("Paste your Predictions Cup API key: ").strip()
    if not key:
        sys.exit("No key given.")
    return key, "typed"


def connect():
    key, source = get_api_key()
    client = bot.CupClient(key, os.environ.get("SIG_BASE_URL"))
    try:
        acc = client.connect()
        t = bot.find_tournament(client, TOURNAMENT_SLUG)
        if source == "typed":                      # only save a key that works
            with open(KEY_FILE, "w") as f:
                f.write(key)
            print(f"Key works - saved to {KEY_FILE} (keep this file private).")
    except bot.CupAPIError as e:
        if e.status == 401 and source == "file":
            os.remove(KEY_FILE)                    # bad saved key: ask again next time
        hints = {
            "INVALID_API_KEY": "the key is wrong or deleted - run again and paste a new one",
            "API_KEY_REVOKED": "the key was revoked - create a new one and run again",
            "API_KEY_EXPIRED": "the key expired - create a new one and run again",
            "INSUFFICIENT_SCOPES": "the key needs the 'read' and 'trade' scopes",
            "TERMS_NOT_ACKNOWLEDGED": "accept the current terms on sig.thesuper.market first",
            "RESIDENCE_UPDATE_REQUIRED": "update your residence in your Cup registration",
            "FORBIDDEN": "confirm your email / join the tournament on the site first",
        }
        sys.exit(f"API error: {e}\n-> {hints.get(e.code, 'see the message above')}")
    except ConnectionError as e:
        sys.exit(f"{e}\nCheck your internet connection.")
    print(f"Connected as {acc.get('username') or acc.get('id')} | tournament "
          f"'{t['name']}' ({t['slug']}) | balance {t.get('myBalance', 0):,.0f} "
          f"{t.get('currencyName', '')}")
    return client, t


def slug(title: str, used: set) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").upper()[:18].strip("-") or "MKT"
    base, i = s, 2
    while s in used:
        s, i = f"{base[:15]}-{i}", i + 1
    used.add(s)
    return s


def list_markets(client, t, write_to: str):
    """Download every open Cup contract with live prices into a markets file."""
    rows = bot.list_cup_contracts(client, t["slug"])
    prices = {}
    ids = [r["exchange_id"] for r in rows]
    for i in range(0, len(ids), 100):
        r = client.get("/exchanges/prices", ids=",".join(ids[i:i + 100]), tournamentId=t["id"])
        prices.update({str(q["exchangeId"]): q for q in r.get("data", [])})

    old = {}
    if os.path.exists(write_to):
        with open(write_to) as f:
            old = {str(o.get("cup_exchange_id")): o for o in json.load(f) if o.get("cup_exchange_id")}

    used, out = {o["id"] for o in old.values()}, []
    for r in rows:
        q = prices.get(r["exchange_id"], {})
        prev = old.get(r["exchange_id"])
        if prev:                                       # keep what you already filled in
            out.append(prev)
            continue
        out.append({"id": slug(r["title"], used), "title": r["title"],
                    "cup_exchange_id": r["exchange_id"], "enabled": False,
                    "manual": None, "kalshi": None, "polymarket": None,
                    "polymarket_outcome": None,
                    "news_query": None, "news_keywords": None, "news_flip": False,
                    "cup_bid_when_listed": q.get("bestBid"),
                    "cup_ask_when_listed": q.get("bestAsk")})
    with open(write_to, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n{len(out)} Cup contracts:")
    for o in out:
        q = prices.get(str(o["cup_exchange_id"]), {})
        b, a = q.get("bestBid"), q.get("bestAsk")
        px = f"{b:.3f}/{a:.3f}" if b is not None and a is not None else "  no quote "
        print(f"  {'ON ' if o.get('enabled') else '   '}{o['id']:<18} {px}  {o['title'][:70]}")
    print(f"\nSaved to {write_to}. Set \"enabled\": true and a fair value "
          f"(manual / kalshi / polymarket) for the markets you want to trade.")


def has_cup_markets() -> bool:
    if not os.path.exists(MARKETS_FILE):
        return False
    with open(MARKETS_FILE) as f:
        return any(m.get("cup_exchange_id") for m in json.load(f))


def ask_confirm(orders) -> bool:
    try:
        return input(f"  Send these {len(orders)} order(s) to the Cup? [y/N]: ").strip().lower() == "y"
    except EOFError:
        return False


def run_api():
    client, t = connect()

    if (len(sys.argv) > 1 and sys.argv[1] == "list") or not has_cup_markets():
        if os.path.exists(MARKETS_FILE) and not has_cup_markets():
            os.replace(MARKETS_FILE, os.path.join(HERE, "markets_manual_backup.json"))
            print("Moved your old manual markets.json to markets_manual_backup.json")
        list_markets(client, t, MARKETS_FILE)
        return

    markets = [m for m in bot.load_markets(MARKETS_FILE) if m.exchange_id]
    if not markets:
        sys.exit('No market in markets.json has "enabled": true - enable some first.')
    # leftovers must expire before the next round, or they could fill on top of new orders
    ttl = max(5, min(ORDER_TTL, LOOP_SECONDS // 2)) if LOOP_SECONDS else ORDER_TTL
    broker = bot.CupBroker(client, markets, t, order_ttl=ttl, max_order_qty=MAX_ORDER_QTY)
    book = bot.load_state(STATE_FILE, broker)
    cfg = make_config()
    print(f"Trading {len(markets)} market(s) | strategy {STRATEGY} | TP {TAKE_PROFIT} | "
          f"SL {STOP_LOSS} | {'asks before sending' if CONFIRM_ORDERS else 'FULLY AUTOMATIC'} "
          f"| every {LOOP_SECONDS}s | Ctrl+C to stop")

    while True:
        try:
            bot.run_once(broker, cfg, book, execute=True, offline=not USE_ONLINE_PRICES,
                         confirm=ask_confirm if CONFIRM_ORDERS else None)
            bot.save_state(STATE_FILE, book, broker)
        except bot.CupAPIError as e:
            print(f"  API error this round, will retry: {e}")
        except OSError as e:
            print(f"  network problem this round, will retry: {e}")
        except KeyboardInterrupt:
            break
        try:
            time.sleep(LOOP_SECONDS)
        except KeyboardInterrupt:
            break
    bot.save_state(STATE_FILE, book, broker)
    print(f"\nStopped. Open orders expire on their own within {ttl}s. State saved.")


# ---------------------------------------------------------------------------
# Manual mode (no API)
# ---------------------------------------------------------------------------

EXAMPLE_MARKETS = [
    {"id": "HOUSE-DEM", "title": "Democrats win the House", "manual": 0.60,
     "kalshi": None, "polymarket": None, "polymarket_outcome": None,
     "cup_bid": 0.52, "cup_ask": 0.55},
    {"id": "SENATE-REP", "title": "Republicans keep the Senate", "manual": 0.70,
     "kalshi": None, "polymarket": None, "polymarket_outcome": None,
     "cup_bid": 0.68, "cup_ask": 0.71},
]


def ask_prices(broker) -> bool:
    print("\nEnter current Cup prices as 'bid ask' (Enter = keep, q = quit):")
    for m in broker.markets():
        while True:
            s = input(f"  {m.id:<12} [{m.bid:.2f} {m.ask:.2f}]: ").strip().lower()
            if s == "q":
                return False
            if s == "":
                break
            try:
                bid, ask = (float(x.replace(",", ".")) for x in s.split())
                if bid > 1 or ask > 1:
                    bid, ask = bid / 100, ask / 100
                if not 0 < bid < ask < 1:
                    raise ValueError
                m.bid, m.ask = bid, ask
                break
            except ValueError:
                print("    type two numbers like 0.52 0.55 (bid below ask)")
    return True


def run_manual():
    if not os.path.exists(MARKETS_FILE):
        with open(MARKETS_FILE, "w") as f:
            json.dump(EXAMPLE_MARKETS, f, indent=2)
        print(f"Created an example markets.json in {HERE} - edit it.\n")
    broker = bot.PaperBroker(bot.load_markets(MARKETS_FILE))
    book = bot.load_state(STATE_FILE, broker)
    cfg = make_config()
    while True:
        try:
            if not ask_prices(broker):
                break
        except (KeyboardInterrupt, EOFError):
            break
        bot.run_once(broker, cfg, book, execute=True, offline=not USE_ONLINE_PRICES)
        bot.save_state(STATE_FILE, book, broker)
        print("\nPlace the orders above on the Cup site, then enter new prices next round.")
    print("\nSaved. Bye!")


if __name__ == "__main__":
    run_api() if MODE == "api" else run_manual()
