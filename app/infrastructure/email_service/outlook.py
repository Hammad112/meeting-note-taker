"""
Outlook/Microsoft 365 service for fetching calendar events.
Uses Microsoft Graph API.
"""

import os
import json
import hashlib
import asyncio
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from zoneinfo import ZoneInfo
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

import httpx
from msal import ConfidentialClientApplication, PublicClientApplication

from .base import EmailServiceBase
from .url_extractor import extract_meeting_url, clean_html
from app.domain.models.meeting import MeetingDetails, MeetingPlatform, MeetingSource
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("outlook")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to receive OAuth callback."""
    
    authorization_code = None
    
    def do_GET(self):
        """Handle GET request with authorization code."""
        query = parse_qs(urlparse(self.path).query)
        OAuthCallbackHandler.authorization_code = query.get('code', [None])[0]
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        response = """
        <html>
        <head><title>Authentication Successful</title></head>
        <body>
            <h1>Authentication Successful!</h1>
            <p>You can close this window and return to the application.</p>
            <script>setTimeout(function() { window.close(); }, 3000);</script>
        </body>
        </html>
        """
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


class OutlookService(EmailServiceBase):
    """
    Outlook/Microsoft 365 service implementation.
    Uses Microsoft Graph API for calendar access.
    """
    
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    AUTHORITY_BASE = "https://login.microsoftonline.com"
    
    def __init__(self):
        """Initialize the Outlook service."""
        self._settings = settings.outlook
        self._token_cache: Optional[Dict[str, Any]] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._auth_message_shown: bool = False  # Prevent auth message spam
        self._refresh_error_shown: bool = False  # Prevent refresh error spam
        
        # Ensure credentials directory exists
        Path(self._settings.token_file).parent.mkdir(parents=True, exist_ok=True)
    
    async def authenticate(self) -> bool:
        """
        Authenticate with Microsoft Graph using OAuth2.
        
        Returns:
            True if authentication was successful.
        """
        try:
            # Try to load existing token (checks web OAuth token file first)
            if self._load_token_cache():
                if self._is_token_valid():
                    logger.info("Using cached Outlook token from web OAuth")
                    await self._init_http_client()
                    return True
                else:
                    # Try to refresh
                    if await self.refresh_token():
                        logger.info("Refreshed Outlook token successfully")
                        return True
            
            # No valid token found
            if not self._settings.client_id:
                if not self._auth_message_shown:
                    logger.error(
                        "Outlook client_id not configured. "
                        "Please set OUTLOOK_CLIENT_ID in .env file."
                    )
                    self._auth_message_shown = True
                return False
            
            # Prompt user to authenticate via web interface (only once)
            if not self._auth_message_shown:
                print("\n" + "=" * 70)
                print("OUTLOOK AUTHENTICATION REQUIRED")
                print("=" * 70)
                print("Please authenticate via the web interface:")
                print("1. Open http://localhost:8888 in your browser")
                print("2. Click 'Authenticate with Microsoft'")
                print("3. Sign in with your Microsoft account")
                print("4. Return here after authentication is complete")
                print("=" * 70 + "\n")
                self._auth_message_shown = True
            return False
            
        except Exception as e:
            logger.error(f"Outlook authentication failed: {e}")
            return False
    
    async def _device_code_flow(self) -> bool:
        """
        Authenticate using device code flow (no secret required).
        
        Returns:
            True if successful.
        """
        try:
            authority = f"{self.AUTHORITY_BASE}/{self._settings.tenant_id}"
            
            app = PublicClientApplication(
                client_id=self._settings.client_id,
                authority=authority
            )
            
            # Build scopes correctly
            graph_scopes = ["Calendars.Read", "Mail.Read", "User.Read"]
            standalone_scopes = ["offline_access", "openid", "profile"]
            scopes = []
            for scope in self._settings.scopes:
                if scope in standalone_scopes:
                    scopes.append(scope)
                elif scope in graph_scopes or not scope.startswith("http"):
                    scopes.append(f"https://graph.microsoft.com/{scope}")
                else:
                    scopes.append(scope)
            
            # Initiate device code flow
            flow = app.initiate_device_flow(scopes=scopes)
            
            if "user_code" not in flow:
                logger.error(f"Failed to initiate device flow: {flow}")
                return False
            
            # Only show message once
            if not self._auth_message_shown:
                print("\n" + "=" * 60)
                print("OUTLOOK AUTHENTICATION REQUIRED")
                print("=" * 60)
                print(f"\n{flow['message']}\n")
                print("=" * 60 + "\n")
                self._auth_message_shown = True
            
            # Wait for user to complete authentication
            result = app.acquire_token_by_device_flow(flow)
            
            if "access_token" in result:
                self._access_token = result["access_token"]
                expires_in = result.get("expires_in", 3600)
                self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                # Save token cache
                self._token_cache = {
                    "access_token": self._access_token,
                    "refresh_token": result.get("refresh_token"),
                    "expires_at": self._token_expires_at.isoformat(),
                    "id_token": result.get("id_token"),
                }
                self._save_token_cache()
                
                return True
            else:
                logger.error(f"Failed to acquire token: {result.get('error_description', result)}")
                return False
                
        except Exception as e:
            logger.error(f"Device code flow failed: {e}")
            return False
    
    async def _authorization_code_flow(self) -> bool:
        """
        Authenticate using authorization code flow (requires client secret).
        
        Returns:
            True if successful.
        """
        try:
            authority = f"{self.AUTHORITY_BASE}/{self._settings.tenant_id}"
            
            if not self._settings.client_secret:
                logger.warning("No client secret configured, using device code flow instead")
                return await self._device_code_flow()
            
            app = ConfidentialClientApplication(
                client_id=self._settings.client_id,
                client_credential=self._settings.client_secret,
                authority=authority
            )
            
            # Build scopes correctly
            graph_scopes = ["Calendars.Read", "Mail.Read", "User.Read"]
            standalone_scopes = ["offline_access", "openid", "profile"]
            scopes = []
            for scope in self._settings.scopes:
                if scope in standalone_scopes:
                    scopes.append(scope)
                elif scope in graph_scopes or not scope.startswith("http"):
                    scopes.append(f"https://graph.microsoft.com/{scope}")
                else:
                    scopes.append(scope)
            
            # Build authorization URL
            auth_url = app.get_authorization_request_url(
                scopes=scopes,
                redirect_uri=self._settings.redirect_uri
            )
            
            # Start local server to receive callback
            parsed = urlparse(self._settings.redirect_uri)
            port = parsed.port or 8400
            
            server = HTTPServer(('localhost', port), OAuthCallbackHandler)
            server_thread = threading.Thread(target=server.handle_request)
            server_thread.start()
            
            # Open browser for authentication
            if not self._auth_message_shown:
                print("\n" + "=" * 60)
                print("OUTLOOK AUTHENTICATION REQUIRED")
                print("=" * 60)
                print("\nOpening browser for Microsoft login...")
                print("If browser doesn't open, visit:")
                print(f"\n{auth_url}\n")
                print("=" * 60 + "\n")
                self._auth_message_shown = True
            
            webbrowser.open(auth_url)
            
            # Wait for callback
            server_thread.join(timeout=120)
            server.server_close()
            
            if not OAuthCallbackHandler.authorization_code:
                logger.error("No authorization code received")
                return False
            
            # Exchange code for token
            result = app.acquire_token_by_authorization_code(
                code=OAuthCallbackHandler.authorization_code,
                scopes=scopes,
                redirect_uri=self._settings.redirect_uri
            )
            
            OAuthCallbackHandler.authorization_code = None  # Reset
            
            if "access_token" in result:
                self._access_token = result["access_token"]
                expires_in = result.get("expires_in", 3600)
                self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                self._token_cache = {
                    "access_token": self._access_token,
                    "refresh_token": result.get("refresh_token"),
                    "expires_at": self._token_expires_at.isoformat(),
                }
                self._save_token_cache()
                
                return True
            else:
                logger.error(f"Failed to acquire token: {result.get('error_description', result)}")
                return False
                
        except Exception as e:
            logger.error(f"Authorization code flow failed: {e}")
            return False
    
    async def refresh_token(self) -> bool:
        """
        Refresh the Outlook access token.
        
        Returns:
            True if refresh was successful.
        """
        if not self._token_cache or not self._token_cache.get("refresh_token"):
            logger.info("No refresh token available, need full authentication")
            return False
        
        try:
            authority = f"{self.AUTHORITY_BASE}/{self._settings.tenant_id}"
            
            if self._settings.client_secret:
                app = ConfidentialClientApplication(
                    client_id=self._settings.client_id,
                    client_credential=self._settings.client_secret,
                    authority=authority
                )
            else:
                app = PublicClientApplication(
                    client_id=self._settings.client_id,
                    authority=authority
                )
            
            # Build scopes - some need Graph prefix, some don't
            graph_scopes = ["Calendars.Read", "Mail.Read", "User.Read"]
            standalone_scopes = ["offline_access", "openid", "profile"]
            scopes = []
            for scope in self._settings.scopes:
                # Skip reserved scopes that should not be included in token requests
                if scope in standalone_scopes:
                    continue
                # Add Graph API prefix if needed
                elif scope in graph_scopes or (not scope.startswith("http") and scope not in standalone_scopes):
                    scopes.append(f"https://graph.microsoft.com/{scope}")
                else:
                    scopes.append(scope)
            
            # Try to acquire token silently using refresh token
            accounts = app.get_accounts()
            
            result = app.acquire_token_by_refresh_token(
                refresh_token=self._token_cache["refresh_token"],
                scopes=scopes
            )
            
            if "access_token" in result:
                self._access_token = result["access_token"]
                expires_in = result.get("expires_in", 3600)
                self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                self._token_cache.update({
                    "access_token": self._access_token,
                    "refresh_token": result.get("refresh_token", self._token_cache.get("refresh_token")),
                    "expires_at": self._token_expires_at.isoformat(),
                })
                self._save_token_cache()
                
                await self._init_http_client()
                logger.info("Outlook token refreshed successfully")
                return True
            else:
                if not self._refresh_error_shown:
                    logger.warning(f"Token refresh failed: {result.get('error_description', 'Unknown error')}")
                    self._refresh_error_shown = True
                return False
                
        except Exception as e:
            if not self._refresh_error_shown:
                logger.error(f"Failed to refresh Outlook token: {e}")
                self._refresh_error_shown = True
            return False
    
    def is_authenticated(self) -> bool:
        """Check if Outlook service is authenticated."""
        return self._access_token is not None and self._is_token_valid()
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._access_token or not self._token_expires_at:
            return False
        # Add 5 minute buffer
        return datetime.now() < (self._token_expires_at - timedelta(minutes=5))
    
    def _load_token_cache(self) -> bool:
        """Load token cache from file."""
        try:
            if os.path.exists(self._settings.token_file):
                with open(self._settings.token_file, 'r') as f:
                    self._token_cache = json.load(f)
                    self._access_token = self._token_cache.get("access_token")
                    expires_at = self._token_cache.get("expires_at")
                    if expires_at:
                        self._token_expires_at = datetime.fromisoformat(expires_at)
                    return True
        except Exception as e:
            logger.warning(f"Failed to load token cache: {e}")
        return False
    
    def _save_token_cache(self) -> None:
        """Save token cache to file."""
        try:
            with open(self._settings.token_file, 'w') as f:
                json.dump(self._token_cache, f, indent=2)
            logger.debug(f"Token cache saved to {self._settings.token_file}")
        except Exception as e:
            logger.warning(f"Failed to save token cache: {e}")
    
    async def _init_http_client(self) -> None:
        """Initialize HTTP client with authorization header."""
        if self._http_client:
            await self._http_client.aclose()
        
        self._http_client = httpx.AsyncClient(
            base_url=self.GRAPH_BASE_URL,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
    
    async def get_calendar_invites(
        self,
        lookahead_hours: int = 24
    ) -> List[MeetingDetails]:
        """
        Get calendar events from Outlook/Microsoft 365.
        
        Args:
            lookahead_hours: How many hours ahead to look for meetings.
            
        Returns:
            List of MeetingDetails objects.
        """
        if not self.is_authenticated():
            if not await self.authenticate():
                return []
        
        meetings = []
        
        try:
            now = datetime.now(ZoneInfo("UTC"))
            end_time = now + timedelta(hours=lookahead_hours)
            
            # Format times for Graph API
            start_str = now.strftime("%Y-%m-%dT%H:%M:%S.0000000")
            end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S.0000000")
            
            # Get calendar events
            response = await self._http_client.get(
                "/me/calendarview",
                params={
                    "startDateTime": start_str,
                    "endDateTime": end_str,
                    "$orderby": "start/dateTime",
                    "$top": 50,
                    "$select": "id,subject,body,start,end,location,organizer,attendees,onlineMeeting,onlineMeetingUrl,isOnlineMeeting"
                }
            )
            
            if response.status_code == 401:
                # Token expired, try refresh
                if await self.refresh_token():
                    return await self.get_calendar_invites(lookahead_hours)
                return []
            
            response.raise_for_status()
            data = response.json()
            
            for event in data.get("value", []):
                meeting = self._parse_calendar_event(event)
                if meeting:
                    meetings.append(meeting)
            
            # Handle pagination
            next_link = data.get("@odata.nextLink")
            while next_link:
                response = await self._http_client.get(next_link)
                response.raise_for_status()
                data = response.json()
                
                for event in data.get("value", []):
                    meeting = self._parse_calendar_event(event)
                    if meeting:
                        meetings.append(meeting)
                
                next_link = data.get("@odata.nextLink")
            
            logger.info(f"Found {len(meetings)} upcoming meetings from Outlook")
            
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Outlook calendar events: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching Outlook events: {e}")
        
        return meetings
    
    def _parse_calendar_event(self, event: dict) -> Optional[MeetingDetails]:
        """
        Parse an Outlook calendar event into MeetingDetails.
        
        Args:
            event: Microsoft Graph event dict.
            
        Returns:
            MeetingDetails if valid online meeting, None otherwise.
        """
        try:
            # Get start and end times
            start_info = event.get("start", {})
            end_info = event.get("end", {})
            
            start_time = self._parse_graph_datetime(start_info)
            end_time = self._parse_graph_datetime(end_info)
            
            if not start_time or not end_time:
                return None
            
            # Get event details
            subject = event.get("subject", "Untitled Meeting")
            event_id = event.get("id", "")
            
            # Get body/description
            body = event.get("body", {})
            description = ""
            if body.get("contentType") == "html":
                description = clean_html(body.get("content", ""))
            else:
                description = body.get("content", "")
            
            # Get location
            location_info = event.get("location", {})
            location = location_info.get("displayName", "")
            
            # Find meeting URL
            meeting_url = None
            platform = MeetingPlatform.UNKNOWN
            
            # Check onlineMeetingUrl (for Teams meetings)
            online_meeting_url = event.get("onlineMeetingUrl")
            if online_meeting_url:
                meeting_url = online_meeting_url
                if "teams.microsoft.com" in online_meeting_url.lower():
                    platform = MeetingPlatform.TEAMS
            
            # Check onlineMeeting object
            if not meeting_url:
                online_meeting = event.get("onlineMeeting", {})
                if online_meeting:
                    meeting_url = online_meeting.get("joinUrl")
                    if meeting_url and "teams" in meeting_url.lower():
                        platform = MeetingPlatform.TEAMS
            
            # Check location and body for other meeting URLs
            if not meeting_url:
                search_text = f"{location} {description}"
                result = extract_meeting_url(search_text)
                if result:
                    meeting_url, platform = result
            
            # Skip if not an online meeting
            if not meeting_url:
                return None
            
            # Get organizer
            organizer_info = event.get("organizer", {})
            email_addr = organizer_info.get("emailAddress", {})
            organizer_email = email_addr.get("address", "")
            organizer_name = email_addr.get("name", organizer_email)
            
            # Get attendees
            attendees = []
            for attendee in event.get("attendees", []):
                email_info = attendee.get("emailAddress", {})
                attendees.append(email_info.get("address", ""))
            
            # Generate meeting ID
            meeting_id = self._generate_meeting_id(meeting_url, start_time, event_id)
            
            return MeetingDetails(
                meeting_id=meeting_id,
                title=subject,
                start_time=start_time,
                end_time=end_time,
                meeting_url=meeting_url,
                platform=platform,
                source=MeetingSource.OUTLOOK,
                organizer=organizer_name,
                organizer_email=organizer_email,
                attendees=attendees,
                description=description if description else None,
                location=location,
                raw_event_id=event_id,
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse Outlook event: {e}")
            return None
    
    def _parse_graph_datetime(self, time_info: dict) -> Optional[datetime]:
        """
        Parse datetime from Microsoft Graph format.
        
        Args:
            time_info: Dict with 'dateTime' and 'timeZone'.
            
        Returns:
            Parsed datetime.
        """
        try:
            dt_str = time_info.get("dateTime")
            tz_str = time_info.get("timeZone", "UTC")
            
            if not dt_str:
                return None
            
            # Parse datetime
            dt = datetime.fromisoformat(dt_str.rstrip('Z'))
            
            # Apply timezone
            try:
                tz = ZoneInfo(tz_str)
                dt = dt.replace(tzinfo=tz)
            except Exception:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            
            return dt
            
        except Exception as e:
            logger.warning(f"Failed to parse datetime: {e}")
            return None
    
    def _generate_meeting_id(
        self,
        url: str,
        start_time: datetime,
        event_id: str = ""
    ) -> str:
        """Generate a unique meeting ID."""
        unique_string = f"{url}|{start_time.isoformat()}|{event_id}"
        return hashlib.sha256(unique_string.encode()).hexdigest()[:16]
    
    async def close(self) -> None:
        """Close HTTP client and cleanup."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
