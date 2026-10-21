from zmanim_mcp.prefs import PrefStore


def test_delete_existing_profile(tmp_path):
    store = PrefStore(tmp_path / "profiles.json")
    store.update("test-household", candle_minutes=20)
    store.update("other", candle_minutes=40)
    assert store.delete("test-household") is True
    assert store.get("test-household") == {}
    assert store.get("other") == {"candle_minutes": 40}
    assert "test-household" not in (tmp_path / "profiles.json").read_text()


def test_delete_missing_profile_is_noop(tmp_path):
    path = tmp_path / "profiles.json"
    store = PrefStore(path)
    assert store.delete("nobody") is False
    assert not path.exists()  # nothing written when there was nothing to delete
    store.update("keep", candle_minutes=18)
    before = path.read_text()
    assert store.delete("nobody") is False
    assert path.read_text() == before


def test_delete_uses_same_key_normalisation(tmp_path):
    store = PrefStore(tmp_path / "profiles.json")
    store.update("Test Household", candle_minutes=18)
    assert store.delete("test household") is True
    assert store.get("Test Household") == {}
