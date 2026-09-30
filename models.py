"""
The maths the app uses to check the research against real price and company data.

Every investment with at least 3 years of monthly prices goes through the same models:

1. Market regression (a two-factor CAPM, Jensen 1968). Monthly returns above the risk-free rate are
   regressed on the Australian market (VAS) and the US market in AUD (IVV):
       r - rf = alpha + b_au (AU - rf) + b_us (US - rf) + e
   Gives beta (how much it moves with the market), alpha (return the market doesn't explain),
   R-squared, and the risk that is specific to this investment.
2. Expected return with Bayesian shrinkage (Jorion 1986, Bayes-Stein). Past average returns are very
   noisy, so the historical mean is pulled towards what the market regression says the investment
   should earn (rf + beta x equity risk premium). Short or wild histories get pulled harder.
3. Growth after volatility drag. What an investment compounds at is roughly mean - variance / 2, so a
   very bumpy ride grows slower than its average suggests. The same lognormal model gives the chance of
   being down after 5 years and a likely range for $1,000.
4. Log-trend regression. ln(price) = a + b * month over the last 10 years: b is the trend growth rate,
   R-squared says how steady that trend has been, and the residual says whether the price is stretched
   above or sagging below its own trend.
5. Trend-following signals: 12-month momentum skipping the latest month (Jegadeesh & Titman 1993;
   Moskowitz, Ooi & Pedersen 2012) and price vs its 10-month average (Faber 2007).
6. Downside risk: maximum drawdown, conditional value at risk (the average of the worst 5% of months,
   Rockafellar & Uryasev 2000) and the Sortino ratio (return per unit of downside swings).
7. Fundamentals: for companies, value (earnings yield), quality (return on equity, margins; Novy-Marx
   2013), growth, balance-sheet safety and analyst views. For funds: fee, size and diversification.
   Crypto has no earnings, so it scores low here by design.

Standard library only.
"""
import math
import statistics
import time

RISK_FREE = 0.0435         # RBA cash rate, Sept 2026
EQUITY_PREMIUM = 0.045     # long-run equity risk premium used for the prior (commonly estimated at 4-5%)
MIN_MONTHS = 36            # fewer than 3 years of prices: not enough data to judge
HORIZON = 5                # years, for the chance-of-loss and $1,000 range

WEIGHTS = {"growth": 0.30, "riskadj": 0.20, "downside": 0.15, "trend": 0.10, "steady": 0.10, "fundamentals": 0.15}


# --------------------------------------------------------------------------- helpers
def lin(x, lo, hi):
    """Map x onto 0-100: lo or worse is 0, hi or better is 100."""
    if x is None:
        return None
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def month_prices(chart):
    """Last adjusted price in each calendar month: {'2024-05': price}. Yahoo sometimes adds an extra
    point for the current month, so later points win."""
    out = {}
    for t, p in zip(chart["t"], chart["adj"]):
        if p and p > 0:
            out[time.strftime("%Y-%m", time.gmtime(t))] = p
    return dict(sorted(out.items()))


def returns(prices):
    ks = list(prices)
    return {ks[i]: prices[ks[i]] / prices[ks[i - 1]] - 1 for i in range(1, len(ks))}


