const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v, d = 0) => v == null ? "–" : (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString("en-AU", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v, d = 1, sign = false) => v == null ? "–" : (sign && v > 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
const cls = v => v == null ? "" : v >= 0 ? "up" : "down";
const scoreCls = s => s >= 75 ? "s-hi" : s >= 55 ? "s-mid" : "s-lo";
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const PALETTE = ["#2a9d8f", "#1f6feb", "#e9a23b", "#8e5cd9", "#d9480f", "#5c940d", "#c2255c"];

async function api(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}
const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// ------------------------------------------------------------------ charts
function sparkline(vals, w = 140, h = 36) {
  vals = (vals || []).filter(v => v != null);
  if (vals.length < 2) return "";
  const mn = Math.min(...vals), mx = Math.max(...vals), rg = mx - mn || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - mn) / rg * (h - 4)).toFixed(1)}`).join(" ");
  const col = vals.at(-1) >= vals[0] ? css("--up") : css("--down");
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round"/></svg>`;
}

// series: [{label, t:[ms], v:[num], color, dash, fill}]
function lineChart(el, series, { fmtY = v => money(v), fmtX = t => new Date(t).toLocaleDateString("en-AU", { month: "short", year: "2-digit" }) } = {}) {
  el.innerHTML = "";
  const all = series.flatMap(s => s.v.filter(v => v != null));
  if (!all.length) { el.innerHTML = `<div class="loading">No data yet</div>`; return; }
  const W = el.clientWidth || 700, H = el.clientHeight || 220, L = 64, R = 12, T = 10, B = 26;
  const ts = series.flatMap(s => s.t);
  const x0 = Math.min(...ts), x1 = Math.max(...ts);
  let y0 = Math.min(...all), y1 = Math.max(...all);
  const pad = (y1 - y0) * 0.08 || y1 * 0.05 || 1; y0 = Math.min(...all) >= 0 ? Math.max(0, y0 - pad) : y0 - pad; y1 += pad;
  const X = t => L + (t - x0) / ((x1 - x0) || 1) * (W - L - R);
  const Y = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4, y = Y(v);
    g += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="${css("--chart-grid")}"/><text x="${L - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="${css("--muted")}">${esc(fmtY(v))}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const t = x0 + (x1 - x0) * i / 4;
    g += `<text x="${X(t)}" y="${H - 6}" text-anchor="${i === 0 ? "start" : i === 4 ? "end" : "middle"}" font-size="11" fill="${css("--muted")}">${esc(fmtX(t))}</text>`;
  }
  for (const s of series) {
    const pts = s.t.map((t, i) => s.v[i] == null ? null : [X(t), Y(s.v[i])]).filter(Boolean);
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
    if (s.fill) g += `<path d="${d}L${pts.at(-1)[0]},${Y(y0)}L${pts[0][0]},${Y(y0)}Z" fill="${s.color}" opacity=".10"/>`;
    g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2.2}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} stroke-linejoin="round"/>`;
  }
  const wrap = document.createElement("div");
  wrap.className = "chartwrap"; wrap.style.height = "100%";
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${g}<line class="hl" y1="${T}" y2="${H - B}" stroke="${css("--muted")}" stroke-dasharray="3 3" visibility="hidden"/></svg><div class="tip" hidden></div>`;
  el.appendChild(wrap);
  const tip = $(".tip", wrap), hl = $(".hl", wrap), svg = $("svg", wrap), main = series[0];
  svg.addEventListener("mousemove", e => {
    const r = svg.getBoundingClientRect(), mx = (e.clientX - r.left) / r.width * W;
    let bi = 0, bd = 1e18;
    main.t.forEach((t, i) => { const d = Math.abs(X(t) - mx); if (d < bd) { bd = d; bi = i; } });
    const px = X(main.t[bi]);
    hl.setAttribute("x1", px); hl.setAttribute("x2", px); hl.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.style.left = (px / W * r.width) + "px"; tip.style.top = (Y(main.v[bi]) / H * r.height) + "px";
    tip.innerHTML = `${esc(new Date(main.t[bi]).toLocaleDateString("en-AU"))} · ` +
      series.map(s => `${esc(s.label)} <b>${esc(fmtY(s.v[Math.min(bi, s.v.length - 1)]))}</b>`).join(" · ");
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
          ${l.score != null ? `<span class="tag">score ${l.score}</span>` : ""}${l.fee != null ? `<span class="tag">fee ${l.fee}%</span>` : ""}
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
            <li>Open a <b>CHESS-sponsored</b> broker account (CMC Invest, Webull, Stake, Moomoo, Pearler or CommSec are popular and cheap for ETFs).</li>
            <li>Buy the ETFs above in one go, or spread it over 2–3 months if a drop right after buying would upset you.</li>
            <li>Set up an automatic ${monthly ? money(monthly) : "monthly"} deposit and top up the same split.</li>
            <li>Log each purchase in <a href="#" onclick="showTab('mine');return false">My money</a> to watch it grow.</li>
            <li>Don't sell because of a scary headline. Check in every few months, not every day.</li>
          </ol></div>
      </div>
      <div class="grid3">
        <div class="stat"><div class="k">Expected long-run return</div><div class="v">${pct(r)}</div><div class="s muted">per year (conservative estimate)</div></div>
        <div class="stat"><div class="k">In 10 years (likely range)</div><div class="v">${money(at(mid, 10))}</div><div class="s muted">${money(at(lo, 10))} – ${money(at(hi, 10))}</div></div>
        <div class="stat"><div class="k">In 20 years (likely range)</div><div class="v">${money(at(mid, 20))}</div><div class="s muted">${money(at(lo, 20))} – ${money(at(hi, 20))}</div></div>
        <div class="stat"><div class="k">You'd have put in (20y)</div><div class="v">${money(amount + monthly * 240)}</div><div class="s muted">the rest is growth</div></div>
      </div>
      <div class="card"><h2 style="margin-top:0">Projection: next 20 years</h2><div id="proj" class="chart tall"></div>
        ${legend([["Expected", css("--up")], ["Poor decade(s)", css("--down"), 1], ["Good decade(s)", css("--accent"), 1], ["Money you put in", css("--chart-2")]])}
        <p class="muted" style="font-size:13px">Smooth lines show averages. Real balances zig-zag and will have down years. The "poor" line assumes returns 3%/yr below expected.</p></div>
      ${p.backtest ? `<div class="card"><h2 style="margin-top:0">If you'd started this plan 5 years ago</h2><div id="bt" class="chart tall"></div>
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
let ASSETS = [], oppFilter = "all";
async function loadOpps() {
  try {
    const j = await api("/api/assets");
    ASSETS = j.assets;
    const buckets = [["all", "All"], ...[...new Map(ASSETS.map(a => [a.bucket, a.bucket_label])).entries()]];
    $("#opp-filters").innerHTML = buckets.map(([k, l]) => `<button data-b="${k}" class="${k === oppFilter ? "on" : ""}">${esc(l)}</button>`).join("") +
      `<span class="muted" style="font-size:12.5px;align-self:center;margin-left:auto">Community data: ${esc(j.sentiment_at || "not scanned yet")}</span>`;
    $$("#opp-filters button").forEach(b => b.onclick = () => { oppFilter = b.dataset.b; $$("#opp-filters button").forEach(x => x.classList.toggle("on", x === b)); renderOpps(); });
    renderOpps();
  } catch (e) { $("#opp-list").innerHTML = `<div class="flag bad">${esc(e.message)}</div>`; }
}
function renderOpps() {
  const rows = ASSETS.filter(a => !a.error && (oppFilter === "all" || a.bucket === oppFilter));
  $("#opp-list").innerHTML = rows.map(a => {
    const m = a.metrics || {};
    return `<div class="opp" data-t="${esc(a.ticker)}">
      <div class="score ${scoreCls(a.score)}">${a.score}</div>
      <div><span class="t">${esc(a.ticker)}</span><span class="tag">${esc(a.bucket_label)}</span>
        <div class="n">${esc(a.name)}</div><div class="v">${esc(a.verdict)}</div></div>
      <div class="num"><b>${money(a.price, 2)}</b><div class="${cls(a.day_change)}" style="font-size:13px">${pct(a.day_change, 2, true)} today</div></div>
      <div class="bars hide-sm">
        <span>Quality ${a.quality}</span><div class="bar"><i style="width:${a.quality}%"></i></div>
        <span>Returns ${a.perf_score} · 5y ${pct(m.cagr5 ?? m.cagr_all)}/yr</span><div class="bar"><i style="width:${a.perf_score}%"></i></div>
        <span>Sentiment ${a.sent_score}${a.sentiment ? ` · ${a.sentiment.reddit_mentions} posts` : ""}</span><div class="bar"><i style="width:${a.sent_score}%"></i></div>
      </div>
      <div class="hide-sm">${sparkline(a.spark)}<div class="muted" style="font-size:11.5px">last 6 months</div></div>
    </div>`;
  }).join("") || `<div class="loading">Nothing here</div>`;
  $$(".opp").forEach(el => el.onclick = () => openAsset(ASSETS.find(a => a.ticker === el.dataset.t)));
}
async function openAsset(a) {
  const m = a.metrics || {}, s = a.sentiment;
  $("#modal-body").innerHTML = `
    <div class="row"><div class="score ${scoreCls(a.score)}">${a.score}</div><div><h2 style="margin:0">${esc(a.ticker)} · ${esc(a.name)}</h2><span class="muted">${esc(a.bucket_label)} · ${money(a.price, 2)} ${esc(a.currency || "")}</span></div></div>
    <p><b>${esc(a.verdict)}</b></p>
    <p>${esc(a.what)}</p>
    <div class="grid3">
      <div class="stat"><div class="k">5-year return</div><div class="v ${cls(m.cagr5)}">${pct(m.cagr5)}</div><div class="s muted">per year, incl. dividends</div></div>
      <div class="stat"><div class="k">Worst drop (10y)</div><div class="v down">${pct(m.mdd, 0)}</div><div class="s muted">peak to bottom</div></div>
      <div class="stat"><div class="k">Up after 12 months</div><div class="v">${pct(m.up_years_pct, 0)}</div><div class="s muted">of the time, historically</div></div>
      <div class="stat"><div class="k">Fee</div><div class="v">${a.fee ? a.fee + "%" : "–"}</div><div class="s muted">per year</div></div>
    </div>
    <div id="m-chart" class="chart" style="margin:14px 0"></div>
    <h3>What people are saying</h3><p>${esc(a.community)}</p>
    ${s ? `<p class="muted">Live scan: ${s.reddit_mentions} Reddit posts (${s.reddit_pos} positive / ${s.reddit_neg} negative), ${s.news_count} news headlines (${s.news_pos} positive / ${s.news_neg} negative).
      ${s.themes.length ? "Themes: " + s.themes.map(t => esc(t[0])).join(", ") : ""}</p>
      ${s.samples.map(p => `<div class="post"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <small>${esc(p.source)} · ${esc(p.date)}</small></div>`).join("")}
      ${s.headlines.map(p => `<div class="post"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <small>news · ${esc(p.date)}</small></div>`).join("")}` : `<p class="muted">No live scan yet. Run one from Community pulse.</p>`}
    <h3 style="margin-top:14px">Watch out for</h3><p>${esc(a.cons)}</p>`;
  $("#modal").hidden = false;
  try {
    const h = await api(`/api/history?t=${encodeURIComponent(a.ticker)}&range=10y&interval=1wk`);
    lineChart($("#m-chart"), [{ label: a.ticker, t: h.t.map(x => x * 1000), v: h.adj, color: css("--accent"), fill: true }], { fmtY: v => money(v, v < 10 ? 2 : 0) });
  } catch { $("#m-chart").innerHTML = ""; }
}
$("#modal-x").onclick = () => $("#modal").hidden = true;
$("#modal").onclick = e => { if (e.target.id === "modal") $("#modal").hidden = true; };
document.addEventListener("keydown", e => { if (e.key === "Escape") $("#modal").hidden = true; });

// ------------------------------------------------------------------ check
$("#c-go").onclick = async () => {
  const items = $("#c-input").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const m = l.match(/^(.*?)[\s,:$=-]+\$?([\d,.]+)\s*$/);
    return m ? { ticker: m[1].trim(), amount: parseFloat(m[2].replace(/,/g, "")) } : null;
  }).filter(Boolean);
  const out = $("#check-out");
  if (!items.length) { out.innerHTML = `<div class="flag bad">Use one line per holding, like <code>VAS 2000</code></div>`; return; }
  $("#c-go").disabled = true; $("#c-status").textContent = "Looking up prices, history and news…"; out.innerHTML = "";
  try {
    const r = await post("/api/check", { items });
    if (!r.rows.length) throw new Error(r.errors.join(" "));
    const gcol = { A: "--up", B: "--up", C: "--warn", D: "--down", F: "--down" }[r.grade];
    const mix = Object.entries(r.mix).filter(([, v]) => v > 0.001);
    out.innerHTML = `
      <div class="grid2">
        <div class="card row" style="align-items:flex-start;gap:20px">
          <div class="grade" style="color:var(${gcol})">${r.grade}</div>
          <div style="flex:1"><b>${r.points}/100</b> for long-term investing · total ${money(r.total)}
            <div class="alloc">${mix.map(([k, v], i) => `<span style="width:${v * 100}%;background:${PALETTE[i]}" title="${esc(k)}"></span>`).join("")}</div>
            <div class="legend">${mix.map(([k, v], i) => `<span><i style="background:${PALETTE[i]};height:8px"></i>${esc(k)} ${pct(v, 0)}</span>`).join("")}</div>
            <p class="muted" style="font-size:13px">Avg fund fee ${r.avg_fee != null ? r.avg_fee.toFixed(2) + "%" : "–"} · expected swings ~${pct(r.vol, 0)}/yr</p></div>
        </div>
        <div class="card"><h3>Verdict</h3>
          ${r.good.map(g => `<div class="flag good">✓ ${esc(g)}</div>`).join("")}
          ${r.flags.map(f => `<div class="flag bad">! ${esc(f)}</div>`).join("") || `<div class="flag good">No major red flags.</div>`}
          ${r.errors.map(f => `<div class="flag warn">${esc(f)}</div>`).join("")}
        </div>
      </div>
      <div class="card scroll"><table><thead><tr><th>Holding</th><th>Type</th><th class="r">Amount</th><th class="r">Score</th><th class="r">5y/yr</th><th class="r">Worst drop</th><th>5y trend</th><th>What people say</th></tr></thead><tbody>
      ${r.rows.map(x => `<tr><td><b>${esc(x.input)}</b><div class="muted" style="font-size:12px">${esc(x.symbol)} · ${esc(x.name)}</div></td>
        <td>${esc(x.bucket_label)}</td><td class="r num">${money(x.amount)}<div class="muted">${pct(x.weight, 0)}</div></td>
        <td class="r"><span class="score ${scoreCls(x.score)}" style="width:40px;height:40px;font-size:14px;display:inline-grid">${x.score}</span></td>
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
    <div class="stat"><div class="k">Worth now</div><div class="v">${money(value, 2)}</div></div>
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
  const rows = data ? Object.entries(data.tickers).map(([t, s]) => ({ t, ...s })).sort((a, b) => b.reddit_mentions - a.reddit_mentions) : [];
  $("#pulse-out").innerHTML = `
    <div class="grid2">
      <div class="card"><h3>What the research concluded</h3>${research.consensus.map(c => `<div class="flag good">${esc(c)}</div>`).join("")}</div>
      <div class="card"><h3>Market backdrop (${esc(research.as_of)})</h3>${research.macro.map(c => `<div class="flag warn">${esc(c)}</div>`).join("")}
        ${data?.themes?.length ? `<h3 style="margin-top:14px">Hot topics in the latest scan</h3><p>${data.themes.map(([k, n]) => `<span class="tag" style="margin:2px">${esc(k)} · ${n}</span>`).join("")}</p>` : ""}
        ${data?.trending_other?.length ? `<h3>Other tickers people mention</h3><p>${data.trending_other.map(([k, n]) => `<span class="tag" style="margin:2px">${esc(k)} · ${n}</span>`).join("")}</p><p class="muted" style="font-size:12.5px">Paste any of these into "Check a portfolio" to analyse them.</p>` : ""}
      </div>
    </div>
    ${rows.length ? `<div class="card scroll"><h3>Buzz by investment</h3><table><thead><tr><th>Ticker</th><th class="r">Reddit posts</th><th>Reddit mood</th><th class="r">News</th><th>News mood</th><th>Themes</th></tr></thead><tbody>
      ${rows.map(r => { const rp = r.reddit_pos + r.reddit_neg, np = r.news_pos + r.news_neg;
        return `<tr><td><b>${esc(r.t)}</b></td><td class="r num">${r.reddit_mentions}</td>
        <td>${rp ? `<div class="bar" style="width:120px;background:var(--bad-bg)"><i style="width:${r.reddit_pos / rp * 100}%;background:var(--up)"></i></div><small class="muted">${r.reddit_pos}+ / ${r.reddit_neg}−</small>` : `<small class="muted">–</small>`}</td>
        <td class="r num">${r.news_count}</td>
        <td>${np ? `<div class="bar" style="width:120px;background:var(--bad-bg)"><i style="width:${r.news_pos / np * 100}%;background:var(--up)"></i></div><small class="muted">${r.news_pos}+ / ${r.news_neg}−</small>` : `<small class="muted">–</small>`}</td>
        <td style="font-size:13px">${r.themes.map(t => esc(t[0])).join(", ")}</td></tr>`; }).join("")}
      </tbody></table></div>` : ""}
    <div class="grid2">
      <div class="card"><h3>Sources checked</h3>
        ${(data?.sources || []).map(s => `<div class="post">${s.ok ? "✓" : "✗"} ${esc(s.name)} <small>${s.ok ? s.items + " items" : ""} ${esc(s.error || "")}</small></div>`).join("")}
        <div class="post">✗ X/Twitter and Facebook <small>need a login or paid API to read, so they aren't scanned directly. Their mainstream takes show up via news coverage and the research below.</small></div>
        <h3 style="margin-top:14px">Research sources</h3>
        ${research.sources.map(([n, u]) => `<div class="post"><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a></div>`).join("")}
      </div>
      <div class="card"><h3>Latest posts scanned</h3>
        ${(data?.recent_posts || []).slice(0, 25).map(p => `<div class="post"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> <small>${esc(p.source)} · ${esc(p.date)}</small></div>`).join("") || `<p class="muted">Run a scan to see posts.</p>`}
      </div>
    </div>`;
}
$("#s-go").onclick = async () => { await post("/api/scan", {}); setTimeout(loadPulse, 500); };

// ------------------------------------------------------------------ boot
let startTab = "plan";
try { startTab = location.hash.slice(1) || localStorage.getItem("tab") || "plan"; } catch {}
if (!document.getElementById(startTab)) startTab = "plan";
showTab(startTab);
