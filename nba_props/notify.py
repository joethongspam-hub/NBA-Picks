"""Phone notification (ntfy.sh) when a run produces new or changed picks.

    python -m nba_props.notify --sport NBA --before old.json --after public/picks.json --url https://...

Reads NTFY_TOPIC from the environment; does nothing if it's unset or the
fresh (not yet locked) picks didn't change since the previous run.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests

STAT_NAMES = {"PTS": "pts", "REB": "reb", "AST": "ast", "3PM": "3PM", "PRA": "PRA", "PR": "P+R", "PA": "P+A",
              "RA": "R+A", "STL": "stl", "BLK": "blk", "PASS_YDS": "pass yds", "PASS_TD": "pass TD",
              "PASS_ATT": "pass att", "PASS_CMP": "comp", "INT": "INT", "RUSH_YDS": "rush yds",
              "RUSH_ATT": "carries", "REC": "rec", "REC_YDS": "rec yds", "RUSH_REC_YDS": "rush+rec yds",
              "ANY_TD": "anytime TD"}


def _fresh(payload: dict) -> list[dict]:
    seen, out = set(), []
    picks = payload.get("top", []) + [p for ps in payload.get("by_game", {}).values() for p in ps]
    for p in sorted(picks, key=lambda p: -p.get("score", 0)):
        k = (p["player_id"], p["stat"], p["side"])
        if not p.get("locked") and k not in seen:
            seen.add(k)
            out.append(p)
    return out


def _key(p):
    return (p["player_id"], p["stat"], p["side"], p["line"])


def build_message(sport: str, before: dict | None, after: dict, force: bool = False) -> tuple[str, str] | None:
    new = _fresh(after) or (_fresh({**after, "top": [dict(p, locked=False) for p in after.get("top", [])],
                                     "by_game": {}}) if force else [])
    if not new:
        return None
    if force:
        before = None
    old_keys = {_key(p) for p in _fresh(before)} if before and before.get("date") == after.get("date") else set()
    new_keys = {_key(p) for p in new}
    if old_keys == new_keys:
        return None
    changed = bool(old_keys)
    a_count = sum(p["grade"] == "A" for p in new)
    label = after.get("label") or after.get("date")
    title = f"{sport} picks {'updated' if changed else 'ready'} · {label}"
    lines = []
    if changed:
        added = len(new_keys - old_keys)
        dropped = len(old_keys - new_keys)
        lines.append(f"{added} new, {dropped} dropped since last run")
    lines.append(f"{len(new)} picks ({a_count} grade A) · {after.get('line_mode', 'estimated')} lines")
    for p in [p for p in new if p["grade"] in ("A", "B")][:5]:
        side = "O" if p["side"] == "OVER" else "U"
        lines.append(f"{p['grade']} · {p['player']} {side} {p['line']:g} {STAT_NAMES.get(p['stat'], p['stat'])} "
                     f"(proj {p['projection']:g})")
    return title, "\n".join(lines)


def send(topic: str, title: str, body: str, url: str) -> None:
    # JSON publishing keeps non-ASCII characters intact in the title.
    r = requests.post("https://ntfy.sh/", timeout=15, json={
        "topic": topic, "title": title, "message": body, "click": url,
        "tags": ["basketball" if title.startswith("NBA") else "football"]})
    r.raise_for_status()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport")
    ap.add_argument("--before")
    ap.add_argument("--after")
    ap.add_argument("--url")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="send even if picks didn't change (test)")
    ap.add_argument("--out", help="write the message to this JSON file instead of sending")
    ap.add_argument("--send-json", help="send a message previously written with --out")
    a = ap.parse_args()
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if a.send_json:
        if not Path(a.send_json).exists() or not topic:
            print("notify: nothing to send" if topic else "notify: NTFY_TOPIC not set")
            return
        m = json.loads(Path(a.send_json).read_text())
        send(topic, m["title"], m["body"], m["url"])
        print("notify: sent")
        return
    before = json.loads(Path(a.before).read_text()) if a.before and Path(a.before).exists() else None
    after = json.loads(Path(a.after).read_text()) if Path(a.after).exists() else None
    msg = build_message(a.sport, before, after, a.force) if after else None
    if not msg:
        print("notify: no new picks, nothing sent")
        return
    if a.out:
        Path(a.out).write_text(json.dumps({"title": msg[0], "body": msg[1], "url": a.url}))
        print("notify: message prepared:", msg[0])
        return
    if a.dry_run or not topic:
        print("notify (not sent):", msg[0], "\n" + msg[1])
        return
    send(topic, msg[0], msg[1], a.url)
    print("notify: sent")


if __name__ == "__main__":
    main()
