# Meeting Bot API 🤖

> **Production-grade FastAPI application for automated meeting joining, transcription, and calendar monitoring**

A sophisticated Python-based meeting bot that automatically monitors your calendar, joins online meetings (Google Meet, Zoom, Microsoft Teams), and provides real-time transcription capabilities—all through a clean REST API with OAuth authentication.

---

## 🌟 Features

- ✅ **Automated Meeting Join** - Monitors Gmail/Outlook calendars and automatically joins meetings
- ✅ **Multi-Platform Support** - Google Meet, Zoom, Microsoft Teams
- ✅ **Real-Time Transcription** - Captures meeting captions and saves transcripts
- ✅ **OAuth Authentication** - Secure Gmail and Outlook OAuth 2.0 flows
- ✅ **Manual Meeting Join** - Join any meeting instantly via API or web UI
- ✅ **Production Architecture** - Clean layered architecture with dependency injection
- ✅ **REST API** - Full-featured API with Swagger/ReDoc documentation
- ✅ **Browser Automation** - Playwright-based stealth mode for reliable joining
- ✅ **Smart Scheduling** - APScheduler with deduplication and time zone support

---

## 🏗️ Architecture

```
📦 meeting-note-tker/
├── 🚀 run.py                      # Application entry point
├── 📋 requirements.txt            # Python dependencies
├── 📝 README.md                   # This file
├── ⚙️  .env                        # Environment configuration
├── 🗂️  app/                        # Main application package
│   ├── main.py                   # FastAPI initialization
│   ├── core/                     # Core infrastructure
│   │   ├── config.py            # Settings (Pydantic)
│   │   ├── logging.py           # Logging configuration
│   │   ├── dependencies.py      # Dependency injection
│   │   └── exceptions.py        # Custom exceptions
│   ├── api/v1/                  # API Layer (versioned)
│   │   ├── endpoints/           # Route handlers
│   │   │   ├── auth.py         # OAuth endpoints
│   │   │   ├── meetings.py     # Meeting control
│   │   │   └── health.py       # Status & health
│   │   └── schemas/             # Pydantic models
│   ├── domain/                  # Business Logic Layer
│   │   ├── models/              # Domain models
│   │   │   └── meeting.py      # Meeting entities
│   │   └── services/            # Business services
│   │       └── meeting_bot_service.py  # Core orchestrator
│   └── infrastructure/          # Implementation Layer
│       ├── email_service/       # Gmail, Calendar API
│       ├── scheduler/           # APScheduler
│       ├── meeting_handler/     # Playwright automation
│       └── transcription/       # Transcript service
├── 📁 credentials/               # OAuth tokens (gitignored)
├── 📁 transcripts/               # Meeting transcripts
├── 📁 logs/                      # Application logs
├── 📁 docs/                      # Additional documentation
└── 🧪 tests/                     # Test suite
```

### **Clean Architecture Layers**

1. **API Layer** (`app/api/`) - HTTP endpoints, request/response handling
2. **Domain Layer** (`app/domain/`) - Business logic, entities, services
3. **Infrastructure Layer** (`app/infrastructure/`) - External services (email, browser, etc.)
4. **Core Layer** (`app/core/`) - Cross-cutting concerns (config, logging, DI)

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+**
- **Google Chrome** (for Playwright browser automation)
- **Virtual environment recommended**

### Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd meeting-note-tker

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Set up environment variables (optional)
cp .env.example .env  # Edit .env with your settings
```

### Running the Application

```bash
# Start the production API server
python run.py
```

The server will start at **http://localhost:8888**

**🎉 You'll see:**
```
============================================================
MEETING BOT API - Production Server
============================================================
🚀 Starting FastAPI application...
📍 Host: localhost:8888
📚 API Docs: http://localhost:8888/api/docs
🔐 Dashboard: http://localhost:8888/api/v1/auth
============================================================
```

---

## 🔐 Authentication

### First-Time Setup

1. **Open the dashboard:** http://localhost:8888/api/v1/auth
2. **Click "Authenticate with Google"** to start Gmail OAuth flow
3. **Grant permissions** for Calendar and Gmail read access
4. **Done!** The bot will start monitoring your calendar

### Supported Providers

- ✅ **Gmail** (OAuth 2.0 - required for Gmail API)
- ✅ **Outlook/Microsoft 365** (OAuth 2.0)
- ✅ **Calendar API** (Backend endpoint integration)

---

## 📡 API Documentation

### Interactive API Docs

- **Swagger UI:** http://localhost:8888/api/docs
- **ReDoc:** http://localhost:8888/api/redoc

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/auth/status` | Check authentication status |
| `GET` | `/api/v1/status` | Get bot status (active sessions) |
| `POST` | `/api/v1/meetings/join` | Manually join a meeting |
| `GET` | `/api/v1/meetings/join` | Manual join UI (HTML) |
| `GET` | `/api/v1/auth` | OAuth authentication dashboard |

### Example: Manual Meeting Join

