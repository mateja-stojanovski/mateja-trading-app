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
import json
import math
import os
import re
import statistics
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from universe import ALIASES, BUCKET_LABEL, BY_TICKER, HISA_RATE, RESEARCH, UNIVERSE

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


def metrics(monthly):
    """Performance stats from a monthly adjusted-close series (includes dividends)."""
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
    full = (a[-1] / a[0]) ** (12 / (len(a) - 1)) - 1
    out["cagr_all"] = full
    rets = [math.log(a[i] / a[i - 1]) for i in range(max(1, len(a) - 60), len(a))]
    out["vol"] = statistics.pstdev(rets) * math.sqrt(12) if len(rets) > 2 else None
    peak, mdd = a[0], 0.0
    for v in a:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    out["mdd"] = mdd
    # share of 12-month windows that finished higher - "how often does it go up"
    wins = [a[i] > a[i - 12] for i in range(12, len(a))]
    out["up_years_pct"] = sum(wins) / len(wins) if wins else None
    return out


def perf_score(m):
    """0-100: risk-adjusted long-term return."""
    g = m.get("cagr5") if m.get("cagr5") is not None else m.get("cagr_all")
    vol = m.get("vol")
    if g is None or not vol:
        return 50
    g = min(g, 0.12)                            # don't reward chasing a hot streak
    sharpe = (g - HISA_RATE * 0.8) / max(vol, 0.03)
    s = 50 + sharpe * 45
    s -= max(0, -m.get("mdd", 0) - 0.35) * 60   # extra penalty for brutal crashes
    trust = min(1, m.get("years", 0) / 7)       # short history = less trust
    s = trust * s + (1 - trust) * 60
    return max(0, min(100, s))


# --------------------------------------------------------------------------- sentiment
POS = ["buy", "bought", "buying", "hold", "holding", "solid", "great", "good", "love", "recommend",
       "set and forget", "set-and-forget", "low fee", "low fees", "cheap", "diversified", "diversification",
       "long term", "long-term", "compounding", "happy", "winner", "outperform", "strong", "boring",
       "safe", "simple", "easy", "no brainer", "bullish", "growth", "up", "gains", "record high", "rally",
       "beat", "upgrade", "surge", "soar", "jump", "rise", "rises", "rising", "top pick", "best"]
NEG = ["sell", "sold", "selling", "avoid", "overvalued", "expensive", "crash", "crashed", "bubble", "scam",
       "risky", "risk", "loss", "losses", "lost", "regret", "dump", "dumped", "bearish", "worst", "bad",
       "terrible", "high fee", "high fees", "overlap", "concentrated", "concentration", "down", "fall",
       "falls", "falling", "plunge", "slump", "tumble", "drop", "drops", "downgrade", "warn", "warning",
       "fear", "worried", "nervous", "underperform", "hype", "fomo", "gamble", "gambling", "rug"]
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
}

SUBS = "fiaustralia+AusFinance+ASX_Bets+ausstocks"
REDDIT_FEEDS = [
    ("r/fiaustralia (top this month)", "https://www.reddit.com/r/fiaustralia/top/.rss?t=month&limit=100"),
    ("r/fiaustralia (newest)", "https://www.reddit.com/r/fiaustralia/new/.rss?limit=100"),
    ("r/AusFinance (investing, top month)",
     "https://www.reddit.com/r/AusFinance/search.rss?q=ETF+OR+shares+OR+invest&restrict_sr=1&sort=top&t=month"),
    ("r/ASX_Bets (top this month)", "https://www.reddit.com/r/ASX_Bets/top/.rss?t=month&limit=100"),
    ("r/ausstocks (top this month)", "https://www.reddit.com/r/ausstocks/top/.rss?t=month&limit=100"),
]

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
    for phrase in [p for p in POS if " " in p]:
        pos += t.count(phrase)
    for phrase in [p for p in NEG if " " in p]:
        neg += t.count(phrase)
    return pos, neg


