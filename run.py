"""
Entry point for Meeting Bot API.
Starts the FastAPI application with production-grade structure.
"""

import sys
import os
import uvicorn

# Add the current directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import settings
from app.core.config import settings


def run():
    """Run the Meeting Bot API server."""
    print("\n" + "=" * 60)
    print("MEETING BOT API - Production Server")
    print("=" * 60)
    print(f"🚀 Starting FastAPI application...")
    print(f"📍 Host: {settings.auth_server.host}:{settings.auth_server.port}")
    print(f"📚 API Docs: http://{settings.auth_server.host}:{settings.auth_server.port}/api/docs")
    print(f"🔐 Dashboard: http://{settings.auth_server.host}:{settings.auth_server.port}/api/v1/auth")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        "app.main:app",
        host=settings.auth_server.host,
        port=settings.auth_server.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
