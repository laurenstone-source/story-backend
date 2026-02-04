# app/schemas/media_schema.py

from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# -----------------------------------------------------
# UNIVERSAL MEDIA FILE OUTPUT (generic media object)
# -----------------------------------------------------
class MediaFileOut(BaseModel):
    id: int
    file_path: str
    file_type: str
    caption: Optional[str] = None
    voice_note_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


# -----------------------------------------------------
# EVENT MEDIA SCHEMA
# -----------------------------------------------------
class MediaOutEvent(BaseModel):
    id: int
    event_id: int | None = None
    profile_id: str | None = None
    file_path: str
    file_type: str
    caption: str | None = None

    model_config = {
        "from_attributes": True
    }


# -----------------------------------------------------
# PROFILE MEDIA SCHEMA
# -----------------------------------------------------
class MediaOutProfile(BaseModel):
    id: int
    profile_id: str | None = None
    event_id: int | None = None
    file_path: str
    file_type: str
    caption: str | None = None

    model_config = {
        "from_attributes": True
    }
