"""
Utility functions for extracting meeting URLs from text.
"""

import re
from typing import Optional, Tuple
from app.models import MeetingPlatform


# Regex patterns for meeting URLs
MEETING_URL_PATTERNS = {
    MeetingPlatform.TEAMS: [
        # Microsoft Teams meeting links (various formats)
        r'https://teams\.microsoft\.com/l/meetup-join/[^\s<>"\']+',
        r'https://teams\.microsoft\.com/meet/[^\s<>"\']+',
        r'https://teams\.live\.com/meet/[^\s<>"\']+',
    ],
    MeetingPlatform.ZOOM: [
        # Zoom meeting links
        r'https://[\w-]*\.?zoom\.us/j/\d+[^\s<>"\']*',
        r'https://[\w-]*\.?zoom\.us/my/[\w.-]+[^\s<>"\']*',
    ],
    MeetingPlatform.GOOGLE_MEET: [
        # Google Meet links
        r'https://meet\.google\.com/[\w-]+',
    ],
}


def extract_meeting_url(text: str) -> Optional[Tuple[str, MeetingPlatform]]:
    """
    Extract meeting URL from text and identify the platform.
    
    Args:
        text: Text to search for meeting URLs (email body, description, etc.)
        
    Returns:
        Tuple of (meeting_url, platform) if found, None otherwise.
    """
    if not text:
        return None
    
    # Search for each platform's patterns
    for platform, patterns in MEETING_URL_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                url = match.group(0)
                # Clean up the URL (remove trailing punctuation)
                url = url.rstrip('.,;:')
                return (url, platform)
    
    return None


def extract_all_meeting_urls(text: str) -> list[Tuple[str, MeetingPlatform]]:
    """
    Extract all meeting URLs from text.
    
    Args:
        text: Text to search for meeting URLs.
        
    Returns:
        List of (meeting_url, platform) tuples.
    """
    if not text:
        return []
    
    results = []
    for platform, patterns in MEETING_URL_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                url = match.rstrip('.,;:')
                if (url, platform) not in results:
                    results.append((url, platform))
    
    return results


def detect_platform_from_url(url: str) -> MeetingPlatform:
    """
    Detect the meeting platform from a URL.
    
    Args:
        url: Meeting URL.
        
    Returns:
        MeetingPlatform enum value.
    """
    if not url:
        return MeetingPlatform.UNKNOWN
    
    url_lower = url.lower()
    
    if 'teams.microsoft.com' in url_lower or 'teams.live.com' in url_lower:
        return MeetingPlatform.TEAMS
    elif 'zoom.us' in url_lower:
        return MeetingPlatform.ZOOM
    elif 'meet.google.com' in url_lower:
        return MeetingPlatform.GOOGLE_MEET
    
    return MeetingPlatform.UNKNOWN


def clean_html(text: str) -> str:
    """
    Remove HTML tags from text.
    
    Args:
        text: HTML text.
        
    Returns:
        Plain text without HTML tags.
    """
    if not text:
        return ""
    
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', ' ', text)
    # Remove extra whitespace
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def normalize_meeting_url(url: str) -> str:
    """
    Normalize a meeting URL for consistent comparison.
    
    Args:
        url: Meeting URL.
        
    Returns:
        Normalized URL.
    """
    if not url:
        return ""
    
    # Remove tracking parameters and normalize
    url = url.split('?')[0] if '?' in url else url
    url = url.rstrip('/')
    
    return url
