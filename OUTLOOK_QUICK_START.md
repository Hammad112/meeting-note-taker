# Outlook OAuth Quick Start Guide

## 🎯 Goal
Add Microsoft Outlook/Microsoft 365 calendar integration to Meeting Bot using OAuth 2.0 authentication.

---

## 📋 Prerequisites
- ✅ Existing Gmail OAuth working
- ✅ FastAPI auth server running on port 8888
- ✅ Microsoft account with Azure access
- ✅ Basic understanding of OAuth 2.0

---

## 🚀 Quick Implementation Path

### Part 1: Azure Setup (30-45 min)

```
1. Azure Portal → Microsoft Entra ID → App Registrations → New
   ↓
2. Name: "Meeting Bot"
   Account types: "Any organizational directory and personal Microsoft accounts"
   ↓
3. Add Redirect URI: http://localhost:8888/auth/outlook/callback
   ↓
4. Create Client Secret (save immediately!)
   ↓
5. Add API Permissions:
   - User.Read
   - Calendars.Read
   - Mail.Read
   - offline_access
   ↓
6. Copy to .env:
   OUTLOOK_CLIENT_ID=<client-id>
   OUTLOOK_CLIENT_SECRET=<secret-value>
```

### Part 2: Code Updates (2-3 hours)

**File: auth_server/oauth_server.py**
```python
# Add new routes
@self.app.get("/auth/outlook/start")
async def outlook_auth_start():
    # Redirect to Microsoft OAuth
    
@self.app.get("/auth/outlook/callback")
async def outlook_auth_callback(request):
    # Handle Microsoft callback
    # Save tokens to credentials/outlook_token.json
```

**File: config/settings.py**
```python
# Add "offline_access" to outlook scopes
scopes: List[str] = Field(
    default=[
        "User.Read",
        "Calendars.Read",
        "Mail.Read",
        "offline_access"  # <-- Add this
    ]
)
```

**File: requirements.txt**
```bash
msal>=1.24.0  # Add this line
```

### Part 3: Test (30-45 min)

```bash
# 1. Install MSAL
pip install msal>=1.24.0

# 2. Start bot
python run.py

# 3. Open browser
http://localhost:8888

# 4. Click "Authenticate with Microsoft"

# 5. Grant permissions

# 6. Verify token saved
cat credentials/outlook_token.json

# 7. Check status
curl http://localhost:8888/auth/status | jq .outlook
```

---

## 📊 Implementation Checklist

### Azure AD Configuration
- [ ] Register app in Azure Portal
- [ ] Configure redirect URI: `http://localhost:8888/auth/outlook/callback`
- [ ] Create client secret and save value
- [ ] Add API permissions (4 scopes)
- [ ] Save client_id and client_secret to .env

### Code Implementation
- [ ] Add `/auth/outlook/start` endpoint
- [ ] Add `/auth/outlook/callback` endpoint
- [ ] Update dashboard UI with Outlook button
- [ ] Update auth status to include Outlook
- [ ] Add `offline_access` to outlook scopes
- [ ] Install `msal` library

### Testing & Validation
- [ ] OAuth flow works end-to-end
- [ ] Tokens saved to `credentials/outlook_token.json`
- [ ] Auth status shows Outlook authenticated
- [ ] Bot can fetch Outlook calendar events
- [ ] Token refresh works automatically

### Documentation
- [ ] Update README with Outlook auth steps
- [ ] Add Outlook endpoints to API_ENDPOINTS.md
- [ ] Update Postman collection

---

## 🔑 Key Files Modified

| File | Changes |
|------|---------|
| `config/settings.py` | Add `offline_access` to scopes |
| `auth_server/oauth_server.py` | Add 2 new endpoints + handlers |
| `requirements.txt` | Add `msal>=1.24.0` |
| `.env` | Add 3 new variables |

---

## 🎨 UI Preview

**Dashboard will have new section:**

