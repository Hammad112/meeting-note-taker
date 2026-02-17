"""
FastAPI Entry Point for Meeting Bot.
Simplified API - manual join only (no auth, no calendar polling).
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.bot import MeetingBot
from app.config import settings, logger


# Initialize core bot
bot = MeetingBot()


class CaptionLanguage(str, Enum):
    """Supported caption languages for Google Meet transcription (89 languages)."""
    AFRIKAANS_ZA = "Afrikaans (South Africa)"
    ALBANIAN_AL = "Albanian (Albania)"
    AMHARIC_ET = "Amharic (Ethiopia)"
    ARABIC_EG = "Arabic (Egypt)"
    ARABIC_LEVANT = "Arabic (Levant)"
    ARABIC_MAGHREBI = "Arabic (Maghrebi)"
    ARABIC_GULF = "Arabic (Peninsular Gulf)"
    ARABIC_AE = "Arabic (United Arab Emirates)"
    ARMENIAN_AM = "Armenian (Armenia)"
    AZERBAIJANI_AZ = "Azerbaijani (Azerbaijan)"
    BASQUE_ES = "Basque (Spain)"
    BENGALI_BD = "Bengali (Bangladesh)"
    BULGARIAN_BG = "Bulgarian (Bulgaria)"
    BURMESE_MM = "Burmese (Myanmar)"
    CATALAN_ES = "Catalan (Spain)"
    CHINESE_CANTONESE = "Chinese, Cantonese (Traditional)"
    CHINESE_MANDARIN_SIMPLIFIED = "Chinese, Mandarin (Simplified)"
    CHINESE_MANDARIN_TRADITIONAL = "Chinese, Mandarin (Traditional)"
    CZECH_CZ = "Czech (Czech Republic)"
    DUTCH = "Dutch"
    ENGLISH = "English"
    ENGLISH_UK = "English (UK)"
    ENGLISH_AU = "English (Australia)"
    ENGLISH_IN = "English (India)"
    ENGLISH_PH = "English (Philippines)"
    ESTONIAN_EE = "Estonian (Estonia)"
    FILIPINO_PH = "Filipino (Philippines)"
    FINNISH_FI = "Finnish (Finland)"
    FRENCH = "French"
    FRENCH_CA = "French (Canada)"
    GALICIAN_ES = "Galician (Spain)"
    GEORGIAN_GE = "Georgian (Georgia)"
    GERMAN = "German"
    GREEK_GR = "Greek (Greece)"
    GUJARATI_IN = "Gujarati (India)"
    HEBREW_IL = "Hebrew (Israel)"
    HINDI = "Hindi"
    HUNGARIAN_HU = "Hungarian (Hungary)"
    ICELANDIC_IS = "Icelandic (Iceland)"
    INDONESIAN_ID = "Indonesian (Indonesia)"
    ITALIAN = "Italian"
    JAPANESE = "Japanese"
    JAVANESE_ID = "Javanese (Indonesia)"
    KANNADA_IN = "Kannada (India)"
    KAZAKH_KZ = "Kazakh (Kazakhstan)"
    KHMER_KH = "Khmer (Cambodia)"
    KINYARWANDA_RW = "Kinyarwanda (Rwanda)"
    KOREAN = "Korean"
    LAO_LA = "Lao (Laos)"
    LATVIAN_LV = "Latvian (Latvia)"
    LITHUANIAN_LT = "Lithuanian (Lithuania)"
    MACEDONIAN_MK = "Macedonian (North Macedonia)"
    MALAY_MY = "Malay (Malaysia)"
    MALAYALAM_IN = "Malayalam (India)"
    MARATHI_IN = "Marathi (India)"
    MONGOLIAN_MN = "Mongolian (Mongolia)"
    NEPALI_NP = "Nepali (Nepal)"
    NORTHERN_SOTHO_ZA = "Northern Sotho (South Africa)"
    NORWEGIAN_NO = "Norwegian (Norway)"
    PERSIAN_IR = "Persian (Iran)"
    POLISH_PL = "Polish (Poland)"
    PORTUGUESE_BR = "Portuguese (Brazil)"
    PORTUGUESE_PT = "Portuguese (Portugal)"
    ROMANIAN_RO = "Romanian (Romania)"
    RUSSIAN = "Russian"
    SERBIAN_RS = "Serbian (Serbia)"
    SESOTHO_ZA = "Sesotho (South Africa)"
    SINHALA_LK = "Sinhala (Sri Lanka)"
    SLOVAK_SK = "Slovak (Slovakia)"
    SLOVENIAN_SI = "Slovenian (Slovenia)"
    SPANISH_MX = "Spanish (Mexico)"
    SPANISH_ES = "Spanish (Spain)"
    SUNDANESE_ID = "Sundanese (Indonesia)"
    SWAHILI = "Swahili"
    SWATI_ZA = "Swati (South Africa)"
    SWEDISH_SE = "Swedish (Sweden)"
    TAMIL_IN = "Tamil (India)"
    TELUGU_IN = "Telugu (India)"
    THAI_TH = "Thai (Thailand)"
    TSHIVENDA_ZA = "Tshivenda (South Africa)"
    TSWANA_ZA = "Tswana (South Africa)"
    TURKISH_TR = "Turkish (Turkey)"
    UKRAINIAN_UA = "Ukrainian (Ukraine)"
    URDU_PK = "Urdu (Pakistan)"
    UZBEK_UZ = "Uzbek (Uzbekistan)"
    VIETNAMESE_VN = "Vietnamese (Vietnam)"
    XHOSA_ZA = "Xhosa (South Africa)"
    XITSONGA_ZA = "Xitsonga (South Africa)"
    ZULU_ZA = "Zulu (South Africa)"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    logger.info("Starting Meeting Bot application...")
    
    try:
        await bot.initialize()
    except Exception as e:
        logger.error(f"Failed to start bot during startup: {e}")
    
    yield
    
    await bot.shutdown()
    logger.info("Meeting Bot application shut down")


DESC = """
## 🚀 Meeting Bot API

