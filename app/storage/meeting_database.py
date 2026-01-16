"""
Meeting Database - Local JSON database mapping meeting URLs to S3 file paths.
"""
import json
import os
from pathlib import Path
from threading import Lock
from datetime import datetime
from app.config.logger import logger


class MeetingDatabase:
    """Manages local JSON database of meeting URLs and their S3 file paths."""
    
    def __init__(self, db_path: str = "data/meeting_database.json"):
        self.db_path = Path(db_path)
        self.lock = Lock()
        
        # Create data directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database file if it doesn't exist
        if not self.db_path.exists():
            self._initialize_db()
            logger.info(f"Created new meeting database at {self.db_path}")
        else:
            logger.info(f"Using existing meeting database at {self.db_path}")
    
    def _initialize_db(self):
        """Create an empty database file."""
        initial_data = {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "meetings": {}
        }
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=2, ensure_ascii=False)
    
    def _load_db(self) -> dict:
        """Load database from file."""
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load database: {e}")
            return {"meetings": {}}
    
    def _save_db(self, data: dict):
        """Save database to file."""
        try:
            data["last_updated"] = datetime.now().isoformat()
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save database: {e}")
    
    def add_meeting(self, meeting_url: str, s3_path: str, metadata: dict = None):
        """
        Add or update a meeting entry in the database.
        
        Args:
            meeting_url: The meeting URL (unique identifier)
            s3_path: The S3 path/URL where the meeting JSON is stored
            metadata: Optional additional metadata to store
        """
        with self.lock:
            db = self._load_db()
            
            entry = {
                "s3_path": s3_path,
                "added_at": datetime.now().isoformat()
            }
            
            if metadata:
                entry["metadata"] = metadata
            
            db["meetings"][meeting_url] = entry
            self._save_db(db)
            
            logger.info(f"Added meeting to database: {meeting_url} -> {s3_path}")
    
    def get_meeting(self, meeting_url: str) -> dict | None:
        """
        Get meeting entry by URL.
        
        Args:
            meeting_url: The meeting URL to look up
            
        Returns:
            Meeting entry dict or None if not found
        """
        with self.lock:
            db = self._load_db()
            return db.get("meetings", {}).get(meeting_url)
    
    def get_all_meetings(self) -> dict:
        """Get all meeting entries."""
        with self.lock:
            db = self._load_db()
            return db.get("meetings", {})
    
    def meeting_exists(self, meeting_url: str) -> bool:
        """Check if a meeting URL exists in the database."""
        return self.get_meeting(meeting_url) is not None
