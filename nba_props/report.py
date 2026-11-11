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
  <button data-v="parlay" id="parlayBtn" style="display:none">Parlays</button>
  <button data-v="games">Games</button>
  <button data-v="team" id="teamBtn" style="display:none">Team</button>
  <button data-v="all">All props</button>
  <button data-v="record">Track record</button>
  <button data-v="half" id="halfBtn" style="display:none">Live</button>
</div></nav>
<main>
  <section class="view on" id="v-best">
    <div class="row" style="gap:8px;margin-bottom:2px"><span class="small">Sort</span><div class="chips sortChips" style="padding:0"></div></div>
    <div class="chips" id="statChips"></div>
    <div class="card" id="bestList"></div>
  </section>
  <section class="view" id="v-parlay">
    <div class="sect" style="margin-top:4px">Parlay checker</div>
    <div class="card" style="padding:12px 14px" id="slipBox"></div>
    <div id="parlayBox"></div>
  </section>
  <section class="view" id="v-games"><div id="gameList"></div></section>
  <section class="view" id="v-team"><div id="teamBox"></div></section>
  <section class="view" id="v-all">
    <input type="search" id="q" placeholder="Search player, team or stat (e.g. 'PTS', 'LAL')">
    <div class="row" style="gap:8px;margin-bottom:8px"><span class="small">Sort</span><div class="chips sortChips" style="padding:0"></div></div>
    <div class="card" id="allList"></div>
  </section>
  <section class="view" id="v-record"><div id="recordBox"></div></section>
  <section class="view" id="v-half">
    <div class="card" style="padding:12px 14px">
      <div class="row" style="gap:8px">
        <select id="hGame" style="flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:9px 10px;font-size:16px"></select>
        <button id="hRefresh" class="chip on" style="padding:9px 14px">Refresh</button>
      </div>
      <div class="small" id="hStatus" style="margin-top:8px">Pick a game: live stats and DraftKings lines load automatically.</div>
    </div>
    <div class="sect">Live edges in this game</div>
    <div class="card" id="hScan"><div class="empty">Load a game in progress to scan for edges.</div></div>
    <div class="sect">Calculator</div>
    <div class="card" style="padding:14px">
      <div class="hgrid">
        <label class="full">Player<select id="hPlayer"></select></label>
        <label>Stat<select id="hStat"></select></label>
        <label>Live line<input id="hLine" type="number" inputmode="decimal" step="0.5" placeholder="e.g. 14.5"></label>
        <label>Minutes so far<input id="hMin" type="number" inputmode="decimal" step="1"></label>
        <label>Stat so far<input id="hVal" type="number" inputmode="decimal" step="1"></label>
        <label>Fouls<input id="hFouls" type="number" inputmode="numeric" step="1" value="0"></label>
        <label>His team's lead (−if trailing)<input id="hMargin" type="number" inputmode="numeric" step="1" value="0"></label>
        <label>Over price<input id="hOver" type="number" inputmode="numeric" placeholder="-115"></label>
        <label>Under price<input id="hUnder" type="number" inputmode="numeric" placeholder="-115"></label>
        <label class="full">Game minutes played (24 = halftime)<input id="hElapsed" type="number" inputmode="decimal" step="1" value="24"></label>
      </div>
    </div>
    <div id="hOut"></div>
    <p class="note">Stats, score and clock come from ESPN's live box score; lines come from DraftKings via ESPN.
    <b>If DraftKings hasn't posted live props, the line shown may be the pregame line</b>, so check your book and edit
    the line if it differs. Minutes so far count as real information (role, foul trouble, blowout); shooting mostly
    regresses (per-minute rate is 80% pregame). Live markets carry more vig, so only bet clear edges.</p>
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

const nReal = D.all.filter(p => p.line_source && p.line_source !== "est.").length, nEst = D.all.length - nReal;
$("#mode").textContent = D.backtest ? "backtest" : !nReal ? "est. lines" : `${nReal} real · ${nEst} est. lines`;
$("#sub").innerHTML = D.backtest
  ? `${D.date} · ${D.games.length} games · projected blind (only games before ${D.date}) · <a href="../" style="color:var(--blue)">today's picks</a>`
  : `${D.date} · ${D.games.length} game${D.games.length===1?"":"s"} · updated ${D.generated}`;
if (D.backtest) document.querySelector('nav button[data-v=record]').textContent = "Results";

// line shopping: best = most favorable line for the side, then best price
function bestBook(p) {
  const b = Object.entries(p.books || {}); if (!b.length) return null;
  const over = p.side === "OVER";
  b.sort((x, y) => (over ? x[1][0] - y[1][0] : y[1][0] - x[1][0]) || (impl(x[1][1]) - impl(y[1][1])));
  return b[0];
}
function shopHTML(p) {
  const b = Object.entries(p.books || {}); if (!b.length) return "";
  const best = bestBook(p), s = p.side === "OVER" ? "O" : "U";
  const order = ["FanDuel", "DraftKings"];
  const rank = k => { const i = order.indexOf(k); return i < 0 ? 9 : i; };
  b.sort((x, y) => (rank(x[0]) - rank(y[0])) || x[0].localeCompare(y[0]));
  return `<div class="small" style="margin:4px 0 2px"><b>Shop:</b> ${b.map(([k, v]) =>
    `<span style="${k === best[0] ? "color:var(--over);font-weight:600" : ""}">${esc(k)} ${s} ${v[0]} ${fmtPrice(v[1])}${k === best[0] && b.length > 1 ? " ✓" : ""}</span>`).join(" · ")}</div>`;
}

