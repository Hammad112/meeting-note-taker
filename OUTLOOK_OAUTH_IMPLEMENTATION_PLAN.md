# Outlook OAuth Implementation Plan for Meeting Bot

## 📋 Executive Summary

This document provides a comprehensive plan to set up Microsoft Outlook credentials and implement OAuth 2.0 authentication for the Meeting Bot application. The plan includes Azure AD app registration, code implementation updates, and integration with the existing FastAPI auth server.

---

## 🎯 Objectives

1. **Set up Azure AD Application** - Register app in Microsoft Entra (formerly Azure AD)
2. **Implement OAuth 2.0 Flow** - Add Outlook OAuth endpoints to auth server
3. **Integrate with Existing System** - Seamlessly integrate with current Gmail OAuth implementation
4. **Enable Calendar Access** - Fetch Outlook calendar events via Microsoft Graph API
5. **Persistent Authentication** - Store and refresh OAuth tokens automatically

---

## 📚 Background Research

### Microsoft Graph API Overview
- **API Base URL**: `https://graph.microsoft.com/v1.0`
- **Authentication**: OAuth 2.0 Authorization Code Flow
- **Scopes Required**:
  - `User.Read` - Basic user profile
  - `Calendars.Read` - Read user calendars
  - `Mail.Read` - Read user emails (optional)
  - `offline_access` - Get refresh token for long-lived access

### OAuth 2.0 Flow Steps
1. **Authorization Request** - Redirect user to Microsoft login
2. **User Consent** - User grants permissions
3. **Authorization Code** - Microsoft redirects back with code
4. **Token Exchange** - Exchange code for access/refresh tokens
5. **API Access** - Use access token to call Microsoft Graph
6. **Token Refresh** - Use refresh token when access token expires

### Existing Implementation Status
✅ **Already Implemented**:
- Outlook service class (`outlook.py`) with device code flow
- Configuration settings (`OutlookSettings`)
- Microsoft Graph API integration
- Token caching mechanism

❌ **Missing**:
- Web-based OAuth flow in auth server (like Gmail)
- Auth server endpoints for Outlook OAuth
- UI integration in dashboard
- Proper error handling for web flow

---

## 🔧 Part 1: Azure AD Application Setup

### Step 1.1: Create Azure AD Account (if needed)
**Prerequisites**: Microsoft account with Azure access