def parse_atom(raw, source):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(raw).findall("a:entry", ns):
        link = e.find("a:link", ns)
        out.append({
            "source": source,
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
            "source": source,
            "title": clean(it.findtext("title", "")),
            "body": clean(it.findtext("description", ""))[:600],
            "url": it.findtext("link", ""),
            "date": it.findtext("pubDate", "")[:16],
        })
    return out


def mention_patterns(ticker, name=""):
    pats = [re.compile(r"(?<![A-Za-z0-9])\$?" + re.escape(ticker) + r"(?![A-Za-z0-9])")]  # case-sensitive
    for a in ALIASES.get(ticker, []):
        pats.append(re.compile(r"\b" + re.escape(a) + r"\b", re.I))
    return pats


def mentions(text, pats):
    return any(p.search(text) for p in pats)


SCAN = {"running": False, "progress": "", "done": 0, "total": 0}
SENT_PATH = os.path.join(DATA, "sentiment.json")


def load_sentiment():
    if os.path.exists(SENT_PATH):
        with open(SENT_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


def reddit_get(url):
    for attempt in range(3):
        try:
            return fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(15 + attempt * 15)
                continue
            raise


def run_scan():
    """Scan Reddit + Google News, attribute posts to tickers, score sentiment. ~2 minutes."""
    if SCAN["running"]:
        return
    SCAN.update(running=True, done=0, progress="Starting...")
    try:
        sources, posts = [], []
        tickers = [u for u in UNIVERSE]
        # one Reddit search per group of tickers (Reddit rate-limits hard, so keep requests few)
        terms = [u["ticker"] if u["bucket"] != "spec" else u["name"] for u in tickers]
        groups = [terms[i:i + 6] for i in range(0, len(terms), 6)]
        SCAN["total"] = len(REDDIT_FEEDS) + len(groups) + len(tickers)

        for label, url in REDDIT_FEEDS:
            SCAN["progress"] = f"Reading {label}"
            try:
                got = parse_atom(reddit_get(url), label)
                posts += got
                sources.append({"name": label, "ok": True, "items": len(got)})
            except Exception as e:
                sources.append({"name": label, "ok": False, "error": str(e)[:80]})
            SCAN["done"] += 1
            time.sleep(5)

        searched = []
        ok = fail = 0
        for g in groups:
            SCAN["progress"] = "Searching Reddit for " + ", ".join(g)
            q = " OR ".join(g)
            url = (f"https://www.reddit.com/r/{SUBS}/search.rss?q={urllib.parse.quote(q)}"
                   f"&restrict_sr=1&sort=relevance&t=year&limit=100")
            try:
                searched += parse_atom(reddit_get(url), "Reddit search")
                ok += 1
            except Exception:
                fail += 1
            SCAN["done"] += 1
            time.sleep(5)
        sources.append({"name": "Reddit ticker search (4 AU subs, past year)", "ok": ok > 0,
                        "items": len(searched),
                        "error": f"{fail} searches rate-limited" if fail else None})

        news = {}
        def get_news(u):
            q = f'"{u["ticker"]}" ASX' if u["bucket"] not in ("spec",) else u["name"] + " price"
            if u["bucket"] in ("core", "au", "global", "defensive", "satellite"):
                q = f'{u["ticker"]} ETF'
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
        sources.append({"name": "Google News (AU, last 60 days)", "ok": True,
                        "items": sum(len(v) for v in news.values())})

        # ---- attribute + score
        results = {}
        for u in tickers:
            t = u["ticker"]
            pats = mention_patterns(t, u["name"])
            seen, items = set(), []
            for p in posts + searched:
                txt = p["title"] + " " + p["body"]
                if p["url"] in seen or not mentions(txt, pats):
                    continue
                seen.add(p["url"])
                items.append(p)
            news_items = [n for n in news.get(t, []) if n["url"] not in seen]
            results[t] = summarise(items, news_items)

        # tickers people talk about that we don't track
        other = {}
        for p in posts:
            for m in re.findall(r"(?:ASX:\s?|\$)([A-Z]{3,4})\b", p["title"] + " " + p["body"]):
                if m not in BY_TICKER:
                    other[m] = other.get(m, 0) + 1
        trending = sorted(other.items(), key=lambda x: -x[1])[:15]

        themes_all = theme_counts(posts)
        data = {"fetched_at": time.strftime("%Y-%m-%d %H:%M"), "sources": sources,
                "posts_scanned": len(posts) + len(searched),
                "headlines_scanned": sum(len(v) for v in news.values()),
                "tickers": results, "trending_other": trending, "themes": themes_all,
                "recent_posts": [{k: p[k] for k in ("source", "title", "url", "date")} for p in posts[:40]]}
        with open(SENT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
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


def summarise(reddit_items, news_items):
    def agg(items):
        pos = neg = opin = 0
        for p in items:
            a, b = text_sentiment(p["title"] + " " + p["body"])
            if a or b:
                opin += 1
                pos += a > b
                neg += b > a
        return pos, neg, opin
    rp, rn, ro = agg(reddit_items)
    np_, nn, no = agg(news_items)
    return {
        "reddit_mentions": len(reddit_items), "reddit_pos": rp, "reddit_neg": rn,
        "news_count": len(news_items), "news_pos": np_, "news_neg": nn,
        "themes": theme_counts(reddit_items)[:4],
        "samples": [{k: p[k] for k in ("source", "title", "url", "date")} for p in reddit_items[:6]],
        "headlines": [{k: p[k] for k in ("title", "url", "date")} for p in news_items[:5]],
    }


def sentiment_score(u, s):
    """Blend researched baseline with live social + news data (0-100)."""
    base = u.get("baseline", 50)
    if not s:
        return base, 0.0
    def ratio(p, n):
        return (p + 1) / (p + n + 2)  # smoothed share positive
    r_live = 100 * ratio(s["reddit_pos"], s["reddit_neg"])
    n_live = 100 * ratio(s["news_pos"], s["news_neg"])
    wr = min(s["reddit_mentions"] / 25, 1) * 0.45
    wn = min(s["news_count"] / 20, 1) * 0.15
    score = base * (1 - wr - wn) + r_live * wr + n_live * wn
    return score, wr + wn


# --------------------------------------------------------------------------- opportunities
def build_asset(u, sent):
    try:
        m = yahoo_chart(u["yahoo"], "10y", "1mo")
        d = yahoo_chart(u["yahoo"], "1y", "1d")
    except Exception as e:
        return {**u, "error": str(e)}
    met = metrics(m)
    daily = d["close"]
    s = (sent or {}).get("tickers", {}).get(u["ticker"])
    ss, live_w = sentiment_score(u, s)
    ps = perf_score(met)
    fee_pen = min(u["fee"] * 25, 15)
    score = 0.40 * u["quality"] + 0.30 * ps + 0.30 * ss - fee_pen * 0.3
    if u["bucket"] == "spec":
        score = min(score, 35)
    elif u["bucket"] == "stock":
        score = min(score, 60)
    return {
        **u, "bucket_label": BUCKET_LABEL[u["bucket"]],
        "price": d.get("price") or m.get("price"), "currency": m.get("currency"),
        "day_change": (daily[-1] / daily[-2] - 1) if len(daily) > 1 else None,
        "spark": daily[-120:], "metrics": met,
        "perf_score": round(ps), "sent_score": round(ss), "live_weight": round(live_w, 2),
        "score": round(score), "verdict": verdict(u, score, met), "sentiment": s,
    }


def verdict(u, score, m):
    b = u["bucket"]
    if b == "spec":
        return "Speculative - only money you can afford to lose (max ~5%)."
    if b == "stock":
        return "Single company - more risk than a fund. Better as a small extra than a core holding."
    if score >= 80:
        return "Strong long-term core holding."
    if score >= 70:
        return "Good long-term option."
    if score >= 60:
        return "OK as a small slice alongside a core fund."
    return "Weaker fit for a beginner long-term portfolio."


def all_assets():
    sent = load_sentiment()
    with ThreadPoolExecutor(8) as ex:
        assets = list(ex.map(lambda u: build_asset(u, sent), UNIVERSE))
    return sorted(assets, key=lambda a: -a.get("score", 0))


# --------------------------------------------------------------------------- plan
PROFILES = {
    "cautious": {"cash": 0.40, "defensive": 0.10, "core": 0.50},
    "balanced": {"cash": 0.20, "core": 0.80},
    "growth":   {"cash": 0.10, "au": 0.30, "global": 0.50, "satellite": 0.10},
}


def make_plan(amount, profile, simple, monthly):
    assets = {a["ticker"]: a for a in all_assets() if "error" not in a}
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
                      "why": a["what"]})
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

    # expected returns (conservative) for projection
    def exp_ret(l):
        if l["ticker"] == "HISA":
            return HISA_RATE, 0.0
        a = assets[l["ticker"]]
        m = a["metrics"]
        hist = m.get("cagr10") or m.get("cagr5") or m.get("cagr_all") or 0.07
        return min(hist, 0.085) * 0.9, m.get("vol") or 0.15   # haircut: past != future
    er = sum(l["weight"] * exp_ret(l)[0] for l in lines)
    vol = sum(l["weight"] * exp_ret(l)[1] for l in lines)

    # backtest on real monthly data (last 5 years)
    series = {}
    for l in lines:
        if l["ticker"] != "HISA":
            m = yahoo_chart(assets[l["ticker"]]["yahoo"], "10y", "1mo")
            series[l["ticker"]] = m
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
    if up in ("BITCOIN",):
        return "BTC-AUD", BY_TICKER["BTC"]
    if up in ("ETHEREUM",):
        return "ETH-AUD", BY_TICKER["ETH"]
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


