"""
Teams Meeting Handler

Handles all Microsoft Teams meeting operations including:
- Meeting join automation
- Pre-join setup (name entry, muting)
- Permission dialog handling
- Lobby admission
- Transcription setup
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from app.config import settings, get_logger
from app.models import MeetingDetails
from app.transcription.service import TranscriptionService
from app.recording import RecordingService
from app.storage import S3Service
from app.speaker_detection import SpeakingTracker
from .teams_scripts import (
    TEAMS_SELECTORS,
    TEAMS_CAPTION_OBSERVER_JS,
    get_selectors_for,
)
from datetime import datetime


logger = get_logger("teams_handler")


class TeamsMeetingHandler:
    """Handler for Microsoft Teams meetings."""
    
    def __init__(self, browser: Browser, transcription_service: TranscriptionService, s3_service: S3Service = None):
        self.browser = browser
        self.transcription_service = transcription_service
        self.recording_service = RecordingService(s3_service=s3_service)
        self.speaking_tracker: SpeakingTracker | None = None  # Will be set per meeting
        logger.info("TeamsMeetingHandler initialized with recording service")
    
    async def join_meeting(self, meeting: MeetingDetails, active_contexts: dict[str, BrowserContext]) -> None:
        """
        Join a Microsoft Teams meeting with full automation.
        
        Flow:
        1. Navigate to meeting URL
        2. Handle "Continue on this browser" prompt
        3. Enter display name on pre-join screen
        4. Mute microphone and camera
        5. Click "Join now"
        6. Wait for admission (lobby)
        7. Enable captions and start transcription
        """

        # VIDEO RECORDING STARTS HERE - capture timestamp for sync
        import time
        video_start_timestamp_ms = int(time.time() * 1000)
        
        context = await self.browser.new_context(
            permissions=["microphone", "camera"],
            ignore_https_errors=True,
            record_video_dir="recordings/temp",  # Temporary dir, will be moved
            record_video_size={"width": 1920, "height": 1080}
        )
        active_contexts[meeting.meeting_url] = context
        
        # Set context for recording service WITH video start timestamp
        self.recording_service.set_context(context)
        self.recording_service.set_video_start_timestamp(video_start_timestamp_ms)
        logger.info(f"Video recording started at context creation: {video_start_timestamp_ms}")
        
        page = await context.new_page()
        
        # Hook console logs for debugging
        page.on("console", lambda msg: logger.debug(f"TEAMS CONSOLE: {msg.text}"))
        
        try:
            # --- Step 1: Navigate to meeting URL ---
            # Force Teams web version to avoid desktop app popup
            original_url = meeting.meeting_url
            web_url = original_url
            if "webjoin=true" not in original_url:
                connector = "&" if "?" in original_url else "?"
                web_url = f"{original_url}{connector}webjoin=true"
            
            logger.info(f"Navigating to Teams meeting (forced web): {web_url}")
            # Use domcontentloaded instead of networkidle - Teams has long-running requests
            await page.goto(web_url, wait_until="domcontentloaded", timeout=60000)
            logger.info("Teams meeting page loaded")
            
            # Wait for page to stabilize
            await asyncio.sleep(2)

            
            await asyncio.sleep(20)
            # --- Step 3: Handle permission dialog early (before name entry) ---
            await self._handle_permission_dialog(page)
            
            # --- Step 3.5: Dismiss any overlay dialogs blocking the pre-join screen ---
            await self._dismiss_overlay_dialogs(page)
            
            # Wait for pre-join screen to fully load
            logger.info("Waiting for pre-join screen to load...")
            await asyncio.sleep(3)
                        
            # Wait for either name input OR join button to appear
            try:
                await page.wait_for_selector(
                    'input[placeholder*="name"], button:has-text("Join now")',
                    timeout=1000
                )
                logger.info("Pre-join screen detected")
            except:
                logger.warning("Pre-join screen elements not detected, continuing anyway...")
            
            # Try dismissing overlays again after waiting
            await self._dismiss_overlay_dialogs(page)
            
            await asyncio.sleep(2)
            
            # --- Step 4: Enter display name ---
            bot_name = meeting.title or settings.bot.teams_bot_name
            name_entered = await self._enter_name(page, bot_name)
            
            if not name_entered:
                # Try again with more wait
                logger.info("Retrying name entry after additional wait...")
                await asyncio.sleep(1)
                await self._enter_name(page, bot_name)
            
            # --- Step 5: Mute microphone and camera before joining ---
            await self._mute_before_join(page)

            # Small wait after muting
            await asyncio.sleep(1)
                        
            # --- Step 6: Click "Join now" button ---
            join_success = await self._click_join(page)
            if not join_success:
                logger.warning("First join attempt failed, retrying...")
                await asyncio.sleep(2)
                join_success = await self._click_join(page)
            
            await asyncio.sleep(2)
            
            # --- Step 7: Wait for admission (lobby handling) ---
            admitted = await self._wait_for_admission(page, timeout=600)
            
            if not admitted:
                logger.error(f"Failed to join Teams meeting: {meeting.title}")
                await context.close()
                if meeting.meeting_url in active_contexts:
                    del active_contexts[meeting.meeting_url]
                return
            
            logger.info(f"✅ Successfully joined Teams meeting: {meeting.title}")
            
            # --- Step 8: Post-join setup ---
            # Enable captions and start transcription
            await self._start_transcription(page, meeting)
            
            # Start automatic recording
            logger.info("Starting automatic recording for Teams...")
            recording_started = await self.recording_service.start_recording(page, meeting)
            if recording_started:
                logger.info("✅ Recording started successfully")
            else:
                logger.warning("⚠️ Recording failed to start")
            
            # Start speaking tracker for speaker diarization
            logger.info("Starting speaking tracker for Teams...")
            self.speaking_tracker = SpeakingTracker(page, verbose_logging=False)
            await self.speaking_tracker.start()
            logger.info("✅ Speaking tracker started")
            
            return context, page
            
        except Exception as e:
            logger.error(f"Error during Teams join flow: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            await context.close()
            if meeting.meeting_url in active_contexts:
                del active_contexts[meeting.meeting_url]
            return None, None
    
    async def _dismiss_overlay_dialogs(self, page: Page) -> None:
        """Dismiss any overlay dialogs that may be blocking the pre-join screen."""
        logger.info("Checking for overlay dialogs to dismiss...")
        
        try:
            # Method 1: Press Escape to close any modal dialogs
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            
            # Method 2: Look for close buttons on dialogs
            close_button_selectors = [
                'button[aria-label="Close"]',
                'button[aria-label="Dismiss"]',
                'button[data-tid*="close"]',
                '.ui-dialog__overlay button',
                '[class*="dialog"] button[aria-label*="close" i]',
                '[class*="modal"] button[aria-label*="close" i]',
                'button:has-text("Close")',
                'button:has-text("Got it")',
                'button:has-text("OK")',
                'button:has-text("Skip")',
                'button:has-text("Not now")',
            ]
            
            for selector in close_button_selectors:
                try:
                    close_btn = page.locator(selector).first
                    if await close_btn.count() > 0 and await close_btn.is_visible(timeout=500):
                        await close_btn.click(timeout=2000)
                        logger.info(f"✅ Dismissed dialog using: {selector}")
                        await asyncio.sleep(0.5)
                        break
                except:
                    continue
            
            # Method 3: Click outside any overlay to dismiss
            try:
                overlay = page.locator('.ui-dialog__overlay, [class*="overlay"]').first
                if await overlay.count() > 0 and await overlay.is_visible(timeout=500):
                    # Press Escape again
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
            except:
                pass
            
            logger.info("Overlay check complete")
            
        except Exception as e:
            logger.debug(f"Overlay dismiss check: {e}")
    
    async def _enter_name(self, page: Page, bot_name: str) -> bool:
        """Enter bot's display name in Teams pre-join screen."""
        logger.info(f"Looking for name input field to enter: {bot_name}")

        try:
            # Wait for the name input to appear
            input_field = page.locator('input[placeholder="Type your name"]')
            await input_field.wait_for(state="visible", timeout=5000)

            # Focus and type name
            await input_field.click()
            await page.wait_for_timeout(500)

            # Clear and type using keyboard (most reliable for Teams)
            await input_field.fill("")
            await page.keyboard.type(bot_name, delay=50)

            logger.info(f"✅ Entered bot name: {bot_name}")
            return True

        except Exception as e:
            logger.warning(f"❌ Failed to enter bot name: {e}")
            return False
    
    async def _mute_before_join(self, page: Page) -> None:
        """Ensure microphone and camera are OFF before joining the meeting."""
        logger.info("Ensuring microphone and camera are muted before joining...")
        
        # --- Turn off Camera ---
        await self._turn_off_camera(page)
        
        # --- Turn off Microphone ---
        await self._turn_off_mic(page)
        
        await asyncio.sleep(1)
    
    async def _turn_off_camera(self, page: Page) -> None:
        """Turn off camera in Teams pre-join screen using specific switch element."""
        logger.info("Attempting to turn off camera...")
        
        try:
            # Use the specific switch element provided by user
            result = await page.evaluate("""
                () => {
                    // Look for the specific camera switch with data-tid="toggle-video"
                    const cameraSwitch = document.querySelector('[data-tid="toggle-video"]');
                    if (cameraSwitch) {
                        const isChecked = cameraSwitch.checked;
                        if (isChecked) {
                            // Camera is ON, click to turn OFF
                            cameraSwitch.click();
                            return 'clicked_camera_switch';
                        } else {
                            // Camera is already OFF
                            return 'already_off';
                        }
                    }
                    return 'not_found';
                }
            """)
            
            logger.info(f"Camera toggle result: {result}")
            
            if result == 'clicked_camera_switch':
                await asyncio.sleep(0.5)
                logger.info("✅ Camera turned OFF")
            elif result == 'already_off':
                logger.info("Camera already OFF")
            else:
                logger.warning("Camera switch not found")
                
        except Exception as e:
            logger.warning(f"Error turning off camera: {e}")
    
    async def _turn_off_mic(self, page: Page) -> None:
        """Turn off microphone in Teams pre-join screen."""
        logger.info("Attempting to turn off microphone...")
        
        try:
            # Find the mic toggle checkbox and uncheck it if it's checked
            await page.evaluate("""
                () => {
                    const micToggle = document.querySelector('input[data-tid="toggle-mute"]');
                    if (micToggle && micToggle.checked) {
                        micToggle.click();
                    }
                }
            """)
            
            logger.info("✅ Mic turned off")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Failed to turn off mic: {e}")

    async def _click_join(self, page: Page) -> bool:
        """Click "Join now" button on Teams pre-join screen."""
        logger.info("Looking for 'Join now' button...")
        
        try:
            # Method 1: Use data-tid attribute (most reliable for Teams)
            join_button = page.locator('button[data-tid="prejoin-join-button"]')
            
            # Wait for button to be enabled and visible
            await join_button.wait_for(state="visible", timeout=10000)
            
            # Check if button is disabled
            if await join_button.is_disabled():
                logger.warning("Join button is disabled, waiting for it to be enabled...")
                await join_button.wait_for(state="attached", timeout=5000)
            
            await join_button.click()
            logger.info("✅ Clicked 'Join now' button")
            return True
            
        except Exception as e:
            logger.error(f"Failed to click join button: {e}")
            return False
    
    async def _handle_permission_dialog(self, page: Page) -> bool:
        """Handle Teams browser permission dialog - allow device access for audio capture."""
        logger.info("Checking for permission dialog...")

        try:
            # Small wait for dialog animation
            await page.wait_for_timeout(1000)

            # Priority order: Try to ALLOW device access first (needed for audio capture)
            # The bot will mute mic/camera in _mute_before_join() anyway
            allow_button_texts = [
                "Allow",
                "Allow devices", 
                "Allow access",
            ]

            for text in allow_button_texts:
                btn = page.get_by_role("button", name=text)
                try:
                    await btn.first.wait_for(state="visible", timeout=2000)
                    logger.info(f"Found 'Allow' permission button: '{text}'")
                    await btn.first.click()
                    logger.info(f"✅ Clicked '{text}' - device access granted for audio capture")
                    await page.wait_for_timeout(2000)
                    return True
                except Exception:
                    pass

            # Fallback: If no "Allow" button found, check for "Continue without" 
            # but log a warning since audio capture may not work
            fallback_texts = [
                "Continue without audio or video",
            ]

            for text in fallback_texts:
                btn = page.get_by_role("button", name=text)
                try:
                    await btn.first.wait_for(state="visible", timeout=2000)
                    logger.warning(f"⚠️ Only found '{text}' button - audio capture may not work!")
                    logger.warning("Consider ensuring browser has device permissions.")
                    await btn.first.click()
                    await page.wait_for_timeout(2000)
                    return True
                except Exception:
                    pass

            logger.info("No permission dialog found (or already dismissed)")
            return True

        except Exception as e:
            logger.warning(f"Error handling permission dialog: {e}")
            return True

    
    async def _wait_for_admission(self, page: Page, timeout: int = 600) -> bool:
        """Wait for admission to Teams meeting (handles lobby)."""
        logger.info(f"Waiting for Teams meeting admission (timeout: {timeout}s)...")
        
        start_time = datetime.now()
        last_status_log = start_time
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            # First, check if permission dialog appeared
            try:
                # Quick check for "Continue without audio or video" button
                continue_btn = page.locator('button:has-text("Continue without")')
                if await continue_btn.count() > 0 and await continue_btn.first.is_visible(timeout=1000):
                    logger.info("⚠️ Permission dialog detected during admission wait!")
                    await self._handle_permission_dialog(page)
            except:
                pass
            
            # Check if we're in the meeting (Leave button visible)
            leave_selectors = get_selectors_for("leave_button")
            
            for selector in leave_selectors:
                try:
                    leave_btn = page.locator(selector)
                    if await leave_btn.count() > 0 and await leave_btn.first.is_visible(timeout=1000):
                        logger.info("✅ Successfully admitted to Teams meeting!")
                        return True
                except:
                    continue
            
            # Check for participant list (another indicator of being in meeting)
            try:
                roster = page.locator('[data-tid="roster-list"], #roster-list')
                if await roster.count() > 0 and await roster.first.is_visible(timeout=500):
                    logger.info("✅ Detected participant list - we're in the meeting!")
                    return True
            except:
                pass
            
            # Check for waiting/lobby messages
            lobby_selectors = get_selectors_for("waiting_lobby")
            in_lobby = False
            
            for selector in lobby_selectors:
                try:
                    lobby_msg = page.locator(selector)
                    if await lobby_msg.count() > 0 and await lobby_msg.first.is_visible(timeout=500):
                        in_lobby = True
                        break
                except:
                    continue
            
            # Log status periodically (every 10 seconds)
            if (datetime.now() - last_status_log).total_seconds() >= 10:
                elapsed = int((datetime.now() - start_time).total_seconds())
                if in_lobby:
                    logger.info(f"⏳ Still waiting in Teams lobby... ({elapsed}s elapsed)")
                else:
                    logger.info(f"⏳ Waiting for Teams meeting admission... ({elapsed}s elapsed)")
                last_status_log = datetime.now()
                
            
            # Check for denial/error messages
            denied_selectors = get_selectors_for("entry_denied")
            
            for selector in denied_selectors:
                try:
                    denied_msg = page.locator(selector)
                    if await denied_msg.count() > 0 and await denied_msg.first.is_visible(timeout=500):
                        logger.error("❌ Entry denied or meeting ended")
                        return False
                except:
                    continue
            
            await asyncio.sleep(2)
        
        logger.error(f"❌ Timed out waiting for Teams meeting admission ({timeout}s)")
        return False
    
    async def _start_transcription(self, page: Page, meeting: MeetingDetails) -> None:
        """Start transcription for Teams meeting. Enables captions and injects caption observer JavaScript."""
        try:
            logger.info("Starting Teams transcription...")
            
            # 1. Start transcription service with meeting details
            self.transcription_service.start_transcription(meeting.title, meeting)
            
            # 2. Expose Python callback to page
            async def on_transcript(data):
                speaker = data.get("speaker", "Unknown Speaker")
                text = data.get("text", "")
                timestamp = data.get("timestamp")  # ISO timestamp from JS
                if text:
                    self.transcription_service.append_transcript(speaker, text, timestamp)
                    logger.debug(f"Caption: [{speaker}] {text[:50]}...")
            
            await page.expose_function("screenAppTranscript", on_transcript)
            
            # 3. Enable captions
            captions_enabled = await self._enable_captions(page)
            
            if not captions_enabled:
                logger.warning("Captions not enabled - transcription may not work")
            else:
                logger.info("Teams captions enabled")
            
            # 4. Inject caption observer JavaScript
            await page.evaluate(TEAMS_CAPTION_OBSERVER_JS)
            logger.info("Teams caption observer injected")
            
            # 5. Start background task to ensure captions stay enabled
            asyncio.create_task(self._caption_monitor(page))
            
        except Exception as e:
            logger.error(f"Failed to start Teams transcription: {e}")
    
    async def _enable_captions(self, page: Page) -> bool:
        """Enable live captions in Teams meeting."""
        logger.info("Attempting to enable Teams live captions...")
        
        # Check if captions are already on
        container_selectors = get_selectors_for("caption_container")
        for selector in container_selectors:
            try:
                container = page.locator(selector)
                if await container.count() > 0 and await container.first.is_visible(timeout=1000):
                    logger.info("Caption container already visible - captions are on")
                    return True
            except:
                continue
        
        # Open More actions menu and click captions
        more_actions_selectors = get_selectors_for("more_actions")
        
        for selector in more_actions_selectors:
            try:
                more_btn = page.locator(selector)
                if await more_btn.count() > 0:
                    await more_btn.first.click(force=True, timeout=3000)
                    logger.info("Opened 'More actions' menu")
                    await asyncio.sleep(2)
                    
                    # Find and click caption option in menu
                    result = await page.evaluate("""
                        () => {
                            const elements = document.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], button');
                            
                            for (const el of elements) {
                                const text = (el.textContent || '').toLowerCase();
                                const label = (el.getAttribute('aria-label') || '').toLowerCase();
                                
                                if ((text.includes('caption') || label.includes('caption')) && 
                                    !text.includes('turn off') && !label.includes('turn off')) {
                                    
                                    const rect = el.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0) {
                                        el.click();
                                        return {success: true, found: el.textContent};
                                    }
                                }
                            }
                            return {success: false};
                        }
                    """)
                    
                    if result.get('success'):
                        logger.info(f"✅ Clicked caption option from More menu: {result.get('found')}")
                        await asyncio.sleep(2)
                        return True
                    
                    # Close menu if nothing found
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                    break
            except:
                continue
        
        logger.warning("Could not enable Teams captions - menu options not found")
        return False
    
    async def _caption_monitor(self, page: Page) -> None:
        """Background task to periodically check if captions are still enabled."""
        logger.info("Starting Teams caption monitor...")
        
        try:
            while True:
                if page.is_closed():
                    break
                
                await asyncio.sleep(60)  # Check every minute
                
                try:
                    # Check if caption container is visible
                    container_selectors = get_selectors_for("caption_container")
                    
                    container_visible = False
                    for selector in container_selectors:
                        try:
                            container = page.locator(selector)
                            if await container.count() > 0 and await container.first.is_visible(timeout=1000):
                                container_visible = True
                                break
                        except:
                            continue
                    
                    if not container_visible:
                        logger.info("Caption container not visible, attempting to re-enable...")
                        await self._enable_captions(page)
                        
                except Exception as e:
                    logger.debug(f"Caption monitor check failed: {e}")
                    
        except asyncio.CancelledError:
            logger.debug("Teams caption monitor cancelled")
        except Exception as e:
            logger.error(f"Teams caption monitor error: {e}")
