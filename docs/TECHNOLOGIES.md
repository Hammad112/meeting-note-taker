# Meeting Bot - Technology Stack

## 📦 Core Dependencies

### Python Runtime
- **Python**: 3.8+ (Type hints, asyncio, zoneinfo support)
- **Async/Await**: Native async/await for concurrent operations

## 🌐 Web Framework & Server

### FastAPI
- **Version**: >=0.100.0
- **Usage**: REST API and OAuth server
- **Features**:
  - Automatic OpenAPI/Swagger documentation
  - Pydantic validation
  - Async request handling
  - CORS middleware support

### Uvicorn
- **Version**: >=0.20.0
- **Usage**: ASGI web server
- **Features**:
  - High-performance async server
  - HTTP/1.1 and WebSocket support
  - Graceful shutdown

## 📧 Email & Calendar APIs

### Google APIs
- **google-auth**: >=2.0.0 - Authentication foundation
- **google-auth-oauthlib**: >=1.0.0 - OAuth 2.0 flows
- **google-auth-httplib2**: >=0.2.0 - HTTP transport
- **google-api-python-client**: >=2.100.0 - Gmail & Calendar APIs

**Scopes Used**:
- `https://www.googleapis.com/auth/gmail.readonly` - Read emails
- `https://www.googleapis.com/auth/calendar.readonly` - Read calendar events

### Calendar Parsing
- **icalendar**: >=6.0.0 - Parse .ics files from email attachments
- **python-dateutil**: >=2.8.0 - Date/time parsing and manipulation

## 🌐 HTTP Client

### httpx
- **Version**: >=0.25.0
- **Usage**: Async HTTP client for backend API communication
- **Features**:
  - Async/await support
  - Connection pooling
  - Request/response interceptors
  - Timeout configuration

## ⏰ Task Scheduling

### APScheduler
- **Version**: >=3.10.0
- **Usage**: Meeting join/end scheduling, periodic email polling
- **Features**:
  - Async job execution
  - Multiple trigger types (date, interval)
  - Event listeners
  - Job persistence (memory store)

## 🌐 Browser Automation

### Playwright
- **Version**: >=1.40.0
- **Usage**: Automated meeting joining via real browser
- **Browser**: Chromium (headless or headed)
- **Features**:
  - Cross-platform support (Windows, macOS, Linux)
  - Persistent browser contexts (stay logged in)
  - Network interception
  - Screenshot/video capture
  - Auto-waiting for elements

**Installation**:
```bash
pip install playwright
playwright install chromium
```

## ⚙️ Configuration Management

### Pydantic
- **Version**: >=2.0.0
- **Usage**: Data validation and settings management
- **Features**:
  - Type validation
  - Data parsing
  - JSON schema generation

### Pydantic Settings
- **Version**: >=2.0.0
- **Usage**: Environment variable configuration
- **Features**:
  - Automatic .env file loading
  - Prefix-based environment variables
  - Type conversion

## 📝 Data Parsing & Validation

### Email Validator
- **Version**: >=2.0.0
- **Usage**: Validate email addresses
- **Features**:
  - RFC 5321/5322 compliance
  - DNS checking (optional)

## 🏗️ Architecture Patterns

### Asynchronous Programming
- **asyncio**: Event loop, coroutines, tasks
- **async/await**: Native Python async syntax
- **Concurrency**: Multiple meetings handled simultaneously

### Design Patterns
- **Factory Pattern**: EmailServiceFactory for service instantiation
- **Strategy Pattern**: Multiple email providers (Gmail, Calendar API)
- **Observer Pattern**: Scheduler callbacks for events
- **Singleton Pattern**: Configuration settings
- **Adapter Pattern**: Base EmailServiceBase interface

## 🗄️ Data Storage

### File System
- **JSON**: OAuth tokens, credentials
- **Text Files**: Meeting transcripts
- **Logs**: Application logs

### Future Considerations
- **SQLite**: Local database for meeting history
- **PostgreSQL**: Production database
- **Redis**: Caching and session storage

## 🔐 Authentication & Security

### OAuth 2.0
- **Flow**: Authorization Code Grant
- **Storage**: Local JSON token files
- **Refresh**: Automatic token refresh

### API Authentication
- **Method**: API Key (X-API-Key header)
- **Backend**: Custom API key validation

## 📊 Logging

### Python Logging
- **Configuration**: Custom logger setup in config/logger.py
- **Handlers**: Console and file handlers
- **Format**: Structured logging with timestamps
- **Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL

