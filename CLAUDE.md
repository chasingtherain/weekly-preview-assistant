# Claude Instructions - Weekly Preview Assistant

## Project Overview
This is a learning project implementing Google's Agent-to-Agent (A2A) protocol. It's a personal assistant that generates weekly calendar previews by coordinating multiple specialized agents.

**Key Goal**: Learn A2A protocol deeply through practical implementation.

**User Trigger**: User manually runs command to generate weekly preview.

## Architecture Principles

### Agent Design
- Each agent is an independent HTTP server (Flask/FastAPI)
- Agents communicate ONLY via A2A protocol messages (JSON over HTTP)
- No direct function calls between agents - always use A2A messages
- Each agent has a single, focused responsibility
- Agents register their capabilities on startup

### A2A Protocol Rules
- All messages MUST conform to the schema in `a2a/protocol.py`
- Always generate UUIDs for message IDs using `uuid.uuid4()`
- Always include timestamps in ISO-8601 format with Z suffix
- Log every A2A message to `logs/a2a_messages/`
- Validate messages before sending using `a2a/validator.py`
- Include `in_reply_to` field in responses to track conversation threads

### Code Conventions
- Python 3.10+ with type hints everywhere
- Use `black` for formatting (line length: 100)
- Use `pylint` for linting
- Docstrings for all public functions (Google style)
- Follow Google Python Style Guide
- Keep functions small and focused (< 50 lines)
- Use descriptive variable names

## File Structure

```
weekly-preview-assistant/
├── agents/
│   ├── orchestrator/    # Coordinates all other agents, manages workflow
│   │   ├── agent.py     # Core orchestration logic
│   │   ├── server.py    # HTTP server (Flask/FastAPI)
│   │   └── config.py    # Configuration
│   ├── calendar/        # Google Calendar integration
│   │   ├── agent.py     # Calendar fetching and conflict detection
│   │   ├── server.py    # HTTP server
│   │   └── google_client.py  # Google API wrapper
│   └── formatter/       # LLM-based summary generation
│       ├── agent.py     # Formatting logic
│       ├── server.py    # HTTP server
│       └── ollama_client.py   # Ollama API wrapper
├── a2a/
│   ├── protocol.py      # A2A message schemas and constants
│   ├── registry.py      # Agent discovery and registration
│   ├── client.py        # HTTP client for A2A communication
│   └── validator.py     # Message schema validation
├── config/
│   ├── agents.json      # Agent registry (runtime)
│   └── settings.py      # Global settings
├── logs/
│   ├── a2a_messages/    # A2A message logs (one file per day)
│   └── errors.log       # Error logs
├── output/
│   └── summaries/       # Generated weekly previews
├── tests/
│   ├── test_orchestrator.py
│   ├── test_calendar.py
│   ├── test_formatter.py
│   └── test_a2a_flow.py  # Integration tests
├── main.py              # Entry point - starts agents and triggers workflow
├── requirements.txt
├── README.md
├── claude.md            # This file
└── docs/
    └── PRD.md           # Product requirements
```

## Development Guidelines

### Adding a New Agent

1. **Create folder structure**
   ```bash
   mkdir -p agents/my_agent
   touch agents/my_agent/agent.py
   touch agents/my_agent/server.py
   ```

2. **Implement `agent.py`** with core logic
   ```python
   class MyAgent:
       def __init__(self):
           self.agent_id = "my_agent-001"
           
       def process_task(self, task_params):
           """Process the task and return result."""
           # Implementation
           return result
   ```

3. **Implement `server.py`** with HTTP endpoints
   ```python
   from flask import Flask, request, jsonify
   
   app = Flask(__name__)
   
   @app.route('/message', methods=['POST'])
   def handle_message():
       message = request.json
       # Validate, process, respond
       return jsonify(response)
   ```

4. **Register capabilities** in startup
   ```python
   registry.register({
       "agent_id": "my_agent-001",
       "capabilities": ["capability_1", "capability_2"],
       "endpoint": "http://localhost:5003",
       "status": "available"
   })
   ```

5. **Add A2A message handlers** following protocol
6. **Write tests** in `tests/test_my_agent.py`

### A2A Message Pattern

**Sending a request:**
```python
import uuid
from datetime import datetime
import requests

message = {
    "message_id": str(uuid.uuid4()),
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "from_agent": "orchestrator-main",
    "to_agent": "calendar-001",
    "message_type": "task_request",
    "task": {
        "action": "fetch_week_events",
        "parameters": {
            "start_date": "2025-02-17",
            "end_date": "2025-02-23",
            "calendars": [
                {"calendar_id": "primary", "label": "You"},
                {"calendar_id": "partner@gmail.com", "label": "Partner"}
            ]
        }
    },
    "reply_to": "http://localhost:5000/responses"
}

# Log the message
log_a2a_message(message, direction="outgoing")

# Send the message
response = requests.post(
    "http://localhost:5001/message",
    json=message,
    timeout=15
)

# Log the response
log_a2a_message(response.json(), direction="incoming")
```

