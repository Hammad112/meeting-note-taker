"""
Recording Service for Meeting Bot

Handles automatic recording of meetings using Playwright's built-in video recording.

Features:
- Automatic start on meeting join
- High quality video recording
- Audio extraction from video
- S3 upload integration
- Local storage with auto-cleanup

Uses Playwright's native context.record_video() for reliable automated recording.
"""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import uuid
import subprocess

from playwright.async_api import Page, BrowserContext

from app.config import settings, get_logger
from app.models import MeetingDetails
from app.storage import S3Service
from .pulse_audio_capture import PulseAudioCapture

logger = get_logger("recording")


class RecordingService:
    """Manages video recording for meetings using Playwright's native recording."""
    
    def __init__(self, s3_service: Optional[S3Service] = None):
        """
        Initialize recording service.
        
        Args:
            s3_service: Optional S3 service for uploads
        """
        self.s3_service = s3_service
        self.is_recording = False
        self.recording_id: Optional[str] = None
        self.meeting_details: Optional[MeetingDetails] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Audio chunk buffer (for JavaScript fallback)
        self.audio_chunks: List[bytes] = []
        
        # PulseAudio capture (primary method for Teams)
        self.pulse_capture: Optional[PulseAudioCapture] = None
        self.use_pulse_audio: bool = False
        
        # Synchronization timestamps (in milliseconds since epoch)
        self.video_started_at_ms: Optional[int] = None
        self.audio_started_at_ms: Optional[int] = None
        
        # Recording metadata
        self.recording_started_at: Optional[datetime] = None
        self.video_file_path: Optional[Path] = None
        self.audio_file_path: Optional[Path] = None
        self.recording_dir: Optional[Path] = None
        
        # Ensure recordings directory exists
        self.recordings_base_dir = Path(settings.recordings_dir if hasattr(settings, 'recordings_dir') else "recordings")
        self.recordings_base_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure temp directory exists for Playwright video recording
        self.temp_recordings_dir = self.recordings_base_dir / "temp"
        self.temp_recordings_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("RecordingService initialized (using Playwright video recording)")
    
    def set_context(self, context: BrowserContext) -> None:
        """Set the browser context for this recording session."""
        self.context = context
    
    def set_video_start_timestamp(self, timestamp_ms: int) -> None:
        """
        Set the video start timestamp.
        
        This should be called immediately when browser context is created,
        since Playwright starts video recording at context creation time.
        
        Args:
            timestamp_ms: Timestamp in milliseconds when context was created
        """
        self.video_started_at_ms = timestamp_ms
        logger.info(f"Video start timestamp set: {timestamp_ms}")
    
    async def start_recording(self, page: Page, meeting: MeetingDetails) -> bool:
        """
        Start automatic recording.
        
        Note: Video recording is configured when creating the browser context.
        This method starts audio recording via JavaScript.
        
        Args:
            page: Playwright page object for the meeting
            meeting: Meeting details
            
        Returns:
            True if recording is active
        """
        if self.is_recording:
            logger.warning("Recording already in progress")
            return False
        
        try:
            self.page = page
            self.meeting_details = meeting
            self.recording_id = f"{meeting.meeting_id or uuid.uuid4()}_{int(datetime.now().timestamp())}"
            self.recording_started_at = datetime.now()
            
            # Create recording directory
            self.recording_dir = self.recordings_base_dir / self.recording_id
            self.recording_dir.mkdir(parents=True, exist_ok=True)
            
            self.video_file_path = self.recording_dir / "video_audio.webm"
            self.audio_file_path = self.recording_dir / "audio_only.webm"
            self.temp_audio_path = self.recording_dir / "audio_temp.webm"
            
            # Note: video_started_at_ms should already be set via set_video_start_timestamp()
            # called from meet_handler when context was created
            if not self.video_started_at_ms:
                logger.warning("Video start timestamp not set! Sync may be inaccurate.")
            
            logger.info(f"Recording initialized for meeting: {meeting.title} (ID: {self.recording_id})")
            logger.info(f"Video will be saved when page closes to: {self.video_file_path}")
            
            # Try PulseAudio capture first (works reliably for Teams and Google Meet)
            audio_started = False
            if await PulseAudioCapture.is_available():
                logger.info("PulseAudio available - using system audio capture")
                self.pulse_capture = PulseAudioCapture(
                    output_dir=self.recording_dir,
                    format="opus",
                    sample_rate=16000,
                    channels=1,
                    verbose=False
                )
                audio_started = await self.pulse_capture.start()
                if audio_started:
                    self.use_pulse_audio = True
                    # Record audio start time for sync (in milliseconds)
                    import time
                    self.audio_started_at_ms = int(time.time() * 1000)
                    logger.info(f"✅ PulseAudio audio recording started at {self.audio_started_at_ms}")
                    
                    # Log sync info
                    if self.video_started_at_ms:
                        offset_ms = self.audio_started_at_ms - self.video_started_at_ms
                        logger.info(f"Audio-Video offset: {offset_ms}ms (audio starts {offset_ms/1000:.1f}s after video)")
                else:
                    logger.warning("PulseAudio start failed, falling back to JavaScript")
                    self.pulse_capture = None
            
            # Fallback to JavaScript MediaRecorder if PulseAudio not available
            if not audio_started:
                logger.info("Using JavaScript MediaRecorder fallback for audio capture")
                # Expose callback for audio chunks
                await page.expose_function("sendAudioChunk", self._handle_audio_chunk)
                
                # Inject audio recording script
                audio_started = await self._inject_audio_recorder()
                
                if audio_started:
                    logger.info("✅ JavaScript audio recording started")
                else:
                    logger.warning("⚠️ Audio recording failed to start")
            
            # Mark as recording (video recording happens via Playwright context)
            self.is_recording = True
            return True
                
        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _inject_audio_recorder(self) -> bool:
        """Inject JavaScript to capture page audio without user interaction."""
        try:
            audio_script = """
            async () => {
                console.log("🎤 Initializing Audio Recorder...");
                
                // Check if already recording
                if (window.audioRecorder) {
                    console.log("Audio recorder already initialized");
                    return { success: true, message: "Already initialized" };
                }
                
                try {
                    // Create a silent audio context to capture page audio
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    
                    // Create a MediaStreamDestination to capture audio
                    const destination = audioContext.createMediaStreamDestination();
                    
                    // Try to find and capture audio from video elements on the page
                    const videoElements = document.querySelectorAll('video, audio');
                    console.log(`Found ${videoElements.length} media elements`);
                    
                    let audioSourceConnected = false;
                    
                    for (const mediaEl of videoElements) {
                        try {
                            if (mediaEl.srcObject) {
                                const source = audioContext.createMediaStreamSource(mediaEl.srcObject);
                                source.connect(destination);
                                audioSourceConnected = true;
                                console.log("✅ Connected audio from media element");
                            }
                        } catch (e) {
                            console.log("Could not connect media element:", e.message);
                        }
                    }
                    
                    // If no video elements, create a silent source (fallback)
                    if (!audioSourceConnected) {
                        console.log("No media elements found, will monitor for them...");
                        
                        // Monitor for new video elements
                        const observer = new MutationObserver((mutations) => {
                            const videos = document.querySelectorAll('video, audio');
                            videos.forEach(mediaEl => {
                                if (mediaEl.srcObject && !mediaEl.dataset.audioConnected) {
                                    try {
                                        const source = audioContext.createMediaStreamSource(mediaEl.srcObject);
                                        source.connect(destination);
                                        mediaEl.dataset.audioConnected = 'true';
                                        console.log("✅ Connected new audio source");
                                    } catch (e) {
                                        console.log("Error connecting audio:", e.message);
                                    }
                                }
                            });
                        });
                        
                        observer.observe(document.body, { childList: true, subtree: true });
                        window.audioMutationObserver = observer;
                    }
                    
                    // Create MediaRecorder for audio
                    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
                        ? 'audio/webm;codecs=opus' 
                        : 'audio/webm';
                    
                    const recorder = new MediaRecorder(destination.stream, {
                        mimeType: mimeType,
                        audioBitsPerSecond: 192000
                    });
                    
                    // Handle recorded chunks
                    recorder.ondataavailable = async (event) => {
                        if (event.data && event.data.size > 0) {
                            const arrayBuffer = await event.data.arrayBuffer();
                            const base64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
                            await window.sendAudioChunk({
                                data: base64,
                                size: event.data.size,
                                timestamp: Date.now()
                            });
                        }
                    };
                    
                    recorder.onerror = (event) => {
                        console.error("Audio recorder error:", event.error);
                    };
                    
                    // Start recording with 5-second chunks
                    recorder.start(5000);
                    
                    // Record audio start timestamp for synchronization
                    window.audioStartTimestamp = Date.now();
                    console.log("✅ Audio recording started at timestamp:", window.audioStartTimestamp);
                    
                    // Store globally
                    window.audioRecorder = recorder;
                    window.audioContext = audioContext;
                    
                    // Stop function
                    window.stopAudioRecording = () => {
                        console.log("⏹️ Stopping audio recording...");
                        if (recorder && recorder.state !== 'inactive') {
                            recorder.stop();
                        }
                        if (window.audioMutationObserver) {
                            window.audioMutationObserver.disconnect();
                        }
                        if (audioContext) {
                            audioContext.close();
                        }
                        console.log("✅ Audio recording stopped");
                    };
                    
                    return { success: true, mimeType };
                    
                } catch (error) {
                    console.error("Audio recording initialization error:", error);
                    return { success: false, error: error.message };
                }
            }
            """
            
            result = await self.page.evaluate(audio_script)
            
            if result.get("success"):
                logger.info(f"Audio recorder injected successfully. MIME: {result.get('mimeType')}")
                
                # Get audio start timestamp for synchronization
                try:
                    audio_ts = await self.page.evaluate("() => window.audioStartTimestamp")
                    if audio_ts:
                        self.audio_started_at_ms = int(audio_ts)
                        logger.info(f"Audio started at timestamp: {self.audio_started_at_ms}")
                        
                        # Calculate initial offset
                        if self.video_started_at_ms:
                            offset_ms = self.audio_started_at_ms - self.video_started_at_ms
                            logger.info(f"Audio-Video offset: {offset_ms}ms (audio {'after' if offset_ms > 0 else 'before'} video)")
                except Exception as ts_error:
                    logger.warning(f"Could not get audio timestamp: {ts_error}")
                
                return True
            else:
                logger.error(f"Audio recorder failed: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error injecting audio recorder: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def stop_recording(self) -> Dict[str, Any]:
        """
        Stop recording and finalize files.
        
        Returns:
            Dictionary with recording metadata and file paths
        """
        if not self.is_recording:
            logger.warning("No active recording to stop")
            return {}
        
        try:
            logger.info(f"Stopping recording: {self.recording_id}")
            
            # Stop audio recording (PulseAudio or JavaScript)
            pulse_audio_result = None
            if self.use_pulse_audio and self.pulse_capture:
                try:
                    pulse_audio_result = await self.pulse_capture.stop()
                    logger.info(f"PulseAudio recording stopped: {pulse_audio_result.get('duration', 0):.1f}s")
                except Exception as e:
                    logger.warning(f"Error stopping PulseAudio recording: {e}")
            else:
                # Stop JavaScript audio recording
                if self.page and not self.page.is_closed():
                    try:
                        await self.page.evaluate("() => { if (window.stopAudioRecording) window.stopAudioRecording(); }")
                        logger.info("JavaScript audio recording stopped")
                    except Exception as e:
                        logger.warning(f"Error stopping JavaScript audio recording: {e}")
            
            # Close page to finalize video
            if self.page and not self.page.is_closed():
                try:
                    # Get the video path from context before closing
                    if self.context:
                        video_path = await self.page.video.path()
                        logger.info(f"Playwright video saved to: {video_path}")
                        
                        # Move to our recording directory
                        if video_path and Path(video_path).exists():
                            shutil.move(video_path, str(self.video_file_path))
                            logger.info(f"Moved video to: {self.video_file_path}")
                        else:
                            logger.warning(f"Video path exists but file not found: {video_path}")
                except Exception as e:
                    logger.warning(f"Error getting video path: {e}")
                    # Try to find any video files in the temp directory
                    try:
                        temp_dir = self.temp_recordings_dir
                        if temp_dir.exists():
                            video_files = list(temp_dir.glob("*.webm"))
                            if video_files:
                                latest_video = max(video_files, key=lambda x: x.stat().st_mtime)
                                shutil.move(str(latest_video), str(self.video_file_path))
                                logger.info(f"Found and moved video from temp dir: {self.video_file_path}")
                    except Exception as move_error:
                        logger.warning(f"Could not recover video from temp dir: {move_error}")
            
            # Give time for final audio chunks
            await asyncio.sleep(2)
            
            # Finalize files
            recording_info = await self._finalize_recordings()
            
            self.is_recording = False
            logger.info(f"✅ Recording stopped: {self.recording_id}")
            
            return recording_info
            
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    async def _handle_audio_chunk(self, data: Dict[str, Any]) -> None:
        """Handle audio chunk from browser."""
        try:
            chunk_data = base64.b64decode(data["data"])
            self.audio_chunks.append(chunk_data)
            logger.debug(f"Audio chunk received: {data['size']} bytes (total chunks: {len(self.audio_chunks)})")
        except Exception as e:
            logger.error(f"Error handling audio chunk: {e}")
    
    async def _extract_audio(self) -> bool:
        """Extract audio from video file using ffmpeg."""
        try:
            if not self.video_file_path or not self.video_file_path.exists():
                logger.warning("Video file not found, cannot extract audio")
                return False
            
            logger.info("Extracting audio from video...")
            
            # Use ffmpeg to extract audio
            cmd = [
                "ffmpeg",
                "-i", str(self.video_file_path),
                "-vn",  # No video
                "-acodec", "libopus",
                "-b:a", "192k",
                "-ar", "48000",
                str(self.audio_file_path),
                "-y"  # Overwrite output file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"✅ Audio extracted to: {self.audio_file_path}")
                return True
            else:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return False
                
        except FileNotFoundError:
            logger.warning("ffmpeg not found - audio extraction skipped")
            logger.warning("To enable audio extraction, install ffmpeg: https://ffmpeg.org/download.html")
            return False
        except Exception as e:
            logger.error(f"Error extracting audio: {e}")
            return False
    
    async def _finalize_recordings(self) -> Dict[str, Any]:
        """Finalize recording files and upload to S3 if configured."""
        try:
            recording_info = {
                "recording_id": self.recording_id,
                "meeting_title": self.meeting_details.title if self.meeting_details else "Unknown",
                "started_at": self.recording_started_at.isoformat() if self.recording_started_at else None,
                "ended_at": datetime.now().isoformat(),
                "duration_seconds": (datetime.now() - self.recording_started_at).total_seconds() if self.recording_started_at else 0,
                "files": {}
            }
            
            # Check video file (video only from Playwright)
            temp_video_path = self.recording_dir / "video_temp.webm"
            if self.video_file_path and self.video_file_path.exists():
                # Rename to temp
                shutil.move(str(self.video_file_path), str(temp_video_path))
                logger.info(f"Video (no audio) saved: {temp_video_path}")
            else:
                logger.warning("Video file not found")
                temp_video_path = None
            
            # Get audio file - either from PulseAudio or JavaScript chunks
            temp_audio_path = None
            audio_source = "none"
            
            if self.use_pulse_audio and self.pulse_capture:
                # PulseAudio was used - get its output file
                pulse_audio_path = self.pulse_capture.get_audio_path()
                if pulse_audio_path and pulse_audio_path.exists():
                    temp_audio_path = pulse_audio_path
                    audio_source = "pulseaudio"
                    logger.info(f"Using PulseAudio audio: {temp_audio_path}")
                else:
                    logger.warning(f"PulseAudio file not found at: {pulse_audio_path}")
            
            # Fallback to JavaScript chunks if PulseAudio not available/failed
            if temp_audio_path is None and self.audio_chunks:
                temp_audio_path = self.recording_dir / "audio_temp.webm"
                logger.info(f"Writing JavaScript audio file: {len(self.audio_chunks)} chunks")
                with open(temp_audio_path, 'wb') as f:
                    for chunk in self.audio_chunks:
                        f.write(chunk)
                audio_source = "javascript"
                logger.info(f"JavaScript audio captured: {temp_audio_path}")
            
            if temp_audio_path is None:
                logger.warning("No audio captured (neither PulseAudio nor JavaScript)")
            
            recording_info["audio_source"] = audio_source
            
            # Merge video and audio using ffmpeg with synchronization
            if temp_video_path and temp_video_path.exists() and temp_audio_path and temp_audio_path.exists():
                try:
                    logger.info("Merging video and audio with ffmpeg (synchronized)...")
                    
                    # Calculate audio offset for synchronization
                    audio_offset_seconds = 0.0
                    if self.video_started_at_ms and self.audio_started_at_ms:
                        offset_ms = self.audio_started_at_ms - self.video_started_at_ms
                        audio_offset_seconds = offset_ms / 1000.0
                        logger.info(f"Applying audio offset: {audio_offset_seconds:.3f}s")
                        recording_info["sync_offset_seconds"] = audio_offset_seconds
                    else:
                        logger.warning("No timestamp data available - merging without offset correction")
                    
                    # Build ffmpeg command with proper synchronization
                    # -ss before input does input seeking (fast), -ss after input does output seeking (slow)
                    cmd = ["ffmpeg"]
                    
                    # Apply sync correction based on offset
                    if audio_offset_seconds > 0:
                        # Audio started AFTER video - trim the start of video to sync
                        # This is the common case: video records pre-join, audio starts after join
                        logger.info(f"Trimming {audio_offset_seconds:.1f}s from video start (audio starts later)")
                        cmd.extend(["-ss", f"{audio_offset_seconds:.3f}"])  # Seek into video
                        cmd.extend(["-i", str(temp_video_path)])
                        cmd.extend(["-i", str(temp_audio_path)])
                        cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
                    elif audio_offset_seconds < 0:
                        # Audio started before video - trim start of audio
                        trim_seconds = abs(audio_offset_seconds)
                        logger.info(f"Trimming {trim_seconds:.1f}s from audio start (audio starts earlier)")
                        cmd.extend(["-i", str(temp_video_path)])
                        cmd.extend(["-ss", f"{trim_seconds:.3f}"])  # Seek into audio
                        cmd.extend(["-i", str(temp_audio_path)])
                        cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
                    else:
                        # No offset needed - simple merge
                        cmd.extend(["-i", str(temp_video_path)])
                        cmd.extend(["-i", str(temp_audio_path)])
                        cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
                    
                    # Output options
                    cmd.extend([
                        "-c:v", "copy",            # Copy video codec (no re-encoding)
                        "-c:a", "libopus",         # Encode audio as Opus
                        "-b:a", "192k",            # Audio bitrate
                        "-shortest",               # End when shortest stream ends
                        str(self.video_file_path),
                        "-y"                       # Overwrite
                    ])
                    
                    logger.info(f"FFmpeg command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        file_size_mb = self.video_file_path.stat().st_size / (1024 * 1024)
                        recording_info["files"]["video_with_audio"] = {
                            "path": str(self.video_file_path),
                            "size_mb": round(file_size_mb, 2),
                            "audio_chunks": len(self.audio_chunks),
                            "sync_applied": audio_offset_seconds != 0
                        }
                        logger.info(f"✅ Video with audio saved (synced): {self.video_file_path} ({file_size_mb:.2f} MB)")
                        
                        # Clean up temp video file only, keep audio file
                        temp_video_path.unlink()
                        
                        # Record audio-only file in metadata
                        audio_size_kb = temp_audio_path.stat().st_size / 1024
                        recording_info["files"]["audio_only"] = {
                            "path": str(temp_audio_path),
                            "size_kb": round(audio_size_kb, 2)
                        }
                        logger.info(f"✅ Audio-only file kept: {temp_audio_path} ({audio_size_kb:.1f} KB)")
                    else:
                        logger.error(f"ffmpeg merge failed: {result.stderr}")
                        logger.warning("Keeping separate video and audio files")
                        
                        # Keep temp files as fallback
                        recording_info["files"]["video_only"] = {
                            "path": str(temp_video_path),
                            "size_mb": round(temp_video_path.stat().st_size / (1024 * 1024), 2)
                        }
                        recording_info["files"]["audio_only"] = {
                            "path": str(temp_audio_path),
                            "size_mb": round(temp_audio_path.stat().st_size / (1024 * 1024), 2),
                            "chunks": len(self.audio_chunks)
                        }
                        
                except FileNotFoundError:
                    logger.error("ffmpeg not found - cannot merge video and audio")
                    logger.error("Please ensure ffmpeg is installed in the Docker container")
                    # Keep temp files as fallback
                    if temp_video_path:
                        recording_info["files"]["video_only"] = {
                            "path": str(temp_video_path),
                            "size_mb": round(temp_video_path.stat().st_size / (1024 * 1024), 2)
                        }
                    if temp_audio_path:
                        recording_info["files"]["audio_only"] = {
                            "path": str(temp_audio_path),
                            "size_mb": round(temp_audio_path.stat().st_size / (1024 * 1024), 2),
                            "chunks": len(self.audio_chunks)
                        }
                except Exception as e:
                    logger.error(f"Error merging video and audio: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            elif temp_video_path and temp_video_path.exists():
                # Only video, no audio
                logger.warning("Only video available (no audio captured)")
                shutil.move(str(temp_video_path), str(self.video_file_path))
                file_size_mb = self.video_file_path.stat().st_size / (1024 * 1024)
                recording_info["files"]["video_only"] = {
                    "path": str(self.video_file_path),
                    "size_mb": round(file_size_mb, 2)
                }
            
            # Also save audio-only file for transcription
            if self.audio_chunks and self.audio_file_path:
                logger.info("Saving separate audio-only file for transcription...")
                with open(self.audio_file_path, 'wb') as f:
                    for chunk in self.audio_chunks:
                        f.write(chunk)
                
                file_size_mb = self.audio_file_path.stat().st_size / (1024 * 1024)
                recording_info["files"]["audio_for_transcription"] = {
                    "path": str(self.audio_file_path),
                    "size_mb": round(file_size_mb, 2),
                    "chunks": len(self.audio_chunks)
                }
                logger.info(f"✅ Audio-only file saved: {self.audio_file_path} ({file_size_mb:.2f} MB)")
            
            
            # Write metadata
            if self.recording_dir:
                metadata_path = self.recording_dir / "metadata.json"
                with open(metadata_path, 'w') as f:
                    json.dump(recording_info, f, indent=2)
            
            # Upload to S3 if S3 service is configured
            if self.s3_service and self.s3_service.is_enabled():
                try:
                    logger.info("Uploading recordings to S3...")
                    meeting_id = self.meeting_details.meeting_id or self.recording_id
                    
                    if self.video_file_path and self.video_file_path.exists():
                        video_s3_key = self.s3_service.upload_recording(
                            str(self.video_file_path),
                            meeting_id,
                            "video_audio"
                        )
                        if video_s3_key:
                            recording_info["files"]["video_audio"]["s3_key"] = video_s3_key
                            logger.info(f"✅ Video uploaded to S3: {video_s3_key}")
                    
                    if self.audio_file_path and self.audio_file_path.exists():
                        audio_s3_key = self.s3_service.upload_recording(
                            str(self.audio_file_path),
                            meeting_id,
                            "audio_only"
                        )
                        if audio_s3_key:
                            recording_info["files"]["audio_only"]["s3_key"] = audio_s3_key
                            logger.info(f"✅ Audio uploaded to S3: {audio_s3_key}")
                    
                except Exception as e:
                    logger.warning(f"S3 upload failed (files kept locally): {e}")
            
            logger.info(f"✅ Recording finalized: {self.recording_id}")
            logger.info(f"   Duration: {recording_info['duration_seconds']:.1f}s")
            
            return recording_info
            
        except Exception as e:
            logger.error(f"Error finalizing recordings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current recording status."""
        return {
            "is_recording": self.is_recording,
            "recording_id": self.recording_id,
            "started_at": self.recording_started_at.isoformat() if self.recording_started_at else None,
            "meeting_title": self.meeting_details.title if self.meeting_details else None
        }
