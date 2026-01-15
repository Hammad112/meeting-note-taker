# Meeting Bot

A Python-based meeting bot that automates joining meetings (Google Meet, Zoom, Teams), transcribing audio, and managing authentication via a local web server.

## 🚀 How to Run

### Prerequisities
- Python 3.8+
- Google Chrome (for Playwright)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd meeting_bot
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install chromium
   ```

### Running the Bot

1. **Start the application:**
   ```bash
   python -m run.py
   ```

2. **Authenticate (First Run):**
   - The bot will start a local web server at `http://localhost:8888`.
   - Open this URL in your browser.
   - Choose **Gmail OAuth Authentication** to sign in with your Google account.
   - Once authenticated, the bot will proceed to monitor your calendar and join meetings.

## 🔌 API Endpoints

The bot exposes a local API server (FastAPI) for control and status monitoring.

**Base URL:** `http://localhost:8888`

### Interactive Documentation
- **Swagger UI:** [http://localhost:8888/docs](http://localhost:8888/docs) - Explore and test API endpoints directly.
- **ReDoc:** [http://localhost:8888/redoc](http://localhost:8888/redoc) - Alternative API documentation.

### Core Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | **Dashboard**: View status and quick actions. |
| `POST` | `/join` | **Manual Join**: Trigger the bot to join a specific meeting URL. |
| `GET` | `/health` | **Health Check**: Verify if the server is running. |
| `GET` | `/auth/status` | **Auth Status**: Check current authentication state. |

### Example: Manually Join a Meeting

You can use the dashboard or send a curl request:

```bash
curl -X POST "http://localhost:8888/join" \
     -H "Content-Type: application/json" \
     -d '{"bot_name": "Transcriber", "meeting_url": "https://meet.google.com/abc-defg-hij"}'
```

## 📚 More Information

- **[QUICKSTART.md](QUICKSTART.md)**: Detailed setup and authentication guide.
