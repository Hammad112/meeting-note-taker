#!/usr/bin/env python3
"""
AWS S3 Configuration Test Script

This script helps verify your AWS S3 configuration for the meeting export feature.
Run this to test your AWS credentials before using the meeting bot.
"""

import os
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

def test_aws_config():
    """Test AWS S3 configuration."""
    print("🔍 Testing AWS S3 Configuration...\n")
    
    # Check environment variables
    print("1. Checking environment variables...")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    region = os.getenv("AWS_REGION", "us-east-1")
    
    if not access_key:
        print("   ❌ AWS_ACCESS_KEY_ID not set")
        return False
    else:
        print(f"   ✅ AWS_ACCESS_KEY_ID: {access_key[:8]}...")
    
    if not secret_key:
        print("   ❌ AWS_SECRET_ACCESS_KEY not set")
        return False
    else:
        print(f"   ✅ AWS_SECRET_ACCESS_KEY: {'*' * 20}")
    
    if not bucket_name:
        print("   ❌ AWS_S3_BUCKET_NAME not set")
        return False
    else:
        print(f"   ✅ AWS_S3_BUCKET_NAME: {bucket_name}")
    
    print(f"   ✅ AWS_REGION: {region}\n")
    
    # Test boto3 import
    print("2. Testing boto3 installation...")
    try:
        import boto3
        print(f"   ✅ boto3 version {boto3.__version__} installed\n")
    except ImportError:
        print("   ❌ boto3 not installed. Run: pip install boto3")
        return False
    
    # Test S3 connection
    print("3. Testing S3 connection...")
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        # Try to list bucket
        response = s3_client.head_bucket(Bucket=bucket_name)
        print(f"   ✅ Successfully connected to bucket: {bucket_name}\n")
        
    except Exception as e:
        print(f"   ❌ Failed to connect to S3: {e}\n")
        print("   Possible issues:")
        print("   - Invalid credentials")
        print("   - Bucket doesn't exist")
        print("   - Insufficient permissions")
        print("   - Network/firewall issues")
        return False
    
    # Test S3Service
    print("4. Testing S3Service class...")
    try:
        from app.storage.s3_service import S3Service
        s3_service = S3Service()
        
        if s3_service.is_enabled():
            print("   ✅ S3Service initialized successfully\n")
        else:
            print("   ❌ S3Service not enabled\n")
            return False
            
    except Exception as e:
        print(f"   ❌ Failed to initialize S3Service: {e}\n")
        return False
    
    # Test upload with sample data
    print("5. Testing sample upload...")
    try:
        test_data = {
            "metadata": {
                "meeting_id": "test_config",
                "meeting_url": "https://example.com/test",
                "platform": "test",
                "start_time": "2025-01-16T10:00:00",
                "end_time": "2025-01-16T10:30:00",
                "duration_seconds": 1800,
                "participant_names": ["Test User"]
            },
            "transcription": [
                {"timestamp": "10:00:00", "speaker": "Test User", "text": "This is a test."}
            ],
            "export_timestamp": "2025-01-16T10:30:01"
        }
        
        s3_path = s3_service.upload_meeting_json(test_data)
        
        if s3_path:
            print(f"   ✅ Successfully uploaded test file to: {s3_path}")
            print(f"   📝 You can verify the file in your S3 console\n")
        else:
            print("   ❌ Upload returned None\n")
            return False
            
    except Exception as e:
        print(f"   ❌ Failed to upload test file: {e}\n")
        return False
    
    print("=" * 60)
    print("✅ All tests passed! AWS S3 is configured correctly.")
    print("=" * 60)
    return True


if __name__ == "__main__":
    # Load .env file if it exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("📄 Loaded .env file\n")
    except ImportError:
        print("⚠️  python-dotenv not installed. Make sure to set environment variables.\n")
    
    success = test_aws_config()
    
    if not success:
        print("\n❌ Configuration test failed!")
        print("\nTo configure AWS S3:")
        print("1. Add to your .env file:")
        print("   AWS_ACCESS_KEY_ID=your_access_key")
        print("   AWS_SECRET_ACCESS_KEY=your_secret_key")
        print("   AWS_S3_BUCKET_NAME=your-bucket-name")
        print("   AWS_REGION=us-east-1")
        print("\n2. Make sure the S3 bucket exists and you have PutObject permissions")
        print("\n3. Run this script again to verify: python test_aws_config.py")
        sys.exit(1)
    else:
        print("\n🚀 You're ready to use the meeting export feature!")
        sys.exit(0)
