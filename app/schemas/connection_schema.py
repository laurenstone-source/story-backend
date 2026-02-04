from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# --------------------------------------------------
# PROFILE PREVIEW (used in connections)
# --------------------------------------------------
class ProfilePreview(BaseModel):
    id: str
    full_name: str | None
    profile_image: str | None


# --------------------------------------------------
# CREATE CONNECTION
# --------------------------------------------------
class ConnectionCreate(BaseModel):
    to_profile_id: str
    relation_type: Optional[str] = None


# --------------------------------------------------
# CONNECTION OUT (single connection)
# --------------------------------------------------
class ConnectionOut(BaseModel):
    id: int
    status: str
    relation_type: Optional[str] = None
    direction: str
    profile: ProfilePreview
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --------------------------------------------------
# CONNECTIONS OVERVIEW
# --------------------------------------------------
class ConnectionMineOut(BaseModel):
    incoming_pending: List[ConnectionOut]
    outgoing_pending: List[ConnectionOut]
    accepted: List[ConnectionOut]
# --------------------------------------------------
# Set Relationship
# --------------------------------------------------

class SetRelationshipPayload(BaseModel):
    relationship: Optional[str] | None
