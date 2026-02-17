"""
Meeting Bot - Simplified.
Manual join only, no calendar polling or scheduling.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict

from app.config import settings, get_logger
from app.meeting_handler import MeetingJoiner
from app.models import MeetingDetails, MeetingSession, MeetingPlatform, MeetingSource

logger = get_logger("bot")


class MeetingBot:
    """
    Simplified Meeting Bot.
    
    Supports manual join only via API.
    No calendar polling or automatic scheduling.
    """
    
    def __init__(self):
        """Initialize the Meeting Bot."""
        self.meeting_joiner: Optional[MeetingJoiner] = None
        self._initialized = False
        self.active_sessions: Dict[str, MeetingSession] = {}
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> bool:
        """Initialize the meeting joiner."""
        if self._initialized:
            return True
        
        logger.info("Initializing Meeting Bot...")
        
        # Initialize meeting joiner
        self.meeting_joiner = MeetingJoiner()
        await self.meeting_joiner.start()
        
        logger.info("Meeting Bot initialized successfully")
        self._initialized = True
        return True
    
    async def manual_join_meeting(
        self, 
        bot_name: str, 
        meeting_url: str,
        s3_bucket_name: str = None, 
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None, 
        aws_region: str = None,
        caption_language: str = "English"
    ) -> dict:
        """
        Manually join a meeting.
        
        Args:
            bot_name: Display name for the bot
            meeting_url: Meeting URL (Google Meet, Teams, or Zoom)
            s3_bucket_name: Optional S3 bucket for transcript storage
            aws_access_key_id: Optional AWS access key
            aws_secret_access_key: Optional AWS secret key
            aws_region: Optional AWS region
            caption_language: Caption language (default: English)
            
        Returns:
            Dict with success status and meeting info
        """
        try:
            # Detect platform from URL
            platform = None
            meeting_url_lower = meeting_url.lower()
            
            if 'meet.google.com' in meeting_url_lower:
                platform = MeetingPlatform.GOOGLE_MEET
            elif 'zoom.us' in meeting_url_lower:
                platform = MeetingPlatform.ZOOM
            elif 'teams.microsoft.com' in meeting_url_lower or 'teams.live.com' in meeting_url_lower:
                platform = MeetingPlatform.TEAMS
            else:
                return {'success': False, 'error': 'Unsupported meeting platform'}
            
            # Create meeting details
            meeting_id = f"manual_{uuid.uuid4().hex[:12]}"
            now = datetime.now(settings.tz_info)
            
            meeting = MeetingDetails(
                meeting_id=meeting_id,
                title=bot_name,
                start_time=now,
                end_time=now.replace(hour=23, minute=59),
                meeting_url=meeting_url,
                platform=platform,
                source=MeetingSource.MANUAL,
                organizer=bot_name,
                description=f"Manual join by {bot_name}",
                caption_language=caption_language
            )
            
            # Store S3 credentials with the meeting 
            if s3_bucket_name and aws_access_key_id and aws_secret_access_key:
                meeting.s3_config = {
                    'bucket_name': s3_bucket_name,
                    'access_key_id': aws_access_key_id,
                    'secret_access_key': aws_secret_access_key,
                    'region': aws_region or 'us-east-1'
                }
            
            # Ensure joiner is initialized
            if not self.meeting_joiner:
                self.meeting_joiner = MeetingJoiner()
                await self.meeting_joiner.start()
            
            # Create session
            session_id = str(uuid.uuid4())[:16]
            session = MeetingSession(
                meeting=meeting,
                session_id=session_id,
                started_at=now
            )
            self.active_sessions[meeting_id] = session
            
            # Join meeting in background
            meeting.is_joined = True
            asyncio.create_task(self.meeting_joiner.join_meeting(meeting))
            
            logger.info(f"✅ Manual join initiated: {meeting.title} ({platform.value})")
            
            return {
                'success': True,
                'meeting_id': meeting_id,
                'session_id': session_id,
                'platform': platform.value
            }
            
        except Exception as e:
            logger.error(f"❌ Manual join failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def shutdown(self) -> None:
        """Shutdown the Meeting Bot gracefully."""
        logger.info("Shutting down Meeting Bot...")
        
        if self.meeting_joiner:
            await self.meeting_joiner.stop()
        
        self.active_sessions.clear()
        logger.info("Meeting Bot shutdown complete")
    
    def get_status(self) -> dict:
        """Get current bot status."""
        return {
            "initialized": self._initialized,
            "active_sessions": len(self.active_sessions),
            "sessions": [s.to_dict() for s in self.active_sessions.values()]
        }