### Manual Join
Use the **POST /api/join** endpoint to have the bot join any meeting instantly.

### Monitoring
Check **GET /api/status** and **GET /api/sessions** to monitor the bot.
"""

app = FastAPI(
    title="Meeting Bot API",
    description=DESC,
    version="2.0.0",
    lifespan=lifespan
)


# Request Models
class ManualJoinRequest(BaseModel):
    bot_name: str = Field(..., json_schema_extra={"examples": ["Bot-01"]})
    meeting_url: str = Field(..., json_schema_extra={"examples": ["https://meet.google.com/abc-defg-hij"]})
    s3_bucket_name: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "examples": ["my-meeting-transcripts"],
            "description": "S3 bucket name. Uses env var AWS_S3_BUCKET_NAME if not provided."
        }
    )
    aws_access_key_id: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "description": "AWS access key. Uses env var AWS_ACCESS_KEY_ID if not provided."
        }
    )
    aws_secret_access_key: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "description": "AWS secret key. Uses env var AWS_SECRET_ACCESS_KEY if not provided."
        }
    )
    aws_region: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "examples": ["us-east-1"],
            "description": "AWS region. Defaults to 'us-east-1'."
        }
    )
    caption_language: CaptionLanguage = Field(
        default=CaptionLanguage.ENGLISH,
        json_schema_extra={
            "description": "Caption language for transcription (89 languages supported)."
        }
    )


# --- API Endpoints ---

@app.get("/", tags=["Status"], summary="Health Check")
async def root():
    """Returns application health and status."""
    return {
        "status": "online",
        "bot_status": bot.get_status(),
        "endpoints": {
            "status": "GET /api/status",
            "sessions": "GET /api/sessions",
            "manual_join": "POST /api/join"
        }
    }


@app.get("/api/status", tags=["Bot API"], summary="Get Bot Status")
async def get_bot_status():
    """Operational status of the bot."""
    return bot.get_status()


@app.post("/api/join", tags=["Bot API"], summary="Join Meeting")
async def manual_join(request: ManualJoinRequest):
    """
    Manually trigger the bot to join a meeting.
    
    **Required**: bot_name, meeting_url
    
    **Optional**: S3 credentials, caption_language
    """
    result = await bot.manual_join_meeting(
        bot_name=request.bot_name,
        meeting_url=request.meeting_url,
        s3_bucket_name=request.s3_bucket_name,
        aws_access_key_id=request.aws_access_key_id,
        aws_secret_access_key=request.aws_secret_access_key,
        aws_region=request.aws_region,
        caption_language=request.caption_language.value
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to join meeting"))
    return result


@app.get("/api/sessions", tags=["Bot API"], summary="List Active Sessions")
async def list_sessions():
    """Lists all active meeting sessions."""
    return bot.active_sessions


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
