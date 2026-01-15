"""
API v1 router aggregation.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import auth, meetings, health

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["Meetings"])
api_router.include_router(health.router, tags=["Health"])

__all__ = ["api_router"]
