from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NELSON_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    models_dir: Path = Path("models")
    embedding_model: str = ""
    cookie_secure: bool = False
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    session_hours: int = 24
    max_upload_mb: int = 25
    user_storage_mb: int = 250
    max_pages: int = 300
    max_chunks: int = 10000
    index_timeout: int = 600
    ocr_language: str = "eng"

    @property
    def db_path(self):
        return self.data_dir / "nelsonict.sqlite3"


settings = Settings()
