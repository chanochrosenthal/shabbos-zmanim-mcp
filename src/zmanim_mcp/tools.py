"""Tool logic: plain async functions returning JSON-able dicts.

Every result has:
  summary      - one or two sentences ready to be spoken by a voice assistant
  ...fields    - structured data (ISO-8601 times with offsets, names, dates)
  attribution  - credit to Hebcal.com (CC BY 4.0) and GeoNames
  source       - where the numbers came from
The MCP layer (server.py) is a thin wrapper around these.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import astro
from .geo import LocationError, Place, resolve
from .hebcal import ATTRIBUTION, HebcalClient, HebcalError
from .prefs import PrefStore

HEBREW_MONTHS = {
    "nisan": "Nisan", "nissan": "Nisan", "iyar": "Iyyar", "iyyar": "Iyyar", "sivan": "Sivan", "tamuz": "Tamuz",
    "tammuz": "Tamuz", "av": "Av", "menachem av": "Av", "elul": "Elul", "tishrei": "Tishrei", "tishri": "Tishrei",
    "cheshvan": "Cheshvan", "heshvan": "Cheshvan", "marcheshvan": "Cheshvan", "mar cheshvan": "Cheshvan",
    "kislev": "Kislev", "teves": "Tevet", "tevet": "Tevet", "shvat": "Sh'vat", "shevat": "Sh'vat", "sh'vat": "Sh'vat",
    "adar": "Adar", "adar i": "Adar1", "adar 1": "Adar1", "adar alef": "Adar1", "adar ii": "Adar2",
    "adar 2": "Adar2", "adar beis": "Adar2", "adar bet": "Adar2",
}


class ToolError(ValueError):
    """A problem the caller can fix; the message is phrased for voice."""


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def say_time(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def say_day(d: date) -> str:
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}"


def _round_minute(dt: datetime) -> datetime:
    return (dt + timedelta(seconds=30)).replace(second=0, microsecond=0)


@dataclass
class Ctx:
    hebcal: HebcalClient
    prefs: PrefStore
    now: Any = None  # injectable clock for tests: callable(tz) -> datetime

    def now_in(self, tzid: str) -> datetime:
        if self.now:
            return self.now(ZoneInfo(tzid))
        return datetime.now(ZoneInfo(tzid))


def _parse_date(s: str | None, place: Place, ctx: Ctx) -> date:
    if not s or s.strip().lower() in ("today", "now"):
        return ctx.now_in(place.tzid).date()
    t = s.strip().lower()
    today = ctx.now_in(place.tzid).date()
    if t == "tomorrow":
        return today + timedelta(days=1)
    if t == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(s.strip())
    except ValueError as exc:
        raise ToolError(f"I couldn't read the date '{s}'. Use YYYY-MM-DD, today or tomorrow.") from exc


async def _place(ctx: Ctx, profile: str | None, city: str | None, latitude: float | None,
                 longitude: float | None, timezone: str | None) -> tuple[Place, dict]:
    prefs = ctx.prefs.get(profile)
    if not city and latitude is None and longitude is None:
        saved = prefs.get("location")
        if not saved:
            raise ToolError("Which city? Tell me a city, or save one with remember_my_location.")
        city, latitude, longitude, timezone = (saved.get("city"), saved.get("latitude"),
                                               saved.get("longitude"), saved.get("timezone"))
    try:
        return await resolve(ctx.hebcal, city, latitude, longitude, timezone), prefs
    except LocationError as exc:
        raise ToolError(str(exc)) from exc


def spoken_place(place: Place) -> str:
    if place.source == "hebcal-city-search":
        return re.sub(r", (USA|United States)$", "", place.title)
    return place.name


def _base(place: Place | None, source: str) -> dict[str, Any]:
    out: dict[str, Any] = {"attribution": ATTRIBUTION, "source": source}
    if place:
        out["location"] = place.to_dict()
    return out


# ---------------------------------------------------------------- get_zmanim
ZMAN_MAP = [  # (our key, hebcal key, spoken label)
    ("alos_hashachar", "alotHaShachar", "dawn (alos, 16.1 degrees)"),
    ("misheyakir", "misheyakir", "misheyakir"),
    ("sunrise", "sunrise", "sunrise"),
    ("sof_zman_shema_mga", "sofZmanShmaMGA", "latest Shema (Magen Avraham)"),
    ("sof_zman_shema_gra", "sofZmanShma", "latest Shema (Gra)"),
    ("sof_zman_tefila_mga", "sofZmanTfillaMGA", "latest Shacharis (Magen Avraham)"),
    ("sof_zman_tefila_gra", "sofZmanTfilla", "latest Shacharis (Gra)"),
    ("chatzos", "chatzot", "midday (chatzos)"),
    ("mincha_gedola", "minchaGedola", "mincha gedola"),
    ("mincha_ketana", "minchaKetana", "mincha ketana"),
    ("plag_hamincha", "plagHaMincha", "plag hamincha"),
    ("sunset", "sunset", "sunset"),
    ("tzeis_8_5_degrees", "tzeit85deg", "nightfall (tzeis, 8.5 degrees)"),
    ("tzeis_72_minutes", "tzeit72min", "Rabbeinu Tam (72 minutes)"),
]
LOCAL_KEY = {"alos_hashachar": "alos", "tzeis_8_5_degrees": "tzeis_8_5", "tzeis_72_minutes": "tzeis_72"}
DEFINITIONS = {
    "alos_hashachar": "Sun 16.1 degrees below the horizon before sunrise.",
    "misheyakir": "Sun 11.5 degrees below the horizon.",
    "sof_zman_shema_mga": "3 proportional hours into a day from 72 minutes before sunrise to 72 minutes after sunset.",
    "sof_zman_shema_gra": "3 proportional hours after sunrise (sunrise to sunset).",
    "sof_zman_tefila_mga": "4 proportional hours, Magen Avraham day (72 minutes).",
    "sof_zman_tefila_gra": "4 proportional hours after sunrise.",
    "mincha_gedola": "6.5 proportional hours after sunrise.",
    "mincha_ketana": "9.5 proportional hours after sunrise.",
    "plag_hamincha": "10.75 proportional hours after sunrise.",
    "tzeis_8_5_degrees": "Sun 8.5 degrees below the horizon after sunset (three small stars).",
    "tzeis_72_minutes": "72 fixed minutes after sunset.",
    "sunrise": "Sea-level sunrise.",
    "sunset": "Sea-level sunset.",
}


FOCUS = {
    "shema": [("sof_zman_shema_mga", "latest Shema is {} by the Magen Avraham"), ("sof_zman_shema_gra", "and {} by the Gra")],
    "tefila": [("sof_zman_tefila_mga", "latest Shacharis is {} by the Magen Avraham"),
               ("sof_zman_tefila_gra", "and {} by the Gra")],
    "sunrise": [("sunrise", "sunrise is {}")],
    "sunset": [("sunset", "sunset is {}")],
    "alos": [("alos_hashachar", "alos hashachar is {}"), ("misheyakir", "and misheyakir is {}")],
    "chatzos": [("chatzos", "chatzos is {}")],
    "mincha": [("mincha_gedola", "mincha gedola is {}"), ("mincha_ketana", "mincha ketana {}"),
               ("plag_hamincha", "and plag hamincha {}")],
    "plag": [("plag_hamincha", "plag hamincha is {}")],
    "tzeis": [("tzeis_8_5_degrees", "nightfall (tzeis) is {}"), ("tzeis_72_minutes", "and Rabbeinu Tam is {}")],
}
ALL_SPOKEN = [("sunrise", "sunrise is {}"), ("sof_zman_shema_mga", "latest Shema is {} by the Magen Avraham"),
              ("sof_zman_shema_gra", "and {} by the Gra"), ("sof_zman_tefila_gra", "latest Shacharis {}"),
              ("chatzos", "chatzos {}"), ("mincha_gedola", "mincha gedola {}"), ("plag_hamincha", "plag hamincha {}"),
              ("sunset", "sunset {}"), ("tzeis_8_5_degrees", "and nightfall {}")]


async def get_zmanim(ctx: Ctx, city: str | None = None, date_str: str | None = None, latitude: float | None = None,
                     longitude: float | None = None, timezone: str | None = None, profile: str | None = None,
                     focus: str | None = None) -> dict:
    if focus and focus not in FOCUS and focus != "all":
        raise ToolError(f"I can focus on: {', '.join(FOCUS)}, or all.")
    place, _ = await _place(ctx, profile, city, latitude, longitude, timezone)
    d = _parse_date(date_str, place, ctx)
    local = astro.compute(d, place.latitude, place.longitude, place.tzid).as_dict()
    times: dict[str, datetime | None] = {}
    source = "hebcal.com zmanim API"
    try:
        data = await ctx.hebcal.zmanim(place.hebcal_params(), d.isoformat())
        for key, hkey, _ in ZMAN_MAP:
            v = data["times"].get(hkey)
            times[key] = datetime.fromisoformat(v) if v else None
    except HebcalError:
        source = "local astronomical calculation (Hebcal unreachable)"
        for key, _, _ in ZMAN_MAP:
            v = local.get(LOCAL_KEY.get(key, key))
            times[key] = _round_minute(v) if v else None
    # Cross-check Hebcal against our own NOAA implementation.
    diffs = [abs((times[k] - local[LOCAL_KEY.get(k, k)]).total_seconds()) / 60
             for k in times if times[k] and local.get(LOCAL_KEY.get(k, k))]
    spoken = [label.format(say_time(times[k])) for k, label in FOCUS.get(focus or "all", ALL_SPOKEN) if times.get(k)]
    summary = f"In {spoken_place(place)} on {say_day(d)}, " + ", ".join(spoken) + "."
    out = _base(place, source)
    out.update({
        "summary": summary,
        "date": d.isoformat(),
        "focus": focus or "all",
        "times": {k: (v.isoformat() if v else None) for k, v in times.items()},
        "times_spoken": {k: (say_time(v) if v else None) for k, v in times.items()},
        "definitions": DEFINITIONS,
        "cross_check": {"method": "independent NOAA solar calculation in this server",
                        "max_difference_minutes": round(max(diffs), 2) if diffs else None},
        "note": "Times are for sea level. Ask your rav which opinion to follow; leave a margin of a few minutes.",
    })
    return out


# ------------------------------------------------------------- shabbos_times
def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def default_candle_minutes(place: Place) -> int:
    """Jerusalem custom is 40 minutes, Haifa 30 (as on Hebcal.com); 18 elsewhere."""
    if _km(place.latitude, place.longitude, 31.7683, 35.2137) <= 12:
        return 40
    if _km(place.latitude, place.longitude, 32.8156, 34.9892) <= 10:
        return 30
    return 18


async def shabbos_times(ctx: Ctx, city: str | None = None, candle_minutes: int | None = None,
                        havdalah_minutes: int | None = None, date_str: str | None = None,
                        latitude: float | None = None, longitude: float | None = None, timezone: str | None = None,
                        profile: str | None = None, ashkenazi: bool = True) -> dict:
    place, prefs = await _place(ctx, profile, city, latitude, longitude, timezone)
    if candle_minutes is None:
        candle_minutes = prefs.get("candle_minutes") or default_candle_minutes(place)
    if havdalah_minutes is None:
        havdalah_minutes = prefs.get("havdalah_minutes")
    if not (0 <= candle_minutes <= 90):
        raise ToolError("Candle lighting minutes should be between 0 and 90.")
    if havdalah_minutes is not None and not (20 <= havdalah_minutes <= 90):
        raise ToolError("Havdalah minutes should be between 20 and 90.")
    tz = ZoneInfo(place.tzid)
    if date_str:
        d = _parse_date(date_str, place, ctx)
        ref = datetime.combine(d, time(0, 0), tz)
    else:
        ref = ctx.now_in(place.tzid)
        d = ref.date()
    params = {**place.hebcal_params(), "c": "on", "s": "on", "maj": "on", "b": candle_minutes,
              "i": "on" if place.in_israel else "off", "start": (d - timedelta(days=1)).isoformat(),
              "end": (d + timedelta(days=10)).isoformat()}
    if ashkenazi:
        params["lg"] = "a"
    if havdalah_minutes is None:
        params["M"] = "on"
    else:
        params["m"] = havdalah_minutes
    try:
        data = await ctx.hebcal.calendar(params)
    except HebcalError:
        return _local_shabbos(place, d, ref, candle_minutes, havdalah_minutes)
    items = data.get("items", [])

    def when(it: dict) -> datetime:
        s = it["date"]
        return datetime.fromisoformat(s) if "T" in s else datetime.combine(date.fromisoformat(s), time(12), tz)

    items.sort(key=when)
    end_idx = next((i for i, it in enumerate(items) if it["category"] == "havdalah" and when(it) >= ref), None)
    if end_idx is None:
        raise ToolError("I couldn't find the next Shabbos in Hebcal's calendar.")
    havdalah = items[end_idx]
    start_idx = end_idx
    for i in range(end_idx - 1, -1, -1):
        if items[i]["category"] == "havdalah":
            break
        start_idx = i
    block = items[start_idx:end_idx + 1]
    candles = [it for it in block if it["category"] == "candles"]
    holidays = [it["title"] for it in block if it["category"] == "holiday" and it.get("yomtov")]
    parsha = next((it for it in block if it["category"] == "parashat"), None)
    hav_dt = when(havdalah)
    lightings = [{"date": when(c).date().isoformat(), "time": when(c).isoformat(), "spoken": say_time(when(c)),
                  "day": say_day(when(c).date()), "occasion": c.get("memo")} for c in candles]
    is_yomtov = bool(holidays) and hav_dt.weekday() != 5
    name = ("Yom Tov" if is_yomtov else "Shabbos") if ashkenazi else ("Yom Tov" if is_yomtov else "Shabbat")
    bits = []
    if lightings:
        first = lightings[0]
        bits.append(f"candle lighting in {spoken_place(place)} is {first['day']} at {first['spoken']}")
        for extra in lightings[1:]:
            bits.append(f"then {extra['day']} at {extra['spoken']} (light from an existing flame)")
    else:
        bits.append(f"{name} has already begun in {spoken_place(place)}")
    if parsha:
        bits.append(f"the parsha is {parsha['title'].replace('Parshas ', '').replace('Parashat ', '')}")
    if holidays:
        bits.append("Yom Tov is " + " and ".join(dict.fromkeys(holidays)))
    if is_yomtov or (holidays and hav_dt.weekday() == 5):
        name = "Yom Tov" if is_yomtov else ("Shabbos" if ashkenazi else "Shabbat")
    bits.append(f"{name} ends with havdalah {say_day(hav_dt.date())} at {say_time(hav_dt)}")
    summary = bits[0][0].upper() + bits[0][1:] + ("; " + "; ".join(bits[1:]) if len(bits) > 1 else "") + "."
    out = _base(place, "hebcal.com Jewish calendar API")
    out.update({
        "summary": summary,
        "kind": "yom_tov" if is_yomtov else ("yom_tov_then_shabbos" if holidays else "shabbos"),
        "candle_lighting": lightings,
        "havdalah": {"time": hav_dt.isoformat(), "spoken": say_time(hav_dt), "day": say_day(hav_dt.date())},
        "parsha": parsha["title"] if parsha else None,
        "holidays": list(dict.fromkeys(holidays)),
        "settings": {"candle_minutes_before_sunset": candle_minutes,
                     "havdalah": f"{havdalah_minutes} minutes after sunset" if havdalah_minutes
                     else "tzeis, sun 8.5 degrees below the horizon"},
        "hebcal_link": parsha.get("link") if parsha else None,
    })
    return out


def _local_shabbos(place: Place, d: date, ref: datetime, candle_minutes: int, havdalah_minutes: int | None) -> dict:
    """Offline fallback: plain weekly Shabbos only (no Yom Tov awareness)."""
    friday = d + timedelta(days=(4 - d.weekday()) % 7)
    if d.weekday() == 5:  # Saturday: this Shabbos is in progress
        friday = d - timedelta(days=1)
    z_fri = astro.compute(friday, place.latitude, place.longitude, place.tzid)
    z_sat = astro.compute(friday + timedelta(days=1), place.latitude, place.longitude, place.tzid)
    candles = _round_minute(z_fri.sunset - timedelta(minutes=candle_minutes))
    hav = z_sat.sunset + timedelta(minutes=havdalah_minutes) if havdalah_minutes else z_sat.tzeis_8_5
    hav = _round_minute(hav)
    out = _base(place, "local astronomical calculation (Hebcal unreachable; Yom Tov not checked)")
    out.update({
        "summary": (f"Candle lighting in {spoken_place(place)} is {say_day(friday)} at {say_time(candles)}; Shabbos ends "
                    f"{say_day(friday + timedelta(days=1))} at {say_time(hav)}. I calculated this myself because "
                    f"Hebcal is unreachable, so Yom Tov isn't included."),
        "kind": "shabbos",
        "candle_lighting": [{"date": friday.isoformat(), "time": candles.isoformat(), "spoken": say_time(candles),
                             "day": say_day(friday), "occasion": None}],
        "havdalah": {"time": hav.isoformat(), "spoken": say_time(hav), "day": say_day(friday + timedelta(days=1))},
        "parsha": None, "holidays": [],
        "settings": {"candle_minutes_before_sunset": candle_minutes,
                     "havdalah": f"{havdalah_minutes} minutes after sunset" if havdalah_minutes
                     else "tzeis, sun 8.5 degrees below the horizon"},
    })
    return out


# ------------------------------------------------------------------- parsha
async def parsha(ctx: Ctx, date_str: str | None = None, israel: bool | None = None, city: str | None = None,
                 profile: str | None = None, ashkenazi: bool = True) -> dict:
    place = None
    tzid = "America/New_York"
    prefs = ctx.prefs.get(profile)
    if city or (israel is None and prefs.get("location")):
        place, prefs = await _place(ctx, profile, city, None, None, None)
        tzid = place.tzid
    if israel is None:
        israel = prefs.get("israel")
    if israel is None:
        israel = place.in_israel if place else False
    today = ctx.now_in(tzid).date()
    if date_str:
        try:
            d = date.fromisoformat(date_str) if date_str not in ("today", "tomorrow") else (
                today if date_str == "today" else today + timedelta(days=1))
        except ValueError as exc:
            raise ToolError(f"I couldn't read the date '{date_str}'. Use YYYY-MM-DD.") from exc
    else:
        d = today
    saturday = d + timedelta(days=(5 - d.weekday()) % 7)
    params = {"s": "on", "maj": "on", "i": "on" if israel else "off", "start": saturday.isoformat(),
              "end": saturday.isoformat()}
    if ashkenazi:
        params["lg"] = "a"
    try:
        data = await ctx.hebcal.calendar(params, ttl=7 * 24 * 3600)
    except HebcalError as exc:
        raise ToolError("Hebcal is unreachable right now, so I can't look up the parsha.") from exc
    items = data.get("items", [])
    p = next((it for it in items if it["category"] == "parashat"), None)
    out = _base(place, "hebcal.com Jewish calendar API")
    where = "in Israel" if israel else "outside Israel"
    if p:
        name = re.sub(r"^(Parshas|Parashat) ", "", p["title"])
        ley = p.get("leyning", {})
        summary = (f"The parsha for Shabbos {saturday.strftime('%B')} {saturday.day} is {name}"
                   + (f", {ley['torah'].replace('-', ' to ')}" if ley.get("torah") else "")
                   + (f". Haftarah: {ley['haftarah'].replace('-', ' to ')}" if ley.get("haftarah") else "") + ".")
        out.update({"summary": summary, "parsha": name, "title": p["title"], "hebrew": p.get("hebrew"),
                    "shabbos_date": saturday.isoformat(), "hebrew_date": p.get("hdate"), "israel": israel,
                    "torah_reading": ley.get("torah"), "haftarah": ley.get("haftarah"),
                    "aliyos": {k: v for k, v in ley.items() if k.isdigit()}, "link": p.get("link")})
    else:
        hol = next((it for it in items if it["category"] == "holiday"), None)
        title = hol["title"] if hol else "a special reading"
        out.update({"summary": f"Shabbos {saturday.strftime('%B')} {saturday.day} {where} is {title}, so there's "
                               f"no regular weekly parsha; the holiday reading is read instead.",
                    "parsha": None, "title": title, "shabbos_date": saturday.isoformat(), "israel": israel})
    return out


# -------------------------------------------------------- upcoming_holidays
_SUFFIX = re.compile(r"(:\s.*$|\s+[IVX]+(\s*\(.*\))?$|\s+\d{4}$|\s+\(.*\)$|\s+day\s+\d+$)")


def _base_name(title: str) -> str:
    t = title
    for _ in range(3):
        t = _SUFFIX.sub("", t).strip()
    return t


async def upcoming_holidays(ctx: Ctx, count: int = 5, date_str: str | None = None, include_minor: bool = True,
                            include_fasts: bool = True, include_modern: bool = False,
                            include_rosh_chodesh: bool = False, israel: bool | None = None,
                            profile: str | None = None, ashkenazi: bool = True) -> dict:
    if not (1 <= count <= 20):
        raise ToolError("Ask for between 1 and 20 holidays.")
    prefs = ctx.prefs.get(profile)
    if israel is None:
        israel = prefs.get("israel")
        if israel is None and prefs.get("location"):
            try:
                place, _ = await _place(ctx, profile, None, None, None, None)
                israel = place.in_israel
            except ToolError:
                israel = None
    israel = bool(israel)
    today = ctx.now_in("America/New_York" if not israel else "Asia/Jerusalem").date()
    start = date.fromisoformat(date_str) if date_str and date_str != "today" else today
    params = {"maj": "on", "min": "on" if include_minor else "off", "mf": "on" if include_fasts else "off",
              "mod": "on" if include_modern else "off", "nx": "on" if include_rosh_chodesh else "off",
              "i": "on" if israel else "off", "start": start.isoformat(),
              "end": (start + timedelta(days=400)).isoformat()}
    if ashkenazi:
        params["lg"] = "a"
    try:
        data = await ctx.hebcal.calendar(params, ttl=24 * 3600)
    except HebcalError as exc:
        raise ToolError("Hebcal is unreachable right now, so I can't list the holidays.") from exc
    groups: dict[str, dict] = {}
    order: list[str] = []
    for it in data.get("items", []):
        if it["category"] not in ("holiday", "roshchodesh"):
            continue
        name = _base_name(it["title"])
        if name.startswith("Erev "):
            key = name[5:]
        else:
            key = name
        d = date.fromisoformat(it["date"][:10])
        g = groups.get(key)
        if g is None or (d - date.fromisoformat(g["last_date"])).days > 2:
            if g is not None:  # same name again much later (e.g. next year's): new entry
                key = f"{key}#{d.isoformat()}"
            groups[key] = {"name": name if not name.startswith("Erev ") else name[5:], "first_date": d.isoformat(),
                           "last_date": d.isoformat(), "hebrew": it.get("hebrew"), "hebrew_date": it.get("hdate"),
                           "category": it.get("subcat") or it["category"], "erev": name.startswith("Erev "),
                           "days_titles": [it["title"]], "link": it.get("link")}
            order.append(key)
        else:
            g["last_date"] = d.isoformat()
            g["days_titles"].append(it["title"])
            if g["erev"] and not name.startswith("Erev "):
                g["erev"] = g["erev"]
    result = []
    for key in order[:count]:
        g = groups[key]
        fd, ld = date.fromisoformat(g["first_date"]), date.fromisoformat(g["last_date"])
        erev = g.pop("erev")
        starts_evening_before = erev or "Candle" in g["days_titles"][0]
        g["multi_day"] = ld != fd
        if "Candle" in g["days_titles"][0]:
            g["spoken"] = f"{g['name']}, first candle the evening of {say_day(fd)}, through {say_day(ld)}"
        elif erev:
            g["spoken"] = (f"{g['name']}, beginning the evening of {say_day(fd)}"
                           + (f", through {say_day(ld)}" if (ld - fd).days > 1 else ""))
        else:
            g["spoken"] = f"{g['name']}, {say_day(fd)}" + (f" through {say_day(ld)}" if ld != fd else "")
        g["starts_evening_before"] = bool(starts_evening_before)
        result.append(g)
    names = "; ".join(r["spoken"] for r in result)
    out = _base(None, "hebcal.com Jewish calendar API")
    out.update({"summary": f"The next {len(result)} Jewish holidays{' in Israel' if israel else ''}: {names}.",
                "holidays": result, "israel": israel, "from_date": start.isoformat(),
                "note": "Hebcal lists Chanukah by the evening each candle is lit; Erev days are shown as the first date."})
    return out


# --------------------------------------------------------------- daf_yomi
async def daf_yomi(ctx: Ctx, date_str: str | None = None, ashkenazi: bool = True) -> dict:
    today = ctx.now_in("America/New_York").date()
    if not date_str or date_str == "today":
        d = today
    elif date_str == "tomorrow":
        d = today + timedelta(days=1)
    else:
        try:
            d = date.fromisoformat(date_str)
        except ValueError as exc:
            raise ToolError(f"I couldn't read the date '{date_str}'. Use YYYY-MM-DD.") from exc
    params = {"F": "on", "start": d.isoformat(), "end": d.isoformat()}
    if ashkenazi:
        params["lg"] = "a"
    try:
        data = await ctx.hebcal.calendar(params, ttl=30 * 24 * 3600)
    except HebcalError as exc:
        raise ToolError("Hebcal is unreachable right now, so I can't look up the daf.") from exc
    it = next((x for x in data.get("items", []) if x["category"] == "dafyomi"), None)
    if not it:
        raise ToolError(f"Hebcal has no Daf Yomi listed for {d.isoformat()}.")
    m = re.match(r"(.+?)\s+(\d+)$", it["title"])
    tractate, page = (m.group(1), int(m.group(2))) if m else (it["title"], None)
    out = _base(None, "hebcal.com Jewish calendar API")
    when = "Today's" if d == today else f"The daf yomi for {say_day(d)}"
    out.update({"summary": f"{when} daf yomi is {it['title']}." if when == "Today's"
                else f"{when} is {it['title']}.",
                "date": d.isoformat(), "daf": it["title"], "tractate": tractate, "page": page,
                "hebrew": it.get("hebrew"), "hebrew_date": it.get("hdate"),
                "learn_link": it.get("link"), "cycle": "Bavli (Daf Yomi)"})
    return out


# ------------------------------------------------------------ convert_date
async def convert_date(ctx: Ctx, gregorian_date: str | None = None, after_sunset: bool = False,
                       hebrew_year: int | None = None, hebrew_month: str | None = None,
                       hebrew_day: int | None = None) -> dict:
    if gregorian_date:
        try:
            g = date.fromisoformat(gregorian_date)
        except ValueError as exc:
            raise ToolError(f"I couldn't read the date '{gregorian_date}'. Use YYYY-MM-DD.") from exc
        params = {"gy": g.year, "gm": g.month, "gd": g.day, "g2h": 1, "gs": "on" if after_sunset else None}
        direction = "gregorian_to_hebrew"
    elif hebrew_year and hebrew_month and hebrew_day:
        hm = HEBREW_MONTHS.get(hebrew_month.strip().lower(), hebrew_month.strip())
        params = {"hy": hebrew_year, "hm": hm, "hd": hebrew_day, "h2g": 1}
        direction = "hebrew_to_gregorian"
    else:
        raise ToolError("Give a Gregorian date (YYYY-MM-DD), or a Hebrew year, month and day.")
    try:
        data = await ctx.hebcal.convert(params)
    except HebcalError as exc:
        raise ToolError(f"Hebcal couldn't convert that date: {exc}") from exc
    gdate = date(data["gy"], data["gm"], data["gd"])
    heb_spoken = f"the {ordinal(data['hd'])} of {data['hm'].replace('Adar1', 'Adar I').replace('Adar2', 'Adar II')}, {data['hy']}"
    if direction == "gregorian_to_hebrew":
        summary = (f"{say_day(gdate)}, {gdate.year}{' after sunset' if after_sunset else ''} is {heb_spoken}.")
    else:
        summary = f"{heb_spoken[0].upper() + heb_spoken[1:]} falls on {say_day(gdate)}, {gdate.year}."
    out = _base(None, "hebcal.com date converter API")
    out.update({"summary": summary, "direction": direction, "gregorian": gdate.isoformat(),
                "after_sunset": bool(data.get("afterSunset")),
                "hebrew": {"year": data["hy"], "month": data["hm"], "day": data["hd"], "text": data.get("hebrew")},
                "events": data.get("events", [])})
    return out


# ------------------------------------------------------------ preferences
async def remember_my_location(ctx: Ctx, city: str | None = None, latitude: float | None = None,
                               longitude: float | None = None, timezone: str | None = None,
                               candle_minutes: int | None = None, havdalah_minutes: int | None = None,
                               profile: str | None = None) -> dict:
    if not city and latitude is None:
        raise ToolError("Tell me the city (or coordinates and time zone) to remember.")
    try:
        place = await resolve(ctx.hebcal, city, latitude, longitude, timezone)
    except LocationError as exc:
        raise ToolError(str(exc)) from exc
    if candle_minutes is not None and not (0 <= candle_minutes <= 90):
        raise ToolError("Candle lighting minutes should be between 0 and 90.")
    if havdalah_minutes is not None and not (20 <= havdalah_minutes <= 90):
        raise ToolError("Havdalah minutes should be between 20 and 90.")
    loc = {"city": city, "latitude": latitude, "longitude": longitude, "timezone": timezone,
           "resolved_title": place.title}
    saved = ctx.prefs.update(profile, location=loc, candle_minutes=candle_minutes,
                             havdalah_minutes=havdalah_minutes, israel=place.in_israel)
    cm = saved.get("candle_minutes") or default_candle_minutes(place)
    out = _base(place, "saved on this server")
    out.update({"summary": f"Got it. I'll use {place.title} from now on, with candle lighting {cm} minutes before "
                           f"sunset" + (f" and havdalah {saved['havdalah_minutes']} minutes after sunset."
                                        if saved.get("havdalah_minutes") else "."),
                "profile": ctx.prefs.key(profile), "preferences": saved})
    return out


async def forget_my_location(ctx: Ctx, profile: str | None = None) -> dict:
    key = ctx.prefs.key(profile)
    deleted = ctx.prefs.delete(profile)
    if deleted:
        summary = ("Done. I've forgotten the saved location and candle lighting settings"
                   + ("." if key == "default" else f" for {key}."))
    else:
        summary = ("There was nothing saved to forget"
                   + ("." if key == "default" else f" for {key}.") + " Nothing was changed.")
    out = _base(None, "saved on this server")
    out.update({"summary": summary, "profile": key, "deleted": deleted})
    return out
