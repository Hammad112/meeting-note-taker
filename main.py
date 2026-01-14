"""
Main Meeting Bot Application.
Orchestrates email monitoring, meeting scheduling, and transcription.
"""

import asyncio
import signal
import sys
import uuid
from datetime import datetime
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo

import httpx

from config import settings, logger, get_logger
from email_service import CombinedEmailService
from scheduler import MeetingScheduler
from meeting_handler import MeetingJoiner
from models import MeetingDetails, MeetingSession, TranscriptSegment
from auth_server import start_auth_server, stop_auth_server

main_logger = get_logger("main")


class MeetingBot:
    """
    Main Meeting Bot orchestrator.
    
    Coordinates:
    - Email monitoring for calendar invites
    - Meeting scheduling and join automation
    - Transcription (when implemented)
    - Backend communication
    """
    
    def __init__(self):
        """Initialize the Meeting Bot."""
        self.email_service = CombinedEmailService()
        self.scheduler = MeetingScheduler()
        self.http_client: Optional[httpx.AsyncClient] = None
        self.meeting_joiner: Optional[MeetingJoiner] = None
        self.auth_server = None
        self._auth_only_mode = False  # Flag for when running auth server only
        
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
        main_logger.info("Initializing Meeting Bot...")
        
        # Start authentication server if enabled
        if settings.auth_server.enabled:
            try:
                self.auth_server = await start_auth_server(
                    host=settings.auth_server.host,
                    port=settings.auth_server.port
                )
                main_logger.info(
                    f"Authentication server started at http://{settings.auth_server.host}:{settings.auth_server.port}"
                )
                main_logger.info("Users can authenticate at the auth server instead of automatic redirects")
            except Exception as e:
                main_logger.warning(f"Failed to start auth server: {e}")
                main_logger.info("Continuing without auth server...")
        
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
        main_logger.info("Authenticating email services...")
        auth_success = await self.email_service.authenticate_all()
        
        if not auth_success:
            main_logger.error("Failed to authenticate email services")
            if settings.auth_server.enabled and self.auth_server:
                main_logger.info("")
                main_logger.info("=" * 60)
                main_logger.info("🔐 AUTHENTICATION REQUIRED")
                main_logger.info("=" * 60)
                main_logger.info(f"✨ Auth server: http://{settings.auth_server.host}:{settings.auth_server.port}")
                main_logger.info("👉 Open the URL above in your browser to authenticate")
                main_logger.info("⏳ Bot will automatically continue once authenticated")
                main_logger.info("=" * 60)
                main_logger.info("")
                # Keep running with auth server only, don't initialize other services
                self._auth_only_mode = True
                return True
            else:
                main_logger.error("Auth server is disabled. Cannot authenticate.")
                return False

        # Initialize meeting joiner (browser automation)
        self.meeting_joiner = MeetingJoiner()
        await self.meeting_joiner.start()
        
        main_logger.info("Meeting Bot initialized successfully")
        self._auth_only_mode = False
        return True
    
    async def run(self) -> None:
        """
        Run the Meeting Bot main loop.
        
        This starts the scheduler and runs until shutdown is requested.
        """
        if not await self.initialize():
            main_logger.error("Failed to initialize Meeting Bot")
            return
        
        # If in auth-only mode, wait for authentication to complete
        if self._auth_only_mode:
            main_logger.info("Running in authentication-only mode")
            main_logger.info("🔄 Waiting for authentication to complete...")
            main_logger.info("   (Authenticate with OAuth at http://localhost:8888)")
            main_logger.info("   ⚠️  Note: Gmail API requires OAuth - app passwords won't work")
            self._setup_signal_handlers()
            
            # Poll for authentication every 3 seconds
            token_file = settings.gmail.token_file
            import os
            check_count = 0
            
            try:
                while not self._shutdown_event.is_set():
                    check_count += 1
                    
                    # Check if OAuth token file exists
                    if os.path.exists(token_file):
                        main_logger.info("✅ OAuth token detected! Continuing initialization...")
                        
                        # Re-authenticate now that we have tokens
                        auth_success = await self.email_service.authenticate_all()
                        
                        if auth_success:
                            main_logger.info("✅ Email services authenticated successfully!")
                            
                            # Initialize meeting joiner
                            self.meeting_joiner = MeetingJoiner()
                            await self.meeting_joiner.start()
                            
                            # Exit auth-only mode
                            self._auth_only_mode = False
                            main_logger.info("✅ Full initialization complete!")
                            break
                        else:
                            main_logger.error("❌ Authentication failed. Please try OAuth authentication.")
                            main_logger.error("   Direct credentials (app passwords) do NOT work with Gmail API")
                    
                    # Every 10 checks (30 seconds), try re-authenticating in case user saved credentials
                    elif check_count % 10 == 0:
                        auth_success = await self.email_service.authenticate_all()
                        if auth_success:
                            main_logger.info("✅ Email services authenticated successfully!")
                            
                            # Initialize meeting joiner
                            self.meeting_joiner = MeetingJoiner()
                            await self.meeting_joiner.start()
                            
                            # Exit auth-only mode
                            self._auth_only_mode = False
                            main_logger.info("✅ Full initialization complete!")
                            break
                    
                    # Wait 3 seconds before checking again
                    try:
                        await asyncio.wait_for(self._shutdown_event.wait(), timeout=3.0)
                        # If we get here, shutdown was requested
                        break
                    except asyncio.TimeoutError:
                        # Timeout is expected, continue polling
                        pass
                        
            except asyncio.CancelledError:
                pass
            
            # If still in auth-only mode, shutdown
            if self._auth_only_mode:
                await self.shutdown()
                return
        
        # Normal operation mode
        # Start scheduler
        self.scheduler.start()
        main_logger.info("Scheduler started")
        
        # Do an immediate poll for meetings
        main_logger.info("Performing initial email poll...")
        await self.scheduler.trigger_immediate_poll()
        
        # Print status
        self._print_status()
        
        # Start periodic status logging
        status_task = asyncio.create_task(self._periodic_status_logging())
        
        # Run until shutdown
        main_logger.info("Meeting Bot is running. Press Ctrl+C to stop.")
        
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            # Cancel status task
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass
            await self.shutdown()
    
    async def shutdown(self) -> None:
        """Shutdown the Meeting Bot gracefully."""
        main_logger.info("Shutting down Meeting Bot...")
        
        # Stop scheduler (only if not in auth-only mode)
        if not self._auth_only_mode:
            self.scheduler.stop()
        
        # End all active sessions
        for session in list(self.active_sessions.values()):
            if session.is_active:
                await self._end_session(session)
        
        # Close email services
        await self.email_service.close()
        
        # Stop meeting joiner
        if self.meeting_joiner:
            await self.meeting_joiner.stop()
        
        # Stop auth server
        if self.auth_server:
            await stop_auth_server()
        
        # Close HTTP client
        if self.http_client:
            await self.http_client.aclose()
        
        main_logger.info("Meeting Bot shutdown complete")
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        # Windows-safe signal handling
        signal.signal(signal.SIGINT, lambda s, f: self._shutdown_event.set())
        signal.signal(signal.SIGTERM, lambda s, f: self._shutdown_event.set())
    
    async def _handle_shutdown_signal(self) -> None:
        """Handle shutdown signal."""
        main_logger.info("Received shutdown signal")
        self._shutdown_event.set()
    
    async def _on_email_poll(self) -> List[MeetingDetails]:
        """
        Callback for email polling.
        
        Returns:
            List of new meetings found.
        """
        main_logger.debug("Polling for new meetings...")
        
        try:
            meetings = await self.email_service.get_new_meetings(
                lookahead_hours=settings.scheduler.lookahead_hours
            )
            
            # Report to backend
            for meeting in meetings:
                await self._report_meeting_to_backend(meeting)
                self.email_service.mark_as_scheduled(meeting)
            
            return meetings
            
        except Exception as e:
            main_logger.error(f"Email poll error: {e}")
            return []
    
    async def _on_meeting_join(self, meeting: MeetingDetails) -> None:
        """
        Callback when it's time to join a meeting.
        
        Args:
            meeting: The meeting to join.
        """
        main_logger.info("="*80)
        main_logger.info(f"📅 JOIN REQUEST: {meeting.title}")
        main_logger.info(f"   🔗 URL: {meeting.meeting_url}")
        main_logger.info(f"   🏢 Platform: {meeting.platform.value.upper()}")
        main_logger.info(f"   ⏰ Start: {meeting.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        main_logger.info(f"   🎯 Meeting ID: {meeting.meeting_id}")
        
        # Check if meeting is within the valid join window
        now = datetime.now(ZoneInfo("UTC"))
        time_since_start = (now - meeting.start_time).total_seconds() / 60  # minutes
        
        # Only join if:
        # 1. Meeting hasn't started yet (negative time_since_start), OR
        # 2. Meeting started less than max_join_after_start_minutes ago
        max_late_join = settings.scheduler.max_join_after_start_minutes
        if time_since_start > max_late_join:
            main_logger.warning(
                f"❌ SKIPPED: Meeting started {time_since_start:.1f} minutes ago "
                f"(max allowed: {max_late_join} min)"
            )
            main_logger.info("="*80)
            return
        
        # Check if meeting has already ended
        if meeting.has_ended:
            main_logger.warning(f"❌ SKIPPED: Meeting has already ended")
            main_logger.info("="*80)
            return
        
        # Check concurrency limit
        if len(self.active_sessions) >= settings.scheduler.max_concurrent_meetings:
            main_logger.warning(
                f"❌ SKIPPED: Max concurrent meetings reached ({len(self.active_sessions)}/{settings.scheduler.max_concurrent_meetings})"
            )
            main_logger.info(f"   Active sessions: {', '.join(s.meeting.title for s in self.active_sessions.values())}")
            main_logger.info("="*80)
            return

        # Check if already active
        if meeting.meeting_id in self.active_sessions:
            session = self.active_sessions[meeting.meeting_id]
            main_logger.info(f"ℹ️  ALREADY ACTIVE: Session {session.session_id[:8]}... running for {(datetime.now(ZoneInfo('UTC')) - session.started_at).seconds // 60} minutes")
            main_logger.info("="*80)
            return
        
        main_logger.info(f"✅ JOINING: Time since start: {time_since_start:.1f} min (within {max_late_join} min window)")
        main_logger.info(f"   Active sessions before join: {len(self.active_sessions)}")
        
        try:
            # Create session
            session_id = str(uuid.uuid4())[:16]
            session = MeetingSession(
                meeting=meeting,
                session_id=session_id,
                started_at=datetime.now(ZoneInfo("UTC"))
            )
            self.active_sessions[meeting.meeting_id] = session
            
            main_logger.info(f"🆔 Session created: {session_id}")
            main_logger.info(f"   📊 Total active sessions: {len(self.active_sessions)}")
            
            # Report to backend
            await self._start_session(session)
            
            # Mark meeting as joined
            meeting.is_joined = True

            # Phase 2 - Actual meeting join via Playwright
            main_logger.info(f"🚀 Launching browser for: {meeting.title}")
            if self.meeting_joiner:
                await self.meeting_joiner.join_meeting(meeting)
                main_logger.info(f"✅ Browser join completed for: {meeting.title}")
            else:
                # Fallback logging if joiner is not available
                main_logger.warning("⚠️  MeetingJoiner not initialized; cannot auto-join.")
                main_logger.info(f"   URL: {meeting.meeting_url}")
                main_logger.info(f"   Platform: {meeting.platform.value}")
                main_logger.info(
                    f"   Meeting ends at: {meeting.end_time.strftime('%H:%M')}"
                )
            
            main_logger.info("="*80)
            
        except Exception as e:
            main_logger.error(f"❌ FAILED to join meeting: {e}")
            main_logger.error(f"   Meeting: {meeting.title}")
            main_logger.error(f"   URL: {meeting.meeting_url}")
            # If failed, remove from active sessions
            if meeting.meeting_id in self.active_sessions:
                del self.active_sessions[meeting.meeting_id]
                main_logger.info(f"   Removed failed session. Active sessions: {len(self.active_sessions)}")
            main_logger.info("="*80)
    
    async def _on_meeting_end(self, meeting: MeetingDetails) -> None:
        """
        Callback when a meeting is scheduled to end.
        
        Args:
            meeting: The meeting that is ending.
        """
        main_logger.info("="*80)
        main_logger.info(f"⏹️  MEETING ENDING: {meeting.title}")
        main_logger.info(f"   🔗 URL: {meeting.meeting_url}")
        main_logger.info(f"   🎯 Meeting ID: {meeting.meeting_id}")
        
        # End session if it exists
        if meeting.meeting_id in self.active_sessions:
            session = self.active_sessions[meeting.meeting_id]
            duration = (datetime.now(ZoneInfo("UTC")) - session.started_at).seconds // 60
            main_logger.info(f"   ⏱️  Session duration: {duration} minutes")
            main_logger.info(f"   🆔 Session ID: {session.session_id}")
            
            # Check if we should attempt to rejoin
            if await self._should_rejoin(meeting):
                main_logger.info(f"🔄 REJOIN TRIGGERED for: {meeting.title}")
                main_logger.info(f"   Attempt: {meeting.rejoin_attempts + 1}/{meeting.max_rejoin_attempts}")
                main_logger.info(f"   URL: {meeting.meeting_url}")
                meeting.rejoin_attempts += 1
                
                # Wait a bit before rejoining
                main_logger.info("   ⏳ Waiting 5 seconds before rejoin...")
                await asyncio.sleep(5)
                
                # Try to rejoin
                try:
                    if self.meeting_joiner:
                        main_logger.info(f"   🚀 Rejoining meeting: {meeting.title}")
                        await self.meeting_joiner.join_meeting(meeting)
                        main_logger.info(f"✅ SUCCESSFULLY REJOINED: {meeting.title}")
                        main_logger.info("="*80)
                        return  # Don't end the session, we're back in!
                except Exception as e:
                    main_logger.error(f"❌ REJOIN FAILED: {e}")
                    main_logger.error(f"   Meeting: {meeting.title}")
            
            # If we didn't rejoin, end the session
            main_logger.info(f"🛑 ENDING SESSION: {session.session_id}")
            await self._end_session(session)
            del self.active_sessions[meeting.meeting_id]
            main_logger.info(f"   📊 Remaining active sessions: {len(self.active_sessions)}")
            if self.active_sessions:
                main_logger.info(f"   Active: {', '.join(s.meeting.title for s in self.active_sessions.values())}")
        
        # Mark meeting as completed
        meeting.is_completed = True
        
        # Report to backend
        await self._report_meeting_completed(meeting)
        main_logger.info("="*80)
    
    async def _should_rejoin(self, meeting: MeetingDetails) -> bool:
        """
        Check if we should attempt to rejoin the meeting.
        
        Args:
            meeting: The meeting to check.
            
        Returns:
            True if we should rejoin.
        """
        # Don't rejoin if we were kicked
        if meeting.was_kicked:
            main_logger.warning(f"❌ REJOIN DENIED: Bot was kicked from meeting")
            main_logger.warning(f"   Meeting: {meeting.title}")
            return False
        
        # Don't rejoin if we've exceeded max attempts
        if meeting.rejoin_attempts >= meeting.max_rejoin_attempts:
            main_logger.warning(f"❌ REJOIN DENIED: Max attempts reached ({meeting.rejoin_attempts}/{meeting.max_rejoin_attempts})")
            main_logger.warning(f"   Meeting: {meeting.title}")
            return False
        
        # Check if meeting is still within time window
        now = datetime.now(ZoneInfo("UTC"))
        time_since_start = (now - meeting.start_time).total_seconds() / 60
        max_late_join = settings.scheduler.max_join_after_start_minutes
        
        if time_since_start > max_late_join:
            main_logger.warning(f"❌ REJOIN DENIED: Outside time window")
            main_logger.warning(f"   Meeting: {meeting.title}")
            main_logger.warning(f"   Started: {time_since_start:.1f} min ago (max: {max_late_join} min)")
            return False
        
        # Check if meeting end time hasn't passed
        if now >= meeting.end_time:
            main_logger.info(f"ℹ️  REJOIN DENIED: Meeting end time has passed")
            main_logger.info(f"   Meeting: {meeting.title}")
            return False
        
        time_remaining = (meeting.end_time - now).seconds // 60
        main_logger.info(f"✅ REJOIN APPROVED: {meeting.title}")
        main_logger.info(f"   Attempt: {meeting.rejoin_attempts + 1}/{meeting.max_rejoin_attempts}")
        main_logger.info(f"   Time since start: {time_since_start:.1f} min (max: {max_late_join} min)")
        main_logger.info(f"   Time remaining: {time_remaining} min")
        return True
    
    async def _start_session(self, session: MeetingSession) -> None:
        """
        Start a new meeting session and report to backend.
        
        Args:
            session: The session to start.
        """
        try:
            # Create session in backend
            response = await self.http_client.post(
                "/api/sessions",
                json={
                    "session_id": session.session_id,
                    "meeting_id": session.meeting.meeting_id,
                    "started_at": session.started_at.isoformat()
                }
            )
            response.raise_for_status()
            
            main_logger.info(f"Session started: {session.session_id}")
            session.is_recording = True
            session.is_transcribing = True
            
        except httpx.HTTPError as e:
            main_logger.error(f"Failed to start session in backend: {e}")
    
    async def _end_session(self, session: MeetingSession) -> None:
        """
        End a meeting session and report to backend.
        
        Args:
            session: The session to end.
        """
        try:
            session.ended_at = datetime.now(ZoneInfo("UTC"))
            session.is_recording = False
            session.is_transcribing = False
            
            # End session in backend
            response = await self.http_client.patch(
                f"/api/sessions/{session.session_id}/end",
                json={"ended_at": session.ended_at.isoformat()}
            )
            response.raise_for_status()
            
            main_logger.info(f"Session ended: {session.session_id}")
            
        except httpx.HTTPError as e:
            main_logger.error(f"Failed to end session in backend: {e}")
    
    async def _report_meeting_to_backend(self, meeting: MeetingDetails) -> None:
        """
        Report a meeting to the backend.
        
        Args:
            meeting: The meeting to report.
        """
        try:
            response = await self.http_client.post(
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
                    "organizer_email": meeting.organizer_email,
                    "attendees": meeting.attendees,
                    "description": meeting.description,
                    "location": meeting.location,
                }
            )
            response.raise_for_status()
            main_logger.debug(f"Meeting reported to backend: {meeting.title}")
            
        except httpx.HTTPError as e:
            main_logger.warning(f"Failed to report meeting to backend: {e}")
    
    async def _report_meeting_completed(self, meeting: MeetingDetails) -> None:
        """
        Report meeting completion to backend.
        
        Args:
            meeting: The completed meeting.
        """
        try:
            response = await self.http_client.patch(
                f"/api/meetings/{meeting.meeting_id}/complete"
            )
            response.raise_for_status()
            main_logger.debug(f"Meeting marked completed: {meeting.title}")
            
        except httpx.HTTPError as e:
            main_logger.warning(f"Failed to mark meeting completed: {e}")
    
    async def send_transcript(self, segment: TranscriptSegment) -> None:
        """
        Send a transcript segment to the backend.
        
        Args:
            segment: The transcript segment to send.
        """
        # For now, just use the first active session or implement a lookup if segment has meeting_id
        if not self.active_sessions:
            main_logger.warning("No active session for transcript")
            return
        
        # Assuming single session for simplified transcript flow or basic list picking
        # TODO: segment should ideally contain session tracking info
        session = list(self.active_sessions.values())[0]
        
        try:
            response = await self.http_client.post(
                "/api/transcripts",
                json={
                    "meeting_id": session.meeting.meeting_id,
                    "session_id": session.session_id,
                    "text": segment.text,
                    "timestamp": segment.timestamp.isoformat(),
                    "start_offset_seconds": segment.start_offset_seconds,
                    "end_offset_seconds": segment.end_offset_seconds,
                    "speaker": segment.speaker,
                    "confidence": segment.confidence,
                    "is_final": segment.is_final,
                }
            )
            response.raise_for_status()
            
            # Also store locally
            session.add_transcript(segment)
            
        except httpx.HTTPError as e:
            main_logger.error(f"Failed to send transcript: {e}")
    
    def _print_status(self) -> None:
        """Print current bot status."""
        scheduled = self.scheduler.get_scheduled_meetings()
        
        print("\n" + "="*80)
        print("MEETING BOT STATUS")
        print("="*80)
        print(f"Email Provider: {settings.email_provider.value}")
        print(f"Auth Method: {settings.gmail.auth_method.value}")
        if settings.auth_server.enabled:
            print(f"Auth Server: http://{settings.auth_server.host}:{settings.auth_server.port}")
        print(f"Poll Interval: {settings.scheduler.email_poll_interval_seconds} seconds")
        print(f"Join Before Start: {settings.scheduler.join_before_start_minutes} minutes")
        print(f"Max Join After Start: {settings.scheduler.max_join_after_start_minutes} minutes")
        print(f"Max Concurrent Meetings: {settings.scheduler.max_concurrent_meetings}")
        print(f"Scheduled Meetings: {len(scheduled)}")
        print(f"Active Sessions: {len(self.active_sessions)}")
        
        if self.active_sessions:
            print("\n🟢 ACTIVE SESSIONS:")
            for meeting_id, session in self.active_sessions.items():
                duration = (datetime.now(ZoneInfo("UTC")) - session.started_at).seconds // 60
                print(f"  📍 {session.meeting.title}")
                print(f"     Session ID: {session.session_id}")
                print(f"     URL: {session.meeting.meeting_url}")
                print(f"     Platform: {session.meeting.platform.value.upper()}")
                print(f"     Duration: {duration} minutes")
                print(f"     Rejoin attempts: {session.meeting.rejoin_attempts}/{session.meeting.max_rejoin_attempts}")
        
        if scheduled:
            print("\n📅 UPCOMING MEETINGS:")
            for meeting in sorted(scheduled, key=lambda m: m.start_time):
                print(f"  - {meeting.title}")
                print(f"    Start: {meeting.start_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"    Platform: {meeting.platform.value}")
                print(f"    URL: {meeting.meeting_url}")
        
        print("="*80 + "\n")
    
    async def _periodic_status_logging(self) -> None:
        """Periodically log active session status."""
        try:
            while True:
                # Wait 5 minutes between status updates
                await asyncio.sleep(300)
                
                if self.active_sessions:
                    main_logger.info("="*80)
                    main_logger.info("📊 PERIODIC STATUS UPDATE")
                    main_logger.info(f"   Active Sessions: {len(self.active_sessions)}")
                    
                    for meeting_id, session in self.active_sessions.items():
                        duration = (datetime.now(ZoneInfo("UTC")) - session.started_at).seconds // 60
                        main_logger.info(f"   🟢 {session.meeting.title}")
                        main_logger.info(f"      Session: {session.session_id}")
                        main_logger.info(f"      URL: {session.meeting.meeting_url}")
                        main_logger.info(f"      Duration: {duration} minutes")
                    main_logger.info("="*80)
        except asyncio.CancelledError:
            pass
    
    def get_status(self) -> dict:
        """
        Get current bot status.
        
        Returns:
            Status dictionary.
        """
        return {
            "running": self.scheduler.is_running,
            "scheduled_meetings": self.scheduler.scheduled_count,
            "active_sessions": [s.to_dict() for s in self.active_sessions.values()],
            "email_provider": settings.email_provider.value,
            "upcoming_jobs": self.scheduler.get_upcoming_jobs()
        }


async def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("MEETING BOT")
    print("=" * 60)
    print(f"Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    bot = MeetingBot()
    await bot.run()


def run():
    """Run the Meeting Bot (synchronous entry point)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
