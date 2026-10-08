"""
predictions_cup_bot.py - trading engine for the Predictions Cup
===============================================================

Start it with run_bot.py (settings live there). This file holds the logic:

  * Cup API client + broker (prices, positions, balance, orders)
  * paper broker for manual mode (you type prices, it tracks a fake account)
  * fair value from your own number and/or Kalshi / Polymarket
  * NEWS: reads the tournament news feed (if the Cup has one) and Google News
    headlines for each market, scores them up/down and nudges the fair value
  * TRENDS: an EMA "ribbon" over the Cup price history; trades with the trend
  * risk: half-Kelly sizing, max share of equity per market, take profit,
    stop loss (fixed or trailing), cooldown after every trade and a longer
    one after a take profit / stop loss

Only the standard library is used - nothing to pip install.

!!! BEFORE TRADING FOR REAL !!!
The Cup endpoint paths below (ENDPOINTS / DEFAULT_BASE_URL / order payload in
CupBroker._send) were written without access to the Cup API docs. Check them
against the docs on sig.thesuper.market, then set LIVE_ORDERS_VERIFIED = True.
Until then the bot reads prices and positions normally but only PRINTS the
orders it would send ("DRY RUN").
"""

from __future__ import annotations

import email.utils
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# ============================ CUP API ======================================
LIVE_ORDERS_VERIFIED = False   # True only after checking the paths below
DEFAULT_BASE_URL = "https://sig.thesuper.market/api/v1"
ENDPOINTS = {
    "me":          "/me",
    "tournaments": "/tournaments",
    "contracts":   "/tournaments/{slug}/exchanges",
    "prices":      "/exchanges/prices",
    "positions":   "/tournaments/{id}/positions",
    "orders":      "/orders",
    "news":        "/tournaments/{slug}/news",
}
# ===========================================================================

KALSHI_URL = "https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
POLYMARKET_URL = "https://gamma-api.polymarket.com/markets?slug={slug}"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
USER_AGENT = "predictions-cup-bot/1.0"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    strategy: str = "both"            # "fair", "ribbon" (trend) or "both"
    take_profit: float = 0.08         # probability points, 0 = off
    stop_loss: float = 0.08           # probability points, 0 = off
    trailing: bool = False            # stop follows the best price since entry
    kelly_fraction: float = 0.5
    min_edge: float = 0.03
    max_market_frac: float = 0.20
    cooldown_runs: int = 3            # rounds to sit out after TP / SL
    trade_cooldown_runs: int = 1      # rounds to sit out after ANY trade
    allow_short: bool = False         # sell YES you don't own (if the Cup allows it)
    # news
    use_news: bool = True
    news_weight: float = 0.05         # max shift of fair value from news (5 points)
    news_half_life_hours: float = 24  # older headlines count less
    news_refresh_seconds: int = 600   # fetch headlines at most this often
    # trend (EMA ribbon over Cup mid prices)
    ribbon_spans: tuple = (3, 5, 8, 13, 21)
    min_trend: float = 0.005          # fast-slow EMA gap needed to call a trend
    trend_gain: float = 3.0           # how much a trend moves the estimate
    max_trend_shift: float = 0.15
    # paper account (manual mode)
    paper_cash: float = 10_000.0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class CupAPIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


def http_json(url: str, method: str = "GET", headers: dict | None = None,
              body: dict | None = None, timeout: float = 15):
    """Returns (status, parsed json or text). Network failure -> ConnectionError."""
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise ConnectionError(f"Can't reach {urllib.parse.urlsplit(url).netloc}: {e}") from e
    text = raw.decode("utf-8", "replace")
    try:
        return status, json.loads(text) if text else {}
    except ValueError:
        return status, text


