from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str
    download_dir: Path = Path("./downloads")
    temp_dir: Path = Path("./tmp")
    database_path: Path = Path("./data/bot.db")
    max_workers: int = 2
    max_active_jobs_per_user: int = 2
    max_file_size_mb: int = 2048
    max_download_seconds: int = 3600
    storage_endpoint: str = ""
    storage_region: str = "auto"
    storage_bucket: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_public_base_url: str = ""
    storage_presigned_ttl: int = 86400
    log_level: str = "INFO"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


settings = Settings()
