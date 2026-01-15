# 🤖 Meeting Bot

A powerful, automated meeting assistant built with **FastAPI** and **Playwright**. The bot monitors your Gmail and Outlook calendars, joins Google Meet, Microsoft Teams, or Zoom meetings automatically, and handles transcription and meeting management.

## 🚀 Features

- **Dual Calendar Sync**: Automatically polls both Gmail and Outlook for upcoming meeting invites.
- **Auto-Join**: Uses Playwright to join meetings on time, handling lobby waits and admission.
- **Transcription**: Captures meeting audio and captions in real-time.
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
```

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
│   ├── meeting_joiner/ # Playwright automation logic
│   └── bot.py          # Core coordinator
├── credentials/        # Storage for OAuth tokens
├── transcripts/        # Generated meeting transcripts
├── main.py             # FastAPI entry point
└── requirements.txt    # Python dependencies
```

## 🛡️ License

[MIT License](LICENSE)
