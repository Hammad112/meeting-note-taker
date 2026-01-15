# Meeting Bot - System Architecture

## 🏗️ Overview

Meeting Bot is an automated Python application that monitors calendar invites, automatically joins online meetings (Google Meet, Zoom, Microsoft Teams), and provides transcription capabilities. The system uses a modular architecture with asynchronous operations for efficient multi-meeting handling.

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Meeting Bot Core                        │
│                      (main.py)                               │
└─────────────────────────────────────────────────────────────┘
         │                    │                   │
         ▼                    ▼                   ▼
┌──────────────────┐ ┌───────────────┐ ┌────────────────────┐
│  Auth Server     │ │   Scheduler   │ │  Meeting Joiner    │
│  (FastAPI)       │ │  (APScheduler)│ │  (Playwright)      │
│  - OAuth Flows   │ │  - Job Queue  │ │  - Browser Auto.   │
│  - Manual Join   │ │  - Polling    │ │  - Audio Capture   │
│  - API Endpoints │ │  - Callbacks  │ │  - Multi-context   │
└──────────────────┘ └───────────────┘ └────────────────────┘
         │                    │                   │
         ▼                    ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Email Services Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Gmail      │  │ Calendar API │  │   Outlook    │     │
│  │   Service    │  │   Service    │  │   (Removed)  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    External Services                         │
│  • Google APIs (Gmail, Calendar)                            │
│  • Backend Calendar API (optional)                          │
│  • Meeting Platforms (Meet, Zoom, Teams)                    │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Storage                              │
│  • OAuth Tokens (credentials/)                              │
│  • Transcripts (transcripts/)                               │
│  • Logs (logs/)                                             │
│  • Browser Profile (.playwright_user_data/)                 │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Core Components

### 1. **MeetingBot** (main.py)
- **Role**: Central orchestrator
- **Responsibilities**:
  - Initializes all services
  - Manages application lifecycle
  - Coordinates email monitoring, scheduling, and meeting joins
  - Handles graceful shutdown
  - Tracks active meeting sessions
- **Key Features**:
  - Asynchronous architecture using `asyncio`
  - Signal handlers for Ctrl+C shutdown
  - Auth-only mode for initial setup
  - HTTP client for backend communication

### 2. **Auth Server** (auth_server/oauth_server.py)
- **Technology**: FastAPI + Uvicorn
- **Port**: 8888 (default)
- **Endpoints**:
  - `/` - Dashboard UI
  - `/auth/gmail/start` - Start Gmail OAuth flow
  - `/auth/gmail/callback` - OAuth callback handler
  - `/auth/status` - Check authentication status
  - `/health` - Health check
  - `/join` - Manual meeting join (GET for UI, POST for API)
  - `/docs` - Swagger API documentation
  - `/redoc` - ReDoc API documentation
- **Features**:
  - OAuth 2.0 flow management
  - Token storage and validation
  - Manual meeting join interface
  - Web-based authentication (no terminal prompts)

### 3. **Email Services** (email_service/)
- **Base Interface**: `EmailServiceBase`
- **Implementations**:
  - **GmailService**: Uses Google Gmail API + Calendar API
  - **CalendarAPIService**: Backend API integration
- **Features**:
  - OAuth 2.0 authentication
  - iCalendar (.ics) parsing
  - Meeting URL extraction
  - Platform detection (Teams, Zoom, Meet)
  - Deduplication based on meeting URL + time
- **URL Extraction**: 
  - Regex patterns for meeting platforms
  - HTML cleaning for email bodies
  - Multiple URL detection

### 4. **Meeting Scheduler** (scheduler/meeting_scheduler.py)
- **Technology**: APScheduler (AsyncIOScheduler)
- **Job Types**:
  - **Email Polling**: Periodic check for new invites (every 40s default)
  - **Meeting Join**: Scheduled at (start_time - join_before_minutes)
  - **Meeting End**: Cleanup and leave at end_time
- **Features**:
  - Time zone aware (UTC-based)
  - Dynamic job scheduling
  - Event listeners (executed, error, missed)
  - Deduplication to prevent double-booking
  - Configurable lookahead window

### 5. **Meeting Joiner** (meeting_handler/playwright_joiner.py)
- **Technology**: Playwright (Chromium)
- **Capabilities**:
  - Headless browser automation (can run with GUI)
  - Persistent user data directory (stay logged in)
  - Multi-context support (multiple meetings simultaneously)
  - Auto-accept media permissions
  - Stealth mode (avoid detection)
- **Platform Support**:
  - Google Meet
  - Microsoft Teams
  - Zoom
- **Features**:
  - Auto-join detection
  - Kick detection and rejoin logic
  - Screenshot capture on join
  - Transcript saving integration

### 6. **Transcription Service** (transcription/service.py)
- **Storage**: Local text files
- **Features**:
  - Session-based transcription
  - Timestamped entries
  - Speaker identification ready
  - File-per-meeting organization
- **Output Format**: `transcript_{meeting_id}_{timestamp}.txt`
- **Future**: Integration with Whisper, Deepgram, or other STT services

