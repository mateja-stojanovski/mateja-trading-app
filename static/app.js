const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v, d = 0) => v == null ? "–" : (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString("en-AU", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v, d = 1, sign = false) => v == null ? "–" : (sign && v > 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
const big = v => v == null ? "–" : v >= 1e12 ? "$" + (v / 1e12).toFixed(1) + "T" : v >= 1e9 ? "$" + (v / 1e9).toFixed(1) + "B" : v >= 1e6 ? "$" + (v / 1e6).toFixed(0) + "M" : money(v);
const num = (v, d = 1) => v == null ? "–" : (+v).toFixed(d);
const cls = v => v == null ? "" : v >= 0 ? "up" : "down";
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const PALETTE = ["#2a9d8f", "#1f6feb", "#e9a23b", "#8e5cd9", "#d9480f", "#5c940d", "#c2255c"];
const TONE = { great: "--great", good: "--good", ok: "--ok", wait: "--wait", avoid: "--avoid" };
const toneCls = s => s >= 72 ? "great" : s >= 62 ? "good" : s >= 52 ? "ok" : s >= 42 ? "wait" : "avoid";

async function api(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}
const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// ------------------------------------------------------------------ "?" help: plain-English explanations
const HELP = {
  how: ["How the decision is made", `<p>Each investment gets three scores out of 100:</p><ul>
    <li><b>Models</b>: maths on 10 years of real prices and company data. How much it's likely to grow, how bumpy the ride is, how bad the falls have been, and whether it's cheap or expensive.</li>
    <li><b>Research &amp; crowd</b>: the app's research on investing sites plus what people are saying on Reddit, Bluesky, StockTwits and in the news.</li>
    <li><b>Final</b>: 60% models + 40% research &amp; crowd. For anything that wasn't researched it's 75% models + 25% the live chatter.</li></ul>
    <p>Anything with less than 3 years of prices isn't scored. It goes in <b>Not enough data</b> at the bottom.</p>`],
  kinds: ["ETFs, stocks and crypto", `<ul><li><b>ETF (exchange-traded fund)</b>: one purchase that owns a slice of hundreds or thousands of companies. Spreads your risk. What most beginners should build on.</li>
    <li><b>Stock (share)</b>: part-ownership of one company. It can do great, or badly, depending on that one business.</li>
    <li><b>Crypto</b>: a digital currency with no company, earnings or dividends behind it. Very big swings.</li></ul>`],
  decision: ["The decision", `<p>From the final score:</p><ul><li><b>Strong buy &amp; hold</b> (72+): a solid long-term holding.</li><li><b>Good buy</b> (62–71)</li><li><b>OK as a small slice</b> (52–61): fine alongside a core fund, not on its own.</li><li><b>Wait and watch</b> (42–51): the evidence is mixed or weak right now.</li><li><b>Avoid for now</b> (under 42)</li></ul><p>It's about holding for years, not quick trades.</p>`],
  final: ["Final score", `<p>Out of 100. It combines the models (the data) with the research and the crowd (what people think). Higher is better for a long-term investor.</p>`],
  model_score: ["Model score", `<p>What the numbers alone say, out of 100. It's built from six parts: expected growth, return for the risk taken, how bad the falls get, the current trend, how steady it's been, and fundamentals (fees for funds, profits and price for companies).</p>`],
  crowd: ["Research & crowd score", `<p>Half the app's research rating (diversification, fees, reputation) and half the mood online: the share of positive vs negative posts on Reddit, Bluesky, StockTwits and in news headlines.</p>`],
  agree: ["Models vs the crowd", `<p>Whether the hard data backs up what people are saying. If the models are more negative, the hype may be ahead of the numbers. If they're more positive, it may be underrated.</p>`],
  confidence: ["Confidence", `<p>How much to trust the model result. <b>High</b>: 8+ years of prices and normal swings. <b>Medium</b>: 5+ years. <b>Low</b>: a short history or wild swings (like crypto), so the numbers could easily be wrong.</p>`],
  size: ["How much to put in", `<p>Common guidance on how big a slice of your money this kind of investment should be. Even a great single company or coin can go badly, so keep those small.</p>`],
  growth: ["Expected growth", `<p>The yearly growth the models expect, <b>after</b> allowing for ups and downs. A bumpy investment grows slower than its average return suggests: lose 50% then gain 50% and you're down 25%.</p>
    <p>It uses a statistical trick called <b>shrinkage</b>: past returns are noisy, so they're pulled towards what investments with the same market exposure usually earn. Short or wild histories get pulled harder.</p>`],
  mu_hist: ["Past average return", `<p>The raw average yearly return over its history (up to 10 years). The models don't take this at face value. A lucky decade can look amazing and not repeat.</p>`],
  vol: ["Volatility (typical swing)", `<p>How much the price usually moves in a year, up or down. A broad share ETF is about 12–16%. A single company 20–35%. Crypto 60–130%. Higher means a bumpier ride.</p>`],
  mdd: ["Worst drop", `<p>The biggest fall from a peak to a low in its history. It shows how bad it has got before. You need to be able to sit through that without selling.</p>`],
  cvar: ["Bad-month loss (CVaR)", `<p>The average loss in its worst 5% of months (about one month in 20). A measure of how painful the bad times are.</p>`],
  ploss: ["Chance of being down after 5 years", `<p>From a standard model of how prices move (lognormal), using the expected growth and volatility. It's an estimate, not a promise.</p>`],
  band: ["$1,000 in 5 years", `<p>What $1,000 might turn into in 5 years. The middle mark is the most likely outcome. The bar runs from a bad case (1 in 10 chance of worse) to a good case (1 in 10 chance of better).</p>`],
  beta: ["Market sensitivity (beta)", `<p>How much it moves when the market moves. 1.0 means it moves with the market. 1.5 means about 50% more. 0 means it ignores the market. Measured against both Australian (VAS) and US (IVV) shares with a regression.</p>`],
  alpha: ["Extra return (alpha)", `<p>Return the market <b>doesn't</b> explain, per year. The "t" number says whether it's real or luck. Below about 2 is probably luck.</p>`],
  r2: ["How much the market explains (R²)", `<p>From 0% to 100%: how much of its ups and downs are just the overall market. Near 100% means it's basically the market. Low means its own story drives it.</p>`],
  trend: ["Long-run trend", `<p>A straight line fitted through the price on a log scale over 10 years. <b>Steadiness</b> is how closely the price followed that line (100% is perfectly steady). <b>Position</b> says whether it's now above or below the line. Far above can mean it's stretched.</p>`],
  momentum: ["Momentum", `<p>Its return over the past 12 months, skipping the latest month. Investments going up have tended to keep going up for a while. It's one of the most-studied patterns in finance.</p>`],
  ma10: ["10-month average", `<p>Whether today's price is above its average of the last 10 months. Above means an uptrend. A well-known simple trend rule.</p>`],
  sharpe: ["Return for the risk (Sharpe)", `<p>The expected return above a savings account, divided by volatility. Higher is better. About 0.4+ is good for shares.</p>`],
  sortino: ["Return for the downside (Sortino)", `<p>Like Sharpe, but it only counts downward swings as risk.</p>`],
  upyears: ["Up after 12 months", `<p>How often, historically, it was higher 12 months later than it was before.</p>`],
  pe: ["P/E ratio", `<p>Share price divided by yearly profit per share. How many years of profit you pay for. About 15 is cheap-ish, 25+ is expensive. Forward P/E uses next year's expected profit.</p>`],
  dy: ["Dividend yield", `<p>Cash paid out each year as a % of the price. Aussie companies often add franking credits (tax already paid) on top.</p>`],
  roe: ["Return on equity", `<p>Profit as a % of the owners' money in the business. How efficiently it makes money. 15%+ is strong.</p>`],
  margin: ["Profit margin", `<p>How many cents of every dollar of sales end up as profit.</p>`],
  revg: ["Revenue growth", `<p>How much sales grew compared with a year earlier.</p>`],
  earng: ["Earnings growth", `<p>How much profit grew compared with a year earlier.</p>`],
  de: ["Debt to equity", `<p>How much it has borrowed compared with what the owners put in. Lower is safer. Banks naturally carry a lot, so it isn't shown for them.</p>`],
  analysts: ["Analyst rating", `<p>The average view of professional analysts, from 1 (strong buy) to 5 (sell). Analysts are often wrong, but a strong consensus is worth knowing.</p>`],
  target: ["Price target", `<p>Where analysts on average think the price will be in about 12 months, and how far that is from today's price.</p>`],
  mcap: ["Market value", `<p>What the whole company or coin is worth at today's price.</p>`],
  fee: ["Fee (management cost)", `<p>Taken from the fund each year, as a % of your money. 0.2% on $10,000 is $20 a year. Low fees matter a lot over decades.</p>`],
  fundsize: ["Fund size", `<p>How much money is invested in the fund. Big funds are cheap to trade and unlikely to close.</p>`],
  holdings: ["Holdings", `<p>How many different companies (or bonds) the fund owns. More means more spread out.</p>`],
  cgrank: ["Market-cap rank", `<p>Where this coin ranks by total value among all cryptocurrencies. Bigger coins are more established, not safer.</p>`],
  ath: ["Below all-time high", `<p>How far the price is below the highest it has ever been.</p>`],
  feargreed: ["Crypto Fear & Greed index", `<p>A daily 0–100 gauge of the crypto market's mood (from alternative.me). Extreme greed often comes before falls, and extreme fear before recoveries.</p>`],
  sentiment: ["What people are saying", `<p>Posts that mention it are read automatically and counted as positive or negative from their wording. StockTwits posters label their own posts Bullish or Bearish. It shows the mood, not whether it's a good investment.</p>`],
  sources: ["Where the chatter comes from", `<ul><li><b>Reddit</b>: Australian investing and crypto communities.</li><li><b>Bluesky</b>: where much of finance Twitter moved. Its search is free and open.</li><li><b>StockTwits</b>: a Twitter-style network just for traders. It only covers crypto and US-listed shares.</li><li><b>Google News</b>: Australian headlines.</li></ul>
    <p><b>X/Twitter, Facebook groups and HotCopper</b> can't be read. They need a paid API or a login, or they block automated readers.</p>`],
  nodata: ["Not enough data", `<p>These came up in the research or in online discussions, but there's less than 3 years of prices, or no data at all. The models would just be guessing, so they aren't scored. That isn't a judgement that they're bad.</p>`],
  found: ["Found in online discussions", `<p>Tickers people mentioned in the latest scan that the app doesn't normally track. If there's enough data, they get the same models. They weren't researched, so read up before buying.</p>`],
  c_growth: ["Growth", `<p>Scores the expected growth after ups and downs. About 10% a year or more gets full marks.</p>`],
  c_riskadj: ["Return for the risk", `<p>Scores the Sharpe ratio: how much return you get for each unit of bumpiness.</p>`],
  c_downside: ["Downside", `<p>Scores how bad the worst drop and the worst months have been. Smaller falls score higher.</p>`],
  c_trend: ["Trend", `<p>Scores momentum and whether it's above its 10-month average, with a penalty if it's stretched far above its long-run trend.</p>`],
  c_steady: ["Steadiness", `<p>Scores how often it was up after 12 months and how steadily it followed its long-run trend.</p>`],
  c_fundamentals: ["Fundamentals", `<p>Companies: cheap or expensive vs profits, how profitable, growth, debt and analyst views. Funds: fee, size and how spread out. Crypto: only its size. It has no profits to value, so it scores low here.</p>`],
  profile: ["How much swing can you stomach?", `<p>Shares go down as well as up. <b>Cautious</b> keeps more in cash and bonds, so it's smoother but grows slower. <b>Growth</b> is nearly all shares, so it's bumpier but grows faster over 10+ years. Choose the one you'd stick with during a 30% drop.</p>`],
  plan_return: ["Expected long-run return", `<p>The yearly growth the models expect for this mix after ups and downs, capped to stay on the careful side. Real years will be above and below this.</p>`],
  projection: ["Projection", `<p>Where your money could be if you keep adding each month. The middle line uses the expected return. The dashed lines show a poor stretch (3% a year lower) and a good one.</p>`],
  backtest: ["Backtest", `<p>What would have happened if you'd started this exact plan 5 years ago, using real prices including dividends. It shows the dips you'd have sat through.</p>`],
  grade: ["Portfolio grade", `<p>A to F for long-term investing: how spread out it is, fees, how much is in single companies or crypto, overlap between holdings, and what the models say about each one.</p>`],
  mix: ["Mix", `<p>How the money splits between broad funds (spread out), single companies and speculative assets like crypto.</p>`],
  worth: ["Your numbers", `<p><b>Worth now</b> uses the latest price. <b>Total gain</b> is worth minus what you paid, including brokerage. <b>Latest change</b> is since the previous data point.</p>`],
  add_purchase: ["Adding a purchase", `<p>Enter the ticker (e.g. DHHF), how many units you bought, the price per unit and any brokerage fee. For a savings account, enter the amount and interest rate.</p>`],
  buzz: ["Buzz by investment", `<p>How often each investment came up on each platform, and the share of posts that sounded positive (green) vs negative (red).</p>`],
  trending: ["Other tickers people mention", `<p>ASX codes written like $XYZ or ASX: XYZ in the posts. The Opportunities tab runs these through the models when there's enough data.</p>`],
  chess: ["CHESS sponsorship", `<p>The ASX's register of who owns which shares. With a CHESS-sponsored broker the shares are in your name, not the broker's, so they're safe if the broker goes bust.</p>`],
};
function help(key) { return `<button class="q" data-help="${key}" type="button" aria-label="What does this mean?">?</button>`; }
const pop = $("#pop");
function closePop() { pop.hidden = true; pop.dataset.for = ""; }
document.addEventListener("click", e => {
  const b = e.target.closest(".q");
  if (b) {
    e.preventDefault(); e.stopPropagation();
    if (pop.dataset.for === b.dataset.help && !pop.hidden) return closePop();
    const [t, body] = HELP[b.dataset.help] || ["", ""];
    pop.innerHTML = `<div class="pop-h"><b>${esc(t)}</b><button class="pop-x" aria-label="Close">×</button></div><div class="pop-b">${body}</div>`;
    pop.hidden = false; pop.dataset.for = b.dataset.help;
    const r = b.getBoundingClientRect(), w = Math.min(340, innerWidth - 24);
    pop.style.width = w + "px";
    pop.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left + r.width / 2 - w / 2)) + "px";
    const below = r.bottom + 8, h = pop.offsetHeight;
    pop.style.top = (below + h > innerHeight - 8 && r.top - h - 8 > 8 ? r.top - h - 8 : Math.min(below, innerHeight - h - 8)) + "px";
    return;
  }
  if (!e.target.closest("#pop") || e.target.closest(".pop-x")) closePop();
}, true);
addEventListener("scroll", closePop, true);

