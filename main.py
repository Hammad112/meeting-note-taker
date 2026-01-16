"""
FastAPI Entry Point for Meeting Bot.
Consolidated backend logic and endpoint definitions.
No HTML frontend; strictly JSON-based API.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.bot import MeetingBot
from app.config import settings, logger
from app.auth_server import AuthManager

# Initialize core bot
bot = MeetingBot()
# Initialize auth manager (pure logic service)
auth_manager = AuthManager(meeting_bot=bot)

# In-memory storage for reported meetings and sessions
reported_meetings: Dict[str, Any] = {}
reported_sessions: Dict[str, Any] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    logger.info("Starting Meeting Bot application...")
    
    # Startup: Initialize and run the bot
    try:
        await bot.initialize()
        # Schedule the bot logic to run in background
        asyncio.create_task(bot.run())
    except Exception as e:
        logger.error(f"Failed to start bot during startup: {e}")
    
    yield
    
    # Shutdown: Gracefully stop the bot
    await bot.shutdown()
    logger.info("Meeting Bot application shut down")

# Documentation Guide
DESC = """
## 🚀 Meeting Bot API Guide

This is the unified backend for the Meeting Bot. Follow these steps to get started:

### 1. 🔑 Authentication
The bot needs permission to read your calendars. If the logs show "AUTHENTICATION REQUIRED", visit:
* **Gmail**: [/auth/gmail/start](/auth/gmail/start)
* **Outlook**: [/auth/outlook/start](/auth/outlook/start)

### 2. 🤖 Manual Join
If you want the bot to join a specific meeting immediately, use the **Manual Join** endpoint below.

