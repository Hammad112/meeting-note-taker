"""
OAuth authentication server for user-initiated authentication.
Provides web endpoints for users to authenticate with their email providers.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import threading

from aiohttp import web
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from config import settings, get_logger

logger = get_logger("auth_server")


class AuthServer:
    """
    Web server for OAuth authentication flows.
    Provides endpoints for users to authenticate without automatic redirects.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8888):
        """
        Initialize the auth server.
        
        Args:
            host: Host to bind the server to.
            port: Port to bind the server to.
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
        # Store pending OAuth flows
        self._flows: Dict[str, Flow] = {}
        self._credentials: Dict[str, Any] = {}
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """Setup web routes."""
        self.app.router.add_get('/', self._index_handler)
        self.app.router.add_get('/auth/gmail/start', self._gmail_auth_start)
        self.app.router.add_get('/auth/gmail/callback', self._gmail_auth_callback)
        # Credentials endpoint removed - Gmail API only supports OAuth
        self.app.router.add_get('/auth/status', self._auth_status)
        self.app.router.add_get('/health', self._health_check)
    
    async def start(self) -> None:
        """Start the authentication server."""
        if self.runner:
            logger.warning("Auth server is already running")
            return
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        
        logger.info(f"Auth server started at http://{self.host}:{self.port}")
        logger.info(f"Gmail OAuth: http://{self.host}:{self.port}/auth/gmail/start")
    
    async def stop(self) -> None:
        """Stop the authentication server."""
        if self.site:
            await self.site.stop()
            self.site = None
        
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        
        logger.info("Auth server stopped")
    
    async def _index_handler(self, request: web.Request) -> web.Response:
        """Handle index page."""
        html = """
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
                <h1>🤖 Meeting Bot - Authentication</h1>
                
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
                    <h2>📊 Authentication Status</h2>
                    <button onclick="checkStatus()">Check Status</button>
                    <div id="statusDisplay"></div>
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
        return web.Response(text=html, content_type='text/html')
    
    async def _gmail_auth_start(self, request: web.Request) -> web.Response:
        """Start Gmail OAuth flow."""
        try:
            credentials_file = settings.gmail.credentials_file
            if not os.path.exists(credentials_file):
                return web.json_response(
                    {'error': 'Gmail credentials file not found'},
                    status=400
                )
            
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
            return web.Response(status=302, headers={'Location': auth_url})
            
        except Exception as e:
            logger.error(f"Error starting Gmail OAuth: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def _gmail_auth_callback(self, request: web.Request) -> web.Response:
        """Handle Gmail OAuth callback."""
        try:
            # Get state and code from query params
            state = request.query.get('state')
            code = request.query.get('code')
            error = request.query.get('error')
            
            if error:
                html = f"""
                <html>
                    <body>
                        <h1>❌ Authentication Failed</h1>
                        <p>Error: {error}</p>
                        <a href="/">Go back</a>
                    </body>
                </html>
                """
                return web.Response(text=html, content_type='text/html')
            
            if not state or state not in self._flows:
                return web.json_response({'error': 'Invalid state'}, status=400)
            
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
            logger.info(f"   Access token: {credentials.token[:20]}...")
            logger.info(f"   Refresh token: {'Yes' if credentials.refresh_token else 'No'}")
            logger.info(f"   Expiry: {credentials.expiry}")
            
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
            
            html = f"""
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
            return web.Response(text=html, content_type='text/html')
            
        except Exception as e:
            logger.error(f"Error in Gmail OAuth callback: {e}")
            html = f"""
            <html>
                <body>
                    <h1>❌ Authentication Error</h1>
                    <p>Error: {str(e)}</p>
                    <a href="/">Go back</a>
                </body>
            </html>
            """
            return web.Response(text=html, content_type='text/html', status=500)
    
    async def _credentials_auth(self, request: web.Request) -> web.Response:
        """Handle direct credentials authentication."""
        try:
            data = await request.json()
            provider = data.get('provider')
            email = data.get('email')
            password = data.get('password')
            
            if not all([provider, email, password]):
                return web.json_response(
                    {'error': 'Missing required fields'},
                    status=400
                )
            
            # Save credentials securely
            credentials_dir = Path('credentials')
            credentials_dir.mkdir(exist_ok=True)
            
            credentials_file = credentials_dir / f'{provider}_direct_credentials.json'
            credentials_data = {
                'email': email,
                'password': password,
                'method': 'direct',
                'created_at': datetime.now().isoformat()
            }
            
            with open(credentials_file, 'w') as f:
                json.dump(credentials_data, f, indent=2)
            
            # Store in memory
            self._credentials[provider] = {
                'method': 'direct',
                'email': email,
                'credentials_file': str(credentials_file),
                'authenticated_at': datetime.now().isoformat()
            }
            
            logger.info(f"Direct credentials saved for {provider}: {email}")
            
            return web.json_response({
                'success': True,
                'message': f'Credentials saved for {provider}',
                'provider': provider,
                'email': email
            })
            
        except Exception as e:
            logger.error(f"Error saving credentials: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def _auth_status(self, request: web.Request) -> web.Response:
        """Get authentication status."""
        return web.json_response({
            'authenticated_providers': list(self._credentials.keys()),
            'credentials': self._credentials,
            'server_time': datetime.now().isoformat()
        })
    
    async def _health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            'status': 'healthy',
            'server': 'auth_server',
            'timestamp': datetime.now().isoformat()
        })
    
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
_event_loop: Optional[asyncio.AbstractEventLoop] = None


async def start_auth_server(host: str = "localhost", port: int = 8888) -> AuthServer:
    """
    Start the authentication server.
    
    Args:
        host: Host to bind to.
        port: Port to bind to.
        
    Returns:
        AuthServer instance.
    """
    global _auth_server
    
    if _auth_server is None:
        _auth_server = AuthServer(host, port)
        await _auth_server.start()
    
    return _auth_server


async def stop_auth_server() -> None:
    """Stop the authentication server."""
    global _auth_server
    
    if _auth_server:
        await _auth_server.stop()
        _auth_server = None