function pickHTML(p, showGame) {
  const lo = Math.min(p.line, p.projection) * 0.6, hi = Math.max(p.line, p.projection) * 1.25 + 0.5;
  const pos = v => ((v - lo) / (hi - lo) * 100).toFixed(1);
  const a = Math.min(pos(p.line), pos(p.projection)), b = Math.max(pos(p.line), pos(p.projection));
  return `<div class="pick" onclick="this.classList.toggle('open')">
    <div class="row">
      <div class="grade g${p.grade}">${p.grade}</div>
      <div class="who"><div class="name">${esc(p.player)}</div>
        <div class="meta">${esc(p.team)} vs ${esc(p.opp)}${showGame ? "" : ""} · ${p.stat} · L10 ${p.hit_l10}${p.line_source === "est." && !D.backtest ? ` · <span style="color:var(--gold)">est. line</span>` : ""}${p.status!=="ACTIVE"?` · <span style="color:var(--gold)">${p.status}</span>`:""}${p.locked?` · <span title="locked at tip-off">locked</span>`:""}</div></div>
      <div class="bet"><div class="side ${p.side}">${p.side==="OVER"?"O":"U"} ${p.line}</div>
        <div class="small">proj ${p.projection} · ${pct(p.prob)}</div>
        ${(() => { const bb = bestBook(p); return bb && Object.keys(p.books).length > 1 ? `<div class="small" style="color:var(--over)">best: ${esc(bb[0])} ${fmtPrice(bb[1][1])}</div>` : ""; })()}
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
      ${shopHTML(p)}
      <div class="small">Line source: ${esc(p.line_source)}${p.price!=null && !Object.keys(p.books || {}).length ? ` · price ${fmtPrice(p.price)}` : ""} · season hit ${p.hit_season} · vs ${esc(p.opp)} ${p.vs_opp}</div>
      <ul class="why">${p.reasons.map(r=>`<li>${esc(r)}</li>`).join("")}</ul>
      ${p.dist && !D.backtest ? `<button class="chip" style="margin-top:8px" onclick="event.stopPropagation();slipAdd('${pkey(p)}')">+ Add to parlay</button>` : ""}
    </div>
  </div>`;
}

// ---- sorting (Grade / Win % / Edge), remembered on this device
const SORTS = [["grade", "Grade"], ["prob", "Win %"], ["edge", "Edge"]];
let sortMode = "grade";
try { sortMode = localStorage.getItem("propSort") || "grade"; } catch (e) {}
const GR = {A: 3, B: 2, C: 1};
function sortPicks(list) {
  const key = sortMode === "prob" ? (p => p.prob) : sortMode === "edge" ? (p => p.edge)
    : (p => (GR[p.grade] || 0) * 1000 + (p.score || 0));
  return [...list].sort((a, b) => key(b) - key(a));
}
function onePerPlayer(list, n) {
  const seen = new Set(), out = [];
  for (const p of list) { if (!seen.has(p.player_id)) { seen.add(p.player_id); out.push(p); } if (out.length >= n) break; }
  return out;
}
function renderSortChips() {
  document.querySelectorAll(".sortChips").forEach(el => el.innerHTML = SORTS.map(([k, l]) =>
    `<button class="chip ${k === sortMode ? "on" : ""}" data-sort="${k}">${l}</button>`).join(""));
}
document.addEventListener("click", e => {
  const k = e.target.dataset && e.target.dataset.sort; if (!k) return;
  sortMode = k; try { localStorage.setItem("propSort", k); } catch (err) {}
  renderSortChips(); renderBest(); renderAll(); renderGames();
});

// ---- best bets with stat filter
let statFilter = "ALL";
function renderBest() {
  renderSortChips();
  const stats = ["ALL", ...new Set(D.top.concat(Object.values(D.by_game).flat()).map(p => p.stat))];
  $("#statChips").innerHTML = stats.map(s => `<button class="chip ${s===statFilter?"on":""}" data-s="${s}">${s==="ALL"?"All":s}</button>`).join("");
  const pool = D.top.concat(D.all.filter(p => p.edge >= 0.03 && p.grade !== "-"))
    .filter(p => statFilter === "ALL" || p.stat === statFilter);
  let list = (statFilter === "ALL" && sortMode === "grade" && !D.backtest) ? D.top : onePerPlayer(sortPicks(pool), 15);
  $("#bestList").innerHTML = list.length ? list.map(p => pickHTML(p, true)).join("")
    : `<div class="empty">${D.games.length ? "No props cleared the bar today." : "No NBA games on this date."}</div>`;
}
$("#statChips").addEventListener("click", e => { const s = e.target.dataset.s; if (s) { statFilter = s; renderBest(); } });

