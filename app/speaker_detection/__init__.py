"""
Speaker Detection Module

Provides speaking tracker for detecting active speakers in meetings.
"""

from .speaking_tracker import SpeakingTracker
from .models import (
    SpeakingSegment,
    ParticipantEvent,
    ParticipantIdentity,
)

__all__ = [
    "SpeakingTracker",
    "SpeakingSegment",
    "ParticipantEvent",
    "ParticipantIdentity",
]
