"""
Configuration settings for the Meeting Bot.
Uses Pydantic Settings for type-safe configuration with environment variable support.
"""

from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from enum import Enum


class EmailProvider(str, Enum):
    """Supported email providers."""
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    CALENDAR_API = "calendar_api"  # Use backend calendar API endpoint
    BOTH = "both"


class AuthMethod(str, Enum):
    """Authentication methods."""
    OAUTH = "oauth"
    CREDENTIALS = "credentials"
    AUTO = "auto"


class TranscriptionProvider(str, Enum):
    """Supported transcription services."""
    OPENAI_WHISPER = "openai_whisper"
    DEEPGRAM = "deepgram"
    LOCAL_WHISPER = "local_whisper"


class MeetingPlatform(str, Enum):
    """Supported meeting platforms."""
    TEAMS = "teams"
    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"


class GmailSettings(BaseSettings):
    """Gmail-specific configuration."""
    model_config = SettingsConfigDict(env_prefix="GMAIL_")
    
    auth_method: AuthMethod = Field(
        default=AuthMethod.AUTO,
        description="Authentication method: oauth, credentials, or auto"
    )
    credentials_file: str = Field(
        default="credentials/gmail_credentials.json",
        description="Path to Gmail OAuth2 credentials JSON file"
    )
    token_file: str = Field(
        default="credentials/gmail_token.json",
        description="Path to store Gmail OAuth2 token"
    )
    direct_credentials_file: str = Field(
        default="credentials/gmail_direct_credentials.json",
        description="Path to direct credentials (email/password)"
    )
    email: str = Field(
        default="",
        description="Gmail email address (for direct credentials)"
    )
    password: str = Field(
        default="",
        description="Gmail app password or token (for direct credentials)"
    )
    scopes: List[str] = Field(
        default=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly"
        ],
        description="Gmail API scopes"
    )


class OutlookSettings(BaseSettings):
    """Outlook/Microsoft Graph configuration."""
    model_config = SettingsConfigDict(env_prefix="OUTLOOK_")
    
    client_id: str = Field(
        default="",
        description="Azure AD Application (client) ID"
    )
    client_secret: str = Field(
        default="",
        description="Azure AD client secret"
    )
    tenant_id: str = Field(
        default="common",
        description="Azure AD tenant ID (use 'common' for multi-tenant)"
    )
    redirect_uri: str = Field(
        default="http://localhost:8400/callback",
        description="OAuth2 redirect URI"
    )
    token_file: str = Field(
        default="credentials/outlook_token.json",
        description="Path to store Outlook OAuth2 token"
    )
    scopes: List[str] = Field(
        default=[
            "User.Read",
            "Calendars.Read",
            "Mail.Read"
        ],
        description="Microsoft Graph API scopes"
    )


class TranscriptionSettings(BaseSettings):
    """Transcription service configuration."""
    model_config = SettingsConfigDict(env_prefix="TRANSCRIPTION_")
    
    provider: TranscriptionProvider = Field(
        default=TranscriptionProvider.OPENAI_WHISPER,
        description="Transcription service provider"
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for Whisper"
    )
    deepgram_api_key: str = Field(
        default="",
        description="Deepgram API key"
    )
    language: str = Field(
        default="en",
        description="Default transcription language"
    )
    chunk_duration_seconds: int = Field(
        default=10,
        description="Duration of audio chunks for transcription"
    )


class AudioSettings(BaseSettings):
    """Audio capture configuration."""
    model_config = SettingsConfigDict(env_prefix="AUDIO_")
    
    device_name: str = Field(
        default="BlackHole 2ch",
        description="Virtual audio device name"
    )
    device_index: Optional[int] = Field(
        default=None,
        description="Audio device index (auto-detected if None)"
    )
    sample_rate: int = Field(
        default=16000,
        description="Audio sample rate in Hz"
    )
    channels: int = Field(
        default=1,
        description="Number of audio channels"
    )
    chunk_size: int = Field(
        default=1024,
        description="Audio buffer chunk size"
    )


class SchedulerSettings(BaseSettings):
    """Meeting scheduler configuration."""
    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")
    
    email_poll_interval_seconds: int = Field(
        default=40,
        description="How often to check for new meeting invites (in seconds)"
    )
    join_before_start_minutes: int = Field(
        default=1,
        description="Join meeting X minutes before start time"
    )
    max_join_after_start_minutes: int = Field(
        default=10,
        description="Maximum minutes after start time to allow joining (prevents joining very late)"
    )
    lookahead_hours: int = Field(
        default=24,
        description="Look for meetings within the next X hours"
    )
    max_concurrent_meetings: int = Field(
        default=5,
        description="Maximum concurrent meeting sessions"
    )


class BackendSettings(BaseSettings):
    """Backend API configuration."""
    model_config = SettingsConfigDict(env_prefix="BACKEND_")
    
    url: str = Field(
        default="http://localhost:8000",
        description="Backend API base URL"
    )
    api_key: str = Field(
        default="",
        description="Backend API key for authentication"
    )
    websocket_path: str = Field(
        default="/ws/transcripts",
        description="WebSocket endpoint path"
    )


class AuthServerSettings(BaseSettings):
    """Authentication server configuration."""
    model_config = SettingsConfigDict(env_prefix="AUTH_SERVER_")
    
    enabled: bool = Field(
        default=True,
        description="Enable authentication server"
    )
    host: str = Field(
        default="localhost",
        description="Auth server host"
    )
    port: int = Field(
        default=8888,
        description="Auth server port"
    )


class Settings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )
    
    # Email provider selection
    email_provider: EmailProvider = Field(
        default=EmailProvider.BOTH,
        description="Which email provider(s) to use"
    )
    
    # Nested settings
    gmail: GmailSettings = Field(default_factory=GmailSettings)
    outlook: OutlookSettings = Field(default_factory=OutlookSettings)
    transcription: TranscriptionSettings = Field(default_factory=TranscriptionSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    backend: BackendSettings = Field(default_factory=BackendSettings)
    auth_server: AuthServerSettings = Field(default_factory=AuthServerSettings)
    
    # Application settings
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Supported platforms
    enabled_platforms: List[MeetingPlatform] = Field(
        default=[
            MeetingPlatform.TEAMS,
            MeetingPlatform.ZOOM,
            MeetingPlatform.GOOGLE_MEET
        ],
        description="Enabled meeting platforms"
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


# Global settings instance
settings = Settings()
