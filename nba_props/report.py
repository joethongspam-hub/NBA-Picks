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
        <div class="meta">${esc(p.team)} vs ${esc(p.opp)}${showGame ? "" : ""} · ${p.stat} · L10 ${p.hit_l10}${p.status!=="ACTIVE"?` · <span style="color:var(--gold)">${p.status}</span>`:""}</div></div>
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
        <div><h3>${esc(g.away)} @ ${esc(g.home)}</h3><div class="meta">${esc(g.time)} · ${vegas}</div></div>
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
    ${recent.map(x => `<tr><td>${x.date.slice(5)} <span class="small">${esc(x.player)}</span></td><td class="${x.side}">${x.side[0]} ${x.stat}</td><td>${x.line}</td><td>${x.actual ?? "–"}</td><td class="${x.result}">${x.result}</td></tr>`).join("")}
    </table></div>` : `<div class="empty">Results appear here after the first day's games are graded.</div>`}${links}`;
}

document.querySelector("nav").addEventListener("click", e => {
  const v = e.target.dataset.v; if (!v) return;
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  document.querySelectorAll(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
});
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
