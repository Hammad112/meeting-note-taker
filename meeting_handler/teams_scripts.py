"""
Microsoft Teams-specific DOM selectors and JavaScript for meeting automation.

This module centralizes all Teams UI selectors and JavaScript code for:
- Meeting join flow
- Caption capture
- UI element detection

Note: Teams UI is frequently updated by Microsoft, so selectors may need
periodic maintenance.
"""

# =============================================================================
# DOM SELECTORS
# =============================================================================

TEAMS_SELECTORS = {
    # -------------------------------------------------------------------------
    # Join Flow Selectors
    # -------------------------------------------------------------------------
    
    # "Continue on this browser" link/button (when Teams tries to open desktop app)
    "continue_browser": [
        'text="Continue on this browser"',
        'text="Use web app instead"',
        'a:has-text("Continue on this browser")',
        'button:has-text("Continue on this browser")',
        '[data-tid="joinOnWeb"]',
    ],
    
    # Name input field on pre-join screen
    "name_input": [
        'input[placeholder="Type your name"]',
        'input[placeholder*="Enter your name"]',
        'input[placeholder*="your name"]',
        'input[data-tid="prejoin-display-name-input"]',
        '#prejoin-input-name',
        'input[type="text"]',  # Fallback for light meetings
    ],
    
    # Join button (various states)
    "join_button": [
        'button:has-text("Join now")',
        'button[data-tid="prejoin-join-button"]',
        'button:has-text("Join meeting")',
        '[data-tid="joinButton"]',
        'button.join-btn',  # Light meetings
    ],
    
    # -------------------------------------------------------------------------
    # Light Meetings (teams.live.com) Specific Selectors
    # -------------------------------------------------------------------------
    
    # Camera toggle in light meetings (toggle switch)
    "light_camera_toggle": [
        'button[aria-label*="camera"]',
        'button[aria-label*="Camera"]',
        'button[aria-label*="video"]',
        '[data-tid="toggle-video"]',
        'div[class*="video"] button',
        'button:near(:text("Background filters"))',  # Camera toggle is near this
    ],
    
    # Microphone toggle in light meetings
    "light_mic_toggle": [
        'button[aria-label*="microphone"]',
        'button[aria-label*="Microphone"]',
        'button[aria-label*="Mute"]',
        '[data-tid="toggle-mute"]',
    ],
    
    # -------------------------------------------------------------------------
    # Lobby / Admission Selectors
    # -------------------------------------------------------------------------
    
    # Waiting in lobby message
    "waiting_lobby": [
        'text="Waiting to be let in"',
        'text="Someone in the meeting should let you in soon"',
        '[data-tid="lobby-waiting-text"]',
        'text="Waiting for organizer"',
    ],
    
    # Denied entry / kicked
    "entry_denied": [
        'text="You can\'t join this meeting"',
        'text="Meeting has ended"',
        'text="You were removed from the meeting"',
        '[data-tid="meeting-ended"]',
    ],
    
    # Leave button (indicates we're in the meeting) - includes light meetings
    "leave_button": [
        'button[aria-label*="Leave"]',
        'button[aria-label*="leave"]',
        'button[id*="hangup"]',
        'button[data-tid="hangup-button"]',
        'button:has-text("Leave")',
        '#hangup-button',
        'button[class*="hangup"]',
        'button[class*="leave"]',
        '[data-tid="call-hangup"]',
        'button[aria-label*="Hang up"]',
        'button[aria-label*="End call"]',
    ],
    
    # -------------------------------------------------------------------------
    # Audio/Video Control Selectors
    # -------------------------------------------------------------------------
    
    # Microphone toggle
    "mic_button": [
        'button[aria-label*="Mute"]',
        'button[aria-label*="microphone"]',
        'button[aria-label*="Unmute"]',
        'button[data-tid="toggle-mute"]',
        '#microphone-button',
    ],
    
    # Camera toggle
    "camera_button": [
        'button[aria-label*="camera"]',
        'button[aria-label*="video"]',
        'button[aria-label*="Turn camera"]',
        'button[data-tid="toggle-video"]',
        '#video-button',
    ],
    
    # Mic is ON (need to mute) - look for "Turn off" or "Mute"
    "mic_on_indicator": [
        'button[aria-label*="Turn off microphone"]',
        'button[aria-label*="Mute microphone"]',
        'button[aria-label="Mute"]',
    ],
    
    # Camera is ON (need to turn off)
    "camera_on_indicator": [
        'button[aria-label*="Turn off camera"]',
        'button[aria-label*="Turn camera off"]',
        'button[aria-label*="Stop video"]',
    ],
    
    # Pre-join mic/camera toggles (different from in-meeting controls)
    "prejoin_mic_toggle": [
        'button[data-tid="toggle-mute"]',
        '[data-tid="prejoin-mic-button"]',
        'button[aria-label*="microphone"][aria-pressed]',
    ],
    
    "prejoin_camera_toggle": [
        'button[data-tid="toggle-video"]',
        '[data-tid="prejoin-camera-button"]',
        'button[aria-label*="camera"][aria-pressed]',
    ],
    
    # -------------------------------------------------------------------------
    # Caption / Transcription Selectors
    # -------------------------------------------------------------------------
    
    # "More actions" menu button (three dots) - includes light meetings
    "more_actions": [
        'button[aria-label*="More actions"]',
        'button[aria-label*="More options"]',
        'button[aria-label*="more"]',
        'button[id*="more-button"]',
        'button[data-tid="more-button"]',
        '#callingButtons-showMoreBtn',
        'button[class*="more"]',
        'button[class*="More"]',
        '[data-tid="callingButtons-showMoreBtn"]',
        'button[title*="More"]',
    ],
    
    # Captions toggle in menu - includes light meetings
    "captions_menu_item": [
        'button:has-text("Turn on live captions")',
        'button:has-text("Start captions")',
        'button:has-text("Live captions")',
        'button:has-text("Captions")',
        '[role="menuitem"]:has-text("captions")',
        '[role="menuitem"]:has-text("Captions")',
        '[data-tid="toggle-captions"]',
        '[data-tid="live-captions-button"]',
        'button[aria-label*="captions"]',
        'button[aria-label*="Captions"]',
        'span:has-text("Turn on live captions")',
        'div:has-text("Turn on live captions")',
    ],
    
    # Captions are ON indicator
    "captions_on_indicator": [
        'button:has-text("Turn off live captions")',
        'button:has-text("Stop captions")',
        '[aria-label*="Turn off captions"]',
    ],
    
    # Language and speech settings (alternative path to captions)
    "language_speech_menu": [
        'button:has-text("Language and speech")',
        '[role="menuitem"]:has-text("Language and speech")',
    ],
    
    # Caption container (where captions appear) - includes light meetings
    "caption_container": [
        '[data-tid="closed-captions-renderer"]',
        '.ts-captions-container',
        '[data-tid="captions-renderer"]',
        '.caption-wrapper',
        '[class*="captions-container"]',
        '[class*="caption-container"]',
        '[class*="live-caption"]',
        '[aria-label*="captions"]',
        '[aria-label*="caption"]',
        'div[class*="Captions"]',  # Light meetings
    ],
    
    # Caption text element - includes light meetings
    "caption_text": [
        '[data-tid="closed-caption-text"]',
        '.caption-text',
        '.ts-caption-text',
        '[class*="caption-text"]',
        '[class*="captionText"]',
        '[class*="live-caption"] span',
        'div[class*="Captions"] span',  # Light meetings
    ],
    
    # Speaker name in captions
    "speaker_name": [
        '[data-tid="closed-caption-speaker-name"]',
        '.caption-speaker-name',
        '.ts-caption-speaker',
        '[class*="speaker-name"]',
        '[class*="speakerName"]',
    ],
    
    # -------------------------------------------------------------------------
    # Meeting State Indicators
    # -------------------------------------------------------------------------
    
    # Participant list panel (indicates in-meeting)
    "participant_list": [
        '[data-tid="roster-list"]',
        '#roster-list',
        '[aria-label*="Participants"]',
    ],
    
    # Chat panel
    "chat_panel": [
        '[data-tid="message-pane"]',
        '#chat-pane',
    ],
    
    # Meeting title/header
    "meeting_header": [
        '[data-tid="meeting-title"]',
        '.meeting-title',
    ],
}


