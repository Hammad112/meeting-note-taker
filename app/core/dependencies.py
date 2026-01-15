"""
Dependency injection for the Meeting Bot API.
Provides instances of services and resources to API endpoints.
"""

from typing import Optional, Any, TYPE_CHECKING
from fastapi import Depends

# Placeholder - will be populated after moving services
_meeting_bot_instance: Optional[Any] = None


def set_meeting_bot_instance(instance):
    """Set the global meeting bot instance."""
    global _meeting_bot_instance
    _meeting_bot_instance = instance


async def get_meeting_bot_service():
    """
    Dependency injection for MeetingBot service.
    
    Returns:
        MeetingBotService instance
    
    Raises:
        HTTPException: If service is not initialized
    """
    from app.core.exceptions import HTTPInternalServerError
    
    if _meeting_bot_instance is None:
        raise HTTPInternalServerError("Meeting bot service not initialized")
    
    return _meeting_bot_instance


# Type hint for clarity
if TYPE_CHECKING:
    from app.domain.services.meeting_bot_service import MeetingBotService

MeetingBotDep = Depends(get_meeting_bot_service)