### 3. 📊 Monitoring
Check the **Status** and **Sessions** endpoints to see what the bot is currently doing.
"""

app = FastAPI(
    title="Meeting Bot API",
    description=DESC,
    version="1.5.0",
    lifespan=lifespan
)

# Models
class ManualJoinRequest(BaseModel):
    bot_name: str = Field(..., json_schema_extra={"examples": ["Bot-01"]})
    meeting_url: str = Field(..., json_schema_extra={"examples": ["https://meet.google.com/abc-defg-hij"]})

class MeetingReport(BaseModel):
    meeting_id: str
    title: str
    start_time: str
    end_time: str
    meeting_url: str
    platform: str
    source: str
    organizer: str

class SessionReport(BaseModel):
    session_id: str
    meeting_id: str
    bot_name: str
    platform: str
    start_time: str

# --- 1. Global Status & Health ---

@app.get("/", tags=["Status"], summary="Root Health Check")
async def root():
    """Returns general application health and a directory of key endpoints."""
    return {
        "status": "online",
        "bot_status": bot.get_status(),
        "auth_status": auth_manager.get_auth_status(),
        "endpoints": {
            "status": "GET /api/status",
            "sessions": "GET /api/sessions",
            "manual_join": "POST /api/join",
            "gmail_auth": "GET /auth/gmail/start",
            "outlook_auth": "GET /auth/outlook/start"
        }
    }

# --- 2. Authentication Flow Endpoints ---

@app.get("/auth/gmail/start", tags=["Authentication"], summary="Start Gmail OAuth")
async def gmail_auth_start(request: Request):
    """
    Initiates the Google OAuth2 flow. 
    Redirects the user to the Google login page.
    """
    host = request.headers.get("host", "localhost:8888")
    result = auth_manager.get_gmail_auth_url(host)
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    
    return RedirectResponse(result["auth_url"])

@app.get("/auth/gmail/callback", tags=["Authentication"], summary="Gmail OAuth Callback")
async def gmail_auth_callback(request: Request):
    """
    Handles the callback from Google. 
    Saves the credentials and activates the bot's Gmail service.
    """
    state = request.query_params.get('state')
    code = request.query_params.get('code')
    
    result = auth_manager.complete_gmail_auth(state, code)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    
    return {
        "status": "success",
        "message": "Gmail authentication successful. You can now close this tab.",
        "details": result
    }

@app.get("/auth/outlook/start", tags=["Authentication"], summary="Start Outlook OAuth")
async def outlook_auth_start():
    """
    Initiates the Microsoft Outlook OAuth2 flow. 
    Redirects the user to the Microsoft login page.
    """
    result = auth_manager.get_outlook_auth_url()
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    
    return RedirectResponse(result["auth_url"])

@app.get("/auth/outlook/callback", tags=["Authentication"], summary="Outlook OAuth Callback")
async def outlook_auth_callback(request: Request):
    """
    Handles the callback from Microsoft. 
    Saves the credentials and activates the bot's Outlook service.
    """
    code = request.query_params.get('code')
    
    result = auth_manager.complete_outlook_auth(code)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    
    return {
        "status": "success",
        "message": "Outlook authentication successful. You can now close this tab.",
        "details": result
    }

@app.get("/auth/status", tags=["Status"])
async def auth_status():
    """Returns the current authentication status for all providers (Gmail, Outlook)."""
    return auth_manager.get_auth_status()

# --- 3. Functional Bot API Endpoints ---

@app.get("/api/status", tags=["Bot API"], summary="Get Bot Runtime Status")
async def get_bot_status():
    """Detailed operational status of the bot, including scheduler state."""
    return bot.get_status()

@app.post("/api/join", tags=["Bot API"])
async def manual_join(request: ManualJoinRequest):
    """
    Manually triggers the bot to join a meeting.
    Payload: { "bot_name": "MyBot", "meeting_url": "https://..." }
    """
    result = await bot.manual_join_meeting(request.bot_name, request.meeting_url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to join meeting"))
    return result

@app.get("/api/sessions", tags=["Bot API"])
async def list_sessions():
    """Lists all active meeting sessions currently managed by the bot."""
    return bot.active_sessions

# --- 4. Reporting Endpoints (Internal Bot usage) ---

@app.post("/api/meetings", tags=["Internal"], summary="Register Meeting")
async def register_meeting(report: MeetingReport):
    """Internal: allows the bot to report discovered meetings."""
    reported_meetings[report.meeting_id] = report.model_dump()
    reported_meetings[report.meeting_id]["status"] = "scheduled"
    logger.debug(f"Meeting reported: {report.title}")
    return {"status": "success"}

@app.patch("/api/meetings/{meeting_id}/complete", tags=["Internal"])
async def complete_meeting(meeting_id: str):
    """Internal: allows the bot to mark a meeting as completed."""
    if meeting_id in reported_meetings:
        reported_meetings[meeting_id]["status"] = "completed"
        reported_meetings[meeting_id]["completed_at"] = datetime.now().isoformat()
    return {"status": "success"}

@app.post("/api/sessions", tags=["Internal"])
async def start_session(report: SessionReport):
    """Internal: allows the bot to report session start."""
    reported_sessions[report.session_id] = report.model_dump()
    reported_sessions[report.session_id]["status"] = "active"
    logger.debug(f"Session started: {report.session_id}")
    return {"status": "success"}

@app.patch("/api/sessions/{session_id}/end", tags=["Internal"])
async def end_session(session_id: str, data: Dict[str, Any]):
    """Internal: allows the bot to report session end."""
    if session_id in reported_sessions:
        reported_sessions[session_id]["status"] = "ended"
        reported_sessions[session_id]["ended_at"] = data.get("ended_at", datetime.now().isoformat())
    return {"status": "success"}

@app.get("/api/reported/meetings", tags=["Internal"])
async def get_reported_meetings():
    """Get history of meetings reported to the backend."""
    return list(reported_meetings.values())

@app.get("/api/reported/sessions", tags=["Internal"])
async def get_reported_sessions():
    """Get history of sessions reported to the backend."""
    return list(reported_sessions.values())

if __name__ == "__main__":
    import uvicorn
    # Start the consolidated API server
    uvicorn.run(app, host="0.0.0.0", port=8888)
