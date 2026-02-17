"""
Meeting Orchestrator

Main coordinator that routes meeting requests to appropriate platform handlers.
Handles unified monitoring and cleanup across all platforms.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import json
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
)

from app.config import get_logger
from app.models import MeetingDetails, MeetingPlatform
from app.transcription.service import TranscriptionService
from app.storage.s3_service import S3Service
from app.storage.meeting_database import MeetingDatabase
from .teams_scripts import get_selectors_for
from .teams_meeting_handler import TeamsMeetingHandler
from .zoom_meeting_handler import ZoomMeetingHandler
from .meet_handler import MeetMeetingHandler


logger = get_logger("meeting_orchestrator")


class MeetingOrchestrator:
    """
    Main coordinator for all meeting platforms.
    
    Routes meeting requests to appropriate handlers and manages:
    - Unified monitoring across platforms
    - Centralized cleanup and JSON export
    - S3 upload and database updates
    """
    
    def __init__(self, browser: Browser):
        self.browser = browser
        
        # Track active contexts for meetings that are being monitored
        self.active_contexts: dict[str, BrowserContext] = {}

        # Services
        self.transcription_service = TranscriptionService()
        self.s3_service = S3Service()
        self.meeting_database = MeetingDatabase()
        
        # Platform handlers (with S3 service for recording uploads)
        self.teams_handler = TeamsMeetingHandler(browser, self.transcription_service, self.s3_service)
        self.zoom_handler = ZoomMeetingHandler(browser)
        self.meet_handler = MeetMeetingHandler(browser, self.transcription_service, self.s3_service)
    
    async def join_meeting(self, meeting: MeetingDetails) -> None:
        """
        Route meeting to appropriate platform handler and start unified monitoring.
        """
        if not meeting.meeting_url:
            logger.warning(f"Cannot join meeting {meeting.title}: no meeting URL.")
            return

        # Check for duplicates
        if meeting.meeting_url in self.active_contexts:
            logger.info(f"Meeting '{meeting.title}' ({meeting.meeting_url}) is already active. Skipping duplicate join.")
            return

        logger.info(
            f"Joining meeting: title='{meeting.title}', "
            f"platform='{meeting.platform.value}', url='{meeting.meeting_url}'"
        )

        try:
            # Route to appropriate handler
            if meeting.platform == MeetingPlatform.TEAMS:
                context, page = await self.teams_handler.join_meeting(meeting, self.active_contexts)
            elif meeting.platform == MeetingPlatform.ZOOM:
                context, page = await self.zoom_handler.join_meeting(meeting, self.active_contexts)
            elif meeting.platform == MeetingPlatform.GOOGLE_MEET:
                context, page = await self.meet_handler.join_meeting(meeting, self.active_contexts)
            else:
                logger.error(f"Unsupported platform: {meeting.platform.value}")
                return
            
            # Start unified monitoring if join was successful
            if context and page:
                platform_name = meeting.platform.value.lower().replace(" ", "_")
                asyncio.create_task(self._monitor_meeting_unified(context, page, meeting, platform_name))
                logger.info(f"{meeting.platform.value} meeting monitoring started for: {meeting.title}")
            
        except Exception as exc:
            logger.error(f"Failed to join meeting {meeting.title}: {exc}")
    
    async def _monitor_meeting_unified(
        self, 
        context: BrowserContext, 
        page: Page, 
        meeting: MeetingDetails,
        platform: str
    ) -> None:
        """
        Unified meeting monitoring function for Teams, Google Meet, and Zoom.
        Handles meeting end detection and cleanup.
        """
        logger.info(f"Monitoring {platform} meeting: {meeting.title}")
        
        try:
            while True:
                if page.is_closed():
                    logger.info(f"{platform} page closed for: {meeting.title}")
                    break
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
                # Check for meeting end indicators
                try:
                    # Check if we've been removed/kicked (mainly for Teams)
                    if platform == "teams":
                        denied_selectors = get_selectors_for("entry_denied")
                        for selector in denied_selectors:
                            try:
                                msg = page.locator(selector)
                                if await msg.count() > 0 and await msg.first.is_visible(timeout=1000):
                                    logger.info(f"Meeting ended or was removed: {meeting.title}")
                                    meeting.was_kicked = True
                                    raise StopIteration()
                            except StopIteration:
                                raise
                            except:
                                continue
                    
                    # Check if Leave button is gone (universal indicator)
                    leave_visible = False
                    
                    # INEFFICIENT: This nested loop structure is overly complex and slow
                    # TODO: Optimize with single pass through combined selectors
                    # Platform-specific leave button selectors
                    if platform == "teams":
                        leave_selectors = get_selectors_for("leave_button")
                    elif platform == "google_meet":
                        leave_selectors = ['button[aria-label*="Leave call"]', 'button[aria-label*="Leave"]']
                    elif platform == "zoom":
                        leave_selectors = ['button[aria-label*="Leave"]', 'button[title*="Leave"]']
                    else:
                        leave_selectors = ['button[aria-label*="Leave"]', 'button[title*="Leave"]']
                    
                    for selector in leave_selectors:
                        try:
                            leave_btn = page.locator(selector)
                            if await leave_btn.count() > 0 and await leave_btn.first.is_visible(timeout=1000):
                                leave_visible = True
                                break
                        except:
                            continue
                    
                    if not leave_visible:
                        # Double-check by looking for other in-meeting indicators
                        # INEFFICIENT: Too many selectors and nested loops
                        # TODO: Create unified selector list per platform
                        in_meeting_indicators = [
                            '[data-tid="roster-list"]',  # Teams
                            '[class*="participant"]',
                            '[class*="Participant"]',
                            'button[aria-label*="Mute"]',
                            'button[aria-label*="microphone"]',
                            '[class*="meeting"]',
                            'video',  # If video element exists, likely still in meeting
                            '[class*="call-controls"]',
                            '[class*="CallControls"]',
                        ]
                        
                        # Add platform-specific indicators
                        if platform == "google_meet":
                            in_meeting_indicators.extend([
                                '[data-is-muted]',  # Meet mute indicators
                                '[data-participant-id]',  # Meet participants
                            ])
                        elif platform == "zoom":
                            in_meeting_indicators.extend([
                                '[class*="footer-button"]',  # Zoom controls
                                '[id*="footer"]',
                            ])
                        
                        still_in_meeting = False
                        for indicator_sel in in_meeting_indicators:
                            try:
                                indicator = page.locator(indicator_sel)
                                if await indicator.count() > 0:
                                    still_in_meeting = True
                                    logger.debug(f"Still in meeting - found: {indicator_sel}")
                                    break
                            except:
                                continue
                        
                        if not still_in_meeting:
                            logger.info(f"No in-meeting indicators found - meeting may have ended: {meeting.title}")
                            # Wait and check again to avoid false positives
                            await asyncio.sleep(5)
                            
                            # Check one more time
                            final_check = False
                            for indicator_sel in in_meeting_indicators[:5]:
                                try:
                                    indicator = page.locator(indicator_sel)
                                    if await indicator.count() > 0:
                                        final_check = True
                                        break
                                except:
                                    continue
                            
                            if not final_check:
                                logger.info(f"Confirmed: meeting appears to have ended: {meeting.title}")
                                break
                            else:
                                logger.debug("False positive - still in meeting after recheck")
                    
                except StopIteration:
                    break
                except Exception as e:
                    logger.debug(f"Monitor check error: {e}")
                    
        except asyncio.CancelledError:
            logger.info(f"{platform} meeting monitor cancelled for: {meeting.title}")
        except Exception as e:
            msg = str(e)
            if "Target page, context or browser has been closed" in msg:
                logger.info(f"{platform} session closed for: {meeting.title}")
            else:
                logger.error(f"Error monitoring {platform} meeting: {e}")
        finally:
            await self._cleanup_meeting_session(context, page, meeting, platform)
    
    async def _cleanup_meeting_session(
        self, 
        context: BrowserContext, 
        page: Page, 
        meeting: MeetingDetails,
        platform: str
    ) -> None:
        """
        Unified cleanup function for meeting sessions.
        Handles transcription stop, JSON export, and resource cleanup.
        """
        logger.info(f"Closing {platform} session for: {meeting.title}")
        
        # Stop transcription
        self.transcription_service.stop_transcription()
        
        # Stop recording if active
        recording_info = None
        try:
            handler = None
            if platform == "teams":
                handler = self.teams_handler
            elif platform == "google_meet":
                handler = self.meet_handler
            
            if handler and handler.recording_service.is_recording:
                logger.info("Stopping recording...")
                recording_info = await handler.recording_service.stop_recording()
                if recording_info:
                    logger.info(f"Recording saved: {recording_info.get('recording_id')}")
                    logger.info(f"Files: {list(recording_info.get('files', {}).keys())}")
        except Exception as e:
            logger.warning(f"Error stopping recording: {e}")
        
        # Stop speaking tracker and collect data (Teams only for now)
        speaking_data = None
        try:
            if platform == "teams" and self.teams_handler.speaking_tracker:
                logger.info("Stopping speaking tracker...")
                speaking_data = await self.teams_handler.speaking_tracker.stop()
                segment_count = len(speaking_data.get('speaking_segments', []))
                event_count = len(speaking_data.get('participant_events', []))
                logger.info(f"✅ Speaking tracker stopped: {segment_count} segments, {event_count} events")
                # Clear tracker reference
                self.teams_handler.speaking_tracker = None
        except Exception as e:
            logger.warning(f"Error stopping speaking tracker: {e}")
        
        # Export to JSON and upload to S3
        try:
            logger.info("Exporting meeting data to JSON...")
            meeting_data = self.transcription_service.export_to_json()
            
            # Check if meeting has custom S3 configuration (from manual join)
            s3_service = None
            if meeting.s3_config:
                # Use custom S3 configuration provided during manual join
                logger.info(f"Using custom S3 configuration for bucket: {meeting.s3_config.get('bucket_name')}")
                s3_service = S3Service(
                    bucket_name=meeting.s3_config.get('bucket_name'),
                    access_key_id=meeting.s3_config.get('access_key_id'),
                    secret_access_key=meeting.s3_config.get('secret_access_key'),
                    region=meeting.s3_config.get('region', 'us-east-1')
                )
            else:
                # Use default S3 service (environment variables)
                s3_service = self.s3_service
            
            # Get meeting ID for consistent directory naming
            meeting_id = meeting.meeting_id or meeting_data.get('metadata', {}).get('meeting_id', 'unknown')
            
            # Upload to S3 if enabled
            if s3_service and s3_service.is_enabled():
                # Upload transcription JSON to {meeting_id}/json/
                s3_path = s3_service.upload_meeting_json(meeting_data, meeting_id)
                if s3_path:
                    logger.info(f"✅ Transcription uploaded to S3: {s3_path}")
                else:
                    logger.warning("Transcription S3 upload failed")
                
                # Upload speaking tracker data to {meeting_id}/json/ (separate file)
                if speaking_data:
                    speaking_s3_path = s3_service.upload_speaking_json(speaking_data, meeting_id)
                    if speaking_s3_path:
                        logger.info(f"✅ Speaking data uploaded to S3: {speaking_s3_path}")
                    else:
                        logger.warning("Speaking data S3 upload failed")
                
                # Upload recording files (audio and video) if available
                if recording_info and recording_info.get('files'):
                    meeting_id = meeting.meeting_id or recording_info.get('recording_id')
                    files = recording_info['files']
                    s3_keys = {}
                    
                    # Upload video with audio
                    if 'video_with_audio' in files:
                        video_path = files['video_with_audio']['path']
                        logger.info(f"Uploading video with audio to S3: {video_path}")
                        video_s3_key = s3_service.upload_recording(video_path, meeting_id, "video_audio")
                        if video_s3_key:
                            s3_keys['video_audio'] = f"s3://{s3_service.bucket_name}/{video_s3_key}"
                            logger.info(f"✅ Video with audio uploaded to S3: {s3_keys['video_audio']}")
                        else:
                            logger.warning("Failed to upload video with audio to S3")
                    
                    # Upload video only (if separate)
                    elif 'video_only' in files:
                        video_path = files['video_only']['path']
                        logger.info(f"Uploading video-only to S3: {video_path}")
                        video_s3_key = s3_service.upload_recording(video_path, meeting_id, "video_only")
                        if video_s3_key:
                            s3_keys['video_only'] = f"s3://{s3_service.bucket_name}/{video_s3_key}"
                            logger.info(f"✅ Video-only uploaded to S3: {s3_keys['video_only']}")
                        else:
                            logger.warning("Failed to upload video-only to S3")
                    
                    # Upload audio only
                    if 'audio_only' in files:
                        audio_path = files['audio_only']['path']
                        logger.info(f"Uploading audio-only to S3: {audio_path}")
                        audio_s3_key = s3_service.upload_recording(audio_path, meeting_id, "audio_only")
                        if audio_s3_key:
                            s3_keys['audio_only'] = f"s3://{s3_service.bucket_name}/{audio_s3_key}"
                            logger.info(f"✅ Audio-only uploaded to S3: {s3_keys['audio_only']}")
                        else:
                            logger.warning("Failed to upload audio-only to S3")
                    
                    # Upload audio for transcription (if separate)
                    elif 'audio_for_transcription' in files:
                        audio_path = files['audio_for_transcription']['path']
                        logger.info(f"Uploading audio for transcription to S3: {audio_path}")
                        audio_s3_key = s3_service.upload_recording(audio_path, meeting_id, "audio_transcription")
                        if audio_s3_key:
                            s3_keys['audio_transcription'] = f"s3://{s3_service.bucket_name}/{audio_s3_key}"
                            logger.info(f"✅ Audio for transcription uploaded to S3: {s3_keys['audio_transcription']}")
                        else:
                            logger.warning("Failed to upload audio for transcription to S3")
                
                # Add to local database with all S3 paths
                if s3_path:
                    metadata = {
                        "meeting_id": meeting.meeting_id,
                        "title": meeting.title,
                        "platform": meeting.platform,
                        "export_timestamp": meeting_data.get("export_timestamp")
                    }
                    
                    # Add recording S3 paths to metadata
                    if recording_info and 's3_keys' in locals():
                        metadata['recordings'] = s3_keys
                    
                    self.meeting_database.add_meeting(
                        meeting_url=meeting.meeting_url,
                        s3_path=s3_path,
                        metadata=metadata
                    )
                    logger.info(f"✅ Meeting data saved to database with S3 references")
                else:
                    logger.warning("S3 transcription upload failed")
            else:
                logger.info("S3 service not enabled. Saving transcription JSON locally only.")
                # Save JSON locally as backup
                json_dir = Path("transcripts/json")
                json_dir.mkdir(parents=True, exist_ok=True)
                json_filename = f"{meeting.meeting_id}_{meeting_data['export_timestamp'].replace(':', '-')}.json"
                json_path = json_dir / json_filename
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(meeting_data, f, indent=2, ensure_ascii=False)
                logger.info(f"Transcription saved locally: {json_path}")
                
                # Save speaking tracker data locally
                if speaking_data:
                    speaking_filename = f"{meeting.meeting_id}_speaking_{meeting_data['export_timestamp'].replace(':', '-')}.json"
                    speaking_path = json_dir / speaking_filename
                    with open(speaking_path, 'w', encoding='utf-8') as f:
                        json.dump(speaking_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"Speaking data saved locally: {speaking_path}")
                
                # Note: Recording files are already saved locally in recordings/ directory
                if recording_info and recording_info.get('files'):
                    logger.info("Recording files saved locally:")
                    for file_type, file_info in recording_info['files'].items():
                        logger.info(f"  - {file_type}: {file_info.get('path')}")

            
            # Reset metadata for next meeting
            self.transcription_service.reset_metadata()
            
        except Exception as export_error:
            logger.error(f"Error exporting meeting data: {export_error}")
        
        # Close context and cleanup
        try:
            await context.close()
        except:
            pass
        
        if meeting.meeting_url in self.active_contexts:
            del self.active_contexts[meeting.meeting_url]
    
    async def cleanup_all(self) -> None:
        """Clean up all active meeting contexts."""
        logger.info("Cleaning up all active meeting contexts...")
        
        for url, context in list(self.active_contexts.items()):
            logger.info(f"Closing active meeting context for {url}")
            await context.close()
            del self.active_contexts[url]
        
        # Stop transcription service
        self.transcription_service.stop_transcription()
