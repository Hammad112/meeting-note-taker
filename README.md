# 🤖 Meeting Bot

A powerful, automated meeting assistant built with **FastAPI** and **Playwright**. The bot monitors your Gmail and Outlook calendars, joins Google Meet, Microsoft Teams, or Zoom meetings automatically, and handles transcription and meeting management.

## 🚀 Features

- **Dual Calendar Sync**: Automatically polls both Gmail and Outlook for upcoming meeting invites.
- **Auto-Join**: Uses Playwright to join meetings on time, handling lobby waits and admission.
- **Transcription**: Captures meeting audio and captions in real-time.
- **Meeting Data Export**: Automatically exports meeting metadata and transcripts to JSON after each meeting.
- **AWS S3 Integration**: Uploads meeting data to S3 for cloud storage and easy retrieval.
- **Meeting Database**: Maintains local JSON database mapping meeting URLs to S3 file paths.
- **Manual Join**: Trigger the bot to join any meeting URL via a simple API call.
- **Unified API**: Control everything through a clean FastAPI interface (Swagger UI included).
- **Stealth Mode**: Advanced browser fingerprinting to avoid bot detection.

## 🛠️ Prerequisites

- **Python 3.10+**
- **Playwright** (and browser binaries)
- **Google Cloud Console Project** (for Gmail API)
- **Azure AD App Registration** (for Outlook/Graph API)

## 📥 Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd meeting_bot
   ```

2. **Create a virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```

## ⚙️ Configuration

Create a `.env` file in the root directory based on the provided template:

```ini
# Email Providers
EMAIL_PROVIDER=both  # gmail, outlook, or both

# Outlook OAuth (Azure Portal)
OUTLOOK_CLIENT_ID=your_client_id
OUTLOOK_CLIENT_SECRET=your_client_secret
OUTLOOK_TENANT_ID=consumers
OUTLOOK_REDIRECT_URI=http://localhost:8888/auth/outlook/callback

# Scheduler Settings
SCHEDULER_EMAIL_POLL_INTERVAL_SECONDS=40
SCHEDULER_JOIN_BEFORE_START_MINUTES=1

# Backend Port
AUTH_SERVER_PORT=8888

# AWS S3 (Optional - for meeting data export)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_S3_BUCKET_NAME=your-bucket-name
AWS_REGION=us-east-1
```

**Note**: If AWS credentials are not configured, meeting data will be saved locally in `transcripts/json/` directory.

See [MEETING_EXPORT_FEATURE.md](MEETING_EXPORT_FEATURE.md) for detailed documentation on the meeting data export feature.

## 🏃 Usage

1. **Start the Bot**:
   ```bash
   python main.py
   ```

2. **Authenticate Services**:
   Open your browser and navigate to:
   - **Gmail**: `http://localhost:8888/auth/gmail/start`
   - **Outlook**: `http://localhost:8888/auth/outlook/start`

3. **Access the API Dashboard**:
   View and test all endpoints at:
   `http://localhost:8888/docs`

## 🔌 API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | GET | General health and status |
| `/api/status` | GET | Detailed bot and scheduler status |
| `/api/sessions` | GET | List currently active meeting sessions |
| `/api/join` | POST | Manually command the bot to join a URL |
| `/auth/status` | GET | Check which services are authenticated |

## 📁 Project Structure

```text
meeting_bot/
├── app/
│   ├── auth_server/    # OAuth logic and token management
│   ├── config/         # Settings and Logging
│   ├── email_service/  # Gmail & Outlook implementations
│   ├── meeting_handler/# Playwright automation logic
│   ├── scheduler/      # Meeting scheduling logic
│   ├── storage/        # S3 and database services
│   ├── transcription/  # Transcription service
│   └── bot.py          # Core coordinator
├── credentials/        # Storage for OAuth tokens
├── data/              # Meeting database
├── transcripts/       # Generated meeting transcripts
│   └── json/          # JSON exports (if S3 not configured)
├── main.py            # FastAPI entry point
└── requirements.txt   # Python dependencies
```

## 📊 Meeting Data Export

After each meeting ends, the system automatically:
1. **Creates JSON export** with metadata (meeting ID, URL, duration, participants, etc.) and full transcription
2. **Uploads to S3** (if configured) for cloud storage
3. **Updates local database** with meeting URL → S3 path mapping

Example JSON structure:
```json
{
  "metadata": {
    "meeting_id": "TestMeeting",
    "meeting_url": "https://meet.google.com/abc-defg-hij",
    "platform": "google_meet",
    "start_time": "2025-01-16T10:30:00",
    "end_time": "2025-01-16T11:15:00",
    "duration_seconds": 2700,
    "participant_names": ["Alice", "Bob", "Charlie"]
  },
  "transcription": [
    {"timestamp": "10:30:15", "speaker": "Alice", "text": "Hello everyone!"}
  ]
}
```

See [MEETING_EXPORT_FEATURE.md](MEETING_EXPORT_FEATURE.md) for complete documentation.

## 🛡️ License

[MIT License](LICENSE)
