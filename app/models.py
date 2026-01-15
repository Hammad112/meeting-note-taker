"""
Data models for meeting information.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class MeetingPlatform(str, Enum):
    """Supported meeting platforms."""
    TEAMS = "teams"
    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"
    UNKNOWN = "unknown"


class MeetingSource(str, Enum):
    """Source of the meeting invite."""
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    CALENDAR_API = "calendar_api"
    MANUAL = "manual"


@dataclass
class MeetingDetails:
    """
    Represents a meeting with all its details.
    """
    meeting_id: str
    title: str
    start_time: datetime
    end_time: datetime
    meeting_url: str
    platform: MeetingPlatform
    source: MeetingSource
    
    # Optional fields
    organizer: Optional[str] = None
    organizer_email: Optional[str] = None
    attendees: List[str] = field(default_factory=list)
    description: Optional[str] = None
    location: Optional[str] = None
    
    # Tracking fields
    is_scheduled: bool = False
    is_joined: bool = False
    is_completed: bool = False
    was_kicked: bool = False
    rejoin_attempts: int = 0
    max_rejoin_attempts: int = 3
    
    # Raw data for debugging
    raw_event_id: Optional[str] = None
    
    def __hash__(self) -> int:
        """Hash based on meeting URL and start time for deduplication."""
        return hash((self.meeting_url, self.start_time.isoformat()))
    
    def __eq__(self, other: object) -> bool:
        """Equality based on meeting URL and start time."""
        if not isinstance(other, MeetingDetails):
            return False
        return self.meeting_url == other.meeting_url and self.start_time == other.start_time
    
    @property
    def duration_minutes(self) -> int:
        """Get meeting duration in minutes."""
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)
    
    @property
    def is_active(self) -> bool:
        """Check if meeting is currently active."""
        now = datetime.now(self.start_time.tzinfo)
        return self.start_time <= now <= self.end_time
    
    @property
    def has_started(self) -> bool:
        """Check if meeting has started."""
        now = datetime.now(self.start_time.tzinfo)
        return now >= self.start_time
    
    @property
    def has_ended(self) -> bool:
        """Check if meeting has ended."""
        now = datetime.now(self.start_time.tzinfo)
        return now > self.end_time
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "meeting_url": self.meeting_url,
            "platform": self.platform.value,
            "source": self.source.value,
            "organizer": self.organizer,
            "organizer_email": self.organizer_email,
            "attendees": self.attendees,
            "description": self.description,
            "location": self.location,
            "duration_minutes": self.duration_minutes,
            "is_scheduled": self.is_scheduled,
            "is_joined": self.is_joined,
            "is_completed": self.is_completed,
            "was_kicked": self.was_kicked,
            "rejoin_attempts": self.rejoin_attempts,
            "max_rejoin_attempts": self.max_rejoin_attempts,
        }


@dataclass
class TranscriptSegment:
    """
    Represents a segment of transcribed text.
    """
    meeting_id: str
    text: str
    timestamp: datetime
    start_offset_seconds: float
    end_offset_seconds: float
    speaker: Optional[str] = None
    confidence: float = 1.0
    is_final: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "meeting_id": self.meeting_id,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "start_offset_seconds": self.start_offset_seconds,
            "end_offset_seconds": self.end_offset_seconds,
            "speaker": self.speaker,
            "confidence": self.confidence,
            "is_final": self.is_final,
        }


@dataclass
class MeetingSession:
    """
    Represents an active meeting session.
    """
    meeting: MeetingDetails
    session_id: str
    started_at: datetime
    transcripts: List[TranscriptSegment] = field(default_factory=list)
    is_recording: bool = False
    is_transcribing: bool = False
    ended_at: Optional[datetime] = None
    
    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.ended_at is None
    
    @property
    def transcript_text(self) -> str:
        """Get full transcript as text."""
        return " ".join(segment.text for segment in self.transcripts)
    
    def add_transcript(self, segment: TranscriptSegment) -> None:
        """Add a transcript segment."""
        self.transcripts.append(segment)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "meeting": self.meeting.to_dict(),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "is_recording": self.is_recording,
            "is_transcribing": self.is_transcribing,
            "transcript_count": len(self.transcripts),
            "is_active": self.is_active,
        }