```
┌─────────────────────────────────────────┐
│  🔐 Outlook OAuth Authentication        │
│                                         │
│  Securely authenticate using your       │
│  Microsoft account through OAuth2.      │
│                                         │
│  [🔐 Authenticate with Microsoft]       │
└─────────────────────────────────────────┘
```

---

## 🔄 OAuth Flow Diagram

```
User clicks button
     ↓
/auth/outlook/start
     ↓
Redirect to Microsoft Login
     ↓
User grants permissions
     ↓
Microsoft redirects to /auth/outlook/callback
     ↓
Exchange code for tokens
     ↓
Save to credentials/outlook_token.json
     ↓
Show success page
     ↓
Bot uses tokens automatically
```

---

## ⚡ Critical Configuration Values

```bash
# .env file
OUTLOOK_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
OUTLOOK_CLIENT_SECRET=ABC~123xyz...
OUTLOOK_TENANT_ID=common
OUTLOOK_REDIRECT_URI=http://localhost:8888/auth/outlook/callback
OUTLOOK_TOKEN_FILE=credentials/outlook_token.json
```

**Azure AD Configuration:**
- Redirect URI MUST exactly match: `http://localhost:8888/auth/outlook/callback`
- Platform: Web
- Scopes: User.Read, Calendars.Read, Mail.Read, offline_access

---

## 🐛 Troubleshooting

### Error: "Invalid redirect URI"
✅ **Fix**: Ensure Azure AD redirect URI exactly matches code
```
Azure: http://localhost:8888/auth/outlook/callback
Code: http://localhost:8888/auth/outlook/callback
```

### Error: "Missing refresh token"
✅ **Fix**: Add `offline_access` to scopes in settings.py

### Error: "Module 'msal' not found"
✅ **Fix**: Install MSAL library
```bash
pip install msal>=1.24.0
```

### Error: "AADSTS50011: Reply URL mismatch"
✅ **Fix**: Check redirect_uri parameter matches Azure AD config

### Error: "Client secret expired"
✅ **Fix**: Generate new secret in Azure Portal → Certificates & secrets

---

## 📚 Key Concepts

### OAuth 2.0 Authorization Code Flow
1. User clicks "Authenticate"
2. Redirect to Microsoft login
3. User grants permissions
4. Get authorization code
5. Exchange code for access token + refresh token
6. Use access token for API calls
7. Use refresh token when access token expires

### Microsoft Graph API
- **Base URL**: `https://graph.microsoft.com/v1.0`
- **Calendar Endpoint**: `/me/calendar/events`
- **Authentication**: Bearer token in Authorization header

### Token Storage
```json
{
  "access_token": "eyJ0...",
  "refresh_token": "AwAB...",
  "expires_at": "2026-01-15T12:00:00",
  "scopes": ["User.Read", "Calendars.Read", ...]
}
```

---

## 🎯 Success Criteria

✅ User can click "Authenticate with Microsoft"  
✅ OAuth flow completes without errors  
✅ Tokens saved to file system  
✅ Auth status shows Outlook authenticated  
✅ Bot can fetch calendar events  
✅ Token refresh works automatically  
✅ Multiple meetings detected and joined  

---

## 📞 Need Help?

**Full Implementation Plan**: See `OUTLOOK_OAUTH_IMPLEMENTATION_PLAN.md`

**Microsoft Docs**:
- [App Registration](https://learn.microsoft.com/en-us/graph/auth-register-app-v2)
- [OAuth Flow](https://learn.microsoft.com/en-us/graph/auth-v2-user)
- [Calendar API](https://learn.microsoft.com/en-us/graph/api/resources/calendar)

**Existing Implementation**: 
- Similar to Gmail OAuth (already working)
- Reference: `auth_server/oauth_server.py` → `_gmail_auth_start()`

---

## ⏱️ Time Estimate

- **Azure Setup**: 30-45 minutes
- **Code Implementation**: 2-3 hours
- **Testing**: 30-45 minutes
- **Documentation**: 30 minutes

**Total**: ~4-5 hours

---

**Ready to start? Open the full plan: `OUTLOOK_OAUTH_IMPLEMENTATION_PLAN.md`**
