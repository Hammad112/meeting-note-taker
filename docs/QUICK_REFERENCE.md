# Meeting Bot - Quick Reference Guide

## 🚀 Quick Start Commands

### Start the Bot
```bash
python run.py
```

### Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### Access Dashboard
```bash
# In browser
http://localhost:8888
```

---

## 📡 Essential API Calls

### Health Check
```bash
curl http://localhost:8888/health
```

### Check Auth Status
```bash
curl http://localhost:8888/auth/status | jq .
```

### Join a Meeting
```bash
curl -X POST http://localhost:8888/join \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Bot","meeting_url":"https://meet.google.com/abc-defg-hij"}'
```

---

## 🔑 OAuth Authentication

### Gmail OAuth Flow
1. Open: `http://localhost:8888/auth/gmail/start`
2. Grant permissions
3. Tokens saved automatically
4. Restart bot

---

## 📂 Important Files

| File | Purpose |
|------|---------|
| `credentials/gmail_token.json` | OAuth tokens |
| `transcripts/transcript_*.txt` | Meeting transcripts |
| `logs/` | Application logs |
| `.playwright_user_data/` | Browser profile |

---

## 🛠️ Configuration

### Environment Variables
```bash
# Gmail Settings
GMAIL_AUTH_METHOD=oauth
GMAIL_CREDENTIALS_FILE=credentials/gmail_credentials.json
GMAIL_TOKEN_FILE=credentials/gmail_token.json

# Scheduler Settings
SCHEDULER_EMAIL_POLL_INTERVAL_SECONDS=40
SCHEDULER_JOIN_BEFORE_START_MINUTES=1
SCHEDULER_LOOKAHEAD_HOURS=24

# Auth Server Settings
AUTH_SERVER_ENABLED=true
AUTH_SERVER_HOST=localhost
AUTH_SERVER_PORT=8888

# Backend API Settings
BACKEND_URL=http://localhost:8000
BACKEND_API_KEY=your-api-key
```

---

## 🎯 Common Use Cases

### Test API Health
```bash
curl http://localhost:8888/health
```

### Authenticate with Gmail
```bash
# Open in browser
open http://localhost:8888/auth/gmail/start
```

### Join Google Meet
```bash
curl -X POST http://localhost:8888/join \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Transcriber","meeting_url":"https://meet.google.com/xxx-yyyy-zzz"}'
```

### Join Zoom Meeting
```bash
curl -X POST http://localhost:8888/join \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Recorder","meeting_url":"https://zoom.us/j/1234567890"}'
```

### Join Microsoft Teams
```bash
curl -X POST http://localhost:8888/join \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Notes","meeting_url":"https://teams.microsoft.com/l/meetup-join/..."}'
```

---

## 🐛 Troubleshooting

### Bot Won't Start
```bash
# Check Python version
python --version  # Should be 3.8+

# Check dependencies
pip list

# Reinstall Playwright browsers
playwright install chromium
```

### Authentication Fails
```bash
# Remove old tokens
rm credentials/gmail_token.json

# Re-authenticate
# Open: http://localhost:8888/auth/gmail/start
```

### Meeting Won't Join
```bash
# Check browser automation
ps aux | grep chromium

# Check logs
tail -f logs/meeting_joiner.log
```

---

## 📊 System Status

### Check Running Processes
```bash
# Check if server is running
lsof -i :8888

# Check Python processes
ps aux | grep python
```

### View Logs
```bash
# All logs
tail -f logs/*.log

# Main application
tail -f logs/main.log

# Meeting joiner
tail -f logs/meeting_joiner.log

# Scheduler
tail -f logs/scheduler.log
```

---

## 🔒 Security Notes

- OAuth tokens stored in `credentials/`
- Never commit tokens to git
- Use `.gitignore` for sensitive files
- API key required for backend communication

---

## 🌐 Supported Platforms

| Platform | URL Pattern | Status |
|----------|-------------|--------|
| Google Meet | `meet.google.com/*` | ✅ Supported |
| Zoom | `zoom.us/j/*` | ✅ Supported |
| Microsoft Teams | `teams.microsoft.com/l/meetup-join/*` | ✅ Supported |

---

## 📈 Performance Tips

- Max 5 concurrent meetings (configurable)
- Email polls every 40 seconds (configurable)
- Joins 1 minute before start (configurable)
- Auto-rejoin on kick (3 attempts max)

---

## 🔗 Quick Links

- Dashboard: http://localhost:8888
- Swagger Docs: http://localhost:8888/docs
- ReDoc: http://localhost:8888/redoc
- OAuth Start: http://localhost:8888/auth/gmail/start
- Manual Join: http://localhost:8888/join

---

## 📦 Postman Import

1. Open Postman
2. Import > File
3. Select `postman_collection.json`
4. Set variable `baseUrl` to `http://localhost:8888`
5. Test endpoints

---

## 🎓 Documentation

- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [TECHNOLOGIES.md](TECHNOLOGIES.md) - Tech stack
- [API_ENDPOINTS.md](API_ENDPOINTS.md) - API reference
- [QUICKSTART.md](QUICKSTART.md) - Setup guide

---

## 💡 Pro Tips

### Auto-restart on Code Changes
```bash
# Install watchdog
pip install watchdog

# Use with auto-restart (if configured)
watchmedo auto-restart python run.py
```

### Background Mode
```bash
# Run in background
nohup python run.py > output.log 2>&1 &

# Check process
ps aux | grep run.py

# Stop
pkill -f run.py
```

### Docker (Future)
```bash
# Build image
docker build -t meeting-bot .

# Run container
docker run -d -p 8888:8888 \
  -v $(pwd)/credentials:/app/credentials \
  -v $(pwd)/transcripts:/app/transcripts \
  meeting-bot
```

---

## 🎯 Testing Checklist

- [ ] Health check responds
- [ ] Auth status endpoint works
- [ ] Gmail OAuth flow completes
- [ ] Manual join works for Google Meet
- [ ] Manual join works for Zoom
- [ ] Manual join works for Teams
- [ ] Transcripts are saved
- [ ] Browser opens meetings
- [ ] Email polling runs

---

## 📞 Emergency Commands

### Kill All Processes
```bash
# Kill server
lsof -ti:8888 | xargs kill -9

# Kill Python processes
pkill -f python

# Kill Chromium
pkill -f chromium
```

### Clean Reset
```bash
# Remove tokens
rm -rf credentials/*.json

# Remove browser data
rm -rf .playwright_user_data/

# Remove logs
rm -rf logs/*

# Remove transcripts
rm -rf transcripts/*
```

### Fresh Start
```bash
# Clean reset (above)
# Then reinstall
pip install -r requirements.txt
playwright install chromium

# Start fresh
python run.py
```

---

**Keep this handy! 📌**
