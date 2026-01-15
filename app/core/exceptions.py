"""
Custom exceptions for the Meeting Bot API.
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class MeetingBotException(Exception):
    """Base exception for Meeting Bot errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(MeetingBotException):
    """Raised when authentication fails."""
    pass


class MeetingJoinError(MeetingBotException):
    """Raised when joining a meeting fails."""
    pass


class SchedulerError(MeetingBotException):
    """Raised when scheduling operations fail."""
    pass


class EmailServiceError(MeetingBotException):
    """Raised when email service operations fail."""
    pass


class TranscriptionError(MeetingBotException):
    """Raised when transcription operations fail."""
    pass


class ConfigurationError(MeetingBotException):
    """Raised when configuration is invalid."""
    pass


# HTTP Exceptions for API responses
class HTTPBadRequest(HTTPException):
    """400 Bad Request"""
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class HTTPUnauthorized(HTTPException):
    """401 Unauthorized"""
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class HTTPForbidden(HTTPException):
    """403 Forbidden"""
    def __init__(self, detail: str = "Not enough permissions"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class HTTPNotFound(HTTPException):
    """404 Not Found"""
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class HTTPConflict(HTTPException):
    """409 Conflict"""
    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class HTTPInternalServerError(HTTPException):
    """500 Internal Server Error"""
    def __init__(self, detail: str = "Internal server error"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
