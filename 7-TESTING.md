# Testing

## 1. Automated tests: 41 passing

```
$ .venv/bin/python -m pytest -v
============================= test session starts ==============================
platform linux -- Python 3.11.6, pytest-9.1.1, pluggy-1.7.0 -- /home/user/tab/files/hackathon/zmanim-mcp/.venv/bin/python
rootdir: /home/user/tab/files/hackathon/zmanim-mcp
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.15.1
collecting ... collected 41 items

tests/test_astro.py::test_lakewood_matches_hebcal_within_one_minute PASSED [  2%]
tests/test_astro.py::test_jerusalem_sunset_and_dst_offset PASSED         [  4%]
tests/test_astro.py::test_order_of_zmanim_is_monotonic PASSED            [  7%]
tests/test_astro.py::test_polar_day_returns_none_instead_of_crashing PASSED [  9%]
tests/test_astro.py::test_sun_event_helper PASSED                        [ 12%]
tests/test_e2e_streamable_http.py::test_streamable_http_end_to_end[auto-2026-07-28] PASSED [ 14%]
tests/test_e2e_streamable_http.py::test_streamable_http_end_to_end[legacy-2025-11-25] PASSED [ 17%]
tests/test_geo.py::test_bundled_aliases[Lakewood-Lakewood] PASSED        [ 19%]
tests/test_geo.py::test_bundled_aliases[Lakewood, NJ-Lakewood] PASSED    [ 21%]
tests/test_geo.py::test_bundled_aliases[lakewood nj-Lakewood] PASSED     [ 24%]
tests/test_geo.py::test_bundled_aliases[Brooklyn-Brooklyn] PASSED        [ 26%]
tests/test_geo.py::test_bundled_aliases[Boro Park-Brooklyn] PASSED       [ 29%]
tests/test_geo.py::test_bundled_aliases[Five Towns-Woodmere] PASSED      [ 31%]
tests/test_geo.py::test_bundled_aliases[Yerushalayim-Jerusalem] PASSED   [ 34%]
tests/test_geo.py::test_bundled_aliases[Jerusalem-Jerusalem] PASSED      [ 36%]
tests/test_geo.py::test_bundled_aliases[Montreal-Montr\xe9al] PASSED     [ 39%]
tests/test_geo.py::test_bundled_aliases[NYC-New York City] PASSED        [ 41%]
tests/test_geo.py::test_bundled_aliases[Tzfat-Safed] PASSED              [ 43%]
tests/test_geo.py::test_qualifier_mismatch_falls_through PASSED          [ 46%]
tests/test_geo.py::test_israel_flag_and_hebcal_params PASSED             [ 48%]
tests/test_geo.py::test_coordinates_require_timezone PASSED              [ 51%]
tests/test_hebcal_client.py::test_rate_limiter_spacing_and_window PASSED [ 53%]
tests/test_hebcal_client.py::test_ttl_cache_lru_and_expiry PASSED        [ 56%]
tests/test_prefs.py::test_delete_existing_profile PASSED                 [ 58%]
tests/test_prefs.py::test_delete_missing_profile_is_noop PASSED          [ 60%]
tests/test_prefs.py::test_delete_uses_same_key_normalisation PASSED      [ 63%]
tests/test_tools.py::test_get_zmanim_lakewood PASSED                     [ 65%]
tests/test_tools.py::test_shabbos_times_lakewood_default_18 PASSED       [ 68%]
tests/test_tools.py::test_shabbos_times_jerusalem_default_40 PASSED      [ 70%]
tests/test_tools.py::test_shabbos_times_custom_minutes PASSED            [ 73%]
tests/test_tools.py::test_shabbos_times_yom_tov_block PASSED             [ 75%]
tests/test_tools.py::test_parsha_diaspora_and_israel_differ PASSED       [ 78%]
tests/test_tools.py::test_upcoming_holidays_groups_multi_day PASSED      [ 80%]
tests/test_tools.py::test_daf_yomi PASSED                                [ 82%]
tests/test_tools.py::test_convert_both_ways PASSED                       [ 85%]
tests/test_tools.py::test_remember_location_is_used_later PASSED         [ 87%]
tests/test_tools.py::test_forget_location_deletes_saved_profile PASSED   [ 90%]
tests/test_tools.py::test_forget_missing_profile_is_a_noop PASSED        [ 92%]
tests/test_tools.py::test_fallback_when_hebcal_is_down PASSED            [ 95%]
tests/test_tools.py::test_cache_prevents_duplicate_requests PASSED       [ 97%]
tests/test_tools.py::test_bad_inputs_have_spoken_errors PASSED           [100%]

============================== 41 passed in 3.49s ==============================
```

