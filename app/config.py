import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Settings:
    # -------------------------------------------------------
    # Project
    # -------------------------------------------------------
    PROJECT_NAME: str = "Story App API"
    ENV: str = os.getenv("ENV", "dev")

        # -------------------------------------------------------
    # Database
    # -------------------------------------------------------
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./story.db"
    )

    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


    # -------------------------------------------------------
    # Authentication / JWT
    # -------------------------------------------------------
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "supersecretlocalkey123"   # Only used for local dev
    )
    ALGORITHM: str = "HS256"

    # 1 day token expiry by default
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24)
    )
       # -------------------------------------------------------
    # Public base URL (used to build absolute media URLs)
    # -------------------------------------------------------
    BASE_URL: str = os.getenv(
        "BASE_URL",
        "http://127.0.0.1:8000"
    )


    # -------------------------------------------------------
    # Storage Configuration
    # -------------------------------------------------------
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")

    # Local media folder
    LOCAL_MEDIA_PATH: str = os.getenv(
        "LOCAL_MEDIA_PATH",
        "./media"   # Default for dev
    )


# Single instance that is imported everywhere
settings = Settings()
