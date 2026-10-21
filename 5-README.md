# Shabbos & Zmanim — an MCP server for Alexa+

**Candle lighting, havdalah, daily zmanim, the weekly parsha, upcoming holidays, Daf Yomi and Hebrew dates, as answers a voice assistant can say out loud.**

Shabbos & Zmanim is a self-hosted [Model Context Protocol](https://modelcontextprotocol.io) server. Alexa+, or any MCP client, can ask it:

> "When is candle lighting this Friday in Lakewood?"
> → *"Candle lighting in Lakewood is Friday, October 23 at 5:47 PM; the parsha is Lech-Lecha; Shabbos ends with havdalah Saturday, October 24 at 6:45 PM."*

Every tool returns two things. The first is a short **voice-ready sentence** (the `summary`, also the text content). The second is **structured data**: ISO-8601 times with UTC offsets, Hebrew names, the opinions used, links and attribution. Speakers can read the answer aloud, and screens or agents can use the fields.

- **MCP spec:** current revision **2026-07-28** over **Streamable HTTP**. It also negotiates **2025-11-25** with handshake-era clients, which is the minimum the hackathon rules name. The end-to-end tests cover both versions.
- **SDK:** the official MCP Python SDK, [`mcp`](https://pypi.org/project/mcp/) **2.3.0** (`mcp.server.mcpserver.MCPServer`, `mcp.Client`).
- **Data:** [Hebcal.com](https://www.hebcal.com/home/developer-apis) REST APIs (free, no API key, CC BY 4.0). The server caches results and rate-limits itself. Results are checked against an **independent astronomical calculation** in this repo, which is also the **offline fallback**.
- **No paid services, no API keys, no accounts.**

## Tools

| Tool | What it answers | Key inputs |
|---|---|---|
| `shabbos_times` | Candle lighting and havdalah for the coming (or current) Shabbos or Yom Tov, plus the parsha and any Yom Tov. Multi-day Yom Tov blocks list every candle lighting. | `city` or `latitude`+`longitude`+`timezone`; `candle_minutes` (default 18, **40 in Jerusalem**, 30 in Haifa); `havdalah_minutes` (default: tzeis at 8.5°, or e.g. 42/50/72); `date`; `ashkenazi` |
| `get_zmanim` | Alos (16.1°), misheyakir, sunrise, sof zman Shema and tefila (**Magen Avraham** and **Gra**), chatzos, mincha gedola/ketana, plag hamincha, sunset, tzeis (8.5°) and Rabbeinu Tam (72 min). | location, `date`, `focus` (`shema`, `tefila`, `sunset`, … keeps the spoken answer short) |
| `parsha` | This week's parsha with Torah and haftarah references and aliyos. Handles Israel vs. diaspora differences. | `date`, `israel` (or inferred from `city`) |
| `upcoming_holidays` | The next N holidays, with multi-day holidays grouped ("Chanukah, first candle the evening of Friday, December 4, through Saturday, December 12"). | `count`, `include_minor`, `include_fasts`, `include_modern`, `include_rosh_chodesh`, `israel` |
| `daf_yomi` | The Daf Yomi page for a date, with a Sefaria link. | `date` |
| `convert_date` | Gregorian to Hebrew and Hebrew to Gregorian, with an after-sunset flag. | `gregorian_date` or `hebrew_year`+`hebrew_month`+`hebrew_day` |
| `remember_my_location` | Saves a household's city and candle/havdalah minutes **across sessions**, so "When does Shabbos start?" needs no city. | `city`/coordinates, `candle_minutes`, `havdalah_minutes`, `profile` |
| `forget_my_location` | Deletes everything `remember_my_location` saved for a profile. Forgetting a profile with nothing saved is a no-op. | `profile` |

All tools except `remember_my_location` and `forget_my_location` are annotated `readOnlyHint: true`. `forget_my_location` is annotated `destructiveHint: true, idempotentHint: true`. See [Privacy](#privacy) for what is stored. Errors come back as MCP tool errors with a speakable message ("I couldn't find a city called 'Qwzxplk'. Try adding the state or country.").

Also exposed:
- **MCP Apps card:** `shabbos_times` carries `_meta.ui.resourceUri = ui://shabbos-zmanim/shabbos-card.html`, a small self-contained HTML card for screen devices (Echo Show style). The server advertises the `io.modelcontextprotocol/ui` extension.
- **Resource** `zmanim://attribution`, which holds the data sources and licenses.
- **Prompt** `erev_shabbos_briefing(city)`.
- `GET /healthz`, which reports status, tool-call count, Hebcal request count and cache hits.

### Locations without a paid geocoder
1. Coordinates plus an IANA time zone, used as given.
2. A bundled table of about 50 cities with Jewish communities (`src/zmanim_mcp/data/cities.json`, GeoNames IDs via Hebcal). It includes neighbourhood aliases: *Boro Park, Flatbush, Williamsburg → Brooklyn; Five Towns → Woodmere; Yerushalayim → Jerusalem; Tzfat → Safed; KJ → Kiryas Joel*.
3. Hebcal's public GeoNames-backed city search, cached for a week. "Lakewood, CO" correctly goes here instead of matching Lakewood, NJ.

## Run it locally

Requirements: Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"        # installs mcp==2.3.0 and pytest

.venv/bin/shabbos-zmanim-mcp              # Streamable HTTP on http://127.0.0.1:8765/mcp
# or: PYTHONPATH=src .venv/bin/python -m zmanim_mcp.server --host 127.0.0.1 --port 8765
# stdio (desktop clients): .venv/bin/shabbos-zmanim-mcp --stdio
```

Environment variables: `HOST`, `PORT`, and `ZMANIM_MCP_STATE` (path of the saved-preferences JSON file; default `./state/profiles.json`).

Try it with the bundled demo client, which uses the official SDK client over Streamable HTTP:

```bash
.venv/bin/python scripts/demo_client.py            # asks 8 spoken-style questions, prints the answers
.venv/bin/python scripts/verify_against_hebcal.py  # cross-checks Lakewood, Brooklyn, Jerusalem vs hebcal.com
.venv/bin/python -m pytest -v                      # 41 tests (unit + end-to-end over Streamable HTTP)
```

## Connect from an MCP client

Any client that speaks Streamable HTTP can point at `http://127.0.0.1:8765/mcp`. A sample `mcpServers` config (HTTP and stdio) is in [`examples/mcp.json`](examples/mcp.json). From Python:

```python
from mcp import Client
async with Client("http://127.0.0.1:8765/mcp") as client:          # negotiates 2026-07-28
    r = await client.call_tool("shabbos_times", {"city": "Lakewood, NJ"})
    print(r.content[0].text)            # the voice-ready sentence
    print(r.structured_content)         # the structured answer
# Client(url, mode="legacy") uses the 2025-11-25 initialize handshake instead.
```

## How it plugs into Alexa+

The hackathon's Alexa+ track accepts a self-hosted MCP server over Streamable HTTP. The server's `instructions`, tool titles, descriptions and typed input schemas tell the assistant's model when to call which tool. (The exact registration screens in the Alexa developer tooling were not exercised in this build. The steps below are the integration shape, not a verified click path.) The `summary` field is written for speech, so the assistant can read it as-is, or combine it with other context.

1. Run the server somewhere Alexa can reach over HTTPS (any small container or VM, behind TLS). **This repo does not deploy anything.**
2. Register the endpoint `https://<your-host>/mcp` as the MCP server for your Alexa+ integration (Streamable HTTP).
3. To keep separate households apart, pass a stable user or household id as `profile`, for example from account linking or an OAuth subject. `remember_my_location` then stores each household's city and minhag for candle lighting and havdalah.
4. On devices with a screen, a host that supports MCP Apps can render the `ui://` Shabbos card linked from `shabbos_times`.

Example conversation:
- *"Alexa, remember we're in Boro Park and we light 20 minutes before sunset."* → `remember_my_location`
- *"When does Shabbos start?"* → `shabbos_times` (no city needed)
- *"What's the latest Shema tomorrow?"* → `get_zmanim(focus="shema")`
- *"Alexa, forget my location."* → `forget_my_location`

## Privacy

`remember_my_location` is the only tool that stores anything. What it keeps, and how to remove it:

- **What is stored, per profile:** the location as the user gave it (a city name, or latitude/longitude plus time zone), the resolved place title (e.g. "Lakewood, NJ"), an Israel/diaspora flag, and the optional candle-lighting and havdalah minutes. The profile key is whatever id the client passes as `profile` (default `default`). No name, email, phone number, IP address or conversation text is stored.
- **Where:** one local JSON file on the server that runs it, default `./state/profiles.json`. The path is set with `ZMANIM_MCP_STATE`. Nothing is sent to any other service for storage.
- **How long:** saved profiles have **no expiry**. A profile is kept until it is overwritten by another `remember_my_location` call, forgotten with `forget_my_location`, or the file is deleted.
- **Forgetting:** `forget_my_location` deletes the profile from the file ("Alexa, forget my location"). Forgetting a profile that has nothing saved is a no-op and says so.
- **Hebcal:** for lookups, Hebcal.com receives only the city (as a name or GeoNames ID) or the coordinates and time zone. It never receives the profile id or the saved preferences.
- **Caching:** Hebcal responses are cached in memory only, and the cache is cleared when the server restarts. Nothing from Hebcal is written to disk.
- **Logs:** the server prints each tool name and its one-line answer to its console (stderr). It does not write a log file unless you redirect that output.

## Design notes

- **Being polite to Hebcal.** It allows up to 90 requests per 10 s. This client stays under 30 per 10 s, spaces requests at least 120 ms apart, honours `Retry-After` on 429, retries with backoff, and keeps a 512-entry LRU+TTL cache. A repeated question costs no extra request.
- **Independent check and offline fallback.** `astro.py` implements the NOAA solar equations from scratch, under MIT and with no GPL dependency. Every `get_zmanim` result reports `cross_check.max_difference_minutes` against Hebcal; in testing it stayed under 1 minute. If Hebcal can't be reached, `get_zmanim` and weekly `shabbos_times` fall back to this calculation and say so.
- **Halachic defaults are explicit.** Every result states its definitions: alos at 16.1°, MGA from a 72-minute day, tzeis at 8.5°, sea-level times, and candle minutes. Ask your rav which opinion to follow.

## Attribution and license

- Data from **[Hebcal.com](https://www.hebcal.com)**, licensed **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**. Every tool result includes `attribution`, and the text content ends with the credit line.
- Location data from **[GeoNames](https://www.geonames.org)** (CC BY 4.0), as provided through Hebcal.
- Code: **MIT** (see [LICENSE](LICENSE)). This project is not affiliated with Hebcal.com or Amazon.

## Repository layout

```
src/zmanim_mcp/server.py     MCP server (tools, resources, prompt, MCP Apps card, /healthz)
src/zmanim_mcp/tools.py      tool logic and voice summaries
src/zmanim_mcp/hebcal.py     Hebcal client: cache, rate limiter, retries
src/zmanim_mcp/astro.py      NOAA solar calculator (fallback and cross-check)
src/zmanim_mcp/geo.py        location resolution (bundled table → Hebcal city search)
src/zmanim_mcp/prefs.py      per-profile saved preferences
src/zmanim_mcp/ui.py         MCP Apps HTML card
tests/                       41 tests; recorded Hebcal fixtures for offline unit tests
scripts/demo_client.py       demo MCP client (used for the video)
scripts/verify_against_hebcal.py
verification/                hebcal.com cross-check output
demo/demo.mp4                demo video (draft)
```