What the tests cover:

| File | Covers |
|---|---|
| `tests/test_e2e_streamable_http.py` | Starts the **real server process** and connects with the official SDK `mcp.Client` over **Streamable HTTP**. Runs once negotiating **2026-07-28** (`mode="auto"`) and once on **2025-11-25** (`mode="legacy"`). Checks that `tools/list` returns exactly the 8 tools with descriptions and object input schemas, that `shabbos_times` carries `_meta.ui.resourceUri`, and that `forget_my_location` is annotated destructive and idempotent. **Calls every tool** (12 calls, live Hebcal) and checks text plus structured content plus attribution. Also checks a bad city (tool error with a speakable message), `resources/list` and `resources/read` of the MCP Apps card (`text/html;profile=mcp-app`), and `prompts/get`. |
| `tests/test_tools.py` | Each tool's logic against **recorded real Hebcal responses** (`tests/fixtures/hebcal_responses.json`, refreshed with `RECORD_FIXTURES=1`) with a fixed clock. Covers Lakewood 18 min vs. Jerusalem 40 min defaults, custom minutes, a Pesach Yom Tov block (3 candle lightings), Israel vs. diaspora parsha (Shabbos 23 Apr 2022), holiday grouping, daf, date conversion both ways, saved preferences, forgetting a saved profile (and forgetting one that was never saved, a no-op), the **offline fallback**, the cache, and input errors. |
| `tests/test_astro.py` | The independent NOAA calculator against Hebcal's published times (all within 1 minute), the Israel DST offset, the ordering of zmanim, and the midnight-sun case (no crash, `None`). |
| `tests/test_geo.py` | Bundled city lookup and aliases, a qualifier mismatch falling through ("Lakewood, CO"), and coordinate and time zone validation. |
| `tests/test_hebcal_client.py` | Rate limiter window and spacing, and the LRU+TTL cache. |
| `tests/test_prefs.py` | The saved-preferences file: deleting a profile removes only that profile, deleting a missing profile changes nothing (no file is written), and profile keys are normalised the same way for save and delete. |

Set `ZMANIM_E2E_OFFLINE=1` to skip the end-to-end test (it calls the live Hebcal API).

## 2. Cross-check against hebcal.com: Lakewood, Brooklyn, Jerusalem

`scripts/verify_against_hebcal.py` calls the running server **through an MCP client** and compares the results with:
- the public **hebcal.com Shabbat web page** (HTML, a different endpoint from the API the server uses) for candle lighting, havdalah and parsha, using 18 / 18 / 40 minutes;
- **hebcal.com's zmanim API** for the 10 main zmanim;
- this server's **own NOAA calculation**, shown for reference.

Result (raw output in `verification/hebcal_check.md` and `.json`): **all 39 checks match** for Friday 2026-10-23 and Shabbos 2026-10-24.

Checked 2026-10-21T01:11:09+00:00 for Friday 2026-10-23 / Shabbos 2026-10-23 via MCP protocol 2026-07-28.

