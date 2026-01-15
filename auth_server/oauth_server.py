"""
OAuth authentication server for user-initiated authentication.
Provides web endpoints for users to authenticate with their email providers.
"""

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from msal import ConfidentialClientApplication
from datetime import timedelta

from config import settings, get_logger

logger = get_logger("auth_server")

# Pydantic models for request bodies
class ManualJoinRequest(BaseModel):
    bot_name: str
    meeting_url: str

class AuthServer:
    """
    Web server for OAuth authentication flows using FastAPI.
    Provides endpoints for users to authenticate without automatic redirects.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8888, meeting_bot = None):
        """
        Initialize the auth server.
        
        Args:
            host: Host to bind the server to.
            port: Port to bind the server to.
            meeting_bot: Reference to main MeetingBot for manual joins.
        """
        self.host = host
        self.port = port
        self.meeting_bot = meeting_bot
        
        # Store pending OAuth flows
        self._flows: Dict[str, Flow] = {}
        self._credentials: Dict[str, Any] = {}
        self._msal_app: Optional[ConfidentialClientApplication] = None
        
        # Initialize FastAPI app
        self.app = FastAPI(
            title="Meeting Bot Authentication Server",
            description="API for Meeting Bot authentication and manual control",
            version="1.0.0"
        )
        
        self.server = None
        self._server_task = None
        
        # Setup middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """Setup web routes."""
        
        @self.app.get("/", response_class=HTMLResponse, tags=["UI"])
        async def index():
            return self._index_handler()
            
        @self.app.get("/auth/gmail/start", tags=["Authentication"])
        async def gmail_auth_start():
            return await self._gmail_auth_start()
            
        @self.app.get("/auth/gmail/callback", response_class=HTMLResponse, tags=["Authentication"])
        async def gmail_auth_callback(request: Request):
            return await self._gmail_auth_callback(request)
            
        @self.app.get("/auth/outlook/start", tags=["Authentication"])
        async def outlook_auth_start():
            return await self._outlook_auth_start()
            
        @self.app.get("/auth/outlook/callback", response_class=HTMLResponse, tags=["Authentication"])
        async def outlook_auth_callback(request: Request):
            return await self._outlook_auth_callback(request)
            
        @self.app.get("/auth/status", tags=["Status"])
        async def auth_status():
            return await self._auth_status()
            
        @self.app.get("/health", tags=["Status"])
        async def health_check():
            return await self._health_check()
            
        @self.app.get("/join", response_class=HTMLResponse, tags=["Manual Join"])
        async def manual_join_page():
            return self._manual_join_page()
            
        @self.app.post("/join", tags=["Manual Join"])
        async def manual_join(request: ManualJoinRequest):
            return await self._manual_join_handler(request)

    async def start(self) -> None:
        """Start the authentication server."""
        if self.server:
            logger.warning("Auth server is already running")
            return
            
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False
        )
        self.server = uvicorn.Server(config)
        
        # Run in background task
        self._server_task = asyncio.create_task(self.server.serve())
        
        logger.info(f"Auth server started at http://{self.host}:{self.port}")
        logger.info(f"Swagger UI available at http://{self.host}:{self.port}/docs")
        logger.info(f"Gmail OAuth: http://{self.host}:{self.port}/auth/gmail/start")
    
    async def stop(self) -> None:
        """Stop the authentication server."""
        if self.server:
            self.server.should_exit = True
            if self._server_task:
                await self._server_task
            self.server = None
            self._server_task = None
        logger.info("Auth server stopped")
    
    def _index_handler(self) -> str:
        """Handle index page."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Meeting Bot - Authentication</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
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
                h1 {
                    color: #333;
                }
                .auth-option {
                    margin: 20px 0;
                    padding: 20px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }
                .auth-option h2 {
                    margin-top: 0;
                    color: #0066cc;
                }
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
                }
                button:hover, .button:hover {
                    background-color: #0052a3;
                }
                input[type="text"], input[type="password"] {
                    width: 100%;
                    padding: 10px;
                    margin: 8px 0;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    box-sizing: border-box;
                }
                .status {
                    margin-top: 20px;
                    padding: 10px;
                    border-radius: 4px;
                }
                .status.success {
                    background-color: #d4edda;
                    color: #155724;
                }
                .status.error {
                    background-color: #f8d7da;
                    color: #721c24;
                }
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
                <h1>🤖 Meeting Bot</h1>
                
                <div class="auth-option">
                    <h2>🚀 Quick Join Meeting</h2>
                    <p>Join any meeting instantly without authentication.</p>
                    <a href="/join" class="button">➡️ Join Meeting Now</a>
                </div>
                
                <div class="info">
                    <p><strong>Gmail Authentication:</strong></p>
                    <p>⚠️ Gmail API only supports OAuth2 authentication. Direct credentials (app passwords) are not supported.</p>
                    <p>Please use the OAuth method below to authenticate with your Gmail account.</p>
                </div>
                
                <div class="auth-option">
                    <h2>🔐 Gmail OAuth Authentication</h2>
                    <p>Securely authenticate using your Google account through OAuth2.</p>
                    <p>This is the only supported method for Gmail API access.</p>
                    <a href="/auth/gmail/start" class="button">🔐 Authenticate with Google</a>
                </div>
                
                <div class="auth-option">
                    <h2>� Outlook OAuth Authentication</h2>
                    <p>Securely authenticate using your Microsoft account through OAuth2.</p>
                    <p>Works with Outlook.com, Microsoft 365, and personal Microsoft accounts.</p>
                    <a href="/auth/outlook/start" class="button">🔐 Authenticate with Microsoft</a>
                </div>
                
                <div class="auth-option">
                    <h2>�📊 Authentication Status</h2>
                    <button onclick="checkStatus()">Check Status</button>
                    <div id="statusDisplay"></div>
                </div>
                
                <div class="auth-option">
                    <h2>📚 API Documentation</h2>
                    <p>View the interactive API documentation.</p>
                    <a href="/docs" class="button">📄 Swagger UI</a>
                </div>
            </div>
            
            <script>
                async function checkStatus() {
                    try {
                        const response = await fetch('/auth/status');
                        const result = await response.json();
                        
                        const statusDiv = document.getElementById('statusDisplay');
                        statusDiv.className = 'status success';
                        statusDiv.innerHTML = '<pre>' + JSON.stringify(result, null, 2) + '</pre>';
                    } catch (error) {
                        const statusDiv = document.getElementById('statusDisplay');
                        statusDiv.className = 'status error';
                        statusDiv.textContent = '❌ Error: ' + error.message;
                    }
                }
            </script>
        </body>
        </html>
        """
    
    async def _gmail_auth_start(self):
        """Start Gmail OAuth flow."""
        try:
            credentials_file = settings.gmail.credentials_file
            if not os.path.exists(credentials_file):
                raise HTTPException(status_code=400, detail='Gmail credentials file not found')
            
            # Create OAuth flow
            flow = Flow.from_client_secrets_file(
                credentials_file,
                scopes=settings.gmail.scopes,
                redirect_uri=f'http://{self.host}:{self.port}/auth/gmail/callback'
            )
            
            # Generate authorization URL
            auth_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            # Store flow for callback
            self._flows[state] = flow
            
            # Redirect to Google
            return RedirectResponse(auth_url)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error starting Gmail OAuth: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _gmail_auth_callback(self, request: Request) -> str:
        """Handle Gmail OAuth callback."""
        try:
            # Get state and code from query params
            state = request.query_params.get('state')
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
            
            if not state or state not in self._flows:
                raise HTTPException(status_code=400, detail='Invalid state')
            
            # Get the flow
            flow = self._flows[state]
            
            # Exchange code for credentials
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Save credentials to file
            token_file = settings.gmail.token_file
            Path(token_file).parent.mkdir(parents=True, exist_ok=True)
            
            # Write token to file
            with open(token_file, 'w') as token:
                token.write(credentials.to_json())
            
            logger.info(f"✅ Gmail OAuth tokens saved to: {token_file}")
            
            # Store in memory
            self._credentials['gmail'] = {
                'method': 'oauth',
                'token_file': token_file,
                'authenticated_at': datetime.now().isoformat(),
                'has_refresh_token': bool(credentials.refresh_token)
            }
            
            # Clean up flow
            del self._flows[state]
            
            logger.info("Gmail OAuth authentication successful - ready to use!")
            
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
                        <h1>✅ Authentication Successful!</h1>
                        <p>Your Gmail account has been successfully authenticated.</p>
                        <p><strong>Tokens have been saved!</strong></p>
                    </div>
                    <div class="info">
                        <h3>📝 Token Details:</h3>
                        <ul>
                            <li><strong>Access Token:</strong> Generated ✓</li>
                            <li><strong>Refresh Token:</strong> {'✓ Saved' if credentials.refresh_token else '✗ Missing'}</li>
                            <li><strong>Saved to:</strong> <code>{token_file}</code></li>
                        </ul>
                    </div>
                    <div class="info">
                        <h3>🚀 Next Steps:</h3>
                        <ol>
                            <li>Go back to your terminal</li>
                            <li>Press <code>Ctrl+C</code> to stop the bot</li>
                            <li>Restart with: <code>./venv/bin/python run.py</code></li>
                            <li>The bot will now use your saved OAuth tokens!</li>
                        </ol>
                    </div>
                    <a href="/">← Back to Authentication Page</a>
                </body>
            </html>
            """
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in Gmail OAuth callback: {e}")
            return f"""
            <html>
                <body>
                    <h1>❌ Authentication Error</h1>
                    <p>Error: {str(e)}</p>
                    <a href="/">Go back</a>
                </body>
            </html>
            """
    
    def _get_msal_app(self) -> ConfidentialClientApplication:
        """Get or create cached MSAL app for Outlook OAuth."""
        if self._msal_app is None:
            outlook_settings = settings.outlook
            authority = f"https://login.microsoftonline.com/{outlook_settings.tenant_id}"
            self._msal_app = ConfidentialClientApplication(
                client_id=outlook_settings.client_id,
                client_credential=outlook_settings.client_secret,
                authority=authority
            )
        return self._msal_app
    
    async def _outlook_auth_start(self):
        """Start Outlook OAuth flow."""
        try:
            outlook_settings = settings.outlook
            
            if not outlook_settings.client_id:
                raise HTTPException(
                    status_code=400, 
                    detail='Outlook client_id not configured. Set OUTLOOK_CLIENT_ID in .env'
                )
            
            # Use cached MSAL app
            app = self._get_msal_app()
            
            # Build auth URL - exclude reserved scopes, MSAL handles them automatically
            reserved_scopes = {"openid", "offline_access", "profile"}
            scopes = [
                f"https://graph.microsoft.com/{scope}"
                for scope in outlook_settings.scopes
                if scope not in reserved_scopes
            ]
            
            auth_url = app.get_authorization_request_url(
                scopes=scopes,
                redirect_uri=outlook_settings.redirect_uri
            )
            
            logger.info(f"Starting Outlook OAuth flow, redirect to: {outlook_settings.redirect_uri}")
            
            # Redirect to Microsoft
            return RedirectResponse(auth_url)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error starting Outlook OAuth: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _outlook_auth_callback(self, request: Request) -> str:
        """Handle Outlook OAuth callback."""
        try:
            code = request.query_params.get('code')
            error = request.query_params.get('error')
            
            if error:
                error_desc = request.query_params.get('error_description', error)
                logger.error(f"Outlook OAuth error: {error_desc}")
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
                            .error {{
                                background-color: #f8d7da;
                                color: #721c24;
                                padding: 20px;
                                border-radius: 8px;
                                margin: 20px 0;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="error">
                            <h1>❌ Authentication Failed</h1>
                            <p><strong>Error:</strong> {error}</p>
                            <p>{error_desc}</p>
                        </div>
                        <a href="/">← Go back</a>
                    </body>
                </html>
                """
            
            if not code:
                raise HTTPException(status_code=400, detail='No authorization code received')
            
            # Exchange code for token using cached MSAL app
            outlook_settings = settings.outlook
            app = self._get_msal_app()
            
            # Build scopes - exclude reserved scopes, MSAL handles them automatically
            reserved_scopes = {"openid", "offline_access", "profile"}
            scopes = [
                f"https://graph.microsoft.com/{scope}"
                for scope in outlook_settings.scopes
                if scope not in reserved_scopes
            ]
            
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
                            ul {{
                                text-align: left;
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
                    <head>
                        <style>
                            body {{
                                font-family: Arial, sans-serif;
                                max-width: 600px;
                                margin: 50px auto;
                                padding: 20px;
                                text-align: center;
                            }}
                            .error {{
                                background-color: #f8d7da;
                                color: #721c24;
                                padding: 20px;
                                border-radius: 8px;
                                margin: 20px 0;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="error">
                            <h1>❌ Token Acquisition Failed</h1>
                            <p><strong>Error:</strong> {result.get('error', 'Unknown')}</p>
                            <p>{error_desc}</p>
                        </div>
                        <a href="/">← Go back</a>
                    </body>
                </html>
                """
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in Outlook OAuth callback: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
                        .error {{
                            background-color: #f8d7da;
                            color: #721c24;
                            padding: 20px;
                            border-radius: 8px;
                            margin: 20px 0;
                        }}
                    </style>
                </head>
                <body>
                    <div class="error">
                        <h1>❌ Authentication Error</h1>
                        <p><strong>Error:</strong> {str(e)}</p>
                    </div>
                    <a href="/">← Go back</a>
                </body>
            </html>
            """
    
    def _manual_join_page(self) -> str:
        """Display manual meeting join page."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Join Meeting - Meeting Bot</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
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
                h1 {
                    color: #333;
                }
                .form-group {
                    margin: 20px 0;
                }
                label {
                    display: block;
                    margin-bottom: 8px;
                    color: #333;
                    font-weight: bold;
                }
                input[type="text"] {
                    width: 100%;
                    padding: 12px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    box-sizing: border-box;
                    font-size: 16px;
                }
                button {
                    background-color: #0066cc;
                    color: white;
                    padding: 14px 28px;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: bold;
                    width: 100%;
                    margin-top: 10px;
                }
                button:hover {
                    background-color: #0052a3;
                }
                button:disabled {
                    background-color: #ccc;
                    cursor: not-allowed;
                }
                .status {
                    margin-top: 20px;
                    padding: 15px;
                    border-radius: 4px;
                    display: none;
                }
                .status.success {
                    background-color: #d4edda;
                    color: #155724;
                    border: 1px solid #c3e6cb;
                    display: block;
                }
                .status.error {
                    background-color: #f8d7da;
                    color: #721c24;
                    border: 1px solid #f5c6cb;
                    display: block;
                }
                .info {
                    background-color: #d1ecf1;
                    padding: 15px;
                    border-radius: 4px;
                    margin: 20px 0;
                    border: 1px solid #bee5eb;
                }
                .back-link {
                    display: inline-block;
                    margin-bottom: 20px;
                    color: #0066cc;
                    text-decoration: none;
                }
                .back-link:hover {
                    text-decoration: underline;
                }
                .example {
                    color: #666;
                    font-size: 14px;
                    margin-top: 5px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <a href="/" class="back-link">← Back to Home</a>
                <h1>🚀 Join Meeting</h1>
                
                <div class="info">
                    <p><strong>Quick Join:</strong></p>
                    <p>Join any Google Meet, Zoom, or Teams meeting instantly without authentication.</p>
                    <p>The bot will join the meeting and start transcription automatically.</p>
                </div>
                
                <form id="joinForm">
                    <div class="form-group">
                        <label for="botName">Bot Name</label>
                        <input 
                            type="text" 
                            id="botName" 
                            name="botName" 
                            placeholder="Enter bot display name"
                            required
                        />
                        <div class="example">Example: Meeting Transcriber Bot</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="meetingUrl">Meeting URL</label>
                        <input 
                            type="text" 
                            id="meetingUrl" 
                            name="meetingUrl" 
                            placeholder="Enter meeting URL"
                            required
                        />
                        <div class="example">Example: https://meet.google.com/abc-defg-hij</div>
                    </div>
                    
                    <button type="submit" id="joinButton">Join Meeting</button>
                </form>
                
                <div id="statusDisplay" class="status"></div>
            </div>
            
            <script>
                document.getElementById('joinForm').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    
                    const botName = document.getElementById('botName').value;
                    const meetingUrl = document.getElementById('meetingUrl').value;
                    const joinButton = document.getElementById('joinButton');
                    const statusDisplay = document.getElementById('statusDisplay');
                    
                    // Disable button and show loading
                    joinButton.disabled = true;
                    joinButton.textContent = 'Joining...';
                    statusDisplay.className = 'status';
                    statusDisplay.style.display = 'none';
                    
                    try {
                        const response = await fetch('/join', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                bot_name: botName,
                                meeting_url: meetingUrl
                            })
                        });
                        
                        const result = await response.json();
                        
                        if (response.ok) {
                            statusDisplay.className = 'status success';
                            statusDisplay.innerHTML = `
                                <strong>✅ Success!</strong><br>
                                Bot is joining the meeting...<br><br>
                                <strong>Meeting ID:</strong> ${result.meeting_id}<br>
                                <strong>Session ID:</strong> ${result.session_id}<br>
                                <strong>Platform:</strong> ${result.platform}<br><br>
                                The bot will start transcription automatically.
                            `;
                            
                            // Reset form
                            document.getElementById('joinForm').reset();
                        } else {
                            statusDisplay.className = 'status error';
                            statusDisplay.innerHTML = `<strong>❌ Error:</strong> ${result.detail || 'Failed to join meeting'}`;
                        }
                    } catch (error) {
                        statusDisplay.className = 'status error';
                        statusDisplay.innerHTML = `<strong>❌ Error:</strong> ${error.message}`;
                    } finally {
                        joinButton.disabled = false;
                        joinButton.textContent = 'Join Meeting';
                    }
                });
            </script>
        </body>
        </html>
        """
    
    async def _manual_join_handler(self, request: ManualJoinRequest) -> Dict[str, Any]:
        """Handle manual meeting join request."""
        try:
            bot_name = request.bot_name.strip()
            meeting_url = request.meeting_url.strip()
            
            # Additional validation handled by Pydantic, but we check empty strings
            if not bot_name:
                raise HTTPException(status_code=400, detail='Bot name is required')
            
            if not meeting_url:
                raise HTTPException(status_code=400, detail='Meeting URL is required')
            
            # Validate URL format
            if not any(domain in meeting_url.lower() for domain in ['meet.google.com', 'zoom.us', 'teams.microsoft.com']):
                raise HTTPException(status_code=400, detail='Invalid meeting URL. Supported platforms: Google Meet, Zoom, Teams')
            
            # Check if meeting bot is available
            if not self.meeting_bot:
                raise HTTPException(status_code=503, detail='Meeting bot is not initialized')
            
            # Trigger manual join
            result = await self.meeting_bot.manual_join_meeting(bot_name, meeting_url)
            
            if result.get('success'):
                return {
                    'success': True,
                    'meeting_id': result['meeting_id'],
                    'session_id': result['session_id'],
                    'platform': result['platform'],
                    'message': 'Bot is joining the meeting'
                }
            else:
                raise HTTPException(status_code=400, detail=result.get('error', 'Failed to join meeting'))
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in manual join: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _auth_status(self) -> Dict[str, Any]:
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
        
        return status
    
    async def _health_check(self) -> Dict[str, Any]:
        """Health check endpoint."""
        return {
            'status': 'healthy',
            'server': 'auth_server',
            'timestamp': datetime.now().isoformat()
        }
    
    def get_auth_status(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Get authentication status for a provider.
        
        Args:
            provider: Provider name (gmail, outlook, etc.)
            
        Returns:
            Authentication status dict or None.
        """
        return self._credentials.get(provider)


# Global auth server instance
_auth_server: Optional[AuthServer] = None
_server_thread: Optional[threading.Thread] = None


async def start_auth_server(host: str = "localhost", port: int = 8888, meeting_bot = None) -> AuthServer:
    """
    Start the authentication server.
    
    Args:
        host: Host to bind to.
        port: Port to bind to.
        meeting_bot: Reference to MeetingBot for manual joins.
        
    Returns:
        AuthServer instance.
    """
    global _auth_server
    
    if _auth_server is None:
        _auth_server = AuthServer(host, port, meeting_bot)
        await _auth_server.start()
    else:
        # Update meeting_bot reference if server already exists
        _auth_server.meeting_bot = meeting_bot
    
    return _auth_server


async def stop_auth_server() -> None:
    """Stop the authentication server."""
    global _auth_server
    
    if _auth_server:
        await _auth_server.stop()
        _auth_server = None
