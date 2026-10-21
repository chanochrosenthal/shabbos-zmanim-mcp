import time

import pytest

from zmanim_mcp.hebcal import RateLimiter, TTLCache

pytestmark = pytest.mark.anyio


async def test_rate_limiter_spacing_and_window():
    lim = RateLimiter(max_requests=3, per_seconds=0.5, min_interval=0.05)
    t0 = time.monotonic()
    for _ in range(4):
        await lim.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.45  # the 4th request waited for the window


def test_ttl_cache_lru_and_expiry():
    c = TTLCache(max_entries=2)
    c.set("a", 1, ttl=10)
    c.set("b", 2, ttl=10)
    c.set("c", 3, ttl=10)
    assert c.get("a") is None and c.get("c") == 3
    c.set("d", 4, ttl=-1)
    assert c.get("d") is None
