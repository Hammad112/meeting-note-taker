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
TEAMS_CAPTION_OBSERVER_JS = """
(() => {
    console.log("Teams Transcription Observer V3 Started");
    
    // Track last emitted text per speaker to avoid duplicates
    const lastEmittedBySpeaker = new Map();
    let captionCounter = 0;
    let currentSpeaker = "Participant";
    
    // Extended selectors for all Teams meeting types including light meetings
    const CAPTION_SELECTORS = {
        // Container selectors (broader matching)
        container: [
            '[data-tid="closed-captions-renderer"]',
            '.ts-captions-container',
            '[data-tid="captions-renderer"]',
            '[class*="captions-container"]',
            '[class*="caption-container"]',
            '[class*="live-caption"]',
            '[class*="Captions"]',
            '[class*="caption-overlay"]',
            '[aria-label*="caption"]',
            '[aria-label*="Caption"]',
            '[aria-live="polite"]'
        ].join(', '),
        // Text element selectors
        text: [
            '[data-tid="closed-caption-text"]',
            '.caption-text',
            '.ts-caption-text',
            '[class*="caption-text"]',
            '[class*="captionText"]',
            '[class*="caption-line"]',
            '[class*="Captions"] span',
            '[class*="caption"] span'
        ].join(', '),
        // Speaker name selectors (expanded)
        speaker: [
            '[data-tid="closed-caption-speaker-name"]',
            '.caption-speaker-name',
            '.ts-caption-speaker',
            '[class*="speaker-name"]',
            '[class*="speakerName"]',
            '[class*="Speaker"]',
            '[class*="caption-speaker"]',
            '[class*="participant-name"]',
            '[class*="displayName"]'
        ].join(', ')
    };
    
    // Debounce settings
    const pendingEmissions = new Map();
    const DEBOUNCE_MS = 800; // Reduced from 1200 for faster capture
    
    function findSpeakerName() {
        // Method 1: Look for speaker name elements
        const speakerEls = document.querySelectorAll(CAPTION_SELECTORS.speaker);
        for (const el of speakerEls) {
            const name = el.innerText?.trim();
            if (name && name.length > 0 && name.length < 100 && !name.includes(':')) {
                return name;
            }
        }
        
        // Method 2: Look in caption rows for speaker pattern
        const captionRows = document.querySelectorAll('[class*="caption"], [data-tid*="caption"]');
        for (const row of captionRows) {
            // Check if row has separate speaker element
            const children = row.children;
            for (const child of children) {
                const text = child.innerText?.trim();
                // Speaker names are usually short and don't have certain patterns
                if (text && text.length > 0 && text.length < 50 && 
                    !text.includes('.') && !text.includes('?') && !text.includes('!') &&
                    child.className && (child.className.includes('speaker') || child.className.includes('name'))) {
                    return text;
                }
            }
        }
        
        // Method 3: Look for participant roster to get current speaker
        const activeParticipant = document.querySelector('[class*="is-speaking"], [class*="isSpeaking"], [aria-label*="speaking"]');
        if (activeParticipant) {
            const name = activeParticipant.innerText?.trim() || 
                        activeParticipant.getAttribute('aria-label')?.replace(' is speaking', '').trim();
            if (name && name.length < 100) {
                return name;
            }
        }
        
        return null;
    }
    
    function findAllCaptionText() {
        let results = [];
        
        // Method 1: Try known containers first
        const containers = document.querySelectorAll(CAPTION_SELECTORS.container);
        
        containers.forEach(container => {
            // Look for text elements inside
            const textElements = container.querySelectorAll(CAPTION_SELECTORS.text);
            
            if (textElements.length > 0) {
                textElements.forEach(el => {
                    const text = el.innerText?.trim();
                    if (text && text.length > 0 && text.length < 500) {
                        results.push({ element: el, container: container, text: text });
                    }
                });
            } else {
                // Get direct text content
                const text = container.innerText?.trim();
                if (text && text.length > 0 && text.length < 500 && 
                    !text.includes('Turn on') && !text.includes('Start') && !text.includes('Settings')) {
                    results.push({ element: container, container: container, text: text });
                }
            }
        });
        
        // Method 2: Fallback - look for any caption-like elements
        if (results.length === 0) {
            const fallbackEls = document.querySelectorAll('[class*="caption"]:not([class*="button"]), [class*="Caption"]:not([class*="Button"])');
            fallbackEls.forEach(el => {
                const text = el.innerText?.trim();
                if (text && text.length > 0 && text.length < 500 && 
                    !text.includes('Turn') && !text.includes('Start') && !text.includes('Live captions')) {
                    results.push({ element: el, container: el, text: text });
                }
            });
        }
        
        return results;
    }
    
    function emitCaption(text, defaultSpeaker) {
        if (!text || text.length === 0) return;
        
        let speaker = defaultSpeaker;
        let captionText = text;
        
        // Try to parse "Speaker: text" or "Speaker - text" format
        const colonMatch = text.match(/^([A-Za-z][A-Za-z\s]{1,30}):\s*(.+)$/);
        const dashMatch = text.match(/^([A-Za-z][A-Za-z\s]{1,30})\s*[-–—]\s*(.+)$/);
        
        if (colonMatch && colonMatch[2].length > 3) {
            speaker = colonMatch[1].trim();
            captionText = colonMatch[2].trim();
        } else if (dashMatch && dashMatch[2].length > 3) {
            speaker = dashMatch[1].trim();
            captionText = dashMatch[2].trim();
        }
        
        // Check if this exact text was just emitted for this speaker
        const lastForSpeaker = lastEmittedBySpeaker.get(speaker) || "";
        if (lastForSpeaker === captionText) return;
        
        // Calculate what's new (incremental caption)
        let textToEmit = captionText;
        if (captionText.startsWith(lastForSpeaker) && lastForSpeaker.length > 0) {
            textToEmit = captionText.substring(lastForSpeaker.length).trim();
        }
        
        if (!textToEmit || textToEmit.length === 0) return;
        
        const timestamp = new Date().toISOString();
        console.log(`[Caption ${++captionCounter}] ${speaker}: ${textToEmit}`);
        
        // Send to Python immediately
        if (window.screenAppTranscript) {
            window.screenAppTranscript({
                speaker: speaker,
                text: textToEmit,
                timestamp: timestamp
            });
        }
        
        // Update last emitted
        lastEmittedBySpeaker.set(speaker, captionText);
    }
    
    function extractCaptions() {
        // Try to get current speaker name
        const detectedSpeaker = findSpeakerName();
        if (detectedSpeaker) {
            currentSpeaker = detectedSpeaker;
        }
        
        const captionItems = findAllCaptionText();
        
        captionItems.forEach((item, index) => {
            const { element, text } = item;
            if (!text) return;
            
            // Create unique key for this element
            const elementKey = element.getAttribute('data-cap-id') || `c${index}`;
            if (!element.getAttribute('data-cap-id')) {
                element.setAttribute('data-cap-id', elementKey);
            }
            
            // Get the last known text for this element
            const pending = pendingEmissions.get(elementKey);
            
            // If text hasn't changed, skip
            if (pending && pending.text === text) return;
            
            // Clear existing timer
            if (pending) {
                clearTimeout(pending.timer);
            }
            
            // Set new debounce timer
            const timer = setTimeout(() => {
                const finalText = element.innerText?.trim();
                if (finalText && finalText.length > 0) {
                    emitCaption(finalText, currentSpeaker);
                }
                pendingEmissions.delete(elementKey);
            }, DEBOUNCE_MS);
            
            pendingEmissions.set(elementKey, { timer, text, speaker: currentSpeaker });
        });
    }
    
    // Create MutationObserver
    const observer = new MutationObserver(() => {
        extractCaptions();
    });
    
    // Observe document
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true
    });
    
    // Poll frequently
    setInterval(extractCaptions, 500); // Every 500ms
    
    // Initial extraction
    extractCaptions();
    
    console.log("Teams Transcription Observer V3 Ready");
    
    // Debug after delay
    setTimeout(() => {
        const found = findAllCaptionText();
        console.log(`Caption scan: ${found.length} element(s) found`);
        found.forEach((f, i) => console.log(`  [${i}] "${f.text.substring(0, 50)}..."`));
    }, 3000);
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

