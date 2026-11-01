"""Game-time weather for NFL games (Open-Meteo, free, no key) + stadium roof types.

Retractable roofs are treated as indoor: they are normally closed in bad
weather, which is the only time weather would matter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nba_props.http import Http

# home team -> (lat, lon, roof)   roof: dome | retractable | open
STADIUMS = {
    "ARI": (33.5276, -112.2626, "retractable"), "ATL": (33.7554, -84.4008, "retractable"),
    "BAL": (39.2780, -76.6227, "open"), "BUF": (42.7738, -78.7870, "open"),
    "CAR": (35.2258, -80.8528, "open"), "CHI": (41.8623, -87.6167, "open"),
    "CIN": (39.0955, -84.5161, "open"), "CLE": (41.5061, -81.6995, "open"),
    "DAL": (32.7473, -97.0945, "retractable"), "DEN": (39.7439, -105.0201, "open"),
    "DET": (42.3400, -83.0456, "dome"), "GB": (44.5013, -88.0622, "open"),
    "HOU": (29.6847, -95.4107, "retractable"), "IND": (39.7601, -86.1639, "retractable"),
    "JAX": (30.3239, -81.6373, "open"), "KC": (39.0489, -94.4839, "open"),
    "LV": (36.0909, -115.1833, "dome"), "LAC": (33.9535, -118.3392, "dome"),
    "LAR": (33.9535, -118.3392, "dome"), "MIA": (25.9580, -80.2389, "open"),
    "MIN": (44.9737, -93.2575, "dome"), "NE": (42.0909, -71.2643, "open"),
    "NO": (29.9511, -90.0812, "dome"), "NYG": (40.8135, -74.0745, "open"),
    "NYJ": (40.8135, -74.0745, "open"), "PHI": (39.9008, -75.1675, "open"),
    "PIT": (40.4468, -80.0158, "open"), "SF": (37.4030, -121.9700, "open"),
    "SEA": (47.5952, -122.3316, "open"), "TB": (27.9759, -82.5033, "open"),
    "TEN": (36.1665, -86.7713, "open"), "WSH": (38.9078, -76.8645, "open"),
}
FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = "temperature_2m,precipitation,snowfall,wind_speed_10m,wind_gusts_10m"


def game_weather(http: Http, game, now: datetime | None = None) -> dict:
    """{'indoor': bool, 'wind': mph, 'gust': mph, 'precip': in/hr, 'snow': in, 'temp': F, 'label': str}"""
    venue = getattr(game, "venue", {}) or {}
    st = STADIUMS.get(game.home.abbr)
    neutral = bool(venue.get("neutral"))
    if venue.get("indoor") is True or (st and st[2] != "open" and not neutral):
        return {"indoor": True, "label": "Indoors"}
    if not st or neutral:
        return {"indoor": None, "label": ""}           # unknown venue (e.g. international game)
    lat, lon, _ = st
    kick = game.date.astimezone(timezone.utc)
    now = now or datetime.now(timezone.utc)
    old = kick < now - timedelta(days=6)
    params = {"latitude": lat, "longitude": lon, "hourly": HOURLY, "wind_speed_unit": "mph",
              "temperature_unit": "fahrenheit", "precipitation_unit": "inch", "timezone": "UTC",
              "start_date": kick.strftime("%Y-%m-%d"), "end_date": (kick + timedelta(hours=4)).strftime("%Y-%m-%d")}
    try:
        data = http.get_json(ARCHIVE if old else FORECAST, params, ttl=30 * 86400 if old else 3 * 3600)
        if not data and old:
            data = http.get_json(FORECAST, params, ttl=30 * 86400)
    except Exception:
        data = None
    h = (data or {}).get("hourly") or {}
    times = h.get("time") or []
    idx = [i for i, t in enumerate(times)
           if kick - timedelta(minutes=30) <= datetime.fromisoformat(t).replace(tzinfo=timezone.utc) <= kick + timedelta(hours=3)]
    if not idx:
        return {"indoor": False, "label": "Outdoors"}

    def avg(k):
        vals = [(h.get(k) or [None] * len(times))[i] for i in idx]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else 0.0

    wx = {"indoor": False, "wind": round(avg("wind_speed_10m"), 1), "gust": round(avg("wind_gusts_10m"), 1),
          "precip": round(avg("precipitation"), 3), "snow": round(sum((h.get("snowfall") or [0] * len(times))[i] or 0 for i in idx), 2),
          "temp": round(avg("temperature_2m"))}
    bits = [f"{wx['temp']}°F", f"wind {wx['wind']:.0f} mph"]
    if wx["snow"] >= 0.1:
        bits.append("snow")
    elif wx["precip"] >= 0.02:
        bits.append("rain")
    wx["label"] = "Outdoors · " + ", ".join(bits)
    return wx