def solve(A, b):
    """Gauss-Jordan elimination with partial pivoting. Returns x with A x = b, or None if singular."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [a - f * b_ for a, b_ in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def ols(y, X):
    """Ordinary least squares. X rows include the intercept column. Returns coefficients, their t-stats,
    R-squared and the residual standard deviation."""
    n, k = len(y), len(X[0])
    if n <= k + 2:
        return None
    XtX = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    Xty = [sum(X[r][i] * y[r] for r in range(n)) for i in range(k)]
    b = solve(XtX, Xty)
    if b is None:
        return None
    fit = [sum(bi * xi for bi, xi in zip(b, row)) for row in X]
    res = [yi - fi for yi, fi in zip(y, fit)]
    sse = sum(e * e for e in res)
    ybar = sum(y) / n
    sst = sum((yi - ybar) ** 2 for yi in y) or 1e-12
    s2 = sse / (n - k)
    tstats = []
    for i in range(k):
        e = [0.0] * k
        e[i] = 1.0
        col = solve(XtX, e)          # column i of (X'X)^-1
        se = math.sqrt(max(s2 * col[i], 1e-18)) if col else None
        tstats.append(b[i] / se if se else None)
    return {"b": b, "t": tstats, "r2": 1 - sse / sst, "resid_sd": math.sqrt(s2), "n": n, "res": res}


# --------------------------------------------------------------------------- benchmarks
def benchmark_returns(au_chart, us_chart):
    return {"au": returns(month_prices(au_chart)), "us": returns(month_prices(us_chart))}


# --------------------------------------------------------------------------- fundamentals
def fund_score(kind, f, info):
    """0-100 from company / fund / coin data, plus the pieces it was built from. None if too little data."""
    f = f or {}
    parts = {}
    if kind == "stock":
        pe = f.get("forward_pe") or f.get("pe")
        if pe is not None:
            parts["value"] = lin(1 / pe, 0.02, 0.08) if pe > 0 else 10
        q = [x for x in (lin(f.get("roe"), 0.03, 0.25), lin(f.get("margin"), 0.0, 0.25)) if x is not None]
        if q:
            parts["quality"] = sum(q) / len(q)
        g = [x for x in (lin(f.get("rev_growth"), -0.05, 0.15), lin(f.get("earn_growth"), -0.10, 0.20)) if x is not None]
        if g:
            parts["growth"] = sum(g) / len(g)
        if f.get("debt_equity") is not None:
            parts["safety"] = lin(-f["debt_equity"], -200, -20)
        if (f.get("analysts") or 0) >= 3:
            a = [x for x in (lin(-(f.get("rec_mean") or 3), -4.0, -1.5), lin(f.get("target_upside"), -0.15, 0.20)) if x is not None]
            parts["analysts"] = sum(a) / len(a)
        if f.get("div_yield") is not None:
            parts["income"] = lin(f["div_yield"], 0.0, 0.05)
        if len(parts) < 3:
            return None, parts
    elif kind == "etf":
        fee = info.get("fee")
        if fee is not None:
            parts["fee"] = lin(-fee, -0.70, -0.03)
        if f.get("total_assets"):
            parts["size"] = lin(math.log10(f["total_assets"]), 7.5, 10.0)   # $30M ... $10B
        if info.get("holdings"):
            parts["diversification"] = lin(math.log10(max(info["holdings"], 1)), 1.0, 3.5)
        if not parts:
            return None, parts
    elif kind == "crypto":
        rank = f.get("mcap_rank")
        if rank:
            parts["size"] = lin(-rank, -50, -1)
        # no earnings, cash flow or dividends to value: capped low on purpose
        return 0.35 * (parts.get("size") or 0), parts
    else:
        return None, parts
    return sum(parts.values()) / len(parts), parts


# --------------------------------------------------------------------------- the full analysis
def analyse(chart, bench, kind, fundamentals=None, info=None):
    """Run every model on one investment. kind: 'etf', 'stock' or 'crypto'."""
    info = info or {}
    prices = month_prices(chart)
    months = len(prices)
    if months < MIN_MONTHS + 1:
        return {"enough": False, "months": months,
                "reason": f"Only {months} month{'s' if months != 1 else ''} of price history (needs 3 years)."}
    keys = list(prices)
    rets_all = returns(prices)
    rk = list(rets_all)[-120:]                    # last 10 years for the statistics
    r = [rets_all[k] for k in rk]
    rf_m = (1 + RISK_FREE) ** (1 / 12) - 1

    # volatility from log returns: a few enormous up-months (crypto) would otherwise blow it up. The matching
    # average (arithmetic) return of a lognormal is the log mean plus half the variance.
    lr = [math.log(1 + x) for x in r]
    vol = statistics.stdev(lr) * math.sqrt(12)
    mu_hist = statistics.fmean(lr) * 12 + vol ** 2 / 2

    # 1. market regression
    reg = None
    both = [k for k in rk if k in bench["au"] and k in bench["us"]]
    if len(both) >= 24:
        y = [rets_all[k] - rf_m for k in both]
        X = [[1.0, bench["au"][k] - rf_m, bench["us"][k] - rf_m] for k in both]
        o = ols(y, X)
        if o:
            reg = {"alpha": o["b"][0] * 12, "alpha_t": o["t"][0], "beta_au": o["b"][1], "beta_us": o["b"][2],
                   "r2": o["r2"], "idio_vol": o["resid_sd"] * math.sqrt(12), "months": o["n"]}

    # 2. expected return: shrink the noisy historical mean towards what the regression says it should earn
    beta_sum = (reg["beta_au"] + reg["beta_us"]) if reg else (1.0 if kind != "crypto" else 1.5)
    prior = RISK_FREE + max(0.0, beta_sum) * EQUITY_PREMIUM
    se = vol / math.sqrt(len(r) / 12)                  # standard error of the historical mean
    tau = 0.15 if kind == "crypto" else 0.03           # how far a true long-run return can sit from the prior (crypto: far less known)
    w_hist = (1 / se ** 2) / (1 / se ** 2 + 1 / tau ** 2)
    mu = w_hist * mu_hist + (1 - w_hist) * prior

    # 3. growth after volatility drag, chance of loss and range over the horizon
    g = mu - vol ** 2 / 2
    sd_h = vol * math.sqrt(HORIZON)
    p_loss = norm_cdf(-g * HORIZON / sd_h) if sd_h else 0.0
    band = {q: round(1000 * math.exp(g * HORIZON + z * sd_h)) for q, z in (("p10", -1.2816), ("p50", 0.0), ("p90", 1.2816))}
    sharpe = (mu - RISK_FREE) / vol if vol else 0.0
    reliable = vol <= 0.8                              # beyond this the 5-year range is too wide to mean much

    # 4. log-trend regression on prices
    tk = keys[-121:]
    lp = [math.log(prices[k]) for k in tk]
    tr = ols(lp, [[1.0, float(i)] for i in range(len(lp))])
    trend = None
    if tr:
        trend = {"growth": math.exp(tr["b"][1] * 12) - 1, "r2": tr["r2"],
                 "z": tr["res"][-1] / tr["resid_sd"] if tr["resid_sd"] else 0.0,
                 "line": [round(math.exp(tr["b"][0] + tr["b"][1] * i), 4) for i in range(len(lp))], "keys": tk}

    # 5. trend-following signals
    pl = [prices[k] for k in keys]
    mom = pl[-2] / pl[-13] - 1 if len(pl) >= 13 else None
    ma10 = statistics.fmean(pl[-10:])
    above_ma = pl[-1] > ma10

    # 6. downside risk (drawdown over the whole history we have)
    peak, mdd = pl[0], 0.0
    for p in pl:
        peak = max(peak, p)
        mdd = min(mdd, p / peak - 1)
    worst = sorted(r)[:max(1, round(len(r) * 0.05))]
    cvar = statistics.fmean(worst)
    down = math.sqrt(statistics.fmean([min(x - rf_m, 0) ** 2 for x in r])) * math.sqrt(12)
    sortino = (mu - RISK_FREE) / down if down else None
    wins = [pl[i] > pl[i - 12] for i in range(12, len(pl))]
    up_pct = sum(wins) / len(wins) if wins else None

    # 7. fundamentals
    fs, fparts = fund_score(kind, fundamentals, info)

    # component scores (0-100)
    comp = {
        "growth": lin(g, -0.04, 0.10),
        "riskadj": lin(sharpe, -0.10, 0.60),
        "downside": 0.5 * lin(mdd, -0.75, -0.10) + 0.5 * lin(cvar, -0.25, -0.03),
        "trend": 0.5 * (lin(mom, -0.25, 0.35) if mom is not None else 50) + 0.5 * (80 if above_ma else 25),
        "steady": 0.5 * (lin(up_pct, 0.40, 0.90) if up_pct is not None else 50) + 0.5 * (lin(trend["r2"], 0.30, 0.95) if trend else 50),
        "fundamentals": fs,
    }
    if trend and trend["z"] > 2:                     # far above its own long-run trend: likely stretched
        comp["trend"] = max(0, comp["trend"] - 15)
    used = {k: w for k, w in WEIGHTS.items() if comp[k] is not None}
    score = sum(comp[k] * w for k, w in used.items()) / sum(used.values())

    # a short history can look great just because markets rose the whole time: pull it towards neutral
    years = len(r) / 12
    trust = 0.6 + 0.4 * min(1.0, max(0.0, (years - 3) / 5))
    score = 50 + (score - 50) * trust
    confidence = "High" if years >= 8 and vol < 0.35 else "Medium" if years >= 5 and vol < 0.6 else "Low"

    return {
        "enough": True, "months": months, "years": round(years, 1), "score": round(score),
        "components": {k: (round(v) if v is not None else None) for k, v in comp.items()}, "trust": round(trust, 2),
        "confidence": confidence,
        "expected": {"mu": mu, "mu_hist": mu_hist, "prior": prior, "weight_hist": w_hist, "growth": g,
                     "vol": vol, "sharpe": sharpe, "sortino": sortino, "p_loss": p_loss, "band": band, "reliable": reliable},
        "regression": reg,
        "trend": {k: v for k, v in (trend or {}).items() if k not in ("line", "keys")} or None,
        "trend_line": {"keys": trend["keys"], "line": trend["line"]} if trend else None,
        "signals": {"mom12_1": mom, "above_ma10": above_ma, "ma10": ma10},
        "risk": {"mdd": mdd, "cvar5": cvar, "downside_vol": down, "up_years_pct": up_pct},
        "fundamentals": {"score": round(fs) if fs is not None else None,
                         "parts": {k: round(v) for k, v in fparts.items() if v is not None}},
    }


def reasons(a, kind):
    """Plain-English reasons behind the model score: the strongest positives and negatives."""
    e, rk, sg, reg, tr = a["expected"], a["risk"], a["signals"], a["regression"], a["trend"]
    pos, neg = [], []
    if not e["reliable"]:
        neg.append(f"Swings about ±{e['vol']:.0%} a year, too wild to forecast. Treat it as a gamble.")
    elif e["growth"] >= 0.07:
        pos.append(f"Expected to grow about {e['growth']:.1%} a year once its ups and downs are taken into account.")
    elif e["growth"] < 0.02:
        neg.append(f"Expected growth after its ups and downs is only about {e['growth']:.1%} a year.")
    if not e["reliable"]:
        pass
    elif e["p_loss"] <= 0.12:
        pos.append(f"Only about a {e['p_loss']:.0%} chance of being down after {HORIZON} years, going by its history.")
    elif e["p_loss"] >= 0.30:
        neg.append(f"About a {e['p_loss']:.0%} chance of being down after {HORIZON} years.")
    if rk["mdd"] <= -0.5:
        neg.append(f"Has fallen {-rk['mdd']:.0%} from a peak before. Expect gut-wrenching drops.")
    elif rk["mdd"] >= -0.25:
        pos.append(f"Its worst fall was {-rk['mdd']:.0%}, mild for an investment like this.")
    if sg["mom12_1"] is not None:
        if sg["mom12_1"] > 0.10 and sg["above_ma10"]:
            pos.append("Strong upward momentum over the past year.")
        elif sg["mom12_1"] < -0.05 and not sg["above_ma10"]:
            neg.append("In a downtrend: below its 10-month average and down over the past year.")
    if tr and tr["z"] > 2:
        neg.append("Trading well above its own long-run trend, so it may be stretched.")
    if reg and reg["alpha_t"] is not None and abs(reg["alpha_t"]) >= 2:
        (pos if reg["alpha"] > 0 else neg).append(
            f"Has {'beaten' if reg['alpha'] > 0 else 'lagged'} what the market explains by {abs(reg['alpha']):.1%} a year, and that's statistically solid.")
    if e["mu_hist"] - e["mu"] > 0.03 and e["reliable"]:
        neg.append(f"Its past {e['mu_hist']:.1%} a year was probably partly luck. Returns that bumpy are hard to trust, "
                   f"so the models expect less.")
    fp = a["fundamentals"]["parts"]
    if kind == "stock":
        if fp.get("value") is not None and fp["value"] < 25:
            neg.append("Expensive compared with its earnings (high P/E).")
        if fp.get("value") is not None and fp["value"] > 70:
            pos.append("Cheap compared with its earnings (low P/E).")
        if fp.get("analysts") is not None and fp["analysts"] < 30:
            neg.append("Most analysts rate it a hold or sell, or see little upside.")
        if fp.get("analysts") is not None and fp["analysts"] > 70:
            pos.append("Analysts are broadly positive and see upside to their price targets.")
        if fp.get("quality") is not None and fp["quality"] > 70:
            pos.append("A high-quality, profitable business.")
    if kind == "etf" and fp.get("fee") is not None and fp["fee"] > 85:
        pos.append("Very low fee.")
    if kind == "crypto":
        neg.append("No earnings or dividends. Its value rests entirely on what the next buyer will pay.")
    return pos[:4], neg[:4]
