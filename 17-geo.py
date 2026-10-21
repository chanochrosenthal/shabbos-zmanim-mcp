"""Location resolution with no paid geocoder.

Order of lookup:
1. Explicit coordinates (latitude, longitude, timezone) from the caller.
2. A bundled table of ~50 cities with Jewish communities (data/cities.json),
   including common neighbourhood aliases ("Boro Park" -> Brooklyn,
   "Five Towns" -> Woodmere, "Yerushalayim" -> Jerusalem).
3. Hebcal's own public city search (GeoNames IDs), cached for a week.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib import resources
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .hebcal import HebcalClient, HebcalError

US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california", "co": "colorado",
    "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas", "ky": "kentucky", "la": "louisiana",
    "me": "maine", "md": "maryland", "ma": "massachusetts", "mi": "michigan", "mn": "minnesota",
    "ms": "mississippi", "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee", "tx": "texas",
    "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}


class LocationError(ValueError):
    """The location could not be resolved; the message is safe to read aloud."""


@dataclass
class Place:
    name: str
    title: str
    latitude: float
    longitude: float
    tzid: str
    geonameid: int | None = None
    country_code: str | None = None
    source: str = "bundled"

    @property
    def in_israel(self) -> bool:
        return self.country_code == "IL" or self.tzid in ("Asia/Jerusalem", "Asia/Tel_Aviv")

    def hebcal_params(self) -> dict[str, Any]:
        if self.geonameid:
            return {"geonameid": self.geonameid}
        return {"latitude": round(self.latitude, 5), "longitude": round(self.longitude, 5), "tzid": self.tzid}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["in_israel"] = self.in_israel
        return d


def _norm(s: str) -> str:
    s = s.lower().replace("é", "e").replace("’", "'")
    s = re.sub(r"[^a-z0-9,' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def bundled_cities() -> list[dict[str, Any]]:
    raw = resources.files("zmanim_mcp").joinpath("data/cities.json").read_text(encoding="utf-8")
    return json.loads(raw)["cities"]


def _qualifier_matches(qualifier: str, city: dict[str, Any]) -> bool:
    if not qualifier:
        return True
    q = US_STATES.get(qualifier, qualifier)
    hay = " ".join(_norm(str(city.get(k) or "")) for k in ("admin1", "title", "cc", "country"))
    return q in hay or (qualifier in ("usa", "us") and city.get("cc") == "US") or (
        qualifier in ("israel", "il", "eretz yisrael") and city.get("cc") == "IL")


def _place_from_city(c: dict[str, Any], source: str = "bundled") -> Place:
    return Place(name=c["name"], title=c["title"], latitude=c["lat"], longitude=c["lon"], tzid=c["tzid"],
                 geonameid=c.get("geonameid"), country_code=c.get("cc"), source=source)


def lookup_bundled(query: str) -> Place | None:
    q = _norm(query)
    parts = [p.strip() for p in q.split(",") if p.strip()]
    if not parts:
        return None
    head, qual = parts[0], (parts[1] if len(parts) > 1 else "")
    # "lakewood nj" without a comma
    if not qual:
        bits = head.rsplit(" ", 1)
        if len(bits) == 2 and bits[1] in US_STATES:
            head, qual = bits[0], bits[1]
    for c in bundled_cities():
        names = {_norm(c["name"])} | {_norm(a) for a in c.get("aliases", [])}
        if head in names or q in names:
            if _qualifier_matches(qual, c) or q in names:
                return _place_from_city(c)
    return None


def validate_tz(tzid: str) -> str:
    try:
        ZoneInfo(tzid)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise LocationError(f"I don't recognise the time zone '{tzid}'. Use an IANA name like America/New_York.") from exc
    return tzid


async def resolve(hebcal: HebcalClient, city: str | None = None, latitude: float | None = None,
                  longitude: float | None = None, timezone: str | None = None) -> Place:
    if latitude is not None or longitude is not None:
        if latitude is None or longitude is None:
            raise LocationError("Please give both latitude and longitude.")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise LocationError("Those coordinates are out of range.")
        if not timezone:
            raise LocationError("With coordinates I also need a time zone, like America/New_York or Asia/Jerusalem.")
        validate_tz(timezone)
        label = city or "your location"
        title = city or f"{latitude:.4f}, {longitude:.4f}"
        cc = "IL" if timezone in ("Asia/Jerusalem", "Asia/Tel_Aviv") else None
        return Place(name=label, title=title, latitude=latitude, longitude=longitude, tzid=timezone,
                     country_code=cc, source="coordinates")
    if not city or not city.strip():
        raise LocationError("Which city? Tell me a city name, or latitude, longitude and time zone.")
    place = lookup_bundled(city)
    if place:
        return place
    # Fall back to Hebcal's public GeoNames-backed city search.
    q = _norm(city)
    parts = [p.strip() for p in q.split(",") if p.strip()]
    head, qual = parts[0], (parts[1] if len(parts) > 1 else "")
    try:
        candidates = await hebcal.search_city(head)
    except HebcalError as exc:
        raise LocationError(f"I couldn't look up '{city}' right now. Try a nearby big city or give coordinates.") from exc
    if qual:
        candidates = [c for c in candidates if _qualifier_matches(qual, {**c, "title": c.get("value")})] or []
    if not candidates:
        raise LocationError(f"I couldn't find a city called '{city}'. Try adding the state or country.")
    best = candidates[0]
    try:
        info = await hebcal.get_json("/zmanim", {"cfg": "json", "geonameid": best["id"], "date": "2026-01-01"},
                                     ttl=30 * 24 * 3600)
    except HebcalError as exc:
        raise LocationError(f"I found {best.get('value')} but couldn't load its details right now.") from exc
    loc = info["location"]
    return Place(name=loc.get("city") or best.get("asciiname") or head, title=loc["title"],
                 latitude=loc["latitude"], longitude=loc["longitude"], tzid=loc["tzid"],
                 geonameid=best["id"], country_code=loc.get("cc"), source="hebcal-city-search")
