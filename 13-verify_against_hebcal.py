"""Cross-check the running MCP server against hebcal.com for Lakewood, Brooklyn and Jerusalem.

  python scripts/verify_against_hebcal.py [--url http://127.0.0.1:8765/mcp] [--date 2026-10-23]

For each city it:
  1. calls the server's shabbos_times and get_zmanim tools through a real MCP client (Streamable HTTP);
  2. fetches the public hebcal.com Shabbat web page (HTML, a different endpoint from the API the
     server uses) and reads the candle-lighting / havdalah <time datetime=...> values and parsha;
  3. fetches hebcal.com's zmanim API for the same day;
  4. compares, and also reports this server's independent NOAA calculation.
Writes verification/hebcal_check.json and verification/hebcal_check.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx2 as httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mcp import Client  # noqa: E402
from zmanim_mcp import astro  # noqa: E402

CITIES = [("Lakewood, NJ", 5100280, 18), ("Brooklyn, NY", 5110302, 18), ("Jerusalem", 281184, 40)]
ZMAN_KEYS = {"alos_hashachar": "alotHaShachar", "sunrise": "sunrise", "sof_zman_shema_mga": "sofZmanShmaMGA",
             "sof_zman_shema_gra": "sofZmanShma", "sof_zman_tefila_gra": "sofZmanTfilla", "chatzos": "chatzot",
             "mincha_gedola": "minchaGedola", "plag_hamincha": "plagHaMincha", "sunset": "sunset",
             "tzeis_8_5_degrees": "tzeit85deg"}
LOCAL = {"alos_hashachar": "alos", "tzeis_8_5_degrees": "tzeis_8_5"}
UA = {"User-Agent": "shabbos-zmanim-mcp verification script (credits Hebcal.com, CC BY 4.0)"}


def hhmm(iso: str | None) -> str | None:
    return iso[11:16] if iso else None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    ap.add_argument("--date", default="2026-10-23", help="a Friday")
    args = ap.parse_args()
    fri = date.fromisoformat(args.date)
    rows, report = [], {"checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "friday": fri.isoformat(), "server": args.url, "cities": []}
    http = httpx.Client(headers=UA, timeout=20)
    async with Client(args.url) as mcp:
        report["protocol_version"] = mcp.protocol_version
        for city, gid, minutes in CITIES:
            st = (await mcp.call_tool("shabbos_times", {"city": city, "date": fri.isoformat()})).structured_content
            zm = (await mcp.call_tool("get_zmanim", {"city": city, "date": fri.isoformat()})).structured_content
            page = http.get("https://www.hebcal.com/shabbat", params={"geonameid": gid, "b": minutes, "M": "on",
                            "gy": fri.year, "gm": fri.month, "gd": fri.day}).text
            time.sleep(0.5)
            web_candles = re.search(r'<li class="candles"[^>]*>.*?<time datetime="([^"]+)"', page, re.S)
            web_havdalah = re.search(r'<li class="havdalah"[^>]*>.*?<time datetime="([^"]+)"', page, re.S)
            web_parsha = re.search(r'Parashat ([A-Za-z\'\-]+)', page)
            api = http.get("https://www.hebcal.com/zmanim", params={"cfg": "json", "geonameid": gid,
                                                                   "date": fri.isoformat()}).json()
            time.sleep(0.5)
            loc = st["location"]
            local = astro.compute(fri, loc["latitude"], loc["longitude"], loc["tzid"]).as_dict()
            c = {"city": city, "geonameid": gid, "candle_minutes": minutes,
                 "shabbos": {
                     "candle_lighting": {"mcp": hhmm(st["candle_lighting"][0]["time"]),
                                         "hebcal_web": hhmm(web_candles.group(1)) if web_candles else None},
                     "havdalah": {"mcp": hhmm(st["havdalah"]["time"]),
                                  "hebcal_web": hhmm(web_havdalah.group(1)) if web_havdalah else None},
                     "parsha": {"mcp": st["parsha"], "hebcal_web": web_parsha.group(0) if web_parsha else None}},
                 "zmanim": {}}
            for k, hk in ZMAN_KEYS.items():
                lv = local.get(LOCAL.get(k, k))
                c["zmanim"][k] = {"mcp": hhmm(zm["times"][k]), "hebcal_api": hhmm(api["times"].get(hk)),
                                  "local_noaa": lv.strftime("%H:%M:%S") if lv else None}
            report["cities"].append(c)
    # Markdown
    md = [f"Checked {report['checked_at']} for Friday {fri.isoformat()} and the Shabbos that follows,"
          f" via MCP protocol {report['protocol_version']}.", ""]
    md += ["| City | Item | MCP server | hebcal.com | Match |", "|---|---|---|---|---|"]
    ok_all = True
    for c in report["cities"]:
        for item, v in c["shabbos"].items():
            web = v["hebcal_web"]
            m = v["mcp"] == web if item != "parsha" else bool(web and v["mcp"] and v["mcp"].split()[-1] in web)
            ok_all &= m
            md.append(f"| {c['city']} | {item} | {v['mcp']} | {web} (web page) | {'yes' if m else 'NO'} |")
        for k, v in c["zmanim"].items():
            m = v["mcp"] == v["hebcal_api"]
            ok_all &= m
            md.append(f"| {c['city']} | {k} | {v['mcp']} | {v['hebcal_api']} (API) · local NOAA {v['local_noaa']} "
                      f"| {'yes' if m else 'NO'} |")
    report["all_match"] = ok_all
    (ROOT / "verification").mkdir(exist_ok=True)
    (ROOT / "verification" / "hebcal_check.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (ROOT / "verification" / "hebcal_check.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print("\nALL MATCH" if ok_all else "\nMISMATCHES FOUND")


if __name__ == "__main__":
    asyncio.run(main())
