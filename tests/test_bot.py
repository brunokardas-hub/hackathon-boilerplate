"""Offline tests: python3 -m unittest discover tests"""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import predictions_cup_bot as bot  # noqa: E402


def cfg(**kw):
    base = dict(strategy="fair", use_news=False, take_profit=0.08, stop_loss=0.08,
                cooldown_runs=3, trade_cooldown_runs=1)
    base.update(kw)
    return bot.Config(**base)


def paper(manual=0.60, bid=0.52, ask=0.55):
    m = bot.Market("HOUSE", "Democrats win the House", manual=manual, bid=bid, ask=ask)
    return bot.PaperBroker([m], cash=10_000), m


def run(broker, c, book, confirm=None):
    with redirect_stdout(io.StringIO()):
        return bot.run_once(broker, c, book, execute=True, offline=True, confirm=confirm)


class Trading(unittest.TestCase):
    def test_buys_when_fair_above_ask(self):
        b, m = paper()
        orders = run(b, cfg(), bot.Book())
        self.assertEqual(len(orders), 1)
        o = orders[0]
        self.assertEqual((o.side, o.price), ("buy", 0.55))
        # half Kelly: 0.5 * (0.60-0.55)/(0.45) * 10000 = 555 dollars -> 1010 shares
        self.assertEqual(o.qty, 1010)
        self.assertEqual(m.position, 1010)

    def test_no_trade_below_min_edge(self):
        b, _ = paper(manual=0.57)
        self.assertEqual(run(b, cfg(), bot.Book()), [])

    def test_trade_cooldown_blocks_next_round(self):
        b, m = paper()
        book = bot.Book()
        run(b, cfg(trade_cooldown_runs=2, max_market_frac=0.01), book)   # small first buy
        self.assertEqual(run(b, cfg(trade_cooldown_runs=2), book), [])   # cooldown 2
        self.assertEqual(run(b, cfg(trade_cooldown_runs=2), book), [])   # cooldown 1
        self.assertEqual(len(run(b, cfg(trade_cooldown_runs=2), book)), 1)  # adds now

    def test_stop_loss_then_cooldown(self):
        b, m = paper()
        book = bot.Book()
        c = cfg()
        run(b, c, book)
        self.assertAlmostEqual(book.st("HOUSE").entry, 0.55)
        m.bid, m.ask = 0.46, 0.49                   # bid fell 0.09 below entry
        m.manual = 0.62                             # still looks cheap, but SL wins
        o = run(b, c, book)[0]
        self.assertEqual(o.side, "sell")
        self.assertIn("stop loss", o.reason)
        self.assertEqual(m.position, 0)
        for _ in range(3):                          # 3 rounds of cooldown
            self.assertEqual(run(b, c, book), [])
        self.assertEqual(run(b, c, book)[0].side, "buy")

    def test_take_profit(self):
        b, m = paper()
        book = bot.Book()
        run(b, cfg(), book)
        m.bid, m.ask, m.manual = 0.64, 0.66, 0.80
        o = run(b, cfg(), book)[0]
        self.assertIn("take profit", o.reason)

    def test_trailing_stop_follows_best(self):
        b, m = paper()
        book = bot.Book()
        c = cfg(trailing=True, take_profit=0, stop_loss=0.05)
        run(b, c, book)
        m.manual = 0.90
        for bid in (0.60, 0.66, 0.70):              # climbs, best = 0.70
            m.bid, m.ask = bid, bid + 0.02
            run(b, c, book)
        m.bid, m.ask = 0.64, 0.66                   # 0.06 off the top, still above entry
        o = run(b, c, book)[0]
        self.assertIn("trailing stop", o.reason)
        self.assertEqual(o.side, "sell")

    def test_edge_gone_exit(self):
        b, m = paper()
        book = bot.Book()
        run(b, cfg(), book)
        m.manual = 0.50                              # now below the bid of 0.52
        o = run(b, cfg(), book)[0]
        self.assertIn("edge gone", o.reason)

    def test_confirm_no_skips(self):
        b, m = paper()
        run(b, cfg(), bot.Book(), confirm=lambda orders: False)
        self.assertEqual(m.position, 0)

    def test_short_only_when_allowed(self):
        b, m = paper(manual=0.40)
        self.assertEqual(run(b, cfg(), bot.Book()), [])
        o = run(b, cfg(allow_short=True), bot.Book())[0]
        self.assertEqual(o.side, "sell")
        self.assertEqual(m.position, -o.qty)


class Trend(unittest.TestCase):
    def test_ribbon_directions(self):
        up = [0.40 + 0.01 * i for i in range(25)]
        self.assertEqual(bot.ribbon(up)[0], 1)
        self.assertEqual(bot.ribbon(up[::-1])[0], -1)
        self.assertEqual(bot.ribbon([0.5] * 25)[0], 0)
        self.assertEqual(bot.ribbon(up[:3])[0], 0)   # not enough history

    def test_ribbon_strategy_buys_uptrend(self):
        m = bot.Market("X", "x", bid=0.60, ask=0.61)
        b = bot.PaperBroker([m])
        book = bot.Book()
        book.st("X").history = [0.40 + 0.01 * i for i in range(20)]
        o = run(b, cfg(strategy="ribbon"), book)[0]
        self.assertEqual(o.side, "buy")

    def test_both_skips_when_trend_disagrees(self):
        b, m = paper()                               # fair says buy
        book = bot.Book()
        book.st("HOUSE").history = [0.80 - 0.01 * i for i in range(25)]   # falling hard
        self.assertEqual(run(b, cfg(strategy="both"), book), [])


