from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class GroupPostCreate(BaseModel):
    content_text: Optional[str] = None


class GroupPostOut(BaseModel):
    id: str
    group_id: str
    author_profile_id: str
    author_name: Optional[str]
    author_profile_picture: Optional[str]  # ✅ ADD THIS
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    content_text: Optional[str]
    status: str    # 👇 UI permissions
    created_at: datetime
    updated_at: datetime
    comment_count: int
    can_edit: bool
    can_delete: bool
    is_hidden: bool

    last_activity_at: datetime

    class Config:
        from_attributes = True
