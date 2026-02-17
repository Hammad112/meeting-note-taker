"""
Recording Service Module

Provides automatic video+audio and audio-only recording for meetings
using PulseAudio system capture (primary) or browser MediaRecorder API (fallback).
"""

from .recording_service import RecordingService
from .pulse_audio_capture import PulseAudioCapture

__all__ = ["RecordingService", "PulseAudioCapture"]

