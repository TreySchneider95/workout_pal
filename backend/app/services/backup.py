import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import get_settings


def backup_database(label: str = "manual") -> Path | None:
    """Copy the live SQLite database to data/backups using SQLite's online backup API.

    Returns the backup path, or None when there is no database yet.
    """
    settings = get_settings()
    source_path = settings.database_path
    if not source_path.exists():
        return None
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = settings.backup_dir / f"workout_pal-{stamp}-{label}.db"
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return target_path
