# Weekly Preview Assistant

> A multi-agent system that generates intelligent weekly calendar previews using Google's Agent-to-Agent (A2A) protocol

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Overview

Weekly Preview Assistant is a learning project that implements Agent-to-Agent (A2A) communication protocols. It coordinates specialized AI agents to compile your upcoming week into a single, actionable summary.

**Key Features:**
- 📅 **Smart Calendar Analysis** - Automatically fetches and organizes your week's events
- ⚠️ **Conflict Detection** - Identifies scheduling overlaps and busy periods
- 🤖 **Multi-Agent Coordination** - Demonstrates A2A protocol with independent agents
- 💡 **Actionable Insights** - Generates helpful suggestions for better week planning
- 🔒 **Privacy First** - Runs locally, your data stays on your machine

## Example Output

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
* 2:00 PM - Project Sync (45 min) ⚠️ CONFLICT
* 4:00 PM - 1-on-1 with Manager (30 min)

**Partner's events:**
* 3:00 PM - Doctor Appointment (1 hour)

### THURSDAY, FEBRUARY 20

**My events:**
* NA

**Partner's events:**
* 10:00 AM - Dentist (30 min)

[... continues for each day ...]

## 💡 INSIGHTS
- Tuesday is your busiest day with 3 meetings
- Scheduling conflict on Tuesday at 2 PM needs resolution
- Thursday has no events for you - good for deep work
```

## Architecture

The system uses three independent agents that communicate via A2A protocol:

```
┌─────────────────┐
│   User Command  │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ Orchestrator Agent  │ ◄── Coordinates workflow
└─────────┬───────────┘
          │
          ├─────────────────┐
          │                 │
          ▼                 ▼
┌──────────────────┐  ┌──────────────────┐
│ Calendar Agent   │  │ Formatter Agent  │
│ (Google Cal API) │  │ (Ollama LLM)     │
└──────────────────┘  └──────────────────┘
          │                 │
          └────────┬────────┘
                   │
                   ▼
          ┌────────────────┐
          │  Weekly Summary │
          │    (Markdown)   │
          └────────────────┘
```

**A2A Message Flow:**
1. Orchestrator discovers available agents
2. Sends task request to Calendar Agent
3. Calendar Agent fetches events → responds
4. Orchestrator sends format request to Formatter Agent
5. Formatter Agent creates summary → responds
6. Orchestrator saves final output

## Tech Stack

- **Python 3.10+** - Core implementation
- **Flask/FastAPI** - Agent HTTP servers
- **Google Calendar API** - Event data source
- **Ollama** - Local LLM for intelligent formatting
- **A2A Protocol** - Agent-to-agent communication

## Getting Started

### Prerequisites

1. **Python 3.10 or higher**
   ```bash
   python --version
   ```

2. **Ollama** (for local LLM)
   ```bash
   # Install from https://ollama.ai
   ollama serve
   ollama pull llama3
   ```

3. **Google Calendar API Access**
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project
   - Enable Google Calendar API
   - Create OAuth 2.0 credentials
   - Download `credentials.json`

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/weekly-preview-assistant.git
cd weekly-preview-assistant

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your paths and preferences

# Authenticate with Google Calendar (one-time setup)
python setup_calendar.py
# This will open your browser for OAuth flow
```

### Configuration

Create a `.env` file with:

```bash
# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS_PATH=/path/to/credentials.json
GOOGLE_CALENDAR_TOKEN_PATH=/path/to/token.json

# Multi-calendar Configuration
CALENDAR_IDS=primary,partner@gmail.com
CALENDAR_LABELS=You,Partner

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3

# User Settings
USER_TIMEZONE=America/Los_Angeles
```

### Usage

Run the weekly preview generator:

```bash
python main.py
```

**Output:**
```
Starting Weekly Preview Assistant...
✓ Orchestrator agent started on port 5000
✓ Calendar agent started on port 5001
✓ Formatter agent started on port 5002
✓ All agents registered

Fetching calendar events...
✓ Retrieved 12 events for week of Feb 17-23

Formatting summary...
✓ Summary generated

Weekly preview saved to: output/summaries/2025-02-17.md
```

Your weekly preview will be saved as a markdown file in `output/summaries/`.

## Project Structure

```
weekly-preview-assistant/
├── agents/              # Independent AI agents
│   ├── orchestrator/    # Workflow coordinator
│   ├── calendar/        # Google Calendar integration
│   └── formatter/       # LLM-based formatting
├── a2a/                 # A2A protocol implementation
│   ├── protocol.py      # Message schemas
│   ├── registry.py      # Agent discovery
│   └── client.py        # HTTP communication
├── config/              # Configuration files
├── logs/                # A2A messages and errors
├── output/              # Generated summaries
├── tests/               # Unit and integration tests
└── main.py             # Entry point
```

## Learning Goals

This project demonstrates:

✅ **Agent-to-Agent Protocol** - Practical implementation of A2A communication  
✅ **Distributed Systems** - Independent agents coordinating via HTTP  
✅ **API Integration** - Google Calendar OAuth and data fetching  
✅ **LLM Integration** - Using local models for intelligent formatting  
✅ **Error Handling** - Retry logic, timeouts, graceful degradation  
✅ **Message Logging** - Complete audit trail of agent communication  

## Development

### Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_calendar.py

# With coverage
pytest --cov=agents tests/
```

### Viewing A2A Message Logs

```bash
# Pretty-print today's messages
cat logs/a2a_messages/$(date +%Y-%m-%d).log | jq

# Filter by agent
cat logs/a2a_messages/*.log | jq 'select(.from_agent == "calendar-001")'

# See only errors
cat logs/a2a_messages/*.log | jq 'select(.message_type == "error")'
```

### Code Style

```bash
# Format code
black .

# Lint code
pylint agents/ a2a/
```

## Future Enhancements

**Planned Features:**
- [ ] Email agent (scan inbox for commitments)
- [ ] Task agent (Todoist/Notion integration)
- [ ] Context agent (learn patterns, provide insights)
- [ ] Automatic scheduling (cron job)
- [ ] Email/Slack delivery
- [ ] Multi-calendar support
- [ ] Web dashboard

**Technical Improvements:**
- [ ] Switch to cloud-hosted LLM option
- [ ] Deploy to cloud (AWS Lambda, GCP Cloud Run)
- [ ] Multi-user support
- [ ] Agent monitoring and health checks

## Cost

**MVP Version:**
- Google Calendar API: **Free** (within quota)
- Ollama: **Free** (runs locally)
- Total: **$0/month**

**Future (with cloud LLM):**
- Claude API: ~$0.05-0.10 per summary
- Total: ~$0.50/month for weekly summaries

## Contributing

This is primarily a learning project, but suggestions and improvements are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Documentation

- **[PRD](docs/PRD.md)** - Product Requirements Document
- **[Claude Instructions](claude.md)** - Guide for AI coding assistants
- **[API Reference](docs/API.md)** - A2A message specifications (coming soon)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Google's Agent-to-Agent (A2A) protocol for inspiration
- Anthropic's Claude for development assistance
- Ollama team for local LLM infrastructure

## Contact

**Project Link:** https://github.com/yourusername/weekly-preview-assistant

---

Built with ❤️ as a learning project to understand Agent-to-Agent communication protocols