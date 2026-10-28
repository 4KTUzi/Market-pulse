"""Offline checks for fetch_data.py using fake API responses (no network needed).

Run:  python3 test_parsers.py
These confirm the parsing logic against the response shapes the APIs are
documented to return. They do not prove the live services are reachable.
"""
import json
import fetch_data as fd

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Fed holds rates steady, Powell flags inflation risks</title>
<link>https://example.com/a</link><pubDate>Wed, 28 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Bitcoin surges past record as ETF inflows jump</title>
<link>https://example.com/b</link><pubDate>Wed, 28 Oct 2026 07:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Oil tumbles as OPEC output rises</title>
<link href="https://example.com/c"/><updated>2026-10-28T06:00:00Z</updated></entry></feed>"""


def test_feeds():
    items = fd.parse_feed(RSS)
    assert len(items) == 2 and items[0][1] == "https://example.com/a"
    assert fd.parse_time(items[0][2]).year == 2026
    atom = fd.parse_feed(ATOM)
    assert atom[0][1] == "https://example.com/c"
    assert fd.parse_time(atom[0][2]).hour == 6


def test_tags():
    tags, watch = fd.tag_headline("Fed holds rates steady, Powell flags inflation risks", "markets")
    assert "Rates & central banks" in tags and "Inflation & jobs" in tags and watch
    tags, watch = fd.tag_headline("Apple opens new store in Paris", "markets")
    assert tags == [] and not watch
    tags, _ = fd.tag_headline("Some headline", "crypto")
    assert "Crypto" in tags


YAHOO = {"chart": {"result": [{
    "meta": {"regularMarketPrice": 105.0, "regularMarketTime": 1793000000, "currency": "USD"},
    "indicators": {"quote": [{"close": [98.0, None, 100.0, 105.0]}]}}]}}


def test_quote():
    fd.get_json = lambda url: YAHOO
    q = fd.fetch_quote(("TEST", "Test Co"))
    assert q["price"] == 105.0 and q["change"] == 5.0 and q["change_pct"] == 5.0
    assert q["spark"] == [98.0, 100.0, 105.0]


COINS = [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": 60000,
          "price_change_percentage_24h_in_currency": 2.5, "price_change_percentage_7d_in_currency": -1.2,
          "market_cap": 1, "total_volume": 1, "sparkline_in_7d": {"price": list(range(168))}}]
GLOBAL = {"data": {"total_market_cap": {"usd": 2e12}, "market_cap_change_percentage_24h_usd": 1.1,
                   "market_cap_percentage": {"btc": 52.34}}}
FNG = {"data": [{"value": "61", "value_classification": "Greed"}, {"value": "50", "value_classification": "Neutral"}]}


def test_crypto():
    def fake(url):
        if "coins/markets" in url:
            return COINS
        if "/global" in url:
            return GLOBAL
        return FNG
    fd.get_json = fake
    errors = []
    coins, glob, fng = fd.fetch_crypto(errors)
    assert not errors
    assert coins[0]["symbol"] == "BTC" and coins[0]["change_24h"] == 2.5 and len(coins[0]["spark"]) == 42
    assert glob["btc_dominance"] == 52.3
    assert fng["value"] == 61 and fng["label"] == "Greed" and fng["week_ago"] == 50


def test_demo_roundtrip():
    d = fd.demo_data()
    json.dumps(d)
    assert d["demo"] and len(d["indices"]) == 5 and d["snapshot"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
    print("all passed")
