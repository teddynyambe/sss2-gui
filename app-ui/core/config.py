"""Application configuration."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Store paths
    BASE_DIR: Path = Path(__file__).parent.parent
    STORE_DIR: Path = BASE_DIR / "store" / "data"
    CATALOG_FILE: str = "peripheral_catalog.json"

    # Application version
    VERSION: str = "1.0.0"

    # CAN auto-connect on startup
    CAN_INTERFACE: str = "socketcan"
    CAN_CHANNEL: str = "can0"
    CAN_BITRATE: int = 250000
    CAN_AUTO_CONNECT: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
