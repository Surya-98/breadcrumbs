from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    db_path: Path
    screenshots_dir: Path
    cloud_upload_enabled: bool
    mongodb_uri: str | None
    mongodb_database: str
    gemini_api_key: str | None
    screen_capture_interval_sec: float

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("BREADCRUMBS_DATA_DIR", ".breadcrumbs-data")).expanduser()
        db_path = Path(os.getenv("BREADCRUMBS_DB_PATH", data_dir / "breadcrumbs.sqlite3")).expanduser()
        screenshots_dir = Path(
            os.getenv("BREADCRUMBS_SCREENSHOTS_DIR", data_dir / "screenshots")
        ).expanduser()
        return cls(
            host=os.getenv("BREADCRUMBS_HOST", "127.0.0.1"),
            port=int(os.getenv("BREADCRUMBS_PORT", "8765")),
            data_dir=data_dir,
            db_path=db_path,
            screenshots_dir=screenshots_dir,
            cloud_upload_enabled=_env_bool("BREADCRUMBS_CLOUD_UPLOAD", False),
            mongodb_uri=os.getenv("MONGODB_URI") or None,
            mongodb_database=os.getenv("MONGODB_DATABASE", "breadcrumbs"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            screen_capture_interval_sec=float(os.getenv("BREADCRUMBS_CAPTURE_INTERVAL", "2.0")),
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