def http_text(url: str, timeout: float = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as e:
        raise ConnectionError(str(e)) from e


def _num(d: dict, *keys, default=None):
    """First key present in d that converts to a float."""
    for k in keys:
        v = d.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return default


# ---------------------------------------------------------------------------
# Cup API client
# ---------------------------------------------------------------------------

class CupClient:
    def __init__(self, api_key: str, base_url: str | None = None):
        self.key = api_key
        self.base = (base_url or DEFAULT_BASE_URL).rstrip("/")

    def _request(self, method: str, path: str, params: dict | None = None,
                 body: dict | None = None, retries: int = 3):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        headers = {"Authorization": f"Bearer {self.key}", "X-API-Key": self.key}
        for attempt in range(retries + 1):
            status, data = http_json(url, method, headers, body)
            if status == 429 or status >= 500:
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
            if status >= 400:
                err = data.get("error", data) if isinstance(data, dict) else {}
                if not isinstance(err, dict):
                    err = {"message": str(err)}
                raise CupAPIError(status, str(err.get("code") or _default_code(status)),
                                  str(err.get("message") or data)[:300])
            return data
        raise CupAPIError(status, _default_code(status), "gave up after retries")

    def get(self, path: str, **params):
        return self._request("GET", path, params)

    def post(self, path: str, body: dict):
        return self._request("POST", path, body=body)

    def connect(self) -> dict:
        """Check the key works; returns the account."""
        return _unwrap(self.get(ENDPOINTS["me"]))


def _default_code(status: int) -> str:
    return {400: "BAD_REQUEST", 401: "INVALID_API_KEY", 403: "FORBIDDEN",
            404: "NOT_FOUND", 429: "RATE_LIMITED"}.get(status, "HTTP_ERROR")


def _unwrap(r):
    return r.get("data", r) if isinstance(r, dict) else r


def _items(r) -> list:
    r = _unwrap(r)
    if isinstance(r, dict):
        for k in ("items", "results", "exchanges", "tournaments", "positions", "news"):
            if isinstance(r.get(k), list):
                return r[k]
        return []
    return r if isinstance(r, list) else []


def find_tournament(client: CupClient, slug: str | None = None) -> dict:
    ts = _items(client.get(ENDPOINTS["tournaments"]))
    if slug:
        for t in ts:
            if t.get("slug") == slug:
                return t
        raise CupAPIError(404, "NOT_FOUND", f"no tournament with slug '{slug}'")
    for t in ts:
        if "predictions cup" in str(t.get("name", "")).lower():
            return t
    if ts:
        return ts[0]
    raise CupAPIError(404, "NOT_FOUND", "no tournaments visible to this key")


def list_cup_contracts(client: CupClient, tournament_slug: str) -> list[dict]:
    """Every open contract: [{"exchange_id": str, "title": str}]."""
    out, cursor, page = [], None, 1
    while True:
        r = client.get(ENDPOINTS["contracts"].format(slug=tournament_slug),
                       status="open", limit=100, cursor=cursor, page=page if cursor is None else None)
        rows = _items(r)
        for x in rows:
            xid = x.get("exchangeId") or x.get("id")
            if xid is not None:
                out.append({"exchange_id": str(xid),
                            "title": x.get("title") or x.get("question") or x.get("name") or str(xid)})
        cursor = (r.get("nextCursor") or (r.get("meta") or {}).get("nextCursor")) if isinstance(r, dict) else None
        if cursor:
            continue
        if len(rows) < 100:
            return out
        page += 1


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------

@dataclass
class Market:
    id: str
    title: str = ""
    exchange_id: str | None = None
    manual: float | None = None
    kalshi: str | None = None
    polymarket: str | None = None
    polymarket_outcome: str | None = None
    news_query: str | None = None          # search text for Google News (default: title)
    news_keywords: list | None = None      # words a headline must contain to count
    news_flip: bool = False                # True if "good news" for the subject means NO
    bid: float = 0.0
    ask: float = 0.0
    position: float = 0.0                  # signed YES shares
    avg_price: float | None = None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2 if self.bid and self.ask else 0.0

    @property
    def quoted(self) -> bool:
        return 0 < self.bid < self.ask < 1


def load_markets(path: str) -> list[Market]:
    """Enabled markets from markets.json (entries without "enabled" count as enabled)."""
    with open(path) as f:
        raw = json.load(f)
    out = []
    for o in raw:
        if not o.get("enabled", True):
            continue
        out.append(Market(
            id=str(o["id"]), title=o.get("title", ""),
            exchange_id=str(o["cup_exchange_id"]) if o.get("cup_exchange_id") else None,
            manual=o.get("manual"), kalshi=o.get("kalshi"), polymarket=o.get("polymarket"),
            polymarket_outcome=o.get("polymarket_outcome"),
            news_query=o.get("news_query"), news_keywords=o.get("news_keywords"),
            news_flip=bool(o.get("news_flip", False)),
            bid=float(o.get("cup_bid") or o.get("cup_bid_when_listed") or 0),
            ask=float(o.get("cup_ask") or o.get("cup_ask_when_listed") or 0)))
    return out


@dataclass
class Order:
    market_id: str
    side: str            # "buy" or "sell" (YES shares)
    qty: int
    price: float
    reason: str

    def __str__(self):
        return f"{self.side.upper():<4} {self.qty:>7} {self.market_id:<18} @ {self.price:.3f}  ({self.reason})"


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------

class PaperBroker:
    """Manual mode: prices typed by you, fills assumed at bid/ask."""

    def __init__(self, markets: list[Market], cash: float = 10_000.0):
        self._markets = {m.id: m for m in markets}
        self.cash = cash

    def markets(self) -> list[Market]:
        return list(self._markets.values())

    def market(self, mid: str) -> Market:
        return self._markets[mid]

    def refresh(self):
        pass

    def equity(self) -> float:
        return self.cash + sum(m.position * m.mid for m in self.markets())

    def place(self, o: Order) -> bool:
        m = self._markets[o.market_id]
        sign = 1 if o.side == "buy" else -1
        new_pos = m.position + sign * o.qty
        if new_pos and (m.position == 0 or (new_pos > 0) != (m.position > 0)):
            m.avg_price = o.price                                  # fresh position
        elif sign * m.position > 0:                                # adding
            m.avg_price = (m.avg_price * abs(m.position) + o.price * o.qty) / abs(new_pos)
        if new_pos == 0:
            m.avg_price = None
        m.position = new_pos
        self.cash -= sign * o.qty * o.price
        return True


class CupBroker:
    """Live Cup account: prices, positions and balance from the API."""

    def __init__(self, client: CupClient, markets: list[Market], tournament: dict,
                 order_ttl: int = 15, max_order_qty: int = 5000):
        self.client = client
        self.t = tournament
        self._markets = {m.id: m for m in markets}
        self.order_ttl = order_ttl
        self.max_order_qty = max_order_qty
        self.cash = float(tournament.get("myBalance") or 0)

    def markets(self) -> list[Market]:
        return list(self._markets.values())

    def market(self, mid: str) -> Market:
        return self._markets[mid]

    def refresh(self):
        by_x = {m.exchange_id: m for m in self.markets()}
        ids = list(by_x)
        for i in range(0, len(ids), 100):
            r = self.client.get(ENDPOINTS["prices"], ids=",".join(ids[i:i + 100]),
                                tournamentId=self.t["id"])
            for q in _items(r):
                m = by_x.get(str(q.get("exchangeId")))
                if m:
                    m.bid = _num(q, "bestBid", "bid", default=0.0)
                    m.ask = _num(q, "bestAsk", "ask", default=0.0)
        try:
            r = self.client.get(ENDPOINTS["positions"].format(id=self.t["id"], slug=self.t.get("slug")))
            for m in self.markets():
                m.position, m.avg_price = 0.0, None
            for p in _items(r):
                m = by_x.get(str(p.get("exchangeId")))
                if not m:
                    continue
                qty = _num(p, "quantity", "netQuantity", "shares", default=None)
                if qty is None:
                    qty = _num(p, "yesQuantity", default=0) - _num(p, "noQuantity", default=0)
                m.position = qty
                m.avg_price = _num(p, "averagePrice", "avgPrice", "entryPrice")
        except CupAPIError as e:
            if e.status != 404:
                raise
            print("  (positions endpoint not found - check ENDPOINTS['positions'])")
        try:
            t = find_tournament(self.client, self.t.get("slug"))
            self.cash = float(t.get("myBalance") or self.cash)
        except CupAPIError:
            pass

    def equity(self) -> float:
        return self.cash + sum(m.position * m.mid for m in self.markets())

    def place(self, o: Order) -> bool:
        m = self._markets[o.market_id]
        left, ok = o.qty, True
        while left > 0:
            q = min(left, self.max_order_qty)
            ok = self._send(m, o, q) and ok
            left -= q
        return ok

    def _send(self, m: Market, o: Order, qty: int) -> bool:
        body = {
            "tournamentId": self.t["id"],
            "exchangeId": m.exchange_id,
            "side": o.side.upper(),
            "outcome": "YES",
            "type": "LIMIT",
            "price": round(o.price, 3),
            "quantity": int(qty),
            "expiresAt": datetime.fromtimestamp(time.time() + self.order_ttl,
                                                timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if not LIVE_ORDERS_VERIFIED:
            print(f"  [DRY RUN] would POST {ENDPOINTS['orders']} {json.dumps(body)}")
            return False
        self.client.post(ENDPOINTS["orders"], body)
        print(f"  sent: {o.side.upper()} {qty} {m.id} @ {o.price:.3f}")
        return True


# ---------------------------------------------------------------------------
# Outside prices (fair value)
# ---------------------------------------------------------------------------

_price_cache: dict = {}


def _cached(key, ttl, fn):
    hit = _price_cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        val = fn()
    except (ConnectionError, ValueError, KeyError, TypeError, IndexError):
        val = None
    _price_cache[key] = (time.time(), val)
    return val


def kalshi_price(ticker: str) -> float | None:
    def go():
        status, r = http_json(KALSHI_URL.format(ticker=urllib.parse.quote(ticker)))
        if status != 200:
            return None
        m = r["market"]
        bid = _num(m, "yes_bid_dollars")
        ask = _num(m, "yes_ask_dollars")
        if bid is None or ask is None:
            bid, ask = _num(m, "yes_bid", default=0) / 100, _num(m, "yes_ask", default=0) / 100
        if 0 < bid <= ask < 1:
            return (bid + ask) / 2
        last = _num(m, "last_price_dollars")
        return last if last is not None else (_num(m, "last_price", default=0) / 100 or None)
    return _cached(("kalshi", ticker), 30, go)


def polymarket_price(slug: str, outcome: str | None = None) -> float | None:
    def go():
        status, r = http_json(POLYMARKET_URL.format(slug=urllib.parse.quote(slug)))
        if status != 200 or not r:
            return None
        m = r[0] if isinstance(r, list) else r
        names = json.loads(m["outcomes"]) if isinstance(m["outcomes"], str) else m["outcomes"]
        prices = json.loads(m["outcomePrices"]) if isinstance(m["outcomePrices"], str) else m["outcomePrices"]
        want = (outcome or "Yes").lower()
        for n, p in zip(names, prices):
            if str(n).lower() == want:
                return float(p)
        return float(prices[0])
    return _cached(("poly", slug, outcome), 30, go)


def fair_value(m: Market, offline: bool) -> float | None:
    vals = []
    if m.manual is not None:
        vals.append(float(m.manual))
    if not offline:
        if m.kalshi:
            p = kalshi_price(m.kalshi)
            if p is not None:
                vals.append(p)
        if m.polymarket:
            p = polymarket_price(m.polymarket, m.polymarket_outcome)
            if p is not None:
                vals.append(p)
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

UP_WORDS = {
    "win", "wins", "won", "winning", "lead", "leads", "leading", "ahead", "surge", "surges",
    "gain", "gains", "rise", "rises", "rising", "boost", "boosted", "favored", "favorite",
    "momentum", "endorse", "endorses", "endorsed", "endorsement", "victory", "clinch",
    "clinches", "secure", "secures", "secured", "approve", "approved", "passes", "passed",
    "likely", "strong", "stronger", "record", "beat", "beats", "up", "higher", "jump", "jumps",
    "soar", "soars", "rally", "rallies", "confirmed", "advance", "advances", "keeps", "holds",
}
DOWN_WORDS = {
    "lose", "loses", "lost", "losing", "trail", "trails", "trailing", "behind", "drop", "drops",
    "fall", "falls", "fell", "slump", "slumps", "decline", "declines", "scandal", "indicted",
    "withdraw", "withdraws", "withdrew", "quit", "quits", "suspends", "unlikely",
    "weak", "weaker", "down", "lower", "plunge", "plunges", "sink", "sinks", "crisis",
    "rejected", "reject", "rejects", "fails", "failed", "blocked", "delay", "delayed",
    "investigation", "lawsuit", "concede", "concedes", "defeat", "defeated", "miss", "misses",
}
NEGATIONS = {"not", "no", "never", "won't", "isn't", "doesn't", "didn't", "can't", "unable"}
STOPWORDS = {
    "will", "the", "and", "for", "with", "that", "this", "from", "into", "than", "more", "less",
    "before", "after", "over", "under", "win", "wins", "keep", "keeps", "who", "what", "when",
    "which", "does", "have", "has", "been", "their", "they", "them", "there", "least", "most",
    "above", "below", "end", "yes", "2025", "2026", "2027", "2028",
}


@dataclass
class Headline:
    title: str
    published: float          # unix time
    source: str = ""
    exchange_ids: tuple = ()  # Cup news can be tagged to specific contracts


def headline_score(text: str) -> float:
    """-1 .. +1 : how 'up' or 'down' a headline reads. Crude word counting."""
    words = re.findall(r"[a-z']+", text.lower())
    up = down = 0
    for i, w in enumerate(words):
        s = 1 if w in UP_WORDS else -1 if w in DOWN_WORDS else 0
        if s and any(x in NEGATIONS for x in words[max(0, i - 3):i]):   # "not likely to win"
            s = -s
        up += s > 0
        down += s < 0
    return 0.0 if up == down else (up - down) / (up + down)


def keywords_for(m: Market) -> list[str]:
    if m.news_keywords:
        return [k.lower() for k in m.news_keywords]
    words = re.findall(r"[A-Za-z][A-Za-z0-9'.-]+", m.title)
    return [w.lower() for w in words if len(w) > 3 and w.lower() not in STOPWORDS]


def relevant(h: Headline, m: Market, kws: list[str]) -> bool:
    if h.exchange_ids:
        return m.exchange_id in h.exchange_ids
    t = h.title.lower()
    return any(k in t for k in kws)


def news_signal(m: Market, headlines: list[Headline], cfg: Config, now: float | None = None):
    """Returns (score -1..1, number of headlines used, best headline)."""
    now = now or time.time()
    kws = keywords_for(m)
    tot = wsum = 0.0
    used, top, top_w = 0, None, 0.0
    for h in headlines:
        if not relevant(h, m, kws):
            continue
        s = headline_score(h.title)
        if not s:
            continue
        age_h = max(0.0, (now - h.published) / 3600)
        w = 0.5 ** (age_h / cfg.news_half_life_hours)
        tot += w * s
        wsum += w
        used += 1
        if w * abs(s) > top_w:
            top, top_w = h, w * abs(s)
    if not used:
        return 0.0, 0, None
    score = (tot / wsum) * min(1.0, used / 3)       # few headlines -> less confidence
    return (-score if m.news_flip else score), used, top


def parse_rss(xml_text: str) -> list[Headline]:
    out = []
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        when = it.findtext("pubDate")
        try:
            ts = email.utils.parsedate_to_datetime(when).timestamp() if when else time.time()
        except (TypeError, ValueError):
            ts = time.time()
        src = (it.findtext("source") or "").strip()
        if title:
            out.append(Headline(title, ts, src))
    return out


def _parse_time(v) -> float:
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e12 else float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


class NewsFeed:
    """Tournament news (if the Cup has a feed) + Google News per market, cached."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._cache: dict = {}
        self._cup_news_missing = False

    def _get(self, key, fn) -> list[Headline]:
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.cfg.news_refresh_seconds:
            return hit[1]
        try:
            val = fn()
        except (ConnectionError, ET.ParseError, CupAPIError, ValueError):
            val = hit[1] if hit else []
        self._cache[key] = (time.time(), val)
        return val

    def cup_news(self, client, tournament) -> list[Headline]:
        if client is None or tournament is None or self._cup_news_missing:
            return []

        def go():
            try:
                r = client.get(ENDPOINTS["news"].format(slug=tournament.get("slug"), id=tournament.get("id")))
            except CupAPIError as e:
                if e.status == 404:
                    self._cup_news_missing = True
                    return []
                raise
            out = []
            for n in _items(r):
                title = n.get("title") or n.get("headline") or ""
                summary = n.get("summary") or n.get("body") or ""
                ids = n.get("exchangeIds") or ([n["exchangeId"]] if n.get("exchangeId") else [])
                out.append(Headline(f"{title}. {summary}".strip(". "),
                                    _parse_time(n.get("publishedAt") or n.get("createdAt") or time.time()),
                                    "Cup", tuple(str(i) for i in ids)))
            return out
        return self._get(("cup",), go)

    def web_news(self, m: Market) -> list[Headline]:
        q = m.news_query or m.title
        return self._get(("web", q), lambda: parse_rss(http_text(
            GOOGLE_NEWS_URL.format(q=urllib.parse.quote(q + " when:7d")))))


# ---------------------------------------------------------------------------
# Trend (EMA ribbon)
# ---------------------------------------------------------------------------

def ema_series_last(values: list[float], span: int) -> float:
    a = 2 / (span + 1)
    e = values[0]
    for v in values[1:]:
        e = a * v + (1 - a) * e
    return e


def ribbon(history: list[float], spans=(3, 5, 8, 13, 21), min_gap: float = 0.005):
    """Returns (direction +1/0/-1, strength = fast EMA - slow EMA)."""
    if len(history) < max(4, spans[0] + 1):
        return 0, 0.0
    emas = [ema_series_last(history, s) for s in spans]
    strength = emas[0] - emas[-1]
    if all(a > b for a, b in zip(emas, emas[1:])) and strength >= min_gap:
        return 1, strength
    if all(a < b for a, b in zip(emas, emas[1:])) and -strength >= min_gap:
        return -1, strength
    return 0, strength


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class MarketState:
    entry: float | None = None
    best: float | None = None
    cooldown: int = 0
    history: list = field(default_factory=list)


@dataclass
class Book:
    round: int = 0
    markets: dict = field(default_factory=dict)
    trades: list = field(default_factory=list)
    news: NewsFeed | None = None

    def st(self, mid: str) -> MarketState:
        if mid not in self.markets:
            self.markets[mid] = MarketState()
        return self.markets[mid]


def load_state(path: str, broker) -> Book:
    book = Book()
    if not os.path.exists(path):
        return book
    try:
        with open(path) as f:
            d = json.load(f)
    except (ValueError, OSError):
        print(f"  (couldn't read {path}, starting fresh)")
        return book
    book.round = d.get("round", 0)
    book.trades = d.get("trades", [])
    for k, v in d.get("markets", {}).items():
        book.markets[k] = MarketState(**{f: v[f] for f in ("entry", "best", "cooldown", "history") if f in v})
    if isinstance(broker, PaperBroker) and "paper" in d:
        broker.cash = d["paper"].get("cash", broker.cash)
        for mid, p in d["paper"].get("positions", {}).items():
            if mid in broker._markets:
                broker._markets[mid].position = p["qty"]
                broker._markets[mid].avg_price = p.get("avg")
    return book


def save_state(path: str, book: Book, broker):
    d = {"round": book.round, "trades": book.trades[-500:],
         "markets": {k: asdict(v) for k, v in book.markets.items()}}
    if isinstance(broker, PaperBroker):
        d["paper"] = {"cash": broker.cash,
                      "positions": {m.id: {"qty": m.position, "avg": m.avg_price}
                                    for m in broker.markets() if m.position}}
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    fair: float | None
    news: float
    news_n: int
    trend: int
    strength: float
    estimate: float | None     # final probability estimate used to trade
    note: str = ""


def make_signal(m: Market, st: MarketState, cfg: Config, fair: float | None,
                news: float, news_n: int) -> Signal:
    trend, strength = ribbon(st.history, cfg.ribbon_spans, cfg.min_trend)
    shift = cfg.news_weight * news
    trend_est = None
    if trend:
        trend_est = m.mid + max(-cfg.max_trend_shift, min(cfg.max_trend_shift, strength * cfg.trend_gain))
    est, note = None, ""
    if cfg.strategy == "fair":
        est = fair + shift if fair is not None else None
    elif cfg.strategy == "ribbon":
        est = trend_est + shift if trend_est is not None else None
    else:  # both
        if fair is not None:
            est = fair + shift
            direction = 1 if est > m.mid else -1
            if trend and trend != direction:
                est, note = None, "trend disagrees"
        elif trend_est is not None:
            est = trend_est + shift
    if est is not None:
        est = max(0.01, min(0.99, est))
    return Signal(fair, news, news_n, trend, strength, est, note)


def kelly_qty(side: int, p: float, m: Market, cfg: Config, equity: float, cash: float) -> int:
    if side > 0:
        price = m.ask
        f = (p - price) / (1 - price)
        cost = price
    else:
        price = m.bid
        f = (price - p) / price
        cost = 1 - price                     # worst-case loss per short share
    if f <= 0 or cost <= 0:
        return 0
    dollars = min(cfg.kelly_fraction * f * equity, cfg.max_market_frac * equity)
    if side > 0:
        dollars = min(dollars, max(0.0, cash))
    return int(dollars / cost)


def decide(m: Market, st: MarketState, sig: Signal, cfg: Config, equity: float, cash: float):
    """Returns (Order | None, status text, hit_tp_or_sl)."""
    pos = m.position
    if not m.quoted:
        return None, "no quote", False

    # 1. take profit / stop loss
    if pos and st.entry is not None:
        if pos > 0:
            px = m.bid
            st.best = px if st.best is None else max(st.best, px)
            gain = px - st.entry
            drop = (st.best if cfg.trailing else st.entry) - px
        else:
            px = m.ask
            st.best = px if st.best is None else min(st.best, px)
            gain = st.entry - px
            drop = px - (st.best if cfg.trailing else st.entry)
        side = "sell" if pos > 0 else "buy"
        if cfg.take_profit and gain >= cfg.take_profit:
            return Order(m.id, side, int(abs(pos)), px, f"take profit +{gain:.3f}"), "TP", True
        if cfg.stop_loss and drop >= cfg.stop_loss:
            kind = "trailing stop" if cfg.trailing else "stop loss"
            return Order(m.id, side, int(abs(pos)), px, f"{kind} -{drop:.3f}"), "SL", True

    p = sig.estimate
    # 2. edge gone / reversed -> close
    if pos > 0 and p is not None and p < m.bid:
        return Order(m.id, "sell", int(pos), m.bid, f"edge gone (est {p:.3f} < bid)"), "exit", False
    if pos < 0 and p is not None and p > m.ask:
        return Order(m.id, "buy", int(-pos), m.ask, f"edge gone (est {p:.3f} > ask)"), "exit", False

    # 3. cooldown blocks new entries
    if st.cooldown > 0:
        return None, f"cooldown {st.cooldown}", False
    if p is None:
        return None, sig.note or "no estimate", False

    # 4. entries / adds
    if p - m.ask >= cfg.min_edge:
        target = kelly_qty(1, p, m, cfg, equity, cash)
        add = target - int(max(pos, 0))
        if pos >= 0 and add > 0 and add >= max(1, 0.2 * target):
            return Order(m.id, "buy", add, m.ask, f"est {p:.3f} vs ask {m.ask:.3f}"), "buy", False
    elif m.bid - p >= cfg.min_edge and cfg.allow_short:
        target = kelly_qty(-1, p, m, cfg, equity, cash)
        add = target - int(max(-pos, 0))
        if pos <= 0 and add > 0 and add >= max(1, 0.2 * target):
            return Order(m.id, "sell", add, m.bid, f"est {p:.3f} vs bid {m.bid:.3f}"), "sell", False
    return None, "hold", False


def _record_fill(prev_pos: float, st: MarketState, o: Order):
    """Update entry/best price after an order went through."""
    sign = 1 if o.side == "buy" else -1
    new_pos = prev_pos + sign * o.qty
    if new_pos == 0:
        st.entry = st.best = None
    elif prev_pos == 0 or (new_pos > 0) != (prev_pos > 0) or st.entry is None:
        st.entry = st.best = o.price
    elif sign * prev_pos > 0:                      # adding: average the entry
        st.entry = (st.entry * abs(prev_pos) + o.price * o.qty) / abs(new_pos)


# ---------------------------------------------------------------------------
# One round
# ---------------------------------------------------------------------------

def run_once(broker, cfg: Config, book: Book, execute: bool = True, offline: bool = False,
             confirm=None) -> list[Order]:
    broker.refresh()
    book.round += 1
    if book.news is None:
        book.news = NewsFeed(cfg)
    client = getattr(broker, "client", None)
    use_news = cfg.use_news and not offline
    cup_news = book.news.cup_news(client, getattr(broker, "t", None)) if use_news else []

    equity, cash = broker.equity(), broker.cash
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n=== round {book.round} | {stamp} | equity {equity:,.0f} | cash {cash:,.0f} ===")
    print(f"  {'market':<18} {'bid':>5} {'ask':>5} {'fair':>5} {'news':>6} {'trend':>5} "
          f"{'est':>5} {'pos':>7}  status")

    orders, hits = [], {}
    for m in broker.markets():
        st = book.st(m.id)
        if m.quoted:
            st.history.append(round(m.mid, 4))
            del st.history[:-100]
        if m.avg_price is not None and m.position and st.entry is None:
            st.entry = st.best = m.avg_price          # position opened outside the bot
        if not m.position:
            st.entry = st.best = None

        fair = fair_value(m, offline)
        news, news_n, top = 0.0, 0, None
        if use_news:
            news, news_n, top = news_signal(m, cup_news + book.news.web_news(m), cfg)
        sig = make_signal(m, st, cfg, fair, news, news_n)
        o, status, hit = decide(m, st, sig, cfg, equity, cash)
        if st.cooldown > 0:
            st.cooldown -= 1
        if o:
            orders.append(o)
            hits[m.id] = hit
            if o.side == "buy":
                cash -= o.qty * o.price
        f = lambda v: f"{v:.3f}"[1:] if v is not None else "  -  "
        trend = {1: "up", -1: "down", 0: "flat"}[sig.trend]
        print(f"  {m.id:<18} {f(m.bid):>5} {f(m.ask):>5} {f(fair):>5} "
              f"{news:+.2f}{'(' + str(news_n) + ')' if news_n else '':<4} {trend:>5} "
              f"{f(sig.estimate):>5} {m.position:>7.0f}  {status}")
        if top and news_n:
            print(f"  {'':<18} news: {top.title[:90]}")

    if not orders:
        print("  no orders this round")
        return []
    print("\n  Orders:")
    for o in orders:
        print(f"    {o}")
    if not execute:
        return orders
    if confirm is not None and not confirm(orders):
        print("  skipped.")
        return []

    for o in orders:
        m, st = broker.market(o.market_id), book.st(o.market_id)
        prev_pos = m.position
        try:
            placed = broker.place(o)
        except CupAPIError as e:
            print(f"  order failed for {o.market_id}: {e}")
            continue
        if not placed:
            continue
        _record_fill(prev_pos, st, o)
        st.cooldown = max(st.cooldown, cfg.cooldown_runs if hits.get(o.market_id) else cfg.trade_cooldown_runs)
        book.trades.append({"time": time.time(), "round": book.round, "market": o.market_id,
                            "side": o.side, "qty": o.qty, "price": o.price, "reason": o.reason})
    return orders