def classify_unknown(chart, met):
    typ = (chart.get("type") or "").upper()
    if typ == "CRYPTOCURRENCY":
        return "spec"
    if typ == "ETF":
        return "satellite"
    vol = met.get("vol") or 0
    return "spec" if vol > 0.55 else "stock"


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
        met = metrics(chart)
        if known:
            a = build_asset(known, sent)
            bucket, fee, quality, name = known["bucket"], known["fee"], known["quality"], known["name"]
            s = a.get("sentiment"); sscore = a.get("sent_score"); score = a.get("score")
            community = known["community"]; cons = known["cons"]
        else:
            bucket = classify_unknown(chart, met)
            fee = None
            quality = {"spec": 30, "stock": 55, "satellite": 55}[bucket]
            name = chart["name"]
            nitems = news_for(chart["name"] if len(chart["name"]) < 40 else sym.split(".")[0])
            s = summarise([], nitems)
            fake = {"baseline": 50}
            sscore, _ = sentiment_score(fake, s)
            ps = perf_score(met)
            score = 0.4 * quality + 0.3 * ps + 0.3 * sscore
            score = min(score, 35 if bucket == "spec" else 60)
            community = "Not in the app's researched list - sentiment below is from recent news headlines only."
            cons = ""
        rows.append({"input": it["ticker"], "symbol": sym, "name": name, "amount": it["amount"],
                     "bucket": bucket, "bucket_label": BUCKET_LABEL[bucket], "fee": fee, "quality": quality,
                     "metrics": met, "score": round(score or 0), "sent_score": round(sscore or 50),
                     "sentiment": s, "community": community, "cons": cons,
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
    vols = [(r["weight"], r["metrics"].get("vol")) for r in rows if r["metrics"].get("vol")]
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
                ("VGS", "IWLD"), ("VAS", "CBA"), ("VAS", "BHP")]
    for a, b in overlaps:
        if a in tick and b in tick:
            points -= 3
            flags.append(f"{a} and {b} overlap a lot - you're partly buying the same companies twice.")
    if len(rows) > 7:
        points -= 5
        flags.append(f"{len(rows)} holdings is a lot for this size - more brokerage, harder to track, rarely better.")
    if port_vol and port_vol > 0.3:
        flags.append(f"Expect big swings - weighted volatility is ~{port_vol:.0%}/yr (a broad ETF is ~12-16%).")
    weak = [r for r in rows if r["score"] < 45]
    for r in weak:
        flags.append(f"{r['input']} scores low ({r['score']}/100) on the app's long-term model.")
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
                return self.send_json({"assets": all_assets(), "sentiment_at": (load_sentiment() or {}).get("fetched_at")})
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
