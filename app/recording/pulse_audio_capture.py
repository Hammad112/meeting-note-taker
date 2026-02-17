"""
PulseAudio-based Audio Capture for Meeting Bot

Captures system audio output using FFmpeg + PulseAudio.
This approach captures ALL audio played by the browser,
working reliably for both Google Meet and MS Teams.

Based on the reference implementation in example/audio-capture.ts
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from app.config import get_logger

logger = get_logger("pulse_audio")


class PulseAudioCapture:
    """
    Capture audio using PulseAudio + FFmpeg.
    
    This captures the system audio output (what the browser plays),
    which works regardless of how the meeting platform handles
    internal media streams.
    """
    
    def __init__(
        self,
        output_dir: Path,
        format: str = "opus",
        sample_rate: int = 16000,
        channels: int = 1,
        verbose: bool = False
    ):
        """
        Initialize PulseAudio capture.
        
        Args:
            output_dir: Directory to save audio file
            format: Audio format ('opus' or 'wav')
            sample_rate: Sample rate in Hz (16000 is good for speech)
            channels: Number of channels (1 = mono)
            verbose: Enable verbose logging
        """
        self.output_dir = Path(output_dir)
        self.format = format
        self.sample_rate = sample_rate
        self.channels = channels
        self.verbose = verbose
        
        # FFmpeg process
        self.ffmpeg_process: Optional[asyncio.subprocess.Process] = None
        
        # State tracking
        self.state = "idle"  # idle, starting, recording, stopping, stopped, error
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.audio_path: Optional[Path] = None
        
        # PulseAudio source (can be overridden via environment)
        self.pulse_source = os.getenv("PULSE_SOURCE", "default.monitor")
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    async def is_available() -> bool:
        """Check if PulseAudio is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            
            if proc.returncode == 0 and b"Server Name:" in stdout:
                logger.info("✓ PulseAudio is available")
                return True
            else:
                logger.warning("PulseAudio not available (pactl info failed)")
                return False
                
        except FileNotFoundError:
            logger.warning("pactl command not found - PulseAudio not installed")
            return False
        except asyncio.TimeoutError:
            logger.warning("PulseAudio check timed out")
            return False
        except Exception as e:
            logger.warning(f"Error checking PulseAudio: {e}")
            return False
    
    async def start(self) -> bool:
        """
        Start audio capture.
        
        Returns:
            True if capture started successfully
        """
        if self.state != "idle":
            logger.warning(f"Cannot start: current state is '{self.state}'")
            return False
        
        self.state = "starting"
        logger.info("Starting PulseAudio audio capture...")
        
        # Check PulseAudio availability
        if not await self.is_available():
            self.state = "error"
            logger.error("PulseAudio is not available")
            return False
        
        # Set default sink (ensure audio goes to the right place)
        try:
            pulse_sink = os.getenv("PULSE_SINK", "default")
            proc = await asyncio.create_subprocess_exec(
                "pactl", "set-default-sink", pulse_sink,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
        except Exception as e:
            logger.debug(f"Could not set default sink: {e}")
        
        # Set up audio file path
        extension = "wav" if self.format == "wav" else "opus"
        self.audio_path = self.output_dir / f"audio.{extension}"
        
        # Build FFmpeg command
        ffmpeg_args = self._build_ffmpeg_args()
        logger.info(f"FFmpeg command: ffmpeg {' '.join(ffmpeg_args)}")
        
        # Record start time BEFORE spawning (for accurate sync)
        self.start_time = datetime.now()
        
        try:
            self.ffmpeg_process = await asyncio.create_subprocess_exec(
                "ffmpeg", *ffmpeg_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait a bit for FFmpeg to initialize
            await asyncio.sleep(1.0)
            
            # Check if process is still running
            if self.ffmpeg_process.returncode is not None:
                stderr = await self.ffmpeg_process.stderr.read()
                logger.error(f"FFmpeg exited immediately: {stderr.decode()}")
                self.state = "error"
                return False
            
            self.state = "recording"
            logger.info("✓ PulseAudio audio capture started successfully")
            return True
            
        except FileNotFoundError:
            logger.error("ffmpeg command not found")
            self.state = "error"
            return False
        except Exception as e:
            logger.error(f"Failed to start FFmpeg: {e}")
            self.state = "error"
            return False
    
    async def stop(self) -> Dict[str, Any]:
        """
        Stop audio capture.
        
        Returns:
            Dictionary with capture results
        """
        if self.state not in ("recording", "starting"):
            logger.warning(f"stop() called but state is '{self.state}'")
            return self._build_result(success=False, error=f"Invalid state: {self.state}")
        
        self.state = "stopping"
        logger.info("Stopping PulseAudio audio capture...")
        
        if not self.ffmpeg_process:
            self.end_time = datetime.now()
            self.state = "stopped"
            return self._build_result(success=False, error="No FFmpeg process found")
        
        try:
            # Send 'q' to FFmpeg for graceful stop
            if self.ffmpeg_process.stdin:
                self.ffmpeg_process.stdin.write(b"q")
                await self.ffmpeg_process.stdin.drain()
            
            # Wait for process to finish (with timeout)
            try:
                await asyncio.wait_for(self.ffmpeg_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("FFmpeg didn't exit gracefully, killing...")
                self.ffmpeg_process.kill()
                await self.ffmpeg_process.wait()
            
            self.end_time = datetime.now()
            self.state = "stopped"
            
            result = self._build_result(success=True)
            logger.info(f"✓ Audio capture stopped. Duration: {result['duration']:.1f}s, Size: {result['file_size_kb']:.1f}KB")
            return result
            
        except Exception as e:
            logger.error(f"Error stopping FFmpeg: {e}")
            self.end_time = datetime.now()
            self.state = "error"
            return self._build_result(success=False, error=str(e))
    
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.state == "recording"
    
    def get_audio_path(self) -> Optional[Path]:
        """Get path to the recorded audio file."""
        return self.audio_path
    
    def _build_ffmpeg_args(self) -> list:
        """Build FFmpeg command arguments."""
        args = [
            # Overwrite output file if exists
            "-y",
            
            # Input: PulseAudio
            "-f", "pulse",
            "-i", self.pulse_source,
            
            # Audio settings
            "-ac", str(self.channels),
            "-ar", str(self.sample_rate),
            
            # Safety duration limit (4 hours)
            "-t", "14400",
        ]
        
        # Output format specific settings
        if self.format == "wav":
            args.extend([
                "-c:a", "pcm_s16le"  # 16-bit PCM (standard WAV)
            ])
        else:
            # Opus
            args.extend([
                "-c:a", "libopus",
                "-application", "voip",  # Optimized for speech
                "-b:a", "32k",           # 32kbps (good for speech)
                "-vbr", "on"             # Variable bitrate
            ])
        
        # Output file
        args.append(str(self.audio_path))
        
        return args
    
    def _build_result(self, success: bool, error: Optional[str] = None) -> Dict[str, Any]:
        """Build result dictionary."""
        file_size = 0
        
        if self.audio_path and self.audio_path.exists():
            try:
                file_size = self.audio_path.stat().st_size
            except:
                pass
        
        duration = 0.0
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        
        return {
            "audio_path": str(self.audio_path) if self.audio_path else "",
            "start_time": self.start_time.timestamp() if self.start_time else 0,
            "end_time": self.end_time.timestamp() if self.end_time else 0,
            "duration": duration,
            "file_size": file_size,
            "file_size_kb": file_size / 1024,
            "success": success and file_size > 0,
            "error": error or (None if file_size > 0 else "No audio data captured"),
        }
