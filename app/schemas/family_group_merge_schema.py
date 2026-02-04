from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FamilyGroupMergeRequestCreate(BaseModel):
    from_group_id: str
    message: Optional[str] = None


class GroupMergeRequestOut(BaseModel):
    id: str

    from_group_id: str
    from_group_name: Optional[str] = None
    from_group_image_url: Optional[str] = None

    to_group_id: str
    to_group_name: Optional[str] = None
    to_group_image_url: Optional[str] = None

    message: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
