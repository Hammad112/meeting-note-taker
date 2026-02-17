"""
Zoom Meeting Handler

Handles all Zoom meeting operations including:
- Meeting join automation
- Basic meeting setup
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
)

from app.config import get_logger
from app.models import MeetingDetails


logger = get_logger("zoom_handler")


class ZoomMeetingHandler:
    """Handler for Zoom meetings."""
    
    def __init__(self, browser: Browser):
        self.browser = browser
    
    async def join_meeting(self, meeting: MeetingDetails, active_contexts: dict[str, BrowserContext]) -> None:
        """
        Join a Zoom meeting with basic automation.
        
        Flow:
        1. Navigate to meeting URL
        2. Wait for page to load
        3. Allow manual completion of join flow
        """
        # Create isolated browser context for this meeting
        context = await self.browser.new_context(permissions=["microphone", "camera"])
        active_contexts[meeting.meeting_url] = context
        page = await context.new_page()
        
        try:
            # --- Step 1: Navigate to meeting URL ---
            logger.info(f"Navigating to Zoom meeting: {meeting.meeting_url}")
            await page.goto(meeting.meeting_url, wait_until="load")
            logger.info("Zoom meeting page loaded")
            
            # --- Step 2: Wait for page stabilization ---
            logger.info("Waiting for Zoom meeting page to stabilize...")
            await asyncio.sleep(30)
            logger.info("Complete join flow in browser.")
            
            return context, page
            
        except Exception as e:
            logger.error(f"Error during Zoom join flow: {e}")
            logger.error(traceback.format_exc())
            
            await context.close()
            if meeting.meeting_url in active_contexts:
                del active_contexts[meeting.meeting_url]
            return None, None
