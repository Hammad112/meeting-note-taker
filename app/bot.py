"""
Meeting Bot Orchestrator.
Coordinates email monitoring, meeting scheduling, and join automation.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo

import httpx

from app.config import settings, get_logger
from app.email_service import CombinedEmailService
from app.scheduler import MeetingScheduler
from app.meeting_handler import MeetingJoiner
from app.models import MeetingDetails, MeetingSession, MeetingPlatform, MeetingSource

logger = get_logger("bot")


class MeetingBot:
    """
    Main Meeting Bot orchestrator.
    
    Coordinates:
    - Email monitoring for calendar invites
    - Meeting scheduling and join automation
    - Transcription
    - Backend communication
    """
    
    def __init__(self):
        """Initialize the Meeting Bot."""
        self.email_service = CombinedEmailService()
        self.scheduler = MeetingScheduler()
        self.http_client: Optional[httpx.AsyncClient] = None
        self.meeting_joiner: Optional[MeetingJoiner] = None
        self._auth_only_mode = False
        self._initialized = False
        
        self.active_sessions: Dict[str, MeetingSession] = {} # meeting_id -> session
        
        # Shutdown flag
        self._shutdown_event = asyncio.Event()
        
        # Set up scheduler callbacks
        self.scheduler.set_callbacks(
            on_meeting_join=self._on_meeting_join,
            on_meeting_end=self._on_meeting_end,
            on_email_poll=self._on_email_poll
        )
    
    async def initialize(self) -> bool:
        """
        Initialize all services.
        
        Returns:
            True if initialization was successful.
        """
        if self._initialized:
            return True
        logger.info("Initializing Meeting Bot...")
        
        # Initialize HTTP client for backend communication
        self.http_client = httpx.AsyncClient(
            base_url=settings.backend.url,
            headers={
                "X-API-Key": settings.backend.api_key,
                "Content-Type": "application/json"
            },
            timeout=70.0
        )
        
        # Authenticate email services
        logger.info("Authenticating email services...")
        auth_success = await self.email_service.authenticate_all()
        
        if not auth_success:
            # We don't log spam here because the email services already log their specific status
            self._auth_only_mode = True
            return True 

        # Initialize meeting joiner
        self.meeting_joiner = MeetingJoiner()
        await self.meeting_joiner.start()
        
        logger.info("Meeting Bot initialized successfully")
        self._auth_only_mode = False
        self._initialized = True
        return True
    
    async def run(self) -> None:
        """Run the Meeting Bot main loop."""
        # Bot should be initialized by the lifespan manager in main.py
        if self._auth_only_mode:
            logger.info("Bot is in authentication-only mode. Waiting for OAuth tokens.")
            # Start a background task to check for tokens periodically if initialized but in auth_only_mode
            asyncio.create_task(self._auth_check_loop())
            return

        await self.start_services()

    async def _auth_check_loop(self) -> None:
        """Periodically check for auth tokens if in auth-only mode."""
        while self._auth_only_mode and not self._shutdown_event.is_set():
            logger.debug("Checking for new OAuth tokens...")
            auth_success = await self.email_service.authenticate_all()
            if auth_success:
                logger.info("✅ All email services authenticated! Starting services...")
                self._auth_only_mode = False
                await self.start_services()
                break
            await asyncio.sleep(60) # Check every minute

    async def start_services(self) -> None:
        """Start the bot services (scheduler)."""
        if self.scheduler.is_running:
            return

        # Initialize meeting joiner if not already
        if not self.meeting_joiner:
            self.meeting_joiner = MeetingJoiner()
            await self.meeting_joiner.start()

        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started. Bot is now active.")
        
        # Initial poll
        await self.scheduler.trigger_immediate_poll()
    
    async def manual_join_meeting(self, bot_name: str, meeting_url: str) -> dict:
        """Manually join a meeting."""
        try:
            from app.models import MeetingPlatform, MeetingSource
            
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
                description=f"Manual join by {bot_name}"
            )
            
            if not self.meeting_joiner:
                self.meeting_joiner = MeetingJoiner()
                await self.meeting_joiner.start()
            
            session_id = str(uuid.uuid4())[:16]
            session = MeetingSession(
                meeting=meeting,
                session_id=session_id,
                started_at=now
            )
            self.active_sessions[meeting_id] = session
            
            await self._start_session(session)
            meeting.is_joined = True
            asyncio.create_task(self.meeting_joiner.join_meeting(meeting))
            
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
        
        if not self._auth_only_mode:
            self.scheduler.stop()
        
        for session in list(self.active_sessions.values()):
            if session.is_active:
                await self._end_session(session)
        
        await self.email_service.close()
        
        if self.meeting_joiner:
            await self.meeting_joiner.stop()
        
        if self.http_client:
            await self.http_client.aclose()
        
        logger.info("Meeting Bot shutdown complete")
    
    async def _on_email_poll(self) -> List[MeetingDetails]:
        """Callback for email polling."""
        try:
            meetings = await self.email_service.get_new_meetings(
                lookahead_hours=settings.scheduler.lookahead_hours
            )
            for meeting in meetings:
                await self._report_meeting_to_backend(meeting)
                self.email_service.mark_as_scheduled(meeting)
            return meetings
        except Exception as e:
            logger.error(f"Email poll error: {e}")
            return []
    
    async def _on_meeting_join(self, meeting: MeetingDetails) -> None:
        """Callback when it's time to join a meeting."""
        # Use automated tz_info for all comparisons
        now = datetime.now(settings.tz_info)
        time_since_start = (now - meeting.start_time).total_seconds() / 60
        max_late_join = settings.scheduler.max_join_after_start_minutes
        
        if time_since_start > max_late_join or meeting.has_ended:
            logger.warning(f"❌ SKIPPED: Meeting {meeting.title} outside join window")
            return
        
        if len(self.active_sessions) >= settings.scheduler.max_concurrent_meetings:
            logger.warning("❌ SKIPPED: Max concurrent meetings reached")
            return

        if meeting.meeting_id in self.active_sessions:
            return
        
        try:
            session_id = str(uuid.uuid4())[:16]
            session = MeetingSession(
                meeting=meeting,
                session_id=session_id,
                started_at=datetime.now(settings.tz_info)
            )
            self.active_sessions[meeting.meeting_id] = session
            await self._start_session(session)
            meeting.is_joined = True

            if self.meeting_joiner:
                await self.meeting_joiner.join_meeting(meeting)
        except Exception as e:
            logger.error(f"❌ FAILED to join meeting: {e}")
            if meeting.meeting_id in self.active_sessions:
                del self.active_sessions[meeting.meeting_id]

    async def _on_meeting_end(self, meeting: MeetingDetails) -> None:
        """Callback when a meeting is scheduled to end."""
        if meeting.meeting_id in self.active_sessions:
            session = self.active_sessions[meeting.meeting_id]
            await self._end_session(session)
            del self.active_sessions[meeting.meeting_id]
        
        meeting.is_completed = True
        await self._report_meeting_completed(meeting)

    async def _start_session(self, session: MeetingSession) -> None:
        """Start a session in backend."""
        try:
            if not session.started_at:
                session.started_at = datetime.now(settings.tz_info)
            
            response = await self.http_client.post(
                "/api/sessions",
                json={
                    "session_id": session.session_id,
                    "meeting_id": session.meeting.meeting_id,
                    "bot_name": self._get_bot_name(session.meeting),
                    "platform": session.meeting.platform.value,
                    "start_time": session.started_at.isoformat()
                }
            )
            response.raise_for_status()
            session.is_recording = True
            session.is_transcribing = True
        except Exception as e:
            logger.error(f"Failed to start session in backend: {e}")
    
    async def _end_session(self, session: MeetingSession) -> None:
        """End a session in backend."""
        try:
            session.ended_at = datetime.now(settings.tz_info)
            response = await self.http_client.patch(
                f"/api/sessions/{session.session_id}/end",
                json={"ended_at": session.ended_at.isoformat()}
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to end session in backend: {e}")
    
    async def _report_meeting_to_backend(self, meeting: MeetingDetails) -> None:
        """Report meeting to backend."""
        try:
            await self.http_client.post(
                "/api/meetings",
                json={
                    "meeting_id": meeting.meeting_id,
                    "title": meeting.title,
                    "start_time": meeting.start_time.isoformat(),
                    "end_time": meeting.end_time.isoformat(),
                    "meeting_url": meeting.meeting_url,
                    "platform": meeting.platform.value,
                    "source": meeting.source.value,
                    "organizer": meeting.organizer,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to report meeting to backend: {e}")

    def _get_bot_name(self, meeting: MeetingDetails) -> str:
        """Get the appropriate bot name for the platform."""
        if meeting.platform == MeetingPlatform.TEAMS:
            return settings.bot.teams_bot_name or settings.bot.default_bot_name
        elif meeting.platform == MeetingPlatform.ZOOM:
            return settings.bot.zoom_bot_name or settings.bot.default_bot_name
        elif meeting.platform == MeetingPlatform.GOOGLE_MEET:
            return settings.bot.google_meet_bot_name or settings.bot.default_bot_name
        return settings.bot.default_bot_name

    async def _report_meeting_completed(self, meeting: MeetingDetails) -> None:
        """Report meeting completion."""
        try:
            await self.http_client.patch(f"/api/meetings/{meeting.meeting_id}/complete")
        except Exception as e:
            logger.warning(f"Failed to mark meeting completed: {e}")

    def get_status(self) -> dict:
        """Get current status."""
        return {
            "running": self.scheduler.is_running,
            "scheduled_meetings": self.scheduler.scheduled_count,
            "active_sessions": [s.to_dict() for s in self.active_sessions.values()],
            "email_provider": settings.email_provider.value,
            "auth_only_mode": self._auth_only_mode
        }
