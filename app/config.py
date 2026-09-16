from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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
    max_model_mb: int = 20480
    max_summary_chunks: int = 256
    ocr_language: str = "eng"
    queue_limit: int = Field(default=32, ge=1, le=256)
    queue_per_user: int = Field(default=2, ge=1, le=32)
    queue_timeout: int = Field(default=600, ge=1, le=3600)
    max_backup_mb: int = Field(default=2048, ge=1, le=2048)
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    launch_root: Path | None = None

    @property
    def db_path(self):
        return self.data_dir / "nelsonict.sqlite3"


settings = Settings()

# Stable bootstrap directory: every process reads the same overlay on restart.
# GUI migration never changes settings of a process that is already running.
settings_root = settings.data_dir.resolve()
settings.launch_root = settings_root

def load_overlay():
    import json
    path = settings_root / "runtime-settings.json"
    if path.exists():
        values = json.loads(path.read_text())
        allowed = {"data_dir", "models_dir", "embedding_model", "allowed_hosts", "cookie_secure", "bind_host", "bind_port"}
        if not isinstance(values, dict) or set(values) - allowed:
            raise RuntimeError("Invalid migration runtime settings.")
        merged = settings.model_dump()
        merged.update(values)
        checked = Settings(**merged)
        for key in allowed & values.keys():
            setattr(settings, key, getattr(checked, key))

load_overlay()
