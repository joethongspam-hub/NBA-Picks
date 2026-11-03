"""Model report: what's working and what isn't, from graded live picks.

Sections
  calibration   predicted win probability vs actual hit rate
  profit        units won betting each pick as a 1-unit single at its price
  market        did DraftKings move toward or against our side (open -> close)?
  misses        why losses lost: minutes/role miss vs production (variance) miss
  segments      win rate by type of pick (side, stat, line source, rest, injuries, last game...)
"""
from __future__ import annotations

from collections import OrderedDict

from .odds import american_to_prob


def _payout(price) -> float:
    """Profit on a 1-unit winning bet."""
    try:
        p = int(price)
    except (TypeError, ValueError):
        p = -110
    return p / 100 if p > 0 else 100 / -p


def _row(label, picks):
    w = sum(r["result"] == "WIN" for r in picks)
    l = sum(r["result"] == "LOSS" for r in picks)
    units = sum(_payout(r.get("price")) if r["result"] == "WIN" else -1.0 for r in picks
                if r["result"] in ("WIN", "LOSS"))
    n = w + l
    return {"label": label, "w": w, "l": l, "pct": round(w / n, 3) if n else None,
            "units": round(units, 2), "roi": round(units / n, 3) if n else None}


def _against_last(r):
    lg = r.get("last_game")
    if lg is None:
        return None
    if r["side"] == "UNDER":
        return lg > r["line"]
    return lg < r["line"]


def _market_move(r):
    """+1 market moved toward our side, -1 against, 0 flat, None unknown."""
    ol, line = r.get("open_line"), r.get("line")
    if ol is None or line is None:
        return None
    if line != ol:
        toward = (line > ol) if r["side"] == "OVER" else (line < ol)
        return 1 if toward else -1
    op, cp = american_to_prob(r.get("open_price")), american_to_prob(r.get("price"))
    if op is None or cp is None or abs(cp - op) < 0.015:
        return 0
    return 1 if cp > op else -1          # our side got more expensive = market agreed


def model_report(graded: list[dict], unit_label: str = "min") -> dict:
    rows = [r for r in graded if r.get("result") in ("WIN", "LOSS")]
    if not rows:
        return {}
    has = lambda r, txt: any(txt in x for x in (r.get("reasons") or []))
    rep = OrderedDict()
    rep["n"] = len(rows)
    rep["overall"] = _row("All picks", rows)

    cal = []
    for lo, hi in ((.50, .55), (.55, .60), (.60, .65), (.65, .70), (.70, 1.01)):
        b = [r for r in rows if lo <= (r.get("prob") or 0) < hi]
        if b:
            x = _row(f"{int(lo * 100)}–{int(min(hi, 1) * 100)}%", b)
            x["predicted"] = round(sum(r["prob"] for r in b) / len(b), 3)
            cal.append(x)
    rep["calibration"] = cal

    rep["profit"] = [_row(f"Grade {g}", [r for r in rows if r.get("grade") == g]) for g in "ABC"
                     if any(r.get("grade") == g for r in rows)]

    mk = [(r, _market_move(r)) for r in rows]
    rep["market"] = [_row(lbl, [r for r, m in mk if m == v]) for lbl, v in
                     (("Line moved toward our side", 1), ("No real move", 0), ("Line moved against us", -1))
                     if any(m == v for _, m in mk)]

    losses = [r for r in rows if r["result"] == "LOSS" and r.get("actual_min") is not None and r.get("minutes")]
    role, var = [], []
    for r in losses:
        err = r["actual_min"] - r["minutes"]
        (role if abs(err) >= max(6, 0.25 * r["minutes"]) else var).append({**r, "min_err": round(err, 1)})
    rep["misses"] = {
        "losses": len(losses), "role": len(role), "variance": len(var),
        "role_more": sum(r["min_err"] > 0 for r in role), "role_less": sum(r["min_err"] < 0 for r in role),
        "examples": [{"player": r["player"], "stat": r["stat"], "side": r["side"], "line": r["line"],
                      "actual": r.get("actual"), "proj_min": r["minutes"], "actual_min": r["actual_min"]}
                     for r in sorted(role, key=lambda r: -abs(r["min_err"]))[:6]],
        "unit": unit_label,
    }

    seg = []
    seg.append(("Side", [_row(s.title(), [r for r in rows if r["side"] == s]) for s in ("OVER", "UNDER")]))
    seg.append(("Line", [_row("Real sportsbook line", [r for r in rows if r.get("line_source") != "est."]),
                         _row("Estimated line", [r for r in rows if r.get("line_source") == "est."])]))
    seg.append(("Last game", [_row("Against last game", [r for r in rows if _against_last(r) is True]),
                              _row("With last game", [r for r in rows if _against_last(r) is False])]))
    seg.append(("Context", [x for x in (
        _row("Back-to-back", [r for r in rows if has(r, "Back-to-back")]),
        _row("Teammate injury boost", [r for r in rows if has(r, " out:")]),
        _row("Opponent defense edge", [r for r in rows if has(r, "allows") or has(r, "limits")]),
        _row("Questionable player", [r for r in rows if r.get("status") == "QUESTIONABLE"]),
    ) if x["w"] + x["l"]]))
    stats = sorted({r["stat"] for r in rows})
    seg.append(("Stat", sorted([_row(s, [r for r in rows if r["stat"] == s]) for s in stats],
                               key=lambda x: -(x["w"] + x["l"]))))
    rep["segments"] = [{"title": t, "rows": [x for x in rs if x["w"] + x["l"]]} for t, rs in seg]
    return rep
