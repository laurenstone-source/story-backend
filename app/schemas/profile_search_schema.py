from pydantic import BaseModel
from typing import Optional


class ProfileSearchOut(BaseModel):
    id: str
    full_name: Optional[str]
    profile_picture_url: Optional[str]
    is_public: bool
    can_view: bool

    class Config:
        from_attributes = True
