import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx2 as httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zmanim_mcp.hebcal import HebcalClient, RateLimiter  # noqa: E402
from zmanim_mcp.prefs import PrefStore  # noqa: E402
from zmanim_mcp import tools as T  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "hebcal_responses.json"
# Unit tests run against real Hebcal responses recorded once (RECORD_FIXTURES=1 refreshes them).
FIXED_NOW = datetime(2026, 10, 21, 10, 0, tzinfo=ZoneInfo("America/New_York"))


def fixed_clock(tz):
    return FIXED_NOW.astimezone(tz)


class FixtureTransport(httpx.AsyncBaseTransport):
    def __init__(self, record: bool):
        self.record = record
        self.data = json.loads(FIXTURES.read_text()) if FIXTURES.exists() else {}
        self.real = httpx.AsyncHTTPTransport() if record else None
        self.seen = []

    async def handle_async_request(self, request):
        key = str(request.url)
        self.seen.append(key)
        if self.record:
            resp = await self.real.handle_async_request(request)
            body = await resp.aread()
            self.data[key] = {"status": resp.status_code, "json": json.loads(body)}
            FIXTURES.write_text(json.dumps(self.data, indent=0, ensure_ascii=False, sort_keys=True))
            return httpx.Response(resp.status_code, content=body, headers={"content-type": "application/json"})
        if key not in self.data:
            raise AssertionError(f"no recorded Hebcal fixture for {key}; run with RECORD_FIXTURES=1")
        item = self.data[key]
        return httpx.Response(item["status"], json=item["json"])


class DownTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise httpx.ConnectError("simulated outage", request=request)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def transport():
    return FixtureTransport(record=os.environ.get("RECORD_FIXTURES") == "1")


@pytest.fixture
def ctx(tmp_path, transport):
    client = HebcalClient(transport=transport, limiter=RateLimiter(min_interval=0.0))
    return T.Ctx(hebcal=client, prefs=PrefStore(tmp_path / "profiles.json"), now=fixed_clock)


@pytest.fixture
def down_ctx(tmp_path):
    client = HebcalClient(transport=DownTransport(), limiter=RateLimiter(min_interval=0.0), backoff=0.0)
    return T.Ctx(hebcal=client, prefs=PrefStore(tmp_path / "profiles.json"), now=fixed_clock)
