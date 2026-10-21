"""Demo: an MCP client playing the role of Alexa+.

Connects to the running server over Streamable HTTP with the official MCP Python SDK client,
lists the tools, then asks a few spoken-style questions. The question -> tool mapping is scripted
here (in Alexa+, the assistant's model picks the tool from the descriptions); every answer printed
is the server's real response. Writes demo/transcript.json for the video.

  python scripts/demo_client.py [--url http://127.0.0.1:8765/mcp]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp import Client

ROOT = Path(__file__).resolve().parents[1]


def script(today):
    tomorrow = (today + timedelta(days=1)).isoformat()
    return [
        ("When is candle lighting this Friday in Lakewood?", "shabbos_times", {"city": "Lakewood, NJ"}),
        ("What's the latest time for Shema tomorrow in Brooklyn?", "get_zmanim",
         {"city": "Brooklyn", "date": tomorrow, "focus": "shema"}),
        ("What's the parsha this week?", "parsha", {}),
        ("What are the next three Jewish holidays?", "upcoming_holidays", {"count": 3}),
        ("What's today's daf yomi?", "daf_yomi", {}),
        ("What's the Hebrew date today?", "convert_date", {"gregorian_date": today.isoformat()}),
        ("We just moved to Jerusalem. Remember that.", "remember_my_location",
         {"city": "Jerusalem", "profile": "demo-household"}),
        ("When does Shabbos start?", "shabbos_times", {"profile": "demo-household"}),
    ]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    args = ap.parse_args()
    today = datetime.now(ZoneInfo("America/New_York")).date()
    out = {"started_at": datetime.now().astimezone().isoformat(timespec="seconds"), "url": args.url, "steps": []}
    async with Client(args.url) as client:
        out["protocol_version"] = client.protocol_version
        print(f"$ connected to {args.url}  (MCP protocol {client.protocol_version}, Streamable HTTP)")
        tools = await client.list_tools()
        out["tools"] = [{"name": t.name, "title": t.title, "description": t.description} for t in tools.tools]
        print(f"$ tools/list -> {len(tools.tools)} tools: " + ", ".join(t.name for t in tools.tools))
        for question, tool, targs in script(today):
            t0 = time.perf_counter()
            res = await client.call_tool(tool, targs)
            ms = (time.perf_counter() - t0) * 1000
            sc = res.structured_content or {}
            step = {"question": question, "tool": tool, "arguments": targs, "is_error": res.is_error,
                    "latency_ms": round(ms), "summary": sc.get("summary") or res.content[0].text,
                    "structured": sc}
            out["steps"].append(step)
            print(f"\n🗣  \"{question}\"")
            print(f"→ tools/call {tool} {json.dumps(targs)}   ({ms:.0f} ms)")
            print(f"🔊 {step['summary']}")
    out["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    (ROOT / "demo").mkdir(exist_ok=True)
    (ROOT / "demo" / "transcript.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print("\n(transcript saved to demo/transcript.json)")


if __name__ == "__main__":
    asyncio.run(main())
