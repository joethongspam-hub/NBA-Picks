"""Render the daily report as one self-contained, mobile-first HTML page."""
from __future__ import annotations

import json

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · __DATE__</title>
<style>
:root{
  --bg:#0c1016; --panel:#141a23; --panel2:#1b2330; --line:#263041; --ink:#e8edf4; --mute:#8b97a8;
  --over:#3ddc97; --under:#ff7a6b; --gold:#f4c95d; --blue:#6ab0ff;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
header{padding:20px 16px 8px;max-width:860px;margin:0 auto}
h1{font-size:22px;margin:0;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:13px;margin-top:2px}
.badge{display:inline-block;font-size:11px;padding:2px 7px;border-radius:99px;border:1px solid var(--line);color:var(--mute);margin-left:6px;vertical-align:2px}
nav{position:sticky;top:0;z-index:5;background:rgba(12,16,22,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
nav .in{max-width:860px;margin:0 auto;display:flex;gap:4px;padding:8px 12px;overflow-x:auto}
nav button{flex:none;background:none;border:0;color:var(--mute);font:600 14px inherit;font-family:inherit;padding:8px 12px;border-radius:8px;cursor:pointer}
nav button.on{color:var(--ink);background:var(--panel2)}
main{max-width:860px;margin:0 auto;padding:12px 12px 60px}
.view{display:none}.view.on{display:block}
.chips{display:flex;gap:6px;overflow-x:auto;padding:4px 0 10px}
.chip{flex:none;border:1px solid var(--line);background:var(--panel);color:var(--mute);border-radius:99px;padding:5px 11px;font-size:13px;cursor:pointer}
.chip.on{color:var(--bg);background:var(--ink);border-color:var(--ink)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;margin-bottom:10px;overflow:hidden}
.pick{padding:12px 14px;border-top:1px solid var(--line);cursor:pointer}
.pick:first-child{border-top:0}
.row{display:flex;align-items:center;gap:10px}
.grade{flex:none;width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font:700 14px var(--mono)}
.gA{background:var(--gold);color:#241a00}.gB{background:#3a4a63;color:var(--ink)}.gC{background:#263041;color:var(--mute)}.g-{background:#1b2330;color:var(--mute)}
.who{flex:1;min-width:0}
.name{font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{color:var(--mute);font-size:12.5px}
.bet{text-align:right;flex:none}
.side{font:700 15px var(--mono)}
.OVER{color:var(--over)}.UNDER{color:var(--under)}
.small{font-size:12px;color:var(--mute)}
.bar{position:relative;height:6px;background:var(--panel2);border-radius:3px;margin:10px 0 4px}
.bar i{position:absolute;top:-3px;width:2px;height:12px;background:var(--ink)}
.bar b{position:absolute;top:0;height:6px;border-radius:3px}
.detail{display:none;margin-top:10px;font-size:13px}
.pick.open .detail{display:block}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:8px 0}
.stats div{background:var(--panel2);border-radius:8px;padding:6px 8px}
.stats span{display:block;color:var(--mute);font-size:11px}
.stats strong{font:600 14px var(--mono)}
ul.why{margin:6px 0 0;padding-left:18px;color:#c6cfdb}
ul.why li{margin:2px 0}
.gh{padding:14px;display:flex;justify-content:space-between;align-items:flex-start;gap:10px;cursor:pointer}
.gh h3{margin:0;font-size:17px}
.inj{padding:0 14px 10px;font-size:12.5px;color:var(--mute)}
.inj .o{color:var(--under)}.inj .q{color:var(--gold)}
.gbody{display:none}.card.open .gbody{display:block}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 8px;text-align:right;border-top:1px solid var(--line);white-space:nowrap}
th{color:var(--mute);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
th:first-child,td:first-child{text-align:left}
td{font-family:var(--mono)}td:first-child{font-family:inherit}
.scroll{overflow-x:auto}
input[type=search]{width:100%;background:var(--panel);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:10px 12px;font-size:15px;margin-bottom:8px}
.rec{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
.rec div{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px;text-align:center}
.rec strong{display:block;font:700 18px var(--mono)}
.rec span{font-size:11.5px;color:var(--mute)}
.WIN{color:var(--over)}.LOSS{color:var(--under)}.PUSH,.VOID{color:var(--mute)}
.res{font:700 12px var(--mono);margin-top:2px}
.PENDING{color:var(--gold)}
.links a{color:var(--blue);margin-right:12px}
.hgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.hgrid label{display:flex;flex-direction:column;font-size:12px;color:var(--mute);gap:4px}
.hgrid .full{grid-column:1 / -1}
.hgrid select,.hgrid input{background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:9px 10px;font-size:16px;width:100%}
.verdict{font:700 20px var(--mono);margin:2px 0 6px}
.empty{color:var(--mute);text-align:center;padding:40px 10px}
.note{color:var(--mute);font-size:12px;margin:14px 2px;line-height:1.5}
.sect{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:16px 2px 8px}
</style>
</head>
<body>
<header>
  <h1>__TITLE__ <span class="badge" id="mode"></span>__SWITCH__</h1>
  <div class="sub" id="sub"></div>
</header>
<nav><div class="in">
  <button data-v="best" class="on">Best bets</button>
  <button data-v="games">Games</button>
  <button data-v="all">All props</button>
  <button data-v="record">Track record</button>
  <button data-v="half" id="halfBtn" style="display:none">Halftime</button>
</div></nav>
<main>
  <section class="view on" id="v-best">
    <div class="chips" id="statChips"></div>
    <div class="card" id="bestList"></div>
  </section>
  <section class="view" id="v-games"><div id="gameList"></div></section>
  <section class="view" id="v-all">
    <input type="search" id="q" placeholder="Search player, team or stat (e.g. 'PTS', 'LAL')">
    <div class="card" id="allList"></div>
  </section>
  <section class="view" id="v-record"><div id="recordBox"></div></section>
  <section class="view" id="v-half">
    <div class="card" style="padding:14px">
      <div class="hgrid">
        <label class="full">Game<select id="hGame"></select></label>
        <label class="full">Player<select id="hPlayer"></select></label>
        <label>Stat<select id="hStat"></select></label>
        <label>Live line<input id="hLine" type="number" inputmode="decimal" step="0.5" placeholder="e.g. 14.5"></label>
        <label>1st-half minutes<input id="hMin" type="number" inputmode="decimal" step="1" placeholder="e.g. 16"></label>
        <label>1st-half stat so far<input id="hVal" type="number" inputmode="decimal" step="1" placeholder="e.g. 9"></label>
        <label>Fouls<input id="hFouls" type="number" inputmode="numeric" step="1" value="0"></label>
        <label>His team's lead (−if trailing)<input id="hMargin" type="number" inputmode="numeric" step="1" value="0"></label>
        <label>Over price<input id="hOver" type="number" inputmode="numeric" placeholder="-115"></label>
        <label>Under price<input id="hUnder" type="number" inputmode="numeric" placeholder="-115"></label>
      </div>
    </div>
    <div id="hOut"></div>
    <p class="note">How it works: first-half <b>minutes</b> count as real information (role, foul trouble, blowout), while
    first-half <b>shooting</b> mostly regresses. Per-minute production is 80% pregame, 20% first half. The second half
    uses the pregame model's game-to-game variance. Live markets carry more vig, so only bet clear edges.</p>
  </section>
  <p class="note">__NOTE__</p>
</main>
<script>
const D = __DATA__;
const LBL = D.labels || {};
const COLS = D.proj_cols || [["min","Min"],["PTS","Pts"],["REB","Reb"],["AST","Ast"],["3PM","3PM"],["PRA","PRA"]];
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pct = x => (x*100).toFixed(0) + "%";
const fmtPrice = p => p == null ? "" : (p > 0 ? "+" + p : p);

$("#mode").textContent = D.backtest ? "backtest" : (D.line_mode === "sportsbook" ? "live lines" : "est. lines");
$("#sub").innerHTML = D.backtest
  ? `${D.date} · ${D.games.length} games · projected blind (only games before ${D.date}) · <a href="../" style="color:var(--blue)">today's picks</a>`
  : `${D.date} · ${D.games.length} game${D.games.length===1?"":"s"} · updated ${D.generated}`;
if (D.backtest) document.querySelector('nav button[data-v=record]').textContent = "Results";

function pickHTML(p, showGame) {
  const lo = Math.min(p.line, p.projection) * 0.6, hi = Math.max(p.line, p.projection) * 1.25 + 0.5;
  const pos = v => ((v - lo) / (hi - lo) * 100).toFixed(1);
  const a = Math.min(pos(p.line), pos(p.projection)), b = Math.max(pos(p.line), pos(p.projection));
  return `<div class="pick" onclick="this.classList.toggle('open')">
    <div class="row">
      <div class="grade g${p.grade}">${p.grade}</div>
      <div class="who"><div class="name">${esc(p.player)}</div>
        <div class="meta">${esc(p.team)} vs ${esc(p.opp)}${showGame ? "" : ""} · ${p.stat} · L10 ${p.hit_l10}${p.status!=="ACTIVE"?` · <span style="color:var(--gold)">${p.status}</span>`:""}${p.locked?` · <span title="locked at tip-off">locked</span>`:""}</div></div>
      <div class="bet"><div class="side ${p.side}">${p.side==="OVER"?"O":"U"} ${p.line}</div>
        <div class="small">proj ${p.projection} · ${pct(p.prob)}</div>
        ${p.result ? `<div class="res ${p.result}">${p.actual!=null?"actual "+p.actual+" · ":""}${p.result}</div>` : ""}</div>
    </div>
    <div class="bar"><b style="left:${a}%;width:${b-a}%;background:var(--${p.side==="OVER"?"over":"under"});opacity:.55"></b><i style="left:${pos(p.line)}%" title="line"></i></div>
    <div class="detail">
      <div class="stats">
        <div><span>Projection</span><strong>${p.projection}</strong></div>
        <div><span>Line</span><strong>${p.line}</strong></div>
        <div><span>Win prob</span><strong>${pct(p.prob)}</strong></div>
        <div><span>Edge</span><strong>${(p.edge*100).toFixed(1)}%</strong></div>
        <div><span>${LBL.season||"Season avg"}</span><strong>${p.season_avg}</strong></div>
        <div><span>${LBL.recent||"L10 avg"}</span><strong>${p.l10_avg}</strong></div>
        <div><span>Hit L5/L10</span><strong>${p.hit_l5} · ${p.hit_l10}</strong></div>
        <div><span>${LBL.min||"Proj min"}</span><strong>${p.minutes}</strong></div>
      </div>
      <div class="small">Line source: ${esc(p.line_source)}${p.price!=null?` · best price ${fmtPrice(p.price)}`:""} · season hit ${p.hit_season} · vs ${esc(p.opp)} ${p.vs_opp}</div>
      <ul class="why">${p.reasons.map(r=>`<li>${esc(r)}</li>`).join("")}</ul>
    </div>
  </div>`;
}

// ---- best bets with stat filter
let statFilter = "ALL";
function renderBest() {
  const stats = ["ALL", ...new Set(D.top.concat(Object.values(D.by_game).flat()).map(p => p.stat))];
  $("#statChips").innerHTML = stats.map(s => `<button class="chip ${s===statFilter?"on":""}" data-s="${s}">${s==="ALL"?"All":s}</button>`).join("");
  let list = statFilter === "ALL" ? D.top
    : D.all.filter(p => p.stat === statFilter && p.edge >= 0.03 && p.grade !== "-").slice(0, 15);
  $("#bestList").innerHTML = list.length ? list.map(p => pickHTML(p, true)).join("")
    : `<div class="empty">${D.games.length ? "No props cleared the bar today." : "No NBA games on this date."}</div>`;
}
$("#statChips").addEventListener("click", e => { const s = e.target.dataset.s; if (s) { statFilter = s; renderBest(); } });

// ---- games
function renderGames() {
  if (!D.games.length) { $("#gameList").innerHTML = `<div class="empty">No NBA games on this date.</div>`; return; }
  $("#gameList").innerHTML = D.games.map(g => {
    const picks = D.by_game[g.id] || [];
    const inj = g.injuries.filter(i => i.level !== "PROBABLE" && i.min >= 8).slice(0, 8);
    const vegas = g.total ? `${esc(g.odds)} · O/U ${g.total} · team totals ${g.away} ${g.tt_away} / ${g.home} ${g.tt_home}` : "No Vegas line posted yet";
    return `<div class="card">
      <div class="gh" onclick="this.parentNode.classList.toggle('open')">
        <div><h3>${esc(g.away)} @ ${esc(g.home)}</h3><div class="meta">${esc(g.time)} · ${vegas}${g.weather?" · "+esc(g.weather):""}</div></div>
        <div class="small">${picks.length} pick${picks.length===1?"":"s"} ▾</div>
      </div>
      ${inj.length ? `<div class="inj">${inj.map(i => `<span class="${i.level==="OUT"||i.level==="DOUBTFUL"?"o":"q"}">${esc(i.team)} ${esc(i.player)} (${esc(i.status)})</span>`).join(" · ")}</div>` : ""}
      ${picks.map(p => pickHTML(p)).join("")}
      <div class="gbody"><div class="sect" style="margin-left:14px">Projections</div><div class="scroll"><table>
        <tr><th>Player</th>${COLS.map(c=>`<th>${c[1]}</th>`).join("")}</tr>
        ${g.projections.map(r => `<tr><td>${esc(r.player)} <span class="small">${esc(r.pos?r.pos+" · ":"")}${esc(r.team)}${r.status!=="ACTIVE"?" · "+r.status[0]:""}</span></td>${COLS.map(c=>`<td>${r[c[0]] ?? "–"}</td>`).join("")}</tr>`).join("")}
      </table></div></div>
    </div>`;
  }).join("");
}

// ---- all props search
function renderAll() {
  const q = $("#q").value.trim().toLowerCase();
  const terms = q.split(/\s+/).filter(Boolean);
  const rows = D.all.filter(p => terms.every(t => `${p.player} ${p.team} ${p.opp} ${p.stat}`.toLowerCase().includes(t))).slice(0, 120);
  $("#allList").innerHTML = rows.length ? rows.map(p => pickHTML(p)).join("") : `<div class="empty">No matches.</div>`;
}
$("#q").addEventListener("input", renderAll);

// ---- model report
function reportHTML(rep) {
  if (!rep || !rep.n) return "";
  const pctTxt = x => x == null ? "–" : (x * 100).toFixed(0) + "%";
  const u = x => (x > 0 ? "+" : "") + x.toFixed(1) + "u";
  const tbl = (rows, extra) => `<div class="card scroll"><table><tr><th></th><th>W-L</th><th>Win%</th>${extra ? "<th>Model said</th>" : ""}<th>Profit</th></tr>
    ${rows.map(x => `<tr><td>${esc(x.label)}</td><td>${x.w}-${x.l}</td><td>${pctTxt(x.pct)}</td>${extra ? `<td>${pctTxt(x.predicted)}</td>` : ""}<td class="${x.units >= 0 ? "WIN" : "LOSS"}">${u(x.units)}</td></tr>`).join("")}</table></div>`;
  const m = rep.misses || {};
  const unit = m.unit === "opps" ? "opportunities" : "minutes";
  return `<div class="sect">Model report · ${rep.n} graded picks</div>
    <div class="note" style="margin-top:0">Profit assumes 1 unit per pick as a single at the listed price (estimated lines at -110).</div>
    <div class="sect">Profit by grade</div>${tbl(rep.profit)}
    <div class="sect">Calibration: does a 65% pick win 65%?</div>${tbl(rep.calibration, true)}
    ${(rep.market || []).length ? `<div class="sect">Market movement (DraftKings open → close)</div>${tbl(rep.market)}
      <div class="note" style="margin-top:4px">Winning the "moved toward our side" row over time is the best early sign of real edge.</div>` : ""}
    ${m.losses ? `<div class="sect">Why losses lost</div><div class="card" style="padding:12px 14px;font-size:13.5px">
      <b>${m.role}</b> of ${m.losses} losses were <b>role misses</b>: ${unit} far off the projection
      (${m.role_more} played more, ${m.role_less} less). <b>${m.variance}</b> were <b>production misses</b>: normal ${unit}, just a bad night.
      ${(m.examples || []).length ? `<ul class="why">${m.examples.map(e => `<li>${esc(e.player)} ${e.side[0]} ${e.line} ${e.stat}: actual ${e.actual} · ${unit} ${e.proj_min} projected, ${e.actual_min} actual</li>`).join("")}</ul>` : ""}
      <div class="small" style="margin-top:6px">Mostly role misses → the model needs better lineup/injury info. Mostly production misses → variance; stay the course.</div></div>` : ""}
    ${(rep.segments || []).map(s => `<div class="sect">By ${esc(s.title.toLowerCase())}</div>${tbl(s.rows)}`).join("")}`;
}

// ---- record
function renderRecord() {
  const r = D.record || {};
  const cell = (k, label) => { const x = r[k] || {w:0,l:0}; return `<div><strong>${x.w}-${x.l}</strong><span>${label}${x.pct!=null?" · "+pct(x.pct):""}</span></div>`; };
  const links = (D.backtests||[]).length && !D.backtest
    ? `<div class="sect">Backtests</div><div class="card" style="padding:12px 14px" class="links">${D.backtests.map(d=>`<a style="color:var(--blue);margin-right:14px" href="backtests/${d}.html">${d}</a>`).join("")}</div>` : "";
  if (D.backtest) {
    const acc = r.accuracy || {};
    const pe = r.all_positive_edge || {w:0,l:0};
    $("#recordBox").innerHTML = `<div class="rec">${cell("all","Shown picks")}${cell("A","Grade A")}${cell("B","Grade B")}${cell("C","Grade C")}</div>
      <div class="note" style="margin-top:0">Every prop with a positive edge: <b>${pe.w}-${pe.l}</b>${pe.pct!=null?" ("+pct(pe.pct)+")":""}. Break-even at -110 is 52.4%.${r.pending?` ${r.pending} props still pending (games not final when this ran).`:""}</div>
      <div class="sect">Projection accuracy (average miss)</div>
      <div class="card scroll"><table><tr><th>Stat</th><th>Props</th><th>Model</th><th>Recent avg</th></tr>
      ${Object.entries(acc).map(([k,v])=>`<tr><td>${k}</td><td>${v.n}</td><td class="${v.model_mae<=v.avg_mae?"WIN":"LOSS"}">${v.model_mae}</td><td>${v.avg_mae}</td></tr>`).join("")}</table></div>
      <div class="note">Lower is better. "Recent avg" is the estimated line (last 10 + season average). Note: who sat out is taken from the actual box scores, which is a little cleaner than the pre-game injury report.</div>
      <div class="sect">Every graded pick</div>
      <div class="card">${(r.recent||[]).map(p=>pickHTML(p)).join("") || '<div class="empty">No final games yet.</div>'}</div>`;
    return;
  }
  const recent = r.recent || [];
  $("#recordBox").innerHTML = `<div class="rec">${cell("all","All")}${cell("A","Grade A")}${cell("B","Grade B")}${cell("C","Grade C")}</div>
    ${recent.length ? `<div class="card scroll"><table><tr><th>Date</th><th>Pick</th><th>Line</th><th>Actual</th><th>Result</th></tr>
    ${recent.slice(0, 15).map(x => `<tr><td>${x.date.slice(5)} <span class="small">${esc(x.player)}</span></td><td class="${x.side}">${x.side[0]} ${x.stat}</td><td>${x.line}</td><td>${x.actual ?? "–"}</td><td class="${x.result}">${x.result}</td></tr>`).join("")}
    </table></div>` : `<div class="empty">Results appear here after the first day's games are graded.</div>`}${reportHTML(r.report)}${links}`;
}

document.querySelector("nav").addEventListener("click", e => {
  const v = e.target.dataset.v; if (!v) return;
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  document.querySelectorAll(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
});
// ---- halftime calculator
const HSTATS = ["PTS","REB","AST","3PM","PRA","PR","PA","RA","STL","BLK"];
const COUNT = new Set(["3PM","STL","BLK"]);
const hasRates = !D.backtest && D.games.some(g => (g.projections || []).some(r => r.rate));
function phi(x){ const t=1/(1+0.2316419*Math.abs(x)); const d=0.3989423*Math.exp(-x*x/2);
  const p=d*t*(0.3193815+t*(-0.3565638+t*(1.781478+t*(-1.821256+t*1.330274)))); return x>0?1-p:p; }
function poissonCdf(k, mu){ if(k<0) return 0; let s=0, term=Math.exp(-mu); for(let i=0;i<=k;i++){ if(i>0) term*=mu/i; s+=term; } return Math.min(1,s); }
function impl(p){ p=Number(p); if(!p) return null; return p>0?100/(p+100):-p/(-p+100); }
function halfCalc() {
  const g = D.games.find(x => x.id === $("#hGame").value); if (!g) return;
  const r = (g.projections || []).find(x => x.player === $("#hPlayer").value); if (!r || !r.rate) return;
  const stat = $("#hStat").value, line = parseFloat($("#hLine").value);
  const m1 = parseFloat($("#hMin").value), v1 = parseFloat($("#hVal").value);
  const fouls = parseInt($("#hFouls").value || "0"), margin = parseInt($("#hMargin").value || "0");
  if ([line, m1, v1].some(x => isNaN(x))) { $("#hOut").innerHTML = `<div class="card" style="padding:14px"><div class="small">Pregame: ${r.pmin} min, ${(r.rate[stat]*r.pmin).toFixed(1)} ${stat} projected. Enter the 1st-half numbers and live line.</div></div>`; return; }
  const notes = [];
  const half = r.pmin / 2;
  const role = Math.max(0.5, Math.min(1.6, m1 / Math.max(half, 1)));
  let m2 = half * (0.5 + 0.5 * role);
  if (role >= 1.2) notes.push(`Played ${m1} min vs ~${half.toFixed(0)} expected: bigger role, 2nd-half minutes raised`);
  if (role <= 0.8) notes.push(`Played ${m1} min vs ~${half.toFixed(0)} expected: smaller role, 2nd-half minutes cut`);
  if (fouls >= 4) { m2 *= 0.8; notes.push(`${fouls} fouls: minutes trimmed 20%`); }
  else if (fouls === 3) { m2 *= 0.92; notes.push("3 fouls at the half: minutes trimmed 8%"); }
  const starter = r.pmin >= 28, am = Math.abs(margin);
  if (am >= 20) { m2 *= starter ? 0.75 : 1.15; notes.push(`${am}-point game: blowout risk, ${starter ? "starter minutes cut 25%" : "bench minutes up"}`); }
  else if (am >= 15) { m2 *= starter ? 0.88 : 1.08; notes.push(`${am}-point game: some blowout risk`); }
  m2 = Math.min(m2, 23);
  const pre = r.rate[stat];
  const r1 = m1 >= 4 ? v1 / m1 : pre;
  const rate2 = 0.8 * pre + 0.2 * r1;
  if (r1 > pre * 1.4) notes.push("Hot 1st half: shooting/production regressed toward pregame rate");
  if (r1 < pre * 0.6 && m1 >= 4) notes.push("Cold 1st half: production expected to bounce back toward pregame rate");
  const mu2 = Math.max(0.01, rate2 * m2), proj = v1 + mu2, need = line - v1;
  let pOver, pUnder;
  if (need <= 0) { pOver = 1; pUnder = 0; }
  else if (COUNT.has(stat)) { const k = Math.floor(need); const integer = Math.abs(need - Math.round(need)) < 1e-9;
    if (integer) { pUnder = poissonCdf(need - 1, mu2); pOver = 1 - poissonCdf(need, mu2); } else { pUnder = poissonCdf(k, mu2); pOver = 1 - pUnder; } }
  else { const sdg = (r.sd || {})[stat] || Math.sqrt(Math.max(r.rate[stat]*r.pmin,1)); const sd = Math.max(Math.sqrt(mu2), sdg * Math.sqrt(Math.max(m2, 1) / Math.max(r.pmin, 1)));
    const integer = Math.abs(line - Math.round(line)) < 1e-9;
    if (integer) { pOver = 1 - phi((need + 0.5 - mu2) / sd); pUnder = phi((need - 0.5 - mu2) / sd); } else { pOver = 1 - phi((need - mu2) / sd); pUnder = 1 - pOver; } }
  // blend with market like the pregame model (live books are sharp)
  const io = impl($("#hOver").value) ?? impl(-115), iu = impl($("#hUnder").value) ?? impl(-115);
  const fair = io / (io + iu);
  pOver = fair + 0.6 * (pOver - fair); pUnder = (1 - fair) + 0.6 * (pUnder - (1 - fair));
  const eo = pOver - io, eu = pUnder - iu;
  const side = eo >= eu ? "OVER" : "UNDER", edge = Math.max(eo, eu), prob = side === "OVER" ? pOver : pUnder;
  const verdict = need <= 0 ? ["Already over the line", "var(--over)"]
    : edge >= 0.06 ? [`Bet ${side}`, side === "OVER" ? "var(--over)" : "var(--under)"]
    : edge >= 0.03 ? [`Lean ${side}`, "var(--gold)"] : ["Pass", "var(--mute)"];
  $("#hOut").innerHTML = `<div class="card" style="padding:14px">
    <div class="verdict" style="color:${verdict[1]}">${verdict[0]}</div>
    <div class="stats">
      <div><span>Projected final</span><strong>${proj.toFixed(1)}</strong></div>
      <div><span>Needs in 2nd half</span><strong>${Math.max(0, need).toFixed(1)}</strong></div>
      <div><span>${side === "OVER" ? "Over" : "Under"} prob</span><strong>${pct(prob)}</strong></div>
      <div><span>Edge</span><strong>${(edge * 100).toFixed(1)}%</strong></div>
      <div><span>2nd-half min</span><strong>${m2.toFixed(1)}</strong></div>
      <div><span>2nd-half ${stat}</span><strong>${mu2.toFixed(1)}</strong></div>
      <div><span>Pregame proj</span><strong>${(pre * r.pmin).toFixed(1)}</strong></div>
      <div><span>Pregame min</span><strong>${r.pmin}</strong></div>
    </div>
    ${notes.length ? `<ul class="why">${notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    <div class="small" style="margin-top:6px">"Bet" needs a 6%+ edge and "Lean" 3–6%, set higher than pregame because live markets carry more vig.</div></div>`;
}
function halfPlayers() {
  const g = D.games.find(x => x.id === $("#hGame").value) || D.games[0];
  const rows = (g.projections || []).filter(r => r.rate).sort((a, b) => a.team.localeCompare(b.team) || b.pmin - a.pmin);
  $("#hPlayer").innerHTML = rows.map(r => `<option value="${esc(r.player)}">${esc(r.team)} · ${esc(r.player)}</option>`).join("");
  halfCalc();
}
if (hasRates) {
  $("#halfBtn").style.display = "";
  $("#hGame").innerHTML = D.games.map(g => `<option value="${g.id}">${esc(g.away)} @ ${esc(g.home)} · ${esc(g.time)}</option>`).join("");
  $("#hStat").innerHTML = HSTATS.map(s => `<option>${s}</option>`).join("");
  $("#hGame").addEventListener("change", halfPlayers);
  ["hPlayer","hStat","hLine","hMin","hVal","hFouls","hMargin","hOver","hUnder"].forEach(id => $("#" + id).addEventListener("input", halfCalc));
  halfPlayers();
}

renderBest(); renderGames(); renderAll(); renderRecord();
</script>
</body>
</html>
"""


NBA_NOTE = ("Projections blend per-minute production, projected minutes, opponent defense vs position, "
            "Vegas implied team totals, rest, home/away splits and injured-teammate usage. When the line says "
            "“est.”, no sportsbook line was available and the line is an estimate of where books open; check your "
            "book's actual number before betting. For entertainment and research only.")


def render(payload: dict, title: str = "NBA Player Props", note: str = NBA_NOTE,
           switch: tuple[str, str] | None = None) -> str:
    data = json.dumps(payload).replace("</", "<\\/")
    sw = (f' <a class="badge" style="color:var(--blue);text-decoration:none" href="{switch[1]}">{switch[0]} →</a>'
          if switch else "")
    return (TEMPLATE.replace("__TITLE__", title).replace("__SWITCH__", sw).replace("__NOTE__", note)
            .replace("__DATE__", payload.get("label") or payload["date"]).replace("__DATA__", data))