**Receiving and responding:**
```python
@app.route('/message', methods=['POST'])
def handle_message():
    incoming = request.json
    
    # Log incoming message
    log_a2a_message(incoming, direction="incoming")
    
    # Validate message
    if not validate_message(incoming):
        return jsonify(create_error_response(incoming, "INVALID_MESSAGE"))
    
    # Process based on message type
    if incoming["message_type"] == "task_request":
        result = process_task(incoming["task"])
        
        response = {
            "message_id": str(uuid.uuid4()),
            "in_reply_to": incoming["message_id"],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "from_agent": "calendar-001",
            "to_agent": incoming["from_agent"],
            "message_type": "task_response",
            "status": "success",
            "result": result
        }
    
    # Log outgoing response
    log_a2a_message(response, direction="outgoing")
    
    return jsonify(response)
```

### Error Handling

**Always wrap A2A calls in try/except:**
```python
try:
    response = requests.post(
        agent_endpoint,
        json=message,
        timeout=15
    )
    response.raise_for_status()
    return response.json()
    
except requests.Timeout:
    logger.error(f"Timeout calling {agent_endpoint}")
    return create_error_response(message, "TIMEOUT")
    
except requests.RequestException as e:
    logger.error(f"Request failed: {e}")
    return create_error_response(message, "REQUEST_FAILED")
    
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return create_error_response(message, "INTERNAL_ERROR")
```

**Error response format:**
```python
def create_error_response(original_message, error_code):
    return {
        "message_id": str(uuid.uuid4()),
        "in_reply_to": original_message.get("message_id"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "from_agent": "agent-id",
        "to_agent": original_message.get("from_agent"),
        "message_type": "error",
        "error": {
            "code": error_code,
            "message": ERROR_MESSAGES.get(error_code),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    }
```

**Retry logic with exponential backoff:**
```python
import time

def send_with_retry(message, endpoint, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(endpoint, json=message, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s
                logger.warning(f"Retry {attempt + 1}/{max_retries} after {wait_time}s")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed after {max_retries} retries")
                raise
```

### Testing Approach

**Unit tests for individual agents:**
```python
import pytest
from unittest.mock import Mock, patch

def test_calendar_agent_fetch_events():
    """Test calendar agent can fetch events."""
    agent = CalendarAgent()
    
    # Mock Google Calendar API
    with patch('agents.calendar.google_client.fetch_events') as mock_fetch:
        mock_fetch.return_value = [{"title": "Meeting"}]
        
        result = agent.fetch_week_events("2025-02-17", "2025-02-23")
        
        assert len(result["events"]) == 1
        assert result["events"][0]["title"] == "Meeting"
```

**Integration tests for A2A flows:**
```python
def test_full_a2a_workflow():
    """Test complete workflow from orchestrator to output."""
    # Start all agents
    orchestrator = start_orchestrator()
    calendar = start_calendar_agent()
    formatter = start_formatter_agent()
    
    # Trigger workflow
    result = orchestrator.generate_weekly_preview()
    
    # Verify A2A messages were sent
    assert len(get_a2a_logs()) >= 4  # Request + response for each agent
    
    # Verify output file created
    assert os.path.exists("output/summaries/2025-02-17.md")
```

**Run tests:**
```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_calendar.py

# With coverage
pytest --cov=agents tests/

# Verbose output
pytest -v tests/
```

## Tech Stack

- **Python 3.10+**: Core language
- **Flask or FastAPI**: Agent HTTP servers (choose one, be consistent)
- **Google Calendar API**: Calendar data source (OAuth 2.0, read-only)
- **Ollama**: Local LLM for formatting (llama3 or similar)
- **Requests**: HTTP client for A2A communication
- **Pytest**: Testing framework
- **Black**: Code formatting
- **Pylint**: Linting

## Common Tasks

### Running the System
```bash
# Ensure Ollama is running
ollama serve

# Run for current week (Monday-Sunday containing today)
python main.py

# Run for following week
python main.py --next

# Output will show:
# - Which week (Mon-Sun) is being generated
# - Agent startup messages
# - Progress updates
# - Final file path
```

### Viewing Logs
```bash
# A2A message logs (pretty-printed JSON)
cat logs/a2a_messages/$(date +%Y-%m-%d).log | jq

# Error logs
tail -f logs/errors.log

# Filter A2A logs by agent
cat logs/a2a_messages/*.log | jq 'select(.from_agent == "calendar-001")'
```

### Running Individual Agents
```bash
# Start calendar agent only (for testing)
python agents/calendar/server.py

# Start orchestrator only
python agents/orchestrator/server.py
```

### Debugging A2A Messages
```bash
# See all messages between two agents
cat logs/a2a_messages/*.log | jq 'select(.from_agent == "orchestrator-main" and .to_agent == "calendar-001")'

# See only errors
cat logs/a2a_messages/*.log | jq 'select(.message_type == "error")'

# Count messages by type
cat logs/a2a_messages/*.log | jq -r '.message_type' | sort | uniq -c
```

