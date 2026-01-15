# Microsoft Teams Meeting Support Implementation Plan

## Executive Summary

This document outlines a comprehensive plan to add Microsoft Teams meeting support to the Meeting Bot, enabling it to:
1. Join MS Teams meetings via browser automation
2. Capture real-time transcriptions during meetings
3. Optionally retrieve Teams-generated transcripts after meetings

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Approach Options](#approach-options)
3. [Recommended Approach: Browser Automation](#recommended-approach-browser-automation)
4. [Phase 1: Teams URL Detection & Meeting Join](#phase-1-teams-url-detection--meeting-join)
5. [Phase 2: Real-time Transcription Capture](#phase-2-real-time-transcription-capture)
6. [Phase 3: Post-Meeting Transcript Retrieval (Optional)](#phase-3-post-meeting-transcript-retrieval-optional)
7. [Implementation Timeline](#implementation-timeline)
8. [Technical Specifications](#technical-specifications)
9. [Testing Plan](#testing-plan)
10. [Limitations & Considerations](#limitations--considerations)

---

## Current State Analysis

### What We Already Have

✅ **Outlook Calendar Integration** - Already fetches Teams meetings from Outlook calendar
✅ **Teams URL Detection** - `url_extractor.py` already detects Teams URLs:
```python
# Pattern in url_extractor.py
MeetingPlatform.TEAMS: [
    r'https://teams\.microsoft\.com/l/meetup-join/[^\s<>"\']+',
    r'https://teams\.live\.com/meet/[^\s<>"\']+',
]
```
✅ **Playwright Infrastructure** - Browser automation already working for Google Meet
✅ **Transcription Service** - Generic service ready to save transcripts

### What's Missing

❌ Teams-specific join flow in `playwright_joiner.py`
❌ Teams caption/transcript capture JavaScript
❌ Teams meeting lobby handling
❌ Teams mute/unmute button detection

---

## Approach Options

### Option A: Browser Automation (Recommended) ✅

**How it works:** Bot opens Teams meeting URL in browser, joins as guest, captures live captions.

**Pros:**
- Works with any Teams meeting (internal, external, guest access)
- No special Teams bot registration required
- Similar to existing Google Meet implementation
- Real-time transcription during meeting
- Works with personal Microsoft accounts

**Cons:**
- Requires Teams web client support for captions
- Bot appears as a participant
- Meeting host must admit bot from lobby

### Option B: Microsoft Graph API Transcription

**How it works:** Use Microsoft Graph API to retrieve meeting transcripts after meeting ends.

**Pros:**
- Official Microsoft API
- High-quality transcripts
- No bot presence in meeting

**Cons:**
- **Only works for Work/School accounts** (not personal accounts)
- Requires tenant admin consent for `OnlineMeetingTranscript.Read.All`
- **Transcripts only available AFTER meeting ends**
- Meeting must have recording/transcription enabled by organizer
- Complex application access policy setup required

### Option C: Azure Communication Services Bot

**How it works:** Register as Teams bot, join meetings via Azure Communication Services.

**Pros:**
- Native Teams integration
- Access to real-time media streams
- Professional bot experience

**Cons:**
- Requires Microsoft 365 Developer subscription
- Significant Azure infrastructure setup
- Monthly costs for Azure Communication Services
- Complex bot registration process

---

## Recommended Approach: Browser Automation

Given your current setup with Playwright and the need to support personal Microsoft accounts, **Option A (Browser Automation)** is recommended.

---

## Phase 1: Teams URL Detection & Meeting Join

### Step 1.1: Update `playwright_joiner.py` for Teams

Add Teams-specific join flow alongside existing Google Meet support.

#### Teams Meeting Join Flow:

```
1. Navigate to Teams meeting URL
2. Wait for "Continue on this browser" link (if shown)
3. Click to use web client instead of desktop app
4. Enter name in "Enter your name" field
5. Toggle off microphone and camera
6. Click "Join now" button
7. Wait in lobby until admitted
8. Detect successful join (participant view appears)
```

### Step 1.2: Teams Meeting URL Patterns

```python
# Already in url_extractor.py - verify these patterns
TEAMS_URL_PATTERNS = [
    r'https://teams\.microsoft\.com/l/meetup-join/[^\s<>"\']+',
    r'https://teams\.live\.com/meet/[^\s<>"\']+',
    r'https://teams\.microsoft\.com/meet/[^\s<>"\']+',
]
```

### Step 1.3: Teams Join Implementation

```python
async def _join_teams_meeting(self, context, page: Page, meeting: MeetingDetails) -> None:
    """Join a Microsoft Teams meeting."""
    
    # 1. Navigate to meeting URL
    await page.goto(meeting.meeting_url, wait_until="domcontentloaded")
    
    # 2. Handle "Continue on this browser" prompt
    try:
        continue_browser = page.locator('text="Continue on this browser"')
        if await continue_browser.is_visible(timeout=5000):
            await continue_browser.click()
    except:
        pass
    
    # 3. Wait for join form
    await page.wait_for_selector('input[placeholder*="Enter your name"]', timeout=30000)
    
    # 4. Enter bot name
    name_input = page.locator('input[placeholder*="Enter your name"]')
    await name_input.fill(meeting.title or "Meeting Bot")
    
    # 5. Mute microphone and camera (before joining)
    await self._teams_mute_before_join(page)
    
    # 6. Click "Join now"
    join_button = page.locator('button:has-text("Join now")')
    await join_button.click()
    
    # 7. Wait for admission to meeting
    await self._wait_for_teams_admission(page)
    
    # 8. Post-join setup
    await self._teams_post_join_setup(page, meeting)
```

### Step 1.4: Teams Lobby Handling

```python
async def _wait_for_teams_admission(self, page: Page, timeout: int = 600) -> bool:
    """Wait for admission to Teams meeting."""
    start = datetime.now()
    
    while (datetime.now() - start).total_seconds() < timeout:
        # Check if admitted (participant list or "Leave" button visible)
        leave_btn = page.locator('button[aria-label*="Leave"], button:has-text("Leave")')
        if await leave_btn.is_visible():
            return True
        
        # Check for "Waiting to be admitted" message
        waiting_msg = page.locator('text="Waiting to be let in"')
        if await waiting_msg.is_visible():
            logger.info("Waiting in Teams lobby...")
        
        await asyncio.sleep(2)
    
    return False
```

---

## Phase 2: Real-time Transcription Capture

### Step 2.1: Enable Teams Live Captions

Teams supports live captions that appear in the meeting. The bot needs to:

1. Click the "More actions" menu (...)
2. Select "Turn on live captions"
3. Observe caption DOM elements

### Step 2.2: Teams Caption DOM Structure

Teams captions appear in a specific DOM structure:

```javascript
// Caption container selectors (may vary with Teams updates)
const TEAMS_CAPTION_SELECTORS = {
    captionContainer: '[data-tid="closed-captions-renderer"]',
    captionText: '[data-tid="closed-caption-text"]',
    speakerName: '[data-tid="closed-caption-speaker-name"]',
    // Alternative selectors
    altContainer: '.caption-wrapper',
    altText: '.caption-text',
};
```

### Step 2.3: Caption Observer JavaScript

```javascript
// Teams Caption Observer - inject into page
(() => {
    console.log("Teams Transcription Observer Started");
    
    const processedCaptions = new Set();
    
    const observer = new MutationObserver((mutations) => {
        // Look for caption elements
        const captionElements = document.querySelectorAll(
            '[data-tid="closed-caption-text"], .caption-text'
        );
        
        captionElements.forEach(el => {
            const text = el.innerText?.trim();
            if (!text || processedCaptions.has(text)) return;
            
            processedCaptions.add(text);
            
            // Find speaker name
            let speaker = "Unknown Speaker";
            const speakerEl = el.closest('[data-tid="closed-captions-renderer"]')
                              ?.querySelector('[data-tid="closed-caption-speaker-name"]');
            if (speakerEl) {
                speaker = speakerEl.innerText?.trim() || speaker;
            }
            
            // Send to Python
            window.screenAppTranscript?.({ speaker, text });
        });
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });
    
    // Also check periodically for missed captions
    setInterval(() => {
        const captions = document.querySelectorAll('[data-tid="closed-caption-text"]');
        captions.forEach(el => {
            const text = el.innerText?.trim();
            if (text && !processedCaptions.has(text)) {
                processedCaptions.add(text);
                const parent = el.closest('[data-tid="closed-captions-renderer"]');
                const speaker = parent?.querySelector('[data-tid="closed-caption-speaker-name"]')?.innerText || "Unknown";
                window.screenAppTranscript?.({ speaker, text });
            }
        });
    }, 1000);
})();
```

### Step 2.4: Enable Captions Programmatically

```python
async def _enable_teams_captions(self, page: Page) -> bool:
    """Enable live captions in Teams meeting."""
    try:
        # Click "More actions" button (three dots)
        more_actions = page.locator('button[aria-label*="More actions"], button[id*="more-button"]')
        if await more_actions.is_visible():
            await more_actions.click()
            await asyncio.sleep(0.5)
        
        # Click "Turn on live captions"
        captions_option = page.locator('button:has-text("Turn on live captions")')
        if await captions_option.is_visible():
            await captions_option.click()
            logger.info("Teams captions enabled")
            return True
        
        # Try alternative: Language and speech settings
        lang_option = page.locator('button:has-text("Language and speech")')
        if await lang_option.is_visible():
            await lang_option.click()
            await asyncio.sleep(0.5)
            turn_on = page.locator('button:has-text("Turn on live captions")')
            if await turn_on.is_visible():
                await turn_on.click()
                return True
        
        return False
    except Exception as e:
        logger.warning(f"Failed to enable Teams captions: {e}")
        return False
```

---

## Phase 3: Post-Meeting Transcript Retrieval (Optional)

### For Work/School Accounts Only

If the user has a work/school Microsoft account with appropriate permissions, you can retrieve Teams-generated transcripts after the meeting ends.

### Step 3.1: Required Azure AD Permissions

Add to your app registration:
- `OnlineMeetingTranscript.Read.All` (Application permission)
- Requires **tenant admin consent**

### Step 3.2: Application Access Policy

Tenant admin must create an access policy:

```powershell
# PowerShell command for tenant admin
New-CsApplicationAccessPolicy -Identity "TranscriptPolicy" -AppIds "<YOUR_APP_ID>"
Grant-CsApplicationAccessPolicy -PolicyName "TranscriptPolicy" -Identity "<USER_OBJECT_ID>"
```

### Step 3.3: Retrieve Transcripts via Graph API

```python
async def get_teams_transcript(self, meeting_id: str, user_id: str) -> Optional[str]:
    """Retrieve Teams meeting transcript via Graph API."""
    
    # List transcripts for meeting
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/onlineMeetings/{meeting_id}/transcripts"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {self._access_token}"}
        )
        
        if response.status_code == 200:
            transcripts = response.json().get("value", [])
            
            if transcripts:
                transcript_id = transcripts[0]["id"]
                
                # Get transcript content (VTT format)
                content_url = f"{url}/{transcript_id}/content"
                content_response = await client.get(
                    content_url,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Accept": "text/vtt"
                    }
                )
                
                if content_response.status_code == 200:
                    return content_response.text
        
        return None
```

---

## Implementation Timeline

| Phase | Task | Estimated Time |
|-------|------|---------------|
| **1.1** | Teams URL detection verification | 1 hour |
| **1.2** | Basic Teams join flow | 4 hours |
| **1.3** | Teams lobby handling | 2 hours |
| **1.4** | Teams mute/camera off | 2 hours |
| **2.1** | Caption enable automation | 3 hours |
| **2.2** | Caption observer JavaScript | 4 hours |
| **2.3** | Integration with transcription service | 2 hours |
| **2.4** | Testing & debugging | 4 hours |
| **3.x** | Graph API transcript (optional) | 8 hours |

**Total Core Implementation: ~22 hours**
**Optional Graph API: ~8 hours additional**

---

## Technical Specifications

### File Changes Required

1. **`meeting_handler/playwright_joiner.py`**
   - Add `_join_teams_meeting()` method
   - Add `_teams_mute_before_join()` method
   - Add `_wait_for_teams_admission()` method
   - Add `_enable_teams_captions()` method
   - Add `_start_teams_transcription()` method
   - Update `open_meeting()` to route Teams meetings

2. **`email_service/url_extractor.py`**
   - Verify Teams URL patterns are comprehensive
   - Add any missing Teams URL variants

3. **`config/settings.py`**
   - Add `teams_bot_name` setting
   - Add `teams_caption_language` setting

4. **New File: `meeting_handler/teams_scripts.py`**
   - JavaScript for Teams caption observation
   - Teams DOM selectors (centralized)

### DOM Selectors (Subject to Teams UI Updates)

```python
TEAMS_SELECTORS = {
    # Join flow
    "continue_browser": 'text="Continue on this browser"',
    "name_input": 'input[placeholder*="Enter your name"]',
    "join_button": 'button:has-text("Join now")',
    
    # Lobby
    "waiting_lobby": 'text="Waiting to be let in"',
    "leave_button": 'button[aria-label*="Leave"]',
    
    # Controls
    "mic_button": 'button[aria-label*="Mute"], button[aria-label*="microphone"]',
    "camera_button": 'button[aria-label*="camera"], button[aria-label*="video"]',
    "more_actions": 'button[aria-label*="More actions"]',
    
    # Captions
    "captions_toggle": 'button:has-text("Turn on live captions")',
    "caption_container": '[data-tid="closed-captions-renderer"]',
    "caption_text": '[data-tid="closed-caption-text"]',
    "speaker_name": '[data-tid="closed-caption-speaker-name"]',
}
```

---

## Testing Plan

### Test Cases

1. **Basic Join Test**
   - Join Teams meeting as guest
   - Verify bot appears in participant list
   - Verify mute status (mic/camera off)

2. **Lobby Admission Test**
   - Join meeting requiring admission
   - Wait in lobby
   - Verify admission detection

3. **Caption Capture Test**
   - Enable captions
   - Speak in meeting
   - Verify transcript capture

4. **Meeting Leave Test**
   - Leave meeting gracefully
   - Verify transcript saved

5. **Error Handling Tests**
   - Invalid meeting URL
   - Meeting expired
   - Denied entry
   - Network interruption

### Test Meeting Setup

Create test meetings at:
- https://outlook.office.com/calendar
- Schedule meeting with Teams link
- Set lobby to "Everyone" for testing

---

## Limitations & Considerations

### Known Limitations

1. **Caption Language**: Teams captions work best in English. Multi-language support may require configuration.

2. **Guest Access**: Some organizations disable guest access. Bot may not be able to join external meetings.

3. **UI Changes**: Microsoft frequently updates Teams UI. Selectors may need periodic maintenance.

4. **Admission Required**: Unlike Google Meet anonymous join, Teams often requires lobby admission.

5. **Browser Compatibility**: Teams web works best in Edge/Chrome. Firefox support is limited.

### Security Considerations

1. Bot joins as a visible participant - meeting attendees will see "Meeting Bot" in the list

2. Transcript capture requires meeting host to allow captions

3. No way to join meetings "invisibly" - this is a security feature, not a limitation

### Personal vs Work Accounts

| Feature | Personal Account | Work/School Account |
|---------|-----------------|---------------------|
| Browser Join | ✅ Yes | ✅ Yes |
| Live Captions | ✅ Yes (limited) | ✅ Yes (full) |
| Post-Meeting Transcript | ❌ No | ✅ With admin consent |
| Recording Access | ❌ No | ✅ With permissions |

---

## Next Steps

1. **Approve this plan** - Review and confirm approach
2. **Phase 1 Implementation** - Start with basic Teams join flow
3. **Phase 2 Implementation** - Add caption capture
4. **Testing** - End-to-end testing with real Teams meetings
5. **Phase 3 (Optional)** - Add Graph API transcript retrieval for work accounts

---

## Quick Start Commands

After implementation, test Teams support:

```bash
# Start the bot
python run.py

# Create a Teams meeting in Outlook calendar
# Bot will detect and join automatically

# Or use the API to join manually
curl -X POST http://localhost:8888/meetings/join \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Teams Meeting",
    "meeting_url": "https://teams.microsoft.com/l/meetup-join/...",
    "platform": "teams"
  }'
```

---

*Last Updated: January 15, 2026*
