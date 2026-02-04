from sqlalchemy import Column, String, Date, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class FamilyPerson(Base):
    """
    A node in a group’s tree.
    Can exist without a real Profile (unclaimed).
    """
    __tablename__ = "family_people"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String, ForeignKey("family_groups.id"), nullable=False)

    display_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=True)
    is_deceased = Column(Boolean, default=False)

    # optional link to a real user profile (ONLY after claim/confirmation)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("Profile", foreign_keys=[profile_id])
