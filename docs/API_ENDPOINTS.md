# Meeting Bot - API Endpoints & CURL Commands

## 🌐 Base URL

```
http://localhost:8888
```

## 📚 Interactive Documentation

### Swagger UI
```bash
# Open in browser
http://localhost:8888/docs
```

### ReDoc
```bash
# Open in browser
http://localhost:8888/redoc
```

---

## 🔍 API Endpoints

### 1. Dashboard / Homepage

**Endpoint**: `GET /`

**Description**: Web-based dashboard for authentication and manual meeting join.

**Response**: HTML page with:
- OAuth authentication links
- Manual join form
- Status check button
- API documentation links

**CURL Command**:
```bash
curl -X GET "http://localhost:8888/" \
  -H "Accept: text/html"
```

**Browser Access**:
```bash
# Open in browser
open http://localhost:8888/  # macOS
start http://localhost:8888/  # Windows
xdg-open http://localhost:8888/  # Linux
```

---

### 2. Health Check

**Endpoint**: `GET /health`

**Description**: Check if the server is running and responsive.

**Response**:
```json
{
  "status": "healthy",
  "service": "Meeting Bot Authentication Server",
  "version": "1.0.0",
  "timestamp": "2026-01-15T10:30:00Z"
}
```

**CURL Command**:
```bash
curl -X GET "http://localhost:8888/health" \
  -H "Accept: application/json"
```

**Response Codes**:
- `200 OK`: Server is healthy
- `5xx`: Server error

---

### 3. Authentication Status

**Endpoint**: `GET /auth/status`

**Description**: Check current authentication status for all configured email services.

**Response**:
```json
{
  "gmail": {
    "authenticated": true,
    "method": "oauth",
    "token_file": "credentials/gmail_token.json",
    "authenticated_at": "2026-01-15T10:00:00",
    "has_refresh_token": true
  },
  "outlook": {
    "authenticated": false,
    "method": null
  },
  "server_running": true,
  "timestamp": "2026-01-15T10:30:00Z"
}
```

**CURL Command**:
```bash
curl -X GET "http://localhost:8888/auth/status" \
  -H "Accept: application/json"
```

**Example with jq (pretty print)**:
```bash
curl -s "http://localhost:8888/auth/status" | jq .
```

**Response Codes**:
- `200 OK`: Status retrieved successfully
- `5xx`: Server error

---

### 4. Start Gmail OAuth Flow

**Endpoint**: `GET /auth/gmail/start`

**Description**: Initiates Gmail OAuth 2.0 authentication flow. Redirects to Google consent screen.

**Query Parameters**: None

**Response**: HTTP 302 redirect to Google OAuth URL

**CURL Command**:
```bash
# Follow redirects to see OAuth URL
curl -L -X GET "http://localhost:8888/auth/gmail/start"

# Just get the redirect location
curl -I "http://localhost:8888/auth/gmail/start"
```

**Browser Access** (Recommended):
```bash
# Open in browser for OAuth flow
open http://localhost:8888/auth/gmail/start  # macOS
start http://localhost:8888/auth/gmail/start  # Windows
```

**Flow**:
1. GET /auth/gmail/start
2. Redirect to Google OAuth consent screen
3. User grants permissions
4. Redirect to /auth/gmail/callback
5. Tokens saved to `credentials/gmail_token.json`

**Response Codes**:
- `302 Found`: Redirect to Google OAuth
- `400 Bad Request`: Credentials file not found
- `500 Internal Server Error`: OAuth flow error

---

### 5. Gmail OAuth Callback

**Endpoint**: `GET /auth/gmail/callback`

**Description**: OAuth callback endpoint. Google redirects here after user grants permissions.

**Query Parameters**:
- `state` (string, required): OAuth state parameter
- `code` (string, required): OAuth authorization code
- `error` (string, optional): Error if user denied access

**Response**: HTML page showing success or error

**CURL Command**:
```bash
# This endpoint is called by Google, not directly
# Example of what Google sends:
curl "http://localhost:8888/auth/gmail/callback?state=abc123&code=4/0AY0e-g7xyz..."
```

**Success Response**: HTML page with:
- ✅ Authentication successful message
- Token file location
- Next steps (restart bot)

**Error Response**: HTML page with error message

**Response Codes**:
- `200 OK`: Authentication successful (HTML)
- `400 Bad Request`: Invalid state or missing parameters
- `500 Internal Server Error`: Token exchange failed

---

### 6. Manual Join - Web Form

**Endpoint**: `GET /join`

**Description**: Display web form for manually joining a meeting.

**Response**: HTML form with:
- Bot name input field
- Meeting URL input field
- Join button

**CURL Command**:
```bash
curl -X GET "http://localhost:8888/join" \
  -H "Accept: text/html"
```

**Browser Access**:
```bash
open http://localhost:8888/join
```

---

### 7. Manual Join Meeting - API

**Endpoint**: `POST /join`

**Description**: Manually trigger the bot to join a specific meeting without email polling.

**Request Headers**:
```
Content-Type: application/json
```

**Request Body**:
```json
{
  "bot_name": "Meeting Transcriber",
  "meeting_url": "https://meet.google.com/abc-defg-hij"
}
```

**Response (Success)**:
```json
{
  "success": true,
  "message": "Successfully joined meeting",
  "meeting_id": "abc-defg-hij",
  "platform": "google_meet",
  "bot_name": "Meeting Transcriber"
}
```

**Response (Error)**:
```json
{
  "success": false,
  "error": "Invalid meeting URL",
  "details": "URL must be from Google Meet, Zoom, or Teams"
}
```

**CURL Commands**:

#### Google Meet
```bash
curl -X POST "http://localhost:8888/join" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "Transcriber Bot",
    "meeting_url": "https://meet.google.com/abc-defg-hij"
  }'
```

