"""Replay a data snapshot (.cache dir) with no network, for model tuning."""
import json
from pathlib import Path
from nba_props.http import Http


class OfflineHttp(Http):
    def __init__(self, cache_dir):
        super().__init__(cache_dir)

    def get_json(self, url, params=None, ttl=None):
        path = self._key(url, params)
        return json.loads(path.read_text()) if path.exists() else None
