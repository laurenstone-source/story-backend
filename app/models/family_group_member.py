from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class FamilyGroupMember(Base):
    __tablename__ = "family_group_members"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String, ForeignKey("family_groups.id"), nullable=False)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)

    role = Column(String, default="member")  # member | admin
    joined_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("FamilyGroup", back_populates="members")
    profile = relationship("Profile", foreign_keys=[profile_id])
