#!/usr/bin/env python3
"""
Market Pulse - data fetcher.

Pulls stock/index quotes, crypto prices, a crypto fear & greed reading and
market news headlines, then writes data.json and data.js next to this file.
The dashboard (index.html) reads data.js.

Uses only the Python standard library. No API keys needed.
Edit the CONFIG section below to change what is tracked.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (compatible; MarketPulse/1.0)"
REFRESH_MINUTES = 30

# --------------------------------------------------------------------------
# CONFIG - change these lists to track different things
# --------------------------------------------------------------------------
INDICES = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "Nasdaq"),
    ("^DJI", "Dow Jones"),
    ("^RUT", "Russell 2000"),
    ("^VIX", "VIX (fear gauge)"),
]
MACRO = [
    ("^TNX", "US 10Y yield"),
    ("DX-Y.NYB", "US Dollar Index"),
    ("CL=F", "Crude oil"),
    ("GC=F", "Gold"),
]
WATCHLIST = [
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("NVDA", "Nvidia"),
    ("AMZN", "Amazon"),
    ("GOOGL", "Alphabet"),
    ("META", "Meta"),
    ("TSLA", "Tesla"),
]
CRYPTO_IDS = ["bitcoin", "ethereum", "solana", "ripple", "binancecoin", "dogecoin"]

# (source name, url, default topic)
FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "markets"),
    ("CNBC Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html", "markets"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "markets"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "macro"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto"),
    ("Cointelegraph", "https://cointelegraph.com/rss", "crypto"),
]
MAX_NEWS_AGE_HOURS = 72
MAX_PER_SOURCE = 10
MAX_NEWS_TOTAL = 45

# Economic calendar: free weekly feed (unofficial, ForexFactory-style data).
CALENDAR_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]
CALENDAR_COUNTRIES = {"USD", "EUR", "GBP", "JPY", "CNY"}  # add "AED", "CAD", ... if you like
CALENDAR_IMPACTS = {"High", "Medium"}                      # add "Low" for everything
CALENDAR_DAYS_AHEAD = 7
# US Fed rate decisions (announced 2:00 pm New York time on the last day of each
# meeting). Source: Federal Reserve 2026 FOMC calendar. Update once a year.
FOMC_DECISION_DATES = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# Keyword rules used to tag headlines. This is a simple heuristic, not analysis.
TAG_RULES = {
    "Rates & central banks": r"\b(fed|federal reserve|fomc|powell|rate cut|rate hike|interest rate|ecb|bank of england|boe|bank of japan|boj|central bank|treasury yield|yields?)\b",
    "Inflation & jobs": r"\b(inflation|cpi|ppi|pce|jobs report|payrolls?|unemployment|jobless|gdp|recession|consumer spending)\b",
    "Earnings": r"\b(earnings|quarterly results|revenue|guidance|profit|eps|beats|misses)\b",
    "Geopolitics & trade": r"\b(tariffs?|sanctions?|war|ceasefire|trade deal|trade war|china|russia|ukraine|iran|israel|gaza|taiwan|middle east|embargo)\b",
    "Energy": r"\b(oil|crude|opec|natural gas|brent|wti)\b",
    "Regulation & legal": r"\b(sec|regulat\w*|lawsuit|antitrust|ban|etf approval|court|ruling|probe|investigation|fine[sd]?)\b",
    "Crypto": r"\b(bitcoin|btc|ethereum|ether|crypto\w*|stablecoin|solana|xrp|ripple|etf|binance|coinbase|defi)\b",
}
STRONG_MOVE = r"\b(surge[sd]?|plunge[sd]?|crash\w*|soar\w*|tumble[sd]?|record|emergency|shock|spike[sd]?|slump\w*|rall(?:y|ies|ied)|sell-?off|panic|halt\w*|collapse[sd]?)\b"
MACRO_TAGS = {"Rates & central banks", "Inflation & jobs", "Geopolitics & trade", "Energy", "Regulation & legal"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def http_get(url, timeout=20, tries=2):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def get_json(url):
    return json.loads(http_get(url).decode("utf-8"))


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rnd(x, n=2):
    return None if x is None else round(float(x), n)


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\s+", " ", s)
    return s.replace("&amp;", "&").replace("&#8217;", "'").replace("&#8216;", "'").replace("&quot;", '"').strip()


# --------------------------------------------------------------------------
# stocks, indices, macro (Yahoo Finance public chart endpoint, unofficial)
# --------------------------------------------------------------------------
def fetch_quote(item):
    sym, name = item
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1mo&interval=1d" % urllib.parse.quote(sym)
    res = get_json(url)["chart"]["result"][0]
    meta = res["meta"]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    price = meta.get("regularMarketPrice", closes[-1])
    prev = closes[-2] if len(closes) >= 2 else meta.get("chartPreviousClose", price)
    change = price - prev
    pct = (change / prev * 100) if prev else 0.0
    ts = meta.get("regularMarketTime")
    return {
        "symbol": sym,
        "name": name,
        "price": rnd(price, 2),
        "change": rnd(change, 2),
        "change_pct": rnd(pct, 2),
        "currency": meta.get("currency", "USD"),
        "as_of": iso(datetime.fromtimestamp(ts, timezone.utc)) if ts else None,
        "spark": [rnd(c, 2) for c in closes[-30:]],
    }


def fetch_group(items, errors, label):
    out = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = [(it, ex.submit(fetch_quote, it)) for it in items]
        for it, f in futures:
            try:
                out.append(f.result())
            except Exception as e:  # noqa: BLE001
                errors.append("%s: %s failed (%s)" % (label, it[0], type(e).__name__))
    return out


# --------------------------------------------------------------------------
# crypto (CoinGecko free API) + fear & greed (alternative.me)
# --------------------------------------------------------------------------
def fetch_crypto(errors):
    coins = []
    try:
        url = (
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=%s"
            "&sparkline=true&price_change_percentage=24h,7d" % ",".join(CRYPTO_IDS)
        )
        for c in get_json(url):
            spark = (c.get("sparkline_in_7d") or {}).get("price") or []
            coins.append({
                "id": c["id"],
                "symbol": c["symbol"].upper(),
                "name": c["name"],
                "price": c.get("current_price"),
                "change_24h": rnd(c.get("price_change_percentage_24h_in_currency"), 2),
                "change_7d": rnd(c.get("price_change_percentage_7d_in_currency"), 2),
                "market_cap": c.get("market_cap"),
                "volume_24h": c.get("total_volume"),
                "spark": [rnd(p, 4) for p in spark[::4]],
            })
        order = {cid: i for i, cid in enumerate(CRYPTO_IDS)}
        coins.sort(key=lambda c: order.get(c["id"], 99))
    except Exception as e:  # noqa: BLE001
        errors.append("Crypto prices failed (%s)" % type(e).__name__)

    glob = None
    try:
        g = get_json("https://api.coingecko.com/api/v3/global")["data"]
        glob = {
            "total_market_cap": g["total_market_cap"]["usd"],
            "market_cap_change_24h": rnd(g.get("market_cap_change_percentage_24h_usd"), 2),
            "btc_dominance": rnd(g["market_cap_percentage"]["btc"], 1),
        }
    except Exception as e:  # noqa: BLE001
        errors.append("Crypto global stats failed (%s)" % type(e).__name__)

    fng = None
    try:
        rows = get_json("https://api.alternative.me/fng/?limit=8")["data"]
        fng = {
            "value": int(rows[0]["value"]),
            "label": rows[0]["value_classification"],
            "week_ago": int(rows[-1]["value"]) if len(rows) > 1 else None,
        }
    except Exception as e:  # noqa: BLE001
        errors.append("Fear & Greed failed (%s)" % type(e).__name__)
    return coins, glob, fng


# --------------------------------------------------------------------------
# news (public RSS / Atom feeds - headline, source, link and time only)
# --------------------------------------------------------------------------
ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(raw):
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):
        items.append((
            strip_html(it.findtext("title")),
            (it.findtext("link") or "").strip(),
            it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"),
        ))
    for en in root.iter(ATOM + "entry"):
        link = ""
        for l in en.findall(ATOM + "link"):
            link = l.get("href") or link
        items.append((
            strip_html(en.findtext(ATOM + "title")),
            link,
            en.findtext(ATOM + "updated") or en.findtext(ATOM + "published"),
        ))
    return items


def parse_time(s):
    if not s:
        return None
    s = s.strip()
    try:
        dt = parsedate_to_datetime(s)
    except Exception:  # noqa: BLE001
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def tag_headline(title, default_topic):
    tags = [t for t, pat in TAG_RULES.items() if re.search(pat, title, re.I)]
    if default_topic == "crypto" and "Crypto" not in tags:
        tags.append("Crypto")
    strong = bool(re.search(STRONG_MOVE, title, re.I))
    macro_hits = [t for t in tags if t in MACRO_TAGS]
    watch = (strong and bool(tags)) or len(macro_hits) >= 2
    return tags[:3], watch


def fetch_news(errors):
    cutoff = now_utc() - timedelta(hours=MAX_NEWS_AGE_HOURS)
    collected = []

    def one(feed):
        name, url, topic = feed
        raw = http_get(url)
        out = []
        for title, link, when in parse_feed(raw):
            dt = parse_time(when)
            if not title or not link or not dt or dt < cutoff:
                continue
            tags, watch = tag_headline(title, topic)
            out.append({
                "title": title,
                "url": link,
                "source": name.replace(" Finance", ""),
                "published": iso(dt),
                "topic": topic,
                "tags": tags,
                "watch": watch,
            })
        out.sort(key=lambda x: x["published"], reverse=True)
        return out[:MAX_PER_SOURCE]

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = [(f, ex.submit(one, f)) for f in FEEDS]
        for f, fut in futures:
            try:
                collected.extend(fut.result())
            except Exception as e:  # noqa: BLE001
                errors.append("News: %s unavailable (%s)" % (f[0], type(e).__name__))

    seen, unique = set(), []
    for n in sorted(collected, key=lambda x: x["published"], reverse=True):
        key = re.sub(r"[^a-z0-9]", "", n["title"].lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        unique.append(n)
    return unique[:MAX_NEWS_TOTAL]


# --------------------------------------------------------------------------
# economic calendar (weekly JSON feed + known Fed decision dates)
# --------------------------------------------------------------------------
def parse_calendar_item(raw):
    """Turn one feed entry into our format, or None if it should be skipped."""
    country = (raw.get("country") or "").upper()
    impact = (raw.get("impact") or "").strip().capitalize()
    title = strip_html(raw.get("title"))
    if not title or country not in CALENDAR_COUNTRIES or impact not in CALENDAR_IMPACTS:
        return None
    when = parse_time(raw.get("date"))
    if not when:
        return None
    return {
        "title": title,
        "country": country,
        "time": iso(when),
        "impact": impact,
        "forecast": (raw.get("forecast") or "").strip() or None,
        "previous": (raw.get("previous") or "").strip() or None,
    }


def fomc_events(now):
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    out = []
    for d in FOMC_DECISION_DATES:
        y, m, day = (int(x) for x in d.split("-"))
        when = datetime(y, m, day, 14, 0, tzinfo=ny)
        out.append({"title": "FOMC interest rate decision", "country": "USD", "time": iso(when),
                    "impact": "High", "forecast": None, "previous": None, "source": "Federal Reserve schedule"})
    return out


def fetch_calendar(errors):
    now = now_utc()
    start = now - timedelta(hours=14)        # keep earlier events from "today" on screen
    end = now + timedelta(days=CALENDAR_DAYS_AHEAD)
    events = []
    for url in CALENDAR_URLS:
        try:
            for raw in get_json(url):
                ev = parse_calendar_item(raw)
                if ev:
                    events.append(ev)
        except Exception as e:  # noqa: BLE001
            errors.append("Calendar feed unavailable (%s)" % type(e).__name__)
            break
    try:
        have_fomc_days = {e["time"][:10] for e in events if re.search(r"fomc|federal funds rate", e["title"], re.I)}
        for ev in fomc_events(now):
            if ev["time"][:10] not in have_fomc_days:
                events.append(ev)
    except Exception as e:  # noqa: BLE001
        errors.append("Fed dates unavailable (%s)" % type(e).__name__)

    seen, out = set(), []
    for ev in sorted(events, key=lambda e: (e["time"], e["title"])):
        key = (ev["time"], ev["title"], ev["country"])
        if key in seen:
            continue
        seen.add(key)
        t = parse_time(ev["time"])
        if start <= t <= end:
            out.append(ev)
    return out[:80]


# --------------------------------------------------------------------------
# plain-English snapshot built from the numbers above
# --------------------------------------------------------------------------
def build_snapshot(indices, watch, coins, fng, news, calendar=None):
    parts = []
    by = {q["symbol"]: q for q in indices}
    idx = [by[s] for s in ("^GSPC", "^IXIC", "^DJI") if s in by]
    if idx:
        parts.append("US stocks: " + ", ".join("%s %+.2f%%" % (q["name"], q["change_pct"]) for q in idx) + " at the last close or live price.")
    if "^VIX" in by:
        v = by["^VIX"]["price"]
        mood = "elevated" if v >= 25 else "moderate" if v >= 18 else "calm"
        parts.append("VIX is %.1f (%s)." % (v, mood))
    if watch:
        top = max(watch, key=lambda q: abs(q["change_pct"]))
        parts.append("Biggest watchlist move: %s %+.2f%%." % (top["name"], top["change_pct"]))
    btc = next((c for c in coins if c["id"] == "bitcoin"), None)
    eth = next((c for c in coins if c["id"] == "ethereum"), None)
    if btc:
        s = "Bitcoin %+.1f%% over 24h" % (btc["change_24h"] or 0)
        if eth:
            s += ", Ethereum %+.1f%%" % (eth["change_24h"] or 0)
        parts.append(s + ".")
    if fng:
        parts.append("Crypto Fear & Greed: %d (%s)." % (fng["value"], fng["label"]))
    flagged = sum(1 for n in news if n["watch"])
    if news:
        parts.append("%d of %d recent headlines are flagged as possible market movers." % (flagged, len(news)))
    if calendar:
        # "Today" here is the UTC day; the page itself groups events by the viewer's local day.
        today = now_utc().strftime("%Y-%m-%d")
        high = [e for e in calendar if e["time"][:10] == today and e["impact"] == "High"]
        if high:
            parts.append("High-impact events today (UTC): " + "; ".join(e["title"] for e in high[:3]) + ".")
    return " ".join(parts)


# --------------------------------------------------------------------------
# demo mode: synthetic placeholder numbers so the page can be previewed
# without network access. Everything is flagged with "demo": true.
# --------------------------------------------------------------------------
def demo_data():
    import random
    rng = random.Random(7)
    now = now_utc()

    def walk(start, n, vol):
        v, out = start, []
        for _ in range(n):
            v *= 1 + rng.uniform(-vol, vol)
            out.append(round(v, 2))
        return out

    def quote(sym, name, base, vol=0.01):
        sp = walk(base, 30, vol)
        ch = sp[-1] - sp[-2]
        return {"symbol": sym, "name": name, "price": sp[-1], "change": round(ch, 2),
                "change_pct": round(ch / sp[-2] * 100, 2), "currency": "USD",
                "as_of": iso(now), "spark": sp}

    indices = [quote("^GSPC", "S&P 500", 5000), quote("^IXIC", "Nasdaq", 16000),
               quote("^DJI", "Dow Jones", 38000), quote("^RUT", "Russell 2000", 2000),
               quote("^VIX", "VIX (fear gauge)", 18, 0.05)]
    macro = [quote("^TNX", "US 10Y yield", 4.2, 0.02), quote("DX-Y.NYB", "US Dollar Index", 104, 0.004),
             quote("CL=F", "Crude oil", 80, 0.02), quote("GC=F", "Gold", 2300, 0.008)]
    watch = [quote(s, n, b, 0.02) for s, n, b in [
        ("AAPL", "Apple", 190), ("MSFT", "Microsoft", 420), ("NVDA", "Nvidia", 900),
        ("AMZN", "Amazon", 180), ("GOOGL", "Alphabet", 170), ("META", "Meta", 480), ("TSLA", "Tesla", 200)]]
    coins = []
    for cid, sym, name, base in [("bitcoin", "BTC", "Bitcoin", 60000), ("ethereum", "ETH", "Ethereum", 3000),
                                 ("solana", "SOL", "Solana", 150), ("ripple", "XRP", "XRP", 0.55),
                                 ("binancecoin", "BNB", "BNB", 580), ("dogecoin", "DOGE", "Dogecoin", 0.15)]:
        sp = walk(base, 42, 0.012)
        coins.append({"id": cid, "symbol": sym, "name": name, "price": sp[-1],
                      "change_24h": round(rng.uniform(-4, 4), 2), "change_7d": round(rng.uniform(-9, 9), 2),
                      "market_cap": round(sp[-1] * 1e7), "volume_24h": round(sp[-1] * 1e6), "spark": sp})
    titles = [
        ("Fed officials signal patience on rate cuts as inflation data looms", "Federal Reserve", "macro"),
        ("Oil jumps after OPEC+ hints at deeper output cuts", "CNBC", "markets"),
        ("Tech earnings beat estimates, Nasdaq rallies", "MarketWatch", "markets"),
        ("Bitcoin ETF inflows surge as SEC reviews new filings", "CoinDesk", "crypto"),
        ("Tariff talks with China stall, stocks slip", "CNBC", "markets"),
        ("Ethereum developers set date for next network upgrade", "Cointelegraph", "crypto"),
        ("Retailers warn of weaker consumer spending ahead of holidays", "MarketWatch", "markets"),
    ]
    news = []
    for i, (t, src, topic) in enumerate(titles):
        tags, watch_flag = tag_headline(t, topic)
        news.append({"title": "[Sample] " + t, "url": "#", "source": src,
                     "published": iso(now - timedelta(hours=2 * i + 1)), "topic": topic,
                     "tags": tags, "watch": watch_flag})
    cal_rows = [
        (-3, "Sample: ISM Services PMI", "USD", "Medium", "52.0", "51.5"),
        (2, "Sample: Crude Oil Inventories", "USD", "Medium", "-1.2M", "0.8M"),
        (5, "Sample: FOMC interest rate decision", "USD", "High", "4.50%", "4.50%"),
        (26, "Sample: ECB President speaks", "EUR", "Medium", None, None),
        (28, "Sample: Core PCE Price Index m/m", "USD", "High", "0.2%", "0.3%"),
        (50, "Sample: Non-Farm Payrolls", "USD", "High", "150K", "142K"),
        (52, "Sample: Unemployment Rate", "USD", "High", "4.1%", "4.1%"),
        (74, "Sample: GDP q/q", "GBP", "Medium", "0.3%", "0.2%"),
    ]
    calendar = [{"title": t, "country": c, "time": iso(now + timedelta(hours=h)), "impact": i,
                 "forecast": f, "previous": p} for h, t, c, i, f, p in cal_rows]
    data = {
        "demo": True,
        "generated_at": iso(now), "next_update_at": iso(now + timedelta(minutes=REFRESH_MINUTES)),
        "refresh_minutes": REFRESH_MINUTES,
        "calendar": calendar,
        "snapshot": build_snapshot(indices, watch, coins, {"value": 55, "label": "Neutral"}, news, calendar),
        "indices": indices, "macro": macro, "watchlist": watch, "crypto": coins,
        "crypto_global": {"total_market_cap": 2.3e12, "market_cap_change_24h": 0.8, "btc_dominance": 52.1},
        "fear_greed": {"value": 55, "label": "Neutral", "week_ago": 48},
        "news": news, "errors": [], "stale_sections": [],
    }
    return data


def write_data(data):
    (ROOT / "data.json").write_text(json.dumps(data, indent=2))
    (ROOT / "data.js").write_text("window.MARKET_DATA = " + json.dumps(data) + ";\n")


def main():
    if "--demo" in sys.argv:
        write_data(demo_data())
        print("Wrote DEMO data (synthetic numbers, flagged on the page).")
        return 0
    errors = []
    prev = {}
    pj = ROOT / "data.json"
    if pj.exists():
        try:
            prev = json.loads(pj.read_text())
        except Exception:  # noqa: BLE001
            prev = {}

    indices = fetch_group(INDICES, errors, "Indices")
    macro = fetch_group(MACRO, errors, "Macro")
    watch = fetch_group(WATCHLIST, errors, "Stocks")
    coins, glob, fng = fetch_crypto(errors)
    news = fetch_news(errors)
    calendar = fetch_calendar(errors)

    stale = []
    # Keep the last good data for any section that came back empty.
    for key, val in (("indices", indices), ("macro", macro), ("watchlist", watch), ("crypto", coins), ("news", news)):
        if not val and prev.get(key):
            stale.append(key)
    indices = indices or prev.get("indices", [])
    macro = macro or prev.get("macro", [])
    watch = watch or prev.get("watchlist", [])
    coins = coins or prev.get("crypto", [])
    news = news or prev.get("news", [])
    glob = glob or prev.get("crypto_global")
    fng = fng or prev.get("fear_greed")

    now = now_utc()
    data = {
        "generated_at": iso(now),
        "next_update_at": iso(now + timedelta(minutes=REFRESH_MINUTES)),
        "refresh_minutes": REFRESH_MINUTES,
        "snapshot": build_snapshot(indices, watch, coins, fng, news, calendar),
        "calendar": calendar,
        "indices": indices,
        "macro": macro,
        "watchlist": watch,
        "crypto": coins,
        "crypto_global": glob,
        "fear_greed": fng,
        "news": news,
        "errors": errors,
        "stale_sections": stale,
    }
    write_data(data)

    print("Updated %s | indices=%d macro=%d stocks=%d crypto=%d news=%d calendar=%d" % (
        data["generated_at"], len(indices), len(macro), len(watch), len(coins), len(news), len(calendar)))
    for e in errors:
        print("  warning:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
