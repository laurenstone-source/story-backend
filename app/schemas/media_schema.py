# app/schemas/media_schema.py

from pydantic import BaseModel, field_serializer
from datetime import datetime
from typing import Optional

# -----------------------------------------------------
# UNIVERSAL MEDIA FILE OUTPUT (generic media object)
# -----------------------------------------------------
from app.utils.urls import absolute_media_url


class MediaFileOut(BaseModel):
    id: int
    file_path: str
    file_type: str
    caption: Optional[str] = None
    voice_note_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    @field_serializer("file_path", "voice_note_path", "thumbnail_path")
    def absolutise_urls(self, v):
        return absolute_media_url(v)

    model_config = {"from_attributes": True}

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
