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

*(Coming next)*

---

## Phase 4: Orchestrator + main.py

*(Coming next)*

---

## Phase 5: Integration Tests

*(Coming next)*