**Actions**:
1. Go to [Azure Portal](https://portal.azure.com/)
2. Sign in with Microsoft account
3. If no subscription, create free account
4. Navigate to Microsoft Entra ID (formerly Azure Active Directory)

**Time Estimate**: 15 minutes (if account creation needed)

---

### Step 1.2: Register Application in Azure AD

**Navigate to**:
1. Azure Portal → Microsoft Entra ID → App registrations → New registration

**Configuration**:
```
Name: Meeting Bot
Supported account types: 
  - Accounts in any organizational directory and personal Microsoft accounts
  
Redirect URI:
  - Platform: Web
  - URI: http://localhost:8888/auth/outlook/callback
```

**Save These Values**:
```
Application (client) ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Directory (tenant) ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Screenshots/Documentation**:
- Save Application (client) ID
- Save Directory (tenant) ID (or use "common" for multi-tenant)
- Take screenshot of overview page

**Time Estimate**: 10 minutes

---

### Step 1.3: Configure Platform Settings

**Navigate to**: App Registration → Authentication

**Actions**:
1. Click "Add a platform" → Web
2. Add Redirect URIs:
   - `http://localhost:8888/auth/outlook/callback` (primary)
   - `http://localhost:8400/callback` (legacy, optional)
3. Under "Implicit grant and hybrid flows":
   - ✅ Access tokens (optional)
   - ✅ ID tokens (optional)
4. Save changes

**Time Estimate**: 5 minutes

---

### Step 1.4: Create Client Secret

**Navigate to**: App Registration → Certificates & secrets

**Actions**:
1. Click "New client secret"
2. Description: `Meeting Bot Client Secret`
3. Expires: 24 months (maximum recommended)
4. Click "Add"
5. **IMPORTANT**: Copy the "Value" immediately (it won't show again)

**Save Securely**:
```
Client Secret Value: ABC123xyz...
Client Secret ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

⚠️ **Security Note**: Store client secret securely. Never commit to git.

**Time Estimate**: 5 minutes

---

### Step 1.5: Configure API Permissions

**Navigate to**: App Registration → API permissions

**Actions**:
1. Click "Add a permission" → Microsoft Graph → Delegated permissions
2. Select permissions:
   - ✅ `User.Read` (Basic profile)
   - ✅ `Calendars.Read` (Read calendars)
   - ✅ `Mail.Read` (Read email) - optional
   - ✅ `offline_access` (Refresh tokens)
3. Click "Add permissions"
4. Optional: Click "Grant admin consent" (if you're admin)

**Final Permissions List**:
```
Microsoft Graph (4):
- User.Read (Delegated)
- Calendars.Read (Delegated)
- Mail.Read (Delegated)
- offline_access (Delegated)
```

**Time Estimate**: 5 minutes

---

### Step 1.6: Save Configuration to .env

**Create/Update `.env` file**:
```bash
# Outlook/Microsoft 365 Settings
OUTLOOK_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
OUTLOOK_CLIENT_SECRET=ABC123xyz...
OUTLOOK_TENANT_ID=common
OUTLOOK_REDIRECT_URI=http://localhost:8888/auth/outlook/callback
OUTLOOK_TOKEN_FILE=credentials/outlook_token.json
```

**Time Estimate**: 2 minutes

**Total Time for Part 1**: ~42 minutes

---

## 💻 Part 2: Code Implementation

### Step 2.1: Update Configuration Settings

**File**: `config/settings.py`

**Changes**:
```python
class OutlookSettings(BaseSettings):
    """Outlook/Microsoft Graph configuration."""
    model_config = SettingsConfigDict(env_prefix="OUTLOOK_")
    
    client_id: str = Field(
        default="",
        description="Azure AD Application (client) ID"
    )
    client_secret: str = Field(
        default="",
        description="Azure AD client secret"
    )
    tenant_id: str = Field(
        default="common",
        description="Azure AD tenant ID (use 'common' for multi-tenant)"
    )
    redirect_uri: str = Field(
        default="http://localhost:8888/auth/outlook/callback",  # UPDATED PORT
        description="OAuth2 redirect URI (must match Azure AD config)"
    )
    token_file: str = Field(
        default="credentials/outlook_token.json",
        description="Path to store Outlook OAuth2 token"
    )
    scopes: List[str] = Field(
        default=[
            "User.Read",
            "Calendars.Read",
            "Mail.Read",
            "offline_access"  # ADDED: Required for refresh tokens
        ],
        description="Microsoft Graph API scopes"
    )
```

**Status**: ✅ Mostly complete (add `offline_access` to defaults)

**Time Estimate**: 5 minutes

---

### Step 2.2: Add Outlook OAuth Endpoints to Auth Server

**File**: `auth_server/oauth_server.py`

**Implementation Steps**:

#### A. Import MSAL Library
```python
from msal import ConfidentialClientApplication
```

#### B. Add Outlook OAuth Start Endpoint
```python
@self.app.get("/auth/outlook/start", tags=["Authentication"])
async def outlook_auth_start():
    return await self._outlook_auth_start()
```

#### C. Add Outlook OAuth Callback Endpoint
```python
@self.app.get("/auth/outlook/callback", response_class=HTMLResponse, tags=["Authentication"])
async def outlook_auth_callback(request: Request):
    return await self._outlook_auth_callback(request)
```

#### D. Implement Start Handler
```python
async def _outlook_auth_start(self):
    """Start Outlook OAuth flow."""
    try:
        outlook_settings = settings.outlook
        
        if not outlook_settings.client_id:
            raise HTTPException(
                status_code=400, 
                detail='Outlook client_id not configured. Set OUTLOOK_CLIENT_ID in .env'
            )
        
        # Create MSAL app
        authority = f"https://login.microsoftonline.com/{outlook_settings.tenant_id}"
        app = ConfidentialClientApplication(
            client_id=outlook_settings.client_id,
            client_credential=outlook_settings.client_secret,
            authority=authority
        )
        
        # Build auth URL
        scopes = [f"https://graph.microsoft.com/{scope}" 
                  for scope in outlook_settings.scopes]
        
        auth_url = app.get_authorization_request_url(
            scopes=scopes,
            redirect_uri=outlook_settings.redirect_uri
        )
        
        # Store app instance for callback
        self._outlook_app = app
        
        # Redirect to Microsoft
        return RedirectResponse(auth_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting Outlook OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### E. Implement Callback Handler
```python
async def _outlook_auth_callback(self, request: Request) -> str:
    """Handle Outlook OAuth callback."""
    try:
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        
        if error:
            return f"""
            <html>
                <body>
                    <h1>❌ Authentication Failed</h1>
                    <p>Error: {error}</p>
                    <a href="/">Go back</a>
                </body>
            </html>
            """
        
        if not code:
            raise HTTPException(status_code=400, detail='No authorization code received')
        
        # Exchange code for token
        outlook_settings = settings.outlook
        authority = f"https://login.microsoftonline.com/{outlook_settings.tenant_id}"
        
        app = ConfidentialClientApplication(
            client_id=outlook_settings.client_id,
            client_credential=outlook_settings.client_secret,
            authority=authority
        )
        
        scopes = [f"https://graph.microsoft.com/{scope}" 
                  for scope in outlook_settings.scopes]
        
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=scopes,
            redirect_uri=outlook_settings.redirect_uri
        )
        
        if "access_token" in result:
            # Save tokens to file
            token_file = outlook_settings.token_file
            Path(token_file).parent.mkdir(parents=True, exist_ok=True)
            
            token_data = {
                "access_token": result["access_token"],
                "refresh_token": result.get("refresh_token"),
                "expires_at": (datetime.now() + timedelta(seconds=result.get("expires_in", 3600))).isoformat(),
                "id_token": result.get("id_token"),
                "scopes": result.get("scope", "").split()
            }
            
            with open(token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
            
            logger.info(f"✅ Outlook OAuth tokens saved to: {token_file}")
            
            # Store in memory
            self._credentials['outlook'] = {
                'method': 'oauth',
                'token_file': token_file,
                'authenticated_at': datetime.now().isoformat(),
                'has_refresh_token': bool(result.get("refresh_token"))
            }
            
            return f"""
            <html>
                <head>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            max-width: 600px;
                            margin: 50px auto;
                            padding: 20px;
                            text-align: center;
                        }}
                        .success {{
                            background-color: #d4edda;
                            color: #155724;
                            padding: 20px;
                            border-radius: 8px;
                            margin: 20px 0;
                        }}
                        .info {{
                            background-color: #d1ecf1;
                            color: #0c5460;
                            padding: 15px;
                            border-radius: 8px;
                            margin: 20px 0;
                            text-align: left;
                        }}
                        code {{
                            background-color: #f8f9fa;
                            padding: 2px 6px;
                            border-radius: 3px;
                            font-family: monospace;
                        }}
                    </style>
                </head>
                <body>
                    <div class="success">
                        <h1>✅ Outlook Authentication Successful!</h1>
                        <p>Your Microsoft account has been successfully authenticated.</p>
                        <p><strong>Tokens have been saved!</strong></p>
                    </div>
                    <div class="info">
                        <h3>📝 Token Details:</h3>
                        <ul>
                            <li><strong>Access Token:</strong> Generated ✓</li>
                            <li><strong>Refresh Token:</strong> {'✓ Saved' if result.get('refresh_token') else '✗ Missing'}</li>
                            <li><strong>Saved to:</strong> <code>{token_file}</code></li>
                        </ul>
                    </div>
                    <div class="info">
                        <h3>🚀 Next Steps:</h3>
                        <ol>
                            <li>Go back to your terminal</li>
                            <li>Press <code>Ctrl+C</code> to stop the bot</li>
                            <li>Restart with: <code>python run.py</code></li>
                            <li>The bot will now use your saved OAuth tokens!</li>
                        </ol>
                    </div>
                    <a href="/">← Back to Authentication Page</a>
                </body>
            </html>
            """
        else:
            error_desc = result.get('error_description', 'Unknown error')
            logger.error(f"Token acquisition failed: {error_desc}")
            return f"""
            <html>
                <body>
                    <h1>❌ Token Acquisition Failed</h1>
                    <p>Error: {error_desc}</p>
                    <a href="/">Go back</a>
                </body>
            </html>
            """
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Outlook OAuth callback: {e}")
        return f"""
        <html>
            <body>
                <h1>❌ Authentication Error</h1>
                <p>Error: {str(e)}</p>
                <a href="/">Go back</a>
            </body>
        </html>
        """
```

**Time Estimate**: 60 minutes

---

### Step 2.3: Update Dashboard UI

**File**: `auth_server/oauth_server.py`

**Update `_index_handler` method**:

Add Outlook section after Gmail section:
```python
<div class="auth-option">
    <h2>🔐 Outlook OAuth Authentication</h2>
    <p>Securely authenticate using your Microsoft account through OAuth2.</p>
    <p>Works with Outlook.com, Microsoft 365, and personal Microsoft accounts.</p>
    <a href="/auth/outlook/start" class="button">🔐 Authenticate with Microsoft</a>
</div>
```

**Time Estimate**: 10 minutes

---

### Step 2.4: Update Auth Status Endpoint

**File**: `auth_server/oauth_server.py`

**Update `_auth_status` method**:

Add Outlook status check:
```python
async def _auth_status(self):
    """Get authentication status."""
    status = {
        "gmail": self._credentials.get('gmail', {
            "authenticated": False,
            "method": None
        }),
        "outlook": self._credentials.get('outlook', {
            "authenticated": False,
            "method": None
        }),
        "server_running": True,
        "timestamp": datetime.now().isoformat()
    }
    
    # Check actual token files
    gmail_token = Path(settings.gmail.token_file)
    if gmail_token.exists() and 'gmail' not in self._credentials:
        status['gmail'] = {
            "authenticated": True,
            "method": "oauth",
            "token_file": str(gmail_token),
            "from_file": True
        }
    
    outlook_token = Path(settings.outlook.token_file)
    if outlook_token.exists() and 'outlook' not in self._credentials:
        status['outlook'] = {
            "authenticated": True,
            "method": "oauth",
            "token_file": str(outlook_token),
            "from_file": True
        }
    
    return JSONResponse(content=status)
```

**Time Estimate**: 15 minutes

---

### Step 2.5: Update Outlook Service to Support Web OAuth

**File**: `email_service/outlook.py`

**Update `authenticate` method**:

```python
async def authenticate(self) -> bool:
    """
    Authenticate with Microsoft Graph using OAuth2.
    
    Returns:
        True if authentication was successful.
    """
    try:
        # Try to load existing token
        if self._load_token_cache():
            if self._is_token_valid():
                logger.info("Using cached Outlook token")
                await self._init_http_client()
                return True
            else:
                # Try to refresh
                if await self.refresh_token():
                    return True
        
        # Check if token file exists (from web OAuth)
        if os.path.exists(self._settings.token_file):
            logger.info("Found Outlook token file from web OAuth")
            if self._load_token_cache():
                if self._is_token_valid():
                    await self._init_http_client()
                    return True
        
        # Need to do OAuth flow
        if not self._settings.client_id:
            logger.error(
                "Outlook client_id not configured. "
                "Please authenticate at: http://localhost:8888/auth/outlook/start"
            )
            return False
        
        # For CLI: Use device code flow
        # For web: User should use auth server
        logger.error("❌ No valid OAuth token found")
        logger.error(f"   Please authenticate at: http://localhost:{settings.auth_server.port}/auth/outlook/start")
        return False
        
    except Exception as e:
        logger.error(f"Outlook authentication failed: {e}")
        return False
```

**Time Estimate**: 20 minutes

---

### Step 2.6: Update Email Service Factory

**File**: `email_service/__init__.py`

**Update `create` method**:

```python
@staticmethod
def create(provider: EmailProvider) -> List[EmailServiceBase]:
    """
    Create email service instance(s) based on provider setting.
    
    Args:
        provider: Which email provider(s) to use.
        
    Returns:
        List of email service instances.
    """
    services = []
    
    # Use Calendar API endpoint (no OAuth needed)
    if provider == EmailProvider.CALENDAR_API:
        services.append(CalendarAPIService())
        logger.info("Calendar API service initialized")
        return services
    
    # Traditional OAuth-based providers
    if provider in (EmailProvider.GMAIL, EmailProvider.BOTH):
        services.append(GmailService())
        logger.info("Gmail service initialized")
    
    if provider in (EmailProvider.OUTLOOK, EmailProvider.BOTH):
        from .outlook import OutlookService  # Import here to avoid circular dependency
        services.append(OutlookService())
        logger.info("Outlook service initialized")
    
    return services
```

**Time Estimate**: 10 minutes

---

### Step 2.7: Update Requirements

**File**: `requirements.txt`

Add MSAL library (if not already present):
```
# Microsoft Authentication Library
msal>=1.24.0
```

**Install**:
```bash
pip install msal>=1.24.0
```

**Time Estimate**: 5 minutes

**Total Time for Part 2**: ~125 minutes (~2 hours)

---

## 🧪 Part 3: Testing & Validation

### Step 3.1: Unit Testing

**Create test file**: `test_outlook_oauth.py`

```python
import pytest
from auth_server.oauth_server import AuthServer

@pytest.mark.asyncio
async def test_outlook_auth_start():
    """Test Outlook OAuth start endpoint."""
    # Test implementation
    pass

@pytest.mark.asyncio
async def test_outlook_auth_callback():
    """Test Outlook OAuth callback."""
    # Test implementation
    pass
```

**Time Estimate**: 30 minutes

---

### Step 3.2: Integration Testing

**Manual Testing Steps**:

1. **Start the bot**:
   ```bash
   python run.py
   ```

2. **Open dashboard**:
   ```
   http://localhost:8888
   ```

3. **Click "Authenticate with Microsoft"**:
   - Should redirect to Microsoft login
   - Enter Microsoft account credentials
   - Grant requested permissions
   - Should redirect back to callback

4. **Verify token saved**:
   ```bash
   cat credentials/outlook_token.json
   # Should show access_token, refresh_token, etc.
   ```

5. **Check auth status**:
   ```bash
   curl http://localhost:8888/auth/status | jq .
   # Should show outlook.authenticated = true
   ```

6. **Test calendar fetch**:
   - Restart bot
   - Bot should automatically use saved token
   - Check logs for "Using cached Outlook token"
   - Verify meetings are detected

**Time Estimate**: 45 minutes

---

### Step 3.3: Error Handling Testing

**Test Scenarios**:

1. **Missing client ID**:
   - Remove `OUTLOOK_CLIENT_ID` from .env
   - Start bot
   - Expected: Error message with instructions

2. **Invalid client secret**:
   - Set wrong client secret
   - Try to authenticate
   - Expected: Clear error message

3. **Expired token**:
   - Manually expire token in JSON file
   - Restart bot
   - Expected: Automatic token refresh

4. **Revoked permissions**:
   - Revoke app permissions in Microsoft account settings
   - Try to use bot
   - Expected: Re-authentication prompt

**Time Estimate**: 30 minutes

**Total Time for Part 3**: ~105 minutes (~1.75 hours)

---

## 📖 Part 4: Documentation Updates

### Step 4.1: Update README.md

Add Outlook authentication section:
```markdown
### Authenticate with Outlook

1. Open: `http://localhost:8888/auth/outlook/start`
2. Sign in with your Microsoft account
3. Grant the requested permissions
4. Tokens will be saved automatically
```

**Time Estimate**: 10 minutes

---

### Step 4.2: Update QUICK_REFERENCE.md

Add Outlook commands:
```markdown
### Outlook OAuth Flow
1. Open: `http://localhost:8888/auth/outlook/start`
2. Grant permissions
3. Tokens saved automatically
4. Restart bot
```

**Time Estimate**: 10 minutes

---

### Step 4.3: Update API_ENDPOINTS.md

Add Outlook endpoints:
```markdown
### 8. Start Outlook OAuth Flow

**Endpoint**: `GET /auth/outlook/start`

**Description**: Initiates Outlook OAuth 2.0 authentication flow. Redirects to Microsoft consent screen.

**CURL Command**:
```bash
curl -L "http://localhost:8888/auth/outlook/start"
```

### 9. Outlook OAuth Callback

**Endpoint**: `GET /auth/outlook/callback`

**Description**: OAuth callback endpoint. Microsoft redirects here after user grants permissions.
```

**Time Estimate**: 20 minutes

---

### Step 4.4: Update Postman Collection

Add Outlook endpoints to `postman_collection.json`:
```json
{
  "name": "Start Outlook OAuth",
  "request": {
    "method": "GET",
    "url": "{{baseUrl}}/auth/outlook/start"
  }
}
```

**Time Estimate**: 15 minutes

---

### Step 4.5: Create Outlook Setup Guide

**Create**: `OUTLOOK_SETUP.md`

Detailed step-by-step guide with screenshots for Azure AD setup.

**Time Estimate**: 30 minutes

**Total Time for Part 4**: ~85 minutes (~1.5 hours)

---

## 🔐 Part 5: Security & Best Practices

### Step 5.1: Secure Credential Storage

**Actions**:
1. Ensure `.env` is in `.gitignore`
2. Add `credentials/` to `.gitignore`
3. Never log client secrets or access tokens
4. Use environment variables for sensitive data

**Update `.gitignore`**:
```
# Credentials
credentials/
.env
.env.local
*.json
!requirements.txt
!package.json
!postman_collection.json
```

**Time Estimate**: 10 minutes

---

### Step 5.2: Implement Token Encryption (Optional)

Consider encrypting stored tokens using `cryptography` library.

**Time Estimate**: 60 minutes (optional)

---

### Step 5.3: Add Rate Limiting

Implement rate limiting for OAuth endpoints to prevent abuse.

**Time Estimate**: 30 minutes (optional)

---

### Step 5.4: Setup Monitoring

Add logging for:
- OAuth flow starts
- Successful authentications
- Failed authentication attempts
- Token refresh events

**Time Estimate**: 20 minutes

**Total Time for Part 5**: ~40-120 minutes

---

## 📊 Implementation Timeline

### Phase 1: Setup (Day 1)
- ✅ Azure AD app registration (42 min)
- ✅ Configuration file updates (5 min)
- **Total**: ~45 minutes

### Phase 2: Core Implementation (Day 1-2)
- ✅ Auth server endpoints (60 min)
- ✅ Dashboard UI updates (10 min)
- ✅ Auth status endpoint (15 min)
- ✅ Outlook service updates (20 min)
- ✅ Email service factory (10 min)
- ✅ Dependencies (5 min)
- **Total**: ~2 hours

### Phase 3: Testing (Day 2)
- ✅ Unit tests (30 min)
- ✅ Integration tests (45 min)
- ✅ Error handling tests (30 min)
- **Total**: ~1.75 hours

### Phase 4: Documentation (Day 2-3)
- ✅ README updates (10 min)
- ✅ Quick reference (10 min)
- ✅ API docs (20 min)
- ✅ Postman collection (15 min)
- ✅ Setup guide (30 min)
- **Total**: ~1.5 hours

### Phase 5: Security (Day 3)
- ✅ Credential protection (10 min)
- ✅ Monitoring (20 min)
- **Total**: ~30 minutes

**Total Implementation Time**: ~6-7 hours

---

## ✅ Checklist

### Azure AD Setup
- [ ] Create/access Azure account
- [ ] Register application
- [ ] Configure platform settings
- [ ] Create client secret
- [ ] Configure API permissions
- [ ] Save configuration to .env

### Code Implementation
- [ ] Update settings.py (add offline_access)
- [ ] Add auth server endpoints
- [ ] Update dashboard UI
- [ ] Update auth status endpoint
- [ ] Update outlook.py service
- [ ] Update email service factory
- [ ] Install MSAL library

### Testing
- [ ] Test OAuth flow end-to-end
- [ ] Verify token storage
- [ ] Test token refresh
- [ ] Test calendar access
- [ ] Test error scenarios

### Documentation
- [ ] Update README.md
- [ ] Update QUICK_REFERENCE.md
- [ ] Update API_ENDPOINTS.md
- [ ] Update Postman collection
- [ ] Create OUTLOOK_SETUP.md

### Security
- [ ] Verify .gitignore
- [ ] Test credential protection
- [ ] Add monitoring/logging
- [ ] Review security best practices

---

## 🚨 Common Issues & Solutions

### Issue 1: "Invalid redirect URI"
**Solution**: Ensure redirect URI in Azure AD exactly matches the one in code
```
Azure AD: http://localhost:8888/auth/outlook/callback
Code: http://localhost:8888/auth/outlook/callback
```

### Issue 2: "AADSTS50011: Reply URL mismatch"
**Solution**: Check that redirect_uri parameter matches Azure AD configuration

### Issue 3: "AADSTS7000215: Invalid client secret"
**Solution**: Regenerate client secret and update .env file

### Issue 4: "Missing refresh token"
**Solution**: Ensure `offline_access` scope is requested

### Issue 5: "Token expired"
**Solution**: Implement proper token refresh logic (already in code)

---

## 📚 References

### Microsoft Documentation
- [Register an application](https://learn.microsoft.com/en-us/graph/auth-register-app-v2)
- [Get access on behalf of a user](https://learn.microsoft.com/en-us/graph/auth-v2-user)
- [Microsoft Graph API Reference](https://learn.microsoft.com/en-us/graph/api/overview)
- [Calendar API](https://learn.microsoft.com/en-us/graph/api/resources/calendar)

### Libraries
- [MSAL Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)
- [Microsoft Graph SDK](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview)

### Examples
- [Microsoft Graph Python Samples](https://github.com/microsoftgraph/msgraph-sdk-python)

---

## 🎓 Next Steps After Implementation

1. **Multi-Account Support**: Allow users to connect multiple Outlook accounts
2. **Automatic Sync**: Periodically sync calendar in background
3. **Webhook Integration**: Use Microsoft Graph webhooks for real-time updates
4. **Admin Consent**: Support organization-wide deployment
5. **Token Encryption**: Encrypt stored tokens for additional security

---

## 📞 Support Resources

- **Azure AD Issues**: [Microsoft Q&A](https://learn.microsoft.com/en-us/answers/topics/azure-active-directory.html)
- **Graph API Issues**: [Microsoft Graph Support](https://developer.microsoft.com/en-us/graph/support)
- **OAuth Issues**: [OAuth 2.0 Docs](https://oauth.net/2/)

---

**Document Version**: 1.0  
**Last Updated**: January 15, 2026  
**Estimated Total Implementation Time**: 6-7 hours
