"""Centralized configuration with environment variable validation."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_cloud_project: str
    google_cloud_location: str = "us-central1"
    gcs_bucket_name: str
    veo_poll_timeout_seconds: int = 300
    veo_poll_interval_seconds: int = 5
    default_voice: str = "en-US-Neural2-J"
    default_speaking_rate: float = 0.9
    max_scenes: int = 10
    storyboard_model: str = "gemini-2.5-flash"
    ambient_music_path: str | None = None
    burn_subtitles: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


_settings = None


def get_settings() -> Settings:
    """Get cached application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
