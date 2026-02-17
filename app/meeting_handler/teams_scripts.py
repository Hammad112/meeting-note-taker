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
        'button[data-track-module-name="muteAudioButton"]',
        'button[title="Mute mic"]',
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
# V10: Uses Teams' actual DOM structure - data-tid="author" and data-tid="closed-caption-text"
TEAMS_CAPTION_OBSERVER_JS = """
(() => {
    console.log("Teams Caption Observer V10 - Using DOM Structure");
    
    const emittedSet = new Set();
    let captionCount = 0;
    let currentSpeaker = "Participant";
    let lastSpeakerChangeTime = Date.now();
    
    // Track pending captions
    const pendingCaptions = new Map();
    const COMPLETE_DELAY_MS = 1000;
    const SPEAKER_TIMEOUT_MS = 5000; // Reset to "Participant" if no name seen for 5s
    
    // Known speaker names (learned during session)
    const knownSpeakers = new Set();
    
    function isPersonName(text) {
        // STRICT name detection - must look like "First Last" or "First"
        if (!text) return false;
        
        const trimmed = text.trim();
        
        // Length: 2-30 chars (names are short)
        if (trimmed.length < 2 || trimmed.length > 30) return false;
        
        // Max 3 words (First Middle Last)
        const words = trimmed.split(/\\s+/);
        if (words.length > 3) return false;
        
        // Each word must start with capital, be 2-15 chars, only letters/hyphens
        for (const word of words) {
            if (!/^[A-Z][a-z\\-\\']{1,14}$/.test(word)) return false;
        }
        
        // Must NOT contain common speech words
        const lower = trimmed.toLowerCase();
        const speechWords = [
            'yes', 'no', 'ok', 'okay', 'sure', 'so', 'can', 'you', 'please',
            'the', 'and', 'is', 'are', 'was', 'were', 'have', 'has', 'had',
            'will', 'would', 'could', 'should', 'may', 'might', 'must',
            'what', 'why', 'how', 'when', 'where', 'who', 'which',
            'this', 'that', 'these', 'those', 'here', 'there',
            'not', 'but', 'for', 'with', 'from', 'about', 'into',
            'your', 'my', 'his', 'her', 'its', 'our', 'their',
            'just', 'like', 'know', 'think', 'want', 'need', 'get',
            'let', 'see', 'say', 'tell', 'ask', 'make', 'take',
            'mute', 'unmute', 'leave', 'share', 'camera', 'call',
            'meeting', 'captions', 'joined', 'left', 'unknown'
        ];
        
        for (const word of words) {
            if (speechWords.includes(word.toLowerCase())) return false;
        }
        
        return true;
    }
    
    function emitCaption(speaker, text) {
        if (!text || text.length < 3) return;
        
        // Skip UI/system text
        const lower = text.toLowerCase();
        if (lower.includes('turn on') || lower.includes('live captions') || 
            lower.includes('captions are turned on') || lower.includes('joined the') ||
            lower.includes('left the') || lower.includes('unknown user')) {
            return;
        }
        
        // Dedupe
        if (emittedSet.has(text)) return;
        emittedSet.add(text);
        
        captionCount++;
        console.log("[#" + captionCount + "] " + speaker + ": " + text);
        
        if (window.screenAppTranscript) {
            window.screenAppTranscript({
                speaker: speaker,
                text: text,
                timestamp: new Date().toISOString()
            });
        }
    }
    
    function isCompleteSentence(text) {
        return /[.!?]$/.test(text.trim());
    }
    
    function processLine(line, elementId, lineIndex, allLines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.length < 2) return;
        
        // Check if this line is ONLY a person's name
        if (isPersonName(trimmed)) {
            currentSpeaker = trimmed;
            knownSpeakers.add(trimmed);
            lastSpeakerChangeTime = Date.now();
            console.log("[Speaker detected] " + trimmed);
            return; // Don't emit name as caption
        }
        
        // Check for "Known Name: text" format at START of line
        for (const name of knownSpeakers) {
            if (trimmed.startsWith(name + ':') || trimmed.startsWith(name + ' :')) {
                currentSpeaker = name;
                lastSpeakerChangeTime = Date.now();
                const colonIdx = trimmed.indexOf(':');
                const captionText = trimmed.substring(colonIdx + 1).trim();
                if (captionText.length > 2) {
                    scheduleEmit(elementId, name, captionText);
                }
                return;
            }
        }
        
        // NEW: Check if previous line was a name (Teams shows name on line above caption)
        if (lineIndex > 0) {
            const prevLine = allLines[lineIndex - 1]?.trim();
            if (prevLine && isPersonName(prevLine)) {
                currentSpeaker = prevLine;
                knownSpeakers.add(prevLine);
                lastSpeakerChangeTime = Date.now();
                console.log("[Speaker from prev line] " + prevLine);
            }
        }
        
        // NEW: Check if next line is a name (sometimes name comes after)
        if (lineIndex < allLines.length - 1) {
            const nextLine = allLines[lineIndex + 1]?.trim();
            if (nextLine && isPersonName(nextLine)) {
                // This line is caption, next is name - use next as speaker for future
                knownSpeakers.add(nextLine);
            }
        }
        
        // Regular caption - use current speaker
        scheduleEmit(elementId, currentSpeaker, trimmed);
    }
    
    function scheduleEmit(elementId, speaker, text) {
        const pending = pendingCaptions.get(elementId);
        if (pending) {
            clearTimeout(pending.timer);
        }
        
        // If no speaker name detected recently, use "Participant"
        let finalSpeaker = speaker;
        const timeSinceLastSpeaker = Date.now() - lastSpeakerChangeTime;
        if (timeSinceLastSpeaker > SPEAKER_TIMEOUT_MS && speaker !== "Participant") {
            // Reset to Participant if we haven't seen a name in a while
            finalSpeaker = "Participant";
        }
        
        const isComplete = isCompleteSentence(text);
        const delay = isComplete ? 200 : COMPLETE_DELAY_MS;
        
        const timer = setTimeout(() => {
            if (isCompleteSentence(text)) {
                emitCaption(finalSpeaker, text);
            }
            pendingCaptions.delete(elementId);
        }, delay);
        
        pendingCaptions.set(elementId, { timer, text, speaker: finalSpeaker });
    }
    
    function findSpeakerNearElement(el) {
        // Look for speaker name in sibling or parent elements
        // Teams often puts name in a separate element near the caption
        
        // Check siblings
        const parent = el.parentElement;
        if (parent) {
            const siblings = Array.from(parent.children);
            for (const sibling of siblings) {
                if (sibling === el) continue;
                const text = sibling.innerText?.trim();
                if (text && isPersonName(text)) {
                    return text;
                }
            }
        }
        
        // Check parent's text (might contain name + caption)
        if (parent) {
            const parentText = parent.innerText?.trim();
            if (parentText) {
                const lines = parentText.split(/[\\n\\r]+/);
                for (const line of lines) {
                    if (isPersonName(line.trim())) {
                        return line.trim();
                    }
                }
            }
        }
        
        return null;
    }
    
    function scanCaptions() {
        // PRIMARY METHOD: Use Teams' actual DOM structure
        // Find all caption text elements with data-tid="closed-caption-text"
        const captionTextElements = document.querySelectorAll('[data-tid="closed-caption-text"]');
        
        for (const captionEl of captionTextElements) {
            try {
                // Find the parent ChatMessageCompact container
                const container = captionEl.closest('.fui-ChatMessageCompact');
                if (!container) continue;
                
                // Find the author/speaker name in the same container
                const authorEl = container.querySelector('[data-tid="author"]');
                let speaker = "Participant";
                
                if (authorEl) {
                    const authorText = authorEl.innerText?.trim();
                    if (authorText && authorText.length > 0 && authorText.length < 50) {
                        speaker = authorText;
                        knownSpeakers.add(authorText);
                        currentSpeaker = authorText;
                        lastSpeakerChangeTime = Date.now();
                    }
                }
                
                // Get the caption text
                const captionText = captionEl.innerText?.trim();
                if (!captionText || captionText.length < 2) continue;
                
                // Create unique ID for this caption element
                let captionId = captionEl.getAttribute('data-caption-id');
                if (!captionId) {
                    captionId = 'cap_' + Date.now() + '_' + Math.random();
                    captionEl.setAttribute('data-caption-id', captionId);
                }
                
                // Process this caption
                scheduleEmit(captionId, speaker, captionText);
                
            } catch(e) {
                console.error("Error processing caption:", e);
            }
        }
        
        // FALLBACK: Also check old selectors for compatibility
        const fallbackSelectors = [
            '[class*="caption" i]',
            '[class*="Caption"]',
            '[data-tid*="caption" i]',
            '[aria-live="polite"]'
        ];
        
        let idx = 0;
        
        for (const selector of fallbackSelectors) {
            try {
                const elements = document.querySelectorAll(selector);
                for (const el of elements) {
                    // Skip if already processed as closed-caption-text
                    if (el.hasAttribute('data-tid') && el.getAttribute('data-tid') === 'closed-caption-text') {
                        continue;
                    }
                    if (el.tagName === 'BUTTON' || el.closest('button')) continue;
                    
                    const text = el.innerText?.trim();
                    if (!text || text.length < 2 || text.length > 1000) continue;
                    
                    const lines = text.split(/[\\n\\r]+/);
                    for (let i = 0; i < lines.length; i++) {
                        processLine(lines[i], 'fallback_' + idx + '_' + i, i, lines);
                    }
                    idx++;
                }
            } catch(e) {}
        }
    }
    
    // Observe DOM
    const observer = new MutationObserver(() => {
        scanCaptions();
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });
    
    // Poll
    setInterval(scanCaptions, 400);
    
    // Initial
    setTimeout(scanCaptions, 500);
    
    console.log("Teams Caption Observer V10 Ready - Using data-tid selectors");
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

