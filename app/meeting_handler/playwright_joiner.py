"""
Playwright Meeting Joiner V2

Refactored version that uses the MeetingOrchestrator for platform-specific handling.
This is the new main entry point that replaces the old monolithic approach.

Usage:
    joiner = MeetingJoiner()
    await joiner.start()
    await joiner.join_meeting(meeting)
    await joiner.stop()
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
)

from app.config import settings, get_logger
from app.models import MeetingDetails, MeetingPlatform
from .meeting_orchestrator import MeetingOrchestrator


logger = get_logger("meeting_joiner")


class MeetingJoiner:
    """
    High-level interface for joining meetings via Playwright.
    
    This version uses the MeetingOrchestrator pattern:
    - Platform-specific handlers in separate files
    - Unified monitoring and cleanup
    - Better separation of concerns
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._orchestrator: Optional[MeetingOrchestrator] = None

        # Use a persistent user data directory so the user can log in once
        # and re-use their authenticated browser profile.
        # self._user_data_dir = Path(".playwright_user_data").resolve()  # UNUSED - commented out

    @property
    def is_running(self) -> bool:
        """Return True if the browser is currently available."""
        return self._browser is not None
    
    async def start(self) -> None:
        """Start Playwright and launch a Chromium browser instance."""
        if self._browser is not None:
            return

        logger.info("Starting Playwright meeting joiner...")

        self._playwright = await async_playwright().start()

        # We use launch() instead of launch_persistent_context to allow multiple isolated contexts
        # Added stealth arguments to avoid 403 Forbidden / 429 Too Many Requests
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            ignore_default_args=["--enable-automation"],  # Critical for stealth
            args=[
                # Media capture flags
                "--enable-usermedia-screen-capturing",
                "--allow-http-screen-capture",
                "--auto-accept-this-tab-capture",
                "--use-fake-ui-for-media-stream",  # Auto-accept permissions
                "--use-fake-device-for-media-stream",  # Create fake mic/camera devices
                "--use-file-for-fake-video-capture=/app/assets/avatar.png",  # Use static avatar instead of test pattern
                
                # AUDIO OUTPUT - Route browser audio to ALSA/PulseAudio for capture
                "--alsa-output-device=default",  # Use ALSA default (routed to PulseAudio)
                "--audio-output-channels=2",  # Stereo output
                "--disable-audio-output-resampler",  # Don't modify audio
                
                # Force audio playback even in headless/background
                "--autoplay-policy=no-user-gesture-required",
                "--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies",
                
                # Prevent audio suspension in background tabs (CRITICAL)
                "--disable-background-media-suspend",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                
                # Stealth flags
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--start-maximized",
                "--disable-infobars",
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-extensions",
                "--disable-popup-blocking",
                "--exclude-switches=enable-automation"
            ]
        )
        
        # Initialize orchestrator
        self._orchestrator = MeetingOrchestrator(self._browser)
        
        logger.info("Playwright meeting joiner started.")

    async def stop(self) -> None:
        """Stop Playwright and close the browser."""
        logger.info("Stopping Playwright meeting joiner...")

        # Clean up all active meetings through orchestrator
        if self._orchestrator:
            await self._orchestrator.cleanup_all()

        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            self._browser = None

        try:
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            self._playwright = None
            self._orchestrator = None

    async def join_meeting(self, meeting: MeetingDetails) -> None:
        """
        Join a meeting using the orchestrator.
        
        This method delegates to the appropriate platform handler through the orchestrator.
        """
        if not meeting.meeting_url:
            logger.warning(f"Cannot join meeting {meeting.title}: no meeting URL.")
            return

        if MeetingPlatform(meeting.platform.value) not in settings.enabled_platforms:
            logger.warning(
                f"Platform {meeting.platform.value} is disabled; "
                f"skipping auto-join for meeting {meeting.title}."
            )
            return

        if self._browser is None:
            await self.start()

        # Delegate to orchestrator
        await self._orchestrator.join_meeting(meeting)
