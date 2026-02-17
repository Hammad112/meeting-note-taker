"""
Configuration settings for the Meeting Bot.
Simplified - only bot, recording, and S3 settings.
"""

from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from enum import Enum
from dateutil import tz


class MeetingPlatform(str, Enum):
    """Supported meeting platforms."""
    TEAMS = "teams"
    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"


class RecordingSettings(BaseSettings):
    """Meeting recording configuration."""
    model_config = SettingsConfigDict(env_prefix="RECORDING_")
    
    enabled: bool = Field(default=True, description="Enable automatic recording")
    save_local: bool = Field(default=True, description="Save recordings locally")
    upload_to_s3: bool = Field(default=True, description="Upload to S3 if configured")
    local_path: str = Field(default="recordings", description="Local recordings directory")
    
    # Video settings
    video_codec: str = Field(default="vp9", description="Video codec")
    video_bitrate: int = Field(default=5000000, description="Video bitrate (bps)")
    video_width: int = Field(default=1920, description="Video width")
    video_height: int = Field(default=1080, description="Video height")
    video_framerate: int = Field(default=30, description="Video framerate")
    
    # Audio settings
    audio_codec: str = Field(default="opus", description="Audio codec")
    audio_bitrate: int = Field(default=192000, description="Audio bitrate (bps)")
    audio_sample_rate: int = Field(default=48000, description="Audio sample rate")
    
    # Storage
    max_local_storage_gb: int = Field(default=50, description="Max local storage (GB)")
    delete_after_s3_upload: bool = Field(default=False, description="Delete local after S3 upload")


class BotSettings(BaseSettings):
    """Bot behavior configuration."""
    model_config = SettingsConfigDict(env_prefix="BOT_")
    
    default_bot_name: str = Field(default="Meeting Bot", description="Default bot name")
    teams_bot_name: str = Field(default="Meeting Transcriber", description="Teams bot name")
    google_meet_bot_name: str = Field(default="Meeting Transcriber", description="Meet bot name")
    zoom_bot_name: str = Field(default="Meeting Transcriber", description="Zoom bot name")
    
    lobby_timeout_seconds: int = Field(default=600, description="Max lobby wait (seconds)")
    auto_enable_captions: bool = Field(default=True, description="Auto-enable captions")
    auto_mute_on_join: bool = Field(default=True, description="Auto-mute on join")


class Settings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        extra="ignore"
    )
    
    # Nested settings
    bot: BotSettings = Field(default_factory=BotSettings)
    recording: RecordingSettings = Field(default_factory=RecordingSettings)
    
    # Application settings
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    timezone: str = Field(default="auto", description="Timezone (or 'auto')")
    
    # Enabled platforms
    enabled_platforms: List[MeetingPlatform] = Field(
        default=[
            MeetingPlatform.TEAMS,
            MeetingPlatform.ZOOM,
            MeetingPlatform.GOOGLE_MEET
        ],
        description="Enabled meeting platforms"
    )
    
    @property
    def recordings_dir(self) -> str:
        """Get recordings directory path."""
        return self.recording.local_path
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()

    @property
    def tz_info(self):
        """Get timezone info (auto-detected if 'auto')."""
        if self.timezone.lower() == "auto":
            return tz.tzlocal()
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(self.timezone)
        except Exception:
            return tz.UTC


# Global settings instance
settings = Settings()
