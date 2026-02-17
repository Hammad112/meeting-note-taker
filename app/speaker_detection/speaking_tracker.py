"""
Speaking Tracker for MS Teams

Tracks active speakers with timestamps using DOM polling.
Separate from caption logic - used for speaker diarization.

Based on TypeScript reference: example/speaking-tracker.ts
"""

import asyncio
import time
import re
from typing import Optional
from datetime import datetime
from playwright.async_api import Page, ElementHandle

from app.config import get_logger
from .models import (
    SpeakingSegment,
    ParticipantEvent,
    ParticipantIdentity,
    ActiveSpeakingSession,
    ParticipantState,
)

logger = get_logger("speaking_tracker")


# Teams-specific selectors for speaking detection
TEAMS_SELECTORS = {
    "speaking_indicators": [
        '[data-tid="voice-level-stream-outline"].vdi-frame-occlusion',
        '.vdi-frame-occlusion[data-tid="voice-level-stream-outline"]',
        '[data-is-speaking="true"]',
        '[data-is-dominant-speaker="true"]',
    ],
    "video_tiles": '[data-stream-type="Video"][data-tid]',
    "exclude_patterns": [
        "call-screen-wrapper",
        "calling-screen",
        "ts-calling-screen",
        "app-container",
        "modern-stage-wrapper",
        "stage-layouts-renderer",
        "stage-layout",
        "only-videos-wrapper",
        "MixedStage-wrapper",
        "participant-avatar",
        "avatar-image-container",
        "calling-roster",
        "roster",
        "attendeesInMeeting",
        "roster-participant",
        "voice-level-stream-outline",
        "arrow-navigator",
        "announcing-region",
        "unmuted",
        "muted",
        "message-list",
        "chat-pane",
        "control-bar",
    ],
}


