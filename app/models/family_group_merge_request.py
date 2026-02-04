from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class FamilyGroupMergeRequest(Base):
    __tablename__ = "family_group_merge_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    from_group_id = Column(String, ForeignKey("family_groups.id"), nullable=False)
    to_group_id = Column(String, ForeignKey("family_groups.id"), nullable=False)

    requested_by_profile_id = Column(String, ForeignKey("profiles.id"), nullable=False)

    message = Column(String, nullable=True)

    # pending / accepted / declined / cancelled
    status = Column(String, default="pending", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)

    from_group = relationship("FamilyGroup", foreign_keys=[from_group_id])
    to_group = relationship("FamilyGroup", foreign_keys=[to_group_id])
    requested_by = relationship("Profile", foreign_keys=[requested_by_profile_id])
