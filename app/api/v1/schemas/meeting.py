"""
API request/response schemas for meeting operations.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class ManualJoinRequest(BaseModel):
    """Request to manually join a meeting."""
    bot_name: str = Field(..., description="Display name for the bot in the meeting", min_length=1)
    meeting_url: str = Field(..., description="Meeting URL to join", min_length=10)


class ManualJoinResponse(BaseModel):
    """Response for manual join request."""
    success: bool
    meeting_id: Optional[str] = None
    session_id: Optional[str] = None
    platform: Optional[str] = None
    error: Optional[str] = None


class MeetingStatusResponse(BaseModel):
    """Meeting status response."""
    running: bool
    scheduled_meetings: int
    active_sessions: List[dict]
    email_provider: str
    upcoming_jobs: List[dict]


class AuthStatusResponse(BaseModel):
    """Authentication status response."""
    gmail_authenticated: bool
    outlook_authenticated: bool
    services: List[str]


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    timestamp: datetime
    version: str


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    error_code: Optional[str] = None
