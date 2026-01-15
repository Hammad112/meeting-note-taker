"""
Calendar API service for fetching meeting data from backend endpoint.
This bypasses direct Gmail/Outlook authentication by using a unified calendar API.
"""

import httpx
from typing import List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .base import EmailServiceBase
from app.domain.models.meeting import MeetingDetails, MeetingPlatform, MeetingSource
from app.core.config import settings
from app.core.logging import get_logger
from .url_extractor import extract_meeting_url

logger = get_logger("calendar_api")


class CalendarAPIService(EmailServiceBase):
    """
    Calendar API service that fetches meetings from a backend endpoint.
    Supports aggregated calendar data from multiple providers (Gmail, Outlook, etc.)
    """
    
    def __init__(self):
        """Initialize the Calendar API service."""
        self.client: Optional[httpx.AsyncClient] = None
        self.authenticated = False
        self._settings = settings.backend
    
    async def authenticate(self) -> bool:
        """
        Authenticate with the backend API.
        
        Returns:
            True if authentication was successful.
        """
        try:
            # Create HTTP client
            self.client = httpx.AsyncClient(
                base_url=self._settings.url,
                headers={
                    "X-API-Key": self._settings.api_key,
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )
            
            # Test the connection
            response = await self.client.get("/health")
            
            if response.status_code == 200:
                logger.info(f"✅ Calendar API authenticated: {self._settings.url}")
                self.authenticated = True
                return True
            else:
                logger.error(f"❌ Calendar API health check failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to authenticate with Calendar API: {e}")
            return False
    
    async def get_calendar_invites(
        self,
        lookahead_hours: int = 168  # 7 days default
    ) -> List[MeetingDetails]:
        """
        Get calendar invites/meeting events.
        
        Args:
            lookahead_hours: How many hours ahead to look for meetings.
            
        Returns:
            List of MeetingDetails objects.
        """
        start_time = datetime.now(ZoneInfo("UTC"))
        end_time = start_time + timedelta(hours=lookahead_hours)
        
        return await self.fetch_meetings(start_time, end_time)
    
    async def refresh_token(self) -> bool:
        """
        Refresh the authentication token if expired.
        Calendar API uses API keys, so no refresh needed.
        
        Returns:
            True (always authenticated with API key)
        """
        return self.authenticated
    
    @property
    def is_authenticated(self) -> bool:
        """Check if the service is authenticated."""
        return self.authenticated
    
    async def fetch_meetings(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[MeetingDetails]:
        """
        Fetch meetings from the backend calendar API.
        
        Args:
            start_time: Start of time range (default: now)
            end_time: End of time range (default: 7 days from now)
        
        Returns:
            List of meeting details.
        """
        if not self.authenticated or not self.client:
            logger.error("Not authenticated with Calendar API")
            return []
        
        try:
            # Default time range
            if not start_time:
                start_time = datetime.now(ZoneInfo("UTC"))
            if not end_time:
                end_time = start_time + timedelta(days=7)
            
            # Fetch meetings from backend
            response = await self.client.get(
                "/api/calendar/meetings",
                params={
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch meetings: {response.status_code}")
                return []
            
            data = response.json()
            meetings = []
            
            # Parse meeting data
            for item in data.get("meetings", []):
                try:
                    meeting = self._parse_meeting(item)
                    if meeting:
                        meetings.append(meeting)
                except Exception as e:
                    logger.error(f"Failed to parse meeting: {e}")
                    continue
            
            logger.info(f"✅ Fetched {len(meetings)} meetings from Calendar API")
            return meetings
            
        except Exception as e:
            logger.error(f"Error fetching meetings from Calendar API: {e}")
            return []
    
    def _parse_meeting(self, item: dict) -> Optional[MeetingDetails]:
        """
        Parse meeting data from API response.
        
        Args:
            item: Meeting data dictionary from API
        
        Returns:
            MeetingDetails object or None if parsing fails
        """
        try:
            # Extract meeting URL
            meeting_url = item.get("meeting_url") or item.get("location", "")
            if not meeting_url:
                # Try to extract from description
                description = item.get("description", "")
                meeting_url = extract_meeting_url(description)
            
            if not meeting_url:
                return None
            
            # Determine platform
            platform = self._detect_platform(meeting_url)
            if not platform:
                return None
            
            # Parse times
            start_time = datetime.fromisoformat(item["start_time"])
            end_time = datetime.fromisoformat(item["end_time"])
            
            # Create meeting details
            meeting = MeetingDetails(
                meeting_id=item.get("id", item.get("meeting_id")),
                title=item.get("title", item.get("summary", "Untitled Meeting")),
                start_time=start_time,
                end_time=end_time,
                meeting_url=meeting_url,
                platform=platform,
                organizer=item.get("organizer", {}).get("email", ""),
                attendees=[
                    att.get("email", "") 
                    for att in item.get("attendees", [])
                ],
                description=item.get("description", ""),
                source=MeetingSource.CALENDAR_API
            )
            
            return meeting
            
        except Exception as e:
            logger.error(f"Error parsing meeting: {e}")
            return None
    
    def _detect_platform(self, url: str) -> Optional[MeetingPlatform]:
        """Detect meeting platform from URL."""
        url_lower = url.lower()
        
        if "meet.google.com" in url_lower:
            return MeetingPlatform.GOOGLE_MEET
        elif "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
            return MeetingPlatform.TEAMS
        elif "zoom.us" in url_lower:
            return MeetingPlatform.ZOOM
        
        return None
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            logger.info("Calendar API client closed")
