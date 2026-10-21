"""Small, polite client for the Hebcal.com REST APIs.

* No API key is needed. Content is licensed CC BY 4.0 by Hebcal.com; every
  tool result carries an attribution string (see ATTRIBUTION).
* Hebcal throttles clients above 90 requests per 10 seconds. This client
  stays far below that: a sliding-window limiter (default 30 requests per
  10 s, at least 120 ms apart) plus an in-memory LRU+TTL cache, so a voice
  assistant asking the same question twice never costs a second request.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict, deque
from typing import Any
from urllib.parse import urlencode

import httpx2 as httpx  # the MCP Python SDK 2.x ships httpx2 (same API as httpx)

BASE = "https://www.hebcal.com"
ATTRIBUTION = "Data: Hebcal.com (hebcal.com), licensed CC BY 4.0. Locations: GeoNames.org (CC BY 4.0)."
USER_AGENT = "shabbos-zmanim-mcp/0.1 (+self-hosted MCP server; credits Hebcal.com, CC BY 4.0)"


class HebcalError(RuntimeError):
    """Hebcal could not be reached or answered with an error."""


class RateLimiter:
    def __init__(self, max_requests: int = 30, per_seconds: float = 10.0, min_interval: float = 0.12):
        self.max_requests = max_requests
        self.per_seconds = per_seconds
        self.min_interval = min_interval
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] > self.per_seconds:
                    self._stamps.popleft()
                wait = 0.0
                if self._stamps and now - self._stamps[-1] < self.min_interval:
                    wait = self.min_interval - (now - self._stamps[-1])
                if len(self._stamps) >= self.max_requests:
                    wait = max(wait, self.per_seconds - (now - self._stamps[0]))
                if wait <= 0:
                    self._stamps.append(now)
                    return
                await asyncio.sleep(wait)


class TTLCache:
    def __init__(self, max_entries: int = 512):
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None or item[0] < time.time():
            if item is not None:
                del self._data[key]
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return item[1]

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._data[key] = (time.time() + ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)


class HebcalClient:
    def __init__(self, base_url: str = BASE, timeout: float = 10.0, limiter: RateLimiter | None = None,
                 cache: TTLCache | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 backoff: float = 0.5):
        self.backoff = backoff
        self.base_url = base_url.rstrip("/")
        self.limiter = limiter or RateLimiter()
        self.cache = cache or TTLCache()
        self.requests_made = 0
        self._client = httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT},
                                         transport=transport, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(self, path: str, params: dict[str, Any], ttl: float = 6 * 3600) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        url = f"{self.base_url}{path}?{urlencode(sorted(clean.items()))}"
        cached = self.cache.get(url)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(3):
            await self.limiter.acquire()
            try:
                self.requests_made += 1
                resp = await self._client.get(url)
            except httpx.HTTPError as exc:  # network trouble: retry with backoff
                last_error = exc
                await asyncio.sleep(self.backoff * (2 ** attempt))
                continue
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("retry-after", "2") or 2)
                last_error = HebcalError("Hebcal rate limit (429)")
                await asyncio.sleep(min(retry_after, 10))
                continue
            if resp.status_code >= 500:
                last_error = HebcalError(f"Hebcal server error {resp.status_code}")
                await asyncio.sleep(self.backoff * (2 ** attempt))
                continue
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:
                raise HebcalError(f"Hebcal returned non-JSON ({resp.status_code})") from exc
            if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
                msg = data.get("error") if isinstance(data, dict) else resp.text[:200]
                raise HebcalError(f"Hebcal error {resp.status_code}: {msg}")
            self.cache.set(url, data, ttl)
            return data
        raise HebcalError(f"Hebcal unreachable: {last_error}")

    # --- typed helpers -------------------------------------------------
    async def zmanim(self, loc_params: dict[str, Any], date_iso: str) -> dict:
        return await self.get_json("/zmanim", {"cfg": "json", "date": date_iso, **loc_params}, ttl=24 * 3600)

    async def calendar(self, params: dict[str, Any], ttl: float = 6 * 3600) -> dict:
        return await self.get_json("/hebcal", {"v": "1", "cfg": "json", **params}, ttl=ttl)

    async def convert(self, params: dict[str, Any]) -> dict:
        return await self.get_json("/converter", {"cfg": "json", **params}, ttl=7 * 24 * 3600)

    async def search_city(self, query: str) -> list[dict]:
        try:
            data = await self.get_json("/complete.php", {"q": query}, ttl=7 * 24 * 3600)
        except HebcalError as exc:
            if "not found" in str(exc).lower():
                return []  # Hebcal answers {"error": "Not Found"} (HTTP 404) when nothing matches
            raise
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