#### Zoom Meeting
```bash
curl -X POST "http://localhost:8888/join" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "Note Taker",
    "meeting_url": "https://zoom.us/j/1234567890?pwd=abc123"
  }'
```

#### Microsoft Teams
```bash
curl -X POST "http://localhost:8888/join" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "Meeting Recorder",
    "meeting_url": "https://teams.microsoft.com/l/meetup-join/..."
  }'
```

#### With Pretty Output (jq)
```bash
curl -s -X POST "http://localhost:8888/join" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "AI Assistant",
    "meeting_url": "https://meet.google.com/xyz-abcd-123"
  }' | jq .
```

**Response Codes**:
- `200 OK`: Meeting join initiated successfully
- `400 Bad Request`: Invalid request body or missing required fields
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Failed to join meeting

**Validation Rules**:
- `bot_name`: Required, string, 1-100 characters
- `meeting_url`: Required, valid URL, must be from supported platform

**Supported Platforms**:
- Google Meet: `meet.google.com/*`
- Zoom: `zoom.us/j/*` or `*.zoom.us/*`
- Microsoft Teams: `teams.microsoft.com/l/meetup-join/*`

---

## 🔧 Advanced CURL Examples

### 1. Check Authentication and Auto-Join

```bash
#!/bin/bash
# Script to check auth status and join a meeting

# Check authentication status
AUTH_STATUS=$(curl -s http://localhost:8888/auth/status | jq -r '.gmail.authenticated')

if [ "$AUTH_STATUS" = "true" ]; then
  echo "✅ Authenticated. Joining meeting..."
  
  # Join meeting
  curl -X POST "http://localhost:8888/join" \
    -H "Content-Type: application/json" \
    -d '{
      "bot_name": "Auto Bot",
      "meeting_url": "https://meet.google.com/abc-defg-hij"
    }'
else
  echo "❌ Not authenticated. Please authenticate first:"
  echo "http://localhost:8888/auth/gmail/start"
fi
```

### 2. Health Check with Retry

```bash
#!/bin/bash
# Wait for server to be healthy

MAX_RETRIES=10
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/health)
  
  if [ "$STATUS" = "200" ]; then
    echo "✅ Server is healthy"
    exit 0
  fi
  
  echo "⏳ Waiting for server... ($RETRY_COUNT/$MAX_RETRIES)"
  sleep 2
  RETRY_COUNT=$((RETRY_COUNT + 1))
done

echo "❌ Server failed to become healthy"
exit 1
```

### 3. Bulk Meeting Join (Multiple Meetings)

```bash
#!/bin/bash
# Join multiple meetings from a list

MEETINGS=(
  "https://meet.google.com/aaa-bbbb-ccc"
  "https://zoom.us/j/1234567890"
  "https://teams.microsoft.com/l/meetup-join/..."
)

for MEETING_URL in "${MEETINGS[@]}"; do
  echo "Joining: $MEETING_URL"
  
  curl -X POST "http://localhost:8888/join" \
    -H "Content-Type: application/json" \
    -d "{
      \"bot_name\": \"Multi Bot\",
      \"meeting_url\": \"$MEETING_URL\"
    }"
  
  echo ""
  sleep 2  # Wait between joins
done
```

### 4. Monitor Authentication Status

```bash
#!/bin/bash
# Monitor authentication status every 5 seconds

while true; do
  clear
  echo "=== Authentication Status ==="
  curl -s http://localhost:8888/auth/status | jq .
  echo ""
  echo "Press Ctrl+C to stop"
  sleep 5
done
```

### 5. Test All Endpoints

```bash
#!/bin/bash
# Test all API endpoints

echo "🧪 Testing Meeting Bot API"
echo ""

# Health Check
echo "1. Health Check:"
curl -s http://localhost:8888/health | jq .
echo ""

# Auth Status
echo "2. Auth Status:"
curl -s http://localhost:8888/auth/status | jq .
echo ""

# Manual Join (example)
echo "3. Manual Join (dry-run):"
echo "  POST /join with meeting URL"
echo ""

echo "✅ API tests complete"
```

---

## 📊 Response Format

All JSON responses follow this structure:

### Success Response
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { ... }
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "details": "Additional error information",
  "code": "ERROR_CODE"
}
```

---

## 🔐 Authentication

### API Key (Future Enhancement)

Currently, no API key is required for localhost. For production deployment:

```bash
curl -X POST "http://localhost:8888/join" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{ ... }'
```

---

## 🚦 Rate Limiting

Currently no rate limiting implemented. Recommended for production:
- 100 requests per minute per IP
- 10 manual joins per hour per IP

---

## 🐛 Error Codes

| HTTP Code | Description | Common Cause |
|-----------|-------------|--------------|
| 200 | OK | Request successful |
| 302 | Found | OAuth redirect |
| 400 | Bad Request | Invalid input data |
| 401 | Unauthorized | Invalid API key (future) |
| 404 | Not Found | Endpoint doesn't exist |
| 422 | Unprocessable Entity | Validation failed |
| 429 | Too Many Requests | Rate limit exceeded (future) |
| 500 | Internal Server Error | Server-side error |
| 503 | Service Unavailable | Server not ready |

---

## 🔄 Webhook Support (Future)

### Meeting Status Webhook

```bash
# Configure webhook URL (future feature)
curl -X POST "http://localhost:8888/settings/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-backend.com/webhook",
    "events": ["meeting_joined", "meeting_ended", "transcript_ready"]
  }'
```

**Webhook Payload Example**:
```json
{
  "event": "meeting_joined",
  "meeting_id": "abc-defg-hij",
  "platform": "google_meet",
  "timestamp": "2026-01-15T10:30:00Z",
  "bot_name": "Transcriber"
}
```
