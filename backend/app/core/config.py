import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ENV: str = "development"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # File storage paths
    UPLOAD_DIR: str = "uploads"
    OUTPUT_DIR: str = "generated_subtitles"
    LOG_DIR: str = "logs"
    MAX_UPLOAD_SIZE: int = 104857600  # 100 MB
    
    # Voice Generation paths & settings
    AUDIO_OUTPUT_DIR: str = "generated_audio"
    VOICE_REFERENCE_DIR: str = "voice_references"
    KOKORO_DEFAULT_VOICE: str = "af_heart"
    VOICE_TEXT_MAX_CHARS: int = 1500
    
    # Faster-Whisper ASR
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    
    # OpenRouter API
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "google/gemma-3-12b-it"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # Resolve absolute paths
    @property
    def upload_path(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        if p.is_absolute():
            return p
        return Path(__file__).resolve().parent.parent.parent / p

    @property
    def output_path(self) -> Path:
        p = Path(self.OUTPUT_DIR)
        if p.is_absolute():
            return p
        return Path(__file__).resolve().parent.parent.parent / p

    @property
    def log_path(self) -> Path:
        p = Path(self.LOG_DIR)
        if p.is_absolute():
            return p
        return Path(__file__).resolve().parent.parent.parent / p

    @property
    def audio_output_path(self) -> Path:
        p = Path(self.AUDIO_OUTPUT_DIR)
        if p.is_absolute():
            return p
        return Path(__file__).resolve().parent.parent.parent / p
        
    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
