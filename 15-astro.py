"""Local astronomical zmanim calculator (offline fallback and cross-check).

Implements the NOAA solar-position equations (Jean Meeus, "Astronomical
Algorithms", as used by the NOAA Solar Calculator) from scratch, so this
project stays MIT-licensed and has no GPL dependency. Times are sea-level
(no elevation correction), which is also Hebcal's default.

Accuracy versus Hebcal.com is typically within one minute; see TESTING.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SUNRISE_SUNSET_ALTITUDE = -0.833  # refraction + solar semi-diameter
ALOS_16_1 = -16.1
TZEIS_8_5 = -8.5
MISHEYAKIR_11_5 = -11.5


def _julian_day(d: date) -> float:
    y, m = d.year, d.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d.day + b - 1524.5


def _solar_params(jd: float) -> tuple[float, float]:
    """Return (declination in degrees, equation of time in minutes) for a Julian day."""
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * mr) * (0.019993 - 0.000101 * t)
         + math.sin(3 * mr) * 0.000289)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    seconds = 21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))
    eps0 = 23 + (26 + seconds / 60) / 60
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(app_long))))
    y = math.tan(math.radians(eps / 2)) ** 2
    l0r = math.radians(l0)
    eot = 4 * math.degrees(
        y * math.sin(2 * l0r) - 2 * e * math.sin(mr) + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
        - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr)
    )
    return decl, eot


def _utc_minutes(d: date, lat: float, lon: float, altitude: float | None, rising: bool) -> float | None:
    """Minutes after 00:00 UTC on date d when the sun reaches `altitude` (None = solar noon)."""
    jd = _julian_day(d)
    guess = 720 - 4 * lon  # start at approximate solar noon
    for _ in range(3):
        decl, eot = _solar_params(jd + guess / 1440.0)
        noon = 720 - 4 * lon - eot
        if altitude is None:
            guess = noon
            continue
        latr, declr = math.radians(lat), math.radians(decl)
        cos_h = (math.sin(math.radians(altitude)) - math.sin(latr) * math.sin(declr)) / (math.cos(latr) * math.cos(declr))
        if cos_h < -1 or cos_h > 1:
            return None  # the sun never reaches that altitude today (polar regions)
        ha = math.degrees(math.acos(cos_h))
        guess = noon - 4 * ha if rising else noon + 4 * ha
    return guess


@dataclass
class LocalZmanim:
    alos: datetime | None
    misheyakir: datetime | None
    sunrise: datetime | None
    sof_zman_shema_mga: datetime | None
    sof_zman_shema_gra: datetime | None
    sof_zman_tefila_mga: datetime | None
    sof_zman_tefila_gra: datetime | None
    chatzos: datetime | None
    mincha_gedola: datetime | None
    mincha_ketana: datetime | None
    plag_hamincha: datetime | None
    sunset: datetime | None
    tzeis_8_5: datetime | None
    tzeis_50: datetime | None
    tzeis_72: datetime | None

    def as_dict(self) -> dict[str, datetime | None]:
        return dict(self.__dict__)


def _at(d: date, minutes: float | None, tz: ZoneInfo) -> datetime | None:
    if minutes is None:
        return None
    base = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return (base + timedelta(minutes=minutes)).astimezone(tz)


def sun_event(d: date, lat: float, lon: float, tzid: str, altitude: float, rising: bool) -> datetime | None:
    """Time (in tzid) when the sun crosses `altitude` degrees on the local civil date d."""
    tz = ZoneInfo(tzid)
    # Local date d spans UTC from local-midnight; search the UTC day that holds local noon.
    noon_local = datetime(d.year, d.month, d.day, 12, tzinfo=tz).astimezone(timezone.utc)
    m = _utc_minutes(noon_local.date(), lat, lon, altitude, rising)
    return _at(noon_local.date(), m, tz)


def compute(d: date, lat: float, lon: float, tzid: str) -> LocalZmanim:
    """All the common zmanim for one civil date at a place (sea level)."""
    tz = ZoneInfo(tzid)
    noon_local = datetime(d.year, d.month, d.day, 12, tzinfo=tz).astimezone(timezone.utc)
    ud = noon_local.date()

    def ev(alt: float | None, rising: bool = True) -> datetime | None:
        return _at(ud, _utc_minutes(ud, lat, lon, alt, rising), tz)

    sunrise = ev(SUNRISE_SUNSET_ALTITUDE, True)
    sunset = ev(SUNRISE_SUNSET_ALTITUDE, False)
    chatzos = ev(None)
    alos = ev(ALOS_16_1, True)
    misheyakir = ev(MISHEYAKIR_11_5, True)
    tzeis = ev(TZEIS_8_5, False)

    def frac(start: datetime | None, end: datetime | None, hours: float) -> datetime | None:
        if start is None or end is None:
            return None
        return start + (end - start) * (hours / 12.0)

    gra = (sunrise, sunset)
    mga = (sunrise - timedelta(minutes=72), sunset + timedelta(minutes=72)) if sunrise and sunset else (None, None)
    return LocalZmanim(
        alos=alos,
        misheyakir=misheyakir,
        sunrise=sunrise,
        sof_zman_shema_mga=frac(*mga, 3),
        sof_zman_shema_gra=frac(*gra, 3),
        sof_zman_tefila_mga=frac(*mga, 4),
        sof_zman_tefila_gra=frac(*gra, 4),
        chatzos=chatzos,
        mincha_gedola=frac(*gra, 6.5),
        mincha_ketana=frac(*gra, 9.5),
        plag_hamincha=frac(*gra, 10.75),
        sunset=sunset,
        tzeis_8_5=tzeis,
        tzeis_50=sunset + timedelta(minutes=50) if sunset else None,
        tzeis_72=sunset + timedelta(minutes=72) if sunset else None,
    )
