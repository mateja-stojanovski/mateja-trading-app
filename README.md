# Investing Opportunities

A local app that suggests long-term investments for an Australian beginner. It also checks other
people's portfolios.

## Start it
- Double-click **Start Investing App.bat**, or
- in the VS Code terminal: `python server.py`

Then open http://localhost:8765 (it opens automatically). Close the window or press Ctrl+C to stop.
You don't need to install anything; it only uses Python's standard library.

## Tabs
| Tab | What it does |
|---|---|
| Start here | Enter an amount and how much risk you can handle. You get a split, a 20-year projection, and a 5-year backtest on real prices. |
| Opportunities | Split into **ETFs & funds**, **Stocks** and **Crypto**. Each investment gets a decision (Strong buy & hold → Avoid for now) from statistical models run on real data plus the research and online mood. Click one for the full breakdown. Anything without enough data is listed separately. |
| Check a portfolio | Paste someone's holdings (`CBA 3000`, `Bitcoin 1500`...). Each one goes through the same models. You get a grade A-F and a list of red flags. |
| My money | Log your real purchases and watch the value chart grow. Saved in `data/my_portfolio.json`. |
| Community pulse | Scans Reddit (Australian investing and crypto subreddits), Bluesky, StockTwits and Google News, then scores the mood. |
| Basics | The Australian essentials: CHESS brokers, the $500 minimum, franking credits, CGT, scams. |

## How the decision works
Every investment is judged two ways, then the two are combined:

`final = 60% models + 40% research & crowd` (investments that weren't researched: `75% models + 25% live mood`)

**Research & crowd** is half the hand-set research rating in `universe.py` (diversification, fees, reputation)
and half the online mood: the baseline from the research, moved by the share of positive vs negative posts on
Reddit, Bluesky, StockTwits (whose users label posts Bullish/Bearish) and news headlines.

**The models** (`models.py`) run on up to 10 years of monthly prices including dividends, plus company data:

| Model | What it gives |
|---|---|
| Two-factor market regression (CAPM, Jensen 1968) against Australian (VAS) and US (IVV) shares | beta, alpha with its t-statistic, R-squared |
| Bayesian shrinkage of the expected return (Jorion 1986) towards what its market exposure should earn | an expected return that doesn't just trust a lucky decade |
| Lognormal growth after volatility drag | expected yearly growth, chance of loss after 5 years, the range for $1,000 |
| Log-price trend regression | trend growth, how steady it is, whether the price is stretched above trend |
| 12-1 month momentum (Jegadeesh & Titman 1993) and the 10-month average rule (Faber 2007) | the current trend |
| Maximum drawdown, CVaR 5% (Rockafellar & Uryasev 2000), Sortino ratio | downside risk |
| Fundamentals from Yahoo Finance (companies: P/E, ROE, margins, growth, debt, analyst ratings and targets; funds: fee, size, holdings; coins: CoinGecko rank) | value, quality and safety |

These become six 0-100 parts (growth 30%, return for the risk 20%, downside 15%, trend 10%, steadiness 10%,
fundamentals 15%). Histories under 8 years are pulled towards 50. Under 3 years isn't scored at all and goes in
**Not enough data**. Swings above 80% a year are marked "too wild to forecast".

Decisions: 72+ Strong buy & hold, 62+ Good buy, 52+ OK as a small slice, 42+ Wait and watch, below that Avoid for now.
Each also says how big a slice it should be (a whole portfolio for an all-in-one fund, 5-10% for one company,
under 5% for all crypto).

Tickers people mention online (`$XYZ` or `ASX: XYZ`) that the app doesn't track are looked up and, if there's
enough data, run through the same models under **Found in online discussions**.

To add an investment or change the research, edit `universe.py`.

## Limits
- X/Twitter and Facebook groups can't be read without a login or paid API, and HotCopper blocks automated
  readers, so they aren't scanned. Bluesky (where much of finance Twitter moved) and StockTwits are used instead.
- StockTwits doesn't cover the ASX, so it's only used for crypto and companies also listed in the US (BHP, RIO, WDS).
- Reddit limits how often it can be read. A full scan takes about 4 minutes, longer if Reddit is rate-limiting,
  and some searches may be skipped. Results are cached in `data/`.
- Models describe the past. They can't predict the future, and a good score isn't a guarantee.
- This is general information, not financial advice.
