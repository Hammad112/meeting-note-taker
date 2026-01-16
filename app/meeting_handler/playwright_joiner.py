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

from app.config import settings, get_logger
from app.models import MeetingDetails, MeetingPlatform
from app.transcription.service import TranscriptionService
from app.storage.s3_service import S3Service
from app.storage.meeting_database import MeetingDatabase
from .teams_scripts import (
    TEAMS_SELECTORS,
    TEAMS_CAPTION_OBSERVER_JS,
    TEAMS_CHECK_CAPTIONS_JS,
    get_selectors_for,
)
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
        
        # S3 and database services
        self.s3_service = S3Service()
        self.meeting_database = MeetingDatabase()
        
        # Debug screenshot counter for naming
        self._screenshot_counter = 0

    @property
    def is_running(self) -> bool:
        """Return True if the browser is currently available."""
        return self._browser is not None
    
    async def _save_debug_screenshot(self, page: Page, step_name: str) -> None:
        """
        Save a debug screenshot and HTML snapshot for a specific step.
        
        Args:
            page: Playwright page to capture
            step_name: Descriptive name for this step (e.g., "teams_page_loaded")
        """
        # DEBUG SCREENSHOTS DISABLED - Uncomment to enable
        return
        
        try:
            # Create screenshots directory if it doesn't exist
            screenshot_dir = Path("logs/screenshots")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate timestamp and filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._screenshot_counter += 1
            counter_str = f"{self._screenshot_counter:02d}"
            
            base_filename = f"{timestamp}_{counter_str}_{step_name}"
            png_path = screenshot_dir / f"{base_filename}.png"
            html_path = screenshot_dir / f"{base_filename}.html"
            
            # Take screenshot
            await page.screenshot(path=str(png_path), full_page=True)
            logger.info(f"📸 Screenshot saved: {png_path.name}")
            
            # Save HTML content
            html_content = await page.content()
            html_path.write_text(html_content, encoding='utf-8')
            logger.info(f"💾 HTML saved: {html_path.name}")
            
        except Exception as e:
            logger.warning(f"Failed to save debug screenshot for {step_name}: {e}")

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
        8. Monitor meeting state
        """
        # Create isolated browser context for this meeting
        context = await self._new_context()
        self.active_contexts[meeting.meeting_url] = context
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
            await page.goto(web_url, wait_until="networkidle")
            logger.info("Teams meeting page loaded")
            
            # Wait for page to stabilize
            await asyncio.sleep(2)
            
            # 📸 Screenshot: Page loaded
            await self._save_debug_screenshot(page, "teams_page_loaded")
            
            # --- Step 2: Handle "Continue on this browser" prompt ---
            await self._teams_handle_continue_browser(page)
            
            # 📸 Screenshot: After handling continue browser
            await self._save_debug_screenshot(page, "after_continue_browser")
            
            # --- Step 3: Handle permission dialog early (before name entry) ---
            # This dialog often appears right after continue browser click
            await self._handle_teams_permission_dialog(page)
            
            # Wait for pre-join screen to fully load
            logger.info("Waiting for pre-join screen to load...")
            await asyncio.sleep(3)
            
            # 📸 Screenshot: Pre-join screen
            await self._save_debug_screenshot(page, "pre_join_screen")
            
            # Wait for either name input OR join button to appear
            try:
                await page.wait_for_selector(
                    'input[placeholder*="name"], button:has-text("Join now")',
                    timeout=8000
                )
                logger.info("Pre-join screen detected")
            except:
                logger.warning("Pre-join screen elements not detected, continuing anyway...")
            
            await asyncio.sleep(2)
            
            # --- Step 4: Enter display name ---
            bot_name = meeting.title or settings.bot.teams_bot_name
            name_entered = await self._teams_enter_name(page, bot_name)
            
            if not name_entered:
                # Try again with more wait
                logger.info("Retrying name entry after additional wait...")
                await asyncio.sleep(1)
                await self._teams_enter_name(page, bot_name)
            
            # 📸 Screenshot: After name entry
            await self._save_debug_screenshot(page, "after_name_entry")
            
            # --- Step 5: Mute microphone and camera before joining ---
            await self._teams_mute_before_join(page)
            
            # 📸 Screenshot: After mute
            await self._save_debug_screenshot(page, "after_mute_setup")
            
            # Small wait after muting
            await asyncio.sleep(1)
            
            # 📸 Screenshot: Before clicking join
            await self._save_debug_screenshot(page, "before_clicking_join")
            
            # --- Step 6: Click "Join now" button ---
            join_success = await self._teams_click_join(page)
            if not join_success:
                logger.warning("First join attempt failed, retrying...")
                await asyncio.sleep(2)
                join_success = await self._teams_click_join(page)
            
            # 📸 Screenshot: After clicking join
            await asyncio.sleep(2)
            await self._save_debug_screenshot(page, "after_clicking_join")
            
            # --- Step 7: Wait for admission (lobby handling) ---
            admitted = await self._wait_for_teams_admission(page, timeout=600)
            
            if not admitted:
                logger.error(f"Failed to join Teams meeting: {meeting.title}")
                # 📸 Screenshot: Admission failed
                await self._save_debug_screenshot(page, "admission_failed")
                await context.close()
                if meeting.meeting_url in self.active_contexts:
                    del self.active_contexts[meeting.meeting_url]
                return
            
            logger.info(f"✅ Successfully joined Teams meeting: {meeting.title}")
            
            # 📸 Screenshot: Successfully joined
            await self._save_debug_screenshot(page, "successfully_joined")
            
            # --- Step 7: Post-join setup ---
            # Post-join mute check (removed as per user request to allow manual control)
            
            # Enable captions and start transcription
            await self._start_teams_transcription(page, meeting)
            
            # 📸 Screenshot: After starting transcription
            await self._save_debug_screenshot(page, "after_transcription_start")
            
            # --- Step 8: Start monitoring task ---
            asyncio.create_task(self._monitor_teams_meeting(context, page, meeting))
            logger.info(f"Teams meeting monitoring started for: {meeting.title}")
            
        except Exception as e:
            logger.error(f"Error during Teams join flow: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 📸 Screenshot: Error state
            try:
                await self._save_debug_screenshot(page, "teams_join_error")
            except:
                pass
            
            await context.close()
            if meeting.meeting_url in self.active_contexts:
                del self.active_contexts[meeting.meeting_url]
    
    async def _teams_handle_continue_browser(self, page: Page) -> bool:
        """
        Handle the "Continue on this browser" prompt that appears when Teams 
        tries to open the desktop app.
        
        Returns:
            True if clicked successfully or prompt not found.
        """
        logger.info("Checking for 'Continue on this browser' prompt...")
        
        # 📸 Screenshot: Before continue click attempt
        await self._save_debug_screenshot(page, "before_continue_click")
        
        selectors = get_selectors_for("continue_browser")
        
        for selector in selectors:
            try:
                element = page.locator(selector)
                if await element.count() > 0:
                    first_visible = element.first
                    if await first_visible.is_visible(timeout=3000):
                        await first_visible.click()
                        logger.info(f"Clicked 'Continue on this browser' using: {selector}")
                        await asyncio.sleep(2)
                        # 📸 Screenshot: After continue click
                        await self._save_debug_screenshot(page, "after_continue_click")
                        return True
            except PlaywrightTimeoutError:
                continue
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        # Also try clicking by text content with flexible matching
        try:
            for text in ["Continue on this browser", "Use web app instead", "Join on the web"]:
                btn = page.get_by_text(text, exact=False)
                if await btn.count() > 0 and await btn.first.is_visible(timeout=2000):
                    await btn.first.click()
                    logger.info(f"Clicked '{text}' button")
                    await asyncio.sleep(2)
                    return True
        except:
            pass
        
        logger.info("No 'Continue on browser' prompt found (may already be on web version)")
        return True
    
    async def _teams_enter_name(self, page: Page, bot_name: str) -> bool:
        """
        Enter the bot's display name in the pre-join screen.
        
        Args:
            page: Playwright page
            bot_name: Name to display in the meeting
            
        Returns:
            True if name was entered successfully.
        """
        logger.info(f"Looking for name input field to enter: {bot_name}")
        
        # Method 1: Wait for and use the placeholder-based input (most reliable)
        try:
            # Wait for the input to be available
            input_field = page.locator('input[placeholder="Type your name"]')
            await input_field.wait_for(state="visible", timeout=5000)
            
            # Click to focus
            await input_field.click()
            await asyncio.sleep(0.5)
            
            # Clear and type (using keyboard for reliability)
            await input_field.fill("")
            await page.keyboard.type(bot_name, delay=50)
            
            logger.info(f"✅ Entered bot name: {bot_name}")
            return True
        except Exception as e:
            logger.debug(f"Method 1 (placeholder) failed: {e}")
        
        # Method 2: Try different placeholder variations
        for placeholder in ["Type your name", "Enter your name", "Your name", "name"]:
            try:
                input_field = page.get_by_placeholder(placeholder, exact=False)
                if await input_field.count() > 0:
                    await input_field.first.click()
                    await asyncio.sleep(0.5)
                    await input_field.first.fill("")
                    await page.keyboard.type(bot_name, delay=50)
                    logger.info(f"✅ Entered bot name via placeholder '{placeholder}': {bot_name}")
                    return True
            except:
                continue
        
        # Method 3: Find any text input on the page
        try:
            # Look for visible input fields
            inputs = page.locator('input[type="text"], input:not([type])')
            count = await inputs.count()
            logger.debug(f"Found {count} text input(s) on page")
            
            for i in range(count):
                try:
                    inp = inputs.nth(i)
                    if await inp.is_visible(timeout=1000):
                        await inp.click()
                        await asyncio.sleep(0.5)
                        await inp.fill("")
                        await page.keyboard.type(bot_name, delay=50)
                        logger.info(f"✅ Entered bot name in input #{i}: {bot_name}")
                        return True
                except:
                    continue
        except Exception as e:
            logger.debug(f"Method 3 (any input) failed: {e}")
        
        # Method 4: Use JavaScript to find and fill the input
        try:
            result = await page.evaluate(f"""
                () => {{
                    const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
                    for (const input of inputs) {{
                        if (input.placeholder && input.placeholder.toLowerCase().includes('name')) {{
                            input.focus();
                            input.value = '{bot_name}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    // Fallback: fill first visible text input
                    for (const input of inputs) {{
                        if (input.offsetParent !== null) {{
                            input.focus();
                            input.value = '{bot_name}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }}
            """)
            if result:
                logger.info(f"✅ Entered bot name via JavaScript: {bot_name}")
                return True
        except Exception as e:
            logger.debug(f"Method 4 (JavaScript) failed: {e}")
        
        logger.warning("❌ Could not find name input field")
        return False
    
    async def _teams_mute_before_join(self, page: Page) -> None:
        """
        Ensure microphone and camera are OFF before joining the meeting.
        Teams pre-join screen has toggle buttons for mic/camera.
        Handles both regular Teams and light meetings UI.
        """
        logger.info("Ensuring microphone and camera are muted before joining...")
        
        # For light meetings (teams.live.com), the toggles are switch-style
        # Camera toggle is near the video preview
        # Mic toggle is in the audio settings panel
        
        # --- Turn off Camera ---
        await self._teams_turn_off_camera(page)
        
        # --- Turn off Microphone ---
        await self._teams_turn_off_mic(page)
        
        await asyncio.sleep(1)
    
    async def _teams_turn_off_camera(self, page: Page) -> None:
        """Turn off camera in Teams pre-join screen."""
        logger.info("Attempting to turn off camera...")
        
        # 📸 Screenshot: Before camera toggle
        await self._save_debug_screenshot(page, "before_camera_toggle")
        
        try:
            # Use JavaScript to find and click camera toggle/button
            result = await page.evaluate("""
                () => {
                    // First, try to find the specific switch element from your HTML
                    // Look for the switch with title containing "Turn camera off"
                    const cameraSwitches = document.querySelectorAll('[role="switch"][title*="camera"]');
                    
                    for (const switchEl of cameraSwitches) {
                        const title = (switchEl.getAttribute('title') || '').toLowerCase();
                        const checked = switchEl.getAttribute('checked') !== null || 
                                        switchEl.getAttribute('aria-checked') === 'true';
                        
                        // If switch exists and is checked (camera ON), click it
                        if (checked && title.includes('camera')) {
                            switchEl.click();
                            return 'clicked_camera_switch';
                        }
                        
                        // If switch exists but not checked (camera OFF)
                        if (!checked && title.includes('camera')) {
                            return 'already_off';
                        }
                    }
                    
                    // Also check the parent container with class "fui-Switch"
                    const switchContainers = document.querySelectorAll('.fui-Switch');
                    for (const container of switchContainers) {
                        const title = (container.getAttribute('title') || '').toLowerCase();
                        if (title.includes('camera')) {
                            // Check if input inside is checked
                            const input = container.querySelector('input[type="checkbox"]');
                            if (input) {
                                const checked = input.checked || input.getAttribute('checked') !== null;
                                if (checked) {
                                    input.click();
                                    return 'clicked_camera_input';
                                } else {
                                    return 'already_off';
                                }
                            }
                        }
                    }
                    
                    // Alternative selectors for camera button
                    const selectors = [
                        'button[data-track-module-name*="video"]',
                        'button[aria-label*="camera"]',
                        'button[aria-label*="video"]',
                        'button[title*="camera"]',
                        'button[title*="video"]',
                        '[data-tid="toggle-video"]',
                        '[data-tid="prejoin-camera-button"]'
                    ];

                    for (const sel of selectors) {
                        const btn = document.querySelector(sel);
                        if (btn && btn.offsetParent !== null) {
                            const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                            const title = (btn.getAttribute('title') || '').toLowerCase();
                            const pressed = btn.getAttribute('aria-pressed') === 'true';

                            // If button indicates already OFF (e.g. label says "Turn on camera")
                            if (label.includes('turn on') || title.includes('turn on')) {
                                return 'already_off';
                            }
                            
                            // If pressed=true on a camera button, it often means it's ON
                            if (pressed && (label.includes('camera') || label.includes('video'))) {
                                btn.click();
                                return 'clicked_selector';
                            }
                            
                            // For the specific data-tid="toggle-video" element
                            if (sel.includes('toggle-video')) {
                                btn.click();
                                return 'clicked_toggle_video';
                            }
                        }
                    }
                    
                    // Try keyboard shortcut as last resort
                    return 'not_found';
                }
            """)
            
            logger.info(f"Camera toggle result: {result}")
            
            if result.startswith('clicked'):
                await asyncio.sleep(0.5)
                # 📸 Screenshot: After camera toggle
                await self._save_debug_screenshot(page, "after_camera_toggle")
            elif result == 'not_found':
                # Try keyboard shortcut Ctrl+Shift+O
                logger.info("Trying keyboard shortcut Ctrl+Shift+O...")
                await page.keyboard.press("Control+Shift+O")
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.warning(f"Error turning off camera: {e}")
            # Fallback to keyboard shortcut
            try:
                await page.keyboard.press("Control+Shift+O")
                await asyncio.sleep(0.5)
            except:
                pass
    
    async def _teams_turn_off_mic(self, page: Page) -> None:
        """Turn off microphone in Teams pre-join screen."""
        logger.info("Attempting to turn off microphone...")
        
        # 📸 Screenshot: Before mic toggle
        await self._save_debug_screenshot(page, "before_mic_toggle")
        
        try:
            # Use JavaScript to find and click the mic toggle
            result = await page.evaluate("""
                () => {
                    // Try to find the mic button using multiple strategies
                    const selectors = [
                        'button[data-track-module-name="muteAudioButton"]',
                        'button[title="Mute mic"]',
                        'button[data-tid="toggle-mute"]',
                        'button[aria-label*="microphone"]',
                        'button[aria-label*="Mute"]',
                        '[data-tid="prejoin-mic-button"]'
                    ];

                    for (const sel of selectors) {
                        const btn = document.querySelector(sel);
                        if (btn && btn.offsetParent !== null) {
                            const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                            const title = (btn.getAttribute('title') || '').toLowerCase();
                            const pressed = btn.getAttribute('aria-pressed') === 'true';
                            const checked = btn.getAttribute('aria-checked') === 'true';

                            // If button says "Unmute" or label indicates it's already muted, stay away
                            if (label.includes('unmute') || title.includes('unmute') || (pressed && label.includes('mute')) || (checked && label.includes('mute'))) {
                                console.log('Mic appears already muted:', sel);
                                return 'already_off';
                            }

                            // If we find "Mute mic" or similar, click it
                            btn.click();
                            console.log('Clicked mic button using:', sel);
                            return 'clicked_' + sel;
                        }
                    }
                   // Method 3: Find any button that says "turn off microphone" or "mute"
                    const buttons = Array.from(document.querySelectorAll('button'));
                    for (const btn of buttons) {
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const title = (btn.getAttribute('title') || '').toLowerCase();
                        const text = (btn.textContent || '').toLowerCase();

                        if (label.includes('mute mic') || title.includes('mute mic') || text.includes('mute mic') || 
                            label.includes('mute microphone') || label === 'mute') {
                            
                            // If it already says "Unmute", it's muted
                            if (label.includes('unmute') || title.includes('unmute') || text.includes('unmute')) {
                                return 'already_off';
                            }
                            
                            btn.click();
                            return 'clicked_mute_button';
                        }
                    }
                    return 'not_found';
                }
            """)
            
            if result.startswith('clicked'):
                logger.info(f"✅ Mic toggle (Method 3): {result}")
                await asyncio.sleep(1)
                # 📸 Screenshot: After mic toggle
                await self._save_debug_screenshot(page, "after_mic_toggle")
                
                # Double check - if it still says "Mute", try again or send shortcut
                check_again = await page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                            const title = (btn.getAttribute('title') || '').toLowerCase();
                            if ((label.includes('mute mic') || title.includes('mute mic')) && 
                                !(label.includes('unmute') || title.includes('unmute'))) {
                                return 'still_unmuted';
                            }
                        }
                        return 'muted_or_not_found';
                    }
                """)
                if check_again == 'still_unmuted':
                    logger.info("Mic still appears unmuted after click, trying Ctrl+Shift+M...")
                    await page.keyboard.press("Control+Shift+M")
                    await asyncio.sleep(0.5)
            elif result == 'already_off':
                logger.info("Mic already OFF")
            else:
                logger.debug(f"Mic toggle result: {result}")
                    
        except Exception as e:
            logger.warning(f"Error turning off mic: {e}")
    
    async def _teams_toggle_if_on(
        self, 
        page: Page, 
        on_indicator_key: str, 
        toggle_key: str, 
        name: str
    ) -> None:
        """
        Toggle a Teams control (mic/camera) if it's currently ON.
        
        Args:
            page: Playwright page
            on_indicator_key: Key in TEAMS_SELECTORS for "is ON" indicator
            toggle_key: Key in TEAMS_SELECTORS for toggle button
            name: Human-readable name for logging
        """
        # Check if currently ON by looking for "Turn off" indicators
        on_selectors = get_selectors_for(on_indicator_key)
        
        for selector in on_selectors:
            try:
                indicator = page.locator(selector)
                if await indicator.count() > 0 and await indicator.first.is_visible(timeout=2000):
                    logger.info(f"{name} appears to be ON, clicking to mute...")
                    await indicator.first.click()
                    await asyncio.sleep(0.5)
                    logger.info(f"{name} toggled OFF")
                    return
            except:
                continue
        
        # Also check aria-pressed state on toggle buttons
        toggle_selectors = get_selectors_for(toggle_key)
        
        for selector in toggle_selectors:
            try:
                toggle = page.locator(selector)
                if await toggle.count() > 0:
                    btn = toggle.first
                    if await btn.is_visible(timeout=2000):
                        # Check aria-pressed="true" means it's ON
                        pressed = await btn.get_attribute("aria-pressed")
                        if pressed == "true":
                            logger.info(f"{name} is ON (aria-pressed=true), clicking to turn off...")
                            await btn.click()
                            await asyncio.sleep(0.5)
                            logger.info(f"{name} toggled OFF")
                            return
            except:
                continue
        
        logger.debug(f"{name} appears to be already OFF or toggle not found")
    
    async def _teams_click_join(self, page: Page) -> bool:
        """
        Click the "Join now" button on Teams pre-join screen.
        
        Returns:
            True if join button was clicked.
        """
        logger.info("Looking for 'Join now' button...")
        
        # Wait a moment for any animations to complete
        await asyncio.sleep(1)
        
        # Method 1: Use JavaScript to find and click (most reliable)
        try:
            result = await page.evaluate("""
                () => {
                    // Find button with "Join now" text
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.textContent.trim().toLowerCase();
                        if (text === 'join now' || text.includes('join now')) {
                            btn.click();
                            return 'clicked';
                        }
                    }
                    
                    // Try other join-related text
                    for (const btn of buttons) {
                        const text = btn.textContent.trim().toLowerCase();
                        if (text === 'join' || text === 'join meeting') {
                            btn.click();
                            return 'clicked_alt';
                        }
                    }
                    
                    return 'not_found';
                }
            """)
            
            if result.startswith('clicked'):
                logger.info(f"✅ Clicked 'Join now' button via JavaScript")
                return True
        except Exception as e:
            logger.debug(f"JavaScript click failed: {e}")
        
        # Method 2: Playwright direct text match
        try:
            btn = page.get_by_role("button", name="Join now")
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()
            logger.info("✅ Clicked 'Join now' button via Playwright")
            return True
        except:
            pass
        
        # Method 3: Try locator with text
        try:
            btn = page.locator('button:has-text("Join now")')
            if await btn.count() > 0 and await btn.first.is_visible(timeout=3000):
                await btn.first.click()
                logger.info("✅ Clicked 'Join now' button (locator)")
                return True
        except:
            pass
        
        # Method 4: Look for any button with "Join" text
        try:
            for text in ["Join now", "Join meeting", "Join"]:
                btn = page.get_by_text(text, exact=True)
                if await btn.count() > 0:
                    # Make sure it's a button or clickable
                    if await btn.first.is_visible(timeout=2000):
                        await btn.first.click()
                        logger.info(f"✅ Clicked '{text}'")
                        return True
        except:
            pass
        
        # Method 5: Find primary styled button (usually Join)
        try:
            result = await page.evaluate("""
                () => {
                    // Look for primary/colored button (Join is usually styled distinctly)
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const style = window.getComputedStyle(btn);
                        const bg = style.backgroundColor;
                        // Primary buttons often have blue/purple background
                        if (bg.includes('rgb(98') || bg.includes('rgb(0, 120') || 
                            bg.includes('#6264a7') || bg.includes('#0078d4') ||
                            btn.className.includes('primary')) {
                            btn.click();
                            return 'clicked_primary';
                        }
                    }
                    return 'not_found';
                }
            """)
            if result == 'clicked_primary':
                logger.info("✅ Clicked primary button (Join)")
                return True
        except:
            pass
        
        logger.warning("❌ Could not find 'Join now' button")
        return False
    
    async def _handle_teams_permission_dialog(self, page: Page) -> bool:
        """
        Handle the Teams browser permission dialog that asks about audio/video.
        
        Dialog text: "Are you sure you don't want audio or video?"
        Button: "Continue without audio or video"
        
        Returns:
            True if dialog was handled or not found (success)
        """
        logger.info("Checking for permission dialog...")
        
        try:
            # Wait a moment for dialog to appear
            await asyncio.sleep(1)
            
            # 📸 Screenshot: Check for permission dialog
            await self._save_debug_screenshot(page, "check_permission_dialog")
            
            # Method 1: Look for "Continue without audio or video" button
            continue_button_texts = [
                "Continue without audio or video",
                "Continue without audio",
                "Continue anyway",
                "Join without audio or video"
            ]
            
            for button_text in continue_button_texts:
                try:
                    # Try exact text match
                    btn = page.get_by_role("button", name=button_text)
                    if await btn.count() > 0:
                        if await btn.first.is_visible(timeout=2000):
                            logger.info(f"Found permission dialog button: '{button_text}'")
                            await btn.first.click()
                            logger.info("✅ Clicked 'Continue without audio or video'")
                            await asyncio.sleep(2)
                            
                            # 📸 Screenshot: After handling dialog
                            await self._save_debug_screenshot(page, "after_permission_dialog")
                            return True
                except Exception as e:
                    logger.debug(f"Method 1 failed for '{button_text}': {e}")
                    continue
            
            # Method 2: Look for button with partial text match
            try:
                btn = page.locator('button:has-text("Continue without")')
                if await btn.count() > 0 and await btn.first.is_visible(timeout=2000):
                    await btn.first.click()
                    logger.info("✅ Clicked continue button (partial match)")
                    await asyncio.sleep(2)
                    await self._save_debug_screenshot(page, "after_permission_dialog")
                    return True
            except:
                pass
            
            # Method 3: Use JavaScript to find and click
            try:
                result = await page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = (btn.textContent || '').toLowerCase();
                            if (text.includes('continue without') || 
                                text.includes('join without') ||
                                text.includes('continue anyway')) {
                                btn.click();
                                return 'clicked_continue';
                            }
                        }
                        return 'not_found';
                    }
                """)
                
                if result == 'clicked_continue':
                    logger.info("✅ Clicked continue button via JavaScript")
                    await asyncio.sleep(2)
                    await self._save_debug_screenshot(page, "after_permission_dialog")
                    return True
            except:
                pass
            
            logger.info("No permission dialog found (or already dismissed)")
            return True
            
        except Exception as e:
            logger.warning(f"Error handling permission dialog: {e}")
            return True  # Don't fail the join process
    
    async def _wait_for_teams_admission(self, page: Page, timeout: int = 600) -> bool:
        """
        Wait for admission to the Teams meeting (handles lobby).
        
        Args:
            page: Playwright page
            timeout: Maximum seconds to wait for admission
            
        Returns:
            True if successfully admitted to meeting.
        """
        logger.info(f"Waiting for Teams meeting admission (timeout: {timeout}s)...")
        
        start_time = datetime.now()
        last_status_log = start_time
        last_screenshot_time = start_time
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            # First, check if permission dialog appeared
            try:
                # Quick check for "Continue without audio or video" button
                continue_btn = page.locator('button:has-text("Continue without")')
                if await continue_btn.count() > 0 and await continue_btn.first.is_visible(timeout=1000):
                    logger.info("⚠️ Permission dialog detected during admission wait!")
                    await self._handle_teams_permission_dialog(page)
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
            
            # Log status periodically (every 30 seconds)
            if (datetime.now() - last_status_log).total_seconds() >= 10:
                elapsed = int((datetime.now() - start_time).total_seconds())
                if in_lobby:
                    logger.info(f"⏳ Still waiting in Teams lobby... ({elapsed}s elapsed)")
                else:
                    logger.info(f"⏳ Waiting for Teams meeting admission... ({elapsed}s elapsed)")
                last_status_log = datetime.now()
                
                # 📸 Screenshot: Periodic lobby/admission status
                await self._save_debug_screenshot(page, f"waiting_admission_{elapsed}s")
            
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
    

    async def _enable_teams_captions(self, page: Page) -> bool:
        """
        Enable live captions in Teams meeting.
        
        Returns:
            True if captions were enabled successfully.
        """
        logger.info("Attempting to enable Teams live captions...")
        
        # 📸 Screenshot: Before caption enable attempt
        await self._save_debug_screenshot(page, "before_caption_enable")
        
        # First check if captions are already on
        on_selectors = get_selectors_for("captions_on_indicator")
        
        for selector in on_selectors:
            try:
                on_indicator = page.locator(selector)
                if await on_indicator.count() > 0 and await on_indicator.first.is_visible(timeout=2000):
                    logger.info("Teams captions are already enabled")
                    return True
            except:
                continue
        
        # Check if caption container is already visible (captions may already be on)
        container_selectors = get_selectors_for("caption_container")
        for selector in container_selectors:
            try:
                container = page.locator(selector)
                if await container.count() > 0 and await container.first.is_visible(timeout=1000):
                    logger.info("Caption container already visible - captions are on")
                    return True
            except:
                continue
        
        # Method 1: Use JavaScript to directly find and click caption button
        try:
            logger.info("Method 1: Searching for caption button with JavaScript...")
            result = await page.evaluate("""
                () => {
                    // Search all interactive elements
                    const elements = document.querySelectorAll('button, [role="menuitem"], [role="button"], [role="menuitemcheckbox"]');
                    
                    for (const el of elements) {
                        const text = (el.textContent || '').toLowerCase();
                        const label = (el.getAttribute('aria-label') || '').toLowerCase();
                        const title = (el.getAttribute('title') || '').toLowerCase();
                        
                        // Look for caption-related keywords
                        const hasCaptionKeyword = 
                            text.includes('live caption') || 
                            text.includes('captions') ||
                            text.includes('subtitle') ||
                            label.includes('live caption') || 
                            label.includes('captions') ||
                            label.includes('subtitle') ||
                            title.includes('live caption') || 
                            title.includes('captions');
                        
                        // Avoid "turn off" buttons (captions already on)
                        const isOffButton = 
                            text.includes('turn off') || 
                            text.includes('stop caption') ||
                            text.includes('hide caption') ||
                            label.includes('turn off') ||
                            title.includes('turn off');
                        
                        if (hasCaptionKeyword && !isOffButton) {
                            // Found a caption button, click it
                            el.click();
                            return {success: true, method: 'direct_button', text: el.textContent};
                        }
                    }
                    return {success: false, method: 'direct_button'};
                }
            """)
            
            if result.get('success'):
                logger.info(f"✅ Enabled captions via direct button: {result.get('text', 'unknown')}")
                await asyncio.sleep(2)
                return True
            else:
                logger.info("Direct caption button not found, trying More menu...")
        except Exception as e:
            logger.warning(f"JavaScript search method failed: {e}")
        
        # Method 2: Try clicking "More actions" menu with force click
        more_actions_selectors = get_selectors_for("more_actions")
        
        for selector in more_actions_selectors:
            try:
                more_btn = page.locator(selector)
                if await more_btn.count() > 0:
                    # Use force click to bypass any overlays
                    await more_btn.first.click(force=True, timeout=3000)
                    logger.info("Opened 'More actions' menu")
                    await asyncio.sleep(2)
                    
                    # Use JavaScript to find caption option in opened menu
                    result = await page.evaluate("""
                        () => {
                            const elements = document.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], button');
                            
                            for (const el of elements) {
                                const text = (el.textContent || '').toLowerCase();
                                const label = (el.getAttribute('aria-label') || '').toLowerCase();
                                
                                if ((text.includes('caption') || label.includes('caption')) && 
                                    !text.includes('turn off') && !label.includes('turn off')) {
                                    
                                    // Check if element is visible
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
                    
                    # Try Language and speech submenu as fallback
                    lang_selectors = get_selectors_for("language_speech_menu")
                    
                    for lang_selector in lang_selectors:
                        try:
                            lang_item = page.locator(lang_selector)
                            if await lang_item.count() > 0 and await lang_item.first.is_visible(timeout=2000):
                                await lang_item.first.click(force=True)
                                logger.info("Opened 'Language and speech' menu")
                                await asyncio.sleep(1.5)
                                
                                # Search for caption toggle in submenu
                                result = await page.evaluate("""
                                    () => {
                                        const elements = document.querySelectorAll('[role="menuitem"], button, [role="menuitemcheckbox"]');
                                        
                                        for (const el of elements) {
                                            const text = (el.textContent || '').toLowerCase();
                                            const label = (el.getAttribute('aria-label') || '').toLowerCase();
                                            
                                            if ((text.includes('caption') || label.includes('caption')) && 
                                                !text.includes('off')) {
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
                                    logger.info(f"✅ Enabled captions from Language submenu: {result.get('found')}")
                                    return True
                        except:
                            continue
                    
                    # Close menu if nothing worked
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                    break
            except:
                continue
        
        # Method 3: Try keyboard shortcut (Ctrl+Shift+U in some Teams versions)
        try:
            logger.info("Method 3: Trying keyboard shortcut Ctrl+Shift+U...")
            await page.keyboard.press("Control+Shift+U")
            await asyncio.sleep(2)
            
            # Check if it worked
            for selector in container_selectors:
                try:
                    container = page.locator(selector)
                    if await container.count() > 0 and await container.first.is_visible(timeout=1000):
                        logger.info("✅ Captions enabled via keyboard shortcut")
                        return True
                except:
                    continue
        except Exception as e:
            logger.warning(f"Keyboard shortcut failed: {e}")
        
        # Method 4: Aggressive search - look in entire DOM for any caption-related element
        try:
            logger.info("Method 4: Aggressive DOM search for caption elements...")
            result = await page.evaluate("""
                () => {
                    // Get all elements with any text content
                    const allElements = document.querySelectorAll('*');
                    const captionElements = [];
                    
                    for (const el of allElements) {
                        const text = (el.textContent || '').toLowerCase();
                        const label = (el.getAttribute('aria-label') || '').toLowerCase();
                        const dataId = (el.getAttribute('data-tid') || '').toLowerCase();
                        
                        // Check for caption-related attributes
                        if (text.includes('caption') || label.includes('caption') || dataId.includes('caption')) {
                            // Must be clickable
                            const tagName = el.tagName.toLowerCase();
                            const role = el.getAttribute('role');
                            
                            if (tagName === 'button' || role === 'button' || role === 'menuitem' || role === 'menuitemcheckbox') {
                                // Avoid "off" buttons
                                if (!text.includes('off') && !label.includes('off')) {
                                    captionElements.push({
                                        tag: tagName,
                                        text: el.textContent.substring(0, 50),
                                        label: label.substring(0, 50),
                                        role: role
                                    });
                                    
                                    // Try to click it
                                    try {
                                        el.click();
                                        return {success: true, clicked: el.textContent.substring(0, 50)};
                                    } catch(e) {
                                        continue;
                                    }
                                }
                            }
                        }
                    }
                    
                    return {success: false, found: captionElements};
                }
            """)
            
            if result.get('success'):
                logger.info(f"✅ Caption enabled via aggressive search: {result.get('clicked')}")
                await asyncio.sleep(2)
                return True
            else:
                found = result.get('found', [])
                if found:
                    logger.warning(f"Found {len(found)} caption-related elements but couldn't click: {found[:3]}")
        except Exception as e:
            logger.error(f"Aggressive search failed: {e}")
        
        logger.warning("Could not enable Teams captions - menu options not found")
        return False
    
    async def _start_teams_transcription(self, page: Page, meeting: MeetingDetails) -> None:
        """
        Start transcription for Teams meeting.
        Enables captions and injects caption observer JavaScript.
        """
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
            captions_enabled = await self._enable_teams_captions(page)
            
            if not captions_enabled:
                logger.warning("Captions not enabled - transcription may not work")
            else:
                # 📸 Screenshot: After enabling captions
                await self._save_debug_screenshot(page, "after_caption_enable")
            
            # 4. Inject caption observer JavaScript
            await page.evaluate(TEAMS_CAPTION_OBSERVER_JS)
            logger.info("Teams caption observer injected")
            
            # 5. Start background task to ensure captions stay enabled
            asyncio.create_task(self._teams_caption_monitor(page))
            
        except Exception as e:
            logger.error(f"Failed to start Teams transcription: {e}")
    
    async def _teams_caption_monitor(self, page: Page) -> None:
        """
        Background task to periodically check if captions are still enabled.
        """
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
                        await self._enable_teams_captions(page)
                        
                except Exception as e:
                    logger.debug(f"Caption monitor check failed: {e}")
                    
        except asyncio.CancelledError:
            logger.debug("Teams caption monitor cancelled")
        except Exception as e:
            logger.error(f"Teams caption monitor error: {e}")
    
    async def _monitor_teams_meeting(
        self, 
        context: BrowserContext, 
        page: Page, 
        meeting: MeetingDetails
    ) -> None:
        """
        Background task to monitor Teams meeting state.
        Handles meeting end detection and cleanup.
        """
        logger.info(f"Monitoring Teams meeting: {meeting.title}")
        
        try:
            while True:
                if page.is_closed():
                    logger.info(f"Teams page closed for: {meeting.title}")
                    break
                
                await asyncio.sleep(30)
                
                # Check for meeting end indicators
                try:
                    # Check if we've been removed/kicked
                    denied_selectors = get_selectors_for("entry_denied")
                    
                    for selector in denied_selectors:
                        try:
                            msg = page.locator(selector)
                            if await msg.count() > 0 and await msg.first.is_visible(timeout=1000):
                                logger.info(f"Meeting ended or was removed: {meeting.title}")
                                meeting.was_kicked = True
                                raise StopIteration()
                        except StopIteration:
                            raise
                        except:
                            continue
                    
                    # Check if Leave button is gone (might indicate meeting ended)
                    leave_selectors = get_selectors_for("leave_button")
                    leave_visible = False
                    
                    for selector in leave_selectors:
                        try:
                            leave_btn = page.locator(selector)
                            if await leave_btn.count() > 0 and await leave_btn.first.is_visible(timeout=1000):
                                leave_visible = True
                                break
                        except:
                            continue
                    
                    if not leave_visible:
                        # Double-check by looking for other in-meeting indicators
                        # Check multiple indicators - light meetings have different UI
                        in_meeting_indicators = [
                            '[data-tid="roster-list"]',
                            '[class*="participant"]',
                            '[class*="Participant"]',
                            'button[aria-label*="Mute"]',
                            'button[aria-label*="microphone"]',
                            '[class*="meeting"]',
                            'video',  # If video element exists, likely still in meeting
                            '[class*="call-controls"]',
                            '[class*="CallControls"]',
                        ]
                        
                        still_in_meeting = False
                        for indicator_sel in in_meeting_indicators:
                            try:
                                indicator = page.locator(indicator_sel)
                                if await indicator.count() > 0:
                                    still_in_meeting = True
                                    logger.debug(f"Still in meeting - found: {indicator_sel}")
                                    break
                            except:
                                continue
                        
                        if not still_in_meeting:
                            logger.info(f"No in-meeting indicators found - meeting may have ended: {meeting.title}")
                            # Wait longer and check again to avoid false positives
                            await asyncio.sleep(10)
                            
                            # Check one more time
                            final_check = False
                            for indicator_sel in in_meeting_indicators[:5]:
                                try:
                                    indicator = page.locator(indicator_sel)
                                    if await indicator.count() > 0:
                                        final_check = True
                                        break
                                except:
                                    continue
                            
                            if not final_check:
                                logger.info(f"Confirmed: meeting appears to have ended: {meeting.title}")
                                break
                            else:
                                logger.debug("False positive - still in meeting after recheck")
                    
                except StopIteration:
                    break
                except Exception as e:
                    logger.debug(f"Monitor check error: {e}")
                    
        except asyncio.CancelledError:
            logger.info(f"Teams meeting monitor cancelled for: {meeting.title}")
        except Exception as e:
            msg = str(e)
            if "Target page, context or browser has been closed" in msg:
                logger.info(f"Teams session closed for: {meeting.title}")
            else:
                logger.error(f"Error monitoring Teams meeting: {e}")
        finally:
            logger.info(f"Closing Teams session for: {meeting.title}")
            self.transcription_service.stop_transcription()
            
            try:
                await context.close()
            except:
                pass
            
            if meeting.meeting_url in self.active_contexts:
                del self.active_contexts[meeting.meeting_url]

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
            
            # Wait for page to stabilize
            await asyncio.sleep(3)
            
            # 📸 Screenshot: Google Meet page loaded
            await self._save_debug_screenshot(page, "gmeet_page_loaded")
            
            # --- 1. Dismiss Device Checks ---
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
                    # 📸 Screenshot: After dismissing device check
                    await self._save_debug_screenshot(page, "gmeet_after_device_dismiss")
            except Exception:
                pass

            # 📸 Screenshot: Before name entry check
            await self._save_debug_screenshot(page, "gmeet_before_name_check")
            
            # --- 2. Auth & Input Name (Guest vs Login) ---
            # --- 2. Auth & Input Name (Guest vs Login) ---
            # Try multiple selectors for the name input
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
                # 📸 Screenshot: After entering name
                await self._save_debug_screenshot(page, "gmeet_after_name_entry")
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
                    # 📸 Screenshot: Login page detected
                    await self._save_debug_screenshot(page, "gmeet_login_page_detected")
                    logger.info("Login page/prompt detected. Attempting auto-login...")
                    if not await self._perform_auto_login(page):
                         logger.error("Auto-login failed or no credentials. Aborting.")
                         # 📸 Screenshot: Login failed
                         await self._save_debug_screenshot(page, "gmeet_login_failed")
                         return
                    # 📸 Screenshot: After successful login
                    await self._save_debug_screenshot(page, "gmeet_after_login")
                else:
                    logger.warning("Could not find name input AND not clearly on login page. Continuing to look for Join buttons...")
                    # 📸 Screenshot: No name input or login detected
                    await self._save_debug_screenshot(page, "gmeet_no_name_or_login")

            # --- 2.5 Ensure Muted in Lobby ---
            # Click buttons to mute if they are active
            logger.info("Ensuring microphone and camera are muted in lobby...")
            # 📸 Screenshot: Before mute check
            await self._save_debug_screenshot(page, "gmeet_before_mute")
            # await self._ensure_mute(page)
            # 📸 Screenshot: After mute check
            await self._save_debug_screenshot(page, "gmeet_after_mute")

            # --- 3. Click Join Action (Ask to Join / Join Now) ---
            # 📸 Screenshot: Before join button search
            await self._save_debug_screenshot(page, "gmeet_before_join_click")
            
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
                        # 📸 Screenshot: After clicking join
                        await self._save_debug_screenshot(page, f"gmeet_after_click_{btn_name.replace(' ', '_').lower()}")
                        join_clicked = True
                        clicked_btn_name = btn_name
                        break
                except: continue
            
            if not join_clicked:
                logger.warning("No 'Join' button found. Check browser.")
                # 📸 Screenshot: No join button found
                await self._save_debug_screenshot(page, "gmeet_no_join_button")
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
            last_screenshot_time = start_time
            admitted = False
            
            # 📸 Screenshot: Start of admission wait
            await self._save_debug_screenshot(page, "gmeet_waiting_admission_start")
            
            while (datetime.now() - start_time).total_seconds() < max_wait_time:
                # Check for success indicator
                leave_btn = page.locator('button[aria-label*="Leave call"]')
                if await leave_btn.count() > 0 and await leave_btn.first.is_visible():
                    logger.info(f"Successfully entered meeting {meeting.title} at {datetime.now()}")
                    # 📸 Screenshot: Successfully admitted
                    await self._save_debug_screenshot(page, "gmeet_successfully_admitted")
                    admitted = True
                    break
                
                # Check for "Asking to join" or "You'll join when someone lets you in"
                # This is just for logging/debugging
                if await page.get_by_text("Asking to be admitted").is_visible() or \
                   await page.get_by_text("You'll join the call when someone lets you in").is_visible():
                     # Just log periodically? No, strict logging.
                     pass 

                # Check if denied? (Optional)
                
                # 📸 Screenshot: Periodic status during wait (every 30 seconds)
                elapsed = (datetime.now() - last_screenshot_time).total_seconds()
                if elapsed >= 30:
                    total_elapsed = int((datetime.now() - start_time).total_seconds())
                    await self._save_debug_screenshot(page, f"gmeet_waiting_admission_{total_elapsed}s")
                    last_screenshot_time = datetime.now()
                
                await asyncio.sleep(2)
            
            if not admitted:
                logger.error("Timed out waiting for meeting admission (10 mins). Aborting.")
                # 📸 Screenshot: Admission timeout
                await self._save_debug_screenshot(page, "gmeet_admission_timeout")
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
            # await self._ensure_mute(page)

            # Start Transcription
            await self._start_transcription(page, meeting)
            
            # 📸 Screenshot: After transcription setup
            await self._save_debug_screenshot(page, "gmeet_after_transcription_setup")

            # --- 6. Lobby Wait & Monitor (Spawn Background Task) ---
            # We spawn a monitoring loop that keeps the context alive until meeting ends
            asyncio.create_task(self._monitor_meeting(context, page, meeting))
            logger.info(f"Meeting {meeting.meeting_id} monitoring started.")

        except Exception as e:
            logger.error(f"Error during join flow: {e}")
            # 📸 Screenshot: Error state
            try:
                await self._save_debug_screenshot(page, "gmeet_join_error")
            except:
                pass
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
            
            # Stop transcription
            self.transcription_service.stop_transcription()
            
            # Export to JSON and upload to S3
            try:
                logger.info("Exporting meeting data to JSON...")
                meeting_data = self.transcription_service.export_to_json()
                
                # Upload to S3 if enabled
                if self.s3_service.is_enabled():
                    s3_path = self.s3_service.upload_meeting_json(meeting_data)
                    if s3_path:
                        # Add to local database
                        self.meeting_database.add_meeting(
                            meeting_url=meeting.meeting_url,
                            s3_path=s3_path,
                            metadata={
                                "meeting_id": meeting.meeting_id,
                                "title": meeting.title,
                                "platform": meeting.platform,
                                "export_timestamp": meeting_data.get("export_timestamp")
                            }
                        )
                        logger.info(f"Successfully exported and uploaded meeting data to S3: {s3_path}")
                    else:
                        logger.warning("S3 upload failed")
                else:
                    logger.info("S3 service not enabled. Saving JSON locally only.")
                    # Save JSON locally as backup
                    import json
                    from pathlib import Path
                    json_dir = Path("transcripts/json")
                    json_dir.mkdir(parents=True, exist_ok=True)
                    json_filename = f"{meeting.meeting_id}_{meeting_data['export_timestamp'].replace(':', '-')}.json"
                    json_path = json_dir / json_filename
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(meeting_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"Meeting data saved locally: {json_path}")
                
                # Reset metadata for next meeting
                self.transcription_service.reset_metadata()
                
            except Exception as export_error:
                logger.error(f"Error exporting meeting data: {export_error}")
            
            # Close context and cleanup
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
            
            # On macOS, Google Meet uses Command (Meta), on Windows/Linux it's Control
            import platform
            modifier = "Meta" if platform.system() == "Darwin" else "Control"
            
            # Helper to toggle if needed
            async def toggle_if_needed(keyword_off: str, shortcut_key: str, name: str):
                try:
                    # Look for a button that says "Turn off ..." which implies it is currently ON
                    btn = page.locator(f'button[aria-label*="{keyword_off}"]')
                    if await btn.count() > 0 and await btn.first.is_visible():
                        shortcut = f"{modifier}+{shortcut_key}"
                        logger.info(f"{name} appears to be ON. Muting via shortcut {shortcut}...")
                        await page.keyboard.press(shortcut)
                        await asyncio.sleep(0.5)
                        # Verify mute worked, if not try clicking
                        if await btn.count() > 0 and await btn.first.is_visible():
                            logger.warning(f"{name} still ON after shortcut, trying click...")
                            await btn.first.click()
                            await asyncio.sleep(0.5)
                    else:
                        logger.info(f"{name} appears to be already OFF (or button not found).")
                except Exception as e:
                    logger.warning(f"Error checking {name} state: {e}")

            await toggle_if_needed("Turn off microphone", "d", "Microphone")
            await toggle_if_needed("Turn off camera", "e", "Camera")

        except Exception as e:
            logger.error(f"Failed to mute audio/video: {e}")

    async def _start_transcription(self, page: Page, meeting: MeetingDetails) -> None:
        """Injects Javascript to capture captions."""
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
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info("Caption check task cancelled.")
        except Exception as e:
            logger.error(f"Fatal error in caption loop: {e}")