class SpeakingTracker:
    """
    Tracks active speakers in MS Teams meetings using DOM polling.
    
    Features:
    - Detects speaking via visual indicators (animated border)
    - Tracks speaking segments with start/end timestamps
    - Records participant join/leave/mute/unmute events
    - Exports data for speaker diarization
    """
    
    def __init__(
        self,
        page: Page,
        speaking_gap_threshold_ms: int = 1500,
        participant_poll_interval_ms: int = 2000,
        verbose_logging: bool = False,
    ):
        self.page = page
        self.speaking_gap_threshold_ms = speaking_gap_threshold_ms
        self.participant_poll_interval_ms = participant_poll_interval_ms
        self.verbose_logging = verbose_logging
        
        # State
        self.start_time: int = 0  # Meeting start timestamp in ms
        self.is_running: bool = False
        
        # Speaking segments
        self.speaking_segments: list[SpeakingSegment] = []
        self.active_speakers: dict[str, ActiveSpeakingSession] = {}
        
        # Participant events
        self.participant_events: list[ParticipantEvent] = []
        self.participant_states: dict[str, ParticipantState] = {}
        
        # Participants registry
        self.participants: dict[str, ParticipantIdentity] = {}
        self.display_name_to_id: dict[str, str] = {}
        
        # Tasks
        self._speaking_task: Optional[asyncio.Task] = None
        self._participant_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start tracking speakers."""
        self.start_time = int(time.time() * 1000)
        self.is_running = True
        
        logger.info("🎙️ SpeakingTracker started for Teams")
        
        # Initial participant scan
        await self._scan_participants()
        
        # Start polling tasks
        self._speaking_task = asyncio.create_task(self._speaking_polling_loop())
        self._participant_task = asyncio.create_task(self._participant_polling_loop())
        self._cleanup_task = asyncio.create_task(self._segment_cleanup_loop())
    
    async def stop(self) -> dict:
        """
        Stop tracking and return all collected data.
        
        Returns:
            Dictionary containing speaking segments, participant events, and participants
        """
        self.is_running = False
        
        # Cancel tasks
        for task in [self._speaking_task, self._participant_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close any remaining active speakers
        self._close_all_active_speakers()
        
        # Mark remaining participants as left
        self._mark_all_participants_left()
        
        total_speaking_time = sum(seg.duration for seg in self.speaking_segments)
        
        logger.info(
            f"🎙️ SpeakingTracker stopped. "
            f"Segments: {len(self.speaking_segments)}, "
            f"Events: {len(self.participant_events)}, "
            f"Total speaking time: {total_speaking_time:.1f}s"
        )
        
        return self.export_to_json()
    
    def export_to_json(self) -> dict:
        """Export all speaking data to JSON-serializable dictionary."""
        # Build participant ID to name mapping
        participant_id_to_name = {
            p.participant_id: p.display_name 
            for p in self.participants.values()
        }
        
        return {
            "metadata": {
                "tracker_version": "1.0",
                "platform": "teams",
                "start_time": self.start_time,
                "end_time": int(time.time() * 1000),
                "total_speaking_time_seconds": round(
                    sum(seg.duration for seg in self.speaking_segments), 2
                ),
            },
            "speaking_segments": [seg.to_dict() for seg in self.speaking_segments],
            "participant_events": [evt.to_dict() for evt in self.participant_events],
            "participants": [p.to_dict() for p in self.participants.values()],
            "participant_id_to_name": participant_id_to_name,
            "export_timestamp": datetime.now().isoformat(),
        }
    
    # =========================================================================
    # Polling Loops
    # =========================================================================
    
    async def _speaking_polling_loop(self) -> None:
        """Poll for active speakers every 100ms."""
        while self.is_running:
            try:
                await self._detect_teams_speaker()
            except Exception as e:
                if self.verbose_logging:
                    logger.debug(f"Speaking poll error: {e}")
            await asyncio.sleep(0.1)  # 100ms
    
    async def _participant_polling_loop(self) -> None:
        """Poll for participant changes."""
        while self.is_running:
            try:
                await self._scan_participants()
            except Exception as e:
                if self.verbose_logging:
                    logger.debug(f"Participant poll error: {e}")
            await asyncio.sleep(self.participant_poll_interval_ms / 1000)
    
    async def _segment_cleanup_loop(self) -> None:
        """Close speaking segments that have been inactive."""
        while self.is_running:
            try:
                now = int(time.time() * 1000)
                to_close = []
                
                for participant_id, session in self.active_speakers.items():
                    if now - session.last_seen_time > self.speaking_gap_threshold_ms:
                        to_close.append(participant_id)
                
                for participant_id in to_close:
                    self._close_speaking_segment(participant_id)
                    
            except Exception as e:
                if self.verbose_logging:
                    logger.debug(f"Segment cleanup error: {e}")
            await asyncio.sleep(0.5)  # 500ms
    
    # =========================================================================
    # Speaking Detection
    # =========================================================================
    
    async def _detect_teams_speaker(self) -> None:
        """Detect currently speaking participant in Teams."""
        try:
            # Look for speaking indicators
            speaking_indicators = await self.page.query_selector_all(
                '[data-tid="voice-level-stream-outline"].vdi-frame-occlusion'
            )
            
            for indicator in speaking_indicators:
                try:
                    # Find parent video tile
                    video_tile = await indicator.evaluate_handle(
                        '(el) => el.closest(\'[data-stream-type="Video"][data-tid]\')'
                    )
                    
                    tile_element = video_tile.as_element()
                    if not tile_element:
                        continue
                    
                    display_name = await tile_element.get_attribute("data-tid")
                    if not display_name or not display_name.strip():
                        continue
                    
                    clean_name = self._clean_display_name(display_name.strip())
                    participant_id = f"video-tile-{clean_name.replace(' ', '-').lower()}"
                    
                    if not self._is_valid_participant_id(participant_id):
                        continue
                    
                    # Register and open speaking segment
                    self._register_participant(participant_id, clean_name)
                    self._open_speaking_segment(participant_id, clean_name, "high")
                    
                    return  # Only track one speaker at a time
                    
                except Exception as e:
                    if self.verbose_logging:
                        logger.debug(f"Error processing indicator: {e}")
                        
        except Exception as e:
            if self.verbose_logging:
                logger.debug(f"Teams speaker detection error: {e}")
    
    # =========================================================================
    # Participant Scanning
    # =========================================================================
    
    async def _scan_participants(self) -> None:
        """Scan for participant changes (join/leave/mute)."""
        now = int(time.time() * 1000)
        meeting_time = (now - self.start_time) / 1000
        current_participant_ids: set[str] = set()
        
        try:
            video_tiles = await self.page.query_selector_all(
                TEAMS_SELECTORS["video_tiles"]
            )
            
            for tile in video_tiles:
                tid = await tile.get_attribute("data-tid")
                if not tid or not tid.strip():
                    continue
                
                display_name = self._clean_display_name(tid.strip())
                if self._should_exclude(tid):
                    continue
                
                participant_id = f"video-tile-{display_name.replace(' ', '-').lower()}"
                if not self._is_valid_participant_id(participant_id):
                    continue
                
                current_participant_ids.add(participant_id)
                
                # Check mute status
                is_muted = await self._check_mute_status(tile)
                
                existing_state = self.participant_states.get(participant_id)
                
                if not existing_state:
                    # NEW participant - JOIN event
                    self._register_participant(participant_id, display_name)
                    self._record_participant_event(
                        participant_id, display_name, "join", now, meeting_time
                    )
                    
                    # Record initial mute state
                    if is_muted:
                        self._record_participant_event(
                            participant_id, display_name, "mute", now, meeting_time
                        )
                    
                    self.participant_states[participant_id] = ParticipantState(
                        participant_id=participant_id,
                        display_name=display_name,
                        is_muted=is_muted,
                        is_present=True,
                        last_updated=now,
                    )
                else:
                    # Existing participant - check for changes
                    
                    # Mute change
                    if existing_state.is_muted != is_muted:
                        event_type = "mute" if is_muted else "unmute"
                        self._record_participant_event(
                            participant_id, display_name, event_type, now, meeting_time
                        )
                        existing_state.is_muted = is_muted
                    
                    # Rejoin after leaving
                    if not existing_state.is_present:
                        self._record_participant_event(
                            participant_id, display_name, "join", now, meeting_time
                        )
                        existing_state.is_present = True
                    
                    existing_state.last_updated = now
            
            # Check for participants who left
            for participant_id, state in self.participant_states.items():
                if state.is_present and participant_id not in current_participant_ids:
                    self._record_participant_event(
                        participant_id, state.display_name, "leave", now, meeting_time
                    )
                    state.is_present = False
                    state.last_updated = now
                    
                    # Update participant record
                    if participant_id in self.participants:
                        self.participants[participant_id].left_at = now
                        
        except Exception as e:
            if self.verbose_logging:
                logger.debug(f"Participant scan error: {e}")
    
    async def _check_mute_status(self, tile: ElementHandle) -> bool:
        """Check if participant is muted by looking at mic icon SVG."""
        try:
            is_muted = await tile.evaluate('''(el) => {
                const svgPaths = el.querySelectorAll("svg path");
                for (const path of svgPaths) {
                    const d = path.getAttribute("d") || "";
                    // Muted icon has diagonal slash patterns
                    if (d.includes("l15 15") || d.includes("2.146 2.854") || d.includes("l-15-15")) {
                        return true;
                    }
                }
                return false;
            }''')
            return bool(is_muted)
        except:
            return False
    
    # =========================================================================
    # Speaking Segment Management
    # =========================================================================
    
    def _open_speaking_segment(
        self, 
        participant_id: str, 
        display_name: str, 
        confidence: str
    ) -> None:
        """Open or update a speaking segment."""
        now = int(time.time() * 1000)
        meeting_time = (now - self.start_time) / 1000
        
        # If already speaking, just update last seen time
        if participant_id in self.active_speakers:
            self.active_speakers[participant_id].last_seen_time = now
            return
        
        # New speaking segment
        session = ActiveSpeakingSession(
            participant_id=participant_id,
            display_name=display_name,
            start_time=now,
            start_meeting_time=meeting_time,
            last_seen_time=now,
            confidence=confidence,
        )
        self.active_speakers[participant_id] = session
        
        logger.info(f"🎤 {display_name} started speaking @ {meeting_time:.1f}s")
    
    def _close_speaking_segment(self, participant_id: str) -> None:
        """Close a speaking segment and add to results."""
        session = self.active_speakers.get(participant_id)
        if not session:
            return
        
        end_time = session.last_seen_time
        end_meeting_time = (end_time - self.start_time) / 1000
        duration = (end_time - session.start_time) / 1000
        
        # Only record if duration >= 0.3 seconds
        if duration >= 0.3:
            segment = SpeakingSegment(
                participant_id=session.participant_id,
                display_name=session.display_name,
                start_time=session.start_time,
                end_time=end_time,
                start_meeting_time=session.start_meeting_time,
                end_meeting_time=end_meeting_time,
                duration=duration,
                confidence=session.confidence,
            )
            self.speaking_segments.append(segment)
            
            logger.info(
                f"🔇 {session.display_name} stopped speaking @ {end_meeting_time:.1f}s "
                f"(duration: {duration:.1f}s)"
            )
        
        del self.active_speakers[participant_id]
    
    def _close_all_active_speakers(self) -> None:
        """Close all active speaking segments."""
        for participant_id in list(self.active_speakers.keys()):
            self._close_speaking_segment(participant_id)
    
    # =========================================================================
    # Participant Event Recording
    # =========================================================================
    
    def _record_participant_event(
        self,
        participant_id: str,
        display_name: str,
        event_type: str,
        timestamp: int,
        meeting_timestamp: float,
    ) -> None:
        """Record a participant event."""
        event = ParticipantEvent(
            participant_id=participant_id,
            display_name=display_name,
            event_type=event_type,
            timestamp=timestamp,
            meeting_timestamp=meeting_timestamp,
            platform="teams",
        )
        self.participant_events.append(event)
        
        emoji = {"join": "➡️", "leave": "⬅️", "mute": "🔇", "unmute": "🔊"}.get(event_type, "📋")
        logger.info(f"{emoji} {display_name} {event_type} @ {meeting_timestamp:.1f}s")
    
    def _mark_all_participants_left(self) -> None:
        """Mark all remaining participants as left."""
        now = int(time.time() * 1000)
        meeting_time = (now - self.start_time) / 1000
        
        for participant_id, state in self.participant_states.items():
            if state.is_present:
                self._record_participant_event(
                    participant_id, state.display_name, "leave", now, meeting_time
                )
                state.is_present = False
    
    # =========================================================================
    # Participant Registry
    # =========================================================================
    
    def _register_participant(self, participant_id: str, display_name: str) -> None:
        """Register a new participant."""
        if participant_id in self.participants:
            # Update last seen
            self.participants[participant_id].last_seen_at = int(time.time() * 1000)
            return
        
        if not self._is_valid_participant_id(participant_id):
            return
        
        if display_name in self.display_name_to_id:
            return
        
        now = int(time.time() * 1000)
        
        self.participants[participant_id] = ParticipantIdentity(
            participant_id=participant_id,
            display_name=display_name,
            platform="teams",
            first_seen_at=now,
            last_seen_at=now,
        )
        self.display_name_to_id[display_name] = participant_id
        
        if self.verbose_logging:
            logger.debug(f"👤 Registered participant: {display_name}")
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _clean_display_name(self, name: str) -> str:
        """Clean display name by removing suffixes."""
        name = re.sub(r'\s*\(You\)$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(Guest\)$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(Organizer\)$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(Presenter\)$', '', name, flags=re.IGNORECASE)
        return name.strip()
    
    def _should_exclude(self, id_str: str) -> bool:
        """Check if element should be excluded based on ID patterns."""
        if not id_str:
            return True
        
        id_lower = id_str.lower()
        for pattern in TEAMS_SELECTORS["exclude_patterns"]:
            if pattern.lower() in id_lower:
                return True
        return False
    
    def _is_valid_participant_id(self, participant_id: str) -> bool:
        """Validate participant ID is legitimate."""
        if not participant_id.startswith("video-tile-"):
            return False
        
        name_part = participant_id[len("video-tile-"):]
        bad_patterns = [
            "stream", "outline", "wrapper", "container", "layout",
            "roster", "button", "control", "menu", "panel", "undefined", "null"
        ]
        
        for pattern in bad_patterns:
            if pattern in name_part:
                return False
        
        return len(name_part) >= 2
    
    # =========================================================================
    # Stats
    # =========================================================================
    
    def get_stats(self) -> dict:
        """Get current tracker statistics."""
        return {
            "is_running": self.is_running,
            "segment_count": len(self.speaking_segments),
            "participant_event_count": len(self.participant_events),
            "participant_count": len(self.participants),
            "active_speaker_count": len(self.active_speakers),
            "total_speaking_time": sum(seg.duration for seg in self.speaking_segments),
        }
