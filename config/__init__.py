"""
Configuration module for the Meeting Bot.
"""

from .settings import (
    Settings,
    settings,
    EmailProvider,
    TranscriptionProvider,
    MeetingPlatform,
    GmailSettings,
    TranscriptionSettings,
    AudioSettings,
    SchedulerSettings,
    BackendSettings,
)
from .logger import logger, get_logger, setup_logging

__all__ = [
    "Settings",
    "settings",
    "EmailProvider",
    "TranscriptionProvider",
    "MeetingPlatform",
    "GmailSettings",
    "TranscriptionSettings",
    "AudioSettings",
    "SchedulerSettings",
    "BackendSettings",
    "logger",
    "get_logger",
    "setup_logging",
]
