from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MediaLibraryItemOut(BaseModel):
    id: str                 # string because audio items will use "profile-audio", etc.
    file_path: str          # absolute URL
    file_type: str          # "image" | "video" | "audio"

    # For nice UI
    label: str              # "Wedding", "Reception", "Profile voice note", etc.
    origin: str             # "Event: Wedding", "Gallery: Reception", "Profile: John Smith"

    # Optional metadata
    caption: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    # Optional links
    thumbnail_path: Optional[str] = None     # absolute URL for video thumb
    voice_note_path: Optional[str] = None    # absolute URL (if this media has its own voice note)

    # IDs for actions
    media_id: Optional[int] = None
    profile_id: Optional[str] = None
    event_id: Optional[int] = None
    gallery_id: Optional[int] = None