// ---- games
function renderGames() {
  if (!D.games.length) { $("#gameList").innerHTML = `<div class="empty">No NBA games on this date.</div>`; return; }
  $("#gameList").innerHTML = D.games.map(g => {
    const picks = sortPicks(D.by_game[g.id] || []);
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
  const rows = sortPicks(D.all.filter(p => terms.every(t => `${p.player} ${p.team} ${p.opp} ${p.stat}`.toLowerCase().includes(t)))).slice(0, 120);
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
  const est = r.est || {w: 0, l: 0};
  $("#recordBox").innerHTML = `<div class="rec">${cell("all","All")}${cell("A","Grade A")}${cell("B","Grade B")}${cell("C","Grade C")}</div>
    <div class="note" style="margin-top:0">Counts only picks on real sportsbook lines.${est.w + est.l ? ` Estimated-line picks (${est.w}-${est.l}) aren't counted.` : ""}</div>
    ${recent.length ? `<div class="card scroll"><table><tr><th>Date</th><th>Pick</th><th>Line</th><th>Actual</th><th>Result</th></tr>
    ${recent.slice(0, 15).map(x => `<tr><td>${x.date.slice(5)} <span class="small">${esc(x.player)}</span></td><td class="${x.side}">${x.side[0]} ${x.stat}</td><td>${x.line}</td><td>${x.actual ?? "–"}</td><td class="${x.result}">${x.result}</td></tr>`).join("")}
    </table></div>` : `<div class="empty">Results appear here after the first day's games are graded.</div>`}${reportHTML(r.report)}${links}`;
}

document.querySelector("nav").addEventListener("click", e => {
  const v = e.target.dataset.v; if (!v) return;
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  document.querySelectorAll(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
});
// ---- parlay checker (slip shared across the NBA / NFL / NHL pages on this device)
const SPORT = document.title.split(" ")[0];
const pkey = p => `${p.player_id}|${p.stat}|${p.side}|${p.line}`;
const PICKS = {};
[...D.all, ...D.top, ...Object.values(D.by_game).flat()].forEach(p => { if (p.dist) PICKS[pkey(p)] = p; });
let SLIP = [];
try { SLIP = JSON.parse(localStorage.getItem("parlaySlip") || "[]"); } catch (e) { SLIP = []; }
const saveSlip = () => { try { localStorage.setItem("parlaySlip", JSON.stringify(SLIP)); } catch (e) {} };
function lgam(x) { const g = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
  let y = x, t = x + 5.5; t -= (x + 0.5) * Math.log(t); let s = 1.000000000190015; for (const c of g) s += c / ++y; return -t + Math.log(2.5066282746310005 * s / x); }
function nbCdf(k, mu, v) { if (k < 0) return 0; if (mu <= 0) return 1; let t = 0;
  if (v <= mu * 1.0001) { for (let i = 0; i <= k; i++) t += Math.exp(-mu + i * Math.log(mu) - lgam(i + 1)); return Math.min(1, t); }
  const r = mu * mu / (v - mu), p = r / (r + mu);
  for (let i = 0; i <= k; i++) t += Math.exp(lgam(i + r) - lgam(r) - lgam(i + 1) + r * Math.log(p) + i * Math.log(1 - p)); return Math.min(1, t); }
function gammaP(a, x) { if (x <= 0) return 0; const gl = lgam(a);
  if (x < a + 1) { let ap = a, s = 1 / a, d = s; for (let i = 0; i < 300; i++) { ap++; d *= x / ap; s += d; if (Math.abs(d) < Math.abs(s) * 1e-10) break; } return s * Math.exp(-x + a * Math.log(x) - gl); }
  let b = x + 1 - a, c = 1e300, d = 1 / b, h = d;
  for (let i = 1; i < 300; i++) { const an = -i * (i - a); b += 2; d = an * d + b; if (Math.abs(d) < 1e-300) d = 1e-300; c = b + an / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; const de = d * c; h *= de; if (Math.abs(de - 1) < 1e-10) break; }
  return 1 - Math.exp(-x + a * Math.log(x) - gl) * h; }
function modelOU(dist, mu, L) {           // [P(over), P(under)] under the projected distribution
  mu = Math.max(mu, 0.01); const int = Math.abs(L - Math.round(L)) < 1e-9;
  if (dist.k === "normal") { const sd = dist.sd; return int ? [1 - phi((L + .5 - mu) / sd), phi((L - .5 - mu) / sd)] : [1 - phi((L - mu) / sd), phi((L - mu) / sd)]; }
  if (dist.k === "gamma") { const k = 1 / Math.pow(dist.cv, 2), th = mu / k;
    return int ? [1 - gammaP(k, (L + .5) / th), gammaP(k, Math.max(L - .5, 0) / th)] : [1 - gammaP(k, L / th), gammaP(k, L / th)]; }
  const v = dist.var; if (int) return [1 - nbCdf(Math.round(L), mu, v), nbCdf(Math.round(L) - 1, mu, v)];
  const u = nbCdf(Math.floor(L), mu, v); return [1 - u, u];
}
function legProb(l) {
  // The app's blended probability at its own line, shifted by how much the projection says the line change matters.
  const [mo0] = modelOU(l.dist, l.mu, l.appLine), [mo1, mu1] = modelOU(l.dist, l.mu, l.line);
  const blendOver0 = l.appSide === "OVER" ? l.appProb : 1 - l.appProb;
  const over = Math.min(.99, Math.max(.01, blendOver0 + (mo1 - mo0)));
  const push = Math.max(0, 1 - mo1 - mu1);
  return l.side === "OVER" ? over : Math.max(.01, 1 - over - push);
}
function slipAdd(k, side) {
  const p = PICKS[k]; if (!p) return;
  if (SLIP.some(l => l.player_id === p.player_id && l.stat === p.stat)) { flash("Already in your parlay"); return; }
  SLIP.push({sport: SPORT, player: p.player, player_id: p.player_id, team: p.team, stat: p.stat, game: p.game, game_id: p.game_id,
    side: side || p.side, line: p.line, price: p.price ?? -110, appLine: p.line, appSide: p.side, appProb: p.prob, mu: p.projection,
    dist: p.dist, grade: p.grade, src: p.line_source, date: D.date});
  saveSlip(); renderSlip(); flash(`Added ${p.player} to parlay (${SLIP.length})`);
}
function flash(msg) { let el = document.getElementById("toast"); if (!el) { el = document.createElement("div"); el.id = "toast";
  el.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:10px 16px;border-radius:99px;font-weight:600;z-index:9;transition:opacity .3s";
  document.body.appendChild(el); } el.textContent = msg; el.style.opacity = 1; clearTimeout(el._t); el._t = setTimeout(() => el.style.opacity = 0, 1600); }
function renderSlip() {
  const btn = $("#parlayBtn"); btn.style.display = ""; btn.textContent = SLIP.length ? `Parlays (${SLIP.length})` : "Parlays";
  const box = $("#slipBox"); if (!box) return;
  const legs = SLIP.map(l => ({...l, p: legProb(l)}));
  let hit = 1, pay = 1; legs.forEach(l => { hit *= l.p; pay *= dec(l.price); });
  const ev = hit * pay - 1, warn = [];
  const games = {}; legs.forEach(l => (games[l.game_id] = (games[l.game_id] || 0) + 1));
  if (Object.values(games).some(n => n > 1)) warn.push("Two or more legs share a game: they're correlated, so the real hit chance can differ from the estimate (and many books only allow these as a same-game parlay).");
  if (new Set(legs.map(l => l.player_id)).size < legs.length) warn.push("Same player twice: these legs move together. Treat the hit chance as rough.");
  legs.forEach(l => { if (l.p - impl(l.price) < 0) warn.push(`${l.player} ${l.side === "OVER" ? "O" : "U"} ${l.line} ${l.stat} has no edge at ${fmtPrice(l.price)}: it lowers the ticket's value.`); });
  const estP = [...new Set(legs.filter(l => l.src === "est.").map(l => l.player))];
  if (estP.length) warn.push(`Estimated app line for ${estP.join(", ")}: enter your book's line and price.`);
  legs.forEach(l => { if (l.date && l.date !== D.date && l.sport === SPORT) warn.push(`${l.player} was added on ${l.date}: the projection may be outdated.`); });
  const grade = !legs.length ? "" : ev >= .25 ? "A" : ev >= .10 ? "B" : ev >= 0 ? "C" : "-";
  const fair = hit > 0 && hit < 1 ? american(1 / hit) : null;
  box.innerHTML = !legs.length ? `<div class="small">Tap <b>+ Add to parlay</b> on any prop (open a pick to see it), or search below. Legs can come from the NBA, NFL and NHL pages.</div>
      <input type="search" id="slipSearch" placeholder="Search a player to add…" style="margin:10px 0 0">${'<div id="slipResults"></div>'}`
    : `${legs.map((l, i) => `<div style="padding:8px 0;border-top:${i ? "1px solid var(--line)" : "0"}">
        <div class="row"><div class="who"><div class="name">${esc(l.player)} <span class="small">${l.sport !== SPORT ? esc(l.sport) + " · " : ""}${esc(l.stat)} · ${esc(l.game)}</span></div>
          <div class="meta">model ${pct(l.p)} · edge ${((l.p - impl(l.price)) * 100).toFixed(1)}% · proj ${l.mu}</div></div>
          <button class="chip" onclick="slipDel(${i})" aria-label="remove">✕</button></div>
        <div class="row" style="gap:6px;margin-top:6px">
          <button class="chip ${l.side === "OVER" ? "on" : ""}" onclick="slipSet(${i},'side','OVER')">Over</button>
          <button class="chip ${l.side === "UNDER" ? "on" : ""}" onclick="slipSet(${i},'side','UNDER')">Under</button>
          <input type="number" step="0.5" inputmode="decimal" value="${l.line}" onchange="slipSet(${i},'line',this.value)" style="width:76px;background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:6px;font-size:15px" aria-label="line">
          <input type="number" inputmode="numeric" value="${l.price}" onchange="slipSet(${i},'price',this.value)" style="width:76px;background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:6px;font-size:15px" aria-label="price">
        </div></div>`).join("")}
      <div class="stats" style="margin-top:10px">
        <div><span>Parlay odds</span><strong>${fmtPrice(american(pay))}</strong></div>
        <div><span>Hit chance</span><strong>${(hit * 100).toFixed(1)}%</strong></div>
        <div><span>Fair odds</span><strong>${fair == null ? "–" : fmtPrice(fair)}</strong></div>
        <div><span>Value</span><strong class="${ev >= 0 ? "WIN" : "LOSS"}">${(ev * 100).toFixed(0)}%</strong></div>
      </div>
      <div class="row" style="margin:6px 0"><div class="grade g${grade}">${grade}</div>
        <div class="small" style="margin-left:8px">${ev >= 0 ? `Model says this ticket is worth more than the payout${ev >= .25 ? " by a lot" : ""}.` : "Model says the payout is too low for the risk."}
        Value runs optimistic (it multiplies each leg's edge), so treat it as a ranking, not a promise.</div></div>
      ${warn.length ? `<ul class="why">${warn.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      <input type="search" id="slipSearch" placeholder="Add another leg: search a player…" style="margin:10px 0 0"><div id="slipResults"></div>
      <button class="chip" style="margin-top:8px" onclick="SLIP=[];saveSlip();renderSlip()">Clear parlay</button>`;
  const q = $("#slipSearch"); q && q.addEventListener("input", () => slipSearch(q.value));
}
function slipSearch(q) {
  const t = q.trim().toLowerCase().split(/\s+/).filter(Boolean), out = $("#slipResults"); if (!t.length) { out.innerHTML = ""; return; }
  const rows = Object.entries(PICKS).filter(([k, p]) => t.every(x => `${p.player} ${p.team} ${p.stat}`.toLowerCase().includes(x)))
    .sort((a, b) => b[1].score - a[1].score).slice(0, 8);
  out.innerHTML = rows.map(([k, p]) => `<div class="row" style="padding:6px 0;border-top:1px solid var(--line)">
      <div class="who"><div class="name">${esc(p.player)} <span class="small">${esc(p.stat)} ${p.line}</span></div>
        <div class="meta">proj ${p.projection} · model likes ${p.side === "OVER" ? "Over" : "Under"} ${pct(p.prob)} · ${esc(p.line_source)}</div></div>
      <button class="chip" onclick="slipAdd('${k}','OVER')">+O</button><button class="chip" onclick="slipAdd('${k}','UNDER')">+U</button></div>`).join("")
    || `<div class="small" style="padding:6px 0">No props found on this page${SPORT !== "NBA" ? "" : ""}.</div>`;
}
function slipDel(i) { SLIP.splice(i, 1); saveSlip(); renderSlip(); }
function slipSet(i, k, v) { const l = SLIP[i];
  if (k === "side") { if (l.side !== v) { l.side = v; l.price = -110; flash("Side flipped: enter your book's price for it"); } } else if (!isNaN(parseFloat(v))) l[k] = k === "price" ? parseInt(v) : parseFloat(v);
  saveSlip(); renderSlip(); }
function slipLoad(type) { const t = ((D.parlays || {}).tickets || []).find(x => x.type === type); if (!t) return;
  SLIP = t.legs.filter(l => l.dist).map(l => ({sport: SPORT, player: l.player, player_id: l.player_id, team: l.team, stat: l.stat, game: l.game,
    game_id: l.game_id, side: l.side, line: l.line, price: l.price, appLine: l.line, appSide: l.side, appProb: l.prob, mu: l.projection,
    dist: l.dist, grade: l.grade, src: l.line_source, date: D.date}));
  saveSlip(); renderSlip(); $("#slipBox").scrollIntoView({behavior: "smooth"}); }
function dec(p) { p = Number(p) || -110; return 1 + (p > 0 ? p / 100 : 100 / -p); }
function american(d) { return d >= 2 ? Math.round((d - 1) * 100) : Math.round(-100 / (d - 1)); }

// ---- parlays
function renderParlays() {
  const P = D.parlays || {}, T = P.tickets || [], R = P.record || {};
  const byType = R.by_type || {}, recent = R.recent || [];
  const anyRec = Object.values(byType).some(x => x.w + x.l);
  if (!T.length && !anyRec) return;
  $("#parlayBtn").style.display = "";
  const s = x => x.side === "OVER" ? "O" : "U";
  const legRow = l => {
    const bb = bestBook(l);
    return `<div class="row" style="padding:6px 0;border-top:1px solid var(--line)">
      <div class="grade g${l.grade}">${l.grade}</div>
      <div class="who"><div class="name">${esc(l.player)} <span class="side ${l.side}" style="font-size:13px">${s(l)} ${l.line} ${esc(l.stat)}</span></div>
        <div class="meta">${esc(l.game)} · ${pct(l.prob)} · ${bb ? `best: ${esc(bb[0])} ${fmtPrice(bb[1][1])}` : esc(l.line_source)}</div></div>
      <div class="bet"><div class="small">${fmtPrice(l.price)}</div>${l.result ? `<div class="res ${l.result}">${l.result}</div>` : ""}</div></div>`;
  };
  const card = t => `<div class="card" style="padding:12px 14px">
      <div class="row"><div class="who"><div class="name" style="font-size:16px">${esc(t.label)} · ${t.legs.length} legs</div>
        ${t.type.startsWith("double") ? `<div class="small" style="color:var(--gold)">Aims for even money: win doubles your stake</div>` : ""}
        <div class="meta">model hit chance ${t.hit < 0.1 ? (t.hit * 100).toFixed(1) + "%" : pct(t.hit)} · value ${(t.ev * 100).toFixed(0)}%${t.locked ? " · locked" : ""}${t.type === "allgames" ? ` · ${t.legs.length} of ${t.games_total} games${(t.missing || []).length ? " (no usable pick in " + t.missing.length + ")" : ""}` : ""}</div></div>
        <div class="bet"><div class="side OVER" style="font-size:17px">${fmtPrice(t.odds)}</div><div class="small">pays ${t.payout.toFixed(2)}×</div>
        ${t.result ? `<div class="res ${t.result}">${t.result}</div>` : ""}</div></div>
      ${t.legs.map(legRow).join("")}
      ${!t.result && !t.locked && t.legs.every(l => l.dist) ? `<button class="chip" style="margin-top:8px" onclick="slipLoad('${t.type}')">Check / edit in parlay checker</button>` : ""}</div>`;
  const tbl = Object.values(byType).filter(x => x.w + x.l);
  $("#parlayBox").innerHTML = `<div class="note" style="margin-top:0">Built from today's graded picks on real lines, one leg per game,
      only minus-money legs with a positive edge and a 60%+ model probability. <b>No player appears on more than one ticket</b>, so one bad prop can only sink one ticket. <b>Value</b> = model hit chance × payout − 1. Hit chance assumes the games are independent.
      Check each line in your book before placing. Parlays swing hard, so keep stakes small.</div>
    ${T.length ? T.map(card).join("") : `<div class="empty">No parlay with positive value today (not enough real-line edges in different games).</div>`}
    ${tbl.length ? `<div class="sect">Parlay track record (1 unit per ticket)</div><div class="card scroll"><table><tr><th></th><th>W-L</th><th>Profit</th></tr>
      ${tbl.map(x => `<tr><td>${esc(x.label)}</td><td>${x.w}-${x.l}</td><td class="${x.units >= 0 ? "WIN" : "LOSS"}">${(x.units > 0 ? "+" : "") + x.units.toFixed(1)}u</td></tr>`).join("")}</table></div>` : ""}
    ${recent.filter(t => t.result).length ? `<div class="sect">Recent tickets</div>${recent.filter(t => t.result).slice(0, 6).map(t => card({...t, label: t.date + " · " + t.label})).join("")}` : ""}`;
}
renderParlays();
if (!D.backtest) renderSlip();

// ---- team bets
function renderTeam() {
  const T = D.team || {}; const all = T.all || [], shown = T.picks || [], rec = T.record || {};
  if (!all.length && !shown.length && !(rec.all && (rec.all.w + rec.all.l))) return;
  $("#teamBtn").style.display = "";
  const shownKey = new Set(shown.map(p => p.game_id + "|" + p.market));
  const byGame = {};
  (all.length ? all : shown).forEach(p => (byGame[p.game_id] = byGame[p.game_id] || []).push(p));
  shown.filter(p => p.locked).forEach(p => { if (!(byGame[p.game_id] || []).some(x => x.market === p.market)) (byGame[p.game_id] = byGame[p.game_id] || []).push(p); });
  const g2 = Object.fromEntries(D.games.map(g => [g.id, g]));
  const row = p => {
    const gr = p.grade || "-";
    return `<div class="pick" onclick="this.classList.toggle('open')"><div class="row">
      <div class="grade g${gr}">${gr}</div>
      <div class="who"><div class="name">${esc(p.pick)} <span class="small">${p.price > 0 ? "+" + p.price : p.price}</span></div>
        <div class="meta">${esc(p.market)} · proj ${esc(p.proj)}${p.locked ? " · locked" : ""}</div></div>
      <div class="bet"><div class="side ${p.edge >= 0.015 ? "OVER" : ""}" style="font-size:14px">${(p.edge * 100).toFixed(1)}%</div>
        <div class="small">${pct(p.prob)} win</div>
        ${p.result ? `<div class="res ${p.result}">${esc(p.final || "")} · ${p.result}</div>` : ""}</div></div>
      <div class="detail"><div class="small">Model alone: ${pct(p.model_prob)} · blended with the market: ${pct(p.prob)} · edge vs price ${(p.edge * 100).toFixed(1)}%</div>
        ${(p.notes || []).length ? `<ul class="why">${p.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}</div></div>`;
  };
  const cards = Object.entries(byGame).map(([gid, ps]) => {
    const g = g2[gid] || {}; const head = ps[0];
    ps.sort((a, b) => ["Moneyline", "Spread", "Puck line", "Total"].indexOf(a.market) - ["Moneyline", "Spread", "Puck line", "Total"].indexOf(b.market));
    return `<div class="card"><div class="gh" style="cursor:default"><div><h3>${esc(head.away)} @ ${esc(head.home)}</h3>
      <div class="meta">${esc(g.time || "")}${g.odds ? " · " + esc(g.odds) : ""}${g.total ? " · O/U " + g.total : ""}</div></div></div>${ps.map(row).join("")}</div>`;
  }).join("");
  const r = rec.all || {w: 0, l: 0};
  const tbl = rows => (rows || []).length ? `<div class="card scroll"><table><tr><th></th><th>W-L</th><th>Win%</th><th>Profit</th></tr>${rows.map(x => `<tr><td>${esc(x.label)}</td><td>${x.w}-${x.l}</td><td>${x.pct == null ? "–" : (x.pct * 100).toFixed(0) + "%"}</td><td class="${x.units >= 0 ? "WIN" : "LOSS"}">${(x.units > 0 ? "+" : "") + x.units.toFixed(1)}u</td></tr>`).join("")}</table></div>` : "";
  $("#teamBox").innerHTML = `<div class="card" style="padding:12px 14px;border-color:var(--gold)"><b style="color:var(--gold)">Experimental${T.banner ? "" : ": no proven edge"}.</b>
    <span class="small">${T.banner ? esc(T.banner) : `In the October backtests, team bets graded A–C lost money in every sport (65–109 combined, about −32 units).
    Sides and totals are the sharpest markets in betting. Use these as a second opinion, not as bets. The live record below shows whether that changes.`}</span></div>
    <div class="note">Moneyline, spread/puck line and total for every game. Grades: A ≥ 5% edge, B ≥ 3%, C ≥ 1.5%.</div>
    ${cards || '<div class="empty">No team lines yet.</div>'}
    ${(r.w + r.l) ? `<div class="sect">Team bets track record · ${r.w}-${r.l}</div>${tbl(rec.by_grade)}${tbl(rec.by_market)}` : ""}`;
}
renderTeam();

// ---- live / halftime calculator
const HSTATS = ["PTS","REB","AST","3PM","PRA","PR","PA","RA","STL","BLK"];
const COUNT = new Set(["3PM","STL","BLK"]);
const DK_TYPES = {"Total Points":"PTS","Total Rebounds":"REB","Total Assists":"AST","Total 3-Point Field Goals":"3PM",
  "Total Points and Rebounds":"PR","Total Points and Assists":"PA","Total Assists and Rebounds":"RA",
  "Total Points, Rebounds, and Assists":"PRA"};
const hasRates = !D.backtest && D.games.some(g => (g.projections || []).some(r => r.rate && r.pid));
const LIVE = {box: {}, lines: {}, margin: {}, elapsed: 24, gameId: null};
function phi(x){ const t=1/(1+0.2316419*Math.abs(x)); const d=0.3989423*Math.exp(-x*x/2);
  const p=d*t*(0.3193815+t*(-0.3565638+t*(1.781478+t*(-1.821256+t*1.330274)))); return x>0?1-p:p; }
function poissonCdf(k, mu){ if(k<0) return 0; let s=0, term=Math.exp(-mu); for(let i=0;i<=k;i++){ if(i>0) term*=mu/i; s+=term; } return Math.min(1,s); }
function impl(p){ p=Number(p); if(!p) return null; return p>0?100/(p+100):-p/(-p+100); }
const statVal = (b, stat) => ({PTS:b.pts, REB:b.reb, AST:b.ast, "3PM":b.fg3, STL:b.stl, BLK:b.blk,
  PRA:b.pts+b.reb+b.ast, PR:b.pts+b.reb, PA:b.pts+b.ast, RA:b.reb+b.ast})[stat];

function liveCompute(r, stat, o) {
  const {line, m1, v1, fouls, margin} = o;
  const elapsed = Math.max(0, Math.min(47, o.elapsed ?? 24));
  const notes = [], left = 48 - elapsed;
  const expSoFar = r.pmin * elapsed / 48, w = Math.min(0.5, elapsed / 48);
  const role = expSoFar >= 2 ? Math.max(0.5, Math.min(1.6, m1 / expSoFar)) : 1;
  let m2 = r.pmin * left / 48 * (1 - w + w * role);
  if (role >= 1.2) notes.push(`${m1} min so far vs ~${expSoFar.toFixed(0)} expected: bigger role, remaining minutes raised`);
  if (role <= 0.8 && expSoFar >= 2) notes.push(`${m1} min so far vs ~${expSoFar.toFixed(0)} expected: smaller role, remaining minutes cut`);
  if (fouls >= 5) { m2 *= 0.7; notes.push(`${fouls} fouls: minutes trimmed 30%`); }
  else if (fouls >= 4 && elapsed < 40) { m2 *= 0.8; notes.push(`${fouls} fouls: minutes trimmed 20%`); }
  else if (fouls === 3 && elapsed <= 24) { m2 *= 0.92; notes.push("3 fouls by halftime: minutes trimmed 8%"); }
  const starter = r.pmin >= 28, am = Math.abs(margin || 0);
  if (am >= 20) { m2 *= starter ? (elapsed >= 36 ? 0.6 : 0.75) : 1.15; notes.push(`${am}-point game: blowout risk, ${starter ? "starter minutes cut" : "bench minutes up"}`); }
  else if (am >= 15) { m2 *= starter ? 0.88 : 1.08; notes.push(`${am}-point game: some blowout risk`); }
  m2 = Math.max(0, Math.min(m2, left - 0.5));
  const pre = r.rate[stat] || 0;
  const r1 = m1 >= 4 ? v1 / m1 : pre;
  const rate2 = 0.8 * pre + 0.2 * r1;
  if (m1 >= 4 && r1 > pre * 1.4) notes.push("Hot so far: production regressed toward pregame rate");
  if (m1 >= 4 && r1 < pre * 0.6) notes.push("Cold so far: production expected to bounce back toward pregame rate");
  const mu2 = Math.max(0.01, rate2 * m2), proj = v1 + mu2, need = line - v1;
  let pOver, pUnder;
  if (need <= 0) { pOver = 1; pUnder = 0; }
  else if (COUNT.has(stat)) { const integer = Math.abs(need - Math.round(need)) < 1e-9;
    if (integer) { pUnder = poissonCdf(need - 1, mu2); pOver = 1 - poissonCdf(need, mu2); } else { pUnder = poissonCdf(Math.floor(need), mu2); pOver = 1 - pUnder; } }
  else { const sdg = (r.sd || {})[stat] || Math.sqrt(Math.max(pre * r.pmin, 1));
    const sd = Math.max(Math.sqrt(mu2), sdg * Math.sqrt(Math.max(m2, 1) / Math.max(r.pmin, 1)));
    const integer = Math.abs(line - Math.round(line)) < 1e-9;
    if (integer) { pOver = 1 - phi((need + 0.5 - mu2) / sd); pUnder = phi((need - 0.5 - mu2) / sd); } else { pOver = 1 - phi((need - mu2) / sd); pUnder = 1 - pOver; } }
  const io = impl(o.over) ?? impl(-115), iu = impl(o.under) ?? impl(-115);
  const fair = io / (io + iu);
  pOver = fair + 0.6 * (pOver - fair); pUnder = (1 - fair) + 0.6 * (pUnder - (1 - fair));
  const eo = pOver - io, eu = pUnder - iu;
  const side = eo >= eu ? "OVER" : "UNDER", edge = need <= 0 ? 0 : Math.max(eo, eu);
  return {side, edge, prob: side === "OVER" ? pOver : pUnder, proj, need, m2, mu2, pre: pre * r.pmin, notes,
          verdict: need <= 0 ? "Already over" : edge >= 0.06 ? `Bet ${side}` : edge >= 0.03 ? `Lean ${side}` : "Pass"};
}

async function getJSON(url) { const r = await fetch(url, {cache: "no-store"}); if (!r.ok) throw new Error(r.status); return r.json(); }
function clockToElapsed(st) {
  const period = st.period || 0, state = (st.type || {}).state;
  if (state === "pre" || !period) return 0;
  if (state === "post") return 48;
  const c = String(st.displayClock || "12:00");
  const left = c.includes(":") ? (+c.split(":")[0] + (+c.split(":")[1]) / 60) : +c / 60;
  return Math.min(48, (Math.min(period, 4) - 1) * 12 + (12 - left));
}
async function loadLive() {
  const gid = $("#hGame").value; LIVE.gameId = gid;
  const g = D.games.find(x => x.id === gid);
  $("#hStatus").textContent = "Loading live box score…";
  try {
    const summ = await getJSON(`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=${gid}`);
    const comp = ((summ.header || {}).competitions || [{}])[0];
    const st = comp.status || {};
    LIVE.elapsed = clockToElapsed(st);
    const scores = {};
    (comp.competitors || []).forEach(c => scores[(c.team || {}).abbreviation] = +c.score || 0);
    const abbrs = Object.keys(scores);
    abbrs.forEach(a => LIVE.margin[a] = scores[a] - (scores[abbrs.find(x => x !== a)] || 0));
    LIVE.box = {};
    ((summ.boxscore || {}).players || []).forEach(t => (t.statistics || []).forEach(sg => {
      const lab = sg.labels || sg.names || [], ix = k => lab.indexOf(k);
      (sg.athletes || []).forEach(a => {
        const v = k => { const s = (a.stats || [])[ix(k)]; if (s == null) return 0; return parseFloat(String(s).split("-")[0]) || 0; };
        LIVE.box[(a.athlete || {}).id] = {min: v("MIN"), pts: v("PTS"), reb: v("REB"), ast: v("AST"), fg3: v("3PT"),
          stl: v("STL"), blk: v("BLK"), pf: v("PF"), team: (t.team || {}).abbreviation};
      });
    }));
    const desc = (st.type || {}).shortDetail || (st.type || {}).description || "";
    $("#hStatus").textContent = `${desc} · ${abbrs.map(a => `${a} ${scores[a]}`).join(" – ")} · loading lines…`;
    LIVE.lines = {};
    // DraftKings live props are provider 200; provider 100 is the pregame feed (fallback, flagged).
    async function loadProvider(pid, live) {
      let page = 1, pages = 1, found = 0;
      while (page <= pages && page <= 3) {
        let pb;
        try { pb = await getJSON(`https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/${gid}/competitions/${gid}/odds/${pid}/propBets?limit=1000&page=${page}`); }
        catch (e) { return found; }
        pages = pb.pageCount || 1; page++;
        const grp = {};
        (pb.items || []).forEach(it => {
          const stat = DK_TYPES[(it.type || {}).name]; if (!stat || !it.odds) return;
          const m = ((it.athlete || {}).$ref || "").match(/athletes\/(\d+)/); if (!m) return;
          (grp[m[1] + "|" + stat] = grp[m[1] + "|" + stat] || []).push(it);
        });
        Object.entries(grp).forEach(([k, its]) => {
          if (its.length < 2 || LIVE.lines[k]) return;          // one side suspended -> skip
          const ln = parseFloat(((its[0].odds || {}).total || {}).value), ln2 = parseFloat(((its[1].odds || {}).total || {}).value);
          if (isNaN(ln) || ln !== ln2) return;
          const pr = it => parseInt(String(((it.odds || {}).american || {}).value || "").replace("+", "")) || null;
          LIVE.lines[k] = {line: ln, over: pr(its[0]), under: pr(its[1]), live};
          found++;
        });
      }
      return found;
    }
    if (LIVE.elapsed > 0 && LIVE.elapsed < 48) await loadProvider(200, true);
    await loadProvider(100, LIVE.elapsed <= 0);     // pregame lines fill any gaps (flagged once the game starts)
    const nLines = Object.keys(LIVE.lines).length, nLive = Object.values(LIVE.lines).filter(x => x.live).length;
    const lineTxt = !nLines ? "no DraftKings lines" : nLive ? `${nLive} live DraftKings lines` : `${nLines} DraftKings lines (pregame, not live: check your book)`;
    $("#hStatus").textContent = `${desc} · ${abbrs.map(a => `${a} ${scores[a]}`).join(" – ")} · ${lineTxt} · updated ${new Date().toLocaleTimeString([], {hour: "numeric", minute: "2-digit"})}`;
    $("#hElapsed").value = LIVE.elapsed.toFixed(0);
    scanLive(g);
    fillPlayer();
  } catch (e) {
    $("#hStatus").textContent = "Couldn't load live data (" + e.message + "). You can still enter numbers manually.";
  }
}
function scanLive(g) {
  const rows = [];
  if (LIVE.elapsed <= 0) { $("#hScan").innerHTML = `<div class="empty">Game hasn't started. Check back at halftime.</div>`; return; }
  (g.projections || []).filter(r => r.rate && r.pid && LIVE.box[r.pid]).forEach(r => {
    const b = LIVE.box[r.pid];
    HSTATS.forEach(stat => {
      const L = LIVE.lines[r.pid + "|" + stat]; if (!L) return;
      const res = liveCompute(r, stat, {line: L.line, m1: b.min, v1: statVal(b, stat), fouls: b.pf,
        margin: LIVE.margin[r.team] || 0, over: L.over, under: L.under, elapsed: LIVE.elapsed});
      if (res.edge >= 0.03) rows.push({r, stat, L, b, res});
    });
  });
  rows.sort((a, b) => b.res.edge - a.res.edge);
  const seen = new Set(), top = rows.filter(x => !seen.has(x.r.pid) && seen.add(x.r.pid)).slice(0, 12);
  $("#hScan").innerHTML = top.length ? top.map((x, i) => `<div class="pick" data-i="${i}">
      <div class="row"><div class="grade ${!x.L.live ? "gC" : x.res.edge >= 0.06 ? "gA" : "gB"}" style="width:auto;padding:0 6px">${!x.L.live ? "Check" : x.res.edge >= 0.06 ? "Bet" : "Lean"}</div>
      <div class="who"><div class="name">${esc(x.r.player)}</div>
        <div class="meta">${esc(x.r.team)} · ${x.stat} · has ${statVal(x.b, x.stat)} in ${x.b.min} min${x.b.pf >= 3 ? ` · ${x.b.pf} fouls` : ""}${x.L.live ? "" : ` · <span style="color:var(--gold)">pregame line: check book</span>`}</div></div>
      <div class="bet"><div class="side ${x.res.side}">${x.res.side === "OVER" ? "O" : "U"} ${x.L.line}</div>
        <div class="small">proj ${x.res.proj.toFixed(1)} · ${(x.res.edge * 100).toFixed(0)}% edge</div></div></div></div>`).join("")
    : `<div class="empty">No clear edges right now${Object.keys(LIVE.lines).length ? "" : " (no DraftKings lines found; use the calculator with your book's line)"}.</div>`;
  $("#hScan").querySelectorAll(".pick").forEach(el => el.addEventListener("click", () => {
    const x = top[+el.dataset.i]; $("#hPlayer").value = x.r.player; $("#hStat").value = x.stat; fillPlayer();
    $("#hOut").scrollIntoView({behavior: "smooth"});
  }));
}
function fillPlayer() {
  const g = D.games.find(x => x.id === $("#hGame").value); if (!g) return;
  const r = (g.projections || []).find(x => x.player === $("#hPlayer").value); if (!r) return;
  const b = LIVE.box[r.pid], stat = $("#hStat").value;
  if (b) { $("#hMin").value = b.min; $("#hVal").value = statVal(b, stat); $("#hFouls").value = b.pf;
           $("#hMargin").value = LIVE.margin[r.team] || 0; }
  const L = LIVE.lines[r.pid + "|" + stat];
  if (L) { $("#hLine").value = L.line; $("#hOver").value = L.over ?? ""; $("#hUnder").value = L.under ?? ""; }
  halfCalc();
}
function halfCalc() {
  const g = D.games.find(x => x.id === $("#hGame").value); if (!g) return;
  const r = (g.projections || []).find(x => x.player === $("#hPlayer").value); if (!r || !r.rate) return;
  const stat = $("#hStat").value, line = parseFloat($("#hLine").value);
  const m1 = parseFloat($("#hMin").value), v1 = parseFloat($("#hVal").value);
  if ([line, m1, v1].some(x => isNaN(x))) { $("#hOut").innerHTML = `<div class="card" style="padding:14px"><div class="small">Pregame: ${r.pmin} min, ${((r.rate[stat] || 0) * r.pmin).toFixed(1)} ${stat} projected. Load the live game or enter the numbers.</div></div>`; return; }
  const res = liveCompute(r, stat, {line, m1, v1, fouls: parseInt($("#hFouls").value || "0"),
    margin: parseInt($("#hMargin").value || "0"), over: $("#hOver").value, under: $("#hUnder").value,
    elapsed: parseFloat($("#hElapsed").value || "24")});
  const color = res.verdict.startsWith("Bet") ? (res.side === "OVER" ? "var(--over)" : "var(--under)")
    : res.verdict.startsWith("Lean") ? "var(--gold)" : res.verdict.startsWith("Already") ? "var(--over)" : "var(--mute)";
  $("#hOut").innerHTML = `<div class="card" style="padding:14px">
    <div class="verdict" style="color:${color}">${res.verdict}</div>
    <div class="stats">
      <div><span>Projected final</span><strong>${res.proj.toFixed(1)}</strong></div>
      <div><span>Still needs</span><strong>${Math.max(0, res.need).toFixed(1)}</strong></div>
      <div><span>${res.side === "OVER" ? "Over" : "Under"} prob</span><strong>${pct(res.prob)}</strong></div>
      <div><span>Edge</span><strong>${(res.edge * 100).toFixed(1)}%</strong></div>
      <div><span>Minutes left</span><strong>${res.m2.toFixed(1)}</strong></div>
      <div><span>More ${stat}</span><strong>${res.mu2.toFixed(1)}</strong></div>
      <div><span>Pregame proj</span><strong>${res.pre.toFixed(1)}</strong></div>
      <div><span>Pregame min</span><strong>${r.pmin}</strong></div>
    </div>
    ${res.notes.length ? `<ul class="why">${res.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    <div class="small" style="margin-top:6px">"Bet" needs a 6%+ edge and "Lean" 3–6%, set higher than pregame because live markets carry more vig.</div></div>`;
}
function halfPlayers() {
  const g = D.games.find(x => x.id === $("#hGame").value) || D.games[0];
  const rows = (g.projections || []).filter(r => r.rate).sort((a, b) => a.team.localeCompare(b.team) || b.pmin - a.pmin);
  $("#hPlayer").innerHTML = rows.map(r => `<option value="${esc(r.player)}">${esc(r.team)} · ${esc(r.player)}</option>`).join("");
}
if (hasRates) {
  $("#halfBtn").style.display = "";
  $("#hGame").innerHTML = D.games.map(g => `<option value="${g.id}">${esc(g.away)} @ ${esc(g.home)} · ${esc(g.time)}</option>`).join("");
  $("#hStat").innerHTML = HSTATS.map(s => `<option>${s}</option>`).join("");
  $("#hGame").addEventListener("change", () => { halfPlayers(); loadLive(); });
  $("#hRefresh").addEventListener("click", loadLive);
  $("#hPlayer").addEventListener("change", fillPlayer);
  $("#hStat").addEventListener("change", fillPlayer);
  ["hLine","hMin","hVal","hFouls","hMargin","hOver","hUnder","hElapsed"].forEach(id => $("#" + id).addEventListener("input", halfCalc));
  halfPlayers();
  let loaded = false;
  document.querySelector('nav button[data-v=half]').addEventListener("click", () => { if (!loaded) { loaded = true; loadLive(); } });
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
    links = [switch] if isinstance(switch, tuple) else (switch or [])
    sw = "".join(f' <a class="badge" style="color:var(--blue);text-decoration:none" href="{h}">{l} →</a>' for l, h in links)
    return (TEMPLATE.replace("__TITLE__", title).replace("__SWITCH__", sw).replace("__NOTE__", note)
            .replace("__DATE__", payload.get("label") or payload["date"]).replace("__DATA__", data))
