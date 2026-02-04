from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# --------------------------------------------------
# CREATE
# --------------------------------------------------
class FamilyGroupCreate(BaseModel):
    name: str

# --------------------------------------------------
# RENAME
# --------------------------------------------------
class FamilyGroupRename(BaseModel):
    name: str

# --------------------------------------------------
# MEMBER
# --------------------------------------------------
class FamilyGroupMemberOut(BaseModel):
    profile_id: str
    display_name: Optional[str]
    profile_image_url: Optional[str] = None
    joined_at: datetime
    role: str

    class Config:
        from_attributes = True


# --------------------------------------------------
# GROUP (LIST / SUMMARY)
# --------------------------------------------------
class FamilyGroupOut(BaseModel):
    id: str
    name: str
    created_by_profile_id: str
    created_at: datetime

    is_archived: bool
    merged_into_group_id: Optional[str] = None
    group_image_url: Optional[str] = None

    class Config:
        from_attributes = True
# --------------------------------------------------
# GROUP DETAIL
# --------------------------------------------------
class FamilyGroupDetailOut(BaseModel):
    id: str
    name: str
    created_by_profile_id: str
    created_at: datetime

    is_archived: bool
    merged_into_group_id: Optional[str] = None
    group_image_url: Optional[str] = None

    members: List[FamilyGroupMemberOut] = []

    my_role: str
    my_profile_id: str   # 👈 FIXED LINE

    class Config:
        from_attributes = True


# --------------------------------------------------
# SEARCH
# --------------------------------------------------
class FamilyGroupSearchOut(BaseModel):
    id: str
    name: str
    group_image_url: Optional[str] = None

    class Config:
        from_attributes = True