# =============================================================================
# JAVASCRIPT CODE
# =============================================================================

# JavaScript to observe Teams captions in real-time (supports light meetings)
# V7: Clean output - only complete sentences, with speaker names
TEAMS_CAPTION_OBSERVER_JS = """
(() => {
    console.log("Teams Caption Observer V7 - Clean Output");
    
    const emittedSet = new Set();
    let captionCount = 0;
    let currentSpeaker = "Participant";
    
    // Track pending (incomplete) captions per element
    const pendingCaptions = new Map();
    const COMPLETE_DELAY_MS = 1200; // Wait 1.2s for sentence to complete
    
    function emitCaption(speaker, text) {
        if (!text || text.length < 3) return;
        
        // Skip UI text
        const lower = text.toLowerCase();
        if (lower.includes('turn on') || lower.includes('live captions') || 
            lower.includes('settings') || lower.includes('more actions') ||
            lower.includes('captions are turned on') || lower === 'mute' ||
            lower === 'leave' || lower === 'share' || lower === 'camera') {
            return;
        }
        
        // Dedupe
        const key = text;
        if (emittedSet.has(key)) return;
        emittedSet.add(key);
        
        captionCount++;
        console.log("[Caption #" + captionCount + "] " + speaker + ": " + text);
        
        if (window.screenAppTranscript) {
            window.screenAppTranscript({
                speaker: speaker,
                text: text,
                timestamp: new Date().toISOString()
            });
        }
    }
    
    function isCompleteSentence(text) {
        // Check if text ends with sentence-ending punctuation
        const trimmed = text.trim();
        return /[.!?]$/.test(trimmed);
    }
    
    function extractSpeakerFromText(text) {
        // Format 1: "Speaker Name: text"
        const colonMatch = text.match(/^([A-Za-z][A-Za-z\\s\\.]{1,30}):\\s*(.+)$/);
        if (colonMatch && colonMatch[2].length > 2) {
            return { speaker: colonMatch[1].trim(), text: colonMatch[2].trim() };
        }
        return null;
    }
    
    function findCurrentSpeaker() {
        // Method 1: Look for speaker name element near captions
        const speakerSelectors = [
            '[class*="speaker" i]',
            '[class*="Speaker"]',
            '[class*="displayName" i]',
            '[class*="participant-name" i]',
            '[data-tid*="speaker" i]'
        ];
        
        for (const sel of speakerSelectors) {
            try {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const name = el.innerText?.trim();
                    if (name && name.length > 1 && name.length < 40 && 
                        /^[A-Za-z]/.test(name) && !/[.!?]/.test(name)) {
                        return name;
                    }
                }
            } catch(e) {}
        }
        
        // Method 2: Look for "is speaking" indicator
        const speaking = document.querySelector('[class*="speaking" i], [aria-label*="speaking"]');
        if (speaking) {
            const name = speaking.innerText?.trim() || 
                        speaking.getAttribute('aria-label')?.replace(/is speaking/i, '').trim();
            if (name && name.length > 1 && name.length < 40) {
                return name;
            }
        }
        
        return null;
    }
    
    function processCaption(elementId, text) {
        if (!text || text.length < 3) return;
        
        // Try to extract speaker from text format
        const parsed = extractSpeakerFromText(text);
        let speaker = currentSpeaker;
        let captionText = text;
        
        if (parsed) {
            speaker = parsed.speaker;
            captionText = parsed.text;
        }
        
        // Clear any existing pending timer for this element
        const pending = pendingCaptions.get(elementId);
        if (pending) {
            clearTimeout(pending.timer);
        }
        
        // If sentence appears complete, emit after short delay
        // If not complete, wait longer for more text
        const isComplete = isCompleteSentence(captionText);
        const delay = isComplete ? 300 : COMPLETE_DELAY_MS;
        
        const timer = setTimeout(() => {
            // Get final text from element
            const el = document.querySelector('[data-caption-id="' + elementId + '"]');
            let finalText = captionText;
            if (el) {
                finalText = el.innerText?.trim() || captionText;
                const reparsed = extractSpeakerFromText(finalText);
                if (reparsed) {
                    speaker = reparsed.speaker;
                    finalText = reparsed.text;
                }
            }
            
            // Only emit if it looks complete (ends with punctuation)
            if (isCompleteSentence(finalText)) {
                emitCaption(speaker, finalText);
            }
            
            pendingCaptions.delete(elementId);
        }, delay);
        
        pendingCaptions.set(elementId, { timer, text: captionText, speaker });
    }
    
    function scanCaptions() {
        // Update current speaker
        const detectedSpeaker = findCurrentSpeaker();
        if (detectedSpeaker) {
            currentSpeaker = detectedSpeaker;
        }
        
        // Find caption elements
        const selectors = [
            '[class*="caption" i]',
            '[class*="Caption"]',
            '[class*="subtitle" i]',
            '[data-tid*="caption" i]',
            '[aria-live="polite"]'
        ];
        
        let elementIdx = 0;
        
        for (const selector of selectors) {
            try {
                const elements = document.querySelectorAll(selector);
                for (const el of elements) {
                    const text = el.innerText?.trim();
                    if (!text || text.length < 3 || text.length > 500) continue;
                    
                    // Skip if it's a button or menu
                    if (el.tagName === 'BUTTON' || el.closest('button')) continue;
                    
                    // Assign ID to track element
                    let elId = el.getAttribute('data-caption-id');
                    if (!elId) {
                        elId = 'cap_' + (elementIdx++);
                        el.setAttribute('data-caption-id', elId);
                    }
                    
                    // Process each line
                    const lines = text.split(/[\\n\\r]+/);
                    for (let i = 0; i < lines.length; i++) {
                        const line = lines[i].trim();
                        if (line.length > 3) {
                            processCaption(elId + '_' + i, line);
                        }
                    }
                }
            } catch(e) {}
        }
    }
    
    // Observe changes
    const observer = new MutationObserver(() => {
        scanCaptions();
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });
    
    // Poll
    setInterval(scanCaptions, 500);
    
    // Initial scan
    setTimeout(scanCaptions, 1000);
    
    console.log("Teams Caption Observer V7 Ready - Only complete sentences");
})();
"""

