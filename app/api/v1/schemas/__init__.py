"""
API v1 schemas module.
"""

from .meeting import (
    ManualJoinRequest,
    ManualJoinResponse,
    MeetingStatusResponse,
    AuthStatusResponse,
    HealthCheckResponse,
    ErrorResponse,
)
from .auth import (
    OAuthCallbackResponse,
    OAuthStartResponse,
)

__all__ = [
    "ManualJoinRequest",
    "ManualJoinResponse",
    "MeetingStatusResponse",
    "AuthStatusResponse",
    "HealthCheckResponse",
    "ErrorResponse",
    "OAuthCallbackResponse",
    "OAuthStartResponse",
]
