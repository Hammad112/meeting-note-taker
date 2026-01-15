"""
FastAPI application initialization for Meeting Bot API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.v1.router import api_router

# Setup logging
setup_logging()

# Create FastAPI application
app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description="Production-grade Meeting Bot API for automated meeting joining and transcription",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """
    Application startup event.
    Initialize MeetingBot service and start background tasks.
    """
    from app.domain.services.meeting_bot_service import MeetingBotService
    from app.core.dependencies import set_meeting_bot_instance
    from app.core.logging import get_logger
    
    logger = get_logger("startup")
    logger.info("Starting Meeting Bot API...")
    
    # Initialize MeetingBot service
    bot = MeetingBotService()
    set_meeting_bot_instance(bot)
    
    # Initialize the bot (authenticate services, start components)
    success = await bot.initialize()
    
    if not success:
        logger.warning("Bot initialization incomplete - may need authentication")
    else:
        logger.info("Meeting Bot API started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown event.
    Cleanup resources and stop background tasks.
    """
    from app.core.dependencies import get_meeting_bot_service
    from app.core.logging import get_logger
    
    logger = get_logger("shutdown")
    logger.info("Shutting down Meeting Bot API...")
    
    try:
        bot = await get_meeting_bot_service()
        await bot.shutdown()
    except:
        pass
    
    logger.info("Meeting Bot API shutdown complete")


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint - redirect to dashboard.
    """
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/v1/auth")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.auth_server.host,
        port=settings.auth_server.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
