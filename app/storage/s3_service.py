"""
S3 Service for uploading meeting transcripts and metadata.
"""
import os
import json
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from app.config.logger import logger


class S3Service:
    """Handles uploading meeting data to AWS S3."""
    
    def __init__(self, bucket_name: str = None, access_key_id: str = None, 
                 secret_access_key: str = None, region: str = None):
        self.s3_client = None
        
        # Use provided credentials or fall back to environment variables
        self.bucket_name = bucket_name or os.getenv("AWS_S3_BUCKET_NAME")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        access_key = access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        
        # Initialize S3 client if credentials are available
        if self._credentials_available(access_key, secret_key):
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name=self.region
                )
                logger.info(f"S3 service initialized successfully for bucket: {self.bucket_name}")
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                self.s3_client = None
        else:
            logger.warning("AWS credentials not configured. S3 upload will be disabled.")
    
    def _credentials_available(self, access_key: str = None, secret_key: str = None) -> bool:
        """Check if AWS credentials are configured."""
        return bool(
            access_key and 
            secret_key and 
            self.bucket_name
        )
    
    def _sanitize_meeting_id(self, meeting_id: str) -> str:
        """
        Sanitize meeting ID for use as S3 directory name.
        Removes/replaces characters that are problematic in S3 keys.
        
        Args:
            meeting_id: Raw meeting ID or link name
            
        Returns:
            Sanitized string safe for S3 key usage
        """
        import re
        # Remove or replace problematic characters
        # Keep alphanumeric, dashes, underscores, and dots
        sanitized = re.sub(r'[^a-zA-Z0-9\-_.]+', '_', meeting_id)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        # Limit length to avoid issues
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        return sanitized or 'unknown'
    
    def upload_meeting_json(self, meeting_data: dict, meeting_id: str = None) -> str | None:
        """
        Upload meeting data as JSON to S3.
        
        Structure: {meeting_id}/json/transcript_{timestamp}.json
        
        Args:
            meeting_data: Dictionary containing meeting metadata and transcript
            meeting_id: Optional meeting ID override (uses metadata if not provided)
            
        Returns:
            S3 object key (path) if successful, None otherwise
        """
        if not self.s3_client:
            logger.warning("S3 client not initialized. Skipping upload.")
            return None
        
        try:
            # Get meeting ID from parameter or metadata
            if not meeting_id:
                meeting_id = meeting_data.get('metadata', {}).get('meeting_id', 'unknown')
            
            # Sanitize meeting ID for S3 key
            safe_meeting_id = self._sanitize_meeting_id(meeting_id)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # New organized structure: {meeting_id}/json/
            s3_key = f"{safe_meeting_id}/json/transcript_{timestamp}.json"
            
            # Convert dict to JSON string
            json_content = json.dumps(meeting_data, indent=2, ensure_ascii=False)
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_content.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'meeting_id': meeting_id,
                    'upload_timestamp': timestamp
                }
            )
            
            # Construct S3 URL
            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            logger.info(f"Successfully uploaded meeting data to S3: {s3_url}")
            return s3_url
            
        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during S3 upload: {e}")
            return None
    
    def is_enabled(self) -> bool:
        """Check if S3 service is enabled and ready."""
        return self.s3_client is not None
    
    def upload_speaking_json(self, speaking_data: dict, meeting_id: str) -> str | None:
        """
        Upload speaking tracker data as JSON to S3.
        
        Structure: {meeting_id}/json/speaking_{timestamp}.json
        
        Args:
            speaking_data: Dictionary containing speaking segments and participant events
            meeting_id: Meeting identifier for directory naming
            
        Returns:
            S3 URL if successful, None otherwise
        """
        if not self.s3_client:
            logger.warning("S3 client not initialized. Skipping speaking data upload.")
            return None
        
        try:
            # Sanitize meeting ID for S3 key
            safe_meeting_id = self._sanitize_meeting_id(meeting_id)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Store in same json directory as transcript
            s3_key = f"{safe_meeting_id}/json/speaking_{timestamp}.json"
            
            # Convert dict to JSON string
            json_content = json.dumps(speaking_data, indent=2, ensure_ascii=False)
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_content.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'meeting_id': meeting_id,
                    'data_type': 'speaking_tracker',
                    'upload_timestamp': timestamp
                }
            )
            
            # Construct S3 URL
            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            logger.info(f"✅ Successfully uploaded speaking data to S3: {s3_url}")
            return s3_url
            
        except ClientError as e:
            logger.error(f"Failed to upload speaking data to S3: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during speaking data upload: {e}")
            return None

    def upload_recording(self, file_path: str, meeting_id: str, recording_type: str = "video") -> str | None:
        """
        Upload a recording file (video or audio) to S3.
        
        Structure:
            - Video files: {meeting_id}/video/{filename}
            - Audio files: {meeting_id}/audio/{filename}
        
        Args:
            file_path: Local path to the recording file
            meeting_id: Meeting identifier
            recording_type: Type of recording ("video_audio", "video_only", "audio_only", "audio_transcription")
            
        Returns:
            S3 object key (path) if successful, None otherwise
        """
        if not self.s3_client:
            logger.warning("S3 client not initialized. Skipping recording upload.")
            return None
        
        try:
            import os
            from pathlib import Path
            
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"Recording file not found: {file_path}")
                return None
            
            # Sanitize meeting ID for S3 key
            safe_meeting_id = self._sanitize_meeting_id(meeting_id)
            
            # Generate S3 key (path) for the recording
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = file_path_obj.suffix
            
            # Determine directory based on recording type
            # video_audio, video_only -> video directory
            # audio_only, audio_transcription -> audio directory
            if recording_type in ("video_audio", "video_only"):
                directory = "video"
                content_type = "video/webm"
                if file_extension == ".mp4":
                    content_type = "video/mp4"
                elif file_extension == ".mkv":
                    content_type = "video/x-matroska"
            else:
                directory = "audio"
                content_type = "audio/webm"
                if file_extension == ".mp4":
                    content_type = "audio/mp4"
                elif file_extension == ".wav":
                    content_type = "audio/wav"
                elif file_extension == ".mp3":
                    content_type = "audio/mpeg"
            
            # New organized structure: {meeting_id}/video/ or {meeting_id}/audio/
            s3_key = f"{safe_meeting_id}/{directory}/{recording_type}_{timestamp}{file_extension}"
            
            # Upload file to S3
            logger.info(f"Uploading {recording_type} recording to S3: {s3_key}")
            
            with open(file_path, 'rb') as f:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=f,
                    ContentType=content_type,
                    Metadata={
                        'meeting_id': meeting_id,
                        'recording_type': recording_type,
                        'upload_timestamp': timestamp
                    }
                )
            
            # Construct S3 URL
            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            file_size_mb = file_path_obj.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Successfully uploaded {recording_type} to S3: {s3_url} ({file_size_mb:.2f} MB)")
            return s3_key
            
        except ClientError as e:
            logger.error(f"Failed to upload recording to S3: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during recording upload: {e}")
            return None

