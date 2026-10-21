import pytest

from zmanim_mcp import tools as T
from zmanim_mcp.hebcal import ATTRIBUTION

pytestmark = pytest.mark.anyio


async def test_get_zmanim_lakewood(ctx):
    r = await T.get_zmanim(ctx, "Lakewood, NJ", "2026-10-23")
    assert r["times"]["sunrise"].startswith("2026-10-23T07:16")
    assert r["times"]["sof_zman_shema_mga"].startswith("2026-10-23T09:22")
    assert r["times"]["sof_zman_shema_gra"].startswith("2026-10-23T09:58")
    assert r["times"]["tzeis_8_5_degrees"].startswith("2026-10-23T18:46")
    assert "Lakewood" in r["summary"] and "9:58 AM" in r["summary"]
    assert r["cross_check"]["max_difference_minutes"] < 1.0
    assert r["attribution"] == ATTRIBUTION
    f = await T.get_zmanim(ctx, "Lakewood, NJ", "2026-10-23", focus="shema")
    assert f["summary"] == ("In Lakewood on Friday, October 23, latest Shema is 9:22 AM by the Magen Avraham, "
                            "and 9:58 AM by the Gra.")
    assert len(f["times"]) == len(r["times"])


async def test_shabbos_times_lakewood_default_18(ctx):
    r = await T.shabbos_times(ctx, "Lakewood")
    assert r["candle_lighting"][0]["spoken"] == "5:47 PM"
    assert r["candle_lighting"][0]["date"] == "2026-10-23"
    assert r["havdalah"]["spoken"] == "6:45 PM"
    assert r["parsha"] == "Parshas Lech-Lecha"
    assert r["settings"]["candle_minutes_before_sunset"] == 18
    assert r["summary"].startswith("Candle lighting in Lakewood is Friday, October 23 at 5:47 PM")


async def test_shabbos_times_jerusalem_default_40(ctx):
    r = await T.shabbos_times(ctx, "Jerusalem")
    assert r["settings"]["candle_minutes_before_sunset"] == 40
    assert r["candle_lighting"][0]["spoken"] == "5:18 PM"


async def test_shabbos_times_custom_minutes(ctx):
    r = await T.shabbos_times(ctx, "Brooklyn", candle_minutes=20, havdalah_minutes=72)
    assert r["settings"] == {"candle_minutes_before_sunset": 20, "havdalah": "72 minutes after sunset"}


async def test_shabbos_times_yom_tov_block(ctx):
    r = await T.shabbos_times(ctx, "Brooklyn", date_str="2027-04-20")
    assert len(r["candle_lighting"]) == 3  # Erev Pesach, 2nd night, Erev Shabbos
    assert r["kind"] == "yom_tov_then_shabbos"
    assert any("Pesach" in h for h in r["holidays"])


async def test_parsha_diaspora_and_israel_differ(ctx):
    d = await T.parsha(ctx, "2022-04-20", israel=False)
    i = await T.parsha(ctx, "2022-04-20", israel=True)
    # Shabbos April 23 2022 was the 8th day of Pesach outside Israel, Acharei Mos in Israel.
    assert d["parsha"] is None and "Pesach" in d["title"]
    assert i["parsha"] == "Achrei Mos"
    r = await T.parsha(ctx)
    assert r["parsha"] == "Lech-Lecha" and r["haftarah"] == "Isaiah 40:27-41:16"


async def test_upcoming_holidays_groups_multi_day(ctx):
    r = await T.upcoming_holidays(ctx, 3)
    names = [h["name"] for h in r["holidays"]]
    assert names[0] == "Chanukah" and r["holidays"][0]["multi_day"]
    assert len(r["holidays"]) == 3


async def test_daf_yomi(ctx):
    r = await T.daf_yomi(ctx, "2026-10-21")
    assert r["daf"] == "Bechoros 33" and r["tractate"] == "Bechoros" and r["page"] == 33


async def test_convert_both_ways(ctx):
    g2h = await T.convert_date(ctx, "2026-10-21")
    assert g2h["hebrew"]["month"] == "Cheshvan" and g2h["hebrew"]["day"] == 10 and g2h["hebrew"]["year"] == 5787
    h2g = await T.convert_date(ctx, hebrew_year=5787, hebrew_month="Kislev", hebrew_day=25)
    assert h2g["gregorian"] == "2026-12-05"
    with pytest.raises(T.ToolError):
        await T.convert_date(ctx)


async def test_remember_location_is_used_later(ctx):
    await T.remember_my_location(ctx, "Boro Park", candle_minutes=20, profile="test-household")
    r = await T.shabbos_times(ctx, profile="test-household")
    assert r["location"]["name"] == "Brooklyn"
    assert r["settings"]["candle_minutes_before_sunset"] == 20
    with pytest.raises(T.ToolError, match="Which city"):
        await T.shabbos_times(ctx, profile="someone-else")


async def test_forget_location_deletes_saved_profile(ctx):
    await T.remember_my_location(ctx, "Lakewood, NJ", candle_minutes=18, profile="test-household")
    await T.remember_my_location(ctx, "Jerusalem", profile="other-household")
    r = await T.forget_my_location(ctx, profile="test-household")
    assert r["deleted"] is True and r["profile"] == "test-household"
    assert "forgotten" in r["summary"]
    assert ctx.prefs.get("test-household") == {}
    with pytest.raises(T.ToolError, match="Which city"):
        await T.shabbos_times(ctx, profile="test-household")
    # other profiles are untouched
    assert ctx.prefs.get("other-household")["location"]["city"] == "Jerusalem"


async def test_forget_missing_profile_is_a_noop(ctx):
    r = await T.forget_my_location(ctx, profile="never-saved")
    assert r["deleted"] is False
    assert r["summary"] == "There was nothing saved to forget for never-saved. Nothing was changed."
    again = await T.forget_my_location(ctx)  # default profile, empty store
    assert again["deleted"] is False and "Nothing was changed" in again["summary"]


async def test_fallback_when_hebcal_is_down(down_ctx):
    z = await T.get_zmanim(down_ctx, "Lakewood", "2026-10-23")
    assert z["source"].startswith("local astronomical calculation")
    assert z["times"]["sunset"].startswith("2026-10-23T18:06")
    s = await T.shabbos_times(down_ctx, "Lakewood")
    assert s["candle_lighting"][0]["spoken"] == "5:48 PM"  # 18 min before the unrounded 18:05:36 sunset
    assert "Hebcal is unreachable" in s["summary"]


async def test_cache_prevents_duplicate_requests(ctx):
    await T.daf_yomi(ctx, "2026-10-21")
    before = ctx.hebcal.requests_made
    await T.daf_yomi(ctx, "2026-10-21")
    assert ctx.hebcal.requests_made == before and ctx.hebcal.cache.hits >= 1


async def test_bad_inputs_have_spoken_errors(ctx):
    with pytest.raises(T.ToolError, match="couldn't read the date"):
        await T.get_zmanim(ctx, "Lakewood", "next Purim")
    with pytest.raises(T.ToolError, match="between 0 and 90"):
        await T.shabbos_times(ctx, "Lakewood", candle_minutes=120)