### 7. **Configuration Management** (config/settings.py)
- **Technology**: Pydantic Settings
- **Configuration Sections**:
  - Gmail settings
  - Outlook settings (deprecated)
  - Transcription settings
  - Audio settings
  - Scheduler settings
  - Backend API settings
  - Auth server settings
  - Bot behavior settings
- **Environment Variables**: Prefix-based (e.g., `GMAIL_`, `SCHEDULER_`)
- **Features**:
  - Type validation
  - Default values
  - Environment variable overrides

### 8. **Data Models** (models.py)
- **Primary Models**:
  - `MeetingDetails`: Complete meeting information
  - `MeetingSession`: Runtime session tracking
  - `TranscriptSegment`: Transcription data unit
- **Enums**:
  - `MeetingPlatform`: teams, zoom, google_meet
  - `MeetingSource`: gmail, outlook, calendar_api, manual
- **Features**:
  - Dataclass-based
  - Serialization support (to_dict)
  - Hash and equality for deduplication
  - Timezone-aware datetime handling

## 🔄 Data Flow

### Meeting Join Workflow

```
1. Email Poll Triggered (Every 40s)
   ↓
2. Email Service Fetches Calendar Events
   ↓
3. Parse iCalendar / Extract Meeting URLs
   ↓
4. Create MeetingDetails Objects
   ↓
5. Scheduler.schedule_meeting()
   ↓
6. Job scheduled at (start_time - 1 min)
   ↓
7. Job Execution → _on_meeting_join()
   ↓
8. MeetingJoiner.join_meeting()
   ↓
9. Browser Opens Meeting URL
   ↓
10. Auto-join Logic Executes
    ↓
11. Transcription Starts
    ↓
12. Monitor for Kick → Rejoin if needed
    ↓
13. Meeting End → _on_meeting_end()
    ↓
14. Cleanup: Stop transcription, close browser
    ↓
15. Backend Notification (if configured)
```

### OAuth Authentication Flow

```
1. User Opens http://localhost:8888
   ↓
2. Clicks "Authenticate with Google"
   ↓
3. Redirected to Google OAuth Consent
   ↓
4. User Grants Permissions
   ↓
5. Redirect to /auth/gmail/callback
   ↓
6. Exchange Code for Tokens
   ↓
7. Save tokens to credentials/gmail_token.json
   ↓
8. Bot Detects Token File
   ↓
9. Re-authenticate Email Services
   ↓
10. Initialize Meeting Joiner
    ↓
11. Start Scheduler
```

## 🗄️ Data Storage

### Credentials Directory
```
credentials/
├── gmail_credentials.json  # OAuth client credentials
└── gmail_token.json        # User access/refresh tokens
```

### Transcripts Directory
```
transcripts/
└── transcript_{meeting_id}_{timestamp}.txt
```

### Browser Data
```
.playwright_user_data/
└── [Chromium profile data]
```

### Logs
```
logs/
└── [Application logs with rotation]
```

## 🔐 Security Considerations

1. **OAuth 2.0**: Secure authentication, no password storage
2. **API Keys**: Backend API key authentication
3. **Local Storage**: Tokens stored locally, never transmitted
4. **CORS**: Enabled for web dashboard
5. **HTTPS**: OAuth requires HTTPS redirect URIs (localhost exception)
6. **Scopes**: Minimal required permissions (read-only calendars)

## 🚀 Scalability

### Current Architecture
- **Single Process**: One bot instance per machine
- **Multi-Meeting**: Up to 5 concurrent meetings (configurable)
- **Async I/O**: Non-blocking operations for efficiency

### Scaling Options
1. **Horizontal**: Multiple bot instances with load balancing
2. **Vertical**: Increase concurrent meeting limit
3. **Distributed**: Separate services (scheduler, joiner, transcription)
4. **Cloud**: Deploy on container platforms (Docker, Kubernetes)

## 📈 Monitoring & Observability

- **Logging**: Structured logging with multiple loggers
- **Health Endpoints**: `/health` for uptime checks
- **Status Tracking**: Active sessions dictionary
- **Event Listeners**: APScheduler job events
- **Error Handling**: Comprehensive try-catch with logging

## 🔮 Future Enhancements

1. **Database**: PostgreSQL for meeting history
2. **Message Queue**: RabbitMQ/Redis for distributed scheduling
3. **WebSockets**: Real-time status updates
4. **Metrics**: Prometheus/Grafana integration
5. **AI Transcription**: Whisper API, Deepgram integration
6. **Multi-tenancy**: Support multiple users/teams
7. **Advanced Audio**: Virtual audio routing, recording
8. **Web Dashboard**: Full-featured React/Vue frontend

## 🛠️ Technology Stack Summary

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.8+ |
| Async Framework | asyncio |
| Web Framework | FastAPI |
| Web Server | Uvicorn |
| Scheduler | APScheduler |
| Browser Automation | Playwright |
| HTTP Client | httpx |
| Config Management | Pydantic Settings |
| Google APIs | google-api-python-client |
| Calendar Parsing | icalendar |
| Date/Time | python-dateutil, zoneinfo |
