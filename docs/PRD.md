# Product Requirements Document (PRD)
## Weekly Preview Assistant - MVP

---

## 1. Overview

### Product Vision
A personal assistant system that automatically compiles a cohesive weekly preview by coordinating multiple AI agents through the Agent-to-Agent (A2A) protocol. The system runs automatically every Sunday via macOS launchd and delivers a compact, messaging-friendly preview to Telegram.

### Success Criteria
- User can trigger system with single command
- Generates accurate weekly preview in under 30 seconds
- Users feel more prepared for their week
- Clear A2A message flows between agents
- Costs under $0.10 per weekly summary

---

## 2. Core User Journey

**Primary Use Case:**
> Sarah works a busy job and wants to start each week prepared. Every Sunday evening, she runs a simple command and receives a comprehensive preview of her upcoming week, highlighting important meetings, deadlines, and potential conflicts.

**User Flow:**
1. System triggers automatically every Sunday at 7pm via launchd (or manually: `python main.py --next`)
2. Weeks start on **Monday** and end on **Sunday**
3. Orchestrator agent coordinates data collection
4. Calendar agent fetches week's events
5. Formatter agent creates compact chat-formatted summary
6. Telegram agent delivers the preview to the user's chat
7. Summary is also saved to file as backup

---

## 3. Functional Requirements

### 3.1 Orchestrator Agent

**Responsibilities:**
- Initiate weekly preview workflow on user command
- Discover and register available agents
- Send A2A task requests to calendar agent
- Wait for responses from all agents
- Pass collected data to formatter agent
- Handle errors and timeouts
- Log all A2A messages for debugging

**Capabilities:**
- Agent registry/discovery
- Parallel task coordination
- Response aggregation
- Error recovery

**A2A Messages Sent:**
- `task_request` to Calendar Agent
- `format_request` to Formatter Agent
- `send_telegram_message` to Telegram Agent (optional)

**A2A Messages Received:**
- `task_response` from Calendar Agent
- `format_response` from Formatter Agent
- `task_response` from Telegram Agent (delivery confirmation)

### 3.2 Calendar Agent

**Responsibilities:**
- Connect to Google Calendar API
- Fetch events from multiple manually configured calendars (user's calendar + partner's calendar)
- Fetch events for upcoming 7 days
- Extract relevant event details (title, time, location, attendees, calendar source label)
- Tag each event with configured calendar label (e.g., "You", "Partner")
- Identify all-day events vs. time-specific meetings
- Merge events from all calendars and sort chronologically
- Detect scheduling conflicts (overlapping time blocks within same calendar only)
- Return structured event data via A2A response

**Input (A2A Message):**
```json
{
  "message_id": "uuid",
  "from_agent": "orchestrator",
  "to_agent": "calendar",
  "message_type": "task_request",
  "task": {
    "action": "fetch_week_events",
    "parameters": {
      "start_date": "2025-02-17",
      "end_date": "2025-02-23",
      "calendars": [
        {
          "calendar_id": "primary",
          "label": "You"
        },
        {
          "calendar_id": "partner@gmail.com",
          "label": "Partner"
        }
      ]
    }
  }
}
```

**Output (A2A Message):**
```json
{
  "message_id": "uuid",
  "in_reply_to": "original-uuid",
  "from_agent": "calendar",
  "to_agent": "orchestrator",
  "message_type": "task_response",
  "status": "success",
  "result": {
    "events": [
      {
        "day": "Monday",
        "date": "2025-02-17",
        "time": "9:00 AM",
        "title": "Team Standup",
        "duration": "30 min",
        "attendees": 5,
        "location": "Zoom",
        "calendar_source": "You"
      },
      {
        "day": "Monday",
        "date": "2025-02-17",
        "time": "2:00 PM",
        "title": "Kids Soccer Practice",
        "duration": "1 hour",
        "attendees": 0,
        "location": "Park",
        "calendar_source": "Partner"
      }
    ],
    "conflicts": [
      {
        "time": "Tuesday 2:00 PM",
        "events": ["Budget Review", "Client Call"],
        "calendar_source": "You"
      }
    ],
    "total_events": 12,
    "busiest_day": "Tuesday"
  }
}
```

### 3.3 Formatter Agent

**Responsibilities:**
- Receive structured data from orchestrator
- Build a compact, messaging-friendly summary deterministically (no LLM)
- Organize by day of week, skip empty days
- Use emoji dots per calendar source (e.g., 🔵 JP, 🟢 VT)
- One line per event with compact time format
- Inline conflict markers (⚠️)
- Use WhatsApp-compatible formatting (single `*bold*`)
- Return formatted chat text

