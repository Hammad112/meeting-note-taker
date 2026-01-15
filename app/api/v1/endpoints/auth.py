"""
OAuth authentication endpoints for Gmail and Outlook.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from msal import ConfidentialClientApplication

from app.core.config import settings
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger("api.auth")

# Store OAuth flows (in production, use Redis or database)
_oauth_flows: Dict[str, Any] = {}


@router.get("/", response_class=HTMLResponse, tags=["UI"])
async def dashboard():
    """
    Main dashboard with authentication options.
    
    Returns:
        HTML dashboard page
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Meeting Bot API - Dashboard</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 900px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            h1 { color: #333; }
            .auth-option {
                margin: 20px 0;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            .auth-option h2 { margin-top: 0; color: #0066cc; }
            button, .button {
                background-color: #0066cc;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                font-size: 16px;
                margin-right: 10px;
            }
            button:hover, .button:hover { background-color: #0052a3; }
            .info {
                background-color: #d1ecf1;
                padding: 15px;
                border-radius: 4px;
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Meeting Bot API</h1>
            
            <div class="auth-option">
                <h2>🚀 Quick Join Meeting</h2>
                <p>Join any meeting instantly without authentication.</p>
                <a href="/api/v1/meetings/join" class="button">➡️ Join Meeting Now</a>
            </div>
            
            <div class="auth-option">
                <h2>🔐 Gmail OAuth Authentication</h2>
                <p>Authenticate using your Google account (OAuth2 only).</p>
                <a href="/api/v1/auth/gmail/start" class="button">🔐 Authenticate with Google</a>
            </div>
            
            <div class="auth-option">
                <h2>📊 System Status</h2>
                <button onclick="checkStatus()">Check Auth Status</button>
                <button onclick="checkMeetingStatus()">Meeting Status</button>
                <div id="statusDisplay"></div>
            </div>
            
            <div class="auth-option">
                <h2>📚 API Documentation</h2>
                <a href="/api/docs" class="button">📄 Swagger UI</a>
                <a href="/api/redoc" class="button">📘 ReDoc</a>
            </div>
        </div>
        
        <script>
            async function checkStatus() {
                try {
                    const response = await fetch('/api/v1/auth/status');
                    const result = await response.json();
                    document.getElementById('statusDisplay').innerHTML = 
                        '<pre>' + JSON.stringify(result, null, 2) + '</pre>';
                } catch (error) {
                    document.getElementById('statusDisplay').innerHTML = 
                        '<p style="color: red;">Error: ' + error.message + '</p>';
                }
            }
            
            async function checkMeetingStatus() {
                try {
                    const response = await fetch('/api/v1/status');
                    const result = await response.json();
                    document.getElementById('statusDisplay').innerHTML = 
                        '<pre>' + JSON.stringify(result, null, 2) + '</pre>';
                } catch (error) {
                    document.getElementById('statusDisplay').innerHTML = 
                        '<p style="color: red;">Error: ' + error.message + '</p>';
                }
            }
        </script>
    </body>
    </html>
    """


@router.get("/gmail/start", tags=["Authentication"])
async def start_gmail_oauth():
    """
    Start Gmail OAuth flow.
    
    Returns:
        Redirect to Google OAuth consent screen
    """
    try:
        credentials_file = settings.gmail.credentials_file
        if not os.path.exists(credentials_file):
            raise HTTPException(status_code=400, detail='Gmail credentials file not found')
        
        # Create OAuth flow
        flow = Flow.from_client_secrets_file(
            credentials_file,
            scopes=settings.gmail.scopes,
            redirect_uri=f'http://{settings.auth_server.host}:{settings.auth_server.port}/api/v1/auth/gmail/callback'
        )
        
        # Generate authorization URL
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        # Store flow for callback
        _oauth_flows[state] = flow
        
        logger.info(f"Starting Gmail OAuth flow with state: {state}")
        
        # Redirect to Google
        return RedirectResponse(auth_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting Gmail OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gmail/callback", response_class=HTMLResponse, tags=["Authentication"])
async def gmail_oauth_callback(request: Request):
    """
    Handle Gmail OAuth callback.
    
    Args:
        request: FastAPI request object with OAuth code and state
    
    Returns:
        HTML success/error page
    """
    try:
        # Get state and code from query params
        state = request.query_params.get('state')
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        
        if error:
            return f"""
            <html><body>
                <h1>❌ Authentication Failed</h1>
                <p>Error: {error}</p>
                <a href="/api/v1/auth">Go back</a>
            </body></html>
            """
        
        if not state or state not in _oauth_flows:
            raise HTTPException(status_code=400, detail='Invalid state')
        
        # Get the flow
        flow = _oauth_flows[state]
        
        # Exchange code for credentials
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Save credentials to file
        token_file = settings.gmail.token_file
        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        
        with open(token_file, 'w') as token:
            token.write(credentials.to_json())
        
        logger.info(f"✅ Gmail OAuth tokens saved to: {token_file}")
        
        # Clean up flow
        del _oauth_flows[state]
        
        return """
        <html>
        <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 50px auto;
                    padding: 20px;
                    text-align: center;
                }
                .success {
                    background-color: #d4edda;
                    color: #155724;
                    padding: 20px;
                    border-radius: 8px;
                }
            </style>
        </head>
        <body>
            <div class="success">
                <h1>✅ Authentication Successful!</h1>
                <p>Your Gmail account has been authenticated.</p>
                <p>The bot will now monitor your calendar for meeting invites.</p>
            </div>
            <p><a href="/api/v1/auth">← Back to Dashboard</a></p>
            <script>setTimeout(() => window.close(), 5000);</script>
        </body>
        </html>
        """
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gmail OAuth callback error: {e}")
        return f"""
        <html><body>
            <h1>❌ Error</h1>
            <p>{str(e)}</p>
            <a href="/api/v1/auth">Go back</a>
        </body></html>
        """


@router.get("/outlook/start", tags=["Authentication"])
async def start_outlook_oauth():
    """
    Start Outlook OAuth flow.
    
    Returns:
        Redirect to Microsoft OAuth consent screen
    """
    # Placeholder for Outlook OAuth
    raise HTTPException(status_code=501, detail="Outlook OAuth not yet implemented in new structure")


@router.get("/outlook/callback", response_class=HTMLResponse, tags=["Authentication"])
async def outlook_oauth_callback(request: Request):
    """
    Handle Outlook OAuth callback.
    
    Args:
        request: FastAPI request object with OAuth code and state
    
    Returns:
        HTML success/error page
    """
    # Placeholder for Outlook OAuth callback
    raise HTTPException(status_code=501, detail="Outlook OAuth not yet implemented in new structure")
