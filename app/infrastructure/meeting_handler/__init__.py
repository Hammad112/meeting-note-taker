"""
Meeting handler module.

Provides abstractions for joining online meetings using browser automation.
"""

from .playwright_joiner import MeetingJoiner

__all__ = ["MeetingJoiner"]