## 🎤 Audio & Transcription (Future)

### Planned Integrations
- **OpenAI Whisper**: Speech-to-text API
- **Deepgram**: Real-time transcription
- **Local Whisper**: Offline transcription model
- **PyAudio/sounddevice**: Audio capture

### Virtual Audio Routing
- **BlackHole** (macOS): Route system audio to bot
- **VB-Cable** (Windows): Virtual audio device
- **PulseAudio** (Linux): Audio routing

## 🐳 Deployment (Future)

### Docker
```dockerfile
# Example Dockerfile structure
FROM python:3.11-slim
RUN playwright install chromium
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /app
CMD ["python", "run.py"]
```

### Docker Compose
- **Services**: Meeting bot, backend API, database
- **Volumes**: Credentials, transcripts, browser data
- **Networks**: Internal service communication

## 🧪 Testing (Recommended)

### Testing Frameworks
- **pytest**: Unit and integration testing
- **pytest-asyncio**: Async test support
- **pytest-playwright**: Playwright fixtures
- **httpx.MockTransport**: HTTP mocking

## 📦 Package Management

### Requirements File
```
requirements.txt  # Production dependencies
```

### Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
.\venv\Scripts\activate   # Windows
```

## 🔄 Version Control

### Git
- **.gitignore**: Excludes credentials, tokens, logs, venv
- **Repository Structure**: Modular, feature-based organization

## 🌍 Time Zone Handling

### zoneinfo
- **Python 3.9+**: Built-in IANA timezone database
- **Usage**: Timezone-aware datetime objects
- **Default**: UTC for internal storage

## 📱 API Documentation

### OpenAPI/Swagger
- **Auto-generated**: FastAPI creates OpenAPI spec
- **UI**: Swagger UI at `/docs`
- **Alternative**: ReDoc at `/redoc`

## 🚀 Performance Optimization

### Async I/O
- Non-blocking operations
- Concurrent HTTP requests
- Parallel meeting monitoring

### Connection Pooling
- **httpx**: Reuses HTTP connections
- **Google API Client**: Persistent sessions

## 🔧 Development Tools

### Recommended
- **VS Code**: Python extension, Playwright extension
- **Postman**: API testing
- **Insomnia**: Alternative API client
- **Chrome DevTools**: Browser debugging

## 📚 Documentation Tools

### Code Documentation
- **Docstrings**: Google-style docstrings
- **Type Hints**: PEP 484 type annotations
- **Comments**: Inline explanations for complex logic

## 🎯 Key Technology Decisions

### Why FastAPI?
- Modern, async-first framework
- Automatic API documentation
- Pydantic integration
- Type safety

### Why Playwright?
- Modern browser automation
- Better than Selenium for complex SPAs
- Built-in waiting mechanisms
- Cross-platform support

### Why APScheduler?
- Native async support
- Flexible scheduling
- No external dependencies (Redis, etc.)
- Easy to integrate

### Why httpx?
- Modern async HTTP client
- Better API than aiohttp
- Similar to requests library
- Strong typing support

## 🔮 Future Technologies

### Potential Additions
- **WebSockets**: Real-time updates (socket.io, websockets)
- **Message Queue**: Celery, RabbitMQ, or Redis Queue
- **Database ORM**: SQLAlchemy, Tortoise ORM
- **Monitoring**: Prometheus, Grafana
- **Logging**: ELK Stack, Loki
- **Caching**: Redis, Memcached
- **AI/ML**: OpenAI APIs, Hugging Face Transformers

## 📈 System Requirements

### Minimum
- **CPU**: 2 cores
- **RAM**: 2GB
- **Disk**: 1GB free space
- **OS**: Windows 10+, macOS 10.14+, Ubuntu 18.04+

### Recommended
- **CPU**: 4+ cores
- **RAM**: 4GB+
- **Disk**: 5GB+ (for browser profiles)
- **Network**: Stable broadband connection

## 🔗 External Services

### Google Cloud Platform
- **Gmail API**: Email access
- **Google Calendar API**: Calendar events
- **OAuth 2.0**: Authentication

### Meeting Platforms
- **Google Meet**: Video conferencing
- **Microsoft Teams**: Enterprise meetings
- **Zoom**: Video meetings

### Backend API (Optional)
- **Custom Calendar API**: Aggregated calendar data
- **X-API-Key**: Authentication mechanism
