from __future__ import annotations
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Set, Optional

from app.config import get_logger

logger = get_logger("transcription_service")

class TranscriptionService:
    """
    Handles saving meeting transcriptions to local files and exporting to JSON.
    """

    def __init__(self, output_dir: str = "transcripts") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_file: Path | None = None
        self._file_handle = None
        
        # Metadata tracking
        self.meeting_details = None
        self.meeting_start_time: Optional[datetime] = None
        self.meeting_end_time: Optional[datetime] = None
        self.participants: Set[str] = set()
        self.transcript_lines: list = []  # Store for JSON export

    def start_transcription(self, meeting_id: str, meeting_details=None) -> None:
        """
        Starts a new transcription session for a given meeting ID.
        Creates a file named 'transcript_{meeting_id}_{timestamp}.txt'.
        
        Args:
            meeting_id: Unique meeting identifier
            meeting_details: MeetingDetails object containing metadata
        """
        self.meeting_start_time = datetime.now()
        self.meeting_details = meeting_details
        self.participants = set()
        self.transcript_lines = []
        
        timestamp = self.meeting_start_time.strftime("%Y%m%d_%H%M%S")
        safe_id = "".join(c for c in meeting_id if c.isalnum() or c in ("-", "_"))
        filename = f"transcript_{safe_id}_{timestamp}.txt"
        self.current_file = self.output_dir / filename
        
        try:
            self._file_handle = open(self.current_file, "a", encoding="utf-8")
            logger.info(f"Started transcription: {self.current_file}")
            self._write_line(f"--- Transcription started for {meeting_id} at {self.meeting_start_time} ---")
        except Exception as e:
            logger.error(f"Failed to open transcript file: {e}")

    def stop_transcription(self) -> None:
        """Closes the current transcript file and records end time."""
        self.meeting_end_time = datetime.now()
        
        if self._file_handle:
            try:
                self._write_line(f"--- Transcription ended at {self.meeting_end_time} ---")
                self._file_handle.close()
            except Exception as e:
                logger.error(f"Error closing transcript file: {e}")
            finally:
                self._file_handle = None
                logger.info(f"Stopped transcription: {self.current_file}")
                # Don't reset metadata yet - we need it for JSON export

    def append_transcript(self, speaker: str, text: str, timestamp: str = None) -> None:
        """
        Appends a new line of transcript.
        
        Args:
            speaker: Name of the speaker
            text: The transcribed text
            timestamp: Optional ISO timestamp from caption capture. If not provided, uses current time.
        """
        if not self._file_handle:
            return

        # Track unique participants
        if speaker and speaker.lower() not in ['system', 'unknown']:
            self.participants.add(speaker)

        # Use provided timestamp or current time
        if timestamp:
            try:
                # Parse ISO timestamp and format as local time
                from datetime import timezone
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.astimezone().strftime("%H:%M:%S")
            except:
                time_str = datetime.now().strftime("%H:%M:%S")
        else:
            time_str = datetime.now().strftime("%H:%M:%S")
        
        # Store for JSON export
        self.transcript_lines.append({
            "timestamp": time_str,
            "speaker": speaker,
            "text": text
        })
        
        # Simple format: [Time] Speaker: Text
        line = f"[{time_str}] {speaker}: {text}"
        self._write_line(line)

    def _write_line(self, line: str) -> None:
        if self._file_handle:
            try:
                self._file_handle.write(line + "\n")
                self._file_handle.flush()
            except Exception as e:
                logger.error(f"Failed to write to transcript: {e}")
    
    def export_to_json(self) -> dict:
        """
        Export meeting data to a JSON-serializable dictionary.
        
        Returns:
            Dictionary containing metadata and full transcription
        """
        # Calculate duration
        duration_seconds = 0
        if self.meeting_start_time and self.meeting_end_time:
            duration_seconds = int((self.meeting_end_time - self.meeting_start_time).total_seconds())
        
        # Build metadata
        metadata = {
            "meeting_id": self.meeting_details.meeting_id if self.meeting_details else "unknown",
            "meeting_url": self.meeting_details.meeting_url if self.meeting_details else None,
            "platform": self.meeting_details.platform if self.meeting_details else "unknown",
            "title": self.meeting_details.title if self.meeting_details else None,
            "start_time": self.meeting_start_time.isoformat() if self.meeting_start_time else None,
            "end_time": self.meeting_end_time.isoformat() if self.meeting_end_time else None,
            "duration_seconds": duration_seconds,
            "participant_names": sorted(list(self.participants)),
            "transcript_file": str(self.current_file) if self.current_file else None
        }
        
        # Add optional fields if available
        if self.meeting_details:
            if self.meeting_details.organizer:
                metadata["organizer"] = self.meeting_details.organizer
            if self.meeting_details.organizer_email:
                metadata["organizer_email"] = self.meeting_details.organizer_email
            if self.meeting_details.description:
                metadata["description"] = self.meeting_details.description
        
        # Build complete JSON structure
        return {
            "metadata": metadata,
            "transcription": self.transcript_lines,
            "export_timestamp": datetime.now().isoformat()
        }
    
    def reset_metadata(self) -> None:
        """Reset metadata after export is complete."""
        self.current_file = None
        self.meeting_details = None
        self.meeting_start_time = None
        self.meeting_end_time = None
        self.participants = set()
        self.transcript_lines = []
