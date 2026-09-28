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
| Opportunities | Every tracked investment, ranked 0-100 with live prices. Click one for its chart, what people say, and its risks. |
| Check a portfolio | Paste someone's holdings (`CBA 3000`, `Bitcoin 1500`...). You get a grade A-F and a list of red flags. |
| My money | Log your real purchases and watch the value chart grow. Saved in `data/my_portfolio.json`. |
| Community pulse | Scans Reddit (r/fiaustralia, r/AusFinance, r/ASX_Bets, r/ausstocks) and Google News, then scores the mood. |
| Basics | The Australian essentials: CHESS brokers, the $500 minimum, franking credits, CGT, scams. |

## How the score works
`score = 40% quality + 30% risk-adjusted returns + 30% sentiment - a small fee penalty`

- **Quality** is a hand-set rating in `universe.py`: diversification, fees, structure.
- **Returns** use 5-year returns including dividends, divided by volatility, with extra penalties for big
  crashes. Returns above 12%/yr count as 12%, so hot streaks aren't rewarded. Funds with short
  histories are pulled towards neutral.
- **Sentiment** starts from a baseline set by web research. It then moves with the live share of positive
  and negative Reddit posts and news headlines.
- Single stocks are capped at 60 and crypto at 35.

To add an investment or change the research, edit `universe.py`.

## Limits
- X/Twitter and Facebook can't be read without a login or paid API, so they aren't scanned directly.
- Reddit limits how often it can be read. A full scan takes about 2 minutes, and some searches may
  be skipped. Results are cached in `data/`.
- This is general information, not financial advice.
