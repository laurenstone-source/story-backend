from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class FamilyGroupJoinRequest(Base):
    __tablename__ = "family_group_join_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String, ForeignKey("family_groups.id"), nullable=False)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)

    status = Column(String, default="pending")  # pending / accepted / declined / cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("FamilyGroup")
    profile = relationship("Profile")
