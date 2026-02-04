from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ------------------------------------------------------
# MEDIA ITEM INSIDE A GALLERY
# ------------------------------------------------------
class GalleryMediaOut(BaseModel):
    id: int
    gallery_id: Optional[int] = None
    event_id: Optional[int] = None
    profile_id: Optional[str] = None

    file_path: str
    file_type: str
    caption: Optional[str] = None
    file_size: Optional[int] = None

    thumbnail_path: Optional[str] = None
    voice_note_path: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    # NEW FIELD: actual duration of videos in seconds
    duration_seconds: Optional[int] = None

    model_config = {
        "from_attributes": True
    }


# ------------------------------------------------------
# UPDATE MEDIA item (caption or voice)
# ------------------------------------------------------
class GalleryMediaUpdate(BaseModel):
    caption: Optional[str] = None


# ------------------------------------------------------
# CREATE GALLERY
# ------------------------------------------------------
class GalleryCreate(BaseModel):
    event_id: int
    title: str
    description: Optional[str] = None

    # NEW FIELD
    long_description: Optional[str] = None


# ------------------------------------------------------
# UPDATE GALLERY (title / descriptions)
# ------------------------------------------------------
class GalleryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

    # NEW FIELD
    long_description: Optional[str] = None


# ------------------------------------------------------
# FULL GALLERY OUTPUT
# ------------------------------------------------------
class GalleryOut(BaseModel):
    id: int
    event_id: int

    title: str
    description: Optional[str]
    long_description: Optional[str] = None

    position: Optional[int] = None

    thumbnail_media_id: Optional[int] = None
    thumbnail_media: Optional[GalleryMediaOut] = None

    voice_note_path: Optional[str] = None
    created_at: Optional[datetime] = None

    media_items: List[GalleryMediaOut] = []

    model_config = {
        "from_attributes": True
    }
