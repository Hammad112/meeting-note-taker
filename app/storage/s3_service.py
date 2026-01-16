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
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        
        # Initialize S3 client if credentials are available
        if self._credentials_available():
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name=self.region
                )
                logger.info("S3 service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                self.s3_client = None
        else:
            logger.warning("AWS credentials not configured. S3 upload will be disabled.")
    
    def _credentials_available(self) -> bool:
        """Check if AWS credentials are configured."""
        return bool(
            os.getenv("AWS_ACCESS_KEY_ID") and 
            os.getenv("AWS_SECRET_ACCESS_KEY") and 
            os.getenv("AWS_S3_BUCKET_NAME")
        )
    
    def upload_meeting_json(self, meeting_data: dict) -> str | None:
        """
        Upload meeting data as JSON to S3.
        
        Args:
            meeting_data: Dictionary containing meeting metadata and transcript
            
        Returns:
            S3 object key (path) if successful, None otherwise
        """
        if not self.s3_client:
            logger.warning("S3 client not initialized. Skipping upload.")
            return None
        
        try:
            # Generate S3 key (path) for the file
            meeting_id = meeting_data.get('metadata', {}).get('meeting_id', 'unknown')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            s3_key = f"meetings/{meeting_id}_{timestamp}.json"
            
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
