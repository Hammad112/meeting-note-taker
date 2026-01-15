from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path

from config import get_logger

logger = get_logger("transcription_service")

class TranscriptionService:
    """
    Handles saving meeting transcriptions to local files.
    """

    def __init__(self, output_dir: str = "transcripts") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_file: Path | None = None
        self._file_handle = None

    def start_transcription(self, meeting_id: str) -> None:
        """
        Starts a new transcription session for a given meeting ID.
        Creates a file named 'transcript_{meeting_id}_{timestamp}.txt'.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_id = "".join(c for c in meeting_id if c.isalnum() or c in ("-", "_"))
        filename = f"transcript_{safe_id}_{timestamp}.txt"
        self.current_file = self.output_dir / filename
        
        try:
            self._file_handle = open(self.current_file, "a", encoding="utf-8")
            logger.info(f"Started transcription: {self.current_file}")
            self._write_line(f"--- Transcription started for {meeting_id} at {datetime.now()} ---")
        except Exception as e:
            logger.error(f"Failed to open transcript file: {e}")

    def stop_transcription(self) -> None:
        """Closes the current transcript file."""
        if self._file_handle:
            try:
                self._write_line(f"--- Transcription ended at {datetime.now()} ---")
                self._file_handle.close()
            except Exception as e:
                logger.error(f"Error closing transcript file: {e}")
            finally:
                self._file_handle = None
                logger.info(f"Stopped transcription: {self.current_file}")
                self.current_file = None

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
