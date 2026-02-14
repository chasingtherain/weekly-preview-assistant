# Product Requirements Document (PRD)
## Weekly Preview Assistant - MVP

---

## 1. Overview

### Product Vision
A personal assistant system that automatically compiles a cohesive weekly preview by coordinating multiple AI agents through the Agent-to-Agent (A2A) protocol. Users manually trigger the system to receive a single, well-formatted summary of their upcoming week.

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
1. User runs command: `python main.py` (defaults to current week) or `python main.py --next` (following week)
2. Weeks start on **Monday** and end on **Sunday**
3. Orchestrator agent coordinates data collection
4. Calendar agent fetches week's events
5. Formatter agent creates readable summary
6. User receives formatted weekly preview saved to file

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

**A2A Messages Received:**
- `task_response` from Calendar Agent
- `format_response` from Formatter Agent

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
- Use Ollama (local LLM) to generate human-friendly summary
- Organize by day of week
- **Group events by calendar source within each day** (e.g., "My events:", "Partner's events:")
- Display "NA" when a calendar has no events for a specific day
- Use bullet point format for events within each group
- Highlight busy days or conflicts (inline with events)
- Create actionable insights
- Return formatted markdown/text

**Input (A2A Message):**
```json
{
  "message_id": "uuid",
  "from_agent": "orchestrator",
  "to_agent": "formatter",
  "message_type": "format_request",
  "data": {
    "calendar_events": [...],
    "conflicts": [...],
    "week_start": "2025-02-17",
    "user_preferences": {
      "timezone": "user_local",
      "format": "markdown"
    }
  }
}
```

**Output (A2A Message):**
```json
{
  "message_id": "uuid",
  "in_reply_to": "original-uuid",
  "from_agent": "formatter",
  "to_agent": "orchestrator",
  "message_type": "format_response",
  "status": "success",
  "result": {
    "formatted_summary": "# WEEK OF FEB 17-23...",
    "format": "markdown",
    "word_count": 450
  }
}
```

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
1. User runs command
2. Orchestrator discovers agents from registry
3. Orchestrator → Calendar Agent (task_request)
4. Calendar Agent processes → Returns (task_response)
5. Orchestrator → Formatter Agent (format_request with calendar data)
6. Formatter Agent processes with Ollama → Returns (format_response)
7. Orchestrator saves final summary
8. Orchestrator prints success message with file location
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
│   └── formatter/
│       ├── agent.py
│       ├── server.py
│       └── ollama_client.py
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
- Google Calendar API (OAuth 2.0, read-only access to primary calendar)
- Ollama (local LLM for formatting)

**Data Storage:**
- JSON files (agent registry, message logs)
- Local file system (summaries)

**LLM:**
- Ollama with llama3 or similar model (free, local)

### 5.3 Agent Communication

**Transport:** HTTP/REST
**Format:** JSON
**Ports:**
- Orchestrator: 5000
- Calendar Agent: 5001
- Formatter Agent: 5002

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

**Markdown file** saved to `output/summaries/YYYY-MM-DD.md`

**Structure:**
```markdown
# WEEK OF FEBRUARY 17-23, 2025

## 🗓️ WEEK AT A GLANCE
- Total events: 12
- Busiest day: Tuesday (5 meetings)
- Light days: Thursday, Saturday

## 📅 DAY BY DAY

### MONDAY, FEBRUARY 17

**My events:**
* 9:00 AM - Team Standup (30 min)
* 2:00 PM - Client Call (1 hour) - Zoom

**Partner's events:**
* 3:00 PM - Kids Soccer Practice (1 hour) - Park

### TUESDAY, FEBRUARY 18 ⚠️ BUSY DAY

**My events:**
* 10:00 AM - Budget Review (1 hour)
* 2:00 PM - Project Sync (45 min) ⚠️ CONFLICT: Overlaps with Budget Review
* 4:00 PM - 1-on-1 with Manager (30 min)

**Partner's events:**
* 3:00 PM - Doctor Appointment (1 hour)

### WEDNESDAY, FEBRUARY 19

**My events:**
* 11:00 AM - Marketing Sync (45 min)

**Partner's events:**
* 2:00 PM - School Pickup

### THURSDAY, FEBRUARY 20

**My events:**
* NA

**Partner's events:**
* 10:00 AM - Dentist (30 min)

[... continues for each day ...]

## 💡 INSIGHTS
- Tuesday is your busiest day with 3 meetings
- Scheduling conflict on Tuesday at 2 PM - reschedule one meeting
- Thursday has no events for you - good for deep work
- Remember to prepare deck for Monday client call

## ⚠️ CONFLICTS
1. **Tuesday 2:00 PM**: Budget Review overlaps with Project Sync
```

### 6.3 Delivery Method

**MVP:** File saved locally to `output/summaries/`
- User checks file after running command
- File path printed in terminal output
- Can be opened in any markdown viewer or text editor

---

## 7. Non-Functional Requirements

### 7.1 Performance
- Total execution time: < 30 seconds
- Calendar API response: < 5 seconds
- Ollama formatting: < 20 seconds
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
- Ollama: Free (runs locally)
- Total: $0/month operational cost

### 7.5 Scalability
- MVP: Single user, local execution
- Future: Multi-user, cloud deployment

---

## 8. Configuration & Setup

### 8.1 Prerequisites
- Python 3.10+
- Ollama installed and running locally
- Google Cloud project with Calendar API enabled
- OAuth 2.0 credentials

### 8.2 Environment Variables
```bash
GOOGLE_CALENDAR_CREDENTIALS_PATH=/path/to/credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=/path/to/token.json
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
USER_TIMEZONE=America/Los_Angeles

# Multi-calendar configuration
CALENDAR_IDS=primary,partner@gmail.com
CALENDAR_LABELS=You,Partner
```

### 8.3 First Run Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install Ollama model
ollama pull llama3

# Authenticate with Google Calendar (one-time)
python setup_calendar.py

# Run the system
python main.py
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
6. **Trigger mechanism**: User runs command manually ✓
7. **LLM choice**: Ollama (local, free) for MVP ✓
8. **Week definition**: Monday through Sunday ✓
9. **Week selection**: `--next` flag for following week, default is current week ✓

---

## 11. Future Enhancements (Post-MVP)

### Phase 2 Agents
- **Email Agent**: Scan for commitments in emails
- **Task Agent**: Pull from Todoist/Notion
- **Context Agent**: Learn patterns, provide insights

### Features
- Automatic scheduling (cron job for Sunday evenings)
- Multi-calendar support (work + personal)
- Customizable output formats (PDF, HTML, email)
- Email or Slack delivery
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

**Document Version:** 1.0  
**Last Updated:** February 14, 2025  
**Status:** Ready for Development