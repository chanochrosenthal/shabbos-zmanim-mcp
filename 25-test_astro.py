from datetime import date, datetime

from zmanim_mcp import astro

# Reference values from Hebcal.com's zmanim API for Lakewood, NJ (geonameid 5100280), 2026-10-23,
# and Jerusalem (281184), 2026-10-23, fetched 2026-10-21. Hebcal rounds to the minute.
LAKEWOOD = dict(lat=40.09789, lon=-74.21764, tzid="America/New_York")
HEBCAL_LAKEWOOD = {"alos": "05:55", "misheyakir": "06:19", "sunrise": "07:16", "sof_zman_shema_mga": "09:22",
                   "sof_zman_shema_gra": "09:58", "sof_zman_tefila_mga": "10:29", "sof_zman_tefila_gra": "10:53",
                   "chatzos": "12:41", "mincha_gedola": "13:08", "mincha_ketana": "15:50",
                   "plag_hamincha": "16:58", "sunset": "18:06", "tzeis_8_5": "18:46", "tzeis_72": "19:18"}


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def test_lakewood_matches_hebcal_within_one_minute():
    z = astro.compute(date(2026, 10, 23), **LAKEWOOD).as_dict()
    for key, ref in HEBCAL_LAKEWOOD.items():
        got = z[key]
        mins = got.hour * 60 + got.minute + got.second / 60
        assert abs(mins - _minutes(ref)) <= 1.0, (key, got, ref)


def test_jerusalem_sunset_and_dst_offset():
    z = astro.compute(date(2026, 10, 23), 31.76904, 35.21633, "Asia/Jerusalem")
    assert z.sunset.utcoffset().total_seconds() == 3 * 3600  # Israel still on summer time on Oct 23 2026
    assert (z.sunset.hour, z.sunset.minute) in ((17, 57), (17, 58))


def test_order_of_zmanim_is_monotonic():
    z = astro.compute(date(2026, 6, 21), **LAKEWOOD).as_dict()
    order = ["alos", "misheyakir", "sunrise", "sof_zman_shema_mga", "sof_zman_shema_gra", "sof_zman_tefila_gra",
             "chatzos", "mincha_gedola", "mincha_ketana", "plag_hamincha", "sunset", "tzeis_8_5", "tzeis_72"]
    times = [z[k] for k in order]
    assert times == sorted(times)


def test_polar_day_returns_none_instead_of_crashing():
    z = astro.compute(date(2026, 6, 21), 69.65, 18.96, "Europe/Oslo")  # Tromso, midnight sun
    assert z.sunset is None and z.sunrise is None
    assert z.chatzos is not None


def test_sun_event_helper():
    t = astro.sun_event(date(2026, 10, 23), LAKEWOOD["lat"], LAKEWOOD["lon"], LAKEWOOD["tzid"], -0.833, rising=False)
    assert isinstance(t, datetime) and t.hour == 18
