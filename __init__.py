"""
Meeting Bot Package.
Automated meeting join and transcription system.
"""

from .main import MeetingBot, main, run
from .models import MeetingDetails, MeetingSession, TranscriptSegment, MeetingPlatform, MeetingSource
from .config import settings, logger, get_logger
from .email_service import (
    CombinedEmailService,
    GmailService,
    EmailServiceFactory,
)
from .scheduler import MeetingScheduler

__version__ = "1.0.0"
__author__ = "Meeting Bot Team"

__all__ = [
    # Main
    "MeetingBot",
    "main",
    "run",
    
    # Models
    "MeetingDetails",
    "MeetingSession",
    "TranscriptSegment",
    "MeetingPlatform",
    "MeetingSource",
    
    # Config
    "settings",
    "logger",
    "get_logger",
    
    # Email
    "CombinedEmailService",
    "GmailService",
    "EmailServiceFactory",
    
    # Scheduler
    "MeetingScheduler",
]
