"""
Base class for email services.
"""

from abc import ABC, abstractmethod
from typing import List
from ..models import MeetingDetails


class EmailServiceBase(ABC):
    """
    Abstract base class for email services.
    Defines the interface that all email service implementations must follow.
    """
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the email service.
        
        Returns:
            True if authentication was successful, False otherwise.
        """
        pass
    
    @abstractmethod
    async def get_calendar_invites(
        self,
        lookahead_hours: int = 24
    ) -> List[MeetingDetails]:
        """
        Get calendar invites/meeting events.
        
        Args:
            lookahead_hours: How many hours ahead to look for meetings.
            
        Returns:
            List of MeetingDetails objects.
        """
        pass
    
    @abstractmethod
    async def refresh_token(self) -> bool:
        """
        Refresh the authentication token if expired.
        
        Returns:
            True if refresh was successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def is_authenticated(self) -> bool:
        """
        Check if currently authenticated.
        
        Returns:
            True if authenticated, False otherwise.
        """
        pass