| City | Item | MCP server | hebcal.com | Match |
|---|---|---|---|---|
| Lakewood, NJ | candle_lighting | 17:47 | 17:47 (web page) | yes |
| Lakewood, NJ | havdalah | 18:45 | 18:45 (web page) | yes |
| Lakewood, NJ | parsha | Parshas Lech-Lecha | Parashat Lech-Lecha (web page) | yes |
| Lakewood, NJ | alos_hashachar | 05:55 | 05:55 (API) · local NOAA 05:55:15 | yes |
| Lakewood, NJ | sunrise | 07:16 | 07:16 (API) · local NOAA 07:16:05 | yes |
| Lakewood, NJ | sof_zman_shema_mga | 09:22 | 09:22 (API) · local NOAA 09:22:28 | yes |
| Lakewood, NJ | sof_zman_shema_gra | 09:58 | 09:58 (API) · local NOAA 09:58:28 | yes |
| Lakewood, NJ | sof_zman_tefila_gra | 10:53 | 10:53 (API) · local NOAA 10:52:35 | yes |
| Lakewood, NJ | chatzos | 12:41 | 12:41 (API) · local NOAA 12:41:07 | yes |
| Lakewood, NJ | mincha_gedola | 13:08 | 13:08 (API) · local NOAA 13:07:54 | yes |
| Lakewood, NJ | plag_hamincha | 16:58 | 16:58 (API) · local NOAA 16:57:57 | yes |
| Lakewood, NJ | sunset | 18:06 | 18:06 (API) · local NOAA 18:05:36 | yes |
| Lakewood, NJ | tzeis_8_5_degrees | 18:46 | 18:46 (API) · local NOAA 18:46:29 | yes |
| Brooklyn, NY | candle_lighting | 17:45 | 17:45 (web page) | yes |
| Brooklyn, NY | havdalah | 18:44 | 18:44 (web page) | yes |
| Brooklyn, NY | parsha | Parshas Lech-Lecha | Parashat Lech-Lecha (web page) | yes |
| Brooklyn, NY | alos_hashachar | 05:54 | 05:54 (API) · local NOAA 05:54:15 | yes |
| Brooklyn, NY | sunrise | 07:16 | 07:16 (API) · local NOAA 07:15:46 | yes |
| Brooklyn, NY | sof_zman_shema_mga | 09:22 | 09:22 (API) · local NOAA 09:21:46 | yes |
| Brooklyn, NY | sof_zman_shema_gra | 09:58 | 09:58 (API) · local NOAA 09:57:46 | yes |
| Brooklyn, NY | sof_zman_tefila_gra | 10:52 | 10:52 (API) · local NOAA 10:51:46 | yes |
| Brooklyn, NY | chatzos | 12:40 | 12:40 (API) · local NOAA 12:40:03 | yes |
| Brooklyn, NY | mincha_gedola | 13:07 | 13:07 (API) · local NOAA 13:06:46 | yes |
| Brooklyn, NY | plag_hamincha | 16:56 | 16:56 (API) · local NOAA 16:56:16 | yes |
| Brooklyn, NY | sunset | 18:04 | 18:04 (API) · local NOAA 18:03:46 | yes |
| Brooklyn, NY | tzeis_8_5_degrees | 18:45 | 18:45 (API) · local NOAA 18:44:59 | yes |
| Jerusalem | candle_lighting | 17:18 | 17:18 (web page) | yes |
| Jerusalem | havdalah | 18:34 | 18:34 (web page) | yes |
| Jerusalem | parsha | Parshas Lech-Lecha | Parashat Lech-Lecha (web page) | yes |
| Jerusalem | alos_hashachar | 05:35 | 05:35 (API) · local NOAA 05:35:24 | yes |
| Jerusalem | sunrise | 06:48 | 06:48 (API) · local NOAA 06:48:05 | yes |
| Jerusalem | sof_zman_shema_mga | 09:00 | 09:00 (API) · local NOAA 08:59:39 | yes |
| Jerusalem | sof_zman_shema_gra | 09:36 | 09:36 (API) · local NOAA 09:35:39 | yes |
| Jerusalem | sof_zman_tefila_gra | 10:32 | 10:32 (API) · local NOAA 10:31:31 | yes |
| Jerusalem | chatzos | 12:23 | 12:23 (API) · local NOAA 12:23:26 | yes |
| Jerusalem | mincha_gedola | 12:51 | 12:51 (API) · local NOAA 12:51:09 | yes |
| Jerusalem | plag_hamincha | 16:49 | 16:49 (API) · local NOAA 16:48:32 | yes |
| Jerusalem | sunset | 17:58 | 17:58 (API) · local NOAA 17:58:21 | yes |
| Jerusalem | tzeis_8_5_degrees | 18:35 | 18:35 (API) · local NOAA 18:35:03 | yes |

The local NOAA calculation (seconds shown) rounds to the same minute as Hebcal in every row. The largest difference seen is under 0.5 min.

## 3. Manual checks

- The demo client (`scripts/demo_client.py`) ran 8 spoken-style questions against the live server on 2026-10-20 at about 9:12 PM ET. The output is in `logs/demo_client.log` (not committed) and `demo/transcript.json`. Every answer was sensible and correctly worded.
- Hebcal request count after the demo run, from `/healthz`: 8 tool calls led to 7 Hebcal requests (one tool, `remember_my_location`, needed none).

## Known limits

- Times are **sea level** (Hebcal's default), with no elevation adjustment.
- `convert_date` converts the date you give it. It does not decide by itself that it is already after sunset; pass `after_sunset: true`.
- The offline fallback covers zmanim and the weekly Shabbos only. Yom Tov, parsha, holidays and daf need Hebcal.
- The MCP Apps card was rendered in a local browser with a real tool result, but **has not been tested inside an MCP Apps host**.
