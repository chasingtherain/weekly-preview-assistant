# Implementation Journal

Track what was built in each phase and how it maps to A2A concepts.

---

## Phase 1: A2A Foundation (aligned with Google A2A spec)

Initially built with a custom message format, then refactored to align with the actual Google A2A protocol specification (https://github.com/google/A2A).

### Files created

**`a2a/protocol.py`** — Google A2A spec core objects
> Implements Task (with lifecycle states: submitted → working → completed/failed), Message (with role: user/agent), Part (TextPart, DataPart), Artifact, AgentCard, and SendMessageRequest. These match the objects defined in `a2a.proto` from the official spec.

**`a2a/validator.py`** — Schema validation for all A2A objects
> Validates Parts, Messages, Tasks, TaskStatus, SendMessageRequests, and AgentCards against the spec's required fields. Catches malformed objects early.

**`a2a/logger.py`** — Message Lifecycle steps 3 & 7
> The "double logging" — every message is logged both when sent and when received. Creates a complete audit trail in NDJSON format (one JSON object per line, filterable with `jq`).

**`a2a/discovery.py`** — Principle 2: Agent Card discovery
> Replaces the original central registry. Each agent serves its Agent Card at `GET /.well-known/agent.json` (per the A2A spec). The orchestrator fetches these cards to discover agent capabilities and endpoints. `find_agent_by_skill()` finds an agent that has a specific skill ID.

**`a2a/client.py`** — A2A HTTP+JSON transport
> Implements `send_message()` (POST /message/send) and `get_task()` (GET /tasks/{id}) — the two main A2A RPCs we need for MVP. Includes validation, logging, timeout, and retry with exponential backoff.

**`config/settings.py`** — Multi-calendar config
> Loads `CALENDAR_IDS` and `CALENDAR_LABELS` from env vars, pairing them into calendar configs.

### What changed from custom → Google A2A spec

- **Central registry → Agent Cards**: Agents self-describe at `/.well-known/agent.json` instead of registering into a central directory
- **Custom message types → Task lifecycle**: Instead of `task_request`/`task_response` pairs, we now use Task objects with states (submitted → working → completed/failed)
- **Free-form payloads → Message + Parts**: Structured content using Role (user/agent) and Parts (text, data)
- **POST /message → POST /message/send**: Endpoint aligned with spec
- **New: Artifacts**: Task outputs are now Artifact objects containing Parts

### Key takeaway

The protocol layer now follows the real Google A2A spec. Any agent that speaks A2A could interoperate with ours. The core concepts (message-based communication, discovery, auditability) are the same, but the wire format is now standardized.

### Tests

66 tests covering protocol, validator, discovery, logger, and settings — all passing.

---

## Phase 2: Calendar Agent

The first real A2A agent — a standalone Flask HTTP server that speaks the Google A2A protocol.

### Files created

**`agents/calendar/google_client.py`** — Google Calendar API wrapper
> Isolates all Google-specific code: OAuth token loading/refresh, event fetching via the Calendar API, and parsing raw events into our simplified format (handling all-day vs timed events, duration calculation, attendee counts).

**`agents/calendar/agent.py`** — Core business logic
> `CalendarAgent` class that fetches from multiple configured calendars, tags each event with its `calendar_source` label, merges events chronologically, and detects scheduling conflicts (overlapping time blocks within the same calendar only).

**`agents/calendar/server.py`** — A2A-compliant HTTP server
> The complete A2A agent implementation with three endpoints:
> - `GET /.well-known/agent.json` — Agent Card for discovery
> - `POST /message/send` — SendMessage RPC (receives Message, creates Task, processes through lifecycle, returns Task with Artifacts)
> - `GET /tasks/<id>` — GetTask RPC (check task status)

### A2A concepts demonstrated

- **Agent Card discovery**: The server serves its own Agent Card describing its `fetch_week_events` skill — no central registry needed
- **Task lifecycle**: Each request creates a Task that moves through `submitted → working → completed` (or `failed`). You can see the state transitions in the server code
- **Messages with Parts**: The orchestrator sends a DataPart containing the action/parameters; the agent responds with a DataPart containing the results
- **Artifacts**: Results are wrapped in an Artifact object attached to the Task, not returned as a raw response
- **Self-contained messages**: The request includes everything needed (date range, calendar IDs, labels) — no hidden state

### How a request flows through the Calendar Agent

```
1. Client POSTs SendMessageRequest to /message/send
2. Server validates the request (validator.py)
3. Server logs incoming message (logger.py)
4. Server creates Task (state: SUBMITTED)
5. Server extracts action params from Message's DataPart
6. Server updates Task (state: WORKING)
7. Agent fetches events from Google Calendar API
8. Agent tags events, merges, detects conflicts
9. Server wraps result in Artifact, attaches to Task
10. Server updates Task (state: COMPLETED)
11. Server logs outgoing response
12. Server returns {task: ...} with the completed Task
```

### Tests

23 new tests (89 total) covering: event parsing, duration calculation, conflict detection, event sorting, server endpoints (Agent Card, SendMessage, GetTask), and error cases.

---

## Phase 3: Formatter Agent

The second A2A agent — takes structured calendar data and produces a human-friendly weekly preview using a local LLM (Ollama).

### Files created

**`agents/formatter/ollama_client.py`** — Ollama API wrapper
> Isolates all Ollama-specific code: sends prompts to `/api/generate` with streaming disabled, handles timeouts and error responses. Clean interface — just `generate(prompt, model, host)` → string.

**`agents/formatter/agent.py`** — Core business logic
> `FormatterAgent` class with a single method `format_weekly_preview()`. The key function is `build_prompt()` which structures the calendar data into a detailed LLM prompt that enforces the PRD output format: events grouped by calendar source per day, "NA" for empty days, conflict markers, and insights. Helper functions handle source extraction and conflict lookups.

**`agents/formatter/server.py`** — A2A-compliant HTTP server
> Same three-endpoint pattern as the Calendar Agent:
> - `GET /.well-known/agent.json` — Agent Card with `format_weekly_preview` skill
> - `POST /message/send` — Receives calendar data as a DataPart, returns formatted summary as a TextPart artifact (plus a DataPart with metadata like word count)
> - `GET /tasks/<id>` — GetTask RPC

### A2A concepts demonstrated

- **Same pattern, different agent**: The Formatter Agent follows the exact same A2A structure as the Calendar Agent — Agent Card, SendMessage, GetTask. This is the point of A2A: agents are interchangeable modules that all speak the same protocol
- **Data flows through Parts**: Calendar Agent outputs a DataPart with events → Orchestrator forwards to Formatter → Formatter outputs a TextPart with the summary. The Part system handles both structured data and plain text
- **Artifact variety**: Calendar Agent returns a DataPart artifact (structured JSON). Formatter returns a TextPart artifact (markdown text) + DataPart metadata. Same Artifact wrapper, different content types
- **Task lifecycle reuse**: Identical `submitted → working → completed/failed` state machine. The server code is structurally similar to the Calendar Agent's — that's by design

### How data flows through the Formatter

```
1. Orchestrator sends calendar data as DataPart in SendMessageRequest
2. Server validates, creates Task (SUBMITTED)
3. Server extracts events, conflicts, week_start from DataPart
4. build_prompt() structures data into 7-day layout grouped by calendar source
5. Prompt sent to Ollama for LLM generation
6. LLM response wrapped in TextPart artifact + DataPart metadata
7. Task updated to COMPLETED, returned to caller
```

### Prompt engineering approach

The prompt builder (`build_prompt()`) does the heavy lifting — it pre-structures the data so the LLM mostly needs to format rather than reason:
- Generates all 7 days (Monday-Sunday) regardless of whether events exist
- Groups events under each calendar source label per day
- Shows "NA" explicitly for empty source/day combinations
- Inlines conflict markers next to affected events
- Instructs the LLM to follow the exact PRD output structure (Week at a Glance → Day by Day → Insights → Conflicts)

### Tests

23 new tests (112 total) covering: Ollama client (success, empty response, connection error), helper functions (source extraction, conflict lookup), prompt building (7-day coverage, grouping, conflicts, header info), FormatterAgent (mock LLM calls, model config), and server endpoints (Agent Card, SendMessage success/failure, GetTask, error handling).

---

## Phase 4: Orchestrator + main.py

The coordinator that ties everything together — discovers agents, delegates work via A2A messages, and saves the final output.

### Files created

**`agents/orchestrator/agent.py`** — Core orchestration logic
> `OrchestratorAgent` class that runs the full workflow: calculate week range → discover agents via Agent Cards → send A2A message to Calendar Agent → forward result to Formatter Agent → save summary to file. Also contains `calculate_week_range()` (Monday-Sunday, with `--next` support) and `save_summary()` (writes to `output/summaries/YYYY-MM-DD.md`).

**`agents/orchestrator/server.py`** — A2A-compliant HTTP server
> Same three-endpoint pattern as other agents. The orchestrator is both an A2A *server* (can receive `generate_weekly_preview` requests) and an A2A *client* (sends requests to Calendar and Formatter agents). This makes it a fully peer-to-peer participant in the A2A network.

**`main.py`** — Entry point (updated from stub)
> Starts Calendar and Formatter agents as background Flask threads, waits for them to be ready (polls `/.well-known/agent.json`), then runs the orchestrator workflow. Supports `python main.py` (current week) and `python main.py --next` (following week).

### A2A concepts demonstrated

- **Orchestrator as A2A client**: The orchestrator NEVER calls agent functions directly. It constructs SendMessageRequests, POSTs them to agent URLs, and reads results from Task artifacts. All communication goes through the A2A protocol
- **Agent Card discovery in practice**: Before running the workflow, the orchestrator fetches Agent Cards from both agents and checks for required skills (`fetch_week_events`, `format_weekly_preview`). If an agent is missing or doesn't have the right skill, the workflow fails gracefully
- **Data flows through the A2A pipeline**: Calendar data moves as DataParts through the entire chain: Orchestrator → Calendar Agent (DataPart request) → Calendar Agent returns DataPart artifact → Orchestrator forwards to Formatter Agent (DataPart request) → Formatter returns TextPart artifact
- **Error propagation**: Each A2A response is checked for errors at the transport level (HTTP failures, timeouts) and the task level (failed state). Errors propagate cleanly back to the user

### The complete A2A message flow

```
1. main.py starts Calendar + Formatter agents in background threads
2. main.py waits for agents to serve Agent Cards (health check)
3. Orchestrator discovers agents via GET /.well-known/agent.json
4. Orchestrator → Calendar Agent: POST /message/send (fetch_week_events)
5. Calendar Agent creates Task (SUBMITTED → WORKING → COMPLETED)
6. Calendar Agent returns Task with DataPart artifact (events, conflicts)
7. Orchestrator extracts data from Calendar's artifact
8. Orchestrator → Formatter Agent: POST /message/send (format_weekly_preview)
9. Formatter Agent creates Task (SUBMITTED → WORKING → COMPLETED)
10. Formatter Agent returns Task with TextPart artifact (markdown summary)
11. Orchestrator extracts summary from Formatter's artifact
12. Orchestrator saves summary to output/summaries/YYYY-MM-DD.md
```

### Key design decisions

- **Background threads, not processes**: Agent servers run as daemon threads so everything exits cleanly when main.py finishes. No port cleanup needed
- **Health check via Agent Card**: `wait_for_agents()` polls the `/.well-known/agent.json` endpoint — this is both a health check and an A2A-native way to verify readiness
- **No central registry**: The orchestrator knows agent URLs from config, but discovers capabilities at runtime via Agent Cards. If you swap in a different Calendar Agent at the same URL, the orchestrator adapts

### Tests

20 new tests (132 total) covering: week range calculation (Monday/Wednesday/Sunday, next week), file saving, agent discovery, full workflow (mocked A2A calls), error cases (missing agents, calendar failure, formatter failure, task failures), and server endpoints (Agent Card, SendMessage, GetTask, error handling).

---

## Phase 5: Integration Tests

End-to-end tests that verify A2A message flows across multiple agents using real Flask test clients.

### File created

**`tests/test_a2a_flow.py`** — Cross-agent integration tests
> Unlike unit tests (which mock agent internals), these spin up real Flask test clients for Calendar, Formatter, and Orchestrator agents and send actual A2A messages between them. Tests verify the protocol works end-to-end.

### What the tests cover

1. **Agent Card Discovery** — All three agents serve valid, consistently-structured Agent Cards at `/.well-known/agent.json`
2. **Calendar Agent A2A flow** — Full Task lifecycle (SUBMITTED → COMPLETED), Artifact contains event DataPart, Task retrievable via GetTask
3. **Formatter Agent A2A flow** — Task lifecycle produces TextPart artifact (summary) + DataPart artifact (metadata)
4. **Cross-agent data flow** — Calendar Agent's output DataPart is directly usable as Formatter Agent's input. Data passes through the chain without transformation issues
5. **Error propagation** — Invalid requests return 400, missing actions return FAILED tasks, agent exceptions surface in Task status messages, unknown task IDs return 404 across all agents
6. **Task history** — Tasks record the original incoming Message for auditability
7. **Multi-calendar flow** — Events from multiple calendar sources (You, Partner) flow correctly through the A2A chain
8. **Orchestrator end-to-end** — The orchestrator's SendMessage endpoint returns proper Tasks with TextPart + DataPart artifacts

### Key insight: unit tests vs integration tests

The unit tests (Phases 2-4) mock agent internals — they test that `CalendarAgent.fetch_week_events()` works, that `build_prompt()` produces correct output, etc. The integration tests here test the *protocol layer* — that A2A messages are correctly constructed, validated, routed, and that data flows through Parts and Artifacts between agents without getting lost or corrupted.

### Tests

12 new tests (144 total) — all passing.

---

## Phase 6: Telegram Agent + Chat Format + Scheduling

Three changes in this phase: replaced the LLM-based formatter with a deterministic chat format, added a Telegram delivery agent, and set up automated weekly scheduling via macOS launchd.

### Why drop the LLM?

The Formatter originally sent structured calendar data to Ollama (local LLM) to generate a human-readable summary. In practice, the LLM added latency, inconsistency, and a dependency (Ollama must be running). Since the output format is fixed and well-defined, a deterministic Python function (`build_chat_format()`) produces the exact same result every time — faster, with no external dependency for formatting.

The original `build_markdown()` function is still available for file output, but the primary format is now `build_chat_format()` which produces compact, emoji-styled text optimised for messaging apps.

### Files created

**`agents/telegram/agent.py`** — Core Telegram logic
> `TelegramAgent` class with a single `send_message(text)` method. Uses the Telegram Bot API directly via `requests` (no python-telegram-bot dependency). Handles API errors, timeouts, and connection failures. Returns delivery confirmation with `message_id`, `chat_id`, and `sent_at`.

**`agents/telegram/server.py`** — A2A-compliant HTTP server
> Same three-endpoint pattern as all other agents:
> - `GET /.well-known/agent.json` — Agent Card with `send_telegram_message` skill
> - `POST /message/send` — Receives text via DataPart, sends to Telegram, returns delivery result as DataPart artifact
> - `GET /tasks/<id>` — GetTask RPC

**`tests/test_telegram.py`** — Telegram agent tests
> 7 tests covering: successful send, API error, timeout, connection error, server endpoints (Agent Card, SendMessage, GetTask), empty text handling, and agent error propagation.

**`com.jp.weekly-preview.plist`** — macOS launchd job
> Schedules `python main.py --next` to run every Sunday at 8pm. Uses the venv Python interpreter and project working directory. Stdout/stderr go to `logs/launchd-stdout.log` and `logs/launchd-stderr.log`. Installed to `~/Library/LaunchAgents/` and loaded via `launchctl load`.

### Files modified

**`agents/formatter/agent.py`** — Replaced LLM with deterministic format
> `FormatterAgent.format_weekly_preview()` now calls `build_chat_format()` instead of sending a prompt to Ollama. New `build_chat_format()` function produces compact, emoji-styled output: calendar-coloured dots (🔵 JP, 🟢 VT), one line per event, empty days skipped, conflict markers (⚠️). Also added helper functions: `_format_time_compact()` ("9:00 AM" → "9am"), `_duration_minutes()`, `_format_duration_compact()` ("2 hours" → "2hrs").

**`agents/orchestrator/agent.py`** — Added Telegram step to workflow
> `OrchestratorAgent` now accepts an optional `telegram_url`. After formatting, it sends the summary to the Telegram Agent via A2A (`_send_telegram()`). Telegram failure is non-blocking — the workflow still succeeds and saves the file even if Telegram delivery fails. Discovery now checks for three agents instead of two.

**`config/settings.py`** — Added Telegram settings
> New fields: `telegram_bot_token`, `telegram_chat_id`, `telegram_port` (default 5003). All loaded from environment variables.

**`main.py`** — Starts Telegram agent, wires it into workflow
> Now starts three background agents (Calendar, Formatter, Telegram) instead of two. Passes `telegram_url` to the orchestrator. Output shows Telegram delivery status.

### The Formatter's chat format output

```
📅 *Week of 16-22 Feb*

*Mon 16 Feb*
🔵 JP: JPVT wed anni (8am)

*Tue 17 Feb*
🔵 JP: woodlands lunch (12pm)
🟢 VT: woodlands lunch (12pm)

*Thu 19 Feb*
🟢 VT: SH lunch (12pm)

*Fri 20 Feb*
🔵 JP: linda bday (all day)
🟢 VT: Tricia lunch (12pm)
🔵 JP: army cny dinner 7pm (7pm)

*Sun 22 Feb*
🟢 VT: Ah Kor gathering (12pm, 2hrs)
🔵 JP: weekly plan + supabase (8pm)
```

Design choices:
- **Emoji dots by calendar**: 🔵 = first calendar (JP), 🟢 = second (VT), up to 6 colours
- **Empty days skipped**: No "NA" lines — cleaner for chat
- **Duration only shown if > 1 hour**: Keeps lines short for typical 30-60 min events
- **Single-asterisk bold**: Compatible with both WhatsApp (`*bold*`) and Telegram

### The complete A2A message flow (updated)

```
1. main.py starts Calendar, Formatter, and Telegram agents in background threads
2. main.py waits for all three to serve Agent Cards (health check)
3. Orchestrator discovers agents via GET /.well-known/agent.json
4. Orchestrator → Calendar Agent: POST /message/send (fetch_week_events)
5. Calendar Agent fetches from Google Calendar API (multiple calendars)
6. Calendar Agent returns Task with DataPart artifact (events, conflicts)
7. Orchestrator → Formatter Agent: POST /message/send (format_weekly_preview)
8. Formatter deterministically builds chat-format summary (no LLM)
9. Formatter returns Task with TextPart artifact (chat summary)
10. Orchestrator → Telegram Agent: POST /message/send (send_telegram_message)
11. Telegram Agent sends text to Telegram Bot API
12. Telegram Agent returns Task with DataPart artifact (delivery confirmation)
13. Orchestrator saves summary to output/summaries/YYYY-MM-DD_created-TIMESTAMP.md
```

### Scheduling

The plist job runs every Sunday at 8pm:
- Executes: `/path/to/venv/bin/python main.py --next`
- `--next` generates a preview for the **upcoming** Monday-Sunday week
- If the Mac is asleep at 8pm, launchd runs it on wake
- Logs to `logs/launchd-stdout.log` and `logs/launchd-stderr.log`

### Environment variables added

```
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<your chat ID>
TELEGRAM_PORT=5003
USER_TIMEZONE=Asia/Singapore
```

### Tests

35 new tests (179 total) — all passing.
