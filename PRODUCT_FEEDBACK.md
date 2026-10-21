# Product feedback

Honest notes from building Shabbos & Zmanim (Oct 20–21, 2026).

## Tools, APIs and SDKs used, and what for
| Tool | Version | Used for |
|---|---|---|
| MCP Python SDK (`mcp`) | 2.3.0 (with `mcp-types` 2.3.0) | Server (`MCPServer`, Streamable HTTP, resources, prompts, the MCP Apps extension) and client (`mcp.Client`, for end-to-end tests and the demo) |
| MCP specification | 2026-07-28 (current), 2025-11-25 (negotiated) | Protocol |
| MCP TypeScript SDK | `@modelcontextprotocol/sdk` 1.32.1 and `@modelcontextprotocol/server` 2.3.1 | Evaluated, not used (see below) |
| Hebcal.com REST APIs | v1.16.2 (as reported in responses) | Zmanim, calendar (Shabbos, parsha, holidays, daf), date converter, city search |
| AWS services | none | — |

## What worked well
- **Python SDK, dual-era protocol support.** One server binary answered both a 2026-07-28 client (`mode="auto"`) and a 2025-11-25 handshake client (`mode="legacy"`) with no code changes. This removed the biggest compliance risk for the Alexa+ track.
- **`MCPServer` ergonomics.** Typed Python signatures with `Annotated[..., Field(description=...)]` turned into clean JSON input schemas with descriptions, ranges and enums (`Literal`). `ToolAnnotations` (readOnlyHint, etc.) worked first try.
- **`mcp.Client` for testing.** `Client("http://…/mcp")` made a real Streamable HTTP end-to-end test about 60 lines. `structured_content`, `is_error` and `read_resource` all behaved as documented.
- **Tool errors.** Raising `ToolError` came back as `isError: true` with our message, not a protocol error. That is right for voice ("I couldn't find that city").
- **Hebcal APIs.** Fast (~80–240 ms), no key, clear CC BY 4.0 terms, and a stated rate limit. The `lg=a` Ashkenazi transliteration ("Parshas", "Shavuos") was a pleasant surprise for our audience.

## What needs work
- **SDK parity across languages.** The spec site lists 2026-07-28 as current, but both TypeScript SDK lines (1.32.1 and the split 2.3.1 packages) still have `LATEST_PROTOCOL_VERSION = '2025-11-25'`. Without reading compiled dist files there's no easy way to see which SDK supports which revision. A support matrix on the SDK page would save time.
- **MCP Apps degradation.** `Apps.tool(...)` registers the tool only for clients that negotiate the Apps extension, so the tool disappears entirely from `tools/list` for other clients. The SDK's own docstring says extensions "MUST degrade gracefully". For a voice-first server that's backwards: the tool must always exist, and the UI is the optional part. The same applies to `add_html_resource`.
- **Voice-friendly results.** Returning a `dict` makes the text content a JSON dump. To get "sentence plus structured data" you must build `CallToolResult` yourself, and then you lose the auto-generated `outputSchema`. A first-class `summary`/`content_text` hook would help every voice integration.
- **Capabilities differ by era.** On a 2025-11-25 connection the initialize result doesn't mention the `io.modelcontextprotocol/ui` extension, while on 2026-07-28 it does. That may be correct by spec, but it's surprising and not explained in the docs.
- **Dependency naming.** `mcp` 2.3.0 pulls `httpx2` (import `httpx2`), not `httpx`. Code and snippets that `import httpx` break inside the same venv.
- **Hebcal city search** (`/complete.php`) works well but isn't in the OpenAPI docs. On no match it answers with a different shape (`{"error":"Not Found"}`) than on a match (a list).

## Onboarding (zero to hello world)
About 15 minutes from `pip install mcp` to a Streamable HTTP server answering `initialize`. Most of that time went to finding which SDK supports which protocol revision, not to writing code. The rest of the server (7 tools at the time, now 8; cache, tests) took a few hours.

## Would we build with these again?
**Yes.** The Python SDK's dual-era support and its client made a standards-compliant, well-tested server quick to build, and Hebcal is a model public API. We'd like the Apps-degradation and voice-content issues above fixed.

## Feature requests
| Request | Why it matters | Priority |
|---|---|---|
| Protocol-version support matrix per SDK release | Contest rules and clients name specific revisions | Important |
| Apps-bound tools stay listed for non-Apps clients (UI meta only) | Voice clients lose the tool entirely today | Critical |
| A spoken/summary text hook alongside `structuredContent` with an auto `outputSchema` | Voice assistants need a sentence, agents need data | Important |
| Python-side test host for MCP Apps views | So a server author can verify a `ui://` card renders and receives `tool-result` | Nice-to-have |
