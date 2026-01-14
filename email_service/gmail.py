"""
Gmail service for fetching calendar invites and meeting information.
Uses Google Gmail API and Google Calendar API.
"""

import os
import json
import base64
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import EmailServiceBase
from .ical_parser import parse_icalendar
from .url_extractor import extract_meeting_url, clean_html
from models import MeetingDetails, MeetingPlatform, MeetingSource
from config import settings, get_logger, AuthMethod

logger = get_logger("gmail")


class GmailService(EmailServiceBase):
    """
    Gmail service implementation for fetching calendar invites.
    Uses both Gmail API (for email-based invites) and Google Calendar API.
    """
    
    def __init__(self):
        """Initialize the Gmail service."""
        self.credentials: Optional[Credentials] = None
        self.gmail_service = None
        self.calendar_service = None
        self._settings = settings.gmail
        
        # Ensure credentials directory exists
        Path(self._settings.credentials_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self._settings.token_file).parent.mkdir(parents=True, exist_ok=True)
    
    async def authenticate(self) -> bool:
        """
        Authenticate with Gmail using configured method.
        
        Returns:
            True if authentication was successful.
        """
        auth_method = self._settings.auth_method
        
        # Gmail API only supports OAuth2 authentication
        # App passwords work with IMAP/SMTP/POP3, but not with Gmail REST API
        
        if auth_method == AuthMethod.CREDENTIALS:
            logger.error("❌ Gmail API does not support direct credentials (app passwords)")
            logger.error("   Gmail API requires OAuth2 authentication")
            logger.error("   Please set GMAIL_AUTH_METHOD=oauth or auto")
            logger.error(f"   Authenticate at: http://localhost:{settings.auth_server.port}/auth/gmail/start")
            return False
        
        # AUTO or OAUTH mode: Use OAuth authentication
        if auth_method in [AuthMethod.AUTO, AuthMethod.OAUTH]:
            # Check for existing OAuth token
            if os.path.exists(self._settings.token_file):
                logger.info("Found OAuth token file, attempting authentication")
                if await self._authenticate_oauth():
                    return True
            
            # No valid token found
            logger.error("❌ No valid OAuth token found")
            logger.error(f"   Please authenticate at: http://localhost:{settings.auth_server.port}/auth/gmail/start")
            return False
        
        return False
    
    # Note: Direct credentials (app passwords) are NOT supported by Gmail API
    # Gmail API only supports OAuth2 authentication
    # This method has been removed as it cannot work with Gmail REST API
    
    async def _authenticate_oauth(self) -> bool:
        """
        Authenticate with Gmail using OAuth2.
        
        Returns:
            True if authentication was successful.
        """
        try:
            creds = None
            
            # Load existing token
            if os.path.exists(self._settings.token_file):
                try:
                    creds = Credentials.from_authorized_user_file(
                        self._settings.token_file,
                        self._settings.scopes
                    )
                except Exception as e:
                    logger.warning(f"Failed to load existing token: {e}")
            
            # If no valid credentials, user must authenticate via auth server
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired Gmail token...")
                    creds.refresh(Request())
                    
                    # Save refreshed token
                    with open(self._settings.token_file, 'w') as token:
                        token.write(creds.to_json())
                else:
                    logger.error(
                        "No valid OAuth token found. Please authenticate using the Auth Server:\n"
                        f"Visit: http://localhost:{settings.auth_server.port}/auth/gmail/start"
                    )
                    return False
            
            self.credentials = creds
            
            # Build services
            self.gmail_service = build('gmail', 'v1', credentials=creds)
            self.calendar_service = build('calendar', 'v3', credentials=creds)
            
            logger.info("Gmail OAuth authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Gmail OAuth authentication failed: {e}")
            return False
    
    async def refresh_token(self) -> bool:
        """
        Refresh the Gmail OAuth token.
        
        Returns:
            True if refresh was successful.
        """
        if not self.credentials:
            return await self.authenticate()
        
        try:
            if self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
                
                # Save updated token
                with open(self._settings.token_file, 'w') as token:
                    token.write(self.credentials.to_json())
                
                # Rebuild services
                self.gmail_service = build('gmail', 'v1', credentials=self.credentials)
                self.calendar_service = build('calendar', 'v3', credentials=self.credentials)
                
                logger.info("Gmail token refreshed successfully")
                return True
            return True
        except Exception as e:
            logger.error(f"Failed to refresh Gmail token: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if Gmail service is authenticated."""
        return (
            self.credentials is not None
            and self.credentials.valid
            and self.gmail_service is not None
        )
    
    async def get_calendar_invites(
        self,
        lookahead_hours: int = 24
    ) -> List[MeetingDetails]:
        """
        Get calendar invites from Gmail and Google Calendar.
        
        Args:
            lookahead_hours: How many hours ahead to look for meetings.
            
        Returns:
            List of MeetingDetails objects.
        """
        if not self.is_authenticated():
            if not await self.authenticate():
                return []
        
        meetings = []
        
        # Get events from Google Calendar
        calendar_meetings = await self._get_calendar_events(lookahead_hours)
        logger.debug(f"Found {len(calendar_meetings)} meetings from Google Calendar API")
        meetings.extend(calendar_meetings)
        
        # Get calendar invites from Gmail (emails with .ics attachments)
        email_meetings = await self._get_email_invites(lookahead_hours)
        logger.debug(f"Found {len(email_meetings)} meetings from Gmail email invites")
        meetings.extend(email_meetings)
        
        # Deduplicate meetings
        before_dedup = len(meetings)
        meetings = self._deduplicate_meetings(meetings)
        if before_dedup != len(meetings):
            logger.debug(f"Deduplicated {before_dedup} meetings down to {len(meetings)} unique meetings")
        
        logger.info(f"Found {len(meetings)} upcoming meetings from Gmail (Calendar: {len(calendar_meetings)}, Email: {len(email_meetings)})")
        return meetings
    
    async def _get_calendar_events(
        self,
        lookahead_hours: int
    ) -> List[MeetingDetails]:
        """
        Get events directly from Google Calendar.
        
        Args:
            lookahead_hours: How many hours ahead to look.
            
        Returns:
            List of MeetingDetails.
        """
        meetings = []
        
        try:
            now = datetime.now(ZoneInfo("UTC"))
            time_max = now + timedelta(hours=lookahead_hours)
            
            # Fetch all pages of calendar events
            page_token = None
            total_events = 0
            
            while True:
                request_params = {
                    'calendarId': 'primary',
                    'timeMin': now.isoformat(),
                    'timeMax': time_max.isoformat(),
                    'singleEvents': True,
                    'orderBy': 'startTime',
                    'maxResults': 250  # Google Calendar API max per page
                }
                
                if page_token:
                    request_params['pageToken'] = page_token
                
                events_result = self.calendar_service.events().list(**request_params).execute()
                
                events = events_result.get('items', [])
                total_events += len(events)
                
                for event in events:
                    meeting = self._parse_calendar_event(event)
                    if meeting:
                        meetings.append(meeting)
                
                # Check for next page
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
            
            logger.debug(f"Found {len(meetings)} events from Google Calendar (processed {total_events} total events)")
            
        except HttpError as e:
            logger.error(f"Failed to fetch Google Calendar events: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching calendar events: {e}")
        
        return meetings
    
    def _parse_calendar_event(self, event: dict) -> Optional[MeetingDetails]:
        """
        Parse a Google Calendar event into MeetingDetails.
        
        Args:
            event: Google Calendar event dict.
            
        Returns:
            MeetingDetails if valid online meeting, None otherwise.
        """
        try:
            # Get start and end times
            start = event.get('start', {})
            end = event.get('end', {})
            
            start_time = self._parse_event_time(start)
            end_time = self._parse_event_time(end)
            
            if not start_time or not end_time:
                return None
            
            # Get meeting details
            summary = event.get('summary', 'Untitled Meeting')
            description = event.get('description', '')
            location = event.get('location', '')
            event_id = event.get('id', '')
            
            # Check for conference data (Google Meet, Zoom, etc.)
            meeting_url = None
            platform = MeetingPlatform.UNKNOWN
            
            # Check conferenceData for Google Meet
            conf_data = event.get('conferenceData', {})
            entry_points = conf_data.get('entryPoints', [])
            for entry in entry_points:
                if entry.get('entryPointType') == 'video':
                    meeting_url = entry.get('uri')
                    if 'meet.google.com' in meeting_url:
                        platform = MeetingPlatform.GOOGLE_MEET
                    break
            
            # Check hangoutLink
            if not meeting_url:
                hangout_link = event.get('hangoutLink')
                if hangout_link:
                    meeting_url = hangout_link
                    platform = MeetingPlatform.GOOGLE_MEET
            
            # Check location and description for other meeting URLs
            if not meeting_url:
                search_text = f"{location} {description}"
                result = extract_meeting_url(search_text)
                if result:
                    meeting_url, platform = result
            
            # Skip if no meeting URL
            if not meeting_url:
                logger.debug(
                    f"Skipping event '{summary}' (no meeting URL found). "
                    f"Location: '{location[:50] if location else 'none'}', "
                    f"Description: '{description[:50] if description else 'none'}'"
                )
                return None
            
            # Get organizer
            organizer = event.get('organizer', {})
            organizer_email = organizer.get('email', '')
            organizer_name = organizer.get('displayName', organizer_email)
            
            # Get attendees
            attendees = []
            for attendee in event.get('attendees', []):
                attendees.append(attendee.get('email', ''))
            
            # Generate meeting ID
            meeting_id = self._generate_meeting_id(meeting_url, start_time, event_id)
            
            return MeetingDetails(
                meeting_id=meeting_id,
                title=summary,
                start_time=start_time,
                end_time=end_time,
                meeting_url=meeting_url,
                platform=platform,
                source=MeetingSource.GMAIL,
                organizer=organizer_name,
                organizer_email=organizer_email,
                attendees=attendees,
                description=clean_html(description) if description else None,
                location=location,
                raw_event_id=event_id,
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse calendar event: {e}")
            return None
    
    def _parse_event_time(self, time_info: dict) -> Optional[datetime]:
        """
        Parse event time from Google Calendar format.
        
        Args:
            time_info: Dict with 'dateTime' or 'date'.
            
        Returns:
            Parsed datetime.
        """
        if 'dateTime' in time_info:
            dt_str = time_info['dateTime']
            # Parse ISO format with timezone
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        elif 'date' in time_info:
            # All-day event
            date_str = time_info['date']
            return datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=ZoneInfo("UTC"))
        return None
    
    async def _get_email_invites(
        self,
        lookahead_hours: int
    ) -> List[MeetingDetails]:
        """
        Get calendar invites from Gmail emails with .ics attachments.
        
        Args:
            lookahead_hours: How many hours ahead to look.
            
        Returns:
            List of MeetingDetails.
        """
        meetings = []
        
        try:
            # Search for emails with calendar invites
            query = 'has:attachment filename:ics newer_than:7d'
            
            # Fetch all pages of results
            page_token = None
            total_messages = 0
            
            while True:
                request_params = {
                    'userId': 'me',
                    'q': query,
                    'maxResults': 50
                }
                
                if page_token:
                    request_params['pageToken'] = page_token
                
                results = self.gmail_service.users().messages().list(**request_params).execute()
                
                messages = results.get('messages', [])
                total_messages += len(messages)
                
                for message in messages:
                    msg_meetings = await self._parse_email_invite(message['id'], lookahead_hours)
                    meetings.extend(msg_meetings)
                
                # Check for next page
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            logger.info(f"Processed {total_messages} Gmail emails with .ics attachments, found {len(meetings)} valid meeting invites")
            
        except HttpError as e:
            logger.error(f"Failed to fetch Gmail messages: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching email invites: {e}")
        
        return meetings
    
    async def _parse_email_invite(
        self,
        message_id: str,
        lookahead_hours: int
    ) -> List[MeetingDetails]:
        """
        Parse calendar invite from a Gmail message.
        
        Args:
            message_id: Gmail message ID.
            lookahead_hours: Lookahead window in hours.
            
        Returns:
            List of MeetingDetails from the email.
        """
        meetings = []
        
        try:
            message = self.gmail_service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Look for .ics attachments
            parts = message.get('payload', {}).get('parts', [])
            
            for part in parts:
                filename = part.get('filename', '')
                if filename.endswith('.ics'):
                    # Get attachment data
                    attachment_id = part.get('body', {}).get('attachmentId')
                    if attachment_id:
                        attachment = self.gmail_service.users().messages().attachments().get(
                            userId='me',
                            messageId=message_id,
                            id=attachment_id
                        ).execute()
                        
                        ics_data = base64.urlsafe_b64decode(attachment['data']).decode('utf-8')
                        parsed_meetings = parse_icalendar(
                            ics_data,
                            MeetingSource.GMAIL,
                            lookahead_hours
                        )
                        meetings.extend(parsed_meetings)
                    else:
                        # Inline attachment
                        data = part.get('body', {}).get('data')
                        if data:
                            ics_data = base64.urlsafe_b64decode(data).decode('utf-8')
                            parsed_meetings = parse_icalendar(
                                ics_data,
                                MeetingSource.GMAIL,
                                lookahead_hours
                            )
                            meetings.extend(parsed_meetings)
        
        except Exception as e:
            logger.warning(f"Failed to parse email invite {message_id}: {e}")
        
        return meetings
    
    def _deduplicate_meetings(
        self,
        meetings: List[MeetingDetails]
    ) -> List[MeetingDetails]:
        """
        Remove duplicate meetings based on URL and start time.
        
        Args:
            meetings: List of meetings.
            
        Returns:
            Deduplicated list.
        """
        seen = set()
        unique = []
        
        for meeting in meetings:
            key = (meeting.meeting_url, meeting.start_time.isoformat())
            if key not in seen:
                seen.add(key)
                unique.append(meeting)
        
        return unique
    
    def _generate_meeting_id(
        self,
        url: str,
        start_time: datetime,
        event_id: str = ""
    ) -> str:
        """Generate a unique meeting ID."""
        unique_string = f"{url}|{start_time.isoformat()}|{event_id}"
        return hashlib.sha256(unique_string.encode()).hexdigest()[:16]
