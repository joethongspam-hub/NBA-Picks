"""Small HTTP layer with retries, polite concurrency and an on-disk cache.

Everything that touches the network goes through `Http.get_json`, which makes
it trivial to swap in a fake for tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class Http:
    def __init__(self, cache_dir: str | os.PathLike = ".cache", ttl_seconds: int = 3 * 3600,
                 timeout: int = 20, retries: int = 3):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    def _key(self, url: str, params: dict | None) -> Path:
        raw = url + "?" + json.dumps(params or {}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + ".json")

    def get_json(self, url: str, params: dict | None = None, ttl: int | None = None) -> Any:
        ttl = self.ttl if ttl is None else ttl
        path = self._key(url, params)
        if ttl > 0 and path.exists() and time.time() - path.stat().st_mtime < ttl:
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        last_err: Exception | None = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                data = r.json()
                if ttl > 0:
                    path.write_text(json.dumps(data))
                return data
            except Exception as e:  # network hiccup, 5xx, bad JSON
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"GET {url} failed: {last_err}")
