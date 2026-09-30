"""
Investing Opportunities - local app server.
Run:  python server.py     (then open http://localhost:8765)

Standard library only - nothing to install.

Optional environment variables (for hosting online, e.g. on Render):
  PORT           port to listen on (default 8765); setting it also listens on all interfaces
  APP_PASSWORD   password for the "My money" tab (any username works)
  SUPABASE_URL   + SUPABASE_KEY: store "My money" holdings in Supabase instead of data/my_portfolio.json
  NO_BROWSER=1   don't open a browser on start (never opens one when PORT is set)
"""
import base64
import hmac
import html
import http.cookiejar
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import models
from universe import ALIASES, BUCKET_LABEL, BY_TICKER, HISA_RATE, KIND_LABEL, RESEARCH, UNIVERSE

PORT = int(os.environ.get("PORT", 8765))
HOST = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
os.makedirs(CACHE, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


# --------------------------------------------------------------------------- http + cache
def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def cached(key, ttl, fn):
    path = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        val = fn()
    except Exception:
        if os.path.exists(path):  # stale is better than nothing
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        raise
    with open(path, "w", encoding="utf-8") as f:
        json.dump(val, f)
    return val


# --------------------------------------------------------------------------- prices
def yahoo_chart(symbol, rng="10y", interval="1mo"):
    def go():
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
               f"?range={rng}&interval={interval}&events=div%2Csplit&includeAdjustedClose=true")
        r = json.loads(fetch(url))["chart"]["result"][0]
        ts = r.get("timestamp") or []
        close = r["indicators"]["quote"][0].get("close") or []
        adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or close
        pts = [(t, c, a) for t, c, a in zip(ts, close, adj) if c is not None and a is not None]
        m = r["meta"]
        return {
            "symbol": symbol,
            "name": m.get("longName") or m.get("shortName") or symbol,
            "currency": m.get("currency"),
            "type": m.get("instrumentType"),
            "price": m.get("regularMarketPrice"),
            "t": [p[0] for p in pts], "close": [p[1] for p in pts], "adj": [p[2] for p in pts],
        }
    ttl = 6 * 3600 if interval == "1mo" else 20 * 60
    return cached(f"chart_{symbol}_{rng}_{interval}", ttl, go)


def yahoo_search(q):
    def go():
        url = ("https://query1.finance.yahoo.com/v1/finance/search?quotesCount=6&newsCount=0&q="
               + urllib.parse.quote(q))
        return json.loads(fetch(url)).get("quotes", [])
    return cached(f"search_{q.lower()}", 7 * 86400, go)


# Yahoo's company data needs a session cookie and a "crumb" token that goes with it
_YOPEN = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
_CRUMB = {"v": None, "t": 0.0}
_CRUMB_LOCK = threading.Lock()


def _yget(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"})
    with _YOPEN.open(req, timeout=20) as r:
        return r.read()


def yahoo_crumb(force=False):
    with _CRUMB_LOCK:
        if force or not _CRUMB["v"] or time.time() - _CRUMB["t"] > 6 * 3600:
            try:
                _yget("https://fc.yahoo.com")   # answers 404 but sets the session cookie
            except Exception:
                pass
            _CRUMB.update(v=_yget("https://query1.finance.yahoo.com/v1/test/getcrumb").decode(), t=time.time())
        return _CRUMB["v"]


def yahoo_fundamentals(symbol):
    """Valuation, profitability, growth, debt and analyst views for a company; size and yield for a fund."""
    def go():
        for attempt in (0, 1):
            crumb = yahoo_crumb(force=attempt == 1)
            url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(symbol)}"
                   f"?modules=summaryDetail,defaultKeyStatistics,financialData,price&crumb={urllib.parse.quote(crumb)}")
            try:
                res = json.loads(_yget(url))["quoteSummary"]["result"][0]
                break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and attempt == 0:
                    continue
                if e.code == 404:
                    return {}
                raise

        def raw(mod, key):
            v = (res.get(mod) or {}).get(key)
            return v.get("raw") if isinstance(v, dict) else None
        price = raw("financialData", "currentPrice") or raw("price", "regularMarketPrice")
        target = raw("financialData", "targetMeanPrice")
        return {
            "pe": raw("summaryDetail", "trailingPE"),
            "forward_pe": raw("summaryDetail", "forwardPE") or raw("defaultKeyStatistics", "forwardPE"),
            "pb": raw("defaultKeyStatistics", "priceToBook"),
            "div_yield": raw("summaryDetail", "dividendYield") or raw("summaryDetail", "yield"),
            "roe": raw("financialData", "returnOnEquity"),
            "margin": raw("financialData", "profitMargins"),
            "rev_growth": raw("financialData", "revenueGrowth"),
            "earn_growth": raw("financialData", "earningsGrowth"),
            "debt_equity": raw("financialData", "debtToEquity"),
            "target": target,
            "target_upside": (target / price - 1) if target and price else None,
            "rec_mean": raw("financialData", "recommendationMean"),
            "rec_key": (res.get("financialData") or {}).get("recommendationKey"),
            "analysts": raw("financialData", "numberOfAnalystOpinions"),
            "market_cap": raw("price", "marketCap"),
            "total_assets": raw("summaryDetail", "totalAssets") or raw("defaultKeyStatistics", "totalAssets"),
            "beta": raw("summaryDetail", "beta") or raw("defaultKeyStatistics", "beta3Year"),
        }
    return cached(f"fund_{symbol}", 24 * 3600, go)


def coingecko_data():
    """Market cap, rank and distance from the all-time high for the coins in the list."""
    ids = [u["coingecko"] for u in UNIVERSE if u.get("coingecko")]
    def go():
        url = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=aud&ids=" + ",".join(ids))
        return {c["id"]: {"mcap_rank": c.get("market_cap_rank"), "market_cap": c.get("market_cap"),
                          "ath_change": (c.get("ath_change_percentage") or 0) / 100,
                          "volume": c.get("total_volume")} for c in json.loads(fetch(url))}
    try:
        return cached("coingecko_markets", 6 * 3600, go)
    except Exception:
        return {}


