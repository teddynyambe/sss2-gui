"""Application configuration."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    # Serial port configuration
    # Empty = auto-detect SSS2 (tty.usbmodem* on Mac, ttyACM* on Linux).
    # Set SSS2_SERIAL_PORT in env to use a specific port.
    SSS2_SERIAL_PORT: str = ""
    SSS2_BAUDRATE: int = 115200
    
    # Store paths
    BASE_DIR: Path = Path(__file__).parent.parent
    STORE_DIR: Path = BASE_DIR / "store" / "data"
    CATALOG_FILE: str = "peripheral_catalog.json"
    STATE_FILE: str = "current_device_state.json"
    SNAPSHOTS_DIR: str = "snapshots"
    
    # Application version
    VERSION: str = "1.0.0"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
