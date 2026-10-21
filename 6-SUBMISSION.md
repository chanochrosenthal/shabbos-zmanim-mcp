# Devpost submission draft: Shabbos & Zmanim

> DRAFT ONLY. Nothing has been submitted. The author submits it. The fields in [brackets] are the author's to fill in.

**Project name:** Shabbos & Zmanim
**Tagline:** The Jewish calendar for Alexa+: candle lighting, zmanim, parsha and holidays as answers you can speak.
**Primary track:** Alexa+ (self-hosted MCP server, Streamable HTTP; current spec 2026-07-28, and it negotiates 2025-11-25)
**Mini challenge:** Open Source (new MIT-licensed repository)
**Repository:** [GitHub URL, to be created by the author]
**Contribution URL (Open Source):** [same repository URL]
**GitHub username:** [author's GitHub username]
**Video:** [YouTube or Vimeo URL, public, under 3 minutes; draft file is demo/demo.mp4, 2:18]

## Inspiration
Observant Jewish households plan their week around times that change every day and differ by city: when to light candles on Friday, the latest time to say Shema, when Shabbos ends, which parsha is read this week, when the next Yom Tov starts. Right now that means checking a calendar on the fridge or opening a phone, which many people avoid or can't do on Shabbos itself. A voice assistant in the kitchen should just know.

## What it does
Shabbos & Zmanim is a self-hosted MCP server that gives Alexa+ (or any MCP client) eight tools:

- **shabbos_times**: candle lighting and havdalah for the coming Shabbos or Yom Tov, including multi-day Yom Tov (each night's candle lighting), with the family's own minhag (18/20/40 minutes; havdalah at 8.5°, 42, 50 or 72 minutes). Jerusalem defaults to 40 minutes.
- **get_zmanim**: alos, misheyakir, sunrise, latest Shema and Shacharis (Magen Avraham and Gra), chatzos, mincha gedola and ketana, plag, sunset, tzeis and Rabbeinu Tam. A `focus` option keeps the spoken answer to what was asked.
- **parsha**: this week's parsha with Torah and haftarah references, and the right answer for Israel vs. the diaspora.
- **upcoming_holidays**: the next N holidays, with multi-day holidays grouped into one spoken answer.
- **daf_yomi** and **convert_date** (Gregorian ↔ Hebrew).
- **remember_my_location**: remembers a household's city and customs across sessions, so "When does Shabbos start?" needs no city.
- **forget_my_location**: deletes everything saved for a household, on request ("Alexa, forget my location").

Every result carries a voice-ready `summary` sentence plus structured fields (ISO times with offsets, Hebrew names, the halachic definitions used, attribution), so a speaker can read it and a screen can render it. `shabbos_times` also links an **MCP Apps** card (`ui://`) for screen devices.

## How we built it
- **Official MCP Python SDK `mcp` 2.3.0** (`MCPServer`, Streamable HTTP transport, `mcp.Client` for tests and the demo). It serves the current protocol revision **2026-07-28** and still negotiates **2025-11-25**; the end-to-end tests run on both.
- **Hebcal.com REST APIs** (free, no key, CC BY 4.0) for zmanim, the Jewish calendar, the date converter and city search. A polite client: a self-imposed limit of 30 requests per 10 s (Hebcal allows 90), 120 ms spacing, Retry-After handling, backoff, and an LRU+TTL cache.
- **An independent NOAA solar calculator** written for this project (MIT, no GPL dependency). It cross-checks every zmanim answer (reported in the result, under 1 minute in every test) and is the **offline fallback** if Hebcal is unreachable.
- **Location without paid geocoding:** coordinates plus time zone, a bundled table of about 50 Jewish-community cities with neighbourhood aliases (Boro Park, Five Towns, Yerushalayim…), then Hebcal's GeoNames city search.
- **Tests:** 41 pytest tests, including an end-to-end test that launches the server and calls every tool over Streamable HTTP. Unit tests run on recorded real Hebcal responses. A verification script compared the server against hebcal.com for Lakewood, Brooklyn and Jerusalem: all 39 checks matched.

## What was built during the hackathon window
All of it. The repository was created from scratch on October 20–21, 2026, inside the submission period (Aug 31 – Oct 23, 2026). That covers the server, tools, calculator, tests, verification, docs and demo video.

## Privacy
Only `remember_my_location` stores anything. Per profile it keeps the location as given (a city, or latitude/longitude plus time zone), the resolved place title, an Israel/diaspora flag, and optional candle-lighting and havdalah minutes. It stores no name, email, phone number, IP address or conversation text. The data lives in one local JSON file on the server that runs it (default `./state/profiles.json`, path set by `ZMANIM_MCP_STATE`). There is no expiry: a profile is kept until it is overwritten, forgotten with the `forget_my_location` tool, or the file is deleted. Hebcal.com receives only the city or coordinates needed for each lookup, never the profile. Hebcal responses are cached in memory only and cleared when the server restarts.

## Challenges
- Spec versions: the MCP site lists 2026-07-28 as current, while the rules name 2025-11-25 as the minimum, and the TypeScript SDK still tops out at 2025-11-25. We chose the Python SDK because it serves both, and tested both.
- Voice-first output: the SDK's default turns a returned dict into JSON text, which a speaker can't read aloud. We return an explicit `CallToolResult` with a spoken sentence as the content and the dict as `structuredContent`.
- MCP Apps: a tool registered through the SDK's Apps helper was hidden from clients that don't negotiate Apps, including the voice client. We registered the tool normally with `_meta.ui.resourceUri` so it degrades gracefully.
- Halachic precision: zmanim have several opinions. Every answer states the definition it used and the defaults are explicit.

## Accomplishments
- Every candle lighting, havdalah and zmanim time checked matched hebcal.com to the minute, in three cities on two continents.
- It works offline for the most important question ("when is Shabbos?").
- One spoken sentence per answer, with real structured data behind it.

## What we learned
MCP's newer revisions (stateless requests, extensions, Apps) make voice and screen tools much nicer. The friction is in SDK parity and in how extensions degrade. See FRICTION_LOG.md.

## What's next
- Hosted deployment with account linking so each Alexa household gets its own profile.
- Proactive reminders ("Shabbos starts in 30 minutes") once Alexa+ notification hooks are available to MCP servers.
- Hebrew and Yiddish spoken output; more minhagim (Chabad/Baal HaTanya times are already in Hebcal's data).
- Elevation-adjusted sunrise and sunset for hilly cities such as Jerusalem.

## Built with
python, mcp (Model Context Protocol Python SDK 2.3.0), streamable-http, starlette, uvicorn, hebcal-api, geonames, pytest, mcp-apps

## Attribution
Data: Hebcal.com (CC BY 4.0). Locations: GeoNames.org (CC BY 4.0). Code: MIT. Not affiliated with Hebcal.com or Amazon.
