"""
Pure logic for OAuth authentication flows.
Contains no FastAPI dependencies.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import asyncio

from google_auth_oauthlib.flow import Flow
from msal import ConfidentialClientApplication

from app.config import settings, get_logger

logger = get_logger("auth_manager")

class AuthManager:
    """
    Manages OAuth authentication flows and credentials.
    Pure logic class used by main.py.
    """
    
    def __init__(self, meeting_bot=None):
        self.meeting_bot = meeting_bot
        self._flows: Dict[str, Flow] = {}
        self._credentials: Dict[str, Any] = {}
        self._msal_app: Optional[ConfidentialClientApplication] = None

    def get_gmail_auth_url(self, host: str):
        """Get the URL to start Gmail OAuth flow."""
        try:
            credentials_file = settings.gmail.credentials_file
            if not os.path.exists(credentials_file):
                return {"error": "Gmail credentials file not found", "status_code": 400}
            
            redirect_uri = f'http://{host}/auth/gmail/callback'
            
            flow = Flow.from_client_secrets_file(
                credentials_file,
                scopes=settings.gmail.scopes,
                redirect_uri=redirect_uri
            )
            
            auth_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            self._flows[state] = flow
            return {"auth_url": auth_url, "state": state}
        except Exception as e:
            logger.error(f"Error getting Gmail OAuth URL: {e}")
            return {"error": str(e), "status_code": 500}

    def complete_gmail_auth(self, state: str, code: str):
        """Complete Gmail OAuth flow."""
        try:
            if not state or state not in self._flows:
                return {"error": "Invalid state or flow expired", "status_code": 400}
            
            flow = self._flows[state]
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            token_file = settings.gmail.token_file
            Path(token_file).parent.mkdir(parents=True, exist_ok=True)
            with open(token_file, 'w') as token:
                token.write(credentials.to_json())
            
            self._credentials['gmail'] = {
                'status': 'authenticated',
                'authenticated_at': datetime.now().isoformat()
            }
            del self._flows[state]
            
            # Start services if bot is present
            if self.meeting_bot:
                asyncio.create_task(self.meeting_bot.start_services())
            
            return {
                "status": "success",
                "message": "Gmail authenticated successfully"
            }
        except Exception as e:
            logger.error(f"Error completing Gmail auth: {e}")
            return {"error": str(e), "status_code": 500}

    def _get_msal_app(self):
        """Helper to create MSAL application."""
        if self._msal_app is None:
            outlook_settings = settings.outlook
            authority = f"https://login.microsoftonline.com/{outlook_settings.tenant_id}"
            self._msal_app = ConfidentialClientApplication(
                client_id=outlook_settings.client_id,
                client_credential=outlook_settings.client_secret,
                authority=authority
            )
        return self._msal_app

    def get_outlook_auth_url(self):
        """Get the URL to start Outlook OAuth flow."""
        try:
            outlook_settings = settings.outlook
            if not outlook_settings.client_id:
                return {"error": "Outlook client_id not configured", "status_code": 400}
            
            app = self._get_msal_app()
            # Use short scope names for Graph API v2.0 as recommended.
            # Avoid reserved scopes like offline_access in the explicit list.
            reserved_scopes = {"openid", "offline_access", "profile", "email"}
            scopes = [s for s in outlook_settings.scopes if s not in reserved_scopes]
            
            # Ensure at least some default scopes if none provided
            if not scopes:
                scopes = ["User.Read", "Calendars.Read", "Mail.Read"]

            auth_url = app.get_authorization_request_url(
                scopes=scopes,
                redirect_uri=outlook_settings.redirect_uri
            )
            return {"auth_url": auth_url}
        except Exception as e:
            logger.error(f"Error getting Outlook OAuth URL: {e}")
            return {"error": str(e), "status_code": 500}

    def complete_outlook_auth(self, code: str):
        """Complete Outlook OAuth flow."""
        try:
            if not code:
                return {"error": "No code received from Microsoft", "status_code": 400}
            
            app = self._get_msal_app()
            outlook_settings = settings.outlook
            reserved_scopes = {"openid", "offline_access", "profile"}
            scopes = [f"https://graph.microsoft.com/{scope}" for scope in outlook_settings.scopes if scope not in reserved_scopes]
            
            result = app.acquire_token_by_authorization_code(
                code=code, 
                scopes=scopes, 
                redirect_uri=outlook_settings.redirect_uri
            )
            
            if "access_token" in result:
                token_file = outlook_settings.token_file
                token_data = {
                    "access_token": result["access_token"],
                    "refresh_token": result.get("refresh_token"),
                    "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=result.get("expires_in", 3600))).isoformat()
                }
                with open(token_file, 'w') as f:
                    json.dump(token_data, f, indent=2)
                
                self._credentials['outlook'] = {
                    'status': 'authenticated', 
                    'authenticated_at': datetime.now().isoformat()
                }
                
                # Start services if bot is present
                if self.meeting_bot:
                    asyncio.create_task(self.meeting_bot.start_services())
                return {
                    "status": "success",
                    "message": "Outlook authenticated successfully"
                }
            else:
                return {
                    "error": f"Microsoft error: {result.get('error_description', 'Unknown error')}",
                    "status_code": 400
                }
        except Exception as e:
            logger.error(f"Error completing Outlook auth: {e}")
            return {"error": str(e), "status_code": 500}

    def get_auth_status(self):
        """Get the current authentication status for all providers."""
        return {
            'gmail': self._credentials.get('gmail', {'status': 'not_authenticated'}),
            'outlook': self._credentials.get('outlook', {'status': 'not_authenticated'}),
            'timestamp': datetime.now().isoformat()
        }