// ------------------------------------------------------------------ charts
function sparkline(vals, w = 140, h = 36) {
  vals = (vals || []).filter(v => v != null);
  if (vals.length < 2) return "";
  const mn = Math.min(...vals), mx = Math.max(...vals), rg = mx - mn || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - mn) / rg * (h - 4)).toFixed(1)}`).join(" ");
  const col = vals.at(-1) >= vals[0] ? css("--up") : css("--down");
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/></svg>`;
}

// series: [{label, t:[ms], v:[num], color, dash, fill}]
function lineChart(el, series, { fmtY = v => money(v), fmtX = t => new Date(t).toLocaleDateString("en-AU", { month: "short", year: "2-digit" }), logY = false } = {}) {
  el.innerHTML = "";
  const all = series.flatMap(s => s.v.filter(v => v != null && (!logY || v > 0)));
  if (!all.length) { el.innerHTML = `<div class="loading">No data yet</div>`; return; }
  const f = logY ? Math.log : v => v, fi = logY ? Math.exp : v => v;
  const W = el.clientWidth || 700, H = el.clientHeight || 220, L = 64, R = 12, T = 10, B = 26;
  const ts = series.flatMap(s => s.t);
  const x0 = Math.min(...ts), x1 = Math.max(...ts);
  let y0 = f(Math.min(...all)), y1 = f(Math.max(...all));
  const pad = (y1 - y0) * 0.08 || Math.abs(y1) * 0.05 || 1; y0 = !logY && Math.min(...all) >= 0 ? Math.max(0, y0 - pad) : y0 - pad; y1 += pad;
  const X = t => L + (t - x0) / ((x1 - x0) || 1) * (W - L - R);
  const Y = v => T + (1 - (f(v) - y0) / (y1 - y0)) * (H - T - B);
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = fi(y0 + (y1 - y0) * i / 4), y = Y(v);
    g += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="${css("--chart-grid")}"/><text x="${L - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="${css("--muted")}">${esc(fmtY(v))}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const t = x0 + (x1 - x0) * i / 4;
    g += `<text x="${X(t)}" y="${H - 6}" text-anchor="${i === 0 ? "start" : i === 4 ? "end" : "middle"}" font-size="11" fill="${css("--muted")}">${esc(fmtX(t))}</text>`;
  }
  for (const s of series) {
    const pts = s.t.map((t, i) => s.v[i] == null ? null : [X(t), Y(s.v[i])]).filter(Boolean);
    if (!pts.length) continue;
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
    if (s.fill) g += `<path d="${d}L${pts.at(-1)[0]},${H - B}L${pts[0][0]},${H - B}Z" fill="${s.color}" opacity=".10"/>`;
    g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2.2}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} stroke-linejoin="round"/>`;
  }
  const wrap = document.createElement("div");
  wrap.className = "chartwrap"; wrap.style.height = "100%";
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${g}<line class="hl" y1="${T}" y2="${H - B}" stroke="${css("--muted")}" stroke-dasharray="3 3" visibility="hidden"/></svg><div class="tip" hidden></div>`;
  el.appendChild(wrap);
  const tip = $(".tip", wrap), hl = $(".hl", wrap), svg = $("svg", wrap), main = series[0];
  const nearest = (s, t) => { let bi = 0, bd = 1e18; s.t.forEach((x, i) => { const d = Math.abs(x - t); if (d < bd) { bd = d; bi = i; } }); return bi; };
  svg.addEventListener("mousemove", e => {
    const r = svg.getBoundingClientRect(), mx = (e.clientX - r.left) / r.width * W;
    const t = x0 + (mx - L) / (W - L - R) * (x1 - x0), bi = nearest(main, t), px = X(main.t[bi]);
    hl.setAttribute("x1", px); hl.setAttribute("x2", px); hl.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.style.left = (px / W * r.width) + "px"; tip.style.top = (Y(main.v[bi]) / H * r.height) + "px";
    tip.innerHTML = `${esc(new Date(main.t[bi]).toLocaleDateString("en-AU"))} · ` +
      series.map(s => `${esc(s.label)} <b>${esc(fmtY(s.v[nearest(s, main.t[bi])]))}</b>`).join(" · ");
  });
  svg.addEventListener("mouseleave", () => { tip.hidden = true; hl.setAttribute("visibility", "hidden"); });
}
const legend = items => `<div class="legend">${items.map(([l, c, dash]) => `<span><i style="background:${c};${dash ? "opacity:.6" : ""}"></i>${esc(l)}</span>`).join("")}</div>`;

