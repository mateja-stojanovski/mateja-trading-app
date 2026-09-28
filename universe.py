"""
The list of investments the app knows about, plus the baseline conclusions from
web research (Sept 2026). Live data (prices, Reddit, news) is layered on top of this.

Fees are approximate management fees (% per year) at time of research - always
check the fund's PDS / website before buying.

bucket:
  core      - all-in-one diversified fund (one ETF = whole portfolio)
  au        - Australian shares
  global    - international shares
  defensive - bonds / cash ETFs (lower growth, lower swings)
  satellite - themed / concentrated, fine as a small slice
  stock     - a single company (more risk than a fund)
  spec      - speculative (crypto etc.) - small "fun money" only
"""

UNIVERSE = [
    # ---- all-in-one diversified -------------------------------------------------
    dict(ticker="DHHF", yahoo="DHHF.AX", name="Betashares Diversified All Growth", bucket="core",
         fee=0.19, holdings=8000, quality=92, baseline=86,
         what="~8,000 companies worldwide (Australia, US, other developed, emerging) in one ETF. 100% shares.",
         community="Very frequently recommended on r/fiaustralia as a single 'set-and-forget' fund. "
                   "Had the highest share of buy orders among the most-traded ASX ETFs in recent broker data.",
         cons="100% shares, so it will drop hard in a crash (30%+ is possible). No bonds cushioning it."),
    dict(ticker="VDHG", yahoo="VDHG.AX", name="Vanguard Diversified High Growth", bucket="core",
         fee=0.27, holdings=16000, quality=88, baseline=82,
         what="Vanguard's all-in-one: ~90% shares (Aus + global) and ~10% bonds. Rebalances itself.",
         community="The classic 'one ETF and chill' pick. Commonly compared with DHHF - VDHG is slightly "
                   "more expensive but has a small bond cushion.",
         cons="Higher fee than DHHF or a DIY VAS+VGS combo. Bonds slightly lower long-run growth."),

    # ---- Australian shares -------------------------------------------------------
    dict(ticker="VAS", yahoo="VAS.AX", name="Vanguard Australian Shares", bucket="au",
         fee=0.07, holdings=300, quality=86, baseline=84,
         what="Top 300 companies on the ASX. The most popular ASX ETF (~$18.7B invested).",
         community="The default 'Aussie half' of the VAS + VGS combo that r/fiaustralia loves. "
                   "Pays good dividends with franking credits (a tax perk for Australians).",
         cons="Only Australia (~2% of world markets) and heavy on banks + miners."),
    dict(ticker="A200", yahoo="A200.AX", name="Betashares Australia 200", bucket="au",
         fee=0.04, holdings=200, quality=87, baseline=80,
         what="Top 200 ASX companies at one of the lowest fees available.",
         community="Often suggested as a cheaper swap for VAS - near-identical performance.",
         cons="Same Australia-only concentration as VAS."),
    dict(ticker="IOZ", yahoo="IOZ.AX", name="iShares Core S&P/ASX 200", bucket="au",
         fee=0.05, holdings=200, quality=86, baseline=76,
         what="ASX 200 index fund from BlackRock/iShares.",
         community="Solid, cheap, less talked about than VAS/A200 but functionally the same thing.",
         cons="Australia-only."),
    dict(ticker="VHY", yahoo="VHY.AX", name="Vanguard Australian High Yield", bucket="au",
         fee=0.25, holdings=70, quality=70, baseline=62,
         what="ASX companies that pay high dividends.",
         community="Liked by people chasing income; the FI crowd usually says growth-focused "
                   "broad funds beat it for young long-term investors.",
         cons="Concentrated in banks/miners, higher fee, less growth."),

    # ---- global shares -------------------------------------------------------------
    dict(ticker="VGS", yahoo="VGS.AX", name="Vanguard MSCI International Shares", bucket="global",
         fee=0.18, holdings=1300, quality=88, baseline=85,
         what="~1,300 companies across the US, Japan, UK, Europe, Canada (developed markets ex-Australia).",
         community="The 'global half' of the famous VAS + VGS combo. The 2nd most traded ASX ETF.",
         cons="No emerging markets. Currency moves (AUD vs USD) affect returns."),
    dict(ticker="BGBL", yahoo="BGBL.AX", name="Betashares Global Shares", bucket="global",
         fee=0.08, holdings=1300, quality=89, baseline=78,
         what="Same idea as VGS (developed markets ex-Australia) at under half the fee.",
         community="Increasingly recommended as the cheaper VGS alternative.",
         cons="Newer fund with a shorter track record."),
    dict(ticker="IVV", yahoo="IVV.AX", name="iShares S&P 500", bucket="global",
         fee=0.04, holdings=500, quality=84, baseline=80,
         what="The 500 biggest US companies (Apple, Microsoft, Nvidia...). Very low fee.",
         community="Hugely popular - many argue the S&P 500 is all you need. Common 20-year pick in AU media.",
         cons="US only, and increasingly dominated by a handful of mega tech stocks."),
    dict(ticker="IWLD", yahoo="IWLD.AX", name="iShares Core MSCI World ex Australia ESG", bucket="global",
         fee=0.09, holdings=1300, quality=84, baseline=66,
         what="Developed-market global shares with ESG screens.",
         community="A cheaper low-key alternative to VGS; less discussed.",
         cons="ESG screening means slightly different holdings to the index."),

    # ---- defensive -------------------------------------------------------------------
    dict(ticker="VAF", yahoo="VAF.AX", name="Vanguard Australian Fixed Interest", bucket="defensive",
         fee=0.10, holdings=1000, quality=74, baseline=58,
         what="Australian government and corporate bonds. Smoother ride, lower returns.",
         community="Seen as useful for older/cautious investors; FI crowd mostly skips bonds when young.",
         cons="Bonds can still fall when interest rates rise (as in 2022). Low long-run growth."),
    dict(ticker="AAA", yahoo="AAA.AX", name="Betashares Australian High Interest Cash", bucket="defensive",
         fee=0.18, holdings=1, quality=66, baseline=55,
         what="Cash held in bank deposits, traded like a share. Barely moves.",
         community="Mostly suggested as a cash parking spot inside a brokerage account.",
         cons="A normal high-interest savings account usually pays about the same or more, with no brokerage."),

    # ---- satellites -------------------------------------------------------------------
    dict(ticker="NDQ", yahoo="NDQ.AX", name="Betashares Nasdaq 100", bucket="satellite",
         fee=0.48, holdings=100, quality=66, baseline=72,
         what="The 100 biggest non-financial Nasdaq companies - very tech heavy.",
         community="Extremely popular and has been a big winner. Common warning: it overlaps heavily "
                   "with IVV/VGS and is concentrated in tech, so keep it a slice not the whole pie.",
         cons="Higher fee, concentrated in tech, big drawdowns (fell ~30% in 2022)."),
    dict(ticker="VGE", yahoo="VGE.AX", name="Vanguard FTSE Emerging Markets", bucket="satellite",
         fee=0.48, holdings=5000, quality=70, baseline=58,
         what="Emerging markets - China, India, Taiwan, Brazil etc.",
         community="Used as a small add-on for extra diversification; long stretches of weak returns.",
         cons="Higher fee, political/currency risk, historically lagged developed markets."),
    dict(ticker="ETHI", yahoo="ETHI.AX", name="Betashares Global Sustainability Leaders", bucket="satellite",
         fee=0.59, holdings=200, quality=64, baseline=62,
         what="Global companies screened for ethics/climate.",
         community="The go-to pick for 'ethical investing' threads.",
         cons="High fee and concentrated in large tech."),
    dict(ticker="HACK", yahoo="HACK.AX", name="Betashares Global Cybersecurity", bucket="satellite",
         fee=0.67, holdings=40, quality=55, baseline=55,
         what="Cybersecurity companies worldwide.",
         community="Thematic - people like the story; FI forums warn thematic ETFs often underperform.",
         cons="Narrow theme, high fee."),
    dict(ticker="GOLD", yahoo="GOLD.AX", name="Global X Physical Gold", bucket="satellite",
         fee=0.40, holdings=1, quality=60, baseline=64,
         what="Physical gold bullion, priced in AUD.",
         community="Popular as a hedge after gold's big run; debated whether it's an investment or a safety blanket.",
         cons="Produces no income or earnings; long flat periods are normal."),
    dict(ticker="DFND", yahoo="DFND.AX", name="VanEck Global Defence", bucket="satellite",
         fee=0.65, holdings=30, quality=52, baseline=60,
         what="Global defence/aerospace companies.",
         community="Hot recent theme in AU media. Momentum-driven.",
         cons="Narrow, high fee, bought mostly on recent hype."),

    # ---- single companies (examples people ask about) -------------------------------
    dict(ticker="CBA", yahoo="CBA.AX", name="Commonwealth Bank", bucket="stock",
         fee=0.0, holdings=1, quality=58, baseline=40,
         what="Australia's largest bank.",
         community="Great business, but analysts and forums widely call it overvalued - "
                   "only ~8% of analysts rate it a buy and its P/E has been higher than Alphabet's.",
         cons="Single company, expensive vs earnings growth of ~2-3%. Already ~10% of VAS anyway."),
    dict(ticker="BHP", yahoo="BHP.AX", name="BHP Group", bucket="stock",
         fee=0.0, holdings=1, quality=58, baseline=58,
         what="World's biggest miner (iron ore, copper).",
         community="Seen as a solid dividend payer, but tied to China and commodity cycles.",
         cons="Cyclical - prices swing with iron ore. Already big in VAS."),
    dict(ticker="CSL", yahoo="CSL.AX", name="CSL Limited", bucket="stock",
         fee=0.0, holdings=1, quality=56, baseline=50,
         what="Global biotech (blood plasma, vaccines).",
         community="Former market darling; sentiment mixed after years of weak share price.",
         cons="Single company risk."),
    dict(ticker="WES", yahoo="WES.AX", name="Wesfarmers", bucket="stock",
         fee=0.0, holdings=1, quality=60, baseline=60,
         what="Bunnings, Kmart, Officeworks and more.",
         community="Viewed as a quality long-term compounder; often 'fully priced'.",
         cons="Single company risk; tied to Australian consumer spending."),

    # ---- speculative ------------------------------------------------------------------
    dict(ticker="BTC", yahoo="BTC-AUD", name="Bitcoin", bucket="spec",
         fee=0.0, holdings=1, quality=30, baseline=45,
         what="The largest cryptocurrency.",
         community="Divisive. Believers post big gains; the RBA has publicly warned Australians about "
                   "speculating on crypto. FI forums: fine as <5% 'fun money' only.",
         cons="Can fall 50-80%. No earnings or dividends. Scams are common around crypto."),
    dict(ticker="ETH", yahoo="ETH-AUD", name="Ethereum", bucket="spec",
         fee=0.0, holdings=1, quality=26, baseline=40,
         what="Second-largest cryptocurrency.",
         community="Same debate as Bitcoin, with even bigger swings.",
         cons="Extremely volatile; speculative."),
]