class News(unittest.TestCase):
    def test_headline_score(self):
        self.assertGreater(bot.headline_score("Democrats surge ahead in new House poll"), 0)
        self.assertLess(bot.headline_score("Democrats trail as House hopes fall"), 0)
        self.assertLess(bot.headline_score("Democrats not likely to win"), 0)
        self.assertEqual(bot.headline_score("House schedule announced"), 0)

    def test_news_signal_relevance_recency_flip(self):
        m = bot.Market("H", "Democrats win the House")
        now = time.time()
        hs = [bot.Headline("Democrats surge in House race", now),
              bot.Headline("Democrats gain in latest poll", now - 3600),
              bot.Headline("Democrats lead generic ballot", now - 7200),
              bot.Headline("Stocks fall sharply", now)]              # irrelevant
        score, n, top = bot.news_signal(m, hs, bot.Config(), now)
        self.assertEqual(n, 3)
        self.assertGreater(score, 0.9)
        m.news_flip = True
        self.assertLess(bot.news_signal(m, hs, bot.Config(), now)[0], 0)

    def test_cup_news_tagged_by_contract(self):
        m = bot.Market("H", "Something", exchange_id="42")
        hs = [bot.Headline("Big win reported", time.time(), "Cup", ("42",)),
              bot.Headline("Big loss reported", time.time(), "Cup", ("7",))]
        score, n, _ = bot.news_signal(m, hs, bot.Config())
        self.assertEqual(n, 1)
        self.assertGreater(score, 0)

    def test_parse_rss(self):
        xml = """<rss><channel>
          <item><title>Candidate surges</title><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate>
                <source>AP</source></item>
          <item><title>Second story</title></item></channel></rss>"""
        hs = bot.parse_rss(xml)
        self.assertEqual([h.title for h in hs], ["Candidate surges", "Second story"])
        self.assertEqual(hs[0].source, "AP")

    def test_news_moves_estimate(self):
        m = bot.Market("H", "Democrats win the House", manual=0.56, bid=0.52, ask=0.55)
        sig = bot.make_signal(m, bot.MarketState(), bot.Config(strategy="fair", news_weight=0.05),
                              0.56, 1.0, 3)
        self.assertAlmostEqual(sig.estimate, 0.61)


class State(unittest.TestCase):
    def test_roundtrip(self):
        b, m = paper()
        book = bot.Book()
        run(b, cfg(), book)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            bot.save_state(p, book, b)
            b2, m2 = paper()
            book2 = bot.load_state(p, b2)
        self.assertEqual(m2.position, m.position)
        self.assertAlmostEqual(b2.cash, b.cash)
        self.assertEqual(book2.st("HOUSE").cooldown, 1)
        self.assertEqual(book2.round, 1)
        self.assertEqual(len(book2.trades), 1)

    def test_load_markets_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            with open(p, "w") as f:
                json.dump([{"id": "A", "cup_exchange_id": 1, "enabled": True},
                           {"id": "B", "cup_exchange_id": 2, "enabled": False},
                           {"id": "C", "manual": 0.5, "cup_bid": 0.4, "cup_ask": 0.45}], f)
            ms = bot.load_markets(p)
        self.assertEqual([m.id for m in ms], ["A", "C"])
        self.assertEqual(ms[0].exchange_id, "1")
        self.assertEqual((ms[1].bid, ms[1].ask), (0.4, 0.45))


class FakeClient:
    def __init__(self):
        self.posts = []

    def get(self, path, **params):
        if path == bot.ENDPOINTS["prices"]:
            return {"data": [{"exchangeId": "11", "bestBid": 0.52, "bestAsk": 0.55}]}
        if path.endswith("/positions"):
            return {"data": [{"exchangeId": "11", "quantity": 0}]}
        if path == bot.ENDPOINTS["tournaments"]:
            return {"data": [{"id": "t1", "slug": "cup", "name": "Predictions Cup", "myBalance": 50_000}]}
        if path.endswith("/news"):
            raise bot.CupAPIError(404, "NOT_FOUND", "no news")
        raise AssertionError(path)

    def post(self, path, body):
        self.posts.append(body)
        return {"data": {"id": "o1"}}


class Cup(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.m = bot.Market("HOUSE", "Democrats win the House", exchange_id="11", manual=0.60)
        t = {"id": "t1", "slug": "cup", "myBalance": 50_000}
        self.broker = bot.CupBroker(self.client, [self.m], t, order_ttl=10, max_order_qty=1000)

    def test_dry_run_sends_nothing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            bot.run_once(self.broker, cfg(), bot.Book(), offline=True)
        self.assertEqual((self.m.bid, self.m.ask), (0.52, 0.55))
        self.assertEqual(self.client.posts, [])
        self.assertIn("DRY RUN", out.getvalue())

    def test_live_orders_are_chunked(self):
        with mock.patch.object(bot, "LIVE_ORDERS_VERIFIED", True), redirect_stdout(io.StringIO()):
            orders = bot.run_once(self.broker, cfg(), bot.Book(), offline=True)
        qty = orders[0].qty                          # 50k equity -> ~5050 shares
        self.assertGreater(qty, 1000)
        self.assertEqual(sum(p["quantity"] for p in self.client.posts), qty)
        self.assertTrue(all(p["quantity"] <= 1000 for p in self.client.posts))
        self.assertEqual(self.client.posts[0]["side"], "BUY")


if __name__ == "__main__":
    unittest.main()
