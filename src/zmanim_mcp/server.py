"""Shabbos & Zmanim MCP server.

Run:   python -m zmanim_mcp.server            (Streamable HTTP on 127.0.0.1:8765/mcp)
       python -m zmanim_mcp.server --stdio    (stdio, for desktop MCP clients)

Built on the official MCP Python SDK (package `mcp`, 2.3.0), which speaks the
current MCP protocol revision 2026-07-28 and still negotiates 2025-11-25 with
handshake-era clients. Every tool is read-only and returns:
  * content[0]           - a short, voice-ready sentence (for Alexa+ to speak)
  * structuredContent    - the full structured answer (ISO times, names, links)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import Annotated, Any, Awaitable, Literal

from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.apps import APP_MIME_TYPE, Apps
from mcp.server.mcpserver.resources import TextResource
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as McpToolError

from . import __version__
from . import tools as T
from .hebcal import ATTRIBUTION, HebcalClient
from .prefs import PrefStore
from .ui import SHABBOS_CARD_HTML

log = logging.getLogger("zmanim_mcp")

INSTRUCTIONS = (
    "Jewish calendar and halachic times (zmanim) for voice assistants such as Alexa+. "
    "Use shabbos_times for candle lighting and havdalah, get_zmanim for daily times, parsha for the "
    "weekly Torah portion, upcoming_holidays, daf_yomi and convert_date. If the user names their city "
    "once, call remember_my_location so later questions can omit it; forget_my_location deletes it. Read the `summary` field aloud; "
    "it is written for speech. Always keep the Hebcal.com attribution when displaying results."
)

CARD_URI = "ui://shabbos-zmanim/shabbos-card.html"
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

City = Annotated[str | None, Field(description="City name, e.g. 'Lakewood, NJ', 'Brooklyn', 'Jerusalem', 'Boro Park'. "
                                               "Omit to use the saved location.")]
Lat = Annotated[float | None, Field(description="Latitude in decimal degrees (use with longitude and timezone).",
                                    ge=-90, le=90)]
Lon = Annotated[float | None, Field(description="Longitude in decimal degrees, negative west of Greenwich.",
                                    ge=-180, le=180)]
Tz = Annotated[str | None, Field(description="IANA time zone, e.g. America/New_York, Asia/Jerusalem. "
                                             "Required with coordinates.")]
DateArg = Annotated[str | None, Field(description="Date as YYYY-MM-DD, or 'today' / 'tomorrow'. Default: today "
                                                  "in the location's time zone.")]
Profile = Annotated[str | None, Field(description="Whose saved preferences to use (an account or household id). "
                                                  "Default: 'default'.")]
Ashk = Annotated[bool, Field(description="Ashkenazi transliteration (Shabbos, Parshas, Sukkos). False = Sephardi "
                                         "(Shabbat, Parashat, Sukkot).")]


def build_server(hebcal: HebcalClient | None = None, prefs: PrefStore | None = None, now=None) -> MCPServer:
    ctx = T.Ctx(hebcal=hebcal or HebcalClient(), prefs=prefs or PrefStore(), now=now)
    apps = Apps()
    stats = {"calls": 0, "started": time.time()}

    async def run(name: str, coro: Awaitable[dict]) -> CallToolResult:
        stats["calls"] += 1
        t0 = time.perf_counter()
        try:
            result = await coro
        except T.ToolError as exc:
            log.info("tool %s -> error: %s", name, exc)
            raise McpToolError(str(exc)) from exc
        log.info("tool %s -> %s (%.0f ms)", name, result.get("summary", "")[:120], (time.perf_counter() - t0) * 1000)
        text = f"{result['summary']}\n\n{ATTRIBUTION}"
        return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=result)

    server = MCPServer(
        name="shabbos-zmanim",
        title="Shabbos & Zmanim",
        description="Candle lighting, havdalah, zmanim, parsha, holidays, daf yomi and Hebrew dates. Data: Hebcal.com (CC BY 4.0).",
        instructions=INSTRUCTIONS,
        website_url="https://www.hebcal.com/home/developer-apis",
        version=__version__,
        extensions=[apps],
    )

    @server.tool(title="Daily zmanim", annotations=READ_ONLY,
                 description="Halachic times for one day at a place: alos hashachar (dawn), misheyakir, sunrise, "
                             "latest Shema and Shacharis (Magen Avraham and Gra), chatzos, mincha gedola, mincha "
                             "ketana, plag hamincha, sunset and tzeis (nightfall, 8.5 degrees and 72 minutes). "
                             "Use for questions like 'when is sunset', 'latest Shema tomorrow in Brooklyn'.")
    async def get_zmanim(
        city: City = None, date: DateArg = None, latitude: Lat = None, longitude: Lon = None, timezone: Tz = None,
        profile: Profile = None,
        focus: Annotated[Literal["all", "shema", "tefila", "sunrise", "sunset", "alos", "chatzos", "mincha", "plag",
                                 "tzeis"] | None,
                         Field(description="Which zman the user asked about, so the spoken summary answers just "
                                           "that ('latest Shema' -> shema). Structured times always include all. "
                                           "Default: all.")] = None,
    ) -> CallToolResult:
        return await run("get_zmanim", T.get_zmanim(ctx, city, date, latitude, longitude, timezone, profile, focus))

    # Registered as a plain tool carrying _meta.ui.resourceUri by hand: a tool registered through
    # Apps.tool() is only listed to clients that negotiate the MCP Apps extension, and voice clients
    # (and most MCP clients today) do not. See FRICTION_LOG.md, entry 4.
    @server.tool(name="shabbos_times", title="Shabbos times", annotations=READ_ONLY,
                 meta={"ui": {"resourceUri": CARD_URI}},
               description="Candle lighting and havdalah for the coming (or current) Shabbos or Yom Tov at a place, "
                           "with the parsha and any Yom Tov. Candle lighting defaults to 18 minutes before sunset "
                           "(40 in Jerusalem, 30 in Haifa) and havdalah to tzeis at 8.5 degrees; both are "
                           "configurable. Use for 'when is candle lighting this Friday in Lakewood?'.")
    async def shabbos_times(
        city: City = None,
        candle_minutes: Annotated[int | None, Field(description="Minutes before sunset to light candles, e.g. 18, 20, "
                                                               "40. Default 18 (Jerusalem 40).", ge=0, le=90)] = None,
        havdalah_minutes: Annotated[int | None, Field(description="Minutes after sunset for havdalah, e.g. 42, 50, 72. "
                                                                 "Default: tzeis at 8.5 degrees.", ge=20, le=90)] = None,
        date: Annotated[str | None, Field(description="Find the Shabbos/Yom Tov on or after this date (YYYY-MM-DD). "
                                                     "Default: now.")] = None,
        latitude: Lat = None, longitude: Lon = None, timezone: Tz = None, profile: Profile = None,
        ashkenazi: Ashk = True,
    ) -> CallToolResult:
        return await run("shabbos_times", T.shabbos_times(ctx, city, candle_minutes, havdalah_minutes, date,
                                                          latitude, longitude, timezone, profile, ashkenazi))

    @server.tool(name="parsha", title="Weekly parsha", annotations=READ_ONLY,
                 description="This week's Torah portion (parsha) with the Torah and haftarah references. Israel and "
                             "the diaspora sometimes read different portions; set israel or give a city.")
    async def parsha_tool(
        date: Annotated[str | None, Field(description="Any date in the week (YYYY-MM-DD); the following Shabbos is "
                                                     "used. Default: this week.")] = None,
        israel: Annotated[bool | None, Field(description="True for the Israel reading schedule, False for the "
                                                        "diaspora. Default: from the city or saved location, else "
                                                        "diaspora.")] = None,
        city: City = None, profile: Profile = None, ashkenazi: Ashk = True,
    ) -> CallToolResult:
        return await run("parsha", T.parsha(ctx, date, israel, city, profile, ashkenazi))

    @server.tool(title="Upcoming Jewish holidays", annotations=READ_ONLY,
                 description="The next N Jewish holidays with their dates, multi-day holidays grouped (e.g. Pesach, "
                             "Chanukah). Optionally include minor holidays, fast days, modern Israeli holidays and "
                             "Rosh Chodesh.")
    async def upcoming_holidays(
        count: Annotated[int, Field(description="How many holidays to return (1-20).", ge=1, le=20)] = 5,
        date: Annotated[str | None, Field(description="Start from this date (YYYY-MM-DD). Default today.")] = None,
        include_minor: Annotated[bool, Field(description="Include minor holidays (Tu BiShvat, Lag BaOmer...).")] = True,
        include_fasts: Annotated[bool, Field(description="Include minor fast days.")] = True,
        include_modern: Annotated[bool, Field(description="Include modern Israeli holidays.")] = False,
        include_rosh_chodesh: Annotated[bool, Field(description="Include Rosh Chodesh.")] = False,
        israel: Annotated[bool | None, Field(description="Israel holiday schedule (one-day Yom Tov).")] = None,
        profile: Profile = None, ashkenazi: Ashk = True,
    ) -> CallToolResult:
        return await run("upcoming_holidays", T.upcoming_holidays(ctx, count, date, include_minor, include_fasts,
                                                                  include_modern, include_rosh_chodesh, israel,
                                                                  profile, ashkenazi))

    @server.tool(title="Daf Yomi", annotations=READ_ONLY,
                 description="The Daf Yomi (Babylonian Talmud page of the day) for a date, with a link to learn it.")
    async def daf_yomi(date: DateArg = None, ashkenazi: Ashk = True) -> CallToolResult:
        return await run("daf_yomi", T.daf_yomi(ctx, date, ashkenazi))

    @server.tool(title="Convert dates", annotations=READ_ONLY,
                 description="Convert a Gregorian date to the Hebrew date, or a Hebrew date to the Gregorian date. "
                             "Give gregorian_date, or hebrew_year + hebrew_month + hebrew_day.")
    async def convert_date(
        gregorian_date: Annotated[str | None, Field(description="Gregorian date YYYY-MM-DD.")] = None,
        after_sunset: Annotated[bool, Field(description="The Gregorian time is after sunset (the Hebrew date "
                                                       "has already advanced).")] = False,
        hebrew_year: Annotated[int | None, Field(description="Hebrew year, e.g. 5787.", ge=3762, le=6000)] = None,
        hebrew_month: Annotated[str | None, Field(description="Hebrew month name: Nisan, Iyar, Sivan, Tamuz, Av, Elul, "
                                                             "Tishrei, Cheshvan, Kislev, Teves, Shvat, Adar, Adar I, "
                                                             "Adar II.")] = None,
        hebrew_day: Annotated[int | None, Field(description="Day of the Hebrew month (1-30).", ge=1, le=30)] = None,
    ) -> CallToolResult:
        return await run("convert_date", T.convert_date(ctx, gregorian_date, after_sunset, hebrew_year,
                                                        hebrew_month, hebrew_day))

    @server.tool(title="Remember my location", annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
        description="Save the user's home city and their candle-lighting / havdalah minutes so later questions "
                    "can omit them ('when is Shabbos?'). Stored on this server per profile, across sessions.")
    async def remember_my_location(
        city: Annotated[str | None, Field(description="Home city, e.g. 'Lakewood, NJ'.")] = None,
        latitude: Lat = None, longitude: Lon = None, timezone: Tz = None,
        candle_minutes: Annotated[int | None, Field(description="Family custom: minutes before sunset.", ge=0,
                                                   le=90)] = None,
        havdalah_minutes: Annotated[int | None, Field(description="Family custom: minutes after sunset (e.g. 50 or "
                                                                 "72). Omit for 8.5 degrees.", ge=20, le=90)] = None,
        profile: Profile = None,
    ) -> CallToolResult:
        return await run("remember_my_location", T.remember_my_location(ctx, city, latitude, longitude, timezone,
                                                                        candle_minutes, havdalah_minutes, profile))

    @server.tool(title="Forget my location", annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
        description="Delete everything saved for a profile by remember_my_location (city or coordinates, time zone, "
                    "candle-lighting and havdalah minutes) from this server. Use when the user says 'forget my "
                    "location' or 'delete my saved settings'. Forgetting a profile that has nothing saved is a no-op.")
    async def forget_my_location(profile: Profile = None) -> CallToolResult:
        return await run("forget_my_location", T.forget_my_location(ctx, profile))

    # Same reason as above: listed to every client, served with the MCP Apps MIME type.
    server.add_resource(TextResource(uri=CARD_URI, name="shabbos-card", title="Shabbos times card",
                                     description="A small visual card (MCP Apps) for screen devices such as Echo Show.",
                                     mime_type=APP_MIME_TYPE, meta={"ui": {"prefersBorder": True}},
                                     text=SHABBOS_CARD_HTML))

    @server.resource("zmanim://attribution", name="attribution", title="Data sources and license",
                     mime_type="text/plain")
    def attribution() -> str:
        return (ATTRIBUTION + "\nHebcal.com API content is licensed under Creative Commons Attribution 4.0 "
                "(https://creativecommons.org/licenses/by/4.0/). This server is MIT-licensed and not affiliated "
                "with Hebcal.com or Amazon.")

    @server.prompt(name="erev_shabbos_briefing", title="Erev Shabbos briefing",
                   description="Ask for a short Friday briefing: candle lighting, parsha and havdalah for a city.")
    def erev_shabbos_briefing(city: str) -> str:
        return (f"Using the shabbos-zmanim tools, give me a 3-sentence Erev Shabbos briefing for {city}: candle "
                f"lighting time, this week's parsha, and when Shabbos ends. Read it in a warm, calm voice.")

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "name": "shabbos-zmanim", "version": __version__,
                             "tool_calls": stats["calls"], "hebcal_requests": ctx.hebcal.requests_made,
                             "cache_hits": ctx.hebcal.cache.hits, "attribution": ATTRIBUTION})

    server.zmanim_ctx = ctx  # type: ignore[attr-defined]  (handy for tests)
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description="Shabbos & Zmanim MCP server")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    ap.add_argument("--stdio", action="store_true", help="serve over stdio instead of Streamable HTTP")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = build_server()
    if args.stdio:
        server.run("stdio")
    else:
        log.info("Shabbos & Zmanim MCP server on http://%s:%d/mcp (Streamable HTTP)", args.host, args.port)
        server.run("streamable-http", host=args.host, port=args.port, streamable_http_path="/mcp")


if __name__ == "__main__":
    main()
