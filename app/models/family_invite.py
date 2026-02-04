from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class FamilyInvite(Base):
    __tablename__ = "family_invites"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String, ForeignKey("family_groups.id"), nullable=False)

    invited_by_profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)
    invited_profile_id = Column(String, ForeignKey("profiles.id"), nullable=True)
    email = Column(String, nullable=True)

    status = Column(String, default="pending")  # pending / accepted / declined / cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("FamilyGroup")
    invited_by = relationship("Profile", foreign_keys=[invited_by_profile_id])
    invited_profile = relationship("Profile", foreign_keys=[invited_profile_id])
