"""
Configuration module for the Meeting Bot.
"""

from .settings import (
    Settings,
    settings,
    MeetingPlatform,
    BotSettings,
    RecordingSettings,
)
from .logger import logger, get_logger, setup_logging

__all__ = [
    "Settings",
    "settings",
    "MeetingPlatform",
    "BotSettings",
    "RecordingSettings",
    "logger",
    "get_logger",
    "setup_logging",
]