**Output format:**
```
📅 *Week of 17-23 Feb*

*Mon 17 Feb*
🔵 JP: Team Standup (9am)
🟢 VT: Soccer Practice (3pm)

*Tue 18 Feb*
🔵 JP: Budget Review (10am) ⚠️
🔵 JP: Client Call (2pm, 2hrs)
🟢 VT: Doctor Appointment (3pm)
```

### 3.4 Telegram Agent

**Responsibilities:**
- Receive formatted text via A2A message from orchestrator
- Send the text to a configured Telegram chat via Bot API
- Return delivery confirmation (message_id, chat_id, sent_at)
- Handle API errors gracefully

**Configuration:**
- `TELEGRAM_BOT_TOKEN`: Bot token from @BotFather
- `TELEGRAM_CHAT_ID`: Target chat or group ID

**Notes:**
- Uses `requests` library to call Telegram Bot API directly (no extra dependency)
- Delivery is optional — if not configured, the workflow skips Telegram
- Telegram failure does not block the rest of the workflow (file save still happens)

---

## 4. A2A Protocol Implementation

### 4.1 Message Schema

**Base Message Format:**
```json
{
  "message_id": "uuid-v4",
  "timestamp": "ISO-8601",
  "from_agent": "agent_identifier",
  "to_agent": "agent_identifier",
  "message_type": "task_request | task_response | error",
  "payload": {}
}
```

### 4.2 Agent Registry

Each agent registers its capabilities on startup:

```json
{
  "agent_id": "calendar-001",
  "name": "Calendar Agent",
  "capabilities": ["fetch_events", "check_availability", "detect_conflicts"],
  "endpoint": "http://localhost:5001",
  "status": "available",
  "registered_at": "2025-02-14T10:00:00Z"
}
```

### 4.3 Communication Flow

```
1. launchd triggers `python main.py --next` (or user runs manually)
2. Orchestrator discovers agents via Agent Cards
3. Orchestrator → Calendar Agent (fetch_week_events)
4. Calendar Agent processes → Returns events and conflicts
5. Orchestrator → Formatter Agent (format_weekly_preview)
6. Formatter Agent builds compact chat format → Returns text
7. Orchestrator → Telegram Agent (send_telegram_message) [optional]
8. Telegram Agent sends to chat → Returns delivery confirmation
9. Orchestrator saves summary to file
```

### 4.4 Error Handling

**Timeout Policy:**
- Calendar Agent: 15 second timeout
- Formatter Agent: 30 second timeout
- On timeout: Log error, return partial results

**Retry Policy:**
- Retry failed requests up to 2 times
- Exponential backoff (2s, 4s)
- After max retries: Graceful degradation

**Error Message Format:**
```json
{
  "message_type": "error",
  "error": {
    "code": "TIMEOUT | API_ERROR | AGENT_UNAVAILABLE",
    "message": "Calendar agent did not respond",
    "agent": "calendar-001",
    "timestamp": "ISO-8601"
  }
}
```

---

## 5. Technical Architecture

### 5.1 System Components

```
weekly-preview-assistant/
├── agents/
│   ├── orchestrator/
│   │   ├── agent.py
│   │   ├── server.py (Flask/FastAPI)
│   │   └── config.py
│   ├── calendar/
│   │   ├── agent.py
│   │   ├── server.py
│   │   └── google_client.py
│   ├── formatter/
│   │   ├── agent.py
│   │   ├── server.py
│   │   └── ollama_client.py
│   └── telegram/
│       ├── agent.py
│       └── server.py
├── a2a/
│   ├── protocol.py (message schemas)
│   ├── registry.py (agent discovery)
│   ├── client.py (HTTP client for A2A)
│   └── validator.py (message validation)
├── config/
│   ├── agents.json (agent registry)
│   └── settings.py
├── logs/
│   └── a2a_messages/ (all message logs)
├── output/
│   └── summaries/ (generated previews)
├── tests/
│   └── test_a2a_flow.py
├── requirements.txt
├── README.md
└── main.py (entry point - starts all agents and triggers workflow)
```

### 5.2 Tech Stack

**Backend:**
- Python 3.10+
- Flask or FastAPI (agent HTTP servers)
- Requests (HTTP client for A2A)

**APIs:**
- Google Calendar API (OAuth 2.0, read-only access)
- Telegram Bot API (message delivery)

**Data Storage:**
- JSON files (agent registry, message logs)
- Local file system (summaries)

**Scheduling:**
- macOS launchd (runs weekly, catches up if Mac was asleep)