// ------------------------------------------------------------------ tabs
const loaded = {};
function showTab(id) {
  $$("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === id));
  $$(".tab").forEach(t => t.classList.toggle("on", t.id === id));
  try { localStorage.setItem("tab", id); } catch {}
  if (!loaded[id]) { loaded[id] = true; ({ plan: buildPlan, opps: loadOpps, mine: loadMine, pulse: loadPulse })[id]?.(); }
}
$$("#tabs button").forEach(b => b.onclick = () => showTab(b.dataset.tab));

// ------------------------------------------------------------------ plan
async function buildPlan() {
  const out = $("#plan-out"), btn = $("#p-go");
  const amount = +$("#p-amount").value || 0, monthly = +$("#p-monthly").value || 0;
  const profile = $("#p-profile").value, simple = $("#p-simple").checked ? 1 : 0;
  btn.disabled = true; out.innerHTML = `<div class="loading">Crunching live data…</div>`;
  try {
    const p = await api(`/api/plan?amount=${amount}&monthly=${monthly}&profile=${profile}&simple=${simple}`);
    const bar = p.lines.map((l, i) => `<span style="width:${l.weight * 100}%;background:${PALETTE[i]}" title="${esc(l.ticker)}"></span>`).join("");
    const items = p.lines.map((l, i) => `
      <div class="line-item"><span class="dot" style="background:${PALETTE[i]}"></span>
        <div><b>${esc(l.ticker)}</b> <span class="muted">${esc(l.name)}</span><span class="tag">${esc(l.bucket_label)}</span>
          ${l.decision ? `<span class="tag t-${toneCls(l.score)}">${esc(l.decision)} · ${l.score}</span>` : ""}${l.fee != null ? `<span class="tag">fee ${l.fee}%</span>` : ""}
          <div class="muted" style="font-size:13.5px">${esc(l.why)}</div></div>
        <div class="num" style="text-align:right"><b>${money(l.amount)}</b><div class="muted">${pct(l.weight, 0)}</div></div>
      </div>`).join("");
    const years = 20, r = p.exp_return;
    const proj = (rate) => { const t = [], v = []; let bal = amount; const now = Date.now();
      for (let m = 0; m <= years * 12; m++) { if (m) bal = bal * (1 + rate) ** (1 / 12) + monthly; if (m % 3 === 0) { t.push(now + m * 2.63e9); v.push(bal); } } return { t, v }; };
    const mid = proj(r), lo = proj(Math.max(0, r - 0.03)), hi = proj(r + 0.025);
    const contrib = { t: mid.t, v: mid.t.map((_, i) => amount + monthly * i * 3) };
    const at = (s, y) => s.v[Math.min(s.v.length - 1, y * 4)];
    out.innerHTML = `
      <div class="grid2">
        <div class="card"><h2 style="margin-top:0">Your split</h2><div class="alloc">${bar}</div>${items}
          ${p.notes.map(n => `<div class="flag warn">${esc(n)}</div>`).join("")}</div>
        <div class="card"><h2 style="margin-top:0">What to do next</h2>
          <ol style="padding-left:18px;margin:0">
            <li>Open a high-interest savings account for the cash part (look for ~5.25%+ with no hoops, or a bonus rate you'll actually meet).</li>
            <li>Open a <b>CHESS-sponsored</b> broker account ${help("chess")} (CMC Invest, Webull, Stake, Moomoo, Pearler or CommSec are popular and cheap for ETFs).</li>
            <li>Buy the ETFs above in one go, or spread it over 2–3 months if a drop right after buying would upset you.</li>
            <li>Set up an automatic ${monthly ? money(monthly) : "monthly"} deposit and top up the same split.</li>
            <li>Log each purchase in <a href="#" onclick="showTab('mine');return false">My money</a> to watch it grow.</li>
            <li>Don't sell because of a scary headline. Check in every few months, not every day.</li>
          </ol></div>
      </div>
      <div class="grid3">
        <div class="stat"><div class="k">Expected long-run return ${help("plan_return")}</div><div class="v">${pct(r)}</div><div class="s muted">per year (careful estimate)</div></div>
        <div class="stat"><div class="k">In 10 years (likely range)</div><div class="v">${money(at(mid, 10))}</div><div class="s muted">${money(at(lo, 10))} – ${money(at(hi, 10))}</div></div>
        <div class="stat"><div class="k">In 20 years (likely range)</div><div class="v">${money(at(mid, 20))}</div><div class="s muted">${money(at(lo, 20))} – ${money(at(hi, 20))}</div></div>
        <div class="stat"><div class="k">You'd have put in (20y)</div><div class="v">${money(amount + monthly * 240)}</div><div class="s muted">the rest is growth</div></div>
      </div>
      <div class="card"><h2 style="margin-top:0">Projection: next 20 years ${help("projection")}</h2><div id="proj" class="chart tall"></div>
        ${legend([["Expected", css("--up")], ["Poor decade(s)", css("--down"), 1], ["Good decade(s)", css("--accent"), 1], ["Money you put in", css("--chart-2")]])}
        <p class="muted" style="font-size:13px">Smooth lines show averages. Real balances zig-zag and will have down years. The "poor" line assumes returns 3%/yr below expected.</p></div>
      ${p.backtest ? `<div class="card"><h2 style="margin-top:0">If you'd started this plan 5 years ago ${help("backtest")}</h2><div id="bt" class="chart tall"></div>
        ${legend([["Your balance (real prices, incl. dividends)", css("--up")], ["Money you put in", css("--chart-2")]])}
        <p class="muted" style="font-size:13px">Put in ${money(p.backtest.contributed)} → would be worth <b class="${cls(p.backtest.value.at(-1) - p.backtest.contributed)}">${money(p.backtest.value.at(-1))}</b>. Notice the dips along the way. That's normal.</p></div>` : ""}`;
    lineChart($("#proj"), [
      { label: "Expected", ...mid, color: css("--up"), fill: true, width: 2.6 },
      { label: "Poor", ...lo, color: css("--down"), dash: "5 4", width: 1.6 },
      { label: "Good", ...hi, color: css("--accent"), dash: "5 4", width: 1.6 },
      { label: "Put in", ...contrib, color: css("--chart-2"), width: 1.6 },
    ], { fmtX: t => new Date(t).getFullYear() });
    if (p.backtest) {
      const bt = p.backtest, t = bt.t.map(x => x * 1000);
      lineChart($("#bt"), [
        { label: "Balance", t, v: bt.value, color: css("--up"), fill: true },
        { label: "Put in", t, v: t.map((_, i) => amount + monthly * i), color: css("--chart-2"), width: 1.6 },
      ]);
    }
  } catch (e) { out.innerHTML = `<div class="flag bad">Couldn't build plan: ${esc(e.message)}</div>`; }
  btn.disabled = false;
}
$("#p-go").onclick = buildPlan;

// ------------------------------------------------------------------ opportunities
const KINDS = [
  ["etf", "ETFs & funds", "One purchase, hundreds of companies", `<svg viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>`],
  ["stock", "Stocks", "Single companies", `<svg viewBox="0 0 24 24"><path d="M4 21V8l8-5 8 5v13M9 21v-6h6v6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/></svg>`],
  ["crypto", "Crypto", "Digital coins: very high risk", `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M9.5 7.5h4a2.2 2.2 0 0 1 0 4.5h-4zm0 4.5h4.6a2.3 2.3 0 0 1 0 4.5H9.5zM11 6v2M11 16.5v2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`],
];
const GROUPS = {
  etf: [["core", "All-in-one funds", "One fund can be your whole portfolio"], ["au", "Australian shares", "The ASX's biggest companies"], ["global", "Global shares", "Companies around the world"],
    ["satellite", "Themed & extras", "Narrower bets: keep them small"], ["defensive", "Defensive (bonds & cash)", "Smoother, lower growth"], ["found", "Found in online discussions", "Mentioned online, not researched"]],
  stock: [["researched", "Researched companies", "Covered by the app's research"], ["added", "More companies people discuss", "Judged on the models and the live scan"], ["found", "Found in online discussions", "Mentioned online, not researched"]],
  crypto: [["all", "Coins", "Keep all crypto under ~5% of your money"]],
};
let OPP = null, oppKind = "etf", oppSort = "score";
try { oppKind = localStorage.getItem("oppKind") || "etf"; } catch {}
async function loadOpps() {
  try {
    OPP = await api("/api/assets");
    $("#opp-meta").innerHTML = `Prices: live · Community scan: ${esc(OPP.sentiment_at || "not run yet")}`;
    renderOpps();
  } catch (e) { $("#opp-list").innerHTML = `<div class="flag bad">${esc(e.message)}</div>`; }
}
function groupOf(a) {
  if (a.kind === "etf") return a.bucket;
  if (a.kind === "stock") return a.discovered ? "found" : a.researched ? "researched" : "added";
  return "all";
}
const sorters = {
  score: (a, b) => b.score - a.score,
  model: (a, b) => b.model_score - a.model_score,
  growth: (a, b) => (b.model.expected.reliable - a.model.expected.reliable) || b.model.expected.growth - a.model.expected.growth,
  risk: (a, b) => a.model.expected.vol - b.model.expected.vol,
};
function renderOpps() {
  const A = OPP.assets;
  $("#kindtabs").innerHTML = KINDS.map(([k, l, sub, ic]) => {
    const list = A.filter(a => a.kind === k), top = [...list].sort(sorters.score)[0];
    return `<button class="kindtab k-${k} ${k === oppKind ? "on" : ""}" data-k="${k}"><span class="ki">${ic}</span>
      <span class="kt"><b>${l}</b><small>${sub}</small></span><span class="kc">${list.length}</span>
      ${top ? `<span class="ktop">Top: <b>${esc(top.ticker)}</b> · ${esc(top.decision.label)}</span>` : ""}</button>`;
  }).join("");
  $$(".kindtab").forEach(b => b.onclick = () => { oppKind = b.dataset.k; try { localStorage.setItem("oppKind", oppKind); } catch {} renderOpps(); });

  const list = A.filter(a => a.kind === oppKind);
  const fg = OPP.fear_greed;
  $("#opp-intro").innerHTML = oppKind === "crypto" ? `<div class="banner b-crypto"><div><b>Crypto is the riskiest thing here.</b> Prices can halve in months, there are no profits or dividends behind them, and scams are common. Common guidance: keep all crypto under about 5% of your money. ${help("kinds")}</div>
      ${fg ? `<div class="fg"><div class="fg-v" style="--p:${fg.value}"><span>${fg.value}</span></div><div><b>${esc(fg.label)}</b><small>Crypto Fear &amp; Greed ${help("feargreed")}</small></div></div>` : ""}</div>`
    : oppKind === "stock" ? `<div class="banner b-stock"><div><b>Single companies carry more risk than a fund.</b> One bad result can knock 30% off. Even the best ones here are better as small extras on top of a core ETF. ${help("kinds")}</div></div>`
    : `<div class="banner b-etf"><div><b>ETFs are where most beginners start.</b> One purchase spreads your money across hundreds or thousands of companies. ${help("kinds")}</div></div>`;

  const top = [...list].sort(sorters.score).filter(a => a.decision.tone !== "avoid").slice(0, 3);
  let html = `<h2 class="sec">Top picks right now ${help("decision")}</h2>` + (top.length ? `<div class="toppicks">${top.map(topCard).join("")}</div>`
    : `<div class="card muted">Nothing here scores well enough to recommend right now.</div>`);
  html += `<div class="legendrow"><span><i class="lg great"></i>Strong buy &amp; hold</span><span><i class="lg good"></i>Good buy</span><span><i class="lg ok"></i>Small slice</span><span><i class="lg wait"></i>Wait</span><span><i class="lg avoid"></i>Avoid</span></div>`;
  for (const [g, label, sub] of GROUPS[oppKind]) {
    const rows = list.filter(a => groupOf(a) === g).sort(sorters[oppSort]);
    if (!rows.length) continue;
    html += `<h2 class="sec">${esc(label)} <small>${esc(sub)}</small>${g === "found" ? " " + help("found") : ""}</h2><div class="list">${rows.map(oppRow).join("")}</div>`;
  }
  $("#opp-list").innerHTML = html || `<div class="loading">Nothing here yet.</div>`;

  const nd = OPP.no_data || [];
  $("#opp-nodata").innerHTML = nd.length ? `<details class="card nodata"><summary><b>Not enough data to judge (${nd.length})</b> ${help("nodata")} <span class="muted small">— came up in research or discussions but can't be run through the models</span></summary>
    ${nd.map(x => `<div class="ndrow"><b>${esc(x.ticker)}</b> <span class="muted">${esc(x.name !== x.ticker ? x.name : "")}</span>${x.discovered ? `<span class="tag">mentioned ${x.mentions}× online</span>` : ""}
      <div class="small">${esc(x.reason)}</div>${(x.samples || []).slice(0, 2).map(p => `<div class="small"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <span class="muted">${esc(p.source)}</span></div>`).join("")}</div>`).join("")}</details>` : "";
  $$(".opp, .topcard").forEach(el => el.onclick = e => { if (!e.target.closest(".q")) openAsset(A.find(a => a.ticker === el.dataset.t)); });
}
$$("#opp-sort button").forEach(b => b.onclick = () => { oppSort = b.dataset.s; $$("#opp-sort button").forEach(x => x.classList.toggle("on", x === b)); if (OPP) renderOpps(); });

function ring(score, size = 58) {
  const r = size / 2 - 5, c = 2 * Math.PI * r, t = toneCls(score);
  return `<span class="ring t-${t}" style="width:${size}px;height:${size}px"><svg viewBox="0 0 ${size} ${size}"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" class="rb"/><circle cx="${size / 2}" cy="${size / 2}" r="${r}" class="rf" stroke-dasharray="${(c * score / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/></svg><b>${score}</b></span>`;
}
const decPill = a => `<span class="dec t-${a.decision.tone}">${esc(a.decision.label)}</span>`;
const agreeChip = a => `<span class="agree a-${a.agreement.dir}">${{ same: "✓ Models agree with the crowd", up: "▲ Models more positive than the crowd", down: "▼ Models more negative than the crowd", none: "Models + live scan only" }[a.agreement.dir]}</span>`;
const growthTxt = e => e.reliable ? pct(e.growth) : "Too wild";
const oneYear = a => a.spark?.length > 1 ? a.spark.at(-1) / a.spark[0] - 1 : null;
function topCard(a, i) {
  const e = a.model.expected;
  return `<div class="topcard t-${a.decision.tone}" data-t="${esc(a.ticker)}"><div class="rank">#${i + 1}</div>
    <div class="row" style="gap:12px;flex-wrap:nowrap">${ring(a.score, 64)}<div style="min-width:0"><div class="t">${esc(a.ticker)}</div><div class="n">${esc(a.name)}</div></div></div>
    ${decPill(a)}<div class="tc-stats"><div><span>Growth</span><b>${growthTxt(e)}</b></div><div><span>Worst drop</span><b class="down">${pct(a.model.risk.mdd, 0)}</b></div><div><span>Loss chance 5y</span><b>${e.reliable ? pct(e.p_loss, 0) : "?"}</b></div></div>
    <div class="spk">${sparkline(a.spark, 240, 42)}</div></div>`;
}
function oppRow(a) {
  const e = a.model.expected, m = a.model;
  return `<div class="opp t-${a.decision.tone}" data-t="${esc(a.ticker)}">
    <div>${ring(a.score)}</div>
    <div class="o-main"><div><span class="t">${esc(a.ticker)}</span> ${decPill(a)}${!a.researched ? `<span class="tag">${a.discovered ? "found online" : "not researched"}</span>` : ""}</div>
      <div class="n">${esc(a.name)}</div><div class="o-size">${esc(a.size_hint)}</div>${agreeChip(a)}</div>
    <div class="o-stats hide-sm">
      <div><span>Expected growth</span>${e.reliable ? `<b class="${cls(e.growth)}">${pct(e.growth)}<small>/yr</small></b>` : `<b class="down">Too wild</b>`}</div>
      <div><span>Typical swing</span><b>±${pct(e.vol, 0)}</b></div>
      <div><span>Worst drop</span><b class="down">${pct(m.risk.mdd, 0)}</b></div>
      <div><span>Confidence</span><b class="conf c-${m.confidence}">${m.confidence}</b></div>
    </div>
    <div class="o-price"><b>${money(a.price, a.price < 10 ? 3 : 2)}</b><div class="${cls(a.day_change)} small">${pct(a.day_change, 2, true)} today</div>
      <div class="hide-sm">${sparkline(a.spark, 120, 30)}</div><div class="small ${cls(oneYear(a))} hide-sm">${pct(oneYear(a), 0, true)} past year</div></div>
  </div>`;
}

// the detail view
const good = (v, lo, hi) => v == null ? "" : v >= hi ? "gd" : v <= lo ? "bd" : "";
function mrow(label, key, value, meaning, tone = "") { return `<tr><td>${esc(label)} ${help(key)}</td><td class="r num ${tone}"><b>${value}</b></td><td class="muted small">${meaning}</td></tr>`; }
function compBars(c) {
  const names = { growth: "Growth", riskadj: "Return for the risk", downside: "Downside", trend: "Trend", steady: "Steadiness", fundamentals: "Fundamentals" };
  return Object.entries(names).map(([k, l]) => `<div class="cbar"><span>${l} ${help("c_" + k)}</span><div class="bar"><i class="t-${toneCls(c[k] ?? 0)}" style="width:${c[k] ?? 0}%"></i></div><b class="num">${c[k] ?? "–"}</b></div>`).join("");
}
function fundBlock(a) {
  const f = a.fundamentals || {};
  if (a.kind === "stock") {
    const recTxt = f.rec_mean ? `${num(f.rec_mean, 1)} <small>(${esc((f.rec_key || "").replace("_", " "))}, ${f.analysts || 0} analysts)</small>` : "–";
    return `<table class="mt">
      ${mrow("P/E (price ÷ profit)", "pe", f.pe ? num(f.pe, 1) : "–", f.forward_pe ? `Forward: ${num(f.forward_pe, 1)}. ${f.forward_pe > 25 ? "Expensive." : f.forward_pe < 15 ? "Cheap-ish." : "Middling."}` : "", f.forward_pe ? (f.forward_pe > 25 ? "bd" : f.forward_pe < 15 ? "gd" : "") : "")}
      ${mrow("Dividend yield", "dy", pct(f.div_yield), "Cash paid each year (before franking)")}
      ${mrow("Return on equity", "roe", pct(f.roe), "How efficiently it makes profit", good(f.roe, 0.06, 0.15))}
      ${mrow("Profit margin", "margin", pct(f.margin), "Profit per dollar of sales", good(f.margin, 0.03, 0.15))}
      ${mrow("Revenue growth", "revg", pct(f.rev_growth, 1, true), "Sales vs a year ago", good(f.rev_growth, -0.01, 0.08))}
      ${mrow("Earnings growth", "earng", pct(f.earn_growth, 1, true), "Profit vs a year ago", good(f.earn_growth, -0.02, 0.10))}
      ${f.debt_equity != null ? mrow("Debt to equity", "de", num(f.debt_equity / 100, 2), "Borrowing vs owners' money", f.debt_equity > 150 ? "bd" : f.debt_equity < 50 ? "gd" : "") : ""}
      ${mrow("Analyst rating", "analysts", recTxt, "1 = strong buy … 5 = sell", f.rec_mean ? (f.rec_mean <= 2.2 ? "gd" : f.rec_mean >= 3.5 ? "bd" : "") : "")}
      ${mrow("Price target", "target", f.target ? money(f.target, 2) : "–", f.target_upside != null ? `${pct(f.target_upside, 0, true)} from today` : "", good(f.target_upside, -0.05, 0.10))}
      ${mrow("Market value", "mcap", big(f.market_cap), "")}</table>`;
  }
  if (a.kind === "etf") return `<table class="mt">
      ${mrow("Fee", "fee", a.fee != null ? a.fee + "% a year" : "–", a.fee != null ? `${money(a.fee * 100)} a year on $10,000` : "", a.fee != null ? (a.fee <= 0.2 ? "gd" : a.fee >= 0.45 ? "bd" : "") : "")}
      ${mrow("Fund size", "fundsize", big(f.total_assets), "")}
      ${mrow("Holdings", "holdings", a.holdings ? a.holdings.toLocaleString() : "–", "Companies or bonds inside it")}
      ${mrow("Dividend yield", "dy", pct(f.div_yield), "Paid out each year")}
      ${f.pe ? mrow("P/E of what it holds", "pe", num(f.pe, 1), f.pe > 25 ? "The companies inside are pricey" : "") : ""}</table>`;
  const fg = OPP?.fear_greed;
  return `<table class="mt">
      ${mrow("Market-cap rank", "cgrank", f.mcap_rank ? "#" + f.mcap_rank : "–", "Among all cryptocurrencies")}
      ${mrow("Market value", "mcap", big(f.market_cap), "")}
      ${mrow("Below all-time high", "ath", pct(f.ath_change, 0), "")}
      ${fg ? mrow("Fear & Greed (whole market)", "feargreed", `${fg.value} · ${esc(fg.label)}`, fg.value >= 75 ? "Extreme greed: often a warning sign" : fg.value <= 25 ? "Extreme fear" : "", fg.value >= 75 ? "bd" : "") : ""}</table>
    <p class="muted small">Crypto has no profits, sales or dividends to value, so its fundamentals score is low by design.</p>`;
}
function socialBlock(a) {
  const s = a.sentiment;
  if (!s) return `<p class="muted">No live scan yet. Run one from Community pulse.</p>`;
  const by = s.by_source || { Reddit: { n: s.reddit_mentions, pos: s.reddit_pos, neg: s.reddit_neg }, News: { n: s.news_count, pos: s.news_pos, neg: s.news_neg } };
  const rows = ["Reddit", "Bluesky", "StockTwits", "News"].filter(k => by[k]).map(k => { const d = by[k], o = d.pos + d.neg;
    return `<div class="src"><span class="plat p-${k.toLowerCase()}">${k}</span><span class="num">${d.n} post${d.n === 1 ? "" : "s"}</span>
      ${o ? `<div class="moodbar"><i style="width:${d.pos / o * 100}%"></i></div><small class="muted">${d.pos} positive · ${d.neg} negative</small>` : `<small class="muted">${d.n ? "no clear opinions" : "none found"}</small>`}</div>`; }).join("");
  return `<div class="srcs">${rows}</div>
    ${s.themes?.length ? `<p class="small">Themes: ${s.themes.map(t => `<span class="tag">${esc(t[0])}</span>`).join(" ")}</p>` : ""}
    ${(s.samples || []).map(p => `<div class="post"><span class="plat p-${(p.source === "StockTwits" ? "stocktwits" : p.source === "Bluesky" ? "bluesky" : "reddit")}">${esc(p.source === "StockTwits" || p.source === "Bluesky" ? p.source : "Reddit")}</span>${p.label ? `<span class="tag ${p.label === "Bullish" ? "t-great" : "t-avoid"}">${esc(p.label)}</span>` : ""} <a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <small>${esc(p.date || "")}</small></div>`).join("")}
    ${(s.headlines || []).map(p => `<div class="post"><span class="plat p-news">News</span> <a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <small>${esc(p.date)}</small></div>`).join("")}`;
}
async function openAsset(a) {
  const m = a.model, e = m.expected, r = m.regression, tr = m.trend, sg = m.signals, rk = m.risk, b = e.band;
  const span = Math.max(b.p90, 1000) * 1.05, pos = v => Math.min(100, v / span * 100);
  $("#modal-body").innerHTML = `
    <div class="m-head k-${a.kind}"><div><div class="m-t">${esc(a.ticker)} <span class="muted">· ${esc(a.name)}</span></div>
      <div class="small muted">${esc(a.kind_label)} · ${esc(a.bucket_label)} · ${money(a.price, a.price < 10 ? 3 : 2)} ${esc(a.currency || "")} <span class="${cls(a.day_change)}">${pct(a.day_change, 2, true)} today</span></div></div></div>
    <div class="m-dec t-${a.decision.tone}">${ring(a.score, 76)}<div><div class="m-dl">${esc(a.decision.label)} ${help("decision")}</div>
      <div>${esc(a.size_hint)} ${help("size")}</div><div class="small">Confidence: <b>${m.confidence}</b> ${help("confidence")} · ${esc(a.agreement.text)} ${help("agree")}</div></div></div>
    <div class="grid2 tight">
      <div class="card"><h3>Why</h3>${a.reasons.pos.map(x => `<div class="why gd">✓ ${esc(x)}</div>`).join("")}${a.reasons.neg.map(x => `<div class="why bd">! ${esc(x)}</div>`).join("") || ""}
        ${!a.reasons.pos.length && !a.reasons.neg.length ? `<p class="muted">Nothing stands out either way.</p>` : ""}</div>
      <div class="card"><h3>The three scores</h3>
        <div class="cbar"><span>Models (the data) ${help("model_score")}</span><div class="bar"><i class="t-${toneCls(a.model_score)}" style="width:${a.model_score}%"></i></div><b class="num">${a.model_score}</b></div>
        <div class="cbar"><span>Research &amp; crowd ${help("crowd")}</span><div class="bar"><i class="t-${toneCls(a.crowd_score)}" style="width:${a.crowd_score}%"></i></div><b class="num">${a.crowd_score}</b></div>
        <div class="cbar strong"><span>Final ${help("final")}</span><div class="bar"><i class="t-${toneCls(a.score)}" style="width:${a.score}%"></i></div><b class="num">${a.score}</b></div>
        <p class="muted small" style="margin:8px 0 0">${a.researched ? "Final = 60% models + 40% research &amp; crowd." : "Not researched: final = 75% models + 25% live chatter."}</p></div>
    </div>
    <div class="card"><h3>$1,000 in 5 years ${help("band")}</h3>
      ${e.reliable ? `<div class="band"><div class="bandbar"><span class="bb" style="left:${pos(b.p10)}%;width:${pos(b.p90) - pos(b.p10)}%"></span><span class="b1000" style="left:${pos(1000)}%"></span><span class="bmid" style="left:${pos(b.p50)}%"></span></div>
        <div class="bandlbl"><span>Bad case <b>${money(b.p10)}</b></span><span>Most likely <b>${money(b.p50)}</b></span><span>Good case <b>${money(b.p90)}</b></span></div></div>
        <p class="small">Chance of being down after 5 years: <b>${pct(e.p_loss, 0)}</b> ${help("ploss")}</p>`
        : `<p><b>Too wild to forecast.</b> It swings about ±${pct(e.vol, 0)} a year, so over 5 years almost anything could happen, from losing most of it to multiplying it. Treat it as a gamble.</p>`}
    </div>
    <div class="card"><h3>Price over 10 years, with its long-run trend ${help("trend")}</h3><div id="m-chart" class="chart"></div>
      ${legend([[a.ticker + " (incl. dividends)", css("--accent")], ["Long-run trend line", css("--warn"), 1]])}</div>
    <div class="card"><h3>What the models found</h3><table class="mt">
      ${mrow("Expected growth", "growth", e.reliable ? pct(e.growth) + "/yr" : "Too wild", e.reliable ? "After ups and downs, with shrinkage" : `The swings are so big the formula gives ${pct(e.growth, 0)}/yr, which means little`, e.reliable ? good(e.growth, 0.02, 0.07) : "bd")}
      ${mrow("Past average return", "mu_hist", pct(e.mu_hist) + "/yr", `The models trust ${pct(e.weight_hist, 0)} of this and fill in the rest`)}
      ${mrow("Typical yearly swing", "vol", "±" + pct(e.vol, 0), e.vol < 0.16 ? "Like a broad share fund" : e.vol < 0.35 ? "Like a single company" : "Very wild", e.vol < 0.16 ? "gd" : e.vol > 0.4 ? "bd" : "")}
      ${mrow("Worst drop", "mdd", pct(rk.mdd, 0), "Peak to bottom", good(rk.mdd, -0.5, -0.25))}
      ${mrow("Bad-month loss", "cvar", pct(rk.cvar5, 1), "Average of the worst 1-in-20 months", good(rk.cvar5, -0.15, -0.06))}
      ${mrow("Return for the risk", "sharpe", num(e.sharpe, 2), e.sortino != null ? `Sortino ${num(e.sortino, 2)}` : "", good(e.sharpe, 0.1, 0.4))}
      ${r ? mrow("Market sensitivity", "beta", `AU ${num(r.beta_au, 2)} · US ${num(r.beta_us, 2)}`, `From a regression on ${r.months} months`) : ""}
      ${r ? mrow("Extra return (alpha)", "alpha", pct(r.alpha, 1, true) + "/yr", `t = ${num(r.alpha_t, 1)} → ${Math.abs(r.alpha_t) >= 2 ? "statistically solid" : "could be luck"}`, Math.abs(r.alpha_t) >= 2 ? (r.alpha > 0 ? "gd" : "bd") : "") : ""}
      ${r ? mrow("Market explains", "r2", pct(r.r2, 0), r.r2 > 0.8 ? "Moves almost exactly with the market" : r.r2 < 0.3 ? "Mostly its own story" : "Partly the market, partly its own story") : ""}
      ${tr ? mrow("Trend growth & steadiness", "trend", `${pct(tr.growth)}/yr · ${pct(tr.r2, 0)}`, tr.z > 2 ? "Now well above its trend: stretched" : tr.z < -1.5 ? "Now well below its trend" : "Near its trend", tr.z > 2 ? "bd" : "") : ""}
      ${mrow("Momentum (12 months)", "momentum", pct(sg.mom12_1, 0, true), sg.mom12_1 > 0.1 ? "Rising" : sg.mom12_1 < -0.05 ? "Falling" : "Flat-ish", good(sg.mom12_1, -0.05, 0.1))}
      ${mrow("Above 10-month average", "ma10", sg.above_ma10 ? "Yes" : "No", sg.above_ma10 ? "Uptrend" : "Downtrend", sg.above_ma10 ? "gd" : "bd")}
      ${mrow("Up after 12 months", "upyears", pct(rk.up_years_pct, 0), "Share of past 12-month periods that were up", good(rk.up_years_pct, 0.55, 0.75))}
    </table><p class="muted small">Based on ${m.years} years of monthly prices${m.trust < 1 ? `. Short history, so the score is pulled towards the middle (${pct(1 - m.trust, 0)} less weight)` : ""}.</p></div>
    <div class="grid2 tight">
      <div class="card"><h3>Score breakdown</h3>${compBars(m.components)}</div>
      <div class="card"><h3>${a.kind === "stock" ? "The business" : a.kind === "etf" ? "The fund" : "The coin"}</h3>${fundBlock(a)}</div>
    </div>
    <div class="card"><h3>What people are saying ${help("sentiment")}</h3>
      ${a.what ? `<p>${esc(a.what)}</p>` : ""}<p class="muted">${esc(a.community)}</p>${socialBlock(a)}</div>
    ${a.cons ? `<div class="card watch"><h3>Watch out for</h3><p>${esc(a.cons)}</p></div>` : ""}`;
  $("#modal").hidden = false; $("#modal .modal-box").scrollTop = 0;
  try {
    const h = await api(`/api/history?t=${encodeURIComponent(a.yahoo || a.ticker)}&range=10y&interval=1wk`);
    const series = [{ label: a.ticker, t: h.t.map(x => x * 1000), v: h.adj, color: css("--accent"), fill: true }];
    const tl = m.trend_line;
    if (tl) series.push({ label: "Trend", t: tl.keys.map(k => Date.UTC(+k.slice(0, 4), +k.slice(5) - 1, 28)), v: tl.line, color: css("--warn"), dash: "6 4", width: 1.8 });
    lineChart($("#m-chart"), series, { fmtY: v => money(v, v < 10 ? 2 : 0), logY: true });
  } catch { $("#m-chart").innerHTML = ""; }
}
$("#modal-x").onclick = () => $("#modal").hidden = true;
$("#modal").onclick = e => { if (e.target.id === "modal") $("#modal").hidden = true; };
document.addEventListener("keydown", e => { if (e.key === "Escape") { if (!pop.hidden) closePop(); else $("#modal").hidden = true; } });

// ------------------------------------------------------------------ check
$("#c-go").onclick = async () => {
  const items = $("#c-input").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const m = l.match(/^(.*?)[\s,:$=-]+\$?([\d,.]+)\s*$/);
    return m ? { ticker: m[1].trim(), amount: parseFloat(m[2].replace(/,/g, "")) } : null;
  }).filter(Boolean);
  const out = $("#check-out");
  if (!items.length) { out.innerHTML = `<div class="flag bad">Use one line per holding, like <code>VAS 2000</code></div>`; return; }
  $("#c-go").disabled = true; $("#c-status").textContent = "Looking up prices, history and news, and running the models…"; out.innerHTML = "";
  try {
    const r = await post("/api/check", { items });
    if (!r.rows.length) throw new Error(r.errors.join(" "));
    const gcol = { A: "--up", B: "--up", C: "--warn", D: "--down", F: "--down" }[r.grade];
    const mix = Object.entries(r.mix).filter(([, v]) => v > 0.001);
    out.innerHTML = `
      <div class="grid2">
        <div class="card row" style="align-items:flex-start;gap:20px">
          <div class="grade" style="color:var(${gcol})">${r.grade}</div>
          <div style="flex:1"><b>${r.points}/100</b> for long-term investing ${help("grade")} · total ${money(r.total)}
            <div class="alloc">${mix.map(([k, v], i) => `<span style="width:${v * 100}%;background:${PALETTE[i]}" title="${esc(k)}"></span>`).join("")}</div>
            <div class="legend">${mix.map(([k, v], i) => `<span><i style="background:${PALETTE[i]};height:8px"></i>${esc(k)} ${pct(v, 0)}</span>`).join("")} ${help("mix")}</div>
            <p class="muted" style="font-size:13px">Avg fund fee ${r.avg_fee != null ? r.avg_fee.toFixed(2) + "%" : "–"} ${help("fee")} · expected swings ~${pct(r.vol, 0)}/yr ${help("vol")}</p></div>
        </div>
        <div class="card"><h3>Verdict</h3>
          ${r.good.map(g => `<div class="flag good">✓ ${esc(g)}</div>`).join("")}
          ${r.flags.map(f => `<div class="flag bad">! ${esc(f)}</div>`).join("") || `<div class="flag good">No major red flags.</div>`}
          ${r.errors.map(f => `<div class="flag warn">${esc(f)}</div>`).join("")}
        </div>
      </div>
      <div class="card scroll"><table><thead><tr><th>Holding</th><th>Type</th><th class="r">Amount</th><th>Decision ${help("decision")}</th><th class="r">5y/yr</th><th class="r">Worst drop ${help("mdd")}</th><th>5y trend</th><th>What people say</th></tr></thead><tbody>
      ${r.rows.map(x => `<tr><td><b>${esc(x.input)}</b><div class="muted" style="font-size:12px">${esc(x.symbol)} · ${esc(x.name)}</div></td>
        <td>${esc(x.bucket_label)}</td><td class="r num">${money(x.amount)}<div class="muted">${pct(x.weight, 0)}</div></td>
        <td><div class="row" style="gap:8px;flex-wrap:nowrap">${ring(x.score, 42)}<span class="dec t-${x.decision.tone}">${esc(x.decision.label)}</span></div></td>
        <td class="r num ${cls(x.metrics.cagr5)}">${pct(x.metrics.cagr5 ?? x.metrics.cagr_all)}</td><td class="r num down">${pct(x.metrics.mdd, 0)}</td>
        <td>${sparkline(x.spark, 110, 30)}</td>
        <td style="font-size:13px;max-width:320px">${esc(x.community)}${x.sentiment && x.sentiment.headlines?.length ? `<div class="muted">News: ${x.sentiment.news_pos} positive / ${x.sentiment.news_neg} negative headlines</div>` : ""}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="muted" style="font-size:13px">Want a better version? Run the same amount through <a href="#" onclick="showTab('plan');return false">Start here</a> and compare.</p>`;
  } catch (e) { out.innerHTML = `<div class="flag bad">${esc(e.message)}</div>`; }
  $("#c-go").disabled = false; $("#c-status").textContent = "";
};

// ------------------------------------------------------------------ my money
let MY = null, myRange = "all";
async function loadMine() {
  try { MY = await api("/api/my"); renderMine(); }
  catch (e) { $("#mine-summary").innerHTML = `<div class="flag bad">${esc(e.message)}</div>`; }
}
function renderMine() {
  const hs = MY.holdings, value = hs.reduce((a, h) => a + (h.value || 0), 0), cost = hs.reduce((a, h) => a + (h.cost || 0), 0);
  const gain = value - cost;
  const H = MY.history;
  const dayAgo = H.length > 2 ? H[H.length - 2].value : null;
  if (!hs.length) {
    $("#mine-summary").innerHTML = `<div class="flag warn">Nothing logged yet. Add your first purchase below, e.g. <b>DHHF</b>, 15 units at $38.00. A savings deposit also counts.</div>`;
    $("#mine-chart").innerHTML = `<div class="loading">Your growth chart will appear here</div>`;
    $("#mine-table").innerHTML = ""; return;
  }
  $("#mine-summary").innerHTML = `<div class="grid3">
    <div class="stat"><div class="k">Worth now ${help("worth")}</div><div class="v">${money(value, 2)}</div></div>
    <div class="stat"><div class="k">Total gain</div><div class="v ${cls(gain)}">${gain >= 0 ? "+" : ""}${money(gain, 2)}</div><div class="s ${cls(gain)}">${pct(cost ? gain / cost : 0, 2, true)}</div></div>
    <div class="stat"><div class="k">You put in</div><div class="v">${money(cost, 2)}</div></div>
    <div class="stat"><div class="k">Latest change</div><div class="v ${cls(value - dayAgo)}">${dayAgo != null ? (value >= dayAgo ? "+" : "") + money(value - dayAgo, 2) : "–"}</div></div></div>`;
  let pts = H;
  if (myRange !== "all") { const cut = Date.now() / 1000 - myRange * 86400; pts = H.filter(p => p.t >= cut); }
  const t = pts.map(p => p.t * 1000);
  lineChart($("#mine-chart"), [
    { label: "Worth", t, v: pts.map(p => p.value), color: css("--up"), fill: true, width: 2.6 },
    { label: "Put in", t, v: pts.map(p => p.cost), color: css("--chart-2"), width: 1.6, dash: "4 4" },
  ], { fmtY: v => money(v), fmtX: x => new Date(x).toLocaleDateString("en-AU", { day: "numeric", month: "short" }) });
  $("#mine-table").innerHTML = `<div class="card scroll"><table><thead><tr><th>Holding</th><th>Bought</th><th class="r">Units</th><th class="r">Cost</th><th class="r">Now</th><th class="r">Gain</th><th></th></tr></thead><tbody>
    ${hs.map(h => { const g = (h.value || 0) - (h.cost || 0); return `<tr><td><b>${esc(h.ticker)}</b><div class="muted" style="font-size:12px">${esc(h.name || "")}</div></td>
      <td>${esc(h.date)}</td><td class="r num">${h.units ?? "–"}</td><td class="r num">${money(h.cost, 2)}</td><td class="r num">${money(h.value, 2)}</td>
      <td class="r num ${cls(g)}">${g >= 0 ? "+" : ""}${money(g, 2)}<div>${pct(h.cost ? g / h.cost : 0, 1, true)}</div></td>
      <td><button class="ghost" data-del="${esc(h.id)}">remove</button></td></tr>`; }).join("")}
    </tbody></table></div>`;
  $$("[data-del]").forEach(b => b.onclick = async () => { if (confirm("Remove this entry?")) { await post("/api/my/delete", { id: b.dataset.del }); loadMine(); } });
}
$$("#mine-range button").forEach(b => b.onclick = () => { myRange = b.dataset.r === "all" ? "all" : +b.dataset.r; $$("#mine-range button").forEach(x => x.classList.toggle("on", x === b)); if (MY) renderMine(); });
$("#m-date").value = new Date().toISOString().slice(0, 10);
$("#m-type").onchange = () => { const h = $("#m-type").value === "HISA"; $$(".share-f").forEach(e => e.hidden = h); $$(".hisa-f").forEach(e => e.hidden = !h); };
$("#m-add").onclick = async () => {
  const hisa = $("#m-type").value === "HISA";
  const body = hisa ? { ticker: "HISA", amount: +$("#m-amount").value, rate: +$("#m-rate").value / 100, date: $("#m-date").value }
    : { ticker: $("#m-ticker").value.trim(), units: +$("#m-units").value, price: +$("#m-price").value, fee: +$("#m-fee").value || 0, date: $("#m-date").value };
  if (hisa ? !body.amount : !(body.ticker && body.units && body.price)) { $("#m-status").textContent = "Fill in all fields."; return; }
  $("#m-status").textContent = "Saving…";
  try { await post("/api/my/add", body); $("#m-status").textContent = "Added ✓"; ["#m-ticker", "#m-units", "#m-price", "#m-amount"].forEach(s => $(s).value = ""); loadMine(); }
  catch (e) { $("#m-status").textContent = e.message; }
};

// ------------------------------------------------------------------ pulse
let pollT;
async function loadPulse() {
  clearTimeout(pollT);
  const [{ scan, data }, research] = await Promise.all([api("/api/sentiment"), api("/api/research")]);
  $("#s-status").textContent = scan.running ? `Scanning… ${scan.progress} (${scan.done}/${scan.total})` : data ? `Last scan: ${data.fetched_at} · ${data.posts_scanned} posts, ${data.headlines_scanned} headlines` : "Not scanned yet";
  $("#s-go").disabled = scan.running;
  if (scan.running) pollT = setTimeout(loadPulse, 3000);
  else if (loaded.opps && data && data.fetched_at !== window._lastScan) { window._lastScan = data.fetched_at; loadOpps(); }
  const rows = data ? Object.entries(data.tickers).map(([t, s]) => ({ t, ...s, total: Object.values(s.by_source || {}).reduce((a, d) => a + d.n, 0) || s.reddit_mentions + s.news_count }))
    .sort((a, b) => b.total - a.total) : [];
  const moodCell = d => { if (!d || !d.n) return `<td><small class="muted">–</small></td>`; const o = d.pos + d.neg;
    return `<td><span class="num">${d.n}</span> ${o ? `<div class="moodbar" style="width:90px;display:inline-block;vertical-align:middle"><i style="width:${d.pos / o * 100}%"></i></div>` : ""}</td>`; };
  const unreadable = data?.unreadable || [["X / Twitter", "needs a paid API or a login."], ["Facebook groups", "need a login and are private."], ["HotCopper", "blocks automated readers."]];
  $("#pulse-out").innerHTML = `
    <div class="grid2">
      <div class="card"><h3>What the research concluded</h3>${research.consensus.map(c => `<div class="flag good">${esc(c)}</div>`).join("")}</div>
      <div class="card"><h3>Market backdrop (${esc(research.as_of)})</h3>${research.macro.map(c => `<div class="flag warn">${esc(c)}</div>`).join("")}
        ${data?.themes?.length ? `<h3 style="margin-top:14px">Hot topics in the latest scan</h3><p>${data.themes.map(([k, n]) => `<span class="tag" style="margin:2px">${esc(k)} · ${n}</span>`).join("")}</p>` : ""}
        ${data?.trending_other?.length ? `<h3>Other tickers people mention ${help("trending")}</h3><p>${data.trending_other.map(([k, n]) => `<span class="tag" style="margin:2px">${esc(k)} · ${n}</span>`).join("")}</p><p class="muted" style="font-size:12.5px">The Opportunities tab runs these through the models when there's enough data.</p>` : ""}
      </div>
    </div>
    ${rows.length ? `<div class="card scroll"><h3>Buzz by investment ${help("buzz")}</h3><table><thead><tr><th>Ticker</th><th>Reddit</th><th>Bluesky</th><th>StockTwits</th><th>News</th><th>Themes</th></tr></thead><tbody>
      ${rows.map(r => { const by = r.by_source || { Reddit: { n: r.reddit_mentions, pos: r.reddit_pos, neg: r.reddit_neg }, News: { n: r.news_count, pos: r.news_pos, neg: r.news_neg } };
        return `<tr><td><b>${esc(r.t)}</b></td>${moodCell(by.Reddit)}${moodCell(by.Bluesky)}${moodCell(by.StockTwits)}${moodCell(by.News)}
        <td style="font-size:13px">${r.themes.map(t => esc(t[0])).join(", ")}</td></tr>`; }).join("")}
      </tbody></table><p class="muted small">Number of posts, and the share that sounded positive (green) vs negative (red).</p></div>` : ""}
    <div class="grid2">
      <div class="card"><h3>Sources checked ${help("sources")}</h3>
        ${(data?.sources || []).map(s => `<div class="post">${s.ok ? "✓" : "✗"} ${s.platform ? `<span class="plat p-${s.platform.toLowerCase()}">${esc(s.platform)}</span>` : ""} ${esc(s.name)} <small>${s.ok ? s.items + " items" : ""} ${esc(s.error || "")}</small></div>`).join("")}
        ${unreadable.map(([n, why]) => `<div class="post">✗ ${esc(n)} <small>${esc(why)}</small></div>`).join("")}
        <h3 style="margin-top:14px">Research sources</h3>
        ${research.sources.map(([n, u]) => `<div class="post"><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a></div>`).join("")}
      </div>
      <div class="card"><h3>Latest posts scanned</h3>
        ${(data?.recent_posts || []).slice(0, 30).map(p => `<div class="post"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <small>${esc(p.source)} · ${esc(p.date)}</small></div>`).join("") || `<p class="muted">Run a scan to see posts.</p>`}
      </div>
    </div>`;
}
$("#s-go").onclick = async () => { await post("/api/scan", {}); setTimeout(loadPulse, 500); };

// ------------------------------------------------------------------ boot
let startTab = "plan";
try { startTab = location.hash.slice(1) || localStorage.getItem("tab") || "plan"; } catch {}
if (!document.getElementById(startTab)) startTab = "plan";
showTab(startTab);
