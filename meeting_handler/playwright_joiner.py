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
            logger.info(f"Navigating to Teams meeting: {meeting.meeting_url}")
            await page.goto(meeting.meeting_url, wait_until="networkidle")
            logger.info("Teams meeting page loaded")
            
            # Wait for page to stabilize
            await asyncio.sleep(5)
            
            # --- Step 2: Handle "Continue on this browser" prompt ---
            await self._teams_handle_continue_browser(page)
            
            # Wait for pre-join screen to fully load (this is critical!)
            logger.info("Waiting for pre-join screen to load...")
            await asyncio.sleep(8)
            
            # Wait for either name input OR join button to appear
            try:
                await page.wait_for_selector(
                    'input[placeholder*="name"], button:has-text("Join now")',
                    timeout=15000
                )
                logger.info("Pre-join screen detected")
            except:
                logger.warning("Pre-join screen elements not detected, continuing anyway...")
            
            await asyncio.sleep(2)
            
            # --- Step 3: Enter display name ---
            bot_name = meeting.title or settings.bot.teams_bot_name
            name_entered = await self._teams_enter_name(page, bot_name)
            
            if not name_entered:
                # Try again with more wait
                logger.info("Retrying name entry after additional wait...")
                await asyncio.sleep(3)
                await self._teams_enter_name(page, bot_name)
            
            # --- Step 4: Mute microphone and camera before joining ---
            await self._teams_mute_before_join(page)
            
            # Small wait after muting
            await asyncio.sleep(1)
            
            # --- Step 5: Click "Join now" button ---
            join_success = await self._teams_click_join(page)
            if not join_success:
                logger.warning("First join attempt failed, retrying...")
                await asyncio.sleep(2)
                join_success = await self._teams_click_join(page)
            
            # --- Step 6: Wait for admission (lobby handling) ---
            admitted = await self._wait_for_teams_admission(page, timeout=600)
            
            if not admitted:
                logger.error(f"Failed to join Teams meeting: {meeting.title}")
                await context.close()
                if meeting.meeting_url in self.active_contexts:
                    del self.active_contexts[meeting.meeting_url]
                return
            
            logger.info(f"✅ Successfully joined Teams meeting: {meeting.title}")
            
            # --- Step 7: Post-join setup ---
            # First mute attempt (immediately after join)
            await self._teams_ensure_muted(page)
            
            # Enable captions and start transcription
            await self._start_teams_transcription(page, meeting)
            
            # Second mute attempt (after a delay - sometimes controls take time to appear)
            await asyncio.sleep(3)
            logger.info("Performing second mute check...")
            await self._teams_ensure_muted(page)
            
            # --- Step 8: Start monitoring task ---
            asyncio.create_task(self._monitor_teams_meeting(context, page, meeting))
            asyncio.create_task(self._teams_periodic_mute_check(page, meeting))
            logger.info(f"Teams meeting monitoring started for: {meeting.title}")
            
        except Exception as e:
            logger.error(f"Error during Teams join flow: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
            await input_field.wait_for(state="visible", timeout=10000)
            
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
        
        try:
            # Use JavaScript to find and click the camera toggle ONLY if it's ON
            result = await page.evaluate("""
                () => {
                    // Method 1: Find button with camera/video aria-label that indicates ON state
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        // Only match buttons that indicate camera is ON (needs to be turned off)
                        if (label.includes('turn off camera') || label.includes('turn off video') ||
                            label.includes('turn camera off') || label.includes('stop camera') ||
                            label.includes('stop video')) {
                            btn.click();
                            console.log('Clicked camera off button:', label);
                            return 'clicked_off_button';
                        }
                    }
                    
                    // Method 2: Find toggle/switch elements and check aria-checked
                    const toggles = document.querySelectorAll('[role="switch"]');
                    for (let i = 0; i < toggles.length; i++) {
                        const toggle = toggles[i];
                        const parent = toggle.closest('div');
                        const nearVideo = parent && (
                            parent.querySelector('video') ||
                            parent.textContent.toLowerCase().includes('camera') ||
                            parent.textContent.toLowerCase().includes('video') ||
                            parent.textContent.toLowerCase().includes('background')
                        );
                        
                        // First toggle is usually camera in Teams light meetings
                        if (nearVideo || i === 0) {
                            const isOn = toggle.getAttribute('aria-checked') === 'true';
                            if (isOn) {
                                toggle.click();
                                console.log('Clicked camera toggle (was ON)');
                                return 'clicked_toggle_was_on';
                            } else {
                                console.log('Camera toggle already OFF');
                                return 'already_off';
                            }
                        }
                    }
                    
                    // Method 3: Check for video preview (indicates camera is on)
                    const videoPreview = document.querySelector('video');
                    if (videoPreview && videoPreview.srcObject) {
                        // Camera is on, try to find and click any camera-related toggle
                        if (toggles.length > 0) {
                            toggles[0].click();
                            console.log('Clicked first toggle (video preview detected)');
                            return 'clicked_with_video_preview';
                        }
                    }
                    
                    return 'not_found_or_already_off';
                }
            """)
            
            if result.startswith('clicked'):
                logger.info(f"✅ Camera toggle: {result}")
                await asyncio.sleep(0.5)
            elif result == 'already_off':
                logger.info("Camera already OFF")
            else:
                logger.debug("Could not find camera toggle or already off")
                    
        except Exception as e:
            logger.warning(f"Error turning off camera: {e}")
    
    async def _teams_turn_off_mic(self, page: Page) -> None:
        """Turn off microphone in Teams pre-join screen."""
        logger.info("Attempting to turn off microphone...")
        
        try:
            # Use JavaScript to find and click the mic toggle ONLY if it's ON
            result = await page.evaluate("""
                () => {
                    // Method 1: Find button that specifically says "turn off microphone" or "mute"
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        // Only match buttons that indicate mic is ON (needs to be muted)
                        if (label.includes('turn off microphone') || label.includes('mute microphone') ||
                            label === 'mute' || label.includes('turn mic off')) {
                            btn.click();
                            console.log('Clicked mic mute button:', label);
                            return 'clicked_mute_button';
                        }
                    }
                    
                    // Method 2: Find toggle near "Microphone" text and check if ON
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        const text = el.textContent || '';
                        if (text.includes('Microphone') && !text.includes('MacBook') && 
                            el.tagName !== 'SCRIPT' && text.length < 200) {
                            const parent = el.closest('div');
                            if (parent) {
                                const toggle = parent.querySelector('[role="switch"]');
                                if (toggle) {
                                    const isOn = toggle.getAttribute('aria-checked') === 'true';
                                    if (isOn) {
                                        toggle.click();
                                        console.log('Clicked mic toggle near Microphone text (was ON)');
                                        return 'clicked_mic_section_toggle';
                                    } else {
                                        console.log('Mic toggle near text already OFF');
                                        return 'already_off';
                                    }
                                }
                            }
                        }
                    }
                    
                    // Method 3: Find all toggles, mic is usually second in Teams light meeting
                    const toggles = document.querySelectorAll('[role="switch"]');
                    if (toggles.length >= 2) {
                        const micToggle = toggles[1];
                        const isOn = micToggle.getAttribute('aria-checked') === 'true';
                        if (isOn) {
                            micToggle.click();
                            console.log('Clicked second toggle (mic) - was ON');
                            return 'clicked_second_toggle';
                        } else {
                            console.log('Second toggle (mic) already OFF');
                            return 'already_off_second';
                        }
                    }
                    
                    // Method 4: Check if there's only one toggle (maybe combined) - skip
                    if (toggles.length === 1) {
                        console.log('Only one toggle found - skipping (probably camera)');
                        return 'skipped_single_toggle';
                    }
                    
                    return 'not_found';
                }
            """)
            
            if result.startswith('clicked'):
                logger.info(f"✅ Mic toggle: {result}")
                await asyncio.sleep(0.5)
            elif result.startswith('already_off'):
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
        
        while (datetime.now() - start_time).total_seconds() < timeout:
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
            if (datetime.now() - last_status_log).total_seconds() >= 30:
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
    
    async def _teams_ensure_muted(self, page: Page) -> None:
        """
        Ensure microphone and camera are muted while in the meeting.
        Uses aggressive JavaScript-based approach for reliability.
        """
        logger.info("Ensuring muted in Teams meeting (post-join)...")
        
        # Wait a moment for meeting controls to fully load
        await asyncio.sleep(2)
        
        # Method 1: Use JavaScript to find and click mute buttons aggressively
        try:
            result = await page.evaluate("""
                () => {
                    let muted = { mic: false, camera: false };
                    
                    // Find and click mic mute button if mic is on
                    const allButtons = document.querySelectorAll('button');
                    
                    for (const btn of allButtons) {
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const title = (btn.getAttribute('title') || '').toLowerCase();
                        const text = (btn.textContent || '').toLowerCase();
                        
                        // Mic mute - look for buttons indicating mic is ON
                        if ((label.includes('mute') && !label.includes('unmute')) ||
                            label.includes('turn off microphone') ||
                            label.includes('mic is on') ||
                            title.includes('mute') && !title.includes('unmute')) {
                            btn.click();
                            console.log('Clicked mic mute button:', label || title);
                            muted.mic = true;
                        }
                        
                        // Camera off - look for buttons indicating camera is ON
                        if (label.includes('turn off camera') ||
                            label.includes('turn camera off') ||
                            label.includes('stop video') ||
                            label.includes('camera is on') ||
                            (label.includes('video') && label.includes('turn off'))) {
                            btn.click();
                            console.log('Clicked camera off button:', label);
                            muted.camera = true;
                        }
                    }
                    
                    // Also check for toggle switches with aria-pressed="true"
                    const toggles = document.querySelectorAll('[role="switch"][aria-checked="true"], button[aria-pressed="true"]');
                    for (const toggle of toggles) {
                        const label = (toggle.getAttribute('aria-label') || '').toLowerCase();
                        if (label.includes('mic') || label.includes('mute')) {
                            if (!muted.mic) {
                                toggle.click();
                                muted.mic = true;
                                console.log('Clicked mic toggle');
                            }
                        }
                        if (label.includes('camera') || label.includes('video')) {
                            if (!muted.camera) {
                                toggle.click();
                                muted.camera = true;
                                console.log('Clicked camera toggle');
                            }
                        }
                    }
                    
                    return muted;
                }
            """)
            
            if result.get('mic'):
                logger.info("✅ Muted microphone (post-join)")
            if result.get('camera'):
                logger.info("✅ Turned off camera (post-join)")
                
        except Exception as e:
            logger.debug(f"JavaScript mute failed: {e}")
        
        # Method 2: Fallback to Playwright locator approach
        await self._teams_toggle_if_on(page, "mic_on_indicator", "mic_button", "Microphone")
        await self._teams_toggle_if_on(page, "camera_on_indicator", "camera_button", "Camera")
        
        # Method 3: Try keyboard shortcuts as final fallback
        try:
            # Ctrl+Shift+M is often mute shortcut in Teams
            await page.keyboard.press("Control+Shift+M")
            logger.debug("Sent Ctrl+Shift+M (mute shortcut)")
        except:
            pass
    
    async def _teams_periodic_mute_check(self, page: Page, meeting: MeetingDetails) -> None:
        """
        Periodically check and ensure mic/camera stay muted.
        Runs in background during the meeting.
        """
        check_count = 0
        max_checks = 5  # Only check first 5 times (first ~2.5 minutes)
        
        try:
            while check_count < max_checks:
                if page.is_closed():
                    break
                
                await asyncio.sleep(30)  # Check every 30 seconds
                check_count += 1
                
                try:
                    # Quick JavaScript check and mute
                    result = await page.evaluate("""
                        () => {
                            const buttons = document.querySelectorAll('button');
                            let actions = [];
                            
                            for (const btn of buttons) {
                                const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                                
                                // Click mute if mic seems to be on
                                if (label.includes('turn off microphone') || 
                                    (label === 'mute' && !label.includes('unmute')) ||
                                    label.includes('mute microphone')) {
                                    btn.click();
                                    actions.push('muted_mic');
                                }
                                
                                // Click to turn off camera if on
                                if (label.includes('turn off camera') || label.includes('turn camera off')) {
                                    btn.click();
                                    actions.push('disabled_camera');
                                }
                            }
                            
                            return actions;
                        }
                    """)
                    
                    if result and len(result) > 0:
                        logger.info(f"Periodic mute check #{check_count}: {result}")
                    else:
                        logger.debug(f"Periodic mute check #{check_count}: already muted")
                        
                except Exception as e:
                    logger.debug(f"Periodic mute check error: {e}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Periodic mute task ended: {e}")

    async def _enable_teams_captions(self, page: Page) -> bool:
        """
        Enable live captions in Teams meeting.
        
        Returns:
            True if captions were enabled successfully.
        """
        logger.info("Attempting to enable Teams live captions...")
        
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
        
        # Method 1: Try clicking "More actions" menu
        more_actions_selectors = get_selectors_for("more_actions")
        
        for selector in more_actions_selectors:
            try:
                more_btn = page.locator(selector)
                if await more_btn.count() > 0 and await more_btn.first.is_visible(timeout=3000):
                    await more_btn.first.click()
                    logger.info("Opened 'More actions' menu")
                    await asyncio.sleep(1.5)
                    
                    # Look for captions option in menu
                    caption_selectors = get_selectors_for("captions_menu_item")
                    
                    for cap_selector in caption_selectors:
                        try:
                            cap_item = page.locator(cap_selector)
                            if await cap_item.count() > 0 and await cap_item.first.is_visible(timeout=2000):
                                await cap_item.first.click()
                                logger.info("Clicked 'Turn on live captions'")
                                await asyncio.sleep(2)
                                return True
                        except:
                            continue
                    
                    # Try Language and speech submenu
                    lang_selectors = get_selectors_for("language_speech_menu")
                    
                    for lang_selector in lang_selectors:
                        try:
                            lang_item = page.locator(lang_selector)
                            if await lang_item.count() > 0 and await lang_item.first.is_visible(timeout=2000):
                                await lang_item.first.click()
                                logger.info("Opened 'Language and speech' menu")
                                await asyncio.sleep(1)
                                
                                # Now look for captions toggle
                                for cap_selector in caption_selectors:
                                    try:
                                        cap_item = page.locator(cap_selector)
                                        if await cap_item.count() > 0 and await cap_item.first.is_visible(timeout=2000):
                                            await cap_item.first.click()
                                            logger.info("Enabled captions from Language submenu")
                                            return True
                                    except:
                                        continue
                        except:
                            continue
                    
                    # Close menu if nothing worked
                    await page.keyboard.press("Escape")
                    break
            except:
                continue
        
        # Method 2: Try keyboard shortcut (Ctrl+Shift+U in some Teams versions)
        try:
            logger.info("Trying keyboard shortcut for captions...")
            await page.keyboard.press("Control+Shift+U")
            await asyncio.sleep(2)
            
            # Check if it worked
            for selector in container_selectors:
                try:
                    container = page.locator(selector)
                    if await container.count() > 0 and await container.first.is_visible(timeout=1000):
                        logger.info("Captions enabled via keyboard shortcut")
                        return True
                except:
                    continue
        except:
            pass
        
        # Method 3: Try using JavaScript to find and click any caption-related button
        try:
            result = await page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button, [role="menuitem"], [role="button"]');
                    for (const btn of buttons) {
                        const text = (btn.textContent || '').toLowerCase();
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('caption') || text.includes('live caption') ||
                            label.includes('caption') || label.includes('live caption')) {
                            if (!text.includes('turn off') && !text.includes('stop') && !label.includes('turn off')) {
                                btn.click();
                                return 'clicked_caption_button';
                            }
                        }
                    }
                    return 'not_found';
                }
            """)
            if result == 'clicked_caption_button':
                logger.info("Enabled captions via JavaScript button click")
                await asyncio.sleep(2)
                return True
        except:
            pass
        
        logger.warning("Could not enable Teams captions - menu options not found")
        return False
    
    async def _start_teams_transcription(self, page: Page, meeting: MeetingDetails) -> None:
        """
        Start transcription for Teams meeting.
        Enables captions and injects caption observer JavaScript.
        """
        try:
            logger.info("Starting Teams transcription...")
            
            # 1. Start transcription service
            self.transcription_service.start_transcription(meeting.title)
            
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

            # --- 2.5 Ensure Muted in Lobby ---
            # Click buttons to mute if they are active
            logger.info("Ensuring microphone and camera are muted in lobby...")
            await self._ensure_mute(page)

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