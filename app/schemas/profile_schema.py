# app/schemas/profile_schema.py

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date
from uuid import UUID


class ProfileBase(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    long_biography: Optional[str] = None

    is_public: Optional[bool] = True
    is_searchable: Optional[bool] = True

    next_of_kin_name: Optional[str] = None
    next_of_kin_email: Optional[EmailStr] = None

    date_of_birth: Optional[date] = None
    is_deceased: Optional[bool] = False
    date_of_death: Optional[date] = None


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(ProfileBase):
    pass


# ======================================================
# ✅ FULL PROFILE OUTPUT
# ======================================================

class ProfileOut(BaseModel):
    id: UUID
    user_id: UUID

    full_name: Optional[str] = None
    bio: Optional[str] = None
    long_biography: Optional[str] = None

    is_public: bool
    is_searchable: Optional[bool] = None

    next_of_kin_name: Optional[str] = None
    next_of_kin_email: Optional[str] = None

    date_of_birth: Optional[date] = None
    is_deceased: bool
    date_of_death: Optional[date] = None

    profile_picture_media_id: Optional[int] = None
    profile_video_media_id: Optional[int] = None

    profile_picture_url: Optional[str] = None
    profile_video_url: Optional[str] = None

    voice_note_path: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str
        }


# ======================================================
# ✅ LIMITED PROFILE OUTPUT
# ======================================================

class ProfileOutLimited(BaseModel):
    id: UUID
    user_id: UUID

    full_name: Optional[str] = None
    bio: Optional[str] = None

    is_public: bool

    dob_label: Optional[str] = None
    is_deceased: Optional[bool] = None

    can_view: bool = False

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str
        }