**Web UI:**
```
http://localhost:8888/api/v1/meetings/join
```

**API Request:**
```bash
curl -X POST "http://localhost:8888/api/v1/meetings/join" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "Meeting Transcriber",
    "meeting_url": "https://meet.google.com/abc-defg-hij"
  }'
```

**Response:**
```json
{
  "success": true,
  "meeting_id": "manual_a1b2c3d4e5f6",
  "session_id": "8f7e6d5c4b3a2",
  "platform": "google_meet"
}
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the root directory:

```bash
# Email Provider
EMAIL_PROVIDER=gmail  # Options: gmail, outlook, both, calendar_api

# Scheduler Settings
SCHEDULER__EMAIL_POLL_INTERVAL_SECONDS=40
SCHEDULER__JOIN_BEFORE_START_MINUTES=1
SCHEDULER__MAX_CONCURRENT_MEETINGS=5
SCHEDULER__LOOKAHEAD_HOURS=24

# Auth Server
AUTH_SERVER__HOST=localhost
AUTH_SERVER__PORT=8888
AUTH_SERVER__ENABLED=true

# Bot Behavior
BOT__TEAMS_BOT_NAME="Meeting Transcriber"
BOT__AUTO_ENABLE_CAPTIONS=true
BOT__AUTO_MUTE_ON_JOIN=true

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
DEBUG=false

# Backend API (optional)
BACKEND__URL=http://localhost:8000
BACKEND__API_KEY=your-api-key
```

### Gmail OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Gmail API** and **Google Calendar API**
4. Create **OAuth 2.0 Client ID** (Desktop app)
5. Download credentials JSON
6. Save as `credentials/gmail_credentials.json`

---

## 🛠️ Development

### Project Structure

```
app/
├── main.py              # FastAPI app initialization
├── core/                # Core infrastructure
│   ├── config.py       # Settings management
│   ├── logging.py      # Logging setup
│   ├── dependencies.py # Dependency injection
│   └── exceptions.py   # Custom exceptions
├── api/v1/             # API version 1
│   ├── router.py       # Router aggregator
│   ├── endpoints/      # API endpoints
│   └── schemas/        # Pydantic request/response models
├── domain/             # Business logic (pure Python)
│   ├── models/         # Domain entities
│   └── services/       # Business services
└── infrastructure/     # External integrations
    ├── email_service/  # Gmail, Outlook
    ├── scheduler/      # APScheduler
    ├── meeting_handler/# Playwright automation
    └── transcription/  # Transcript service
```

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
# Format code
black app/

# Lint
flake8 app/

# Type checking
mypy app/
```

---

## 📝 Usage Examples

### Automated Calendar Monitoring

The bot automatically:
1. Polls your calendar every 40 seconds
2. Detects upcoming meetings with join links
3. Joins 1 minute before start time
4. Enables captions/transcription
5. Saves transcripts to `transcripts/` directory
6. Leaves at meeting end time

### Manual Join

```python
import requests

response = requests.post(
    "http://localhost:8888/api/v1/meetings/join",
    json={
        "bot_name": "AI Transcriber",
        "meeting_url": "https://teams.microsoft.com/l/meetup-join/..."
    }
)

print(response.json())
```

### Check Active Sessions

```bash
curl http://localhost:8888/api/v1/status
```

---

## 🔧 Troubleshooting

### Authentication Issues

**Problem:** "Failed to authenticate email services"

**Solution:**
1. Delete old tokens: `rm credentials/gmail_token.json`
2. Restart the app: `python run.py`
3. Re-authenticate at http://localhost:8888/api/v1/auth

### Meeting Join Fails

**Problem:** Bot can't join meeting

**Solutions:**
- Ensure Playwright is installed: `playwright install chromium`
- Check meeting URL format is correct
- Verify platform is supported (Teams, Zoom, Meet)
- Check logs in `logs/` directory

### Port Already in Use

**Problem:** "Address already in use: 8888"

**Solution:**
```bash
# Kill process on port 8888
lsof -ti:8888 | xargs kill -9

# Or change port in .env
AUTH_SERVER__PORT=9999
```

---

## 📚 Additional Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Detailed architecture overview
- [docs/API_ENDPOINTS.md](docs/API_ENDPOINTS.md) - Complete API reference
- [docs/QUICKSTART.md](docs/QUICKSTART.md) - Step-by-step setup guide
- [docs/TECHNOLOGIES.md](docs/TECHNOLOGIES.md) - Technology stack details

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Acknowledgments

- **FastAPI** - Modern, fast web framework
- **Playwright** - Reliable browser automation
- **APScheduler** - Advanced Python scheduler
- **Pydantic** - Data validation using Python type hints

---

## 📞 Support

For issues, questions, or contributions:
- 🐛 **Bug Reports:** Open an issue
- 💡 **Feature Requests:** Open an issue with [Feature] tag
- 📖 **Documentation:** Check `/docs` directory

---

**Made with ❤️ for automated meeting management**
