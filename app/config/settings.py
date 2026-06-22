from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path


DATA_DIR = Path(os.environ.get("NOTEBOOKLM_DATA_DIR", "."))


class Settings(BaseSettings):
    HEADLESS: bool = False
    TIMEOUT_MS: int = 300000  # 5 minutes for generation
    LOGIN_TIMEOUT_SECONDS: int = 0  # 0 waits until sign-in completes
    PARALLEL_EXTRACTIONS: int = 3
    BROWSER_DATA_DIR: Path = DATA_DIR / "browser_data"
    OUTPUT_DIR: Path = DATA_DIR / "output"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
