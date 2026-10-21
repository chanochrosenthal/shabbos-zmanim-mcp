import pytest

from zmanim_mcp import geo


@pytest.mark.parametrize("query,expected", [
    ("Lakewood", "Lakewood"), ("Lakewood, NJ", "Lakewood"), ("lakewood nj", "Lakewood"),
    ("Brooklyn", "Brooklyn"), ("Boro Park", "Brooklyn"), ("Five Towns", "Woodmere"),
    ("Yerushalayim", "Jerusalem"), ("Jerusalem", "Jerusalem"), ("Montreal", "Montréal"),
    ("NYC", "New York City"), ("Tzfat", "Safed"),
])
def test_bundled_aliases(query, expected):
    place = geo.lookup_bundled(query)
    assert place is not None and place.name == expected


def test_qualifier_mismatch_falls_through():
    assert geo.lookup_bundled("Lakewood, CO") is None


def test_israel_flag_and_hebcal_params():
    j = geo.lookup_bundled("Jerusalem")
    assert j.in_israel and j.hebcal_params() == {"geonameid": 281184}
    assert not geo.lookup_bundled("Lakewood").in_israel


@pytest.mark.anyio
async def test_coordinates_require_timezone(ctx):
    with pytest.raises(geo.LocationError, match="time zone"):
        await geo.resolve(ctx.hebcal, latitude=40.0, longitude=-74.0)
    with pytest.raises(geo.LocationError, match="recognise"):
        await geo.resolve(ctx.hebcal, latitude=40.0, longitude=-74.0, timezone="Mars/Olympus")
    p = await geo.resolve(ctx.hebcal, latitude=40.0, longitude=-74.0, timezone="America/New_York")
    assert p.hebcal_params() == {"latitude": 40.0, "longitude": -74.0, "tzid": "America/New_York"}
