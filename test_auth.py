#!/usr/bin/env python3
"""
Test script for the new authentication system.
Run this to verify authentication is working correctly.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings, AuthMethod
from auth_server import start_auth_server, stop_auth_server
from email_service.gmail import GmailService


async def test_auth_server():
    """Test that the authentication server starts correctly."""
    print("\n" + "="*60)
    print("Testing Authentication Server")
    print("="*60)
    
    try:
        auth_server = await start_auth_server(
            host=settings.auth_server.host,
            port=settings.auth_server.port
        )
        print(f"✅ Auth server started successfully")
        print(f"   URL: http://{settings.auth_server.host}:{settings.auth_server.port}")
        
        # Wait a moment
        await asyncio.sleep(1)
        
        await stop_auth_server()
        print(f"✅ Auth server stopped successfully")
        return True
    except Exception as e:
        print(f"❌ Auth server test failed: {e}")
        return False


async def test_gmail_oauth():
    """Test Gmail OAuth authentication."""
    print("\n" + "="*60)
    print("Testing Gmail OAuth Authentication")
    print("="*60)
    
    if not os.path.exists(settings.gmail.token_file):
        print(f"⚠️  No OAuth token found at {settings.gmail.token_file}")
        print(f"   Please authenticate first:")
        print(f"   1. Set GMAIL_AUTH_METHOD=oauth")
        print(f"   2. Visit http://localhost:{settings.auth_server.port}/auth/gmail/start")
        return None
    
    try:
        service = GmailService()
        # Temporarily set to OAuth mode
        original_method = service._settings.auth_method
        service._settings.auth_method = AuthMethod.OAUTH
        
        success = await service.authenticate()
        
        # Restore original method
        service._settings.auth_method = original_method
        
        if success:
            print("✅ Gmail OAuth authentication successful")
            print(f"   Token file: {settings.gmail.token_file}")
            return True
        else:
            print("❌ Gmail OAuth authentication failed")
            return False
    except Exception as e:
        print(f"❌ Gmail OAuth test failed: {e}")
        return False


async def test_gmail_credentials():
    """Test Gmail direct credentials authentication."""
    print("\n" + "="*60)
    print("Testing Gmail Direct Credentials Authentication")
    print("="*60)
    
    email = settings.gmail.email
    password = settings.gmail.password
    
    # Also check credentials file
    if not (email and password):
        if os.path.exists(settings.gmail.direct_credentials_file):
            print(f"✅ Found credentials file at {settings.gmail.direct_credentials_file}")
        else:
            print(f"⚠️  No credentials found")
            print(f"   Please set either:")
            print(f"   1. GMAIL_EMAIL and GMAIL_PASSWORD environment variables")
            print(f"   2. Create {settings.gmail.direct_credentials_file}")
            print(f"   3. Use the web form at http://localhost:{settings.auth_server.port}")
            return None
    
    try:
        service = GmailService()
        # Temporarily set to CREDENTIALS mode
        original_method = service._settings.auth_method
        service._settings.auth_method = AuthMethod.CREDENTIALS
        
        success = await service.authenticate()
        
        # Restore original method
        service._settings.auth_method = original_method
        
        if success:
            print("✅ Gmail credentials authentication successful")
            print(f"   Email: {email if email else '[from file]'}")
            return True
        else:
            print("❌ Gmail credentials authentication failed")
            print("   Make sure you're using an App Password (not regular password)")
            print("   Generate one at: https://myaccount.google.com/apppasswords")
            return False
    except Exception as e:
        print(f"❌ Gmail credentials test failed: {e}")
        return False


async def test_auto_mode():
    """Test auto authentication mode."""
    print("\n" + "="*60)
    print("Testing Auto Mode Authentication")
    print("="*60)
    
    try:
        service = GmailService()
        # Use actual auto mode
        service._settings.auth_method = AuthMethod.AUTO
        
        success = await service.authenticate()
        
        if success:
            print("✅ Auto mode authentication successful")
            return True
        else:
            print("⚠️  Auto mode couldn't authenticate")
            print("   This is expected if no credentials are configured")
            return False
    except Exception as e:
        print(f"❌ Auto mode test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("🤖 Meeting Bot - Authentication System Test")
    print("="*60)
    
    print("\n📋 Current Configuration:")
    print(f"   Auth Method: {settings.gmail.auth_method.value}")
    print(f"   Auth Server Enabled: {settings.auth_server.enabled}")
    print(f"   Auth Server Port: {settings.auth_server.port}")
    print(f"   Gmail Email: {settings.gmail.email or '[not set]'}")
    print(f"   Gmail Token File: {settings.gmail.token_file}")
    print(f"   Gmail Creds File: {settings.gmail.direct_credentials_file}")
    
    # Run tests
    results = []
    
    # Test 1: Auth Server
    result = await test_auth_server()
    results.append(("Auth Server", result))
    
    # Test 2: OAuth (if token exists)
    result = await test_gmail_oauth()
    if result is not None:
        results.append(("Gmail OAuth", result))
    
    # Test 3: Credentials (if configured)
    result = await test_gmail_credentials()
    if result is not None:
        results.append(("Gmail Credentials", result))
    
    # Test 4: Auto Mode
    result = await test_auto_mode()
    results.append(("Auto Mode", result))
    
    # Summary
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    
    for test_name, result in results:
        if result is True:
            print(f"✅ {test_name}")
        elif result is False:
            print(f"❌ {test_name}")
        else:
            print(f"⚠️  {test_name} (skipped)")
    
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    
    if failed > 0:
        print("\n⚠️  Some tests failed. Please check the error messages above.")
        print("   For help, see: AUTHENTICATION.md and QUICKSTART.md")
    else:
        print("\n✅ All tests passed! Authentication system is working correctly.")
    
    print("\n" + "="*60)
    print("Next Steps:")
    print("="*60)
    
    if not any(result is True for _, result in results[1:]):  # No auth method worked
        print(f"1. Visit http://localhost:{settings.auth_server.port} to authenticate")
        print("2. Or set up credentials in .env file")
        print("3. See QUICKSTART.md for detailed instructions")
    else:
        print("1. Your authentication is configured!")
        print("2. Run: python -m meeting_bot")
        print("3. The bot will start monitoring your calendar")
    
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)
