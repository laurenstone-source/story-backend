from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class FamilyGroup(Base):
    __tablename__ = "family_groups"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    created_by_profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ✅ NEW: group image
    group_image_url = Column(String, nullable=True)

    # Archive/merge tracking (never delete data)
    is_archived = Column(Boolean, default=False, nullable=False)
    merged_into_group_id = Column(String, ForeignKey("family_groups.id"), nullable=True)
    archived_at = Column(DateTime, nullable=True)

    created_by_profile = relationship(
        "Profile",
        foreign_keys=[created_by_profile_id],
    )

    members = relationship(
        "FamilyGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )
