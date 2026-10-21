# Friction log

Logged as it happened while building Shabbos & Zmanim (2026-10-20 evening ET to 2026-10-21 UTC). Times are minutes from the start of the build.

---

### 1. Which SDK implements which MCP spec revision?
- **Task:** Pick an official SDK that implements MCP spec 2025-11-25 or later over Streamable HTTP, as the Alexa+ track requires.
- **Steps:** (t+1m) `npm view @modelcontextprotocol/sdk`, latest 1.32.1. Grepped `dist/esm/types.js`: `LATEST_PROTOCOL_VERSION = '2025-11-25'`. Fetched modelcontextprotocol.io/specification/versioning: "The current protocol version is 2026-07-28". Installed the newer split packages `@modelcontextprotocol/server` and `client` 2.3.1: still `LATEST_PROTOCOL_VERSION = "2025-11-25"`. Downloaded the Python wheel `mcp` 2.3.0 and grepped it: `mcp_types.LATEST_PROTOCOL_VERSION = '2026-07-28'`, with separate handshake-era and modern code paths.
- **Expected:** One place (SDK README, release notes or the spec site) stating which revisions each SDK release supports.
- **Actual:** Had to install two TypeScript packages and unzip a Python wheel to find out. The SDK lines differ by a full spec revision.
- **Severity:** Medium. About 4 minutes, with real risk of picking the wrong SDK for a contest with a version requirement.
- **Workaround:** Chose the Python SDK (dual-era). An end-to-end test asserts the negotiated version is 2026-07-28 in `auto` mode and 2025-11-25 in `legacy` mode.
- **Suggestion:** Publish a protocol-revision support matrix per SDK release. Expose a `SUPPORTED_PROTOCOL_VERSIONS` constant in every SDK's public API and its docs.

### 2. Contest rule wording vs. the current spec
- **Task:** Make sure the entry meets "implementing MCP spec version 2025-11-25 (or a later version, once confirmed)".
- **Steps:** Read the rules and the spec site.
- **Expected:** A clear answer on whether 2026-07-28 counts as "confirmed".
- **Actual:** Ambiguous. The spec site calls 2026-07-28 current; the rules only say "once confirmed".
- **Severity:** Low to medium (a compliance risk).
- **Workaround:** Serve both. 2025-11-25 is negotiated through the initialize handshake, which is tested.
- **Suggestion:** State in the rules or FAQ which revisions are accepted as of the submission deadline.

### 3. `mcp` 2.3.0 ships `httpx2`, not `httpx`
- **Task:** Write the Hebcal HTTP client using the SDK's own HTTP dependency to keep the install small.
- **Steps:** (t+6m) `import httpx` gave `ModuleNotFoundError` in a fresh venv with only `mcp==2.3.0`. `pip list` showed `httpx2 2.15.1`.
- **Expected:** `httpx` available, as in older SDK versions and most examples online.
- **Actual:** The dependency is the renamed `httpx2` package.
- **Severity:** Low (about 2 minutes).
- **Workaround:** `import httpx2 as httpx` (same API).
- **Suggestion:** Mention it in the 2.x migration notes, or re-export a client helper so servers don't import the HTTP library directly.

### 4. Tools registered with `Apps.tool()` vanish for non-Apps clients
- **Task:** Attach an MCP Apps `ui://` card to `shabbos_times` for Echo-Show-style screens, while voice clients keep using the tool.
- **Steps:** (t+11m) Used `apps = Apps()`, `@apps.tool(resource_uri="ui://…")`, `apps.add_html_resource(...)`, then `MCPServer(extensions=[apps])`. Connected with a plain `mcp.Client` in `auto` and `legacy` modes and called `tools/list`.
- **Expected:** `shabbos_times` listed for every client, with `_meta.ui.resourceUri` that non-Apps clients ignore. The SDK's own docstring says an extension "MUST degrade gracefully".
- **Actual:** `shabbos_times` was missing from `tools/list` (6 of 7 tools listed). Calling it returned `Unknown tool: shabbos_times`. The `ui://` resource was also missing from `resources/list`.
- **Severity:** High. The most important tool silently disappeared for the main (voice) client. It was caught only because the end-to-end test listed the tools.
- **Workaround:** Register the tool with `@server.tool(..., meta={"ui": {"resourceUri": URI}})` and the HTML with `server.add_resource(TextResource(..., mime_type=APP_MIME_TYPE))`. Keep `Apps()` in `extensions` only so the capability is advertised.
- **Suggestion:** Make `Apps.tool` always register the tool and only gate UI behaviour on negotiation, or offer an explicit `always_list=True`, and document the current behaviour clearly.

