import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    return Path(bundle_root) if bundle_root else PROJECT_ROOT


def _default_data_dir() -> Path:
    configured = os.getenv("FINANCE_APP_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if getattr(sys, "frozen", False) or os.getenv("FINANCE_DESKTOP") == "1":
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Ledger Local"
        if sys.platform == "win32":
            return Path(os.getenv("LOCALAPPDATA", Path.home())) / "Ledger Local"
        return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / (
            "ledger-local"
        )
    return PROJECT_ROOT / "data"


RESOURCE_ROOT = _resource_root()
APP_DATA_DIR = _default_data_dir()


class Settings(BaseSettings):
    app_name: str = "Local Finance AI"
    api_prefix: str = "/api"
    database_url: str = f"sqlite:///{APP_DATA_DIR / 'finance.db'}"
    frontend_origin: str = "http://localhost:5173"
    uploads_dir: Path = APP_DATA_DIR / "uploads"
    processed_dir: Path = APP_DATA_DIR / "processed"
    reports_dir: Path = APP_DATA_DIR / "reports"
    docs_dir: Path = RESOURCE_ROOT / "docs"
    chroma_dir: Path = APP_DATA_DIR / "chroma"
    frontend_dist_dir: Path = RESOURCE_ROOT / "frontend_dist"
    max_upload_mb: int = 20
    ocr_enabled: bool = True
    ocr_languages: str = "eng+deu"
    ocr_dpi: int = 300
    ocr_page_segmentation_mode: int = 6
    ollama_enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_seconds: int = 120
    ollama_context_length: int = 8192
    finnhub_api_key: str = ""
    finnhub_base_url: str = "https://finnhub.io/api/v1"
    twelve_data_api_key: str = ""
    twelve_data_base_url: str = "https://api.twelvedata.com"
    fx_base_url: str = "https://api.frankfurter.dev/v1"
    market_data_timeout_seconds: int = 12
    market_credentials_file: Path = APP_DATA_DIR / "market_credentials.json"

    model_config = SettingsConfigDict(
        env_file=(
            PROJECT_ROOT / ".env"
            if not getattr(sys, "frozen", False)
            and os.getenv("FINANCE_DESKTOP") != "1"
            else None
        ),
        env_prefix="FINANCE_",
        extra="ignore",
    )


settings = Settings()