### Modifying Output Format

**CRITICAL OUTPUT FORMAT REQUIREMENT:**

Events must be grouped by calendar source within each day:

```markdown
### MONDAY, FEBRUARY 17

**My events:**
* 9:00 AM - Team Standup (30 min)
* 2:00 PM - Client Call (1 hour) - Zoom

**Partner's events:**
* 3:00 PM - Kids Soccer Practice (1 hour)

### TUESDAY, FEBRUARY 18

**My events:**
* NA

**Partner's events:**
* 10:00 AM - Doctor Appointment (1 hour)
```

**Key requirements:**
- Group by calendar label ("My events:", "Partner's events:")
- Use bullet points for events within each group
- Show "NA" when a calendar has no events for a day
- Include time, title, duration, and location (if present)
- Keep conflict markers inline with events (⚠️ CONFLICT)

To modify the format:
1. Update prompt in `agents/formatter/agent.py`
2. Ensure LLM receives calendar_source for each event
3. Test with: `pytest tests/test_formatter.py`
4. Generate sample: `python main.py`
5. Review output in `output/summaries/`

### Adding Calendar Event Fields

1. Update `agents/calendar/agent.py` event parsing
2. Update A2A response schema in `a2a/protocol.py`
3. Update validator in `a2a/validator.py`
4. Update formatter prompt to use new fields
5. Add tests for new fields

## Important Architectural Rules

### NEVER Bypass A2A Protocol
❌ **Wrong:**
```python
# Direct function call
events = calendar_agent.fetch_events()
```

✅ **Correct:**
```python
# A2A message
message = create_task_request("calendar-001", "fetch_week_events", {...})
response = send_a2a_message(message, calendar_endpoint)
events = response["result"]["events"]
```

### Always Log A2A Messages
Every message sent or received MUST be logged:
```python
# After sending
log_a2a_message(message, direction="outgoing", agent_id="orchestrator-main")

# After receiving
log_a2a_message(response, direction="incoming", agent_id="orchestrator-main")
```

### Keep Agents Independent
- One agent failure shouldn't crash others
- Agents should handle missing dependencies gracefully
- Use timeouts on all A2A calls
- Return partial results when possible

### Follow the PRD
Always refer to `docs/PRD.md` for:
- Requirements and scope
- Message format specifications
- Success criteria
- Design decisions

## Environment Setup

### Required Environment Variables
```bash
# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS_PATH=/path/to/credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=/path/to/token.json

# Multi-calendar Configuration
# Comma-separated calendar IDs to fetch events from
CALENDAR_IDS=primary,partner@gmail.com
# Comma-separated labels for each calendar (same order as IDs)
CALENDAR_LABELS=You,Partner

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3

# User settings
USER_TIMEZONE=America/Los_Angeles

# Agent ports (optional, defaults shown)
ORCHESTRATOR_PORT=5000
CALENDAR_PORT=5001
FORMATTER_PORT=5002
```

### First-Time Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install and start Ollama
# (see https://ollama.ai for installation)
ollama serve
ollama pull llama3

# Set up Google Calendar API
# 1. Go to Google Cloud Console
# 2. Create project and enable Calendar API
# 3. Create OAuth 2.0 credentials
# 4. Download credentials.json

# Authenticate with Google (one-time)
python setup_calendar.py
# This will open browser for OAuth flow
# Token will be saved to token.json
```

## Current Implementation Status

- [ ] Project structure created
- [ ] A2A protocol layer (`a2a/`) implemented
- [ ] Agent registry system working
- [ ] Orchestrator agent complete
- [ ] Calendar agent complete (Google Calendar integration)
- [ ] Formatter agent complete (Ollama integration)
- [ ] Message logging functional
- [ ] Error handling in place
- [ ] Unit tests written
- [ ] Integration tests written
- [ ] End-to-end workflow tested
- [ ] Documentation complete

## References

- **PRD**: `docs/PRD.md` - Full product requirements
- **Google A2A Spec**: [To be added when available]
- **Google Calendar API**: https://developers.google.com/calendar
- **Ollama API**: https://github.com/ollama/ollama/blob/main/docs/api.md

## Tips for Claude Code

- When implementing agents, start with the message handler skeleton first
- Always validate incoming messages before processing
- Use type hints to make message structures clear
- Create helper functions for common A2A patterns (send_request, create_response)
- Test each agent independently before integration
- Keep A2A message logs clean and readable (use proper JSON formatting)
- When debugging, trace the complete message flow through logs
- Remember: this is a learning project, prioritize clarity over optimization

## Common Pitfalls to Avoid

1. ❌ Forgetting to log A2A messages
2. ❌ Not validating message schemas
3. ❌ Using direct function calls instead of A2A messages
4. ❌ Not handling timeouts and errors
5. ❌ Hardcoding agent endpoints (use registry)
6. ❌ Missing `in_reply_to` in response messages
7. ❌ Not using ISO-8601 timestamps with Z suffix
8. ❌ Blocking the main thread while waiting for responses