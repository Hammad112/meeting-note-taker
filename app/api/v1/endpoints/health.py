"""
Health check and status endpoints.
"""

from datetime import datetime
from fastapi import APIRouter, Depends
from typing import Dict, Any

from app.api.v1.schemas.meeting import HealthCheckResponse, AuthStatusResponse, MeetingStatusResponse
from app.core.config import settings
from app.core.dependencies import get_meeting_bot_service

router = APIRouter()


@router.get("/health", response_model=HealthCheckResponse, tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.
    
    Returns:
        Health status with timestamp and version
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(),
        "version": settings.version,
    }


@router.get("/auth/status", response_model=AuthStatusResponse, tags=["Authentication"])
async def get_auth_status() -> Dict[str, Any]:
    """
    Check authentication status for all configured services.
    
    Returns:
        Authentication status for Gmail and Outlook
    """
    import os
    
    gmail_authenticated = os.path.exists(settings.gmail.token_file)
    outlook_authenticated = os.path.exists(settings.outlook.token_file)
    
    services = []
    if gmail_authenticated:
        services.append("gmail")
    if outlook_authenticated:
        services.append("outlook")
    
    return {
        "gmail_authenticated": gmail_authenticated,
        "outlook_authenticated": outlook_authenticated,
        "services": services,
    }


@router.get("/status", response_model=MeetingStatusResponse, tags=["Status"])
async def get_meeting_status(bot=Depends(get_meeting_bot_service)) -> Dict[str, Any]:
    """
    Get current meeting bot status.
    
    Returns:
        Bot status including active sessions and scheduled meetings
    """
    return bot.get_status()
