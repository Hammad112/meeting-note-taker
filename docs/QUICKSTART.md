# Quick Start Guide - New Authentication System

## 🚀 Getting Started in 3 Minutes

### Method 1: OAuth (Recommended - Most Secure)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the bot:**
   ```bash
   python -m meeting_bot
   ```

3. **Authenticate:**
   - Open browser to: http://localhost:8888
   - Click "Authenticate with Google"
   - Grant permissions
   - Done! ✅

### Method 2: Direct Credentials (Quickest Setup)

1. **Get your Gmail App Password:**
   - Enable 2FA: https://myaccount.google.com/security
   - Create App Password: https://myaccount.google.com/apppasswords
   - Copy the 16-character password

2. **Create .env file:**
   ```bash
   cp .env.example .env
   ```

3. **Edit .env:**
   ```bash
   GMAIL_AUTH_METHOD=credentials
   GMAIL_EMAIL=your.email@gmail.com
   GMAIL_PASSWORD=abcd efgh ijkl mnop  # Your app password
   AUTH_SERVER_ENABLED=false  # Optional: disable auth server
   ```

4. **Start the bot:**
   ```bash
   python -m meeting_bot
   ```

## 🎯 What Changed?

### Before (Old System)
```
Start bot → Automatic browser popup → Manual OAuth → Bot continues
```
**Problem:** No flexibility, forced immediate authentication

### After (New System)
```
Start bot → Choose your method:
  1. Visit web UI (http://localhost:8888) for OAuth
  2. Use pre-configured credentials (email + app password)
  3. Use environment variables
```
**Benefit:** Flexible, production-ready, no forced browser popups

## 🔐 Authentication Methods Comparison

| Method | Security | Setup Effort | Production Ready | Automation Friendly |
|--------|----------|--------------|------------------|---------------------|
| **OAuth (Web UI)** | ⭐⭐⭐⭐⭐ | Easy | ✅ Yes | ⚠️ Requires initial manual step |
| **Direct Credentials** | ⭐⭐⭐⭐ | Very Easy | ✅ Yes | ✅ Fully automated |
| **Auto Mode** | ⭐⭐⭐⭐⭐ | Easy | ✅ Yes | ✅ Smart fallback |

## 📝 Configuration Examples

### Example 1: Local Development
```bash
# .env
GMAIL_AUTH_METHOD=auto
AUTH_SERVER_ENABLED=true
AUTH_SERVER_PORT=8888
```

**First run:** Visit http://localhost:8888 to authenticate
**Subsequent runs:** Uses saved token automatically

### Example 2: Docker/Production
```bash
# .env
GMAIL_AUTH_METHOD=credentials
GMAIL_EMAIL=bot@company.com
GMAIL_PASSWORD=${SECRET_APP_PASSWORD}  # From secrets manager
AUTH_SERVER_ENABLED=false
```

### Example 3: CI/CD Pipeline
```bash
# Authenticate once locally
GMAIL_AUTH_METHOD=oauth
AUTH_SERVER_ENABLED=true

# Then deploy with token file
GMAIL_AUTH_METHOD=oauth
GMAIL_TOKEN_FILE=/secure/path/gmail_token.json
AUTH_SERVER_ENABLED=false
```

## 🌐 Auth Server Features

When you visit http://localhost:8888:

```
┌─────────────────────────────────────┐
│  🤖 Meeting Bot - Authentication    │
├─────────────────────────────────────┤
│                                     │
│  Option 1: OAuth (Recommended)      │
│  [🔐 Authenticate with Google]     │
│                                     │
│  Option 2: Direct Credentials       │
│  Email: [________________]          │
│  Password: [________________]       │
│  [🔑 Authenticate]                 │
│                                     │
│  📊 Status: [Check Status]          │
└─────────────────────────────────────┘
```

## 🔍 Verify Your Setup

```bash
# Check if auth server is running
curl http://localhost:8888/health

# Check authentication status
curl http://localhost:8888/auth/status
```

Expected response:
```json
{
  "authenticated_providers": ["gmail"],
  "credentials": {
    "gmail": {
      "method": "oauth",
      "authenticated_at": "2026-01-14T10:30:00"
    }
  }
}
```

## 🐛 Troubleshooting

### "Failed to authenticate"
```bash
# Check your configuration
echo $GMAIL_AUTH_METHOD

# For OAuth: Make sure auth server is running
curl http://localhost:8888/health

# For credentials: Verify app password
# Must be 16 characters from https://myaccount.google.com/apppasswords
```

### "Port 8888 already in use"
```bash
# Change the port
export AUTH_SERVER_PORT=9999
# Or in .env: AUTH_SERVER_PORT=9999
```

### "No credentials found"
```bash
# Check what the bot is looking for:
# 1. credentials/gmail_direct_credentials.json
# 2. credentials/gmail_token.json
# 3. Environment variables GMAIL_EMAIL and GMAIL_PASSWORD

# Set one of these or use: http://localhost:8888
```

## 📚 Next Steps

1. ✅ Authenticate (you just did this!)
2. 📅 Bot will start monitoring your calendar
3. 🤖 Automatically joins meetings 1 minute before start
4. 📝 Captures transcripts (for Google Meet)
5. 💾 Saves to `transcripts/` folder

## 🆘 Need Help?

- **Documentation:** See [AUTHENTICATION.md](AUTHENTICATION.md) for detailed guide
- **Logs:** Check `logs/meeting_bot_YYYYMMDD.log`
- **Status:** Visit http://localhost:8888/auth/status
- **Health:** Visit http://localhost:8888/health

## ⚡ Pro Tips

1. **Use Auto Mode** - Let the bot figure out the best method
2. **Secure Your Credentials** - Add `credentials/` to `.gitignore`
3. **Rotate App Passwords** - Change them periodically for security
4. **Test Before Production** - Run locally first with OAuth
5. **Monitor Logs** - Check for authentication issues early