### 5. Voice-ready text and structured data at the same time
- **Task:** Return a sentence Alexa+ can speak plus structured data.
- **Steps:** (t+10m) Returned a `dict` from the tool function. The text content became the full JSON dump, which a speaker can't read aloud. Returned `CallToolResult(content=[TextContent(summary)], structured_content=dict)` instead.
- **Expected:** A supported way to give both a human-readable text and structured output from a typed return.
- **Actual:** Possible only by building `CallToolResult` by hand, which drops the auto-generated `outputSchema`.
- **Severity:** Medium (affects every voice integration).
- **Workaround:** Manual `CallToolResult`. The structured fields are documented in the README instead of an `outputSchema`.
- **Suggestion:** Add a `text=`/`summary=` hook (or a `ToolResult(text, data)` helper) that keeps output-schema generation.

### 6. MCP Apps View handshake details live only in the ext-apps spec repo
- **Task:** Write the `ui://` HTML card so a host can deliver the tool result to it.
- **Steps:** The SDK docstrings point to the spec. Fetched `ext-apps/specification/draft/apps.mdx` to learn `ui/initialize`, `ui/notifications/initialized` and `ui/notifications/tool-result`. The example `protocolVersion` in that doc is `"2025-06-18"`.
- **Expected:** A minimal View template or a Python-side test host in the SDK.
- **Actual:** No way to verify from Python that the card receives a result. Rendered it locally in a browser with the real result passed in the URL fragment instead.
- **Severity:** Medium.
- **Workaround:** The card accepts `postMessage` tool results and a `#<json>` fragment for local previews. It is untested inside a real Apps host, and that is called out in TESTING.md.
- **Suggestion:** Ship a tiny reference host (or a pytest fixture) that loads a `ui://` resource and posts a tool result.

### 7. Different capabilities by protocol era
- **Task:** Check that the Apps extension is advertised.
- **Steps:** Compared `client.server_capabilities` in `auto` vs. `legacy` mode.
- **Expected:** The same advertised server features on both.
- **Actual:** 2026-07-28 shows `extensions: {"io.modelcontextprotocol/ui": {}}` and `listChanged: true`. 2025-11-25 shows neither (`listChanged: false`).
- **Severity:** Low. It may be correct by spec, but it's undocumented and surprising.
- **Workaround:** None needed. The tool and resource are listed either way after the workaround in #4.
- **Suggestion:** Document per-era capability differences in the SDK's migration guide.

### 8. Hebcal city search: undocumented, with an inconsistent "not found" shape
- **Task:** Geocode arbitrary city names with no paid geocoder.
- **Steps:** (t+4m) `GET https://www.hebcal.com/complete.php?q=Lakewood` returned a list of GeoNames matches with IDs. `q=Beit%20Shemesh` returned `{"error":"Not Found"}`, an object rather than an empty list, while `q=Bet%20Shemesh` works. The endpoint isn't in Hebcal's OpenAPI docs.
- **Expected:** A documented endpoint that returns `[]` when nothing matches, and handles common spelling variants.
- **Actual:** A shape change on no match, and it is spelling-sensitive.
- **Severity:** Low (would have crashed a naïve client).
- **Workaround:** Treat "Not Found" as no match. Bundle a table of about 50 community cities with aliases (`Beit Shemesh` → `Bet Shemesh`, `Boro Park` → Brooklyn). Fall back to search only after that.
- **Suggestion (to Hebcal):** Document `/complete.php` (or a `/geo/search` JSON endpoint) and return `[]` on no match.

### 9. Finding a date where Israel and the diaspora read different parshiyos (test data)
- **Task:** Write a test proving the `israel` flag matters.
- **Steps:** First guessed Shabbos 2027-05-01. Both schedules read Achrei Mos, so the test failed.
- **Expected/Actual:** My own assumption was wrong (the 8th day of Pesach 2027 is a Thursday). Used Shabbos 2022-04-23, the 8th day of Pesach in the diaspora and Achrei Mos in Israel.
- **Severity:** Low (domain detail, not a product bug). Logged because a voice server has to get this right.
- **Suggestion:** None for the platform. This is why the parsha tool always lets the caller say Israel vs. diaspora.