### 5.3 Agent Communication

**Transport:** HTTP/REST
**Format:** JSON
**Ports:**
- Orchestrator: 5000
- Calendar Agent: 5001
- Formatter Agent: 5002
- Telegram Agent: 5003

---

## 6. User Interface (MVP)

### 6.1 Command Line Interface

**Running the system:**
```bash
# Current week (Monday-Sunday containing today)
$ python main.py

# Following week
$ python main.py --next

# Output:
Starting Weekly Preview Assistant...
✓ Orchestrator agent started on port 5000
✓ Calendar agent started on port 5001
✓ Formatter agent started on port 5002
✓ All agents registered

Generating preview for: Mon Feb 17 - Sun Feb 23, 2025

Fetching calendar events...
✓ Retrieved 12 events for week of Feb 17-23

Formatting summary...
✓ Summary generated

Weekly preview saved to: output/summaries/2025-02-17.md
```

### 6.2 Output Format

**Compact chat format** optimised for Telegram/WhatsApp delivery:

```
📅 *Week of 17-23 Feb*

*Mon 17 Feb*
🔵 JP: Team Standup (9am)
🔵 JP: Client Call (2pm) - Zoom
🟢 VT: Soccer Practice (3pm)

*Tue 18 Feb*
🔵 JP: Budget Review (10am) ⚠️
🔵 JP: Project Sync (2pm)
🔵 JP: 1-on-1 with Manager (4pm)
🟢 VT: Doctor Appointment (3pm)

*Wed 19 Feb*
🔵 JP: Marketing Sync (11am)
🟢 VT: School Pickup (2pm)

*Thu 20 Feb*
🟢 VT: Dentist (10am)
```

Key format rules:
- Empty days are skipped entirely (no "NA")
- Emoji dots distinguish calendar sources (🔵 first, 🟢 second)
- One line per event with compact time (9am not 9:00 AM)
- Duration only shown if > 1 hour (e.g., "2hrs")
- Conflict marker ⚠️ inline
- Single `*bold*` for WhatsApp/Telegram compatibility

Also saved to `output/summaries/` as backup.

### 6.3 Delivery Method

