from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration, overridable with WORKOUT_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="WORKOUT_")

    data_dir: Path = PROJECT_DIR / "data"
    # Default seed source: the ZIP supplied with the project.
    seed_path: Path = PROJECT_DIR / "seed" / "home_gym_workout_with_images.zip"
    # Import the seed automatically on startup when the database has no exercises.
    auto_seed: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Address people open the app at, e.g. http://raspberrypi.local:8080 (used for links in emails).
    app_url: str | None = None

    # Outgoing email for plan-assistant prompts. Leave smtp_host empty to disable email.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None  # defaults to smtp_username

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and (self.smtp_from or self.smtp_username))

    @property
    def database_path(self) -> Path:
        return self.data_dir / "workout_pal.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


@lru_cache
def get_settings() -> Settings:
    return Settings()
