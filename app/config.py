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

    LOCAL_MEDIA_PATH: str = os.getenv(
        "LOCAL_MEDIA_PATH",
        "./media"
    )

    # -------------------------------------------------------
    # Supabase Storage
    # -------------------------------------------------------
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_BUCKET: str = os.getenv("SUPABASE_BUCKET", "media")

    # -------------------------------------------------------
    # Supabase Auth (JWT verification)
    # -------------------------------------------------------
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")


# ✅ This stays OUTSIDE the class
settings = Settings()
