"""
Google Meet Meeting Handler

Handles all Google Meet meeting operations including:
- Meeting join automation
- Guest mode handling
- Auto-login functionality
- Lobby admission
- Transcription setup
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
)

from app.config import get_logger
from app.models import MeetingDetails
from app.transcription.service import TranscriptionService
from app.recording import RecordingService
from datetime import datetime


logger = get_logger("meet_handler")


class MeetMeetingHandler:
    """Handler for Google Meet meetings."""
    
    def __init__(self, browser: Browser, transcription_service: TranscriptionService, s3_service = None):
        self.browser = browser
        self.transcription_service = transcription_service
        self.s3_service = s3_service
        self.recording_service = RecordingService(s3_service=s3_service)
        logger.info("MeetMeetingHandler initialized with recording service")
    
    async def join_meeting(self, meeting: MeetingDetails, active_contexts: dict[str, BrowserContext]) -> None:
        """
        Join a Google Meet meeting with full automation.
        
        Flow:
        1. Navigate to meeting URL
        2. Handle device permission prompts
        3. Enter guest name or auto-login
        4. Click join button
        5. Wait for admission
        6. Start transcription
        """
        # Create a new isolated context for this meeting
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

        try:
            # --- Step 1: Navigate to meeting URL ---
            logger.info(f"Navigating to {meeting.meeting_url}...")
            await page.goto(meeting.meeting_url, wait_until="load")
            
            # Wait for page to stabilize
            await asyncio.sleep(3)
            
            # --- Step 2: Dismiss Device Checks ---
            # Try to click "Continue without microphone and camera"
            try:
                btn = page.get_by_role('button', name='Continue without microphone and camera')
                if await btn.is_visible(timeout=5000):
                    try:
                        await btn.click(timeout=5000)
                    except Exception as e:
                        logger.warning(f"Normal click failed: {e}. Trying force click...")
                        await btn.click(force=True)
                    logger.info("Clicked 'Continue without microphone and camera'")
                    await asyncio.sleep(1)
            except Exception:
                pass
            
            # --- Step 2.5: Explicitly turn off camera and microphone ---
            await self._mute_camera_and_mic(page)

            # --- Step 3: Handle Guest Name or Login ---
            name_input = None
            for selector in [
                'input[placeholder="Your name"]',
                'input[placeholder="Enter your name"]',
                'input[aria-label="Your name"]',
                'input[aria-label="Enter your name"]',
                'input[type="text"]' # Fallback to any text input if others fail
            ]:
                try:
                    # Specific check for generic input to ensure it's the right one (optional refinement)
                    input_el = page.locator(selector).first
                    if await input_el.is_visible(timeout=2000):
                        name_input = input_el
                        break
                except:
                    continue
            
            if name_input:
                bot_name = meeting.title or "Assistant"
                logger.info(f"Guest mode detected. Entering bot name: {bot_name}...")
                await name_input.fill(bot_name)
                await asyncio.sleep(1)
                # Proceed to click Join
            else:
                # If no guest input, check for login
                # But be careful, "Sign in" might be visible even on guest page (top right)
                # We strictly check if we are FORCED to login (i.e. we are on accounts.google.com or similar)
                
                # Check URL for login page
                is_login_page = "accounts.google.com" in page.url
                
                # Check for prominent central sign-in prompt (not just header button)
                is_signin_prompt = await page.get_by_text("Sign in to join").is_visible()
                
                if is_login_page or is_signin_prompt:
                    logger.info("Login page/prompt detected. Attempting auto-login...")
                    if not await self._perform_auto_login(page):
                         logger.error("Auto-login failed or no credentials. Aborting.")
                         return
                else:
                    logger.warning("Could not find name input AND not clearly on login page. Continuing to look for Join buttons...")

            # --- Step 4: Click Join Action (Ask to Join / Join Now) ---
            join_clicked = False
            clicked_btn_name = ""
            
            # Try clicking buttons
            for btn_name in ["Ask to join", "Join now", "Join"]:
                try:
                    btn = page.get_by_role("button", name=btn_name, exact=True)
                    if await btn.is_visible(timeout=2000):
                        try:
                            await btn.click(timeout=5000)
                        except Exception as click_error:
                            logger.warning(f"Normal click failed for '{btn_name}': {click_error}. Trying force click...")
                            await btn.click(force=True)
                        logger.info(f"Clicked '{btn_name}' button.")
                        await asyncio.sleep(2)
          
                        join_clicked = True
                        clicked_btn_name = btn_name
                        break
                except: continue
            
            if not join_clicked:
                logger.warning("No 'Join' button found. Check browser.")
                # We continue anyway, maybe it auto-joined?
            else:
                logger.info(f"Join action initiated via '{clicked_btn_name}'...")

            # --- Step 5: Wait for Admission / Entry ---
            # If we clicked "Ask to join", we are in a waiting state.
            logger.info("Waiting for meeting admission...")
            max_wait_time = 600 # 10 minutes wait for admission?
            start_time = datetime.now()
            admitted = False
            
            while (datetime.now() - start_time).total_seconds() < max_wait_time:
                # Check for success indicator
                leave_btn = page.locator('button[aria-label*="Leave call"]')
                if await leave_btn.count() > 0 and await leave_btn.first.is_visible():
                    logger.info(f"Successfully entered meeting {meeting.title} at {datetime.now()}")
                    admitted = True
                    break
                
                # Check for "Asking to join" or "You'll join when someone lets you in"
                # This is just for logging/debugging
                if await page.get_by_text("Asking to be admitted").is_visible() or \
                   await page.get_by_text("You'll join the call when someone lets you in").is_visible():
                     # Just log periodically? No, strict logging.
                     pass 
                
                await asyncio.sleep(2)
            
            if not admitted:
                logger.error("Timed out waiting for meeting admission (10 mins). Aborting.")
                await context.close()
                if meeting.meeting_url in active_contexts:
                   del active_contexts[meeting.meeting_url]
                return

            # --- Step 6: Post-Join Setup (Transcription) ---
            # Now we are 100% sure we are in.
            logger.info("Starting transcription for Google Meet...")
            await self._start_transcription(page, meeting)
            
            # Start automatic recording
            logger.info("Starting automatic recording for Google Meet...")
            recording_started = await self.recording_service.start_recording(page, meeting)
            if recording_started:
                logger.info("✅ Recording started successfully")
            else:
                logger.warning("⚠️ Recording failed to start")

            return context, page

        except Exception as e:
            logger.error(f"Error during join flow: {e}")
            try:
                logger.error("Error during join flow: {e}")
            except:
                pass
            await context.close()
            if meeting.meeting_url in active_contexts:
                del active_contexts[meeting.meeting_url]
            return None, None
    
    async def _perform_auto_login(self, page: Page) -> bool:
        """Attempts to log in using env vars. Returns True if successful."""
        email = os.getenv("GOOGLE_EMAIL")
        password = os.getenv("GOOGLE_PASSWORD")
        if not email or not password:
            logger.warning("GOOGLE_EMAIL/PASSWORD not set.")
            return False
        
        try:
            await page.get_by_label("Email or phone").fill(email)
            await page.get_by_role("button", name="Next").click()
            await page.wait_for_selector('input[type="password"]', timeout=10000)
            await page.get_by_role("textbox", name="Enter your password").fill(password)
            await page.get_by_role("button", name="Next").click()
            await page.wait_for_url(lambda u: "meet.google.com" in u, timeout=20000)
            return True
        except Exception as e:
            logger.error(f"Auto-login exception: {e}")
            return False
    
    async def _start_transcription(self, page: Page, meeting: MeetingDetails) -> None:
        """Injects Javascript to capture captions for Google Meet."""
        try:
            logger.info("Injecting transcription observer...")

            # Hook console logs to see JS errors in Python logs
            page.on("console", lambda msg: logger.info(f"BROWSER CONSOLE: {msg.text}"))
            
            # 1. Start service with meeting details
            self.transcription_service.start_transcription(meeting.title, meeting)

            # 2. Expose python callback
            async def on_transcript(data):
                # data is expected to be {speaker: "Name", text: "..."}
                speaker = data.get("speaker", "Unknown")
                text = data.get("text", "")
                if text:
                    self.transcription_service.append_transcript(speaker, text)
            
            # Clean up potential existing binding
            await page.expose_function("screenAppTranscript", on_transcript)

            # 3. Inject JS
            # Updated to V4: Uses 2.5s debouncing to ensure only full/stable sentences are captured.
            # This prevents repetitive fragments like "Hello", "Hello I", "Hello I am".
            js_script_robust = """
            () => {
                console.log("Transcription Observer ROBUST V4 (Debounced) Started");
                
                // Map to track timers for each element: Element -> {timer, text, speaker}
                const pendingEmissions = new Map();

                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        // We strictly want to handle text updates or new nodes
                        if (mutation.type !== 'childList' && mutation.type !== 'characterData') return;
                        
                        // Selectors from User HTML + Known ones
                        const textSelector = '.ygicle, .VbkSUe, .bh44bd, .iTTPOb, .CNusmb, [jscontroller="yQsYHe"]';
                        
                        // Limit scope
                        let scope = document.querySelector('[jsname="dsyhDe"]') || document.querySelector('.a4cQT') || document.body;
                        const textElements = scope.querySelectorAll(textSelector);
                        
                        textElements.forEach(el => {
                            const currentText = el.innerText;
                            if (!currentText || currentText.trim().length === 0) return;
                            
                            // Check if this is exactly what we last emitted for this element (stable state)
                            if (el.dataset.lastEmitted === currentText) return;

                            // Speaker Detection
                            let speaker = "Unknown Speaker";
                            const rowContainer = el.closest('.nMcdL') || el.closest('.bj4p3b');
                            if (rowContainer) {
                                const nameSpan = rowContainer.querySelector('.NWpY1d');
                                if (nameSpan) speaker = nameSpan.innerText;
                            }
                            if (speaker === "Unknown Speaker") {
                                const senderContainer = el.closest('[data-sender-name]');
                                if (senderContainer) speaker = senderContainer.getAttribute('data-sender-name');
                            }
                            if (speaker === "Unknown Speaker") {
                                const nameEl = el.closest('.a4cQT')?.querySelector('.zs7s8d');
                                if (nameEl) speaker = nameEl.innerText;
                            }

                            // Debounce Logic
                            // If we have a pending timer for this element, clear it (text is still changing!)
                            if (pendingEmissions.has(el)) {
                                clearTimeout(pendingEmissions.get(el).timer);
                            }

                            // Set a new timer. If no changes happen for 2.5 seconds, we emit.
                            const timer = setTimeout(() => {
                                // Final extraction logic
                                let textToEmit = currentText;
                                const lastEmitted = el.dataset.lastEmitted || "";
                                
                                // Handling Appends: "Hello" (emitted) -> "Hello World" (new)
                                // We only want to emit "World"
                                if (currentText.startsWith(lastEmitted)) {
                                    textToEmit = currentText.substring(lastEmitted.length).trim();
                                }
                                
                                // Clean up punctuation-only updates if necessary (e.g. just adding a dot)
                                // But generally if it's a new word, we want it.
                                
                                if (textToEmit && textToEmit.length > 0) {
                                    console.log(`Captured (Stable): ${speaker}: ${textToEmit}`);
                                    window.screenAppTranscript({
                                        speaker: speaker,
                                        text: textToEmit
                                    });
                                    // Mark this full text as emitted
                                    el.dataset.lastEmitted = currentText;
                                }
                                
                                pendingEmissions.delete(el);
                            }, 2500); // 2.5 seconds stability wait

                            // Store in map
                            pendingEmissions.set(el, { timer, text: currentText, speaker });
                        });
                    });
                });
                
                observer.observe(document.body, { childList: true, subtree: true, characterData: true });
            }
            """
            
            await page.evaluate(js_script_robust)
            
            # 4. Spawn Caption Enabler Background Task
            # We spawn this so it doesn't block main join flow (which needs to start monitor)
            asyncio.create_task(self._ensure_captions_loop(page))
            logger.info("Caption enabler task spawned.")

        except Exception as e:
            logger.error(f"Failed to start transcription logic: {e}")

    async def _ensure_captions_loop(self, page: Page) -> None:
        """Background task to ensure captions are enabled."""
        logger.info("Starting loop to ensure captions are enabled (checking every 30s)...")
        
        # Wait a moment for UI to settle before first check
        await asyncio.sleep(5)
        
        try:
            while True:
                # Safety check: Stop if page/browser is closed
                if page.is_closed():
                    logger.debug("Page closed, stopping caption check.")
                    break
                    
                try:
                    # 1. Check if "Turn off captions" exists -> If yes, they are ON.
                    turn_off_btn = page.locator('button[aria-label*="Turn off captions"]')
                    if await turn_off_btn.count() > 0 and await turn_off_btn.first.is_visible():
                        logger.info("Captions are ON (Found 'Turn off captions' button).")
                        break
                    
                    # 1.5 Try keyboard shortcut first (most reliable - bypasses overlays)
                    logger.info("Attempting to enable captions with keyboard shortcut 'c'...")
                    await page.keyboard.press("c")
                    await asyncio.sleep(2)
                    
                    # Check if it worked
                    if await turn_off_btn.count() > 0 and await turn_off_btn.first.is_visible():
                        logger.info("Successfully enabled captions with keyboard shortcut 'c'.")
                        break 
                    
                    # 2. Verify button state indicates captions are on
                    selectors = [
                        'button[jsname="r8qRAd"]',
                        'button[aria-label*="Turn on captions"]',
                        'button[aria-label*="captions"]', 
                        'button[icon="cc"]'
                    ]
                    
                    captions_already_on = False
                    
                    for sel in selectors:
                        btns = page.locator(sel)
                        count = await btns.count()
                        
                        for i in range(count):
                            btn = btns.nth(i)
                            if not await btn.is_visible():
                                continue
                            
                            is_pressed = await btn.get_attribute("aria-pressed")
                            label = await btn.get_attribute("aria-label") or ""
                            
                            if is_pressed == "true" or "Turn off" in label:
                                captions_already_on = True
                                break
                        
                        if captions_already_on:
                            break
                    
                    if captions_already_on:
                        logger.info("Captions are ON (verified via button state).")
                        break
                    
                    # If keyboard shortcut didn't work after first attempt, log and retry next cycle
                    logger.warning("Keyboard shortcut 'c' didn't enable captions yet. Will retry next cycle...")
                        
                except Exception as e:
                     logger.warning(f"Error in caption logic: {e}")

                # Wait 30 seconds before next check
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            logger.info("Caption check task cancelled.")
        except Exception as e:
            logger.error(f"Fatal error in caption loop: {e}")
    
    async def _mute_camera_and_mic(self, page) -> None:
        """
        Explicitly turn off camera and microphone before joining.
        Google Meet has toggle buttons on the pre-join screen.
        """
        logger.info("Ensuring camera and microphone are OFF before joining...")
        
        # Camera toggle selectors (Google Meet)
        camera_selectors = [
            'button[aria-label*="Turn off camera"]',
            'button[aria-label*="camera is on"]',
            'button[data-is-muted="false"][aria-label*="camera"]',
            '[data-tooltip*="Turn off camera"]',
        ]
        
        # Mic toggle selectors (Google Meet)
        mic_selectors = [
            'button[aria-label*="Turn off microphone"]',
            'button[aria-label*="microphone is on"]', 
            'button[data-is-muted="false"][aria-label*="microphone"]',
            '[data-tooltip*="Turn off microphone"]',
        ]
        
        # Try to turn off camera
        camera_off = False
        for selector in camera_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    camera_off = True
                    logger.info(f"✅ Camera turned OFF via: {selector}")
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                continue
        
        if not camera_off:
            # Try keyboard shortcut: Ctrl+E toggles camera in Meet
            try:
                await page.keyboard.press("Control+e")
                logger.info("Sent Ctrl+E to toggle camera")
                await asyncio.sleep(0.5)
            except Exception:
                pass
        
        # Try to turn off microphone
        mic_off = False
        for selector in mic_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    mic_off = True
                    logger.info(f"✅ Microphone turned OFF via: {selector}")
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                continue
        
        if not mic_off:
            # Try keyboard shortcut: Ctrl+D toggles mic in Meet
            try:
                await page.keyboard.press("Control+d")
                logger.info("Sent Ctrl+D to toggle microphone")
                await asyncio.sleep(0.5)
            except Exception:
                pass
        
        if not camera_off and not mic_off:
            logger.warning("Could not find camera/mic toggle buttons. Bot may show test pattern.")

