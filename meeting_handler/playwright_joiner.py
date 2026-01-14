"""
Playwright-based meeting joiner.

This module is responsible for opening meeting URLs in a real browser using
Playwright. It is intentionally minimal for now and focuses on:

- Launching a persistent Chromium profile (so you stay logged in)
- Opening the meeting URL for Teams / Zoom / Google Meet
- Providing clear logging hooks for future UI automation (clicking Join, etc.)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from config import settings, get_logger
from models import MeetingDetails, MeetingPlatform
from transcription.service import TranscriptionService
import os
from datetime import datetime


logger = get_logger("meeting_joiner")


class MeetingJoiner:
    """
    High-level interface for joining meetings via Playwright.

    Usage pattern:
        joiner = MeetingJoiner()
        await joiner.start()
        await joiner.join_meeting(meeting)
        await joiner.stop()
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

        # Use a persistent user data directory so the user can log in once
        # and re-use their authenticated browser profile.
        self._user_data_dir = Path(".playwright_user_data").resolve()

        # Track active contexts for meetings that are being monitored
        self.active_contexts: dict[str, BrowserContext] = {}

        self.transcription_service = TranscriptionService()

    @property
    def is_running(self) -> bool:
        """Return True if the browser is currently available."""
        return self._browser is not None

    async def start(self) -> None:
        """
        Start Playwright and launch a Chromium browser instance.
        """
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
                "--enable-usermedia-screen-capturing",
                "--allow-http-screen-capture",
                "--auto-accept-this-tab-capture",
                "--use-fake-ui-for-media-stream", # Auto-accept permissions
                "--disable-blink-features=AutomationControlled", # Stealth: Hide navigator.webdriver
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--start-maximized",
                "--disable-infobars",
                "--exclude-switches=enable-automation"
            ]
        )
        logger.info("Playwright meeting joiner started.")

    async def stop(self) -> None:
        """
        Stop Playwright and close the browser.
        """
        logger.info("Stopping Playwright meeting joiner...")

        # Close all active meeting contexts first
        for url, context in list(self.active_contexts.items()):
            logger.info(f"Closing active meeting context for {url}")
            await context.close()
            del self.active_contexts[url]

        try:
            if self._context is not None:
                await self._context.close()
        finally:
            self._context = None

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

    async def join_meeting(self, meeting: MeetingDetails) -> None:
        """
        Join a meeting in the browser.

        This currently opens the meeting URL in a new tab and leaves the rest
        (e.g., clicking the final Join button) to the user. Platform-specific
        automation hooks are in place for future expansion.
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

        # Check for duplicates
        if meeting.meeting_url in self.active_contexts:
            logger.info(f"Meeting '{meeting.title}' ({meeting.meeting_url}) is already active. Skipping duplicate join.")
            return

        logger.info(
            f"Opening meeting in browser: title='{meeting.title}', "
            f"platform='{meeting.platform.value}', url='{meeting.meeting_url}'"
        )

        try:
            if meeting.platform == MeetingPlatform.TEAMS:
                await self._join_teams(meeting)
            elif meeting.platform == MeetingPlatform.ZOOM:
                await self._join_zoom(meeting)
            elif meeting.platform == MeetingPlatform.GOOGLE_MEET:
                await self._join_google_meet(meeting)
            else:
                await self._open_generic(meeting)
        except Exception as exc:
            logger.error(f"Failed to open meeting URL for {meeting.title}: {exc}")

    async def _new_context(self) -> BrowserContext:
        """Create a new browser context with stealth settings."""
        if not self._browser:
            await self.start()
        
        # Real Chrome User Agent (Windows)
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        context = await self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 720}, # Standard viewport
            device_scale_factor=1,
            permissions=["microphone", "camera"], # Pre-grant permissions
            ignore_https_errors=True
        )
        
        # Stealth: clear navigator.webdriver
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Advanced Stealth: usage of init scripts to mock real browser features
        await context.add_init_script("""
            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
            
            // Mock plugins/mime types (often empty in headless/automation)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Pass WebGL checks?
            // (Optional, keeps it simple for now)

            // Mock chrome runtime if missing
            if (!window.chrome) {
                window.chrome = { runtime: {} };
            }
        """)

        return context

    async def _new_page(self) -> Page:
        """Create a new page in a new context (Legacy helper)."""
        if self._browser is None:
             await self.start()
        context = await self._browser.new_context()
        return await context.new_page()

    async def _join_teams(self, meeting: MeetingDetails) -> None:
        # Create isolated context
        context = await self._new_context()
        self.active_contexts[meeting.meeting_url] = context
        page = await context.new_page()
        
        await page.goto(meeting.meeting_url, wait_until="networkidle")
        logger.info("Teams meeting page loaded...")

        # ... (rest of Teams logic same just using 'page') ...
        # Helper to safely click a button by role/name without failing the whole flow
        async def _try_click_button(name_pattern: str, description: str, timeout_ms: int = 8000) -> None:
            try:
                button = page.get_by_role(
                    "button",
                    name=re.compile(name_pattern, re.IGNORECASE),
                )
                await button.wait_for(timeout=timeout_ms)
                await button.click()
                logger.info(f"Clicked Teams button: {description}")
            except PlaywrightTimeoutError:
                logger.debug(f"Teams button not found (timeout): {description}")
            except Exception as exc:
                logger.debug(f"Teams button click skipped ({description}): {exc}")

        # 1) If Microsoft tries to open the desktop app, choose the web experience
        await _try_click_button(r"(use the web app|continue on this browser|continue in this browser)", "Continue on this browser")

        # Give the page a brief moment to transition to the pre-join screen
        await asyncio.sleep(40)

        # 2) Click "Join now" on the pre-join screen, if it appears
        await _try_click_button(r"join now", "Join now")

        logger.info("Teams join flow attempted; verify join state in the browser window.")
        # Monitoring would go here if implemented for Teams

    async def _join_zoom(self, meeting: MeetingDetails) -> None:
        context = await self._browser.new_context(permissions=["microphone", "camera"])
        self.active_contexts[meeting.meeting_url] = context
        page = await context.new_page()
        
        await page.goto(meeting.meeting_url, wait_until="load")
        logger.info("Zoom meeting page loaded. Waiting 10s...")
        await asyncio.sleep(30)
        logger.info("Complete join flow in the browser.")


    async def _join_google_meet(self, meeting: MeetingDetails) -> None:
        """
        Open a Google Meet meeting and attempt to join automatically.
        Uses a robust flow: Guest -> Auto-Login -> Lobby Wait.
        """
        # Create a new isolated context for this meeting
        context = await self._browser.new_context(
            permissions=["microphone", "camera"],
            ignore_https_errors=True
        )
        page = await context.new_page()
        self.active_contexts[meeting.meeting_url] = context # Track session

        try:
            logger.info(f"Navigating to {meeting.meeting_url}...")
            await page.goto(meeting.meeting_url, wait_until="load")
            
            # --- 1. Dismiss Device Checks ---
            # Try to click "Continue without microphone and camera"
            try:
                btn = page.get_by_role('button', name='Continue without microphone and camera')
                if await btn.is_visible(timeout=5000):
                    await btn.click()
                    logger.info("Clicked 'Continue without microphone and camera'")
            except Exception:
                pass

            # --- 2. Auth & Input Name (Guest vs Login) ---
            # Priority: Guest Name Input
            name_input = page.get_by_placeholder("Your name")
            if await name_input.is_visible(timeout=10000):
                bot_name = meeting.title  # Use the bot name from meeting details
                logger.info(f"Guest mode detected. Entering bot name: {bot_name}...")
                await name_input.fill(bot_name)
                # Proceed to click Join
            else:
                # If no guest input, check for login
                if "accounts.google.com" in page.url or await page.get_by_text("Sign in").is_visible():
                    logger.info("Login page detected. Attempting auto-login...")
                    if not await self._perform_auto_login(page):
                         logger.error("Auto-login failed or no credentials. Aborting.")
                         return

            # --- 3. Click Join Action (Ask to Join / Join Now) ---
            join_clicked = False
            clicked_btn_name = ""
            
            # Try clicking buttons
            for btn_name in ["Ask to join", "Join now", "Join"]:
                try:
                    btn = page.get_by_role("button", name=btn_name, exact=True)
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        logger.info(f"Clicked '{btn_name}' button.")
                        join_clicked = True
                        clicked_btn_name = btn_name
                        break
                except: continue
            
            if not join_clicked:
                logger.warning("No 'Join' button found. Check browser.")
                # We continue anyway, maybe it auto-joined?
            else:
                logger.info(f"Join action initiated via '{clicked_btn_name}'...")

            # --- 4. Wait for Admission / Entry ---
            # If we clicked "Ask to join", we are in a waiting state.
            # If we clicked "Join now", we might be in instantly.
            
            # Robust Admission Wait Loop
            # We look for the "Leave call" button as the definitive sign of being IN the meeting.
            # We also check for "Asking to join..." text to log status.
            
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

                # Check if denied? (Optional)
                
                await asyncio.sleep(2)
            
            if not admitted:
                logger.error("Timed out waiting for meeting admission (10 mins). Aborting.")
                # Logic to clean up?
                # For now, let monitor handle close? Or return?
                # Better to return.
                await context.close()
                if meeting.meeting_url in self.active_contexts:
                   del self.active_contexts[meeting.meeting_url]
                return

            # --- 5. Post-Join Setup (Mute & Transcribe) ---
            # Now we are 100% sure we are in.

            # Mute Audio/Video
            await self._ensure_mute(page)

            # Start Transcription
            await self._start_transcription(page, meeting)

            # --- 6. Lobby Wait & Monitor (Spawn Background Task) ---
            # We spawn a monitoring loop that keeps the context alive until meeting ends
            asyncio.create_task(self._monitor_meeting(context, page, meeting))
            logger.info(f"Meeting {meeting.meeting_id} monitoring started.")

        except Exception as e:
            logger.error(f"Error during join flow: {e}")
            await context.close()
            if meeting.meeting_url in self.active_contexts:
                del self.active_contexts[meeting.meeting_url]

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

    async def _monitor_meeting(self, context: BrowserContext, page: Page, meeting: MeetingDetails):
        """BACKGROUND TASK: Keeps the browser open and checks for meeting end."""
        logger.info(f"Monitoring meeting: {meeting.title}")
        try:
            while True:
                if page.is_closed(): break
                await asyncio.sleep(30)
                
                # Check exit conditions
                if await page.get_by_text("You left the call").is_visible():
                     logger.info(f"Meeting ended ('You left the call') at {datetime.now()}.")
                     break
                if await page.get_by_text("Return to home screen").is_visible():
                     logger.info("Meeting ended (Returned to home).")
                     break

        except Exception as e:
            msg = str(e)
            if "Target page, context or browser has been closed" in msg:
                logger.info(f"Meeting session closed for {meeting.title} (Window closed).")
            else:
                logger.error(f"Error monitoring meeting {meeting.title}: {e}")
        finally:
            logger.info(f"Closing session for {meeting.title}")
            await context.close()
            if meeting.meeting_url in self.active_contexts:
                del self.active_contexts[meeting.meeting_url]
            self.transcription_service.stop_transcription()

    async def _open_generic(self, meeting: MeetingDetails) -> None:
        """Fallback: just open the meeting URL in a new tab."""
        page = await self._new_page()
        await page.goto(meeting.meeting_url, wait_until="load")
        logger.info(
            "Generic meeting URL opened. You may need to complete the join flow manually."
        )

    async def _ensure_mute(self, page: Page) -> None:
        """Ensures microphone and camera are muted using keyboard shortcuts."""
        try:
            logger.info("Attempting to mute microphone and camera...")
            # Helper to toggle if needed
            async def toggle_if_needed(keyword_off: str, shortcut: str, name: str):
                try:
                    # Look for a button that says "Turn off ..." which implies it is currently ON
                    # The aria-label usually contains the shortcut too, e.g. "Turn off microphone (ctrl + d)"
                    btn = page.locator(f'button[aria-label*="{keyword_off}"]')
                    if await btn.count() > 0 and await btn.first.is_visible():
                         logger.info(f"{name} appears to be ON. Muting via shortcut {shortcut}...")
                         await page.keyboard.press(shortcut)
                         await asyncio.sleep(1)
                    else:
                        logger.info(f"{name} appears to be already OFF (or button not found).")
                except Exception as e:
                    logger.warning(f"Error checking {name} state: {e}")

            await toggle_if_needed("Turn off microphone", "Control+d", "Microphone")
            await toggle_if_needed("Turn off camera", "Control+e", "Camera")

        except Exception as e:
            logger.error(f"Failed to mute audio/video: {e}")

    async def _start_transcription(self, page: Page, meeting: MeetingDetails) -> None:
        """Injects Javascript to capture captions."""
        try:
            logger.info("Injecting transcription observer...")
            
            # 1. Start service
            self.transcription_service.start_transcription(meeting.title)

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
            js_script_v2 = """
            () => {
                console.log("Transcription Observer V2 Started");
                
                // We will observe the body for new captions appearing
                const observer = new MutationObserver((mutations) => {
                    const captionContainer = document.querySelector('[jsname="dsyhDe"]');
                    if (!captionContainer) return;

                    // The logic here depends on how the DOM updates. 
                    // Usually new <span> or <div> elements are appended.
                    
                    // Let's look for the specific text classes
                    const textElements = captionContainer.querySelectorAll('.TBMuR, .VbkSUe');
                    
                    textElements.forEach(el => {
                        // Check if we already processed this element
                        if (el.dataset.processed === "true") return;
                        
                        const text = el.innerText;
                        if (!text) return;

                        // Try to find speaker info
                        let speaker = "Unknown Speaker";
                        // Heuristic: iterate up to find a container with speaker info
                        let current = el;
                        while(current && current !== captionContainer) {
                             if (current.hasAttribute('data-sender-name')) {
                                 speaker = current.getAttribute('data-sender-name');
                                 break;
                             }
                             // Or check for an element with the user's selector
                             const speakerEl = current.querySelector('[data-speaker-id]'); 
                             if (speakerEl) {
                                 speaker = speakerEl.innerText || speakerEl.getAttribute('data-speaker-id');
                                 break;
                             }
                             current = current.parentElement;
                        }

                        // Mark as processed to avoid duplicates (this is transient, new spans appear for new text usually)
                        el.dataset.processed = "true";
                        
                        window.screenAppTranscript({
                            speaker: speaker,
                            text: text
                        });
                    });
                });
                
                observer.observe(document.body, { childList: true, subtree: true });
            }
            """
            
            await page.evaluate(js_script_v2)
            
            # Attempt to turn on captions if they aren't?
            try:
                # Button often has 'Turn on captions' aria-label
                cc_btn = page.locator('button[aria-label*="Turn on captions"]')
                if await cc_btn.count() > 0 and await cc_btn.first.is_visible():
                     logger.info("Turning on captions...")
                     await cc_btn.first.click()
            except: pass

        except Exception as e:
            logger.error(f"Failed to start transcription logic: {e}")

    async def _ensure_mute(self, page: Page) -> None:
        """Ensures microphone and camera are muted using keyboard shortcuts."""
        try:
            logger.info("Attempting to mute microphone and camera...")
            # Helper to toggle if needed
            async def toggle_if_needed(keyword_off: str, shortcut: str, name: str):
                try:
                    # Look for a button that says "Turn off ..." which implies it is currently ON
                    # The aria-label usually contains the shortcut too, e.g. "Turn off microphone (ctrl + d)"
                    btn = page.locator(f'button[aria-label*="{keyword_off}"]')
                    if await btn.count() > 0 and await btn.first.is_visible():
                         logger.info(f"{name} appears to be ON. Muting via shortcut {shortcut}...")
                         await page.keyboard.press(shortcut)
                         await asyncio.sleep(1)
                    else:
                        logger.info(f"{name} appears to be already OFF (or button not found).")
                except Exception as e:
                    logger.warning(f"Error checking {name} state: {e}")

            await toggle_if_needed("Turn off microphone", "Control+d", "Microphone")
            await toggle_if_needed("Turn off camera", "Control+e", "Camera")

        except Exception as e:
            logger.error(f"Failed to mute audio/video: {e}")

    async def _start_transcription(self, page: Page, meeting: MeetingDetails) -> None:
        """Injects Javascript to capture captions."""
        try:
            logger.info("Injecting transcription observer...")

            # Hook console logs to see JS errors in Python logs
            page.on("console", lambda msg: logger.info(f"BROWSER CONSOLE: {msg.text}"))
            
            # 1. Start service
            self.transcription_service.start_transcription(meeting.title)

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
            # We spawn this so it doesn't block the main join flow (which needs to start the monitor)
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
                        # We can either break (assume they stay on) or continue checking periodically
                        # Breaking is safer to reduce noise, unless user turns them off manually.
                        # Let's break for now.
                        break 

                    # 2. Check if a caption button indicates "Pressed" (Active)
                    selectors = [
                        'button[jsname="r8qRAd"]',
                        'button[aria-label*="Turn on captions"]',
                        'button[aria-label*="captions"]', 
                        'button[icon="cc"]'
                    ]
                    
                    found_button = False
                    captions_already_on = False
                    target_btn = None
                    
                    for sel in selectors:
                        btns = page.locator(sel)
                        count = await btns.count()
                        
                        for i in range(count):
                            btn = btns.nth(i)
                            if not await btn.is_visible():
                                continue
                                
                            found_button = True
                            target_btn = btn
                            
                            is_pressed = await btn.get_attribute("aria-pressed")
                            label = await btn.get_attribute("aria-label") or ""
                            
                            if is_pressed == "true" or "Turn off" in label:
                                captions_already_on = True
                                break
                        
                        if found_button:
                            break
                    
                    if captions_already_on:
                        logger.info("Captions are ON (Button state is pressed/active).")
                        break 

                    # 3. If we found a button but it's OFF, click it
                    if found_button and target_btn:
                        logger.info("Found caption button (currently OFF). Clicking it...")
                        await target_btn.click()
                        await asyncio.sleep(2)
                        
                        is_pressed_now = await target_btn.get_attribute("aria-pressed")
                        if is_pressed_now == "true":
                            logger.info("Successfully enabled captions.")
                            break
                        else:
                            logger.info("Clicked button but state didn't change immediately.")

                    # 4. If NO button found, try "More Options" menu
                    elif not found_button:
                        # Only log this occasionally to avoid spam if it really doesn't exist
                        logger.debug("Direct caption button NOT found. Checking 'More options'...")
                        
                        more_options = page.locator('button[aria-label="More options"]')
                        if await more_options.count() > 0 and await more_options.first.is_visible():
                            await more_options.first.click()
                            await asyncio.sleep(1)
                            
                            menu_item = page.locator('li[role="menuitem"]:has-text("Turn on captions")')
                            if await menu_item.count() > 0 and await menu_item.first.is_visible():
                                logger.info("Found 'Turn on captions' in menu. Clicking...")
                                await menu_item.first.click()
                                await asyncio.sleep(2)
                                break 
                            else:
                                logger.debug("'Turn on captions' not found in menu. Closing menu.")
                                await page.keyboard.press("Escape")
                        else:
                            # 5. Last Resort: Keyboard Shortcut
                            logger.info("Attempting 'c' shortcut as fallback.")
                            await page.keyboard.press("c")
                        
                except Exception as e:
                     logger.warning(f"Error in caption logic: {e}")

                # Wait 30 seconds before next check
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info("Caption check task cancelled.")
        except Exception as e:
            logger.error(f"Fatal error in caption loop: {e}")


        except Exception as e:
            logger.error(f"Failed to start transcription logic: {e}")