BY_TICKER = {u["ticker"]: u for u in UNIVERSE}

# Words people use for a ticker in casual posts
ALIASES = {
    "CBA": ["commbank", "commonwealth bank"],
    "BTC": ["bitcoin"],
    "ETH": ["ethereum"],
    "BHP": ["bhp"],
    "CSL": ["csl"],
    "WES": ["wesfarmers"],
    "GOLD": ["gold etf"],
}

BUCKET_LABEL = {
    "core": "All-in-one diversified",
    "au": "Australian shares",
    "global": "Global shares",
    "defensive": "Defensive (bonds/cash)",
    "satellite": "Themed / satellite",
    "stock": "Single company",
    "spec": "Speculative",
}

# Conclusions from the Sept 2026 web research - shown in the app and used as the baseline
RESEARCH = {
    "as_of": "2026-09-27",
    "macro": [
        "RBA cash rate is 4.35% with the big four banks expecting a hike to 4.60% at the 29 Sept 2026 meeting "
        "(inflation ~3.5%, still above target).",
        "The ASX 200 hit a record above 9,198 in Feb 2026, dropped ~8% in a month, and has since moved sideways "
        "around 8,550-9,000 (8,696 in mid-Sept).",
        "High-interest savings accounts pay ~5.25-5.8% ongoing (e.g. AMP GO Save 5.25%, ING bonus 5.40%) - "
        "a genuinely good, zero-risk return for money you want to watch go up steadily.",
    ],
    "consensus": [
        "Australian FI communities (r/fiaustralia, r/AusFinance) overwhelmingly favour low-fee, broad index ETFs "
        "held for 10+ years: DHHF or VDHG as one-fund options, or VAS + VGS/BGBL as a two-fund combo.",
        "Most-traded ASX ETFs by broker data: VAS (#1), VGS (#2), VDHG (#5), DHHF (#8). DHHF had ~89% buy orders.",
        "Common warnings: don't stock-pick with your first few thousand, avoid hype themes, keep crypto to small "
        "'fun money', don't sell in a crash, and keep an emergency fund in a savings account first.",
        "CBA is widely considered overvalued (~8% of analysts rate it a buy).",
        "Use a CHESS-sponsored broker so shares are held in your name (e.g. CMC Invest, Webull, Stake, Moomoo, "
        "CommSec, Pearler for ASX). Betashares Direct offers $0 brokerage but is custodial.",
        "The ASX requires a minimum $500 for your first purchase of any share/ETF.",
    ],
    "sources": [
        ("Top 10 most traded ASX ETFs (Tiger)", "https://www.itiger.com/news/2469990036"),
        ("VDHG vs DHHF", "https://bytesizefinance.substack.com/p/vdhg-vs-dhhf-which-investment-suits"),
        ("5 ASX ETFs to hold for 20 years (Motley Fool, Sept 2026)",
         "https://www.fool.com.au/2026/09/24/5-asx-etfs-for-aussie-investors-to-buy-and-hold-for-20-years/"),
        ("Where to invest $5,000 in ASX ETFs (Motley Fool)",
         "https://www.fool.com.au/2026/05/28/where-to-invest-5000-in-asx-etfs-in-june-2026/"),
        ("Canstar best ETFs 2026", "https://www.canstar.com.au/etfs/etfs-highest-return/"),
        ("Finder high-interest savings Sept 2026",
         "https://www.finder.com.au/savings-accounts/high-interest-savings-accounts"),
        ("Finder RBA cash rate predictions", "https://www.finder.com.au/rba-cash-rate"),
        ("ASX 200 2026 forecast (Mitrade)",
         "https://www.mitrade.com/au/insights/indices/indices-basic/asx-200-forecast-2026"),
        ("CBA overvalued (Market Index)",
         "https://it.tradingview.com/news/marketindex%3Ab164f403a094b%3A0-big-fund-managers-hate-cba-because-it-s-overvalued-but-the-trend-is-your-friend"),
        ("RBA warns on crypto", "https://investing.com/news/cryptocurrency-news/reserve-bank-warns-aussies-over-punting-on-fad-driven-cryptocurrencies-2684873"),
        ("Best CHESS-sponsored brokers (Finder)", "https://www.finder.com.au/share-trading/best-chess-sponsored-brokers"),
    ],
}

HISA_RATE = 0.0525  # a realistic ongoing savings rate without bonus hoops (Sept 2026)
