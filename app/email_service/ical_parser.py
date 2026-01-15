"""
iCalendar (.ics) parser for extracting meeting details.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo

from icalendar import Calendar
from dateutil.rrule import rrulestr
from dateutil.parser import parse as parse_date

from app.models import MeetingDetails, MeetingPlatform, MeetingSource
from .url_extractor import extract_meeting_url, clean_html
from app.config import get_logger

logger = get_logger("ical_parser")


def parse_icalendar(
    ics_content: str,
    source: MeetingSource,
    lookahead_hours: int = 24
) -> List[MeetingDetails]:
    """
    Parse iCalendar (.ics) content and extract meeting details.
    
    Args:
        ics_content: Raw iCalendar file content.
        source: Source of the calendar (gmail/outlook).
        lookahead_hours: Only include meetings within this time range.
        
    Returns:
        List of MeetingDetails objects.
    """
    meetings = []
    
    try:
        cal = Calendar.from_ical(ics_content)
    except Exception as e:
        logger.error(f"Failed to parse iCalendar: {e}")
        return meetings
    
    now = datetime.now(ZoneInfo("UTC"))
    lookahead_end = now + timedelta(hours=lookahead_hours)
    
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        
        try:
            meeting = _parse_vevent(component, source, now, lookahead_end)
            if meeting:
                meetings.append(meeting)
        except Exception as e:
            logger.warning(f"Failed to parse event: {e}")
            continue
    
    return meetings


def _parse_vevent(
    event,
    source: MeetingSource,
    now: datetime,
    lookahead_end: datetime
) -> Optional[MeetingDetails]:
    """
    Parse a VEVENT component into MeetingDetails.
    
    Args:
        event: iCalendar VEVENT component.
        source: Source of the calendar.
        now: Current datetime.
        lookahead_end: End of lookahead window.
        
    Returns:
        MeetingDetails if valid meeting found, None otherwise.
    """
    # Get start and end times
    dtstart = event.get("dtstart")
    dtend = event.get("dtend")
    
    if not dtstart:
        return None
    
    start_time = _normalize_datetime(dtstart.dt)
    
    if dtend:
        end_time = _normalize_datetime(dtend.dt)
    else:
        # Default 1 hour meeting if no end time
        end_time = start_time + timedelta(hours=1)
    
    # Check if meeting is within lookahead window
    if start_time > lookahead_end or end_time < now:
        return None
    
    # Get meeting details
    summary = str(event.get("summary", "Untitled Meeting"))
    description = event.get("description", "")
    if description:
        description = clean_html(str(description))
    
    location = str(event.get("location", "")) if event.get("location") else ""
    uid = str(event.get("uid", ""))
    
    # Get organizer
    organizer = event.get("organizer")
    organizer_email = None
    organizer_name = None
    if organizer:
        organizer_email = str(organizer).replace("mailto:", "")
        if hasattr(organizer, "params"):
            organizer_name = organizer.params.get("CN", organizer_email)
    
    # Get attendees
    attendees = []
    for attendee in event.get("attendee", []):
        if isinstance(attendee, list):
            for a in attendee:
                attendees.append(str(a).replace("mailto:", ""))
        else:
            attendees.append(str(attendee).replace("mailto:", ""))
    
    # Extract meeting URL from description, location, or special properties
    meeting_url = None
    platform = MeetingPlatform.UNKNOWN
    
    # Check for online meeting URL in various places
    search_text = f"{description} {location}"
    
    # Check X-MICROSOFT-SKYPETEAMSMEETINGURL for Teams
    teams_url = event.get("X-MICROSOFT-SKYPETEAMSMEETINGURL")
    if teams_url:
        meeting_url = str(teams_url)
        platform = MeetingPlatform.TEAMS
    
    # Check location and description for URLs
    if not meeting_url:
        result = extract_meeting_url(search_text)
        if result:
            meeting_url, platform = result
    
    # Skip if no meeting URL found (not an online meeting)
    if not meeting_url:
        logger.debug(
            f"No meeting URL found for event '{summary}' (start: {start_time.strftime('%Y-%m-%d %H:%M')}). "
            f"Location: '{location[:50] if location else 'none'}', "
            f"Description: '{description[:100] if description else 'none'}'"
        )
        return None
    
    # Generate meeting ID
    meeting_id = _generate_meeting_id(meeting_url, start_time, uid)
    
    return MeetingDetails(
        meeting_id=meeting_id,
        title=summary,
        start_time=start_time,
        end_time=end_time,
        meeting_url=meeting_url,
        platform=platform,
        source=source,
        organizer=organizer_name,
        organizer_email=organizer_email,
        attendees=attendees,
        description=description,
        location=location,
        raw_event_id=uid,
    )


def _normalize_datetime(dt) -> datetime:
    """
    Normalize a datetime to be timezone-aware.
    
    Args:
        dt: datetime or date object from iCalendar.
        
    Returns:
        Timezone-aware datetime.
    """
    if hasattr(dt, 'hour'):
        # It's a datetime
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt
    else:
        # It's a date (all-day event)
        return datetime.combine(dt, datetime.min.time(), tzinfo=ZoneInfo("UTC"))


def _generate_meeting_id(url: str, start_time: datetime, uid: str = "") -> str:
    """
    Generate a unique meeting ID.
    
    Args:
        url: Meeting URL.
        start_time: Meeting start time.
        uid: Original event UID.
        
    Returns:
        Unique meeting ID.
    """
    unique_string = f"{url}|{start_time.isoformat()}|{uid}"
    return hashlib.sha256(unique_string.encode()).hexdigest()[:16]
