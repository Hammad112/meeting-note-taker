"""
Data models for speaker detection and tracking.
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime


@dataclass
class SpeakingSegment:
    """
    Represents a continuous speaking segment by a participant.
    Used for speaker diarization (who spoke when).
    """
    participant_id: str
    display_name: str
    start_time: int  # Unix timestamp in milliseconds
    end_time: int  # Unix timestamp in milliseconds
    start_meeting_time: float  # Seconds since meeting start
    end_meeting_time: float  # Seconds since meeting start
    duration: float  # Duration in seconds
    confidence: Literal["high", "medium", "low"] = "medium"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "participant_id": self.participant_id,
            "display_name": self.display_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_meeting_time": round(self.start_meeting_time, 2),
            "end_meeting_time": round(self.end_meeting_time, 2),
            "duration": round(self.duration, 2),
            "confidence": self.confidence
        }


@dataclass
class ParticipantEvent:
    """
    Represents a participant event (join, leave, mute, unmute).
    """
    participant_id: str
    display_name: str
    event_type: Literal["join", "leave", "mute", "unmute"]
    timestamp: int  # Unix timestamp in milliseconds
    meeting_timestamp: float  # Seconds since meeting start
    platform: str = "teams"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "participant_id": self.participant_id,
            "display_name": self.display_name,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "meeting_timestamp": round(self.meeting_timestamp, 2),
            "platform": self.platform
        }


@dataclass
class ParticipantIdentity:
    """
    Represents a participant's identity information.
    """
    participant_id: str
    display_name: str
    platform: str = "teams"
    first_seen_at: int = 0  # Unix timestamp in milliseconds
    last_seen_at: int = 0  # Unix timestamp in milliseconds
    left_at: Optional[int] = None  # Unix timestamp when participant left
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "participant_id": self.participant_id,
            "display_name": self.display_name,
            "platform": self.platform,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "left_at": self.left_at
        }


@dataclass
class ActiveSpeakingSession:
    """
    Tracks an active speaking session (internal use).
    """
    participant_id: str
    display_name: str
    start_time: int  # Unix timestamp in milliseconds
    start_meeting_time: float  # Seconds since meeting start
    last_seen_time: int  # Unix timestamp in milliseconds
    confidence: Literal["high", "medium", "low"] = "medium"


@dataclass
class ParticipantState:
    """
    Tracks current participant state for change detection.
    """
    participant_id: str
    display_name: str
    is_muted: bool = False
    is_present: bool = True
    last_updated: int = 0  # Unix timestamp in milliseconds
