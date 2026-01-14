"""
Configuration module for the Meeting Bot.
"""

from .settings import (
    Settings,
    settings,
    EmailProvider,
    AuthMethod,
    TranscriptionProvider,
    MeetingPlatform,
    GmailSettings,
    TranscriptionSettings,
    AudioSettings,
    SchedulerSettings,
    BackendSettings,
    AuthServerSettings,
)
from .logger import logger, get_logger, setup_logging

__all__ = [
    "Settings",
    "settings",
    "EmailProvider",
    "AuthMethod",
    "TranscriptionProvider",
    "MeetingPlatform",
    "GmailSettings",
    "TranscriptionSettings",
    "AudioSettings",
    "SchedulerSettings",
    "BackendSettings",
    "AuthServerSettings",
    "logger",
    "get_logger",
    "setup_logging",
]
