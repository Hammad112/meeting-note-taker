"""
Meeting scheduler using APScheduler.
Handles scheduling meeting joins at appropriate times.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Awaitable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)

from app.models import MeetingDetails
from app.config import settings, get_logger

logger = get_logger("scheduler")


class MeetingScheduler:
    """
    Scheduler for managing meeting join times and email polling.
    Uses APScheduler for time-based job scheduling.
    """
    
    def __init__(self):
        """Initialize the meeting scheduler."""
        self._settings = settings.scheduler
        self._is_running: bool = False
        
        # Configure job stores
        jobstores = {
            'default': MemoryJobStore()
        }
        
        # Create scheduler
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=ZoneInfo("UTC")
        )
        
        # Track scheduled meetings by ID and by URL
        self._scheduled_meetings: Dict[str, MeetingDetails] = {}
        self._scheduled_urls: set = set()  # Track URLs to prevent duplicates
        
        # Callbacks
        self._on_meeting_join: Optional[Callable[[MeetingDetails], Awaitable[None]]] = None
        self._on_meeting_end: Optional[Callable[[MeetingDetails], Awaitable[None]]] = None
        self._on_email_poll: Optional[Callable[[], Awaitable[List[MeetingDetails]]]] = None
        
        # Add event listeners
        self._scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED
        )
    
    def set_callbacks(
        self,
        on_meeting_join: Optional[Callable[[MeetingDetails], Awaitable[None]]] = None,
        on_meeting_end: Optional[Callable[[MeetingDetails], Awaitable[None]]] = None,
        on_email_poll: Optional[Callable[[], Awaitable[List[MeetingDetails]]]] = None
    ) -> None:
        """
        Set callback functions for scheduler events.
        
        Args:
            on_meeting_join: Called when it's time to join a meeting.
            on_meeting_end: Called when a meeting ends.
            on_email_poll: Called to poll for new meetings.
        """
        self._on_meeting_join = on_meeting_join
        self._on_meeting_end = on_meeting_end
        self._on_email_poll = on_email_poll
    
    def start(self) -> None:
        """Start the scheduler."""
        if not self._is_running:
            self._scheduler.start()
            self._is_running = True
            logger.info("Meeting scheduler started")
            # Schedule email polling job
            self._schedule_email_polling()
    
    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._is_running:
            return

        try:
            # Avoid calling into a closed event loop (e.g. during test teardown)
            loop = getattr(self._scheduler, "_eventloop", None)
            if self._scheduler.running and not (loop and loop.is_closed()):
                self._scheduler.shutdown(wait=False)
            logger.info("Meeting scheduler stopped")
        finally:
            # Always mark as not running from our perspective so tests/teardown
            # logic does not keep trying to stop an already-stopped scheduler.
            self._is_running = False
    
    def _schedule_email_polling(self) -> None:
        """Schedule periodic email polling job."""
        self._scheduler.add_job(
            self._email_poll_job,
            trigger=IntervalTrigger(
                seconds=self._settings.email_poll_interval_seconds,
                timezone=ZoneInfo("UTC")
            ),
            id="email_polling",
            name="Email Polling",
            replace_existing=True,
            max_instances=1
        )
        logger.info(
            f"Email polling scheduled every {self._settings.email_poll_interval_seconds} seconds"
        )
    
    async def _email_poll_job(self) -> None:
        """Email polling job that runs periodically."""
        logger.debug("Running email poll job...")
        
        if self._on_email_poll:
            try:
                meetings = await self._on_email_poll()
                logger.info(f"Email poll found {len(meetings)} new meetings")
                
                # Schedule each new meeting
                for meeting in meetings:
                    self.schedule_meeting(meeting)
            except Exception as e:
                logger.error(f"Email poll error: {e}")
    
    def schedule_meeting(self, meeting: MeetingDetails) -> bool:
        """
        Schedule a meeting join job.
        
        Args:
            meeting: Meeting to schedule.
            
        Returns:
            True if scheduled successfully.
        """
        # Check if already scheduled by ID
        if meeting.meeting_id in self._scheduled_meetings:
            logger.debug(f"Meeting already scheduled by ID: {meeting.title}")
            return False
        
        # Check if already scheduled by URL (prevents duplicates from different providers)
        if meeting.meeting_url in self._scheduled_urls:
            logger.debug(f"Meeting URL already scheduled: {meeting.meeting_url}")
            return False
        
        # Check if meeting has already ended
        if meeting.has_ended:
            logger.debug(f"Meeting has already ended: {meeting.title}")
            return False
        
        # Calculate join time (X minutes before start)
        join_time = meeting.start_time - timedelta(
            minutes=self._settings.join_before_start_minutes
        )
        
        # If join time is in the past but meeting hasn't started, join now
        now = datetime.now(ZoneInfo("UTC"))
        if join_time < now:
            if meeting.has_started and not meeting.has_ended:
                # Meeting is in progress, join immediately
                join_time = now + timedelta(seconds=5)
            elif not meeting.has_started:
                # Join time passed but meeting hasn't started
                join_time = now + timedelta(seconds=5)
            else:
                logger.debug(f"Meeting join time passed and meeting ended: {meeting.title}")
                return False
        
        try:
            # Schedule join job
            self._scheduler.add_job(
                self._meeting_join_job,
                trigger=DateTrigger(run_date=join_time, timezone=ZoneInfo("UTC")),
                args=[meeting],
                id=f"join_{meeting.meeting_id}",
                name=f"Join: {meeting.title}",
                replace_existing=True,
                misfire_grace_time=300  # 5 minutes grace period
            )
            
            # Schedule end job
            self._scheduler.add_job(
                self._meeting_end_job,
                trigger=DateTrigger(run_date=meeting.end_time, timezone=ZoneInfo("UTC")),
                args=[meeting],
                id=f"end_{meeting.meeting_id}",
                name=f"End: {meeting.title}",
                replace_existing=True,
                misfire_grace_time=60
            )
            
            # Track scheduled meeting by ID and URL
            self._scheduled_meetings[meeting.meeting_id] = meeting
            self._scheduled_urls.add(meeting.meeting_url)
            meeting.is_scheduled = True
            
            logger.info(
                f"Scheduled meeting: {meeting.title} "
                f"(join at {join_time.strftime('%H:%M')}, "
                f"end at {meeting.end_time.strftime('%H:%M')})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule meeting {meeting.title}: {e}")
            return False
    
    async def _meeting_join_job(self, meeting: MeetingDetails) -> None:
        """
        Meeting join job that runs at scheduled time.
        
        Args:
            meeting: Meeting to join.
        """
        logger.info(f"Time to join meeting: {meeting.title}")
        
        if self._on_meeting_join:
            try:
                await self._on_meeting_join(meeting)
            except Exception as e:
                logger.error(f"Meeting join callback error: {e}")
    
    async def _meeting_end_job(self, meeting: MeetingDetails) -> None:
        """
        Meeting end job that runs when meeting is scheduled to end.
        
        Args:
            meeting: Meeting that is ending.
        """
        logger.info(f"Meeting ending: {meeting.title}")
        
        if self._on_meeting_end:
            try:
                await self._on_meeting_end(meeting)
            except Exception as e:
                logger.error(f"Meeting end callback error: {e}")
        
        # Cleanup
        self._cleanup_meeting(meeting.meeting_id)
    
    def _cleanup_meeting(self, meeting_id: str) -> None:
        """
        Clean up a completed meeting.
        
        Args:
            meeting_id: ID of the meeting to clean up.
        """
        # Remove from tracking
        if meeting_id in self._scheduled_meetings:
            meeting = self._scheduled_meetings[meeting_id]
            self._scheduled_urls.discard(meeting.meeting_url)
            del self._scheduled_meetings[meeting_id]
        
        # Remove any remaining jobs
        for job_id in [f"join_{meeting_id}", f"end_{meeting_id}"]:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass  # Job might not exist
        
        logger.debug(f"Cleaned up meeting: {meeting_id}")
    
    def cancel_meeting(self, meeting_id: str) -> bool:
        """
        Cancel a scheduled meeting.
        
        Args:
            meeting_id: ID of the meeting to cancel.
            
        Returns:
            True if cancelled successfully.
        """
        if meeting_id not in self._scheduled_meetings:
            return False
        
        self._cleanup_meeting(meeting_id)
        logger.info(f"Cancelled meeting: {meeting_id}")
        return True
    
    def get_scheduled_meetings(self) -> List[MeetingDetails]:
        """
        Get all currently scheduled meetings.
        
        Returns:
            List of scheduled meetings.
        """
        return list(self._scheduled_meetings.values())
    
    def get_upcoming_jobs(self) -> List[dict]:
        """
        Get information about upcoming scheduled jobs.
        
        Returns:
            List of job info dictionaries.
        """
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        return jobs
    
    def _on_job_event(self, event: JobExecutionEvent) -> None:
        """
        Handle scheduler job events.
        
        Args:
            event: Job execution event.
        """
        if event.exception:
            logger.error(f"Job {event.job_id} failed: {event.exception}")
        elif hasattr(event, 'scheduled_run_time'):
            # Check if job was missed
            if event.scheduled_run_time:
                delay = (datetime.now(ZoneInfo("UTC")) - event.scheduled_run_time).total_seconds()
                if delay > 60:
                    logger.warning(f"Job {event.job_id} was delayed by {delay:.0f} seconds")
    
    async def trigger_immediate_poll(self) -> List[MeetingDetails]:
        """
        Trigger an immediate email poll (useful for initial startup).
        
        Returns:
            List of meetings found.
        """
        if self._on_email_poll:
            meetings = await self._on_email_poll()
            for meeting in meetings:
                self.schedule_meeting(meeting)
            return meetings
        return []
    
    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._is_running
    
    @property
    def scheduled_count(self) -> int:
        """Get count of scheduled meetings."""
        return len(self._scheduled_meetings)
