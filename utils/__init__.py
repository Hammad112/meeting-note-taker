"""
Utility functions for the Meeting Bot.
"""

import re
import hashlib
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo


def generate_id(prefix: str = "", length: int = 16) -> str:
    """
    Generate a unique ID.
    
    Args:
        prefix: Optional prefix for the ID.
        length: Length of the random part.
        
    Returns:
        Unique ID string.
    """
    import uuid
    random_part = uuid.uuid4().hex[:length]
    return f"{prefix}{random_part}" if prefix else random_part


def hash_string(s: str, length: int = 16) -> str:
    """
    Create a hash of a string.
    
    Args:
        s: String to hash.
        length: Length of the returned hash.
        
    Returns:
        Hash string.
    """
    return hashlib.sha256(s.encode()).hexdigest()[:length]


def parse_datetime(dt_string: str, default_tz: str = "UTC") -> Optional[datetime]:
    """
    Parse a datetime string with timezone handling.
    
    Args:
        dt_string: Datetime string to parse.
        default_tz: Default timezone if not specified.
        
    Returns:
        Parsed datetime or None if parsing fails.
    """
    from dateutil.parser import parse
    
    try:
        dt = parse(dt_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(default_tz))
        return dt
    except Exception:
        return None


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to human-readable string.
    
    Args:
        seconds: Duration in seconds.
        
    Returns:
        Formatted duration string (e.g., "1h 30m 45s").
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a string for use as a filename.
    
    Args:
        filename: Original filename.
        
    Returns:
        Sanitized filename.
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Limit length
    return sanitized[:200]


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.
    
    Args:
        text: Text to truncate.
        max_length: Maximum length.
        suffix: Suffix to add when truncated.
        
    Returns:
        Truncated text.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def retry_async(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for retrying async functions.
    
    Args:
        max_retries: Maximum number of retry attempts.
        delay: Initial delay between retries in seconds.
        backoff: Backoff multiplier for delay.
        
    Returns:
        Decorated function.
    """
    import asyncio
    import functools
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            
            raise last_exception
        
        return wrapper
    
    return decorator