def fear_greed():
    """The crypto Fear & Greed index (0 = extreme fear, 100 = extreme greed)."""
    def go():
        d = json.loads(fetch("https://api.alternative.me/fng/?limit=1"))["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    try:
        return cached("fear_greed", 6 * 3600, go)
    except Exception:
        return None


def metrics(monthly):
    """Simple performance stats from a monthly adjusted-close series (includes dividends)."""
    a = monthly["adj"]
    out = {"years": round(len(a) / 12, 1)}
    if len(a) < 3:
        return out

    def cagr(n_months):
        if len(a) <= n_months:
            return None
        return (a[-1] / a[-1 - n_months]) ** (12 / n_months) - 1

    out["r1y"] = cagr(12)
    out["cagr3"] = cagr(36)
    out["cagr5"] = cagr(60)
    out["cagr10"] = cagr(119)
    out["cagr_all"] = (a[-1] / a[0]) ** (12 / (len(a) - 1)) - 1
    peak, mdd = a[0], 0.0
    for v in a:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    out["mdd"] = mdd
    wins = [a[i] > a[i - 12] for i in range(12, len(a))]
    out["up_years_pct"] = sum(wins) / len(wins) if wins else None
    return out


# --------------------------------------------------------------------------- sentiment
# General words plus finance words in the spirit of the Loughran-McDonald finance sentiment lists
POS = {"buy", "bought", "buying", "hold", "holding", "solid", "great", "good", "love", "recommend", "low", "cheap",
       "diversified", "diversification", "compounding", "happy", "winner", "outperform", "outperformed", "strong",
       "boring", "safe", "simple", "easy", "bullish", "bull", "growth", "gains", "gain", "rally", "beat", "beats",
       "upgrade", "upgraded", "surge", "surges", "soar", "soars", "jump", "jumps", "rise", "rises", "rising", "best",
       "profit", "profitable", "record", "improve", "improved", "exceed", "exceeded", "undervalued", "accumulate",
       "moon", "breakout", "higher", "recovery", "rebound"}
NEG = {"sell", "sold", "selling", "avoid", "overvalued", "expensive", "crash", "crashed", "bubble", "scam", "risky",
       "loss", "losses", "lost", "regret", "dump", "dumped", "bearish", "bear", "worst", "bad", "terrible", "overlap",
       "concentrated", "concentration", "down", "fall", "falls", "falling", "plunge", "plunges", "slump", "tumble",
       "drop", "drops", "downgrade", "downgraded", "warn", "warning", "warns", "fear", "worried", "nervous",
       "underperform", "underperformed", "hype", "fomo", "gamble", "gambling", "rug", "weak", "weaker", "decline",
       "declines", "lawsuit", "fraud", "investigation", "impairment", "bankrupt", "bankruptcy", "default", "writedown",
       "miss", "missed", "cut", "cuts", "layoffs", "lower", "sinks", "slides"}
POS_PHRASES = ["set and forget", "set-and-forget", "low fee", "low fees", "long term", "long-term", "no brainer",
               "record high", "top pick", "all time high"]
NEG_PHRASES = ["high fee", "high fees", "rug pull", "sell off", "sell-off", "profit warning"]
NEGATORS = {"not", "no", "never", "don't", "dont", "isn't", "wasn't", "won't", "without"}
THEMES = {
    "set-and-forget": ["set and forget", "set-and-forget", "chill"],
    "low fees": ["low fee", "cheap", r"mer\b", r"fees?\b", "expense ratio"],
    "diversification": ["diversif"],
    "dividends/franking": ["dividend", "franking", "franked"],
    "overvalued": ["overvalued", "expensive", "p/e", "valuation"],
    "tech concentration": ["tech heavy", "concentrat", "magnificent", "nvidia"],
    "crash/volatility fears": ["crash", "volatil", "bubble", "correction"],
    "hype/speculation": ["moon", "hype", "fomo", "yolo", "gamble", "tendies"],
    "overlap": ["overlap"],
    "interest rates": ["rate hike", "rate cut", "interest rate", "rba"],
}

AU_SUBS = "fiaustralia+AusFinance+ASX_Bets+ausstocks+ASX"
CRYPTO_SUBS = "CryptoCurrency+Bitcoin+ethereum+solana+XRP"
REDDIT_FEEDS = [
    ("r/fiaustralia (top this month)", "https://www.reddit.com/r/fiaustralia/top/.rss?t=month&limit=100", "au"),
    ("r/fiaustralia (newest)", "https://www.reddit.com/r/fiaustralia/new/.rss?limit=100", "au"),
    ("r/AusFinance (investing, top month)",
     "https://www.reddit.com/r/AusFinance/search.rss?q=ETF+OR+shares+OR+invest&restrict_sr=1&sort=top&t=month", "au"),
    ("r/ASX_Bets (top this month)", "https://www.reddit.com/r/ASX_Bets/top/.rss?t=month&limit=100", "au"),
    ("r/ausstocks (top this month)", "https://www.reddit.com/r/ausstocks/top/.rss?t=month&limit=100", "au"),
    ("r/ASX (top this month)", "https://www.reddit.com/r/ASX/top/.rss?t=month&limit=100", "au"),
    ("r/CryptoCurrency (top this week)", "https://www.reddit.com/r/CryptoCurrency/top/.rss?t=week&limit=100", "crypto"),
    ("r/Bitcoin (top this week)", "https://www.reddit.com/r/Bitcoin/top/.rss?t=week&limit=100", "crypto"),
    ("r/ethereum (top this month)", "https://www.reddit.com/r/ethereum/top/.rss?t=month&limit=100", "crypto"),
]
# where people talk that the app can't read, and why
UNREADABLE = [
    ("X / Twitter", "needs a paid API or a login; the free mirrors are shut down or blocked."),
    ("Facebook groups", "need a login and are private."),
    ("HotCopper", "blocks automated readers (Cloudflare)."),
]
CONTEXT_RE = re.compile(r"\b(asx|etf|etfs|shares?|stocks?|invest\w*|dividends?|portfolio|market|price|buy|buying|"
                        r"sell|selling|bull\w*|bear\w*|hodl|crypto|super|brokerage)\b|\$", re.I)
TICKER_STOP = {"ASX", "ETF", "ETFS", "USD", "AUD", "CEO", "IPO", "EPS", "YTD", "ATH", "FOMO", "HODL", "NYSE", "SPY",
               "USA", "GDP", "RBA", "CPI", "NFT", "DCA", "FIRE", "LOL", "IMO", "TLDR", "EDIT", "HISA", "CGT", "ATO",
               "SMSF", "AFSL", "ASIC", "GST", "ETH", "BTC", "SOL", "XRP"}

ASX_WORD = re.compile(r"(?<![$\w])ASX(?![\w])")
TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[a-z][a-z'\-/]*")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", html.unescape(s or "")))).strip()


def text_sentiment(text):
    t = text.lower()
    words = WORD_RE.findall(t)
    pos = neg = 0
    for i, w in enumerate(words):
        negated = i > 0 and words[i - 1] in NEGATORS or i > 1 and words[i - 2] in NEGATORS
        if w in POS:
            neg, pos = (neg + 1, pos) if negated else (neg, pos + 1)
        elif w in NEG:
            neg, pos = (neg, pos + 1) if negated else (neg + 1, pos)
    pos += sum(t.count(p) for p in POS_PHRASES)
    neg += sum(t.count(p) for p in NEG_PHRASES)
    return pos, neg


def parse_atom(raw, source):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(raw).findall("a:entry", ns):
        link = e.find("a:link", ns)
        out.append({
            "source": source, "platform": "Reddit",
            "title": clean(e.findtext("a:title", "", ns)),
            "body": clean(e.findtext("a:content", "", ns))[:3000],
            "url": link.get("href") if link is not None else "",
            "date": e.findtext("a:updated", "", ns)[:10],
        })
    return out


def parse_rss(raw, source):
    out = []
    for it in ET.fromstring(raw).iter("item"):
        out.append({
            "source": source, "platform": "News",
            "title": clean(it.findtext("title", "")),
            "body": clean(it.findtext("description", ""))[:600],
            "url": it.findtext("link", ""),
            "date": it.findtext("pubDate", "")[:16],
        })
    return out


def bluesky_search(q, days=90):
    """Recent English posts on Bluesky (where much of finance Twitter moved) matching q."""
    url = ("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?limit=60&sort=latest&lang=en&q="
           + urllib.parse.quote(q))
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    out = []
    for p in json.loads(fetch(url)).get("posts", []):
        rec = p.get("record") or {}
        date = (rec.get("createdAt") or "")[:10]
        if date < cutoff:
            continue
        text = clean(rec.get("text", ""))
        handle = (p.get("author") or {}).get("handle", "")
        out.append({"source": "Bluesky", "platform": "Bluesky", "title": text[:180], "body": text,
                    "url": f"https://bsky.app/profile/{handle}/post/{p.get('uri', '').rsplit('/', 1)[-1]}", "date": date})
    return out


def stocktwits_stream(symbol):
    """The latest StockTwits messages for a symbol. Many carry the poster's own Bullish / Bearish label."""
    j = json.loads(fetch(f"https://api.stocktwits.com/api/2/streams/symbol/{urllib.parse.quote(symbol)}.json"))
    out = []
    for m in j.get("messages", []):
        label = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        user = (m.get("user") or {}).get("username", "")
        out.append({"source": "StockTwits", "platform": "StockTwits", "title": clean(m.get("body", ""))[:180],
                    "body": clean(m.get("body", "")), "label": label, "date": (m.get("created_at") or "")[:10],
                    "url": f"https://stocktwits.com/{user}/message/{m.get('id')}"})
    return out


def mention_patterns(u):
    t = u["ticker"]
    pats = []
    if not (u.get("kind") == "crypto" and t == "SOL"):     # SOL is also Soul Patts on the ASX
        pats.append(re.compile(r"(?<![A-Za-z0-9])\$?" + re.escape(t) + r"(?![A-Za-z0-9])"))  # case-sensitive
    for a in ALIASES.get(t, []):
        pats.append(re.compile(r"\b" + re.escape(a) + r"\b", re.I))
    return pats


def mentions(text, pats):
    return any(p.search(text) for p in pats)


def bluesky_query(u):
    if u["kind"] == "etf":
        return f"{u['ticker']} ETF"
    if u["kind"] == "crypto":
        return u["name"]
    return re.sub(r"\s+(Group|Limited|Global|Energy)$", "", u["name"])


SCAN = {"running": False, "progress": "", "done": 0, "total": 0}
SENT_PATH = os.path.join(DATA, "sentiment.json")


def load_sentiment():
    if os.path.exists(SENT_PATH):
        with open(SENT_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


REDDIT_LIMITED = {"n": 0}   # rate-limited requests in a row during this scan


def reddit_get(url):
    """Reddit rate-limits hard. Retry once; after 3 refusals in a row, skip Reddit for the rest of the scan
    instead of making the scan take half an hour."""
    if REDDIT_LIMITED["n"] >= 3:
        raise RuntimeError("skipped: Reddit is rate-limiting, try again later")
    for attempt in range(2):
        try:
            got = fetch(url)
            REDDIT_LIMITED["n"] = 0
            return got
        except urllib.error.HTTPError as e:
            if e.code == 429:
                REDDIT_LIMITED["n"] += 1
                if attempt == 0 and REDDIT_LIMITED["n"] < 3:
                    time.sleep(20)
                    continue
            raise


def carry_over_reddit(results, prev):
    """Reddit couldn't be read at all this time: keep each investment's Reddit numbers from the previous scan."""
    for t, s in results.items():
        old = (prev.get("tickers") or {}).get(t)
        if not old:
            continue
        r = (old.get("by_source") or {}).get("Reddit") or {"n": old.get("reddit_mentions", 0), "pos": old.get("reddit_pos", 0),
                                                           "neg": old.get("reddit_neg", 0), "opinions": 0}
        s["by_source"]["Reddit"] = r
        s["reddit_mentions"], s["reddit_pos"], s["reddit_neg"] = r["n"], r["pos"], r["neg"]
        s["samples"] = [p for p in old.get("samples", []) if p.get("source") not in ("Bluesky", "StockTwits")][:5] + s["samples"]
        s["themes"] = s["themes"] or old.get("themes", [])


def run_scan():
    """Scan Reddit, Bluesky, StockTwits and Google News, attribute posts to investments, score the mood,
    and note tickers people mention that the app doesn't track. About 3-4 minutes."""
    if SCAN["running"]:
        return
    SCAN.update(running=True, done=0, progress="Starting...")
    REDDIT_LIMITED["n"] = 0
    try:
        sources, au_posts, crypto_posts = [], [], []
        tickers = list(UNIVERSE)
        au_terms = [u["ticker"] for u in tickers if u["kind"] != "crypto"]
        au_groups = [au_terms[i:i + 6] for i in range(0, len(au_terms), 6)]
        crypto_terms = [u["name"] for u in tickers if u["kind"] == "crypto"]
        st_list = [u for u in tickers if u.get("stocktwits")]
        SCAN["total"] = len(REDDIT_FEEDS) + len(au_groups) + 1 + len(tickers) + 1 + len(st_list) + len(tickers)

        # ---- Reddit: the feeds, then searches for the tickers (Reddit rate-limits hard, so few requests)
        for label, url, group in REDDIT_FEEDS:
            SCAN["progress"] = f"Reading {label}"
            try:
                got = parse_atom(reddit_get(url), label)
                (au_posts if group == "au" else crypto_posts).extend(got)
                sources.append({"name": label, "platform": "Reddit", "ok": True, "items": len(got)})
            except Exception as e:
                sources.append({"name": label, "platform": "Reddit", "ok": False, "error": str(e)[:80]})
            SCAN["done"] += 1
            time.sleep(5)
        searched_au, searched_crypto, ok, fail = [], [], 0, 0
        for subs, terms, bucket in [(AU_SUBS, g, searched_au) for g in au_groups] + [(CRYPTO_SUBS, crypto_terms, searched_crypto)]:
            SCAN["progress"] = "Searching Reddit for " + ", ".join(terms)
            url = (f"https://www.reddit.com/r/{subs}/search.rss?q={urllib.parse.quote(' OR '.join(terms))}"
                   f"&restrict_sr=1&sort=relevance&t=year&limit=100")
            try:
                bucket.extend(parse_atom(reddit_get(url), "Reddit search"))
                ok += 1
            except Exception:
                fail += 1
            SCAN["done"] += 1
            time.sleep(5)
        sources.append({"name": "Reddit ticker searches (AU + crypto subs, past year)", "platform": "Reddit", "ok": ok > 0,
                        "items": len(searched_au) + len(searched_crypto),
                        "error": f"{fail} searches rate-limited" if fail else None})

        # ---- Bluesky: one search per investment, kept only when it's about investing
        SCAN["progress"] = "Searching Bluesky"
        bsky, bsky_ok = {}, 0
        def get_bsky(u):
            try:
                pats = mention_patterns(u)
                return u["ticker"], [p for p in bluesky_search(bluesky_query(u))
                                     if mentions(p["body"], pats) and CONTEXT_RE.search(p["body"])]
            except Exception:
                return u["ticker"], None
        with ThreadPoolExecutor(4) as ex:
            for t, items in ex.map(get_bsky, tickers):
                bsky[t] = items or []
                bsky_ok += items is not None
                SCAN["done"] += 1
        try:
            # "$ASX" is also a US-listed chip maker, and ticker-spam bots list dozens of cashtags: skip both
            bsky_asx = [p for p in bluesky_search("ASX") if CONTEXT_RE.search(p["body"]) and ASX_WORD.search(p["body"])
                        and len(re.findall(r"\$[A-Z]{2,5}", p["body"])) <= 4]
        except Exception:
            bsky_asx = []
        SCAN["done"] += 1
        sources.append({"name": "Bluesky (posts about each investment + #ASX, last 90 days)", "platform": "Bluesky",
                        "ok": bsky_ok > 0, "items": sum(len(v) for v in bsky.values()) + len(bsky_asx)})

        # ---- StockTwits: crypto and US-listed shares (it doesn't cover the ASX)
        st = {}
        for u in st_list:
            SCAN["progress"] = f"Reading StockTwits {u['stocktwits']}"
            try:
                st[u["ticker"]] = stocktwits_stream(u["stocktwits"])
            except Exception:
                st[u["ticker"]] = []
            SCAN["done"] += 1
            time.sleep(1)
        sources.append({"name": "StockTwits (" + ", ".join(u["stocktwits"] for u in st_list) + ")", "platform": "StockTwits",
                        "ok": any(st.values()), "items": sum(len(v) for v in st.values())})

        # ---- Google News
        news = {}
        def get_news(u):
            if u["kind"] == "etf":
                q = f'{u["ticker"]} ETF'
            elif u["kind"] == "crypto":
                q = u["name"] + " price"
            else:
                q = f'"{u["ticker"]}" ASX'
            url = ("https://news.google.com/rss/search?hl=en-AU&gl=AU&ceid=AU:en&q="
                   + urllib.parse.quote(q + " when:60d"))
            try:
                return u["ticker"], parse_rss(fetch(url), "Google News")[:40]
            except Exception:
                return u["ticker"], []
        SCAN["progress"] = "Reading news headlines"
        with ThreadPoolExecutor(6) as ex:
            for t, items in ex.map(get_news, tickers):
                news[t] = items
                SCAN["done"] += 1
        sources.append({"name": "Google News (AU, last 60 days)", "platform": "News", "ok": True,
                        "items": sum(len(v) for v in news.values())})

        # ---- attribute + score
        results = {}
        for u in tickers:
            t, pats = u["ticker"], mention_patterns(u)
            pool = crypto_posts + searched_crypto + au_posts if u["kind"] == "crypto" else au_posts + searched_au
            seen, items = set(), []
            for p in pool:
                if p["url"] in seen or not mentions(p["title"] + " " + p["body"], pats):
                    continue
                seen.add(p["url"])
                items.append(p)
            news_items = [n for n in news.get(t, []) if n["url"] not in seen]
            results[t] = summarise(items, news_items, bsky.get(t, []), st.get(t, []))

        prev = load_sentiment() or {}
        reddit_read = any(s["ok"] for s in sources if s.get("platform") == "Reddit")
        if not reddit_read and prev.get("tickers"):
            carry_over_reddit(results, prev)
            sources.append({"name": f"Reddit mentions carried over from the scan on {prev.get('fetched_at')}", "platform": "Reddit",
                            "ok": True, "items": sum(r["reddit_mentions"] for r in results.values())})
            au_posts = [dict(p, body="") for p in prev.get("recent_posts", [])]

        # tickers people talk about that the app doesn't track (Australian posts only: $SOL there is Soul Patts)
        other, where = {}, {}
        for p in au_posts + searched_au + bsky_asx:
            txt = p["title"] + " " + p["body"]
            for m in set(re.findall(r"(?:ASX:\s?|\$)([A-Z]{3,4})\b", txt)):
                if m not in BY_TICKER and m not in TICKER_STOP:
                    other[m] = other.get(m, 0) + 1
                    where.setdefault(m, []).append({k: p[k] for k in ("source", "title", "url", "date")})
        if not reddit_read:
            for t, n in prev.get("trending_other", []):
                other[t] = other.get(t, 0) + n
                where.setdefault(t, []).extend(prev.get("trending_samples", {}).get(t, []))
        trending = sorted(other.items(), key=lambda x: -x[1])[:20]

        everything = au_posts + crypto_posts
        data = {"fetched_at": time.strftime("%Y-%m-%d %H:%M"), "sources": sources,
                "unreadable": UNREADABLE,
                "posts_scanned": len(everything) + len(searched_au) + len(searched_crypto)
                                 + sum(len(v) for v in bsky.values()) + len(bsky_asx) + sum(len(v) for v in st.values()),
                "headlines_scanned": sum(len(v) for v in news.values()),
                "tickers": results, "trending_other": trending,
                "trending_samples": {t: where[t][:3] for t, _ in trending},
                "themes": theme_counts(everything + bsky_asx),
                "recent_posts": [{k: p[k] for k in ("source", "title", "url", "date")}
                                 for p in (au_posts[:25] + bsky_asx[:10] + crypto_posts[:10])]}
        with open(SENT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
        _ASSETS_MEMO.clear()
        SCAN["progress"] = "Done"
    except Exception as e:
        SCAN["progress"] = f"Scan failed: {e}"
    finally:
        SCAN["running"] = False


def theme_counts(items):
    counts = {}
    for p in items:
        t = (p["title"] + " " + p["body"]).lower()
        for theme, keys in THEMES.items():
            if any(re.search(r"\b" + k, t) for k in keys):
                counts[theme] = counts.get(theme, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])


def summarise(reddit_items, news_items, bsky_items=(), st_items=()):
    def agg(items):
        pos = neg = opin = 0
        for p in items:
            if p.get("label") in ("Bullish", "Bearish"):     # StockTwits: the poster labelled it
                opin += 1
                pos += p["label"] == "Bullish"
                neg += p["label"] == "Bearish"
                continue
            a, b = text_sentiment(p["title"] + " " + p["body"])
            if a or b:
                opin += 1
                pos += a > b
                neg += b > a
        return {"n": len(items), "pos": pos, "neg": neg, "opinions": opin}
    by = {"Reddit": agg(reddit_items), "Bluesky": agg(bsky_items), "StockTwits": agg(st_items), "News": agg(news_items)}
    social = list(reddit_items[:5]) + list(bsky_items[:3]) + list(st_items[:3])
    return {
        "reddit_mentions": by["Reddit"]["n"], "reddit_pos": by["Reddit"]["pos"], "reddit_neg": by["Reddit"]["neg"],
        "news_count": by["News"]["n"], "news_pos": by["News"]["pos"], "news_neg": by["News"]["neg"],
        "by_source": by,
        "themes": theme_counts(list(reddit_items) + list(bsky_items))[:4],
        "samples": [{k: p.get(k) for k in ("source", "title", "url", "date", "label")} for p in social],
        "headlines": [{k: p[k] for k in ("title", "url", "date")} for p in news_items[:5]],
    }


# how much each platform can move the mood score away from the researched baseline, and how many posts it
# takes to count fully (StockTwits posters label their own posts, so those are the most reliable)
SOURCE_WEIGHT = {"Reddit": (0.35, 25), "Bluesky": (0.12, 20), "StockTwits": (0.18, 30), "News": (0.15, 20)}


def sentiment_score(u, s):
    """Blend the researched baseline with live social + news data (0-100)."""
    base = u.get("baseline", 50)
    if not s:
        return base, 0.0
    by = s.get("by_source") or {"Reddit": {"n": s["reddit_mentions"], "pos": s["reddit_pos"], "neg": s["reddit_neg"]},
                                "News": {"n": s["news_count"], "pos": s["news_pos"], "neg": s["news_neg"]}}
    acc = wsum = 0.0
    for src, (w, full) in SOURCE_WEIGHT.items():
        d = by.get(src)
        if not d or not d["n"]:
            continue
        ww = w * min(d["n"] / full, 1)
        acc += ww * 100 * (d["pos"] + 1) / (d["pos"] + d["neg"] + 2)   # smoothed share positive
        wsum += ww
    return base * (1 - wsum) + acc, wsum


# --------------------------------------------------------------------------- opportunities
DECISIONS = [(72, "Strong buy & hold", "great"), (62, "Good buy", "good"), (52, "OK as a small slice", "ok"),
             (42, "Wait and watch", "wait"), (0, "Avoid for now", "avoid")]
SIZE_HINT = {
    "core": "Can be your whole portfolio on its own.",
    "au": "Can be a big part of a portfolio, alongside a global fund.",
    "global": "Can be a big part of a portfolio, alongside an Australian fund.",
    "defensive": "For cautious or short-term money. Low growth.",
    "satellite": "Keep it to a small slice, about 10-20%.",
    "found": "Not researched: keep it small and read up on it first.",
    "stock": "Keep any one company to about 5-10% of your money.",
    "spec": "Keep all crypto together under about 5% of your money.",
}


def decision(score):
    for cut, label, tone in DECISIONS:
        if score >= cut:
            return {"label": label, "tone": tone}


def agreement(model_score, crowd_score, researched):
    if not researched:
        return {"text": "Not in the research, so the models and the live scan decide.", "dir": "none"}
    d = model_score - crowd_score
    if d >= 10:
        return {"text": "The models are more positive than the research and the crowd.", "dir": "up"}
    if d <= -10:
        return {"text": "The models are more negative than the research and the crowd.", "dir": "down"}
    return {"text": "The models agree with the research and the crowd.", "dir": "same"}


def benchmarks():
    try:
        return models.benchmark_returns(yahoo_chart("VAS.AX", "10y", "1mo"), yahoo_chart("IVV.AX", "10y", "1mo"))
    except Exception:
        return {"au": {}, "us": {}}


def no_data(u, reason, name=None):
    return {"ticker": u["ticker"], "name": name or u["name"], "kind": u.get("kind"), "no_data": True,
            "reason": reason, "discovered": u.get("discovered", False), "mentions": u.get("mentions"),
            "samples": u.get("samples", [])}


def build_asset(u, sent, bench, extras):
    try:
        m = yahoo_chart(u["yahoo"], "10y", "1mo")
    except Exception:
        return no_data(u, "No price data found for this code on Yahoo Finance.")
    kind = u.get("kind") or {"ETF": "etf", "EQUITY": "stock", "CRYPTOCURRENCY": "crypto"}.get((m.get("type") or "").upper())
    name = m["name"] if u.get("discovered") else u["name"]
    if not kind:
        return no_data(u, "Not a share, fund or coin the models can handle.", name)
    try:
        d = yahoo_chart(u["yahoo"], "1y", "1d")
    except Exception:
        d = {"close": [], "price": None}
    f = {}
    if kind in ("stock", "etf"):
        try:
            f = yahoo_fundamentals(u["yahoo"]) or {}
        except Exception:
            f = {}
    elif kind == "crypto":
        f = extras["cg"].get(u.get("coingecko"), {})
    a = models.analyse(m, bench, kind, f, {"fee": u.get("fee"), "holdings": u.get("holdings")})
    if not a["enough"]:
        return no_data(u, a["reason"], name)
    bucket = u.get("bucket") or ("found" if kind != "crypto" else "spec")
    researched = u.get("researched", True)
    s = u.get("_sent") or (sent or {}).get("tickers", {}).get(u["ticker"])
    ss, live_w = sentiment_score(u, s)
    crowd = 0.5 * u["quality"] + 0.5 * ss if researched else ss
    final = 0.6 * a["score"] + 0.4 * crowd if researched else 0.75 * a["score"] + 0.25 * ss
    pos, neg = models.reasons(a, kind)
    daily = d["close"]
    final = round(final)
    dec = decision(final)
    return {
        **{k: v for k, v in u.items() if not k.startswith("_")},
        "name": name, "kind": kind, "kind_label": KIND_LABEL[kind], "bucket": bucket,
        "bucket_label": BUCKET_LABEL.get(bucket, bucket), "researched": researched,
        "price": d.get("price") or m.get("price"), "currency": m.get("currency"),
        "day_change": (daily[-1] / daily[-2] - 1) if len(daily) > 1 else None,
        "spark": daily[::max(1, len(daily) // 120)] + daily[-1:] if daily else [],   # the past year, ~120 points
        "metrics": metrics(m), "model": a, "fundamentals": f,
        "model_score": a["score"], "crowd_score": round(crowd), "sent_score": round(ss), "live_weight": round(live_w, 2),
        "score": round(final), "decision": dec, "agreement": agreement(a["score"], crowd, researched),
        "reasons": {"pos": pos, "neg": neg}, "size_hint": SIZE_HINT.get(bucket, ""),
        "verdict": f"{dec['label']}. {SIZE_HINT.get(bucket, '')}", "sentiment": s,
    }


def discovered_items(sent):
    """Tickers people mention that the app doesn't track: they get the same data check and models."""
    out = []
    samples = (sent or {}).get("trending_samples", {})
    for t, n in (sent or {}).get("trending_other", [])[:12]:
        if n < 2 or t in BY_TICKER:
            continue
        out.append(dict(ticker=t, yahoo=f"{t}.AX", name=t, bucket=None, kind=None, researched=False, discovered=True,
                        mentions=n, samples=samples.get(t, []), fee=None, holdings=None, quality=None, baseline=50,
                        what="", community=f"Mentioned {n} times in the latest scan of Australian investing discussions.",
                        cons="Not researched. Check what the company or fund does before buying."))
    return out


_ASSETS_MEMO = {}
_ASSETS_LOCK = threading.Lock()


def all_assets():
    """Every investment through the models, grouped later by kind. Memoised for 10 minutes."""
    sent = load_sentiment()
    key = (sent or {}).get("fetched_at")
    with _ASSETS_LOCK:
        hit = _ASSETS_MEMO.get(key)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        bench, extras = benchmarks(), {"cg": coingecko_data()}
        items = UNIVERSE + discovered_items(sent)
        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(lambda u: build_asset(u, sent, bench, extras), items))
        out = {"assets": sorted([a for a in res if not a.get("no_data")], key=lambda a: -a["score"]),
               "no_data": [a for a in res if a.get("no_data")],
               "fear_greed": fear_greed(), "sentiment_at": key,
               "risk_free": models.RISK_FREE, "horizon": models.HORIZON}
        _ASSETS_MEMO.clear()
        _ASSETS_MEMO[key] = (time.time(), out)
        return out


# --------------------------------------------------------------------------- plan
PROFILES = {
    "cautious": {"cash": 0.40, "defensive": 0.10, "core": 0.50},
    "balanced": {"cash": 0.20, "core": 0.80},
    "growth":   {"cash": 0.10, "au": 0.30, "global": 0.50, "satellite": 0.10},
}


def make_plan(amount, profile, simple, monthly):
    assets = {a["ticker"]: a for a in all_assets()["assets"] if a.get("researched")}
    weights = dict(PROFILES.get(profile, PROFILES["balanced"]))
    if simple and profile == "growth":
        weights = {"cash": 0.10, "core": 0.90}
    best = {}
    for a in sorted(assets.values(), key=lambda a: -a["score"]):
        best.setdefault(a["bucket"], a)
    lines, notes = [], []
    for bucket, w in weights.items():
        amt = amount * w
        if bucket == "cash":
            lines.append({"ticker": "HISA", "name": "High-interest savings account",
                          "bucket_label": "Cash", "amount": amt, "weight": w,
                          "why": f"Grows every single month (~{HISA_RATE*100:.2f}% p.a.). Your emergency buffer "
                                 f"and the part you'll literally see go up every month."})
            continue
        a = best.get(bucket)
        if not a:
            continue
        lines.append({"ticker": a["ticker"], "name": a["name"], "bucket_label": a["bucket_label"],
                      "amount": amt, "weight": w, "score": a["score"], "fee": a["fee"],
                      "decision": a["decision"]["label"], "why": a["what"]})
    # ASX needs $500 minimum first buy - fold tiny lines into the largest share line
    share_lines = [l for l in lines if l["ticker"] != "HISA"]
    big = max(share_lines, key=lambda l: l["amount"]) if share_lines else None
    for l in list(share_lines):
        if l is not big and l["amount"] < 500:
            big["amount"] += l["amount"]; big["weight"] += l["weight"]
            lines.remove(l)
            notes.append(f"{l['ticker']} was merged into {big['ticker']} because the ASX requires at least "
                         f"$500 for a first purchase.")
    if big and big["amount"] < 500:
        notes.append("Under $500 can't buy an ASX ETF yet - keep saving in the HISA until you hit $500.")

    # expected returns for the projection: the models' growth after volatility drag, capped to stay conservative
    def exp_ret(l):
        if l["ticker"] == "HISA":
            return HISA_RATE, 0.0
        e = assets[l["ticker"]]["model"]["expected"]
        return min(e["growth"], 0.085), e["vol"]
    er = sum(l["weight"] * exp_ret(l)[0] for l in lines)
    vol = sum(l["weight"] * exp_ret(l)[1] for l in lines)

    # backtest on real monthly data (last 5 years)
    series = {}
    for l in lines:
        if l["ticker"] != "HISA":
            series[l["ticker"]] = yahoo_chart(assets[l["ticker"]]["yahoo"], "10y", "1mo")
    back = backtest(lines, series, amount, monthly, months=60)
    return {"lines": lines, "notes": notes, "exp_return": er, "exp_vol": vol, "backtest": back,
            "hisa_rate": HISA_RATE}


def backtest(lines, series, amount, monthly, months=60):
    if not series:
        return None
    n = min(min(len(s["adj"]) for s in series.values()), months + 1)
    ts = list(series.values())[0]["t"][-n:]
    units = {}
    cash = 0.0
    contributed = amount
    vals = []
    for i in range(n):
        if i == 0:
            for l in lines:
                if l["ticker"] == "HISA":
                    cash = l["amount"]
                else:
                    units[l["ticker"]] = l["amount"] / series[l["ticker"]]["adj"][-n]
        else:
            cash *= (1 + HISA_RATE) ** (1 / 12)
            if monthly:
                contributed += monthly
                for l in lines:
                    if l["ticker"] == "HISA":
                        cash += monthly * l["weight"]
                    else:
                        units[l["ticker"]] += monthly * l["weight"] / series[l["ticker"]]["adj"][-n + i]
        v = cash + sum(u * series[t]["adj"][-n + i] for t, u in units.items())
        vals.append(round(v, 2))
    return {"t": ts, "value": vals, "contributed": contributed}


# --------------------------------------------------------------------------- portfolio checker
def resolve(q):
    q = q.strip()
    up = q.upper().replace(".AX", "")
    if up in BY_TICKER:
        return BY_TICKER[up]["yahoo"], BY_TICKER[up]
    for u in UNIVERSE:
        if up.lower() in ALIASES.get(u["ticker"], []) or up.lower() == u["name"].lower():
            return u["yahoo"], u
    if re.fullmatch(r"[A-Z0-9]{3,5}", up):
        for sym in (up + ".AX", up, up + "-AUD"):
            try:
                c = yahoo_chart(sym, "10y", "1mo")
                if c["adj"]:
                    return sym, None
            except Exception:
                pass
    try:
        for r in yahoo_search(q):
            sym = r.get("symbol")
            if sym and r.get("quoteType") in ("EQUITY", "ETF", "CRYPTOCURRENCY", "MUTUALFUND"):
                if r.get("quoteType") == "CRYPTOCURRENCY" and sym.endswith("-USD"):
                    sym = sym[:-4] + "-AUD"
                return sym, None
    except Exception:
        pass
    return None, None


def classify_unknown(chart):
    typ = (chart.get("type") or "").upper()
    if typ == "CRYPTOCURRENCY":
        return "spec", "crypto"
    if typ == "ETF":
        return "satellite", "etf"
    return "stock", "stock"


def news_for(q):
    def go():
        url = ("https://news.google.com/rss/search?hl=en-AU&gl=AU&ceid=AU:en&q="
               + urllib.parse.quote(q + " shares when:60d"))
        return parse_rss(fetch(url), "Google News")[:30]
    try:
        return cached(f"news_{q}", 6 * 3600, go)
    except Exception:
        return []


def check_portfolio(items):
    sent = load_sentiment() or {}
    bench, extras = benchmarks(), {"cg": coingecko_data()}
    rows, errors = [], []
    for it in items:
        sym, known = resolve(it["ticker"])
        if not sym:
            errors.append(f"Couldn't find '{it['ticker']}'.")
            continue
        try:
            chart = yahoo_chart(sym, "10y", "1mo")
        except Exception:
            errors.append(f"No price data for '{it['ticker']}'.")
            continue
        if known:
            u = known
        else:
            bucket, kind = classify_unknown(chart)
            u = dict(ticker=it["ticker"].upper(), yahoo=sym, name=chart["name"], bucket=bucket, kind=kind,
                     researched=False, discovered=True, fee=None, holdings=None, quality=None, baseline=50, what="",
                     community="Not in the app's researched list - sentiment below is from recent news headlines only.",
                     cons="")
            u["_sent"] = summarise([], news_for(chart["name"] if len(chart["name"]) < 40 else sym.split(".")[0]))
        a = build_asset(u, sent, bench, extras)
        if a.get("no_data"):
            errors.append(f"{it['ticker']}: {a['reason']} It isn't scored.")
            continue
        rows.append({"input": it["ticker"], "symbol": sym, "name": a["name"], "amount": it["amount"],
                     "bucket": a["bucket"], "bucket_label": a["bucket_label"], "fee": a.get("fee"),
                     "quality": a.get("quality"), "metrics": a["metrics"], "score": a["score"],
                     "sent_score": a["sent_score"], "decision": a["decision"], "sentiment": a["sentiment"],
                     "community": a["community"], "cons": a["cons"], "vol": a["model"]["expected"]["vol"],
                     "spark": chart["adj"][-60:]})
    total = sum(r["amount"] for r in rows)
    if not total:
        return {"rows": rows, "errors": errors or ["Nothing to analyse."]}
    for r in rows:
        r["weight"] = r["amount"] / total

    flags, good = [], []
    w = lambda cond: sum(r["weight"] for r in rows if cond(r))
    spec = w(lambda r: r["bucket"] == "spec")
    stocks = w(lambda r: r["bucket"] == "stock")
    diversified = w(lambda r: r["bucket"] in ("core", "au", "global"))
    au = w(lambda r: r["bucket"] == "au" or r["symbol"].endswith(".AX") and r["bucket"] == "stock")
    au += 0.4 * w(lambda r: r["bucket"] == "core")
    biggest = max(rows, key=lambda r: r["weight"])
    fees = [(r["weight"], r["fee"]) for r in rows
            if r["fee"] is not None and r["bucket"] not in ("stock", "spec")]
    avg_fee = sum(a * b for a, b in fees) / sum(a for a, _ in fees) if fees else None
    vols = [(r["weight"], r["vol"]) for r in rows if r.get("vol")]
    port_vol = sum(a * b for a, b in vols) / sum(a for a, _ in vols) if vols else None

    points = 100
    if spec > 0.05:
        points -= min(40, (spec - 0.05) * 100)
        flags.append(f"{spec:.0%} is in speculative assets (crypto / very volatile). Common guidance is 5% or less.")
    if stocks > 0.3:
        points -= min(25, (stocks - 0.3) * 60)
        flags.append(f"{stocks:.0%} is in individual companies. A broad ETF spreads risk across hundreds of them.")
    if biggest["weight"] > 0.4 and biggest["bucket"] not in ("core", "au", "global"):
        points -= 15
        flags.append(f"{biggest['input']} is {biggest['weight']:.0%} of the portfolio - a lot riding on one bet.")
    if diversified < 0.5:
        points -= 15
        flags.append("Less than half is in broad diversified funds (e.g. DHHF, VDHG, VAS, VGS, IVV).")
    else:
        good.append(f"{diversified:.0%} is in broad diversified funds - that's the backbone FI communities recommend.")
    if au > 0.8 and len(rows) > 0:
        points -= 8
        flags.append("Almost everything is Australian. Australia is ~2% of world markets - consider adding global shares.")
    if avg_fee is not None:
        if avg_fee > 0.45:
            points -= 8
            flags.append(f"Average fund fee is {avg_fee:.2f}% p.a. - over 20+ years that adds up. Core ETFs cost 0.04-0.20%.")
        elif avg_fee <= 0.2:
            good.append(f"Low average fund fee ({avg_fee:.2f}% p.a.).")
    tick = {r["symbol"].split(".")[0].split("-")[0] for r in rows}
    overlaps = [("DHHF", "VAS"), ("DHHF", "VGS"), ("VDHG", "VAS"), ("VDHG", "VGS"), ("DHHF", "VDHG"),
                ("VAS", "A200"), ("VAS", "IOZ"), ("A200", "IOZ"), ("IVV", "NDQ"), ("VGS", "BGBL"),
                ("VGS", "IWLD"), ("VAS", "CBA"), ("VAS", "BHP"), ("IVV", "VTS"), ("VGS", "VTS")]
    for a, b in overlaps:
        if a in tick and b in tick:
            points -= 3
            flags.append(f"{a} and {b} overlap a lot - you're partly buying the same companies twice.")
    if len(rows) > 7:
        points -= 5
        flags.append(f"{len(rows)} holdings is a lot for this size - more brokerage, harder to track, rarely better.")
    if port_vol and port_vol > 0.3:
        flags.append(f"Expect big swings - weighted volatility is ~{port_vol:.0%}/yr (a broad ETF is ~12-16%).")
    for r in rows:
        if r["decision"]["tone"] in ("wait", "avoid"):
            flags.append(f"{r['input']}: the models say \"{r['decision']['label']}\" ({r['score']}/100).")
    points = max(0, min(100, points))
    grade = "A" if points >= 85 else "B" if points >= 72 else "C" if points >= 58 else "D" if points >= 42 else "F"
    return {"rows": rows, "errors": errors, "total": total, "grade": grade, "points": round(points),
            "flags": flags, "good": good, "avg_fee": avg_fee, "vol": port_vol,
            "mix": {"Diversified funds": diversified, "Single companies": stocks, "Speculative": spec,
                    "Other": max(0, 1 - diversified - stocks - spec)}}


# --------------------------------------------------------------------------- my portfolio
MY_PATH = os.path.join(DATA, "my_portfolio.json")


def supabase(method, path, body=None):
    """Call the Supabase REST API for the `holdings` table (rows: id text, data jsonb)."""
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/holdings{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def load_my():
    if SUPABASE_URL:
        rows = supabase("GET", "?select=data&order=created_at")
        return {"holdings": [r["data"] for r in rows]}
    if os.path.exists(MY_PATH):
        with open(MY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"holdings": []}


def save_my(d):
    with open(MY_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def add_my(h):
    if SUPABASE_URL:
        return supabase("POST", "", {"id": h["id"], "data": h})
    d = load_my()
    d["holdings"].append(h)
    save_my(d)


def delete_my(i):
    if SUPABASE_URL:
        return supabase("DELETE", "?id=eq." + urllib.parse.quote(i))
    d = load_my()
    d["holdings"] = [h for h in d["holdings"] if h["id"] != i]
    save_my(d)


def fx_to_aud(ccy):
    if ccy in (None, "AUD"):
        return 1.0
    try:
        c = yahoo_chart(f"{ccy}AUD=X", "5d", "1d")
        return c["price"] or c["close"][-1]
    except Exception:
        return 1.0


def my_value():
    d = load_my()
    out, series = [], {}
    first = None
    for h in d["holdings"]:
        buy_ts = time.mktime(time.strptime(h["date"], "%Y-%m-%d"))
        first = buy_ts if first is None else min(first, buy_ts)
        if h["ticker"] == "HISA":
            yrs = max(0, (time.time() - buy_ts) / (365.25 * 86400))
            value = h["amount"] * (1 + h.get("rate", HISA_RATE)) ** yrs
            out.append({**h, "value": value, "cost": h["amount"], "name": "Savings account"})
            continue
        sym, _ = resolve(h["ticker"])
        try:
            c = yahoo_chart(sym, "5y", "1d")
        except Exception:
            out.append({**h, "error": "no data"}); continue
        fx = fx_to_aud(c["currency"])
        price = (c["price"] or c["close"][-1]) * fx
        out.append({**h, "symbol": sym, "name": c["name"], "price": price,
                    "value": price * h["units"], "cost": h["units"] * h["price"] + h.get("fee", 0)})
        series[h["id"]] = (c, fx)
    # daily value history since first purchase
    hist = []
    if first:
        days = int((time.time() - first) // 86400) + 1
        for i in range(0, days, max(1, days // 400)):
            ts = first + i * 86400
            total = cost = 0.0
            for h in d["holdings"]:
                bts = time.mktime(time.strptime(h["date"], "%Y-%m-%d"))
                if bts > ts:
                    continue
                if h["ticker"] == "HISA":
                    total += h["amount"] * (1 + h.get("rate", HISA_RATE)) ** ((ts - bts) / (365.25 * 86400))
                    cost += h["amount"]
                elif h["id"] in series:
                    c, fx = series[h["id"]]
                    px = None
                    for t, cl in zip(c["t"], c["close"]):
                        if t <= ts + 86400:
                            px = cl
                        else:
                            break
                    px = px if px is not None else h["price"] / fx
                    total += px * fx * h["units"]
                    cost += h["units"] * h["price"] + h.get("fee", 0)
            hist.append({"t": ts, "value": round(total, 2), "cost": round(cost, 2)})
        now_total = sum(o.get("value", 0) for o in out)
        now_cost = sum(o.get("cost", 0) for o in out)
        hist.append({"t": time.time(), "value": round(now_total, 2), "cost": round(now_cost, 2)})
    return {"holdings": out, "history": hist}


# --------------------------------------------------------------------------- web server
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(ROOT, "static"), **k)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorised(self):
        """"My money" is personal, so when APP_PASSWORD is set it needs the password (browser login box)."""
        if not APP_PASSWORD:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                pw = base64.b64decode(auth[6:]).decode().partition(":")[2]
            except Exception:
                pw = ""
            if hmac.compare_digest(pw.encode(), APP_PASSWORD.encode()):
                return True
        body = json.dumps({"error": "Password needed for My money."}).encode()
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="My money"')
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(p.query))
        try:
            if p.path == "/api/assets":
                return self.send_json(all_assets())
            if p.path == "/api/research":
                return self.send_json(RESEARCH)
            if p.path == "/api/sentiment":
                return self.send_json({"scan": SCAN, "data": load_sentiment()})
            if p.path == "/api/plan":
                return self.send_json(make_plan(float(q.get("amount", 5000)), q.get("profile", "balanced"),
                                                q.get("simple") == "1", float(q.get("monthly", 0))))
            if p.path == "/api/my":
                if not self.authorised():
                    return
                return self.send_json(my_value())
            if p.path == "/api/history":
                sym, _ = resolve(q["t"])
                return self.send_json(yahoo_chart(sym, q.get("range", "5y"), q.get("interval", "1wk")))
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)
        return super().do_GET()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        try:
            if p.path == "/api/scan":
                threading.Thread(target=run_scan, daemon=True).start()
                return self.send_json({"started": True})
            if p.path == "/api/check":
                return self.send_json(check_portfolio(self.body()["items"]))
            if p.path.startswith("/api/my/") and not self.authorised():
                return
            if p.path == "/api/my/add":
                h = self.body()
                h["id"] = str(int(time.time() * 1000))
                if h["ticker"] != "HISA":
                    h["ticker"] = h["ticker"].upper().strip()
                    sym, _ = resolve(h["ticker"])
                    if not sym:
                        return self.send_json({"error": f"Couldn't find {h['ticker']}"}, 400)
                add_my(h)
                return self.send_json({"ok": True})
            if p.path == "/api/my/delete":
                delete_my(self.body()["id"])
                return self.send_json({"ok": True})
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)
        self.send_error(404)


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"\n  Investing Opportunities is running at {url}\n  (close this window or press Ctrl+C to stop)\n")
    if not load_sentiment():
        threading.Thread(target=run_scan, daemon=True).start()
    if os.environ.get("NO_BROWSER") != "1" and "PORT" not in os.environ:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