# JavaScript to check if captions are enabled
TEAMS_CHECK_CAPTIONS_JS = """
(() => {
    // Check for caption container visibility
    const container = document.querySelector('[data-tid="closed-captions-renderer"], .ts-captions-container');
    if (container && container.offsetParent !== null) {
        return { enabled: true, method: 'container_visible' };
    }
    
    // Check for "Turn off captions" button (indicates ON)
    const offButton = document.querySelector('button:has-text("Turn off live captions"), [aria-label*="Turn off captions"]');
    if (offButton) {
        return { enabled: true, method: 'off_button_found' };
    }
    
    // Check for captions toggle state
    const captionToggle = document.querySelector('[data-tid="toggle-captions"], button[aria-label*="captions"]');
    if (captionToggle && captionToggle.getAttribute('aria-pressed') === 'true') {
        return { enabled: true, method: 'toggle_pressed' };
    }
    
    return { enabled: false, method: null };
})();
"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_selectors_for(element_type: str) -> list:
    """
    Get list of selectors for a specific element type.
    
    Args:
        element_type: Key from TEAMS_SELECTORS dict
        
    Returns:
        List of CSS/text selectors to try
    """
    return TEAMS_SELECTORS.get(element_type, [])


def get_first_selector(element_type: str) -> str:
    """
    Get the primary (first) selector for an element type.
    
    Args:
        element_type: Key from TEAMS_SELECTORS dict
        
    Returns:
        Primary selector string
    """
    selectors = TEAMS_SELECTORS.get(element_type, [])
    return selectors[0] if selectors else ""

