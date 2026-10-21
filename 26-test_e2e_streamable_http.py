"""End-to-end: start the real server process, connect over Streamable HTTP with the official
MCP Python SDK client, list the tools and call every one of them - once on the current protocol
revision (2026-07-28) and once on the handshake-era revision (2025-11-25).

This test talks to the live Hebcal.com API. Set ZMANIM_E2E_OFFLINE=1 to skip it.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx2 as httpx
import pytest

from mcp import Client

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.anyio,
              pytest.mark.skipif(os.environ.get("ZMANIM_E2E_OFFLINE") == "1", reason="offline run")]

EXPECTED_TOOLS = {"get_zmanim", "shabbos_times", "parsha", "upcoming_holidays", "daf_yomi", "convert_date",
                  "remember_my_location", "forget_my_location"}

CALLS = [
    ("remember_my_location", {"city": "Lakewood, NJ", "candle_minutes": 18, "profile": "e2e"}),
    ("shabbos_times", {"profile": "e2e"}),
    ("shabbos_times", {"city": "Jerusalem"}),
    ("get_zmanim", {"city": "Brooklyn", "date": "2026-10-23"}),
    ("get_zmanim", {"latitude": 31.778, "longitude": 35.235, "timezone": "Asia/Jerusalem", "date": "2026-10-23"}),
    ("parsha", {"date": "2026-10-21"}),
    ("parsha", {"date": "2022-04-20", "israel": True}),
    ("upcoming_holidays", {"count": 3, "date": "2026-10-21"}),
    ("daf_yomi", {"date": "2026-10-21"}),
    ("convert_date", {"gregorian_date": "2026-10-21"}),
    ("convert_date", {"hebrew_year": 5787, "hebrew_month": "Kislev", "hebrew_day": 25}),
    ("forget_my_location", {"profile": "e2e"}),
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url(tmp_path_factory):
    port = _free_port()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"),
           "ZMANIM_MCP_STATE": str(tmp_path_factory.mktemp("state") / "profiles.json")}
    log = open(tmp_path_factory.mktemp("log") / "server.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "zmanim_mcp.server", "--port", str(port)], env=env,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(base + "/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("server did not start")
    yield base + "/mcp"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.parametrize("mode,expected_version", [("auto", "2026-07-28"), ("legacy", "2025-11-25")])
async def test_streamable_http_end_to_end(server_url, mode, expected_version):
    async with Client(server_url, mode=mode) as client:
        assert client.protocol_version == expected_version
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert names == EXPECTED_TOOLS
        for t in tools.tools:
            assert t.description and len(t.description) > 40
            assert t.input_schema["type"] == "object"
        shabbos = next(t for t in tools.tools if t.name == "shabbos_times")
        assert shabbos.meta["ui"]["resourceUri"] == "ui://shabbos-zmanim/shabbos-card.html"
        forget = next(t for t in tools.tools if t.name == "forget_my_location")
        assert forget.annotations.destructive_hint is True and forget.annotations.idempotent_hint is True
        assert forget.annotations.read_only_hint is False

        for name, args in CALLS:
            result = await client.call_tool(name, args)
            assert not result.is_error, (name, result.content)
            text = result.content[0].text
            assert "Hebcal.com" in text
            sc = result.structured_content
            assert sc["summary"] and sc["summary"] in text
            assert "CC BY 4.0" in sc["attribution"]

        # errors come back as tool errors with a speakable message, not as protocol failures
        bad = await client.call_tool("get_zmanim", {"city": "Qwzxplk"})
        assert bad.is_error and "couldn't find" in bad.content[0].text

        resources = await client.list_resources()
        uris = {str(r.uri) for r in resources.resources}
        assert "ui://shabbos-zmanim/shabbos-card.html" in uris
        card = await client.read_resource("ui://shabbos-zmanim/shabbos-card.html")
        assert card.contents[0].mime_type == "text/html;profile=mcp-app"

        prompt = await client.get_prompt("erev_shabbos_briefing", {"city": "Lakewood"})
        assert "Lakewood" in prompt.messages[0].content.text
