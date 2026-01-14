"""
Email service module for fetching calendar invites from Gmail.
"""

from typing import List, Optional
from .base import EmailServiceBase
from .gmail import GmailService
from .ical_parser import parse_icalendar
from .url_extractor import (
    extract_meeting_url,
    extract_all_meeting_urls,
    detect_platform_from_url,
    clean_html,
)
from ..models import MeetingDetails
from ..config import settings, EmailProvider, get_logger

logger = get_logger("email_service")


class EmailServiceFactory:
    """Factory for creating email service instances."""
    
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
        
        if provider in (EmailProvider.GMAIL, EmailProvider.BOTH):
            services.append(GmailService())
            logger.info("Gmail service initialized")
        
        # Note: Outlook support has been removed. Only Gmail is available.
        
        return services


class CombinedEmailService:
    """
    Combined email service that aggregates results from multiple providers.
    """
    
    def __init__(self, provider: Optional[EmailProvider] = None):
        """
        Initialize the combined email service.
        
        Args:
            provider: Which provider(s) to use. Defaults to settings value.
        """
        self.provider = provider or settings.email_provider
        self.services = EmailServiceFactory.create(self.provider)
        self._scheduled_meetings: set = set()  # Track scheduled meeting IDs
    
    async def authenticate_all(self) -> bool:
        """
        Authenticate all configured email services.
        
        Returns:
            True if at least one service authenticated successfully.
        """
        if not self.services:
            logger.error("No email services configured")
            return False
        
        results = []
        for service in self.services:
            try:
                result = await service.authenticate()
                results.append(result)
                logger.info(f"{service.__class__.__name__}: {'authenticated' if result else 'failed'}")
            except Exception as e:
                logger.error(f"{service.__class__.__name__} authentication error: {e}")
                results.append(False)
        
        return any(results)
    
    async def get_all_calendar_invites(
        self,
        lookahead_hours: int = 24
    ) -> List[MeetingDetails]:
        """
        Get calendar invites from all configured services.
        
        Args:
            lookahead_hours: How many hours ahead to look.
            
        Returns:
            Combined and deduplicated list of meetings.
        """
        all_meetings = []
        
        for service in self.services:
            try:
                if not service.is_authenticated():
                    await service.authenticate()
                
                meetings = await service.get_calendar_invites(lookahead_hours)
                all_meetings.extend(meetings)
                logger.debug(f"{service.__class__.__name__}: found {len(meetings)} meetings")
            except Exception as e:
                logger.error(f"Error fetching from {service.__class__.__name__}: {e}")
        
        # Deduplicate
        deduplicated = self._deduplicate_meetings(all_meetings)
        logger.info(f"Total unique meetings found: {len(deduplicated)}")
        
        return deduplicated
    
    async def get_new_meetings(
        self,
        lookahead_hours: int = 24
    ) -> List[MeetingDetails]:
        """
        Get only new meetings that haven't been scheduled yet.
        
        Args:
            lookahead_hours: How many hours ahead to look.
            
        Returns:
            List of new meetings.
        """
        all_meetings = await self.get_all_calendar_invites(lookahead_hours)
        
        new_meetings = [
            m for m in all_meetings
            if m.meeting_id not in self._scheduled_meetings
        ]
        
        logger.info(f"Found {len(new_meetings)} new meetings (not yet scheduled)")
        return new_meetings
    
    def mark_as_scheduled(self, meeting: MeetingDetails) -> None:
        """
        Mark a meeting as scheduled to prevent duplicate scheduling.
        
        Args:
            meeting: The meeting that was scheduled.
        """
        self._scheduled_meetings.add(meeting.meeting_id)
        meeting.is_scheduled = True
        logger.debug(f"Marked meeting as scheduled: {meeting.title} ({meeting.meeting_id})")
    
    def clear_completed_meetings(self, meetings: List[MeetingDetails]) -> None:
        """
        Remove completed meetings from tracking.
        
        Args:
            meetings: List of meetings to check.
        """
        for meeting in meetings:
            if meeting.has_ended:
                self._scheduled_meetings.discard(meeting.meeting_id)
                logger.debug(f"Removed completed meeting from tracking: {meeting.title}")
    
    def _deduplicate_meetings(
        self,
        meetings: List[MeetingDetails]
    ) -> List[MeetingDetails]:
        """
        Remove duplicate meetings based on URL and start time.
        
        Args:
            meetings: List of meetings.
            
        Returns:
            Deduplicated list.
        """
        seen = set()
        unique = []
        
        for meeting in meetings:
            # Use URL and start time for deduplication
            key = (meeting.meeting_url, meeting.start_time.isoformat())
            if key not in seen:
                seen.add(key)
                unique.append(meeting)
        
        return unique
    
    async def close(self) -> None:
        """Close all services and cleanup."""
        for service in self.services:
            if hasattr(service, 'close'):
                await service.close()


__all__ = [
    "EmailServiceBase",
    "GmailService",
    "EmailServiceFactory",
    "CombinedEmailService",
    "parse_icalendar",
    "extract_meeting_url",
    "extract_all_meeting_urls",
    "detect_platform_from_url",
    "clean_html",
]