**Primary:** Telegram Bot delivery
- Sent automatically to configured Telegram chat/group
- Delivery is optional (requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`)
- If Telegram is not configured or fails, summary is still saved to file

**Backup:** File saved locally to `output/summaries/`

---

## 7. Non-Functional Requirements

### 7.1 Performance
- Total execution time: < 15 seconds
- Calendar API response: < 5 seconds
- Formatter (deterministic): < 1 second
- Telegram delivery: < 5 seconds
- Agent startup time: < 3 seconds

### 7.2 Reliability
- 95% success rate for summary generation
- Graceful degradation if one agent fails
- All A2A messages logged for debugging
- Clear error messages to user

### 7.3 Security
- Google OAuth tokens stored securely (not in git)
- Environment variables for sensitive config
- Read-only calendar permissions
- No calendar data stored persistently (only in logs)
- Logs excluded from version control

### 7.4 Cost
- Google Calendar API: Free (within quota)
- Telegram Bot API: Free
- Total: $0/month operational cost

### 7.5 Scalability
- MVP: Single user, local execution
- Future: Multi-user, cloud deployment

---

## 8. Configuration & Setup

### 8.1 Prerequisites
- Python 3.10+
- Google Cloud project with Calendar API enabled
- OAuth 2.0 credentials
- Telegram bot (created via @BotFather)

### 8.2 Environment Variables
```bash
GOOGLE_CALENDAR_CREDENTIALS_PATH=/path/to/credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=/path/to/token.json
USER_TIMEZONE=America/Los_Angeles

# Multi-calendar configuration
CALENDAR_IDS=primary,partner@gmail.com
CALENDAR_LABELS=You,Partner

# Telegram delivery (optional)
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
TELEGRAM_CHAT_ID=your-chat-id
```

### 8.3 First Run Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Authenticate with Google Calendar (one-time)
python setup_calendar.py

# Run the system
python main.py

# Set up automatic scheduling (macOS)
cp com.jp.weekly-preview.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.jp.weekly-preview.plist
```

---

## 9. Success Metrics

### Technical Metrics
- [ ] All agents communicate via A2A protocol
- [ ] Messages conform to schema
- [ ] 100% test coverage for A2A flows
- [ ] Zero crashes over one-week test period
- [ ] All calendar events included accurately
- [ ] Conflicts detected correctly

### User Metrics
- [ ] Summary generated successfully on command
- [ ] Output is readable and actionable
- [ ] User reports feeling more prepared for week
- [ ] Execution time under 30 seconds

### Learning Metrics
- [ ] Clear understanding of A2A concepts
- [ ] Can explain agent discovery mechanism
- [ ] Can debug A2A message flows
- [ ] Portfolio-ready project with clear documentation

---

## 10. Decisions Made

### Open Questions - Resolved

1. **Timezone handling**: Use user's local timezone only ✓
2. **Calendar permissions**: Read-only access to primary calendar ✓
3. **Summary length**: Full day-by-day breakdown, 300-500 words ✓
4. **Conflict detection**: Overlapping time blocks only ✓
5. **Failure mode**: Log error, skip that week, notify user ✓
6. **Trigger mechanism**: Automatic via launchd (Sunday 7pm), manual fallback ✓
7. **Formatting**: Deterministic code (no LLM needed for structured calendar data) ✓
8. **Week definition**: Monday through Sunday ✓
9. **Week selection**: `--next` flag for following week, default is current week ✓
10. **Output format**: Compact chat format for messaging apps (not verbose markdown) ✓
11. **Delivery method**: Telegram Bot API (free, reliable, great formatting) ✓
12. **Scheduling**: macOS launchd with missed-job catch-up on wake ✓

---

## 11. Future Enhancements (Post-MVP)

### Phase 2 Agents
- **Email Agent**: Scan for commitments in emails
- **Task Agent**: Pull from Todoist/Notion
- **Context Agent**: Learn patterns, provide insights

### Features
- ~~Automatic scheduling (cron job for Sunday evenings)~~ Done (launchd)
- ~~Multi-calendar support (work + personal)~~ Done
- ~~Messaging delivery~~ Done (Telegram)
- Meeting prep suggestions
- Travel time calculations
- Smart conflict resolution suggestions
- Week-over-week comparison

### Technical
- Switch to cloud-hosted LLM option (Claude API)
- Deploy to cloud (AWS Lambda, Google Cloud Run)
- Multi-user support
- Web dashboard
- Agent monitoring/health checks
- A/B testing different summary formats

---

## 12. Appendix

### A2A Message Flow Example

**Complete Flow:**

```json
// 1. Orchestrator → Calendar Agent
{
  "message_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2025-02-16T20:00:00Z",
  "from_agent": "orchestrator-main",
  "to_agent": "calendar-001",
  "message_type": "task_request",
  "task": {
    "action": "fetch_week_events",
    "parameters": {
      "start_date": "2025-02-17",
      "end_date": "2025-02-23",
      "calendar_id": "primary"
    }
  },
  "reply_to": "http://localhost:5000/responses"
}

// 2. Calendar Agent → Orchestrator
{
  "message_id": "e5f6g7h8-i9j0-k1l2-m3n4-o5p678901234",
  "in_reply_to": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2025-02-16T20:00:03Z",
  "from_agent": "calendar-001",
  "to_agent": "orchestrator-main",
  "message_type": "task_response",
  "status": "success",
  "result": {
    "events": [
      {
        "day": "Monday",
        "date": "2025-02-17",
        "time": "9:00 AM",
        "title": "Team Standup",
        "duration": "30 min",
        "attendees": 5
      }
    ],
    "conflicts": [],
    "total_events": 12,
    "busiest_day": "Tuesday"
  }
}

// 3. Orchestrator → Formatter Agent
{
  "message_id": "i9j0k1l2-m3n4-o5p6-q7r8-s9t012345678",
  "timestamp": "2025-02-16T20:00:04Z",
  "from_agent": "orchestrator-main",
  "to_agent": "formatter-001",
  "message_type": "format_request",
  "data": {
    "calendar_events": [/* from calendar agent */],
    "conflicts": [],
    "week_start": "2025-02-17",
    "user_preferences": {
      "timezone": "America/Los_Angeles",
      "format": "markdown"
    }
  },
  "reply_to": "http://localhost:5000/responses"
}

// 4. Formatter Agent → Orchestrator
{
  "message_id": "m3n4o5p6-q7r8-s9t0-u1v2-w3x456789012",
  "in_reply_to": "i9j0k1l2-m3n4-o5p6-q7r8-s9t012345678",
  "timestamp": "2025-02-16T20:00:25Z",
  "from_agent": "formatter-001",
  "to_agent": "orchestrator-main",
  "message_type": "format_response",
  "status": "success",
  "result": {
    "formatted_summary": "# WEEK OF FEB 17-23...",
    "format": "markdown",
    "word_count": 432
  }
}
```

---

**Document Version:** 2.0
**Last Updated:** February 15, 2026
**Status:** Implemented