# app/schemas/family_group_post_comment_schema.py

from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class GroupPostCommentCreate(BaseModel):
    content_text: str


class GroupPostCommentOut(BaseModel):
    id: str
    post_id: str
    author_profile_id: str

    author_name: str | None
    author_profile_picture: str | None

    media_url: Optional[str] = None
    media_type: Optional[str] = None

    content_text: str
    status: str

    created_at: datetime
    updated_at: datetime | None

    is_hidden: bool
    can_edit: bool
    can_delete: bool
GroupPostCommentOut.model_rebuild()
