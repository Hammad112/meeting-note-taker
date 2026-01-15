"""
API schemas for authentication operations.
"""

from typing import Optional
from pydantic import BaseModel, Field


class OAuthCallbackResponse(BaseModel):
    """OAuth callback response."""
    success: bool
    message: str
    redirect_url: Optional[str] = None


class OAuthStartResponse(BaseModel):
    """OAuth start response."""
    auth_url: str
    state: str
